"""Run one writing-track section against a case and write result.json.

The result carries, per the task's output requirements:

  case_id            the input identifier, echoed from the spec
  output_contract_*  every field the case's output_contract names (kept when the
                     audit already carries it, copied verbatim when the spec
                     supplies it, null + a limit note when it cannot be derived)
  deliverable        the editable artifact (目标产物)
  evidence_map       per-item source/verdict ledger (事实与来源映射)
  boundary           human-review items, gaps, uncertainties (版本与边界)
  status / findings  the audit verdict and its rule-level detail

Exit codes: 0 clean, 3 review, 4 blocked, 5 undetermined (refused, never a crash).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import writing as W  # noqa: E402

# Fields that are bulky inputs rather than results: never copied wholesale into
# the result by the contract echo (the deliverable section carries the artifact
# itself; everything else is summarised).
_BULKY = {"output_contract", "section", "spec", "text", "manuscript_text", "draft",
          "source_text", "target_text", "segments", "comments", "responses",
          "template", "references", "evidence", "glossary", "figures", "headings",
          "claims", "baseline_text", "anchors"}


def _refused(out_dir: Path, message: str) -> dict:
    """The undetermined refusal every unrunnable case gets: an exit code, not a crash.

    Contract echo is deliberately NOT applied here: the spec never parsed, so
    there is no case_id or output_contract to echo.
    """
    result = {"schema_version": "writeaudit/v1", "status": "undetermined",
              "findings": [{"rule": "audit.no_section", "severity": "high",
                            "message": message}],
              "limits": ["the case could not be run as declared"]}
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
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
    if section == "translation":
        mode = str(spec.get("output_mode") or "").strip().lower()
        segments = spec.get("segments") or []
        if segments:
            return {"kind": mode or "bilingual", "shape": "segments",
                    "segment_count": len(segments),
                    "target_text": W._segments_text(segments, "target")}
        return {"kind": mode or "plain", "shape": "document",
                "target_text": str(spec.get("target_text") or "")}
    if section == "evidence_writing":
        return {"kind": "manuscript",
                "text": str(spec.get("draft") or spec.get("text") or ""),
                "claim_count": len(spec.get("claims") or [])}
    if section == "review_response":
        return {"kind": "response_letter_and_manuscript",
                "manuscript_text": str(spec.get("manuscript_text") or ""),
                "response_count": len(spec.get("responses") or [])}
    if section == "format_template":
        return {"kind": "formatted_document", "text": str(spec.get("text") or "")}
    return {"kind": "unknown"}


def build_and_audit(spec_path: Path, out_dir: Path, section: str | None = None) -> dict:
    try:
        spec = json.loads(Path(spec_path).read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError, OSError) as exc:
        # An unreadable spec is a refusal with the usual exit code, not a traceback.
        return _refused(out_dir, f"the spec file is not readable JSON: {exc}")
    if not isinstance(spec, dict):
        return _refused(out_dir, "the spec file is not a JSON object")

    sec = section or spec.get("section")
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    if not sec:
        return _refused(out_dir, "no section was declared, so no rules apply")
    if sec not in W.SECTIONS:
        return _refused(out_dir, f"unknown section '{sec}', so no rules apply")

    findings, status, counts = W.run(spec, sec)

    result = {
        "schema_version": "writeaudit/v1",
        "section": sec,
        "status": status,
        "findings": findings,
        "severity_counts": counts,
        "checked": _checked(spec, sec),
        "limits": [],
        "deliverable": _deliverable(spec, sec),
        "evidence_map": W.evidence_map(spec, sec),
        "boundary": {
            "human_review_and_gaps": W.open_questions(spec, sec),
            "declared_limits": spec.get("limits") or [],
        },
    }
    _echo_contract(result, spec)
    (out_dir / "result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2),
                                         encoding="utf-8")
    return result


def _checked(spec: dict, section: str) -> dict:
    """What was actually looked at, so a reader knows the audit's scope."""
    if section == "evidence_writing":
        return {"evidence_items": len(spec.get("evidence") or []),
                "claims": len(spec.get("claims") or []),
                "sentences": len(W._sentences(spec.get("text") or
                                              spec.get("draft") or ""))}
    if section == "translation":
        segments = [s for s in (spec.get("segments") or []) if isinstance(s, dict)] \
            if isinstance(spec.get("segments"), list) else []
        src = str(spec.get("source_text") or "")
        if segments:
            src = W._segments_text(segments, "source")
        tgt = str(spec.get("target_text") or "")
        if segments:
            tgt = W._segments_text(segments, "target")
        return {"source_chars": len(src), "target_chars": len(tgt),
                "segments": len(segments),
                "glossary_terms": len(spec.get("glossary") or {})
                                     if isinstance(spec.get("glossary"), dict) else 0,
                "backcheck_records": len(spec.get("backcheck"))
                                     if isinstance(spec.get("backcheck"), list) else 0}
    if section == "review_response":
        return {"comments": len(spec.get("comments") or []),
                "responses": len(spec.get("responses") or []),
                "manuscript_chars": len(str(spec.get("manuscript_text") or ""))}
    if section == "format_template":
        import re
        return {"headings": sum(1 for l in (spec.get("text") or "").splitlines()
                                if re.match(r"^\s*\d+(\.\d+)*\s+\S", l)),
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
                      "case_id": r.get("case_id"),
                      "findings": [f["rule"] for f in r["findings"]],
                      "wrote": str(Path(a.out) / "result.json")}, ensure_ascii=False))
    return {"clean": 0, "review": 3, "blocked": 4, "undetermined": 5}.get(r["status"], 1)


if __name__ == "__main__":
    raise SystemExit(main())
