"""Independent cold-import, end-to-end, determinism and contract verification."""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
PACKAGE = HERE.parent


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def cold_import(path, env):
    code = (
        "import importlib.util,sys;sys.dont_write_bytecode=True;"
        "p=sys.argv[1];s=importlib.util.spec_from_file_location('cold_verify',p);"
        "m=importlib.util.module_from_spec(s);s.loader.exec_module(m);print('OK')"
    )
    process = subprocess.run([sys.executable, "-I", "-c", code, str(path)],
                             capture_output=True, text=True, timeout=20, env=env)
    return {"module": path.name, "exit_code": process.returncode,
            "passed": process.returncode == 0 and "OK" in process.stdout,
            "stderr": process.stderr[-500:]}


def run_cli(package, out, mode, env):
    return subprocess.run([
        sys.executable, "-I", str(package / "scripts" / "scicode.py"),
        "--case", str(package / "examples" / "case.json"),
        "--spec", str(package / "examples" / "spec.json"),
        "--out", str(out), "--mode", mode,
    ], capture_output=True, text=True, timeout=30, env=env)


def package_audit(package):
    files = [p for p in package.rglob("*") if p.is_file()]
    issues, total = [], 0
    for path in files:
        relative = path.relative_to(package)
        if path.is_symlink():
            issues.append(f"symlink: {relative}")
        if "__pycache__" in path.parts or path.suffix.lower() in (".pyc", ".pyo", ".db", ".sqlite", ".png", ".pdf"):
            issues.append(f"scratch/binary: {relative}")
        size = path.stat().st_size
        total += size
        if size > 500_000:
            issues.append(f"over 500KB: {relative}")
        try:
            path.read_text(encoding="utf-8")
        except (UnicodeError, OSError) as exc:
            issues.append(f"not UTF-8 text: {relative}: {exc}")
    if len(files) > 50:
        issues.append(f"too many files: {len(files)}")
    if total > 2_000_000:
        issues.append(f"package too large: {total}")
    return {"files": len(files), "bytes": total, "issues": issues, "passed": not issues}


def verify(package):
    package = package.resolve()
    env = dict(os.environ)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    imports = [cold_import(package / "scripts" / f"{name}.py", env)
               for name in ("codegen", "runner", "validator", "scicode")]
    with tempfile.TemporaryDirectory(prefix="scicode-independent-smoke-") as temporary:
        out = Path(temporary) / "out"
        first = run_cli(package, out, "execute", env)
        result_path = out / "result.json"
        if not result_path.is_file():
            return {"passed": False, "error": "first smoke wrote no result.json", "imports": imports}
        first_result_bytes = result_path.read_bytes()
        first_analysis_bytes = (out / "analysis.json").read_bytes()
        result = json.loads(first_result_bytes)
        second = run_cli(package, out, "execute", env)
        deterministic = (first_result_bytes == result_path.read_bytes() and
                         first_analysis_bytes == (out / "analysis.json").read_bytes())
        generate_out = Path(temporary) / "generate-only"
        generated = run_cli(package, generate_out, "generate", env)
        generated_result = json.loads((generate_out / "result.json").read_text(encoding="utf-8"))
        case = json.loads((package / "examples" / "case.json").read_text(encoding="utf-8"))
        contract = case["output_contract"]
        missing = [key for key in contract if key not in result]
        artifact_missing = [name for name in result.get("artifacts", {}).values()
                            if isinstance(name, str) and not (out / name).is_file()]
        checks = {
            "first_exit_clean": first.returncode == 0 and result.get("status") == "clean",
            "second_exit_clean": second.returncode == 0,
            "cold_imports": all(item["passed"] for item in imports),
            "deterministic_result_and_analysis": deterministic,
            "really_executed": result.get("execution_result", {}).get("executed") is True,
            "no_shell": result.get("execution_result", {}).get("shell") is False,
            "independent_validation_passed": result.get("validation", {}).get("status") == "passed",
            "all_contract_fields": not missing,
            "engine_beats_case": result.get("status") == "clean" and isinstance(result.get("analysis_result"), dict),
            "case_value_preserved": result.get("case_note") == case["case_note"],
            "unknown_null_and_limited": result.get("unavailable_field") is None and any(
                "unavailable_field" in item for item in result.get("limits", [])),
            "golden_mean": result.get("statistics", {}).get("response", {}).get("mean") == 14.5,
            "welch_anchor": abs(result.get("analysis_result", {}).get("tests", [{}])[0].get(
                "p_two_sided", 0) - 0.0040863304) < 1e-9,
            "artifacts_exist": not artifact_missing,
            "svg_traceable": "source-sha256" in (out / "figure.svg").read_text(encoding="utf-8"),
            "generate_only_honest": generated.returncode == 0 and generated_result.get("status") == "generated"
                                    and generated_result.get("execution_result", {}).get("executed") is False
                                    and not (generate_out / "analysis.json").exists(),
            "execution_duration_logged_separately": (out / "execution-log.json").is_file()
                                                      and json.loads((out / "execution-log.json").read_text(
                                                          encoding="utf-8")).get("duration_ms", 0) >= 0,
        }
        evidence = {"result_sha256": sha(result_path), "analysis_sha256": sha(out / "analysis.json"),
                    "code_sha256": sha(out / "analysis.py"), "validation": result.get("validation", {}).get("summary"),
                    "missing_contract_fields": missing, "missing_artifacts": artifact_missing}
    packaging = package_audit(package)
    checks["package_text_budget"] = packaging["passed"]
    return {"schema_version": "scicode-independent-verification/v1", "passed": all(checks.values()),
            "checks": checks, "cold_imports": imports, "evidence": evidence, "package": packaging}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--package", type=Path, default=PACKAGE)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    report = verify(args.package)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if args.report:
        args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
