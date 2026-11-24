"""Dependency-free, source-bound scholarly retrieval primitives.

This module does not perform network I/O.  Query URLs are plans for later human or
service execution; every returned hit comes from an actually supplied export.
The same file is vendored only into the three target skills, never imported across
packages or from the older shared search engine.
"""
from __future__ import annotations

import copy
import csv
import hashlib
import json
import math
import re
import unicodedata
from collections import Counter
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

SCHEMA_VERSION = "source-bound-retrieval/v2"
EXIT = {"clean": 0, "review": 3, "blocked": 4, "undetermined": 5}
BULKY = {
    "case_id", "output_contract", "output_contract_fields", "section", "spec",
    "query", "queries", "corpus", "documents", "records", "studies", "papers",
    "results", "index", "text", "full_text", "hits", "search", "answers",
    "status", "findings", "limits", "uncertainty", "检索结果", "证据记录", "状态说明",
}


class RetrievalError(Exception):
    def __init__(self, rule: str, message: str, exit_code: int = 5):
        super().__init__(message)
        self.rule, self.exit_code = rule, exit_code


def dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2) + "\n"


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(dumps(value), encoding="utf-8")


def write_csv(path: Path, rows: list[dict[str, Any]], preferred: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = list(preferred)
    for row in rows:
        for key in row:
            if key not in fields:
                fields.append(key)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({k: (json.dumps(v, ensure_ascii=False, separators=(",", ":"))
                                  if isinstance(v, (dict, list)) else "" if v is None else v)
                             for k, v in row.items()})


def load_case(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RetrievalError("retrieval.case_unreadable", f"case is not readable UTF-8 JSON: {exc}") from exc
    if not isinstance(value, dict):
        raise RetrievalError("retrieval.case_not_object", "case must be a JSON object", 4)
    return value


def merged_spec(case: dict[str, Any]) -> dict[str, Any]:
    spec = copy.deepcopy(case.get("spec")) if isinstance(case.get("spec"), dict) else {}
    for key, value in case.items():
        if key not in {"spec", "case_id", "output_contract"}:
            spec[key] = copy.deepcopy(value)
    return spec


def contract_fields(contract: Any) -> tuple[list[str], list[str]]:
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
    return [str(contract)], [f"scalar output_contract {type(contract).__name__} was treated as one field name"]


def complete_contract(result: dict[str, Any], spec: dict[str, Any], case: dict[str, Any]) -> dict[str, Any]:
    result["case_id"] = case.get("case_id") if case else spec.get("case_id")
    result.setdefault("limits", [])
    if not isinstance(case, dict):
        return result
    fields, warnings = contract_fields(case.get("output_contract"))
    result["limits"].extend(w for w in warnings if w not in result["limits"])
    if "output_contract" in case:
        result["output_contract"] = copy.deepcopy(case["output_contract"])
    result["output_contract_fields"] = fields
    for name in fields:
        if name in {"output_contract", "output_contract_fields"}:
            continue
        if name in result:
            continue
        # Caller-carried response fields never override derived execution state or
        # bulky source content.  They are provenance defaults, not claimed results.
        source = case if name in case else spec
        if name in source and name not in BULKY:
            result[name] = copy.deepcopy(source[name])
        else:
            result[name] = None
            result["limits"].append(f"output_contract field '{name}' remains null: not derivable from supplied evidence")
            result.setdefault("findings", []).append({
                "rule": "retrieval.contract_field_missing", "severity": "medium", "field": name})
            if result.get("status") == "clean":
                result["status"] = "review"
    return result


def refusal_result(case: dict[str, Any] | None, rule: str, message: str) -> dict[str, Any]:
    result = {
        "schema_version": SCHEMA_VERSION, "status": "undetermined",
        "case_id": (case or {}).get("case_id"),
        "refusal": {"rule": rule, "message": str(message)[:1000]},
        "findings": [{"rule": rule, "severity": "high", "message": str(message)[:1000]}],
        "uncertainty": ["No source-bound retrieval/screening run completed."],
        "limits": ["no documents, database hit counts, scientific facts or human decisions were inferred"],
        "检索结果": {"候选文献": [], "排序/筛选结果": [], "遗漏说明": [str(message)[:500]]},
        "证据记录": {"query_log": [], "evidence": []},
        "状态说明": {"运行状态": "undetermined", "空结果": False, "失败": str(message)[:500],
                   "权限或接口异常": [], "冲突": [], "不确定性": ["input could not be executed"]},
    }
    return complete_contract(result, merged_spec(case) if case else {}, case or {})


_TEXT_KEYS = ("text", "full_text", "fullText", "abstract", "abstractText", "sections", "pages", "message", "title")
_PATH_KEYS = {"documents_path", "corpus_path", "records_path", "materials_path", "file_path", "path"}
_CONTAINER_KEYS = ("documents", "records", "corpus", "studies", "papers", "works", "candidates", "results")


def records_from_payload(payload: Any, path: str) -> list[Any]:
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        message = payload.get("message")
        if isinstance(message, dict):
            if isinstance(message.get("items"), list):
                return message["items"]
            if any(k in message for k in ("title", "DOI", "abstract")):
                return [message]
        if isinstance(payload.get("resultList"), dict) and isinstance(payload["resultList"].get("result"), list):
            return payload["resultList"]["result"]
        for key in _CONTAINER_KEYS:
            if isinstance(payload.get(key), list):
                return payload[key]
        if any(k in payload for k in _TEXT_KEYS) or "DOI" in payload or "doi" in payload:
            return [payload]
    raise RetrievalError("retrieval.material_shape", f"{path} contains no scholarly record list or supported response")


def _read_ris(text: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    current: dict[str, Any] = {}
    tag_map = {"TI": "title", "T1": "title", "AB": "abstract", "N2": "abstract", "DO": "doi",
               "PY": "year", "Y1": "year", "JO": "journal", "JF": "journal", "T2": "journal",
               "UR": "url", "KW": "keywords", "TY": "publication_type", "ID": "id"}
    for line in text.replace("\r\n", "\n").split("\n"):
        match = re.match(r"^([A-Z][A-Z0-9])\s+-\s?(.*)$", line)
        if match:
            tag, value = match.groups()
            if tag == "TY" and current:
                rows.append(current)
                current = {}
            if tag == "ER":
                if current:
                    rows.append(current)
                    current = {}
                continue
            key = tag_map.get(tag)
            if tag in {"AU", "A1"}:
                current.setdefault("authors", []).append(value)
            elif key:
                if key == "keywords":
                    current.setdefault(key, []).append(value)
                elif key in current:
                    current[key] = str(current[key]) + "\n" + value
                else:
                    current[key] = value
        elif current and line.strip():
            # RIS continuations belong to the most recent field.  JSON output
            # preserves the actual supplied words rather than inventing values.
            current["continuation"] = str(current.get("continuation", "")) + "\n" + line.strip()
    if current:
        rows.append(current)
    if not rows:
        raise RetrievalError("retrieval.material_shape", "RIS input contains no TY/ER records")
    return rows


def read_material(path: Path) -> list[Any]:
    if not path.is_file():
        raise RetrievalError("retrieval.material_missing", f"declared material is absent: {path}")
    suffix = path.suffix.lower()
    try:
        text = path.read_text(encoding="utf-8-sig")
        if suffix == ".json":
            return records_from_payload(json.loads(text), str(path))
        if suffix == ".jsonl":
            return records_from_payload([json.loads(line) for line in text.splitlines() if line.strip()], str(path))
        if suffix == ".csv":
            return list(csv.DictReader(text.splitlines()))
        if suffix == ".ris":
            return _read_ris(text)
        if suffix in {".txt", ".md"}:
            return [{"id": path.stem, "text": text, "source": str(path), "source_scope": "provided_excerpt"}]
    except RetrievalError:
        raise
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, csv.Error) as exc:
        raise RetrievalError("retrieval.material_unreadable", f"cannot read {path}: {exc}") from exc
    raise RetrievalError("retrieval.material_unsupported",
                         f"unsupported material {path.suffix}; PDF must be converted by an actual text/OCR tool first")


def _collect_paths(value: Any, parent: str = "") -> list[str]:
    paths: list[str] = []
    if isinstance(value, dict):
        for key, item in value.items():
            if key in _PATH_KEYS and isinstance(item, str) and not re.match(r"^https?://", item):
                paths.append(item)
            elif key in {"materials", "files", "attachments", "exports", "source_files"}:
                paths.extend(_collect_paths(item, key))
    elif isinstance(value, list) and parent in {"materials", "files", "attachments", "exports", "source_files"}:
        for item in value:
            if isinstance(item, str) and not re.match(r"^https?://", item):
                paths.append(item)
            else:
                paths.extend(_collect_paths(item, parent))
    return list(dict.fromkeys(paths))


def _invert_abstract(index: Any) -> str:
    if not isinstance(index, dict):
        return ""
    positions: list[tuple[int, str]] = []
    for word, places in index.items():
        if isinstance(places, list):
            positions.extend((int(pos), str(word)) for pos in places if isinstance(pos, int))
    return " ".join(word for _, word in sorted(positions))


def _as_text(value: Any) -> str:
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return str(value)
    return ""


def _first(raw: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        value = raw.get(key)
        if value not in (None, "", []):
            return value
    return None


def _list_text(value: Any) -> list[str]:
    if value is None:
        return []
    values = value if isinstance(value, list) else [value]
    out: list[str] = []
    for item in values:
        if isinstance(item, dict):
            candidate = _first(item, "name", "display_name", "term", "given", "family", "authorString", "keyword")
            if candidate is None and (item.get("given") or item.get("family")):
                candidate = " ".join(str(item.get(k, "")).strip() for k in ("given", "family")).strip()
        else:
            candidate = item
        text = _as_text(candidate)
        if text:
            out.append(text)
    return out


def normalize_doi(value: Any) -> str:
    doi = _as_text(value)
    doi = re.sub(r"^(?:https?://(?:dx\.)?doi\.org/|doi:\s*)", "", doi, flags=re.I).strip()
    return doi.lower()


def normalize_title(value: Any) -> str:
    text = unicodedata.normalize("NFKC", _as_text(value)).casefold()
    return "".join(ch for ch in text if ch.isalnum())


def _year(raw: dict[str, Any]) -> int | None:
    value = _first(raw, "year", "pubYear", "publication_year")
    if value is None:
        for key in ("publication_date", "firstPublicationDate", "date"):
            match = re.match(r"^(\d{4})", _as_text(raw.get(key)))
            if match:
                value = match.group(1)
                break
    if value is None and isinstance(raw.get("issued"), dict):
        parts = raw["issued"].get("date-parts")
        if isinstance(parts, list) and parts and isinstance(parts[0], list) and parts[0]:
            value = parts[0][0]
    try:
        year = int(str(value)[:4])
        return year if 1000 <= year <= 9999 else None
    except (TypeError, ValueError):
        return None


def _structured_text(value: Any) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        chunks = []
        for item in value:
            if isinstance(item, dict):
                chunks.append(_as_text(_first(item, "text", "content", "body", "title")))
            else:
                chunks.append(_as_text(item))
        return "\n".join(x for x in chunks if x)
    if isinstance(value, dict):
        return "\n".join(f"{key}: {_structured_text(item)}" for key, item in value.items())
    return _as_text(value)


def _source_quality(raw: dict[str, Any], material_path: str) -> dict[str, Any]:
    declaration = " ".join(str(raw.get(k, "")) for k in ("source", "source_database", "database", "publisher", "source_type"))
    combined = (declaration + " " + material_path).casefold()
    if "crossref" in combined:
        return {"score": 0.90, "basis": "supplied Crossref response/export; bibliographic registry trace", "scope": "provenance_only"}
    if "europe" in combined and "pmc" in combined:
        return {"score": 0.90, "basis": "supplied Europe PMC response/export; identifier-aware biomedical index trace", "scope": "provenance_only"}
    if "openalex" in combined:
        return {"score": 0.85, "basis": "supplied OpenAlex response/export; open scholarly index trace", "scope": "provenance_only"}
    if "publisher" in combined or "出版" in combined:
        return {"score": 0.90, "basis": "supplied publisher-labelled response; publication-status was not independently refetched", "scope": "provenance_only"}
    if declaration.strip():
        return {"score": 0.65, "basis": "named source supplied by case; registry/peer-review status not independently verified", "scope": "provenance_only"}
    return {"score": 0.40, "basis": "local supplied record with no independently verified registry response", "scope": "provenance_only"}


def normalize_record(raw: Any, index: int, dataset_id: str = "inline") -> dict[str, Any]:
    if isinstance(raw, str):
        raw = {"text": raw}
    if not isinstance(raw, dict):
        raise RetrievalError("retrieval.record_invalid", f"record {index} is {type(raw).__name__}, not an object/string")
    original = raw
    if isinstance(raw.get("message"), dict) and any(k in raw["message"] for k in ("title", "DOI", "abstract")):
        merged = dict(raw["message"])
        for key in ("id", "source", "source_database", "database", "query_id"):
            if key in raw and key not in merged:
                merged[key] = raw[key]
        raw = merged
    title_value = _first(raw, "title", "display_name", "article-title")
    title = _as_text(title_value[0] if isinstance(title_value, list) and title_value else title_value)
    if isinstance(raw.get("journalInfo"), dict) and isinstance(raw["journalInfo"].get("journal"), dict):
        raw = dict(raw)
        raw.setdefault("journal", raw["journalInfo"]["journal"].get("title"))
    publication_type_value = _first(raw, "publication_type", "pubType", "type", "subtype")
    if publication_type_value is None and isinstance(raw.get("pubTypeList"), dict):
        publication_type_value = raw["pubTypeList"].get("pubType")
    journal_value = _first(raw, "journal", "container-title", "journalTitle", "host_venue")
    if isinstance(journal_value, dict):
        journal_value = _first(journal_value, "title", "display_name", "name")
    journal = _as_text(journal_value[0] if isinstance(journal_value, list) and journal_value else journal_value)
    authors_raw = _first(raw, "authors", "author", "authorString", "authorships")
    if isinstance(authors_raw, list):
        unwrapped = []
        for item in authors_raw:
            unwrapped.append(item.get("author", item) if isinstance(item, dict) else item)
        authors_raw = unwrapped
    authors = _list_text(authors_raw)
    if len(authors) == 1 and isinstance(authors_raw, str) and re.search(r"[,;]", authors_raw):
        authors = [x.strip() for x in re.split(r"[,;]", authors_raw) if x.strip()]
    doi_value = _first(raw, "doi", "DOI")
    doi = normalize_doi(doi_value)
    identifier = str(_first(original, "id", "doc_id", "uid") or _first(raw, "id", "pmid", "PMID", "openalex_id")
                     or (f"doi:{doi}" if doi else "") or f"record-{index + 1:03d}")
    abstract_value = _first(raw, "abstract", "abstractText", "summary")
    abstract = _as_text(abstract_value) if isinstance(abstract_value, str) else _structured_text(abstract_value)
    if not abstract:
        abstract = _invert_abstract(raw.get("abstract_inverted_index"))
    body = _structured_text(_first(raw, "full_text", "fullText", "body", "content", "sections", "pages", "text"))
    keywords = _list_text(_first(raw, "keywords", "keyword", "mesh_terms", "topics"))
    year = _year(raw)
    url = _as_text(_first(raw, "url", "URL", "link", "resource"))
    if isinstance(raw.get("primary_location"), dict):
        url = url or _as_text(raw["primary_location"].get("landing_page_url"))
    doi_syntax = (not doi) or re.match(r"^10\.\d{4,9}/\S+$", doi, flags=re.I) is not None
    fields = {"title": title, "abstract": abstract, "keywords": "\n".join(keywords), "body": body}
    metadata = {
        "title": title or None, "authors": authors, "year": year, "journal": journal or None,
        "doi": doi or None, "doi_url": f"https://doi.org/{doi}" if doi and doi_syntax else None,
        "pmid": _as_text(_first(raw, "pmid", "PMID")) or None, "url": url or None,
        "language": _as_text(raw.get("language")) or None,
        "publication_type": ", ".join(_list_text(publication_type_value)) or None,
        "publication_status": _as_text(_first(raw, "publication_status", "status", "subtype")) or None,
        "version": _as_text(_first(raw, "version", "source_version")) or None,
        "publisher": _as_text(raw.get("publisher")) or None,
        "citation_count": raw.get("cited_by_count", raw.get("citation_count")),
    }
    required = {"title": title, "authors": authors, "year": year, "journal": journal,
                "doi": doi if doi_syntax else None, "abstract": abstract}
    missing = [name for name, value in required.items() if value in (None, "", [])]
    material_path = str(raw.get("_material_path") or dataset_id)
    source_record = {
        "dataset_id": dataset_id, "dataset_row": index,
        "declared_source": _as_text(_first(original, "source", "source_database", "database")) or None,
        "query_id": _as_text(_first(original, "query_id", "search_id")) or None,
        "material_path": material_path, "url": url or None,
        "remote_hit_count": original.get("source_hit_count") if isinstance(original.get("source_hit_count"), int) else None,
        "access": _as_text(_first(raw, "access", "access_level", "availability")) or None,
    }
    # Selected source-supported fields are retained for conflict/opinion handling;
    # the engine never interprets a domain label as an actual scientific result.
    assertions = {key: copy.deepcopy(raw[key]) for key in
                  ("answer", "opinion", "stance", "direction", "conclusion", "finding", "comparison_key",
                   "study_id", "conflicting_opinion", "design", "study_design") if key in raw}
    return {
        "record_id": identifier, "dataset_id": dataset_id, "dataset_row": index,
        "metadata": metadata, "fields": fields, "source": source_record,
        "source_quality": _source_quality(raw, material_path),
        "metadata_completeness": {"score": round((6 - len(missing)) / 6, 6), "missing_fields": missing,
                                  "note": "Presence/parse completeness only; not factual verification or research quality."},
        "doi_valid_syntax": doi_syntax, "assertions": assertions,
        "raw_decision": original.get("decision", original.get("included")),
    }


def load_records(spec: dict[str, Any], case_dir: Path) -> list[dict[str, Any]]:
    raw_records: list[Any] | None = None
    dataset_ids: list[str] = []
    for key in ("documents", "records", "corpus", "studies", "papers", "works", "candidates"):
        if key in spec:
            if not isinstance(spec[key], list):
                raise RetrievalError("retrieval.records_invalid", f"{key} must be a list")
            raw_records = spec[key]
            dataset_ids = ["inline"] * len(raw_records)
            break
    if raw_records is None:
        paths = _collect_paths(spec)
        if not paths:
            raise RetrievalError("retrieval.no_documents", "case supplies neither candidate records nor authorized material paths")
        raw_records = []
        for text in paths:
            path = Path(text)
            if not path.is_absolute():
                candidate = case_dir / path
                input_candidate = Path("/input") / path
                path = candidate if candidate.exists() else input_candidate if input_candidate.exists() else candidate
            loaded = read_material(path)
            for item in loaded:
                if isinstance(item, dict):
                    item = dict(item)
                    item["_material_path"] = str(path)
                raw_records.append(item)
                dataset_ids.append(str(path))
    if not raw_records:
        raise RetrievalError("retrieval.no_documents", "the supplied candidate set is empty", 4)
    records: list[dict[str, Any]] = []
    for i, raw in enumerate(raw_records):
        dataset_id = dataset_ids[i] if i < len(dataset_ids) else "inline"
        if isinstance(raw, dict) and str(_first(raw, "access", "access_level") or "").casefold() in {"restricted", "red", "paywalled"}:
            # Preserve a metadata-only tombstone; no restricted body is serialized.
            clean = {k: copy.deepcopy(v) for k, v in raw.items()
                     if k in {"id", "doc_id", "doi", "DOI", "title", "authors", "author", "year", "journal",
                              "source", "source_database", "access", "access_level"}}
            clean["_material_path"] = raw.get("_material_path", dataset_id)
            record = normalize_record(clean, i, dataset_id)
            record["access_blocked"] = True
        else:
            record = normalize_record(raw, i, dataset_id)
            record["access_blocked"] = False
        records.append(record)
    return records


def deduplicate(records: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    """Cluster exact-DOI and exact-normalized-title exports, retaining every row.

    Same-title/different-DOI-or-year records are version candidates, not silently
    asserted exact duplicates.  Primary selection favours a declared formal
    publication and then metadata completeness, never citation/reputation.
    """
    groups: list[list[dict[str, Any]]] = []
    doi_group: dict[str, int] = {}
    title_group: dict[str, int] = {}
    for record in sorted(records, key=lambda r: r["dataset_row"]):
        doi = record["metadata"].get("doi") if record.get("doi_valid_syntax", True) else None
        title = normalize_title(record["metadata"].get("title"))
        candidates = {g for g in (doi_group.get(doi) if doi else None,
                                  title_group.get(title) if title else None) if g is not None}
        if not candidates:
            groups.append([record])
            gi = len(groups) - 1
        else:
            gi = min(candidates)
            groups[gi].append(record)
            # Merge any cross-linked groups instead of losing a transitively shared DOI.
            for other in sorted(candidates - {gi}, reverse=True):
                groups[gi].extend(groups[other])
                for moved in groups[other]:
                    md = moved["metadata"]
                    if md.get("doi"):
                        doi_group[md["doi"]] = gi
                    nt = normalize_title(md.get("title"))
                    if nt:
                        title_group[nt] = gi
                groups[other] = []
        if doi:
            doi_group[doi] = gi
        if title:
            title_group[title] = gi
    works: list[dict[str, Any]] = []
    audit: list[dict[str, Any]] = []
    conflicts: list[dict[str, Any]] = []
    for group in groups:
        if not group:
            continue
        def primary_key(record: dict[str, Any]) -> tuple:
            status = str(record["metadata"].get("publication_status") or "").casefold()
            formal = (0 if any(x in status for x in ("preprint", "posted")) else
                      2 if any(x in status for x in ("journal", "published", "versionofrecord", "article")) else 1)
            return (formal, record["metadata_completeness"]["score"], record["source_quality"]["score"],
                    -record["dataset_row"])
        primary = max(group, key=primary_key)
        gid = "work-" + hashlib.sha256((primary["record_id"] + "\0" + str(group[0]["dataset_row"])).encode()).hexdigest()[:14]
        dois = {r["metadata"].get("doi") for r in group if r["metadata"].get("doi")}
        years = {r["metadata"].get("year") for r in group if r["metadata"].get("year") is not None}
        titles = {normalize_title(r["metadata"].get("title")) for r in group if r["metadata"].get("title")}
        journals = {_as_text(r["metadata"].get("journal")).casefold() for r in group if r["metadata"].get("journal")}
        statuses = [str(r["metadata"].get("publication_status") or "").casefold() for r in group]
        has_preprint = any(any(x in status for x in ("preprint", "posted")) for status in statuses)
        has_formal = any(any(x in status for x in ("journal", "published", "versionofrecord")) for status in statuses)
        group_kind = "single"
        if len(group) > 1:
            if len(dois) > 1 or len(years) > 1 or (has_preprint and has_formal):
                group_kind = "version_or_metadata_conflict"
            else:
                group_kind = "exact_doi_or_title_duplicate"
        member_ids = [r["record_id"] for r in group]
        conflict_items = []
        if len(dois) > 1:
            conflict_items.append({"field": "doi", "values": sorted(dois), "resolution": "version candidate; human review required"})
        if len(years) > 1:
            conflict_items.append({"field": "year", "values": sorted(years), "resolution": "source/year conflict retained; not guessed"})
        if len(group) > 1 and has_preprint and has_formal:
            conflict_items.append({"field": "publication_status", "values": sorted(set(statuses)),
                                   "resolution": "preprint/formal version candidate; no duplicate scientific evidence count"})
        if len(journals) > 1 and len(group) > 1:
            conflict_items.append({"field": "journal", "values": sorted(journals), "resolution": "source conflict retained"})
        work = copy.deepcopy(primary)
        work.update({
            "work_id": gid, "member_ids": member_ids, "member_rows": [r["dataset_row"] for r in group],
            "dedup_status": group_kind, "duplicate_of": primary["record_id"],
            "sources": [r["source"] for r in group], "source_qualities": [r["source_quality"] for r in group],
        })
        works.append(work)
        for record in group:
            audit.append({"record_id": record["record_id"], "dataset_id": record["dataset_id"],
                          "dataset_row": record["dataset_row"], "work_id": gid,
                          "duplicate_of": None if record is primary else primary["record_id"],
                          "group_id": gid, "dedup_status": group_kind,
                          "accounting": "primary_export" if record is primary else "retained_group_member_not_independent_evidence"})
        if conflict_items:
            conflicts.append({"work_id": gid, "member_ids": member_ids, "items": conflict_items})
    works.sort(key=lambda w: min(w["member_rows"]))
    audit.sort(key=lambda r: r["dataset_row"])
    conflicts.sort(key=lambda c: c["work_id"])
    return works, audit, conflicts


_STOP = {"the", "a", "an", "and", "or", "of", "for", "with", "without", "in", "on", "to", "from", "by",
         "is", "are", "was", "were", "be", "been", "how", "what", "which", "does", "do", "can", "study",
         "research", "using", "use", "based", "between", "effect", "effects", "我们", "如何", "什么", "哪些",
         "是否", "研究", "作用", "影响", "文献", "检索", "相关", "方法", "进行", "以及", "一个", "一种"}


def analyzer(text: Any) -> list[str]:
    value = unicodedata.normalize("NFKC", str(text or "")).casefold()
    tokens = re.findall(r"[a-z0-9]+(?:-[a-z0-9]+)*", value)
    tokens += [part for token in list(tokens) if "-" in token for part in token.split("-")]
    for run in re.findall(r"[\u3400-\u9fff]+", value):
        tokens.extend(run)
        tokens.extend(run[i:i + 2] for i in range(len(run) - 1))
    return [token for token in tokens if token not in _STOP]


def query_terms(text: Any) -> list[str]:
    value = unicodedata.normalize("NFKC", str(text or "")).casefold()
    terms = set(re.findall(r"[a-z][a-z0-9_-]{1,}", value)) - _STOP
    for run in re.findall(r"[\u3400-\u9fff]{2,}", value):
        if len(run) <= 6:
            terms.add(run)
        else:
            # Long unsegmented Chinese questions cannot be treated as one exact
            # title phrase.  Character bigrams are a disclosed lexical fallback.
            terms.update(run[i:i + 2] for i in range(len(run) - 1))
    return sorted(terms - _STOP)


def occurrence_spans(text: str, term: str) -> list[tuple[int, int]]:
    """Original-string spans; never compute offsets in a differently sized casefold."""
    if not text or not term:
        return []
    return [(m.start(), m.end()) for m in re.finditer(re.escape(str(term)), text, flags=re.I)]


def negated_prefix(text: str, start: int) -> bool:
    """Conservative scope negation immediately preceding a term, not topic sentiment."""
    prefix = text[max(0, start - 40):start].strip().casefold()
    if not prefix:
        return False
    if re.search(r"(?:不是|并非|不属于|不包括|没有|无关|离题)\s*(?:关于|研究|文献|论文)?\s*$", prefix):
        return True
    return re.search(r"(?:^|[\s,;，；。])(?:not|no|never|without|off[- ]scope|irrelevant)"
                     r"(?:\s+(?:a|an|the|this|that|actual|real|study|research|paper))*\W*$", prefix) is not None


def positive_spans(text: str, term: str) -> list[tuple[int, int]]:
    return [(start, end) for start, end in occurrence_spans(text, term) if not negated_prefix(text, start)]


def mask_negated_spans(text: str, term: str) -> str:
    spans = [(s, e) for s, e in occurrence_spans(text, term) if negated_prefix(text, s)]
    chars = list(text)
    for start, end in spans:
        chars[start:end] = " " * (end - start)
    return "".join(chars)


def field_term_match(text: str, term: str) -> bool:
    spans = occurrence_spans(text, term)
    if spans:
        return bool(positive_spans(text, term))
    qtokens = analyzer(term)
    return bool(qtokens) and all(q in analyzer(text) for q in qtokens)


def term_in_fields(term: str, fields: dict[str, str]) -> bool:
    if not str(term or "").strip():
        return False
    return any(field_term_match(text or "", str(term)) for text in fields.values() if text)


def matched_terms(terms: list[str], fields: dict[str, str]) -> list[str]:
    return sorted({term for term in terms if term_in_fields(term, fields)}, key=lambda x: (x.casefold(), x))


class BM25Index:
    """Independently computed field-weighted BM25 with auditable components."""
    FIELD_WEIGHTS = {"title": 4.0, "abstract": 2.0, "keywords": 2.5, "body": 1.0}

    def __init__(self, works: list[dict[str, Any]], k1: float = 1.2, b: float = 0.75):
        self.works = {w["work_id"]: w for w in works}
        self.order = [w["work_id"] for w in works]
        self.k1, self.b = k1, b
        self.tokens: dict[str, dict[str, list[str]]] = {}
        self.stats: dict[str, dict[str, Any]] = {}
        for field in self.FIELD_WEIGHTS:
            df: Counter[str] = Counter()
            lengths: list[int] = []
            for work_id in self.order:
                text = self.works[work_id]["fields"].get(field, "")
                tokens = analyzer(text)
                self.tokens.setdefault(work_id, {})[field] = tokens
                lengths.append(len(tokens))
                df.update(set(tokens))
            self.stats[field] = {"df": dict(df), "avg_length": sum(lengths) / len(lengths) if lengths else 0.0}

    def score(self, work_id: str, terms: list[str]) -> dict[str, Any]:
        work = self.works[work_id]
        terms_detail = []
        components = {field: 0.0 for field in self.FIELD_WEIGHTS}
        observed: list[str] = []
        n_docs = max(1, len(self.order))
        for term in sorted(set(terms), key=lambda x: x.casefold()):
            found = False
            for field, weight in self.FIELD_WEIGHTS.items():
                tokens = self.tokens[work_id][field]
                qtokens = analyzer(term)
                text = work["fields"].get(field, "")
                exact_spans = occurrence_spans(text, term)
                accepted_spans = positive_spans(text, term)
                phrase_hit = bool(accepted_spans)
                if exact_spans and not phrase_hit:
                    continue
                if not phrase_hit and not all(q in tokens for q in qtokens):
                    continue
                found = True
                # Negative scope occurrences neither qualify a record nor inflate tf.
                scored_tokens = analyzer(mask_negated_spans(text, term)) if exact_spans else tokens
                tf = sum(scored_tokens.count(q) for q in qtokens)
                if phrase_hit:
                    tf = max(tf, 1)
                if not tf:
                    continue
                field_stats = self.stats[field]
                idf = sum(math.log(1 + (n_docs - field_stats["df"].get(q, 0) + 0.5) /
                                   (field_stats["df"].get(q, 0) + 0.5)) for q in qtokens)
                avg = field_stats["avg_length"] or len(tokens) or 1.0
                denominator = tf + self.k1 * (1 - self.b + self.b * len(tokens) / avg)
                contribution = weight * idf * (self.k1 + 1) * tf / denominator
                components[field] += contribution
                terms_detail.append({"term": term, "field": field, "tf": tf,
                                     "score": round(contribution, 8), "phrase_match": phrase_hit})
            if found:
                observed.append(term)
        rounded = {key: round(value, 8) for key, value in components.items()}
        raw = round(sum(components.values()), 8)
        return {"bm25": raw, "normalized_relevance": round(raw / (raw + 4.0), 8) if raw else 0.0,
                "matched_terms": observed, "field_components": rounded, "term_field_scores": terms_detail,
                "parameters": {"k1": self.k1, "b": self.b, "field_weights": self.FIELD_WEIGHTS}}


# A deliberately small, disclosed seed lexicon.  It is a recall aid, not a claim
# that database-side MeSH mappings were resolved.  Case-supplied term mappings take
# precedence and are the correct path for specialised topics.
SEED_GROUPS = [
    {"id": "protein-structure-prediction", "label": "蛋白质结构预测", "role": "object",
     "terms": ["蛋白质结构预测", "蛋白结构预测", "protein structure prediction", "protein folding", "蛋白质折叠"]},
    {"id": "attention", "label": "注意力机制", "role": "method",
     "terms": ["attention", "self-attention", "transformer", "注意力", "自注意力", "transformers"]},
    {"id": "solid-electrolyte", "label": "固态电解质", "role": "object",
     "terms": ["固态电解质", "固体电解质", "solid electrolyte", "solid-state electrolyte", "solid state electrolyte"]},
    {"id": "grain-boundary", "label": "晶界", "role": "mechanism",
     "terms": ["晶界", "grain boundary", "grain boundaries", "grain-boundary"]},
    {"id": "ionic-conductivity", "label": "离子电导率", "role": "outcome",
     "terms": ["离子电导率", "ionic conductivity", "ion conductivity", "锂离子电导"]},
    {"id": "additive-manufacturing", "label": "增材制造", "role": "method",
     "terms": ["增材制造", "additive manufacturing", "3d printing", "3-d printing", "3d打印"]},
    {"id": "microstructure", "label": "微观组织", "role": "outcome",
     "terms": ["微观组织", "显微组织", "microstructure", "microstructural"]},
    {"id": "randomized-trial", "label": "随机对照试验", "role": "design",
     "terms": ["随机对照试验", "随机试验", "randomized controlled trial", "randomised controlled trial", "rct"],
     "controlled_terms": [{"vocabulary": "MeSH", "term": "Randomized Controlled Trial", "mapping": "candidate; verify in MeSH before execution"}]},
    {"id": "chronic-pain", "label": "慢性疼痛", "role": "population",
     "terms": ["慢性疼痛", "chronic pain", "persistent pain"],
     "controlled_terms": [{"vocabulary": "MeSH", "term": "Chronic Pain", "mapping": "candidate; verify in MeSH before execution"}]},
    {"id": "exercise-therapy", "label": "运动疗法", "role": "intervention",
     "terms": ["运动疗法", "居家运动", "exercise therapy", "home exercise", "physical exercise"],
     "controlled_terms": [{"vocabulary": "MeSH", "term": "Exercise Therapy", "mapping": "candidate; verify in MeSH before execution"}]},
]


def _concept_from_value(value: Any, index: int, explicit: bool = True) -> dict[str, Any]:
    if isinstance(value, str):
        value = {"label": value}
    if not isinstance(value, dict):
        value = {"label": str(value)}
    if "terms" not in value:
        for key in ("concept", "term", "text", "name", "value"):
            if isinstance(value.get(key), str):
                value = dict(value, terms=[value[key]])
                break
    terms_raw = value.get("terms")
    if isinstance(terms_raw, dict):
        terms_raw = [terms_raw.get("base", terms_raw.get("label", [])), terms_raw.get("synonyms", []),
                     terms_raw.get("translations", [])]
    if not isinstance(terms_raw, list):
        terms_raw = [terms_raw] if terms_raw is not None else []
    label = _as_text(_first(value, "label", "name", "concept", "id")) or f"concept-{index + 1}"
    seeds = []
    if not terms_raw:
        seeds = [label]
    for item in terms_raw + seeds:
        terms_raw2 = item if isinstance(item, list) else [item]
        for term in terms_raw2:
            text = _as_text(term)
            if text and text not in seeds:
                seeds.append(text)
    synonyms = _as_list(value.get("synonyms"))
    translations = value.get("translations") if isinstance(value.get("translations"), dict) else {}
    for vals in translations.values():
        synonyms.extend(_as_list(vals))
    controlled = value.get("controlled_terms", value.get("controlled_vocabulary", []))
    if isinstance(controlled, str):
        controlled = [{"vocabulary": "case-declared", "term": controlled, "mapping": "case supplied"}]
    elif isinstance(controlled, list):
        controlled = [{"vocabulary": "case-declared", "term": x, "mapping": "case supplied"} if isinstance(x, str) else x
                      for x in controlled]
    else:
        controlled = []
    trusted_controlled = [item for item in controlled
                          if not any(flag in str(item.get("mapping", "")).casefold()
                                     for flag in ("candidate", "verify", "unverified"))
                          if isinstance(item, dict)]
    all_terms = list(dict.fromkeys(seeds + synonyms + _list_text(trusted_controlled)))
    # Apply exact disclosed seed mappings to explicit labels/terms as well.
    for seed in SEED_GROUPS:
        hay = (label + "\n" + "\n".join(seeds)).casefold()
        if any(term.casefold() in hay or hay in term.casefold() for term in seed["terms"] if len(hay) >= 2):
            all_terms.extend(x for x in seed["terms"] if x not in all_terms)
            if not controlled:
                controlled = copy.deepcopy(seed.get("controlled_terms", []))
    return {"concept_id": _as_text(value.get("concept_id") or value.get("id")) or f"C{index + 1:02d}",
            "label": label, "role": _as_text(value.get("role") or value.get("facet")) or "topic",
            "terms": list(dict.fromkeys(seeds)), "synonyms": list(dict.fromkeys(synonyms)),
            "controlled_terms": controlled, "all_terms": list(dict.fromkeys(all_terms)),
            "required": value.get("required", True), "provenance": "case_supplied" if explicit else "declared_seed_lexicon"}


def _as_list(value: Any) -> list[str]:
    if value is None:
        return []
    values = value if isinstance(value, list) else [value]
    return [text for item in values if (text := _as_text(item))]


def research_question_text(spec: dict[str, Any]) -> str:
    # Structured Boolean queries are executable syntax, never natural-language
    # text from which new broad OR terms (including literal 'all') may be mined.
    if not _first(spec, "research_question", "question") and isinstance(spec.get("query"), dict) \
            and any(key in spec["query"] for key in ("all", "any", "not")):
        return ""
    value = _first(spec, "research_question", "question", "query", "topic", "task")
    if isinstance(value, dict):
        return "; ".join(f"{key}: {_structured_text(item)}" for key, item in value.items()
                         if key not in {"concepts", "subquestions"})
    return _as_text(value)


def derive_concepts(spec: dict[str, Any], question: str | None = None) -> list[dict[str, Any]]:
    raw = _first(spec, "concepts", "concept_groups", "facets", "term_groups", "keywords")
    if isinstance(spec.get("research_question"), dict) and not raw:
        raw = spec["research_question"].get("concepts")
    concepts: list[dict[str, Any]] = []
    if isinstance(raw, dict):
        for key, value in raw.items():
            if isinstance(value, dict):
                value = dict(value, role=value.get("role", key), label=value.get("label", key))
            elif isinstance(value, list):
                value = {"label": key, "terms": value, "role": key}
            concepts.append(_concept_from_value(value, len(concepts), True))
    elif isinstance(raw, list):
        concepts = [_concept_from_value(value, i, True) for i, value in enumerate(raw)]
    elif isinstance(raw, str):
        concepts = [_concept_from_value(raw, 0, True)]
    if concepts:
        return [c for i, c in enumerate(concepts) if c["all_terms"] or c["terms"]]
    text = question if question is not None else research_question_text(spec)
    hay = text.casefold()
    for seed in SEED_GROUPS:
        if any(term.casefold() in hay for term in seed["terms"]):
            concepts.append(_concept_from_value(seed, len(concepts), False))
    if not concepts and text:
        terms = query_terms(text)
        if terms:
            concepts = [{"concept_id": "C01", "label": text, "role": "topic", "terms": terms,
                         "synonyms": [], "controlled_terms": [], "all_terms": terms, "required": True,
                         "provenance": "question_lexical_fallback_no_semantic_translation"}]
    return [c for i, c in enumerate(concepts) if c["all_terms"] or c["terms"]]


def temporal_scope(spec: dict[str, Any]) -> dict[str, Any]:
    scope = spec.get("research_scope") if isinstance(spec.get("research_scope"), dict) else {}
    protocol = spec.get("search_protocol") if isinstance(spec.get("search_protocol"), dict) else {}
    start = _first(spec, "start_date", "date_from", "from_date") or _first(scope, "start_date", "date_from") or protocol.get("start_date")
    end = _first(spec, "end_date", "date_to", "until_date") or _first(scope, "end_date", "date_to") or protocol.get("end_date")
    languages = _first(spec, "languages", "language") or scope.get("languages") or protocol.get("languages") or []
    for label, value in (("start_date", start), ("end_date", end)):
        if value is not None and not isinstance(value, (str, int)):
            raise RetrievalError("retrieval.invalid_temporal_boundary", f"{label} must be an ISO date/year scalar, not {type(value).__name__}", 4)
        if value is not None and not re.match(r"^\d{4}(?:-\d{2}-\d{2})?", _as_text(value)):
            raise RetrievalError("retrieval.invalid_temporal_boundary", f"{label} is not a YYYY or YYYY-MM-DD boundary: {value}", 4)
    if not isinstance(languages, (str, list)):
        raise RetrievalError("retrieval.invalid_language_boundary", "languages must be a string or list of language codes", 4)
    return {"start_date": _as_text(start) or None, "end_date": _as_text(end) or None,
            "languages": _as_list(languages), "search_date": _as_text(_first(spec, "search_date", "snapshot_date")) or None}


def temporal_match(work: dict[str, Any], scope: dict[str, Any]) -> tuple[bool, str | None]:
    year = work["metadata"].get("year")
    for key, operator in (("start_date", "start"), ("end_date", "end")):
        boundary = scope.get(key)
        if boundary:
            match = re.match(r"^(\d{4})", boundary)
            if match:
                if year is None:
                    return False, f"missing year cannot satisfy {operator}_date boundary {boundary}"
                if (operator == "start" and year < int(match.group(1))) or (operator == "end" and year > int(match.group(1))):
                    return False, f"year {year} outside declared {key}={boundary}"
    languages = [str(x).casefold() for x in scope.get("languages", [])]
    if languages:
        language = str(work["metadata"].get("language") or "").casefold()
        if not language:
            return False, "missing language cannot satisfy declared language boundary"
        if not any(language == item or language.startswith(item + "-") or item in {"zh", "cn"} and language.startswith("zh")
                   for item in languages):
            return False, f"language {language} outside declared {languages}"
    return True, None


def _quoted_group(terms: list[str]) -> str:
    if not terms:
        return ""
    return "(" + " OR ".join('"' + term.replace('"', "") + '"' for term in terms) + ")"


def source_query_plans(concepts: list[dict[str, Any]], scope: dict[str, Any], base: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    """Build real API parameter shapes, explicitly marked planned/not executed.

    OpenAlex follows pyalex's separators: comma joins distinct filters, | ORs
    values (and + is available for AND in filter values).  Crossref gets a
    bibliographic term string plus filters, never a pretend MeSH query.  Europe
    PMC gets TITLE_ABS boolean groups and a real date boundary.
    """
    groups = [_quoted_group(c["all_terms"] or c["terms"]) for c in concepts]
    boolean = " AND ".join(g for g in groups if g)
    all_terms = list(dict.fromkeys(t for c in concepts for t in (c["all_terms"] or c["terms"])))
    start, end = scope.get("start_date"), scope.get("end_date")
    languages = scope.get("languages") or []
    oa_filters = []
    if start:
        oa_filters.append(f"from_publication_date:{start}")
    if end:
        oa_filters.append(f"to_publication_date:{end}")
    if languages:
        oa_filters.append("language:" + "|".join(languages))
    oa_params = {"search": boolean or " ".join(all_terms), "filter": ",".join(oa_filters),
                 "select": "id,doi,title,display_name,publication_year,authorships,primary_location,abstract_inverted_index,type",
                 "per-page": 200, "cursor": "*"}
    cr_filter = []
    if start:
        cr_filter.append(f"from-pub-date:{start}")
    if end:
        cr_filter.append(f"until-pub-date:{end}")
    cr_params = {"query.bibliographic": " ".join(all_terms), "filter": ",".join(cr_filter),
                 "select": "DOI,title,author,issued,container-title,abstract,URL,type,publisher",
                 "rows": 100, "cursor": "*"}
    epmc_parts = []
    for group in groups:
        if group:
            epmc_parts.append("TITLE_ABS:" + group)
    epmc_query = " AND ".join(epmc_parts) or boolean
    if start or end:
        epmc_query += f" AND FIRST_PDATE:[{start or '*'} TO {end or '*'}]"
    if languages:
        epmc_query += " AND (" + " OR ".join(f"LANG:{lang}" for lang in languages) + ")"
    epmc_params = {"query": epmc_query, "format": "json", "pageSize": 100, "cursorMark": "*"}
    return [
        {"source": "OpenAlex", "execution_status": "planned_not_executed", "http_method": "GET",
         "request_url": "https://api.openalex.org/works?" + urlencode({k: v for k, v in oa_params.items() if v != ""}),
         "parameters": oa_params, "boolean_local": boolean, "fields": ["title", "abstract"],
         "time_boundary": {"from": start, "to": end}, "remote_hit_count": None,
         "note": "Reproducible request plan only. No remote request or remote result count was made."},
        {"source": "Crossref", "execution_status": "planned_not_executed", "http_method": "GET",
         "request_url": "https://api.crossref.org/works?" + urlencode({k: v for k, v in cr_params.items() if v != ""}),
         "parameters": cr_params, "boolean_local": boolean, "fields": ["bibliographic metadata"],
         "time_boundary": {"from": start, "to": end}, "remote_hit_count": None,
         "note": "Crossref uses query.bibliographic + filters; local Boolean gates are not represented as an unverified Crossref Boolean grammar."},
        {"source": "Europe PMC", "execution_status": "planned_not_executed", "http_method": "GET",
         "request_url": "https://www.ebi.ac.uk/europepmc/webservices/rest/search?" + urlencode(epmc_params),
         "parameters": epmc_params, "boolean_local": boolean, "fields": ["TITLE_ABS"],
         "time_boundary": {"from": start, "to": end}, "remote_hit_count": None,
         "note": "TITLE_ABS/FIRST_PDATE plan only; candidate MeSH terms are not inserted without verification."},
    ]


def query_for_concepts(index: BM25Index, concepts: list[dict[str, Any]], scope: dict[str, Any],
                       hard_all: bool = False, minimum_facets: int = 0) -> list[dict[str, Any]]:
    rows = []
    required = [c for c in concepts if c.get("required") is not False] or concepts
    for work_id in index.order:
        work = index.works[work_id]
        passes_date, reason = temporal_match(work, scope)
        facets = []
        for concept in concepts:
            terms = concept["all_terms"] or concept["terms"]
            matched = matched_terms(terms, work["fields"])
            facets.append({"concept_id": concept["concept_id"], "label": concept["label"], "role": concept["role"],
                           "matched_terms": matched, "matched": bool(matched)})
        coverage = sum(1 for f in facets if f["matched"])
        required_coverage = sum(1 for concept, facet in zip(concepts, facets)
                                if concept.get("required") is not False and facet["matched"])
        gates = (not hard_all or required_coverage == len(required)) and coverage >= minimum_facets
        if not passes_date or not gates:
            continue
        all_terms = [t for facet in facets for t in facet["matched_terms"]]
        if not all_terms:
            continue
        score = index.score(work_id, all_terms)
        rows.append({"work_id": work_id, "facet_matches": facets, "facet_coverage": coverage,
                     "required_facet_coverage": required_coverage, **score})
    rows.sort(key=lambda r: (-r["normalized_relevance"], -r["facet_coverage"],
                             normalize_title(index.works[r["work_id"]]["metadata"].get("title")),
                             index.works[r["work_id"]]["work_id"]))
    for i, row in enumerate(rows, 1):
        row["rank"] = i
    return rows


def supplied_query_objects(spec: dict[str, Any]) -> list[dict[str, Any]]:
    raw = _first(spec, "queries", "search_queries", "query_history", "search_history", "iterations")
    if raw is None and isinstance(spec.get("search_protocol"), dict):
        raw = _first(spec["search_protocol"], "queries", "iterations", "databases")
    if raw is None:
        return []
    values = raw if isinstance(raw, list) else [raw]
    out = []
    for i, item in enumerate(values):
        if isinstance(item, str):
            out.append({"query_id": f"Q{i + 1:02d}", "query": item})
        elif isinstance(item, dict):
            out.append(copy.deepcopy(item) | {"query_id": str(item.get("query_id") or item.get("id") or f"Q{i + 1:02d}")})
    return out


def finding(result: dict[str, Any], rule: str, severity: str, message: str, **extra: Any) -> None:
    result.setdefault("findings", []).append({"rule": rule, "severity": severity, "message": message, **extra})
    if severity in {"medium", "high"} and result.get("status") == "clean":
        result["status"] = "review" if severity == "medium" else "blocked"


def score_evidence(work: dict[str, Any], score: dict[str, Any], limit: int = 40) -> list[dict[str, Any]]:
    """Return field-level verbatim slices for every scored term/field component."""
    evidence = []
    for item in score.get("term_field_scores", []):
        text = work["fields"].get(item["field"], "")
        term = item["term"]
        spans = positive_spans(text, term)
        start = spans[0][0] if spans else -1
        matched = term
        if start < 0:
            for token in analyzer(term):
                token_spans = positive_spans(text, token)
                if token_spans:
                    start = token_spans[0][0]
                    matched = text[start:start + len(token)]
                    break
        if start < 0:
            # A score must never be justified with an invented quote.  Keep an
            # auditable missing locator for investigation instead.
            evidence.append({"record_id": work["record_id"], "work_id": work["work_id"],
                             "term": term, "field": item["field"],
                             "locator": {"source_path": f"fields.{item['field']}", "start": None, "end": None},
                             "quote": None, "status": "locator_unresolved_requires_review"})
            continue
        end = start + len(matched)
        quote = text[start:end]
        evidence.append({"record_id": work["record_id"], "work_id": work["work_id"], "term": term,
                         "field": item["field"], "locator": {"source_path": f"fields.{item['field']}",
                         "dataset_id": work["dataset_id"], "dataset_row": work["dataset_row"],
                         "start": start, "end": end}, "quote": quote, "status": "verbatim"})
        if len(evidence) >= limit:
            break
    return evidence


def public_candidate(work: dict[str, Any], score: dict[str, Any] | None = None) -> dict[str, Any]:
    return {"record_id": work["record_id"], "work_id": work["work_id"], "member_ids": work["member_ids"],
            "duplicate_of": work.get("duplicate_of"), "group_id": work["work_id"],
            "metadata": work["metadata"], "sources": work["sources"],
            "metadata_completeness": work["metadata_completeness"], "source_quality": work["source_quality"],
            "dedup_status": work["dedup_status"],
            "evidence": score_evidence(work, score) if score else [], "relevance": score}
