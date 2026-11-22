"""Benchmark for the grant-proposal skill.

One scenario per rule, aligned to the scoring points this task states:

  seven elements, each evidenced                -> element_missing, element_no_evidence
  paragraph -> element -> evidence mapping      -> paragraph_no_element, paragraph_no_evidence
  "already done" kept apart from "proposed"     -> status_unlabelled
  assessable objectives mapped to content/route -> aim_without_measure, objective_unmapped,
                                                   objective_no_route
  a route with inputs, outputs, risk, fallback  -> route_no_io, route_no_risk, route_no_fallback
  capability-evidence-relation foundation       -> foundation_no_*
  a justified budget                            -> budget_unjustified

    python bench_proposal.py
"""

from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import sections as S  # noqa: E402

RATIONALE = ("Surface-area limitation is the binding constraint in the current process, and the "
             "proposed coating is the only route we can execute with the platform in hand.")
INNOVATION = ("Unlike prior work that reports endpoint uptake, this proposal measures the rate "
              "at which the coating changes it, under paired controls.")

BASE = {
    "elements": {
        "rationale": {"text": RATIONALE, "evidence": "preliminary data M1"},
        "question": {"text": "whether a 42 nm porous coating raises uptake rate three-fold",
                     "evidence": "M1"},
        "objectives": {"text": "three measurable objectives", "evidence": "Sec 2"},
        "content": {"text": "coating synthesis and rate measurement", "evidence": "M2"},
        "innovation": {"text": INNOVATION, "evidence": "[doe2020]"},
        "technical_route": {"text": "three steps with fallbacks", "evidence": "Sec 4"},
        "foundation": {"text": "platform and prior coating work", "evidence": "M0"},
    },
    "paragraphs": [{"text": "why this matters", "element": "rationale", "evidence": "M1"}],
    "objectives": [{"id": "O1", "measure": "rate ratio vs control", "outcome": "three-fold rate",
                    "content_ref": "C1"}],
    "content": [{"id": "C1", "text": "synthesise and measure"}],
    "route": [{"id": "R1", "objective": "O1", "input": "monomer solution",
               "output": "coated sample", "risk": "pore collapse",
               "fallback": "template removal at lower temperature"}],
    "foundation_items": [{"name": "coating rig", "capability": "deposit 40 nm films",
                          "evidence": "M0 run 2023-04",
                          "relation": "the same rig makes the proposed coatings",
                          "status": "done"}],
    "timeline": [{"period": "Y1", "milestone": "coating built and characterised"}],
    "budget": [{"item": "consumables", "justification": "monomer for 60 runs"}],
    "budget_justification": "each line is costed from current supplier quotes",
}


def d(**over):
    s = copy.deepcopy(BASE)
    s.update(over)
    return s


def el(name, **over):
    s = copy.deepcopy(BASE)
    s["elements"] = copy.deepcopy(BASE["elements"])
    s["elements"][name] = {**BASE["elements"][name], **over}
    return s


SCEN = [
    ("clean", lambda: (d(), [])),

    # the seven elements
    ("element_missing",
     lambda: (d(elements={k: v for k, v in BASE["elements"].items() if k != "innovation"}),
              ["prop.element_missing"])),
    ("element_no_evidence", lambda: (el("rationale", evidence=""), ["prop.element_no_evidence"])),

    # three-level mapping
    ("paragraph_no_element",
     lambda: (d(paragraphs=[{"text": "why this matters", "evidence": "M1"}]),
              ["prop.paragraph_no_element"])),
    ("paragraph_no_evidence",
     lambda: (d(paragraphs=[{"text": "why this matters", "element": "rationale"}]),
              ["prop.paragraph_no_evidence"])),

    # done versus planned
    ("status_unlabelled",
     lambda: (d(foundation_items=[{k: v for k, v in BASE["foundation_items"][0].items()
                                   if k != "status"}]),
              ["prop.status_unlabelled"])),
    ("foundation_no_relation",
     lambda: (d(foundation_items=[{k: v for k, v in BASE["foundation_items"][0].items()
                                   if k != "relation"}]),
              ["prop.foundation_no_relation"])),

    # the question must be bounded
    ("question_too_broad",
     lambda: (el("question", text="a comprehensive study of every aspect of uptake"),
              ["prop.question_too_broad"])),

    # objectives
    ("objectives_missing", lambda: (d(objectives=[]), ["prop.objectives_missing"])),
    ("aim_without_measure",
     lambda: (d(objectives=[{"id": "O1", "outcome": "faster uptake", "content_ref": "C1"}]),
              ["prop.aim_without_measure"])),
    ("objective_unmapped",
     lambda: (d(objectives=[{"id": "O1", "measure": "rate ratio", "outcome": "three-fold"}]),
              ["prop.objective_unmapped"])),
    ("objective_no_route",
     lambda: (d(objectives=[{"id": "O2", "measure": "rate ratio", "outcome": "three-fold",
                             "content_ref": "C1"}]),
              ["prop.objective_no_route"])),

    # the technical route
    ("route_no_io",
     lambda: (d(route=[{k: v for k, v in BASE["route"][0].items()
                        if k not in ("input", "output")}]), ["prop.route_no_io"])),
    ("route_no_risk",
     lambda: (d(route=[{k: v for k, v in BASE["route"][0].items() if k != "risk"}]),
              ["prop.route_no_risk"])),
    ("route_no_fallback",
     lambda: (d(route=[{k: v for k, v in BASE["route"][0].items() if k != "fallback"}]),
              ["prop.route_no_fallback"])),

    # milestones and budget
    ("milestone_missing",
     lambda: (d(timeline=[{"period": "Y1"}]), ["prop.milestone_missing"])),
    ("budget_unjustified",
     lambda: (d(budget_justification=""), ["prop.budget_unjustified"])),
    ("budget_line_unjustified",
     lambda: (d(budget=[{"item": "consumables"}]), ["prop.budget_line_unjustified"])),

    # thin narrative
    ("field_too_thin", lambda: (el("innovation", text="Novel."), ["prop.field_too_thin"])),
]


def main() -> int:
    rows = []
    for name, builder in SCEN:
        spec, expect = builder()
        findings, status, counts = S.run(spec, "proposal")
        fired = {f["rule"] for f in findings}
        missing = [r for r in expect if r not in fired]
        spurious = [] if expect else [f["rule"] for f in findings]
        ok = not missing and not spurious
        rows.append({"scenario": name, "expected": expect, "fired": sorted(fired),
                     "missing": missing, "spurious": spurious, "pass": ok,
                     "status": status})
        print(f"{'PASS' if ok else 'FAIL'}  {name:<26} missing={missing} spurious={spurious}")

    passed = sum(1 for r in rows if r["pass"])
    report = {"schema_version": "proposal-bench/v1", "scenarios": rows,
              "totals": {"passed": passed, "of": len(rows)},
              "note": ("One scenario per rule, aligned to the proposal scoring points. Clean "
                       "baselines must report nothing.")}
    (Path(__file__).resolve().parent / "report_proposal.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n{passed}/{len(rows)} pass")
    return 0 if passed == len(rows) else 1


if __name__ == "__main__":
    raise SystemExit(main())
