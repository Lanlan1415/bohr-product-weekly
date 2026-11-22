"""Run one structured section against a case spec and write result.json.

The result keeps the delivery contract the case declares: every field listed in
the spec's output_contract is echoed into result.json (values the case itself
carries pass through untouched, audit-derived keys are filled by the audit, the
rest become null with a limits note), and the case identifier is recorded from
the spec or the command line whenever either carries one. A refused run keeps
the same contract, so even an unrunnable case returns a comparable result file
rather than a crash.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import sections as S  # noqa: E402


def _contract_echo(spec: dict, derived: dict, limits: list) -> dict:
    """Carry every declared output_contract field into the result.

    A value the case itself carries passes through untouched. Keys the audit
    derives (status, section, findings, severity counts, the checked summary and
    the limits list) are filled from the audit — a passthrough value must never
    override the audited status, because the audited one is the honest one.
    Anything else becomes null with a limits note, never a fabricated value.
    """
    contract = spec.get("output_contract")
    if contract is None:
        return {}
    if not isinstance(contract, dict):
        limits.append("output_contract is not an object, so its fields cannot be echoed")
        return {}
    echo: dict = {}
    for key in contract:
        k = str(key)
        if k in derived:
            echo[k] = derived[k]
        elif k in spec:
            echo[k] = spec[k]
        else:
            echo[k] = None
            limits.append(f"output_contract field '{k}' is not derivable by this audit")
    return echo


def _refused(out_dir, message: str, spec: dict | None = None,
             case_id: str | None = None) -> dict:
    """The undetermined refusal every unrunnable case gets: an exit code, not a crash.

    Self-contained on purpose: it runs before any audit exists, so it must not
    call the contract echo helper (the helper is defined for the audited path and
    takes a derived map a refusal never has). The echo is inlined here instead —
    the case identifier and the declared output_contract fields are still written
    when the spec carries them, with null for anything the refused run could not
    derive, so a refusal stays comparable with a real run.
    """
    limits: list = ["the case could not be run as declared"]
    result = {"schema_version": "secrun/v1", "status": "undetermined",
              "findings": [{"rule": "audit.no_section", "severity": "high",
                            "message": message}],
              "limits": limits}
    if isinstance(spec, dict):
        cid = case_id or spec.get("case_id")
        if cid is not None:
            result["case_id"] = str(cid)
        contract = spec.get("output_contract")
        if isinstance(contract, dict):
            echo: dict = {}
            for key in contract:
                k = str(key)
                if k in ("status", "findings", "severity_counts", "section", "checked"):
                    echo[k] = result.get(k)
                elif k in spec:
                    echo[k] = spec[k]
                else:
                    echo[k] = None
                    limits.append(f"output_contract field '{k}' is not derivable "
                                  "by this audit")
            if echo:
                result["output_contract"] = echo
    elif case_id is not None:
        result["case_id"] = str(case_id)
    out_dir = Path(out_dir); out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2),
                                         encoding="utf-8")
    return result


def build_and_audit(spec_path, out_dir, section=None, case_id=None) -> dict:
    try:
        spec = json.loads(Path(spec_path).read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        # An unreadable spec is a refusal with the usual exit code, not a traceback.
        return _refused(out_dir, f"the spec file is not readable JSON: {exc}", None, case_id)
    except OSError:
        return _refused(out_dir, "the spec file could not be read", None, case_id)
    if not isinstance(spec, dict):
        return _refused(out_dir, "the spec file is not a JSON object", None, case_id)
    sec = section or spec.get("section")
    out_dir = Path(out_dir); out_dir.mkdir(parents=True, exist_ok=True)

    if not isinstance(sec, str) or not sec.strip():
        return _refused(out_dir, "no section declared, so no rules apply", spec, case_id)
    sec = sec.strip()
    if sec not in S.SECTIONS:
        return _refused(out_dir, f"unknown section '{sec}', so no rules apply", spec, case_id)

    findings, status, counts = S.run(spec, sec)
    limits: list = []
    checked = {"section": sec, "items": _count(spec, sec)}
    if sec == "compare_docs":
        # completeness summary for the comparison matrix: which declared field each
        # supplied document reports, so unreported cells are named, not silent
        checked["coverage"] = S.compare_coverage(spec)
    derived = {"status": status, "section": sec, "findings": findings,
               "severity_counts": counts, "checked": checked, "limits": limits}
    echo = _contract_echo(spec, derived, limits)
    result = {"schema_version": "secrun/v1", "section": sec, "status": status,
              "findings": findings, "severity_counts": counts, "limits": limits,
              "checked": checked}
    cid = case_id or spec.get("case_id")
    if cid is not None:
        result["case_id"] = str(cid)
    if echo:
        result["output_contract"] = echo
    (out_dir / "result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2),
                                         encoding="utf-8")
    return result


def _count(spec: dict, section: str) -> int:
    for key in ("conclusions", "claims", "documents", "formulas", "answers", "paragraphs",
                "statements", "aims", "objectives", "risks", "outcomes", "route",
                "schedule", "chapters", "nodes"):
        v = spec.get(key)
        if isinstance(v, (list, tuple, dict)):
            return len(v)
    if isinstance(spec.get("text"), str):
        return len(spec["text"].split())
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
    ap.add_argument("--case-id", help="case identifier to record in result.json")
    a = ap.parse_args(argv)
    r = build_and_audit(Path(a.spec), Path(a.out), a.section, a.case_id)
    print(json.dumps({"status": r["status"], "section": r.get("section"),
                      "case_id": r.get("case_id"),
                      "findings": [f["rule"] for f in r["findings"]],
                      "wrote": str(Path(a.out) / "result.json")}, ensure_ascii=False))
    return {"clean": 0, "review": 3, "blocked": 4, "undetermined": 5}.get(r["status"], 1)


if __name__ == "__main__":
    raise SystemExit(main())
