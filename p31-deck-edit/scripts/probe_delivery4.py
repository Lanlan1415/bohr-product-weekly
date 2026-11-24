"""Hostile real-CLI probes for delivery contracts, exits and idempotency."""
from __future__ import annotations

import copy
import hashlib
import json
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS))
import pptxgen as P
import pnggen

CLI = SCRIPTS / "deckbuild.py"
ROOT = Path(tempfile.mkdtemp(prefix="p31_hostile4_"))
LOGO = ROOT / "logo.png"
canvas = pnggen.Canvas(120, 60)
canvas.rect_outline(2, 2, 117, 57, width=2)
canvas.save(LOGO)
BASE = {
    "section": "deck_edit", "case_id": "probe-p31",
    "output_contract": ["case_id", "status", "deck_file", "version_record", "custom", "missing"],
    "custom": {"kept": True},
    "spacing": {"title": 32, "body": 20}, "font_ea": "Microsoft YaHei", "font_latin": "Arial",
    "min_font_pt": 14, "require_notes": True, "available_evidence": ["Fig. 3b, p.7"],
    "style": {"footer": {"text": "probe", "page_numbers": True,
                         "logo": str(LOGO), "logo_alt": "probe logo"}},
    "slides": [
        {"title": "吸收速率是研究瓶颈", "claim": "速率是瓶颈", "evidence": "Fig. 3b, p.7", "notes": "引入问题。"},
        {"title": "涂层使速率提高 3 倍", "claim": "涂层提高速率", "evidence": "Fig. 3b, p.7",
         "bullets": ["n = 6", "对照 12.4 a.u."], "notes": "强调对照与边界。"},
    ],
}


def execute(name: str, payload=BASE, *, raw=None, missing=False, case=None, case_raw=None,
            case_id=None) -> dict:
    work = ROOT / name
    work.mkdir(parents=True, exist_ok=True)
    spec = work / "missing.json" if missing else work / "spec.json"
    if not missing:
        spec.write_text(raw if raw is not None else json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    argv = [sys.executable, "-I", "-X", "utf8", str(CLI),
            "--spec", str(spec), "--out", str(work / "out")]
    if case is not None or case_raw is not None:
        path = work / "case.json"
        path.write_text(case_raw if case_raw is not None else json.dumps(case, ensure_ascii=False), encoding="utf-8")
        argv += ["--case", str(path)]
    if case_id is not None:
        argv += ["--case-id", case_id]
    proc = subprocess.run(argv, capture_output=True, text=True, timeout=240)
    path = work / "out" / "result.json"
    try:
        result = json.loads(path.read_text(encoding="utf-8"))
        valid = isinstance(result, dict)
    except Exception:
        result, valid = None, False
    no_tb = "Traceback" not in proc.stdout + proc.stderr
    return {"name": name, "exit": proc.returncode, "result": result, "has_result": valid,
            "no_traceback": no_tb, "stdout": proc.stdout, "stderr": proc.stderr,
            "work": work, "base_ok": proc.returncode in (0, 3, 4, 5) and valid and no_tb}


def package_digest(path: Path) -> str:
    digest = hashlib.sha256()
    with zipfile.ZipFile(path) as z:
        for name in sorted(z.namelist()):
            digest.update(name.encode()); digest.update(z.read(name))
    return digest.hexdigest()


def main() -> int:
    rows = []

    def add(name: str, row: dict, expected=None, extra=None):
        ok = row["base_ok"]
        if expected is not None:
            ok = ok and row["exit"] == expected
        if extra:
            ok = ok and bool(extra(row))
        rows.append({"probe": name, "pass": ok, "exit": row["exit"],
                     "status": (row.get("result") or {}).get("status"),
                     "has_result": row["has_result"], "no_traceback": row["no_traceback"],
                     "stderr": row["stderr"][-240:]})
        print(f"{'PASS' if ok else 'FAIL'}  {name:<38} exit={row['exit']} result={row['has_result']}")
        if not ok:
            print(json.dumps({k: str(v)[:800] for k, v in row.items()}, ensure_ascii=False, default=str))

    first = execute("01_clean")
    add("01_clean_real_pptx", first, 0, lambda r: (r["work"] / "out/deck.pptx").stat().st_size > 1000)
    add("02_clean_repeat_idempotent", execute("02_clean_repeat"), 0,
        lambda r: package_digest(r["work"] / "out/deck.pptx") == package_digest(first["work"] / "out/deck.pptx"))
    add("03_missing_spec", execute("03_missing_spec", missing=True, case_id="kept-id"), 5,
        lambda r: r["result"].get("case_id") == "kept-id")
    add("04_invalid_json", execute("04_bad_json", raw="{broken"), 5)
    add("05_array_spec", execute("05_array_spec", raw="[1,2]"), 5)
    bad = copy.deepcopy(BASE); bad["section"] = "unknown"
    add("06_unknown_section", execute("06_unknown_section", bad), 5)
    bad = copy.deepcopy(BASE); bad["section"] = ["deck_edit"]
    add("07_section_wrong_type", execute("07_section_type", bad), 5)
    bad = copy.deepcopy(BASE); bad["slides"] = "two slides"
    add("08_slides_wrong_type", execute("08_slides_type", bad), 5)
    bad = copy.deepcopy(BASE); bad["slides"][1]["bullets"] = "not-a-list"
    add("09_bullets_wrong_type", execute("09_bullets_type", bad), 5)
    bad = copy.deepcopy(BASE); bad["spacing"] = "32/20"
    add("10_bad_spacing_limit", execute("10_bad_spacing", bad), 0,
        lambda r: any("spacing" in x for x in r["result"]["limits"]))
    bad = copy.deepcopy(BASE); bad["slides"] = []
    add("11_empty_deck", execute("11_empty_deck", bad), 4)
    bad = copy.deepcopy(BASE); bad["output_contract"] = [{"field": "case_id"}, {"name": "custom"}, {"key": "missing"}]
    add("12_contract_object_list", execute("12_contract_objects", bad), 0,
        lambda r: r["result"].get("custom") == {"kept": True} and r["result"].get("missing") is None)
    bad = copy.deepcopy(BASE); bad["output_contract"] = 7
    add("13_contract_unknown_shape", execute("13_contract_bad", bad), 0,
        lambda r: any("output_contract" in x for x in r["result"]["limits"]))
    bad = copy.deepcopy(BASE); bad["slides"][1]["image"] = str(ROOT / "ghost.png")
    add("14_missing_image", execute("14_missing_image", bad), 4)
    bad = copy.deepcopy(BASE); bad["source_deck"] = str(ROOT / "ghost.pptx")
    add("15_missing_source", execute("15_missing_source", bad), 5)
    corrupt = ROOT / "corrupt.pptx"; corrupt.write_bytes(b"not an OPC package")
    bad = copy.deepcopy(BASE); bad["source_deck"] = str(corrupt)
    add("16_corrupt_source", execute("16_corrupt_source", bad), 5)
    bad = copy.deepcopy(BASE); bad["template"] = {"file": str(ROOT / "ghost.pptx")}
    add("17_missing_template", execute("17_missing_template", bad), 4)
    malformed = ROOT / "malformed.pptx"
    with zipfile.ZipFile(malformed, "w") as z:
        z.writestr("ppt/presentation.xml", "<broken")
    bad = copy.deepcopy(BASE); bad["template"] = {"file": str(malformed)}
    add("18_malformed_template", execute("18_malformed_template", bad), 4)
    add("19_case_contract_passthrough", execute("19_case_contract", case={
        "case_id": "actual-case", "output_contract": {"case_id": "id", "deck_file": "pptx", "custom": "obj"}}), 0,
        lambda r: r["result"].get("case_id") == "actual-case" and r["result"].get("custom") == {"kept": True})
    add("20_malformed_case_limit", execute("20_bad_case", case_raw="{bad"), 0,
        lambda r: any("case file" in x for x in r["result"]["limits"]))
    bad = copy.deepcopy(BASE); bad["style"] = "wrong"
    add("21_bad_style_limit", execute("21_bad_style", bad), 0,
        lambda r: any("style" in x for x in r["result"]["limits"]))
    bad = copy.deepcopy(BASE); bad["style"]["colors"] = {"text": "FFFFFF", "title": "FFFFFF", "background": "FFFFFF"}
    add("22_low_contrast_review", execute("22_low_contrast", bad), 3)
    bad = copy.deepcopy(BASE); bad["style"]["footer"]["logo"] = str(ROOT / "no-logo.png")
    add("23_missing_logo_blocked", execute("23_missing_logo", bad), 4)

    source_spec = copy.deepcopy(BASE)
    P.write_deck([P.Slide(title="吸收速率是研究瓶颈", notes="引入问题。"),
                  P.Slide(title="涂层使速率提高 3 倍", bullets=[P.Bullet("n = 6")], notes="强调对照与边界。")],
                 ROOT / "source.pptx", spacing={"title": 32, "body": 20},
                 fonts=("Arial", "Microsoft YaHei"), style=P.normalize_style(source_spec["style"]))
    bad = copy.deepcopy(BASE); bad["source_deck"] = str(ROOT / "source.pptx")
    bad["revisions"] = [{"n": 1, "instruction": "invalid geometry probe", "changes": [
        {"slide": 2, "action": "set_geometry", "shape": "Title", "reason": "probe",
         "geometry": {"x": 0, "y": 0, "w": 0, "h": 1}}]}]
    add("24_invalid_source_geometry", execute("24_bad_source_geometry", bad), 4)
    good = copy.deepcopy(BASE); good["revisions"] = [{"n": 1, "instruction": "legitimate structural edit", "changes": [
        {"slide": 2, "action": "set_style", "shape": "Title", "reason": "hierarchy", "font_size_pt": 34}]}]
    good["source_deck"] = str(ROOT / "source.pptx")
    add("25_real_source_style_edit", execute("25_real_source_style", good), 0)
    add("26_audited_status_wins", execute("26_status_wins", dict(BASE, status="pretend-clean")), 0,
        lambda r: r["result"].get("status") == "clean")
    add("27_refusal_keeps_full_case_contract", execute("27_refusal_contract", raw="{broken", case={
        "case_id": "refusal-case", "custom": "case-value",
        "output_contract": ["case_id", "status", "deck_file", "custom", "absent"]}), 5,
        lambda r: r["result"].get("case_id") == "refusal-case" and
                  r["result"].get("status") == "undetermined" and
                  r["result"].get("custom") == "case-value" and
                  "deck_file" in r["result"] and r["result"].get("deck_file") is None and
                  "absent" in r["result"] and r["result"].get("absent") is None)

    passed = sum(1 for x in rows if x["pass"])
    result = {"schema_version": "deck-delivery-hostile/v4", "probes": rows,
              "totals": {"passed": passed, "of": len(rows)}, "temp_root": str(ROOT)}
    (SCRIPTS / "report_probe_delivery4.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n{passed}/{len(rows)} probes pass\nartifacts: {ROOT}")
    return 0 if passed == len(rows) else 1


if __name__ == "__main__":
    raise SystemExit(main())
