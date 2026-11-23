"""Benchmark for the graphical-abstract audit.

    python bench_ga.py
"""
from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import graphical_abstract as G  # noqa: E402

BASE = {
    "canvas_mm": [170, 70],
    "size_limit_mm": [180, 80],
    "max_words": 60,
    "core_message": "Coating restores uptake",
    "limitations": ["In vitro only"],
    "result_modality": "quantitative",
    "takeaways": {"problem": "p1", "method": "m1", "finding": "f1", "conclusion": "c1"},
    "reading_order": ["p1", "m1", "f1", "c1"],
    "nodes": [
        {"id": "p1", "label": "Uptake is slow", "layer": 0},
        {"id": "m1", "label": "Porous coating, 42 nm", "layer": 1},
        {"id": "f1", "label": "3x faster uptake", "layer": 2,
         "visual_data": {"kind": "bar", "unit": "uptake (a.u.)",
                         "items": [{"label": "Before", "value": 0.42},
                                   {"label": "Coated", "value": 1.8}]}},
        {"id": "c1", "label": "Coating aids uptake", "layer": 3},
    ],
    "edges": [{"from": "p1", "to": "m1"}, {"from": "m1", "to": "f1"}, {"from": "f1", "to": "c1"}],
}
SOURCE = ["42", "3", "0.42", "1.8"]


def scen_clean():
    return copy.deepcopy(BASE), SOURCE, []


def scen_missing_takeaway():
    s = copy.deepcopy(BASE)
    s["takeaways"].pop("finding")
    return s, SOURCE, ["ga.missing_takeaway"]


def scen_takeaway_not_placed():
    """A declared takeaway whose text appears nowhere on the canvas.

    Note the rule accepts a substring: declaring "Porous coating" against the
    label "Porous coating, 42 nm" correctly counts as placed, so this scenario
    uses wording that is genuinely absent.
    """
    s = copy.deepcopy(BASE)
    s["takeaways"]["method"] = "Electrospun fibre mat"
    return s, SOURCE, ["ga.takeaway_not_placed"]


def scen_number_not_in_source():
    s = copy.deepcopy(BASE)
    s["nodes"][2]["label"] = "10x faster uptake"
    return s, SOURCE, ["ga.value_not_in_source"]


def scen_too_many_words():
    s = copy.deepcopy(BASE)
    s["max_words"] = 5
    return s, SOURCE, ["ga.text_too_long"]


def scen_size_out_of_spec():
    s = copy.deepcopy(BASE)
    s["canvas_mm"] = [240, 120]
    return s, SOURCE, ["ga.size_out_of_spec"]


def scen_unlinked():
    s = copy.deepcopy(BASE)
    s["edges"] = []
    return s, SOURCE, ["ga.takeaway_panels_unlinked"]


def scen_reading_order():
    s = copy.deepcopy(BASE)
    s["nodes"][0]["layer"] = 2
    s["nodes"][2]["layer"] = 0
    return s, SOURCE, ["ga.reading_order"]


def scen_no_source_values():
    return copy.deepcopy(BASE), None, ["ga.source_values_unavailable"]


SCENARIOS = [
    ("clean", scen_clean),
    ("missing_takeaway", scen_missing_takeaway),
    ("takeaway_not_placed", scen_takeaway_not_placed),
    ("number_not_in_source", scen_number_not_in_source),
    ("too_many_words", scen_too_many_words),
    ("size_out_of_spec", scen_size_out_of_spec),
    ("unlinked_takeaways", scen_unlinked),
    ("reading_order", scen_reading_order),
    ("no_source_values", scen_no_source_values),
]


def main() -> int:
    rows = []
    for name, builder in SCENARIOS:
        spec, src, expect = builder()
        r = G.audit_graphical_abstract(spec, src)
        fired = {f["rule"] for f in r["findings"]}
        missing = [x for x in expect if x not in fired]
        spurious = []
        if not expect:
            spurious = [f["rule"] for f in r["findings"] if f["severity"] in ("high", "medium")]
        rows.append({"scenario": name, "expected": expect, "fired": sorted(fired),
                     "missing": missing, "spurious": spurious,
                     "pass": not missing and not spurious})
    passed = sum(1 for r in rows if r["pass"])
    report = {"schema_version": "ga-bench/v1", "scenarios": rows,
              "totals": {"passed": passed, "of": len(rows)},
              "note": "One planted defect per scenario; the clean baseline must stay silent."}
    (Path(__file__).resolve().parent / "report_ga.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    for r in rows:
        print(f"{'PASS' if r['pass'] else 'FAIL'}  {r['scenario']:<22}"
              f"expected={r['expected']} missing={r['missing']} spurious={r['spurious']}")
    print(f"\n{passed}/{len(rows)} scenarios pass")
    return 0 if passed == len(rows) else 1


if __name__ == "__main__":
    raise SystemExit(main())
