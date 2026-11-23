"""Echo the case's delivery contract into a result dict.

A case declares, in its output_contract, the fields its result must carry. This
helper carries each declared field into the result:

  a field the audit already produced is kept (the audited value wins);
  a field the spec itself carries a value for is copied verbatim (bulky inputs
  excluded -- a contract field is an assertion about the deliverable, not a
  place to dump the whole material list);
  a field neither can fill becomes null with a note in limits, so a reviewer
  finds the key and an honest gap instead of a silent omission. Dict, field-list
  and {"fields": ...} contracts are supported, including structured refusals.
"""
from __future__ import annotations

# Spec keys that carry bulk material. Copying them into the result would make
# every result.json a second copy of the input, so a contract field with one of
# these names is filled as null and named in limits instead.
_BULKY = ("output_contract", "section", "spec", "text", "manuscript_text", "rows",
          "records", "documents", "references", "evidence", "materials", "paragraphs",
          "taxonomy", "slides", "template", "nodes", "edges", "components",
          "mechanism_text", "bom", "stages", "source_values")


def apply(result: dict, spec: dict) -> dict:
    """Merge the declared contract fields into `result`, in place. Returns result."""
    if not isinstance(spec, dict):
        return result
    cid = spec.get("case_id")
    if cid is not None and "case_id" not in result:
        result["case_id"] = str(cid)
    contract = spec.get("output_contract")
    if isinstance(contract, dict) and isinstance(contract.get("fields"), (list, tuple, dict, str)):
        contract = contract["fields"]
    if isinstance(contract, dict):
        keys = list(contract)
    elif isinstance(contract, str):
        keys = [contract]
    elif isinstance(contract, (list, tuple)):
        keys = []
        for item in contract:
            if isinstance(item, str) and item.strip():
                keys.append(item)
            elif isinstance(item, dict):
                key = item.get("name") or item.get("field") or item.get("key")
                if isinstance(key, str) and key.strip():
                    keys.append(key)
                else:
                    result.setdefault("limits", []).append(f"output_contract entry has no usable name: {item!r}")
            else:
                result.setdefault("limits", []).append(f"output_contract entry is not a field: {item!r}")
    else:
        if contract is not None:
            result.setdefault("limits", []).append("output_contract is not a supported field list")
        return result
    limits = result.setdefault("limits", [])
    for key in keys:
        k = str(key)
        if k in result:
            continue
        if k in spec and k not in _BULKY:
            result[k] = spec[k]
            continue
        result[k] = None
        limits.append(f"output_contract field '{k}' was not derivable by this audit")
    return result
