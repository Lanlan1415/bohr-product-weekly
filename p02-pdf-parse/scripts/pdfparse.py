"""pdf-parse v2 — real scientific PDF parsing and Harbor result contract.

  python -I -X utf8 scripts/pdfparse.py parse --case /input/case.json --out /app/output

Exit codes: 0 clean, 3 usable review/partial, 4 caller error, 5 undetermined.
Every formal-case failure writes result.json without a traceback.  All original
output_contract fields and top-level case_id are preserved on success and refusal.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import pipeline, reader, reading_order, structure, superscript, tables_pdf  # noqa: E402

ALLOWED_SECTIONS = {None, "", "parse", "pdf_parse", "pdf-parse", "reading", "reading-01", "文献文档解析"}
DIRECT_KEYS = ("pdf_path", "pdf", "source_pdf", "file")


def _candidate_values(value: Any, key: str = "") -> list[str]:
    out: list[str] = []
    if isinstance(value, str):
        if not value.lower().startswith(("http://", "https://")) and (key in DIRECT_KEYS or value.lower().endswith(".pdf")):
            out.append(value)
    elif isinstance(value, list):
        for item in value:
            out.extend(_candidate_values(item, key))
    elif isinstance(value, dict):
        for k, item in value.items():
            if k in {"path", "file_path", "pdf_path", "pdf", "source_pdf", "file", "materials", "files", "attachments"}:
                out.extend(_candidate_values(item, k))
    return out


def locate_pdf(case: dict[str, Any], case_dir: Path) -> tuple[Path, list[str], list[str]]:
    declared: list[str] = []
    direct_seen = any(key in case for key in DIRECT_KEYS)
    for key in DIRECT_KEYS:
        if key in case:
            declared.extend(_candidate_values(case[key], key))
    if not declared and direct_seen:
        raise reader.Refusal("no_pdf_path", "declared pdf_path/pdf/source_pdf/file must contain a local path string")
    if not declared:
        for key in ("materials", "files", "attachments"):
            declared.extend(_candidate_values(case.get(key), key))
    auto_discovered = False
    auto_others: list[str] = []
    if not declared:
        candidates = sorted(case_dir.glob("*.pdf")) if case_dir.is_dir() else []
        input_dir = Path("/input")
        if not candidates and input_dir.is_dir():
            candidates = sorted(input_dir.glob("*.pdf"))
        if candidates:
            declared = [str(candidates[0])]
            auto_others = [str(p) for p in candidates[1:]]
            auto_discovered = True
    if not declared:
        raise reader.Refusal("no_pdf_path", "case must declare pdf_path/pdf/source_pdf/file or provide a PDF in its input directory")
    resolved = []
    for value in declared:
        path = Path(value)
        resolved.append(path if path.is_absolute() else case_dir / path)
    primary = resolved[0]
    if not primary.is_file():
        raise reader.Refusal("pdf_missing", f"declared PDF does not exist: {primary}")
    extras = auto_others + [str(p) for p in resolved[1:]]
    if auto_discovered:
        extras.append("primary path auto-discovered from the sole/alphabetically first PDF in the input directory")
    return primary, declared, extras


def _bool(value: Any, default: bool = True) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.lower() not in {"0", "false", "no", "off"}
    if value is None:
        return default
    return bool(value)


def _document_metadata(read: dict[str, Any], blocks: list[dict[str, Any]]) -> dict[str, Any]:
    metadata = dict(read.get("metadata") or {})
    # Backend keys are source metadata, not generated bibliographic facts.
    metadata = {k: v for k, v in metadata.items() if k.lower() not in {"pages", "encrypted", "format"}}
    title_block = next((b for b in blocks if b.get("kind") == "title"), None)
    if title_block and not metadata.get("title"):
        metadata["title"] = title_block["text"]
        metadata["title_source"] = {"block_id": title_block["block_id"], "basis": "largest-first-page-title-candidate"}
    authors = [b for b in blocks if b.get("kind") == "authors"]
    if authors and not metadata.get("author"):
        metadata["author"] = "\n".join(b["text"] for b in authors)
        metadata["author_source"] = "PDF byline block"
    affiliations = [b["text"] for b in blocks if b.get("kind") == "affiliation"]
    if affiliations:
        metadata["affiliations"] = affiliations
    full = "\n".join(b.get("text", "") for b in blocks[:30])
    doi = re.search(r"\b10\.\d{4,9}/[^\s]+", full, re.I)
    if doi and not metadata.get("doi"):
        metadata["doi"] = doi.group(0).rstrip(".,;")
        metadata["doi_basis"] = "DOI syntax found in extracted first-page/leading text; no remote resolution"
    metadata["metadata_policy"] = "PDF metadata and byline candidates are distinguished; authors_candidate is never promoted automatically."
    return metadata


def _link_figure_captions(blocks: list[dict[str, Any]], captions: list[dict[str, Any]]) -> None:
    for figure in [b for b in blocks if b.get("kind") == "figure"]:
        candidates = [c for c in captions if c["kind"] == "figure" and c["locator"]["page"] == figure["locator"]["page"]]
        if not candidates:
            continue
        box = figure["bbox"]
        def distance(caption):
            cb = caption["locator"]["bbox"]
            below = cb[1] - box[3]
            above = box[1] - cb[3]
            return (0 if below >= -2 else 1, abs(below) if below >= -2 else abs(above) + 1000)
        caption = min(candidates, key=distance)
        if distance(caption)[1] <= 400:
            figure["caption"] = caption["text"]
            figure["caption_id"] = caption["caption_id"]
            caption["linked_target"] = figure["block_id"]


def cmd_parse(args: argparse.Namespace) -> int:
    case: Any = {}
    case_path = Path(args.case or args.spec)
    try:
        try:
            case = json.loads(case_path.read_text(encoding="utf-8-sig"))
        except (json.JSONDecodeError, UnicodeDecodeError, OSError) as exc:
            pipeline.refuse(args.out, {}, f"case_unreadable: {exc}")
            return 5
        if not isinstance(case, dict):
            pipeline.refuse(args.out, {}, "case_not_object")
            return 4
        section = case.get("section")
        if section not in ALLOWED_SECTIONS:
            pipeline.refuse(args.out, case, f"unknown_section: {section}", ["Use section=parse/pdf_parse/reading-01 or omit it."])
            return 5
        pipeline.write(args.out, {"schema_version": "pdf-parse/v2", "status": "undetermined",
                                  "case_id": case.get("case_id"),
                                  "limits": ["PDF extraction is running; this early partial is replaced after completion."]})
        pdf_path, declared_paths, extra_paths = locate_pdf(case, case_path.resolve().parent)
        read = reader.read(pdf_path, native_tables=_bool(case.get("native_tables"), True))
        reading_order.mark_headers_footers(read["pages"])
        all_blocks, native, findings = [], [], list(read.get("findings", []))
        page_details = []
        for page in read["pages"]:
            page["document_metadata"] = read.get("metadata", {})
            ordered = reading_order.order_page(page)
            findings.extend(ordered["warnings"])
            all_blocks.extend(ordered["blocks"])
            native.extend(page.get("tables", []))
            page_details.append({"page": page["page"], "columns": ordered["columns"],
                                 "column_ranges": ordered["column_ranges"],
                                 "text_char_count": page.get("text_char_count", 0),
                                 "is_scanned": page.get("is_scanned", False)})
        if extra_paths:
            auto_only = len(extra_paths) == 1 and extra_paths[0].startswith("primary path auto-discovered")
            findings.append({"rule": "pdf.input_autodiscovery" if auto_only else "pdf.multiple_pdf_candidates",
                             "severity": "medium", "page": None,
                             "message": "The primary PDF was selected deterministically; other candidates/notes are listed. Only that primary was parsed.",
                             "candidates": extra_paths, "primary": str(pdf_path)})
        scanned = [p["page"] for p in read["pages"] if p.get("is_scanned")]
        if scanned:
            findings.append({"rule": "pdf.scanned_pages", "severity": "high", "page": None,
                             "message": f"Pages without a text layer were not OCR-read: {scanned}", "pages": scanned})

        page_heights = {p["page"]: p.get("height", 0) for p in read["pages"]}
        structure.identify_document(all_blocks, read.get("metadata", {}), page_heights)
        if len(read["pages"]) >= 2 and not any(b.get("kind") == "heading" for b in all_blocks):
            findings.append({"rule": "pdf.no_headings", "severity": "medium", "page": None,
                             "message": "No reliable section headings were detected in this multi-page PDF; body extraction remains available."})
        superscript.mark_formulas(all_blocks)
        outline = structure.build_outline(all_blocks)
        sections = structure.build_sections(all_blocks)
        captions = structure.extract_captions(all_blocks)
        formulas = superscript.extract_formulas(all_blocks)
        references = structure.extract_references(all_blocks)
        if any(r.get("review_required") for r in references):
            findings.append({"rule": "pdf.reference_segmentation_review", "severity": "medium", "page": None,
                             "message": "Unnumbered references were reconstructed using author/year boundaries; component locators are retained for manual verification."})
        continuations = structure.cross_page_continuations(all_blocks)
        tables = tables_pdf.normalize_tables(native)
        tables_pdf.attach_captions(tables, captions)
        tables = tables_pdf.merge_continuations(tables)
        _link_figure_captions(all_blocks, captions)
        metadata = _document_metadata(read, all_blocks)
        if read["backend"] in {"pypdf", "pdftotext"} and native:
            raise reader.Refusal("internal_error", "text-only fallback unexpectedly returned native tables")
        if not any(b.get("text") for b in all_blocks):
            raise reader.Refusal("scanned_only", "no extractable text survived page ordering")

        status = "review" if any(f.get("severity") in {"medium", "high"} for f in findings) else "clean"
        rr = pipeline.reading_result(outline, all_blocks, tables, formulas, references, captions,
                                     read["pages"], metadata, sections)
        eb = pipeline.evidence_and_boundaries(all_blocks, tables, formulas)
        limits = []
        if read["backend"] == "pdftotext":
            limits.append("Poppler text fallback: no block bboxes, font/script flags, native table cells or reliable multi-column restoration.")
        if read["backend"] == "pypdf":
            limits.append("pypdf text fallback: no line/span geometry or native table cells; reading order remains backend order.")
        if scanned:
            limits.append(f"Scanned pages {scanned} are explicit unverified gaps; run authorized OCR then re-run for complete text.")
        limits.append("Formula output is verbatim Unicode with source span/script evidence; latex=null and no semantics are inferred.")
        if not native:
            limits.append("No native table grid was detected/extracted; no rectangular table was fabricated from ordinary prose.")
        result = {
            "schema_version": "pdf-parse/v2", "status": status, "case_id": case.get("case_id"),
            "reading_result": rr, "evidence_and_boundaries": eb,
            "provenance": pipeline.provenance(read["sha256"], read["backend"], pdf_path.name,
                                               read["page_count"], read.get("backend_version", "unknown"),
                                               read.get("backend_errors", [])),
            "metadata": metadata, "source_toc": read.get("source_toc", []),
            "outline": outline, "outline_flat": structure.flatten_outline(outline), "sections": sections,
            "pages": page_details, "tables": tables, "blocks": all_blocks, "formulas": formulas,
            "captions": captions, "references": references, "cross_page_continuations": continuations,
            "findings": findings, "warnings": findings, "limits": limits,
            "run_state": {"exit_meaning": "0 clean / 3 review / 4 caller error / 5 undetermined",
                          "handoff": "Inspect findings, evidence_and_boundaries.unverified and source_pages.json; OCR scanned gaps before claiming completeness."},
            "change_records": [{"operation": "extract", "backend": read["backend"], "source_sha256": read["sha256"]},
                               {"operation": "reading_order", "pages": page_details},
                               {"operation": "structure", "outline_items": len(structure.flatten_outline(outline)),
                                "tables": len(tables), "formulas": len(formulas), "references": len(references)}],
        }
        derived = {"阅读/解析结果": rr, "证据与边界": eb, "运行状态": status,
                   "sources": [{"source_name": pdf_path.name, "sha256": read["sha256"], "backend": read["backend"]}],
                   "uncertainty": findings, "limitations": limits}
        result = pipeline.echo_contract(result, case, derived)
        status = result["status"]
        result["run_state"]["final_status"] = status
        pipeline.write_artifacts(args.out, result, read["pages"])
        pipeline.write(args.out, result)
        print(json.dumps({"status": status, "case_id": result.get("case_id"), "backend": read["backend"],
                          "pages": read["page_count"], "blocks": len(all_blocks), "outline": len(structure.flatten_outline(outline)),
                          "tables": len(tables), "formulas": len(formulas), "references": len(references),
                          "warnings": len(findings)}, ensure_ascii=False))
        return {"clean": 0, "review": 3}.get(status, 5)
    except reader.Refusal as exc:
        reason = exc.reason
        if reason.startswith("unknown_section"):
            code = 5
        elif reason in {"no_pdf_path"}:
            code = 4
        else:
            code = 5
        hints = {
            "scanned_only": ["Run authorized OCR (for example OCRmyPDF/Tesseract) and re-run; no text was invented."],
            "encrypted": ["Provide an authorized unlocked copy; password bypass is not attempted."],
            "encrypted_or_corrupted": ["Check PDF integrity and provide an uncorrupted file."],
            "pdf_missing": ["Check the declared path relative to case.json or /input."],
            "all_backends_failed": ["Install PyMuPDF>=1.23 and pypdf, or inspect the recorded backend errors."],
            "backend_missing": ["Install PyMuPDF>=1.23 for layout/table parsing."],
        }.get(reason, [])
        pipeline.refuse(args.out, case, reason, hints)
        return code
    except Exception as exc:
        pipeline.refuse(args.out, case, f"internal_error: {type(exc).__name__}: {str(exc)[:220]}",
                        ["Inspect the named stage; no parse result is claimed."])
        return 5


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="pdf-parse", description=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("parse", help="parse a real PDF into source-anchored structure")
    p.add_argument("--case", default="", help="path to case.json")
    p.add_argument("--spec", default="", help="alias for --case")
    p.add_argument("--out", required=True, help="output directory")
    args = ap.parse_args(argv)
    if args.cmd == "parse":
        if not (args.case or args.spec):
            pipeline.refuse(args.out, {}, "case_unreadable: --case/--spec is required")
            return 5
        return cmd_parse(args)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
