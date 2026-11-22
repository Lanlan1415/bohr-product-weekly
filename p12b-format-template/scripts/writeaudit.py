"""Run one writing-track section against a case and write result.json.

Runtime contract honoured here: the case arrives as /input/case.json plus
task.md; the case carries case_id and an output_contract naming the fields its
result.json must contain. This tool writes /app/output/result.json carrying
case_id, the audit verdict, and every declared output_contract field — a field
whose value the spec carries is echoed verbatim, a field the audit fills
itself keeps the audited value, and a field nothing carries is written as None
and named in limits. The refused path (unreadable spec, non-object spec, no
declared or unknown section, audit failure) still writes a traceable
result.json with status undetermined — and never echoes contract fields,
because a refused run performed no audit.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import writing as W  # noqa: E402

EXIT_CODES = {"clean": 0, "review": 3, "blocked": 4, "undetermined": 5}


def _write(out_dir: Path, result: dict) -> None:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    (out / "result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2),
                                     encoding="utf-8")


def _refused(out_dir: Path, finding: dict, note: str, case_id=None) -> dict:
    """The honest result when the audit cannot run at all.

    Writes result.json with status undetermined (exit 5) so the platform gets
    a traceable record even from a broken input. It deliberately does NOT echo
    output_contract fields: a refused run performed no audit, and fabricating
    contract-shaped structure without evidence would be worse than none.
    """
    result = {
        "schema_version": "writeaudit/v1",
        "case_id": case_id,
        "status": "undetermined",
        "findings": [finding],
        "severity_counts": {"high": 1, "medium": 0, "low": 0},
        "checked": {},
        "limits": [note],
    }
    _write(out_dir, result)
    return result


def contract_echo(spec: dict, result: dict) -> list[str]:
    """Echo the case's declared output_contract fields into the result.

    The contract may be an object (its keys are the field names) or a list
    (strings, or objects carrying a name/field/key). Returns the limits notes:
    one per declared field that neither the audit nor the spec could fill.
    """
    contract = spec.get("output_contract")
    fields: list[str] = []
    if isinstance(contract, dict):
        fields = [str(k) for k in contract]
    elif isinstance(contract, (list, tuple)):
        for e in contract:
            if isinstance(e, str) and e.strip():
                fields.append(e.strip())
            elif isinstance(e, dict):
                name = e.get("name") or e.get("field") or e.get("key") or ""
                if str(name).strip():
                    fields.append(str(name).strip())
    notes: list[str] = []
    for f in fields:
        if result.get(f) is not None:
            continue  # already carried by the audit itself
        v = spec.get(f)
        if v is None or (isinstance(v, str) and not v.strip()):
            result[f] = None
            notes.append(f"output_contract field '{f}' has no value in the spec")
        else:
            result[f] = v
    if fields:
        result["output_contract_fields"] = fields
    return notes


def build_and_audit(spec_path: Path, out_dir: Path, section: str | None = None) -> dict:
    out_dir = Path(out_dir)
    try:
        raw = Path(spec_path).read_text(encoding="utf-8")
    except (OSError, ValueError) as exc:
        return _refused(out_dir,
                        {"rule": "audit.spec_unreadable", "severity": "high",
                         "message": "the spec file could not be read, so no rules ran"},
                        f"spec file unreadable: {exc}")
    try:
        spec = json.loads(raw)
    except (json.JSONDecodeError, UnicodeDecodeError, ValueError) as exc:
        return _refused(out_dir,
                        {"rule": "audit.spec_unreadable", "severity": "high",
                         "message": "the spec file is not valid JSON, so no rules ran"},
                        f"spec is not valid JSON: {exc}")
    if not isinstance(spec, dict):
        return _refused(out_dir,
                        {"rule": "audit.spec_not_object", "severity": "high",
                         "message": "the spec is valid JSON but not an object, so no rules "
                                    "apply"},
                        "spec must be a JSON object")
    case_id = spec.get("case_id")
    if case_id is not None and not isinstance(case_id, (str, int)):
        case_id = str(case_id)

    sec = section or spec.get("section")
    sec = str(sec) if sec is not None else None
    if not (sec and sec.strip()):
        return _refused(out_dir,
                        {"rule": "audit.no_section", "severity": "high",
                         "message": "no section was declared, so no rules apply"},
                        "the case declares no section", case_id)
    sec = sec.strip()

    try:
        findings, status, counts = W.run(spec, sec)
    except ValueError:
        return _refused(out_dir,
                        {"rule": "audit.section_unknown", "severity": "high",
                         "message": "the declared section is not one this audit implements, "
                                    "so no rules ran"},
                        f"unknown section '{sec}'", case_id)
    except Exception as exc:  # a spec the audit cannot complete on is reported, not raised
        return _refused(out_dir,
                        {"rule": "audit.section_error", "severity": "high",
                         "message": "the audit could not complete on this spec, so its "
                                    "verdict is undetermined"},
                        f"audit failed on section '{sec}': {type(exc).__name__}: {exc}",
                        case_id)

    result = {
        "schema_version": "writeaudit/v1",
        "case_id": case_id,
        "section": sec,
        "status": status,
        "findings": findings,
        "severity_counts": counts,
        "checked": _checked(spec, sec),
        "limits": [],
    }
    notes = contract_echo(spec, result)
    result["limits"] = notes or ["all declared output_contract fields carry values"]
    _write(out_dir, result)
    return result


def _checked(spec: dict, section: str) -> dict:
    """What was actually looked at, so a reader knows the audit's scope."""

    def _n(value) -> int:
        if isinstance(value, (list, tuple, dict, str)):
            return len(value)
        return 0

    if section == "evidence_writing":
        return {"evidence_items": _n(spec.get("evidence")),
                "sentences": len(__import__("guard").split_sentences(str(spec.get("text") or "")))}
    if section == "translation":
        return {"source_chars": len(str(spec.get("source_text") or "")),
                "target_chars": len(str(spec.get("target_text") or "")),
                "glossary_terms": _n(spec.get("glossary"))}
    if section == "review_response":
        comments = spec.get("comments") or []
        responses = spec.get("responses") or []
        if not isinstance(comments, (list, tuple)):
            comments = []
        if not isinstance(responses, (list, tuple)):
            responses = []
        evidence_states: dict[str, int] = {}
        for r in responses:
            if not isinstance(r, dict):
                continue
            ev_raw = r.get("evidence") or []
            if isinstance(ev_raw, (list, tuple)):
                for ev in ev_raw:
                    if not isinstance(ev, dict):
                        ev = {"status": str(ev)}
                    st = str(ev.get("status") or "unstated").strip().lower() or "unstated"
                    evidence_states[st] = evidence_states.get(st, 0) + 1
        return {"comments": len(comments),
                "responses": len(responses),
                "evidence_by_status": evidence_states}
    if section == "format_template":
        return {"headings": sum(1 for l in str(spec.get("text") or "").splitlines()
                                if __import__("re").match(r"^\s*\d+(\.\d+)*\s+\S", l)),
                "references": _n(spec.get("references"))}
    return {}


def main(argv: list[str] | None = None) -> int:
    import argparse
    ap = argparse.ArgumentParser(prog="writeaudit", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--spec", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--section", help="override the section declared in the spec")
    a = ap.parse_args(argv)
    r = build_and_audit(Path(a.spec), Path(a.out), a.section)
    print(json.dumps({"status": r["status"], "section": r.get("section"),
                      "case_id": r.get("case_id"),
                      "contract_fields": len(r.get("output_contract_fields") or []),
                      "findings": [f["rule"] for f in r["findings"]],
                      "wrote": str(Path(a.out) / "result.json")}, ensure_ascii=False))
    return EXIT_CODES.get(r["status"], 1)


if __name__ == "__main__":
    raise SystemExit(main())
