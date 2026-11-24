"""Benchmark for the evidence-driven writing skill.

One scenario per rule, aligned to the three-part deliverable this task states
(claim list / evidence table / draft) and to the four elements it grades on every claim
(claim, source, strength label, uncertainty statement), plus the many-to-many linking
and the material-form handling (scan / abstract-only / reordered two-column PDF).

    python bench_ew.py
"""

from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import writing as W  # noqa: E402

QUOTE = "The coating increased the uptake rate three-fold."
BASE = {
    "draft": "吸收速率提高到 3 倍 [C1]。",
    "claims": [
        {"id": "C1",
         "claim": "涂层使吸收速率提高三倍",
         "strength": "strong",
         "strength_basis": "controlled experiment, n=6, replicated",
         "uncertainty": "",
         "sources": [{"key": "doe2020", "quote": QUOTE, "locator": "p.7",
                      "support_relation": "supports", "support_strength": "strong",
                      "support_basis": "The controlled result directly reports the claimed three-fold uptake change."}]},
    ],
    "evidence": [
        {"key": "doe2020", "title": "Porous coatings for uptake", "year": 2020,
         "source_type": "primary", "text_quality": "native", "text": QUOTE},
    ],
}


def d(**over):
    s = copy.deepcopy(BASE)
    s.update(over)
    return s


def claim(**over):
    s = copy.deepcopy(BASE)
    s["claims"] = [dict(BASE["claims"][0], **over)]
    return s


def link(**over):
    s = copy.deepcopy(BASE)
    s["claims"] = copy.deepcopy(BASE["claims"])
    s["claims"][0]["sources"] = [dict(BASE["claims"][0]["sources"][0], **over)]
    return s


def ev(**over):
    s = copy.deepcopy(BASE)
    s["evidence"] = [dict(BASE["evidence"][0], **over)]
    return s


def triangulated():
    s = copy.deepcopy(BASE)
    second_quote = "A second controlled study also found a three-fold increase."
    second = {"key": "roe2021", "quote": second_quote, "locator": "Table 2",
              "support_relation": "supports", "support_strength": "moderate",
              "support_basis": "An independent controlled experiment reports the same direction and magnitude."}
    first = s["claims"][0]["sources"][0]
    first["support_strength"] = "moderate"
    s["claims"][0]["sources"].append(second)
    s["claims"][0]["strength_basis"] = "two independent controlled experiments, convergent results"
    s["evidence"].append({"key": "roe2021", "title": "Independent coating trial", "year": 2021,
                          "source_type": "primary", "text_quality": "native", "text": second_quote})
    return s


def opposing_registered():
    s = triangulated()
    counter_quote = "No uptake gain was detected below the solubility threshold."
    s["claims"][0]["sources"].append(
        {"key": "chen2022", "quote": counter_quote, "locator": "Results, paragraph 2",
         "support_relation": "contradicts", "support_strength": "none",
         "support_basis": "This is an opposing result retained as a scope boundary."})
    s["claims"][0]["conflict_note"] = "The claim is restricted to conditions above the solubility threshold."
    s["evidence"].append({"key": "chen2022", "title": "Boundary conditions for uptake", "year": 2022,
                          "source_type": "primary", "text_quality": "native", "text": counter_quote})
    return s


SCEN = [
    ("clean", lambda: (d(), [])),
    ("independent_moderate_triangulation_clean", lambda: (triangulated(), [])),
    ("opposition_registered_clean", lambda: (opposing_registered(), [])),

    # the three parts
    ("claims_missing", lambda: (d(claims=[]), ["ew.claims_missing"])),
    ("draft_missing", lambda: (d(draft=""), ["ew.draft_missing"])),
    ("table_missing", lambda: (d(evidence=[]), ["ew.evidence_table_missing"])),

    # claim identity
    ("claim_no_id", lambda: (claim(id=""), ["ew.claim_no_id"])),
    ("claim_empty", lambda: (claim(claim=""), ["ew.claim_empty"])),
    ("claim_not_in_draft", lambda: (d(draft="一句没有编号的话。"), ["ew.claim_not_in_draft"])),

    # the four elements
    ("strength_missing", lambda: (claim(strength=""), ["ew.strength_missing"])),
    ("strength_invalid", lambda: (claim(strength="very strong"), ["ew.strength_invalid"])),
    ("strength_without_basis", lambda: (claim(strength_basis=""), ["ew.strength_without_basis"])),
    ("uncertainty_missing", lambda: (claim(strength="weak"), ["ew.uncertainty_missing"])),

    # links
    ("claim_no_support", lambda: (claim(sources=[]), ["ew.claim_no_support"])),
    ("source_not_in_table",
     lambda: (link(key="ghost2019"), ["ew.source_not_in_table"])),
    ("link_no_quote", lambda: (link(quote=""), ["ew.link_no_quote"])),
    ("link_no_locator", lambda: (link(locator=""), ["ew.link_no_locator"])),
    ("quote_not_in_source",
     lambda: (link(quote="The coating tripled uptake in every sample."),
              ["ew.quote_not_in_source"])),
    ("support_undeclared",
     lambda: (link(support_relation=""), ["ew.link_support_undeclared",
                                        "ew.claim_no_direct_support"])),
    ("support_basis_missing",
     lambda: (link(support_basis=""), ["ew.support_basis_missing"])),
    ("link_strength_missing",
     lambda: (link(support_strength=""), ["ew.link_strength_missing",
                                         "ew.support_weaker_than_claim"])),
    ("link_strength_unknown",
     lambda: (link(support_strength="decisive"), ["ew.link_strength_unknown"])),
    ("single_weak_source_cannot_carry_strong_claim",
     lambda: (link(support_strength="weak"), ["ew.support_weaker_than_claim"])),
    ("counterevidence_cannot_be_support",
     lambda: (link(support_relation="contradicts", support_strength="none",
                   support_basis="", conflict_note="The claim is narrowed to the positive trial."),
              ["ew.claim_no_direct_support"])),
    ("opposition_not_addressed",
     lambda: (link(support_relation="undercuts", support_strength="none", support_basis=""),
              ["ew.claim_no_direct_support", "ew.opposition_not_addressed"])),
    ("locator_not_in_source",
     lambda: (d(claims=[dict(BASE["claims"][0],
                            sources=[dict(BASE["claims"][0]["sources"][0], locator="p.999")])],
                evidence=[dict(BASE["evidence"][0],
                               passages=[{"locator": "p.7", "text": QUOTE}])]),
              ["ew.locator_not_in_source"])),
    ("quote_not_at_locator",
     lambda: (d(evidence=[dict(BASE["evidence"][0],
                               passages=[{"locator": "p.7", "text": "Unrelated method detail."}])]),
              ["ew.quote_not_at_locator"])),
    ("draft_claim_unregistered",
     lambda: (d(draft="吸收速率提高到 3 倍 [C1]。另一个论断 [C9]。"),
              ["ew.draft_claim_unregistered"])),
    ("malformed_link_degrades",
     lambda: (claim(sources=["doe2020"]), ["ew.claim_no_support"])),

    # source quality
    ("retracted_source", lambda: (ev(retracted=True), ["ew.retracted_source_used"])),
    ("preprint_as_strong", lambda: (ev(source_type="preprint"), ["ew.preprint_as_strong"])),
    ("metadata_incomplete", lambda: (ev(year=""), ["ew.reference_metadata_incomplete"])),
    ("source_type_missing", lambda: (ev(source_type=""), ["ew.source_type_missing"])),

    # many-to-many and strength/prose agreement
    ("source_unused",
     lambda: (d(evidence=BASE["evidence"] + [
         {"key": "roe2021", "title": "Another study", "year": 2021,
          "source_type": "review", "text": "x"}]),
         ["ew.source_unused"])),
    ("draft_overstates_strength",
     lambda: (d(draft="This proves the coating works [C1].",
                claims=[dict(BASE["claims"][0], strength="weak",
                             uncertainty="single small study")]),
              ["ew.draft_overstates_strength"])),

    # --- material form: scan / abstract-only / reordered two-column PDF ---
    # Every source declares the form its text arrived in; each unregistered
    # form or missing pass record is a named finding, and the quote check says
    # what its failure means in that form.
    ("text_quality_undeclared",
     lambda: (ev(text_quality=""), ["ew.text_quality_undeclared"])),
    ("text_quality_unknown", lambda: (ev(text_quality="scanned"), ["ew.text_quality_unknown"])),
    ("ocr_provenance_missing",
     lambda: (ev(text_quality="ocr"), ["ew.ocr_provenance_missing"])),
    ("ocr_registered_clean",
     lambda: (ev(text_quality="ocr",
                 ocr_note="ocr-tool p.1-12, confidence 0.97, layout checked p.7"), [])),
    ("extraction_disorder_unrecorded",
     lambda: (ev(text_quality="two_column_reordered"),
              ["ew.extraction_disorder_unrecorded"])),
    ("disorder_registered_clean",
     lambda: (ev(text_quality="two_column_reordered",
                 order_repair_note="columns split at x>300pt, reading order rebuilt"), [])),
    ("abstract_only_strong",
     lambda: (ev(text_quality="abstract_only"), ["ew.support_abstract_only"])),
    ("abstract_only_weak_ok",
     lambda: (d(claims=[dict(BASE["claims"][0], strength="weak",
                             uncertainty="abstract-only record, full text not yet obtained")],
                evidence=[dict(BASE["evidence"][0], text_quality="abstract_only")]), [])),
    ("quote_unverifiable", lambda: (ev(text=""), ["ew.quote_unverifiable"])),
    ("quote_fails_on_ocr",
     lambda: (ev(text_quality="ocr",
                 ocr_note="ocr-tool p.1-12, confidence 0.97",
                 text="The coating increased the uptake rate three-f0ld."),
               ["ew.quote_not_in_source"])),
    ("quote_variant_rescues_ocr",
     lambda: (d(evidence=[dict(BASE["evidence"][0], text_quality="ocr",
                               ocr_note="ocr-tool p.1-12, confidence 0.97",
                               text="The coating increased the uptake rate three-f0ld.")],
                claims=[dict(BASE["claims"][0],
                             sources=[dict(BASE["claims"][0]["sources"][0],
                                           quote_variants=["The coating increased the "
                                                           "uptake rate three-f0ld."])])]),
              [])),
    ("conflict_unregistered",
     lambda: (ev(conflicts_with=["roe2021"]), ["ew.conflict_unregistered"])),
    ("conflict_registered_clean",
     lambda: (d(claims=[dict(BASE["claims"][0],
                             conflict_note="roe2021 reports no gain at lower dose; scope "
                                           "restricted to 25 C trials")],
                evidence=[dict(BASE["evidence"][0], conflicts_with=["roe2021"])]), [])),
    ("abstract_conflict_unregistered",
     lambda: (ev(abstract_conflict=True), ["ew.abstract_conflict_unregistered"])),
    ("abstract_conflict_registered_clean",
     lambda: (d(claims=[dict(BASE["claims"][0],
                             conflict_note="abstract says two-fold, full text Table 2 says "
                                           "three-fold; citing the full-text value")],
                evidence=[dict(BASE["evidence"][0], abstract_conflict=True)]), [])),
]


def main() -> int:
    rows = []
    for name, builder in SCEN:
        spec, expect = builder()
        findings, status, counts = W.run(spec, "evidence_writing")
        fired = {f["rule"] for f in findings}
        missing = [r for r in expect if r not in fired]
        spurious = [] if expect else [f["rule"] for f in findings]
        ok = not missing and not spurious
        rows.append({"scenario": name, "expected": expect, "fired": sorted(fired),
                     "missing": missing, "spurious": spurious, "pass": ok,
                     "status": status})
        print(f"{'PASS' if ok else 'FAIL'}  {name:<26} missing={missing} spurious={spurious}")

    passed = sum(1 for r in rows if r["pass"])
    report = {"schema_version": "ew-bench/v1", "scenarios": rows,
              "totals": {"passed": passed, "of": len(rows)},
              "note": ("One scenario per rule, aligned to the three-part deliverable and the "
                       "four graded elements. Clean baselines must report nothing.")}
    (Path(__file__).resolve().parent / "report_ew.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n{passed}/{len(rows)} pass")
    return 0 if passed == len(rows) else 1


if __name__ == "__main__":
    raise SystemExit(main())
