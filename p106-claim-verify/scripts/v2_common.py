"""Private standard-library evidence/contract primitives for the v2 reading CLIs.

This module never parses PDFs, performs network requests, or infers scientific truth.
It verifies quotations only against explicitly supplied source snapshots.  Page and
paragraph identifiers are copied from that snapshot; missing values remain null.
"""
from __future__ import annotations

import copy
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, OSError):
        pass

SCHEMA_VERSION = "reading-v2-evidence/v1"
_BULKY = {"text", "full_text", "manuscript_text", "source_text", "documents",
          "materials", "claims", "references", "evidence", "output_contract"}


def read_json(path: str | Path) -> tuple[Any, str | None]:
    try:
        return json.loads(Path(path).read_text(encoding="utf-8-sig")), None
    except (OSError, UnicodeDecodeError, ValueError) as exc:
        return None, f"{path} is not readable JSON: {type(exc).__name__}: {exc}"


def dump_json(path: str | Path, value: Any) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                 encoding="utf-8", newline="\n")


def field_names(contract: Any) -> tuple[list[str], list[str]]:
    warnings: list[str] = []
    if contract is None:
        return [], warnings
    if isinstance(contract, dict):
        wrappers = {"required", "fields", "lists", "optional"}
        if set(contract).issubset(wrappers | {"notes"}) and set(contract) & wrappers:
            raw = []
            for key in ("required", "fields", "lists", "optional"):
                value = contract.get(key)
                raw.extend(list(value) if isinstance(value, dict) else value if isinstance(value, (list, tuple)) else [])
        elif isinstance(contract.get("properties"), dict):
            raw = list(contract["properties"])
        else:
            raw = list(contract)
    else:
        raw = list(contract) if isinstance(contract, (list, tuple)) else [contract]
    fields: list[str] = []
    for pos, entry in enumerate(raw):
        if isinstance(entry, str):
            name = entry.strip()
        elif isinstance(entry, dict):
            name = str(entry.get("field") or entry.get("name") or entry.get("key") or "").strip()
        else:
            name = ""
        if name:
            if name not in fields:
                fields.append(name)
        else:
            warnings.append(f"output_contract entry {pos} has no usable field/name/key")
    return fields, warnings


def complete_contract(result: dict, case: Any, aliases: dict[str, str] | None = None,
                      workorder: Any = None) -> dict:
    """Complete original fields at TOP LEVEL; never replace an evidenced value.

    Precedence is engine derived > explicit case-carried value > explicit workorder
    value > null + limits.  The original identity and contract spelling are retained.
    """
    case = case if isinstance(case, dict) else {}
    workorder = workorder if isinstance(workorder, dict) else {}
    result = copy.deepcopy(result)
    result["case_id"] = case.get("case_id")
    limits = result.setdefault("limits", [])
    if not isinstance(limits, list):
        limits = result["limits"] = [str(limits)]
    if result.get("case_id") in (None, ""):
        limits.append("case_id is missing in case.json; no identifier was inferred")
    fields, warnings = field_names(case.get("output_contract"))
    limits.extend(x for x in warnings if x not in limits)
    if "output_contract" in case:
        result["output_contract"] = copy.deepcopy(case["output_contract"])
    result["output_contract_fields"] = fields
    aliases = aliases or {}
    for field in fields:
        if result.get(field) is not None:
            continue
        alias = aliases.get(field)
        if alias and result.get(alias) is not None:
            result[field] = copy.deepcopy(result[alias])
        elif field in case and case.get(field) is not None and field not in _BULKY:
            result[field] = copy.deepcopy(case[field])
        elif field in workorder and workorder.get(field) is not None and field not in _BULKY:
            result[field] = copy.deepcopy(workorder[field])
        else:
            result[field] = None
            note = f"output_contract field '{field}' remains null: no evidenced value from this run"
            if note not in limits:
                limits.append(note)
    ordered = {"case_id": result.get("case_id")}
    ordered.update(result)
    return ordered


def make_finding(rule: str, severity: str, message: str, item: Any = None,
                 fix: str | None = None) -> dict:
    row = {"rule": rule, "severity": severity, "message": message,
           "verdict": "undetermined" if severity == "undetermined" else "evidence_gap",
           "basis": "deterministic source-snapshot validation"}
    if item is not None:
        row["item"] = item
    if fix:
        row["fix"] = fix
    return row


def finalise_findings(rows: list[dict]) -> list[dict]:
    unique: dict[str, dict] = {}
    for row in rows:
        marker = json.dumps(row, ensure_ascii=False, sort_keys=True, default=str)
        unique.setdefault(marker, copy.deepcopy(row))
    out = sorted(unique.values(), key=lambda x: (str(x.get("item") or ""),
                                                 str(x.get("rule") or ""),
                                                 str(x.get("message") or "")))
    for pos, row in enumerate(out, 1):
        row["id"] = f"F{pos:03d}"
    return out


def severity_counts(findings: list[dict]) -> dict:
    counts: dict[str, int] = {}
    for row in findings:
        sev = str(row.get("severity") or "")
        if sev != "undetermined":
            counts[sev] = counts.get(sev, 0) + 1
    return dict(sorted(counts.items()))


def run_state(findings: list[dict]) -> tuple[str, int]:
    if any(x.get("severity") == "high" for x in findings):
        return "partial", 4
    if findings:
        return "review", 3
    return "success", 0


def _text(record: dict) -> str:
    return next((str(record[k]) for k in ("text", "full_text", "source_text", "content")
                 if isinstance(record.get(k), str)), "")


def _records(value: Any) -> list[dict]:
    entries = list(value.values()) if isinstance(value, dict) else value
    return [x for x in entries if isinstance(x, dict)] if isinstance(entries, (list, tuple)) else []


class SourceCorpus:
    """An explicitly supplied, quotable source index.

    Accepted bundle: {"documents": [{"document_id", "text", "paragraphs":
    [{"paragraph_id", "text", "page", "section", "table_id", ...]}]}.
    Plain document text is split into deterministic snapshot paragraphs P0001...;
    these are labelled derived_snapshot rather than represented as original PDF ids.
    """

    def __init__(self, bundle: Any):
        raw = bundle.get("documents") if isinstance(bundle, dict) else bundle
        if raw is None and isinstance(bundle, dict):
            raw = bundle.get("sources")
        self.documents: dict[str, dict] = {}
        self.errors: list[str] = []
        for pos, doc in enumerate(_records(raw)):
            doc_id = str(doc.get("document_id") or doc.get("source_document_id") or
                         doc.get("id") or doc.get("name") or "").strip()
            if not doc_id:
                self.errors.append(f"documents[{pos}] has no document_id")
                continue
            if doc_id in self.documents:
                self.errors.append(f"duplicate document_id '{doc_id}'")
                continue
            text = _text(doc)
            paragraphs = []
            declared = isinstance(doc.get("paragraphs"), (list, tuple))
            if declared:
                for ppos, para in enumerate(_records(doc.get("paragraphs"))):
                    pid = str(para.get("paragraph_id") or para.get("id") or "").strip()
                    if not pid or not isinstance(para.get("text"), str):
                        self.errors.append(f"{doc_id}.paragraphs[{ppos}] needs paragraph_id and text")
                        continue
                    paragraphs.append(dict(para, paragraph_id=pid))
            elif text:
                chunks = [x for x in re.split(r"(?:\r?\n){2,}", text) if x.strip()]
                paragraphs = [{"paragraph_id": f"P{i:04d}", "text": x}
                              for i, x in enumerate(chunks or [text], 1)]
            par_index: dict[str, dict] = {}
            for para in paragraphs:
                pid = para["paragraph_id"]
                if pid in par_index:
                    self.errors.append(f"duplicate paragraph_id '{doc_id}/{pid}'")
                par_index[pid] = para
            if not text and par_index:
                # A paragraph-only snapshot is sufficient evidence.  Derive a stable
                # concatenated index solely for character offsets; no prose is added.
                text = "\n\n".join(str(p.get("text") or "") for p in par_index.values())
            self.documents[doc_id] = {
                "document_id": doc_id, "text": text, "paragraphs": par_index,
                "paragraph_id_origin": "declared_snapshot" if declared else "derived_snapshot",
                "metadata": {k: copy.deepcopy(v) for k, v in doc.items()
                             if k not in {"text", "full_text", "source_text", "content", "paragraphs"}},
                "digest": hashlib.sha256(text.encode("utf-8")).hexdigest(),
            }
        if not self.documents:
            self.errors.append("no readable documents with document_id in source bundle")

    def anchor(self, evidence: Any, owner: str, require_structured: bool = True) -> tuple[dict, list[dict]]:
        if not isinstance(evidence, dict):
            return {"verbatim": "", "found": False}, [make_finding(
                "evidence.not_object", "high", f"{owner}: evidence is not an object", owner)]
        doc_id = str(evidence.get("source_document_id") or evidence.get("document_id") or
                     evidence.get("source_id") or "").strip()
        pid = str(evidence.get("paragraph_id") or "").strip()
        quote = str(evidence.get("verbatim") or evidence.get("quote") or "")
        locator = {k: evidence.get(k) for k in
                   ("page", "section", "table_id", "row", "column", "figure_id", "bbox", "charspan")
                   if evidence.get(k) is not None}
        out = {"source_document_id": doc_id or None, "paragraph_id": pid or None,
               "verbatim": quote, "context": evidence.get("context"),
               "found": False, **locator}
        findings: list[dict] = []
        if not doc_id or doc_id not in self.documents:
            findings.append(make_finding("evidence.unknown_source", "high",
                                         f"{owner}: source_document_id '{doc_id}' is absent", owner))
            return out, findings
        doc = self.documents[doc_id]
        if not pid or pid not in doc["paragraphs"]:
            findings.append(make_finding("evidence.paragraph_unresolved", "high",
                                         f"{owner}: paragraph_id '{pid}' is absent in '{doc_id}'", owner))
            return out, findings
        para = doc["paragraphs"][pid]
        ptext = str(para.get("text") or "")
        pos = ptext.find(quote) if quote else -1
        if not quote or pos < 0:
            findings.append(make_finding("evidence.quote_not_in_source", "high",
                                         f"{owner}: quotation does not occur verbatim in {doc_id}/{pid}", owner))
            return out, findings
        context = evidence.get("context")
        if context is not None:
            if not isinstance(context, str) or context not in ptext or quote not in context:
                findings.append(make_finding("evidence.context_mismatch", "high",
                                             f"{owner}: context must occur in the same paragraph and contain the quotation", owner))
        else:
            out["context"] = ptext
        for key in ("page", "section", "table_id", "row", "column", "figure_id", "bbox", "charspan"):
            # Snapshot values are authoritative; evidence-side aliases are accepted only
            # when the paragraph does not declare them.
            if para.get(key) is not None:
                if key in locator and locator[key] != para.get(key):
                    findings.append(make_finding("evidence.locator_conflict", "high",
                                                 f"{owner}: {key} disagrees with source snapshot", owner))
                out[key] = copy.deepcopy(para.get(key))
        if require_structured and not any(out.get(k) is not None for k in
                                          ("page", "table_id", "figure_id", "section", "bbox", "charspan")):
            findings.append(make_finding("evidence.locator_vague", "high",
                                         f"{owner}: source snapshot gives no page/section/table/figure/bbox locator",
                                         owner))
        global_pos = str(doc.get("text") or "").find(ptext) if ptext else -1
        out.update({"found": True, "match": "verbatim", "paragraph_char_start": pos,
                    "paragraph_char_end": pos + len(quote),
                    "char_start": global_pos + pos if global_pos >= 0 else None,
                    "char_end": global_pos + pos + len(quote) if global_pos >= 0 else None,
                    "paragraph_id_origin": doc["paragraph_id_origin"]})
        return out, findings

    def quality(self) -> list[dict]:
        rows = []
        for doc_id in sorted(self.documents):
            doc = self.documents[doc_id]
            meta = doc["metadata"]
            rows.append({
                "source_document_id": doc_id,
                "full_text_available": bool(doc["text"] or doc["paragraphs"]),
                "sha256": doc["digest"],
                "publication_type": meta.get("publication_type", "not_reported"),
                "version": meta.get("version", "not_reported"),
                "retraction_status": meta.get("retraction_status", "not_checked"),
                "peer_review_status": meta.get("peer_review_status", "not_checked"),
                "quality_note": meta.get("quality_note",
                    "quality fields are supplied metadata; unreported fields are not inferred"),
            })
        return rows


def tokens(value: Any) -> set[str]:
    """Candidate-retrieval tokens only. CJK bigrams avoid cross-language zero scores."""
    text = str(value or "").lower()
    words = re.findall(r"[a-z][a-z0-9_-]+", text)
    cjk = "".join(re.findall(r"[\u3400-\u9fff]", text))
    grams = [cjk[i:i + 2] for i in range(max(0, len(cjk) - 1))]
    return set(words + grams + ([cjk] if len(cjk) == 1 else []))


def retrieval_overlap(claim: Any, quote: Any) -> float:
    a, b = tokens(claim), tokens(quote)
    return round(len(a & b) / len(a), 6) if a else 0.0


def write_refusal(case: Any, out_dir: str | Path, message: str,
                  extra: dict | None = None, workorder: Any = None) -> dict:
    findings = [make_finding("run.undetermined", "undetermined", message,
                             fix="Provide readable source snapshots and the declared v2 work order.")]
    result = {"schema_version": SCHEMA_VERSION, "status": "undetermined", "ok": False,
              "findings": findings, "audit_report": findings, "severity_counts": {},
              "sources": [], "source_quality": [], "uncertainty": [{"reason": message}],
              "checked": {}, "limits": [message],
              "change_records": [{"action": "structured_refusal", "values_fabricated": False}]}
    if isinstance(extra, dict):
        result.update(copy.deepcopy(extra))
    result = complete_contract(result, case, workorder=workorder)
    dump_json(Path(out_dir) / "result.json", result)
    return result
