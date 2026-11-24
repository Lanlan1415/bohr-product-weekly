"""Run one structured section against a case spec and write result.json.

The result keeps the delivery contract: every field the case declares in its
output_contract is echoed into result.json (case-carried values pass through,
audit-derived values are filled by the audit, the rest are null with a limits
note), and the case identifier is recorded whenever the spec or the command
line carries one.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import sections as S  # noqa: E402


def _mirror_unknown(template, path: str, limits: list):
    if isinstance(template, dict):
        return {str(k): _mirror_unknown(v, f"{path}.{k}" if path else str(k), limits)
                for k, v in template.items()}
    if isinstance(template, list):
        if path:
            limits.append(f"output_contract array '{path}' has no generated items")
        return []
    if path:
        limits.append(f"output_contract field '{path}' is not derivable by this audit")
    return None


def _contract_echo(spec: dict, derived: dict, limits: list) -> dict:
    """Carry every declared output_contract field into the result.

    Values the case itself carries pass through untouched; keys the audit derives
    (status, section, findings, severity counts, the checked summary and the limits)
    are filled from the audit -- a passthrough value must never override the audited
    status, because the audited one is the honest one; anything else becomes null
    with a limits note, never a fabricated value.
    """
    contract = spec.get("output_contract")
    transfer_profile = spec.get("transfer_profile")
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
        elif isinstance(transfer_profile, dict) and k in transfer_profile:
            echo[k] = transfer_profile[k]
        else:
            echo[k] = _mirror_unknown(contract[key], k, limits)
    return echo


def _refused(out_dir, message: str, case_id=None, echo=None, limits=None) -> dict:
    """The undetermined refusal every unrunnable case gets: an exit code, not a crash.

    Self-contained on purpose: it runs before the audit exists, so it never calls
    _contract_echo itself (at the call sites where the spec never parsed there is
    no spec object to echo from). Where a spec did parse, the caller builds the
    echo and the case identifier and hands both in as plain values.
    """
    limits = list(limits or ["the case could not be run as declared"])
    result = {"schema_version": "secrun/v1", "case_id": str(case_id) if case_id is not None else None,
              "status": "undetermined",
              "findings": [{"rule": "audit.no_section", "severity": "high",
                            "message": message}],
              "limits": limits}
    if case_id is not None:
        result["case_id"] = str(case_id)
    if echo:
        result["output_contract"] = echo
        for key, value in echo.items():
            if key not in result:
                result[key] = value
    out_dir = Path(out_dir); out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2),
                                         encoding="utf-8")
    return result


def build_and_audit(spec_path, out_dir, section=None, case_id=None) -> dict:
    if isinstance(spec_path, dict):
        spec = spec_path
    else:
        try:
            spec = json.loads(Path(spec_path).read_text(encoding="utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError, OSError) as exc:
            # An unreadable spec is a refusal with the usual exit code, not a traceback.
            return _refused(out_dir, f"the spec file is not readable JSON: {exc}", case_id)
    if not isinstance(spec, dict):
        return _refused(out_dir, "the spec file is not a JSON object", case_id)

    cid = case_id or spec.get("case_id")
    sec = section or spec.get("section")
    out_dir = Path(out_dir); out_dir.mkdir(parents=True, exist_ok=True)

    # Refusal paths build their own echo and limits here, where the spec exists,
    # and hand them to _refused as plain values; _refused itself never calls the
    # echo, because at the earlier call sites there is no spec to echo from.
    if not isinstance(sec, str) or not sec.strip():
        rlimits = ["the case could not be run as declared"]
        return _refused(out_dir, "no section declared, so no rules apply", cid,
                        _contract_echo(spec, {}, rlimits), rlimits)
    sec = sec.strip()
    if sec not in S.SECTIONS:
        rlimits = ["the case could not be run as declared"]
        return _refused(out_dir, f"unknown section '{sec}', so no rules apply", cid,
                        _contract_echo(spec, {}, rlimits), rlimits)

    findings, status, counts = S.run(spec, sec)
    limits: list = []
    checked = {"section": sec, "items": _count(spec, sec)}
    if sec == "compare_docs":
        # completeness summary for the comparison matrix: which declared field each
        # supplied document reports, so unreported cells are named, not silent
        checked["coverage"] = S.compare_coverage(spec)
    derived = {"status": status, "section": sec, "findings": findings,
               "severity_counts": counts, "checked": checked, "limits": limits}
    if sec == "dissemination":
        import commercial_transfer as CT
        derived["deliverable"] = {
            "kind": "research_commercialization" if CT.enabled(spec) else "research_rewrite",
            "audience": spec.get("audience"), "text": str(spec.get("text") or ""),
            "changes": spec.get("changes") or [], "limitations": spec.get("limitations"),
            "transfer_profile_present": CT.enabled(spec),
        }
        derived["evidence_map"] = [
            {"kind": "declared_source", "value": str(x)} for x in
            (spec.get("evidence") if isinstance(spec.get("evidence"), list) else [])
        ] + [{"kind": "change", "value": x} for x in
             (spec.get("changes") if isinstance(spec.get("changes"), list) else [])]
        derived["boundary"] = {
            "open_questions": spec.get("open_questions") if "open_questions" in spec else None,
            "business_and_commercialization_review": CT.open_questions(spec),
        }
        derived["transfer_assessment"] = CT.summary(spec)
        derived["target_text"] = derived["deliverable"]["text"]
        derived["rewrite"] = spec.get("rewrite") or derived["deliverable"]
    echo = _contract_echo(spec, derived, limits)
    result = {"schema_version": "secrun/v1", "section": sec, "status": status,
              "findings": findings, "severity_counts": counts, "limits": limits,
              "checked": checked}
    for key in ("deliverable", "evidence_map", "boundary", "transfer_assessment"):
        if key in derived and derived[key] is not None:
            result[key] = derived[key]
    if cid is not None:
        result["case_id"] = str(cid)
    if echo:
        result["output_contract"] = echo
        for key, value in echo.items():
            if key not in result:
                result[key] = value
    (out_dir / "result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2),
                                         encoding="utf-8")
    return result


def build_case(case_path, out_dir, section=None, case_id=None) -> dict:
    """Run actual case.json directly, including nested-spec delivery contracts."""
    try:
        case = json.loads(Path(case_path).read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError, OSError) as exc:
        return _refused(out_dir, f"the case file is not readable JSON: {exc}", case_id)
    if not isinstance(case, dict):
        return _refused(out_dir, "the case file is not a JSON object", case_id)
    if "spec" in case and not isinstance(case.get("spec"), dict):
        return _refused(out_dir, "case.spec is not an object", case_id or case.get("case_id"),
                        _contract_echo(case, {}, ["the case could not be run as declared"]))
    spec = dict(case["spec"]) if isinstance(case.get("spec"), dict) else dict(case)
    for key in ("case_id", "output_contract", "transfer_profile"):
        if key in case:
            spec[key] = case[key]
    if "case_id" not in spec:
        spec["case_id"] = case.get("id") or case.get("caseId")
    spec.setdefault("section", section or "dissemination")
    return build_and_audit(spec, out_dir, section, case_id)


def _count(spec: dict, section: str) -> int:
    for key in ("conclusions", "claims", "documents", "formulas", "answers", "paragraphs",
                "statements", "aims", "chapters", "nodes"):
        v = spec.get(key)
        if isinstance(v, (list, tuple, dict)):
            return len(v)
    if isinstance(spec.get("text"), str):
        return len(str(spec.get("text") or "").split())
    if isinstance(spec.get("checklist"), dict):
        return len(spec.get("checklist") or {})
    return 0


def main(argv=None) -> int:
    import argparse
    ap = argparse.ArgumentParser(prog="secrun", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    source = ap.add_mutually_exclusive_group(required=True)
    source.add_argument("--spec", help="assembled section spec (legacy/explicit interface)")
    source.add_argument("--case", help="actual case.json (flat or with nested spec)")
    ap.add_argument("--out", required=True)
    ap.add_argument("--section", help="override the spec's declared section")
    ap.add_argument("--case-id", help="case identifier to record in result.json")
    a = ap.parse_args(argv)
    if a.case:
        r = build_case(Path(a.case), Path(a.out), a.section, a.case_id)
    else:
        r = build_and_audit(Path(a.spec), Path(a.out), a.section, a.case_id)
    print(json.dumps({"status": r["status"], "section": r.get("section"),
                      "case_id": r.get("case_id"),
                      "findings": [f["rule"] for f in r["findings"]],
                      "wrote": str(Path(a.out) / "result.json")}, ensure_ascii=False))
    return {"clean": 0, "review": 3, "blocked": 4, "undetermined": 5}.get(r["status"], 1)


if __name__ == "__main__":
    raise SystemExit(main())
