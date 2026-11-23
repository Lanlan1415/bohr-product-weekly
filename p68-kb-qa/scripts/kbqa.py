"""Deterministic, extractive knowledge-base QA with paragraph evidence.

The pipeline deliberately has no generative step.  It inventories real files,
retrieves paragraphs with CJK-aware lexical ranking, decomposes multi-part
questions, and returns only verbatim source sentences as factual claims.  An
unsupported question is an explicit insufficient-evidence result, not an
invitation to invent an answer.

Public entry points:
    run_case(case, base_dir, out_dir, material_root=None) -> result dictionary
    verify_export(out_dir) -> verification dictionary
"""
from __future__ import annotations

import csv
import hashlib
import html.parser
import json
import math
import os
import re
import shutil
import subprocess
import tempfile
import unicodedata
import zipfile
from collections import Counter
from pathlib import Path
from xml.etree import ElementTree

SCHEMA = "kbqa/v3"
TEXT_SUFFIXES = {".txt", ".md", ".markdown", ".csv", ".tsv", ".json",
                 ".jsonl", ".ndjson", ".html", ".htm", ".xml", ".yaml", ".yml"}
DOC_SUFFIXES = TEXT_SUFFIXES | {".pdf", ".docx"}
SKIP_NAMES = {"case.json", "challenge.json", "config.json", "task.md",
              "result.json", "kb_index.json", "answers.json", "answers.md",
              "operation_log.json"}
DOC_KEYS = ("documents", "materials", "files", "records", "library", "corpus")
QUESTION_KEYS = ("questions", "queries", "searches", "questions_to_answer")
PATH_KEYS = ("path", "file", "file_path", "filepath", "source_path", "absolute_path")
TEXT_KEYS = ("text", "content", "body", "markdown", "extracted_text")
ID_KEYS = ("document_id", "doc_id", "id", "name", "filename", "title")
BULKY_CASE_KEYS = {"documents", "materials", "files", "records", "library", "corpus",
                   "questions", "queries", "searches", "output_contract", "text",
                   "content", "body", "workorder", "workorder_data"}

# These are query/function words, not domain stop words.  Domain terms are never
# discarded merely because they are common in a particular corpus.
CJK_STOP = {
    "什么", "多少", "哪些", "哪个", "如何", "为何", "为什么", "是否", "请问", "请",
    "根据", "知识库", "资料库", "材料中", "文件中", "原文", "回答", "说明", "介绍",
    "一下", "相关", "对应", "进行", "以及", "并且", "同时", "分别", "对比", "比较",
    "这个", "那个", "一种", "一个", "我们", "他们", "它们", "可以", "能够", "有无",
    "是不是", "有没有", "中的", "里的", "记录", "给出", "列出", "查询", "检索",
}
EN_STOP = {
    "a", "an", "and", "are", "as", "at", "be", "been", "but", "by", "can", "could",
    "do", "does", "for", "from", "give", "has", "have", "how", "in", "into", "is",
    "it", "its", "list", "me", "of", "on", "or", "our", "please", "show", "that",
    "the", "their", "them", "these", "this", "those", "to", "was", "we", "were",
    "what", "when", "where", "which", "who", "why", "with", "would", "you", "your",
}
MULTI_CUE = re.compile(r"分别|各自|以及|并且|同时|对比|比较|多跳|两个|三个|多个|and\b|compare", re.I)
# Retrieval-only bilingual cues.  They never enter an answer unless the exact
# source sentence is retrieved, so these are vocabulary bridges, not facts.
QUERY_BRIDGES = {
    "温度": ("temperature", "temp"), "保存": ("storage", "stored", "held", "kept"),
    "样品": ("sample", "specimen"), "测量": ("measurement", "measured"),
    "重复": ("replicate", "replicates", "repetition"), "数量": ("number", "count"),
    "版本": ("version", "revision"), "文件": ("file", "document"),
    "目录": ("directory", "folder"), "路径": ("path", "location"),
    "作者": ("author",), "标题": ("title",), "年份": ("year",),
    "来源": ("source", "origin"), "摘要": ("abstract", "summary"),
    "方法": ("method", "protocol"), "结果": ("result", "finding"),
    "结论": ("conclusion",), "吸收": ("uptake", "absorption"),
    "提高": ("increase", "increased", "raised", "improved"),
    "降低": ("decrease", "decreased", "reduced"), "取代": ("supersede", "superseded"),
    "冲突": ("conflict", "contradiction"), "权限": ("permission", "readonly"),
    "标签": ("tag", "label"), "批注": ("annotation", "comment"),
}
NUMBER = re.compile(r"(?<![A-Za-z0-9_])[-+]?\d+(?:\.\d+)?(?:\s*(?:%|％|倍|折|摄氏度|度|年|月|日|次|篇|个|种|nm|mm|cm|km|mg|kg|g|ml|l|pa|kpa|mpa|ev|kev|mev|gev|k|kv|mv|v|ma|a|w|kw|mw|hz|khz|mhz|ghz))?", re.I)


def _json(value) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _sha(text: str | bytes) -> str:
    raw = text if isinstance(text, bytes) else str(text).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _norm(text) -> str:
    return re.sub(r"\s+", " ", unicodedata.normalize("NFKC", str(text or "")).casefold()).strip()


def tokens(text, query: bool = False) -> list[str]:
    """Latin words plus CJK bigrams; CJK never degrades to an ASCII-only empty set."""
    s = unicodedata.normalize("NFKC", str(text or "")).casefold()
    latin = re.findall(r"[a-z][a-z0-9_+-]*|\d+(?:\.\d+)?", s)
    out = []
    for word in latin:
        if len(word) <= 1 or word in EN_STOP:
            continue
        out.append(word)
        # Conservative plural bridge (samples→sample); irregular morphology is
        # deliberately untouched rather than guessed by a stemming algorithm.
        if word.isalpha() and len(word) > 4 and word.endswith("s") and not word.endswith("ss"):
            out.append(word[:-1])
    for run in re.findall(r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]+", s):
        # Split explicit function words before forming bigrams.  If splitting
        # leaves nothing (e.g. “温度多少”), the original run still contributes
        # its domain bigram “温度”.
        pieces = [run]
        if query:
            for stop in sorted(CJK_STOP, key=len, reverse=True):
                nxt = []
                for p in pieces:
                    nxt.extend(x for x in p.split(stop) if x)
                pieces = nxt or [run]
        for p in pieces:
            if query:
                p = re.sub(r"[的了在是中里于和与及其或很都也就着到从被把对向]", "", p)
            if len(p) == 1:
                out.append(p)
            elif len(p) > 1:
                out.extend(p[i:i + 2] for i in range(len(p) - 1))
    return sorted(set(out))


def _source_id(record: dict, fallback: str) -> str:
    for key in ID_KEYS:
        value = record.get(key)
        if isinstance(value, (str, int)) and str(value).strip():
            return str(value).strip()
    return fallback


def _safe_rel(path: Path, base: Path) -> str:
    try:
        return path.resolve().relative_to(base.resolve()).as_posix()
    except (OSError, ValueError):
        return path.resolve().as_posix()


def _paragraphs(text: str) -> list[dict]:
    """Paragraph/page coordinates are derived only from real form-feed boundaries."""
    pages = str(text or "").split("\f")
    explicit_pages = len(pages) > 1
    rows = []
    serial = 0
    for page_index, page in enumerate(pages, 1):
        # A blank line is a paragraph boundary; single newlines inside a text
        # paragraph are retained so administrative one-line records stay intact.
        chunks = [c for c in re.split(r"(?:\r?\n){2,}", page) if c.strip()]
        for chunk in chunks:
            value = chunk.strip("\r\n")
            # Line-oriented administrative libraries and very long unbroken
            # blocks keep real line coordinates.  Normal prose paragraphs are
            # not split merely because they contain a newline.
            lines = value.splitlines() if len(value) > 4000 or len(chunks) == 1 else [value]
            for line in lines:
                if not line.strip():
                    continue
                serial += 1
                rows.append({"paragraph": serial,
                             "page": page_index if explicit_pages else None,
                             "text": line.strip()})
    return rows


class _HTMLText(html.parser.HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts = []

    def handle_data(self, data):
        if data.strip():
            self.parts.append(data.strip())

    def handle_starttag(self, tag, attrs):
        if tag in {"p", "div", "section", "article", "br", "li", "tr", "h1", "h2", "h3"}:
            self.parts.append("\n\n")


def _pdf_text(path: Path) -> tuple[str, str]:
    exe = shutil.which("pdftotext")
    if not exe:
        raise ValueError("PDF requires the provided pdftotext tool; no text was guessed")
    proc = subprocess.run([exe, "-layout", str(path), "-"], capture_output=True,
                          timeout=90)
    if proc.returncode != 0:
        detail = proc.stderr.decode("utf-8", "replace")[:300]
        raise ValueError("pdftotext could not extract this PDF: " + detail)
    return proc.stdout.decode("utf-8", "replace"), "pdftotext-layout"


def _docx_text(path: Path) -> tuple[str, str]:
    with zipfile.ZipFile(path) as zf:
        raw = zf.read("word/document.xml")
    root = ElementTree.fromstring(raw)
    ns = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
    paras = []
    for p in root.iter(ns + "p"):
        value = "".join(t.text or "" for t in p.iter(ns + "t"))
        if value.strip():
            paras.append(value)
    return "\n\n".join(paras), "docx-document-xml"


def read_material(path: Path) -> tuple[str, str]:
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        return _pdf_text(path)
    if suffix == ".docx":
        return _docx_text(path)
    raw = path.read_bytes()
    text = raw.decode("utf-8-sig")
    if suffix in {".html", ".htm"}:
        parser = _HTMLText()
        parser.feed(text)
        return "".join(parser.parts), "html-text"
    return text, "utf8-text"


def _lookup(context: dict, names) -> object:
    for name in names:
        value = context.get(name)
        if value not in (None, "", [], {}):
            return value
    work = context.get("workorder_data")
    if isinstance(work, dict):
        for name in names:
            value = work.get(name)
            if value not in (None, "", [], {}):
                return value
    return None


def _load_workorder(case: dict, base: Path) -> tuple[dict, list]:
    """Load a declared JSON workorder, never infer facts from its filename."""
    failures = []
    result = dict(case)
    ref = case.get("workorder") or case.get("workorder_path")
    if isinstance(ref, dict):
        result["workorder_data"] = ref
        return result, failures
    if isinstance(ref, str) and ref.strip():
        path = Path(ref)
        if not path.is_absolute():
            path = base / path
        try:
            data = json.loads(path.read_text(encoding="utf-8-sig"))
            if isinstance(data, dict):
                result["workorder_data"] = data
            else:
                failures.append({"rule": "kbqa.workorder_not_object", "path": str(path)})
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            failures.append({"rule": "kbqa.workorder_unreadable", "path": str(path),
                             "reason": str(exc)[:300]})
    return result, failures


def extract_questions(context: dict) -> list[dict]:
    value = _lookup(context, QUESTION_KEYS)
    if isinstance(value, dict):
        value = value.get("questions") or value.get("queries") or value.get("items") or [value]
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, list):
        return []
    out = []
    for i, item in enumerate(value, 1):
        if isinstance(item, str) and item.strip():
            out.append({"question_id": f"q{i:03d}", "question": item.strip(),
                        "subquestions": []})
        elif isinstance(item, dict):
            question = (item.get("question") or item.get("query") or item.get("search")
                        or item.get("text") or item.get("prompt"))
            if not isinstance(question, str) or not question.strip():
                continue
            qid = item.get("question_id") or item.get("id") or f"q{i:03d}"
            subs = item.get("subquestions") or item.get("sub_queries") or []
            if isinstance(subs, str):
                subs = [subs]
            subs = [s.strip() for s in subs if isinstance(s, str) and s.strip()]
            out.append({"question_id": str(qid), "question": question.strip(),
                        "subquestions": subs})
    return out


def _record_paths(context: dict) -> list:
    value = _lookup(context, DOC_KEYS)
    if value is None:
        return []
    if isinstance(value, dict):
        # A dict of doc-id -> text/record is a common library representation.
        if any(k in value for k in PATH_KEYS + TEXT_KEYS):
            return [value]
        rows = []
        for key in ("documents", "materials", "files", "records", "items"):
            if isinstance(value.get(key), list):
                return value[key]
        for key, item in value.items():
            if isinstance(item, dict):
                rows.append(dict(item, document_id=item.get("document_id") or key))
            elif isinstance(item, str):
                rows.append({"document_id": key, "text": item})
        return rows
    if isinstance(value, (str, Path)):
        return [value]
    return value if isinstance(value, list) else []


def _aliases(context: dict) -> dict:
    value = _lookup(context, ("aliases", "query_aliases", "synonyms"))
    out = {}
    if isinstance(value, dict):
        for canonical, values in value.items():
            if not isinstance(canonical, str):
                continue
            vals = values if isinstance(values, list) else [values]
            vals = [v for v in vals if isinstance(v, str) and v.strip()]
            out[canonical] = [canonical.strip()] + [v.strip() for v in vals]
    return out


def _resolve(path_value: str, base: Path, material_root: Path | None) -> Path:
    path = Path(path_value)
    if path.is_absolute():
        return path
    if material_root is not None:
        candidate = material_root / path
        if candidate.exists():
            return candidate
    return base / path


def _discover(base: Path) -> list[Path]:
    rows = []
    if not base.is_dir():
        return rows
    for root, dirs, files in os.walk(base):
        dirs[:] = sorted(d for d in dirs if not d.startswith(".") and d not in
                         {"output", "outputs", "__pycache__", "node_modules", "venv", ".git"})
        for name in sorted(files):
            path = Path(root) / name
            if name.lower() in SKIP_NAMES or path.suffix.lower() not in DOC_SUFFIXES:
                continue
            rows.append(path)
            if len(rows) >= 500:
                return rows
    return sorted(rows, key=lambda p: p.as_posix())


def inventory(context, base, material_root):
    """Read each declared real source once and retain its paragraph coordinates."""
    base = Path(base).resolve()
    material_root = Path(material_root).resolve() if material_root else None
    records = _record_paths(context)
    workorder_data = context.get("workorder_data")
    records_declared = any(key in context or
                           (isinstance(workorder_data, dict) and key in workorder_data)
                           for key in DOC_KEYS)
    failures = list(context.get("_workorder_failures") or [])
    trace = [{"seq": 1, "action": "inventory_started",
              "detail": "declared materials; no labels are treated as evidence"}]
    resolved = []
    for i, item in enumerate(records, 1):
        if isinstance(item, dict):
            rec = dict(item)
        elif isinstance(item, (str, Path)):
            rec = {"path": str(item)}
        else:
            failures.append({"rule": "kbqa.record_not_object", "index": i - 1})
            continue
        rec["document_id"] = _source_id(rec, f"doc-{i:03d}")
        inline = next((rec[k] for k in TEXT_KEYS if isinstance(rec.get(k), str) and rec[k].strip()), None)
        if inline is not None:
            resolved.append(("inline", rec, inline, "case-inline"))
            continue
        value = next((rec.get(k) for k in PATH_KEYS if isinstance(rec.get(k), (str, Path)) and str(rec.get(k)).strip()), None)
        if value is None:
            failures.append({"rule": "kbqa.document_has_no_content", "document_id": rec["document_id"]})
            continue
        resolved.append(("path", rec, _resolve(str(value), base, material_root), None))
    if not records and not records_declared:
        root = material_root or base
        declared_root = _lookup(context, ("material_root", "library_root", "root", "directory"))
        if isinstance(declared_root, str) and declared_root.strip():
            root = _resolve(declared_root, base, material_root)
        paths = _discover(root)
        trace.append({"seq": 2, "action": "directory_discovered", "root": str(root),
                      "candidate_files": len(paths)})
        resolved.extend(("path", {"document_id": _safe_rel(p, root)}, p, None) for p in paths)

    public, paragraphs_by_id, seen = [], {}, set()
    for i, (kind, rec, value, extraction) in enumerate(resolved, 1):
        doc_id = str(rec.get("document_id") or f"doc-{i:03d}")
        declared_id = doc_id
        suffix = 2
        while doc_id in paragraphs_by_id:
            doc_id = f"{declared_id}~{suffix}"
            suffix += 1
        if doc_id != declared_id:
            failures.append({"rule": "kbqa.duplicate_document_id", "document_id": declared_id,
                             "assigned_document_id": doc_id,
                             "recovery": "declare unique document ids; no paragraph evidence was overwritten"})
        source_path = None
        try:
            raw_hash = size = None
            if kind == "path":
                path = Path(value)
                if path.is_dir():
                    failures.append({"rule": "kbqa.path_is_directory", "document_id": doc_id,
                                     "path": str(path)})
                    continue
                marker = str(path.resolve())
                if marker in seen:
                    continue
                seen.add(marker)
                source_path = _safe_rel(path, base)
                raw = path.read_bytes()
                raw_hash, size = _sha(raw), len(raw)
                text, extraction = read_material(path)
            else:
                text = str(value)
            paras = _paragraphs(text)
            if not paras:
                failures.append({"rule": "kbqa.no_searchable_text", "document_id": doc_id,
                                 "path": source_path})
                continue
            text_hash = _sha(text)
            public.append({
                "document_id": doc_id,
                "title": rec.get("title") if isinstance(rec.get("title"), str) else None,
                "path": source_path, "directory": str(Path(source_path).parent) if source_path else None,
                "file_type": Path(source_path).suffix.lower() if source_path else "inline",
                "bytes": size, "sha256": raw_hash or text_hash, "text_sha256": text_hash,
                "version": rec.get("version") or rec.get("material_version"),
                "supersedes": rec.get("supersedes"),
                "aliases": rec.get("aliases") if isinstance(rec.get("aliases"), list) else [],
                "metadata": rec.get("metadata") if isinstance(rec.get("metadata"), dict) else {},
                "source": rec.get("source") or rec.get("origin"),
                "permissions": "read" if kind == "path" else "inline",
                "extraction": extraction, "paragraph_count": len(paras), "pages_with_coordinates": sum(1 for p in paras if p["page"] is not None),
            })
            if doc_id != declared_id:
                public[-1]["declared_document_id"] = declared_id
            paragraphs_by_id[doc_id] = paras
        except (OSError, UnicodeDecodeError, ValueError, TypeError, zipfile.BadZipFile,
                ElementTree.ParseError, subprocess.SubprocessError) as exc:
            failures.append({"rule": "kbqa.document_unreadable", "document_id": doc_id,
                             "path": source_path or str(value), "reason": str(exc)[:400]})
    order = sorted(range(len(public)), key=lambda i: public[i]["document_id"])
    public = [public[i] for i in order]
    paragraphs_by_id = {d["document_id"]: paragraphs_by_id[d["document_id"]] for d in public}
    by_hash = {}
    for doc in public:
        by_hash.setdefault(doc["sha256"], []).append(doc["document_id"])
    for doc in public:
        doc["duplicate_of"] = sorted(x for x in by_hash[doc["sha256"]] if x != doc["document_id"])
    trace.append({"seq": len(trace) + 1, "action": "inventory_finished",
                  "readable_documents": len(public), "failures": len(failures)})
    return public, paragraphs_by_id, failures, trace


class Retriever:
    def __init__(self, documents, paragraphs_by_id, aliases=None):
        self.documents = documents
        self.doc_by_id = {d["document_id"]: d for d in documents}
        self.aliases = aliases or {}
        self.paragraphs = []
        seen_duplicate_text = set()
        for doc in documents:
            # Exact duplicate files are visible in inventory but searched once.
            if doc["duplicate_of"] and doc["document_id"] != min([doc["document_id"]] + doc["duplicate_of"]):
                continue
            for para in paragraphs_by_id[doc["document_id"]]:
                marker = (doc["text_sha256"], para["paragraph"], para["text"])
                if marker in seen_duplicate_text:
                    continue
                seen_duplicate_text.add(marker)
                row = dict(para)
                row["document_id"] = doc["document_id"]
                row["tokens"] = tokens(para["text"])
                self.paragraphs.append(row)
        self.df = Counter()
        for p in self.paragraphs:
            self.df.update(set(p["tokens"]))
        self.n = len(self.paragraphs)
        self.avg_len = (sum(len(p["tokens"]) for p in self.paragraphs) / self.n) if self.n else 1.0

    def variants(self, query: str) -> list[str]:
        out = [query.strip()]
        norm = _norm(query)
        bridges = [word for cue, words in sorted(QUERY_BRIDGES.items()) if cue in query
                   for word in words]
        if bridges:
            # A separate translated query avoids diluting lexical coverage with
            # terms in two scripts.  The source text itself is never translated.
            out.append(" ".join(bridges))
        for canonical, vals in sorted(self.aliases.items()):
            hits = [v for v in vals if _norm(v) and _norm(v) in norm]
            if hits and canonical.strip():
                expanded = query + " " + canonical + " " + " ".join(hits)
                if _norm(expanded) not in {_norm(x) for x in out}:
                    out.append(expanded)
        return out

    def _idf(self, token):
        return math.log(1.0 + (self.n - self.df.get(token, 0) + 0.5) / (self.df.get(token, 0) + 0.5))

    def search_one(self, query: str) -> tuple[list, dict]:
        qt = tokens(query, query=True)
        # Keep domain terms even when every document mentions them.  BM25/IDF
        # already down-weights common terms; deleting them breaks small corpora
        # and two-version questions where “样品/文件” is precisely the subject.
        qset = set(qt)
        scored = []
        for p in self.paragraphs:
            pt = set(p["tokens"])
            shared = qset & pt
            if not shared:
                continue
            tf = Counter(p["tokens"])
            bm = 0.0
            for t in shared:
                denom = tf[t] + 1.2 * (0.25 + 0.75 * len(p["tokens"]) / max(1.0, self.avg_len))
                bm += self._idf(t) * tf[t] * 2.2 / max(0.001, denom)
            coverage = len(shared) / max(1, len(qset))
            phrase = 1.0 if len(_norm(query)) >= 2 and _norm(query) in _norm(p["text"]) else 0.0
            score = bm + 2.5 * coverage + 2.0 * phrase
            scored.append((score, coverage, len(shared), p, sorted(shared, key=lambda t: (-self._idf(t), t))))
        scored.sort(key=lambda x: (-x[0], x[3]["document_id"], x[3]["paragraph"]))
        return scored, {"query_tokens": sorted(qset), "variant": query}

    def retrieve(self, hop_query: str, full_query: str, top_k: int = 8) -> dict:
        variants = [(hop_query, 1.0)]
        if _norm(full_query) != _norm(hop_query):
            variants.append((full_query, 0.55))
        for variant in self.variants(hop_query)[1:]:
            variants.append((variant, 0.85))
        fused = {}
        plans = []
        for query, weight in variants:
            scored, plan = self.search_one(query)
            plans.append(plan)
            for rank, (raw, coverage, shared_n, p, shared) in enumerate(scored[:20], 1):
                key = (p["document_id"], p["paragraph"])
                entry = fused.setdefault(key, {"paragraph": p, "rrf": 0.0, "best_raw": 0.0,
                                               "coverage": 0.0, "matched_terms": set(),
                                               "variants": []})
                entry["rrf"] += weight / (60.0 + rank)
                entry["best_raw"] = max(entry["best_raw"], raw)
                entry["coverage"] = max(entry["coverage"], coverage)
                entry["matched_terms"].update(shared)
                entry["variants"].append(query)
        hits = list(fused.values())
        for h in hits:
            # A bounded 0..1 quality accompanies RRF so abstention never depends
            # on corpus size.  One specific bigram/word can ground a lookup;
            # broad multi-aspect questions need proportionally more coverage.
            h["quality"] = min(1.0, 0.72 * h["coverage"] + 0.28 * h["best_raw"] / (h["best_raw"] + 4.0))
            h["matched_terms"] = sorted(h["matched_terms"])
            h["variants"] = sorted(set(h["variants"]))
        hits.sort(key=lambda h: (-h["rrf"], h["paragraph"]["document_id"], h["paragraph"]["paragraph"]))
        return {"hits": hits[:top_k], "query_variants": plans}


def query_plan(question: dict) -> list[dict]:
    text = question["question"]
    explicit = question.get("subquestions") or []
    if explicit:
        parts = explicit
    else:
        parts = []
        if MULTI_CUE.search(text) and ("，" in text or "," in text or "；" in text or ";" in text):
            parts = [p.strip(" ，,；;。?？") for p in re.split(r"[，,；;]", text) if p.strip(" ，,；;。?？")]
            parts = [p for p in parts if len(tokens(p, query=True)) >= 1]
            if len(parts) < 2:
                parts = []
    if not parts:
        parts = [text]
    # The original is retained as a context variant, while each hop is answered
    # and reported independently.  No subquestion can silently disappear.
    return [{"hop": i, "query": part, "depends_on": i - 1 if i > 1 else None,
             "role": "decomposed_subquestion" if len(parts) > 1 else "single_lookup"}
            for i, part in enumerate(parts[:6], 1)]


def _sentences(paragraph_text: str) -> list[dict]:
    text = str(paragraph_text)
    spans = []
    start = 0
    # Chinese terminators and newlines are unambiguous.  English full stops are
    # treated as boundaries only before whitespace+capital/digit, avoiding most
    # abbreviations and decimal points.
    pattern = re.compile(r"[。！？；]+|\n+|(?<=[.!?])\s+(?=[A-Z0-9])")
    for match in pattern.finditer(text):
        end = match.end()
        piece = text[start:end]
        if piece.strip():
            left = len(piece) - len(piece.lstrip())
            right = len(piece.rstrip())
            spans.append({"text": piece.strip(), "start": start + left, "end": start + right})
        start = end
    piece = text[start:]
    if piece.strip():
        left = len(piece) - len(piece.lstrip())
        spans.append({"text": piece.strip(), "start": start + left, "end": len(piece.rstrip())})
    return spans or [{"text": text.strip(), "start": 0, "end": len(text.rstrip())}]


def _best_sentence(hit, query):
    p = hit["paragraph"]
    candidates = _sentences(p["text"])
    qt = set(tokens(query, query=True))
    best = None
    for sent in candidates:
        shared = qt & set(tokens(sent["text"]))
        score = len(shared) * 3 + (4 if _norm(query) and _norm(query) in _norm(sent["text"]) else 0)
        # Prefer the source sentence carrying the matched query terms; ties use
        # source order, never random or wall-clock state.
        key = (score, len(shared), -sent["start"])
        if best is None or key > best[0]:
            best = (key, sent, sorted(shared))
    sent = best[1]
    evidence = {
        "evidence_id": "ev-" + _sha(p["document_id"] + "|" + str(p["paragraph"]) + "|" + sent["text"])[:12],
        "document_id": p["document_id"],
        "quote": sent["text"],
        "paragraph_text": p["text"],
        "locator": {"document_id": p["document_id"], "page": p["page"],
                    "paragraph": p["paragraph"], "char_start": sent["start"],
                    "char_end": sent["end"]},
        "matched_terms": hit["matched_terms"], "retrieval": {"rrf": round(hit["rrf"], 8),
        "quality": round(hit["quality"], 6), "variants": hit["variants"]},
    }
    return evidence


def _numeric_signature(text):
    return tuple(sorted(set(_norm(x).replace(" ", "") for x in NUMBER.findall(str(text)))))


def _conflicts(hits, chosen, query):
    """Surface possible numeric disagreement; never declare a semantic winner."""
    if not chosen:
        return []
    qset = set(tokens(query, query=True))
    base = chosen[0]
    base_sig = _numeric_signature(base["quote"])
    if not base_sig:
        return []
    out = []
    for hit in hits[1:5]:
        candidate = _best_sentence(hit, query)
        if candidate["evidence_id"] == base["evidence_id"]:
            continue
        sig = _numeric_signature(candidate["quote"])
        if not sig or sig == base_sig:
            continue
        shared = qset & set(tokens(candidate["quote"]))
        if len(shared) < max(1, min(2, len(qset))):
            continue
        # Different numbers in a close retrieval set are a conflict CANDIDATE,
        # surfaced with both exact passages; there is no automatic averaging or
        # version guess.  A user-supplied supersedes relation stays metadata.
        out.append({"kind": "possible_numeric_conflict", "query": query,
                    "evidence": [base, candidate], "numeric_values": [list(base_sig), list(sig)],
                    "resolution": "unresolved; both source locators are supplied"})
        break
    return out


def answer_question(question, retriever: Retriever) -> tuple[dict, list, list]:
    plan = query_plan(question)
    claims, gaps, confs, hop_results = [], [], [], []
    all_evidence = {}
    for hop in plan:
        found = retriever.retrieve(hop["query"], question["question"])
        hits = found["hits"]
        # Abstention gate: weak overlap with a long question is not evidence.
        # For a one-token specific lookup, a single exact CJK bigram is enough.
        qtokens = tokens(hop["query"], query=True)
        threshold = 0.30 if len(qtokens) <= 2 else 0.24
        supported = [h for h in hits if h["coverage"] >= (0.45 if len(qtokens) <= 2 else 0.16)
                     and h["quality"] >= threshold]
        selected = supported[:1]
        if re.search(r"哪些|所有|列出|清单|对比|比较|分别|多文件|各文件|files\b|compare|list", hop["query"], re.I):
            for h in supported[1:4]:
                if h["quality"] < 0.36:
                    continue
                doc_id = h["paragraph"]["document_id"]
                if not selected or all(doc_id != old["paragraph"]["document_id"] for old in selected):
                    selected.append(h)
        if not selected:
            gaps.append({"hop": hop["hop"], "subquestion": hop["query"],
                         "reason": "未检索到达到支撑阈值的段落级证据",
                         "missing": "包含该子问题关键实体与关系/数值的可读原文段落"})
            hop_results.append(dict(hop, status="insufficient_evidence", evidence_ids=[],
                                    retrieval_variants=found["query_variants"]))
            continue
        ev = [_best_sentence(h, hop["query"]) for h in selected]
        for item in ev:
            all_evidence[item["evidence_id"]] = item
        conflicts = _conflicts(supported, ev, hop["query"])
        for conflict in conflicts:
            for item in conflict["evidence"]:
                all_evidence[item["evidence_id"]] = item
            confs.append(conflict)
        for item in ev:
            claims.append({"text": item["quote"], "kind": "reported",
                           "cites": [item["evidence_id"]], "locators": [item["locator"]],
                           "hop": hop["hop"]})
        hop_results.append(dict(hop, status="conflicted" if conflicts else "answered",
                                evidence_ids=[e["evidence_id"] for e in ev],
                                retrieval_variants=found["query_variants"]))
    if not claims:
        status = "insufficient_evidence"
        answer = "根据当前可读取的知识库，无法回答：未找到足以支撑该问题的原文段落。"
    elif gaps or confs:
        status = "partial" if gaps else "conflicted"
        answer = " ".join(c["text"] + " [" + c["cites"][0] + "]" for c in claims)
    else:
        status = "answered"
        answer = " ".join(c["text"] + " [" + c["cites"][0] + "]" for c in claims)
    answer_record = {
        "question_id": question["question_id"], "question": question["question"],
        "status": status, "answer": answer, "answer_kind": "extractive" if claims else "explicit_unknown",
        "claims": claims, "answer_sentences": claims, "gaps": gaps,
        "query_plan": hop_results,
        "coverage": {"subquestions": len(plan), "answered": sum(1 for h in hop_results if h["status"] != "insufficient_evidence"),
                     "unanswered": sum(1 for h in hop_results if h["status"] == "insufficient_evidence")},
    }
    return answer_record, list(all_evidence.values()), confs


def _verify_answers(result, paragraphs_by_id):
    problems = []
    evidence = {e["evidence_id"]: e for r in result.get("answers", []) for e in r.get("_evidence", [])}
    # Evidence is globally pooled by run_case before this check.
    evidence = {e["evidence_id"]: e for e in result.get("evidence", [])}
    claim_count = 0
    for answer in result.get("answers", []):
        for claim in answer.get("claims", []):
            claim_count += 1
            if not claim.get("cites") or not claim.get("locators"):
                problems.append({"rule": "kbqa.claim_without_locator", "question_id": answer["question_id"]})
                continue
            ev = evidence.get(claim["cites"][0])
            if ev is None:
                problems.append({"rule": "kbqa.unknown_evidence", "question_id": answer["question_id"]})
                continue
            loc = claim["locators"][0]
            paras = paragraphs_by_id.get(loc["document_id"], [])
            para = next((p for p in paras if p["paragraph"] == loc["paragraph"]), None)
            if para is None or para["text"][loc["char_start"]:loc["char_end"]] != claim["text"]:
                problems.append({"rule": "kbqa.quote_anchor_mismatch", "question_id": answer["question_id"],
                                 "evidence_id": ev["evidence_id"]})
            if ev["quote"] != claim["text"]:
                problems.append({"rule": "kbqa.claim_quote_mismatch", "question_id": answer["question_id"]})
    return {"claims_checked": claim_count, "evidence_records": len(evidence),
            "locator_coverage": (claim_count - sum(1 for p in problems if p["rule"] == "kbqa.claim_without_locator")),
            "problems": problems, "ok": not problems}


def _public_evidence(evidence):
    out = []
    for e in evidence:
        row = {k: v for k, v in e.items() if k != "paragraph_text"}
        out.append(row)
    return sorted(out, key=lambda e: e["evidence_id"])


CONTRACT_ALIASES = {
    "answer": "answers", "answers": "answers", "qa": "answers", "questions": "answers",
    "evidence": "evidence", "sources": "evidence", "citations": "evidence",
    "documents": "documents", "files": "documents", "inventory": "documents",
    "conflicts": "conflicts", "uncertainty": "uncertainties", "uncertainties": "uncertainties",
    "logs": "operation_trace", "operation_log": "operation_trace", "operation_trace": "operation_trace",
    "status": "status", "case_id": "case_id", "coverage": "coverage", "limits": "limits",
    "index": "index_path", "report": "report_path", "deliverable": "deliverables",
    "verification": "verification", "query_plan": "query_plans", "retrieval": "query_plans",
}


def complete_contract(result: dict, case: dict) -> None:
    """case_id + every output_contract key, with honest aliases and null limits."""
    result["case_id"] = case.get("case_id", case.get("id"))
    contract = case.get("output_contract")
    if not isinstance(contract, dict):
        if contract is not None:
            result["limits"].append("output_contract was not an object; no contract fields could be mapped")
        return
    for key, spec in contract.items():
        if key in result:
            continue
        alias = CONTRACT_ALIASES.get(key) or CONTRACT_ALIASES.get(key.lower())
        if key in case and key not in BULKY_CASE_KEYS:
            value = case[key]
            if isinstance(value, (str, int, float, bool)) or value is None:
                result[key] = value
            else:
                # Small structured case values are real metadata, not material.
                encoded = _json(value)
                result[key] = value if len(encoded) <= 50000 else None
                if result[key] is None:
                    result["limits"].append(f"contract field '{key}' source value exceeded the safe echo limit")
        elif isinstance(spec, (str, int, float, bool)):
            # Literal contract values are passthrough metadata, not aliases.
            result[key] = spec
        elif alias and alias in result:
            result[key] = result[alias]
        else:
            result[key] = None
            result["limits"].append(f"output_contract field '{key}' has no evidence-backed value; null is intentional")


def run_case(case: dict, base_dir, out_dir, material_root=None) -> dict:
    base = Path(base_dir)
    out = Path(out_dir)
    context, work_failures = _load_workorder(case, base)
    context["_workorder_failures"] = work_failures
    docs, para_map, failures, trace = inventory(context, base, material_root)
    questions = extract_questions(context)
    answers, evidence_all, conflicts, uncertainties = [], {}, [], []
    retriever = Retriever(docs, para_map, _aliases(context))
    for question in questions:
        answer, evs, confs = answer_question(question, retriever)
        answers.append(answer)
        for ev in evs:
            evidence_all[ev["evidence_id"]] = ev
        conflicts.extend(confs)
        for gap in answer["gaps"]:
            uncertainties.append({"question_id": answer["question_id"], "kind": "insufficient_evidence",
                                  "detail": gap})
        for conf in confs:
            uncertainties.append({"question_id": answer["question_id"], "kind": "possible_numeric_conflict",
                                  "detail": conf["resolution"]})
    evidence = sorted(evidence_all.values(), key=lambda e: e["evidence_id"])
    versions = [{"document_id": d["document_id"], "version": d["version"],
                 "supersedes": d["supersedes"], "aliases": d["aliases"],
                 "duplicate_of": d["duplicate_of"], "sha256": d["sha256"]}
                for d in docs if d["version"] is not None or d["supersedes"] or d["duplicate_of"] or d["aliases"]]
    counts = Counter(a["status"] for a in answers)
    if not docs:
        status = "undetermined"
        status_reason = "no readable/searchable document was available"
    elif not questions:
        status = "undetermined"
        status_reason = "no structured question/query was available in case.json or its declared workorder"
    else:
        status = "partial" if failures else "done"
        status_reason = "some declared materials could not be read" if failures else "all questions were processed; explicit unknowns are answers with insufficient evidence"
    coverage = {"questions": len(answers),
                "answered": counts.get("answered", 0), "partial": counts.get("partial", 0),
                "conflicted": counts.get("conflicted", 0),
                "insufficient_evidence": counts.get("insufficient_evidence", 0),
                "subquestions": sum(a["coverage"]["subquestions"] for a in answers),
                "unanswered_subquestions": sum(a["coverage"]["unanswered"] for a in answers)}
    limits = []
    if failures:
        limits.append("one or more declared materials were not searchable; see failures and recovery")
    if counts.get("insufficient_evidence"):
        limits.append("some questions have no supporting passage in the readable corpus; no external facts were added")
    if conflicts:
        limits.append("possible numeric conflicts are presented with both locators and no automatic winner")
    result = {
        "schema_version": SCHEMA, "status": status, "status_reason": status_reason,
        "deliverables": ["result.json", "answers.json", "answers.md", "kb_index.json", "operation_log.json"],
        "documents": docs, "versions": versions, "answers": answers,
        "evidence": _public_evidence(evidence), "conflicts": [
            {**c, "evidence": _public_evidence(c["evidence"])} for c in conflicts],
        "coverage": coverage, "query_plans": [
            {"question_id": a["question_id"], "hops": a["query_plan"]} for a in answers],
        "uncertainties": uncertainties, "failures": failures, "limits": limits,
        "operation_trace": trace + [{"seq": len(trace) + i + 1, "action": "question_processed",
                                      "question_id": a["question_id"], "status": a["status"],
                                      "hops": a["coverage"]["subquestions"]} for i, a in enumerate(answers)],
        "index_path": "kb_index.json", "report_path": "answers.md", "verification": {},
    }
    result["verification"] = _verify_answers(result, para_map)
    complete_contract(result, case)
    if not result["verification"]["ok"]:
        result["status"] = "undetermined"
        result["status_reason"] = "internal evidence verification failed; answers must not be delivered as verified"
        result["limits"].append("one or more generated claims failed source-anchor verification")
    _write_outputs(out, result, docs, para_map)
    return result


def _write_outputs(out: Path, result, docs, para_map) -> None:
    out.mkdir(parents=True, exist_ok=True)
    answers_payload = {"schema_version": SCHEMA, "case_id": result.get("case_id"),
                       "answers": result["answers"], "evidence": result["evidence"],
                       "conflicts": result["conflicts"]}
    (out / "answers.json").write_text(json.dumps(answers_payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    lines = ["# Knowledge-base answers", "",
             "Factual sentences below are verbatim source extracts. Bracketed evidence ids resolve in result.json.", ""]
    for a in result["answers"]:
        lines.extend([f"## {a['question_id']}: {a['question']}", f"status: {a['status']}", "", a["answer"], ""])
        for claim in a["claims"]:
            loc = claim["locators"][0]
            where = f"{loc['document_id']} ¶{loc['paragraph']}"
            if loc["page"] is not None:
                where += f" page {loc['page']}"
            where += f" chars {loc['char_start']}–{loc['char_end']}"
            lines.append(f"- [{claim['cites'][0]}] {where}")
        for gap in a["gaps"]:
            lines.append(f"- GAP hop {gap['hop']}: {gap['reason']}; missing: {gap['missing']}")
        lines.append("")
    (out / "answers.md").write_text("\n".join(lines), encoding="utf-8")
    index_docs = []
    for doc in docs:
        row = dict(doc)
        row["paragraphs"] = para_map[doc["document_id"]]
        index_docs.append(row)
    (out / "kb_index.json").write_text(json.dumps({"schema_version": SCHEMA, "documents": index_docs},
        ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    (out / "operation_log.json").write_text(json.dumps({"schema_version": SCHEMA,
        "operations": result["operation_trace"], "failures": result["failures"]},
        ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    (out / "result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")


def verify_export(out_dir) -> dict:
    """Independent cold verification of exported quotes and locators."""
    out = Path(out_dir)
    try:
        result = json.loads((out / "result.json").read_text(encoding="utf-8"))
        index = json.loads((out / "kb_index.json").read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        return {"ok": False, "findings": [{"rule": "kbqa.export_unreadable", "reason": str(exc)}]}
    para_map = {d.get("document_id"): d.get("paragraphs", []) for d in index.get("documents", []) if isinstance(d, dict)}
    verification = _verify_answers(result, para_map)
    return {"ok": verification["ok"], "claims_checked": verification["claims_checked"],
            "findings": verification["problems"]}
