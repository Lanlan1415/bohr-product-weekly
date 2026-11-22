"""Benchmark for the polished schematic skill: provenance, font, determinism."""
from __future__ import annotations
import copy, json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import matplotlib.pyplot as plt  # noqa: E402
import fontsel  # noqa: E402
import provenance  # noqa: E402
import schematic  # noqa: E402

OUT = Path(__file__).resolve().parent / "_run_schematic2"
BASE = {
 "font_size": 9, "canvas_mm": [130, 60],
 "materials": [{"id": "m1", "name": "基底"}, {"id": "m2", "name": "催化剂"}, {"id": "m3", "name": "产物"}],
 "connections": [{"from": "a", "to": "b"}, {"from": "b", "to": "c"}],
 "nodes": [{"id": "a", "label": "基底", "evidence": "m1", "layer": 0, "color": "#56B4E9"},
           {"id": "b", "label": "催化剂", "evidence": "m2", "layer": 1, "color": "#009E73"},
           {"id": "c", "label": "产物", "evidence": "m3", "layer": 2, "color": "#E69F00"}],
 "edges": [{"from": "a", "to": "b", "type": "flow"}, {"from": "b", "to": "c", "type": "flow"}],
}

def d(**o):
    s = copy.deepcopy(BASE); s.update(o); return s

def run(name, spec):
    p = OUT / name; p.mkdir(parents=True, exist_ok=True)
    (p/"spec.json").write_text(json.dumps(spec, ensure_ascii=False), encoding="utf-8")
    return schematic.build_and_audit(p/"spec.json", p/"o")

SCEN = [
 ("clean", lambda: (d(), [])),
 ("untraceable", lambda: (d(nodes=[{"id":"a","label":"基底","layer":0}, BASE["nodes"][1], BASE["nodes"][2]]), ["trace.entity_untraceable"])),
 ("material_unused", lambda: (d(materials=BASE["materials"]+[{"id":"m4","name":"副产物"}]), ["trace.material_not_drawn"])),
 ("invented_edge", lambda: (d(edges=BASE["edges"]+[{"from":"a","to":"c"}]), ["trace.edge_not_in_source"])),
 ("connection_missing", lambda: (d(edges=[BASE["edges"][0]]), ["trace.connection_not_drawn"])),

]

def injected_glyphs():
    saved = fontsel.resolve
    dj = fontsel._find(["DejaVuSans.ttf"])
    fontsel.resolve = lambda text="": fontsel.Resolved("DejaVu Sans", dj, fontsel.coverage(dj, text))
    try:
        r = run("glyphs", d(nodes=[{"id":"a","label":"基底材料","layer":0,"evidence":"m1"}, BASE["nodes"][1], BASE["nodes"][2]]))
    finally:
        fontsel.resolve = saved
    return r, "export.missing_glyphs"

def injected_nondet():
    saved = provenance.check_deterministic
    provenance.check_deterministic = lambda *a, **k: {"deterministic": False,
        "detail": {"geometry_differs": True}, "note": "injected"}
    try:
        r = run("nondet", d())
    finally:
        provenance.check_deterministic = saved
    return r, "repro.nondeterministic"

def main() -> int:
    rows = []
    for name, b in SCEN:
        spec, expect = b()
        r = run(name, spec)
        fired = {f["rule"] for f in r["findings"]}
        missing = [x for x in expect if x not in fired]
        spurious = [] if expect else [f["rule"] for f in r["findings"]]
        ok = not missing and not spurious
        rows.append({"scenario": name, "missing": missing, "spurious": spurious, "pass": ok})
        print(f"{'PASS' if ok else 'FAIL'}  {name:<18} missing={missing} spurious={spurious}")
    for name, fn in (("missing_glyphs", injected_glyphs), ("nondeterministic", injected_nondet)):
        r, rule = fn()
        ok = rule in {f["rule"] for f in r["findings"]}
        rows.append({"scenario": name, "missing": [] if ok else [rule], "spurious": [], "pass": ok, "injected": True})
        print(f"{'PASS' if ok else 'FAIL'}  {name:<18} injected={ok}")
    plt.close("all")
    passed = sum(1 for x in rows if x["pass"])
    (Path(__file__).resolve().parent/"report_schematic2.json").write_text(
        json.dumps({"scenarios": rows, "totals": {"passed": passed, "of": len(rows)}},
                   ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n{passed}/{len(rows)} pass")
    return 0 if passed == len(rows) else 1

if __name__ == "__main__":
    raise SystemExit(main())
