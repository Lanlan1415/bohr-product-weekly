"""Generate, optionally execute, and independently validate scientific analysis code.

Platform entry point:
  python scripts/scicode.py --case /input/case.json --spec /app/work/scicode-spec.json \
      --out /app/output --mode execute

Only code emitted by codegen.py is executed.  Caller-provided Python, shell
strings, network clients, and credential-bearing environments are not accepted.
Every runtime failure after argument parsing writes a structured result.json.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import platform
import sys
from pathlib import Path

# Isolated mode (-I) also implies -E, so an environment variable alone cannot
# prevent local bytecode artifacts.  Keep the installed text package clean.
sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))
import codegen  # noqa: E402
import runner  # noqa: E402
import validator  # noqa: E402

SCHEMA = "scicode/v1"
EXIT = {"clean": 0, "generated": 0, "review": 3, "blocked": 4, "undetermined": 5}
INTERNAL = {"output_contract", "case_id"}


def _read_json(path):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8-sig")), None
    except FileNotFoundError:
        return None, "file not found"
    except json.JSONDecodeError as exc:
        return None, f"invalid JSON at line {exc.lineno} column {exc.colno}"
    except (OSError, UnicodeError) as exc:
        return None, f"{type(exc).__name__}: {str(exc)[:300]}"


def _inside(path, root):
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def _resolve_input(spec_path, case_path, source, extra_roots, out_dir):
    if not isinstance(source, dict) or not isinstance(source.get("path"), str):
        raise codegen.SpecError("input.path_invalid", "spec.input.path must be a non-empty string")
    raw = source["path"]
    if "://" in raw:
        raise codegen.SpecError("input.network_forbidden", "network URLs are not valid input paths")
    candidate = Path(raw).expanduser()
    bases = [spec_path.parent]
    if case_path is not None:
        bases.append(case_path.parent)
    if not candidate.is_absolute():
        for base in bases:
            trial = (base / candidate).resolve()
            if trial.exists():
                candidate = trial
                break
        else:
            candidate = (bases[0] / candidate).resolve()
    else:
        candidate = candidate.resolve()
    roots = []
    for root in bases + [Path(x) for x in extra_roots]:
        try:
            roots.append(Path(root).resolve())
        except OSError:
            continue
    if not roots or not any(_inside(candidate, root) for root in roots):
        raise codegen.SpecError("input.path_outside_allowlist",
                                "input path must be inside the case/spec directory or --allow-input-root")
    if _inside(candidate, out_dir):
        raise codegen.SpecError("input.output_overlap", "input files must not reside in the output directory")
    return candidate


def _contract_fields(contract, limits, findings):
    if contract is None:
        return []
    if isinstance(contract, dict):
        return list(contract.keys())
    if isinstance(contract, list):
        fields = []
        for index, item in enumerate(contract):
            if isinstance(item, str):
                fields.append(item)
            else:
                limits.append(f"output_contract[{index}] is not a field-name string and was not echoed")
        return fields
    limits.append("output_contract is neither an object nor a field-name list")
    findings.append({"rule": "contract.invalid", "severity": "high",
                     "message": "output_contract must be an object or list of field names"})
    return []


def _base_result(case_id):
    return {
        "schema_version": SCHEMA, "case_id": case_id, "section": "scicode",
        "status": "undetermined", "code": None,
        "generated_code": {"generated": False}, "analysis_result": None,
        "execution_result": {"execution_attempted": False, "executed": False,
                             "reason": "not started"},
        "execution": {"execution_attempted": False, "executed": False},
        "validation": {"status": "not_run"},
        "environment": None, "artifacts": {}, "sources": [],
        "findings": [], "limits": [], "uncertainty": [],
    }


def _finalize(result, carrier, contract, out_dir):
    limits = result.setdefault("limits", [])
    findings = result.setdefault("findings", [])
    fields = _contract_fields(contract, limits, findings)
    # Recompute status after late contract/validation findings.
    if result.get("status") not in ("generated", "undetermined"):
        if any(f.get("severity") == "high" for f in findings):
            result["status"] = "blocked"
        elif findings:
            result["status"] = "review"
    if result.get("case_id") is None:
        result["case_id"] = None
        if "no case_id was supplied" not in limits:
            limits.append("no case_id was supplied")
    for key in fields:
        if key in result and result[key] is not None:
            continue
        if isinstance(carrier, dict) and key in carrier:
            result[key] = carrier[key]
        else:
            result[key] = None
            limits.append(f"output_contract field {key!r} was not derivable; null means not supplied, not passed")
    result["uncertainty"] = list(dict.fromkeys(limits))
    counts = {}
    for finding in findings:
        severity = finding.get("severity", "medium")
        counts[severity] = counts.get(severity, 0) + 1
    result["severity_counts"] = counts
    status = result.get("status", "undetermined")
    result["run_state"] = {
        "exit_code": EXIT.get(status, 5),
        "exit_meaning": status,
        "handoff": "inspect findings and limits before using any result",
    }
    out_dir.mkdir(parents=True, exist_ok=True)
    temporary = out_dir / "result.json.tmp"
    temporary.write_text(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False),
                         encoding="utf-8")
    temporary.replace(out_dir / "result.json")
    return result


def _refusal(out_dir, carrier, contract, case_id, rule, message):
    result = _base_result(case_id)
    result["findings"] = [{"rule": rule, "severity": "high", "message": message}]
    result["limits"] = ["the case could not be run as declared; no execution or numeric result is claimed"]
    return _finalize(result, carrier, contract, out_dir)


def build(spec_path, out_dir, case_path=None, mode="execute", timeout=20,
          max_output_chars=4000, allow_input_roots=(), max_input_bytes=25_000_000):
    spec_path = Path(spec_path).resolve()
    case_path = Path(case_path).resolve() if case_path else None
    out_dir = Path(out_dir).resolve()
    try:
        out_dir.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        # No writable output directory means no place for result.json; keep the
        # console refusal structured rather than emitting a traceback.
        return {"schema_version": SCHEMA, "case_id": None, "status": "undetermined",
                "findings": [{"rule": "output.unwritable", "severity": "high",
                              "message": f"{type(exc).__name__}: {str(exc)[:300]}"}]}

    spec, spec_error = _read_json(spec_path)
    case, case_error = (None, None)
    if case_path is not None:
        case, case_error = _read_json(case_path)
    carrier = case if isinstance(case, dict) else spec if isinstance(spec, dict) else {}
    contract = carrier.get("output_contract") if isinstance(carrier, dict) else None
    case_id = carrier.get("case_id") if isinstance(carrier, dict) else None
    if spec_error:
        return _refusal(out_dir, carrier, contract, case_id, "input.spec_unreadable", spec_error)
    if not isinstance(spec, dict):
        return _refusal(out_dir, carrier, contract, case_id, "input.spec_not_object",
                        "spec JSON must have an object at the top level")
    if case_path is not None and case_error:
        return _refusal(out_dir, spec, spec.get("output_contract"), spec.get("case_id"),
                        "input.case_unreadable", case_error)
    if case_path is not None and not isinstance(case, dict):
        return _refusal(out_dir, spec, spec.get("output_contract"), spec.get("case_id"),
                        "input.case_not_object", "case JSON must have an object at the top level")
    # A separate case file is authoritative for identity and output contract.
    if isinstance(case, dict):
        merged = dict(spec)
        merged["case_id"] = case.get("case_id")
        spec = merged
        carrier, contract, case_id = case, case.get("output_contract"), case.get("case_id")
    else:
        spec = dict(spec)
        spec["case_id"] = spec.get("case_id")
        carrier, contract, case_id = spec, spec.get("output_contract"), spec.get("case_id")

    try:
        source = spec.get("input")
        input_path = _resolve_input(spec_path, case_path, source, allow_input_roots, out_dir)
        code, normalized = codegen.generate_code(spec, resolved_input=input_path,
                                                 max_input_bytes=max_input_bytes)
    except codegen.SpecError as exc:
        return _refusal(out_dir, carrier, contract, case_id, exc.rule, exc.message)
    except (OSError, ValueError, TypeError) as exc:
        return _refusal(out_dir, carrier, contract, case_id, "spec.unprocessable",
                        f"{type(exc).__name__}: {str(exc)[:400]}")

    if not input_path.is_file():
        return _refusal(out_dir, carrier, contract, case_id, "input.file_missing",
                        f"declared input is not a regular file: {source.get('path')}")
    input_size = input_path.stat().st_size
    if input_size > normalized["input"]["max_bytes"]:
        return _refusal(out_dir, carrier, contract, case_id, "input.too_large",
                        f"input has {input_size} bytes; limit is {normalized['input']['max_bytes']}")
    input_sha = validator.file_sha256(input_path)
    expected_sha = (normalized.get("validation") or {}).get("expected_input_sha256")
    if expected_sha and expected_sha != input_sha:
        return _refusal(out_dir, carrier, contract, case_id, "validation.expected_input_sha256",
                        "actual input SHA256 differs from the declared snapshot")

    code_sha = hashlib.sha256(code.encode("utf-8")).hexdigest()
    code_path = out_dir / "analysis.py"
    code_path.write_bytes(code.encode("utf-8"))
    codegen.audit_generated_code(code_path.read_text(encoding="utf-8"))
    input_manifest = {
        "path": source.get("path"), "format": normalized["input"]["format"],
        "query": normalized["input"].get("query"), "sha256": input_sha, "bytes": input_size,
        "snapshot_policy": "source file hashed, never modified; extracted rows are a separate artifact",
    }
    (out_dir / "input-manifest.json").write_text(
        json.dumps(input_manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    environment = {
        "engine": codegen.ENGINE_VERSION,
        "python": platform.python_version(), "implementation": platform.python_implementation(),
        "platform": platform.platform(), "dependencies": {"third_party": [], "runtime": "Python standard library"},
        "seed": normalized["parameters"]["seed"],
        "float_precision": normalized["parameters"]["float_precision"],
        "code_sha256": code_sha, "input_sha256": input_sha,
        "code_generation": "deterministic declarative template",
        "execution_boundary": "generator-emitted code only; no shell, no network grammar, no caller secrets; not a general OS sandbox",
    }
    (out_dir / "environment.json").write_text(
        json.dumps(environment, ensure_ascii=False, indent=2), encoding="utf-8")

    result = _base_result(case_id)
    result["code"] = code
    result["generated_code"] = {"generated": True, "path": "analysis.py", "sha256": code_sha,
                                "standalone": True, "language": "Python"}
    result["environment"] = environment
    result["sources"] = [input_manifest]
    result["artifacts"] = {"code": "analysis.py", "input_manifest": "input-manifest.json",
                           "environment": "environment.json"}
    result["parameters"] = normalized["parameters"]
    result["data_dictionary"] = normalized["columns"]

    if mode == "generate":
        result["status"] = "generated"
        result["execution_result"] = {"execution_attempted": False, "executed": False,
                                      "reason": "generate-only mode; code is not claimed to have run"}
        result["execution"] = result["execution_result"]
        result["limits"] = ["code generation only: no execution result or scientific validation is claimed"]
        return _finalize(result, carrier, contract, out_dir)

    execution = runner.execute_generated(code_path, out_dir, timeout=timeout,
                                         max_output_chars=max_output_chars)
    result["execution_result"] = execution
    result["execution"] = execution
    result["artifacts"]["execution_log"] = "execution-log.json"
    analysis, analysis_error = _read_json(out_dir / "analysis.json")
    if analysis_error:
        analysis = None
    if isinstance(analysis, dict):
        result["analysis_result"] = analysis
        result["statistics"] = analysis.get("statistics")
        result["quality_report"] = analysis.get("data_quality")
        result["findings"].extend(analysis.get("findings") or [])
        result["limits"].extend(analysis.get("limits") or [])
        for key, value in (analysis.get("artifacts") or {}).items():
            result["artifacts"].setdefault(key, value)

    if execution.get("timed_out"):
        result["status"] = "undetermined"
        result["findings"].append({"rule": "execution.timeout", "severity": "high",
                                   "message": "generated code exceeded the configured timeout and was killed"})
        result["limits"].append("execution timed out; partial files are not scientific results")
    elif execution.get("spawn_error"):
        result["status"] = "undetermined"
        result["findings"].append({"rule": "execution.spawn_failed", "severity": "high",
                                   "message": execution["spawn_error"]})
    elif execution.get("exit_code") not in (0, 3, 4, 5):
        result["status"] = "blocked"
        result["findings"].append({"rule": "execution.failed", "severity": "high",
                                   "message": f"generated code exited unexpectedly with {execution.get('exit_code')}"})
    elif not isinstance(analysis, dict):
        result["status"] = "undetermined"
        result["findings"].append({"rule": "execution.result_missing", "severity": "high",
                                   "message": analysis_error or "analysis.json is not a JSON object"})
    else:
        validation, validation_findings = validator.validate_result(
            analysis, normalized, out_dir, code_sha, input_sha)
        result["validation"] = validation
        result["findings"].extend(validation_findings)
        result["artifacts"]["validation"] = "result.json"
        if analysis.get("status") == "undetermined" or execution.get("exit_code") == 5:
            result["status"] = "undetermined"
        elif analysis.get("status") == "blocked" or validation["status"] == "failed":
            result["status"] = "blocked"
        elif result["findings"]:
            result["status"] = "review"
        else:
            result["status"] = "clean"
    result["quality_and_reproducibility"] = {
        "input_manifest": "input-manifest.json", "environment": "environment.json",
        "execution_log": "execution-log.json", "validation": result["validation"],
    }
    return _finalize(result, carrier, contract, out_dir)


def main(argv=None):
    parser = argparse.ArgumentParser(prog="scicode", description=__doc__)
    parser.add_argument("--spec", required=True, help="declarative analysis spec JSON")
    parser.add_argument("--case", help="platform case.json (authoritative case_id/output_contract)")
    parser.add_argument("--out", required=True, help="dedicated output directory")
    parser.add_argument("--mode", choices=("generate", "execute"), default="execute")
    parser.add_argument("--timeout", type=int, default=20, help="child timeout in seconds (1..120)")
    parser.add_argument("--max-output-chars", type=int, default=4000, help="per-stream capture limit")
    parser.add_argument("--max-input-bytes", type=int, default=25_000_000)
    parser.add_argument("--allow-input-root", action="append", default=[],
                        help="additional trusted input root; repeatable")
    args = parser.parse_args(argv)
    result = build(Path(args.spec), Path(args.out), case_path=args.case, mode=args.mode,
                   timeout=args.timeout, max_output_chars=args.max_output_chars,
                   allow_input_roots=args.allow_input_root,
                   max_input_bytes=max(1, min(args.max_input_bytes, 100_000_000)))
    print(json.dumps({"case_id": result.get("case_id"), "status": result.get("status"),
                      "findings": [f.get("rule") for f in result.get("findings", [])],
                      "executed": (result.get("execution_result") or {}).get("executed", False),
                      "wrote": str(Path(args.out) / "result.json")}, ensure_ascii=False))
    return EXIT.get(result.get("status"), 5)


if __name__ == "__main__":
    raise SystemExit(main())
