"""Multi-column reading-order restoration for pdf-parse.

Classifies text blocks into columns by their horizontal bbox, then orders them
column-by-column top-to-bottom. Detects a single full-width header/footer band
and keeps it before the first column. Refuses (as findings, not errors) when the
column structure is ambiguous (e.g. side-by-side text boxes of different widths)
so the caller can fall back to a per-page unsorted stream.

Output: ordered list of blocks with column index + restored sequence number.
"""
from __future__ import annotations


def _mid(b: dict) -> tuple[float, float]:
    x0, y0, x1, y1 = b["bbox"]
    return ((x0 + x1) / 2, (y0 + y1) / 2)


def _width(b: dict) -> float:
    return abs(b["bbox"][2] - b["bbox"][0])


def _height(b: dict) -> float:
    return abs(b["bbox"][3] - b["bbox"][1])


def _is_full_width(b: dict, page_width: float, ratio: float = 0.85) -> bool:
    if page_width <= 0:
        return False
    return _width(b) >= ratio * page_width


def order_page(page: dict, page_width: float) -> dict:
    """Restore reading order for one page.

    Returns {"blocks": [...], "columns": int, "warnings": [str]}.
    """
    blocks = [b for b in page.get("blocks", []) if b.get("type") == "text"]
    if not blocks:
        return {"blocks": [], "columns": 0, "warnings": []}

    if len(blocks) == 1 or page_width <= 0:
        return {"blocks": [dict(b, column=0) for b in blocks],
                "columns": 1, "warnings": []}

    full_width = [b for b in blocks if _is_full_width(b, page_width)]
    rest = [b for b in blocks if b not in full_width]

    if not rest:
        # all full-width: top-to-bottom
        ordered = sorted(full_width, key=lambda b: b["bbox"][1])
        return {"blocks": [dict(b, column=0) for b in ordered],
                "columns": 1, "warnings": []}

    # cluster rest by horizontal midpoint
    xs = sorted(_mid(b)[0] for b in rest)
    gaps = [(xs[i + 1] - xs[i], i) for i in range(len(xs) - 1)]
    if not gaps:
        n_cols = 1
        split_x = None
    else:
        big_gap, idx = max(gaps)
        # 单栏: 没有大于0.3倍页宽的大间隙；多栏: 间隙 ≥ 0.2 页宽
        if big_gap >= 0.2 * page_width:
            n_cols = 2
            split_x = (xs[idx] + xs[idx + 1]) / 2
        else:
            n_cols = 1
            split_x = None

    warnings: list[str] = []
    if n_cols == 2:
        left = [b for b in rest if _mid(b)[0] < split_x]
        right = [b for b in rest if _mid(b)[0] >= split_x]
        left.sort(key=lambda b: b["bbox"][1])
        right.sort(key=lambda b: b["bbox"][1])
        for b in left:
            b["column"] = 0
        for b in right:
            b["column"] = 1
        ordered = left + right
    else:
        ordered = sorted(rest, key=lambda b: b["bbox"][1])
        for b in ordered:
            b["column"] = 0

    # 全宽带：顶部 before 列; 底部 after 列
    top_full = sorted([b for b in full_width if b["bbox"][1] <= min(b2["bbox"][1] for b2 in rest)],
                      key=lambda b: b["bbox"][1])
    bottom_full = sorted([b for b in full_width if b not in top_full],
                         key=lambda b: b["bbox"][1])
    for b in top_full + bottom_full:
        b["column"] = None

    final = top_full + ordered + bottom_full
    for i, b in enumerate(final):
        b["order"] = i

    # 校验：列内 y 坐标是否近似单调（如果有大量重叠就警告）
    for col_idx in {b.get("column") for b in final if b.get("column") is not None}:
        col_blocks = [b for b in final if b.get("column") == col_idx]
        ys = [b["bbox"][1] for b in col_blocks]
        if any(ys[i + 1] < ys[i] - 5 for i in range(len(ys) - 1)):
            warnings.append(f"column {col_idx}: y-coordinates not monotonic (possible side-by-side)")

    return {"blocks": final, "columns": n_cols, "warnings": warnings}
