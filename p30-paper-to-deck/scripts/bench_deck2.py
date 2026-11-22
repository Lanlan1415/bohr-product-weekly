"""Benchmark for the polished paper-to-deck skill.

Covers the paper-mapping rules (a figure must name the paper object it came from, its
caption survives), Chinese text measurement, and the three things added in the polish
pass: the declared typeface must exist, the text must have glyphs, and two builds must
produce the same deck.

Three defects cannot be expressed in a spec — a missing typeface, a font without the
needed glyphs, and a non-reproducible build — so those inject them by patching.

    python bench_deck2.py
"""

from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import deckaudit  # noqa: E402
import deckbuild  # noqa: E402

OUT = Path(__file__).resolve().parent / "_run_p2d2"
OUT.mkdir(parents=True, exist_ok=True)

# The paper-mapping rules only apply to a slide that actually shows a figure, so the
# scenarios need a real image file rather than a path that does not exist.
FIG = OUT / "fig3b.png"
if not FIG.exists():
    from PIL import Image, ImageDraw
    _im = Image.new("RGB", (600, 400), "white")
    _d = ImageDraw.Draw(_im)
    _d.rectangle([40, 40, 560, 360], outline="black", width=2)
    _im.save(FIG)

BASE = {
    "section": "paper_to_deck",
    "min_font_pt": 14,
    "max_bullets_per_slide": 5,
    "require_notes": True,
    "spacing": {"title": 32, "body": 20},
    "font_ea": "Microsoft YaHei",
    "font_latin": "Arial",
    "available_evidence": ["Fig. 3b, p.7", "Table 1, p.6"],
    "slides": [
        {"title": "多孔涂层加速吸收", "layout": "title", "caption": "42 nm 涂层，速率提高 3 倍",
         "claim": "问题是吸收速率，不是终点", "evidence": "Fig. 3b, p.7",
         "notes": "引入问题；不读标题。"},
        {"title": "吸收速率提高 3 倍", "claim": "涂层使速率提高三倍",
         "evidence": "Fig. 3b, p.7", "caption": "Fig. 3b, p.7 — 对比的是速率",
         "bullets": ["对照组 12.4 a.u.", "涂层组 31.2 a.u.", "每组 n = 6"],
         "notes": "停顿；对比的是速率，不是终点。"},
    ],
}


def d(**over):
    s = copy.deepcopy(BASE)
    s.update(over)
    return s


def run(name: str, spec: dict) -> dict:
    p = OUT / name
    p.mkdir(parents=True, exist_ok=True)
    (p / "spec.json").write_text(json.dumps(spec, ensure_ascii=False), encoding="utf-8")
    return deckbuild.build_and_audit(p / "spec.json", p / "o")


def scen_clean():
    return d(), []


def scen_unattributed():
    """A slide carries a figure but names no paper object anywhere."""
    s = d()
    s["slides"] = copy.deepcopy(BASE["slides"])
    s["slides"][1]["image"] = str(FIG)
    s["slides"][1]["image_alt"] = "吸收速率对比"
    for k in ("caption", "evidence", "notes"):
        s["slides"][1][k] = ""
    return s, ["paper.figure_unattributed"]


def scen_caption_missing():
    s = d()
    s["slides"] = copy.deepcopy(BASE["slides"])
    s["slides"][1]["image"] = str(FIG)
    s["slides"][1]["image_alt"] = "吸收速率对比"
    s["slides"][1]["caption"] = ""
    return s, ["paper.caption_missing"]


def scen_evidence_unsupported():
    s = d()
    s["slides"] = copy.deepcopy(BASE["slides"])
    s["slides"][1]["evidence"] = "Fig. 9z, p.44"
    s["slides"][1]["caption"] = "Fig. 9z, p.44"
    return s, ["deck.evidence_unsupported"]


def scen_overflow_cjk():
    """Chinese bullets must be measured with CJK line breaking, not as one line."""
    s = d(spacing={"title": 32, "body": 44})
    s["slides"] = copy.deepcopy(BASE["slides"])
    s["slides"][1]["bullets"] = ["这是一段特意写得很长的中文正文，用来确认换行后的文本高度会"
                                 "超出文本框，而不是被当成一行来估算。"] * 5
    return s, ["text.overflow"]


def scen_notes_repeat_title():
    s = d()
    s["slides"] = copy.deepcopy(BASE["slides"])
    s["slides"][1]["notes"] = BASE["slides"][1]["title"]
    return s, ["deck.notes_repeat_title"]


SCEN = [
    ("clean", scen_clean),
    ("unattributed", scen_unattributed),
    ("caption_missing", scen_caption_missing),
    ("evidence_unsupported", scen_evidence_unsupported),
    ("overflow_cjk", scen_overflow_cjk),
    ("notes_repeat", scen_notes_repeat_title),
]


def injected_font_missing() -> tuple[dict, str]:
    saved = deckaudit._installed
    deckaudit._installed = lambda fam: fam.lower() != "fg-cjk-absent"
    try:
        r = run("font_missing", d(font_ea="FG-CJK-Absent"))
    finally:
        deckaudit._installed = saved
    return r, "font.declared_missing"


def injected_missing_glyphs() -> tuple[dict, str]:
    import fontsel
    saved = fontsel.resolve
    dj = fontsel._find(["DejaVuSans.ttf"])
    fontsel.resolve = lambda text="": fontsel.Resolved(
        family="DejaVu Sans", path=dj, missing=fontsel.coverage(dj, text))
    try:
        r = run("glyphs", d())
    finally:
        fontsel.resolve = saved
    return r, "export.missing_glyphs"


def injected_nondeterministic() -> tuple[dict, str]:
    saved = deckbuild.check_deterministic
    deckbuild.check_deterministic = lambda spec, out_dir: {
        "deterministic": False, "note": "injected", "detail": {"slides": 2}}
    try:
        r = run("nondet", d())
    finally:
        deckbuild.check_deterministic = saved
    return r, "repro.nondeterministic"


def main() -> int:
    rows = []
    for name, builder in SCEN:
        spec, expect = builder()
        r = run(name, spec)
        fired = {f["rule"] for f in r["findings"]}
        missing = [x for x in expect if x not in fired]
        spurious = [] if expect else [f["rule"] for f in r["findings"]]
        ok = not missing and not spurious
        rows.append({"scenario": name, "expected": expect, "fired": sorted(fired),
                     "missing": missing, "spurious": spurious, "pass": ok,
                     "status": r["status"]})
        print(f"{'PASS' if ok else 'FAIL'}  {name:<22} missing={missing} spurious={spurious}")

    for name, fn in (("font_missing", injected_font_missing),
                     ("missing_glyphs", injected_missing_glyphs),
                     ("nondeterministic", injected_nondeterministic)):
        r, rule = fn()
        ok = rule in {f["rule"] for f in r["findings"]}
        rows.append({"scenario": name, "expected": [rule],
                     "missing": [] if ok else [rule], "spurious": [],
                     "pass": ok, "injected": True, "status": r["status"]})
        print(f"{'PASS' if ok else 'FAIL'}  {name:<22} injected={ok}")

    passed = sum(1 for x in rows if x["pass"])
    report = {"schema_version": "deck-p2d-bench/v1", "scenarios": rows,
              "totals": {"passed": passed, "of": len(rows)},
              "note": ("Paper-mapping rules plus CJK measurement, declared-font existence, "
                       "glyph coverage and build determinism. Three scenarios inject a defect.")}
    (Path(__file__).resolve().parent / "report_deck2.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n{passed}/{len(rows)} pass")
    return 0 if passed == len(rows) else 1


if __name__ == "__main__":
    raise SystemExit(main())
