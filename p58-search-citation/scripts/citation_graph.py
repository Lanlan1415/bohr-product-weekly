"""Deterministic, source-bound citation tracing and related-work discovery.

No network access is performed.  Citation edges are always ``citing -> cited``;
traversal direction is recorded separately.  Related-work signals are never
silently promoted to citation edges.
"""
from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from collections import deque
from difflib import SequenceMatcher

SCHEMA_VERSION = "citation-trace/v2"


def _text(value):
    return str(value).strip() if value is not None else ""


def _doi(value):
    value = _text(value).lower()
    value = re.sub(r"^(?:https?://(?:dx\.)?doi\.org/|doi:\s*)", "", value)
    return value.rstrip(" .;")


def _title(value):
    value = unicodedata.normalize("NFKD", _text(value))
    value = "".join(c for c in value if not unicodedata.combining(c))
    return " ".join(re.findall(r"[\w]+", value.lower(), flags=re.UNICODE))


def _list(value):
    if value is None:
        return []
    return value if isinstance(value, list) else [value]


def _names(value):
    out = []
    for item in _list(value):
        if isinstance(item, dict):
            name = item.get("name") or " ".join(
                _text(item.get(k)) for k in ("given", "firstName", "family", "lastName")
                if _text(item.get(k)))
            if not name:
                name = item.get("family") or item.get("lastName") or ""
        else:
            name = item
        if _text(name):
            out.append(_text(name))
    return out


def _surname_initial(names):
    out = set()
    for name in names:
        parts = _title(name).split()
        if not parts:
            continue
        if "," in name:
            surname = _title(name.split(",", 1)[0]).replace(" ", "")
            rest = _title(name.split(",", 1)[1]).split()
            initial = rest[0][0] if rest else ""
        elif len(parts) == 1:
            surname, initial = parts[0], ""
        else:
            surname, initial = parts[-1], parts[0][0]
        out.add((surname, initial))
    return out


def _year(record):
    for key in ("year", "publication_year", "published_year"):
        if str(record.get(key) or "").isdigit():
            return int(record[key])
    for key in ("issued", "published", "published-online", "published-print", "date"):
        value = record.get(key)
        if isinstance(value, dict):
            value = value.get("date-time") or value.get("date-parts")
        match = re.search(r"(?:19|20)\d{2}", _text(value))
        if match:
            return int(match.group())
    return None


def _records(spec):
    rows = spec.get("works") or spec.get("records") or spec.get("documents")
    if isinstance(spec.get("sources"), dict) and not rows:
        rows = []
        for source, payload in spec["sources"].items():
            payload = payload if isinstance(payload, dict) else {}
            for record in payload.get("records") or []:
                if isinstance(record, dict):
                    row = dict(record)
                    row.setdefault("source", source)
                    rows.append(row)
    if not isinstance(rows, list):
        return []
    return [dict(row, source=row.get("source") or row.get("database") or "snapshot")
            for row in rows if isinstance(row, dict)]


def _normalise_records(rows):
    out = []
    for index, row in enumerate(rows):
        rid = _text(row.get("id") or row.get("work_id") or row.get("paperId")
                    or row.get("DOI") or row.get("doi") or row.get("title"))
        title = _text(row.get("title") or row.get("display_name"))
        if not rid and title:
            rid = "title:" + _title(title)
        if not rid:
            continue
        source = _text(row.get("source") or "snapshot")
        local = dict(row)
        local.update({
            "_observation": source + ":" + rid + ":" + str(index),
            "_rid": rid, "_source": source, "_title": title,
            "_title_key": _title(title), "_doi": _doi(row.get("doi") or row.get("DOI")),
            "_authors": _names(row.get("authors") or row.get("author") or row.get("creators")),
            "_year": _year(row),
            "_version_group": _text(row.get("version_group") or row.get("work_family")
                                     or row.get("canonical_work_id")),
        })
        out.append(local)
    return sorted(out, key=lambda r: (r["_source"], r["_rid"], r["_observation"]))


class _Sets:
    def __init__(self, rows):
        self.parent = {r["_observation"]: r["_observation"] for r in rows}

    def find(self, key):
        while self.parent[key] != key:
            self.parent[key] = self.parent[self.parent[key]]
            key = self.parent[key]
        return key

    def union(self, a, b):
        a, b = self.find(a), self.find(b)
        if a == b:
            return a
        a, b = sorted((a, b))
        self.parent[b] = a
        return a


def _compatible(a, b, explicit_version=False):
    if a["_doi"] and b["_doi"] and a["_doi"] != b["_doi"] and not explicit_version:
        return False
    if a["_year"] and b["_year"] and abs(a["_year"] - b["_year"]) > 1:
        return False
    return True


def _identity(rows):
    """Exact identifiers first, then conservative Zotero-style fuzzy matching."""
    sets = _Sets(rows)
    evidence = []
    by_doi, by_version = {}, {}
    for row in rows:
        if row["_doi"]:
            by_doi.setdefault(row["_doi"], []).append(row)
        if row["_version_group"]:
            by_version.setdefault(row["_version_group"], []).append(row)
    for doi, group in sorted(by_doi.items()):
        for other in group[1:]:
            sets.union(group[0]["_observation"], other["_observation"])
            evidence.append({"left": group[0]["_observation"], "right": other["_observation"],
                             "rule": "doi_exact", "evidence": doi, "merged": True})
    for group_id, group in sorted(by_version.items()):
        for other in group[1:]:
            sets.union(group[0]["_observation"], other["_observation"])
            evidence.append({"left": group[0]["_observation"], "right": other["_observation"],
                             "rule": "declared_version_group", "evidence": group_id,
                             "merged": True})
    # Rebuild groups after strong links, and veto fuzzy bridges between different DOIs.
    for i, a in enumerate(rows):
        for b in rows[i + 1:]:
            if sets.find(a["_observation"]) == sets.find(b["_observation"]):
                continue
            shared_version = bool(a["_version_group"] and
                                  a["_version_group"] == b["_version_group"])
            if not _compatible(a, b, shared_version):
                continue
            if not a["_title_key"] or not b["_title_key"]:
                continue
            ratio = SequenceMatcher(None, a["_title_key"], b["_title_key"]).ratio()
            creator_overlap = bool(_surname_initial(a["_authors"]) &
                                   _surname_initial(b["_authors"]))
            creator_free = not a["_authors"] and not b["_authors"]
            exact = a["_title_key"] == b["_title_key"]
            # Different declared DOIs are allowed only through an explicit version group.
            if (exact and (creator_overlap or creator_free or shared_version)) or \
                    (ratio >= 0.94 and creator_overlap):
                group_a = [r for r in rows if sets.find(r["_observation"]) == sets.find(a["_observation"])]
                group_b = [r for r in rows if sets.find(r["_observation"]) == sets.find(b["_observation"])]
                if not shared_version and any(x["_doi"] and y["_doi"] and x["_doi"] != y["_doi"]
                                              for x in group_a for y in group_b):
                    continue
                sets.union(a["_observation"], b["_observation"])
                evidence.append({"left": a["_observation"], "right": b["_observation"],
                                 "rule": "title_exact_author" if exact else "title_fuzzy_author",
                                 "title_similarity": round(ratio, 6),
                                 "shared_creators": sorted(_surname_initial(a["_authors"]) &
                                                           _surname_initial(b["_authors"])),
                                 "year_gap": abs((a["_year"] or 0) - (b["_year"] or 0))
                                 if a["_year"] and b["_year"] else None,
                                 "merged": True})
    groups = {}
    for row in rows:
        groups.setdefault(sets.find(row["_observation"]), []).append(row)
    canonical, aliases = {}, {}
    for root, members in groups.items():
        members.sort(key=lambda r: (r["_doi"].startswith("10.48550/"), not bool(r["_doi"]),
                                    r["_source"], r["_rid"], r["_observation"]))
        rep = members[0]
        digest = hashlib.sha256("\n".join(sorted(m["_observation"] for m in members)).encode()).hexdigest()[:12]
        work_id = rep["_doi"] or rep["_rid"]
        if work_id.startswith("W") or work_id.startswith("10."):
            work_id = work_id
        conflicts = []
        for field in ("_title", "_year"):
            vals = sorted({str(m[field]) for m in members if m[field] not in (None, "")})
            if len(vals) > 1:
                conflicts.append({"field": field.lstrip("_"), "values": vals,
                                  "retained": True, "resolution": "primary record only for display"})
        canonical[root] = {
            "work_id": work_id, "cluster_id": "work-" + digest,
            "title": rep["_title"] or None, "doi": rep["_doi"] or None,
            "authors": rep["_authors"], "year": rep["_year"],
            "version_records": [{"observation_id": m["_observation"], "source": m["_source"],
                                 "record_id": m["_rid"], "doi": m["_doi"] or None,
                                 "title": m["_title"] or None, "year": m["_year"],
                                 "version": m.get("version")} for m in members],
            "conflicting_metadata": conflicts,
        }
        for member in members:
            for alias in (member["_rid"], member["_doi"], member["cluster_doi"] if "cluster_doi" in member else ""):
                if alias:
                    aliases.setdefault(alias, set()).add(root)
            if member["_title_key"]:
                aliases.setdefault("title:" + member["_title_key"], set()).add(root)
    return canonical, aliases, evidence, groups


def _target_identifiers(value):
    if isinstance(value, dict):
        return [_text(value.get(k)) for k in ("id", "work_id", "paperId", "doi", "DOI")
                if _text(value.get(k))]
    value = _text(value)
    return [value] if value else []


def _raw_edges(spec, rows):
    edges = []
    for index, edge in enumerate(_list(spec.get("edges") or spec.get("citation_edges"))):
        if not isinstance(edge, dict):
            continue
        citing = _text(edge.get("citing_id") or edge.get("citing") or edge.get("from")
                       or edge.get("source_id"))
        cited = _text(edge.get("cited_id") or edge.get("cited") or edge.get("to")
                      or edge.get("target_id"))
        if citing and cited:
            item = dict(edge)
            item.update({"_citing": citing, "_cited": cited,
                         "_source": _text(edge.get("source") or edge.get("database") or "snapshot"),
                         "_ordinal": "edge-%06d" % index})
            edges.append(item)
    for row in rows:
        references = row.get("references") or row.get("referenced_works") or row.get("refs")
        for index, target in enumerate(_list(references)):
            for cited in _target_identifiers(target):
                edges.append({"_citing": row["_rid"], "_cited": cited,
                              "_source": row["_source"], "_ordinal": row["_observation"] + "-ref-%04d" % index,
                              "source_record_id": row["_rid"],
                              "context": target.get("context") if isinstance(target, dict) else None})
        for index, citing_row in enumerate(_list(row.get("citations") or row.get("cited_by"))):
            for citing in _target_identifiers(citing_row):
                edges.append({"_citing": citing, "_cited": row["_rid"],
                              "_source": row["_source"], "_ordinal": row["_observation"] + "-cite-%04d" % index,
                              "source_record_id": row["_rid"],
                              "context": citing_row.get("context") if isinstance(citing_row, dict) else None})
        text = _text(row.get("text"))
        for index, match in enumerate(re.finditer(r"(?im)^\s*(?:cites|refs):\s*([^\n]+)", text)):
            for cited in re.split(r"[,;\s]+", match.group(1).strip()):
                if cited and cited.lower() != "none":
                    edges.append({"_citing": row["_rid"], "_cited": cited,
                                  "_source": row["_source"], "_ordinal": row["_observation"] + "-text-%04d" % index,
                                  "context": match.group(0)})
    return edges


def _resolve(identifier, aliases, canonical):
    identifier = _text(identifier)
    candidates = set()
    for key in (identifier, _doi(identifier), "title:" + _title(identifier)):
        candidates |= aliases.get(key, set())
    if len(candidates) == 1:
        root = next(iter(candidates))
        return root, canonical[root]["work_id"], False
    if len(candidates) > 1:
        return None, None, True
    # Unknown endpoints remain nodes with missing metadata rather than disappearing.
    return "external:" + identifier, identifier, False


def run(spec):
    rows = _normalise_records(_records(spec))
    canonical, aliases, merge_evidence, groups = _identity(rows)
    ambiguous, skipped = [], []
    clean_edges, edge_seen = [], set()
    for raw in _raw_edges(spec, rows):
        cr, citing, amb1 = _resolve(raw["_citing"], aliases, canonical)
        cd, cited, amb2 = _resolve(raw["_cited"], aliases, canonical)
        if amb1 or amb2:
            ambiguous.append({"citing": raw["_citing"], "cited": raw["_cited"],
                              "reason": "identifier maps to multiple identity clusters"})
            continue
        if cr is None or cd is None or citing == cited:
            continue
        for root, work_id in ((cr, citing), (cd, cited)):
            if root not in canonical:
                canonical[root] = {"work_id": work_id, "cluster_id": "external-" + hashlib.sha256(
                    work_id.encode()).hexdigest()[:12], "title": None, "doi": _doi(work_id) or None,
                    "authors": [], "year": None, "version_records": [],
                    "conflicting_metadata": [{"field": "metadata", "values": [], "retained": True,
                                               "resolution": "edge-only endpoint; metadata missing"}]}
        key = (citing, cited, raw["_source"], _text(raw.get("context")), _text(raw.get("source_record_id")))
        if key in edge_seen:
            skipped.append({"citing_id": citing, "cited_id": cited, "source": raw["_source"],
                            "reason": "identical edge duplicate"})
            continue
        edge_seen.add(key)
        edge_id = "edge-" + hashlib.sha256("\0".join(key).encode()).hexdigest()[:16]
        clean_edges.append({
            "edge_id": edge_id, "citing_id": citing, "cited_id": cited,
            "direction": "citing_to_cited", "source": raw["_source"],
            "source_record_id": raw.get("source_record_id"),
            "query": raw.get("query"), "citation_context": raw.get("context")
            or raw.get("citation_context"), "context_locator": raw.get("context_locator")
            or raw.get("locator"), "intention": raw.get("intention"),
            "evidence_complete": bool(raw.get("context") or raw.get("citation_context")
                                      or raw.get("source_record_id") or raw.get("locator")),
        })
    clean_edges.sort(key=lambda e: (e["citing_id"], e["cited_id"], e["source"], e["edge_id"]))
    raw_seed = spec.get("seed_id") or spec.get("seed") or spec.get("root_id")
    if isinstance(raw_seed, dict):
        raw_seed = raw_seed.get("id") or raw_seed.get("doi") or raw_seed.get("title")
    # Lists/objects are malformed identifiers, not seed strings to search automatically.
    seed = _text(raw_seed) if isinstance(raw_seed, (str, int)) and not isinstance(raw_seed, bool) else ""
    if not seed and len(canonical) == 1:
        seed = next(iter(canonical.values()))["work_id"]
    seed_root, seed, ambiguous_seed = _resolve(seed, aliases, canonical) if seed else (None, "", False)
    if not seed or ambiguous_seed or seed_root is None:
        return {"schema_version": SCHEMA_VERSION, "status": "undetermined",
                "refusal": {"rule": "citation.seed_unresolved",
                            "message": "seed_id is missing, ambiguous, or not a scalar identifier"},
                "limits": ["no citation traversal was performed"], "findings": []}
    if seed_root not in canonical:
        canonical[seed_root] = {"work_id": seed, "cluster_id": "external-" + hashlib.sha256(
            seed.encode()).hexdigest()[:12], "title": None, "doi": _doi(seed) or None,
            "authors": [], "year": None, "version_records": [], "conflicting_metadata": []}
    outgoing, incoming = {}, {}
    for edge in clean_edges:
        outgoing.setdefault(edge["citing_id"], []).append(edge)
        incoming.setdefault(edge["cited_id"], []).append(edge)
    depth = spec.get("max_depth", spec.get("depth", 2))
    try:
        depth = max(0, min(int(depth), 8))
    except (TypeError, ValueError):
        depth = 2
    direction = _text(spec.get("direction") or "both").lower()
    if direction not in ("forward", "backward", "both"):
        direction = "both"
    max_nodes = spec.get("max_nodes", 200)
    try:
        max_nodes = max(1, min(int(max_nodes), 2000))
    except (TypeError, ValueError):
        max_nodes = 200
    distances = {seed: 0}
    parents = {seed: []}
    queue = deque([seed])
    stopped_by_budget = False
    while queue:
        current = queue.popleft()
        if distances[current] >= depth:
            continue
        neighbours = []
        if direction in ("backward", "both"):
            neighbours += [(edge["cited_id"], "backward", edge) for edge in outgoing.get(current, [])]
        if direction in ("forward", "both"):
            neighbours += [(edge["citing_id"], "forward", edge) for edge in incoming.get(current, [])]
        neighbours.sort(key=lambda n: (n[0], n[1], n[2]["source"], n[2]["edge_id"]))
        for neighbour, travel, edge in neighbours:
            if neighbour == seed:
                continue
            new_distance = distances[current] + 1
            candidate_path = parents[current] + [{
                "from_id": current, "to_id": neighbour, "traversal_direction": travel,
                "edge_id": edge["edge_id"], "citing_id": edge["citing_id"],
                "cited_id": edge["cited_id"], "source": edge["source"],
                "citation_context": edge["citation_context"]}]
            if neighbour not in distances or new_distance < distances[neighbour]:
                if neighbour not in distances and len(distances) - 1 >= max_nodes:
                    stopped_by_budget = True
                    continue
                distances[neighbour] = new_distance
                parents[neighbour] = candidate_path
                queue.append(neighbour)
    def node(work_id):
        root = next((r for r, w in canonical.items() if w["work_id"] == work_id), None)
        return canonical.get(root, {"work_id": work_id, "title": None, "doi": _doi(work_id) or None,
                                    "authors": [], "year": None, "version_records": [],
                                    "conflicting_metadata": []})
    candidates = []
    for work_id in sorted(distances, key=lambda w: (distances[w], w)):
        if work_id == seed:
            continue
        path = parents[work_id]
        sources = sorted({hop["source"] for hop in path})
        candidate = dict(node(work_id))
        candidate.update({
            "depth": distances[work_id], "relation": "direct" if distances[work_id] == 1 else "indirect",
            "discovery_directions": sorted({hop["traversal_direction"] for hop in path}),
            "shortest_path": path, "evidence_sources": sources,
            "reason": "reachable from the seed by " + str(distances[work_id]) +
                      " source-recorded citation edge(s); every hop is listed",
        })
        candidates.append(candidate)
    # Co-citation: a later work cites both the seed and another work.
    co_citation = []
    for later in sorted(incoming.get(seed, []), key=lambda e: e["citing_id"]):
        citing_work = later["citing_id"]
        for edge in sorted(outgoing.get(citing_work, []), key=lambda e: e["cited_id"]):
            other = edge["cited_id"]
            if other == seed:
                continue
            co_citation.append({"work_id": other, "association": "co_citation",
                                "shared_citing_works": [citing_work],
                                "shared_edge_ids": sorted([later["edge_id"], edge["edge_id"]]),
                                "reason": citing_work + " cites both the seed and this work"})
    # Bibliographic coupling: seed and candidate share one or more references.
    seed_refs = {e["cited_id"] for e in outgoing.get(seed, [])}
    coupling = []
    for citing in sorted(outgoing):
        if citing == seed:
            continue
        shared = sorted(seed_refs & {e["cited_id"] for e in outgoing[citing]})
        if shared:
            coupling.append({"work_id": citing, "association": "bibliographic_coupling",
                             "shared_references": shared,
                             "shared_edge_ids": sorted(e["edge_id"] for e in outgoing[citing]
                                                       if e["cited_id"] in shared),
                             "reason": "shares " + str(len(shared)) + " recorded reference(s) with the seed"})
    associations = {}
    for item in co_citation + coupling:
        old = associations.get(item["work_id"])
        if old is None:
            associations[item["work_id"]] = item
        else:
            old["association"] = "co_citation+bibliographic_coupling"
            old["reason"] += "; " + item["reason"]
            for key in ("shared_citing_works", "shared_references", "shared_edge_ids"):
                if key in item:
                    old[key] = sorted(set(old.get(key, [])) | set(item[key]))
    related = []
    for work_id, association in sorted(associations.items()):
        related.append(dict(association, depth=distances.get(work_id),
                            direct_citation_path_available=work_id in distances))
    # Structural labels use only the retained, seed-centred graph.
    years = [w.get("year") for w in candidates if w.get("year")]
    recent_cutoff = max(years) - 2 if years else None
    network_nodes = []
    for work_id in [seed] + sorted(set(distances) - {seed}):
        back = len(outgoing.get(work_id, []))
        forward = len(incoming.get(work_id, []))
        roles = ["seed"] if work_id == seed else []
        if work_id != seed:
            if back >= 2 and forward:
                roles.append("bridge")
            if forward >= 2 and distances.get(work_id, 0):
                roles.append("foundational_in_snapshot")
            if recent_cutoff is not None and (node(work_id).get("year") or -9999) >= recent_cutoff:
                roles.append("recent")
            if not roles:
                roles.append("peripheral")
        network_nodes.append({"work_id": work_id, "roles": roles,
                              "backward_edges": back, "forward_edges": forward,
                              "depth": distances.get(work_id, 0)})
    source_status = spec.get("source_status") or {}
    limits = []
    findings = []
    if stopped_by_budget:
        limits.append("max_nodes budget stopped expansion; not a complete citation neighbourhood")
        findings.append({"rule": "citation.budget_stopped", "severity": "medium"})
    if ambiguous or ambiguous_seed:
        findings.append({"rule": "citation.identity_ambiguous", "severity": "high",
                         "entries": ambiguous})
        limits.append("ambiguous identifiers were excluded pending arbitration")
    missing_context = [e["edge_id"] for e in clean_edges if not e["citation_context"]]
    if missing_context:
        findings.append({"rule": "citation.context_missing", "severity": "low",
                         "count": len(missing_context), "entries": missing_context})
    if skipped:
        findings.append({"rule": "citation.edge_deduplicated", "severity": "low",
                         "count": len(skipped), "entries": skipped})
    for source, payload in sorted(source_status.items()):
        if not isinstance(payload, dict) or payload.get("status") not in (None, "ok", "success"):
            limits.append("source " + source + " was incomplete; citation absence is only absence in this snapshot")
    snapshot = {"records": rows, "edges": clean_edges, "seed": seed,
                "depth": depth, "direction": direction}
    fingerprint = hashlib.sha256(json.dumps(snapshot, sort_keys=True, ensure_ascii=False,
                                                   default=str).encode()).hexdigest()
    status = "review" if limits or any(f["severity"] == "high" for f in findings) else "clean"
    return {
        "schema_version": SCHEMA_VERSION, "status": status, "ok": True,
        "seed": dict(node(seed), requested_seed=seed, expansion_depth=depth,
                     traversal_direction=direction),
        "candidates": candidates, "candidate_count": len(candidates),
        "citation_edges": clean_edges, "edge_count": len(clean_edges),
        "paths": [{"work_id": c["work_id"], "depth": c["depth"],
                   "shortest_path": c["shortest_path"], "relation": c["relation"]}
                  for c in candidates],
        "associations": related, "association_count": len(related),
        "identity_merges": merge_evidence, "duplicate_edges": skipped,
        "network_summary": {"nodes": network_nodes,
                            "roles": {role: sorted(n["work_id"] for n in network_nodes if role in n["roles"])
                                      for role in ("bridge", "foundational_in_snapshot", "recent", "peripheral")},
                            "stop_reason": "max_nodes" if stopped_by_budget else "max_depth_or_exhausted"},
        "coverage": {"works_considered": len(canonical), "nodes_discovered": len(candidates),
                     "max_nodes": max_nodes, "source_status": source_status,
                     "missing_context_edges": len(missing_context)},
        "source_status": source_status,
        "sources": sorted({e["source"] for e in clean_edges}),
        "evidence_records": [{"edge_id": e["edge_id"], "source": e["source"],
                              "source_record_id": e["source_record_id"],
                              "context_locator": e["context_locator"]} for e in clean_edges],
        "findings": findings, "limits": limits,
        "uncertainty": "Only retained snapshot edges are traversed. Empty expansion does not prove zero citations; related signals are not direct citation claims.",
        "change_log": [{"action": "identity_alignment", "groups": len(groups)},
                       {"action": "graph_expansion", "depth": depth, "direction": direction},
                       {"action": "related_work_discovery", "associations": len(related)}],
        "snapshot_sha256": fingerprint,
    }


def is_citation_spec(spec):
    return isinstance(spec, dict) and (spec.get("mode") == "citation" or
        any(k in spec for k in ("seed_id", "citation_edges", "citation_works", "max_depth")))
