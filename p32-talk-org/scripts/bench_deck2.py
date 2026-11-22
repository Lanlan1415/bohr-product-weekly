"""Benchmark for the polished talk-organisation skill.

Covers the organisation rules (a stated objective, an audience, one assertion per slide
with an evidence-strength label, a defensible pace, a strength label the reader can
rank, a narrative arc with no uncovered beat, prepared answers when the talk demands
them, and a declared figure that actually exists), Chinese text measurement, and the
three things added in the earlier polish pass: the declared typeface must exist, the
text must have glyphs, and two builds must produce the same deck.

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

OUT = Path(__file__).resolve().parent / "_run_org2"

BASE = {
    "section": "talk_org",
    "min_font_pt": 14,
    "max_bullets_per_slide": 5,
    "require_notes": True,
    "spacing": {"title": 32, "body": 20},
    "font_ea": "Microsoft YaHei",
    "font_latin": "Arial",
    "available_evidence": ["Fig. 3b, p.7"],
    "goal": {"objective": "让评审认可方法的新颖性",
             "audience": "具备表面化学背景的评审",
             "minutes": 6},
    "slides": [
        {"title": "吸收速率是瓶颈", "claim": "瓶颈在于表面积", "strength": "moderate",
         "evidence": "Fig. 3b, p.7", "notes": "先立瓶颈，再给方法。"},
        {"title": "多孔涂层使速率提高 3 倍", "claim": "涂层使吸收速率提高三倍", "strength": "strong",
         "evidence": "Fig. 3b, p.7",
         "bullets": ["对照组 12.4 a.u.", "涂层组 31.2 a.u.", "每组 n = 6"],
         "notes": "核心结果；强调速率而非终点。"},
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


def scen_goal_missing():
    s = d()
    s["goal"] = {"audience": "评审", "minutes": 6}
    return s, ["org.goal_missing"]


def scen_audience_missing():
    s = d()
    s["goal"] = {"objective": "让评审认可新颖性", "minutes": 6}
    return s, ["org.audience_missing"]


def scen_claim_is_topic():
    s = d()
    s["slides"] = copy.deepcopy(BASE["slides"])
    s["slides"][1]["claim"] = "方法概述"
    return s, ["org.claim_is_topic"]


def scen_strength_missing():
    s = d()
    s["slides"] = copy.deepcopy(BASE["slides"])
    s["slides"][0].pop("strength")
    return s, ["org.evidence_strength_missing"]


def scen_pace_too_fast():
    return d(goal={"objective": "让评审认可新颖性", "audience": "评审", "minutes": 1}), ["org.pace_too_fast"]


def scen_overflow_cjk():
    """Chinese bullets must be measured with CJK line breaking, not as one line."""
    s = d(spacing={"title": 32, "body": 44})
    s["slides"] = copy.deepcopy(BASE["slides"])
    s["slides"][1]["bullets"] = ["这是一段特意写得很长的中文正文，用来确认换行后的文本高度会"
                                 "超出文本框，而不是被当成一行来估算。"] * 5
    return s, ["text.overflow"]


def scen_pace_too_slow():
    """Over four minutes per slide: the deck is thinner than the talk."""
    return d(goal={"objective": "让合作者理解进度风险", "audience": "课题组",
                   "minutes": 12}), ["org.pace_too_slow"]


def scen_strength_unknown():
    """A strength label outside the declared vocabulary cannot be ranked."""
    s = d()
    s["slides"] = copy.deepcopy(BASE["slides"])
    s["slides"][0]["strength"] = "非常确凿"
    return s, ["org.strength_unknown"]


def scen_strength_scale_ok():
    """A spec-declared vocabulary is honoured: 足够确凿 in the widened scale stays silent."""
    s = scen_strength_unknown()[0]
    s["strength_scale"] = ["strong", "moderate", "weak", "非常确凿"]
    return s, []


def scen_narrative_incomplete():
    """A declared narrative beat no slide carries is a hole in the talk."""
    s = d(narrative=["question", "method", "result", "limit"])
    s["slides"] = copy.deepcopy(BASE["slides"])
    s["slides"][0]["role"] = "question"
    s["slides"][1]["role"] = "result"
    return s, ["org.narrative_incomplete"]


def scen_narrative_complete():
    """Same arc fully covered: the rule must not fire."""
    s = d(narrative=["question", "result"])
    s["slides"] = copy.deepcopy(BASE["slides"])
    s["slides"][0]["role"] = "question"
    s["slides"][1]["role"] = "result"
    return s, []


def scen_role_undeclared():
    """A slide on a role the arc does not name sits outside the planned path."""
    s = d(narrative=["question", "result"])
    s["slides"] = copy.deepcopy(BASE["slides"])
    s["slides"][0]["role"] = "question"
    s["slides"][1]["role"] = "punchline"
    return s, ["org.role_undeclared"]


def scen_qa_prep_missing():
    """A talk that demands prepared answers but records none."""
    return d(require_qa_prep=True), ["org.qa_prep_missing"]


def scen_qa_prep_ok():
    """Prepared questions with answer pages satisfy the demand and stay silent."""
    s = d(require_qa_prep=True,
          qa_prep=[{"question": "对照组的涂层厚度如何保证一致？", "answer_slide": 2},
                   {"question": "速率提高是热效应还是结构效应？", "answer": "见 Fig. S4 对照"}])
    return s, []


def scen_empty_deck():
    """A spec with no slides is blocked, not a clean empty package."""
    s = d()
    s["slides"] = []
    return s, ["deck.no_slides"]


def scen_image_missing():
    """A declared figure the filesystem does not have is lost content, named up front."""
    s = d()
    s["slides"] = copy.deepcopy(BASE["slides"])
    s["slides"][1]["image"] = "no_such_figure_9f2.png"
    return s, ["image.file_missing"]


SCEN = [
    ("clean", scen_clean),
    ("goal_missing", scen_goal_missing),
    ("audience_missing", scen_audience_missing),
    ("claim_is_topic", scen_claim_is_topic),
    ("strength_missing", scen_strength_missing),
    ("pace_too_fast", scen_pace_too_fast),
    ("pace_too_slow", scen_pace_too_slow),
    ("overflow_cjk", scen_overflow_cjk),
    ("strength_unknown", scen_strength_unknown),
    ("strength_scale_ok", scen_strength_scale_ok),
    ("narrative_incomplete", scen_narrative_incomplete),
    ("narrative_complete", scen_narrative_complete),
    ("role_undeclared", scen_role_undeclared),
    ("qa_prep_missing", scen_qa_prep_missing),
    ("qa_prep_ok", scen_qa_prep_ok),
    ("empty_deck", scen_empty_deck),
    ("image_missing", scen_image_missing),
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
        print(f"{'PASS' if ok else 'FAIL'}  {name:<20} missing={missing} spurious={spurious}")

    for name, fn in (("font_missing", injected_font_missing),
                     ("missing_glyphs", injected_missing_glyphs),
                     ("nondeterministic", injected_nondeterministic)):
        r, rule = fn()
        ok = rule in {f["rule"] for f in r["findings"]}
        rows.append({"scenario": name, "expected": [rule],
                     "missing": [] if ok else [rule], "spurious": [],
                     "pass": ok, "injected": True, "status": r["status"]})
        print(f"{'PASS' if ok else 'FAIL'}  {name:<20} injected={ok}")

    passed = sum(1 for x in rows if x["pass"])
    report = {"schema_version": "talk-org-bench/v1", "scenarios": rows,
              "totals": {"passed": passed, "of": len(rows)},
              "note": ("Organisation rules (goal, audience, claim shape, strength vocabulary, "
                       "narrative coverage, QA preparation, pace, declared figures) plus CJK "
                       "measurement, declared-font existence, glyph coverage and build "
                       "determinism. Three scenarios inject a defect.")}
    (Path(__file__).resolve().parent / "report_deck2.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n{passed}/{len(rows)} pass")
    return 0 if passed == len(rows) else 1


if __name__ == "__main__":
    raise SystemExit(main())
