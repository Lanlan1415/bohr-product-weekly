"""Deterministic, evidence-bounded research topic and novelty evaluation.

The engine does not search the web and does not infer scientific novelty from
keyword absence.  It audits a prospectively declared search, compares supplied
works, evaluates explicit prior-art collisions and computes a bounded decision.
Only Python's standard library is used.
"""
from __future__ import annotations

from typing import Any

SCHEMA = "topic-evaluation/v2"
ASPECTS = ("task", "method", "data", "metric", "conclusion")
CLAIM_TYPES = {"method", "data", "scene_transfer", "conclusion_correction"}
COLLISIONS = {
    "direct_precedent", "renamed_mechanism", "algebraic_equivalent",
    "statistical_equivalent", "routine_adaptation", "scene_transfer",
    "followup_work", "strong_baseline", "none",
}
DIRECT = {"direct_precedent", "renamed_mechanism", "algebraic_equivalent", "statistical_equivalent"}
TRANSFER = {"routine_adaptation", "scene_transfer"}
GRADES = {"P", "A", "M", "U"}
PREREQS = {"data", "compute", "experiment", "time", "personnel"}


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


def _meaningful_difference(value: Any) -> bool:
    text = _text(value).lower()
    return bool(text) and text not in {"none", "no", "nil", "无", "没有", "无差异", "n/a"}


def analyze(spec: dict) -> dict:
    findings: list[dict] = []
    uncertainty: list[dict] = []

    def add(rule: str, severity: str, message: str, **context: Any) -> None:
        findings.append({"rule": rule, "severity": severity, "message": message, **context})

    def uncertain(kind: str, message: str, **context: Any) -> None:
        row = {"kind": kind, "message": message, **context}
        if row not in uncertainty:
            uncertainty.append(row)

    # 1. A falsifiable question is structured, not a broad topic label.
    question = spec.get("research_question")
    if not isinstance(question, dict):
        add("topic.question_missing", "high", "research_question must be an object")
        question = {}
    q_required = ("statement", "object", "variables", "comparator", "outcome",
                  "expected_conclusion", "falsification_condition")
    for field in q_required:
        value = question.get(field)
        if not _text(value) and not _items(value):
            add("topic.question_field_missing", "high",
                f"research_question.{field} is required for a testable question", field=field)
    question_out = {field: question.get(field) for field in q_required}
    question_out["scope"] = question.get("scope")

    # 2. Search provenance: prospective and executed searches never share counts.
    protocol = spec.get("search_protocol")
    if not isinstance(protocol, dict):
        add("topic.search_protocol_missing", "high", "search_protocol must be an object")
        protocol = {}
    search_status = _text(protocol.get("status")) or "undetermined"
    if search_status not in {"executed", "fixed_corpus", "prospective"}:
        add("topic.search_status_unknown", "high",
            "search_protocol.status must be executed, fixed_corpus or prospective")
    for field in ("start_date", "end_date"):
        if not _text(protocol.get(field)):
            add("topic.search_boundary_missing", "high",
                f"search_protocol.{field} is required", field=field)
    if not _items(protocol.get("languages")) and not _text(protocol.get("languages")):
        add("topic.languages_missing", "medium", "language limits must be explicit")
    for field in ("inclusion_criteria", "exclusion_criteria"):
        if not _items(protocol.get(field)):
            add("topic.screening_criteria_missing", "high",
                f"search_protocol.{field} must contain testable criteria", field=field)
    sources = _items(protocol.get("sources"))
    if not sources:
        add("topic.sources_missing", "high", "at least one declared source is required")
    elif len(sources) < 2:
        add("topic.single_source", "medium",
            "only one source is declared; absence from one source cannot support a novelty conclusion")
    source_rows = []
    for pos, source in enumerate(sources):
        if not isinstance(source, dict):
            add("topic.source_row_invalid", "high", "source entry is not an object", source_index=pos)
            continue
        name = _text(source.get("name")) or f"source-{pos + 1}"
        for field in ("name", "query", "fields"):
            value = source.get(field)
            if not _text(value) and not _items(value):
                add("topic.source_field_missing", "high",
                    f"source {name} lacks {field}", source=name, field=field)
        query = _text(source.get("query"))
        if query and not any(token in query.upper() for token in (" AND ", " OR ", " NOT ", ":", "\"", "*")):
            add("topic.query_not_reproducible", "medium",
                f"source {name} query is a keyword string without explicit fields or boolean structure",
                source=name)
        searched_at = _text(source.get("searched_at") or source.get("snapshot_date"))
        if search_status in {"executed", "fixed_corpus"} and not searched_at:
            add("topic.search_date_missing", "high",
                f"{search_status} source {name} needs searched_at or snapshot_date", source=name)
        hit_count = source.get("hit_count")
        if search_status == "executed" and (not isinstance(hit_count, int) or isinstance(hit_count, bool) or hit_count < 0):
            add("topic.hit_count_invalid", "high",
                f"executed source {name} needs a non-negative integer hit_count", source=name)
        if search_status != "executed" and hit_count is not None:
            add("topic.unexecuted_count_present", "high",
                f"source {name} is {search_status}; a hit count cannot be presented as an executed result",
                source=name)
        source_rows.append({
            "name": name, "database": source.get("database"), "interface": source.get("interface"),
            "query": query, "fields": source.get("fields"), "coverage": source.get("coverage"),
            "searched_at": searched_at or None, "filters": source.get("filters"),
            "hit_count": hit_count if search_status == "executed" else None,
            "execution_status": search_status,
        })
    if search_status == "prospective":
        uncertain("search_not_executed", "检索式为前瞻协议；未执行的数据库检索不能证明已有工作集合完备或支持首创结论。")

    # 3. Work-level evidence and five-aspect comparison matrix.
    works = _items(spec.get("works"))
    if not works:
        add("topic.works_missing", "high", "the existing-work set is empty")
    work_map: dict[str, dict] = {}
    evidence_map: dict[str, dict] = {}
    matrix: list[dict] = []
    evidence_matrix: list[dict] = []
    closest_count = 0
    for pos, work in enumerate(works):
        if not isinstance(work, dict):
            add("topic.work_row_invalid", "high", "work entry is not an object", work_index=pos)
            continue
        wid = _text(work.get("id") or work.get("work_id")) or f"W{pos + 1:03d}"
        if wid in work_map:
            add("topic.work_id_duplicate", "high", f"duplicate work id {wid}", work_id=wid)
            continue
        work_map[wid] = work
        decision = _text(work.get("decision")) or "undetermined"
        if decision not in {"include", "exclude", "undetermined"}:
            add("topic.work_decision_unknown", "high",
                f"work {wid} decision must be include, exclude or undetermined", work_id=wid)
        if decision == "exclude" and not _text(work.get("exclusion_reason")):
            add("topic.exclusion_reason_missing", "high",
                f"excluded work {wid} needs a criterion-linked exclusion_reason", work_id=wid)
        if not _text(work.get("title")):
            add("topic.work_title_missing", "high", f"work {wid} has no title", work_id=wid)
        if work.get("closest") is True:
            closest_count += 1
        verification = (_text(work.get("verification")) or "U").upper()
        if verification not in GRADES:
            add("topic.evidence_grade_unknown", "medium",
                f"work {wid} verification must be P/A/M/U", work_id=wid)
            verification = "U"
        if verification in {"M", "U"}:
            uncertain("source_verification", f"{wid} 只有元数据或不可核验信息，不能承担决定性创新判断。",
                      work_id=wid, verification=verification)
        comparable = work.get("comparable")
        if not isinstance(comparable, bool):
            add("topic.comparability_unstated", "high",
                f"work {wid} must declare comparable true or false", work_id=wid)
        reasons = work.get("incomparable_reasons") if isinstance(work.get("incomparable_reasons"), dict) else {}
        if comparable is False and not any(_text(v) for v in reasons.values()):
            add("topic.incomparable_reason_missing", "high",
                f"work {wid} is not directly comparable but gives no aspect-specific reason", work_id=wid)
        ev_entries = _items(work.get("evidence"))
        by_aspect: dict[str, list[dict]] = {aspect: [] for aspect in ASPECTS}
        source_excerpt = work.get("source_excerpt")
        for ev_pos, ev in enumerate(ev_entries):
            if not isinstance(ev, dict):
                add("topic.evidence_row_invalid", "high", f"work {wid} evidence entry is not an object",
                    work_id=wid, evidence_index=ev_pos)
                continue
            aspect = _text(ev.get("aspect"))
            eid = _text(ev.get("id")) or f"{wid}:{aspect or 'evidence'}"
            quote = _text(ev.get("quote"))
            locator = _text(ev.get("locator"))
            if aspect not in ASPECTS:
                add("topic.evidence_aspect_unknown", "high",
                    f"evidence {eid} must name one of {', '.join(ASPECTS)}", work_id=wid)
                continue
            if not quote or not locator:
                add("topic.evidence_locator_missing", "high",
                    f"evidence {eid} requires verbatim quote and exact locator", work_id=wid, aspect=aspect)
            if eid in evidence_map:
                add("topic.evidence_id_duplicate", "high", f"duplicate evidence id {eid}", work_id=wid)
                continue
            if isinstance(source_excerpt, str) and source_excerpt and quote and quote not in source_excerpt:
                add("topic.quote_not_in_source", "high",
                    f"evidence {eid} quote is not a verbatim substring of source_excerpt", work_id=wid)
            row = {
                "evidence_id": eid, "work_id": wid, "title": work.get("title"),
                "doi": work.get("doi"), "year": work.get("year"), "source": ev.get("source") or work.get("source"),
                "decision": decision, "include_exclude_reason": work.get("exclusion_reason") or work.get("inclusion_reason"),
                "verification": verification, "aspect": aspect, "value": work.get(aspect),
                "quote": quote, "locator": locator,
            }
            evidence_map[eid] = row
            by_aspect[aspect].append(row)
            evidence_matrix.append(row)
        cells = {}
        for aspect in ASPECTS:
            if not _text(work.get(aspect)):
                add("topic.comparison_field_missing", "high",
                    f"work {wid} lacks comparable field {aspect}", work_id=wid, aspect=aspect)
            if not by_aspect[aspect]:
                add("topic.comparison_evidence_missing", "high",
                    f"work {wid} field {aspect} has no evidence row", work_id=wid, aspect=aspect)
            cells[aspect] = {
                "value": work.get(aspect), "evidence_ids": [row["evidence_id"] for row in by_aspect[aspect]],
                "incomparable_reason": reasons.get(aspect),
            }
        matrix.append({
            "work_id": wid, "title": work.get("title"), "doi": work.get("doi"), "year": work.get("year"),
            "decision": decision, "include_exclude_reason": work.get("exclusion_reason") or work.get("inclusion_reason"),
            "closest": work.get("closest") is True, "closest_reason": work.get("closest_reason"),
            "verification": verification, "comparable": comparable,
            "incomparable_reasons": reasons, **cells,
        })
    if works and closest_count == 0:
        add("topic.closest_work_missing", "high", "no work is identified as genuinely closest prior work")

    def check_refs(refs: Any, claim_id: str, role: str) -> list[str]:
        clean = []
        for ref in _items(refs):
            ref_text = _text(ref)
            if ref_text not in evidence_map:
                add("topic.claim_evidence_unresolved", "high",
                    f"claim {claim_id} {role} reference {ref_text or '<empty>'} does not resolve",
                    claim_id=claim_id, role=role)
            else:
                clean.append(ref_text)
        return clean

    # 4. Independent novelty gates: collisions, residual difference and counter-evidence.
    claims = _items(spec.get("innovation_claims"))
    if not claims:
        add("topic.innovation_claims_missing", "high", "at least one innovation claim must be audited")
    novelty_rows = []
    novelty_statuses = []
    for pos, claim in enumerate(claims):
        if not isinstance(claim, dict):
            add("topic.innovation_row_invalid", "high", "innovation claim is not an object", claim_index=pos)
            continue
        cid = _text(claim.get("id")) or f"I{pos + 1:02d}"
        statement = _text(claim.get("statement"))
        claim_type = _text(claim.get("type"))
        if not statement:
            add("topic.innovation_statement_missing", "high", f"claim {cid} has no statement", claim_id=cid)
        if claim_type not in CLAIM_TYPES:
            add("topic.innovation_type_unknown", "high",
                f"claim {cid} type must be method/data/scene_transfer/conclusion_correction", claim_id=cid)
        difference_refs = check_refs(claim.get("difference_evidence_refs"), cid, "difference")
        comparisons = _items(claim.get("nearest_comparisons"))
        if not comparisons:
            add("topic.nearest_comparison_missing", "high",
                f"claim {cid} has no nearest-work collision audit", claim_id=cid)
        comparison_rows = []
        direct_covered = False
        residual = False
        transfer_only = bool(comparisons)
        counter_rows = []
        comparison_complete = True
        for comp_pos, comp in enumerate(comparisons):
            if not isinstance(comp, dict):
                add("topic.collision_row_invalid", "high", f"claim {cid} collision row is not an object",
                    claim_id=cid, comparison_index=comp_pos)
                comparison_complete = False
                continue
            wid = _text(comp.get("work_id"))
            collision = _text(comp.get("collision"))
            if wid not in work_map:
                add("topic.collision_work_unknown", "high",
                    f"claim {cid} references unknown work {wid}", claim_id=cid, work_id=wid)
                comparison_complete = False
            if collision not in COLLISIONS:
                add("topic.collision_type_unknown", "high",
                    f"claim {cid} has unsupported collision type {collision}", claim_id=cid, work_id=wid)
                comparison_complete = False
            if "same_constraints" not in comp:
                add("topic.constraints_unstated", "medium",
                    f"claim {cid} / {wid} does not state whether constraints and information match",
                    claim_id=cid, work_id=wid)
            refs = check_refs(comp.get("evidence_refs"), cid, f"collision:{wid}")
            if not refs:
                add("topic.collision_evidence_missing", "high",
                    f"claim {cid} collision with {wid} has no exact evidence", claim_id=cid, work_id=wid)
                comparison_complete = False
            difference = _text(comp.get("remaining_difference"))
            has_difference = _meaningful_difference(difference)
            if collision in DIRECT and not has_difference:
                direct_covered = True
            if collision in DIRECT and has_difference:
                residual = True
            if collision not in TRANSFER:
                transfer_only = False
            counters = check_refs(comp.get("counterevidence_refs"), cid, f"counterevidence:{wid}")
            for ref in counters:
                counter_rows.append({"work_id": wid, "evidence_id": ref,
                                     "response": comp.get("counterevidence_response")})
                if not _text(comp.get("counterevidence_response")):
                    add("topic.counterevidence_unresolved", "medium",
                        f"claim {cid} has unanswered counter-evidence {ref}",
                        claim_id=cid, evidence_id=ref)
                    uncertain("counterevidence", f"创新点 {cid} 存在未回应反证 {ref}，不能写成已被排除。",
                              claim_id=cid, evidence_id=ref)
            comparison_rows.append({
                "work_id": wid, "collision": collision, "same_constraints": comp.get("same_constraints"),
                "remaining_difference": difference or None, "evidence_refs": refs,
                "counterevidence_refs": counters, "counterevidence_response": comp.get("counterevidence_response"),
            })
        work_grades = [matrix_row["verification"] for matrix_row in matrix
                       if matrix_row["work_id"] in {_text(c.get("work_id")) for c in comparisons if isinstance(c, dict)}]
        evidence_sufficient = bool(work_grades) and all(grade in {"P", "A"} for grade in work_grades)
        if direct_covered:
            computed = "covered_by_prior_work"
        elif counter_rows and any(not _text(row.get("response")) for row in counter_rows):
            computed = "contested_in_scope"
        elif residual:
            computed = "specific_residual_difference" if difference_refs and comparison_complete else "undetermined"
        elif transfer_only or (claim_type == "scene_transfer" and comparisons):
            computed = "incremental_transfer_not_method_first"
        elif (comparison_complete and difference_refs and evidence_sufficient
              and search_status in {"executed", "fixed_corpus"} and len(source_rows) >= 2):
            computed = "not_covered_in_declared_scope"
        else:
            computed = "undetermined"
        if computed == "undetermined":
            add("topic.novelty_undetermined", "high",
                f"claim {cid} cannot be graded from complete searches, exact evidence and collision checks",
                claim_id=cid)
        novelty_statuses.append(computed)
        novelty_rows.append({
            "claim_id": cid, "statement": statement, "type": claim_type,
            "difference_evidence_refs": difference_refs, "nearest_comparisons": comparison_rows,
            "computed_status": computed,
            "bounded_conclusion": _novelty_conclusion(computed),
            "scope": "declared sources, dates and supplied existing-work set only; never global first",
            "counterevidence": counter_rows,
        })

    # 5. Feasibility: each premise is sourced or an explicit testable assumption.
    feasibility = spec.get("feasibility") if isinstance(spec.get("feasibility"), dict) else {}
    prerequisites = _items(feasibility.get("prerequisites"))
    categories = set()
    prereq_rows = []
    for pos, pre in enumerate(prerequisites):
        if not isinstance(pre, dict):
            add("topic.prerequisite_row_invalid", "high", "feasibility prerequisite is not an object",
                prerequisite_index=pos)
            continue
        pid = _text(pre.get("id")) or f"P{pos + 1:02d}"
        category = _text(pre.get("category"))
        categories.add(category)
        status = _text(pre.get("status")) or "unknown"
        if status not in {"verified", "assumed", "planned", "missing", "unknown"}:
            add("topic.prerequisite_status_unknown", "high",
                f"prerequisite {pid} has unsupported status {status}", prerequisite_id=pid)
        if not _text(pre.get("requirement")):
            add("topic.prerequisite_requirement_missing", "high",
                f"prerequisite {pid} lacks a testable requirement", prerequisite_id=pid)
        if status == "verified" and (not _text(pre.get("source")) or not _text(pre.get("locator"))):
            add("topic.verified_premise_unsourced", "high",
                f"verified prerequisite {pid} needs source and exact locator", prerequisite_id=pid)
        if status in {"assumed", "planned"} and (not _text(pre.get("assumption")) or not _text(pre.get("validation"))):
            add("topic.assumption_validation_missing", "high",
                f"{status} prerequisite {pid} needs explicit assumption and validation", prerequisite_id=pid)
        critical = pre.get("critical") is True
        if critical and status in {"missing", "unknown"}:
            add("topic.critical_prerequisite_unresolved", "high",
                f"critical prerequisite {pid} is {status}", prerequisite_id=pid, category=category)
        if status in {"assumed", "planned"}:
            uncertain("feasibility_assumption", f"前提 {pid} 尚未核实；结论以其声明的验证步骤通过为条件。",
                      prerequisite_id=pid, status=status)
        prereq_rows.append({
            "id": pid, "category": category, "requirement": pre.get("requirement"),
            "status": status, "critical": critical, "source": pre.get("source"),
            "locator": pre.get("locator"), "assumption": pre.get("assumption"),
            "validation": pre.get("validation"), "impact_if_false": pre.get("impact_if_false"),
        })
    for category in sorted(PREREQS - categories):
        add("topic.feasibility_category_missing", "high",
            f"feasibility does not audit {category}", category=category)
    route_rows = []
    for pos, step in enumerate(_items(feasibility.get("route"))):
        if not isinstance(step, dict):
            add("topic.route_row_invalid", "high", "route step is not an object", route_index=pos)
            continue
        sid = _text(step.get("id")) or f"R{pos + 1:02d}"
        for field in ("input", "output", "cost", "risk", "fallback"):
            if not _text(step.get(field)):
                add("topic.route_field_missing", "high",
                    f"route {sid} lacks {field}", route_id=sid, field=field)
        route_rows.append({"id": sid, **{field: step.get(field) for field in
                           ("input", "output", "cost", "risk", "fallback", "validates")}})
    if not route_rows:
        add("topic.route_missing", "high", "feasibility.route has no executable steps")
    critical_missing = any(row["critical"] and row["status"] == "missing" for row in prereq_rows)
    critical_unknown = any(row["critical"] and row["status"] == "unknown" for row in prereq_rows)
    conditional_pre = any(row["status"] in {"assumed", "planned"} for row in prereq_rows)
    if critical_unknown:
        feasibility_status = "undetermined"
    elif critical_missing:
        feasibility_status = "not_currently_feasible"
    elif conditional_pre:
        feasibility_status = "conditionally_feasible"
    else:
        feasibility_status = "feasible_within_declared_resources"
    impact = spec.get("impact") if isinstance(spec.get("impact"), dict) else {}
    for field in ("scientific", "practical"):
        if not _text(impact.get(field)):
            add("topic.impact_missing", "medium", f"impact.{field} is required", field=field)

    high_rules = {row["rule"] for row in findings if row["severity"] == "high"}
    if novelty_statuses and any(status == "covered_by_prior_work" for status in novelty_statuses):
        grade = "revise_and_recheck"
    elif critical_missing:
        grade = "pre_study_required"
    elif (critical_unknown or not novelty_statuses or any(status in {"undetermined", "contested_in_scope"}
          for status in novelty_statuses) or high_rules):
        grade = "undetermined"
    elif conditional_pre or feasibility_status != "feasible_within_declared_resources":
        grade = "conditional_go"
    else:
        grade = "go_within_scope"
    decision_reasons = {
        "go_within_scope": "创新碰撞、检索范围和全部关键资源前提均在声明边界内通过；不表示全球首创或实验已成功。",
        "conditional_go": "仅在列明假设经路线验证、回退方案仍成立时推进；任何前提失败都需重评。",
        "pre_study_required": "关键资源缺失或只有迁移型增量，先做最低成本预研究，不进入完整项目承诺。",
        "revise_and_recheck": "至少一条核心创新陈述被已有工作直接覆盖，必须缩小或重写创新点后重新检索。",
        "undetermined": "证据、检索或关键前提不足，不能给出肯定或否定首创/可行性结论。",
    }
    severity_counts = {level: sum(1 for row in findings if row["severity"] == level)
                       for level in ("high", "medium", "low")}
    status = "blocked" if severity_counts["high"] else ("review" if findings else "clean")
    for item in _items(spec.get("uncertainties")):
        if isinstance(item, dict):
            uncertain(str(item.get("kind") or "declared"), _text(item.get("message")) or "declared uncertainty",
                      **{k: v for k, v in item.items() if k not in {"kind", "message"}})
        elif _text(item):
            uncertain("declared", _text(item))
    gaps = list(_items(spec.get("gaps")))
    if search_status == "prospective":
        gaps.append("实际数据库检索及命中集合尚未形成，现有工作集合完整性未决。")
    result = {
        "schema_version": SCHEMA, "status": status, "research_question": question_out,
        "search_protocol": {**protocol, "sources": source_rows},
        "comparison_matrix": matrix, "evidence_matrix": evidence_matrix,
        "novelty_assessment": novelty_rows,
        "feasibility_assessment": {
            "computed_status": feasibility_status, "prerequisites": prereq_rows,
            "route": route_rows, "impact": impact,
        },
        "decision": {
            "grade": grade, "reason": decision_reasons[grade],
            "novelty_scope": "not global novelty; bounded to declared sources and work set",
            "independent_gates": ["research_question", "search_coverage", "prior_art_collision",
                                  "counterevidence", "feasibility"],
        },
        "research_gaps": gaps, "uncertainties": uncertainty, "uncertainty": uncertainty,
        "findings": findings, "severity_counts": severity_counts,
        "checked": {"works": len(matrix), "evidence_rows": len(evidence_matrix),
                    "innovation_claims": len(novelty_rows), "sources": len(source_rows),
                    "prerequisites": len(prereq_rows)},
        "limits": ["This is a deterministic audit of supplied evidence, not live retrieval or proof of global novelty.",
                   "P/A/M/U describes source verification, not study quality or effect certainty."],
        "change_records": [{"sequence": 1, "action": "computed_bounded_evaluation",
                            "basis": "declared protocol, work evidence, collisions and resource premises"}],
    }
    return result


def _novelty_conclusion(status: str) -> str:
    return {
        "covered_by_prior_work": "核心陈述在至少一项相近工作中被直接覆盖；不得继续宣称为新方法或首创。",
        "specific_residual_difference": "直接先例存在，但剩余差异有明确定位；只能主张该具体差异，需进一步反证。",
        "incremental_transfer_not_method_first": "属于常规模型适配或场景迁移，不能升级为方法理论首创。",
        "contested_in_scope": "存在未回应的相反证据，创新性结论保持争议状态。",
        "not_covered_in_declared_scope": "在声明数据库、日期、检索式和已比较工作集合内未被直接覆盖；不等于全球无人研究。",
        "undetermined": "证据或检索不足，创新性无法确定。",
    }.get(status, "创新性无法确定。")
