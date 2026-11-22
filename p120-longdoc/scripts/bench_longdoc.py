"""Benchmark for the thesis / long-document skill.

One scenario per rule, aligned to the scoring points this task states:

  outline chapters written, argument parts present -> outline_item_unwritten,
                                                      argument_element_missing
  front and back matter                            -> reference_section_missing,
                                                      figure_list_missing, appendix_missing
  terminology and symbol tables, consistency       -> terminology_missing,
                                                      symbol_table_missing, duplicate_definition
  claims bound to references                       -> claim_no_citation, citation_unknown,
                                                      citation_conclusion_mismatch
  no contradictions across chapters                -> conclusion_contradiction
  chapter-level change records                     -> no_chapter_changelog
  numbering and cross-references resolve           -> numbering_gap, dangling_crossref,
                                                      figure_numbering_gap, figure_ref_unknown

    python bench_longdoc.py
"""

from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import sections as S  # noqa: E402

CHAPTERS = [
    {"number": 1, "title": "intro", "outline_id": "O1", "argument_element": "question",
     "definitions": [{"term": "uptake rate", "text": "rate of uptake"}],
     "claims": [{"text": "coating raises uptake", "reference": "doe2020"}],
     "conclusions": [{"statement": "coating raises uptake rate", "direction": "increases"}],
     "changelog": ["v1 drafted"]},
    {"number": 2, "title": "methods", "outline_id": "O2", "argument_element": "method",
     "changelog": ["v1 drafted"]},
    {"number": 3, "title": "results", "outline_id": "O3", "argument_element": "result",
     "figure_refs": [1], "changelog": ["v1 drafted"]},
    {"number": 4, "title": "discussion", "outline_id": "O4", "argument_element": "discussion",
     "conclusions": [{"statement": "coating raises uptake rate", "direction": "increases"}],
     "changelog": ["v1 drafted"]},
    {"number": 5, "title": "limits", "outline_id": "O5", "argument_element": "limitation",
     "changelog": ["v1 drafted"]},
]

BASE = {
    "outline": [
        {"id": "O1", "title": "intro", "argument_element": "question"},
        {"id": "O2", "title": "methods", "argument_element": "method"},
        {"id": "O3", "title": "results", "argument_element": "result"},
        {"id": "O4", "title": "discussion", "argument_element": "discussion"},
        {"id": "O5", "title": "limits", "argument_element": "limitation"},
    ],
    "front_matter": {"toc": ["intro", "methods", "results", "discussion", "limits"],
                     "figure_list": ["Fig 1"], "reference_section": "yes", "appendix": "yes"},
    "terminology": [{"preferred": "uptake rate", "chapter": "1"}],
    "symbols": [{"symbol": "r", "meaning": "rate"}],
    "references": [{"key": "doe2020", "title": "coating raises uptake", "year": 2020,
                    "topic": "coating raises uptake"}],
    "figures": [{"number": 1, "caption": "uptake curves"}],
    "chapters": CHAPTERS,
}


def d(**over):
    s = copy.deepcopy(BASE)
    s.update(over)
    return s


def ch(index, **over):
    s = copy.deepcopy(BASE)
    s["chapters"] = copy.deepcopy(CHAPTERS)
    s["chapters"][index] = {**CHAPTERS[index], **over}
    return s


def front(**over):
    s = copy.deepcopy(BASE)
    s["front_matter"] = {**BASE["front_matter"], **over}
    return s


SCEN = [
    ("clean", lambda: (d(), [])),

    # outline versus written
    ("no_chapters", lambda: (d(chapters=[]), ["long.no_chapters"])),
    ("outline_unwritten",
     lambda: (d(chapters=CHAPTERS[:4]), ["long.outline_item_unwritten"])),
    ("chapter_not_in_outline", lambda: (ch(0, outline_id="O9"), ["long.chapter_not_in_outline"])),
    ("argument_element_missing",
     lambda: (d(chapters=CHAPTERS[:4], outline=BASE["outline"][:4]),
              ["long.argument_element_missing"])),

    # front and back matter
    ("reference_section_missing",
     lambda: (front(reference_section=""), ["long.reference_section_missing"])),
    ("figure_list_missing", lambda: (front(figure_list=[]), ["long.figure_list_missing"])),
    ("appendix_missing", lambda: (front(appendix=""), ["long.appendix_missing"])),

    # tables
    ("terminology_missing", lambda: (d(terminology=[]), ["long.terminology_missing"])),
    ("symbol_table_missing", lambda: (d(symbols=[]), ["long.symbol_table_missing"]),
     ),
    ("duplicate_definition",
     lambda: (d(chapters=[CHAPTERS[0],
                          {**CHAPTERS[1], "definitions": [{"term": "Uptake-Rate",
                                                           "text": "again"}]},
                          *CHAPTERS[2:]]),
              ["long.duplicate_definition"])),
    ("term_variant_declared",
     lambda: (d(terminology=[{"preferred": "uptake rate", "variants": ["uptake"],
                              "chapter": "1"}]),
              ["long.term_variant_declared"])),

    # claims and references
    ("claim_no_citation",
     lambda: (ch(0, claims=[{"text": "coating raises uptake"}]), ["long.claim_no_citation"])),
    ("citation_unknown",
     lambda: (ch(0, claims=[{"text": "x", "reference": "roe2021"}]), ["long.citation_unknown"])),
    ("citation_conclusion_mismatch",
     lambda: (ch(0, claims=[{"text": "lipid rafts control endocytosis in neurons",
                             "reference": "doe2020"}]),
              ["long.citation_conclusion_mismatch"])),

    # contradictions
    ("conclusion_contradiction",
     lambda: (ch(3, conclusions=[{"statement": "coating raises uptake rate",
                                  "direction": "decreases"}]),
              ["long.conclusion_contradiction"])),

    # numbering and cross-references
    ("numbering_gap",
     lambda: (d(chapters=[CHAPTERS[0], {**CHAPTERS[1], "number": 3}]), ["long.numbering_gap"])),
    ("dangling_crossref", lambda: (ch(0, crossrefs=[9]), ["long.dangling_crossref"])),
    ("figure_numbering_gap",
     lambda: (d(figures=[{"number": 1}, {"number": 3}]), ["long.figure_numbering_gap"])),
    ("figure_ref_unknown", lambda: (ch(2, figure_refs=[9]), ["long.figure_ref_unknown"])),

    # toc and change records
    ("toc_incomplete", lambda: (front(toc=["intro", "methods"]), ["long.toc_incomplete"])),
    ("no_chapter_changelog", lambda: (ch(1, changelog=[]), ["long.no_chapter_changelog"])),    ("change_no_reason", lambda: (d(chapters=[
        {**BASE["chapters"][0],
         "changelog": [{"what": "redefined uptake rate", "why": "", "term": "uptake rate"}]},
        BASE["chapters"][1]]), ["long.change_no_reason"])),
    ("change_impact_untraced", lambda: (d(chapters=[
        {**BASE["chapters"][0],
         "definitions": [{"term": "uptake rate", "text": "rate of uptake"}],
         "changelog": [{"what": "redefined uptake rate", "why": "align with data", "term": "uptake rate"}]},
        {**BASE["chapters"][1],
         "definitions": [{"term": "uptake rate", "text": "rate again"}],
         "changelog": BASE["chapters"][1].get("changelog", [])}]),
        ["long.change_impact_untraced"])),
    ("word_budget_off", lambda: (d(outline=[
        {**BASE["outline"][0], "word_budget": 10000},
        *BASE["outline"][1:]],
        chapters=[{**BASE["chapters"][0], "word_count": 1000}, *BASE["chapters"][1:]]),
        ["long.word_budget_off"])),
    ("fp_change_ok", lambda: (d(chapters=[
        {**BASE["chapters"][0],
         "changelog": [{"what": "clarified wording", "why": "reviewer 2", "impact": []}]},
        *BASE["chapters"][1:]]), [])),
    ("fp_word_budget_ok", lambda: (d(outline=[
        {**BASE["outline"][0], "word_budget": 2000},
        *BASE["outline"][1:]],
        chapters=[{**BASE["chapters"][0], "word_count": 1800}, *BASE["chapters"][1:]]), [])),

    # --- reference metadata -------------------------------------------------
    ("reference_metadata_incomplete",
     lambda: (d(references=[{"key": "doe2020", "title": "coating raises uptake",
                              "topic": "coating raises uptake"}]),
              ["long.reference_metadata_incomplete"])),
    ("fp_reference_complete",
     lambda: (d(references=[{"key": "doe2020", "title": "coating raises uptake", "year": 2020,
                              "topic": "coating raises uptake"}]), [])),

    # --- conclusions carry a direction --------------------------------------
    ("conclusion_without_direction",
     lambda: (ch(0, conclusions=[{"statement": "coating raises uptake rate"}]),
              ["long.conclusion_without_direction"])),
    ("fp_conclusion_with_direction",
     lambda: (ch(0, conclusions=[{"statement": "coating raises uptake rate",
                                  "direction": "increases"}]), [])),

    # --- a declared variant actually used in a chapter body ------------------
    ("term_variant_used",
     lambda: (d(terminology=[{"preferred": "uptake rate", "variants": ["absorption speed"],
                              "chapter": "1"}],
                chapters=[{**CHAPTERS[0], "text": "The absorption speed rises with the coating."},
                          *CHAPTERS[1:]]),
              ["long.term_variant_used", "long.term_variant_declared"])),
    ("fp_term_variant_unused",
     lambda: (d(terminology=[{"preferred": "uptake rate", "variants": ["absorption speed"],
                              "chapter": "1"}], chapters=CHAPTERS),
              ["long.term_variant_declared"])),

    # --- tables: numbering and references ------------------------------------
    ("table_numbering_gap",
     lambda: (d(tables=[{"number": 1}, {"number": 3}]), ["long.table_numbering_gap"])),
    ("table_ref_unknown",
     lambda: (d(tables=[{"number": 1}],
                chapters=[{**CHAPTERS[0], "table_refs": [9]}, *CHAPTERS[1:]]),
              ["long.table_ref_unknown"])),
    ("fp_table_ok",
     lambda: (d(tables=[{"number": 1}],
                chapters=[{**CHAPTERS[0], "table_refs": [1]}, *CHAPTERS[1:]]), [])),

    # --- TOC entries that match no chapter -----------------------------------
    ("toc_entry_unknown",
     lambda: (front(toc=["intro", "methods", "结果"]),
              ["long.toc_entry_unknown", "long.toc_incomplete"])),
    ("fp_toc_exact",
     lambda: (front(toc=["intro", "methods", "results", "discussion", "limits"]), [])),

    # --- evidence plan (opt-in track) ----------------------------------------
    ("evidence_plan_missing",
     lambda: (d(track_consistency=True, chapters=[
         {**BASE["chapters"][0], "answers": "whether the coating raises uptake",
          "authorship_declared": True, "evidence": "doe2020"},
         {**BASE["chapters"][1], "answers": "how samples were prepared",
          "authorship_declared": True},
         {**BASE["chapters"][2], "answers": "what the measurements show",
          "authorship_declared": True, "evidence": "Fig 1"},
         *[{**c, "answers": "limits of the evidence", "authorship_declared": True,
            "evidence": "chapter 3 data"} for c in BASE["chapters"][3:]]]),
              ["long.evidence_plan_missing"])),
    ("fp_track_complete",
     lambda: (d(track_consistency=True, chapters=[
         {**c, "answers": f"chapter {c.get('number')} question",
          "authorship_declared": True, "evidence": "sec 2 data"}
         for c in BASE["chapters"]]), [])),
]


def main() -> int:
    rows = []
    for name, builder in SCEN:
        spec, expect = builder()
        findings, status, counts = S.run(spec, "longdoc")
        fired = {f["rule"] for f in findings}
        missing = [r for r in expect if r not in fired]
        spurious = [] if expect else [f["rule"] for f in findings]
        ok = not missing and not spurious
        rows.append({"scenario": name, "expected": expect, "fired": sorted(fired),
                     "missing": missing, "spurious": spurious, "pass": ok,
                     "status": status})
        print(f"{'PASS' if ok else 'FAIL'}  {name:<30} missing={missing} spurious={spurious}")

    passed = sum(1 for r in rows if r["pass"])
    report = {"schema_version": "longdoc-bench/v1", "scenarios": rows,
              "totals": {"passed": passed, "of": len(rows)},
              "note": ("One scenario per rule, aligned to the long-document scoring points. "
                       "Clean baselines must report nothing.")}
    (Path(__file__).resolve().parent / "report_longdoc.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n{passed}/{len(rows)} pass")
    return 0 if passed == len(rows) else 1


if __name__ == "__main__":
    raise SystemExit(main())
