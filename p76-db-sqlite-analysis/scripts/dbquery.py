"""Execute one authorised SQLite SELECT and produce a reproducible analysis bundle.

Only Python's standard library is used.  Safety is defence in depth: a single
SELECT/WITH statement check, a native SQLite authorizer that denies every write,
ATTACH, PRAGMA and dangerous function, a file:...?mode=ro connection, and
PRAGMA query_only=ON.  The query plan and rows really come from SQLite.

  python dbquery.py --db snapshot.sqlite --spec spec.json --out output
  python dbquery.py --db snapshot.sqlite --case case.json --sql "SELECT ..." --out output

No PostgreSQL/MySQL/network driver is pretended to exist.  Unsupported drivers,
missing execution environments and unreadable databases return undetermined.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import shutil
import sqlite3
import time
from collections import Counter
from pathlib import Path

ENGINE = "sqlite-query-analysis/v1"
SCHEMA = "db-query-analysis/v1"
EXIT_CODES = {"clean": 0, "review": 3, "blocked": 4, "refused": 5, "undetermined": 5}
MAX_SQL_CHARS = 200_000
MAX_ROWS_CAP = 100_000
MAX_TIMEOUT = 60.0


class Failure(Exception):
    def __init__(self, status: str, rule: str, message: str, **details):
        super().__init__(message)
        self.status = status
        self.rule = rule
        self.message = message
        self.details = details


# ---------------------------------------------------------------------------
# JSON, hashing and contract helpers
# ---------------------------------------------------------------------------

def _json_value(value):
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        if value != value:
            return {"type": "nonfinite", "value": "NaN"}
        if abs(value) == float("inf"):
            return {"type": "nonfinite", "value": "Infinity" if value > 0 else "-Infinity"}
        return value
    if isinstance(value, (bytes, bytearray, memoryview)):
        raw = bytes(value)
        return {"type": "blob", "length": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}
    if isinstance(value, dict):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_value(item) for item in value]
    return {"type": type(value).__name__, "repr": repr(value)}


def _write_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(_json_value(value), ensure_ascii=False, indent=2,
                               allow_nan=False) + "\n", encoding="utf-8")


def _canonical(value) -> str:
    return json.dumps(_json_value(value), ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"), allow_nan=False)


def _hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _hash_value(value) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def _contract_keys(contract) -> tuple[list[str], list[str]]:
    notes = []
    if contract is None:
        return [], notes
    if isinstance(contract, str):
        return [contract], notes
    if isinstance(contract, dict):
        fields = contract.get("fields")
        if fields is None:
            return list(contract), notes
        if isinstance(fields, dict):
            return list(fields), notes
        contract = fields
    if not isinstance(contract, (list, tuple)):
        return [], ["output_contract is not a field list"]
    keys = []
    for item in contract:
        if isinstance(item, str) and item.strip():
            keys.append(item)
        elif isinstance(item, dict):
            key = item.get("name") or item.get("field") or item.get("key")
            if isinstance(key, str) and key.strip():
                keys.append(key)
            else:
                notes.append(f"output_contract entry has no usable name: {item!r}")
        else:
            notes.append(f"output_contract contains a non-string field: {item!r}")
    return keys, notes


_BULKY = {"output_contract", "rows", "data", "documents", "text", "spec"}


def _echo_contract(spec: dict, result: dict) -> None:
    limits = result.setdefault("limits", [])
    result["case_id"] = spec.get("case_id")
    keys, notes = _contract_keys(spec.get("output_contract"))
    limits.extend(notes)
    for key in keys:
        if key in result:
            continue
        if key in spec and key not in _BULKY:
            result[key] = _json_value(spec[key])
        else:
            result[key] = None
            limits.append(f"output_contract field '{key}' was not derivable by this execution")


# ---------------------------------------------------------------------------
# SQL masking, validation and conservative join extraction
# ---------------------------------------------------------------------------

def _mask_sql(sql: str) -> str:
    """Mask comments and quoted content while preserving newlines and punctuation.

    This is deliberately a scanner, not a regular-expression SQL sanitizer.  It is
    used for statement counting and conservative relationship extraction; SQLite's
    authorizer remains the actual security boundary.
    """
    chars = list(sql)
    output = list(sql)
    state = "normal"
    index = 0
    while index < len(chars):
        char = chars[index]
        nxt = chars[index + 1] if index + 1 < len(chars) else ""
        if state == "normal":
            if char == "-" and nxt == "-":
                state = "line_comment"
                output[index] = output[index + 1] = " "
                index += 2
                continue
            if char == "/" and nxt == "*":
                state = "block_comment"
                output[index] = output[index + 1] = " "
                index += 2
                continue
            if char in ("'", '"', "`"):
                state = {"'": "single", '"': "double", "`": "backtick"}[char]
                output[index] = " "
            elif char == "[":
                state = "bracket"
                output[index] = " "
        elif state == "line_comment":
            if char == "\n":
                state = "normal"
            else:
                output[index] = " "
        elif state == "block_comment":
            if char == "*" and nxt == "/":
                output[index] = output[index + 1] = " "
                index += 2
                state = "normal"
                continue
            if char != "\n":
                output[index] = " "
        else:
            quote = {"single": "'", "double": '"', "backtick": "`", "bracket": "]"}[state]
            if char != "\n":
                output[index] = " "
            if char == quote:
                if nxt == quote and state != "bracket":
                    output[index + 1] = " "
                    index += 2
                    continue
                state = "normal"
        index += 1
    if state not in ("normal", "line_comment"):
        raise Failure("refused", "query.unterminated_quote", "SQL contains an unterminated quote or block comment")
    return "".join(output)


def _validate_sql(sql) -> tuple[str, str]:
    if not isinstance(sql, str) or not sql.strip():
        raise Failure("refused", "query.sql_missing", "spec.sql must contain one SELECT or WITH query")
    if len(sql) > MAX_SQL_CHARS:
        raise Failure("refused", "query.too_large", "SQL exceeds the input safety limit", limit=MAX_SQL_CHARS)
    masked = _mask_sql(sql)
    statements = [part for part in masked.split(";") if part.strip()]
    if len(statements) != 1:
        raise Failure("refused", "query.multiple_statements", "exactly one read-only statement is allowed",
                      statements=len(statements))
    first = re.match(r"\s*([A-Za-z]+)", statements[0])
    keyword = first.group(1).upper() if first else ""
    if keyword not in ("SELECT", "WITH"):
        raise Failure("refused", "query.not_read_only", "only SELECT or WITH ... SELECT is accepted",
                      first_keyword=keyword or None)
    dangerous = re.search(r"\b(load_extension|readfile|writefile|fts3_tokenizer|zipfile)\s*\(", masked, re.I)
    if dangerous:
        raise Failure("refused", "security.read_only_violation",
                      "file/extension functions are outside the authorised database-only capability",
                      function=dangerous.group(1))
    return sql, masked


def _aliases(masked: str) -> list[dict]:
    keyword_exclusions = {"ON", "WHERE", "JOIN", "LEFT", "RIGHT", "INNER", "OUTER", "FULL", "CROSS",
                          "GROUP", "ORDER", "LIMIT", "HAVING", "UNION", "EXCEPT", "INTERSECT", "USING",
                          "SELECT", "WHEN", "THEN", "ELSE", "END", "WINDOW", "RETURNING"}
    pattern = re.compile(
        r"\b(?P<keyword>FROM|JOIN)\s+(?P<table>[A-Za-z_][\w$]*(?:\.[A-Za-z_][\w$]*)?)"
        r"(?:\s+(?:AS\s+)?(?P<alias>[A-Za-z_][\w$]*))?", re.I)
    tables = []
    for match in pattern.finditer(masked):
        table = match.group("table").split(".")[-1]
        alias = match.group("alias")
        if alias and alias.upper() in keyword_exclusions:
            alias = None
        tables.append({"table": table, "alias": alias or table, "keyword": match.group("keyword").upper(),
                       "start": match.start(), "end": match.end()})
    return tables


def _relationships(masked: str, schema: dict, allowed_joins: list | None = None) -> dict:
    aliases = _aliases(masked)
    by_alias = {item["alias"].casefold(): item["table"] for item in aliases}
    by_alias.update({item["table"].casefold(): item["table"] for item in aliases})
    joins = []
    pair_pattern = re.compile(r"\b([A-Za-z_][\w$]*)\.([A-Za-z_][\w$]*)\s*=\s*([A-Za-z_][\w$]*)\.([A-Za-z_][\w$]*)")
    clause = re.compile(r"\b(?:LEFT|RIGHT|INNER|FULL|CROSS|JOIN|WHERE|GROUP|HAVING|ORDER|LIMIT|UNION|EXCEPT|INTERSECT)\b", re.I)
    for item in aliases:
        if item["keyword"] != "JOIN":
            continue
        following = clause.search(masked, item["end"])
        segment = masked[item["end"]:following.start() if following else len(masked)]
        using = re.search(r"\bUSING\s*\(([^)]+)\)", segment, re.I)
        pairs = []
        for match in pair_pattern.finditer(segment):
            left_alias, left_col, right_alias, right_col = match.groups()
            left_table = by_alias.get(left_alias.casefold())
            right_table = by_alias.get(right_alias.casefold())
            if left_table and right_table:
                pairs.append({"left": f"{left_table}.{left_col}", "right": f"{right_table}.{right_col}"})
        if using:
            current = item["table"]
            previous = next((other["table"] for other in reversed(aliases) if other["end"] <= item["start"]), None)
            for column in using.group(1).split(","):
                column = column.strip().strip('"`[]')
                if previous and column:
                    pairs.append({"left": f"{previous}.{column}", "right": f"{current}.{column}"})
        joins.append({"table": item["table"], "on_present": bool(pairs), "pairs": pairs})

    declared_fk = set()
    for table in schema["objects"].values():
        for fk in table["foreign_keys"]:
            if fk["referenced_table"]:
                declared_fk.add((f"{table['name']}.{fk['from']}".casefold(), f"{fk['referenced_table']}.{fk['to']}".casefold()))
                declared_fk.add((f"{fk['referenced_table']}.{fk['to']}".casefold(), f"{table['name']}.{fk['from']}".casefold()))
    allowed = set()
    for item in allowed_joins or []:
        if isinstance(item, dict) and item.get("left") and item.get("right"):
            pair = (str(item["left"]).casefold(), str(item["right"]).casefold())
            allowed.add(pair)
            allowed.add(pair[::-1])
    references = set()
    for join in joins:
        for pair in join["pairs"]:
            key = (pair["left"].casefold(), pair["right"].casefold())
            pair["declared_foreign_key"] = key in declared_fk
            pair["explicitly_allowed"] = key in allowed
            references.add(pair["left"])
            references.add(pair["right"])
    global_pairs = []
    for match in pair_pattern.finditer(masked):
        left_alias, left_col, right_alias, right_col = match.groups()
        left_table = by_alias.get(left_alias.casefold())
        right_table = by_alias.get(right_alias.casefold())
        if left_table and right_table:
            global_pairs.append({"left": f"{left_table}.{left_col}", "right": f"{right_table}.{right_col}"})
    return {"tables": [{k: v for k, v in item.items() if k not in ("start", "end")} for item in aliases],
            "joins": joins, "all_qualified_conditions": global_pairs,
            "referenced_join_columns": sorted(references)}


# ---------------------------------------------------------------------------
# Read-only connection and native schema/query plan
# ---------------------------------------------------------------------------

def _quoted(identifier: str) -> str:
    return '"' + identifier.replace('"', '""') + '"'


def _open_database(path_value) -> tuple[sqlite3.Connection, Path]:
    path = Path(str(path_value)).expanduser()
    if not path.is_file():
        raise Failure("undetermined", "connection.unavailable", "SQLite database file does not exist", path=str(path))
    uri = path.resolve().as_uri() + "?mode=ro"
    try:
        connection = sqlite3.connect(uri, uri=True, isolation_level=None)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA query_only = ON")
        try:
            connection.execute("PRAGMA trusted_schema = OFF")
        except sqlite3.Error:
            pass
        try:
            connection.enable_load_extension(False)
        except (AttributeError, sqlite3.Error):
            pass  # The authorizer still denies load_extension and every write.
        if hasattr(connection, "setlimit"):
            connection.setlimit(sqlite3.SQLITE_LIMIT_ATTACHED, 0)
        return connection, path
    except sqlite3.Error as exc:
        raise Failure("undetermined", "connection.failed", "could not open the SQLite snapshot read-only",
                      error=str(exc), path=str(path))


def _schema(connection: sqlite3.Connection) -> dict:
    try:
        rows = connection.execute(
            "SELECT name, type, sql FROM sqlite_master "
            "WHERE type IN ('table','view') AND name NOT LIKE 'sqlite_%' ORDER BY name").fetchall()
        objects = {}
        for row in rows:
            name = row["name"]
            columns = [dict(item) for item in connection.execute(f"PRAGMA table_info({_quoted(name)})")]
            foreign_keys = [{"from": item["from"], "referenced_table": item["table"], "to": item["to"],
                             "on_update": item["on_update"], "on_delete": item["on_delete"]}
                            for item in connection.execute(f"PRAGMA foreign_key_list({_quoted(name)})")]
            indexes = []
            for index in connection.execute(f"PRAGMA index_list({_quoted(name)})"):
                index_columns = [entry["name"] for entry in connection.execute(f"PRAGMA index_info({_quoted(index['name'])})")]
                indexes.append({"name": index["name"], "unique": bool(index["unique"]),
                                "origin": index["origin"], "columns": index_columns})
            row_count = None
            if row["type"] == "table":
                row_count = connection.execute(f"SELECT COUNT(*) FROM {_quoted(name)}").fetchone()[0]
            objects[name] = {"name": name, "type": row["type"], "sql": row["sql"],
                             "columns": columns, "foreign_keys": foreign_keys,
                             "indexes": indexes, "rows_in_snapshot": row_count}
        # Implicit REFERENCES parent_table without a column names the single PK.
        for obj in objects.values():
            for fk in obj["foreign_keys"]:
                if fk["to"] is None and fk["referenced_table"] in objects:
                    parent = objects[fk["referenced_table"]]
                    primary = sorted((column for column in parent["columns"] if column["pk"]),
                                     key=lambda column: column["pk"])
                    if len(primary) == 1:
                        fk["to"] = primary[0]["name"]
        metadata = {}
        for pragma in ("user_version", "schema_version", "application_id", "journal_mode"):
            try:
                metadata[pragma] = connection.execute(f"PRAGMA {pragma}").fetchone()[0]
            except sqlite3.Error:
                metadata[pragma] = None
        return {"objects": objects, "snapshot_metadata": metadata}
    except sqlite3.Error as exc:
        raise Failure("undetermined", "connection.invalid_database", "the file is not a readable SQLite database",
                      error=str(exc))


def _authorizer(state: dict):
    allowed = {sqlite3.SQLITE_SELECT, sqlite3.SQLITE_READ, sqlite3.SQLITE_FUNCTION, sqlite3.SQLITE_RECURSIVE}
    dangerous = {"load_extension", "writefile", "readfile", "fts3_tokenizer", "zipfile", "edit"}

    def authorize(action, arg1, arg2, database, source):
        name = f"SQLITE_{action}"
        if action == sqlite3.SQLITE_READ:
            state["reads"].add((arg1, arg2))
        if action == sqlite3.SQLITE_FUNCTION and str(arg2 or arg1 or "").casefold() in dangerous:
            state["denied"] = {"action": "SQLITE_FUNCTION", "function": arg2 or arg1}
            return sqlite3.SQLITE_DENY
        if action not in allowed:
            state["denied"] = {"action_code": action, "action": name, "arg1": arg1,
                               "arg2": arg2, "database": database, "source": source}
            return sqlite3.SQLITE_DENY
        return sqlite3.SQLITE_OK
    return authorize


def _execute(connection: sqlite3.Connection, sql: str, parameters, state: dict,
             max_rows: int, deadline: float, plan_only: bool = False) -> dict:
    prefix = "EXPLAIN QUERY PLAN " if plan_only else ""
    aborted = {"timeout": False}

    def progress():
        if time.monotonic() > deadline:
            aborted["timeout"] = True
            return 1
        return 0

    connection.set_progress_handler(progress, 1000)
    try:
        cursor = connection.execute(prefix + sql, parameters)
        if plan_only:
            records = [dict(row) for row in cursor.fetchall()]
            return {"plan": records}
        names = [entry[0] for entry in cursor.description or []]
        fetched = cursor.fetchmany(max_rows + 1)
        return {"column_names": names, "raw_rows": fetched,
                "truncated": len(fetched) > max_rows,
                "rows": fetched[:max_rows]}
    except (sqlite3.Error, TypeError, ValueError) as exc:
        if aborted["timeout"]:
            raise Failure("undetermined", "query.timeout", "query exceeded the deterministic resource budget")
        if state.get("denied"):
            raise Failure("refused", "security.read_only_violation", "SQLite authorizer denied a non-read-only operation",
                          **state["denied"])
        operation = "query planning" if plan_only else "query execution"
        raise Failure("refused", "query.sql_error", f"SQLite rejected the statement during {operation}",
                      error=str(exc), error_type=type(exc).__name__)
    finally:
        connection.set_progress_handler(None, 0)


# ---------------------------------------------------------------------------
# Result quality, expectations and unit handling
# ---------------------------------------------------------------------------

def _unique_names(names: list[str]) -> tuple[list[str], list[dict]]:
    counts = Counter()
    unique = []
    mapping = []
    for name in names:
        base = name or "unnamed"
        counts[base] += 1
        output = base if counts[base] == 1 else f"{base}__{counts[base]}"
        unique.append(output)
        mapping.append({"source_name": name, "result_name": output})
    return unique, mapping


def _quality(rows: list[dict], columns: list[str]) -> dict:
    report = {"row_count": len(rows), "per_column": {}, "exact_duplicate_rows": 0}
    canonical_rows = []
    for column in columns:
        values = [row.get(column) for row in rows]
        non_null = [value for value in values if value is not None]
        types = sorted({type(value).__name__ for value in non_null})
        canonical_values = [_canonical(value) for value in non_null]
        report["per_column"][column] = {
            "null_count": len(values) - len(non_null),
            "non_null": len(non_null),
            "missing_fraction": (len(values) - len(non_null)) / len(values) if values else 0.0,
            "distinct_count": len(set(canonical_values)),
            "storage_types": types,
            "mixed_storage_types": len(types) > 1,
        }
    report["exact_duplicate_rows"] = len(rows) - len({_canonical(row) for row in rows})
    return report


def _grain_check(rows: list[dict], grain: list[str]) -> dict:
    groups = {}
    for index, row in enumerate(rows):
        key = _canonical([row.get(column) for column in grain])
        groups.setdefault(key, []).append(index)
    duplicates = [{"key": json.loads(key), "rows": indices} for key, indices in groups.items() if len(indices) > 1]
    return {"grain": grain, "unique": not duplicates, "duplicate_groups": duplicates,
            "group_count": len(groups)}


def _summary(rows: list[dict], columns: list[str]) -> dict:
    result = {"row_count": len(rows), "sums": {}, "means": {}, "mins": {}, "maxs": {}, "nulls": {}, "distinct": {}}
    for column in columns:
        values = [row.get(column) for row in rows]
        numeric = [value for value in values if isinstance(value, (int, float)) and not isinstance(value, bool)]
        result["nulls"][column] = sum(value is None for value in values)
        result["distinct"][column] = len({_canonical(value) for value in values})
        if numeric:
            result["sums"][column] = sum(numeric)
            result["means"][column] = sum(numeric) / len(numeric)
            result["mins"][column] = min(numeric)
            result["maxs"][column] = max(numeric)
    return result


def _close(actual, expected, tolerance: float) -> bool:
    if isinstance(actual, (int, float)) and isinstance(expected, (int, float)):
        return abs(actual - expected) <= tolerance * max(1.0, abs(expected))
    return _canonical(actual) == _canonical(expected)


UNIT_DEFINITIONS = {
    "kg": ("mass", 1000.0, 0.0), "g": ("mass", 1.0, 0.0), "mg": ("mass", 1e-3, 0.0),
    "ug": ("mass", 1e-6, 0.0), "µg": ("mass", 1e-6, 0.0), "ng": ("mass", 1e-9, 0.0),
    "l": ("volume", 1.0, 0.0), "ml": ("volume", 1e-3, 0.0), "ul": ("volume", 1e-6, 0.0),
    "µl": ("volume", 1e-6, 0.0), "nl": ("volume", 1e-9, 0.0),
    "m": ("length", 1.0, 0.0), "km": ("length", 1000.0, 0.0), "cm": ("length", 0.01, 0.0),
    "mm": ("length", 0.001, 0.0), "um": ("length", 1e-6, 0.0), "µm": ("length", 1e-6, 0.0),
    "nm": ("length", 1e-9, 0.0),
    "h": ("time", 3600.0, 0.0), "min": ("time", 60.0, 0.0), "s": ("time", 1.0, 0.0),
    "ms": ("time", 1e-3, 0.0), "us": ("time", 1e-6, 0.0), "µs": ("time", 1e-6, 0.0),
    "mol/l": ("molar", 1.0, 0.0), "m": ("length", 1.0, 0.0),
    "mmol/l": ("molar", 1e-3, 0.0), "umol/l": ("molar", 1e-6, 0.0), "µmol/l": ("molar", 1e-6, 0.0),
    "nmol/l": ("molar", 1e-9, 0.0), "mm": ("length", 0.001, 0.0),
    "mmol": ("amount", 1e-3, 0.0), "umol": ("amount", 1e-6, 0.0), "µmol": ("amount", 1e-6, 0.0),
    "mol": ("amount", 1.0, 0.0), "nmol": ("amount", 1e-9, 0.0),
    "kj": ("energy", 1000.0, 0.0), "j": ("energy", 1.0, 0.0),
    "kcal": ("energy", 4184.0, 0.0), "cal": ("energy", 4.184, 0.0),
    "c": ("temperature", 1.0, 273.15), "°c": ("temperature", 1.0, 273.15),
    "k": ("temperature", 1.0, 0.0), "f": ("temperature", 5.0 / 9.0, 459.67),
    "°f": ("temperature", 5.0 / 9.0, 459.67),
    "%": ("dimensionless", 0.01, 0.0), "percent": ("dimensionless", 0.01, 0.0),
    "fraction": ("dimensionless", 1.0, 0.0), "ppm": ("dimensionless", 1e-6, 0.0),
    "ppb": ("dimensionless", 1e-9, 0.0),
}
# Molar shorthand is common in research tables and unambiguous when used as a unit.
UNIT_DEFINITIONS.update({"molar": ("molar", 1.0, 0.0), "millimolar": ("molar", 1e-3, 0.0),
                         "micromolar": ("molar", 1e-6, 0.0)})


def _unit_definition(unit: str):
    raw = str(unit or "").strip().replace("μ", "µ").replace(" ", "")
    # Case is semantically significant: m is metre, M is molar; mM is not mm.
    aliases = {"M": "mol/l", "mM": "mmol/l", "uM": "umol/l", "µM": "umol/l",
               "nM": "nmol/l", "mL": "ml", "uL": "ul", "µL": "ul", "nL": "nl"}
    key = aliases.get(raw, raw.casefold())
    return UNIT_DEFINITIONS.get(key), key


def _convert(value: float, source: str, target: str) -> tuple[float, dict]:
    source_def, source_key = _unit_definition(source)
    target_def, target_key = _unit_definition(target)
    if source_key == target_key:
        return value, {"factor": 1.0, "source_offset": 0.0, "target_offset": 0.0, "dimension": "same_unit"}
    if not source_def or not target_def or source_def[0] != target_def[0]:
        raise ValueError(f"incompatible or unknown units: {source!r} -> {target!r}")
    dimension, source_factor, source_offset = source_def
    _, target_factor, target_offset = target_def
    converted = (value + source_offset) * source_factor / target_factor - target_offset
    return converted, {"factor": source_factor / target_factor, "source_offset": source_offset,
                       "target_offset": target_offset, "dimension": dimension}


def _normalise_units(raw_rows: list[dict], unit_specs: dict) -> tuple[list[dict], list[dict], list[dict]]:
    analysis_rows = [dict(row) for row in raw_rows]
    changes = []
    problems = []
    for column, config in unit_specs.items():
        if not isinstance(config, dict):
            problems.append({"rule": "unit.spec_invalid", "column": column, "message": "unit configuration must be an object"})
            continue
        target = config.get("target_unit")
        unit_column = config.get("unit_column")
        fixed_source = config.get("source_unit") or config.get("unit")
        if not target:
            continue
        new_column = str(config.get("new_column") or f"{column}__{re.sub(r'[^A-Za-z0-9_]+', '_', str(target))}")
        for index, original in enumerate(raw_rows):
            value = original.get(column)
            if value is None:
                analysis_rows[index][new_column] = None
                continue
            source = original.get(unit_column) if unit_column else fixed_source
            if not source:
                problems.append({"rule": "unit.source_missing", "row": index, "column": column,
                                 "message": "a numeric value has no declared source unit"})
                analysis_rows[index][new_column] = None
                continue
            if not isinstance(value, (int, float)) or isinstance(value, bool):
                problems.append({"rule": "unit.non_numeric", "row": index, "column": column,
                                 "message": "unit conversion never parses or guesses numbers embedded in text"})
                analysis_rows[index][new_column] = None
                continue
            try:
                converted, detail = _convert(float(value), str(source), str(target))
                analysis_rows[index][new_column] = converted
                changes.append({"row": index, "column": column, "original": value,
                                "source_unit": source, "target_unit": target, "new_column": new_column,
                                "new_value": converted, **detail})
            except ValueError as exc:
                analysis_rows[index][new_column] = None
                problems.append({"rule": "unit.incompatible", "row": index, "column": column,
                                 "source_unit": source, "target_unit": target, "message": str(exc)})
    return analysis_rows, changes, problems


# ---------------------------------------------------------------------------
# Dictionary, evidence and artifacts
# ---------------------------------------------------------------------------

def _dictionary_index(spec: dict) -> dict:
    source = spec.get("data_dictionary") or spec.get("column_dictionary") or spec.get("columns") or {}
    index = {}
    if isinstance(source, dict):
        for key, value in source.items():
            if isinstance(value, dict):
                index[str(key).casefold()] = dict(value)
            else:
                index[str(key).casefold()] = {"description": str(value)}
    elif isinstance(source, list):
        for item in source:
            if not isinstance(item, dict) or not item.get("name"):
                continue
            keys = {str(item["name"]).casefold()}
            if item.get("table"):
                keys.add(f"{item['table']}.{item['name']}".casefold())
            for key in keys:
                index[key] = dict(item)
    return index


def _field_interpretation(columns: list[str], dictionary: dict, reads: set) -> list[dict]:
    tables = sorted({table for table, _ in reads if table})
    fields = []
    for column in columns:
        direct = dictionary.get(column.casefold())
        suffix_matches = [(key, value) for key, value in dictionary.items() if key.endswith("." + column.casefold())]
        selected = direct
        source = "data_dictionary" if direct else None
        ambiguous = False
        if selected is None and len(suffix_matches) == 1:
            selected = suffix_matches[0][1]
            source = "data_dictionary"
        elif selected is None and len(suffix_matches) > 1:
            ambiguous = True
        fields.append({"column": column, "description": (selected or {}).get("description") or (selected or {}).get("semantic"),
                       "unit": (selected or {}).get("unit") or (selected or {}).get("target_unit"),
                       "semantic": (selected or {}).get("semantic") or (selected or {}).get("role"),
                       "source": source, "ambiguous_dictionary_matches": [key for key, _ in suffix_matches] if ambiguous else [],
                       "referenced_tables": tables})
    return fields


def _csv_value(value) -> str:
    value = _json_value(value)
    return value if value is None or isinstance(value, (str, int, float)) else _canonical(value)


def _write_rows(path: Path, rows: list[dict], columns: list[str]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({column: _csv_value(row.get(column)) for column in columns})


def _setting_int(spec: dict, key: str, default: int, minimum: int, maximum: int) -> int:
    try:
        value = int(spec.get(key, default))
    except (TypeError, ValueError):
        raise Failure("undetermined", "input.spec_invalid", f"{key} must be an integer", field=key)
    return min(maximum, max(minimum, value))


def _status(findings: list[dict]) -> str:
    if any(item["severity"] == "high" for item in findings):
        return "blocked"
    return "review" if findings else "clean"


def _counts(findings: list[dict]) -> dict:
    counts = {"high": 0, "medium": 0, "low": 0}
    for finding in findings:
        counts[finding["severity"]] = counts.get(finding["severity"], 0) + 1
    return counts


def _failure_result(out_dir: Path, failure: Failure, spec: dict, artifacts: dict | None = None) -> dict:
    result = {"schema_version": SCHEMA, "status": failure.status,
              "findings": [{"rule": failure.rule, "severity": "high", "message": failure.message, **failure.details}],
              "severity_counts": {"high": 1, "medium": 0, "low": 0},
              "artifacts": artifacts or {}, "limits": ["No successful query result is claimed for this failure."],
              "query": {"sql": spec.get("sql") or spec.get("query"), "parameters": _json_value(spec.get("parameters") or spec.get("params") or [])},
              "execution": {"status": "not_completed", "row_count": None, "result_verified": False}}
    _echo_contract(spec, result)
    _write_json(out_dir / "result.json", result)
    return result


# ---------------------------------------------------------------------------
# Main execution
# ---------------------------------------------------------------------------

def run_analysis(db_value, spec: dict, out_dir: Path, task_path: str | None = None) -> dict:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    artifacts = {}
    connection = None
    try:
        if not isinstance(spec, dict):
            raise Failure("undetermined", "input.spec_not_object", "query spec must be a JSON object")
        driver = str(spec.get("driver") or "sqlite").strip().casefold()
        if driver not in ("sqlite", "sqlite3"):
            raise Failure("undetermined", "connection.unsupported_driver",
                          "only a local SQLite snapshot is executable by this package", requested_driver=driver)
        raw_sql = spec.get("sql") or spec.get("query")
        if isinstance(raw_sql, str):
            (out_dir / "query.sql").write_text(raw_sql.rstrip() + "\n", encoding="utf-8")
            artifacts["query_sql"] = str(out_dir / "query.sql")
        sql, masked = _validate_sql(raw_sql)
        parameters = spec.get("parameters") or spec.get("params") or []
        if not isinstance(parameters, (list, tuple, dict)):
            raise Failure("refused", "query.parameters_invalid", "parameters must be a JSON array or object")
        max_rows = _setting_int(spec, "max_rows", 10_000, 1, MAX_ROWS_CAP)
        try:
            timeout = min(MAX_TIMEOUT, max(0.1, float(spec.get("timeout_seconds", 20))))
        except (TypeError, ValueError):
            raise Failure("undetermined", "input.spec_invalid", "timeout_seconds must be numeric")
        if not db_value:
            raise Failure("undetermined", "connection.unavailable", "no SQLite database path was supplied")

        connection, db_path = _open_database(db_value)
        original_hash = _hash_file(db_path)
        if spec.get("snapshot_copy", True):
            if db_path.stat().st_size <= int(spec.get("snapshot_max_bytes", 5_000_000)):
                snapshot = out_dir / "database_snapshot.sqlite"
                if db_path.resolve() != snapshot.resolve():
                    shutil.copyfile(db_path, snapshot)
                artifacts["database_snapshot"] = str(snapshot)
            else:
                artifacts["database_snapshot"] = None

        schema = _schema(connection)
        _write_json(out_dir / "schema.json", schema)
        artifacts["schema"] = str(out_dir / "schema.json")
        state = {"denied": None, "reads": set()}
        connection.set_authorizer(_authorizer(state))
        planned = _execute(connection, sql, parameters, state, max_rows, time.monotonic() + timeout, plan_only=True)
        executed = _execute(connection, sql, parameters, state, max_rows, time.monotonic() + timeout)
        query_plan = planned["plan"]
        _write_json(out_dir / "query_plan.json", query_plan)
        artifacts["query_plan"] = str(out_dir / "query_plan.json")

        names, name_mapping = _unique_names(executed["column_names"])
        raw_rows = [dict(zip(names, [_json_value(value) for value in row])) for row in executed["rows"]]
        findings = []
        limits = []
        if any(source is None or not str(source).strip() for source, _ in name_mapping):
            findings.append({"rule": "query.unnamed_column", "severity": "medium",
                             "message": "unnamed result expressions were assigned deterministic names"})
        if len(set(executed["column_names"])) != len(executed["column_names"]):
            findings.append({"rule": "query.duplicate_column_names", "severity": "medium",
                             "message": "duplicate SQLite result names were suffixed instead of overwritten",
                             "column_name_map": name_mapping})
        if not raw_rows:
            findings.append({"rule": "query.empty_result", "severity": "medium",
                             "message": "the authorised query executed successfully but returned zero rows"})
        if executed["truncated"]:
            findings.append({"rule": "query.rows_truncated", "severity": "high",
                             "message": "the result exceeds max_rows; aggregates over this partial extract are not complete",
                             "max_rows": max_rows})
            limits.append("Only max_rows plus one row was fetched to detect truncation; full-table conclusions are blocked.")

        quality = _quality(raw_rows, names)
        if quality["exact_duplicate_rows"]:
            findings.append({"rule": "data.duplicate_rows", "severity": "medium",
                             "message": "identical result rows are preserved and reported, not silently deduplicated",
                             "count": quality["exact_duplicate_rows"]})
        for column, details in quality["per_column"].items():
            if details["mixed_storage_types"]:
                findings.append({"rule": "data.mixed_storage_types", "severity": "medium",
                                 "message": "a result column mixes SQLite storage types; no implicit numeric coercion was applied",
                                 "column": column, **details})

        not_null = spec.get("not_null") or []
        if not isinstance(not_null, list) or any(not isinstance(column, str) for column in not_null):
            raise Failure("undetermined", "input.spec_invalid", "not_null must be an array of result column names")
        for column in not_null:
            if column not in names:
                findings.append({"rule": "validation.not_null_column_missing", "severity": "high",
                                 "message": "a not_null constraint names a column absent from the result", "column": column})
            elif quality["per_column"][column]["null_count"]:
                findings.append({"rule": "validation.unexpected_null", "severity": "high",
                                 "message": "NULL appears in a column declared not_null; it was not coerced to zero or blank text",
                                 "column": column, "null_count": quality["per_column"][column]["null_count"]})

        dictionary = _dictionary_index(spec)
        if not dictionary:
            findings.append({"rule": "schema.data_dictionary_missing", "severity": "medium",
                             "message": "no data dictionary was supplied; field semantics remain limited to SQLite declarations"})
            limits.append("Field meanings and units are undetermined without a supplied data dictionary.")
        interpretation = _field_interpretation(names, dictionary, state["reads"])
        for field in interpretation:
            if field["ambiguous_dictionary_matches"]:
                findings.append({"rule": "schema.field_ambiguous", "severity": "medium",
                                 "message": "multiple qualified dictionary fields match this result column",
                                 "column": field["column"], "candidates": field["ambiguous_dictionary_matches"]})

        relationships = _relationships(masked, schema, spec.get("allowed_joins"))
        if relationships["joins"] and not relationships["all_qualified_conditions"]:
            findings.append({"rule": "join.condition_missing", "severity": "high",
                             "message": "an explicit JOIN has no recognised ON/USING condition",
                             "note": "inspect query.sql and query_plan.json; a deliberate Cartesian join must be justified"})
        if relationships["joins"] and not spec.get("grain"):
            limits.append("Join row inflation cannot be ruled out until a result grain is declared or inferred from GROUP BY.")
        for join in relationships["joins"]:
            for pair in join["pairs"]:
                if not pair["declared_foreign_key"] and not pair["explicitly_allowed"]:
                    findings.append({"rule": "join.key_not_declared", "severity": "low",
                                     "message": "a join pair is not backed by a schema FK or allowed_joins declaration; verify semantics",
                                     **pair})

        group_match = re.search(r"\bGROUP\s+BY\b(.*?)(?=\bHAVING\b|\bORDER\b|\bLIMIT\b|$)", masked, re.I | re.S)
        group_fields = []
        if group_match:
            group_fields = [item.strip().strip('"`[]') for item in group_match.group(1).split(",") if item.strip()]
        inferred_grain = []
        for field in group_fields:
            candidate = field if field in names else field.split(".")[-1]
            if candidate not in names and field.isdigit() and 1 <= int(field) <= len(names):
                candidate = names[int(field) - 1]
            if candidate in names:
                inferred_grain.append(candidate)
        grain = spec.get("grain") or inferred_grain
        if grain and (not isinstance(grain, list) or any(not isinstance(column, str) for column in grain)):
            raise Failure("undetermined", "input.spec_invalid", "grain must be an array of result column names")
        grain_result = None
        if grain:
            missing = [column for column in grain if column not in names]
            if missing:
                findings.append({"rule": "validation.grain_missing", "severity": "high",
                                 "message": "declared grain columns are absent from the query result", "missing": missing})
            else:
                grain_result = _grain_check(raw_rows, grain)
                if not grain_result["unique"]:
                    findings.append({"rule": "validation.grain_not_unique", "severity": "high",
                                     "message": "the declared analysis grain is not unique; join/aggregation inflation is possible",
                                     "duplicate_groups": grain_result["duplicate_groups"][:20]})

        unit_specs = spec.get("units") or {}
        if not isinstance(unit_specs, dict):
            raise Failure("undetermined", "input.spec_invalid", "units must be an object keyed by result column")
        analysis_rows, unit_changes, unit_problems = _normalise_units(raw_rows, unit_specs)
        for problem in unit_problems:
            severity = "high" if problem["rule"] in ("unit.incompatible", "unit.non_numeric", "unit.source_missing") else "medium"
            findings.append({"severity": severity, **problem})
        for column, config in unit_specs.items():
            if isinstance(config, dict) and config.get("unit_column") and not config.get("target_unit"):
                unit_values = {row.get(config["unit_column"]) for row in raw_rows if row.get(config["unit_column"]) is not None}
                if len(unit_values) > 1:
                    findings.append({"rule": "unit.mixed_units", "severity": "medium",
                                     "message": "multiple source units are present but no target_unit conversion was declared",
                                     "column": column, "units": sorted(map(str, unit_values))})

        expected_count = spec.get("expected_row_count")
        if expected_count is not None:
            try:
                expected_count = int(expected_count)
            except (TypeError, ValueError):
                raise Failure("undetermined", "input.spec_invalid", "expected_row_count must be an integer")
            if expected_count != len(raw_rows):
                findings.append({"rule": "validation.row_count_mismatch", "severity": "high",
                                 "message": "actual result row count differs from the independent expectation",
                                 "expected": expected_count, "actual": len(raw_rows)})
        expected_columns = spec.get("expected_columns")
        if expected_columns is not None:
            missing = [column for column in expected_columns if column not in names] if isinstance(expected_columns, list) else list(expected_columns or [])
            extra = [column for column in names if column not in expected_columns] if spec.get("exact_columns") and isinstance(expected_columns, list) else []
            if missing or extra or not isinstance(expected_columns, list):
                findings.append({"rule": "validation.columns_mismatch", "severity": "high",
                                 "message": "query result columns do not meet expected_columns", "missing": missing, "extra": extra})
        expected_rows = spec.get("expected_rows")
        if expected_rows is not None:
            expected_serial = _json_value(expected_rows)
            if expected_serial != raw_rows:
                findings.append({"rule": "validation.rows_mismatch", "severity": "high",
                                 "message": "query rows differ from the independently supplied expected_rows",
                                 "expected_row_count": len(expected_rows) if isinstance(expected_rows, list) else None,
                                 "actual_row_count": len(raw_rows), "rows_sha256": _hash_value(raw_rows),
                                 "expected_sha256": _hash_value(expected_rows)})

        tolerance = float(spec.get("numeric_tolerance", 1e-9))
        actual_summary = _summary(analysis_rows, list(analysis_rows[0].keys()) if analysis_rows else list(dict.fromkeys(names + [key for row in analysis_rows for key in row])))
        expected_summary = spec.get("expected_summary") or {}
        if not isinstance(expected_summary, dict):
            raise Failure("undetermined", "input.spec_invalid", "expected_summary must be an object")
        for metric, expected_value in expected_summary.items():
            if metric == "row_count":
                matched = _close(actual_summary["row_count"], expected_value, tolerance)
                actual_value = actual_summary["row_count"]
            elif metric in ("sums", "means", "mins", "maxs", "nulls", "distinct") and isinstance(expected_value, dict):
                for column, expected in expected_value.items():
                    actual_value = actual_summary[metric].get(column)
                    if not _close(actual_value, expected, tolerance):
                        findings.append({"rule": "validation.summary_mismatch", "severity": "high",
                                         "message": "an independently recomputed summary disagrees with expected_summary",
                                         "metric": metric, "column": column, "expected": expected, "actual": actual_value})
                continue
            else:
                raise Failure("undetermined", "input.spec_invalid", "unsupported expected_summary metric", metric=metric)
            if not matched:
                findings.append({"rule": "validation.summary_mismatch", "severity": "high",
                                 "message": "actual row_count differs from expected_summary", "expected": expected_value, "actual": actual_value})

        independent = None
        check = spec.get("independent_check")
        if check:
            check_sql = check if isinstance(check, str) else check.get("sql")
            check_params = [] if isinstance(check, str) else check.get("parameters", [])
            expected = 1 if isinstance(check, str) else check.get("expected", 1)
            check_sql, _ = _validate_sql(check_sql)
            check_plan = _execute(connection, check_sql, check_params, state, 2, time.monotonic() + timeout, plan_only=True)
            check_result = _execute(connection, check_sql, check_params, state, 2, time.monotonic() + timeout)
            check_rows = check_result["rows"]
            scalar = check_rows[0][0] if len(check_rows) == 1 and len(check_result["column_names"]) == 1 else None
            passed = len(check_rows) == 1 and len(check_result["column_names"]) == 1 and _close(scalar, expected, tolerance)
            independent = {"sql": check_sql, "query_plan": check_plan["plan"], "scalar": _json_value(scalar),
                           "expected": expected, "passed": passed}
            if not passed:
                findings.append({"rule": "validation.independent_check_failed", "severity": "high",
                                 "message": "the independent validation SQL did not return the declared expected scalar",
                                 "expected": expected, "actual": _json_value(scalar)})

        read_tables = sorted({table for table, _ in state["reads"] if table})
        read_columns = sorted([{"table": table, "column": column} for table, column in state["reads"]],
                              key=lambda item: (item["table"] or "", item["column"] or ""))
        post_hash = _hash_file(db_path)
        if post_hash != original_hash:
            findings.append({"rule": "connection.snapshot_changed", "severity": "high",
                             "message": "database bytes changed during execution; results are not one stable snapshot",
                             "before_sha256": original_hash, "after_sha256": post_hash})
        _write_json(out_dir / "rows.json", raw_rows)
        _write_json(out_dir / "analysis_rows.json", analysis_rows)
        _write_rows(out_dir / "rows.csv", raw_rows, names)
        analysis_columns = list(dict.fromkeys(names + [key for row in analysis_rows for key in row]))
        _write_rows(out_dir / "analysis_rows.csv", analysis_rows, analysis_columns)
        artifacts.update({"rows_json": str(out_dir / "rows.json"), "rows_csv": str(out_dir / "rows.csv"),
                          "analysis_rows_json": str(out_dir / "analysis_rows.json"),
                          "analysis_rows_csv": str(out_dir / "analysis_rows.csv")})
        execution = {"driver": "SQLite", "sqlite_version": sqlite3.sqlite_version,
                     "read_only_uri": True, "query_only_pragma": True, "authorizer": True,
                     "single_statement": True, "row_count": len(raw_rows), "column_count": len(names),
                     "truncated": executed["truncated"], "max_rows": max_rows, "timeout_seconds": timeout,
                     "referenced_tables": read_tables, "referenced_columns": read_columns,
                     "database_sha256_before": original_hash, "database_sha256_after": post_hash,
                     "snapshot_stable": original_hash == post_hash,
                     "query_sha256": hashlib.sha256(sql.encode("utf-8")).hexdigest(),
                     "rows_sha256": _hash_value(raw_rows), "analysis_rows_sha256": _hash_value(analysis_rows)}
        log = {"input_validated": True, "database_opened_read_only": True, "schema_extracted": True,
               "query_planned": True, "query_executed": True, "rows_fetched": len(raw_rows),
               "truncated": executed["truncated"], "independent_check": independent,
               "snapshot_stable": execution["snapshot_stable"], "exit_code_semantics": EXIT_CODES}
        _write_json(out_dir / "execution_log.json", log)
        artifacts["execution_log"] = str(out_dir / "execution_log.json")
        if artifacts.get("database_snapshot") is None:
            limits.append("Database exceeds snapshot_max_bytes; hash and schema identify the source but no byte copy was retained.")
        if not spec.get("interpretation"):
            limits.append("No causal or scientific interpretation is inferred from SQL rows alone.")
        conclusions = {"result": f"SQLite returned {len(raw_rows)} rows and {len(names)} columns from one read-only statement.",
                       "row_count": len(raw_rows), "grain_check": grain_result,
                       "independent_check_passed": independent["passed"] if independent else None,
                       "interpretation": spec.get("interpretation"),
                       "trace": {"query_sha256": execution["query_sha256"], "rows_sha256": execution["rows_sha256"]}}
        findings_status = _status(findings)
        result = {"schema_version": SCHEMA, "status": findings_status,
                  "findings": findings, "severity_counts": _counts(findings),
                  "analysis_result": {"rows": raw_rows, "analysis_rows": analysis_rows,
                                      "column_name_map": name_mapping, "summary": actual_summary},
                  "rows": raw_rows, "analysis_rows": analysis_rows,
                  "quality_report": quality, "unit_changes": unit_changes,
                  "schema": schema, "query_plan": query_plan,
                  "relationships": relationships,
                  "aggregation": {"group_by": group_fields, "grain": grain,
                                  "grain_check": grain_result},
                  "field_interpretation": interpretation,
                  "execution": execution, "conclusions": conclusions,
                  "query": {"sql": sql, "parameters": _json_value(parameters)},
                  "artifacts": artifacts, "provenance": {
                      "engine": ENGINE, "python_sqlite_module": getattr(sqlite3, "version", None),
                      "sqlite_runtime": sqlite3.sqlite_version, "database_file": str(db_path),
                      "database_sha256": original_hash, "snapshot_metadata": schema["snapshot_metadata"],
                      "task_file": str(task_path) if task_path else None,
                      "task_sha256": _hash_file(Path(task_path)) if task_path else None},
                  "limits": limits}
        _echo_contract(spec, result)
        _write_json(out_dir / "result.json", result)
        return result
    except Failure as failure:
        return _failure_result(out_dir, failure, spec if isinstance(spec, dict) else {}, artifacts)
    except Exception as exc:
        failure = Failure("undetermined", "runtime.failed",
                          f"query analysis could not complete: {type(exc).__name__}: {exc}")
        return _failure_result(out_dir, failure, spec if isinstance(spec, dict) else {}, artifacts)
    finally:
        if connection is not None:
            try:
                connection.close()
            except sqlite3.Error:
                pass


def _load_spec(path: str | None) -> dict:
    if not path:
        return {}
    try:
        value = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise Failure("undetermined", "input.spec_unreadable", f"could not read query spec: {exc}")
    if not isinstance(value, dict):
        raise Failure("undetermined", "input.spec_not_object", "query spec must be a JSON object")
    return value


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="dbquery", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--db")
    parser.add_argument("--spec")
    parser.add_argument("--case")
    parser.add_argument("--task")
    parser.add_argument("--sql")
    parser.add_argument("--out", required=True)
    args = parser.parse_args(argv)
    spec = {}
    try:
        spec = _load_spec(args.case) if args.case else {}
        query_spec = _load_spec(args.spec)
        for key, value in query_spec.items():
            spec[key] = value
        if args.sql is not None:
            spec["sql"] = args.sql
        spec.setdefault("driver", "sqlite")
        result = run_analysis(args.db or spec.get("db_path") or spec.get("database"), spec,
                              Path(args.out), args.task)
    except Failure as failure:
        result = _failure_result(Path(args.out), failure, spec)
    except Exception as exc:
        result = _failure_result(Path(args.out),
                                 Failure("undetermined", "runtime.failed",
                                         f"request preparation failed: {type(exc).__name__}: {exc}"), spec)
    print(json.dumps({"status": result["status"], "case_id": result.get("case_id"),
                      "findings": [finding["rule"] for finding in result.get("findings", [])],
                      "rows": (result.get("execution") or {}).get("row_count"),
                      "result": str(Path(args.out) / "result.json")}, ensure_ascii=False))
    return EXIT_CODES.get(result["status"], 1)


if __name__ == "__main__":
    raise SystemExit(main())
