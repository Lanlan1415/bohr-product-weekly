"""Authoritative Harbor case identity and output_contract completion for sysrevrun."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def load_case(path: str | Path | None) -> tuple[dict, str | None]:
    if path is None:
        return {}, None
    try:
        case = json.loads(Path(path).read_text(encoding="utf-8-sig"))
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
        return [str(key) for key in contract], warnings
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


def complete(result: dict, spec: dict, case: dict) -> None:
    values = dict(spec)
    values.update(case)  # original case metadata and values are authoritative
    if not case.get("case_id") and spec.get("case_id") is not None:
        values["case_id"] = spec["case_id"]
    result["case_id"] = values.get("case_id")
    contract = case.get("output_contract", spec.get("output_contract"))
    names, warnings = field_names(contract)
    result.setdefault("limits", []).extend(warnings)
    if contract is not None:
        result["output_contract"] = contract
    result["output_contract_fields"] = names
    paths = {
        "research_product": result.get("research_product"),
        "systematic_review": result.get("research_product"),
        "review_result": result.get("research_product"),
        "search_protocol": result.get("search_protocol"),
        "search_log": result.get("search_log"),
        "screening_log": result.get("screening_log"),
        "prisma_flow": result.get("prisma_flow"),
        "evidence_matrix": result.get("evidence_matrix"),
        "evidence_matrix_file": result.get("evidence_matrix_file"),
        "quality_appraisals": result.get("quality_appraisals"),
        "quality_summary": result.get("quality_summary"),
        "risk_of_bias": result.get("quality_appraisals"),
        "synthesis_claims": result.get("synthesis_claims"),
        "heterogeneity": result.get("heterogeneity"),
        "meta_analysis": result.get("meta_analysis"),
        "citation_coverage": result.get("citation_coverage"),
        "uncertainties": result.get("uncertainties"),
        "uncertainty": result.get("uncertainties"),
        "limitations": result.get("uncertainties"),
        "research_gaps": result.get("research_gaps"),
        "change_records": result.get("change_records"),
        "artifacts": result.get("artifacts"),
        "deliverables": result.get("deliverables"),
    }
    bulky = {"records", "materials", "source_excerpt", "output_contract", "synthesis_claims", "quality_appraisals"}
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
            result.setdefault("limits", []).append(
                f"output_contract field '{name}' remains null: not derivable from this run")
