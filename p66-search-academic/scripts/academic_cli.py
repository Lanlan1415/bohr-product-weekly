"""Run source-bound academic retrieval; never performs network I/O.

python -I -X utf8 scripts/academic_cli.py --case /input/case.json --out /app/output

Exit 0 clean, 3 review/partial, 4 blocked/caller-shape, 5 unreadable or internal.
Every scientific-input failure writes result.json with case_id/output_contract when
those are readable.  Argparse usage errors remain exit 2.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import retrieval_common as C  # noqa: E402
import academic_engine as E  # noqa: E402


def write_outputs(out: Path, result: dict) -> None:
    out.mkdir(parents=True, exist_ok=True)
    C.write_json(out / "query_plan.json", result.get("query_plan", {}))
    C.write_json(out / "query_log.json", result.get("query_log", []))
    C.write_json(out / "candidate_set.json", result.get("candidate_set", []))
    query_rows = []
    for row in result.get("query_log", []):
        query_rows.append({
            "query_id": row["query_id"], "round": row["round"], "purpose": row["purpose"],
            "execution_status": row["execution_status"], "boolean_logic": row["boolean_logic"],
            "concepts": row["concepts"], "time_boundary": row["time_boundary"],
            "language_boundary": row["language_boundary"], "local_snapshot_hit_count": row["local_snapshot_hit_count"],
            "remote_hit_count": None, "local_snapshot_hit_work_ids": row["local_snapshot_hit_work_ids"],
            "empty_result": row.get("empty_result"),
        })
    C.write_csv(out / "query_log.csv", query_rows,
                ["query_id", "round", "purpose", "execution_status", "boolean_logic", "concepts",
                 "time_boundary", "language_boundary", "local_snapshot_hit_count", "remote_hit_count",
                 "local_snapshot_hit_work_ids", "empty_result"])
    candidate_rows = []
    for item in result.get("candidate_set", []):
        candidate_rows.append({
            "rank": item["rank"], "record_id": item["record_id"], "work_id": item["work_id"],
            "title": item["metadata"].get("title"), "authors": item["metadata"].get("authors"),
            "year": item["metadata"].get("year"), "journal": item["metadata"].get("journal"),
            "doi": item["metadata"].get("doi"), "in_top_k": item["in_top_k"],
            "relevance_normalized": item["relevance"]["normalized_relevance"], "bm25": item["relevance"]["bm25"],
            "facet_coverage": item["relevance"]["facet_coverage"],
            "field_components": item["relevance"]["field_components"],
            "matched_terms": item["relevance"]["matched_terms"],
            "metadata_completeness": item["metadata_completeness"]["score"],
            "metadata_missing": item["metadata_completeness"]["missing_fields"],
            "source_trace_quality": item["source_quality"]["score"],
            "retrieved_by_query_ids": item["retrieved_by_query_ids"], "member_ids": item["member_ids"],
            "dedup_status": item["dedup_status"], "sources": item["sources"],
        })
    C.write_csv(out / "candidate_set.csv", candidate_rows,
                ["rank", "record_id", "work_id", "title", "authors", "year", "journal", "doi", "in_top_k",
                 "relevance_normalized", "bm25", "facet_coverage", "field_components", "matched_terms",
                 "metadata_completeness", "metadata_missing", "source_trace_quality", "retrieved_by_query_ids",
                 "member_ids", "dedup_status", "sources"])
    C.write_csv(out / "dedup_audit.csv", result.get("dedup_audit", []),
                ["record_id", "dataset_id", "dataset_row", "work_id", "group_id", "duplicate_of",
                 "dedup_status", "accounting"])
    (out / "retrieval_report.md").write_text(E.report_markdown(result), encoding="utf-8")
    artifacts = []
    for name in result.get("deliverables", []):
        if name == "result.json":
            continue
        path = out / name
        artifacts.append({"path": name, "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                          "bytes": path.stat().st_size})
    result["artifacts"] = artifacts
    C.write_json(out / "result.json", result)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="academic-search", description=__doc__)
    parser.add_argument("--case", "--spec", dest="case", required=True, help="actual case.json (offline data only)")
    parser.add_argument("--out", required=True, help="output directory")
    args = parser.parse_args(argv)
    out = Path(args.out)
    case = None
    try:
        case = C.load_case(Path(args.case))
        # Honest early partial: never wait until the end to create a deliverable.
        partial = {"schema_version": E.SCHEMA_VERSION, "status": "review", "case_id": case.get("case_id"),
                   "findings": [{"rule": "academic.run_in_progress", "severity": "low",
                                 "message": "partial initialization artifact; will be replaced at completion"}],
                   "limits": ["initialization only; no retrieval result yet"],
                   "uncertainty": ["retrieval did not complete when this partial was written"]}
        C.write_json(out / "result.json", C.complete_contract(partial, C.merged_spec(case), case))
        result = E.build_result(case, Path(args.case).resolve().parent)
        write_outputs(out, result)
    except C.RetrievalError as exc:
        result = C.refusal_result(case, exc.rule, str(exc))
        if exc.exit_code == 4:
            result["status"] = "blocked"
            result["状态说明"]["运行状态"] = "blocked"
        C.write_json(out / "result.json", result)
    except Exception as exc:  # scientific boundary: no traceback into the deliverable
        result = C.refusal_result(case, "academic.internal_error", f"{type(exc).__name__}: {exc}")
        C.write_json(out / "result.json", result)
    print(json.dumps({"status": result.get("status"), "case_id": result.get("case_id"),
                      "candidates": len(result.get("candidate_set", [])),
                      "local_queries": len(result.get("query_log", [])),
                      "remote_hit_count": None, "wrote": str(out / "result.json")}, ensure_ascii=False))
    if "refusal" in result:
        return 4 if result.get("status") == "blocked" else 5
    return C.EXIT.get(result.get("status"), 5)


if __name__ == "__main__":
    raise SystemExit(main())
