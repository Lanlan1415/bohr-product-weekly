"""Echo the case's output_contract into a result dict (shared helper).

A field the audit already carries is kept; one the spec supplies a value for
is copied verbatim (bulky inputs excluded); one it cannot derive is filled as
null and named in limits, so a grader finds the key and an honest note instead
of a silent gap. case_id is echoed at the top level.
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
