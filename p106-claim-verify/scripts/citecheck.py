"""End-to-end citation and fact verification for an original Harbor case.

Primary use:
  python citecheck.py --case /input/case.json --out /app/output
  python citecheck.py --case /input/case.json --material /app/work/paper.txt \
      --out /app/output

Only --refresh-metadata performs network I/O (Crossref).  Offline runs compare
against supplied registry records and otherwise say undetermined.  Bibliographic
identity and evidence support are deliberately independent verdicts.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
import review_common as C  # noqa: E402

DOI_RX = re.compile(r"\b10\.\d{4,9}/[-._;()/:A-Z0-9]+", re.I)
YEAR_RX = re.compile(r"\b(?:19|20)\d{2}[a-z]?\b", re.I)
HEDGES = re.compile(r"\b(?:may|might|could|suggest(?:s|ed)?|possible|possibly|potential(?:ly)?|appears?|seems?|associated)\b|可能|或许|提示|相关", re.I)
CAUSAL = re.compile(r"\b(?:caus(?:e|es|ed|ing)|leads?\s+to|result(?:s|ed)?\s+in|improv(?:e|es|ed)|reduc(?:e|es|ed)|increas(?:e|es|ed)|decreas(?:e|es|ed)|effect\s+of)\b|导致|引起|改善|降低|提高", re.I)
NEGATION = re.compile(r"\b(?:not|no|never|neither|without|failed\s+to|did\s+not|does\s+not|non[- ]significant)\b|不|未|无|没有", re.I)
NUMBER_WORDS = {"zero": "0", "one": "1", "two": "2", "three": "3", "four": "4", "five": "5",
                "six": "6", "seven": "7", "eight": "8", "nine": "9", "ten": "10"}
ALIASES = {"审查报告": "audit_report", "依据与边界": "evidence_bounds", "结果状态": "result_state",
           "review_report": "audit_report", "evidence_and_boundaries": "evidence_bounds",
           "result_status": "result_state", "citation_results": "citation_checks",
           "fact_results": "fact_checks", "metadata_results": "metadata_checks"}


def _span_for_offset(doc: C.Document, start: int, end: int, text: str) -> dict:
    nearest = min(doc.spans, key=lambda s: abs(s["start"] - start)) if doc.spans else None
    span = dict(nearest or {"id": "S0000", "paragraph": 0, "sentence": 0, "section": "references", "kind": "sentence"})
    span.update({"text": text, "start": start, "end": end, "page": doc.page_at(start),
                 "line_start": doc.line_at(start), "line_end": doc.line_at(max(start, end - 1))})
    return span


def _surnames(value: Any) -> list[str]:
    if isinstance(value, str):
        parts = re.split(r"\s*(?:,|;|\band\b|&|、|，)\s*", value)
        names = []
        for part in parts:
            match = re.search(r"([A-Z][A-Za-z'’\-]+|[\u3400-\u9fff]{2,4})(?:\s+[A-Z][A-Za-z.\-]*)*$", part.strip())
            if match:
                names.append(match.group(1).lower())
        return sorted(set(names))
    if isinstance(value, list):
        names = []
        for author in value:
            if isinstance(author, str):
                names.extend(_surnames([author]))
            elif isinstance(author, dict):
                family = author.get("family") or author.get("lastName") or author.get("surname")
                if not family and isinstance(author.get("name"), str):
                    names.extend(_surnames([author["name"]]))
                elif family:
                    names.append(str(family).lower())
        return sorted(set(names))
    return []


def parse_reference(raw: str, key: str, locator: dict | None = None, structured: bool = False) -> dict:
    raw = C.normalise_space(raw)
    doi_match = DOI_RX.search(raw)
    doi = C.normalise_doi(doi_match.group(0)) if doi_match else ""
    year_match = YEAR_RX.search(raw)
    year = year_match.group(0)[:4] if year_match else ""
    title = ""
    title_confidence = "low"
    quoted = re.search(r"[\"“]([^\"”]{8,})[\"”]", raw)
    if quoted:
        title = quoted.group(1).strip()
        title_confidence = "high"
    elif year_match:
        tail = raw[year_match.end():].lstrip(" .):：")
        candidate = re.split(r"(?<=[.!?。！？])\s+", tail, maxsplit=1)[0]
        if len(candidate) >= 8 and not candidate.lower().startswith(("doi", "http", "vol.", "pp.")):
            title = candidate.strip(" .")
            title_confidence = "medium"
    if not title:
        cleaned = re.sub(r"^\s*(?:\[\d+\]|\d+[.)])\s*", "", raw)
        segments = re.split(r"(?<=[.!?。！？])\s+", cleaned)
        if len(segments) >= 2:
            candidate = segments[1]
            title = candidate.strip(" .")
            title_confidence = "low"
    authors_text = raw[:year_match.start()] if year_match else raw.split(". ", 1)[0]
    authors_reliable = bool(re.search(r",|\band\b|&|et\s+al|、|，|等", authors_text, re.I))
    return {"key": str(key), "raw": raw, "doi": doi, "title": title, "year": year,
            "authors_text": authors_text.strip(" ."), "authors": _surnames(authors_text) if authors_reliable else [],
            "title_confidence": "high" if structured else title_confidence,
            "source_shape": "structured" if structured else "parsed", "locator": locator}


def structured_references(case: dict) -> list[dict]:
    value = case.get("references") or case.get("bibliography") or []
    entries = value
    if isinstance(value, dict):
        entries = [dict(v, key=k) if isinstance(v, dict) else {"key": k, "raw": str(v)}
                   for k, v in value.items()]
    refs = []
    if not isinstance(entries, list):
        return refs
    for pos, entry in enumerate(entries):
        if isinstance(entry, str):
            refs.append(parse_reference(entry, str(pos + 1), structured=True))
            continue
        if not isinstance(entry, dict):
            continue
        raw = str(entry.get("raw") or entry.get("reference") or entry.get("text") or "")
        key = str(entry.get("key") or entry.get("id") or entry.get("label") or pos + 1)
        ref = parse_reference(raw or str(entry.get("title") or ""), key, entry.get("locator") if isinstance(entry.get("locator"), dict) else None, True)
        for field in ("title", "year"):
            if entry.get(field) is not None:
                ref[field] = str(entry[field])[:4] if field == "year" else str(entry[field])
        ref["doi"] = C.normalise_doi(entry.get("doi") or entry.get("DOI") or ref["doi"])
        if entry.get("authors") is not None or entry.get("author") is not None:
            ref["authors"] = _surnames(entry.get("authors", entry.get("author")))
            ref["authors_text"] = str(entry.get("authors", entry.get("author")))
        ref["title_confidence"] = "high" if ref["title"] else "low"
        ref["structured"] = entry
        refs.append(ref)
    return refs


def extract_references(doc: C.Document, case: dict) -> list[dict]:
    supplied = structured_references(case)
    if supplied:
        return supplied
    lines = list(re.finditer(r"[^\n\f]*(?:\n|\f|$)", doc.text))
    start_index = None
    for pos, match in enumerate(lines):
        heading = doc.heading(match.group(0).strip("\n\f"))
        if heading and re.fullmatch(r"(?:\d+(?:\.\d+)*\s*)?(?:references|bibliography|参考文献)", heading, re.I):
            start_index = pos + 1
            break
    if start_index is None:
        return []
    selected = []
    for match in lines[start_index:]:
        value = match.group(0).strip("\n\f")
        heading = doc.heading(value)
        if heading and re.match(r"^(?:appendix|supplement|附录|补充)", heading, re.I):
            break
        selected.append((match.start(), value))
    groups: list[tuple[str, list[str]]] = []
    current_key = ""
    current: list[str] = []
    for _, value in selected:
        marker = re.match(r"^\s*(?:\[(\d+)\]|(\d+)[.)])\s+", value)
        if marker:
            if current:
                groups.append((current_key or str(len(groups) + 1), current))
            current_key = marker.group(1) or marker.group(2)
            current = [value]
        elif not value.strip():
            if current and not re.search(r"\s", current[-1].strip()):
                pass
            if current and any(len(" ".join(current)) > 80 for _ in [0]):
                # Blank lines delimit author-year bibliographies only when no numbering exists.
                if not any(re.match(r"^\s*(?:\[\d+\]|\d+[.)])\s+", x) for x in current):
                    groups.append((str(len(groups) + 1), current))
                    current = []
        elif value.strip():
            current.append(value.strip())
    if current:
        groups.append((current_key or str(len(groups) + 1), current))
    refs = []
    for pos, (key, parts) in enumerate(groups):
        raw = C.normalise_space(" ".join(parts))
        if len(raw) < 12:
            continue
        needle = parts[0][:min(len(parts[0]), 60)]
        offset = doc.text.find(needle)
        if offset < 0:
            offset = selected[0][0] if selected else 0
        span = _span_for_offset(doc, offset, min(len(doc.text), offset + len(raw)), raw)
        ref = parse_reference(raw, key or str(pos + 1))
        ref["locator"] = doc.evidence(span)
        refs.append(ref)
    return refs


def _reference_aliases(ref: dict) -> set[str]:
    aliases = {str(ref.get("key") or "").lower()}
    if ref.get("authors") and ref.get("year"):
        aliases.add(ref["authors"][0] + str(ref["year"]))
    if ref.get("doi"):
        aliases.add(ref["doi"])
    return {x for x in aliases if x}


def link_citations(doc: C.Document, refs: list[dict]) -> list[dict]:
    by_key: dict[str, dict] = {}
    for ref in refs:
        for alias in _reference_aliases(ref):
            by_key.setdefault(alias, ref)
    instances = []
    for span in doc.spans:
        if span["kind"] == "heading" or re.search(r"references|bibliography|参考文献", span["section"], re.I):
            continue
        text = span["text"]
        markers: list[tuple[str, str, dict | None]] = []
        for match in re.finditer(r"\[\s*(\d+)(?:\s*([-–,;])\s*(\d+))?\s*\]", text):
            first, sep, last = match.group(1), match.group(2), match.group(3)
            keys = [first]
            if sep and last:
                if sep in "-–" and 0 < int(last) - int(first) <= 50:
                    keys = [str(x) for x in range(int(first), int(last) + 1)]
                else:
                    keys.append(last)
            for key in keys:
                markers.append((match.group(0), key, by_key.get(key)))
        for match in re.finditer(r"([A-Z][A-Za-z'’\-]+|[\u3400-\u9fff]{2,4})(?:\s+(?:et\s+al\.?|等))?\s*(?:,|\s)?\s*\(?\b((?:19|20)\d{2})\b\)?", text):
            surname, year = match.group(1).lower(), match.group(2)
            ref = by_key.get(surname + year)
            if ref:
                markers.append((match.group(0), str(ref["key"]), ref))
        seen = set()
        for marker, key, ref in markers:
            identity = (marker, key)
            if identity in seen:
                continue
            seen.add(identity)
            instances.append({"marker": marker, "reference_key": key, "reference": ref,
                              "claim": text, "span": span, "locator": doc.locator(span)})
    return instances


def registry_records(case: dict, sources: list[dict]) -> list[dict]:
    records = []
    for key in ("metadata_registry", "doi_registry", "verified_metadata", "crossref_records", "registry"):
        value = case.get(key)
        entries = value.values() if isinstance(value, dict) else value
        if isinstance(entries, (list, tuple)):
            records.extend(x for x in entries if isinstance(x, dict))
    records.extend(x for x in sources if isinstance(x, dict) and (x.get("doi") or x.get("title")))
    # Metadata-only supplied sources are valid registry snapshots even without full text.
    for key in ("sources", "external_sources", "cited_sources", "evidence_sources"):
        value = case.get(key)
        entries = value.values() if isinstance(value, dict) else value
        if isinstance(entries, (list, tuple)):
            records.extend(x for x in entries if isinstance(x, dict) and (x.get("doi") or x.get("title")))
    unique = []
    seen = set()
    for record in records:
        marker = (C.normalise_doi(record.get("doi") or record.get("DOI")), _registry_title(record).casefold(),
                  _registry_year(record), str(record.get("registry_locator") or record.get("locator") or ""),
                  C.sha256_text(str(record.get("text") or record.get("full_text") or "")))
        if marker in seen:
            continue
        seen.add(marker)
        unique.append(record)
    return unique


def fetch_crossref(doi: str, timeout: float) -> tuple[dict | None, str | None]:
    url = "https://api.crossref.org/works/" + urllib.parse.quote(doi, safe="")
    request = urllib.request.Request(url, headers={"Accept": "application/json", "User-Agent": "source-bound-citation-audit/1.0"})
    try:
        with urllib.request.urlopen(request, timeout=max(1.0, min(float(timeout), 30.0))) as response:
            payload = json.loads(response.read().decode("utf-8"))
        message = payload.get("message") if isinstance(payload, dict) else None
        if not isinstance(message, dict):
            return None, "Crossref response had no message object"
        record = dict(message)
        record["registry_source"] = "Crossref REST API"
        record["registry_locator"] = url
        return record, None
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError, ValueError, json.JSONDecodeError) as exc:
        return None, f"Crossref lookup failed for {doi}: {type(exc).__name__}: {exc}"


def _registry_year(record: dict) -> str:
    if record.get("year") is not None:
        return str(record["year"])[:4]
    for key in ("published", "published-print", "published-online", "issued", "created"):
        value = record.get(key)
        if isinstance(value, dict):
            parts = value.get("date-parts")
            if parts and isinstance(parts, list) and parts[0]:
                return str(parts[0][0])
            if value.get("date-time"):
                return str(value["date-time"])[:4]
    return ""


def _registry_title(record: dict) -> str:
    title = record.get("title")
    if isinstance(title, list):
        return str(title[0]) if title else ""
    return str(title or "")


def verify_metadata(ref: dict, registry: list[dict]) -> dict:
    base = {"reference_key": ref["key"], "reference_doi": ref.get("doi") or None,
            "reference_title": ref.get("title") or None, "overall": "undetermined",
            "doi_status": "undetermined", "title_status": "undetermined",
            "author_status": "undetermined", "year_status": "undetermined",
            "registry_source": None, "registry_locator": None, "mismatches": []}
    if not registry:
        base["reason"] = "no supplied registry record matched; offline metadata verification was not performed"
        return base
    candidates = []
    if ref.get("doi"):
        candidates = [r for r in registry if C.normalise_doi(r.get("doi") or r.get("DOI")) == ref["doi"]]
    if not candidates and ref.get("title"):
        candidates = [r for r in registry if C.f1(ref["title"], _registry_title(r)) >= 0.88]
    if len(candidates) != 1:
        base["reason"] = "no unique registry match" if not candidates else "ambiguous registry matches"
        base["candidate_count"] = len(candidates)
        return base
    record = candidates[0]
    base["registry_source"] = record.get("registry_source") or record.get("source") or "supplied registry"
    base["registry_locator"] = record.get("registry_locator") or record.get("url") or record.get("locator")
    reg_doi = C.normalise_doi(record.get("doi") or record.get("DOI"))
    if ref.get("doi") and reg_doi:
        base["doi_status"] = "match" if ref["doi"] == reg_doi else "mismatch"
    elif reg_doi and not ref.get("doi"):
        base["doi_status"] = "not_reported_in_reference"
    reg_title = _registry_title(record)
    if ref.get("title") and reg_title:
        score = C.f1(ref["title"], reg_title)
        base["title_similarity"] = round(score, 4)
        base["title_status"] = "match" if score >= (0.88 if ref.get("title_confidence") == "high" else 0.94) else "mismatch"
        base["registry_title"] = reg_title
    reg_authors = _surnames(record.get("authors", record.get("author")))
    if ref.get("authors") and reg_authors:
        base["author_status"] = "match" if set(ref["authors"]) == set(reg_authors) else "mismatch"
        base["reference_authors"] = ref["authors"]
        base["registry_authors"] = reg_authors
    reg_year = _registry_year(record)
    if ref.get("year") and reg_year:
        base["year_status"] = "match" if ref["year"] == reg_year else "mismatch"
        base["registry_year"] = reg_year
    for field in ("doi", "title", "author", "year"):
        if base[field + "_status"] == "mismatch":
            base["mismatches"].append(field)
    compared = [base[f + "_status"] for f in ("doi", "title", "author", "year")]
    if base["mismatches"]:
        base["overall"] = "mismatch"
    elif "match" in compared and all(x in {"match", "not_reported_in_reference"} for x in compared if x != "undetermined"):
        base["overall"] = "match" if ref.get("doi") and reg_doi else "undetermined"
    base["identity_note"] = "metadata identity does not establish that the source supports the claim or that the claim is true"
    return base


def numeric_tokens(text: str) -> list[str]:
    # Citation callouts are locators, not scientific quantities in the claim.
    scrubbed = re.sub(r"\[\s*\d+(?:\s*[-–,;]\s*\d+)*\s*\]", " ", text)
    scrubbed = re.sub(r"\(\s*(?:[A-Z][^()]*?,\s*)?(?:19|20)\d{2}\s*\)", "( )", scrubbed)
    values = []
    for match in re.finditer(r"(?<![\w.])(?:\d+(?:\.\d+)?|zero|one|two|three|four|five|six|seven|eight|nine|ten)(?![\w.])", scrubbed, re.I):
        value = match.group(0).lower()
        values.append(NUMBER_WORDS.get(value, value))
    return sorted(set(values))


def _scope(text: str) -> set[str]:
    scopes = set()
    for name, rx in (("human", r"\b(?:human|patients?|participants?|adults?|children)\b|人|患者|受试者"),
                     ("mouse", r"\b(?:mice|mouse|murine)\b|小鼠"), ("rat", r"\b(?:rats?)\b|大鼠"),
                     ("invitro", r"\b(?:in\s+vitro|cell\s+line|cells?)\b|体外|细胞")):
        if re.search(rx, text, re.I):
            scopes.add(name)
    return scopes


def assess_support(claim: str, evidence: str, declared: str | None = None) -> tuple[str, str, dict]:
    relevance = C.overlap(claim, evidence)
    similarity = C.f1(claim, evidence)
    missing_numbers = sorted(set(numeric_tokens(claim)) - set(numeric_tokens(evidence)))
    details = {"claim_relevance": round(relevance, 4), "claim_evidence_f1": round(similarity, 4),
               "missing_numbers": missing_numbers, "metadata_match_is_not_fact_truth": True}
    if relevance < 0.15 or similarity < 0.08:
        return "not_supported", "insufficient", details
    neg_claim = bool(NEGATION.search(claim))
    neg_evidence = bool(NEGATION.search(evidence))
    if neg_claim != neg_evidence and similarity >= 0.52:
        details["polarity_conflict"] = True
        return "not_supported", "refutes", details
    if bool(CAUSAL.search(claim)) and re.search(r"\b(?:associat(?:ed|ion)|correlat(?:ed|ion))\b|相关", evidence, re.I):
        details["scope_mismatch"] = "causal claim but associational evidence"
        return "partial", "scope_mismatch", details
    claim_scope, evidence_scope = _scope(claim), _scope(evidence)
    if "human" in claim_scope and evidence_scope and "human" not in evidence_scope:
        details["scope_mismatch"] = "human claim but non-human evidence"
        return "partial", "scope_mismatch", details
    if missing_numbers:
        details["scope_mismatch"] = "claim numbers are absent from evidence"
        return "partial", "numeric_mismatch", details
    claim_hedged = bool(HEDGES.search(claim))
    evidence_hedged = bool(HEDGES.search(evidence))
    if evidence_hedged and not claim_hedged and relevance >= 0.4:
        details["strength_mismatch"] = "hedged evidence but unqualified claim"
        return "partial", "strength_mismatch", details
    if relevance >= 0.72 and similarity >= 0.42:
        return "supports", "direct_support", details
    if declared in {"supports", "partial", "insufficient", "refutes", "not_supported"} and relevance >= 0.45:
        return ("partial" if declared == "supports" else declared), "declared_relation_requires_human_confirmation", details
    return "undetermined", "lexical_overlap_is_not_entailment", details


def match_source(ref: dict | None, sources: list[dict], explicit: str | None = None) -> dict | None:
    if explicit:
        for source in sources:
            if explicit.lower() in {str(source.get(k) or "").lower() for k in ("key", "id", "name", "doi")}:
                return source
    if not ref:
        return None
    if ref.get("doi"):
        exact = [s for s in sources if C.normalise_doi(s.get("doi")) == ref["doi"]]
        if len(exact) == 1:
            return exact[0]
    for source in sources:
        if str(ref.get("key")) in {str(source.get(k)) for k in ("key", "id", "name")}:
            return source
    if ref.get("title"):
        candidates = [s for s in sources if C.f1(ref["title"], s.get("title") or s.get("name")) >= 0.75]
        if len(candidates) == 1:
            return candidates[0]
    return None


def split_components(claim: str) -> list[str]:
    parts = [claim]
    if re.search(r"\s+(?:but|whereas|however|while)\s+|[；;]", claim, re.I):
        parts = [p.strip() for p in re.split(r"\s+(?:but|whereas|however|while)\s+|[；;]", claim, flags=re.I) if p.strip()]
    elif re.search(r"\s+and\s+", claim, re.I):
        halves = re.split(r"\s+and\s+", claim, maxsplit=1, flags=re.I)
        if len(halves) == 2 and re.search(r"\b(?:is|are|was|were|has|have|increases?|decreases?|reduces?|improves?|causes?)\b|提高|降低|导致", halves[1], re.I):
            parts = halves
    return parts if len(parts) > 1 and all(len(C.tokenize(p)) >= 2 for p in parts) else [claim]


def supplied_claims(case: dict) -> list[dict]:
    claims = case.get("claims") or case.get("claim_evidence") or []
    return [x for x in claims if isinstance(x, dict)] if isinstance(claims, list) else []


def audit(case: dict, materials: list[dict], material_errors: list[str], refresh: bool = False,
          timeout: float = 8.0) -> tuple[dict, list[str]]:
    if not materials:
        return {}, material_errors
    primary = materials[0]
    doc = C.Document(primary["text"], primary["name"])
    sources_raw = C.source_documents(case, materials)
    source_docs = [(src, C.Document(src["text"], src.get("name") or "cited source")) for src in sources_raw]
    refs = extract_references(doc, case)
    instances = link_citations(doc, refs)
    registry = registry_records(case, sources_raw)
    network_errors: list[str] = []
    network_used = False
    if refresh:
        for ref in refs:
            if ref.get("doi") and not any(C.normalise_doi(r.get("doi") or r.get("DOI")) == ref["doi"] for r in registry):
                record, error = fetch_crossref(ref["doi"], timeout)
                network_used = True
                if record:
                    registry.append(record)
                if error:
                    network_errors.append(error)

    findings: list[dict] = []
    pending: list[dict] = []
    passed: list[str] = []
    metadata_checks = []
    for ref in refs:
        raw = ref.get("raw") or ""
        if re.search(r"\bdoi\s*[:=]", raw, re.I) and not ref.get("doi"):
            findings.append({"rule": "cite.doi_malformed", "category": "引用规范", "severity": "medium",
                             "reference_key": ref["key"], "location": (ref.get("locator") or {}).get("locator"),
                             "excerpt": raw[:500], "verdict": "metadata_error",
                             "basis": "A DOI label is present but no syntactically valid DOI could be extracted.",
                             "fix": "Correct the DOI using the supplied authoritative record; do not infer one from the title."})
        check = verify_metadata(ref, registry)
        metadata_checks.append(check)
        loc = (ref.get("locator") or {}).get("locator") if isinstance(ref.get("locator"), dict) else str(ref.get("locator") or "") or None
        if check["overall"] == "mismatch":
            findings.append({"rule": "cite.metadata_mismatch", "category": "引用与事实核验", "severity": "high" if "doi" in check["mismatches"] or "title" in check["mismatches"] else "medium",
                             "reference_key": ref["key"], "location": loc, "excerpt": raw[:500],
                             "verdict": "metadata_mismatch", "fields": check["mismatches"], "metadata_check": check,
                             "basis": "The reference and a uniquely matched registry record disagree on one or more identity fields.",
                             "fix": "Reconcile the named fields against the registry locator and cite the correct version; do not change scientific support verdicts from metadata alone."})
        elif check["overall"] == "match":
            passed.append(f"metadata:{ref['key']}")
        else:
            pending.append({"kind": "metadata", "reference_key": ref["key"], "status": "undetermined",
                            "reason": check.get("reason") or "not all identity fields could be compared",
                            "needed": "authoritative DOI/title/author/year record or cited source full text"})

    for instance in instances:
        if instance["reference"] is None:
            findings.append({"rule": "cite.reference_not_in_list", "category": "引用支持", "severity": "high",
                             "reference_key": instance["reference_key"], "location": instance["locator"],
                             "excerpt": instance["claim"], "verdict": "citation_target_missing",
                             "basis": "The in-text callout has no corresponding parsed bibliography entry.",
                             "fix": "Add the intended bibliography entry or correct the callout, then rerun metadata and support checks."})

    citation_checks: list[dict] = []
    explicit_claims = supplied_claims(case)
    work_items: list[dict] = []
    if explicit_claims:
        ref_by_key = {str(r["key"]): r for r in refs}
        for pos, claim in enumerate(explicit_claims, 1):
            key = str(claim.get("reference_key") or claim.get("citation") or claim.get("source") or "")
            ref = ref_by_key.get(key)
            span = None
            quote = claim.get("manuscript_quote") or claim.get("location_quote")
            if isinstance(quote, str):
                span, _ = doc.find_quote(quote)
            if span is None:
                candidates = [s for s in doc.spans if C.overlap(claim.get("claim") or claim.get("text"), s["text"]) > 0.45]
                span = candidates[0] if candidates else (doc.spans[0] if doc.spans else None)
            evidence = claim.get("evidence") or claim.get("evidence_spans") or []
            if isinstance(evidence, dict):
                evidence = [evidence]
            work_items.append({"claim_id": str(claim.get("id") or f"C{pos:03d}"),
                               "claim": str(claim.get("claim") or claim.get("text") or ""),
                               "reference": ref, "reference_key": key, "span": span,
                               "evidence": evidence if isinstance(evidence, list) else [],
                               "declared": claim.get("support")})
    else:
        for pos, instance in enumerate(instances, 1):
            work_items.append({"claim_id": f"C{pos:03d}", "claim": instance["claim"],
                               "reference": instance["reference"], "reference_key": instance["reference_key"],
                               "span": instance["span"], "evidence": [], "declared": None})

    for item in work_items:
        ref = item["reference"]
        source = match_source(ref, sources_raw, str(item.get("reference_key") or ""))
        source_doc = next((d for s, d in source_docs if source is s), None) if source else None
        for component_no, component in enumerate(split_components(item["claim"]), 1):
            cid = item["claim_id"] + (f".{component_no}" if len(split_components(item["claim"])) > 1 else "")
            base = {"claim_id": cid, "claim": component, "reference_key": item["reference_key"] or (ref or {}).get("key"),
                    "claim_locator": doc.locator(item["span"]) if item["span"] else None,
                    "claim_excerpt": item["span"]["text"] if item["span"] else None,
                    "metadata_status": next((m["overall"] for m in metadata_checks if m["reference_key"] == (ref or {}).get("key")), "undetermined"),
                    "support_verdict": "undetermined", "evidence_quote": None, "evidence_locator": None,
                    "fact_verified": False}
            if not ref:
                base["reason"] = "citation target is absent or ambiguous"
                pending.append({"kind": "citation_support", **base})
                citation_checks.append(base)
                continue
            explicit_evidence = item["evidence"]
            evidence_span = None
            match_type = "none"
            evidence_error = None
            if explicit_evidence:
                ev = explicit_evidence[min(component_no - 1, len(explicit_evidence) - 1)]
                if isinstance(ev, str):
                    ev = {"quote": ev}
                if isinstance(ev, dict):
                    explicit_source = match_source(ref, sources_raw, str(ev.get("source") or "")) or source
                    explicit_doc = next((d for s, d in source_docs if s is explicit_source), None)
                    quote = ev.get("quote") or ev.get("excerpt") or ev.get("text")
                    if explicit_doc and quote:
                        evidence_span, match_type = explicit_doc.find_quote(str(quote))
                        source, source_doc = explicit_source, explicit_doc
                        if evidence_span is None:
                            evidence_error = "quoted evidence does not occur in the cited source"
                    elif not explicit_doc:
                        evidence_error = "cited source full text is unavailable"
                    if evidence_span is None and ev.get("locator") and quote:
                        base["evidence_quote"] = quote
                        base["evidence_locator"] = ev.get("locator")
                        base["reason"] = "locator supplied but quote could not be checked against full text"
            if evidence_span is None and source_doc and not evidence_error:
                candidates = [s for s in source_doc.spans if s["kind"] != "heading"
                              and not re.search(r"references|bibliography|参考文献", s["section"], re.I)]
                if candidates:
                    evidence_span = max(candidates, key=lambda s: (C.overlap(component, s["text"]), C.f1(component, s["text"])))
                    match_type = "best_lexical_span"
            if evidence_error:
                findings.append({"rule": "cite.evidence_quote_not_in_source", "category": "引用支持", "severity": "high",
                                 "claim_id": cid, "reference_key": ref["key"],
                                 "location": base["claim_locator"], "excerpt": component,
                                 "verdict": "evidence_not_verifiable", "basis": evidence_error,
                                 "fix": "Replace the quotation with an exact cited-source span and its page/paragraph/figure locator."})
                base["reason"] = evidence_error
            elif evidence_span is not None and source_doc:
                evidence = source_doc.evidence(evidence_span, (source or {}).get("name"))
                base.update({"evidence_quote": evidence["quote"], "evidence_locator": evidence["locator"],
                             "evidence_match_type": match_type, "evidence": evidence})
                verdict, relation, details = assess_support(component, evidence_span["text"], item.get("declared"))
                base.update({"support_verdict": verdict, "support_relation": relation, "alignment": details})
                if verdict == "not_supported":
                    findings.append({"rule": "cite.claim_not_supported", "category": "引用支持", "severity": "high",
                                     "claim_id": cid, "reference_key": ref["key"], "location": base["claim_locator"],
                                     "excerpt": component, "evidence_quote": evidence["quote"], "evidence_locator": evidence["locator"],
                                     "verdict": "not_supported", "basis": f"The cited span has insufficient lexical/polarity alignment ({details}).",
                                     "fix": "Replace the citation with a source that states this subclaim, or delete/narrow the unsupported wording."})
                elif verdict == "partial":
                    findings.append({"rule": "cite.claim_partially_supported", "category": "引用支持", "severity": "medium",
                                     "claim_id": cid, "reference_key": ref["key"], "location": base["claim_locator"],
                                     "excerpt": component, "evidence_quote": evidence["quote"], "evidence_locator": evidence["locator"],
                                     "verdict": "partial", "basis": str(details),
                                     "fix": "Narrow the claim to the cited population, numbers and modality, or add direct evidence for the omitted part."})
                elif verdict == "supports":
                    passed.append(f"claim:{cid}")
                    base["fact_verified"] = False
                else:
                    base["reason"] = "evidence span is relevant but entailment cannot be decided deterministically"
            if base["support_verdict"] == "undetermined":
                base.setdefault("reason", "cited source full text/evidence span is unavailable")
                pending.append({"kind": "citation_support", "claim_id": cid, "reference_key": ref["key"],
                                "status": "undetermined", "reason": base["reason"],
                                "needed": "exact cited-source evidence quote and locator"})
            citation_checks.append(base)

    # Cross-section numeric conflicts: compare only high-similarity statements with disjoint values.
    fact_checks: list[dict] = []
    abstract = doc.section_spans(r"abstract|摘要")
    body = [s for s in doc.spans if s["kind"] != "heading" and not re.search(r"abstract|摘要|references|参考文献", s["section"], re.I)]
    for a in abstract:
        a_nums = set(numeric_tokens(a["text"]))
        if not a_nums:
            continue
        best = None
        best_score = 0.0
        a_no_num = re.sub(r"\d+(?:\.\d+)?|\b(?:one|two|three|four|five|six|seven|eight|nine|ten)\b", " ", a["text"], flags=re.I)
        for b in body:
            b_no_num = re.sub(r"\d+(?:\.\d+)?|\b(?:one|two|three|four|five|six|seven|eight|nine|ten)\b", " ", b["text"], flags=re.I)
            score = C.f1(a_no_num, b_no_num)
            if score > best_score:
                best, best_score = b, score
        if best is None:
            continue
        b_nums = set(numeric_tokens(best["text"]))
        check = {"subject_excerpt": a["text"], "abstract_locator": doc.locator(a),
                 "body_locator": doc.locator(best), "abstract_values": sorted(a_nums),
                 "body_values": sorted(b_nums), "text_similarity_without_numbers": round(best_score, 4),
                 "status": "undetermined"}
        if best_score >= 0.62 and a_nums != b_nums and (a_nums - b_nums) and (b_nums - a_nums):
            check["status"] = "conflict"
            findings.append({"rule": "fact.numeric_conflict", "category": "事实核验", "severity": "high",
                             "location": doc.locator(a), "excerpt": a["text"],
                             "evidence_quote": best["text"], "evidence_locator": doc.locator(best),
                             "verdict": "source_internal_conflict", "basis": "Highly aligned abstract/body statements report disjoint values.",
                             "fix": "Check both values against the underlying table/data, correct the erroneous location, and record the correction."})
            fact_checks.append(check)
        elif best_score >= 0.62 and a_nums == b_nums:
            check["status"] = "consistent"
            passed.append("fact:" + a["id"])
            fact_checks.append(check)

    for error in material_errors + network_errors:
        pending.append({"kind": "material_or_registry_access", "status": "undetermined", "reason": error})
    findings = C.finalise_findings(findings)
    counts = C.severity_counts(findings)
    not_checked = ["method design beyond citation/fact implications", "statistical recomputation",
                   "full academic-integrity determination", "independent truth of supported claims"]
    limits = ["Metadata matching verifies bibliographic identity only; it never proves a scientific claim true.",
              "Support verdicts use only supplied/retrieved source text. Missing full text or registry access yields undetermined, not a false/supportive verdict.",
              "Automatic lexical alignment is a review aid; supported means direct textual support under the stated thresholds, not independent experimental validation.",
              "No network request is made unless --refresh-metadata is explicitly supplied."]
    status = "blocked" if counts.get("high") else ("review" if findings or pending or material_errors or network_errors else "clean")
    evidence_bounds = {"excerpts": [f.get("excerpt") for f in findings if f.get("excerpt")],
                       "citation_evidence": [{"claim_id": c["claim_id"], "quote": c.get("evidence_quote"),
                                              "locator": c.get("evidence_locator"), "support_verdict": c["support_verdict"]}
                                             for c in citation_checks],
                       "pending_review": pending,
                       "metadata_identity_is_not_fact_truth": True}
    source_summaries = [{k: v for k, v in m.items() if k != "text"} for m in materials]
    for record in registry:
        if record.get("registry_locator"):
            source_summaries.append({"name": record.get("registry_source") or "metadata registry",
                                     "path": record.get("registry_locator"), "role": "metadata_registry"})
    result = {"schema_version": C.SCHEMA_VERSION, "status": status, "ok": status != "undetermined",
              "audit_report": findings, "findings": findings, "citation_checks": citation_checks,
              "metadata_checks": metadata_checks, "fact_checks": fact_checks,
              "references": [{k: v for k, v in r.items() if k not in {"structured"}} for r in refs],
              "citation_instances": [{"marker": i["marker"], "reference_key": i["reference_key"],
                                      "claim": i["claim"], "locator": i["locator"]} for i in instances],
              "evidence_bounds": evidence_bounds, "uncertainty": pending,
              "result_state": C.result_state(findings, sorted(set(passed)), pending, not_checked),
              "severity_counts": counts, "sources": source_summaries,
              "checked": {"manuscript_chars": len(doc.text), "manuscript_sha256": doc.sha256,
                          "pages": doc.page_count, "sentences": len(doc.spans), "references": len(refs),
                          "citation_callouts": len(instances), "claims": len(citation_checks),
                          "metadata_records": len(registry), "cited_full_texts": len(source_docs),
                          "facets": {"fact_verification": "checked", "citation_support": "checked",
                                     "method_design": "not_checked_by_this_specialist_pass",
                                     "statistical_reporting": "numeric_conflicts_only",
                                     "argument_chain": "claim_evidence_strength_only",
                                     "academic_norms": "citation_identity_only"}},
              "limits": limits, "network_metadata_refresh": network_used,
              "change_records": [{"stage": "parse", "action": "segment references and link in-text callouts",
                                  "reference_count": len(refs), "callout_count": len(instances)},
                                 {"stage": "metadata", "action": "compare DOI/title/authors/year independently of support",
                                  "network_refresh_requested": refresh},
                                 {"stage": "support", "action": "bind exact evidence spans and assess each claim component",
                                  "claim_count": len(citation_checks), "values_fabricated": False}]}
    return result, pending


def run(case_path: str | Path, out_dir: str | Path, materials: list[str] | None = None,
        refresh: bool = False, timeout: float = 8.0) -> dict:
    case, error = C.read_json(case_path)
    if error:
        return C.refused({}, out_dir, "cite.case_unreadable", error, ALIASES)
    if not isinstance(case, dict):
        return C.refused({}, out_dir, "cite.case_not_object", "case.json must be a JSON object", ALIASES)
    records, errors = C.material_records(case, case_path, materials)
    if not records:
        detail = "no readable manuscript/full text was supplied"
        if errors:
            detail += "; " + "; ".join(errors)
        return C.refused(case, out_dir, "cite.no_manuscript", detail, ALIASES)
    try:
        result, _ = audit(case, records, errors, refresh, timeout)
        result = C.complete_contract(result, case, ALIASES)
        C.write_artifacts(out_dir, result)
        return result
    except Exception as exc:
        return C.refused(case, out_dir, "cite.internal_error",
                         f"citation audit could not complete: {type(exc).__name__}: {exc}", ALIASES)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="citecheck", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--case", required=True, help="original /input/case.json")
    parser.add_argument("--material", action="append", default=[], help="extracted manuscript text/PDF; repeat for cited sources")
    parser.add_argument("--out", required=True, help="output directory")
    parser.add_argument("--refresh-metadata", action="store_true", help="explicitly query Crossref for unmatched DOIs")
    parser.add_argument("--timeout", type=float, default=8.0, help="per-request Crossref timeout in seconds")
    args = parser.parse_args(argv)
    try:
        result = run(args.case, args.out, args.material, args.refresh_metadata, args.timeout)
    except Exception as exc:
        result = C.refused({}, args.out, "cite.runner_error", f"runner refused: {type(exc).__name__}: {exc}", ALIASES)
    print(C.summary_for_stdout(result))
    return C.EXIT_CODES.get(result.get("status"), 5)


if __name__ == "__main__":
    raise SystemExit(main())
