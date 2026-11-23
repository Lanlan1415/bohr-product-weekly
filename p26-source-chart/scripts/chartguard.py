"""Render and audit a traceable scientific chart, with no network dependency.

The engine has three layers inspired by declarative grammar tools (Vega-Lite and
seaborn): infer field types, bind explicit encoding channels, then reconcile the
rendered artists with source rows.  A chart is not accepted merely because a
file exists: labels, uncertainty, sample size, accessible redundant encodings,
and the actual drawn geometry are checked.

Explicit mode:
  python chartguard.py --spec spec.json --data table.csv --out output
Automatic, question-aware mode:
  python chartguard.py --auto --data table.csv --question "compare groups" --out output
Either mode accepts --case case.json and --task task.md for contract passthrough.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import re
import shutil
import struct
import textwrap
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path
from xml.sax.saxutils import escape

try:  # Import failure becomes a structured undetermined result in the CLI.
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import numpy as np
    _IMPORT_ERROR = None
except Exception as exc:  # pragma: no cover - exercised on minimal Python images
    matplotlib = None
    plt = None
    np = None
    _IMPORT_ERROR = f"{type(exc).__name__}: {exc}"

import fontsel as FS

ENGINE = "source-chart/v3"
SCHEMA = "source-chart/v3"
CHART_KINDS = {"bar", "line", "scatter", "box", "heatmap", "histogram"}
REQUIRED = {
    "bar": {"x", "y"},
    "line": {"x", "y"},
    "scatter": {"x", "y"},
    "box": {"x", "y"},
    "heatmap": {"x", "y", "value"},
    "histogram": {"x"},
}
SUPPORTED_CHANNELS = {
    "x", "y", "value", "group", "x_err", "x_err2", "y_err", "y_err2",
    # Pre-aggregated absolute CI/interval endpoints (Vega-Lite layered errorband).
    # They are source columns, never intervals inferred by this renderer.
    "y_lower", "y_upper",
}
UNCERTAINTY_CHANNELS = {
    "x_err", "x_err2", "y_err", "y_err2", "y_lower", "y_upper",
}
# Okabe-Ito, including black as the eighth colour.  Shape, dash and hatch are
# redundant channels so colour is never the sole series identifier.
OKABE_ITO = ["#E69F00", "#56B4E9", "#009E73", "#0072B2", "#D55E00", "#CC79A7", "#F0E442", "#000000"]
MARKERS = ["o", "s", "^", "D", "v", "P", "X", "<"]
DASHES = ["-", "--", "-.", ":", (0, (5, 2)), (0, (2, 1)), (0, (7, 2)), (0, (1, 1))]
HATCHES = ["", "//", "\\\\", "xx", "..", "++", "--", "oo"]
NULL_TOKENS = {"", "null", "none", "na", "n/a", "nan", "not reported", "未报告", "缺失"}


# ---------------------------------------------------------------------------
# Data and field types
# ---------------------------------------------------------------------------

def _missing(value) -> bool:
    return value is None or str(value).strip().casefold() in NULL_TOKENS


def load_table(path: Path) -> dict:
    """Read UTF-8 CSV/TSV/JSON without silently dropping headers or row shape errors."""
    path = Path(path)
    raw = path.read_text(encoding="utf-8-sig")
    if path.suffix.lower() == ".json":
        data = json.loads(raw)
        rows = data if isinstance(data, list) else data.get("rows", []) if isinstance(data, dict) else None
        if not isinstance(rows, list) or any(not isinstance(r, dict) for r in rows):
            raise ValueError("JSON table must be a list of row objects or an object with rows[]")
        columns = []
        for row in rows:
            for key in row:
                if key not in columns:
                    columns.append(key)
    else:
        lines = raw.splitlines()
        delim = "\t" if lines and lines[0].count("\t") > lines[0].count(",") else ","
        reader = csv.DictReader(io.StringIO(raw), delimiter=delim)
        columns = list(reader.fieldnames or [])
        if len(columns) != len(set(columns)):
            raise ValueError("duplicate column names would make the data-to-mark mapping ambiguous")
        rows = list(reader)
        if any(None in row for row in rows):
            raise ValueError("a row has more cells than the header")
    return {"columns": columns, "rows": rows, "n": len(rows)}


def _as_float(value):
    if _missing(value):
        return None
    try:
        number = float(str(value).strip())
        return number if number == number and abs(number) != float("inf") else None
    except (TypeError, ValueError):
        return None


def _as_coordinate(value):
    """Numeric coordinate or a real ISO temporal coordinate for ordered line charts."""
    number = _as_float(value)
    if number is not None or _missing(value):
        return number
    try:
        from matplotlib import dates as mdates
        return float(mdates.date2num(datetime.fromisoformat(str(value).strip().replace("Z", "+00:00"))))
    except (TypeError, ValueError, OverflowError):
        return None


def numeric_column(table: dict, name: str) -> list[float | None]:
    return [_as_float(row.get(name)) for row in table["rows"]]


def is_numeric(table: dict, name: str) -> bool:
    values = numeric_column(table, name)
    present = [v for v in values if v is not None]
    declared = sum(1 for row in table["rows"] if not _missing(row.get(name)))
    return bool(present) and len(present) == declared


def _temporal_column(table: dict, name: str) -> bool:
    values = [str(row.get(name, "")).strip() for row in table["rows"] if not _missing(row.get(name))]
    if not values:
        return False
    if any(token in name.casefold() for token in ("date", "time", "year", "month", "week", "日期", "时间", "年", "月")):
        return True
    parsed = 0
    for value in values[:100]:
        try:
            datetime.fromisoformat(value.replace("Z", "+00:00"))
            parsed += 1
        except ValueError:
            pass
    return parsed >= max(1, int(0.8 * len(values[:100])))


def infer_field_types(table: dict) -> dict:
    """Return Vega-Lite-like nominal/ordinal/quantitative/temporal types with evidence."""
    result = {}
    for column in table.get("columns", []):
        raw = [row.get(column) for row in table["rows"] if not _missing(row.get(column))]
        distinct = {str(value) for value in raw}
        if _temporal_column(table, column):
            kind, reason = "temporal", "column name or ISO values indicate ordered time"
        elif is_numeric(table, column):
            name = column.casefold()
            categorical_hint = any(token in name for token in ("class", "category", "group", "type", "label", "species", "类别", "分组", "处理"))
            if categorical_hint and len(distinct) <= 20:
                kind, reason = "ordinal", "numeric codes with a categorical field name"
            else:
                kind, reason = "quantitative", "all non-missing values parse as finite numbers"
        elif len(distinct) <= 2:
            kind, reason = "nominal", "two-level categorical values"
        else:
            kind, reason = "nominal", "non-numeric categorical values"
        result[column] = {
            "type": kind,
            "reason": reason,
            "non_null": len(raw),
            "missing": table["n"] - len(raw),
            "distinct": len(distinct),
        }
    return result


def recommend_encoding(table: dict, question: str = "") -> dict:
    """Choose a chart from field types and the analytical purpose, never from values alone."""
    fields = infer_field_types(table)
    quantitative = [c for c, meta in fields.items() if meta["type"] == "quantitative"]
    temporal = [c for c, meta in fields.items() if meta["type"] == "temporal"]
    categorical = [c for c, meta in fields.items() if meta["type"] in ("nominal", "ordinal")]
    q = (question or "").casefold()
    wants = lambda *words: any(word in q for word in words)

    if temporal and quantitative:
        kind, x, y = "line", temporal[0], quantitative[0]
        reason = "a temporal field and a quantitative measure require an ordered trend"
    elif wants("heatmap", "matrix", "热图", "矩阵") and len(categorical) >= 2 and quantitative:
        kind, x, y = "heatmap", categorical[0], categorical[1]
        reason = "two categorical grid fields and one quantitative value support a matrix"
    elif categorical and quantitative and wants("distribut", "box", "分布", "箱线"):
        kind, x, y = "box", categorical[0], quantitative[0]
        reason = "grouped raw observations should show their distribution, not only means"
    elif wants("distribut", "histogram", "分布", "直方") and quantitative:
        kind, x, y = "histogram", quantitative[0], None
        reason = "the question asks for the distribution of a quantitative field"
    elif wants("correl", "relationship", "scatter", "相关", "关系", "散点") and len(quantitative) >= 2:
        kind, x, y = "scatter", quantitative[0], quantitative[1]
        reason = "two quantitative fields preserve paired observations in a scatter plot"
    elif categorical and quantitative:
        # Repeated observations are distributions; one value per category is a comparison.
        counts = {}
        for row in table["rows"]:
            counts[row.get(categorical[0])] = counts.get(row.get(categorical[0]), 0) + 1
        kind = "box" if counts and max(counts.values()) > 1 else "bar"
        x, y = categorical[0], quantitative[0]
        reason = ("repeated observations per category favour a box plot" if kind == "box"
                  else "one quantitative value per category supports a length-encoded comparison")
    elif len(quantitative) >= 2:
        kind, x, y = "scatter", quantitative[0], quantitative[1]
        reason = "with no categorical axis, two quantitative fields retain the most information"
    elif quantitative:
        kind, x, y = "histogram", quantitative[0], None
        reason = "a single quantitative field is best summarised by an explicit-bin distribution"
    else:
        raise ValueError("no quantitative field is available for a supported scientific chart")

    encoding = {"x": x}
    if y is not None:
        encoding["y"] = y
    if kind == "heatmap":
        encoding["value"] = quantitative[0]
    group = None
    if kind in ("bar", "box", "histogram") and len(categorical) > 1:
        candidate = next((c for c in categorical if c != x), None)
        if candidate and fields[candidate]["distinct"] <= 8:
            group = candidate
    elif kind in ("line", "scatter") and categorical:
        candidate = categorical[0]
        if fields[candidate]["distinct"] <= 8:
            group = candidate
    if group:
        encoding["group"] = group
    return {
        "kind": kind,
        "encoding": encoding,
        "field_types": fields,
        "selection_reason": reason,
        "rejected_alternatives": {
            "pie": "angle and area impede accurate comparison",
            "dual_axis": "separate scales invite spurious magnitude comparisons; facet or normalise explicitly",
            "bar_for_repeated_observations": "raw distributions would be hidden",
        },
    }


def auto_spec(table: dict, question: str = "", overrides: dict | None = None, units: dict | None = None) -> dict:
    recommendation = recommend_encoding(table, question)
    recommendation["encoding"].update({k: v for k, v in (overrides or {}).items()
                                       if v and k in SUPPORTED_CHANNELS})
    kind = (overrides or {}).get("kind") or recommendation["kind"]
    enc = recommendation["encoding"]
    if kind == "histogram":
        enc.pop("y", None)
        enc.pop("value", None)
    elif kind != "heatmap":
        enc.pop("value", None)
    units = units or {}
    spec = {
        "kind": kind,
        "title": (question or "Scientific data visualization").strip()[:180],
        "caption": "Generated from the declared source table; missing values are not coerced to zero.",
        "x_label": enc.get("x"),
        "y_label": enc.get("y") or ("Count" if kind == "histogram" else enc.get("y")),
        "x_unit": units.get(enc.get("x")),
        "y_unit": units.get(enc.get("y")),
        "value_label": enc.get("value"),
        "value_unit": units.get(enc.get("value")),
        "legend": bool(enc.get("group")),
        "panel": "a",
        "value_labels": kind == "bar",
        "encoding": enc,
        "field_types": recommendation["field_types"],
        "_recommendation": {
            "question": question,
            "reason": recommendation["selection_reason"],
            "rejected_alternatives": recommendation["rejected_alternatives"],
            "automatic": True,
        },
    }
    if kind == "histogram":
        spec["bins"] = 10
    return {k: v for k, v in spec.items() if v is not None}


def chart_label_text(spec: dict, table: dict, plan: dict | None) -> str:
    enc = (plan or {}).get("encoding") or {}
    parts = [str(spec.get(k) or "") for k in
             ("title", "caption", "x_label", "y_label", "x_unit", "y_unit", "value_label", "value_unit", "errorbar_meaning")]
    cols = [enc.get("x"), enc.get("group")]
    if (plan or {}).get("kind") == "heatmap":
        cols.append(enc.get("y"))
    seen = []
    for col in cols:
        if not col or col not in table.get("columns", []):
            continue
        for row in table.get("rows", []):
            value = str(row.get(col, ""))
            if value not in seen:
                seen.append(value)
    return "".join(parts) + "".join(seen)


# ---------------------------------------------------------------------------
# Encoding validation
# ---------------------------------------------------------------------------

def plan_encoding(spec: dict, table: dict) -> dict:
    problems = []
    kind = spec.get("kind")
    if kind not in CHART_KINDS:
        return {"ok": False, "plan": None, "problems": [{
            "rule": "encoding.unknown_chart_kind", "kind": kind, "allowed": sorted(CHART_KINDS)}]}
    if not table.get("rows"):
        return {"ok": False, "plan": None, "problems": [{
            "rule": "data.no_rows", "message": "the table has no data rows, so there is nothing to draw"}]}

    enc = spec.get("encoding") or {}
    if not isinstance(enc, dict):
        return {"ok": False, "plan": None, "problems": [{
            "rule": "input.encoding_not_object", "message": "encoding must be an object of channel-to-column mappings"}]}
    if any(key in spec for key in ("y2", "secondary_y", "right_y", "twinx")) or any(key in enc for key in ("y2", "secondary_y")):
        problems.append({"rule": "encoding.dual_axis_unsupported",
                         "message": "a second quantitative axis can imply spurious magnitudes; facet or explicitly normalise instead"})
    for channel in enc:
        if channel not in SUPPORTED_CHANNELS:
            problems.append({"rule": "encoding.unsupported_channel", "channel": channel,
                             "supported": sorted(SUPPORTED_CHANNELS)})
    for channel in REQUIRED[kind]:
        if not enc.get(channel):
            problems.append({"rule": "encoding.required_channel_unmapped", "channel": channel,
                             "chart_kind": kind, "message": f"a {kind} chart must map '{channel}'"})

    numeric_channels = {"value", *UNCERTAINTY_CHANNELS}
    if kind == "histogram":
        numeric_channels.add("x")
    elif kind != "heatmap":
        numeric_channels.add("y")
    if kind in ("line", "scatter"):
        numeric_channels.add("x")
    for channel, column in enc.items():
        if not column or channel not in SUPPORTED_CHANNELS:
            continue
        if not isinstance(column, str) or column not in table["columns"]:
            problems.append({"rule": "encoding.column_missing", "channel": channel, "column": column,
                             "available": table["columns"]})
        elif channel in numeric_channels and not is_numeric(table, column):
            temporal_x = kind == "line" and channel == "x" and (
                infer_field_types(table).get(column, {}).get("type") == "temporal")
            if not temporal_x:
                problems.append({"rule": "encoding.not_numeric", "channel": channel, "column": column,
                                 "message": f"'{column}' has non-numeric, non-missing values"})
    if kind == "heatmap" and enc.get("group"):
        problems.append({"rule": "encoding.unsupported_channel_for_kind", "channel": "group", "chart_kind": kind})
    if kind != "heatmap" and enc.get("value"):
        problems.append({"rule": "encoding.unsupported_channel_for_kind", "channel": "value", "chart_kind": kind})
    if kind == "histogram" and enc.get("y"):
        problems.append({"rule": "encoding.unsupported_channel_for_kind", "channel": "y", "chart_kind": kind})
    for channel in ("x_err", "x_err2"):
        if kind not in ("line", "scatter") and enc.get(channel):
            problems.append({"rule": "encoding.unsupported_channel_for_kind", "channel": channel, "chart_kind": kind})
    for channel in ("y_err", "y_err2"):
        if kind in ("box", "heatmap", "histogram") and enc.get(channel):
            problems.append({"rule": "encoding.unsupported_channel_for_kind", "channel": channel, "chart_kind": kind})
    for channel in ("y_lower", "y_upper"):
        if kind != "line" and enc.get(channel):
            problems.append({"rule": "encoding.unsupported_channel_for_kind", "channel": channel, "chart_kind": kind,
                             "message": "absolute interval endpoints form a layered line errorband"})
    if bool(enc.get("y_lower")) != bool(enc.get("y_upper")):
        problems.append({"rule": "encoding.incomplete_interval", "channels": ["y_lower", "y_upper"],
                         "message": "both absolute lower and upper source columns are required for an errorband"})
    for primary, secondary in (("x_err", "x_err2"), ("y_err", "y_err2")):
        if enc.get(secondary) and not enc.get(primary):
            problems.append({"rule": "encoding.incomplete_interval", "channels": [secondary, primary],
                             "message": "an asymmetric secondary error column requires its primary upper error column"})

    # Ambiguous duplicate cells/bars would otherwise be overplotted and silently lost.
    if kind in ("bar", "heatmap") and not problems:
        keys = []
        for index, row in enumerate(table["rows"]):
            key = [str(row.get(enc.get("x")))]
            if kind == "heatmap":
                key.append(str(row.get(enc.get("y"))))
            if enc.get("group"):
                key.append(str(row.get(enc.get("group"))))
            keys.append((tuple(key), index))
        seen = {}
        for key, index in keys:
            seen.setdefault(key, []).append(index)
        duplicates = {key: rows for key, rows in seen.items() if len(rows) > 1}
        if duplicates:
            problems.append({"rule": "data.duplicate_marks", "chart_kind": kind,
                             "message": "duplicate category/series keys would overlap; aggregate explicitly or choose box/scatter",
                             "examples": [{"key": key, "rows": rows}
                                          for key, rows in list(duplicates.items())[:10]]})
    return {"ok": not problems, "problems": problems,
            "plan": None if problems else {"kind": kind, "encoding": enc,
                                           "n": table["n"], "columns": table["columns"]}}


# ---------------------------------------------------------------------------
# Render
# ---------------------------------------------------------------------------

def _geometry(spec: dict) -> tuple[tuple[float, float], int]:
    figsize = (4.2, 3.2)
    value = spec.get("figsize")
    if isinstance(value, (list, tuple)) and len(value) == 2:
        try:
            candidate = (float(value[0]), float(value[1]))
            if all(1.5 <= v <= 30 for v in candidate):
                figsize = candidate
        except (TypeError, ValueError):
            pass
    export = spec.get("export") or {}
    if isinstance(export, dict) and export.get("width_mm") is not None:
        try:
            width_in = float(export["width_mm"]) / 25.4
            if 1.5 <= width_in <= 30:
                figsize = (width_in, figsize[1])
        except (TypeError, ValueError):
            pass
    try:
        dpi = int(spec.get("dpi", 300))
        if dpi <= 0 or dpi > 1200:
            dpi = 300
    except (TypeError, ValueError):
        dpi = 300
    return figsize, dpi


def observation_counts(spec: dict, table: dict) -> dict:
    """Observable counts are not silently relabelled as biological replicates."""
    enc = spec.get("encoding") or {}
    counts = {}
    if enc.get("group") and enc["group"] in table.get("columns", []):
        for row in table["rows"]:
            key = str(row.get(enc["group"]))
            counts[key] = counts.get(key, 0) + 1
    return {"total_source_rows": table["n"], "by_series": counts,
            "declared_n": spec.get("caption_n"),
            "replication_unit": spec.get("n_semantics") or "not declared; source rows are observations, not assumed independent n"}


def _caption(spec: dict, table: dict) -> str:
    parts = []
    if str(spec.get("caption") or "").strip():
        parts.append(str(spec["caption"]).strip())
    if spec.get("caption_n") is not None:
        semantics = f" ({spec['n_semantics']})" if spec.get("n_semantics") else ""
        parts.append(f"Declared sample size n = {spec['caption_n']}{semantics}")
    else:
        parts.append(f"Source rows = {table['n']} (not assumed to be independent n)")
    counts = observation_counts(spec, table)["by_series"]
    if counts:
        parts.append("Source observations by series: " + ", ".join(f"{key}={value}" for key, value in counts.items()))
    if any((spec.get("encoding") or {}).get(channel) for channel in UNCERTAINTY_CHANNELS):
        parts.append(f"Uncertainty = {spec.get('errorbar_meaning') or 'UNDEFINED'} (pre-aggregated source values)")
    return " | ".join(parts)


def _svg_description(path: Path, title: str, description: str) -> None:
    """Embed a real SVG title/description and ARIA label, not just a JSON claim."""
    text = path.read_text(encoding="utf-8")
    match = re.search(r"<svg\b[^>]*>", text, flags=re.S)
    if not match:
        return
    opening = match.group(0)
    if "role=" not in opening:
        opening = opening[:-1] + ' role="img">'
    accessible = f"<title>{escape(title)}</title><desc>{escape(description)}</desc>"
    text = text[:match.start()] + opening + accessible + text[match.end():]
    # Matplotlib uses random-looking definition/clip ids. Canonicalise ids in
    # first-definition order and update every reference, preserving geometry
    # and editability while making SVG files deterministic across processes.
    generated = []
    for found in re.finditer(r'\bid="([mph][0-9a-f]{10})"', text):
        if found.group(1) not in generated:
            generated.append(found.group(1))
    for index, old in enumerate(generated, 1):
        new = f"sourcechart_def_{index:04d}"
        text = re.sub(rf'\bid="{re.escape(old)}"', f'id="{new}"', text)
        text = text.replace(f"#{old}", f"#{new}")
    path.write_text(text, encoding="utf-8")


def render_chart(spec: dict, table: dict, plan: dict, out_stem: Path,
                 dpi: int = 300, fonttype: str = "none") -> dict:
    matplotlib.rcParams["svg.fonttype"] = fonttype
    enc, kind, rows = plan["encoding"], plan["kind"], table["rows"]
    font = FS.resolve(chart_label_text(spec, table, plan))
    if font.family and font.family != "<none>":
        matplotlib.rcParams["font.family"] = "sans-serif"
        matplotlib.rcParams["font.sans-serif"] = [font.family, "DejaVu Sans"]
    figsize, dpi = _geometry(spec)
    fig, ax = plt.subplots(figsize=figsize)
    mark_rows = []
    aggregates = []

    groups = [None]
    if enc.get("group"):
        groups = []
        for row in rows:
            value = row.get(enc["group"])
            if value not in groups:
                groups.append(value)
    categories = []
    if kind in ("bar", "box"):
        for row in rows:
            value = str(row.get(enc["x"]))
            if value not in categories:
                categories.append(value)

    if kind in ("bar", "box"):
        lookup = {}
        for index, row in enumerate(rows):
            group = row.get(enc["group"]) if enc.get("group") else None
            lookup[(group, str(row.get(enc["x"])))] = index
        group_n = len(groups)
        width = 0.82 / max(1, group_n)
        labelled = set()
        for gi, group in enumerate(groups):
            colour = OKABE_ITO[gi % len(OKABE_ITO)]
            for ci, category in enumerate(categories):
                if kind == "bar":
                    index = lookup.get((group, category))
                    if index is None:
                        continue
                    row = rows[index]
                    y = _as_float(row.get(enc["y"]))
                    error = _as_float(row.get(enc["y_err"])) if enc.get("y_err") else None
                    error2 = _as_float(row.get(enc["y_err2"])) if enc.get("y_err2") else None
                    if enc.get("y_err2"):
                        # Asymmetric interval follows Vega-Lite's layered errorbar:
                        # lower magnitude, then upper magnitude, all from source rows.
                        bar_error = [[np.nan if error2 is None else error2],
                                     [np.nan if error is None else error]]
                    elif enc.get("y_err"):
                        bar_error = [np.nan if error is None else error]
                    else:
                        bar_error = None
                    position = ci + (gi - (group_n - 1) / 2) * width
                    series_label = str(group) if group is not None and group not in labelled else None
                    container = ax.bar([position], [np.nan if y is None else y], width=width * 0.94,
                                       color=colour, edgecolor="#222222", linewidth=0.45,
                                       hatch=HATCHES[gi % len(HATCHES)] if group_n > 1 else "",
                                       label=series_label, yerr=bar_error,
                                       capsize=3 if bar_error is not None else 0)
                    if series_label is not None:
                        labelled.add(group)
                    if spec.get("value_labels") and y is not None:
                        # Matplotlib grouped-bar gallery pattern: annotate the actual
                        # container value rather than retyping scientific numbers.
                        ax.bar_label(container, labels=[f"{y:g}"], padding=2, fontsize=6.5)
                    patch = container.patches[0]
                    mark_rows.append({
                        "mark": f"bar{len(mark_rows)}", "row": index, "x": category, "y": y,
                        "series": None if group is None else str(group), "y_err": error,
                        "y_err2": error2,
                        "rendered": {"x": float(patch.get_x() + patch.get_width() / 2),
                                     "y": float(patch.get_height()), "width": float(patch.get_width())}})
                else:
                    indices = [i for i, row in enumerate(rows)
                               if str(row.get(enc["x"])) == category
                               and (not enc.get("group") or row.get(enc["group"]) == group)]
                    values = [(i, _as_float(rows[i].get(enc["y"]))) for i in indices]
                    valid = [(i, value) for i, value in values if value is not None]
                    if not valid:
                        continue
                    position = ci + (gi - (group_n - 1) / 2) * width
                    ax.boxplot([value for _, value in valid], positions=[position], widths=width * 0.72,
                               patch_artist=True, showfliers=True,
                               boxprops=dict(facecolor=colour, edgecolor="#222222", alpha=0.55,
                                             hatch=HATCHES[gi % len(HATCHES)] if group_n > 1 else ""),
                               medianprops=dict(color="#111111", linewidth=1.3),
                               whiskerprops=dict(color="#444444"), capprops=dict(color="#444444"))
                    offsets = np.linspace(-width * 0.22, width * 0.22, len(valid)) if len(valid) > 1 else [0.0]
                    series_label = str(group) if group is not None and group not in labelled else None
                    collection = ax.scatter([position + offset for offset in offsets], [value for _, value in valid],
                                            s=12, marker=MARKERS[gi % len(MARKERS)], color=colour,
                                            edgecolors="#222222", linewidths=0.3, zorder=3,
                                            label=series_label)
                    if series_label is not None:
                        labelled.add(group)
                    for (index, value), offset, xy in zip(valid, offsets, collection.get_offsets()):
                        mark_rows.append({"mark": f"obs{len(mark_rows)}", "row": index, "x": category,
                                          "y": value, "series": None if group is None else str(group),
                                          "y_err": None,
                                          "rendered": {"x": float(position + offset), "y": float(xy[1])}})
        ax.set_xticks(range(len(categories)))
        ax.set_xticklabels(categories)

    elif kind in ("line", "scatter"):
        for gi, group in enumerate(groups):
            indices = [i for i, row in enumerate(rows)
                       if not enc.get("group") or row.get(enc["group"]) == group]
            temporal_x = kind == "line" and infer_field_types(table).get(enc.get("x"), {}).get("type") == "temporal"
            coordinate = _as_coordinate if temporal_x else _as_float
            if kind == "line":
                indices.sort(key=lambda i: (coordinate(rows[i].get(enc["x"])) is None,
                                            coordinate(rows[i].get(enc["x"])) if coordinate(rows[i].get(enc["x"])) is not None else 0, i))
            xs = [coordinate(rows[i].get(enc["x"])) for i in indices]
            ys = [_as_float(rows[i].get(enc["y"])) for i in indices]
            xe = [_as_float(rows[i].get(enc["x_err"])) for i in indices] if enc.get("x_err") else None
            xe2 = [_as_float(rows[i].get(enc["x_err2"])) for i in indices] if enc.get("x_err2") else None
            ye = [_as_float(rows[i].get(enc["y_err"])) for i in indices] if enc.get("y_err") else None
            ye2 = [_as_float(rows[i].get(enc["y_err2"])) for i in indices] if enc.get("y_err2") else None
            ylo = [_as_float(rows[i].get(enc["y_lower"])) for i in indices] if enc.get("y_lower") else None
            yhi = [_as_float(rows[i].get(enc["y_upper"])) for i in indices] if enc.get("y_upper") else None
            xplot = [np.nan if value is None else value for value in xs]
            yplot = [np.nan if value is None else value for value in ys]
            colour = OKABE_ITO[gi % len(OKABE_ITO)]
            label = None if group is None else str(group)
            if kind == "line" and ylo is not None and yhi is not None:
                # Vega-Lite layer_line_errorband_ci pattern: a real separate
                # interval layer behind the centre line, sourced per row.
                ax.fill_between(xplot,
                                [np.nan if value is None else value for value in ylo],
                                [np.nan if value is None else value for value in yhi],
                                color=colour, alpha=0.18, linewidth=0, zorder=1)
            if kind == "line":
                artist = ax.plot(xplot, yplot, color=colour, label=label, linewidth=1.4,
                                 linestyle=DASHES[gi % len(DASHES)], marker=MARKERS[gi % len(MARKERS)],
                                 markersize=3.5, markeredgecolor="#222222", markeredgewidth=0.3, zorder=3)[0]
                xydata = artist.get_xydata()
                rendered = {i: {"x": float(xy[0]), "y": float(xy[1])}
                            for i, xy in zip(indices, xydata) if np.isfinite(xy[0]) and np.isfinite(xy[1])}
            else:
                valid_positions = [j for j, (x, y) in enumerate(zip(xs, ys)) if x is not None and y is not None]
                collection = ax.scatter([xs[j] for j in valid_positions], [ys[j] for j in valid_positions],
                                        color=colour, s=25, label=label, zorder=3,
                                        marker=MARKERS[gi % len(MARKERS)], edgecolors="#222222", linewidths=0.35)
                rendered = {indices[j]: {"x": float(xy[0]), "y": float(xy[1])}
                            for j, xy in zip(valid_positions, collection.get_offsets())}
            nanify = lambda values: None if values is None else [np.nan if value is None else value for value in values]
            xerr = ([nanify(xe2), nanify(xe)] if xe2 is not None else nanify(xe))
            yerr = ([nanify(ye2), nanify(ye)] if ye2 is not None else nanify(ye))
            if xerr is not None or yerr is not None:
                ax.errorbar(xplot, yplot, xerr=xerr, yerr=yerr,
                            fmt="none", ecolor=colour, capsize=3, elinewidth=0.8, zorder=2)
            for j, (i, x, y) in enumerate(zip(indices, xs, ys)):
                mark_rows.append({"mark": f"pt{i}", "row": i, "x": x, "y": y,
                                  "series": label,
                                  "x_err": xe[j] if xe is not None else None,
                                  "x_err2": xe2[j] if xe2 is not None else None,
                                  "y_err": ye[j] if ye is not None else None,
                                  "y_err2": ye2[j] if ye2 is not None else None,
                                  "y_lower": ylo[j] if ylo is not None else None,
                                  "y_upper": yhi[j] if yhi is not None else None,
                                  "rendered": rendered.get(i)})

    elif kind == "heatmap":
        grid, indices = {}, {}
        for index, row in enumerate(rows):
            gx, gy = str(row.get(enc["x"])), str(row.get(enc["y"]))
            grid[(gy, gx)] = _as_float(row.get(enc["value"]))
            indices[(gy, gx)] = index
        xs_axis = list(dict.fromkeys(str(row.get(enc["x"])) for row in rows))
        ys_axis = list(dict.fromkeys(str(row.get(enc["y"])) for row in rows))
        matrix = np.array([[grid.get((y, x), np.nan) for x in xs_axis] for y in ys_axis], dtype=float)
        color_range = spec.get("color_range")
        vmin = vmax = None
        if isinstance(color_range, (list, tuple)) and len(color_range) == 2:
            try:
                vmin, vmax = float(color_range[0]), float(color_range[1])
            except (TypeError, ValueError):
                pass
        image = ax.imshow(matrix, aspect="auto", cmap="viridis", vmin=vmin, vmax=vmax)
        ax.set_xticks(range(len(xs_axis)))
        ax.set_xticklabels(xs_axis)
        ax.set_yticks(range(len(ys_axis)))
        ax.set_yticklabels(ys_axis)
        value_label = spec.get("value_label") or enc.get("value")
        if spec.get("value_unit"):
            value_label = f"{value_label} ({spec['value_unit']})"
        fig.colorbar(image, ax=ax, label=value_label)
        for yi, y in enumerate(ys_axis):
            for xi, x in enumerate(xs_axis):
                index = indices.get((y, x))
                if index is None:
                    continue
                value = grid[(y, x)]
                mark_rows.append({"mark": f"cell{index}", "row": index, "x": x, "y": y,
                                  "value": value, "series": None, "y_err": None,
                                  "rendered": {"grid_x": xi, "grid_y": yi,
                                               "value": float(image.get_array()[yi, xi])}})

    elif kind == "histogram":
        all_values = [_as_float(row.get(enc["x"])) for row in rows]
        finite = [value for value in all_values if value is not None]
        declared_edges = spec.get("bin_edges")
        if isinstance(declared_edges, list) and len(declared_edges) >= 2:
            edges = np.array([float(value) for value in declared_edges], dtype=float)
            if not np.all(np.diff(edges) > 0):
                raise ValueError("bin_edges must be strictly increasing")
        else:
            try:
                bins = int(spec.get("bins", 10))
                bins = min(100, max(1, bins))
            except (TypeError, ValueError):
                bins = 10
            edges = np.histogram_bin_edges(finite, bins=bins)
        for gi, group in enumerate(groups):
            idx = [i for i, row in enumerate(rows) if not enc.get("group") or row.get(enc["group"]) == group]
            values = [all_values[i] for i in idx if all_values[i] is not None]
            counts, actual_edges = np.histogram(values, bins=edges)
            colour = OKABE_ITO[gi % len(OKABE_ITO)]
            label = None if group is None else str(group)
            ax.hist(values, bins=actual_edges, histtype="step", linewidth=1.5,
                    linestyle=DASHES[gi % len(DASHES)], color=colour, label=label)
            for bin_index, count in enumerate(counts):
                member_rows = [i for i in idx if all_values[i] is not None
                               and actual_edges[bin_index] <= all_values[i] <= actual_edges[bin_index + 1]
                               and (bin_index == len(counts) - 1 or all_values[i] < actual_edges[bin_index + 1])]
                aggregates.append({"series": label, "bin": bin_index,
                                   "left": float(actual_edges[bin_index]), "right": float(actual_edges[bin_index + 1]),
                                   "count": int(count), "rows": member_rows})
            for i in idx:
                value = all_values[i]
                bin_index = None if value is None else int(np.searchsorted(actual_edges, value, side="right") - 1)
                if bin_index is not None:
                    bin_index = min(len(counts) - 1, max(0, bin_index))
                mark_rows.append({"mark": f"obs{i}", "row": i, "x": value, "series": label,
                                  "bin": bin_index,
                                  "bin_left": None if bin_index is None else float(actual_edges[bin_index]),
                                  "bin_right": None if bin_index is None else float(actual_edges[bin_index + 1]),
                                  "rendered": None})

    xlabel = spec.get("x_label") or enc.get("x") or ""
    ylabel = spec.get("y_label") or enc.get("y") or ("Count" if kind == "histogram" else "")
    ax.set_xlabel(xlabel + (f" ({spec['x_unit']})" if spec.get("x_unit") else ""))
    ax.set_ylabel(ylabel + (f" ({spec['y_unit']})" if spec.get("y_unit") else ""))
    if kind == "line" and enc.get("x") and not is_numeric(table, enc["x"]) and _temporal_column(table, enc["x"]):
        from matplotlib import dates as mdates
        locator = mdates.AutoDateLocator()
        ax.xaxis.set_major_locator(locator)
        ax.xaxis.set_major_formatter(mdates.ConciseDateFormatter(locator))
    if spec.get("title"):
        ax.set_title(str(spec["title"]), fontsize=10)
    if len(groups) > 1 or (spec.get("legend") and enc.get("group")):
        ax.legend(frameon=False, fontsize=7, title=spec.get("legend_title") or enc.get("group"))
    if kind in ("line", "scatter", "box"):
        ax.grid(axis="y", color="#DDDDDD", linewidth=0.5, zorder=0)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)

    ylim = spec.get("ylim")
    if isinstance(ylim, (list, tuple)) and len(ylim) == 2:
        try:
            ax.set_ylim(float(ylim[0]), float(ylim[1]))
        except (TypeError, ValueError):
            pass
    yscale = str(spec.get("y_scale") or "").strip().lower()
    if yscale in ("log", "symlog", "logit"):
        try:
            ax.set_yscale(yscale)
        except (ValueError, TypeError):
            pass

    caption = _caption(spec, table)
    # The caption uses physical width, not a fixed character count: 115 glyphs
    # at 7 pt can exceed a 3.5-inch journal panel and be clipped on the right.
    wrap_width = max(32, int(figsize[0] * 18))
    wrapped = textwrap.fill(caption, width=wrap_width, break_long_words=False,
                            break_on_hyphens=False) if caption else ""
    lines = wrapped.count("\n") + 1 if wrapped else 0
    if wrapped:
        fig.text(0.01, 0.01, wrapped, fontsize=7, va="bottom", ha="left")
    fig.tight_layout(rect=(0, min(0.35, 0.045 * lines + 0.02) if lines else 0, 1, 1))

    out_stem = Path(out_stem)
    out_stem.parent.mkdir(parents=True, exist_ok=True)
    svg, png, pdf = out_stem.with_suffix(".svg"), out_stem.with_suffix(".png"), out_stem.with_suffix(".pdf")
    # Remove wall-clock metadata so the same input also reproduces file bytes,
    # rather than merely reproducing a reassuring result.json claim.
    fig.savefig(svg, format="svg", metadata={"Date": None})
    fig.savefig(png, format="png", dpi=dpi, metadata={"Software": ENGINE})
    fig.savefig(pdf, format="pdf", metadata={"CreationDate": None})
    description = str(spec.get("accessibility_description") or
                      f"{kind} chart; x={xlabel}; y={ylabel}; series={enc.get('group') or 'none'}; "
                      f"source rows={table['n']}; uncertainty={spec.get('errorbar_meaning') or 'none'}. {caption}")
    _svg_description(svg, str(spec.get("title") or f"{kind} chart"), description)
    (out_stem.parent / "caption.txt").write_text(caption + "\n", encoding="utf-8")
    return {"fig": fig, "ax": ax, "kind": kind, "mark_rows": mark_rows,
            "aggregates": aggregates, "groups": groups, "dpi": dpi,
            "svg": svg, "png": png, "pdf": pdf,
            "font": {"family": font.family, "path": font.path, "missing": list(font.missing)},
            "xlim": ax.get_xlim(), "ylim": ax.get_ylim(), "description": description}


# ---------------------------------------------------------------------------
# Audit actual artefacts and drawn geometry
# ---------------------------------------------------------------------------

def _png_dpi(path: Path):
    try:
        data = path.read_bytes()
        if not data.startswith(b"\x89PNG\r\n\x1a\n"):
            return None
        offset = 8
        while offset + 12 <= len(data):
            length = struct.unpack(">I", data[offset:offset + 4])[0]
            kind = data[offset + 4:offset + 8]
            if kind == b"pHYs" and length == 9:
                x, y, unit = struct.unpack(">IIB", data[offset + 8:offset + 17])
                if unit == 1:
                    return x * 0.0254, y * 0.0254
            offset += 12 + length
    except (OSError, struct.error):
        pass
    return None


def audit_chart(spec: dict, table: dict, plan: dict, built: dict) -> dict:
    findings = []

    def add(rule, severity, message, **extra):
        findings.append({"rule": rule, "severity": severity, "message": message, **extra})

    enc, kind, rows = plan["encoding"], plan["kind"], table["rows"]
    axes = (("x", "x_label", "x_unit"),) if kind == "histogram" else (("x", "x_label", "x_unit"), ("y", "y_label", "y_unit"))
    for axis_name, label_key, unit_key in axes:
        if not (spec.get(label_key) or enc.get(axis_name)):
            add("axis.x_label_missing" if axis_name == "x" else "axis.y_label_missing", "high",
                f"the {axis_name} axis carries no label")
        if enc.get(axis_name) and is_numeric(table, enc[axis_name]) and not spec.get(unit_key):
            add("axis.x_unit_missing" if axis_name == "x" else "axis.y_unit_missing", "medium",
                f"the {axis_name} axis is numeric but declares no unit")
    if not str(spec.get("title") or "").strip():
        add("annotation.title_missing", "medium", "the chart has no rendered title")
    if kind == "heatmap" and enc.get("value") and not spec.get("value_unit"):
        add("color.unit_missing", "medium", "the numeric colour scale declares no unit")
    if table["n"] < 3:
        add("data.small_sample", "low", "fewer than three source rows limits distribution and uncertainty interpretation",
            rows=table["n"])

    # Required numeric missingness is named; optional blank error cells remain legal.
    for channel in sorted(REQUIRED[kind]):
        column = enc.get(channel)
        if not column or column not in table["columns"]:
            continue
        numeric_required = (channel in ("x", "y") and kind in ("line", "scatter", "histogram")) or channel in ("y", "value")
        if numeric_required:
            missing = [i for i, row in enumerate(rows) if _missing(row.get(column))]
            if missing:
                add("data.missing_numeric", "medium",
                    "missing cells in a required numeric channel are left undrawn, never coerced to zero",
                    channel=channel, column=column, count=len(missing), rows=missing[:50])
    duplicates = len(rows) - len({json.dumps(row, ensure_ascii=False, sort_keys=True, default=str) for row in rows})
    if duplicates:
        add("data.duplicate_rows", "low", "identical source rows are retained and counted, not silently deduplicated",
            count=duplicates)

    if kind != "histogram" and kind != "heatmap":
        for index, row in enumerate(rows):
            y = _as_float(row.get(enc.get("y") or ""))
            if y is None:
                continue
            lo, hi = built["ylim"]
            check_lo = min(lo, 0.0) if kind == "bar" else lo
            if not (min(check_lo, hi) - 1e-9 <= y <= max(check_lo, hi) + 1e-9):
                add("axis.value_clipped", "high", "a data value falls outside the drawn axis range",
                    row=index, value=y, axis="y", axis_range=[check_lo, hi])
                break
    if kind in ("line", "scatter"):
        temporal_x = kind == "line" and infer_field_types(table).get(enc.get("x"), {}).get("type") == "temporal"
        coordinate = _as_coordinate if temporal_x else _as_float
        for index, row in enumerate(rows):
            x = coordinate(row.get(enc.get("x") or ""))
            if x is None:
                continue
            lo, hi = built["xlim"]
            if not (min(lo, hi) - 1e-9 <= x <= max(lo, hi) + 1e-9):
                add("axis.value_clipped", "high", "an x value falls outside the drawn axis range",
                    row=index, value=x, axis="x", axis_range=[lo, hi])
                break

    if enc.get("group"):
        data_groups = {str(row.get(enc["group"])) for row in rows}
        drawn = {str(group) for group in built["groups"] if group is not None}
        if data_groups - drawn:
            add("series.missing_from_chart", "high", "groups present in the data were not drawn",
                missing=sorted(data_groups - drawn))
        legend = built["ax"].get_legend()
        if legend is None:
            add("legend.absent", "medium", "the chart has multiple groups but no legend")
        else:
            texts = [text.get_text() for text in legend.get_texts()]
            expected = [str(group) for group in built["groups"] if group is not None]
            if sorted(texts) != sorted(expected):
                add("legend.series_mismatch", "medium", "legend labels do not match the drawn series",
                    legend=texts, drawn=expected)
    for channel in sorted(UNCERTAINTY_CHANNELS):
        if enc.get(channel) and not any(mark.get(channel) is not None for mark in built["mark_rows"]):
            add("error.column_not_drawn", "high", f"the {channel} channel has no rendered uncertainty", channel=channel)
    if any(enc.get(channel) for channel in UNCERTAINTY_CHANNELS) and not str(spec.get("errorbar_meaning") or "").strip():
        add("annotation.errorbar_meaning_missing", "medium", "uncertainty is drawn without SD/SEM/CI/range semantics",
            channels=sorted(channel for channel in UNCERTAINTY_CHANNELS if enc.get(channel)))
    for index, row in enumerate(rows):
        for channel in ("x_err", "x_err2", "y_err", "y_err2"):
            if not enc.get(channel):
                continue
            value = _as_float(row.get(enc[channel]))
            if value is not None and value < 0:
                add("error.invalid_value", "high", "an error magnitude is negative; use absolute endpoints for directed intervals",
                    row=index, channel=channel, value=value)
        if enc.get("y_lower") and enc.get("y_upper"):
            lower = _as_float(row.get(enc["y_lower"]))
            centre = _as_float(row.get(enc["y"]))
            upper = _as_float(row.get(enc["y_upper"]))
            if lower is not None and upper is not None and centre is not None and not lower <= centre <= upper:
                add("error.invalid_interval", "high", "interval endpoints do not bracket the centre value",
                    row=index, lower=lower, centre=centre, upper=upper)

    untraced = [mark for mark in built["mark_rows"] if "row" not in mark]
    if untraced:
        add("traceability.missing", "high", "marks exist without a source row index", count=len(untraced))
    if len(built["mark_rows"]) < len(rows):
        add("traceability.row_coverage", "medium", "fewer mark records than source rows",
            rows=len(rows), marks=len(built["mark_rows"]))

    # Reconcile actual artist geometry, including dodged bar centres and values.
    for mark in built["mark_rows"]:
        if kind == "histogram":
            continue
        rendered = mark.get("rendered")
        if rendered is None:
            if mark.get("y") is not None or (kind == "heatmap" and mark.get("value") is not None):
                add("encoding.drawn_value_mismatch", "high", "a non-missing source value has no rendered geometry",
                    row=mark.get("row"), mark=mark.get("mark"))
            continue
        comparisons = [("y", "y")]
        if kind == "heatmap":
            comparisons = [("value", "value")]
        elif kind in ("line", "scatter") and mark.get("x") is not None:
            comparisons.append(("x", "x"))
        for source_key, rendered_key in comparisons:
            source_value = mark.get(source_key)
            drawn_value = rendered.get(rendered_key)
            if source_value is None or drawn_value is None:
                continue
            try:
                if abs(float(source_value) - float(drawn_value)) > 1e-8 * max(1.0, abs(float(source_value))):
                    add("encoding.drawn_value_mismatch", "high", "rendered geometry disagrees with the source value",
                        row=mark.get("row"), mark=mark.get("mark"), channel=source_key,
                        expected=source_value, drawn=drawn_value)
                    break
            except (TypeError, ValueError):
                pass

    cap_n = spec.get("caption_n")
    if cap_n is not None:
        n_col = next((c for c in table["columns"] if c.strip().lower() in ("n", "sample_size", "samples", "n_obs")), None)
        try:
            cap_i = int(cap_n)
        except (TypeError, ValueError):
            cap_i = None
        if cap_i is None:
            add("caption.n_mismatch", "high", "the declared sample size is not numeric", caption_n=repr(cap_n))
        else:
            if n_col:
                values = [v for v in numeric_column(table, n_col) if v is not None]
                ok = cap_i in {int(v) for v in values} or cap_i == int(sum(values))
                detail = {"caption_n": cap_i, "n_column": n_col,
                          "distinct_n": sorted({int(v) for v in values}), "n_total": int(sum(values))}
            else:
                ok = cap_i == table["n"]
                detail = {"caption_n": cap_i, "table_rows": table["n"]}
            if not ok:
                add("caption.n_mismatch", "high", "the caption sample size is unsupported by the source", **detail)

    for annotation in spec.get("significance") or []:
        if not isinstance(annotation, dict):
            continue
        a, b = (annotation.get("between") or [None, None])[:2]
        present = {str(row.get(enc.get("group"))) for row in rows} if enc.get("group") else set()
        if enc.get("group") and not {str(a), str(b)} <= present:
            add("annotation.unknown_comparison", "high", "a significance comparison names absent groups",
                between=[a, b], groups=sorted(present))

    # Caption bounds are measured on the actual rendered canvas. Valid caption
    # text does not imply it survived the physical journal panel width.
    built["fig"].canvas.draw()
    renderer = built["fig"].canvas.get_renderer()
    for index, text in enumerate(built["fig"].texts):
        if not text.get_text().strip():
            continue
        box = text.get_window_extent(renderer=renderer)
        canvas = built["fig"].bbox
        if (box.x0 < canvas.x0 - 1 or box.x1 > canvas.x1 + 1
                or box.y0 < canvas.y0 - 1 or box.y1 > canvas.y1 + 1):
            add("layout.caption_outside_canvas", "high", "the rendered caption is clipped by the physical canvas",
                caption_index=index,
                bounds_px=[round(box.x0, 1), round(box.y0, 1), round(box.x1, 1), round(box.y1, 1)],
                canvas_px=[round(canvas.x1, 1), round(canvas.y1, 1)])

    for artifact, minimum in ((built["svg"], 500), (built["png"], 1000), (built["pdf"], 500)):
        try:
            if artifact.stat().st_size < minimum:
                add("export.empty_artifact", "high", "an exported artefact is absent or unexpectedly empty",
                    path=str(artifact), minimum_bytes=minimum)
        except OSError:
            add("export.empty_artifact", "high", "an exported artefact cannot be read", path=str(artifact))
    svg_text = built["svg"].read_text(encoding="utf-8", errors="replace")
    try:
        svg_root = ET.fromstring(svg_text)
        element_names = [element.tag.rsplit("}", 1)[-1] for element in svg_root.iter()]
        if svg_root.tag.rsplit("}", 1)[-1] != "svg":
            add("export.svg_invalid", "high", "the editable root element is not SVG")
        if "text" not in element_names:
            add("export.no_live_text", "high", "the SVG labels are outlines rather than editable text")
        if "title" not in element_names or "desc" not in element_names:
            add("export.accessibility_description_missing", "medium", "the SVG lacks an embedded title/description")
    except ET.ParseError as exc:
        add("export.svg_invalid", "high", "the editable SVG is not well-formed XML", error=str(exc))
    if not built["png"].read_bytes().startswith(b"\x89PNG\r\n\x1a\n"):
        add("export.png_invalid", "high", "the raster preview is not a valid PNG stream")
    if not built["pdf"].read_bytes().startswith(b"%PDF"):
        add("export.pdf_invalid", "high", "the PDF export is invalid")
    if built["dpi"] < 300:
        add("export.low_dpi", "medium", f"raster preview at {built['dpi']} dpi; 300+ expected")
    physical = _png_dpi(built["png"])
    if physical and min(physical) < 299:
        add("export.png_dpi_mismatch", "medium", "the PNG pHYs chunk declares less than 300 dpi",
            png_dpi=[round(value, 2) for value in physical])
    export = spec.get("export") or {}
    if isinstance(export, dict) and export.get("width_mm") is not None:
        try:
            expected_width = float(export["width_mm"])
            tolerance = float(export.get("tolerance_mm", 2.0))
            actual_width = float(built["fig"].get_size_inches()[0]) * 25.4
            if abs(actual_width - expected_width) > tolerance:
                add("export.width_out_of_band", "medium", "the actual canvas misses the declared column width",
                    declared_mm=expected_width, actual_mm=round(actual_width, 2), tolerance_mm=tolerance)
        except (TypeError, ValueError):
            add("export.width_invalid", "medium", "the declared export width is not numeric")

    font_info = built.get("font") or {}
    if font_info.get("path") is None:
        add("font.unresolved", "medium", "no readable font file was found")
    elif font_info.get("missing"):
        add("font.glyph_missing", "medium", "a drawn label contains unsupported glyphs",
            family=font_info.get("family"), missing=font_info.get("missing"))

    if kind == "bar":
        xcol = enc.get("x")
        if xcol in table["columns"]:
            values = [v for v in numeric_column(table, xcol) if v is not None]
            yearlike = len(values) >= 4 and all(float(v).is_integer() and 1500 <= v <= 2999 for v in values)
            if _temporal_column(table, xcol) or yearlike:
                add("encoding.time_as_bars", "medium", "a time-like x field is drawn as disconnected bars", x=xcol)
        if xcol in table["columns"] and not is_numeric(table, xcol):
            distinct = len({str(row.get(xcol)) for row in rows})
            if distinct > 12:
                add("read.too_many_categories", "medium", "more than twelve categories share one axis", categories=distinct)
    if len(built.get("groups") or []) > 8:
        add("read.too_many_categories", "medium", "more than eight series force palette reuse", series=len(built["groups"]))

    ylim = spec.get("ylim")
    if kind == "bar" and isinstance(ylim, (list, tuple)) and len(ylim) == 2:
        try:
            baseline = float(ylim[0])
            if baseline > 0:
                add("axis.truncated_baseline", "high", "bar lengths start above zero and exaggerate differences", baseline=baseline)
        except (TypeError, ValueError):
            pass
    if str(spec.get("y_scale") or "").strip().lower() in ("log", "symlog", "logit"):
        values = [v for v in numeric_column(table, enc.get("y") or "") if v is not None]
        bad = [v for v in values if v <= 0]
        if bad:
            add("axis.log_nonpositive", "medium", "a log scale cannot show non-positive values", nonpositive=len(bad))
    if kind == "heatmap":
        values = [v for v in numeric_column(table, enc.get("value") or "") if v is not None]
        color_range = spec.get("color_range")
        if not color_range:
            add("color.range_undeclared", "medium", "the heatmap declares no colour range")
        elif isinstance(color_range, (list, tuple)) and len(color_range) == 2:
            try:
                lo, hi = float(color_range[0]), float(color_range[1])
                outside = [v for v in values if v < lo or v > hi]
                if outside:
                    add("color.range_clipped", "high", "data values fall outside the colour range", outside=len(outside))
            except (TypeError, ValueError):
                add("color.range_invalid", "medium", "the declared colour range is not numeric")
    if not str(spec.get("panel") or "").strip():
        add("layout.panel_missing", "low", "no panel letter is declared; composites need one")

    counts = {}
    for finding in findings:
        counts[finding["severity"]] = counts.get(finding["severity"], 0) + 1
    mapping_json = json.dumps(built["mark_rows"], ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return {
        "schema_version": SCHEMA,
        "status": "clean" if not findings else "blocked" if counts.get("high") else "review",
        "findings": findings,
        "severity_counts": counts,
        "encoding": {
            "chart_kind": kind, "channels": enc, "rows_in_source": table["n"],
            "marks_drawn": len(built["mark_rows"]),
            "field_types": spec.get("field_types") or infer_field_types(table),
            "selection": spec.get("_recommendation"),
            "group_layout": "dodged with stable category order" if kind in ("bar", "box") else "per-series",
        },
        "artifacts": {"svg": str(built["svg"]), "pdf": str(built["pdf"]), "png": str(built["png"]),
                      "caption": str(built["svg"].parent / "caption.txt")},
        "mark_to_row": built["mark_rows"],
        "mark_to_row_sha256": hashlib.sha256(mapping_json.encode("utf-8")).hexdigest(),
        "sample_size": observation_counts(spec, table),
        "aggregates": built.get("aggregates") or [],
        "accessibility": {
            "palette": "Okabe-Ito",
            "redundant_series_encoding": "colour + shape/dash/hatch + legend text",
            "svg_title_description": True,
            "description": built.get("description"),
            "note": "programmatic encoding checks are not a claim of human visual inspection",
        },
        "limits": [
            "Programmatic geometry and artefact checks do not constitute human visual inspection or validate the scientific hypothesis.",
            "Significance declarations are checked for valid groups but are not drawn as brackets.",
        ] if spec.get("significance") else [
            "Programmatic geometry and artefact checks do not constitute human visual inspection or validate the scientific hypothesis."
        ],
    }


# ---------------------------------------------------------------------------
# Contract, provenance and public API
# ---------------------------------------------------------------------------

_BULKY = ("output_contract", "rows", "data", "documents", "text", "manuscript_text", "spec")


def _contract_keys(contract) -> tuple[list[str], list[str]]:
    limits = []
    if contract is None:
        return [], limits
    if isinstance(contract, str):
        return [contract], limits
    if isinstance(contract, dict):
        fields = contract.get("fields")
        if fields is None:
            return list(contract), limits
        contract = fields
    if isinstance(contract, dict):
        return list(contract), limits
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
                limits.append(f"output_contract entry has no usable name: {item!r}")
        else:
            limits.append(f"output_contract contains a non-string field: {item!r}")
    return keys, limits


def _echo_contract(spec: dict, result: dict, limits: list) -> None:
    if spec.get("case_id") is not None:
        result["case_id"] = spec["case_id"]
    keys, notes = _contract_keys(spec.get("output_contract"))
    limits.extend(notes)
    for key in keys:
        if key in result:
            continue
        if key in spec and key not in _BULKY:
            result[key] = spec[key]
        else:
            result[key] = None
            limits.append(f"output_contract field '{key}' was not derivable by this audit")


def _undetermined(out_dir: Path, rule: str, message: str, spec: dict | None = None, **extra) -> dict:
    result = {"schema_version": SCHEMA, "status": "undetermined",
              "findings": [{"rule": rule, "severity": "high", "message": message, **extra}],
              "limits": [], "artifacts": {}}
    if isinstance(spec, dict):
        _echo_contract(spec, result, result["limits"])
    else:
        result["case_id"] = None
        result["limits"].append("no readable spec was available for contract passthrough")
    result["limits"].append("the case could not be run as declared; nothing trustworthy was rendered")
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return result


_MAX_LABEL = 240


def clip_spec_labels(spec: dict) -> list[str]:
    clipped = []
    for key, value in list(spec.items()):
        if isinstance(value, str) and len(value) > _MAX_LABEL:
            spec[key] = value[:_MAX_LABEL]
            clipped.append(key)
    return clipped


def _sha256(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _provenance(spec_path: Path, data_path: Path, out_dir: Path, built: dict | None, table: dict) -> dict:
    provenance = {"engine": ENGINE, "matplotlib": matplotlib.__version__ if matplotlib else None,
                  "spec_file": str(spec_path), "spec_sha256": _sha256(spec_path),
                  "data_file": str(data_path), "data_sha256": _sha256(data_path),
                  "rows_in_source": table["n"]}
    if built:
        provenance["font"] = {"family": (built.get("font") or {}).get("family"),
                              "path": (built.get("font") or {}).get("path")}
        provenance["dpi"] = built.get("dpi")
    try:
        if Path(data_path).stat().st_size <= 1_000_000:
            snapshot = out_dir / ("source_snapshot" + Path(data_path).suffix.lower())
            if Path(data_path).resolve() != snapshot.resolve():
                shutil.copyfile(data_path, snapshot)
            provenance["source_snapshot"] = str(snapshot)
        else:
            provenance["source_snapshot"] = None
            provenance["source_snapshot_note"] = "source exceeds 1MB; identified by sha256 only"
    except OSError:
        provenance["source_snapshot"] = None
    return provenance


def _build_and_audit(spec_path: Path, data_path: Path, out_dir: Path) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    try:
        spec = json.loads(spec_path.read_text(encoding="utf-8-sig"))
    except (json.JSONDecodeError, UnicodeDecodeError, OSError, ValueError) as exc:
        return _undetermined(out_dir, "input.spec_unreadable", f"the spec is not readable JSON: {exc}")
    if not isinstance(spec, dict):
        return _undetermined(out_dir, "input.spec_not_object", "the spec is not a JSON object")
    # Backward-compatible field from source-chart/v1, with disagreement refused.
    legacy_meaning = spec.get("error_meaning")
    if legacy_meaning is not None:
        if spec.get("errorbar_meaning") not in (None, legacy_meaning):
            return _undetermined(out_dir, "input.conflicting_uncertainty_semantics",
                                 "error_meaning and errorbar_meaning disagree", spec)
        spec["errorbar_meaning"] = legacy_meaning
    try:
        table = load_table(data_path)
    except (json.JSONDecodeError, UnicodeDecodeError, OSError, ValueError, TypeError, AttributeError) as exc:
        return _undetermined(out_dir, "input.data_unreadable", f"the data table could not be read: {exc}", spec)

    pre_findings = []
    clipped = clip_spec_labels(spec)
    if clipped:
        pre_findings.append({"rule": "input.label_truncated", "severity": "medium",
                             "message": "oversized presentation fields were clipped before rendering",
                             "fields": clipped, "limit": _MAX_LABEL})
    planned = plan_encoding(spec, table)
    if not planned["ok"]:
        result = {"schema_version": SCHEMA, "status": "refused",
                  "findings": [{"severity": "high", **problem} for problem in planned["problems"]],
                  "note": "the encoding was refused rather than approximated",
                  "limits": [], "artifacts": {}}
        _echo_contract(spec, result, result["limits"])
        result["limits"].append("the encoding plan was rejected before rendering")
        (out_dir / "result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        return result
    if _IMPORT_ERROR is not None:
        return _undetermined(out_dir, "dependency.unavailable",
                             f"scientific rendering dependencies are unavailable: {_IMPORT_ERROR}", spec)
    try:
        built = render_chart(spec, table, planned["plan"], out_dir / "figure",
                             dpi=spec.get("dpi", 300), fonttype=spec.get("_fonttype", "none"))
    except Exception as exc:
        return _undetermined(out_dir, "render.failed", f"rendering failed: {type(exc).__name__}: {exc}", spec)

    result = audit_chart(spec, table, planned["plan"], built)
    result["findings"] = pre_findings + result["findings"]
    counts = result.get("severity_counts") or {}
    for finding in pre_findings:
        counts[finding["severity"]] = counts.get(finding["severity"], 0) + 1
    result["severity_counts"] = counts
    if any(finding["severity"] == "high" for finding in pre_findings):
        result["status"] = "blocked"
    result["spec"] = spec
    result["provenance"] = _provenance(spec_path, data_path, out_dir, built, table)
    if result["provenance"].get("source_snapshot"):
        result["artifacts"]["source_snapshot"] = result["provenance"]["source_snapshot"]
    mapping_path = out_dir / "mark_to_row.json"
    mapping_path.write_text(json.dumps({"encoding": result["encoding"], "marks": result["mark_to_row"],
                                       "aggregates": result["aggregates"]}, ensure_ascii=False, indent=2), encoding="utf-8")
    result["artifacts"]["mark_to_row"] = str(mapping_path)
    result["artifacts"]["resolved_spec"] = str(spec_path)
    result["sources"] = [
        {"role": "source_data", "path": str(data_path), "sha256": result["provenance"]["data_sha256"]},
        {"role": "resolved_spec", "path": str(spec_path), "sha256": result["provenance"]["spec_sha256"]},
    ]
    uncertainty = spec.get("uncertainty")
    result["uncertainty"] = uncertainty if isinstance(uncertainty, list) else []
    result["change_records"] = spec.get("change_records") if isinstance(spec.get("change_records"), list) else []
    _echo_contract(spec, result, result["limits"])
    (out_dir / "result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    plt.close(built["fig"])
    return result


def build_and_audit(spec_path: Path, data_path: Path, out_dir: Path) -> dict:
    spec_path, data_path, out_dir = Path(spec_path), Path(data_path), Path(out_dir)
    try:
        return _build_and_audit(spec_path, data_path, out_dir)
    except Exception as exc:  # last-resort structured failure, never a user traceback
        spec = None
        try:
            candidate = json.loads(spec_path.read_text(encoding="utf-8-sig"))
            spec = candidate if isinstance(candidate, dict) else None
        except Exception:
            pass
        return _undetermined(out_dir, "runtime.failed", f"unexpected engine failure: {type(exc).__name__}: {exc}", spec)


EXIT_CODES = {"clean": 0, "review": 3, "blocked": 4, "refused": 5, "undetermined": 5}


def _read_object(path: str | None, label: str) -> dict:
    if not path:
        return {}
    value = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be a JSON object")
    return value


def _merge_edit(base: dict, patch: dict) -> dict:
    """JSON-merge a presentation/encoding edit without touching the source table."""
    merged = json.loads(json.dumps(base, ensure_ascii=False))
    def apply(target: dict, changes: dict, prefix: str = "") -> None:
        for key, value in changes.items():
            path = f"{prefix}.{key}" if prefix else key
            if path in {"data", "data_file", "rows", "source_snapshot"}:
                raise ValueError(f"source-preserving edit cannot replace {path}")
            if isinstance(value, dict) and isinstance(target.get(key), dict):
                apply(target[key], value, path)
            else:
                target[key] = json.loads(json.dumps(value, ensure_ascii=False))
    apply(merged, patch)
    return merged


def _diff_records(before: dict, after: dict) -> list[dict]:
    records = []
    def walk(old, new, path=""):
        if isinstance(old, dict) and isinstance(new, dict):
            for key in sorted(set(old) | set(new)):
                if key == "change_records":
                    continue
                walk(old.get(key), new.get(key), f"{path}.{key}" if path else key)
        elif old != new:
            records.append({"path": path, "before": old, "after": new})
    walk(before, after)
    return records


def _validate_editable_svg(path: str) -> tuple[int, str]:
    svg_path = Path(path)
    root = ET.fromstring(svg_path.read_text(encoding="utf-8-sig"))
    names = [element.tag.rsplit("}", 1)[-1] for element in root.iter()]
    if root.tag.rsplit("}", 1)[-1] != "svg" or "text" not in names:
        raise ValueError("base figure must be well-formed SVG with editable live text")
    return len(names), str(svg_path)


def main(argv: list[str] | None = None) -> int:
    import argparse
    parser = argparse.ArgumentParser(prog="chartguard", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--spec", help="base generation spec; with --edit this is the source spec")
    parser.add_argument("--edit", help="JSON merge patch for a source-preserving chart edit")
    parser.add_argument("--base-figure", help="existing live-text SVG being edited")
    parser.add_argument("--data", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--case")
    parser.add_argument("--task")
    parser.add_argument("--auto", action="store_true")
    parser.add_argument("--question")
    parser.add_argument("--kind", choices=sorted(CHART_KINDS))
    parser.add_argument("--x")
    parser.add_argument("--y")
    parser.add_argument("--group")
    parser.add_argument("--y-err")
    parser.add_argument("--x-err")
    parser.add_argument("--y-lower")
    parser.add_argument("--y-upper")
    parser.add_argument("--units", help="JSON object mapping column names to declared units")
    args = parser.parse_args(argv)
    out_dir = Path(args.out)
    case = {}
    edit_context = None
    try:
        case = _read_object(args.case, "case")
        if not args.spec and not args.auto:
            raise ValueError("provide --spec, or use --auto to infer an explicit encoding")
        if args.edit and not args.spec:
            raise ValueError("source-preserving --edit requires --spec as the base specification")
        if args.base_figure and not args.edit:
            raise ValueError("--base-figure is meaningful only with --edit")
        if args.spec:
            spec = _read_object(args.spec, "spec")
        else:
            table = load_table(Path(args.data))
            question = args.question or ""
            if args.task:
                question = Path(args.task).read_text(encoding="utf-8-sig")
            question = question or str(case.get("question") or case.get("task") or case.get("prompt") or "")
            units = json.loads(args.units) if args.units else case.get("column_units") or case.get("units") or {}
            if not isinstance(units, dict):
                raise ValueError("units must be a JSON object")
            overrides = {"kind": args.kind, "x": args.x, "y": args.y,
                         "group": args.group, "y_err": args.y_err, "x_err": args.x_err,
                         "y_lower": args.y_lower, "y_upper": args.y_upper}
            spec = auto_spec(table, question, overrides, units)
        if args.edit:
            patch = _read_object(args.edit, "edit patch")
            before = json.loads(json.dumps(spec, ensure_ascii=False))
            spec = _merge_edit(spec, patch)
            changes = _diff_records(before, spec)
            spec["change_records"] = changes
            svg_check = _validate_editable_svg(args.base_figure) if args.base_figure else None
            edit_context = {"base_spec": str(args.spec), "base_figure": args.base_figure,
                            "svg_check": svg_check, "changes": changes}
        for key in ("case_id", "output_contract"):
            # The official case is authoritative over a working spec draft.
            if key in case:
                spec[key] = case[key]
        out_dir.mkdir(parents=True, exist_ok=True)
        resolved = out_dir / "resolved_spec.json"
        resolved.write_text(json.dumps(spec, ensure_ascii=False, indent=2), encoding="utf-8")
        result = build_and_audit(resolved, Path(args.data), out_dir)
        if edit_context:
            changes_path = out_dir / "change_records.json"
            changes_path.write_text(json.dumps(edit_context["changes"], ensure_ascii=False, indent=2), encoding="utf-8")
            result["change_records"] = edit_context["changes"]
            result.setdefault("artifacts", {})["change_records"] = str(changes_path)
            result.setdefault("sources", []).append({"role": "base_spec", "path": edit_context["base_spec"]})
            if edit_context["svg_check"]:
                count, source_svg = edit_context["svg_check"]
                result["sources"].append({"role": "base_editable_svg", "path": source_svg, "elements": count})
            (out_dir / "result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception as exc:
        spec = dict(case) if case else None
        result = _undetermined(out_dir, "input.request_invalid",
                               f"the request could not be prepared: {type(exc).__name__}: {exc}", spec)
    print(json.dumps({"status": result["status"], "case_id": result.get("case_id"),
                      "findings": [finding["rule"] for finding in result.get("findings", [])],
                      "marks": len(result.get("mark_to_row") or []),
                      "selection": (result.get("encoding") or {}).get("selection"),
                      "wrote": str(out_dir / "result.json")}, ensure_ascii=False))
    return EXIT_CODES.get(result["status"], 1)


if __name__ == "__main__":
    raise SystemExit(main())
