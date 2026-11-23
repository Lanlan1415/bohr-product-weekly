"""Harbor CLI for reproducible protocol, dedup and dual-review screening.

python -I -X utf8 scripts/systematic_cli.py --case /input/case.json --out /app/output
python -I -X utf8 scripts/systematic_cli.py --case examples/case.json --out ./_run_example

Exit 0 clean, 3 review/partial, 4 invalid case object, 5 unreadable/undetermined.
No live database requests. Expected failures write result.json without a traceback
and retain readable case_id plus all original output_contract fields.
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
import systematic as engine  # noqa: E402

ALLOWED_SECTIONS = {None, "", "systematic", "search-systematic", "systematic_search",
                    "systematic_screening", "系统性文献检索与纳排筛选"}


def _refuse(out: Path, case: Any, rule: str, message: str) -> dict[str, Any]:
    result = C.refusal_result(case, rule, message, "systematic", engine.SCHEMA_VERSION)
    C.write_json(out / "result.json", result)
    return result


def run_case(case: dict[str, Any], case_dir: Path, out: Path) -> dict[str, Any]:
    result = engine.attach_rubric(engine.analyze(C.merged_spec(case), case_dir))
    result = C.complete_contract(result, case, "systematic")
    C.write_json(out / "result.json", result)
    C.write_json(out / "search_protocol.json", result["search_protocol"])
    C.write_jsonl(out / "screening_decisions.jsonl", result["screening_decisions"])
    C.write_json(out / "flow_audit.json", result["flow_counts"])
    C.write_json(out / "adjudication_and_agreement.json", {
        "reviewer_agreement": result["reviewer_agreement"],
        "disagreements": [f for f in result["findings"] if "disagreement" in f["rule"]],
        "criteria_version": result["criteria_version"],
    })
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="search-systematic", description=__doc__)
    parser.add_argument("--case", "--spec", dest="case", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args(argv)
    out = Path(args.out)
    case: Any = {}
    try:
        try:
            case = json.loads(Path(args.case).read_text(encoding="utf-8-sig"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            _refuse(out, {}, "systematic.case_unreadable", f"case file not readable: {exc}")
            return 5
        if not isinstance(case, dict):
            _refuse(out, {}, "systematic.case_not_object", "case.json must be a JSON object")
            return 4
        if case.get("section") not in ALLOWED_SECTIONS:
            _refuse(out, case, "systematic.unknown_section", f"unknown section '{case.get('section')}'")
            return 5
        C.write_json(out / "result.json", {
            "schema_version": engine.SCHEMA_VERSION, "status": "undetermined",
            "case_id": case.get("case_id"),
            "limits": ["screening is still running; this partial is replaced only after completion"],
        })
        result = run_case(case, Path(args.case).resolve().parent, out)
        print(json.dumps({"status": result["status"], "case_id": result.get("case_id"),
                          "unique_clusters": result["unique_work_clusters"],
                          "included": result["flow_counts"]["overall"]["included"],
                          "excluded": result["flow_counts"]["overall"]["excluded"],
                          "pending": result["flow_counts"]["overall"]["pending"],
                          "counts_closed": result["prisma_counts_closed"]}, ensure_ascii=False))
        return {"clean": 0, "review": 3, "blocked": 4, "undetermined": 5}.get(result["status"], 5)
    except C.MaterialError as exc:
        _refuse(out, case, exc.rule, str(exc))
        return exc.exit_code
    except Exception as exc:
        _refuse(out, case, "systematic.internal_error", f"{type(exc).__name__}: {exc}")
        return 5


if __name__ == "__main__":
    raise SystemExit(main())
