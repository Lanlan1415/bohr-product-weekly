"""Directed, evidence-bound graph validation and conservative assertion merging.

The schema/pattern concept follows neo4j-graphrag's SimpleKGPipeline, but this module
adds stricter evidence locator, confidence, conflict and merge-ledger requirements.
It never infers entity identity from a common material or method name alone.
"""
from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path
import unicodedata

import kg_sources


EDGE_COLUMNS = ["edge_id", "subject", "predicate", "object", "source_id", "paragraph_id", "quote"]
NODE_COLUMNS = ["node_id", "label", "type", "aliases"]
COMPARATIVES = {"outperforms", "more_stable_than", "compares", "contradicts", "reports_value"}


def norm(value):
    if isinstance(value, (dict, list, tuple)):
        value = json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)
    text = " ".join(unicodedata.normalize("NFKC", str(value or "")).split()).casefold()
    return text.replace("‐", "-").replace("‑", "-").replace("–", "-").replace("—", "-").replace("−", "-")


def load_schema(path=None):
    if path is None:
        path = Path(__file__).resolve().parent.parent / "references" / "graph_schema.json"
    schema = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    if not isinstance(schema, dict) or not isinstance(schema.get("directed_relations"), dict):
        raise ValueError("graph schema is missing directed_relations")
    return schema


def read_csv(path, fields=None):
    with Path(path).open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        missing = [x for x in fields or [] if x not in (reader.fieldnames or [])]
        if missing:
            raise ValueError("missing CSV columns " + ",".join(missing))
        return [dict(row, _line=i) for i, row in enumerate(reader, start=2)]


def evidence_of(edge):
    ev = edge.get("evidence") if isinstance(edge.get("evidence"), list) else []
    if ev:
        return [e for e in ev if isinstance(e, dict)]
    # One source per row is a faithful, explicit representation.  A second format of the
    # same paper retains its same source_id rather than masquerading as independent evidence.
    raw = {key: edge.get(key) for key in (
        "source_id", "paragraph_id", "quote", "evidence_strength", "confidence", "locator",
        "source_file", "page", "section_title")}
    return [{k: v for k, v in raw.items() if v not in (None, "")}]


def _numbers(value):
    try:
        f = float(value)
        if f < 0 or f > 1 or f != f or f in (float("inf"), -float("inf")):
            raise ValueError
        return f
    except (TypeError, ValueError) as exc:
        raise ValueError("confidence must be a finite number in [0,1]") from exc


def _instance_identity_overlap(nodes, schema):
    """Each instance pair must share a specific author/source identifier, not just a name."""
    if len(nodes) < 2:
        return False
    pairs = []
    for a in nodes[1:]:
        found = False
        for b in nodes[:1]:
            ids_a = a.get("identifiers") if isinstance(a.get("identifiers"), dict) else {}
            ids_b = b.get("identifiers") if isinstance(b.get("identifiers"), dict) else {}
            common = sorted(k for k in set(ids_a) & set(ids_b)
                            if str(ids_a[k]).strip() and norm(ids_a[k]) == norm(ids_b[k]))
            if common:
                found = True
                pairs.extend(common)
        if not found:
            return False
    return True


def merge_ledger(decisions, nodes, schema, quote_validator=None):
    """Classify duplicate candidates rather than silently merging or flagging legitimately split samples.

    Decision: {node_ids, action: merge|keep_separate, justification, identifiers_shared,
    evidence:[{source_id,paragraph_id,quote}]}.  An absent decision is unresolved; for
    instances this is a hard error.  Keep-separate decisions are preserved in the report,
    so a deliberate duplicate label is different from accidental low-quality duplication.
    """
    grouped = {}
    for node in nodes:
        if not isinstance(node, dict):
            continue
        for key in [norm(node.get("label"))] + [norm(x) for x in (node.get("aliases") or []) if not isinstance(x, dict)]:
            if key:
                grouped.setdefault((str(node.get("type") or ""), key), set()).add(str(node.get("node_id") or ""))
    candidates = {k: sorted(v) for k, v in grouped.items() if len(v) > 1}
    by_id = {str(n.get("node_id")): n for n in nodes if isinstance(n, dict)}
    decisions = decisions if isinstance(decisions, list) else []
    ledger = []
    unresolved = []
    errors = []
    seen_pairs = set()
    for i, d in enumerate(decisions):
        if not isinstance(d, dict):
            errors.append("merge decision %d is not an object" % i)
            continue
        ids = [str(x) for x in d.get("node_ids") or []]
        action = d.get("action") or d.get("decision")
        evidence = d.get("evidence") if isinstance(d.get("evidence"), list) else []
        valid_evidence = []
        for ev in evidence:
            if not isinstance(ev, dict):
                continue
            check = quote_validator(ev) if quote_validator else True
            if check:
                valid_evidence.append(ev)
        entry = {"node_ids": ids, "action": action, "justification": d.get("justification") or d.get("reason"),
                 "evidence_count": len(valid_evidence), "identifiers_shared": d.get("identifiers_shared") or []}
        good_shape = len(ids) >= 2 and len(set(ids)) == len(ids) and all(x in by_id for x in ids)
        if not good_shape:
            errors.append("merge decision %d has missing/unknown/duplicate nodes" % i)
        elif action not in ("merge", "keep_separate"):
            errors.append("merge decision %d must choose merge or keep_separate" % i)
        elif len({str(by_id[x].get("type")) for x in ids}) != 1:
            errors.append("merge decision %d mixes entity types" % i)
        elif not str(entry["justification"] or "").strip() or not valid_evidence:
            errors.append("merge decision %d needs a justification and source-attached verbatim evidence" % i)
        else:
            entity_type = str(by_id[ids[0]].get("type"))
            can_keep_separate = action == "keep_separate" and entry["evidence_count"] >= 1
            if entity_type in schema.get("instance_types", []) and not can_keep_separate:
                shared = entry["identifiers_shared"]
                overlap = _instance_identity_overlap([by_id[x] for x in ids], schema)
                if not shared or not overlap:
                    errors.append("instance merge review %d has no matching author/source identifiers" % i)
                elif action == "merge" and len({str(ev.get("source_id")) for ev in valid_evidence}) > 1:
                    # A shared identifier remains the guard even across papers; this branch
                    # explicitly records why cross-paper identity is exceptionally accepted.
                    entry["cross_source_identity"] = True
            if action == "keep_separate" and entry["evidence_count"] < 1:
                errors.append("keep_separate %d has no independently checkable evidence" % i)
            else:
                for part in ids:
                    seen_pairs.add((str(by_id[part].get("type")), part))
        ledger.append(entry)
    for (etype, _), ids in candidates.items():
        covered = sum(1 for x in ledger if all(i in x["node_ids"] for i in ids[:2]))
        if not covered:
            unresolved.append({"type": etype, "node_ids": ids})
            if etype in schema.get("instance_types", []):
                errors.append("same-name instance candidates %s have no explicit keep_separate/shared-identifier decision" % ids)
            else:
                errors.append("possible duplicate entities %s need a source-backed merge/keep_separate decision" % ids)
    return {"errors": errors, "decisions": ledger, "unresolved": unresolved}


def validate_graph(graph, schema, sources=None, decisions=None):
    nodes = graph.get("nodes") if isinstance(graph, dict) else []
    edges = graph.get("edges") if isinstance(graph, dict) else []
    nodes = nodes if isinstance(nodes, list) else []
    edges = edges if isinstance(edges, list) else []
    errors, warnings = [], []
    ids, node_records = set(), {}
    for i, node in enumerate(nodes):
        if not isinstance(node, dict):
            errors.append("node %d is not an object" % i); continue
        nid = str(node.get("node_id") or "").strip()
        typ = str(node.get("type") or "").strip()
        label = str(node.get("label") or "").strip()
        if not nid or not label:
            errors.append("node %d lacks node_id/label" % i)
        if nid in ids:
            errors.append("duplicate node_id %s" % nid)
        ids.add(nid); node_records[nid] = node
        if typ not in schema.get("node_types", []):
            errors.append("node %s has undeclared type %s" % (nid, typ))
        if not (node.get("evidence") or []) and node.get("substantive", True) is not False:
            errors.append("node %s has no source_id/paragraph_id/verbatim evidence" % nid)
        for ev in (node.get("evidence") or []):
            if not isinstance(ev, dict):
                continue
            ok, reason = kg_sources.check_evidence(ev, sources, schema)
            if not ok:
                errors.append("node %s evidence invalid: %s" % (nid, reason))
    ids.discard("")
    edge_ids, seen = set(), {}
    all_conflicts, all_merged = [], []
    for i, edge in enumerate(edges):
        if not isinstance(edge, dict):
            errors.append("edge %d is not an object" % i); continue
        eid = str(edge.get("edge_id") or "edge-%d" % (i + 1))
        if eid in edge_ids:
            errors.append("duplicate edge_id %s" % eid)
        edge_ids.add(eid)
        s, p, o = str(edge.get("subject") or ""), str(edge.get("predicate") or ""), str(edge.get("object") or "")
        if s not in node_records or o not in node_records:
            errors.append("edge %s has a dangling endpoint" % eid)
        relation = schema["directed_relations"].get(p)
        if relation is None:
            errors.append("edge %s uses predicate outside schema: %s" % (eid, p))
        else:
            if s in node_records and node_records[s].get("type") not in relation.get("subject_types", []):
                errors.append("edge %s direction/type error: %s(%s) -%s-> object has an invalid subject type" % (eid, s, node_records[s].get("type"), p))
            if o in node_records and node_records[o].get("type") not in relation.get("object_types", []):
                errors.append("edge %s direction/type error: invalid object type %s for %s" % (eid, node_records[o].get("type"), p))
            condition = edge.get("condition") if isinstance(edge.get("condition"), dict) else ({"text": edge.get("condition")} if str(edge.get("condition") or "").strip() else None)
            if (relation.get("condition_required") or p in COMPARATIVES) and not condition:
                errors.append("edge %s is comparative/qualified but has no condition" % eid)
            if condition and not (condition.get("text") or condition.get("id") or condition.get("locator")):
                errors.append("edge %s has an empty condition object" % eid)
        evidences = evidence_of(edge)
        if not evidences:
            errors.append("edge %s has no source evidence" % eid)
        for ev in evidences:
            ok, reason = kg_sources.check_evidence(ev, sources, schema)
            if not ok:
                errors.append("edge %s evidence invalid: %s" % (eid, reason))
            if "confidence" not in ev:
                errors.append("edge %s lacks reader confidence for evidence" % eid)
            else:
                try:
                    _numbers(ev["confidence"])
                except ValueError as exc:
                    errors.append("edge %s: %s" % (eid, str(exc)))
            strength = str(ev.get("evidence_strength") or "").strip()
            if strength not in schema.get("evidence_strength", []):
                errors.append("edge %s has unsupported evidence_strength %s" % (eid, strength))
        key = (s, p, o, norm(edge.get("condition")), norm(edge.get("value")), norm(edge.get("unit")))
        if key in seen:
            # This validator catches accidental duplicate IDs in hand-authored input.  The
            # builder instead consolidates all evidence before validation, allowing distinct
            # source assertions to survive and conflicts to be labelled rather than erased.
            errors.append("duplicate assertion %s must be merged with an evidence list" % (eid,))
            all_merged.append({"existing": seen[key], "duplicate": eid})
            a = by_assertion_values(seen[key], edges)
            if a[0] != edge.get("value") or a[1] != edge.get("unit"):
                all_conflicts.append({"subject": s, "predicate": p, "object": o,
                                      "condition": edge.get("condition"), "edge_ids": [seen[key], eid],
                                      "disposition": "preserve both; no averaging"})
        else:
            seen[key] = eid
    merge = merge_ledger(decisions if decisions is not None else graph.get("merge_decisions"), nodes, schema,
                         lambda ev: kg_sources.check_evidence(ev, sources, schema)[0])
    errors.extend(merge["errors"])
    return {"ok": not errors, "schema_version": schema.get("schema_version"),
            "errors": errors, "warnings": warnings, "node_count": len(nodes), "edge_count": len(edges),
            "entity_candidates_checked": len(merge["decisions"]) + len(merge["unresolved"]),
            "merge_decisions": merge["decisions"], "unresolved_entity_candidates": merge["unresolved"],
            "duplicates": all_merged, "conflicts": all_conflicts,
            "quote_validation": kg_sources.registry_status(sources)}


def by_assertion_values(edge_id, edges):
    for edge in edges:
        if isinstance(edge, dict) and str(edge.get("edge_id")) == str(edge_id):
            return edge.get("value"), edge.get("unit")
    return None, None


def consolidate(edges):
    """Merge only identical qualified assertions; never discard source/conflict distinctions.

    Identical s/p/o/condition+value+unit records receive an ordered evidence list and the
    minimum supplied extraction confidence.  Distinct values become unresolved conflicts:
    both remain in the graph and no one is overwritten or averaged.
    """
    grouped = {}
    for index, original in enumerate(edges):
        if not isinstance(original, dict):
            continue
        edge = dict(original)
        key = (edge.get("subject"), edge.get("predicate"), edge.get("object"),
               norm(edge.get("condition")), edge.get("value"), edge.get("unit"))
        evidences = evidence_of(edge)
        grouped.setdefault(str(key), {"edge": edge, "evidence": [], "ids": [], "confidence": []})
        cell = grouped[str(key)]
        cell["evidence"].extend(evidences)
        cell["ids"].append(str(edge.get("edge_id") or "edge-%d" % (index + 1)))
        for ev in evidences:
            try:
                cell["confidence"].append(_numbers(ev.get("confidence")))
            except ValueError:
                pass
    groups = {}
    conflicts = []
    for cell in grouped.values():
        edge = cell["edge"]
        semantic = (edge.get("subject"), edge.get("predicate"), edge.get("object"))
        groups.setdefault(semantic, []).append(cell)
    for semantic, cells in groups.items():
        for cell in cells:
            edge = cell["edge"]
            qual = norm(edge.get("condition"))
            same_qual = [c for c in cells if norm(c["edge"].get("condition")) == qual]
            # Same s/p/o under different conditions are independent qualified findings,
            # not a conflict.  Only divergent values under the same qualifier conflict.
            qualified_values = {(c["edge"].get("value"), c["edge"].get("unit")) for c in same_qual}
            if len(qualified_values) > 1:
                edge["status"] = "conflict"
                if not any(c["edge_ids"] == cell["ids"] for c in conflicts):
                    conflicts.append({"subject": semantic[0], "predicate": semantic[1], "object": semantic[2],
                                      "condition": edge.get("condition"), "edge_ids": cell["ids"],
                                      "value": edge.get("value"), "unit": edge.get("unit"),
                                      "disposition": "retained independently; not merged numerically/averaged"})
            else:
                edge["status"] = "accepted"
            edge["evidence"] = cell["evidence"]
            if cell["confidence"]:
                edge["confidence"] = min(cell["confidence"])
            edge["supporting_edge_ids"] = cell["ids"]
    return [c["edge"] for c in grouped.values()], conflicts
