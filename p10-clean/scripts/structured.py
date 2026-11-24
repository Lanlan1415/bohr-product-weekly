"""Typed, schema-validated and provenance-preserving cleaning outputs.

The mechanism follows Frictionless Table Schema's order: declared missing
markers -> logical types -> constraints -> cell-addressed validation errors.
It adds an analysis-ready view; it does not replace the original/display table
or decide scientific conflicts.
"""
from __future__ import annotations

import hashlib
import json
import re

import cleaning as C
import units as U


def _dictionary(spec):
    fields = []
    missing = sorted(C.missing_token_set(spec))
    for col in spec.get("columns") or []:
        if not isinstance(col, dict) or not col.get("name"):
            continue
        semantic = str(col.get("semantic") or "numeric").lower()
        logical = {"numeric": "number", "text": "string", "id": "string",
                   "categorical": "string", "date": "date", "boolean": "boolean",
                   "integer": "integer"}.get(semantic, semantic)
        field = {"name": col["name"], "type": logical,
                 "title": col.get("title") or col["name"],
                 "description": col.get("description") or "declared by the case data dictionary",
                 "semantic": semantic, "missingValues": missing,
                 "target_unit": col.get("target_unit")}
        constraints = {}
        for src, dst in (("required", "required"), ("unique", "unique"),
                         ("allowed_values", "enum"), ("enum", "enum"),
                         ("pattern", "pattern"), ("minimum", "minimum"), ("maximum", "maximum")):
            if src in col:
                constraints[dst] = col[src]
        if "plausible" in col and isinstance(col["plausible"], (list, tuple)) and len(col["plausible"]) == 2:
            constraints["minimum"], constraints["maximum"] = col["plausible"]
        if constraints:
            field["constraints"] = constraints
        fields.append(field)
    return {"@schema": "https://specs.frictionlessdata.io/table-schema/",
            "primaryKey": spec.get("key_columns") or [], "fields": fields}


def _row_id(row, index, spec, source=False):
    columns = []
    if spec.get("row_id_column"):
        columns.append(spec.get("row_id_column"))
    if source and spec.get("source_column"):
        columns.append(spec.get("source_column"))
    for col in columns:
        if isinstance(row, dict) and col in row and row.get(col) not in (None, ""):
            return {"column": col, "value": row.get(col)}
    return {"column": None, "value": "input-row-%04d" % index}


def _typed(v, raw, semantic):
    if v.get("kind") in ("missing", "unparsed", "unit_refused"):
        return None
    kind = v.get("kind")
    if kind == "range":
        factor = 1.0
        try:
            parsed = U.parse_measurement(str(raw))
            unit = parsed.get("unit") or ""
            target = v.get("unit") or unit
            if unit and target and unit != target:
                conv = U.convert(1.0, unit, target)
                if conv.get("ok"):
                    factor = conv["factor"]
        except (TypeError, ValueError):
            factor = 1.0
        return {"low": v["value"], "high": v["value"] if parsed.get("low") == parsed.get("high") else parsed["high"] * factor,
                "unit": v.get("unit"), "kind": "range"}
    if kind == "plus_minus":
        parsed = U.parse_measurement(str(raw))
        factor = 1.0
        unit, target = parsed.get("unit") or "", v.get("unit") or ""
        if unit and target and unit != target:
            conv = U.convert(1.0, unit, target)
            if conv.get("ok"):
                factor = conv["factor"]
        return {"value": v["value"], "error": parsed["error"] * factor,
                "unit": target, "kind": "plus_minus"}
    if semantic == "boolean":
        text = str(raw).strip().lower()
        if text in ("true", "yes", "1", "是"):
            return True
        if text in ("false", "no", "0", "否"):
            return False
        return None
    if semantic == "integer":
        try:
            number = float(v.get("value"))
            return int(number) if number.is_integer() else None
        except (TypeError, ValueError):
            return None
    return v.get("value")


def _measurement(v, raw, col, typed):
    return {"kind": v.get("kind"), "original": raw, "value": v.get("value"),
            "unit": v.get("unit"), "converted": v.get("converted"),
            "typed": typed, "missing": v.get("kind") == "missing",
            "refusal": v.get("refusal")}


def _constraint_errors(fields, rows, runs, spec):
    errors = []
    run_by_col = {r["column"]: r for r in runs}
    for field in fields:
        name, cons = field["name"], field.get("constraints") or {}
        run = run_by_col.get(name)
        if not run:
            continue
        values = {v["row"]: v for v in run["values"]}
        seen = {}
        try:
            pattern = re.compile(cons["pattern"]) if "pattern" in cons else None
        except (re.error, TypeError) as exc:
            errors.append({"row": None, "field": name, "code": "invalid-schema-pattern",
                           "message": "declared pattern cannot compile: %s" % str(exc)[:120]})
            continue
        for i, row in enumerate(rows):
            if not isinstance(row, dict):
                continue
            raw = row.get(name)
            v = values.get(i, {})
            missing = v.get("kind") == "missing" or raw is None or (name not in row)
            if cons.get("required") is True and missing:
                errors.append({"row": i, "field": name, "code": "required-cell-missing",
                               "message": "required field is missing"})
                continue
            if missing:
                continue
            text = "" if raw is None else str(raw)
            if "enum" in cons:
                allowed = cons["enum"]
                if isinstance(allowed, list) and text not in [str(a) for a in allowed]:
                    errors.append({"row": i, "field": name, "code": "constraint-enum",
                                   "message": "value outside declared allowed set", "original": raw})
            if pattern is not None and not pattern.search(text):
                errors.append({"row": i, "field": name, "code": "constraint-pattern",
                               "message": "value does not match declared pattern", "original": raw})
            value = v.get("value")
            for key, code, op in (("minimum", "constraint-minimum", lambda a,b: a < b),
                                  ("maximum", "constraint-maximum", lambda a,b: a > b)):
                if key in cons and isinstance(value, (int, float)):
                    try:
                        bound = float(cons[key])
                        if op(value, bound):
                            errors.append({"row": i, "field": name, "code": code,
                                           "message": "numeric value violates declared %s=%s" % (key, cons[key]),
                                           "value": value, "bound": bound})
                    except (TypeError, ValueError):
                        errors.append({"row": None, "field": name, "code": "invalid-schema-bound",
                                       "message": "%s is not numeric" % key})
            if cons.get("unique") is True:
                if text in seen:
                    errors.append({"row": i, "field": name, "code": "constraint-unique",
                                   "message": "non-unique value also occurs on row %s" % seen[text],
                                   "original": raw})
                else:
                    seen[text] = i
    return errors


def enrich(result, rows, spec):
    """Add types, data dictionary, a validation report and evidence manifests."""
    mapped, _aliases = C.apply_field_aliases(rows, spec)
    runs = []
    for col in spec.get("columns") or []:
        if not isinstance(col, dict) or not col.get("name"):
            continue
        plausible = col.get("plausible")
        if not (isinstance(plausible, (list, tuple)) and len(plausible) == 2 and
                all(isinstance(v, (int, float)) for v in plausible)):
            plausible = None
        runs.append(C.standardise_column(mapped, col["name"], col.get("target_unit"),
                                        plausible, col.get("semantic"), spec))
    positions = [i for i, row in enumerate(mapped) if isinstance(row, dict)]
    analysis = [dict(mapped[i]) for i in positions]
    measurements = []
    fields = _dictionary(spec)["fields"]
    for field in fields:
        name = field["name"]
        run = next((r for r in runs if r["column"] == name), None)
        if run is None:
            continue
        value_map = {v["row"]: v for v in run["values"]}
        for out_i, input_i in enumerate(positions):
            raw = mapped[input_i].get(name)
            v = value_map.get(input_i, {"kind": "missing", "value": None})
            semantic = str(field.get("semantic") or "numeric").lower()
            typed = _typed(v, raw, semantic)
            analysis[out_i][name] = typed
            if v.get("kind") not in ("text", "category", "date"):
                measurements.append({"input_row_index": input_i, "field": name,
                                     "record_id": _row_id(mapped[input_i], input_i, spec),
                                     "source": _row_id(mapped[input_i], input_i, spec, source=True) if spec.get("source_column") else None,
                                     **_measurement(v, raw, name, typed)})
    errors = _constraint_errors(fields, mapped, runs, spec)
    aliases = spec.get("field_aliases") if isinstance(spec.get("field_aliases"), dict) else {}
    for src, dst in sorted(aliases.items()):
        if not isinstance(src, str) or not isinstance(dst, str):
            continue
        for i, row in enumerate(rows):
            if isinstance(row, dict) and src in row and dst in row and str(row[src]) != str(row[dst]):
                errors.append({"row": i, "field": dst, "code": "field-alias-conflict",
                               "message": "source and canonical columns coexist with different values; neither is silently overwritten",
                               "original": {src: row[src], dst: row[dst]}})
    result["data_dictionary"] = {"fields": fields, "missing_value_policy": "declared tokens become null before type conversion; never zero"}
    result["analysis_table"] = analysis
    result["measurements"] = measurements
    result["schema_validation"] = {
        "valid": not errors, "errors": errors,
        "error_counts": {code: sum(1 for e in errors if e["code"] == code)
                         for code in sorted({e["code"] for e in errors})},
        "mechanism": "missing markers -> logical types -> declared required/unique/enum/pattern/min/max constraints",
        "reference_model": "Frictionless Table Schema-compatible field and cell-addressed error model"}
    result["conversion_ledger"] = []
    for change in result.get("changes") or []:
        i = change.get("row")
        source_record = mapped[i] if isinstance(i, int) and 0 <= i < len(mapped) and isinstance(mapped[i], dict) else {}
        entry = dict(change)
        entry["change_id"] = "%s:row=%s:column=%s:seq=%04d" % (
            change.get("rule"), i, change.get("column"), len(result["conversion_ledger"]))
        entry["input_row_index"] = i
        entry["record_id"] = _row_id(source_record, i if isinstance(i, int) else -1, spec)
        entry["source_record"] = _row_id(source_record, i if isinstance(i, int) else -1, spec, source=True) if spec.get("source_column") else None
        if change.get("rule") == "R04":
            entry["transformation"] = {"kind": "unit_conversion", "formula": change.get("why"),
                                       "before": change.get("original"), "after": change.get("new")}
        else:
            entry["transformation"] = {"kind": {"R01": "text_normalisation", "R02": "missing_marker_to_null",
                                                  "R03": "unparsed_gap", "R05": "range_diagnostic",
                                                  "R08": "date_normalisation", "R10": "field_alias",
                                                  "R12": "unit_provenance_refusal"}.get(change.get("rule"), "diagnostic"),
                                       "formula": change.get("why"), "before": change.get("original"),
                                       "after": change.get("new")}
        result["conversion_ledger"].append(entry)
    missing_before = 0
    tokens = C.missing_token_set(spec)
    for field in fields:
        for row in mapped:
            if isinstance(row, dict) and C.is_missing_token(str(row.get(field["name"], "")), tokens):
                missing_before += 1
    result["before_after"] = {
        "input_records": len(rows), "mapped_valid_records": len(positions),
        "declared_missing_cells_before": missing_before,
        "typed_null_cells_after": sum(m.get("missing") for m in measurements),
        "rewritten_cells": sum(c.get("new") is not None and c.get("rule") in C.VALUE_RULES for c in result.get("changes") or []),
        "unit_conversions": sum(c.get("rule") == "R04" and c.get("new") is not None for c in result.get("changes") or []),
        "schema_errors": len(errors), "records_dropped": 0,
        "duplicate_policy": "report and recommend only; no repeated experiment or exact record is silently deleted"}
    recommendations = []
    for kind, entries in (("exact_duplicate_record", result.get("duplicates", {}).get("rule_duplicate_records") or []),
                          ("repeated_experiment", result.get("duplicates", {}).get("rule_duplicate_experiments") or [])):
        for e in entries:
            recommendations.append({"kind": kind, "rows": e.get("rows"), "key": e.get("key"),
                                    "sources": e.get("sources"),
                                    "action": "human review before any deletion/merge",
                                    "merged": False})
    result["dedupe_recommendations"] = recommendations
    result["input_manifest"] = {
        "sha256": hashlib.sha256(json.dumps(rows, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest(),
        "row_count": len(rows),
        "record_ids": [{"input_row_index": i, "record_id": _row_id(row, i, spec),
                        "source": _row_id(row, i, spec, source=True) if spec.get("source_column") else None}
                       for i, row in enumerate(rows)]}
    invariants = {"original_cells_kept_in_changes": all("original" in c for c in result.get("changes") or []),
                  "cleaned_cells_match_ledger": True,
                  "duplicates_not_silently_removed": len(result.get("cleaned_table") or []) == len(positions)}
    cleaned = result.get("cleaned_table") or []
    for c in result.get("changes") or []:
        i, col, new = c.get("row"), c.get("column"), c.get("new")
        if c.get("rule") in C.VALUE_RULES and new is not None:
            if not isinstance(i, int) or i >= len(cleaned) or cleaned[i].get(col) != new:
                invariants["cleaned_cells_match_ledger"] = False
    result["integrity_checks"] = invariants
    if errors:
        result.setdefault("findings", []).append({
            "rule": "clean.schema_constraints", "severity": "medium",
            "message": "declared schema constraints require review; typed invalid cells were not silently repaired",
            "count": len(errors), "codes": sorted({e["code"] for e in errors})})
        counts = result.setdefault("severity_counts", {})
        counts["medium"] = counts.get("medium", 0) + 1
        if result.get("status") == "clean":
            result["status"] = "review"
    return result


def write_analysis_csv(result, path):
    import csv
    fields = []
    for row in result.get("analysis_table") or []:
        for key in row:
            if key not in fields:
                fields.append(key)
    if not fields:
        return
    with open(path, "w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        for row in result["analysis_table"]:
            writer.writerow({k: (json.dumps(v, ensure_ascii=False, sort_keys=True)
                                 if isinstance(v, (dict, list)) else v) for k, v in row.items()})
