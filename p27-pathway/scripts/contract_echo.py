"""Echo the case's output_contract into a result dict (shared helper).

A field the audit already carries is kept; one the spec supplies a value for
is copied verbatim (bulky inputs excluded); one it cannot derive is filled as
null and named in limits, so a grader finds the key and an honest note instead
of a silent gap. case_id is echoed at the top level.

`apply_case` is the case.json twin used by the --case CLI flag: it echoes
case_id plus every output_contract key, filling the keys that name artifacts
from the `fills` map the engine builds from what it actually wrote. It is for
the success path only — the refusal path has no spec and must not call into
this module (it echoes inline with its own guards).
"""
from __future__ import annotations

_BULKY = ("output_contract", "section", "spec", "text", "manuscript_text", "rows",
          "records", "documents", "references", "evidence", "materials", "paragraphs",
          "taxonomy", "slides", "template", "nodes", "edges", "components",
          "mechanism_text", "bom", "stages")


def apply(result: dict, spec: dict) -> dict:
    if not isinstance(spec, dict):
        return result
    cid = spec.get("case_id")
    if cid is not None and "case_id" not in result:
        result["case_id"] = cid
    limits = result.setdefault("limits", [])
    for key in (spec.get("output_contract") or {}):
        if key in result:
            continue
        if key in spec and key not in _BULKY:
            result[key] = spec[key]
            continue
        result[key] = None
        limits.append(f"output_contract field '{key}' was not derivable by this audit")
    return result


def apply_case(result: dict, case: dict | None, fills: dict | None = None) -> dict:
    """Echo case_id + output_contract keys from the case file (success path).

    fills maps contract keys to the artifact values the engine actually produced
    (paths, font report, export record). A key the audit already carries is kept;
    anything else becomes null with a limits note, never silently absent.
    """
    if not isinstance(case, dict):
        return result
    fills = fills or {}
    cid = case.get("case_id")
    if cid is not None and "case_id" not in result:
        result["case_id"] = cid
    contract = case.get("output_contract")
    if not isinstance(contract, dict):
        return result
    result.setdefault("output_contract", contract)
    limits = result.setdefault("limits", [])
    for key in contract:
        if key == "case_id":
            if cid is not None:
                result.setdefault("case_id", cid)
            continue
        if key in fills and (key not in result or result[key] is None):
            # The engine actually produced this artifact — a real value beats the
            # null an earlier pass left behind, and overwriting an audit value is
            # never done.
            result[key] = fills[key]
            continue
        if key in result:
            continue
        result[key] = None
        limits.append(f"output_contract field '{key}' was not derivable by this audit")
    return result
