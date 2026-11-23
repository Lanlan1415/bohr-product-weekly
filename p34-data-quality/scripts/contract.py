"""Case contract plumbing, including structured refusals.

Every readable case keeps case_id and every output_contract key, including when
execution is refused. Undetermined fields are null and named in limits; a refusal
never substitutes an empty artifact for a completed result.
"""
from __future__ import annotations

import json
from pathlib import Path

BULKY = {"rows", "columns", "key_columns", "value_columns", "missing_tokens",
         "table_path", "section", "output_contract", "encoding", "delimiter",
         "units", "rules", "workorder", "spec"}
DERIVED = {
    "change_ledger": "changes",
    "changes": "changes",
    "reversible_log": "reversible_log",
    "before_after": "before_after",
    "validation_results": "validation_results",
    "data_dictionary": "data_dictionary",
    "cleaned_table": "cleaned_table",
    "quality_report": "quality_report",
    "anomalies": "anomalies",
}
REFUSED_SCHEMA = "data-quality/v3"


def refused(out_dir, message: str, spec=None, rule: str = "clean.refused") -> dict:
    """Write a safe undetermined result and preserve every known contract key."""
    result = {
        "schema_version": REFUSED_SCHEMA,
        "status": "undetermined",
        "findings": [{"rule": rule, "severity": "high", "message": str(message)}],
        "severity_counts": {"high": 1},
        "limits": ["the case could not be run as declared"],
    }
    if isinstance(spec, dict):
        if spec.get("case_id") is not None:
            result["case_id"] = spec.get("case_id")
        echo_contract(spec, result, result["limits"])
    else:
        result["case_id"] = None
        result["limits"].append("case metadata was unavailable; case_id could not be recovered")
    try:
        out_dir = Path(out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "result.json").write_text(
            json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    except OSError:
        pass
    return result


def echo_contract(spec: dict, result: dict, limits: list) -> None:
    """Fill every declared key without dropping or inventing output values."""
    if not isinstance(spec, dict):
        return
    contract = spec.get("output_contract")
    if isinstance(contract, dict):
        keys = [str(k) for k in contract.keys()]
    elif isinstance(contract, (list, tuple)):
        keys = [k for k in contract if isinstance(k, str)]
        if len(keys) != len(contract):
            limits.append("non-string output_contract entries were not valid field names")
    elif contract is None:
        return
    else:
        limits.append("output_contract was neither an object nor a list of field names")
        result["output_contract_fields"] = []
        return
    for key in keys:
        if key in result:
            continue
        # A supplied value is authoritative and passes through unchanged, even on
        # a structured refusal (it is case input, not an invented result).
        if key in spec and key not in BULKY:
            result[key] = spec[key]
            continue
        source = DERIVED.get(key)
        if result.get("status") != "undetermined" and source in result:
            result[key] = result[source]
            continue
        result[key] = None
        limits.append(f"output_contract field '{key}' was not derivable in status "
                      f"{result.get('status', 'undetermined')}")
    result["output_contract_fields"] = keys


def load_spec(spec_path) -> tuple[dict | None, str | None]:
    """Read UTF-8/UTF-8-BOM JSON, returning an error instead of raising."""
    try:
        raw = Path(spec_path).read_text(encoding="utf-8-sig")
    except OSError as exc:
        return None, f"the spec file could not be read: {exc}"
    except UnicodeDecodeError as exc:
        return None, f"the spec file is not valid UTF-8 text: {exc}"
    try:
        spec = json.loads(raw)
    except json.JSONDecodeError as exc:
        return None, f"the spec file is not valid JSON: {exc}"
    return spec, None
