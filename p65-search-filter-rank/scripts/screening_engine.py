"""Explainable title/abstract triage, dedup, ranking and human-review ledger."""
from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
from typing import Any

import retrieval_common as C

SCHEMA_VERSION = "screening-rank/v2"
ALLOWED_FIELDS = {"title", "abstract", "keywords", "body"}
DECISION_MAP = {"include": "include", "included": "include", "keep": "include", "yes": "include", "1": "include",
                "relevant": "include", "保留": "include", "纳入": "include", "核心": "include",
                "exclude": "exclude", "excluded": "exclude", "no": "exclude", "0": "exclude",
                "排除": "exclude", "不相关": "exclude", "pending": "pending", "maybe": "pending",
                "undetermined": "pending", "待定": "pending", "待复核": "pending"}


def _protocol_source(spec: dict[str, Any]) -> tuple[dict[str, Any], bool]:
    if isinstance(spec.get("screening_protocol"), dict):
        return spec["screening_protocol"], True
    if isinstance(spec.get("screening_criteria"), dict):
        return spec["screening_criteria"], True
    if any(k in spec for k in ("inclusion_criteria", "exclusion_criteria", "include_criteria", "exclude_criteria")):
        return spec, True
    return {}, False


def _criterion_groups(raw: dict[str, Any], cid: str) -> list[dict[str, Any]]:
    groups = []
    if isinstance(raw.get("groups"), list):
        for i, group in enumerate(raw["groups"], 1):
            if isinstance(group, str):
                group = {"terms": [group]}
            if isinstance(group, dict):
                groups.extend(_criterion_groups(group, f"{cid}-G{i:02d}"))
    all_terms = raw.get("all")
    all_values = all_terms if isinstance(all_terms, list) else ([all_terms] if all_terms is not None else [])
    for i, term in enumerate(all_values, 1):
        if str(term).strip():
            groups.append({"group_id": f"{cid}-ALL{i:02d}", "label": f"required term {i}", "terms": [str(term)]})
    any_values = raw.get("any")
    if any_values is not None:
        values = any_values if isinstance(any_values, list) else [any_values]
        terms = [str(x).strip() for x in values if str(x).strip()]
        if terms:
            groups.append({"group_id": f"{cid}-ANY", "label": "any alternative", "terms": terms})
    raw_terms = raw.get("terms", raw.get("keywords"))
    if isinstance(raw_terms, dict):
        values = []
        for value in raw_terms.values():
            values.extend(value if isinstance(value, list) else [value])
        raw_terms = values
    if raw_terms is not None:
        values = raw_terms if isinstance(raw_terms, list) else [raw_terms]
        terms = [str(x).strip() for x in values if str(x).strip()]
        if terms:
            groups.append({"group_id": f"{cid}-TERMS", "label": "case supplied alternative terms", "terms": terms})
    synonyms = raw.get("synonyms")
    if synonyms is not None:
        values = synonyms if isinstance(synonyms, list) else [synonyms]
        terms = [str(x).strip() for x in values if str(x).strip()]
        if groups and terms:
            groups[-1]["terms"] = list(dict.fromkeys(groups[-1]["terms"] + terms))
        elif terms:
            groups.append({"group_id": f"{cid}-SYN", "label": "declared synonyms", "terms": terms})
    return groups


def normalize_criterion(raw: Any, index: int, kind: str) -> dict[str, Any]:
    if isinstance(raw, str):
        raw = {"id": f"INC-{index:02d}" if kind == "include" else f"EX-{index:02d}",
               "description": raw, "terms": [raw]}
    if not isinstance(raw, dict):
        raise C.RetrievalError("screening.criterion_invalid", f"criterion {index} must be an object or string", 4)
    cid = str(raw.get("id") or raw.get("criterion_id") or raw.get("code")
              or (f"INC-{index:02d}" if kind == "include" else f"EX-{index:02d}"))
    actual_kind = str(raw.get("kind", raw.get("type", kind))).casefold()
    aliases = {"inclusion": "include", "inclusion_criteria": "include", "include": "include",
               "exclusion": "exclude", "exclusion_criteria": "exclude", "exclude": "exclude"}
    if actual_kind not in aliases:
        raise C.RetrievalError("screening.criterion_kind_invalid", f"criterion {cid} has unsupported kind {actual_kind}", 4)
    kind = aliases[actual_kind]
    fields = raw.get("fields", ["title", "abstract"])
    if isinstance(fields, str):
        fields = [fields]
    if not isinstance(fields, list) or not fields or any(field not in ALLOWED_FIELDS for field in fields):
        raise C.RetrievalError("screening.criterion_fields_invalid", f"criterion {cid} has unsupported fields {fields}", 4)
    groups = _criterion_groups(raw, cid)
    if not groups:
        fallback = raw.get("description", raw.get("label", raw.get("name", "")))
        if str(fallback).strip():
            groups = [{"group_id": cid + "-TEXT", "label": "literal criterion text", "terms": [str(fallback)]}]
    if not groups:
        raise C.RetrievalError("screening.criterion_empty", f"criterion {cid} has no executable terms", 4)
    minimum = raw.get("minimum_should_match", raw.get("min_groups", len(groups)))
    try:
        minimum = int(minimum)
    except (TypeError, ValueError):
        raise C.RetrievalError("screening.minimum_match_invalid", f"criterion {cid} minimum_should_match is not an integer", 4)
    if minimum < 1 or minimum > len(groups):
        raise C.RetrievalError("screening.minimum_match_invalid",
                               f"criterion {cid} minimum_should_match must be 1..{len(groups)}", 4)
    return {"criterion_id": cid, "kind": kind, "description": str(raw.get("description", raw.get("label", raw.get("name", cid)))),
            "required": raw.get("required", kind == "include") is not False, "fields": list(fields),
            "groups": groups, "minimum_should_match": minimum,
            "priority": raw.get("priority", 100 if kind == "exclude" else 50),
            "provenance": raw.get("provenance", "case_supplied_screening_protocol")}


def normalize_protocol(spec: dict[str, Any]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    raw, explicit = _protocol_source(spec)
    inclusion = raw.get("inclusion_criteria", raw.get("include_criteria", raw.get("inclusion", [])))
    exclusion = raw.get("exclusion_criteria", raw.get("exclude_criteria", raw.get("exclusion", [])))
    inclusion = inclusion if isinstance(inclusion, list) else [inclusion] if inclusion else []
    exclusion = exclusion if isinstance(exclusion, list) else [exclusion] if exclusion else []
    criteria = [normalize_criterion(item, i + 1, "include") for i, item in enumerate(inclusion)] + [
        normalize_criterion(item, i + 1, "exclude") for i, item in enumerate(exclusion)]
    origin = "explicit_case_supplied" if criteria else "derived_lexical_requires_recall_review"
    if not criteria:
        question = C.research_question_text(spec)
        concepts = C.derive_concepts(spec, question)
        for item in concepts:
            criteria.append({"criterion_id": "DERIVED-" + item["concept_id"], "kind": "include",
                             "description": item["label"], "required": item.get("required", True) is not False,
                             "fields": ["title", "abstract"],
                             "groups": [{"group_id": "DERIVED-" + item["concept_id"] + "-G",
                                         "label": item["role"], "terms": item["all_terms"]}],
                             "minimum_should_match": 1, "priority": 50,
                             "provenance": item.get("provenance", "derived_from_question")})
    if not criteria:
        raise C.RetrievalError("screening.protocol_missing",
                               "no executable inclusion criteria, research concepts or screening protocol was supplied", 4)
    ids = [criterion["criterion_id"] for criterion in criteria]
    if len(set(ids)) != len(ids):
        raise C.RetrievalError("screening.criterion_id_duplicate", "criterion ids must be unique", 4)
    policy = str(raw.get("criterion_priority", raw.get("conflict_policy", "exclusion_wins")))
    normalized_policy = "manual_review" if any(x in policy.casefold() for x in ("manual", "人工", "review")) else "exclusion_wins"
    thresholds = raw.get("human_review_thresholds", raw.get("review_thresholds", {}))
    if not isinstance(thresholds, dict):
        raise C.RetrievalError("screening.thresholds_invalid", "human_review_thresholds must be an object", 4)
    confidence = thresholds.get("confidence_below", raw.get("human_review_confidence_below", 0.70))
    tie_margin = thresholds.get("tie_margin", raw.get("ranking_tie_margin", 2.0))
    try:
        confidence, tie_margin = float(confidence), float(tie_margin)
        if not 0 <= confidence <= 1 or tie_margin < 0:
            raise ValueError
    except (TypeError, ValueError):
        raise C.RetrievalError("screening.thresholds_invalid",
                               "confidence_below must be in [0,1] and tie_margin must be non-negative", 4)
    weights = raw.get("ranking_weights", {"relevance": 0.70, "criteria_coverage": 0.20,
                                           "metadata_completeness": 0.05, "source_trace": 0.05})
    required_weights = {"relevance", "criteria_coverage", "metadata_completeness", "source_trace"}
    if not isinstance(weights, dict) or set(weights) != required_weights:
        raise C.RetrievalError("screening.rank_weights_invalid", f"ranking_weights must contain exactly {sorted(required_weights)}", 4)
    try:
        weights = {key: float(value) for key, value in weights.items()}
        if any(value < 0 for value in weights.values()) or abs(sum(weights.values()) - 1) > 1e-9:
            raise ValueError
    except (TypeError, ValueError):
        raise C.RetrievalError("screening.rank_weights_invalid", "ranking weights must be non-negative and sum to 1", 4)
    protocol = {"origin": origin, "criteria": criteria, "criterion_priority": normalized_policy,
                "declared_priority_text": policy,
                "derived_missing_required_policy": "pending" if origin.startswith("derived") else "exclude_with_explicit_reason",
                "human_review_thresholds": {"confidence_below": confidence, "tie_margin": tie_margin},
                "ranking_weights": weights,
                "ranking_formula": "100 * (w_relevance*BM25_normalized + w_coverage*required_criteria_coverage + w_metadata*metadata_completeness + w_source*source_trace_quality); eligibility gate evaluated first",
                "ranking_scope": ["title", "abstract", "keywords"], "tie_rule": "exact score ties: normalized title, then DOI, then work_id",
                "stage": "title_abstract_screening_not_fulltext_systematic_review",
                "dedup_rule": "exact DOI/normalized title groups; all source rows retained; version conflicts are pending",
                "source_scope": C.temporal_scope(spec)}
    return protocol, criteria


def evaluate_criterion(work: dict[str, Any], criterion: dict[str, Any]) -> dict[str, Any]:
    selected_fields = {field: work["fields"].get(field, "") for field in criterion["fields"]}
    groups = []
    evidence = []
    for group in criterion["groups"]:
        aliases = C.matched_terms(group["terms"], selected_fields)
        for alias in aliases:
            for field, text in selected_fields.items():
                if not C.field_term_match(text, alias):
                    continue
                fake_score = {"term_field_scores": [{"term": alias, "field": field}]}
                for item in C.score_evidence(work, fake_score, limit=1):
                    evidence.append({"criterion_id": criterion["criterion_id"], "group_id": group["group_id"], **item})
        matched = bool(aliases)
        groups.append({"group_id": group["group_id"], "label": group["label"], "terms": group["terms"],
                       "matched_terms": aliases, "matched": matched,
                       "field_evidence": [e for e in evidence if e["group_id"] == group["group_id"]]})
    matched_groups = sum(group["matched"] for group in groups)
    matched = matched_groups >= criterion["minimum_should_match"]
    return {"criterion_id": criterion["criterion_id"], "kind": criterion["kind"], "required": criterion["required"],
            "matched": matched, "matched_groups": matched_groups, "total_groups": len(groups),
            "coverage": round(matched_groups / len(groups), 8), "groups": groups, "evidence": evidence,
            "reason": criterion["description"]}


def initial_decision(work: dict[str, Any], protocol: dict[str, Any], matches: list[dict[str, Any]],
                     criteria: list[dict[str, Any]]) -> dict[str, Any]:
    match_by_id = {m["criterion_id"]: m for m in matches}
    exclusions = [m for m in matches if m["kind"] == "exclude" and m["matched"]]
    required = [c for c in criteria if c["kind"] == "include" and c["required"]]
    matched_required = [c for c in required if match_by_id[c["criterion_id"]]["matched"]]
    missed_required = [c for c in required if not match_by_id[c["criterion_id"]]["matched"]]
    optional = [c for c in criteria if c["kind"] == "include" and not c["required"]]
    any_optional = any(match_by_id[c["criterion_id"]]["matched"] for c in optional)
    title = work["fields"].get("title", "").strip()
    abstract = work["fields"].get("abstract", "").strip()
    enough_text = bool(title or abstract)
    if work.get("access_blocked"):
        return {"decision": "pending", "reason_code": "ACCESS-RESTRICTED", "reason_codes": ["ACCESS-RESTRICTED"],
                "reason": "Access-restricted text was not indexed; cannot confirm eligibility.", "relevance_class": "indeterminate",
                "required_criteria": required, "missed_required": missed_required, "criterion_conflict": False}
    passed, boundary_reason = C.temporal_match(work, protocol["source_scope"])
    if not passed:
        missing = str(boundary_reason).startswith("missing")
        code = "MISSING-BOUNDARY-METADATA" if missing else "EX-BOUNDARY"
        return {"decision": "pending" if missing else "exclude", "reason_code": code, "reason_codes": [code],
                "reason": boundary_reason, "relevance_class": "indeterminate" if missing else "unrelated",
                "required_criteria": required, "missed_required": missed_required, "criterion_conflict": False}
    if exclusions and (matched_required or any_optional) and protocol["criterion_priority"] == "manual_review":
        ids = [m["criterion_id"] for m in exclusions] + [c["criterion_id"] for c in missed_required]
        return {"decision": "pending", "reason_code": "CRITERION-CONFLICT", "reason_codes": ids,
                "reason": "Exclusion evidence and unmet inclusion conditions coexist under manual-review priority.",
                "relevance_class": "indeterminate", "required_criteria": required, "missed_required": missed_required,
                "criterion_conflict": True}
    if exclusions:
        ids = [m["criterion_id"] for m in exclusions]
        return {"decision": "exclude", "reason_code": "EX:" + ",".join(ids), "reason_codes": ids,
                "reason": "Matched explicit exclusion criterion/criteria; exclusion wins under frozen priority.",
                "relevance_class": "unrelated", "required_criteria": required, "missed_required": missed_required,
                "criterion_conflict": bool(missed_required)}
    if not enough_text:
        return {"decision": "pending", "reason_code": "INSUFFICIENT-TEXT", "reason_codes": ["INSUFFICIENT-TEXT"],
                "reason": "Neither title nor abstract was supplied; lexical absence is not automatic exclusion.",
                "relevance_class": "indeterminate", "required_criteria": required, "missed_required": missed_required,
                "criterion_conflict": False}
    if missed_required:
        ids = [c["criterion_id"] for c in missed_required]
        explicit = protocol["origin"] == "explicit_case_supplied"
        return {"decision": "exclude" if explicit else "pending",
                "reason_code": "EX-MISSING" if explicit else "UNCLEAR", "reason_codes": ids,
                "reason": ("Required criterion not found in declared title/abstract fields under an explicit frozen protocol."
                           if explicit else "Derived lexical criterion was not found; with no human-approved protocol this becomes pending, not automatic exclusion."),
                "relevance_class": "unrelated" if explicit else "indeterminate",
                "required_criteria": required, "missed_required": missed_required, "criterion_conflict": False}
    if required and len(matched_required) == len(required) or not required and any_optional:
        return {"decision": "include", "reason_code": "INC-ALL-REQUIRED", "reason_codes": [c["criterion_id"] for c in required],
                "reason": "All required title/abstract inclusion criteria matched and no priority exclusion matched.",
                "relevance_class": "directly_relevant", "required_criteria": required, "missed_required": [],
                "criterion_conflict": False}
    return {"decision": "pending", "reason_code": "NO-INCLUSION-EVIDENCE", "reason_codes": ["NO-INCLUSION-EVIDENCE"],
            "reason": "No required or optional positive inclusion evidence was found.", "relevance_class": "indeterminate",
            "required_criteria": required, "missed_required": [], "criterion_conflict": False}


def supplied_reviews(spec: dict[str, Any]) -> list[dict[str, Any]]:
    value = None
    for key in ("review_decisions", "human_reviews", "manual_decisions", "adjudications", "screening_reviews"):
        if key in spec:
            value = spec[key]
            break
    if value is None:
        return []
    if isinstance(value, dict):
        value = [dict(v, record_id=k) if isinstance(v, dict) else {"decision": v, "record_id": k} for k, v in value.items()]
    if not isinstance(value, list):
        raise C.RetrievalError("screening.reviews_invalid", "review decisions must be a list or record-id mapping", 4)
    return copy.deepcopy(value)


def apply_reviews(work_rows: list[dict[str, Any]], spec: dict[str, Any], result: dict[str, Any]) -> list[dict[str, Any]]:
    by_raw_id: dict[str, list[dict[str, Any]]] = {}
    by_work: dict[str, list[dict[str, Any]]] = {}
    for row in work_rows:
        for member_id in row.get("member_ids", [row["record_id"]]):
            by_raw_id.setdefault(member_id, []).append(row)
        by_work.setdefault(row["work_id"], []).append(row)
    history = []
    for i, review in enumerate(supplied_reviews(spec), 1):
        if not isinstance(review, dict):
            C.finding(result, "screening.review_invalid", "medium", f"review {i} is not an object")
            continue
        rid = str(review.get("record_id", review.get("doc_id", review.get("work_id", ""))))
        reviewer = str(review.get("reviewer", review.get("user_id", ""))).strip()
        reason = str(review.get("rationale", review.get("reason", review.get("note", "")))).strip()
        decision = DECISION_MAP.get(str(review.get("decision", review.get("label", ""))).casefold())
        targets = by_raw_id.get(rid, []) if rid in by_raw_id else by_work.get(rid, [])
        if not targets or not reviewer or not reason or decision is None:
            C.finding(result, "screening.review_invalid", "medium",
                      f"review {i} lacks a known target, reviewer, rationale or valid include/pending/exclude decision",
                      supplied_record_id=rid)
            continue
        is_adjudicator = review.get("adjudication") is True or str(review.get("role", "")).casefold() == "adjudicator"
        for target in targets:
            history_record_id = rid if rid in target.get("member_ids", []) else target["record_id"]
            history_entry = {"record_id": history_record_id, "work_id": target["work_id"],
                             "label": 1 if decision == "include" else 0 if decision == "exclude" else None,
                             "decision": decision, "classifier": "fielded-bm25-protocol-v2",
                             "querier": "confidence_threshold_plus_tie_margin", "balancer": None,
                             "feature_extractor": "title_abstract_keywords_bm25_and_criteria",
                             "training_set": None, "time": review.get("time"), "note": reason,
                             "tags": ["title_abstract", "human_declared"], "user_id": reviewer,
                             "adjudication": is_adjudicator}
            history.append(history_entry)
            target.setdefault("human_history", []).append(history_entry)
    # Same-work groups must share a final label.  Conflicting labels remain pending
    # unless an explicit adjudicator resolves them.
    for work_id, rows in by_work.items():
        votes = [entry for row in rows for entry in row.get("human_history", [])]
        if not votes:
            continue
        adjudications = [entry for entry in votes if entry["adjudication"]]
        labels = {entry["decision"] for entry in votes}
        if adjudications:
            if len({entry["decision"] for entry in adjudications}) == 1:
                final, resolution = adjudications[-1]["decision"], "adjudicated_by_declared_reviewer"
            else:
                final, resolution = "pending", "conflicting_adjudications"
        elif len(labels) == 1:
            final, resolution = next(iter(labels)), "consistent_declared_human_review"
        else:
            final, resolution = "pending", "unresolved_human_label_conflict"
        for row in rows:
            before = row["final_decision"]
            if final == "pending" or resolution in {"conflicting_adjudications", "unresolved_human_label_conflict"}:
                C.finding(result, "screening.human_label_conflict", "medium",
                          f"work {work_id} has unresolved human labels", work_id=work_id)
            row["final_decision"] = final
            row["review_resolution"] = resolution
            row.setdefault("change_records", []).append({"operation": "apply_declared_human_review",
                "engine_decision": row["engine_decision"], "before": before, "after": final,
                "reviewer_ids": sorted({entry["user_id"] for entry in row.get("human_history", [])}),
                "rationale": [entry["note"] for entry in row.get("human_history", [])]})
    return history


def build_result(case: dict[str, Any], case_dir: Path) -> dict[str, Any]:
    spec = C.merged_spec(case)
    records = C.load_records(spec, case_dir)
    works, duplicate_audit, version_conflicts = C.deduplicate(records)
    protocol, criteria = normalize_protocol(spec)
    works_by_id = {work["work_id"]: work for work in works}
    rank_works = []
    for work in works:
        clone = copy.deepcopy(work)
        clone["fields"] = {"title": work["fields"].get("title", ""), "abstract": work["fields"].get("abstract", ""),
                           "keywords": work["fields"].get("keywords", ""), "body": ""}
        rank_works.append(clone)
    index = C.BM25Index(rank_works)
    all_terms = list(dict.fromkeys(term for criterion in criteria for group in criterion["groups"] for term in group["terms"]))
    required = [criterion for criterion in criteria if criterion["kind"] == "include" and criterion["required"]]
    conflict_by_work = {item["work_id"]: item for item in version_conflicts}
    rows = []
    result: dict[str, Any] = {"schema_version": SCHEMA_VERSION, "status": "clean", "case_id": case.get("case_id"),
                              "findings": [], "limits": [], "uncertainty": []}
    for work in works:
        criteria_matches = [evaluate_criterion(work, criterion) for criterion in criteria]
        decision = initial_decision(work, protocol, criteria_matches, criteria)
        matched = C.matched_terms(all_terms, {k: work["fields"].get(k, "") for k in ("title", "abstract", "keywords")})
        score = index.score(work["work_id"], matched) if matched else {"bm25": 0.0, "normalized_relevance": 0.0,
                    "matched_terms": [], "field_components": {"title": 0.0, "abstract": 0.0, "keywords": 0.0, "body": 0.0},
                    "term_field_scores": [], "parameters": {"k1": 1.2, "b": 0.75}}
        required_coverage = (len(required) - len(decision["missed_required"])) / len(required) if required else (
            1.0 if decision["decision"] == "include" else 0.0)
        weights = protocol["ranking_weights"]
        components = {"relevance": score["normalized_relevance"], "criteria_coverage": round(required_coverage, 8),
                      "metadata_completeness": work["metadata_completeness"]["score"],
                      "source_trace": work["source_quality"]["score"]}
        weighted = {key: round(100 * weights[key] * components[key], 8) for key in weights}
        priority = round(sum(weighted.values()), 8)
        confidence = 0.95 if decision["decision"] == "include" else 0.60 if decision["decision"] == "pending" else 0.90
        if not work["fields"].get("abstract"):
            confidence = min(confidence, 0.55)
        if decision["missed_required"]:
            confidence = min(confidence, 0.55)
        if decision["decision"] == "exclude":
            confidence = min(confidence, 0.85)
        version_conflict = conflict_by_work.get(work["work_id"])
        if version_conflict and decision["decision"] != "exclude":
            confidence = min(confidence, 0.35)
            decision["decision"] = "pending"
            decision["reason_code"] = "VERSION-CONFLICT"
            decision["reason_codes"] = list(dict.fromkeys(decision["reason_codes"] + ["VERSION-CONFLICT"]))
            decision["reason"] += " Same-work version/metadata conflicts require human review."
            decision["relevance_class"] = "indeterminate"
        if decision["criterion_conflict"]:
            confidence = min(confidence, 0.30)
        threshold = protocol["human_review_thresholds"]
        review_reasons = []
        if decision["decision"] == "pending":
            review_reasons.append("pending eligibility or unresolved criterion evidence")
        if confidence < threshold["confidence_below"]:
            review_reasons.append(f"decision confidence {confidence:.2f} is below frozen threshold {threshold['confidence_below']:.2f}")
        if version_conflict:
            review_reasons.append("preprint/formal/source metadata conflict")
        if any(field in {"title", "abstract", "year"} for field in work["metadata_completeness"]["missing_fields"]):
            review_reasons.append("title/abstract/year missing or incomplete")
        rows.append({**C.public_candidate(work, score), "engine_decision": decision["decision"],
                     "final_decision": decision["decision"], "relevance_class": decision["relevance_class"],
                     "reason_code": decision["reason_code"], "reason_codes": decision["reason_codes"],
                     "reason": decision["reason"], "criteria_matches": criteria_matches,
                     "criterion_conflict": decision["criterion_conflict"],
                     "score_components": components, "weighted_components": weighted, "priority_score": priority,
                     "decision_confidence": round(confidence, 6),
                     "confidence_note": "Deterministic rule-based triage confidence, not calibrated probability.",
                     "review_reasons": review_reasons, "needs_human_review": bool(review_reasons),
                     "near_tie_with": [], "exact_tie_with": [], "version_conflicts": [version_conflict] if version_conflict else [],
                     "human_history": [], "review_resolution": None, "change_records": []})
    # Rank first and apply frozen tie/near-tie rules before any human override.
    eligible = [row for row in rows if row["engine_decision"] != "exclude"]
    eligible.sort(key=lambda row: (-row["priority_score"], C.normalize_title(row["metadata"].get("title")),
                                   row["metadata"].get("doi") or "", row["work_id"]))
    for i, row in enumerate(eligible):
        if i > 0:
            gap = eligible[i - 1]["priority_score"] - row["priority_score"]
            if gap == 0:
                row["exact_tie_with"].append(eligible[i - 1]["work_id"])
                eligible[i - 1]["exact_tie_with"].append(row["work_id"])
            if gap <= protocol["human_review_thresholds"]["tie_margin"]:
                row["near_tie_with"].append(eligible[i - 1]["work_id"])
                eligible[i - 1]["near_tie_with"].append(row["work_id"])
    for row in rows:
        if row["near_tie_with"]:
            row["review_reasons"].append(f"adjacent ranking gap <= {protocol['human_review_thresholds']['tie_margin']}")
            row["needs_human_review"] = True
    human_history = apply_reviews(rows, spec, result)
    k_value = spec.get("top_k", spec.get("k", 10))
    try:
        if isinstance(k_value, bool) or int(k_value) != k_value or int(k_value) < 0:
            raise ValueError
        top_k = int(k_value)
    except (TypeError, ValueError):
        raise C.RetrievalError("screening.top_k_invalid", "top_k/k must be a non-negative integer", 4)
    include_rows = sorted([row for row in rows if row["final_decision"] == "include"],
                          key=lambda row: (-row["priority_score"], C.normalize_title(row["metadata"].get("title")),
                                           row["metadata"].get("doi") or "", row["work_id"]))
    pending_rows = sorted([row for row in rows if row["final_decision"] == "pending"],
                          key=lambda row: (-row["priority_score"], C.normalize_title(row["metadata"].get("title")),
                                           row["metadata"].get("doi") or "", row["work_id"]))
    exclude_rows = sorted([row for row in rows if row["final_decision"] == "exclude"],
                          key=lambda row: (-row["priority_score"], C.normalize_title(row["metadata"].get("title")),
                                           row["metadata"].get("doi") or "", row["work_id"]))
    for collection, kind in ((include_rows, "include"), (pending_rows, "pending"), (exclude_rows, "exclude")):
        for rank, row in enumerate(collection, 1):
            row["rank"] = rank
            row["ranking_layer"] = kind
            row["in_top_k"] = kind == "include" and rank <= top_k
    ordered_rows = include_rows + pending_rows + exclude_rows
    # Missing metadata is explicit but never silently substituted in ranking.
    for row in ordered_rows:
        missing = row["metadata_completeness"]["missing_fields"]
        if missing and row["final_decision"] != "exclude":
            C.finding(result, "screening.metadata_incomplete", "medium",
                      f"candidate {row['work_id']} lacks {', '.join(missing)}",
                      work_id=row["work_id"], missing_fields=missing)
        unresolved = [e for e in row.get("evidence", []) if e.get("status") != "verbatim"] + [
            e for criterion in row["criteria_matches"] for e in criterion.get("evidence", []) if e.get("status") != "verbatim"]
        if unresolved:
            C.finding(result, "screening.evidence_locator_unresolved", "high",
                      f"candidate {row['work_id']} has unresolved evidence locators")
    if any(row["version_conflicts"] for row in rows):
        C.finding(result, "screening.version_conflict_review", "medium",
                  "one or more preprint/formal/source conflicts requires human adjudication",
                  conflicts=version_conflicts)
    review_queue = [{key: row[key] for key in ("work_id", "record_id", "final_decision", "priority_score",
                    "decision_confidence", "review_reasons", "near_tie_with", "exact_tie_with", "review_resolution")}
                    for row in ordered_rows if row["final_decision"] == "pending" or row["needs_human_review"]]
    for item in review_queue:
        item["human_review_performed"] = bool(next(row for row in rows if row["work_id"] == item["work_id"])["human_history"])
        item["resolution_required"] = not item["human_review_performed"] or item["review_resolution"] in {
            "unresolved_human_label_conflict", "conflicting_adjudications"}
        if item["resolution_required"]:
            C.finding(result, "screening.review_required", "medium",
                      f"work {item['work_id']} needs human review: {', '.join(item['review_reasons']) or 'pending final decision'}",
                      work_id=item["work_id"])
    if not include_rows:
        C.finding(result, "screening.no_retained_records", "medium",
                  "no record was retained by the engine/human-reviewed protocol; excluded and pending rows remain inspectable")
    # Every export row inherits its work disposition but is never counted twice as
    # independent evidence.  This mirrors ASReview duplicate_of/group_id semantics.
    final_by_work = {row["work_id"]: row for row in rows}
    screening_log = []
    for audit in duplicate_audit:
        final = final_by_work[audit["work_id"]]
        screening_log.append({**audit, "title": final["metadata"].get("title"),
                              "engine_decision": final["engine_decision"], "final_decision": final["final_decision"],
                              "relevance_class": final["relevance_class"], "reason_code": final["reason_code"],
                              "reason": final["reason"], "priority_score": final["priority_score"],
                              "decision_confidence": final["decision_confidence"],
                              "review_resolution": final["review_resolution"],
                              "not_independent_evidence": audit["duplicate_of"] is not None})
    accounted = all(row["work_id"] in final_by_work for row in screening_log) and len(screening_log) == len(records)
    if not accounted:
        C.finding(result, "screening.accounting_broken", "high", "not every raw export row is covered by screening_log")
    search_trace = {key: copy.deepcopy(spec[key]) for key in ("query", "queries", "query_history", "search_history", "search_protocol")
                    if key in spec}
    result.update({
        "screening_protocol": protocol, "screened_records": ordered_rows, "ranked_included": include_rows,
        "pending_records": pending_rows, "excluded_records": exclude_rows, "review_queue": review_queue,
        "screening_log": screening_log, "human_review_history": human_history, "dedup_audit": duplicate_audit,
        "source_conflicts": version_conflicts,
        "检索结果": {"候选文献": ordered_rows, "排序/筛选结果": {
                     "保留": [{"work_id": row["work_id"], "rank": row["rank"], "top_k": row["in_top_k"],
                             "priority_score": row["priority_score"], "score_components": row["score_components"]}
                            for row in include_rows],
                     "待定": [{"work_id": row["work_id"], "rank": row["rank"], "review_reasons": row["review_reasons"]}
                            for row in pending_rows],
                     "排除": [{"work_id": row["work_id"], "reason_code": row["reason_code"], "reason": row["reason"]}
                            for row in exclude_rows]},
                   "元数据": {row["work_id"]: row["metadata"] for row in ordered_rows},
                   "来源定位": {row["work_id"]: row["sources"] for row in ordered_rows},
                   "遗漏说明": [{"work_id": row["work_id"], "missing": row["metadata_completeness"]["missing_fields"],
                              "duplicate_of": row["duplicate_of"]} for row in ordered_rows]},
        "证据记录": {"screening_protocol": protocol, "screening_log": screening_log,
                   "criteria_and_evidence": {row["work_id"]: row["criteria_matches"] for row in ordered_rows},
                   "排序特征与分数解释": {row["work_id"]: {"priority_score": row["priority_score"],
                                      "components": row["score_components"], "weighted_components": row["weighted_components"],
                                      "matched_terms": row["relevance"]["matched_terms"],
                                      "field_components": row["relevance"]["field_components"]} for row in ordered_rows},
                   "人工复核门槛": protocol["human_review_thresholds"], "原始查询与迭代": search_trace,
                   "人工复核记录": human_history, "同分与复核队列": review_queue},
        "状态说明": {"运行状态": result["status"],
                   "已完成": {"input_export_rows": len(records), "screened_work_groups": len(works),
                            "include": len(include_rows), "pending": len(pending_rows), "exclude": len(exclude_rows)},
                   "未完成": review_queue, "空结果": {"candidate_set_empty": False, "included_empty": not bool(include_rows)},
                   "冲突": version_conflicts + [f for f in result["findings"] if "conflict" in f["rule"]],
                   "权限或接口异常": [{"record_id": record["record_id"], "access": record["source"].get("access")}
                                   for record in records if record.get("access_blocked")],
                   "计数闭合": {"raw_rows_equal_log_rows": len(records) == len(screening_log),
                              "all_groups_have_final_decision": len({r["work_id"] for r in rows}) == len(works),
                              "include_pending_exclude_total": len(include_rows) + len(pending_rows) + len(exclude_rows),
                              "expected_groups": len(works), "passed": accounted},
                   "不确定性": "Title/abstract lexical triage is not full-text relevance or systematic-review adjudication."},
        "candidate_set_summary": {"input_export_rows": len(records), "deduplicated_work_groups": len(works),
                                  "include": len(include_rows), "pending": len(pending_rows), "exclude": len(exclude_rows),
                                  "top_k": top_k, "top_k_count": sum(row["in_top_k"] for row in include_rows),
                                  "review_queue": len(review_queue), "human_decisions_applied": len(human_history),
                                  "all_raw_rows_accounted": accounted, "remote_hit_count": None},
        "sources": [source for work in works for source in work["sources"]],
        "change_records": [change for row in rows for change in row["change_records"]],
        "uncertainty": ["A lexical include/exclude is not full-text truth; pending is the safety layer for missing text, derived criteria and conflicts.",
                        "Priority is a weighted heuristic, not a learned/calibrated model; source trace and metadata completeness stay visible separately.",
                        "No remote query, remote hit count, global Recall@k or completed human review is claimed unless explicitly supplied and validated."],
        "deliverables": ["result.json", "screening_protocol.json", "screened_records.json", "screening_log.csv",
                         "ranked_candidates.csv", "review_queue.csv", "screening_report.md"],
    })
    result["limits"] = ["Screening is title/abstract/keywords lexical triage; negative evidence beyond declared criteria is not inferred.",
                        "Near ties and low confidence create review items; deterministic title/DOI/work_id ties alone do not fabricate semantic superiority.",
                        "Duplicate export rows stay in the ledger but are not independent evidence; versions and source conflicts remain pending."]
    return C.complete_contract(result, spec, case)


def report_markdown(result: dict[str, Any]) -> str:
    summary = result["candidate_set_summary"]
    lines = ["# 文献筛选与智能排序（标题/摘要级固定候选集）", "", f"- case_id：{result.get('case_id')}",
             f"- 状态：{result.get('status')}",
             f"- 输入导出 {summary['input_export_rows']} 行；作品/版本组 {summary['deduplicated_work_groups']}；"
             f"保留 {summary['include']}，待定 {summary['pending']}，排除 {summary['exclude']}。",
             "- 本报告不是全文系统综述，也不声称远程数据库命中、全球召回或已执行人工复核。", "",
             "## 可复算排序", "",
             "| 层级 | rank | 文献 | 总分 | 相关性 | 标准覆盖 | 元数据 | 来源可追溯 | 决定与理由 |", "|-|-|-|-|-|-|-|-|-|"]
    for row in result["screened_records"]:
        title = str(row["metadata"].get("title") or "undetermined").replace("|", "/")
        comp = row["score_components"]
        lines.append(f"| {row['final_decision']} | {row['rank']} | {title} | {row['priority_score']:.4f} | "
                     f"{comp['relevance']:.4f} | {comp['criteria_coverage']:.4f} | {comp['metadata_completeness']:.3f} | "
                     f"{comp['source_trace']:.2f} | {row['reason_code']} {row['reason'].replace('|', '/')} |")
    lines += ["", "总分 = 70% 字段BM25 + 20% 必需标准覆盖 + 5% 元数据完整性 + 5% 来源可追溯性（如案例未覆盖权重配置）。纳排门控先执行，分数不能救回明确排除。", "",
              "同分以规范题名、DOI、work_id 决定稳定次序；近同分、低置信、版本冲突和待定条目录入 review_queue，而不是伪装成语义强弱。", "",
              "## 逐条理由与复核", "",
              "screening_log.csv 覆盖全部原始导出行，ranked_candidates.csv 保留每个标准与特征，review_queue.csv 列出人工复核门槛和真实复核状态。没有 reviewer + rationale 的输入不会写成已完成人工复核。", ""]
    for finding in result.get("findings", []):
        lines.append(f"- {finding['severity']} / {finding['rule']}：{finding.get('message', '')}")
    return "\n".join(lines) + "\n"
