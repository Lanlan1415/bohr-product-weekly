"""Small, independent SFNT reader for glyph coverage and text advance widths.

This is not a font renderer.  It reads the standard TTF/TTC/OTF tables needed by
an audit (cmap, head, hhea, hmtx, name) so isolated Python can still measure text
instead of crashing on an optional Pillow import.
"""
from __future__ import annotations

import struct
from functools import lru_cache
from pathlib import Path


def _u16(data: bytes, offset: int) -> int:
    return struct.unpack_from(">H", data, offset)[0]


def _i16(data: bytes, offset: int) -> int:
    return struct.unpack_from(">h", data, offset)[0]


def _u32(data: bytes, offset: int) -> int:
    return struct.unpack_from(">I", data, offset)[0]


class SFNT:
    def __init__(self, path: str | Path):
        self.path = str(path)
        self.data = Path(path).read_bytes()
        if self.data[:4] == b"ttcf":
            base = _u32(self.data, 12)
        else:
            base = 0
        count = _u16(self.data, base + 4)
        self.tables = {}
        for index in range(count):
            pos = base + 12 + index * 16
            tag = self.data[pos:pos + 4].decode("latin1")
            self.tables[tag] = (_u32(self.data, pos + 8), _u32(self.data, pos + 12))
        head, _ = self.tables["head"]
        self.units_per_em = _u16(self.data, head + 18) or 1000
        hhea, _ = self.tables["hhea"]
        self.metric_count = _u16(self.data, hhea + 34)
        self.cmap = self._read_cmap()

    def _table(self, name: str) -> tuple[int, int]:
        return self.tables[name]

    def _read_cmap(self) -> dict[int, int]:
        base, _ = self._table("cmap")
        candidates = []
        for index in range(_u16(self.data, base + 2)):
            rec = base + 4 + index * 8
            platform, encoding = _u16(self.data, rec), _u16(self.data, rec + 2)
            sub = base + _u32(self.data, rec + 4)
            fmt = _u16(self.data, sub)
            score = (100 if fmt == 12 else 50 if fmt == 4 else 0)
            score += 20 if platform == 3 else 10 if platform == 0 else 0
            score += 5 if encoding in (1, 10) else 0
            if score:
                candidates.append((score, fmt, sub))
        for _, fmt, sub in sorted(candidates, reverse=True):
            try:
                return self._cmap12(sub) if fmt == 12 else self._cmap4(sub)
            except (IndexError, struct.error, KeyError):
                continue
        return {}

    def _cmap12(self, sub: int) -> dict[int, int]:
        mapping = {}
        for index in range(_u32(self.data, sub + 12)):
            pos = sub + 16 + index * 12
            start, end, gid = (_u32(self.data, pos), _u32(self.data, pos + 4),
                               _u32(self.data, pos + 8))
            # A defensive cap prevents a hostile font from expanding unbounded memory.
            if end < start or end - start > 0x10FFFF:
                continue
            for code in range(start, end + 1):
                mapping[code] = gid + code - start
        return mapping

    def _cmap4(self, sub: int) -> dict[int, int]:
        mapping = {}
        segx2 = _u16(self.data, sub + 6)
        segments = segx2 // 2
        ends = sub + 14
        starts = ends + segx2 + 2
        deltas = starts + segx2
        ranges = deltas + segx2
        for index in range(segments):
            end = _u16(self.data, ends + index * 2)
            start = _u16(self.data, starts + index * 2)
            delta = _i16(self.data, deltas + index * 2)
            ro = _u16(self.data, ranges + index * 2)
            if start == 0xFFFF:
                continue
            for code in range(start, min(end, 0xFFFE) + 1):
                if ro == 0:
                    gid = (code + delta) & 0xFFFF
                else:
                    address = ranges + index * 2 + ro + (code - start) * 2
                    if address + 2 > len(self.data):
                        continue
                    raw = _u16(self.data, address)
                    gid = (raw + delta) & 0xFFFF if raw else 0
                if gid:
                    mapping[code] = gid
        return mapping

    def glyph(self, char: str) -> int:
        return self.cmap.get(ord(char), 0)

    def missing(self, text: str) -> tuple[str, ...]:
        return tuple(sorted({ch for ch in text if not ch.isspace() and not self.glyph(ch)}))

    def width(self, text: str, px: float) -> float:
        base, _ = self._table("hmtx")
        last_advance = self.units_per_em
        total = 0
        for char in text:
            gid = self.glyph(char)
            if gid < self.metric_count:
                advance = _u16(self.data, base + gid * 4)
                last_advance = advance
            else:
                advance = last_advance
            total += advance
        return total * px / self.units_per_em

    def family_names(self) -> set[str]:
        if "name" not in self.tables:
            return set()
        base, _ = self.tables["name"]
        count, strings = _u16(self.data, base + 2), _u16(self.data, base + 4)
        names = set()
        for index in range(count):
            rec = base + 6 + index * 12
            platform, name_id = _u16(self.data, rec), _u16(self.data, rec + 6)
            if name_id not in (1, 16):
                continue
            length, offset = _u16(self.data, rec + 8), _u16(self.data, rec + 10)
            start = base + strings + offset
            raw = self.data[start:start + length]
            for encoding in (("utf-16-be",) if platform in (0, 3) else ("latin1",)):
                try:
                    value = raw.decode(encoding).strip()
                    if value:
                        names.add(value)
                except UnicodeDecodeError:
                    pass
        return names


@lru_cache(maxsize=24)
def load(path: str | Path) -> SFNT:
    return SFNT(path)


def coverage(path: str | Path, text: str) -> tuple[str, ...]:
    return load(path).missing(text)


def family(path: str | Path) -> set[str]:
    try:
        return load(path).family_names()
    except (OSError, KeyError, IndexError, struct.error):
        return set()
