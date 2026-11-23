"""Strict stdlib-only table loading for CSV/TSV and read-only SQLite."""
from __future__ import annotations

import csv
import hashlib
import io
import json
import re
import sqlite3
from pathlib import Path


def _decode(raw: bytes, declared=None):
    encodings = [str(declared)] if declared else []
    if raw.startswith((b"\xff\xfe", b"\xfe\xff")):
        encodings.append("utf-16")
    encodings.extend(["utf-8-sig", "gb18030"])
    tried, last = [], ""
    for encoding in encodings:
        if not encoding or encoding in tried:
            continue
        tried.append(encoding)
        try:
            return raw.decode(encoding), encoding, None
        except (UnicodeDecodeError, LookupError) as exc:
            last = str(exc)
    return None, None, "table decoding failed; tried " + ", ".join(tried) + ": " + last


def _csv(path: Path, spec: dict):
    try:
        raw_bytes = path.read_bytes()
    except OSError as exc:
        return [], str(path), {}, f"table could not be read: {exc}"
    raw, encoding, error = _decode(raw_bytes, spec.get("encoding"))
    if error:
        return [], str(path), {}, error
    meta = {"kind": "delimited", "encoding": encoding, "bytes": len(raw_bytes),
            "file_sha256": hashlib.sha256(raw_bytes).hexdigest()}
    if not raw or not raw.strip():
        return [], str(path), meta, None
    delimiter = spec.get("delimiter")
    if delimiter not in (",", "\t", ";", "|"):
        first = raw.splitlines()[0]
        delimiter = max((",", "\t", ";", "|"), key=lambda d: first.count(d))
    meta["delimiter"] = delimiter
    try:
        reader = csv.DictReader(io.StringIO(raw, newline=""), delimiter=delimiter)
        headers = reader.fieldnames or []
        if not headers or any(h is None or not str(h).strip() for h in headers):
            return [], str(path), meta, "table has an empty or unnamed header"
        if len(set(str(h).strip() for h in headers)) != len(headers):
            return [], str(path), meta, "duplicate header names would silently overwrite cells"
        rows = list(reader)
    except (csv.Error, TypeError, ValueError) as exc:
        return [], str(path), meta, f"delimited table parse failed: {exc}"
    if any(None in row for row in rows):
        return [], str(path), meta, "a row has more cells than the header"
    return rows, str(path), meta, None


def _sqlite(path: Path, spec: dict):
    if not path.is_file():
        return [], str(path), {}, f"SQLite database is missing: {path}"
    query = spec.get("query") or spec.get("sql")
    table = spec.get("table_name") or spec.get("table")
    max_rows = spec.get("max_rows", 100000)
    if not isinstance(max_rows, int) or isinstance(max_rows, bool) or not 1 <= max_rows <= 1000000:
        return [], str(path), {}, "max_rows must be an integer in [1, 1000000]"
    meta = {"kind": "sqlite", "read_only": True,
            "database_sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
    try:
        uri = path.resolve().as_uri() + "?mode=ro"
        con = sqlite3.connect(uri, uri=True)
        con.execute("PRAGMA query_only = ON")
        try:
            tables = [r[0] for r in con.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name")]
            meta["tables"] = tables
            if query is None:
                if table is None and len(tables) == 1:
                    table = tables[0]
                if not isinstance(table, str) or table not in tables:
                    return [], str(path), meta, "declare table_name from the available tables; no table was guessed"
                query = 'SELECT * FROM "' + table.replace('"', '""') + '"'
            if not isinstance(query, str):
                return [], str(path), meta, "query must be a SQL string"
            query = query.strip()
            if query.endswith(";"):
                query = query[:-1].rstrip()
            if not re.match(r"^(?:SELECT|WITH)\b", query, re.IGNORECASE) or ";" in query:
                return [], str(path), meta, "only one read-only SELECT/WITH query is accepted"
            cur = con.execute(query)
            names = [d[0] for d in cur.description or []]
            if not names or len(set(names)) != len(names):
                return [], str(path), meta, "query must return named, distinct columns"
            raw_rows = cur.fetchmany(max_rows + 1)
            if len(raw_rows) > max_rows:
                return [], str(path), meta, f"query exceeded max_rows={max_rows}; narrow it explicitly"
            rows = [dict(zip(names, values)) for values in raw_rows]
            meta.update({"query": query, "columns": names, "rows_returned": len(rows),
                         "table_name": table})
            return rows, str(path), meta, None
        finally:
            con.close()
    except (sqlite3.Error, OSError) as exc:
        return [], str(path), meta, f"read-only SQLite query failed: {exc}"


def validate_dictionary(spec: dict):
    """Reject malformed declared semantics before they silently become numeric."""
    import math
    columns = spec.get("columns")
    if columns is None:
        return None
    if not isinstance(columns, list):
        return "columns must be a list"
    allowed = {"", "numeric", "date", "categorical", "text", "id"}
    for i, col in enumerate(columns):
        if not isinstance(col, dict) or not isinstance(col.get("name"), str) or not col["name"].strip():
            return f"columns[{i}] needs a non-empty string name"
        semantic = col.get("semantic")
        if semantic is not None and not isinstance(semantic, str):
            return f"columns[{i}].semantic must be a string"
        if isinstance(semantic, str) and semantic.strip().lower() not in allowed:
            return f"columns[{i}].semantic '{semantic}' is unsupported"
        if col.get("target_unit") is not None and not isinstance(col.get("target_unit"), str):
            return f"columns[{i}].target_unit must be a string"
        plausible = col.get("plausible")
        if plausible is not None:
            if not isinstance(plausible, (list, tuple)) or len(plausible) != 2:
                return f"columns[{i}].plausible must be [lower, upper]"
            if any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v)
                   for v in plausible) or plausible[0] > plausible[1]:
                return f"columns[{i}].plausible needs finite ordered numeric bounds"
    for key in ("key_columns", "value_columns", "missing_tokens"):
        value = spec.get(key)
        if value is not None and (not isinstance(value, list)
                                  or any(not isinstance(item, str) for item in value)):
            return f"spec.{key} must be a list of strings"
    return None


def load_table(spec: dict):
    """Return (rows, source, metadata, error); never silently drop malformed rows."""
    dictionary_error = validate_dictionary(spec)
    if dictionary_error:
        return [], "dictionary", {}, dictionary_error
    rows = spec.get("rows")
    if rows is not None:
        if not isinstance(rows, list) or any(not isinstance(r, dict) for r in rows):
            return [], "inline", {}, "rows must be a list containing only objects"
        return rows, "inline", {"kind": "inline", "rows_returned": len(rows)}, None
    db = spec.get("sqlite_path") or spec.get("database_path") or spec.get("db_path")
    if db is not None:
        if not isinstance(db, str) or not db.strip():
            return [], "sqlite", {}, "sqlite_path must be a non-empty string"
        return _sqlite(Path(db), spec)
    table = spec.get("table_path")
    if table is not None:
        if not isinstance(table, str) or not table.strip():
            return [], "table", {}, "table_path must be a non-empty string"
        path = Path(table)
        if not path.is_file():
            return [], str(path), {}, f"table_path is missing or not a regular file: {table}"
        return _csv(path, spec)
    return [], "none", {}, None


def infer_columns(rows: list[dict]) -> list[dict]:
    """Conservative schema inference only when the case supplied no dictionary.

    Numeric requires at least 80% parse coverage among nonmissing cells. Other
    columns become categorical only at bounded cardinality; identifiers are not
    inferred as keys, so inference cannot fabricate a uniqueness design.
    """
    import units as U
    names = sorted({str(k) for row in rows for k in row})
    result = []
    for name in names:
        raw = [row.get(name) for row in rows]
        present = [str(v).strip() for v in raw if v is not None and str(v).strip()]
        parsed = sum(U.parse_measurement(v)["kind"] in ("single", "plus_minus", "range")
                     for v in present)
        unique = len(set(present))
        if present and parsed / len(present) >= 0.8:
            semantic = "numeric"
        elif present and unique <= min(50, max(2, int(len(rows) * 0.2))):
            semantic = "categorical"
        else:
            semantic = "text"
        result.append({"name": name, "semantic": semantic, "inferred": True,
                       "nonmissing": len(present), "numeric_parse_coverage":
                           round(parsed / len(present), 6) if present else None})
    return result
