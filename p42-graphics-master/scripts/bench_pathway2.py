"""Benchmark for the polished mechanism-figure skill."""
from __future__ import annotations
import copy, json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import matplotlib.pyplot as plt  # noqa: E402
import fontsel  # noqa: E402
import pathway  # noqa: E402
import provenance  # noqa: E402

OUT = Path(__file__).resolve().parent / "_run_pathway2"

BASE = {
 "species":"human","font_size":9,"canvas_mm":[150,70],
 "aliases":{"TP53":["Tp53","p53"]},
 "materials":[{"id":"m1","name":"TP53"},{"id":"m2","name":"MDM2"},{"id":"m3","name":"CDKN1A"}],
 "connections":[{"from":"g1","to":"p1"},{"from":"p1","to":"g2"}],
 "nodes":[
   {"id":"g1","label":"TP53","kind":"gene","evidence":"m1","layer":0,
    "accession":"HGNC:11998","accession_source":"hgnc","color":"#56B4E9"},
   {"id":"p1","label":"MDM2","kind":"protein","evidence":"m2","layer":1,
    "accession":"Q00987","accession_source":"uniprot","color":"#009E73"},
   {"id":"g2","label":"CDKN1A","kind":"gene","evidence":"m3","layer":2,
    "accession":"HGNC:1784","accession_source":"hgnc","color":"#E69F00"}],
 "edges":[{"from":"g1","to":"p1","type":"activate"},{"from":"p1","to":"g2","type":"inhibit"}],
}

def d(**o):
    s = copy.deepcopy(BASE); s.update(o); return s

def run(name, spec):
    p = OUT / name; p.mkdir(parents=True, exist_ok=True)
    (p/"spec.json").write_text(json.dumps(spec, ensure_ascii=False), encoding="utf-8")
    return pathway.build_and_audit(p/"spec.json", p/"o")

SCEN = [
 ("clean", lambda: (d(), [])),
 ("untraceable", lambda: (d(nodes=[{**BASE["nodes"][0], "evidence": ""}]), ["trace.entity_untraceable"])),
 ("bad_evidence", lambda: (d(nodes=[{**BASE["nodes"][0], "evidence": "m99"}]), ["trace.evidence_not_in_materials"])),
 ("material_unused", lambda: (d(materials=BASE["materials"]+[{"id":"m4","name":"BAX"}]), ["trace.material_not_drawn"])),
 ("invented_edge", lambda: (d(edges=BASE["edges"]+[{"from":"g1","to":"g2","type":"activate"}]), ["trace.edge_not_in_source"])),
 ("connection_missing", lambda: (d(edges=[BASE["edges"][0]]), ["trace.connection_not_drawn"])),
 ("gene_casing", lambda: (d(nodes=[{**BASE["nodes"][0], "label":"Tp53"}]), ["nomenclature.gene_casing"])),
 ("alias_collision", lambda: (d(nodes=BASE["nodes"]+[{"id":"g3","label":"Tp53","kind":"gene","evidence":"m1","layer":3,
                                                      "accession":"HGNC:11998","accession_source":"hgnc"}],
                               edges=BASE["edges"]+[{"from":"g2","to":"g3"}],
                               connections=BASE["connections"]+[{"from":"g2","to":"g3"}]),
                             ["nomenclature.alias_collision"])),
]

def injected_glyphs():
    saved = fontsel.resolve
    dj = fontsel._find(["DejaVuSans.ttf"])
    fontsel.resolve = lambda text="": fontsel.Resolved("DejaVu Sans", dj, fontsel.coverage(dj, text))
    try:
        s = d(nodes=[{**BASE["nodes"][0], "label": "肿瘤抑制因子"}, BASE["nodes"][1], BASE["nodes"][2]])
        r = run("glyphs", s)
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
        rows.append({"scenario": name, "expected": expect, "missing": missing,
                     "spurious": spurious, "pass": ok})
        print(f"{'PASS' if ok else 'FAIL'}  {name:<18} missing={missing} spurious={spurious}")
    for name, fn in (("missing_glyphs", injected_glyphs), ("nondeterministic", injected_nondet)):
        r, rule = fn()
        ok = rule in {f["rule"] for f in r["findings"]}
        rows.append({"scenario": name, "expected": [rule], "missing": [] if ok else [rule],
                     "spurious": [], "pass": ok, "injected": True})
        print(f"{'PASS' if ok else 'FAIL'}  {name:<18} injected={ok}")
    plt.close("all")
    passed = sum(1 for x in rows if x["pass"])
    (Path(__file__).resolve().parent/"report_pathway2.json").write_text(
        json.dumps({"scenario": rows, "totals": {"passed": passed, "of": len(rows)}},
                   ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n{passed}/{len(rows)} pass")
    return 0 if passed == len(rows) else 1

if __name__ == "__main__":
    raise SystemExit(main())
