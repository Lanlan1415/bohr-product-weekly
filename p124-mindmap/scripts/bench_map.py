"""Benchmark for the mind-map skill.

One scenario per rule, aligned to the scoring points the task states:

  tree integrity (one root, no cycles, bounded depth)   -> root_count, dangling_parent,
                                                          cycle, too_deep
  sibling discipline                                    -> duplicate_sibling, wide_node
  every leaf traceable                                  -> leaf_without_evidence
  relations the map asserts (连得对)                      -> edge_incomplete, edge_dangling,
                                                          edge_self, edge_type_missing,
                                                          edge_type_unknown, edge_no_basis
  fact vs summary vs inference                          -> kind_undeclared, kind_unknown
  no placeholder nodes (抓得准)                            -> decorative_label
  readable scale                                        -> too_many_nodes

    python bench_map.py
"""

from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import sections as S  # noqa: E402

BASE = {
    "max_depth": 4,
    "nodes": [
        {"id": "r", "label": "paper"},
        {"id": "a", "label": "problem", "parent": "r", "evidence_exempt": True},
        {"id": "b", "label": "method", "parent": "r", "evidence": "Sec 2", "kind": "fact"},
        {"id": "c", "label": "finding", "parent": "r", "evidence": "Fig 3b", "kind": "fact"},
        {"id": "d", "label": "limit", "parent": "c", "evidence": "p.7", "kind": "summary"},
    ],
    "edges": [{"from": "b", "to": "c", "kind": "support", "basis": "p.7"}],
}


def d(**over):
    s = copy.deepcopy(BASE)
    s.update(over)
    return s


SCEN = [
    ("clean", lambda: (d(), [])),
    ("no_nodes", lambda: (d(nodes=[]), ["map.no_nodes"])),
    ("root_count", lambda: (d(nodes=BASE["nodes"] + [{"id": "r2", "label": "second root"}]),
                            ["map.root_count"])),
    ("dangling_parent", lambda: (d(nodes=BASE["nodes"] + [
        {"id": "e", "label": "orphan", "parent": "zz", "evidence": "p.1", "kind": "fact"}]),
        ["map.dangling_parent"])),
    ("cycle", lambda: (d(nodes=BASE["nodes"] + [
        {"id": "e", "label": "loop", "parent": "f", "evidence": "p.1", "kind": "fact"},
        {"id": "f", "label": "loop2", "parent": "e", "evidence": "p.1", "kind": "fact"}]),
        ["map.cycle"])),
    ("too_deep", lambda: (d(max_depth=2, nodes=BASE["nodes"] + [
        {"id": "g", "label": "deep", "parent": "d", "evidence": "p.8", "kind": "fact"}]),
        ["map.too_deep"])),
    ("duplicate_sibling", lambda: (d(nodes=BASE["nodes"] + [
        {"id": "b2", "label": "method", "parent": "r", "evidence": "Sec 3", "kind": "fact"}]),
        ["map.duplicate_sibling"])),
    ("leaf_without_evidence", lambda: (d(nodes=BASE["nodes"] + [
        {"id": "h", "label": "bare", "parent": "d"}]),
        ["map.leaf_without_evidence"])),
    ("wide_node", lambda: (d(max_children=2, nodes=BASE["nodes"] + [
        {"id": "i1", "label": "kid one", "parent": "r", "evidence": "p.2", "kind": "fact"},
        {"id": "i2", "label": "kid two", "parent": "r", "evidence": "p.2", "kind": "fact"},
        {"id": "i3", "label": "kid three", "parent": "r", "evidence": "p.3", "kind": "fact"}]),
        ["map.wide_node"])),
    # relations
    ("edge_incomplete", lambda: (d(edges=BASE["edges"] + [{"from": "c", "kind": "causal",
                                                           "basis": "p.8"}]),
                                 ["map.edge_incomplete"])),
    ("edge_dangling", lambda: (d(edges=BASE["edges"] + [{"from": "c", "to": "zz",
                                                         "kind": "causal", "basis": "p.8"}]),
                               ["map.edge_dangling"])),
    ("edge_self", lambda: (d(edges=BASE["edges"] + [{"from": "c", "to": "c",
                                                     "kind": "causal", "basis": "p.8"}]),
                           ["map.edge_self"])),
    ("edge_type_missing", lambda: (d(edges=BASE["edges"] + [{"from": "c", "to": "b",
                                                             "basis": "p.8"}]),
                                   ["map.edge_type_missing"])),
    ("edge_type_unknown", lambda: (d(edges=BASE["edges"] + [{"from": "c", "to": "b",
                                                             "kind": "causes_maybe",
                                                             "basis": "p.8"}]),
                                   ["map.edge_type_unknown"])),
    ("edge_no_basis", lambda: (d(edges=BASE["edges"] + [{"from": "c", "to": "b",
                                                         "kind": "contrast"}]),
                               ["map.edge_no_basis"])),
    # provenance kinds
    ("kind_undeclared", lambda: (d(nodes=BASE["nodes"] + [
        {"id": "j", "label": "risk", "parent": "c", "evidence": "p.9"}]),
        ["map.kind_undeclared"])),
    ("kind_unknown", lambda: (d(nodes=BASE["nodes"] + [
        {"id": "k", "label": "guess", "parent": "c", "evidence": "p.9", "kind": "opinion"}]),
        ["map.kind_unknown"])),
    # labels and scale
    ("decorative_label", lambda: (d(nodes=BASE["nodes"] + [
        {"id": "x", "label": "其他", "parent": "c", "evidence_exempt": True}]),
        ["map.decorative_label"])),
    ("too_many_nodes", lambda: (d(max_nodes=3), ["map.too_many_nodes"])),
    ("duplicate_node_id", lambda: (d(nodes=BASE["nodes"] + [
        {"id": "b", "label": "reused id", "parent": "r", "evidence": "p.2", "kind": "fact"}]),
        ["map.duplicate_node_id"])),
    ("parent_relation_unknown", lambda: (d(nodes=[{**n, "parent_kind": "perhaps_related"} if n["id"] == "b" else n
                                                   for n in BASE["nodes"]]),
        ["map.parent_relation_unknown"])),
    ("label_missing", lambda: (d(nodes=BASE["nodes"] + [
        {"id": "unlabelled", "label": "", "parent": "c", "evidence": "p.3", "kind": "fact"}]),
        ["map.label_missing"])),
    # false-positive guards: standard map content must stay silent
    ("fp_real_labels", lambda: (d(nodes=BASE["nodes"] + [
        {"id": "m", "label": "方法", "parent": "b", "evidence": "p.3", "kind": "fact"},
        {"id": "n", "label": "aims", "parent": "c", "evidence": "p.4", "kind": "summary"}]), [])),
    ("fp_edge_variants", lambda: (d(edges=BASE["edges"] + [
        {"from": "a", "to": "b", "kind": "dependency", "basis": "Table 2 row 3"},
        {"from": "c", "to": "d", "kind": "contains", "basis": "Fig 3b"}]), [])),
]


def main() -> int:
    rows = []
    for name, builder in SCEN:
        spec, expect = builder()
        findings, status, counts = S.run(spec, "mindmap")
        fired = {f["rule"] for f in findings}
        missing = [r for r in expect if r not in fired]
        spurious = [] if expect else [f["rule"] for f in findings]
        ok = not missing and not spurious
        rows.append({"scenario": name, "expected": expect, "fired": sorted(fired),
                     "missing": missing, "spurious": spurious, "pass": ok, "status": status})
        print(f"{'PASS' if ok else 'FAIL'}  {name:<26} missing={missing} spurious={spurious}")

    passed = sum(1 for r in rows if r["pass"])
    report = {"schema_version": "map-bench/v2", "scenarios": rows,
              "totals": {"passed": passed, "of": len(rows)},
              "note": ("One scenario per rule, aligned to the mind-map scoring points. "
                       "Clean baselines and false-positive guards must report nothing.")}
    (Path(__file__).resolve().parent / "report_map.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n{passed}/{len(rows)} pass")
    return 0 if passed == len(rows) else 1


if __name__ == "__main__":
    raise SystemExit(main())
