"""Benchmark for the relation-type and category-mapping rules.

Covers the rules added against the brief's failure classes:

  a misspelled relation type silently re-styled as a flow arrow ("抑制画成激活")
  a colour mapping that is not a mapping (one category, two colours)
  a drawn entity whose category the declared legend list does not know

Each scenario plants exactly one defect and names the rule that must fire; the
clean baseline must report nothing.

    python bench_schematic3.py
"""

from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import schematic  # noqa: E402

OUT = Path(__file__).resolve().parent / "_run_schematic3"

BASE = {
    "case_id": "demo-cat-001",
    "font_size": 9, "canvas_mm": [130, 60],
    "materials": [{"id": "m1", "name": "Substrate"}, {"id": "m2", "name": "Catalyst"},
                  {"id": "m3", "name": "Intermediate"}, {"id": "m4", "name": "Product"}],
    "connections": [{"from": "a", "to": "b"}, {"from": "b", "to": "c"},
                    {"from": "c", "to": "d"}],
    "categories": {"substrate": "#56B4E9", "catalyst": "#009E73",
                   "intermediate": "#E69F00", "product": "#0072B2"},
    "nodes": [
        {"id": "a", "label": "Substrate", "evidence": "m1", "layer": 0, "category": "substrate"},
        {"id": "b", "label": "Catalyst", "evidence": "m2", "layer": 1, "category": "catalyst"},
        {"id": "c", "label": "Intermediate", "evidence": "m3", "layer": 2, "category": "intermediate"},
        {"id": "d", "label": "Product", "evidence": "m4", "layer": 3, "category": "product"},
    ],
    "edges": [{"from": "a", "to": "b", "type": "activate"},
              {"from": "b", "to": "c", "type": "flow"},
              {"from": "c", "to": "d", "type": "bind"}],
}


def d(**o):
    s = copy.deepcopy(BASE)
    s.update(o)
    return s


def run(name, spec):
    p = OUT / name
    p.mkdir(parents=True, exist_ok=True)
    (p / "spec.json").write_text(json.dumps(spec, ensure_ascii=False), encoding="utf-8")
    return schematic.build_and_audit(p / "spec.json", p / "o")


SCEN = [
    # clean: category colours inherited from the declared mapping, types known
    ("clean_categories", lambda: (d(), [])),
    ("all_types_known", lambda: (
        d(edges=[{"from": "a", "to": "b", "type": "activate"},
                 {"from": "b", "to": "c", "type": "inhibit"},
                 {"from": "c", "to": "d", "type": "bind"}]), [])),

    # the mechanism relation silently re-styled
    ("edge_type_unknown", lambda: (
        d(edges=[{"from": "a", "to": "b", "type": "actviate"}, BASE["edges"][1],
                 BASE["edges"][2]]),
        ["edge.type_unknown"])),

    # colour mapping consistency
    ("category_mismatch_declared", lambda: (
        d(nodes=[{**BASE["nodes"][0], "color": "#D55E00"}, *BASE["nodes"][1:]]),
        ["colour.category_mismatch"])),
    ("category_mismatch_group", lambda: (
        d(nodes=[*BASE["nodes"][:2], {**BASE["nodes"][2], "color": "#CC79A7"},
                 BASE["nodes"][3]]),
        ["colour.category_mismatch"])),
    ("category_unknown", lambda: (
        d(nodes=[*BASE["nodes"][:2], {**BASE["nodes"][2], "category": "solvent"},
                 BASE["nodes"][3]]),
        ["colour.category_unknown"])),
    ("category_list_unknown", lambda: (
        d(categories=["substrate", "catalyst", "product"],
          nodes=[*BASE["nodes"][:2], BASE["nodes"][2], BASE["nodes"][3]]),
        ["colour.category_unknown"])),
    ("category_list_clean", lambda: (
        d(categories=["substrate", "catalyst", "intermediate", "product"]), [])),
]


def main() -> int:
    rows = []
    for name, b in SCEN:
        spec, expect = b()
        r = run(name, spec)
        fired = {f["rule"] for f in r["findings"]}
        missing = [x for x in expect if x not in fired]
        spurious = [] if expect else [f["rule"] for f in r["findings"]]
        ok = not missing and not spurious
        rows.append({"scenario": name, "missing": missing, "spurious": spurious,
                     "pass": ok, "status": r["status"]})
        print(f"{'PASS' if ok else 'FAIL'}  {name:<26} missing={missing} spurious={spurious}")

    passed = sum(1 for x in rows if x["pass"])
    (Path(__file__).resolve().parent / "report_schematic3.json").write_text(
        json.dumps({"scenarios": rows, "totals": {"passed": passed, "of": len(rows)},
                    "note": ("One defect per rule, plus clean guards for inheritance and "
                             "declared-list categories. Clean baselines report nothing.")},
                   ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n{passed}/{len(rows)} pass")
    return 0 if passed == len(rows) else 1


if __name__ == "__main__":
    raise SystemExit(main())
