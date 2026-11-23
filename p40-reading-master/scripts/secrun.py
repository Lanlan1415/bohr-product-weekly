"""Run one structured reading section against a case spec and write result.json."""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import contract as C  # noqa: E402
import sections as S  # noqa: E402


def _refused(out_dir, message: str, rule: str = "audit.no_section") -> dict:
    """Write an undetermined refusal; deliberately do not echo an output contract."""
    result = {
        "schema_version": "secrun/v1",
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
    if sec not in S.SECTIONS:
        return _refused(out_dir, f"unknown section '{sec}', so no rules apply")

    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    try:
        findings, status, counts = S.run(spec, sec)
        checked = {"section": sec, "items": _count(spec, sec)}
        if sec == "compare_docs":
            checked["coverage"] = S.compare_coverage(spec)
    except Exception as exc:  # the last engine boundary, not a user-visible traceback
        return _refused(out_dir,
                        f"the audit ended unexpectedly: {type(exc).__name__}: {str(exc)[:180]}",
                        "audit.spec_malformed")

    result = {
        "schema_version": "secrun/v1",
        "section": sec,
        "status": status,
        "findings": findings,
        "severity_counts": counts,
        "limits": [],
        "checked": checked,
    }
    if status != "undetermined":
        C.merge_result(result, spec)
    elif C.case_id(spec) is not None:
        result["case_id"] = C.case_id(spec)
    (out_dir / "result.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return result


def _count(spec: dict, section: str) -> int:
    for key in ("conclusions", "claims", "documents", "formulas", "answers", "paragraphs",
                "statements", "aims", "chapters", "nodes"):
        value = spec.get(key)
        if isinstance(value, (list, dict)):
            return len(value)
    if "text" in spec:
        return len(str(spec.get("text") or "").split())
    if isinstance(spec.get("checklist"), dict):
        return len(spec["checklist"])
    return 0


def main(argv=None) -> int:
    import argparse
    ap = argparse.ArgumentParser(prog="secrun", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--spec", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--section", help="override the spec's declared section")
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
