"""Run one writing-track section against a case and write result.json."""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import writing as W  # noqa: E402


def _contract_keys(contract) -> list[str]:
    if isinstance(contract, dict):
        return [str(key) for key in contract]
    if isinstance(contract, list):
        return [str(key) for key in contract if isinstance(key, str)]
    return []


def _echo_contract(result: dict, spec: dict) -> dict:
    """Preserve case identity and every declared field on every run path.

    Audit-owned values win; all other values supplied by the spec are copied
    verbatim, including deliverables and evidence records.  Unknown values stay
    null and are explicitly limited rather than fabricated or dropped as bulky.
    """
    result["case_id"] = spec.get("case_id")
    keys = _contract_keys(spec.get("output_contract"))
    for key in keys:
        if key in result:
            continue
        if key in spec:
            result[key] = spec[key]
        else:
            result[key] = None
            result.setdefault("limits", []).append(
                f"output_contract field '{key}' was not derivable by this audit")
    result["output_contract_fields"] = keys
    return result


def _write_result(out_dir, result: dict) -> dict:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2),
                                         encoding="utf-8")
    return result


def _refused(out_dir, message: str, spec: dict | None = None,
             rule: str = "audit.no_section") -> dict:
    """A refusal is a recorded outcome and still honours the known contract."""
    result = {"schema_version": "writeaudit/v1", "status": "undetermined",
              "findings": [{"rule": rule, "severity": "high", "message": message}],
              "limits": ["the case could not be run as declared; nothing was audited"]}
    return _write_result(out_dir, _echo_contract(result, spec or {}))


def build_and_audit(spec_path: Path, out_dir: Path, section: str | None = None) -> dict:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    try:
        # utf-8-sig: a BOM the platform text pipeline prepended is not a spec defect;
        # refusing a readable spec over three invisible bytes would be.
        spec = json.loads(Path(spec_path).read_text(encoding="utf-8-sig"))
    except (json.JSONDecodeError, UnicodeDecodeError, OSError) as exc:
        # An unreadable spec is a refusal with the usual exit code, not a traceback.
        return _refused(out_dir, f"the spec file is not readable JSON: {exc}")
    if not isinstance(spec, dict):
        return _refused(out_dir, "the spec file is not a JSON object")
    sec = section or spec.get("section")

    if not sec:
        return _refused(out_dir, "no section was declared, so no rules apply", spec)
    if not isinstance(sec, str) or sec not in W.SECTIONS:
        return _refused(out_dir, f"unknown section '{sec}', so no rules apply", spec,
                        "audit.section_unknown")

    try:
        findings, status, counts = W.run(spec, sec)
    except Exception as exc:
        return _refused(out_dir,
                        f"the audit could not complete on this spec: {type(exc).__name__}: {exc}",
                        spec, "audit.section_error")

    limits = []
    result = {
        "schema_version": "writeaudit/v1",
        "section": sec,
        "status": status,
        "findings": findings,
        "severity_counts": counts,
        "checked": _checked(spec, sec),
        "limits": limits,
    }
    _echo_contract(result, spec)
    return _write_result(out_dir, result)


def _checked(spec: dict, section: str) -> dict:
    """What was actually looked at, so a reader knows the audit's scope."""
    if section == "evidence_writing":
        summary = W._claim_support_summary(spec)
        summary.update({
            "evidence_items": len(spec.get("evidence") or []),
            "sentences": len(__import__("guard").split_sentences(
                str(spec.get("draft") or spec.get("text") or ""))),
            "coverage_meaning": "declared, verbatim-linked coverage; not an entailment proof"})
        return summary
    if section == "translation":
        return {"source_chars": len(spec.get("source_text") or ""),
                "target_chars": len(spec.get("target_text") or ""),
                "glossary_terms": len(spec.get("glossary") or {})}
    if section == "review_response":
        return {"comments": len(spec.get("comments") or []),
                "responses": len(spec.get("responses") or [])}
    if section == "format_template":
        return {"headings": sum(1 for l in (spec.get("text") or "").splitlines()
                                if __import__("re").match(r"^\s*\d+(\.\d+)*\s+\S", l)),
                "references": len(spec.get("references") or [])}
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
                      "findings": [f["rule"] for f in r["findings"]],
                      "wrote": str(Path(a.out) / "result.json")}, ensure_ascii=False))
    return {"clean": 0, "review": 3, "blocked": 4, "undetermined": 5}.get(r["status"], 1)


if __name__ == "__main__":
    raise SystemExit(main())
