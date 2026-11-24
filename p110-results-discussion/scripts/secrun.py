"""Run one structured section against a case spec and write result.json.

The result carries, per the task's output requirements:

  case_id            the input identifier, echoed from the spec
  output_contract_*  every field the case's output_contract names (kept when the
                     result already carries it, copied verbatim when the spec
                     supplies it, null + a limit note when it cannot be derived)
  deliverable        the editable artifact (目标产物)
  evidence_map       per-item source/verdict ledger (事实与来源映射)
  boundary           human-review items and uncertainties (版本与边界)
  status / findings  the audit verdict and its rule-level detail

Exit codes: 0 clean, 3 review, 4 blocked, 5 undetermined (refused, never a crash).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import sections as S  # noqa: E402

def _contract_keys(contract) -> list[str]:
    if isinstance(contract, dict):
        return [str(key) for key in contract]
    if isinstance(contract, list):
        return [str(key) for key in contract if isinstance(key, str)]
    return []


def _write_result(out_dir, result: dict) -> dict:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2),
                                         encoding="utf-8")
    return result


def _refused(out_dir, message: str, spec: dict | None = None,
             rule: str = "audit.no_section") -> dict:
    """A structured refusal; a readable spec still gets complete contract echo."""
    result = {"schema_version": "secrun/v1", "status": "undetermined",
              "findings": [{"rule": rule, "severity": "high", "message": message}],
              "limits": ["the case could not be run as declared"]}
    _echo_contract(result, spec or {})
    return _write_result(out_dir, result)


def _echo_contract(result: dict, spec: dict) -> dict:
    """Echo identity and every declared value, regardless of payload shape/size."""
    if not isinstance(spec, dict):
        spec = {}
    result.setdefault("case_id", spec.get("case_id"))
    limits = result.setdefault("limits", [])
    keys = _contract_keys(spec.get("output_contract"))
    if spec.get("output_contract") is not None and not isinstance(
            spec.get("output_contract"), (dict, list)):
        limits.append("output_contract is neither an object nor an array; fields were read as empty")
    for key in keys:
        if key in result:
            continue
        if key in spec:
            result[key] = spec[key]
        else:
            result[key] = None
            limits.append(f"output_contract field '{key}' was not derivable by this audit")
    result["output_contract_fields"] = keys
    return result


def _deliverable(spec: dict, section: str) -> dict:
    """The editable artifact the task asked for, echoed so the result carries it."""
    if section == "results_discussion":
        results = str(spec.get("results_text") or "")
        discussion = str(spec.get("discussion_text") or "")
        return {"kind": "results_and_discussion",
                "results_text": results,
                "discussion_text": discussion,
                "results_words": len(results.split()),
                "discussion_words": len(discussion.split())}
    return {"kind": "structured_section", "section": section}


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

    if not sec:
        return _refused(out_dir, "no section declared, so no rules apply", spec)
    if not isinstance(sec, str) or sec not in S.SECTIONS:
        return _refused(out_dir, f"unknown section '{sec}', so no rules apply", spec,
                        "audit.section_unknown")

    try:
        findings, status, counts = S.run(spec, sec)
    except Exception as exc:
        return _refused(out_dir,
                        f"the audit could not complete: {type(exc).__name__}: {exc}",
                        spec, "audit.section_error")

    checked = {"section": sec, "items": _count(spec, sec)}
    if sec == "results_discussion":
        results = str(spec.get("results_text") or "")
        discussion = str(spec.get("discussion_text") or "")
        checked.update({
            "figures": len([f for f in (spec.get("figures") or []) if isinstance(f, dict)])
                       if isinstance(spec.get("figures"), (list, tuple)) else 0,
            "comparisons": len([c for c in (spec.get("comparisons") or []) if isinstance(c, dict)])
                           if isinstance(spec.get("comparisons"), (list, tuple)) else 0,
            "literature": len([l for l in (spec.get("literature") or []) if isinstance(l, dict)])
                          if isinstance(spec.get("literature"), (list, tuple)) else 0,
            "limitations": len([l for l in (spec.get("limitations") or []) if isinstance(l, dict)])
                           if isinstance(spec.get("limitations"), (list, tuple)) else 0,
            "results_words": len(results.split()),
            "discussion_words": len(discussion.split()),
            "numeric_ledger": S.numeric_ledger(spec),
        })
    if sec == "compare_docs":
        # completeness summary for the comparison matrix: which declared field each
        # supplied document reports, so unreported cells are named, not silent
        checked["coverage"] = S.compare_coverage(spec)
    result = {"schema_version": "secrun/v1", "section": sec, "status": status,
              "findings": findings, "severity_counts": counts, "limits": [],
              "checked": checked,
              "deliverable": _deliverable(spec, sec),
              "evidence_map": S.evidence_map(spec, sec),
              "boundary": {"human_review_and_gaps": S.open_questions(spec, sec),
                           "declared_limits": spec.get("limits")
                           if isinstance(spec.get("limits"), list) else []}}
    _echo_contract(result, spec)
    return _write_result(out_dir, result)


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
                      "case_id": r.get("case_id"),
                      "findings": [f["rule"] for f in r["findings"]],
                      "wrote": str(Path(a.out) / "result.json")}, ensure_ascii=False))
    return {"clean": 0, "review": 3, "blocked": 4, "undetermined": 5}.get(r["status"], 1)


if __name__ == "__main__":
    raise SystemExit(main())
