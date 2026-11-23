"""Evidence-table driven literature review generation and citation audit.

This is not an abstract concatenator.  It screens and deduplicates records,
validates theme membership against quotes, compares study fields, detects
opposing directions within comparable outcome groups, computes claim strength,
and generates a draft only from evidence-linked synthesis claims.
"""
from __future__ import annotations

import re
from collections import defaultdict
from typing import Any

SCHEMA = "review-generate/v2"
FIELDS = ("method", "data", "metric", "conclusion")
CLAIM_TYPES = {"consensus", "contradiction", "method_comparison", "data_comparison"}
DIRECTIONS = {"positive", "negative", "no_effect", "mixed", "not_reported"}


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
    text = re.sub(r"^https?://(?:dx\.)?doi\.org/", "", text)
    return text.rstrip(". ")


def _title(value: Any) -> str:
    return re.sub(r"[^a-z0-9\u4e00-\u9fff]+", "", _text(value).lower())


def analyze(spec: dict) -> dict:
    findings: list[dict] = []
    uncertainties: list[dict] = []

    def add(rule: str, severity: str, message: str, **context: Any) -> None:
        findings.append({"rule": rule, "severity": severity, "message": message, **context})

    def uncertain(kind: str, message: str, **context: Any) -> None:
        row = {"kind": kind, "message": message, **context}
        if row not in uncertainties:
            uncertainties.append(row)

    if not _text(spec.get("review_question")):
        add("review.question_missing", "high", "review_question is required")
    protocol = spec.get("screening_protocol") if isinstance(spec.get("screening_protocol"), dict) else {}
    if protocol.get("frozen_before_review") is not True:
        add("review.criteria_not_frozen", "high", "screening criteria must be frozen before synthesis")
    if not _text(protocol.get("version")):
        add("review.protocol_version_missing", "medium", "screening protocol version is missing")
    for field in ("inclusion_criteria", "exclusion_criteria"):
        if not _items(protocol.get(field)):
            add("review.criteria_missing", "high", f"screening_protocol.{field} is required", field=field)
    corpus = spec.get("corpus") if isinstance(spec.get("corpus"), dict) else {}
    if not _text(corpus.get("id")) or not _text(corpus.get("version")) or not _text(corpus.get("snapshot_date")):
        add("review.corpus_version_missing", "high", "corpus id/version/snapshot_date are required")
    sources = [row for row in _items(corpus.get("sources")) if isinstance(row, dict)]
    if not sources:
        add("review.sources_missing", "high", "at least one corpus source is required")
    for pos, source in enumerate(sources):
        if not _text(source.get("name")) or not _text(source.get("locator")):
            add("review.source_locator_missing", "high", "each corpus source needs name and locator", source_index=pos)

    raw_records = _items(spec.get("records"))
    if not raw_records:
        add("review.records_missing", "high", "no input records were supplied")
    records: list[dict] = []
    canonical: dict[str, str] = {}
    seen_ids: set[str] = set()
    duplicates: list[dict] = []
    malformed = 0
    screening_rows: list[dict] = []

    for pos, raw in enumerate(raw_records):
        if not isinstance(raw, dict):
            malformed += 1
            add("review.record_invalid", "high", "record entry is not an object", record_index=pos)
            continue
        rid = _text(raw.get("id") or raw.get("record_id")) or f"R{pos + 1:03d}"
        if rid in seen_ids:
            malformed += 1
            add("review.record_id_duplicate", "high", f"duplicate record id {rid}", record_id=rid)
            continue
        seen_ids.add(rid)
        key = _doi(raw.get("doi")) or _title(raw.get("title"))
        duplicate_of = _text(raw.get("duplicate_of")) or canonical.get(key)
        if key and key not in canonical:
            canonical[key] = rid
        record = dict(raw)
        record["_id"] = rid
        if duplicate_of:
            record["_computed_decision"] = "duplicate"
            record["_duplicate_of"] = duplicate_of
            duplicates.append({"record_id": rid, "duplicate_of": duplicate_of, "match_key": key or None})
        else:
            decision = _text(raw.get("decision")) or "undetermined"
            record["_computed_decision"] = decision
            if decision not in {"include", "exclude", "undetermined"}:
                add("review.screening_decision_invalid", "high",
                    f"record {rid} decision must be include/exclude/undetermined", record_id=rid)
            if decision == "exclude" and not _text(raw.get("exclusion_reason")):
                add("review.exclusion_reason_missing", "high",
                    f"excluded record {rid} needs a criterion-linked reason", record_id=rid)
            if decision == "include" and not _text(raw.get("inclusion_reason")):
                add("review.inclusion_reason_missing", "high",
                    f"included record {rid} needs a criterion-linked reason", record_id=rid)
        records.append(record)
        screening_rows.append({
            "record_id": rid, "title": raw.get("title"), "doi": raw.get("doi"), "year": raw.get("year"),
            "source": raw.get("source"), "computed_decision": record["_computed_decision"],
            "duplicate_of": record.get("_duplicate_of"),
            "reason": raw.get("exclusion_reason") or raw.get("inclusion_reason"),
            "full_text_status": raw.get("full_text_status"),
        })

    active = [row for row in records if row["_computed_decision"] == "include"]
    excluded = [row for row in records if row["_computed_decision"] == "exclude"]
    if raw_records and not active:
        add("review.no_included_records", "high", "no included records are available for synthesis")
    record_map = {row["_id"]: row for row in records}
    active_map = {row["_id"]: row for row in active}

    evidence_map: dict[str, dict] = {}
    evidence_rows: list[dict] = []
    for record in records:
        rid = record["_id"]
        included = record["_computed_decision"] == "include"
        source_excerpt = record.get("source_excerpt")
        for ev_pos, ev in enumerate(_items(record.get("evidence"))):
            if not isinstance(ev, dict):
                add("review.evidence_row_invalid", "high", f"record {rid} evidence entry is not an object",
                    record_id=rid, evidence_index=ev_pos)
                continue
            eid = _text(ev.get("id")) or f"{rid}:E{ev_pos + 1}"
            quote = _text(ev.get("quote"))
            locator = _text(ev.get("locator"))
            if eid in evidence_map:
                add("review.evidence_id_duplicate", "high", f"duplicate evidence id {eid}", record_id=rid)
                continue
            if not quote or not locator:
                add("review.evidence_locator_missing", "high",
                    f"evidence {eid} needs verbatim quote and exact locator", record_id=rid)
            if isinstance(source_excerpt, str) and source_excerpt and quote and quote not in source_excerpt:
                add("review.quote_not_in_source", "high",
                    f"evidence {eid} quote is absent from source_excerpt", record_id=rid)
            fields = [_text(value) for value in _items(ev.get("fields")) if _text(value)]
            row = {
                "evidence_id": eid, "record_id": rid, "title": record.get("title"),
                "doi": record.get("doi"), "year": record.get("year"), "source": record.get("source"),
                "screening_decision": record["_computed_decision"],
                "include_exclude_reason": record.get("inclusion_reason") or record.get("exclusion_reason"),
                "full_text_status": record.get("full_text_status"), "fields": fields,
                "comparison_key": record.get("comparison_key"), "direction": record.get("direction"),
                "quote": quote, "locator": locator,
            }
            evidence_map[eid] = row
            evidence_rows.append(row)
        if not included:
            continue
        full_status = _text(record.get("full_text_status")) or "undetermined"
        if full_status not in {"full_text", "abstract_only", "metadata_only"}:
            add("review.fulltext_status_unknown", "medium",
                f"record {rid} has unknown full_text_status", record_id=rid)
        if full_status != "full_text":
            uncertain("limited_text", f"{rid} 只有 {full_status}，证据强度和元数据完整性受限。",
                      record_id=rid, full_text_status=full_status)
        if _text(record.get("direction")) not in DIRECTIONS:
            add("review.direction_unknown", "high",
                f"included record {rid} needs a declared result direction", record_id=rid)
        if not _text(record.get("comparison_key")):
            add("review.comparison_key_missing", "high",
                f"included record {rid} needs a comparable outcome group key", record_id=rid)
        field_evidence = record.get("field_evidence") if isinstance(record.get("field_evidence"), dict) else {}
        for field in FIELDS:
            if not _text(record.get(field)):
                add("review.comparison_field_missing", "high",
                    f"record {rid} lacks {field}", record_id=rid, field=field)
            refs = [_text(ref) for ref in _items(field_evidence.get(field)) if _text(ref)]
            if not refs:
                add("review.field_evidence_missing", "high",
                    f"record {rid} field {field} has no evidence backlink", record_id=rid, field=field)

    # Resolve field references only after every record's evidence is indexed.  This
    # distinguishes a genuinely unknown ID from a valid ID owned by a later record.
    for record in active:
        rid = record["_id"]
        field_evidence = record.get("field_evidence") if isinstance(record.get("field_evidence"), dict) else {}
        for field in FIELDS:
            for ref_value in _items(field_evidence.get(field)):
                ref = _text(ref_value)
                if not ref:
                    continue
                if ref not in evidence_map:
                    add("review.field_evidence_unresolved", "high",
                        f"record {rid} field {field} reference {ref} does not resolve", record_id=rid, field=field)
                elif evidence_map[ref]["record_id"] != rid:
                    add("review.field_evidence_cross_record", "high",
                        f"record {rid} field {field} incorrectly cites {ref}", record_id=rid, field=field)

    # Theme membership is evidence-backed and may be multi-label; denominators stay explicit.
    themes = _items(spec.get("themes"))
    theme_map: dict[str, dict] = {}
    theme_members: dict[str, list[str]] = defaultdict(list)
    if not themes:
        add("review.themes_missing", "high", "no corpus-derived themes were declared")
    for pos, theme in enumerate(themes):
        if not isinstance(theme, dict):
            add("review.theme_row_invalid", "high", "theme entry is not an object", theme_index=pos)
            continue
        tid = _text(theme.get("id")) or f"T{pos + 1:02d}"
        if tid in theme_map:
            add("review.theme_id_duplicate", "high", f"duplicate theme id {tid}")
            continue
        if not _text(theme.get("label")) or not _text(theme.get("boundary")):
            add("review.theme_boundary_missing", "high",
                f"theme {tid} needs label and explicit boundary", theme_id=tid)
        theme_map[tid] = theme
    theme_assignments: list[dict] = []
    for record in active:
        rid = record["_id"]
        assignments = _items(record.get("theme_assignments"))
        if not assignments:
            add("review.record_unclustered", "high", f"included record {rid} has no evidence-backed theme",
                record_id=rid)
        for assignment in assignments:
            if not isinstance(assignment, dict):
                add("review.theme_assignment_invalid", "high", f"record {rid} theme assignment is not an object",
                    record_id=rid)
                continue
            tid = _text(assignment.get("theme_id"))
            if tid not in theme_map:
                add("review.theme_unknown", "high", f"record {rid} references unknown theme {tid}", record_id=rid)
                continue
            refs = [_text(ref) for ref in _items(assignment.get("evidence_refs")) if _text(ref)]
            if not _text(assignment.get("rationale")) or not refs:
                add("review.theme_rationale_missing", "high",
                    f"record {rid} / {tid} needs rationale and evidence_refs", record_id=rid, theme_id=tid)
            for ref in refs:
                if ref not in evidence_map or evidence_map[ref]["record_id"] != rid:
                    add("review.theme_evidence_unresolved", "high",
                        f"record {rid} theme {tid} reference {ref} is invalid", record_id=rid, theme_id=tid)
            theme_members[tid].append(rid)
            theme_assignments.append({"record_id": rid, "theme_id": tid,
                                      "rationale": assignment.get("rationale"), "evidence_refs": refs})
    for tid in theme_map:
        if not theme_members[tid]:
            add("review.empty_theme", "medium", f"theme {tid} has no included records", theme_id=tid)

    # Comparison matrix and automatic conflict candidates.
    comparison_rows: list[dict] = []
    groups: dict[str, list[dict]] = defaultdict(list)
    for record in active:
        rid = record["_id"]
        field_evidence = record.get("field_evidence") or {}
        comparison_rows.append({
            "record_id": rid, "title": record.get("title"), "year": record.get("year"),
            "theme_ids": [row["theme_id"] for row in theme_assignments if row["record_id"] == rid],
            "comparison_key": record.get("comparison_key"), "method": record.get("method"),
            "data": record.get("data"), "metric": record.get("metric"),
            "conclusion": record.get("conclusion"), "direction": record.get("direction"),
            "limitations": record.get("limitations"),
            "evidence_refs": {field: field_evidence.get(field) for field in FIELDS},
        })
        groups[_text(record.get("comparison_key"))].append(record)
    conflict_candidates: list[dict] = []
    for key, members in groups.items():
        directions = sorted({_text(row.get("direction")) for row in members
                             if _text(row.get("direction")) not in {"", "not_reported"}})
        if len(members) >= 2 and len(directions) >= 2:
            conflict_candidates.append({
                "comparison_key": key, "record_ids": [row["_id"] for row in members],
                "directions": directions, "status": "candidate_requires_synthesis",
            })

    def resolve_refs(refs: Any, claim_id: str, role: str) -> list[str]:
        clean = []
        for ref_value in _items(refs):
            ref = _text(ref_value)
            ev = evidence_map.get(ref)
            if ev is None:
                add("review.claim_evidence_unresolved", "high",
                    f"claim {claim_id} {role} reference {ref or '<empty>'} does not resolve",
                    claim_id=claim_id, role=role)
            elif ev["screening_decision"] != "include":
                add("review.excluded_evidence_cited", "high",
                    f"claim {claim_id} cites screened-out evidence {ref}", claim_id=claim_id, role=role)
            else:
                clean.append(ref)
        return clean

    claims_out: list[dict] = []
    covered_conflict_records: dict[str, set[str]] = defaultdict(set)
    cited_records: set[str] = set()
    for pos, claim in enumerate(_items(spec.get("synthesis_claims"))):
        if not isinstance(claim, dict):
            add("review.claim_row_invalid", "high", "synthesis claim entry is not an object", claim_index=pos)
            continue
        cid = _text(claim.get("id")) or f"C{pos + 1:02d}"
        ctype = _text(claim.get("type"))
        tid = _text(claim.get("theme_id"))
        statement = _text(claim.get("statement"))
        if ctype not in CLAIM_TYPES:
            add("review.claim_type_unknown", "high", f"claim {cid} has unsupported type {ctype}", claim_id=cid)
        if tid not in theme_map:
            add("review.claim_theme_unknown", "high", f"claim {cid} references unknown theme {tid}", claim_id=cid)
        if not statement:
            add("review.claim_statement_missing", "high", f"claim {cid} has no statement", claim_id=cid)
        support = resolve_refs(claim.get("support_evidence_refs"), cid, "support")
        contra = resolve_refs(claim.get("contradicting_evidence_refs"), cid, "contradicting")
        if not support:
            add("review.claim_support_missing", "high", f"claim {cid} has no included supporting evidence",
                claim_id=cid)
        support_records = {evidence_map[ref]["record_id"] for ref in support}
        contra_records = {evidence_map[ref]["record_id"] for ref in contra}
        cited_records |= support_records | contra_records
        all_records = support_records | contra_records
        key = _text(claim.get("comparison_key"))
        comparable = groups.get(key, [])
        conflicting_directions = sorted({_text(row.get("direction")) for row in comparable
                                         if _text(row.get("direction")) not in {"", "not_reported"}})
        omitted = {row["_id"] for row in comparable} - all_records if len(conflicting_directions) >= 2 else set()
        if omitted:
            add("review.claim_omits_conflict", "medium",
                f"claim {cid} omits comparable opposing records: {', '.join(sorted(omitted))}",
                claim_id=cid, record_ids=sorted(omitted))
        if ctype == "contradiction":
            if not contra or not support_records or not contra_records or support_records == contra_records:
                add("review.contradiction_not_two_sided", "high",
                    f"contradiction {cid} needs independent support and contradicting record sets", claim_id=cid)
                strength = "undetermined"
            else:
                strength = "contested"
                covered_conflict_records[key] |= all_records
        elif omitted or contra:
            strength = "contested"
        elif ctype == "consensus" and len(support_records) < 2:
            add("review.consensus_single_source", "medium",
                f"consensus {cid} has only one independent source", claim_id=cid)
            strength = "suggestive"
        elif ctype in {"method_comparison", "data_comparison"} and len(support_records) < 2:
            add("review.comparison_single_source", "medium",
                f"comparison {cid} needs at least two records", claim_id=cid)
            strength = "suggestive"
        else:
            statuses = {active_map[rid].get("full_text_status") for rid in all_records if rid in active_map}
            strength = "established" if len(all_records) >= 2 and statuses == {"full_text"} else "suggestive"
        claims_out.append({
            "claim_id": cid, "type": ctype, "theme_id": tid, "comparison_key": key,
            "statement": statement, "computed_strength": strength,
            "support_evidence_refs": support, "contradicting_evidence_refs": contra,
            "support_records": sorted(support_records), "contradicting_records": sorted(contra_records),
            "omitted_conflicting_records": sorted(omitted),
            "citations": [evidence_map[ref] for ref in support + contra],
        })
    if not claims_out:
        add("review.synthesis_claims_missing", "high", "no cross-study synthesis claims were supplied")
    for candidate in conflict_candidates:
        covered = covered_conflict_records.get(candidate["comparison_key"], set())
        required = set(candidate["record_ids"])
        if not required <= covered:
            candidate["status"] = "unaddressed_conflict"
            add("review.conflict_unaddressed", "medium",
                f"comparison {candidate['comparison_key']} has opposing directions not synthesized two-sided",
                comparison_key=candidate["comparison_key"])
            uncertain("conflict", f"比较组 {candidate['comparison_key']} 的相反结论未被完整并陈。",
                      comparison_key=candidate["comparison_key"], record_ids=candidate["record_ids"])
        else:
            candidate["status"] = "addressed_two_sided"

    # Research gaps need positive evidence plus a bounded resolution/coverage check.
    gaps_out: list[dict] = []
    for pos, gap in enumerate(_items(spec.get("research_gaps"))):
        if not isinstance(gap, dict):
            add("review.gap_row_invalid", "high", "research gap entry is not an object", gap_index=pos)
            continue
        gid = _text(gap.get("id")) or f"G{pos + 1:02d}"
        refs = resolve_refs(gap.get("positive_evidence_refs"), gid, "positive_gap")
        cited_records |= {evidence_map[ref]["record_id"] for ref in refs}
        checks = []
        for check in _items(gap.get("scope_checks")):
            if not isinstance(check, dict):
                add("review.gap_scope_row_invalid", "medium", f"gap {gid} scope check is not an object", gap_id=gid)
                continue
            complete = all(_text(check.get(field)) for field in ("source", "query", "covered_years", "outcome"))
            if not complete:
                add("review.gap_scope_incomplete", "medium",
                    f"gap {gid} scope check needs source/query/covered_years/outcome", gap_id=gid)
            checks.append({field: check.get(field) for field in
                           ("source", "query", "covered_years", "outcome", "status")})
        if refs and checks and all(all(_text(row.get(field)) for field in
                                      ("source", "query", "covered_years", "outcome")) for row in checks):
            computed = "supported_bounded_gap"
        elif refs:
            computed = "candidate_only_scope_check_missing"
            add("review.gap_scope_missing", "medium",
                f"gap {gid} has positive evidence but no complete bounded scope check", gap_id=gid)
        else:
            computed = "undetermined"
            add("review.gap_positive_evidence_missing", "medium",
                f"gap {gid} lacks direct positive evidence; absence from a corpus alone is insufficient", gap_id=gid)
        gaps_out.append({
            "gap_id": gid, "theme_id": gap.get("theme_id"), "type": gap.get("type"),
            "statement": gap.get("statement"), "computed_status": computed,
            "positive_evidence_refs": refs, "scope_checks": checks,
            "bounded_conclusion": gap.get("bounded_conclusion"),
            "scope": "supplied corpus and declared scope checks only; not a global absence claim",
            "citations": [evidence_map[ref] for ref in refs],
        })

    for record in active:
        rid = record["_id"]
        if rid not in cited_records:
            if record.get("context_only") is True and _text(record.get("context_only_reason")):
                uncertain("context_only", f"{rid} 仅作背景，不承担综合论断。",
                          record_id=rid, reason=record.get("context_only_reason"))
            else:
                add("review.record_not_synthesized", "medium",
                    f"included record {rid} is not cited by any synthesis claim or gap", record_id=rid)
    for item in _items(spec.get("uncertainties")):
        if isinstance(item, dict):
            uncertain(str(item.get("kind") or "declared"), _text(item.get("message")) or "declared uncertainty",
                      **{k: v for k, v in item.items() if k not in {"kind", "message"}})
        elif _text(item):
            uncertain("declared", _text(item))

    included_ids = list(active_map)
    coverage = {
        "included_records": len(included_ids), "cited_records": len(set(included_ids) & cited_records),
        "uncited_record_ids": sorted(set(included_ids) - cited_records),
        "record_coverage_ratio": round(len(set(included_ids) & cited_records) / len(included_ids), 6)
                                 if included_ids else 0,
        "claims": len(claims_out), "claims_with_locatable_citations": sum(
            bool(row["citations"]) and all(ev["quote"] and ev["locator"] for ev in row["citations"])
            for row in claims_out),
        "multi_label_theme_counts_not_exclusive": True,
    }
    severity_counts = {level: sum(row["severity"] == level for row in findings)
                       for level in ("high", "medium", "low")}
    status = "blocked" if severity_counts["high"] else ("review" if findings else "clean")
    screening = {
        "identified_input_rows": len(raw_records), "malformed_rows": malformed,
        "duplicates": len(duplicates), "screened_unique_records": len(records) - len(duplicates),
        "included": len(active), "excluded": len(excluded),
        "undetermined": sum(row["_computed_decision"] == "undetermined" for row in records),
        "duplicate_rows": duplicates,
        "arithmetic": "identified_input_rows = malformed_rows + duplicates + screened_unique_records",
    }
    return {
        "schema_version": SCHEMA, "status": status, "review_question": spec.get("review_question"),
        "corpus": corpus, "screening_protocol": protocol, "screening": screening,
        "screening_log": screening_rows, "themes": [
            {**theme_map[tid], "record_ids": theme_members[tid],
             "evidence_backed_assignments": [row for row in theme_assignments if row["theme_id"] == tid]}
            for tid in theme_map],
        "theme_assignments": theme_assignments, "comparison_matrix": comparison_rows,
        "conflict_candidates": conflict_candidates, "synthesis_claims": claims_out,
        "research_gaps": gaps_out, "evidence_matrix": evidence_rows,
        "citation_coverage": coverage, "uncertainties": uncertainties, "uncertainty": uncertainties,
        "findings": findings, "severity_counts": severity_counts,
        "checked": {"input_records": len(raw_records), "included_records": len(active),
                    "evidence_rows": len(evidence_rows), "themes": len(theme_map), "claims": len(claims_out)},
        "limits": ["The draft synthesizes only included records in the supplied snapshot; it is not live database retrieval.",
                   "Computed strength reflects evidence design and conflict coverage, not a formal GRADE rating.",
                   "Theme labels and scientific wording require source reading; deterministic code cannot validate semantic adequacy."],
        "change_records": [{"sequence": 1, "action": "screened_clustered_compared_and_synthesized",
                            "basis": "frozen protocol, verbatim evidence and two-sided claim coverage"}],
    }
