"""Harbor CLI for controlled cross-language retrieval and original-text evidence.

python -I -X utf8 scripts/crosslang_cli.py --case /input/case.json --out /app/output
python -I -X utf8 scripts/crosslang_cli.py --case examples/case.json --out ./_run_example

Exit 0 clean, 3 review/partial, 4 invalid case object, 5 unreadable/undetermined.
No network or MT service is called. Expected failures write result.json without a
traceback and preserve readable case_id plus all original output_contract fields.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import case_common as C  # noqa: E402
import crosslang as engine  # noqa: E402

ALLOWED_SECTIONS = {None, "", "crosslang", "cross-language", "search-crosslang",
                    "cross_language_search", "跨语言文献检索"}


def _refuse(out: Path, case: Any, rule: str, message: str) -> dict[str, Any]:
    result = C.refusal_result(case, rule, message, "crosslang", engine.SCHEMA_VERSION)
    C.write_json(out / "result.json", result)
    return result


def run_case(case: dict[str, Any], case_dir: Path, out: Path) -> dict[str, Any]:
    result = engine.attach_rubric(engine.analyze(C.merged_spec(case), case_dir))
    result = C.complete_contract(result, case, "crosslang")
    C.write_json(out / "result.json", result)
    C.write_json(out / "concept_alignment.json", result["concept_alignment"])
    C.write_jsonl(out / "multilingual_queries.jsonl", result["multilingual_queries"])
    C.write_jsonl(out / "original_evidence.jsonl", result["evidence_ledger"])
    C.write_json(out / "retrieval_evaluation.json", {
        "language_summary": result["language_summary"],
        "known_set_evaluation": result["known_set_evaluation"],
        "feedback_runs": result["feedback_runs"],
        "quotation_policy": result["quotation_policy"],
        "independent_recompute": result["independent_recompute"],
    })
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="search-crosslang", description=__doc__)
    parser.add_argument("--case", "--spec", dest="case", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args(argv)
    out = Path(args.out)
    case: Any = {}
    try:
        try:
            case = json.loads(Path(args.case).read_text(encoding="utf-8-sig"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            _refuse(out, {}, "crosslang.case_unreadable", f"case file not readable: {exc}")
            return 5
        if not isinstance(case, dict):
            _refuse(out, {}, "crosslang.case_not_object", "case.json must be a JSON object")
            return 4
        if case.get("section") not in ALLOWED_SECTIONS:
            _refuse(out, case, "crosslang.unknown_section", f"unknown section '{case.get('section')}'")
            return 5
        C.write_json(out / "result.json", {
            "schema_version": engine.SCHEMA_VERSION, "status": "undetermined",
            "case_id": case.get("case_id"),
            "limits": ["cross-language analysis is still running; this partial is replaced only after completion"],
        })
        result = run_case(case, Path(args.case).resolve().parent, out)
        recall = result["known_set_evaluation"]
        print(json.dumps({"status": result["status"], "case_id": result.get("case_id"),
                          "works": result["unique_candidate_works"],
                          "views": result["unique_input_views_after_exact_dedup"],
                          "baseline_recall": recall["before"]["known_set_recall"],
                          "expanded_recall": recall["after"]["known_set_recall"],
                          "marginal_gain": recall["marginal_gain"]}, ensure_ascii=False))
        return {"clean": 0, "review": 3, "blocked": 4, "undetermined": 5}.get(result["status"], 5)
    except C.MaterialError as exc:
        _refuse(out, case, exc.rule, str(exc))
        return exc.exit_code
    except Exception as exc:
        _refuse(out, case, "crosslang.internal_error", f"{type(exc).__name__}: {exc}")
        return 5


if __name__ == "__main__":
    raise SystemExit(main())
