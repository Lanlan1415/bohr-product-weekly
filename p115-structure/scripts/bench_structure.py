"""Benchmark for the structure-and-logic diagnosis skill.

One scenario per rule, aligned to the scoring points this task states:

  a complete diagnosis of six dimensions       -> dimension_missing, no_diagnosis
  judgements matching the actual text          -> evidence_not_in_text, finding_no_evidence
  no style preference reported as a defect     -> style_as_defect
  suggestions the author can execute           -> suggestion_missing, suggestion_no_action,
                                                  suggestion_not_executable
  every judgement locatable                    -> finding_no_locator, finding_locator_vague
  cross-section consistency                    -> promise_not_delivered, abstract_overclaim,
                                                  abstract_conclusion_mismatch

    python bench_structure.py
"""

from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import sections as S  # noqa: E402

MANUSCRIPT = (
    "1 Introduction\nUptake is limited by surface area. We ask whether a porous coating raises "
    "uptake.\n2 Methods\nWe coated samples and measured uptake.\n3 Results\nUptake rose "
    "three-fold.\n4 Discussion\nThe effect is consistent with a surface-area mechanism.\n"
)

DIMS = ["research_question", "section_structure", "argument_chain", "paragraph_relation",
        "duplication", "conclusion_scope"]
EVIDENCE = {
    "research_question": "We ask whether a porous coating raises uptake",
    "section_structure": "2 Methods",
    "argument_chain": "The effect is consistent with a surface-area mechanism",
    "paragraph_relation": "3 Results",
    "duplication": "We coated samples and measured uptake",
    "conclusion_scope": "Uptake rose three-fold",
}

BASE = {
    "manuscript_text": MANUSCRIPT,
    "research_question": "whether a porous coating raises uptake",
    "design": "experimental",
    "conclusion": "The effect is consistent with a surface-area mechanism.",
    "abstract": "Uptake rose three-fold with a porous coating, consistent with a "
                "surface-area mechanism.",
    "limitations": "single material, one coating thickness",
    "promises": [{"statement": "we measure uptake under the coating",
                  "locator": "1 Introduction"}],
    "delivery_text": "We coated samples and measured uptake. Uptake rose three-fold.",
    "contributions": [{"claim": "a porous coating raises uptake", "anchor": "3 Results"}],
    "paragraphs": [
        {"id": "p1", "section": "Introduction", "text": "Uptake is limited by surface area",
         "claims": [{"claim": "uptake is limited by surface area", "support": "[doe2020]",
                     "strength": "moderate", "support_strength": "moderate"}]},
        {"id": "p2", "section": "Methods", "text": "We coated samples and measured uptake",
         "claims": [{"claim": "the method is sound", "support": "Sec 2", "strength": "weak",
                     "support_strength": "moderate"}]},
        {"id": "p3", "section": "Results", "text": "Uptake rose three-fold",
         "claims": [{"claim": "uptake rose three-fold", "support": "Fig 1", "strength": "strong",
                     "support_strength": "strong"}]},
    ],
    "diagnosis": [{"id": d[:3].upper(), "dimension": d, "finding": "noted",
                   "evidence": EVIDENCE[d], "locator": "1 Introduction", "severity": "minor"}
                  for d in DIMS],
    "suggestions": [{"for_finding": "ARG", "action": "move the mechanism sentence to Results"}],
}


def d(**over):
    s = copy.deepcopy(BASE)
    s.update(over)
    return s


def diag(index, **over):
    s = copy.deepcopy(BASE)
    s["diagnosis"] = copy.deepcopy(BASE["diagnosis"])
    s["diagnosis"][index] = dict(BASE["diagnosis"][index], **over)
    return s


def para(index, **over):
    s = copy.deepcopy(BASE)
    s["paragraphs"] = copy.deepcopy(BASE["paragraphs"])
    s["paragraphs"][index] = {**BASE["paragraphs"][index], **over}
    return s


SCEN = [
    ("clean", lambda: (d(), [])),

    # the diagnosis must exist and cover six dimensions
    ("no_manuscript", lambda: (d(manuscript_text="", paragraphs=[]), ["struct.no_manuscript"])),
    ("no_diagnosis", lambda: (d(diagnosis=[]), ["struct.no_diagnosis"])),
    ("dimension_missing",
     lambda: (d(diagnosis=BASE["diagnosis"][:5]), ["struct.dimension_missing"])),
    ("dimension_unknown", lambda: (diag(0, dimension="voice"), ["struct.dimension_unknown"])),

    # the research question and contributions
    ("research_question_missing",
     lambda: (d(research_question=""), ["struct.research_question_missing"])),
    ("question_absent_from_text",
     lambda: (d(research_question="do lipid rafts control endocytosis in neurons"),
              ["struct.question_absent_from_text"])),
    ("contribution_unanchored",
     lambda: (d(contributions=[{"claim": "a porous coating raises uptake"}]),
              ["struct.contribution_unanchored"])),

    # findings must be evidenced, located, and not style
    ("finding_no_evidence", lambda: (diag(0, evidence=""), ["struct.finding_no_evidence"])),
    ("evidence_fabricated",
     lambda: (diag(0, evidence="The abstract contradicts the results table entirely"),
              ["struct.evidence_not_in_text"])),
    ("finding_no_locator", lambda: (diag(0, locator=""), ["struct.finding_no_locator"])),
    ("style_as_defect", lambda: (diag(2, severity="style"), ["struct.style_as_defect"])),

    # suggestions
    ("suggestion_missing", lambda: (diag(0, severity="major"), ["struct.suggestion_missing"])),
    ("suggestion_no_action",
     lambda: (d(suggestions=[{"for_finding": "ARG", "action": ""}]),
              ["struct.suggestion_no_action"])),
    ("suggestion_orphaned",
     lambda: (d(suggestions=[{"for_finding": "ZZZ", "action": "cut it"}]),
              ["struct.suggestion_orphaned"])),

    # paragraph-level
    ("multiple_claims",
     lambda: (para(0, claims=[{"claim": "a", "support": "x"},
                              {"claim": "b", "support": "y"}]),
              ["struct.multiple_claims"])),
    ("claim_without_support",
     lambda: (para(0, claims=[{"claim": "uptake is limited by surface area"}]),
              ["struct.claim_without_support"])),
    # A cycle is A supported by B and B supported by A; a claim pointing at itself is a
    # malformed pointer, which is a different defect.
    ("circular_support",
     lambda: (d(paragraphs=[
         {"id": "p1", "section": "Introduction", "text": "Uptake is limited by surface area",
          "claims": [{"claim": "uptake is limited by surface area",
                      "support": "uptake rose three-fold"}]},
         {"id": "p3", "section": "Results", "text": "Uptake rose three-fold",
          "claims": [{"claim": "uptake rose three-fold",
                      "support": "uptake is limited by surface area"}]}]),
              ["struct.circular_support"])),
    ("support_weaker_than_claim",
     lambda: (para(2, claims=[{"claim": "uptake rose three-fold", "support": "Fig 1",
                               "strength": "strong", "support_strength": "weak"}]),
              ["struct.support_weaker_than_claim"])),
    ("duplicate_paragraph",
     lambda: (d(paragraphs=BASE["paragraphs"] + [
         {"id": "p4", "section": "Discussion",
          "text": "We coated samples and measured uptake",
          "claims": [{"claim": "the method is sound", "support": "Sec 2"}]}]),
              ["struct.duplicate_paragraph"])),
    ("section_interleaved",
     lambda: (d(paragraphs=BASE["paragraphs"] + [
         {"id": "p4", "section": "Introduction", "text": "More introduction",
          "claims": [{"claim": "background matters", "support": "[doe2020]"}]}]),
              ["struct.section_interleaved"])),

    # conclusion scope
    ("conclusion_exceeds_scope",
     lambda: (d(design="observational",
                conclusion="The coating causes higher uptake and proves the mechanism."),
              ["struct.conclusion_exceeds_scope"])),
    ("limitations_missing", lambda: (d(limitations=""), ["struct.limitations_missing"])),

    # round 2: cross-section consistency and suggestion executability
    ("promise_not_delivered",
     lambda: (d(promises=[{"statement": "we test whether lipid rafts control endocytosis "
                                          "in neurons", "locator": "1 Introduction"}]),
              ["struct.promise_not_delivered"])),
    ("abstract_overclaim",
     lambda: (d(design="observational",
                abstract="The coating causes higher uptake and proves the mechanism."),
              ["struct.abstract_overclaim"])),
    ("abstract_conclusion_mismatch",
     lambda: (d(abstract="Lipid rafts control endocytosis in neurons across brain regions."),
              ["struct.abstract_conclusion_mismatch"])),
    ("finding_locator_vague",
     lambda: (diag(0, locator="the paper"), ["struct.finding_locator_vague"])),
    ("suggestion_not_executable",
     lambda: (d(suggestions=[{"for_finding": "ARG",
                              "action": "this should really be improved"}]),
              ["struct.suggestion_not_executable"])),
]


def main() -> int:
    rows = []
    for name, builder in SCEN:
        spec, expect = builder()
        findings, status, counts = S.run(spec, "structure_logic")
        fired = {f["rule"] for f in findings}
        missing = [r for r in expect if r not in fired]
        spurious = [] if expect else [f["rule"] for f in findings]
        ok = not missing and not spurious
        rows.append({"scenario": name, "expected": expect, "fired": sorted(fired),
                     "missing": missing, "spurious": spurious, "pass": ok,
                     "status": status})
        print(f"{'PASS' if ok else 'FAIL'}  {name:<28} missing={missing} spurious={spurious}")

    passed = sum(1 for r in rows if r["pass"])
    report = {"schema_version": "structure-bench/v1", "scenarios": rows,
              "totals": {"passed": passed, "of": len(rows)},
              "note": ("One scenario per rule, aligned to the structure-diagnosis scoring "
                       "points. Clean baselines must report nothing.")}
    (Path(__file__).resolve().parent / "report_structure.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n{passed}/{len(rows)} pass")
    return 0 if passed == len(rows) else 1


if __name__ == "__main__":
    raise SystemExit(main())
