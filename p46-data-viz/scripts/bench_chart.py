"""Benchmark for the chart render-and-audit engine.

Every scenario is a spec/data pair with exactly one defect planted, plus the
rule that must fire. The clean baseline must report no high or medium finding,
so a detector cannot pass by flagging everything.

    python bench_chart.py
"""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import chartguard as C  # noqa: E402

DATA = """group,condition,response,response_sd,n
WT,control,12.4,1.1,6
WT,drug,31.2,2.4,6
KO,control,10.1,0.9,6
KO,drug,14.8,1.3,6
"""

BAD_DATA = """group,condition,response
WT,control,12.4
WT,drug,many
KO,control,10.1
KO,drug,14.8
"""

BASE = {
    "kind": "bar",
    "title": "Treatment response by genotype",
    "caption": "Bars show source-row values; error bars are defined in the caption.",
    "x_label": "Treatment",
    "y_label": "Response",
    "y_unit": "a.u.",
    "caption_n": 6,
    "legend": True,
    "errorbar_meaning": "SD",
    "panel": "a",
    "encoding": {"x": "condition", "y": "response", "y_err": "response_sd", "group": "group"},
}


def scen_clean():
    return dict(BASE), DATA, []


def scen_missing_unit():
    s = dict(BASE); s.pop("y_unit")
    return s, DATA, ["axis.y_unit_missing"]


def scen_unknown_column():
    s = dict(BASE); s["encoding"] = dict(BASE["encoding"], y="not_a_column")
    return s, DATA, ["encoding.column_missing"]


def scen_text_in_numeric_channel():
    return dict(BASE), BAD_DATA, ["encoding.not_numeric"]


def scen_no_error_bars():
    s = dict(BASE); s["encoding"] = {"x": "condition", "y": "response", "group": "group"}
    return s, DATA, []


def scen_n_mismatch():
    s = dict(BASE, caption_n=99)
    return s, DATA, ["caption.n_mismatch"]


def scen_missing_required_channel():
    s = dict(BASE); s["encoding"] = {"x": "condition"}
    return s, DATA, ["encoding.required_channel_unmapped"]


def scen_unknown_kind():
    s = dict(BASE, kind="pie")
    return s, DATA, ["encoding.unknown_chart_kind"]


def scen_unknown_comparison():
    s = dict(BASE, significance=[{"between": ["WT", "Rescue"], "p": "0.01"}])
    return s, DATA, ["annotation.unknown_comparison"]


def scen_paths_not_text():
    s = dict(BASE, _fonttype="path")
    return s, DATA, ["export.no_live_text"]


def scen_low_dpi():
    return dict(BASE, dpi=72), DATA, ["export.low_dpi"]


EMPTY_DATA = "group,condition,response,response_sd,n" + chr(10)

PARTIAL_ERR = ("group,condition,response,response_sd,n" + chr(10)
               + "WT,control,12.4,1.1,6" + chr(10)
               + "WT,drug,31.2,,6" + chr(10)
               + "KO,control,10.1,,6" + chr(10)
               + "KO,drug,14.8,1.3,6" + chr(10))


def scen_empty_table():
    """A header-only table is refused with data.no_rows, never a crash."""
    return dict(BASE), EMPTY_DATA, ["data.no_rows"]


def scen_partial_blank_err():
    """A partially blank error column renders: blanks draw nothing, nothing crashes."""
    return dict(BASE), PARTIAL_ERR, []


def scen_cjk_labels():
    """Chinese axis labels resolve to a CJK-capable font, so no box glyphs appear."""
    s = dict(BASE, x_label="处理组", y_label="响应强度")
    return s, DATA, []


def scen_glyph_missing():
    """A drawn character that no candidate font covers is reported, never a silent box."""
    s = dict(BASE, x_label="treatment \u23f0")
    return s, DATA, ["font.glyph_missing"]


# --- round-2 rules: chart kind vs data structure, axis hygiene, readability ---
# Each scenario plants exactly one defect and names the rule that must fire.

YEAR_DATA = ("group,year,response,response_sd,n" + chr(10)
             + "WT,2020,12.4,1.1,6" + chr(10)
             + "WT,2021,13.9,1.2,6" + chr(10)
             + "WT,2022,15.6,1.0,6" + chr(10)
             + "WT,2023,18.2,1.4,6" + chr(10))


def scen_time_as_bars():
    """A time-like x column drawn as disconnected bars — the named mismatch between
    chart kind and data structure (ordering and continuity vanish)."""
    s = dict(BASE, encoding={"x": "year", "y": "response", "y_err": "response_sd",
                             "group": "group"}, x_label="Year", x_unit="year")
    return s, YEAR_DATA, ["encoding.time_as_bars"]


def scen_truncated_baseline():
    """A declared y-axis starting above zero shortens every bar and exaggerates
    differences — the classic truncated-baseline misleading chart."""
    s = dict(BASE, ylim=[5, 40])
    return s, DATA, ["axis.truncated_baseline"]


LOG_DATA = ("day,response" + chr(10)
            + "1,12.4" + chr(10)
            + "2,0" + chr(10)
            + "3,10.1" + chr(10)
            + "4,14.8" + chr(10))


def scen_log_nonpositive():
    """A log y-scale over data containing zero: the point cannot be shown and is
    dropped silently unless the audit names it."""
    s = dict(BASE, kind="line", y_scale="log", y_unit="fold",
             x_label="Time", x_unit="h", encoding={"x": "day", "y": "response"})
    return s, LOG_DATA, ["axis.log_nonpositive"]


MANY_DATA = "condition,response" + chr(10) + "".join(
    f"cond{i:02d},{10 + i}.5" + chr(10) for i in range(15))


def scen_too_many_categories():
    """Fifteen categories jammed onto one categorical axis — unreadable at
    single-column width, so the audit asks for a split or grouping."""
    s = dict(BASE, legend=False, caption_n=None, y_unit="a.u.",
             encoding={"x": "condition", "y": "response"})
    s.pop("errorbar_meaning", None)
    return s, MANY_DATA, ["read.too_many_categories"]


def scen_errorbar_meaning_missing():
    """An error channel is drawn but nothing says whether the bars are SD, SEM or
    a confidence interval."""
    s = dict(BASE)
    s.pop("errorbar_meaning")
    return s, DATA, ["annotation.errorbar_meaning_missing"]


HEAT_DATA = ("row_x,col_y,uptake" + chr(10)
             + "A,low,0.2" + chr(10)
             + "A,high,1.4" + chr(10)
             + "B,low,0.8" + chr(10)
             + "B,high,3.1" + chr(10))


def _heat_spec(extra):
    s = {"kind": "heatmap", "title": "Uptake matrix", "x_label": "Sample", "y_label": "Dose",
         "value_label": "uptake", "value_unit": "a.u.", "panel": "a", "encoding": {"x": "row_x", "y": "col_y",
                                                                                  "value": "uptake"}}
    s.update(extra)
    return s


def scen_heatmap_clipped():
    """A declared colour range that does not cover the data pins the hottest cells
    to the palette end, so their magnitude is misread."""
    return _heat_spec({"color_range": [0, 1]}), HEAT_DATA, ["color.range_clipped"]


def scen_heatmap_undeclared():
    """No colour range declared: a reader cannot tell whether the palette spans
    the data or truncates it."""
    return _heat_spec({}), HEAT_DATA, ["color.range_undeclared"]


def scen_heatmap_clean():
    """A heatmap whose declared colour range covers the data stays silent."""
    return _heat_spec({"color_range": [0, 4]}), HEAT_DATA, []


def scen_panel_missing():
    """No panel letter declared — legal for a lone figure, but the export records
    none, so a composite cannot place it (low severity)."""
    s = dict(BASE)
    s.pop("panel")
    return s, DATA, ["layout.panel_missing"]


def scen_label_truncated():
    """A presentation string far beyond any journal label is clipped before render
    and the clip is reported, so the drawn labels are never silently different."""
    s = dict(BASE, title="T" * 5000)
    return s, DATA, ["input.label_truncated"]


def scen_title_missing():
    s = dict(BASE)
    s.pop("title")
    return s, DATA, ["annotation.title_missing"]


def scen_dual_axis():
    s = dict(BASE, secondary_y="other_measure")
    return s, DATA, ["encoding.dual_axis_unsupported"]


def scen_duplicate_bars():
    return dict(BASE), DATA + "KO,drug,99.0,1.3,6\n", ["data.duplicate_marks"]


def scen_missing_numeric():
    data = DATA.replace("WT,drug,31.2", "WT,drug,")
    return dict(BASE), data, ["data.missing_numeric"]


def scen_histogram_clean():
    s = {"kind": "histogram", "title": "Response distribution", "x_label": "Response",
         "x_unit": "a.u.", "panel": "a", "bins": 3,
         "encoding": {"x": "response"}}
    return s, DATA, []


SCENARIOS = [
    ("clean", scen_clean),
    ("empty_table", scen_empty_table),
    ("partial_blank_err", scen_partial_blank_err),
    ("missing_unit", scen_missing_unit),
    ("unknown_column", scen_unknown_column),
    ("text_in_numeric", scen_text_in_numeric_channel),
    ("n_mismatch", scen_n_mismatch),
    ("missing_required_channel", scen_missing_required_channel),
    ("unknown_chart_kind", scen_unknown_kind),
    ("unknown_comparison", scen_unknown_comparison),
    ("paths_not_text", scen_paths_not_text),
    ("low_dpi", scen_low_dpi),
    ("cjk_labels", scen_cjk_labels),
    ("glyph_missing", scen_glyph_missing),
    ("time_as_bars", scen_time_as_bars),
    ("truncated_baseline", scen_truncated_baseline),
    ("log_nonpositive", scen_log_nonpositive),
    ("too_many_categories", scen_too_many_categories),
    ("errorbar_meaning_missing", scen_errorbar_meaning_missing),
    ("heatmap_clipped", scen_heatmap_clipped),
    ("heatmap_undeclared", scen_heatmap_undeclared),
    ("heatmap_clean", scen_heatmap_clean),
    ("panel_missing", scen_panel_missing),
    ("label_truncated", scen_label_truncated),
    ("title_missing", scen_title_missing),
    ("dual_axis", scen_dual_axis),
    ("duplicate_bars", scen_duplicate_bars),
    ("missing_numeric", scen_missing_numeric),
    ("histogram_clean", scen_histogram_clean),
]


def run_one(name, builder, root: Path) -> dict:
    spec, data, expect = builder()
    d = root / name
    d.mkdir(parents=True, exist_ok=True)
    (d / "spec.json").write_text(json.dumps(spec, ensure_ascii=False, indent=2), encoding="utf-8")
    (d / "data.csv").write_text(data, encoding="utf-8")
    r = C.build_and_audit(d / "spec.json", d / "data.csv", d / "out")

    fired = {f["rule"] for f in r.get("findings", [])}
    missing = [x for x in expect if x not in fired]
    spurious = []
    if not expect:
        spurious = [f["rule"] for f in r.get("findings", []) if f["severity"] in ("high", "medium")]
    if name == "clean":
        centers = [m["rendered"]["x"] for m in r.get("mark_to_row", [])]
        if len(centers) != 4 or len(set(centers)) != 4:
            spurious.append("selfcheck_grouped_bar_overlap")
        caption = (d / "out" / "caption.txt").read_text(encoding="utf-8")
        if "SD" not in caption or "n = 6" not in caption:
            spurious.append("selfcheck_caption_semantics_missing")
        svg = (d / "out" / "figure.svg").read_text(encoding="utf-8")
        if "<desc>" not in svg or "role=\"img\"" not in svg:
            spurious.append("selfcheck_accessibility_metadata_missing")
        if (r.get("layout") or {}).get("text_overflow"):
            spurious.append("selfcheck_text_overflow")
    if name == "histogram_clean":
        if sum(a["count"] for a in r.get("aggregates", [])) != 4:
            spurious.append("selfcheck_histogram_count_mismatch")
    return {"scenario": name, "expected": expect, "fired": sorted(fired),
            "missing": missing, "spurious": spurious, "status": r["status"],
            "pass": not missing and not spurious}


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="chartguard-bench-") as tmp:
        root = Path(tmp)
        rows = [run_one(n, b, root) for n, b in SCENARIOS]
    passed = sum(1 for r in rows if r["pass"])
    report = {
        "schema_version": "chart-bench/v2",
        "scenarios": rows,
        "totals": {"passed": passed, "of": len(rows)},
        "note": ("One planted defect per scenario plus rendered-geometry, caption and accessibility "
                 "assertions. Runtime images are written to a temporary directory, never shipped."),
    }
    (Path(__file__).resolve().parent / "report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    for r in rows:
        print(f"{'PASS' if r['pass'] else 'FAIL'}  {r['scenario']:<26}"
              f"expected={r['expected']} missing={r['missing']} spurious={r['spurious']}")
    print(f"\n{passed}/{len(rows)} scenarios pass")
    return 0 if passed == len(rows) else 1


if __name__ == "__main__":
    raise SystemExit(main())
