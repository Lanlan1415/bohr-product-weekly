"""Full deterministic regression bench for aligned experiment-plan comparison.
Run: python scripts/bench_compare.py [--report examples/bench-report.json]
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
import compare_engine as E  # noqa: E402

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
        E.compare(spec)
    except E.SpecError as exc:
        check(name, True, str(exc))
    except Exception as exc:
        check(name, False, f"wrong exception {type(exc).__name__}: {exc}")
    else:
        check(name, False, "expected SpecError")


def expect_rule(name, spec, rule, status=None):
    try:
        result = E.compare(spec)
        check(name, rule in rules(result) and (status is None or result["status"] == status),
              json.dumps({"status": result["status"], "rules": sorted(rules(result))}, ensure_ascii=False))
        return result
    except Exception as exc:
        check(name, False, f"unexpected {type(exc).__name__}: {exc}")
        return {}


def candidate(spec, pid):
    return next(c for c in spec["candidate_plans"] if c["plan_id"] == pid)


def run_engine_tests():
    clean = E.compare(copy.deepcopy(BASE))
    check("clean baseline zero findings", clean["status"] == "clean" and clean["findings"] == [], json.dumps(clean["severity_counts"]))
    check("three versions and fifteen evidence cells", len(clean["plan_versions"]) == 3 and len(clean["evidence_matrix"]) == 15)
    evaluations = {c["plan_id"]: c for c in clean["candidate_evaluations"]}
    check("cost arithmetic all candidates", [evaluations[p]["total_cost"] for p in ("P1", "P2", "P3")] == [100, 210, 140])
    check("time includes preparation queue expected rework", [evaluations[p]["total_time_hours"] for p in ("P1", "P2", "P3")] == [12, 20, 16])
    check("over-budget P2 is eliminated despite soft values", evaluations["P2"]["gate_status"] == "failed" and evaluations["P2"]["score"] is None)
    check("only eligible plans ranked", [x["plan_id"] for x in clean["ranking"]] == ["P3", "P1"])
    check("weighted arithmetic verified", clean["ranking"][0]["score"] == 66.8 and clean["ranking"][1]["score"] == 62.25)
    check("every matrix cell has evidence", all(x["evidence_status"] == "present" and x["evidence_refs"] for x in clean["evidence_matrix"]))
    check("tradeoffs include all three accepted disadvantages", {x["criterion"] for x in clean["tradeoffs"][0]["winner_disadvantages"]} == {"total_cost", "total_time_hours", "risk_score"})
    check("weight sensitivity executed", len(clean["sensitivity_analysis"]["scenarios"]) == 10 and clean["sensitivity_analysis"]["winner_stable"] is True)
    check("exact flip thresholds calculated", len(clean["sensitivity_analysis"]["exact_top_two_weight_flip_thresholds"]) == 5)
    check("uncertainty corners executed", len(clean["uncertainty_analysis"]["scenarios"]) == 10 and clean["uncertainty_analysis"]["winner_stable"] is True)
    check("fallback has concrete triggers", clean["fallback_plan"]["plan_id"] == "P1" and len(clean["fallback_plan"]["triggers"]) == 2)
    check("contract case value passthrough", clean["caller_note"] == BASE["caller_note"])
    check("contract unknown null plus limit", clean["unknown_figure"] is None and any("unknown_figure" in x for x in clean["limits"]))
    check("no experiment claimed", clean["run_state"]["actual_experiment_executed"] is False and clean["comparison_summary"]["execution_status"] == "not_executed")
    check("deterministic in memory", clean == E.compare(copy.deepcopy(BASE)))

    expect_spec_error("refuse missing case_id", mutated(lambda s: s.pop("case_id")))
    expect_spec_error("refuse missing objective", mutated(lambda s: s.pop("objective")))
    expect_spec_error("refuse fewer than two candidates", mutated(lambda s: s.update(candidate_plans=s["candidate_plans"][:1])))
    expect_spec_error("refuse empty criteria", mutated(lambda s: s.update(criteria=[])))
    expect_spec_error("refuse duplicate criteria", mutated(lambda s: s["criteria"].append(copy.deepcopy(s["criteria"][0]))))
    expect_spec_error("refuse negative weight", mutated(lambda s: s["criteria"][0].update(weight=-1)))
    expect_spec_error("refuse zero total weight", mutated(lambda s: [c.update(weight=0) for c in s["criteria"]]))
    expect_spec_error("refuse invalid direction", mutated(lambda s: s["criteria"][0].update(direction="sideways")))
    expect_spec_error("refuse duplicate plan id", mutated(lambda s: s["candidate_plans"][1].update(plan_id="P1")))
    expect_spec_error("refuse malformed candidate", mutated(lambda s: s["candidate_plans"].append("bad")))
    expect_spec_error("refuse malformed constraint collection", mutated(lambda s: s.update(hard_constraints={})))
    expect_spec_error("refuse invalid sensitivity delta", mutated(lambda s: s["sensitivity"].update(weight_delta=0)))

    expect_rule("no hard constraints warning", mutated(lambda s: s.update(hard_constraints=[])), "constraint.none_declared", "review")
    expect_rule("malformed constraint never silently passes", mutated(lambda s: s["hard_constraints"].append({"id": "BAD"})), "constraint.malformed", "blocked")
    r = expect_rule("all candidates over budget gives no recommendation", mutated(lambda s: s["hard_constraints"][0].update(value=50)), "compare.no_feasible_plan", "blocked")
    check("all infeasible recommendation is null", r.get("recommendation") is None) 
    spec = mutated(lambda s: (s["hard_constraints"][0].update(value=50), s.update(recommendation={"plan_id": "FAKE"})))
    r = E.compare(spec)
    check("caller cannot overwrite engine null recommendation", r["recommendation"] is None and any("caller input cannot override" in x for x in r["limits"]))

    def equipment_unavailable(s):
        candidate(s, "P3")["plan"]["resources"]["equipment_available"] = False
    r = E.compare(mutated(equipment_unavailable))
    check("resource gate switches recommendation to P1", r["recommendation"]["plan_id"] == "P1" and any(x["plan_id"] == "P3" for x in r["eliminated_plans"]), r["status"])
    expect_rule("unknown hard gate cannot pass", mutated(lambda s: s["hard_constraints"][0].update(metric="missing_metric")), "compare.no_feasible_plan", "blocked")

    def gate_uncertain(s):
        candidate(s, "P3")["plan"]["uncertainties"]["total_cost"]["upper"] = 220
    r = E.compare(mutated(gate_uncertain))
    p3_gate = next(x for x in r["constraint_results"] if x["plan_id"] == "P3")
    check("constraint interval crossing makes candidate ineligible", p3_gate["gate_status"] == "unknown" and any(x.get("uncertainty_gate") for x in p3_gate["constraints"]), r["status"])

    expect_rule("criterion missing value high", mutated(lambda s: candidate(s, "P3")["plan"]["metrics"].pop("evidence_strength")), "criterion.value_missing", "blocked")
    expect_rule("criterion missing evidence high", mutated(lambda s: candidate(s, "P3")["plan"]["evidence"].pop("risk_score")), "evidence.missing", "blocked")

    def unknown_source(s):
        candidate(s, "P3")["plan"]["evidence"]["risk_score"] = ["SRC-DOES-NOT-EXIST"]
    expect_rule("unknown evidence source high", mutated(unknown_source), "evidence.unknown_source", "blocked")
    expect_rule("score rationale required", mutated(lambda s: candidate(s, "P3")["plan"]["rationales"].pop("risk_score")), "evidence.rationale_missing", "review")
    r = expect_rule("derived scale is explicit review", mutated(lambda s: s["criteria"][0].pop("scale_bounds")), "criterion.bounds_derived", "review")
    cells = [x for x in r["scoring_matrix"] if x["criterion"] == "scientific_alignment"]
    check("derived minmax still discriminates", next(x for x in cells if x["plan_id"] == "P1")["normalised"] == 0 and next(x for x in cells if x["plan_id"] == "P3")["normalised"] == 1)
    expect_rule("outside scale clipped and named", mutated(lambda s: candidate(s, "P3")["plan"]["metrics"].update(risk_score=6)), "criterion.outside_scale", "review")
    r = expect_rule("declared cost mismatch corrected by arithmetic", mutated(lambda s: candidate(s, "P3")["plan"]["metrics"].update(total_cost=999)), "cost.total_mismatch", "blocked")
    check("engine cost has precedence over fake declared total", next(x for x in r["candidate_evaluations"] if x["plan_id"] == "P3")["total_cost"] == 140)
    expect_rule("negative cost item rejected", mutated(lambda s: candidate(s, "P3")["plan"]["cost_items"][0].update(quantity=-1)), "cost.invalid_item", "blocked")

    def mixed_currency(s):
        candidate(s, "P3")["plan"]["cost_items"][1]["currency"] = "USD"
    expect_rule("mixed currencies rejected", mutated(mixed_currency), "cost.currency_mixed", "blocked")
    expect_rule("per-run cost requires n_runs", mutated(lambda s: candidate(s, "P3")["plan"].pop("n_runs")), "cost.multiplier_missing", "blocked")

    def unitemised_cost(s):
        plan = candidate(s, "P3")["plan"]
        plan.pop("cost_items")
        plan["evidence"]["total_cost"] = ["SRC-QUOTE"]
    expect_rule("unitemised cost is a visible limit", mutated(unitemised_cost), "cost.not_itemised", "review")
    expect_rule("declared time mismatch corrected", mutated(lambda s: candidate(s, "P3")["plan"]["metrics"].update(total_time_hours=99)), "time.total_mismatch", "blocked")
    expect_rule("negative time item rejected", mutated(lambda s: candidate(s, "P3")["plan"]["time_items"][0].update(hours=-1)), "time.invalid_item", "blocked")

    def unitemised_time(s):
        plan = candidate(s, "P3")["plan"]
        plan.pop("time_items")
        plan["evidence"]["total_time_hours"] = ["SRC-BOOKING"]
    expect_rule("unitemised time is a visible limit", mutated(unitemised_time), "time.not_itemised", "review")
    expect_rule("invalid uncertainty interval", mutated(lambda s: candidate(s, "P3")["plan"]["uncertainties"].update(total_cost={"lower": 200, "upper": 100})), "uncertainty.invalid_interval", "review")
    expect_rule("malformed uncertainty collection", mutated(lambda s: candidate(s, "P3")["plan"].update(uncertainties="unknown")), "uncertainty.malformed", "review")

    def unstable_uncertainty(s):
        candidate(s, "P3")["plan"]["uncertainties"]["evidence_strength"]["lower"] = 3
    r = expect_rule("winner instability under interval is reported", mutated(unstable_uncertainty), "uncertainty.winner_unstable", "review")
    check("unstable uncertainty is recorded in recommendation", r["recommendation"]["robust_to_declared_interval_probes"] is False and r["uncertainty_analysis"]["winner_stable"] is False)
    r = expect_rule("large weight probe exposes instability", mutated(lambda s: s["sensitivity"].update(weight_delta=0.9)), "sensitivity.winner_unstable", "review")
    check("unstable weight is recorded in recommendation", r["recommendation"]["robust_to_weight_probe"] is False)
    expect_rule("fallback triggers required", mutated(lambda s: s.update(fallback_triggers=[])), "fallback.triggers_missing", "review")
    expect_rule("fallback target validated", mutated(lambda s: s["fallback_triggers"][0].update(target_plan_id="NOPE")), "fallback.malformed", "blocked")

    def only_p1(s):
        for pid in ("P2", "P3"):
            candidate(s, pid)["plan"]["resources"]["equipment_available"] = False
    expect_rule("one eligible plan means no validated runner-up", mutated(only_p1), "fallback.no_runner_up", "review")

    def tied(s):
        clone = copy.deepcopy(s["candidate_plans"][0])
        clone["plan_id"] = "P2"
        clone["version"] = "v1.0-copy"
        s["candidate_plans"] = [s["candidate_plans"][0], clone]
    r = expect_rule("top tie is not hidden", mutated(tied), "recommendation.tie", "review")
    check("tie flag propagated", r["recommendation"]["tie"] is True)

    r = E.compare(mutated(lambda s: s.update(status="fake", output_contract=["case_id", "status", "recommendation", "missing"])))
    check("list contract and engine precedence", r["status"] == "clean" and r["missing"] is None)
    r = E.compare(mutated(lambda s: s.update(sources=[])))
    check("unregistered evidence allowed only when no registry declared", r["status"] == "clean")

    def no_intervals(s):
        for c in s["candidate_plans"]:
            c["plan"].pop("uncertainties", None)
    r = E.compare(mutated(no_intervals))
    check("no intervals is explicit not fabricated", r["uncertainty_analysis"]["assessed"] is False and r["status"] == "clean")
    r = E.compare(mutated(lambda s: candidate(s, "P3")["plan"]["metrics"].update(total_cost=999)))
    check("high finding blocks execution status", r["recommendation"]["selection_status"] == "blocked_by_findings_do_not_execute")


def run_cli_tests():
    with tempfile.TemporaryDirectory(prefix="p75-bench-") as tmp:
        tmp = Path(tmp)
        cli = HERE / "compare_cli.py"
        valid = tmp / "valid.json"
        valid.write_text(json.dumps(BASE, ensure_ascii=False), encoding="utf-8")

        def invoke(path, out):
            return subprocess.run([sys.executable, str(cli), "--spec", str(path), "--out", str(out)], capture_output=True, text=True, timeout=30)

        proc = invoke(valid, tmp / "ok")
        check("CLI clean exit 0", proc.returncode == 0 and "Traceback" not in proc.stderr, proc.stderr)
        for name, content in (("malformed JSON", "{"), ("JSON array", "[]"), ("empty object", "{}"), ("NaN weight", '{"case_id":"x","objective":"x","criteria":[{"name":"a","weight":NaN}],"candidate_plans":[{},{}]}')):
            path = tmp / (name.replace(" ", "_") + ".json")
            path.write_text(content, encoding="utf-8")
            out = tmp / ("out_" + name.replace(" ", "_"))
            proc = invoke(path, out)
            try:
                result = json.loads((out / "result.json").read_text(encoding="utf-8"))
            except Exception:
                result = {}
            check("CLI structured refusal: " + name, proc.returncode == 5 and result.get("status") == "undetermined" and "Traceback" not in proc.stderr, proc.stderr)
        proc = invoke(tmp / "not-found.json", tmp / "missing-out")
        check("CLI missing file refusal", proc.returncode == 5 and "Traceback" not in proc.stderr, proc.stderr)
        bad_utf = tmp / "bad-utf8.json"
        bad_utf.write_bytes(b"\xff\xfe")
        proc = invoke(bad_utf, tmp / "bad-utf-out")
        check("CLI invalid UTF-8 refusal", proc.returncode == 5 and "Traceback" not in proc.stderr, proc.stderr)

        review = mutated(lambda s: s.update(fallback_triggers=[]))
        path = tmp / "review.json"
        path.write_text(json.dumps(review, ensure_ascii=False), encoding="utf-8")
        check("CLI review exit 3", invoke(path, tmp / "review-out").returncode == 3)
        blocked = mutated(lambda s: candidate(s, "P3")["plan"]["metrics"].update(total_cost=999))
        path = tmp / "blocked.json"
        path.write_text(json.dumps(blocked, ensure_ascii=False), encoding="utf-8")
        check("CLI blocked exit 4", invoke(path, tmp / "blocked-out").returncode == 4)

        wrapped = {"case_id": BASE["case_id"], "output_contract": BASE["output_contract"], "inputs": {k: v for k, v in BASE.items() if k not in ("case_id", "output_contract")}}
        path = tmp / "case.json"
        path.write_text(json.dumps(wrapped, ensure_ascii=False), encoding="utf-8")
        proc = subprocess.run([sys.executable, str(cli), "--case", str(path), "--out", str(tmp / "case-out")], capture_output=True, text=True, timeout=30)
        check("CLI original case wrapper", proc.returncode == 0 and json.loads((tmp / "case-out" / "result.json").read_text(encoding="utf-8"))["case_id"] == BASE["case_id"], proc.stderr)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--report")
    args = parser.parse_args()
    run_engine_tests()
    run_cli_tests()
    passed = sum(x["passed"] for x in RESULTS)
    report = {"schema": "bench-compare/v1", "engine_schema": E.SCHEMA,
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
