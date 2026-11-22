"""Benchmark for the pathway figure audit (layout + nomenclature).

Each scenario plants one defect and names the rule that must fire. The clean
baseline must report no high or medium finding, so blanking everything cannot
pass.

    python bench_pathway.py
"""

from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import matplotlib.pyplot as plt  # noqa: E402

import nomenclature  # noqa: E402
import schematic  # noqa: E402

BASE = {
    "species": "human",
    "font_size": 9,
    "aliases": {"TP53": ["Tp53", "p53"]},
    "nodes": [
        {"id": "g1", "label": "TP53", "kind": "gene", "layer": 0,
         "accession": "HGNC:11998", "accession_source": "hgnc", "color": "#56B4E9"},
        {"id": "p1", "label": "MDM2", "kind": "protein", "layer": 1,
         "accession": "Q00987", "accession_source": "uniprot", "color": "#009E73"},
        {"id": "g2", "label": "CDKN1A", "kind": "gene", "layer": 2,
         "accession": "HGNC:1784", "accession_source": "hgnc", "color": "#E69F00"},
    ],
    "edges": [
        {"from": "g1", "to": "p1", "type": "activate"},
        {"from": "p1", "to": "g2", "type": "inhibit"},
    ],
}


def scen_clean():
    return copy.deepcopy(BASE), []


def scen_wrong_casing():
    s = copy.deepcopy(BASE)
    s["nodes"][0]["label"] = "Tp53"
    return s, ["nomenclature.gene_casing"]


def scen_missing_accession():
    s = copy.deepcopy(BASE)
    s["nodes"][1].pop("accession")
    return s, ["nomenclature.missing_accession"]


def scen_alias_collision():
    s = copy.deepcopy(BASE)
    s["nodes"].append({"id": "g3", "label": "Tp53", "kind": "gene", "layer": 3,
                       "accession": "HGNC:11998", "accession_source": "hgnc"})
    s["edges"].append({"from": "g2", "to": "g3"})
    return s, ["nomenclature.alias_collision"]


def scen_vague_entity():
    s = copy.deepcopy(BASE)
    s["nodes"].append({"id": "v", "label": "signaling", "layer": 3})
    s["edges"].append({"from": "g2", "to": "v"})
    return s, ["nomenclature.vague_entity"]


def scen_malformed_accession():
    s = copy.deepcopy(BASE)
    s["nodes"][0]["accession"] = "TP53_HUMAN"
    return s, ["nomenclature.accession_malformed"]


def scen_species_ambiguous():
    s = copy.deepcopy(BASE)
    s.pop("species")
    s["nodes"][0]["label"] = "Tp53"          # mouse casing
    s["nodes"][2]["label"] = "CDKN1A"        # human casing
    s["aliases"] = {}
    return s, ["nomenclature.species_ambiguous"]


def scen_protein_italic():
    """A protein name set in italic: convention sets protein names in roman."""
    s = copy.deepcopy(BASE)
    s["nodes"][1]["kind"] = "protein"
    s["nodes"][1]["italic"] = True
    return s, ["nomenclature.protein_italic"]


def scen_gene_not_italic():
    """A gene symbol forced roman by an explicit italic:false."""
    s = copy.deepcopy(BASE)
    s["nodes"][0]["kind"] = "gene"
    s["nodes"][0]["italic"] = False
    return s, ["nomenclature.gene_not_italic"]


def scen_layout_overlap():
    s = copy.deepcopy(BASE)
    s["nodes"] = [{"id": f"N{i}", "label": "Extremely long entity name", "layer": 1}
                  for i in range(6)]
    s["edges"] = []
    s["canvas_mm"] = [60, 45]
    s["font_size"] = 30
    return s, ["label.overlap"]


def scen_backward_arrow():
    s = copy.deepcopy(BASE)
    s["edges"].append({"from": "g2", "to": "g1", "type": "flow"})
    return s, ["edge.backward_flow"]


SCENARIOS = [
    ("clean", scen_clean),
    ("wrong_casing", scen_wrong_casing),
    ("missing_accession", scen_missing_accession),
    ("alias_collision", scen_alias_collision),
    ("vague_entity", scen_vague_entity),
    ("malformed_accession", scen_malformed_accession),
    ("species_ambiguous", scen_species_ambiguous),
    ("protein_italic", scen_protein_italic),
    ("gene_not_italic", scen_gene_not_italic),
    ("layout_overlap", scen_layout_overlap),
    ("backward_arrow", scen_backward_arrow),
]


def run_one(name, builder, root: Path) -> dict:
    spec, expect = builder()
    d = root / name
    d.mkdir(parents=True, exist_ok=True)
    built = schematic.render(spec, d / "figure")
    layout = schematic.audit(spec, built)
    nom = nomenclature.audit_nomenclature(spec, built["svg"])
    plt.close(built["fig"])

    fired = {f["rule"] for f in layout["findings"] + nom["findings"]}
    missing = [r for r in expect if r not in fired]
    spurious = []
    if not expect:
        spurious = [f["rule"] for f in layout["findings"] + nom["findings"]
                    if f["severity"] in ("high", "medium")]
    return {"scenario": name, "expected": expect, "fired": sorted(fired),
            "missing": missing, "spurious": spurious,
            "pass": not missing and not spurious}


def main() -> int:
    root = Path(__file__).resolve().parent / "_run"
    rows = [run_one(n, b, root) for n, b in SCENARIOS]
    passed = sum(1 for r in rows if r["pass"])
    report = {"schema_version": "pathway-bench/v1", "scenarios": rows,
              "totals": {"passed": passed, "of": len(rows)},
              "note": ("One planted defect per scenario. The clean baseline must stay silent, "
                       "so blanket flagging cannot pass.")}
    (Path(__file__).resolve().parent / "report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    for r in rows:
        print(f"{'PASS' if r['pass'] else 'FAIL'}  {r['scenario']:<22}"
              f"expected={r['expected']} missing={r['missing']} spurious={r['spurious']}")
    print(f"\n{passed}/{len(rows)} scenarios pass")
    return 0 if passed == len(rows) else 1


if __name__ == "__main__":
    raise SystemExit(main())
