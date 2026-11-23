"""Deterministic Harbor case I/O shared by this package's specialist CLI.

Only caller-supplied local JSON/JSONL/CSV/TXT/MD materials are read.  This module
never fetches network content, invents a timestamp or treats a translation as an
original quotation.  All offsets refer to the exact retained source field.
"""
from __future__ import annotations

import copy
import csv
import hashlib
import json
import re
import unicodedata
from pathlib import Path
from typing import Any

TEXT_SUFFIXES = {".txt", ".md"}
PATH_KEYS = {
    "documents_path", "corpus_path", "records_path", "candidates_path",
    "reference_set_path", "references_path", "known_relevant_path", "qrels_path",
    "protocol_path", "materials_path", "path", "file_path",
}
BULKY = {
    "case_id", "output_contract", "output_contract_fields", "spec", "task",
    "documents", "studies", "corpus", "records", "candidates", "results",
    "reference_set", "references", "known_relevant", "known_relevant_set",
    "qrels", "documents_path", "reference_set_path", "records_path",
    "materials", "files", "attachments", "search_history", "iterations",
    "queries", "text", "full_text", "fullText", "body", "content", "abstract",
    "title", "concepts", "term_table", "terminology", "protocol",
    "screening_protocol", "criteria", "inclusion_criteria", "exclusion_criteria",
    "reviewer_decisions", "annotations", "adjudications", "screening_decisions",
}

LATIN_RE = re.compile(r"[^\W_][\w'’._-]*", re.UNICODE)
CJK_RE = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]+")
STOP = {
    "the", "and", "for", "with", "from", "this", "that", "study", "research",
    "using", "were", "was", "are", "our", "their", "between", "into", "among",
    "doi", "http", "https", "abstract", "introduction", "methods", "results",
}


class MaterialError(Exception):
    """Expected caller/material failure with a stable rule and process exit."""

    def __init__(self, rule: str, message: str, exit_code: int = 5):
        super().__init__(message)
        self.rule = rule
        self.exit_code = exit_code


def as_text(value: Any) -> str:
    if value is None or isinstance(value, (dict, list)):
        return ""
    return str(value)


def first(raw: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        value = raw.get(key)
        if value not in (None, "", []):
            return value
    return None


def contract_fields(contract: Any) -> tuple[list[str], list[str]]:
    """Support string, mapping, string-list and field/name/key object-list contracts."""
    warnings: list[str] = []
    if contract is None:
        return [], warnings
    if isinstance(contract, str):
        return [contract], warnings
    if isinstance(contract, dict):
        return [str(k) for k in contract], warnings
    if isinstance(contract, list):
        names: list[str] = []
        for i, item in enumerate(contract):
            if isinstance(item, str):
                names.append(item)
            elif isinstance(item, dict):
                name = item.get("field", item.get("name", item.get("key")))
                if name is None:
                    warnings.append(f"output_contract entry {i} has no field/name/key")
                else:
                    names.append(str(name))
            else:
                warnings.append(f"output_contract entry {i} has unsupported type {type(item).__name__}")
        return list(dict.fromkeys(names)), warnings
    warnings.append(f"output_contract has unsupported type {type(contract).__name__}")
    return [], warnings


def complete_contract(result: dict[str, Any], case: dict[str, Any], prefix: str) -> dict[str, Any]:
    """Engine values win; caller-carried scalar values are second; absence is null+limit."""
    if not isinstance(case, dict):
        return result
    result["case_id"] = case.get("case_id")
    result.setdefault("limits", [])
    fields, warnings = contract_fields(case.get("output_contract"))
    for note in warnings:
        if note not in result["limits"]:
            result["limits"].append(note)
    if "output_contract" in case:
        result["output_contract"] = copy.deepcopy(case["output_contract"])
    result["output_contract_fields"] = fields
    for name in fields:
        if name in {"output_contract", "output_contract_fields"}:
            continue
        if name in result:
            continue
        if name in case and name not in BULKY:
            result[name] = copy.deepcopy(case[name])
        else:
            result[name] = None
            note = f"output_contract field '{name}' remains null: not derivable from supplied evidence"
            result["limits"].append(note)
            result.setdefault("findings", []).append({
                "rule": f"{prefix}.contract_field_missing", "severity": "medium", "field": name,
            })
            if result.get("status") == "clean":
                result["status"] = "review"
    return result


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows),
                    encoding="utf-8")


def refusal_result(case: Any, rule: str, message: str, prefix: str, schema: str) -> dict[str, Any]:
    result = {
        "schema_version": schema, "status": "undetermined",
        "refusal": {"rule": rule, "message": str(message)[:1000]},
        "findings": [{"rule": rule, "severity": "high", "message": str(message)[:1000]}],
        "uncertainty": ["No specialist search workflow was completed."], "limits": [],
    }
    if isinstance(case, dict):
        return complete_contract(result, case, prefix)
    result["case_id"] = None
    return result


def fingerprint(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                     separators=(",", ":")).encode("utf-8")).hexdigest()


def merged_spec(case: dict[str, Any]) -> dict[str, Any]:
    nested = case.get("spec") if isinstance(case.get("spec"), dict) else {}
    spec = dict(nested)
    for key, value in case.items():
        if key not in {"case_id", "output_contract", "spec"}:
            spec[key] = value
    return spec


def normalize_doi(value: Any) -> str:
    text = as_text(value).strip()
    text = re.sub(r"^(?:https?://(?:dx\.)?doi\.org/|doi\s*:\s*)", "", text, flags=re.I)
    return text.strip().strip("<>. ;,").lower()


def normalize_title(value: Any) -> str:
    text = unicodedata.normalize("NFKC", as_text(value)).casefold()
    text = re.sub(r"[\W_]+", " ", text, flags=re.UNICODE)
    return " ".join(text.split())


def normalize_author(value: Any) -> str:
    if isinstance(value, list):
        value = value[0] if value else ""
    if isinstance(value, dict):
        family = first(value, "family", "lastName", "last_name", "surname")
        given = first(value, "given", "firstName", "first_name")
        literal = first(value, "literal", "name")
        value = family or literal or given or ""
    text = unicodedata.normalize("NFKC", as_text(value)).casefold()
    text = re.sub(r"\b(?:et al|and others)\b\.?", "", text)
    return re.sub(r"[^\w]+", "", text, flags=re.UNICODE)


def publication_year(raw: dict[str, Any]) -> str:
    value = first(raw, "year", "pubYear", "publication_year", "published", "publication_date",
                  "issued", "created", "date")
    if isinstance(value, dict):
        parts = value.get("date-parts")
        if isinstance(parts, list) and parts and isinstance(parts[0], list) and parts[0]:
            value = parts[0][0]
        else:
            value = first(value, "date", "year", "dateTime")
    match = re.search(r"(?:18|19|20|21)\d{2}", as_text(value))
    return match.group(0) if match else ""


def authors_value(raw: dict[str, Any]) -> Any:
    value = first(raw, "authors", "author", "authorString", "creator", "creators")
    if isinstance(value, dict):
        return value.get("name") or value
    return value


def records_from_payload(payload: Any, path: str = "inline") -> list[Any]:
    """Extract scientific records without converting a response envelope into prose."""
    if isinstance(payload, list):
        return payload
    if not isinstance(payload, dict):
        raise MaterialError("search.material_shape", f"{path} is neither a record list nor a response object")
    message = payload.get("message")
    if isinstance(message, dict):
        if isinstance(message.get("items"), list):
            return message["items"]
        if any(k in message for k in ("title", "DOI", "abstract", "author")):
            return [message]
    if isinstance(payload.get("resultList"), dict) and isinstance(payload["resultList"].get("result"), list):
        return payload["resultList"]["result"]
    for key in ("documents", "studies", "corpus", "records", "candidates", "references",
                "reference_set", "known_relevant", "items", "results", "views"):
        if isinstance(payload.get(key), list):
            return payload[key]
    if any(k in payload for k in ("id", "doc_id", "title", "DOI", "doi", "pmid", "text",
                                  "full_text", "fullText", "abstract", "abstractText", "body", "sections")):
        return [payload]
    raise MaterialError("search.material_shape", f"{path} contains no recognizable scientific records")


def resolve_path(text: str, case_dir: Path) -> Path:
    path = Path(text)
    if path.is_absolute():
        return path
    local = case_dir / path
    if local.exists():
        return local
    input_path = Path("/input") / path
    return input_path if input_path.exists() else local


def read_material(path: Path) -> Any:
    if not path.is_file():
        raise MaterialError("search.material_missing", f"declared material does not exist: {path}")
    try:
        if path.suffix.lower() == ".jsonl":
            return [json.loads(line) for line in path.read_text(encoding="utf-8-sig").splitlines()
                    if line.strip()]
        if path.suffix.lower() == ".json":
            return json.loads(path.read_text(encoding="utf-8-sig"))
        if path.suffix.lower() == ".csv":
            with path.open("r", encoding="utf-8-sig", newline="") as handle:
                return list(csv.DictReader(handle))
        if path.suffix.lower() in TEXT_SUFFIXES:
            return [{"id": path.stem, "text": path.read_text(encoding="utf-8-sig"),
                     "source": str(path), "source_scope": "provided_text"}]
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, csv.Error) as exc:
        raise MaterialError("search.material_unreadable", f"cannot read {path}: {exc}") from exc
    raise MaterialError("search.material_unsupported",
                        f"unsupported material type {path.suffix}; extract PDF/OCR text first")


def load_value(spec: dict[str, Any], keys: tuple[str, ...], case_dir: Path) -> tuple[Any, str | None]:
    """Load the first declared value, accepting either inline payload or explicit *_path."""
    for key in keys:
        if key in spec and spec[key] not in (None, ""):
            return spec[key], None
        path_key = key + "_path"
        if path_key in spec and isinstance(spec[path_key], str):
            path = resolve_path(spec[path_key], case_dir)
            return read_material(path), str(path)
    return None, None


def load_document_records(spec: dict[str, Any], case_dir: Path,
                          keys: tuple[str, ...] = ("documents", "studies", "corpus", "records", "candidates")) -> tuple[list[Any], list[str]]:
    value, source = load_value(spec, keys, case_dir)
    if value is None:
        materials = first(spec, "materials", "files", "attachments")
        raw_rows: list[Any] = []
        sources: list[str] = []
        if isinstance(materials, str):
            materials = [materials]
        if isinstance(materials, list):
            for item in materials:
                path_text = item if isinstance(item, str) else first(item, "path", "file_path") if isinstance(item, dict) else None
                if not path_text or re.match(r"^https?://", str(path_text)):
                    continue
                path = resolve_path(str(path_text), case_dir)
                rows = records_from_payload(read_material(path), str(path))
                raw_rows.extend(rows)
                sources.extend([str(path)] * len(rows))
        if raw_rows:
            return raw_rows, sources
        return [], []
    if source is not None:
        rows = records_from_payload(value, source)
        return rows, [source] * len(rows)
    return records_from_payload(value), ["inline"] * len(records_from_payload(value))


def field_unit(value: Any, field: str, doc_id: str, index: int) -> dict[str, Any] | None:
    text = as_text(value)
    if not text.strip():
        return None
    return {"unit": index, "field": field, "document_id": doc_id, "text": text}


def normalize_document(raw: Any, index: int, source_path: str = "inline") -> dict[str, Any]:
    """Normalize common Crossref/EuropePMC/local shapes while retaining source fields."""
    if isinstance(raw, str):
        raw = {"id": raw}
    if not isinstance(raw, dict):
        raise MaterialError("search.document_invalid", f"record {index} is {type(raw).__name__}, not object/string")
    original = raw
    if isinstance(raw.get("message"), dict) and any(k in raw["message"] for k in ("title", "DOI", "abstract")):
        raw = dict(raw["message"])
        raw.setdefault("source", original.get("source") or "Crossref supplied response")
    doi = normalize_doi(first(original, "doi", "DOI") or first(raw, "doi", "DOI"))
    pmid = as_text(first(raw, "pmid", "PMID")).strip()
    explicit_id = first(original, "id", "doc_id", "uid", "record_id", "work_id") or first(raw, "id", "doc_id", "uid")
    doc_id = as_text(explicit_id).strip() or doi or pmid or f"doc-{index + 1:03d}"
    title_value = first(raw, "title", "article-title", "articleTitle")
    if isinstance(title_value, list):
        title_value = title_value[0] if title_value else ""
    title = as_text(title_value).strip()
    author = authors_value(raw)
    first_author = normalize_author(author)
    year = publication_year(raw)
    source_name = first(original, "source", "source_name", "database", "source_title") or first(raw, "source", "source_name", "database")
    version = first(original, "version", "source_version", "version_kind", "publication_status") or first(raw, "version", "source_version", "version_kind", "publication_status")
    language = first(original, "language", "lang", "body_language", "content_language") or first(raw, "language", "lang", "body_language", "content_language")
    work_id = as_text(first(original, "work_id", "study_id", "cluster_id", "workId") or first(raw, "work_id", "study_id", "cluster_id", "workId")).strip()
    relation = first(original, "relation", "relation_type", "version_of", "translation_of", "trans_of") or first(raw, "relation_type", "version_of", "translation_of", "trans_of")
    identifiers = {doc_id, doi, pmid}
    aliases = first(original, "identifiers", "aliases", "alternate_ids") or first(raw, "identifiers", "aliases", "alternate_ids")
    if isinstance(aliases, str):
        identifiers.add(aliases)
    elif isinstance(aliases, list):
        identifiers.update(as_text(x) for x in aliases if as_text(x).strip())
    elif isinstance(aliases, dict):
        identifiers.update(as_text(x) for x in aliases.values() if as_text(x).strip())
    identifiers = {x for x in identifiers if x and x.strip()}

    units: list[dict[str, Any]] = []
    for field in ("id", "doc_id", "doi", "DOI", "pmid", "PMID", "title", "article-title", "articleTitle",
                  "authorString", "journal", "container-title", "source", "database", "language", "lang",
                  "body_language", "content_language", "version", "version_kind", "work_id", "study_id"):
        value = raw.get(field)
        values = value if isinstance(value, list) else [value]
        for j, item in enumerate(values):
            if isinstance(item, (dict, list)):
                continue
            unit = field_unit(item, field + (f"[{j}]" if isinstance(value, list) else ""), doc_id, len(units))
            if unit:
                units.append(unit)
    if author and not units:
        unit = field_unit(as_text(author), "author", doc_id, len(units))
        if unit:
            units.append(unit)
    full_text_available = False
    for key in ("full_text", "fullText", "full_text_xml", "body", "content"):
        value = raw.get(key)
        if isinstance(value, str) and value.strip():
            unit = field_unit(value, key, doc_id, len(units))
            if unit:
                units.append(unit)
            full_text_available = True
    abstract = first(raw, "abstract", "abstractText", "summary")
    if isinstance(abstract, list):
        abstract = "\n".join(as_text(x) for x in abstract if as_text(x))
    unit = field_unit(abstract, "abstract", doc_id, len(units))
    if unit:
        units.append(unit)
    unit = field_unit(raw.get("text"), "text", doc_id, len(units))
    if unit:
        units.append(unit)
    sections = raw.get("sections")
    if isinstance(sections, dict):
        sections = [{"title": k, "text": v} for k, v in sections.items()]
    if isinstance(sections, list):
        for j, sec in enumerate(sections):
            if isinstance(sec, str):
                unit = field_unit(sec, f"sections[{j}]", doc_id, len(units))
                if unit:
                    units.append(unit)
                    full_text_available = True
            elif isinstance(sec, dict):
                text = first(sec, "text", "content", "body")
                if isinstance(text, list):
                    for k, part in enumerate(text):
                        value = first(part, "text", "content") if isinstance(part, dict) else part
                        unit = field_unit(value, f"sections[{j}].paragraphs[{k}]", doc_id, len(units))
                        if unit:
                            units.append(unit)
                            full_text_available = True
                else:
                    unit = field_unit(text, f"sections[{j}].text", doc_id, len(units))
                    if unit:
                        units.append(unit)
                        full_text_available = True
    for field in ("paragraphs", "pages"):
        rows = raw.get(field)
        if isinstance(rows, list):
            for j, row in enumerate(rows):
                value = first(row, "text", "content") if isinstance(row, dict) else row
                unit = field_unit(value, f"{field}[{j}].text", doc_id, len(units))
                if unit:
                    if isinstance(row, dict):
                        for meta in ("page", "page_number", "section", "paragraph"):
                            if meta in row:
                                unit[meta] = row[meta]
                    units.append(unit)
                    full_text_available = True
    units = [u for u in units if u]
    if not units:
        raise MaterialError("search.document_no_text", f"record '{doc_id}' has no usable identifier, title or text")
    if raw.get("full_text_available") is True:
        full_text_available = True
    scope = as_text(first(raw, "source_scope", "coverage", "availability")).lower()
    abstract_only = bool(raw.get("abstract_only")) or "abstract" in scope or (
        bool(unit) and not full_text_available and not raw.get("text") and not sections)
    if "full translation" in scope or as_text(version).lower() in {"full_translation", "publisher_full_translation"}:
        full_text_available = True
    source = {
        "material_path": source_path,
        "name": as_text(source_name).strip() or None,
        "database": as_text(first(raw, "database", "source_name")).strip() or None,
        "type": as_text(first(raw, "source_type")).strip() or None,
        "url": as_text(first(raw, "url", "URL")).strip() or None,
        "version": as_text(version).strip() or None,
        "license": as_text(first(raw, "license", "licence")).strip() or None,
    }
    text = "\n".join(u["text"] for u in units)
    metadata = {
        "title": title or None, "doi": doi or None, "pmid": pmid or None, "year": year or None,
        "first_author": first_author or None,
        "authors": author if isinstance(author, str) else None,
        "journal": as_text(first(raw, "journal", "container-title", "journalTitle")).strip() or None,
        "language": as_text(language).strip() or None,
        "version": as_text(version).strip() or None,
        "retracted": first(raw, "retracted", "isRetracted"),
        "access": first(raw, "access", "access_level"),
    }
    return {
        "doc_id": doc_id, "work_id": work_id or None, "doi": doi, "pmid": pmid,
        "title": title, "normalized_title": normalize_title(title), "first_author": first_author,
        "year": year, "identifiers": sorted(identifiers), "units": units, "text": text,
        "metadata": metadata, "source": source, "relation": relation,
        "full_text_available": full_text_available, "abstract_only": abstract_only,
        "query_id": first(original, "query_id", "queryId", "search_id"),
        "query": first(original, "query", "search_query"),
        "query_field": first(original, "query_field", "field", "search_field"),
        "retrieval_round": first(original, "retrieval_round", "iteration", "round", "phase"),
        "original": original,
    }


def normalize_documents(raw_docs: list[Any], sources: list[str]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    docs: list[dict[str, Any]] = []
    omissions: list[dict[str, Any]] = []
    for i, raw in enumerate(raw_docs):
        source = sources[i] if i < len(sources) else "inline"
        if isinstance(raw, dict) and as_text(raw.get("access")).lower() in {"red", "restricted", "paywalled"} \
                and not first(raw, "title", "DOI", "doi", "id", "doc_id"):
            omissions.append({"index": i, "reason": "access restricted and no matchable metadata", "id": raw.get("id")})
            continue
        try:
            docs.append(normalize_document(raw, i, source))
        except MaterialError as exc:
            omissions.append({"index": i, "reason": str(exc), "rule": exc.rule,
                              "id": raw.get("id") if isinstance(raw, dict) else None})
    return docs, omissions


def term_occurrences(text: str, term: str, limit: int = 50) -> list[tuple[int, int]]:
    """Case-insensitive exact phrase matching with Latin word boundaries.

    CJK runs use substring semantics because they have no spaces.  Latin uses
    boundaries so 'cat' cannot match 'catastrophe'.  Offsets come from a regex over
    the ORIGINAL text, not a case-folded/normalized copy whose length may change.
    """
    if not text or not term:
        return []
    phrase = str(term).strip()
    if not phrase:
        return []
    if CJK_RE.search(phrase):
        pattern = re.escape(phrase)
    else:
        pattern = r"(?<![\w])" + re.escape(phrase) + r"(?![\w])"
    out: list[tuple[int, int]] = []
    try:
        for match in re.finditer(pattern, text, flags=re.IGNORECASE | re.UNICODE):
            out.append((match.start(), match.end()))
            if len(out) >= limit:
                break
    except re.error:
        return []
    return out


def evidence_for(doc: dict[str, Any], terms: list[str], limit: int = 12) -> list[dict[str, Any]]:
    evidence: list[dict[str, Any]] = []
    for unit in doc["units"]:
        for term in terms:
            for start, end in term_occurrences(unit["text"], term):
                locator = {"document_id": doc["doc_id"], "unit": unit["unit"],
                           "source_field": unit["field"], "start": start, "end": end}
                for meta in ("page", "page_number", "section", "paragraph"):
                    if meta in unit:
                        locator[meta] = unit[meta]
                evidence.append({
                    "term": term, "quote": unit["text"][start:end], "locator": locator,
                    "text_origin": "supplied_original_field", "source": doc["source"],
                })
                if len(evidence) >= limit:
                    return evidence
    return evidence


def text_terms(text: str) -> list[str]:
    """Language-neutral lexical features, not a claim of linguistic tokenization."""
    terms = {m.group(0).casefold() for m in LATIN_RE.finditer(text or "")}
    for run in CJK_RE.findall(text or ""):
        if len(run) == 1:
            terms.add(run)
        else:
            terms.update(run[i:i + 2] for i in range(len(run) - 1))
    return sorted(t for t in terms if len(t.strip()) > 0 and t not in STOP)


def status_block(status: str, completed: list[Any], unfinished: list[Any], empty: list[Any],
                 conflicts: list[Any], access: list[Any], uncertainty: list[Any]) -> dict[str, Any]:
    return {"运行状态": status, "已完成": completed, "未完成": unfinished,
            "空结果": empty, "冲突": conflicts, "权限或接口异常": access,
            "不确定性": uncertainty}
