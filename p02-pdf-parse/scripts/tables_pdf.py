"""Native table-cell normalisation, merged geometry and cautious continuations."""
from __future__ import annotations

import json
import re
from typing import Any


def _text(value: Any) -> str:
    return "" if value is None else str(value)


def _overlap(a0: float, a1: float, b0: float, b1: float) -> float:
    return max(0.0, min(a1, b1) - max(a0, b0))


def _merged_regions(table: dict[str, Any]) -> list[dict[str, Any]]:
    geometry = table.get("row_geometry", [])
    if not geometry:
        return []
    # Column centres come from every observed grid cell, not inferred text x positions.
    col_boxes: dict[int, list[list[float]]] = {}
    for row in geometry:
        for c, box in enumerate(row.get("cell_bboxes", [])):
            if box is not None:
                col_boxes.setdefault(c, []).append(box)
    col_centers = {c: (sum(b[0] + b[2] for b in boxes) / (2 * len(boxes)),
                       sum(b[0] for b in boxes) / len(boxes), sum(b[2] for b in boxes) / len(boxes))
                   for c, boxes in col_boxes.items()}
    regions = []
    for unique in table.get("unique_cell_bboxes", []):
        covered_rows = []
        for row in geometry:
            box = row["bbox"]
            cy = (box[1] + box[3]) / 2
            if unique[1] - 0.5 <= cy <= unique[3] + 0.5 and _overlap(unique[0], unique[2], box[0], box[2]) > 0:
                covered_rows.append(row["row"])
        covered_cols = []
        for c, (_, x0, x1) in col_centers.items():
            if _overlap(unique[0], unique[2], x0, x1) >= 0.45 * max(0.01, x1 - x0):
                covered_cols.append(c)
        if len(covered_rows) > 1 or len(covered_cols) > 1:
            r0, r1 = min(covered_rows), max(covered_rows)
            c0, c1 = min(covered_cols), max(covered_cols)
            regions.append({"region_id": f"{table['table_id']}-merge-{len(regions) + 1:02d}",
                            "bbox": unique, "row_start": r0, "row_end": r1, "col_start": c0, "col_end": c1,
                            "rowspan": len(covered_rows), "colspan": len(covered_cols),
                            "text": _text(table["rows"][r0][c0]) if r0 < len(table["rows"]) and c0 < len(table["rows"][r0]) else "",
                            "derivation": "native cell bbox covers multiple native row/column geometries"})
    return regions


def normalize_table(table: dict[str, Any]) -> dict[str, Any]:
    result = dict(table)
    result["rows"] = [[_text(c) if c is not None else None for c in row] for row in table.get("rows", [])]
    header_names = list((table.get("header") or {}).get("names") or [])
    result["columns"] = header_names if len(header_names) == table.get("col_count") else \
        [f"col_{i + 1}" for i in range(int(table.get("col_count", 0)))]
    regions = _merged_regions(result)
    result["merged_regions"] = regions
    top_left = {(r["row_start"], r["col_start"]): r for r in regions}
    covered = {}
    for region in regions:
        for r in range(region["row_start"], region["row_end"] + 1):
            for c in range(region["col_start"], region["col_end"] + 1):
                if (r, c) != (region["row_start"], region["col_start"]):
                    covered[(r, c)] = region["region_id"]
    cells = []
    for r, row in enumerate(result["rows"]):
        boxes = result.get("row_geometry", [])[r].get("cell_bboxes", []) if r < len(result.get("row_geometry", [])) else []
        for c, value in enumerate(row):
            box = boxes[c] if c < len(boxes) else None
            item = {"row": r, "column": c, "text": value, "bbox": box,
                    "rowspan": 1 if box is not None else None, "colspan": 1 if box is not None else None}
            if (r, c) in top_left:
                item["rowspan"] = top_left[(r, c)]["rowspan"]
                item["colspan"] = top_left[(r, c)]["colspan"]
                item["merged_region"] = top_left[(r, c)]["region_id"]
            if (r, c) in covered:
                item["covered_by"] = covered[(r, c)]
                item["rowspan"] = item["colspan"] = None
            cells.append(item)
    result["cells"] = cells
    result["markdown"] = to_markdown(result)
    result["cell_fidelity"] = "Text and None values are copied from PyMuPDF Table.extract; spans derive only from native cell geometry."
    # Geometry is retained via cells/merged_regions; these two bulky intermediate
    # fields need not be duplicated in result.json.
    result.pop("unique_cell_bboxes", None)
    result.pop("row_geometry", None)
    return result


def to_markdown(table: dict[str, Any]) -> str:
    rows = [[_text(c).replace("|", "\\|").replace("\n", "<br>") for c in row] for row in table.get("rows", [])]
    if not rows:
        return ""
    columns = table.get("columns") or [f"col_{i + 1}" for i in range(table.get("col_count", len(rows[0])))]
    header = [_text(c).replace("|", "\\|") for c in columns]
    # If native header is the first table row, do not duplicate it as a synthetic row.
    body = rows[1:] if (table.get("header") or {}).get("names") and not (table.get("header") or {}).get("external") else rows
    lines = ["| " + " | ".join(header) + " |", "| " + " | ".join(["---"] * len(header)) + " |"]
    lines.extend("| " + " | ".join(row + [""] * (len(header) - len(row))) + " |" for row in body)
    return "\n".join(lines)


def normalize_tables(tables: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [normalize_table(t) for t in tables]


def attach_captions(tables: list[dict[str, Any]], captions: list[dict[str, Any]]) -> None:
    for table in tables:
        page = table["locator"]["page"]
        box = table["locator"]["bbox"]
        candidates = [c for c in captions if c["kind"] == "table" and c["locator"]["page"] == page]
        if not candidates:
            continue
        def distance(caption):
            cb = caption["locator"]["bbox"]
            above = box[1] - cb[3]
            below = cb[1] - box[3]
            return (0 if above >= -2 else 1, abs(above) if above >= -2 else abs(below) + 1000)
        caption = min(candidates, key=distance)
        if distance(caption)[1] <= 350:
            table["caption"] = caption["text"]
            table["caption_id"] = caption["caption_id"]
            caption["linked_target"] = table["table_id"]


def merge_continuations(tables: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Merge only explicit continuations or an identical repeated header row."""
    if not tables:
        return []
    ordered = sorted(tables, key=lambda t: (t["locator"]["page"], t["locator"]["bbox"][1], t["table_id"]))
    merged: list[dict[str, Any]] = []
    for table in ordered:
        if not merged:
            merged.append(table)
            continue
        prev = merged[-1]
        same_shape = prev.get("col_count") == table.get("col_count")
        adjacent = table["locator"]["page"] == prev["locator"]["page"] + 1
        explicit = bool(re.search(r"\b(?:continued|continuation)\b|续表", table.get("caption", ""), re.I))
        repeated_header = bool(prev.get("rows") and table.get("rows") and prev["rows"][0] == table["rows"][0]
                               and any(_text(c).strip() for c in prev["rows"][0]))
        if same_shape and adjacent and (explicit or repeated_header):
            original_id = table["table_id"]
            start = 1 if repeated_header else 0
            additions = table["rows"][start:]
            prev["rows"].extend(additions)
            prev["row_count"] = len(prev["rows"])
            prev.setdefault("continuation", []).append({"table_id": original_id, "locator": table["locator"],
                                                         "reason": "explicit continued caption" if explicit else "identical repeated header",
                                                         "rows_appended": len(additions)})
            prev["locator"] = dict(prev["locator"])
            prev["locator"]["continued_pages"] = [x["table_id"] for x in prev["continuation"]]
            # Cell-level provenance for the continuation remains in a companion list.
            prev.setdefault("continuation_cells", []).extend(table.get("cells", []))
            prev["markdown"] = to_markdown(prev)
            continue
        merged.append(table)
    return merged


def tables_json(tables: list[dict[str, Any]]) -> str:
    return json.dumps(tables, ensure_ascii=False, indent=2) + "\n"
