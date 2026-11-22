"""Case contract plumbing: refusal results and output_contract echo.

The Harbor runtime contract says every case returns a result.json that keeps
case_id and every field the case's output_contract names. Two helpers serve
that, deliberately tiny:

  refused       the undetermined result every unrunnable case gets — an exit
                code, not a traceback. It copies exactly one scalar (case_id)
                and never runs the contract echo, because the echo reads
                nested spec structure and a refusal must not be able to raise.
  echo_contract fills the named contract fields into a finished result: a
                field the result already carries is kept, one the spec supplies
                under the same name is copied verbatim (bulky inputs excluded),
                and one nobody can supply is written as null and named in
                limits, so a grader finds an honest gap instead of a missing key.
"""

from __future__ import annotations

import json
from pathlib import Path

# Spec keys whose values are bulky cleaning inputs rather than deliverable
# values: echoing a whole table into result.json would bury the verdict the
# grader reads first (the table itself is preserved verbatim in original.json).
BULKY = ("rows", "columns", "key_columns", "value_columns", "missing_tokens",
         "table_path", "section", "output_contract", "encoding", "delimiter",
         "units", "rules", "workorder")

REFUSED_SCHEMA = "datarun/v1"


def refused(out_dir, message: str, spec=None,
            rule: str = "clean.refused") -> dict:
    """Write and return the undetermined result for a case that cannot run.

    This path deliberately does not run the contract echo (which reads nested
    spec structure): a refusal must never be able to raise, so it only copies
    one scalar and writes with every failure swallowed — an unwritable output
    directory is itself the undetermined run.
    """
    result = {
        "schema_version": REFUSED_SCHEMA,
        "status": "undetermined",
        "findings": [{"rule": rule, "severity": "high", "message": message}],
        "severity_counts": {"high": 1},
        "limits": ["the case could not be run as declared"],
    }
    if isinstance(spec, dict) and spec.get("case_id") is not None:
        result["case_id"] = spec.get("case_id")
    try:
        out_dir = Path(out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "result.json").write_text(
            json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    except OSError:
        pass
    return result


def echo_contract(spec: dict, result: dict, limits: list) -> None:
    """Fill the case's output_contract fields into `result` in place."""
    contract = spec.get("output_contract")
    if isinstance(contract, dict):
        keys = list(contract.keys())
    elif isinstance(contract, (list, tuple)):
        keys = [str(k) for k in contract]
    else:
        return
    for key in keys:
        if key in result:
            continue
        if key in spec and key not in BULKY:
            result[key] = spec[key]
            continue
        result[key] = None
        limits.append(f"output_contract field '{key}' was not derivable by this audit")
    result["output_contract_fields"] = keys


def load_spec(spec_path) -> tuple[dict | None, str | None]:
    """Read a spec file, returning (spec, error). Any failure is a message, not a raise."""
    try:
        raw = Path(spec_path).read_text(encoding="utf-8")
    except OSError as exc:
        return None, f"the spec file could not be read: {exc}"
    except UnicodeDecodeError as exc:
        return None, f"the spec file is not valid UTF-8 text: {exc}"
    try:
        spec = json.loads(raw)
    except json.JSONDecodeError as exc:
        return None, f"the spec file is not valid JSON: {exc}"
    return spec, None
