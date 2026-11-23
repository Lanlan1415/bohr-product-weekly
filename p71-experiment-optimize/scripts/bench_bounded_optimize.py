"""Executable arithmetic, constraint, uncertainty and reproducibility benches."""
from __future__ import annotations

import copy
import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from bounded_optimize import build, lhs, optimize, summary  # noqa: E402


def base():
    return {
        "variables": [
            {"name": "temperature", "kind": "continuous", "values": [60, 70, 80, 90, 100],
             "unit": "C", "source": "synthetic equipment range rev1"},
            {"name": "pH", "kind": "discrete", "values": [6, 7, 8], "unit": "1",
             "source": "synthetic protocol domain rev2"}],
        "hard_constraints": [{"id": "T-limit", "metric": "parameter.temperature", "op": "<=",
                                "value": 100, "unit": "C", "source": "synthetic equipment manual"},
                              {"id": "cost-limit", "metric": "total_cost", "op": "<=", "value": 100,
                                "unit": "CNY", "source": "synthetic budget contract"},
                              {"id": "time-limit", "metric": "total_time_hours", "op": "<=", "value": 20,
                                "source": "synthetic scheduling contract"},
                              {"id": "sample-limit", "metric": "total_samples", "op": "<=", "value": 24,
                                "source": "synthetic sample allocation"}],
        "response_models": {"yield": {"kind": "polynomial", "intercept": 60,
             "coefficients": {"temperature": 1.2, "pH": 0.4}, "quadratic": {"temperature": -0.006},
             "source": "explicit synthetic calibration function; not a real measurement"}},
        "cost_model": {"intercept": 15, "coefficients": {"temperature": 0.2, "pH": 0.1},
                        "source": "explicit synthetic prospective price ledger"},
        "time_model": {"intercept": 2, "coefficients": {"temperature": 0.01},
                        "source": "explicit synthetic prospective timing ledger"},
        "sample_model": {"intercept": 12, "source": "explicit synthetic sample contract"},
        "objectives": [{"name": "yield", "direction": "maximize", "weight": 1,
                         "unit": "%", "measurement": "explicit synthetic response equation",
                         "tolerance": {"absolute": 0.5, "source": "synthetic acceptance protocol"}}],
        "baseline": {"parameters": {"temperature": 60, "pH": 6},
                      "source": "explicit synthetic baseline"},
        "study_design": {"independent_replicates": 2},
        "search": {"seed": 42, "max_evaluations": 16, "patience": 2, "improvement_tolerance": 0.001},
    }


def main():
    reports = []
    def record(name, ok, extra=None):
        reports.append({"scenario": name, "pass": bool(ok), "detail": extra or {}})
        print(("PASS" if ok else "FAIL") + "  " + name + ("  " + str(extra) if extra else ""))

    r = optimize(base())
    selected = r["recommended_parameters"]
    record("known_polynomial_optimum", selected == {"temperature": 100.0, "pH": 8.0}, selected)
    record("resource_arithmetic", r["recommendation"]["cost_and_resource_metrics"]["total_cost"] == 71.6
           and r["recommendation"]["cost_and_resource_metrics"]["total_samples"] == 24)
    record("baseline_difference", r["baseline_comparisons"]["responses"]["yield"]["delta"] > 0)
    record("morris_elementary_effects", len(r["parameter_sensitivity"]["results"]) == 2
           and all(x["n_elementary_effects"] >= 2 for x in r["parameter_sensitivity"]["results"]))
    record("weight_sensitivity_full_rerank", len(r["weight_sensitivity"]["scenarios"]) == 2)
    record("stop_rules_and_seed", r["search_record"]["seed"] == 42
           and r["search_record"]["stop_rules"]["improvement_tolerance"] == 0.001
           and r["search_record"]["actual_stop_reason"])
    record("all_candidates_traceable", all(p["responses"] and p["gate"] and p["evaluation_index"] for p in r["candidate_evaluations"]))

    s = base(); s["hard_constraints"][0]["value"] = 80
    limited = optimize(s)
    record("hard_constraint_changes_optimum", limited["recommended_parameters"]["temperature"] == 80,
           limited["recommended_parameters"])
    record("all_selected_constraints_pass", all(c["status"] == "pass" for c in limited["recommendation"]["constraint_results"]))

    s = base(); s["objectives"].append({"name": "total_cost", "direction": "minimize", "weight": 0.4,
             "unit": "CNY", "measurement": "price arithmetic", "tolerance": {"absolute": 1.0}})
    multi = optimize(s)
    record("response_cost_multi_objective", all(not p["unknown_objective_values"] for p in multi["candidate_evaluations"] if p["gate"]["status"] == "feasible")
           and len(multi["weight_sensitivity"]["scenarios"]) == 4)

    s = base(); s["hard_constraints"][0]["op"] = ">="
    s["hard_constraints"][0]["value"] = 130
    no = optimize(s)
    record("infeasible_not_pretended_optimum", no["recommended_parameters"] is None
           and no["status"] == "blocked" and "optimization.no_feasible_complete_point" in {f["rule"] for f in no["findings"]})

    s = base(); del s["response_models"]
    missing = optimize(s)
    record("unknown_response_not_fabricated", missing["recommended_parameters"] is None
           and all(p["responses"]["yield"]["kind"] == "unknown" for p in missing["candidate_evaluations"]))

    # Matched observed repeats on both baseline and candidate: no model needed for these points.
    observed = base()
    observed["variables"] = [{"name": "temperature", "kind": "discrete", "values": [60, 70],
                               "unit": "C", "source": "synthetic observed finite domain"}]
    observed["baseline"] = {"parameters": {"temperature": 60, "pH": 6}}
    observed["observed_runs"] = [
        {"parameters": {"temperature": 60, "pH": 6}, "responses": {"yield": [90, 92, 94]},
         "source": "synthetic baseline rows A1-A3"},
        {"parameters": {"temperature": 70, "pH": 6}, "responses": {"yield": [100, 102, 104]},
         "source": "synthetic candidate rows B1-B3"}]
    observed["response_models"] = {}
    obs = optimize(observed)
    delta = obs["baseline_comparisons"]["responses"]["yield"]
    chosen = obs["recommendation"]["predicted_or_observed_responses"]["yield"]
    record("matched_repeats_ci_effect", chosen["kind"] == "observed"
           and chosen["statistics"]["n_independent"] == 3
           and len(chosen["statistics"]["mean_ci95"]) == 2 and "cohens_d_pooled_sensitivity" in delta)

    categorical = {
        "variables": [{"name": "method", "kind": "categorical", "values": ["A", "B"], "source": "synthetic categorical domain"}],
        "hard_constraints": [{"id": "method-required", "metric": "parameter.method", "op": "==", "value": "B", "source": "synthetic method rule"}],
        "objectives": [{"name": "yield", "direction": "maximize", "weight": 1,
                         "measurement": "two recorded points", "tolerance": 0.1}],
        "observed_runs": [{"parameters": {"method": "A"}, "responses": {"yield": [1]}, "source": "synthetic A"},
                           {"parameters": {"method": "B"}, "responses": {"yield": [2]}, "source": "synthetic B"}],
        "baseline": {"parameters": {"method": "A"}},
        "search": {"seed": 9, "max_evaluations": 2},
    }
    cat = optimize(categorical)
    record("categorical_constraint_finite_cv", cat["recommended_parameters"] == {"method": "B"}
           and all(json.dumps(p["gate"]["normalized_cv"], allow_nan=False) is not None for p in cat["candidate_evaluations"]))

    lhs_spec = base()
    lhs_spec["variables"] = [{"name": "x", "values": list(range(12)), "kind": "discrete", "source": "synthetic LHS domain"},
                              {"name": "y", "values": list(range(12)), "kind": "discrete", "source": "synthetic LHS domain"}]
    from bounded_optimize import domain
    lhs_domains = [domain(v) for v in lhs_spec["variables"]]
    lhs_a = lhs(lhs_domains, 8, 19, 0); lhs_b = lhs(lhs_domains, 8, 19, 0)
    record("seeded_lhs_reproducible", lhs_a == lhs_b and lhs_a != lhs(lhs_domains, 8, 20, 0))

    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td); spec = base(); spec["case_id"] = "synthetic-optimization-id"
        spec["output_contract"] = ["experiment_plan", "evidence_and_risks", "confirmation_items", "unknown_field"]
        sp = tmp / "spec.json"; sp.write_text(json.dumps(spec), encoding="utf-8")
        case = tmp / "case.json"; case.write_text(json.dumps({
            "case_id": "case-takes-precedence-example", "output_contract": spec["output_contract"]}), encoding="utf-8")
        r1 = build(sp, tmp / "a", case); r2 = build(sp, tmp / "b", case)
        identical = json.dumps(r1, sort_keys=True) == json.dumps(r2, sort_keys=True)
        record("contract_unknown_named_and_determinism", identical
               and all(k in r1 for k in spec["output_contract"])
               and r1["unknown_field"] is None
               and any("unknown_field" in line for line in r1["limits"])
               and r1["case_id"] == "synthetic-optimization-id")
        sp.write_text("[broken]", encoding="utf-8")
        bad = build(sp, tmp / "bad", case)
        record("structured_contract_refusal", bad["status"] == "undetermined" and case
               and all(k in bad for k in ["experiment_plan", "evidence_and_risks", "confirmation_items"]))

    # Numeric sanity of the independent statistic helper, including sparse cases.
    stat = summary([1, 2, 3])
    clean_stat = summary([5])
    record("repeat_summary_numbers", stat["value"] == 2 and stat["sample_sd"] == 1
           and clean_stat["n_independent"] == 1 and "mean_ci95" not in clean_stat)
    passed = sum(x["pass"] for x in reports)
    root = Path(__file__).resolve().parent.parent
    (root / "examples" / "optimization-bench-report.json").write_text(
        json.dumps({"schema_version": "bounded-optimization-bench/v1", "scenarios": reports,
                    "totals": {"passed": passed, "of": len(reports)}}, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n{passed}/{len(reports)} scenarios pass")
    return 0 if passed == len(reports) else 1


if __name__ == "__main__":
    raise SystemExit(main())
