"""Full deterministic regression bench for experiment-plan generation.
Run: python scripts/bench_generate.py [--report examples/bench-report.json]
"""
from __future__ import annotations

import argparse
import copy
import json
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))
import plan_engine as E  # noqa: E402

BASE = json.loads((ROOT / "examples" / "spec.json").read_text(encoding="utf-8"))
RESULTS = []


def check(name, condition, detail=""):
    RESULTS.append({"name": name, "passed": bool(condition), "detail": detail})


def rules(result):
    return {f["rule"] for f in result.get("findings", [])}


def mutated(fn):
    spec = copy.deepcopy(BASE)
    fn(spec)
    return spec


def expect_spec_error(name, spec):
    try:
        E.generate(spec)
    except E.SpecError as exc:
        check(name, True, str(exc))
    except Exception as exc:
        check(name, False, f"wrong exception {type(exc).__name__}: {exc}")
    else:
        check(name, False, "expected SpecError")


def expect_rule(name, spec, rule, status=None):
    try:
        result = E.generate(spec)
        check(name, rule in rules(result) and (status is None or result["status"] == status),
              json.dumps({"status": result["status"], "rules": sorted(rules(result))}, ensure_ascii=False))
        return result
    except Exception as exc:
        check(name, False, f"unexpected {type(exc).__name__}: {exc}")
        return {}


def run_engine_tests():
    clean = E.generate(copy.deepcopy(BASE))
    check("clean baseline has zero findings", clean["status"] == "clean" and clean["findings"] == [], json.dumps(clean["severity_counts"]))
    check("three candidate versions retained", len(clean["plan_versions"]) == 3)
    check("full factorial has four unique cells", len({r["cell"] for r in clean["design_matrix"]}) == 4)
    check("independent repeats not conflated with technical repeats", len(clean["design_matrix"]) == 12 and clean["selected_plan"]["sample_size"]["total_measurements"] == 24)
    check("cost arithmetic", clean["selected_plan"]["cost"]["total"] == 152)
    check("time arithmetic includes preparation and queue", clean["selected_plan"]["schedule"]["total_expected_hours"] == 12)
    check("declared weighted sum selects P3", clean["selected_plan"]["plan_id"] == "P3" and clean["ranking"][0]["score"] == 74.8)
    check("weight sensitivity is actually executed", len(clean["sensitivity_analysis"]["scenarios"]) == 6 and clean["sensitivity_analysis"]["stable_winner"] is True)
    check("randomized run ids are unique", len({r["run_id"] for r in clean["design_matrix"]}) == 12 and clean["selected_plan"]["randomization"]["run_order_generated"] is True)
    check("plan never claims execution", clean["selected_plan"]["lifecycle"] == "planned_not_executed" and clean["run_state"]["actual_experiment_executed"] is False)
    check("contract engine value has precedence", clean["status"] == "clean" and clean["case_id"] == BASE["case_id"])
    check("contract case value passthrough", clean["caller_note"] == BASE["caller_note"])
    check("contract unknown is null plus limit", clean["nonexistent_attachment"] is None and any("nonexistent_attachment" in x for x in clean["limits"]))
    check("engine deterministic in memory", clean == E.generate(copy.deepcopy(BASE)))

    expect_spec_error("refuse missing case_id", mutated(lambda s: s.pop("case_id")))
    expect_spec_error("refuse missing objective", mutated(lambda s: s.pop("objective")))
    expect_spec_error("refuse malformed candidates", mutated(lambda s: s.update(candidate_plans={})))
    expect_spec_error("refuse empty factors", mutated(lambda s: s.update(factors=[])))
    expect_spec_error("refuse duplicate factors", mutated(lambda s: s.update(factors=[s["factors"][0], s["factors"][0]])))
    expect_spec_error("refuse empty domain", mutated(lambda s: s["factors"][0].update(levels=[])))
    expect_spec_error("refuse invalid numeric step", mutated(lambda s: s.update(factors=[{"name": "x", "domain": {"min": 0, "max": 1, "step": 0}}])))
    expect_spec_error("refuse factorial explosion", mutated(lambda s: s["optimization"].update(max_combinations=3)))
    expect_spec_error("refuse nonfinite level", mutated(lambda s: s["factors"][1]["levels"][0].update(value=float("nan"))))

    parsed, count = E._normalise_factors([{"name": "x", "domain": {"min": 0, "max": 0.6, "step": 0.2}}])
    check("decimal finite domain inclusive", count == 4 and [x["value"] for x in parsed[0]["levels"]] == [0.0, 0.2, 0.4, 0.6])

    expect_rule("equipment out-of-range eliminates whole design", mutated(lambda s: s["factors"][1]["levels"][1].update(value=50)), "optimize.no_feasible_plan", "blocked")
    expect_rule("budget gate eliminates all candidates", mutated(lambda s: s["resources"]["budget"].update(amount=1)), "optimize.no_feasible_plan", "blocked")
    expect_rule("time gate eliminates all candidates", mutated(lambda s: s["resources"].update(time_window_hours=1)), "optimize.no_feasible_plan", "blocked")
    expect_rule("sample limit gate", mutated(lambda s: s["resources"].update(sample_limit=2)), "optimize.no_feasible_plan", "blocked")
    expect_rule("sample size missing", mutated(lambda s: s["sample_size"].pop("n_per_cell")), "sample_size.missing", "blocked")
    expect_rule("sample basis missing", mutated(lambda s: s["sample_size"].pop("basis")), "sample_size.basis_missing", "review")
    r = expect_rule("randomization missing", mutated(lambda s: s.pop("randomization")), "randomization.incomplete", "review")
    check("unrandomized order is honestly labelled", r.get("selected_plan", {}).get("randomization", {}).get("run_order_generated") is False)
    expect_rule("blinding missing", mutated(lambda s: s.pop("blinding")), "blinding.incomplete", "review")
    expect_rule("controls missing", mutated(lambda s: s["plan_template"].update(controls=[])), "control.missing", "blocked")

    def bad_variable(s):
        s["plan_template"]["variables"][0].pop("operational_definition")
    expect_rule("variable operational definition required", mutated(bad_variable), "variable.undefined", "blocked")
    expect_rule("outcome measurement required", mutated(lambda s: s["plan_template"]["variables"][2].pop("measurement")), "variable.measurement_missing", "blocked")
    expect_rule("confounder strategy required", mutated(lambda s: s["plan_template"]["variables"][3].pop("control_strategy")), "variable.confounder_uncontrolled", "review")

    def cycle(s):
        s["plan_template"]["steps"][0]["depends_on"] = ["S3"]
    expect_rule("step dependency cycle", mutated(cycle), "steps.dependency_cycle", "blocked")
    expect_rule("unknown step dependency", mutated(lambda s: s["plan_template"]["steps"][0].update(depends_on=["NOPE"])), "steps.unknown_dependency", "blocked")
    expect_rule("step failure decision required", mutated(lambda s: s["plan_template"]["steps"][0].pop("failure_action")), "steps.decision_missing", "blocked")
    expect_rule("decision threshold required", mutated(lambda s: s["plan_template"].update(decision_thresholds=[])), "threshold.missing", "blocked")
    expect_rule("multiplicity required for four cells", mutated(lambda s: s["plan_template"]["statistical_plan"].pop("multiple_comparisons")), "statistics.multiplicity_missing", "blocked")
    expect_rule("risk fallback required", mutated(lambda s: s["plan_template"].update(risks=[])), "risk.missing", "blocked")
    r = expect_rule("pending safety puts execution on hold", mutated(lambda s: s["plan_template"].update(safety={"status": "pending"})), "safety.approval_pending", "blocked")
    check("pending approval HOLD is explicit", r.get("selected_plan", {}).get("execution_gate") == "HOLD")
    expect_rule("ethics exemption needs rationale", mutated(lambda s: s["plan_template"].update(ethics={"status": "not_required"})), "ethics.rationale_missing", "review")
    expect_rule("missing resource blocks execution", mutated(lambda s: s["plan_template"]["materials"][0].update(state="missing")), "materials.unavailable", "blocked")
    expect_rule("criterion scale bounds required for clean", mutated(lambda s: s["optimization"]["criteria"][0].pop("scale_bounds")), "criterion.bounds_derived", "review")

    def no_evidence(s):
        for c in s["candidate_plans"]:
            c["evidence"] = {}
    expect_rule("criterion evidence required", mutated(no_evidence), "criterion.evidence_missing", "review")

    def no_rationale(s):
        for c in s["candidate_plans"]:
            c["rationales"] = {}
        s["optimization"]["criteria"][2].pop("rationale")
    expect_rule("criterion rationale required", mutated(no_rationale), "criterion.rationale_missing", "review")
    r = expect_rule("no preference criteria is not called optimum", mutated(lambda s: s["optimization"].update(criteria=[])), "optimize.criteria_missing", "review")
    check("no-criteria fallback stable and honest", r.get("selected_plan", {}).get("selection_basis", "").startswith("first feasible") and r.get("ranking") == [])

    def no_metric(s):
        for c in s["candidate_plans"]:
            c["metrics"] = {}
    expect_rule("missing score metric cannot be silently zero-filled", mutated(no_metric), "criterion.value_missing", "blocked")

    def mixed_currency(s):
        s["candidate_plans"][0]["cost_items"][1]["currency"] = "USD"
    expect_rule("unlike currencies are not added", mutated(mixed_currency), "cost.currency_mixed", "blocked")

    def powered(s, n):
        s["factors"] = [s["factors"][0]]
        s["sample_size"].update(n_per_cell=n, minimum_effect=1.0, sd=1.0, alpha=0.05, power=0.8, attrition_rate=0.1)
        s["resources"]["sample_limit"] = 50
        s["resources"]["time_window_hours"] = 30
        s["resources"]["budget"]["amount"] = 400
    r = expect_rule("underpowered declared n detected", mutated(lambda s: powered(s, 16)), "sample_size.underpowered", "blocked")
    calc = r.get("selected_plan", {}).get("sample_size", {}).get("power_calculation", {})
    check("power formula and attrition arithmetic exposed", calc.get("n_per_group_before_attrition") == 16 and calc.get("n_per_group_after_attrition") == 18, json.dumps(calc))
    r = E.generate(mutated(lambda s: powered(s, 18)))
    check("adequate power example clean", r["status"] == "clean" and r["selected_plan"]["sample_size"]["total_independent_runs"] == 36, json.dumps(r["severity_counts"]))
    expect_rule("two-group power approximation not misapplied to 2x2", mutated(lambda s: s["sample_size"].update(minimum_effect=1, sd=1)), "sample_size.power_model_mismatch", "blocked")

    def extra_controls(s):
        s["design"].update(control_runs_per_replication=2, control_conditions=[{"control_id": "negative", "treatment": "control", "temperature": 20}, {"control_id": "process"}])
        s["resources"].update(sample_limit=30)
        s["resources"]["budget"]["amount"] = 250
    r = E.generate(mutated(extra_controls))
    check("declared extra controls materialized", len(r["design_matrix"]) == 18 and r["selected_plan"]["sample_size"]["total_independent_runs"] == 18, str(r["status"]))
    expect_rule("extra controls require concrete conditions", mutated(lambda s: s["design"].update(control_runs_per_replication=2)), "design.control_conditions_mismatch", "blocked")

    def center(s):
        s["factors"] = [dict(s["factors"][1], equipment_id=None)]
        s["design"].update(center_points=1, center_values={"temperature": 25})
        s["resources"].update(sample_limit=20)
        s["resources"]["budget"]["amount"] = 250
    r = E.generate(mutated(center))
    check("declared center points materialized", len(r["design_matrix"]) == 9 and sum(1 for x in r["design_matrix"] if x["cell"] == "center") == 3, str(r["status"]))
    expect_rule("center values never invented", mutated(lambda s: s["design"].update(center_points=1)), "design.center_values_missing", "blocked")

    spec = mutated(lambda s: s.update(status="fake-clean", output_contract=["case_id", "status", "selected_plan", "unknown_field"]))
    r = E.generate(spec)
    check("list contract and engine precedence", r["status"] == "clean" and r["unknown_field"] is None)
    spec = mutated(lambda s: (s["resources"]["budget"].update(amount=1), s.update(selected_plan={"plan_id": "FAKE"})))
    r = E.generate(spec)
    check("caller cannot overwrite engine null selected plan", r["selected_plan"] is None and any("caller input cannot override" in x for x in r["limits"]))
    expect_rule("malformed candidate is named", mutated(lambda s: s["candidate_plans"].append("bad")), "candidate.malformed", "blocked")


def run_cli_tests():
    with tempfile.TemporaryDirectory(prefix="p74-bench-") as tmp:
        tmp = Path(tmp)
        cli = HERE / "plan_cli.py"
        valid = tmp / "valid.json"
        valid.write_text(json.dumps(BASE, ensure_ascii=False), encoding="utf-8")

        def invoke(path, out):
            return subprocess.run([sys.executable, str(cli), "--spec", str(path), "--out", str(out)], capture_output=True, text=True, timeout=30)

        proc = invoke(valid, tmp / "ok")
        check("CLI clean exit 0", proc.returncode == 0 and "Traceback" not in proc.stderr, proc.stderr)
        for name, content in (("malformed JSON", "{"), ("JSON array", "[]"), ("empty object", "{}"), ("NaN domain", '{"case_id":"x","objective":"x","factors":[{"name":"x","levels":[NaN]}],"candidate_plans":[{"plan_id":"P"}]}')):
            path = tmp / (name.replace(" ", "_") + ".json")
            path.write_text(content, encoding="utf-8")
            proc = invoke(path, tmp / ("out_" + name.replace(" ", "_")))
            try:
                result = json.loads((tmp / ("out_" + name.replace(" ", "_")) / "result.json").read_text(encoding="utf-8"))
            except Exception:
                result = {}
            check("CLI structured refusal: " + name, proc.returncode == 5 and result.get("status") == "undetermined" and "Traceback" not in proc.stderr, proc.stderr)
        missing = invoke(tmp / "does-not-exist.json", tmp / "missing-out")
        check("CLI missing file refusal", missing.returncode == 5 and "Traceback" not in missing.stderr, missing.stderr)
        bad_utf = tmp / "bad-utf8.json"
        bad_utf.write_bytes(b"\xff\xfe\x00")
        proc = invoke(bad_utf, tmp / "bad-utf-out")
        check("CLI invalid UTF-8 refusal", proc.returncode == 5 and "Traceback" not in proc.stderr, proc.stderr)

        review_spec = mutated(lambda s: s["sample_size"].pop("basis"))
        review_path = tmp / "review.json"
        review_path.write_text(json.dumps(review_spec, ensure_ascii=False), encoding="utf-8")
        check("CLI review exit 3", invoke(review_path, tmp / "review-out").returncode == 3)
        blocked_spec = mutated(lambda s: s["plan_template"].update(risks=[]))
        blocked_path = tmp / "blocked.json"
        blocked_path.write_text(json.dumps(blocked_spec, ensure_ascii=False), encoding="utf-8")
        check("CLI blocked exit 4", invoke(blocked_path, tmp / "blocked-out").returncode == 4)

        wrapped = {"case_id": BASE["case_id"], "output_contract": BASE["output_contract"], "inputs": {k: v for k, v in BASE.items() if k not in ("case_id", "output_contract")}}
        wrapped_path = tmp / "case.json"
        wrapped_path.write_text(json.dumps(wrapped, ensure_ascii=False), encoding="utf-8")
        proc = subprocess.run([sys.executable, str(cli), "--case", str(wrapped_path), "--out", str(tmp / "case-out")], capture_output=True, text=True, timeout=30)
        check("CLI original case wrapper", proc.returncode == 0 and json.loads((tmp / "case-out" / "result.json").read_text(encoding="utf-8"))["case_id"] == BASE["case_id"], proc.stderr)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--report")
    args = parser.parse_args()
    run_engine_tests()
    run_cli_tests()
    passed = sum(x["passed"] for x in RESULTS)
    report = {"schema": "bench-generate/v1", "engine_schema": E.SCHEMA,
              "total": len(RESULTS), "passed": passed, "failed": len(RESULTS) - passed,
              "clean_baseline_findings": 0, "results": RESULTS}
    text = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if args.report:
        Path(args.report).write_text(text, encoding="utf-8")
    print(json.dumps({"total": len(RESULTS), "passed": passed, "failed": len(RESULTS) - passed}))
    for item in RESULTS:
        if not item["passed"]:
            print("FAIL", item["name"], item["detail"])
    return 0 if passed == len(RESULTS) else 1


if __name__ == "__main__":
    raise SystemExit(main())
