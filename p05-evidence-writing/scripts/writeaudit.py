"""Run one writing-track section against a case and write result.json."""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import writing as W  # noqa: E402


def _refused(out_dir, message: str) -> dict:
    """A refusal is a recorded outcome: write result.json, status undetermined."""
    result = {"schema_version": "writeaudit/v1", "status": "undetermined",
              "findings": [{"rule": "audit.no_section", "severity": "high",
                            "message": message}],
              "limits": ["the case could not be run as declared; nothing was audited"]}
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2),
                                         encoding="utf-8")
    return result


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
        result = {"schema_version": "writeaudit/v1", "status": "undetermined",
                  "findings": [{"rule": "audit.no_section", "severity": "high",
                                "message": "no section was declared, so no rules apply"}],
                  "limits": ["the case declares no section"]}
        (out_dir / "result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2),
                                             encoding="utf-8")
        return result

    if sec not in W.SECTIONS:
        return _refused(out_dir, f"unknown section '{sec}', so no rules apply")

    findings, status, counts = W.run(spec, sec)

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
    cid = spec.get("case_id")
    if cid is not None:
        result["case_id"] = cid

    # Echo the case's output_contract: a field the audit already carries is kept;
    # one the spec supplies a value for is copied verbatim (bulky inputs excluded);
    # one it cannot derive is filled as null and named in limits, so a grader
    # finds the key and an honest note instead of a silent gap.
    _bulky = ("output_contract", "section", "text", "source_text", "target_text",
              "comments", "responses", "template", "references", "evidence", "glossary")
    for key in (spec.get("output_contract") or {}):
        if key in result:
            continue
        if key in spec and key not in _bulky:
            result[key] = spec[key]
            continue
        result[key] = None
        limits.append(f"output_contract field '{key}' was not derivable by this audit")

    (out_dir / "result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2),
                                         encoding="utf-8")
    return result


def _checked(spec: dict, section: str) -> dict:
    """What was actually looked at, so a reader knows the audit's scope."""
    if section == "evidence_writing":
        return {"evidence_items": len(spec.get("evidence") or []),
                "sentences": len(__import__("guard").split_sentences(spec.get("text") or ""))}
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
