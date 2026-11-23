"""Frozen-known-set coverage, miss attribution and supplementary-search accounting."""
from __future__ import annotations

import copy
import difflib
import re
from pathlib import Path
from typing import Any

import case_common as C

SCHEMA_VERSION = "search-coverage/v2"


def _iterations(spec: dict[str, Any]) -> list[dict[str, Any]]:
    raw = C.first(spec, "search_history", "iterations", "queries") or []
    if isinstance(raw, dict):
        raw = [raw | {"query_id": key} if isinstance(value, dict) else {"query_id": key, "query": value}
               for key, value in raw.items()]
    if isinstance(raw, str):
        raw = [{"query": raw}]
    out = []
    if not isinstance(raw, list):
        return out
    for i, item in enumerate(raw):
        if isinstance(item, str):
            item = {"query": item}
        if not isinstance(item, dict):
            continue
        results = C.first(item, "returned_ids", "result_ids", "candidate_ids", "record_ids", "hit_ids")
        if results is None:
            nested = item.get("results") or item.get("hits") or item.get("documents")
            if isinstance(nested, list):
                results = [C.first(x, "id", "doc_id", "doi", "DOI") if isinstance(x, dict) else x for x in nested]
        if isinstance(results, str):
            results = [results]
        fields = C.first(item, "fields", "field", "search_fields", "query_field")
        if isinstance(fields, str):
            fields = [fields]
        source = C.first(item, "source", "database", "source_name")
        kind = C.as_text(C.first(item, "phase", "kind", "iteration_type", "type", "round")).lower()
        supplementary = bool(item.get("supplementary")) or any(x in kind for x in ("supplement", "expan", "补检"))
        out.append({
            "query_id": C.as_text(C.first(item, "query_id", "id", "name") or f"query-{i + 1:02d}"),
            "query": C.first(item, "query", "search_query", "expression", "query_string", "string"),
            "fields": fields if isinstance(fields, list) else [],
            "source": source, "date_searched": C.first(item, "date_searched", "search_date", "date"),
            "date_from": C.first(item, "date_from", "from_date", "start_year", "year_from"),
            "date_to": C.first(item, "date_to", "until_date", "end_year", "year_to"),
            "supplementary": supplementary,
            "returned_ids": [C.as_text(x) for x in results if C.as_text(x)] if isinstance(results, list) else [],
            "result_count_declared": C.first(item, "result_count", "hit_count", "n_results"),
            "original": item,
        })
    return out


def _is_supplementary(doc: dict[str, Any]) -> bool:
    text = C.as_text(doc.get("retrieval_round")).lower()
    return any(x in text for x in ("supplement", "expan", "补检"))


def _id_norm(value: Any) -> str:
    text = C.normalize_doi(value)
    return text.strip().casefold()


def _doc_key(doc: dict[str, Any]) -> str:
    if doc.get("doi"):
        return "doi:" + doc["doi"]
    if doc.get("work_id"):
        return "work:" + doc["work_id"].casefold()
    return "record:" + doc["doc_id"].casefold()


def _ref_key(ref: dict[str, Any]) -> str:
    if ref.get("doi"):
        return "doi:" + ref["doi"]
    if ref.get("work_id"):
        return "work:" + ref["work_id"].casefold()
    if ref["normalized_title"] and (ref["year"] or ref["first_author"]):
        return "title:" + ref["normalized_title"] + "|" + ref["year"] + "|" + ref["first_author"]
    return "reference:" + ref["doc_id"].casefold()


def _freeze_references(raw_refs: list[Any], sources: list[str]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    refs, omissions = C.normalize_documents(raw_refs, sources)
    frozen: list[dict[str, Any]] = []
    duplicates: list[dict[str, Any]] = []
    positions: dict[str, int] = {}
    for ref in refs:
        raw = ref.get("original") if isinstance(ref.get("original"), dict) else {}
        ref["ref_id"] = C.as_text(C.first(raw, "ref_id", "reference_id", "id", "doc_id") or ref["doc_id"]) \
            if isinstance(raw, dict) else ref["doc_id"]
        ref["availability"] = C.first(raw, "availability", "access", "access_level") if isinstance(raw, dict) else None
        ref["retracted"] = bool(C.first(raw, "retracted", "isRetracted")) if isinstance(raw, dict) else False
        ref["inclusion_reason"] = C.first(raw, "inclusion_reason", "reason", "relevance_reason") if isinstance(raw, dict) else None
        ref["reference_source"] = C.first(raw, "reference_source", "source", "origin") if isinstance(raw, dict) else None
        ref["source"] = dict(ref["source"])
        if ref["reference_source"]:
            ref["source"]["reference_source"] = ref["reference_source"]
        key = _ref_key(ref)
        if key in positions:
            at = positions[key]
            master = frozen[at]
            duplicates.append({"duplicate_ref_id": ref["ref_id"], "kept_ref_id": master["ref_id"],
                               "merge_key": key, "reason": "same normalized reference work"})
            master["alternate_ref_ids"].append(ref["ref_id"])
            if not master["inclusion_reason"]:
                master["inclusion_reason"] = ref["inclusion_reason"]
            continue
        ref["alternate_ref_ids"] = []
        ref["frozen_index"] = len(frozen)
        positions[key] = len(frozen)
        frozen.append(ref)
    if not frozen:
        raise C.MaterialError("coverage.no_reference_set",
                              "reference_set/known_relevant is absent or has no identifiable works")
    kept_aliases = {r["ref_id"] for r in frozen} | {a for r in frozen for a in r["alternate_ref_ids"]}
    omissions = [o for o in omissions if C.as_text(o.get("id")) not in kept_aliases]
    return frozen, duplicates + omissions


def _load_references(spec: dict[str, Any], case_dir: Path) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    value, source = C.load_value(spec, ("reference_set", "known_relevant", "known_relevant_set",
                                           "references", "qrels"), case_dir)
    if value is None:
        return [], []
    if isinstance(value, dict) and not any(k in value for k in ("documents", "references", "reference_set",
                                                                 "known_relevant", "items", "results", "message", "resultList")):
        # TREC-like qrels: {ref-or-query: {candidate: relevance}} or {ref: candidate}.
        rows = []
        for key, target in value.items():
            if isinstance(target, dict):
                if any(str(v).isdigit() for v in target.values()):
                    rows.append({"id": key, "qrels": target})
                else:
                    row = dict(target)
                    row.setdefault("id", key)
                    rows.append(row)
            else:
                rows.append({"id": key, "candidate_id": target})
        value = rows
    rows = C.records_from_payload(value, source or "inline")
    return _freeze_references(rows, [source or "inline"] * len(rows))


def _load_candidates(spec: dict[str, Any], case_dir: Path) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    raw_docs, sources = C.load_document_records(spec, case_dir)
    docs, omissions = C.normalize_documents(raw_docs, sources)
    supplementary_raw, supplementary_path = C.load_value(spec, ("supplementary_documents", "supplemental_documents",
                                                                  "extended_corpus"), case_dir)
    if supplementary_raw is not None:
        rows = C.records_from_payload(supplementary_raw, supplementary_path or "inline")
        extra, extra_omissions = C.normalize_documents(rows, [supplementary_path or "inline"] * len(rows))
        for doc in extra:
            doc["retrieval_round"] = doc.get("retrieval_round") or "supplementary"
        docs.extend(extra)
        omissions.extend(extra_omissions)
    # Keep record-level imports. Work-level clusters below prevent double counting.
    return docs, omissions


def _cluster_documents(docs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    clusters: dict[str, dict[str, Any]] = {}
    for doc in docs:
        key = _doc_key(doc)
        if key not in clusters:
            clusters[key] = {
                "cluster_id": key, "identifiers": set(), "dois": set(), "pmids": set(),
                "titles": [], "years": set(), "authors": set(), "views": [], "keys": {key},
                "record_ids": set(), "work_ids": set(),
            }
        cluster = clusters[key]
        cluster["identifiers"].update(_id_norm(x) for x in doc["identifiers"] if _id_norm(x))
        cluster["record_ids"].add(_id_norm(doc["doc_id"]))
        if doc.get("work_id"):
            cluster["work_ids"].add(_id_norm(doc["work_id"]))
            cluster["keys"].add("work:" + _id_norm(doc["work_id"]))
        if doc.get("doi"):
            cluster["dois"].add(doc["doi"])
        if doc.get("pmid"):
            cluster["pmids"].add(_id_norm(doc["pmid"]))
        if doc["normalized_title"]:
            cluster["titles"].append(doc)
        if doc["year"]:
            cluster["years"].add(doc["year"])
        if doc["first_author"]:
            cluster["authors"].add(doc["first_author"])
        cluster["views"].append(doc)
    # Follow explicit work_id/version_of links only; similar titles alone never merge works.
    by_work = {}
    for cluster in clusters.values():
        for work in cluster["work_ids"]:
            by_work.setdefault(work, []).append(cluster)
    merged: list[dict[str, Any]] = []
    used: set[int] = set()
    for cluster in clusters.values():
        if id(cluster) in used:
            continue
        group = [cluster]
        for work in cluster["work_ids"]:
            group.extend(by_work.get(work, []))
        root = cluster
        for other in group:
            if other is root or id(other) in used:
                continue
            root["identifiers"].update(other["identifiers"])
            root["dois"].update(other["dois"])
            root["pmids"].update(other["pmids"])
            root["titles"].update(other["titles"])
            root["years"].update(other["years"])
            root["authors"].update(other["authors"])
            root["views"].extend(other["views"])
            root["keys"].update(other["keys"])
            root["record_ids"].update(other["record_ids"])
            root["work_ids"].update(other["work_ids"])
            used.add(id(other))
        used.add(id(root))
        merged.append(root)
    return merged


def _title_similarity(a: str, b: str) -> tuple[float, float]:
    sequence = difflib.SequenceMatcher(None, a, b).ratio() if a and b else 0.0
    ta, tb = set(C.text_terms(a)), set(C.text_terms(b))
    jaccard = len(ta & tb) / len(ta | tb) if ta | tb else 0.0
    return sequence, jaccard


def _manual_map(spec: dict[str, Any]) -> dict[tuple[str, str], dict[str, Any]]:
    raw = C.first(spec, "manual_adjudications", "match_adjudications", "coverage_adjudications") or []
    if not isinstance(raw, list):
        return {}
    out = {}
    for item in raw:
        if not isinstance(item, dict):
            continue
        ref = C.as_text(C.first(item, "ref_id", "reference_id", "known_id"))
        cand = C.as_text(C.first(item, "candidate_id", "doc_id", "record_id", "cluster_id"))
        if ref:
            out[(ref.casefold(), cand.casefold())] = item
    return out


def _match_one(ref: dict[str, Any], cluster: dict[str, Any]) -> dict[str, Any] | None:
    ref_ids = {_id_norm(x) for x in ref["identifiers"] if _id_norm(x)}
    ref_ids.add(_id_norm(ref["ref_id"]))
    exact = sorted(ref_ids & (cluster["identifiers"] | cluster["record_ids"] | cluster["work_ids"]))
    if ref.get("doi") and ref["doi"] in cluster["dois"]:
        exact.append("doi:" + ref["doi"])
    if ref.get("pmid") and _id_norm(ref["pmid"]) in cluster["pmids"]:
        exact.append("pmid:" + ref["pmid"])
    if exact:
        return {"covered": True, "method": "identifier_exact", "confidence": "high",
                "matched_identifiers": sorted(set(exact)), "needs_adjudication": False}
    best = None
    for other in cluster["titles"]:
        if not ref["normalized_title"] or not other["normalized_title"]:
            continue
        sequence, jaccard = _title_similarity(ref["normalized_title"], other["normalized_title"])
        exact_title = ref["normalized_title"] == other["normalized_title"]
        year_ok = bool(ref["year"] and other["year"] and ref["year"] == other["year"])
        author_ok = bool(ref["first_author"] and other["first_author"]
                         and ref["first_author"] == other["first_author"])
        year_conflict = bool(ref["year"] and other["year"] and ref["year"] != other["year"])
        author_conflict = bool(ref["first_author"] and other["first_author"]
                               and ref["first_author"] != other["first_author"])
        title_ok = exact_title or (sequence >= 0.92 and jaccard >= 0.70)
        candidate = {
            "covered": title_ok and (year_ok or author_ok) and not year_conflict and not author_conflict,
            "method": "title_exact_with_corroboration" if exact_title else "title_approximate_with_corroboration",
            "confidence": "high" if exact_title and year_ok and author_ok else "medium",
            "title_similarity": round(sequence, 6), "title_token_jaccard": round(jaccard, 6),
            "year_match": year_ok, "author_match": author_ok,
            "year_conflict": year_conflict, "author_conflict": author_conflict,
            "matched_doc_id": other["doc_id"],
            "needs_adjudication": title_ok and not (year_ok or author_ok),
        }
        if best is None or (candidate["covered"], sequence + jaccard) > (best["covered"], best["title_similarity"] + best["title_token_jaccard"]):
            best = candidate
    return best


def _match_refs(refs: list[dict[str, Any]], clusters: list[dict[str, Any]], manual: dict[tuple[str, str], dict[str, Any]]) -> list[dict[str, Any]]:
    ledger = []
    for ref in refs:
        matches = []
        for cluster in clusters:
            match = _match_one(ref, cluster)
            if match:
                match = dict(match)
                match["cluster_id"] = cluster["cluster_id"]
                match["candidate_ids"] = [v["doc_id"] for v in cluster["views"]]
                matches.append(match)
        for adjudication_key, decision in manual.items():
            ref_key, cand_key = adjudication_key
            if ref_key not in {ref["ref_id"].casefold(), ref["doc_id"].casefold(),
                               *[a.casefold() for a in ref["alternate_ref_ids"]]}:
                continue
            selected = next((m for m in matches if cand_key in {m["cluster_id"].casefold(),
                            *[x.casefold() for x in m["candidate_ids"]]}), None)
            verdict = C.as_text(C.first(decision, "decision", "verdict", "status")).lower()
            if verdict in {"covered", "include", "match", "yes", "true", "hit"}:
                selected = selected or {"cluster_id": cand_key, "candidate_ids": [cand_key]}
                selected.update({"covered": True, "method": "manual_adjudication", "confidence": "reviewed",
                                 "needs_adjudication": False, "manual": decision})
                matches = [selected] + [m for m in matches if m is not selected]
            elif verdict in {"not_covered", "exclude", "different_work", "no", "false", "miss"}:
                matches = [m for m in matches if cand_key not in {m["cluster_id"].casefold(),
                           *[x.casefold() for x in m["candidate_ids"]]}]
        covered = [m for m in matches if m.get("covered")]
        pending = [m for m in matches if m.get("needs_adjudication")]
        selected = covered[0] if covered else pending[0] if pending else None
        entry = {
            "ref_id": ref["ref_id"], "reference": {
                "doi": ref["doi"] or None, "pmid": ref["pmid"] or None, "title": ref["title"] or None,
                "year": ref["year"] or None, "first_author": ref["first_author"] or None,
                "alternate_ref_ids": ref["alternate_ref_ids"], "inclusion_reason": ref["inclusion_reason"],
                "availability": ref["availability"], "retracted": ref["retracted"],
            },
            "status": "covered" if covered else "awaiting_adjudication" if pending else "missed",
            "covered": bool(covered), "match": selected,
            "alternative_matches": matches[1:] if selected else [],
            "evidence": [], "attempted_queries": [], "miss_analysis": None,
        }
        if selected:
            best_doc_id = selected.get("matched_doc_id") or (selected["candidate_ids"][0] if selected.get("candidate_ids") else "")
            terms = [ref["title"], ref.get("doi"), ref.get("pmid"), ref["ref_id"]]
            for cluster in clusters:
                if cluster["cluster_id"] == selected["cluster_id"]:
                    doc = next((v for v in cluster["views"] if v["doc_id"] == best_doc_id), cluster["views"][0])
                    entry["evidence"] = C.evidence_for(doc, [C.as_text(t) for t in terms if C.as_text(t)])
                    break
        ledger.append(entry)
    return ledger


def _query_checks(ref: dict[str, Any], queries: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    checks: list[dict[str, Any]] = []
    reasons: list[dict[str, Any]] = []
    title_terms = [t for t in C.text_terms(ref["title"]) if len(t) >= 4]
    ref_source = C.as_text(ref.get("reference_source") or ref["source"].get("name")).casefold()
    for query in queries:
        expression = C.as_text(query["query"])
        normalized_expr = expression.casefold()
        present = [t for t in title_terms if t in normalized_expr]
        missing = [t for t in title_terms if t not in normalized_expr]
        check = {
            "query_id": query["query_id"], "query": expression or None,
            "source": query["source"], "fields": query["fields"],
            "date_from": query["date_from"], "date_to": query["date_to"],
            "title_terms_present": present, "title_terms_absent": missing,
            "returned_reference_identifier": any(_id_norm(v) in {_id_norm(x) for x in query["returned_ids"]}
                                                  for v in ref["identifiers"]),
        }
        checks.append(check)
        year = ref["year"]
        def window_year(value: Any) -> str:
            match = re.search(r"(?:18|19|20|21)\d{2}", C.as_text(value))
            return match.group(0) if match else ""
        start, end = window_year(query["date_from"]), window_year(query["date_to"])
        if year and ((start and year < start) or (end and year > end)):
            reasons.append({"reason_code": "time_window_excludes_reference", "certainty": "verified_from_declared_protocol",
                            "query_id": query["query_id"], "source": query["source"], "fields": query["fields"],
                            "evidence": {"reference_year": year, "date_from": query["date_from"], "date_to": query["date_to"]},
                            "action": "Run a versioned query that includes the reference year."})
        if ref_source and query["source"] and ref_source != C.as_text(query["source"]).casefold():
            reasons.append({"reason_code": "reference_source_not_queried", "certainty": "verified_from_declared_protocol",
                            "query_id": query["query_id"], "source": query["source"], "expected_source": ref.get("reference_source") or ref["source"].get("name"),
                            "action": "Search the reference-bearing source or explicitly document its unavailability."})
        if title_terms and not present and expression:
            reasons.append({"reason_code": "query_lacks_reference_title_discriminators", "certainty": "lexical_clue_not_sole_cause",
                            "query_id": query["query_id"], "source": query["source"], "fields": query["fields"],
                            "evidence": {"required_title_terms_considered": title_terms, "absent_terms": missing},
                            "action": "Add validated title synonyms or an identifier probe, then measure newly covered references."})
    return checks, reasons


def _finish_misses(ledger: list[dict[str, Any]], refs: list[dict[str, Any]], queries: list[dict[str, Any]]) -> None:
    by_ref = {r["ref_id"]: r for r in refs}
    for entry in ledger:
        if entry["covered"]:
            entry["attempted_queries"] = [{k: q[k] for k in ("query_id", "query", "source", "fields", "returned_ids")}
                                          for q in queries]
            continue
        ref = by_ref[entry["ref_id"]]
        checks, reasons = _query_checks(ref, queries)
        entry["attempted_queries"] = checks
        unavailable = bool(ref["retracted"]) or C.as_text(ref["availability"]).lower() in {
            "unavailable", "restricted", "paywalled", "no_full_text", "retracted",
        }
        pending_match = entry["status"] == "awaiting_adjudication"
        primary = "match_requires_manual_adjudication" if pending_match else reasons[0]["reason_code"] if reasons else "not_present_in_supplied_candidate_snapshot"
        absence_reason = [] if pending_match else [{"reason_code": "not_present_in_supplied_candidate_snapshot",
                                 "certainty": "verified_for_supplied_snapshot",
                                 "evidence": "No final candidate satisfied the declared identifier/title+corroboration/manual rule.",
                                 "action": "Search a new source or add validated terms; absence here says nothing about global relevance."}]
        if pending_match:
            absence_reason.append({"reason_code": "match_requires_manual_adjudication",
                                   "certainty": "candidate_exists_but_identity_unresolved",
                                   "candidate": entry["match"],
                                   "action": "Confirm or reject the candidate; neither coverage nor exclusion is inferred automatically."})
        entry["miss_analysis"] = {
            "primary_reason": primary,
            "reasons": reasons + absence_reason,
            "record_availability": ref["availability"], "retracted": ref["retracted"],
            "unavailable_record_kept_in_denominator": unavailable,
            "note": "A miss is not a judgement of irrelevance. Lexical clues are separated from verified query-window/source facts.",
        }


def _metrics(ledger: list[dict[str, Any]], judged_candidate_count: int | None = None) -> dict[str, Any]:
    total = len(ledger)
    covered = sum(1 for x in ledger if x["covered"])
    matched_clusters = {x["match"]["cluster_id"] for x in ledger if x["covered"] and x.get("match")}
    precision = None
    if judged_candidate_count is not None and judged_candidate_count > 0:
        precision = min(len(matched_clusters), judged_candidate_count) / judged_candidate_count
    return {
        "scope": "frozen_known_relevant_set_only",
        "reference_total_after_internal_dedup": total,
        "covered_references": covered, "missed_references": total - covered,
        "unmatched_references": sum(1 for x in ledger if x["status"] == "missed"),
        "awaiting_adjudication": sum(1 for x in ledger if x["status"] == "awaiting_adjudication"),
        "known_set_recall": covered / total if total else None,
        "known_set_miss_rate": (total - covered) / total if total else None,
        "candidate_precision": precision,
        "precision_denominator": judged_candidate_count,
        "absolute_coverage": None,
        "scope_note": "Recall uses the frozen supplied relevant set, not retrieved hits. Absolute corpus/global coverage is unknowable from this snapshot and is not estimated. Precision is computed only when every candidate has an explicit relevance judgement.",
    }


def _candidate_provenance(clusters: list[dict[str, Any]], queries: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    out = {c["cluster_id"]: [] for c in clusters}
    lookup = {}
    for c in clusters:
        for key in c["identifiers"] | c["record_ids"] | c["work_ids"] | c["keys"]:
            lookup[_id_norm(key)] = c["cluster_id"]
    for query in queries:
        for value in query["returned_ids"]:
            key = lookup.get(_id_norm(value))
            if key is not None:
                out[key].append({"query_id": query["query_id"], "source": query["source"],
                                 "fields": query["fields"], "query": query["query"],
                                 "supplementary": query["supplementary"]})
    for c in clusters:
        seen_queries = {p["query_id"] for p in out[c["cluster_id"]]}
        for view in c["views"]:
            if view.get("query_id") and C.as_text(view["query_id"]) not in seen_queries:
                out[c["cluster_id"]].append({"query_id": view["query_id"], "query": view.get("query"),
                                             "fields": [view["query_field"]] if view.get("query_field") else [],
                                             "source": view["source"].get("name"), "supplementary": _is_supplementary(view)})
    return out


def _iteration_comparison(refs: list[dict[str, Any]], clusters: list[dict[str, Any]], queries: list[dict[str, Any]],
                          manual: dict[tuple[str, str], dict[str, Any]]) -> dict[str, Any]:
    provenance = _candidate_provenance(clusters, queries)
    baseline_queries = [q for q in queries if not q["supplementary"]]
    supplementary_queries = [q for q in queries if q["supplementary"]]
    if queries and any(q["returned_ids"] for q in queries):
        baseline_keys = {p for q in baseline_queries for p in q["returned_ids"]}
        baseline_clusters = [c for c in clusters if any(_id_norm(p) in (c["identifiers"] | c["record_ids"] | c["work_ids"] | c["keys"])
                                                        for p in baseline_keys)]
        # Candidate records with no query result map cannot be invented into the query-based baseline.
        if not baseline_queries and not supplementary_queries:
            baseline_clusters = [c for c in clusters if not any(_is_supplementary(v) for v in c["views"])]
        basis = "query_returned_ids"
    else:
        baseline_clusters = [c for c in clusters if not any(_is_supplementary(v) for v in c["views"])]
        basis = "supplied_corpus_and_supplementary_round_tags"
    if not supplementary_queries and not any(_is_supplementary(v) for c in clusters for v in c["views"]):
        basis = "single_snapshot_no_supplementary_round"
    before = _match_refs(refs, baseline_clusters, manual)
    after = _match_refs(refs, clusters, manual)
    before_covered = {x["ref_id"] for x in before if x["covered"]}
    after_covered = {x["ref_id"] for x in after if x["covered"]}
    rounds = []
    cumulative = set(before_covered)
    for query in supplementary_queries:
        returned = {_id_norm(x) for x in query["returned_ids"]}
        selected_clusters = [c for c in clusters if returned & (c["identifiers"] | c["record_ids"] | c["work_ids"] | c["keys"])]
        visible = baseline_clusters + selected_clusters
        result = _match_refs(refs, visible, manual)
        round_covered = {x["ref_id"] for x in result if x["covered"]}
        new = sorted(round_covered - cumulative)
        rounds.append({"query_id": query["query_id"], "query": query["query"], "source": query["source"],
                       "fields": query["fields"], "newly_covered_ref_ids": new, "marginal_gain": len(new),
                       "no_new_coverage": not new})
        cumulative.update(round_covered)
    # If supplementary records carry no query ids, calculate their aggregate marginal gain without per-query inventions.
    final_new = sorted(after_covered - before_covered)
    return {
        "basis": basis, "before": _metrics(before), "after": _metrics(after),
        "newly_covered_ref_ids": final_new, "marginal_gain": len(final_new),
        "miss_reduction": (len(before) - len(before_covered)) - (len(after) - len(after_covered)),
        "supplementary_rounds": rounds,
        "remaining_missed_ref_ids": sorted({x["ref_id"] for x in after if not x["covered"]}),
        "stop_rule": "Stop when an actually executed new-source/new-term round adds zero newly covered references; a lexical rewrite alone is not evidence of gain.",
    }


def analyze(spec: dict[str, Any], case_dir: Path) -> dict[str, Any]:
    refs, ref_issues = _load_references(spec, case_dir)
    if not refs:
        raise C.MaterialError("coverage.no_reference_set",
                              "reference_set/known_relevant is absent or has no identifiable works")
    docs, omissions = _load_candidates(spec, case_dir)
    if not docs:
        raise C.MaterialError("coverage.no_candidates", "no candidate document could be normalized")
    queries = _iterations(spec)
    clusters = _cluster_documents(docs)
    manual = _manual_map(spec)
    ledger = _match_refs(refs, clusters, manual)
    _finish_misses(ledger, refs, queries)
    provenance = _candidate_provenance(clusters, queries)
    judged = C.first(spec, "judged_candidates", "candidate_relevance_judgements", "candidate_labels")
    judged_count = None
    if C.first(spec, "candidate_labels_complete", "all_candidates_judged") is True:
        if isinstance(judged, list):
            judged_count = len(judged)
        elif isinstance(judged, dict):
            judged_count = len(judged)
        elif judged is None:
            judged_count = len(clusters)
    metrics = _metrics(ledger, judged_count)
    comparison = _iteration_comparison(refs, clusters, queries, manual)
    candidates = []
    for cluster in clusters:
        representative = cluster["views"][0]
        candidates.append({
            "work_key": cluster["cluster_id"], "record_ids": [v["doc_id"] for v in cluster["views"]],
            "metadata": [v["metadata"] for v in cluster["views"]],
            "sources": [v["source"] for v in cluster["views"]],
            "versions": [{"record_id": v["doc_id"], "version": v["metadata"].get("version"),
                          "language": v["metadata"].get("language"), "source_scope": "abstract_only" if v["abstract_only"] else "full_or_supplied_text"} for v in cluster["views"]],
            "retrieval_provenance": provenance[cluster["cluster_id"]],
        })
    findings = []
    if ref_issues:
        findings.append({"rule": "coverage.reference_records_skipped", "severity": "medium", "entries": ref_issues})
    if omissions:
        findings.append({"rule": "coverage.candidate_records_skipped", "severity": "medium", "entries": omissions})
    unresolved = [x["ref_id"] for x in ledger if x["status"] == "awaiting_adjudication"]
    if unresolved:
        findings.append({"rule": "coverage.match_adjudication_required", "severity": "medium", "ref_ids": unresolved})
    if judged_count is None:
        findings.append({"rule": "coverage.precision_not_estimable", "severity": "low",
                         "message": "Candidate relevance labels are incomplete; no precision is invented."})
    limits = ["Only supplied local records and declared query history were used; no live source or global coverage is claimed."]
    if not queries:
        limits.append("No query history was supplied, so source/field/time attribution is limited to the final candidate snapshot.")
    if comparison["basis"] == "single_snapshot_no_supplementary_round":
        limits.append("No supplementary search was supplied; before/after gain is zero rather than a fabricated expansion.")
    status = "review" if findings and any(f["severity"] in {"high", "medium"} for f in findings) else "clean"
    uncertainty = ["Known-set recall is not absolute corpus coverage.", "Uncovered references remain relevant-set members, not irrelevant works."]
    if unresolved:
        uncertainty.append("Some exact/near-title candidates lack identifier/author/year corroboration and need human adjudication.")
    result = {
        "schema_version": SCHEMA_VERSION, "status": status,
        "reference_freeze": {"sha256": C.fingerprint([{k: r[k] for k in ("ref_id", "doi", "pmid", "title", "year", "first_author", "inclusion_reason")} for r in refs]),
                             "reference_count_raw_after_unusable_omissions": len(refs) + len(ref_issues),
                             "reference_count_unique": len(refs), "issues": ref_issues,
                             "denominator_rule": "One frozen relevant work after internal reference dedup; retracted/unavailable records stay in the denominator."},
        "input_fingerprint": C.fingerprint(spec),
        "coverage_metrics": metrics, "coverage_matrix": ledger,
        "missed_references": [x for x in ledger if not x["covered"]],
        "supplementary_search": comparison, "candidate_set": candidates,
        "documents_indexed": len(docs), "unique_candidate_works": len(clusters),
        "findings": findings, "limits": limits, "uncertainty": uncertainty,
        "sources": [{"query_id": q["query_id"], "query": q["query"], "source": q["source"], "fields": q["fields"],
                     "date_searched": q["date_searched"], "date_from": q["date_from"], "date_to": q["date_to"],
                     "returned_ids": q["returned_ids"], "supplementary": q["supplementary"]} for q in queries],
        "change_records": [{"operation": "freeze_reference_set", "sha256": C.fingerprint([r["ref_id"] for r in refs])},
                           {"operation": "deduplicate_candidates", "input_records": len(docs), "unique_candidate_works": len(clusters)},
                           {"operation": "measure_supplementary_gain", "basis": comparison["basis"],
                            "newly_covered": comparison["newly_covered_ref_ids"]}],
        "omissions": omissions,
        "independent_recompute": {"recall_numerator": metrics["covered_references"],
                                  "recall_denominator": metrics["reference_total_after_internal_dedup"],
                                  "expected_miss_plus_covered": len(ledger),
                                  "closure_holds": metrics["covered_references"] + metrics["unmatched_references"] + metrics["awaiting_adjudication"] == len(ledger)},
    }
    return result


def attach_rubric(result: dict[str, Any]) -> dict[str, Any]:
    result["检索结果"] = {
        "候选文献": result["candidate_set"], "排序/筛选结果": result["coverage_matrix"],
        "元数据": [c["metadata"] for c in result["candidate_set"]],
        "来源定位": [c["sources"] for c in result["candidate_set"]],
        "覆盖率": result["coverage_metrics"], "遗漏说明": result["missed_references"],
        "补检增益": result["supplementary_search"],
    }
    result["证据记录"] = {
        "参考集冻结": result["reference_freeze"], "逐条命中与证据": result["coverage_matrix"],
        "查询字段来源": result["sources"], "补检前后": result["supplementary_search"],
        "复算入口": result["independent_recompute"], "核验方法": "Each evidence quote is the exact source_field[start:end]; recall = covered / frozen unique reference works.",
    }
    result["状态说明"] = C.status_block(
        result["status"], [x["ref_id"] for x in result["coverage_matrix"] if x["covered"]],
        [x["ref_id"] for x in result["coverage_matrix"] if not x["covered"]],
        [] if result["candidate_set"] else ["candidate_set"],
        [f for f in result["findings"] if "adjudication" in f["rule"]], result["omissions"], result["uncertainty"])
    result["evidence_ledger"] = [{"ref_id": row["ref_id"], "evidence": row["evidence"],
                                  "attempted_queries": row["attempted_queries"],
                                  "miss_analysis": row["miss_analysis"]} for row in result["coverage_matrix"]]
    result["运行状态"] = result["status"]
    return result
