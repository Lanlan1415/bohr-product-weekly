"""Independent round-2 probes and round-3 smoke/determinism checks.
Usage: python scripts/verify_independent.py probe|smoke [--report PATH]
"""
from __future__ import annotations

import argparse
import copy
import csv
import hashlib
import json
import os
import random
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))
import plan_engine as E  # noqa: E402

BASE = json.loads((ROOT / "examples" / "spec.json").read_text(encoding="utf-8"))
CHECKS = []


def check(name, condition, detail=""):
    CHECKS.append({"name": name, "passed": bool(condition), "detail": detail})


def run_cli(spec, out, case=False, cwd=None):
    args = [sys.executable, str(HERE / "plan_cli.py"), "--case" if case else "--spec", str(spec), "--out", str(out)]
    return subprocess.run(args, cwd=cwd, capture_output=True, text=True, timeout=40)


def write(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def snapshot(out, names):
    return {name: digest(out / name) for name in names}


ARTIFACTS = ("result.json", "plan.md", "design_matrix.csv", "change_records.json")


def probe(tmp):
    valid = tmp / "valid.json"
    write(valid, BASE)
    proc = run_cli(valid, tmp / "valid-out")
    check("baseline exit 0 without traceback", proc.returncode == 0 and not proc.stderr, proc.stderr)
    refused = [("syntax", "{"), ("array", "[]"), ("nan", '{"case_id":"x","objective":"x","factors":[{"name":"x","levels":[NaN]}],"candidate_plans":[{}]}')]
    for name, content in refused:
        path = tmp / f"{name}.json"
        path.write_text(content, encoding="utf-8")
        out = tmp / f"{name}-out"
        proc = run_cli(path, out)
        result = json.loads((out / "result.json").read_text(encoding="utf-8"))
        check(f"hostile {name} structured exit 5", proc.returncode == 5 and result["status"] == "undetermined" and "Traceback" not in proc.stderr, proc.stderr)
    proc = run_cli(tmp / "no-such-file.json", tmp / "missing-out")
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
    spec["optimization"]["max_combinations"] = 3
    path = tmp / "explosion.json"
    write(path, spec)
    proc = run_cli(path, tmp / "explosion-out")
    check("factorial explosion structured refusal", proc.returncode == 5 and "Traceback" not in proc.stderr)

    spec = copy.deepcopy(BASE)
    spec["output_contract"] = {"case_id": "id", "status": "engine", "selected_plan": "engine null", "caller_note": "case", "unknown": "null"}
    spec["status"] = "fake-clean"
    spec["resources"]["budget"]["amount"] = 1
    spec["selected_plan"] = {"plan_id": "FAKE"}
    path = tmp / "precedence.json"
    write(path, spec)
    proc = run_cli(path, tmp / "precedence-out")
    result = json.loads((tmp / "precedence-out" / "result.json").read_text(encoding="utf-8"))
    expected_keys = set(spec["output_contract"])
    check("contract keys preserved exactly", expected_keys <= set(result))
    check("case id top level", result["case_id"] == BASE["case_id"])
    check("engine status beats fake case status", result["status"] == "blocked")
    check("engine null selected_plan cannot be replaced", result["selected_plan"] is None and any("cannot override" in x for x in result["limits"]))
    check("case carried field and unknown null plus limits", result["caller_note"] == BASE["caller_note"] and result["unknown"] is None and any("unknown" in x for x in result["limits"]))
    check("blocked exit 4 and no traceback", proc.returncode == 4 and "Traceback" not in proc.stderr, proc.stderr)

    spec = copy.deepcopy(BASE)
    spec["sample_size"].pop("basis")
    path = tmp / "review.json"
    write(path, spec)
    proc = run_cli(path, tmp / "review-out")
    check("review exit 3 and findings retained", proc.returncode == 3 and json.loads((tmp / "review-out" / "result.json").read_text(encoding="utf-8"))["findings"])

    out = tmp / "idempotent"
    first = run_cli(valid, out)
    hashes = snapshot(out, ARTIFACTS)
    second = run_cli(valid, out)
    check("same output directory rerun is idempotent", first.returncode == second.returncode == 0 and hashes == snapshot(out, ARTIFACTS))
    out2 = tmp / "idempotent-other"
    run_cli(valid, out2)
    check("different output directories byte identical", hashes == snapshot(out2, ARTIFACTS))
    check("all artifacts UTF-8 regular nonsymlink files", all((out / name).is_file() and not (out / name).is_symlink() and (out / name).read_text(encoding="utf-8") is not None for name in ARTIFACTS))
    check("stdout is machine-readable summary", json.loads(first.stdout)["status"] == "clean")


def smoke(tmp):
    cold = tmp / "cold"
    cold.mkdir()
    code = f"import sys; sys.path.insert(0, {str(HERE)!r}); import plan_engine, plan_cli; print(plan_engine.SCHEMA)"
    proc = subprocess.run([sys.executable, "-I", "-c", code], cwd=cold, capture_output=True, text=True, timeout=30)
    check("cold import outside package", proc.returncode == 0 and E.SCHEMA in proc.stdout and not proc.stderr, proc.stderr)

    spec = copy.deepcopy(BASE)
    spec["case_id"] = "smoke-temperature-revision-002"
    spec["factors"][1]["levels"][0]["value"] = 22
    spec["factors"][1]["levels"][1]["value"] = 28
    spec["randomization"]["seed"] = 41
    before = hashlib.sha256(json.dumps(spec, sort_keys=True).encode()).hexdigest()
    wrapped = {"case_id": spec["case_id"], "output_contract": spec["output_contract"], "notes": "outer metadata", "inputs": {k: v for k, v in spec.items() if k not in ("case_id", "output_contract")}}
    case = tmp / "case.json"
    write(case, wrapped)
    out = tmp / "smoke-out"
    proc = run_cli(case, out, case=True, cwd=cold)
    result = json.loads((out / "result.json").read_text(encoding="utf-8"))
    check("realistic nested case smoke clean outside cwd", proc.returncode == 0 and result["case_id"] == spec["case_id"], proc.stderr)
    check("all smoke artifacts present", all((out / name).is_file() for name in ARTIFACTS))
    rows = list(csv.DictReader((out / "design_matrix.csv").open(encoding="utf-8")))
    check("smoke levels preserved per run", {row["temperature"] for row in rows} == {"22", "28"})
    check("smoke full factorial and independent n", len(rows) == 12 and len({row["cell"] for row in rows}) == 4 and all(len([r for r in rows if r["cell"] == cell]) == 3 for cell in {r["cell"] for r in rows}))
    check("unique run ids and contiguous run order", len({r["run_id"] for r in rows}) == 12 and sorted(int(r["run_order"]) for r in rows) == list(range(1, 13)))
    check("smoke cost and time arithmetic", result["selected_plan"]["cost"]["total"] == 152 and result["selected_plan"]["schedule"]["total_expected_hours"] == 12)
    expected_ids = [f"P3-D{cell:03d}-C{cell:02d}-R{rep:02d}" for cell in range(1, 5) for rep in range(1, 4)]
    random.Random(41).shuffle(expected_ids)
    actual_ids = [r["run_id"] for r in sorted(rows, key=lambda x: int(x["run_order"]))]
    check("independent seed shuffle reproduced", actual_ids == expected_ids)
    text = (out / "plan.md").read_text(encoding="utf-8")
    check("smoke plan is prospective and sourced", "not executed" in text and "SRC-MANUAL" in text and "run_id" in text)
    after = hashlib.sha256(json.dumps(spec, sort_keys=True).encode()).hexdigest()
    check("caller spec was not mutated", before == after)
    hashes = snapshot(out, ARTIFACTS)
    out2 = tmp / "smoke-out-2"
    proc2 = run_cli(case, out2, case=True, cwd=cold)
    check("cold realistic rerun byte deterministic", proc2.returncode == 0 and hashes == snapshot(out2, ARTIFACTS))
    check("import and runs have no traceback", not proc.stderr and not proc2.stderr, proc.stderr + proc2.stderr)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("round", choices=("probe", "smoke"))
    parser.add_argument("--report")
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix=f"p74-{args.round}-") as tmp:
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
