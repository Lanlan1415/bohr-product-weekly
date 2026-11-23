"""Harbor case loading and faithful output-field completion for trendrun.

This module is used only after a structured analysis exists.  The refusal writer
in trendrun.py intentionally has no dependency on it or on a parsed spec.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def load_case(path: str | Path | None) -> tuple[dict, str | None]:
    if path is None:
        return {}, None
    try:
        case = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        return {}, f"case.json unavailable or invalid: {exc}"
    if not isinstance(case, dict):
        return {}, "case.json is not an object; identity and contract are undetermined"
    return case, None


def field_names(contract: Any) -> tuple[list[str], list[str]]:
    warnings: list[str] = []
    if contract is None:
        return [], warnings
    if isinstance(contract, dict):
        return [str(k) for k in contract], warnings
    if isinstance(contract, str):
        return [contract], warnings
    if isinstance(contract, list):
        names = []
        for pos, entry in enumerate(contract):
            if isinstance(entry, str):
                names.append(entry)
            elif isinstance(entry, dict):
                name = entry.get("field", entry.get("name", entry.get("key")))
                if name is None:
                    warnings.append(f"output_contract entry {pos} has no field/name/key")
                else:
                    names.append(str(name))
            else:
                warnings.append(f"output_contract entry {pos} has unsupported type {type(entry).__name__}")
        return list(dict.fromkeys(names)), warnings
    warnings.append(f"output_contract has unsupported type {type(contract).__name__}")
    return [], warnings


def combine(case: dict, spec: dict) -> dict:
    values = dict(case)
    values.update({k: v for k, v in spec.items() if v is not None or k not in case})
    # Original case metadata is authoritative; a hand-written spec cannot rebrand it.
    if case.get("case_id") is not None:
        values["case_id"] = case["case_id"]
    if "output_contract" in case:
        values["output_contract"] = case["output_contract"]
    nested = spec.get("case")
    if isinstance(nested, dict):
        if not values.get("case_id") and nested.get("case_id") is not None:
            values["case_id"] = nested["case_id"]
        if not values.get("output_contract") and nested.get("output_contract") is not None:
            values["output_contract"] = nested["output_contract"]
    return values


def complete(result: dict, spec: dict, case: dict) -> None:
    values = combine(case, spec)
    result["case_id"] = values.get("case_id")
    contract = values.get("output_contract")
    names, warnings = field_names(contract)
    limits = result.setdefault("limits", [])
    limits.extend(warnings)
    if contract is not None:
        result["output_contract"] = contract
    result["output_contract_fields"] = names

    paths = {
        "research_product": result.get("research_product"),
        "review_result": result.get("research_product"),
        "trend_analysis": result.get("time_trend"),
        "time_trend": result.get("time_trend"),
        "topic_evolution": result.get("topic_evolution"),
        "representative_works": result.get("representative_works"),
        "research_gaps": result.get("research_gaps"),
        "evidence_matrix": result.get("evidence_matrix"),
        "evidence_matrix_file": result.get("evidence_matrix_file"),
        "screening_results": result.get("screening"),
        "sources": result.get("sources"),
        "uncertainty": result.get("uncertainty"),
        "limitations": result.get("uncertainty"),
        "change_records": result.get("change_records"),
    }
    bulky = {"records", "documents", "materials", "source_text", "output_contract",
             "topic_aliases", "gap_candidates", "evolution_events"}
    for name in names:
        if name in result and name not in {"output_contract", "output_contract_fields"}:
            continue
        value = paths.get(name)
        if value is not None:
            result[name] = value
        elif name in values and name not in bulky:
            result[name] = values[name]
        else:
            result[name] = None
            limits.append(f"output_contract field '{name}' remains null: not derivable from this run")
