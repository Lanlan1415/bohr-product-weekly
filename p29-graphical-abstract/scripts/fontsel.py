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

    if best is not None:
        return best

    # Nothing found at all: name it rather than pretending.
    return Resolved(family="<none>", path=None,
                    missing=tuple(sorted(set(c for c in text if not c.isspace()))))


def labels_text(spec: dict) -> str:
    """Every character the figure will draw, gathered from the spec."""
    parts = ["INPUT QUESTION METHOD RESULT MECHANISM CONCLUSION Source observation Scope limitation"]
    for n in spec.get("nodes") or []:
        if not isinstance(n, dict):
            continue
        parts.append(str(n.get("label") or ""))
        parts.append(str(n.get("visual_caption") or ""))
        parts.extend(str(step) for step in (n.get("steps") or []))
        data = n.get("visual_data") or {}
        if isinstance(data, dict):
            parts.append(str(data.get("unit") or ""))
            parts.append(str(data.get("uncertainty") or ""))
            parts.append(str(data.get("n_caption") or ""))
            if data.get("n") is not None:
                parts.append(f"n = {data['n']}")
            for item in data.get("items") or []:
                if isinstance(item, dict):
                    parts.append(str(item.get("label") or item.get("id") or ""))
                    if item.get("value") is not None:
                        try:
                            parts.append(f"{float(item['value']):g}")
                        except (TypeError, ValueError):
                            parts.append(str(item.get("value")))
    for e in spec.get("edges") or []:
        if isinstance(e, dict):
            parts.append(str(e.get("label") or ""))
    core = spec.get("core_message")
    parts.append(str(core.get("text") or "") if isinstance(core, dict) else str(core or ""))
    for item in spec.get("limitations") or []:
        parts.append(str(item.get("text") or "") if isinstance(item, dict) else str(item))
    parts.append(str(spec.get("title") or ""))
    parts.append(str(spec.get("caption") or ""))
    for g in spec.get("groups") or []:
        parts.append(str(g))
    return "".join(parts)
