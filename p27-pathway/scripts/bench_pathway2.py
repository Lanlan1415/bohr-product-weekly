"""Benchmark for the polished mechanism-figure skill.

One scenario per rule: each plants one defect and names the rule that must
fire; the clean baselines must stay silent, so blanket flagging cannot pass.

Two defects cannot be planted in a spec — a font without the needed glyphs and
a renderer that is not reproducible — so those scenarios inject them by patching
a resolver and restoring it afterwards. That still tests the checker against a
real defect rather than a mock.
"""
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
 "materials":[{"id":"m1","name":"TP53","source":"Results ¶2"},
              {"id":"m2","name":"MDM2","source":"Results ¶2"},
              {"id":"m3","name":"CDKN1A","source":"Fig 4b"}],
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

CASE = {"case_id": "bench-case-p27", "output_contract": {
    "figure_svg": "editable layered svg path",
    "figure_pdf": "embedded-font pdf path",
    "font_report": "resolved font record"}}


def d(**o):
    s = copy.deepcopy(BASE); s.update(o); return s


def run(name, spec, checklist=None):
    p = OUT / name; p.mkdir(parents=True, exist_ok=True)
    (p/"spec.json").write_text(json.dumps(spec, ensure_ascii=False), encoding="utf-8")
    return pathway.build_and_audit(p/"spec.json", p/"o",
                                   Path(checklist) if checklist else None)


def sc_clean():            return d(), []
def sc_untraceable():      return d(nodes=[{**BASE["nodes"][0], "evidence": ""}]), ["trace.entity_untraceable"]
def sc_bad_evidence():     return d(nodes=[{**BASE["nodes"][0], "evidence": "m99"}]), ["trace.evidence_not_in_materials"]
def sc_material_unused():  return d(materials=BASE["materials"]+[{"id":"m4","name":"BAX","source":"Results ¶3"}]), ["trace.material_not_drawn"]
def sc_invented_edge():    return d(edges=BASE["edges"]+[{"from":"g1","to":"g2","type":"activate"}]), ["trace.edge_not_in_source"]
def sc_connection_missing(): return d(edges=[BASE["edges"][0]]), ["trace.connection_not_drawn"]
def sc_gene_casing():      return d(nodes=[{**BASE["nodes"][0], "label":"Tp53"}]), ["nomenclature.gene_casing"]
def sc_alias_collision():
    return (d(nodes=BASE["nodes"]+[{"id":"g3","label":"Tp53","kind":"gene","evidence":"m1","layer":3,
                                    "accession":"HGNC:11998","accession_source":"hgnc"}],
              edges=BASE["edges"]+[{"from":"g2","to":"g3"}],
              connections=BASE["connections"]+[{"from":"g2","to":"g3"}]),
            ["nomenclature.alias_collision"])
def sc_material_no_source():
    mats = copy.deepcopy(BASE["materials"]); mats[0].pop("source")
    return d(materials=mats), ["trace.material_no_source"]
def sc_dangling_edge():
    return d(edges=BASE["edges"]+[{"from":"g1","to":"ghost","type":"activate"}]), ["edge.dangling"]
def sc_malformed_entries():
    s = d()
    s["nodes"] = BASE["nodes"] + ["oops"]
    s["edges"] = BASE["edges"] + [42]
    return s, ["node.malformed", "edge.malformed"]
def sc_compartment_mismatch():
    s = d(compartments=[{"id":"nucleus","label":"细胞核","layers":[2]}])
    s["nodes"][1]["compartment"] = "nucleus"       # MDM2 sits at layer 1, band is layer 2
    return s, ["compartment.mismatch"]
def sc_compartment_undeclared():
    s = d()
    s["nodes"][0]["compartment"] = "cytosol"       # no compartment band declares this id
    return s, ["compartment.undeclared"]
def sc_compartment_clean():
    s = d(compartments=[{"id":"membrane","label":"细胞膜","layers":[0]},
                        {"id":"cytosol","label":"细胞质","layers":[1]}])
    s["nodes"][0]["compartment"] = "membrane"
    s["nodes"][1]["compartment"] = "cytosol"
    return s, []
def sc_confidence_missing():
    s = d(confidence_required=True)
    return s, ["edge.confidence_missing"]
def sc_confidence_unknown():
    s = d(confidence_required=True)
    s["edges"][0]["confidence"] = "very strong"    # not a declared level
    s["edges"][1]["confidence"] = "confirmed"
    return s, ["edge.confidence_unknown"]
def sc_confidence_clean():
    s = d(confidence_required=True)
    s["edges"][0]["confidence"] = "confirmed"
    s["edges"][1]["confidence"] = "predicted"
    return s, []
def sc_feedback_unlabeled():
    return (d(edges=BASE["edges"]+[{"from":"g2","to":"g1","type":"activate"}],
              connections=BASE["connections"]+[{"from":"g2","to":"g1"}]),
            ["edge.feedback_unlabeled"])
def sc_feedback_clean():
    return (d(edges=BASE["edges"]+[{"from":"g2","to":"g1","type":"activate","feedback":True}],
              connections=BASE["connections"]+[{"from":"g2","to":"g1"}]),
            [])
def sc_recycle_clean():
    return (d(edges=BASE["edges"]+[{"from":"g2","to":"g1","type":"flow","recycle":True}],
              connections=BASE["connections"]+[{"from":"g2","to":"g1"}]),
            [])
def sc_size_not_positive():
    s = d()
    s["nodes"][0]["size"] = 0
    return s, ["size.not_positive"]
def sc_size_unexplained():
    s = d(legend_required=True)
    s["nodes"][0]["size"] = 1.0
    s["nodes"][1]["size"] = 2.0
    s["legend"] = ["TP53 (gene)", "MDM2 (protein)", "CDKN1A (gene)"]
    return s, ["legend.size_unexplained"]
def sc_size_explained():
    s = d(legend_required=True, legend_notes=["节点大小 = 表达量（归一化）"])
    s["nodes"][0]["size"] = 1.0
    s["nodes"][1]["size"] = 2.0
    s["legend"] = ["TP53 (gene)", "MDM2 (protein)", "CDKN1A (gene)"]
    return s, []
def sc_canvas_invalid():
    return d(canvas_mm=[0, 50]), ["audit.no_section"]

SCEN = [
 ("clean", sc_clean),
 ("untraceable", sc_untraceable),
 ("bad_evidence", sc_bad_evidence),
 ("material_unused", sc_material_unused),
 ("invented_edge", sc_invented_edge),
 ("connection_missing", sc_connection_missing),
 ("gene_casing", sc_gene_casing),
 ("alias_collision", sc_alias_collision),
 ("material_no_source", sc_material_no_source),
 ("dangling_edge", sc_dangling_edge),
 ("malformed_entries", sc_malformed_entries),
 ("compartment_mismatch", sc_compartment_mismatch),
 ("compartment_undeclared", sc_compartment_undeclared),
 ("compartment_clean", sc_compartment_clean),
 ("confidence_missing", sc_confidence_missing),
 ("confidence_unknown", sc_confidence_unknown),
 ("confidence_clean", sc_confidence_clean),
 ("feedback_unlabeled", sc_feedback_unlabeled),
 ("feedback_clean", sc_feedback_clean),
 ("recycle_clean", sc_recycle_clean),
 ("size_not_positive", sc_size_not_positive),
 ("size_unexplained", sc_size_unexplained),
 ("size_explained", sc_size_explained),
 ("canvas_invalid", sc_canvas_invalid),
]

CHECKLIST_BAD = OUT / "_bad_checklist.json"


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


def sc_checklist_unreadable():
    OUT.mkdir(parents=True, exist_ok=True)
    CHECKLIST_BAD.write_text("not json at all", encoding="utf-8")
    r = run("checklist_bad", d(), CHECKLIST_BAD)
    return r, "checklist.unreadable"


def sc_refusal_contract():
    """A refusal still echoes case_id + output_contract from the case file."""
    p = OUT / "refusal_contract"; p.mkdir(parents=True, exist_ok=True)
    (p/"spec.json").write_text("{ broken json", encoding="utf-8")
    (p/"case.json").write_text(json.dumps(CASE, ensure_ascii=False), encoding="utf-8")
    r = pathway.build_and_audit(p/"spec.json", p/"o", None, p/"case.json", None)
    ok = (r["status"] == "undetermined"
          and r.get("case_id") == CASE["case_id"]
          and r.get("output_contract") == CASE["output_contract"]
          and r.get("figure_pdf") is None)
    return r, ["audit.no_section"], ok


def sc_success_contract():
    """--case on a clean run fills the artifact-named contract keys with real paths."""
    p = OUT / "success_contract"; p.mkdir(parents=True, exist_ok=True)
    (p/"spec.json").write_text(json.dumps(d(), ensure_ascii=False), encoding="utf-8")
    (p/"case.json").write_text(json.dumps(CASE, ensure_ascii=False), encoding="utf-8")
    r = pathway.build_and_audit(p/"spec.json", p/"o", None, p/"case.json", None)
    ok = (r.get("case_id") == CASE["case_id"]
          and isinstance(r.get("figure_svg"), str) and Path(r["figure_svg"]).suffix == ".svg"
          and isinstance(r.get("figure_pdf"), str) and Path(r["figure_pdf"]).suffix == ".pdf"
          and r.get("font_report", {}).get("family"))
    return r, [], ok


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
        print(f"{'PASS' if ok else 'FAIL'}  {name:<24} missing={missing} spurious={spurious}")
    for name, fn, rule in (("missing_glyphs", injected_glyphs, "export.missing_glyphs"),
                           ("nondeterministic", injected_nondet, "repro.nondeterministic"),
                           ("checklist_unreadable", sc_checklist_unreadable, "checklist.unreadable")):
        r, rule_id = fn()
        ok = rule_id in {f["rule"] for f in r["findings"]}
        rows.append({"scenario": name, "expected": [rule_id], "missing": [] if ok else [rule_id],
                     "spurious": [], "pass": ok, "injected": True})
        print(f"{'PASS' if ok else 'FAIL'}  {name:<24} injected={ok}")
    for name, fn in (("refusal_contract", sc_refusal_contract), ("success_contract", sc_success_contract)):
        res, expect, ok = fn()
        rows.append({"scenario": name, "expected": expect, "missing": [] if ok else ["<contract gap>"],
                     "spurious": [], "pass": bool(ok), "contract": True})
        print(f"{'PASS' if ok else 'FAIL'}  {name:<24} contract={ok}")
    plt.close("all")
    passed = sum(1 for x in rows if x["pass"])
    (Path(__file__).resolve().parent/"report_pathway2.json").write_text(
        json.dumps({"scenario": rows, "totals": {"passed": passed, "of": len(rows)}},
                   ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n{passed}/{len(rows)} pass")
    return 0 if passed == len(rows) else 1


if __name__ == "__main__":
    raise SystemExit(main())
