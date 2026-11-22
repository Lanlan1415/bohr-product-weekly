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

# Fields that are bulky inputs rather than results: never copied wholesale into
# the result by the contract echo (the deliverable section carries the artifact).
_BULKY = {"output_contract", "section", "spec", "text", "manuscript_text", "results_text",
          "discussion_text", "figures", "comparisons", "literature", "limitations",
          "references", "evidence", "claims", "conclusions", "documents", "rows",
          "records", "materials", "paragraphs", "nodes", "edges", "answers", "chapters"}


def _refused(out_dir, message: str) -> dict:
    """The undetermined refusal every unrunnable case gets: an exit code, not a crash.

    Contract echo is deliberately NOT applied here: the spec never parsed, so
    there is no case_id or output_contract to echo.
    """
    result = {"schema_version": "secrun/v1", "status": "undetermined",
              "findings": [{"rule": "audit.no_section", "severity": "high",
                            "message": message}],
              "limits": ["the case could not be run as declared"]}
    out_dir = Path(out_dir); out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2),
                                         encoding="utf-8")
    return result


def _echo_contract(result: dict, spec: dict) -> dict:
    """Echo case_id and every output_contract field into the result."""
    if not isinstance(spec, dict):
        return result
    cid = spec.get("case_id")
    if cid is not None and "case_id" not in result:
        result["case_id"] = cid
    limits = result.setdefault("limits", [])
    contract = spec.get("output_contract")
    if contract is None:
        return result
    if not isinstance(contract, dict):
        limits.append("output_contract is not an object, so no field was echoed")
        return result
    for key in contract:
        if key in result:
            continue
        if key in spec and key not in _BULKY:
            result[key] = spec[key]
            continue
        result[key] = None
        limits.append(f"output_contract field '{key}' was not derivable by this audit")
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
                      "case_id": r.get("case_id"),
                      "findings": [f["rule"] for f in r["findings"]],
                      "wrote": str(Path(a.out) / "result.json")}, ensure_ascii=False))
    return {"clean": 0, "review": 3, "blocked": 4, "undetermined": 5}.get(r["status"], 1)


if __name__ == "__main__":
    raise SystemExit(main())
