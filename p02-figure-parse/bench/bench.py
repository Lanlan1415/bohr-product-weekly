"""Benchmark question set and scorer for figure-parse.

    python bench/bench.py make            # write bench/cases/*/
    python bench/bench.py score           # run the skill, score against truth
    python bench/bench.py score --verbose

Each case is a generated figure with an analytic ground truth, so the error
below is measured against a known answer rather than estimated. Cases cover the
things the skill claims to handle and the things that break naive readers:
log axes, an inverted axis, markers-only, error bars, multiple panels, and a
bare image panel with no frame at all.

The score run also executes an ablation: the same pipeline with log detection
disabled and forced to linear. The gap between the two is the measured value of
axis-type discrimination, which is one of the capabilities this skill claims.
Both are reported; neither is presented as a measurement of any competing tool.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

HERE = Path(__file__).resolve().parent
SCRIPTS = HERE.parent / "scripts"
CASES = HERE / "cases"

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
        """Tick marks at the positions the case declares, inside the axis span."""
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
        """One solid column from the baseline up to `value`."""
        x0 = self.px_x(x_center - width / 2, xlim)
        x1 = self.px_x(x_center + width / 2, xlim)
        ytop = self.px_y(value, ylim)
        self.d.rectangle([x0, ytop, x1, self.bottom], fill=color)
        return ytop

    def bar_err(self, xlim, ylim, x_center, value, err, half_w=6):
        """A black error bar above one bar's top, like a bar chart carries."""
        px = self.px_x(x_center, xlim)
        ytop = self.px_y(value, ylim)
        yup = self.px_y(value + err, ylim)
        self.d.line([(px, yup), (px, ytop)], fill=(0, 0, 0), width=2)
        self.d.line([(px - half_w, yup), (px + half_w, yup)], fill=(0, 0, 0), width=2)
        self.d.line([(px - half_w, ytop), (px + half_w, ytop)], fill=(0, 0, 0), width=2)
        return yup

    def save(self, path: Path):
        self.im.save(path)


def build_cases() -> list[dict]:
    """Case definitions. `truth` is analytic, so the error is against a known answer."""
    cases = []

    # 1. Plain linear scatter-free line pair: the easy baseline.
    cases.append(dict(
        name="01-linear-two-series",
        xlim=(0.0, 10.0), ylim=(0.0, 100.0),
        x_ticks=[0, 2, 4, 6, 8, 10], y_ticks=[0, 20, 40, 60, 80, 100],
        series=[
            {"color": RED, "fn": "50+30*sin(0.6*x)", "label": "red"},
            {"color": BLUE, "fn": "20+4*x", "label": "blue"},
        ],
    ))

    # 2. log x axis: a linear reader misplaces every point far from the ticks.
    cases.append(dict(
        name="02-log-x",
        xlim=(1.0, 1000.0), ylim=(0.0, 100.0), x_log=True,
        x_ticks=[1, 10, 100, 1000], y_ticks=[0, 25, 50, 75, 100],
        series=[{"color": BLUE, "fn": "10+25*log10(x)", "label": "blue"}],
    ))

    # 3. log y axis.
    cases.append(dict(
        name="03-log-y",
        xlim=(0.0, 10.0), ylim=(1.0, 10000.0), y_log=True,
        x_ticks=[0, 2, 4, 6, 8, 10], y_ticks=[1, 10, 100, 1000, 10000],
        series=[{"color": RED, "fn": "10**(2+0.3*x)", "label": "red"}],
    ))

    # 4. Three series, one of them crossing the others.
    cases.append(dict(
        name="04-three-series",
        xlim=(0.0, 10.0), ylim=(0.0, 100.0),
        x_ticks=[0, 2, 4, 6, 8, 10], y_ticks=[0, 20, 40, 60, 80, 100],
        series=[
            {"color": RED, "fn": "20+6*x", "label": "red"},
            {"color": BLUE, "fn": "90-7*x", "label": "blue"},
            {"color": GREEN, "fn": "55+20*sin(0.9*x)", "label": "green"},
        ],
    ))

    # 5. Markers only with error bars.
    cases.append(dict(
        name="05-markers-errorbars",
        xlim=(0.0, 10.0), ylim=(0.0, 100.0),
        x_ticks=[0, 2, 4, 6, 8, 10], y_ticks=[0, 20, 40, 60, 80, 100],
        markers={"color": RED, "fn": "30+5*x", "err": "4+0.5*x",
                 "x": [0.5, 1.5, 2.5, 3.5, 4.5, 5.5, 6.5, 7.5, 8.5, 9.5]},
        series=[],
    ))

    # 6. Inverted y axis (y grows downward) -- rare, but it exists in the wild
    #    and a reader that assumes the normal direction is silently mirrored.
    cases.append(dict(
        name="06-inverted-y",
        xlim=(0.0, 10.0), ylim=(100.0, 0.0), y_inverted=True,
        x_ticks=[0, 2, 4, 6, 8, 10], y_ticks=[100, 80, 60, 40, 20, 0],
        series=[{"color": BLUE, "fn": "80-5*x", "label": "blue"}],
    ))

    # 7. A bare image panel: no frame, so calibration must refuse rather than invent.
    cases.append(dict(name="07-no-frame", bare_image=True))

    # 8. A bar chart: solid columns. The per-column median that digitises a curve
    #    reads a bar as a horizontal line through its middle, so this case scores
    #    the bar detector, not the curve path.
    cases.append(dict(
        name="08-bar-chart",
        xlim=(0.0, 4.0), ylim=(0.0, 100.0),
        x_ticks=[0, 1, 2, 3, 4], y_ticks=[0, 20, 40, 60, 80, 100],
        bars={"color": RED, "values": [35, 55, 80, 45],
              "centers": [0.5, 1.5, 2.5, 3.5], "width": 0.5},
        series=[],
    ))

    # 9. Bars with black error bars and a significance mark above them: the marks
    #    are invisible to the colour mask, so this scores the annotation search.
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


def emit(case: dict, root: Path) -> dict:
    """Write one case's figure, case.json and truth.json."""
    d = root / case["name"]
    d.mkdir(parents=True, exist_ok=True)

    if case.get("bare_image"):
        fig = Fig()
        # A blob with no axes at all, like a micrograph.
        fig.d.ellipse([200, 150, 400, 330], fill=(120, 120, 130))
        fig.d.ellipse([250, 190, 320, 260], fill=(200, 200, 210))
        fig.save(d / "fig.png")
        (d / "case.json").write_text(json.dumps(
            {"case_id": case["name"], "images": [{"path": "fig.png"}]}, indent=2))
        (d / "truth.json").write_text(json.dumps(
            {"expect": "no frame detected, status undetermined or partial, no fabricated values"},
            indent=2))
        return case

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

    # Y tick values must be written in reading order: top of the axis first,
    # bottom last. Sorting by drawn pixel position gets that right for a normal
    # axis and for an inverted one alike, which is the whole point of case 06.
    fig2 = Fig()
    y_sorted = sorted(case["y_ticks"],
                      key=lambda v: fig2.px_y(v, case["ylim"], case.get("y_log", False)))

    spec = {
        "path": "fig.png",
        # Values in reading order: x left->right, y top->bottom.
        "x_tick_values": [v for v in case["x_ticks"]],
        "y_tick_values": y_sorted,
        "x_unit": "x", "y_unit": "y",
        "x_scale": "log" if case.get("x_log") else "linear",
        "y_scale": "log" if case.get("y_log") else "linear",
    }
    if case.get("y_inverted"):
        spec["y_axis_inverted"] = True
    (d / "case.json").write_text(json.dumps(
        {"case_id": case["name"], "images": [spec]}, indent=2))

    truth = {
        "xlim": case["xlim"], "ylim": case["ylim"],
        "x_log": bool(case.get("x_log")), "y_log": bool(case.get("y_log")),
        "series": [{"label": s["label"], "fn": s["fn"], "color": s["color"]}
                   for s in case.get("series", [])],
    }
    if mk:
        # Scored against the marker curve too, so a markers-only panel is not
        # silently treated as "no truth to compare against".
        truth["series"].append({"label": "markers", "fn": mk["fn"], "color": mk["color"]})
        truth["markers"] = {"fn": mk["fn"], "x": mk["x"]}
    if bars:
        truth["bars"] = [{"x": bars["centers"][i], "value": v}
                         for i, v in enumerate(bars["values"])]
        if bars.get("errors"):
            truth["bar_errors"] = bars["errors"]
        if bars.get("sig_at") is not None:
            truth["has_significance_mark"] = True
    (d / "truth.json").write_text(json.dumps(truth, indent=2))
    return case


def run_figparse(case_dir: Path, force_linear: bool = False) -> dict:
    case = json.loads((case_dir / "case.json").read_text(encoding="utf-8"))
    if force_linear:
        for im in case["images"]:
            im.pop("x_scale", None)
            im.pop("y_scale", None)
            im["x_scale"] = im["y_scale"] = "linear"
    tmp = Path(tempfile.mkdtemp())
    (tmp / "case.json").write_text(json.dumps(case), encoding="utf-8")
    import shutil
    shutil.copy(case_dir / "fig.png", tmp / "fig.png")
    r = subprocess.run([sys.executable, str(SCRIPTS / "figparse.py"), "run",
                        "--case", str(tmp / "case.json"), "--out", str(tmp / "out")],
                       capture_output=True, text=True)
    if r.returncode != 0:
        return {"status": "error", "stderr": r.stderr[-800:]}
    return json.loads((tmp / "out" / "result.json").read_text(encoding="utf-8"))


def score_case(case_dir: Path, result: dict) -> dict:
    truth = json.loads((case_dir / "truth.json").read_text(encoding="utf-8"))
    if "expect" in truth:
        panels = result.get("panels", [])
        frames = [p.get("frame_px") for p in panels]
        ok = bool(panels) and all(f is None for f in frames)
        return {"case": case_dir.name, "kind": "no-frame", "status": result.get("status"),
                "pass": ok, "note": "frame refused" if ok else "invented a frame"}

    env = {"sin": np.sin, "cos": np.cos, "log10": np.log10, "exp": np.exp, "sqrt": np.sqrt}
    panels = [p for p in result.get("panels", []) if p.get("series")]
    if not panels:
        return {"case": case_dir.name, "status": result.get("status"), "pass": False,
                "note": "no digitised series"}

    # --- bar-chart cases: score the bar detector, not the curve path ---------
    truth_bars = truth.get("bars")
    bar_entries = [s for p in panels for s in p.get("series", [])
                   if s.get("chart_type") == "bar"]
    if truth_bars:
        if not bar_entries:
            curve_entries = [s for p in panels for s in p.get("series", [])
                             if s.get("chart_type") == "curve"]
            note = ("no bar series detected"
                    + ("; the panel fell back to the curve path, which reads bars as midlines"
                       if curve_entries else ""))
            return {"case": case_dir.name, "status": result.get("status"), "pass": False,
                    "note": note}
        tol = 0.02 * abs(truth["ylim"][1] - truth["ylim"][0])
        errs = []
        for tb in truth_bars:
            best = min(bar_entries[0].get("bars", []),
                       key=lambda b: abs(b["x_center"] - tb["x"]),
                       default=None)
            if best is None:
                return {"case": case_dir.name, "status": result.get("status"),
                        "pass": False, "note": "bar list empty"}
            errs.append(abs(best["top_value"] - tb["value"]))
        row = {"case": case_dir.name, "status": result.get("status"), "kind": "bar",
               "worst_max_error": round(max(errs), 3), "tolerance": round(tol, 3),
               "n_bars_read": sum(len(s.get("bars", [])) for s in bar_entries),
               "n_bars_truth": len(truth_bars)}
        row["pass"] = (max(errs) <= tol
                       and row["n_bars_read"] == row["n_bars_truth"])
        if truth.get("bar_errors") and row["pass"]:
            cands = [c for s in bar_entries
                     for c in s.get("annotations", {}).get("error_bar_candidates", [])]
            row["error_bar_candidates"] = len(cands)
            row["pass"] = row["pass"] and len(cands) >= len(truth["bar_errors"])
        if truth.get("has_significance_mark") and row["pass"]:
            marks = [c for s in bar_entries
                     for c in s.get("annotations", {}).get("marker_candidates", [])]
            row["marker_candidates"] = len(marks)
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
            # report relative error there. Comparing absolute values across four
            # decades would always look catastrophic and never be informative.
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
    # Log axes: worst relative error under 10%, which is about the stroke width
    # expressed as a multiplicative factor (see references/calibration-method.md).
    tol = 0.10 if log_axis else 0.02 * abs(truth["ylim"][1] - truth["ylim"][0])
    return {"case": case_dir.name, "status": result.get("status"),
            "worst_max_error": round(worst, 4 if log_axis else 3),
            "error_kind": "relative" if log_axis else "absolute",
            "tolerance": round(tol, 4 if log_axis else 3),
            "series_errors": [{"label": e["label"],
                               "max": round(e["max"], 4 if log_axis else 3),
                               "median": round(e["metric"], 4 if log_axis else 3)} for e in errs],
            "pass": worst <= tol}



def cmd_make(_a) -> int:
    CASES.mkdir(parents=True, exist_ok=True)
    for c in build_cases():
        emit(c, CASES)
    print(json.dumps({"wrote": str(CASES),
                      "cases": [c["name"] for c in build_cases()]}, indent=2))
    return 0


def cmd_score(a) -> int:
    dirs = sorted([d for d in CASES.iterdir() if d.is_dir()]) if CASES.exists() else []
    if not dirs:
        print("no cases; run `python bench/bench.py make` first", file=sys.stderr)
        return 1

    rows, abl_rows = [], []
    for d in dirs:
        res = run_figparse(d)
        rows.append(score_case(d, res))
        if res.get("status") != "error":
            abl_rows.append(score_case(d, run_figparse(d, force_linear=True)))

    def summarize(title: str, rs: list[dict]) -> dict:
        passed = [r for r in rs if r.get("pass")]
        return {"title": title, "passed": len(passed), "of": len(rs)}

    skill = summarize("figure-parse (auto)", rows)
    abl = summarize("ablation: forced linear", abl_rows)
    report = {
        "mode": "skill",
        "cases": rows,
        "totals": {"skill": skill, "ablation_linear": abl},
        "note": ("The ablation runs the same pipeline with log-axis detection disabled. It is an "
                 "ablation of this tool, not a measurement of any other agent or product."),
    }
    out = HERE / "report.json"
    out.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({"cases": [{"case": r["case"], "pass": r.get("pass"),
                                 "status": r.get("status"),
                                 "worst": r.get("worst_max_error"), "note": r.get("note")}
                                for r in rows],
                      "skil": skill, "ablation": abl, "wrote": str(out)}, indent=2))
    return 0 if skill["passed"] >= max(1, int(0.8 * len(rows))) else 1


def main() -> int:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    m = sub.add_parser("make"); m.set_defaults(func=cmd_make)
    s = sub.add_parser("score"); s.add_argument("--verbose", action="store_true")
    s.set_defaults(func=cmd_score)
    a = ap.parse_args()
    return a.func(a)


if __name__ == "__main__":
    raise SystemExit(main())
