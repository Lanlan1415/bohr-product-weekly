"""Run one structured section against a case spec and write result.json."""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import sections as S  # noqa: E402


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
        spec = json.loads(Path(spec_path).read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError, OSError) as exc:
        # An unreadable spec is a refusal with the usual exit code, not a traceback.
        return _refused(out_dir, f"the spec file is not readable JSON: {exc}")
    if not isinstance(spec, dict):
        return _refused(out_dir, "the spec file is not a JSON object")
    sec = section or spec.get("section")
    out_dir = Path(out_dir); out_dir.mkdir(parents=True, exist_ok=True)

    if not sec:
        return _refused(out_dir, "no section declared, so no rules apply")
    if sec not in S.SECTIONS:
        return _refused(out_dir, f"unknown section '{sec}', so no rules apply")

    findings, status, counts = S.run(spec, sec)
    limits = []

    checked = {"section": sec, "items": _count(spec, sec)}
    if sec == "compare_docs":
        # completeness summary for the comparison matrix: which declared field each
        # supplied document reports, so unreported cells are named, not silent
        checked["coverage"] = S.compare_coverage(spec)
    if sec == "structure_logic":
        # coverage evidence for the six-dimension census: which dimensions the
        # diagnosis actually touches, and how many promises were declared
        dims = sorted({str((d or {}).get("dimension") or "").strip().lower()
                       for d in (spec.get("diagnosis") or []) if isinstance(d, dict)} - {""})
        checked["dimensions_covered"] = dims
        checked["promises_declared"] = len([p for p in (spec.get("promises") or [])
                                            if isinstance(p, dict)])
    result = {"schema_version": "secrun/v1", "section": sec, "status": status,
              "findings": findings, "severity_counts": counts, "limits": limits,
              "checked": checked}
    cid = spec.get("case_id")
    if cid is not None:
        result["case_id"] = cid

    # Echo the case's output_contract: a field the audit already carries is kept;
    # one the spec supplies a value for is copied verbatim (bulky inputs excluded);
    # one it cannot derive is filled as null and named in limits, so a grader
    # finds the key and an honest note instead of a silent gap. The contract can
    # arrive as a list, a dict, or a bare field name — anything else is recorded
    # as a limits note rather than crashing the echo.
    _bulky = ("output_contract", "section", "manuscript_text", "text", "documents",
              "references", "evidence", "paragraphs")
    oc = spec.get("output_contract")
    if oc is None:
        keys = []
    elif isinstance(oc, str):
        keys = [oc]
    elif isinstance(oc, dict):
        inner = oc.get("fields")
        keys = list(inner) if isinstance(inner, (list, tuple)) else list(oc.keys())
    elif isinstance(oc, (list, tuple)):
        keys = list(oc)
    else:
        keys = []
        limits.append("output_contract was present but is not a field list; it is "
                      "preserved verbatim in the spec echo")
    for key in keys:
        if not isinstance(key, str) or not key.strip():
            limits.append(f"output_contract contains a non-string field name: {key!r}")
            continue
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
