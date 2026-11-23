#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""validate_result.py -- validate result.json against the skill contract and the case output_contract.

Checks:
  - envelope present: case_id, status, status_reason, sources, uncertainty, change_records
  - status is one of success / partial / undetermined / refused
  - sources / uncertainty / change_records are lists
  - partial, undetermined, refused carry uncertainty or limits (a partial result
    must identify its limits)
  - every required field of resources/output_contract.json exists
  - every field named by the case output_contract exists (contract mirror)
  - every contract "lists" field is a list

Usage:
  python3 validate_result.py /app/output/result.json \
    --contract $SKILL/resources/output_contract.json \
    --case /input/case.json
exit 0 = ok (the delivery license); 1 = contract violations listed.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ENVELOPE = ("case_id", "status", "status_reason", "sources", "uncertainty",
            "change_records")
STATUSES = {"success", "partial", "undetermined", "refused"}
LIST_FIELDS = {"parameter_table", "datasets", "steps", "limitations",
               "sources", "uncertainty", "change_records", "coverage", "gap_analysis",
               "evidence_map", "conflicts", "findings"}


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def unwrap(payload: dict) -> dict:
    if "case_id" not in payload and isinstance(payload.get("result"), dict):
        return payload["result"]
    return payload


def contract_field_names(case, defaults):
    fields = list(defaults)
    raw = case.get("output_contract") if isinstance(case, dict) else None
    names = []
    if isinstance(raw, dict):
        wrappers = {"fields", "required", "lists", "optional"}
        if raw and set(raw).issubset(wrappers):
            for value in raw.values():
                nested = contract_field_names({"output_contract": value}, [])
                names.extend(x for x in nested if x not in names)
        else:
            names = [str(k) for k in raw]
    elif isinstance(raw, list):
        for item in raw:
            if isinstance(item, str):
                names.append(item)
            elif isinstance(item, dict):
                name = str(item.get("name") or item.get("field") or item.get("key") or "")
                if name:
                    names.append(name)
    for item in names:
        if item not in fields and item not in ENVELOPE:
            fields.append(item)
    return fields


def validate(payload: dict, required) -> list:
    errors = []
    for key in list(ENVELOPE) + list(required):
        if key not in payload:
            errors.append("missing field: %s" % key)
    status = payload.get("status")
    if status not in STATUSES:
        errors.append("status must be success, partial, undetermined, or refused")
    for key in ("sources", "uncertainty", "change_records"):
        if key in payload and not isinstance(payload[key], list):
            errors.append("%s must be a list" % key)
    if status in {"partial", "undetermined", "refused"}:
        if not payload.get("uncertainty") and not payload.get("limits"):
            errors.append("%s needs uncertainty or limits" % status)
    if "case_id" in payload and not payload.get("case_id"):
        errors.append("case_id must be non-empty")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate a skill result.json")
    parser.add_argument("result")
    parser.add_argument("--contract", required=True)
    parser.add_argument("--case", default="")
    args = parser.parse_args()
    try:
        payload = unwrap(load_json(Path(args.result)))
    except (OSError, json.JSONDecodeError) as e:
        print("result unreadable: %s" % e)
        return 1
    try:
        contract = load_json(Path(args.contract))
    except (OSError, json.JSONDecodeError) as e:
        print("contract unreadable: %s" % e)
        return 1
    case = None
    if args.case:
        try:
            case = load_json(Path(args.case))
        except (OSError, json.JSONDecodeError) as e:
            print("case unreadable: %s" % e)
            return 1
    required = contract_field_names(case, list(contract.get("required", [])))
    errors = validate(payload, required)
    for name in contract_field_names(case, []):
        if payload.get(name) is None and not any(name in str(note) for note in payload.get("limits", [])):
            errors.append("null contract field needs a limits explanation: %s" % name)
    for key in contract.get("lists", []):
        if key in payload and not isinstance(payload[key], list):
            errors.append("%s must be a list" % key)
    for key in ("parameter_table", "datasets", "steps"):
        if key in payload and not isinstance(payload[key], list):
            errors.append("%s must be a list" % key)
    if errors:
        print("\n".join(errors))
        return 1
    print("ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
