"""Raster primitives for figure digitisation — nothing but the standard library.

The figure route used to hard-import numpy, scipy and Pillow. On a machine
without them every chart-reading case died with a traceback before any result
was written — the failure class that sank this package's first submission.
This module replaces exactly the operations those libraries were used for:

  luma, HSV, thresholds                     per-pixel loops over rows
  binary dilation / erosion / closing       run-length based (box structures,
                                            scipy's border_value=0 semantics)
  connected components (4-connectivity)     union-find over runs, with bounding
                                            boxes, sizes and centroids
  per-column / per-row statistics           column runs walked once
  median, least-squares line, moving mean   statistics + the closed form

The run-based representation keeps the hot paths proportional to the *ink*,
not to the image, so a 640x480 figure processes in about a second.
"""

from __future__ import annotations

import statistics


# ---------------------------------------------------------------------------
# Planes
# ---------------------------------------------------------------------------

class Gray:
    """An HxW luma plane: rows of floats in 0..255."""

    __slots__ = ("rows", "h", "w")

    def __init__(self, rows: list[list[float]]) -> None:
        self.rows = rows
        self.h = len(rows)
        self.w = len(rows[0]) if rows else 0

    def median(self) -> float:
        flat = [v for row in self.rows for v in row]
        return statistics.median(flat) if flat else 0.0


class HSV:
    """H in degrees 0..360, S and V in 0..255, for an RGB plane."""

    __slots__ = ("h", "s", "v", "h_h", "h_w")

    def __init__(self, rgb_rows: list) -> None:
        hrows: list[list[float]] = []
        srows: list[list[float]] = []
        vrows: list[list[float]] = []
        for row in rgb_rows:
            hr: list[float] = []
            sr: list[float] = []
            vr: list[float] = []
            for (r, g, b) in row:
                mx = r if r >= g and r >= b else (g if g >= b else b)
                mn = r if r <= g and r <= b else (g if g <= b else b)
                d = mx - mn
                if d <= 0:
                    hr.append(0.0)
                elif mx == r:
                    hr.append((((g - b) / d) % 6.0) * 60.0)
                elif mx == g:
                    hr.append((((b - r) / d) + 2.0) * 60.0)
                else:
                    hr.append((((r - g) / d) + 4.0) * 60.0)
                sr.append(255.0 * d / mx if mx > 0 else 0.0)
                vr.append(mx)
            hrows.append(hr)
            srows.append(sr)
            vrows.append(vr)
        self.h, self.s, self.v = hrows, srows, vrows
        self.h_h = len(hrows)
        self.h_w = len(hrows[0]) if hrows else 0

    def hue_bins(self) -> list[list[int]]:
        return [[int(x // 15.0) % 24 for x in row] for row in self.h]


class Bits:
    """An HxW boolean mask."""

    __slots__ = ("rows", "h", "w", "_row_runs")

    def __init__(self, rows: list[list[bool]]) -> None:
        self.rows = rows
        self.h = len(rows)
        self.w = len(rows[0]) if rows else 0
        self._row_runs: list | None = None

    # -- constructors -------------------------------------------------------

    @classmethod
    def from_runs(cls, h: int, w: int, runs_per_row: list[list[tuple[int, int]]]) -> "Bits":
        rows = [[False] * w for _ in range(h)]
        for y, runs in enumerate(runs_per_row):
            row = rows[y]
            for s, e in runs:
                for x in range(s, e + 1):
                    row[x] = True
        return cls(rows)

    @classmethod
    def empty(cls, h: int, w: int) -> "Bits":
        return cls([[False] * w for _ in range(h)])

    @classmethod
    def from_gray(cls, gray: Gray, threshold: float) -> "Bits":
        return cls([[v < threshold for v in row] for row in gray.rows])

    # -- basic queries ------------------------------------------------------

    def any(self) -> bool:
        for row in self.rows:
            for v in row:
                if v:
                    return True
        return False

    def count(self) -> int:
        return sum(1 for row in self.rows for v in row if v)

    def runs_row(self, y: int) -> list[tuple[int, int]]:
        """Maximal True runs of one row, inclusive."""
        out: list[tuple[int, int]] = []
        row = self.rows[y]
        x = 0
        w = self.w
        while x < w:
            if row[x]:
                s = x
                while x + 1 < w and row[x + 1]:
                    x += 1
                out.append((s, x))
            x += 1
        return out

    def col_ys(self, x: int) -> list[int]:
        """All set rows in one column, ascending."""
        return [y for y, row in enumerate(self.rows) if row[x]]

    def col_runs(self) -> list[list[tuple[int, int]]]:
        """Runs per column, computed in one pass over the row runs."""
        cols: list[list[int]] = [[] for _ in range(self.w)]
        for y, runs in enumerate(self.runs_all_rows()):
            for (s, e) in runs:
                for x in range(s, e + 1):
                    cols[x].append(y)
        return [_runs_from_points(ys) for ys in cols]

    def runs_all_rows(self) -> list[list[tuple[int, int]]]:
        if self._row_runs is None:
            self._row_runs = [self.runs_row(y) for y in range(self.h)]
        return self._row_runs

    def crop(self, y0: int, y1: int, x0: int, x1: int) -> "Bits":
        """Inclusive crop [y0..y1] x [x0..x1]."""
        return Bits([row[x0:x1 + 1] for row in self.rows[y0:y1 + 1]])

    # -- morphology ---------------------------------------------------------

    def dilate_box(self, ry: int, rx: int) -> "Bits":
        """Box dilation, separable, on runs."""
        # Horizontal pass.
        hr: list[list[tuple[int, int]]] = []
        for y in range(self.h):
            runs = [(max(0, s - rx), min(self.w - 1, e + rx))
                    for (s, e) in self.runs_row(y)]
            hr.append(_merge_runs(runs))
        # Vertical pass.
        per_row: list[list[tuple[int, int]]] = [[] for _ in range(self.h)]
        for y, runs in enumerate(hr):
            lo, hi = max(0, y - ry), min(self.h - 1, y + ry)
            for (s, e) in runs:
                for yy in range(lo, hi + 1):
                    per_row[yy].append((s, e))
        return Bits.from_runs(self.h, self.w, [_merge_runs(r) for r in per_row])

    def erode_box(self, ry: int, rx: int) -> "Bits":
        """Box erosion; outside the array counts as unset (border_value=0).

        1D-erode each row by rx, then a pixel at row y survives only when every
        row y-ry..y+ry is inside the array and erode-supported at that column.
        """
        er: list[list[tuple[int, int]]] = []
        for y in range(self.h):
            runs = []
            for (s, e) in self.runs_row(y):
                s2, e2 = s + rx, e - rx
                if s2 <= e2:
                    runs.append((s2, e2))
            er.append(runs)
        out: list[list[tuple[int, int]]] = []
        for y in range(self.h):
            if y - ry < 0 or y + ry > self.h - 1:
                out.append([])
                continue
            spans = er[y - ry]
            for dy in range(-ry + 1, ry + 1):
                spans = _intersect_runs(spans, er[y + dy])
                if not spans:
                    break
            out.append(spans)
        return Bits.from_runs(self.h, self.w, out)

    def close_box(self, ry: int, rx: int) -> "Bits":
        """Binary closing with a box structure (dilate, then erode)."""
        return self.dilate_box(ry, rx).erode_box(ry, rx)

    # -- components ---------------------------------------------------------

    def label4(self) -> list[dict]:
        """4-connected components: boxes, sizes, centroids (y, x).

        Runs on consecutive rows whose x-spans share a column are the same
        component — the run-graph union-find, which is what
        scipy.ndimage.label + find_objects + center_of_mass produced here.
        """
        parent: list[int] = []

        def find(i: int) -> int:
            while parent[i] != i:
                parent[i] = parent[parent[i]]
                i = parent[i]
            return i

        def union(i: int, j: int) -> None:
            ri, rj = find(i), find(j)
            if ri != rj:
                parent[max(ri, rj)] = min(ri, rj)

        prev: list[tuple[int, int, int]] = []
        run_index: list[list[tuple[int, int, int]]] = []
        for y in range(self.h):
            cur: list[tuple[int, int, int]] = []
            for (s, e) in self.runs_row(y):
                idx = len(parent)
                parent.append(idx)
                cur.append((s, e, idx))
            for (s, e, idx) in cur:
                for (ps, pe, pidx) in prev:
                    if ps <= e and s <= pe:
                        union(idx, pidx)
            run_index.append(cur)
            prev = cur

        boxes: dict[int, list[int]] = {}
        counts: dict[int, int] = {}
        sx: dict[int, float] = {}
        sy: dict[int, float] = {}
        for y in range(self.h):
            for (s, e, idx) in run_index[y]:
                root = find(idx)
                n = e - s + 1
                b = boxes.get(root)
                if b is None:
                    boxes[root] = [y, y, s, e]
                    counts[root] = 0
                    sx[root] = 0.0
                    sy[root] = 0.0
                else:
                    if y > b[1]:
                        b[1] = y
                    if s < b[2]:
                        b[2] = s
                    if e > b[3]:
                        b[3] = e
                counts[root] += n
                sy[root] += y * n
                sx[root] += (s + e) * n / 2.0
        comps = []
        for root, b in boxes.items():
            n = counts[root]
            comps.append({
                "y0": b[0], "y1": b[1], "x0": b[2], "x1": b[3],
                "size": n,
                "cy": sy[root] / n,
                "cx": sx[root] / n,
            })
        comps.sort(key=lambda c: (c["y0"], c["x0"]))
        return comps


# ---------------------------------------------------------------------------
# Run algebra
# ---------------------------------------------------------------------------

def _merge_runs(runs: list[tuple[int, int]]) -> list[tuple[int, int]]:
    """Merge overlapping/touching runs; sorted, inclusive."""
    if not runs:
        return []
    runs = sorted(runs)
    out = [[runs[0][0], runs[0][1]]]
    for s, e in runs[1:]:
        if s <= out[-1][1] + 1:
            if e > out[-1][1]:
                out[-1][1] = e
        else:
            out.append([s, e])
    return [(s, e) for s, e in out]


def _intersect_runs(a: list[tuple[int, int]], b: list[tuple[int, int]]) -> list[tuple[int, int]]:
    out: list[tuple[int, int]] = []
    i = j = 0
    while i < len(a) and j < len(b):
        s = max(a[i][0], b[j][0])
        e = min(a[i][1], b[j][1])
        if s <= e:
            out.append((s, e))
        if a[i][1] <= b[j][1]:
            i += 1
        else:
            j += 1
    return out


def _runs_from_points(ys: list[int]) -> list[tuple[int, int]]:
    """Runs from an ascending list of coordinates."""
    if not ys:
        return []
    out = [[ys[0], ys[0]]]
    for y in ys[1:]:
        if y == out[-1][1] + 1:
            out[-1][1] = y
        else:
            out.append([y, y])
    return [(s, e) for s, e in out]


# ---------------------------------------------------------------------------
# Statistics helpers
# ---------------------------------------------------------------------------

def median(values) -> float:
    return statistics.median(values) if values else 0.0


def linfit(pixels, values) -> tuple[float, float]:
    """Least-squares y = a*x + b, the exact polyfit(deg=1) closed form."""
    n = len(pixels)
    if n == 0:
        return 0.0, 0.0
    mp = sum(pixels) / n
    mv = sum(values) / n
    sxx = sum((p - mp) ** 2 for p in pixels)
    sxy = sum((p - mp) * (v - mv) for p, v in zip(pixels, values))
    a = sxy / sxx if sxx else 0.0
    return a, mv - a * mp


def moving_mean(values: list[float], w: int) -> list[float]:
    """Centred moving average, the pure-Python np.convolve(ones/w)."""
    n = len(values)
    if w <= 1 or n < w:
        return list(values)
    half = w // 2
    out = []
    running = sum(values[:w])
    for i in range(n):
        if w <= n:
            lo = i - half
            hi = lo + w
            if lo < 0 or hi > n:
                # 'valid'-style edges: np.convolve(valid) yields n-w+1 values;
                # figparse centres it, so mirror the shrink at the edges.
                out.append(sum(values[max(0, lo):min(n, hi)]) / max(1, min(n, hi) - max(0, lo)))
            else:
                if i == half:
                    running = sum(values[0:w])
                elif i > half:
                    running += values[hi - 1] - values[lo - 1]
                out.append(running / w)
        else:
            out.append(values[i])
    return out
