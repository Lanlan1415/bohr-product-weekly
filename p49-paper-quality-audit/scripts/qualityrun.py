"""Evidence-bound, eleven-dimension manuscript quality review.

The caller reads the actual paper and records concise dimension assessments and
verbatim source evidence.  This program validates that evidence, adds only
mechanically decidable checks, preserves the legacy audit, and writes a stable
result.json.  It never invents an importance/novelty judgement for the caller.

python qualityrun.py --case /input/case.json --out /app/output
python qualityrun.py --spec examples/spec-quality.json --out out_quality

Optional --manuscript supplies a TXT/MD/TEX/PDF manuscript not inline in case.json.
Exit: 0 clean, 3 review/minor or incomplete review, 4 major manuscript issue,
5 undetermined/refused input.  Every path returns structured JSON, no traceback.
"""
from __future__ import annotations

import argparse
import copy
import json
import re
import subprocess
import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import sections as LEGACY  # noqa: E402

SCHEMA = "paper-quality-review/v2"
DIMENSIONS = (
    "problem_importance", "innovation", "design", "data", "analysis",
    "results", "argumentation", "writing", "citations", "reproducibility",
    "ethics_compliance",
)
DIMENSION_ZH = {
    "problem_importance": "问题重要性", "innovation": "创新性", "design": "研究设计",
    "data": "数据质量", "analysis": "分析方法", "results": "结果报告",
    "argumentation": "论证链", "writing": "写作与结构", "citations": "引用支持",
    "reproducibility": "可复现性", "ethics_compliance": "伦理与合规",
}
CATEGORY = {
    "problem_importance": "论证链", "innovation": "论证链", "design": "方法设计",
    "data": "事实核验", "analysis": "统计报告", "results": "统计报告",
    "argumentation": "论证链", "writing": "学术规范", "citations": "引用支持",
    "reproducibility": "学术规范", "ethics_compliance": "学术规范",
}
SEVERITY = {"low": 1, "medium": 2, "high": 3}
TEXT_KEYS = ("manuscript_text", "full_text", "paper_text", "draft")
PATH_KEYS = ("manuscript_path", "paper_path", "pdf_path", "manuscript", "paper")
BULKY = set(TEXT_KEYS) | {
    "output_contract", "paragraphs", "materials", "references", "chapters",
    "figures", "abstract", "diagnosis", "documents", "files", "inputs",
    "quality_assessments", "dimension_reviews", "text", "content",
}
HEADINGS = {
    "abstract": ("abstract", "摘要"),
    "introduction": ("introduction", "background", "引言", "前言", "背景"),
    "methods": ("methods", "methodology", "materials and methods", "方法", "材料与方法"),
    "results": ("results", "结果"),
    "discussion": ("discussion", "讨论"),
    "conclusion": ("conclusion", "conclusions", "结论"),
    "references": ("references", "bibliography", "参考文献"),
}
CAUSAL = re.compile(
    r"\b(causes?|caused|drives?|leads?\s+to|results?\s+in|proves?)\b|导致|证明|引起", re.I)


def _norm(value) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _clip(value, limit=500) -> str:
    text = _norm(value)
    return text if len(text) <= limit else text[:limit].rstrip() + "…"


def _sentences(text: str) -> list[dict]:
    rows = []
    section = "unsectioned"
    paragraph = 0
    for line in str(text).splitlines():
        raw = line.strip()
        if not raw:
            continue
        paragraph += 1
        heading = _heading(raw)
        if heading:
            section = heading[0]
            rows.append({"section": section, "paragraph": paragraph, "sentence": 1,
                         "text": raw, "heading": True})
            continue
        parts = re.split(r"(?<=[.!?。！？])\s+(?=[A-Z0-9(\[\"'始本文我们他她它这该])", raw)
        for j, part in enumerate(p for p in parts if p.strip()):
            rows.append({"section": section, "paragraph": paragraph, "sentence": j + 1,
                         "text": part.strip(), "heading": False})
    return rows


def _heading(line: str):
    bare = re.sub(r"^\s*(?:\d+(?:\.\d+)*|[IVX]+)[.、\s]+", "", line.strip(), flags=re.I)
    bare = bare.strip("#:： \t").lower()
    if len(bare) > 90:
        return None
    for canonical, aliases in HEADINGS.items():
        # Exact heading only: "Results continuation" is body text, not a Results heading.
        if any(bare == a.lower() for a in aliases):
            return canonical, line.strip()
    return None


def _location(row: dict | None) -> dict:
    if not row:
        return {"section": None, "paragraph": None, "sentence": None}
    return {k: row.get(k) for k in ("section", "paragraph", "sentence")}


def _evidence(row: dict | None, basis="direct manuscript wording") -> dict:
    return {"quote": _clip(row.get("text")) if row else None,
            "location": _location(row), "basis": basis}


def _find(rows: list[dict], pattern: str):
    rx = re.compile(pattern, re.I)
    return next((r for r in rows if not r.get("heading") and rx.search(r["text"])), None)


def _contains(text: str, quote: str) -> bool:
    return bool(_norm(quote)) and _norm(quote).rstrip("…") in _norm(text)


def _find_quote(rows: list[dict], text: str, quote: str):
    nq = _norm(quote).rstrip("…")
    for row in rows:
        if nq and nq in _norm(row["text"]):
            return row
    # A longer quotation may span extraction sentences; its substring still
    # locates the passage, but use the nearest matching opening words as locator.
    head = nq[:80]
    return next((r for r in rows if head and head[:35] in _norm(r["text"])), None)


def _records(value):
    return value if isinstance(value, list) else []


def _as_float(value):
    if isinstance(value, bool) or value is None:
        return None
    try:
        answer = float(str(value).replace(",", "").strip())
        return answer if answer == answer and abs(answer) != float("inf") else None
    except (ValueError, TypeError, OverflowError):
        return None


def _truthy_text(value) -> bool:
    return bool(_norm(value)) and _norm(value).lower() not in {
        "none", "null", "n/a", "na", "missing", "not reported", "未报告", "缺失"}


def _read_pdf(path: Path) -> tuple[str, str | None]:
    errors = []
    try:
        import fitz  # optional and imported lazily
        with fitz.open(str(path)) as doc:
            text = "\n".join(page.get_text("text") for page in doc)
        if text.strip():
            return text, None
        errors.append("PyMuPDF returned an empty text layer")
    except Exception as exc:
        errors.append(f"PyMuPDF: {exc}")
    try:
        from pypdf import PdfReader  # optional and imported lazily
        text = "\n".join(page.extract_text() or "" for page in PdfReader(str(path)).pages)
        if text.strip():
            return text, None
        errors.append("pypdf returned an empty text layer")
    except Exception as exc:
        errors.append(f"pypdf: {exc}")
    try:
        proc = subprocess.run(["pdftotext", "-layout", str(path), "-"],
                              capture_output=True, timeout=60)
        text = proc.stdout.decode("utf-8", "replace") if proc.returncode == 0 else ""
        if text.strip():
            return text, None
        errors.append("pdftotext returned no text")
    except (OSError, subprocess.SubprocessError) as exc:
        errors.append(f"pdftotext: {exc}")
    return "", "; ".join(errors)


def _read_manuscript(path: Path) -> tuple[str, str | None]:
    try:
        if path.stat().st_size > 30_000_000:
            return "", "manuscript exceeds the 30MB parser safety limit"
    except OSError as exc:
        return "", str(exc)
    if path.suffix.lower() == ".pdf":
        return _read_pdf(path)
    try:
        raw = path.read_bytes()
    except OSError as exc:
        return "", str(exc)
    for encoding in ("utf-8-sig", "utf-16", "gb18030"):
        try:
            return raw.decode(encoding), None
        except UnicodeDecodeError:
            continue
    return raw.decode("latin-1"), "text was not UTF-8; decoded as latin-1 with limits"


def _walk_for_text(value):
    if isinstance(value, dict):
        for key in TEXT_KEYS:
            if isinstance(value.get(key), str) and value[key].strip():
                return value[key]
        for key in ("documents", "papers", "sources", "inputs", "materials"):
            answer = _walk_for_text(value.get(key))
            if answer:
                return answer
    elif isinstance(value, list):
        for item in value:
            answer = _walk_for_text(item)
            if answer:
                return answer
    return ""


def _walk_for_path(value):
    if isinstance(value, dict):
        for key in PATH_KEYS:
            candidate = value.get(key)
            if isinstance(candidate, str) and candidate.strip():
                return candidate
        for key in ("documents", "papers", "files", "inputs", "materials", "artifacts"):
            answer = _walk_for_path(value.get(key))
            if answer:
                return answer
        # Generic document records often carry only path/file_path.
        if any(k in value for k in ("path", "file_path", "file")):
            candidate = value.get("path") or value.get("file_path") or value.get("file")
            if isinstance(candidate, str) and Path(candidate).suffix.lower() in {
                    ".pdf", ".txt", ".md", ".tex", ".json"}:
                return candidate
        for child in value.values():
            if isinstance(child, (dict, list)):
                answer = _walk_for_path(child)
                if answer:
                    return answer
    elif isinstance(value, list):
        for item in value:
            answer = _walk_for_path(item)
            if answer:
                return answer
    return ""


def _load_manuscript(spec: dict, base: Path, override=None) -> tuple[str, list[str], list[str]]:
    limits, sources = [], []
    if override:
        path = Path(override)
        text, err = _read_manuscript(path)
        if err:
            limits.append(f"manuscript parser limit: {err}")
        if text.strip():
            sources.append(str(path))
            return text, limits, sources
        if not path.exists():
            limits.append(f"manuscript file is missing: {path}")
        # A JSON source may itself contain the inline manuscript.
        if path.suffix.lower() == ".json" and path.exists():
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
                text = _walk_for_text(payload)
                if text:
                    sources.append(str(path))
                    return text, limits, sources
            except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
                limits.append(f"JSON manuscript fallback failed: {exc}")
        return "", limits, sources
    inline = _walk_for_text(spec)
    if inline.strip():
        sources.append("case.inline_manuscript")
        return inline, limits, sources
    candidate = _walk_for_path(spec)
    if candidate:
        path = Path(candidate)
        if not path.is_absolute():
            choices = [base / path, Path("/input") / path, Path("/app/work") / path]
            path = next((p for p in choices if p.exists()), choices[0])
        return _load_manuscript(spec, base, path)
    return "", ["no manuscript text or readable manuscript path was supplied"], sources


def _finding(findings, rule, dimension, severity, message, evidence=None,
             defect_class="review_observation", suggestion="Return to the cited passage and verify.",
             scope="manuscript", **location):
    findings.append({
        "rule": rule, "dimension": dimension, "dimension_zh": DIMENSION_ZH.get(dimension, dimension),
        "category": CATEGORY.get(dimension, "学术规范"), "severity": severity,
        "finding": message, "message": message, "basis": (evidence or {}).get("basis", "structured audit input"),
        "evidence": evidence or {"quote": None, "location": _location(None), "basis": "not available"},
        "location": dict((evidence or {}).get("location") or _location(None), **location),
        "suggestion": suggestion, "defect_class": defect_class, "scope": scope,
    })


def _legacy_dimension(rule):
    if rule.startswith("struct."):
        return "argumentation"
    if rule.startswith("long."):
        if "citation" in rule or "reference" in rule:
            return "citations"
        if "changelog" in rule or "change_" in rule:
            return "reproducibility"
        return "writing"
    if rule.startswith("pd."):
        if any(x in rule for x in ("citation", "source", "reference")):
            return "citations"
        if any(x in rule for x in ("figure", "abstract", "value")):
            return "results"
        if "declaration" in rule:
            return "ethics_compliance"
        if "change_log" in rule:
            return "reproducibility"
        if "causation" in rule:
            return "argumentation"
        if any(x in rule for x in ("section", "term")):
            return "writing"
        return "data"
    return "analysis"


def _run_legacy(spec, findings, limits):
    requested = spec.get("legacy_sections", [])
    if isinstance(requested, str):
        requested = [requested]
    if not isinstance(requested, list):
        return []
    origin = []
    for section in requested:
        if section not in {"paper_draft", "structure_logic", "longdoc"}:
            limits.append(f"unsupported legacy section was not run: {section}")
            continue
        try:
            found, _, _ = LEGACY.run(copy.deepcopy(spec), section)
        except Exception as exc:
            _finding(findings, "pqa.legacy_audit_failed", "analysis", "medium",
                     f"Legacy {section} audit could not be completed: {exc}",
                     defect_class="review_gap", scope="review_process")
            continue
        origin.append(section)
        for old in found:
            dim = _legacy_dimension(str(old.get("rule", "")))
            quote = old.get("evidence") if isinstance(old.get("evidence"), str) else old.get("text")
            ev = {"quote": _clip(quote) if quote else None,
                  "location": {k: old.get(k) for k in ("section", "paragraph", "sentence")},
                  "basis": f"legacy {section} deterministic rule"}
            new = dict(old)
            new.update({"dimension": dim, "dimension_zh": DIMENSION_ZH[dim],
                        "category": CATEGORY[dim], "origin": section,
                        "finding": old.get("message", old.get("rule")),
                        "basis": ev["basis"], "evidence": ev,
                        "defect_class": old.get("defect_class", "method_or_reporting_issue"),
                        "scope": "manuscript"})
            new.setdefault("location", ev["location"])
            new.setdefault("suggestion", "Resolve the evidenced legacy finding and rerun the same rule.")
            findings.append(new)
    return origin


def _structured_checks(spec, text, rows, findings, calculations, positive):
    # Problem importance and innovation require actual argument evidence, not a score template.
    question = _find(rows, r"\b(research question|we (?:ask|investigate|examine)|this study (?:aims|addresses)|hypothes)\b|研究问题|本文旨在|本研究旨在|假设")
    importance = _find(rows, r"\b(important|significance|critical|urgent|needed|gap|challenge)\b|重要性|迫切|研究空白|关键问题|现实意义")
    if question:
        positive["problem_importance"].append(_evidence(question, "explicit research problem"))
    if importance:
        positive["problem_importance"].append(_evidence(importance, "explicit significance/rationale wording"))
    novelty = _find(rows, r"\b(novel|first|new method|we propose|our contribution|innovation)\b|首次|创新|我们提出|本文贡献")
    if novelty:
        positive["innovation"].append(_evidence(novelty, "declared novelty/contribution claim"))
        prior = _find(rows, r"\b(compar\w*.{0,45}\b(?:with|to)\b|unlike|prior work|previous (?:work|studies)|baseline)\b|与.{0,20}(?:相比|不同)|已有研究|前人|基线")
        if not prior and not _truthy_text(spec.get("prior_work_comparison")):
            _finding(findings, "pqa.novelty_without_contrast", "innovation", "medium",
                     "A novelty/contribution claim is present, but no explicit comparison with prior work or a baseline was located.",
                     _evidence(novelty, "claim present; contrast search found no supporting passage"),
                     "reporting_gap", "Add a bounded comparison to the closest prior approach; do not infer superiority from the claim alone.")

    design = _norm(spec.get("design"))
    question_type = _norm(spec.get("research_question_type") or spec.get("question_type")).lower()
    compatible = {
        "causal_effect": {"rct", "randomized", "randomised", "experiment", "quasi_experiment", "natural_experiment"},
        "diagnostic_accuracy": {"diagnostic", "cross_sectional", "cohort", "case_control"},
        "prediction": {"cohort", "experimental", "observational", "cross_sectional", "rct", "secondary_analysis"},
        "descriptive": {"cross_sectional", "cohort", "case_series", "qualitative", "survey", "observational"},
    }
    dkey = design.lower().replace("-", "_").replace(" ", "_")
    if question_type in compatible and dkey and not any(k in dkey for k in compatible[question_type]):
        evidence = _evidence(question, "declared question type and design are incompatible")
        evidence["declared"] = {"research_question_type": question_type, "design": design}
        _finding(findings, "pqa.design_question_mismatch", "design", "high",
                 f"The declared {question_type} question is not answered by the declared {design} design.",
                 evidence, "method_defect", "Justify a valid design-question link or narrow the claim; do not repair this by adding a label.")
    if dkey in {"experimental", "randomized_controlled_trial", "randomised_controlled_trial", "rct"}:
        controls = spec.get("controls")
        if isinstance(controls, list):
            controls_present = bool(controls)
        else:
            controls_present = _truthy_text(controls)
        if not controls_present:
            _finding(findings, "pqa.comparative_design_no_control", "design", "high",
                     "The declared comparative experimental design has no control/comparator declaration.",
                     _evidence(_find(rows, r"randomi[sz]|experiment|试验|实验"), "declared design lacks a comparator"),
                     "method_defect", "Provide the comparator that was actually used, or accurately restate a non-comparative design.")
    conclusion = next((r for r in reversed(rows) if r.get("section") == "conclusion" and not r.get("heading")), None)
    if conclusion is None:
        conclusion = _find(rows, r"\b(in conclusion|we conclude|conclude[sd]? that|therefore)\b|总之|综上|结论")
    if ("observ" in dkey or "correl" in dkey or "cross_section" in dkey) and conclusion and CAUSAL.search(conclusion["text"]):
        _finding(findings, "pqa.causal_conclusion_exceeds_design", "argumentation", "high",
                 "A causal conclusion is asserted from a declared non-experimental design.",
                 _evidence(conclusion, "causal wording exceeds the declared design"),
                 "method_defect", "Rewrite as association or identify a defensible causal identification strategy and sensitivity analyses.")

    recruited = _as_float(spec.get("recruited_n"))
    analysed = _as_float(spec.get("analysed_n"))
    if recruited is not None and analysed is not None:
        delta = analysed - recruited
        calculations.append({"check": "sample_accounting", "inputs": {"recruited_n": recruited, "analysed_n": analysed},
                             "computed": {"analysed_minus_recruited": delta}, "valid": delta <= 0})
        if delta > 0:
            _finding(findings, "pqa.sample_accounting_impossible", "data", "high",
                     f"Analysed n ({analysed:g}) exceeds recruited n ({recruited:g}) by {delta:g}.",
                     _evidence(_find(rows, r"recruit|enrol|analy[sz]ed|纳入|纳入分析|入组"), "recomputed participant accounting"),
                     "numeric_inconsistency", "Reconcile participant flow and define the independent analysis unit; identify any records counted twice.")

    for record in _records(spec.get("reported_values")):
        if not isinstance(record, dict):
            continue
        left, right = _as_float(record.get("value")), _as_float(record.get("comparator_value"))
        if left is None or right is None:
            calculations.append({"check": "reported_value_comparison", "name": record.get("name"),
                                 "status": "not_computable", "reason": "Both numeric values are required."})
            continue
        tolerance = _as_float(record.get("tolerance"))
        tolerance = 1e-9 if tolerance is None else max(0.0, tolerance)
        delta = left - right
        ok = abs(delta) <= tolerance
        calc = {"check": "reported_value_comparison", "name": record.get("name"),
                "inputs": {"value": left, "comparator_value": right, "tolerance": tolerance},
                "computed": {"difference": delta, "absolute_difference": abs(delta)}, "consistent": ok}
        calculations.append(calc)
        if not ok:
            ev = _evidence(_find_quote(rows, text, str(record.get("quote") or record.get("name") or "")),
                           "numeric values recalculated from declared locations")
            _finding(findings, "pqa.numeric_reporting_inconsistent", "results", "high",
                     f"Reported values disagree beyond tolerance: difference={delta:g}, tolerance={tolerance:g}.",
                     ev, "numeric_inconsistency", "Reconcile the two source locations; do not harmonize them without checking the underlying data.")

    # Prefer the manuscript itself over a separate extraction field.  A reviewer
    # does not have to repeat a declaration that is already plainly present.
    text_declarations = {
        "data_availability": _find(rows, r"data (?:are |is )?availab|数据可用|数据可用性|数据集.{0,12}(?:公开|存储)"),
        "code_availability": _find(rows, r"code (?:is |are )?availab|source code|代码可用|代码.{0,12}(?:公开|托管)"),
        "competing_interests": _find(rows, r"competing interests?|conflicts? of interest|利益冲突|竞争性利益"),
        "ethics_statement": _find(rows, r"ethics (?:committee|approval)|institutional review board|informed consent|伦理委员会|伦理审批|知情同意"),
    }
    for key, meta in (("data_availability", spec.get("data_availability")),
                      ("code_availability", spec.get("code_availability")),
                      ("competing_interests", spec.get("competing_interests")),
                      ("ethics_statement", spec.get("ethics_statement"))):
        dimension, rule, note = {
            "data_availability": ("reproducibility", "pqa.data_availability_missing", "No data availability statement was located."),
            "code_availability": ("reproducibility", "pqa.code_availability_missing", "A computational study has no code/pseudocode availability declaration."),
            "competing_interests": ("ethics_compliance", "pqa.competing_interests_missing", "No competing-interest declaration was located for a declared full submission review."),
            "ethics_statement": ("ethics_compliance", "pqa.ethics_statement_missing", "Human/animal research is indicated but no ethics/consent statement was supplied."),
        }[key]
        meta_present = _truthy_text(meta) or bool(text_declarations[key])
        should_check = False
        if rule == "pqa.code_availability_missing":
            should_check = bool(spec.get("computational_study")) and not meta_present
        elif rule == "pqa.ethics_statement_missing":
            should_check = bool(spec.get("human_or_animal_research")) and not meta_present
        elif rule == "pqa.competing_interests_missing":
            should_check = spec.get("source_scope") == "full_article" and not meta_present
        else:
            should_check = spec.get("source_scope") == "full_article" and not meta_present
        if meta_present and text_declarations[key]:
            positive[dimension].append(_evidence(text_declarations[key], "declaration located in manuscript"))
        if should_check:
            _finding(findings, rule, dimension, "medium", note,
                     defect_class="reporting_gap", suggestion="Report the actual status/repository or state the applicable restriction; never invent an identifier.")

    if spec.get("source_scope") == "full_article":
        required = spec.get("required_sections", ["introduction", "methods", "results", "discussion"])
        present = {_heading(r["text"])[0] for r in rows if r.get("heading") and _heading(r["text"])}
        missing = [s for s in required if s not in present]
        # Optional algebraic data can be supplied by the extraction layer.
        if isinstance(spec.get("sections_present"), list):
            present |= set(spec["sections_present"])
            missing = [s for s in required if s not in present]
        if missing:
            _finding(findings, "pqa.full_article_sections_missing", "writing", "high",
                     "Expected sections are not present in the declared full article: " + ", ".join(missing) + ".",
                     defect_class="structural_or_extraction_gap",
                     suggestion="Check extraction completeness first; if the manuscript truly lacks these sections, restore the needed evidence-bearing sections.")
        else:
            for section in required:
                positive["writing"].append({"quote": None, "location": {"section": section},
                                            "basis": "required section heading detected"})
        if not _truthy_text(spec.get("reference_section_present")) and "references" not in present:
            citation_pattern = r"\[[0-9]+(?:[-,–][0-9]+)*\]|\([A-Z][A-Za-z-]+(?: et al\.)?,? \d{4}\)|[A-Z][A-Za-z-]+ et al\. \(\d{4}\)|参考文献|\[[A-Za-z]+\d{4}\]"
            cited = _find(rows, r"\[[0-9]+|[A-Z][A-Za-z-]+ et al\.|参考文献|\[[A-Za-z]+\d{4}\]") if re.search(citation_pattern, text, re.I) else None
            if cited:
                _finding(findings, "pqa.references_section_unresolved", "citations", "high",
                         "Citation markers are present but no references section was resolved in the declared full article.",
                         _evidence(cited, "reference list required to verify these markers"),
                         "reporting_or_extraction_gap", "Recover the reference list before judging citation completeness; unresolved extraction is not proof of misconduct.")


def _assess(spec, text, rows, findings, positive):
    supplied = spec.get("quality_assessments", spec.get("dimension_reviews", []))
    by_name = {}
    if isinstance(supplied, dict):
        supplied = [dict(v, dimension=k) if isinstance(v, dict) else {"dimension": k, "rating": v}
                    for k, v in supplied.items()]
    for item in _records(supplied):
        if isinstance(item, dict) and item.get("dimension") in DIMENSIONS:
            by_name[item["dimension"]] = item
    reviews = []
    for dimension in DIMENSIONS:
        item = by_name.get(dimension)
        issues = []
        strengths = []
        rationale = None
        rating = "not_assessed"
        if item is None:
            _finding(findings, "pqa.dimension_not_assessed", dimension, "medium",
                     f"{DIMENSION_ZH[dimension]} was not given an evidence-bound reviewer assessment.",
                     defect_class="review_gap", scope="review_process",
                     suggestion="Read the relevant manuscript passages and supply an evidence-bound assessment; absence of an assessment is not a manuscript defect.")
        else:
            rating = _norm(item.get("rating") or "assessed").lower()
            rationale = _norm(item.get("rationale") or item.get("assessment")) or None
            evidence_items = item.get("evidence", [])
            if isinstance(evidence_items, (str, dict)):
                evidence_items = [evidence_items]
            valid_evidence = []
            for ev in _records(evidence_items):
                quote = ev.get("quote", ev.get("text")) if isinstance(ev, dict) else ev
                if not _contains(text, str(quote or "")):
                    _finding(findings, "pqa.review_evidence_not_in_source", dimension, "high",
                             "A reviewer assessment cites text that is not present in the supplied manuscript.",
                             {"quote": _clip(quote), "location": _location(None),
                              "basis": "verbatim normalized-whitespace source validation failed"},
                             "review_evidence_error", "Replace the quotation with a verbatim manuscript passage or mark the judgement unverified.",
                             scope="review_process")
                    continue
                record = _evidence(_find_quote(rows, text, str(quote)), "reviewer-supplied verbatim source evidence")
                if isinstance(ev, dict) and ev.get("locator"):
                    record["reported_locator"] = ev["locator"]
                valid_evidence.append(record)
            if not valid_evidence and not _norm(item.get("basis")) and not item.get("source_limited") and not item.get("not_applicable"):
                _finding(findings, "pqa.assessment_without_evidence", dimension, "medium",
                         "A dimension rating has neither verbatim evidence nor an explicit source-limited basis.",
                         defect_class="review_gap", scope="review_process",
                         suggestion="Add exact source evidence, or declare why this dimension is not assessable/not applicable in the supplied scope.")
            else:
                strengths.extend(valid_evidence)
            for s in _records(item.get("strengths")):
                if isinstance(s, str):
                    strengths.append({"quote": None, "location": _location(None), "basis": s})
            concerns = item.get("concerns", item.get("issues", []))
            if isinstance(concerns, (str, dict)):
                concerns = [concerns]
            for concern in _records(concerns):
                if isinstance(concern, str):
                    concern = {"finding": concern}
                if not isinstance(concern, dict):
                    continue
                severity = _norm(concern.get("severity") or "medium").lower()
                if severity not in SEVERITY:
                    severity = "medium"
                own_evidence = concern.get("evidence_quote") or concern.get("quote")
                if own_evidence:
                    if not _contains(text, str(own_evidence)):
                        _finding(findings, "pqa.review_evidence_not_in_source", dimension, "high",
                                 "A concern's quoted evidence is not present in the supplied manuscript.",
                                 {"quote": _clip(own_evidence), "location": _location(None),
                                  "basis": "concern evidence source validation failed"},
                                 "review_evidence_error", "Use exact source wording or explicitly mark this concern as a reporting-level inference.",
                                 scope="review_process")
                        continue
                    ev = _evidence(_find_quote(rows, text, str(own_evidence)),
                                   _norm(concern.get("basis") or "reviewer judgement anchored to source text"))
                elif valid_evidence:
                    ev = valid_evidence[0]
                else:
                    # Reporting gaps can be grounded in an explicit searched scope,
                    # but a defect about a specific passage cannot be unanchored.
                    defect_class0 = _norm(concern.get("defect_class") or "review_observation")
                    if defect_class0 not in {"reporting_gap", "suggestion"}:
                        _finding(findings, "pqa.concern_without_source", dimension, "high",
                                 "A substantive reviewer concern has no verbatim source evidence and is therefore unverified.",
                                 defect_class="review_evidence_error", scope="review_process",
                                 suggestion="Attach exact evidence or downgrade explicitly to a bounded suggestion/reporting gap.")
                        continue
                    ev = {"quote": None, "location": _location(None),
                          "basis": _norm(concern.get("basis") or "absence assessed only within the declared source scope")}
                issue = {"id": f"pending-{dimension}-{len(issues)+1}",
                         "finding": _norm(concern.get("finding") or concern.get("message") or concern.get("issue")),
                         "severity": severity, "evidence": ev,
                         "defect_class": _norm(concern.get("defect_class") or "review_observation"),
                         "suggestion": _norm(concern.get("suggestion") or "Address the evidenced concern without inventing missing facts.")}
                if not issue["finding"]:
                    continue
                issues.append(issue)
                _finding(findings, concern.get("rule") or "pqa.reviewer_substantiated_issue", dimension,
                         severity, issue["finding"], ev, issue["defect_class"], issue["suggestion"])
        reviews.append({"dimension": dimension, "dimension_zh": DIMENSION_ZH[dimension],
                        "rubric_focus": dimension.replace("_", " "), "reviewer_rating": rating,
                        "rationale": rationale, "positive_evidence": strengths,
                        "submitted_issues": issues, "mechanical_finding_ids": []})
    return reviews


def _finalize(spec, text, sources, limits, legacy_ran, positive, calculations, findings, reviews):
    # Stable order and IDs are independent of dictionary/set iteration order.
    findings.sort(key=lambda f: (DIMENSIONS.index(f.get("dimension")) if f.get("dimension") in DIMENSIONS else 99,
                                 -SEVERITY.get(f.get("severity"), 0), str(f.get("rule", "")),
                                 str(f.get("finding", ""))))
    for i, finding in enumerate(findings, 1):
        finding["id"] = f"Q{i:03d}"
    by_dim = {d: [] for d in DIMENSIONS}
    for finding in findings:
        if finding.get("dimension") in by_dim:
            by_dim[finding["dimension"]].append(finding)
    for review in reviews:
        dim = review["dimension"]
        own = by_dim[dim]
        review["mechanical_finding_ids"] = [f["id"] for f in own if f.get("rule") != "pqa.reviewer_substantiated_issue"]
        manuscript_issues = [f for f in own if f.get("scope") == "manuscript"]
        review_gaps = [f for f in own if f.get("scope") == "review_process"]
        worst = max([SEVERITY.get(f.get("severity"), 0) for f in manuscript_issues] or [0])
        review["status"] = ("major_revision" if worst == 3 else "minor_revision" if worst == 2
                            else "attention_suggested" if worst == 1 else
                            "not_assessed" if review_gaps and review["reviewer_rating"] == "not_assessed"
                            else "no_major_defect_detected")
        review["highest_manuscript_severity"] = next((s for s, n in SEVERITY.items() if n == worst), None)
        review["finding_ids"] = [f["id"] for f in own]
        if not review["positive_evidence"]:
            review["positive_evidence"] = positive.get(dim, [])
        review["recommendation"] = ("Resolve high-severity evidence before publication readiness can be assessed."
                                    if worst == 3 else "Address evidenced issues and rerun the same source version."
                                    if worst else "No additional mechanical action; retain reviewer uncertainty and source boundaries.")
    manuscript = [f for f in findings if f.get("scope") == "manuscript"]
    process = [f for f in findings if f.get("scope") == "review_process"]
    if any(f.get("severity") == "high" for f in manuscript + process):
        status = "blocked"
    elif findings:
        status = "review"
    else:
        status = "clean"
    if any(f.get("severity") == "high" for f in manuscript):
        grade = "major_revision"
    elif any(f.get("severity") == "medium" for f in manuscript):
        grade = "minor_revision"
    elif findings:
        grade = "review_incomplete"
    else:
        grade = "no_major_defect_detected"
    counts = Counter(f.get("severity") for f in manuscript)
    process_counts = Counter(f.get("severity") for f in process)
    quotes = []
    for f in findings:
        q = (f.get("evidence") or {}).get("quote")
        if q and _contains(text, q):
            quotes.append({"finding_id": f["id"], "quote": q, "location": f.get("location")})
    audit_report = []
    for f in findings:
        audit_report.append({"id": f["id"], "rule": f["rule"], "dimension": f["dimension"],
                             "category": f.get("category"), "severity": f["severity"],
                             "location": f.get("location"), "finding": f["finding"],
                             "basis": f.get("basis"), "suggestion": f.get("suggestion"),
                             "defect_class": f.get("defect_class"), "scope": f.get("scope"),
                             "evidence": f.get("evidence")})
    result = {
        "schema_version": SCHEMA, "case_id": spec.get("case_id"), "status": status,
        "overall_assessment": {"grade": grade,
                               "basis": "highest substantiated manuscript severity; reviewer process gaps are reported separately",
                               "publication_decision": None,
                               "decision_note": "This audit is not a journal accept/reject decision."},
        "manuscript_version": spec.get("manuscript_version", spec.get("version")),
        "source_scope": spec.get("source_scope", "declared_or_discovered_excerpt"),
        "findings": findings, "audit_report": audit_report,
        "dimension_reviews": reviews,
        "severity_counts": {s: counts.get(s, 0) for s in ("high", "medium", "low")},
        "review_process_severity_counts": {s: process_counts.get(s, 0) for s in ("high", "medium", "low")},
        "evidence_and_boundaries": {
            "manuscript_quotes": quotes,
            "material_evidence": [c for c in calculations],
            "positive_evidence": positive,
            "pending_review": [f["id"] for f in process] +
                              [f["id"] for f in manuscript if f.get("defect_class") in {"reporting_gap", "reporting_or_extraction_gap", "structural_or_extraction_gap"}],
            "not_checked": [r["dimension"] for r in reviews if r["status"] == "not_assessed"]},
        "result_status": {
            "pass": [r["dimension"] for r in reviews if r["status"] == "no_major_defect_detected"],
            "problems": [f["id"] for f in manuscript],
            "pending": [f["id"] for f in process],
            "not_checked": [r["dimension"] for r in reviews if r["status"] == "not_assessed"],
            "status": status, "status_reason": f"{len(manuscript)} manuscript findings; {len(process)} review-process findings"},
        "recomputations": calculations, "sources": sources,
        "checked": {"manuscript_characters": len(text), "dimensions": len(reviews),
                    "dimensions_assessed": sum(r["reviewer_rating"] != "not_assessed" for r in reviews),
                    "legacy_sections": legacy_ran, "findings": len(findings)},
        "limits": limits,
        "review_receipt": {"engine": SCHEMA, "deterministic_order": True,
                           "source_quote_validation": "normalized whitespace, verbatim substring",
                           "dimensions": list(DIMENSIONS)},
    }
    if result["case_id"] is None:
        del result["case_id"]
    if result["manuscript_version"] is None:
        del result["manuscript_version"]
    _contract(spec, result)
    return result


def _contract(spec, result):
    contract = spec.get("output_contract")
    keys = list(contract) if isinstance(contract, dict) else [str(k) for k in contract] if isinstance(contract, list) else []
    aliases = {
        "review_report": "audit_report", "审查报告": "audit_report",
        "quality_dimensions": "dimension_reviews", "维度审查": "dimension_reviews",
        "overall_grade": "overall_assessment", "整体评价": "overall_assessment",
        "evidence": "evidence_and_boundaries", "依据与边界": "evidence_and_boundaries",
        "uncertainty": "limits", "不确定性": "limits", "source": "sources",
    }
    for key in keys:
        if key in result:
            continue
        target = aliases.get(key)
        if target:
            result[key] = copy.deepcopy(result[target])
        elif key in spec and key not in BULKY:
            result[key] = copy.deepcopy(spec[key])
        else:
            result[key] = None
            result.setdefault("limits", []).append(f"output_contract field '{key}' was not derivable by this audit")


def audit(spec: dict, manuscript_override=None, base_dir=None) -> dict:
    if not isinstance(spec, dict):
        return _refusal(spec, "case input must be a JSON object")
    base = Path(base_dir) if base_dir else Path.cwd()
    text, limits, sources = _load_manuscript(spec, base, manuscript_override)
    if not text.strip():
        return _refusal(spec, "no readable manuscript text was obtained", limits)
    rows = _sentences(text)
    findings, calculations = [], []
    positive = {d: [] for d in DIMENSIONS}
    _structured_checks(spec, text, rows, findings, calculations, positive)
    legacy_ran = _run_legacy(spec, findings, limits)
    reviews = _assess(spec, text, rows, findings, positive)
    return _finalize(spec, text, sources, limits, legacy_ran, positive, calculations, findings, reviews)


def _refusal(spec, message, limits=None):
    result = {"schema_version": SCHEMA, "status": "undetermined",
              "overall_assessment": {"grade": "not_assessable", "publication_decision": None},
              "findings": [{"id": "Q001", "rule": "pqa.input_not_readable", "severity": "high",
                            "finding": message, "message": message, "scope": "review_process",
                            "defect_class": "execution_failure", "location": _location(None),
                            "evidence": {"quote": None, "location": _location(None), "basis": "input loader"},
                            "suggestion": "Provide the actual manuscript or recover its text layer, then rerun."}],
              "audit_report": [], "dimension_reviews": [
                  {"dimension": d, "dimension_zh": DIMENSION_ZH[d], "status": "not_assessed",
                   "reviewer_rating": "not_assessed", "finding_ids": []} for d in DIMENSIONS],
              "severity_counts": {"high": 0, "medium": 0, "low": 0},
              "review_process_severity_counts": {"high": 1, "medium": 0, "low": 0},
              "evidence_and_boundaries": {"manuscript_quotes": [], "material_evidence": [],
                                            "pending_review": ["Q001"], "not_checked": list(DIMENSIONS)},
              "result_status": {"pass": [], "problems": [], "pending": ["Q001"],
                                "not_checked": list(DIMENSIONS), "status": "undetermined",
                                "status_reason": message},
              "recomputations": [], "sources": [], "checked": {"dimensions_assessed": 0},
              "limits": list(limits or []) + [message]}
    if isinstance(spec, dict):
        if spec.get("case_id") is not None:
            result["case_id"] = spec.get("case_id")
        _contract(spec, result)
    return result


def _load_case(path):
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        return data, None
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        return {}, f"case file is not readable JSON: {exc}"


def _write(path: Path, result: dict):
    try:
        path.mkdir(parents=True, exist_ok=True)
        (path / "result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n",
                                          encoding="utf-8")
        return None
    except OSError as exc:
        return str(exc)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="qualityrun", description=__doc__)
    parser.add_argument("--case"), parser.add_argument("--spec")
    parser.add_argument("--manuscript"), parser.add_argument("--out", default="out_quality")
    try:
        args, unknown = parser.parse_known_args(argv)
    except SystemExit:
        args, unknown = None, ["argument parsing failed"]
    if args is None or unknown or not (args.case or args.spec):
        result = _refusal({}, "expected --case or --spec; unknown arguments: " + ", ".join(map(str, unknown)))
        out = Path(args.out) if args is not None else Path("out_quality")
        _write(out, result)
        print(json.dumps({"status": "undetermined", "error": "invalid invocation", "wrote": str(out / "result.json")}, ensure_ascii=False))
        return 5
    source = args.case or args.spec
    spec, error = _load_case(source)
    if error:
        result = _refusal({}, error)
    else:
        try:
            result = audit(spec, args.manuscript, Path(source).resolve().parent)
        except Exception as exc:  # user input must never escape as a traceback
            result = _refusal(spec if isinstance(spec, dict) else {}, f"audit refused after an input/processing error: {exc}")
    write_error = _write(Path(args.out), result)
    if write_error:
        print(json.dumps({"status": "undetermined", "error": "result.json could not be written: " + write_error}, ensure_ascii=False))
        return 5
    print(json.dumps({"status": result["status"], "grade": result.get("overall_assessment", {}).get("grade"),
                      "findings": [f.get("rule") for f in result.get("findings", [])],
                      "wrote": str(Path(args.out) / "result.json")}, ensure_ascii=False))
    return {"clean": 0, "review": 3, "blocked": 4, "undetermined": 5}[result["status"]]


if __name__ == "__main__":
    raise SystemExit(main())
