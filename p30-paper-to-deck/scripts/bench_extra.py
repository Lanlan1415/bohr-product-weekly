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

SCEN = [("paper_ok", c_paper_ok), ("paper_unattributed", c_paper_unattributed),
        ("paper_no_caption", c_paper_no_caption), ("edit_ok", c_edit_ok),
        ("edit_no_reason", c_edit_no_reason), ("edit_noop", c_edit_noop),
        ("talk_ok", c_talk_ok), ("talk_no_goal", c_talk_no_goal),
        ("talk_topic_claim", c_talk_topic_claim), ("talk_no_strength", c_talk_no_strength),
        ("talk_too_fast", c_talk_fast), ("tmpl_ok", c_tmpl_ok),
        ("tmpl_flat", c_tmpl_flat), ("tmpl_undeclared", c_tmpl_undeclared)]

def main() -> int:
    rows = []
    for name, b in SCEN:
        spec, section, expect = b()
        deck_summary = {"spacing": spec.get("spacing")} if section == "template_fit" else None
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
