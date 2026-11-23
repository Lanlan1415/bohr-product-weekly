"""Section, heading, and layout structure detection for pdf-parse.

Detects heading lines (by font size heuristics, numbering prefixes, and common
academic section names) and labels title/abstract/section levels. Returns a
section tree with locators back to page + block index.
"""
from __future__ import annotations

import re

NUMBERED = re.compile(r"^\s*(\d+(?:\.\d+){0,3})[.\s]+([A-Z一-鿿][\S]?.*)$")
NAMED = re.compile(
    r"^\s*(abstract|introduction|background|methods?|materials? and methods|"
    r"experimental (?:section|setup|procedures?)|results(?: and discussion)?|"
    r"discussion|conclusion(?:s)?|acknowledg(?:e)?ments?|references|bibliography|"
    r"appendix|supplementary\s+(?:materials?|information)|"
    r"综述|引言|摘要|方法|材料与方法|结果|讨论|结论|致谢|参考文献|附录)\b",
    re.IGNORECASE)
HEADER_FOOTER = re.compile(
    r"^\s*(\d+\s*[-–—]\s*\d+|page\s+\d+(?:\s+of\s+\d+)?)\s*$",
    re.IGNORECASE)


def is_heading(text: str) -> tuple[bool, str | None, str]:
    """Returns (is_heading, level, normalized_title)."""
    t = text.strip()
    if not t or len(t) > 200:
        return False, None, t
    if HEADER_FOOTER.match(t):
        return False, None, t
    m = NUMBERED.match(t)
    if m:
        dots = m.group(1).count(".")
        level = ["1", "1.1", "1.1.1", "1.1.1.1"][dots] if dots < 4 else "1.1.1.1"
        return True, level, t
    if NAMED.match(t):
        return True, "1", t
    return False, None, t


def identify_sections(blocks: list[dict], page: int) -> list[dict]:
    """Mark blocks as title/heading/paragraph/figure_caption with locators."""
    out: list[dict] = []
    render_kinds = {"title", "heading", "paragraph",
                    "figure_caption", "table_caption", "header_footer"}
    for idx, b in enumerate(blocks):
        text = b.get("text", "").strip()
        kind = b.get("kind", "paragraph")
        if kind not in render_kinds:
            kind = "paragraph"
        ok, level, _ = is_heading(text)
        if ok:
            kind = "heading"
            b["heading_level"] = level
        if re.match(r"^(figure|fig\.?|图)\s*\d+", text, re.IGNORECASE):
            kind = "figure_caption"
        if re.match(r"^(table|tab\.?|表)\s*\d+", text, re.IGNORECASE):
            kind = "table_caption"
        b["kind"] = kind
        b["locator"] = {"page": page, "block": idx, "column": b.get("column")}
        out.append(b)
    return out


def build_outline(blocks: list[dict]) -> list[dict]:
    """Numbered heading outline (only 1 / 1.1 / 1.1.1 levels)."""
    outline = []
    stack: list[tuple[str, list]] = []
    for b in blocks:
        if b.get("kind") != "heading":
            continue
        level = b.get("heading_level", "1")
        title = b.get("text", "").strip()
        while stack and len(stack[-1][0]) >= len(level) and stack:
            stack.pop()
        item = {"level": level, "title": title, "page": b["locator"]["page"],
                "block": b["locator"]["block"], "children": []}
        if stack:
            stack[-1][1].append(item)
        else:
            outline.append(item)
        stack.append((level, item["children"]))
    return outline
