#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""assemble_result.py -- build the complete result.json from the case and the prose.

Code-over-inference: the agent only writes /app/work/prose.md; this script does
the rest so no field is hand-assembled and no number is hallucinated in:

  1. extract the parameter table from the case config (name, value, unit,
     source path, line) -- JSON scalars and `key: value` / `key=value` lines in
     .yaml/.yml/.txt/.log; nested JSON objects are skipped, not flattened;
  2. audit the prose numbers against that table (numeric_consistency.audit_prose);
  3. mirror every case output_contract field into the result (recursively,
     filling only missing keys, and recording what was mirrored);
  4. write result.json with the honest envelope: case_id, status, status_reason,
     sources, uncertainty, change_records, limits.

Status semantics:
  refused       the config path does not exist
  undetermined  no key-value parameters were found
  partial       prose missing/empty, or an unsupported number, or a setup
                field such as the dataset is absent (kept, not invented)
  success       every prose number is in the table and the dataset was present

Usage:
  python3 assemble_result.py --case /input/case.json --input-root /input \
    --prose /app/work/prose.md --work /app/work --output /app/output/result.json
Exit 0 whenever a result.json was written (an honest refused/partial result is
a valid deliverable); exit 2 only when arguments or the case are unreadable.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))

from numeric_consistency import audit_prose, known_value_strings

ENVELOPE = ("case_id", "status", "status_reason", "sources", "uncertainty",
            "change_records")
STATUSES = {"success", "partial", "undetermined", "refused"}
CANONICAL_FIELDS = ["parameter_table", "datasets", "steps", "prose",
                    "number_audit", "reproducibility", "limitations"]
LIST_FIELDS = {"parameter_table", "datasets", "steps", "limitations",
               "sources", "uncertainty", "change_records"}
DATA_KEYS = ("dataset", "data", "split", "train_split", "test_split",
             "dataset_name", "corpus", "benchmark")
LINE_RE = re.compile(r"^([\w\u4e00-\u9fff][\w.\-\u4e00-\u9fff]*)\s*[:=]\s*(.+?)\s*$")
NUM_UNIT_RE = re.compile(r"^([+-]?(?:\d+\.\d*|\.\d+|\d+))\s*([A-Za-z%°]{1,10})$")


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8")


def case_id_of(case: dict[str, Any]) -> str:
    for key in ("case_id", "id", "caseId"):
        if case.get(key):
            return str(case[key])
    return "unknown"


def base_result(case_id: str, status: str, reason: str) -> dict[str, Any]:
    return {
        "case_id": case_id,
        "status": status,
        "status_reason": reason,
        "sources": [],
        "uncertainty": [],
        "change_records": [],
        "limits": [],
    }


def empty_fields() -> dict[str, Any]:
    """Shape-consistent empties so every consumer sees the same keys."""
    return {
        "parameter_table": [],
        "datasets": [],
        "steps": [],
        "prose": "",
        "number_audit": {"unsupported": [], "known_values": [], "summary": {}},
        "reproducibility": {"config_files": [], "parameters_extracted": 0,
                            "command": "", "seed_present": False},
        "limitations": [],
    }


def locate(raw: str, roots: list[Path]) -> Path | None:
    path = Path(raw)
    if path.is_absolute() and path.exists():
        return path
    for root in roots:
        found = root / raw
        if found.exists():
            return found
    return None


def coerce(raw: str) -> tuple[Any, str]:
    """Parse a raw value string into (value, unit). Unknown shapes stay strings."""
    text = raw.strip().strip("'\"")
    if re.fullmatch(r"-?\d+", text):
        return int(text), ""
    if re.fullmatch(r"-?\d+\.\d+", text):
        return float(text), ""
    m = NUM_UNIT_RE.match(text)
    if m:
        return float(m.group(1)), m.group(2)
    return text, ""


def extract_rows(path: Path) -> list[dict[str, Any]]:
    """Parameter rows with file and line. Conservative by design."""
    rows: list[dict[str, Any]] = []
    if path.suffix == ".json":
        try:
            payload = json.loads(path.read_text(encoding="utf-8-sig"))
        except json.JSONDecodeError:
            payload = None
        if isinstance(payload, dict):
            for key, value in payload.items():
                if isinstance(value, (dict, list)):
                    continue  # nested shapes are not flattened into guesses
                unit = ""
                if isinstance(value, str):
                    value, unit = coerce(value)
                rows.append({"name": str(key), "value": value, "unit": unit,
                             "source": str(path), "line": None})
        return rows
    for index, line in enumerate(path.read_text(encoding="utf-8-sig",
                                                errors="replace").splitlines(), 1):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        match = LINE_RE.match(stripped)
        if not match:
            continue
        value, unit = coerce(match.group(2))
        rows.append({"name": match.group(1), "value": value, "unit": unit,
                     "source": str(path), "line": index})
    return rows


def dataset_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    datasets = []
    for row in rows:
        name = row["name"].lower()
        if name in DATA_KEYS or "dataset" in name:
            datasets.append({"name": row["value"], "source": row["source"],
                             "line": row["line"], "status": "from_config"})
    if not datasets:
        datasets.append({"name": None, "status": "not_in_source",
                         "reason": "no dataset key in the config or logs"})
    return datasets


def default_for(spec: Any) -> Any:
    if isinstance(spec, str):
        low = spec.lower()
        if "list" in low or "array" in low:
            return []
        if "object" in low or "dict" in low or "map" in low:
            return {}
        if "number" in low or "int" in low or "float" in low:
            return None
        if "bool" in low:
            return False
        return ""
    if isinstance(spec, dict):
        return {}
    if isinstance(spec, list):
        return []
    return ""


def mirror_contract(result: dict[str, Any], case: dict[str, Any]) -> list[str]:
    """Ensure every case output_contract field exists in the result.

    Only fills missing keys, recursing into dict-shaped specs. Returns the
    mirrored (previously missing) top-level field names.
    """
    raw = case.get("output_contract") if isinstance(case, dict) else None
    mirrored: list[str] = []

    def ensure(payload: dict[str, Any], spec: Any, top: bool) -> None:
        if isinstance(spec, list):
            for item in spec:
                if isinstance(item, str):
                    if item not in payload:
                        payload[item] = [] if item in LIST_FIELDS else default_for("string")
                        if top:
                            mirrored.append(item)
                else:
                    ensure(payload, item, top)
            return
        if not isinstance(spec, dict):
            return
        for key, sub in spec.items():
            if key in ("required", "fields", "lists", "optional"):
                ensure(payload, sub, top)
                continue
            if isinstance(sub, dict):
                existed = key in payload
                child = payload.setdefault(key, {})
                if isinstance(child, dict):
                    ensure(child, sub, False)
                if top and not existed:
                    mirrored.append(key)
            elif key not in payload:
                payload[key] = default_for(sub) if sub is not None else ""
                if top:
                    mirrored.append(key)

    if raw is not None:
        ensure(result, raw, True)
    return mirrored


def build(case: dict[str, Any], case_path: Path, input_root: str, prose_arg: str,
          work: Path) -> tuple[dict[str, Any], str]:
    roots = [case_path.parent, Path("/input")]
    if input_root:
        roots.append(Path(input_root))
    roots.append(work)
    materials = case.get("materials") if isinstance(case.get("materials"), dict) else {}
    config_key = materials.get("config_dir") or materials.get("config") or "config"
    config_path = locate(str(config_key), roots)
    if config_path is None:
        result = base_result(case_id_of(case), "refused",
                             "config file or directory is missing")
        result.update(empty_fields())
        result["limits"] = ["missing config"]
        result["uncertainty"].append({"item": "config",
                                      "reason": "config path not found in the case inputs",
                                      "needs_human": True})
        return result, "refused"
    files = ([config_path] if config_path.is_file() else
             sorted(p for p in config_path.rglob("*")
                    if p.suffix in {".json", ".yaml", ".yml", ".txt", ".log"}))
    rows: list[dict[str, Any]] = []
    for path in files:
        rows.extend(extract_rows(path))

    prose_path = None
    prose_note = ""
    if prose_arg:
        # An explicitly requested prose file is used as-is; a missing one is a
        # gap to report, never silently replaced by another file.
        prose_path = locate(prose_arg, [work, *roots])
        if prose_path is None:
            prose_note = "prose file not found: %s" % prose_arg
    else:
        prose_path = locate(str(materials.get("prose") or "prose.md"), [work, *roots])
    prose = prose_path.read_text(encoding="utf-8-sig", errors="replace") if prose_path else ""

    audit = audit_prose(prose, rows)
    flagged = audit["unsupported_numbers"]
    datasets = dataset_rows(rows)
    steps = [{"step_id": "p%d" % index, "name": row["name"], "value": row["value"],
              "source": row["source"], "line": row["line"]}
             for index, row in enumerate(rows, 1)]
    limitations = []
    if any(item["status"] == "not_in_source" for item in datasets):
        limitations.append({"item": "dataset",
                            "reason": "not named in the supplied config",
                            "needs_author": True})
    if flagged:
        limitations.append({"item": "prose numbers",
                            "reason": "at least one number is not in the config",
                            "needs_author": True})
    if audit["todo_confirm_count"]:
        limitations.append({"item": "TODO-confirm markers",
                            "reason": "%d number(s) await author confirmation" % audit["todo_confirm_count"],
                            "needs_author": True})
    reproducibility = {
        "config_files": [str(p) for p in files],
        "parameters_extracted": len(rows),
        "command": case.get("command") or "",
        "seed_present": any(row["name"].lower() in {"seed", "random_seed"} for row in rows),
    }

    if prose_path is None or not prose.strip():
        status = "partial"
        reason = ("parameters are extracted but prose.md is missing or empty"
                  + ("; %s" % prose_note if prose_note else ""))
    elif flagged:
        status = "partial"
        reason = "prose contains numbers that are not in the config or logs"
    elif not rows:
        status = "undetermined"
        reason = "no key-value parameters were found"
    elif any(item.get("status") == "not_in_source" for item in datasets):
        status = "partial"
        reason = ("prose numbers match the config; a setup field such as the "
                  "dataset is absent and was not invented")
    else:
        status = "success"
        reason = ("every prose number matches an extracted parameter and the "
                  "setup fields are present")

    result = base_result(case_id_of(case), status, reason)
    result.update({
        "parameter_table": rows,
        "datasets": datasets,
        "steps": steps,
        "prose": prose,
        "number_audit": {
            "unsupported": flagged,
            "known_values": sorted(known_value_strings(rows)),
            "summary": {k: v for k, v in audit.items() if k != "unsupported_numbers"},
        },
        "reproducibility": reproducibility,
        "limitations": limitations,
    })
    result["sources"] = [
        {"source_id": row["name"], "path": row["source"],
         "locator": "line %s" % row["line"] if row["line"] else "json key",
         "quote": "%s=%s" % (row["name"], row["value"])}
        for row in rows
    ]
    for item in flagged:
        result["uncertainty"].append({"item": item["number"], "reason": item["context"],
                                      "needs_human": True})
    for item in limitations:
        result["uncertainty"].append({"item": item["item"], "reason": item["reason"],
                                      "needs_human": True})
    if prose_note:
        result["uncertainty"].append({"item": "prose", "reason": prose_note,
                                      "needs_human": True})
    if status != "success":
        result["limits"] = [reason]
    result["change_records"].append({
        "id": "methods-1",
        "action": "trace",
        "before": "prose numbers",
        "after": "%d config values; %d unsupported" % (len(rows), len(flagged)),
        "reason": "a smooth paragraph can introduce a number that no config contains",
    })
    return result, status


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Assemble result.json from the case config and the prose (code over inference).")
    parser.add_argument("--case", required=True)
    parser.add_argument("--input-root", default="/input")
    parser.add_argument("--prose", default="")
    parser.add_argument("--work", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    case_path = Path(args.case)
    if not case_path.exists():
        sys.stderr.write("[assemble_result] case not found: %s\n" % case_path)
        return 2
    try:
        case = load_json(case_path)
    except (json.JSONDecodeError, OSError) as e:
        sys.stderr.write("[assemble_result] case unreadable: %s\n" % e)
        return 2
    result, status = build(case, case_path, args.input_root, args.prose, Path(args.work))
    mirrored = mirror_contract(result, case)
    if mirrored:
        result["change_records"].append({
            "id": "methods-2",
            "action": "mirror",
            "before": "case output_contract",
            "after": "filled missing fields: " + ", ".join(mirrored),
            "reason": "the result must carry every output_contract field",
        })
    Path(args.work).mkdir(parents=True, exist_ok=True)
    write_json(Path(args.output), result)
    print("status=%s params=%d unsupported=%d mirrored=%d"
          % (status, len(result["parameter_table"]),
             len(result["number_audit"]["unsupported"]), len(mirrored)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
