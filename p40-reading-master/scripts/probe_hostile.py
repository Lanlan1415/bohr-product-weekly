"""Twenty-five real-CLI hostile probes for reading-master.

Every probe asserts exit in {0,3,4,5}, no traceback, and the promised JSON artifact.
Refusal probes also verify that output_contract is not echoed as a fake deliverable.
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS))
PKG = SCRIPTS.parent
ALLOWED = {0, 3, 4, 5}


def run(name: str, argv: list[str], result: Path | None, expect: int,
        work: Path, rows: list, check=None):
    proc = subprocess.run([sys.executable, "-I", "-X", "utf8"] + argv,
                          capture_output=True, text=True, timeout=180)
    clean = "Traceback" not in proc.stdout and "Traceback" not in proc.stderr
    data = None
    if result is not None and result.exists():
        try:
            data = json.loads(result.read_text(encoding="utf-8"))
        except Exception:
            clean = False
    ok = proc.returncode in ALLOWED and proc.returncode == expect and clean
    if result is not None:
        ok = ok and data is not None
    if check:
        ok = ok and bool(check(data))
    detail = {"exit": proc.returncode, "stderr": proc.stderr[-300:],
              "result": data, "stdout": proc.stdout[-200:]}
    rows.append((name, ok, detail))


def write_json(path: Path, value) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(value, str):
        path.write_text(value, encoding="utf-8")
    else:
        path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")
    return path


def main() -> int:
    work = Path(tempfile.mkdtemp(prefix="probe40_"))
    sec = str(SCRIPTS / "secrun.py")
    wr = str(SCRIPTS / "writeaudit.py")
    fig = str(SCRIPTS / "figparse.py")
    tab = str(SCRIPTS / "tables.py")
    extract = json.loads((PKG / "examples" / "spec-extract.json").read_text(encoding="utf-8"))
    rows = []

    def sec_case(name: str, value, expect=5, section=None, check=None):
        spec = write_json(work / name / "spec.json", value)
        out = work / name / "out"
        argv = [sec, "--spec", str(spec), "--out", str(out)]
        if section:
            argv += ["--section", section]
        run(name, argv, out / "result.json", expect, work, rows, check)

    sec_case("p01_sec_missing", None if False else "{not json", 5)
    # A truly missing file is separate from malformed JSON.
    out = work / "p02_sec_notfound" / "out"
    run("p02_sec_notfound", [sec, "--spec", str(work / "none.json"), "--out", str(out)],
        out / "result.json", 5, work, rows)
    sec_case("p03_sec_array", [1, 2, 3], 5)
    bad_section = dict(extract)
    bad_section["output_contract"] = ["fake_answer"]
    sec_case("p04_sec_unknown_no_echo", bad_section, 5, "not_a_section",
             lambda r: "fake_answer" not in r)

    nested = dict(extract)
    nested.pop("case_id", None)
    nested.pop("output_contract", None)
    nested["case"] = {"case_id": "nested-40", "custom_note": "kept",
                      "output_contract": {"case_id": "id", "custom_note": "note",
                                          "missing_field": "null"}}
    sec_case("p05_sec_nested_contract", nested, 0, None,
             lambda r: (r.get("case_id") == "nested-40" and r.get("custom_note") == "kept"
                        and "missing_field" in r and r["missing_field"] is None
                        and any("missing_field" in x for x in r["limits"])))

    objects = dict(extract)
    objects["output_contract"] = [{"field": "status"}, {"name": "case_id"},
                                  {"key": "custom_metric"}]
    objects["custom_metric"] = 42
    sec_case("p06_sec_contract_objects", objects, 0, None,
             lambda r: r.get("custom_metric") == 42 and r.get("case_id") == "a028c71c-extract-demo")

    weird = dict(extract)
    weird["output_contract"] = 7
    sec_case("p07_sec_contract_shape", weird, 0, None,
             lambda r: any("output_contract shape" in x for x in r["limits"]))

    malformed = dict(extract)
    malformed["fields"] = [1]
    sec_case("p08_sec_malformed_fields", malformed, 5, None,
             lambda r: (r["status"] == "undetermined"
                        and r["findings"][0]["rule"] == "audit.spec_malformed"))

    # Writing CLI failures and malformed glossary.
    out = work / "p09_write_notfound" / "out"
    run("p09_write_notfound", [wr, "--spec", str(work / "none-write.json"), "--out", str(out)],
        out / "result.json", 5, work, rows)
    spec = write_json(work / "p10_write_badjson" / "spec.json", "{bad")
    out = work / "p10_write_badjson" / "out"
    run("p10_write_badjson", [wr, "--spec", str(spec), "--out", str(out)],
        out / "result.json", 5, work, rows)
    spec = write_json(work / "p11_write_unknown" / "spec.json", {"section": "qa"})
    out = work / "p11_write_unknown" / "out"
    run("p11_write_unknown", [wr, "--spec", str(spec), "--out", str(out),
                              "--section", "not_writing"], out / "result.json", 5, work, rows)

    translation = {
        "case_id": "probe-translation",
        "section": "translation", "output_mode": "plain",
        "source_text": "Coating may improve uptake.", "source_lang": "en",
        "target_text": "涂层可能提高吸收。", "target_lang": "zh",
        "glossary": [1],
        "segments": [{"id": "s1", "source": "Coating may improve uptake.",
                      "target": "涂层可能提高吸收。"}],
    }
    spec = write_json(work / "p12_write_badglossary" / "spec.json", translation)
    out = work / "p12_write_badglossary" / "out"
    run("p12_write_badglossary", [wr, "--spec", str(spec), "--out", str(out)],
        out / "result.json", 5, work, rows,
        lambda r: r["findings"][0]["rule"] == "audit.spec_malformed")

    translation["glossary"] = {}
    translation["custom_note"] = "writing kept"
    translation["output_contract"] = ["case_id", "custom_note", "section"]
    spec = write_json(work / "p13_write_contract" / "spec.json", translation)
    out = work / "p13_write_contract" / "out"
    run("p13_write_contract", [wr, "--spec", str(spec), "--out", str(out)],
        out / "result.json", 0, work, rows,
        lambda r: r.get("custom_note") == "writing kept" and r.get("case_id") == "probe-translation")

    # Figure case/file failures, including the two tracebacks preserved from attempt 88031.
    out = work / "p14_fig_case_missing" / "out"
    run("p14_fig_case_missing", [fig, "run", "--case", str(work / "none-case.json"),
                                 "--out", str(out)], out / "result.json", 5, work, rows)
    case = write_json(work / "p15_fig_badjson" / "case.json", "{not json")
    out = work / "p15_fig_badjson" / "out"
    run("p15_fig_badjson", [fig, "run", "--case", str(case), "--out", str(out)],
        out / "result.json", 5, work, rows)
    case = write_json(work / "p16_fig_nonobject" / "case.json", [1])
    out = work / "p16_fig_nonobject" / "out"
    run("p16_fig_nonobject", [fig, "run", "--case", str(case), "--out", str(out)],
        out / "result.json", 5, work, rows)

    missing_case = {"case_id": "missing-image", "images": [{"path": "ghost.png"}],
                    "output_contract": ["fake_answer"]}
    case = write_json(work / "p17_fig_ghost" / "case.json", missing_case)
    out = work / "p17_fig_ghost" / "out"
    run("p17_fig_ghost", [fig, "run", "--case", str(case), "--out", str(out)],
        out / "result.json", 5, work, rows,
        lambda r: "fake_answer" not in r and any("not found" in x for x in r["limits"]))

    corrupt_dir = work / "p18_fig_corrupt"
    corrupt_dir.mkdir(parents=True, exist_ok=True)
    (corrupt_dir / "corrupt.png").write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 32)
    case = write_json(corrupt_dir / "case.json", {"case_id": "corrupt-image",
                                                  "images": [{"path": "corrupt.png"}]})
    out = corrupt_dir / "out"
    run("p18_fig_corrupt", [fig, "run", "--case", str(case), "--out", str(out)],
        out / "result.json", 5, work, rows,
        lambda r: any("decoded" in x for x in r["limits"]))

    calib = corrupt_dir / "calib.json"
    run("p19_calibrate_ghost", [fig, "calibrate", "--image", str(corrupt_dir / "ghost.png"),
                                "--out", str(calib)], calib, 5, work, rows,
        lambda r: r.get("limits"))

    # Valid figure with contract echo (success 0), generated from analytic truth.
    import bench_figparse as B
    valid_dir = work / "p20_fig_valid"
    B.emit(B.build_cases()[0], valid_dir)
    case_obj = json.loads((valid_dir / "01-linear-two-series" / "case.json").read_text())
    case_obj["custom_note"] = "figure kept"
    case_obj["output_contract"] = ["status", "case_id", "custom_note", "panels"]
    case = write_json(valid_dir / "01-linear-two-series" / "case.json", case_obj)
    out = valid_dir / "out"
    run("p20_fig_valid_contract", [fig, "run", "--case", str(case), "--out", str(out)],
        out / "result.json", 0, work, rows,
        lambda r: r.get("custom_note") == "figure kept" and bool(r.get("panels")))

    # Tables: success, all-failed undetermined, malformed JSON and bad case.
    table_dir = work / "p21_table_valid"
    table_dir.mkdir(parents=True, exist_ok=True)
    csv = table_dir / "table.csv"
    csv.write_text("sample,value\nA,12%\nB,25%\n", encoding="utf-8")
    case = write_json(table_dir / "case.json", {
        "case_id": "table-probe", "custom_note": "table kept",
        "output_contract": ["status", "case_id", "custom_note", "tables"]})
    out = table_dir / "out"
    run("p21_table_valid_contract", [tab, str(csv), "--out", str(out), "--case", str(case)],
        out / "result.json", 0, work, rows,
        lambda r: r.get("custom_note") == "table kept" and r["tables"][0]["ok"])

    out = work / "p22_table_missing" / "out"
    run("p22_table_missing", [tab, str(work / "no-table.csv"), "--out", str(out)],
        out / "result.json", 5, work, rows,
        lambda r: not r["tables"][0]["ok"])

    bad_json = write_json(work / "p23_table_badjson" / "bad.json", "{not json")
    out = work / "p23_table_badjson" / "out"
    run("p23_table_badjson", [tab, str(bad_json), "--out", str(out)],
        out / "result.json", 5, work, rows,
        lambda r: not r["tables"][0]["ok"] and r["tables"][0].get("reason"))

    case = write_json(work / "p24_table_badcase" / "case.json", "{bad")
    out = work / "p24_table_badcase" / "out"
    run("p24_table_badcase", [tab, str(csv), "--out", str(out), "--case", str(case)],
        out / "result.json", 5, work, rows)

    occupied = work / "p25_out_is_file"
    occupied.write_text("x", encoding="utf-8")
    run("p25_sec_out_is_file", [sec, "--spec", str(PKG / "examples" / "spec-extract.json"),
                                "--out", str(occupied)], None, 5, work, rows)

    failed = 0
    print()
    for name, ok, detail in rows:
        print(("PASS" if ok else "FAIL") + "  " + name)
        if not ok:
            failed += 1
            print("      " + json.dumps(detail, ensure_ascii=False, default=str)[:600])
    print(f"\n{len(rows) - failed}/{len(rows)} probes pass")
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())
