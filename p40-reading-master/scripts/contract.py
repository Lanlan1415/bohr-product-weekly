"""Shared case/result contract plumbing for the four reading-route CLIs.

Only successful or graded runs call :func:`merge_result`. Refusal paths deliberately
never call it: an unrunnable case must not be dressed up as a contract-complete
answer with fabricated null fields.
"""

from __future__ import annotations

import json
from pathlib import Path


_ADMIN = {"output_contract", "case"}


def contract_fields(output_contract) -> list[str]:
    """Read list/name-map/string/list-of-object contracts without blind iteration."""
    if output_contract is None:
        return []
    if isinstance(output_contract, str):
        lines = [line.strip() for line in output_contract.splitlines() if line.strip()]
        if len(lines) == 1 and "," in lines[0]:
            lines = [part.strip() for part in lines[0].split(",")]
        return list(dict.fromkeys(lines))
    if isinstance(output_contract, dict):
        return [str(key) for key in output_contract]
    names: list[str] = []
    if isinstance(output_contract, list):
        for entry in output_contract:
            if isinstance(entry, str) and entry.strip():
                names.append(entry.strip())
            elif isinstance(entry, dict):
                for key in ("field", "name", "key", "id"):
                    if entry.get(key):
                        names.append(str(entry[key]))
                        break
    return list(dict.fromkeys(name for name in names if name))


def case_id(spec: dict):
    """Find case_id at the top level or in a nested case object."""
    if spec.get("case_id") is not None:
        return spec.get("case_id")
    nested = spec.get("case")
    if isinstance(nested, dict):
        if nested.get("case_id") is not None:
            return nested.get("case_id")
        if nested.get("id") is not None:
            return nested.get("id")
    return spec.get("id")


def merge_result(result: dict, spec: dict) -> dict:
    """Backfill case_id and every original output_contract field.

    Values already derived by the engine win. Otherwise a value supplied on the spec
    (or nested case object) is copied verbatim; an underivable field becomes null and
    is named in limits. No source text is invented and no field is silently renamed.
    """
    limits = result.get("limits")
    if not isinstance(limits, list):
        limits = [] if limits is None else [str(limits)]
        result["limits"] = limits

    cid = case_id(spec)
    if cid is not None:
        result["case_id"] = cid

    nested = spec.get("case") if isinstance(spec.get("case"), dict) else {}
    output_contract = spec.get("output_contract")
    if output_contract is None and nested:
        output_contract = nested.get("output_contract")
    if output_contract is not None and not isinstance(output_contract, (str, dict, list)):
        note = "output_contract shape was not recognised; expected list, object, or string"
        if note not in limits:
            limits.append(note)
        return result

    for key in contract_fields(output_contract):
        if key in result:
            continue
        if key in spec and key not in _ADMIN:
            result[key] = spec[key]
            continue
        if key in nested and key not in _ADMIN:
            result[key] = nested[key]
            continue
        result[key] = None
        note = f"output_contract field '{key}' was not derivable by this route"
        if note not in limits:
            limits.append(note)
    return result


def status_exit(status: str) -> int:
    """Uniform process verdict, including undetermined -> 5 on every route."""
    return {
        "clean": 0,
        "success": 0,
        "review": 3,
        "partial": 3,
        "blocked": 4,
        "undetermined": 5,
    }.get(status, 5)


def read_case(path) -> dict:
    """Read a case JSON object, raising a short ValueError for the CLI to refuse."""
    try:
        value = json.loads(Path(path).read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError, OSError) as exc:
        raise ValueError(f"the case file is not readable JSON: {exc}") from exc
    if not isinstance(value, dict):
        raise ValueError("the case file is not a JSON object")
    return value
