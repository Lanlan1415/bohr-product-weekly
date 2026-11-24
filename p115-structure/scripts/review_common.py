"""Shared, standard-library utilities for source-bound academic review CLIs.

The three review packages carry byte-identical copies of this module.  It owns
case/material loading, stable source locators, and the Harbor result contract;
scientific verdicts remain in each package's own engine.
"""
from __future__ import annotations

import bisect
import copy
import hashlib
import json
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any, Iterable

SCHEMA_VERSION = "source-review/v1"
EXIT_CODES = {"clean": 0, "review": 3, "blocked": 4, "undetermined": 5}
TEXT_KEYS = ("manuscript_text", "paper_text", "full_text", "source_text", "draft", "text")
BULKY_KEYS = {
    "text", "draft", "manuscript_text", "paper_text", "full_text", "source_text",
    "materials", "documents", "references", "evidence", "paragraphs", "claims",
    "output_contract", "case", "input", "inputs", "metadata_registry", "doi_registry",
}
SECTION_NAMES = (
    "abstract", "introduction", "background", "methods", "method", "methodology",
    "materials and methods", "results", "discussion", "conclusion", "conclusions",
    "limitations", "acknowledgements", "acknowledgments", "references", "bibliography",
    "appendix", "supplementary", "摘要", "引言", "前言", "方法", "材料与方法", "结果",
    "讨论", "结论", "局限", "参考文献", "附录", "补充材料",
)
STOPWORDS = {
    "the", "a", "an", "and", "or", "of", "to", "in", "on", "for", "with", "by",
    "from", "that", "this", "these", "those", "is", "are", "was", "were", "be", "been",
    "being", "as", "at", "we", "our", "us", "it", "its", "their", "they", "them", "than",
    "then", "there", "here", "into", "between", "among", "using", "used", "use", "based",
    "study", "studies", "paper", "article", "results", "result", "show", "showed", "shows",
    "found", "find", "demonstrate", "demonstrated", "significantly", "significant", "however",
    "also", "can", "could", "may", "might", "not", "no", "et", "al", "fig", "figure", "table",
    "的", "了", "和", "与", "在", "对", "为", "是", "我们", "本文", "研究", "结果", "显示",
}


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def read_json(path: str | Path) -> tuple[Any, str | None]:
    try:
        return json.loads(Path(path).read_text(encoding="utf-8-sig")), None
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        return None, f"{path} is not readable JSON: {type(exc).__name__}: {exc}"


def read_text_file(path: str | Path) -> tuple[str, str | None]:
    """Read a material without importing anything from its directory.

    PDF extraction uses an installed pdftotext binary when available.  Lack of a
    backend is an explicit limitation, never an invented text layer.
    """
    p = Path(path)
    try:
        if p.suffix.lower() == ".pdf":
            exe = shutil.which("pdftotext")
            if not exe:
                return "", "PDF text backend unavailable; run the platform PDF/OCR tool and pass its text output"
            proc = subprocess.run([exe, "-layout", str(p), "-"], capture_output=True,
                                  timeout=120, check=False)
            if proc.returncode != 0:
                detail = proc.stderr.decode("utf-8", "replace").strip()
                return "", "PDF extraction failed: " + (detail or f"pdftotext exit {proc.returncode}")
            return proc.stdout.decode("utf-8", "replace"), None
        return p.read_text(encoding="utf-8-sig"), None
    except (OSError, UnicodeDecodeError, subprocess.SubprocessError) as exc:
        return "", f"material {p} could not be read: {type(exc).__name__}: {exc}"


def _path_value(value: Any, base: Path) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None
    p = Path(value)
    if not p.is_absolute():
        p = base / p
    return str(p)


def _record_text(record: dict, base: Path) -> tuple[str, str | None, str | None]:
    for key in TEXT_KEYS:
        value = record.get(key)
        if isinstance(value, str) and value.strip():
            return value, None, None
    for key in ("path", "file", "file_path", "source_path", "artifact"):
        path = _path_value(record.get(key), base)
        if path:
            text, error = read_text_file(path)
            return text, error, path
    return "", None, None


def material_records(case: dict, case_path: str | Path | None = None,
                     extra_materials: Iterable[str] | None = None) -> tuple[list[dict], list[str]]:
    """Return the primary manuscript first and all other readable sources after it.

    Only explicitly named text/material fields are consumed; prompts and domain labels
    are never treated as scientific evidence.
    """
    base = Path(case_path).resolve().parent if case_path else Path.cwd()
    records: list[dict] = []
    errors: list[str] = []
    seen: set[str] = set()

    def add(name: str, text: str, role: str, path: str | None = None) -> None:
        if not isinstance(text, str) or not text.strip():
            return
        digest = sha256_text(text)
        marker = path or digest
        if marker in seen:
            return
        seen.add(marker)
        records.append({"name": name, "role": role, "path": path, "text": text,
                        "sha256": digest, "chars": len(text)})

    for pos, value in enumerate(extra_materials or []):
        path = _path_value(value, Path.cwd())
        if not path:
            continue
        text, error = read_text_file(path)
        if error:
            errors.append(error)
        add(Path(path).name, text, "manuscript" if pos == 0 else "supplied_material", path)

    direct = next((case.get(k) for k in TEXT_KEYS
                   if isinstance(case.get(k), str) and case.get(k).strip()), None)
    if direct and not records:
        add("case manuscript", direct, "manuscript")

    nested = case.get("manuscript") or case.get("paper") or case.get("document")
    if isinstance(nested, dict):
        text, error, path = _record_text(nested, base)
        if error:
            errors.append(error)
        add(str(nested.get("name") or nested.get("id") or "manuscript"), text, "manuscript", path)
    elif isinstance(nested, str) and nested.strip() and not records:
        add("manuscript", nested, "manuscript")

    materials = case.get("materials") or case.get("documents") or case.get("artifacts") or []
    if isinstance(materials, dict):
        materials = list(materials.values())
    if isinstance(materials, list):
        for pos, item in enumerate(materials):
            if isinstance(item, str):
                item = {"path": item}
            if not isinstance(item, dict):
                errors.append(f"material entry {pos} has unsupported type {type(item).__name__}")
                continue
            text, error, path = _record_text(item, base)
            if error:
                errors.append(error)
            name = str(item.get("name") or item.get("id") or (Path(path).name if path else f"material-{pos+1}"))
            role = str(item.get("role") or item.get("kind") or item.get("type") or "supplied_material")
            add(name, text, role, path)

    if not records:
        for container_key in ("input", "inputs", "case"):
            nested_case = case.get(container_key)
            if isinstance(nested_case, dict):
                text = next((nested_case.get(k) for k in TEXT_KEYS
                             if isinstance(nested_case.get(k), str) and nested_case.get(k).strip()), None)
                if text:
                    add("nested case manuscript", text, "manuscript")
                    break

    if len(records) > 1 and not any(r["role"].lower() == "manuscript" for r in records):
        manuscript_words = re.compile(r"manuscript|paper|full[ _-]?text|稿件|论文|全文", re.I)
        primary = [r for r in records if manuscript_words.search(r["name"] + " " + r["role"])]
        if primary:
            first = primary[0]
            first["role"] = "manuscript"
            records.remove(first)
            records.insert(0, first)
    if records and not any(r["role"].lower() == "manuscript" for r in records):
        records[0]["role"] = "manuscript"
    elif records:
        primary = next(r for r in records if r["role"].lower() == "manuscript")
        records.remove(primary)
        records.insert(0, primary)
    return records, errors


def source_documents(case: dict, materials: list[dict]) -> list[dict]:
    """Collect cited-source full texts separately from bibliographic metadata."""
    out: list[dict] = []
    for material in materials[1:]:
        out.append(dict(material))
    containers = [case.get(k) for k in
                  ("source_documents", "cited_sources", "external_sources", "evidence_sources", "sources")]
    for container in containers:
        entries = container.values() if isinstance(container, dict) else container
        if not isinstance(entries, (list, tuple)):
            continue
        for pos, entry in enumerate(entries):
            if not isinstance(entry, dict):
                continue
            text = next((entry.get(k) for k in ("text", "full_text", "source_text", "content")
                         if isinstance(entry.get(k), str) and entry.get(k).strip()), None)
            if not text:
                continue
            item = dict(entry)
            item.update({"name": str(entry.get("name") or entry.get("key") or entry.get("id") or f"source-{pos+1}"),
                         "text": text, "sha256": sha256_text(text), "chars": len(text)})
            out.append(item)
    unique = []
    seen = set()
    for item in out:
        marker = (str(item.get("doi") or "").lower(), item.get("sha256"))
        if marker in seen:
            continue
        seen.add(marker)
        unique.append(item)
    return unique


def normalise_space(text: Any) -> str:
    return re.sub(r"\s+", " ", str(text or "")).strip()


def normalise_doi(value: Any) -> str:
    if not isinstance(value, str):
        return ""
    doi = value.strip()
    doi = re.sub(r"^(?:https?://(?:dx\.)?doi\.org/|doi:\s*)", "", doi, flags=re.I)
    return doi.strip().strip("<>[]{}.,;，。；").lower()


def tokenize(text: Any) -> list[str]:
    words = [w.lower() for w in re.findall(r"[A-Za-z][A-Za-z0-9_-]{1,}|[\u3400-\u9fff]+", str(text or ""))]
    tokens: list[str] = []
    for word in words:
        if word in STOPWORDS or len(word) <= 2 and word.isascii():
            continue
        if re.fullmatch(r"[\u3400-\u9fff]+", word):
            if len(word) <= 3:
                if word not in STOPWORDS:
                    tokens.append(word)
            else:
                tokens.extend(word[i:i+2] for i in range(len(word)-1))
        else:
            tokens.append(word)
    return tokens


def overlap(claim: Any, evidence: Any) -> float:
    a, b = set(tokenize(claim)), set(tokenize(evidence))
    if not a or not b:
        return 0.0
    return len(a & b) / len(a)


def f1(a_text: Any, b_text: Any) -> float:
    a, b = set(tokenize(a_text)), set(tokenize(b_text))
    if not a or not b:
        return 0.0
    common = len(a & b)
    if not common:
        return 0.0
    precision, recall = common / len(a), common / len(b)
    return 2 * precision * recall / (precision + recall)


class Document:
    """An immutable text snapshot with deterministic page/paragraph/sentence locators."""

    def __init__(self, text: str, name: str = "manuscript") -> None:
        self.name = name
        self.text = str(text or "").replace("\r\n", "\n").replace("\r", "\n")
        self.sha256 = sha256_text(self.text)
        self._line_starts = [0]
        self._line_pages = [1]
        page = 1
        for match in re.finditer(r"\n|\f", self.text):
            if match.group() == "\n":
                self._line_starts.append(match.end())
                self._line_pages.append(page)
            else:
                page += 1
                if match.end() < len(self.text) and self.text[match.end()] == "\n":
                    self._line_starts.append(match.end() + 1)
                    self._line_pages.append(page)
        self.page_count = page
        self.spans: list[dict] = []
        self._build_spans()

    def page_at(self, offset: int) -> int:
        return self.text[:max(0, offset)].count("\f") + 1

    def line_at(self, offset: int) -> int:
        return max(1, bisect.bisect_right(self._line_starts, offset))

    def _section_before(self, offset: int) -> str:
        section = "front matter"
        for line in self.text[:offset].splitlines():
            title = self.heading(line)
            if title:
                section = title
        return section

    @staticmethod
    def heading(line: str) -> str | None:
        value = normalise_space(line).strip("#:：")
        if not value or len(value) > 120:
            return None
        plain = re.sub(r"^\d+(?:\.\d+)*[.)、]?\s*", "", value).strip()
        for name in SECTION_NAMES:
            if plain.lower() == name.lower() or (name in {"方法", "结果", "讨论", "结论", "参考文献", "摘要"}
                                               and plain.startswith(name) and len(plain) <= len(name) + 8):
                return plain
        if re.match(r"^\d+(?:\.\d+)*\s+\S", value) and len(value.split()) <= 16:
            return plain
        return None

    def _build_spans(self) -> None:
        paragraph = 0
        sentence_no = 0
        section = "front matter"

        def add_chunk(raw: str, start: int, current_section: str, is_heading: bool = False) -> None:
            nonlocal sentence_no
            pieces = [raw] if is_heading else list(re.finditer(
                r".+?(?:[!?。！？](?=\s|$)|(?<![Ee][Tt] [Aa][Ll])(?<![A-Z])\.(?=\s|$)|$)", raw, re.S))
            for piece in pieces:
                value = piece if isinstance(piece, str) else piece.group(0)
                piece_start = 0 if isinstance(piece, str) else piece.start()
                if not value.strip():
                    continue
                lead = len(value) - len(value.lstrip())
                trail = len(value.rstrip())
                s = start + piece_start + lead
                e = start + piece_start + trail
                quote = self.text[s:e]
                if not quote:
                    continue
                sentence_no += 1
                self.spans.append({
                    "id": f"S{sentence_no:04d}", "text": quote, "start": s, "end": e,
                    "page": self.page_at(s), "line_start": self.line_at(s), "line_end": self.line_at(max(s, e-1)),
                    "paragraph": paragraph, "sentence": sentence_no,
                    "section": normalise_space(quote) if is_heading else current_section,
                    "kind": "heading" if is_heading else "sentence",
                })

        # Headings are separate spans and update the section for following text.
        # Blank lines create paragraphs, while PDF single-line wrapping stays intact.
        cursor = 0
        content_start: int | None = None
        content_lines: list[str] = []
        for line_match in re.finditer(r"[^\n\f]*(?:\n|\f|$)", self.text):
            line = line_match.group(0).rstrip("\n\f")
            if line_match.start() == line_match.end():
                break
            heading = self.heading(line)
            blank = not line.strip()
            if heading or blank:
                if content_lines and content_start is not None:
                    paragraph += 1
                    add_chunk("\n".join(content_lines), content_start, section)
                    content_lines, content_start = [], None
                if heading:
                    paragraph += 1
                    section = normalise_space(line).strip("#:：")
                    add_chunk(line, line_match.start(), section, True)
            else:
                if content_start is None:
                    content_start = line_match.start()
                content_lines.append(line)
            cursor = line_match.end()
        if content_lines and content_start is not None:
            paragraph += 1
            add_chunk("\n".join(content_lines), content_start, section)

    def locator(self, span: dict) -> str:
        return (f"p.{span['page']}; {span['section']}; para {span['paragraph']}; "
                f"sentence {span['sentence']}; lines {span['line_start']}-{span['line_end']}")

    def evidence(self, span: dict, source: str | None = None) -> dict:
        return {"source": source or self.name, "quote": span["text"], "locator": self.locator(span),
                "page": span["page"], "paragraph": span["paragraph"], "sentence_id": span["id"],
                "start": span["start"], "end": span["end"], "exact_match": True}

    def find_quote(self, quote: str) -> tuple[dict | None, str]:
        if not isinstance(quote, str) or not quote.strip():
            return None, "empty"
        pos = self.text.find(quote)
        if pos >= 0:
            span = min(self.spans, key=lambda s: abs(s["start"] - pos)) if self.spans else None
            if span:
                located = dict(span)
                located.update({"text": quote, "start": pos, "end": pos + len(quote),
                                "page": self.page_at(pos), "line_start": self.line_at(pos),
                                "line_end": self.line_at(pos + len(quote) - 1)})
                return located, "exact"
        target = normalise_space(quote).casefold()
        for span in self.spans:
            if normalise_space(span["text"]).casefold() == target:
                return span, "whitespace_normalized"
        return None, "not_found"

    def section_spans(self, pattern: str, include_headings: bool = False) -> list[dict]:
        rx = re.compile(pattern, re.I)
        return [s for s in self.spans if rx.search(str(s["section"]))
                and (include_headings or s["kind"] != "heading")]


def field_names(contract: Any) -> tuple[list[str], list[str]]:
    warnings: list[str] = []
    if contract is None:
        return [], warnings
    if isinstance(contract, dict):
        raw = list(contract)
    elif isinstance(contract, str):
        raw = [contract]
    elif isinstance(contract, (list, tuple)):
        raw = list(contract)
    else:
        return [], [f"output_contract has unsupported type {type(contract).__name__}"]
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


def complete_contract(result: dict, case: dict, aliases: dict[str, str] | None = None) -> dict:
    """Complete fields with engine value > explicit case value > null + limits.

    The original case identity and contract are authoritative; a spec can never
    rebrand them.  Contract completion also runs on structured refusals.
    """
    result = dict(result)
    result["case_id"] = case.get("case_id") if isinstance(case, dict) else None
    limits = result.setdefault("limits", [])
    if not isinstance(limits, list):
        limits = result["limits"] = [str(limits)]
    fields, warnings = field_names(case.get("output_contract") if isinstance(case, dict) else None)
    limits.extend(w for w in warnings if w not in limits)
    if isinstance(case, dict) and "output_contract" in case:
        result["output_contract"] = copy.deepcopy(case["output_contract"])
    result["output_contract_fields"] = fields
    aliases = aliases or {}
    for field in fields:
        if result.get(field) is not None:
            continue
        alias = aliases.get(field)
        if alias and result.get(alias) is not None:
            result[field] = copy.deepcopy(result[alias])
        elif field in case and case.get(field) is not None:
            # A declared contract field is authoritative even when it contains the
            # editable manuscript, evidence or paragraph records.  "Bulky" is not
            # a reason to silently replace a supplied value with null.
            result[field] = copy.deepcopy(case[field])
        else:
            result[field] = None
            note = f"output_contract field '{field}' remains null: no evidenced value from this run"
            if note not in limits:
                limits.append(note)
    ordered = {"case_id": result["case_id"]}
    ordered.update(result)
    return ordered


def severity_counts(findings: list[dict]) -> dict:
    counts: dict[str, int] = {}
    for finding in findings:
        severity = str(finding.get("severity") or "undetermined")
        if severity != "undetermined":
            counts[severity] = counts.get(severity, 0) + 1
    return dict(sorted(counts.items()))


def finalise_findings(findings: Iterable[dict]) -> list[dict]:
    unique: list[dict] = []
    seen = set()
    for finding in findings:
        item = dict(finding)
        marker = json.dumps({k: item.get(k) for k in
                             ("rule", "location", "excerpt", "claim_id", "reference_key", "facet")},
                            ensure_ascii=False, sort_keys=True, default=str)
        if marker in seen:
            continue
        seen.add(marker)
        unique.append(item)
    unique.sort(key=lambda f: (str(f.get("location") or "zzz"), str(f.get("rule") or ""),
                               str(f.get("claim_id") or ""), str(f.get("excerpt") or "")))
    for pos, finding in enumerate(unique, 1):
        finding.setdefault("id", f"F{pos:03d}")
        finding.setdefault("severity", "medium")
        finding.setdefault("verdict", "evidence_gap")
        finding.setdefault("basis", "source-bound deterministic review rule")
        finding.setdefault("fix", "Inspect the quoted source and revise or supply the missing evidence.")
        finding.setdefault("location", None)
        finding.setdefault("excerpt", None)
    return unique


def result_state(findings: list[dict], passed: list[Any], pending: list[Any], not_checked: list[Any]) -> dict:
    return {"passed": passed,
            "problems": [f.get("id") for f in findings if f.get("severity") in {"high", "medium", "low"}],
            "pending_review": pending, "not_checked": not_checked}


def write_artifacts(out_dir: str | Path, result: dict) -> None:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(result, ensure_ascii=False, indent=2, sort_keys=False)
    (out / "result.json").write_text(payload + "\n", encoding="utf-8")
    lines = ["# Source-bound academic review", "", f"Case: {result.get('case_id')}",
             f"Status: {result.get('status')}", ""]
    for finding in result.get("audit_report") or result.get("findings") or []:
        lines.extend([f"## {finding.get('id', '')} {finding.get('rule', finding.get('category', ''))}",
                      f"- Severity: {finding.get('severity')}",
                      f"- Location: {finding.get('location')}",
                      f"- Excerpt: {finding.get('excerpt')}",
                      f"- Verdict: {finding.get('verdict')}",
                      f"- Basis: {finding.get('basis')}",
                      f"- Action: {finding.get('fix')}", ""])
    if result.get("limits"):
        lines.extend(["## Limits", ""] + [f"- {x}" for x in result["limits"]])
    (out / "audit_report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    log = {"case_id": result.get("case_id"), "status": result.get("status"),
           "checked": result.get("checked"), "change_records": result.get("change_records") or [],
           "deterministic": True, "network_metadata_refresh": bool(result.get("network_metadata_refresh", False))}
    (out / "run_log.json").write_text(json.dumps(log, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def refused(case: dict, out_dir: str | Path, rule: str, message: str,
            aliases: dict[str, str] | None = None) -> dict:
    finding = {"id": "RUN01", "rule": rule, "category": "run_state", "severity": "high",
               "verdict": "undetermined", "location": None, "excerpt": None,
               "basis": message, "fix": "Provide readable source material and rerun; no scientific verdict was inferred."}
    result = {"schema_version": SCHEMA_VERSION, "status": "undetermined", "ok": False,
              "findings": [finding], "audit_report": [], "severity_counts": {},
              "evidence_bounds": {"excerpts": [], "citation_evidence": [], "pending_review": [message]},
              "uncertainty": [{"reason": message, "needed": "readable source material"}],
              "result_state": {"passed": [], "problems": [], "pending_review": [message],
                               "not_checked": ["all scientific review facets"]},
              "sources": [], "checked": {}, "limits": [message],
              "change_records": [{"stage": "refusal", "action": "write_structured_undetermined_result",
                                  "values_fabricated": False}]}
    result = complete_contract(result, case if isinstance(case, dict) else {}, aliases)
    write_artifacts(out_dir, result)
    return result


def summary_for_stdout(result: dict) -> str:
    return json.dumps({"case_id": result.get("case_id"), "status": result.get("status"),
                       "findings": len(result.get("findings") or []),
                       "audit_report": len(result.get("audit_report") or []),
                       "undetermined": len(result.get("uncertainty") or [])}, ensure_ascii=False)
