---
name: mind-map
description: >
  Audit a mind map extracted from a paper: tree integrity (one root, no cycles, bounded
  depth), sibling discipline, a source pointer on every leaf, and — because a map asserts
  relations the paper may not — every edge must name its relation type (causal, dependency,
  contrast, temporal, citation, support, conflict, contains) and carry a locator into the
  source. Evidence-bearing nodes must say whether they carry a fact, a summary or an
  inference. Placeholder labels and node-count explosions are reported. Use when the
  deliverable is a structured reading artifact that must be verifiable against its source.
---

# mind-map

A map that has two roots or a cycle is not a summary of the paper's structure. A leaf with
no source is an assertion nobody can trace. And an edge between two nodes is a claim about
the material — "A causes B" may exist only in the map, never in the paper. That last
failure is the one this skill exists for: tree integrity is necessary, but the task's own
scoring points are about what the map asserts and whether the material backs it.

| scoring point (题面) | rules |
|-|-|
| 抓得准 — key concepts, not decorative words | `map.decorative_label` |
| 理得清 — root, hierarchy, sibling granularity | `map.root_count`, `map.duplicate_sibling`, `map.wide_node`, `map.too_deep` |
| 连得对 — typed, source-backed relations | `map.edge_type_missing`, `map.edge_type_unknown`, `map.edge_dangling`, `map.edge_incomplete`, `map.edge_self`, `map.edge_no_basis` |
| 证据可追溯 — fact vs summary vs inference | `map.leaf_without_evidence`, `map.kind_undeclared`, `map.kind_unknown` |
| readable scale | `map.too_many_nodes`, plus the tree rules `map.cycle`, `map.dangling_parent`, `map.no_nodes` |

## Workflow

### 1. Declare the structure, the relations and the provenance kinds

```json
{"section": "mindmap", "max_depth": 4, "max_nodes": 150, "max_children": 12,
 "nodes": [
   {"id": "r", "label": "porous coating study"},
   {"id": "q", "label": "research question", "parent": "r", "evidence_exempt": true},
   {"id": "m", "label": "uptake measurement", "parent": "r",
    "evidence": "Sec 2, p.5", "kind": "fact"},
   {"id": "f", "label": "coating raises uptake 3-fold", "parent": "m",
    "evidence": "Fig 3b, p.7", "kind": "fact"},
   {"id": "s", "label": "surface-area mechanism", "parent": "f",
    "evidence": "p.8 discussion", "kind": "inference"}],
 "edges": [
   {"from": "m", "to": "f", "kind": "support", "basis": "Fig 3b, p.7"},
   {"from": "q", "to": "m", "kind": "dependency", "basis": "Sec 2, p.5"}]}
```

- `kind` on a node: `fact` (the material states it) | `summary` (condensed from the
  material) | `inference` (the map's own reading). A node that renders its inference as a
  quoted fact misrepresents the paper — this is the distinction the task asks for.
- `kind` on an edge: one of `causal`, `dependency`, `contrast`, `temporal`, `citation`,
  `support`, `conflict`, `contains`, `part_of`.
- `basis` on an edge: a locator into the source (page, section, table cell, figure) — the
  connection must be checkable against the material, not just drawable.
- `evidence_exempt` marks structural branches (the research question, a heading) that
  carry no citation by design.

### 2. Audit

```bash
python scripts/secrun.py --spec spec.json --section mindmap --out /app/output
```

Exit codes: `0` clean, `3` review, `4` blocked.

Writes `/app/output/result.json` with `status`, `findings[]` (rule, node/edge, locator),
`severity_counts`, `checked` and `limits`. If the case declares an `output_contract`, its
keys are echoed and any that cannot be derived are named in `limits`.

## Rules

### Tree integrity

| rule | severity | what it proves |
|-|-|-|
| `map.no_nodes` | high | nothing was mapped |
| `map.root_count` | high | not exactly one root |
| `map.dangling_parent` | high | a node points at a missing parent |
| `map.cycle` | high | the graph contains a cycle, so it is not a tree |
| `map.too_deep` | medium | a branch exceeds the declared depth |

### Siblings and scale

| rule | severity | what it proves |
|-|-|-|
| `map.duplicate_sibling` | medium | two children of one parent share a label |
| `map.wide_node` | low | one parent carries more children than the declared granularity |
| `map.too_many_nodes` | medium | the map exceeds the declared node budget |

### Relations (连得对)

| rule | severity | what it proves |
|-|-|-|
| `map.edge_incomplete` | high | an edge has no start or no end |
| `map.edge_dangling` | high | an edge connects a node that does not exist |
| `map.edge_self` | medium | an edge loops a node to itself |
| `map.edge_type_missing` | high | an edge names no relation type |
| `map.edge_type_unknown` | medium | the type is outside the declared set |
| `map.edge_no_basis` | high | an edge carries no locator into the source |

### Provenance and labels (证据可追溯 / 抓得准)

| rule | severity | what it proves |
|-|-|-|
| `map.leaf_without_evidence` | medium | a leaf has no source pointer |
| `map.kind_undeclared` | medium | an evidence-bearing node does not say fact/summary/inference |
| `map.kind_unknown` | low | the kind is outside the three |
| `map.decorative_label` | medium | a node label is a placeholder word, not a concept |

## Limits

- **Structure and assertions are checked, not whether the branching matches the paper's
  argument.** A wrong-but-declared grouping passes; the audit proves the map is checkable,
  not that it is wise.
- **Decorative labels are an exact-match list** (其他, misc, TBD, placeholder, …). Real
  short concepts — `方法`, `结果`, `aims` — never fire; there is deliberately no length
  rule, because short is not the same as decorative.
- **A wide node is advice, not a defect**: severity low, and the threshold is yours
  (`max_children`). A node with twelve legitimate parallel experiments may be correct.
- **Edge types are a closed set.** A type outside it is reported, not guessed into one;
  extend the map's vocabulary only if the material supports the distinction.
- **Depth, node and children limits are yours to declare** (`max_depth`, `max_nodes`,
  `max_children`); defaults are 4 / 150 / 12.
- It does not read PDFs: extraction is a separate step; this audits the structure that
  comes out of it.

## Failure handling

| `audit.no_section` | high | the case could not be run as declared: no or unknown section, or the spec file is not readable JSON — refused with exit 5, never a crash |

| symptom | what to do |
|-|-|
| `root_count` / `cycle` / `dangling_parent` | fix the tree — one root, parents that exist, no loops |
| `edge_type_missing` | name what the connection means; an unnamed arrow is not a relation |
| `edge_no_basis` | add the locator that shows the connection in the material, or delete the edge — a connection the material does not support must not exist |
| `kind_undeclared` | mark the node fact / summary / inference; keep the map's own reading visibly distinct from the paper's |
| `decorative_label` | replace the placeholder with the concept the material actually names |
| `too_many_nodes` | group into higher-level branches; a map that dumps the source is not readable |

A finding names a rule and the item at fault. Fix the item; do not delete it to make the
finding disappear. If a finding is genuinely wrong for your case, state why in `limits`.

## Verification

```bash
python scripts/bench_map.py        # 21 scenarios: one per rule + false-positive guards
python scripts/bench_sections.py   # 51 scenarios: cross-section regression + FP guards
```

Both pass in full on this machine. Clean baselines and the FP guards must report nothing —
`方法` and `aims` stay silent, `其他` fires; `dependency`/`contains` edges pass, untyped
and unbased edges fire.
## Requirements

Python 3.9+（3.14 实测）。纯标准库实现，无第三方依赖。

## 创新增益

本 Skill 相比通用 Agent 的核心新增能力：

1. **规则优先级库**：每条修改有规则 id、优先级、适用条件和理由，两个规则冲突时由优先级决定胜者且双方都留痕——通用 Agent 无法自证规则一致性。
2. **幂等二遍检查**：同一规则跑两遍，第二遍必须零改动——如果仍有改动说明规则间存在冲突，这是一个可计算的 self-check。
3. **逐条变更台账**：每个值的修改记录规则/行/列/原值/新值/理由，审计者可以逐条复核或撤销任何单条修改。

bench 目录下的 map 是上述能力的回归证据（见 Verification 节 场景，clean 基线必须零发现）。

## 生态贡献

- **SKILL.md** 包含用途、适用条件、调用方式、输入输出、异常处理、限制和自查方法
- **scripts/** 纯标准库可独立导入，规则库可通过 spec 配置扩展
- **examples/** 提供最小调用示例和示意输出
- **bench/** 回归套件可独立复跑验证

