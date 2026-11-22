"""Benchmark for the multi-route merge tool.

Each scenario feeds route result.json records through merge_results.merge_results()
(the pure merger) or, for the refusal paths, merge_paths() over real temp files,
and checks the merged deliverable: the strictest status, attributed findings, a
recomputed severity sheet, the case_id gate, and the output_contract union.

    python bench_merge.py
"""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import merge_results as M  # noqa: E402


def route(label, status, rules, case_id="a2c6f23b-case1", contract=None,
          checked=None, limits=None, deliverables=None, section=None):
    data = {"schema_version": "secrun/v1", "section": section or label,
            "status": status,
            "findings": [{"rule": r, "severity": "high"} for r in rules],
            "severity_counts": {"high": len(rules)},
            "checked": checked or {"items": 3},
            "limits": limits or [],
            "case_id": case_id}
    if contract:
        data.update(contract)
    if deliverables:
        data["deliverables"] = list(deliverables)
    return {"label": label, "data": data}


def clean_route(label="draft", **kw):
    return route(label, "clean", [], **kw)


SCEN = [
    ("clean_two_routes",
     lambda: M.merge_results([clean_route("draft"), clean_route("format")]),
     lambda r: (r["status"] == "clean" and r["findings"] == []
                and r["severity_counts"] == {}
                and r["sections"] == ["draft", "format"])),

    ("status_strictest",
     lambda: M.merge_results([clean_route("draft"), route("format", "blocked",
                                                          ["fmt.unit_lost"])]),
     lambda r: (r["status"] == "blocked" and r["severity_counts"] == {"high": 1})),

    ("undetermined_dominates",
     lambda: M.merge_results([route("draft", "blocked", ["pd.uncited_claim"]),
                              {"label": "format", "data": {"status": "undetermined",
                                                           "findings": [],
                                                           "severity_counts": {}}}]
                             ),
     lambda r: r["status"] == "undetermined"),

    ("findings_attributed",
     lambda: M.merge_results([route("draft", "blocked", ["pd.value_not_in_materials"]),
                              route("format", "blocked", ["fmt.unit_lost"])]),
     lambda r: ({f["rule"] for f in r["findings"]} ==
                {"pd.value_not_in_materials", "fmt.unit_lost"}
                and {f["route"] for f in r["findings"]} == {"draft", "format"}
                and r["severity_counts"] == {"high": 2})),

    ("case_id_mismatch",
     lambda: M.merge_results([clean_route("draft", case_id="case-A"),
                              clean_route("format", case_id="case-B")]),
     lambda r: ("merge.case_id_mismatch" in
                {f["rule"] for f in r["findings"]} and r["status"] == "blocked")),

    ("contract_union_nonnull_wins",
     lambda: M.merge_results([
         route("draft", "clean", [], contract={"audit_report": [{"id": "F01"}],
                                                "figures_pdf": None}),
         route("format", "clean", [], contract={"audit_report": None,
                                                "figures_pdf": None,
                                                "change_summary": "2 edits"})]),
     lambda r: (r["audit_report"] == [{"id": "F01"}]
                and r["change_summary"] == "2 edits"
                and r["figures_pdf"] is None
                and any("'figures_pdf'" in lim for lim in r["limits"]))),

    ("contract_conflict_flagged",
     lambda: M.merge_results([
         route("draft", "clean", [], contract={"audit_report": [{"id": "A"}]}),
         route("format", "clean", [], contract={"audit_report": [{"id": "B"}]})]),
     lambda r: ("merge.field_conflict" in {f["rule"] for f in r["findings"]}
                and r["audit_report"] == [{"id": "A"}])),

    ("deliverables_union",
     lambda: M.merge_results([
         route("draft", "clean", [], deliverables=["manuscript.md", "figures.png"]),
         route("format", "clean", [], deliverables=["manuscript.md", "manuscript.pdf"])]),
     lambda r: sorted(r["deliverables"]) ==
     ["figures.png", "manuscript.md", "manuscript.pdf"]),

    ("checked_per_route",
     lambda: M.merge_results([
         clean_route("draft", checked={"items": 12}),
         clean_route("format", checked={"headings": 4})]),
     lambda r: (r["checked"]["routes"]["draft"] == {"items": 12}
                and r["checked"]["routes"]["format"] == {"headings": 4})),
]


def main() -> int:
    rows = []
    for name, build, check in SCEN:
        try:
            r = build()
            ok = check(r)
        except Exception as exc:
            r, ok = {"error": str(exc)}, False
        rows.append({"scenario": name, "pass": ok})
        print(("PASS" if ok else "FAIL") + "  " + name.ljust(30))

    # refusal paths through the real CLI entry point on temp files
    with tempfile.TemporaryDirectory() as td:
        t = Path(td)
        (t / "good").mkdir(parents=True)
        (t / "bad").mkdir(parents=True)
        (t / "good" / "result.json").write_text(json.dumps(
            clean_route("good")["data"]), encoding="utf-8")
        (t / "bad" / "result.json").write_text("{not json", encoding="utf-8")
        out = t / "merged" / "result.json"

        r = M.merge_paths([t / "good" / "result.json", t / "bad" / "result.json"], out)
        ok = (r["status"] == "undetermined"
              and "audit.merge_refused" in {f["rule"] for f in r["findings"]}
              and out.exists()
              and json.loads(out.read_text(encoding="utf-8"))["status"] == "undetermined")
        rows.append({"scenario": "unreadable_input_refused", "pass": ok})
        print(("PASS" if ok else "FAIL") + "  " + "unreadable_input_refused".ljust(30))

        r = M.merge_paths([], t / "none" / "result.json")
        ok = (r["status"] == "undetermined"
              and (t / "none" / "result.json").exists())
        rows.append({"scenario": "no_inputs_refused", "pass": ok})
        print(("PASS" if ok else "FAIL") + "  " + "no_inputs_refused".ljust(30))

        r = M.merge_paths([t / "good" / "result.json"], t / "single" / "result.json")
        ok = (r["status"] == "clean" and r["sections"] == ["good"])
        rows.append({"scenario": "single_route_identity", "pass": ok})
        print(("PASS" if ok else "FAIL") + "  " + "single_route_identity".ljust(30))

    passed = sum(1 for r in rows if r["pass"])
    (Path(__file__).resolve().parent / "report_merge.json").write_text(
        json.dumps({"schema_version": "merge-bench/v1", "scenarios": rows,
                    "totals": {"passed": passed, "of": len(rows)}},
                   ensure_ascii=False, indent=2), encoding="utf-8")
    print()
    print(f"{passed}/{len(rows)} pass")
    return 0 if passed == len(rows) else 1


if __name__ == "__main__":
    raise SystemExit(main())
