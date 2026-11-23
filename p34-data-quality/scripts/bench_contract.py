"""Benchmark for the case contract: case_id + output_contract passthrough, refusals.

The Harbor runtime contract requires every case result.json to keep case_id and
every field the case's output_contract names. This bench pins that behaviour and
the refusal ladder: an unrunnable input is an exit-5 undetermined result.json,
never a traceback, every readable refusal preserves case_id/output_contract,
and a re-clean of the same input into the same directory stays refused.

    python bench_contract.py
"""

from __future__ import annotations

import copy
import json
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import dataquality  # noqa: E402
import quality_gates  # noqa: E402

OUT = Path(__file__).resolve().parent / "_run_contract"

CLEAN = {
    "case_id": "demo-case-340",
    "rows": [
        {"sample_id": "S1", "bandgap": "3.20 eV", "measured_on": "2023/05/14"},
        {"sample_id": "s1", "bandgap": "3200 meV", "measured_on": "2023年5月14日"},
        {"sample_id": "S2", "bandgap": "not reported", "measured_on": "14.06.2023"},
    ],
    "columns": [
        {"name": "sample_id", "semantic": "id"},
        {"name": "bandgap", "target_unit": "eV", "plausible": [0, 6], "semantic": "numeric"},
        {"name": "measured_on", "semantic": "date"},
    ],
    "key_columns": ["sample_id"],
    "output_contract": {"cleaned_table": "the cleaned table",
                        "quality_report": "computed per-column report",
                        "change_ledger": "rule/row/column/original/new per edit",
                        "anomaly_notes": "named gaps and refusals"},
    "anomaly_notes": "S2 bandgap 未检出：missing，不是 0；日期 14.06.2023 为 dot 格式。",
}


def write_spec(name: str, spec) -> Path:
    d = OUT / name
    d.mkdir(parents=True, exist_ok=True)
    body = spec if isinstance(spec, str) else json.dumps(spec, ensure_ascii=False)
    (d / "spec.json").write_text(body, encoding="utf-8")
    return d / "spec.json"


def scen_case_id_echo():
    """case_id and contract fields land in result.json; carried values pass through."""
    r = dataquality.build_and_audit(write_spec("echo", copy.deepcopy(CLEAN)),
                                    OUT / "echo_out")
    problems = []
    if r.get("case_id") != "demo-case-340":
        problems.append("case_id missing")
    if r.get("anomaly_notes") != CLEAN["anomaly_notes"]:
        problems.append("carried contract value did not pass through verbatim")
    if r.get("quality_report", {}).get("rows") != 3:
        problems.append("quality_report not derived")
    if r.get("change_ledger") != r.get("changes"):
        problems.append("change_ledger was not derived from the real edit ledger")
    if any("change_ledger" in x for x in r.get("limits", [])):
        problems.append("derivable change_ledger was incorrectly marked undetermined")
    if not r.get("validation_results") or not (r.get("report_reconciliation") or {}).get("all_match"):
        problems.append("validation evidence or report/table reconciliation missing")
    restored = quality_gates.restore_rows(r["cleaned_table"], r["changes"])
    if restored != CLEAN["rows"]:
        problems.append("reverse ledger did not restore the exact original rows")
    if r.get("output_contract_fields") != list(CLEAN["output_contract"]):
        problems.append("contract field list not recorded")
    return problems


def scen_bad_json():
    """Unparseable JSON is an undetermined refusal with exit 5, not a traceback."""
    spec_path = write_spec("badjson", '{"rows": [oops')
    problems = []
    code = dataquality.main(["--spec", str(spec_path), "--out", str(OUT / "badjson_out")])
    if code != 5:
        problems.append(f"exit code {code}, expected 5")
    r = json.loads((OUT / "badjson_out" / "result.json").read_text(encoding="utf-8"))
    if r.get("status") != "undetermined":
        problems.append("status not undetermined")
    if not any(f.get("rule") == "clean.refused" for f in r.get("findings", [])):
        problems.append("refusal finding missing")
    if r.get("case_id") is not None:
        problems.append("unreadable input without --case cannot recover a case_id")
    return problems


def scen_not_object():
    """A JSON array is refused as undetermined."""
    spec_path = write_spec("notobject", "[1, 2, 3]")
    r = dataquality.build_and_audit(spec_path, OUT / "notobject_out")
    problems = []
    if r.get("status") != "undetermined":
        problems.append("status not undetermined")
    if "not an object" not in str(r.get("findings", [{}])[0].get("message", "")):
        problems.append("reason not named")
    return problems


def scen_missing_spec_file():
    """A missing spec file is refused undetermined (no FileNotFoundError traceback)."""
    problems = []
    code = dataquality.main(["--spec", str(OUT / "nope" / "spec.json"),
                             "--out", str(OUT / "nope_out")])
    if code != 5:
        problems.append(f"exit code {code}, expected 5")
    r = json.loads((OUT / "nope_out" / "result.json").read_text(encoding="utf-8"))
    if r.get("status") != "undetermined":
        problems.append("status not undetermined")
    return problems


def scen_no_rows():
    """Empty rows / rows as a dict are refused undetermined and still name the case."""
    problems = []
    spec = copy.deepcopy(CLEAN)
    spec["rows"] = []
    code = dataquality.main(["--spec", str(write_spec("norows", spec)),
                             "--out", str(OUT / "norows_out")])
    if code != 5:
        problems.append(f"empty rows exit code {code}, expected 5")
    r = json.loads((OUT / "norows_out" / "result.json").read_text(encoding="utf-8"))
    if r.get("case_id") != "demo-case-340":
        problems.append("refused run lost the case_id")
    spec2 = copy.deepcopy(CLEAN)
    spec2["rows"] = {"S1": {"bandgap": "3.2 eV"}}
    r2 = dataquality.build_and_audit(write_spec("rowsdict", spec2), OUT / "rowsdict_out")
    if r2.get("status") != "undetermined":
        problems.append("rows as an object must be refused, not partially cleaned")
    return problems


def scen_table_path_error():
    """A table_path that cannot be read is an undetermined refusal, not a crash."""
    problems = []
    spec = copy.deepcopy(CLEAN)
    spec.pop("rows")
    spec["table_path"] = str(OUT)  # a directory: read_text must not raise
    r = dataquality.build_and_audit(write_spec("tabledir", spec), OUT / "tabledir_out")
    if r.get("status") != "undetermined":
        problems.append(f"status {r.get('status')}, expected undetermined")
    spec2 = copy.deepcopy(CLEAN)
    spec2.pop("rows")
    spec2["table_path"] = str(OUT / "ghost_table.csv")
    r2 = dataquality.build_and_audit(write_spec("tablemiss", spec2), OUT / "tablemiss_out")
    if r2.get("status") != "undetermined":
        problems.append(f"missing table status {r2.get('status')}, expected undetermined")
    return problems


def scen_idempotent_rerun():
    """Same spec into fresh directories: identical findings; same directory refuses."""
    problems = []
    outs = []
    for run in (1, 2):
        r = dataquality.build_and_audit(write_spec("idem", copy.deepcopy(CLEAN)),
                                        OUT / f"idem_out{run}")
        outs.append(r)
    a, b = outs
    if a.get("status") != b.get("status") or a.get("findings") != b.get("findings"):
        problems.append("re-run changed the verdict")
    if a.get("status") != "review":
        problems.append(f"clean-ish baseline reported {a.get('status')}: "
                        f"{[f['rule'] for f in a.get('findings', [])]}")
    # same directory, same input -> refused re-clean, first result intact
    first = json.loads((OUT / "idem_out1" / "result.json").read_text(encoding="utf-8"))
    r3 = dataquality.build_and_audit(write_spec("idem", copy.deepcopy(CLEAN)), OUT / "idem_out1")
    if r3.get("status") != "blocked" or not any(
            f["rule"] == "clean.already_cleaned" for f in r3.get("findings", [])):
        problems.append("same-input re-clean was not refused")
    if r3.get("case_id") != "demo-case-340":
        problems.append("re-clean refusal lost the case_id")
    again = json.loads((OUT / "idem_out1" / "result.json").read_text(encoding="utf-8"))
    if again.get("findings") != first.get("findings"):
        problems.append("the refusal overwrote the first run's result.json")
    return problems


def scen_refusal_contract_from_case():
    """A broken spec still preserves contract metadata supplied by --case."""
    case_path = OUT / "refusal_case.json"
    case = {"case_id": "case-refusal-34", "note": "case-owned pass-through",
            "output_contract": {"case_id": "id", "cleaned_table": "table",
                                "quality_report": "report", "note": "text"}}
    case_path.write_text(json.dumps(case, ensure_ascii=False), encoding="utf-8")
    spec_path = write_spec("badjson_with_case", "{broken")
    code = dataquality.main(["--spec", str(spec_path), "--out", str(OUT / "badjson_case_out"),
                             "--case", str(case_path)])
    r = json.loads((OUT / "badjson_case_out" / "result.json").read_text(encoding="utf-8"))
    problems = []
    if code != 5 or r.get("status") != "undetermined":
        problems.append("broken spec was not exit-5 undetermined")
    if r.get("case_id") != "case-refusal-34" or r.get("note") != "case-owned pass-through":
        problems.append("case-owned fields were lost")
    for key in ("cleaned_table", "quality_report"):
        if key not in r or r[key] is not None:
            problems.append(key + " must be present and null on refusal")
    if r.get("output_contract_fields") != list(case["output_contract"]):
        problems.append("refusal contract field list incomplete")
    return problems


def scen_case_merge_and_undo_cli():
    """--case fills missing metadata and the standalone undo command restores exactly."""
    spec = copy.deepcopy(CLEAN)
    spec.pop("case_id")
    spec.pop("output_contract")
    spec.pop("anomaly_notes")
    case_path = OUT / "merge_case.json"
    case_path.write_text(json.dumps({k: CLEAN[k] for k in
                                     ("case_id", "output_contract", "anomaly_notes")},
                                    ensure_ascii=False), encoding="utf-8")
    out = OUT / "merge_out"
    r = dataquality.build_and_audit(write_spec("merge", spec), out, case_path)
    problems = []
    if r.get("case_id") != CLEAN["case_id"] or r.get("anomaly_notes") != CLEAN["anomaly_notes"]:
        problems.append("case metadata merge failed")
    import subprocess
    undo = OUT / "undo_out"
    proc = subprocess.run([sys.executable, "-I", "-X", "utf8",
                           str(Path(__file__).resolve().parent / "undo_cleaning.py"),
                           "--result", str(out / "result.json"), "--out", str(undo)],
                          capture_output=True, text=True, timeout=60)
    if proc.returncode != 0 or "Traceback" in proc.stderr:
        problems.append("undo CLI failed: " + proc.stderr[-200:])
    else:
        restored = json.loads((undo / "restored.json").read_text(encoding="utf-8"))
        if restored != CLEAN["rows"]:
            problems.append("undo CLI output differs from original")
    return problems


def scen_gb18030_and_duplicate_header():
    """Real encoding conversion is logged; ambiguous headers are structured refusals."""
    table = OUT / "gb18030.csv"
    table.write_bytes("样品,值\n甲,1.5\n乙,2.5\n".encode("gb18030"))
    spec = {"case_id": "encoding-demo", "table_path": str(table),
            "columns": [{"name": "样品", "semantic": "id"},
                        {"name": "值", "semantic": "numeric"}], "key_columns": ["样品"]}
    r = dataquality.build_and_audit(write_spec("encoding", spec), OUT / "encoding_out")
    problems = []
    if r.get("status") != "clean" or (r.get("input_metadata") or {}).get("encoding") != "gb18030":
        problems.append("GB18030 table was not decoded and logged")
    bad = OUT / "duplicate_header.csv"
    bad.write_text("a,a\n1,2\n", encoding="utf-8")
    spec2 = {"case_id": "duplicate-header", "table_path": str(bad),
             "columns": [{"name": "a", "semantic": "numeric"}]}
    r2 = dataquality.build_and_audit(write_spec("duplicate_header", spec2),
                                     OUT / "duplicate_header_out")
    if r2.get("status") != "undetermined" or "duplicate header" not in str(r2.get("findings")):
        problems.append("duplicate header was not refused")
    return problems


SCENARIOS = [
    ("case_id_echo", scen_case_id_echo),
    ("bad_json", scen_bad_json),
    ("not_object", scen_not_object),
    ("missing_spec_file", scen_missing_spec_file),
    ("no_rows", scen_no_rows),
    ("table_path_error", scen_table_path_error),
    ("idempotent_rerun", scen_idempotent_rerun),
    ("refusal_contract_from_case", scen_refusal_contract_from_case),
    ("case_merge_and_undo_cli", scen_case_merge_and_undo_cli),
    ("gb18030_and_duplicate_header", scen_gb18030_and_duplicate_header),
]


def main() -> int:
    shutil.rmtree(OUT, ignore_errors=True)
    rows = []
    for name, fn in SCENARIOS:
        try:
            problems = fn()
        except Exception as exc:
            problems = [f"scenario raised: {exc!r}"]
        rows.append({"scenario": name, "problems": problems, "pass": not problems})
        print(f"{'PASS' if not problems else 'FAIL'}  {name:<20} {problems}")
    passed = sum(1 for r in rows if r["pass"])
    (Path(__file__).resolve().parent / "report_contract.json").write_text(
        json.dumps({"schema_version": "contract-bench/v1", "scenarios": rows,
                    "totals": {"passed": passed, "of": len(rows)}},
                   ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n{passed}/{len(rows)} scenarios pass")
    return 0 if passed == len(rows) else 1


if __name__ == "__main__":
    raise SystemExit(main())
