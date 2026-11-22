"""Benchmark for the method-and-stats section (study design, variables, sample size).

One scenario per rule, aligned to the five review facets the brief states:

  研究设计 -> design_unstated, control_missing, randomisation_unstated,
              blinding_unstated, endpoint_not_primary
  变量定义 -> variable_undefined, variable_role_missing, variable_type_missing,
              cutpoint_unjustified, missing_handling_undeclared, model_type_mismatch
  统计方法 -> model_unstated, multiple_comparisons_unaddressed, ci_missing
  样本量   -> sample_size_missing, sample_size_basis_missing, attrition_unaccounted

Every defect scenario ships with a false-positive guard: the same spec with the
gap filled (or the practice explicitly declared) must report nothing.

    python bench_method.py
"""

from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import sections as S  # noqa: E402

BASE = {
    "section": "method_stats",
    "design": "rct",
    "controls": "placebo group, parallel arms",
    "randomisation": "computer-generated block randomisation, 1:1 allocation",
    "blinding": "double-blind (participant and assessor)",
    "inferential": True,
    "model": "linear_regression",
    "sample_size": "n = 64 (32 per arm)",
    "sample_size_basis": "power 0.8, alpha 0.05, effect d = 0.5 from pilot M1",
    "recruited_n": 70,
    "analysed_n": 64,
    "attrition_handling": "6 lost to follow-up; intention-to-treat for the primary endpoint",
    "confidence_intervals": "95% CI reported for every effect size",
    "multiple_comparisons": "Bonferroni across the family of primary endpoints",
    "variables": [
        {"name": "dose", "role": "exposure", "type": "continuous",
         "definition": "mg/kg/day administered, verified by dispensing log",
         "missing_handling": "complete-case (no missing exposures in record)",
         "cutpoint": "", "cutpoint_basis": ""},
        {"name": "reaction_time", "role": "outcome", "type": "continuous",
         "definition": "milliseconds from cue onset to response, median of 20 trials",
         "missing_handling": "multiple imputation (m = 5) under MAR",
         "cutpoint": "", "cutpoint_basis": ""},
    ],
    "endpoints": [{"name": "reaction_time", "primary": True, "timepoint": "week 12"}],
    "comparisons": [{"name": "low dose vs control", "significant": True},
                    {"name": "high dose vs control", "significant": True}],
}


def d(**over):
    s = copy.deepcopy(BASE)
    s.update(over)
    return s


def var(index, **over):
    s = copy.deepcopy(BASE)
    s["variables"][index].update(over)
    return s


SCEN = [
    ("clean", lambda: (copy.deepcopy(BASE), [])),

    # nothing to audit
    ("no_study", lambda: (d(design="", variables=[], endpoints=[], comparisons=[],
                            inferential=False), ["msa.no_study"])),

    # 研究设计
    ("design_unstated", lambda: (d(design=""), ["msa.design_unstated"])),
    ("control_missing", lambda: (d(controls=""), ["msa.control_missing"])),
    ("randomisation_unstated", lambda: (d(randomisation=""),
                                        ["msa.randomisation_unstated"])),
    ("blinding_unstated",
     lambda: ((lambda s: (s.pop("blinding"), s)[1])(copy.deepcopy(BASE)),
              ["msa.blinding_unstated"])),
    ("endpoint_not_primary",
     lambda: (d(endpoints=[{"name": "reaction_time", "primary": False,
                            "timepoint": "week 12"}]),
              ["msa.endpoint_not_primary"])),

    # 变量定义
    ("variable_undefined", lambda: (var(0, definition=""), ["msa.variable_undefined"])),
    ("variable_role_missing", lambda: (var(0, role=""), ["msa.variable_role_missing"])),
    ("variable_type_missing", lambda: (var(0, type=""), ["msa.variable_type_missing"])),
    ("cutpoint_unjustified",
     lambda: (var(1, cutpoint="> 300 ms", cutpoint_basis=""), ["msa.cutpoint_unjustified"])),
    ("missing_handling_undeclared",
     lambda: (var(0, missing_handling=""), ["msa.missing_handling_undeclared"])),
    ("model_type_mismatch", lambda: (d(model="linear_regression",
                                       variables=[
                                           {"name": "dose", "role": "exposure",
                                            "type": "continuous",
                                            "definition": "mg/kg/day administered",
                                            "missing_handling": "complete-case"},
                                           {"name": "readmit", "role": "outcome",
                                            "type": "binary",
                                            "definition": "readmission within 30 days",
                                            "missing_handling": "complete-case"}]),
                                     ["msa.model_type_mismatch"])),

    # 统计方法
    ("model_unstated", lambda: (d(model=""), ["msa.model_unstated"])),
    ("multiple_comparisons_unaddressed",
     lambda: (d(comparisons=BASE["comparisons"] + [
         {"name": "arm A vs arm B", "significant": False},
         {"name": "sex subgroup", "significant": True}],
         multiple_comparisons=""),
         ["msa.multiple_comparisons_unaddressed"])),
    ("ci_missing", lambda: (d(confidence_intervals="", p_values_reported=True),
                            ["msa.ci_missing"])),

    # 样本量
    ("sample_size_missing", lambda: (d(sample_size=""), ["msa.sample_size_missing"])),
    ("sample_size_basis_missing",
     lambda: (d(sample_size_basis=""), ["msa.sample_size_basis_missing"])),
    ("attrition_unaccounted",
     lambda: (d(attrition_handling=""), ["msa.attrition_unaccounted"])),

    # false-positive guards: declared practice, single-arm study, n stated inline,
    # few comparisons, no CI demand without p-value claim, no attrition gap
    ("fp_open_label_explicit",
     lambda: (d(blinding="open-label (objective outcome, assessor-blind analysis)"), [])),
    ("fp_single_arm_no_control", lambda: (d(design="single_arm"), [])),
    ("fp_n_stated_inline",
     lambda: (d(sample_size="",
                variables=[dict(BASE["variables"][0],
                                definition="dose in mg/kg/day, n = 64 enrolled")]), [])),
    ("fp_two_comparisons_no_mcp",
     lambda: (d(multiple_comparisons="",
                multiple_comparisons_note=""), [])),
    ("fp_no_p_no_ci_demand",
     lambda: (d(p_values_reported=False), [])),
    ("fp_attrition_none", lambda: (d(recruited_n=64, analysed_n=64), [])),

    # CJK design names must gate the comparative checks the same way
    ("cjk_control_missing",
     lambda: (d(design="随机对照试验", controls="", randomisation="区组随机化（1:1）",
                blinding="双盲"), ["msa.control_missing"])),
    ("fp_cjk_control_declared",
     lambda: (d(design="随机对照试验", controls="安慰剂对照组（n=32）",
                randomisation="区组随机化（1:1）", blinding="双盲"), [])),
]


def main() -> int:
    rows = []
    for name, builder in SCEN:
        spec, expect = builder()
        findings, status, counts = S.run(spec, "method_stats")
        fired = {f["rule"] for f in findings}
        missing = [r for r in expect if r not in fired]
        spurious = [] if expect else [f["rule"] for f in findings]
        ok = not missing and not spurious
        rows.append({"scenario": name, "expected": expect, "fired": sorted(fired),
                     "missing": missing, "spurious": spurious, "pass": ok,
                     "status": status})
        print(f"{'PASS' if ok else 'FAIL'}  {name:<34} missing={missing} spurious={spurious}")

    passed = sum(1 for r in rows if r["pass"])
    report = {"schema_version": "method-bench/v1", "scenarios": rows,
              "totals": {"passed": passed, "of": len(rows)},
              "note": ("One scenario per rule across the five method-stats facets. "
                       "Clean baselines must report nothing.")}
    (Path(__file__).resolve().parent / "report_method.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n{passed}/{len(rows)} pass")
    return 0 if passed == len(rows) else 1


if __name__ == "__main__":
    raise SystemExit(main())
