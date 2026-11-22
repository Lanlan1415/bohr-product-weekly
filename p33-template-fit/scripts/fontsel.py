"""Pick a font that can actually draw the labels, and prove it.

The defect this exists for: a Latin-only default face has no CJK glyphs, so a
Chinese label renders as a row of empty boxes. The figure still saves, the file
still opens, and every Chinese character in it is unreadable — which is exactly
the failure "字体未嵌入导致中文变成方框" that this challenge names.

Coverage is checked against **the characters the figure actually uses**, not
against "is this a CJK font". A label may mix CJK, Latin, Greek and maths
symbols, and a font that covers Chinese may still lack `µ` or `θ`.

Coverage and measurement run on `fontmetrics.py` — the pure-standard-library
TrueType reader — so both work in any Python 3.9+ environment. A missing font
reader used to be invisible here; now "cannot verify" is a distinct state
(`measured=False`) that callers must report honestly instead of treating as
"no glyphs anywhere".
"""

from __future__ import annotations

import glob
from dataclasses import dataclass
from pathlib import Path

import fontmetrics as FM

# Ordered by preference: a humanist sans that covers both scripts reads best in a
# figure, then the common Windows faces, then the open Noto families.
PREFERRED = [
    ("Microsoft YaHei", ["msyh.ttc", "msyh.ttf"]),
    ("Noto Sans SC", ["NotoSansSC-VF.ttf", "NotoSansCJK-Regular.ttc"]),
    ("SimHei", ["simhei.ttf"]),
    ("Source Han Sans SC", ["SourceHanSansSC-Regular.otf"]),
    ("SimSun", ["simsun.ttc"]),
    ("DengXian", ["Deng.ttf", "Dengb.ttf"]),
    ("WenQuanYi Zen Hei", ["wqy-zenhei.ttc"]),
    ("DejaVu Sans", ["DejaVuSans.ttf"]),
    ("Arial", ["arial.ttf"]),
]

FONT_DIRS = [
    "C:/Windows/Fonts",
    "/usr/share/fonts",
    "/usr/local/share/fonts",
    str(Path.home() / ".fonts"),
]


@dataclass(frozen=True)
class Resolved:
    family: str
    path: str | None
    missing: tuple[str, ...]
    measured: bool = False

    @property
    def ok(self) -> bool:
        return self.path is not None and self.measured and not self.missing


def _find(names: list[str]) -> str | None:
    """Locate a font file by bare name across the known font directories."""
    for d in FONT_DIRS:
        for name in names:
            direct = Path(d) / name
            if direct.exists():
                return str(direct)
            hits = glob.glob(str(Path(d) / "**" / name), recursive=True)
            if hits:
                return hits[0]
    return None


def _cjk_fonts() -> list[str]:
    """Any installed file whose name looks CJK-capable, as a last resort."""
    out = []
    for d in FONT_DIRS:
        for pat in ("*yahei*", "*simhei*", "*heiti*", "*NotoSans*SC*", "*SourceHan*",
                    "*wqy*", "*song*", "*han*"):
            out.extend(glob.glob(str(Path(d) / "**" / pat), recursive=True))
    return out


def find_family_file(family: str) -> str | None:
    """Locate an installed file for a declared family name.

    Used by the audit's `font.declared_missing` check: the family is installed
    when a file in the font directories either matches the family's usual file
    name or actually carries the family name in its name table. This is the
    fallback that keeps the check honest on machines without matplotlib's font
    index — which previously reported every declared face as missing.
    """
    want = FM._norm_family(family)
    if not want:
        return None
    seen: list[str] = []
    for d in FONT_DIRS:
        if not Path(d).is_dir():
            continue
        seen.extend(str(p) for p in Path(d).glob("*.tt[fc]"))
        seen.extend(str(p) for p in Path(d).glob("*.otf"))
    # Exact stem match first, then a name-table match over the directory.
    for p in seen:
        if FM._norm_family(Path(p).stem) == want:
            return p
    for p in seen:
        if FM.family_matches_file(family, p):
            return p
    return _find(_FAMILY_FILES.get(want, [])) or None


# Families whose file names are conventional rather than derived from the name.
_FAMILY_FILES = {
    "microsoftyahei": ["msyh.ttc", "msyh.ttf", "msyhbd.ttc"],
    "arial": ["arial.ttf"],
    "timesnewroman": ["times.ttf", "timesbd.ttf"],
    "calibri": ["calibri.ttf"],
    "cambria": ["cambria.ttc"],
    "simsun": ["simsun.ttc"],
    "simhei": ["simhei.ttf"],
    "dejavusans": ["DejaVuSans.ttf"],
    "consolas": ["consola.ttf"],
    "segoeui": ["segoeui.ttf"],
    "dengxian": ["Deng.ttf"],
}


def coverage(path: str, text: str) -> tuple[str, ...]:
    """Characters in `text` that have no glyph in the font at `path`.

    Read with the standard-library TrueType parser, so this works whether or
    not matplotlib is installed. Returns an empty tuple when the file cannot be
    read — unknown is reported as unknown rather than as complete; callers that
    need to distinguish the two use `coverage_result`.
    """
    missing, measured = coverage_result(path, text)
    return missing


def coverage_result(path: str, text: str) -> tuple[tuple[str, ...], bool]:
    """(missing characters, whether the font file could actually be read)."""
    fm = FM.load_font(path)
    if fm is None:
        return (), False
    return fm.missing(text), True


def resolve(text: str = "") -> Resolved:
    """Choose the first preferred font that covers every character in `text`.

    Falls back to the best partial candidate, so the caller still gets a usable
    font and an explicit `missing` list rather than an exception. `measured`
    says whether any candidate could actually be read: a False here means
    glyph coverage is unknown, not "everything is missing".
    """
    best: Resolved | None = None
    seen: set[str] = set()

    def consider(family: str, path: str) -> Resolved:
        miss, meas = coverage_result(path, text)
        return Resolved(family=family, path=path, missing=miss, measured=meas)

    for family, names in PREFERRED:
        path = _find(names)
        if not path or path in seen:
            continue
        seen.add(path)
        cand = consider(family, path)
        if cand.ok:
            return cand
        if best is None or len(cand.missing) < len(best.missing):
            best = cand

    for path in _cjk_fonts():
        if path in seen:
            continue
        seen.add(path)
        cand = consider(Path(path).stem, path)
        if cand.ok:
            return cand
        if best is None or len(cand.missing) < len(best.missing):
            best = cand

    if best is not None:
        return best

    # Nothing found at all: name it rather than pretending.
    return Resolved(family="<none>", path=None,
                    missing=tuple(sorted(set(c for c in text if not c.isspace()))),
                    measured=False)


def labels_text(spec: dict) -> str:
    """Every character the figure will draw, gathered from the spec."""
    parts = []
    for n in spec.get("nodes") or []:
        parts.append(str(n.get("label") or ""))
    for e in spec.get("edges") or []:
        parts.append(str(e.get("label") or ""))
    parts.append(str(spec.get("title") or ""))
    parts.append(str(spec.get("caption") or ""))
    for g in spec.get("groups") or []:
        parts.append(str(g))
    return "".join(parts)
