"""Result shaping / contract echo / provenance for pdf-parse."""
from __future__ import annotations

import hashlib
import json
import time


_BULKY = ("output_contract", "pages", "blocks", "text", "source_path",
          "outline", "tables", "formulas", "section_tree")


def echo_contract(result: dict, case: dict, ws_summary: dict) -> dict:
    """case_id at top; output_contract fields: engine > spec > null+limits."""
    limits = result.setdefault("limits", [])
    cid = case.get("case_id") if isinstance(case, dict) else None
    if cid is not None:
        result["case_id"] = cid
    for key in (case.get("output_contract") or []):
        if key in result:
            continue
        if key in ws_summary and key not in _BULKY:
            result[key] = ws_summary[key]
        elif isinstance(case, dict) and key in case and key not in _BULKY:
            result[key] = case[key]
        else:
            result[key] = None
            limits.append(f"output_contract field '{key}' was not derivable by pdf-parse")
    return result


def refuse(out_dir: str, case: dict, reason: str, hints: list[str] | None = None):
    """A recorded refusal: result.json with status undetermined, exit 5."""
    result = {
        "status": "undetermined",
        "reason": reason,
        "refusalRule": "pdf.refused",
        "source": case.get("case_id") if isinstance(case, dict) else "",
        "hints": hints or [],
        "engine": "pdf-parse/v1",
    }
    if isinstance(case, dict):
        cid = case.get("case_id")
        if cid is not None:
            result["case_id"] = cid
        for key in (case.get("output_contract") or []):
            if key not in result and not (key in case and key not in _BULKY):
                result[key] = None
    write(out_dir, result)
    return result


def write(out_dir: str, result: dict) -> None:
    from pathlib import Path
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    (out / "result.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")


def provenance(sha256: str, backend: str, source_path: str, page_count: int,
               elapsed_s: float) -> dict:
    return {"sha256": sha256, "backend": backend, "source_path": source_path,
            "page_count": page_count, "elapsed_s": round(elapsed_s, 2),
            "engine_version": "pdf-parse/v1",
            "utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}


def reading_result(outline, blocks, tables, formulas_count: int) -> dict:
    """Map rubric fields: 阅读/解析结果 = structured document with locators."""
    return {"outline": outline,
            "block_kinds": {k: sum(1 for b in blocks if b.get("kind") == k)
                            for k in {b.get("kind", "paragraph") for b in blocks}},
            "text_blocks": sum(1 for b in blocks if b.get("kind") in ("paragraph", "heading")),
            "table_count": len(tables),
            "formula_count": formulas_count,
            "body_chars": sum(len(b.get("text", "")) for b in blocks),
            "scanned_pages": sum(1 for b in blocks if b.get("is_scanned"))}


def evidence_and_boundaries(blocks: list[dict]) -> dict:
    """Map rubric fields: 证据与边界 = per-block locator + unverifable items list."""
    locators = []
    for b in blocks:
        loc = b.get("locator", {})
        locators.append({"page": loc.get("page"), "block": loc.get("block"),
                         "column": loc.get("column"), "kind": b.get("kind"),
                         "quote": (b.get("text", "") or "")[:80]})
    unverified = [b["text"][:80] for b in blocks
                  if b.get("is_scanned") or b.get("warnings")]
    return {"locators": locators, "unverified": unverified,
            "note": "paraphrase cannot anchor — anchors are exact substrings of source text"}
