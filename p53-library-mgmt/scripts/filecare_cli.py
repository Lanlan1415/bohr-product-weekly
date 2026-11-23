"""Inspect a REAL research file tree without modifying it.

  python filecare_cli.py --root /path/to/library --spec spec.json \
      --case /input/case.json --query "缓冲液" --out /app/output

The optional spec declares records/metadata_files, structure, meta_fields and
organize.naming_template. Output: result.json, file_inventory.json,
operation_plan.json and inventory.md. No move/rename/delete is ever executed.

Exit 0 = ok; 4 = partial (named unreadable/extraction/link/conflict items);
5 = undetermined (unreadable input, missing/empty root, export failure);
2 = argparse usage. Whenever the case itself is readable, case_id and every
output_contract key are present even on a structured refusal.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import filecare  # noqa: E402

_BULKY = {"output_contract", "task", "materials", "documents", "records", "text", "files"}


def _read_json(path: Path) -> tuple[dict | None, str | None]:
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        return None, str(exc)
    if not isinstance(value, dict):
        return None, "JSON root must be an object"
    return value, None


def _derived(result: dict, key: str):
    if key == "library_result":
        return {"documents": result.get("documents") or [],
                "duplicates": result.get("duplicates") or [],
                "version_candidates": result.get("version_candidates") or [],
                "declared_version_links": result.get("declared_version_links") or [],
                "operation_plan": result.get("operation_plan") or []}
    if key == "operation_evidence":
        return result.get("operation_evidence")
    if key == "failure_recovery":
        return {"findings": result.get("findings") or [],
                "attachments": result.get("attachments") or {},
                "limits": result.get("limits") or [],
                "recovery": "source tree was read-only; no recovery write is required"}
    if key == "sources":
        docs = result.get("documents") or []
        return [{"path": d.get("path"), "sha256": d.get("sha256"),
                 "meta_src": d.get("meta_src") or {}} for d in docs]
    if key == "uncertainty":
        return [f for f in (result.get("findings") or [])
                if f.get("severity") in {"medium", "high", "low"}]
    if key in {"changes", "change_record"}:
        return result.get("operation_evidence")
    return None


def _echo_contract(result: dict, case: dict | None) -> None:
    if not case:
        return
    limits = result.setdefault("limits", [])
    cid = case.get("case_id", case.get("id"))
    result["case_id"] = cid
    if cid is None:
        limits.append("case_id was absent in the readable case object")
    contract = case.get("output_contract")
    if isinstance(contract, list):
        keys = [str(k) for k in contract]
        contract = {k: None for k in keys}
    if not isinstance(contract, dict):
        if contract is not None:
            limits.append("output_contract was neither an object nor a field list")
        return
    for key, literal in contract.items():
        if key in result:
            continue
        value = _derived(result, key)
        if value is not None:
            result[key] = value
        elif key in case and key not in _BULKY:
            result[key] = case[key]
        elif isinstance(literal, (str, int, float, bool)) and (
                not isinstance(literal, str) or len(literal) <= 500):
            result[key] = literal
        else:
            result[key] = None
            limits.append(f"output_contract field {key!r} was not derivable; retained as null")


def _write(out: Path, result: dict) -> None:
    out.mkdir(parents=True, exist_ok=True)
    (out / "result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2),
                                    encoding="utf-8")


def _structured_refusal(out: Path, case: dict | None, rule: str, message: str) -> dict:
    result = filecare.refusal(rule, message)
    _echo_contract(result, case)
    _write(out, result)
    return result


def run(root: Path | None, spec_path: Path | None, case_path: Path | None,
        query: str | None, out: Path) -> dict:
    case = None
    if case_path:
        case, error = _read_json(case_path)
        if error:
            return _structured_refusal(out, None, "filecare.case_unreadable", error)
    spec: dict = {}
    if spec_path:
        spec, error = _read_json(spec_path)
        if error:
            return _structured_refusal(out, case, "filecare.spec_unreadable", error)
    try:
        result = filecare.run(spec, root, query)
        if result.get("status") == "undetermined":
            _echo_contract(result, case)
            _write(out, result)
            return result
        library_result = {
            "schema_version": result["schema_version"], "counts": result["counts"],
            "documents": result["documents"], "duplicates": result["duplicates"],
            "version_candidates": result["version_candidates"],
            "declared_version_links": result["declared_version_links"],
            "attachments": result["attachments"],
            "metadata_conflicts": result["metadata_conflicts"],
        }
        out.mkdir(parents=True, exist_ok=True)
        (out / "file_inventory.json").write_text(
            json.dumps(library_result, ensure_ascii=False, indent=2), encoding="utf-8")
        (out / "operation_plan.json").write_text(
            json.dumps({"source_mode": "read_only", "executed_moves": 0,
                        "plan": result["operation_plan"]}, ensure_ascii=False, indent=2),
            encoding="utf-8")
        (out / "inventory.md").write_text(filecare.render_inventory(result), encoding="utf-8")
        result["wrote"] = [str(out / n) for n in
                           ("file_inventory.json", "operation_plan.json", "inventory.md", "result.json")]
    except OSError as exc:
        return _structured_refusal(out, case, "filecare.export_failed", str(exc))
    _echo_contract(result, case)
    _write(out, result)
    return result


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="library-filecare", description=__doc__)
    ap.add_argument("--root", required=True, help="real source tree; opened read-only")
    ap.add_argument("--spec", help="optional declarations JSON")
    ap.add_argument("--case", help="case.json for case_id/output_contract passthrough")
    ap.add_argument("--query", help="optional full-text/title/path/metadata query")
    ap.add_argument("--out", required=True, help="separate output directory")
    args = ap.parse_args(argv)
    result = run(Path(args.root) if args.root else None,
                 Path(args.spec) if args.spec else None,
                 Path(args.case) if args.case else None,
                 args.query, Path(args.out))
    print(json.dumps({"status": result.get("status"), "case_id": result.get("case_id"),
                      "counts": result.get("counts"), "refusal": result.get("refusal")},
                     ensure_ascii=False))
    return {"ok": 0, "partial": 4, "undetermined": 5}.get(result.get("status"), 5)


if __name__ == "__main__":
    raise SystemExit(main())
