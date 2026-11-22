"""Benchmark for the paper-draft skill.

One scenario per rule, aligned to the scoring points this task states:

  a real section draft, not an outline          -> draft_missing, sections_missing
  facts matching the materials                  -> value_not_in_materials, figure_caption_*
  claims tracing to a material AND a reference  -> uncited_claim, material_*, unknown_source
  template sections, figures, declarations      -> sections_missing, declaration_missing
  the revision trail                            -> change_log_missing

Every defect scenario ships with a false-positive guard: the same spec with the
defect repaired must report nothing.

    python bench_draft.py
"""

from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import sections as S  # noqa: E402

DRAFT = ("1 Introduction\n"
         "The coating raises uptake [doe2020] {M1}.\n"
         "2 Methods\n"
         "We measured 3 mM samples {M2}.\n"
         "3 Results\n"
         "Uptake rose three-fold [doe2020] {M1} (Fig 1).\n")

BASE = {
    "draft": DRAFT,
    "abstract": "The coating raised uptake three-fold.",
    "design": "experimental",
    "template": {"sections": ["introduction", "methods", "results"]},
    "materials": [
        {"id": "M1", "locator": "run01.csv row 4",
         "text": "uptake rose three-fold with the coating"},
        {"id": "M2", "locator": "notes.md 12:04", "text": "samples were prepared at 3 mM"},
    ],
    "references": [
        {"key": "doe2020", "authors": "Doe J", "year": 2020, "journal": "J Uptake",
         "topic": "coating raises uptake", "doi": "10.1000/x"},
    ],
    "figures": [{"id": "Fig 1", "caption": "Uptake rose three-fold with the coating",
                 "values": ["three-fold"]}],
    "declarations": {"data_availability": "on request",
                     "author_contributions": "all authors",
                     "competing_interests": "none", "funding": "grant 123"},
    "change_log": ["v1 initial", "v2 added methods"],
}


def d(**over):
    s = copy.deepcopy(BASE)
    s.update(over)
    return s


def fig(**over):
    s = copy.deepcopy(BASE)
    s["figures"] = [dict(BASE["figures"][0], **over)]
    return s


def ref(**over):
    s = copy.deepcopy(BASE)
    s["references"] = [dict(BASE["references"][0], **over)]
    return s


# A methods section that anchors no material: the steps cannot be compared with
# what the records say was actually done, so a conflict could sit in it unchecked.
DRAFT_NOANCH = ("1 Introduction\n"
                "The coating raises uptake [doe2020] {M1}.\n"
                "2 Methods\n"
                "Steps followed the standard protocol.\n"
                "3 Results\n"
                "Uptake rose three-fold [doe2020] {M1} (Fig 1).\n")


SCEN = [
    ("clean", lambda: (d(), [])),

    # structure
    ("draft_missing", lambda: (d(draft=""), ["pd.draft_missing"])),
    ("sections_missing",
     lambda: (d(draft="1 Introduction\nThe coating raises uptake [doe2020] {M1}.\n2 Methods\n"),
              ["pd.sections_missing"])),
    ("declaration_missing",
     lambda: (d(declarations={k: v for k, v in BASE["declarations"].items()
                              if k != "funding"}), ["pd.declaration_missing"])),

    # materials
    ("materials_missing", lambda: (d(materials=[]), ["pd.materials_missing"])),
    ("material_no_locator",
     lambda: (d(materials=[{"id": "M1", "text": BASE["materials"][0]["text"]},
                           BASE["materials"][1]]), ["pd.material_no_locator"])),
    ("material_unknown",
     lambda: (d(draft=DRAFT.replace("{M2}", "{M9}")), ["pd.material_unknown"])),
    ("material_unused",
     lambda: (d(materials=BASE["materials"] + [{"id": "M3", "locator": "x",
                                                "text": "unused"}]),
              ["pd.material_unused"])),

    # claims and citations
    ("uncited_claim",
     lambda: (d(draft="1 Introduction\nUptake increased with coating.\n2 Methods\n"
                      "We measured 3 mM samples {M2}.\n3 Results\n"
                      "Uptake rose three-fold [doe2020] {M1} (Fig 1).\n"),
              ["pd.uncited_claim"])),
    ("unknown_source", lambda: (ref(key="roe2021"), ["pd.unknown_source"])),
    ("citation_mismatch", lambda: (ref(topic="unrelated topic about protein folding"),
                                   ["pd.citation_mismatch"])),
    ("citation_padding",
     lambda: (d(references=BASE["references"] + [
         {"key": "a1", "authors": "A", "year": 2020, "journal": "J", "topic": "coating raises uptake"},
         {"key": "a2", "authors": "B", "year": 2020, "journal": "J", "topic": "coating raises uptake"},
         {"key": "a3", "authors": "C", "year": 2020, "journal": "J", "topic": "coating raises uptake"}],
         draft="1 Introduction\nUptake rises with the coating [doe2020, a1, a2, a3] {M1}.\n"
               "2 Methods\nWe measured 3 mM samples {M2}.\n3 Results\n"
               "Uptake rose three-fold [doe2020] {M1} (Fig 1).\n"),
         ["pd.citation_padding"])),

    # facts against materials
    ("value_not_in_materials",
     lambda: (d(draft="1 Introduction\nWe measured 9 mM samples {M2}.\n2 Methods\n"
                      "3 Results\nUptake rose three-fold [doe2020] {M1} (Fig 1).\n"),
              ["pd.value_not_in_materials"])),
    ("trend_as_causation",
     lambda: (d(design="observational",
                draft="1 Introduction\nThe coating causes higher uptake [doe2020] {M1}.\n"
                      "2 Methods\nWe measured 3 mM samples {M2}.\n3 Results\n"
                      "Uptake rose three-fold [doe2020] {M1} (Fig 1).\n"),
              ["pd.trend_as_causation"])),

    # figures
    ("caption_mismatch", lambda: (fig(caption="Uptake rose with the coating"),
                                  ["pd.figure_caption_mismatch"])),
    ("caption_missing", lambda: (fig(caption=""), ["pd.figure_caption_missing"])),
    ("figure_uncited", lambda: (d(figures=[{"id": "Fig 2", "caption": "Uptake rose three-fold",
                                            "values": ["three-fold"]}]),
                                ["pd.figure_uncited"])),

    # abstract, references, trail
    ("abstract_conflict",
     lambda: (d(abstract="The coating raised uptake 9-fold."), ["pd.abstract_result_conflict"])),
    ("reference_metadata_incomplete", lambda: (ref(journal=""), ["pd.reference_metadata_incomplete"])),
    ("change_log_missing", lambda: (d(change_log=[]), ["pd.change_log_missing"])),

    # figures numbering: a gap is a deleted figure the text may still point at
    ("figure_numbering_gap", lambda: (d(figures=[
        {"id": "Fig 1", "caption": "uptake curve", "number": 1},
        {"id": "Fig 3", "caption": "cell viability", "number": 3}]),
        ["pd.figure_numbering_gap"])),
    ("fp_figure_numbers_ok", lambda: (d(figures=[
        {"id": "Fig 1", "caption": "uptake curve", "number": 1},
        {"id": "Fig 2", "caption": "uptake curve, second repeat", "number": 2}],
        draft=BASE["draft"].replace("(Fig 1)", "(Fig 1, Fig 2)")), [])),

    # references identifiable as cited: a filled field can still be unfindable
    ("fp_reference_year_ok", lambda: (ref(year=1859), [])),
    ("fp_reference_doi_ok",
     lambda: (ref(doi="https://doi.org/10.1000/j.uptake.2020"), [])),
    ("fp_reference_volume_ok", lambda: (ref(volume="12", issue="3"), [])),

    # method steps checkable against the records
    ("fp_methods_not_declared",
     lambda: (d(draft=DRAFT_NOANCH, materials=BASE["materials"][:1],
                template={"sections": ["introduction", "results"]}), [])),


]


def main() -> int:
    rows = []
    for name, builder in SCEN:
        spec, expect = builder()
        findings, status, counts = S.run(spec, "paper_draft")
        fired = {f["rule"] for f in findings}
        missing = [r for r in expect if r not in fired]
        spurious = [] if expect else [f["rule"] for f in findings]
        ok = not missing and not spurious
        rows.append({"scenario": name, "expected": expect, "fired": sorted(fired),
                     "missing": missing, "spurious": spurious, "pass": ok,
                     "status": status})
        print(f"{'PASS' if ok else 'FAIL'}  {name:<30} missing={missing} spurious={spurious}")

    passed = sum(1 for r in rows if r["pass"])
    report = {"schema_version": "draft-bench/v1", "scenarios": rows,
              "totals": {"passed": passed, "of": len(rows)},
              "note": ("One scenario per rule, aligned to the paper-draft scoring points. "
                       "Clean baselines must report nothing.")}
    (Path(__file__).resolve().parent / "report_draft.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n{passed}/{len(rows)} pass")
    return 0 if passed == len(rows) else 1


if __name__ == "__main__":
    raise SystemExit(main())
