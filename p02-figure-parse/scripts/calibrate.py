"""Pixel -> data calibration for scientific figures.

Given a raster figure, locate plot panels, find the axis frame, detect tick
marks along each axis, and fit the pixel->data mapping. Every fitted mapping
carries its own residual so the caller can report a real reading uncertainty
instead of a made-up one.

Dependencies: numpy, scipy (both in the pinned scientific-python image).
No OCR here on purpose: tick *pixel positions* are geometry, tick *labels*
are text. This module does the geometry and asks the caller for the values.
"""

from __future__ import annotations

import numpy as np
from scipy import ndimage

# A pixel is "ink" when it is this much darker than the panel background.
INK_DELTA = 60
MIN_PANEL_W = 40
MIN_PANEL_H = 40
# Largest residual, in pixels, that still counts as a calibration.
MAX_RMS_PX = 2.0


def load_gray(rgb: np.ndarray) -> np.ndarray:
    """Luma in 0..255 from an HxWx3 uint8 array (or pass through if already gray)."""
    a = np.asarray(rgb)
    if a.ndim == 3:
        a = a[..., :3] @ np.array([0.299, 0.587, 0.114])
    return a.astype(np.float64)


def ink_mask(gray: np.ndarray, delta: float = INK_DELTA) -> np.ndarray:
    """Boolean mask of drawn pixels.

    Uses a per-panel median background instead of a global threshold, so an
    over-exposed scan and a clean vector render both land in range.
    """
    bg = np.median(gray)
    return gray < (bg - delta)


AXIS_SAT_MAX = 60   # out of 255; above this a pixel is coloured data ink, not axis


def dark_ink_mask(rgb: np.ndarray, delta: float = INK_DELTA) -> np.ndarray:
    """The near-black subset of the ink: spines, ticks, labels, annotations.

    A bar chart breaks naive frame detection: a solid bar is ink too, and its
    vertical edges are exactly the long straight runs that `find_frame` keys
    on, so the bars get read as spines. Axis furniture is drawn in near-black
    while data ink is saturated, so the frame search runs on the low-saturation
    subset. Greyscale figures keep everything in this mask — there colour is
    not available to separate data from axis, and the limits say so.
    """
    gray = load_gray(rgb)
    dark = ink_mask(gray, delta)
    a = np.asarray(rgb, dtype=np.float64)
    if a.ndim == 2:
        return dark
    mx = a.max(-1)
    mn = a.min(-1)
    sat = 255.0 * (mx - mn) / np.maximum(mx, 1e-9)
    return dark & (sat < AXIS_SAT_MAX)


def _runs(flags: np.ndarray) -> list[tuple[int, int]]:
    """Maximal runs of True as inclusive (start, end) index pairs."""
    if not flags.any():
        return []
    d = np.diff(np.concatenate(([0], flags.astype(np.int8), [0])))
    starts = np.flatnonzero(d == 1)
    ends = np.flatnonzero(d == -1) - 1
    return list(zip(starts.tolist(), ends.tolist()))


def find_panels(mask: np.ndarray, min_w: int = MIN_PANEL_W, min_h: int = MIN_PANEL_H) -> list[dict]:
    """Split a multi-panel figure into panel bounding boxes.

    Grows labels on the ink mask, then merges labels that overlap in both axes
    so that a panel's scattered tick labels and markers stay with the panel.
    """
    # Dilate so nearby ink (curve + tick labels + axis) groups together.
    grown = ndimage.binary_dilation(mask, structure=np.ones((9, 9), bool))
    labels, n = ndimage.label(grown)
    boxes = []
    for sl in ndimage.find_objects(labels):
        if sl is None:
            continue
        y0, y1, x0, x1 = sl[0].start, sl[0].stop, sl[1].start, sl[1].stop
        if (x1 - x0) < min_w or (y1 - y0) < min_h:
            continue
        boxes.append([int(x0), int(y0), int(x1), int(y1)])

    merged = True
    while merged:
        merged = False
        for i in range(len(boxes)):
            for j in range(i + 1, len(boxes)):
                a, b = boxes[i], boxes[j]
                if a[0] <= b[2] and b[0] <= a[2] and a[1] <= b[3] and b[1] <= a[3]:
                    boxes[i] = [min(a[0], b[0]), min(a[1], b[1]), max(a[2], b[2]), max(a[3], b[3])]
                    boxes.pop(j)
                    merged = True
                    break
            if merged:
                break
    boxes.sort(key=lambda r: (r[1] // 40, r[0]))
    for idx, b in enumerate(boxes):
        b_ids = {"panel_id": f"p{idx + 1}", "bbox_px": {"x0": b[0], "y0": b[1], "x1": b[2], "y1": b[3]}}
        boxes[idx] = b_ids
    return boxes


def find_frame(mask: np.ndarray) -> dict | None:
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
    h, w = mask.shape
    mask_v = ndimage.binary_closing(mask, structure=np.ones((25, 1), bool))
    mask_h = ndimage.binary_closing(mask, structure=np.ones((1, 25), bool))
    row_len = np.array([max((e - s + 1 for s, e in _runs(mask_h[y])), default=0) for y in range(h)])
    col_len = np.array([max((e - s + 1 for s, e in _runs(mask_v[:, x])), default=0) for x in range(w)])

    hrows = np.flatnonzero(row_len > 0.55 * w)
    vcols = np.flatnonzero(col_len > 0.55 * h)
    if len(hrows) < 1 or len(vcols) < 1:
        return None

    left, bottom = int(vcols.min()), int(hrows.max())
    has_right = int(vcols.max()) - left >= MIN_PANEL_W
    has_top = bottom - int(hrows.min()) >= MIN_PANEL_H
    right = int(vcols.max()) if has_right else w - 1
    top = int(hrows.min()) if has_top else 0

    if right - left < MIN_PANEL_W or bottom - top < MIN_PANEL_H:
        return None
    return {"left": left, "right": right, "top": top, "bottom": bottom,
            "closed": bool(has_right and has_top),
            "inner_vertical_lines": int(len(vcols)), "inner_horizontal_lines": int(len(hrows))}


def find_ticks(mask: np.ndarray, frame: dict, axis: str) -> list[int]:
    """Pixel positions of tick marks outside the frame edge.

    看 frame 外侧 (x 轴看下方, y 轴看左侧) 的短线。刻度是垂直于轴的短笔画，
    比标签文字更靠近轴，所以只在紧邻轴的窄带里找。
    """
    left, right, top, bottom = frame["left"], frame["right"], frame["top"], frame["bottom"]
    h, w = mask.shape
    positions: list[int] = []

    if axis == "x":
        band = mask[min(bottom + 1, h - 1):min(bottom + 8, h), left:right + 1]
        if band.size == 0:
            return []
        colhits = band.sum(axis=0) >= 2
        positions = [(left + s + e) // 2 for s, e in _runs(colhits) if 1 <= e - s <= 6]
    else:
        band = mask[top:bottom + 1, max(left - 7, 0):max(left, 1)]
        if band.size == 0:
            return []
        rowhits = band.sum(axis=1) >= 2
        positions = [(top + s + e) // 2 for s, e in _runs(rowhits) if 1 <= e - s <= 6]

    return _dedupe(positions, min_gap=3)


def _dedupe(xs: list[int], min_gap: int) -> list[int]:
    out: list[int] = []
    for x in sorted(xs):
        if not out or x - out[-1] >= min_gap:
            out.append(x)
    return out


def fit_from_limits(left_px: int, right_px: int, limits: tuple[float, float], scale: str = "linear") -> dict:
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
        a = (np.log10(hi) - np.log10(lo)) / (right_px - left_px)
        b = np.log10(lo) - a * left_px
        return {"ok": True, "scale": "log", "slope": float(a), "intercept": float(b),
                "rms_px": None, "tick_pairs": [], "outlier_px": [],
                "source": "axis_limits_frame_edges",
                "caveat": "frame edges assumed to equal the axis limits; no residual to verify this"}

    a = (hi - lo) / (right_px - left_px)
    b = lo - a * left_px
    return {"ok": True, "scale": "linear", "slope": float(a), "intercept": float(b),
            "rms_px": None, "tick_pairs": [], "outlier_px": [],
            "source": "axis_limits_frame_edges",
            "caveat": "frame edges assumed to equal the axis limits; no residual to verify this"}


def fit_axis(pixels: list[int], values: list[float], scale: str = "auto") -> dict:
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

    p = np.asarray(pixels, dtype=float)
    v = np.asarray(values, dtype=float)
    candidates = []
    if scale in ("linear", "auto"):
        candidates.append(("linear", v))
    if scale in ("log", "auto"):
        if np.all(v > 0):
            candidates.append(("log", np.log10(v)))
        elif scale == "log":
            return {"ok": False, "reason": "log axis needs strictly positive tick values"}

    best = None
    for kind, target in candidates:
        a, b = np.polyfit(p, target, 1)
        resid = target - (a * p + b)
        rms = float(np.sqrt(np.mean(resid ** 2)))
        # Residual in px-equivalent so linear and log are comparable.
        rms_px = rms / abs(a) if a != 0 else float("inf")
        if best is None or rms_px < best["_rms_px"]:
            best = {"scale": kind, "a": float(a), "b": float(b), "rms_px": rms_px,
                    "residual": resid.tolist()}

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
    outliers = [int(p[i]) for i in range(len(p)) if abs(best["residual"][i]) > k * max(best["rms_px"] * abs(best["a"]), 1e-9)]

    return {
        "ok": True,
        "scale": best["scale"],
        "slope": best["a"],
        "intercept": best["b"],
        "rms_px": round(best["rms_px"], 4),
        "tick_pairs": [{"px": int(a), "value": float(b)} for a, b in zip(pixels, values)],
        "outlier_px": outliers,
    }


def px_to_value(px: float | np.ndarray, fit: dict) -> float | np.ndarray:
    """Apply a fitted axis to pixel coordinate(s)."""
    raw = fit["slope"] * np.asarray(px, dtype=float) + fit["intercept"]
    return np.power(10.0, raw) if fit["scale"] == "log" else raw


def infer_scale_from_spacing(pixels: list[int]) -> str:
    """Guess axis scale from tick spacing alone.

    Decade ticks on a log axis are evenly spaced in pixels but unevenly spaced
    in value; a linear axis with uneven tick labels is rare. This is a weak
    prior the caller should override with the OCR'd label values when it has
    them.
    """
    if len(pixels) < 3:
        return "unknown"
    gaps = np.diff(sorted(pixels)).astype(float)
    cv = float(np.std(gaps) / np.mean(gaps)) if np.mean(gaps) else 0.0
    return "even-spacing"
