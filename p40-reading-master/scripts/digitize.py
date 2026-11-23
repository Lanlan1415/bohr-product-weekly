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

Dependencies: none beyond the standard library (`rasterkit.py` provides the
morphology, labelling and statistics that scipy.ndimage used to).
"""

from __future__ import annotations

import rasterkit as R

MIN_SATURATION = 45          # out of 255; below this a pixel is grey, i.e. not data ink
MIN_SERIES_PIXELS = 25
LEGEND_EDGE_EXCLUSION = 2    # px inward from the frame, keeps spine antialiasing out


def to_hsv(rgb: list) -> R.HSV:
    """HSV triple for rows of (r, g, b). H in degrees; computed once per panel."""
    return R.HSV(rgb)


def find_series_colors(rgb: list, frame: dict, max_series: int = 8,
                       hsv: "R.HSV | None" = None) -> list[dict]:
    """Cluster the saturated colours inside the frame into candidate series.

    Colours are binned on a coarse hue grid; bins that survive a pixel-count
    floor become series. The returned `hue`/`sat` lets the caller name them in
    the order the legend lists them.
    """
    hsv = hsv or to_hsv(rgb)
    x0 = frame["left"] + LEGEND_EDGE_EXCLUSION
    x1 = frame["right"] - LEGEND_EDGE_EXCLUSION
    y0 = frame["top"] + LEGEND_EDGE_EXCLUSION
    y1 = frame["bottom"] - LEGEND_EDGE_EXCLUSION
    bins: dict[int, list[tuple[float, float]]] = {}
    for y in range(max(0, y0), min(hsv.h_h - 1, y1) + 1):
        hrow, srow = hsv.h[y], hsv.s[y]
        for x in range(max(0, x0), min(hsv.h_w - 1, x1) + 1):
            s = srow[x]
            if s >= MIN_SATURATION:
                b = int(hrow[x] // 15.0) % 24
                bins.setdefault(b, []).append((hrow[x], s))
    out = []
    for b, pairs in bins.items():
        if len(pairs) < MIN_SERIES_PIXELS:
            continue
        out.append({
            "hue_bin": b,
            "pixels": len(pairs),
            "median_hue": R.median([p[0] for p in pairs]),
            "median_sat": R.median([p[1] for p in pairs]),
        })
    out.sort(key=lambda c: -c["pixels"])
    return out[:max_series]


def series_mask(rgb: list, frame: dict, hue_bin: int,
                hsv: "R.HSV | None" = None) -> R.Bits:
    """Boolean mask of the pixels belonging to one colour bin."""
    hsv = hsv or to_hsv(rgb)
    x0 = frame["left"] + LEGEND_EDGE_EXCLUSION
    x1 = frame["right"] - LEGEND_EDGE_EXCLUSION
    y0 = frame["top"] + LEGEND_EDGE_EXCLUSION
    y1 = frame["bottom"] - LEGEND_EDGE_EXCLUSION
    rows: list[list[tuple[int, int]]] = []
    ylo = max(0, y0)
    yhi = min(hsv.h_h - 1, y1)
    xlo = max(0, x0)
    xhi = min(hsv.h_w - 1, x1)
    for y in range(hsv.h_h):
        if y < ylo or y > yhi:
            rows.append([])
            continue
        hr, sr = hsv.h[y], hsv.s[y]
        runs: list[tuple[int, int]] = []
        start = None
        for x in range(xlo, xhi + 1):
            ok = sr[x] >= MIN_SATURATION and int(hr[x] // 15.0) % 24 == hue_bin
            if ok and start is None:
                start = x
            elif not ok and start is not None:
                runs.append((start, x - 1))
                start = None
        if start is not None:
            runs.append((start, xhi))
        rows.append(runs)
    return R.Bits.from_runs(hsv.h_h, hsv.h_w, rows)


def extract_points(mask: R.Bits, frame: dict, n_markers: int = 0) -> list[dict]:
    """Sample one (x_px, y_px) per column, or marker centroids if asked.

    Returns pixel-space points; conversion to data units is the caller's job
    because it owns the calibration.
    """
    sub = mask.crop(frame["top"], frame["bottom"], frame["left"], frame["right"])
    if not sub.any():
        return []

    if n_markers >= 3:
        comps = sub.label4()
        sizes = [c["size"] for c in comps]
        med = R.median(sizes) if comps else 0.0
        pts = []
        for c in comps:
            # Keep only blobs close to the median size: that rejects stray
            # antialiasing specks which would otherwise each read as a point.
            if med and 0.3 * med <= c["size"] <= 2.5 * med:
                pts.append({"x_px": float(frame["left"] + c["cx"]),
                            "y_px": float(frame["top"] + c["cy"]),
                            "weight_px": int(c["size"])})
        return sorted(pts, key=lambda d: d["x_px"])

    pts = []
    cols = sub.col_runs()
    for x in range(sub.w):
        ys = _ys_from_runs(cols[x])
        if not ys:
            continue
        pts.append({"x_px": float(frame["left"] + x),
                    "y_px": float(frame["top"] + R.median(ys)),
                    "thickness_px": len(ys)})
    # A hard pixel staircase makes a steep line's column median jump by several
    # pixels even when the underlying curve is smooth. A [1,2,1]/4 binomial tap
    # estimates the sub-pixel centre without shifting x or flattening markers
    # (the marker branch returned above). Endpoints keep their measured values.
    if len(pts) >= 3:
        raw_y = [p["y_px"] for p in pts]
        for i in range(1, len(pts) - 1):
            pts[i]["y_px_raw"] = raw_y[i]
            pts[i]["y_px"] = (raw_y[i - 1] + 2.0 * raw_y[i] + raw_y[i + 1]) / 4.0
    return pts


def thin_curve(points: list[dict], every: int = 1) -> list[dict]:
    """Subsample a dense per-column trace to a readable size, keeping x order."""
    if every <= 1:
        return points
    return points[::every]


def column_extents(mask: R.Bits, frame: dict) -> list[dict]:
    """Vertical ink extent of each occupied column inside the frame.

    An error bar shows up as a column whose extent is several times the stroke
    width, isolated from its neighbours. A steep line also produces tall
    columns, but they come in long contiguous runs, so isolation is what
    separates the two.
    """
    sub = mask.crop(frame["top"], frame["bottom"], frame["left"], frame["right"])
    out = []
    cols = sub.col_runs()
    for x in range(sub.w):
        ys = _ys_from_runs(cols[x])
        if not ys:
            continue
        out.append({"x_px": frame["left"] + x,
                    "y_top_px": frame["top"] + min(ys),
                    "y_bot_px": frame["top"] + max(ys),
                    "extent_px": len(ys),
                    "y_mid_px": frame["top"] + R.median(ys)})
    return out


def find_error_bars(mask: R.Bits, frame: dict, min_ratio: float = 3.0) -> list[dict]:
    """Columns that are tall, isolated vertical strokes: candidate error bars.

    Deliberately conservative. A wrong error bar is worse than a missing one,
    because it reads as a measured quantity. Callers should treat the result as
    a candidate set and say so.
    """
    cols = column_extents(mask, frame)
    if len(cols) < 8:
        return []
    med = R.median([c["extent_px"] for c in cols])
    if med <= 0:
        return []

    xs = [c["x_px"] for c in cols]
    tall = [i for i, c in enumerate(cols) if c["extent_px"] > min_ratio * med]
    if len(tall) < 3:
        return []

    # Isolation: reject a column whose neighbours are also tall. A steep line
    # produces a contiguous run; a marker's error bar stands alone.
    sp = sorted(xs)
    gaps = [sp[i + 1] - sp[i] for i in range(len(sp) - 1)]
    typical_gap = R.median(gaps) if gaps else 1.0
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

def detect_bars(mask: R.Bits, frame: dict, min_bar_width: int = 6,
                min_height: int = 8, min_bars: int = 2, flat_tol: float = 2.0,
                base_tol_frac: float = 0.02) -> "dict | None":
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
    sub = mask.crop(frame["top"], frame["bottom"], frame["left"], frame["right"])
    if not sub.any():
        return None
    cols = sub.col_runs()
    occupied = [bool(runs) for runs in cols]

    runs = []
    x = 0
    while x < sub.w:
        if occupied[x]:
            x2 = x
            while x2 + 1 < sub.w and occupied[x2 + 1]:
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
        tops, bottoms = [], []
        for c in range(a, b + 1):
            ys = _ys_from_runs(cols[c])
            if not ys:
                continue
            tops.append(min(ys))
            bottoms.append(max(ys))
        if len(tops) < min_bar_width:
            continue
        top, bot = R.median(tops), R.median(bottoms)
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
    bl = R.median(baselines)
    tol = max(3.0, base_tol_frac * (frame["bottom"] - frame["top"]))
    if max(abs(r - bl) for r in baselines) > tol:
        return None
    bars.sort(key=lambda d: d["x0_px"])
    return {"baseline_px": frame["top"] + bl, "bars": bars}


def find_annotations_above(ink: R.Bits, frame: dict, bars: list[dict],
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
        region = ink.crop(y_lo, t - 3, x0, x1)
        if not region.any():
            continue
        for c in region.label4():
            hh = c["y1"] - c["y0"] + 1
            w = c["x1"] - c["x0"] + 1
            size = c["size"]
            cx = x0 + c["cx"]
            cy = y_lo + c["cy"]
            aspect = hh / max(w, 1)
            # A capped error bar is a vertical stroke plus two horizontal caps:
            # caps widen it, so its aspect sits around 1-3, not above it. What
            # separates it from a significance glyph is height: a marker is
            # glyph-scale (a few px), an error bar spans tens of pixels.
            w_cap = max(10.0, 0.6 * (b["x1_px"] - b["x0_px"]))
            if hh >= 9 and aspect >= 0.8 and w <= w_cap:
                err_cands.append({"x_px": round(cx, 1), "y_px": round(cy, 1),
                                  "height_px": hh, "width_px": w, "pixels": size,
                                  "kind": "error_bar_candidate"})
            elif hh <= 9 and w <= 40 and size <= 150:
                marker_cands.append({"x_px": round(cx, 1), "y_px": round(cy, 1),
                                     "height_px": hh, "width_px": w, "pixels": size,
                                     "kind": "significance_marker_candidate"})
    return {"error_bar_candidates": err_cands, "marker_candidates": marker_cands}


def _ys_from_runs(runs: list[tuple[int, int]]) -> list[int]:
    ys: list[int] = []
    for (s, e) in runs:
        ys.extend(range(s, e + 1))
    return ys
