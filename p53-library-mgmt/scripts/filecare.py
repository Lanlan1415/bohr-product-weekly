"""Read-only inspection and a reversible plan for a real research file tree.

Unlike library.py (an inline-text store), this module treats the source bytes as
the artifact. It inventories every regular file, hashes the original bytes in
full, extracts text only with a real backend, resolves declared aliases and
attachments, and plans names/directories without moving or deleting anything.
The same mechanisms are useful for Zotero-like linked attachments and ordinary
folders, but no Zotero account or publisher metadata is assumed.
"""
from __future__ import annotations

import csv
import hashlib
import json
import os
import re
import shutil
import stat
import subprocess
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

SCHEMA_VERSION = "library-filecare/v2"
TEXT_EXTS = {".txt", ".md", ".csv", ".tsv", ".json", ".jsonl", ".xml",
             ".yaml", ".yml", ".ris", ".bib", ".tex", ".log", ".py"}
KIND = {
    ".pdf": "pdf", ".doc": "office", ".docx": "office", ".ppt": "office",
    ".pptx": "office", ".xls": "office", ".xlsx": "office", ".csv": "data",
    ".tsv": "data", ".json": "data", ".jsonl": "data", ".txt": "text",
    ".md": "text", ".ris": "metadata", ".bib": "metadata", ".png": "image",
    ".jpg": "image", ".jpeg": "image", ".tif": "image", ".tiff": "image",
    ".zip": "archive", ".7z": "archive", ".gz": "archive",
}
META_FIELDS = ("title", "author", "authors", "year", "doi", "project",
               "instrument", "journal", "version", "batch", "type")


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with Path(path).open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def refusal(rule: str, message: str) -> dict:
    return {"schema_version": SCHEMA_VERSION, "status": "undetermined",
            "refusal": {"rule": rule, "message": message},
            "limits": ["the source tree was not changed and no completed inventory is claimed"]}


def _xml_text(data: bytes) -> str:
    root = ET.fromstring(data)
    vals = []
    for el in root.iter():
        tag = el.tag.rsplit("}", 1)[-1]
        if tag in {"t", "v"} and el.text:
            vals.append(el.text)
        elif tag in {"p", "row"} and vals:
            vals.append("\n")
    return re.sub(r"\n{3,}", "\n\n", " ".join(vals)).strip()


def _ooxml(path: Path) -> tuple[str, dict, str]:
    """Extract actual visible OOXML text and core properties, never guessed."""
    meta: dict = {}
    chunks: list[str] = []
    with zipfile.ZipFile(path) as zf:
        names = set(zf.namelist())
        if "docProps/core.xml" in names:
            core = ET.fromstring(zf.read("docProps/core.xml"))
            for el in core.iter():
                key = el.tag.rsplit("}", 1)[-1]
                value = (el.text or "").strip()
                if value and key in {"title", "creator", "subject", "description"}:
                    meta[{"creator": "author"}.get(key, key)] = value
        if path.suffix.lower() == ".docx":
            targets = ["word/document.xml"] if "word/document.xml" in names else []
        elif path.suffix.lower() == ".pptx":
            targets = sorted((n for n in names if re.fullmatch(r"ppt/slides/slide\d+\.xml", n)),
                             key=lambda n: int(re.search(r"(\d+)", Path(n).stem).group(1)))
        else:
            targets = sorted(n for n in names if n == "xl/sharedStrings.xml" or
                             re.fullmatch(r"xl/worksheets/sheet\d+\.xml", n))
        for name in targets:
            chunks.append(_xml_text(zf.read(name)))
    return "\n".join(c for c in chunks if c).strip(), meta, "ooxml-xml"


def _pdf(path: Path) -> tuple[str, dict, str]:
    errors = []
    try:
        import fitz  # type: ignore
        try:
            with fitz.open(path) as doc:
                if doc.is_encrypted:
                    raise ValueError("encrypted PDF")
                pages = [page.get_text("text") for page in doc]
                md = doc.metadata or {}
            text = "\f".join(pages).strip()
            if text:
                meta = {k: str(md[k]) for k in ("title", "author") if md.get(k)}
                return text, meta, "pymupdf"
            errors.append("pymupdf:no_text_layer")
        except Exception as exc:  # backend errors become an honest extraction status
            errors.append("pymupdf:" + str(exc)[:120])
    except ImportError:
        errors.append("pymupdf:unavailable")
    try:
        import pypdf  # type: ignore
        try:
            rd = pypdf.PdfReader(str(path))
            if rd.is_encrypted:
                raise ValueError("encrypted PDF")
            text = "\f".join((p.extract_text() or "") for p in rd.pages).strip()
            if text:
                md = rd.metadata or {}
                raw_meta = {k: str(md[k]) for k in ("/Title", "/Author") if md.get(k)}
                meta = {{"/Title": "title", "/Author": "author"}.get(k, k): v
                        for k, v in raw_meta.items()}
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
            text = proc.stdout.decode("utf-8", errors="strict").strip()
            if proc.returncode == 0 and text:
                return text, {}, "pdftotext"
            errors.append("pdftotext:no_text_or_error")
        except (OSError, subprocess.TimeoutExpired, UnicodeDecodeError) as exc:
            errors.append("pdftotext:" + str(exc)[:120])
    else:
        errors.append("pdftotext:unavailable")
    raise ValueError("; ".join(errors))


def extract(path: Path, max_bytes: int = 16 * 1024 * 1024) -> dict:
    """Return text plus extraction evidence, or a precise non-fabricating status."""
    suffix = path.suffix.lower()
    try:
        if path.stat().st_size > max_bytes:
            return {"status": "skipped_large", "backend": None, "text": "", "meta": {},
                    "detail": f"text extraction limit is {max_bytes} bytes; raw-byte hashing still ran"}
        if suffix in TEXT_EXTS:
            raw = path.read_bytes()
            encoding = "utf-8-sig"
            if raw.startswith((b"\xff\xfe", b"\xfe\xff")):
                encoding = "utf-16"
            return {"status": "extracted", "backend": encoding, "meta": {},
                    "text": raw.decode(encoding), "detail": ""}
        if suffix == ".pdf":
            text, meta, backend = _pdf(path)
        elif suffix in {".docx", ".pptx", ".xlsx"}:
            text, meta, backend = _ooxml(path)
        else:
            return {"status": "unsupported", "backend": None, "text": "", "meta": {},
                    "detail": "no safe text extractor is declared for this file type"}
        if not text.strip():
            return {"status": "no_text_layer", "backend": backend, "text": "", "meta": meta,
                    "detail": "the backend found no extractable text; no content was invented"}
        return {"status": "extracted", "backend": backend, "text": text, "meta": meta,
                "detail": ""}
    except (OSError, UnicodeError, zipfile.BadZipFile, ET.ParseError, ValueError) as exc:
        return {"status": "failed", "backend": None, "text": "", "meta": {},
                "detail": str(exc)[:400]}


def _norm_rel(value) -> str:
    text = str(value or "").strip().replace("\\", "/")
    while text.startswith("./"):
        text = text[2:]
    return text


def _in_root(root: Path, relative: str) -> bool:
    try:
        candidate = (root / relative).resolve()
        return candidate != root and root in candidate.parents
    except OSError:
        return False


def _norm_doi(value) -> str:
    text = str(value or "").strip().lower()
    return re.sub(r"^(?:https?://(?:dx\.)?doi\.org/|doi:\s*)", "", text).rstrip(" .;")


def _norm_title(value) -> str:
    return re.sub(r"[^\w\u4e00-\u9fff]+", "", str(value or "").casefold())


def _slug(value, fallback: str, max_len: int = 80) -> str:
    text = re.sub(r'[<>:"/\\|?*\x00-\x1f]+', "", str(value or ""))
    text = re.sub(r"[\s\-_]+", "-", text).strip("-. ")
    return (text or fallback)[:max_len].rstrip("-. ")


def _records_from_value(value, source: str) -> list[dict]:
    if isinstance(value, dict):
        for key in ("records", "documents", "files", "items"):
            if isinstance(value.get(key), list):
                value = value[key]
                break
        else:
            rows = []
            for path, meta in value.items():
                if isinstance(meta, dict):
                    rows.append({"path": path, "meta": meta, "_source": source})
            return rows
    if not isinstance(value, list):
        return []
    rows = []
    for i, row in enumerate(value):
        if not isinstance(row, dict):
            continue
        rec = dict(row)
        rec["_source"] = f"{source}#{i + 1}"
        rows.append(rec)
    return rows


def load_declared_records(spec: dict, root: Path) -> tuple[list[dict], list[str]]:
    """Load only declared record/sidecar values and retain field-level provenance."""
    records: list[dict] = []
    warnings: list[str] = []
    for i, rec in enumerate(spec.get("records") or []):
        if isinstance(rec, dict):
            item = dict(rec)
            item["_source"] = f"spec.records#{i + 1}"
            records.append(item)
        else:
            warnings.append(f"spec.records#{i + 1} is not an object and was not used")
    raw_sidecars = spec.get("metadata_files") or []
    if isinstance(raw_sidecars, str):
        raw_sidecars = [raw_sidecars]
    sidecars = list(raw_sidecars) if isinstance(raw_sidecars, (list, tuple)) else []
    for default in ("metadata.json", "metadata.csv", "metadata.tsv"):
        if (root / default).is_file() and default not in sidecars:
            sidecars.append(default)
    for name in sidecars:
        path = root / _norm_rel(name)
        try:
            if not path.is_file() or not _in_root(root, _norm_rel(name)):
                raise ValueError("metadata file is missing or outside root")
            if path.suffix.lower() == ".json":
                value = json.loads(path.read_text(encoding="utf-8-sig"))
                rows = _records_from_value(value, _norm_rel(name))
            elif path.suffix.lower() in {".csv", ".tsv"}:
                delim = "\t" if path.suffix.lower() == ".tsv" else ","
                with path.open(encoding="utf-8-sig", newline="") as fh:
                    rows = []
                    for i, row in enumerate(csv.DictReader(fh, delimiter=delim)):
                        rec = {"path": row.pop("path", row.pop("file", "")),
                               "meta": {k: v for k, v in row.items() if v not in (None, "")},
                               "_source": f"{_norm_rel(name)}#row-{i + 2}"}
                        rows.append(rec)
            else:
                raise ValueError("metadata sidecar must be JSON, CSV or TSV")
            records.extend(rows)
        except (OSError, ValueError, UnicodeError, json.JSONDecodeError, csv.Error) as exc:
            warnings.append(f"metadata sidecar {name!r} was not used: {exc}")
    return records, sorted(set(sidecars))


def _merge_file_record(path: str, records: list[dict], aliases: dict) -> tuple[dict, dict, list[str]]:
    """Attach declared metadata to one file without guessing values from its name."""
    matched = [r for r in records if _norm_rel(r.get("path") or r.get("file")) == path]
    meta: dict = {}
    sources: dict = {}
    warnings: list[str] = []
    for rec in matched:
        source = str(rec.get("_source") or "record")
        values = rec.get("meta") if isinstance(rec.get("meta"), dict) else rec
        for key, value in values.items():
            if key.startswith("_") or key in {"path", "file", "meta", "aliases", "attachments"}:
                continue
            if value in (None, "", [], {}):
                continue
            if key in meta and meta[key] != value:
                warnings.append(f"{path}: conflicting declarations for {key}: {meta[key]!r} vs {value!r}")
                continue
            meta[key] = value
            sources[key] = f"{source}:{key}"
        rid = str(rec.get("id") or "").strip()
        if rid:
            aliases.setdefault(rid, set()).add(path)
        for alias in rec.get("aliases") or []:
            aliases.setdefault(str(alias), set()).add(path)
    return meta, sources, warnings


def _search_key(value) -> list[str]:
    text = str(value or "").casefold()
    latin = re.findall(r"[a-z][a-z0-9_-]+", text)
    cjk = []
    for run in re.findall(r"[\u4e00-\u9fff]{2,}", text):
        cjk.extend(run[i:i + 2] for i in range(len(run) - 1))
    return sorted(set(latin + cjk))


def _retrieve(documents: list[dict], query) -> dict | None:
    if not query:
        return None
    terms = _search_key(query)
    hits = []
    for doc in documents:
        text = doc.get("_text") or ""
        fields = [doc.get("title") or "", doc.get("path") or "", text,
                  json.dumps(doc.get("meta") or {}, ensure_ascii=False)]
        shared = sorted(set(terms) & set(_search_key(" ".join(fields))))
        if not shared:
            continue
        at = text.casefold().find(str(shared[0]).casefold()) if text else -1
        snippet = text[max(0, at - 80): at + len(shared[0]) + 160] if at >= 0 else ""
        hits.append({"path": doc["path"], "score": len(shared), "matched_terms": shared,
                     "sha256": doc["sha256"], "snippet": snippet,
                     "reason": "shared full-text/title/path/metadata terms; exact terms recorded"})
    hits.sort(key=lambda h: (-h["score"], h["path"]))
    return {"query": str(query), "hits": hits, "empty": not hits,
            "note": "no indexed full text or metadata term matched" if not hits else
                    "ranked by distinct matched terms, then source path; no semantic claim"}


def run(spec: dict, root, query=None) -> dict:
    if not isinstance(spec, dict):
        return refusal("filecare.spec_unreadable", "spec must be a JSON object")
    root = Path(root) if root else None
    if root is None or not root.is_dir():
        return refusal("filecare.root_missing", f"batch root is not a readable directory: {root}")
    try:
        root = root.resolve()
    except OSError as exc:
        return refusal("filecare.root_missing", str(exc))
    records, sidecars = load_declared_records(spec, root)
    paths: list[Path] = []
    path_errors: list[dict] = []

    def onerror(exc):
        path_errors.append({"path": str(getattr(exc, "filename", "")), "reason": str(exc)})

    for base, dirs, names in os.walk(root, followlinks=False, onerror=onerror):
        dirs[:] = sorted(d for d in dirs if not os.path.islink(os.path.join(base, d)))
        for name in sorted(names):
            p = Path(base) / name
            if p.is_symlink():
                path_errors.append({"path": p.relative_to(root).as_posix(),
                                    "reason": "symbolic link not followed or hashed"})
                continue
            if p.is_file():
                paths.append(p)
    paths.sort(key=lambda p: p.relative_to(root).as_posix())
    if not paths:
        return refusal("filecare.empty_root", "the root contains no regular files to inventory")

    aliases: dict[str, set] = {}
    declared_by_path = {_norm_rel(r.get("path") or r.get("file")): r for r in records
                        if _norm_rel(r.get("path") or r.get("file"))}
    for rec in records:
        path = _norm_rel(rec.get("path") or rec.get("file"))
        rid = str(rec.get("id") or "").strip()
        if path and rid:
            aliases.setdefault(rid, set()).add(path)
        for alias in rec.get("aliases") or []:
            if path:
                aliases.setdefault(str(alias), set()).add(path)

    documents: list[dict] = []
    findings: list[dict] = []
    warnings: list[str] = []
    referenced: set[str] = set()
    missing: list[dict] = []
    conflicts: list[dict] = []
    version_links: list[dict] = []
    for rec in records:
        source_path = _norm_rel(rec.get("path") or rec.get("file"))
        if source_path:
            referenced.add(source_path)
        for field in ("attachments", "attachment", "fulltext", "supplement"):
            vals = rec.get(field) or []
            if isinstance(vals, (str, dict)):
                vals = [vals]
            if not isinstance(vals, list):
                continue
            for val in vals:
                if isinstance(val, dict):
                    val = val.get("path") or val.get("file") or val.get("id")
                target = _norm_rel(val)
                resolved = sorted(aliases.get(target, {target}))
                if len(resolved) > 1:
                    conflicts.append({"source": rec.get("_source"), "field": field,
                                      "reference": target, "candidates": resolved,
                                      "reason": "ambiguous alias; no attachment selected"})
                elif not _in_root(root, resolved[0]) or not (root / resolved[0]).is_file():
                    missing.append({"source": rec.get("_source"), "field": field,
                                    "reference": target, "reason": "declared attachment or alias not found inside root"})
                else:
                    referenced.add(resolved[0])
        for field in ("version_of", "supersedes", "alias_of"):
            if rec.get(field):
                target = _norm_rel(rec.get(field))
                resolved = sorted(aliases.get(target, {target}))
                version_links.append({"from": source_path, "to": resolved[0] if len(resolved) == 1 else None,
                                      "reference": target, "basis": f"declared:{field}",
                                      "resolved": len(resolved) == 1 and (root / resolved[0]).is_file()})
                if len(resolved) == 1:
                    referenced.add(resolved[0])

    for p in paths:
        rel = p.relative_to(root).as_posix()
        entry = {"id": rel, "path": rel, "title": "", "kind": KIND.get(p.suffix.lower(), "other"),
                 "extension": p.suffix.lower(), "bytes": None, "sha256": None, "mode": None,
                 "readable": False, "text_extraction": {"status": "not_attempted"},
                 "meta": {}, "meta_src": {}, "folder": "未归类", "folder_cues": []}
        try:
            st = p.stat()
            entry["bytes"] = st.st_size
            entry["mode"] = stat.filemode(st.st_mode)
            entry["sha256"] = sha256_file(p)
            entry["readable"] = True
        except OSError as exc:
            entry["text_extraction"] = {"status": "unreadable", "detail": str(exc)}
            documents.append(entry)
            continue
        meta, meta_src, merge_warnings = _merge_file_record(rel, records, aliases)
        warnings.extend(merge_warnings)
        extracted = extract(p)
        entry["text_extraction"] = {k: v for k, v in extracted.items() if k not in {"text", "meta"}}
        entry["text_characters"] = len(extracted.get("text") or "")
        for key, value in (extracted.get("meta") or {}).items():
            if key not in meta:
                meta[key] = value
                meta_src[key] = f"embedded:{extracted.get('backend')}:{key}"
        entry["meta"] = meta
        entry["meta_src"] = meta_src
        entry["title"] = str(meta.get("title") or Path(rel).stem)
        entry["_text"] = extracted.get("text") or ""
        documents.append(entry)

    by_hash: dict[str, list[str]] = {}
    for doc in documents:
        if doc.get("sha256"):
            by_hash.setdefault(doc["sha256"], []).append(doc["path"])
    duplicates = [{"sha256": sha, "paths": sorted(items),
                   "policy": "identical original bytes; keep every source, plan review only"}
                  for sha, items in sorted(by_hash.items()) if len(items) > 1]

    groups: dict[str, list[dict]] = {}
    for doc in documents:
        meta = doc["meta"]
        keys = []
        if _norm_doi(meta.get("doi")):
            keys.append("doi:" + _norm_doi(meta.get("doi")))
        if _norm_title(meta.get("title")) and meta.get("year") not in (None, ""):
            keys.append("title_year:" + _norm_title(meta.get("title")) + ":" + str(meta["year"]))
        for key in keys:
            groups.setdefault(key, []).append(doc)
    related = []
    metadata_conflicts = []
    for key, docs in sorted(groups.items()):
        if len(docs) < 2 or len({d["sha256"] for d in docs}) < 2:
            continue
        related_paths = sorted(d["path"] for d in docs)
        evidence_basis = "declared DOI" if key.startswith("doi:") else "declared title+year"
        evidence_basis += " plus different original-byte hashes"
        existing = next((g for g in related if g["paths"] == related_paths), None)
        if existing is not None:
            existing["keys"].append(key)
            existing["basis"] = existing["basis"] + "; also " + evidence_basis
        else:
            related.append({"key": key, "keys": [key], "paths": related_paths,
                            "relation": "version_or_related", "authoritative": None,
                            "basis": evidence_basis})
        for field in META_FIELDS:
            vals: dict[str, list[str]] = {}
            for d in docs:
                if field in d["meta"]:
                    vals.setdefault(json.dumps(d["meta"][field], ensure_ascii=False, sort_keys=True),
                                    []).append(d["path"])
            if len(vals) > 1:
                previous = next((c for c in metadata_conflicts
                                 if c["field"] == field and c["paths"] == related_paths), None)
                if previous is not None:
                    previous["groups"].append(key)
                    continue
                metadata_conflicts.append({"group": key, "groups": [key], "field": field,
                                           "paths": related_paths,
                                           "values": [{"value": json.loads(v), "paths": ps}
                                                      for v, ps in sorted(vals.items())]})

    structure = spec.get("structure") if isinstance(spec.get("structure"), list) else []
    organize = spec.get("organize") if isinstance(spec.get("organize"), dict) else {}
    operation_plan: list[dict] = []
    occupied: dict[str, str] = {}
    for doc in documents:
        haystack = "\n".join([doc["title"], doc.get("_text") or "",
                              json.dumps(doc["meta"], ensure_ascii=False)]).casefold()
        for rule in structure:
            if not isinstance(rule, dict) or not rule.get("folder"):
                continue
            raw_cues = rule.get("cues") or []
            if isinstance(raw_cues, str):
                raw_cues = [raw_cues]
            cues = [str(c) for c in raw_cues if str(c).strip()]
            matched = [c for c in cues if c.casefold() in haystack]
            if matched:
                doc["folder"] = str(rule["folder"]).strip("/")
                doc["folder_cues"] = matched
                break
        meta = doc["meta"]
        template = str(organize.get("naming_template") or "author-year-title").lower()
        if template == "keep":
            stem = Path(doc["path"]).stem
            basis = "keep original filename"
        elif template == "doi" and meta.get("doi"):
            stem = "doi-" + _slug(_norm_doi(meta.get("doi")), Path(doc["path"]).stem)
            basis = "declared DOI metadata"
        elif meta.get("author") and meta.get("year") and meta.get("title"):
            author = meta["author"][0] if isinstance(meta["author"], list) and meta["author"] else meta["author"]
            stem = _slug(f"{author}-{meta['year']}-{meta['title']}", Path(doc["path"]).stem)
            basis = "declared author-year-title metadata"
        elif meta.get("title"):
            stem = _slug(meta["title"], Path(doc["path"]).stem)
            basis = "declared title only; missing fields not invented"
        else:
            stem = Path(doc["path"]).stem
            basis = "original stem fallback; metadata insufficient"
        folder = doc["folder"] if doc["folder"] != "未归类" else "review/未归类"
        target = f"{folder}/{stem}{doc['extension']}"
        if target.casefold() in occupied and occupied[target.casefold()] != doc["path"]:
            disambiguator = doc.get("sha256") or hashlib.sha256(doc["path"].encode("utf-8")).hexdigest()
            target = f"{folder}/{stem}-{disambiguator[:12]}{doc['extension']}"
        occupied[target.casefold()] = doc["path"]
        action = "review_move" if doc.get("sha256") else "inspect_unreadable"
        operation_plan.append({"source": doc["path"], "recommended_path": target,
                               "action": action, "executed": False,
                               "source_sha256": doc["sha256"], "name_basis": basis,
                               "folder_evidence": doc["folder_cues"],
                               "requires_human_approval": True,
                               "rollback": "if later applied, move recommended_path back to source after hash verification"})

    orphans = []
    if records:
        ignored = set(sidecars) | {"case.json", "task.md"}
        orphans = sorted(d["path"] for d in documents
                         if d["path"] not in referenced and d["path"] not in ignored)
    if path_errors:
        findings.append({"rule": "filecare.walk_skipped", "severity": "medium", "entries": path_errors})
    unreadable = [d["path"] for d in documents if not d["readable"]]
    not_extracted = [{"path": d["path"], "status": d["text_extraction"]["status"],
                      "detail": d["text_extraction"].get("detail", "")}
                     for d in documents if d["readable"] and d["text_extraction"]["status"] != "extracted"]
    if unreadable:
        findings.append({"rule": "filecare.unreadable", "severity": "medium", "paths": unreadable})
    if not_extracted:
        findings.append({"rule": "filecare.text_unavailable", "severity": "low", "entries": not_extracted})
    if duplicates:
        findings.append({"rule": "filecare.duplicate_content", "severity": "low",
                         "count": len(duplicates), "groups": duplicates})
    if missing:
        findings.append({"rule": "filecare.attachment_missing", "severity": "medium", "entries": missing})
    if conflicts or warnings:
        findings.append({"rule": "filecare.metadata_conflict", "severity": "medium",
                         "aliases": conflicts, "records": warnings})
    if orphans:
        findings.append({"rule": "filecare.attachment_orphan", "severity": "low", "paths": orphans})
    if metadata_conflicts:
        findings.append({"rule": "filecare.related_metadata_conflict", "severity": "medium",
                         "entries": metadata_conflicts})
    unfiled = [d["path"] for d in documents if d["folder"] == "未归类"]
    if structure and unfiled:
        findings.append({"rule": "filecare.unfiled", "severity": "low", "paths": unfiled})

    # Re-hash before delivery. Nothing has been written underneath root, so this
    # verifies that inspection did not silently change any source artifact.
    verify_errors = []
    for doc in documents:
        if not doc.get("sha256"):
            continue
        try:
            current = sha256_file(root / doc["path"])
            if current != doc["sha256"]:
                verify_errors.append({"path": doc["path"], "before": doc["sha256"], "after": current})
        except OSError as exc:
            verify_errors.append({"path": doc["path"], "error": str(exc)})

    raw_required = spec.get("meta_fields") or []
    if not isinstance(raw_required, (list, tuple)):
        raw_required = []
    required = [str(f) for f in raw_required]
    text_by_path = {d["path"]: d.get("_text") or "" for d in documents}
    for doc in documents:
        doc["metadata_missing"] = [f for f in required
                                   if f not in doc["meta"] or doc["meta"][f] in (None, "", [])]
        doc.pop("_text", None)
    retrieval = _retrieve([dict(d, _text=text_by_path[d["path"]]) for d in documents],
                          query or spec.get("query"))
    partial = bool(path_errors or unreadable or not_extracted or missing or conflicts or
                   warnings or metadata_conflicts or verify_errors)
    result = {
        "schema_version": SCHEMA_VERSION, "status": "partial" if partial else "ok",
        "counts": {"files": len(documents), "readable": sum(d["readable"] for d in documents),
                   "text_extracted": sum(d["text_extraction"]["status"] == "extracted" for d in documents),
                   "text_unavailable": len(not_extracted), "duplicate_sets": len(duplicates),
                   "missing_attachments": len(missing), "orphan_files": len(orphans),
                   "metadata_conflicts": len(metadata_conflicts) + len(warnings),
                   "planned_moves": sum(p["action"] == "review_move" for p in operation_plan),
                   "executed_moves": 0},
        "documents": documents, "duplicates": duplicates, "version_candidates": related,
        "declared_version_links": version_links,
        "attachments": {"missing": missing, "conflicts": conflicts, "orphans": orphans,
                        "referenced_files": sorted(referenced), "sidecars": sidecars},
        "metadata_conflicts": metadata_conflicts,
        "operation_plan": operation_plan,
        "operation_evidence": {"root": str(root), "hash_algorithm": "sha256", "hash_bytes": "original file bytes",
                               "source_mode": "read_only", "input_writes": 0,
                               "planned_moves": len(operation_plan), "executed_moves": 0,
                               "post_inventory_hash_errors": verify_errors,
                               "rollback": "no changes to roll back; every proposed row includes reversal instructions"},
        "retrieval": retrieval, "findings": findings, "limits": [],
    }
    if verify_errors:
        result["status"] = "partial"
        result["findings"].append({"rule": "filecare.integrity_changed", "severity": "high",
                                   "entries": verify_errors})
    if required:
        result["metadata_missing"] = {d["path"]: d["metadata_missing"] for d in documents
                                      if d["metadata_missing"]}
    if not records:
        result["limits"].append("no record/sidecar declarations: metadata and attachment linkage were not inferred")
    if not structure:
        result["limits"].append("no structure rules: proposed destinations remain under review/未归类")
    return result


def render_inventory(result: dict) -> str:
    lines = ["# Research file inventory and review plan", "",
             f"Files: {result.get('counts', {}).get('files', 0)}; source writes: 0; planned moves: "
             f"{result.get('counts', {}).get('planned_moves', 0)}", "",
             "| source | original SHA-256 | bytes | text | folder | recommended path |",
             "|---|---|---:|---|---|---|"]
    plans = {p["source"]: p for p in result.get("operation_plan") or []}
    for d in result.get("documents") or []:
        lines.append("| {path} | `{sha256}` | {bytes} | {status} | {folder} | {target} |".format(
            path=d["path"], sha256=d.get("sha256") or "unreadable", bytes=d.get("bytes"),
            status=d["text_extraction"]["status"], folder=d["folder"],
            target=plans.get(d["path"], {}).get("recommended_path", "")))
    for title, key in (("Duplicate original bytes", "duplicates"),
                       ("Missing attachments", "missing"),
                       ("Orphan files", "orphans")):
        values = result.get(key) if key == "duplicates" else result.get("attachments", {}).get(key)
        if values:
            lines.extend(["", "## " + title, "", "```json", json.dumps(values, ensure_ascii=False, indent=2), "```"])
    lines.extend(["", "No source file was moved, renamed, overwritten or deleted."])
    return "\n".join(lines) + "\n"
