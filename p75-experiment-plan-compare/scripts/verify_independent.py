"""Independent round-2 probes and round-3 smoke/determinism checks.
Usage: python scripts/verify_independent.py probe|smoke [--report PATH]
"""
from __future__ import annotations

import argparse
import copy
import csv
import hashlib
import json
import math
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))
import compare_engine as E  # noqa: E402

BASE = json.loads((ROOT / "examples" / "spec.json").read_text(encoding="utf-8"))
CHECKS = []
ARTIFACTS = ("result.json", "recommendation.md", "comparison_matrix.csv", "evidence_matrix.csv", "sensitivity.json", "change_records.json")


def check(name, condition, detail=""):
    CHECKS.append({"name": name, "passed": bool(condition), "detail": detail})


def run_cli(spec, out, case=False, cwd=None):
    args = [sys.executable, str(HERE / "compare_cli.py"), "--case" if case else "--spec", str(spec), "--out", str(out)]
    return subprocess.run(args, cwd=cwd, capture_output=True, text=True, timeout=40)


def write(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")


def snapshot(out):
    return {name: hashlib.sha256((out / name).read_bytes()).hexdigest() for name in ARTIFACTS}


def probe(tmp):
    valid = tmp / "valid.json"
    write(valid, BASE)
    proc = run_cli(valid, tmp / "valid-out")
    check("baseline exit 0 without traceback", proc.returncode == 0 and not proc.stderr, proc.stderr)
    for name, content in (("syntax", "{"), ("array", "[]"), ("nan", '{"case_id":"x","objective":"x","criteria":[{"name":"a","weight":NaN}],"candidate_plans":[{},{}]}')):
        path = tmp / f"{name}.json"
        path.write_text(content, encoding="utf-8")
        out = tmp / f"{name}-out"
        proc = run_cli(path, out)
        result = json.loads((out / "result.json").read_text(encoding="utf-8"))
        check(f"hostile {name} structured exit 5", proc.returncode == 5 and result["status"] == "undetermined" and "Traceback" not in proc.stderr, proc.stderr)
    proc = run_cli(tmp / "missing.json", tmp / "missing-out")
    check("missing file structured refusal", proc.returncode == 5 and "Traceback" not in proc.stderr)
    bad = tmp / "bad-utf.json"
    bad.write_bytes(b"\xff\xfe")
    proc = run_cli(bad, tmp / "bad-utf-out")
    check("bad UTF-8 structured refusal", proc.returncode == 5 and "Traceback" not in proc.stderr)
    for name, contract in (("integer", 3), ("null", None), ("bad-list-entry", ["case_id", 3])):
        spec = copy.deepcopy(BASE)
        spec["output_contract"] = contract
        path = tmp / f"contract-{name}.json"
        write(path, spec)
        out = tmp / f"contract-{name}-out"
        proc = run_cli(path, out)
        result = json.loads((out / "result.json").read_text(encoding="utf-8"))
        check(f"malformed contract {name} refused", proc.returncode == 5 and result["status"] == "undetermined" and "Traceback" not in proc.stderr, proc.stderr)
    spec = copy.deepcopy(BASE)
    spec["candidate_plans"] = spec["candidate_plans"][:1]
    path = tmp / "one-candidate.json"
    write(path, spec)
    proc = run_cli(path, tmp / "one-candidate-out")
    check("one-candidate comparison structured refusal", proc.returncode == 5 and "Traceback" not in proc.stderr)

    spec = copy.deepcopy(BASE)
    spec["output_contract"] = {"case_id": "id", "status": "engine", "recommendation": "engine null", "caller_note": "case", "unknown": "null"}
    spec["status"] = "fake-clean"
    spec["recommendation"] = {"plan_id": "FAKE"}
    spec["hard_constraints"][0]["value"] = 50
    path = tmp / "precedence.json"
    write(path, spec)
    proc = run_cli(path, tmp / "precedence-out")
    result = json.loads((tmp / "precedence-out" / "result.json").read_text(encoding="utf-8"))
    check("contract keys preserved exactly", set(spec["output_contract"]) <= set(result))
    check("case id top level", result["case_id"] == BASE["case_id"])
    check("engine status beats fake case status", result["status"] == "blocked")
    check("engine null recommendation cannot be replaced", result["recommendation"] is None and any("cannot override" in x for x in result["limits"]))
    check("case carried field and unknown null plus limits", result["caller_note"] == BASE["caller_note"] and result["unknown"] is None and any("unknown" in x for x in result["limits"]))
    check("all infeasible blocked exit 4", proc.returncode == 4 and "Traceback" not in proc.stderr, proc.stderr)

    spec = copy.deepcopy(BASE)
    spec["fallback_triggers"] = []
    path = tmp / "review.json"
    write(path, spec)
    proc = run_cli(path, tmp / "review-out")
    check("review exit 3 and findings retained", proc.returncode == 3 and json.loads((tmp / "review-out" / "result.json").read_text(encoding="utf-8"))["findings"])

    out = tmp / "idempotent"
    first = run_cli(valid, out)
    hashes = snapshot(out)
    second = run_cli(valid, out)
    check("same output directory rerun idempotent", first.returncode == second.returncode == 0 and hashes == snapshot(out))
    out2 = tmp / "idempotent-other"
    run_cli(valid, out2)
    check("different output directories byte identical", hashes == snapshot(out2))
    check("all artifacts UTF-8 regular nonsymlink files", all((out / name).is_file() and not (out / name).is_symlink() and (out / name).read_text(encoding="utf-8") is not None for name in ARTIFACTS))
    check("stdout is machine-readable summary", json.loads(first.stdout)["status"] == "clean")


def smoke(tmp):
    cold = tmp / "cold"
    cold.mkdir()
    code = f"import sys; sys.path.insert(0, {str(HERE)!r}); import compare_engine, compare_cli; print(compare_engine.SCHEMA)"
    proc = subprocess.run([sys.executable, "-I", "-c", code], cwd=cold, capture_output=True, text=True, timeout=30)
    check("cold import outside package", proc.returncode == 0 and E.SCHEMA in proc.stdout and not proc.stderr, proc.stderr)

    spec = copy.deepcopy(BASE)
    spec["case_id"] = "smoke-aligned-choice-002"
    spec["caller_note"] = "smoke pass-through value"
    before = hashlib.sha256(json.dumps(spec, sort_keys=True).encode()).hexdigest()
    wrapped = {"case_id": spec["case_id"], "output_contract": spec["output_contract"], "inputs": {k: v for k, v in spec.items() if k not in ("case_id", "output_contract")}}
    case = tmp / "case.json"
    write(case, wrapped)
    out = tmp / "smoke-out"
    proc = run_cli(case, out, case=True, cwd=cold)
    result = json.loads((out / "result.json").read_text(encoding="utf-8"))
    check("realistic nested case smoke clean outside cwd", proc.returncode == 0 and result["case_id"] == spec["case_id"], proc.stderr)
    check("all smoke artifacts present", all((out / name).is_file() for name in ARTIFACTS))
    check("three candidates and two eligible", len(result["plan_versions"]) == 3 and len(result["ranking"]) == 2)
    check("failed budget candidate never ranked", "P2" not in {r["plan_id"] for r in result["ranking"]} and any(x["plan_id"] == "P2" for x in result["eliminated_plans"]))
    ranking = {r["plan_id"]: r["score"] for r in result["ranking"]}
    for pid, score in ranking.items():
        cells = [x for x in result["scoring_matrix"] if x["plan_id"] == pid]
        recomputed = sum(x["weighted_contribution"] for x in cells) * 100
        check(f"independently recompute WSM {pid}", math.isclose(recomputed, score, abs_tol=1e-6), f"{recomputed} vs {score}")
    registry = {x["id"] for x in spec["sources"]}
    check("all smoke evidence resolves to registry", all(ref in registry for row in result["evidence_matrix"] for ref in row["evidence_refs"]))
    check("tradeoff and concrete fallback present", len(result["tradeoffs"][0]["winner_disadvantages"]) == 3 and len(result["fallback_plan"]["triggers"]) == 2)
    check("case value and unknown contract null handled", result["caller_note"] == "smoke pass-through value" and result["unknown_figure"] is None)
    text = (out / "recommendation.md").read_text(encoding="utf-8")
    check("smoke recommendation has sources and no execution", "no experiment executed" in text and "HC-BUDGET" in text and "Fallback" in text)
    check("weight and interval scenarios both nonempty", len(result["sensitivity_analysis"]["scenarios"]) == 10 and len(result["uncertainty_analysis"]["scenarios"]) == 10)
    check("caller spec not mutated", before == hashlib.sha256(json.dumps(spec, sort_keys=True).encode()).hexdigest())
    hashes = snapshot(out)
    out2 = tmp / "smoke-out-2"
    proc2 = run_cli(case, out2, case=True, cwd=cold)
    check("cold realistic rerun byte deterministic", proc2.returncode == 0 and hashes == snapshot(out2))
    check("import and runs have no traceback", not proc.stderr and not proc2.stderr, proc.stderr + proc2.stderr)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("round", choices=("probe", "smoke"))
    parser.add_argument("--report")
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix=f"p75-{args.round}-") as tmp:
        (probe if args.round == "probe" else smoke)(Path(tmp))
    passed = sum(x["passed"] for x in CHECKS)
    report = {"round": args.round, "engine_schema": E.SCHEMA, "total": len(CHECKS), "passed": passed,
              "failed": len(CHECKS) - passed, "checks": CHECKS}
    text = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if args.report:
        Path(args.report).write_text(text, encoding="utf-8")
    print(json.dumps({"round": args.round, "total": len(CHECKS), "passed": passed, "failed": len(CHECKS) - passed}))
    for item in CHECKS:
        if not item["passed"]:
            print("FAIL", item["name"], item["detail"])
    return 0 if passed == len(CHECKS) else 1


if __name__ == "__main__":
    raise SystemExit(main())
