"""Run verifiable, extractive knowledge-base question answering.

  python kbqa_cli.py --case /input/case.json --out /app/output
  python kbqa_cli.py --case /input/case.json --out /app/output --material-root /input
  python kbqa_cli.py --verify-only --out /app/output

Exit codes: 0 done, 3 partial, 5 undetermined/refusal.  Every refused run emits
JSON on stdout and, whenever the output directory is writable, result.json.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import kbqa  # noqa: E402


def _print(value):
    print(json.dumps(value, ensure_ascii=False, sort_keys=True))


def _refusal(out: Path, message: str, case=None, code="kbqa.case_unreadable") -> int:
    result = {"schema_version": kbqa.SCHEMA, "status": "undetermined",
              "case_id": (case or {}).get("case_id", (case or {}).get("id")),
              "status_reason": message, "answers": [], "evidence": [],
              "failures": [{"rule": code, "reason": message}],
              "limits": ["the run could not be completed as declared; no facts were generated"],
              "operation_trace": [{"seq": 1, "action": "refused", "rule": code}]}
    if isinstance(case, dict) and isinstance(case.get("output_contract"), dict):
        try:
            kbqa.complete_contract(result, case)
        except (TypeError, ValueError) as exc:
            result["limits"].append("contract passthrough failed safely: " + str(exc)[:200])
    try:
        out.mkdir(parents=True, exist_ok=True)
        (out / "result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2,
                                                sort_keys=True), encoding="utf-8")
        wrote = str(out / "result.json")
    except OSError as exc:
        wrote = None
        result["limits"].append("result.json could not be written: " + str(exc)[:300])
    _print({"ok": False, "status": "undetermined", "reason": message, "wrote": wrote})
    return 5


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="kbqa", description=__doc__)
    parser.add_argument("--case", help="original case.json")
    parser.add_argument("--out", required=True, help="output directory")
    parser.add_argument("--material-root", help="root for relative materials/directory discovery")
    parser.add_argument("--verify-only", action="store_true", help="re-check exported claim anchors")
    args = parser.parse_args(argv)
    out = Path(args.out)
    if args.verify_only:
        try:
            report = kbqa.verify_export(out)
        except Exception as exc:  # verification is a structured refusal, never a traceback
            return _refusal(out, "verification could not run: " + str(exc)[:400],
                            code="kbqa.verification_failed")
        _print(report)
        return 0 if report.get("ok") else 5
    if not args.case:
        return _refusal(out, "--case is required unless --verify-only is used",
                        code="kbqa.case_required")
    path = Path(args.case)
    case = None
    try:
        case = json.loads(path.read_text(encoding="utf-8-sig"))
        if not isinstance(case, dict):
            return _refusal(out, "case.json must contain a JSON object", code="kbqa.case_not_object")
        material_root = Path(args.material_root) if args.material_root else None
        result = kbqa.run_case(case, path.resolve().parent, out, material_root)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        return _refusal(out, "case file is not readable JSON: " + str(exc)[:400], case)
    except Exception as exc:  # boundary guarantee for hostile workorder shapes
        return _refusal(out, "knowledge-base pipeline refused an invalid input: " +
                        (type(exc).__name__ + ": " + str(exc))[:500], case,
                        code="kbqa.invalid_input")
    _print({"ok": result["status"] != "undetermined", "status": result["status"],
            "case_id": result.get("case_id"), "documents": len(result.get("documents", [])),
            "questions": len(result.get("answers", [])),
            "answered": result.get("coverage", {}).get("answered"),
            "insufficient_evidence": result.get("coverage", {}).get("insufficient_evidence"),
            "claims_verified": result.get("verification", {}).get("ok"),
            "wrote": str(out / "result.json")})
    return {"done": 0, "partial": 3}.get(result["status"], 5)


if __name__ == "__main__":
    raise SystemExit(main())
