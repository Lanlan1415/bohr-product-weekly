"""Coordinate-based reading order with up to three columns and spanning bands.

Headers/footers are retained as auxiliary evidence but excluded from body text.
Cross-column title/abstract/equation bands close the preceding column segment;
within a segment each column is read top-to-bottom before moving right.  Ambiguous
layouts produce a named warning rather than a confidence claim.  Every block gets
stable source_block and reading-order locators.
"""
from __future__ import annotations

import re
from collections import Counter
from typing import Any


def _width(b: dict[str, Any]) -> float:
    return max(0.0, float(b["bbox"][2]) - float(b["bbox"][0]))


def _cx(b: dict[str, Any]) -> float:
    return (float(b["bbox"][0]) + float(b["bbox"][2])) / 2


def _norm(text: str) -> str:
    value = text.lower().strip()
    # Only explicit pagination is normalised. Replacing every number would turn
    # changing headings such as "1 Methods" / "2 Results" into a fake header.
    value = re.sub(r"\bpage\s+\d+(?:\s+of\s+\d+)?\b", "page#", value)
    if re.fullmatch(r"[-–—]?\s*\d+\s*[-–—]?", value):
        value = "#"
    return re.sub(r"\W+", "", value)


def mark_headers_footers(pages: list[dict[str, Any]]) -> None:
    """Mark repeated marginal text, and explicit page-number lines, in place."""
    occurrences: Counter[tuple[str, str]] = Counter()
    for page in pages:
        h = float(page.get("height", 0) or 0)
        if h <= 0:
            continue
        for b in page.get("blocks", []):
            if b.get("type") != "text":
                continue
            top = float(b["bbox"][3]) <= h * 0.12
            bottom = float(b["bbox"][1]) >= h * 0.88
            if top or bottom:
                occurrences[("header" if top else "footer", _norm(b.get("text", "")))] += 1
    for page in pages:
        h = float(page.get("height", 0) or 0)
        for b in page.get("blocks", []):
            if b.get("type") != "text":
                continue
            text = b.get("text", "").strip()
            top = h > 0 and float(b["bbox"][3]) <= h * 0.12
            bottom = h > 0 and float(b["bbox"][1]) >= h * 0.88
            role = "header" if top else "footer" if bottom else None
            repeated = bool(role and _norm(text) and occurrences[(role, _norm(text))] >= 2)
            page_number = bool(re.fullmatch(r"(?:page\s+)?\d+(?:\s+of\s+\d+)?|[-–—]?\s*\d+\s*[-–—]?", text, re.I))
            if repeated or (role and page_number):
                b["layout_role"] = role
                b["include_in_body"] = False


def _cluster_columns(blocks: list[dict[str, Any]], page_width: float) -> tuple[int, list[float]]:
    """Return 1..3 columns and split positions; conservative cluster sizes."""
    if len(blocks) < 4 or page_width <= 0:
        return 1, []
    xs = sorted(_cx(b) for b in blocks)
    gaps = sorted(((xs[i + 1] - xs[i], (xs[i] + xs[i + 1]) / 2) for i in range(len(xs) - 1)), reverse=True)
    best = []
    for count, threshold in ((3, 0.18), (2, 0.12)):
        if len(blocks) < count * 2:
            continue
        candidates = sorted(gaps[:count - 1], key=lambda x: x[1])
        if len(candidates) != count - 1 or any(g < page_width * threshold for g, _ in candidates):
            continue
        splits = [x[1] for x in candidates]
        groups = [[] for _ in range(count)]
        for b in blocks:
            idx = sum(_cx(b) >= split for split in splits)
            groups[idx].append(b)
        if all(len(g) >= 2 for g in groups):
            best = splits
            break
    return (len(best) + 1 if best else 1), best


def _column_sort(blocks: list[dict[str, Any]], splits: list[float]) -> list[dict[str, Any]]:
    count = len(splits) + 1
    groups: list[list[dict[str, Any]]] = [[] for _ in range(count)]
    for b in blocks:
        idx = sum(_cx(b) >= split for split in splits)
        b["column"] = idx
        groups[idx].append(b)
    out = []
    for group in groups:
        group.sort(key=lambda b: (round(float(b["bbox"][1]), 2), float(b["bbox"][0]), b.get("source_block", 0)))
        out.extend(group)
    return out


def order_page(page: dict[str, Any], page_width: float | None = None) -> dict[str, Any]:
    width = float(page_width if page_width is not None else page.get("width", 0) or 0)
    # Images are carriers, not text. Keep them in reading order too, linked later
    # to captions; completely empty scanned pages receive an explicit placeholder.
    blocks = [dict(b) for b in page.get("blocks", []) if b.get("type") in {"text", "image"}]
    if page.get("is_scanned"):
        blocks.append({"type": "text", "kind": "scanned_page", "text": "", "raw_text": "",
                       "bbox": [0, 0, width, float(page.get("height", 0) or 0)],
                       "source_block": len(blocks), "include_in_body": False, "is_scanned": True})
    if not blocks:
        return {"blocks": [], "columns": 0, "warnings": [], "column_ranges": []}
    warnings: list[dict[str, Any]] = []
    auxiliary = [b for b in blocks if b.get("layout_role") in {"header", "footer"}]
    content = [b for b in blocks if b not in auxiliary]
    for b in content:
        b.setdefault("include_in_body", b.get("type") == "text")
    for b in auxiliary:
        b["include_in_body"] = False

    if len(content) <= 1 or width <= 0:
        ordered = sorted(content, key=lambda b: (float(b["bbox"][1]), float(b["bbox"][0]), b.get("source_block", 0)))
        for b in ordered:
            b["column"] = 0
        n_cols, splits, ranges = 1, [], [{"column": 0, "method": "single-or-flat"}]
    else:
        metadata_title = re.sub(r"\W+", "", str((page.get("document_metadata") or {}).get("title", ""))).lower()
        def metadata_title_band(b):
            text = re.sub(r"\W+", "", b.get("text", "")).lower()
            return bool(page.get("page") == 1 and metadata_title and text == metadata_title)
        spanning = [b for b in content if (_width(b) >= 0.70 * width
                    and float(b["bbox"][0]) <= 0.28 * width and float(b["bbox"][2]) >= 0.72 * width)
                    or metadata_title_band(b)]
        regular = [b for b in content if b not in spanning]
        # Wide prose blocks are stable layout anchors. Math fragments, table cell
        # scraps and superscripts are assigned AFTER the column boundary is known;
        # allowing them to vote for the boundary hides otherwise clear columns.
        anchors = [b for b in regular if _width(b) >= 0.25 * width]
        if len(anchors) < 4:
            anchors = regular
        n_cols, splits = _cluster_columns(anchors, width)
        if n_cols == 1:
            ordered = sorted(content, key=lambda b: (round(float(b["bbox"][1]), 2), float(b["bbox"][0]), b.get("source_block", 0)))
            for b in ordered:
                b["column"] = 0
        else:
            ordered = []
            consumed: set[int] = set()
            bands = sorted(spanning, key=lambda b: (float(b["bbox"][1]), float(b["bbox"][0])))
            for band in bands:
                before = [b for b in regular if id(b) not in consumed and float(b["bbox"][1]) < float(band["bbox"][1]) - 1]
                for b in before:
                    consumed.add(id(b))
                ordered.extend(_column_sort(before, splits))
                band["column"] = None
                band["spanning"] = True
                ordered.append(band)
            tail = [b for b in regular if id(b) not in consumed]
            ordered.extend(_column_sort(tail, splits))
        ranges = []
        bounds = [0.0] + splits + [width]
        for i in range(n_cols):
            ranges.append({"column": i, "x0": round(bounds[i], 3), "x1": round(bounds[i + 1], 3),
                           "block_count": sum(1 for b in ordered if b.get("column") == i)})
        if n_cols >= 2 and any(b.get("type") == "text" and b.get("column") is None for b in ordered):
            # This is information, not an error: spanning blocks are intentional.
            pass
        side_by_side = False
        for i, left in enumerate(regular):
            for right in regular[i + 1:]:
                ly0, ly1 = float(left["bbox"][1]), float(left["bbox"][3])
                ry0, ry1 = float(right["bbox"][1]), float(right["bbox"][3])
                vertical = max(0.0, min(ly1, ry1) - max(ly0, ry0))
                overlap_ratio = vertical / max(1.0, min(ly1 - ly0, ry1 - ry0))
                horizontal_clear = float(left["bbox"][2]) < float(right["bbox"][0]) or float(right["bbox"][2]) < float(left["bbox"][0])
                if vertical > 3 and overlap_ratio > 0.45 and horizontal_clear:
                    side_by_side = True
                    break
            if side_by_side:
                break
        if n_cols == 1 and side_by_side and not page.get("tables"):
            warnings.append({"rule": "pdf.column_order_warning", "severity": "medium", "page": page.get("page"),
                             "message": "Vertically overlapping, horizontally disjoint text blocks could not be conservatively assigned to columns; source y/x order retained for review."})

    headers = sorted((b for b in auxiliary if b.get("layout_role") == "header"),
                     key=lambda b: (float(b["bbox"][1]), float(b["bbox"][0])))
    footers = sorted((b for b in auxiliary if b.get("layout_role") == "footer"),
                     key=lambda b: (float(b["bbox"][1]), float(b["bbox"][0])))
    final = headers + ordered + footers
    for i, b in enumerate(final):
        b["order"] = i
        b["page"] = page.get("page")
    return {"blocks": final, "columns": n_cols, "warnings": warnings, "column_ranges": ranges}
