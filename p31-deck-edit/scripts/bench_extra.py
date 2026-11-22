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
EDIT = {"revisions": [{"n": 2, "instruction": "add the measured magnitude", "changes": [
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


# --- deck-edit additions: every defect carries its FP guards (Lesson 6) ---------
# The new record rules are declarative: a field the record never declares (the
# slide list, the deck summary, the delivered pointer) turns the corresponding
# check off, and each guard proves exactly that. A structural change that records
# no text pair at all, a deletion that keeps its snapshot, a single revision, a
# declared delivered pointer, new text that did land (on the slide or in the
# notes) and an old caller that passes no summary must all stay silent.

ITER = {"revisions": [
    {"n": 2, "instruction": "压缩到十分钟", "changes": [
        {"slide": 2, "before": "吸收速率明显提高", "after": "吸收速率提高 3 倍",
         "reason": "把模糊的程度词换成实测倍数"}]},
    {"n": 3, "instruction": "面向评审改写", "changes": [
        {"slide": 1, "before": "研究背景", "after": "涂层为何是瓶颈",
         "reason": "评审要的是问题，不是领域综述"}]},
], "slides": [{"title": "涂层为何是瓶颈"}, {"title": "吸收速率提高 3 倍"},
              {"title": "机制与限制"}],
 "delivered_revision": 2}


def c_edit_half_diff():
    s = copy.deepcopy(EDIT); s["revisions"][0]["changes"][0].pop("after")
    return s, "deck_edit", ["edit.change_half_diff"]


def c_edit_half_fp_structural():
    # A structural change legitimately records no text pair at all; only a change
    # that keeps exactly one side claims a diff and breaks it.
    s = copy.deepcopy(EDIT)
    s["revisions"][0]["changes"][0] = {"slide": 2, "reason": "图从左栏移到右栏"}
    return s, "deck_edit", []


def c_edit_out_of_range():
    s = copy.deepcopy(EDIT)
    s["slides"] = [{"title": "a"}, {"title": "b"}]
    s["revisions"][0]["changes"][0]["slide"] = 9
    return s, "deck_edit", ["edit.change_slide_out_of_range"]


def c_edit_range_fp_in_range():
    # A change naming the deck's last slide is the normal case, not a defect.
    s = copy.deepcopy(EDIT)
    s["slides"] = [{"title": "a"}, {"title": "b"}]
    return s, "deck_edit", []


def c_edit_delete_no_snapshot():
    s = copy.deepcopy(EDIT)
    s["revisions"][0]["changes"][0] = {"slide": 2, "action": "delete", "after": "",
                                       "reason": "删去与主线无关的背景段落"}
    return s, "deck_edit", ["edit.delete_without_snapshot"]


def c_edit_delete_fp_snapshot():
    # A deletion that keeps the removed text can be restored — that is the record
    # working as intended.
    s = copy.deepcopy(EDIT)
    s["revisions"][0]["changes"][0] = {"slide": 2, "action": "delete",
                                       "before": "与主线无关的背景段落", "after": "",
                                       "reason": "删去与主线无关的背景段落"}
    return s, "deck_edit", []


def c_edit_delivered_missing():
    s = copy.deepcopy(ITER); s.pop("delivered_revision")
    return s, "deck_edit", ["edit.delivered_revision_missing"]


def c_edit_delivered_fp_declared():
    # Two revisions with a valid delivered pointer: the history is shippable.
    s = copy.deepcopy(ITER)
    return s, "deck_edit", [], None


def c_edit_delivered_fp_single():
    # One revision is trivially the deliverable; no pointer is required.
    s = copy.deepcopy(EDIT)
    s["slides"] = [{"title": "a"}, {"title": "b"}]
    return s, "deck_edit", []


def c_edit_after_absent():
    s = copy.deepcopy(EDIT); s["slides"] = [{"title": "a"}, {"title": "b"}]
    ds = {"slides": [{"index": 1, "text": "a", "notes": ""},
                     {"index": 2, "text": "对照 12.4 a.u.", "notes": ""}]}
    return s, "deck_edit", ["edit.change_not_in_deck"], ds


def c_edit_after_fp_landed():
    # The record is the change that was made: the new text is in the slide.
    s = copy.deepcopy(EDIT); s["slides"] = [{"title": "a"}, {"title": "b"}]
    ds = {"slides": [{"index": 1, "text": "a", "notes": ""},
                     {"index": 2, "text": "Uptake rose 3-fold\n对照", "notes": ""}]}
    return s, "deck_edit", [], ds


def c_edit_after_fp_notes():
    # A change whose new text landed in the speaker notes is a legitimate record;
    # notes are a scored deliverable, not slide text.
    s = copy.deepcopy(EDIT); s["slides"] = [{"title": "a"}, {"title": "b"}]
    ds = {"slides": [{"index": 1, "text": "a", "notes": ""},
                     {"index": 2, "text": "对照", "notes": "Uptake rose 3-fold"}]}
    return s, "deck_edit", [], ds


def c_edit_after_fp_legacy_summary():
    # The old spacing-only summary carries no per-slide text: an old caller is
    # never punished for what it was never given.
    s = copy.deepcopy(EDIT); s["slides"] = [{"title": "a"}, {"title": "b"}]
    return s, "deck_edit", [], {"spacing": {"title": 32, "body": 20}}


SCEN = [("paper_ok", c_paper_ok), ("paper_unattributed", c_paper_unattributed),
        ("paper_no_caption", c_paper_no_caption), ("edit_ok", c_edit_ok),
        ("edit_no_reason", c_edit_no_reason), ("edit_noop", c_edit_noop),
        ("edit_half_diff", c_edit_half_diff),
        ("edit_half_fp_structural", c_edit_half_fp_structural),
        ("edit_out_of_range", c_edit_out_of_range),
        ("edit_range_fp_in_range", c_edit_range_fp_in_range),
        ("edit_delete_no_snapshot", c_edit_delete_no_snapshot),
        ("edit_delete_fp_snapshot", c_edit_delete_fp_snapshot),
        ("edit_delivered_missing", c_edit_delivered_missing),
        ("edit_delivered_fp_declared", c_edit_delivered_fp_declared),
        ("edit_delivered_fp_single", c_edit_delivered_fp_single),
        ("edit_after_absent", c_edit_after_absent),
        ("edit_after_fp_landed", c_edit_after_fp_landed),
        ("edit_after_fp_notes", c_edit_after_fp_notes),
        ("edit_after_fp_legacy", c_edit_after_fp_legacy_summary),
        ("talk_ok", c_talk_ok), ("talk_no_goal", c_talk_no_goal),
        ("talk_topic_claim", c_talk_topic_claim), ("talk_no_strength", c_talk_no_strength),
        ("talk_too_fast", c_talk_fast), ("tmpl_ok", c_tmpl_ok),
        ("tmpl_flat", c_tmpl_flat), ("tmpl_undeclared", c_tmpl_undeclared)]

def main() -> int:
    rows = []
    for name, b in SCEN:
        out = b()
        if len(out) == 3:
            spec, section, expect = out
            deck_summary = {"spacing": spec.get("spacing")} if section == "template_fit" else None
        else:
            spec, section, expect, deck_summary = out
            if deck_summary is None and section == "template_fit":
                deck_summary = {"spacing": spec.get("spacing")}
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
        print(f"{'PASS' if r['pass'] else 'FAIL'}  {r['scenario']:<24} missing={r['missing']} spurious={r['spurious']}")
    print(f"\n{passed}/{len(rows)} pass")
    return 0 if passed == len(rows) else 1

if __name__ == "__main__":
    raise SystemExit(main())
