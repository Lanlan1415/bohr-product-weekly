"""Shared case/output-contract handling for the source-bound figure CLIs.

The public examples use two contract shapes:
  * a flat mapping of requested field -> description;
  * a JSON-schema-like object with fields[], required[] or properties{}.
Both are resolved without inventing values.  Original declarations are retained,
resolved values are available in contract_field_values, and requested fields are
also surfaced at result top level where doing so cannot displace useful output.
"""
from __future__ import annotations

from copy import deepcopy
from typing import Any

_SCHEMA_KEYS = {"fields", "required", "properties", "type", "additionalProperties",
                "$schema", "$id", "title", "description", "definitions", "$defs"}


def embedded_spec(case: dict | None) -> dict | None:
    """Return an explicitly embedded drawing spec, never an inferred/free-text one."""
    if not isinstance(case, dict):
        return None
    if isinstance(case.get("nodes"), list):
        return case
    for key in ("spec", "diagram", "drawing_spec", "figure_spec"):
        value = case.get(key)
        if isinstance(value, dict) and isinstance(value.get("nodes"), list):
            return value
    work = case.get("workorder")
    if isinstance(work, dict):
        for key in ("spec", "diagram", "drawing_spec", "figure_spec"):
            value = work.get(key)
            if isinstance(value, dict) and isinstance(value.get("nodes"), list):
                return value
    return None


def _contract_fields(contract: dict) -> tuple[list[str], bool]:
    """Return requested field names and whether this was a flat echo contract."""
    if not isinstance(contract, dict):
        return [], False
    fields: list[str] = []
    raw_fields = contract.get("fields")
    if isinstance(raw_fields, dict):
        fields.extend(str(k) for k in raw_fields)
    elif isinstance(raw_fields, (list, tuple)):
        fields.extend(str(x) for x in raw_fields if isinstance(x, (str, int, float)))
    properties = contract.get("properties")
    if isinstance(properties, dict):
        fields.extend(str(k) for k in properties)
    required = contract.get("required")
    if isinstance(required, (list, tuple)):
        fields.extend(str(x) for x in required if isinstance(x, str))
    flat = not (fields or any(k in contract for k in _SCHEMA_KEYS))
    if flat:
        fields.extend(str(k) for k in contract)
    if "case_id" in contract or "case_id" in fields:
        fields.append("case_id")
    return list(dict.fromkeys(fields)), flat


def apply_contract(result: dict, spec: dict | None, case: dict | None,
                   derived: dict[str, Any] | None = None) -> dict:
    """Resolve every requested field, preserving the original declaration.

    Derived runtime values win over placeholder descriptions.  Values explicitly
    supplied in the spec/case pass through otherwise.  Unknown fields become null
    and a limits entry; they are never silently omitted or hallucinated.
    """
    spec = spec if isinstance(spec, dict) else {}
    case = case if isinstance(case, dict) else {}
    derived = dict(derived or {})
    contract = case.get("output_contract")
    if not isinstance(contract, dict):
        contract = spec.get("output_contract")
    cid = case.get("case_id", spec.get("case_id", result.get("case_id")))
    if cid is not None:
        result["case_id"] = cid
        result = {"case_id": result.pop("case_id"), **result}
    if not isinstance(contract, dict):
        return result

    fields, flat = _contract_fields(contract)
    limits = result.setdefault("limits", [])
    if not isinstance(limits, list):
        limits = [str(limits)]
        result["limits"] = limits
    values: dict[str, Any] = {}
    merged_derived = dict(result)
    merged_derived.update(derived)
    for key in fields:
        if key == "case_id":
            value = cid
        elif key in merged_derived:
            value = merged_derived[key]
        elif key in spec:
            value = spec[key]
        elif key in case and key != "output_contract":
            value = case[key]
        else:
            value = None
            note = f"output_contract field '{key}' was not derivable; retained as null"
            if note not in limits:
                limits.append(note)
        values[key] = deepcopy(value)

    # A flat contract historically meant output_contract itself was the resolved
    # mapping.  Schema-shaped declarations stay verbatim; field_values covers both.
    result["output_contract"] = deepcopy(values if flat else contract)
    result["contract_field_values"] = deepcopy(values)
    for key, value in values.items():
        if key not in result:
            result[key] = deepcopy(value)
    return result
