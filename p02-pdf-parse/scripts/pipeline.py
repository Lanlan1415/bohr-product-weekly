"""Deterministic result shaping, contract completion and reusable PDF artifacts."""
from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
from typing import Any

BULKY = {"output_contract", "pages", "blocks", "text", "source_path", "outline", "tables", "formulas",
         "section_tree", "materials", "files", "pdf_path", "pdf", "source_pdf", "file"}


def contract_fields(contract: Any) -> tuple[list[str], list[str]]:
    warnings: list[str] = []
    if contract is None:
        return [], warnings
    if isinstance(contract, str):
        return [contract], warnings
    if isinstance(contract, dict):
        return [str(k) for k in contract], warnings
    if isinstance(contract, list):
        names = []
        for i, item in enumerate(contract):
            if isinstance(item, str):
                names.append(item)
            elif isinstance(item, dict):
                name = item.get("field", item.get("name", item.get("key")))
                if name is None:
                    warnings.append(f"output_contract entry {i} has no field/name/key")
                else:
                    names.append(str(name))
            else:
                warnings.append(f"output_contract entry {i} has unsupported type {type(item).__name__}")
        return list(dict.fromkeys(names)), warnings
    warnings.append(f"output_contract has unsupported type {type(contract).__name__}")
    return [], warnings


def echo_contract(result: dict[str, Any], case: dict[str, Any], derived: dict[str, Any] | None = None) -> dict[str, Any]:
    """Engine value > case-carried value > null + named limit, for every field."""
    if not isinstance(case, dict):
        return result
    derived = derived or {}
    result["case_id"] = case.get("case_id")
    limits = result.setdefault("limits", [])
    fields, warnings = contract_fields(case.get("output_contract"))
    limits.extend(w for w in warnings if w not in limits)
    if "output_contract" in case:
        result["output_contract"] = copy.deepcopy(case["output_contract"])
    result["output_contract_fields"] = fields
    for name in fields:
        if name in {"output_contract", "output_contract_fields", "case_id"}:
            continue
        if name in result:
            continue
        if name in derived and derived[name] is not None:
            result[name] = derived[name]
        elif name in case and name not in BULKY:
            result[name] = copy.deepcopy(case[name])
        else:
            result[name] = None
            limits.append(f"output_contract field '{name}' remains null: not derivable by pdf-parse")
            result.setdefault("findings", []).append({"rule": "pdf.contract_field_missing", "severity": "medium",
                                                       "field": name})
            if result.get("status") == "clean":
                result["status"] = "review"
    return result


def refuse(out_dir: str | Path, case: Any, reason: str, hints: list[str] | None = None):
    """A contract-preserving refusal with no traceback and no fabricated content."""
    result = {"schema_version": "pdf-parse/v2", "status": "undetermined", "reason": reason,
              "refusalRule": reason.split(":", 1)[0], "hints": hints or [], "engine": "pdf-parse/v2",
              "reading_result": None, "evidence_and_boundaries": None, "findings": [], "limits": []}
    if isinstance(case, dict):
        echo_contract(result, case)
    else:
        result["case_id"] = None
    write(out_dir, result)
    return result


def write(out_dir: str | Path, result: dict[str, Any]) -> None:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    (out / "result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def provenance(sha256: str, backend: str, source_name: str, page_count: int,
               backend_version: str = "unknown", backend_errors: list[str] | None = None) -> dict[str, Any]:
    return {"sha256": sha256, "backend": backend, "backend_version": backend_version,
            "source_name": source_name, "page_count": page_count, "engine_version": "pdf-parse/v2",
            "determinism": "No wall-clock or elapsed-time fields; byte replay is expected for the same input and backends.",
            "backend_errors_before_success": backend_errors or []}


def reading_result(outline: list[dict[str, Any]], blocks: list[dict[str, Any]], tables: list[dict[str, Any]],
                   formulas: list[dict[str, Any]], references: list[dict[str, Any]],
                   captions: list[dict[str, Any]], pages: list[dict[str, Any]],
                   metadata: dict[str, Any], sections: list[dict[str, Any]]) -> dict[str, Any]:
    kinds: dict[str, int] = {}
    for b in blocks:
        kinds[b.get("kind", "paragraph")] = kinds.get(b.get("kind", "paragraph"), 0) + 1
    scanned = [p["page"] for p in pages if p.get("is_scanned")]
    return {"document_metadata": metadata, "outline": outline, "sections": sections,
            "block_kinds": dict(sorted(kinds.items())),
            "text_blocks": sum(1 for b in blocks if b.get("type") == "text" and b.get("text")),
            "table_count": len(tables), "formula_count": len(formulas), "reference_count": len(references),
            "caption_count": len(captions), "figure_count": sum(1 for b in blocks if b.get("kind") == "figure"),
            "body_chars": sum(len(b.get("text", "")) for b in blocks if b.get("include_in_body")),
            "raw_text_chars": sum(len(p.get("raw_text", "")) for p in pages),
            "page_count": len(pages), "scanned_pages": scanned,
            "pages_with_text": [p["page"] for p in pages if p.get("text_char_count", 0) > 0]}


def evidence_and_boundaries(blocks: list[dict[str, Any]], tables: list[dict[str, Any]],
                            formulas: list[dict[str, Any]]) -> dict[str, Any]:
    locators = []
    for b in blocks:
        loc = b.get("locator", {})
        text = b.get("text", "") or ""
        quote = text[:240]
        locators.append({"page": loc.get("page"), "block": loc.get("block"), "order": loc.get("order"),
                         "column": loc.get("column"), "bbox": loc.get("bbox"), "block_id": b.get("block_id"),
                         "kind": b.get("kind"), "char_start": 0, "char_end": len(quote), "quote": quote,
                         "text_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest()})
    unverified = []
    for b in blocks:
        if b.get("kind") == "scanned_page":
            unverified.append({"block_id": b.get("block_id"), "page": b.get("locator", {}).get("page"),
                               "reason": "scanned page has no extracted text; OCR/render inspection required"})
    return {"locators": locators,
            "table_locators": [{"table_id": t["table_id"], **t["locator"]} for t in tables],
            "formula_locators": [{"formula_id": f["formula_id"], **f["locator"]} for f in formulas],
            "unverified": unverified,
            "note": "Every quote is the exact prefix of its extracted block at char_start:char_end; no paraphrase is used as a locator."}


def full_text(blocks: list[dict[str, Any]], pages: list[dict[str, Any]]) -> str:
    by_page: dict[int, list[dict[str, Any]]] = {p["page"]: [] for p in pages}
    for b in blocks:
        if b.get("include_in_body") and b.get("text"):
            by_page.setdefault(b["locator"]["page"], []).append(b)
    chunks = []
    for p in pages:
        chunks.append(f"===== PDF page {p['page']} =====\n")
        chunks.extend(b["text"].rstrip() + "\n" for b in by_page.get(p["page"], []))
    return "\n".join(chunks).rstrip() + "\n"


def document_markdown(result: dict[str, Any]) -> str:
    md = ["# Structured PDF parse", ""]
    md.append(f"- Case: `{result.get('case_id')}`")
    md.append(f"- Backend: `{result['provenance']['backend']}`")
    md.append(f"- Source SHA-256: `{result['provenance']['sha256']}`")
    md.append("")
    metadata = result.get("metadata", {})
    if metadata.get("title"):
        md.extend([f"# {metadata['title']}", ""])
    if metadata.get("author"):
        md.extend([metadata["author"], ""])
    for b in result.get("blocks", []):
        if not b.get("include_in_body") or not b.get("text"):
            continue
        if b.get("kind") == "heading":
            level = min(6, int(b.get("heading_level", 1)) + (1 if metadata.get("title") else 0))
            md.extend(["#" * level + " " + b["text"], ""])
        else:
            md.extend([b["text"], ""])
    for table in result.get("tables", []):
        md.extend([f"## {table.get('caption', table['table_id'])}", "", table.get("markdown", ""), ""])
    if result.get("references"):
        md.extend(["## Extracted references", ""])
        md.extend([f"- {r['text']}" for r in result["references"]])
        md.append("")
    return "\n".join(md).rstrip() + "\n"


def write_artifacts(out_dir: str | Path, result: dict[str, Any], pages: list[dict[str, Any]]) -> None:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    (out / "full_text.txt").write_text(full_text(result.get("blocks", []), pages), encoding="utf-8")
    (out / "document.md").write_text(document_markdown(result), encoding="utf-8")
    (out / "tables.json").write_text(json.dumps(result.get("tables", []), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    raw_pages = [{"page": p["page"], "raw_text": p.get("raw_text", ""), "text_char_count": p.get("text_char_count", 0),
                  "is_scanned": p.get("is_scanned", False), "width": p.get("width"), "height": p.get("height")}
                 for p in pages]
    (out / "source_pages.json").write_text(json.dumps(raw_pages, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    result["artifacts"] = [{"path": "full_text.txt", "kind": "ordered_body_text"},
                           {"path": "document.md", "kind": "structured_editable_markdown"},
                           {"path": "tables.json", "kind": "native_table_cells"},
                           {"path": "source_pages.json", "kind": "unmodified_backend_page_text"}]
