"""Benchmark for the four skill-specific sections."""
from __future__ import annotations
import copy, json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import extra_rules as X

PAPER = {"slides": [
    {"title": "Question", "claim": "uptake is slow", "evidence": "Fig. 3b, p.7"},
    {"title": "Finding", "claim": "3x faster", "evidence": "Fig. 3b, p.7",
     "image": "f.png", "caption": "Fig. 3b, p.7"},
]}
EDIT = {"revisions": [{"n": 2, "changes": [
    {"slide": 2, "before": "Uptake rose", "after": "Uptake rose 3-fold", "reason": "add magnitude"}]}]}
TALK = {"goal": {"objective": "convince reviewers of novelty", "audience": "reviewers", "minutes": 12},
        "slides": [{"claim": "Coating raises uptake 3-fold", "strength": "strong"},
                   {"claim": "Mechanism is plausible", "strength": "moderate"}]}
TMPL = {"spacing": {"title": 32, "body": 20},
        "template": {"name": "conf-2026", "layouts": ["title", "content"]},
        "slides": [{"layout": "title"}, {"layout": "content"}]}


def c_paper_ok(): return copy.deepcopy(PAPER), "paper_to_deck", []
def c_paper_unattributed():
    s = copy.deepcopy(PAPER); s["slides"][1]["caption"] = ""; s["slides"][1]["evidence"] = ""
    return s, "paper_to_deck", ["paper.figure_unattributed"]
def c_paper_no_caption():
    s = copy.deepcopy(PAPER); s["slides"][1]["caption"] = ""
    return s, "paper_to_deck", ["paper.caption_missing"]
def c_edit_ok(): return copy.deepcopy(EDIT), "deck_edit", []
def c_edit_no_reason():
    s = copy.deepcopy(EDIT); s["revisions"][0]["changes"][0]["reason"] = ""
    return s, "deck_edit", ["edit.change_without_reason"]
def c_edit_noop():
    s = copy.deepcopy(EDIT); s["revisions"][0]["changes"][0]["after"] = "Uptake rose"
    return s, "deck_edit", ["edit.change_is_noop"]
def c_talk_ok(): return copy.deepcopy(TALK), "talk_org", []
def c_talk_no_goal():
    s = copy.deepcopy(TALK); s["goal"] = {"audience": "reviewers"}
    return s, "talk_org", ["org.goal_missing"]
def c_talk_topic_claim():
    s = copy.deepcopy(TALK); s["slides"][1]["claim"] = "Overview of mechanism"
    return s, "talk_org", ["org.claim_is_topic"]
def c_talk_no_strength():
    s = copy.deepcopy(TALK); s["slides"][0].pop("strength")
    return s, "talk_org", ["org.evidence_strength_missing"]
def c_talk_fast():
    s = copy.deepcopy(TALK); s["goal"]["minutes"] = 1
    return s, "talk_org", ["org.pace_too_fast"]
def c_tmpl_ok(): return copy.deepcopy(TMPL), "template_fit", []
def c_tmpl_flat():
    s = copy.deepcopy(TMPL); s["spacing"] = {"title": 22, "body": 20}
    return s, "template_fit", ["format.size_ladder_flat"]
def c_tmpl_undeclared():
    s = copy.deepcopy(TMPL); s["slides"][1]["layout"] = "two-column"
    return s, "template_fit", ["format.undeclared_layout"]


# --- template-fit additions: every defect carries its FP guards (Lesson 6) ------
# The new template-fit rules judge the written deck against the declared spec, so
# their fixtures hand over a deck summary in the shape deckbuild.deck_summary
# produces. A summary field that is absent turns the corresponding check off, and
# each guard proves exactly that: an off-theme body font, an undeclared font theme,
# a different declared layout, a missing template, a descriptive caption and an
# old spacing-only caller must all stay silent.

def _ds(spec, slides):
    return {"spacing": spec.get("spacing"), "slides": slides}


def c_tmpl_font_drift():
    s = copy.deepcopy(TMPL); s["font_ea"] = "Microsoft YaHei"; s["font_latin"] = "Arial"
    ds = _ds(s, [
        {"layout": "title", "title_fonts": ["Arial", "Microsoft YaHei"], "text": ""},
        {"layout": "content", "title_fonts": ["Times New Roman"], "text": ""}])
    return s, "template_fit", ["format.font_drift"], ds


def c_tmpl_font_drift_fp_body():
    # Body runs legitimately change face for code or emphasis; only titles must
    # stay on the declared theme.
    s = copy.deepcopy(TMPL); s["font_ea"] = "Microsoft YaHei"; s["font_latin"] = "Arial"
    ds = _ds(s, [
        {"layout": "title", "title_fonts": ["Arial", "Microsoft YaHei"], "text": ""},
        {"layout": "content", "title_fonts": ["Arial", "Microsoft YaHei"],
         "text": "the code listing is set in Consolas"}])
    return s, "template_fit", [], ds


def c_tmpl_font_drift_fp_undeclared():
    # No fonts declared: the theme is unknown, so nothing is compared.
    s = copy.deepcopy(TMPL)
    ds = _ds(s, [
        {"layout": "title", "title_fonts": ["Times New Roman"], "text": ""},
        {"layout": "content", "title_fonts": ["Times New Roman"], "text": ""}])
    return s, "template_fit", [], ds


def c_tmpl_title_drift():
    s = copy.deepcopy(TMPL)
    s["slides"] = [{"layout": "title"}, {"layout": "content"}, {"layout": "content"}]
    ds = _ds(s, [
        {"layout": "title", "title_geom": [822960, 2194560, 10583400, 1371600], "text": ""},
        {"layout": "content", "title_geom": [457200, 320040, 11274480, 914400], "text": ""},
        {"layout": "content", "title_geom": [457200, 685800, 11274480, 914400], "text": ""}])
    return s, "template_fit", ["format.title_drift"], ds


def c_tmpl_title_drift_fp_layouts():
    # Different declared layouts may legitimately place titles differently; only
    # slides sharing one layout are compared.
    s = copy.deepcopy(TMPL)
    s["template"]["layouts"] = ["title", "content", "section"]
    s["slides"] = [{"layout": "title"}, {"layout": "content"}, {"layout": "section"}]
    ds = _ds(s, [
        {"layout": "title", "title_geom": [822960, 2194560, 10583400, 1371600], "text": ""},
        {"layout": "content", "title_geom": [457200, 320040, 11274480, 914400], "text": ""},
        {"layout": "section", "title_geom": [457200, 685800, 11274480, 914400], "text": ""}])
    return s, "template_fit", [], ds


def c_tmpl_title_drift_fp_no_template():
    # No template declared: there is no layout contract to drift from.
    s = copy.deepcopy(TMPL); s.pop("template")
    s["slides"] = [{"layout": "content"}, {"layout": "content"}]
    ds = _ds(s, [
        {"layout": "content", "title_geom": [457200, 320040, 11274480, 914400], "text": ""},
        {"layout": "content", "title_geom": [457200, 685800, 11274480, 914400], "text": ""}])
    return s, "template_fit", [], ds


def c_tmpl_figure_mismatch():
    s = copy.deepcopy(TMPL)
    s["slides"][1] = {"layout": "content", "caption": "Fig. 4b 吸收曲线",
                      "evidence": "Fig. 3b, p.7"}
    return s, "template_fit", ["format.figure_mismatch"], None


def c_tmpl_figure_fp_descriptive():
    # A caption with no figure number is never compared against the locator.
    s = copy.deepcopy(TMPL)
    s["slides"][1] = {"layout": "content", "caption": "吸收速率对比曲线",
                      "evidence": "Fig. 3b, p.7"}
    return s, "template_fit", [], None


def c_tmpl_figure_fp_overlap():
    # A slide that legitimately compares two figures mentions the caption's figure
    # too, so the number sets intersect.
    s = copy.deepcopy(TMPL)
    s["slides"][1] = {"layout": "content", "caption": "Fig. 3b 与 Fig. 4 的对比",
                      "evidence": "Fig. 3b, p.7"}
    return s, "template_fit", [], None


def c_tmpl_figure_fp_cjk():
    # The Chinese and the Latin name of the same figure number agree.
    s = copy.deepcopy(TMPL)
    s["slides"][1] = {"layout": "content", "caption": "图 3 吸收速率",
                      "evidence": "Fig. 3b, p.7"}
    return s, "template_fit", [], None


DROPPED = {"layout": "content", "title": "结果", "caption": "Fig. 3b, p.7",
           "bullets": ["对照组 12.4 a.u.", "涂层组 31.2 a.u."]}


def c_tmpl_content_dropped():
    s = copy.deepcopy(TMPL); s["slides"][1] = copy.deepcopy(DROPPED)
    ds = _ds(s, [
        {"layout": "title", "text": "多孔涂层"},
        {"layout": "content", "text": "结果\n对照组 12.4 a.u."}])
    return s, "template_fit", ["format.content_dropped"], ds


def c_tmpl_content_fp_all_present():
    s = copy.deepcopy(TMPL); s["slides"][1] = copy.deepcopy(DROPPED)
    ds = _ds(s, [
        {"layout": "title", "text": "多孔涂层"},
        {"layout": "content",
         "text": "结果\n对照组 12.4 a.u.\n涂层组 31.2 a.u.\nFig. 3b, p.7"}])
    return s, "template_fit", [], ds


def c_tmpl_content_fp_legacy_summary():
    # The old spacing-only summary carries no per-slide text: an old caller is
    # never punished for what it was never given.
    s = copy.deepcopy(TMPL); s["slides"][1] = copy.deepcopy(DROPPED)
    return s, "template_fit", [], {"spacing": s.get("spacing")}


def c_tmpl_slide_dropped():
    # A declared slide that the written deck does not contain at all.
    s = copy.deepcopy(TMPL)
    s["slides"] = [{"layout": "title"}, {"layout": "content"}, {"layout": "content"}]
    ds = _ds(s, [
        {"layout": "title", "text": "多孔涂层"},
        {"layout": "content", "text": "结果"}])
    return s, "template_fit", ["format.content_dropped"], ds


SCEN = [("paper_ok", c_paper_ok), ("paper_unattributed", c_paper_unattributed),
        ("paper_no_caption", c_paper_no_caption), ("edit_ok", c_edit_ok),
        ("edit_no_reason", c_edit_no_reason), ("edit_noop", c_edit_noop),
        ("talk_ok", c_talk_ok), ("talk_no_goal", c_talk_no_goal),
        ("talk_topic_claim", c_talk_topic_claim), ("talk_no_strength", c_talk_no_strength),
        ("talk_too_fast", c_talk_fast), ("tmpl_ok", c_tmpl_ok),
        ("tmpl_flat", c_tmpl_flat), ("tmpl_undeclared", c_tmpl_undeclared),
        ("tmpl_font_drift", c_tmpl_font_drift),
        ("tmpl_font_fp_body", c_tmpl_font_drift_fp_body),
        ("tmpl_font_fp_undeclared", c_tmpl_font_drift_fp_undeclared),
        ("tmpl_title_drift", c_tmpl_title_drift),
        ("tmpl_drift_fp_layouts", c_tmpl_title_drift_fp_layouts),
        ("tmpl_drift_fp_no_template", c_tmpl_title_drift_fp_no_template),
        ("tmpl_figure_mismatch", c_tmpl_figure_mismatch),
        ("tmpl_figure_fp_descriptive", c_tmpl_figure_fp_descriptive),
        ("tmpl_figure_fp_overlap", c_tmpl_figure_fp_overlap),
        ("tmpl_figure_fp_cjk", c_tmpl_figure_fp_cjk),
        ("tmpl_content_dropped", c_tmpl_content_dropped),
        ("tmpl_content_fp_all_present", c_tmpl_content_fp_all_present),
        ("tmpl_content_fp_legacy", c_tmpl_content_fp_legacy_summary),
        ("tmpl_slide_dropped", c_tmpl_slide_dropped)]

def main() -> int:
    rows = []
    for name, b in SCEN:
        out = b()
        if len(out) == 3:
            spec, section, expect = out
            deck_summary = {"spacing": spec.get("spacing")} if section == "template_fit" else None
        else:
            spec, section, expect, deck_summary = out
        got = X.run(spec, section, deck_summary)
        fired = {f["rule"] for f in got}
        missing = [x for x in expect if x not in fired]
        spurious = [] if expect else [f["rule"] for f in got if f["severity"] in ("high", "medium")]
        rows.append({"scenario": name, "section": section, "expected": expect,
                     "fired": sorted(fired), "missing": missing, "spurious": spurious,
                     "pass": not missing and not spurious})
    passed = sum(1 for r in rows if r["pass"])
    (Path(__file__).resolve().parent / "report_extra.json").write_text(
        json.dumps({"schema_version": "extra-bench/v1", "scenarios": rows,
                    "totals": {"passed": passed, "of": len(rows)}}, ensure_ascii=False, indent=2),
        encoding="utf-8")
    for r in rows:
        print(f"{'PASS' if r['pass'] else 'FAIL'}  {r['scenario']:<20} missing={r['missing']} spurious={r['spurious']}")
    print(f"\n{passed}/{len(rows)} pass")
    return 0 if passed == len(rows) else 1

if __name__ == "__main__":
    raise SystemExit(main())
