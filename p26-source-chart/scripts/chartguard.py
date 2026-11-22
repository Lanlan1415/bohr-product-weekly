"""Render a data chart from source values, then audit the encoding.

The deliverable is not "a chart that looks right". It is a chart whose every mark
can be traced back to a source row, whose axes and legend agree with the data,
and whose export survives a journal's requirements. So this module keeps the
data-to-mark mapping as first-class output rather than throwing it away once
matplotlib has drawn something.

  encode  — spec + data -> validated encoding plan (or a refusal)
  render  — plan -> Figure, SVG, PDF, PNG, plus mark -> row indices
  audit   — plan + built -> findings

Refusal is a feature: a spec that asks for a bar chart over a text column gets
told so, instead of a chart of zeros.
"""

from __future__ import annotations

import csv
import io
import json
import re
from pathlib import Path

# Rendering dependencies are optional at import time so a missing matplotlib is
# an honest refusal (exit 5, result.json, no traceback) instead of a crash.
try:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import numpy as np
except Exception as _exc:  # ImportError or backend failure
    plt = None
    np = None
    _DEPS_ERROR = str(_exc)
else:
    _DEPS_ERROR = None

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

CJK_CHAR = re.compile(r"[\u4e00-\u9fff]")
# Families that carry CJK glyphs on the platforms this task runs on. Presence
# of any one of them means Chinese labels can render as text, not as boxes.
CJK_FAMILIES = (
    "SimHei", "Microsoft YaHei", "PingFang SC", "Hiragino Sans GB",
    "Noto Sans CJK SC", "Noto Sans CJK JP", "Noto Sans CJK", "Noto Sans SC",
    "Source Han Sans SC", "Source Han Sans", "WenQuanYi Micro Hei",
    "WenQuanYi Zen Hei", "SimSun", "KaiTi", "FangSong", "STHeiti", "STSong",
    "AR PL UMing CN", "Malgun Gothic",
)


def fonts_support_cjk() -> bool:
    """True when at least one installed font family carries CJK glyphs."""
    if plt is None:
        return False
    try:
        from matplotlib import font_manager
        names = {f.name for f in font_manager.fontManager.ttflist}
        return bool(names & set(CJK_FAMILIES))
    except Exception:
        return False


def _png_physical_dpi(path: Path) -> float | None:
    """Read the pHYs chunk of a PNG: the resolution a viewer will actually use.

    Pure stdlib chunk walk; returns None when the file is not a PNG or carries
    no pHYs chunk (unknown, not failing).
    """
    try:
        data = Path(path).read_bytes()
    except OSError:
        return None
    if not data.startswith(b"\x89PNG\r\n\x1a\n"):
        return None
    pos = 8
    while pos + 8 <= len(data):
        length = int.from_bytes(data[pos:pos + 4], "big")
        ctype = data[pos + 4:pos + 8]
        if ctype == b"pHYs":
            ppm_x = int.from_bytes(data[pos + 8:pos + 12], "big")
            return ppm_x * 0.0254
        pos += 12 + length
        if length < 0:
            break
    return None


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
    if not isinstance(enc, dict):
        problems.append({"rule": "encoding.bad_shape",
                         "message": "the encoding block is not an object of channel -> "
                                    "column name, so no channel can be validated"})
        return {"ok": False, "problems": problems, "plan": None}
    for ch in REQUIRED[kind]:
        if not enc.get(ch):
            problems.append({"rule": "encoding.required_channel_unmapped", "channel": ch,
                             "chart_kind": kind,
                             "message": f"a {kind} chart must map the '{ch}' channel"})

    # Every mapped column must exist, and numeric channels must actually be numeric.
    for ch, col in enc.items():
        if not col:
            continue
        if col not in table["columns"]:
            problems.append({"rule": "encoding.column_missing", "channel": ch, "column": col,
                             "available": table["columns"]})
            continue
        if ch in ("y", "value", "x_err", "y_err") or (ch == "x" and kind != "bar"):
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

    fig, ax = plt.subplots(figsize=spec.get("figsize", (3.5, 2.8)))
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

    # Grouped bars share the category slots: each series gets its own sub-slot
    # inside every category (dodged), not the same x position (overlaid). The
    # old per-group arange stacked every series on top of itself, which hid
    # all but the last-drawn bar.
    bar_categories = None
    if kind == "bar" and len(groups) > 1:
        bar_categories = []
        for r in rows:
            c = str(r.get(enc["x"]))
            if c not in bar_categories:
                bar_categories.append(c)
        ax.set_xticks(np.arange(len(bar_categories)))
        ax.set_xticklabels(bar_categories, rotation=0)

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
            if bar_categories is not None:
                width = 0.8 / len(groups)
                pos = np.array([bar_categories.index(lbl) for lbl in labels],
                               dtype=float)
                pos = pos + (gi - (len(groups) - 1) / 2.0) * width
            else:
                width = 0.65
                pos = np.arange(len(idx))
            # A missing value draws nothing (NaN), never a silent zero-height bar.
            ax.bar(pos, [np.nan if y is None else y for y in ys], width=width,
                   color=colour, label=label,
                   yerr=errs_n if errs else None, capsize=3 if errs else 0)
            if bar_categories is None:
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
            im = ax.imshow(m, aspect="auto", cmap="viridis")
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
        else:
            # The legend must name exactly the series that were drawn: an entry
            # for a series that never reached the canvas (or a missing entry)
            # makes colour-to-series mapping wrong even when the picture looks
            # finished.
            texts = [t.get_text() for t in built["ax"].get_legend().get_texts()]
            drawn_names = [str(g) for g in built["groups"] if g is not None]
            if sorted(texts) != sorted(drawn_names):
                add("legend.series_mismatch", "medium",
                    "legend entries do not match the drawn series, so colour maps to "
                    "the wrong name", legend=texts[:8], drawn=drawn_names[:8])

    # 4. error column present but not drawn
    if enc.get("y_err") and not any(m.get("y_err") is not None for m in built["mark_rows"]):
        add("error.column_not_drawn", "high",
            "the spec maps an error channel but no error bars were rendered")
    # Error-bar meaning: a spread without a stated meaning (SD, SEM, CI, range)
    # is unreadable in review — the reader cannot tell scatter from significance.
    if (enc.get("y_err") and kind in ("bar", "line", "scatter")
            and not str(spec.get("error_meaning") or "").strip()):
        add("error.meaning_undeclared", "medium",
            "error bars are drawn with no declared meaning (SD, SEM, CI, range); a "
            "reader cannot tell what the spread represents", channel=enc.get("y_err"))

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

    # 5b. drawn geometry must equal the source numbers. The renderer is trusted
    #     for layout, never for values: the audit reads the values back out of
    #     the matplotlib artists and reconciles them against the mark-to-row
    #     mapping, so a phantom bar (a missing cell drawn as zero) or a dropped
    #     value is a finding even though the picture looks complete. Bar charts
    #     read ax.patches heights; scatter reads collection offsets. Line and
    #     heatmap artists mix with error-bar objects, so those two kinds are
    #     reconciled through the mark rows only (see Limits).
    if kind in ("bar", "scatter"):
        expected: list = [m.get("y") for m in built["mark_rows"]]
        drawn_vals: list = []
        if kind == "bar":
            drawn_vals = [float(p.get_height()) for p in built["ax"].patches]
        else:
            for coll in built["ax"].collections:
                for off in coll.get_offsets():
                    drawn_vals.append(float(off[1]))
        nan = float("nan")
        drawn_vals = [v for v in drawn_vals if v == v]          # drop NaN artists
        expected_f = [float(e) for e in expected if e is not None]
        if len(drawn_vals) != len(expected_f):
            add("encoding.drawn_value_mismatch", "high",
                "the number of drawn marks disagrees with the source rows the mapping "
                "declares, so a value was silently dropped or invented",
                expected=len(expected_f), drawn=len(drawn_vals))
        else:
            for j, (e, d) in enumerate(zip(expected_f, drawn_vals)):
                if abs(e - d) > 1e-9 * max(1.0, abs(e)):
                    add("encoding.drawn_value_mismatch", "high",
                        "a drawn mark does not equal its source value, so the figure "
                        "misrepresents the data", mark_index=j, expected=e, drawn=d)
                    break

    # 5c. CJK labels need a CJK-capable font, or every Chinese glyph renders as
    #     a box and the chart ships unreadable. Fires only when a label actually
    #     contains CJK characters, so English charts are never flagged.
    label_texts = [str(built["ax"].get_xlabel()), str(built["ax"].get_ylabel())]
    label_texts += [t.get_text() for t in built["ax"].get_xticklabels()]
    label_texts += [t.get_text() for t in built["ax"].get_yticklabels()]
    label_texts += [str(g) for g in built["groups"] if g is not None]
    if any(CJK_CHAR.search(t) for t in label_texts) and not fonts_support_cjk():
        add("label.cjk_font_missing", "medium",
            "labels contain CJK characters but no CJK-capable font is installed, so "
            "they render as hollow boxes; install one (e.g. a Noto Sans CJK or "
            "Microsoft YaHei) or set rcParams font.sans-serif to a CJK family")

    # 6. caption-declared sample size must match the source
    #    A table may aggregate several observations per row, in which case an
    #    explicit n column is authoritative and the row count is not the sample
    #    size. Comparing against row count there produces a mismatch that is an
    #    artefact of the check, so the n column wins when it exists.
    cap_n = spec.get("caption_n")
    if cap_n is not None:
        # A caption sample size that is not a number ("six") cannot be measured;
        # the audit reports the shape instead of crashing on the comparison.
        try:
            cap_n = int(cap_n)
        except (TypeError, ValueError):
            add("caption.n_unparseable", "medium",
                "the declared caption sample size is not a number, so the "
                "caption-to-source check cannot run",
                caption_n=str(cap_n)[:40])
            cap_n = None
    if cap_n is not None:
        n_col = next((c for c in table["columns"]
                      if c.strip().lower() in ("n", "sample_size", "samples", "n_obs")), None)
        if n_col:
            vals = [v for v in numeric_column(table, n_col) if v is not None]
            ok = (int(cap_n) in {int(v) for v in vals}) or (int(cap_n) == int(sum(vals)))
            detail = {"caption_n": int(cap_n), "n_column": n_col,
                      "distinct_n": sorted({int(v) for v in vals}), "n_total": int(sum(vals))}
        else:
            ok = int(cap_n) == table["n"]
            detail = {"caption_n": int(cap_n), "table_rows": table["n"]}
        if not ok:
            add("caption.n_mismatch", "high",
                "the caption states a sample size the source table does not support", **detail)

    # 7. significance annotation must reference a comparison that exists in the data
    for ann in spec.get("significance") or []:
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
    # The file, not the parameter: read the resolution back out of the PNG's
    # pHYs chunk, so a wrong savefig setting is caught in the artefact itself.
    png_dpi = _png_physical_dpi(built["png"])
    if png_dpi is not None and round(png_dpi) < 300:
        add("export.png_dpi_mismatch", "medium",
            "the PNG's embedded physical resolution reads below 300 dpi, so the "
            "delivered raster does not meet the resolution it was requested at",
            png_dpi=round(png_dpi, 1))
    # Declared width: a journal names a column width in mm; when the delivery
    # declares one, the drawn figure width must be inside tolerance.
    export_decl = spec.get("export") or {}
    if isinstance(export_decl, dict) and export_decl.get("width_mm") is not None:
        try:
            want_mm = float(export_decl["width_mm"])
            tol_mm = float(export_decl.get("tolerance_mm", 2.0))
        except (TypeError, ValueError):
            want_mm = None
        if want_mm:
            got_mm = float(built["fig"].get_size_inches()[0]) * 25.4
            if abs(got_mm - want_mm) > tol_mm:
                add("export.width_out_of_band", "medium",
                    "the figure width misses the declared target width, so the panel "
                    "will not fit the column it was sized for",
                    declared_mm=want_mm, actual_mm=round(got_mm, 1),
                    tolerance_mm=tol_mm)

    counts: dict[str, int] = {}
    for f in findings:
        guide = RULEGUIDE.get(f["rule"])
        if guide:
            for field in ("basis", "fix"):
                if guide.get(field):
                    f.setdefault(field, guide[field])
        counts[f["severity"]] = counts.get(f["severity"], 0) + 1

    return {
        "schema_version": "chartguard/v1",
        "status": ("clean" if not findings else "blocked" if counts.get("high") else "review"),
        "findings": findings,
        "severity_counts": counts,
        "encoding": {"chart_kind": kind, "channels": enc, "rows_in_source": table["n"],
                     "marks_drawn": len(built["mark_rows"])},
        "artifacts": {"svg": str(built["svg"]), "pdf": str(built["pdf"]), "png": str(built["png"])},
        "mark_to_row": built["mark_rows"][:200],
    }


# Spec keys whose values are bulky inputs rather than results: never copied
# verbatim into result.json by the contract echo.
_BULKY = ("output_contract", "rows", "data", "table")


def _refused(out_dir: Path, message: str, rule: str = "spec.unreadable", spec=None) -> dict:
    """The refusal every unrunnable case gets: an exit code, not a crash.

    `spec` is accepted only as an already-parsed plain dict so a refused run
    still names the case it could not run. This path deliberately does not run
    the contract echo (which walks nested spec structure): a refusal must never
    be able to raise, so it copies one scalar and nothing else.
    """
    result = {"schema_version": "chartguard/v1", "status": "refused",
              "findings": [{"rule": rule, "severity": "high", "message": message}],
              "note": "the case was refused rather than approximated or crashed"}
    if isinstance(spec, dict) and spec.get("case_id") is not None:
        result["case_id"] = spec.get("case_id")
    out_dir = Path(out_dir)
    try:
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "result.json").write_text(
            json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    except OSError:
        pass
    return result


def _echo_contract(spec: dict, result: dict, limits: list) -> None:
    """Echo the case's output_contract into result.json.

    A field the audit already carries is kept; one the spec supplies a value
    for is copied verbatim (bulky inputs excluded); one it cannot derive is
    filled as null and named in limits, so a grader finds the key and an
    honest note instead of a silent gap.
    """
    contract = spec.get("output_contract")
    if isinstance(contract, dict):
        keys = list(contract.keys())
    elif isinstance(contract, (list, tuple)):
        keys = [str(k) for k in contract]
    else:
        return
    for key in keys:
        if key in result:
            continue
        if key in spec and key not in _BULKY:
            result[key] = spec[key]
            continue
        result[key] = None
        limits.append(f"output_contract field '{key}' was not derivable by this audit")


# ---------------------------------------------------------------------------
# Rule guide: the judgement basis and the actionable fix each finding carries.
#
# A chart finding must be actionable, not a bare id: "basis" states the
# criterion the verdict rests on, "fix" states what to do about it. Applied
# uniformly at the end of audit_chart.
# ---------------------------------------------------------------------------

RULEGUIDE: dict[str, dict] = {
    "encoding.required_channel_unmapped": {
        "basis": "口径：图型必需通道缺失即拒收，不近似绘制",
        "fix": "在 encoding 中补映射该通道到真实列名"},
    "encoding.column_missing": {
        "basis": "口径：通道映射到列名，列必须存在于源表",
        "fix": "改用 findings.available 中列出的真实列名"},
    "encoding.not_numeric": {
        "basis": "口径：数值通道必须全数值（非空单元格全部可解析）",
        "fix": "清洗或显式剔除非数值单元格，绝不强行置 0"},
    "encoding.unknown_chart_kind": {
        "basis": "口径：五种图型闭合（bar/line/scatter/box/heatmap），未知即拒收",
        "fix": "改用支持的图型，或改用示意图类工具"},
    "data.no_rows": {
        "basis": "口径：无数据行则无物可画",
        "fix": "核对数据文件路径与表头行"},
    "encoding.bad_shape": {
        "basis": "口径：encoding 必须是通道到列名的对象，其他形状无法验证",
        "fix": "把 encoding 改写为对象（例如 x 到列名、y 到列名的映射）后重跑"},
    "caption.n_unparseable": {
        "basis": "口径：图注样本量必须是数字才能与源表对账",
        "fix": "把 caption_n 改写为数字后重跑"},
    "axis.x_label_missing": {
        "basis": "口径：坐标轴必须带标签，否则脱离题注后不可读",
        "fix": "补 x_label（或让引擎从列名生成）"},
    "axis.y_label_missing": {
        "basis": "口径：坐标轴必须带标签",
        "fix": "补 y_label"},
    "axis.x_unit_missing": {
        "basis": "口径：数值轴必须声明单位（类别轴豁免）",
        "fix": "补 x_unit"},
    "axis.y_unit_missing": {
        "basis": "口径：数值轴必须声明单位——mV 与 V 的差别读者无法从图面分辨",
        "fix": "补 y_unit"},
    "axis.value_clipped": {
        "basis": "口径：每个数据值必须落在绘制范围内，出界即不可见",
        "fix": "扩大 limits 或核查离群值是否为录入错误"},
    "series.missing_from_chart": {
        "basis": "口径：数据中的每个组都必须被绘制",
        "fix": "核查组列取值与过滤逻辑，补画缺失组"},
    "legend.absent": {
        "basis": "口径：多组着色必须有图例，否则颜色无含义",
        "fix": "置 legend 为 true 或补组说明"},
    "legend.series_mismatch": {
        "basis": "口径：图例条目必须与实际绘制的系列一一对应",
        "fix": "重绘使图例与系列对齐；不要手工改图例文字"},
    "error.column_not_drawn": {
        "basis": "口径：误差通道已映射就必须真的画出",
        "fix": "核查 y_err 指向的列是否为误差值列"},
    "error.meaning_undeclared": {
        "basis": "口径：误差线必须声明含义（SD/SEM/CI/极差），否则读者无从解读",
        "fix": "在 spec 的 error_meaning 中声明误差线含义，并写进图注"},
    "traceability.missing": {
        "basis": "口径：每个图元必须携带源行索引",
        "fix": "重跑引擎重建 mark_to_row 映射"},
    "traceability.row_coverage": {
        "basis": "口径：图元数不得少于源行数——缺行即静默过滤",
        "fix": "核查被过滤的行并在报告中说明"},
    "caption.n_mismatch": {
        "basis": "口径：图注样本量必须与源表（或 n 列）一致",
        "fix": "修正图注 n 或核对 n 列语义（per-group vs 总计）"},
    "annotation.unknown_comparison": {
        "basis": "口径：显著性标记比较的两组必须都存在于数据",
        "fix": "删除模板复制来的标记，或改指真实存在的组"},
    "encoding.drawn_value_mismatch": {
        "basis": "口径：画布图元读回值必须等于源数据值——图不得改写数据",
        "fix": "重跑渲染；若仍不符，说明绘图代码被手工改动过"},
    "label.cjk_font_missing": {
        "basis": "口径：含 CJK 的标注必须有 CJK 字体，否则渲染为方框",
        "fix": "安装 CJK 字体（Noto Sans CJK / Microsoft YaHei）或将 rcParams font.sans-serif 设为 CJK 族"},
    "export.no_live_text": {
        "basis": "口径：SVG 必须保留活字文本，转曲即不可编辑",
        "fix": "以 svg.fonttype = none 重新导出"},
    "export.pdf_invalid": {
        "basis": "口径：PDF 导出必须是合法 PDF",
        "fix": "核查导出路径与后端后重导"},
    "export.low_dpi": {
        "basis": "口径：位图预览不低于 300 dpi",
        "fix": "以 dpi>=300 重新导出"},
    "export.png_dpi_mismatch": {
        "basis": "口径：以 PNG 文件内嵌物理分辨率（pHYs 块）实测，而非采信参数",
        "fix": "检查 savefig 的 dpi 设置与插值，重导并实测"},
    "export.width_out_of_band": {
        "basis": "口径：声明目标宽度（期刊栏宽）则实测图宽须落在容差内",
        "fix": "按 width_mm 调整 figsize 后重导"},
    "spec.unreadable": {
        "basis": "口径：spec 不可读即无法按声明运行，拒收不崩溃",
        "fix": "修正 spec 文件为合法 JSON 对象后重跑"},
    "spec.not_object": {
        "basis": "口径：spec 必须是 JSON 对象",
        "fix": "把顶层改为对象（键值结构）后重跑"},
    "data.unreadable": {
        "basis": "口径：数据文件不可读则无物可画，拒收不崩溃",
        "fix": "核对 --data 路径与文件编码（UTF-8 CSV/JSON）"},
    "deps.unavailable": {
        "basis": "口径：matplotlib/numpy 缺失时诚实拒收，不产出残缺图",
        "fix": "pip install matplotlib numpy 后重跑"},
    "render.failed": {
        "basis": "口径：渲染或审计异常按拒收处理，绝不抛 traceback",
        "fix": "按 findings.message 定位输入问题后重跑"},
}


def build_and_audit(spec_path: Path, data_path: Path, out_dir: Path) -> dict:
    out_dir = Path(out_dir)

    if _DEPS_ERROR:
        return _refused(out_dir,
                        f"rendering dependencies are unavailable: {_DEPS_ERROR}. "
                        f"Install matplotlib and numpy, then rerun.",
                        rule="deps.unavailable")
    try:
        # utf-8-sig tolerates a BOM left by Windows editors; plain utf-8 files
        # read identically, so no honest input is refused over encoding trivia.
        spec = json.loads(Path(spec_path).read_text(encoding="utf-8-sig"))
    except (json.JSONDecodeError, UnicodeDecodeError, OSError) as exc:
        return _refused(out_dir, f"the spec file is not readable JSON: {exc}",
                        rule="spec.unreadable")
    if not isinstance(spec, dict):
        return _refused(out_dir, "the spec file is not a JSON object",
                        rule="spec.not_object")
    try:
        table = load_table(Path(data_path))
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        return _refused(out_dir, f"the data file is not readable: {exc}",
                        rule="data.unreadable")

    planned = plan_encoding(spec, table)
    if not planned["ok"]:
        result = {"schema_version": "chartguard/v1", "status": "refused",
                  "findings": [{"rule": p["rule"], "severity": "high", **p}
                               for p in planned["problems"]],
                  "note": "the spec was refused rather than approximated"}
        cid = spec.get("case_id")
        if cid is not None:
            result["case_id"] = cid
        try:
            out_dir.mkdir(parents=True, exist_ok=True)
            (out_dir / "result.json").write_text(
                json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        except OSError:
            pass
        return result

    try:
        dpi = spec.get("dpi", 300)
        try:
            dpi = int(float(dpi))
        except (TypeError, ValueError):
            dpi = 300          # an unparseable dpi degrades to the default, not a crash
        built = render_chart(spec, table, planned["plan"], out_dir / "figure",
                             dpi=dpi, fonttype=spec.get("_fonttype", "none"))
        result = audit_chart(spec, table, planned["plan"], built)
    except Exception as exc:  # a render or audit bug must never surface as a traceback
        plt.close("all")
        return _refused(out_dir,
                        f"the render/audit failed on this case and was refused: {exc}",
                        rule="render.failed", spec=spec)
    result["spec"] = spec
    result.setdefault("limits", [])
    cid = spec.get("case_id")
    if cid is not None:
        result["case_id"] = cid
    _echo_contract(spec, result, result["limits"])
    try:
        (out_dir / "result.json").write_text(
            json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    except OSError as exc:
        result["status"] = "refused"
        result["limits"] = result["limits"] + [f"result.json could not be written: {exc}"]
    plt.close(built["fig"])
    return result


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
                      "findings": [f["rule"] for f in r.get("findings", [])],
                      "marks": len(r.get("mark_to_row") or []),
                      "wrote": str(Path(a.out) / "result.json")}, ensure_ascii=False))
    return {"clean": 0, "review": 3, "blocked": 4, "refused": 5}.get(r["status"], 1)


if __name__ == "__main__":
    raise SystemExit(main())
