"""PDF reader layer for pdf-parse.

Three backends, tried in order:

  1. PyMuPDF (`fitz`)  — preserves layout, fonts, page boxes
  2. pypdf             — pure-python fallback
  3. pdftotext         — poppler binary on PATH (form feeds preserved)

The reader always returns a uniform page dict:
  {"page": int, "width": float, "height": float,
   "blocks": [{"type": "text"|"table"|"image"|"formula",
               "bbox": [x0,y0,x1,y1],
               "text": str, "column": int|None, "order": int}],
   "is_scanned": bool}

If no backend can extract a usable text layer, raise Refusal with a reason
(scanned-only, encrypted, corrupted). Never silently fabricate text.
"""
from __future__ import annotations

import hashlib
import shutil
import subprocess
from pathlib import Path


class Refusal(Exception):
    def __init__(self, reason: str, message: str = ""):
        super().__init__(message or reason)
        self.reason = reason


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _has_text(pages: list[dict], min_chars: int = 80) -> bool:
    return sum(len(b.get("text", "") or "") for p in pages for b in p["blocks"]) >= min_chars


def _with_pymupdf(path: Path) -> list[dict]:
    try:
        import fitz  # PyMuPDF
    except ImportError:
        raise Refusal("backend_missing", "PyMuPDF not installed")
    try:
        doc = fitz.open(path)
    except Exception as exc:
        raise Refusal("encrypted_or_corrupted", str(exc)[:200])
    if doc.is_encrypted:
        raise Refusal("encrypted", "PDF is password-encrypted")
    pages: list[dict] = []
    for i, page in enumerate(doc):
        raw = page.get_text("dict")  # blocks with bbox + spans
        blocks: list[dict] = []
        for b in raw.get("blocks", []):
            if b.get("type") == 1:  # image
                blocks.append({"type": "image", "bbox": list(b["bbox"]), "text": "",
                               "column": None, "order": len(blocks)})
                continue
            spans = []
            for line in b.get("lines", []) or []:
                for span in line.get("spans", []) or []:
                    spans.append(span.get("text", ""))
            text = "".join(spans).strip()
            if not text:
                continue
            blocks.append({"type": "text", "bbox": list(b["bbox"]), "text": text,
                           "column": None, "order": len(blocks)})
        pages.append({"page": i + 1, "width": page.rect.width, "height": page.rect.height,
                      "blocks": blocks,
                      "is_scanned": not any(b["text"] for b in blocks)})
    doc.close()
    if not _has_text(pages):
        raise Refusal("scanned_only", "no extractable text layer on any page")
    return pages


def _with_pypdf(path: Path) -> list[dict]:
    try:
        import pypdf
    except ImportError:
        raise Refusal("backend_missing", "pypdf not installed")
    try:
        rd = pypdf.PdfReader(str(path))
    except Exception as exc:
        raise Refusal("encrypted_or_corrupted", str(exc)[:200])
    if rd.is_encrypted:
        raise Refusal("encrypted", "PDF is password-encrypted")
    pages: list[dict] = []
    for i, page in enumerate(rd.pages):
        try:
            text = page.extract_text() or ""
        except Exception as exc:
            raise Refusal("extraction_error", str(exc)[:200])
        blocks = []
        if text.strip():
            mb = page.mediabox
            blocks.append({"type": "text",
                           "bbox": [float(mb.left), float(mb.bottom),
                                    float(mb.right), float(mb.top)],
                           "text": text.strip(), "column": None, "order": 0})
        pages.append({"page": i + 1,
                      "width": float(page.mediabox.width),
                      "height": float(page.mediabox.height),
                      "blocks": blocks,
                      "is_scanned": not text.strip()})
    if not _has_text(pages):
        raise Refusal("scanned_only", "no extractable text layer on any page")
    return pages


def _with_pdftotext(path: Path) -> list[dict]:
    exe = shutil.which("pdftotext")
    if not exe:
        raise Refusal("backend_missing", "pdftotext not on PATH")
    try:
        out = subprocess.run([exe, "-layout", "-enc", "UTF-8", str(path), "-"],
                             capture_output=True, timeout=120)
        if out.returncode != 0:
            raise Refusal("pdftotext_failed", out.stderr.decode(errors="replace")[:200])
    except subprocess.TimeoutExpired:
        raise Refusal("pdftotext_timeout", "pdftotext exceeded 120s")
    text = out.stdout.decode("utf-8", errors="replace")
    if not text.strip():
        raise Refusal("scanned_only", "pdftotext returned no characters")
    pages: list[dict] = []
    for i, chunk in enumerate(text.split("\f")):
        blocks = []
        if chunk.strip():
            blocks.append({"type": "text", "bbox": [0, 0, 0, 0], "text": chunk.strip(),
                           "column": None, "order": 0})
        pages.append({"page": i + 1, "width": 0, "height": 0, "blocks": blocks,
                      "is_scanned": not chunk.strip()})
    return pages


def read(path: Path) -> dict:
    """Read a PDF with the best available backend; never silently fabricate."""
    path = Path(path)
    if not path.exists():
        raise Refusal("file_missing", str(path))
    sha = _sha256(path)
    errors: list[str] = []
    for backend_name, fn in (("pymupdf", _with_pymupdf),
                             ("pypdf", _with_pypdf),
                             ("pdftotext", _with_pdftotext)):
        try:
            pages = fn(path)
            return {"backend": backend_name, "sha256": sha,
                    "page_count": len(pages), "pages": pages}
        except Refusal as exc:
            errors.append(f"{backend_name}: {exc.reason}")
            continue
    raise Refusal("all_backends_failed", " | ".join(errors))
