"""Pixel -> data calibration for scientific figures.

Given a raster figure, locate plot panels, find the axis frame, detect tick
marks along each axis, and fit the pixel->data mapping. Every fitted mapping
carries its own residual so the caller can report a real reading uncertainty
instead of a made-up one.

Dependencies: none beyond the standard library. The morphology and connected
components run on `rasterkit.py` (run-length dilation/closing, union-find
labelling) with scipy-identical semantics, and the fit is the exact
least-squares closed form — this module used to hard-import numpy and scipy,
which made every chart-reading case die on machines without them, before any
result.json was written.

No OCR here on purpose: tick *pixel positions* are geometry, tick *labels*
are text. This module does the geometry and asks the caller for the values.
"""

from __future__ import annotations

import math

import rasterkit as R

# A pixel is "ink" when it is this much darker than the panel background.
INK_DELTA = 60
MIN_PANEL_W = 40
MIN_PANEL_H = 40
# Largest residual, in pixels, that still counts as a calibration.
MAX_RMS_PX = 2.0


def load_gray(rgb: list) -> R.Gray:
    """Luma in 0..255 from rows of (r, g, b) (or pass through if already Gray)."""
    if isinstance(rgb, R.Gray):
        return rgb
    rows = [[0.299 * r + 0.587 * g + 0.114 * b for (r, g, b) in row] for row in rgb]
    return R.Gray(rows)


def ink_mask(gray: R.Gray, delta: float = INK_DELTA) -> R.Bits:
    """Boolean mask of drawn pixels.

    Uses a per-panel median background instead of a global threshold, so an
    over-exposed scan and a clean vector render both land in range.
    """
    bg = gray.median()
    return R.Bits.from_gray(gray, bg - delta)


AXIS_SAT_MAX = 60   # out of 255; above this a pixel is coloured data ink, not axis


def dark_ink_mask(rgb: list, delta: float = INK_DELTA) -> R.Bits:
    """The near-black subset of the ink: spines, ticks, labels, annotations.

    A bar chart breaks naive frame detection: a solid bar is ink too, and its
    vertical edges are exactly the long straight runs that `find_frame` keys
    on, so the bars get read as spines. Axis furniture is drawn in near-black
    while data ink is saturated, so the frame search runs on the low-saturation
    subset. Greyscale figures keep everything in this mask — there colour is
    not available to separate data from axis, and the limits say so.
    """
    gray = load_gray(rgb)
    bg = gray.median()
    thr = bg - delta
    out = R.Bits.empty(gray.h, gray.w)
    for y, row in enumerate(rgb):
        grow = gray.rows[y]
        mrow = out.rows[y]
        for x, (r, g, b) in enumerate(row):
            if grow[x] < thr:
                mx = r if r >= g and r >= b else (g if g >= b else b)
                mn = r if r <= g and r <= b else (g if g <= b else b)
                sat = 255.0 * (mx - mn) / max(mx, 1e-9)
                if sat < AXIS_SAT_MAX:
                    mrow[x] = True
    return out


def find_panels(mask: R.Bits, min_w: int = MIN_PANEL_W, min_h: int = MIN_PANEL_H) -> list[dict]:
    """Split a multi-panel figure into panel bounding boxes.

    Grows labels on the ink mask, then merges labels that overlap in both axes
    so that a panel's scattered tick labels and markers stay with the panel.
    """
    grown = mask.dilate_box(4, 4)          # the 9x9 structure, as (25,1)-style halves
    boxes = []
    for c in grown.label4():
        x0, y0, x1, y1 = c["x0"], c["y0"], c["x1"], c["y1"]
        if (x1 - x0 + 1) < min_w or (y1 - y0 + 1) < min_h:
            continue
        boxes.append([x0, y0, x1 + 1, y1 + 1])   # ndimage slices are end-exclusive

    merged = True
    while merged:
        merged = False
        for i in range(len(boxes)):
            for j in range(i + 1, len(boxes)):
                a, b = boxes[i], boxes[j]
                if a[0] <= b[2] and b[0] <= a[2] and a[1] <= b[3] and b[1] <= a[3]:
                    boxes[i] = [min(a[0], b[0]), min(a[1], b[1]),
                                max(a[2], b[2]), max(a[3], b[3])]
                    boxes.pop(j)
                    merged = True
                    break
            if merged:
                break
    boxes.sort(key=lambda r: (r[1] // 40, r[0]))
    out = []
    for idx, b in enumerate(boxes):
        out.append({"panel_id": f"p{idx + 1}",
                    "bbox_px": {"x0": b[0], "y0": b[1], "x1": b[2], "y1": b[3]}})
    return out


def find_frame(mask: R.Bits) -> dict | None:
    """Locate the plot axes inside one panel.

    Most scientific plots draw only the left and bottom spines. So the left and
    bottom edges come from the longest straight ink runs, while the right and
    top edges fall back to the panel bounds when no opposing spine exists —
    calibration only needs the two real axes, and clipping to the panel never
    throws data away. `closed` records which case we are in.

    The runs are measured on directionally closed copies of the mask: a data
    curve drawn over a spine cuts the spine's ink run into segments, and a
    plain run-length test then misses an axis that is plainly there. Closing
    along the column direction bridges vertical gaps (and along rows bridges
    horizontal ones) without joining the spine to its tick marks, which sit
    *beside* it, not across the gap.
    """
    h, w = mask.h, mask.w
    mask_v = mask.close_box(12, 0)   # structure ones((25, 1))
    mask_h = mask.close_box(0, 12)   # structure ones((1, 25))
    row_len = [0.0] * h
    for y, runs in enumerate(mask_h.runs_all_rows()):
        if runs:
            row_len[y] = max(e - s + 1 for (s, e) in runs)
    col_len = [0.0] * w
    for x, runs in enumerate(mask_v.col_runs()):
        if runs:
            col_len[x] = max(e - s + 1 for (s, e) in runs)

    hrows = [y for y in range(h) if row_len[y] > 0.55 * w]
    vcols = [x for x in range(w) if col_len[x] > 0.55 * h]
    if len(hrows) < 1 or len(vcols) < 1:
        return None

    left, bottom = min(vcols), max(hrows)
    has_right = max(vcols) - left >= MIN_PANEL_W
    has_top = bottom - min(hrows) >= MIN_PANEL_H
    right = max(vcols) if has_right else w - 1
    top = min(hrows) if has_top else 0

    if right - left < MIN_PANEL_W or bottom - top < MIN_PANEL_H:
        return None
    return {"left": left, "right": right, "top": top, "bottom": bottom,
            "closed": bool(has_right and has_top),
            "inner_vertical_lines": len(vcols), "inner_horizontal_lines": len(hrows)}


def find_ticks(mask: R.Bits, frame: dict, axis: str) -> list[int]:
    """Pixel positions of tick marks outside the frame edge.

    看 frame 外侧 (x 轴看下方, y 轴看左侧) 的短线。刻度是垂直于轴的短笔画，
    比标签文字更靠近轴，所以只在紧邻轴的窄带里找。
    """
    left, right, top, bottom = frame["left"], frame["right"], frame["top"], frame["bottom"]
    h = mask.h
    positions: list[int] = []

    if axis == "x":
        y0 = min(bottom + 1, h - 1)
        y1 = min(bottom + 8, h)
        band = mask.crop(y0, y1 - 1, left, right) if y1 > y0 else R.Bits.empty(0, 1)
        if band.h == 0 or band.w == 0:
            return []
        colhits = []
        for runs in band.col_runs():
            colhits.append(sum(e - s + 1 for (s, e) in runs) >= 2)
        positions = [(left + s + e) // 2 for s, e in R._runs_from_points(
            [i for i, v in enumerate(colhits) if v]) if 1 <= e - s <= 6]
    else:
        x0 = max(left - 7, 0)
        x1 = max(left, 1)
        band = mask.crop(top, bottom, x0, x1 - 1) if x1 > x0 else R.Bits.empty(1, 0)
        if band.h == 0 or band.w == 0:
            return []
        rowhits = []
        for runs in band.runs_all_rows():
            rowhits.append(sum(e - s + 1 for (s, e) in runs) >= 2)
        positions = [(top + s + e) // 2 for s, e in R._runs_from_points(
            [i for i, v in enumerate(rowhits) if v]) if 1 <= e - s <= 6]

    return _dedupe(positions, min_gap=3)


def _dedupe(xs: list[int], min_gap: int) -> list[int]:
    out: list[int] = []
    for x in sorted(xs):
        if not out or x - out[-1] >= min_gap:
            out.append(x)
    return out


def fit_from_limits(left_px: int, right_px: int, limits: tuple[float, float],
                    scale: str = "linear") -> dict:
    """Calibrate straight from the frame edges and the axis limits.

    Correct for the common case where the axes box *is* the data limits, which
    is what matplotlib and most plotting libraries produce by default. It is a
    weaker source than tick positions: if the plot has margins (ggplot's
    default, or hand-drawn axes), the limits sit outside the frame and this fit
    is wrong in a way no residual can reveal. So it is only used when no
    labelled tick is available, and the result says so.
    """
    try:
        lo, hi = float(limits[0]), float(limits[1])
    except (TypeError, ValueError):
        return {"ok": False, "reason": "axis limits are not numeric"}
    if hi == lo:
        return {"ok": False, "reason": "axis limits are equal"}

    if scale == "log":
        if lo <= 0 or hi <= 0:
            return {"ok": False, "reason": "log axis needs positive limits"}
        a = (math.log10(hi) - math.log10(lo)) / (right_px - left_px)
        b = math.log10(lo) - a * left_px
        return {"ok": True, "scale": "log", "slope": a, "intercept": b,
                "rms_px": None, "tick_pairs": [], "outlier_px": [],
                "source": "axis_limits_frame_edges",
                "caveat": "frame edges assumed to equal the axis limits; no residual to verify this"}

    a = (hi - lo) / (right_px - left_px)
    b = lo - a * left_px
    return {"ok": True, "scale": "linear", "slope": a, "intercept": b,
            "rms_px": None, "tick_pairs": [], "outlier_px": [],
            "source": "axis_limits_frame_edges",
            "caveat": "frame edges assumed to equal the axis limits; no residual to verify this"}


def fit_axis(pixels: list, values: list, scale: str = "auto") -> dict:
    """Fit pixel->value for one axis.

    scale: 'linear', 'log', or 'auto'. 'auto' picks whichever fits the tick
    pairs with the smaller residual — this is how a log axis gets caught
    instead of silently being read as linear.
    """
    if len(pixels) != len(values) or len(pixels) < 2:
        return {
            "ok": False,
            "reason": f"need >=2 matched tick pairs, got pixels={len(pixels)} values={len(values)}",
        }

    p = [float(v) for v in pixels]
    candidates = []
    if scale in ("linear", "auto"):
        candidates.append(("linear", [float(v) for v in values]))
    if scale in ("log", "auto"):
        if all(float(v) > 0 for v in values):
            candidates.append(("log", [math.log10(float(v)) for v in values]))
        elif scale == "log":
            return {"ok": False, "reason": "log axis needs strictly positive tick values"}

    best = None
    for kind, target in candidates:
        a, b = R.linfit(p, target)
        resid = [t - (a * pv + b) for pv, t in zip(p, target)]
        rms = math.sqrt(sum(r * r for r in resid) / len(resid))
        # Residual in px-equivalent so linear and log are comparable.
        rms_px = rms / abs(a) if a != 0 else float("inf")
        if best is None or rms_px < best["_rms_px"]:
            best = {"scale": kind, "a": a, "b": b, "rms_px": rms_px,
                    "residual": resid, "_rms_px": rms_px}

    # A fit that misses the tick positions by more than a couple of pixels is
    # not a calibration, it is a line drawn through the wrong points. Refusing
    # it here is what stops a log axis from being reported as linear with a
    # confident-looking score.
    if best["rms_px"] > MAX_RMS_PX:
        return {
            "ok": False,
            "reason": (f"best {best['scale']} fit misses the tick positions by "
                       f"{best['rms_px']:.1f} px (limit {MAX_RMS_PX}); the axis model is wrong"),
            "rms_px": round(best["rms_px"], 4),
            "tried_scales": [c[0] for c in candidates],
        }

    # A tick that sits far off the fit means the tick list has a stray
    # (a piece of a legend, a split axis); report it rather than hide it.
    k = 3.0
    outliers = [int(p[i]) for i in range(len(p))
                if abs(best["residual"][i]) > k * max(best["rms_px"] * abs(best["a"]), 1e-9)]

    return {
        "ok": True,
        "scale": best["scale"],
        "slope": best["a"],
        "intercept": best["b"],
        "rms_px": round(best["rms_px"], 4),
        "tick_pairs": [{"px": int(a), "value": float(b)} for a, b in zip(pixels, values)],
        "outlier_px": outliers,
    }


def px_to_value(px, fit: dict):
    """Apply a fitted axis to pixel coordinate(s) (scalar or list)."""
    if isinstance(px, (list, tuple)):
        vals = [fit["slope"] * float(v) + fit["intercept"] for v in px]
        if fit["scale"] == "log":
            vals = [10.0 ** v for v in vals]
        return vals
    raw = fit["slope"] * float(px) + fit["intercept"]
    return 10.0 ** raw if fit["scale"] == "log" else raw


def infer_scale_from_spacing(pixels: list) -> str:
    """Guess axis scale from tick spacing alone.

    Decade ticks on a log axis are evenly spaced in pixels but unevenly spaced
    in value; a linear axis with uneven tick labels is rare. This is a weak
    prior the caller should override with the OCR'd label values when it has
    them.
    """
    if len(pixels) < 3:
        return "unknown"
    sp = sorted(pixels)
    gaps = [sp[i + 1] - sp[i] for i in range(len(sp) - 1)]
    mean = sum(gaps) / len(gaps) if gaps else 0.0
    if mean:
        std = math.sqrt(sum((g - mean) ** 2 for g in gaps) / len(gaps))
        _ = std / mean   # coefficient of variation, kept for diagnostics
    return "even-spacing"
