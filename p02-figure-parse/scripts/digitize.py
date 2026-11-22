"""Series extraction (digitisation) inside a calibrated plot frame.

Turns a raster panel into per-series (x, y) point lists in data units, plus a
per-point evidence record so a reviewer can re-read the same pixel.

Design notes that matter for correctness:
- Only saturated, non-grey pixels become a series colour, so black spines,
  tick labels, and grey gridlines never digitise as data.
- Points near the frame edge and inside legend boxes are excluded.
- Marker centroids are used when a series is markers-only; otherwise each
  column contributes one median-y sample, which handles thick and thin lines
  alike.
"""

from __future__ import annotations

import numpy as np
from scipy import ndimage

MIN_SATURATION = 45          # out of 255; below this a pixel is grey, i.e. not data ink
MIN_SERIES_PIXELS = 25
LEGEND_EDGE_EXCLUSION = 2    # px inward from the frame, keeps spine antialiasing out


def _to_hsv(rgb: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """HSV triple for an HxWx3 uint8/float array. H in degrees."""
    a = np.asarray(rgb, dtype=np.float64)
    if a.max() <= 1.0:
        a = a * 255.0
    r, g, b = a[..., 0], a[..., 1], a[..., 2]
    mx, mn = a.max(-1), a.min(-1)
    d = mx - mn
    h = np.zeros_like(mx)
    nz = d > 0
    idx = nz & (mx == r)
    h[idx] = ((g[idx] - b[idx]) / d[idx]) % 6
    idx = nz & (mx == g)
    h[idx] = ((b[idx] - r[idx]) / d[idx]) + 2
    idx = nz & (mx == b)
    h[idx] = ((r[idx] - g[idx]) / d[idx]) + 4
    h *= 60.0
    s = np.where(mx > 0, 255.0 * d / np.maximum(mx, 1e-9), 0.0)
    return h, s, mx


def find_series_colors(rgb: np.ndarray, frame: dict, max_series: int = 8) -> list[dict]:
    """Cluster the saturated colours inside the frame into candidate series.

    Colours are binned on a coarse hue grid; bins that survive a pixel-count
    floor become series. The returned `hue`/`sat` lets the caller name them in
    the order the legend lists them.
    """
    h, s, _ = _to_hsv(rgb)
    inner = np.zeros(s.shape, bool)
    inner[frame["top"] + LEGEND_EDGE_EXCLUSION:frame["bottom"] - LEGEND_EDGE_EXCLUSION,
          frame["left"] + LEGEND_EDGE_EXCLUSION:frame["right"] - LEGEND_EDGE_EXCLUSION] = True
    data = inner & (s >= MIN_SATURATION)

    if not data.any():
        return []

    hue_bins = np.floor(h / 15.0).astype(int) % 24
    out = []
    for b in range(24):
        sel = data & (hue_bins == b)
        n = int(sel.sum())
        if n < MIN_SERIES_PIXELS:
            continue
        out.append({
            "hue_bin": b,
            "pixels": n,
            "median_hue": float(np.median(h[sel])),
            "median_sat": float(np.median(s[sel])),
        })
    out.sort(key=lambda c: -c["pixels"])
    return out[:max_series]


def series_mask(rgb: np.ndarray, frame: dict, hue_bin: int) -> np.ndarray:
    """Boolean mask of the pixels belonging to one colour bin."""
    h, s, _ = _to_hsv(rgb)
    m = np.zeros(s.shape, bool)
    m[frame["top"] + LEGEND_EDGE_EXCLUSION:frame["bottom"] - LEGEND_EDGE_EXCLUSION,
      frame["left"] + LEGEND_EDGE_EXCLUSION:frame["right"] - LEGEND_EDGE_EXCLUSION] = True
    return m & (s >= MIN_SATURATION) & ((np.floor(h / 15.0).astype(int) % 24) == hue_bin)


def extract_points(mask: np.ndarray, frame: dict, n_markers: int = 0) -> list[dict]:
    """Sample one (x_px, y_px) per column, or marker centroids if asked.

    Returns pixel-space points; conversion to data units is the caller's job
    because it owns the calibration.
    """
    sub = mask[frame["top"]:frame["bottom"] + 1, frame["left"]:frame["right"] + 1]
    if not sub.any():
        return []

    if n_markers >= 3:
        labels, n = ndimage.label(sub)
        coms = ndimage.center_of_mass(sub, labels, range(1, n + 1))
        sizes = ndimage.sum(sub, labels, range(1, n + 1))
        med = float(np.median(sizes)) if n else 0.0
        pts = []
        for (cy, cx), sz in zip(coms, sizes):
            # Keep only blobs close to the median size: that rejects stray
            # antialiasing specks which would otherwise each read as a point.
            if 0.3 * med <= sz <= 2.5 * med:
                pts.append({"x_px": float(frame["left"] + cx), "y_px": float(frame["top"] + cy),
                            "weight_px": int(sz)})
        return sorted(pts, key=lambda d: d["x_px"])

    pts = []
    for x in range(sub.shape[1]):
        ys = np.flatnonzero(sub[:, x])
        if ys.size == 0:
            continue
        pts.append({"x_px": float(frame["left"] + x),
                    "y_px": float(frame["top"] + float(np.median(ys))),
                    "thickness_px": int(ys.size)})
    return pts


def thin_curve(points: list[dict], every: int = 1) -> list[dict]:
    """Subsample a dense per-column trace to a readable size, keeping x order."""
    if every <= 1:
        return points
    return points[::every]


def column_extents(mask: np.ndarray, frame: dict) -> list[dict]:
    """Vertical ink extent of each occupied column inside the frame.

    An error bar shows up as a column whose extent is several times the stroke
    width, isolated from its neighbours. A steep line also produces tall
    columns, but they come in long contiguous runs, so isolation is what
    separates the two.
    """
    sub = mask[frame["top"]:frame["bottom"] + 1, frame["left"]:frame["right"] + 1]
    out = []
    for x in range(sub.shape[1]):
        ys = np.flatnonzero(sub[:, x])
        if ys.size == 0:
            continue
        out.append({"x_px": frame["left"] + x,
                    "y_top_px": frame["top"] + int(ys.min()),
                    "y_bot_px": frame["top"] + int(ys.max()),
                    "extent_px": int(ys.size),
                    "y_mid_px": frame["top"] + float(np.median(ys))})
    return out


def find_error_bars(mask: np.ndarray, frame: dict, min_ratio: float = 3.0) -> list[dict]:
    """Columns that are tall, isolated vertical strokes: candidate error bars.

    Deliberately conservative. A wrong error bar is worse than a missing one,
    because it reads as a measured quantity. Callers should treat the result as
    a candidate set and say so.
    """
    cols = column_extents(mask, frame)
    if len(cols) < 8:
        return []
    med = float(np.median([c["extent_px"] for c in cols]))
    if med <= 0:
        return []

    xs = [c["x_px"] for c in cols]
    tall = [i for i, c in enumerate(cols) if c["extent_px"] > min_ratio * med]
    if len(tall) < 3:
        return []

    # Isolation: reject a column whose neighbours are also tall. A steep line
    # produces a contiguous run; a marker's error bar stands alone.
    gaps = np.diff(sorted(xs))
    typical_gap = float(np.median(gaps)) if gaps.size else 1.0
    tall_set = set(tall)
    isolated = [i for i in tall
                if (i - 1 not in tall_set or xs[i] - xs[i - 1] > 2 * typical_gap)
                and (i + 1 not in tall_set or xs[i + 1] - xs[i] > 2 * typical_gap)]
    if len(isolated) < 3:
        return []

    return [{
        "x_px": cols[i]["x_px"],
        "y_px": cols[i]["y_mid_px"],
        "half_length_px": (cols[i]["extent_px"] - med) / 2.0,
        "extent_px": cols[i]["extent_px"],
    } for i in isolated]


# ---------------------------------------------------------------------------
# Statistical charts: bars, and the marks that live above them
# ---------------------------------------------------------------------------

def detect_bars(mask: np.ndarray, frame: dict, min_bar_width: int = 6,
                min_height: int = 8, min_bars: int = 2, flat_tol: float = 2.0,
                base_tol_frac: float = 0.02) -> dict | None:
    """Solid flat-topped columns standing on a shared baseline: a bar chart.

    A bar is a filled rectangle: across its whole width the ink runs from a
    flat top down to the axis baseline. A stroked curve fails this twice over —
    its top moves column to column, and its bottom does not sit on a shared
    baseline. The detector refuses anything else, because a wrong bar reading
    is a fabricated value: the per-column median that digitises a curve would
    read a solid bar as a horizontal line through its middle.

    Adjacent bars that touch merge into one run and fail the flat-top test, so
    the panel falls back to the curve path and is reported as not-bar-like;
    that is honest. Known residual risk, stated in SKILL.md: a very thick
    *dashed* flat line can present short flat runs on a shared baseline.
    """
    sub = mask[frame["top"]:frame["bottom"] + 1, frame["left"]:frame["right"] + 1]
    if sub.size == 0 or not sub.any():
        return None
    occupied = sub.sum(axis=0) > 0

    runs = []
    x = 0
    while x < sub.shape[1]:
        if occupied[x]:
            x2 = x
            while x2 + 1 < sub.shape[1] and occupied[x2 + 1]:
                x2 += 1
            runs.append((x, x2))
            x = x2 + 1
        else:
            x += 1

    bars, baselines = [], []
    for a, b in runs:
        w = b - a + 1
        if w < min_bar_width:
            continue
        col = sub[:, a:b + 1]
        tops, bottoms = [], []
        for c in range(col.shape[1]):
            ys = np.flatnonzero(col[:, c])
            if ys.size == 0:
                continue
            tops.append(ys.min())
            bottoms.append(ys.max())
        if len(tops) < min_bar_width:
            continue
        top, bot = float(np.median(tops)), float(np.median(bottoms))
        height = bot - top
        if height < min_height:
            continue
        # Flat top: a bar's top row is level across its width. A curve rises or
        # falls; even a locally flat curve segment will not share a baseline
        # with a second segment, which is the second gate below.
        if max(abs(t - top) for t in tops) > flat_tol:
            continue
        bars.append({"x0_px": frame["left"] + a, "x1_px": frame["left"] + b,
                     "top_px": frame["top"] + top, "bottom_px": frame["top"] + bot,
                     "width_px": w, "height_px": round(height, 1)})
        baselines.append(bot)

    if len(bars) < min_bars:
        return None
    bl = float(np.median(baselines))
    tol = max(3.0, base_tol_frac * (frame["bottom"] - frame["top"]))
    if max(abs(r - bl) for r in baselines) > tol:
        return None
    bars.sort(key=lambda d: d["x0_px"])
    return {"baseline_px": frame["top"] + bl, "bars": bars}


def find_annotations_above(ink: np.ndarray, frame: dict, bars: list[dict],
                           max_span_frac: float = 0.35) -> dict:
    """Small ink marks sitting just above bar tops: significance markers, caps.

    Asterisks, daggers and error-bar caps are drawn in black over the bars, so
    they are invisible to the saturated-colour mask. This looks for connected
    ink components in the strip above each bar's top and classifies them by
    shape — a tall thin stroke reads as an error-bar candidate, a compact blob
    as a significance-marker candidate. Everything is a candidate: a bracket, a
    letter grade or stray antialiasing can land in the same strip, so the
    reviewer confirms against the figure.
    """
    top = frame["top"]
    strip_h = max(6, int(max_span_frac * (frame["bottom"] - frame["top"])))
    err_cands, marker_cands = [], []
    for b in bars:
        x0, x1 = int(b["x0_px"]), int(b["x1_px"])
        t = int(b["top_px"])
        y_lo = max(top, t - strip_h)
        if t - 2 <= y_lo:
            continue
        region = ink[y_lo:t - 2, x0:x1 + 1]
        if region.size == 0 or not region.any():
            continue
        labels, n = ndimage.label(region)
        if n < 1:
            continue
        for sl in ndimage.find_objects(labels):
            if sl is None:
                continue
            h = sl[0].stop - sl[0].start
            w = sl[1].stop - sl[1].start
            size = int((labels[sl] > 0).sum())
            cx = x0 + (sl[1].start + sl[1].stop) / 2.0
            cy = y_lo + (sl[0].start + sl[0].stop) / 2.0
            aspect = h / max(w, 1)
            # A capped error bar is a vertical stroke plus two horizontal caps:
            # caps widen it, so its aspect sits around 1-3, not above it. What
            # separates it from a significance glyph is height: a marker is
            # glyph-scale (a few px), an error bar spans tens of pixels.
            w_cap = max(10.0, 0.6 * (b["x1_px"] - b["x0_px"]))
            if h >= 9 and aspect >= 0.8 and w <= w_cap:
                err_cands.append({"x_px": round(cx, 1), "y_px": round(cy, 1),
                                  "height_px": h, "width_px": w, "pixels": size,
                                  "kind": "error_bar_candidate"})
            elif h <= 9 and w <= 40 and size <= 150:
                marker_cands.append({"x_px": round(cx, 1), "y_px": round(cy, 1),
                                     "height_px": h, "width_px": w, "pixels": size,
                                     "kind": "significance_marker_candidate"})
    return {"error_bar_candidates": err_cands, "marker_candidates": marker_cands}

