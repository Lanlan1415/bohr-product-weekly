"""Independent regression anchors for the direct statistical-analysis layer.

No third-party package is required. Exact small-sample rank p values, hand-
computed paired-t and multiplicity-adjusted p values are asserted explicitly.
"""
from __future__ import annotations

import copy
import json
import math
import shutil
import sqlite3
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import cleandata as CL  # noqa: E402
import statscore as SC  # noqa: E402

OUT = Path(__file__).resolve().parent / "_run_statscore"


def cols(*names):
    result = [{"name": "group", "semantic": "categorical"},
              {"name": "response", "semantic": "numeric"}]
    if "pair" in names:
        result.append({"name": "pair", "semantic": "id"})
    return result


def close(got, want, tol=1e-8):
    return got is not None and abs(got - want) <= tol


def test_mann_whitney_exact():
    rec = SC.mann_whitney([1, 2], [3, 4])
    problems = [] if close(rec["U"], 4) and close(rec["p"], 1 / 3) and close(rec["rank_biserial"], 1) else [rec]
    # Independent enumeration of all six assignments is the hand check:
    # U=4 only for the observed split; U=0 for its reverse split => 2/6.
    return problems


def test_multiplicity_anchors():
    p = [0.01, 0.04, 0.03]
    expected = {"bonferroni": [0.03, 0.12, 0.09],
                "holm": [0.03, 0.06, 0.06],
                "fdr_bh": [0.03, 0.04, 0.04]}
    problems = []
    for method, want in expected.items():
        got = [r["p_adjusted"] for r in SC.adjust_pvalues(p, method)]
        if any(abs(a - b) > 1e-12 for a, b in zip(got, want)):
            problems.append({"method": method, "got": got, "want": want})
    if [r["reject"] for r in SC.adjust_pvalues(p, "holm")] != [True, False, False]:
        problems.append("Holm reject decisions differ from adjusted p<=alpha")
    return problems


def test_paired_t_hand_anchor():
    rows = []
    for pair, (before, after) in enumerate(((1, 2), (2, 4), (3, 6)), 1):
        rows.extend([{"pair": pair, "group": "before", "response": before},
                     {"pair": pair, "group": "after", "response": after}])
    spec = {"rows": rows, "columns": cols("pair"),
            "analyses": [{"metric": "response", "group_col": "group", "design": "paired",
                          "pair_id": "pair", "group_a": "before", "group_b": "after",
                          "test": "paired_t"}]}
    result = CL.run(rows, spec)
    rec = result["analysis_results"][0]
    # Hand: differences=[1,2,3], mean=2, sd=1, se=1/sqrt(3),
    # t=2*sqrt(3)=3.464101615, df=2. Exact p is the two-sided Student tail.
    problems = []
    if not close(rec["mean_difference"], 2) or not close(rec["t"], 2 * math.sqrt(3), 1e-10):
        problems.append("paired hand t/difference mismatch")
    if not close(rec["p"], 0.0741799002274486, 1e-10) or rec["df"] != 2:
        problems.append("paired p/df mismatch: " + str(rec.get("p")))
    if not (rec["ci95"]["low"] < 2 < rec["ci95"]["high"] and close(rec["cohen_dz"], 2)):
        problems.append("paired CI/effect missing")
    if rec["power_and_sample_size"]["post_hoc_power_computed"] is not False:
        problems.append("post-hoc power should not be fabricated")
    return problems


def test_wilcoxon_exact():
    rows = []
    for pair, difference in enumerate((1, 2, 3), 1):
        rows.extend([{"pair": pair, "group": "before", "response": 0},
                     {"pair": pair, "group": "after", "response": difference}])
    spec = {"rows": rows, "columns": cols("pair"),
            "analyses": [{"metric": "response", "group_col": "group", "design": "paired",
                          "pair_id": "pair", "group_a": "before", "group_b": "after",
                          "test": "wilcoxon"}]}
    rec = CL.run(rows, spec)["analysis_results"][0]
    # Three positive non-tied ranks: 2^3=8 sign assignments, two extremes => .25.
    return [] if close(rec["W_plus"], 6) and close(rec["p"], 0.25) and close(rec["matched_rank_biserial"], 1) else [rec]


def test_kruskal_hand_anchor():
    groups = {"a": [1, 2, 3], "b": [4, 5, 6], "c": [7, 8, 9]}
    rec = SC._kruskal(groups)
    # Hand: rank sums 6,15,24 -> H=7.2; chi-square df=2 tail = exp(-H/2).
    problems = []
    if not close(rec["H"], 7.2) or not close(rec["p"], math.exp(-3.6), 1e-12):
        problems.append(rec)
    if not close(SC.chi_square_sf(7.2, 2), math.exp(-3.6), 1e-12):
        problems.append("chi-square df=2 anchor failed")
    return problems


def test_anova_and_posthoc():
    rows = [{"group": g, "response": x} for g, vals in
            (("a", [1, 2, 3]), ("b", [4, 5, 6]), ("c", [7, 8, 9])) for x in vals]
    spec = {"rows": rows, "columns": cols(),
            "analyses": [{"metric": "response", "group_col": "group", "test": "anova",
                          "correction": "holm"}]}
    rec = CL.run(rows, spec)["analysis_results"][0]
    # Hand: SSB=54, SSW=6 -> F=(54/2)/(6/6)=27; df=(2,6).
    problems = []
    if rec.get("status") != "computed" or "单因素 ANOVA" not in rec.get("result_text", ""):
        problems.append("ANOVA status/result text was not marked computed")
    if not close(rec["F"], 27) or (rec["df1"], rec["df2"]) != (2, 6):
        problems.append("ANOVA hand F mismatch")
    if len(rec.get("pairwise_comparisons", [])) != 3:
        problems.append("three pairwise post-hoc comparisons missing")
    if any(p.get("p_adjusted") is None or p.get("reject") is None for p in rec["pairwise_comparisons"]):
        problems.append("post-hoc adjusted p/reject missing")
    return problems


def test_cleaned_units_drive_statistics():
    rows = [{"group": "a", "response": f"{x} mg/L"} for x in (1, 2, 3)]
    rows += [{"group": "b", "response": f"{x} ug/L"} for x in (4000, 5000, 6000)]
    spec = {"rows": rows,
            "columns": [{"name": "group", "semantic": "categorical"},
                        {"name": "response", "semantic": "numeric", "target_unit": "mg/L"}],
            "analyses": [{"metric": "response", "group_col": "group", "test": "welch"}]}
    rec = CL.run(rows, spec)["analysis_results"][0]
    # 4000/5000/6000 ug/L are 4/5/6 mg/L. Using raw cells would be a factor-1000 bug.
    return [] if close(rec["mean_difference"], 3) and close(rec["descriptives_by_group"]["b"]["mean"], 5) else [rec]


def test_correlation_and_causation():
    rows = [{"x": x, "y": y} for x, y in ((1, 1), (2, 2), (3, 4), (4, 8))]
    spec = {"rows": rows, "columns": [{"name": "x", "semantic": "numeric"},
                                      {"name": "y", "semantic": "numeric"}],
            "correlations": [{"x": "x", "y": "y", "method": "pearson"},
                             {"x": "x", "y": "y", "method": "spearman"}]}
    result = CL.run(rows, spec)
    pearson, spearman = result["correlations"]
    n = 4
    mx, my = sum(r["x"] for r in rows) / n, sum(r["y"] for r in rows) / n
    numerator = sum((r["x"] - mx) * (r["y"] - my) for r in rows)
    independent_r = numerator / math.sqrt(sum((r["x"] - mx) ** 2 for r in rows)
                                           * sum((r["y"] - my) ** 2 for r in rows))
    problems = []
    if not close(pearson["r"], independent_r, 1e-12):
        problems.append("independent Pearson formula mismatch")
    if not close(spearman["r"], 1.0):
        problems.append("monotonic Spearman must equal one")
    if pearson["causation_established"] is not False or "相关不等于因果" not in pearson["result_text"]:
        problems.append("correlation/causation boundary missing")
    return problems


def test_diagnostics():
    values = list(range(1, 9))
    jb = SC.jarque_bera(values)
    bf = SC.brown_forsythe({"a": [1, 2, 3], "b": [1, 10, 100]})
    problems = []
    if jb.get("df") != 2 or not close(jb["p"], math.exp(-jb["statistic"] / 2), 1e-12):
        problems.append("JB df2 identity failed")
    if bf.get("status") != "computed" or bf.get("df1") != 1 or bf.get("df2") != 4:
        problems.append("Brown-Forsythe diagnostic failed")
    return problems


def test_auto_and_degenerate():
    request = {"metric": "response", "group_col": "group", "test": "auto"}
    rows = [{"group": "a", "response": 1}, {"group": "a", "response": 2},
            {"group": "b", "response": 3}, {"group": "b", "response": 4}]
    rec = CL.run(rows, {"rows": rows, "columns": cols(), "analyses": [request]})["analysis_results"][0]
    problems = [] if rec["test"] == "mann_whitney" else ["small-sample auto did not choose exact rank test"]
    rows2 = [{"group": "a", "response": 1}, {"group": "a", "response": 1},
             {"group": "b", "response": 2}, {"group": "b", "response": 2}]
    rec2 = CL.run(rows2, {"rows": rows2, "columns": cols(),
                          "analyses": [{"metric": "response", "group_col": "group", "test": "welch"}]})["analysis_results"][0]
    if rec2["status"] != "undetermined" or rec2.get("p") is not None:
        problems.append("zero-variance groups produced a statistic")
    return problems


def test_duplicate_design_guard():
    rows = [{"subject": "s1", "group": "a", "response": 1},
            {"subject": "s1", "group": "a", "response": 1},
            {"subject": "s2", "group": "a", "response": 2},
            {"subject": "s3", "group": "b", "response": 4},
            {"subject": "s4", "group": "b", "response": 5}]
    dictionary = cols() + [{"name": "subject", "semantic": "id"}]
    request = {"metric": "response", "group_col": "group", "test": "welch"}
    base = {"rows": rows, "columns": dictionary, "key_columns": ["subject"], "analyses": [request]}
    blocked = CL.run(rows, base)
    problems = []
    if blocked["analysis_results"][0]["status"] != "undetermined" or blocked["analysis_results"][0].get("p") is not None:
        problems.append("default review let duplicate copies inflate inferential n")
    dropped = copy.deepcopy(base); dropped["duplicate_policy"] = "drop_exact_copies"
    resolved = CL.run(rows, dropped)
    if resolved["analysis_results"][0].get("mean_difference") != 3 \
            or resolved["analysis_population"]["duplicate_rows_removed"] != 1 \
            or len(resolved["analysis_table"]) != 4:
        problems.append("explicit exact-copy policy did not produce a logged four-row analysis table")
    conflict = copy.deepcopy(rows); conflict[1]["response"] = 9
    conflict_spec = copy.deepcopy(dropped); conflict_spec["rows"] = conflict
    unresolved = CL.run(conflict, conflict_spec)
    if unresolved["analysis_results"][0]["status"] != "undetermined":
        problems.append("dropping exact copies hid a same-key value conflict")
    conflict_spec["duplicate_policy"] = "keep_as_independent"
    conflict_spec["duplicate_justification"] = "pre-registered independent replicate assays"
    kept = CL.run(conflict, conflict_spec)
    if kept["analysis_results"][0]["status"] != "computed" or not kept["analysis_population"]["duplicate_justification"]:
        problems.append("justified replicate policy was not respected and logged")
    return problems


def test_dictionary_inference_and_determinism():
    rows = [{"group": "a", "response": 1}, {"group": "a", "response": 2},
            {"group": "b", "response": 4}, {"group": "b", "response": 5}]
    spec = {"rows": rows, "analyses": [{"metric": "response", "group_col": "group", "test": "welch"}]}
    a, b = CL.run(rows, spec), CL.run(rows, spec)
    problems = []
    if a != b:
        problems.append("same in-memory run was not deterministic")
    if (a.get("data_dictionary") or {}).get("source", "").startswith("case-declared"):
        problems.append("missing dictionary was not honestly marked inferred")
    if not any(c["name"] == "response" and c["semantic"] == "numeric"
               for c in a["data_dictionary"]["columns"]):
        problems.append("numeric column inference failed")
    return problems


def test_sqlite_and_read_only_refusal():
    dbdir = OUT / "sqlite"
    dbdir.mkdir(parents=True, exist_ok=True)
    db = dbdir / "research.db"
    con = sqlite3.connect(db)
    con.execute("CREATE TABLE observations (id INTEGER, grp TEXT, response REAL)")
    con.executemany("INSERT INTO observations VALUES (?,?,?)",
                    [(1, "a", 1), (2, "a", 2), (3, "b", 4), (4, "b", 5)])
    con.commit(); con.close()
    spec = {"case_id": "sqlite-demo", "sqlite_path": str(db), "table_name": "observations",
            "query": "SELECT grp AS \"group\", response FROM observations ORDER BY id",
            "columns": cols(),
            "analyses": [{"metric": "response", "group_col": "group", "test": "welch"}],
            "output_contract": {"case_id": "id", "analysis_results": "computed", "result_text": "text"}}
    sp = dbdir / "spec.json"
    sp.write_text(json.dumps(spec), encoding="utf-8")
    result = CL.build_and_audit(sp, dbdir / "out")
    problems = []
    if not (result.get("input_metadata") or {}).get("read_only"):
        problems.append("SQLite read-only provenance missing")
    if result.get("analysis_results", [{}])[0].get("mean_difference") != 3:
        problems.append("SQLite-backed analysis incorrect")
    if len(result.get("result_text", [])) != 1 or "均值差" not in result["result_text"][0]:
        problems.append("result_text contract shape inconsistent")
    bad = dict(spec); bad["query"] = "DELETE FROM observations"; bad["case_id"] = "bad-sql"
    sp2 = dbdir / "bad.json"; sp2.write_text(json.dumps(bad), encoding="utf-8")
    refused = CL.build_and_audit(sp2, dbdir / "badout")
    if refused.get("status") != "undetermined" or refused.get("analysis_results") is not None:
        problems.append("non-SELECT was not refused with null derived contract")
    con = sqlite3.connect(db)
    count = con.execute("SELECT COUNT(*) FROM observations").fetchone()[0]; con.close()
    if count != 4:
        problems.append("database changed despite read-only promise")
    return problems


def test_broken_spec_contract():
    case = {"case_id": "case-broken", "note": "pass",
            "output_contract": {"case_id": "id", "analysis_results": "list", "note": "text"}}
    OUT.mkdir(parents=True, exist_ok=True)
    cp = OUT / "broken_case.json"; cp.write_text(json.dumps(case), encoding="utf-8")
    sp = OUT / "broken.json"; sp.write_text("{not json", encoding="utf-8")
    result = CL.build_and_audit(sp, OUT / "broken_out", cp)
    if result.get("case_id") != "case-broken" or result.get("note") != "pass":
        return ["case metadata lost"]
    if "analysis_results" not in result or result["analysis_results"] is not None:
        return ["derived field on refusal must be present and null"]
    return []


SCENARIOS = [
    ("mann_whitney_exact", test_mann_whitney_exact),
    ("multiplicity_anchors", test_multiplicity_anchors),
    ("paired_t_hand_anchor", test_paired_t_hand_anchor),
    ("wilcoxon_exact", test_wilcoxon_exact),
    ("kruskal_hand_anchor", test_kruskal_hand_anchor),
    ("anova_and_posthoc", test_anova_and_posthoc),
    ("cleaned_units_drive_statistics", test_cleaned_units_drive_statistics),
    ("correlation_and_causation", test_correlation_and_causation),
    ("diagnostics", test_diagnostics),
    ("auto_and_degenerate", test_auto_and_degenerate),
    ("duplicate_design_guard", test_duplicate_design_guard),
    ("dictionary_inference_and_determinism", test_dictionary_inference_and_determinism),
    ("sqlite_and_read_only_refusal", test_sqlite_and_read_only_refusal),
    ("broken_spec_contract", test_broken_spec_contract),
]


def main():
    shutil.rmtree(OUT, ignore_errors=True)
    rows = []
    for name, fn in SCENARIOS:
        try:
            problems = fn()
        except Exception as exc:
            problems = [f"raised: {exc!r}"]
        rows.append({"scenario": name, "problems": problems, "pass": not problems})
        print(f"{'PASS' if not problems else 'FAIL'}  {name:<38} {problems}")
    report = {"schema_version": "statscore-bench/v1", "scenarios": rows,
              "totals": {"passed": sum(r["pass"] for r in rows), "of": len(rows)},
              "cross_checks": {"paired_t": "differences [1,2,3] -> t=2*sqrt(3), df=2",
                               "mann_whitney": "U=4 for [1,2] vs [3,4] -> exact p=2/6",
                               "kruskal": "H=7.2, df=2 -> p=exp(-3.6)",
                               "holm": "[.01,.04,.03] -> [.03,.06,.06]"}}
    (Path(__file__).resolve().parent.parent / "report_statscore.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n{report['totals']['passed']}/{len(rows)} scenarios pass (direct-analysis)")
    return 0 if all(r["pass"] for r in rows) else 1


if __name__ == "__main__":
    raise SystemExit(main())
