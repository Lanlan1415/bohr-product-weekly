"""Twenty-six hostile CLI probes: valid exit, JSON result, and no traceback."""
from __future__ import annotations

import copy
import json
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
CLI = SCRIPTS / "deckbuild.py"
BASE = {
    "section": "paper_to_deck", "case_id": "probe-p43",
    "output_contract": ["case_id", "status", "deck_file", "evidence_map"],
    "spacing": {"title": 32, "body": 20}, "font_ea": "Microsoft YaHei", "font_latin": "Arial",
    "min_font_pt": 14, "require_notes": True, "available_evidence": ["Fig. 3b, p.7"],
    "slides": [
        {"title": "问题", "claim": "速率是瓶颈", "evidence": "Fig. 3b, p.7", "notes": "引入。"},
        {"title": "速率提高 3 倍", "claim": "涂层提高速率", "evidence": "Fig. 3b, p.7",
         "bullets": ["n = 6", "3 倍"], "notes": "强调对照。"},
    ],
}


def execute(root: Path, name: str, payload=BASE, *, raw=None, missing=False,
            case=None, case_raw=None) -> dict:
    work = root / name
    work.mkdir(parents=True, exist_ok=True)
    spec = work / "missing.json" if missing else work / "spec.json"
    if not missing:
        spec.write_text(raw if raw is not None else json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    argv = [sys.executable, "-I", "-X", "utf8", str(CLI),
            "--spec", str(spec), "--out", str(work / "out")]
    if case is not None or case_raw is not None:
        case_path = work / "case.json"
        case_path.write_text(case_raw if case_raw is not None else json.dumps(case, ensure_ascii=False),
                             encoding="utf-8")
        argv += ["--case", str(case_path)]
    proc = subprocess.run(argv, capture_output=True, text=True, timeout=240)
    result_path = work / "out" / "result.json"
    try:
        result = json.loads(result_path.read_text(encoding="utf-8"))
        valid_json = isinstance(result, dict)
    except Exception:
        result, valid_json = None, False
    no_traceback = "Traceback" not in proc.stdout + proc.stderr
    return {"name": name, "exit": proc.returncode, "result": result,
            "has_result": valid_json, "no_traceback": no_traceback,
            "stderr": proc.stderr[-300:],
            "base_ok": proc.returncode in (0, 3, 4, 5) and valid_json and no_traceback}


def main() -> int:
    root = Path(tempfile.mkdtemp(prefix="p43_hostile_"))
    checks = []

    def add(name: str, row: dict, extra=True, expected=None):
        ok = row["base_ok"] and extra
        if expected is not None:
            ok = ok and row["exit"] == expected
        checks.append({"probe": name, "pass": ok, "exit": row["exit"],
                       "status": (row.get("result") or {}).get("status"),
                       "no_traceback": row["no_traceback"], "has_result": row["has_result"]})
        print(f"{'PASS' if ok else 'FAIL'}  {name:<38} exit={row['exit']} result={row['has_result']}")
        if not ok:
            print(json.dumps(row, ensure_ascii=False, default=str)[:700])

    add("01_clean", execute(root, "01_clean"), expected=0)
    add("02_missing_spec", execute(root, "02_missing_spec", missing=True), expected=5)
    add("03_invalid_json", execute(root, "03_invalid_json", raw="{broken"), expected=5)
    add("04_array_spec", execute(root, "04_array_spec", raw="[1,2]"), expected=5)
    bad = copy.deepcopy(BASE); bad["section"] = "unknown_route"
    add("05_unknown_section", execute(root, "05_unknown_section", bad), expected=5)
    bad = copy.deepcopy(BASE); bad["section"] = ["paper_to_deck"]
    add("06_section_wrong_type", execute(root, "06_section_wrong_type", bad), expected=5)
    bad = copy.deepcopy(BASE); bad["slides"] = "two slides"
    add("07_slides_wrong_type", execute(root, "07_slides_wrong_type", bad), expected=5)
    bad = copy.deepcopy(BASE); bad["slides"][1]["bullets"] = "not-a-list"
    add("08_bullets_wrong_type", execute(root, "08_bullets_wrong_type", bad), expected=5)
    bad = copy.deepcopy(BASE); bad["spacing"] = "32/20"
    row = execute(root, "09_bad_spacing", bad)
    add("09_bad_spacing_honest_default", row,
        any("spacing" in x for x in row["result"]["limits"]), expected=0)
    bad = copy.deepcopy(BASE); bad["slides"] = []
    add("10_empty_deck", execute(root, "10_empty_deck", bad), expected=4)
    bad = copy.deepcopy(BASE)
    bad["output_contract"] = [{"field": "case_id"}, {"name": "custom"}, {"key": "missing"}]
    bad["custom"] = {"kept": True}
    row = execute(root, "11_contract_object_list", bad)
    add("11_contract_object_list", row,
        row["result"].get("custom") == {"kept": True} and row["result"].get("missing") is None,
        expected=0)
    bad = copy.deepcopy(BASE); bad["output_contract"] = 7
    row = execute(root, "12_contract_bad_shape", bad)
    add("12_contract_bad_shape", row,
        any("output_contract" in x for x in row["result"]["limits"]), expected=0)
    bad = copy.deepcopy(BASE); bad["slides"][1]["image"] = str(root / "ghost.png")
    add("13_missing_image", execute(root, "13_missing_image", bad), expected=4)
    bad = copy.deepcopy(BASE); bad["source_deck"] = str(root / "ghost.pptx")
    add("14_missing_source_deck", execute(root, "14_missing_source_deck", bad), expected=5)
    bad_source = root / "invalid-source.pptx"; bad_source.write_bytes(b"not an OPC package")
    bad = copy.deepcopy(BASE); bad["source_deck"] = str(bad_source)
    add("15_corrupt_source_deck", execute(root, "15_corrupt_source_deck", bad), expected=5)
    bad = copy.deepcopy(BASE); bad["template"] = {"file": str(root / "ghost.potx")}
    add("16_missing_template", execute(root, "16_missing_template", bad), expected=4)
    malformed = root / "malformed.pptx"
    with zipfile.ZipFile(malformed, "w") as z:
        z.writestr("ppt/presentation.xml", "<p:presentation")
    bad = copy.deepcopy(BASE); bad["template"] = {"file": str(malformed)}
    add("17_malformed_template_xml", execute(root, "17_malformed_template_xml", bad), expected=4)
    row = execute(root, "18_valid_case_contract", case={
        "case_id": "actual-case", "output_contract": {"case_id": "id", "deck_file": "pptx"}})
    add("18_valid_case_contract", row,
        row["result"].get("case_id") == "actual-case" and "deck_file" in row["result"], expected=0)
    row = execute(root, "19_malformed_case", case_raw="{bad")
    add("19_malformed_case_limit", row,
        any("case file" in x for x in row["result"]["limits"]), expected=0)
    bad = copy.deepcopy(BASE); bad["max_slides"] = "two"
    add("20_invalid_slide_budget", execute(root, "20_invalid_slide_budget", bad), expected=3)
    bad = copy.deepcopy(BASE); bad["max_slides"] = 1
    add("21_slide_budget_exceeded", execute(root, "21_slide_budget_exceeded", bad), expected=3)
    bad = copy.deepcopy(BASE); bad["slides"][1]["bullets"] = ["⚡🚀🔬 混合文本"]
    add("22_unicode_glyph_coverage", execute(root, "22_unicode_glyph_coverage", bad))
    bad = copy.deepcopy(BASE); bad["min_slides"] = 3
    add("23_minimum_slide_count", execute(root, "23_minimum_slide_count", bad), expected=3)
    bad = copy.deepcopy(BASE); bad["output_contract"] = {"status": "audit", "status_fake": "null"}
    row = execute(root, "24_audited_status_wins", bad)
    add("24_audited_status_wins", row, row["result"]["status"] == "clean", expected=0)

    # Real source-deck and real-template CLI runs, generated only in the temp root.
    import pptxgen as P
    source_spec = copy.deepcopy(BASE)
    P.write_deck([P.Slide(title="问题", notes="引入。"),
                  P.Slide(title="旧标题", bullets=[P.Bullet("n = 6"), P.Bullet("3 倍")],
                          notes="强调对照。")], root / "source.pptx",
                 spacing={"title": 32, "body": 20}, fonts=("Arial", "Microsoft YaHei"))
    bad = copy.deepcopy(BASE); bad["section"] = "deck_edit"; bad["source_deck"] = str(root / "source.pptx")
    bad["revisions"] = [{"n": 1, "instruction": "改题", "changes": [
        {"slide": 2, "before": "旧标题", "after": "速率提高 3 倍", "reason": "量化"}]}]
    add("25_real_source_edit", execute(root, "25_real_source_edit", bad), expected=0)
    P.write_deck([P.Slide(title="template")], root / "template.pptx",
                 spacing={"title": 32, "body": 20}, fonts=("Arial", "Microsoft YaHei"))
    bad = copy.deepcopy(BASE)
    bad["template"] = {"file": str(root / "template.pptx"), "name": "real", "layouts": ["blank"]}
    for slide in bad["slides"]:
        slide["layout"] = "blank"
    add("26_real_template_shell", execute(root, "26_real_template_shell", bad), expected=0)

    passed = sum(1 for x in checks if x["pass"])
    report = {"schema_version": "ppt-master-hostile/v1", "probes": checks,
              "totals": {"passed": passed, "of": len(checks)}, "temp_root": str(root)}
    (SCRIPTS / "report_hostile.json").write_text(json.dumps(report, ensure_ascii=False, indent=2),
                                                encoding="utf-8")
    print(f"\n{passed}/{len(checks)} probes pass")
    return 0 if passed == len(checks) else 1


if __name__ == "__main__":
    raise SystemExit(main())
