"""Question-decomposed, bounded scientific retrieval over supplied snapshots."""
from __future__ import annotations

import copy
import json
import re
from pathlib import Path
from typing import Any

import retrieval_common as C

SCHEMA_VERSION = "question-search/v2"
SCOPE_ROLES = {"object", "population", "context", "organism", "material", "研究对象", "对象"}


def expression_terms(expression: Any) -> list[str]:
    if isinstance(expression, list):
        return list(dict.fromkeys(str(t).strip() for t in expression if str(t).strip()))
    text = str(expression or "")
    quoted = re.findall(r'"([^"\n]+)"', text)
    if quoted:
        return list(dict.fromkeys(q.strip() for q in quoted if q.strip()))
    terms = C.query_terms(text)
    ignored = {"and", "or", "not", "title", "abs", "title_abs", "mesh", "lang", "first_pdate", "filter"}
    return [t for t in terms if t.casefold() not in ignored]


def concept(terms: list[str], cid: str, label: str, required: bool = True) -> dict[str, Any]:
    return {"concept_id": cid, "label": label, "role": "query", "terms": list(terms), "all_terms": list(terms),
            "synonyms": [], "controlled_terms": [], "required": required, "provenance": "subquestion_supplied"}


def normalize_query(item: Any, qid: str) -> tuple[list[dict[str, Any]], list[str], Any, bool]:
    if isinstance(item, str):
        terms = expression_terms(item)
        return ([concept(terms, qid, item)] if terms else []), [], item, False
    if not isinstance(item, dict):
        return [], [], item, False
    raw = item.get("query", item.get("q", item.get("search_query", item)))
    excluded = item.get("not", item.get("exclude", []))
    if isinstance(raw, dict):
        groups = []
        for i, term in enumerate(expression_terms(raw.get("all", []))):
            groups.append(concept([term], f"{qid}-A{i + 1}", f"ALL {term}"))
        any_terms = expression_terms(raw.get("any", []))
        if any_terms:
            groups.append(concept(any_terms, f"{qid}-OR", "ANY alternatives"))
        if not excluded:
            excluded = raw.get("not", raw.get("exclude", []))
        return groups, expression_terms(excluded), raw, len(groups) > 1
    terms = expression_terms(raw)
    return ([concept(terms, qid, str(raw))] if terms else []), expression_terms(excluded), raw, False


def raw_subquestions(spec: dict[str, Any]) -> list[Any]:
    for key in ("subquestions", "research_questions", "questions"):
        if isinstance(spec.get(key), list):
            return spec[key]
    question = spec.get("research_question")
    if isinstance(question, dict) and isinstance(question.get("subquestions"), list):
        return question["subquestions"]
    if isinstance(spec.get("question_plan"), dict) and isinstance(spec["question_plan"].get("subquestions"), list):
        return spec["question_plan"]["subquestions"]
    return []


def automatic_subquestions(spec: dict[str, Any]) -> list[dict[str, Any]]:
    question = C.research_question_text(spec)
    concepts = C.derive_concepts(spec, question)
    if not concepts:
        return []
    scopes = [c for c in concepts if c["role"] in SCOPE_ROLES]
    facets = [c for c in concepts if c not in scopes]
    rows = []
    if scopes and facets:
        for i, facet in enumerate(facets, 1):
            rows.append({"id": f"S{i:02d}", "question": f"{question} → {facet['role']} / {facet['label']}",
                         "concepts": scopes + [facet], "required": True, "depends_on": [],
                         "decomposition_rule": "shared object/population scope AND one mechanism/method/outcome facet"})
    elif len(concepts) == 1:
        rows.append({"id": "S01", "question": question or concepts[0]["label"], "concepts": concepts,
                     "required": True, "depends_on": [], "decomposition_rule": "one executable research facet"})
    else:
        for i, item in enumerate(concepts, 1):
            rows.append({"id": f"S{i:02d}", "question": f"{question} → {item['role']} / {item['label']}",
                         "concepts": [item], "required": True, "depends_on": [],
                         "decomposition_rule": "one independently answerable facet; no invented object scope"})
    return rows


def normalize_subquestions(spec: dict[str, Any]) -> list[dict[str, Any]]:
    raws = raw_subquestions(spec)
    output = []
    for i, raw in enumerate(raws or automatic_subquestions(spec), 1):
        if isinstance(raw, str):
            raw = {"question": raw}
        if not isinstance(raw, dict):
            raw = {"question": str(raw)}
        item = copy.deepcopy(raw)
        item["id"] = str(raw.get("id") or raw.get("subquestion_id") or f"S{i:02d}")
        item["question"] = str(raw.get("question") or raw.get("text") or raw.get("label") or item["id"])
        item["depends_on"] = [str(x) for x in (raw.get("depends_on") or raw.get("dependencies") or [])]
        item["required"] = raw.get("required", True) is not False
        local_spec = dict(spec)
        for key in ("concepts", "concept_groups", "facets", "term_groups"):
            if key in raw:
                local_spec[key] = raw[key]
        query_values = C.supplied_query_objects(raw)
        if not query_values and raw.get("query") is not None:
            query_values = [{"query_id": f"{item['id']}-Q01", "query": raw["query"]}]
        item["supplied_queries"] = query_values
        if query_values:
            item["concepts"] = []
        elif "concepts" not in item or not item["concepts"]:
            item["concepts"] = C.derive_concepts(local_spec, item["question"])
        output.append(item)
    ids = [item["id"] for item in output]
    if len(set(ids)) != len(ids):
        raise C.RetrievalError("question.subquestion_id_duplicate", "subquestion ids must be unique", 4)
    for item in output:
        unknown = set(item["depends_on"]) - set(ids)
        if unknown:
            raise C.RetrievalError("question.dependency_unknown",
                                   f"subquestion {item['id']} references unknown dependencies {sorted(unknown)}", 4)
        if item["id"] in item["depends_on"]:
            raise C.RetrievalError("question.dependency_cycle", f"subquestion {item['id']} depends on itself", 4)
    return output


def schedule(subquestions: list[dict[str, Any]]) -> list[list[str]]:
    ids = [s["id"] for s in subquestions]
    done: set[str] = set()
    batches = []
    while len(done) < len(ids):
        ready = [s["id"] for s in subquestions if s["id"] not in done and set(s["depends_on"]) <= done]
        if not ready:
            raise C.RetrievalError("question.dependency_cycle", "subquestion dependency graph has a cycle", 4)
        batches.append(ready)
        done.update(ready)
    return batches


def run_query(index: C.BM25Index, works_by_id: dict[str, dict[str, Any]], concepts: list[dict[str, Any]],
              scope: dict[str, Any], qid: str, round_name: str, subquestion_id: str,
              purpose: str, hard_all: bool, not_terms: list[str] | None = None,
              diagnostic: bool = False) -> dict[str, Any]:
    if not concepts or not any(c["all_terms"] or c["terms"] for c in concepts):
        raise C.RetrievalError("question.subquery_empty", f"{qid} contains no searchable terms", 4)
    rows = C.query_for_concepts(index, concepts, scope, hard_all=hard_all)
    if not_terms:
        rows = [row for row in rows if not C.matched_terms(not_terms, works_by_id[row["work_id"]]["fields"])]
    for row in rows:
        row["diagnostic_partial_only"] = diagnostic
    log = {
        "query_id": qid, "subquestion_id": subquestion_id, "round": round_name, "purpose": purpose,
        "execution_status": "fixed_snapshot_scanned", "diagnostic_partial_only": diagnostic,
        "concepts": copy.deepcopy(concepts),
        "boolean_logic": {"between_concepts": "AND" if hard_all else "OR",
                          "within_concept": "OR", "NOT": not_terms or [],
                          "promotion_rule": "diagnostic partial hits never become direct joint-question answers"},
        "fields": ["title", "abstract", "keywords", "body"],
        "time_boundary": {"from": scope.get("start_date"), "to": scope.get("end_date")},
        "language_boundary": scope.get("languages", []), "search_date": scope.get("search_date"),
        "source_queries": C.source_query_plans(concepts, scope),
        "local_snapshot_hit_count": len(rows), "local_snapshot_hit_work_ids": [r["work_id"] for r in rows],
        "remote_hit_count": None, "hits": rows,
        "excluded_from_boundary_or_boolean": [],
    }
    ids = {row["work_id"] for row in rows}
    for work_id, work in works_by_id.items():
        if work_id in ids:
            continue
        passed, reason = C.temporal_match(work, scope)
        if not passed:
            log["excluded_from_boundary_or_boolean"].append({"work_id": work_id, "reason": reason})
        elif not_terms and C.matched_terms(not_terms, work["fields"]):
            log["excluded_from_boundary_or_boolean"].append({"work_id": work_id, "reason": "matched declared NOT term"})
    if not rows:
        log["empty_result"] = {"status": "empty_within_fixed_snapshot", "remote_hit_count": None,
                               "explanation": "No supplied record satisfies this joint query and its declared boundaries. It is not global research-gap evidence.",
                               "next_action": "Inspect object/facet diagnostics or execute the separate planned API query; neither is claimed as a completed remote search."}
    return log


def assertion_conflicts(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    # Different wording across different studies is not automatically a
    # contradiction.  Compare only explicitly flagged sets, declared comparison
    # groups, or reports of one study; never infer scientific opposition by vote.
    flagged = any(bool(row.get("assertions", {}).get("conflicting_opinion")) for row in rows)
    groups: dict[str, list[dict[str, Any]]] = {"explicitly_flagged_subquestion": rows} if flagged else {}
    for row in rows:
        assertions = row.get("assertions", {})
        if assertions.get("comparison_key") not in (None, ""):
            groups.setdefault("comparison:" + str(assertions["comparison_key"]), []).append(row)
        if assertions.get("study_id") not in (None, ""):
            groups.setdefault("study:" + str(assertions["study_id"]), []).append(row)
    by_field: dict[str, list[dict[str, Any]]] = {}
    for group_name, members in groups.items():
        for row in members:
            for key, value in row.get("assertions", {}).items():
                if key in {"answer", "opinion", "stance", "direction", "conclusion", "finding", "conflicting_opinion"} \
                        and value not in (None, ""):
                    by_field.setdefault(key, []).append({"group": group_name, "work_id": row["work_id"], "value": value})
    conflicts = []
    for field, values in sorted(by_field.items()):
        unique = {json.dumps(v["value"], ensure_ascii=False, sort_keys=True) for v in values}
        if len(unique) > 1:
            conflicts.append({"field": field, "records": values,
                              "resolution": "both/all declared positions retained; no majority vote; human adjudication required"})
    return conflicts


def build_result(case: dict[str, Any], case_dir: Path) -> dict[str, Any]:
    spec = C.merged_spec(case)
    records = C.load_records(spec, case_dir)
    works, duplicate_audit, version_conflicts = C.deduplicate(records)
    works_by_id = {work["work_id"]: work for work in works}
    index = C.BM25Index(works)
    subquestions = normalize_subquestions(spec)
    if not subquestions:
        raise C.RetrievalError("question.no_subquestions", "research question could not be decomposed into searchable subquestions", 4)
    batches = schedule(subquestions)
    scope = C.temporal_scope(spec)
    result: dict[str, Any] = {"schema_version": SCHEMA_VERSION, "status": "clean", "case_id": case.get("case_id"),
                              "findings": [], "limits": [], "uncertainty": []}
    query_log: list[dict[str, Any]] = []
    subresults = []
    seen_work_best: dict[str, dict[str, Any]] = {}
    seen_work_queries: dict[str, list[str]] = {}
    by_sub_id = {item["id"]: item for item in subquestions}
    execution_subquestions = [by_sub_id[sid] for batch in batches for sid in batch]
    for sub in execution_subquestions:
        initial_rows: list[dict[str, Any]] = []
        diagnostic_rows: list[dict[str, Any]] = []
        subquery_count = 0
        supplied = sub["supplied_queries"]
        if supplied:
            for item in supplied:
                groups, not_terms, _, hard_all = normalize_query(item, f"{sub['id']}-Q{subquery_count + 1:02d}")
                subquery_count += 1
                qid = str(item.get("query_id") or f"{sub['id']}-Q{subquery_count:02d}")
                log = run_query(index, works_by_id, groups, scope, qid, "R01", sub["id"],
                                "execute frozen subquestion query without broadening", hard_all, not_terms)
                query_log.append(log)
                initial_rows.extend(log["hits"])
        else:
            initial_concepts = sub["concepts"]
            log = run_query(index, works_by_id, initial_concepts, scope, f"{sub['id']}-Q01", "R01", sub["id"],
                            "joint object/facet evidence required for a direct answer", hard_all=len(initial_concepts) > 1)
            query_log.append(log)
            initial_rows.extend(log["hits"])
        # Deduplicate hits from multiple frozen queries for this subquestion.
        best_by_work: dict[str, dict[str, Any]] = {}
        for row in initial_rows:
            previous = best_by_work.get(row["work_id"])
            if previous is None or (row["normalized_relevance"], row["facet_coverage"], row["bm25"]) > (
                    previous["normalized_relevance"], previous["facet_coverage"], previous["bm25"]):
                best_by_work[row["work_id"]] = row
        selected = sorted(best_by_work.values(),
                          key=lambda r: (-r["normalized_relevance"], -r["facet_coverage"],
                                         C.normalize_title(works_by_id[r["work_id"]]["metadata"].get("title")), r["work_id"]))
        direct_work_ids = {r["work_id"] for r in selected}
        # R02 diagnostic decomposition only runs if exact joint execution did not answer.
        if not selected and not supplied:
            for j, item in enumerate(sub["concepts"], 1):
                log = run_query(index, works_by_id, [item], scope, f"{sub['id']}-GAP{j:02d}", "R02", sub["id"],
                                "diagnose which joint facet has evidence; single-facet hits are never promoted to direct answers",
                                hard_all=False, diagnostic=True)
                query_log.append(log)
                diagnostic_rows.extend(log["hits"])
        for row in selected:
            work = works_by_id[row["work_id"]]
            row["record_id"] = work["record_id"]
            row["assertions"] = work["assertions"]
            row["evidence"] = C.score_evidence(work, row)
            row["direct_joint_hit"] = True
            previous = seen_work_best.get(row["work_id"])
            if previous is None or row["normalized_relevance"] > previous["normalized_relevance"]:
                seen_work_best[row["work_id"]] = copy.deepcopy(row)
            seen_work_queries.setdefault(row["work_id"], []).append(sub["id"])
        conflicts = assertion_conflicts(selected) + [dict(c, subquestion_id=sub["id"]) for c in version_conflicts
                                                       if c["work_id"] in direct_work_ids]
        if selected and conflicts:
            sub_status, sub_confidence = "answered_with_conflicts_human_review", "direct_joint_hit_conflict_unresolved"
            C.finding(result, "question.evidence_conflict", "medium",
                      f"subquestion {sub['id']} has conflicting declared positions or source versions",
                      subquestion_id=sub["id"], conflicts=conflicts)
        elif selected:
            sub_status, sub_confidence = "answered", "direct_joint_query_hit"
        elif diagnostic_rows:
            sub_status, sub_confidence = "bounded_gap_partial_facets_only", "diagnostic_only_not_an_answer"
            C.finding(result, "question.only_partial_evidence", "medium",
                      f"subquestion {sub['id']} has single-facet diagnostics but no joint evidence",
                      subquestion_id=sub["id"])
        else:
            sub_status, sub_confidence = "bounded_gap_in_supplied_snapshot", "no_joint_evidence"
            C.finding(result, "question.subquestion_unanswered", "medium",
                      f"subquestion {sub['id']} remains unanswered in this fixed snapshot",
                      subquestion_id=sub["id"])
        for row in selected:
            missing = works_by_id[row["work_id"]]["metadata_completeness"]["missing_fields"]
            if missing:
                C.finding(result, "question.evidence_metadata_incomplete", "medium",
                          f"evidence work {row['work_id']} for {sub['id']} lacks {', '.join(missing)}",
                          subquestion_id=sub["id"], work_id=row["work_id"])
        subresults.append({
            "subquestion_id": sub["id"], "question": sub["question"], "depends_on": sub["depends_on"],
            "required": sub["required"], "decomposition_rule": sub.get("decomposition_rule", "case supplied/frozen"),
            "concepts": sub["concepts"], "status": sub_status, "evidence_support": sub_confidence,
            "direct_answer_work_ids": [r["work_id"] for r in selected], "direct_evidence": selected,
            "partial_diagnostic_work_ids": sorted({r["work_id"] for r in diagnostic_rows} - direct_work_ids),
            "partial_diagnostic_note": "R02 single-facet rows are diagnostics only; not direct evidence for the joint subquestion.",
            "empty_result": not bool(selected), "bounded_scope": "only supplied records and frozen queries/term mappings",
            "conflicts": conflicts,
            "review_reason": None if sub_status == "answered" else "human review required; no global research-gap or global-recall conclusion",
        })
    subresults.sort(key=lambda row: [s["id"] for s in subquestions].index(row["subquestion_id"]))
    candidates = []
    for row in subresults:
        for evidence in row["direct_evidence"]:
            work = works_by_id[evidence["work_id"]]
            candidate = C.public_candidate(work, evidence)
            candidate["supports_subquestion_ids"] = sorted(set(seen_work_queries.get(work["work_id"], [])))
            candidates.append(candidate)
    # Different subquestions may share a work; deduplicate the top-level reading set.
    unique_candidates: dict[str, dict[str, Any]] = {}
    for candidate in candidates:
        work_id = candidate["work_id"]
        if work_id in unique_candidates:
            previous = unique_candidates[work_id]
            previous["supports_subquestion_ids"] = sorted(set(previous["supports_subquestion_ids"] + candidate["supports_subquestion_ids"]))
            if candidate["relevance"]["normalized_relevance"] > previous["relevance"]["normalized_relevance"]:
                previous["relevance"] = candidate["relevance"]
                previous["evidence"] = candidate["evidence"]
        else:
            unique_candidates[work_id] = candidate
    candidate_list = sorted(unique_candidates.values(),
                            key=lambda item: (-item["relevance"]["normalized_relevance"],
                                              C.normalize_title(item["metadata"].get("title")), item["work_id"]))
    for i, item in enumerate(candidate_list, 1):
        item["rank"] = i
    statuses = {row["status"] for row in subresults}
    if any("conflicts" in status for status in statuses):
        stop = {"status": "stop_for_human_adjudication", "reason": "All frozen queries ran, but declared evidence/version conflicts remain; no majority-vote resolution."}
    elif all(status == "answered" for status in statuses):
        stop = {"status": "complete_for_this_frozen_snapshot", "reason": "Every subquestion has direct evidence under its original joint query gates; additional remote coverage unknown."}
    else:
        stop = {"status": "bounded_local_stop_review_required", "reason": "Every subquestion and needed facet diagnostic ran. Unanswered facets remain bounded snapshot gaps, not global research gaps; remote plans were not executed."}
    decomposition = {
        "research_question": C.research_question_text(spec) or None,
        "subquestions": [{"id": s["id"], "question": s["question"], "depends_on": s["depends_on"],
                          "required": s["required"], "concepts": s["concepts"],
                          "decomposition_rule": s.get("decomposition_rule", "case supplied/frozen")} for s in subquestions],
        "scheduling_plan": [{"batch": i + 1, "ready_subquestions": batch, "actual_execution": "sequential_replay_of_ready_set"}
                            for i, batch in enumerate(batches)],
        "dependency_order": [item for batch in batches for item in batch],
        "stop_rule": "answer every required subquestion by direct joint evidence, or log a bounded snapshot gap/conflict; never relax ALL silently",
        "time_scope": scope,
        "controlled_vocabulary_note": "Only case-supplied or verified controlled terms execute. Candidate mappings remain plans for vocabulary review.",
    }
    result.update({
        "question_decomposition": decomposition, "subquestion_results": subresults,
        "query_log": query_log, "candidate_set": candidate_list, "dedup_audit": duplicate_audit,
        "stop_decision": stop,
        "检索结果": {"候选文献": candidate_list, "排序/筛选结果": [{"subquestion_id": s["subquestion_id"],
                     "status": s["status"], "direct_answer_work_ids": s["direct_answer_work_ids"],
                     "partial_diagnostic_work_ids": s["partial_diagnostic_work_ids"],
                     "conflicts": len(s["conflicts"])} for s in subresults],
                   "元数据": {c["work_id"]: c["metadata"] for c in candidate_list},
                   "来源定位": {c["work_id"]: c["sources"] for c in candidate_list},
                   "遗漏说明": [{"subquestion_id": s["subquestion_id"], "status": s["status"],
                              "reason": s["review_reason"]} for s in subresults if s["review_reason"]]},
        "证据记录": {"question_decomposition": decomposition, "query_log": query_log,
                   "subquestion_results": subresults, "dedup_audit": duplicate_audit,
                   "evidence_ledger": [{"subquestion_id": s["subquestion_id"], **e} for s in subresults
                                     for e in s["direct_evidence"] for e in e["evidence"]],
                   "停止理由": stop},
        "状态说明": {"运行状态": result["status"], "已完成": [row["query_id"] for row in query_log],
                   "未完成": [{"subquestion_id": s["subquestion_id"], "reason": s["review_reason"]}
                            for s in subresults if s["review_reason"]],
                   "空结果": not bool(candidate_list), "冲突": [c for s in subresults for c in s["conflicts"]],
                   "权限或接口异常": [f for f in result["findings"] if "access" in f["rule"]],
                   "不确定性": ["All answers/gaps are fixed-snapshot statements; remote plans and human adjudication are not completed."]},
        "sources": [source for work in works for source in work["sources"]],
        "evidence_summary": {"subquestions": len(subresults), "answered": sum(s["status"] == "answered" for s in subresults),
                             "conflicted": sum("conflicts" in s["status"] for s in subresults),
                             "bounded_gaps": sum(s["status"].startswith("bounded_gap") for s in subresults),
                             "source_export_records": len(records), "deduplicated_works": len(works),
                             "direct_candidate_works": len(candidate_list), "completed_local_queries": len(query_log),
                             "remote_hit_count": None},
        "uncertainty": ["Lexical term mappings are not semantic proof of a mechanism or causal relation.",
                        "An empty subquestion is scoped to supplied records/queries, never global absence.",
                        "DOI syntax and source status are not independently refetched or upgraded."],
        "change_records": [{"operation": "question_decomposition_freeze", "subquestion_id": s["id"],
                            "depends_on": s["depends_on"]} for s in subquestions],
        "deliverables": ["result.json", "question_plan.json", "query_log.json", "query_log.csv",
                         "question_evidence.csv", "question_report.md"],
    })
    result["limits"] = ["OpenAlex/Crossref/Europe PMC requests embedded in query logs are planned_not_executed; remote hit counts are null.",
                        "Partial single-facet results remain diagnostic and cannot answer the original joint subquestion.",
                        "Scheduling shows ready sets, not fabricated concurrent timing or resource-use metrics."]
    return C.complete_contract(result, spec, case)


def report_markdown(result: dict[str, Any]) -> str:
    lines = ["# 科研问题驱动检索（固定快照）", "", f"- case_id：{result.get('case_id')}",
             f"- 状态：{result.get('status')}", "- 远程请求：仅计划，未执行；命中数只计算本次供入记录。", "",
             "## 问题拆解与依赖", "", "| 子问题 | 依赖 | 状态 | 直接证据 | 诊断性部分证据 |", "|-|-|-|-|-|"]
    for row in result["subquestion_results"]:
        lines.append(f"| {row['subquestion_id']} {row['question'].replace('|', '/')} | {','.join(row['depends_on']) or '—'} | "
                     f"{row['status']} | {len(row['direct_answer_work_ids'])} | {len(row['partial_diagnostic_work_ids'])} |")
    lines += ["", "## 检索轮次", "", "| 子问题 | query | 轮次 | 本地命中 | 远程命中 |", "|-|-|-|-|-|"]
    for row in result["query_log"]:
        lines.append(f"| {row['subquestion_id']} | {row['query_id']} | {row['round']} | {row['local_snapshot_hit_count']} | null |")
    lines += ["", f"停止判定：{result['stop_decision']['status']}；{result['stop_decision']['reason']}", "",
              "R02 分面命中只用于定位缺口。没有满足原联合查询的记录时，不把单面命中升级成子问题答案，也不声称全球研究空白。", "",
              "原式、对象范围、同义词/跨语言映射、受控词候选、布尔逻辑、时间/语言边界、逐篇证据切片和冲突见 result.json、query_log.json 与 question_evidence.csv。"]
    for finding in result.get("findings", []):
        lines.append(f"- {finding['severity']} / {finding['rule']}：{finding.get('message', '')}")
    return "\n".join(lines) + "\n"
