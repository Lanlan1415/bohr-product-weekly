"""Benchmark for the results-and-discussion skill.

One scenario per rule, aligned to the scoring points this task states:

  both sections, values matching the figures    -> results_missing, discussion_missing,
                                                   value_not_in_figures,
                                                   errorbar_meaning_undeclared,
                                                   errorbar_meaning_absent_from_text
  statistics and inference strength             -> statistic_missing,
                                                   non_significant_claimed_as_effect,
                                                   sample_size_absent
  negative results, conflicting literature, limitations
                                                 -> negative_result_omitted,
                                                   negative_result_absent_from_results,
                                                   conflicting_literature_ignored, limitation_*
  description kept apart from interpretation    -> interpretation_in_results,
                                                   mechanism_as_fact, causal_overreach
  every discussion claim attributable           -> discussion_uncited,
                                                   discussion_value_unsourced

    python bench_rd.py
"""

from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import sections as S  # noqa: E402

BASE = {
    "design": "experimental",
    "results_text": ("Uptake rose three-fold in the coated group (p < 0.01, t-test). "
                     "Arm B showed no change."),
    "discussion_text": ("The coated samples showed higher uptake, consistent with earlier work "
                        "[doe2020]. The mechanism may involve increased surface area [doe2020]. "
                        "Arm B did not reach significance. Roe reports a conflicting result "
                        "[roe2021]. Alternative explanations include measurement drift, which "
                        "was monitored with the same calibration samples [doe2020]."),
    "figures": [{"id": "Fig 1", "values": ["3", "three-fold", "0.01"],
                 "has_errorbar": True, "errorbar": "SD"}],
    "comparisons": [{"name": "coated vs control", "significant": True, "strength": "strong"},
                    {"name": "Arm B", "significant": False}],
    "literature": [{"key": "doe2020", "agrees": True},
                   {"key": "roe2021", "agrees": False, "finding": "no effect at low dose"}],
    "limitations": [{"level": "sample", "text": "single material system tested"},
                    {"level": "measurement", "text": "one coating thickness measured"},
                    {"level": "sample", "text": "Findings are limited to this material and should not be extrapolated to other materials."}],
}


def d(**over):
    s = copy.deepcopy(BASE)
    s.update(over)
    return s


def rich():
    s = d()
    s["results_text"] = ("Coated mean was 3.0 mmol versus 2.0 mmol for control; the difference was "
                         "1.0 mmol (95% CI 0.5 to 1.5; p = 0.01, t-test). "
                         "Arm B showed a higher response but did not reach significance.")
    s["figures"] = [{"id": "Table 1", "values": ["3", "2", "1", "0.5", "1.5", "0.01", "95"],
                     "has_errorbar": True, "errorbar": "95% CI"}]
    s["comparisons"] = [
        {"name": "coated vs control", "significant": True, "strength": "strong",
         "mean_treatment": 3.0, "mean_control": 2.0, "effect_type": "difference",
         "effect_size": 1.0, "ci_low": 0.5, "ci_high": 1.5, "p_value": 0.01,
         "source_ref": "Table 1, coated-control row"},
        {"name": "Arm B", "significant": False},
    ]
    return s


SCEN = [
    ("effect_uncertainty_clean", lambda: (rich(), [])),
    ("number_format_equivalent_clean", lambda: (d(
        figures=[{"id": "Fig 1", "values": ["3.0", "three-fold", "0.010"],
                  "has_errorbar": True, "errorbar": "SD"}]), [])),
    ("rounded_effect_clean", lambda: (d(
        results_text="Coated mean was 3.0004 mmol versus 2.0 mmol; the difference was 1.0 mmol "
                     "(95% CI 0.5 to 1.5; p = 0.01, t-test). Arm B showed no change.",
        figures=[{"id": "Table 1", "values": ["3.0004", "2", "1", "0.5", "1.5", "0.01", "95"],
                  "has_errorbar": True, "errorbar": "95% CI"}],
        comparisons=[{"name": "coated vs control", "significant": True, "strength": "strong",
                      "mean_treatment": 3.0004, "mean_control": 2.0,
                      "effect_type": "difference", "effect_size": 1.0,
                      "ci_low": 0.5, "ci_high": 1.5, "p_value": 0.01, "tolerance": 0.0005},
                     {"name": "Arm B", "significant": False}]), [])),

    ("clean", lambda: (d(), [])),

    # the two sections
    ("results_missing", lambda: (d(results_text=""), ["rd.results_missing"])),
    ("discussion_missing", lambda: (d(discussion_text=""), ["rd.discussion_missing"])),

    # values and figures
    ("value_not_in_figures",
     lambda: (d(results_text="Uptake rose 9-fold in the coated group (p < 0.01, t-test). "
                            "Arm B showed no change."),
              ["rd.value_not_in_figures"])),
    ("errorbar_undeclared",
     lambda: (d(figures=[{"id": "Fig 1", "values": ["3", "three-fold", "0.01"],
                          "has_errorbar": True}]), ["rd.errorbar_meaning_undeclared"])),

    # statistics
    ("statistic_missing",
     lambda: (d(results_text="Uptake rose three-fold in the coated group. Arm B showed no change."),
              ["rd.statistic_missing"])),
    ("comparison_no_verdict",
     lambda: (d(comparisons=[{"name": "coated vs control"}]),
              ["rd.comparison_no_verdict"])),
    ("nonsig_as_effect",
     lambda: (d(results_text="Uptake rose three-fold in the coated group (p < 0.01, t-test). "
                            "Arm B showed a higher response."),
              ["rd.non_significant_claimed_as_effect"])),

    # effect size, uncertainty and numeric caliber
    ("effect_value_mismatch", lambda: (d(
        results_text="Coated mean was 3.0 mmol versus 2.0 mmol; the difference was 1.2 mmol "
                     "(95% CI 0.5 to 1.5; p = 0.01, t-test). Arm B showed no change.",
        figures=[{"id": "Table 1", "values": ["3", "2", "1.2", "0.5", "1.5", "0.01", "95"],
                  "has_errorbar": True, "errorbar": "95% CI"}],
        comparisons=[dict(rich()["comparisons"][0], effect_size=1.2),
                     {"name": "Arm B", "significant": False}]), ["rd.effect_value_mismatch"])),
    ("effect_size_missing", lambda: (d(
        comparisons=[{key: value for key, value in rich()["comparisons"][0].items()
                      if key != "effect_size"}, {"name": "Arm B", "significant": False}]),
        ["rd.effect_size_missing"])),
    ("uncertainty_missing", lambda: (d(
        comparisons=[{key: value for key, value in rich()["comparisons"][0].items()
                      if key not in ("ci_low", "ci_high")}, {"name": "Arm B", "significant": False}]),
        ["rd.uncertainty_missing"])),
    ("uncertainty_inconsistent", lambda: (d(
        comparisons=[dict(rich()["comparisons"][0], ci_low=1.2), {"name": "Arm B", "significant": False}]),
        ["rd.uncertainty_inconsistent"])),
    ("significance_misclassified", lambda: (d(
        comparisons=[dict(rich()["comparisons"][0], significant=False),
                     {"name": "Arm B", "significant": False}]), ["rd.significance_misclassified"])),
    ("significance_ci_conflict", lambda: (d(
        comparisons=[dict(rich()["comparisons"][0], ci_low=-0.5, ci_high=2.5),
                     {"name": "Arm B", "significant": False}]), ["rd.significance_ci_conflict"])),
    ("malformed_significance_degrades", lambda: (d(
        comparisons=[{"name": "coated vs control", "significant": "perhaps"},
                     {"name": "Arm B", "significant": False}]), ["rd.comparison_no_verdict"])),
    ("alternative_explanations_missing", lambda: (d(
        discussion_text="The coated samples showed higher uptake, consistent with earlier work [doe2020]. "
                        "The mechanism may involve increased surface area [doe2020]. Arm B did not reach "
                        "significance. Roe reports a conflicting result [roe2021]."),
        ["rd.alternative_explanations_missing"])),
    ("extrapolation_boundary_missing", lambda: (d(limitations=BASE["limitations"][:2]),
        ["rd.extrapolation_boundary_missing"])),
    ("derivation_not_reproducible", lambda: (d(derivations=[{"value": 1.0, "formula": ""}]),
        ["rd.derivation_not_reproducible"])),

    # description vs interpretation
    ("interpretation_in_results",
     lambda: (d(results_text="Uptake rose three-fold because the coating increased surface area."),
              ["rd.interpretation_in_results"])),
    ("mechanism_as_fact",
     lambda: (d(discussion_text="The mechanism involves increased surface area [doe2020]."),
              ["rd.mechanism_as_fact"])),
    ("causal_overreach",
     lambda: (d(design="observational",
                discussion_text="The coating causes higher uptake [doe2020]."),
              ["rd.causal_overreach"])),

    # attribution
    ("discussion_uncited",
     lambda: (d(discussion_text="Earlier work agrees with this result."),
              ["rd.discussion_uncited"])),

    # honesty about what did not work
    ("negative_omitted",
     lambda: (d(discussion_text="The coated samples showed higher uptake, consistent with earlier "
                                "work [doe2020]. The mechanism may involve surface area [doe2020]. "
                                "Roe reports a conflicting result [roe2021]."),
              ["rd.negative_result_omitted"])),
    ("conflict_ignored",
     lambda: (d(discussion_text="The coated samples showed higher uptake, consistent with earlier "
                                "work [doe2020]. The mechanism may involve surface area [doe2020]. "
                                "Arm B did not reach significance."),
              ["rd.conflicting_literature_ignored"])),

    # limitations
    ("limitations_missing", lambda: (d(limitations=[]), ["rd.limitations_missing"])),
    ("limitation_vague",
     lambda: (d(limitations=[{"level": "method",
                              "text": "further work is needed to confirm this"},
                             {"level": "sample", "text": "single material"}]),
              ["rd.limitation_vague"])),
    ("limitation_narrow",
     lambda: (d(limitations=[{"level": "sample", "text": "single material system tested"}]),
              ["rd.limitation_level_narrow"])),

    # numbers
    ("unitless_number",
     lambda: (d(results_text="We observed 7 samples with no change."), ["rd.unitless_number"])),

    # --- false-positive guards: standard statistical prose must stay clean ---
    # "The results in Table 1" is a pointer, not a causal claim; the p-value needs no unit
    # and no figure entry.
    ("pointer_and_pvalue_clean",
     lambda: (d(results_text="The results in Table 1 show a three-fold rise (p < 0.01, "
                             "t-test). Arm B showed no change."), [])),
    # p, t(df), n, R², CI — statistics, not measurements.
    ("stats_exempt",
     lambda: (d(results_text="Uptake rose three-fold in the coated group (p < 0.01, "
                             "t(24) = 3.2, n = 6, R² = 0.87). Arm B showed no change."), [])),
    ("chinese_stats_clean",
     lambda: (d(results_text="包覆组摄取量提高了三倍（P<0.05，t检验）。B组无显著变化。",
                comparisons=[{"name": "coated vs control", "significant": True,
                              "strength": "strong"}],
                literature=[{"key": "doe2020", "agrees": True}]), [])),
    # "compared via a t-test" states a method, not a mechanism.
    ("method_via_clean",
     lambda: (d(results_text="组间差异通过t检验比较（P<0.05）。B组无显著变化。",
                comparisons=[{"name": "coated vs control", "significant": True,
                              "strength": "strong"}],
                literature=[{"key": "doe2020", "agrees": True}]), [])),
    # A sentence pointing at this study's own data is attributed without a citation key.
    ("data_ref_attributed",
     lambda: (d(discussion_text="This increase is consistent with the dose dependence "
                                "shown in Fig. 3.",
                comparisons=[{"name": "coated vs control", "significant": True,
                              "strength": "strong"}],
                literature=[{"key": "doe2020", "agrees": True}]), [])),

    # --- round 2: prose-side traceability and design coverage ----------------

    # 误差棒含义必须落在正文: the prose mentions the bars but never says SD/SEM/CI.
    ("errorbar_meaning_absent",
     lambda: (d(results_text="Uptake rose three-fold in the coated group (p < 0.01, t-test). "
                             "Error bars are shown for every group. Arm B showed no change."),
              ["rd.errorbar_meaning_absent_from_text"])),
    ("errorbar_meaning_stated_clean",
     lambda: (d(results_text="Uptake rose three-fold in the coated group (p < 0.01, t-test; "
                             "error bars show SD). Arm B showed no change."), [])),
    ("errorbar_required_not_mentioned",
     # Declarative opt-in: a case that requires the meaning in the text gets a
     # finding when the prose never mentions the bars at all.
     lambda: (d(require_errorbar_in_text=True), ["rd.errorbar_meaning_absent_from_text"])),

    # 阴性结果也要进结果段: the null comparison is named only in the discussion.
    ("negative_absent_from_results",
     lambda: (d(results_text="Uptake rose three-fold in the coated group (p < 0.01, t-test)."),
              ["rd.negative_result_absent_from_results"])),

    # 统计口径（n）必须可追溯: the comparison declares n and the text never carries it.
    ("sample_size_absent",
     lambda: (d(comparisons=[{"name": "coated vs control", "significant": True,
                              "strength": "strong", "n": 12},
                             {"name": "Arm B", "significant": False, "n": 10}]),
              ["rd.sample_size_absent"])),
    ("sample_size_present_clean",
     lambda: (d(results_text="Uptake rose three-fold in the coated group (p < 0.01, t-test, "
                             "n = 12). Arm B showed no change (n = 10).",
                comparisons=[{"name": "coated vs control", "significant": True,
                              "strength": "strong", "n": 12},
                             {"name": "Arm B", "significant": False, "n": 10}]), [])),

    # 讨论里的数字必须可回溯: 5-fold is in neither the figure data nor the results.
    ("discussion_value_unsourced",
     lambda: (d(discussion_text="The coated samples showed higher uptake, consistent with "
                                "earlier work [doe2020]; the 5-fold rise at low dose remains "
                                "unexplained. Arm B did not reach significance. Roe reports a "
                                "conflicting result [roe2021]."),
              ["rd.discussion_value_unsourced"])),
    ("discussion_value_traced_clean",
     lambda: (d(discussion_text="The coated samples showed higher uptake, consistent with "
                                "earlier work [doe2020]; the three-fold rise matches the "
                                "figure. Arm B did not reach significance. Roe reports a "
                                "conflicting result [roe2021]."), [])),

    # cross-sectional data cannot carry causal language either
    ("causal_overreach_cross_sectional",
     lambda: (d(design="cross-sectional",
                discussion_text="The coating causes higher uptake [doe2020]."),
              ["rd.causal_overreach"])),
]


def main() -> int:
    rows = []
    for name, builder in SCEN:
        spec, expect = builder()
        findings, status, counts = S.run(spec, "results_discussion")
        fired = {f["rule"] for f in findings}
        missing = [r for r in expect if r not in fired]
        spurious = [] if expect else [f["rule"] for f in findings]
        ok = not missing and not spurious
        rows.append({"scenario": name, "expected": expect, "fired": sorted(fired),
                     "missing": missing, "spurious": spurious, "pass": ok,
                     "status": status})
        print(f"{'PASS' if ok else 'FAIL'}  {name:<28} missing={missing} spurious={spurious}")

    passed = sum(1 for r in rows if r["pass"])
    report = {"schema_version": "rd-bench/v1", "scenarios": rows,
              "totals": {"passed": passed, "of": len(rows)},
              "note": ("One scenario per rule, aligned to the results/discussion scoring points. "
                       "Clean baselines must report nothing.")}
    (Path(__file__).resolve().parent / "report_rd.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n{passed}/{len(rows)} pass")
    return 0 if passed == len(rows) else 1


if __name__ == "__main__":
    raise SystemExit(main())
