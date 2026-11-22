"""Self-test: draw a figure whose true data is known, then measure recovery error.

This is how the skill earns its "更准" claim — the error below is measured
against ground truth generated here, not asserted in prose.

    python scripts/selftest.py
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

HERE = Path(__file__).resolve().parent

# --- ground truth geometry -------------------------------------------------
W, H = 640, 480
LEFT, RIGHT, TOP, BOTTOM = 90, 600, 60, 400
X_RANGE = (0.0, 10.0)
Y_RANGE = (0.0, 100.0)
X_TICKS = [0, 2, 4, 6, 8, 10]
Y_TICKS = [0, 20, 40, 60, 80, 100]
RED = (220, 40, 40)
BLUE = (40, 80, 220)


def x_to_px(v: float) -> float:
    return LEFT + (v - X_RANGE[0]) / (X_RANGE[1] - X_RANGE[0]) * (RIGHT - LEFT)


def y_to_px(v: float) -> float:
    return BOTTOM - (v - Y_RANGE[0]) / (Y_RANGE[1] - Y_RANGE[0]) * (BOTTOM - TOP)


def truth_red(x: np.ndarray) -> np.ndarray:
    return 50 + 30 * np.sin(x * 0.6)


def truth_blue(x: np.ndarray) -> np.ndarray:
    return 20 + 4.0 * x


def make_figure(path: Path) -> None:
    im = Image.new("RGB", (W, H), "white")
    d = ImageDraw.Draw(im)

    # Spines: left + bottom only, like most journal plots.
    d.line([(LEFT, TOP), (LEFT, BOTTOM)], fill=(0, 0, 0), width=2)
    d.line([(LEFT, BOTTOM), (RIGHT, BOTTOM)], fill=(0, 0, 0), width=2)

    # Ticks point outward, 5 px long.
    for v in X_TICKS:
        px = x_to_px(v)
        d.line([(px, BOTTOM + 1), (px, BOTTOM + 5)], fill=(0, 0, 0), width=2)
    for v in Y_TICKS:
        py = y_to_px(v)
        d.line([(LEFT - 5, py), (LEFT - 1, py)], fill=(0, 0, 0), width=2)

    xs = np.linspace(0.5, 9.5, 400)
    d.line([(x_to_px(x), y_to_px(y)) for x, y in zip(xs, truth_red(xs))], fill=RED, width=3)
    d.line([(x_to_px(x), y_to_px(y)) for x, y in zip(xs, truth_blue(xs))], fill=BLUE, width=3)

    im.save(path)


def run_case(tmp: Path) -> dict:
    img = tmp / "fig.png"
    make_figure(img)
    case = tmp / "case.json"
    case.write_text(json.dumps({
        "case_id": "selftest-synthetic",
        "images": [{
            "path": "fig.png",
            "x_tick_values": X_TICKS, "x_unit": "s",
            # y values listed in reading order (top -> bottom), per the
            # convention documented in SKILL.md.
            "y_tick_values": list(reversed(Y_TICKS)), "y_unit": "mV",
        }],
    }), encoding="utf-8")

    out = tmp / "out"
    r = subprocess.run([sys.executable, str(HERE / "figparse.py"), "run",
                        "--case", str(case), "--out", str(out)],
                       capture_output=True, text=True)
    if r.returncode != 0:
        raise SystemExit(f"figparse failed:\n{r.stdout}\n{r.stderr}")
    return json.loads((out / "result.json").read_text(encoding="utf-8"))


def score(result: dict) -> dict:
    xs = np.linspace(0.5, 9.5, 200)
    report = {"panels": len(result["panels"]), "series": [], "status": result["status"]}

    for series in result["panels"][0]["series"]:
        gx = np.array(series["x"], dtype=float)
        gy = np.array(series["y"], dtype=float)
        # Annotate each digitised point against whichever truth curve is closer.
        err_red = np.abs(gy - truth_red(gx))
        err_blue = np.abs(gy - truth_blue(gx))
        if np.median(err_red) <= np.median(err_blue):
            err, name = err_red, "red"
        else:
            err, name = err_blue, "blue"
        report["series"].append({
            "appearance_hue": series["appearance"]["median_hue_deg"],
            "matched_curve": name,
            "max_abs_error": round(float(err.max()), 3),
            "p95_abs_error": round(float(np.percentile(err, 95)), 3),
            "x_span": [round(float(gx.min()), 3), round(float(gx.max()), 3)],
        })

    with open(HERE / ".." / "examples" / "selftest-report.json", "w", encoding="utf-8") as fh:
        json.dump({"note": "synthetic ground truth, not an official case result", **report},
                  fh, indent=2)
    return report


def main() -> int:
    with tempfile.TemporaryDirectory() as td:
        res = run_case(Path(td))
    rep = score(res)

    print(json.dumps(rep, indent=2))
    worst = max((s["max_abs_error"] for s in rep["series"]), default=float("inf"))
    ok = rep["status"] == "success" and len(rep["series"]) == 2 and worst < 2.0
    print(f"\n{'PASS' if ok else 'FAIL'}: worst max_abs_error={worst} (tolerance 2.0 units)")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
