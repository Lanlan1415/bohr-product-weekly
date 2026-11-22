"""An index+query engine over a corpus of research documents.

The organising brief names the regular failures: the answer is a whole file
where a section was asked for; citations carry no page or version so nobody can
re-check them; one hit is treated as a conclusion; an empty result is padded
with something; and after a failure nobody can tell whether the file was never
indexed. This engine is built against those:

  检索可复现   every result records the normalised query and the index
              fingerprint (sha256 over the exact indexed texts), and the index
              itself is written beside the result — the same corpus + query
              re-runs byte-identical, and anyone can replay the query against
              the recorded index
  命中带定位   every hit carries passages, and every passage carries a locator
              (document id, paragraph index, character range) whose quote is a
              verbatim slice of the indexed text — quote == text[start:end] is
              checkable by anyone holding the corpus
  空结果诚实   a query nothing matches returns an empty hit list with a note;
              a miss is reported as a miss, never padded
  布尔硬执行   all-terms is a hard constraint, any-terms is an alternative set;
              both given, both must hold — filter conditions are executed as
              declared, never relaxed to manufacture hits

Refusals are honest too: an empty corpus, a malformed index and an empty query
are refused with named rules — the engine never searches a partial or guessed
index. No wall-clock fields are written, so the same run is byte-identical.
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
    """Normalise a query into {"all": [...], "any": [...]} or refuse.

    A bare string becomes an any-of query over its terms. A query that declares
    nothing searchable is refused: searching nothing would fabricate a result.
    """
    if isinstance(query, str):
        terms = query_terms(query)
        if not terms:
            return None, _refusal(
                "search.empty_query",
                "the query contains no searchable term (a latin word or a CJK run of "
                "2+ characters)")
        return {"all": [], "any": terms}, None
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
        return {"all": all_t, "any": any_t}, None
    return None, _refusal(
        "search.empty_query",
        "the query is neither a string nor an {all, any} object")


def build_index(corpus):
    """Index the corpus: paragraphs, content terms, a corpus fingerprint.

    Returns {"ok": True, "index": ..., "skipped": [...]} or {"ok": False,
    "refusal": ...}. A bare string entry is a document with a generated id;
    an entry that is not a document is skipped and named; a duplicate doc id is
    skipped and named rather than silently merged.
    """
    if not isinstance(corpus, list):
        return {"ok": False,
                "refusal": _refusal("search.empty_corpus",
                                    "the corpus is missing or not a list of documents")}
    docs: dict = {}
    order: list = []
    skipped: list = []
    seen_ids: set = set()
    for i, entry in enumerate(corpus):
        if isinstance(entry, dict):
            text = entry.get("text")
            if text is None:
                skipped.append({"index": i, "reason": "entry is an object but has no text"})
                continue
            doc_id = str(entry.get("id") or entry.get("doc_id") or "").strip()
            text = str(text)
        elif isinstance(entry, str):
            doc_id, text = "", entry
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
        docs[doc_id] = {"text": text, "paragraphs": paragraphs, "terms": key_terms(text)}
        order.append(doc_id)
    if not order:
        detail = "; ".join(str(s["reason"]) for s in skipped[:3])
        return {"ok": False,
                "refusal": _refusal("search.empty_corpus",
                                    "no document could be indexed (corpus empty or every "
                                    "entry skipped" + (": " + detail if detail else "") + ")")}
    canonical = [{"id": k, "text": docs[k]["text"]} for k in order]
    index = {
        "schema_version": SCHEMA_VERSION,
        "documents": docs,
        "order": order,
        "corpus_sha256": hashlib.sha256(json.dumps(
            canonical, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest(),
    }
    return {"ok": True, "index": index, "skipped": skipped}


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


def _passages(paragraphs: list, terms: list, max_passages: int = 20) -> list:
    out: list = []
    for i, para in enumerate(paragraphs):
        for t in terms:
            for s, e in _find_occurrences(para, t):
                out.append({"term": t,
                            "locator": {"paragraph": i, "start": s, "end": e,
                                        "quote": para[s:e]}})
                if len(out) >= max_passages:
                    return out
    return out


def run_query(index, query):
    """Boolean AND/OR over the index; hits carry passages with verbatim locators.

    all: every declared term must appear (hard constraint). any: at least one
    must appear. Both given, both must hold. Score = number of distinct matched
    terms; ties keep index order. Empty hits are honest; the result records the
    normalised query and the index fingerprint so anyone can replay it.
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
        matched_terms = sorted({t for t in q["all"] + q["any"] if t.lower() in low})
        passages = _passages(doc["paragraphs"], matched_terms)
        hits.append({"doc_id": doc_id, "score": len(matched_terms),
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
        result["note"] = ("no document matches the query over " + str(len(index["order"]))
                          + " indexed document(s); reported as empty, never padded")
    return {"ok": True, "result": result}


def search(spec):
    """Full pass: corpus (or a prebuilt index) + query → (index, result).

    Returns (None, refusal) when the corpus or the query cannot support a run;
    otherwise (index, result) with the result carrying the query record and the
    index fingerprint.
    """
    if not isinstance(spec, dict):
        return None, _refusal_result("search.spec_unreadable",
                                     "the spec is not a JSON object")
    if spec.get("query") is None:
        return None, _refusal_result("search.empty_query", "the spec declares no query")
    if isinstance(spec.get("index"), dict):
        built = {"ok": True, "index": spec["index"], "skipped": []}
    else:
        built = build_index(spec.get("corpus"))
        if not built["ok"]:
            return None, _lift(built["refusal"])
    res = run_query(built["index"], spec["query"])
    if not res["ok"]:
        return None, _lift(res["refusal"])
    result = res["result"]
    if built.get("skipped"):
        result["skipped"] = built["skipped"]
        result["findings"] = [{"rule": "search.doc_skipped", "severity": "low",
                               "count": len(built["skipped"]),
                               "entries": built["skipped"],
                               "why": "these corpus entries could not be indexed; named "
                                      "here instead of vanishing"}]
    return built["index"], result
