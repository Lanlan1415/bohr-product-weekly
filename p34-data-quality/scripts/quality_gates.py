"""Table-derived quality gates, before/after reconciliation, and reversible edits.

The validation-result shape follows the useful part of Great Expectations'
workflow: each expectation names its target and parameters and carries observed
and failing counts plus row-level evidence.  This implementation is deliberately
stdlib-only and evaluates both the input and the actual cleaned table.
"""
from __future__ import annotations

import copy
import hashlib
import json
from collections import OrderedDict

import cleaning as C

REWRITE_RULES = {"R01", "R04", "R08"}
SUMMARY_KEYS = ("rows", "columns", "cells", "missing_cells", "unparsed_cells",
                "rewritten_cells", "duplicate_records", "duplicate_experiments")


def _digest(rows) -> str:
    payload = json.dumps(rows, sort_keys=True, ensure_ascii=False,
                         separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _summary(result: dict) -> dict:
    report = result.get("quality_report") or {}
    return {key: report.get(key) for key in SUMMARY_KEYS}


def _column_map(result: dict) -> dict:
    return {str(rec.get("column")): rec
            for rec in (result.get("quality_report") or {}).get("per_column", [])
            if isinstance(rec, dict)}


def _rule_rows(result: dict, *rules: str) -> list[int]:
    wanted = set(rules)
    return sorted({int(c["row"]) for c in result.get("changes", [])
                   if c.get("rule") in wanted and isinstance(c.get("row"), int)})


def _duplicate_rows(result: dict, kind: str) -> list[int]:
    key = "rule_duplicate_records" if kind == "records" else "rule_duplicate_experiments"
    rows = set()
    for rec in (result.get("duplicates") or {}).get(key, []):
        if isinstance(rec, dict):
            rows.update(i for i in rec.get("rows", []) if isinstance(i, int))
    return sorted(rows)


def build_validation_results(before: dict, after: dict, spec: dict) -> list[dict]:
    """Evaluate schema, completeness, validity, range, units and uniqueness.

    ``before_failed`` is evidence of improvement, not a second score. ``success``
    always describes the actual final table. No expectation is silently skipped:
    absent keys produce an explicit not-evaluated uniqueness record.
    """
    bcols, acols = _column_map(before), _column_map(after)
    rows = after.get("cleaned_table") or []
    columns = [str(c["name"]) for c in spec.get("columns", [])
               if isinstance(c, dict) and str(c.get("name") or "").strip()]
    actual_columns = sorted({str(k) for row in rows if isinstance(row, dict) for k in row})
    results: list[dict] = []

    def add(name, dimension, column, observed, before_failed, after_failed,
            failing_rows=None, parameters=None, evidence=None):
        after_failed = None if after_failed is None else int(after_failed)
        rec = {
            "expectation": name,
            "dimension": dimension,
            "column": column,
            "parameters": parameters or {},
            "observed_count": int(observed),
            "before_failed": None if before_failed is None else int(before_failed),
            "after_failed": after_failed,
            "success": None if after_failed is None else after_failed == 0,
            "success_rate": (None if after_failed is None or not observed
                             else round(max(0.0, (observed - after_failed) / observed), 6)),
            "failing_rows": list(failing_rows or [])[:50],
            "evidence": evidence or {},
        }
        results.append(rec)

    missing_before = [c for c in columns if c not in actual_columns]
    add("schema.columns_present", "schema", None, len(columns),
        len(missing_before), len(missing_before), parameters={"expected": columns},
        evidence={"missing_columns": missing_before})
    for col in columns:
        b, a = bcols.get(col, {}), acols.get(col, {})
        n = int(a.get("cells") or len(rows))
        brow = _rule_rows(before, "R02")
        arow = _rule_rows(after, "R02")
        add("completeness.non_missing", "completeness", col, n,
            b.get("missing"), a.get("missing"), arow,
            evidence={"missing_after": a.get("missing"), "missing_means_not_zero": True})
        invalid_b = int(b.get("unparsed") or 0) + int(b.get("unit_refused") or 0)
        invalid_a = int(a.get("unparsed") or 0) + int(a.get("unit_refused") or 0)
        add("validity.declared_type", "validity", col, n, invalid_b, invalid_a,
            _rule_rows(after, "R03", "R08"),
            {"semantic": (a.get("semantic") or b.get("semantic"))},
            {"unparsed_after": a.get("unparsed"), "unit_refused_after": a.get("unit_refused")})
        declared = next((c for c in spec.get("columns", [])
                         if isinstance(c, dict) and c.get("name") == col), {})
        plausible = declared.get("plausible")
        if isinstance(plausible, (list, tuple)) and len(plausible) == 2:
            bbad = sum(1 for c in before.get("changes", [])
                       if c.get("rule") == "R05" and c.get("column") == col)
            abad = sum(1 for c in after.get("changes", [])
                       if c.get("rule") == "R05" and c.get("column") == col)
            arows = sorted({c["row"] for c in after.get("changes", [])
                            if c.get("rule") == "R05" and c.get("column") == col})
            add("validity.declared_range", "validity", col, n, bbad, abad, arows,
                {"plausible": list(plausible)},
                {"action": "flagged_and_retained", "automatic_cap_or_delete": False})
        target = declared.get("target_unit")
        if target:
            bunit = sum(1 for c in before.get("changes", [])
                        if c.get("rule") == "R04" and c.get("column") == col)
            arefused = int(a.get("unit_refused") or 0)
            refused_rows = [c["row"] for c in after.get("changes", [])
                            if c.get("rule") == "R04" and c.get("column") == col
                            and c.get("new") is None]
            add("consistency.target_unit", "consistency", col, n, bunit, arefused,
                refused_rows, {"target_unit": target},
                {"converted_before": sum(1 for c in before.get("changes", [])
                                          if c.get("rule") == "R04" and c.get("column") == col
                                          and c.get("new") is not None),
                 "conversion_factor_in_ledger": True})

    keys = spec.get("key_columns") or []
    if keys:
        for kind, expectation, dimension in (
                ("records", "uniqueness.no_record_copies", "uniqueness"),
                ("experiments", "consistency.no_key_conflicts", "consistency")):
            arows = _duplicate_rows(after, kind)
            brows = _duplicate_rows(before, kind)
            add(expectation, dimension, None, len(rows), len(brows), len(arows), arows,
                {"key_columns": list(keys)},
                {"duplicate_groups_after": int((after.get("duplicates") or {})
                                               .get("duplicate_" + kind, 0)),
                 "action": "reported_not_merged"})
    else:
        add("uniqueness.no_record_copies", "uniqueness", None, len(rows), None, None,
            parameters={"key_columns": []},
            evidence={"status": "not_evaluated",
                      "reason": "no real key_columns declared; rows were not collapsed"})
    return results


def direct_table_counts(rows: list[dict], spec: dict) -> dict:
    """Independent light-weight recount used to reconcile the generated report."""
    columns = [str(c["name"]) for c in spec.get("columns", [])
               if isinstance(c, dict) and str(c.get("name") or "").strip()]
    tokens = C.missing_token_set(spec)
    cells = missing = 0
    for col in columns:
        for row in rows:
            if not isinstance(row, dict):
                continue
            cells += 1
            if C.is_missing_token(str(row.get(col, "") or ""), tokens):
                missing += 1
    return {"rows": len([r for r in rows if isinstance(r, dict)]),
            "columns": len(columns), "cells": cells, "missing_cells": missing}


def restore_rows(cleaned_rows: list[dict], changes: list[dict]) -> list[dict]:
    """Undo actual rewrites in reverse ledger order; refuse on table drift.

    Diagnostics (R02/R03/R05) are intentionally not undo operations because they
    never changed the table. Every edit applied here carries its original value.
    """
    restored = copy.deepcopy(cleaned_rows)
    edits = [(i, c) for i, c in enumerate(changes)
             if c.get("rule") in REWRITE_RULES and c.get("new") is not None]
    for ledger_index, change in reversed(edits):
        row, col = change.get("row"), change.get("column")
        if not isinstance(row, int) or row < 0 or row >= len(restored) or col not in restored[row]:
            raise ValueError(f"ledger entry {ledger_index} points outside the cleaned table")
        current = restored[row][col]
        if str(current) != str(change.get("new")):
            raise ValueError(f"ledger entry {ledger_index} does not match the current cell; "
                             "refusing to overwrite a later edit")
        restored[row][col] = change.get("original")
    return restored


def augment(result: dict, original_rows: list[dict], spec: dict) -> dict:
    """Add all reviewable evidence after the core rules have produced a table."""
    import cleaning as core
    cleaned = result.get("cleaned_table") or []
    after = core.clean(cleaned, spec)
    before_summary, after_summary = _summary(result), _summary(after)
    validations = build_validation_results(result, after, spec)
    evaluated = [v for v in validations if v["success"] is not None]
    result["validation_results"] = validations
    result["validation_summary"] = {
        "total": len(validations), "evaluated": len(evaluated),
        "passed": sum(v["success"] is True for v in evaluated),
        "failed": sum(v["success"] is False for v in evaluated),
        "before_failed_total": sum(v["before_failed"] or 0 for v in evaluated),
        "after_failed_total": sum(v["after_failed"] or 0 for v in evaluated),
        "evaluated_on": "actual_cleaned_table",
    }
    result["data_dictionary"] = {
        "declared_columns": copy.deepcopy(spec.get("columns") or []),
        "actual_columns": sorted({str(k) for r in original_rows if isinstance(r, dict) for k in r}),
        "key_columns": list(spec.get("key_columns") or []),
        "value_columns": list(spec.get("value_columns") or []),
        "missing_tokens": sorted(C.missing_token_set(spec)),
        "dictionary_source": "spec.columns copied from the case dictionary by the caller",
    }
    actual_edits = [(i, c) for i, c in enumerate(result.get("changes", []))
                    if c.get("rule") in REWRITE_RULES and c.get("new") is not None]
    result["reversible_log"] = [
        {"ledger_index": i, "rule": c.get("rule"), "row": c.get("row"),
         "column": c.get("column"), "original": c.get("original"), "new": c.get("new"),
         "can_undo": True, "undo": {"row": c.get("row"), "column": c.get("column"),
                                    "restore": c.get("original")}}
        for i, c in actual_edits]
    result["reversible_log_complete"] = len(actual_edits) == sum(
        1 for c in result.get("changes", [])
        if c.get("rule") in REWRITE_RULES and c.get("new") is not None)
    changed_coordinates = {(c.get("row"), c.get("column")) for _, c in actual_edits}
    direct = direct_table_counts(cleaned, spec)
    checks = [{"field": key, "reported": after_summary.get(key), "recounted": direct.get(key),
               "match": after_summary.get(key) == direct.get(key)}
              for key in ("rows", "columns", "cells", "missing_cells")]
    result["before_after"] = {
        "before": before_summary, "after": after_summary,
        "delta_after_minus_before": {k: ((after_summary.get(k) or 0) - (before_summary.get(k) or 0))
                                      for k in SUMMARY_KEYS},
        "changed_cells": len(changed_coordinates),
        "changed_cell_coordinates": [{"row": r, "column": c} for r, c in sorted(changed_coordinates)],
        "rows_added": max(0, len(cleaned) - len(original_rows)),
        "rows_removed": max(0, len(original_rows) - len(cleaned)),
        "missing_cells_imputed": max(0, int((before_summary.get("missing_cells") or 0)
                                            - (after_summary.get("missing_cells") or 0))),
        "original_sha256": _digest(original_rows), "cleaned_sha256": _digest(cleaned),
    }
    result["report_reconciliation"] = {
        "checks": checks, "all_match": all(c["match"] for c in checks),
        "recount_method": "direct row/cell pass over cleaned_table, independent of report totals",
    }
    if not result["report_reconciliation"]["all_match"]:
        result.setdefault("findings", []).append({
            "rule": "clean.report_table_mismatch", "severity": "high",
            "message": "quality report totals do not match a direct recount of cleaned_table",
            "checks": checks})
    refused_units = [{"column": name, "count": rec.get("unit_refused", 0)}
                     for name, rec in _column_map(after).items() if rec.get("unit_refused")]
    if refused_units:
        result.setdefault("findings", []).append({
            "rule": "clean.unit_refused", "severity": "medium",
            "message": "unknown or incompatible units were not converted; affected cells remain named gaps",
            "detail": refused_units})
    counts = {}
    for finding in result.get("findings", []):
        counts[finding["severity"]] = counts.get(finding["severity"], 0) + 1
    result["severity_counts"] = counts
    result["status"] = "blocked" if counts.get("high") else "review" if counts else "clean"
    result["change_ledger"] = result.get("changes", [])
    result["schema_version"] = "data-quality/v3"
    return result
