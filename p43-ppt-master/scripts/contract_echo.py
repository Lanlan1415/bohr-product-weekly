"""Case identity and output-contract passthrough for results and safe refusals.

Successful audits derive fields from the delivered artifact. Refusals pass only
an independently parsed case, never the absent/malformed spec; their caller
also guards this module so a hostile contract cannot suppress result.json.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

BULKY = {
    "slides", "revisions", "goal", "template", "available_evidence", "spec",
    "output_contract", "materials", "documents", "records", "source_text",
}


def read_case(path: str | Path | None) -> tuple[dict[str, Any], str | None]:
    if not path:
        return {}, None
    try:
        value = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        return {}, f"case file could not be read as UTF-8 JSON: {exc}"
    if not isinstance(value, dict):
        return {}, "case file is not a JSON object; case identity/contract unavailable"
    return value, None


def contract_keys(contract: Any) -> tuple[list[str], str | None]:
    """Accept the case shapes used by Harbor without guessing at unknown ones."""
    if contract is None:
        return [], None
    if isinstance(contract, str):
        return [contract], None
    if isinstance(contract, dict):
        return [str(k) for k in contract], None
    if isinstance(contract, (list, tuple)):
        keys: list[str] = []
        for item in contract:
            if isinstance(item, str):
                keys.append(item)
            elif isinstance(item, dict):
                key = item.get("field", item.get("name", item.get("key")))
                if key is not None:
                    keys.append(str(key))
                else:
                    return keys, "an output_contract entry has no field/name/key"
            else:
                return keys, "an output_contract list entry is neither text nor an object"
        return list(dict.fromkeys(keys)), None
    return [], f"unsupported output_contract shape: {type(contract).__name__}"


def merged_spec(spec: dict, case: dict) -> dict:
    """Case values provide identity/contract; explicitly constructed spec values win."""
    out = dict(case)
    out.update({k: v for k, v in spec.items() if v is not None or k not in case})
    # The actual case file is authoritative for platform identity and field list.
    if case.get("case_id") is not None:
        out["case_id"] = case["case_id"]
    if "output_contract" in case:
        out["output_contract"] = case["output_contract"]
    if "case_id" not in spec and isinstance(spec.get("case"), dict):
        if spec["case"].get("case_id") is not None:
            out["case_id"] = spec["case"]["case_id"]
    if "output_contract" not in spec and isinstance(spec.get("case"), dict):
        if "output_contract" in spec["case"]:
            out["output_contract"] = spec["case"]["output_contract"]
    return out


def apply(result: dict, spec: dict, case: dict | None = None) -> dict:
    """Backfill every requested field; audited values always beat spec claims."""
    source = merged_spec(spec, case or {})
    if source.get("case_id") is not None:
        result["case_id"] = source["case_id"]
    else:
        result.setdefault("case_id", None)
    contract = source.get("output_contract")
    keys, problem = contract_keys(contract)
    limits = result.setdefault("limits", [])
    if problem:
        limits.append(problem)
    if contract is not None:
        result["output_contract"] = contract
    result["output_contract_fields"] = keys

    # Common names are derived from actual outputs, not copied from self-claims.
    derived = {
        "deck_file": (result.get("deck") or {}).get("path"),
        "editable_presentation": (result.get("deck") or {}).get("path"),
        "evidence_map": result.get("evidence_map"),
        "slide_evidence_map": result.get("evidence_map"),
        "render_record": result.get("preview"),
        "version_record": result.get("reproducibility"),
        "change_records": result.get("change_records"),
        "sources": result.get("sources"),
        "uncertainty": result.get("uncertainty"),
    }
    for key in keys:
        if key in result and key not in {"output_contract", "output_contract_fields"}:
            continue
        if key in derived and derived[key] is not None:
            result[key] = derived[key]
        elif key in source and key not in BULKY:
            result[key] = source[key]
        else:
            result[key] = None
            limits.append(f"output_contract field '{key}' was not derivable; null retained")
    return result
