"""Functional regression bench for scicode.  All inputs are synthetic and local."""
from __future__ import annotations

import argparse
import copy
import csv
import json
import sqlite3
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
CLI = HERE / "scicode.py"
BASE_ROWS = [
    {"sample": "S1", "group": "A", "x": "1", "y": "2"},
    {"sample": "S2", "group": "A", "x": "2", "y": "4"},
    {"sample": "S3", "group": "A", "x": "3", "y": "6"},
    {"sample": "S4", "group": "B", "x": "1", "y": "3"},
    {"sample": "S5", "group": "B", "x": "2", "y": "5"},
    {"sample": "S6", "group": "B", "x": "3", "y": "9"},
]
BASE_SPEC = {
    "case_id": "bench-scicode",
    "section": "scicode",
    "input": {"path": "data.csv", "format": "csv"},
    "columns": [
        {"name": "sample", "type": "id"},
        {"name": "group", "type": "categorical"},
        {"name": "x", "type": "numeric"},
        {"name": "y", "type": "numeric"},
    ],
    "metrics": ["x", "y"],
    "parameters": {"seed": 7, "float_precision": 10},
    "validation": {"expected_rows": 6,
                   "golden": [{"path": "statistics.x.mean", "value": 2.0,
                               "atol": 1e-9, "rtol": 1e-9}]},
}
CONTRACT = ["status", "code", "analysis_result", "execution_result", "validation",
            "environment", "case_payload", "not_derivable"]


def write_csv(path, rows, delimiter=","):
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]), delimiter=delimiter,
                                lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def scenario(name, spec=None, rows=None, status="clean", rules=(), mode="execute",
             files=None, case_mutator=None, check=None):
    return {"name": name, "spec": spec or copy.deepcopy(BASE_SPEC),
            "rows": copy.deepcopy(BASE_ROWS if rows is None else rows),
            "status": status, "rules": set(rules), "mode": mode, "files": files or {},
            "case_mutator": case_mutator, "check": check}


def scenarios():
    items = [scenario("clean_baseline", check=lambda r, o, t: (
        assert_equal(r["statistics"]["x"]["mean"], 2.0) and
        assert_equal(r["findings"], []) and assert_true((o / "analysis.py").is_file())))]
    items.append(scenario("generate_only_never_claims_execution", mode="generate", status="generated",
                          check=lambda r, o, t: assert_true(not (o / "analysis.json").exists()) and
                          assert_equal(r["execution_result"]["executed"], False)))
    rows = copy.deepcopy(BASE_ROWS)
    rows[1]["y"], rows[2]["y"] = "0", "NA"
    items.append(scenario("missing_is_not_zero", rows=rows, status="review", rules=["data.missing_values"],
                          check=lambda r, o, t: assert_equal(r["statistics"]["y"]["n"], 5) and
                          assert_equal(r["statistics"]["y"]["min"], 0.0)))
    rows = copy.deepcopy(BASE_ROWS)
    rows[2]["x"] = "six"
    unparsed_spec = copy.deepcopy(BASE_SPEC)
    unparsed_spec["validation"] = {}
    items.append(scenario("unparsed_numeric_named", spec=unparsed_spec, rows=rows, status="review",
                          rules=["data.unparsed_values"],
                          check=lambda r, o, t: assert_equal(r["statistics"]["x"]["unparsed"], 1)))
    rows = copy.deepcopy(BASE_ROWS) + [copy.deepcopy(BASE_ROWS[0])]
    duplicate_spec = copy.deepcopy(BASE_SPEC)
    duplicate_spec["validation"] = {}
    items.append(scenario("duplicates_kept_by_default", spec=duplicate_spec, rows=rows, status="review",
                          rules=["data.duplicate_rows"],
                          check=lambda r, o, t: assert_equal(r["analysis_result"]["input"]["rows_analysed"], 7) and
                          assert_equal(r["analysis_result"]["data_quality"]["duplicates_removed"], 0)))
    drop_spec = copy.deepcopy(duplicate_spec)
    drop_spec["drop_exact_duplicates"] = True
    items.append(scenario("duplicates_explicitly_dropped", spec=drop_spec, rows=rows, status="review",
                          rules=["data.duplicate_rows"],
                          check=lambda r, o, t: assert_equal(r["analysis_result"]["input"]["rows_analysed"], 6) and
                          assert_equal(r["statistics"]["x"]["mean"], 2.0)))
    group_spec = copy.deepcopy(BASE_SPEC)
    group_spec["group_by"] = "group"
    items.append(scenario("group_summaries", spec=group_spec,
                          check=lambda r, o, t: assert_equal(
                              [x["n"] for x in r["analysis_result"]["groups"]["metrics"]["y"]], [3, 3])))
    welch_spec = copy.deepcopy(BASE_SPEC)
    welch_spec["group_by"] = "group"
    welch_spec["welch_t"] = {"column": "y", "group_a": "A", "group_b": "B"}
    items.append(scenario("welch_small_sample_advisory", spec=welch_spec, status="review",
                          rules=["stats.small_sample"],
                          check=lambda r, o, t: assert_true(r["analysis_result"]["tests"][0]["p_two_sided"] is not None)))
    rows = []
    for index in range(6):
        rows.append({"sample": f"A{index}", "group": "A", "x": str(index), "y": str(10 + index)})
        rows.append({"sample": f"B{index}", "group": "B", "x": str(index), "y": str(14 + index)})
    stable_spec = copy.deepcopy(welch_spec)
    stable_spec["validation"] = {}
    items.append(scenario("welch_numeric_anchor", spec=stable_spec, rows=rows,
                          check=lambda r, o, t: assert_close(r["analysis_result"]["tests"][0]["p_two_sided"],
                                                            0.0040863304, 1e-9)))
    zero_spec = copy.deepcopy(welch_spec)
    zero_spec["validation"] = {}
    zero_rows = copy.deepcopy(BASE_ROWS)
    for row in zero_rows:
        row["y"] = "1" if row["group"] == "A" else "2"
    items.append(scenario("welch_zero_variance_refused", spec=zero_spec, rows=zero_rows,
                          status="blocked", rules=["stats.zero_variance"]))
    corr_spec = copy.deepcopy(BASE_SPEC)
    corr_spec["correlations"] = [["x", "y"]]
    items.append(scenario("paired_correlation", spec=corr_spec,
                          check=lambda r, o, t: assert_equal(r["analysis_result"]["correlations"][0]["n"], 6)))
    golden_bad = copy.deepcopy(BASE_SPEC)
    golden_bad["validation"]["golden"][0]["value"] = 999
    items.append(scenario("golden_mismatch_blocks", spec=golden_bad, status="blocked", rules=["validation.golden.0"]))
    rows_bad = copy.deepcopy(BASE_SPEC)
    rows_bad["validation"]["expected_rows"] = 7
    items.append(scenario("expected_rows_mismatch_blocks", spec=rows_bad, status="blocked",
                          rules=["validation.expected_rows"]))
    histogram = copy.deepcopy(BASE_SPEC)
    histogram["chart"] = {"kind": "histogram", "column": "x", "bins": 4, "unit": "mg"}
    items.append(scenario("histogram_svg", spec=histogram,
                          check=lambda r, o, t: assert_true("data-count" in (o / "figure.svg").read_text(encoding="utf-8"))))
    scatter = copy.deepcopy(BASE_SPEC)
    scatter["chart"] = {"kind": "scatter", "x": "x", "y": "y", "title": "真实相关"}
    items.append(scenario("scatter_svg_row_trace", spec=scatter,
                          check=lambda r, o, t: assert_true("data-row" in (o / "figure.svg").read_text(encoding="utf-8"))))
    json_spec = copy.deepcopy(BASE_SPEC)
    json_spec["input"] = {"path": "data.json", "format": "json"}
    items.append(scenario("json_rows", spec=json_spec,
                          files={"data.json": lambda root, rows: (root / "data.json").write_text(
                              json.dumps({"rows": rows}, ensure_ascii=False), encoding="utf-8")}))
    tsv_spec = copy.deepcopy(BASE_SPEC)
    tsv_spec["input"] = {"path": "data.tsv", "format": "tsv"}
    items.append(scenario("tsv_rows", spec=tsv_spec,
                          files={"data.tsv": lambda root, rows: write_csv(root / "data.tsv", rows, delimiter="\t")}))
    sqlite_spec = copy.deepcopy(BASE_SPEC)
    sqlite_spec["input"] = {"path": "research.db", "format": "sqlite",
                            "query": 'SELECT sample, "group", x, y FROM measurements ORDER BY sample'}
    items.append(scenario("sqlite_read_only_query", spec=sqlite_spec,
                          files={"research.db": make_database},
                          check=lambda r, o, t: assert_equal(r["analysis_result"]["input"]["rows_read"], 6)))
    empty_query = copy.deepcopy(sqlite_spec)
    empty_query["input"]["query"] = 'SELECT sample, "group", x, y FROM measurements WHERE 1=0'
    items.append(scenario("sqlite_empty_query", spec=empty_query, status="undetermined", rules=["input.no_rows"],
                          files={"research.db": make_database}))
    write_query = copy.deepcopy(sqlite_spec)
    write_query["input"]["query"] = "DELETE FROM measurements"
    items.append(scenario("sqlite_write_refused_before_execution", spec=write_query, status="undetermined",
                          rules=["query.not_read_only"], files={"research.db": make_database}))
    cjk_rows = [{"样本": "甲", "组别": "对照", "测量": "1.5"},
                {"样本": "乙", "组别": "处理", "测量": "2.5"}]
    cjk_spec = {"case_id": "中文案例", "input": {"path": "data.csv", "format": "csv"},
                "columns": [{"name": "样本", "type": "id"}, {"name": "组别", "type": "categorical"},
                            {"name": "测量", "type": "numeric", "unit": "微摩尔"}],
                "metrics": ["测量"], "group_by": "组别"}
    items.append(scenario("cjk_end_to_end", spec=cjk_spec, rows=cjk_rows,
                          check=lambda r, o, t: assert_equal(r["case_id"], "中文案例") and
                          assert_true("中文案例" in (o / "result.json").read_text(encoding="utf-8"))))
    exact_cap = copy.deepcopy(BASE_SPEC)
    exact_cap["input"]["max_rows"] = 6
    items.append(scenario("exact_row_cap_not_truncated", spec=exact_cap))
    short_cap = copy.deepcopy(BASE_SPEC)
    short_cap["input"]["max_rows"] = 5
    short_cap["validation"] = {}
    items.append(scenario("row_cap_truncation_blocks", spec=short_cap, status="blocked", rules=["input.row_limit"]))

    def case_values(case):
        case["status"] = "case status must not replace engine status"
        case["analysis_result"] = "case analysis must not replace computed analysis"
    items.append(scenario("engine_wins_case_values_pass", case_mutator=case_values,
                          check=lambda r, o, t: assert_equal(r["case_payload"], "kept verbatim") and
                          assert_equal(r["status"], "clean") and isinstance(r["analysis_result"], dict)))
    return items


def make_database(root, rows):
    path = root / "research.db"
    connection = sqlite3.connect(path)
    connection.execute("CREATE TABLE measurements (sample TEXT, group_name TEXT, x REAL, y REAL)")
    # 'group' is accepted as a column name by SQLite for this synthetic fixture.
    connection.execute("DROP TABLE measurements")
    connection.execute('CREATE TABLE measurements (sample TEXT, "group" TEXT, x REAL, y REAL)')
    connection.executemany('INSERT INTO measurements VALUES (?, ?, ?, ?)',
                           [(r["sample"], r["group"], r["x"], r["y"]) for r in rows])
    connection.commit()
    connection.close()


def assert_true(value):
    assert value, "assertion failed"
    return True


def assert_equal(actual, expected):
    assert actual == expected, f"expected {expected!r}, got {actual!r}"
    return True


def assert_close(actual, expected, tolerance):
    assert actual is not None and abs(actual - expected) <= tolerance, (actual, expected)
    return True


def run_one(item):
    with tempfile.TemporaryDirectory(prefix=f"scicode-{item['name']}-") as temporary:
        root = Path(temporary)
        out = root / "out"
        rows = item["rows"]
        write_csv(root / "data.csv", rows)
        for filename, maker in item["files"].items():
            maker(root, rows)
        spec = item["spec"]
        (root / "spec.json").write_text(json.dumps(spec, ensure_ascii=False), encoding="utf-8")
        case = {"case_id": spec.get("case_id"), "case_payload": "kept verbatim",
                "output_contract": CONTRACT}
        if item["case_mutator"]:
            item["case_mutator"](case)
        (root / "case.json").write_text(json.dumps(case, ensure_ascii=False), encoding="utf-8")
        command = [sys.executable, "-I", str(CLI), "--spec", str(root / "spec.json"),
                   "--case", str(root / "case.json"), "--out", str(out), "--mode", item["mode"]]
        process = subprocess.run(command, capture_output=True, text=True, timeout=30)
        errors = []
        try:
            result = json.loads((out / "result.json").read_text(encoding="utf-8"))
        except Exception as exc:
            return {"scenario": item["name"], "pass": False,
                    "error": f"result unreadable: {exc}; stdout={process.stdout}; stderr={process.stderr}"}
        expected_rc = {"clean": 0, "generated": 0, "review": 3, "blocked": 4, "undetermined": 5}[item["status"]]
        if process.returncode != expected_rc:
            errors.append(f"rc {process.returncode} != {expected_rc}")
        if result.get("status") != item["status"]:
            errors.append(f"status {result.get('status')} != {item['status']}")
        fired = {finding.get("rule") for finding in result.get("findings", [])}
        if not item["rules"].issubset(fired):
            errors.append(f"missing rules {sorted(item['rules'] - fired)}")
        if item["name"] == "clean_baseline" and fired:
            errors.append(f"clean baseline fired {sorted(fired)}")
        for key in CONTRACT:
            if key not in result:
                errors.append(f"contract missing {key}")
        if result.get("not_derivable") is not None:
            errors.append("unknown contract field was not null")
        if "Traceback" in process.stdout or "Traceback" in process.stderr:
            errors.append("top-level traceback")
        if item["check"]:
            try:
                item["check"](result, out, root)
            except Exception as exc:
                errors.append(f"scenario assertion: {exc}")
        return {"scenario": item["name"], "pass": not errors, "status": result.get("status"),
                "exit_code": process.returncode, "fired": sorted(fired), "errors": errors}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--report", help="optional JSON report path (never required for runtime)")
    args = parser.parse_args()
    rows = [run_one(item) for item in scenarios()]
    for row in rows:
        print(("PASS" if row["pass"] else "FAIL") + f" {row['scenario']:<42} " +
              (f"status={row.get('status')} rc={row.get('exit_code')}" if row["pass"] else str(row.get("errors") or row.get("error"))))
    passed = sum(row["pass"] for row in rows)
    report = {"schema_version": "scicode-bench/v1", "synthetic_inputs": True,
              "totals": {"passed": passed, "of": len(rows)}, "scenarios": rows}
    if args.report:
        Path(args.report).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"{passed}/{len(rows)} scenarios pass")
    return 0 if passed == len(rows) else 1


if __name__ == "__main__":
    raise SystemExit(main())
