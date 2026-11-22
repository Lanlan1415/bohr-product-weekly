"""Run one writing-track section against a case and write result.json.

The result carries the case's identity and its declared output contract: case_id
is echoed from the spec top level, and every key named in output_contract is
present in result.json — carried by the audit already, copied verbatim from the
spec (bulky inputs excluded), or filled as null with an honest limits note. A
run that cannot be executed at all is refused with exit 5 and still writes a
result.json — never a traceback.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import writing as W  # noqa: E402

# Spec keys whose values are bulky inputs rather than results: they are never
# copied verbatim into result.json (an echoed full manuscript would bury the
# audit verdict the grader reads first). Everything else the spec supplies
# under an output_contract key is passed through unchanged.
_BULKY = ("output_contract", "section", "text", "draft", "manuscript_text",
          "baseline_text", "source_text", "target_text", "comments", "responses",
          "claims", "evidence", "glossary", "segments", "template", "references",
          "anchors", "components", "conversions", "declarations")


def _refused(out_dir: Path, message: str, spec=None) -> dict:
    """The undetermined refusal every unrunnable case gets: an exit code, not a crash.

    `spec` is accepted only as an already-parsed plain dict so a refused run
    still names the case it could not run. This path deliberately does not run
    the contract echo (which walks nested spec structure): a refusal must never
    be able to raise, so it copies one scalar and nothing else.
    """
    result = {"schema_version": "writeaudit/v1", "status": "undetermined",
              "findings": [{"rule": "audit.no_section", "severity": "high",
                            "message": message}],
              "limits": ["the case could not be run as declared"]}
    if isinstance(spec, dict) and spec.get("case_id") is not None:
        result["case_id"] = spec.get("case_id")
    out_dir = Path(out_dir)
    try:
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "result.json").write_text(
            json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    except OSError:
        # an unwritable output directory is itself an undetermined run
        pass
    return result


def _echo_contract(spec: dict, result: dict, limits: list) -> None:
    """Echo the case's output_contract into result.json.

    A field the audit already carries is kept; one the spec supplies a value
    for is copied verbatim (bulky inputs excluded); one it cannot derive is
    filled as null and named in limits, so a grader finds the key and an
    honest note instead of a silent gap.
    """
    contract = spec.get("output_contract")
    if isinstance(contract, dict):
        keys = list(contract.keys())
    elif isinstance(contract, (list, tuple)):
        keys = [str(k) for k in contract]
    else:
        return
    for key in keys:
        if key in result:
            continue
        if key in spec and key not in _BULKY:
            result[key] = spec[key]
            continue
        result[key] = None
        limits.append(f"output_contract field '{key}' was not derivable by this audit")


def build_and_audit(spec_path: Path, out_dir: Path, section: str | None = None) -> dict:
    try:
        # utf-8-sig tolerates a BOM left by Windows editors; plain utf-8 files
        # read identically, so no honest input is refused over encoding trivia.
        spec = json.loads(Path(spec_path).read_text(encoding="utf-8-sig"))
    except (json.JSONDecodeError, UnicodeDecodeError, OSError) as exc:
        # An unreadable or missing spec is a refusal with the usual exit code,
        # never a traceback.
        return _refused(out_dir, f"the spec file is not readable JSON: {exc}")
    if not isinstance(spec, dict):
        return _refused(out_dir, "the spec file is not a JSON object")
    sec = section or spec.get("section")
    out_dir = Path(out_dir)

    if not isinstance(sec, str) or not sec.strip():
        return _refused(out_dir, "no section declared, so no rules apply", spec)
    if sec not in W.SECTIONS:
        return _refused(out_dir, f"unknown section '{sec}', so no rules apply", spec)

    try:
        findings, status, counts = W.run(spec, sec)
    except Exception as exc:  # a rule bug must never surface as a caller-side traceback
        return _refused(out_dir, f"the audit failed on this spec and was refused: {exc}",
                        spec)

    result = {
        "schema_version": "writeaudit/v1",
        "section": sec,
        "status": status,
        "findings": findings,
        "severity_counts": counts,
        "pending": W.pending_items(findings),
        "checked": _checked(spec, sec),
        "limits": [],
    }
    cid = spec.get("case_id")
    if cid is not None:
        result["case_id"] = cid

    _echo_contract(spec, result, result["limits"])

    try:
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "result.json").write_text(
            json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    except OSError as exc:
        result["status"] = "undetermined"
        result["limits"] = result["limits"] + [f"result.json could not be written: {exc}"]
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
                "responses": len(spec.get("responses") or []),
                "declarations_required": len(spec.get("required_declarations") or [])}
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
