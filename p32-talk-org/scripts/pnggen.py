"""Write a real PNG with nothing but the standard library.

The bench fixtures draw small figures (a framed rectangle, a synthetic plot).
They used to import Pillow for that, which made the bench itself crash on a
machine without Pillow — the same missing-dependency failure the audit had
already been hardened against, one layer down. A fixture needs four drawing
primitives and a PNG encoder; both fit in this file: `zlib` compresses the
scanlines and `struct` writes the chunks, so generating test images needs no
imaging library at all.
"""

from __future__ import annotations

import struct
import zlib


class Canvas:
    """A tiny RGB canvas with the primitives the fixtures need."""

    def __init__(self, w: int, h: int, bg=(255, 255, 255)) -> None:
        self.w, self.h = w, h
        self.px = [[tuple(bg) for _ in range(w)] for _ in range(h)]

    def rect_outline(self, x0: int, y0: int, x1: int, y1: int,
                     color=(0, 0, 0), width: int = 2) -> None:
        for t in range(width):
            for x in range(x0 + t, x1 - t + 1):
                self.px[y0 + t][x] = color
                self.px[y1 - t][x] = color
            for y in range(y0 + t, y1 - t + 1):
                self.px[y][x0 + t] = color
                self.px[y][x1 - t] = color

    def rect_fill(self, x0: int, y0: int, x1: int, y1: int, color) -> None:
        for y in range(max(0, y0), min(self.h - 1, y1) + 1):
            for x in range(max(0, x0), min(self.w - 1, x1) + 1):
                self.px[y][x] = color

    def line(self, x0, y0, x1, y1, color=(0, 0, 0), width: int = 1) -> None:
        """Bresenham with a square brush; coordinates may be fractional."""
        dx, dy = abs(x1 - x0), abs(y1 - y0)
        sx = 1 if x0 <= x1 else -1
        sy = 1 if y0 <= y1 else -1
        err = dx - dy
        x, y = float(x0), float(y0)
        cx, cy = int(round(x)), int(round(y))
        ex, ey = int(round(x1)), int(round(y1))
        for _ in range(abs(ex - cx) + abs(ey - cy) + 1):
            half = width // 2
            for oy in range(-half, half + 1):
                for ox in range(-half, half + 1):
                    xx, yy = cx + ox, cy + oy
                    if 0 <= xx < self.w and 0 <= yy < self.h:
                        self.px[yy][xx] = color
            e2 = 2 * err
            if e2 > -dy:
                err -= dy
                cx += sx
            if e2 < dx:
                err += dx
                cy += sy
            if (cx, cy) == (ex, ey):
                break

    def save(self, path) -> None:
        write_png(path, self.px, self.w, self.h)


def _chunk(tag: bytes, data: bytes) -> bytes:
    return (struct.pack(">I", len(data)) + tag + data
            + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF))


def write_png(path, px: list, w: int, h: int) -> None:
    """8-bit RGB PNG, filter type 0 on every scanline."""
    raw = bytearray()
    for row in px:
        raw.append(0)
        for (r, g, b) in row:
            raw += bytes((int(r) & 0xFF, int(g) & 0xFF, int(b) & 0xFF))
    ihdr = struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0)
    png = (b"\x89PNG\r\n\x1a\n"
           + _chunk(b"IHDR", ihdr)
           + _chunk(b"IDAT", zlib.compress(bytes(raw), 6))
           + _chunk(b"IEND", b""))
    with open(path, "wb") as fh:
        fh.write(png)
