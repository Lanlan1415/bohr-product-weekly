"""Harbor CLI for evidence-anchored research-quality appraisal.

  python -I -X utf8 scripts/quality_cli.py --case /input/case.json --out /app/output
  python -I -X utf8 scripts/quality_cli.py --case examples/case.json --out ./_run_example

case.json may carry documents/studies/corpus/records inline or declare JSON,
JSONL, TXT or MD material paths.  The CLI never fetches remote content.  PDF text
must first be extracted with the platform PDF tool; a PDF binary is not silently
presented as appraised text.  Exit: 0 clean, 3 review/partial, 4 caller/blocked,
5 unreadable or undetermined.  Every expected failure writes result.json without
a traceback and preserves case_id plus every original output_contract field.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import appraisal as A  # noqa: E402

ALLOWED_SECTIONS = {None, "", "quality", "appraisal", "quality_appraisal", "research_quality",
                    "search-quality", "文献研究质量评价"}
TEXT_SUFFIXES = {".txt", ".md"}
JSON_SUFFIXES = {".json", ".jsonl"}
PATH_KEYS = {"documents_path", "corpus_path", "records_path", "materials_path", "path", "file_path"}


class MaterialError(Exception):
    def __init__(self, rule: str, message: str, exit_code: int = 5):
        super().__init__(message)
        self.rule, self.exit_code = rule, exit_code


def _write(out: Path, result: dict[str, Any]) -> None:
    out.mkdir(parents=True, exist_ok=True)
    (out / "result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def contract_fields(contract: Any) -> tuple[list[str], list[str]]:
    warnings: list[str] = []
    if contract is None:
        return [], warnings
    if isinstance(contract, str):
        return [contract], warnings
    if isinstance(contract, dict):
        return [str(k) for k in contract], warnings
    if isinstance(contract, list):
        names = []
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


def complete_contract(result: dict[str, Any], case: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(case, dict):
        return result
    if case.get("case_id") is not None:
        result["case_id"] = case["case_id"]
    elif "case_id" not in result:
        result["case_id"] = None
    result.setdefault("limits", [])
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
        if name in case and name not in A.BULKY:
            result[name] = copy.deepcopy(case[name])
        else:
            result[name] = None
            note = f"output_contract field '{name}' remains null: not derivable from supplied evidence"
            result["limits"].append(note)
            result.setdefault("findings", []).append({"rule": "quality.contract_field_missing", "severity": "medium",
                                                       "field": name})
            if result.get("status") == "clean":
                result["status"] = "review"
    return result


def refuse(out: Path, case: Any, rule: str, message: str) -> dict[str, Any]:
    result = {"schema_version": A.SCHEMA_VERSION, "status": "undetermined",
              "refusal": {"rule": rule, "message": str(message)[:1000]},
              "findings": [{"rule": rule, "severity": "high", "message": str(message)[:1000]}],
              "uncertainty": ["No appraisal judgement was completed."], "limits": []}
    if isinstance(case, dict):
        complete_contract(result, case)
    else:
        result["case_id"] = None
    _write(out, result)
    return result


def _as_text(value: Any) -> str:
    if isinstance(value, str):
        return value
    if value is None or isinstance(value, (dict, list)):
        return ""
    return str(value)


def _first(raw: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        value = raw.get(key)
        if value not in (None, "", []):
            return value
    return None


def _metadata(raw: dict[str, Any]) -> dict[str, Any]:
    md: dict[str, Any] = {}
    nested = raw.get("metadata") if isinstance(raw.get("metadata"), dict) else {}
    merged = dict(nested)
    merged.update(raw)
    aliases = {
        "title": ("title", "article-title"), "doi": ("doi", "DOI"), "pmid": ("pmid", "PMID"),
        "journal": ("journal", "container-title", "journalTitle"), "year": ("year", "pubYear"),
        "publisher": ("publisher",), "authors": ("authors", "author", "authorString"),
        "design": ("design", "study_design", "publication_type", "pubType"),
        "publication_status": ("publication_status", "subtype"),
        "source": ("source", "source_name", "database"), "source_type": ("source_type",),
        "version": ("version", "source_version"), "url": ("url", "URL"),
        "retracted": ("retracted", "isRetracted"), "subtype": ("subtype",),
        "license": ("license", "licence"), "access": ("access", "access_level"),
    }
    for target, keys in aliases.items():
        value = _first(merged, *keys)
        if isinstance(value, list) and target in {"title", "journal"}:
            value = value[0] if value else None
        if isinstance(value, (dict, list)):
            value = json.dumps(value, ensure_ascii=False, sort_keys=True)
        if value is not None:
            md[target] = str(value) if not isinstance(value, bool) else value
    return md


def _unit(text: Any, path: str, doc_id: str, index: int, *, section: str | None = None,
          page: int | None = None, paragraph: int | None = None, table: str | None = None) -> dict[str, Any] | None:
    value = _as_text(text)
    if not value.strip():
        return None
    locator = {"document_id": doc_id, "unit": index, "source_path": path}
    if section is not None:
        locator["section"] = str(section)
    if page is not None:
        locator["page"] = page
    if paragraph is not None:
        locator["paragraph"] = paragraph
    if table is not None:
        locator["table"] = table
    return {"text": value, "locator": locator}


def _add_field_units(raw: dict[str, Any], doc_id: str, units: list[dict[str, Any]], prefix: str = "") -> None:
    fields = ["title", "DOI", "doi", "pmid", "journal", "container-title", "publisher", "source", "source_type",
              "version", "source_version", "design", "study_design", "publication_type", "pubType",
              "publication_status", "subtype", "retracted", "isRetracted"]
    for key in fields:
        value = raw.get(key)
        values = value if isinstance(value, list) else [value]
        for j, item in enumerate(values):
            path = prefix + key + (f"[{j}]" if isinstance(value, list) else "")
            u = _unit(item, path, doc_id, len(units))
            if u:
                units.append(u)


def normalize_document(raw: Any, index: int, source_path: str = "inline") -> dict[str, Any]:
    if isinstance(raw, str):
        raw = {"text": raw}
    if not isinstance(raw, dict):
        raise MaterialError("quality.document_invalid", f"document {index} is {type(raw).__name__}, not object/string")
    original = raw
    if isinstance(raw.get("message"), dict) and any(k in raw["message"] for k in ("title", "abstract", "DOI")):
        raw = dict(raw["message"])
        raw.setdefault("source", original.get("source") or "Crossref supplied response")
    doc_id = str(_first(original, "id", "doc_id", "uid") or _first(raw, "DOI", "doi", "pmid", "id") or f"doc-{index + 1:03d}")
    md = _metadata(raw)
    units: list[dict[str, Any]] = []
    _add_field_units(raw, doc_id, units)

    full_keys = ("full_text", "fullText", "full_text_xml", "fullTextXML", "body", "content")
    full_text_available = False
    for key in full_keys:
        value = raw.get(key)
        if isinstance(value, str) and value.strip():
            units.append(_unit(value, key, doc_id, len(units)))
            full_text_available = True
        elif key == "content" and isinstance(value, (dict, list)):
            # Structured content is walked below only if it is a section/page list.
            pass
    # Generic text is explicitly an excerpt unless another full-text key exists.
    if isinstance(raw.get("text"), str) and raw["text"].strip():
        units.append(_unit(raw["text"], "text", doc_id, len(units)))
    abstract = _first(raw, "abstract", "abstractText", "summary")
    if abstract is not None:
        if isinstance(abstract, list):
            abstract = "\n".join(_as_text(x) for x in abstract if _as_text(x))
        units.append(_unit(abstract, "abstract", doc_id, len(units), section="Abstract"))

    sections = raw.get("sections")
    if isinstance(sections, dict):
        sections = [{"title": k, "text": v} for k, v in sections.items()]
    if isinstance(sections, list):
        for j, sec in enumerate(sections):
            if isinstance(sec, str):
                units.append(_unit(sec, f"sections[{j}]", doc_id, len(units), section=f"section[{j}]"))
            elif isinstance(sec, dict):
                title = str(_first(sec, "title", "heading", "name") or f"section[{j}]")
                text = _first(sec, "text", "content", "body", "paragraphs")
                if isinstance(text, list):
                    for k, part in enumerate(text):
                        value = _first(part, "text", "content") if isinstance(part, dict) else part
                        units.append(_unit(value, f"sections[{j}].paragraphs[{k}]", doc_id, len(units), section=title, paragraph=k))
                else:
                    units.append(_unit(text, f"sections[{j}].text", doc_id, len(units), section=title))
    pages = raw.get("pages")
    if isinstance(pages, list):
        for j, page in enumerate(pages):
            value = _first(page, "text", "content") if isinstance(page, dict) else page
            number = page.get("page", page.get("page_number", j + 1)) if isinstance(page, dict) else j + 1
            try:
                number = int(number)
            except (TypeError, ValueError):
                number = j + 1
            units.append(_unit(value, f"pages[{j}].text", doc_id, len(units), page=number))
    paragraphs = raw.get("paragraphs")
    if isinstance(paragraphs, list):
        for j, para in enumerate(paragraphs):
            value = _first(para, "text", "content") if isinstance(para, dict) else para
            section = para.get("section") if isinstance(para, dict) else None
            page = para.get("page") if isinstance(para, dict) else None
            units.append(_unit(value, f"paragraphs[{j}]", doc_id, len(units), section=section, page=page, paragraph=j))
    tables = raw.get("tables")
    if isinstance(tables, list):
        for j, table in enumerate(tables):
            if not isinstance(table, dict):
                continue
            table_id = str(table.get("id") or table.get("label") or f"table-{j + 1}")
            caption = table.get("caption")
            units.append(_unit(caption, f"tables[{j}].caption", doc_id, len(units), section="Table caption", table=table_id))
            cells = table.get("cells")
            if isinstance(cells, list):
                for k, cell in enumerate(cells):
                    if isinstance(cell, dict):
                        value = _first(cell, "text", "value", "content")
                        path = f"tables[{j}].cells[{k}].text"
                    else:
                        value, path = cell, f"tables[{j}].cells[{k}]"
                    units.append(_unit(value, path, doc_id, len(units), table=table_id))
            rows = table.get("rows")
            if isinstance(rows, list):
                for r, row in enumerate(rows):
                    values = row if isinstance(row, list) else list(row.values()) if isinstance(row, dict) else [row]
                    for c, cell in enumerate(values):
                        units.append(_unit(cell, f"tables[{j}].rows[{r}][{c}]", doc_id, len(units), table=table_id))
    units = [u for u in units if u]
    if not units:
        raise MaterialError("quality.document_no_text", f"document '{doc_id}' has no supplied text or usable metadata")
    scope = str(_first(raw, "source_scope", "coverage", "availability") or "").lower()
    abstract_only = bool(raw.get("abstract_only")) or "abstract" in scope or (abstract is not None and not full_text_available and not raw.get("text") and not sections and not pages and not paragraphs)
    if raw.get("full_text_available") is True:
        full_text_available = True
    if raw.get("full_text_available") is False and not full_text_available:
        abstract_only = abstract_only or abstract is not None
    source = {"material_path": source_path, "name": md.get("source"), "type": md.get("source_type"),
              "version": md.get("version"), "url": md.get("url"), "license": md.get("license")}
    return {"doc_id": doc_id, "metadata": md, "units": units, "source": source,
            "full_text_available": full_text_available, "abstract_only": abstract_only,
            "raw_relevance": original.get("relevance_score"), "screening_decision": original.get("decision")}


def _records_from_payload(payload: Any, path: str) -> list[Any]:
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        for key in ("documents", "studies", "corpus", "records", "results"):
            if isinstance(payload.get(key), list):
                return payload[key]
        if isinstance(payload.get("resultList"), dict) and isinstance(payload["resultList"].get("result"), list):
            return payload["resultList"]["result"]
        if any(k in payload for k in ("text", "full_text", "abstract", "abstractText", "message", "title", "sections", "pages")):
            return [payload]
    raise MaterialError("quality.material_shape", f"{path} does not contain a document list or a scientific document")


def _read_material(path: Path) -> list[Any]:
    if not path.is_file():
        raise MaterialError("quality.material_missing", f"declared material does not exist: {path}")
    try:
        if path.suffix.lower() == ".jsonl":
            rows = [json.loads(line) for line in path.read_text(encoding="utf-8-sig").splitlines() if line.strip()]
            return _records_from_payload(rows, str(path))
        if path.suffix.lower() == ".json":
            return _records_from_payload(json.loads(path.read_text(encoding="utf-8-sig")), str(path))
        if path.suffix.lower() in TEXT_SUFFIXES:
            return [{"id": path.stem, "text": path.read_text(encoding="utf-8-sig"), "source": str(path), "source_scope": "provided_excerpt"}]
    except (json.JSONDecodeError, UnicodeDecodeError, OSError) as exc:
        raise MaterialError("quality.material_unreadable", f"cannot read {path}: {exc}") from exc
    raise MaterialError("quality.material_unsupported", f"unsupported material type {path.suffix}; extract PDF/OCR text to JSON/TXT first")


def _inline_documents(spec: dict[str, Any]) -> list[Any] | None:
    for key in ("documents", "studies", "corpus", "records"):
        if key in spec:
            if not isinstance(spec[key], list):
                raise MaterialError("quality.documents_invalid", f"{key} must be a list")
            return spec[key]
    if any(k in spec for k in ("full_text", "abstract", "sections", "pages")) and "query" not in spec:
        return [spec]
    return None


def _collect_paths(value: Any, key: str = "") -> list[str]:
    paths: list[str] = []
    if isinstance(value, dict):
        for k, v in value.items():
            if k in PATH_KEYS and isinstance(v, str) and not re.match(r"^https?://", v):
                paths.append(v)
            elif k in {"materials", "files", "attachments"}:
                paths.extend(_collect_paths(v, k))
    elif isinstance(value, list) and key in {"materials", "files", "attachments"}:
        for item in value:
            if isinstance(item, str) and not re.match(r"^https?://", item):
                paths.append(item)
            else:
                paths.extend(_collect_paths(item, key))
    return list(dict.fromkeys(paths))


def _resolve(path_text: str, base: Path) -> Path:
    path = Path(path_text)
    if path.is_absolute():
        return path
    candidate = base / path
    if candidate.exists():
        return candidate
    input_candidate = Path("/input") / path
    return input_candidate if input_candidate.exists() else candidate


def load_normalized(spec: dict[str, Any], case_dir: Path) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    docs_raw = _inline_documents(spec)
    sources: list[Any] = []
    if docs_raw is None:
        path_texts = _collect_paths(spec)
        if not path_texts:
            raise MaterialError("quality.no_documents", "case supplies neither documents nor readable material paths")
        docs_raw = []
        for text in path_texts:
            path = _resolve(text, case_dir)
            loaded = _read_material(path)
            docs_raw.extend(loaded)
            sources.extend([str(path)] * len(loaded))
    else:
        sources = ["inline"] * len(docs_raw)
    normalized, omissions = [], []
    seen: dict[str, str] = {}
    for i, (raw, source) in enumerate(zip(docs_raw, sources)):
        if isinstance(raw, dict) and str(raw.get("access", "")).lower() in {"red", "restricted", "paywalled"}:
            omissions.append({"index": i, "id": raw.get("id"), "reason": "access restricted; full text not indexed"})
            continue
        try:
            doc = normalize_document(raw, i, str(source))
        except MaterialError as exc:
            if len(docs_raw) == 1:
                raise
            omissions.append({"index": i, "reason": str(exc), "rule": exc.rule})
            continue
        fingerprint = hashlib.sha256("\n".join(u["text"] for u in doc["units"]).encode("utf-8")).hexdigest()
        if doc["doc_id"] in seen:
            if seen[doc["doc_id"]] == fingerprint:
                omissions.append({"index": i, "id": doc["doc_id"], "reason": "exact duplicate record skipped"})
                continue
            base = doc["doc_id"]
            doc["doc_id"] = f"{base}#duplicate-{i + 1}"
            omissions.append({"index": i, "id": base, "reason": f"conflicting duplicate retained as {doc['doc_id']}"})
        seen[doc["doc_id"]] = fingerprint
        normalized.append(doc)
    if not normalized:
        if omissions and all("restricted" in str(o.get("reason")) for o in omissions):
            raise MaterialError("quality.access_blocked", "all supplied documents are access-restricted", 4)
        raise MaterialError("quality.no_documents", "no document with usable supplied evidence remains")
    return normalized, omissions, docs_raw


def _terms(text: str) -> list[str]:
    latin = {x.lower() for x in re.findall(r"[A-Za-z][A-Za-z0-9_-]{2,}", text or "")}
    latin -= {"the", "and", "for", "with", "from", "this", "that", "study", "research"}
    cjk = set()
    for run in re.findall(r"[\u4e00-\u9fff]{2,}", text or ""):
        cjk.update(run[i:i + 2] for i in range(len(run) - 1))
    return sorted(latin | cjk)


def _candidate_set(spec: dict[str, Any], docs: list[dict[str, Any]], appraisals: list[dict[str, Any]],
                   omissions: list[dict[str, Any]]) -> dict[str, Any]:
    question = str(spec.get("research_question") or spec.get("question") or spec.get("query") or "")
    terms = _terms(question)
    ranked = []
    for pos, (doc, app) in enumerate(zip(docs, appraisals)):
        haystack = (str(doc["metadata"].get("title", "")) + "\n" + "\n".join(
            u["text"] for u in doc["units"] if str(u["locator"].get("source_path", "")).startswith("abstract"))).lower()
        matched = [t for t in terms if t.lower() in haystack]
        lexical = len(matched) / len(terms) if terms else None
        supplied = doc.get("raw_relevance")
        try:
            supplied_score = float(supplied) if supplied is not None else None
        except (TypeError, ValueError):
            supplied_score = None
        rank_score = supplied_score if supplied_score is not None else (lexical if lexical is not None else 0.0)
        ranked.append({"doc_id": doc["doc_id"], "title": doc["metadata"].get("title"),
                       "doi": doc["metadata"].get("doi"), "pmid": doc["metadata"].get("pmid"),
                       "publication_status": doc["metadata"].get("publication_status"),
                       "relevance": {"basis": "case_supplied" if supplied_score is not None else "lexical_title_abstract" if terms else "not_computed_no_question",
                                     "score": supplied_score if supplied_score is not None else lexical,
                                     "matched_terms": matched, "note": "Relevance is separate from methodological quality."},
                       "quality_grade": app["overall"]["grade"], "coverage": app["coverage"],
                       "screening_decision": doc.get("screening_decision") or "appraised_not_automatically_included",
                       "source": doc["source"], "_position": pos, "_rank_score": rank_score})
    ranked.sort(key=lambda x: (-x["_rank_score"], x["_position"], x["doc_id"]))
    for i, item in enumerate(ranked, 1):
        item["rank"] = i
        item.pop("_position", None)
        item.pop("_rank_score", None)
    return {"候选文献": ranked, "排序/筛选结果": [{"doc_id": x["doc_id"], "rank": x["rank"],
                                               "decision": x["screening_decision"]} for x in ranked],
            "排序依据": "Case-supplied relevance score when present; otherwise deterministic title/abstract lexical overlap. Quality is reported separately and never traded for relevance.",
            "元数据": {d["doc_id"]: d["metadata"] for d in docs},
            "来源定位": {d["doc_id"]: d["source"] for d in docs},
            "遗漏说明": omissions + [{"reason": "Only supplied/authorized local materials were appraised; no live remote or global coverage claim."}]}


def build_result(case: dict[str, Any], case_dir: Path) -> dict[str, Any]:
    nested = case.get("spec") if isinstance(case.get("spec"), dict) else {}
    spec = dict(nested)
    for key, value in case.items():
        if key not in {"case_id", "output_contract", "spec"}:
            spec[key] = value
    docs, omissions, raw_docs = load_normalized(spec, case_dir)
    result = A.appraise({"normalized_documents": docs, "review_decisions": spec.get("review_decisions") or []})
    candidates = _candidate_set(spec, docs, result["appraisals"], omissions)
    evidence_ledger = [{"doc_id": a["doc_id"], "dimension": row["dimension"], **e}
                       for a in result["appraisals"] for row in a["quality_table"] for e in row["evidence"]]
    manual_changes = [c for a in result["appraisals"] for c in a.get("change_records", [])]
    changes = [{"operation": "normalize_supplied_source", "doc_id": d["doc_id"],
                "source": d["source"], "text_units": len(d["units"])} for d in docs] + manual_changes
    if omissions:
        result["findings"].append({"rule": "quality.records_omitted", "severity": "medium", "entries": omissions})
        result["status"] = "review"
    search_trace = {key: copy.deepcopy(spec[key]) for key in ("queries", "query", "search_history", "iterations",
                                                                "reference_graph", "import_state", "screening_protocol")
                    if key in spec}
    status_text = result["status"]
    result.update({
        "检索结果": candidates,
        "证据记录": {"质量评价表": result["appraisals"], "评价量表": result["rubric_definition"],
                   "查询与迭代": search_trace, "证据定位": evidence_ledger,
                   "复核记录": manual_changes,
                   "核验方法": "Each text quote must equal its source unit at start:end; structured-field quotes retain their exact source_path."},
        "状态说明": {"运行状态": status_text, "已完成": [a["doc_id"] for a in result["appraisals"]],
                   "未完成": [{"doc_id": a["doc_id"], "items": a["review_queue"]} for a in result["appraisals"] if a["review_queue"]],
                   "空结果": [], "冲突": [f for f in result["findings"] if "conflict" in f["rule"]],
                   "权限或接口异常": [o for o in omissions if "restricted" in str(o.get("reason"))],
                   "不确定性": result["uncertainty"]},
        "candidate_set": candidates["候选文献"], "evidence_ledger": evidence_ledger,
        "sources": [d["source"] | {"doc_id": d["doc_id"]} for d in docs],
        "search_trace": search_trace, "change_records": changes,
        "documents_appraised": len(docs), "omissions": omissions,
    })
    return complete_contract(result, case)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="research-quality", description=__doc__)
    parser.add_argument("--case", "--spec", dest="case", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args(argv)
    out = Path(args.out)
    case: Any = {}
    try:
        try:
            case = json.loads(Path(args.case).read_text(encoding="utf-8-sig"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            refuse(out, {}, "quality.case_unreadable", f"case file not readable: {exc}")
            return 5
        if not isinstance(case, dict):
            refuse(out, {}, "quality.case_not_object", "case.json must be a JSON object")
            return 4
        section = case.get("section")
        if section not in ALLOWED_SECTIONS:
            refuse(out, case, "quality.unknown_section", f"unknown section '{section}'")
            return 5
        # Save an honest early partial before material processing.
        early = {"schema_version": A.SCHEMA_VERSION, "status": "undetermined", "case_id": case.get("case_id"),
                 "limits": ["appraisal is still running; this partial is replaced only after completion"]}
        _write(out, early)
        result = build_result(case, Path(args.case).resolve().parent)
        _write(out, result)
        print(json.dumps({"status": result["status"], "case_id": result.get("case_id"),
                          "documents": result.get("documents_appraised"),
                          "grades": [a["overall"]["grade"] for a in result.get("appraisals", [])]}, ensure_ascii=False))
        return {"clean": 0, "review": 3, "blocked": 4, "undetermined": 5}.get(result["status"], 5)
    except MaterialError as exc:
        refuse(out, case, exc.rule, str(exc))
        return exc.exit_code
    except Exception as exc:  # Formal case boundary: never expose a traceback.
        refuse(out, case, "quality.internal_error", f"{type(exc).__name__}: {exc}")
        return 5


if __name__ == "__main__":
    raise SystemExit(main())
