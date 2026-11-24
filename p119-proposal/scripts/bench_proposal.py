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


FULL = copy.deepcopy(BASE)
FULL.update({
    "grant_profile": "nsfc_full",
    "architecture": {
        "background": "Current porous coatings are limited by surface area.",
        "gap": "Endpoint uptake is reported, but the time-resolved rate is unknown.",
        "question": "whether a 42 nm coating changes the uptake rate under paired controls",
        "hypothesis": "the coating raises the rate at least three-fold without selectivity loss",
        "objectives": "three measurable objectives in the work plan",
        "content": "coating synthesis, rate measurement and control comparison",
        "technical_route": "synthesise, characterise, then measure paired samples",
        "outcomes": "a rate-ratio estimate and a reusable measurement protocol",
    },
    "science_question": {
        "property": "需求牵引，突破瓶颈",
        "central_question": "whether 42 nm porosity changes uptake rate rather than only endpoint uptake",
        "hypothesis": "the rate ratio exceeds three against the uncoated substrate",
        "boundary": "one material class, 24 h, paired controls, no in vivo claim",
        "falsifiability": "a rate ratio at or below one falsifies the central hypothesis",
    },
    "innovations": [{
        "id": "I1",
        "text": "Time-resolved rate measurement under paired controls.",
        "comparison_target": "endpoint-only uptake studies [doe2020]",
        "difference": "measures rate trajectories in the same samples instead of one endpoint",
        "why_hard": "requires stable paired sampling without changing the coating",
        "feasibility_evidence": "M1 pilot run and the existing coating rig",
        "evidence": "[doe2020]; M1 pilot run",
    }],
    "key_questions": [{
        "id": "KQ1",
        "text": "Does the coating change the uptake trajectory or only its endpoint?",
        "content_ref": "C1",
        "attribute": "mechanism",
        "answer_measure": "paired rate ratio with a confidence interval",
    }],
    "feasibility": {
        "technical": "the coating rig already deposits 40 nm films",
        "team": "one materials lead and one measurement operator",
        "resource": "existing rig plus consumables in the given budget",
        "time": "two synthesis campaigns fit the annual plan",
        "preliminary_status": "provided",
        "preliminary_gap": "",
    },
    "applicant_evidence": {
        "status": "partial",
        "items": [],
        "gap_note": "The applicant's independent preliminary results are not in the supplied "
                    "materials; only external published evidence and team platform access are claimed.",
    },
    "outcomes": [{
        "id": "W1",
        "objectives": ["O1"],
        "kind": "paper and protocol",
        "assessment": "rate ratio reproduces under a second operator",
    }],
    "risks": [{
        "id": "K1",
        "type": "method_feasibility",
        "trigger": "two pore collapses in one week",
        "impact": "synthesis campaign stalls",
        "fallback": "lower-temperature template removal",
        "decision_point": "end of month two",
    }],
    "ethics": {
        "applicable": False,
        "scope_explanation": "in vitro materials only; no human, animal or personal data",
    },
    "budget": [{
        "item": "consumables",
        "amount_status": "not_provided",
        "amount": None,
        "purpose": "synthesis and paired measurement campaigns",
        "basis": "60 runs at the supplier catalogue unit scale; amount pending finance",
        "justification": "monomer for 60 runs",
    }],
    "timeline": [{
        "period": "Y1",
        "milestone": "coating built and characterised",
        "deliverable": "coating protocol and first paired dataset",
        "objectives": ["O1"],
    }],
})
FULL["foundation_items"][0]["owner"] = "external published platform work"


def full_with(mutator):
    s = copy.deepcopy(FULL)
    mutator(s)
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

    # Full NSFC-style review profile: eight layers + structured review checks.
    ("full_clean", lambda: (copy.deepcopy(FULL), [])),
    ("architecture_layer_missing",
     lambda: (full_with(lambda s: s["architecture"].update(gap="")),
              ["prop.architecture_layer_missing"])),
    ("science_property_missing",
     lambda: (full_with(lambda s: s["science_question"].update(property="")),
              ["prop.science_property_missing"])),
    ("innovation_weak_no_comparator",
     lambda: (full_with(lambda s: s["innovations"][0].update(
         comparison_target="", difference="")),
              ["prop.innovation_no_comparator", "prop.innovation_no_difference"])),
    ("innovation_generic",
     lambda: (full_with(lambda s: s["innovations"][0].update(
         difference="采用先进的深度学习方法提高效率")), ["prop.innovation_weak"])),
    ("innovation_overclaimed",
     lambda: (full_with(lambda s: s["innovations"][0].update(
         text="国际首次填补空白，采用全新的方法")), ["prop.innovation_overclaimed"])),
    ("key_question_unknown_content",
     lambda: (full_with(lambda s: s["key_questions"][0].update(content_ref="C9")),
              ["prop.key_question_content_unknown"])),
    ("preliminary_gap_unaccounted",
     lambda: (full_with(lambda s: s["feasibility"].update(
         preliminary_status="not_provided", preliminary_gap="")),
              ["prop.feasibility_preliminary_unaccounted"])),
    ("applicant_gap_not_recorded",
     lambda: (full_with(lambda s: s["applicant_evidence"].update(gap_note="")),
              ["prop.applicant_evidence_gap_note_missing"])),
    ("applicant_provided_empty",
     lambda: (full_with(lambda s: s["applicant_evidence"].update(status="provided", items=[])),
              ["prop.applicant_evidence_items_missing"])),
    ("foundation_owner_missing",
     lambda: (full_with(lambda s: s["foundation_items"][0].pop("owner")),
              ["prop.foundation_owner_missing"])),
    ("timeline_deliverable_missing",
     lambda: (full_with(lambda s: s["timeline"][0].update(deliverable="")),
              ["prop.timeline_deliverable_missing"])),
    ("outcome_unmapped",
     lambda: (full_with(lambda s: s["outcomes"][0].update(objectives=[])),
              ["prop.outcome_unmapped"])),
    ("risk_trigger_missing",
     lambda: (full_with(lambda s: s["risks"][0].update(trigger="")),
              ["prop.risk_field_missing"])),
    ("ethics_undeclared",
     lambda: (full_with(lambda s: s.pop("ethics")), ["prop.ethics_undeclared"])),
    ("budget_amount_invented",
     lambda: (full_with(lambda s: s["budget"][0].update(amount_status="provided")),
              ["prop.budget_amount_missing"])),
    ("cjk_argument_guard",
     lambda: (full_with(lambda s: (
         s["elements"]["rationale"].update(
             text="多孔涂层已有终点证据，但缺少同批速率轨迹，本项目以配对测量区分速率与终点效应，并限定材料体系与时间窗口。"),
         s["elements"]["innovation"].update(
             text="相较指定论文的终点比较，本项目在同一批样品上测量速率轨迹并保留配对对照，因此差异是可复核的，而非只换方法名称。"))),
              [])),
    ("field_too_thin_cjk",
     lambda: (full_with(lambda s: s["elements"]["rationale"].update(text="主题很重要。")),
              ["prop.field_too_thin"])),
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
