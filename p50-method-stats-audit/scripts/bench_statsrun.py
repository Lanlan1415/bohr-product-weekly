"""Methods/statistics v2 regression, recomputation and false-positive suite.

The qualified design is crossed with known statistical errors.  Values asserted
here are actually computed by statscore; no expected result is a paper answer.
"""
from __future__ import annotations
import copy
import json
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import statscore as SC  # noqa: E402
import statsrun as AUD  # noqa: E402

TEXT = """1 Introduction
We asked whether standardized feedback changed reaction time compared with sham feedback.
2 Methods
We performed a randomized double-blind parallel trial in independent participants.
The statistician generated a block allocation sequence and concealed assignments.
The sham comparator and blinded outcome assessment were specified before recruitment.
The primary outcome was reaction time in milliseconds, a continuous measurement.
We recruited 64 participants and analysed all 64 without exclusions.
Sample size used Cohen d=0.5, alpha=0.05 and power=0.80 from the pilot study.
The primary analysis used linear regression with 95% confidence intervals.
Multiplicity was controlled across the confirmatory family.
There were no missing outcomes and every observation was retained.
No outliers were detected by the prespecified residual rule.
Robustness analyses used Welch estimation and complete-case sensitivity assumptions.
3 Results
The mean reaction-time difference was 0.4 ms with a 95% confidence interval.
The effect estimate and exact p value are reported in Table 1.
The intervention improved mean reaction time in this randomized sample.
4 Reproducibility
The data version is d64-v1 and analysis code version is commit abc123.
The frozen command was python analyse.py --seed 17; the recorded seed was 17.
Data and complete analysis outputs are archived for independent review.
References
Doe J (2020). Independent-unit design and reporting. Journal of Methods 2:3-9.
"""
T_RECORD = {"type": "welch_t", "name": "primary mean contrast", "source_locator": "Results Table 1",
            "source_quote": "The mean reaction-time difference was 0.4 ms with a 95% confidence interval.",
            "mean1": 5.2, "sd1": 1.2, "n1": 30, "mean2": 4.8, "sd2": 1.8, "n2": 35,
            "alternative": "two-sided", "confidence": 0.95}
BASE = {
    "case_id": "methods-local-fixture", "manuscript_version": "methods-fixture-v1",
    "source_scope": "full_methods_report", "manuscript_text": TEXT,
    "research_question_type": "causal_effect", "design": "rct", "controls": "sham parallel arm",
    "randomisation": "concealed block allocation", "blinding": "double blind",
    "inferential": True, "model": "linear_regression", "outcome_type": "continuous",
    "sample_size": "n=64 independent participants",
    "sample_size_basis": "pilot d=0.5 alpha=0.05 power=0.80",
    "recruited_n": 64, "analysed_n": 64, "attrition_handling": "no attrition",
    "p_values_reported": True, "confidence_intervals": "95% CI for the primary contrast",
    "multiple_comparisons": "Benjamini-Hochberg within the declared confirmatory family",
    "variables": [
        {"name": "feedback", "role": "exposure", "type": "binary", "definition": "standardized versus sham feedback",
         "missing_handling": "no missing exposure", "cutpoint": "", "cutpoint_basis": ""},
        {"name": "reaction_time", "role": "outcome", "type": "continuous", "definition": "milliseconds after cue",
         "missing_handling": "no missing primary outcome", "cutpoint": "", "cutpoint_basis": ""},
    ],
    "endpoints": [{"name": "reaction_time", "primary": True, "timepoint": "end of session"}],
    "comparisons": [{"name": "feedback versus sham", "significant": True}],
    "independence": {"name": "independent denominator", "source_locator": "Methods participants",
                     "allocation_unit": "participant", "analysis_unit": "participant",
                     "model": "linear regression of independent participants", "n_observations": 64,
                     "n_independent_units": 64, "treats_observations_as_independent": True},
    "missing_data": {"name": "missing primary outcomes", "source_locator": "Methods population",
                     "expected_n": 64, "observed_n": 64, "missing_count": 0,
                     "handling": "no missing outcome", "mechanism_or_assumption": "complete records verified"},
    "outliers": {"name": "outlier policy", "source_locator": "Methods residual rule",
                 "detected": False, "removed": False, "prespecified": True,
                 "handling": "all observations retained", "sensitivity_analysis": "all-observation analysis"},
    "statistical_checks": [T_RECORD],
    "power_analyses": [{"name": "Pilot-based achieved power", "source_locator": "Methods sample size",
                        "effect_size": 0.5, "nobs1": 32, "ratio": 1.0, "alpha": 0.05,
                        "alternative": "two-sided", "solve": "power"}],
    "comparison_families": [{"name": "confirmatory p family", "source_locator": "Table 1", "method": "bh",
                             "comparisons": [{"name": "primary", "p": 0.29033248197735895}]}],
    "diagnostics": [{"type": "levene", "name": "parallel-arm variance check", "source_locator": "Supplement S2",
                     "center": "median", "model_requires_equal_variance": True,
                     "groups": [[10, 11, 9, 10, 11, 9, 10, 11], [10.2, 11.2, 9.2, 10.2, 11.2, 9.2, 10.2, 11.2]]}],
    "p_value_statements": [{"name": "bounded primary interpretation", "source_locator": "Results paragraph 1",
                            "source_quote": "The intervention improved mean reaction time in this randomized sample.",
                            "p_value": 0.01, "alpha": 0.05, "significant": True,
                            "effect_size": "Hedges g=0.52", "claim": "The intervention improved mean reaction time in this randomized sample."}],
    "conclusion": "The intervention improved mean reaction time in this randomized sample.",
    "sensitivity_analyses": [{"name": "Welch robustness", "result": "same direction and compatible CI"}],
    "computational_study": True,
    "reproducibility": {"name": "frozen analysis", "source_locator": "Reproducibility",
                        "code_used": True, "randomness_used": True, "data_version": "d64-v1",
                        "code_version": "abc123", "analysis_command": "python analyse.py --seed 17", "seed": 17},
    "review_complete": True,
    "output_contract": {"audit_report": "array", "statistical_recalculations": "array",
                        "evidence_and_boundaries": "object", "result_status": "object",
                        "manuscript_version": "string", "reviewer_note": "string"},
    "reviewer_note": "preserve-contract-value",
}


def d(**over):
    spec = copy.deepcopy(BASE)
    spec.update(over)
    return spec


def one_check(**changes):
    item = copy.deepcopy(T_RECORD)
    item.update(changes)
    return [item]


def model_outcome_mismatch():
    spec = d(outcome_type="binary")
    spec["variables"][1]["type"] = "binary"
    return spec


def correctly_reported_summary():
    calc = SC.independent_t(5.2, 1.2, 30, 4.8, 1.8, 35)
    return d(statistical_checks=one_check(reported_p=calc["p_value"], reported_statistic=calc["statistic"],
                                          reported_df=calc["df"], reported_ci=calc["mean_difference_ci"],
                                          reported_effect_size=calc["cohens_d"], effect_type="cohens_d"))


def family_with_declared_adjustments(correct=True):
    family = {"name": "BH family", "method": "bh", "source_locator": "Table 2",
              "comparisons": [{"name": "a", "p": 0.01, "reported_adjusted_p": 0.03},
                              {"name": "b", "p": 0.02, "reported_adjusted_p": 0.03},
                              {"name": "c", "p": 0.04, "reported_adjusted_p": 0.04}]}
    if not correct:
        family["comparisons"][2]["reported_adjusted_p"] = 0.04 / 3
    return d(comparison_families=[family], comparisons=[{"name": "a"}, {"name": "b"}, {"name": "c"}])


def linear_regression(coefficient_mismatch=False):
    x = list(range(1, 11))
    y = [1.1, 2.9, 5.2, 6.8, 9.3, 10.7, 13.2, 14.8, 17.1, 18.9]
    diag = {"type": "regression", "name": "linear residual audit", "source_locator": "Supplement model fit",
            "y": y, "x": [[v] for v in x], "reset_power": 3}
    if coefficient_mismatch:
        diag["reported_coefficients"] = [0.0, 0.0]
    return d(diagnostics=[diag])


def nonlinear_regression():
    x = list(range(1, 11))
    y = [0.8 + 1.5 * v + 0.45 * v * v for v in x]
    return d(diagnostics=[{"type": "regression", "name": "known neglected curvature",
                           "source_locator": "Supplement nonlinear fit", "y": y,
                           "x": [[v] for v in x], "reset_power": 3}])


SCEN = [
    ("clean_qualified_design", lambda: (d(), [], "clean", "no_major_defect_detected")),
    ("correct_reported_summary_quiet", lambda: (correctly_reported_summary(), [], "clean", "no_major_defect_detected")),
    ("known_wrong_p_detected", lambda: (d(statistical_checks=one_check(reported_p=0.000001)),
        ["msv.reported_p_recompute_mismatch"], "blocked", "major_methods_revision")),
    ("known_wrong_t_detected", lambda: (d(statistical_checks=one_check(reported_statistic=0.0)),
        ["msv.reported_statistic_recompute_mismatch"], "blocked", "major_methods_revision")),
    ("reported_p_ci_conflict_detected", lambda: (d(statistical_checks=one_check(reported_p=0.049, reported_ci=[-1.0, 1.0])),
        ["msv.p_ci_decision_conflict"], "blocked", "major_methods_revision")),
    ("different_ci_alpha_levels_not_false_conflict", lambda: (d(statistical_checks=one_check(confidence=0.90, alpha=0.05)),
        [], "clean", "no_major_defect_detected")),
    ("power_n_required_recomputed", lambda: (d(power_analyses=[{"name": "sample solve", "effect_size": 0.5,
        "power": 0.8, "alpha": 0.05, "ratio": 1.0, "solve": "nobs1"}]), [], "clean", "no_major_defect_detected")),
    ("power_report_mismatch_detected", lambda: (d(power_analyses=[{"name": "power mismatch", "effect_size": 0.5,
        "nobs1": 32, "ratio": 1.0, "alpha": 0.05, "solve": "power", "reported_power": 0.99}]),
        ["msv.power_recompute_mismatch"], "blocked", "major_methods_revision")),
    ("power_missing_input_not_method_error", lambda: (d(power_analyses=[{"name": "insufficient", "solve": "power", "effect_size": 0.5}]),
        [], "review", "review_incomplete")),
    ("correct_bh_recomputed_quiet", lambda: (family_with_declared_adjustments(), [], "clean", "no_major_defect_detected")),
    ("wrong_bh_detected", lambda: (family_with_declared_adjustments(False),
        ["msv.adjusted_p_recompute_mismatch"], "blocked", "major_methods_revision")),
    ("confirmatory_multiplicity_gap", lambda: (dict(family_with_declared_adjustments(), **{}) if False else None, [], "clean", "no_major_defect_detected")),
    ("pseudoreplication_design_detected", lambda: (d(independence={"name": "site confounding", "source_locator": "Methods sites",
        "allocation_unit": "clinic", "analysis_unit": "participant", "model": "ordinary independent t test",
        "n_observations": 120, "n_independent_units": 10, "treats_observations_as_independent": True}),
        ["msv.pseudoreplication_independence_conflict", "msv.pseudoreplication_count_confirmed"], "blocked", "major_methods_revision")),
    ("cluster_aware_design_quiet", lambda: (d(independence={"name": "cluster model", "source_locator": "Methods sites",
        "allocation_unit": "clinic", "analysis_unit": "participant", "model": "linear mixed model with clinic random intercept",
        "accounts_for_clustering": True, "n_observations": 120, "n_independent_units": 10,
        "treats_observations_as_independent": False}), [], "clean", "no_major_defect_detected")),
    ("design_question_mismatch_detected", lambda: (d(research_question_type="diagnostic_accuracy"),
        ["msv.design_question_mismatch"], "blocked", "major_methods_revision")),
    ("model_outcome_mismatch_detected", lambda: (model_outcome_mismatch(),
        ["msv.model_outcome_mismatch", "msa.model_type_mismatch"], "blocked", "major_methods_revision")),
    ("randomization_reporting_gap_preserved", lambda: (d(randomisation=""),
        ["msa.randomisation_unstated"], "review", "minor_methods_revision")),
    ("missing_handling_gap_not_method_error", lambda: (d(missing_data={"name": "missing outcomes", "source_locator": "Flow diagram",
        "expected_n": 64, "observed_n": 58, "handling": "complete case"}),
        ["msv.missing_assumption_unreported"], "review", "minor_methods_revision")),
    ("missing_count_conflict_recomputed", lambda: (d(missing_data={"name": "bad flow", "source_locator": "Flow diagram",
        "expected_n": 64, "observed_n": 58, "missing_count": 2, "handling": "complete case", "mechanism_or_assumption": "MAR"}),
        ["msv.missing_count_inconsistent"], "blocked", "major_methods_revision")),
    ("data_driven_outlier_exclusion_detected", lambda: (d(outliers={"name": "post hoc exclusion", "source_locator": "Results exclusion note",
        "detected": True, "removed": True, "prespecified": False}),
        ["msv.data_driven_outlier_exclusion"], "blocked", "major_methods_revision")),
    ("prespecified_outlier_policy_quiet", lambda: (d(outliers={"name": "justified exclusion", "source_locator": "Methods SAP",
        "detected": True, "removed": True, "prespecified": True, "handling": "prespecified instrument failure only",
        "sensitivity_analysis": "all available observations"}), [], "clean", "no_major_defect_detected")),
    ("p_as_probability_of_null_detected", lambda: (d(p_value_statements=[{"name": "wrong p definition", "source_locator": "Discussion",
        "p_value": 0.03, "claim": "The probability that the null hypothesis is true is 0.03."}]),
        ["msv.p_probability_of_null_misread"], "blocked", "major_methods_revision")),
    ("nonsignificant_as_equivalence_detected", lambda: (d(p_value_statements=[{"name": "wrong equivalence", "source_locator": "Discussion",
        "p_value": 0.62, "claim": "p=0.62 proves no effect and equivalence."}]),
        ["msv.nonsignificant_as_no_effect"], "blocked", "major_methods_revision")),
    ("significance_as_magnitude_detected", lambda: (d(p_value_statements=[{"name": "wrong magnitude", "source_locator": "Discussion",
        "p_value": 0.001, "claim": "This is a large clinically meaningful effect."}]),
        ["msv.significance_equated_with_importance"], "review", "minor_methods_revision")),
    ("difference_in_significance_detected", lambda: (d(p_value_statements=[{"name": "wrong indirect comparison", "source_locator": "Subgroup discussion",
        "p_value": 0.04, "claim": "Effects differ between subgroups.", "significant_vs_nonsignificant_comparison": True}]),
        ["msv.significance_difference_without_direct_test"], "blocked", "major_methods_revision")),
    ("causal_correlation_detected", lambda: (d(design="observational", research_question_type="descriptive",
        conclusion="Feedback causes a persistent improvement."),
        ["msv.correlation_causal_overreach"], "blocked", "major_methods_revision")),
    ("qualified_observational_association_quiet", lambda: (d(design="observational", research_question_type="descriptive",
        conclusion="Feedback was associated with faster responses in this sample."), [], "clean", "no_major_defect_detected")),
    ("sensitivity_gap_detected", lambda: (d(sensitivity_analyses=[]),
        ["msv.sensitivity_analysis_missing"], "review", "minor_methods_revision")),
    ("reanalysis_version_gap_detected", lambda: (d(reproducibility={"name": "incomplete frozen run", "source_locator": "Code statement",
        "code_used": True, "randomness_used": True, "data_version": "d64-v1", "analysis_command": "python analyse.py", "seed": 17}),
        ["msv.reanalysis_fields_missing"], "review", "minor_methods_revision")),
    ("reanalysis_value_mismatch_computed", lambda: (d(reproducibility=dict(BASE["reproducibility"], reported_values=[
        {"name": "RMSE", "reported": 1.2, "recomputed": 1.0, "tolerance": 0.05}])),
        ["msv.reanalysis_value_mismatch"], "blocked", "major_methods_revision")),
    ("linear_model_qualified", lambda: (linear_regression(), [], "clean", "no_major_defect_detected")),
    ("nonlinearity_reset_detected", lambda: (nonlinear_regression(),
        ["msv.model_specification_signal"], "review", "minor_methods_revision")),
    ("wrong_ols_coefficients_detected", lambda: (linear_regression(True),
        ["msv.regression_coefficient_recompute_mismatch"], "blocked", "major_methods_revision")),
    ("levene_assumption_signal_quantified", lambda: (d(diagnostics=[{"type": "levene", "name": "heterogeneous groups",
        "source_locator": "Raw groups", "model_requires_equal_variance": True, "center": "median",
        "groups": [[1, 2, 3, 4, 2, 3, 2, 3], [0, 20, 40, 60, 1, 40, 5, 30]]}]),
        ["msv.equal_variance_assumption_signal"], "review", "minor_methods_revision")),
    ("jb_normality_signal_quantified", lambda: (d(diagnostics=[{"type": "normality", "name": "skewed residuals",
        "source_locator": "Residual data", "model_assumes_normality": True,
        "values": [0, 0, 0, 0, 0, 0, 0, 0, 0, 100]}]),
        ["msv.residual_normality_signal"], "review", "minor_methods_revision")),
    ("pearson_computed_without_causal_claim", lambda: (d(diagnostics=[{"type": "correlation", "name": "auxiliary correlation",
        "source_locator": "Supplement pairs", "x": [1, 2, 3, 4], "y": [2, 4, 6, 8]}]), [], "clean", "no_major_defect_detected")),
    ("insufficient_t_inputs_incomplete_not_defect", lambda: (d(statistical_checks=[{"type": "welch_t", "name": "missing SD",
        "source_locator": "Table 1", "mean1": 5.2, "n1": 30, "mean2": 4.8, "n2": 35}]), [], "review", "review_incomplete")),
    ("invented_source_quote_rejected", lambda: (d(statistical_checks=one_check(source_quote="A fake p value of 0.0001 was reported.")),
        ["msv.evidence_not_in_source"], "blocked", "review_incomplete")),
    ("substantiated_reviewer_issue_preserved", lambda: (d(review_findings=[{"dimension": "model_choice", "severity": "high",
        "source_locator": "Methods Table 1", "finding": "Repeated observations were analysed with a between-subject model.",
        "defect_class": "method_defect", "suggestion": "Fit a repeated-measures model."}]),
        ["msv.reviewer_substantiated_issue"], "blocked", "major_methods_revision")),
    ("unverified_reviewer_issue_rejected", lambda: (d(review_findings=[{"dimension": "model_choice", "severity": "high",
        "finding": "The model was wrong.", "defect_class": "method_defect"}]),
        ["msv.reviewer_issue_unverified"], "blocked", "review_incomplete")),
    ("coverage_flag_cannot_fabricate_clean", lambda: (d(review_findings=[{"dimension": "model_choice", "severity": "low",
        "finding": "Bounded suggestion.", "defect_class": "suggestion"}]), ["msv.reviewer_issue_unverified"], "blocked", "review_incomplete")),
]

# A separate true reporting-gap family avoids mutating a built tuple in a scenario.
SCEN[11] = ("confirmatory_multiplicity_gap", lambda: ((lambda s: (
    s["comparison_families"][0].pop("method", None),
    s["comparison_families"][0].update(confirmatory=True),
    s)[-1])(d(comparison_families=[{"name": "uncorrected family", "confirmatory": True,
                                      "comparisons": [{"name": "a", "p": 0.01}, {"name": "b", "p": 0.02}]}])),
    ["msv.multiplicity_unaddressed"], "review", "minor_methods_revision"))


def main():
    rows = []
    for name, builder in SCEN:
        spec, expected, want_status, want_grade = builder()
        result = AUD.audit(spec)
        fired = [f["rule"] for f in result["findings"]]
        missing = [rule for rule in expected if rule not in fired]
        spurious = [] if expected else fired
        ok = not missing and not spurious and result["status"] == want_status and result["overall_assessment"]["grade"] == want_grade
        contract_ok = result.get("case_id") == spec["case_id"] and result.get("reviewer_note") == "preserve-contract-value" and all(k in result for k in spec["output_contract"])
        numeric_ok = True
        if name == "known_wrong_p_detected":
            calc = next(c for c in result["statistical_recalculations"] if c.get("name") == "primary mean contrast")
            numeric_ok = abs(calc["p_value"] - 0.29033248197735895) < 1e-12 and abs(calc["df"] - 59.61035784930767) < 1e-10
        if name == "power_n_required_recomputed":
            calc = next(c for c in result["statistical_recalculations"] if c.get("name") == "sample solve")
            numeric_ok = calc["nobs1_rounded_up"] == 63 and calc["total_n_rounded_up"] == 126 and abs(calc["nobs1_continuous"] - 62.79088407460955) < 1e-10
        if name == "correct_bh_recomputed_quiet":
            calc = next(c for c in result["statistical_recalculations"] if c.get("name") == "BH family")
            numeric_ok = calc["adjusted"] == [0.03, 0.03, 0.04]
        if name == "pseudoreplication_design_detected":
            calc = next(c for c in result["statistical_recalculations"] if c["type"] == "independent_unit_accounting")
            numeric_ok = calc["observations_per_independent_unit"] == 12
        if name == "missing_count_conflict_recomputed":
            calc = next(c for c in result["statistical_recalculations"] if c["type"] == "missing_data_accounting")
            numeric_ok = calc["missing_count"] == 2
        if name == "reanalysis_value_mismatch_computed":
            calc = next(c for c in result["statistical_recalculations"] if c["type"] == "reanalysis_value_comparison")
            numeric_ok = abs(calc["difference"] - 0.2) < 1e-12 and not calc["within_tolerance"]
        if name in {"insufficient_t_inputs_incomplete_not_defect", "power_missing_input_not_method_error"}:
            numeric_ok = all(c.get("computable") for c in result["statistical_recalculations"] if c.get("type") not in {"power", "independent_t"}) and not result["findings"] and result["evidence_and_boundaries"]["not_computable"]
        ok = ok and contract_ok and numeric_ok
        rows.append({"scenario": name, "expected": expected, "fired": fired, "missing": missing,
                     "spurious": spurious, "status": result["status"], "expected_status": want_status,
                     "grade": result["overall_assessment"]["grade"], "expected_grade": want_grade,
                     "contract_ok": contract_ok, "numeric_ok": numeric_ok, "pass": ok})
        print(f"{'PASS' if ok else 'FAIL'} {name:<53} missing={missing} spurious={spurious}")
    # Direct mathematical anchors independent of the higher-level auditing logic.
    t_anchor = SC.t_sf_two(1.0, 10)
    t_quantile = SC.t_ppf(0.975, 10)
    clean = AUD.audit(d())
    extra = [
        ("math_t_tail_known_reference", abs(t_anchor - 0.3408931323020593) < 1e-12),
        ("math_t_quantile_known_reference", abs(t_quantile - 2.228138851963773) < 1e-7),
        ("math_chi2_df2_exact", abs(SC.chi2_sf(2, 2) - math.exp(-1)) < 1e-13),
        ("clean_zero_findings", clean["findings"] == [] and clean["status"] == "clean"),
        ("all_fourteen_dimensions", [x["dimension"] for x in clean["method_dimensions"]] == list(AUD.DIMENSIONS)),
        ("all_clean_recalculations_computable", all(c.get("computable") for c in clean["statistical_recalculations"])),
        ("deterministic_repeat", json.dumps(clean, ensure_ascii=False, sort_keys=True) == json.dumps(AUD.audit(d()), ensure_ascii=False, sort_keys=True)),
    ]
    for name, ok in extra:
        rows.append({"scenario": name, "pass": ok})
        print(f"{'PASS' if ok else 'FAIL'} {name}")
    passed = sum(bool(r["pass"]) for r in rows)
    report = {"schema_version": "method-statistics-bench/v2", "scenarios": rows,
              "totals": {"passed": passed, "of": len(rows)}, "clean_baseline_findings": clean["findings"],
              "anchors": {"welch_p": 0.29033248197735895, "welch_df": 59.61035784930767,
                          "normal_power_nobs1": 62.79088407460955, "bh_adjusted": [0.03, 0.03, 0.04]},
              "note": "Qualified designs and known numeric/model errors cross-check false positives; non-computable inputs never become method defects."}
    (Path(__file__).resolve().parent / "report_statsrun.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n{passed}/{len(rows)} pass")
    return 0 if passed == len(rows) else 1


if __name__ == "__main__":
    raise SystemExit(main())
