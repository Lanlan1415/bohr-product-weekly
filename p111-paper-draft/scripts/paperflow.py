"""Build and audit an editable, evidence-linked manuscript result.

Primary entry point for the academic-paper-writing skill.  The established
``sections.py`` audit remains the fact/citation checker; this module adds the
paper-scale delivery contract: real section headings, non-empty sections, an
explicit problem -> method -> evidence -> conclusion chain, paragraph context
records, editable runtime artefacts, and top-level output_contract echo.

Usage:
  python paperflow.py --spec /app/work/spec.json --case /input/case.json \
      --out /app/output

Exit codes: 0 clean, 3 review, 4 blocked, 5 undetermined.  Every input failure
that can be represented is written as structured result.json, not a traceback.
Only Python's standard library is used.
"""
from __future__ import annotations

import argparse
import copy
import json
import re
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
import sections as S  # noqa: E402

EXIT = {"clean": 0, "review": 3, "blocked": 4, "undetermined": 5}
DERIVED = {"case_id", "status", "section", "findings", "severity_counts",
           "checked", "limits", "deliverable", "evidence_map", "boundary",
           "paragraph_ledger", "argument_chain_audit", "build"}
PLACEHOLDER = re.compile(
    r"\b(?:TODO|TBD|FIXME|PLACEHOLDER)\b|\[insert[^\]]*\]|待补|待确认|待核|待填",
    re.IGNORECASE)
HEADING_NAMES = {
    "abstract": ("abstract", "摘要"),
    "introduction": ("introduction", "background", "引言", "背景"),
    "methods": ("method", "methods", "materials and methods", "study design",
                "experimental section", "experimental procedures", "方法",
                "研究方法", "实验方法", "数据与方法", "实验部分"),
    "results": ("results", "results and discussion", "结果", "结果与讨论"),
    "discussion": ("discussion", "讨论"),
    "conclusion": ("conclusion", "conclusions", "结论"),
    "references": ("references", "bibliography", "参考文献"),
    "data_availability": ("data availability", "data availability statement",
                          "数据可得性", "数据可用性"),
    "acknowledgements": ("acknowledgement", "acknowledgements", "致谢"),
}


def _add(findings: list[dict], rule: str, severity: str, message: str, **kw: Any) -> None:
    findings.append({"rule": rule, "severity": severity, "message": message, **kw})


def _norm(text: Any) -> str:
    return re.sub(r"\s+", " ", str(text or "")).strip()


def _heading_key(text: Any) -> str:
    value = _norm(text).lower().strip("# ")
    value = re.sub(r"^\d+(?:\.\d+)*[.、]?\s+", "", value)
    value = value.rstrip(".:：").strip()
    for canonical, aliases in HEADING_NAMES.items():
        if value in aliases:
            return canonical
    return value.replace(" ", "_")


def parse_sections(draft: str) -> list[dict]:
    """Return only real standalone headings; prose mentioning a section is not one."""
    lines = draft.splitlines()
    marks: list[tuple[int, str, str]] = []
    for i, raw in enumerate(lines):
        line = raw.strip()
        if not line:
            continue
        candidate = re.sub(r"^#{1,6}\s+", "", line)
        # A heading is one short line, not a sentence that happens to say Methods.
        if len(candidate) <= 100 and not re.search(r"[。！？!?]$", candidate):
            key = _heading_key(candidate)
            known = any(candidate.lower().strip("# ").rstrip(".:：") in aliases
                        for aliases in HEADING_NAMES.values())
            numbered = bool(re.match(r"^\d+(?:\.\d+)*[.、]?\s+\S+", candidate))
            markdown = line.startswith("#")
            if known or (numbered and len(candidate.split()) <= 12):
                marks.append((i, key, _norm(candidate)))
    sections: list[dict] = []
    for pos, (start, key, title) in enumerate(marks):
        end = marks[pos + 1][0] if pos + 1 < len(marks) else len(lines)
        sections.append({"id": key or f"section_{pos + 1}", "title": title,
                         "line": start + 1, "text": "\n".join(lines[start + 1:end]).strip()})
    return sections


def _required_sections(spec: dict) -> list[str]:
    template = spec.get("template") if isinstance(spec.get("template"), dict) else {}
    raw = template.get("sections") or []
    if isinstance(raw, str):
        raw = [raw]
    if not isinstance(raw, (list, tuple)):
        return []
    return [_heading_key(s) for s in raw if _norm(s)]


def _paragraphs(sections: list[dict], draft: str) -> list[dict]:
    ledger: list[dict] = []
    source_sections = sections or [{"id": "unsectioned", "title": "Unsectioned",
                                    "line": 1, "text": draft}]
    for sec in source_sections:
        text = str(sec.get("text") or "")
        blocks = [b.strip() for b in re.split(r"\n\s*\n", text) if b.strip()]
        # Short authored examples often use one paragraph per line without blank lines.
        if len(blocks) == 1 and len(text.splitlines()) > 1:
            blocks = [b.strip() for b in text.splitlines() if b.strip()]
        for block in blocks:
            pid = f"P{len(ledger) + 1:03d}"
            anchors = re.findall(r"\{([A-Za-z0-9:_\-]+)\}", block)
            citations = re.findall(r"\[([A-Za-z][A-Za-z0-9_:\-]*)\]", block)
            ledger.append({"id": pid, "section": sec["id"],
                           "role": sec["id"], "text": block,
                           "material_anchors": anchors, "citation_keys": citations,
                           "previous": ledger[-1]["id"] if ledger else None})
            if len(ledger) > 1:
                ledger[-2]["next"] = pid
    if ledger:
        ledger[-1]["next"] = None
    return ledger


def _chain_items(raw: Any) -> list[dict]:
    if isinstance(raw, dict):
        raw = [raw]
    if not isinstance(raw, (list, tuple)):
        return []
    return [x if isinstance(x, dict) else {"problem": str(x)} for x in raw]


def audit_flow(spec: dict, findings: list[dict]) -> tuple[list[dict], list[dict], list[dict]]:
    draft = str(spec.get("draft") or spec.get("text") or "")
    sections = parse_sections(draft)
    required = _required_sections(spec)
    by_id = {s["id"]: s for s in sections}
    missing = [s for s in required if s not in by_id]
    if missing:
        _add(findings, "pf.section_heading_missing", "high",
             "a required section is not present as a real standalone heading; prose or a "
             "placeholder mentioning its name is not the section", missing=missing)
    for sec in sections:
        if required and sec["id"] in required and not _norm(sec.get("text")):
            _add(findings, "pf.section_empty", "high",
                 "a required heading has no body content", section=sec["id"],
                 line=sec["line"])
    if required and not missing:
        positions = [next(i for i, s in enumerate(sections) if s["id"] == name)
                     for name in required]
        if positions != sorted(positions):
            _add(findings, "pf.section_order_inconsistent", "medium",
                 "required section headings do not follow the template order",
                 expected=required, found=[s["id"] for s in sections])

    # The chain is an index of exact manuscript quotes plus material ids.  It does not
    # ask the writer to invent a new claim; it proves that the claims already in the
    # manuscript meet each other across sections.
    chain = _chain_items(spec.get("argument_chain"))
    is_full_paper = ({"introduction", "methods", "results"}.issubset(set(required))
                     and bool({"discussion", "conclusion"} & set(required)))
    if is_full_paper and not chain:
        _add(findings, "pf.argument_chain_missing", "high",
             "a full-paper draft needs a problem-method-evidence-conclusion index; map exact "
             "quotes and existing material ids rather than adding new scientific claims")
    material_records = spec.get("materials") if isinstance(spec.get("materials"), (list, tuple)) else []
    figure_records = spec.get("figures") if isinstance(spec.get("figures"), (list, tuple)) else []
    reference_records = spec.get("references") if isinstance(spec.get("references"), (list, tuple)) else []
    known_evidence = {str(x.get("id")) for x in material_records
                      if isinstance(x, dict) and x.get("id")}
    known_evidence |= {str(x.get("id")) for x in figure_records
                       if isinstance(x, dict) and x.get("id")}
    known_evidence |= {str(x.get("key")) for x in reference_records
                       if isinstance(x, dict) and x.get("key")}
    chain_audit: list[dict] = []
    for idx, item in enumerate(chain):
        cid = _norm(item.get("id")) or f"Q{idx + 1}"
        roles = ("problem", "method", "conclusion")
        absent = [role for role in roles if not _norm(item.get(role))]
        evidence = item.get("evidence")
        if isinstance(evidence, str):
            evidence = [evidence]
        if not isinstance(evidence, (list, tuple)):
            evidence = []
        if not evidence:
            absent.append("evidence")
        if absent:
            _add(findings, "pf.chain_link_missing", "high",
                 "an argument-chain row does not connect problem, method, evidence and conclusion",
                 chain_id=cid, missing=absent)
        section_map = item.get("sections") if isinstance(item.get("sections"), dict) else {}
        role_quotes: dict[str, bool] = {}
        for role in roles:
            quote = _norm(item.get(role))
            if not quote:
                continue
            wanted = _heading_key(section_map.get(role) or (
                "introduction" if role == "problem" else
                "methods" if role == "method" else "conclusion"))
            haystack = by_id.get(wanted, {}).get("text", "") if wanted in by_id else draft
            found = _norm(quote) in _norm(haystack)
            role_quotes[role] = found
            if not found:
                _add(findings, "pf.chain_quote_not_in_draft", "high",
                     "an argument-chain quote cannot be found in its assigned manuscript section",
                     chain_id=cid, role=role, expected_section=wanted)
        unknown = [str(e) for e in evidence if str(e) not in known_evidence]
        if unknown:
            _add(findings, "pf.chain_evidence_unknown", "high",
                 "an argument-chain row points to evidence absent from the material/figure/"
                 "reference index", chain_id=cid, unknown=unknown)
        chain_audit.append({"id": cid, "complete": not absent,
                            "evidence": [str(e) for e in evidence],
                            "quotes_located": role_quotes,
                            "sections": {k: _heading_key(v) for k, v in section_map.items()}})

    ledger = _paragraphs(sections, draft)
    pids = {p["id"] for p in ledger}
    links = spec.get("paragraph_links") or spec.get("context_contract") or []
    if isinstance(links, dict):
        links = links.get("links") or []
    if not isinstance(links, (list, tuple)):
        links = []
    clean_links: list[dict] = []
    for idx, link in enumerate(links):
        if not isinstance(link, dict):
            _add(findings, "pf.context_link_invalid", "medium",
                 "a paragraph context link is not an object", link_index=idx)
            continue
        source, target = _norm(link.get("from")), _norm(link.get("to"))
        relation = _norm(link.get("relation"))
        valid = source in pids and target in pids and source != target and bool(relation)
        if valid:
            source_i = next(i for i, p in enumerate(ledger) if p["id"] == source)
            target_i = next(i for i, p in enumerate(ledger) if p["id"] == target)
            valid = source_i < target_i
        if not valid:
            _add(findings, "pf.context_link_invalid", "medium",
                 "a context link must join existing distinct paragraph ids in forward order "
                 "and name their relation", link_index=idx, source=source, target=target)
        else:
            clean_links.append({"from": source, "to": target, "relation": relation})

    registered = " ".join(str(x) for x in (spec.get("review_points") or []))
    registered += " " + " ".join(str(x) for x in (spec.get("limits") or []))
    for p in ledger:
        marker = PLACEHOLDER.search(p["text"])
        if marker and marker.group(0).lower() not in registered.lower() and not registered.strip():
            _add(findings, "pf.placeholder_unregistered", "medium",
                 "an unresolved manuscript marker is not routed to a review point or limit",
                 paragraph=p["id"], marker=marker.group(0))
    return sections, ledger, chain_audit


def contract_names(raw: Any) -> list[str]:
    """Accept map and list output_contract spellings without renaming any field."""
    names: list[str] = []
    if isinstance(raw, dict):
        wrapper = {"fields", "required", "lists", "optional"}
        if raw and set(raw).issubset(wrapper):
            for value in raw.values():
                for name in contract_names(value):
                    if name not in names:
                        names.append(name)
        else:
            names = [str(k) for k in raw]
    elif isinstance(raw, (list, tuple)):
        for entry in raw:
            if isinstance(entry, str):
                name = entry
            elif isinstance(entry, dict):
                name = str(entry.get("name") or entry.get("field") or entry.get("key") or "")
            else:
                continue
            if name and name not in names:
                names.append(name)
    return names


def echo_contract(spec: dict, result: dict) -> None:
    fields = contract_names(spec.get("output_contract"))
    limits = result.setdefault("limits", [])
    for field in fields:
        if field in DERIVED and field in result:
            if result[field] is None and not any(field in str(note) for note in limits):
                limits.append(f"output_contract field '{field}' is null because the engine could not derive it")
            continue  # engine evidence has priority over a case-provided claim
        if field in spec and field != "output_contract" and spec[field] is not None:
            result[field] = copy.deepcopy(spec[field])
        else:
            result[field] = None
            limits.append(f"output_contract field '{field}' was not derivable; left null")
    if fields:
        result["output_contract_fields"] = fields


def _status(findings: list[dict]) -> tuple[str, dict]:
    counts: dict[str, int] = {}
    for f in findings:
        sev = str(f.get("severity") or "medium")
        counts[sev] = counts.get(sev, 0) + 1
    return ("blocked" if counts.get("high") else "review" if findings else "clean"), counts


def _write(out: Path, result: dict) -> None:
    out.mkdir(parents=True, exist_ok=True)
    (out / "result.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _refusal(out: Path, message: str, spec: dict | None = None,
             rule: str = "audit.spec_unreadable") -> dict:
    spec = spec if isinstance(spec, dict) else {}
    limits = [message]
    result = {"schema_version": "paperflow/v1", "case_id": spec.get("case_id"),
              "section": "paper_draft", "status": "undetermined",
              "findings": [{"rule": rule, "severity": "high", "message": message}],
              "severity_counts": {"high": 1}, "checked": {}, "limits": limits,
              "deliverable": None, "evidence_map": [], "boundary": {"human_review": [message]}}
    echo_contract(spec, result)
    _write(out, result)
    return result


def build(spec: dict, out: Path) -> dict:
    draft = str(spec.get("draft") or spec.get("text") or "")
    # Reuse the established clean/fact/citation engine unchanged, then add paper-scale checks.
    findings, _, _ = S.run(spec, "paper_draft")
    sections, ledger, chain_audit = audit_flow(spec, findings)
    status, counts = _status(findings)
    cid = spec.get("case_id")
    cid = str(cid) if cid is not None else None
    materials = spec.get("materials") if isinstance(spec.get("materials"), list) else []
    references = spec.get("references") if isinstance(spec.get("references"), list) else []
    evidence_map = [
        {"kind": "material", "id": str(m.get("id")), "locator": m.get("locator"),
         "text": m.get("text")} for m in materials if isinstance(m, dict)
    ] + [
        {"kind": "reference", "id": str(r.get("key")), "authors": r.get("authors"),
         "year": r.get("year"), "journal": r.get("journal"), "doi": r.get("doi")}
        for r in references if isinstance(r, dict)
    ]
    review_points = spec.get("review_points") or spec.get("open_questions") or []
    declared_limits = spec.get("limits") if isinstance(spec.get("limits"), list) else []
    result = {
        "schema_version": "paperflow/v1", "case_id": cid, "section": "paper_draft",
        "status": status, "findings": findings, "severity_counts": counts,
        "checked": {"sections": len(sections), "required_sections": len(_required_sections(spec)),
                    "paragraphs": len(ledger), "argument_links": len(chain_audit),
                    "materials": len(materials), "references": len(references)},
        "limits": list(declared_limits),
        "deliverable": {"kind": "editable_manuscript", "path": "manuscript.md",
                        "format": "markdown", "text": draft,
                        "sections": [{k: s[k] for k in ("id", "title", "line")} for s in sections]},
        "evidence_map": evidence_map,
        "paragraph_ledger": ledger,
        "argument_chain_audit": chain_audit,
        "boundary": {"human_review": review_points, "declared_limits": declared_limits},
        "build": {"manuscript_generated": bool(draft.strip()),
                  "citation_keys_resolved": not any(f["rule"] == "pd.unknown_source" for f in findings),
                  "all_required_headings_present": all(s in {x["id"] for x in sections}
                                                        for s in _required_sections(spec)),
                  "visual_or_typesetting_check": "not_performed"},
    }
    echo_contract(spec, result)
    _write(out, result)
    # Runtime artefacts are regenerated wholesale: no append and no run-dependent timestamp.
    (out / "manuscript.md").write_text(draft, encoding="utf-8")
    (out / "evidence_map.json").write_text(
        json.dumps(evidence_map, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (out / "paragraph_ledger.json").write_text(
        json.dumps(ledger, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return result


def load_spec(spec_path: Path, case_path: Path | None) -> dict:
    raw = json.loads(spec_path.read_text(encoding="utf-8-sig"))
    if not isinstance(raw, dict):
        raise ValueError("spec must be a JSON object")
    if case_path is None:
        return raw
    case = json.loads(case_path.read_text(encoding="utf-8-sig"))
    if not isinstance(case, dict):
        raise ValueError("case must be a JSON object")
    merged = dict(case)
    merged.update(raw)  # authored spec supplies the draft; case supplies contract fallbacks
    if "case_id" not in raw:
        for key in ("case_id", "id", "caseId"):
            if case.get(key) is not None:
                merged["case_id"] = case[key]
                break
    return merged


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--spec", required=True)
    ap.add_argument("--case")
    ap.add_argument("--out", required=True)
    args = ap.parse_args(argv)
    out = Path(args.out)
    try:
        spec = load_spec(Path(args.spec), Path(args.case) if args.case else None)
        result = build(spec, out)
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
        result = _refusal(out, f"input could not be read as a valid spec/case: {exc}")
    except Exception as exc:  # final structured boundary: never expose a traceback to the runner
        result = _refusal(out, f"manuscript audit could not complete: {type(exc).__name__}: {exc}",
                          rule="audit.section_error")
    print(json.dumps({"status": result.get("status"), "case_id": result.get("case_id"),
                      "findings": [f.get("rule") for f in result.get("findings", [])],
                      "wrote": str(out / "result.json")}, ensure_ascii=False))
    return EXIT.get(str(result.get("status")), 5)


if __name__ == "__main__":
    raise SystemExit(main())
