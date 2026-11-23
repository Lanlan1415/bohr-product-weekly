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
import math
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
    """Terms of a bare query, including CJK boundary-safe bigrams for recall.

    Short CJK phrases stay whole. Long unspaced Chinese questions also emit
    adjacent bigrams, so treating the entire sentence as one substring cannot
    silently erase an otherwise correct answer. Bigrams never cross punctuation,
    latin text or whitespace. Structured ``all``/``any`` terms stay verbatim.
    """
    s = str(q or "")
    terms = {t.lower() for t in _LATIN_WORD.findall(s)}
    for run in _CJK_RUN.findall(s):
        if len(run) <= 4:
            terms.add(run)
        if len(run) > 4:
            terms.update(run[i:i + 2] for i in range(len(run) - 1))
    return sorted(terms)


def analyzer(text: str) -> list[str]:
    """Unicode-codepoint tokens: latin words plus CJK uni/bigrams.

    This is the NgramTokenizer mechanism applied at character boundaries rather
    than UTF-8 bytes. It is deliberately deterministic and language neutral;
    no dictionary segmentation or semantic model is pretended.
    """
    text = str(text or "").casefold()
    tokens = re.findall(r"[a-z0-9]+(?:-[a-z0-9]+)*", text)
    # Hyphenated terms contribute their components as well as the full token.
    tokens += [part for tok in list(tokens) if "-" in tok for part in tok.split("-")]
    for run in re.findall(r"[\u4e00-\u9fff]+", text):
        tokens.extend(run)
        tokens.extend(run[i:i + 2] for i in range(len(run) - 1))
    return [t for t in tokens if t not in _STOP]


def _split_pages(text: str) -> tuple[list[str], list[int]]:
    paragraphs: list[str] = []
    pages: list[int] = []
    for page_no, chunk in enumerate(str(text or "").split("\f"), 1):
        for para in chunk.split("\n"):
            if para.strip():
                paragraphs.append(para)
                pages.append(page_no)
    return paragraphs, pages


def _meta_text(meta: dict) -> str:
    vals = []
    for key in sorted(meta):
        value = meta[key]
        if isinstance(value, (dict, list)):
            value = json.dumps(value, ensure_ascii=False, sort_keys=True)
        vals.extend([str(key), str(value)])
    return "\n".join(vals)


def _field_map(doc: dict) -> dict[str, str]:
    """Body and metadata channels used by BM25; built for old indexes too."""
    if isinstance(doc.get("fields"), dict):
        return {k: str(v or "") for k, v in doc["fields"].items()}
    paragraphs = doc.get("paragraphs") or []
    headings = "\n".join(s.get("title") or "" for s in doc.get("sections") or []
                         if isinstance(s, dict))
    return {"body": doc.get("text") or "", "title": doc.get("title") or "",
            "headings": headings, "path": doc.get("path") or "",
            "metadata": _meta_text(doc.get("meta") or {})}


def _statistics(index: dict) -> dict:
    if isinstance(index.get("statistics"), dict):
        return index["statistics"]
    docs = [index["documents"][k] for k in index["order"]]
    stats = {"doc_count": len(docs), "fields": {}}
    for field in ("body", "title", "headings", "path", "metadata"):
        tokenized = [analyzer(_field_map(d).get(field, "")) for d in docs]
        df: dict[str, int] = {}
        for tokens in tokenized:
            for token in set(tokens):
                df[token] = df.get(token, 0) + 1
        stats["fields"][field] = {"df": df,
                                  "avg_length": (sum(map(len, tokenized)) / len(docs)) if docs else 0.0}
    return stats


def _bm25_side(index: dict, terms: list[str], fields: list[str], weights: dict) -> dict:
    """Tantivy-form BM25 per field with explicit weights and explanations."""
    stats = _statistics(index)
    n_docs = max(1, len(index["order"]))
    out: dict[str, dict] = {}
    for pos, doc_id in enumerate(index["order"]):
        doc = index["documents"][doc_id]
        fmap = _field_map(doc)
        detail: dict[str, dict] = {}
        components: dict[str, float] = {}
        for term in terms:
            term_detail: dict[str, float] = {}
            for field in fields:
                tokens = analyzer(fmap.get(field, ""))
                if not tokens:
                    continue
                qtokens = analyzer(term)
                tf = sum(tokens.count(qt) for qt in qtokens)
                if not tf:
                    continue
                field_stats = stats["fields"][field]
                # Multiple query tokens (e.g. a CJK phrase) sum their IDFs.
                idf = sum(math.log(1 + (n_docs - field_stats["df"].get(qt, 0) + 0.5) /
                                   (field_stats["df"].get(qt, 0) + 0.5)) for qt in qtokens)
                avg = field_stats["avg_length"] or float(len(tokens)) or 1.0
                norm = 1.2 * (1 - 0.75 + 0.75 * len(tokens) / avg)
                value = float(weights.get(field, 1.0)) * idf * 2.2 * tf / (tf + norm)
                term_detail[field] = value
                components[field] = components.get(field, 0.0) + value
            if term_detail:
                detail[term] = term_detail
        if detail:
            out[doc_id] = {"score": sum(components.values()), "fields": components,
                           "terms": detail, "position": pos}
    return out


def _ranks(scored: dict) -> dict[str, int]:
    ordered = sorted(scored, key=lambda d: (-scored[d]["score"], scored[d]["position"], d))
    ranks: dict[str, int] = {}
    previous_score = None
    previous_rank = 0
    for index, doc_id in enumerate(ordered):
        value = scored[doc_id]["score"]
        rank = previous_rank if previous_score is not None and value == previous_score else index + 1
        ranks[doc_id] = rank
        previous_score, previous_rank = value, rank
    return ranks


def _filter_values(index: dict, filters: dict) -> dict:
    values: dict[str, list] = {}
    for key in filters:
        found = set()
        for doc_id in index["order"]:
            meta = index["documents"][doc_id].get("meta") or {}
            if key in meta:
                found.add(json.dumps(meta[key], ensure_ascii=False, sort_keys=True))
        values[key] = sorted(json.loads(v) for v in found)
    return values


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
            if text is None and isinstance(entry.get("pages"), list):
                text = "\f".join(str(p.get("text") or "") if isinstance(p, dict) else str(p)
                                 for p in entry["pages"])
            if text is None:
                skipped.append({"index": i, "reason": "entry is an object but has no text"})
                continue
            doc_id = str(entry.get("id") or entry.get("doc_id") or "").strip()
            text = str(text)
            title = str(entry.get("title") or "").strip()
            path = str(entry.get("path") or "").strip()
            meta = entry.get("meta")
            if meta is not None and not isinstance(meta, dict):
                meta_warnings.append(
                    {"index": i, "doc_id": doc_id or "(auto)",
                     "reason": "entry meta is not an object; stored empty — "
                               "filters cannot use it, never guessed"})
                meta = {}
        elif isinstance(entry, str):
            doc_id, text, meta, title, path = "", entry, {}, "", ""
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
        meta = dict(meta or {})
        title = title or str(meta.get("title") or "")
        path = path or str(entry.get("source_path") or "") if isinstance(entry, dict) else path
        paragraphs, paragraph_pages = _split_pages(text)
        secs = section_map(paragraphs)
        sections = [{"paragraph": k, "title": v} for k, v in sorted(secs.items())
                    if v is not None and (k == 0 or secs.get(k - 1) != v)]
        fields = {"body": text, "title": title,
                  "headings": "\n".join(s["title"] for s in sections),
                  "path": path, "metadata": _meta_text(meta)}
        docs[doc_id] = {"text": text, "paragraphs": paragraphs,
                        "paragraph_pages": paragraph_pages, "title": title, "path": path,
                        "sections": sections, "terms": key_terms(text), "fields": fields,
                        "sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
                        "source_sha256": entry.get("source_sha256") if isinstance(entry, dict) else None,
                        "meta": meta}
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
    canonical = [{"id": k, "text": docs[k]["text"], "meta": docs[k]["meta"],
                  "title": docs[k]["title"], "path": docs[k]["path"],
                  "source_sha256": docs[k].get("source_sha256")} for k in order]
    index = {
        "schema_version": SCHEMA_VERSION,
        "documents": docs,
        "order": order,
        "corpus_sha256": hashlib.sha256(json.dumps(
            canonical, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest(),
    }
    index["statistics"] = _statistics(index)
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
              max_passages: int = 20, pages: list | None = None) -> list:
    out: list = []
    for i, para in enumerate(paragraphs):
        for t in terms:
            for s, e in _find_occurrences(para, t):
                out.append({"term": t,
                            "locator": {"paragraph": i,
                                        "page": (pages[i] if pages and i < len(pages) else None),
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
    """Hard boolean/filter retrieval plus explainable BM25+metadata fusion.

    The lexical gates never loosen. Ranking uses Tantivy's BM25 formula over
    body/headings and title/path/metadata channels, then txtai-style weighted
    reciprocal-rank fusion by document id. ``score`` remains the backward-
    compatible distinct-term count; ``ranking_score`` drives ordering.
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

    terms = list(dict.fromkeys(q["all"] + q["any"]))
    weights = {"body": 1.0, "headings": 2.0, "title": 3.0, "path": 1.0, "metadata": 2.25}
    candidates = []
    term_matching_ids = []
    for doc_id in index["order"]:
        doc = index["documents"][doc_id]
        fmap = _field_map(doc)
        low = "\n".join(fmap.values()).casefold()
        matched_all = all(t.casefold() in low for t in q["all"])
        matched_any = (not q["any"]) or any(t.casefold() in low for t in q["any"])
        if not (matched_all and matched_any):
            continue
        term_matching_ids.append(doc_id)
        if q["filters"] and not _filters_match(doc.get("meta") or {}, q["filters"]):
            continue
        candidates.append(doc_id)

    body = _bm25_side(index, terms, ["body", "headings"], weights)
    meta_side = _bm25_side(index, terms, ["title", "path", "metadata"], weights)
    body_rank = _ranks({d: body[d] for d in candidates if d in body})
    meta_rank = _ranks({d: meta_side[d] for d in candidates if d in meta_side})
    duplicate_groups: dict[str, list[str]] = {}
    hits = []
    for doc_id in candidates:
        doc = index["documents"][doc_id]
        fmap = _field_map(doc)
        low = "\n".join(fmap.values()).casefold()
        matched_terms = sorted({t for t in terms if t.casefold() in low})
        passages = _passages(doc["paragraphs"], matched_terms,
                             section_map(doc["paragraphs"]),
                             pages=doc.get("paragraph_pages"))
        field_matches = []
        for field in ("title", "path", "metadata"):
            hay = fmap.get(field, "")
            for term in matched_terms:
                at = hay.casefold().find(term.casefold())
                if at >= 0:
                    field_matches.append({"field": field, "term": term,
                                          "quote": hay[at:at + len(term)]})
        br, mr = body_rank.get(doc_id), meta_rank.get(doc_id)
        ranking_score = (0.75 / br if br else 0.0) + (0.25 / mr if mr else 0.0)
        body_score = body.get(doc_id, {}).get("score", 0.0)
        meta_score = meta_side.get(doc_id, {}).get("score", 0.0)
        hits.append({
            "doc_id": doc_id, "doc_sha256": doc.get("sha256", ""),
            "source_sha256": doc.get("source_sha256"), "title": doc.get("title") or "",
            "path": doc.get("path") or "", "meta": doc.get("meta") or {},
            "score": len(matched_terms), "ranking_score": ranking_score,
            "matched_terms": matched_terms, "passages": passages,
            "field_matches": field_matches,
            "rank_reason": {
                "method": "0.75/body_rank + 0.25/metadata_rank; lower source rank is better",
                "body_rank": br, "metadata_rank": mr,
                "body_bm25": round(body_score, 8), "metadata_bm25": round(meta_score, 8),
                "field_weights": weights,
                "body_term_contributions": body.get(doc_id, {}).get("terms", {}),
                "metadata_term_contributions": meta_side.get(doc_id, {}).get("terms", {}),
                "note": "BM25 and field weights order evidence; they are not a probability or semantic label",
            },
        })
        duplicate_groups.setdefault(doc.get("sha256", ""), []).append(doc_id)
    # Fused relevance first; index order is the final deterministic tie-break.
    order_pos = {d: i for i, d in enumerate(index["order"])}
    hits.sort(key=lambda h: (-h["ranking_score"], -h["rank_reason"]["body_bm25"],
                             order_pos[h["doc_id"]]))
    duplicate_sets = [sorted(set(ids)) for ids in duplicate_groups.values() if len(set(ids)) > 1]
    result = {
        "schema_version": SCHEMA_VERSION,
        "ok": True,
        "query": q,
        "index_sha256": str(index.get("corpus_sha256", ""))[:16],
        "documents_indexed": len(index["order"]),
        "hits": hits,
        "empty": not hits,
        "ranking": {"method": "BM25 + metadata weighted reciprocal-rank fusion",
                    "formula": "idf=ln(1+(N-n+0.5)/(n+0.5)); k1=1.2; b=0.75",
                    "body_weight": 0.75, "metadata_weight": 0.25, "field_weights": weights,
                    "cjk": "contiguous Unicode codepoint unigrams+bigrams; no cross-boundary grams"},
        "evidence": {"duplicate_doc_id_sets": duplicate_sets,
                     "independent_document_count": len(hits) - sum(len(x) - 1 for x in duplicate_sets),
                     "note": " duplicate ids share a text hash and are not independent evidence" if duplicate_sets else ""},
        "ambiguity": {"is_ambiguous": False, "candidate_doc_ids": [], "reason": None},
    }
    if len(hits) > 1 and abs(hits[0]["ranking_score"] - hits[1]["ranking_score"]) < 1e-12 \
            and abs(hits[0]["rank_reason"]["body_bm25"] - hits[1]["rank_reason"]["body_bm25"]) < 1e-9:
        result["ambiguity"] = {"is_ambiguous": True,
                               "candidate_doc_ids": [hits[0]["doc_id"], hits[1]["doc_id"]],
                               "reason": "top results tie under every ranking component; review both, never choose silently"}
    if not hits:
        reason = "filters_excluded_all_term_matches" if term_matching_ids and q["filters"] else "no_term_match"
        note = ("no document matches the query over " + str(len(index["order"]))
                + " indexed document(s); reported as empty, never padded")
        if q["filters"]:
            note += ("; the declared filters " + json.dumps(q["filters"],
                                                            ensure_ascii=False,
                                                            sort_keys=True)
                     + " matched no document — executed as declared, not relaxed")
        result["note"] = note
        result["no_result"] = {
            "reason": reason, "term_matching_doc_ids_before_filters": term_matching_ids,
            "filters": q["filters"], "available_filter_values": _filter_values(index, q["filters"]),
            "recovery": ["verify the normalized query and indexed text-extraction coverage",
                         "change terms or filters explicitly in a new query; the engine did not relax anything"],
        }
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
