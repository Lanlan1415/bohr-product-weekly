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
    Rule("R00", 0, "skip a row that is not a record object, and name it"),
    Rule("R10", 5, "map an aliased source column to its canonical column name"),
    Rule("R01", 10, "strip surrounding whitespace from every cell"),
    Rule("R02", 20, "treat the not-reported tokens as a missing value, never as 0"),
    Rule("R03", 30, "parse a value into number / error / unit / range structure"),
    Rule("R04", 40, "convert a unit to the column's target unit, recording the factor"),
    Rule("R05", 50, "flag a value outside the declared plausible range"),
    Rule("R06", 60, "normalise the entity key for duplicate detection"),
    Rule("R11", 65, "resolve declared synonyms for entity keys; originals stay untouched"),
    Rule("R07", 70, "mark duplicate records separately from duplicate experiments"),
    Rule("R08", 80, "normalise dates to ISO 8601; never invent numeric precision"),
    Rule("R09", 90, "a hand-supplied quality report must agree with the computed one"),
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
        written = None  # the full rewritten cell text, when the rewrite is structured
        if target_unit and unit and unit != target_unit:
            if parsed["kind"] == "range":
                # A range must stay a range: converting only the low endpoint and
                # writing it back would silently replace an interval with a point.
                lo_c = U.convert(float(parsed["low"]), unit, target_unit)
                hi_c = U.convert(float(parsed["high"]), unit, target_unit)
                refused = lo_c if not lo_c.get("ok") else (hi_c if not hi_c.get("ok") else None)
                if refused is not None:
                    changes.append({"rule": "R04", "priority": 40, "row": i, "column": column,
                                    "original": cell, "new": None,
                                    "why": f"unit conversion refused: {refused['reason']}"})
                    values.append({"row": i, "kind": "unit_refused", "value": None,
                                   "original": cell, "converted": None,
                                   "refusal": refused.get("kind")})
                    continue
                converted = lo_c["value"]
                written = f"{lo_c['value']:g}-{hi_c['value']:g} {target_unit}"
                changes.append({"rule": "R04", "priority": 40, "row": i, "column": column,
                                "original": cell, "new": written,
                                "why": f"range endpoints converted: {lo_c['formula']}; "
                                       f"{hi_c['formula']}"})
            elif parsed["kind"] == "plus_minus":
                # The error bar shares the value's unit, so it converts with the
                # same factor; keeping it turns "12±0.5 mV" into a bare number.
                v_c = U.convert(float(parsed["value"]), unit, target_unit)
                e_c = U.convert(float(parsed["error"]), unit, target_unit)
                refused = v_c if not v_c.get("ok") else (e_c if not e_c.get("ok") else None)
                if refused is not None:
                    changes.append({"rule": "R04", "priority": 40, "row": i, "column": column,
                                    "original": cell, "new": None,
                                    "why": f"unit conversion refused: {refused['reason']}"})
                    values.append({"row": i, "kind": "unit_refused", "value": None,
                                   "original": cell, "converted": None,
                                   "refusal": refused.get("kind")})
                    continue
                converted = v_c["value"]
                written = f"{v_c['value']:g}\u00b1{e_c['value']:g} {target_unit}"
                changes.append({"rule": "R04", "priority": 40, "row": i, "column": column,
                                "original": cell, "new": written,
                                "why": f"value and error converted: {v_c['formula']}; "
                                       f"{e_c['formula']}"})
            else:
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
                written = f"{conv['value']:g} {target_unit}"
                changes.append({"rule": "R04", "priority": 40, "row": i, "column": column,
                                "original": cell, "new": written,
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
        entry = {"row": i, "kind": parsed["kind"], "value": eff,
                 "unit": target_unit or unit, "original": cell,
                 "converted": converted}
        if written is not None:
            entry["written"] = written
        values.append(entry)

    return {"column": column, "target_unit": target_unit, "values": values,
            "changes": changes}


def find_duplicates(rows: list[dict], key_columns: list[str],
                    value_columns: list[str] | None = None,
                    synonyms: dict | None = None,
                    source_column: str | None = None) -> dict:
    """Split exact duplicates from same-entity records with different values.

    A duplicate *record* is the same key with identical values: a copy-paste.

    A duplicate *experiment* is the same key with different values. Those are not
    merged, because two runs of the same material are two measurements, and
    averaging them silently would hide the disagreement.

    `synonyms` (from spec.synonyms) is a declared, reviewable merge key: entity
    spellings that resolve to the same canonical name group together, and the
    original cells stay untouched. Spellings outside the table are listed as
    synonym_unmapped — merging across them is a human decision, not a guess.
    """
    synonyms = synonyms or {}
    source_column = str(source_column or "").strip()
    if not key_columns:
        # Without declared keys every row would collapse into one "" bucket and a
        # fully distinct table would report as duplicate experiments. No keys, no
        # census: report why, instead of a spurious medium finding.
        return {"rule_duplicate_records": [], "rule_duplicate_experiments": [],
                "duplicate_records": 0, "duplicate_experiments": 0,
                "synonym_unmapped": [],
                "note": ("no key_columns declared, so the duplicate census was skipped — "
                         "declare the fields that identify an entity to enable it")}
    canon_keys = {norm_key(v) for v in synonyms.values()}
    unmapped: set = set()
    for row in rows:
        if not isinstance(row, dict):
            continue
        for c in key_columns:
            val = str(row.get(c, "") or "").strip()
            if not val:
                continue
            nv = norm_key(val)
            if synonyms and nv not in synonyms and nv not in canon_keys:
                unmapped.add(val)

    def _src(i: int):
        if not source_column or not isinstance(rows[i], dict):
            return None
        sv = rows[i].get(source_column)
        return None if sv in (None, "") else str(sv)

    buckets: dict[str, list[int]] = {}
    for i, row in enumerate(rows):
        if not isinstance(row, dict):
            continue  # a non-record row has no key; the bucket check cannot judge it
        key = "|".join(resolve_key(str(row.get(c, "") or ""), synonyms)
                       for c in key_columns)
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
                entry = {"key": key, "rows": group, "value_set": list(sig)}
                sources = [s for s in (_src(i) for i in group) if s]
                if sources:
                    entry["sources"] = sources
                exact.append(entry)
        if len(subgroups) > 1:
            entry = {"key": key, "rows": idxs,
                     "distinct_value_sets": len(subgroups),
                     "groups": [subgroups[k] for k in subgroups]}
            sources = [s for s in (_src(i) for i in idxs) if s]
            if sources:
                entry["sources"] = sources
            distinct.append(entry)

    return {
        "rule_duplicate_records": exact,
        "rule_duplicate_experiments": distinct,
        "duplicate_records": len(exact),
        "duplicate_experiments": len(distinct),
        "synonym_unmapped": sorted(unmapped),
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


def apply_field_aliases(rows: list, spec: dict) -> tuple[list, list]:
    """R10: rename aliased source columns to their canonical names.

    Returns (mapped_rows, alias_changes). The mapping comes from spec.field_aliases
    ({source_name: canonical_name}); a source column is renamed only when the
    canonical name is not already taken by that row, and every rename is recorded
    so the mapping is auditable. Original values never move between columns.
    """
    aliases = spec.get("field_aliases")
    mapped: dict = {}
    if isinstance(aliases, dict):
        for src, dst in aliases.items():
            if (isinstance(src, str) and isinstance(dst, str)
                    and src.strip() and dst.strip()):
                mapped[src.strip()] = dst.strip()
    if not mapped:
        return rows, []
    new_rows, changes = [], []
    for i, row in enumerate(rows):
        if not isinstance(row, dict):
            new_rows.append(row)
            continue
        r = dict(row)
        for src, dst in mapped.items():
            if src in r and dst not in r:
                r[dst] = r.pop(src)
                changes.append({"rule": "R10", "priority": 5, "row": i, "column": dst,
                                "original": "column '" + src + "'",
                                "new": "column '" + dst + "'",
                                "why": "field alias declared in the spec "
                                       "(source column renamed, value untouched)"})
        new_rows.append(r)
    return new_rows, changes


def unmapped_columns(rows: list, spec: dict) -> list[str]:
    """Columns present in the rows that the schema neither declares nor maps.

    The rubric asks for an explicit unmapped-fields list: a column nobody declared
    has no known semantics, so it is named instead of being quietly carried along.
    Declared columns, key columns and the provenance source column are mapped by
    definition; everything else is listed.
    """
    declared = {str(c.get("name")).strip()
                for c in (spec.get("columns") or []) if isinstance(c, dict) and c.get("name")}
    keys = {str(k).strip() for k in (spec.get("key_columns") or [])}
    src = str(spec.get("source_column") or "").strip()
    present = set()
    for row in rows:
        if isinstance(row, dict):
            present |= {str(k) for k in row}
    return sorted(present - declared - keys - ({src} if src else set()))


def unreported_fields(rows: list, spec: dict) -> list[str]:
    """Fields the schema declares that no row actually carries."""
    declared = [c.get("name") for c in (spec.get("columns") or [])
                if isinstance(c, dict) and c.get("name")]
    present = set()
    for row in rows:
        if isinstance(row, dict):
            present |= {k for k, v in row.items() if str(v).strip()}
    return [c for c in declared if c not in present]


def synonym_table(spec: dict) -> dict:
    """The declared entity synonym table: normalised alias -> canonical name.

    An empty or malformed table is treated as absent, so declaring nothing never
    turns every key spelling into an unmapped value.
    """
    raw = spec.get("synonyms")
    table: dict = {}
    if isinstance(raw, dict):
        for alias, canon in raw.items():
            if (isinstance(alias, str) and isinstance(canon, str)
                    and alias.strip() and canon.strip()):
                table[norm_key(alias)] = canon.strip()
    return table


def resolve_key(value: str, table: dict) -> str:
    """Grouping key of one entity value: canonicalised through the synonym table.

    The original cell is never rewritten — only the key the duplicate census
    groups by changes, and the mapping is visible in the synonym table itself.
    """
    nv = norm_key(value)
    canon = table.get(nv)
    return norm_key(canon) if canon else nv


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


def pending_review(column_runs: list[dict], dupes: dict, changes: list[dict],
                   limit: int = 500) -> list[dict]:
    """The to-confirm list: every value the engine would not decide by itself.

    This is the deliverable a reviewer reads first — unparsed cells, refused
    conversions, out-of-range values, duplicate experiments and unmapped entity
    spellings all land here with their row and their reason, so nothing rests on
    a silent judgement call.
    """
    items: list[dict] = []
    for run in column_runs:
        for v in run["values"]:
            if v["kind"] == "unparsed":
                items.append({"row": v["row"], "column": run["column"], "what": "unparsed",
                              "original": v.get("original"),
                              "why": "could not be parsed; kept as a named gap"})
            elif v["kind"] == "unit_refused":
                items.append({"row": v["row"], "column": run["column"], "what": "unit_refused",
                              "original": v.get("original"),
                              "why": "unit unknown or incompatible; conversion refused by name"})
    for c in changes:
        if c.get("rule") == "R05":
            items.append({"row": c.get("row"), "column": c.get("column"),
                          "what": "out_of_range", "original": c.get("original"),
                          "why": "outside the declared plausible range; keep, drop or cap "
                                 "is a human decision"})
    for de in dupes.get("rule_duplicate_experiments") or []:
        item = {"rows": de.get("rows"), "key": de.get("key"), "what": "duplicate_experiment",
                "why": "same entity with different values; merging needs a stated rule"}
        if de.get("sources"):
            item["sources"] = de["sources"]
        items.append(item)
    for s in dupes.get("synonym_unmapped") or []:
        items.append({"value": s, "what": "synonym_unmapped",
                      "why": "entity spelling outside the declared synonym table; "
                             "merging across it needs human confirmation"})
    total = len(items)
    if total > limit:
        items = items[:limit]
        items.append({"what": "truncated", "why": f"the to-confirm list was capped at {limit} "
                                                  f"of {total} entries"})
    return items


def clean(rows: list[dict], spec: dict) -> dict:
    """Full pass: map fields, standardise every column, find duplicates, report."""
    source_column = str(spec.get("source_column") or "").strip()
    mapped_rows, alias_changes = apply_field_aliases(rows, spec)

    column_runs = []
    for col in spec.get("columns") or []:
        if not isinstance(col, dict) or not str(col.get("name") or "").strip():
            continue  # a column entry that is not an object cannot name a column
        plausible = col.get("plausible")
        if not (isinstance(plausible, (list, tuple)) and len(plausible) == 2
                and all(isinstance(v, (int, float)) for v in plausible)):
            plausible = None  # a malformed range is no range
        run = standardise_column(mapped_rows, col["name"], col.get("target_unit"),
                                 plausible, col.get("semantic"), spec)
        run["semantic"] = col.get("semantic")
        column_runs.append(run)

    synonyms = synonym_table(spec)
    dupes = find_duplicates(mapped_rows, spec.get("key_columns") or [],
                            spec.get("value_columns") or [],
                            synonyms=synonyms, source_column=source_column)
    anomalies = anomaly_report(mapped_rows, spec)
    report = quality_report(mapped_rows, spec, column_runs, dupes)

    changes = alias_changes + [c for run in column_runs for c in run["changes"]]
    if source_column:
        # Provenance: every change and duplicate entry carries the declared source
        # value of its row, so an edit can be traced past the row index to the
        # record's origin.
        for c in changes:
            i = c.get("row")
            if isinstance(i, int) and 0 <= i < len(mapped_rows) and isinstance(mapped_rows[i], dict):
                sv = mapped_rows[i].get(source_column)
                if sv not in (None, ""):
                    c["source"] = str(sv)
    by_rule: dict[str, int] = {}
    for c in changes:
        by_rule[c["rule"]] = by_rule.get(c["rule"], 0) + 1

    # Idempotence check: the rules must not keep finding work after one pass.
    cleaned_rows = [dict(r) for r in mapped_rows if isinstance(r, dict)]
    for run in column_runs:
        # A cell is rewritten only when a rule rewrote it. Re-serialising every
        # value would turn "3.20 eV" into "3.2 eV" with no change record, which is
        # a silent edit of the source data.
        # A refusal (new: None) is a resting state, not a rewrite: only cells that
        # actually changed count toward idempotence.
        # The cleaned cell is exactly what the ledger's "new" holds: the rewrite
        # and the record cannot disagree, and a trimmed "3.20 eV" keeps its
        # reported precision instead of being re-serialised as "3.2 eV".
        for c in run["changes"]:
            if c["rule"] in VALUE_RULES and c.get("new") is not None:
                i = c["row"]
                if isinstance(i, int) and 0 <= i < len(cleaned_rows) \
                        and isinstance(cleaned_rows[i], dict):
                    cleaned_rows[i][c["column"]] = c["new"]
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
    unmapped = unmapped_columns(mapped_rows, spec)
    if unmapped:
        findings.append({"rule": "clean.unmapped_columns", "severity": "low",
                         "message": "columns present in the rows but neither declared in the "
                                    "schema nor aliased — their semantics are unrecorded",
                         "columns": unmapped})
    absent = unreported_fields(mapped_rows, spec)
    if absent:
        findings.append({"rule": "clean.declared_fields_absent", "severity": "low",
                         "message": "schema fields no row carries — declared but never supplied",
                         "columns": absent})
    if dupes.get("synonym_unmapped"):
        findings.append({"rule": "clean.synonym_unmapped", "severity": "low",
                         "message": "entity spellings outside the declared synonym table; "
                                    "merging across them needs human confirmation",
                         "values": dupes["synonym_unmapped"][:50]})
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
        "pending_review": pending_review(column_runs, dupes, changes),
        "unmapped_columns": unmapped,
        "declared_fields_absent": absent,
        "provenance": ({"source_column": source_column,
                        "sources": sorted({str(c["source"]) for c in changes if "source" in c}
                                          | {s for de in dupes.get("rule_duplicate_experiments")
                                             or [] for s in de.get("sources", [])})}
                       if source_column else None),
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
