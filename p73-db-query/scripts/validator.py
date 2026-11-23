"""Independent post-execution checks for generated scientific analyses."""
from __future__ import annotations

import csv
import hashlib
import json
import math
import statistics
from pathlib import Path


def file_sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        while True:
            block = handle.read(1024 * 1024)
            if not block:
                break
            digest.update(block)
    return digest.hexdigest()


def _get_path(data, path):
    current = data
    for part in path.split("."):
        if isinstance(current, dict) and part in current:
            current = current[part]
        elif isinstance(current, list):
            try:
                current = current[int(part)]
            except (ValueError, IndexError):
                return None
        else:
            return None
    return current


def validate_result(analysis, spec, out_dir, code_sha256, input_sha256):
    """Recompute means from cleaned.csv and verify hashes, structure and goldens."""
    out_dir = Path(out_dir)
    checks, findings = [], []

    def check(name, passed, details=None, severity="high"):
        item = {"check": name, "passed": bool(passed)}
        if details is not None:
            item["details"] = details
        checks.append(item)
        if not passed:
            findings.append({"rule": f"validation.{name}", "severity": severity,
                             "message": f"post-execution check failed: {name}",
                             "details": details})

    check("analysis_object", isinstance(analysis, dict))
    if not isinstance(analysis, dict):
        return {"status": "failed", "checks": checks,
                "summary": {"passed": 0, "failed": 1}}, findings
    check("code_sha256", file_sha256(out_dir / "analysis.py") == code_sha256)
    check("input_sha256", (analysis.get("input") or {}).get("sha256") == input_sha256,
          {"expected": input_sha256, "actual": (analysis.get("input") or {}).get("sha256")})

    cleaned_path = out_dir / "cleaned.csv"
    if analysis.get("status") != "undetermined" and cleaned_path.is_file():
        try:
            with cleaned_path.open("r", encoding="utf-8", newline="") as handle:
                cleaned = list(csv.DictReader(handle))
            check("cleaned_row_count", len(cleaned) == (analysis.get("input") or {}).get("rows_analysed"),
                  {"csv": len(cleaned), "analysis": (analysis.get("input") or {}).get("rows_analysed")})
            for name, reported in (analysis.get("statistics") or {}).items():
                values = []
                for row in cleaned:
                    raw = row.get(name, "")
                    if raw == "":
                        continue
                    try:
                        value = float(raw)
                    except (TypeError, ValueError, OverflowError):
                        continue
                    if math.isfinite(value):
                        values.append(value)
                mean_ok = (not values and reported.get("n") == 0 and reported.get("mean") is None)
                if values and reported.get("mean") is not None:
                    mean_ok = math.isclose(statistics.fmean(values), float(reported.get("mean")),
                                           rel_tol=1e-8, abs_tol=1e-8)
                check(f"mean_recomputed.{name}", mean_ok,
                      {"csv_n": len(values), "csv_mean": statistics.fmean(values) if values else None,
                       "reported": reported.get("mean")})
                check(f"count_accounting.{name}",
                      int(reported.get("rows", -1)) == int(reported.get("n", -2)) +
                      int(reported.get("missing", -3)) + int(reported.get("unparsed", -4)),
                      reported)
        except (OSError, csv.Error, UnicodeError, TypeError, ValueError) as exc:
            check("cleaned_recomputation", False, f"{type(exc).__name__}: {str(exc)[:300]}")

    declared = (spec.get("validation") or {})
    if "expected_rows" in declared:
        actual = (analysis.get("input") or {}).get("rows_read")
        check("expected_rows", actual == declared["expected_rows"],
              {"expected": declared["expected_rows"], "actual": actual})
    if "expected_columns" in declared:
        actual = (analysis.get("input") or {}).get("source_columns") or []
        missing = [name for name in declared["expected_columns"] if name not in actual]
        check("expected_columns", not missing, {"missing": missing, "actual": actual})
    if declared.get("expected_input_sha256"):
        check("expected_input_sha256", input_sha256 == declared["expected_input_sha256"],
              {"expected": declared["expected_input_sha256"], "actual": input_sha256})

    for index, golden in enumerate(declared.get("golden") or []):
        actual = _get_path(analysis, golden["path"])
        expected = golden["value"]
        passed = False
        if isinstance(expected, (int, float)) and not isinstance(expected, bool):
            try:
                passed = math.isclose(float(actual), float(expected),
                                      rel_tol=golden["rtol"], abs_tol=golden["atol"])
            except (TypeError, ValueError, OverflowError):
                passed = False
        else:
            passed = actual == expected
        check(f"golden.{index}", passed, {"path": golden["path"], "expected": expected, "actual": actual})

    if analysis.get("chart"):
        figure = out_dir / "figure.svg"
        valid = False
        if figure.is_file():
            try:
                text = figure.read_text(encoding="utf-8")
                valid = "<svg" in text and "</svg>" in text and input_sha256 in text
            except (OSError, UnicodeError):
                valid = False
        check("figure_svg", valid)
    passed = sum(1 for item in checks if item["passed"])
    failed = len(checks) - passed
    return {"status": "passed" if failed == 0 else "failed",
            "summary": {"passed": passed, "failed": failed}, "checks": checks}, findings
