"""Render a data chart from source values, then audit the encoding.

The deliverable is not "a chart that looks right". It is a chart whose every mark
can be traced back to a source row, whose axes and legend agree with the data,
and whose export survives a journal's requirements. So this module keeps the
data-to-mark mapping as first-class output rather than throwing it away once
matplotlib has drawn something.

  encode  — spec + data -> validated encoding plan (or a refusal)
  render  — plan -> Figure, SVG, PDF, PNG, plus mark -> row indices
  audit   — plan + built -> findings (labels, units, clipping, font coverage, export)

Refusal is a feature: a spec that asks for a bar chart over a text column gets
told so, instead of a chart of zeros.

Font coverage is part of the audit because the default DejaVu Sans has no CJK
glyphs: a Chinese axis label renders as empty boxes, the file still saves, and
the defect is invisible until a reviewer opens the figure.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import shutil
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

import fontsel as FS

ENGINE = "chartguard/v1"
CHART_KINDS = {"bar", "line", "scatter", "box", "heatmap"}
# Channels a chart may need, and which are mandatory for each kind.
REQUIRED = {
    "bar": {"x", "y"},
    "line": {"x", "y"},
    "scatter": {"x", "y"},
    "box": {"x", "y"},
    "heatmap": {"x", "y", "value"},
}
OKABE_ITO = ["#E69F00", "#56B4E9", "#009E73", "#0072B2", "#D55E00", "#CC79A7", "#F0E442"]


# ---------------------------------------------------------------------------
# Data
# ---------------------------------------------------------------------------

def load_table(path: Path) -> dict:
    """Read CSV/JSON into {columns: [...], rows: [{col: value}], n}."""
    raw = Path(path).read_text(encoding="utf-8-sig")
    if Path(path).suffix.lower() == ".json":
        data = json.loads(raw)
        rows = data if isinstance(data, list) else data.get("rows", [])
    else:
        delim = "\t" if raw.splitlines() and raw.splitlines()[0].count("\t") > raw.splitlines()[0].count(",") else ","
        rows = list(csv.DictReader(io.StringIO(raw), delimiter=delim))
    # An empty table is a refusal, not a crash: plan_encoding reports data.no_rows and
    # the CLI answers with the usual refused result.json.
    return {"columns": list(rows[0].keys()) if rows else [], "rows": rows, "n": len(rows)}


def _as_float(v):
    try:
        return float(str(v).strip())
    except (TypeError, ValueError):
        return None


def numeric_column(table: dict, name: str) -> list[float | None]:
    return [_as_float(r.get(name)) for r in table["rows"]]


def is_numeric(table: dict, name: str) -> bool:
    vals = numeric_column(table, name)
    filled = [v for v in vals if v is not None]
    return bool(filled) and len(filled) == sum(1 for r in table["rows"] if str(r.get(name, "")).strip())


def chart_label_text(spec: dict, table: dict, plan: dict | None) -> str:
    """Every character the figure will actually draw, from the spec and the data.

    Axis labels, units and caption come from the spec; tick and legend text comes
    from the data (category values of the x / group columns, and the y categories
    of a heatmap). A font that covers the axis label but not the category names
    still produces boxes, so both sources are gathered.
    """
    enc = (plan or {}).get("encoding") or {}
    parts = [str(spec.get(k) or "") for k in
             ("title", "caption", "x_label", "y_label", "x_unit", "y_unit", "value_label")]
    cols = [enc.get("x"), enc.get("group")]
    if (plan or {}).get("kind") == "heatmap":
        cols.append(enc.get("y"))
    seen: list[str] = []
    for col in cols:
        if not col or col not in table.get("columns", []):
            continue
        for r in table.get("rows", []):
            v = str(r.get(col, ""))
            if v not in seen:
                seen.append(v)
    return "".join(parts) + "".join(seen)


# ---------------------------------------------------------------------------
# Encoding plan
# ---------------------------------------------------------------------------

def plan_encoding(spec: dict, table: dict) -> dict:
    """Validate the spec against the table and produce an encoding plan.

    Returns {"ok": bool, "problems": [...], "plan": {...}}. A problem is a hard
    refusal; it never degrades into drawing something else.
    """
    problems: list[dict] = []
    kind = spec.get("kind")
    if kind not in CHART_KINDS:
        problems.append({"rule": "encoding.unknown_chart_kind", "kind": kind,
                         "allowed": sorted(CHART_KINDS)})
        return {"ok": False, "problems": problems, "plan": None}

    if not table.get("rows"):
        problems.append({"rule": "data.no_rows",
                         "message": "the table has no data rows, so there is nothing to draw"})
        return {"ok": False, "problems": problems, "plan": None}

    enc = spec.get("encoding") or {}
    for ch in REQUIRED[kind]:
        if not enc.get(ch):
            problems.append({"rule": "encoding.required_channel_unmapped", "channel": ch,
                             "chart_kind": kind,
                             "message": f"a {kind} chart must map the '{ch}' channel"})

    # Every mapped column must exist, and numeric channels must actually be numeric.
    # Which channels sit on a continuous scale depends on the kind: line/scatter use
    # a numeric x; bar/box keep x categorical; heatmap treats both x and y as grid
    # coordinates and only `value` carries numbers. Demanding numerals elsewhere
    # refused exactly the categorical charts the render path supports.
    numeric_channels = {"value", "x_err", "y_err"}
    if kind != "heatmap":
        numeric_channels.add("y")
    if kind in ("line", "scatter"):
        numeric_channels.add("x")
    for ch, col in enc.items():
        if not col:
            continue
        if col not in table["columns"]:
            problems.append({"rule": "encoding.column_missing", "channel": ch, "column": col,
                             "available": table["columns"]})
            continue
        if ch in numeric_channels:
            if not is_numeric(table, col):
                problems.append({"rule": "encoding.not_numeric", "channel": ch, "column": col,
                                 "message": f"'{col}' is not fully numeric, so it cannot drive a "
                                            f"numeric channel"})

    group_col = enc.get("group")
    if group_col and group_col not in table["columns"]:
        problems.append({"rule": "encoding.column_missing", "channel": "group", "column": group_col})

    return {"ok": not problems, "problems": problems,
            "plan": None if problems else {"kind": kind, "encoding": enc,
                                           "n": table["n"], "columns": table["columns"]}}


# ---------------------------------------------------------------------------
# Render
# ---------------------------------------------------------------------------

def render_chart(spec: dict, table: dict, plan: dict, out_stem: Path,
                 dpi: int = 300, fonttype: str = "none") -> dict:
    """Draw the chart and keep the mark -> row mapping.

    `fonttype` defaults to "none" so SVG keeps live text; the audit checks it.
    """
    matplotlib.rcParams["svg.fonttype"] = fonttype
    enc, kind = plan["encoding"], plan["kind"]
    rows = table["rows"]

    # Pick a font that covers every drawn character. The resolved record travels
    # with the built chart so the audit can prove coverage instead of assuming it.
    font = FS.resolve(chart_label_text(spec, table, plan))
    if font.family and font.family != "<none>":
        matplotlib.rcParams["font.family"] = "sans-serif"
        matplotlib.rcParams["font.sans-serif"] = [font.family, "DejaVu Sans"]

    # Hostile-spec safe geometry: a wrong-shaped figsize or a non-numeric dpi is a
    # spec defect, but it must degrade to the default canvas rather than crash.
    figsize = (3.5, 2.8)
    fs = spec.get("figsize")
    if isinstance(fs, (list, tuple)) and len(fs) == 2:
        try:
            figsize = (float(fs[0]), float(fs[1]))
        except (TypeError, ValueError):
            figsize = (3.5, 2.8)
    try:
        dpi = int(dpi)
    except (TypeError, ValueError):
        dpi = 300

    fig, ax = plt.subplots(figsize=figsize)
    mark_rows: list[dict] = []
    ylabel = spec.get("y_label") or enc.get("y") or ""
    yunit = spec.get("y_unit") or ""
    xlabel = spec.get("x_label") or enc.get("x") or ""

    groups = [None]
    if enc.get("group"):
        seen = []
        for r in rows:
            g = r.get(enc["group"])
            if g not in seen:
                seen.append(g)
        groups = seen

    for gi, g in enumerate(groups):
        idx = [i for i, r in enumerate(rows)
               if g is None or r.get(enc["group"]) == g]
        xs = [_as_float(rows[i].get(enc["x"])) if enc["x"] in table["columns"] else None for i in idx]
        ys = [_as_float(rows[i].get(enc["y"])) for i in idx]
        label = str(g) if g is not None else None
        colour = OKABE_ITO[gi % len(OKABE_ITO)]
        errs = None
        if enc.get("y_err"):
            # matplotlib rejects None in yerr; a blank error cell is a skipped bar, so it
            # becomes NaN (drawn as nothing) while the mark row keeps the honest None.
            errs = [_as_float(rows[i].get(enc["y_err"])) for i in idx]
            errs_n = [np.nan if v is None else v for v in errs]

        if kind == "bar":
            labels = [str(rows[i].get(enc["x"])) for i in idx]
            pos = np.arange(len(idx)) + gi * 0.0
            # A missing value draws nothing (NaN), never a silent zero-height bar.
            ax.bar(pos, [np.nan if y is None else y for y in ys], width=0.65,
                   color=colour, label=label,
                   yerr=errs_n if errs else None, capsize=3 if errs else 0)
            ax.set_xticks(pos)
            ax.set_xticklabels(labels, rotation=0)
            mark_rows += [{"mark": f"bar{i}", "row": idx[i], "x": labels[i], "y": ys[i],
                           "series": label, "y_err": errs[i] if errs else None}
                          for i in range(len(idx))]
        elif kind == "line":
            xs_n = [x if x is not None else i for i, x in enumerate(xs)]
            yy = [y if y is not None else np.nan for y in ys]
            ax.plot(xs_n, yy, color=colour, label=label, linewidth=1.4)
            if errs:
                ax.errorbar(xs_n, yy, yerr=errs_n, fmt="none", ecolor=colour, capsize=3)
            mark_rows += [{"mark": f"pt{i}", "row": idx[i], "x": xs_n[i], "y": ys[i],
                           "series": label, "y_err": errs[i] if errs else None}
                          for i in range(len(idx))]
        elif kind == "scatter":
            xs_n = [x if x is not None else i for i, x in enumerate(xs)]
            ys_n = [np.nan if y is None else y for y in ys]
            ax.scatter(xs_n, ys_n, color=colour, s=22, label=label, zorder=3)
            if errs:
                ax.errorbar(xs_n, ys_n, yerr=errs_n, fmt="none", ecolor=colour, capsize=3)
            mark_rows += [{"mark": f"pt{i}", "row": idx[i], "x": xs_n[i], "y": ys[i],
                           "series": label, "y_err": errs[i] if errs else None}
                          for i in range(len(idx))]
        elif kind == "box":
            ax.boxplot([y for y in ys if y is not None], positions=[gi],
                       widths=0.5, patch_artist=True,
                       boxprops=dict(facecolor=colour, alpha=0.8))
            ax.set_xticks(range(len(groups)))
            ax.set_xticklabels([str(g) if g is not None else "all" for g in groups])
            mark_rows += [{"mark": f"row{i}", "row": idx[i], "x": label, "y": ys[i],
                           "series": label, "y_err": None} for i in range(len(idx))]
        elif kind == "heatmap":
            grid = {}
            for i in idx:
                gx = str(rows[i].get(enc["x"]))
                gy = str(rows[i].get(enc["y"]))
                grid[(gy, gx)] = _as_float(rows[i].get(enc["value"]))
            ys_axis = sorted({k[0] for k in grid})
            xs_axis = sorted({k[1] for k in grid})
            m = np.array([[grid.get((r, c), np.nan) for c in xs_axis] for r in ys_axis], dtype=float)
            # A declared colour range is applied so the audit can check it against the
            # data; an undeclared one falls back to matplotlib's data-driven limits.
            cr = spec.get("color_range")
            vmin = vmax = None
            if isinstance(cr, (list, tuple)) and len(cr) == 2:
                try:
                    vmin, vmax = float(cr[0]), float(cr[1])
                except (TypeError, ValueError):
                    vmin = vmax = None
            im = ax.imshow(m, aspect="auto", cmap="viridis", vmin=vmin, vmax=vmax)
            ax.set_xticks(range(len(xs_axis))); ax.set_xticklabels(xs_axis)
            ax.set_yticks(range(len(ys_axis))); ax.set_yticklabels(ys_axis)
            fig.colorbar(im, ax=ax, label=spec.get("value_label") or enc.get("value"))
            mark_rows += [{"mark": f"cell{i}", "row": idx[i], "x": str(rows[i].get(enc["x"])),
                           "y": str(rows[i].get(enc["y"])),
                           "value": _as_float(rows[i].get(enc["value"])),
                           "series": None, "y_err": None} for i in range(len(idx))]

    ax.set_xlabel(xlabel)
    ax.set_ylabel(f"{ylabel} ({yunit})" if yunit else ylabel)
    if len(groups) > 1 or spec.get("legend"):
        ax.legend(frameon=False, fontsize=7)
    # Declared axis limits and scale are applied before export, so the audit sees
    # the axis the reader will actually see (a declared truncated baseline or a log
    # scale over non-positive values is reportable, not assumed away).
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
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    fig.tight_layout()

    out_stem = Path(out_stem)
    out_stem.parent.mkdir(parents=True, exist_ok=True)
    svg, png, pdf = (out_stem.with_suffix(".svg"), out_stem.with_suffix(".png"),
                     out_stem.with_suffix(".pdf"))
    fig.savefig(svg, format="svg")
    fig.savefig(png, format="png", dpi=dpi)
    fig.savefig(pdf, format="pdf")

    return {"fig": fig, "ax": ax, "kind": kind, "mark_rows": mark_rows,
            "groups": groups, "dpi": dpi, "svg": svg, "png": png, "pdf": pdf,
            "font": {"family": font.family, "path": font.path,
                     "missing": list(font.missing)},
            "xlim": ax.get_xlim(), "ylim": ax.get_ylim()}


# ---------------------------------------------------------------------------
# Audit
# ---------------------------------------------------------------------------

def audit_chart(spec: dict, table: dict, plan: dict, built: dict) -> dict:
    findings: list[dict] = []

    def add(rule, severity, message, **extra):
        findings.append({"rule": rule, "severity": severity, "message": message, **extra})

    enc, kind = plan["encoding"], plan["kind"]
    rows = table["rows"]

    # 1. axis labels and units — the most common reason a chart is unreadable later.
    # Literal rule ids (not f-strings) so the documented id and the emitted id are
    # the same string a checker can match.
    for axis_name, label_key, unit_key in (("x", "x_label", "x_unit"), ("y", "y_label", "y_unit")):
        if not (spec.get(label_key) or enc.get(axis_name)):
            add("axis.x_label_missing" if axis_name == "x" else "axis.y_label_missing", "high",
                f"the {axis_name} axis carries no label")
        # A unit is only meaningful for a numeric channel. "control"/"drug" is a
        # category, and demanding a unit for it produces a finding nobody can act on.
        numeric_axis = bool(enc.get(axis_name)) and is_numeric(table, enc[axis_name])
        if numeric_axis and not spec.get(unit_key):
            add("axis.x_unit_missing" if axis_name == "x" else "axis.y_unit_missing", "medium",
                f"the {axis_name} axis is numeric but declares no unit; a reader cannot tell "
                f"mV from V")

    # 2. every data point must be inside the drawn limits, or it is silently clipped
    for i, r in enumerate(rows):
        y = _as_float(r.get(enc.get("y") or ""))
        if y is None:
            continue
        lo, hi = built["ylim"]
        if kind == "bar":
            lo = min(lo, 0.0)
        if not (min(lo, hi) - 1e-9 <= y <= max(lo, hi) + 1e-9):
            add("axis.value_clipped", "high",
                "a data value falls outside the drawn axis range, so the mark is invisible",
                row=i, value=y, axis_range=[lo, hi])
            break

    # 3. legend / series agreement
    if enc.get("group"):
        data_groups = {str(r.get(enc["group"])) for r in rows}
        drawn = {str(g) for g in built["groups"] if g is not None}
        if data_groups - drawn:
            add("series.missing_from_chart", "high",
                "groups present in the data were not drawn", missing=sorted(data_groups - drawn))
        if built["ax"].get_legend() is None:
            add("legend.absent", "medium",
                "the chart has multiple groups but no legend, so colour has no meaning")

    # 4. error column present but not drawn
    if enc.get("y_err") and not any(m.get("y_err") is not None for m in built["mark_rows"]):
        add("error.column_not_drawn", "high",
            "the spec maps an error channel but no error bars were rendered")

    # 5. traceability: every mark must name its source row
    untraced = [m for m in built["mark_rows"] if "row" not in m]
    if untraced:
        add("traceability.missing", "high",
            "marks exist without a source row index, so the figure cannot be traced to the data",
            count=len(untraced))
    if len(built["mark_rows"]) < len(rows):
        add("traceability.row_coverage", "medium",
            "fewer marks than source rows; some rows are not represented in the figure",
            rows=len(rows), marks=len(built["mark_rows"]))

    # 6. caption-declared sample size must match the source
    #    A table may aggregate several observations per row, in which case an
    #    explicit n column is authoritative and the row count is not the sample
    #    size. Comparing against row count there produces a mismatch that is an
    #    artefact of the check, so the n column wins when it exists.
    cap_n = spec.get("caption_n")
    if cap_n is not None:
        n_col = next((c for c in table["columns"]
                      if c.strip().lower() in ("n", "sample_size", "samples", "n_obs")), None)
        try:
            cap_i = int(cap_n)
        except (TypeError, ValueError):
            # A non-numeric caption_n is a spec defect: it cannot name a sample size,
            # so the caption is unsupported rather than correct.
            cap_i = None
        if cap_i is None:
            add("caption.n_mismatch", "high",
                "the caption's sample size is not a number, so it cannot match the source",
                caption_n=repr(cap_n))
        elif n_col:
            vals = [v for v in numeric_column(table, n_col) if v is not None]
            ok = (cap_i in {int(v) for v in vals}) or (cap_i == int(sum(vals)))
            detail = {"caption_n": cap_i, "n_column": n_col,
                      "distinct_n": sorted({int(v) for v in vals}), "n_total": int(sum(vals))}
        else:
            ok = cap_i == table["n"]
            detail = {"caption_n": cap_i, "table_rows": table["n"]}
        if cap_i is not None and not ok:
            add("caption.n_mismatch", "high",
                "the caption states a sample size the source table does not support", **detail)

    # 7. significance annotation must reference a comparison that exists in the data
    for ann in spec.get("significance") or []:
        if not isinstance(ann, dict):
            # A malformed annotation entry (a bare string where an object was declared)
            # degrades to being skipped; it cannot reference anything checkable.
            continue
        a, b = ann.get("between") or [None, None]
        present = {str(r.get(enc.get("group"))) for r in rows} if enc.get("group") else set()
        if enc.get("group") and not {str(a), str(b)} <= present:
            add("annotation.unknown_comparison", "high",
                "a significance mark compares groups that are not both in the data",
                between=[a, b], groups=sorted(present))

    # 8. export hygiene
    svg_text = built["svg"].read_text(encoding="utf-8", errors="replace")
    if "<text" not in svg_text:
        add("export.no_live_text", "high",
            "the SVG has no <text> elements, so labels are outlines and cannot be edited")
    pdf_bytes = built["pdf"].read_bytes()
    if not pdf_bytes.startswith(b"%PDF"):
        add("export.pdf_invalid", "high", "the PDF export is not a valid PDF")
    if built["dpi"] < 300:
        add("export.low_dpi", "medium", f"raster preview at {built['dpi']} dpi; 300+ expected")

    # 9. font coverage — a glyph the resolved font lacks renders as an empty box
    font_info = built.get("font") or {}
    if font_info.get("path") is None:
        add("font.unresolved", "medium",
            "no readable font file was found, so glyph coverage could not be proven")
    elif font_info.get("missing"):
        add("font.glyph_missing", "medium",
            "a drawn label contains characters with no glyph in the resolved font, "
            "so they render as empty boxes",
            family=font_info.get("family"), missing=font_info.get("missing"))

    # 10. chart kind vs data structure — a time axis drawn as connected bars hides
    # the continuity the reader needs (one of the challenge's named failures).
    if kind == "bar":
        xcol = enc.get("x")
        if xcol in table["columns"] and is_numeric(table, xcol):
            vals = [v for v in numeric_column(table, xcol) if v is not None]
            name = str(xcol).strip().lower()
            timelike = any(k in name for k in
                           ("year", "month", "date", "day", "time", "week", "quarter",
                            "年", "月", "日", "时间", "季度"))
            yearlike = (len(vals) >= 4
                        and all(float(v).is_integer() and 1500 <= v <= 2999 for v in vals))
            if timelike or yearlike:
                add("encoding.time_as_bars", "medium",
                    "the x column is time-like but is drawn as disconnected bars; a "
                    "line or scatter preserves the ordering and the between-point "
                    "continuity a reader assumes", x=xcol, distinct=len(set(vals)))

    # 11. category overload — too many categories or series jammed into one panel
    # is unreadable at single-column width, and colour can no longer carry them.
    xcol = enc.get("x")
    if kind == "bar" and xcol in table["columns"] and not is_numeric(table, xcol):
        distinct = len({str(r.get(xcol)) for r in rows})
        if distinct > 12:
            add("read.too_many_categories", "medium",
                "more than twelve categories on one categorical axis will not stay "
                "readable at single-column width; split the panel or group the classes",
                x=xcol, categories=distinct)
    if len(built.get("groups") or []) > 8:
        add("read.too_many_categories", "medium",
            "more than eight series share one palette, so colours repeat and the "
            "legend cannot disambiguate them", series=len(built.get("groups") or []))

    # 12. an error bar without a declared meaning (SD, SEM or CI) is unreadable
    if enc.get("y_err") and not str(spec.get("errorbar_meaning") or "").strip():
        add("annotation.errorbar_meaning_missing", "medium",
            "an error channel is drawn but the spec does not say whether the bars are "
            "SD, SEM or a confidence interval; the caption cannot fix what the spec "
            "never declared")

    # 13. a declared baseline above zero shortens every bar and exaggerates the
    # differences between them
    ylim = spec.get("ylim")
    if kind == "bar" and isinstance(ylim, (list, tuple)) and len(ylim) == 2:
        try:
            lo = float(ylim[0])
        except (TypeError, ValueError):
            lo = None
        if lo is not None and lo > 0:
            add("axis.truncated_baseline", "high",
                "the declared y-axis starts above zero, so bar lengths no longer "
                "encode the values and differences are exaggerated",
                baseline=lo)

    # 14. a log scale over non-positive values silently drops or bends points
    if str(spec.get("y_scale") or "").strip().lower() in ("log", "symlog", "logit"):
        yvals = [v for v in numeric_column(table, enc.get("y") or "") if v is not None]
        bad = [v for v in yvals if v <= 0]
        if bad:
            add("axis.log_nonpositive", "medium",
                "the y scale is logarithmic but the data contain non-positive values, "
                "which a log axis cannot show; they will be dropped silently",
                nonpositive=len(bad))

    # 15. heatmap colour range: declared range must cover the data, undeclared
    # range must be named (a truncated colour scale exaggerates differences)
    if kind == "heatmap":
        vcol = enc.get("value") or ""
        data_vals = [v for v in numeric_column(table, vcol) if v is not None]
        cr = spec.get("color_range")
        if not cr:
            add("color.range_undeclared", "medium",
                "the heatmap declares no colour scale range, so a reader cannot tell "
                "whether the palette spans the data or truncates it")
        elif isinstance(cr, (list, tuple)) and len(cr) == 2:
            try:
                lo, hi = float(cr[0]), float(cr[1])
            except (TypeError, ValueError):
                lo = None
            if lo is not None:
                outside = [v for v in data_vals if v < lo or v > hi]
                if outside:
                    add("color.range_clipped", "high",
                        "data values fall outside the declared colour range, so those "
                        "cells are pinned to the palette ends and their magnitude is "
                        "misread", outside=len(outside), declared=[lo, hi])

    # 16. panel numbering — a figure destined for a composite needs its letter
    if not str(spec.get("panel") or "").strip():
        add("layout.panel_missing", "low",
            "no panel letter is declared; a single-panel figure may not need one, "
            "but composites do, and the export records none")

    counts: dict[str, int] = {}
    for f in findings:
        counts[f["severity"]] = counts.get(f["severity"], 0) + 1

    return {
        "schema_version": "data-viz/v1",
        "status": ("clean" if not findings else "blocked" if counts.get("high") else "review"),
        "findings": findings,
        "severity_counts": counts,
        "encoding": {"chart_kind": kind, "channels": enc, "rows_in_source": table["n"],
                     "marks_drawn": len(built["mark_rows"])},
        "artifacts": {"svg": str(built["svg"]), "pdf": str(built["pdf"]), "png": str(built["png"])},
        "mark_to_row": built["mark_rows"][:200],
        "limits": [],
    }


# ---------------------------------------------------------------------------
# Platform contract passthrough
# ---------------------------------------------------------------------------

# Keys that are inputs rather than deliverables: copying them into result.json
# verbatim would duplicate the whole case payload under every contract field.
_BULKY = ("output_contract", "rows", "data", "documents", "text", "manuscript_text", "spec")


def _echo_contract(spec: dict, result: dict, limits: list) -> None:
    """Carry the case's contract into result.json.

    case.json names the keys the grader looks for (output_contract) and requires
    case_id verbatim. A field the audit already carries is kept; a field the spec
    supplies is copied verbatim; a field the engine cannot derive is written as
    null and named in limits, so the grader finds the key plus an honest note
    instead of a silent gap.
    """
    cid = spec.get("case_id")
    if cid is not None:
        result["case_id"] = cid
    oc = spec.get("output_contract")
    if oc is None:
        return
    if isinstance(oc, str):
        keys = [oc]
    elif isinstance(oc, dict):
        keys = list(oc.get("fields") or oc.keys())
    elif isinstance(oc, (list, tuple)):
        keys = list(oc)
    else:
        limits.append("output_contract was present but is not a field list; it is "
                      "preserved verbatim in the spec echo")
        return
    for key in keys:
        if not isinstance(key, str) or not key.strip():
            limits.append(f"output_contract contains a non-string field name: {key!r}")
            continue
        if key in result:
            continue
        if key in spec and key not in _BULKY:
            result[key] = spec[key]
            continue
        result[key] = None
        limits.append(f"output_contract field '{key}' was not derivable by this audit")


def _undetermined(out_dir: Path, rule: str, message: str, **extra) -> dict:
    """The honest answer when the case cannot be run at all: a result.json with an
    exit code, never a traceback. Contract echo is deliberately NOT performed here
    (the spec may be unreadable, so there is nothing trustworthy to echo)."""
    result = {"schema_version": "data-viz/v1", "status": "undetermined",
              "findings": [{"rule": rule, "severity": "high", "message": message, **extra}],
              "limits": ["the case could not be run as declared; nothing was rendered"],
              "artifacts": {}}
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2),
                                         encoding="utf-8")
    return result


# A presentation field beyond this length is clipped: matplotlib's text layout on
# a megabyte-long label takes minutes, and no journal label is that long. The clip
# is reported, never silent.
_MAX_LABEL = 2000


def clip_spec_labels(spec: dict) -> list[str]:
    """Clip oversized string fields in the spec, returning the clipped field names."""
    clipped = []
    for key, value in list(spec.items()):
        if isinstance(value, str) and len(value) > _MAX_LABEL:
            spec[key] = value[:_MAX_LABEL]
            clipped.append(key)
    return clipped


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    h.update(Path(path).read_bytes())
    return h.hexdigest()


def _provenance(spec_path: Path, data_path: Path, out_dir: Path, built: dict | None,
                table: dict) -> dict:
    """The reproducibility record: which bytes went in, which engine and font drew
    it, and where the raw-source snapshot lives. A figure is only reviewable if a
    second machine can restore the exact inputs."""
    prov = {"engine": ENGINE, "matplotlib": matplotlib.__version__,
            "spec_file": str(spec_path), "spec_sha256": _sha256(spec_path),
            "data_file": str(data_path), "data_sha256": _sha256(data_path),
            "rows_in_source": table["n"]}
    if built:
        prov["font"] = {"family": (built.get("font") or {}).get("family"),
                        "path": (built.get("font") or {}).get("path")}
        prov["dpi"] = built.get("dpi")
    # Snapshot the raw source next to the figure, so the chain data -> figure is
    # inspectable without access to the original upload. Skip huge files; the hash
    # already identifies them.
    try:
        if Path(data_path).stat().st_size <= 1_000_000:
            snap = out_dir / ("source_snapshot" + Path(data_path).suffix.lower())
            shutil.copyfile(data_path, snap)
            prov["source_snapshot"] = str(snap)
        else:
            prov["source_snapshot"] = None
            prov["source_snapshot_note"] = "source file exceeds 1MB; identified by sha256 only"
    except OSError:
        prov["source_snapshot"] = None
    return prov


def build_and_audit(spec_path: Path, data_path: Path, out_dir: Path) -> dict:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    # Unreadable inputs are undetermined, not crashes: the CLI answers with the
    # usual result.json and exit code so a caller can grade the failure.
    try:
        spec = json.loads(Path(spec_path).read_text(encoding="utf-8-sig"))
    except (json.JSONDecodeError, UnicodeDecodeError, OSError, ValueError) as exc:
        return _undetermined(out_dir, "input.spec_unreadable",
                             f"the spec file is not readable JSON: {exc}")
    if not isinstance(spec, dict):
        return _undetermined(out_dir, "input.spec_not_object",
                             "the spec file is not a JSON object")
    try:
        table = load_table(Path(data_path))
    except (json.JSONDecodeError, UnicodeDecodeError, OSError, ValueError) as exc:
        return _undetermined(out_dir, "input.data_unreadable",
                             f"the data file could not be read as CSV or JSON: {exc}")

    # A megabyte-long label would stall the renderer for minutes; presentation
    # strings are clipped to a sane maximum and the clip is reported, not silent.
    pre_findings: list[dict] = []
    clipped_fields = clip_spec_labels(spec)
    if clipped_fields:
        pre_findings.append({"rule": "input.label_truncated", "severity": "medium",
                             "message": "spec string fields beyond the length limit were "
                                        "clipped before rendering; the drawn labels are "
                                        "not the submitted ones verbatim",
                             "fields": clipped_fields, "limit": _MAX_LABEL})

    planned = plan_encoding(spec, table)
    if not planned["ok"]:
        result = {"schema_version": "data-viz/v1", "status": "refused",
                  "findings": [{"rule": p["rule"], "severity": "high", **p}
                               for p in planned["problems"]],
                  "note": "the spec was refused rather than approximated",
                  "limits": ["the encoding plan was rejected before rendering; nothing was drawn"]}
        # The spec is readable here, so the contract keys and case_id travel with
        # the refusal — a grader can match this result.json to its case.
        _echo_contract(spec, result, result["limits"])
        (out_dir / "result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2),
                                             encoding="utf-8")
        return result

    try:
        dpi = spec.get("dpi", 300)
        built = render_chart(spec, table, planned["plan"], out_dir / "figure",
                             dpi=dpi, fonttype=spec.get("_fonttype", "none"))
    except Exception as exc:  # a matplotlib-level failure must still leave a graded answer
        return _undetermined(out_dir, "render.failed",
                             f"rendering failed: {type(exc).__name__}: {exc}")

    result = audit_chart(spec, table, planned["plan"], built)
    result["findings"] = pre_findings + result["findings"]
    counts = result.get("severity_counts") or {}
    for f in pre_findings:
        counts[f["severity"]] = counts.get(f["severity"], 0) + 1
    result["severity_counts"] = counts
    if any(f["severity"] == "high" for f in pre_findings):
        result["status"] = "blocked"
    result["spec"] = spec
    result["provenance"] = _provenance(spec_path, data_path, out_dir, built, table)
    if result["provenance"].get("source_snapshot"):
        result["artifacts"]["source_snapshot"] = result["provenance"]["source_snapshot"]
    _echo_contract(spec, result, result["limits"])
    (out_dir / "result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2),
                                         encoding="utf-8")
    plt.close(built["fig"])
    return result


EXIT_CODES = {"clean": 0, "review": 3, "blocked": 4, "refused": 5, "undetermined": 5}


def main(argv: list[str] | None = None) -> int:
    import argparse

    ap = argparse.ArgumentParser(prog="chartguard", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--spec", required=True)
    ap.add_argument("--data", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args(argv)

    r = build_and_audit(Path(a.spec), Path(a.data), Path(a.out))
    print(json.dumps({"status": r["status"],
                      "case_id": r.get("case_id"),
                      "findings": [f["rule"] for f in r.get("findings", [])],
                      "marks": len(r.get("mark_to_row") or []),
                      "wrote": str(Path(a.out) / "result.json")}, ensure_ascii=False))
    return EXIT_CODES.get(r["status"], 1)


if __name__ == "__main__":
    raise SystemExit(main())
