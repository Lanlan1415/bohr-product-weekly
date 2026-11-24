"""Draft/verify an Introduction + Related Work package with structured refusals.

  python -I scripts/introcrun.py --spec /app/work/spec.json --out /app/output

The spec contains real drafted prose and evidence records.  The CLI does not invent
literature, results or novelty; it checks what was actually supplied, writes the
editable manuscript and closest-work comparison CSV, and mirrors the full contract.
"""
from __future__ import annotations

import argparse
import csv
import json
import re
from collections import Counter
from pathlib import Path

SECTION_PATTERNS = {
    "background": re.compile(r"研究背景|research\s+background|(?:^|\n)#+\s*background\b", re.I),
    "related_work": re.compile(r"相关工作|related\s+work", re.I),
    "research_gap": re.compile(r"研究空白|研究缺口|research\s+gap|knowledge\s+gap", re.I),
    "contributions": re.compile(r"贡献|contributions?|objectives?(?:\s+and\s+scope)?", re.I),
}
COMPARISON_FIELDS = ("problem_setting", "method_route", "data_evaluation", "scope")
NOVELTY_OVERCLAIM = re.compile(
    r"\b(?:first[-\s]+ever|world[-\s]+first|we\s+are\s+(?:the\s+)?first|"
    r"first\s+to\s+(?:show|report|demonstrate|propose)|no\s+(?:previous|prior)\s+"
    r"(?:study|work)|unprecedented|internationally\s+leading)\b|"
    r"首次提出|首次实现|首次证明|首次报道|首创|国际领先|国际先进|国内外领先|史无前例", re.I)
EVIDENCE_STATES = ("verified_full_text", "abstract_only", "metadata_only", "author_judgment")
NOVELTY_DISCLAIMER = re.compile(
    r"不声称|不是声称|并非|不作|不能宣称|不宣称|"
    r"without\s+claiming|does\s+not\s+claim|rather\s+than\s+claim", re.I)


def _has_unqualified_novelty_overclaim(text):
    """Reject priority hype, not an explicit sentence disclaiming it."""
    for sentence in re.split(r"(?<=[.!?。！？])|\n", text or ""):
        if NOVELTY_OVERCLAIM.search(sentence) and not NOVELTY_DISCLAIMER.search(sentence):
            return True
    return False


def _records(value):
    if not isinstance(value, (list, tuple)):
        return []
    return [item for item in value if isinstance(item, dict)]


def _text(value):
    return str(value or "").strip()


def _findings(findings, code, severity, detail, **extra):
    findings.append({"code": code, "severity": severity, "detail": detail, **extra})


def _locator(anchor):
    value = anchor.get("locator")
    if isinstance(value, dict):
        return _text(value.get("section") or value.get("page") or value.get("paragraph")
                     or value.get("table") or value.get("figure") or value.get("id"))
    return _text(value)


def _contract_keys(contract):
    if isinstance(contract, dict):
        return [str(key) for key in contract]
    if isinstance(contract, list):
        return [str(item) for item in contract if isinstance(item, str)]
    return []


def _echo_contract(result, spec):
    result["case_id"] = spec.get("case_id")
    keys = _contract_keys(spec.get("output_contract"))
    result.setdefault("limits", [])
    for key in keys:
        if key in result:
            continue
        if key in spec:
            result[key] = spec[key]
        else:
            result[key] = None
            result["limits"].append(f"output_contract field '{key}' has no evidenced value")
    result["output_contract_fields"] = keys
    return result


def _write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value, encoding="utf-8")


def _refused(out_dir, detail, spec=None, code="intro.spec_unreadable"):
    result = {"schema_version": "introcrun/v1", "status": "undetermined",
              "findings": [{"code": code, "severity": "high", "detail": detail}],
              "uncertainty": [detail], "limits": ["The run could not execute as declared."]}
    spec = spec if isinstance(spec, dict) else {}
    key = spec.get("section")
    if key:
        result["section"] = key
    _echo_contract(result, spec)
    out = Path(out_dir) / "result.json"
    _write(out, json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    return result


def _anchors(paper):
    out = []
    for anchor in _records(paper.get("anchors")):
        out.append(anchor)
    if isinstance(paper.get("anchor"), dict):
        out.append(paper["anchor"])
    return out


def _verify_anchor(anchor, ref, source, findings, where):
    quote = _text(anchor.get("quote") if isinstance(anchor, dict) else "")
    locator = _locator(anchor) if isinstance(anchor, dict) else ""
    if not quote or not locator:
        _findings(findings, "INTRO_ANCHOR_INCOMPLETE", "high",
                  "A source-backed paraphrase needs exact quote and section/page/paragraph locator",
                  ref=ref, field=where)
        return False
    source_text = _text(source.get("text"))
    if source_text and quote not in source_text:
        _findings(findings, "INTRO_QUOTE_NOT_IN_SOURCE", "high",
                  "The quote is not a verbatim substring of the supplied source text",
                  ref=ref, field=where, quote=quote[:100])
        return False
    if not source_text:
        _findings(findings, "INTRO_QUOTE_UNVERIFIABLE", "medium",
                  "The source text was not supplied; the quote remains unverified rather than accepted",
                  ref=ref, field=where)
        return False
    passages = source.get("passages")
    if isinstance(passages, list):
        wanted = _locator(anchor).casefold()
        exact = [p for p in _records(passages) if _locator(p).casefold() == wanted]
        if not exact:
            _findings(findings, "INTRO_LOCATOR_NOT_IN_SOURCE", "high",
                      "The declared locator does not resolve in the source passage index", ref=ref)
            return False
        if not any(quote in _text(p.get("text")) for p in exact):
            _findings(findings, "INTRO_QUOTE_NOT_AT_LOCATOR", "high",
                      "The quote occurs elsewhere but not at the declared locator", ref=ref)
            return False
    return bool(source_text)


def _paper_checks(spec, refs, sources, findings):
    verified = {}
    groups = _records(spec.get("groups"))
    used = set()
    for group in groups:
        name = _text(group.get("group")) or "unnamed-group"
        basis = _text(group.get("basis") or group.get("basis_kind"))
        if not re.search(r"问题设定|方法路线|数据与评价|problem|method|data|evaluation|approach|route", basis, re.I):
            _findings(findings, "INTRO_GROUP_BASIS_UNDECLARED", "medium",
                      "Group must be organised by problem setting, method route or data/evaluation", group=name)
        for paper in _records(group.get("papers") or group.get("items")):
            ref = _text(paper.get("ref") or paper.get("key"))
            used.add(ref)
            where = f"{name}:{ref or '<missing-ref>'}"
            label = _text((spec.get("citation_labels") or {}).get(ref) if isinstance(spec.get("citation_labels"), dict)
                          else "") or _text(refs.get(ref, {}).get("citation")) or ref
            if label and label not in _text(spec.get("draft")):
                _findings(findings, "INTRO_MATRIX_CITATION_NOT_IN_DRAFT", "high",
                          "A compared work is absent from the final manuscript's citations", ref=ref,
                          expected_label=label)
            if ref not in refs:
                _findings(findings, "INTRO_CITATION_NOT_IN_LIBRARY", "high",
                          "A related-work row cites a work absent from the metadata library", ref=ref, group=name)
            for field in ("conclusion", "conditions", "limitation"):
                if not _text(paper.get(field)):
                    _findings(findings, "INTRO_PARAPHRASE_INCOMPLETE", "high",
                              "Each work needs conclusion, conditions and limitation columns", ref=ref, field=field)
            relation = _text(paper.get("support_relation"))
            if relation not in ("supports", "contradicts", "context"):
                _findings(findings, "INTRO_SUPPORT_UNDECLARED", "high",
                          "Bibliographic matching is not support; declare supports/contradicts/context",
                          ref=ref, found=relation)
            elif relation == "supports" and not _text(paper.get("support_reason")):
                _findings(findings, "INTRO_SUPPORT_REASON_MISSING", "high",
                          "Explain what the exact source passage supports; a title does not entail the paraphrase", ref=ref)
            by_field = {}
            for anchor in _anchors(paper):
                by_field[_text(anchor.get("field"))] = anchor
            state = _text(paper.get("evidence_status")) or "verified_full_text"
            if state not in EVIDENCE_STATES:
                _findings(findings, "INTRO_EVIDENCE_STATE_UNKNOWN", "medium",
                          "Unknown evidence availability state", ref=ref, found=state)
            local_verified = True
            for field in ("conclusion", "conditions", "limitation"):
                anchor = by_field.get(field)
                if anchor is None:
                    if state == "verified_full_text":
                        _findings(findings, "INTRO_FIELD_ANCHOR_MISSING", "high",
                                  "A verified full-text row needs an anchor for every paraphrase column",
                                  ref=ref, field=field)
                        local_verified = False
                    continue
                if not _verify_anchor(anchor, ref, sources.get(ref, {}), findings, field):
                    local_verified = False
            if state != "verified_full_text":
                local_verified = False
                _findings(findings, "INTRO_EVIDENCE_LIMITED", "medium",
                          "Paraphrase is downgraded by actual source availability; it is not full-text verified",
                          ref=ref, evidence_status=state)
                if not _text(paper.get("downgrade_reason")):
                    _findings(findings, "INTRO_DOWNGRADE_UNEXPLAINED", "medium",
                              "Abstract/metadata-only or author-judgment paraphrase needs a visible downgrade reason", ref=ref)
            verified[ref] = local_verified and state == "verified_full_text"
    return groups, used, verified


def _nearest_checks(spec, refs, sources, verified, findings):
    rows = _records(spec.get("nearest_works"))
    seen = set()
    for row in rows:
        ref = _text(row.get("ref") or row.get("key"))
        if not ref or ref in seen:
            _findings(findings, "INTRO_NEAREST_ID_INVALID", "high",
                      "Closest-work rows need a unique library identifier", ref=ref)
        seen.add(ref)
        if ref not in refs:
            _findings(findings, "INTRO_NEAREST_NOT_IN_LIBRARY", "high",
                      "Closest work is absent from the actual library", ref=ref)
            continue
        if not _text(row.get("similarity_basis")):
            _findings(findings, "INTRO_SIMILARITY_UNJUSTIFIED", "medium",
                      "'Most similar' needs an explicit shared problem/method basis", ref=ref)
        comparison_state = _text(row.get("comparison_status")) or "verified"
        if comparison_state == "verified" and not verified.get(ref, False):
            _findings(findings, "INTRO_NEAREST_COMPARISON_UNVERIFIED", "high",
                      "Closest-work differences cannot be declared verified when full-text paraphrase columns are downgraded",
                      ref=ref)
        elif comparison_state == "provisional" and not _text(row.get("reason")):
            _findings(findings, "INTRO_PROVISIONAL_UNEXPLAINED", "medium",
                      "A provisional closest-work comparison needs its uncertainty reason", ref=ref)
        for field in COMPARISON_FIELDS:
            cell = row.get(field)
            if not isinstance(cell, dict):
                _findings(findings, "INTRO_NEAREST_DIMENSION_MISSING", "high",
                          "Closest work needs point-by-point problem/method/data/scope differences",
                          ref=ref, field=field)
                continue
            for key in ("prior", "this_work", "difference"):
                if not _text(cell.get(key)):
                    _findings(findings, "INTRO_NEAREST_CELL_INCOMPLETE", "high",
                              "Each comparison cell states prior work, this work and the concrete difference",
                              ref=ref, field=field, missing=key)
            evidence = cell.get("evidence")
            if isinstance(evidence, dict):
                evidence.setdefault("locator", evidence.get("section") or evidence.get("page"))
                _verify_anchor(evidence, ref, sources.get(ref, {}), findings, f"nearest:{field}")
            elif comparison_state == "verified":
                _findings(findings, "INTRO_NEAREST_EVIDENCE_MISSING", "high",
                          "Verified comparison needs an exact prior-work quote+locator for this dimension",
                          ref=ref, field=field)
            if not _text(cell.get("current_evidence") or row.get("current_anchor")):
                _findings(findings, "INTRO_CURRENT_DIFFERENCE_UNANCHORED", "high",
                          "This-work side of a comparison needs a method/result artifact anchor",
                          ref=ref, field=field)
    return rows


def _gap_checks(spec, refs, sources, findings):
    chain = _records(spec.get("gap_chain"))
    if len(chain) < 3:
        _findings(findings, "INTRO_GAP_CHAIN_SHORT", "high",
                  "Research gap requires at least literature/cross-gap evidence, reasoning and this_work")
        return
    if _text(chain[-1].get("kind")) != "this_work":
        _findings(findings, "INTRO_GAP_NOT_CLOSED", "high",
                  "The final gap-chain step must identify this work's concrete response")
    for index, step in enumerate(chain, 1):
        if not _text(step.get("basis")):
            _findings(findings, "INTRO_GAP_BASIS_MISSING", "high",
                      "Every gap-chain step needs its derivation/grounding", step=index)
        mode = _text(step.get("evidence_or_author_judgment"))
        if mode not in ("evidence", "author_judgment"):
            _findings(findings, "INTRO_GAP_EVIDENCE_MODE_MISSING", "high",
                      "Gap steps must distinguish sourced evidence from author judgment", step=index)
        elif mode == "author_judgment" and step is not chain[-1]:
            # Author inference is legitimate, but it must be visibly bounded in the delivered draft.
            marker = _text(step.get("marker"))
            if not marker or marker not in _text(spec.get("draft")):
                _findings(findings, "INTRO_AUTHOR_JUDGMENT_HIDDEN", "medium",
                          "An author-judgment gap step is not marked in the manuscript", step=index)
        if mode == "evidence":
            evidence = step.get("evidence")
            if not isinstance(evidence, dict):
                _findings(findings, "INTRO_GAP_EVIDENCE_MISSING", "high",
                          "Sourced gap step lacks its quote+locator evidence", step=index)
                continue
            ref = _text(evidence.get("ref") or step.get("ref"))
            if ref and ref not in refs:
                _findings(findings, "INTRO_GAP_UNKNOWN_REFERENCE", "high",
                          "Gap evidence points to an unknown source", ref=ref, step=index)
            _verify_anchor(evidence, ref, sources.get(ref, {}), findings, f"gap:{index}")


def _contribution_checks(spec, findings):
    rows = _records(spec.get("contributions") or spec.get("contributions_alignment"))
    materials = _text(spec.get("materials_text"))
    for index, row in enumerate(rows, 1):
        claim = _text(row.get("claim"))
        status = _text(row.get("status")) or "aligned"
        mapped = _text(row.get("mapped_to"))
        if not claim:
            _findings(findings, "INTRO_CONTRIBUTION_EMPTY", "high",
                      "A contribution needs a verifiable proposition", contribution=index)
        if status == "aligned":
            if not mapped:
                _findings(findings, "INTRO_CONTRIBUTION_UNANCHORED", "high",
                          "Aligned contribution needs actual method/figure/table/result anchors", contribution=index)
            elif materials:
                artifacts = re.findall(r"(?:Figure|Table|Fig\.|Algorithm|方法章节|结果章节)\s*(?:§)?\s*\d+", mapped, re.I)
                missing = [item for item in artifacts if item not in materials]
                if missing:
                    _findings(findings, "INTRO_CONTRIBUTION_ARTIFACT_MISSING", "high",
                              "Contribution points to an artifact absent from this-work materials",
                              contribution=index, missing=missing)
            if not _text(row.get("scope")):
                _findings(findings, "INTRO_CONTRIBUTION_SCOPE_MISSING", "high",
                          "Contributions must state method/dataset/setting scope rather than universal novelty",
                          contribution=index)
        elif status in ("not_verifiable", "author_judgment") and not _text(row.get("reason")):
            _findings(findings, "INTRO_UNVERIFIED_REASON_MISSING", "medium",
                      "Unverifiable/author-judgment contribution needs its reason", contribution=index)
        else:
            if status not in ("aligned", "not_verifiable", "author_judgment"):
                _findings(findings, "INTRO_CONTRIBUTION_STATUS_UNKNOWN", "medium",
                          "Unknown contribution alignment state", contribution=index, found=status)
        if _has_unqualified_novelty_overclaim(claim):
            _findings(findings, "INTRO_NOVELTY_OVERCLAIM", "high",
                      "Do not claim first/unique/international priority without an explicit external review",
                      contribution=index)
    if _has_unqualified_novelty_overclaim(_text(spec.get("draft"))):
        _findings(findings, "INTRO_NOVELTY_OVERCLAIM_IN_DRAFT", "high",
                  "Draft contains an unsupported priority/first-in-field claim")
    return rows


def _background_checks(spec, findings):
    roles = {_text(row.get("role")) for row in _records(spec.get("background"))}
    missing = [role for role in ("context", "problem", "constraint")
               if role not in roles]
    for role in missing:
        _findings(findings, "INTRO_BACKGROUND_ELEMENT_MISSING", "medium",
                  "Background needs context, specific problem and technical constraint before the gap",
                  role=role)
    if not _records(spec.get("background")):
        # Structured background is expected, but a clearly fielded problem statement also counts.
        if spec.get("problem_setting") and spec.get("objective"):
            findings[:] = [f for f in findings if f.get("code") != "INTRO_BACKGROUND_ELEMENT_MISSING"]


def audit(spec):
    findings = []
    references = _records(spec.get("references") or spec.get("entries"))
    refs = {}
    sources = {}
    for index, entry in enumerate(references):
        key = _text(entry.get("key") or entry.get("id") or entry.get("ref"))
        if not key:
            _findings(findings, "INTRO_REFERENCE_ID_MISSING", "medium",
                      "Bibliographic entry needs a stable key/DOI/arXiv identifier", entry=index)
            continue
        if key in refs:
            _findings(findings, "INTRO_REFERENCE_ID_DUPLICATE", "high",
                      "Duplicate reference ids break citation identity", ref=key)
        refs[key] = entry
        sources[key] = entry
        for field in ("title", "authors", "year", "venue"):
            if not _text(entry.get(field) or entry.get("author")):
                _findings(findings, "INTRO_REFERENCE_METADATA_INCOMPLETE", "medium",
                          "Bibliographic identity needs title/authors/year/venue copied from actual metadata",
                          ref=key, field=field)
    if not refs:
        _findings(findings, "INTRO_LIBRARY_EMPTY", "medium",
                  "No library was provided; related-work coverage remains partial, not invented")
    _background_checks(spec, findings)
    for section, pattern in SECTION_PATTERNS.items():
        if not pattern.search(_text(spec.get("draft"))):
            _findings(findings, "INTRO_MANUSCRIPT_SECTION_MISSING", "high",
                      "Editable manuscript is missing a required Introduction/Related Work element", section=section)
    groups, used, verified = _paper_checks(spec, refs, sources, findings)
    nearest = _nearest_checks(spec, refs, sources, verified, findings)
    _gap_checks(spec, refs, sources, findings)
    contributions = _contribution_checks(spec, findings)
    if not nearest:
        _findings(findings, "INTRO_CLOSEST_WORK_MISSING", "high",
                  "At least one closest work needs point-by-point differences versus this work")
    counts = Counter(f["severity"] for f in findings)
    status = "blocked" if counts.get("high") else ("review" if findings else "clean")
    verification = {
        "references": len(refs), "related_work_rows": sum(len(_records(g.get("papers") or g.get("items"))) for g in groups),
        "cited_rows": len(used), "closest_work_comparisons": len(nearest),
        "comparison_dimensions_per_row": list(COMPARISON_FIELDS),
        "full_text_verified_refs": sorted(key for key, value in verified.items() if value),
        "contributions_aligned": sum(_text(row.get("status") or "aligned") == "aligned" for row in contributions),
        "gap_steps": len(_records(spec.get("gap_chain"))),
        "coverage_limit": "Coverage is over the supplied actual library/scientific material, not a claim of complete-field retrieval.",
        "support_limit": "Exact quotes and declared paraphrase reasons are auditable; bibliographic identity never counts as entailment.",
    }
    return findings, status, dict(counts), verification


def _write_artifacts(spec, out_dir, result):
    out_dir.mkdir(parents=True, exist_ok=True)
    manuscript = _text(spec.get("draft"));
    if manuscript:
        _write(out_dir / "intro_related_work.md", manuscript + "\n")
    rows = []
    for work in _records(spec.get("nearest_works")):
        row = {"ref": _text(work.get("ref") or work.get("key")),
               "comparison_status": _text(work.get("comparison_status")) or "verified"}
        for field in COMPARISON_FIELDS:
            cell = work.get(field) if isinstance(work.get(field), dict) else {}
            row[f"{field}__prior"] = _text(cell.get("prior"))
            row[f"{field}__this_work"] = _text(cell.get("this_work"))
            row[f"{field}__difference"] = _text(cell.get("difference"))
        row["current_anchor"] = _text(work.get("current_anchor"))
        rows.append(row)
    fields = ["ref", "comparison_status"] + [f"{field}__{part}" for field in COMPARISON_FIELDS
                                              for part in ("prior", "this_work", "difference")] + ["current_anchor"]
    path = out_dir / "comparison_matrix.csv"
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    _write(out_dir / "result.json", json.dumps(result, ensure_ascii=False, indent=2) + "\n")


def run(spec_path, out_dir):
    try:
        spec = json.loads(Path(spec_path).read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        return _refused(out_dir, f"Spec is not readable JSON: {type(exc).__name__}: {exc}")
    if not isinstance(spec, dict):
        return _refused(out_dir, "Spec must be a JSON object", code="intro.spec_not_object")
    section = spec.get("section")
    if section and section not in ("introduction_related_work", "intro_related_work", "introduction"):
        return _refused(out_dir, f"Unknown section '{section}'; this package writes introduction and related work",
                        spec, code="intro.section_unknown")
    out_dir = Path(out_dir)
    findings, status, counts, verification = audit(spec)
    result = {"schema_version": "introcrun/v1", "section": "introduction_related_work",
              "status": status, "findings": findings, "severity_counts": counts,
              "verification": verification,
              "uncertainty": list(spec.get("uncertainty") or []) if isinstance(spec.get("uncertainty"), list) else [],
              "human_review_items": list(spec.get("human_review_items") or [])
              if isinstance(spec.get("human_review_items"), list) else [],
              "deliverables": spec.get("deliverables") or ["intro_related_work.md", "comparison_matrix.csv", "result.json"],
              "limits": ["Closest-work completeness is bounded by the supplied library; no complete-field novelty claim is inferred."]}
    try:
        _echo_contract(result, spec)
        _write_artifacts(spec, out_dir, result)
    except (OSError, TypeError, ValueError, csv.Error) as exc:
        return _refused(out_dir, f"Artifacts could not be generated: {type(exc).__name__}: {exc}", spec,
                        code="intro.artifact_error")
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--spec", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args(argv)
    result = run(args.spec, args.out)
    print(json.dumps({"status": result.get("status"), "case_id": result.get("case_id"),
                      "findings": [f["code"] for f in result.get("findings", [])],
                      "wrote": str(Path(args.out) / "result.json")}, ensure_ascii=False))
    return {"clean": 0, "review": 3, "blocked": 4, "undetermined": 5}.get(result.get("status"), 5)


if __name__ == "__main__":
    raise SystemExit(main())
