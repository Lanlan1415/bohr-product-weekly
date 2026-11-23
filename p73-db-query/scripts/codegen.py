"""Deterministic, standard-library scientific analysis code generator.

The generator is deliberately narrower than a general Python agent: it emits one
standalone analysis.py from a validated declarative spec.  The executor in this
package accepts only this output; caller-supplied Python is never executed.
"""
from __future__ import annotations

import ast
import copy
import json
import re

ENGINE_VERSION = "scicode/1.0"
SAFE_IMPORTS = {"csv", "hashlib", "html", "io", "json", "math", "sqlite3", "statistics", "pathlib"}
BANNED_NAMES = {"eval", "exec", "compile", "__import__", "breakpoint", "open", "input"}
SQL_FORBIDDEN = re.compile(
    r"\b(attach|detach|pragma|insert|update|delete|drop|alter|create|replace|"
    r"vacuum|reindex|load_extension)\b", re.I)


class SpecError(ValueError):
    def __init__(self, rule: str, message: str):
        super().__init__(message)
        self.rule = rule
        self.message = message


def _integer(value, default, low, high, field):
    if value is None:
        return default
    if isinstance(value, bool):
        raise SpecError("spec.type_error", f"{field} must be an integer")
    try:
        number = int(value)
    except (TypeError, ValueError, OverflowError):
        raise SpecError("spec.type_error", f"{field} must be an integer")
    if number < low or number > high:
        raise SpecError("spec.range_error", f"{field} must be between {low} and {high}")
    return number


def _string_list(value, field, allow_empty=True):
    if value is None:
        return []
    if not isinstance(value, list) or any(not isinstance(x, str) for x in value):
        raise SpecError("spec.type_error", f"{field} must be a list of strings")
    if not allow_empty and not value:
        raise SpecError("spec.empty_input", f"{field} must not be empty")
    if len(value) > 100 or any(len(x) > 500 for x in value):
        raise SpecError("spec.input_too_large", f"{field} exceeds its declared bound")
    return list(value)


def validate_read_only_query(query):
    if not isinstance(query, str) or not query.strip():
        raise SpecError("query.missing", "SQLite input requires a non-empty SELECT query")
    stripped = query.strip()
    if ";" in stripped.rstrip(";") or stripped.count(";") > 1:
        raise SpecError("query.not_read_only", "multiple SQL statements are not accepted")
    if not re.match(r"^(select|with)\b", stripped, re.I):
        raise SpecError("query.not_read_only", "only SELECT or WITH queries are accepted")
    if SQL_FORBIDDEN.search(stripped):
        raise SpecError("query.not_read_only", "the query contains a forbidden write/pragma token")
    if len(stripped) > 20000:
        raise SpecError("spec.input_too_large", "SQL query exceeds 20000 characters")
    return stripped.rstrip(";").strip()


def normalize_spec(spec, resolved_input=None, max_input_bytes=25_000_000):
    """Return a bounded copy of spec or raise a structured SpecError."""
    if not isinstance(spec, dict):
        raise SpecError("input.spec_not_object", "spec must be a JSON object")
    out = copy.deepcopy(spec)
    section = out.get("section")
    if section not in (None, "scicode", "code_generation", "科研代码生成与执行"):
        raise SpecError("section.unknown", f"unsupported section {section!r}; expected scicode")
    source = out.get("input")
    if not isinstance(source, dict):
        raise SpecError("input.missing", "spec.input must be an object")
    path = source.get("path")
    if not isinstance(path, str) or not path.strip() or len(path) > 4096:
        raise SpecError("input.path_invalid", "spec.input.path must be a non-empty bounded string")
    fmt = source.get("format")
    if fmt is None:
        suffix = path.lower().rsplit(".", 1)[-1] if "." in path else ""
        fmt = {"csv": "csv", "tsv": "tsv", "json": "json", "db": "sqlite",
               "sqlite": "sqlite", "sqlite3": "sqlite"}.get(suffix)
    if fmt not in ("csv", "tsv", "json", "sqlite"):
        raise SpecError("input.format_unknown", "input.format must be csv, tsv, json, or sqlite")
    source["format"] = fmt
    source["resolved_path"] = str(resolved_input or path)
    source["max_bytes"] = min(
        _integer(source.get("max_bytes"), max_input_bytes, 1, 100_000_000, "input.max_bytes"),
        max_input_bytes)
    source["max_rows"] = _integer(source.get("max_rows"), 10000, 1, 50000, "input.max_rows")
    if fmt == "sqlite":
        source["query"] = validate_read_only_query(source.get("query"))
    elif source.get("query") is not None:
        raise SpecError("spec.type_error", "input.query is valid only for SQLite input")

    columns = out.get("columns")
    if not isinstance(columns, list) or not columns:
        raise SpecError("dictionary.missing", "spec.columns must be a non-empty data dictionary")
    names, sources = set(), set()
    normalized_columns = []
    for index, col in enumerate(columns):
        if not isinstance(col, dict):
            raise SpecError("dictionary.type_error", f"columns[{index}] must be an object")
        name, original = col.get("name"), col.get("source", col.get("name"))
        if not isinstance(name, str) or not name.strip() or len(name) > 200:
            raise SpecError("dictionary.type_error", f"columns[{index}].name is invalid")
        if not isinstance(original, str) or not original.strip() or len(original) > 200:
            raise SpecError("dictionary.type_error", f"columns[{index}].source is invalid")
        kind = col.get("type", col.get("semantic", "text"))
        if kind not in ("numeric", "categorical", "text", "id", "date"):
            raise SpecError("dictionary.type_error", f"unsupported type for column {name}")
        if name in names or original in sources:
            raise SpecError("dictionary.duplicate", "column names/sources must be unique")
        names.add(name)
        sources.add(original)
        item = dict(col)
        item.update({"name": name, "source": original, "type": kind,
                     "required": bool(col.get("required", True))})
        normalized_columns.append(item)
    out["columns"] = normalized_columns

    metrics = _string_list(out.get("metrics"), "metrics")
    if not metrics:
        metrics = [c["name"] for c in normalized_columns if c["type"] == "numeric"]
    if not metrics:
        raise SpecError("dictionary.no_metrics", "declare at least one numeric metric")
    for name in metrics:
        if name not in names or next(c for c in normalized_columns if c["name"] == name)["type"] != "numeric":
            raise SpecError("dictionary.metric_unknown", f"metric {name!r} is not a declared numeric column")
    out["metrics"] = metrics

    group_by = out.get("group_by")
    if group_by is not None and (not isinstance(group_by, str) or group_by not in names):
        raise SpecError("dictionary.group_unknown", "group_by must name a declared column")
    out["missing_tokens"] = _string_list(out.get("missing_tokens"), "missing_tokens")[:50]
    out["drop_exact_duplicates"] = out.get("drop_exact_duplicates", False)
    if not isinstance(out["drop_exact_duplicates"], bool):
        raise SpecError("spec.type_error", "drop_exact_duplicates must be boolean")

    correlations = out.get("correlations", [])
    if not isinstance(correlations, list):
        raise SpecError("spec.type_error", "correlations must be a list")
    for pair in correlations:
        if (not isinstance(pair, list) or len(pair) != 2 or
                any(x not in metrics for x in pair)):
            raise SpecError("dictionary.metric_unknown", "each correlation must pair two declared metrics")

    tests = out.get("welch_t", [])
    if isinstance(tests, dict):
        tests = [tests]
    if not isinstance(tests, list):
        raise SpecError("spec.type_error", "welch_t must be an object or list")
    for test in tests:
        if not isinstance(test, dict) or test.get("column") not in metrics:
            raise SpecError("dictionary.metric_unknown", "each Welch test needs a declared metric column")
        test_group = test.get("group_by", group_by)
        if test_group not in names:
            raise SpecError("dictionary.group_unknown", "Welch test group_by is not declared")
        if not isinstance(test.get("group_a"), (str, int, float)) or not isinstance(test.get("group_b"), (str, int, float)):
            raise SpecError("dictionary.group_unknown", "Welch test needs group_a and group_b")
        test["group_by"] = test_group
    out["welch_t"] = tests

    chart = out.get("chart")
    if chart is not None:
        if not isinstance(chart, dict) or chart.get("kind") not in ("histogram", "scatter"):
            raise SpecError("chart.unsupported", "chart.kind must be histogram or scatter")
        if chart["kind"] == "histogram" and chart.get("column") not in metrics:
            raise SpecError("dictionary.metric_unknown", "histogram column must be a declared metric")
        if chart["kind"] == "scatter" and (chart.get("x") not in metrics or chart.get("y") not in metrics):
            raise SpecError("dictionary.metric_unknown", "scatter x/y must be declared metrics")
        chart["bins"] = _integer(chart.get("bins"), 10, 1, 50, "chart.bins")
        for key in ("title", "x_label", "y_label", "unit"):
            if key in chart and not isinstance(chart[key], str):
                raise SpecError("spec.type_error", f"chart.{key} must be a string")
            if isinstance(chart.get(key), str) and len(chart[key]) > 500:
                raise SpecError("spec.input_too_large", f"chart.{key} is too long")

    validation = out.get("validation", {})
    if not isinstance(validation, dict):
        raise SpecError("spec.type_error", "validation must be an object")
    if "expected_rows" in validation:
        validation["expected_rows"] = _integer(validation["expected_rows"], None, 0, 1000000,
                                                "validation.expected_rows")
    _string_list(validation.get("expected_columns"), "validation.expected_columns")
    golden = validation.get("golden", [])
    if not isinstance(golden, list):
        raise SpecError("spec.type_error", "validation.golden must be a list")
    for item in golden:
        if not isinstance(item, dict) or not isinstance(item.get("path"), str) or "value" not in item:
            raise SpecError("spec.type_error", "each golden check needs path and value")
        for key, default in (("atol", 1e-8), ("rtol", 1e-8)):
            try:
                item[key] = float(item.get(key, default))
            except (TypeError, ValueError, OverflowError):
                raise SpecError("spec.type_error", f"golden {key} must be numeric")
            if item[key] < 0 or not (item[key] < float("inf")):
                raise SpecError("spec.range_error", f"golden {key} must be finite and non-negative")

    parameters = out.get("parameters", {})
    if not isinstance(parameters, dict):
        raise SpecError("spec.type_error", "parameters must be an object")
    parameters["seed"] = _integer(parameters.get("seed"), 0, 0, 2**31 - 1, "parameters.seed")
    parameters["float_precision"] = _integer(parameters.get("float_precision"), 10, 4, 15,
                                               "parameters.float_precision")
    out["parameters"] = parameters
    out["engine_version"] = ENGINE_VERSION
    return out


def audit_generated_code(code):
    """Defence-in-depth check; this is not advertised as a general sandbox."""
    tree = ast.parse(code)
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.split(".")[0] not in SAFE_IMPORTS:
                    raise SpecError("execution.unsafe_code", f"disallowed import {alias.name}")
        elif isinstance(node, ast.ImportFrom):
            if (node.module or "").split(".")[0] not in SAFE_IMPORTS:
                raise SpecError("execution.unsafe_code", f"disallowed import {node.module}")
        elif isinstance(node, ast.Name) and node.id in BANNED_NAMES:
            raise SpecError("execution.unsafe_code", f"disallowed builtin {node.id}")
        elif (isinstance(node, ast.Attribute) and node.attr.startswith("__")
              and node.attr != "__name__"):
            raise SpecError("execution.unsafe_code", "dunder attribute access is disallowed")
    return True


GENERATED_TEMPLATE = r'''"""Generated by scicode/1.0. Standalone; standard library only."""
import csv
import hashlib
import html
import io
import json
import math
import sqlite3
import statistics
from pathlib import Path

SPEC = json.loads(__SPEC_JSON__)
OUT = Path(__file__).resolve().parent
MISSING_DEFAULT = {"", "na", "n/a", "null", "none", "nan", "not reported", "未报告", "未检出"}
MISSING = MISSING_DEFAULT | {str(x).strip().casefold() for x in SPEC.get("missing_tokens", [])}
PRECISION = SPEC["parameters"]["float_precision"]


def number(value):
    if value is None or isinstance(value, bool):
        return None
    try:
        result = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return result if math.isfinite(result) else None


def rounded(value):
    if value is None:
        return None
    return round(float(value), PRECISION)


def sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while True:
            block = handle.read(1024 * 1024)
            if not block:
                break
            digest.update(block)
    return digest.hexdigest()


def emit(payload):
    (OUT / "analysis.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")


def fail(rule, message, status="undetermined", code=5, details=None):
    finding = {"rule": rule, "severity": "high", "message": message}
    if details:
        finding.update(details)
    payload = {"schema_version": "scicode-analysis/v1", "case_id": SPEC.get("case_id"),
               "status": status, "findings": [finding], "statistics": {}, "groups": {},
               "correlations": [], "tests": [], "artifacts": {},
               "limits": ["analysis did not complete; no numeric result is claimed"]}
    emit(payload)
    print(json.dumps({"status": status, "error": rule}, ensure_ascii=False))
    raise SystemExit(code)


def write_rows(path, rows, columns):
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=columns, extrasaction="ignore", lineterminator="\n")
    writer.writeheader()
    for row in rows:
        cooked = {}
        for key in columns:
            value = row.get(key)
            if isinstance(value, (dict, list)):
                value = json.dumps(value, ensure_ascii=False, sort_keys=True)
            cooked[key] = "" if value is None else value
        writer.writerow(cooked)
    path.write_text(buffer.getvalue(), encoding="utf-8")


def read_rows():
    source = SPEC["input"]
    path = Path(source["resolved_path"])
    if not path.is_file():
        fail("input.file_missing", "declared input file does not exist or is not a regular file")
    if path.stat().st_size > source["max_bytes"]:
        fail("input.too_large", "input exceeds the configured byte limit",
             details={"bytes": path.stat().st_size, "max_bytes": source["max_bytes"]})
    fmt = source["format"]
    rows, columns = [], []
    truncated = False
    if fmt in ("csv", "tsv"):
        raw = path.read_text(encoding="utf-8-sig")
        reader = csv.DictReader(io.StringIO(raw), delimiter="\t" if fmt == "tsv" else ",")
        columns = list(reader.fieldnames or [])
        for row in reader:
            if None in row:
                fail("input.row_shape", "a CSV/TSV row has more cells than the header",
                     status="blocked", code=4)
            if len(rows) >= source["max_rows"]:
                truncated = True
                break
            rows.append(dict(row))
    elif fmt == "json":
        data = json.loads(path.read_text(encoding="utf-8-sig"))
        if isinstance(data, dict):
            data = data.get("rows")
        if not isinstance(data, list):
            fail("input.rows_type", "JSON input must be a row list or an object containing rows")
        for row in data:
            if not isinstance(row, dict):
                fail("input.row_type", "every JSON row must be an object")
            if len(rows) >= source["max_rows"]:
                truncated = True
                break
            rows.append(dict(row))
            for key in row:
                if key not in columns:
                    columns.append(key)
    else:
        connection = None
        try:
            connection = sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)
            connection.execute("PRAGMA query_only=ON")
            cursor = connection.execute(source["query"])
            columns = [item[0] for item in (cursor.description or [])]
            fetched = cursor.fetchmany(source["max_rows"] + 1)
            truncated = len(fetched) > source["max_rows"]
            fetched = fetched[:source["max_rows"]]
            rows = [dict(zip(columns, values)) for values in fetched]
        finally:
            if connection is not None:
                connection.close()
    if not columns or any(not isinstance(name, str) or not name for name in columns):
        fail("input.header_missing", "input has no usable named columns", status="blocked", code=4)
    if len(set(columns)) != len(columns):
        fail("input.duplicate_columns", "duplicate source column names would silently overwrite values",
             status="blocked", code=4, details={"columns": columns})
    if not rows:
        fail("input.no_rows", "the table/query returned zero rows; no statistic is fabricated")
    return rows, columns, truncated


def describe(values, states, precision=True):
    numeric = [value for value, state in zip(values, states) if state == "valid" and value is not None]
    record = {"rows": len(values), "n": len(numeric),
              "missing": sum(state == "missing" for state in states),
              "unparsed": sum(state == "unparsed" for state in states)}
    if numeric:
        record.update({"mean": statistics.fmean(numeric),
                       "sample_sd": statistics.stdev(numeric) if len(numeric) > 1 else None,
                       "min": min(numeric), "median": statistics.median(numeric), "max": max(numeric)})
        quantiles = statistics.quantiles(numeric, n=4, method="inclusive") if len(numeric) > 1 else [None, None, None]
        record.update({"q1": quantiles[0], "q3": quantiles[2]})
    else:
        record.update({"mean": None, "sample_sd": None, "min": None, "median": None,
                       "max": None, "q1": None, "q3": None})
    if precision:
        record = {key: rounded(value) if isinstance(value, float) else value
                  for key, value in record.items()}
    return record


def betacf(a, b, x):
    tiny = 1e-300
    qab, qap, qam = a + b, a + 1.0, a - 1.0
    c = 1.0
    d = 1.0 - qab * x / qap
    if abs(d) < tiny:
        d = tiny
    d = 1.0 / d
    h = d
    for m in range(1, 201):
        m2 = 2 * m
        aa = m * (b - m) * x / ((qam + m2) * (a + m2))
        d = 1.0 + aa * d
        if abs(d) < tiny:
            d = tiny
        c = 1.0 + aa / c
        if abs(c) < tiny:
            c = tiny
        d = 1.0 / d
        h *= d * c
        aa = -(a + m) * (qab + m) * x / ((a + m2) * (qap + m2))
        d = 1.0 + aa * d
        if abs(d) < tiny:
            d = tiny
        c = 1.0 + aa / c
        if abs(c) < tiny:
            c = tiny
        d = 1.0 / d
        delta = d * c
        h *= delta
        if abs(delta - 1.0) < 3e-14:
            return h
    raise ValueError("incomplete beta did not converge")


def betai(a, b, x):
    if x <= 0.0:
        return 0.0
    if x >= 1.0:
        return 1.0
    bt = math.exp(math.lgamma(a + b) - math.lgamma(a) - math.lgamma(b) +
                  a * math.log(x) + b * math.log1p(-x))
    if x < (a + 1.0) / (a + b + 2.0):
        return bt * betacf(a, b, x) / a
    return 1.0 - bt * betacf(b, a, 1.0 - x) / b


def welch(records, states, test):
    column, group = test["column"], test["group_by"]
    samples = {str(test["group_a"]): [], str(test["group_b"]): []}
    for index, row in enumerate(records):
        key = str(row.get(group)) if row.get(group) is not None else "<missing>"
        if key in samples and states[index][column] == "valid":
            samples[key].append(float(records[index][column]))
    a = samples[str(test["group_a"])]
    b = samples[str(test["group_b"])]
    result = {"column": column, "group_by": group, "group_a": str(test["group_a"]),
              "group_b": str(test["group_b"]), "n_a": len(a), "n_b": len(b),
              "direction": "group_b minus group_a"}
    findings = []
    if len(a) < 2 or len(b) < 2:
        findings.append({"rule": "stats.sample_too_small", "severity": "high",
                         "message": "Welch t requires at least two valid values per group",
                         "column": column, "n_a": len(a), "n_b": len(b)})
        result.update({"mean_a": statistics.fmean(a) if a else None,
                       "mean_b": statistics.fmean(b) if b else None,
                       "t": None, "df": None, "p_two_sided": None})
        return result, findings
    va, vb = statistics.variance(a), statistics.variance(b)
    ma, mb = statistics.fmean(a), statistics.fmean(b)
    result.update({"mean_a": rounded(ma), "mean_b": rounded(mb), "difference": rounded(mb - ma)})
    if va <= 0 or vb <= 0:
        findings.append({"rule": "stats.zero_variance", "severity": "high",
                         "message": "Welch t is undefined for a zero-variance group",
                         "column": column, "variance_a": va, "variance_b": vb})
        result.update({"t": None, "df": None, "p_two_sided": None})
        return result, findings
    se2 = va / len(a) + vb / len(b)
    t_value = (mb - ma) / math.sqrt(se2)
    df = se2 * se2 / ((va / len(a)) ** 2 / (len(a) - 1) + (vb / len(b)) ** 2 / (len(b) - 1))
    p_value = betai(df / 2.0, 0.5, df / (df + t_value * t_value))
    pooled = math.sqrt(((len(a) - 1) * va + (len(b) - 1) * vb) / (len(a) + len(b) - 2))
    result.update({"t": rounded(t_value), "df": rounded(df), "p_two_sided": rounded(p_value),
                   "cohen_d_pooled": rounded((mb - ma) / pooled) if pooled > 0 else None})
    if len(a) < 5 or len(b) < 5:
        findings.append({"rule": "stats.small_sample", "severity": "medium",
                         "message": "small group: inspect distribution and use the p value cautiously",
                         "column": column, "n_a": len(a), "n_b": len(b)})
    return result, findings


def svg_chart(records, states, input_sha):
    chart = SPEC.get("chart")
    if not chart:
        return None
    width, height, left, right, top, bottom = 800, 500, 85, 30, 45, 75
    pw, ph = width - left - right, height - top - bottom
    title = html.escape(chart.get("title") or chart["kind"])
    unit = chart.get("unit", "")
    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
             f'<metadata>source-sha256:{input_sha};generator:scicode/1.0</metadata>',
             '<rect width="100%" height="100%" fill="white"/>',
             f'<text x="{width/2}" y="25" text-anchor="middle" font-family="sans-serif" font-size="18">{title}</text>',
             f'<line x1="{left}" y1="{top+ph}" x2="{left+pw}" y2="{top+ph}" stroke="black"/>',
             f'<line x1="{left}" y1="{top}" x2="{left}" y2="{top+ph}" stroke="black"/>']
    if chart["kind"] == "histogram":
        column = chart["column"]
        values = [float(row[column]) for index, row in enumerate(records)
                  if states[index][column] == "valid"]
        if not values:
            fail("chart.no_values", "histogram has no valid numeric values", status="blocked", code=4)
        low, high = min(values), max(values)
        bins = chart["bins"]
        if high == low:
            low, high = low - 0.5, high + 0.5
        counts = [0] * bins
        for value in values:
            index = min(bins - 1, int((value - low) / (high - low) * bins))
            counts[index] += 1
        peak = max(counts)
        for index, count in enumerate(counts):
            x = left + pw * index / bins
            y = top + ph * (1 - count / peak)
            bar_w, bar_h = pw / bins, ph * count / peak
            parts.append(f'<rect data-bin="{index}" data-count="{count}" x="{x:.3f}" y="{y:.3f}" width="{max(0, bar_w-1):.3f}" height="{bar_h:.3f}" fill="#4878b8"/>')
        x_label = chart.get("x_label") or column
        y_label = chart.get("y_label") or "Frequency"
        axis = f"{low:g}..{high:g}" + (f" {unit}" if unit else "")
    else:
        xcol, ycol = chart["x"], chart["y"]
        points = [(index, float(row[xcol]), float(row[ycol])) for index, row in enumerate(records)
                  if states[index][xcol] == "valid" and states[index][ycol] == "valid"]
        if not points:
            fail("chart.no_values", "scatter plot has no paired numeric values", status="blocked", code=4)
        xs, ys = [p[1] for p in points], [p[2] for p in points]
        xmin, xmax, ymin, ymax = min(xs), max(xs), min(ys), max(ys)
        if xmax == xmin:
            xmin, xmax = xmin - 0.5, xmax + 0.5
        if ymax == ymin:
            ymin, ymax = ymin - 0.5, ymax + 0.5
        for index, xval, yval in points:
            x = left + pw * (xval - xmin) / (xmax - xmin)
            y = top + ph * (1 - (yval - ymin) / (ymax - ymin))
            parts.append(f'<circle data-row="{index}" data-x="{xval:g}" data-y="{yval:g}" cx="{x:.3f}" cy="{y:.3f}" r="3" fill="#4878b8" fill-opacity="0.65"/>')
        x_label = chart.get("x_label") or xcol
        y_label = chart.get("y_label") or ycol
        axis = f"x {xmin:g}..{xmax:g}; y {ymin:g}..{ymax:g}" + (f" {unit}" if unit else "")
    parts.extend([f'<text x="{left+pw/2}" y="{height-20}" text-anchor="middle" font-family="sans-serif">{html.escape(x_label)}</text>',
                  f'<text x="20" y="{top+ph/2}" text-anchor="middle" transform="rotate(-90 20 {top+ph/2})" font-family="sans-serif">{html.escape(y_label)}</text>',
                  f'<text x="{left}" y="{height-45}" font-family="sans-serif" font-size="11">{html.escape(axis)}</text>', '</svg>'])
    (OUT / "figure.svg").write_text("\n".join(parts), encoding="utf-8")
    return {"kind": chart["kind"], "path": "figure.svg", "source_sha256": input_sha,
            "marks": len(counts) if chart["kind"] == "histogram" else len(points)}


def main():
    raw_rows, source_columns, truncated = read_rows()
    source = SPEC["input"]
    input_sha = sha256(Path(source["resolved_path"]))
    findings, limits, changes = [], [], []
    for column in SPEC["columns"]:
        if column["required"] and column["source"] not in source_columns:
            fail("data.column_missing", f"required source column {column['source']!r} is absent",
                 status="blocked", code=4, details={"available_columns": source_columns})
    records, states = [], []
    per_quality = {c["name"]: {"missing": 0, "unparsed": 0} for c in SPEC["columns"]}
    for row_index, raw in enumerate(raw_rows):
        record, row_state = {}, {}
        for column in SPEC["columns"]:
            name = column["name"]
            value = raw.get(column["source"])
            if isinstance(value, bytes):
                value = "0x" + value.hex()
            text = value.strip() if isinstance(value, str) else value
            is_missing = value is None or (isinstance(text, str) and text.casefold() in MISSING)
            if is_missing:
                record[name], row_state[name] = None, "missing"
                per_quality[name]["missing"] += 1
                if len(changes) < 100:
                    changes.append({"row": row_index, "column": name, "original": value,
                                    "new": None, "reason": "missing token; never coerced to zero"})
            elif column["type"] == "numeric":
                parsed = number(text)
                if parsed is None:
                    record[name], row_state[name] = None, "unparsed"
                    per_quality[name]["unparsed"] += 1
                    if len(changes) < 100:
                        changes.append({"row": row_index, "column": name, "original": value,
                                        "new": None, "reason": "unparsed or non-finite numeric value"})
                else:
                    record[name], row_state[name] = parsed, "valid"
            else:
                record[name], row_state[name] = text, "valid"
        records.append(record)
        states.append(row_state)
    write_rows(OUT / "extracted_rows.csv", raw_rows, source_columns)

    for name, quality in per_quality.items():
        if quality["missing"]:
            findings.append({"rule": "data.missing_values", "severity": "medium",
                             "message": "missing values are named gaps, not zero", "column": name,
                             "count": quality["missing"]})
        if quality["unparsed"]:
            findings.append({"rule": "data.unparsed_values", "severity": "medium",
                             "message": "unparsed/non-finite numeric cells were excluded from statistics",
                             "column": name, "count": quality["unparsed"]})
    if truncated:
        limits.append("row cap reached; additional input rows were not analysed")
        findings.append({"rule": "input.row_limit", "severity": "high",
                         "message": "row cap truncated the input; completeness cannot be claimed",
                         "max_rows": source["max_rows"]})

    pairs = list(zip(records, states))
    seen = set()
    unique_pairs = []
    for pair in pairs:
        key = json.dumps(pair[0], ensure_ascii=False, sort_keys=True, allow_nan=False)
        if key not in seen:
            seen.add(key)
            unique_pairs.append(pair)
    duplicates = len(pairs) - len(unique_pairs)
    if duplicates:
        findings.append({"rule": "data.duplicate_rows", "severity": "low",
                         "message": "exact duplicate rows counted; removal only by explicit spec",
                         "count": duplicates, "removed": SPEC["drop_exact_duplicates"]})
    if SPEC["drop_exact_duplicates"]:
        pairs = unique_pairs
    records = [pair[0] for pair in pairs]
    states = [pair[1] for pair in pairs]
    names = [column["name"] for column in SPEC["columns"]]
    write_rows(OUT / "cleaned.csv", records, names)

    statistics_by_column = {}
    for name in SPEC["metrics"]:
        statistics_by_column[name] = describe([row.get(name) for row in records],
                                               [state[name] for state in states])
    groups = {}
    if SPEC.get("group_by"):
        group_name = SPEC["group_by"]
        group_values = sorted({str(row.get(group_name)) if row.get(group_name) is not None else "<missing>"
                               for row in records})
        groups = {"group_by": group_name, "metrics": {}}
        for name in SPEC["metrics"]:
            group_records = []
            for group_value in group_values:
                indices = [index for index, row in enumerate(records)
                           if (str(row.get(group_name)) if row.get(group_name) is not None else "<missing>") == group_value]
                item = {"group": group_value}
                item.update(describe([records[index].get(name) for index in indices],
                                     [states[index][name] for index in indices]))
                group_records.append(item)
            groups["metrics"][name] = group_records

    correlations = []
    for xcol, ycol in SPEC.get("correlations", []):
        points = [(float(row[xcol]), float(row[ycol])) for index, row in enumerate(records)
                  if states[index][xcol] == "valid" and states[index][ycol] == "valid"]
        item = {"x": xcol, "y": ycol, "n": len(points), "pearson_r": None}
        if len(points) >= 2:
            xs, ys = [p[0] for p in points], [p[1] for p in points]
            mx, my = statistics.fmean(xs), statistics.fmean(ys)
            denominator = math.sqrt(sum((x-mx)**2 for x in xs) * sum((y-my)**2 for y in ys))
            if denominator > 0:
                item["pearson_r"] = rounded(sum((x-mx)*(y-my) for x, y in points) / denominator)
            else:
                findings.append({"rule": "stats.zero_variance", "severity": "high",
                                 "message": "Pearson correlation is undefined for a constant column",
                                 "x": xcol, "y": ycol})
        else:
            findings.append({"rule": "stats.sample_too_small", "severity": "high",
                             "message": "Pearson correlation needs two paired values", "x": xcol, "y": ycol})
        correlations.append(item)

    tests = []
    for test in SPEC.get("welch_t", []):
        result, test_findings = welch(records, states, test)
        tests.append(result)
        findings.extend(test_findings)
    if tests:
        limits.append("Welch tests do not prove normality or causality; inspect distributions and design")

    chart = svg_chart(records, states, input_sha)
    artifacts = {"extracted_rows": "extracted_rows.csv", "cleaned_table": "cleaned.csv",
                 "analysis": "analysis.json"}
    if chart:
        artifacts["figure"] = "figure.svg"
    high = any(item["severity"] == "high" for item in findings)
    status = "blocked" if high else "review" if findings else "clean"
    result = {"schema_version": "scicode-analysis/v1", "case_id": SPEC.get("case_id"),
              "status": status,
              "input": {"format": source["format"], "path": source["path"], "sha256": input_sha,
                        "rows_read": len(raw_rows), "rows_analysed": len(records),
                        "source_columns": source_columns, "query": source.get("query"),
                        "row_cap": source["max_rows"], "truncated": truncated},
              "data_quality": {"exact_duplicate_rows": duplicates,
                               "duplicates_removed": duplicates if SPEC["drop_exact_duplicates"] else 0,
                               "changes": changes, "changes_truncated": len(changes) >= 100},
              "statistics": statistics_by_column, "groups": groups,
              "correlations": correlations, "tests": tests, "chart": chart,
              "artifacts": artifacts, "findings": findings, "limits": limits}
    emit(result)
    print(json.dumps({"status": status, "rows": len(records),
                      "findings": len(findings)}, ensure_ascii=False))
    raise SystemExit(4 if status == "blocked" else 3 if status == "review" else 0)


try:
    main()
except SystemExit:
    raise
except Exception as exc:
    fail("execution.analysis_error", f"generated analysis failed: {type(exc).__name__}: {str(exc)[:400]}")
'''


def generate_code(spec, resolved_input=None, max_input_bytes=25_000_000):
    normalized = normalize_spec(spec, resolved_input=resolved_input, max_input_bytes=max_input_bytes)
    encoded = json.dumps(normalized, ensure_ascii=False, sort_keys=True, allow_nan=False)
    code = GENERATED_TEMPLATE.replace("__SPEC_JSON__", repr(encoded))
    audit_generated_code(code)
    return code, normalized
