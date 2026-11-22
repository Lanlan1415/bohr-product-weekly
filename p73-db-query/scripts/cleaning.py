"""Rule-driven cleaning and standardisation of aggregate research data tables.

The design constraint is that every change must be explainable after the fact. So
this module never mutates a value silently:

  - every rule has an id, a priority, and a stated applicability
  - every change records rule id, row, column, original, new, and why
  - the original value is preserved in the record, even when it is wrong
  - running the same rules twice produces no further changes (idempotent)

That last property is what makes a cleaning pass reviewable: if a second run keeps
finding things to change, the rules disagree with each other, and the priority
order is wrong.

Two distinctions the module refuses to collapse:

  duplicate record   vs  duplicate experiment   (same numbers, different sample)
  missing            vs  zero                   (not reported is not 0)

Both are reported separately, because in a meta-analysis the difference changes the
conclusion.
"""

from __future__ import annotations

import hashlib
import json
import re

from dataclasses import dataclass, field

import units as U


@dataclass
class Rule:
    id: str
    priority: int
    description: str
    applies_when: str = "always"


# The rule library. Priorities run low to high; a later rule may override an
# earlier one, and the record shows both, so the override is visible.
RULES = [
    Rule("R01", 10, "strip surrounding whitespace from every cell"),
    Rule("R02", 20, "treat the not-reported tokens as a missing value, never as 0"),
    Rule("R03", 30, "parse a value into number / error / unit / range structure"),
    Rule("R04", 40, "convert a unit to the column's target unit, recording the factor"),
    Rule("R05", 50, "flag a value outside the declared plausible range"),
    Rule("R06", 60, "normalise the entity key for duplicate detection"),
    Rule("R07", 70, "mark duplicate records separately from duplicate experiments"),
    Rule("R08", 80, "normalise dates to ISO 8601; never invent numeric precision"),
]


DEFAULT_MISSING_TOKENS = (
    "", "nd", "n.d.", "n/a", "na", "none", "not reported", "not detected",
    "未检出", "未检测", "低于检出限", "<lod", "-999",
)


def missing_token_set(spec: dict) -> set:
    """The not-reported token set: the built-ins plus the case's own additions.

    "-999" is the sentinel the organising brief names; a case may declare more via
    spec.missing_tokens (merged, never replaced).
    """
    toks = set(DEFAULT_MISSING_TOKENS)
    extra = spec.get("missing_tokens") or []
    if isinstance(extra, (list, tuple)):
        toks |= {str(x).strip().lower() for x in extra if str(x).strip()}
    return toks


def is_missing_token(cell: str, tokens: set) -> bool:
    return str(cell or "").strip().lower() in tokens


DATE_FORMATS = (
    ("%Y-%m-%d", "iso"),
    ("%Y/%m/%d", "slash"),
    ("%d.%m.%Y", "dot"),
    ("%Y年%m月%d日", "cjk"),
    ("%Y-%m", "iso-month"),
    ("%Y/%m", "slash-month"),
)


def norm_date(cell: str) -> dict:
    """Normalise one date cell to ISO 8601, or report why it cannot be."""
    import datetime as _dt
    s = str(cell or "").strip()
    if not s:
        return {"ok": False, "reason": "empty"}
    for fmt, name in DATE_FORMATS:
        try:
            d = _dt.datetime.strptime(s, fmt)
        except ValueError:
            continue
        if fmt.endswith("month"):
            return {"ok": True, "iso": d.strftime("%Y-%m"), "source_format": name,
                    "granularity": "month"}
        return {"ok": True, "iso": d.strftime("%Y-%m-%d"), "source_format": name,
                "granularity": "day"}
    return {"ok": False, "reason": "unrecognised date format: " + s[:30]}


def norm_key(text: str) -> str:
    """Normalise an entity key for duplicate detection.

    Case, spacing, hyphenation and Greek/Latin look-alikes are folded; chemical
    formula digits are kept, because CO2 and CO are different substances and
    merging them is far worse than missing a duplicate.
    """
    t = str(text or "").strip().lower()
    t = t.replace("\u2010", "-").replace("\u2011", "-").replace("\u2013", "-")
    t = re.sub(r"[\s_]+", "", t)
    t = t.replace("\u00b5", "u").replace("\u03bc", "u")
    t = t.replace("\u03b1", "alpha").replace("\u03b2", "beta").replace("\u03b3", "gamma")
    return t


def standardise_column(rows: list[dict], column: str, target_unit: str | None,
                       plausible: tuple[float, float] | None = None,
                       semantic: str | None = None, spec_ref: dict | None = None) -> dict:
    """Apply R01-R05 (or R08 for date columns) to one column.

    `semantic` comes from the data dictionary: "date" switches the column to R08
    date normalisation, "categorical" to a whitespace census, "text"/"id" skip
    measurement parsing entirely.
    """
    changes: list[dict] = []
    values: list[dict] = []
    semantic = (semantic or "").strip().lower()
    tokens = missing_token_set(spec_ref or {})
    for i, row in enumerate(rows):
        if not isinstance(row, dict):
            # A row that is not an object is malformed input: it is skipped and named,
            # never a crash.
            changes.append({"rule": "R00", "priority": 0, "row": i, "column": column,
                            "original": str(row)[:60], "new": None,
                            "why": "row is not a record; skipped"})
            continue
        raw = row.get(column, "")
        cell = str(raw).strip()
        if is_missing_token(cell, tokens):
            # A sentinel for "not measured" ("-999", "ND", "未检出", blank, ...) is a
            # missing value under every semantic — counting it as data would invent
            # observations, and counting it as a parse failure hides the difference
            # between "not measured" and "could not read".
            changes.append({"rule": "R02", "priority": 20, "row": i, "column": column,
                            "original": cell, "new": None,
                            "why": "not-reported token carries no measurement"})
            values.append({"row": i, "kind": "missing", "value": None,
                           "original": cell, "converted": None})
            continue
        if cell != str(raw):
            changes.append({"rule": "R01", "priority": 10, "row": i, "column": column,
                            "original": str(raw), "new": cell, "why": "whitespace trimmed"})

        if semantic == "date":
            nd = norm_date(cell)
            if nd.get("ok"):
                iso = nd["iso"]
                if iso != cell:
                    changes.append({"rule": "R08", "priority": 80, "row": i, "column": column,
                                    "original": cell, "new": iso,
                                    "why": "date normalised from " + nd["source_format"]
                                           + " format to ISO 8601"})
                values.append({"row": i, "kind": "date", "value": iso, "original": cell,
                               "converted": None, "granularity": nd.get("granularity")})
            else:
                changes.append({"rule": "R08", "priority": 80, "row": i, "column": column,
                                "original": cell, "new": None,
                                "why": "date could not be normalised: " + nd["reason"]})
                values.append({"row": i, "kind": "unparsed", "value": None,
                               "original": cell, "converted": None})
            continue

        if semantic == "categorical":
            cat = " ".join(cell.split())
            if cat != cell:
                changes.append({"rule": "R01", "priority": 10, "row": i, "column": column,
                                "original": cell, "new": cat,
                                "why": "category whitespace collapsed"})
            values.append({"row": i, "kind": "category", "value": cat, "original": cell,
                           "converted": None})
            continue

        if semantic in ("text", "id"):
            values.append({"row": i, "kind": "text", "value": cell, "original": cell,
                           "converted": None})
            continue

        parsed = U.parse_measurement(cell)
        if parsed["kind"] == "not_reported":
            changes.append({"rule": "R02", "priority": 20, "row": i, "column": column,
                            "original": cell, "new": None,
                            "why": "not reported is a missing value, not zero"})
            values.append({"row": i, "kind": "missing", "value": None,
                           "original": cell, "converted": None})
            continue

        if parsed["kind"] == "unparsed":
            changes.append({"rule": "R03", "priority": 30, "row": i, "column": column,
                            "original": cell, "new": None,
                            "why": "could not be parsed as a measurement; left as a named gap"})
            values.append({"row": i, "kind": "unparsed", "value": None,
                           "original": cell, "converted": None})
            continue

        unit = parsed.get("unit") or ""
        num = parsed.get("value", parsed.get("low"))
        converted = None
        if target_unit and unit and unit != target_unit:
            conv = U.convert(num, unit, target_unit)
            if not conv.get("ok"):
                changes.append({"rule": "R04", "priority": 40, "row": i, "column": column,
                                "original": cell, "new": None,
                                "why": f"unit conversion refused: {conv['reason']}"})
                values.append({"row": i, "kind": "unit_refused", "value": None,
                               "original": cell, "converted": None,
                               "refusal": conv.get("kind")})
                continue
            converted = conv["value"]
            changes.append({"rule": "R04", "priority": 40, "row": i, "column": column,
                            "original": cell,
                            "new": f"{conv['value']:g} {target_unit}",
                            "why": conv["formula"]})

        eff = converted if converted is not None else num
        if plausible and eff is not None:
            try:
                lo, hi = plausible
            except (TypeError, ValueError):
                lo = hi = None
            if lo is None or hi is None:
                lo = hi = None
            if lo is not None and isinstance(lo, (int, float))                     and isinstance(hi, (int, float))                     and isinstance(eff, (int, float)) and not (lo <= eff <= hi):
                changes.append({"rule": "R05", "priority": 50, "row": i, "column": column,
                                "original": cell, "new": eff,
                                "why": f"outside the plausible range [{lo:g}, {hi:g}]"})
        values.append({"row": i, "kind": parsed["kind"], "value": eff,
                       "unit": target_unit or unit, "original": cell,
                       "converted": converted})

    return {"column": column, "target_unit": target_unit, "values": values,
            "changes": changes}


def find_duplicates(rows: list[dict], key_columns: list[str],
                    value_columns: list[str] | None = None) -> dict:
    """Split exact duplicates from same-entity records with different values.

    A duplicate *record* is the same key with identical values: a copy-paste.

    A duplicate *experiment* is the same key with different values. Those are not
    merged, because two runs of the same material are two measurements, and
    averaging them silently would hide the disagreement.
    """
    if not key_columns:
        # Without declared keys every row would collapse into one "" bucket and a
        # fully distinct table would report as duplicate experiments. No keys, no
        # census: report why, instead of a spurious medium finding.
        return {"rule_duplicate_records": [], "rule_duplicate_experiments": [],
                "duplicate_records": 0, "duplicate_experiments": 0,
                "note": ("no key_columns declared, so the duplicate census was skipped — "
                         "declare the fields that identify an entity to enable it")}
    buckets: dict[str, list[int]] = {}
    for i, row in enumerate(rows):
        if not isinstance(row, dict):
            continue  # a non-record row has no key; the bucket check cannot judge it
        key = "|".join(norm_key(row.get(c, "")) for c in key_columns)
        buckets.setdefault(key, []).append(i)

    exact, distinct = [], []
    for key, idxs in buckets.items():
        if len(idxs) < 2:
            continue
        # Group the bucket by value tuple first. A bucket can hold both an exact
        # pair and a differing run of the same entity; collapsing the whole bucket
        # to one label loses the exact pair, which is the actionable one.
        if not value_columns:
            # Undeclared value columns default to every non-key column: comparing
            # full values is what "same record" means, and an empty signature would
            # collapse a genuinely differing run into one exact duplicate.
            value_columns = sorted({c for i in idxs for c in rows[i].keys()
                                    if isinstance(rows[i], dict)}
                                   - {str(k) for k in key_columns})
        subgroups: dict[tuple, list[int]] = {}
        for i in idxs:
            sig = tuple(str(rows[i].get(c, "")).strip() for c in value_columns)
            subgroups.setdefault(sig, []).append(i)
        for sig, group in subgroups.items():
            if len(group) > 1:
                exact.append({"key": key, "rows": group, "value_set": list(sig)})
        if len(subgroups) > 1:
            distinct.append({"key": key, "rows": idxs,
                             "distinct_value_sets": len(subgroups),
                             "groups": [subgroups[k] for k in subgroups]})

    return {
        "rule_duplicate_records": exact,
        "rule_duplicate_experiments": distinct,
        "duplicate_records": len(exact),
        "duplicate_experiments": len(distinct),
        "note": ("duplicate records are safe to drop after review; duplicate experiments are "
                 "separate measurements of the same entity and must not be merged without a "
                 "stated rule"),
    }


def anomaly_report(rows: list[dict], spec: dict) -> dict:
    """Missing, unparsed, refused and out-of-range counts per column."""
    columns = spec.get("columns") or []
    report = {"per_column": {}, "total_rows": len(rows)}
    for col in columns:
        if not isinstance(col, dict):
            continue
        name = col["name"]
        target = col.get("target_unit")
        std = standardise_column(rows, name, target, col.get("plausible"),
                                 col.get("semantic"), spec)
        kinds: dict[str, int] = {}
        for v in std["values"]:
            kinds[v["kind"]] = kinds.get(v["kind"], 0) + 1
        report["per_column"][name] = {
            "target_unit": target,
            "kinds": kinds,
            "missing": kinds.get("missing", 0),
            "unparsed": kinds.get("unparsed", 0),
            "unit_refused": kinds.get("unit_refused", 0),
            "changes": len(std["changes"]),
        }
    report["columns_with_missing"] = [c for c, v in report["per_column"].items() if v["missing"]]
    report["columns_with_unparsed"] = [c for c, v in report["per_column"].items() if v["unparsed"]]
    return report


def unreported_fields(spec: dict) -> list[str]:
    """Fields the schema declares that no row actually carries."""
    declared = [c["name"] for c in (spec.get("columns") or [])]
    rows = spec.get("rows") or []
    present = {k for row in rows for k, v in row.items() if str(v).strip()}
    return [c for c in declared if c not in present]


def quality_report(rows: list[dict], spec: dict, column_runs: list[dict],
                   dupes: dict) -> dict:
    """A structured quality report computed from the table itself.

    Every number is derived from the data, so a hand-written report that disagrees
    with the table is detectable (R09) — the report becomes machine-checkable
    instead of prose.
    """
    per_column = []
    for run in column_runs:
        vals = run["values"]
        n = len(vals)
        missing = sum(1 for v in vals if v["kind"] == "missing")
        unparsed = sum(1 for v in vals if v["kind"] == "unparsed")
        unit_refused = sum(1 for v in vals if v["kind"] == "unit_refused")
        rewritten = sum(1 for c in run["changes"]
                        if c["rule"] in VALUE_RULES and c.get("new") is not None)
        per_column.append({
            "column": run["column"],
            "semantic": run.get("semantic"),
            "target_unit": run.get("target_unit"),
            "cells": n,
            "missing": missing,
            "unparsed": unparsed,
            "unit_refused": unit_refused,
            "rewritten": rewritten,
            "parse_rate": round((n - missing - unparsed) / n, 4) if n else None,
            "completeness": round((n - missing - unparsed) / n, 4) if n else None,
        })
    return {
        "rows": len([r for r in rows if isinstance(r, dict)]),
        "columns": len(per_column),
        "cells": sum(c["cells"] for c in per_column),
        "missing_cells": sum(c["missing"] for c in per_column),
        "unparsed_cells": sum(c["unparsed"] for c in per_column),
        "rewritten_cells": sum(c["rewritten"] for c in per_column),
        "duplicate_records": dupes.get("duplicate_records", 0),
        "duplicate_experiments": dupes.get("duplicate_experiments", 0),
        "per_column": per_column,
    }


def check_report_consistency(report: dict, supplied: dict) -> list[dict]:
    """R09: a hand-supplied quality report must agree with the computed one.

    Only the integer fields a report author would copy by hand are checked;
    narrative claims are out of scope.
    """
    import re as _re
    problems: list[dict] = []
    for key in ("rows", "columns", "cells", "missing_cells", "unparsed_cells",
                "duplicate_records", "duplicate_experiments"):
        if key not in supplied:
            continue
        m = _re.search(r"-?[0-9]+", str(supplied.get(key)))
        if m is None:
            continue
        claimed_n = int(m.group(0))
        if claimed_n != report.get(key):
            problems.append({"rule": "clean.report_inconsistent", "severity": "medium",
                             "field": key, "claimed": claimed_n,
                             "computed": report.get(key),
                             "why": "the supplied quality report disagrees with the table"})
    return problems


def clean(rows: list[dict], spec: dict) -> dict:
    """Full pass: standardise every column, find duplicates, report anomalies."""
    column_runs = []
    for col in spec.get("columns") or []:
        if not isinstance(col, dict) or not str(col.get("name") or "").strip():
            continue  # a column entry that is not an object cannot name a column
        plausible = col.get("plausible")
        if not (isinstance(plausible, (list, tuple)) and len(plausible) == 2
                and all(isinstance(v, (int, float)) for v in plausible)):
            plausible = None  # a malformed range is no range
        run = standardise_column(rows, col["name"], col.get("target_unit"),
                                 plausible, col.get("semantic"), spec)
        run["semantic"] = col.get("semantic")
        column_runs.append(run)

    dupes = find_duplicates(rows, spec.get("key_columns") or [],
                            spec.get("value_columns") or [])
    anomalies = anomaly_report(rows, spec)
    report = quality_report(rows, spec, column_runs, dupes)

    changes = [c for run in column_runs for c in run["changes"]]
    by_rule: dict[str, int] = {}
    for c in changes:
        by_rule[c["rule"]] = by_rule.get(c["rule"], 0) + 1

    # Idempotence check: the rules must not keep finding work after one pass.
    cleaned_rows = [dict(r) for r in rows if isinstance(r, dict)]
    for run in column_runs:
        # A cell is rewritten only when a rule rewrote it. Re-serialising every
        # value would turn "3.20 eV" into "3.2 eV" with no change record, which is
        # a silent edit of the source data.
        # A refusal (new: None) is a resting state, not a rewrite: only cells that
        # actually changed count toward idempotence.
        rewritten = {c["row"] for c in run["changes"]
                     if c["rule"] in VALUE_RULES and c.get("new") is not None}
        for v in run["values"]:
            if v["row"] in rewritten and v["value"] is not None:
                if not isinstance(v["value"], (int, float)):
                    # A text/categorical rewrite lands verbatim; the :g format is
                    # for numbers only.
                    cleaned_rows[v["row"]][run["column"]] = str(v["value"])
                else:
                    cleaned_rows[v["row"]][run["column"]] = (
                        f"{v['value']:g} {v['unit']}".strip()
                        if v.get("unit") else f"{v['value']:g}")
    second = clean_count(cleaned_rows, spec)

    findings = []
    if anomalies["columns_with_missing"]:
        findings.append({"rule": "clean.missing_values", "severity": "medium",
                         "message": "some values are not reported; they are missing, not zero",
                         "columns": anomalies["columns_with_missing"]})
    if anomalies["columns_with_unparsed"]:
        findings.append({"rule": "clean.unparsed_values", "severity": "medium",
                         "message": "some cells could not be parsed and are kept as named gaps",
                         "columns": anomalies["columns_with_unparsed"]})
    if dupes["duplicate_records"]:
        findings.append({"rule": "clean.duplicate_records", "severity": "low",
                         "message": "identical rows found; safe to drop after review",
                         "count": dupes["duplicate_records"]})
    if dupes["duplicate_experiments"]:
        findings.append({"rule": "clean.duplicate_experiments", "severity": "medium",
                         "message": "the same entity appears with different values; these are "
                                    "separate measurements and must not be averaged silently",
                         "count": dupes["duplicate_experiments"]})
    if second > 0:
        findings.append({"rule": "clean.not_idempotent", "severity": "high",
                         "message": "a second pass still changes cells, so the rule priorities "
                                    "disagree with each other", "second_pass_changes": second})
    supplied_report = spec.get("quality_report")
    if isinstance(supplied_report, dict):
        findings.extend(check_report_consistency(report, supplied_report))
    elif supplied_report not in (None, []):
        findings.append({"rule": "clean.report_inconsistent", "severity": "medium",
                         "why": "the supplied quality_report is not an object, so it cannot be "
                                "checked against the table"})

    counts: dict[str, int] = {}
    for f in findings:
        counts[f["severity"]] = counts.get(f["severity"], 0) + 1

    return {
        "schema_version": "clean/v1",
        "status": ("clean" if not findings else "blocked" if counts.get("high") else "review"),
        "findings": findings,
        "severity_counts": counts,
        "rows": len(rows),
        "rules_applied": [{"id": r.id, "priority": r.priority, "description": r.description}
                          for r in RULES],
        "changes_by_rule": by_rule,
        "changes": changes[:2000],
        "duplicates": dupes,
        "anomalies": anomalies,
        "cleaned_table": cleaned_rows,
        "idempotent": second == 0,
        "quality_report": report,
        "original_sha256": hashlib.sha256(
            json.dumps(rows, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()[:16],
    }


# Rules that rewrite a cell. R02/R03/R05 are diagnostics about the data and
# legitimately recur on every pass, so counting them would report a rule conflict
# where there is only an unfixed gap. R08 is a genuine rewrite and idempotent:
# once a date is ISO 8601, the second pass finds nothing to change.
VALUE_RULES = {"R01", "R04", "R08"}


def clean_count(rows: list[dict], spec: dict) -> int:
    """How many cells a further pass would still *rewrite*.

    Idempotence is about value changes, not about diagnostics: a column with three
    unreported values will report them again on every run, and that is correct.
    """
    total = 0
    for col in spec.get("columns") or []:
        if not isinstance(col, dict) or not str(col.get("name") or "").strip():
            continue
        plausible = col.get("plausible")
        if not (isinstance(plausible, (list, tuple)) and len(plausible) == 2
                and all(isinstance(v, (int, float)) for v in plausible)):
            plausible = None
        run = standardise_column(rows, col["name"], col.get("target_unit"), plausible,
                                 col.get("semantic"), spec)
        total += sum(1 for c in run["changes"]
                     if c["rule"] in VALUE_RULES and c.get("new") is not None)
    return total
