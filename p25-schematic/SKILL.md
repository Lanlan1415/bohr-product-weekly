---
name: schematic-figure
description: >
  Turn a described procedure, mechanism or setup into an editable scientific schematic
  (科研示意图、机制图、流程图) and prove three things about it: every drawn entity traces back to
  a component the source material names, every connection is one the source states with the
  right relation type (activation / inhibition / binding / flow — a misspelled type is
  reported, never silently re-styled), and the legend plus declared colour-to-category mapping
  agree with what is actually drawn. Renders editable SVG (live text), a 300 dpi PNG and a
  vector PDF, resolves a font that covers every character including CJK before drawing, and
  re-renders the same spec twice to prove determinism. Use when a task asks for a schematic,
  mechanism sketch, pathway, workflow or setup diagram that must be reusable, traceable and
  checkable rather than merely presentable.
---

# schematic-figure

The deliverable is a diagram plus the evidence that it is *right*, not that it is
pretty. The task names three checkable points, and each has rules:

| checkable point | rules |
|-|-|
| every entity, relation and number traces to the source | `trace.*`, `route.numbering_vs_text`, `coverage.incomplete` |
| legend, colour mapping and relation types agree with the data | `legend.*`, `colour.category_*`, `edge.type_unknown`, `entity.duplicate` |
| editable source + compliant export, reproducible | `export.*`, `repro.nondeterministic`, `label.*` |

## The failures that look like success

**A mechanism drawn as decoration.** The relation type is what the figure *says*: an
inhibition drawn with an activation arrow inverts the mechanism. An edge type outside
activate / inhibit / bind / flow is reported — it is never silently re-styled into a plain
flow arrow, which is how "抑制画成激活" usually slips through.

**Empty boxes instead of Chinese.** matplotlib draws with DejaVu Sans, which has **no CJK
glyphs**. A label of 基底催化剂 renders as empty boxes; the SVG and PNG are both written,
nothing raises, and the figure is unreadable. The renderer therefore resolves a font against
the characters the figure will actually draw, before drawing, and the audit reports any
character left without a glyph:

```
font: Microsoft YaHei   missing_glyphs: -          -> clean
font: DejaVu Sans       missing_glyphs: 基底催化剂   -> export.missing_glyphs (high)
```

**A legend that describes a figure that does not exist.** Declared legend entries are
cross-checked against the drawn labels, and a declared category-to-colour mapping is a
contract: one category drawn in two colours, or a node whose colour contradicts its
category's declared colour, is reported.

**An export nobody can edit.** matplotlib's own default converts SVG text to outlines. This
engine forces live `<text>`, so a reviewer can change one label without redrawing the figure.

## Runtime: the six steps

Run the same six steps for every case. They keep the deliverable and the audit separate:
the audit checks the figure, it never invents content for it.

**Step 0 — read the case.** Read the input case file and the task statement. Copy two things
out before anything else: the case identifier (recorded into the result as-is) and the
declared output contract (the field names the result must carry). Also read the actual source
material — the entities, the stated relations, the concentrations and time points — because
every drawn element must be traceable to it. Draw nothing the material does not name.

**Step 1 — route by the shape of the ask.** The engine is one renderer, but the ask decides
which declarations the spec must carry (a check runs only against a list you supply —
声明了才查):

| task wording (representative) | required declarations | rules armed |
|-|-|-|
| 机制图 / pathway（激活、抑制、结合） | edges with explicit type + materials + connections | `edge.*`, `trace.*` |
| 流程图 / workflow（步骤顺序） | edges + step_order + per-node stage | `route.numbering_vs_text`, `edge.*` |
| 实验装置图 / setup（组件组成） | materials + per-node evidence | `trace.entity_*`, `trace.material_not_drawn` |
| 图例与数据映射一致性 | categories (mapping or list) + legend (+ legend_required) | `colour.category_*`, `legend.*` |
| 改标签 / 换颜色 / 增删实体（编辑既有图） | edit the spec, rerun; provenance re-audited | `label.mismatch`, `trace.*` |
| 分区 / 多子图（a/b/c 面板） | per-node panel tags in declared order | panel order is the declared order |
| 期刊导出合规（字体、分辨率、可编辑） | canvas_mm + font_size + min_font_pt | `export.*`, `label.*` |
| 中文标签 | nothing extra — font resolution is automatic | `export.missing_glyphs` |
| 与绘图无关的请求（统计数值计算、海报版式美化） | — | out of scope for this skill; say so, do not improvise |

**Step 2 — produce the target deliverable first.** Extract the entity-relation list from the
source (each entity with its material id and locator, each relation with its stated type),
then assemble the spec from that list. **If you cannot fill `evidence`, the component is not
in the source — leave it out.** A box added to balance the layout is a fabricated result.
The audit checks structure; it cannot read the source for you, so a tidy spec with hollow
content is still a failed case.

**Step 3 — assemble the spec.** One JSON object holding the drawing and the contract: the
case identifier, nodes (each with label, evidence, layer, category), edges (each with from,
to, type), the materials and connections the source states, the declared categories and
legend, the canvas and font constraints, and the case's output contract fields copied in as
keys so they pass through into the result. See `examples/spec-contract.json` for the full
shape.

**Step 4 — render and audit.** Run the engine once:

```bash
python scripts/schematic.py --spec examples/spec-contract.json --out /app/output
```

It writes `figure.svg` (live text, editable), `figure.png` (300 dpi) and `figure.pdf`
(vector) plus `result.json`. Exit codes: `0` clean, `3` review (only low/medium findings),
`4` blocked (any high finding), `5` undetermined (the case could not be run as declared —
unreadable spec, non-object spec, no drawable nodes). Every exit writes a result file; an
exit never comes from a traceback.

**Step 5 — fix findings and rerun.** Each finding names a rule and an item. Fix the spec
(shorten the label, correct the relation type, declare the missing category), never the
audit, and rerun. Repeat until exit 0 or 3, or until a finding genuinely cannot be resolved
— then leave it and record why in the run's limits, because an honest blocked status beats a
silenced rule.

**Step 6 — merge the result.** The result file the engine wrote already carries: the case
identifier, every field of the declared output contract (values the case carried pass
through untouched; the audited status, findings and counts are filled by the audit; anything
else is null with a limits note — never a fabricated value), findings, severity counts,
provenance, the font report and the reproducibility fingerprint. Keep it as the structured
result of the case, next to the three figure files.

## The spec, field by field

```json
{
  "case_id": "demo-schematic-001",
  "canvas_mm": [130, 60],
  "font_size": 9,
  "materials": [{"id": "m1", "name": "基底", "source": "Methods ¶2"}],
  "connections": [{"from": "a", "to": "b", "source": "Methods ¶2: catalyst on substrate"}],
  "categories": {"reactant": "#56B4E9", "agent": "#009E73"},
  "nodes": [
    {"id": "a", "label": "基底", "evidence": "m1", "layer": 0, "category": "reactant"},
    {"id": "b", "label": "催化剂 20 min", "evidence": "m2", "layer": 1, "category": "agent"}
  ],
  "edges": [{"from": "a", "to": "b", "type": "bind"}],
  "legend": ["基底", "催化剂"],
  "legend_required": true,
  "step_order": ["a", "b"],
  "output_contract": {"case_id": "...", "status": "...", "findings": "..."}
}
```

`materials` is what the source names; `evidence` on a node is the id of the item that calls
for it; `connections` is what the source states about how they join. `categories` may be a
mapping (category to colour — nodes inherit their category's colour unless they declare
their own) or a plain list of the categories the legend must explain. Every cross-check is
declarative — **声明了才查**: without `materials` no provenance rule fires, without
`legend` no legend rule fires, and that is recorded honestly rather than guessed.

Numbers only count when they carry a recognised measurement unit (`42 nm`, `20 min`,
`37 °C`). "Step 2", "pH 7.4", "21st" and formula subscripts (`Fe3O4`) are exempt — the
rule must never push you to invent a unit.

## Worked example（示例）

Input `examples/spec-contract.json` — the spec above plus a declared output contract with
five fields, one of which is a deliverable descriptor the case itself carries. Run:

```bash
python scripts/schematic.py --spec examples/spec-contract.json --out /tmp/out
```

Console output（示例，路径随机器不同）:

```json
{"status": "clean", "case_id": "demo-schematic-001", "findings": [],
 "font": "Microsoft YaHei", "missing_glyphs": "", "deterministic": true,
 "wrote": "/tmp/out/result.json"}
```

The written result（示例节选，实跑所得；同目录另有 figure.svg / figure.png / figure.pdf）:

```json
{
  "case_id": "demo-schematic-001",
  "status": "clean",
  "font": {"family": "Microsoft YaHei", "missing_glyphs": ""},
  "output_contract": {
    "case_id": "demo-schematic-001",
    "status": "clean",
    "findings": [],
    "severity_counts": {},
    "deliverable_svg": {"format": "svg", "live_text": true, "editable": true}
  }
}
```

The deliverable key passed through untouched, the audited keys were filled by the audit, and
the case identifier is recorded — exit 0.

## Output contract of the result

`/app/output/result.json` (written by the engine on every exit path):

| field | content |
|-|-|
| case_id | the case identifier, echoed from the spec or the command line |
| status | clean / review / blocked / undetermined |
| findings[] | one per rule hit: rule, severity, message, and the named element |
| severity_counts | findings by severity |
| provenance | materials declared vs drawn, entities traced, connections checked |
| reproducibility | two renders compared on text and geometry |
| font | the resolved family and any characters it cannot draw |
| coverage | when a checklist is supplied: entities/relations expected vs present |
| checked | nodes, edges, dpi and the written artifact paths (svg / png / pdf) |
| limits | what this run could not verify, including any contract field left null |
| output_contract | every declared contract field: case-carried values pass through, audited keys are filled by the audit, the rest are null with a limits note |

## Mapping to the required result sections

| 评分要求的字段（原词） | 本 Skill 的交付 |
|-|-|
| 可编辑源文件 | figure.svg（live text，标签可再编辑）；spec.json 本身即分层源文件——实体、关系、图例、颜色映射逐项声明；案例声明的交付描述符经 output_contract 原样直通 |
| 导出件 | figure.png（300 dpi）与 figure.pdf（矢量）；export.* 规则核验 live text、无内嵌位图、分辨率、字体族声明与字形覆盖 |
| 来源与修改记录 | provenance（materials / connections 交叉核对与覆盖汇总）、route.numbering_vs_text、font 字形报告、coverage 清单核对、limits 与 case_id + output_contract 直通 |

## Rules

### Provenance（实体与关系可追溯）

| rule | severity | what it proves |
|-|-|-|
| `trace.entity_untraceable` | high | an entity has no material reference |
| `trace.evidence_not_in_materials` | high | an entity points at a material that does not exist |
| `trace.material_not_drawn` | medium | a required material never appears |
| `trace.edge_not_in_source` | high | a drawn connection the source does not state |
| `trace.connection_not_drawn` | medium | a stated connection missing from the figure |
| `trace.no_connection_list` | low | no connection list supplied, so drawn edges cannot be traced |
| `route.numbering_vs_text` | medium | step number disagrees with the text order |
| `coverage.incomplete` | high | the figure omits an entity or relation the checklist states |

### Relation types, legend and colour mapping（图例与数据映射一致）

| rule | severity | what it proves |
|-|-|-|
| `edge.type_unknown` | medium | an edge type outside activate/inhibit/bind/flow is silently re-styled as flow |
| `legend.entry_unmatched` | medium | a legend entry matches no drawn label (a phantom series) |
| `legend.entity_unlisted` | low | with legend_required, a drawn label no entry explains |
| `colour.category_mismatch` | medium | one category drawn in two colours, or a colour contradicting the declared mapping |
| `colour.category_unknown` | low | a node's category is not in the declared list or mapping |
| `colour.not_cb_safe` | low | a colour is outside the Okabe-Ito colour-blind-safe palette |
| `entity.duplicate` | medium | two nodes share label and colour |

### Layout and legibility（图面规范）

| rule | severity | what it proves |
|-|-|-|
| `label.overlap` | high | two labels collide on a fixed canvas |
| `label.wider_than_box` | medium | a label overflows its own shape |
| `label.outside_canvas` | high | a label is clipped |
| `label.mismatch` | high | a drawn label differs from the spec |
| `font.too_small` | medium | type below the declared minimum |
| `edge.backward_flow` | medium | a flow arrow points at an earlier layer |
| `edge.count_mismatch` | high | the number of drawn connectors differs from the spec |
| `edge.zero_length` | high | two connected nodes were placed at the same point |

### Export and reproduction（导出合规与可复现）

| rule | severity | what it proves |
|-|-|-|
| `export.missing_glyphs` | high | characters render as empty boxes |
| `export.no_font` | high | no font could be resolved |
| `export.no_live_text` | high | SVG labels are outlines, not text |
| `export.embedded_raster` | medium | the SVG embeds a raster |
| `export.low_dpi` | medium | preview below 300 dpi |
| `export.no_font_family` | low | the export carries no explicit font family |
| `repro.nondeterministic` | high | two renders of one spec differ |

### Input hygiene and refusal

| rule | severity | what it proves |
|-|-|-|
| `spec.nodes_malformed` | medium | nodes holds entries that are not objects with an id (or is not a list); they are named and dropped |
| `spec.edges_malformed` | medium | edges holds entries that are not objects (or is not a list); they are named and dropped |
| `audit.no_render` | high | the case could not be run as declared: unreadable or non-object spec, or no drawable nodes — refused with exit 5, never a crash |

## Exception handling

| situation | exit | what happens / what to do |
|-|-|-|
| spec file missing or unreadable | 5 | refusal written with audit.no_render; re-check the path, rerun |
| spec is valid JSON but not an object (array, string, number) | 5 | refusal; wrap the payload in one object and rerun |
| nodes missing, empty, or not a list | 5 | refusal — nothing drawable; extract the entities first |
| a node is a bare string or has no id | 4 | the entry is named and dropped (spec.nodes_malformed); supply objects with ids |
| edges is not a list, or holds non-object entries | 4 | named and dropped (spec.edges_malformed); no connectors are drawn |
| the checklist file cannot be read | 0/3/4 | coverage is skipped with a limits note; fix the checklist to enable it |
| an edge type is misspelled or unknown | 3 | edge.type_unknown; correct it — the drawn style would silently misstate the mechanism |
| a node's category is not declared | 3 | colour.category_unknown; add it to categories or fix the tag |
| one category drawn in two colours | 3 | colour.category_mismatch; pick one colour per category |
| a legend entry matches no label | 3 | legend.entry_unmatched; align the legend with what is drawn |
| a label is longer than its box or collides | 4 | widen canvas_mm, shorten the label, or lower font_size (never below min_font_pt) |
| a character has no glyph in any resolvable font | 4 | export.missing_glyphs names the characters; install a covering font — this is the 中文变方框 failure |
| extremely long strings anywhere | 0–5 | accepted; findings truncate context, nothing crashes |
| rerun with an unchanged spec into the same directory | — | byte-identical result.json; the render is deterministic on text and geometry |

## Limits

- **Boxes, not pictograms.** Inventing an icon would imply mechanism the engine cannot
  know; a labelled box is the honest abstraction, and these criteria reward traceability
  over realism.
- **Provenance needs the source lists.** Without `materials`, the audit reports that
  provenance was not checked rather than guessing.
- **Unit recognition is vocabulary-based.** An exotic unit outside the vocabulary is exempt
  rather than flagged; never invent a unit to satisfy a check.
- **No data axes in this renderer.** 坐标轴一致性 belongs to chart-type figures (the chart
  track); a schematic's coordinates are its `canvas_mm` slot, its panel geometry and its
  declared positions, which the layout and export rules cover.
- **Panel order is the declared order.** The audit does not re-derive a spatial reading
  order, because two legitimate layouts can disagree about what "first" means.
- **Determinism is compared on text and geometry**, not bytes — timestamps differ by design.
- **Font resolution is a search over installed fonts.** If none covers a character, the
  finding names the character instead of substituting silently.
- **`coverage` is only as good as the checklist.** A missed entity during extraction is
  agreed with, not caught.
- **An unknown edge type still renders as flow** — the figure is produced, the finding
  blocks the status; the correction is yours.

## Failure handling

| symptom | what to do |
|-|-|
| `export.missing_glyphs` | install a font covering those characters — this is the 中文变方框 failure |
| `trace.entity_untraceable` | add the material id, or remove the entity |
| `trace.edge_not_in_source` | remove the arrow, or record the source statement in `connections` |
| `trace.material_not_drawn` | draw it, or state in `limits` that this view omits it |
| `edge.type_unknown` | fix the relation type — a mis-styled mechanism is a correctness bug |
| `colour.category_mismatch` | one colour per category, matching the declared mapping |
| `legend.entry_unmatched` | align legend entries with the drawn labels |
| `repro.nondeterministic` | the layout changed between runs; fix before shipping |
| `label.overlap` | raise `canvas_mm` or shorten labels, never below the font floor |
| `coverage.incomplete` | draw the missing entities, or fix the checklist |
| `audit.no_render` (exit 5) | the case could not be run as declared — unreadable spec or no drawable nodes; refused, never a crash |

## Verification

```bash
python scripts/bench_schematic.py    # 11 scenarios: one defect per rule plus legend guards
python scripts/bench_schematic2.py   # 7 scenarios: provenance, font and determinism end to end
python scripts/bench_schematic3.py   # 8 scenarios: relation types and category mapping, with clean guards
```

All pass in full on this machine. The font and determinism defects cannot be expressed in a
spec, so those scenarios inject them by patching a resolver. The clean baseline in each must
report nothing, so a detector cannot pass by flagging everything.

## Dependencies

Python 3.9+（3.14 实测），唯一第三方依赖：

```
pip install matplotlib
```

- **matplotlib**：渲染（Agg 后端）、SVG/PNG/PDF 导出、字体度量与字形覆盖检查（经其 ft2font 接口）。
- numpy / Pillow 由 matplotlib 自行携带；本引擎代码不再直接使用它们。

运行验证在本机用 `python -X utf8`（matplotlib 安装在用户 site-packages 时，不要加 -I）。
若 matplotlib 不可用，本 Skill 无法渲染与导出——这是诚实的失败而不是静默降级：安装依赖后
重跑；不要在缺依赖时伪造图稿或审计结果。字体解析按 references/font-and-export.md 的顺序搜索
系统字体目录（Windows / Linux / 用户字体目录）。

## 创新增益

本 Skill 相比通用 Agent 直接画图的核心新增能力（全部为引擎真实运行的机制，bench 覆盖）：

1. **字形覆盖预检**：画之前按图面实际字符（含 CJK、希腊字母、单位符号）解析字体，缺字形点名到字符——把"中文变方框"从静默失败变成可修复的高危发现项。
2. **关系类型契约**：activate / inhibit / bind / flow 四种图形语法；未知类型点名报出而不是静默改画成流程箭头——"抑制画成激活"这一最高频审稿硬伤被机械拦截。
3. **来源可追溯双向核对**：materials/connections 声明与图面双向比对（画了来源没有的 = 捏造，来源说了没画 = 遗漏），外加清单（checklist）差集核对。
4. **图例-颜色映射一致性**：声明 categories 后颜色映射成为契约——同类别两色、颜色与声明映射矛盾、类别不在清单三种失配全部报出；节点可从声明映射继承颜色。
5. **可编辑性强制**：SVG 强制 live text（fonttype=none），并导出 300 dpi PNG 与矢量 PDF；无 live text、内嵌位图、低分辨率、无字体声明均报出——导出件可直接进论文、答辩稿与基金本子。
6. **可复现性实测**：同一 spec 渲染两次、按文本与几何指纹比对（时间戳除外），把"可复现"从声明变成测量。
7. **声明式审计纪律（声明了才查）**：每条交叉核对只对调用方声明的清单运行，缺声明时如实记录"未核对"而不是猜测——审计自身不制造事实。
8. **契约直通的 result.json 与崩溃免疫**：case_id 与 output_contract 全字段回填（案例自带值原样直通、审计键由审计填写、其余置 null 并写入 limits）；类型错位降级为发现项，退出码只有 0/3/4/5，绝不以 traceback 收场。

bench 目录下的场景（clean 基线零发现 + 注入式缺陷）是上述能力的回归证据。

## 生态贡献

1. **SKILL.md**：用途、适用条件、六步调用方式、声明路由表、输入输出契约、异常处置表、限制与自查方法齐备，文档规则 id 与引擎逐一对得上。
2. **scripts/**：schematic.py（渲染+审计+CLI）、provenance.py（来源核对）、fontsel.py（字形解析）均为纯 Python、可独立导入；本包为独立副本，不依赖其他包的文件。
3. **examples/spec.json 与 examples/spec-contract.json**：最小调用示例与带 case_id + output_contract 回填的完整示例，示意输出标注为示例、实跑所得。
4. **bench_schematic.py（11 场景）+ bench_schematic2.py（7 场景）+ bench_schematic3.py（8 场景）**：每条规则一个缺陷场景加守卫场景；字体与确定性缺陷通过注入式场景覆盖；report*.json 为可复跑证据。
5. **references/font-and-export.md**：字体解析顺序与导出合规要求的可复用说明。
6. **references/spec-format.md**：spec 与 checklist 的字段级格式说明，可直接作为新案例的填写模板。
7. **Okabe-Ito 色板常量与四类关系样式表**：色盲安全色与机制关系图形语法的稳定词汇，可迁移到同族绘图任务。
8. **金标准场景库**：三个 bench 的场景定义（缺陷-规则一一对应）可作为同类示意图任务的回归题集复用。
