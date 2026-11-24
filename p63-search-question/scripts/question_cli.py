"""Question-driven fixed-snapshot retrieval; no network access.

python -I -X utf8 scripts/question_cli.py --case /input/case.json --out /app/output

Exit: 0 clean, 3 review/gap/conflict, 4 blocked caller shape, 5 unreadable/internal;
argparse usage errors are 2.  All scientific failures write result.json without a
traceback and preserve readable case_id/output_contract values.
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
import question_engine as E  # noqa: E402


def write_outputs(out: Path, result: dict) -> None:
    out.mkdir(parents=True, exist_ok=True)
    C.write_json(out / "question_plan.json", result.get("question_decomposition", {}))
    C.write_json(out / "query_log.json", result.get("query_log", []))
    rows = []
    for log in result.get("query_log", []):
        rows.append({"subquestion_id": log["subquestion_id"], "query_id": log["query_id"], "round": log["round"],
                     "purpose": log["purpose"], "concepts": log["concepts"], "boolean_logic": log["boolean_logic"],
                     "time_boundary": log["time_boundary"], "language_boundary": log["language_boundary"],
                     "diagnostic_partial_only": log["diagnostic_partial_only"],
                     "local_snapshot_hit_count": log["local_snapshot_hit_count"], "remote_hit_count": None,
                     "local_snapshot_hit_work_ids": log["local_snapshot_hit_work_ids"],
                     "excluded_from_boundary_or_boolean": log["excluded_from_boundary_or_boolean"],
                     "empty_result": log.get("empty_result")})
    C.write_csv(out / "query_log.csv", rows,
                ["subquestion_id", "query_id", "round", "purpose", "concepts", "boolean_logic", "time_boundary",
                 "language_boundary", "diagnostic_partial_only", "local_snapshot_hit_count", "remote_hit_count",
                 "local_snapshot_hit_work_ids", "excluded_from_boundary_or_boolean", "empty_result"])
    evidence_rows = []
    for sub in result.get("subquestion_results", []):
        for row in sub["direct_evidence"]:
            work = next(item for item in result["candidate_set"] if item["work_id"] == row["work_id"])
            evidence_rows.append({"subquestion_id": sub["subquestion_id"], "subquestion_status": sub["status"],
                                  "work_id": row["work_id"], "record_id": row["record_id"],
                                  "title": work["metadata"].get("title"), "doi": work["metadata"].get("doi"),
                                  "year": work["metadata"].get("year"),
                                  "relevance_normalized": row["normalized_relevance"], "bm25": row["bm25"],
                                  "facet_matches": row["facet_matches"], "matched_terms": row["matched_terms"],
                                  "field_components": row["field_components"], "evidence": row["evidence"],
                                  "direct_joint_hit": row["direct_joint_hit"], "conflicts": sub["conflicts"],
                                  "metadata_completeness": work["metadata_completeness"],
                                  "source_quality": work["source_quality"], "sources": work["sources"]})
    C.write_csv(out / "question_evidence.csv", evidence_rows,
                ["subquestion_id", "subquestion_status", "work_id", "record_id", "title", "doi", "year",
                 "relevance_normalized", "bm25", "facet_matches", "matched_terms", "field_components", "evidence",
                 "direct_joint_hit", "conflicts", "metadata_completeness", "source_quality", "sources"])
    (out / "question_report.md").write_text(E.report_markdown(result), encoding="utf-8")
    result["artifacts"] = []
    for name in result.get("deliverables", []):
        if name == "result.json":
            continue
        path = out / name
        result["artifacts"].append({"path": name, "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                                    "bytes": path.stat().st_size})
    C.write_json(out / "result.json", result)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="question-search", description=__doc__)
    parser.add_argument("--case", "--spec", dest="case", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args(argv)
    out = Path(args.out)
    case = None
    try:
        case = C.load_case(Path(args.case))
        partial = {"schema_version": E.SCHEMA_VERSION, "status": "review", "case_id": case.get("case_id"),
                   "findings": [{"rule": "question.run_in_progress", "severity": "low",
                                 "message": "initialization artifact; will be replaced by actual run"}],
                   "limits": ["partial only; no subquestion was answered yet"], "uncertainty": ["not completed"]}
        C.write_json(out / "result.json", C.complete_contract(partial, C.merged_spec(case), case))
        result = E.build_result(case, Path(args.case).resolve().parent)
        write_outputs(out, result)
    except C.RetrievalError as exc:
        result = C.refusal_result(case, exc.rule, str(exc))
        if exc.exit_code == 4:
            result["status"] = "blocked"
            result["状态说明"]["运行状态"] = "blocked"
        C.write_json(out / "result.json", result)
    except Exception as exc:
        result = C.refusal_result(case, "question.internal_error", f"{type(exc).__name__}: {exc}")
        C.write_json(out / "result.json", result)
    print(json.dumps({"status": result.get("status"), "case_id": result.get("case_id"),
                      "subquestions": len(result.get("subquestion_results", [])),
                      "answered": sum(s["status"] == "answered" for s in result.get("subquestion_results", [])),
                      "remote_hit_count": None, "wrote": str(out / "result.json")}, ensure_ascii=False))
    if "refusal" in result:
        return 4 if result.get("status") == "blocked" else 5
    return C.EXIT.get(result.get("status"), 5)


if __name__ == "__main__":
    raise SystemExit(main())
