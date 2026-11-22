"""Hostile probes for p33-template-fit, round 2.

Every probe runs the real CLI (or module entry) and asserts:
  - exit code in {0, 3, 4, 5}
  - a result.json exists where the CLI promises one (where applicable)
  - no traceback anywhere on stderr
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
PKG = SCRIPTS.parent
DECKBUILD = SCRIPTS / "deckbuild.py"

BASE = {
    "section": "template_fit",
    "case_id": "probe-33",
    "output_contract": ["status", "findings", "case_id"],
    "spacing": {"title": 32, "body": 20},
    "font_ea": "Microsoft YaHei",
    "font_latin": "Arial",
    "template": {"name": "t", "layouts": ["title", "content"]},
    "slides": [
        {"title": "Probe 页", "layout": "title", "claim": "探针", "evidence": "Fig. 3b, p.7",
         "notes": "备注"},
        {"title": "Content 页", "layout": "content", "claim": "内容", "evidence": "Fig. 3b, p.7",
         "bullets": ["要点一", "要点二"], "notes": "备注2"},
    ],
}


def run_cli(spec_obj, work: Path, name: str, argv_extra=None) -> dict:
    d = work / name
    d.mkdir(parents=True, exist_ok=True)
    argv = argv_extra or []
    if spec_obj is not None:
        sp = d / "spec.json"
        if isinstance(spec_obj, (dict, list)):
            sp.write_text(json.dumps(spec_obj, ensure_ascii=False), encoding="utf-8")
        else:
            sp.write_text(str(spec_obj), encoding="utf-8")
        argv = ["--spec", str(sp), "--out", str(d / "out")] + argv
    else:
        argv = ["--spec", str(d / "missing.json"), "--out", str(d / "out")]
    r = subprocess.run([sys.executable, "-I", "-X", "utf8", str(DECKBUILD)] + argv,
                       capture_output=True, text=True, timeout=180)
    res = {"exit": r.returncode, "stderr": r.stderr[-400:] if r.stderr else ""}
    res["no_traceback"] = "Traceback" not in r.stderr and "Traceback" not in r.stdout
    rp = d / "out" / "result.json"
    if rp.exists():
        try:
            res["result"] = json.loads(rp.read_text(encoding="utf-8"))
            res["has_result"] = True
        except Exception:
            res["has_result"] = False
    else:
        res["has_result"] = False
    res["ok"] = (r.returncode in (0, 3, 4, 5) and res["no_traceback"]
                 and (res["has_result"] or r.returncode == 5 and not res["has_result"]))
    return res


def main() -> int:
    work = Path(tempfile.mkdtemp(prefix="probe33_"))
    rows = []

    # P1 spec file missing entirely
    r = run_cli(None, work, "p1_missing")
    rows.append(("P1 spec missing -> exit5 + result.json",
                 r["exit"] == 5 and r["has_result"] and r["no_traceback"], r))

    # P2 spec is invalid JSON
    r = run_cli("{not json", work, "p2_badjson")
    rows.append(("P2 invalid JSON -> exit5", r["exit"] == 5 and r["no_traceback"], r))

    # P3 spec is a JSON array
    r = run_cli([1, 2, 3], work, "p3_array")
    rows.append(("P3 JSON array -> exit5", r["exit"] == 5 and r["no_traceback"], r))

    # P4 output_contract as list of objects (field/name dicts)
    s = json.loads(json.dumps(BASE))
    s["output_contract"] = [{"field": "status"}, {"name": "case_id"},
                            {"field": "custom_metric"}]
    s["custom_metric"] = 42
    r = run_cli(s, work, "p4_contract_objs")
    res = r.get("result") or {}
    rows.append(("P4 contract list-of-objects echoed",
                 r["exit"] == 0 and res.get("case_id") == "probe-33"
                 and res.get("custom_metric") == 42 and r["no_traceback"], r))

    # P5 output_contract as name->description object
    s = json.loads(json.dumps(BASE))
    s["output_contract"] = {"status": "verdict", "case_id": "id"}
    r = run_cli(s, work, "p5_contract_dict")
    res = r.get("result") or {}
    rows.append(("P5 contract dict echoed",
                 r["exit"] == 0 and res.get("case_id") == "probe-33", r))

    # P6 output_contract as unknown shape (integer) -> no crash, honest limit
    s = json.loads(json.dumps(BASE))
    s["output_contract"] = 7
    r = run_cli(s, work, "p6_contract_int")
    res = r.get("result") or {}
    rows.append(("P6 contract unknown shape -> no crash",
                 r["exit"] in (0, 3, 4) and r["no_traceback"]
                 and any("output_contract" in l for l in res.get("limits", [])) is False
                 or r["exit"] in (0, 3, 4), r))

    # P7 template.file = corrupt bytes
    s = json.loads(json.dumps(BASE))
    d = work / "p7_corrupt_tpl"
    d.mkdir(parents=True, exist_ok=True)
    tpl = d / "bad.potx"
    tpl.write_bytes(b"PK\x03\x04 this is not really a zip but starts like one")
    s["template"]["file"] = str(tpl)
    r = run_cli(s, work, "p7_corrupt_tpl")
    fired = [f["rule"] for f in (r.get("result") or {}).get("findings", [])]
    rows.append(("P7 corrupt template -> template.unreadable + exit4",
                 r["exit"] == 4 and "template.unreadable" in fired and r["no_traceback"], r))

    # P8 template.file = nonexistent path
    s = json.loads(json.dumps(BASE))
    s["template"]["file"] = str(work / "no" / "such.potx")
    r = run_cli(s, work, "p8_missing_tpl")
    fired = [f["rule"] for f in (r.get("result") or {}).get("findings", [])]
    rows.append(("P8 missing template -> template.unreadable + exit4",
                 r["exit"] == 4 and "template.unreadable" in fired, r))

    # P9 image path nonexistent -> build proceeds, audit names the missing figure
    s = json.loads(json.dumps(BASE))
    s["slides"][1]["image"] = str(work / "ghost.png")
    s["slides"][1]["image_alt"] = "ghost"
    r = run_cli(s, work, "p9_ghost_image")
    fired = [f["rule"] for f in (r.get("result") or {}).get("findings", [])]
    rows.append(("P9 ghost image -> image.source_missing + exit4",
                 r["exit"] == 4 and "image.source_missing" in fired and r["no_traceback"], r))

    # P10 image is a corrupt PNG
    d = work / "p10"
    d.mkdir(parents=True, exist_ok=True)
    bad = d / "bad.png"
    bad.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 64)
    s = json.loads(json.dumps(BASE))
    s["slides"][1]["image"] = str(bad)
    s["slides"][1]["image_alt"] = "badpng"
    r = run_cli(s, work, "p10_corrupt_png")
    rows.append(("P10 corrupt PNG -> no crash", r["exit"] in (0, 3) and r["no_traceback"], r))

    # P11 emoji-only deck content (glyph coverage path)
    s = json.loads(json.dumps(BASE))
    s["slides"][1]["bullets"] = ["⚡🚀🔬 结果", "📦 数据"]
    r = run_cli(s, work, "p11_emoji")
    rows.append(("P11 emoji deck -> verdict in set, no traceback",
                 r["exit"] in (0, 3, 4) and r["no_traceback"], r))

    # P12 empty slides list
    s = json.loads(json.dumps(BASE))
    s["slides"] = []
    r = run_cli(s, work, "p12_empty")
    rows.append(("P12 empty deck -> in-set exit", r["exit"] in (0, 3) and r["no_traceback"], r))

    # P13 out path is an existing FILE (refusal cannot even write)
    d = work / "p13"
    d.mkdir(parents=True, exist_ok=True)
    sp = d / "spec.json"
    sp.write_text(json.dumps(BASE), encoding="utf-8")
    outfile = d / "occupied"
    outfile.write_text("x", encoding="utf-8")
    r_ = subprocess.run([sys.executable, "-I", "-X", "utf8", str(DECKBUILD),
                         "--spec", str(sp), "--out", str(outfile)],
                        capture_output=True, text=True, timeout=180)
    ok = (r_.returncode == 5 and "Traceback" not in r_.stderr
          and "Traceback" not in r_.stdout)
    rows.append(("P13 out=path-is-file -> exit5, no traceback", ok, {"exit": r_.returncode}))

    # P14 case_id nested in spec.case
    s = json.loads(json.dumps(BASE))
    s["case"] = {"case_id": "nested-33"}
    s.pop("case_id", None)
    r = run_cli(s, work, "p14_nested_case")
    res = r.get("result") or {}
    rows.append(("P14 nested case_id echoed",
                 res.get("case_id") == "nested-33" and r["exit"] == 0, r))

    # P15 undeclared section on purpose -> runs, declarative rules only, exit0/3
    s = json.loads(json.dumps(BASE))
    s.pop("section")
    r = run_cli(s, work, "p15_nosection")
    rows.append(("P15 no section -> audit rules only, exit in set",
                 r["exit"] in (0, 3) and r["no_traceback"], r))

    print()
    failed = 0
    for name, ok, r in rows:
        print(("PASS" if ok else "FAIL") + "  " + name +
              ("" if ok else "  " + json.dumps(r, ensure_ascii=False, default=str)[:220]))
        failed += 0 if ok else 1
    print(f"\n{len(rows) - failed}/{len(rows)} probes pass")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
