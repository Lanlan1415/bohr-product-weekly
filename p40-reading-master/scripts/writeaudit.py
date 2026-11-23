"""Run one writing-track reading audit and write result.json.

Unreadable JSON, a non-object spec, a missing/unknown section and unexpected malformed
shapes produce undetermined + exit 5 with a result.json, never a bare traceback.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import contract as C  # noqa: E402
import writing as W  # noqa: E402


def _refused(out_dir, message: str, rule: str = "audit.no_section") -> dict:
    """Undetermined refusal; no contract echo is performed on this path."""
    result = {
        "schema_version": "writeaudit/v1",
        "status": "undetermined",
        "findings": [{"rule": rule, "severity": "high", "message": message}],
        "severity_counts": {"high": 1},
        "checked": {},
        "limits": ["the case could not be run as declared"],
    }
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "result.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return result


def build_and_audit(spec_path, out_dir, section=None) -> dict:
    try:
        spec = json.loads(Path(spec_path).read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError, OSError) as exc:
        return _refused(out_dir, f"the spec file is not readable JSON: {exc}")
    if not isinstance(spec, dict):
        return _refused(out_dir, "the spec file is not a JSON object")
    sec = section or spec.get("section")
    if not sec:
        return _refused(out_dir, "no section declared, so no rules apply")
    if sec not in W.SECTIONS:
        return _refused(out_dir, f"unknown section '{sec}', so no rules apply")

    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    try:
        findings, status, counts = W.run(spec, sec)
        checked = _checked(spec, sec)
    except Exception as exc:
        return _refused(out_dir,
                        f"the audit ended unexpectedly: {type(exc).__name__}: {str(exc)[:180]}",
                        "audit.spec_malformed")
    result = {
        "schema_version": "writeaudit/v1",
        "section": sec,
        "status": status,
        "findings": findings,
        "severity_counts": counts,
        "checked": checked,
        "limits": [],
    }
    if status != "undetermined":
        C.merge_result(result, spec)
    elif C.case_id(spec) is not None:
        result["case_id"] = C.case_id(spec)
    (out_dir / "result.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return result


def _checked(spec: dict, section: str) -> dict:
    """What was actually examined, using only shapes that are safe to measure."""
    if section == "evidence_writing":
        evidence = spec.get("evidence")
        return {"evidence_items": len(evidence) if isinstance(evidence, list) else 0,
                "sentences": len(__import__("guard").split_sentences(
                    str(spec.get("draft") or spec.get("text") or "")))}
    if section == "translation":
        glossary = spec.get("glossary")
        return {"source_chars": len(str(spec.get("source_text") or "")),
                "target_chars": len(str(spec.get("target_text") or "")),
                "glossary_terms": len(glossary) if isinstance(glossary, dict) else 0}
    if section == "review_response":
        comments, responses = spec.get("comments"), spec.get("responses")
        return {"comments": len(comments) if isinstance(comments, list) else 0,
                "responses": len(responses) if isinstance(responses, list) else 0}
    if section == "format_template":
        references = spec.get("references")
        return {"headings": sum(1 for line in str(spec.get("text") or "").splitlines()
                                if __import__("re").match(r"^\s*\d+(\.\d+)*\s+\S", line)),
                "references": len(references) if isinstance(references, list) else 0}
    return {}


def main(argv: list[str] | None = None) -> int:
    import argparse
    ap = argparse.ArgumentParser(prog="writeaudit", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--spec", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--section", help="override the section declared in the spec")
    args = ap.parse_args(argv)
    try:
        result = build_and_audit(Path(args.spec), Path(args.out), args.section)
    except Exception as exc:
        try:
            result = _refused(Path(args.out),
                              f"the audit ended unexpectedly: {type(exc).__name__}: {str(exc)[:180]}",
                              "audit.spec_malformed")
        except Exception:
            print(json.dumps({"status": "undetermined", "wrote": None,
                              "error": f"{type(exc).__name__}: {str(exc)[:140]}"},
                             ensure_ascii=False))
            return 5
    print(json.dumps({"status": result["status"], "section": result.get("section"),
                      "findings": [f["rule"] for f in result["findings"]],
                      "wrote": str(Path(args.out) / "result.json")}, ensure_ascii=False))
    return C.status_exit(result["status"])


if __name__ == "__main__":
    raise SystemExit(main())
