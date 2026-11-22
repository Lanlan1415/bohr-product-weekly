"""Benchmark for the case contract: case_id + output_contract passthrough, refusals.

The Harbor runtime contract requires every case result.json to keep case_id and
every field the case's output_contract names. This bench pins that behaviour and
the refusal ladder: an unrunnable input is an exit-5 undetermined result.json,
never a traceback, and a refusal never runs the contract echo.

    python bench_contract.py
"""

from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import deckbuild  # noqa: E402

OUT = Path(__file__).resolve().parent / "_run_contract"

CLEAN = {
    "case_id": "demo-case-320",
    "section": "talk_org",
    "min_font_pt": 14,
    "spacing": {"title": 32, "body": 20},
    "goal": {"objective": "让评审认可方法的新颖性", "audience": "评审", "minutes": 6},
    "slides": [
        {"title": "吸收速率是瓶颈", "claim": "瓶颈在于表面积", "strength": "moderate",
         "evidence": "Fig. 3b, p.7", "notes": "先立瓶颈。"},
        {"title": "涂层使速率提高 3 倍", "claim": "涂层使吸收速率提高三倍", "strength": "strong",
         "evidence": "Fig. 3b, p.7", "notes": "核心结果。"}
    ],
    "output_contract": {"deck_file": "editable deck file",
                        "evidence_map": "per-page evidence mapping",
                        "presenter_notes": "the speaker-notes export",
                        "qa_ledger": "prepared questions and answer pages"},
    "presenter_notes": "全场备注要点见每页 notes；口径与页面主张一致。",
}


def write_spec(name: str, spec) -> Path:
    p = OUT / name
    p.mkdir(parents=True, exist_ok=True)
    body = spec if isinstance(spec, str) else json.dumps(spec, ensure_ascii=False)
    (p / "spec.json").write_text(body, encoding="utf-8")
    return p / "spec.json"


def scen_case_id_echo():
    """case_id and contract fields land in result.json; carried values pass through."""
    r = deckbuild.build_and_audit(write_spec("echo", copy.deepcopy(CLEAN)), OUT / "echo_out")
    problems = []
    if r.get("case_id") != "demo-case-320":
        problems.append("case_id missing")
    if r.get("presenter_notes") != CLEAN["presenter_notes"]:
        problems.append("carried contract value did not pass through verbatim")
    if not isinstance(r.get("evidence_map"), list) or len(r["evidence_map"]) != 2:
        problems.append("evidence_map not derived")
    if r.get("qa_ledger") is not None:
        problems.append("unsupplyable field should be null, not invented")
    if not any("qa_ledger" in x for x in r.get("limits", [])):
        problems.append("unsupplyable contract field not named in limits")
    if r.get("output_contract_fields") != list(CLEAN["output_contract"]):
        problems.append("contract field list not recorded")
    return problems


def scen_field_kept():
    """A contract field the result already carries is kept, not overwritten by null."""
    spec = copy.deepcopy(CLEAN)
    spec["output_contract"] = {"deck": "the written deck", "evidence_map": "the mapping"}
    r = deckbuild.build_and_audit(write_spec("kept", spec), OUT / "kept_out")
    problems = []
    if not isinstance(r.get("deck"), dict) or "path" not in r["deck"]:
        problems.append("deck block was clobbered by the echo")
    if r.get("limits") and any("evidence_map" in x for x in r["limits"]):
        problems.append("derived field wrongly reported as underivable")
    return problems


def scen_bad_json():
    """Unparseable JSON is an undetermined refusal with exit 5, not a traceback."""
    spec_path = write_spec("badjson", '{"slides": [oops')
    problems = []
    code = deckbuild.main(["--spec", str(spec_path), "--out", str(OUT / "badjson_out")])
    if code != 5:
        problems.append(f"exit code {code}, expected 5")
    r = json.loads((OUT / "badjson_out" / "result.json").read_text(encoding="utf-8"))
    if r.get("status") != "undetermined":
        problems.append("status not undetermined")
    if not any(f.get("rule") == "audit.refused" for f in r.get("findings", [])):
        problems.append("refusal finding missing")
    if r.get("output_contract_fields") is not None:
        problems.append("refusal must not run the contract echo")
    return problems


def scen_not_object():
    """A JSON array is refused as undetermined."""
    spec_path = write_spec("notobject", "[1, 2, 3]")
    r = deckbuild.build_and_audit(spec_path, OUT / "notobject_out")
    problems = []
    if r.get("status") != "undetermined":
        problems.append("status not undetermined")
    if "not an object" not in str(r.get("findings", [{}])[0].get("message", "")):
        problems.append("reason not named")
    return problems


def scen_unknown_section():
    """An unknown section is refused undetermined and still names the case."""
    spec = copy.deepcopy(CLEAN)
    spec["section"] = "slide_vibes"
    spec_path = write_spec("unknown", spec)
    problems = []
    code = deckbuild.main(["--spec", str(spec_path), "--out", str(OUT / "unknown_out")])
    if code != 5:
        problems.append(f"exit code {code}, expected 5")
    r = json.loads((OUT / "unknown_out" / "result.json").read_text(encoding="utf-8"))
    if r.get("case_id") != "demo-case-320":
        problems.append("refused run lost the case_id")
    if r.get("status") != "undetermined":
        problems.append("status not undetermined")
    return problems


def scen_missing_spec_file():
    """A missing spec file is refused undetermined."""
    problems = []
    code = deckbuild.main(["--spec", str(OUT / "nope" / "spec.json"),
                           "--out", str(OUT / "nope_out")])
    if code != 5:
        problems.append(f"exit code {code}, expected 5")
    r = json.loads((OUT / "nope_out" / "result.json").read_text(encoding="utf-8"))
    if r.get("status") != "undetermined":
        problems.append("status not undetermined")
    return problems


def scen_idempotent():
    """Same spec twice: identical findings, severity counts and status."""
    problems = []
    outs = []
    for run in (1, 2):
        r = deckbuild.build_and_audit(write_spec("idem", copy.deepcopy(CLEAN)),
                                      OUT / f"idem_out{run}")
        outs.append(r)
    a, b = outs
    if a.get("status") != b.get("status") or a.get("findings") != b.get("findings"):
        problems.append("re-run changed the verdict")
    if a.get("severity_counts") != b.get("severity_counts"):
        problems.append("severity counts differ between runs")
    if a.get("status") != "clean":
        problems.append(f"clean baseline reported {a.get('status')}: "
                        f"{[f['rule'] for f in a.get('findings', [])]}")
    return problems


SCENARIOS = [
    ("case_id_echo", scen_case_id_echo),
    ("field_kept", scen_field_kept),
    ("bad_json", scen_bad_json),
    ("not_object", scen_not_object),
    ("unknown_section", scen_unknown_section),
    ("missing_spec_file", scen_missing_spec_file),
    ("idempotent", scen_idempotent),
]


def main() -> int:
    rows = []
    for name, fn in SCENARIOS:
        try:
            problems = fn()
        except Exception as exc:
            problems = [f"scenario raised: {exc!r}"]
        rows.append({"scenario": name, "problems": problems, "pass": not problems})
        print(f"{'PASS' if not problems else 'FAIL'}  {name:<20} {problems}")
    passed = sum(1 for r in rows if r["pass"])
    (Path(__file__).resolve().parent / "report_contract.json").write_text(
        json.dumps({"schema_version": "contract-bench/v1", "scenarios": rows,
                    "totals": {"passed": passed, "of": len(rows)}},
                   ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n{passed}/{len(rows)} scenarios pass")
    return 0 if passed == len(rows) else 1


if __name__ == "__main__":
    raise SystemExit(main())
