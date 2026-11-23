"""Scientific-document structure over real, page-anchored PDF blocks."""
from __future__ import annotations

import re
import statistics
from typing import Any

NUMBERED = re.compile(r"^\s*(\d+(?:\.\d+){0,5})[.)]?\s+([A-Za-z\u4e00-\u9fff][^\n]{0,179})$")
NAMED = {
    "abstract": "Abstract", "introduction": "Introduction", "background": "Background",
    "method": "Methods", "methods": "Methods", "materials and methods": "Materials and Methods",
    "experimental section": "Experimental Section", "experimental setup": "Experimental Setup",
    "results": "Results", "results and discussion": "Results and Discussion",
    "discussion": "Discussion", "conclusion": "Conclusion", "conclusions": "Conclusions",
    "acknowledgment": "Acknowledgments", "acknowledgments": "Acknowledgments",
    "acknowledgement": "Acknowledgments", "acknowledgements": "Acknowledgments",
    "references": "References", "bibliography": "References", "appendix": "Appendix",
    "supplementary material": "Supplementary Material", "supplementary information": "Supplementary Information",
    "摘要": "摘要", "引言": "引言", "方法": "方法", "材料与方法": "材料与方法",
    "结果": "结果", "讨论": "讨论", "结论": "结论", "致谢": "致谢", "参考文献": "参考文献", "附录": "附录",
}
CAPTION = re.compile(r"^\s*(figure|fig\.?|图|table|tab\.?|表)\s*([A-Za-z]?\d+[A-Za-z0-9.-]*)\s*[:.]?\s*(.*)$", re.I | re.S)
REFERENCE_MARK = re.compile(r"(?m)^\s*(?:\[(\d+)\]|(\d{1,3})[.)])\s+")


def is_heading(text: str, block: dict[str, Any] | None = None, body_font: float = 0) -> tuple[bool, int | None, str]:
    t = text.strip()
    if not t or len(t) > 190 or t.count("\n") > 1:
        return False, None, t
    named = NAMED.get(t.strip(" ：:").lower())
    if named:
        return True, 1, t
    m = NUMBERED.match(t)
    if m and len(t.split()) <= 30:
        # Decimal values, formulae, references and table rows are not headings.
        title = m.group(2).strip()
        if re.search(r"[.,;:!?，。；！？]$", title) or re.search(r"[=≈≡≠≤≥∑∫√]|\b(?:log|det|exp)\b", title, re.I):
            return False, None, t
        if re.match(r"^\d+[.)]\s+(?:et\s+al\.|pp\.|[A-Z][a-z]+\s+[A-Z][a-z]+\.)", t):
            return False, None, t
        if block and body_font:
            flags = [int(x) for x in block.get("flags", [])]
            all_bold = bool(flags) and all(bool(x & 16) for x in flags)
            size = float(block.get("font_size_max", 0) or 0)
            if not all_bold and size < body_font * 1.15:
                return False, None, t
        return True, m.group(1).count(".") + 1, t
    if block and body_font:
        size = float(block.get("font_size_max", 0) or 0)
        if size >= body_font * 1.22 and len(t.split()) <= 24 and not re.search(r"[.!?。！？]$", t):
            if not re.match(r"^(?:figure|fig\.?|table|tab\.?|图|表)\s*\d+", t, re.I):
                return True, 1, t
    return False, None, t


def _body_font(blocks: list[dict[str, Any]]) -> float:
    sizes = []
    for b in blocks:
        if b.get("type") != "text" or b.get("layout_role") or len(b.get("text", "")) < 40:
            continue
        size = float(b.get("font_size_median", 0) or 0)
        if size > 0:
            sizes.append(size)
    return statistics.median(sizes) if sizes else 0


def _block_id(page: int, source: int) -> str:
    return f"p{page:04d}-b{source:03d}"


def identify_document(blocks: list[dict[str, Any]], metadata: dict[str, Any] | None = None,
                      page_heights: dict[int, float] | None = None) -> list[dict[str, Any]]:
    metadata = metadata or {}
    page_heights = page_heights or {}
    body_font = _body_font(blocks)
    section_stack: list[tuple[int, str]] = []
    in_references = False
    in_abstract = False
    title_seen = False
    meta_title = str(metadata.get("title", "")).strip()
    meta_author = str(metadata.get("author", metadata.get("authors", ""))).strip()
    for b in blocks:
        page = int(b.get("page", (b.get("locator") or {}).get("page", 0)) or 0)
        source = int(b.get("source_block", b.get("order", 0)) or 0)
        b["block_id"] = _block_id(page, source)
        b["locator"] = {"page": page, "block": source, "order": b.get("order"),
                        "column": b.get("column"), "bbox": b.get("bbox"), "block_id": b["block_id"]}
        if b.get("type") == "image":
            b.update(kind="figure", include_in_body=False)
            continue
        if b.get("is_scanned"):
            b.update(kind="scanned_page", include_in_body=False)
            continue
        text = b.get("text", "").strip()
        if b.get("layout_role") in {"header", "footer"}:
            b.update(kind="header_footer", include_in_body=False, section_path=[])
            continue
        b["section_path"] = [x[1] for x in section_stack]
        if not text:
            b.update(kind="empty", include_in_body=False)
            continue

        # Captions take precedence over font and formula heuristics.
        if CAPTION.match(text):
            kind = "figure_caption" if re.match(r"(?:figure|fig\.?|图)", text, re.I) else "table_caption"
            b.update(kind=kind, include_in_body=False, caption=CAPTION.match(text).group(0))
            continue

        heading, level, _ = is_heading(text, b, body_font)
        first_page_candidate = page == 1 and ((not section_stack and not in_abstract) or exact_meta_title)
        exact_meta_title = bool(meta_title and (text == meta_title or _compact(text) == _compact(meta_title)))
        title_size = body_font and float(b.get("font_size_max", 0) or 0) >= body_font * 1.65
        if first_page_candidate and not title_seen and (exact_meta_title or title_size) and not NUMBERED.match(text) and not NAMED.get(text.strip(" ：:").lower()):
            b.update(kind="title", include_in_body=False, section_path=[])
            title_seen = True
            continue
        if first_page_candidate and title_seen and not heading:
            if meta_author and (_compact(text) == _compact(meta_author) or _compact(meta_author) in _compact(text)):
                b.update(kind="authors", include_in_body=False)
                continue
            if re.search(r"\b(?:university|institute|department|laboratory|hospital|college|academy)\b|@|大学|研究院|实验室|医院", text, re.I):
                b.update(kind="affiliation", include_in_body=False)
                continue
            # A short comma-separated byline immediately after the title is only
            # a candidate, never silently promoted into document metadata.
            if len(text) < 180 and "," in text and not re.search(r"\b(?:we|the|this|abstract)\b", text, re.I):
                b.update(kind="authors_candidate", include_in_body=False)
                continue

        h = page_heights.get(page, 0)
        size = float(b.get("font_size_median", 0) or 0)
        if h and size and body_font and float(b["bbox"][1]) > 0.82 * h and size < body_font * 0.90:
            b.update(kind="footnote", include_in_body=False)
            continue
        if heading:
            while section_stack and section_stack[-1][0] >= int(level):
                section_stack.pop()
            section_stack.append((int(level), text))
            b["section_path"] = [x[1] for x in section_stack[:-1]]
            b.update(kind="heading", heading_level=int(level), include_in_body=True)
            normalized = text.strip(" ：:").lower()
            in_references = normalized in {"references", "bibliography", "参考文献"}
            in_abstract = normalized == "abstract" or normalized == "摘要"
            continue
        if in_references:
            b.update(kind="reference", include_in_body=False)
        elif in_abstract:
            b.update(kind="abstract", include_in_body=True)
        else:
            b.update(kind="paragraph", include_in_body=b.get("include_in_body", True))
    return blocks


def _compact(text: str) -> str:
    return re.sub(r"\W+", "", text).lower()


def build_outline(blocks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    outline: list[dict[str, Any]] = []
    stack: list[tuple[int, list[dict[str, Any]]]] = []
    for b in blocks:
        if b.get("kind") != "heading":
            continue
        level = int(b.get("heading_level", 1))
        while stack and stack[-1][0] >= level:
            stack.pop()
        loc = b["locator"]
        item = {"level": level, "title": b.get("text", "").strip(), "page": loc["page"],
                "block": loc["block"], "block_id": b["block_id"], "bbox": loc.get("bbox"), "children": []}
        if stack:
            stack[-1][1].append(item)
        else:
            outline.append(item)
        stack.append((level, item["children"]))
    return outline


def flatten_outline(outline: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out = []
    def walk(items, parents):
        for item in items:
            row = {k: v for k, v in item.items() if k != "children"}
            row["section_path"] = parents + [item["title"]]
            out.append(row)
            walk(item.get("children", []), row["section_path"])
    walk(outline, [])
    return out


def build_sections(blocks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    headings = [(i, b) for i, b in enumerate(blocks) if b.get("kind") == "heading"]
    sections = []
    for pos, (start, heading) in enumerate(headings):
        level = int(heading.get("heading_level", 1))
        end = len(blocks)
        for j, nxt in headings[pos + 1:]:
            if int(nxt.get("heading_level", 1)) <= level:
                end = j
                break
        content = [b for b in blocks[start + 1:end] if b.get("kind") != "heading"]
        sections.append({"section_id": heading["block_id"], "title": heading["text"], "level": level,
                         "section_path": heading.get("section_path", []) + [heading["text"]],
                         "start": heading["locator"],
                         "end_page": content[-1]["locator"]["page"] if content else heading["locator"]["page"],
                         "block_ids": [b["block_id"] for b in content],
                         "text": "\n\n".join(b.get("text", "") for b in content if b.get("type") == "text")})
    return sections


def extract_captions(blocks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    captions = []
    for b in blocks:
        if b.get("kind") not in {"figure_caption", "table_caption"}:
            continue
        match = CAPTION.match(b.get("text", ""))
        if not match:
            continue
        group = match.group(1).lower()
        captions.append({"caption_id": b["block_id"] + "-caption",
                         "kind": "figure" if group.startswith(("fig", "图")) else "table",
                         "label": f"{match.group(1)} {match.group(2)}", "number": match.group(2),
                         "text": b["text"], "locator": b["locator"], "linked_target": None})
    return captions


def _has_reference_year(text: str) -> bool:
    return bool(re.search(r"(?<!\d)(?:19|20)\d{2}[a-z]?[.)]", text))


def _looks_like_author_start(text: str) -> bool:
    flat = re.sub(r"\s+", " ", text).strip()
    if not flat or len(flat) > 420 or not re.match(r"^[A-ZÀ-Þ]", flat) or \
            re.match(r"(?:https?://|doi\b|in\b|proceedings\b|journal\b|using\b|linear\b)", flat, re.I):
        return False
    ym = re.search(r"(?<!\d)(?:19|20)\d{2}[a-z]?[.)]", flat)
    prefix = flat[:ym.start()].strip(" ,;.") if ym else flat.strip(" ,;.")
    if not prefix or len(prefix.split()) > 45 or \
            re.search(r"\b(?:proceedings|journal|conference|meeting|association|international|pages|technical\s+papers|"
                      r"january|february|march|april|may|june|july|august|september|october|november|december)\b", prefix, re.I):
        return False
    capitals = re.findall(r"\b[A-ZÀ-Þ][A-Za-zÀ-þ'’´`-]*", prefix)
    if ("," in prefix or re.search(r"\band\b", prefix)) and len(capitals) >= 2:
        return True
    # Single-author entries with an explicit year are also a boundary; a bare
    # conference year with no author prefix cannot trigger this branch.
    return bool(ym and len(prefix) < 120 and len(prefix.split()) <= 12 and
                re.fullmatch(r"[A-ZÀ-Þ0-9 .,'’´&-]+", prefix))


def _reference_record(parts: list[dict[str, Any]], index: int, numbered: bool) -> dict[str, Any]:
    value = "\n".join(p["text"].strip() for p in parts if p["text"].strip())
    doi = re.search(r"\b10\.\d{4,9}/[^\s]+", value, re.I)
    first = parts[0]
    return {"reference_id": f"{first['block_id']}-ref-{index:03d}",
            "number": first.get("number"), "text": value,
            "doi": doi.group(0).rstrip(".") if doi else None,
            "locator": first["locator"],
            "component_blocks": [{"block_id": p["block_id"], "locator": p["locator"],
                                  "char_start": p.get("char_start", 0), "char_end": p.get("char_end", len(p["text"]))}
                                 for p in parts],
            "source": "explicit reference numbers" if numbered else "unnumbered author/year boundary heuristic",
            "review_required": not numbered}


def extract_references(blocks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    source = [b for b in blocks if b.get("kind") == "reference" and b.get("text", "").strip()]
    if not source:
        return []
    references: list[dict[str, Any]] = []
    if any(REFERENCE_MARK.search(b["text"]) for b in source):
        parts: list[dict[str, Any]] = []
        def flush():
            nonlocal parts
            if parts:
                references.append(_reference_record(parts, len(references) + 1, True))
                parts = []
        for b in source:
            text = b["text"]
            matches = list(REFERENCE_MARK.finditer(text))
            if not matches:
                if parts:
                    parts.append({"text": text, "block_id": b["block_id"], "locator": b["locator"]})
                continue
            prefix = text[:matches[0].start()].strip()
            if prefix and parts:
                parts.append({"text": prefix, "block_id": b["block_id"], "locator": b["locator"]})
            for i, match in enumerate(matches):
                flush()
                end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
                parts = [{"text": text[match.start():end].strip(), "block_id": b["block_id"],
                          "locator": b["locator"], "number": match.group(1) or match.group(2),
                          "char_start": match.start(), "char_end": end}]
            flush()
        flush()
        return references

    groups: list[list[dict[str, Any]]] = []
    current: list[dict[str, Any]] = []
    has_year = False
    for b in source:
        starts = _looks_like_author_start(b["text"])
        if current and has_year and starts:
            groups.append(current)
            current, has_year = [], False
        current.append({"text": b["text"], "block_id": b["block_id"], "locator": b["locator"]})
        has_year = has_year or _has_reference_year(b["text"])
    if current:
        groups.append(current)
    for parts in groups:
        references.append(_reference_record(parts, len(references) + 1, False))
    return references


def cross_page_continuations(blocks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Conservative candidates only; source blocks are never destructively merged."""
    body = [b for b in blocks if b.get("kind") in {"paragraph", "abstract"} and b.get("include_in_body", True)]
    out = []
    for prev, nxt in zip(body, body[1:]):
        if nxt["locator"]["page"] != prev["locator"]["page"] + 1:
            continue
        left, right = prev.get("text", "").rstrip(), nxt.get("text", "").lstrip()
        if not left or not right or re.search(r"[.!?。！？:：;；]$", left):
            continue
        if not re.match(r"^[a-z0-9α-ω(,;]", right):
            continue
        out.append({"from_block": prev["block_id"], "to_block": nxt["block_id"],
                    "from_page": prev["locator"]["page"], "to_page": nxt["locator"]["page"],
                    "basis": "adjacent body blocks; previous has no terminal punctuation and next starts lowercase/digit",
                    "status": "candidate_not_auto_merged"})
    return out
