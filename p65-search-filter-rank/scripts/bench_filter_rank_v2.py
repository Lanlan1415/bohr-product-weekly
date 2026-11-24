"""Full regression for screening-rank/v2, not an official score.

python -B -I -X utf8 scripts/bench_filter_rank_v2.py
"""
from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import retrieval_common as C  # noqa: E402
import screening_engine as E  # noqa: E402

ROOT = HERE.parent
PUBLIC = json.loads((ROOT / "examples" / "public_real_records.json").read_text(encoding="utf-8"))
EXAMPLE = json.loads((ROOT / "examples" / "case.json").read_text(encoding="utf-8"))
SYNTH = json.loads((ROOT / "examples" / "records.json").read_text(encoding="utf-8"))
BASE_PROTOCOL = {"inclusion_criteria": [{"id": "INC-PROTEIN", "terms": ["protein", "protein folding"]}],
                 "exclusion_criteria": [], "human_review_thresholds": {"confidence_below": 0.70, "tie_margin": 0.0}}


def case(records=None, **kw):
    value = {"case_id": "screening-bench", "research_question": "protein structure prediction",
             "records": copy.deepcopy(records if records is not None else [PUBLIC[0]]),
             "screening_protocol": copy.deepcopy(BASE_PROTOCOL),
             "output_contract": ["检索结果", "证据记录", "状态说明"]}
    value.update(kw)
    return value


def record(identifier, title, abstract, **kw):
    value = {"id": identifier, "source": "explicitly synthetic screening fixture",
             "title": title, "abstract": abstract, "authors": ["Synthetic Author"],
             "year": 2024, "journal": "Synthetic fixture record", "language": "en"}
    value.update(kw)
    return value


def build(value):
    return E.build_result(value, ROOT / "examples")


def main():
    def clean_baseline():
        result = build(case())
        return result["status"] == "clean" and result["findings"] == [] and len(result["ranked_included"]) == 1 \
            and result["review_queue"] == [] and result["candidate_set_summary"]["include"] == 1

    def all_raw_rows_accounted():
        result = build(copy.deepcopy(EXAMPLE))
        expected = {"include": 2, "pending": 2, "exclude": 4}
        summary = result["candidate_set_summary"]
        return len(result["screening_log"]) == 9 and all(summary[key] == count for key, count in expected.items()) \
            and sum(log["duplicate_of"] is not None for log in result["screening_log"]) == 1 \
            and result["状态说明"]["计数闭合"]["passed"]

    def keyword_rich_wrong_object_excluded():
        result = build(copy.deepcopy(EXAMPLE))
        casting = next(row for row in result["excluded_records"] if row["record_id"] == "synth-casting-offscope")
        return casting["priority_score"] > 50 and casting["reason_code"] == "EX-MISSING" \
            and casting["relevance_class"] == "unrelated"

    def explicit_required_criterion_not_relaxed():
        result = build(copy.deepcopy(EXAMPLE))
        guide = next(row for row in result["excluded_records"] if row["record_id"] == "synth-guide-exclude")
        return guide["reason_code"] == "EX-MISSING" and any(c["criterion_id"] == "INC-EVIDENCE" and not c["matched"]
                                                                   for c in guide["criteria_matches"])

    def conservative_negation_not_positive():
        result = build(copy.deepcopy(EXAMPLE))
        row = next(row for row in result["excluded_records"] if row["record_id"] == "synth-negated-offscope")
        obj = next(c for c in row["criteria_matches"] if c["criterion_id"] == "INC-OBJECT")
        return not obj["matched"] and row["final_decision"] == "exclude"

    def version_conflict_pending_and_grouped():
        result = build(copy.deepcopy(EXAMPLE))
        pending = next(row for row in result["pending_records"] if row["record_id"] == "synth-version-formal")
        return pending["reason_code"] == "VERSION-CONFLICT" and pending["decision_confidence"] <= 0.35 \
            and len(pending["member_ids"]) == 2 and sum(1 for row in result["screening_log"]
                                                       if row["work_id"] == pending["work_id"]) == 2

    def near_tie_and_exact_tie_review():
        a = record("tie-a", "A unique title", "protein folding common wording")
        b = record("tie-b", "B unique title", "protein folding common wording")
        value = case(records=[b, a])
        result = build(value)
        ids = [row["record_id"] for row in result["ranked_included"]]
        return ids == ["tie-a", "tie-b"] and all(row["exact_tie_with"] for row in result["ranked_included"]) \
            and all(row["needs_human_review"] for row in result["ranked_included"])

    def topk_only_include():
        result = build(copy.deepcopy(EXAMPLE))
        return [row["record_id"] for row in result["ranked_included"] if row["in_top_k"]] == ["synth-relevant-b", "synth-relevant-a"] \
            and all(not row["in_top_k"] for row in result["pending_records"] + result["excluded_records"])

    def ranking_dimensions_separate_and_recomputable():
        result = build(copy.deepcopy(EXAMPLE))
        row = result["ranked_included"][0]
        formula = round(sum(row["weighted_components"].values()), 8)
        return formula == row["priority_score"] and row["metadata_completeness"]["score"] < 1 \
            and row["source_quality"]["score"] == 0.65 and row["relevance"]["normalized_relevance"] > 0.8

    def derived_missing_criterion_pending_not_exclude():
        unrelated = record("derived-unrelated", "Completely different coating title", "thermal insulation unrelated evidence")
        value = case(records=[unrelated]); value.pop("screening_protocol")
        result = build(value)
        row = result["screened_records"][0]
        return row["final_decision"] == "pending" and row["reason_code"] == "UNCLEAR" \
            and result["screening_protocol"]["origin"] == "derived_lexical_requires_recall_review"

    def missing_title_abstract_pending():
        missing = record("missing-text", None, None, year=2024)
        result = build(case(records=[missing]))
        return result["pending_records"][0]["reason_code"] == "INSUFFICIENT-TEXT" and not result["excluded_records"]

    def missing_year_pending_not_exclude():
        missing = record("missing-year", "Protein folding no year", "protein folding evidence", year=None)
        result = build(case(records=[missing], start_date="2020-01-01"))
        return result["pending_records"][0]["reason_code"] == "MISSING-BOUNDARY-METADATA"

    def out_of_scope_year_excluded():
        old = record("old-protein", "Protein folding historical fixture", "protein folding evidence", year=2018)
        result = build(case(records=[old], start_date="2020-01-01"))
        return result["excluded_records"][0]["reason_code"] == "EX-BOUNDARY"

    def criterion_fields_invalid_refused():
        value = case(screening_protocol={"inclusion_criteria": [{"id": "bad", "fields": ["abstract", "imaginary"], "terms": ["x"]}]})
        try:
            build(value)
        except C.RetrievalError as exc:
            return exc.rule == "screening.criterion_fields_invalid" and exc.exit_code == 4
        return False

    def protocol_missing_refused():
        value = case(); value.pop("screening_protocol"); value.pop("research_question")
        try:
            build(value)
        except C.RetrievalError as exc:
            return exc.rule == "screening.protocol_missing" and exc.exit_code == 4
        return False

    def weights_sum_invalid_refused():
        value = copy.deepcopy(case())
        value["screening_protocol"]["ranking_weights"] = {"relevance": 0.9, "criteria_coverage": 0.2,
                                                          "metadata_completeness": 0.1, "source_trace": 0.1}
        try:
            build(value)
        except C.RetrievalError as exc:
            return exc.rule == "screening.rank_weights_invalid"
        return False

    def duplicate_criterion_id_refused():
        value = case(screening_protocol={"inclusion_criteria": [{"id": "same", "terms": ["protein"]},
                                                                {"id": "same", "terms": ["folding"]}]})
        try:
            build(value)
        except C.RetrievalError as exc:
            return exc.rule == "screening.criterion_id_duplicate"
        return False

    def evidence_locators_verbatim():
        result = build(copy.deepcopy(EXAMPLE))
        records = C.load_records(C.merged_spec(EXAMPLE), ROOT / "examples")
        works, _, _ = C.deduplicate(records)
        work_by_id = {work["work_id"]: work for work in works}
        checks = []
        for row in result["screened_records"]:
            for criterion in row["criteria_matches"]:
                for ev in criterion["evidence"]:
                    text = work_by_id[row["work_id"]]["fields"][ev["field"]]
                    loc = ev["locator"]
                    checks.append(text[loc["start"]:loc["end"]] == ev["quote"])
        return bool(checks) and all(checks)

    def valid_human_review_changes_and_logs():
        value = case(review_decisions=[{"record_id": "crossref-alphafold", "decision": "exclude",
                                        "reviewer": "declared-reviewer-A", "rationale": "explicit synthetic review-decision fixture",
                                        "time": "2026-11-24T00:00:00Z"}])
        result = build(value)
        row = result["excluded_records"][0]
        history = result["human_review_history"][0]
        return row["engine_decision"] == "include" and row["final_decision"] == "exclude" \
            and history["label"] == 0 and history["user_id"] == "declared-reviewer-A" \
            and history["classifier"] == "fielded-bm25-protocol-v2" and history["time"] == "2026-11-24T00:00:00Z" \
            and result["change_records"][0]["after"] == "exclude"

    def invalid_human_review_not_fabricated():
        value = case(review_decisions=[{"record_id": "unknown", "decision": "exclude", "reviewer": "missing-target", "rationale": "x"}])
        result = build(value)
        return result["ranked_included"][0]["final_decision"] == "include" and result["human_review_history"] == [] \
            and any(f["rule"] == "screening.review_invalid" for f in result["findings"])

    def duplicate_member_review_resolves_work_group():
        first, second = copy.deepcopy(PUBLIC[0]), copy.deepcopy(PUBLIC[0])
        second["id"] = "duplicate-export-second"
        result = build(case(records=[first, second],
                            review_decisions=[{"record_id": "duplicate-export-second", "decision": "exclude",
                                               "reviewer": "duplicate-label-reviewer", "rationale": "explicit duplicate-row label fixture"}]))
        history = result["human_review_history"][0]
        return (history["record_id"] == "duplicate-export-second" and result["excluded_records"][0]["final_decision"] == "exclude"
                and len(result["dedup_audit"]) == 2 and not result["ranked_included"])

    def conflicting_reviews_require_adjudication():
        reviews = [{"record_id": "crossref-alphafold", "decision": "include", "reviewer": "A", "rationale": "fixture A"},
                   {"record_id": "crossref-alphafold", "decision": "exclude", "reviewer": "B", "rationale": "fixture B"}]
        result = build(case(review_decisions=reviews))
        return result["pending_records"][0]["review_resolution"] == "unresolved_human_label_conflict" \
            and any(f["rule"] == "screening.human_label_conflict" for f in result["findings"])

    def adjudication_resolves_label_conflict():
        reviews = [{"record_id": "crossref-alphafold", "decision": "include", "reviewer": "A", "rationale": "fixture A"},
                   {"record_id": "crossref-alphafold", "decision": "exclude", "reviewer": "B", "rationale": "fixture B"},
                   {"record_id": "crossref-alphafold", "decision": "include", "reviewer": "C", "role": "adjudicator",
                    "rationale": "fixture adjudication based on frozen protocol"}]
        result = build(case(review_decisions=reviews))
        row = result["ranked_included"][0]
        return row["final_decision"] == "include" and row["review_resolution"] == "adjudicated_by_declared_reviewer" \
            and not any(f["rule"] == "screening.human_label_conflict" for f in result["findings"])

    def include_exclude_criterion_conflict_pending():
        value = copy.deepcopy(case())
        value["screening_protocol"] = {"criterion_priority": "manual_review",
            "inclusion_criteria": [{"id": "INC", "terms": ["protein"]}],
            "exclusion_criteria": [{"id": "EX", "terms": ["protein"]}]}
        result = build(value)
        row = result["pending_records"][0]
        return row["reason_code"] == "CRITERION-CONFLICT" and row["criterion_conflict"]

    def exclusion_wins_when_declared():
        value = case(screening_protocol={"criterion_priority": "exclusion_wins",
            "inclusion_criteria": [{"id": "INC", "terms": ["protein"]}],
            "exclusion_criteria": [{"id": "EX", "terms": ["protein"]}]})
        result = build(value)
        return result["excluded_records"][0]["reason_code"] == "EX:EX"

    def no_retained_records_is_review_not_block():
        result = build(case(records=[record("off-topic", "Unrelated title", "unrelated abstract")]))
        return result["status"] == "review" and not result["ranked_included"] \
            and result["状态说明"]["空结果"]["included_empty"] and len(result["excluded_records"]) == 1

    def null_metadata_never_invented():
        result = build(copy.deepcopy(EXAMPLE))
        metadata_only = next(row for row in result["screened_records"] if row["record_id"] == "synth-metadata-only")
        return metadata_only["metadata"]["doi"] is None and metadata_only["metadata"]["title"] is None \
            and metadata_only["final_decision"] == "pending"

    def caller_decision_not_fake_human_review():
        value = case()
        value["records"][0]["decision"] = "exclude"
        result = build(value)
        return result["human_review_history"] == [] and result["ranked_included"][0]["final_decision"] == "include"

    def contract_and_engine_status_priority():
        result = build(case(status="fabricated-clean", output_contract={"检索结果": {}, "证据记录": {}, "状态说明": {}, "unknown": {}}))
        return result["status"] == "review" and result["unknown"] is None and "unknown" in result["output_contract_fields"]

    def deterministic_replay():
        value = copy.deepcopy(EXAMPLE)
        return C.dumps(build(value)) == C.dumps(build(value))

    def topk_negative_refused():
        try:
            build(case(top_k=-1))
        except C.RetrievalError as exc:
            return exc.rule == "screening.top_k_invalid" and exc.exit_code == 4
        return False

    scenarios = [
        ("clean_baseline_zero_findings", clean_baseline),
        ("all_raw_rows_accounted", all_raw_rows_accounted),
        ("keyword_rich_wrong_object_excluded", keyword_rich_wrong_object_excluded),
        ("required_criterion_not_relaxed", explicit_required_criterion_not_relaxed),
        ("conservative_negation_not_positive", conservative_negation_not_positive),
        ("version_conflict_pending_grouped", version_conflict_pending_and_grouped),
        ("near_and_exact_tie_review", near_tie_and_exact_tie_review),
        ("topk_only_include", topk_only_include),
        ("dimensions_separate_recomputable", ranking_dimensions_separate_and_recomputable),
        ("derived_missing_pending_not_exclude", derived_missing_criterion_pending_not_exclude),
        ("missing_title_abstract_pending", missing_title_abstract_pending),
        ("missing_year_pending_not_exclude", missing_year_pending_not_exclude),
        ("outside_year_excluded", out_of_scope_year_excluded),
        ("criterion_fields_invalid", criterion_fields_invalid_refused),
        ("protocol_missing_refused", protocol_missing_refused),
        ("weights_sum_invalid_refused", weights_sum_invalid_refused),
        ("duplicate_criterion_id_refused", duplicate_criterion_id_refused),
        ("evidence_locators_verbatim", evidence_locators_verbatim),
        ("valid_human_review_logged", valid_human_review_changes_and_logs),
        ("invalid_human_review_not_fake", invalid_human_review_not_fabricated),
        ("duplicate_member_review_work_group", duplicate_member_review_resolves_work_group),
        ("conflicting_reviews_pending", conflicting_reviews_require_adjudication),
        ("adjudication_resolves_conflict", adjudication_resolves_label_conflict),
        ("criteria_conflict_manual_pending", include_exclude_criterion_conflict_pending),
        ("exclusion_wins_declared", exclusion_wins_when_declared),
        ("no_retained_review_not_block", no_retained_records_is_review_not_block),
        ("null_metadata_not_invented", null_metadata_never_invented),
        ("caller_decision_not_human_proof", caller_decision_not_fake_human_review),
        ("contract_engine_status_priority", contract_and_engine_status_priority),
        ("deterministic_replay", deterministic_replay),
        ("negative_topk_refused", topk_negative_refused),
    ]
    rows = []
    for name, fn in scenarios:
        try:
            ok, why = bool(fn()), ""
        except Exception as exc:
            ok, why = False, f"{type(exc).__name__}: {exc}"
        rows.append({"scenario": name, "pass": ok, "why": why})
        print(("PASS" if ok else "FAIL") + f"  {name:<46}" + why)
    passed = sum(x["pass"] for x in rows)
    report = {"schema_version": "screening-rank-v2-bench/v1", "official_score": False,
              "scenarios": rows, "totals": {"passed": passed, "of": len(rows)}}
    (HERE / "report_filter_rank_v2.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"\n{passed}/{len(rows)} scenarios pass")
    return 0 if passed == len(rows) else 1


if __name__ == "__main__":
    raise SystemExit(main())
