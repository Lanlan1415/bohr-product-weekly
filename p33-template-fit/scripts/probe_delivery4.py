"""Hostile real-CLI probes for template adaptation and batch contracts."""
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
ROOT = Path(tempfile.mkdtemp(prefix="p33_hostile4_"))
LOGO = ROOT / "logo.png"
canvas = pnggen.Canvas(120, 60)
canvas.rect_outline(2, 2, 117, 57, width=2)
canvas.save(LOGO)
BASE = {
    "section": "template_fit", "case_id": "probe-p33",
    "output_contract": ["case_id", "status", "deck_file", "template_application", "custom", "missing"],
    "custom": {"kept": True},
    "spacing": {"title": 32, "body": 20}, "font_ea": "Microsoft YaHei", "font_latin": "Arial",
    "min_font_pt": 14, "require_notes": True, "available_evidence": ["Fig. 3b, p.7"],
    "template": {"name": "declared", "layouts": ["title", "content"]},
    "style": {"colors": {"background": "FFFFFF", "text": "1A1A1A", "title": "17365D"},
              "footer": {"text": "probe", "page_numbers": True,
                         "logo": str(LOGO), "logo_alt": "probe logo"}},
    "slides": [
        {"title": "吸收速率是研究瓶颈", "layout": "title", "claim": "速率是瓶颈",
         "evidence": "Fig. 3b, p.7", "notes": "引入问题。"},
        {"title": "涂层使速率提高约 2.52 倍", "layout": "content", "claim": "31.2 / 12.4 = 2.52",
         "evidence": "Fig. 3b, p.7", "bullets": ["n = 6", "对照 12.4 a.u."], "notes": "强调对照与边界。"},
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
    try:
        result = json.loads((work / "out" / "result.json").read_text(encoding="utf-8"))
        valid = isinstance(result, dict)
    except Exception:
        result, valid = None, False
    no_tb = "Traceback" not in proc.stdout + proc.stderr
    return {"name": name, "exit": proc.returncode, "result": result, "has_result": valid,
            "no_traceback": no_tb, "stdout": proc.stdout, "stderr": proc.stderr,
            "work": work, "base_ok": proc.returncode in (0, 3, 4, 5) and valid and no_tb}


def digest(path: Path) -> str:
    h = hashlib.sha256()
    with zipfile.ZipFile(path) as z:
        for name in sorted(z.namelist()):
            h.update(name.encode()); h.update(z.read(name))
    return h.hexdigest()


def main() -> int:
    rows = []

    def add(name: str, row: dict, expected=None, extra=None):
        ok = row["base_ok"] and (expected is None or row["exit"] == expected)
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
        lambda r: digest(r["work"] / "out/deck.pptx") == digest(first["work"] / "out/deck.pptx"))
    add("03_missing_spec", execute("03_missing_spec", missing=True, case_id="kept-id"), 5,
        lambda r: r["result"].get("case_id") == "kept-id")
    add("04_invalid_json", execute("04_bad_json", raw="{broken"), 5)
    add("05_array_spec", execute("05_array_spec", raw="[1,2]"), 5)
    bad = copy.deepcopy(BASE); bad["section"] = "unknown"
    add("06_unknown_section", execute("06_unknown_section", bad), 5)
    bad = copy.deepcopy(BASE); bad["section"] = ["template_fit"]
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
    add("14_missing_figure", execute("14_missing_figure", bad), 4)
    bad = copy.deepcopy(BASE); bad["source_deck"] = str(ROOT / "ghost.pptx")
    add("15_missing_source", execute("15_missing_source", bad), 5)
    corrupt = ROOT / "corrupt.pptx"; corrupt.write_bytes(b"not an OPC package")
    bad = copy.deepcopy(BASE); bad["source_deck"] = str(corrupt)
    add("16_corrupt_source", execute("16_corrupt_source", bad), 5)
    bad = copy.deepcopy(BASE); bad["template"]["file"] = str(ROOT / "ghost.pptx")
    add("17_missing_template", execute("17_missing_template", bad), 4)
    malformed = ROOT / "malformed.pptx"
    with zipfile.ZipFile(malformed, "w") as z:
        z.writestr("ppt/presentation.xml", "<broken")
    bad = copy.deepcopy(BASE); bad["template"]["file"] = str(malformed)
    add("18_malformed_template", execute("18_malformed_template", bad), 4)
    bad = copy.deepcopy(BASE); bad["slides"][1]["layout"] = "two-column"
    add("19_undeclared_layout", execute("19_undeclared_layout", bad), 4)
    bad = copy.deepcopy(BASE); bad["style"]["colors"]["text"] = "FFFFFF"
    add("20_low_contrast_review", execute("20_low_contrast", bad), 3)
    bad = copy.deepcopy(BASE); bad["style"]["footer"]["logo"] = str(ROOT / "no-logo.png")
    add("21_missing_logo_blocked", execute("21_missing_logo", bad), 4)
    add("22_case_contract_passthrough", execute("22_case_contract", case={
        "case_id": "actual-case", "output_contract": {"case_id": "id", "deck_file": "pptx", "custom": "obj"}}), 0,
        lambda r: r["result"].get("case_id") == "actual-case" and r["result"].get("custom") == {"kept": True})
    add("23_malformed_case_limit", execute("23_bad_case", case_raw="{bad"), 0,
        lambda r: any("case file" in x for x in r["result"]["limits"]))
    add("24_refusal_keeps_contract", execute("24_refusal_contract", raw="{broken", case={
        "case_id": "refusal-case", "custom": "case-value",
        "output_contract": ["case_id", "status", "deck_file", "custom", "absent"]}), 5,
        lambda r: r["result"].get("case_id") == "refusal-case" and
                  r["result"].get("status") == "undetermined" and
                  r["result"].get("custom") == "case-value" and
                  r["result"].get("deck_file") is None and
                  "absent" in r["result"] and r["result"]["absent"] is None)

    # Real source batch through the external CLI, not a direct helper call.
    source = ROOT / "source.pptx"
    P.write_deck([P.Slide(title="吸收速率是研究瓶颈", layout="title", notes="引入问题。"),
                  P.Slide(title="涂层使速率提高约 2.52 倍",
                          bullets=[P.Bullet("n = 6"), P.Bullet("对照 12.4 a.u.")], notes="强调对照与边界。")],
                 source, spacing={"title": 32, "body": 20}, fonts=("Arial", "Microsoft YaHei"),
                 style=P.normalize_style(BASE["style"]))
    good = copy.deepcopy(BASE); good["source_deck"] = str(source); good["batch_format"] = {
        "title_style": {"font_size_pt": 30}, "body_style": {"font_size_pt": 18}}
    add("25_real_source_batch", execute("25_real_source_batch", good), 0)

    from bench_delivery4 import native_template
    template = native_template("cli-native")
    good = copy.deepcopy(BASE); good["template"].update({"file": str(template), "name": "cli-native"})
    good["require_title_placeholder"] = True
    good.pop("batch_format", None); good.pop("source_deck", None)
    add("26_real_native_template", execute("26_real_native_template", good), 0,
        lambda r: r["result"].get("template_application", {}).get("applied") is True)
    add("27_audited_status_wins", execute("27_status_wins", dict(BASE, status="pretend-clean")), 0,
        lambda r: r["result"].get("status") == "clean")

    passed = sum(1 for x in rows if x["pass"])
    result = {"schema_version": "template-delivery-hostile/v4", "probes": rows,
              "totals": {"passed": passed, "of": len(rows)}, "temp_root": str(ROOT)}
    (SCRIPTS / "report_probe_delivery4.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n{passed}/{len(rows)} probes pass\nartifacts: {ROOT}")
    return 0 if passed == len(rows) else 1


if __name__ == "__main__":
    raise SystemExit(main())
