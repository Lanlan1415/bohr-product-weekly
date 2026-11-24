"""End-to-end reproduction tests with two actually executed numerical candidates.

The numerical task is synthetic: integrate x^2 on [0,1].  The independently known
value 1/3 is used, never a previous run's output.  It does not claim paper replication.
Temporary scripts and manifests are isolated outside the submitted skill package.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parent))
import sections as S

RUNNER = Path(__file__).resolve().with_name("rerun.py")


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def manifest(root, script, methods, extra=None):
    commands = []
    for item in methods:
        name, method, n = item[:3]
        series = item[3] if len(item) > 3 else None
        seed = item[4] if len(item) > 4 else 41
        commands.append({"id": name, "seed": seed, "series": series,
                         "argv": ["{python}", script.name, "--method", method, "--n", str(n), "--seed", str(seed)],
                         "metrics": [{"name": "integral_x_squared", "paper": 1.0 / 3.0,
                                      "json_path": "integral", "tolerance": {"abs": 5e-5, "rel": 0},
                                      "paper_locator": "analytic integral of x^2 on [0,1]",
                                      "statistic": "one deterministic grid (not a claimed paper metric)"}]})
    obj = {"schema_version": "candidate-execution/v1", "scope": "two local candidate numerical methods; not the original paper's code",
           "code_version": "local-synthetic-numerics-v1", "data_version": "unit-interval-grid@v1",
           "seed": 41, "timeout_s": 5,
           "files": {script.name: {"sha256": sha(script), "license": "synthetic-local-fixture"}, "grid.json": {"sha256": sha(root / "grid.json"), "state": "present"}},
           "parameters": [{"name": "n", "source": "assumed", "value": 64, "justification": "chosen for the known-value discretisation smoke"},
                          {"name": "seed", "source": "assumed", "value": 41, "justification": "hash-seed pinning for a deterministic numerical experiment"}],
           "commands": commands}
    if extra:
        obj.update(extra)
    (root / "manifest.json").write_text(json.dumps(obj), encoding="utf-8")
    return root / "manifest.json"


def call(root, manifest_path, out, case=None):
    cmd = [sys.executable, str(RUNNER), "--manifest", str(manifest_path), "--workspace", str(root), "--out", str(out)]
    if case:
        cmd += ["--case", str(case)]
    return subprocess.run(cmd, capture_output=True, text=True, timeout=30)


def tests():
    rows = []
    def ok(name, cond, detail=None):
        rows.append({"scenario": name, "pass": bool(cond), "detail": str(detail)})
        print(("PASS " if cond else "FAIL ") + name + (" :: " + str(detail) if not cond else ""))
    with tempfile.TemporaryDirectory(prefix="repro_real_candidates_") as td:
        root = Path(td)
        script = root / "candidate.py"
        script.write_text('''import argparse, json\np=argparse.ArgumentParser(); p.add_argument("--method");p.add_argument("--n",type=int);p.add_argument("--seed",type=int);a=p.parse_args()\nn=a.n;h=1.0/n\nif a.method=="trapezoid":\n    actual=(0.0+1.0)/2.0+sum((i*h)**2 for i in range(1,n));actual*=h\nelif a.method=="simpson":\n    if n%2: raise ValueError("n must be even")\n    actual=0.0+1.0+4.0*sum((i*h)**2 for i in range(1,n,2))+2.0*sum((i*h)**2 for i in range(2,n,2));actual*=h/3.0\nelse: raise ValueError("bad method")\nprint("completed synthetic quadrature")\nprint(json.dumps({"method":a.method,"n":n,"seed":a.seed,"integral":actual},sort_keys=True))\n''', encoding="utf-8")
        (root / "grid.json").write_text(json.dumps({"lo": 0, "hi": 1, "function": "x^2"}), encoding="utf-8")
        case = root / "case.json"
        case.write_text(json.dumps({"case_id": "synthetic-two-candidates", "custom": ["contract", 42],
                                    "output_contract": {"execution_records": "...", "custom": "...", "run_manifest": "..."}}), encoding="utf-8")
        mp = manifest(root, script, [("trapezoid-A", "trapezoid", 64, "trapezoid-64", 41),
                                      ("Simpson-B", "simpson", 64),
                                      ("trapezoid-A-seed-43", "trapezoid", 64, "trapezoid-64", 43)])
        first, second = root / "out-first", root / "out-second"
        r1 = call(root, mp, first, case)
        r2 = call(root, mp, second, case)
        result = json.loads((first / "result.json").read_text(encoding="utf-8"))
        ok("two_candidates_actually_completed", r1.returncode == 0 and result["execution"] == {"actually_launched": True, "all_completed": True, "command_count": 3, "completed_count": 3}, (r1.returncode, r1.stdout, r1.stderr))
        metrics = result["metrics"]
        trapezoid = next(m for m in metrics if m["command"] == "trapezoid-A")
        simpson = next(m for m in metrics if m["command"] == "Simpson-B")
        # Independently evaluate the quadrature convergence target, not the tool's claim.
        exact = 1.0 / 3.0
        trapezoid_error = 1.0 / (6.0 * 64.0 ** 2)
        # Interpret algorithm differences separately from declared-series seed repeats.
        ok("independent_trapezoid_recalculation", abs(trapezoid["reproduced"] - (exact + trapezoid_error)) < 1e-14 and abs(trapezoid["absolute_delta"] - trapezoid_error) < 1e-14 and trapezoid["within_tolerance"] is True, trapezoid)
        ok("independent_simpson_recalculation", abs(simpson["reproduced"] - exact) < 1e-15 and simpson["within_tolerance"] is True, simpson)
        ok("seed_variation_only_within_declared_series", result["seed_variation"][0]["seeds"] == [41, 43] and result["seed_variation"][0]["stdev"] == 0 and len(result["seed_variation"]) == 1)
        ok("case_id_and_all_contract_fields", result["case_id"] == "synthetic-two-candidates" and result["custom"] == ["contract", 42] and result["run_manifest"] == "run-manifest.json" and len(result["execution_records"]) == 3)
        det = {"result": (first / "result.json").read_bytes() == (second / "result.json").read_bytes(),
               "manifest": (first / "run-manifest.json").read_bytes() == (second / "run-manifest.json").read_bytes(),
               "logs": (first / "runs" / "trapezoid-A" / "stdout.log").read_bytes() == (second / "runs" / "trapezoid-A" / "stdout.log").read_bytes()}
        ok("deterministic_result_and_logs", all(det.values()), det)
        ok("no_original_paper_reproduction_claim", result["paper_reproduction_claim"] is False and "unavailable original" in result["claim_boundary"])
        spec = {"commit": "local-synthetic-numerics-v1", "data_version": "unit-interval-grid@v1", "commands": ["declared"],
                "checklist": {"materials": [{"name": "candidate", "source": "local", "version": "v1", "state": "present"}],
                              "environment": {"dependencies": "stdlib", "hardware": "local", "seed": "41"}, "parameters": [], "run": {"logs": "actual paths", "exit_status": "completed"}, "results": {"tolerance": "5e-5", "comparison_basis": "x^2", "statistic": "one deterministic grid", "metrics": metrics}, "verdict": "reproducible", "verdict_basis": "both actual candidates within analytic tolerance"}, "actual_run": result}
        audit_rules = {f["rule"] for f in S.run(spec, "reproduce")[0]}
        ok("good_actual_run_has_no_consistency_false_positive", not {r for r in audit_rules if r.startswith("repro.execution") or r == "repro.verdict_inconsistent_execution"}, sorted(audit_rules))
        spec["actual_run"] = dict(result, execution={"actually_launched": False, "all_completed": False}, status="undetermined")
        rules = {f["rule"] for f in S.run(spec, "reproduce")[0]}
        ok("unsupported_reproducible_verdict_rejected", "repro.execution_claim_unsupported" in rules and "repro.verdict_inconsistent_execution" in rules)
        spec["actual_run"] = dict(result, code_version="WRONG")
        ok("actual_commit_mismatch_detected", "repro.execution_revision_mismatch" in {f["rule"] for f in S.run(spec, "reproduce")[0]})

        failing_mp = manifest(root, script, [("coarse", "trapezoid", 4)])
        failing_out = root / "out-coarse"
        rb = call(root, failing_mp, failing_out)
        bad = json.loads((failing_out / "result.json").read_text())
        ok("real_out_of_tolerance_classified_methodological", rb.returncode == 3 and bad["metrics"][0]["delta_class"] == "methodological" and bad["metrics"][0]["within_tolerance"] is False and bad["metrics"][0]["absolute_delta"] > 0.01)
        ok("out_of_tolerance_has_next_action_not_fake_fix", "do not relax the tolerance post hoc" in bad["findings"][0]["next_action"] and bad["findings"][0]["failure_class"] == "metric_out_of_tolerance")

        timeout_script = root / "timeout.py"
        timeout_script.write_text("import time\ntime.sleep(30)\n", encoding="utf-8")
        tm = manifest(root, timeout_script, [], {"commands": [{"id": "timeout", "timeout_s": 0.05, "argv": ["{python}", timeout_script.name], "metrics": []}], "timeout_s": 0.1})
        to = root / "out-timeout"
        rt = call(root, tm, to)
        tr = json.loads((to / "result.json").read_text(encoding="utf-8"))
        ok("timeout_is_actual_failure_with_logs", rt.returncode == 4 and tr["runs"][0]["failure_class"] == "timeout" and tr["execution"]["actually_launched"] is True and (to / "runs" / "timeout" / "stderr.log").is_file())

        for label, extra, expected_rc in [
            ("missing_dependency_no_execution", {"dependencies": ["definitely-no-such-package-xyz==1.0"]}, 5),
            ("non_python_command_refused", {"commands": [{"id": "shell", "argv": ["cmd", "/c", "dir"]}]}, 5),
            ("python_c_refused", {"commands": [{"id": "inline", "argv": ["{python}", "-c", "print(1)"]}]}, 5),
            ("workspace_escape_refused", {"commands": [{"id": "escape", "argv": ["{python}", "../candidate.py"]}]}, 5),
        ]:
            pm = manifest(root, script, [("probe", "trapezoid", 64)], extra)
            po = root / ("out-" + label)
            rr = call(root, pm, po)
            pr = json.loads((po / "result.json").read_text(encoding="utf-8"))
            ok(label, rr.returncode == expected_rc and pr["execution"]["actually_launched"] is False and not rr.stderr, (rr.returncode, rr.stdout, rr.stderr))
        bad_manifest = manifest(root, script, [("badhash", "trapezoid", 64)])
        mm = json.loads(bad_manifest.read_text())
        mm["files"][script.name]["sha256"] = "0" * 64
        bad_manifest.write_text(json.dumps(mm), encoding="utf-8")
        bro = root / "out-bad-hash"
        br = call(root, bad_manifest, bro)
        ok("hash_mismatch_prevents_execution", br.returncode == 5 and not bro.joinpath("runs").exists() and json.loads((bro / "result.json").read_text())["execution"]["actually_launched"] is False)

        malformed = root / "malformed.json"; malformed.write_text("{broken", encoding="utf-8")
        mro = root / "out-malformed"
        mr = call(root, malformed, mro)
        ok("malformed_manifest_structured_refusal", mr.returncode == 5 and mro.joinpath("result.json").is_file() and "refused" in json.loads((mro / "result.json").read_text())["findings"][0]["rule"] and not mr.stderr)
    return rows


def main():
    rows = tests()
    passed = sum(r["pass"] for r in rows)
    output = {"schema_version": "repro-execution-bench/v1", "synthetic": True, "original_paper_reproduced": False,
              "scenarios": rows, "totals": {"passed": passed, "of": len(rows)}}
    (Path(__file__).resolve().parent / "report_execution.json").write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    print("%d/%d pass" % (passed, len(rows)))
    return 0 if passed == len(rows) else 1


if __name__ == "__main__":
    raise SystemExit(main())
