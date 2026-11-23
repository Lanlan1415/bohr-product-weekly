"""Drawing primitives for the figure bench — standard library only.

The bench draws analytic figures at exact pixel coordinates so readings can be
scored against known truth. Drawing used to import Pillow, which made the
bench itself — the very thing that proves the engine runs — crash on machines
without it. On top of `pngio.write_png_rgb` this adds the four primitives the
bench needs: thick lines, filled rectangles, filled ellipses, and one glyph
(the significance asterisk) from a 5x7 bitmap.
"""

from __future__ import annotations

import pngio

ASTERISK = [
    "..X..",
    "..X..",
    "X.X.X",
    ".XXX.",
    "X.X.X",
    "..X..",
    "..X..",
]


class Canvas:
    """An RGB canvas with the primitives the bench fixtures need."""

    def __init__(self, w: int, h: int, bg=(255, 255, 255)) -> None:
        self.w, self.h = w, h
        self.px = [[bg for _ in range(w)] for _ in range(h)]

    def line(self, *args, color=(0, 0, 0), fill=None, width: int = 1) -> None:
        """A thick line segment.

        Accepts both `line(x0, y0, x1, y1, ...)` and the Pillow-style
        `line([(x0, y0), (x1, y1)], fill=...)` so bench fixtures read the same
        as they did against PIL.
        """
        if fill is not None:
            color = fill
        if len(args) == 1 and isinstance(args[0], (list, tuple)) and len(args[0]) == 2:
            (x0, y0), (x1, y1) = args[0]
        elif len(args) == 2 and isinstance(args[0], (list, tuple)):
            (x0, y0), (x1, y1) = args
        elif len(args) == 4:
            x0, y0, x1, y1 = args
        else:
            raise TypeError("line() expects two points or four coordinates")
        x0, y0, x1, y1 = round(x0), round(y0), round(x1), round(y1)
        dx, dy = abs(x1 - x0), abs(y1 - y0)
        sx = 1 if x0 <= x1 else -1
        sy = 1 if y0 <= y1 else -1
        err = dx - dy
        cx, cy = x0, y0
        half = width // 2
        while True:
            for oy in range(-half, half + (1 if width % 2 == 0 else 0)):
                for ox in range(-half, half + (1 if width % 2 == 0 else 0)):
                    xx, yy = cx + ox, cy + oy
                    if 0 <= xx < self.w and 0 <= yy < self.h:
                        self.px[yy][xx] = color
            if cx == x1 and cy == y1:
                break
            e2 = 2 * err
            if e2 > -dy:
                err -= dy
                cx += sx
            if e2 < dx:
                err += dx
                cy += sy

    def rect_fill(self, x0, y0, x1, y1, color) -> None:
        for y in range(max(0, round(y0)), min(self.h - 1, round(y1)) + 1):
            for x in range(max(0, round(x0)), min(self.w - 1, round(x1)) + 1):
                self.px[y][x] = color

    def ellipse_fill(self, x0, y0, x1, y1, color) -> None:
        """Filled ellipse inside the inclusive box (Pillow-style bounds)."""
        cx = (x0 + x1) / 2.0
        cy = (y0 + y1) / 2.0
        rx = max((x1 - x0) / 2.0, 0.5)
        ry = max((y1 - y0) / 2.0, 0.5)
        for y in range(max(0, round(y0)), min(self.h - 1, round(y1)) + 1):
            for x in range(max(0, round(x0)), min(self.w - 1, round(x1)) + 1):
                if ((x - cx) / rx) ** 2 + ((y - cy) / ry) ** 2 <= 1.06:
                    self.px[y][x] = color

    def glyph(self, x: int, y: int, color=(0, 0, 0)) -> None:
        """Draw the significance asterisk with its top-left at (x, y)."""
        for gy, row in enumerate(ASTERISK):
            for gx, c in enumerate(row):
                if c == "X" and 0 <= y + gy < self.h and 0 <= x + gx < self.w:
                    self.px[y + gy][x + gx] = color

    def save(self, path) -> None:
        pngio.write_png_rgb(path, self.px, self.w, self.h)
