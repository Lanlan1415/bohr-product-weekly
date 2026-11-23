"""Deterministic multi-database query planning, identity merging and provenance.

The module consumes retained source exports.  It never calls a remote service and
never claims that a generated query was executed.  All records and conflicting
values retain their source lineage.
"""
from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from difflib import SequenceMatcher

SCHEMA_VERSION = "multi-db-search/v2"
OPENALEX_TITLE_FIELD = "title.search"
DEFAULT_PRIORITY = ["publisher", "crossref", "europepmc", "openalex", "semantic_scholar", "arxiv"]


def _text(value):
    return str(value).strip() if value is not None else ""


def _list(value):
    if value is None:
        return []
    return value if isinstance(value, list) else [value]


def _doi(value):
    value = _text(value).lower()
    value = re.sub(r"^(?:https?://(?:dx\.)?doi\.org/|doi:\s*)", "", value)
    return value.rstrip(" .;")


def _title(value):
    value = unicodedata.normalize("NFKD", _text(value))
    value = "".join(c for c in value if not unicodedata.combining(c))
    return " ".join(re.findall(r"[\w]+", value.lower(), flags=re.UNICODE))


def _names(value):
    names = []
    for item in _list(value):
        if isinstance(item, dict):
            name = item.get("name") or item.get("display_name")
            if not name:
                family = _text(item.get("family") or item.get("lastName"))
                given = _text(item.get("given") or item.get("firstName"))
                name = (given + " " + family).strip() if given and family else (family or given)
            if not name and item.get("author"):
                return _names(item["author"])
        else:
            name = item
        if _text(name):
            names.append(_text(name))
    return names


def _author_keys(names):
    keys = set()
    for name in names:
        normal = _title(name)
        parts = normal.split()
        if not parts:
            continue
        if "," in name:
            last = _title(name.split(",", 1)[0]).replace(" ", "")
            rest = _title(name.split(",", 1)[1]).split()
            initial = rest[0][0] if rest else ""
        elif len(parts) == 1:
            last, initial = parts[0], ""
        else:
            last, initial = parts[-1], parts[0][0]
        keys.add((last, initial))
    return keys


def _year(record):
    for key in ("year", "publication_year", "pubYear"):
        if str(record.get(key) or "").isdigit():
            return int(record[key])
    for key in ("issued", "published-online", "published-print", "published", "firstPublicationDate",
                "firstIndexDate", "date"):
        value = record.get(key)
        if isinstance(value, dict):
            value = value.get("date-time") or value.get("date-parts")
        match = re.search(r"(?:19|20)\d{2}", _text(value))
        if match:
            return int(match.group())
    return None


def _source_rows(spec):
    """Yield (source, payload, raw record), retaining malformed row counts."""
    sources = spec.get("sources")
    rows = []
    if isinstance(sources, dict):
        for source, payload in sources.items():
            payload = payload if isinstance(payload, dict) else {"status": "error", "records": []}
            for index, raw in enumerate(_list(payload.get("records") or payload.get("results"))):
                rows.append((_text(source), payload, raw, index))
    else:
        records = spec.get("records") or spec.get("documents") or []
        for index, raw in enumerate(_list(records)):
            source = _text(raw.get("source") or raw.get("database")) if isinstance(raw, dict) else "unknown"
            rows.append((source or "unknown", {}, raw, index))
    return rows


def _normalise(source, raw, index):
    if not isinstance(raw, dict):
        return None, {"source": source, "index": index,
                      "reason": "record is not an object", "raw_type": type(raw).__name__}
    external = raw.get("externalIds") if isinstance(raw.get("externalIds"), dict) else {}
    identifiers = raw.get("identifiers") if isinstance(raw.get("identifiers"), dict) else {}
    rid = _text(raw.get("id") or raw.get("record_id") or raw.get("paperId") or raw.get("pmid")
                or raw.get("DOI") or raw.get("doi") or raw.get("title"))
    title = _text(raw.get("title") or raw.get("display_name") or raw.get("articleTitle"))
    if not rid and title:
        rid = "title:" + _title(title)
    if not rid and not title:
        return None, {"source": source, "index": index, "reason": "record has no id or title"}
    authors = _names(raw.get("authors") or raw.get("author") or raw.get("creators") or raw.get("authorList"))
    journal = raw.get("container-title") or raw.get("journal") or raw.get("container_title")
    if isinstance(journal, dict):
        journal = journal.get("title") or journal.get("name")
    if isinstance(journal, list):
        journal = journal[0] if journal else None
    doi = _doi(raw.get("doi") or raw.get("DOI") or external.get("DOI") or identifiers.get("doi"))
    clean = dict(raw)
    clean.update({
        "_source": source, "_rid": rid or "row-%06d" % index,
        "_observation": source + ":" + (rid or "row-%06d" % index) + ":" + str(index),
        "_title": title, "_title_key": _title(title), "_doi": doi,
        "_authors": authors, "_author_keys": _author_keys(authors), "_year": _year(raw),
        "_journal": _text(journal), "_type": _text(raw.get("type") or raw.get("publicationType")
                                                    or raw.get("pubType")),
        "_version_group": _text(raw.get("version_group") or raw.get("work_family")
                                 or raw.get("canonical_work_id")),
        "_identifiers": {"doi": doi or None,
                         "pmid": _text(raw.get("pmid") or external.get("PubMed") or identifiers.get("pmid")) or None,
                         "pmcid": _text(raw.get("pmcid") or external.get("PubMedCentral")
                                        or identifiers.get("pmcid")) or None,
                         "arxiv": _text(external.get("ArXiv") or raw.get("arxiv_id")
                                        or identifiers.get("arxiv")) or None,
                         "openalex": _text(raw.get("openalex") or raw.get("openalex_id")
                                           or identifiers.get("openalex")) or None},
    })
    return clean, None


def _translate(source, query):
    """Translate only declared concepts; generated dictionaries sort stably in JSON."""
    if isinstance(query, str):
        title, terms, author = query, query, ""
        start, end = "", ""
    else:
        query = query if isinstance(query, dict) else {}
        title = _text(query.get("title") or query.get("topic") or query.get("research_question"))
        terms = _text(query.get("terms") or query.get("bibliographic") or title)
        author = _text(query.get("author"))
        start, end = _text(query.get("from_date")), _text(query.get("until_date"))
    source = source.lower()
    phrase = terms.replace('"', "")
    if source == "crossref":
        params = {"query.bibliographic": phrase}
        if author:
            params["query.author"] = author
        filters = []
        if start:
            filters.append("from-pub-date:" + start)
        if end:
            filters.append("until-pub-date:" + end)
        if filters:
            params["filter"] = ",".join(filters)
        return {"endpoint": "https://api.crossref.org/works", "parameters": params,
                "field_semantics": "query.bibliographic/query.author; pub-date filters are publication dates"}
    if source == "europepmc":
        parts = [('TITLE:"' + title + '"')] if title else (['(' + phrase + ')'] if phrase else [])
        if author:
            parts.append('AUTH:"' + author + '"')
        if start:
            parts.append("FIRST_PDATE:[" + start + " TO *]")
        if end:
            parts.append("FIRST_PDATE:[* TO " + end + "]")
        return {"endpoint": "https://www.ebi.ac.uk/europepmc/webservices/rest/search",
                "parameters": {"query": " AND ".join(parts), "format": "json"},
                "field_semantics": "TITLE/AUTH/FIRST_PDATE native fields; not Crossref syntax"}
    if source == "openalex":
        filters = []
        if title:
            filters.append(OPENALEX_TITLE_FIELD + ":" + title)
        if start:
            filters.append("from_publication_date:" + start)
        if end:
            filters.append("to_publication_date:" + end)
        params = {"search": phrase}
        if filters:
            params["filter"] = ",".join(filters)
        return {"endpoint": "https://api.openalex.org/works", "parameters": params,
                "field_semantics": "search plus title.search/publication_date filters"}
    if source == "semantic_scholar":
        params = {"query": " ".join(x for x in (phrase, author) if x),
                  "fields": "title,authors,year,externalIds,publicationTypes,journal"}
        if start or end:
            params["publicationDateOrYear"] = (start or "*") + ":" + (end or "*")
        return {"endpoint": "https://api.semanticscholar.org/graph/v1/paper/search",
                "parameters": params, "field_semantics": "Graph API free query plus publicationDateOrYear"}
    if source == "arxiv":
        parts = [('ti:"' + title + '"')] if title else (["all:" + phrase] if phrase else [])
        if author:
            parts.append('au:"' + author + '"')
        return {"endpoint": "https://export.arxiv.org/api/query",
                "parameters": {"search_query": " AND ".join(parts)},
                "field_semantics": "arXiv ti/au fields"}
    return {"endpoint": None, "parameters": {"query": phrase, "author": author or None,
                                               "from_date": start or None, "until_date": end or None},
            "field_semantics": "generic retained-export query; database-specific mapping unavailable"}


class _Sets:
    def __init__(self, rows):
        self.parent = {r["_observation"]: r["_observation"] for r in rows}

    def find(self, key):
        if self.parent[key] != key:
            self.parent[key] = self.find(self.parent[key])
        return self.parent[key]

    def union(self, a, b):
        a, b = self.find(a), self.find(b)
        if a == b:
            return a
        a, b = sorted((a, b))
        self.parent[b] = a
        return a


def _identity(rows):
    sets = _Sets(rows)
    decisions = []
    def link(group, key, rule, details=None):
        for other in group[1:]:
            if sets.find(group[0]["_observation"]) == sets.find(other["_observation"]):
                continue
            sets.union(group[0]["_observation"], other["_observation"])
            decisions.append({"left": group[0]["_observation"], "right": other["_observation"],
                              "rule": rule, "evidence": key, "merged": True,
                              **(details or {})})
    for field, rule in (("_doi", "doi_exact"),):
        groups = {}
        for row in rows:
            if row[field]:
                groups.setdefault(row[field], []).append(row)
        for value, group in sorted(groups.items()):
            link(group, value, rule)
    # Strong secondary IDs cannot override a declared conflicting DOI.
    for field, rule in (("pmid", "pmid_exact"), ("pmcid", "pmcid_exact"), ("arxiv", "arxiv_exact")):
        groups = {}
        for row in rows:
            value = row["_identifiers"][field]
            if value:
                groups.setdefault(value, []).append(row)
        for value, group in sorted(groups.items()):
            for other in group[1:]:
                if group[0]["_doi"] and other["_doi"] and group[0]["_doi"] != other["_doi"]:
                    decisions.append({"left": group[0]["_observation"], "right": other["_observation"],
                                      "rule": "identity_conflict_veto", "evidence": value,
                                      "merged": False, "reason": "secondary ID agrees but DOIs conflict"})
                else:
                    link([group[0], other], value, rule)
    groups = {}
    for row in rows:
        if row["_version_group"]:
            groups.setdefault(row["_version_group"], []).append(row)
    for value, group in sorted(groups.items()):
        link(group, value, "declared_version_group", {"different_dois_retained": True})
    for i, a in enumerate(rows):
        for b in rows[i + 1:]:
            if sets.find(a["_observation"]) == sets.find(b["_observation"]):
                continue
            explicit = bool(a["_version_group"] and a["_version_group"] == b["_version_group"])
            if a["_doi"] and b["_doi"] and a["_doi"] != b["_doi"] and not explicit:
                continue
            if a["_year"] and b["_year"] and abs(a["_year"] - b["_year"]) > 1:
                continue
            if not a["_title_key"] or not b["_title_key"]:
                continue
            ratio = SequenceMatcher(None, a["_title_key"], b["_title_key"]).ratio()
            shared = a["_author_keys"] & b["_author_keys"]
            creator_free = not a["_authors"] and not b["_authors"]
            exact = a["_title_key"] == b["_title_key"]
            if not ((exact and (shared or creator_free or explicit)) or (ratio >= 0.94 and shared)):
                continue
            left_root, right_root = sets.find(a["_observation"]), sets.find(b["_observation"])
            left = [r for r in rows if sets.find(r["_observation"]) == left_root]
            right = [r for r in rows if sets.find(r["_observation"]) == right_root]
            if not explicit and any(x["_doi"] and y["_doi"] and x["_doi"] != y["_doi"]
                                    for x in left for y in right):
                decisions.append({"left": a["_observation"], "right": b["_observation"],
                                  "rule": "transitive_identity_veto", "merged": False,
                                  "reason": "fuzzy match would bridge distinct DOI clusters"})
                continue
            sets.union(a["_observation"], b["_observation"])
            decisions.append({"left": a["_observation"], "right": b["_observation"],
                              "rule": "title_exact_author" if exact else "title_fuzzy_author",
                              "title_similarity": round(ratio, 6), "shared_creators": sorted(shared),
                              "year_gap": abs(a["_year"] - b["_year"]) if a["_year"] and b["_year"] else None,
                              "merged": True})
    groups = {}
    for row in rows:
        groups.setdefault(sets.find(row["_observation"]), []).append(row)
    return groups, decisions


def _priority(source, configured):
    return configured.index(source) if source in configured else len(configured)


def _merge_group(members, configured_priority):
    members = sorted(members, key=lambda r: (_priority(r["_source"], configured_priority),
                                              r["_observation"]))
    rep = members[0]
    digest = hashlib.sha256("\n".join(sorted(m["_observation"] for m in members)).encode()).hexdigest()[:12]
    observations = []
    for member in members:
        observations.append({"source": member["_source"], "record_id": member["_rid"],
                             "observation_id": member["_observation"], "raw_record": {
                                 k: v for k, v in member.items() if not k.startswith("_")}})
    fields = ("title", "doi", "authors", "year", "journal", "type")
    provenance, conflicts = {}, []
    merged = {"work_id": "work-" + digest, "sources": sorted({m["_source"] for m in members}),
              "source_records": observations}
    for field in fields:
        observations_for_field = []
        values = {}
        for m in members:
            key = "_" + field
            value = m[key]
            if field == "doi":
                value = value or None
            if value in (None, "", []):
                continue
            normalized = _title(value) if field in ("title", "journal", "type") else (
                json.dumps(value, sort_keys=True, ensure_ascii=False) if isinstance(value, list) else str(value))
            values.setdefault(normalized, value)
            observations_for_field.append({"source": m["_source"], "record_id": m["_rid"],
                                           "value": value, "raw_locator": "record:" + m["_observation"]})
        provenance[field] = observations_for_field
        if observations_for_field:
            merged[field] = observations_for_field[0]["value"]
        else:
            merged[field] = None if field != "authors" else []
        if len(values) > 1:
            conflicts.append({"field": field, "selected_value": merged[field],
                              "selection_rule": "source priority then observation id",
                              "alternative_values_retained": list(values.values()),
                              "observations": observations_for_field})
    # With explicit version merging a preprint DOI must not erase a publisher DOI.
    non_preprint = [m for m in members if m["_doi"] and not m["_doi"].startswith("10.48550/")]
    if non_preprint:
        merged["doi"] = non_preprint[0]["_doi"]
    merged["identifiers"] = {name: sorted({m["_identifiers"][name] for m in members
                                                  if m["_identifiers"][name]})
                                    for name in ("doi", "pmid", "pmcid", "arxiv", "openalex")}
    merged["field_provenance"] = provenance
    merged["metadata_conflicts"] = conflicts
    merged["version_records"] = [{"source": m["_source"], "record_id": m["_rid"],
                                   "doi": m["_doi"] or None, "version": m.get("version"),
                                   "version_group": m["_version_group"] or None}
                                  for m in members]
    merged["screening_reason"] = "returned by at least one source-native query; not locally excluded"
    return merged


def run(spec):
    sources = spec.get("sources") if isinstance(spec.get("sources"), dict) else {}
    required = [_text(s) for s in _list(spec.get("required_sources") or spec.get("databases"))]
    if not required:
        required = sorted(sources) or sorted({s for s, _, _, _ in _source_rows(spec)})
    query = spec.get("query") or spec.get("research_question") or spec.get("topic") or {}
    supplied_queries = spec.get("queries") if isinstance(spec.get("queries"), dict) else {}
    translations = []
    for source in required:
        payload = sources.get(source) if isinstance(sources.get(source), dict) else {}
        generated = _translate(source, query)
        actual = supplied_queries.get(source) or payload.get("query")
        translations.append({"source": source, "translated_query": generated,
                             "executed_query": actual, "execution_claim": "retained_export_only",
                             "provided_query_precedes_generated": bool(actual)})
    rows, rejected, accepted, filtered = [], [], [], []
    source_counts = {s: {"records_seen": 0, "records_valid": 0, "records_included": 0,
                         "records_rejected": 0, "records_filtered": 0} for s in required}
    for source, payload, raw, index in _source_rows(spec):
        source_counts.setdefault(source, {"records_seen": 0, "records_valid": 0, "records_included": 0,
                                          "records_rejected": 0, "records_filtered": 0})
        source_counts[source]["records_seen"] += 1
        clean, bad = _normalise(source, raw, index)
        if bad:
            rejected.append(bad)
            source_counts[source]["records_rejected"] += 1
            continue
        source_counts[source]["records_valid"] += 1
        exclude = raw.get("include") is False
        haystack = _title(clean["_title"] + " " + _text(raw.get("abstract")))
        excluded_term = next((term for term in _list(spec.get("exclude_terms"))
                              if _title(term) and _title(term) in haystack), None)
        if exclude or excluded_term:
            filtered.append({"source": source, "record_id": clean["_rid"],
                             "reason": "declared exclusion" if exclude else "excluded term: " + excluded_term})
            source_counts[source]["records_filtered"] += 1
            continue
        payload_query = payload.get("query") or supplied_queries.get(source)
        clean["_query"] = payload_query or _translate(source, query)
        accepted.append(clean)
        rows.append(clean)
        source_counts[source]["records_included"] += 1
    if not required and not rows and not rejected:
        return {"schema_version": SCHEMA_VERSION, "status": "undetermined",
                "refusal": {"rule": "multidb.no_sources", "message": "no sources or retained records were provided"},
                "limits": ["no federated search was performed"]}
    priority = [_text(s) for s in _list(spec.get("source_priority")) if _text(s)] or DEFAULT_PRIORITY
    groups, decisions = _identity(rows)
    collapsed_observations = sum(len(members) - 1 for members in groups.values())
    merged = [_merge_group(members, priority) for _, members in sorted(groups.items(),
                  key=lambda item: sorted(m["_observation"] for m in item[1])[0])]
    merged.sort(key=lambda w: (w["title"] is None, _title(w["title"] or w["work_id"]), w["work_id"]))
    group_of = {}
    for members in groups.values():
        obs_sorted = sorted(m["_observation"] for m in members)
        digest = hashlib.sha256("\n".join(obs_sorted).encode()).hexdigest()[:12]
        for member in members:
            group_of[member["_observation"]] = "work-" + digest
    source_summary = []
    summary_sources = sorted(set(required) | set(source_counts))
    for source in summary_sources:
        payload = sources.get(source) if isinstance(sources.get(source), dict) else {}
        status = payload.get("status") or ("ok" if source in {r["_source"] for r in rows} else "missing")
        counts = source_counts.get(source, {"records_seen": 0, "records_valid": 0, "records_included": 0,
                                            "records_rejected": 0, "records_filtered": 0})
        unique = sorted({group_of[r["_observation"]] for r in rows if r["_source"] == source})
        source_summary.append({"source": source, "required": source in required, "status": status,
                               "error": payload.get("error"), "authorization": payload.get("authorization"),
                               "request": payload.get("request"), "raw_response_ref": payload.get("raw_response_ref"),
                               "pages_retained": payload.get("pages_retained"),
                               "unique_works_after_global_merge": len(unique), "work_ids": unique,
                               **counts})
    single = [w for w in merged if len(w["sources"]) == 1]
    multi = [w for w in merged if len(w["sources"]) > 1]
    unique_only = {}
    for work in single:
        unique_only.setdefault(work["sources"][0], []).append(work["work_id"])
    overlap = {}
    for work in multi:
        for i, left in enumerate(work["sources"]):
            for right in work["sources"][i + 1:]:
                key = left + "|" + right
                overlap.setdefault(key, []).append(work["work_id"])
    required_fields = [_text(f) for f in _list(spec.get("required_fields"))] or \
        ["title", "doi", "authors", "year", "journal"]
    field_coverage = {}
    for field in required_fields:
        present = [w["work_id"] for w in merged if w.get(field) not in (None, "", [])]
        missing = [w["work_id"] for w in merged if w.get(field) in (None, "", [])]
        field_coverage[field] = {"present": len(present), "missing": len(missing),
                                 "missing_work_ids": missing}
    limits = ["Generated translations are query plans; only retained exports were processed"]
    findings = []
    for summary in source_summary:
        if summary["status"] not in ("ok", "success", "complete"):
            findings.append({"rule": "multidb.source_incomplete", "severity": "high",
                             "source": summary["source"], "status": summary["status"],
                             "error": summary["error"]})
            limits.append("source " + summary["source"] + " was not completely covered")
    if rejected:
        findings.append({"rule": "multidb.record_rejected", "severity": "medium",
                         "count": len(rejected), "entries": rejected})
    if filtered:
        findings.append({"rule": "multidb.record_filtered", "severity": "low",
                         "count": len(filtered), "entries": filtered})
    conflicts = [{"work_id": w["work_id"], "conflicts": w["metadata_conflicts"]}
                 for w in merged if w["metadata_conflicts"]]
    if conflicts:
        findings.append({"rule": "multidb.metadata_conflicts_retained", "severity": "low",
                         "count": len(conflicts), "entries": conflicts})
    input_count = sum(v["records_seen"] for v in source_counts.values())
    valid_count = sum(v["records_valid"] for v in source_counts.values())
    included_count = sum(v["records_included"] for v in source_counts.values())
    reconciliation = {
        "identified_records": input_count, "rejected_records": len(rejected),
        "valid_records": valid_count, "filtered_records": len(filtered),
        "included_source_records": included_count, "unique_works": len(merged),
        "duplicate_observations": collapsed_observations,
        "single_source_works": len(single), "multi_source_works": len(multi),
        "equations": [
            {"name": "input_closure", "left": input_count,
             "right": valid_count + len(rejected), "closed": input_count == valid_count + len(rejected)},
            {"name": "screening_closure", "left": valid_count,
             "right": included_count + len(filtered), "closed": valid_count == included_count + len(filtered)},
            {"name": "dedup_closure", "left": included_count,
             "right": len(merged) + collapsed_observations,
             "closed": included_count == len(merged) + collapsed_observations},
            {"name": "overlap_partition", "left": len(merged),
             "right": len(single) + len(multi), "closed": len(merged) == len(single) + len(multi)},
        ],
    }
    reconciliation["closed"] = all(e["closed"] for e in reconciliation["equations"])
    if not reconciliation["closed"]:
        findings.append({"rule": "multidb.count_not_closed", "severity": "high"})
        limits.append("count reconciliation did not close")
    fingerprint = hashlib.sha256(json.dumps({"sources": sources, "rows": rows,
        "query": query, "required": required}, sort_keys=True, ensure_ascii=False,
        default=str).encode()).hexdigest()
    return {
        "schema_version": SCHEMA_VERSION, "status": "review" if any(
            f["severity"] in ("high", "medium") for f in findings) else "clean", "ok": True,
        "query_translations": translations, "records": merged, "merged_records": merged,
        "unique_work_count": len(merged), "source_coverage": source_summary,
        "coverage": {"required_sources": required, "covered_sources": [s["source"] for s in source_summary
                        if s["status"] in ("ok", "success", "complete")],
                     "sources_with_gaps": [s["source"] for s in source_summary
                        if s["status"] not in ("ok", "success", "complete")],
                     "unique_to_source": {k: sorted(v) for k, v in sorted(unique_only.items())},
                     "pairwise_overlap": {k: sorted(v) for k, v in sorted(overlap.items())},
                     "field_coverage": field_coverage},
        "merge_decisions": decisions, "duplicate_observations": collapsed_observations,
        "metadata_conflicts": conflicts, "rejected_records": rejected, "filtered_records": filtered,
        "count_reconciliation": reconciliation, "evidence_records": [
            {"work_id": w["work_id"], "source_lineage": w["source_records"],
             "field_provenance": w["field_provenance"]} for w in merged],
        "findings": findings, "limits": limits,
        "uncertainty": "Coverage is limited to required sources and retained responses. A failed or absent source is a recall gap, not evidence that no work exists.",
        "change_log": [{"action": "query_translation", "sources": required},
                       {"action": "identity_merge", "before": included_count, "after": len(merged)},
                       {"action": "metadata_merge", "conflicts_retained": len(conflicts)}],
        "snapshot_sha256": fingerprint,
    }


def is_multidb_spec(spec):
    return isinstance(spec, dict) and (spec.get("mode") in ("multi_db", "multidb", "federated") or
        "required_sources" in spec or "query_translations" in spec)
