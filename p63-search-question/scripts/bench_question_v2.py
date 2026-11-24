"""Full independent regression for question-search/v2, not an official score.

python -B -I -X utf8 scripts/bench_question_v2.py
"""
from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import question_engine as E  # noqa: E402
import retrieval_common as C  # noqa: E402

ROOT = HERE.parent
PUBLIC = json.loads((ROOT / "examples" / "public_real_records.json").read_text(encoding="utf-8"))
EXAMPLE = json.loads((ROOT / "examples" / "case.json").read_text(encoding="utf-8"))
SYNTH = json.loads((ROOT / "examples" / "records.json").read_text(encoding="utf-8"))


def case(value=None, **kw):
    result = copy.deepcopy(value or {"case_id": "question-clean", "research_question": "protein structure prediction",
                                     "records": [PUBLIC[0]], "output_contract": ["检索结果", "证据记录", "状态说明"]})
    result.update(kw)
    return result


def build(value):
    return E.build_result(value, ROOT / "examples")


def comparison_record(identifier, title, stance, comparison_key=None):
    record = {"id": identifier, "source": "explicitly synthetic comparison fixture",
              "title": title, "abstract": "Explicit synthetic protein structure prediction comparison text.",
              "authors": ["Synthetic Comparison Author"], "year": 2024,
              "journal": "Synthetic comparison fixture", "language": "en", "stance": stance}
    if comparison_key is not None:
        record["comparison_key"] = comparison_key
    return record


def main():
    def clean_baseline():
        result = build(case())
        return result["status"] == "clean" and result["findings"] == [] and len(result["subquestion_results"]) == 1 \
            and result["subquestion_results"][0]["status"] == "answered"

    def facets_keep_object_scope():
        result = build(copy.deepcopy(EXAMPLE))
        return len(result["subquestion_results"]) == 5 and all(
            any(c["role"] == "object" and c["required"] for c in s["concepts"])
            for s in result["subquestion_results"])

    def pure_chinese_recalls_english_evidence():
        result = build(copy.deepcopy(EXAMPLE))
        s4 = next(s for s in result["subquestion_results"] if s["subquestion_id"] == "S04")
        return any(e["record_id"] == "en-interface-02" for s in result["subquestion_results"]
                   for e in s["direct_evidence"]) and s4["status"] == "answered"

    def negation_and_partial_not_promoted():
        result = build(copy.deepcopy(EXAMPLE))
        gap = next(s for s in result["subquestion_results"] if s["subquestion_id"] == "S05")
        return gap["status"] == "bounded_gap_partial_facets_only" and gap["direct_answer_work_ids"] == [] \
            and gap["partial_diagnostic_work_ids"] and all(e["record_id"] not in {"zh-liquid-03", "en-polymer-05"}
                for s in result["subquestion_results"] for e in s["direct_evidence"] if s["subquestion_id"] == "S05")

    def explicit_conflict_only_in_comparable_set():
        result = build(copy.deepcopy(EXAMPLE))
        s1 = next(s for s in result["subquestion_results"] if s["subquestion_id"] == "S01")
        s3 = next(s for s in result["subquestion_results"] if s["subquestion_id"] == "S03")
        return s1["status"] == "answered_with_conflicts_human_review" and s3["status"] == "answered"

    def unflagged_different_stance_not_conflict():
        a = comparison_record("stance-a", "Protein structure prediction method A", "positive wording")
        b = comparison_record("stance-b", "Protein structure prediction method B", "negative wording")
        result = build(case(records=[a, b]))
        return not any(f["rule"] == "question.evidence_conflict" for f in result["findings"])

    def same_comparison_key_detects_conflict():
        a = comparison_record("comparison-a", "Protein structure prediction method A", "positive", "same-outcome")
        b = comparison_record("comparison-b", "Protein structure prediction method B", "negative", "same-outcome")
        result = build(case(records=[a, b]))
        return any(f["rule"] == "question.evidence_conflict" for f in result["findings"])

    def dependency_execution_is_topological():
        value = case(subquestions=[
            {"id": "S2", "question": "protein", "query": {"all": ["protein"]}, "depends_on": ["S1"]},
            {"id": "S1", "question": "attention", "query": {"all": ["attention"]}}], records=PUBLIC)
        result = build(value)
        return [q["subquestion_id"] for q in result["query_log"]][:2] == ["S1", "S2"] \
            and result["question_decomposition"]["dependency_order"] == ["S1", "S2"]

    def dependency_cycle_refused():
        value = case(subquestions=[{"id": "S1", "question": "protein", "depends_on": ["S2"]},
                                   {"id": "S2", "question": "attention", "depends_on": ["S1"]}])
        try:
            build(value)
        except C.RetrievalError as exc:
            return exc.rule == "question.dependency_cycle" and exc.exit_code == 4
        return False

    def unknown_dependency_refused():
        value = case(subquestions=[{"id": "S1", "question": "protein", "depends_on": ["missing"]}])
        try:
            build(value)
        except C.RetrievalError as exc:
            return exc.rule == "question.dependency_unknown"
        return False

    def duplicate_subquestion_refused():
        value = case(subquestions=[{"id": "same", "question": "protein"}, {"id": "same", "question": "protein"}])
        try:
            build(value)
        except C.RetrievalError as exc:
            return exc.rule == "question.subquestion_id_duplicate"
        return False

    def all_any_not_no_broad_or():
        records = [copy.deepcopy(SYNTH[1]), copy.deepcopy(SYNTH[2]), copy.deepcopy(SYNTH[4])]
        value = case(subquestions=[{"id": "STRICT", "question": "scope",
                                    "query": {"all": ["solid electrolyte"], "any": ["impedance", "polymer"],
                                              "not": ["liquid"]}}], records=records)
        result = build(value)
        direct = [e["record_id"] for e in result["subquestion_results"][0]["direct_evidence"]]
        return direct == ["en-interface-02"] and result["query_log"][0]["boolean_logic"]["between_concepts"] == "AND"

    def supplied_scope_query_not_natural_language():
        value = case(research_question=None, query=None,
                     subquestions=[{"id": "Q", "question": "frozen", "query": {"all": ["all-token-missing"]}}])
        result = build(value)
        return len(result["query_log"]) == 1 and result["candidate_set"] == [] \
            and result["subquestion_results"][0]["status"] == "bounded_gap_in_supplied_snapshot"

    def evidence_fields_slice_verbatim():
        result = build(copy.deepcopy(EXAMPLE))
        records = C.load_records(C.merged_spec(EXAMPLE), ROOT / "examples")
        works, _, _ = C.deduplicate(records)
        work_by_id = {w["work_id"]: w for w in works}
        checks = []
        for sub in result["subquestion_results"]:
            for hit in sub["direct_evidence"]:
                for ev in hit["evidence"]:
                    text = work_by_id[hit["work_id"]]["fields"][ev["field"]]
                    loc = ev["locator"]
                    checks.append(text[loc["start"]:loc["end"]] == ev["quote"])
        return bool(checks) and all(checks)

    def same_term_after_negation_positive_quote():
        text = "This is not a protein folding paper. A separate section evaluates protein folding experiments."
        spans = C.positive_spans(text, "protein folding")
        return len(spans) == 1 and text[spans[0][0]:spans[0][1]] == "protein folding" and spans[0][0] > 20

    def duplicate_rows_all_accounted():
        result = build(copy.deepcopy(EXAMPLE))
        summary = result["evidence_summary"]
        return summary["source_export_records"] == 6 and summary["deduplicated_works"] == 5 \
            and len(result["dedup_audit"]) == 6 and sum(a["duplicate_of"] is not None for a in result["dedup_audit"]) == 1

    def shared_work_maps_all_subquestions():
        result = build(copy.deepcopy(EXAMPLE))
        shared = next(c for c in result["candidate_set"] if c["record_id"] == "zh-grain-01")
        return {"S01", "S02", "S03"} <= set(shared["supports_subquestion_ids"])

    def bounded_stop_and_remote_null():
        result = build(copy.deepcopy(EXAMPLE))
        return result["stop_decision"]["status"] in {"bounded_local_stop_review_required", "stop_for_human_adjudication"} \
            and all(q["remote_hit_count"] is None for q in result["query_log"]) \
            and all(plan["execution_status"] == "planned_not_executed" for q in result["query_log"] for plan in q["source_queries"])

    def time_language_missing_is_explicit():
        value = copy.deepcopy(EXAMPLE)
        value["languages"] = ["en"]
        result = build(value)
        reasons = [x["reason"] for q in result["query_log"] for x in q["excluded_from_boundary_or_boolean"]]
        return any("language zh" in reason for reason in reasons) and result["status"] == "review"

    def metadata_missing_not_made_complete():
        result = build(copy.deepcopy(EXAMPLE))
        assert result["status"] == "review"
        return any(f["rule"] == "question.evidence_metadata_incomplete" for f in result["findings"]) \
            and all(c["metadata"]["doi"] is None for c in result["candidate_set"])

    def output_contract_passthrough():
        value = case(output_contract={"检索结果": {}, "证据记录": {}, "unknown": {}, "case_note": {}},
                     case_note="caller value")
        result = build(value)
        return result["case_id"] == "question-clean" and result["case_note"] == "caller value" \
            and result["unknown"] is None and result["status"] == "review"

    def deterministic_result_bytes():
        value = copy.deepcopy(EXAMPLE)
        return C.dumps(build(value)) == C.dumps(build(value))

    def source_plans_are_reproducible():
        result = build(copy.deepcopy(EXAMPLE))
        log = result["query_log"][0]
        plans = {p["source"]: p for p in log["source_queries"]}
        return "TITLE_ABS" in plans["Europe PMC"]["parameters"]["query"] \
            and "query.bibliographic" in plans["Crossref"]["parameters"] \
            and "2022-01-01" in plans["OpenAlex"]["parameters"]["filter"] \
            and log["boolean_logic"]["between_concepts"] == "AND"

    scenarios = [
        ("clean_baseline_zero_findings", clean_baseline),
        ("facets_keep_object_all_scope", facets_keep_object_scope),
        ("pure_chinese_recalls_english", pure_chinese_recalls_english_evidence),
        ("negation_partial_not_promoted", negation_and_partial_not_promoted),
        ("conflict_only_comparable_set", explicit_conflict_only_in_comparable_set),
        ("unflagged_stance_not_conflict", unflagged_different_stance_not_conflict),
        ("same_comparison_key_conflict", same_comparison_key_detects_conflict),
        ("dependency_execution_topological", dependency_execution_is_topological),
        ("dependency_cycle_refused", dependency_cycle_refused),
        ("unknown_dependency_refused", unknown_dependency_refused),
        ("duplicate_subquestion_refused", duplicate_subquestion_refused),
        ("all_any_not_no_broad_or", all_any_not_no_broad_or),
        ("structured_query_no_natural_language_broadening", supplied_scope_query_not_natural_language),
        ("evidence_fields_slice_verbatim", evidence_fields_slice_verbatim),
        ("negated_then_positive_quote", same_term_after_negation_positive_quote),
        ("duplicate_rows_all_accounted", duplicate_rows_all_accounted),
        ("shared_work_all_subquestions", shared_work_maps_all_subquestions),
        ("bounded_stop_remote_null", bounded_stop_and_remote_null),
        ("time_language_explicit_exclusion", time_language_missing_is_explicit),
        ("metadata_missing_stays_incomplete", metadata_missing_not_made_complete),
        ("output_contract_passthrough", output_contract_passthrough),
        ("deterministic_result_bytes", deterministic_result_bytes),
        ("source_plans_reproducible", source_plans_are_reproducible),
    ]
    rows = []
    for name, fn in scenarios:
        try:
            ok, why = bool(fn()), ""
        except Exception as exc:
            ok, why = False, f"{type(exc).__name__}: {exc}"
        rows.append({"scenario": name, "pass": ok, "why": why})
        print(("PASS" if ok else "FAIL") + f"  {name:<48}" + why)
    passed = sum(x["pass"] for x in rows)
    report = {"schema_version": "question-search-v2-bench/v1", "official_score": False,
              "scenarios": rows, "totals": {"passed": passed, "of": len(rows)}}
    (HERE / "report_question_v2.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"\n{passed}/{len(rows)} scenarios pass")
    return 0 if passed == len(rows) else 1


if __name__ == "__main__":
    raise SystemExit(main())
