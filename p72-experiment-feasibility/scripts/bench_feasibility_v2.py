"""Executable checks for versioned feasibility resource arithmetic and review gates."""
from __future__ import annotations

import copy
import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from feasibility import CATEGORIES, build, evaluate, run  # noqa: E402


def base():
    return {
        "units": {"total_samples": "samples", "total_cost": "CNY"},
        "source_record": {"scenario": "synthetic method test; not a real vendor quote or facility"},
        "inventory": [
            {"resource_id": "T_sensor_range", "status": "present", "source": "synthetic equipment inventory rev2",
             "capabilities": {"max_temperature": {"value": 120, "unit": "C"}}},
            {"resource_id": "centrifuge_capacity", "status": "external_confirmed", "confirmed": True,
             "source": "synthetic prospective booking scenario rev3"},
            {"resource_id": "reagent_A", "status": "external_confirmed", "confirmed": True,
             "source": "synthetic prospective procurement scenario rev1", "lead_time_hours": 48,
             "available_quantity": 2, "unit": "mL"},
        ],
        "hard_constraints": [
            {"id": "samples-limit", "metric": "total_samples", "op": "<=", "value": 40,
             "unit": "samples", "source": "synthetic protocol sample limit"},
            {"id": "budget-limit", "metric": "total_cost", "op": "<=", "value": 3000,
             "source": "synthetic resource contract"},
            {"id": "temperature-range", "metric": "parameter.temperature", "op": "<=", "value": 100,
             "unit": "C", "source": "synthetic equipment manual"},
        ],
        "plan_versions": [{
            "plan_id": "plan-v2", "source_version": "synthetic-plan@2", "source_locator": "method fixture",
            "hypothesis": "synthetic temperature-response hypothesis", "variables": {"independent": "temperature", "dependent": "response"},
            "controls": [{"control_id": "baseline", "source": "synthetic protocol"}], "judgement_criteria": "reported variation and pass/fail thresholds are declared",
            "steps": [{"step_id": "prepare", "sample_units": 12, "device_hours": 1,
                        "person_hours": 2, "waiting_hours": 8, "elapsed_hours": 10,
                        "material_quantity": 2, "unit_price": {"amount": 100, "currency": "CNY"}},
                       {"step_id": "measure", "sample_units": 12, "device_hours": 1,
                        "person_hours": 1, "waiting_hours": 1, "elapsed_hours": 2,
                        "independent_runs": 2, "material_quantity": 1,
                        "unit_price": {"amount": 100, "currency": "CNY"}}],
            "sampling": {"per_step": True},
            "parameters": {"temperature": 80}, "units": {"parameter.temperature": "C"},
            "parameter_domains": {"temperature": [60, 80, 100]},
            "equipment_requirements": [{"resource_id": "T_sensor_range", "capability": "max_temperature",
                                        "min_value": 100, "unit": "C", "source": "synthetic protocol"},
                                       {"resource_id": "centrifuge_capacity", "source": "synthetic protocol"}],
            "material_requirements": [{"resource_id": "reagent_A", "quantity": 2, "unit": "mL",
                                       "source": "synthetic protocol"}],
            "metrics": {"total_time_hours": 14},
            "ethics": {"involvement": {"human_samples": False, "animals": False,
                                         "personal_data": False, "biohazard": False}, "approvals": []},
            "safety": {"hazards": []},
            "risks": [{"trigger": "sensor outside range", "response": "stop and use verified alternative", "source": "synthetic SOP"}],
        }],
    }


def scenarios():
    yield "clean_resource_arithmetic", base(), "clean", None
    s = base(); s["plan_versions"][0]["sampling"] = {"groups": [
        {"group_id": "G1", "units": 12, "independent_batches": 2, "technical_replicates": 5}]}
    yield "technical_repeats_are_not_independent_samples", s, "clean", None
    s = base(); s["hard_constraints"][0]["value"] = 10
    yield "sample_consumption_blocks", s, "blocked", "feasibility.hard_constraint_violated"
    s = base(); s["plan_versions"][0]["parameters"]["temperature"] = 130
    yield "temperature_conflict_blocks", s, "blocked", "feasibility.hard_constraint_violated"
    s = base(); s["inventory"][2]["confirmed"] = False
    yield "prospective_procurement_is_conditional", s, "review", "feasibility.constraint_unknown"
    s = base(); s["plan_versions"][0]["material_requirements"][0]["quantity"] = 3
    yield "confirmed_supply_allows_larger_planned_order", s, "clean", None
    s = base(); s["inventory"][2].update(status="missing", available_quantity=0)
    yield "stock_unavailable_blocks", s, "blocked", "feasibility.hard_constraint_violated"
    s = base(); s["inventory"][2].update(confirmed=True, available_quantity=2, lead_time_hours=999)
    yield "only_arithmetic_supply_not_schedule", s, "clean", None
    s = base(); s["plan_versions"][0]["ethics"]["involvement"]["human_samples"] = True
    s["plan_versions"][0]["ethics"]["approvals"] = [{"scope": "human_samples", "status": "pending", "source": "synthetic prospective approval"}]
    yield "approval_pending_not_execution_ready", s, "review", "feasibility.constraint_unknown"
    s = base(); s["plan_versions"][0]["ethics"]["involvement"]["human_samples"] = True
    yield "declared_ethics_without_approval_blocks", s, "blocked", "feasibility.hard_constraint_violated"
    s = base(); s["plan_versions"][0]["safety"] = {"hazards": [{"name": "synthetic hazard", "required_controls": []}]}
    yield "unverified_safety_control_blocks", s, "blocked", "feasibility.hard_constraint_violated"
    s = base(); del s["plan_versions"][0]["controls"]
    yield "absence_is_not_pass", s, "review", "feasibility.coverage_incomplete"
    s = base(); s["hard_constraints"][0]["metric"] = "total_samples_typo"
    yield "unknown_metric_not_satisfied", s, "review", "feasibility.constraint_unknown"
    s = base(); s["hard_constraints"][0]["unit"] = "millilitre"
    yield "unit_mismatch_named", s, "review", "feasibility.constraint_unknown"
    s = base(); s["plan_versions"].append(dict(copy.deepcopy(s["plan_versions"][0]), plan_id="plan-v1", parameters={"temperature": 130}))
    s["plan_versions"][1]["source_version"] = "synthetic-plan@1"
    yield "three_state_versions_preserved", s, "review", "feasibility.hard_constraint_violated"
    s = base(); s["plan_versions"][0]["metrics"] = {"total_samples": "not counted"}
    yield "bad_numbers_do_not_crash", s, "review", None


def main():
    reports = []
    names = set()
    for name, spec, expected, rule in scenarios():
        r = evaluate(spec, spec["plan_versions"][0], 0)
        rules = {f["rule"] for f in r["findings"]}
        core = r["constraint_results"]
        sample_ok = (r["derived_metrics"]["total_samples"] is None if name == "bad_numbers_do_not_crash"
                      else r["derived_metrics"]["total_samples"] == 24 if name == "technical_repeats_are_not_independent_samples"
                      else r["derived_metrics"]["total_samples"] == 36)
        if name == "technical_repeats_are_not_independent_samples":
            sample_ok = sample_ok and r["derived_metric_arithmetic"]["steps"][-1]["exclude_technical_repetitions"] is True
        cost_ok = r["derived_metrics"]["total_cost"] == 400
        expected_status = expected
        expected_rule = rule
        if name == "three_state_versions_preserved":
            r2 = evaluate(spec, spec["plan_versions"][1], 1)
            overall = run(spec)
            names.update([r2["verdict"]])
            expected_status = "clean"  # clean first version, blocked second version
            expected_rule = None
            expected_plan_status = (r2["status"] == "blocked"
                                    and rule in {f["rule"] for f in r2["findings"]}
                                    and overall["status"] == "blocked"
                                    and len(overall["version_reviews"]) == 2)
        else:
            expected_plan_status = True
        ok = r["status"] == expected_status and expected_plan_status and sample_ok and cost_ok and (expected_rule is None or expected_rule in rules) and [x["category"] for x in r["seven_category_coverage"]] == list(CATEGORIES)
        reports.append({"scenario": name, "pass": ok, "status": r["status"], "rules": sorted(rules),
                        "derived_metrics": r["derived_metrics"]})
        print(("PASS" if ok else "FAIL") + "  " + name + f" ({r['verdict']}, samples={r['derived_metrics']['total_samples']}, cost={r['derived_metrics']['total_cost']})")
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        spec = base(); spec["case_id"] = "synthetic-contract-fixture"
        spec["output_contract"] = ["feasibility_review", "evidence", "required_confirmations"]
        sp = tmp / "spec.json"; sp.write_text(json.dumps(spec, ensure_ascii=False), encoding="utf-8")
        r = build(sp, tmp / "out")
        ok = all(k in r for k in spec["output_contract"]) and r["case_id"] == "synthetic-contract-fixture" and r["status"] == "clean"
        reports.append({"scenario": "contract_and_identity", "pass": ok})
        print(("PASS" if ok else "FAIL") + "  contract_and_identity")
        two = build(sp, tmp / "out2")
        ok = json.dumps(r, sort_keys=True, ensure_ascii=False) == json.dumps(two, sort_keys=True, ensure_ascii=False)
        reports.append({"scenario": "determinism", "pass": ok}); print(("PASS" if ok else "FAIL") + "  determinism")
        sp.write_text("{broken", encoding="utf-8")
        cp = tmp / "case.json"; cp.write_text(json.dumps({"case_id": "synthetic-contract-fixture", "output_contract": ["feasibility_review", "evidence", "required_confirmations"]}), encoding="utf-8")
        r = build(sp, tmp / "refusal", cp)
        ok = (r["status"] == "undetermined" and r["case_id"] == "synthetic-contract-fixture"
              and all(k in r for k in ("feasibility_review", "evidence", "required_confirmations")))
        reports.append({"scenario": "structured_refusal", "pass": ok}); print(("PASS" if ok else "FAIL") + "  structured_refusal")
    passed = sum(1 for r in reports if r["pass"])
    root = Path(__file__).resolve().parent.parent
    (root / "examples" / "feasibility-bench-report.json").write_text(
        json.dumps({"schema_version": "feasibility-bench/v2", "scenarios": reports,
                    "totals": {"passed": passed, "of": len(reports)}}, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n{passed}/{len(reports)} scenarios pass")
    return 0 if passed == len(reports) else 1


if __name__ == "__main__":
    raise SystemExit(main())
