---
name: mind-map
description: >
  From a paper, proposal or project record, build and audit a real source-linked mind map:
  typed parent/cross-branch relations, fact/summary/inference provenance, evidence locators,
  optional supplied URLs, priorities, a measured non-overlapping deterministic layout, and
  editable SVG, FreeMind, offline HTML and JSON artifacts. Use when the deliverable is a
  structured visual reading artifact rather than a prose summary or nested bullet list.
  Missing evidence is marked, never linked to an invented source.
---

# mind-map

## What this skill produces

One run writes real diagram artifacts, not just findings about an abstract tree:

| artifact | actual content |
|-|-|
| `mindmap.svg` | editable vector graph: measured node rectangles, hierarchy links, dashed typed cross-relations, provenance-kind colors, priority marks, full labels/evidence in accessible attributes |
| `mindmap.mm` | standard editable FreeMind XML with one root, nested hierarchy, evidence/kind attributes and `<arrowlink>` relations |
| `mindmap.html` | offline clickable inspection page: the same SVG, Fit/Actual controls and evidence display on node click; no CDN or network script |
| `mindmap.json` | normalized nodes, hierarchical relations, typed edges and source locator map |
| `layout.json` | node boxes, viewport, overlap pairs and boundary violations |
| `result.json` | status/findings, artifact/source map, original `case_id`, all `output_contract` fields |

Trigger when the task is a **paper/review structure map, experimental route, project plan, meeting
decision map or concept map** that must be openable, readable, editable and traceable. Do not use it
for free prose or a generic bullet outline; those need no graphical relation semantics.

## Runtime contract

- Read `/input/case.json` and `/input/task.md`; never infer material content from the task label.
- Extract the original `case_id`, full `output_contract`, requested map domain and any case-specific
  output fields. `/input` is read-only; work under `/app/work`; deliver under `/app/output`.
- Every exit writes `result.json`, including refusals. `output_contract` values the case itself
  carries pass through untouched; audited fields are filled from real results; unknown fields are
  `null` and named in `limits`. A list of field names is accepted.
- Node evidence must point at the real page/section/table/task locator. `source_url` is emitted as
  a hyperlink **only** if it is a supplied `http(s)` URL; no URL is generated from a title or DOI.
- The semantic question — whether materials really support a node/edge — still needs the Agent to
  read the paper. The engine proves structure and locators, not scientific truth.

## Input shape

```json
{
  "case_id": "opaque-original-id",
  "section": "mindmap",
  "title": "reading map title",
  "max_depth": 4, "max_nodes": 150, "max_children": 12,
  "nodes": [
    {"id": "r", "label": "paper or project"},
    {"id": "q", "label": "research question", "parent": "r",
     "evidence": "Abstract p.1", "kind": "summary", "priority": 2,
     "parent_kind": "contains"},
    {"id": "m", "label": "paired measurement method", "parent": "r",
     "evidence": "Sec 2.1 p.3", "kind": "fact",
     "source_url": "https://only-a-supplied-real-url.example/paper"},
    {"id": "f", "label": "measured increase", "parent": "r",
     "evidence": "Fig 3b p.7", "kind": "fact", "priority": 1}
  ],
  "edges": [
    {"from": "q", "to": "m", "kind": "dependency", "basis": "Task record R1 p.1"},
    {"from": "m", "to": "f", "kind": "support", "basis": "Fig 3b p.7"}
  ],
  "output_contract": {
    "case_id": "……", "status": "……", "svg": "……",
    "layout": "……", "sources": "……"
  }
}
```

- `kind` on a node is `fact` / `summary` / `inference`; a root/heading may omit it as structural.
  `evidence_exempt` is only for a genuinely structural no-source node, never to hide missing evidence.
- An edge `kind` is one of `causal`, `dependency`, `contrast`, `temporal`, `citation`, `support`,
  `conflict`, `contains`, `part_of`, and must carry a source `basis`. The hierarchy relation may be
  set with `parent_kind`; default `contains`. An unnamed arrow is not a relation.
- `priority` (`0..3`, 1/2/3 highlighted) marks the small number of take-away nodes. Priority is
  visual emphasis, not claimed scientific importance.
- Optional `order` gives deterministic sibling order. The source order is the deterministic default.

## Run

```bash
python3 /skills/weekly-skill/scripts/secrun.py \
  --spec /app/work/map_spec.json --out /app/output
```

Optional original case-id override for an awkward input:

```bash
python3 /skills/weekly-skill/scripts/secrun.py \
  --spec /app/work/map_spec.json --out /app/output --case-id ORIGINAL-001
```

Exit/status:

| exit | status | meaning |
|-|-|-|
| 0 | clean | graph structurally valid and real artifacts generated |
| 3 | review | non-fatal provenance/label/priority/relation finding; artifacts still generated |
| 4 | blocked | invalid tree/reference/layout or artifact failure; no forged SVG |
| 5 | undetermined | unreadable/non-object spec, unknown section, missing spec; structured result |

## Layout and visual mechanism

Reference: [markmap/markmap](https://github.com/markmap/markmap), `markmap-view` 0.18.13 (MIT).
This package does not embed markmap/d3; it independently implements the relevant measured packing:

1. Measure wrapped label + evidence into a node rectangle.
2. Pack every subtree into a finite span; allocate disjoint spans for children.
3. Use 22 units between siblings and an extra 24 units above/below each non-root subtree, so
   unrelated branches are visually farther apart than siblings.
4. Place each depth after the previous depth's widest measured rectangle (100-unit horizontal gap).
5. Recompute the viewport from actual right/bottom bounds.
6. Independently test every pair of boxes for intersection and every box/text line for boundary
   escape. A failed layout is an artifact failure, not a drawable partial.

The result is deterministic: no clock, random jitter, hash order or machine path enters any artifact.
SVG uses `<title>` and data attributes for full labels/evidence; long visible labels wrap and end
with `…` while the full source label remains accessible in JSON/SVG attributes.

### Optional raster preview

SVG is the actual editable preview and HTML is an offline interactive renderer. If a task explicitly
requires PNG, only generate it with a real renderer:

```bash
python3 scripts/render_preview.py --svg /app/output/mindmap.svg --png /app/output/mindmap.png
```

The helper tries `rsvg-convert`, then `inkscape`, then Python CairoSVG, verifies the PNG magic bytes,
and exits 6 if none succeeds. It never renames SVG to PNG or claims an unproduced preview. PDF can be
produced from the same SVG with the runtime's supplied renderer under the same honesty rule.

## Audit rules

### Tree and scale

| rule | severity | what it proves |
|-|-|-|
| `map.no_nodes` | high | nothing was mapped |
| `map.duplicate_node_id` | high | IDs are not unique, so parents/edges are ambiguous |
| `map.label_missing` | high | a node does not name a concept |
| `map.root_count` | high | not exactly one root |
| `map.dangling_parent` | high | a node points at a missing parent |
| `map.cycle` | high | graph contains a cycle |
| `map.too_deep` | medium | branch exceeds declared depth |
| `map.duplicate_sibling` | medium | siblings reuse a label |
| `map.wide_node` | low | one parent exceeds declared granularity |
| `map.too_many_nodes` | medium | map exceeds declared node budget |

### Relations and provenance

| rule | severity | what it proves |
|-|-|-|
| `map.edge_incomplete` | high | edge lacks source or target |
| `map.edge_dangling` | high | edge endpoint does not exist |
| `map.edge_self` | medium | relation loops to itself |
| `map.edge_type_missing` | high | edge names no relation type |
| `map.edge_type_unknown` | medium | relation outside declared vocabulary |
| `map.edge_no_basis` | high | edge has no source locator |
| `map.parent_relation_unknown` | medium | hierarchical relation is outside vocabulary |
| `map.leaf_without_evidence` | medium | leaf has no source pointer |
| `map.kind_undeclared` | medium | evidence-bearing node omits fact/summary/inference |
| `map.kind_unknown` | low | provenance kind outside the three |
| `map.decorative_label` | medium | placeholder word rather than a concept |

## Delivery and evidence

`result.artifacts` and `result.sources` describe/contain only generated/supplied data. `checked`
includes node count, edge count, overlap-pair count and boundary-violation count. `layout.json` holds
the exact node boxes; `mindmap.json` holds the reconstructed hierarchy, relation types/bases and
source map; `revision`/`change_log` should be maintained by the calling Agent when it actually edits
the map, rather than fabricated by the renderer.

The caller should preserve supplied chapters/paper page numbers as locators. If PDF extraction is
needed, use the environment's PDF tool first and feed the actual extracted locator/prose. The map
renderer never invents missing source text, page numbers, evidence, DOI or URL.

## Failure and limits

- A second root or cycle: exit 4, no SVG. Fix the actual hierarchy; do not connect nodes arbitrarily.
- Duplicate/missing node ID/label: exit 4. Assign stable IDs and real concept labels.
- Unknown link type: exit 3; extend vocabulary only when the material supports the distinction.
- A high finding or layout failure leaves `result.json` and any earlier honest work, but not a fake
  SVG.
- Exact viewport proof applies to node boxes and text lines. Relation labels use the white halo and
  short relation names; full basis remains in edge attributes and the title/source map, avoiding
  long labels obscuring nodes.
- Decorative labels are a conservative exact-match list; a short real concept is not penalised.
- Node/edge relation semantics and source support are not semantically verified.
- SVG/HTML are editable and openable; PNG/PDF claim only when a real renderer wrote valid bytes.
- The map is not a substitute for the full paper or a replacement for the written argument.

## Verification

```bash
python3 scripts/bench_map.py        # 24 scenarios: every audit rule + false-positive guards
python3 scripts/bench_sections.py   # 51 cross-section regression/FP scenarios
python3 scripts/bench_render.py     # 19 XML/structure/bounds/determinism/preview scenarios
```

The render suite independently reparses SVG geometry, verifies zero overlap and viewport bounds
(including a 31-node stress tree), checks single-root FreeMind/arrowlinks, long-label XML escaping and
full accessible labels, provenance/priority marks, real supplied URLs, blocked bad graphs, contract
echo/null handling and honest no-renderer PNG behavior. Clean baselines report nothing; synthesized
examples are explicitly labeled and are not presented as official evaluation results.

## Requirements

Python 3.9+ standard library for map generation and audits. No third-party runtime dependency is
required. Optional PNG conversion requires one of rsvg-convert, Inkscape or CairoSVG that actually
exists in the execution environment; its absence is an explicit exit 6, not a fabricated artifact.
