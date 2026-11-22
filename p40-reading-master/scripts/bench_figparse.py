"""Benchmark for the figure/table digitisation routes: analytic truth, generated cases.

    python bench_figparse.py

Nine figure cases are drawn at exact pixel coordinates with a known analytic
curve, then read back through `figparse.py run` and scored against that truth,
so the error is measured against a known answer rather than estimated. The set
covers the things the route claims to handle and the things that break naive
readers: log axes, an inverted axis, markers-only, error bars, bar charts with
annotations, and a bare image panel with no frame at all — where the tool must
refuse to invent a calibration.

An ablation repeats every case with log detection disabled and both axes forced
to linear. The gap between the two runs is the measured value of axis-type
discrimination, one of the capabilities this route claims. It is reported as
evidence; the pass gate is the nine truth-scored cases.

Three table scenarios exercise `tables.py`: typed columns (percent columns keep
the printed number), markdown pipe tables, and refusal of unparseable input by
name instead of guessing.

Cases are generated into a fresh temp directory, so the bench leaves no
artefacts in the package.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

SCRIPTS = Path(__file__).resolve().parent
FIGPARSE = SCRIPTS / "figparse.py"
TABLES = SCRIPTS / "tables.py"

RED = (214, 39, 40)
BLUE = (31, 119, 180)
GREEN = (44, 160, 44)


class Fig:
    """A single-panel plot drawn at exact pixel coordinates."""

    def __init__(self, w=640, h=480, left=90, right=600, top=60, bottom=400):
        self.W, self.H = w, h
        self.left, self.right, self.top, self.bottom = left, right, top, bottom
        self.im = Image.new("RGB", (w, h), "white")
        self.d = ImageDraw.Draw(self.im)

    def frame(self):
        self.d.line([(self.left, self.top), (self.left, self.bottom)], fill=(0, 0, 0), width=2)
        self.d.line([(self.left, self.bottom), (self.right, self.bottom)], fill=(0, 0, 0), width=2)

    def ticks(self, spec, xlim, ylim):
        for v in spec["x_ticks"]:
            px = self.px_x(v, xlim, spec.get("x_log", False))
            if self.left <= px <= self.right:
                self.d.line([(px, self.bottom + 1), (px, self.bottom + 5)], fill=(0, 0, 0), width=2)
        for v in spec["y_ticks"]:
            py = self.px_y(v, ylim, spec.get("y_log", False))
            if self.top <= py <= self.bottom:
                self.d.line([(self.left - 5, py), (self.left - 1, py)], fill=(0, 0, 0), width=2)

    def px_x(self, v, xlim, log=False):
        lo, hi = xlim
        if log:
            f = (np.log10(v) - np.log10(lo)) / (np.log10(hi) - np.log10(lo))
        else:
            f = (v - lo) / (hi - lo)
        return self.left + f * (self.right - self.left)

    def px_y(self, v, ylim, log=False):
        lo, hi = ylim
        if log:
            f = (np.log10(v) - np.log10(lo)) / (np.log10(hi) - np.log10(lo))
        else:
            f = (v - lo) / (hi - lo)
        return self.bottom - f * (self.bottom - self.top)

    def series(self, fn, xlim, ylim, color, n=300, width=3, logx=False, logy=False):
        xs = np.linspace(xlim[0], xlim[1], n)
        pts = []
        for x in xs:
            y = fn(x)
            if not np.isfinite(y):
                continue
            pts.append((self.px_x(x, xlim, logx), self.px_y(y, ylim, logy)))
        self.d.line(pts, fill=color, width=width)

    def markers(self, fn, xlim, ylim, color, x_values, r=4, err=None):
        for x in x_values:
            y = fn(x)
            px, py = self.px_x(x, xlim), self.px_y(y, ylim)
            if err is not None:
                e = err(x)
                h = abs(self.px_y(y + e, ylim) - py)
                self.d.line([(px, py - h), (px, py + h)], fill=color, width=2)
                self.d.line([(px - 4, py - h), (px + 4, py - h)], fill=color, width=2)
                self.d.line([(px - 4, py + h), (px + 4, py + h)], fill=color, width=2)
            self.d.ellipse([px - r, py - r, px + r, py + r], fill=color)

    def bar(self, xlim, ylim, x_center, width, value, color):
        x0 = self.px_x(x_center - width / 2, xlim)
        x1 = self.px_x(x_center + width / 2, xlim)
        ytop = self.px_y(value, ylim)
        self.d.rectangle([x0, ytop, x1, self.bottom], fill=color)

    def bar_err(self, xlim, ylim, x_center, value, err, half_w=6):
        px = self.px_x(x_center, xlim)
        ytop = self.px_y(value, ylim)
        yup = self.px_y(value + err, ylim)
        self.d.line([(px, yup), (px, ytop)], fill=(0, 0, 0), width=2)
        self.d.line([(px - half_w, yup), (px + half_w, yup)], fill=(0, 0, 0), width=2)
        self.d.line([(px - half_w, ytop), (px + half_w, ytop)], fill=(0, 0, 0), width=2)

    def save(self, path: Path):
        self.im.save(path)


def build_cases() -> list[dict]:
    """Case definitions. `truth` is analytic, so the error is against a known answer."""
    cases = []
    cases.append(dict(
        name="01-linear-two-series",
        xlim=(0.0, 10.0), ylim=(0.0, 100.0),
        x_ticks=[0, 2, 4, 6, 8, 10], y_ticks=[0, 20, 40, 60, 80, 100],
        series=[{"color": RED, "fn": "50+30*sin(0.6*x)", "label": "red"},
                {"color": BLUE, "fn": "20+4*x", "label": "blue"}],
    ))
    cases.append(dict(
        name="02-log-x",
        xlim=(1.0, 1000.0), ylim=(0.0, 100.0), x_log=True,
        x_ticks=[1, 10, 100, 1000], y_ticks=[0, 25, 50, 75, 100],
        series=[{"color": BLUE, "fn": "10+25*log10(x)", "label": "blue"}],
    ))
    cases.append(dict(
        name="03-log-y",
        xlim=(0.0, 10.0), ylim=(1.0, 10000.0), y_log=True,
        x_ticks=[0, 2, 4, 6, 8, 10], y_ticks=[1, 10, 100, 1000, 10000],
        series=[{"color": RED, "fn": "10**(2+0.3*x)", "label": "red"}],
    ))
    cases.append(dict(
        name="04-three-series",
        xlim=(0.0, 10.0), ylim=(0.0, 100.0),
        x_ticks=[0, 2, 4, 6, 8, 10], y_ticks=[0, 20, 40, 60, 80, 100],
        series=[{"color": RED, "fn": "20+6*x", "label": "red"},
                {"color": BLUE, "fn": "90-7*x", "label": "blue"},
                {"color": GREEN, "fn": "55+20*sin(0.9*x)", "label": "green"}],
    ))
    cases.append(dict(
        name="05-markers-errorbars",
        xlim=(0.0, 10.0), ylim=(0.0, 100.0),
        x_ticks=[0, 2, 4, 6, 8, 10], y_ticks=[0, 20, 40, 60, 80, 100],
        markers={"color": RED, "fn": "30+5*x", "err": "4+0.5*x",
                 "x": [0.5, 1.5, 2.5, 3.5, 4.5, 5.5, 6.5, 7.5, 8.5, 9.5]},
        series=[],
    ))
    cases.append(dict(
        name="06-inverted-y",
        xlim=(0.0, 10.0), ylim=(100.0, 0.0), y_inverted=True,
        x_ticks=[0, 2, 4, 6, 8, 10], y_ticks=[100, 80, 60, 40, 20, 0],
        series=[{"color": BLUE, "fn": "80-5*x", "label": "blue"}],
    ))
    cases.append(dict(name="07-no-frame", bare_image=True))
    cases.append(dict(
        name="08-bar-chart",
        xlim=(0.0, 4.0), ylim=(0.0, 100.0),
        x_ticks=[0, 1, 2, 3, 4], y_ticks=[0, 20, 40, 60, 80, 100],
        bars={"color": RED, "values": [35, 55, 80, 45],
              "centers": [0.5, 1.5, 2.5, 3.5], "width": 0.5},
        series=[],
    ))
    cases.append(dict(
        name="09-bars-annotations",
        xlim=(0.0, 4.0), ylim=(0.0, 100.0),
        x_ticks=[0, 1, 2, 3, 4], y_ticks=[0, 20, 40, 60, 80, 100],
        bars={"color": BLUE, "values": [40, 60, 75, 50],
              "centers": [0.5, 1.5, 2.5, 3.5], "width": 0.5,
              "errors": [5, 8, 6, 7], "sig_at": 2.5},
        series=[],
    ))
    return cases


def emit(case: dict, root: Path) -> None:
    """Write one case's figure, case file and truth into the bench temp dir."""
    d = root / case["name"]
    d.mkdir(parents=True, exist_ok=True)

    if case.get("bare_image"):
        fig = Fig()
        fig.d.ellipse([200, 150, 400, 330], fill=(120, 120, 130))
        fig.d.ellipse([250, 190, 320, 260], fill=(200, 200, 210))
        fig.save(d / "fig.png")
        (d / "case.json").write_text(json.dumps(
            {"case_id": case["name"], "images": [{"path": "fig.png"}]}, indent=2))
        (d / "truth.json").write_text(json.dumps(
            {"expect": "no frame detected, status undetermined or partial, no fabricated values"},
            indent=2))
        return

    fig = Fig()
    fig.frame()
    fig.ticks(case, case["xlim"], case["ylim"])

    env = {"sin": np.sin, "cos": np.cos, "log10": np.log10, "exp": np.exp, "sqrt": np.sqrt}
    for s in case.get("series", []):
        fig.series(lambda x, e=s["fn"]: eval(e, env, {"x": x}), case["xlim"], case["ylim"],
                   s["color"], logx=case.get("x_log", False), logy=case.get("y_log", False))

    mk = case.get("markers")
    if mk:
        err = (lambda x, e=mk["err"]: eval(e, env, {"x": x})) if mk.get("err") else None
        fig.markers(lambda x, e=mk["fn"]: eval(e, env, {"x": x}), case["xlim"], case["ylim"],
                    mk["color"], mk["x"], err=err)

    bars = case.get("bars")
    if bars:
        for i, v in enumerate(bars["values"]):
            fig.bar(case["xlim"], case["ylim"], bars["centers"][i], bars["width"], v, bars["color"])
        for i, v in enumerate(bars.get("errors") or []):
            fig.bar_err(case["xlim"], case["ylim"], bars["centers"][i],
                        bars["values"][i], v)
        if bars.get("sig_at") is not None:
            px = fig.px_x(bars["sig_at"], case["xlim"])
            py = fig.px_y(bars["values"][bars["centers"].index(bars["sig_at"])], case["ylim"])
            fig.d.text((px - 6, py - 18), "*", fill=(0, 0, 0))
            fig.d.text((px, py - 18), "*", fill=(0, 0, 0))
            fig.d.text((px + 6, py - 18), "*", fill=(0, 0, 0))

    fig.save(d / "fig.png")

    # Y tick values are written in reading order (top of the axis first). Sorting
    # by drawn pixel position gets that right for a normal axis and for an
    # inverted one alike, which is the whole point of case 06.
    y_sorted = sorted(case["y_ticks"],
                      key=lambda v: Fig().px_y(v, case["ylim"], case.get("y_log", False)))
    spec = {"path": "fig.png",
            "x_tick_values": list(case["x_ticks"]),
            "y_tick_values": y_sorted,
            "x_unit": "x", "y_unit": "y",
            "x_scale": "log" if case.get("x_log") else "linear",
            "y_scale": "log" if case.get("y_log") else "linear"}
    if case.get("y_inverted"):
        spec["y_axis_inverted"] = True
    (d / "case.json").write_text(json.dumps(
        {"case_id": case["name"], "images": [spec]}, indent=2))

    truth = {"xlim": list(case["xlim"]), "ylim": list(case["ylim"]),
             "x_log": bool(case.get("x_log")), "y_log": bool(case.get("y_log")),
             "series": [{"label": s["label"], "fn": s["fn"]} for s in case.get("series", [])]}
    if mk:
        truth["series"].append({"label": "markers", "fn": mk["fn"]})
    if bars:
        truth["bars"] = [{"x": bars["centers"][i], "value": v}
                         for i, v in enumerate(bars["values"])]
        if bars.get("errors"):
            truth["bar_errors"] = bars["errors"]
        if bars.get("sig_at") is not None:
            truth["has_significance_mark"] = True
    (d / "truth.json").write_text(json.dumps(truth, indent=2))


def run_figparse(case_dir: Path, force_linear: bool = False) -> dict:
    case = json.loads((case_dir / "case.json").read_text(encoding="utf-8"))
    if force_linear:
        for im in case["images"]:
            im["x_scale"] = im["y_scale"] = "linear"
    tmp = Path(tempfile.mkdtemp())
    try:
        (tmp / "case.json").write_text(json.dumps(case), encoding="utf-8")
        shutil.copy(case_dir / "fig.png", tmp / "fig.png")
        r = subprocess.run([sys.executable, str(FIGPARSE), "run",
                            "--case", str(tmp / "case.json"), "--out", str(tmp / "out")],
                           capture_output=True, text=True, timeout=120)
        if r.returncode != 0:
            return {"status": "error", "stderr": r.stderr[-800:]}
        return json.loads((tmp / "out" / "result.json").read_text(encoding="utf-8"))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def score_case(case_dir: Path, result: dict) -> dict:
    truth = json.loads((case_dir / "truth.json").read_text(encoding="utf-8"))
    if "expect" in truth:
        panels = result.get("panels", [])
        ok = bool(panels) and all(p.get("frame_px") is None for p in panels)
        return {"case": case_dir.name, "kind": "no-frame", "status": result.get("status"),
                "pass": ok, "note": "frame refused" if ok else "invented a frame"}

    env = {"sin": np.sin, "cos": np.cos, "log10": np.log10, "exp": np.exp, "sqrt": np.sqrt}
    panels = [p for p in result.get("panels", []) if p.get("series")]
    if not panels:
        return {"case": case_dir.name, "status": result.get("status"), "pass": False,
                "note": "no digitised series"}

    truth_bars = truth.get("bars")
    bar_entries = [s for p in panels for s in p.get("series", []) if s.get("chart_type") == "bar"]
    if truth_bars:
        if not bar_entries:
            return {"case": case_dir.name, "status": result.get("status"), "pass": False,
                    "note": "no bar series detected"}
        tol = 0.02 * abs(truth["ylim"][1] - truth["ylim"][0])
        errs = []
        for tb in truth_bars:
            best = min(bar_entries[0].get("bars", []),
                       key=lambda b: abs(b["x_center"] - tb["x"]), default=None)
            if best is None:
                return {"case": case_dir.name, "status": result.get("status"),
                        "pass": False, "note": "bar list empty"}
            errs.append(abs(best["top_value"] - tb["value"]))
        row = {"case": case_dir.name, "kind": "bar", "status": result.get("status"),
               "worst_max_error": round(max(errs), 3), "tolerance": round(tol, 3),
               "n_bars_read": sum(len(s.get("bars", [])) for s in bar_entries),
               "n_bars_truth": len(truth_bars)}
        row["pass"] = (max(errs) <= tol and row["n_bars_read"] == row["n_bars_truth"])
        if truth.get("bar_errors") and row["pass"]:
            cands = [c for s in bar_entries
                     for c in s.get("annotations", {}).get("error_bar_candidates", [])]
            row["pass"] = row["pass"] and len(cands) >= len(truth["bar_errors"])
        if truth.get("has_significance_mark") and row["pass"]:
            marks = [c for s in bar_entries
                     for c in s.get("annotations", {}).get("marker_candidates", [])]
            row["pass"] = row["pass"] and len(marks) >= 1
        return row

    errs = []
    for s in panels[0]["series"]:
        gx = np.array(s["x"], dtype=float)
        gy = np.array(s["y"], dtype=float)
        if s.get("x_unit") == "axis_fraction":
            return {"case": case_dir.name, "status": result.get("status"), "pass": False,
                    "note": "fell back to axis_fraction, no physical units"}
        best = None
        for t in truth.get("series", []):
            ty = np.array([eval(t["fn"], env, {"x": float(x)}) for x in gx], dtype=float)
            e = np.abs(gy - ty)
            # On a log axis the reading error is multiplicative, so rank and
            # report relative error there.
            metric = e / np.maximum(np.abs(ty), 1e-12) if truth.get("y_log") else e
            if best is None or np.median(metric) < best[0]:
                best = (float(np.median(metric)), float(np.max(metric)), t["label"])
        if best:
            errs.append({"metric": best[0], "max": best[1], "label": best[2]})

    if not errs:
        return {"case": case_dir.name, "status": result.get("status"), "pass": False,
                "note": "series could not be matched to any truth curve"}

    log_axis = bool(truth.get("y_log"))
    worst = max(e["max"] for e in errs)
    # Linear axes: worst error under 2% of the plotted y span.
    # Log axes: worst relative error under 10% (about the stroke width).
    tol = 0.10 if log_axis else 0.02 * abs(truth["ylim"][1] - truth["ylim"][0])
    return {"case": case_dir.name, "status": result.get("status"),
            "worst_max_error": round(worst, 4 if log_axis else 3),
            "error_kind": "relative" if log_axis else "absolute",
            "tolerance": round(tol, 4 if log_axis else 3),
            "pass": worst <= tol}


# --- table scenarios ---------------------------------------------------------

def run_tables(files: list[Path], case_obj: dict | None, work: Path) -> dict:
    out = work / "tables_out"
    cmd = [sys.executable, str(TABLES)] + [str(f) for f in files] + ["--out", str(out)]
    if case_obj is not None:
        cp = work / "case.json"
        cp.write_text(json.dumps(case_obj), encoding="utf-8")
        cmd += ["--case", str(cp)]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    if r.returncode != 0:
        return {"status": "error", "stderr": r.stderr[-800:]}
    return json.loads((out / "result.json").read_text(encoding="utf-8"))


def table_scenarios(work: Path) -> list[dict]:
    work.mkdir(parents=True, exist_ok=True)
    rows = []

    # T1: a CSV whose columns type cleanly; a percent column keeps the printed
    # number (12% stays 12, never 0.12) and says so.
    csv = work / "t1.csv"
    csv.write_text("concentration_uM,inhibition,replicate\n1.5,12%,A\n2.0,25%,A\n3.1,41%,B\n",
                   encoding="utf-8")
    res = run_tables([csv], None, work)
    tables = [t for t in res.get("tables", []) if t.get("ok")]
    cols = {c["column"]: c for t in tables for c in t.get("columns", [])}
    ok = (res.get("status") != "error" and len(tables) == 1
          and cols.get("concentration_uM", {}).get("kind") == "numeric"
          and cols.get("inhibition", {}).get("kind") == "numeric"
          and cols.get("inhibition", {}).get("unit_hint") == "percent"
          and cols.get("inhibition", {}).get("values") == [12.0, 25.0, 41.0]
          and cols.get("replicate", {}).get("kind") == "text")
    rows.append({"scenario": "tables_csv_typed_percent", "pass": bool(ok),
                 "note": "" if ok else json.dumps(cols, ensure_ascii=False)[:200]})

    # T2: a markdown pipe table parses to header plus rows; a text column keeps
    # its cells verbatim and names which cells are not numeric.
    md = work / "t2.md"
    md.write_text("| sample | yield |\n|---|---|\n| A1 | 82 |\n| B2 | n/a |\n| C3 | 77 |\n",
                  encoding="utf-8")
    res = run_tables([md], None, work)
    tables = [t for t in res.get("tables", []) if t.get("ok")]
    cols = {c["column"]: c for t in tables for c in t.get("columns", [])}
    ok = (res.get("status") != "error" and len(tables) == 1
          and cols.get("sample", {}).get("kind") == "text"
          and cols.get("sample", {}).get("values") == ["A1", "B2", "C3"]
          and cols.get("yield", {}).get("kind") == "text"
          and cols.get("yield", {}).get("non_numeric_cells") == [1])
    rows.append({"scenario": "tables_markdown_text_column", "pass": bool(ok),
                 "note": "" if ok else json.dumps(cols, ensure_ascii=False)[:200]})

    # T3: unparseable input is refused by name — a missing file and a JSON that
    # is not an array of records each report ok false with a reason, the rest of
    # the batch still lands, and the case_id travels through.
    missing = work / "nope.csv"
    bad = work / "bad.json"
    bad.write_text('{"not": "a record array"}', encoding="utf-8")
    res = run_tables([missing, bad], {"case_id": "tables-refusal-demo"}, work)
    entries = res.get("tables", [])
    refused = [t for t in entries if not t.get("ok")]
    ok = (res.get("status") != "error" and len(refused) == 2
          and all(t.get("reason") for t in refused)
          and res.get("case_id") == "tables-refusal-demo")
    rows.append({"scenario": "tables_refusal_by_name", "pass": bool(ok),
                 "note": "" if ok else json.dumps(entries, ensure_ascii=False)[:200]})
    return rows


def main() -> int:
    rows: list[dict] = []
    abl_rows: list[dict] = []
    root = Path(tempfile.mkdtemp(prefix="figbench_"))
    try:
        cases = build_cases()
        for c in cases:
            emit(c, root / "cases")
        for d in sorted((root / "cases").iterdir()):
            res = run_figparse(d)
            rows.append(score_case(d, res))
            if res.get("status") != "error":
                abl_rows.append(score_case(d, run_figparse(d, force_linear=True)))
        rows += table_scenarios(root / "tables")
    finally:
        shutil.rmtree(root, ignore_errors=True)

    passed = sum(1 for r in rows if r.get("pass"))
    abl_passed = sum(1 for r in abl_rows if r.get("pass"))
    for r in rows:
        label = r.get("case") or r.get("scenario") or "?"
        print(("PASS" if r.get("pass") else "FAIL") + "  " + label)
        if not r.get("pass"):
            print("      " + json.dumps(r, ensure_ascii=False)[:200])
    (SCRIPTS / "report_figparse.json").write_text(json.dumps(
        {"schema_version": "figparse-bench/v1",
         "scenarios": rows,
         "totals": {"passed": passed, "of": len(rows)},
         "ablation_forced_linear": {"passed": abl_passed, "of": len(abl_rows),
                                    "note": ("same pipeline with log-axis detection disabled; "
                                             "an ablation of this tool, not a measurement of "
                                             "any other agent or product")}},
        ensure_ascii=False, indent=2), encoding="utf-8")
    print()
    print(f"{passed}/{len(rows)} scenarios pass")
    return 0 if passed == len(rows) else 1


if __name__ == "__main__":
    raise SystemExit(main())
