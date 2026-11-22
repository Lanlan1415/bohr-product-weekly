"""Benchmark for the apparatus / roadmap audit.

    python bench_apparatus.py
"""

from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import apparatus as A  # noqa: E402

APPARATUS = {
    "figure_kind": "apparatus",
    "components": ["Laser", "Beam splitter", "Sample", "Detector"],
    "nodes": [
        {"id": "n1", "label": "Laser", "layer": 0},
        {"id": "n2", "label": "Beam splitter", "layer": 1},
        {"id": "n3", "label": "Sample", "layer": 2},
        {"id": "n4", "label": "Detector", "layer": 3},
    ],
    "edges": [
        {"from": "n1", "to": "n2"}, {"from": "n2", "to": "n3"}, {"from": "n3", "to": "n4"},
        {"from": "n2", "to": "n4", "type": "flow"},
    ],
}

ROUTE = {
    "figure_kind": "route",
    "nodes": [
        {"id": "s1", "label": "Synthesis", "stage": 1, "layer": 0},
        {"id": "s2", "label": "Characterisation", "stage": 2, "layer": 1},
        {"id": "d1", "label": "Meets spec?", "stage": 3, "layer": 2, "kind": "decision"},
        {"id": "s4", "label": "Scale-up", "stage": 4, "layer": 3},
    ],
    "edges": [
        {"from": "s1", "to": "s2"}, {"from": "s2", "to": "d1"},
        {"from": "d1", "to": "s4", "type": "activate"},
        {"from": "d1", "to": "s2", "type": "bind"},
    ],
}


def scen_clean_apparatus():
    return copy.deepcopy(APPARATUS), []


def scen_legend_unmatched():
    """A legend entry no drawn label carries: a phantom part."""
    s = copy.deepcopy(APPARATUS)
    s["legend"] = ["Laser", "Ghost chamber"]
    return s, ["apparatus.legend_entry_unmatched"]


def scen_legend_clean():
    """Every legend entry matches a drawn label — must stay silent."""
    s = copy.deepcopy(APPARATUS)
    s["legend"] = [n["label"] for n in s["nodes"]]
    return s, []


def scen_component_missing():
    s = copy.deepcopy(APPARATUS)
    s["components"] = s["components"] + ["Mirror"]
    return s, ["apparatus.component_missing"]


def scen_indistinguishable():
    s = copy.deepcopy(APPARATUS)
    s["nodes"].append({"id": "n5", "label": "Laser", "layer": 1})
    s["edges"].append({"from": "n1", "to": "n5"})
    return s, ["apparatus.indistinguishable_components"]


def scen_orphan():
    s = copy.deepcopy(APPARATUS)
    s["nodes"].append({"id": "n6", "label": "Spare", "layer": 2})
    return s, ["apparatus.orphan_component"]


def scen_clean_route():
    return copy.deepcopy(ROUTE), []


def scen_stage_duplicate():
    """Stages 1,2,3,2: a repeat with no missing number, so only the duplicate fires."""
    s = copy.deepcopy(ROUTE)
    s["nodes"][3]["stage"] = 2
    return s, ["route.stage_duplicate"]


def scen_stage_gap():
    s = copy.deepcopy(ROUTE)
    s["nodes"][2]["stage"] = 8
    return s, ["route.stage_gap"]


def scen_decision_without_branches():
    s = copy.deepcopy(ROUTE)
    s["edges"] = [e for e in s["edges"] if e.get("type") != "bind"]
    return s, ["route.decision_without_branches"]


def scen_no_exit():
    s = copy.deepcopy(ROUTE)
    # Wire the last stage back to the first, so nothing terminates.
    s["edges"].append({"from": "s4", "to": "s1", "type": "bind"})
    return s, ["route.no_exit", "route.no_entry"]


SCENARIOS = [
    ("clean_apparatus", scen_clean_apparatus),
    ("legend_unmatched", scen_legend_unmatched),
    ("legend_clean", scen_legend_clean),
    ("component_missing", scen_component_missing),
    ("indistinguishable", scen_indistinguishable),
    ("orphan", scen_orphan),
    ("clean_route", scen_clean_route),
    ("stage_duplicate", scen_stage_duplicate),
    ("stage_gap", scen_stage_gap),
    ("decision_no_branches", scen_decision_without_branches),
    ("no_exit", scen_no_exit),
]


def main() -> int:
    rows = []
    for name, builder in SCENARIOS:
        spec, expect = builder()
        r = A.audit_apparatus(spec)
        fired = {f["rule"] for f in r["findings"]}
        missing = [x for x in expect if x not in fired]
        spurious = []
        if not expect:                  # clean baseline must stay silent
            spurious = [f["rule"] for f in r["findings"] if f["severity"] in ("high", "medium")]
        rows.append({"scenario": name, "expected": expect, "fired": sorted(fired),
                     "missing": missing, "spurious": spurious,
                     "pass": not missing and not spurious})

    passed = sum(1 for r in rows if r["pass"])
    report = {"schema_version": "apparatus-bench/v1", "scenarios": rows,
              "totals": {"passed": passed, "of": len(rows)},
              "note": "One planted defect per scenario; clean baselines must stay silent."}
    (Path(__file__).resolve().parent / "report_apparatus.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    for r in rows:
        print(f"{'PASS' if r['pass'] else 'FAIL'}  {r['scenario']:<24}"
              f"expected={r['expected']} missing={r['missing']} spurious={r['spurious']}")
    print(f"\n{passed}/{len(rows)} scenarios pass")
    return 0 if passed == len(rows) else 1


if __name__ == "__main__":
    raise SystemExit(main())
