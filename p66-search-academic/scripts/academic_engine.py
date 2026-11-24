"""Academic retrieval over actual supplied scholarly exports.

The output separates (1) lexical relevance, (2) metadata completeness and
(3) provenance trace quality.  No score is a scientific-quality judgement.
"""
from __future__ import annotations

import copy
import re
from pathlib import Path
from typing import Any

import retrieval_common as C

SCHEMA_VERSION = "academic-search/v2"


def expression_terms(expression: Any) -> list[str]:
    if isinstance(expression, list):
        return list(dict.fromkeys(str(t).strip() for t in expression if str(t).strip()))
    text = str(expression or "")
    quoted = re.findall(r'"([^"\n]+)"', text)
    if quoted:
        return list(dict.fromkeys(q.strip() for q in quoted if q.strip()))
    terms = C.query_terms(text)
    ignored = {"and", "or", "not", "title", "abs", "title_abs", "mesh", "lang", "first_pdate",
               "from", "to", "publication", "date", "query", "filter"}
    return [t for t in terms if t.casefold() not in ignored]


def concept_for_terms(terms: list[str], cid: str = "Q", label: str = "supplied query", role: str = "query") -> dict[str, Any]:
    return {"concept_id": cid, "label": label, "role": role, "terms": list(terms), "all_terms": list(terms),
            "synonyms": [], "controlled_terms": [], "required": True, "provenance": "case_supplied_query"}


def score_hits(index: C.BM25Index, works_by_id: dict[str, dict[str, Any]], rows: list[dict[str, Any]],
               best: dict[str, dict[str, Any]], links: dict[str, list[str]], query_id: str) -> None:
    for row in rows:
        work_id = row["work_id"]
        links.setdefault(work_id, []).append(query_id)
        previous = best.get(work_id)
        if previous is None or (row["normalized_relevance"], row["facet_coverage"], row["bm25"]) > (
                previous["normalized_relevance"], previous["facet_coverage"], previous["bm25"]):
            best[work_id] = copy.deepcopy(row)


def execute_concept_query(index: C.BM25Index, records: list[dict[str, Any]], works_by_id: dict[str, dict[str, Any]],
                          concepts: list[dict[str, Any]], scope: dict[str, Any], query_id: str,
                          round_id: str, purpose: str, best: dict[str, dict[str, Any]],
                          links: dict[str, list[str]], planned_sources: bool = True,
                          hard_all: bool = False, excluded_terms: list[str] | None = None) -> dict[str, Any]:
    rows = C.query_for_concepts(index, concepts, scope, hard_all=hard_all)
    if excluded_terms:
        rows = [r for r in rows if not C.matched_terms(excluded_terms, works_by_id[r["work_id"]]["fields"])]
    score_hits(index, works_by_id, rows, best, links, query_id)
    supplied = []
    for concept in concepts:
        supplied.append({"concept_id": concept["concept_id"], "label": concept["label"],
                         "role": concept["role"], "terms": concept["terms"], "synonyms": concept["synonyms"],
                         "controlled_terms": concept["controlled_terms"], "all_terms": concept["all_terms"]})
    log = {
        "query_id": query_id, "round": round_id, "purpose": purpose,
        "execution_status": "fixed_snapshot_scanned", "snapshot_scope": "only case-supplied records",
        "search_date": scope.get("search_date"), "time_boundary": {"from": scope.get("start_date"), "to": scope.get("end_date")},
        "language_boundary": scope.get("languages"), "fields": ["title", "abstract", "keywords", "body"],
        "boolean_logic": {"required_concept_groups_all": hard_all,
                          "terms_within_a_concept": "OR", "not_terms": excluded_terms or []},
        "concepts": supplied, "local_snapshot_hit_count": len(rows),
        "local_snapshot_hit_work_ids": [r["work_id"] for r in rows],
        "remote_hit_count": None, "excluded_from_boundary_or_boolean": [],
        "source_queries": C.source_query_plans(concepts, scope) if planned_sources else [],
    }
    # Boundary and NOT omissions are explicit, not global-database exclusions.
    for work in works_by_id.values():
        if work["work_id"] in {r["work_id"] for r in rows}:
            continue
        passed, why = C.temporal_match(work, scope)
        if not passed:
            log["excluded_from_boundary_or_boolean"].append({"work_id": work["work_id"], "reason": why})
        elif excluded_terms and C.matched_terms(excluded_terms, work["fields"]):
            log["excluded_from_boundary_or_boolean"].append({"work_id": work["work_id"],
                                                              "reason": "matched a NOT term; snapshot-local exclusion"})
    if not rows:
        log["empty_result"] = {
            "status": "empty_within_fixed_snapshot", "remote_hit_count": None,
            "explanation": "No supplied record satisfied this query and the declared boundaries. This is not global absence or a failed remote query.",
            "next_action": "A reviewer may execute the separate planned source queries or add a versioned synonym; neither has already been done by this run."
        }
    return log


def supplied_queries(spec: dict[str, Any]) -> list[dict[str, Any]]:
    objects = C.supplied_query_objects(spec)
    if isinstance(spec.get("query"), str) and not objects:
        objects = [{"query_id": "Q00", "query": spec["query"]}]
    elif isinstance(spec.get("query"), dict) and not objects \
            and any(key in spec["query"] for key in ("all", "any", "not")):
        objects = [{"query_id": "Q00", "query": spec["query"]}]
    return objects


def normalize_supplied(item: dict[str, Any]) -> tuple[list[dict[str, Any]], list[str], Any]:
    query = item.get("query", item.get("q", item.get("search_query", item)))
    excluded = item.get("not", item.get("exclude", []))
    excluded_terms = expression_terms(excluded)
    if isinstance(query, dict):
        if not excluded:
            excluded = query.get("not", query.get("exclude", []))
            excluded_terms = expression_terms(excluded)
        concepts = []
        for i, term in enumerate(expression_terms(query.get("all", []))):
            concepts.append(concept_for_terms([term], f"{item['query_id']}-A{i + 1}", f"ALL {term}"))
        any_terms = expression_terms(query.get("any", []))
        if any_terms:
            concepts.append(concept_for_terms(any_terms, f"{item['query_id']}-OR", "ANY alternatives"))
        return concepts, excluded_terms, query
    # A structured item with a query string preserves that exact string; its
    # surrounding database/filters stay in the raw query record.
    terms = expression_terms(query)
    concepts = [concept_for_terms(terms, f"{item['query_id']}-OR", str(query))] if terms else []
    return concepts, excluded_terms, query


def _merge_best_scores_with_metadata(best: dict[str, dict[str, Any]], works_by_id: dict[str, dict[str, Any]],
                                     links: dict[str, list[str]]) -> list[dict[str, Any]]:
    candidates = []
    for work_id, score in best.items():
        work = works_by_id[work_id]
        item = C.public_candidate(work, score)
        item["retrieved_by_query_ids"] = sorted(set(links.get(work_id, [])))
        item["relevance_explanation"] = {
            "method": "hard query/boundary gates, then field-weighted BM25 over actually matched terms",
            "separate_dimensions": {
                "topical_relevance_normalized": score["normalized_relevance"],
                "metadata_completeness": work["metadata_completeness"]["score"],
                "source_trace_quality": work["source_quality"]["score"],
            },
            "not_inferred": ["global recall", "research quality", "peer-review status", "DOI existence beyond supplied metadata"],
        }
        candidates.append(item)
    candidates.sort(key=lambda item: (-item["relevance"]["normalized_relevance"],
                                      -item["relevance"]["facet_coverage"],
                                      C.normalize_title(item["metadata"].get("title")), item["work_id"]))
    for i, item in enumerate(candidates, 1):
        item["rank"] = i
    return candidates


def item_scope(base: dict[str, Any], item: dict[str, Any]) -> dict[str, Any]:
    """Query-specific filters refine the frozen global scope, never widen it."""
    scope = copy.deepcopy(base)
    filters = item.get("filters") if isinstance(item.get("filters"), dict) else {}
    start = item.get("start_date", item.get("date_from")) or filters.get("from_publication_date") or filters.get("from-pub-date")
    end = item.get("end_date", item.get("date_to")) or filters.get("to_publication_date") or filters.get("until-pub-date")
    languages = item.get("languages", item.get("language", filters.get("language")))
    if start:
        scope["start_date"] = start
    if end:
        scope["end_date"] = end
    if languages:
        scope["languages"] = C._as_list(languages)
    return C.temporal_scope({"start_date": scope.get("start_date"), "end_date": scope.get("end_date"),
                             "languages": scope.get("languages", []), "search_date": scope.get("search_date")})


def build_result(case: dict[str, Any], case_dir: Path) -> dict[str, Any]:
    spec = C.merged_spec(case)
    records = C.load_records(spec, case_dir)
    works, duplicate_audit, conflicts = C.deduplicate(records)
    works_by_id = {work["work_id"]: work for work in works}
    index = C.BM25Index(works)
    scope = C.temporal_scope(spec)
    supplied = supplied_queries(spec)
    question = C.research_question_text(spec)
    concepts = C.derive_concepts(spec, question)
    if not concepts:
        for item in supplied:
            c, _, _ = normalize_supplied(item)
            for concept in c:
                if concept["all_terms"]:
                    concepts.append(concept)
    if not supplied and not concepts:
        raise C.RetrievalError("academic.query_missing", "neither a research question/concepts nor an executable supplied query was provided", 4)
    result: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION, "status": "clean", "case_id": case.get("case_id"),
        "findings": [], "limits": [], "uncertainty": [],
    }
    best: dict[str, dict[str, Any]] = {}
    links: dict[str, list[str]] = {}
    query_log: list[dict[str, Any]] = []
    # R00: execute every actual supplied query without silently changing it.
    for i, item in enumerate(supplied):
        qconcepts, not_terms, raw_query = normalize_supplied(item)
        if not qconcepts:
            C.finding(result, "academic.query_not_executable", "medium",
                      f"supplied query {item['query_id']} has no usable terms", query_id=item["query_id"])
            continue
        query = execute_concept_query(index, records, works_by_id, qconcepts, item_scope(scope, item), item["query_id"], "R00",
                                      "execute supplied query literally with disclosed lexical normalization",
                                      best, links, planned_sources=False, hard_all=len(qconcepts) > 1,
                                      excluded_terms=not_terms)
        query["input_query"] = copy.deepcopy(item)
        query["normalized_query"] = raw_query
        query_log.append(query)
    # R01: baseline question terms, only when this adds a distinct executable query.
    seen_termsets = {tuple(sorted(t.casefold() for c in log["concepts"] for t in c["all_terms"])) for log in query_log}
    if concepts and (not supplied or question):
        if question:
            base_terms = C.query_terms(question)
        else:
            base_terms = list(dict.fromkeys(t for c in concepts for t in c["terms"]))
        baseline_key = tuple(sorted(t.casefold() for t in base_terms))
        if base_terms and baseline_key not in seen_termsets:
            baseline = [concept_for_terms(base_terms, "QBASE", "literal question lexical probe")]
            query_log.append(execute_concept_query(index, records, works_by_id, baseline, scope, "QBASE", "R01",
                                                   "literal question baseline for explicit expansion comparison",
                                                   best, links, planned_sources=False))
            seen_termsets.add(baseline_key)
        expanded_terms = list(dict.fromkeys(t.casefold() for c in concepts for t in c["all_terms"] or c["terms"]))
        if expanded_terms and tuple(sorted(expanded_terms)) not in seen_termsets:
            query_log.append(execute_concept_query(index, records, works_by_id, concepts, scope, "QEXP", "R02",
                                                   "expand declared synonyms/translations within concept groups; OR across concepts for recall",
                                                   best, links, planned_sources=True))
            seen_termsets.add(tuple(sorted(expanded_terms)))
        # Gap-driven third round: separately probe each concept that no earlier hit
        # covered.  A covered facet is not re-queried just to inflate query counts.
        covered_labels = {facet["label"] for score in best.values() for facet in score.get("facet_matches", []) if facet["matched"]}
        for j, concept in enumerate(concepts, 1):
            if concept["label"] in covered_labels:
                continue
            terms = concept["all_terms"] or concept["terms"]
            if not terms:
                continue
            query_log.append(execute_concept_query(index, records, works_by_id, [concept], scope,
                                                   f"QGAP{j:02d}", "R03",
                                                   "separate probe for a previously uncovered concept/gap",
                                                   best, links, planned_sources=False))
    # Deduplicate frozen planned source queries at the plan level.
    plan_sources = C.source_query_plans(concepts, scope) if concepts else []
    controlled_pending = []
    for concept in concepts:
        for item in concept.get("controlled_terms", []):
            if "candidate" in str(item.get("mapping", "")).casefold() or "verify" in str(item.get("mapping", "")).casefold():
                controlled_pending.append({"concept_id": concept["concept_id"], **item,
                                           "execution_status": "not_executed_requires_vocabulary_review"})
    candidates = _merge_best_scores_with_metadata(best, works_by_id, links)
    k_value = spec.get("top_k", spec.get("k", 10))
    try:
        if isinstance(k_value, bool) or int(k_value) != k_value or int(k_value) < 0:
            raise ValueError("negative, boolean or non-integral top_k")
        top_k = int(k_value)
    except (TypeError, ValueError):
        raise C.RetrievalError("academic.top_k_invalid", "top_k/k must be a non-negative integer", 4)
    for item in candidates:
        item["in_top_k"] = item["rank"] <= top_k
        missing = item["metadata_completeness"]["missing_fields"]
        if missing:
            C.finding(result, "academic.metadata_incomplete", "medium",
                      f"candidate {item['work_id']} lacks {', '.join(missing)}",
                      work_id=item["work_id"], missing_fields=missing)
        unresolved = [e for e in item.get("evidence", []) if e.get("status") != "verbatim"]
        if unresolved:
            C.finding(result, "academic.evidence_locator_unresolved", "high",
                      f"candidate {item['work_id']} has {len(unresolved)} unresolved score locators",
                      work_id=item["work_id"])
    for conflict in conflicts:
        C.finding(result, "academic.source_version_conflict", "medium",
                  f"work {conflict['work_id']} has conflicting version/source metadata", **conflict)
    for record in records:
        if record.get("access_blocked"):
            C.finding(result, "academic.access_blocked", "medium",
                      f"record {record['record_id']} is access restricted; metadata only and no full-text claim",
                      record_id=record["record_id"])
        if not record.get("doi_valid_syntax"):
            C.finding(result, "academic.doi_syntax_invalid", "medium",
                      f"record {record['record_id']} has invalid DOI syntax; DOI not used for deduplication claim",
                      record_id=record["record_id"])
    matched_work_ids = set(best)
    unmatched = [{"work_id": work["work_id"], "record_id": work["record_id"],
                  "reason": "no supplied query matched under the fixed snapshot and declared boundaries"}
                 for work in works if work["work_id"] not in matched_work_ids]
    if not candidates:
        C.finding(result, "academic.empty_result", "medium",
                  "query battery returned no records from the supplied snapshot; remote/global absence is unknown")
    if plan_sources:
        result["limits"].append("OpenAlex/Crossref/Europe PMC URLs are reproducible plans only and were not executed; remote_hit_count remains null.")
    result["limits"].append("Lexical matching is language-aware but not semantic inference; paraphrases outside declared synonyms can be missed.")
    result["limits"].append("DOI normalization and syntax checks do not prove registration, publication status, retraction status or current online availability.")
    result["uncertainty"] = ["Completeness is bounded by the supplied exports, query variants and snapshot; no global Recall@k is claimed."]
    stop_decision = ({"status": "completed_supplied_structured_queries_no_implicit_widening",
                      "reason": "Only declared structured queries ran. No natural-language question authorised a separate broad expansion; final candidates were unioned only from those queries."}
                     if supplied and not question else
                     {"status": "stopped_after_frozen_query_battery",
                      "reason": "Every supplied/expanded query and every previously uncovered facet was evaluated; no uncovered facet remained for R04. Additional remote coverage was not executed."})
    query_plan = {
        "research_question": question or None, "concepts": concepts, "time_scope": scope,
        "source_queries": plan_sources, "controlled_vocabulary_pending_review": controlled_pending,
        "query_order": [row["query_id"] for row in query_log],
        "stop_decision": stop_decision,
    }
    top_rows = [{"doc_id": item["record_id"], "work_id": item["work_id"], "rank": item["rank"],
                 "top_k": item["in_top_k"], "score": item["relevance"]["normalized_relevance"],
                 "metadata_completeness": item["metadata_completeness"]["score"],
                 "source_trace_quality": item["source_quality"]["score"],
                 "retrieved_by_query_ids": item["retrieved_by_query_ids"]} for item in candidates]
    retrieval = {
        "候选文献": candidates, "排序/筛选结果": top_rows, "元数据": {item["work_id"]: item["metadata"] for item in candidates},
        "来源定位": {item["work_id"]: item["sources"] for item in candidates},
        "遗漏说明": unmatched + [{"reason": "Only fixed supplied exports were scanned; no live remote or global coverage claim."}],
        "top_k": top_k,
    }
    status_explanation = {
        "运行状态": result["status"], "已完成": [log["query_id"] for log in query_log],
        "未完成": [p["source"] for p in plan_sources],
        "空结果": not bool(candidates), "冲突": conflicts,
        "权限或接口异常": [f for f in result["findings"] if f["rule"] in {"academic.access_blocked", "academic.query_not_executable"}],
        "不确定性": result["uncertainty"],
        "无结果处理": "fixed-snapshot empty + exact query log + not-yet-executed source plans; never padded",
    }
    result.update({
        "query_plan": query_plan, "query_log": query_log, "candidate_set": candidates,
        "dedup_audit": duplicate_audit, "source_conflicts": conflicts,
        "检索结果": retrieval,
        "证据记录": {"query_plan": query_plan, "query_log": query_log, "dedup_audit": duplicate_audit,
                   "evidence_ledger": [e for item in candidates for e in item.get("evidence", [])],
                   "score_definition": "BM25 k1=1.2 b=0.75, weights title/abstract/keywords/body=4/2/2.5/1; hard date/language and Boolean filters precede ranking",
                   "核验方法": "For every verbatim evidence row require quote == fields.<field>[start:end]; recompute ranks from per-field contributions. Null remote counts mean not executed."},
        "状态说明": status_explanation,
        "candidate_set_summary": {
            "source_export_records": len(records), "deduplicated_works": len(works),
            "duplicate_or_version_export_records": len(records) - len(works),
            "candidate_works": len(candidates), "top_k_count": sum(1 for x in top_rows if x["top_k"]),
            "unmatched_works": len(unmatched), "completed_local_queries": len(query_log),
            "remote_hit_count": None,
        },
        "sources": [source for work in works for source in work["sources"]],
        "change_records": [{"operation": "deduplicate_without_deleting_input_rows", "work_id": row["work_id"],
                            "record_id": row["record_id"], "duplicate_of": row["duplicate_of"]} for row in duplicate_audit],
        "deliverables": ["result.json", "query_plan.json", "query_log.json", "candidate_set.json",
                         "query_log.csv", "candidate_set.csv", "dedup_audit.csv", "retrieval_report.md"],
    })
    return C.complete_contract(result, spec, case)


def report_markdown(result: dict[str, Any]) -> str:
    summary = result["candidate_set_summary"]
    lines = [
        "# 学术文献检索结果（固定快照）", "",
        f"- case_id：{result.get('case_id')}", f"- 状态：{result.get('status')}",
        "- 范围：仅实际供入的记录/响应。API 请求均已生成但未执行，远程命中数为 null；不是全球检索或全球召回证明。", "",
        "## 查询与迭代", "",
        "| 查询 | 轮次 | 目的 | 本地快照命中 | 远程命中 |", "|-|-|-|-|-|",
    ]
    for row in result.get("query_log", []):
        lines.append(f"| {row['query_id']} | {row['round']} | {row['purpose']} | {row['local_snapshot_hit_count']} | null |")
    lines += ["", "原查询、布尔概念、时间/语言边界和 OpenAlex/Crossref/Europe PMC 请求计划见 query_plan.json 与 query_log.json。", "",
              "## 去重候选与排序", "",
              "| rank | 文献 | DOI | 年 | BM25相关度 | 元数据完整性 | 来源可追溯性 | 查询 |", "|-|-|-|-|-|-|-|-|"]
    for item in result.get("candidate_set", []):
        md = item["metadata"]
        lines.append(f"| {item['rank']} | {str(md.get('title') or '').replace('|', '/')} | {md.get('doi') or 'undetermined'} | "
                     f"{md.get('year') or 'undetermined'} | {item['relevance']['normalized_relevance']:.6f} | "
                     f"{item['metadata_completeness']['score']:.3f} | {item['source_quality']['score']:.2f} | "
                     f"{','.join(item['retrieved_by_query_ids'])} |")
    lines += ["", "三个分数分别表示词面主题相关性、元数据存在性、来源可追溯性；不能互相替代，也不是论文研究质量评分。", "",
              f"输入导出 {summary['source_export_records']} 条，去重/版本组 {summary['deduplicated_works']} 个，候选 {summary['candidate_works']} 个。"
              "所有原始记录仍在 dedup_audit.csv 中，预印本/正式版本或来源冲突不被静默删除。", "",
              "## 空结果、冲突与限制", ""]
    for row in result.get("query_log", []):
        if row.get("empty_result"):
            lines.append(f"- {row['query_id']}：{row['empty_result']['explanation']}")
    for item in result.get("limits", []):
        lines.append(f"- {item}")
    for item in result.get("findings", []):
        lines.append(f"- {item['severity']} / {item['rule']}：{item.get('message', '')}")
    return "\n".join(lines) + "\n"
