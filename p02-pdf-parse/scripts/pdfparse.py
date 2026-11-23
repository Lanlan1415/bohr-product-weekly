"""pdf-parse CLI — read /input/case.json, parse PDF, write /app/output/result.json.

    python scripts/pdfparse.py --case /input/case.json --out /app/output
    python scripts/pdfparse.py --spec spec.json --out /tmp/out

Exit codes:
  0 parsed OK (clean or review)
  3 parse refused: structural issue but recovered
  4 parse refused: caller asked for something unsupported
  5 undetermined: unreadable PDF, encrypted, scanned, no backend, missing input
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import reader, reading_order, structure, superscript, tables_pdf, pipeline  # noqa: E402


def cmd_parse(args: argparse.Namespace) -> int:
    started = time.time()
    case_path = Path(args.case) if args.case else Path(args.spec)
    try:
        case = json.loads(case_path.read_text(encoding="utf-8-sig"))
    except (json.JSONDecodeError, UnicodeDecodeError, OSError) as exc:
        pipeline.refuse(args.out, {}, f"case_unreadable: {exc}")
        return 5
    if not isinstance(case, dict):
        pipeline.refuse(args.out, {}, "case_not_object")
        return 4

    pdf_path_str = (case.get("pdf_path") or case.get("pdf") or
                    case.get("source_pdf") or case.get("file"))
    if not pdf_path_str:
        pipeline.refuse(args.out, case,
                        "no_pdf_path: case must give pdf_path (or pdf/source_pdf/file)")
        return 4

    pdf_path = Path(pdf_path_str)
    if not pdf_path.exists():
        pipeline.refuse(args.out, case, f"pdf_missing: {pdf_path_str}")
        return 5

    try:
        read = reader.read(pdf_path)
    except reader.Refusal as exc:
        # Map reader refusal reason codes to structured refusal + recovery hints
        hints = {
            "scanned_only": ["Run OCR first (e.g. ocrmypdf or tesseract)",
                             "Confirm the PDF is actually scanned, not text-layer"],
            "encrypted": ["Provide an unlocked copy, or pass the password"],
            "encrypted_or_corrupted": ["Check PDF integrity with `qpdf --check`"],
            "all_backends_failed": ["Install PyMuPDF (pip install pymupdf) and retry"],
            "file_missing": ["Check the path is readable from this process"],
        }.get(exc.reason, [])
        pipeline.refuse(args.out, case, exc.reason, hints)
        return 5

    # ---- per-page: order + structure + formulas + tables -------------------
    all_blocks: list[dict] = []
    all_tables: list[dict] = []
    warnings: list[str] = []
    for page in read["pages"]:
        pw = page.get("width", 0)
        ordered = reading_order.order_page(page, pw)
        warnings.extend(f"p{page['page']}: {w}" for w in ordered["warnings"])
        marked = structure.identify_sections(ordered["blocks"], page["page"])
        superscript.mark_formulas(marked)
        all_blocks.extend(marked)
        tbl = tables_pdf.rebuild_tables(ordered["blocks"], page["page"])
        if tbl:
            all_tables.append(tbl)

    outline = structure.build_outline(all_blocks)
    kind_counts = superscript.count_by_kind(all_blocks)

    # ---- status -----------------------------------------------------------
    n_scanned = sum(1 for b in all_blocks if b.get("is_scanned"))
    if n_scanned > 0 and n_scanned == len(read["pages"]):
        # shouldn't happen (reader would have refused), but be honest
        pipeline.refuse(args.out, case, "scanned_only", ["Run OCR first"])
        return 5

    n_formula = kind_counts.get("formula", 0)
    if not outline:
        status = "review"
    elif warnings:
        status = "review"
    else:
        status = "clean"

    rr = pipeline.reading_result(outline, all_blocks, all_tables, n_formula)
    eb = pipeline.evidence_and_boundaries(all_blocks)
    prov = pipeline.provenance(read["sha256"], read["backend"],
                               str(pdf_path), read["page_count"],
                               time.time() - started)

    result = {
        "schema_version": "pdf-parse/v1",
        "status": status,
        "reading_result": rr,
        "evidence_and_boundaries": eb,
        "provenance": prov,
        "outline": outline,
        "tables": all_tables,
        "blocks": all_blocks,
        "warnings": warnings,
        "run_state": {"exit_meaning": "0 clean / 3 review / 4 refused / 5 undetermined",
                      "handoff": "broken blocks flagged in evidence_and_boundaries.locators"},
        "limits": [],
    }
    # accuracy band: pypdf can't see layouts; only pymupdf can column-restore
    if read["backend"] == "pdftotext":
        result["limits"].append("pdftopdf backend cannot restore column order; text is per-page only")
    if read["backend"] == "pypdf":
        result["limits"].append("pypdf yields flat text per page; columns/formulas/tables need pymupdf for best accuracy")

    result = pipeline.echo_contract(result, case, rr)
    pipeline.write(args.out, result)
    print(json.dumps({"status": status, "outline": len(outline),
                      "tables": len(all_tables), "blocks": len(all_blocks),
                      "formula": n_formula, "warnings": len(warnings),
                      "backend": read["backend"]}))
    return {"clean": 0, "review": 3}.get(status, 5)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="pdf-parse")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("parse", help="parse a PDF")
    p.add_argument("--case", default="", help="path to case.json")
    p.add_argument("--spec", default="", help="alias for --case")
    p.add_argument("--out", required=True, help="output directory")
    args = ap.parse_args(argv)
    if args.cmd == "parse":
        return cmd_parse(args)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
