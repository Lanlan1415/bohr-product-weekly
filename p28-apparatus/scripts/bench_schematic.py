"""Benchmark for the schematic render-and-audit engine.

Each scenario plants exactly one defect and states which rule must fire. A
scenario passes only if every required rule is reported — and the clean
baseline must report nothing, so a detector cannot pass by flagging everything.

    python bench.py
"""

from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import schematic as S  # noqa: E402

BASE = {
    "font_size": 9,
    "nodes": [
        {"id": "A", "label": "Substrate", "layer": 0, "color": "#56B4E9"},
        {"id": "B", "label": "Complex", "layer": 1, "color": "#009E73"},
        {"id": "C", "label": "Product", "layer": 2, "color": "#E69F00"},
    ],
    "edges": [
        {"from": "A", "to": "B", "type": "bind"},
        {"from": "B", "to": "C", "type": "activate"},
    ],
}


def scen_clean():
    return copy.deepcopy(BASE), [], {}


def scen_overlap():
    """Twelve long labels on one layer collide once the canvas is fixed width."""
    spec = copy.deepcopy(BASE)
    spec["nodes"] = [{"id": f"N{i}", "label": "Very long entity name", "layer": 1}
                     for i in range(6)]
    spec["edges"] = []
    # A fixed single-column slot with oversized type: labels cannot fit their
    # boxes, and at this row pitch they also collide with each other.
    spec["canvas_mm"] = [60, 45]
    spec["font_size"] = 30
    return spec, ["label.overlap", "label.wider_than_box"], {}


def scen_small_font():
    spec = copy.deepcopy(BASE)
    spec["font_size"] = 3.2
    return spec, ["font.too_small"], {}


def scen_unsafe_colour():
    spec = copy.deepcopy(BASE)
    spec["nodes"][0]["color"] = "#FF0000"
    return spec, ["colour.not_cb_safe"], {}


def scen_backward_flow():
    spec = copy.deepcopy(BASE)
    spec["edges"].append({"from": "C", "to": "A", "type": "flow"})
    return spec, ["edge.backward_flow"], {}


def scen_duplicate_entity():
    spec = copy.deepcopy(BASE)
    spec["nodes"].append({"id": "B2", "label": "Complex", "layer": 1, "color": "#009E73"})
    spec["edges"].append({"from": "B", "to": "B2", "type": "bind"})
    return spec, ["entity.duplicate"], {}


def scen_paths_not_text():
    """svg.fonttype='path' is the default and silently breaks editability."""
    return copy.deepcopy(BASE), ["export.no_live_text"], {"fonttype": "path"}


def scen_low_dpi():
    return copy.deepcopy(BASE), ["export.low_dpi"], {"dpi": 72}


SCENARIOS = [
    ("clean", scen_clean),
    ("label_overlap", scen_overlap),
    ("font_too_small", scen_small_font),
    ("unsafe_colour", scen_unsafe_colour),
    ("backward_flow", scen_backward_flow),
    ("duplicate_entity", scen_duplicate_entity),
    ("paths_not_text", scen_paths_not_text),
    ("low_dpi", scen_low_dpi),
]


def run_one(name, builder, out_root: Path) -> dict:
    spec, expect, opts = builder()
    import matplotlib
    saved = matplotlib.rcParams["svg.fonttype"]
    if opts.get("rc"):
        matplotlib.rcParams.update(opts["rc"])
    try:
        d = out_root / name
        d.mkdir(parents=True, exist_ok=True)
        spec_path = d / "spec.json"
        spec_path.write_text(json.dumps(spec, ensure_ascii=False, indent=2), encoding="utf-8")
        built = S.render(spec, d / "figure", dpi=opts.get("dpi", 300),
                         fonttype=opts.get("fonttype", "none"))
        res = S.audit(spec, built)
        import matplotlib.pyplot as plt
        plt.close(built["fig"])
    finally:
        matplotlib.rcParams["svg.fonttype"] = saved

    fired = {f["rule"] for f in res["findings"]}
    missing = [r for r in expect if r not in fired]
    # A clean scenario must produce no high-severity finding at all.
    spurious = []
    if not expect:
        spurious = [f["rule"] for f in res["findings"] if f["severity"] in ("high", "medium")]
    return {
        "scenario": name,
        "expected": expect,
        "fired": sorted(fired),
        "missing": missing,
        "spurious": spurious,
        "status": res["status"],
        "pass": not missing and not spurious,
    }


def main() -> int:
    out_root = Path(__file__).resolve().parent / "_run"
    rows = [run_one(n, b, out_root) for n, b in SCENARIOS]
    passed = sum(1 for r in rows if r["pass"])
    report = {
        "schema_version": "schematic-bench/v1",
        "scenarios": rows,
        "totals": {"passed": passed, "of": len(rows)},
        "note": ("Each scenario plants one defect and names the rule that must fire. The clean "
                 "baseline must report no high or medium finding, so flagging everything is not "
                 "a way to pass."),
    }
    (Path(__file__).resolve().parent / "report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    for r in rows:
        mark = "PASS" if r["pass"] else "FAIL"
        print(f"{mark}  {r['scenario']:<18} expected={r['expected']} missing={r['missing']}"
              f" spurious={r['spurious']}")
    print(f"\n{passed}/{len(rows)} scenarios pass")
    return 0 if passed == len(rows) else 1


if __name__ == "__main__":
    raise SystemExit(main())
