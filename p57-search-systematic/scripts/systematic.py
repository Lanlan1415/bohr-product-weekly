"""Versioned search protocol, conservative dedup and dual-review PRISMA screening."""
from __future__ import annotations

import difflib
import json
from pathlib import Path
from typing import Any

import case_common as C

SCHEMA_VERSION = "search-systematic/v2"
INC, EXC = "include", "exclude"
PENDING = "pending"


def _queries(spec: dict[str, Any], protocol: dict[str, Any]) -> list[dict[str, Any]]:
    raw = protocol.get("searches") or protocol.get("queries") or spec.get("queries") or spec.get("search_history") or []
    if isinstance(raw, dict):
        raw = [dict(v, query_id=k) if isinstance(v, dict) else {"query_id": k, "query": v} for k, v in raw.items()]
    if isinstance(raw, str):
        raw = [{"query": raw}]
    out = []
    if not isinstance(raw, list):
        return out
    for i, q in enumerate(raw):
        if isinstance(q, str):
            q = {"query": q}
        if not isinstance(q, dict):
            continue
        fields = C.first(q, "fields", "field", "search_fields")
        if isinstance(fields, str):
            fields = [fields]
        out.append({
            "query_id": C.as_text(C.first(q, "query_id", "id") or f"query-{i + 1:02d}"),
            "database": C.first(q, "database", "source", "source_name"),
            "platform": C.first(q, "platform", "interface", "provider"),
            "query_string": C.first(q, "query_string", "query", "expression", "search_query"),
            "fields": fields if isinstance(fields, list) else [],
            "coverage_from": C.first(q, "coverage_from", "date_from", "start_date", "year_from"),
            "coverage_to": C.first(q, "coverage_to", "date_to", "end_date", "year_to"),
            "date_searched": C.first(q, "date_searched", "search_date", "date"),
            "language_limits": q.get("language_limits", q.get("languages")),
            "other_limits": C.first(q, "other_limits", "limits", "filters"),
            "hit_count_declared": C.first(q, "hit_count", "result_count", "n_results"),
            "returned_ids": C.first(q, "returned_ids", "result_ids", "record_ids") or [],
            "deduplication_method": C.first(q, "deduplication_method", "dedup_method"),
            "notes": q.get("notes"),
        })
    return out


def _criteria_values(raw: dict[str, Any]) -> list[str]:
    values = C.first(raw, "values", "any", "all", "terms", "value", "term", "synonyms")
    if values is None:
        return []
    if not isinstance(values, list):
        values = [values]
    return [C.as_text(v) for v in values if C.as_text(v)]


def _normalized_criteria(spec: dict[str, Any], protocol: dict[str, Any]) -> list[dict[str, Any]]:
    raw_items: list[Any] = []
    for key, kind in (("criteria", None), ("inclusion_criteria", "include"), ("exclusion_criteria", "exclude")):
        value = protocol.get(key, spec.get(key))
        if isinstance(value, dict):
            value = [dict(v, id=k) if isinstance(v, dict) else {"id": k, "any": v} for k, v in value.items()]
        if isinstance(value, str):
            value = [value]
        if isinstance(value, list):
            for item in value:
                if isinstance(item, dict) and kind and not C.first(item, "type", "kind", "direction"):
                    item = dict(item, type=kind)
                elif isinstance(item, str) and kind:
                    item = {"any": [item], "type": kind}
                raw_items.append(item)
    out = []
    for i, item in enumerate(raw_items):
        if isinstance(item, str):
            item = {"any": [item]}
        if not isinstance(item, dict):
            continue
        kind = C.as_text(C.first(item, "type", "kind", "direction") or "include").lower()
        kind = "exclude" if kind.startswith("ex") or kind in {"exclusion", "not"} else "include"
        out.append({
            "id": C.as_text(C.first(item, "id", "criterion_id", "name") or f"{kind[:3].upper()}-{i + 1:02d}"),
            "type": kind,
            "field": C.as_text(C.first(item, "field", "source_field") or "text"),
            "values": _criteria_values(item),
            "match": C.as_text(C.first(item, "match", "operator") or "any").lower(),
            "reason_code": C.first(item, "reason_code", "failure_reason", "code"),
            "description": C.first(item, "description", "criterion", "label"),
            "original": item,
        })
    return out


def _protocol(spec: dict[str, Any]) -> dict[str, Any]:
    raw = spec["screening_protocol"] if "screening_protocol" in spec else spec.get("protocol", {})
    if raw is None:
        raw = {}
    if not isinstance(raw, dict):
        raise C.MaterialError("systematic.protocol_invalid", "screening_protocol must be an object")
    criteria = _normalized_criteria(spec, raw)
    searches = _queries(spec, raw)
    if not criteria:
        raise C.MaterialError("systematic.no_criteria", "no executable inclusion/exclusion criteria were supplied")
    review_mode = C.as_text(C.first(raw, "review_mode", "screening_mode") or spec.get("review_mode") or "dual_independent")
    declared = C.first(raw, "criteria_version", "protocol_version", "version") or spec.get("criteria_version")
    canonical = {"criteria": [{k: c[k] for k in ("id", "type", "field", "values", "match", "reason_code")} for c in criteria],
                 "searches": searches, "review_mode": review_mode}
    digest = C.fingerprint(canonical)
    return {
        "criteria_version": C.as_text(declared) if declared else "sha256:" + digest[:16],
        "declared_version_present": declared is not None,
        "protocol_sha256": digest, "review_mode": review_mode,
        "criteria": criteria, "searches": searches,
        "scope": C.first(raw, "scope", "research_question") or spec.get("research_question"),
        "date_limit_note": "Dates and limits are caller-declared protocol facts, not a claim that a live database was searched.",
        "freeze_rule": "The same content hash governs every record. Votes from another declared version are not silently reused.",
    }


def _title_conflict(a: dict[str, Any], b: dict[str, Any]) -> bool:
    if not a["normalized_title"] or not b["normalized_title"]:
        return False
    return difflib.SequenceMatcher(None, a["normalized_title"], b["normalized_title"]).ratio() < 0.50


def _relation_targets(doc: dict[str, Any]) -> set[str]:
    raw = doc["original"]
    values = [raw.get(k) for k in ("work_id", "study_id", "version_of", "translation_of", "trans_of", "relation", "relation_type")]
    out = set()
    def walk(value: Any):
        if isinstance(value, str):
            out.update({_norm(value), _norm(C.normalize_doi(value))})
        elif isinstance(value, dict):
            for key, item in value.items():
                if any(x in key.lower() for x in ("version", "preprint", "translation", "work", "study", "doi", "id")):
                    walk(item)
        elif isinstance(value, list):
            for item in value:
                walk(item)
    for value in values:
        walk(value)
    out.discard("")
    return out


def _norm(value: Any) -> str:
    return C.as_text(value).strip().casefold()


def _deduplicate(docs: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    n = len(docs)
    parent = list(range(n))
    conflicts: list[dict[str, Any]] = []
    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i
    def union(i, j, reason):
        a, b = find(i), find(j)
        if a == b:
            return True
        ai, bi = (a, b) if a < b else (b, a)
        parent[bi] = ai
        return True
    def safe_pair(i, j):
        return not _title_conflict(docs[i], docs[j])
    by_work, by_doi, by_pmid = {}, {}, {}
    for i, doc in enumerate(docs):
        work = _norm(doc.get("work_id"))
        if work:
            by_work.setdefault(work, []).append(i)
        if doc.get("doi"):
            by_doi.setdefault(doc["doi"], []).append(i)
        if doc.get("pmid"):
            by_pmid.setdefault(_norm(doc["pmid"]), []).append(i)
    for mapping, reason in ((by_work, "explicit_work_id"), (by_doi, "doi_exact"), (by_pmid, "pmid_exact")):
        for key, ids in mapping.items():
            for j in ids[1:]:
                i = ids[0]
                if safe_pair(i, j):
                    union(i, j, reason)
                else:
                    conflicts.append({"rule": "systematic.identifier_conflict", "ids": [docs[i]["doc_id"], docs[j]["doc_id"]],
                                      "key": key, "message": "Same identifier but widely divergent titles; records were not merged."})
    # Title matching needs both author AND year for DOI-missing records. Two different DOIs never merge by title.
    for i in range(n):
        for j in range(i + 1, n):
            a, b = docs[i], docs[j]
            if not a["normalized_title"] or a["normalized_title"] != b["normalized_title"]:
                continue
            if a.get("doi") and b.get("doi") and a["doi"] != b["doi"]:
                continue
            if not a["first_author"] or a["first_author"] != b["first_author"] or not a["year"] or a["year"] != b["year"]:
                continue
            union(i, j, "title_author_year_exact")
    lookup = {}
    for key, ids in by_work.items():
        for i in ids:
            lookup[key] = i
    for key, ids in by_doi.items():
        lookup[key] = ids[0]
        lookup[_norm(key)] = ids[0]
    for key, ids in by_pmid.items():
        lookup[key] = ids[0]
    for i, doc in enumerate(docs):
        for target in _relation_targets(doc):
            if target in lookup:
                union(i, lookup[target], "explicit_version_relation")
    groups: dict[int, list[int]] = {}
    for i in range(n):
        groups.setdefault(find(i), []).append(i)
    clusters, merge_log = [], []
    for root, ids in sorted(groups.items(), key=lambda item: min(item[1])):
        ids = sorted(ids)
        members = [docs[i] for i in ids]
        kept = members[0]
        cluster_id = kept.get("work_id") or kept.get("doi") or kept["doc_id"]
        cluster = {"cluster_id": cluster_id, "records": members, "record_ids": [d["doc_id"] for d in members],
                   "title": kept["title"] or next((d["title"] for d in members if d["title"]), None),
                   "metadata": [d["metadata"] for d in members],
                   "sources": [d["source"] for d in members],
                   "versions": [{"record_id": d["doc_id"], "version": d["metadata"].get("version"),
                                 "full_text_available": d["full_text_available"], "abstract_only": d["abstract_only"]}
                                for d in members]}
        for member in members[1:]:
            exact = (member.get("doi") and any(d.get("doi") == member.get("doi") for d in members[:members.index(member)])) \
                or (member.get("pmid") and any(d.get("pmid") == member.get("pmid") for d in members[:members.index(member)])) \
                or C.fingerprint(member["text"]) == C.fingerprint(kept["text"])
            related = bool(member.get("work_id") or _relation_targets(member))
            kind = "version_linked" if related and not exact else "duplicate_removed"
            merge_log.append({"removed_record_id": member["doc_id"], "kept_cluster_id": cluster_id,
                              "kept_record_id": kept["doc_id"], "kind": kind,
                              "reason": "exact identifier/content" if exact else "explicit work/version link or title+author+year",
                              "canonical_title": kept["title"] or None,
                              "member_title": member["title"] or None})
        clusters.append(cluster)
    return clusters, merge_log, conflicts


def _all_text(cluster: dict[str, Any]) -> str:
    return "\n".join(d["text"] for d in cluster["records"])


def _structured_value(cluster: dict[str, Any], field: str) -> Any:
    for doc in cluster["records"]:
        if field in doc["original"]:
            return doc["original"][field]
    return None


def _criterion_evaluation(cluster: dict[str, Any], criterion: dict[str, Any]) -> dict[str, Any]:
    text = _all_text(cluster)
    structured = _structured_value(cluster, criterion["field"])
    haystack = C.as_text(structured) if structured is not None and not isinstance(structured, (dict, list)) else text
    matches = [v for v in criterion["values"] if C.term_occurrences(haystack, v)]
    operator = criterion["match"]
    if operator in {"all", "includes_all", "and"}:
        matched = bool(criterion["values"]) and len(matches) == len(criterion["values"])
    elif operator in {"none", "not_any", "excludes"}:
        matched = not matches
        matches = []
    elif operator in {"exists", "present"}:
        matched = bool(haystack.strip())
    elif operator in {"equals", "equal", "in"}:
        matched = any(_norm(haystack) == _norm(v) for v in criterion["values"])
        matches = [v for v in criterion["values"] if _norm(haystack) == _norm(v)]
    else:
        matched = bool(matches)
    evidence = []
    terms = matches or ([C.as_text(structured)] if structured is not None and structured != "" else [])
    for doc in cluster["records"]:
        evidence.extend(C.evidence_for(doc, [t for t in terms if t], limit=3))
        if evidence:
            break
    known_structured = structured is not None and criterion["field"] not in {"text", "title", "abstract", "full_text", "body", "content"}
    if not evidence and structured is not None and not isinstance(structured, (dict, list)):
        source_doc = next((d for d in cluster["records"] if criterion["field"] in d["original"]), cluster["records"][0])
        evidence = [{"term": criterion["field"], "quote": C.as_text(structured),
                     "locator": {"document_id": source_doc["doc_id"], "source_field": criterion["field"]},
                     "text_origin": "supplied_original_structured_field", "source": source_doc["source"]}]
    if not haystack.strip():
        status = "unknown"
    elif matched:
        status = "matched"
    else:
        status = "not_matched"
    return {"criterion_id": criterion["id"], "type": criterion["type"], "status": status,
            "matched_values": matches, "evidence": evidence[:6], "structured_value_known": known_structured,
            "reason_code": criterion["reason_code"]}


def _machine_suggestion(cluster: dict[str, Any], criteria: list[dict[str, Any]]) -> dict[str, Any]:
    evaluations = [_criterion_evaluation(cluster, c) for c in criteria]
    exclusions = [e for e in evaluations if e["type"] == "exclude" and e["status"] == "matched"]
    failed_include = [e for e in evaluations if e["type"] == "include" and e["status"] == "not_matched"]
    uncertain_include = [e for e in evaluations if e["type"] == "include" and e["status"] == "unknown"]
    include_criteria = [e for e in evaluations if e["type"] == "include"]
    if exclusions:
        decision = EXC
        reasons = [e.get("reason_code") or "EX-CRITERION:" + e["criterion_id"] for e in exclusions]
    elif failed_include and all(e["structured_value_known"] for e in failed_include):
        decision = EXC
        reasons = [e.get("reason_code") or "FAILED-INCLUSION:" + e["criterion_id"] for e in failed_include]
    elif include_criteria and not failed_include and not uncertain_include:
        decision = INC
        reasons = ["IN-ALL-INCLUSION-MET"]
    else:
        decision = PENDING
        reasons = ["AWAIT-EVIDENCE:" + e["criterion_id"] for e in failed_include + uncertain_include] or ["AWAIT-INCLUSION-CRITERIA"]
    return {"decision": decision, "reason_codes": reasons, "criteria_evaluation": evaluations,
            "note": "A lexical suggestion only; absence of a keyword alone is not a scientific exclusion."}


def _votes(spec: dict[str, Any], protocol: dict[str, Any], clusters: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    raw = C.first(spec, "reviewer_decisions", "annotations", "screening_decisions", "decisions", "reviews") or []
    if isinstance(raw, dict):
        raw = [dict(v, record_id=k) if isinstance(v, dict) else {"record_id": k, "decision": v} for k, v in raw.items()]
    if not isinstance(raw, list):
        return [], [{"rule": "systematic.review_shape_invalid", "severity": "high", "message": "reviewer decisions must be a list/object"}]
    record_cluster = {}
    for cluster in clusters:
        for doc in cluster["records"]:
            for identifier in [doc["doc_id"], doc.get("work_id"), doc.get("doi"), *doc["identifiers"]]:
                if identifier:
                    record_cluster[_norm(identifier)] = cluster["cluster_id"]
    votes, findings = [], []
    for i, item in enumerate(raw):
        if not isinstance(item, dict):
            continue
        record = C.first(item, "cluster_id", "record_id", "doc_id", "study_id", "work_id", "doi", "id")
        cluster_id = record_cluster.get(_norm(record), _norm(record))
        if not any(c["cluster_id"] == cluster_id for c in clusters):
            findings.append({"rule": "systematic.review_record_unknown", "severity": "high", "record_id": record})
            continue
        decision = C.as_text(C.first(item, "decision", "label", "verdict", "judgement")).lower()
        decision = {**{x: x for x in (INC, EXC, PENDING)}, "included": INC, "excluded": EXC,
                    "yes": INC, "no": EXC, "uncertain": PENDING, "awaiting": PENDING,
                    "maybe": PENDING, "full_text": INC}.get(decision, PENDING)
        stage = C.as_text(C.first(item, "stage", "screening_stage") or "title_abstract").lower()
        stage = "full_text" if any(x in stage for x in ("full", "全文")) else "title_abstract"
        declared_version = C.first(item, "criteria_version", "protocol_version")
        reasons = C.first(item, "reason_codes", "reason_code", "exclude_reason", "reason")
        if isinstance(reasons, str):
            reasons = [reasons]
        cluster = next(c for c in clusters if c["cluster_id"] == cluster_id)
        declared_evidence = C.first(item, "evidence", "quotes", "supporting_text") or []
        if isinstance(declared_evidence, (str, dict)):
            declared_evidence = [declared_evidence]
        evidence_quotes = []
        if isinstance(declared_evidence, list):
            for ev in declared_evidence:
                quote = C.first(ev, "quote", "text", "value") if isinstance(ev, dict) else ev
                evidence_quotes.append(C.as_text(quote))
        located_evidence = []
        missing_quotes = []
        for quote in evidence_quotes:
            found = []
            if quote:
                for doc in cluster["records"]:
                    found.extend(C.evidence_for(doc, [quote], limit=4))
                if not found and any(quote in C.as_text(d["original"].get(k)) for d in cluster["records"] for k in ("design", "population", "publication_status")):
                    source_doc = next(d for d in cluster["records"] if any(quote in C.as_text(d["original"].get(k)) for k in ("design", "population", "publication_status")))
                    source_field = next(k for k in ("design", "population", "publication_status") if quote in C.as_text(source_doc["original"].get(k)))
                    found = [{"term": source_field, "quote": quote,
                              "locator": {"document_id": source_doc["doc_id"], "source_field": source_field},
                              "text_origin": "supplied_original_structured_field", "source": source_doc["source"]}]
            if found:
                located_evidence.extend(found)
            else:
                missing_quotes.append(quote)
        reviewer = C.as_text(C.first(item, "reviewer", "annotator", "reviewer_id"))
        vote = {
            "cluster_id": cluster_id, "stage": stage, "decision": decision,
            "reviewer": reviewer,
            "criteria_version": C.as_text(declared_version) if declared_version else protocol["criteria_version"],
            "criteria_version_declared": declared_version is not None,
            "reason_codes": reasons if isinstance(reasons, list) else [],
            "rationale": C.first(item, "rationale", "justification", "comment"),
            "evidence_declared": evidence_quotes, "evidence": located_evidence,
            "original": item,
        }
        if missing_quotes:
            vote["invalid"] = "reviewer_evidence_unverified"
            findings.append({"rule": "systematic.reviewer_evidence_unverified", "severity": "high",
                             "record_id": record, "reviewer": vote["reviewer"], "quotes_not_found": missing_quotes})
        if not reviewer:
            vote.setdefault("invalid", "reviewer_identity_missing")
            findings.append({"rule": "systematic.reviewer_identity_missing", "severity": "high", "record_id": record})
        if not declared_version:
            findings.append({"rule": "systematic.review_version_unspecified", "severity": "medium",
                             "record_id": record, "reviewer": reviewer,
                             "note": "Vote is evaluated against the frozen protocol but its declared source version is absent; confirm before final scientific use."})
        if declared_version and C.as_text(declared_version) != protocol["criteria_version"]:
            vote["invalid"] = "criteria_version_mismatch"
            findings.append({"rule": "systematic.criteria_version_conflict", "severity": "high",
                             "record_id": record, "declared": declared_version, "current": protocol["criteria_version"],
                             "required_action": "rescreen under the frozen current criteria before synthesis"})
        if decision == EXC and not vote["reason_codes"]:
            vote.setdefault("invalid", "exclusion_reason_missing")
            findings.append({"rule": "systematic.exclusion_reason_missing", "severity": "high",
                             "record_id": record, "reviewer": vote["reviewer"], "stage": stage})
        votes.append(vote)
    return votes, findings


def _adjudications(spec: dict[str, Any], protocol: dict[str, Any], clusters: list[dict[str, Any]]) -> tuple[dict[tuple[str, str], dict[str, Any]], list[dict[str, Any]]]:
    raw = C.first(spec, "adjudications", "conflict_resolutions", "arbitrations") or []
    if not isinstance(raw, list):
        return {}, []
    out, findings = {}, []
    for item in raw:
        if not isinstance(item, dict):
            continue
        record = C.first(item, "cluster_id", "record_id", "doc_id", "study_id", "work_id", "doi", "id")
        cluster = next((c for c in clusters if c["cluster_id"] == record or any(d["doc_id"] == record for d in c["records"])), None)
        stage = C.as_text(C.first(item, "stage", "screening_stage") or "title_abstract").lower()
        stage = "full_text" if "full" in stage or "全文" in stage else "title_abstract"
        version = C.first(item, "criteria_version", "protocol_version")
        if version and C.as_text(version) != protocol["criteria_version"]:
            findings.append({"rule": "systematic.adjudication_version_conflict", "severity": "high", "record_id": record,
                             "declared": version, "current": protocol["criteria_version"]})
            continue
        decision = C.as_text(C.first(item, "decision", "verdict", "label")).lower()
        if decision not in {INC, EXC, PENDING}:
            continue
        if not C.as_text(C.first(item, "reviewer", "adjudicator", "arbitrator")):
            findings.append({"rule": "systematic.adjudicator_identity_missing", "severity": "high", "record_id": record})
            continue
        if not version:
            findings.append({"rule": "systematic.adjudication_version_unspecified", "severity": "medium", "record_id": record})
        normalized = dict(item)
        evidence = C.first(item, "evidence", "quotes", "supporting_text") or []
        if isinstance(evidence, str):
            evidence = [evidence]
        located = []
        missing = []
        if cluster and isinstance(evidence, list):
            for quote in evidence:
                if isinstance(quote, dict):
                    quote = C.first(quote, "quote", "text", "value")
                found = []
                for doc in cluster["records"]:
                    found.extend(C.evidence_for(doc, [C.as_text(quote)], limit=4))
                if not found:
                    for doc in cluster["records"]:
                        for field in ("design", "population", "publication_status"):
                            if C.as_text(quote) and C.as_text(quote) in C.as_text(doc["original"].get(field)):
                                found = [{"term": field, "quote": C.as_text(quote),
                                          "locator": {"document_id": doc["doc_id"], "source_field": field},
                                          "text_origin": "supplied_original_structured_field", "source": doc["source"]}]
                                break
                        if found:
                            break
                if found:
                    located.extend(found)
                else:
                    missing.append(C.as_text(quote))
        normalized["evidence"] = located
        if missing:
            findings.append({"rule": "systematic.adjudication_evidence_unverified", "severity": "high",
                             "record_id": record, "quotes_not_found": missing})
            continue
        if decision == EXC and not C.first(item, "reason_code", "reason", "exclude_reason"):
            findings.append({"rule": "systematic.adjudication_reason_missing", "severity": "high", "record_id": record})
        if not C.first(item, "rationale", "justification", "comment"):
            findings.append({"rule": "systematic.adjudication_rationale_missing", "severity": "high", "record_id": record})
            continue
        out[(_norm(record), stage)] = normalized
        if cluster:
            out[(cluster["cluster_id"].casefold(), stage)] = normalized
    return out, findings


def _consensus(cluster: dict[str, Any], stage: str, votes: list[dict[str, Any]],
               adjudications: dict[tuple[str, str], dict[str, Any]], dual: bool) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    valid = [v for v in votes if v["cluster_id"] == cluster["cluster_id"] and v["stage"] == stage and not v.get("invalid")]
    reviewers = {v["reviewer"] for v in valid}
    conflicts = []
    resolution = None
    adjudication_used = None
    if dual and len(reviewers) >= 2:
        decisions = {v["decision"] for v in valid}
        if len(decisions) == 1:
            final = next(iter(decisions))
            if final != PENDING:
                resolution = "independent_consensus"
            reason_sets = {tuple(sorted(v["reason_codes"])) for v in valid if v["decision"] == EXC}
            if len(reason_sets) > 1:
                conflicts.append({"rule": "systematic.reason_code_disagreement", "severity": "medium",
                                  "cluster_id": cluster["cluster_id"], "stage": stage,
                                  "note": "Same decision but different exclusion rationale; both are retained."})
        else:
            final = PENDING
            conflicts.append({"rule": "systematic.decision_disagreement", "severity": "low",
                              "cluster_id": cluster["cluster_id"], "stage": stage,
                              "decisions": {v["reviewer"]: v["decision"] for v in valid},
                              "type": "include_vs_exclude" if {INC, EXC} <= decisions else "decision_vs_uncertain"})
            keys = [(cluster["cluster_id"].casefold(), stage)] + [(r["doc_id"].casefold(), stage) for r in cluster["records"]]
            adj = next((adjudications[k] for k in keys if k in adjudications), None)
            adjudication_used = adj
            if adj:
                final = C.as_text(C.first(adj, "decision", "verdict", "label")).lower()
                resolution = "third_party_adjudication"
                if final == EXC and not C.first(adj, "reason_code", "reason", "exclude_reason"):
                    final = PENDING
                    resolution = None
                    conflicts.append({"rule": "systematic.adjudication_reason_missing", "severity": "high",
                                      "cluster_id": cluster["cluster_id"], "stage": stage})
    elif not dual and len(reviewers) >= 1:
        final = valid[0]["decision"]
        resolution = "declared_single_reviewer" if final != PENDING else None
    else:
        final = PENDING
    return {"stage": stage, "decision": final, "resolution": resolution,
            "adjudication": adjudication_used, "votes": valid,
            "requires_second_reviewer": dual and len(reviewers) < 2}, conflicts


def _screen(clusters: list[dict[str, Any]], protocol: dict[str, Any], votes: list[dict[str, Any]],
            adjudications: dict[tuple[str, str], dict[str, Any]], machine_suggestions: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    dual = protocol["review_mode"].lower() in {"dual", "dual_independent", "independent_double", "two_reviewers", "双人", "双人独立"}
    ledger, findings = [], []
    for cluster in clusters:
        ta, ta_findings = _consensus(cluster, "title_abstract", votes, adjudications, dual)
        ft, ft_findings = _consensus(cluster, "full_text", votes, adjudications, dual)
        findings.extend(ta_findings + ft_findings)
        if ta["decision"] == EXC:
            overall, final_reason = EXC, "excluded_title_abstract"
            ft_applicable = False
        elif ta["decision"] == INC:
            ft_applicable = True
            if ft["decision"] == INC:
                overall, final_reason = INC, "included_after_full_text"
            elif ft["decision"] == EXC:
                overall, final_reason = EXC, "excluded_full_text"
            else:
                overall, final_reason = PENDING, "awaiting_full_text_review"
        else:
            overall, final_reason = PENDING, "awaiting_title_abstract_review"
            ft_applicable = False
        reason_codes = [v["reason_codes"] for stage in (ta, ft) for v in stage["votes"]
                        if v["decision"] == EXC]
        deciding_stage = ta if overall == EXC and ta["decision"] == EXC else ft if overall in {EXC, INC} else None
        if deciding_stage and deciding_stage.get("adjudication"):
            adj_reason = C.first(deciding_stage["adjudication"], "reason_codes", "reason_code", "reason", "exclude_reason")
            if adj_reason:
                reason_codes.append(adj_reason if isinstance(adj_reason, list) else [adj_reason])
        final_evidence = []
        if deciding_stage:
            for vote in deciding_stage["votes"]:
                final_evidence.extend(vote.get("evidence") or [])
            if deciding_stage.get("adjudication"):
                final_evidence.extend(deciding_stage["adjudication"].get("evidence") or [])
            if not final_evidence:
                final_evidence = [ev for row in machine_suggestions[cluster["cluster_id"]]["criteria_evaluation"] for ev in row["evidence"]]
        ledger.append({"cluster_id": cluster["cluster_id"], "record_ids": cluster["record_ids"],
                       "title": cluster["title"], "metadata": cluster["metadata"], "sources": cluster["sources"],
                       "versions": cluster["versions"], "final_decision": overall, "final_reason": final_reason,
                       "exclusion_reason_codes": [x for pair in reason_codes for x in pair],
                       "final_evidence": final_evidence,
                       "title_abstract": ta, "full_text": {**ft, "applicable": ft_applicable},
                       "machine_suggestion": machine_suggestions[cluster["cluster_id"]],
                       "human_confirmation_required": resolution_is_not_human(ta, ft, overall)})
    return ledger, findings


def resolution_is_not_human(ta, ft, overall):
    if overall == INC:
        return ta.get("resolution") is None or ft.get("resolution") is None
    if overall == EXC:
        return ta.get("resolution") is None and ft.get("resolution") is None
    return True


def _agreement(votes: list[dict[str, Any]], stage: str) -> dict[str, Any]:
    by_cluster = {}
    for vote in votes:
        if vote["stage"] != stage or vote.get("invalid"):
            continue
        by_cluster.setdefault(vote["cluster_id"], {})[vote["reviewer"]] = vote["decision"]
    pairs = []
    for cluster, reviewers in sorted(by_cluster.items()):
        if len(reviewers) >= 2:
            names = sorted(reviewers)[:2]  # Agreement statistic is explicitly the first two declared reviewers.
            pairs.append((cluster, reviewers[names[0]], reviewers[names[1]]))
    if not pairs:
        return {"paired_records": 0, "agreements": 0, "agreement_rate": None, "cohens_kappa": None,
                "note": "No two independent human votes; agreement is not estimated."}
    agree = sum(a == b for _, a, b in pairs)
    observed = agree / len(pairs)
    categories = {INC, EXC, PENDING}
    pa = {c: sum(a == c for _, a, _ in pairs) / len(pairs) for c in categories}
    pb = {c: sum(b == c for _, _, b in pairs) / len(pairs) for c in categories}
    expected = sum(pa[c] * pb[c] for c in categories)
    kappa = (observed - expected) / (1 - expected) if expected != 1 else None
    return {"paired_records": len(pairs), "agreements": agree, "agreement_rate": observed,
            "cohens_kappa": kappa, "note": "Descriptive input votes only; no reviewers are fabricated."}


def _flow(ledger: list[dict[str, Any]], raw_count: int, merge_log: list[dict[str, Any]], invalid_count: int) -> dict[str, Any]:
    duplicates = sum(x["kind"] == "duplicate_removed" for x in merge_log)
    versions = sum(x["kind"] == "version_linked" for x in merge_log)
    screened = len(ledger)
    ta_excluded = sum(x["title_abstract"]["decision"] == EXC for x in ledger)
    ta_pending = sum(x["title_abstract"]["decision"] == PENDING for x in ledger)
    advanced = [x for x in ledger if x["title_abstract"]["decision"] == INC]
    ft_excluded = sum(x["title_abstract"]["decision"] == INC and x["full_text"]["decision"] == EXC for x in ledger)
    ft_pending = sum(x["title_abstract"]["decision"] == INC and x["full_text"]["decision"] == PENDING for x in ledger)
    ft_included = sum(x["final_decision"] == INC for x in ledger)
    identification = raw_count == invalid_count + duplicates + versions + screened
    ta_close = screened == ta_excluded + len(advanced) + ta_pending
    ft_close = len(advanced) == ft_excluded + ft_pending + ft_included
    return {
        "identification": {"raw_records": raw_count, "invalid_records_named": invalid_count,
                           "duplicates_removed": duplicates, "other_versions_linked": versions,
                           "unique_work_clusters": screened,
                           "equation": "raw = invalid + duplicates + linked_versions + unique_clusters",
                           "closure_holds": identification},
        "title_abstract": {"screened": screened, "excluded": ta_excluded,
                           "advanced_to_full_text": len(advanced), "pending": ta_pending,
                           "equation": "screened = excluded + advanced + pending", "closure_holds": ta_close},
        "full_text": {"assessed": len(advanced), "excluded": ft_excluded, "included": ft_included,
                      "pending": ft_pending, "equation": "assessed = excluded + included + pending",
                      "closure_holds": ft_close},
        "overall": {"included": ft_included, "excluded": ta_excluded + ft_excluded,
                    "pending": ta_pending + ft_pending,
                    "process_complete": (ta_pending + ft_pending) == 0,
                    "all_count_closures_hold": identification and ta_close and ft_close},
        "prisma_note": "Counts are work-cluster counts after record/version consolidation. Pending decisions remain explicit; they are never coerced into included or excluded to force closure.",
    }


def analyze(spec: dict[str, Any], case_dir: Path) -> dict[str, Any]:
    protocol = _protocol(spec)
    raw_docs, sources = C.load_document_records(spec, case_dir)
    docs, omissions = C.normalize_documents(raw_docs, sources)
    if not docs:
        raise C.MaterialError("systematic.no_records", "no usable bibliographic records were supplied")
    clusters, merge_log, conflicts = _deduplicate(docs)
    votes, vote_findings = _votes(spec, protocol, clusters)
    adjudications, adjudication_findings = _adjudications(spec, protocol, clusters)
    suggestions = {c["cluster_id"]: _machine_suggestion(c, protocol["criteria"]) for c in clusters}
    ledger, screen_findings = _screen(clusters, protocol, votes, adjudications, suggestions)
    findings = [{**c, "severity": "high"} for c in conflicts] + vote_findings + adjudication_findings + screen_findings
    incomplete_searches = [q["query_id"] for q in protocol["searches"]
                           if not q["database"] or not q["query_string"] or not q["date_searched"] or not q["fields"]]
    if not protocol["searches"]:
        findings.append({"rule": "systematic.search_protocol_missing", "severity": "medium",
                         "message": "No source/query/date protocol was supplied; only the screening subset is replayable."})
    elif incomplete_searches:
        findings.append({"rule": "systematic.search_protocol_incomplete", "severity": "medium",
                         "query_ids": incomplete_searches,
                         "required": ["database", "query_string", "fields", "date_searched"]})
    if omissions:
        findings.append({"rule": "systematic.records_omitted", "severity": "medium", "entries": omissions})
    flow = _flow(ledger, len(raw_docs), merge_log, len(omissions))
    if not flow["overall"]["all_count_closures_hold"]:
        findings.append({"rule": "systematic.count_not_closed", "severity": "high", "flow": flow})
    if flow["overall"]["pending"]:
        findings.append({"rule": "systematic.review_pending", "severity": "medium",
                         "pending": flow["overall"]["pending"],
                         "message": "Pending human decisions remain; process is auditable but not complete."})
    if merge_log:
        findings.append({"rule": "systematic.records_consolidated", "severity": "low", "entries": merge_log})
    if not votes:
        findings.append({"rule": "systematic.human_review_absent", "severity": "medium",
                         "message": "Only machine suggestions are available; no dual independent screening is claimed."})
    status = "review" if any(f.get("severity") in {"high", "medium"} for f in findings) else "clean"
    potential_old = [v for v in votes if v.get("invalid") == "criteria_version_mismatch"]
    changes = [{"operation": "freeze_protocol", "protocol_sha256": protocol["protocol_sha256"],
                "criteria_version": protocol["criteria_version"]},
               {"operation": "consolidate_records", "input_records": len(raw_docs),
                "unique_work_clusters": len(clusters), "merge_log": merge_log},
               {"operation": "screen_frozen_version", "criteria_version": protocol["criteria_version"],
                "old_version_votes_requiring_rescreen": len(potential_old)}]
    return {
        "schema_version": SCHEMA_VERSION, "status": status, "protocol": protocol,
        "search_protocol": {"databases_and_queries": protocol["searches"],
                            "deduplication": {"method": "DOI/PMID exact; explicit work/version links; DOI-missing title+first_author+year exact only",
                                              "records_input": len(raw_docs), "unique_work_clusters": len(clusters),
                                              "merge_log": merge_log},
                            "selection_process": protocol["review_mode"],
                            "reporting_reference": "PRISMA-S-style database/query/field/date/limit logs and explicit management of records; no live search claimed."},
        "protocol_sha256": protocol["protocol_sha256"], "criteria_version": protocol["criteria_version"],
        "screening_decisions": ledger, "included_records": [x for x in ledger if x["final_decision"] == INC],
        "excluded_records": [x for x in ledger if x["final_decision"] == EXC],
        "pending_records": [x for x in ledger if x["final_decision"] == PENDING],
        "reviewer_agreement": {"title_abstract": _agreement(votes, "title_abstract"),
                               "full_text": _agreement(votes, "full_text")},
        "flow_counts": flow, "prisma_flow": flow,
        "prisma_counts_closed": flow["overall"]["all_count_closures_hold"],
        "documents_indexed": len(docs), "unique_work_clusters": len(clusters),
        "candidate_set": [{"cluster_id": c["cluster_id"], "record_ids": c["record_ids"], "title": c["title"],
                           "metadata": c["metadata"], "sources": c["sources"], "versions": c["versions"]} for c in clusters],
        "findings": findings, "limits": ["Local finite records only; search strings are replay specifications, not newly executed remote searches.",
                                               "Automatic lexical suggestions never replace final human scientific decisions.",
                                               "Records awaiting review are not counted as final inclusions or exclusions."],
        "uncertainty": (["Some decisions await independent review or adjudication."] if flow["overall"]["pending"] else [])
                       + ["Title/abstract evidence cannot establish full-text eligibility when full text is unavailable."],
        "sources": [d["source"] | {"record_id": d["doc_id"]} for d in docs],
        "change_records": changes, "omissions": omissions,
        "independent_recompute": {"identification_raw_minus_removed": len(raw_docs) - len(omissions) - len(merge_log),
                                  "unique_clusters_recounted": len(clusters),
                                  "title_abstract_sum": flow["title_abstract"]["excluded"] + flow["title_abstract"]["advanced_to_full_text"] + flow["title_abstract"]["pending"],
                                  "full_text_sum": flow["full_text"]["excluded"] + flow["full_text"]["included"] + flow["full_text"]["pending"],
                                  "expected_all_closures": True},
    }


def attach_rubric(result: dict[str, Any]) -> dict[str, Any]:
    result["检索结果"] = {"候选文献": result["candidate_set"], "排序/筛选结果": result["screening_decisions"],
                         "纳入文献": result["included_records"], "排除文献": result["excluded_records"],
                         "待复核": result["pending_records"], "元数据": [c["metadata"] for c in result["candidate_set"]],
                         "来源定位": result["sources"], "流程计数": result["flow_counts"]}
    result["证据记录"] = {"检索协议": result["search_protocol"], "标准版本": result["criteria_version"],
                         "去重依据": result["search_protocol"]["deduplication"],
                         "逐条判定": result["screening_decisions"], "双人一致性": result["reviewer_agreement"],
                         "变更日志": result["change_records"], "复算入口": result["independent_recompute"]}
    result["状态说明"] = C.status_block(
        result["status"], [x["cluster_id"] for x in result["included_records"]],
        [{"cluster_id": x["cluster_id"], "reason": x["final_reason"]} for x in result["pending_records"]],
        [] if result["candidate_set"] else ["candidate_set"],
        [f for f in result["findings"] if "conflict" in f["rule"] or "disagreement" in f["rule"]],
        result["omissions"], result["uncertainty"])
    result["运行状态"] = result["status"]
    result["evidence_ledger"] = [{"cluster_id": x["cluster_id"], "title_abstract": x["title_abstract"],
                                  "full_text": x["full_text"], "machine_suggestion": x["machine_suggestion"]}
                                 for x in result["screening_decisions"]]
    return result
