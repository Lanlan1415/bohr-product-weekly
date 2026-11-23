"""Harbor CLI for frozen-reference coverage and miss analysis.

python -I -X utf8 scripts/coverage_cli.py --case /input/case.json --out /app/output
python -I -X utf8 scripts/coverage_cli.py --case examples/case.json --out ./_run_example

Exit 0 clean, 3 review/partial, 4 invalid case object, 5 unreadable/undetermined.
Every expected failure writes result.json without a traceback and, when readable,
preserves case_id and all output_contract fields. No network calls are made.
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
import coverage as engine  # noqa: E402

ALLOWED_SECTIONS = {None, "", "coverage", "search-coverage", "coverage_analysis",
                    "检索覆盖率与遗漏分析"}


def _refuse(out: Path, case: Any, rule: str, message: str) -> dict[str, Any]:
    result = C.refusal_result(case, rule, message, "coverage", engine.SCHEMA_VERSION)
    C.write_json(out / "result.json", result)
    return result


def run_case(case: dict[str, Any], case_dir: Path, out: Path) -> dict[str, Any]:
    result = engine.analyze(C.merged_spec(case), case_dir)
    result = engine.attach_rubric(result)
    result = C.complete_contract(result, case, "coverage")
    C.write_json(out / "result.json", result)
    C.write_jsonl(out / "coverage_matrix.jsonl", result["coverage_matrix"])
    C.write_json(out / "supplementary_search.json", result["supplementary_search"])
    C.write_json(out / "search_protocol.json", {
        "sources_and_queries": result["sources"],
        "reference_freeze": result["reference_freeze"],
        "scope": "supplied finite snapshot only; no live search was performed",
    })
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="search-coverage", description=__doc__)
    parser.add_argument("--case", "--spec", dest="case", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args(argv)
    out = Path(args.out)
    case: Any = {}
    try:
        try:
            case = json.loads(Path(args.case).read_text(encoding="utf-8-sig"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            _refuse(out, {}, "coverage.case_unreadable", f"case file not readable: {exc}")
            return 5
        if not isinstance(case, dict):
            _refuse(out, {}, "coverage.case_not_object", "case.json must be a JSON object")
            return 4
        if case.get("section") not in ALLOWED_SECTIONS:
            _refuse(out, case, "coverage.unknown_section", f"unknown section '{case.get('section')}'")
            return 5
        C.write_json(out / "result.json", {
            "schema_version": engine.SCHEMA_VERSION, "status": "undetermined",
            "case_id": case.get("case_id"),
            "limits": ["coverage analysis is still running; this partial is replaced only after completion"],
        })
        result = run_case(case, Path(args.case).resolve().parent, out)
        metrics = result["coverage_metrics"]
        print(json.dumps({"status": result["status"], "case_id": result.get("case_id"),
                          "recall": metrics["known_set_recall"],
                          "covered": metrics["covered_references"],
                          "reference_total": metrics["reference_total_after_internal_dedup"],
                          "marginal_gain": result["supplementary_search"]["marginal_gain"]}, ensure_ascii=False))
        return {"clean": 0, "review": 3, "blocked": 4, "undetermined": 5}.get(result["status"], 5)
    except C.MaterialError as exc:
        _refuse(out, case, exc.rule, str(exc))
        return exc.exit_code
    except Exception as exc:  # The formal boundary must never leak a traceback.
        _refuse(out, case, "coverage.internal_error", f"{type(exc).__name__}: {exc}")
        return 5


if __name__ == "__main__":
    raise SystemExit(main())
