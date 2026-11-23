"""Deterministic patent and technical-literature search over an authorised snapshot.

The engine deliberately separates lexical retrieval from patent-register facts:

* publication, application, grant and priority numbers are normalised independently
  and matched as fields, never as ambiguous substrings;
* simple-family and INPADOC-family identifiers use different fields.  A family_of
  query expands only through an explicitly recorded identifier and never interprets
  a members link as an exhaustive family or as equal claim scope;
* priority, filing, publication and status dates keep their own semantics and ISO
  precision.  Missing dates are reported, never filled from another date field;
* recorded legal status is not current legal status.  Current status remains
  undetermined unless the record expressly carries an official-registry verification
  and query date;
* red/restricted records are excluded before indexing.  Their text is never copied
  to index.json or result.json.

Every hit carries source-located, slice-verifiable passages.  Findings drive a
stable status: clean (0), review (3), blocked (4), or a refusal/undetermined (5).
No wall-clock value or network response is invented, so equal inputs replay exactly.
"""

from __future__ import annotations

from datetime import date
import hashlib
import json
import re

SCHEMA_VERSION = "patent-search/v2"

_STOP = {"the", "and", "for", "with", "this", "that", "from", "are", "was",
         "他们的", "我们", "因此", "但是", "然后"}
_LATIN_WORD = re.compile(r"[A-Za-z][A-Za-z0-9_-]{1,}")
_CJK_RUN = re.compile(r"[\u4e00-\u9fff]{2,}")
_NUMBER_RE = re.compile(r"^[A-Z]{2}(?=[A-Z0-9]*\d)[A-Z0-9]{4,}$")
_LABEL_RE = re.compile(
    r"^\s*([A-Za-z\u4e00-\u9fff][A-Za-z0-9\u4e00-\u9fff _/-]{0,42}):\s*(.*?)\s*$")

NUMBER_FIELDS = ("publication_number", "application_number", "grant_number",
                 "priority_number")
NUMBER_KINDS = {"any": NUMBER_FIELDS, "publication": ("publication_number",),
                "application": ("application_number",), "grant": ("grant_number",),
                "priority": ("priority_number",)}
DATE_FIELDS = ("priority_date", "filing_date", "publication_date", "grant_date",
               "status_date")
LIST_FIELDS = {"family", "inpadoc_family", "family_members", "cpc", "ipc"}
SOURCE_FIELDS = ("source", "source_version", "query_date", "url", "source_type",
                 "license", "access", "display_scope")

FIELD_ALIASES = {
    "number": "publication_number", "patent_number": "publication_number",
    "pub": "publication_number", "pub_number": "publication_number",
    "publication": "publication_number", "publication_no": "publication_number",
    "publication_number": "publication_number", "公开号": "publication_number",
    "application": "application_number", "app_number": "application_number",
    "application_no": "application_number", "application_number": "application_number",
    "申请号": "application_number", "grant": "grant_number",
    "grant_no": "grant_number", "grant_number": "grant_number",
    "授权号": "grant_number", "priority": "priority_number",
    "priority_no": "priority_number", "priority_number": "priority_number",
    "优先权号": "priority_number", "family": "family",
    "simple_family": "family", "simple_family_id": "family", "简单同族": "family",
    "inpadoc": "inpadoc_family", "inpadoc_family": "inpadoc_family",
    "inpadoc_family_id": "inpadoc_family", "extended_family": "inpadoc_family",
    "INPADOC同族": "inpadoc_family", "members": "family_members",
    "family_members": "family_members", "observed_members": "family_members",
    "priority_date": "priority_date", "earliest_priority_date": "priority_date",
    "优先权日": "priority_date", "filing_date": "filing_date",
    "application_date": "filing_date", "申请日": "filing_date",
    "publication_date": "publication_date", "公开日": "publication_date",
    "grant_date": "grant_date", "授权日": "grant_date",
    "status": "status", "legal_status": "status", "法律状态": "status",
    "status_date": "status_date", "legal_status_date": "status_date",
    "status_effective_date": "status_date", "状态生效日": "status_date",
    "cpc": "cpc", "cpc_class": "cpc", "ipc": "ipc", "ipc_class": "ipc",
    "title": "title", "题名": "title", "applicant": "applicant",
    "assignee": "applicant", "申请人": "applicant", "document_type": "document_type",
    "doc_type": "document_type", "record_type": "document_type",
    "文献类型": "document_type", "doi": "doi", "year": "year",
    "journal": "journal", "language": "language",
    "claim_version": "claim_version", "claims_version": "claim_version",
    "claim_document_version": "claim_version", "权利要求版本": "claim_version",
    "claims_source": "claims_source", "权利要求来源": "claims_source",
    "source": "source", "source_name": "source", "数据库": "source",
    "source_version": "source_version", "database_version": "source_version",
    "库版本": "source_version", "query_date": "query_date", "检索日期": "query_date",
    "url": "url", "source_url": "url", "locator_url": "url",
    "source_type": "source_type", "registry_type": "source_type",
    "license": "license", "licence": "license", "使用许可": "license",
    "access": "access", "access_class": "access", "授权级别": "access",
    "display_scope": "display_scope", "可展示范围": "display_scope",
} | {name: name for name in (*NUMBER_FIELDS, *DATE_FIELDS, *LIST_FIELDS,
                             *SOURCE_FIELDS, "registry_verified", "status_source",
                             "status_source_type", "claims_source")}

_QUERY_KEYS = {
    "all", "any", "not", "filters", "number", "number_kind", "publication_number",
    "application_number", "grant_number", "priority_number", "family", "family_scope",
    "family_of", "status", "cpc", "ipc", "applicant", "date_field", "date_from",
    "date_to", "claim_version", "require_current_status", "require_claims",
    "require_fields", "require_source_license", "source", "source_type",
    "document_type",
}
_FILTER_KEYS = _QUERY_KEYS - {"all", "any", "not", "filters"}
_REQUIREABLE_FIELDS = set(FIELD_ALIASES.values()) | {"family", "inpadoc_family"}


def _refusal(rule: str, message: str) -> dict:
    return {"rule": rule, "message": message}


def _refusal_result(rule: str, message: str) -> dict:
    return {"schema_version": SCHEMA_VERSION, "ok": False,
            "status": "undetermined", "refusal": _refusal(rule, message),
            "limits": ["no query was answered"]}


def _lift(bare_refusal: dict) -> dict:
    return _refusal_result(bare_refusal["rule"], bare_refusal["message"])


def _label(value) -> str:
    return re.sub(r"[\s-]+", "_", str(value or "").strip().lower()).strip("_")


def _values(value, split: bool = False) -> list:
    if value is None:
        return []
    if isinstance(value, (list, tuple)):
        out = []
        for item in value:
            out.extend(_values(item, split=split))
        return out
    if isinstance(value, (dict, set)):
        return [str(value)]
    if split and isinstance(value, str) and any(mark in value for mark in (";", ",")):
        return [part.strip() for part in re.split(r"[;,]", value) if part.strip()]
    return [value]


def _canonical_field(name) -> str:
    return FIELD_ALIASES.get(_label(name), _label(name))


def _put(fields: dict, name, value) -> None:
    key = _canonical_field(name)
    if not key or value is None or isinstance(value, (dict, set)):
        return
    vals = _values(value, split=key in LIST_FIELDS)
    vals = [v.strip() if isinstance(v, str) else v for v in vals]
    vals = [v for v in vals if str(v).strip()]
    if not vals:
        return
    if key not in fields:
        fields[key] = vals if key in LIST_FIELDS else vals[0]
        return
    old = fields[key] if isinstance(fields[key], list) else [fields[key]]
    for val in vals:
        if not any(str(val).casefold() == str(x).casefold() for x in old):
            old.append(val)
    fields[key] = old if key in LIST_FIELDS or len(old) > 1 else old[0]


def _parse_text_fields(text: str) -> dict:
    fields: dict = {}
    for line in str(text or "").splitlines():
        match = _LABEL_RE.match(line)
        if match:
            key = _canonical_field(match.group(1))
            if key in _REQUIREABLE_FIELDS:
                _put(fields, key, match.group(2))
    return fields


def _metadata_fields(entry: dict) -> dict:
    raw: dict = {}
    for container in (entry.get("metadata"), entry.get("fields")):
        if isinstance(container, dict):
            raw.update(container)
    for key, value in entry.items():
        if key not in {"id", "doc_id", "text", "metadata", "fields"}:
            raw[key] = value
    source = raw.get("source")
    if isinstance(source, dict):
        raw.pop("source", None)
        for key, value in source.items():
            mapped = {"name": "source", "version": "source_version",
                      "date": "query_date", "type": "source_type"}.get(key, key)
            raw[mapped] = value
    fields: dict = {}
    for key, value in raw.items():
        canonical = _canonical_field(key)
        if canonical in _REQUIREABLE_FIELDS:
            _put(fields, canonical, value)
    return fields


def normalise_patent_number(value) -> str:
    """Keep country and kind codes; remove only presentation punctuation."""
    return re.sub(r"[^A-Z0-9]", "", str(value or "").upper())


# US spelling is kept as a public alias for callers and older bench utilities.
normalize_patent_number = normalise_patent_number


def _normalise_number_fields(fields: dict) -> None:
    for key in NUMBER_FIELDS + ("family_members",):
        if key in fields:
            vals = [normalise_patent_number(v) for v in _values(fields[key])]
            fields[key] = vals if key in LIST_FIELDS or len(vals) > 1 else vals[0]


def _text_from_fields(fields: dict) -> str:
    lines = []
    for key in sorted(fields):
        vals = fields[key] if isinstance(fields[key], list) else [fields[key]]
        for value in vals:
            if not isinstance(value, (dict, list, tuple)):
                lines.append(f"{key}: {value}")
    return "\n".join(lines)


def _date_info(raw) -> dict:
    text = str(raw or "").strip()
    info = {"raw": text, "valid": False, "normalized": None, "precision": None,
            "start": None, "end": None}
    compact = text.replace("/", "-")
    match = re.fullmatch(r"(\d{4})(?:-(\d{2})(?:-(\d{2}))?)?", compact)
    if not match and re.fullmatch(r"\d{8}", compact):
        match = re.fullmatch(r"(\d{4})(\d{2})(\d{2})", compact)
    if not match:
        info["error"] = "expected YYYY, YYYY-MM, YYYY-MM-DD, or YYYYMMDD"
        return info
    year = int(match.group(1))
    month = int(match.group(2)) if match.group(2) else None
    day = int(match.group(3)) if match.group(3) else None
    try:
        if month is None:
            start, end, precision = date(year, 1, 1), date(year, 12, 31), "year"
            normalized = f"{year:04d}"
        elif day is None:
            start = date(year, month, 1)
            end = date(year + (month == 12), 1 if month == 12 else month + 1, 1)
            end = end.fromordinal(end.toordinal() - 1)
            precision, normalized = "month", f"{year:04d}-{month:02d}"
        else:
            start = end = date(year, month, day)
            precision, normalized = "day", f"{year:04d}-{month:02d}-{day:02d}"
    except ValueError as exc:
        info["error"] = str(exc)
        return info
    info.update({"valid": True, "normalized": normalized, "precision": precision,
                 "start": start.isoformat(), "end": end.isoformat()})
    return info


def _date_infos(doc: dict, field: str) -> list:
    return list((doc.get("dates") or {}).get(field) or [])


def _extract_dates(fields: dict) -> dict:
    return {key: [_date_info(v) for v in _values(fields[key])]
            for key in DATE_FIELDS if key in fields}


def _source(fields: dict) -> dict:
    return {key: fields[key] for key in SOURCE_FIELDS if key in fields}


def _is_true(value) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "y"}


def _registry_verified(fields: dict) -> bool:
    kind = _label(fields.get("status_source_type") or fields.get("source_type"))
    return bool(_is_true(fields.get("registry_verified"))
                and kind in {"official_registry", "official_register", "registry",
                             "patent_office", "uspto", "epo", "wipo", "cnipa"}
                and _date_info(fields.get("query_date"))["valid"])


def _prepare_entry(entry, generated_id: str):
    if isinstance(entry, str):
        return {"doc_id": generated_id, "text": entry, "text_fields": {},
                "fields": {}, "conflicts": []}
    if not isinstance(entry, dict):
        return {"skip": "entry is neither an object nor a string: " + type(entry).__name__}
    doc_id = str(entry.get("id") or entry.get("doc_id") or generated_id).strip()
    structured = _metadata_fields(entry)
    text = entry.get("text")
    text_fields = _parse_text_fields(str(text)) if text is not None else {}
    access = _label(structured.get("access") or text_fields.get("access"))
    if access in {"red", "restricted", "prohibited", "no_access", "closed"}:
        return {"restricted": {"doc_id": doc_id, "access": access or "red",
                               "source": structured.get("source") or text_fields.get("source"),
                               "reason": "restricted source excluded before indexing"}}
    fields = dict(text_fields)
    conflicts = []
    for key, value in structured.items():
        if key in fields and str(fields[key]).casefold() != str(value).casefold():
            conflicts.append({"field": key, "text_value": fields[key],
                              "structured_value": value})
        fields[key] = value
    _normalise_number_fields(fields)
    display_limited = None
    scope_tokens = {_label(v) for value in _values(fields.get("display_scope"))
                    for v in re.split(r"[,;\s]+", str(value)) if str(v).strip()}
    if access == "yellow" and "full_text" not in scope_tokens:
        # Yellow material is reduced to declared metadata before any artifact is
        # written.  "metadata" permits all recognised labels, never raw prose.
        allowed = set(NUMBER_FIELDS) | set(DATE_FIELDS) | {
            "family", "inpadoc_family", "document_type", *SOURCE_FIELDS}
        if "metadata" in scope_tokens:
            allowed |= set(fields)
        for token in sorted(scope_tokens - {"metadata"}):
            field = _canonical_field(token)
            if field in _REQUIREABLE_FIELDS:
                allowed.add(field)
        fields = {key: value for key, value in fields.items() if key in allowed}
        text_fields = {key: value for key, value in text_fields.items() if key in allowed}
        conflicts = [item for item in conflicts if item.get("field") in allowed]
        text = "id: " + doc_id + "\n" + _text_from_fields(fields)
        display_limited = {"doc_id": doc_id, "access": "yellow",
                           "source": fields.get("source"),
                           "allowed_fields": sorted(fields),
                           "reason": "yellow source reduced to authorised metadata before indexing"}
    if text is None:
        text = _text_from_fields(fields)
    text = str(text or "")
    if not text.strip():
        return {"skip": "entry is an object but has no text or recognised metadata"}
    evidence_fields = dict(fields)
    for key, value in text_fields.items():
        _put(evidence_fields, key, value)
    return {"doc_id": doc_id, "text": text, "text_fields": text_fields,
            "fields": fields, "evidence_fields": evidence_fields, "conflicts": conflicts,
            "display_limited": display_limited}


def key_terms(text: str, min_len: int = 2) -> list:
    s = str(text or "")
    latin = re.findall(r"[A-Za-z][A-Za-z0-9_-]{%d,}" % (min_len - 1), s)
    cjk = re.findall(r"[\u4e00-\u9fff]{%d,}" % max(min_len, 2), s)
    grams: set = set(latin)
    for run in cjk:
        n = max(min_len, 2)
        grams.update(run[i:i + n] for i in range(len(run) - n + 1))
    return sorted(g for g in grams if g.lower() not in _STOP)


def query_terms(q: str) -> list:
    s = str(q or "")
    terms = {t.lower() for t in _LATIN_WORD.findall(s)}
    terms |= set(_CJK_RUN.findall(s))
    return sorted(terms)


def _term_list(raw) -> list:
    if raw is None:
        return []
    if not isinstance(raw, list):
        raw = [raw]
    out = []
    for value in raw:
        text = str(value).strip()
        if text and text.casefold() not in {x.casefold() for x in out}:
            out.append(text)
    return out


def _boolean(raw) -> bool | None:
    if isinstance(raw, bool):
        return raw
    if isinstance(raw, (int, float)) and raw in (0, 1):
        return bool(raw)
    text = str(raw or "").strip().lower()
    if text in {"true", "yes", "1"}:
        return True
    if text in {"false", "no", "0", ""}:
        return False
    return None


def _query_date(value, label):
    info = _date_info(value)
    if not info["valid"]:
        return None, _refusal("patent.query_date_invalid",
                              f"{label} is not a valid ISO date: {info.get('error')}")
    return info, None


def parse_query(query):
    """Return a normalised lexical + patent-field query or a named refusal."""
    if isinstance(query, str):
        number = normalise_patent_number(query)
        if _NUMBER_RE.fullmatch(number) and sum(c.isdigit() for c in number) >= 4:
            return {"all": [], "any": [], "not": [], "number": number,
                    "number_kind": "any"}, None
        terms = query_terms(query)
        if not terms:
            return None, _refusal("search.empty_query",
                                  "the query contains no searchable term")
        return {"all": [], "any": terms, "not": []}, None
    if not isinstance(query, dict):
        return None, _refusal("search.empty_query",
                              "the query is neither a string nor a query object")
    unknown = sorted(set(query) - _QUERY_KEYS)
    if unknown:
        return None, _refusal("patent.query_field_unknown",
                              "unsupported query field(s): " + ", ".join(unknown))
    filters = query.get("filters") or {}
    if not isinstance(filters, dict):
        return None, _refusal("patent.query_field_unknown", "filters must be an object")
    unknown_filters = sorted(set(filters) - _FILTER_KEYS)
    if unknown_filters:
        return None, _refusal("patent.query_field_unknown",
                              "unsupported filter field(s): " + ", ".join(unknown_filters))
    merged = {key: value for key, value in query.items()
              if key not in {"all", "any", "not", "filters"}}
    merged.update(filters)
    q = {"all": _term_list(query.get("all")), "any": _term_list(query.get("any")),
         "not": _term_list(query.get("not"))}

    aliases = [key for key in ("publication_number", "application_number",
                               "grant_number", "priority_number") if key in merged]
    if aliases and "number" in merged:
        return None, _refusal("patent.query_field_unknown",
                              "use either number or a kind-specific number alias, not both")
    if len(aliases) > 1:
        return None, _refusal("patent.query_field_unknown",
                              "declare only one kind-specific number alias per query")
    if aliases:
        kind = aliases[0].removesuffix("_number")
        q["number"] = normalise_patent_number(merged[aliases[0]])
        q["number_kind"] = kind
    elif "number" in merged:
        q["number"] = normalise_patent_number(merged["number"])
        q["number_kind"] = _label(merged.get("number_kind") or "any")
    elif "family_of" in merged:
        q["number_kind"] = _label(merged.get("number_kind") or "any")
    if "number_kind" in merged and "number_kind" not in q:
        q["number_kind"] = _label(merged.get("number_kind"))
    if "number_kind" in q and q["number_kind"] not in NUMBER_KINDS:
        return None, _refusal("patent.query_field_unknown",
                              "number_kind must be any, publication, application, grant, or priority")
    if "family_of" in merged:
        q["family_of"] = normalise_patent_number(merged["family_of"])
    for key in ("family", "status", "cpc", "ipc", "applicant", "claim_version",
                "source", "source_type", "document_type"):
        if key in merged:
            vals = _term_list(merged[key])
            if vals:
                q[key] = vals if key in {"family"} else vals[0]
    scope = _label(merged.get("family_scope") or "simple")
    if scope not in {"simple", "inpadoc"}:
        return None, _refusal("patent.query_field_unknown",
                              "family_scope must be simple or inpadoc")
    if "family" in q or "family_of" in q or "family_scope" in merged:
        q["family_scope"] = scope

    date_keys = [key for key in ("date_from", "date_to") if key in merged]
    date_field = _canonical_field(merged.get("date_field") or "priority_date")
    if date_field not in DATE_FIELDS:
        return None, _refusal("patent.query_field_unknown",
                              "date_field must name a supported patent date")
    intervals = {}
    for key in date_keys:
        info, err = _query_date(merged[key], key)
        if err:
            return None, err
        intervals[key] = info
        q[key] = info["normalized"]
    if date_keys:
        q["date_field"] = date_field
        if "date_from" in intervals and "date_to" in intervals \
                and intervals["date_from"]["start"] > intervals["date_to"]["end"]:
            return None, _refusal("patent.query_date_invalid", "date_from is after date_to")
    for key in ("require_current_status", "require_claims", "require_source_license"):
        if key in merged:
            val = _boolean(merged[key])
            if val is None:
                return None, _refusal("patent.query_field_unknown", key + " must be boolean")
            q[key] = val
    if "require_fields" in merged:
        fields = [_canonical_field(v) for v in _term_list(merged["require_fields"])]
        bad = sorted(set(fields) - _REQUIREABLE_FIELDS)
        if bad:
            return None, _refusal("patent.query_field_unknown",
                                  "unsupported required field(s): " + ", ".join(bad))
        q["require_fields"] = fields

    positive = bool(q["all"] or q["any"] or q["number"] if "number" in q else q["all"] or q["any"])
    positive = positive or any(key in q for key in
                               ("family", "family_of", "status", "cpc", "ipc", "applicant",
                                "date_from", "date_to", "claim_version", "source",
                                "source_type", "document_type"))
    if not positive:
        return None, _refusal("search.empty_query",
                              "the query declares no positive lexical or patent-field criterion")
    return q, None


def build_index(corpus):
    """Build a deterministic index; restricted records are metadata-only skips."""
    if not isinstance(corpus, list):
        return {"ok": False, "refusal": _refusal(
            "search.empty_corpus", "the corpus is missing or not a list of documents")}
    docs: dict = {}
    order: list = []
    skipped: list = []
    restricted: list = []
    display_limited: list = []
    seen_ids: set = set()
    for i, entry in enumerate(corpus):
        generated = "doc-" + str(len(order) + 1).zfill(3)
        prepared = _prepare_entry(entry, generated)
        if "restricted" in prepared:
            item = {"index": i, **prepared["restricted"]}
            restricted.append(item)
            continue
        if "skip" in prepared:
            skipped.append({"index": i, "reason": prepared["skip"]})
            continue
        if prepared.get("display_limited"):
            display_limited.append({"index": i, **prepared["display_limited"]})
        doc_id = prepared["doc_id"]
        if doc_id in seen_ids:
            skipped.append({"index": i, "reason": "duplicate doc id '" + doc_id
                            + "'; the entry is skipped rather than silently merged"})
            continue
        seen_ids.add(doc_id)
        text = prepared["text"]
        docs[doc_id] = {
            "text": text, "paragraphs": [p for p in text.split("\n") if p.strip()],
            "terms": key_terms(text), "fields": prepared["fields"],
            "evidence_fields": prepared.get("evidence_fields", prepared["fields"]),
            "dates": _extract_dates(prepared["fields"]),
            "conflicts": prepared["conflicts"],
        }
        order.append(doc_id)
    if not order and not restricted:
        detail = "; ".join(str(s["reason"]) for s in skipped[:3])
        return {"ok": False, "refusal": _refusal(
            "search.empty_corpus", "no document could be indexed" +
            (": " + detail if detail else ""))}
    canonical = [{"id": key, "text": docs[key]["text"], "fields": docs[key]["fields"]}
                 for key in order]
    number_index: dict = {kind: {} for kind in NUMBER_FIELDS}
    for doc_id in order:
        fields = docs[doc_id]["fields"]
        for kind in NUMBER_FIELDS:
            for number in _values(fields.get(kind)):
                number_index[kind].setdefault(str(number), []).append(doc_id)
    index = {"schema_version": SCHEMA_VERSION, "documents": docs, "order": order,
             "corpus_sha256": hashlib.sha256(json.dumps(
                 canonical, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest(),
             "number_index": number_index, "restricted": restricted,
             "display_limited": display_limited}
    return {"ok": True, "index": index, "skipped": skipped, "restricted": restricted,
            "display_limited": display_limited}


def _find_occurrences(para: str, term: str, limit: int = 50) -> list:
    out: list = []
    text = str(term or "")
    if not text:
        return out
    low_t, low_p = text.lower(), para.lower()
    start = 0
    if len(low_p) != len(para) or len(low_t) != len(text):
        while len(out) < limit:
            at = para.find(text, start)
            if at < 0:
                break
            out.append((at, at + len(text)))
            start = at + 1
        return out
    while len(out) < limit:
        at = low_p.find(low_t, start)
        if at < 0:
            break
        out.append((at, at + len(text)))
        start = at + 1
    return out


def _paragraph_field(para: str):
    match = _LABEL_RE.match(para)
    return _canonical_field(match.group(1)) if match else None


def _passages(paragraphs: list, terms: list, doc_id: str, max_passages: int = 20,
              existing=None) -> list:
    out = list(existing or [])
    seen = {(p["locator"]["paragraph"], p["locator"]["start"], p["locator"]["end"])
            for p in out}
    for i, para in enumerate(paragraphs):
        for term in terms:
            for start, end in _find_occurrences(para, str(term)):
                marker = (i, start, end)
                if marker in seen:
                    continue
                out.append({"term": str(term), "locator": {
                    "doc_id": doc_id, "paragraph": i, "start": start, "end": end,
                    "field": _paragraph_field(para), "quote": para[start:end]}})
                seen.add(marker)
                if len(out) >= max_passages:
                    return out
    return out


def _doc_has_number(doc: dict, number: str, kind: str = "any") -> bool:
    fields = doc.get("fields") or {}
    return any(number in [str(v) for v in _values(fields.get(field))]
               for field in NUMBER_KINDS.get(kind, NUMBER_FIELDS))


def _field_values(doc: dict, field: str) -> list:
    return _values((doc.get("fields") or {}).get(field))


def _finding(rule, severity, message, doc_ids=None, entries=None) -> dict:
    out = {"rule": rule, "severity": severity, "message": message}
    if doc_ids:
        out["doc_ids"] = sorted(set(doc_ids))
        out["count"] = len(out["doc_ids"])
    if entries is not None:
        out["entries"] = entries
        out["count"] = len(entries)
    return out


def _date_overlap(doc: dict, field: str, lower, upper) -> bool:
    for info in _date_infos(doc, field):
        if not info["valid"]:
            continue
        if lower and info["end"] < lower["start"]:
            continue
        if upper and info["start"] > upper["end"]:
            continue
        return True
    return False


def _query_intervals(q: dict):
    return (_date_info(q["date_from"]) if "date_from" in q else None,
            _date_info(q["date_to"]) if "date_to" in q else None)


def _filter_fields(filter_name: str, q: dict) -> list:
    if filter_name in {"number", "family_of"}:
        return list(NUMBER_KINDS.get(q.get("number_kind", "any"), NUMBER_FIELDS))
    if filter_name in {"family", "family_of"}:
        return ["family" if q.get("family_scope", "simple") == "simple" else "inpadoc_family"]
    if filter_name in {"date_from", "date_to"}:
        return [q.get("date_field", "priority_date")]
    return [filter_name]


def _legal_status(fields: dict) -> dict:
    verified = _registry_verified(fields)
    return {"recorded_status": fields.get("status"),
            "status_date": fields.get("status_date"),
            "source": fields.get("status_source") or fields.get("source"),
            "source_type": fields.get("status_source_type") or fields.get("source_type"),
            "query_date": fields.get("query_date"), "registry_verified": verified,
            "current_status": fields.get("status") if verified else "undetermined",
            "note": "verified only at the recorded query date" if verified else
                    "snapshot token only; current official legal status is undetermined"}


def _families(hits: list, documents: dict, selected_scope=None) -> list:
    groups: dict = {}
    scopes = (("simple", "family"), ("inpadoc", "inpadoc_family"))
    if selected_scope:
        scopes = tuple(item for item in scopes if item[0] == selected_scope)
    for hit in hits:
        fields = documents[hit["doc_id"]]["fields"]
        for scope, field in scopes:
            for family_id in _values(fields.get(field)):
                key = (scope, str(family_id))
                groups.setdefault(key, []).append(hit["doc_id"])
    return [{"scope": scope, "family_id": family_id,
             "doc_ids": sorted(set(doc_ids)), "member_count": len(set(doc_ids)),
             "coverage": "observed indexed members only; not an exhaustive family",
             "claim_scope": "membership does not establish equal claim scope"}
            for (scope, family_id), doc_ids in sorted(groups.items())]


def _finalise(result: dict, documents: dict) -> dict:
    findings = result.get("findings", [])
    findings.sort(key=lambda f: (f.get("rule", ""), f.get("doc_ids", []),
                                 f.get("message", "")))
    counts = {sev: sum(1 for f in findings if f.get("severity") == sev)
              for sev in ("high", "medium", "low")}
    status = "blocked" if counts["high"] else "review" if counts["medium"] else "clean"
    limits = list(dict.fromkeys(str(x) for x in result.get("limits", [])))
    general = "Coverage is limited to the accessible indexed snapshot; empty is not global absence."
    if general not in limits:
        limits.append(general)
    if result.get("families"):
        caveat = "Observed family links are not exhaustive and do not imply equal claim scope."
        if caveat not in limits:
            limits.append(caveat)
    result.update({"schema_version": SCHEMA_VERSION, "ok": True, "status": status,
                   "severity_counts": counts, "limits": limits, "uncertainty": limits})
    hits = result.get("hits", [])
    sources = [{"doc_id": hit["doc_id"], **hit.get("source", {})} for hit in hits]
    result["sources"] = sources
    result["检索结果"] = {
        "候选文献": hits, "排序/筛选结果": [hit["doc_id"] for hit in hits],
        "排序依据": "distinct lexical terms plus declared field matches; stable corpus-order ties",
        "筛选依据": result.get("query"), "同族归并": result.get("families", []),
        "缺失项": [f for f in findings if "missing" in f.get("rule", "")],
    }
    result["证据记录"] = {
        "查询": result.get("query"), "来源与定位": sources,
        "索引指纹": result.get("index_sha256"),
        "定位": [{"doc_id": hit["doc_id"], "passages": hit.get("passages", [])}
                 for hit in hits],
        "字段口径": {"number": "normalised exact field; kind codes retained",
                     "family": "simple and INPADOC identifiers are separate",
                     "dates": "inclusive ISO intervals; no cross-date substitution",
                     "status": "current status undetermined without dated official verification"},
        "发现": findings,
    }
    result["状态说明"] = {
        "运行状态": status, "空结果": result.get("empty", False),
        "冲突": [f for f in findings if "conflict" in f.get("rule", "")],
        "权限或接口异常": [f for f in findings if "restricted" in f.get("rule", "")],
        "已完成": [f"searched {result.get('documents_indexed', 0)} accessible record(s)",
                   f"returned {len(hits)} ranked hit(s) with source locators"],
        "未完成": [f.get("message", f.get("rule", ""))
                   for f in findings if f.get("severity") in {"high", "medium"}],
        "不确定性": limits,
    }
    return result


def run_query(index, query):
    """Execute hard lexical and patent-field constraints over a readable index."""
    if not isinstance(index, dict) or not isinstance(index.get("documents"), dict) \
            or not isinstance(index.get("order"), list):
        return {"ok": False, "refusal": _refusal(
            "search.index_malformed", "the index needs a documents map plus an order list")}
    if len(set(index["order"])) != len(index["order"]):
        return {"ok": False, "refusal": _refusal(
            "search.index_malformed", "index order contains duplicate document ids")}
    if not index["order"] and not index.get("restricted"):
        return {"ok": False, "refusal": _refusal(
            "search.empty_corpus", "the index contains no accessible documents")}
    for doc_id in index["order"]:
        doc = index["documents"].get(doc_id)
        if not isinstance(doc, dict) or not isinstance(doc.get("paragraphs"), list) \
                or not isinstance(doc.get("text"), str):
            return {"ok": False, "refusal": _refusal(
                "search.index_malformed", "index entry '" + str(doc_id) + "' is malformed")}
        if "fields" in doc and not isinstance(doc["fields"], dict):
            return {"ok": False, "refusal": _refusal(
                "search.index_malformed", "index fields for '" + str(doc_id) + "' are malformed")}
        if "fields" not in doc:
            doc["fields"] = _parse_text_fields(doc["text"])
            _normalise_number_fields(doc["fields"])
        doc.setdefault("evidence_fields", doc["fields"])
        doc.setdefault("dates", _extract_dates(doc["fields"]))
        doc.setdefault("conflicts", [])
    q, err = parse_query(query)
    if err is not None:
        return {"ok": False, "refusal": err}

    docs = index["documents"]
    order = index["order"]
    findings: list = []
    family_ids: set = set()
    seed_ids: list = []
    if "family_of" in q:
        seed_ids = [doc_id for doc_id in order
                    if _doc_has_number(docs[doc_id], q["family_of"], q.get("number_kind", "any"))]
        family_field = "family" if q.get("family_scope") == "simple" else "inpadoc_family"
        missing = [doc_id for doc_id in seed_ids if not _field_values(docs[doc_id], family_field)]
        for doc_id in seed_ids:
            family_ids.update(str(v) for v in _field_values(docs[doc_id], family_field))
        if missing:
            findings.append(_finding(
                "patent.family_missing", "medium",
                "seed has no declared " + family_field + "; seed retained without inferred expansion",
                missing))
        if len(family_ids) > 1:
            findings.append(_finding(
                "patent.family_conflict", "medium",
                "seeds resolve to multiple declared family identifiers; groups retained without cross-family merge",
                seed_ids, [{"family_field": family_field, "family_ids": sorted(family_ids)}]))

    lower, upper = _query_intervals(q)
    hits = []
    date_missing: list = []
    date_invalid: list = []
    claim_missing: list = []
    for doc_id in order:
        doc = docs[doc_id]
        fields = doc["fields"]
        low = doc["text"].lower()
        if any(term.lower() in low for term in q["not"]):
            continue
        if not all(term.lower() in low for term in q["all"]):
            continue
        if q["any"] and not any(term.lower() in low for term in q["any"]):
            continue
        matched_filters: list = []
        if "family_of" in q:
            family_field = "family" if q.get("family_scope") == "simple" else "inpadoc_family"
            declared = {str(v) for v in _field_values(doc, family_field)}
            if doc_id not in seed_ids and not (declared & family_ids):
                continue
            matched_filters.append("family_of")
        if "number" in q:
            if not _doc_has_number(doc, q["number"], q.get("number_kind", "any")):
                continue
            matched_filters.append("number")
        if "family" in q:
            family_field = "family" if q.get("family_scope") == "simple" else "inpadoc_family"
            wanted = {str(v).casefold() for v in _values(q["family"])}
            declared = {str(v).casefold() for v in _field_values(doc, family_field)}
            if not (wanted & declared):
                continue
            matched_filters.append("family")
        simple_exact = True
        for key in ("status", "claim_version", "source_type", "document_type"):
            if key in q and q[key].casefold() not in {str(v).casefold()
                                                       for v in _field_values(doc, key)}:
                simple_exact = False
        if not simple_exact:
            if "claim_version" in q and not _field_values(doc, "claim_version"):
                claim_missing.append(doc_id)
            continue
        if "claim_version" in q:
            matched_filters.append("claim_version")
        for key in ("status", "source_type", "document_type"):
            if key in q:
                matched_filters.append(key)
        if "applicant" in q:
            if not any(q["applicant"].casefold() in str(v).casefold()
                       for v in _field_values(doc, "applicant")):
                continue
            matched_filters.append("applicant")
        if "source" in q:
            if q["source"].casefold() not in str(fields.get("source") or "").casefold():
                continue
            matched_filters.append("source")
        class_ok = True
        for key in ("cpc", "ipc"):
            if key not in q:
                continue
            prefix = normalise_patent_number(q[key])
            classes = [normalise_patent_number(v) for v in _field_values(doc, key)]
            if not any(value.startswith(prefix) for value in classes):
                class_ok = False
            else:
                matched_filters.append(key)
        if not class_ok:
            continue
        if "date_field" in q:
            if not _field_values(doc, q["date_field"]):
                date_missing.append(doc_id)
                continue
            if not any(info["valid"] for info in _date_infos(doc, q["date_field"])):
                date_invalid.append(doc_id)
                continue
            if not _date_overlap(doc, q["date_field"], lower, upper):
                continue
            matched_filters.extend(["date_from"] if "date_from" in q else [])
            matched_filters.extend(["date_to"] if "date_to" in q else [])

        matched_terms = sorted({term for term in q["all"] + q["any"]
                                if term.lower() in low})
        evidence_terms = list(matched_terms)
        for filter_name in matched_filters:
            for field in _filter_fields(filter_name, q):
                evidence_terms.extend(str(v) for v in _values(
                    (doc.get("evidence_fields") or {}).get(field)))
        passages = _passages(doc["paragraphs"], evidence_terms, doc_id)
        legal = _legal_status(fields)
        hit = {"doc_id": doc_id, "score": len(matched_terms) + len(set(matched_filters)),
               "matched_terms": matched_terms, "matched_filters": sorted(set(matched_filters)),
               "passages": passages, "metadata": fields, "source": _source(fields),
               "family": {"simple": fields.get("family"),
                          "inpadoc": fields.get("inpadoc_family")},
               "dates": doc["dates"], "legal_status": legal,
               "claim_version": fields.get("claim_version"),
               "document_type": fields.get("document_type", "unspecified")}
        hits.append(hit)
    hits.sort(key=lambda hit: (-hit["score"], order.index(hit["doc_id"])))

    if date_missing:
        findings.append(_finding(
            "patent.date_missing", "medium",
            "records excluded by the date filter lack " + q["date_field"] +
            "; no other date was substituted", date_missing))
    if date_invalid:
        findings.append(_finding(
            "patent.date_invalid", "medium",
            "records excluded by the date filter have no valid " + q["date_field"], date_invalid))
    if claim_missing:
        findings.append(_finding(
            "patent.claim_version_missing", "medium",
            "records excluded by a claim-version filter do not declare a version", claim_missing))
    hit_ids = {hit["doc_id"] for hit in hits}
    invalid_hit_dates = []
    date_order = []
    for doc_id in sorted(hit_ids):
        doc = docs[doc_id]
        for field, infos in (doc.get("dates") or {}).items():
            if any(not info["valid"] for info in infos):
                invalid_hit_dates.append(doc_id)
        priorities = [i for i in _date_infos(doc, "priority_date") if i["valid"]]
        filings = [i for i in _date_infos(doc, "filing_date") if i["valid"]]
        if priorities and filings and min(p["start"] for p in priorities) > max(
                f["end"] for f in filings):
            date_order.append(doc_id)
    if invalid_hit_dates:
        findings.append(_finding("patent.date_invalid", "medium",
                                 "hit metadata contains an invalid date", invalid_hit_dates))
    if date_order:
        findings.append(_finding("patent.date_order", "medium",
                                 "earliest priority date is after the filing date", date_order))
    # An absent family_of seed remains an honest clean empty; no family is inferred.
    required = set(q.get("require_fields") or [])
    claims_required_missing = [hit["doc_id"] for hit in hits
                               if q.get("require_claims")
                               and not _field_values(docs[hit["doc_id"]], "claim_version")]
    if claims_required_missing:
        findings.append(_finding("patent.claim_version_missing", "medium",
                                 "returned hits do not identify the source-located claim version",
                                 claims_required_missing))
    required_entries = []
    for hit in hits:
        for field in sorted(required):
            if not _field_values(docs[hit["doc_id"]], field):
                required_entries.append({"doc_id": hit["doc_id"], "field": field})
    if required_entries:
        findings.append(_finding("patent.field_missing", "medium",
                                 "required metadata is absent on returned hits",
                                 entries=required_entries))
    unverified = [hit["doc_id"] for hit in hits
                  if q.get("require_current_status") and not hit["legal_status"]["registry_verified"]]
    if unverified:
        findings.append(_finding("patent.status_unverified", "medium",
                                 "current official legal status is undetermined at the requested verification level",
                                 unverified))
    license_missing = [hit["doc_id"] for hit in hits if q.get("require_source_license")
                       and (not hit["source"].get("license") or not hit["source"].get("access"))]
    if license_missing:
        findings.append(_finding("patent.source_license_unknown", "medium",
                                 "returned source lacks an explicit licence or access classification",
                                 license_missing))

    collisions = []
    for hit in hits:
        doc = docs[hit["doc_id"]]
        for kind in NUMBER_FIELDS:
            for number in _field_values(doc, kind):
                peers = [peer for peer in order if peer != hit["doc_id"]
                         and number in [str(v) for v in _field_values(docs[peer], kind)]]
                if peers:
                    collisions.extend([hit["doc_id"], *peers])
    if "number" in q:
        for doc_id in order:
            if doc_id in hit_ids or not _doc_has_number(docs[doc_id], q["number"],
                                                       q.get("number_kind", "any")):
                continue
            collisions.append(doc_id)
    if collisions:
        findings.append(_finding("patent.number_collision", "medium",
                                 "one normalised number maps to multiple document ids; records were not merged",
                                 collisions))
    status_conflicts = []
    for number_kind in NUMBER_FIELDS:
        groups: dict = {}
        for doc_id in sorted(hit_ids):
            for number in _field_values(docs[doc_id], number_kind):
                groups.setdefault(str(number), []).append(doc_id)
        for number, doc_ids in groups.items():
            if len(doc_ids) < 2:
                continue
            states = {_label(docs[d]["fields"].get("status")) for d in doc_ids
                      if docs[d]["fields"].get("status") is not None}
            if len(states) > 1:
                status_conflicts.extend(doc_ids)
    if status_conflicts:
        findings.append(_finding("patent.status_conflict", "medium",
                                 "records sharing a normalised number carry conflicting status tokens",
                                 status_conflicts))
    metadata_entries = [{"doc_id": doc_id, **conflict}
                        for doc_id in sorted(hit_ids) for conflict in docs[doc_id]["conflicts"]]
    if metadata_entries:
        findings.append(_finding("patent.metadata_conflict", "medium",
                                 "structured metadata overrides conflicting text labels; both values are retained",
                                 entries=metadata_entries))

    change_records = [{"stage": "query", "action": "normalise_query_and_field_filters",
                       "details": q}]
    if "family_of" in q:
        change_records.append({"stage": "family", "action": "expand_declared_family",
                               "scope": q.get("family_scope"), "seed_ids": seed_ids,
                               "family_ids": sorted(family_ids),
                               "inference": "none; observed declared identifiers only"})
    result = {"query": q, "index_sha256": str(index.get("corpus_sha256", "")),
              "documents_indexed": len(order), "hits": hits, "empty": not hits,
              "findings": findings, "limits": [], "change_records": change_records}
    if not hits:
        result["note"] = ("no accessible document matches the declared query over " + str(len(order))
                          + " indexed document(s); reported as empty, never padded")
        if "family_of" in q and not seed_ids:
            result["note"] = "family seed is absent from the accessible snapshot; no family inferred"
    selected_scope = q.get("family_scope") if ("family" in q or "family_of" in q) else None
    result["families"] = _families(hits, docs, selected_scope)
    return {"ok": True, "result": _finalise(result, docs)}


def search(spec):
    """Run corpus (or prebuilt index) + query and attach build-level findings."""
    if not isinstance(spec, dict):
        return None, _refusal_result("search.spec_unreadable", "the spec is not a JSON object")
    if spec.get("query") is None:
        return None, _refusal_result("search.empty_query", "the spec declares no query")
    if isinstance(spec.get("index"), dict):
        built = {"ok": True, "index": spec["index"], "skipped": [],
                 "restricted": spec["index"].get("restricted", []),
                 "display_limited": spec["index"].get("display_limited", [])}
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
        result["change_records"].append({"stage": "index", "action": "skip_named_entries",
                                         "entries": built["skipped"]})
        result["findings"].append(_finding(
            "search.doc_skipped", "low",
            "corpus entries were skipped and named rather than silently merged",
            entries=built["skipped"]))
    restricted = built.get("restricted") or []
    if restricted:
        severity = "high" if not built["index"]["order"] else "medium"
        result["findings"].append(_finding(
            "patent.source_restricted", severity,
            "restricted records were excluded before indexing; no restricted text is returned",
            entries=restricted))
    result["restricted"] = restricted
    if restricted:
        result["change_records"].append({"stage": "permission", "action": "exclude_red_before_index",
                                         "entries": restricted, "text_retained": False})
    limited = built.get("display_limited") or []
    if limited:
        result["findings"].append(_finding(
            "patent.source_restricted", "medium",
            "yellow records were reduced to authorised metadata before indexing",
            entries=limited))
    result["display_limited"] = limited
    if limited:
        result["change_records"].append({"stage": "permission",
                                         "action": "reduce_yellow_to_authorised_metadata",
                                         "entries": limited, "raw_text_retained": False})
    _finalise(result, built["index"]["documents"])
    return built["index"], result
