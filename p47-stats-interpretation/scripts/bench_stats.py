"""Benchmark for the cleaning + statistical-interpretation engine.

Each scenario plants one defect (or proves one FP guard): the three claim checks
the task names — direction, significance language, computed-number citation —
plus the statistical layer the rubric asks for (descriptives, Welch t, effect
sizes, CI, IQR outliers, assumption advisories, multiple comparisons, the
claimed-p reconciliation), the malformed-claim degradations, the refusal paths
of the CLI, and the contract echo. The clean baseline must report nothing, so a
detector cannot pass by flagging everything. Distribution math is asserted
against table anchors (t and F critical values at 0.05).

    python bench_stats.py
"""

from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import cleandata as CL  # noqa: E402
import statsinterp as S  # noqa: E402

BASE_ROWS = [
    {"group": "control", "response": "12.4"},
    {"group": "control", "response": "11.8"},
    {"group": "control", "response": "12.9"},
    {"group": "drug", "response": "31.2"},
    {"group": "drug", "response": "30.6"},
    {"group": "drug", "response": "31.9"},
]
BASE_CLAIM = {
    "metric": "response", "test": "two-sample t-test", "group_col": "group",
    "group_a": "control", "group_b": "drug", "p": 0.01,
    "interpretation": "给药组均值为31.23，高于对照组的12.37，差异有统计学意义",
}
BASE = {
    "rows": copy.deepcopy(BASE_ROWS),
    "columns": [
        {"name": "group", "semantic": "categorical"},
        {"name": "response", "semantic": "numeric"},
    ],
    "stats": [copy.deepcopy(BASE_CLAIM)],
}

# recomputed from BASE_ROWS: mean_a=12.3667, mean_b=31.2333, diff=18.8667


def scen_clean():
    return "run", (copy.deepcopy(BASE["rows"]), copy.deepcopy(BASE)), []


def scen_direction_mismatch():
    s = copy.deepcopy(BASE)
    s["stats"][0]["interpretation"] = "给药组均值为31.23，低于对照组的12.37，差异有统计学意义"
    return "run", (copy.deepcopy(s["rows"]), s), ["stats.direction_mismatch"]


def scen_direction_field():
    s = copy.deepcopy(BASE)
    s["stats"][0]["interpretation"] = "给药组均值为31.23，对照组为12.37，差异有统计学意义"
    s["stats"][0]["direction"] = "lower"
    return "run", (copy.deepcopy(s["rows"]), s), ["stats.direction_mismatch"]


def scen_significance_overclaim():
    s = copy.deepcopy(BASE)
    s["stats"][0]["p"] = 0.30
    s["stats"][0]["interpretation"] = "给药组显著高于对照组（31.23 vs 12.37）"
    return "run", (copy.deepcopy(s["rows"]), s), ["stats.significance_mismatch"]


def scen_p_mismatch_claimed():
    """A claimed p the table contradicts: p=0.30 over separated groups.

    The wording stays honest (non-significant), so the language check is quiet;
    the claimed-p reconciliation is what catches the invented 0.30.
    """
    s = copy.deepcopy(BASE)
    s["stats"][0]["p"] = 0.30
    s["stats"][0]["interpretation"] = "给药组均值为31.23，与对照组12.37相比差异无统计学意义（不显著）"
    return "run", (copy.deepcopy(s["rows"]), s), ["stats.p_mismatch"]


def scen_p_mismatch_fp():
    """FP guard: p=0.30 with overlapping groups — computed Welch p agrees, all quiet."""
    s = copy.deepcopy(BASE)
    s["rows"] = [
        {"group": "control", "response": "12.4"},
        {"group": "control", "response": "11.8"},
        {"group": "control", "response": "12.9"},
        {"group": "drug", "response": "13.0"},
        {"group": "drug", "response": "12.2"},
        {"group": "drug", "response": "13.5"},
    ]
    s["stats"][0]["p"] = 0.30
    s["stats"][0]["interpretation"] = "给药组均值为12.9，与对照组12.37相比差异无统计学意义（不显著）"
    return "run", (copy.deepcopy(s["rows"]), s), []


def scen_significance_underclaim():
    s = copy.deepcopy(BASE)
    s["stats"][0]["interpretation"] = "给药组均值31.23与对照组12.37差异无统计学意义"
    return "run", (copy.deepcopy(s["rows"]), s), ["stats.significance_mismatch"]


def scen_number_not_in_table():
    s = copy.deepcopy(BASE)
    s["stats"][0]["interpretation"] = "给药组均值为99.9，远高于对照组"
    return "run", (copy.deepcopy(s["rows"]), s), ["stats.number_not_in_table"]


def scen_value_field_mismatch():
    s = copy.deepcopy(BASE)
    s["stats"][0]["value"] = 25.0
    return "run", (copy.deepcopy(s["rows"]), s), ["stats.number_not_in_table"]


def scen_metric_unknown():
    s = copy.deepcopy(BASE)
    s["stats"][0]["metric"] = "blood_pressure"
    return "run", (copy.deepcopy(s["rows"]), s), ["stats.metric_unknown"]


def scen_group_unknown():
    s = copy.deepcopy(BASE)
    s["stats"][0]["group_b"] = "rescue"
    return "run", (copy.deepcopy(s["rows"]), s), ["stats.group_unknown"]


def scen_claim_malformed():
    s = copy.deepcopy(BASE)
    s["stats"] = [{"metric": "response", "test": "t-test", "p": 0.01}]
    return "run", (copy.deepcopy(s["rows"]), s), ["stats.claim_malformed"]


def scen_missing_named():
    """A not-reported cell is a named missing value, never a coerced zero."""
    s = copy.deepcopy(BASE)
    s["rows"][0]["response"] = "not reported"
    s["stats"] = []
    return "run", (copy.deepcopy(s["rows"]), s), ["clean.missing_values"]


def scen_duplicate_experiments():
    """Same entity with different values: two measurements, reported not merged."""
    s = copy.deepcopy(BASE)
    s["stats"] = []
    s["key_columns"] = ["group"]
    s["value_columns"] = ["response"]
    return "run", (copy.deepcopy(s["rows"]), s), ["clean.duplicate_experiments"]


def scen_rounded_citation_fp():
    """FP guard: a citation rounded to one decimal still matches the computed mean."""
    s = copy.deepcopy(BASE)
    s["stats"][0]["interpretation"] = "给药组均值为31.2，高于对照组"
    return "run", (copy.deepcopy(s["rows"]), s), []


def scen_sample_too_small():
    """A group with one usable value has no variance and cannot carry a test."""
    s = copy.deepcopy(BASE)
    s["rows"] = [
        {"group": "control", "response": "12.4"},
        {"group": "control", "response": "11.8"},
        {"group": "control", "response": "12.9"},
        {"group": "drug", "response": "31.2"},
    ]
    return "run", (copy.deepcopy(s["rows"]), s), ["stats.sample_too_small"]


def scen_zero_variance():
    """A group with zero variance makes the t statistic undefined."""
    s = copy.deepcopy(BASE)
    s["rows"] = [
        {"group": "control", "response": "12.4"},
        {"group": "control", "response": "11.8"},
        {"group": "control", "response": "12.9"},
        {"group": "drug", "response": "31.2"},
        {"group": "drug", "response": "31.2"},
        {"group": "drug", "response": "31.2"},
    ]
    return "run", (copy.deepcopy(s["rows"]), s), ["stats.zero_variance"]


def scen_missing_ratio_high():
    """A group that is mostly gaps cannot carry the comparison."""
    s = copy.deepcopy(BASE)
    s["rows"] = [
        {"group": "control", "response": "12.4"},
        {"group": "control", "response": "11.8"},
        {"group": "control", "response": "12.9"},
        {"group": "drug", "response": "not reported"},
        {"group": "drug", "response": "ND"},
        {"group": "drug", "response": "31.9"},
    ]
    return "run", (copy.deepcopy(s["rows"]), s), ["stats.missing_ratio_high"]


def scen_groups_omitted():
    """Three groups in the data, two compared: the exclusion must be declared."""
    s = copy.deepcopy(BASE)
    s["rows"] = copy.deepcopy(BASE["rows"]) + [
        {"group": "rescue", "response": "20.1"},
        {"group": "rescue", "response": "20.9"},
        {"group": "rescue", "response": "19.8"},
    ]
    return "run", (copy.deepcopy(s["rows"]), s), ["stats.groups_omitted"]


def scen_groups_omitted_declared_fp():
    """FP guard: the same three-group table with excluded_groups declared is quiet."""
    s = copy.deepcopy(BASE)
    s["rows"] = copy.deepcopy(BASE["rows"]) + [
        {"group": "rescue", "response": "20.1"},
        {"group": "rescue", "response": "20.9"},
        {"group": "rescue", "response": "19.8"},
    ]
    s["stats"][0]["excluded_groups"] = ["rescue"]
    return "run", (copy.deepcopy(s["rows"]), s), []


def scen_multiple_comparison():
    """Three pairwise claims with no declared correction inflate false positives."""
    s = copy.deepcopy(BASE)
    s["rows"] = copy.deepcopy(BASE["rows"]) + [
        {"group": "rescue", "response": "20.1"},
        {"group": "rescue", "response": "20.9"},
        {"group": "rescue", "response": "19.8"},
    ]
    s["stats"] = [
        {"metric": "response", "group_col": "group", "group_a": "control",
         "group_b": "drug", "p": 0.01,
         "interpretation": "给药组均值为31.23，高于对照组的12.37", "excluded_groups": []},
        {"metric": "response", "group_col": "group", "group_a": "control",
         "group_b": "rescue", "p": 0.04,
         "interpretation": "rescue组均值为20.27，高于对照组的12.37"},
        {"metric": "response", "group_col": "group", "group_a": "drug",
         "group_b": "rescue", "p": 0.04,
         "interpretation": "rescue组均值为20.27，低于给药组的31.23"},
    ]
    return "run", (copy.deepcopy(s["rows"]), s), ["stats.multiple_comparison"]


def scen_multiple_comparison_declared_fp():
    """FP guard: the same claims with a declared correction stay quiet on this rule."""
    s = copy.deepcopy(BASE)
    s["rows"] = copy.deepcopy(BASE["rows"]) + [
        {"group": "rescue", "response": "20.1"},
        {"group": "rescue", "response": "20.9"},
        {"group": "rescue", "response": "19.8"},
    ]
    corr = "bonferroni"
    s["stats"] = [
        {"metric": "response", "group_col": "group", "group_a": "control",
         "group_b": "drug", "p": 0.01, "correction": corr,
         "interpretation": "给药组均值为31.23，高于对照组的12.37"},
        {"metric": "response", "group_col": "group", "group_a": "control",
         "group_b": "rescue", "p": 0.04, "correction": corr,
         "interpretation": "rescue组均值为20.27，高于对照组的12.37"},
        {"metric": "response", "group_col": "group", "group_a": "drug",
         "group_b": "rescue", "p": 0.04, "correction": corr,
         "interpretation": "rescue组均值为20.27，低于给药组的31.23"},
    ]
    return "run", (copy.deepcopy(s["rows"]), s), []


def scen_outliers_iqr():
    """A Tukey-fence outlier is listed with its row, never deleted."""
    s = copy.deepcopy(BASE)
    s["rows"] = [
        {"group": "control", "response": "1.0"}, {"group": "control", "response": "1.1"},
        {"group": "control", "response": "1.2"}, {"group": "control", "response": "1.3"},
        {"group": "control", "response": "0.9"}, {"group": "control", "response": "1.1"},
        {"group": "control", "response": "1.2"}, {"group": "control", "response": "1.0"},
        {"group": "drug", "response": "1.4"}, {"group": "drug", "response": "1.2"},
        {"group": "drug", "response": "9.0"}, {"group": "drug", "response": "1.3"},
    ]
    s["stats"] = []
    return "run", (copy.deepcopy(s["rows"]), s), ["stats.outliers_iqr"]


def scen_assumption_normality():
    """Strong skew in a small sample: advisory before any parametric reading."""
    s = copy.deepcopy(BASE)
    s["rows"] = [
        {"group": "control", "response": "1.0"}, {"group": "control", "response": "1.1"},
        {"group": "control", "response": "1.2"}, {"group": "control", "response": "1.3"},
        {"group": "control", "response": "9.0"},
        {"group": "drug", "response": "2.0"}, {"group": "drug", "response": "2.1"},
        {"group": "drug", "response": "2.2"}, {"group": "drug", "response": "2.3"},
        {"group": "drug", "response": "2.4"},
    ]
    s["stats"] = []
    return "run", (copy.deepcopy(s["rows"]), s), ["stats.outliers_iqr",
                                                  "stats.assumption_normality"]


def scen_descriptives_layer():
    """FP guard: the deliverable layer — descriptives, effect size, CI, charts,
    manifest — is present and matches hand-checked values."""
    return "run", (copy.deepcopy(BASE["rows"]), copy.deepcopy(BASE)), [], \
        {"asserts": {"descriptives": True, "effect_size": True, "ci": True,
                     "charts": True, "manifest": True, "anova_none": True}}


def scen_math_anchors():
    """Distribution math against table anchors (t=2.2281 df=10 -> 0.05 etc.)."""
    return "math", None, [], {"anchors": True}


def scen_cli_unreadable_spec():
    """A spec that is not JSON is refused with exit-5 semantics, never a crash."""
    return "cli", "{ this is not json", ["clean.spec_unreadable"], {"status": "undetermined"}


def scen_cli_no_rows():
    """A spec with neither rows nor a readable table_path is refused."""
    return "cli", {"columns": [{"name": "group"}]}, ["clean.spec_unreadable"], \
        {"status": "undetermined"}


def scen_cli_missing_spec():
    """A spec file that does not exist is refused, not a FileNotFoundError."""
    return "cli", {"__missing__": True}, ["clean.spec_unreadable"], {"status": "undetermined"}


def scen_cli_rows_not_list():
    """spec.rows that is a string is refused, not silently emptied."""
    return "cli", {"payload": {"rows": "hello", "columns": [{"name": "response"}]}}, \
        ["clean.spec_unreadable"], {"status": "undetermined"}


def scen_cli_case_contract():
    """FP guard: --case supplies case_id and the output_contract echo; the run stays clean."""
    return "cli", {"payload": {"columns": [{"name": "group", "semantic": "categorical"},
                                           {"name": "response", "semantic": "numeric"}],
                               "rows": copy.deepcopy(BASE["rows"]),
                               "stats": [copy.deepcopy(BASE_CLAIM)],
                               "summary": "contract echo demo"},
                   "case": {"case_id": "case-stats-001",
                            "output_contract": {"case_id": "echo", "status": "audit",
                                                "summary": "pass-through",
                                                "stats_audit": "computed",
                                                "descriptives": "computed",
                                                "plots": "not derivable"}},
                   "asserts": {"case_id": "case-stats-001",
                               "summary": "contract echo demo",
                               "plots_is_none": True}}, \
        [], {"status": "clean"}


SCENARIOS = [
    ("clean", scen_clean),
    ("direction_mismatch", scen_direction_mismatch),
    ("direction_field", scen_direction_field),
    ("significance_overclaim", scen_significance_overclaim),
    ("p_mismatch_claimed", scen_p_mismatch_claimed),
    ("p_mismatch_fp", scen_p_mismatch_fp),
    ("significance_underclaim", scen_significance_underclaim),
    ("number_not_in_table", scen_number_not_in_table),
    ("value_field_mismatch", scen_value_field_mismatch),
    ("metric_unknown", scen_metric_unknown),
    ("group_unknown", scen_group_unknown),
    ("claim_malformed", scen_claim_malformed),
    ("missing_named", scen_missing_named),
    ("duplicate_experiments", scen_duplicate_experiments),
    ("rounded_citation_fp", scen_rounded_citation_fp),
    ("sample_too_small", scen_sample_too_small),
    ("zero_variance", scen_zero_variance),
    ("missing_ratio_high", scen_missing_ratio_high),
    ("groups_omitted", scen_groups_omitted),
    ("groups_omitted_declared_fp", scen_groups_omitted_declared_fp),
    ("multiple_comparison", scen_multiple_comparison),
    ("multiple_comparison_declared_fp", scen_multiple_comparison_declared_fp),
    ("outliers_iqr", scen_outliers_iqr),
    ("assumption_normality", scen_assumption_normality),
    ("descriptives_layer", scen_descriptives_layer),
    ("math_anchors", scen_math_anchors),
    ("cli_unreadable_spec", scen_cli_unreadable_spec),
    ("cli_no_rows", scen_cli_no_rows),
    ("cli_missing_spec", scen_cli_missing_spec),
    ("cli_rows_not_list", scen_cli_rows_not_list),
    ("cli_case_contract", scen_cli_case_contract),
]


def run_one(name, builder, root: Path) -> dict:
    built = builder()
    kind, payload, expect = built[0], built[1], built[2]
    extra = built[3] if len(built) > 3 else {}
    out = root / name
    out.mkdir(parents=True, exist_ok=True)
    note = ""
    missing = []
    r: dict = {"findings": []}
    if kind == "math":
        anchors = [
            ("t_2.2281_df10", S.t_two_sided_p(2.2281388519677088, 10), 0.05, 1e-6),
            ("t_12.706_df1", S.t_two_sided_p(12.706204736432095, 1), 0.05, 1e-6),
            ("t_4.3027_df2", S.t_two_sided_p(4.302652829728485, 2), 0.05, 1e-5),
            ("t_1.0_df30", S.t_two_sided_p(1.0, 30), 0.325308615, 1e-6),
            ("F_3.7083_3_10", S.f_sf(3.7083, 3, 10), 0.05, 2e-6),
            ("F_4.8259_3_10", S.f_sf(4.8259, 3, 10), 0.025, 2e-5),
            ("tq_0.05_df10", S.t_two_sided_critical(0.05, 10), 2.228138852, 1e-3),
            ("tq_0.01_df2", S.t_two_sided_critical(0.01, 2), 9.924842500, 2e-3),
        ]
        for aname, got, want, tol in anchors:
            if got is None or abs(got - want) > tol:
                missing.append(f"{aname}:{got}")
        fired: set = set()
        status = "clean"
    elif kind == "cli":
        sp = out / "spec.json"
        if isinstance(payload, dict) and payload.get("__missing__"):
            r = CL.build_and_audit(sp.parent / "__nope__.json", out / "res")
        elif isinstance(payload, str):
            sp.write_text(payload, encoding="utf-8")
            r = CL.build_and_audit(sp, out / "res")
        elif "payload" in payload or "case" in payload:
            case = None
            body = payload["payload"]
            if payload.get("case"):
                case = out / "case.json"
                case.write_text(json.dumps(payload["case"], ensure_ascii=False, indent=2),
                                encoding="utf-8")
            sp.write_text(json.dumps(body, ensure_ascii=False, indent=2), encoding="utf-8")
            r = CL.build_and_audit(sp, out / "res", case)
        else:
            sp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
            r = CL.build_and_audit(sp, out / "res")
        fired = {f["rule"] for f in r["findings"]}
        status = r["status"]
        want_status = extra.pop("status", None)
        if want_status and status != want_status:
            missing.append("status:" + status)
    else:
        rows, spec = payload
        r = CL.run(rows, spec)
        fired = {f["rule"] for f in r["findings"]}
        status = r["status"]
    missing.extend(x for x in expect if x not in fired)
    spurious = []
    if not expect:
        spurious = [f["rule"] for f in (r.get("findings") or [])
                    if f["severity"] in ("high", "medium")]
    asserts = extra.get("asserts") or ({} if kind == "cli" else {})
    if name == "clean":
        rec = r["stats_audit"]["claims"][0]
        if abs(rec["diff"] - 18.8667) > 0.001 or rec["n_a"] != 3 or rec["n_b"] != 3:
            missing.append("computed_means")
        note += f" diff={rec['diff']} means=({rec['mean_a']},{rec['mean_b']})"
    if name == "p_mismatch_claimed":
        rec = r["stats_audit"]["claims"][0]
        if rec.get("p_computed") is None or rec["p_computed"] > 0.05:
            missing.append("p_computed_not_tiny")
        note += f" p_computed={rec.get('p_computed')}"
    if name == "p_mismatch_fp":
        rec = r["stats_audit"]["claims"][0]
        if rec.get("p_computed") is None or rec["p_computed"] < 0.05:
            missing.append("p_computed_not_large")
        note += f" p_computed={rec.get('p_computed')}"
    if name == "zero_variance":
        rec = r["stats_audit"]["claims"][0]
        if rec.get("t_stat") is not None:
            missing.append("t_should_be_absent")
    if name == "groups_omitted":
        rec = r["stats_audit"]["claims"][0]
        if rec.get("anova") is None or rec["anova"].get("k_groups") != 3:
            missing.append("anova_record")
        note += f" anova={rec.get('anova')}"
    if asserts.get("descriptives"):
        rec = r["descriptives"][1] if len(r["descriptives"]) > 1 else {}
        if rec.get("n") != 6 or rec.get("median") != 21.75 or rec.get("mean") != 21.8 \
                or rec.get("n_missing") != 0 or rec.get("units_seen") != []:
            missing.append("descriptives:" + json.dumps(rec, ensure_ascii=False)[:120])
        rec2 = r["stats_audit"]["claims"][0]
        if rec2.get("cohen_d") is None or rec2.get("hedges_g") is None \
                or rec2.get("t_stat") is None or rec2.get("p_computed") is None:
            missing.append("effect_size_missing")
        if rec2.get("ci95_low") is None or rec2.get("ci95_high") is None \
                or not (rec2["ci95_low"] < rec2["diff"] < rec2["ci95_high"]):
            missing.append("ci_missing")
        if r.get("anova_record"):
            missing.append("anova_should_be_absent")
        note += (f" d={rec2.get('cohen_d')} g={rec2.get('hedges_g')} "
                 f"t={rec2.get('t_stat')} ci=({rec2.get('ci95_low')},{rec2.get('ci95_high')})")
    if asserts.get("charts") and not r.get("charts"):
        missing.append("charts_missing")
    if asserts.get("manifest") and not (r.get("run_manifest") or {}).get("rows_sha256_16"):
        missing.append("manifest_missing")
    if asserts.get("anova_none") is True:
        rec2 = r["stats_audit"]["claims"][0]
        if rec2.get("anova") is not None:
            missing.append("anova_should_be_absent")
    if asserts.get("case_id") and r.get("case_id") != asserts["case_id"]:
        missing.append("case_id:" + str(r.get("case_id")))
    if asserts.get("summary") and r.get("summary") != asserts["summary"]:
        missing.append("summary:" + str(r.get("summary")))
    if asserts.get("plots_is_none") and r.get("plots") is not None:
        missing.append("plots_not_none")
    return {"scenario": name, "expected": expect, "fired": sorted(fired),
            "missing": missing, "spurious": spurious, "status": status,
            "pass": not missing and not spurious, "extra": note.strip()}


def main() -> int:
    root = Path(__file__).resolve().parent / "_run"
    if root.exists():
        import shutil
        shutil.rmtree(root)  # fresh scratch: the already_cleaned guard must not trip
    rows = [run_one(n, b, root) for n, b in SCENARIOS]
    passed = sum(1 for r in rows if r["pass"])
    report = {
        "schema_version": "stats-bench/v2",
        "scenarios": rows,
        "totals": {"passed": passed, "of": len(rows)},
        "note": ("Each scenario plants one defect or proves one FP guard. The clean "
                 "baseline must report no high or medium finding, the computed claim "
                 "record is asserted against hand-checked group means, and the "
                 "distribution math is asserted against table anchors."),
    }
    (Path(__file__).resolve().parent.parent / "report_stats.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    for r in rows:
        print(("PASS" if r["pass"] else "FAIL") + f"  {r['scenario']:<34}"
              f" missing={r['missing']} spurious={r['spurious']}"
              + ((" |" + r["extra"]) if r["extra"] else ""))
    print(f"\n{passed}/{len(rows)} scenarios pass")
    return 0 if passed == len(rows) else 1


if __name__ == "__main__":
    raise SystemExit(main())
