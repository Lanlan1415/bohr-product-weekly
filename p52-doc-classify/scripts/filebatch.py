"""Classify an actual file tree and materialise a non-destructive organised copy."""
from __future__ import annotations

import csv
import hashlib
import json
import re
import shutil
import subprocess
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

import classify
import land

SCHEMA_VERSION = "doc-filebatch/v2"
TEXT_EXTS = {".txt", ".md", ".csv", ".tsv", ".json", ".jsonl", ".xml", ".yaml",
             ".yml", ".ris", ".bib", ".tex", ".log", ".py"}
DOI_RE = re.compile(r"\b10\.\d{4,9}/[-._;()/:A-Z0-9]+", re.I)


def _xml_text(raw: bytes) -> str:
    root = ET.fromstring(raw)
    return " ".join(el.text for el in root.iter()
                    if el.tag.rsplit("}", 1)[-1] in {"t", "v"} and el.text)


def _ooxml(path: Path) -> tuple[str, dict, str]:
    meta: dict = {}
    chunks: list[str] = []
    with zipfile.ZipFile(path) as zf:
        names = set(zf.namelist())
        if "docProps/core.xml" in names:
            root = ET.fromstring(zf.read("docProps/core.xml"))
            for el in root.iter():
                key, value = el.tag.rsplit("}", 1)[-1], (el.text or "").strip()
                if value and key in {"title", "creator", "subject", "description"}:
                    meta[{"creator": "author"}.get(key, key)] = value
        suffix = path.suffix.lower()
        if suffix == ".docx":
            targets = ["word/document.xml"] if "word/document.xml" in names else []
        elif suffix == ".pptx":
            targets = sorted((n for n in names if re.fullmatch(r"ppt/slides/slide\d+\.xml", n)),
                             key=lambda n: int(re.search(r"\d+", Path(n).stem).group()))
        else:
            targets = sorted(n for n in names if n == "xl/sharedStrings.xml" or
                             re.fullmatch(r"xl/worksheets/sheet\d+\.xml", n))
        chunks = [_xml_text(zf.read(n)) for n in targets]
    return "\n".join(c for c in chunks if c.strip()), meta, "ooxml-xml"


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
                    "detail": "no real text layer; no content-based classification was invented"}
        return {"status": "extracted", "text": text, "meta": meta, "backend": backend,
                "detail": ""}
    except (OSError, UnicodeError, ValueError, zipfile.BadZipFile, ET.ParseError) as exc:
        return {"status": "failed", "text": "", "meta": {}, "backend": None,
                "detail": str(exc)[:400]}


def _declared_records(root: Path, names: list[str]) -> tuple[dict, list[str]]:
    by_path: dict[str, dict] = {}
    warnings: list[str] = []
    for name in names:
        path = root / name
        try:
            if not path.is_file() or root not in path.resolve().parents:
                raise ValueError("sidecar missing or outside root")
            rows = []
            if path.suffix.lower() == ".json":
                value = json.loads(path.read_text(encoding="utf-8-sig"))
                if isinstance(value, dict):
                    for key in ("documents", "records", "files", "items"):
                        if isinstance(value.get(key), list):
                            value = value[key]
                            break
                    else:
                        value = [{"path": k, "meta": v} for k, v in value.items()
                                 if isinstance(v, dict)]
                rows = value if isinstance(value, list) else []
            elif path.suffix.lower() in {".csv", ".tsv"}:
                with path.open(encoding="utf-8-sig", newline="") as fh:
                    rows = list(csv.DictReader(fh, delimiter="\t" if path.suffix.lower() == ".tsv" else ","))
            for i, rec in enumerate(rows):
                if not isinstance(rec, dict):
                    continue
                rel = str(rec.get("path") or rec.get("file") or "").strip().replace("\\", "/")
                if not rel:
                    continue
                target = by_path.setdefault(rel, {})
                values = rec.get("meta") if isinstance(rec.get("meta"), dict) else rec
                source = f"{name}#{i + 1}"
                for key, value in values.items():
                    if key in {"path", "file", "meta", "attachments", "aliases"} or value in (None, "", [], {}):
                        continue
                    if key in target and target[key] != value:
                        warnings.append(f"{rel}: conflicting {key} declarations; first value retained")
                        continue
                    target[key] = value
                    target.setdefault("_sources", {})[key] = f"{source}:{key}"
        except (OSError, ValueError, UnicodeError, json.JSONDecodeError, csv.Error) as exc:
            warnings.append(f"metadata sidecar {name!r} not used: {exc}")
    return by_path, warnings


def _content_metadata(text: str) -> tuple[dict, dict]:
    meta: dict = {}
    sources: dict = {}
    match = DOI_RE.search(text[:16000])
    if match:
        meta["doi"] = match.group(0).rstrip(".;,)")
        sources["doi"] = f"content_regex:[{match.start()}:{match.end()}]:{match.group(0)}"
    return meta, sources


def run(spec: dict, root, out_dir) -> dict:
    if not isinstance(spec, dict):
        return {"schema_version": SCHEMA_VERSION, "status": "undetermined",
                "refusal": {"rule": "filebatch.spec_unreadable", "message": "spec must be an object"}}
    root = Path(root).resolve() if root else None
    if root is None or not root.is_dir():
        return {"schema_version": SCHEMA_VERSION, "status": "undetermined",
                "refusal": {"rule": "filebatch.root_missing", "message": f"root is not a directory: {root}"}}
    if not isinstance(spec.get("taxonomy"), list) or not spec["taxonomy"]:
        return {"schema_version": SCHEMA_VERSION, "status": "undetermined",
                "refusal": {"rule": "cls.empty_taxonomy",
                            "message": "a declared multi-level taxonomy is required; no categories are guessed"}}
    inv = land.inventory(root)
    if inv.get("status") == "undetermined":
        return inv
    sidecars = list(spec.get("metadata_files") or [])
    for name in ("metadata.json", "metadata.csv", "metadata.tsv"):
        if (root / name).is_file() and name not in sidecars:
            sidecars.append(name)
    declared, warnings = _declared_records(root, sidecars)
    records: list[dict] = []
    extracts: dict[str, dict] = {}
    provenance: dict[str, dict] = {}
    metadata_by_path: dict[str, dict] = {}
    for i, file in enumerate(inv["files"]):
        rel = file["path"]
        path = root / rel
        got = extract(path) if file.get("readable", True) and file.get("sha256") else {
            "status": "failed", "text": "", "meta": {}, "backend": None,
            "detail": "file could not be read or hashed"}
        extracts[rel] = {k: v for k, v in got.items() if k not in {"text", "meta"}}
        declared_meta = {k: v for k, v in declared.get(rel, {}).items() if k != "_sources"}
        meta = dict(declared_meta)
        meta_src = dict(declared.get(rel, {}).get("_sources") or {})
        for key, value in (got.get("meta") or {}).items():
            if key not in meta:
                meta[key] = value
                meta_src[key] = f"embedded:{got.get('backend')}:{key}"
        # A metadata sidecar DESCRIBES other files; its DOI-looking strings are
        # not automatically identifiers of the sidecar itself.
        content_meta, content_src = ({}, {}) if rel in sidecars else _content_metadata(
            got.get("text") or "")
        for key, value in content_meta.items():
            if key not in meta:
                meta[key] = value
                meta_src[key] = content_src[key]
        metadata_by_path[rel] = meta
        provenance[rel] = meta_src
        records.append({"id": rel, "path": rel,
                        "title": str(meta.get("title") or ""),
                        "abstract": str(meta.get("abstract") or ""),
                        "keywords": meta.get("keywords") or meta.get("subject") or "",
                        "text": got.get("text") or "", "meta": meta})
    cls = classify.run({"taxonomy": spec["taxonomy"], "records": records},
                       min_hits=spec.get("min_hits", 1))
    if cls.get("status") == "undetermined":
        return cls
    cls_by_id = {r["id"]: r for r in cls["records"]}
    entries = []
    file_results = []
    inv_by_path = {f["path"]: f for f in inv["files"]}
    for rec in records:
        rel = rec["path"]
        result = cls_by_id[rel]
        labels = result.get("labels") or []
        meta = metadata_by_path[rel]
        entry = {"path": rel, "category": result["primary"],
                 "author": meta.get("author") or meta.get("creator"),
                 "year": meta.get("year"), "title": meta.get("title"),
                 "doi": meta.get("doi"), "version": meta.get("version") or meta.get("pubstate"),
                 "secondary_categories": [x["category"] for x in labels[1:]],
                 "classification_confidence": result["confidence"],
                 "classification_reason": result["reason"],
                 "classification_evidence": result.get("source_evidence") or [],
                 "metadata_provenance": provenance[rel], "text_extraction": extracts[rel]}
        entries.append(entry)
        file_results.append({"path": rel, "inventory": inv_by_path[rel],
                             "classification": result, "metadata": meta,
                             "metadata_provenance": provenance[rel],
                             "text_extraction": extracts[rel]})
    landed = land.land_run({"entries": entries, "organize": spec.get("organize") or {}},
                           root, out_dir, execute_now=False)
    if landed.get("status") == "undetermined":
        return landed
    fingerprint = hashlib.sha256(json.dumps({
        "files": [{"path": f["path"], "sha256": f["sha256"]} for f in inv["files"]],
        "taxonomy": spec["taxonomy"], "metadata": provenance,
    }, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()
    status = "review" if landed["status"] == "review" or any(
        r.get("review_required") for r in cls["records"]) else landed["status"]
    return {"schema_version": SCHEMA_VERSION, "status": status,
            "counts": {"files": len(records), "classifications": len(cls["records"]),
                       "unclassified": len(cls["summary"]["unclassified_ids"]),
                       "multi_label": len(cls["summary"]["multi_label_ids"]),
                       "needs_review": len(cls["summary"]["needs_review_ids"]),
                       "planned": len(landed["plan"]), "source_writes": 0},
            "files": file_results, "classification_summary": cls["summary"],
            "taxonomy_declared": cls["taxonomy_declared"],
            "plan": landed["plan"], "duplicates": landed["duplicates"],
            "near_duplicates": landed["near_duplicates"],
            "version_relations": landed["version_relations"],
            "findings": cls["findings"] + landed["findings"],
            "metadata_warnings": warnings, "batch_sha256": fingerprint,
            "limits": ["source filenames/extensions never supply classification evidence",
                       "confidence is deterministic evidence calibration, not a neural-model probability"]}


def run_with_output(spec: dict, root, out_dir, materialize=None) -> dict:
    result = run(spec, root, out_dir)
    if result.get("status") == "undetermined" or materialize is None:
        return result
    copy_result = land.materialize_plan(result["plan"], root, materialize, out_dir)
    result["materialized"] = copy_result
    result["findings"] = result.get("findings", []) + copy_result["findings"]
    if copy_result["status"] == "blocked":
        result["status"] = "blocked"
    elif copy_result["status"] == "review" and result["status"] != "blocked":
        result["status"] = "review"
    result["counts"]["copied"] = copy_result["changed"]
    result["counts"]["copy_already_done"] = copy_result["already_done"]
    result["operation_evidence"] = {"source_mode": "read_only", "source_writes": 0,
                                    "copy_journal": copy_result["journal_path"],
                                    "destination": copy_result.get("destination"),
                                    "post_copy_hashes_verified": copy_result["changed"]}
    return result


def render_summary(result: dict) -> str:
    lines = ["# Actual file classification and safe landing", "",
             f"batch_sha256: {result.get('batch_sha256', '-')}", "",
             "| file | primary | confidence | review | secondary | target |",
             "|---|---|---:|---|---|---|"]
    plans = {p["old"]: p for p in result.get("plan") or []}
    for item in result.get("files") or []:
        path, c = item["path"], item["classification"]
        target = plans.get(path, {}).get("new", "")
        secondary = ", ".join(x["category"] for x in (c.get("labels") or [])[1:])
        lines.append(f"| {path} | {c['primary']} | {c['confidence']} | {c.get('review_required')} | "
                     f"{secondary} | {target} |")
    lines.extend(["", "Source files were not moved, renamed, overwritten or deleted.",
                  "When materialisation is requested, only verified copies are created in the separate output tree."])
    return "\n".join(lines) + "\n"
