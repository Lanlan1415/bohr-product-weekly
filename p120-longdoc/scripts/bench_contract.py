"""Contract benchmark: the delivery contract survives every run shape.

Runs the secrun engine in-process against fixture specs written to a temporary
directory and asserts, per scenario, what the delivery contract requires:

  the case identifier is recorded on every exit path
  declared output_contract fields are echoed (case-carried values pass through,
  audit-derived keys are filled by the audit, the rest are null with a limits note)
  a refusal (undetermined) still writes a result file and keeps the contract
  a rerun with an unchanged spec is byte-identical (the audit is deterministic)
  hostile inputs (section as a list, non-object spec) refuse instead of crashing

    python bench_contract.py
"""
from __future__ import annotations

import copy
import json
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import secrun  # noqa: E402

SCRIPTS = Path(__file__).resolve().parent

CHAPTERS = [
    {"number": 1, "title": "intro", "outline_id": "O1", "argument_element": "question",
     "definitions": [{"term": "uptake rate", "text": "rate of uptake"}],
     "claims": [{"text": "coating raises uptake", "reference": "doe2020"}],
     "conclusions": [{"statement": "coating raises uptake rate", "direction": "increases"}],
     "changelog": ["v1 drafted"]},
    {"number": 2, "title": "methods", "outline_id": "O2", "argument_element": "method",
     "changelog": ["v1 drafted"]},
    {"number": 3, "title": "results", "outline_id": "O3", "argument_element": "result",
     "figure_refs": [1], "changelog": ["v1 drafted"]},
    {"number": 4, "title": "discussion", "outline_id": "O4", "argument_element": "discussion",
     "conclusions": [{"statement": "coating raises uptake rate", "direction": "increases"}],
     "changelog": ["v1 drafted"]},
    {"number": 5, "title": "limits", "outline_id": "O5", "argument_element": "limitation",
     "changelog": ["v1 drafted"]},
]

DELIVERABLE = {"format": "per-chapter editable working chapters with change records",
               "carries": ["outline mapping", "terminology table", "changelog per chapter"]}

SPEC = {
    "case_id": "demo-longdoc-001",
    "section": "longdoc",
    "outline": [
        {"id": "O1", "title": "intro", "argument_element": "question"},
        {"id": "O2", "title": "methods", "argument_element": "method"},
        {"id": "O3", "title": "results", "argument_element": "result"},
        {"id": "O4", "title": "discussion", "argument_element": "discussion"},
        {"id": "O5", "title": "limits", "argument_element": "limitation"},
    ],
    "front_matter": {"toc": ["intro", "methods", "results", "discussion", "limits"],
                     "figure_list": ["Fig 1"], "reference_section": "yes", "appendix": "yes"},
    "terminology": [{"preferred": "uptake rate", "chapter": "1"}],
    "symbols": [{"symbol": "r", "meaning": "rate"}],
    "references": [{"key": "doe2020", "title": "coating raises uptake", "year": 2020,
                    "topic": "coating raises uptake"}],
    "figures": [{"number": 1, "caption": "uptake curves"}],
    "chapters": CHAPTERS,
    "working_chapters": DELIVERABLE,
    "output_contract": {
        "case_id": "echo of the input identifier",
        "status": "audited run status",
        "section": "audited section",
        "working_chapters": "the deliverable, passed through from the spec",
        "findings": "audit findings",
        "severity_counts": "finding counts by severity",
    },
}


def _run(tmp: Path, name: str, spec, extra=()) -> tuple[dict, int, Path]:
    out = tmp / name
    spec_path = tmp / f"{name}.json"
    spec_path.write_text(json.dumps(spec, ensure_ascii=False), encoding="utf-8")
    proc = subprocess.run([sys.executable, str(SCRIPTS / "secrun.py"),
                           "--spec", str(spec_path), "--out", str(out), *extra],
                          capture_output=True, text=True, timeout=120)
    result_path = out / "result.json"
    result = json.loads(result_path.read_text(encoding="utf-8")) if result_path.exists() else {}
    return result, proc.returncode, result_path


def main() -> int:
    rows: list[dict] = []

    def check(name: str, ok: bool, detail: str = "") -> None:
        rows.append({"scenario": name, "pass": bool(ok), "detail": detail})
        print(f"{'PASS' if ok else 'FAIL'}  {name:<30} {detail}")

    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)

        # 1. clean run: contract echoed, case_id recorded, exit 0
        r, code, _ = _run(tmp, "clean", SPEC)
        oc = r.get("output_contract") or {}
        check("clean_exit_0", code == 0 and r.get("status") == "clean", f"exit={code}")
        check("case_id_recorded", r.get("case_id") == "demo-longdoc-001")
        check("contract_all_fields",
              set(oc.keys()) == set(SPEC["output_contract"].keys()),
              f"echoed={sorted(oc.keys())}")
        check("passthrough_untouched", oc.get("working_chapters") == DELIVERABLE)
        check("derived_filled_by_audit",
              oc.get("status") == "clean" and oc.get("section") == "longdoc"
              and oc.get("findings") == [])
        check("no_null_contract_fields",
              all(v is not None for v in oc.values()),
              "no field left null on the happy path")

        # 2. determinism: same spec twice -> byte-identical result
        r1, _, p1 = _run(tmp, "det_a", SPEC)
        r2, _, p2 = _run(tmp, "det_b", SPEC)
        check("rerun_byte_identical", p1.read_bytes() == p2.read_bytes())

        # 3. CLI --case-id overrides and is recorded on a refusal path too
        bad = {"case_id": "from-spec", "section": "not-a-section",
               "output_contract": {"status": "audited run status"}}
        r, code, _ = _run(tmp, "unknown_section", bad, ["--case-id", "cli-override"])
        check("unknown_section_exit_5", code == 5 and r.get("status") == "undetermined",
              f"exit={code}")
        check("case_id_cli_wins", r.get("case_id") == "cli-override")
        oc = r.get("output_contract") or {}
        check("refusal_keeps_contract_nulls",
              oc.get("status") is None and any("not derivable" in l for l in r.get("limits", [])))

        # 4. hostile inputs refuse, never crash
        cases = [
            ("bad_json", None, 5),
            ("non_object", [1, 2, 3], 5),
            ("no_section", {"chapters": []}, 5),
            ("section_is_list", {"section": ["longdoc"]}, 5),
            ("empty_object", {}, 5),
        ]
        for name, payload, want in cases:
            path = tmp / f"{name}.json"
            path.write_text("{ this is not json" if payload is None
                            else json.dumps(payload, ensure_ascii=False), encoding="utf-8")
            out = tmp / f"out_{name}"
            proc = subprocess.run([sys.executable, str(SCRIPTS / "secrun.py"),
                                   "--spec", str(path), "--out", str(out)],
                                  capture_output=True, text=True, timeout=120)
            wrote = (out / "result.json").exists()
            check(f"hostile_{name}",
                  proc.returncode == want and wrote and "Traceback" not in proc.stderr,
                  f"exit={proc.returncode} wrote={wrote}")

        # 5. missing spec file refuses with the usual exit
        proc = subprocess.run([sys.executable, str(SCRIPTS / "secrun.py"),
                               "--spec", str(tmp / "nope.json"),
                               "--out", str(tmp / "out_missing")],
                              capture_output=True, text=True, timeout=120)
        check("hostile_missing_file",
              proc.returncode == 5 and (tmp / "out_missing" / "result.json").exists()
              and "Traceback" not in proc.stderr, f"exit={proc.returncode}")

        # 6. non-object output_contract is reported in limits, run still completes
        spec_nc = copy.deepcopy(SPEC)
        spec_nc["output_contract"] = ["status", "working_chapters"]
        r, code, _ = _run(tmp, "contract_list", spec_nc)
        check("contract_not_object_reported",
              code == 0 and any("output_contract is not an object" in l
                                for l in r.get("limits", [])))

    passed = sum(1 for r in rows if r["pass"])
    (SCRIPTS / "report_contract.json").write_text(
        json.dumps({"schema_version": "contract-bench/v1", "scenarios": rows,
                    "totals": {"passed": passed, "of": len(rows)}},
                   ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n{passed}/{len(rows)} pass")
    return 0 if passed == len(rows) else 1


if __name__ == "__main__":
    raise SystemExit(main())
