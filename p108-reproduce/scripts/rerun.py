#!/usr/bin/env python3
"""Execute declared candidate methods and produce an honest, checkable run manifest.

Design follows MLCube's fixed runner/task declaration idea: same command declaration,
explicit input/output paths, and recorded environment.  It is intentionally a small
runner, not a container daemon, and does not claim container isolation.  ``python``
commands run through the current interpreter with ``-I`` and no shell; arbitrary
executables, network installers, missing hashes and out-of-workspace paths are refused.

Exit codes:
  0 all declared executions and metric checks completed/matched;
  3 executed, but non-matching metrics or incomplete coverage need review;
  4 execution failed (with actual log/exit evidence);
  5 declaration/material/security refusal (no claim that anything ran).
"""
from __future__ import annotations

import argparse
from collections import defaultdict
import hashlib
import importlib.metadata
import json
import math
import os
from pathlib import Path
import platform
import statistics
import subprocess
import sys

SCHEMA = "candidate-execution/v1"
STATUS_RC = {"clean": 0, "partial": 3, "blocked": 4, "undetermined": 5}


class Refusal(ValueError):
    pass


def sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        while True:
            part = f.read(1024 * 1024)
            if not part:
                break
            h.update(part)
    return h.hexdigest()


def manifest_hash(manifest) -> str:
    return hashlib.sha256(json.dumps(manifest, sort_keys=True, ensure_ascii=False,
                                    default=str).encode("utf-8")).hexdigest()


def inside(root: Path, relative) -> Path:
    if not isinstance(relative, str) or not relative.strip():
        raise Refusal("every material path must be a non-empty workspace-relative string")
    p = Path(relative)
    if p.is_absolute() or p.drive:
        raise Refusal("absolute material path is refused: " + relative)
    try:
        out = (root / p).resolve()
        out.relative_to(root.resolve())
    except (OSError, ValueError) as exc:
        raise Refusal("path escapes workspace: " + relative) from exc
    return out


def contract_fields(contract):
    if isinstance(contract, dict):
        return list(contract)
    if isinstance(contract, list):
        result = []
        for x in contract:
            if isinstance(x, str):
                result.append(x)
            elif isinstance(x, dict):
                for key in ("name", "field", "key", "id"):
                    if x.get(key) is not None:
                        result.append(str(x[key])); break
        return result
    return []


def _versions(deps):
    result = {}
    for entry in deps or []:
        if isinstance(entry, dict):
            name, wanted = str(entry.get("name") or ""), str(entry.get("version") or entry.get("required") or "")
        else:
            bits = str(entry).split("==", 1)
            name, wanted = bits[0].strip(), bits[1].strip() if len(bits) == 2 else ""
        if not name:
            raise Refusal("dependency name cannot be blank")
        try:
            actual = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            actual = None
        result[name] = {"declared": wanted or None, "actual": actual,
                        "available": actual is not None,
                        "version_conflict": bool(wanted and actual and wanted != actual)}
    return result


def result_value(obj, path):
    if path in (None, "", "."):
        return obj
    cur = obj
    if str(path).startswith("/"):
        parts = [p.replace("~1", "/").replace("~0", "~") for p in str(path).split("/")[1:]]
    else:
        parts = str(path).split(".")
    for part in parts:
        if isinstance(cur, dict):
            cur = cur.get(part)
        elif isinstance(cur, list) and part.isdigit():
            index = int(part)
            cur = cur[index] if index < len(cur) else None
        else:
            return None
    return cur


def _metric(record, warning, metric):
    name = metric.get("name")
    paper = metric.get("paper", metric.get("expected"))
    tol = metric.get("tolerance")
    path = metric.get("json_path", metric.get("path"))
    actual_raw = result_value(record, path)
    entry = {"name": name, "paper": paper, "reproduced": None,
             "json_path": path, "raw_result": actual_raw,
             "paper_locator": metric.get("paper_locator"),
             "statistic": metric.get("statistic"), "basis": metric.get("basis")}
    try:
        if not name or paper is None or tol is None or not path:
            raise ValueError("name, paper/expected, tolerance and json_path are required")
        actual = float(actual_raw)
        expected = float(paper)
        if not math.isfinite(actual) or not math.isfinite(expected):
            raise ValueError("non-finite metric")
        if isinstance(tol, dict):
            absolute = float(tol.get("abs", 0.0))
            relative = float(tol.get("rel", 0.0))
        elif isinstance(tol, (int, float)) and not isinstance(tol, bool):
            absolute, relative = float(tol), 0.0
        else:
            raise ValueError("tolerance must be numeric or {abs, rel}")
        if absolute < 0 or relative < 0 or not math.isfinite(absolute + relative):
            raise ValueError("tolerance must be finite and non-negative")
        delta = actual - expected
        bound = absolute + relative * abs(expected)
        entry.update({"reproduced": actual, "absolute_delta": delta,
                      "tolerance": {"abs": absolute, "rel": relative},
                      "bound": bound, "within_tolerance": abs(delta) <= bound,
                      "verdict": "within_tolerance" if abs(delta) <= bound else "out_of_tolerance",
                      "delta_class": "methodological" if abs(delta) > bound else None,
                      "explanation": "actual difference exceeds the predeclared abs+relative tolerance" if abs(delta) > bound else "computed from actual output and predeclared tolerance"})
        if abs(delta) > bound:
            warning.append({"kind": "metric_out_of_tolerance", "name": name,
                            "next_action": "Check command/configuration and data/code hashes first.  Then inspect stochastic variation with the same predeclared metric and additional declared seeds; do not relax the tolerance post hoc."})
    except (TypeError, ValueError, OverflowError) as exc:
        entry.update({"within_tolerance": None, "verdict": "undetermined",
                      "reason": str(exc)[:240]})
        warning.append({"kind": "metric_undetermined", "name": name,
                        "reason": str(exc)[:160],
                        "next_action": "Repair output parsing or supply source-backed expected value and tolerance; never infer one from the attempted run."})
    return entry


def _plan_argv(argv, root: Path):
    if not isinstance(argv, list) or not argv or not all(isinstance(x, str) for x in argv):
        raise Refusal("each command must be a non-empty argv list of strings")
    if argv[0] not in {"{python}", "python", "python3", sys.executable}:
        raise Refusal("only the declared Python runner is supported; no shell/arbitrary executable")
    if len(argv) < 2 or not argv[1].endswith(".py"):
        raise Refusal("the runner executes exactly one declared workspace .py script; -c/-m/shell commands are refused")
    out = [sys.executable, "-I"]
    for token in argv[1:]:
        # Material filenames are resolved to absolute workspace files, so -I cannot
        # select a same-named planted file in the caller directory.
        if token.endswith(".py") or "/" in token or "\\" in token or token.startswith("."):
            if any(c in token for c in ["\r", "\n"]):
                raise Refusal("newline in path token is refused")
            path = inside(root, token)
            if token.endswith(".py") and not path.is_file():
                raise Refusal("declared input/script path is missing: " + token)
            # Input data is covered individually by files.sha256.  A possibly-new path
            # here can therefore be a declared command output, never an excuse to escape.
            out.append(str(path))
        else:
            out.append(token)
    return out


def re_search_dependency(stderr_bytes: bytes) -> bool:
    text = stderr_bytes.decode("utf-8", errors="replace").lower()
    return any(marker in text for marker in ("modulenotfounderror", "importerror",
                                             "no module named", "package is required"))


def _read_command_output(command, run_dir: Path, root: Path):
    source = command.get("output")
    if source:
        path = source if isinstance(source, str) else source.get("path")
        if not isinstance(path, str):
            raise ValueError("output path must be a string")
        p = inside(root, path)
        if not p.is_file():
            raise ValueError("declared output file was not produced: " + path)
        if p.stat().st_size > 2_000_000:
            raise ValueError("JSON output exceeds 2 MB cap")
        try:
            return json.loads(p.read_text(encoding="utf-8-sig")), str(p)
        except (OSError, UnicodeError, ValueError) as exc:
            raise ValueError("cannot read declared JSON output: " + str(exc)[:180]) from exc
    text = (run_dir / "stdout.log").read_text(encoding="utf-8", errors="replace")
    # Only the last non-empty line is a candidate JSON result.  It is parsed, never eval'ed.
    lines = [line for line in text.splitlines() if line.strip()]
    if not lines:
        raise ValueError("no printed JSON result is available")
    try:
        return json.loads(lines[-1]), "stdout:last_non_empty_json"
    except ValueError as exc:
        raise ValueError("last stdout line is not JSON; declare output instead") from exc


def execute(manifest: dict, root: Path, output: Path):
    if not isinstance(manifest, dict):
        raise Refusal("manifest must be a JSON object")
    if str(manifest.get("schema_version") or SCHEMA).split("/")[0] not in {"candidate-execution", "rerun"}:
        raise Refusal("unsupported manifest schema")
    for key in ("code_version", "data_version", "seed"):
        if manifest.get(key) in (None, ""):
            raise Refusal("missing required run declaration: " + key)
    commands = manifest.get("commands")
    if not isinstance(commands, list) or not commands:
        raise Refusal("manifest.commands must contain at least one command")
    declared_files = manifest.get("files") or {}
    if not isinstance(declared_files, dict):
        raise Refusal("manifest.files must map workspace-relative paths to sha256 records")
    if len(commands) > 20:
        raise Refusal("more than 20 commands is outside this runner's bounded execution contract")
    file_evidence = {}
    for name, rec in declared_files.items():
        path = inside(root, name)
        if not path.is_file():
            raise Refusal("required material is missing: " + name)
        if path.stat().st_size > 100_000_000:
            raise Refusal("material exceeds 100 MB runner limit: " + name)
        expected = rec.get("sha256") if isinstance(rec, dict) else rec
        actual = sha(path)
        if not expected:
            raise Refusal("required material has no expected sha256: " + name)
        if actual != str(expected).lower():
            raise Refusal("material hash mismatch: " + name)
        file_evidence[name] = rec if isinstance(rec, dict) else {"sha256": rec}
        file_evidence[name] = dict(file_evidence[name], actual_sha256=actual,
                                   bytes=path.stat().st_size, verified=True)
    deps = _versions(manifest.get("dependencies"))
    timeout = manifest.get("timeout_s", 60)
    try:
        timeout = float(timeout)
    except (TypeError, ValueError) as exc:
        raise Refusal("timeout_s must be numeric") from exc
    if not 0.1 <= timeout <= 300:
        raise Refusal("timeout_s is outside 0.1..300 second runner bound")

    output.mkdir(parents=True, exist_ok=True)
    results, findings = [], []
    executed_any = False
    for idx, command in enumerate(commands):
        if not isinstance(command, dict):
            raise Refusal("command entry must be an object")
        cid = str(command.get("id") or "command-%02d" % (idx + 1))
        run_dir = output / "runs" / cid
        run_dir.mkdir(parents=True, exist_ok=True)
        run = {"id": cid, "declared_argv": command.get("argv"),
               "actual_launched": False, "completed": False,
               "seed": command.get("seed", manifest["seed"]),
               "series": command.get("series"),
               "metrics": [], "logs": {}, "failure_class": None}
        try:
            unavailable = [name for name, rec in deps.items() if not rec["available"]]
            conflicts = [name for name, rec in deps.items() if rec["version_conflict"]]
            if unavailable:
                run["failure_class"] = "dependency_error"
                raise Refusal("declared dependencies unavailable: " + ",".join(unavailable))
            declared_argv = command.get("argv")
            script_name = declared_argv[1] if isinstance(declared_argv, list) and len(declared_argv) > 1 else None
            if script_name not in declared_files:
                raise Refusal("the command's .py entry script must have its own verified files.sha256 entry")
            argv = _plan_argv(declared_argv, root)
            env = {"PATH": os.environ.get("PATH", ""), "SYSTEMROOT": os.environ.get("SYSTEMROOT", ""),
                   "PYTHONHASHSEED": str(run["seed"]), "SEED": str(run["seed"]), "PYTHONIOENCODING": "utf-8",
                   "LC_ALL": "C.UTF-8", "LANG": "C.UTF-8", "TZ": "UTC",
                   "SOURCE_DATE_EPOCH": str(int(run["seed"]))}
            for key in ("TEMP", "TMP", "HOME", "USERPROFILE"):
                if os.environ.get(key):
                    env[key] = os.environ[key]
            with (run_dir / "stdout.log").open("wb") as stdout, (run_dir / "stderr.log").open("wb") as stderr:
                run["actual_launched"] = True
                executed_any = True
                try:
                    proc = subprocess.run(argv, cwd=str(root), env=env, stdout=stdout, stderr=stderr,
                                          stdin=subprocess.DEVNULL, timeout=min(timeout, float(command.get("timeout_s", timeout))),
                                          check=False)
                    exit_code = proc.returncode
                    failure = None if exit_code == 0 else "execution_error"
                except subprocess.TimeoutExpired:
                    exit_code, failure = None, "timeout"
                stderr_bytes = (run_dir / "stderr.log").read_bytes()[:2_000_000]
                if failure and re_search_dependency(stderr_bytes):
                    failure = "dependency_error"
                # Runtime belongs to the native platform trace, not this deterministic result.
            run["argv"] = argv
            run["exit_code"] = exit_code
            run["completed"] = exit_code == 0
            run["logs"] = {"stdout": str((run_dir / "stdout.log").relative_to(output)),
                           "stderr": str((run_dir / "stderr.log").relative_to(output))}
            for stream in ("stdout.log", "stderr.log"):
                if (run_dir / stream).stat().st_size > 20_000_000:
                    findings.append({"rule": "repro.log_truncation_review", "severity": "medium",
                                     "command": cid, "message": stream + " exceeds 20 MB; retained on disk, result does not inline it"})
            run["failure_class"] = failure
            if conflicts:
                findings.append({"rule": "repro.env_version_conflict", "severity": "high", "command": cid,
                                 "dependencies": {name: deps[name] for name in conflicts},
                                 "next_action": "Pin the declared dependency in an isolated environment and rerun; do not report these results as the declared version."})
            if exit_code != 0:
                findings.append({"rule": "repro.execution_failed", "severity": "high", "command": cid,
                                 "failure_class": failure, "exit_code": exit_code,
                                 "next_action": "Read the saved stderr and material versions; repair dependency/command/data errors before claiming output-level reproduction."})
                results.append(run)
                continue
            record, metric_source = _read_command_output(command, run_dir, root)
            run["metric_source"] = metric_source
            for metric in command.get("metrics") or []:
                if not isinstance(metric, dict):
                    findings.append({"rule": "repro.metric_spec_malformed", "severity": "high", "command": cid,
                                     "message": "metric declaration is not an object"})
                    continue
                warnings = []
                computed = _metric(record, warnings, metric)
                run["metrics"].append(computed)
                findings.extend({"rule": "repro.metric_out_of_tolerance" if w["kind"] == "metric_out_of_tolerance" else "repro.metric_undetermined",
                                 "severity": "high" if w["kind"] == "metric_out_of_tolerance" else "medium",
                                 "command": cid, "failure_class": w["kind"], **w} for w in warnings)
            if not command.get("metrics"):
                run["coverage"] = "executed without a declared comparison; not a reproduction verdict"
        except (Refusal, OSError, ValueError, TypeError) as exc:
            message = str(exc)[:240]
            inferred_class = "missing_material" if "missing" in message.lower() else "declaration_or_output_error"
            run.update({"completed": False, "failure_class": run.get("failure_class") or inferred_class,
                        "failure_reason": message})
            findings.append({"rule": "repro.run_incomplete", "severity": "high", "command": cid,
                             "failure_class": run["failure_class"], "message": str(exc)[:240],
                             "next_action": "Resolve this declared dependency/material/output failure and execute again; this run is not reproduced."})
        results.append(run)
    return results, findings, deps, file_evidence, executed_any


def variation(runs):
    groups = defaultdict(list)
    for run in runs:
        if not run.get("series"):
            continue
        for metric in run.get("metrics") or []:
            if isinstance(metric.get("reproduced"), (int, float)):
                key = run["series"], metric.get("name")
                groups[key].append((run.get("seed"), metric["reproduced"]))
    out = []
    for (group, name), pairs in sorted(groups.items(), key=str):
        values = [v for _, v in pairs]
        if len(values) > 1:
            out.append({"group": group, "metric": name, "seeds": [s for s, _ in pairs],
                        "values": values, "mean": statistics.fmean(values),
                        "stdev": statistics.stdev(values), "min": min(values), "max": max(values),
                        "not_a_confidence_interval": True})
    return out


def finalize(manifest, case, runs, findings, deps, files, executed, output, root):
    failed = [r for r in runs if not r.get("completed")]
    findings_high = any(f.get("severity") == "high" for f in findings)
    undetermined_metrics = any(m.get("within_tolerance") is None for r in runs for m in r.get("metrics") or [])
    no_comparison = any(not r.get("metrics") for r in runs if r.get("completed"))
    if failed:
        status = "blocked"
    elif runs and not undetermined_metrics and not findings_high and not no_comparison:
        status = "clean"
    else:
        status = "partial"
    if not executed:
        status = "undetermined"
    payload = {"schema_version": SCHEMA, "case_id": case.get("case_id") if case else manifest.get("case_id"),
               "status": status, "scope": manifest.get("scope", "declared candidate methods only"),
               "paper_reproduction_claim": False,
               "claim_boundary": "This runner verifies the declared command/material snapshot.  It does not recreate an unavailable original repository, dataset, container, physical experiment or full paper result.",
               "execution": {"actually_launched": executed, "all_completed": bool(runs) and not failed,
                             "command_count": len(runs), "completed_count": len(runs) - len(failed)},
               "code_version": manifest["code_version"], "data_version": manifest["data_version"],
               "parameters": manifest.get("parameters", []),
               "environment": {"python": sys.version, "python_executable": sys.executable,
                               "platform": platform.platform(), "machine": platform.machine(),
                               "processor": platform.processor() or "not_reported",
                               "seed": manifest["seed"], "dependencies": deps,
                               "container_isolation": False},
               "files": files, "manifest_sha256": manifest_hash(manifest),
               "runs": runs,
               "metrics": [dict(m, command=r["id"]) for r in runs for m in r.get("metrics") or []],
               "seed_variation": variation(runs), "findings": findings,
               "failure_analysis": [{"command": r["id"], "class": r.get("failure_class"),
                                     "reason": r.get("failure_reason"),
                                     "next_action": "Inspect stderr and restore missing/undeclared dependencies/materials; then rerun unchanged inputs."}
                                    for r in runs if r.get("failure_class")],
               "limits": ["No shell/container isolation is claimed. Only declared Python argv is supported.",
                          "A zero exit code is execution success, not scientific correctness; metrics decide that separately.",
                          "Dependencies without an exact declared version are availability checks, not version-equivalence evidence.",
                          "Seed variance is descriptive; no confidence interval is claimed for a tiny convenience sample."],
               "logs_root": "runs"}
    aliases = {"sources": files, "environment_snapshot": payload["environment"],
               "execution_records": runs, "metrics": [dict(m, command=r["id"]) for r in runs for m in r.get("metrics") or []],
               "comparison_metrics": [dict(m, command=r["id"]) for r in runs for m in r.get("metrics") or []],
               "failure_classifications": payload["failure_analysis"], "uncertainty": payload["limits"],
               "run_manifest": "run-manifest.json"}
    for key in contract_fields((case or {}).get("output_contract")):
        if key in payload:
            continue
        if key in aliases:
            payload[key] = aliases[key]
        elif key in case:
            payload[key] = case[key]
        else:
            payload[key] = None
            payload["limits"].append("output_contract field %r was not derivable from actual execution records" % key)
    # Do not persist self-reported timestamps: valid deterministic reruns byte-compare cleanly.
    (output / "run-manifest.json").write_text(json.dumps({
        "schema_version": SCHEMA, "manifest": manifest, "files": files,
        "manifest_sha256": payload["manifest_sha256"], "environment": payload["environment"],
        "scope": payload["scope"]}, ensure_ascii=False, indent=2), encoding="utf-8")
    return payload


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--manifest", required=True)
    ap.add_argument("--workspace", required=True, help="material root; all paths must remain inside it")
    ap.add_argument("--out", required=True)
    ap.add_argument("--case", help="optional case.json supplying case_id/output_contract")
    args = ap.parse_args(argv)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    case = {}
    manifest = {}
    try:
        if args.case:
            case = json.loads(Path(args.case).read_text(encoding="utf-8-sig"))
            if not isinstance(case, dict):
                raise Refusal("case.json is not an object")
        manifest = json.loads(Path(args.manifest).read_text(encoding="utf-8-sig"))
        root = Path(args.workspace).resolve()
        if not root.is_dir():
            raise Refusal("workspace is not a directory")
        runs, findings, deps, files, executed = execute(manifest, root, out)
        result = finalize(manifest, case, runs, findings, deps, files, executed, out, root)
    except (OSError, UnicodeError, ValueError, TypeError) as exc:
        result = {"schema_version": SCHEMA, "case_id": case.get("case_id"),
                  "status": "undetermined",
                  "execution": {"actually_launched": False, "all_completed": False},
                  "findings": [{"rule": "repro.refused", "severity": "high", "message": str(exc)[:300],
                                "failure_class": "declaration_or_material_refusal"}],
                  "limits": ["Nothing was claimed to execute; correct declaration/material errors first."]}
        for key in contract_fields(case.get("output_contract")):
            if key not in result:
                result[key] = case.get(key)
                if key not in case:
                    result["limits"].append("output_contract field %r cannot be derived after refusal" % key)
        result["failure_analysis"] = [{"class": "declaration_or_material_refusal",
                                       "next_action": "Correct the manifest, hashes, dependencies and paths before execution."}]
    (out / "result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    rc = STATUS_RC[result["status"]]
    print(json.dumps({"status": result["status"], "rc": rc,
                      "actually_launched": result["execution"]["actually_launched"],
                      "commands": result["execution"].get("command_count", 0),
                      "wrote": str(out / "result.json")}, ensure_ascii=False))
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
