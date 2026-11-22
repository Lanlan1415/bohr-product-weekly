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
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import contract_echo  # noqa: E402

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

    # Glyph coverage is a shared export contract: resolve a font against the exact
    # characters this figure draws, and record it in the result.
    try:
        import fontsel as _fs
        labels_for_font = [str(spec.get(k) or "") for k in
                           ("x_label", "y_label", "title", "caption")]
        labels_for_font += [str(r.get(c) or "") for c in enc.values() if c
                            for r in rows]
        drawn = "".join(labels_for_font)
        font_info = _fs.resolve(drawn)
    except Exception as exc:
        # A dead font path must not masquerade as clean: name the failure and fall
        # back to matplotlib's own default, but record that glyph coverage is unknown.
        font_info = None
        font_error = "font resolution failed: " + str(exc)
    else:
        font_error = None
    if font_info is not None and getattr(font_info, "family", None):
        matplotlib.rcParams["font.family"] = "sans-serif"
        matplotlib.rcParams["font.sans-serif"] = [font_info.family]

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
            # Grouped bars dodge: each series gets its own slot inside the category
            # width, or a later series silently paints over the earlier one.
            n_series = max(len(groups), 1)
            slot = 0.72 / n_series
            pos = np.arange(len(idx)) + (gi - (n_series - 1) / 2) * slot
            ax.bar(pos, [np.nan if y is None else y for y in ys], width=slot,
                   color=colour, label=label,
                   yerr=errs_n if errs else None, capsize=3 if errs else 0)
            ax.set_xticks(np.arange(len(idx)))
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
            "xlim": ax.get_xlim(), "ylim": ax.get_ylim(),
            "font": font_info, "font_error": font_error}


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
    font_info = built.get("font")
    if font_info is not None and getattr(font_info, "missing", None):
        add("export.missing_glyphs", "high",
            "characters on the figure have no glyph in the resolved font, so they render "
            "as boxes", family=font_info.family,
            glyphs=list(font_info.missing)[:12])

    counts: dict[str, int] = {}
    for f in findings:
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


def _refused(out_dir: Path, problems: list[dict]) -> dict:
    """Write the refused verdict. The caller asked for something the engine will
    not approximate: an unreadable spec, an unreadable table, an unknown kind."""
    result = {"schema_version": "chartguard/v1", "status": "refused",
              "findings": [{"rule": p["rule"], "severity": "high", **p} for p in problems],
              "note": "the spec was refused rather than approximated"}
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2),
                                         encoding="utf-8")
    return result


def build_and_audit(spec_path: Path, data_path: Path, out_dir: Path) -> dict:
    out_dir = Path(out_dir); out_dir.mkdir(parents=True, exist_ok=True)
    try:
        spec = json.loads(Path(spec_path).read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        return _refused(out_dir, [{"rule": "audit.no_section", "message": "spec file not found: " + str(exc)}])
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        return _refused(out_dir, [{"rule": "audit.no_section",
                                   "message": f"the spec file is not readable JSON: {exc}"}])
    if not isinstance(spec, dict):
        return _refused(out_dir, [{"rule": "audit.no_section",
                                   "message": "the spec file is not a JSON object"}])
    try:
        table = load_table(Path(data_path))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        return _refused(out_dir, [{"rule": "data.unreadable",
                                   "message": f"the data table could not be read: {exc}"}])

    planned = plan_encoding(spec, table)
    if not planned["ok"]:
        result = {"schema_version": "chartguard/v1", "status": "refused",
                  "findings": [{"rule": p["rule"], "severity": "high", **p} for p in planned["problems"]],
                  "note": "the spec was refused rather than approximated"}
        result = contract_echo.apply(result, spec)
        (out_dir / "result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2),
                                             encoding="utf-8")
        return result

    built = render_chart(spec, table, planned["plan"], out_dir / "figure",
                         dpi=spec.get("dpi", 300), fonttype=spec.get("_fonttype", "none"))
    result = audit_chart(spec, table, planned["plan"], built)
    result["spec"] = spec
    font_info = built.get("font")
    if font_info is not None:
        result["font"] = {"family": font_info.family, "path": font_info.path,
                          "missing_glyphs": list(font_info.missing)}
    if built.get("font_error"):
        result["limits"] = list(result.get("limits") or []) + [built["font_error"]]
    result = contract_echo.apply(result, spec)
    (out_dir / "result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2),
                                         encoding="utf-8")
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
