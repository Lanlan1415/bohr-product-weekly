"""Regression and false-positive guards for the eleven-dimension quality audit.

Every expected substantive defect has a qualified-design or clean counterpart.
The clean baseline must have no findings, rather than merely no high findings.
"""
from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import qualityrun as Q  # noqa: E402

MANUSCRIPT = """Abstract
This two-arm randomized study evaluated reaction time after a brief intervention.
1 Introduction
Reaction time is important for safe instrument operation.
We ask whether the prerecorded intervention changes reaction time.
Existing reaction-time training studies provide mixed evidence.
We propose a standardized feedback protocol and compare it with the protocol of Doe et al. (2020).
2 Methods
The randomized parallel design used a sham-feedback control group.
A statistician generated the allocation sequence and outcome assessors were blinded.
We recruited 64 participants and analysed 64 independent participants.
The primary outcome was reaction time in milliseconds.
Reaction time was analysed with a linear model and 95% confidence intervals.
Deidentified data are available in the project repository.
The analysis code is available with the archived workflow.
The ethics committee approved the protocol and participants gave informed consent.
The authors declare no competing interests.
3 Results
The estimated mean difference was 12.0 ms (95% CI 4.0 to 20.0).
The primary analysis included all 64 participants.
4 Discussion
The intervention group had faster responses under the tested conditions.
The observed estimate addresses the stated question and supports the proposed protocol within this sample.
The single-centre sample limits generalization to other settings.
5 Conclusion
The intervention changed reaction time in this randomized sample.
References
Doe J (2020). Standardized reaction-time feedback. Journal of Measurement 10:1-8.
Data availability
Deidentified data are available in the project repository.
Code availability
The analysis code is available with the archived workflow.
Ethics
The ethics committee approved the protocol and participants gave informed consent.
Competing interests
The authors declare no competing interests.
"""

# One concrete passage grounds each reviewer assessment. No evidence-free ratings.
ASSESSMENTS = [
    {"dimension": "problem_importance", "rating": "adequate", "rationale": "Safety relevance and question are explicit.", "evidence": ["Reaction time is important for safe instrument operation."]},
    {"dimension": "innovation", "rating": "adequate", "rationale": "Novel protocol is compared with prior work, not asserted in isolation.", "evidence": ["We propose a standardized feedback protocol and compare it with the protocol of Doe et al. (2020)."]},
    {"dimension": "design", "rating": "adequate", "evidence": ["The randomized parallel design used a sham-feedback control group."]},
    {"dimension": "data", "rating": "adequate", "evidence": ["We recruited 64 participants and analysed 64 independent participants."]},
    {"dimension": "analysis", "rating": "adequate", "evidence": ["Reaction time was analysed with a linear model and 95% confidence intervals."]},
    {"dimension": "results", "rating": "adequate", "evidence": ["The estimated mean difference was 12.0 ms (95% CI 4.0 to 20.0)."]},
    {"dimension": "argumentation", "rating": "adequate", "evidence": ["The observed estimate addresses the stated question and supports the proposed protocol within this sample."]},
    {"dimension": "writing", "rating": "adequate", "evidence": ["The single-centre sample limits generalization to other settings."]},
    {"dimension": "citations", "rating": "adequate", "evidence": ["Doe J (2020). Standardized reaction-time feedback. Journal of Measurement 10:1-8."]},
    {"dimension": "reproducibility", "rating": "adequate", "evidence": ["The analysis code is available with the archived workflow."]},
    {"dimension": "ethics_compliance", "rating": "adequate", "evidence": ["The authors declare no competing interests."]},
]

BASE = {
    "case_id": "quality-local-fixture",
    "manuscript_version": "fixture-v1",
    "source_scope": "full_article",
    "manuscript_text": MANUSCRIPT,
    "research_question_type": "causal_effect",
    "design": "rct",
    "controls": "sham-feedback control group",
    "recruited_n": 64,
    "analysed_n": 64,
    "human_or_animal_research": True,
    "computational_study": True,
    "data_availability": "project repository",
    "code_availability": "archived workflow",
    "competing_interests": "none",
    "ethics_statement": "approved with informed consent",
    "reference_section_present": True,
    "quality_assessments": ASSESSMENTS,
    "reported_values": [{"name": "mean difference", "value": 12.0,
                         "comparator_value": 12.0, "tolerance": 1e-9,
                         "quote": "The estimated mean difference was 12.0 ms"}],
    "output_contract": {"audit_report": "array", "evidence_and_boundaries": "object",
                        "result_status": "object", "manuscript_version": "string",
                        "reviewer_note": "string"},
    "reviewer_note": "preserve-this-contract-value",
}


def d(**over):
    spec = copy.deepcopy(BASE)
    spec.update(over)
    return spec


def assessment(dim, **over):
    a = copy.deepcopy(ASSESSMENTS)
    for item in a:
        if item["dimension"] == dim:
            item.update(over)
    return a


SCEN = [
    ("clean_qualified_design", lambda: (d(), [], "clean", "no_major_defect_detected")),
    ("all_dimensions_must_be_assessed", lambda: (d(quality_assessments=[]), ["pqa.dimension_not_assessed"], "review", "review_incomplete")),
    ("rating_requires_evidence", lambda: (d(quality_assessments=assessment("innovation", evidence=[])),
                                          ["pqa.assessment_without_evidence"], "review", "review_incomplete")),
    ("fabricated_review_quote_rejected", lambda: (d(quality_assessments=assessment("design", evidence=["An imaginary crossover design was used."])),
                                                 ["pqa.review_evidence_not_in_source"], "blocked", "review_incomplete")),
    ("substantiated_concern_is_not_template", lambda: (d(quality_assessments=assessment(
        "results", concerns=[{"finding": "The primary effect omits the comparator arm estimate.",
                              "severity": "high", "evidence_quote": "The estimated mean difference was 12.0 ms",
                              "defect_class": "reporting_gap", "suggestion": "Report both arm summaries."}])),
        ["pqa.reviewer_substantiated_issue"], "blocked", "major_revision")),
    ("novelty_needs_prior_contrast", lambda: (d(manuscript_text=MANUSCRIPT.replace(" and compare it with the protocol of Doe et al. (2020)", ""),
                                               quality_assessments=assessment("innovation", evidence=["We propose a standardized feedback protocol."]),
                                               prior_work_comparison=""),
        ["pqa.novelty_without_contrast"], "review", "minor_revision")),
    ("design_question_mismatch", lambda: (d(design="case_series"),
        ["pqa.design_question_mismatch"], "blocked", "major_revision")),
    ("observational_causal_overreach", lambda: (d(design="observational", controls="comparison cohort",
        manuscript_text=MANUSCRIPT.replace("The intervention changed reaction time in this randomized sample.",
                                          "The intervention causes faster reaction times.")),
        ["pqa.causal_conclusion_exceeds_design"], "blocked", "major_revision")),
    ("qualified_observational_association", lambda: (d(design="observational", controls="comparison cohort", research_question_type="descriptive",
        manuscript_text=MANUSCRIPT.replace("The intervention changed reaction time in this randomized sample.",
                                          "The intervention was associated with faster reaction times in this sample.")),
        [], "clean", "no_major_defect_detected")),
    ("comparative_design_without_control", lambda: (d(controls=""),
        ["pqa.comparative_design_no_control"], "blocked", "major_revision")),
    ("impossible_sample_accounting_recomputed", lambda: (d(recruited_n=50, analysed_n=64),
        ["pqa.sample_accounting_impossible"], "blocked", "major_revision")),
    ("numeric_conflict_recomputed", lambda: (d(reported_values=[{"name": "effect", "value": 12.0,
        "comparator_value": 10.0, "tolerance": 0.5, "quote": "The estimated mean difference was 12.0 ms"}]),
        ["pqa.numeric_reporting_inconsistent"], "blocked", "major_revision")),
    ("numeric_match_is_quiet", lambda: (d(reported_values=[{"name": "effect", "value": 12.0,
        "comparator_value": 10.0, "tolerance": 2.0, "quote": "The estimated mean difference was 12.0 ms"}]),
        [], "clean", "no_major_defect_detected")),
    ("required_sections_missing", lambda: (d(manuscript_text=MANUSCRIPT.replace("3 Results\n", "Results continuation\n", 1)),
        ["pqa.full_article_sections_missing"], "blocked", "major_revision")),
    ("references_unresolved", lambda: (d(manuscript_text=MANUSCRIPT.replace("References\n", "Source notes\n", 1), reference_section_present=False),
        ["pqa.references_section_unresolved"], "blocked", "major_revision")),
    ("ethics_reporting_gap_not_method_error", lambda: (d(ethics_statement="",
        manuscript_text=MANUSCRIPT.replace("The ethics committee approved the protocol and participants gave informed consent.\n", "")),
        ["pqa.ethics_statement_missing"], "review", "minor_revision")),
    ("excerpt_does_not_force_article_structure", lambda: (d(source_scope="excerpt"),
        [], "clean", "no_major_defect_detected")),
]


def main() -> int:
    rows = []
    for name, builder in SCEN:
        spec, expected, want_status, want_grade = builder()
        result = Q.audit(spec)
        fired = [f["rule"] for f in result["findings"]]
        missing = [r for r in expected if r not in fired]
        spurious = [] if expected else fired
        wrong_status = result["status"] != want_status
        wrong_grade = result["overall_assessment"]["grade"] != want_grade
        ok = not missing and not spurious and not wrong_status and not wrong_grade
        # Every result preserves the complete declared contract.
        contract_ok = (result.get("case_id") == spec["case_id"] and
                       result.get("reviewer_note") == "preserve-this-contract-value" and
                       all(k in result for k in spec["output_contract"]))
        numeric_ok = True
        if name == "impossible_sample_accounting_recomputed":
            calc = next(c for c in result["recomputations"] if c["check"] == "sample_accounting")
            numeric_ok = calc["computed"]["analysed_minus_recruited"] == 14
        if name == "numeric_conflict_recomputed":
            calc = next(c for c in result["recomputations"] if c["check"] == "reported_value_comparison")
            numeric_ok = calc["computed"]["difference"] == 2.0 and calc["consistent"] is False
        ok = ok and contract_ok and numeric_ok
        rows.append({"scenario": name, "expected": expected, "fired": fired,
                     "status": result["status"], "expected_status": want_status,
                     "grade": result["overall_assessment"]["grade"], "expected_grade": want_grade,
                     "contract_ok": contract_ok, "numeric_ok": numeric_ok,
                     "missing": missing, "spurious": spurious, "pass": ok})
        print(f"{'PASS' if ok else 'FAIL'} {name:<40} missing={missing} spurious={spurious}")
    # Determinism and preservation of all eleven dimensions are invariants.
    one = Q.audit(d())
    two = Q.audit(d())
    extra = [
        ("byte_stable_audit", json.dumps(one, ensure_ascii=False, sort_keys=True) == json.dumps(two, ensure_ascii=False, sort_keys=True)),
        ("eleven_dimension_coverage", [r["dimension"] for r in one["dimension_reviews"]] == list(Q.DIMENSIONS)),
        ("clean_has_no_findings", one["findings"] == []),
        ("clean_has_all_contract_keys", all(k in one for k in BASE["output_contract"])),
    ]
    for name, ok in extra:
        rows.append({"scenario": name, "pass": ok})
        print(f"{'PASS' if ok else 'FAIL'} {name}")
    passed = sum(bool(r["pass"]) for r in rows)
    report = {"schema_version": "quality-bench/v1", "scenarios": rows,
              "totals": {"passed": passed, "of": len(rows)},
              "clean_baseline_findings": one["findings"],
              "note": "Qualified RCT and observational designs cross-check false positives; numeric fixtures are actually recomputed."}
    (Path(__file__).resolve().parent / "report_quality.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n{passed}/{len(rows)} pass")
    return 0 if passed == len(rows) else 1


if __name__ == "__main__":
    raise SystemExit(main())
