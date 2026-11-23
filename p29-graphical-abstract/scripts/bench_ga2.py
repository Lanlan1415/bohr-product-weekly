"""Benchmark for the polished graphical-abstract skill.

Covers the claim rules (the three-part claim, numbers traced to source, text and size
limits) plus the three source-bound criteria and the glyph check that were added in the
polish pass.

Two defects cannot be expressed in a spec — a font without the needed glyphs, and a
renderer that is not reproducible — so those inject them by patching and restore
afterwards.

    python bench_ga2.py
"""

from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import matplotlib.pyplot as plt  # noqa: E402

import fontsel  # noqa: E402
import ga_figure  # noqa: E402
import provenance  # noqa: E402

OUT = Path(__file__).resolve().parent / "_run_ga2"

# A clean abstract: Chinese labels, three declared takeaways, every number in source,
# every panel traced to a material item.
BASE = {
    "canvas_mm": [180, 90],
    "size_limit_mm": [185, 95],
    "max_words": 80,
    "font_size": 8.4,
    "core_message": {"text": "多孔涂层恢复快速吸收", "evidence": "mat3"},
    "source_values": ["42", "3", "0.6", "1.8", "6"],
    "limitations": [{"text": "体外实验；耐久性未评估", "evidence": "mat4"}],
    "result_modality": "quantitative",
    "takeaways": {"problem": "p1", "method": "m1", "finding": "f1", "conclusion": "c1"},
    "reading_order": ["p1", "m1", "f1", "c1"],
    "materials": [{"id": "mat1", "name": "缓慢吸收"},
                  {"id": "mat2", "name": "多孔涂层"},
                  {"id": "mat3", "name": "吸收速率"},
                  {"id": "mat4", "name": "范围与结论"}],
    "legend": ["吸收缓慢", "多孔涂层 42 nm", "吸收快 3 倍", "体外吸收改善"],
    "nodes": [
        {"id": "p1", "label": "吸收缓慢", "evidence": "mat1", "layer": 0, "color": "#D55E00"},
        {"id": "m1", "label": "多孔涂层 42 nm", "evidence": "mat2", "layer": 1, "color": "#0072B2"},
        {"id": "f1", "label": "吸收快 3 倍", "evidence": "mat3", "layer": 2, "color": "#009E73",
         "visual_data": {"kind": "bar", "unit": "吸收速率（a.u.）", "n_caption": "每组 n = 6", "uncertainty": "95% CI",
                         "items": [{"label": "未处理", "value": 0.6, "evidence": "mat1"},
                                   {"label": "涂层", "value": 1.8, "evidence": "mat3"}]}},
        {"id": "c1", "label": "体外吸收改善", "evidence": "mat4", "layer": 3, "color": "#CC79A7"},
    ],
    "edges": [
        {"from": "p1", "to": "m1", "type": "activate"},
        {"from": "m1", "to": "f1", "type": "activate"},
        {"from": "f1", "to": "c1", "type": "activate"},
    ],
}


def d(**over):
    s = copy.deepcopy(BASE)
    s.update(over)
    return s


def run(name: str, spec: dict) -> dict:
    p = OUT / name
    p.mkdir(parents=True, exist_ok=True)
    (p / "spec.json").write_text(json.dumps(spec, ensure_ascii=False), encoding="utf-8")
    return ga_figure.build_and_audit(p / "spec.json", p / "o")


# --- claim rules (pre-existing, must still hold) ----------------------------

def scen_takeaway_missing():
    s = d()
    s["takeaways"] = {"problem": "p1", "method": "m1"}
    return s, ["ga.missing_takeaway"]


def scen_value_not_in_source():
    s = d(nodes=[{**BASE["nodes"][0]},
                 {**BASE["nodes"][1]},
                 {**BASE["nodes"][2], "label": "吸收快 10 倍"}])
    return s, ["ga.value_not_in_source"]


def scen_size_out_of_spec():
    return d(canvas_mm=[240, 120]), ["ga.size_out_of_spec"]


# --- new in the polish pass -------------------------------------------------

def scen_untraceable():
    s = d(nodes=[{**BASE["nodes"][0], "evidence": ""},
                 {**BASE["nodes"][1]},
                 {**BASE["nodes"][2]}])
    return s, ["trace.entity_untraceable"]


def scen_bad_evidence():
    s = d(nodes=[{**BASE["nodes"][0], "evidence": "mat99"},
                 {**BASE["nodes"][1]},
                 {**BASE["nodes"][2]}])
    return s, ["trace.evidence_not_in_materials"]


def scen_material_unused():
    s = d(materials=BASE["materials"] + [{"id": "mat5", "name": "未使用的材料"}])
    return s, ["trace.material_not_drawn"]


SCEN = [
    ("clean", lambda: (d(), [])),
    ("takeaway_missing", scen_takeaway_missing),
    ("value_not_in_source", scen_value_not_in_source),
    ("size_out_of_spec", scen_size_out_of_spec),
    ("untraceable", scen_untraceable),
    ("bad_evidence", scen_bad_evidence),
    ("material_unused", scen_material_unused),
]


def injected_missing_glyphs() -> tuple[dict, str]:
    """Point the renderer at a font that cannot draw the Chinese labels."""
    saved = fontsel.resolve
    dejavu = fontsel._find(["DejaVuSans.ttf"])
    fontsel.resolve = lambda text="": fontsel.Resolved(
        family="DejaVu Sans", path=dejavu, missing=fontsel.coverage(dejavu, text))
    try:
        r = run("missing_glyphs", d())
    finally:
        fontsel.resolve = saved
    return r, "export.missing_glyphs"


def injected_nondeterministic() -> tuple[dict, str]:
    saved = provenance.check_deterministic
    provenance.check_deterministic = lambda *a, **k: {
        "deterministic": False, "detail": {"geometry_differs": True}, "note": "injected"}
    try:
        r = run("nondeterministic", d())
    finally:
        provenance.check_deterministic = saved
    return r, "repro.nondeterministic"


def main() -> int:
    rows = []
    for name, builder in SCEN:
        spec, expect = builder()
        r = run(name, spec)
        fired = {f["rule"] for f in r["findings"]}
        missing = [x for x in expect if x not in fired]
        spurious = [] if expect else [f["rule"] for f in r["findings"]]
        ok = not missing and not spurious
        rows.append({"scenario": name, "expected": expect, "fired": sorted(fired),
                     "missing": missing, "spurious": spurious, "pass": ok,
                     "status": r["status"]})
        print(f"{'PASS' if ok else 'FAIL'}  {name:<22} missing={missing} spurious={spurious}")

    for name, fn in (("missing_glyphs", injected_missing_glyphs),
                     ("nondeterministic", injected_nondeterministic)):
        r, rule = fn()
        ok = rule in {f["rule"] for f in r["findings"]}
        rows.append({"scenario": name, "expected": [rule],
                     "missing": [] if ok else [rule], "spurious": [],
                     "pass": ok, "injected": True, "status": r["status"]})
        print(f"{'PASS' if ok else 'FAIL'}  {name:<22} injected={ok}")

    plt.close("all")
    passed = sum(1 for x in rows if x["pass"])
    report = {
        "schema_version": "ga2-bench/v1",
        "scenarios": rows,
        "totals": {"passed": passed, "of": len(rows)},
        "note": ("Claim rules plus provenance, glyph coverage and determinism. Two scenarios "
                 "inject a defect by patching a font resolver and the determinism check, "
                 "because those cannot be expressed in a spec."),
    }
    (Path(__file__).resolve().parent / "report_ga2.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n{passed}/{len(rows)} pass")
    return 0 if passed == len(rows) else 1


if __name__ == "__main__":
    raise SystemExit(main())
