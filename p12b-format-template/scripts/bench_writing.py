"""Benchmark for the writing-track sections: one planted defect per scenario."""
from __future__ import annotations
import copy, json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import writing as W

EV = {
    "draft": "吸收速率提高到 3 倍 [C1]。",
    "claims": [
        {"id": "C1",
         "claim": "\u6d82\u5c42\u4f7f\u5438\u6536\u901f\u7387\u63d0\u9ad8\u4e09\u500d",
         "strength": "strong",
         "strength_basis": "controlled experiment, n=6, replicated",
         "uncertainty": "",
         "sources": [{"key": "doe2020",
                      "quote": "The coating increased the uptake rate three-fold.",
                      "locator": "p.7"}]},
    ],
    "evidence": [
        {"key": "doe2020", "title": "Porous coatings for uptake", "year": 2020,
         "source_type": "primary",
         "text": "The coating increased the uptake rate three-fold."},
    ],
}

SRC = "涂层的吸收率提高到原来的3倍[1]。样品在25 °C下测量[2]。"
TR = {"output_mode": "plain", "source_text": SRC, "source_lang": "zh", "target_lang": "en",
      "target_text": "The coating improved uptake 3-fold [1]. Samples were measured at 25 °C [2]."}

RR = {
    "manuscript_version": "v2",
    "manuscript_text": "3.2 Results\nWe added a vehicle control (n=6).\n",
    "anchors": ["3.2 Results", "Appendix A"],
    "comments": [
        {"id": "C1", "text": "Add a vehicle control.", "type": "method", "severity": "major",
         "subrequirements": []},
        {"id": "C2", "text": "Justify the kinetic model.", "type": "method", "severity": "major",
         "subrequirements": []},
    ],
    "responses": [
        {"comment_id": "C1", "decision": "accept", "tone": "accept",
         "changes": [{"what": "added a vehicle control group",
                      "location": "3.2 Results",
                      "manuscript_version": "v2",
                      "added_text": "We added a vehicle control"}]},
        {"comment_id": "C2", "decision": "accept", "tone": "accept",
         "changes": [{"what": "added a derivation appendix",
                      "location": "Appendix A",
                      "manuscript_version": "v2"}]},
    ],
}

FT = {
    "text": "1 Introduction\nWe study it [a1].\n2 Methods\nWe use 3 mM [a2].\n"
            "3 Results\nIt works [a3].\n",
    "template": {
        "sections": ["introduction", "methods", "results"],
        "word_limit": 4000,
        "spec": {"font": "Times New Roman", "size_pt": 11, "line_spacing": 1.5,
                 "margin_mm": 25, "columns": 1, "caption_position": "below",
                 "reference_style": "APA", "heading_levels": 3, "export_format": "docx"},
        "checks": ["margins", "caption_position", "reference_style"],
    },
    "headings": [
        {"level": 1, "number": "1", "text": "Introduction", "style": "Heading 1"},
        {"level": 1, "number": "2", "text": "Methods", "style": "Heading 1"},
        {"level": 1, "number": "3", "text": "Results", "style": "Heading 1"},
    ],
    "input_units": {"figures": 2, "tables": 1, "equations": 3, "footnotes": 4},
    "output_units": {"figures": 2, "tables": 1, "equations": 3, "footnotes": 4},
    "conversion_steps": ["open in Word", "apply template styles", "export to docx"],
    "export": {"format": "docx", "font_embedded": True, "page_size_measured": True,
               "toc_refreshed": True, "editable": True},
    "checks_done": ["margins", "caption_position", "reference_style"],
    "references": [{"key": "a1"}, {"key": "a2"}, {"key": "a3"}],
}


def d(base, **kw):
    """Shallow-copy a baseline and override keys. Present once, used by every case."""
    out = copy.deepcopy(base)
    out.update(kw)
    return out


S = [
 ("ev_clean",        "evidence_writing", lambda: (copy.deepcopy(EV), [])),
 ("ev_uncited",      "evidence_writing", lambda: (d(EV, claims=[{**EV["claims"][0], "sources": []}]), ["ew.claim_no_support"])),
 ("ev_unknown",      "evidence_writing", lambda: (d(EV, claims=[{**EV["claims"][0], "sources": [{"key": "ghost2019", "quote": "x", "locator": "p.1"}]}]), ["ew.source_not_in_table"])),
 ("ev_no_set",       "evidence_writing", lambda: (d(EV, evidence=[]), ["ew.evidence_table_missing"])),
 ("tr_clean",        "translation",      lambda: (copy.deepcopy(TR), [])),
 ("tr_dropped_num",  "translation",      lambda: (d(TR, target_text="The coating improved uptake [1]. Samples were measured at 25 °C [2]."), ["xlate.invariant_broken"])),
 ("tr_unit_changed", "translation",      lambda: (d(TR, target_text="The coating improved uptake 3-fold [1]. Samples were measured at 25 °F [2]."), ["xlate.invariant_broken", "xlate.invariant_added"])),
 ("tr_residue",      "translation",      lambda: (d(TR, target_text="The coating 涂层 improved uptake 3-fold [1]. Samples were measured at 25 °C [2]."), ["xlate.untranslated_residue"])),
 ("tr_missing_side", "translation",      lambda: (d(TR, target_text=""), ["xlate.missing_side"])),
 ("rr_clean",        "review_response",  lambda: (copy.deepcopy(RR), [])),
 ("rr_unanswered",   "review_response",  lambda: (d(RR, responses=RR["responses"][:1]), ["resp.comment_unanswered"])),
 ("rr_no_reason",    "review_response",  lambda: (d(RR, responses=[
     {"comment_id": "C1", "decision": "reject", "tone": "polite_rebuttal"},
     RR["responses"][1]]), ["resp.rebuttal_without_reason"])),
 ("rr_unlocated",    "review_response",  lambda: (d(RR, responses=[
     {"comment_id": "C1", "decision": "accept", "tone": "accept",
      "changes": [{"what": "fixed", "manuscript_version": "v2"}]},
     RR["responses"][1]]), ["resp.change_unlocatable"])),
 ("ft_clean",        "format_template",  lambda: (copy.deepcopy(FT), [])),
 ("ft_missing_sec",  "format_template",  lambda: (d(FT, text="1 Introduction\nWe study it [a1].\n2 Methods\nWe use 3 mM [a2].\n"), ["fmt.section_missing"])),
 ("ft_order",        "format_template",  lambda: (d(FT, text="1 Methods\nWe use 3 mM [a2].\n2 Introduction\nIt works [a1].\n3 Results\nOk [a3].\n"), ["fmt.section_order"])),
 ("ft_heading_skip", "format_template",  lambda: (d(FT, headings=[
     {"level": 1, "number": "1", "text": "Introduction", "style": "Heading 1"},
     {"level": 3, "number": "1.1.1", "text": "Deep sub", "style": "Heading 3"},
     {"level": 1, "number": "2", "text": "Methods", "style": "Heading 1"},
     {"level": 1, "number": "3", "text": "Results", "style": "Heading 1"}]),
     ["fmt.heading_level_skip"])),
 ("ft_word_limit",   "format_template",  lambda: (d(FT, template={**FT["template"], "word_limit": 5}), ["fmt.word_limit_exceeded"])),
 ("ft_cite_ghost",   "format_template",  lambda: (d(FT, text="1 Introduction\nWe study it [a9].\n2 Methods\nWe use 3 mM [a2].\n3 Results\nIt works [a3].\n"), ["fmt.citation_not_in_reference_list"])),
 ("ft_ref_uncited",  "format_template",  lambda: (d(FT, references=[{"key": "a1"}, {"key": "a2"}, {"key": "a3"}, {"key": "a4"}]), ["fmt.reference_never_cited"])),
]


def main() -> int:
    rows = []
    for name, section, builder in S:
        spec, expect = builder()
        findings, status, counts = W.run(spec, section)
        fired = {f["rule"] for f in findings}
        missing = [r for r in expect if r not in fired]
        spurious = [] if expect else [f["rule"] for f in findings if f["severity"] in ("high", "medium")]
        ok = not missing and not spurious
        rows.append({"scenario": name, "section": section, "expected": expect,
                     "fired": sorted(fired), "missing": missing, "spurious": spurious,
                     "status": status, "pass": ok})
        print(f"{'PASS' if ok else 'FAIL'}  {name:<17}{section:<17} missing={missing} spurious={spurious}")
    passed = sum(1 for r in rows if r["pass"])
    (Path(__file__).resolve().parent / "report_writing.json").write_text(
        json.dumps({"schema_version": "writing-bench/v1", "scenarios": rows,
                    "totals": {"passed": passed, "of": len(rows)},
                    "note": "One planted defect per scenario; clean baselines must stay silent."},
                   ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n{passed}/{len(rows)} pass")
    return 0 if passed == len(rows) else 1


if __name__ == "__main__":
    raise SystemExit(main())
