"""Cross-check a written reproduction verdict against an actual rerun.py record.

The legacy checklist remains useful for planning.  This module only tightens it when a
real ``actual_run`` record is embedded or supplied as a JSON object.  Its verdict never of
its own turn a textual plan into a reproduce claim.
"""
from __future__ import annotations

import json
from pathlib import Path


def _add(findings, rule, severity, message, **extra):
    findings.append({"rule": rule, "severity": severity, "message": message, **extra})


def actual_record(spec):
    value = spec.get("actual_run")
    if isinstance(value, dict):
        return value
    if isinstance(value, str) and value.strip():
        try:
            obj = json.loads(Path(value).read_text(encoding="utf-8-sig"))
            return obj if isinstance(obj, dict) else None
        except (OSError, ValueError, UnicodeError):
            return {"status": "undetermined", "execution": {}, "findings": [],
                    "read_error": "actual_run could not be read as a JSON object"}
    return None


def audit(spec: dict, findings: list[dict]):
    record = actual_record(spec)
    if record is None:
        return
    checklist = spec.get("checklist") if isinstance(spec.get("checklist"), dict) else {}
    verdict = str(checklist.get("verdict") or "")
    execution = record.get("execution") if isinstance(record.get("execution"), dict) else {}
    if record.get("read_error"):
        _add(findings, "repro.execution_record_unreadable", "high", record["read_error"])
        return
    launched = execution.get("actually_launched") is True
    completed = execution.get("all_completed") is True
    if verdict == "reproducible" and not (launched and completed):
        _add(findings, "repro.execution_claim_unsupported", "high",
             "the report says reproducible but its actual run was not launched and completed; "
             "a checklist or a stored success string is not an execution")
    if not launched and record.get("status") not in {"undetermined"}:
        _add(findings, "repro.execution_record_incomplete", "high",
             "execution is not marked undetermined despite the record saying nothing actually launched")
    if record.get("code_version") and spec.get("commit") and record["code_version"] != spec["commit"]:
        _add(findings, "repro.execution_revision_mismatch", "high",
             "the report commit differs from the actually executed code version",
             report=spec["commit"], actual=record["code_version"])
    if record.get("data_version") and spec.get("data_version") and record["data_version"] != spec["data_version"]:
        _add(findings, "repro.execution_revision_mismatch", "high",
             "the report data version differs from the actually executed input snapshot",
             report=spec["data_version"], actual=record["data_version"])

    runs = record.get("runs") if isinstance(record.get("runs"), list) else []
    if launched and not runs:
        _add(findings, "repro.execution_record_incomplete", "high",
             "the record claims execution but carries no command-level records")
    any_metrics = False
    for index, run in enumerate(runs):
        if not isinstance(run, dict):
            _add(findings, "repro.execution_record_incomplete", "high",
                 "a command-level record is not an object", command_index=index)
            continue
        cid = run.get("id", index)
        if not isinstance(run.get("exit_code"), int) and run.get("completed"):
            _add(findings, "repro.execution_record_incomplete", "high",
                 "a supposedly completed run lacks a numeric exit code", command=cid)
        logs = run.get("logs") if isinstance(run.get("logs"), dict) else {}
        if (launched and run.get("actual_launched") is True and
                not str(logs.get("stdout") or "").strip() and not str(logs.get("stderr") or "").strip()):
            _add(findings, "repro.execution_record_incomplete", "high",
                 "an actually launched run has no retained stdout/stderr paths", command=cid)
        if run.get("completed") is not True:
            _add(findings, "repro.execution_command_failed", "high",
                 "an actual command did not complete; its failure needs repair before reproduction is claimed",
                 command=cid, failure_class=run.get("failure_class"))
        for metric in run.get("metrics") or []:
            if not isinstance(metric, dict):
                _add(findings, "repro.execution_metric_malformed", "high",
                     "a computed metric record is not an object", command=cid)
                continue
            any_metrics = True
            within = metric.get("within_tolerance")
            if within is False:
                _add(findings, "repro.verdict_inconsistent_execution", "high",
                     "an actually computed metric misses its predeclared tolerance; the missing "
                     "tolerance cannot be called a successful reproduction", command=cid,
                     metric=metric.get("name"), delta=metric.get("absolute_delta"),
                     bound=metric.get("bound"))
            elif within is None:
                _add(findings, "repro.execution_metric_undetermined", "medium",
                     "an execution metric is undetermined, not a passing comparison",
                     command=cid, metric=metric.get("name"), reason=metric.get("reason"))
            if not run.get("failure_class") and within is False and not metric.get("explanation"):
                _add(findings, "repro.execution_difference_unexplained", "medium",
                     "an out-of-tolerance metric lacks a source-grounded methodological explanation",
                     command=cid, metric=metric.get("name"))
    if completed and not any_metrics:
        _add(findings, "repro.execution_without_comparison", "medium",
             "the commands completed but have no metrics to compare against the paper; execution success alone is not reproduction")
    if verdict == "reproducible" and (record.get("status") != "clean" or not completed or not any_metrics):
        _add(findings, "repro.verdict_inconsistent_execution", "high",
             "the reproducible verdict does not agree with the actual execution/metric status",
             actual_status=record.get("status"))
