"""Offline explainable scientific-record screening and ranking.

python -I -X utf8 scripts/screening_cli.py --case /input/case.json --out /app/output

Exit 0 clean, 3 review/pending/conflict/no-retained, 4 blocked input/case shape,
5 unreadable/internal, 2 argparse usage.  result.json is written on scientific
failure without a traceback and retains readable case_id/output_contract.
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
import screening_engine as E  # noqa: E402


def write_outputs(out: Path, result: dict) -> None:
    out.mkdir(parents=True, exist_ok=True)
    C.write_json(out / "screening_protocol.json", result.get("screening_protocol", {}))
    C.write_json(out / "screened_records.json", result.get("screened_records", []))
    C.write_csv(out / "screening_log.csv", result.get("screening_log", []),
                ["dataset_id", "dataset_row", "record_id", "work_id", "group_id", "duplicate_of", "dedup_status",
                 "title", "engine_decision", "final_decision", "relevance_class", "reason_code", "reason",
                 "priority_score", "decision_confidence", "review_resolution", "not_independent_evidence", "accounting"])
    rank_rows = []
    for row in result.get("screened_records", []):
        rank_rows.append({"record_id": row["record_id"], "work_id": row["work_id"], "ranking_layer": row["ranking_layer"],
                          "rank": row["rank"], "in_top_k": row["in_top_k"], "title": row["metadata"].get("title"),
                          "authors": row["metadata"].get("authors"), "year": row["metadata"].get("year"),
                          "journal": row["metadata"].get("journal"), "doi": row["metadata"].get("doi"),
                          "engine_decision": row["engine_decision"], "final_decision": row["final_decision"],
                          "relevance_class": row["relevance_class"], "reason_code": row["reason_code"],
                          "reason": row["reason"], "criteria_matches": row["criteria_matches"],
                          "priority_score": row["priority_score"], "score_components": row["score_components"],
                          "weighted_components": row["weighted_components"], "bm25": row["relevance"]["bm25"],
                          "matched_terms": row["relevance"]["matched_terms"],
                          "field_components": row["relevance"]["field_components"], "evidence": row["evidence"],
                          "metadata_completeness": row["metadata_completeness"], "source_quality": row["source_quality"],
                          "decision_confidence": row["decision_confidence"], "needs_human_review": row["needs_human_review"],
                          "near_tie_with": row["near_tie_with"], "exact_tie_with": row["exact_tie_with"],
                          "member_ids": row["member_ids"], "sources": row["sources"],
                          "review_resolution": row["review_resolution"]})
    C.write_csv(out / "ranked_candidates.csv", rank_rows,
                ["record_id", "work_id", "ranking_layer", "rank", "in_top_k", "title", "authors", "year", "journal", "doi",
                 "engine_decision", "final_decision", "relevance_class", "reason_code", "reason", "criteria_matches",
                 "priority_score", "score_components", "weighted_components", "bm25", "matched_terms", "field_components",
                 "evidence", "metadata_completeness", "source_quality", "decision_confidence", "needs_human_review",
                 "near_tie_with", "exact_tie_with", "member_ids", "sources", "review_resolution"])
    C.write_csv(out / "review_queue.csv", result.get("review_queue", []),
                ["work_id", "record_id", "final_decision", "priority_score", "decision_confidence",
                 "review_reasons", "near_tie_with", "exact_tie_with", "review_resolution",
                 "human_review_performed", "resolution_required"])
    (out / "screening_report.md").write_text(E.report_markdown(result), encoding="utf-8")
    result["artifacts"] = []
    for name in result.get("deliverables", []):
        if name == "result.json":
            continue
        path = out / name
        result["artifacts"].append({"path": name, "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                                    "bytes": path.stat().st_size})
    C.write_json(out / "result.json", result)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="screening-rank", description=__doc__)
    parser.add_argument("--case", "--spec", dest="case", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args(argv)
    out = Path(args.out)
    case = None
    try:
        case = C.load_case(Path(args.case))
        partial = {"schema_version": E.SCHEMA_VERSION, "status": "review", "case_id": case.get("case_id"),
                   "findings": [{"rule": "screening.run_in_progress", "severity": "low",
                                 "message": "partial initialization artifact; expected to be replaced"}],
                   "limits": ["initialization only; no screening decision yet"], "uncertainty": ["not completed"]}
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
        result = C.refusal_result(case, "screening.internal_error", f"{type(exc).__name__}: {exc}")
        C.write_json(out / "result.json", result)
    summary = result.get("candidate_set_summary", {})
    print(json.dumps({"status": result.get("status"), "case_id": result.get("case_id"),
                      "include": summary.get("include"), "pending": summary.get("pending"),
                      "exclude": summary.get("exclude"), "review_queue": summary.get("review_queue"),
                      "all_raw_rows_accounted": summary.get("all_raw_rows_accounted"),
                      "remote_hit_count": None, "wrote": str(out / "result.json")}, ensure_ascii=False))
    if "refusal" in result:
        return 4 if result.get("status") == "blocked" else 5
    return C.EXIT.get(result.get("status"), 5)


if __name__ == "__main__":
    raise SystemExit(main())
