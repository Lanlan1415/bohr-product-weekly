"""Table-region detection and structure reconstruction for pdf-parse.

Two strategies, in order:

  1. Structured table detection — poppler/MuPDF sometimes marks a region as a
     table; if so, the reader already returned those blocks with type=table.
  2. Heuristic table reconstruction — sequences of text blocks that align into
     a grid by their x coordinates (≥3 distinct columns, ≥2 aligned rows).

Returns the table as JSON `{"columns": [...], "rows": [[...]], "locator": ...}`,
or null when no grid is found. Refuses to fabricate a rectangular table from
text that does not align.
"""
from __future__ import annotations


def _tolerance(blocks: list[dict]) -> float:
    widths = [abs(b["bbox"][2] - b["bbox"][0]) for b in blocks if b.get("bbox")]
    if not widths:
        return 5.0
    avg = sum(widths) / len(widths)
    return max(2.0, avg / 20)


def _column_centers(blocks: list[dict], tol: float) -> list[float]:
    xs = sorted({bucket for b in blocks for bucket in [round(b["bbox"][0] / tol) * tol]})
    if len(xs) < 3:
        return []
    merged: list[float] = [xs[0]]
    for x in xs[1:]:
        if x - merged[-1] > tol * 1.5:
            merged.append(x)
    return merged if len(merged) >= 3 else []


def _assign_column(b: dict, cols: list[float], tol: float) -> int:
    x = b["bbox"][0]
    best, best_d = -1, tol * 2
    for i, c in enumerate(cols):
        d = abs(x - c)
        if d < best_d:
            best_d, best = d, i
    return best if best_d <= tol * 2 else -1


def rebuild_tables(blocks: list[dict], page: int) -> dict | None:
    """Try to detect a grid in blocks; return the table dict or None."""
    text_blocks = [b for b in blocks if b.get("type") == "text" and b.get("bbox")]
    if len(text_blocks) < 6:
        return None
    tol = _tolerance(text_blocks)
    cols = _column_centers(text_blocks, tol)
    if len(cols) < 3:
        return None
    rows_by_y: dict[float, list[tuple[float, dict]]] = {}
    for b in text_blocks:
        key = round(b["bbox"][1] / (tol * 1.5)) * (tol * 1.5)
        rows_by_y.setdefault(key, []).append((b["bbox"][0], b))
    rows = sorted(rows_by_y.items(), key=lambda kv: kv[0])
    if len(rows) < 2:
        return None
    grid: list[list[str]] = []
    valid_rows = 0
    for y, items in rows:
        cells: list[str] = [""] * len(cols)
        filled = 0
        for x, b in sorted(items):
            ci = _assign_column(b, cols, tol)
            if ci >= 0:
                cells[ci] = b.get("text", "").strip()
                filled += 1
        if filled >= 2:
            valid_rows += 1
        grid.append(cells)
    if valid_rows < 2 or len(cols) < 3:
        return None
    header = [c if c else f"col_{i+1}" for i, c in enumerate(cols)]
    return {"columns": header, "rows": grid,
            "col_count": len(cols), "row_count": len(grid),
            "method": "x-grid", "tolerance": round(tol, 2),
            "locator": {"page": page, "bbox": [
                min(b["bbox"][0] for b in text_blocks),
                min(b["bbox"][1] for b in text_blocks),
                max(b["bbox"][2] for b in text_blocks),
                max(b["bbox"][3] for b in text_blocks)]}}
