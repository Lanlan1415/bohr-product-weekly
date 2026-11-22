"""Benchmark for the chart render-and-audit engine.

Every scenario is a spec/data pair with exactly one defect planted, plus the
rule that must fire. The clean baseline must report no high or medium finding,
so a detector cannot pass by flagging everything.

    python bench_chart.py
"""

from __future__ import annotations

import json
import sys
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
    "x_label": "Treatment",
    "y_label": "Response",
    "y_unit": "a.u.",
    "caption_n": 6,
    "legend": True,
    "error_meaning": "SD",
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
    return dict(BASE, dpi=72), DATA, ["export.low_dpi", "export.png_dpi_mismatch"]


EMPTY_DATA = "group,condition,response,response_sd,n" + chr(10)

PARTIAL_ERR = ("group,condition,response,response_sd,n" + chr(10)
               + "WT,control,12.4,1.1,6" + chr(10)
               + "WT,drug,,2.4,6" + chr(10)
               + "KO,control,10.1,,6" + chr(10)
               + "KO,drug,14.8,1.3,6" + chr(10))


def scen_empty_table():
    """A header-only table is refused with data.no_rows, never a crash."""
    return dict(BASE), EMPTY_DATA, ["data.no_rows"]


def scen_partial_blank_err():
    """A partially blank error column renders: blanks draw nothing, nothing crashes."""
    return dict(BASE), PARTIAL_ERR, []


def scen_no_error_meaning():
    """Error bars drawn without a declared meaning are unreadable in review."""
    s = dict(BASE); s.pop("error_meaning")
    return s, DATA, ["error.meaning_undeclared"]


def scen_export_width():
    """A declared column width the figure misses is a real export failure."""
    s = dict(BASE, export={"width_mm": 200.0, "tolerance_mm": 2.0})
    return s, DATA, ["export.width_out_of_band"]


def scen_cjk_label():
    """CJK labels fire only when no CJK-capable font is installed on this machine."""
    s = dict(BASE, x_label="处理组", y_label="响应强度")
    if C.fonts_support_cjk():
        return s, DATA, []          # font exists -> renders as text, stays silent
    return s, DATA, ["label.cjk_font_missing"]


def scen_unreadable_spec():
    """Bad spec JSON is refused with a rule id, never a traceback."""
    return "{not json at all,", DATA, ["spec.unreadable"]


def scen_not_object():
    """A JSON array spec is refused."""
    return json.dumps([1, 2, 3]), DATA, ["spec.not_object"]


def scen_missing_data():
    """A missing data file is refused with data.unreadable."""
    return json.dumps(dict(BASE)), "MISSING", ["data.unreadable"]


SCATTER_DATA = """condition_id,response
1,12.4
2,18.9
3,25.1
4,31.7
"""


def scen_scatter_clean():
    """A scatter chart reads back cleanly: offsets equal source values."""
    s = dict(BASE, kind="scatter", legend=False, caption_n=None,
             x_label="Dose level", x_unit="level", y_label="Response", y_unit="a.u.",
             encoding={"x": "condition_id", "y": "response"})
    return s, SCATTER_DATA, []

SCENARIOS = [
    ("clean", scen_clean),
    ("empty_table", scen_empty_table),
    ("partial_blank_err", scen_partial_blank_err),
    ("scatter_clean", scen_scatter_clean),
    ("missing_unit", scen_missing_unit),
    ("unknown_column", scen_unknown_column),
    ("text_in_numeric", scen_text_in_numeric_channel),
    ("no_error_meaning", scen_no_error_meaning),
    ("n_mismatch", scen_n_mismatch),
    ("missing_required_channel", scen_missing_required_channel),
    ("unknown_chart_kind", scen_unknown_kind),
    ("unknown_comparison", scen_unknown_comparison),
    ("paths_not_text", scen_paths_not_text),
    ("low_dpi", scen_low_dpi),
    ("export_width", scen_export_width),
    ("cjk_label", scen_cjk_label),
    ("unreadable_spec", scen_unreadable_spec),
    ("not_object", scen_not_object),
    ("missing_data", scen_missing_data),
]


def run_one(name, builder, root: Path) -> dict:
    spec, data, expect = builder()
    d = root / name
    d.mkdir(parents=True, exist_ok=True)
    if isinstance(spec, str):
        (d / "spec.json").write_text(spec, encoding="utf-8")
    else:
        (d / "spec.json").write_text(json.dumps(spec, ensure_ascii=False, indent=2),
                                     encoding="utf-8")
    if data == "MISSING":
        data_path = d / "absent.csv"      # referenced but never written
    else:
        (d / "data.csv").write_text(data, encoding="utf-8")
        data_path = d / "data.csv"
    r = C.build_and_audit(d / "spec.json", data_path, d / "out")

    fired = {f["rule"] for f in r.get("findings", [])}
    missing = [x for x in expect if x not in fired]
    spurious = []
    if not expect:
        spurious = [f["rule"] for f in r.get("findings", []) if f["severity"] in ("high", "medium")]
    return {"scenario": name, "expected": expect, "fired": sorted(fired),
            "missing": missing, "spurious": spurious, "status": r["status"],
            "pass": not missing and not spurious}


def main() -> int:
    root = Path(__file__).resolve().parent / "_run"
    rows = [run_one(n, b, root) for n, b in SCENARIOS]
    passed = sum(1 for r in rows if r["pass"])
    report = {
        "schema_version": "chart-bench/v1",
        "scenarios": rows,
        "totals": {"passed": passed, "of": len(rows)},
        "note": ("One planted defect per scenario. The clean baseline must stay silent on high "
                 "and medium findings, so blanket flagging cannot pass."),
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
