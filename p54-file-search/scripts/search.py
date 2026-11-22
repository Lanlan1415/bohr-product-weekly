"""An index+query engine over a corpus of research documents.

The organising brief names the regular failures: the answer is a whole file
where a section was asked for; citations carry no page or version so nobody can
re-check them; one hit is treated as a conclusion; filters are silently
relaxed until something "hits"; renamed copies are treated as independent
evidence; and after a failure nobody can tell whether the file was never
indexed. This engine is built against those:

  检索可复现   every result records the normalised query (terms AND filters)
              and the index fingerprint (sha256 over the exact indexed texts),
              and the index itself is written beside the result — the same
              corpus + query re-runs byte-identical, and anyone can replay the
              query against the recorded index
  命中带定位   every hit carries passages, and every passage carries a locator
              (document id, document sha256, paragraph index, enclosing section
              title, character range) whose quote is a verbatim slice of the
              indexed text — quote == text[start:end] is checkable by anyone
              holding the corpus, and the section title puts the hit at
              章节级 granularity, not whole-file
  空结果诚实   a query nothing matches returns an empty hit list with a note
              (naming the filters when filters were declared); a miss is
              reported as a miss, never padded, never widened
  布尔与过滤硬执行   all-terms is a hard constraint, any-terms an alternative
              set, both given both must hold; declared metadata filters (year,
              project, type, batch...) must every one match a document's meta —
              a document missing the key never matches, an unsatisfiable
              filter yields an honest empty result, and a malformed filter is
              refused rather than silently dropped. Identical texts under two
              doc ids are named as duplicate content so a renamed copy can
              never pass as a second piece of evidence

Refusals are honest too: an empty corpus, a malformed index, an empty query and
a malformed filter are refused with named rules — the engine never searches a
partial or guessed index, and never runs with quietly-ignored constraints. No
wall-clock fields are written, so the same run is byte-identical.
"""

from __future__ import annotations

import hashlib
import json
import re

SCHEMA_VERSION = "file-search/v1"

_STOP = {"the", "and", "for", "with", "this", "that", "from", "are", "was",
         "他们的", "我们", "因此", "但是", "然后"}

_LATIN_WORD = re.compile(r"[A-Za-z][A-Za-z0-9_-]{1,}")
_CJK_RUN = re.compile(r"[\u4e00-\u9fff]{2,}")

# A heading line starts a section: markdown hashes, numbered headings
# ("1 缓冲液配制", "2.3 样品制备"), Chinese numbered headings ("二、方法"),
# or a "第X章/节" line. The convention is one paragraph per non-empty line.
_HEADING = re.compile(
    r"^\s{0,4}(#{1,6}\s+\S.*"
    r"|\d+(?:\.\d+)*[、.．]?\s+\S.*"
    r"|[一二三四五六七八九十百]+[、.．]\s*\S.*"
    r"|第[一二三四五六七八九十百0-9]+[章节部分讲][\s、.．:：]?\s*\S.*)$")


def is_heading(line: str) -> bool:
    """A heading line: markdown hashes / 第X章 / Chinese-ordinal / digit-numbered.
    Digit-numbered lines must be short (<= 60 chars) and must not end with
    sentence punctuation — "2 存 储" is a heading, "2023 年 3 月 我们测了…" is
    a sentence that happens to start with a number."""
    s = str(line or "").strip()
    if not s or len(s) > 120 or not _HEADING.match(s):
        return False
    if s.startswith("#") or s.startswith("第"):
        return True
    return len(s) <= 60 and not re.search(r"[。！？.!?；;]$", s)


def section_map(paragraphs: list) -> dict:
    """Map each paragraph index to its enclosing section title. A heading line
    belongs to its own section; paragraphs after it inherit the most recent
    heading. Documents with no headings map every paragraph to None."""
    out: dict = {}
    current = None
    for i, para in enumerate(paragraphs):
        if is_heading(para):
            current = para.strip()
        out[i] = current
    return out


def _refusal(rule: str, message: str) -> dict:
    """The bare refusal payload: {rule, message}. Helpers wrap it under
    "refusal"; search() lifts it into a full refusal result."""
    return {"rule": rule, "message": message}


def _refusal_result(rule: str, message: str) -> dict:
    """A full refusal result — a refusal is a result, not a crash."""
    return {"schema_version": SCHEMA_VERSION, "status": "undetermined",
            "refusal": _refusal(rule, message),
            "limits": ["no query was answered"]}


def _lift(bare_refusal: dict) -> dict:
    return _refusal_result(bare_refusal["rule"], bare_refusal["message"])


def key_terms(text: str, min_len: int = 2) -> list:
    """Content terms of a text: latin words + CJK bigrams (the p45 logic)."""
    s = str(text or "")
    latin = re.findall(r"[A-Za-z][A-Za-z0-9_-]{%d,}" % (min_len - 1), s)
    cjk = re.findall(r"[\u4e00-\u9fff]{%d,}" % max(min_len, 2), s)
    grams: set = set(latin)
    for run in cjk:
        n = max(min_len, 2)
        grams.update(run[i:i + n] for i in range(len(run) - n + 1))
    return sorted(g for g in grams if g.lower() not in _STOP)


def query_terms(q: str) -> list:
    """Terms of a bare-string query: latin words plus whole CJK runs (a CJK
    phrase stays one searchable term instead of being split into bigrams)."""
    s = str(q or "")
    terms = {t.lower() for t in _LATIN_WORD.findall(s)}
    terms |= set(_CJK_RUN.findall(s))
    return sorted(terms)


def parse_query(query):
    """Normalise a query into {"all": [...], "any": [...], "filters": {...}} or
    refuse.

    A bare string becomes an any-of query over its terms. A query that declares
    nothing searchable is refused: searching nothing would fabricate a result.
    Declared metadata filters are validated here — a filter that is not an
    object, or whose values are not scalars, is a refusal (search.filter_invalid)
    rather than a constraint that is quietly dropped: silently widening the
    filter is exactly the failure the brief names.
    """
    filters: dict = {}
    if isinstance(query, dict):
        raw_f = query.get("filters")
        if raw_f is not None:
            if not isinstance(raw_f, dict):
                return None, _refusal(
                    "search.filter_invalid",
                    "query.filters must be an object of scalar constraints, not "
                    + type(raw_f).__name__)
            for k, v in raw_f.items():
                if not isinstance(v, (str, int, float, bool)) or v is None:
                    return None, _refusal(
                        "search.filter_invalid",
                        "query.filters value for '" + str(k) + "' is not a scalar "
                        "constraint; refusing rather than dropping the condition")
                filters[str(k)] = v

    if isinstance(query, str):
        terms = query_terms(query)
        if not terms:
            return None, _refusal(
                "search.empty_query",
                "the query contains no searchable term (a latin word or a CJK run of "
                "2+ characters)")
        return {"all": [], "any": terms, "filters": filters}, None
    if isinstance(query, dict):
        def terms_of(key):
            raw = query.get(key)
            if raw is None:
                return []
            if not isinstance(raw, list):
                raw = [raw]
            return [str(t).strip() for t in raw if str(t).strip()]
        all_t, any_t = terms_of("all"), terms_of("any")
        if not all_t and not any_t:
            return None, _refusal(
                "search.empty_query",
                "the query declares neither all nor any terms; there is nothing to "
                "search for")
        return {"all": all_t, "any": any_t, "filters": filters}, None
    return None, _refusal(
        "search.empty_query",
        "the query is neither a string nor an {all, any, filters} object")


def build_index(corpus):
    """Index the corpus: paragraphs, enclosing sections, content terms, a
    per-document sha256 and a corpus fingerprint.

    Returns {"ok": True, "index": ..., "skipped": [...], "duplicates": [...]}
    or {"ok": False, "refusal": ...}. A bare string entry is a document with a
    generated id; an entry that is not a document is skipped and named; a
    duplicate doc id is skipped and named rather than silently merged; two
    entries with identical text under different ids are BOTH indexed and
    reported as duplicate content — a renamed copy must not pass as a second
    piece of evidence.
    """
    if not isinstance(corpus, list):
        return {"ok": False,
                "refusal": _refusal("search.empty_corpus",
                                    "the corpus is missing or not a list of documents")}
    docs: dict = {}
    order: list = []
    skipped: list = []
    meta_warnings: list = []
    seen_ids: set = set()
    for i, entry in enumerate(corpus):
        if isinstance(entry, dict):
            text = entry.get("text")
            if text is None:
                skipped.append({"index": i, "reason": "entry is an object but has no text"})
                continue
            doc_id = str(entry.get("id") or entry.get("doc_id") or "").strip()
            text = str(text)
            meta = entry.get("meta")
            if meta is not None and not isinstance(meta, dict):
                meta_warnings.append(
                    {"index": i, "doc_id": doc_id or "(auto)",
                     "reason": "entry meta is not an object; stored empty — "
                               "filters cannot use it, never guessed"})
                meta = {}
        elif isinstance(entry, str):
            doc_id, text, meta = "", entry, {}
        else:
            skipped.append({"index": i,
                            "reason": "entry is neither an object nor a string: "
                                      + type(entry).__name__})
            continue
        if not doc_id:
            doc_id = "doc-" + str(len(order) + 1).zfill(3)
        if doc_id in seen_ids:
            skipped.append({"index": i,
                            "reason": "duplicate doc id '" + doc_id
                                      + "'; the entry is skipped rather than silently merged"})
            continue
        seen_ids.add(doc_id)
        paragraphs = [p for p in text.split("\n") if p.strip()]
        secs = section_map(paragraphs)
        sections = [{"paragraph": k, "title": v} for k, v in sorted(secs.items())
                    if v is not None and (k == 0 or secs.get(k - 1) != v)]
        docs[doc_id] = {"text": text, "paragraphs": paragraphs,
                        "sections": sections, "terms": key_terms(text),
                        "sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
                        "meta": dict(meta or {})}
        order.append(doc_id)
    if not order:
        detail = "; ".join(str(s["reason"]) for s in skipped[:3])
        return {"ok": False,
                "refusal": _refusal("search.empty_corpus",
                                    "no document could be indexed (corpus empty or every "
                                    "entry skipped" + (": " + detail if detail else "") + ")")}
    # Duplicate content: identical text under two or more doc ids — both stay
    # indexed, and the pair is named so copies are not treated as independent
    # evidence.
    duplicates: list = []
    by_text: dict = {}
    for doc_id in order:
        by_text.setdefault(docs[doc_id]["sha256"], []).append(doc_id)
    for sha, ids in sorted(by_text.items()):
        if len(ids) > 1:
            duplicates.append({"sha256": sha[:16], "doc_ids": sorted(ids),
                               "note": "identical text under several ids; both indexed "
                                       "and named here — a copy is not a second source"})
    canonical = [{"id": k, "text": docs[k]["text"], "meta": docs[k]["meta"]}
                 for k in order]
    index = {
        "schema_version": SCHEMA_VERSION,
        "documents": docs,
        "order": order,
        "corpus_sha256": hashlib.sha256(json.dumps(
            canonical, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest(),
    }
    return {"ok": True, "index": index, "skipped": skipped,
            "meta_warnings": meta_warnings, "duplicates": duplicates}


def _find_occurrences(para: str, term: str, limit: int = 50) -> list:
    """Every (start, end) of term in para, case-insensitive and slice-verified.

    Offsets come from the lowercased copy only when lowercasing preserved the
    length (it does for ordinary characters); otherwise the exact form is used.
    Either way the returned range always brackets a slice of the ORIGINAL
    paragraph, so quote == paragraph[start:end] is checkable.
    """
    out: list = []
    t = str(term or "")
    if not t:
        return out
    low_t, low_p = t.lower(), para.lower()
    start = 0
    if len(low_p) != len(para) or len(low_t) != len(t):
        while len(out) < limit:
            at = para.find(t, start)
            if at < 0:
                break
            out.append((at, at + len(t)))
            start = at + 1
        return out
    while len(out) < limit:
        at = low_p.find(low_t, start)
        if at < 0:
            break
        out.append((at, at + len(t)))
        start = at + 1
    return out


def _passages(paragraphs: list, terms: list, sections: dict,
              max_passages: int = 20) -> list:
    out: list = []
    for i, para in enumerate(paragraphs):
        for t in terms:
            for s, e in _find_occurrences(para, t):
                out.append({"term": t,
                            "locator": {"paragraph": i,
                                        "section": sections.get(i),
                                        "start": s, "end": e,
                                        "quote": para[s:e]}})
                if len(out) >= max_passages:
                    return out
    return out


def _filters_match(meta: dict, filters: dict) -> bool:
    """Every declared filter must equal the document's meta value. A document
    missing the key never matches — an absent field is not a wildcard."""
    for k, v in filters.items():
        if k not in meta:
            return False
        mv = meta[k]
        if mv != v and str(mv) != str(v):
            return False
    return True


def run_query(index, query):
    """Boolean AND/OR plus hard metadata filters over the index; hits carry
    passages with verbatim, section-level locators.

    all: every declared term must appear (hard constraint). any: at least one
    must appear. Both given, both must hold. filters: every declared constraint
    must match the document's meta — executed as declared, never relaxed.
    Score = number of distinct matched terms; ties keep index order. Empty hits
    are honest; the result records the normalised query (terms and filters) and
    the index fingerprint so anyone can replay it.
    """
    if not isinstance(index, dict) or not isinstance(index.get("documents"), dict) \
            or not isinstance(index.get("order"), list):
        return {"ok": False,
                "refusal": _refusal("search.index_malformed",
                                    "the index is not a readable index object (a documents "
                                    "map plus an order list is expected)")}
    for doc_id in index["order"]:
        doc = index["documents"].get(doc_id)
        if not isinstance(doc, dict) or not isinstance(doc.get("paragraphs"), list) \
                or not isinstance(doc.get("text"), str):
            return {"ok": False,
                    "refusal": _refusal("search.index_malformed",
                                        "index entry '" + str(doc_id)
                                        + "' is malformed; refusing rather than searching "
                                          "a partial index")}
    q, err = parse_query(query)
    if err is not None:
        return {"ok": False, "refusal": err}

    hits = []
    for doc_id in index["order"]:
        doc = index["documents"][doc_id]
        low = doc["text"].lower()
        matched_all = all(t.lower() in low for t in q["all"])
        matched_any = (not q["any"]) or any(t.lower() in low for t in q["any"])
        if not (matched_all and matched_any):
            continue
        if q["filters"] and not _filters_match(doc.get("meta") or {}, q["filters"]):
            continue
        matched_terms = sorted({t for t in q["all"] + q["any"] if t.lower() in low})
        passages = _passages(doc["paragraphs"], matched_terms,
                             section_map(doc["paragraphs"]))
        hits.append({"doc_id": doc_id, "doc_sha256": doc.get("sha256", ""),
                     "score": len(matched_terms),
                     "matched_terms": matched_terms, "passages": passages})
    # Stable sort: equal scores keep index order, so ranking is a function of
    # the corpus and the query alone.
    hits.sort(key=lambda h: -h["score"])
    result = {
        "schema_version": SCHEMA_VERSION,
        "ok": True,
        "query": q,
        "index_sha256": str(index.get("corpus_sha256", ""))[:16],
        "documents_indexed": len(index["order"]),
        "hits": hits,
        "empty": not hits,
    }
    if not hits:
        note = ("no document matches the query over " + str(len(index["order"]))
                + " indexed document(s); reported as empty, never padded")
        if q["filters"]:
            note += ("; the declared filters " + json.dumps(q["filters"],
                                                            ensure_ascii=False,
                                                            sort_keys=True)
                     + " matched no document — executed as declared, not relaxed")
        result["note"] = note
    return {"ok": True, "result": result}


def search(spec):
    """Full pass: corpus (or a prebuilt index) + query → (index, result).

    Returns (None, refusal) when the corpus or the query cannot support a run;
    otherwise (index, result) with the result carrying the query record, the
    index fingerprint, honest status (ok when the whole corpus was indexed;
    partial when entries were skipped or warned), and duplicate-content and
    meta-warning findings.
    """
    if not isinstance(spec, dict):
        return None, _refusal_result("search.spec_unreadable",
                                     "the spec is not a JSON object")
    if spec.get("query") is None:
        return None, _refusal_result("search.empty_query", "the spec declares no query")
    if isinstance(spec.get("index"), dict):
        built = {"ok": True, "index": spec["index"], "skipped": [],
                 "meta_warnings": [], "duplicates": []}
    else:
        built = build_index(spec.get("corpus"))
        if not built["ok"]:
            return None, _lift(built["refusal"])
    res = run_query(built["index"], spec["query"])
    if not res["ok"]:
        return None, _lift(res["refusal"])
    result = res["result"]
    # Spec-carried values pass through: a case_id declared on the spec itself
    # is honoured in the result (a case file can also supply it via the CLI
    # --case passthrough, which keeps this value when present). Absent means
    # null — the field is present either way.
    result["case_id"] = spec["case_id"] \
        if isinstance(spec.get("case_id"), (str, int)) else None
    findings = []
    if built.get("skipped"):
        result["skipped"] = built["skipped"]
        findings.append({"rule": "search.doc_skipped", "severity": "low",
                         "count": len(built["skipped"]),
                         "entries": built["skipped"],
                         "why": "these corpus entries could not be indexed; named "
                                "here instead of vanishing"})
    for w in built.get("meta_warnings") or []:
        findings.append({"rule": "search.meta_invalid", "severity": "low",
                         "index": w["index"], "doc_id": w["doc_id"],
                         "why": w["reason"]})
    for dup in built.get("duplicates") or []:
        findings.append({"rule": "search.duplicate_content", "severity": "low",
                         "sha256": dup["sha256"], "doc_ids": dup["doc_ids"],
                         "why": "identical text under several ids: both indexed, and "
                                "the copy is named — do not count it as a second "
                                "piece of evidence"})
    if findings:
        result["findings"] = findings
        result["status"] = "partial"
    else:
        result["status"] = "ok"
    return built["index"], result
