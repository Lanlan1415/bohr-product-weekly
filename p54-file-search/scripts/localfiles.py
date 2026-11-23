"""Build a searchable corpus from real files with explicit extraction coverage."""
from __future__ import annotations

import csv
import hashlib
import json
import os
import re
import shutil
import subprocess
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

TEXT_EXTS = {".txt", ".md", ".csv", ".tsv", ".json", ".jsonl", ".xml", ".yaml",
             ".yml", ".ris", ".bib", ".tex", ".log", ".py"}


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _xml_text(raw: bytes) -> str:
    root = ET.fromstring(raw)
    vals = []
    for el in root.iter():
        if el.tag.rsplit("}", 1)[-1] in {"t", "v"} and el.text:
            vals.append(el.text)
    return " ".join(vals)


def _ooxml(path: Path) -> tuple[str, dict, str]:
    meta: dict = {}
    texts: list[str] = []
    with zipfile.ZipFile(path) as zf:
        names = set(zf.namelist())
        if "docProps/core.xml" in names:
            root = ET.fromstring(zf.read("docProps/core.xml"))
            for el in root.iter():
                key, value = el.tag.rsplit("}", 1)[-1], (el.text or "").strip()
                if value and key in {"title", "creator", "subject"}:
                    meta[{"creator": "author"}.get(key, key)] = value
        suffix = path.suffix.lower()
        if suffix == ".docx":
            targets = ["word/document.xml"] if "word/document.xml" in names else []
            separator = "\n"
        elif suffix == ".pptx":
            targets = sorted((n for n in names if re.fullmatch(r"ppt/slides/slide\d+\.xml", n)),
                             key=lambda n: int(re.search(r"\d+", Path(n).stem).group()))
            separator = "\f"  # each physical slide is a locatable page
        else:
            targets = sorted(n for n in names if n == "xl/sharedStrings.xml" or
                             re.fullmatch(r"xl/worksheets/sheet\d+\.xml", n))
            separator = "\f"
        for name in targets:
            value = _xml_text(zf.read(name))
            if value.strip():
                texts.append(value)
    return separator.join(texts), meta, "ooxml-xml"


def _pdf(path: Path) -> tuple[str, dict, str]:
    errors = []
    try:
        import fitz  # type: ignore
        try:
            with fitz.open(path) as doc:
                if doc.is_encrypted:
                    raise ValueError("encrypted PDF")
                text = "\f".join(page.get_text("text") for page in doc)
                raw = doc.metadata or {}
            if text.strip():
                return text, {k: str(raw[k]) for k in ("title", "author") if raw.get(k)}, "pymupdf"
            errors.append("pymupdf:no_text_layer")
        except Exception as exc:
            errors.append("pymupdf:" + str(exc)[:120])
    except ImportError:
        errors.append("pymupdf:unavailable")
    try:
        import pypdf  # type: ignore
        try:
            rd = pypdf.PdfReader(str(path))
            if rd.is_encrypted:
                raise ValueError("encrypted PDF")
            text = "\f".join((p.extract_text() or "") for p in rd.pages)
            if text.strip():
                md = rd.metadata or {}
                meta = {}
                if md.get("/Title"):
                    meta["title"] = str(md["/Title"])
                if md.get("/Author"):
                    meta["author"] = str(md["/Author"])
                return text, meta, "pypdf"
            errors.append("pypdf:no_text_layer")
        except Exception as exc:
            errors.append("pypdf:" + str(exc)[:120])
    except ImportError:
        errors.append("pypdf:unavailable")
    exe = shutil.which("pdftotext")
    if exe:
        try:
            proc = subprocess.run([exe, "-layout", "-enc", "UTF-8", str(path), "-"],
                                  capture_output=True, timeout=90)
            text = proc.stdout.decode("utf-8", errors="strict")
            if proc.returncode == 0 and text.strip():
                return text, {}, "pdftotext"
            errors.append("pdftotext:no_text_or_error")
        except (OSError, UnicodeError, subprocess.TimeoutExpired) as exc:
            errors.append("pdftotext:" + str(exc)[:120])
    else:
        errors.append("pdftotext:unavailable")
    raise ValueError("; ".join(errors))


def extract(path: Path, max_bytes: int = 16 * 1024 * 1024) -> dict:
    try:
        if path.stat().st_size > max_bytes:
            return {"status": "skipped_large", "text": "", "meta": {}, "backend": None,
                    "detail": f"file exceeds {max_bytes}-byte extraction budget"}
        if path.suffix.lower() in TEXT_EXTS:
            raw = path.read_bytes()
            encoding = "utf-16" if raw.startswith((b"\xff\xfe", b"\xfe\xff")) else "utf-8-sig"
            return {"status": "extracted", "text": raw.decode(encoding), "meta": {},
                    "backend": encoding, "detail": ""}
        if path.suffix.lower() == ".pdf":
            text, meta, backend = _pdf(path)
        elif path.suffix.lower() in {".docx", ".pptx", ".xlsx"}:
            text, meta, backend = _ooxml(path)
        else:
            return {"status": "unsupported", "text": "", "meta": {}, "backend": None,
                    "detail": "no declared safe extractor for this suffix"}
        if not text.strip():
            return {"status": "no_text_layer", "text": "", "meta": meta, "backend": backend,
                    "detail": "backend found no text; OCR was not fabricated"}
        return {"status": "extracted", "text": text, "meta": meta, "backend": backend,
                "detail": ""}
    except (OSError, UnicodeError, ValueError, zipfile.BadZipFile, ET.ParseError) as exc:
        return {"status": "failed", "text": "", "meta": {}, "backend": None,
                "detail": str(exc)[:400]}


def _meta_records(path: Path) -> list[dict]:
    if path.suffix.lower() == ".json":
        value = json.loads(path.read_text(encoding="utf-8-sig"))
        if isinstance(value, dict):
            for key in ("documents", "records", "files", "items"):
                if isinstance(value.get(key), list):
                    value = value[key]
                    break
            else:
                return [{"path": k, "meta": v} for k, v in value.items() if isinstance(v, dict)]
        return [r for r in value if isinstance(r, dict)] if isinstance(value, list) else []
    delim = "\t" if path.suffix.lower() == ".tsv" else ","
    with path.open(encoding="utf-8-sig", newline="") as fh:
        return [dict(r) for r in csv.DictReader(fh, delimiter=delim)]


def build_corpus(root: Path, metadata_files: list[str] | None = None,
                 max_bytes: int = 16 * 1024 * 1024) -> dict:
    root = Path(root).resolve()
    if not root.is_dir():
        return {"ok": False, "refusal": {"rule": "search.root_missing",
                                         "message": f"not a readable directory: {root}"}}
    sidecars = list(metadata_files or [])
    for name in ("metadata.json", "metadata.csv", "metadata.tsv"):
        if (root / name).is_file() and name not in sidecars:
            sidecars.append(name)
    records: list[dict] = []
    issues: list[dict] = []
    for name in sidecars:
        p = root / name
        try:
            if not p.is_file() or root not in p.resolve().parents:
                raise ValueError("sidecar is missing or outside root")
            records.extend(_meta_records(p))
        except (OSError, ValueError, UnicodeError, json.JSONDecodeError, csv.Error) as exc:
            issues.append({"path": name, "status": "metadata_failed", "detail": str(exc)})
    by_path: dict[str, dict] = {}
    for rec in records:
        path = str(rec.get("path") or rec.get("file") or "").strip().replace("\\", "/")
        if not path:
            continue
        target = by_path.setdefault(path, {"meta": {}, "meta_src": {}, "title": ""})
        values = rec.get("meta") if isinstance(rec.get("meta"), dict) else rec
        for key, value in values.items():
            if key in {"path", "file", "meta", "attachments", "aliases"} or value in (None, "", [], {}):
                continue
            if key in target["meta"] and target["meta"][key] != value:
                issues.append({"path": path, "status": "metadata_conflict", "field": key,
                               "detail": "different declared values retained as a warning; first value kept"})
                continue
            target["meta"][key] = value
            target["meta_src"][key] = "declared_sidecar"
        target["title"] = str(rec.get("title") or target["meta"].get("title") or target["title"])
    paths = []
    for base, dirs, names in os.walk(root, followlinks=False):
        dirs[:] = sorted(d for d in dirs if not os.path.islink(os.path.join(base, d)))
        for name in sorted(names):
            p = Path(base) / name
            rel = p.relative_to(root).as_posix()
            if p.is_symlink():
                issues.append({"path": rel, "status": "symlink_skipped", "detail": "link not followed"})
            elif p.is_file():
                paths.append(p)
    paths.sort(key=lambda p: p.relative_to(root).as_posix())
    corpus, coverage = [], []
    sidecar_set = set(sidecars)
    for p in paths:
        rel = p.relative_to(root).as_posix()
        row = {"path": rel, "role": "metadata_sidecar" if rel in sidecar_set else "document",
               "size": None, "source_sha256": None}
        try:
            row["size"] = p.stat().st_size
            row["source_sha256"] = sha256_file(p)
        except OSError as exc:
            row.update(status="unreadable", detail=str(exc))
            issues.append(row)
            coverage.append(row)
            continue
        if rel in sidecar_set:
            row.update(status="metadata_only", detail="linked metadata is indexed via declared document metadata")
            coverage.append(row)
            continue
        got = extract(p, max_bytes=max_bytes)
        row.update(status=got["status"], backend=got.get("backend"),
                   detail=got.get("detail") or "", characters=len(got.get("text") or ""))
        declared = by_path.get(rel, {"meta": {}, "meta_src": {}, "title": ""})
        meta = dict(declared["meta"])
        for key, value in (got.get("meta") or {}).items():
            if key not in meta:
                meta[key] = value
        if got["status"] == "extracted":
            corpus.append({"id": rel, "path": rel, "title": declared["title"] or meta.get("title") or "",
                           "text": got["text"], "meta": meta, "source_sha256": row["source_sha256"]})
        else:
            issues.append(row)
        coverage.append(row)
    return {"ok": bool(corpus), "corpus": corpus, "coverage": coverage, "issues": issues,
            "refusal": None if corpus else {"rule": "search.empty_corpus",
                                            "message": "no file yielded a real text layer; see extraction coverage"}}
