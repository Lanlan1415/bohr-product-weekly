"""Benchmark for the opening-report / research-plan section.

One clean baseline, one defect scenario per rule that the opening-report brief
names as a scoring point, and repaired-twin guards for the rules added against
the brief's four questions (the plan must 立得住 / 对得上 / 排得开 / 说得清).
A scenario passes only if every required rule fires; the clean baseline must
report nothing, so a detector cannot pass by flagging everything.

    python bench_plan.py
"""

from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import sections as S  # noqa: E402

BACKGROUND = {
    "known": "coated substrates raise uptake in three published systems",
    "unknown": "whether the rate change appears at the 42 nm thickness the platform can make",
    "to_test": "rate ratio of coated vs uncoated substrate at one thickness",
}
OBJECTIVES = [
    {"id": "O1", "metric": "uptake rate ratio", "sample": "n = 6 per arm",
     "control": "uncoated substrate, same temperature",
     "timepoint": "24 h", "threshold": 3.0,
     "threshold_basis": "rate change reported by [doe2020] at 40 nm"},
    {"id": "O2", "metric": "coating thickness uniformity", "sample": "n = 6 wafers",
     "control": "within-wafer variance", "timepoint": "at deposition"},
]
ROUTE = [
    {"id": "R1", "objective": "O1", "input": "monomer solution",
     "output": "coated substrate", "risk": "pore collapse",
     "fallback": "template removal at lower temperature",
     "depends_on": []},
    {"id": "R2", "objective": "O2", "input": "coated substrate",
     "output": "thickness map", "risk": "roughness confounds the profile",
     "fallback": "AFM on a witness wafer",
     "depends_on": ["R1"]},
]
SCHEDULE = [
    {"period": "2025-03 to 2025-08", "end_month": 6,
     "deliverable": "coating protocol and first rate dataset",
     "on_critical_path": True},
    {"period": "2025-09 to 2026-02", "end_month": 12,
     "deliverable": "rate ratio at three arm sizes, draft chapter",
     "on_critical_path": True},
]
CLAIMS = [
    {"text": "40 nm coatings raised uptake rates in prior work",
     "reference": "doe2020", "version": "v2.1"},
    {"text": "the platform produced 38 nm coatings in the 2025-03 run",
     "material": "M1", "version": "run 2025-03-14"},
]
RISKS = [
    {"id": "K1", "type": "method_feasibility", "trigger": "two collapses in one week",
     "impact": "route step R1 stalls", "fallback": "lower-temperature template removal",
     "decision_point": "end of month 2"},
    {"id": "K2", "type": "data_access", "trigger": "instrument booking denied twice",
     "impact": "schedule slips one quarter", "fallback": "share time on the partner rig",
     "decision_point": "end of month 4"},
]
OUTCOMES = [
    {"id": "W1", "objectives": ["O1"], "kind": "paper",
     "assessment": "rate ratio confirmed by a second operator on the same rig"},
    {"id": "W2", "objectives": ["O2"], "kind": "dataset",
     "assessment": "thickness map accepted by the co-supervisor"},
]

BASE = {
    "case_id": "demo-plan-001",
    "section": "research_plan",
    "period_months": 18,
    "resource_budget": 40,
    "resource_needed": 32,
    "materials": [{"id": "M1", "name": "2025-03 coating runs"}],
    "references": [{"key": "doe2020", "title": "Porous coatings", "year": 2020}],
    "elements": {
        "background": {**BACKGROUND,
                       "text": "Uptake is limited by surface area; prior coatings raise it."},
        "problem": {"text": "whether a 42 nm porous coating raises uptake rate three-fold"},
        "objectives": {"text": "two objectives with metric, sample, control and timepoint"},
        "technical_route": {"text": "two steps with declared dependencies"},
        "schedule": {"text": "two phases inside the 18-month period"},
        "risks": {"text": "method and data-access risks with triggers"},
        "outcomes": {"text": "one paper and one dataset, each with an assessment"},
    },
    "objectives": OBJECTIVES,
    "route": ROUTE,
    "schedule": SCHEDULE,
    "claims": CLAIMS,
    "risks": RISKS,
    "outcomes": OUTCOMES,
}

# Extended recipe-repair, FAIR/reproducibility and ethics closed-loop fields. They
# formalize what the case gives; no approval number or result is invented.
BASE["elements"]["problem"]["falsification"] = "the paired estimate fails the declared threshold"
BASE["hypotheses"] = [
    {"id": "H1", "objective": "O1", "statement": "42 nm coating raises the 24 h rate ratio to 3",
     "test": "paired coated/uncoated assay", "null_result": "threshold or direction is not met"},
    {"id": "H2", "objective": "O2", "statement": "thickness is sufficiently uniform for a controlled test",
     "test": "within-wafer profilometry", "null_result": "nonuniformity triggers deposition redesign"},
]
BASE["work_packages"] = [
    {"id": "WP1", "title": "coating and test", "objectives": ["O1", "O2"],
     "route_steps": ["R1", "R2"], "method": "templated deposition and paired assay",
     "data": "M1 and paired runs", "deliverable": "protocol and dataset",
     "acceptance": "H1/H2 evaluated with raw data retained", "start_month": 1, "end_month": 6}
]
BASE["data_plan"] = {
    "sources": [{"id": "M1", "version": "2025-03-14", "access": "existing lab records"}],
    "collection_method": "paired coated/uncoated measurements",
    "quality_control": "witness wafer and independent repeat",
    "analysis": "paired rate ratio with uncertainty and uniformity sensitivity analysis",
    "data_availability": "raw measurement tables with the report",
}
BASE["ethics"] = {"applicable": False,
                  "scope_explanation": "inorganic samples, no humans, personal data or animals"}


def d(**over):
    s = copy.deepcopy(BASE)
    s.update(over)
    return s


def out(**over):
    s = copy.deepcopy(BASE)
    s["outcomes"] = [{**o, **over} for o in copy.deepcopy(BASE["outcomes"])]
    return s


SCEN = [
    ("clean", lambda: (d(), [])),

    # the seven elements
    ("element_missing", lambda: (d(elements={k: v for k, v in BASE["elements"].items()
                                             if k != "risks"}), ["rp.element_missing"])),
    ("element_no_text", lambda: (d(elements={**BASE["elements"],
                                             "schedule": {"text": ""}}),
                                 ["rp.element_no_text"])),

    # gap statement, not a literature list
    ("gap_incomplete", lambda: (d(elements={**BASE["elements"],
                                            "background": {"known": "prior coatings work"}}),
                                ["rp.background_gap_incomplete"])),

    # claims traceable to material or reference, with a version
    ("claim_no_citation", lambda: (d(claims=[{"text": "40 nm coatings raised uptake"}]),
                                   ["rp.claim_no_citation"])),
    ("citation_unknown", lambda: (d(claims=[{"text": "prior rate change",
                                             "reference": "zhou2019",
                                             "version": "v1"}]),
                                  ["rp.citation_unknown"])),
    ("claim_no_version", lambda: (d(claims=[{"text": "prior rate change",
                                             "reference": "doe2020"}]),
                                  ["rp.claim_no_version"])),

    # objectives with criteria and a grounded threshold
    ("objective_no_criteria", lambda: (
        d(objectives=[{"id": "O1", "metric": "rate ratio", "sample": "n = 6"}]),
        ["rp.objective_no_criteria"])),
    ("threshold_no_basis", lambda: (
        d(objectives=[{**OBJECTIVES[0], "threshold_basis": ""}, OBJECTIVES[1]]),
        ["rp.threshold_no_basis"])),
    ("objectives_missing", lambda: (d(objectives=[]), ["rp.objectives_missing"])),

    # route: io, declared dependency, known dependency
    ("route_no_io", lambda: (
        d(route=[{k: v for k, v in ROUTE[0].items() if k != "output"}, ROUTE[1]]),
        ["rp.route_no_io"])),
    ("route_no_dependency", lambda: (
        d(route=[ROUTE[0], {**ROUTE[1], "depends_on": []}]),
        ["rp.route_no_dependency"])),
    ("first_step_no_dependency_ok", lambda: (
        d(route=[{**ROUTE[0], "depends_on": []}, ROUTE[1]]),
        [])),  # twin guard: the entry step is exempt, must stay silent
    ("route_dependency_unknown", lambda: (
        d(route=[ROUTE[0], {**ROUTE[1], "depends_on": ["R9"]}]),
        ["rp.route_dependency_unknown"])),

    # schedule inside the period, monotonic, with deliverables and a path
    ("period_no_schedule", lambda: (d(schedule=[]), ["rp.schedule_missing"])),
    ("schedule_exceeds_period", lambda: (
        d(schedule=[{"period": "P1", "end_month": 20,
                     "deliverable": "rate dataset", "on_critical_path": True}]),
        ["rp.schedule_exceeds_period"])),
    ("schedule_not_monotonic", lambda: (
        d(schedule=[SCHEDULE[0], {**SCHEDULE[1], "end_month": 4}]),
        ["rp.schedule_not_monotonic"])),
    ("equal_end_months_ok", lambda: (
        d(schedule=[SCHEDULE[0], {**SCHEDULE[1], "end_month": 6}]),
        [])),  # twin guard: phases ending together are not out of order
    ("milestone_no_deliverable", lambda: (
        d(schedule=[{"period": "P1", "end_month": 6, "on_critical_path": True},
                    SCHEDULE[1]]),
        ["rp.milestone_no_deliverable"])),
    ("critical_path_unmarked", lambda: (
        d(schedule=[{**SCHEDULE[0], "on_critical_path": False},
                    {**SCHEDULE[1], "on_critical_path": False}]),
        ["rp.critical_path_unmarked"])),

    # risks: classified, trigger/impact/fallback/decision point, both core kinds
    ("risks_missing", lambda: (d(risks=[]), ["rp.risks_missing"])),
    ("risk_no_fallback", lambda: (
        d(risks=[{**RISKS[0], "fallback": ""}, RISKS[1]]),
        ["rp.risk_no_fallback"])),
    ("risk_type_unknown", lambda: (
        d(risks=[{**RISKS[0], "type": "weather"}, RISKS[1]]),
        ["rp.risk_type_unknown"])),

    # outcomes: judged, and tied to objectives (对得上)
    ("outcomes_missing", lambda: (d(outcomes=[]), ["rp.outcomes_missing"])),
    ("outcome_no_assessment", lambda: (
        d(outcomes=[{**OUTCOMES[0], "assessment": ""}, OUTCOMES[1]]),
        ["rp.outcome_no_assessment"])),
    ("outcome_unmapped", lambda: (
        out(objectives=[]),
        ["rp.outcome_unmapped"])),
    ("outcome_unknown_objective", lambda: (
        out(objectives=["O9"]),
        ["rp.outcome_unmapped"])),
    ("outcome_mapped_ok", lambda: (d(), [])),  # twin guard: mapped outcomes stay silent

    # resource envelope
    ("resource_exceeds_budget", lambda: (d(resource_needed=64), ["rp.resource_exceeds_budget"])),

    # falsifiable hypotheses and executable work packages
    ("problem_not_falsifiable", lambda: (
        d(elements={**BASE["elements"], "problem": {"text": "coating improves uptake"}}),
        ["rp.problem_not_falsifiable"])),
    ("hypothesis_missing", lambda: (d(hypotheses=[BASE["hypotheses"][0]]),
                                    ["rp.hypothesis_missing_for_objective"])),
    ("hypothesis_incomplete", lambda: (
        d(hypotheses=[{**BASE["hypotheses"][0], "null_result": ""}, BASE["hypotheses"][1]]),
        ["rp.hypothesis_incomplete"])),
    ("hypothesis_unknown_objective", lambda: (
        d(hypotheses=[{**BASE["hypotheses"][0], "objective": "O9"}, BASE["hypotheses"][1]]),
        ["rp.hypothesis_unknown_objective"])),
    ("work_packages_missing", lambda: (d(work_packages=[]), ["rp.work_packages_missing"])),
    ("work_package_incomplete", lambda: (
        d(work_packages=[{**BASE["work_packages"][0], "acceptance": ""}]),
        ["rp.work_package_incomplete"])),
    ("work_package_unknown_ref", lambda: (
        d(work_packages=[{**BASE["work_packages"][0], "objectives": ["O9"], "route_steps": ["R9"]}]),
        ["rp.work_package_ref_unknown"])),
    ("route_not_in_work_package", lambda: (
        d(work_packages=[{**BASE["work_packages"][0], "route_steps": ["R1"]}]),
        ["rp.route_not_in_work_package"])),
    ("work_package_period_invalid", lambda: (
        d(work_packages=[{**BASE["work_packages"][0], "start_month": 7, "end_month": 6}]),
        ["rp.work_package_schedule_invalid"])),
    ("route_dependency_cycle", lambda: (
        d(route=[{**ROUTE[0], "depends_on": ["R2"]}, ROUTE[1]]),
        ["rp.route_dependency_cycle"])),

    # data, analysis and explicit applicable/not-applicable ethics governance
    ("data_plan_missing", lambda: (d(data_plan={}), ["rp.data_plan_missing"])),
    ("data_plan_incomplete", lambda: (
        d(data_plan={**BASE["data_plan"], "quality_control": ""}),
        ["rp.data_plan_incomplete"])),
    ("ethics_undeclared", lambda: (d(ethics={}), ["rp.ethics_undeclared"])),
    ("ethics_incomplete", lambda: (
        d(ethics={"applicable": True, "approval_status": "pending institutional review"}),
        ["rp.ethics_incomplete"])),
    ("ethics_data_mismatch", lambda: (
        d(data_plan={**BASE["data_plan"], "personal_data": True}), ["rp.ethics_data_mismatch"])),
    ("ethics_applicable_complete_ok", lambda: (
        d(ethics={"applicable": True, "approval_status": "pending; no recruitment before approval",
                  "consent": "written informed consent before enrollment",
                  "privacy": "pseudonymization with a separately controlled key",
                  "data_retention": "retain de-identified records for five years per protocol",
                  "oversight": "institutional review board"}), [])),
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
              "note": ("One scenario per opening-report scoring point, plus repaired-twin "
                       "guards for the dependency / schedule-shape / outcome-mapping rules. "
                       "Clean baselines must report nothing.")}
    (Path(__file__).resolve().parent / "report_plan.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n{passed}/{len(rows)} pass")
    return 0 if passed == len(rows) else 1


if __name__ == "__main__":
    raise SystemExit(main())
