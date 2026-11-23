"""Deterministic PRISMA screening, risk-of-bias and evidence-synthesis engine.

Only actual supplied records are counted for fixed corpora.  Executed database
exports must reconcile exactly; prospective searches keep external counts null.
No network retrieval, LLM judgement or fabricated PRISMA totals are performed.
"""
from __future__ import annotations

import math
import re
from collections import Counter, defaultdict
from typing import Any

SCHEMA = "systematic-review/v2"
DIRECTIONS = {"positive", "negative", "no_effect", "mixed", "not_reported"}
DOMAIN_SETS = {"ROB2": ["D1", "D2", "D3", "D4", "D5"],
               "ROBINS-I": ["D1", "D2", "D3", "D4", "D5", "D6", "D7"],
               "QUADAS-2": ["D1", "D2", "D3", "D4"], "generic": None}
JUDGEMENTS = {
    "ROB2": {"low", "some_concerns", "high", "no_information", "not_applicable"},
    "ROBINS-I": {"low", "moderate", "serious", "critical", "no_information", "not_applicable"},
    "QUADAS-2": {"low", "some_concerns", "high", "no_information", "not_applicable"},
    "generic": {"low", "some_concerns", "high", "no_information", "not_applicable"},
}
RANKS = {"low": 0, "moderate": 1, "some_concerns": 1, "no_information": 2,
         "high": 3, "serious": 3, "critical": 4}
PRIMARY_DEFAULT = {"low", "some_concerns", "moderate"}


def _text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return " ".join(value.split())
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return str(value)
    return ""


def _items(value: Any) -> list:
    return value if isinstance(value, list) else []


def _doi(value: Any) -> str:
    text = _text(value).lower()
    return re.sub(r"^https?://(?:dx\.)?doi\.org/", "", text).rstrip(". ")


def _title(value: Any) -> str:
    return re.sub(r"[^a-z0-9\u4e00-\u9fff]+", "", _text(value).lower())


def _number(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    value = float(value)
    return value if math.isfinite(value) else None


def _pool(members: list[dict], allow: bool) -> dict:
    """Inverse-variance fixed and DerSimonian-Laird random effects over all eligible studies."""
    base = {"computed": False, "reason": None, "k": len(members)}
    if not allow:
        base["reason"] = "meta-analysis disabled by protocol; narrative synthesis only"
        return base
    if len(members) < 2:
        base["reason"] = "fewer than two independent primary studies"
        return base
    effects = [row.get("effect") if isinstance(row.get("effect"), dict) else {} for row in members]
    measures = {_text(effect.get("measure")) for effect in effects}
    if len(measures) != 1 or not next(iter(measures), ""):
        base["reason"] = "effect measures are absent or not identical across the complete comparison group"
        return base
    estimates = [_number(effect.get("estimate")) for effect in effects]
    ses = [_number(effect.get("se")) for effect in effects]
    if any(value is None for value in estimates) or any(value is None or value <= 0 for value in ses):
        base["reason"] = "every study in the group needs a finite estimate and positive standard error"
        return base
    estimates = [float(value) for value in estimates]
    ses = [float(value) for value in ses]
    weights = [1.0 / (se * se) for se in ses]
    sw = sum(weights)
    fixed_mean = sum(w * y for w, y in zip(weights, estimates)) / sw
    fixed_se = math.sqrt(1.0 / sw)
    q = sum(w * (y - fixed_mean) ** 2 for w, y in zip(weights, estimates))
    df = len(members) - 1
    i2 = max(0.0, (q - df) / q) * 100.0 if q > 0 else 0.0
    denominator = sw - sum(w * w for w in weights) / sw
    tau2 = max(0.0, (q - df) / denominator) if denominator > 0 else 0.0
    random_weights = [1.0 / (se * se + tau2) for se in ses]
    sr = sum(random_weights)
    random_mean = sum(w * y for w, y in zip(random_weights, estimates)) / sr
    random_se = math.sqrt(1.0 / sr)
    return {
        "computed": True, "reason": None, "k": len(members),
        "effect_measure": next(iter(measures)),
        "study_ids": [row.get("study_id") for row in members],
        "estimates": estimates, "standard_errors": ses,
        "fixed_effect": {"estimate": fixed_mean, "se": fixed_se,
                         "ci95": [fixed_mean - 1.96 * fixed_se, fixed_mean + 1.96 * fixed_se]},
        "random_effects_DL": {"estimate": random_mean, "se": random_se, "tau2": tau2,
                              "ci95": [random_mean - 1.96 * random_se, random_mean + 1.96 * random_se]},
        "Q": q, "df": df, "I2_percent": i2,
        "interpretation": "exploratory_only_high_heterogeneity" if i2 >= 75 else
                          ("random_effects_with_caution" if i2 >= 50 else "computed_summary_with_reported_heterogeneity"),
        "headline_allowed": i2 < 75,
        "method": "inverse variance; fixed effect and DerSimonian-Laird random effects; normal 95% CI",
    }


def analyze(spec: dict) -> dict:
    findings: list[dict] = []
    uncertainties: list[dict] = []

    def add(rule: str, severity: str, message: str, **context: Any) -> None:
        findings.append({"rule": rule, "severity": severity, "message": message, **context})

    def uncertain(kind: str, message: str, **context: Any) -> None:
        row = {"kind": kind, "message": message, **context}
        if row not in uncertainties:
            uncertainties.append(row)

    question = spec.get("research_question")
    if not isinstance(question, dict):
        add("sr.question_missing", "high", "research_question must be an object with PICO/structure")
        question = {}
    for field in ("population", "intervention", "comparator", "outcome"):
        if not _text(question.get(field)):
            add("sr.pico_missing", "high", f"research_question.{field} is required", field=field)
    protocol = spec.get("search_protocol") if isinstance(spec.get("search_protocol"), dict) else {}
    execution = _text(protocol.get("status")) or "undetermined"
    if execution not in {"executed", "fixed_corpus", "prospective"}:
        add("sr.search_status_unknown", "high", "search_protocol.status must be executed/fixed_corpus/prospective")
    if not _text(protocol.get("version")):
        add("sr.protocol_version_missing", "high", "search protocol must be versioned and frozen")
    for field in ("start_date", "end_date"):
        if not _text(protocol.get(field)):
            add("sr.search_boundary_missing", "high", f"search_protocol.{field} is required", field=field)
    if not _items(protocol.get("languages")) and not _text(protocol.get("languages")):
        add("sr.language_boundary_missing", "high", "language restrictions are required")
    for field in ("inclusion_criteria", "exclusion_criteria"):
        if not _items(protocol.get(field)):
            add("sr.criteria_missing", "high", f"search_protocol.{field} must be explicit", field=field)
    if not _text(protocol.get("criterion_priority")) or not _text(protocol.get("conflict_policy")):
        add("sr.criterion_conflict_policy_missing", "high",
            "criterion priority and conflict adjudication policy are required")
    databases = _items(protocol.get("databases"))
    if not databases:
        add("sr.databases_missing", "high", "at least one database/source is required")
    source_names = set()
    search_rows: list[dict] = []
    for pos, source in enumerate(databases):
        if not isinstance(source, dict):
            add("sr.database_row_invalid", "high", "database entry is not an object", database_index=pos)
            continue
        name = _text(source.get("name")) or f"database-{pos + 1}"
        source_names.add(name)
        query = _text(source.get("query"))
        for field in ("name", "query", "fields", "coverage"):
            if not _text(source.get(field)) and not _items(source.get(field)):
                add("sr.database_field_missing", "high", f"source {name} lacks {field}",
                    source=name, field=field)
        if query and not any(token in query.upper() for token in (" AND ", " OR ", " NOT ", ":", "\"", "*")):
            add("sr.query_not_executable", "high", f"source {name} query is only an unstructured keyword string",
                source=name)
        if not _items(source.get("synonyms")) and not _items(source.get("controlled_terms")):
            add("sr.controlled_vocabulary_missing", "medium",
                f"source {name} has neither synonyms nor controlled terms", source=name)
        search_date = _text(source.get("search_date") or source.get("snapshot_date"))
        if execution in {"executed", "fixed_corpus"} and not search_date:
            add("sr.search_date_missing", "high", f"{execution} source {name} needs an actual date", source=name)
        hits = source.get("hit_count")
        if execution == "executed" and (not isinstance(hits, int) or isinstance(hits, bool) or hits < 0):
            add("sr.hit_count_invalid", "high", f"executed source {name} needs non-negative integer hit_count",
                source=name)
        if execution != "executed" and hits is not None:
            add("sr.unexecuted_hit_count", "high", f"{execution} source {name} cannot report executed hits",
                source=name)
        search_rows.append({"kind": "database", "name": name, "query": query,
                            "fields": source.get("fields"), "controlled_terms": source.get("controlled_terms"),
                            "synonyms": source.get("synonyms"), "filters": source.get("filters"),
                            "coverage": source.get("coverage"), "search_date": search_date or None,
                            "status": execution, "hit_count": hits if execution == "executed" else None,
                            "records_supplied": 0})

    raw_records = _items(spec.get("records"))
    if not raw_records and execution != "prospective":
        add("sr.records_missing", "high", "no identification/export records were supplied")
    records: list[dict] = []
    screening_log: list[dict] = []
    duplicate_rows: list[dict] = []
    malformed = 0
    seen_ids: set[str] = set()
    canonical: dict[str, str] = {}
    for pos, raw in enumerate(raw_records):
        if not isinstance(raw, dict):
            malformed += 1
            add("sr.record_invalid", "high", "identification record is not an object", record_index=pos)
            continue
        rid = _text(raw.get("report_id") or raw.get("id")) or f"R{pos + 1:03d}"
        if rid in seen_ids:
            malformed += 1
            add("sr.report_id_duplicate", "high", f"duplicate report_id {rid}", report_id=rid)
            continue
        seen_ids.add(rid)
        source_name = _text(raw.get("source_database"))
        matched_source = next((row for row in search_rows if row["name"] == source_name), None)
        if matched_source is None:
            add("sr.record_source_unknown", "high", f"record {rid} names unknown source {source_name}",
                report_id=rid)
        else:
            matched_source["records_supplied"] += 1
        key = _doi(raw.get("doi")) or _title(raw.get("title"))
        duplicate_of = _text(raw.get("duplicate_of")) or canonical.get(key)
        if key and key not in canonical:
            canonical[key] = rid
        record = dict(raw)
        record["_id"] = rid
        record["_study_id"] = _text(raw.get("study_id")) or rid
        record["_duplicate_of"] = duplicate_of or None
        record["_malformed"] = False
        records.append(record)
        if duplicate_of:
            duplicate_rows.append({"report_id": rid, "duplicate_of": duplicate_of, "match_key": key or None})
            screening_log.append({"report_id": rid, "study_id": record["_study_id"], "title": raw.get("title"),
                                  "source_database": source_name, "stage": "identification",
                                  "computed_decision": "duplicate", "reason_code": "DUP",
                                  "reason": f"duplicate of {duplicate_of}"})
            continue
        if raw.get("automation_exclude") is True:
            reason = _text(raw.get("automation_reason"))
            if not reason:
                add("sr.automation_reason_missing", "high", f"automation-removed record {rid} lacks reason",
                    report_id=rid)
            screening_log.append({"report_id": rid, "study_id": record["_study_id"], "title": raw.get("title"),
                                  "source_database": source_name, "stage": "pre_screen_automation",
                                  "computed_decision": "excluded", "reason_code": "AUTO", "reason": reason})
            continue
        if raw.get("pre_screen_exclude") is True:
            reason = _text(raw.get("pre_screen_reason"))
            if not reason:
                add("sr.pre_screen_reason_missing", "high", f"pre-screen-removed record {rid} lacks reason",
                    report_id=rid)
            screening_log.append({"report_id": rid, "study_id": record["_study_id"], "title": raw.get("title"),
                                  "source_database": source_name, "stage": "pre_screen_other",
                                  "computed_decision": "excluded", "reason_code": "OTHER", "reason": reason})
            continue
        ta = _text(raw.get("ta_decision")) or "undetermined"
        if ta not in {"include", "exclude", "undetermined"}:
            add("sr.ta_decision_invalid", "high", f"record {rid} has invalid ta_decision {ta}", report_id=rid)
        if ta == "exclude" and (not _text(raw.get("ta_reason_code")) or not _text(raw.get("ta_reason"))):
            add("sr.ta_exclusion_reason_missing", "high", f"title/abstract exclusion {rid} needs code and reason",
                report_id=rid)
        if ta == "undetermined":
            add("sr.ta_decision_undetermined", "high", f"title/abstract decision for {rid} remains undetermined",
                report_id=rid)
        base_log = {"report_id": rid, "study_id": record["_study_id"], "title": raw.get("title"),
                    "source_database": source_name, "stage": "title_abstract", "computed_decision": ta,
                    "reason_code": raw.get("ta_reason_code"), "reason": raw.get("ta_reason"),
                    "reviewer": raw.get("ta_reviewer"), "reviewers": raw.get("ta_reviews"),
                    "adjudication": raw.get("ta_adjudication")}
        screening_log.append(base_log)
        if ta != "include":
            continue
        full_status = _text(raw.get("fulltext_status")) or "undetermined"
        if full_status == "not_retrieved" and not _text(raw.get("retrieval_reason")):
            add("sr.not_retrieved_reason_missing", "high", f"not-retrieved report {rid} needs a reason",
                report_id=rid)
        if full_status not in {"retrieved", "not_retrieved"}:
            add("sr.retrieval_status_unknown", "high", f"report {rid} sought for retrieval has unknown fulltext status",
                report_id=rid)
        if full_status == "not_retrieved":
            screening_log.append({"report_id": rid, "study_id": record["_study_id"], "stage": "retrieval",
                                  "computed_decision": "not_retrieved", "reason_code": "NOT-RETRIEVED",
                                  "reason": raw.get("retrieval_reason")})
            continue
        ft = _text(raw.get("ft_decision")) or "undetermined"
        if ft not in {"include", "exclude", "undetermined"}:
            add("sr.ft_decision_invalid", "high", f"report {rid} has invalid ft_decision {ft}", report_id=rid)
        if ft == "exclude" and (not _text(raw.get("ft_reason_code")) or not _text(raw.get("ft_reason"))):
            add("sr.ft_exclusion_reason_missing", "high", f"full-text exclusion {rid} needs code and reason",
                report_id=rid)
        if ft == "undetermined":
            add("sr.ft_decision_undetermined", "high", f"full-text decision for {rid} remains undetermined",
                report_id=rid)
        screening_log.append({"report_id": rid, "study_id": record["_study_id"], "stage": "full_text",
                              "computed_decision": ft, "reason_code": raw.get("ft_reason_code"),
                              "reason": raw.get("ft_reason"), "reviewer": raw.get("ft_reviewer"),
                              "reviewers": raw.get("ft_reviews"), "adjudication": raw.get("ft_adjudication")})

    # Check independent reviewers and adjudication without overwriting declared final decisions.
    for record in records:
        rid = record["_id"]
        for stage in ("ta", "ft"):
            decision = _text(record.get(f"{stage}_decision"))
            if not decision:
                continue
            reviews = [row for row in _items(record.get(f"{stage}_reviews")) if isinstance(row, dict)]
            if reviews:
                votes = [_text(row.get("decision")) for row in reviews]
                if any(not _text(row.get("reviewer")) for row in reviews):
                    add("sr.reviewer_missing", "high", f"{stage} review for {rid} has no reviewer", report_id=rid)
                if len(set(votes)) > 1:
                    adj = record.get(f"{stage}_adjudication")
                    if not isinstance(adj, dict) or not _text(adj.get("reason")) or _text(adj.get("decision")) != decision:
                        add("sr.review_conflict_unresolved", "high",
                            f"{stage} reviewers disagree for {rid}; final decision needs matching reasoned adjudication",
                            report_id=rid, stage=stage, votes=votes)
                    else:
                        uncertain("reviewer_disagreement", f"{rid} 的 {stage} 初选分歧已按裁决理由解决并留痕。",
                                  report_id=rid, stage=stage, votes=votes)
            elif not _text(record.get(f"{stage}_reviewer")):
                add("sr.reviewer_missing", "high", f"{stage} decision for {rid} has no reviewer", report_id=rid)

    if execution == "executed":
        for source in search_rows:
            if source["hit_count"] != source["records_supplied"]:
                add("sr.export_count_mismatch", "high",
                    f"source {source['name']} hit_count ({source['hit_count']}) != supplied export rows ({source['records_supplied']})",
                    source=source["name"])

    candidates = [row for row in records if not row["_duplicate_of"]
                  and row.get("automation_exclude") is not True and row.get("pre_screen_exclude") is not True]
    ta_included = [row for row in candidates if _text(row.get("ta_decision")) == "include"]
    ta_excluded = [row for row in candidates if _text(row.get("ta_decision")) == "exclude"]
    ta_undetermined = [row for row in candidates if _text(row.get("ta_decision")) not in {"include", "exclude"}]
    automation_removed = [row for row in records if not row["_duplicate_of"] and row.get("automation_exclude") is True]
    other_removed = [row for row in records if not row["_duplicate_of"] and row.get("pre_screen_exclude") is True
                     and row.get("automation_exclude") is not True]
    not_retrieved = [row for row in ta_included if _text(row.get("fulltext_status")) == "not_retrieved"]
    assessed = [row for row in ta_included if _text(row.get("fulltext_status")) == "retrieved"]
    ft_excluded = [row for row in assessed if _text(row.get("ft_decision")) == "exclude"]
    ft_undetermined = [row for row in assessed if _text(row.get("ft_decision")) not in {"include", "exclude"}]
    included = [row for row in assessed if _text(row.get("ft_decision")) == "include"]
    included_study_ids = sorted({row["_study_id"] for row in included})
    counts = {
        "identified": len(raw_records), "malformed": malformed, "duplicates": len(duplicate_rows),
        "automation_removed": len(automation_removed), "other_removed": len(other_removed),
        "records_screened": len(candidates), "records_excluded": len(ta_excluded),
        "records_undetermined": len(ta_undetermined), "reports_sought": len(ta_included),
        "reports_not_retrieved": len(not_retrieved), "reports_assessed": len(assessed),
        "reports_excluded": len(ft_excluded), "fulltext_undetermined": len(ft_undetermined),
        "reports_included": len(included), "studies_included": len(included_study_ids),
    }
    ta_reasons = Counter(_text(row.get("ta_reason_code")) or "UNSPECIFIED" for row in ta_excluded)
    ft_reasons = Counter(_text(row.get("ft_reason_code")) or "UNSPECIFIED" for row in ft_excluded)
    checks = {
        "identification_closes": counts["identified"] == malformed + counts["duplicates"] +
                                 counts["automation_removed"] + counts["other_removed"] + counts["records_screened"],
        "title_abstract_closes": counts["records_screened"] == counts["records_excluded"] +
                                  counts["records_undetermined"] + counts["reports_sought"],
        "retrieval_closes": counts["reports_sought"] == counts["reports_not_retrieved"] + counts["reports_assessed"],
        "fulltext_closes": counts["reports_assessed"] == counts["reports_excluded"] +
                            counts["fulltext_undetermined"] + counts["reports_included"],
        "ta_exclusion_reasons_close": sum(ta_reasons.values()) == counts["records_excluded"],
        "ft_exclusion_reasons_close": sum(ft_reasons.values()) == counts["reports_excluded"],
    }
    if not all(checks.values()):
        add("sr.prisma_not_closed", "high", "one or more PRISMA arithmetic identities do not close",
            checks=checks)
    if ta_undetermined or ft_undetermined:
        add("sr.screening_incomplete", "high", "undetermined screening decisions prevent a final include set")
    if execution == "fixed_corpus" and not included:
        add("sr.no_included_records", "high", "fixed corpus has no included studies for synthesis")
    if execution == "prospective":
        add("sr.prospective_protocol_only", "medium",
            "prospective protocol only; database execution and completed-review counts are undetermined")
        uncertain("prospective_only", "检索与筛选为前瞻协议；没有真实数据库执行结果，PRISMA 外部流程计数保持 null。")

    # Evidence rows are checked before quality appraisal or synthesis can use them.
    evidence_map: dict[str, dict] = {}
    evidence_rows: list[dict] = []
    for record in records:
        rid = record["_id"]
        source_excerpt = record.get("source_excerpt")
        for ev_pos, ev in enumerate(_items(record.get("evidence"))):
            if not isinstance(ev, dict):
                add("sr.evidence_row_invalid", "high", f"report {rid} evidence entry is not an object", report_id=rid)
                continue
            eid = _text(ev.get("id")) or f"{rid}:E{ev_pos + 1}"
            quote = _text(ev.get("quote"))
            locator = _text(ev.get("locator"))
            if eid in evidence_map:
                add("sr.evidence_id_duplicate", "high", f"duplicate evidence id {eid}", report_id=rid)
                continue
            if not quote or not locator:
                add("sr.evidence_locator_missing", "high", f"evidence {eid} needs quote and exact locator",
                    report_id=rid)
            if isinstance(source_excerpt, str) and source_excerpt and quote and quote not in source_excerpt:
                add("sr.quote_not_in_source", "high", f"evidence {eid} quote is absent from source_excerpt",
                    report_id=rid)
            row = {"evidence_id": eid, "report_id": rid, "study_id": record["_study_id"],
                   "title": record.get("title"), "doi": record.get("doi"), "year": record.get("year"),
                   "source_database": record.get("source_database"), "fields": ev.get("fields"),
                   "comparison_key": record.get("comparison_key"), "quote": quote, "locator": locator,
                   "included": record in included}
            evidence_map[eid] = row
            evidence_rows.append(row)

    for record in included:
        rid = record["_id"]
        for field in ("design", "population", "intervention", "comparator", "outcome", "followup",
                      "method", "data", "conclusion", "comparison_key"):
            if not _text(record.get(field)):
                add("sr.synthesis_field_missing", "high", f"included report {rid} lacks {field}",
                    report_id=rid, field=field)
        if _text(record.get("direction")) not in DIRECTIONS:
            add("sr.direction_unknown", "high", f"included report {rid} has unknown direction", report_id=rid)
        field_refs = record.get("field_evidence") if isinstance(record.get("field_evidence"), dict) else {}
        for field in ("method", "data", "outcome", "conclusion"):
            if not _items(field_refs.get(field)):
                add("sr.field_evidence_missing", "high", f"included report {rid} field {field} has no evidence",
                    report_id=rid, field=field)

    def evidence_owners(ref: str) -> dict | None:
        return evidence_map.get(ref)

    for record in included:
        rid = record["_id"]
        field_refs = record.get("field_evidence") if isinstance(record.get("field_evidence"), dict) else {}
        for refs in field_refs.values():
            for value in _items(refs):
                ref = _text(value)
                if ref not in evidence_map:
                    add("sr.field_evidence_unresolved", "high", f"report {rid} field evidence {ref} does not resolve",
                        report_id=rid)
                elif evidence_map[ref]["report_id"] != rid:
                    add("sr.field_evidence_cross_report", "high", f"report {rid} incorrectly cites {ref}",
                        report_id=rid)
        effect = record.get("effect")
        if effect is not None:
            if not isinstance(effect, dict) or not _text(effect.get("evidence_ref")):
                add("sr.effect_evidence_missing", "high", f"effect for {rid} needs an evidence_ref", report_id=rid)
            elif effect.get("evidence_ref") not in evidence_map or evidence_map[effect["evidence_ref"]]["report_id"] != rid:
                add("sr.effect_evidence_unresolved", "high", f"effect evidence for {rid} is invalid", report_id=rid)

    # One primary report per study avoids double counting multi-report studies in synthesis.
    primary_by_study: dict[str, list[dict]] = defaultdict(list)
    for record in included:
        if _text(record.get("synthesis_role")) != "secondary":
            primary_by_study[record["_study_id"]].append(record)
    synthesis_members: list[dict] = []
    for study_id in included_study_ids:
        primaries = primary_by_study.get(study_id, [])
        if len(primaries) != 1:
            add("sr.primary_report_count_invalid", "high",
                f"study {study_id} needs exactly one primary synthesis report; found {len(primaries)}", study_id=study_id)
        else:
            synthesis_members.append(primaries[0])

    # Bias appraisal: per-domain evidence and computed overall; unweighted summaries (robvis-style rows).
    appraisals = _items(spec.get("quality_appraisals"))
    quality_rows: list[dict] = []
    quality_by_study: dict[str, dict] = {}
    domain_counts: dict[str, Counter] = defaultdict(Counter)
    overall_counts: Counter = Counter()
    for pos, appraisal in enumerate(appraisals):
        if not isinstance(appraisal, dict):
            add("sr.quality_row_invalid", "high", "quality appraisal entry is not an object", appraisal_index=pos)
            continue
        sid = _text(appraisal.get("study_id"))
        tool = _text(appraisal.get("tool")) or "generic"
        if sid not in included_study_ids:
            add("sr.quality_study_not_included", "high", f"quality appraisal references non-included study {sid}",
                study_id=sid)
            continue
        if sid in quality_by_study:
            add("sr.quality_duplicate", "high", f"study {sid} has multiple quality appraisals", study_id=sid)
            continue
        if tool not in DOMAIN_SETS:
            add("sr.quality_tool_unknown", "high", f"study {sid} uses unsupported quality tool {tool}", study_id=sid)
            continue
        expected_domains = DOMAIN_SETS[tool]
        domains = _items(appraisal.get("domains"))
        domain_rows: list[dict] = []
        seen_domains = set()
        for dpos, domain in enumerate(domains):
            if not isinstance(domain, dict):
                add("sr.quality_domain_invalid", "high", f"study {sid} domain entry is not an object", study_id=sid)
                continue
            did = _text(domain.get("domain")) or f"D{dpos + 1}"
            judgement = _text(domain.get("judgement"))
            if did in seen_domains:
                add("sr.quality_domain_duplicate", "high", f"study {sid} repeats domain {did}", study_id=sid)
            seen_domains.add(did)
            if judgement not in JUDGEMENTS[tool]:
                add("sr.quality_judgement_unknown", "high",
                    f"study {sid} domain {did} has invalid judgement {judgement} for {tool}", study_id=sid, domain=did)
            refs = [_text(value) for value in _items(domain.get("evidence_refs")) if _text(value)]
            if not refs:
                add("sr.quality_evidence_missing", "high", f"study {sid} domain {did} has no evidence", study_id=sid)
            for ref in refs:
                owner = evidence_owners(ref)
                if owner is None or owner["study_id"] != sid or not owner["included"]:
                    add("sr.quality_evidence_unresolved", "high",
                        f"study {sid} domain {did} reference {ref} is not included study evidence",
                        study_id=sid, domain=did)
            domain_rows.append({"study_id": sid, "tool": tool, "domain": did, "judgement": judgement,
                                "evidence_refs": refs, "rationale": domain.get("rationale")})
        if expected_domains is not None and seen_domains != set(expected_domains):
            add("sr.quality_domain_coverage", "high",
                f"{tool} study {sid} must cover exactly {', '.join(expected_domains)}", study_id=sid)
        if tool == "generic" and not seen_domains:
            add("sr.quality_domain_coverage", "high", f"generic appraisal {sid} has no domains", study_id=sid)
        values = [row["judgement"] for row in domain_rows if row["judgement"] in RANKS]
        if not values:
            overall = "undetermined"
        elif tool == "ROB2" and any(value == "high" for value in values):
            overall = "high"
        elif tool == "ROB2" and any(value in {"some_concerns", "no_information"} for value in values):
            overall = "some_concerns"
        else:
            overall = max(values, key=lambda value: RANKS[value])
        reported = _text(appraisal.get("overall_reported"))
        if reported and reported != overall:
            add("sr.quality_overall_mismatch", "high",
                f"study {sid} overall_reported={reported} but domain computation={overall}", study_id=sid)
        quality = {"study_id": sid, "tool": tool, "domains": domain_rows,
                   "overall_computed": overall, "overall_reported": reported or None,
                   "summary_weighting": "unweighted",
                   "citations": [evidence_map[ref] for ref in dict.fromkeys(
                       ref for row in domain_rows for ref in row["evidence_refs"] if ref in evidence_map)]}
        quality_by_study[sid] = quality
        quality_rows.extend(domain_rows)
        overall_counts[overall] += 1
        for row in domain_rows:
            domain_counts[f"{tool}:{row['domain']}"][row["judgement"]] += 1
    for sid in included_study_ids:
        if sid not in quality_by_study:
            add("sr.quality_missing", "high", f"included study {sid} has no domain-level quality appraisal",
                study_id=sid)
    quality_summary = {
        "weighting": "unweighted; every included study contributes one per domain",
        "by_domain": [{"tool_domain": key, "counts": dict(counts_), "n": sum(counts_.values()),
                       "proportions": {j: count / sum(counts_.values()) for j, count in counts_.items()}}
                      for key, counts_ in domain_counts.items()],
        "overall": {"counts": dict(overall_counts), "n": sum(overall_counts.values())},
    }

    # Conflict detection, clinical heterogeneity and optional complete-group meta-analysis.
    groups: dict[str, list[dict]] = defaultdict(list)
    for record in synthesis_members:
        groups[_text(record.get("comparison_key"))].append(record)
    heterogeneity: list[dict] = []
    meta_results: list[dict] = []
    settings = spec.get("synthesis_settings") if isinstance(spec.get("synthesis_settings"), dict) else {}
    allow_meta = settings.get("allow_meta_analysis") is True
    primary_overall = set(_items(settings.get("primary_overall")) or sorted(PRIMARY_DEFAULT))
    for key, members in groups.items():
        domain_fields = ("design", "population", "intervention", "comparator", "outcome", "followup", "direction")
        variation = {field: sorted({_text(row.get(field)) for row in members}) for field in domain_fields}
        risks = sorted({(quality_by_study.get(row["_study_id"]) or {}).get("overall_computed", "undetermined")
                        for row in members})
        effect_measures = sorted({_text((row.get("effect") or {}).get("measure")) for row in members})
        clinical = any(len(variation[field]) > 1 for field in
                       ("design", "population", "intervention", "comparator", "outcome", "followup"))
        meta = _pool(members, allow_meta)
        primary_members = [row for row in members
                           if (quality_by_study.get(row["_study_id"]) or {}).get("overall_computed") in primary_overall]
        sensitivity = {"primary_study_ids": [row["_study_id"] for row in primary_members],
                       "excluded_from_primary_ids": [row["_study_id"] for row in members if row not in primary_members],
                       "primary_pool": _pool(primary_members, allow_meta) if len(primary_members) != len(members) else None}
        row = {"comparison_key": key, "study_ids": [row["_study_id"] for row in members],
               "variation": variation, "risk_of_bias": risks, "effect_measures": effect_measures,
               "clinical_or_methodological_heterogeneity": clinical,
               "direction_conflict": len(variation["direction"]) > 1,
               "pooling_decision": "computed_but_exploratory" if meta.get("computed") and not meta.get("headline_allowed")
                                    else ("computed" if meta.get("computed") else "narrative_only"),
               "meta_analysis": meta, "sensitivity_by_risk": sensitivity}
        heterogeneity.append(row)
        if meta.get("computed"):
            meta_results.append({"comparison_key": key, **meta})
        if clinical or meta.get("I2_percent", 0) >= 50:
            uncertain("heterogeneity", f"比较组 {key} 存在临床/方法或统计异质性，不能做无条件合并解释。",
                      comparison_key=key, I2_percent=meta.get("I2_percent"), variation=variation)

    def resolve(refs: Any, owner: str, role: str) -> list[str]:
        clean = []
        for value in _items(refs):
            ref = _text(value)
            ev = evidence_map.get(ref)
            if ev is None:
                add("sr.claim_evidence_unresolved", "high", f"{owner} {role} reference {ref} does not resolve",
                    owner=owner, role=role)
            elif not ev["included"]:
                add("sr.excluded_evidence_cited", "high", f"{owner} cites non-included evidence {ref}",
                    owner=owner, role=role)
            else:
                clean.append(ref)
        return clean

    claims_out: list[dict] = []
    cited_reports: set[str] = set()
    for pos, claim in enumerate(_items(spec.get("synthesis_claims"))):
        if not isinstance(claim, dict):
            add("sr.claim_row_invalid", "high", "synthesis claim entry is not an object", claim_index=pos)
            continue
        cid = _text(claim.get("id")) or f"C{pos + 1:02d}"
        statement = _text(claim.get("statement"))
        ctype = _text(claim.get("type")) or "synthesis"
        key = _text(claim.get("comparison_key"))
        if not statement or key not in groups:
            add("sr.claim_scope_invalid", "high", f"claim {cid} needs statement and a valid comparison_key",
                claim_id=cid)
        support = resolve(claim.get("support_evidence_refs"), cid, "support")
        contra = resolve(claim.get("contradicting_evidence_refs"), cid, "contradicting")
        if not support:
            add("sr.claim_support_missing", "high", f"claim {cid} has no included support", claim_id=cid)
        sr = {evidence_map[ref]["report_id"] for ref in support}
        cr = {evidence_map[ref]["report_id"] for ref in contra}
        cited_reports |= sr | cr
        meta = next((row["meta_analysis"] for row in heterogeneity if row["comparison_key"] == key), None)
        group_records = groups.get(key, [])
        all_group_reports = {row["_id"] for row in group_records}
        used_reports = sr | cr
        opposing = any(row.get("direction") != next(iter(group_records), {}).get("direction") for row in group_records)
        omitted = all_group_reports - used_reports if opposing else set()
        ifctype = ctype == "contradiction"
        if ctype == "contradiction" and (not cr or not sr or sr == cr):
            add("sr.contradiction_not_two_sided", "high", f"contradiction {cid} lacks independent sides",
                claim_id=cid)
            strength = "undetermined"
        elif ctype == "contradiction" or omitted or contra:
            strength = "contested"
        elif len({evidence_map[ref]["study_id"] for ref in support}) < 2:
            strength = "suggestive"
        elif meta and meta.get("computed") and not meta.get("headline_allowed"):
            strength = "contested"
        else:
            strength = "established_within_scope"
        if omitted:
            add("sr.claim_omits_opposing_reports", "high", f"claim {cid} omits primary reports {sorted(omitted)}",
                claim_id=cid)
        related_studies = {evidence_map[ref]["study_id"] for ref in support + contra}
        primary_studies = {sid for sid in related_studies
                           if (quality_by_study.get(sid) or {}).get("overall_computed") in primary_overall}
        sensitivity_changed = related_studies != primary_studies and (len(primary_studies) < 2 or ctype == "contradiction")
        if sensitivity_changed:
            uncertain("risk_sensitivity", f"论断 {cid} 在排除高/不明确偏倚研究后证据基础改变，主结论必须降级。",
                      claim_id=cid, primary_study_ids=sorted(primary_studies),
                      all_study_ids=sorted(related_studies))
        claims_out.append({"claim_id": cid, "type": ctype, "comparison_key": key, "statement": statement,
                           "computed_strength": strength, "support_evidence_refs": support,
                           "contradicting_evidence_refs": contra, "support_reports": sorted(sr),
                           "contradicting_reports": sorted(cr), "omitted_opposing_reports": sorted(omitted),
                           "all_study_ids": sorted(related_studies), "primary_study_ids_after_risk_filter": sorted(primary_studies),
                           "sensitivity_changed": sensitivity_changed, "heterogeneity": meta,
                           "citations": [evidence_map[ref] for ref in support + contra]})
    for group in heterogeneity:
        if not group.get("direction_conflict"):
            continue
        key = group["comparison_key"]
        group = next(row for row in heterogeneity if row["comparison_key"] == key)
        covered = False
        for claim in claims_out:
            if claim["type"] == "contradiction" and claim["comparison_key"] == key:
                cited = set(claim["support_reports"]) | set(claim["contradicting_reports"])
                required = {row["_id"] for row in groups[key]}
                if required <= cited:
                    covered = True
        if not covered:
            add("sr.conflict_unaddressed", "high",
                f"comparison group {key} has opposite directions without complete two-sided synthesis",
                comparison_key=key)
            uncertain("conflict", f"比较组 {key} 的相反方向未被完整并陈。", comparison_key=key)
    if included and not claims_out:
        add("sr.synthesis_missing", "high", "included studies have no synthesis claims")

    gaps_out: list[dict] = []
    for pos, gap in enumerate(_items(spec.get("research_gaps"))):
        if not isinstance(gap, dict):
            add("sr.gap_row_invalid", "medium", "research gap is not an object", gap_index=pos)
            continue
        gid = _text(gap.get("id")) or f"G{pos + 1:02d}"
        refs = resolve(gap.get("positive_evidence_refs"), gid, "positive_gap")
        cited_reports |= {evidence_map[ref]["report_id"] for ref in refs}
        gap_scope_rows = [row for row in _items(gap.get("scope_checks")) if isinstance(row, dict)]
        complete_checks = bool(gap_scope_rows) and all(all(_text(row.get(field)) for field in
                       ("source", "query", "covered_years", "outcome")) for row in gap_scope_rows)
        if refs and complete_checks:
            gap_status = "supported_bounded_gap"
        else:
            gap_status = "undetermined"
            add("sr.gap_evidence_or_scope_missing", "medium",
                f"gap {gid} needs positive evidence and source/query/year/outcome checks", gap_id=gid)
        gaps_out.append({"gap_id": gid, "statement": gap.get("statement"), "computed_status": gap_status,
                         "positive_evidence_refs": refs, "scope_checks": gap_scope_rows,
                         "bounded_conclusion": gap.get("bounded_conclusion"),
                         "citations": [evidence_map[ref] for ref in refs]})
    for record in included:
        if record["_id"] not in cited_reports and record.get("context_only") is not True:
            add("sr.included_report_not_synthesized", "medium",
                f"included report {record['_id']} is absent from synthesis and gaps", report_id=record["_id"])

    for item in _items(spec.get("uncertainties")):
        if isinstance(item, dict):
            uncertain(str(item.get("kind") or "declared"), _text(item.get("message")) or "declared uncertainty",
                      **{k: v for k, v in item.items() if k not in {"kind", "message"}})
        elif _text(item):
            uncertain("declared", _text(item))
    severity_counts = {level: sum(row["severity"] == level for row in findings)
                       for level in ("high", "medium", "low")}
    status = "blocked" if severity_counts["high"] else ("review" if findings else "clean")
    prisma_counts = counts if execution != "prospective" else {key: None for key in counts}
    prisma = {
        "scope": execution, "counts": prisma_counts, "checks": checks if execution != "prospective" else {},
        "complete": execution != "prospective" and all(checks.values()) and not ta_undetermined and not ft_undetermined,
        "ta_exclusion_reason_counts": dict(ta_reasons) if execution != "prospective" else {},
        "ft_exclusion_reason_counts": dict(ft_reasons) if execution != "prospective" else {},
        "included_report_ids": [row["_id"] for row in included] if execution != "prospective" else [],
        "included_study_ids": included_study_ids if execution != "prospective" else [],
        "duplicate_rows": duplicate_rows,
        "warning": "fixed_corpus counts describe supplied rows only; prospective nulls are not zero",
    }
    return {
        "schema_version": SCHEMA, "status": status, "research_question": question,
        "search_protocol": {**protocol, "databases": search_rows}, "search_log": search_rows,
        "screening_log": screening_log, "prisma_flow": prisma, "evidence_matrix": evidence_rows,
        "quality_appraisals": list(quality_by_study.values()), "quality_summary": quality_summary,
        "heterogeneity": heterogeneity, "meta_analysis": meta_results, "synthesis_claims": claims_out,
        "research_gaps": gaps_out,
        "citation_coverage": {"included_reports": len(included), "cited_reports": len(cited_reports & {r["_id"] for r in included}),
                              "uncited_report_ids": sorted({r["_id"] for r in included} - cited_reports),
                              "claims": len(claims_out),
                              "claims_with_locators": sum(bool(row["citations"]) for row in claims_out)},
        "uncertainties": uncertainties, "uncertainty": uncertainties,
        "findings": findings, "severity_counts": severity_counts,
        "checked": {"raw_records": len(raw_records), "screened": len(candidates), "included_reports": len(included),
                    "included_studies": len(included_study_ids), "quality_studies": len(quality_by_study),
                    "evidence_rows": len(evidence_rows), "heterogeneity_groups": len(heterogeneity)},
        "limits": ["No live database search is performed. Executed exports must reconcile exactly; fixed-corpus counts are snapshot-relative.",
                   "Narrative and quantitative synthesis require source-reading. I2/Q/tau2 do not alone prove or refute clinical poolability.",
                   "Overall risk is computed from supplied domain judgements; no causal or GRADE claim is made.",
                   "Prospective PRISMA counts remain null rather than fabricated zeroes."],
        "change_records": [{"sequence": 1, "action": "protocol_screen_appraise_synthesize",
                            "basis": "versioned protocol, two-stage log, exact evidence and sensitivity analysis"}],
    }
