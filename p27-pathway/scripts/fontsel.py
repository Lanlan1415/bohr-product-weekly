"""Pick a font that can actually draw the labels, and prove it.

The defect this exists for: matplotlib's default DejaVu Sans has no CJK glyphs, so a
Chinese label renders as a row of empty boxes. The figure still saves, the file still
opens, and every Chinese character in it is unreadable — which is exactly the failure
"字体未嵌入导致中文变成方框" that this challenge names.

Coverage is checked against **the characters the figure actually uses**, not against
"is this a CJK font". A label may mix CJK, Latin, Greek and maths symbols, and a font
that covers Chinese may still lack `µ` or `θ`.
"""

from __future__ import annotations

import glob
from dataclasses import dataclass
from pathlib import Path

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

    @property
    def ok(self) -> bool:
        return self.path is not None and not self.missing


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


# Filename fragments that mark a CJK-capable face in the wild, for the
# matplotlib-managed fallback scan. Broad on purpose: a container that ships
# only "NotoSansCJKtc-Regular.otf" or "DroidSansFallbackFull.ttf" must still be
# found, because otherwise every Chinese label degrades to empty boxes.
_CJK_MARKERS = ("yahei", "simhei", "heiti", "cjk", "sourcehan", "source-han",
                "wqy", "zenhei", "song", "sun", "ming", "hei", "kai", "deng",
                "han", "droidsansfallback", "malgun", "meiryo", "msgothic",
                "msmincho", "hiragino", "unicode")


def _manager_candidates(limit: int = 40) -> list[str]:
    """Font files matplotlib knows about whose name suggests CJK coverage.

    Deterministic (sorted, capped) so the resolver cannot flip between runs —
    this scan is the wide net behind the preferred list, not a lottery.
    """
    try:
        from matplotlib import font_manager
        files = font_manager.findSystemFonts(fontext="ttf")
    except Exception:
        return []
    picked = sorted(f for f in files
                    if any(m in Path(f).name.lower() for m in _CJK_MARKERS))
    return picked[:limit]


def coverage(path: str, text: str) -> tuple[str, ...]:
    """Characters in `text` that have no glyph in the font at `path`.

    Returns an empty tuple when the file cannot be read — unknown is reported as
    unknown rather than as complete.
    """
    try:
        from matplotlib.ft2font import FT2Font
        ft = FT2Font(path)
    except Exception:
        return tuple(sorted(set(c for c in text if not c.isspace())))

    missing = []
    for ch in sorted(set(text)):
        if ch.isspace():
            continue
        try:
            if ft.get_char_index(ord(ch)) == 0:
                missing.append(ch)
        except Exception:
            missing.append(ch)
    return tuple(missing)


def resolve(text: str = "") -> Resolved:
    """Choose the first preferred font that covers every character in `text`.

    Falls back to the best partial candidate, so the caller still gets a usable font
    and an explicit `missing` list rather than an exception.
    """
    best: Resolved | None = None
    seen: set[str] = set()

    def consider(family: str, path: str) -> Resolved:
        miss = coverage(path, text)
        return Resolved(family=family, path=path, missing=miss)

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

    # Wide net: every CJK-suggesting file matplotlib can see, preferred list and
    # filesystem guesses exhausted. Containers regularly install faces under
    # names or directories the preferred list does not know.
    for path in _manager_candidates():
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
                    missing=tuple(sorted(set(c for c in text if not c.isspace()))))


def labels_text(spec: dict) -> str:
    """Every character the figure will draw, gathered from the spec."""
    parts = []
    for n in spec.get("nodes") or []:
        if isinstance(n, dict):
            parts.append(str(n.get("label") or ""))
    for e in spec.get("edges") or []:
        if isinstance(e, dict):
            parts.append(str(e.get("label") or ""))
    parts.append(str(spec.get("title") or ""))
    parts.append(str(spec.get("caption") or ""))
    for g in spec.get("groups") or []:
        parts.append(str(g))
    return "".join(parts)
