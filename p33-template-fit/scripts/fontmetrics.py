"""True Type font metrics with nothing but the standard library.

The audit's two font-dependent verdicts — "does this text fit its box" and
"can any installed font draw these characters" — used to depend on optional
third-party readers (Pillow, matplotlib.ft2font). On a machine without them
the checks silently degraded or, worse, reported every character as missing.
This module removes that failure class: it parses the TrueType/OpenType tables
directly with `struct`, so glyph coverage and real advance widths work in any
Python 3.9+ environment.

What is read, and what it is used for:

  cmap   char -> glyph index          glyph coverage (`export.missing_glyphs`)
  head   unitsPerEm                   scale font units -> pixels
  hhea   numberOfHMetrics             how many advances are stored
  hmtx   per-glyph advance widths     wrapped overflow measurement
  name   family names (IDs 1, 16)     is a declared typeface actually installed

Formats: raw TTF/OTF ("sfnt"), and TTC collections (Windows ships CJK faces
such as msyh.ttc as collections; the first face is used). CFF-flavoured OTF
files carry the same head/cmap/hmtx tables, so advances work there too; only
`glyf` outlines are never needed.
"""

from __future__ import annotations

import struct
from pathlib import Path

_CACHE: dict[str, "FontMetrics | None"] = {}


def _u16(b: bytes, off: int) -> int:
    return struct.unpack_from(">H", b, off)[0]


def _i16(b: bytes, off: int) -> int:
    return struct.unpack_from(">h", b, off)[0]


def _u32(b: bytes, off: int) -> int:
    return struct.unpack_from(">I", b, off)[0]


class FontMetrics:
    """The subset of one font face this engine needs."""

    def __init__(self, data: bytes) -> None:
        self.units_per_em = 1000
        self.advances: dict[int, int] = {}          # glyph index -> advance (font units)
        self.chars: set[int] = set()                # covered code points
        self.family_names: set[str] = set()
        self.readable = False
        self._parse(data)

    # -- parsing -----------------------------------------------------------

    def _parse(self, data: bytes) -> None:
        try:
            tables = self._sfnt_tables(data)
            if not tables:
                return
            self._parse_head(tables, data)
            self._parse_cmap(tables, data)
            self._parse_hmtx(tables, data)
            self._parse_name(tables, data)
            self.readable = bool(self.chars) or bool(self.advances)
        except (struct.error, IndexError, ValueError, KeyError):
            self.readable = False

    @staticmethod
    def _sfnt_tables(data: bytes) -> dict[str, tuple[int, int]]:
        """Table directory of the first face: {tag: (offset, length)}."""
        if data[:4] == b"ttcf":
            n = _u32(data, 8)
            off = _u32(data, 12)
            return FontMetrics._read_dir(data, off)
        if data[:4] in (b"\x00\x01\x00\x00", b"OTTO", b"true", b"typ1"):
            return FontMetrics._read_dir(data, 0)
        return {}

    @staticmethod
    def _read_dir(data: bytes, base: int) -> dict[str, tuple[int, int]]:
        num = _u16(data, base + 4)
        out: dict[str, tuple[int, int]] = {}
        for i in range(num):
            rec = base + 12 + 16 * i
            tag = data[rec:rec + 4].decode("latin-1", "replace")
            off = _u32(data, rec + 8)
            length = _u32(data, rec + 12)
            out[tag] = (off, length)
        return out

    def _parse_head(self, tables, data) -> None:
        if "head" in tables:
            off, _ = tables["head"]
            upem = _u16(data, off + 18)
            if 16 <= upem <= 16384:
                self.units_per_em = upem

    def _parse_hmtx(self, tables, data) -> None:
        if "hmtx" not in tables or "hhea" not in tables:
            return
        hoff, _ = tables["hhea"]
        num_h = _u16(data, hoff + 34)
        moff, mlen = tables["hmtx"]
        last = 0
        for i in range(min(num_h, mlen // 4)):
            self.advances[i] = _u16(data, moff + 4 * i)
            last = self.advances[i]
        # Glyphs beyond numberOfHMetrics share the last advance.
        self._last_advance = last

    def _parse_cmap(self, tables, data) -> None:
        if "cmap" not in tables:
            return
        coff, _ = tables["cmap"]
        num = _u16(data, coff + 2)
        best: tuple[int, int] | None = None     # (priority, subtable offset)
        prio = {(3, 10): 5, (0, 4): 4, (0, 6): 4, (3, 1): 3, (0, 3): 2,
                (0, 2): 2, (0, 1): 2, (0, 0): 1, (1, 0): 0}
        for i in range(num):
            rec = coff + 4 + 8 * i
            pid = _u16(data, rec)
            eid = _u16(data, rec + 2)
            off = _u32(data, rec + 4)
            p = prio.get((pid, eid))
            if p is not None and (best is None or p > best[0]):
                best = (p, coff + off)
        if best is None:
            return
        self._read_cmap_subtable(data, best[1])

    def _read_cmap_subtable(self, data: bytes, off: int) -> None:
        fmt = _u16(data, off)
        if fmt == 0:
            for i in range(256):
                g = data[off + 6 + i]
                if g:
                    self.chars.add(i)
                    self._note_char(i, g)
        elif fmt == 4:
            segx2 = _u16(data, off + 6)
            seg = segx2 // 2
            ends = [_u16(data, off + 14 + 2 * i) for i in range(seg)]
            starts = [_u16(data, off + 16 + segx2 + 2 * i) for i in range(seg)]
            deltas = [_i16(data, off + 16 + 2 * segx2 + 2 * i) for i in range(seg)]
            range_off_base = off + 16 + 3 * segx2
            for i in range(seg):
                ro = _u16(data, range_off_base + 2 * i)
                for c in range(starts[i], min(ends[i], 0x10FFFF) + 1):
                    if c == 0xFFFF:
                        break
                    if ro == 0:
                        g = (c + deltas[i]) & 0xFFFF
                    else:
                        addr = range_off_base + 2 * i + ro + 2 * (c - starts[i])
                        if addr + 1 >= len(data):
                            continue
                        gg = _u16(data, addr)
                        g = (gg + deltas[i]) & 0xFFFF if gg else 0
                    if g:
                        self.chars.add(c)
                        self._note_char(c, g)
        elif fmt == 6:
            first = _u16(data, off + 6)
            count = _u16(data, off + 8)
            for i in range(count):
                c = first + i
                g = _u16(data, off + 10 + 2 * i)
                if g:
                    self.chars.add(c)
                    self._note_char(c, g)
        elif fmt == 12:
            ngroups = _u32(data, off + 12)
            for i in range(ngroups):
                rec = off + 16 + 12 * i
                s = _u32(data, rec)
                e = _u32(data, rec + 4)
                sg = _u32(data, rec + 8)
                if e - s > 0x20000:
                    e = s + 0x20000
                for k in range(e - s + 1):
                    c = s + k
                    g = sg + k
                    if g:
                        self.chars.add(c)
                        self._note_char(c, g)

    def _note_char(self, char: int, glyph: int) -> None:
        # Record the char -> glyph mapping once; advances are looked up lazily.
        if not hasattr(self, "_glyph_of"):
            self._glyph_of = {}
        self._glyph_of[char] = glyph

    def _parse_name(self, tables, data) -> None:
        if "name" not in tables:
            return
        off, _ = tables["name"]
        count = _u16(data, off + 2)
        str_off = off + _u16(data, off + 4)
        for i in range(count):
            rec = off + 6 + 12 * i
            pid = _u16(data, rec)
            name_id = _u16(data, rec + 6)
            length = _u16(data, rec + 8)
            ro = _u16(data, rec + 10)
            if name_id not in (1, 16):
                continue
            raw = data[str_off + ro: str_off + ro + length]
            try:
                text = raw.decode("utf-16-be") if pid == 3 else raw.decode("latin-1")
            except Exception:
                continue
            if text.strip():
                self.family_names.add(text.strip())

    # -- queries ------------------------------------------------------------

    def has_char(self, ch: str) -> bool:
        if not self.readable:
            return False
        g = getattr(self, "_glyph_of", {})
        if g:
            return ord(ch) in g
        return ord(ch) in self.chars

    def advance(self, ch: str) -> float:
        """Advance width of one character in font units (0 when unknown)."""
        glyph = getattr(self, "_glyph_of", {}).get(ord(ch))
        if glyph is None:
            return 0.0
        adv = self.advances.get(glyph)
        if adv is None:
            adv = getattr(self, "_last_advance", 0)
        return float(adv)

    def text_width_px(self, text: str, size_pt: float, dpi: int = 96) -> float:
        """Width of `text` in pixels at `size_pt`, from real advance widths.

        A character with no glyph counts at one full em: the deck is about to
        show a .notdef box for it, and one em is the conservative reading of
        what that box occupies, rather than pretending the character is absent.
        """
        px = size_pt * dpi / 72.0
        upem = max(self.units_per_em, 1)
        total = 0.0
        for ch in text:
            if ch in "\t\n\r":
                continue
            if not self.has_char(ch):
                total += upem
                continue
            total += self.advance(ch)
        return total / upem * px

    def missing(self, text: str) -> tuple[str, ...]:
        """Characters with no glyph in this font."""
        if not self.readable:
            return ()
        return tuple(sorted({ch for ch in text if not ch.isspace() and not self.has_char(ch)}))


def load_font(path) -> FontMetrics | None:
    """Parse one font file (cached). None when the file cannot be read as a face."""
    key = str(path)
    if key in _CACHE:
        return _CACHE[key]
    fm: FontMetrics | None
    try:
        data = Path(path).read_bytes()
        fm = FontMetrics(data)
        if not fm.readable:
            fm = None
    except OSError:
        fm = None
    _CACHE[key] = fm
    return fm


def measure_text_px(text: str, size_pt: float, dpi: int = 96,
                    font_path: str | None = None) -> float | None:
    """Real advance-width measurement, or None when no readable font is given."""
    if not font_path:
        return None
    fm = load_font(font_path)
    if fm is None:
        return None
    return fm.text_width_px(text, size_pt, dpi)


def family_matches_file(family: str, path) -> bool:
    """Whether the face at `path` claims the given family name.

    Normalises case, spaces, hyphens and the common UI suffixes so "Microsoft
    YaHei" matches the family record in msyh.ttc and "Noto Sans SC" matches
    "Noto Sans SC Regular".
    """
    fm = load_font(path)
    if fm is None:
        return False
    want = _norm_family(family)
    if not want:
        return False
    for name in fm.family_names:
        if _norm_family(name) == want:
            return True
        # A family record may carry a style suffix; strip it the same way.
        if _norm_family(name.replace(" Regular", "").replace(" Bold", "")) == want:
            return True
    return False


def _norm_family(s: str) -> str:
    for suf in (" regular", " bold", " italic", " light", " medium"):
        if s.lower().endswith(suf):
            s = s[: -len(suf)]
    return "".join(c for c in s.lower() if c.isalnum())
