"""PNG read/write with nothing but zlib and struct.

The figure route reads raster images and the bench draws them. Pillow used to
be a hard import for both, so a Pillow-less machine could neither read a
figure nor run the bench — one more way for a case to die without writing a
result. This module does both: decode the PNG subset that scientific figures
use (8- and 16-bit, greyscale / RGB / palette / alpha), and encode RGB scanlines.
Formats outside the subset raise a `PngError` naming the limitation, so the
caller reports an honest limit instead of a traceback.
"""

from __future__ import annotations

import struct
import zlib


class PngError(ValueError):
    """The file is a PNG this reader does not support, or is not a PNG at all."""


_MAGIC = b"\x89PNG\r\n\x1a\n"


def _paeth(a: int, b: int, c: int) -> int:
    p = a + b - c
    pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
    if pa <= pb and pa <= pc:
        return a
    if pb <= pc:
        return b
    return c


def read_png_rgb(path) -> list[list[tuple[int, int, int]]]:
    """Decode a PNG file into rows of (r, g, b).

    Supports bit depths 8 and 16, colour types 0 (grey), 2 (RGB), 3 (palette),
    4 (grey+alpha), 6 (RGBA); 16-bit is reduced to the high byte. Interlaced
    (Adam7) files raise PngError.
    """
    data = open(path, "rb").read()
    if data[:8] != _MAGIC:
        raise PngError("not a PNG file (magic mismatch)")
    pos = 8
    ihdr = None
    plte = None
    idat = bytearray()
    while pos + 8 <= len(data):
        length = struct.unpack_from(">I", data, pos)[0]
        tag = data[pos + 4:pos + 8]
        chunk = data[pos + 8:pos + 8 + length]
        if tag == b"IHDR":
            ihdr = struct.unpack(">IIBBBBB", chunk[:13])
        elif tag == b"PLTE":
            plte = chunk
        elif tag == b"IDAT":
            idat += chunk
        elif tag == b"IEND":
            break
        pos += 12 + length
    if ihdr is None:
        raise PngError("PNG has no IHDR")
    w, h, depth, ctype, compression, filter_, interlace = ihdr
    if interlace != 0:
        raise PngError("interlaced PNG (Adam7) is not supported; re-export progressive")
    if compression != 0 or filter_ != 0:
        raise PngError("unsupported PNG compression/filter method")
    if depth not in (1, 2, 4, 8, 16):
        raise PngError(f"bit depth {depth} is not supported")
    if depth in (1, 2, 4) and ctype not in (0, 3):
        raise PngError(f"bit depth {depth} is only supported for grey and palette PNGs")
    channels = {0: 1, 2: 3, 3: 1, 4: 2, 6: 4}.get(ctype)
    if channels is None:
        raise PngError(f"colour type {ctype} is not supported")
    raw = zlib.decompress(bytes(idat))
    bpp = channels * (2 if depth == 16 else 1)
    stride = (w * channels * depth + 7) // 8
    if len(raw) < (stride + 1) * h:
        raise PngError("PNG pixel data is truncated")

    out: list[bytearray] = []
    prev = bytearray(stride)
    idx = 0
    for _y in range(h):
        ftype = raw[idx]
        idx += 1
        line = bytearray(raw[idx:idx + stride])
        idx += stride
        if ftype == 1:            # Sub
            for i in range(bpp, stride):
                line[i] = (line[i] + line[i - bpp]) & 0xFF
        elif ftype == 2:          # Up
            for i in range(stride):
                line[i] = (line[i] + prev[i]) & 0xFF
        elif ftype == 3:          # Average
            for i in range(stride):
                left = line[i - bpp] if i >= bpp else 0
                line[i] = (line[i] + ((left + prev[i]) >> 1)) & 0xFF
        elif ftype == 4:          # Paeth
            for i in range(stride):
                left = line[i - bpp] if i >= bpp else 0
                up = prev[i]
                ul = prev[i - bpp] if i >= bpp else 0
                line[i] = (line[i] + _paeth(left, up, ul)) & 0xFF
        elif ftype != 0:
            raise PngError(f"unknown PNG filter type {ftype}")
        prev = line
        out.append(line)

    # Expand to RGB rows.
    rows: list[list[tuple[int, int, int]]] = []
    for line in out:
        row: list[tuple[int, int, int]] = []
        if ctype == 0 and depth in (1, 2, 4):
            # Low-bit-depth greyscale: scale the value across 0..255.
            levels = (1 << depth) - 1
            per_byte = 8 // depth
            for x in range(w):
                byte = line[x // per_byte]
                shift = 8 - depth * (x % per_byte + 1)
                g = (byte >> shift) & levels
                g = int(g * 255 / levels)
                row.append((g, g, g))
        elif ctype == 2:
            if depth == 8:
                for x in range(w):
                    row.append((line[3 * x], line[3 * x + 1], line[3 * x + 2]))
            else:
                for x in range(w):
                    row.append((line[6 * x], line[6 * x + 2], line[6 * x + 4]))
        elif ctype == 6:
            if depth == 8:
                for x in range(w):
                    row.append((line[4 * x], line[4 * x + 1], line[4 * x + 2]))
            else:
                for x in range(w):
                    row.append((line[8 * x], line[8 * x + 2], line[8 * x + 4]))
        elif ctype == 0:
            if depth == 8:
                for x in range(w):
                    g = line[x]
                    row.append((g, g, g))
            else:
                for x in range(w):
                    g = line[2 * x]
                    row.append((g, g, g))
        elif ctype == 4:
            if depth == 8:
                for x in range(w):
                    g = line[2 * x]
                    row.append((g, g, g))
            else:
                for x in range(w):
                    g = line[4 * x]
                    row.append((g, g, g))
        elif ctype == 3:
            if plte is None:
                raise PngError("palette PNG has no PLTE chunk")
            if depth == 8:
                for x in range(w):
                    i3 = 3 * line[x]
                    row.append((plte[i3], plte[i3 + 1], plte[i3 + 2]))
            else:
                per_byte = 8 // depth
                mask = (1 << depth) - 1
                max_idx = (len(plte) // 3) - 1
                for x in range(w):
                    byte = line[x // per_byte]
                    shift = 8 - depth * (x % per_byte + 1)
                    idx = (byte >> shift) & mask
                    idx = min(idx, max_idx)
                    row.append((plte[3 * idx], plte[3 * idx + 1], plte[3 * idx + 2]))
        rows.append(row)
    return rows


def write_png_rgb(path, rows: list, w: int, h: int) -> None:
    """Encode rows of (r, g, b) as an 8-bit RGB PNG, filter type 0."""
    raw = bytearray()
    for row in rows:
        raw.append(0)
        for (r, g, b) in row:
            raw += bytes((int(r) & 0xFF, int(g) & 0xFF, int(b) & 0xFF))

    def chunk(tag: bytes, payload: bytes) -> bytes:
        return (struct.pack(">I", len(payload)) + tag + payload
                + struct.pack(">I", zlib.crc32(tag + payload) & 0xFFFFFFFF))

    ihdr = struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0)
    png = (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr)
           + chunk(b"IDAT", zlib.compress(bytes(raw), 6)) + chunk(b"IEND", b""))
    with open(path, "wb") as fh:
        fh.write(png)


def image_size(path) -> tuple[int, int] | None:
    """Pixel dimensions of a PNG header, or None when unreadable."""
    try:
        with open(path, "rb") as fh:
            head = fh.read(24)
        if head[:8] != _MAGIC:
            return None
        w, h = struct.unpack_from(">II", head, 16)
        return int(w), int(h)
    except OSError:
        return None
