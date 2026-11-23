"""Thirty hostile probes of the real p69 CLI and its recoverable result records."""
from __future__ import annotations

import copy
import json
import subprocess
import sys
import tempfile
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
PKG = SCRIPTS.parent
CLI = SCRIPTS / "trendrun.py"
BASE = json.loads((PKG / "examples/spec-trend.json").read_text(encoding="utf-8"))


def spec():
    return copy.deepcopy(BASE)


def execute(root: Path, name: str, payload=None, raw=None, missing_spec=False,
            case=None, case_raw=None, case_id=None) -> dict:
    work = root / name
    work.mkdir(parents=True, exist_ok=True)
    path = work / "spec.json"
    if not missing_spec:
        path.write_text(raw if raw is not None else json.dumps(payload if payload is not None else spec(),
                                                              ensure_ascii=False), encoding="utf-8")
    argv = [sys.executable, "-I", "-X", "utf8", str(CLI),
            "--spec", str(path), "--out", str(work / "nested" / "out")]
    if case is not None or case_raw is not None:
        cp = work / "case.json"
        cp.write_text(case_raw if case_raw is not None else json.dumps(case, ensure_ascii=False), encoding="utf-8")
        argv += ["--case", str(cp)]
    if case_id:
        argv += ["--case-id", case_id]
    proc = subprocess.run(argv, capture_output=True, text=True, timeout=240)
    result_path = work / "nested" / "out" / "result.json"
    try:
        result = json.loads(result_path.read_text(encoding="utf-8"))
        valid = isinstance(result, dict)
    except Exception:
        result, valid = None, False
    no_traceback = "Traceback" not in proc.stdout + proc.stderr
    return {"exit": proc.returncode, "result": result, "valid_result": valid,
            "no_traceback": no_traceback, "stderr": proc.stderr[-400:],
            "base_ok": proc.returncode in (0, 3, 4, 5) and valid and no_traceback}


def main() -> int:
    root = Path(tempfile.mkdtemp(prefix="p69_hostile_"))
    checks = []

    def add(name, row, expected=None, predicate=True):
        ok = row["base_ok"] and predicate and (expected is None or row["exit"] == expected)
        checks.append({"probe": name, "pass": ok, "exit": row["exit"],
                       "status": (row.get("result") or {}).get("status"),
                       "result_json": row["valid_result"], "no_traceback": row["no_traceback"]})
        print(f"{'PASS' if ok else 'FAIL'}  {name:<40} exit={row['exit']} result={row['valid_result']}")
        if not ok:
            print(json.dumps(row, ensure_ascii=False, default=str)[:700])

    case = {"case_id": "hostile-valid", "output_contract": ["case_id", "research_product", "evidence_matrix", "uncertainty"]}
    row = execute(root, "01_clean", case=case)
    add("01_clean_contract_artifacts", row, 0,
        row["result"]["case_id"] == "hostile-valid" and len(row["result"].get("artifacts") or []) == 4)
    add("02_missing_spec", execute(root, "02_missing_spec", missing_spec=True), 5)
    add("03_invalid_json", execute(root, "03_invalid_json", raw="{broken"), 5)
    add("04_array_spec", execute(root, "04_array_spec", raw="[1,2]"), 5)
    s = spec(); s["records"] = []
    add("05_empty_corpus", execute(root, "05_empty_corpus", s), 4)
    s = spec(); s["records"] = "ten records"
    add("06_records_wrong_type", execute(root, "06_records_wrong_type", s), 5)
    s = spec(); s.pop("records"); s["records_path"] = str(root / "absent.json")
    add("07_missing_records_file", execute(root, "07_missing_records_file", s), 5)
    bad_json = root / "records-bad.json"; bad_json.write_text("[{bad", encoding="utf-8")
    s = spec(); s.pop("records"); s["records_path"] = str(bad_json)
    add("08_malformed_records_file", execute(root, "08_malformed_records_file", s), 5)
    empty_csv = root / "records-empty.csv"; empty_csv.write_text("id,title,year\n", encoding="utf-8")
    s = spec(); s.pop("records"); s["records_path"] = str(empty_csv)
    add("09_empty_csv", execute(root, "09_empty_csv", s), 4)
    s = spec(); s["research_question"] = ""
    add("10_question_missing", execute(root, "10_question_missing", s), 4)
    s = spec(); s.pop("search_protocol")
    add("11_protocol_missing", execute(root, "11_protocol_missing", s), 4)
    s = spec(); s["search_protocol"]["start_year"] = 2024; s["search_protocol"]["end_year"] = 2018
    add("12_reversed_window", execute(root, "12_reversed_window", s), 4)
    s = spec(); s["search_protocol"]["year_basis"] = "unsure"
    add("13_unknown_year_basis", execute(root, "13_unknown_year_basis", s), 4)
    s = spec(); s["records"][0].pop("decision")
    add("14_undetermined_screening", execute(root, "14_undetermined_screening", s), 4)
    s = spec(); duplicate = copy.deepcopy(s["records"][2]); duplicate["id"] = "R011"; s["records"].append(duplicate)
    add("15_duplicate_version", execute(root, "15_duplicate_version", s), 3)
    s = spec(); duplicate = copy.deepcopy(s["records"][1]); duplicate["id"] = "R001"; s["records"].append(duplicate)
    add("16_duplicate_record_id", execute(root, "16_duplicate_record_id", s), 4)
    s = spec(); s["records"][0].pop("year")
    add("17_missing_year", execute(root, "17_missing_year", s), 3)
    s = spec(); s["output_contract"] = 7
    row = execute(root, "18_contract_bad_shape", s)
    add("18_contract_bad_shape", row, 0, any("output_contract" in x for x in row["result"]["limits"]))
    s = spec(); s["output_contract"] = [{"field": "case_id"}, {"name": "custom"}, {"key": "absent"}]
    s["custom"] = {"kept": True}
    row = execute(root, "19_contract_object_list", s)
    add("19_contract_object_list", row, 0,
        row["result"].get("custom") == {"kept": True} and row["result"].get("absent") is None)
    row = execute(root, "20_malformed_case", case_raw="{bad")
    add("20_malformed_case", row, 0, any("case.json" in x for x in row["result"]["limits"]))
    row = execute(root, "21_case_identity_authoritative", case={"case_id": "actual-case", "output_contract": ["case_id"]})
    add("21_case_identity_authoritative", row, 0, row["result"]["case_id"] == "actual-case")
    row = execute(root, "22_refusal_keeps_explicit_id", raw="[1]", case_id="refusal-id")
    add("22_refusal_keeps_explicit_id", row, 5, row["result"].get("case_id") == "refusal-id")
    s = spec(); s["gap_candidates"][0]["evidence"][0]["record_id"] = "NOPE"
    add("23_unknown_gap_evidence", execute(root, "23_unknown_gap_evidence", s), 4)
    s = spec(); s["gap_candidates"][0]["exclusion_checks"] = []
    row = execute(root, "24_gap_without_exclusion", s)
    add("24_gap_without_exclusion", row, 4,
        row["result"].get("research_gaps", [{}])[0].get("computed_status") == "undetermined" if row["result"].get("research_gaps") else False)
    s = spec(); s["ambiguous_terms"].append({"term": "GNN", "topic_by_context": {}})
    add("25_unresolved_homonym", execute(root, "25_unresolved_homonym", s), 4)
    s = spec(); s["gap_candidates"] = []
    row = execute(root, "26_no_gap_candidates", s)
    add("26_no_gap_candidates_not_invented", row, 0,
        row["result"]["research_gaps"] == [] and any(x.get("kind") == "research_gap" for x in row["result"]["uncertainty"]))
    s = spec(); s["screening_protocol"] = {"auto_apply": True, "must_match_any": ["coating", "GNN", "graph"],
                                          "exclude_terms": ["clinical dosing"]}
    for r in s["records"]:
        r.pop("decision", None); r.pop("reason", None); r.pop("reason_code", None)
    add("27_prospective_auto_screen", execute(root, "27_prospective_auto_screen", s), 0)
    records_path = root / "records.json"
    records_path.write_text(json.dumps(BASE["records"], ensure_ascii=False), encoding="utf-8")
    s = spec(); s.pop("records"); s["records_path"] = str(records_path)
    add("28_external_json_records", execute(root, "28_external_json_records", s), 0)
    s = spec(); s["trend_claims"][0]["expected_count"] = 99
    add("29_trend_count_mismatch", execute(root, "29_trend_count_mismatch", s), 4)
    s = spec(); s["trend_claims"][0].update({"change_point_year": 2022, "significance": "confirmed"})
    row = execute(root, "30_overclaimed_turning_point", s)
    add("30_overclaimed_turning_point", row, 4,
        any(x["rule"] == "tr.changepoint_overclaimed" for x in row["result"]["findings"]))

    passed = sum(x["pass"] for x in checks)
    report = {"schema_version": "trend-hostile/v2", "probes": checks,
              "totals": {"passed": passed, "of": len(checks)}, "temp_root": str(root)}
    (SCRIPTS / "report_hostile.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n{passed}/{len(checks)} probes pass")
    return 0 if passed == len(checks) else 1


if __name__ == "__main__":
    raise SystemExit(main())
