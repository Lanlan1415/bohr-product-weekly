"""Run one structured section against a case spec and write result.json."""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import sections as S  # noqa: E402


_BULKY = ("output_contract", "section", "manuscript_text", "text", "documents",
          "references", "evidence", "paragraphs", "materials", "records",
          "chapters", "rows", "entries", "nodes", "outline", "fields")


def _echo_contract(result: dict, spec: dict) -> dict:
    """case_id at top; output_contract field echo.
    Audit-derived > spec caller-carried scalar > null + limits note.
    """
    limits = result.setdefault("limits", [])
    cid = spec.get("case_id")
    if cid is not None:
        result["case_id"] = cid
    for key in (spec.get("output_contract") or []):
        if key in result:
            continue
        if key in spec and key not in _BULKY:
            result[key] = spec[key]
            continue
        result[key] = None
        limits.append(f"output_contract field '{key}' was not derivable by this audit")
    return result


def _refused(out_dir, message: str) -> dict:
    """The undetermined refusal every unrunnable case gets: an exit code, not a crash."""
    result = {"schema_version": "secrun/v1", "status": "undetermined",
              "findings": [{"rule": "audit.no_section", "severity": "high",
                            "message": message}],
              "limits": ["the case could not be run as declared"]}
    out_dir = Path(out_dir); out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2),
                                         encoding="utf-8")
    return result


def build_and_audit(spec_path, out_dir, section=None) -> dict:
    try:
        spec = json.loads(Path(spec_path).read_text(encoding="utf-8-sig"))
    except (json.JSONDecodeError, UnicodeDecodeError, OSError) as exc:
        # An unreadable spec is a refusal with the usual exit code, not a traceback.
        return _refused(out_dir, f"the spec file is not readable JSON: {exc}")
    if not isinstance(spec, dict):
        return _refused(out_dir, "the spec file is not a JSON object")
    sec = section or spec.get("section")
    out_dir = Path(out_dir); out_dir.mkdir(parents=True, exist_ok=True)

    if not isinstance(sec, str) or not sec:
        return _refused(out_dir, "no section declared, so no rules apply")
    if sec not in S.SECTIONS:
        return _refused(out_dir, f"unknown section '{sec}', so no rules apply")

    findings, status, counts = S.run(spec, sec)

    checked = {"section": sec, "items": _count(spec, sec)}
    if sec == "compare_docs":
        # completeness summary for the comparison matrix: which declared field each
        # supplied document reports, so unreported cells are named, not silent
        checked["coverage"] = S.compare_coverage(spec)
    result = {"schema_version": "secrun/v1", "section": sec, "status": status,
              "findings": findings, "severity_counts": counts, "limits": [],
              "checked": checked}
    result = _echo_contract(result, spec)
    (out_dir / "result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2),
                                         encoding="utf-8")
    return result


def _count(spec: dict, section: str) -> int:
    for key in ("conclusions", "claims", "documents", "formulas", "answers", "paragraphs",
                "statements", "aims", "chapters", "nodes"):
        if key in spec:
            return len(spec.get(key) or [])
    if "text" in spec:
        return len(str(spec.get("text") or "").split())
    if "checklist" in spec:
        return len(spec.get("checklist") or {})
    return 0


def main(argv=None) -> int:
    import argparse
    ap = argparse.ArgumentParser(prog="secrun", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--spec", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--section", help="override the spec's declared section")
    a = ap.parse_args(argv)
    r = build_and_audit(Path(a.spec), Path(a.out), a.section)
    print(json.dumps({"status": r["status"], "section": r.get("section"),
                      "findings": [f["rule"] for f in r["findings"]],
                      "wrote": str(Path(a.out) / "result.json")}, ensure_ascii=False))
    return {"clean": 0, "review": 3, "blocked": 4, "undetermined": 5}.get(r["status"], 1)


if __name__ == "__main__":
    raise SystemExit(main())
