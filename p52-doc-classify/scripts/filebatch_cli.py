"""Classify actual files and optionally create an organised, verified COPY.

  python filebatch_cli.py --root /input/library --spec workorder.json \
      --case /input/case.json --out /app/output --materialize /app/output/organized

Spec: taxonomy (required), metadata_files, min_hits and organize naming options.
Every source file is inventoried and hashed. No source move/rename/delete occurs.

Exit 0 ok; 3 review (unknown/low-confidence/multi-way ambiguity/near duplicate);
4 blocked (unsafe/hash/copy conflict); 5 undetermined (bad input/export);
2 argparse usage. A readable case's case_id and every output_contract key are
retained on success, review, blocked and structured refusal paths.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import filebatch  # noqa: E402

_BULKY = {"output_contract", "records", "documents", "files", "materials", "task", "text"}


def _read(path: Path) -> tuple[dict | None, str | None]:
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        return None, str(exc)
    if not isinstance(value, dict):
        return None, "expected a JSON object"
    return value, None


def _derived(result: dict, key: str):
    values = {
        "library_result": {"files": result.get("files") or [],
                           "classification_summary": result.get("classification_summary"),
                           "plan": result.get("plan") or [],
                           "duplicates": result.get("duplicates") or [],
                           "version_relations": result.get("version_relations") or []},
        "classification_result": {"files": result.get("files") or [],
                                  "summary": result.get("classification_summary"),
                                  "taxonomy": result.get("taxonomy_declared") or []},
        "operation_evidence": result.get("operation_evidence") or {
            "source_mode": "read_only", "source_writes": 0,
            "plan": result.get("plan") or [], "batch_sha256": result.get("batch_sha256")},
        "failure_recovery": {"findings": result.get("findings") or [],
                             "metadata_warnings": result.get("metadata_warnings") or [],
                             "limits": result.get("limits") or [],
                             "recovery": "original files are untouched; review/remove only generated copies"},
        "sources": [{"path": f.get("path"), "sha256": (f.get("inventory") or {}).get("sha256"),
                     "metadata_provenance": f.get("metadata_provenance") or {}}
                    for f in result.get("files") or []],
        "uncertainty": {"needs_review": (result.get("classification_summary") or {}).get("needs_review_ids") or [],
                        "classification_summary": result.get("classification_summary")},
    }
    return values.get(key)


def _echo(result: dict, case: dict | None) -> None:
    if not case:
        return
    limits = result.setdefault("limits", [])
    result["case_id"] = case.get("case_id", case.get("id"))
    contract = case.get("output_contract")
    if isinstance(contract, list):
        contract = {str(k): None for k in contract}
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
            limits.append(f"output_contract field {key!r} retained as null because it was underivable")


def _write(out: Path, result: dict) -> None:
    out.mkdir(parents=True, exist_ok=True)
    (out / "result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2),
                                    encoding="utf-8")


def _refusal(out: Path, case: dict | None, rule: str, message: str) -> dict:
    result = {"schema_version": filebatch.SCHEMA_VERSION, "status": "undetermined",
              "refusal": {"rule": rule, "message": message},
              "limits": ["no complete classification or materialisation is claimed"]}
    _echo(result, case)
    _write(out, result)
    return result


def run(root: Path, spec_path: Path, case_path: Path | None, out: Path,
        materialize: Path | None) -> dict:
    case = None
    if case_path:
        case, error = _read(case_path)
        if error:
            return _refusal(out, None, "filebatch.case_unreadable", error)
    spec, error = _read(spec_path)
    if error:
        return _refusal(out, case, "filebatch.spec_unreadable", error)
    try:
        root_resolved, out_resolved = root.resolve(), out.resolve()
        if root_resolved == out_resolved or root_resolved in out_resolved.parents or out_resolved in root_resolved.parents:
            return _refusal(out, case, "filebatch.output_conflict",
                            "out must be separate from, not inside, and not contain the source root")
        result = filebatch.run_with_output(spec, root, out, materialize)
    except Exception as exc:  # the public CLI always degrades to a structured result
        return _refusal(out, case, "filebatch.run_failed",
                        f"{type(exc).__name__}: {exc}")
    if result.get("status") != "undetermined":
        try:
            out.mkdir(parents=True, exist_ok=True)
            (out / "classification.json").write_text(json.dumps({
                "files": result.get("files") or [],
                "summary": result.get("classification_summary"),
                "taxonomy": result.get("taxonomy_declared") or [],
            }, ensure_ascii=False, indent=2), encoding="utf-8")
            (out / "operation_plan.json").write_text(json.dumps({
                "source_mode": "read_only", "source_writes": 0,
                "plan": result.get("plan") or [],
                "duplicates": result.get("duplicates") or [],
                "near_duplicates": result.get("near_duplicates") or [],
                "version_relations": result.get("version_relations") or [],
            }, ensure_ascii=False, indent=2), encoding="utf-8")
            (out / "summary.md").write_text(filebatch.render_summary(result), encoding="utf-8")
            result["wrote"] = [str(out / n) for n in
                               ("classification.json", "operation_plan.json", "summary.md", "result.json")]
        except OSError as exc:
            return _refusal(out, case, "filebatch.export_failed", str(exc))
    _echo(result, case)
    _write(out, result)
    return result


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="doc-filebatch", description=__doc__)
    ap.add_argument("--root", required=True, help="actual source file tree (read-only)")
    ap.add_argument("--spec", required=True, help="workorder JSON with declared taxonomy")
    ap.add_argument("--case", help="case.json for contract passthrough")
    ap.add_argument("--out", required=True, help="separate result directory")
    ap.add_argument("--materialize", help="separate directory for hash-verified organised copies")
    args = ap.parse_args(argv)
    result = run(Path(args.root), Path(args.spec),
                 Path(args.case) if args.case else None, Path(args.out),
                 Path(args.materialize) if args.materialize else None)
    print(json.dumps({"status": result.get("status"), "case_id": result.get("case_id"),
                      "counts": result.get("counts"), "refusal": result.get("refusal")},
                     ensure_ascii=False))
    return {"ok": 0, "review": 3, "blocked": 4, "undetermined": 5}.get(result.get("status"), 5)


if __name__ == "__main__":
    raise SystemExit(main())
