"""Real PDF extraction backends with loss-aware, page-anchored records.

Preferred PyMuPDF keeps blocks -> lines -> spans, font metrics, Unicode text,
images, document metadata, outlines and native table cells.  pypdf and Poppler
are explicit text-only fallbacks, never represented as layout-equivalent.

A page with any meaningful extracted characters is retained (there is no arbitrary
80-character threshold).  Scanned/encrypted inputs produce named refusals; mixed
scanned pages remain visible as unprocessed placeholders.  No OCR or scientific
content is fabricated here.
"""
from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import warnings
from pathlib import Path
from typing import Any


class Refusal(Exception):
    def __init__(self, reason: str, message: str = ""):
        super().__init__(message or reason)
        self.reason = reason
        self.message = message or reason


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _bbox(value: Any) -> list[float]:
    return [round(float(v), 3) for v in value]


def _has_text(pages: list[dict[str, Any]]) -> bool:
    return any((b.get("text") or "").strip() for p in pages for b in p.get("blocks", []))


def _import_pymupdf():
    try:
        import pymupdf
        return pymupdf
    except ImportError:
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", FutureWarning)
                import fitz
            return fitz
        except ImportError as exc:
            raise Refusal("backend_missing", "PyMuPDF not installed") from exc


def _native_tables(page: Any, page_number: int) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    tables: list[dict[str, Any]] = []
    findings: list[dict[str, Any]] = []
    if not hasattr(page, "find_tables"):
        findings.append({"rule": "pdf.table_backend_unavailable", "severity": "medium", "page": page_number,
                         "message": "PyMuPDF Page.find_tables is unavailable (requires >=1.23); no table grid was invented."})
        return tables, findings
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            finder = page.find_tables(strategy="lines")
    except Exception as exc:
        findings.append({"rule": "pdf.native_table_error", "severity": "medium", "page": page_number,
                         "message": f"native table detection failed: {type(exc).__name__}: {str(exc)[:180]}"})
        return tables, findings
    for i, table in enumerate(getattr(finder, "tables", []) or []):
        try:
            matrix = table.extract()
            rows = []
            for r, row in enumerate(getattr(table, "rows", []) or []):
                cell_boxes = [_bbox(c) if c is not None else None for c in row.cells]
                rows.append({"row": r, "bbox": _bbox(row.bbox), "cell_bboxes": cell_boxes})
            unique_cells = []
            seen = set()
            for cell in getattr(table, "cells", []) or []:
                if cell is None:
                    continue
                box = _bbox(cell)
                key = tuple(box)
                if key not in seen:
                    seen.add(key)
                    unique_cells.append(box)
            header = getattr(table, "header", None)
            tables.append({
                "table_id": f"p{page_number:04d}-table-{i + 1:02d}", "method": "pymupdf-find_tables-lines",
                "locator": {"page": page_number, "bbox": _bbox(table.bbox), "table_index": i},
                "row_count": int(table.row_count), "col_count": int(table.col_count),
                "rows": matrix, "row_geometry": rows, "unique_cell_bboxes": unique_cells,
                "header": {"names": list(getattr(header, "names", []) or []),
                           "external": bool(getattr(header, "external", False)),
                           "bbox": _bbox(header.bbox) if header is not None and getattr(header, "bbox", None) is not None else None},
            })
        except Exception as exc:
            findings.append({"rule": "pdf.native_table_error", "severity": "medium", "page": page_number,
                             "message": f"table {i + 1} could not be copied from its page: {type(exc).__name__}: {str(exc)[:160]}"})
    return tables, findings


def _segment_block(template: dict[str, Any], lines: list[dict[str, Any]]) -> dict[str, Any]:
    item = {k: v for k, v in template.items() if k not in {"lines", "bbox", "text", "raw_text", "source_block", "order",
                                                            "font_size_max", "font_size_min", "font_size_median", "fonts", "flags"}}
    copied_lines = []
    for i, line in enumerate(lines):
        copied = dict(line)
        copied["line"] = i
        copied_lines.append(copied)
    spans = [s for line in copied_lines for s in line.get("spans", [])]
    item.update({"type": "text", "lines": copied_lines,
                 "text": "\n".join(line["text"] for line in copied_lines).strip(),
                 "raw_text": "\n".join(line.get("raw_text", line["text"]) for line in copied_lines).strip(),
                 "bbox": [min(line["bbox"][0] for line in copied_lines), min(line["bbox"][1] for line in copied_lines),
                          max(line["bbox"][2] for line in copied_lines), max(line["bbox"][3] for line in copied_lines)],
                 "pdf_block": template.get("source_block", template.get("pdf_block", 0))})
    sizes = [s["size"] for s in spans if s.get("text", "").strip()]
    item.update({"font_size_max": max(sizes) if sizes else 0, "font_size_min": min(sizes) if sizes else 0,
                 "font_size_median": sorted(sizes)[len(sizes) // 2] if sizes else 0,
                 "fonts": sorted({s["font"] for s in spans if s.get("font")}),
                 "flags": sorted({s["flags"] for s in spans})})
    return item


def _expand_layout_block(block: dict[str, Any]) -> list[dict[str, Any]]:
    """Split MuPDF blocks that physically combine columns.

    MuPDF may co-locate two independently inserted headings in one block/line.
    Line gaps and abrupt x-origin reversals are physical evidence for a split;
    linguistic text is never changed. Ordinary wrapped paragraph lines remain in
    one block and keep their original newline boundaries.
    """
    physical_lines = []
    for line in block.get("lines", []) or []:
        spans = line.get("spans", []) or []
        if len(spans) < 2:
            physical_lines.append(line)
            continue
        groups, current = [], []
        for span in spans:
            if current:
                previous = current[-1]
                gap = float(span["bbox"][0]) - float(previous["bbox"][2])
                if gap > max(60.0, float(previous.get("size", 0)) * 6):
                    groups.append(current)
                    current = []
            current.append(span)
        if current:
            groups.append(current)
        for group in groups:
            text = "".join(s.get("text", "") for s in group)
            physical_lines.append({"line": 0, "text": text, "raw_text": text, "spans": group,
                                   "bbox": [min(s["bbox"][0] for s in group), min(s["bbox"][1] for s in group),
                                            max(s["bbox"][2] for s in group), max(s["bbox"][3] for s in group)],
                                   "dir": line.get("dir", [1, 0])})
    if len(physical_lines) <= 1:
        return [_segment_block(block, physical_lines)] if physical_lines else []
    segments, current = [], []
    for line in physical_lines:
        if current:
            prev = current[-1]
            x_shift = abs(float(line["bbox"][0]) - float(prev["bbox"][0]))
            y_reversal = float(line["bbox"][1]) < float(prev["bbox"][1]) - 2
            disjoint_same_y = abs(float(line["bbox"][1]) - float(prev["bbox"][1])) < 2 and \
                (float(line["bbox"][0]) > float(prev["bbox"][2]) + 40 or float(prev["bbox"][0]) > float(line["bbox"][2]) + 40)
            if x_shift > 80 or y_reversal or disjoint_same_y:
                segments.append(current)
                current = []
        current.append(line)
    if current:
        segments.append(current)
    return [_segment_block(block, segment) for segment in segments]


def _with_pymupdf(path: Path, native_tables: bool = True) -> dict[str, Any]:
    fitz = _import_pymupdf()
    try:
        doc = fitz.open(str(path))
    except Exception as exc:
        raise Refusal("encrypted_or_corrupted", f"PyMuPDF cannot open PDF: {str(exc)[:240]}") from exc
    try:
        if bool(getattr(doc, "needs_pass", False)) or bool(getattr(doc, "is_encrypted", False)):
            raise Refusal("encrypted", "PDF requires a password; supply an authorized unlocked copy")
        pages: list[dict[str, Any]] = []
        findings: list[dict[str, Any]] = []
        for i, page in enumerate(doc):
            raw = page.get_text("dict", sort=False)
            blocks: list[dict[str, Any]] = []
            for source_index, b in enumerate(raw.get("blocks", []) or []):
                box = _bbox(b.get("bbox", (0, 0, 0, 0)))
                if b.get("type") == 1:
                    blocks.append({"type": "image", "bbox": box, "text": "", "raw_text": "",
                                   "source_block": source_index, "column": None, "order": source_index,
                                   "image": {"width": b.get("width"), "height": b.get("height"),
                                             "ext": b.get("ext"), "xref": b.get("xref", 0)}})
                    continue
                if b.get("type") != 0:
                    continue
                lines, spans_all = [], []
                for line_index, line in enumerate(b.get("lines", []) or []):
                    spans = []
                    for span in line.get("spans", []) or []:
                        item = {"text": span.get("text", ""), "bbox": _bbox(span.get("bbox", (0, 0, 0, 0))),
                                "size": round(float(span.get("size", 0)), 3), "font": span.get("font", ""),
                                "flags": int(span.get("flags", 0)), "color": int(span.get("color", 0)),
                                "origin": _bbox(span.get("origin", (0, 0))) if span.get("origin") else None}
                        spans.append(item)
                        spans_all.append(item)
                    line_text = "".join(s["text"] for s in spans)
                    if line_text or spans:
                        lines.append({"line": line_index, "bbox": _bbox(line.get("bbox", (0, 0, 0, 0))),
                                      "text": line_text, "raw_text": line_text, "spans": spans,
                                      "dir": list(line.get("dir", (1, 0)))})
                text = "\n".join(line["text"] for line in lines).strip()
                if not text:
                    continue
                sizes = [s["size"] for s in spans_all if s["text"].strip()]
                blocks.append({"type": "text", "bbox": box, "text": text, "raw_text": text,
                               "source_block": source_index, "column": None, "order": source_index,
                               "lines": lines,
                               "font_size_max": max(sizes) if sizes else 0,
                               "font_size_min": min(sizes) if sizes else 0,
                               "font_size_median": sorted(sizes)[len(sizes) // 2] if sizes else 0,
                               "fonts": sorted({s["font"] for s in spans_all if s["font"]}),
                               "flags": sorted({s["flags"] for s in spans_all})})
            expanded = []
            for original in blocks:
                pieces = _expand_layout_block(original) if original.get("type") == "text" else [original]
                for piece in pieces:
                    piece["source_block"] = len(expanded)
                    piece["order"] = len(expanded)
                    expanded.append(piece)
            blocks = expanded
            if any(ord(ch) == 0xFFFD for b in blocks for ch in b.get("text", "")):
                findings.append({"rule": "pdf.text_encoding_warning", "severity": "medium", "page": i + 1,
                                 "message": "U+FFFD replacement characters occur in the text layer; original glyphs may be unrecoverable."})
            text_count = sum(len(b.get("text", "")) for b in blocks)
            has_image = any(b.get("type") == "image" for b in blocks)
            tables, table_findings = _native_tables(page, i + 1) if native_tables else ([], [])
            findings.extend(table_findings)
            pages.append({"page": i + 1, "width": float(page.rect.width), "height": float(page.rect.height),
                          "rotation": int(page.rotation), "blocks": blocks, "tables": tables,
                          "raw_text": page.get_text("text", sort=False),
                          "text_char_count": text_count, "image_count": sum(1 for b in blocks if b.get("type") == "image"),
                          "is_scanned": text_count == 0 and has_image})
        metadata = {str(k): str(v) for k, v in (doc.metadata or {}).items() if v not in (None, "")}
        toc = []
        try:
            toc = [{"level": int(x[0]), "title": str(x[1]), "page": int(x[2])} for x in doc.get_toc(simple=True)]
        except Exception:
            toc = []
        if not _has_text(pages):
            raise Refusal("scanned_only", "no extractable text layer on any page; OCR is required before appraisal")
        return {"pages": pages, "metadata": metadata, "source_toc": toc, "findings": findings,
                "backend_version": str(getattr(fitz, "VersionBind", "unknown"))}
    except Refusal:
        raise
    except Exception as exc:
        raise Refusal("extraction_error", f"PyMuPDF extraction failed: {type(exc).__name__}: {str(exc)[:220]}") from exc
    finally:
        doc.close()


def _with_pypdf(path: Path) -> dict[str, Any]:
    try:
        import pypdf
    except ImportError as exc:
        raise Refusal("backend_missing", "pypdf not installed") from exc
    try:
        rd = pypdf.PdfReader(str(path))
    except Exception as exc:
        raise Refusal("encrypted_or_corrupted", f"pypdf cannot open PDF: {str(exc)[:220]}") from exc
    if rd.is_encrypted:
        raise Refusal("encrypted", "PDF is password-encrypted")
    pages, findings = [], []
    for i, page in enumerate(rd.pages):
        try:
            text = page.extract_text() or ""
        except Exception as exc:
            text = ""
            findings.append({"rule": "pdf.page_extraction_error", "severity": "medium", "page": i + 1,
                             "message": f"pypdf failed on this page: {type(exc).__name__}: {str(exc)[:160]}"})
        blocks = []
        if text.strip():
            mb = page.mediabox
            blocks.append({"type": "text", "bbox": _bbox((mb.left, mb.bottom, mb.right, mb.top)),
                           "text": text.strip(), "raw_text": text.strip(), "source_block": 0,
                           "column": None, "order": 0, "lines": [], "font_size_max": 0,
                           "font_size_min": 0, "font_size_median": 0, "fonts": [], "flags": []})
        pages.append({"page": i + 1, "width": float(page.mediabox.width), "height": float(page.mediabox.height),
                      "rotation": int(page.get("/Rotate", 0) or 0), "blocks": blocks, "tables": [],
                      "raw_text": text, "text_char_count": len(text.strip()), "image_count": 0,
                      "is_scanned": not text.strip()})
    if not _has_text(pages):
        raise Refusal("scanned_only", "pypdf found no usable text layer")
    md_raw = rd.metadata or {}
    metadata = {str(k).lstrip("/").lower(): str(v) for k, v in md_raw.items() if v not in (None, "")}
    findings.append({"rule": "pdf.layout_fallback", "severity": "medium", "page": None,
                     "message": "pypdf supplied text only; line/span coordinates, native tables and reliable column restoration are unavailable."})
    return {"pages": pages, "metadata": metadata, "source_toc": [], "findings": findings,
            "backend_version": str(getattr(pypdf, "__version__", "unknown"))}


def _pdfinfo(exe: str, path: Path) -> dict[str, str]:
    candidate = Path(exe).with_name("pdfinfo.exe" if Path(exe).suffix.lower() == ".exe" else "pdfinfo")
    if not candidate.exists():
        candidate = shutil.which("pdfinfo") or ""
    if not candidate:
        return {}
    try:
        out = subprocess.run([str(candidate), str(path)], capture_output=True, timeout=30)
        if out.returncode != 0:
            return {}
        metadata = {}
        for line in out.stdout.decode("utf-8", errors="replace").splitlines():
            if ":" in line:
                key, value = line.split(":", 1)
                metadata[key.strip().lower()] = value.strip()
        return metadata
    except (OSError, subprocess.TimeoutExpired):
        return {}


def _with_pdftotext(path: Path) -> dict[str, Any]:
    exe = shutil.which("pdftotext")
    if not exe:
        raise Refusal("backend_missing", "pdftotext not on PATH")
    try:
        out = subprocess.run([exe, "-layout", "-enc", "UTF-8", str(path), "-"],
                             capture_output=True, timeout=120)
    except subprocess.TimeoutExpired as exc:
        raise Refusal("pdftotext_timeout", "pdftotext exceeded 120s") from exc
    except OSError as exc:
        raise Refusal("pdftotext_failed", str(exc)) from exc
    if out.returncode != 0:
        message = out.stderr.decode(errors="replace")[:240]
        if "password" in message.lower():
            raise Refusal("encrypted", message)
        raise Refusal("pdftotext_failed", message)
    text = out.stdout.decode("utf-8", errors="strict")
    chunks = text.split("\f")
    while chunks and not chunks[-1].strip():
        chunks.pop()
    if not any(chunk.strip() for chunk in chunks):
        raise Refusal("scanned_only", "pdftotext returned no characters")
    pages = []
    for i, chunk in enumerate(chunks):
        value = chunk.strip()
        blocks = []
        if value:
            blocks.append({"type": "text", "bbox": [0, 0, 0, 0], "text": value, "raw_text": value,
                           "source_block": 0, "column": None, "order": 0, "lines": [],
                           "font_size_max": 0, "font_size_min": 0, "font_size_median": 0,
                           "fonts": [], "flags": []})
        pages.append({"page": i + 1, "width": 0, "height": 0, "rotation": 0, "blocks": blocks,
                      "tables": [], "raw_text": chunk, "text_char_count": len(value),
                      "image_count": 0, "is_scanned": not value})
    return {"pages": pages, "metadata": _pdfinfo(exe, path), "source_toc": [],
            "findings": [{"rule": "pdf.layout_fallback", "severity": "medium", "page": None,
                          "message": "pdftotext -layout supplied text and page breaks only; no bbox-level columns/tables/claims are inferred."}],
            "backend_version": "poppler-pdftotext"}


def read(path: Path, native_tables: bool = True) -> dict[str, Any]:
    """Read with the best available backend and preserve all degradation notes."""
    path = Path(path)
    if not path.is_file():
        raise Refusal("file_missing", str(path))
    if path.stat().st_size > 1024 ** 3:
        raise Refusal("resource_limit", "PDF exceeds the declared 1 GiB safety limit")
    sha = _sha256(path)
    errors: list[str] = []
    reasons: list[str] = []
    for backend_name, fn in (("pymupdf", lambda: _with_pymupdf(path, native_tables)),
                             ("pypdf", lambda: _with_pypdf(path)),
                             ("pdftotext", lambda: _with_pdftotext(path))):
        try:
            payload = fn()
            return {"backend": backend_name, "sha256": sha, "page_count": len(payload["pages"]),
                    "pages": payload["pages"], "metadata": payload.get("metadata", {}),
                    "source_toc": payload.get("source_toc", []), "findings": payload.get("findings", []),
                    "backend_version": payload.get("backend_version", "unknown"),
                    "backend_errors": errors}
        except Refusal as exc:
            errors.append(f"{backend_name}: {exc.reason}: {exc.message[:180]}")
            reasons.append(exc.reason)
            continue
    # Preserve the actionable cause instead of hiding scanned/encrypted inputs
    # behind a generic all-backends failure.
    if "encrypted" in reasons:
        raise Refusal("encrypted", " | ".join(errors))
    if reasons and all(r in {"scanned_only", "backend_missing"} for r in reasons) and "scanned_only" in reasons:
        raise Refusal("scanned_only", " | ".join(errors))
    raise Refusal("all_backends_failed", " | ".join(errors))
