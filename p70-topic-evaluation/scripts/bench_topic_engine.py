"""Regression battery for the formal topic-evaluation engine (synthetic data only)."""
from __future__ import annotations

import copy
import importlib.util
import json
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import topic_engine as E  # noqa: E402

ROOT = HERE.parent
SPEC_PATH = ROOT / "examples" / "topic-spec.json"
CASE_PATH = ROOT / "examples" / "case.json"
CLI = HERE / "topicrun.py"
BASE = json.loads(SPEC_PATH.read_text(encoding="utf-8"))
CASE = json.loads(CASE_PATH.read_text(encoding="utf-8"))
CONTRACT_NAMES = ["research_product", "comparison_matrix", "evidence_matrix", "novelty_assessment",
                  "feasibility_assessment", "decision", "search_protocol", "uncertainties",
                  "research_gaps", "change_records", "deliverables"]


def spec():
    return copy.deepcopy(BASE)


def run_cli(tmp: Path, data: dict | None = None, case: dict | None = CASE, raw_spec: str | None = None):
    tmp.mkdir(parents=True, exist_ok=True)
    source = tmp / "input.json"
    if raw_spec is not None:
        source.write_text(raw_spec, encoding="utf-8")
    else:
        source.write_text(json.dumps(data if data is not None else spec(), ensure_ascii=False), encoding="utf-8")
    case_file = tmp / "case.json"
    if case is not None:
        case_file.write_text(json.dumps(case, ensure_ascii=False), encoding="utf-8")
    out = tmp / "out"
    args = [sys.executable, "-I", "-X", "utf8", str(CLI), "--spec", str(source), "--out", str(out)]
    if case is not None:
        args += ["--case", str(case_file)]
    proc = subprocess.run(args, capture_output=True, text=True, timeout=60)
    result_path = out / "result.json"
    result = json.loads(result_path.read_text(encoding="utf-8")) if result_path.exists() else {}
    return proc, result, out


def has_rule(result, rule):
    return rule in {row.get("rule") for row in result.get("findings", [])}


def s_clean(tmp, name):
    result = E.analyze(spec())
    return (result["status"] == "clean" and not result["findings"]
            and result["decision"]["grade"] == "go_within_scope"
            and result["novelty_assessment"][0]["computed_status"] == "not_covered_in_declared_scope")


def s_artifacts_contract(tmp, name):
    proc, result, out = run_cli(tmp)
    expected = {"topic_evaluation.md", "comparison_matrix.csv", "evidence_matrix.csv",
                "novelty_audit.csv", "result.json"}
    return (proc.returncode == 0 and expected <= {p.name for p in out.iterdir()}
            and result["case_id"] == CASE["case_id"]
            and result["output_contract_fields"] == CONTRACT_NAMES
            and all(name in result and result[name] is not None for name in CONTRACT_NAMES)
            and result["output_contract"] == CASE["output_contract"]
            and len(result["artifacts"]) == 4
            and all(len(row["sha256"]) == 64 for row in result["artifacts"]))


def s_prospective_not_executed(tmp, name):
    data = spec()
    data["search_protocol"]["status"] = "prospective"
    result = E.analyze(data)
    return (all(row["hit_count"] is None for row in result["search_protocol"]["sources"])
            and result["novelty_assessment"][0]["computed_status"] == "undetermined"
            and result["decision"]["grade"] == "undetermined"
            and any(row["kind"] == "search_not_executed" for row in result["uncertainties"]))


def s_prospective_fake_count(tmp, name):
    data = spec()
    data["search_protocol"]["status"] = "prospective"
    data["search_protocol"]["sources"][0]["hit_count"] = 0
    result = E.analyze(data)
    return has_rule(result, "topic.unexecuted_count_present") and result["status"] == "blocked"


def s_executed_requires_real_count(tmp, name):
    data = spec()
    data["search_protocol"]["status"] = "executed"
    for source in data["search_protocol"]["sources"]:
        source.pop("hit_count", None)
    result = E.analyze(data)
    return sum(row["rule"] == "topic.hit_count_invalid" for row in result["findings"]) == 3


def s_direct_collision(tmp, name):
    data = spec()
    comp = data["innovation_claims"][0]["nearest_comparisons"][1]
    comp["collision"] = "direct_precedent"
    comp["remaining_difference"] = ""
    result = E.analyze(data)
    return (result["novelty_assessment"][0]["computed_status"] == "covered_by_prior_work"
            and result["decision"]["grade"] == "revise_and_recheck")


def s_transfer_not_method_first(tmp, name):
    data = spec()
    claim = data["innovation_claims"][0]
    claim["type"] = "scene_transfer"
    claim["nearest_comparisons"][0]["collision"] = "routine_adaptation"
    claim["nearest_comparisons"][1]["collision"] = "scene_transfer"
    result = E.analyze(data)
    return result["novelty_assessment"][0]["computed_status"] == "incremental_transfer_not_method_first"


def s_counterevidence(tmp, name):
    data = spec()
    comp = data["innovation_claims"][0]["nearest_comparisons"][1]
    comp["counterevidence_refs"] = ["W002:conclusion"]
    result = E.analyze(data)
    return (result["novelty_assessment"][0]["computed_status"] == "contested_in_scope"
            and result["decision"]["grade"] == "undetermined"
            and any(row["kind"] == "counterevidence" for row in result["uncertainties"]))


def s_quote_tamper(tmp, name):
    data = spec()
    data["works"][0]["evidence"][0]["quote"] = "fabricated sentence absent from source"
    result = E.analyze(data)
    return has_rule(result, "topic.quote_not_in_source") and result["status"] == "blocked"


def s_incomparable_reason(tmp, name):
    data = spec()
    data["works"][1]["incomparable_reasons"] = {}
    result = E.analyze(data)
    return has_rule(result, "topic.incomparable_reason_missing")


def s_single_source_no_clear_gate(tmp, name):
    data = spec()
    data["search_protocol"]["sources"] = data["search_protocol"]["sources"][:1]
    result = E.analyze(data)
    return (has_rule(result, "topic.single_source")
            and result["novelty_assessment"][0]["computed_status"] == "undetermined")


def s_assumption_needs_validation(tmp, name):
    data = spec()
    pre = data["feasibility"]["prerequisites"][0]
    pre["status"] = "assumed"
    pre["assumption"] = "假设数据划分可复用"
    pre.pop("validation", None)
    result = E.analyze(data)
    return has_rule(result, "topic.assumption_validation_missing")


def s_missing_critical_prestudy(tmp, name):
    data = spec()
    data["feasibility"]["prerequisites"][0]["status"] = "missing"
    result = E.analyze(data)
    return (has_rule(result, "topic.critical_prerequisite_unresolved")
            and result["decision"]["grade"] == "pre_study_required"
            and result["feasibility_assessment"]["computed_status"] == "not_currently_feasible")


def s_unknown_evidence_ref(tmp, name):
    data = spec()
    data["innovation_claims"][0]["difference_evidence_refs"] = ["W999:method"]
    result = E.analyze(data)
    return has_rule(result, "topic.claim_evidence_unresolved")


def s_duplicate_work_id(tmp, name):
    data = spec()
    data["works"].append(copy.deepcopy(data["works"][0]))
    result = E.analyze(data)
    return has_rule(result, "topic.work_id_duplicate") and result["checked"]["works"] == 2


def s_refusal_contract(tmp, name):
    proc, result, out = run_cli(tmp, raw_spec="{not json")
    return (proc.returncode == 5 and result["status"] == "undetermined"
            and result["case_id"] == CASE["case_id"]
            and result["output_contract_fields"] == CONTRACT_NAMES
            and all(name in result for name in CONTRACT_NAMES)
            and "Traceback" not in proc.stderr)


def s_idempotent_bytes(tmp, name):
    proc1, result1, out = run_cli(tmp)
    first = {p.name: p.read_bytes() for p in out.iterdir() if p.is_file()}
    source = tmp / "input.json"
    proc2 = subprocess.run([sys.executable, "-I", "-X", "utf8", str(CLI), "--spec", str(source),
                            "--case", str(tmp / "case.json"), "--out", str(out)],
                           capture_output=True, text=True, timeout=60)
    second = {p.name: p.read_bytes() for p in out.iterdir() if p.is_file()}
    return proc1.returncode == proc2.returncode == 0 and first == second


def s_cold_import(tmp, name):
    module_path = HERE / "topic_engine.py"
    spec_obj = importlib.util.spec_from_file_location("cold_topic_engine", module_path)
    module = importlib.util.module_from_spec(spec_obj)
    spec_obj.loader.exec_module(module)
    result = module.analyze(spec())
    return result["status"] == "clean" and result["checked"]["evidence_rows"] == 10


SCENARIOS = [
    ("clean_baseline", s_clean), ("artifacts_and_contract", s_artifacts_contract),
    ("prospective_not_executed", s_prospective_not_executed),
    ("prospective_fake_count", s_prospective_fake_count),
    ("executed_requires_real_count", s_executed_requires_real_count),
    ("direct_collision", s_direct_collision), ("transfer_not_method_first", s_transfer_not_method_first),
    ("counterevidence", s_counterevidence), ("quote_tamper", s_quote_tamper),
    ("incomparable_reason", s_incomparable_reason), ("single_source_no_clear_gate", s_single_source_no_clear_gate),
    ("assumption_needs_validation", s_assumption_needs_validation),
    ("missing_critical_prestudy", s_missing_critical_prestudy),
    ("unknown_evidence_ref", s_unknown_evidence_ref), ("duplicate_work_id", s_duplicate_work_id),
    ("refusal_contract", s_refusal_contract), ("idempotent_bytes", s_idempotent_bytes),
    ("cold_import", s_cold_import),
]


def main():
    rows = []
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        for pos, (name, fn) in enumerate(SCENARIOS):
            try:
                ok = bool(fn(root / f"{pos:02d}_{name}", name))
                why = ""
            except Exception as exc:
                ok, why = False, f"raised {type(exc).__name__}: {exc}"
            rows.append({"scenario": name, "pass": ok, "why": why})
            print(("PASS" if ok else "FAIL") + f"  {name:<32}" + why)
    passed = sum(row["pass"] for row in rows)
    report = {"schema_version": "topic-engine-bench/v2", "synthetic_only": True,
              "scenarios": rows, "totals": {"passed": passed, "of": len(rows)}}
    (HERE / "report_topic_engine.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n{passed}/{len(rows)} scenarios pass")
    return 0 if passed == len(rows) else 1


if __name__ == "__main__":
    raise SystemExit(main())
