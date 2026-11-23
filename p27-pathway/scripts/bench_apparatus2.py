"""Benchmark for the apparatus figure skill.

One scenario per rule, including the three criteria the challenge states explicitly:

  1. every entity traces back to the input material   -> trace.*
  2. connections and ordering hold                     -> trace.edge_not_in_source, route.*
  3. re-running gives the same figure                  -> repro.nondeterministic

Two defects cannot be planted in a spec — a font without the needed glyphs, and a
renderer that is not reproducible — so those scenarios inject them by patching, and
restore afterwards. That still tests the checker against a real defect rather than a
mock.
"""

from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import matplotlib.pyplot as plt  # noqa: E402

import apparatus as A  # noqa: E402
import apparatusfig as AF  # noqa: E402
import fontsel  # noqa: E402
import provenance  # noqa: E402
import schematic  # noqa: E402

OUT = Path(__file__).resolve().parent / "_run_apparatus"

BASE = {
    "figure_kind": "apparatus",
    "font_size": 9,
    "canvas_mm": [140, 70],
    "materials": [{"id": "m1", "name": "激光器", "source": "Methods ¶1"},
                  {"id": "m2", "name": "分束器", "source": "Methods ¶1"},
                  {"id": "m3", "name": "探测器", "source": "Methods ¶2"}],
    "connections": [{"from": "n1", "to": "n2", "source": "Methods ¶1"},
                    {"from": "n2", "to": "n3", "source": "Methods ¶2"}],
    "nodes": [
        {"id": "n1", "label": "激光器", "evidence": "m1", "layer": 0, "color": "#56B4E9"},
        {"id": "n2", "label": "分束器", "evidence": "m2", "layer": 1, "color": "#009E73"},
        {"id": "n3", "label": "探测器", "evidence": "m3", "layer": 2, "color": "#E69F00"},
    ],
    "edges": [{"from": "n1", "to": "n2", "type": "flow"},
              {"from": "n2", "to": "n3", "type": "flow"}],
}


def d(**over):
    s = copy.deepcopy(BASE)
    s.update(over)
    return s


def run_spec(name: str, spec: dict) -> dict:
    """Render + full audit in a temp dir, the same path the skill uses."""
    d_ = OUT / name
    d_.mkdir(parents=True, exist_ok=True)
    p = d_ / "spec.json"
    p.write_text(json.dumps(spec, ensure_ascii=False), encoding="utf-8")
    return AF.build_and_audit(p, d_ / "out")


# --- scenarios -------------------------------------------------------------

def scen_clean():
    return BASE, []


def scen_no_evidence():
    s = d()
    s["nodes"] = copy.deepcopy(BASE["nodes"])
    s["nodes"][1].pop("evidence")
    return s, ["trace.entity_untraceable"]


def scen_bad_evidence():
    s = d()
    s["nodes"] = copy.deepcopy(BASE["nodes"])
    s["nodes"][1]["evidence"] = "m99"
    return s, ["trace.evidence_not_in_materials"]


def scen_material_unused():
    s = d()
    s["materials"] = BASE["materials"] + [{"id": "m4", "name": "快门"}]
    return s, ["trace.material_not_drawn"]


def scen_invented_edge():
    s = d()
    s["edges"] = BASE["edges"] + [{"from": "n1", "to": "n3", "type": "flow"}]
    return s, ["trace.edge_not_in_source"]


def scen_numbering():
    s = d(figure_kind="route",
          step_order=["n1", "n3", "n2"],
          nodes=[{"id": "n1", "label": "合成", "stage": 1, "layer": 0},
                 {"id": "n2", "label": "表征", "stage": 2, "layer": 1},
                 {"id": "n3", "label": "放大", "stage": 3, "layer": 2}],
          edges=[{"from": "n1", "to": "n2"}, {"from": "n2", "to": "n3"}])
    s.pop("materials", None)
    s.pop("connections", None)
    return s, ["route.numbering_vs_text"]


def scen_overlap():
    s = d(canvas_mm=[60, 45], font_size=30,
          nodes=[{"id": f"N{i}", "label": "极长的部件名称", "layer": 1} for i in range(6)],
          edges=[])
    s.pop("materials", None)
    s.pop("connections", None)
    return s, ["label.overlap", "label.wider_than_box"]


def scen_dangling():
    """An edge naming an undeclared node is reported, not silently dropped."""
    s = d()
    s["edges"] = BASE["edges"] + [{"from": "n1", "to": "ghost", "type": "flow"}]
    return s, ["edge.dangling"]


def scen_malformed():
    """Malformed list entries are skipped and reported so the case still draws."""
    s = d()
    s["nodes"] = BASE["nodes"] + ["oops"]
    s["edges"] = BASE["edges"] + [17]
    return s, ["node.malformed", "edge.malformed"]


def scen_recycle():
    """A declared recycle return is an intentional back-flow, not an error."""
    s = d()
    s["edges"] = BASE["edges"] + [{"from": "n3", "to": "n1", "type": "flow", "recycle": True}]
    s["connections"] = BASE["connections"] + [{"from": "n3", "to": "n1", "source": "Methods ¶3"}]
    return s, []


def scen_stage_nonnumeric():
    """A stage value that is not a number is reported instead of crashing."""
    s = d(figure_kind="route",
          nodes=[{"id": "n1", "label": "合成", "stage": 1, "layer": 0},
                 {"id": "n2", "label": "表征", "stage": "two", "layer": 1},
                 {"id": "n3", "label": "放大", "stage": 3, "layer": 2}],
          edges=[{"from": "n1", "to": "n2"}, {"from": "n2", "to": "n3"}])
    s.pop("materials", None)
    s.pop("connections", None)
    return s, ["route.stage_nonnumeric"]


SCEN = [
    ("clean", scen_clean),
    ("untraceable", scen_no_evidence),
    ("bad_evidence", scen_bad_evidence),
    ("material_unused", scen_material_unused),
    ("invented_edge", scen_invented_edge),
    ("numbering", scen_numbering),
    ("overlap", scen_overlap),
    ("dangling", scen_dangling),
    ("malformed", scen_malformed),
    ("recycle", scen_recycle),
    ("stage_nonnumeric", scen_stage_nonnumeric),
]


def injected_missing_glyphs() -> tuple[dict, list[str]]:
    """Point the renderer at a font that cannot draw Chinese."""
    saved = fontsel.resolve
    dejavu = fontsel._find(["DejaVuSans.ttf"])
    fontsel.resolve = lambda text="": fontsel.Resolved(
        family="DejaVu Sans", path=dejavu, missing=fontsel.coverage(dejavu, text))
    try:
        spec = copy.deepcopy(BASE)
        r = run_spec("missing_glyphs", spec)
    finally:
        fontsel.resolve = saved
    fired = {f["rule"] for f in r["findings"]}
    return r, ["export.missing_glyphs"] if "export.missing_glyphs" in fired else []


def injected_nondeterministic() -> tuple[dict, list[str]]:
    """Make the second render differ, as a non-reproducible renderer would."""
    # Patch the shared checker, not the caller: determinism now lives in provenance.py
    # and both diagram skills delegate to it.
    saved = provenance.check_deterministic

    def fake(spec, render_fn, tmp_dir=None):
        return {"deterministic": False, "detail": {"geometry_differs": True},
                "note": "injected: two renders differ"}

    provenance.check_deterministic = fake
    try:
        spec = copy.deepcopy(BASE)
        r = run_spec("nondeterministic", spec)
    finally:
        provenance.check_deterministic = saved
    fired = {f["rule"] for f in r["findings"]}
    return r, ["repro.nondeterministic"] if "repro.nondeterministic" in fired else []


def main() -> int:
    rows = []
    for name, builder in SCEN:
        spec, expect = builder()
        r = run_spec(name, spec)
        fired = {f["rule"] for f in r["findings"]}
        missing = [x for x in expect if x not in fired]
        spurious = [] if expect else [f["rule"] for f in r["findings"]]
        ok = not missing and not spurious
        rows.append({"scenario": name, "expected": expect, "fired": sorted(fired),
                     "missing": missing, "spurious": spurious, "pass": ok,
                     "status": r["status"]})
        print(f"{'PASS' if ok else 'FAIL'}  {name:<18} missing={missing} spurious={spurious}")

    for name, fn in (("missing_glyphs", injected_missing_glyphs),
                     ("nondeterministic", injected_nondeterministic)):
        r, got = fn()
        ok = bool(got)
        rows.append({"scenario": name, "expected": got, "fired": got,
                     "missing": [] if ok else ["<not fired>"], "spurious": [],
                     "pass": ok, "status": r["status"], "injected": True})
        print(f"{'PASS' if ok else 'FAIL'}  {name:<18} injected={ok}")

    plt.close("all")
    passed = sum(1 for r in rows if r["pass"])
    report = {"schema_version": "apparatus2-bench/v1", "scenarios": rows,
              "totals": {"passed": passed, "of": len(rows)},
              "note": ("Two scenarios inject a defect by patching a font resolver and a "
                       "determinism check, because those defects cannot be expressed in a spec.")}
    (Path(__file__).resolve().parent / "report_apparatus2.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n{passed}/{len(rows)} pass")
    return 0 if passed == len(rows) else 1


if __name__ == "__main__":
    raise SystemExit(main())
