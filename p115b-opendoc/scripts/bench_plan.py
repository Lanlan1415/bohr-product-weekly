"""Benchmark for the research-plan (opening report) skill.

One scenario per rule, aligned to the scoring points this task states:

  seven elements present and answered     -> element_missing, element_no_text
  a gap statement, not a literature list  -> background_gap_incomplete
  period declared and respected           -> period_undeclared, schedule_exceeds_period
  claims tied to material/reference/version -> claim_no_citation, citation_unknown,
                                              claim_no_version
  objectives with criteria and basis      -> objective_no_criteria, threshold_no_basis
  a route with io and dependencies        -> route_no_io, route_dependency_unknown
  risks classified with trigger/impact/fallback/decision point
                                          -> risk_type_*, risk_no_*
  outcomes with an assessment             -> outcome_no_assessment
  resources inside the envelope           -> resource_exceeds_budget

    python bench_plan.py
"""

from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import sections as S  # noqa: E402

BASE = {
    "period_months": 24,
    "resource_budget": 100.0,
    "resource_needed": 80.0,
    "elements": {
        "background": {"text": "surface-area limitation",
                       "known": "uptake is surface limited",
                       "unknown": "whether a 42 nm coating changes the rate",
                       "to_test": "rate under paired controls"},
        "problem": {"text": "the rate is the bottleneck"},
        "objectives": {"text": "two measurable objectives"},
        "technical_route": {"text": "three steps"},
        "schedule": {"text": "four quarters"},
        "risks": {"text": "four classified risks"},
        "outcomes": {"text": "two assessable outcomes"},
    },
    "materials": [{"id": "M1", "locator": "run01.csv"}],
    "references": [{"key": "doe2020", "title": "Porous coatings", "year": 2020}],
    "claims": [{"text": "uptake is surface limited", "material": "M1",
                "version": "2024-05"}],
    "objectives": [{"id": "O1", "metric": "rate ratio", "sample": "n=6 per arm",
                    "control": "uncoated", "timepoint": "week 8",
                    "threshold": 3.0, "threshold_basis": "pilot run M1 showed 2.8"}],
    "route": [{"id": "R1", "input": "monomer solution", "output": "coated sample"},
              {"id": "R2", "input": "coated sample", "output": "rate curve",
               "depends_on": ["R1"]}],
    "schedule": [
        {"period": "Q1", "end_month": 6, "deliverable": "coating built",
         "on_critical_path": True},
        {"period": "Q2", "end_month": 12, "deliverable": "rate curve measured"},
    ],
    "risks": [
        {"id": "K1", "type": "data_access", "trigger": "vendor delay over 2 weeks",
         "impact": "Q1 slips", "fallback": "use in-house monomer", "decision_point": "week 3 of Q1"},
        {"id": "K2", "type": "method_feasibility", "trigger": "pore collapse in 50% of runs",
         "impact": "rate curve unusable", "fallback": "lower template temperature",
         "decision_point": "end of Q1"},
    ],
    "outcomes": [{"id": "P1", "kind": "paper", "assessment": "submitted to a peer-reviewed journal"},
                 {"id": "P2", "kind": "dataset", "assessment": "deposited with a DOI"}],
}


def d(**over):
    s = copy.deepcopy(BASE)
    s.update(over)
    return s


def el(name, **over):
    s = copy.deepcopy(BASE)
    s["elements"] = copy.deepcopy(BASE["elements"])
    s["elements"][name] = {**BASE["elements"].get(name, {}), **over}
    return s


def risk(index, **over):
    s = copy.deepcopy(BASE)
    s["risks"] = copy.deepcopy(BASE["risks"])
    s["risks"][index] = {**BASE["risks"][index], **over}
    return s


SCEN = [
    ("clean", lambda: (d(), [])),

    # seven elements
    ("element_missing",
     lambda: (d(elements={k: v for k, v in BASE["elements"].items() if k != "risks"}),
              ["rp.element_missing"])),
    ("element_no_text", lambda: (el("problem", text=""), ["rp.element_no_text"])),

    # gap statement
    ("gap_incomplete", lambda: (el("background", unknown=""), ["rp.background_gap_incomplete"])),

    # period
    ("period_undeclared", lambda: (d(period_months=None), ["rp.period_undeclared"])),
    ("schedule_exceeds_period",
     lambda: (d(period_months=6), ["rp.schedule_exceeds_period"])),

    # claims
    ("claim_no_citation",
     lambda: (d(claims=[{"text": "uptake is surface limited", "version": "v1"}]),
              ["rp.claim_no_citation"])),
    ("citation_unknown",
     lambda: (d(claims=[{"text": "x", "reference": "roe2021", "version": "v1"}]),
              ["rp.citation_unknown"])),
    ("claim_no_version",
     lambda: (d(claims=[{"text": "x", "material": "M1"}]), ["rp.claim_no_version"])),

    # objectives
    ("objectives_missing", lambda: (d(objectives=[]), ["rp.objectives_missing"])),
    ("objective_no_criteria",
     lambda: (d(objectives=[{"id": "O1", "metric": "rate ratio"}]), ["rp.objective_no_criteria"])),
    ("threshold_no_basis",
     lambda: (d(objectives=[{**BASE["objectives"][0], "threshold_basis": ""}]),
              ["rp.threshold_no_basis"])),

    # route
    ("route_no_io",
     lambda: (d(route=[{"id": "R1", "input": "monomer"}]), ["rp.route_no_io"])),
    ("route_dependency_unknown",
     lambda: (d(route=[BASE["route"][0], {"id": "R2", "input": "a", "output": "b",
                                          "depends_on": ["R9"]}]),
              ["rp.route_dependency_unknown"])),

    # schedule
    ("milestone_no_deliverable",
     lambda: (d(schedule=[{"period": "Q1", "end_month": 6}]), ["rp.milestone_no_deliverable"])),
    ("critical_path_unmarked",
     lambda: (d(schedule=[{"period": "Q1", "end_month": 6, "deliverable": "coating"}]),
              ["rp.critical_path_unmarked"])),

    # risks
    ("risks_missing", lambda: (d(risks=[]), ["rp.risks_missing"])),
    ("risk_type_missing", lambda: (risk(0, type=""), ["rp.risk_type_missing"])),
    ("risk_type_unknown", lambda: (risk(0, type="weather"), ["rp.risk_type_unknown"])),
    ("risk_no_trigger", lambda: (risk(0, trigger=""), ["rp.risk_no_trigger"])),
    ("risk_no_fallback", lambda: (risk(0, fallback=""), ["rp.risk_no_fallback"])),
    ("risk_no_decision_point", lambda: (risk(0, decision_point=""), ["rp.risk_no_decision_point"])),
    ("risk_type_uncovered",
     lambda: (d(risks=[BASE["risks"][0]]), ["rp.risk_type_uncovered"])),

    # outcomes
    ("outcomes_missing", lambda: (d(outcomes=[]), ["rp.outcomes_missing"])),
    ("outcome_no_assessment",
     lambda: (d(outcomes=[{"id": "P1", "kind": "paper"}]), ["rp.outcome_no_assessment"])),

    # resources
    ("resource_exceeds_budget", lambda: (d(resource_needed=150.0), ["rp.resource_exceeds_budget"])),
]


def main() -> int:
    rows = []
    for name, builder in SCEN:
        spec, expect = builder()
        findings, status, counts = S.run(spec, "research_plan")
        fired = {f["rule"] for f in findings}
        missing = [r for r in expect if r not in fired]
        spurious = [] if expect else [f["rule"] for f in findings]
        ok = not missing and not spurious
        rows.append({"scenario": name, "expected": expect, "fired": sorted(fired),
                     "missing": missing, "spurious": spurious, "pass": ok,
                     "status": status})
        print(f"{'PASS' if ok else 'FAIL'}  {name:<28} missing={missing} spurious={spurious}")

    passed = sum(1 for r in rows if r["pass"])
    report = {"schema_version": "plan-bench/v1", "scenarios": rows,
              "totals": {"passed": passed, "of": len(rows)},
              "note": ("One scenario per rule, aligned to the opening-report scoring points. "
                       "Clean baselines must report nothing.")}
    (Path(__file__).resolve().parent / "report_plan.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n{passed}/{len(rows)} pass")
    return 0 if passed == len(rows) else 1


if __name__ == "__main__":
    raise SystemExit(main())
