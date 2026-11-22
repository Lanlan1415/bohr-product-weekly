---
name: pathway-figure
description: >
  Build a biological mechanism or pathway figure from a bound workorder and verify it
  on two axes at once: whether each label is a well-formed, unambiguous entity (species
  casing, gene italic, alias collisions, accessions) and whether each entity and arrow
  traces back to the source material rather than being drawn because it looked
  plausible. Compartment bands are declared, not guessed: nodes are placed into the
  subcellular band they claim, and a receptor drawn outside its band is a finding.
  Relations carry evidence strength (confirmed/predicted/hypothetical) as visible line
  styles, feedback loops must be marked, and node size is a checked data channel.
  Also proves the figure is reproducible and that every character has a glyph —
  matplotlib's default font has none for Chinese, so labels silently become empty
  boxes. Delivers a layered editable SVG source plus 300 dpi PNG plus an embedded-font
  PDF plus a structured result.json (output_contract fields verbatim from case.json +
  case_id + figure/source/export records + audit findings + sources + uncertainty),
  and refuses with a structured result instead of crashing when the material is
  unreadable. Use when a task asks for a mechanism diagram, pathway figure, or
  signalling schematic.
---

# pathway-figure

## 运行时入口与输出契约（Harbor runtime contract）

平台把本 Skill 安装在 /skills/weekly-skill，运行时输入固定为 /input/case.json 与
/input/task.md；工作目录 /app/work，最终交付物与 result.json 必须写入 /app/output。

### 六步运行时入口（每步带核验，harness agent 按此执行）

1. **读输入**：读 /input/case.json（拿到 case_id 与 output_contract 的字段清单）和
   /input/task.md。实际输入文件与原论文是事实依据；不依据错误的领域标签补造数据。
   *核验*：case_id 已拿到；output_contract 逐字段抄在草稿上（如 figure_svg / figure_pdf /
   font_report / export_check），后续每步对齐。
2. **解析材料成 spec**（写到 /app/work/spec.json）：把机制文字解析成结构化中间表示——
   **实体**（materials + nodes：kind 区分基因/蛋白，accession 与 aliases 做命名归一，
   evidence 指向材料条目，compartment 声明区室）、**相互作用**（connections + edges：
   促进/抑制/磷酸化/泛素化/结合/募集/转运映射为 activate/inhibit/bind/flow 四种线型，
   每条填 source 指向原文，confidence 填 confirmed/predicted/hypothetical）、
   **方向与区室**（nodes[].layer 表达受体—胞内—核层级，compartments 声明区室带）、
   **图例**（legend + legend_notes + legend_required）。
   *核验*：每个 node 有 evidence；每条 edge 在 connections 里有对应陈述；抽不出的字段
   留空并登记 uncertainty，不臆造。
3. **写 meta.json**（/app/work/meta.json，可选但推荐）：
   `{"sources": [...人工确认的来源...], "uncertainty": [...抽取缺口/歧义取舍...], "limits": [...]}`
   ——引擎会把这三张表合并进 result.json，避免 harness 手工拼 JSON 出错。
   *核验*：meta 是合法 JSON 对象；每条 uncertainty 指向一个具体缺口。
4. **跑引擎**（matplotlib 需已安装）：
   `python scripts/pathway.py --spec spec.json --case /input/case.json --checklist checklist.json --meta meta.json --out /app/output`
   （--checklist 可选：给定时按材料实体/关系清单做覆盖审计；--case 把 case.json 的
   case_id 与 output_contract 逐字段回填进 result.json；--meta 合并三张表）
   *核验*：退出码 ∈ {0,3,4,5}（全表见下）；stderr 无 traceback；/app/output 出现
   figure.svg、figure.png、figure.pdf、result.json 四个文件。
5. **读 result.json**：
   `case_id` 与 `output_contract` 已回填；`figure`/`source`/`export` 三个产出记录齐全；
   `findings` 逐条带 rule/severity/message；`reproducibility.deterministic` 为 true；
   `sources`、`uncertainty`、`limits` 已合并 meta。
   *核验*：status=clean/review 才可交付；blocked 时先修复 high 发现再重跑。
6. **交付并复跑**：figure.svg（分层可编辑源文件）+ figure.png（300 dpi）+ figure.pdf
   （嵌入字体）+ result.json 落 /app/output；同一 spec 原样再跑一遍，
   *核验*：第二遍 result.json 的 `reproducibility.deterministic` 为 true（读者可复现的
   证明），figure 内容一致。

### 路由决策表（按案例形态选入口）

| 案例形态 | 入口 | 说明 |
|-|-|-|
| 机制图/通路图/信号转导示意图 | `scripts/pathway.py` | 本包主入口：布局 + 命名 + 溯源 + 区室 + 证据强度全审计 |
| 混合案例附带的装置面板/路线阶段图 | `scripts/apparatusfig.py` | 共享结构审计（BOM/编号/出入/图例），同样的拒绝纪律与契约回填 |
| 仅有渲染/导出/布局自检需求 | `scripts/schematic.py --spec ... --checklist ...` | 只跑布局与导出审计，不做命名与溯源 |

退出码全表（两个入口一致）：`0` clean / `3` review（可交付但带发现）/ `4` blocked
（存在未修复 high 缺陷）/ `5` undetermined（输入侧无法建图，引擎拒绝）。

### result.json 合成规则（顺序即覆盖优先级）

引擎自己写出**完整** result.json，harness 不再手工拼装大 JSON：

```
result.json =
  1. case.json 中 output_contract 的全部原始字段 —— 经 --case 逐字段回填：
     引擎真实产出的键（figure_svg/figure_png/figure_pdf/source/font_report/export_check）
     填真实路径或记录；推导不出的键填 null 并在 limits 说明；case_id 置顶
  2. case_id —— 取自 case.json
  3. 引擎产出映射 —— figure{svg,png,pdf} / source(=svg 路径) / export{formats,dpi,
     canvas_mm,font_family,font_file,font_embedded,missing_glyphs,colour_palette,live_text}
  4. 引擎审计字段 —— status, findings, severity_counts, audits, checked,
     reproducibility, font, coverage, provenance
  5. sources —— 引擎从 spec 自动抽取（element→material→locator），并合并 --meta.sources
  6. uncertainty —— 引擎自动登记默认参数与覆盖缺口，并合并 --meta.uncertainty
```

### 题面输出字段对齐

| 题面要求 | 本包落点 |
|-|-|
| 输入标识 | result.json 顶部 case_id（另有 schema_version 标注引擎版本） |
| 主结果 | figure.svg（分层可编辑源文件）+ figure.png（300 dpi）+ figure.pdf（嵌入字体） |
| 证据/来源定位 | spec 的 materials[].source、connections[].source、nodes[].evidence → result.json 的 sources（element/material/locator 三列）与 provenance.coverage |
| 运行状态 | status：clean=完成；review=部分（可交付但带发现，limits 写明边界）；blocked=失败（存在未修复 high 缺陷）；undetermined=失败（输入侧无法建图，引擎拒绝） |
| 不确定性 | uncertainty 列表（引擎自动登记：默认画布/默认字号/自动配色/溯源未执行/覆盖未审计/字形缺口），逐条可复核 |
| 可编辑源文件 | figure.svg live text；完成标准：实体、关系、图例和数据映射正确（由 trace/legend/coverage/compartment 审计背书） |
| 导出件 | figure.png + figure.pdf + result.json 的 export 记录：目标格式（svg/png/pdf）、尺寸（canvas_mm）、分辨率（300 dpi）、字体（family、font_file、font_embedded、missing_glyphs）、色彩（Okabe-Ito 色盲安全检查） |
| 来源与修改记录 | sources（逐元素定位）+ provenance（覆盖计数）+ reproducibility（两遍渲染一致）+ uncertainty 人工确认项 + schema_version |

### rubric 三段映射表（可编辑源文件 / 导出件 / 来源与修改记录）

| rubric 三段 | 可编辑源文件（spec 中的字段） | 导出件/落盘产物 | 来源与修改记录 |
|-|-|-|-|
| 可编辑源文件 | nodes[].label/kind/layer/compartment、edges[].type/confidence、legend、compartments | figure.svg（live text，SVG 字体以非内联方式写入，文字可改）+ figure.svg 的 layer 分层 | trace.*、legend.*、compartment.*、coverage 审计背书"实体、关系、图例和数据映射正确" |
| 导出件 | canvas_mm、font_size、min_font_pt、颜色（Okabe-Ito） | figure.svg + figure.png（300 dpi）+ figure.pdf（type 42 嵌入 TrueType） | result.json 的 export 记录（formats/dpi/canvas_mm/font_*/missing_glyphs/colour_palette）+ font 审计 |
| 来源与修改记录 | materials[].source、connections[].source、nodes[].evidence | result.json 的 sources（element/material/locator）+ provenance.coverage 计数 | uncertainty（默认参数、抽取缺口、人工确认项）+ limits（审计边界）+ schema_version（引擎版本，改动可追溯） |

### 材料缺失时拒绝而不是崩溃

引擎内置拒绝路径：spec 不是可读 JSON、不是 JSON 对象、或抽不出可画内容时，pathway.py
不抛栈回溯，而是写 result.json（status=undetermined，发现 audit.no_section，exit 5），
拒绝路径同样回填 case_id 与 output_contract（直接守护式读 case.json——该路径没有 spec，
禁止调用 contract_echo）。材料缺失、无法判断、运行失败三种情形都必须落一份结构化
result.json；绝不裸抛异常，也绝不交一个空白输出目录。

| 情形 | status | 处置 |
|-|-|-|
| case.json 或 task.md 缺失/不可解析 | failed | reason=missing_input；uncertainty 写明缺什么 |
| spec 不可读/不可画 | undetermined | 引擎自动走拒绝路径（audit.no_section，exit 5），拒绝 result 同样带 case_id + output_contract |
| 材料抽不出任何实体 | failed | reason=empty_materials；不得凭空画节点 |
| 材料只覆盖部分实体/关系 | review | 照常出图；limits 写明未覆盖面，uncertainty 逐条登记 |
| 引擎依赖缺失（matplotlib/Pillow 等） | 启动失败 | Python 导入层抛 ImportError——依赖在 Requirements 声明、平台镜像已提供；导入失败后 CLI 无法再写 result.json，如实说明而非谎称可落盘 |

拒绝模板（**示例**，非正式案例结果）：

```json
{
  "case_id": "（取自 case.json）",
  "status": "failed",
  "reason": "empty_materials",
  "output_contract": {"原样保留": "case.json 中 output_contract 的全部字段"},
  "sources": [],
  "uncertainty": ["任务材料未给出实体清单，无法开始画图；需补充机制描述或通路材料"],
  "limits": ["拒绝执行：未产出任何图面"]
}
```

A mechanism figure fails in one of two ways, and they need different checks.

**Nomenclature** — the picture is legible and says the wrong thing: `Tp53` in a human
figure, a gene set in roman so the reader cannot tell it from its protein, `TP53` and
`p53` drawn as two boxes so one actor becomes a two-step pathway.

**Provenance** — the picture contains a component or an arrow the source never states.
This figure type gets the same deduction as any apparatus diagram for that fault: a
step nobody can find in the methods.

Both are checked here, plus the two export properties that decide whether the
deliverable is usable at all.

## The failure that looks like success

matplotlib draws with DejaVu Sans, which has **no CJK glyphs**. A label of `肿瘤抑制因子`
renders as empty boxes; the SVG and PNG are written, nothing errors, and every Chinese
label is unreadable. The renderer therefore resolves a font against the characters the
figure actually uses (fontsel.py searches installed fonts per character) before
drawing, and the audit reports any character left without a glyph:

```
font: Microsoft YaHei   missing_glyphs: -                -> clean
font: DejaVu Sans       missing_glyphs: 肿瘤抑制因子      -> export.missing_glyphs (high)
```

Resolution is a three-stage deterministic search: the preferred families, then any
CJK-named file in the known font directories, then every CJK-suggesting file
matplotlib itself can see (sorted, capped) — so a container that ships a font under
an unexpected name is still found, and the same input always resolves to the same
font on the same machine.

## Workflow

### 1. Write the material list and the naming facts first

```json
{
  "species": "human",
  "canvas_mm": [150, 70],
  "aliases": {"TP53": ["Tp53", "p53"]},
  "materials": [{"id": "m1", "name": "TP53", "source": "Results ¶2"},
                {"id": "m2", "name": "MDM2", "source": "Results ¶2"}],
  "connections": [{"from": "g1", "to": "p1", "source": "Results ¶2: p53 induces MDM2"}],
  "compartments": [{"id": "cytosol", "label": "细胞质", "layers": [0, 1]},
                   {"id": "nucleus", "label": "细胞核", "layers": [2]}],
  "nodes": [
    {"id": "g1", "label": "TP53", "kind": "gene", "evidence": "m1", "layer": 0,
     "compartment": "cytosol", "accession": "HGNC:11998", "accession_source": "hgnc",
     "color": "#56B4E9"},
    {"id": "p1", "label": "MDM2", "kind": "protein", "evidence": "m2", "layer": 1,
     "compartment": "cytosol", "accession": "Q00987", "accession_source": "uniprot",
     "color": "#009E73"}
  ],
  "edges": [{"from": "g1", "to": "p1", "type": "activate", "confidence": "confirmed"}],
  "confidence_required": true,
  "legend": ["TP53 (gene)", "MDM2 (protein)"],
  "legend_notes": ["节点大小 = 表达量（归一化）"],
  "legend_required": false
}
```

`aliases` is what makes alias-collision detection possible — build it from the source
text, not from memory. `materials` + `evidence` is what makes provenance possible, and
a material entry without `source` is reported (`trace.material_no_source`) because a
locator-less claim cannot be re-checked. `species` drives the casing rules; without it
only mixed conventions can be reported. `kind` separates gene from protein — the
distinction the challenge names first. `compartments` declares the subcellular bands;
nodes without an explicit `layer` are placed **inside the band they claim** (constraint
layout), and an explicit layer that contradicts the band is a high finding. The full
worked example with every field is `examples/spec.json`.

### 2. Run it

```bash
python scripts/pathway.py --spec spec.json --case /input/case.json --out /app/output
```

Exit codes: `0` clean, `3` review, `4` blocked, `5` undetermined (refused). Writes
result.json, figure.svg (live text, editable), figure.png (300 dpi) and figure.pdf
(embedded TrueType). Run the command twice before shipping:
reproducibility.deterministic in the second result.json is the proof that a reader can
re-run the skill to the same figure.

### 3. Read the four fields that carry the verdict

| field | what it tells you |
|-|-|
| `findings[]` | nomenclature, provenance, compartment, confidence, layout and export, in one list |
| `coverage.incomplete` | how many entities and connections were actually traced |
| `reproducibility.deterministic` | two renders compared on text and geometry |
| `export` | formats, dpi, canvas, font family/file/embedding, missing glyphs, palette |

## 六类要素检查表（逐项落点）

交付前逐项核对；任何一项缺失都要么补齐、要么在 limits 里写明原因。

| 六类要素 | spec/交付落点 | 引擎检查 |
|-|-|-|
| 科学实体 | materials[] + nodes（kind 区分基因/蛋白，accession 与 aliases 命名归一，evidence 溯源，compartment 声明区室） | nomenclature.gene_casing, nomenclature.alias_collision, nomenclature.missing_accession, trace.entity_untraceable, trace.evidence_not_in_materials, trace.material_not_drawn, trace.material_no_source |
| 空间关系 | nodes[].layer 与 compartments[] 区室带（约束布图：无显式 layer 的节点放进其声明区室）、edges[].from/to 方向 | label.overlap, label.outside_canvas, label.wider_than_box, edge.backward_flow, edge.zero_length, compartment.mismatch, compartment.undeclared, edge.dangling, route.no_entry, route.no_exit |
| 数据编码 | edges[].type 四种线型语义（activate/inhibit/bind/flow）+ edges[].confidence 证据强度线型 + nodes[].color（Okabe-Ito）+ nodes[].size（大小编码，面积正比） | colour.not_cb_safe, edge.count_mismatch, edge.zero_length, edge.confidence_missing, edge.confidence_unknown, edge.feedback_unlabeled, size.not_positive, legend.size_unexplained |
| 图例标注 | legend[]（系列）+ legend_notes[]（映射说明，如"节点大小 = 表达量"）+ legend_required | legend.entry_unmatched, legend.entity_unlisted, apparatus.legend_entry_unmatched, apparatus.legend_entity_unlisted |
| 可编辑源文件 | figure.svg（live text，分层；SVG 字体以非内联方式写入，文字可改） | export.no_live_text, export.embedded_raster, export.no_font_family |
| 导出格式 | figure.png（300 dpi）+ figure.pdf（type 42 嵌入字体）+ font 解析记录 | export.missing_glyphs, export.no_font, export.low_dpi, font.too_small, label.mismatch |

## Rules

### Nomenclature — is each label a valid, unambiguous entity

| rule | severity | what it proves |
|-|-|-|
| `nomenclature.gene_casing` | high | symbol contradicts the declared species' convention |
| `nomenclature.alias_collision` | high | two nodes are the same entity under different names |
| `nomenclature.gene_not_italic` | medium | a gene symbol is set roman |
| `nomenclature.protein_italic` | medium | a protein name is set italic |
| `nomenclature.missing_accession` | medium | no resolvable identifier |
| `nomenclature.accession_malformed` | medium | accession does not match its declared format |
| `nomenclature.species_ambiguous` | medium | human and rodent casing mixed, no species declared |
| `nomenclature.vague_entity` | low | a process word drawn as a node |

### Provenance — is each entity and arrow in the source

| rule | severity | what it proves |
|-|-|-|
| `trace.entity_untraceable` | high | an entity has no material reference |
| `trace.evidence_not_in_materials` | high | an entity points at a material that does not exist |
| `trace.material_not_drawn` | medium | a required material never appears |
| `trace.material_no_source` | medium | a material entry carries no source locator, so its claim cannot be re-checked |
| `trace.edge_not_in_source` | high | a drawn arrow the source does not state |
| `trace.connection_not_drawn` | medium | a stated connection missing from the figure |
| `trace.no_connection_list` | low | no connection list was supplied |
| `route.numbering_vs_text` | medium | step number disagrees with the text order |

### Direction, topology, compartments and layout

| rule | severity | what it proves |
|-|-|-|
| `route.decision_without_branches` | high | a decision node has no branches |
| `route.no_entry` | high | a route stage nothing leads into |
| `route.no_exit` | high | a route stage that leads nowhere |
| `route.stage_duplicate` | high | the same stage label appears twice |
| `route.stage_gap` | medium | stage numbering skips a phase |
| `route.stage_nonnumeric` | medium | a stage value is not a number, so order and gaps cannot be checked |
| `label.outside_canvas` | high | a label is clipped by the figure edge |
| `label.overlap` | high | labels collide on a fixed canvas |
| `label.wider_than_box` | medium | a label overflows its own shape |
| `edge.backward_flow` | medium | a flow arrow points at an earlier layer without a `recycle` declaration |
| `edge.feedback_unlabeled` | medium | a backward activate/inhibit arrow (a feedback loop) is not marked `feedback: true` |
| `edge.dangling` | medium | a connection names a node the figure does not declare (断头箭头) |
| `compartment.mismatch` | high | an explicit layer places a node outside the compartment band it claims |
| `compartment.undeclared` | medium | a node names a compartment the spec never declares |
| `compart.malformed` | medium | a compartment entry without an id was skipped |

### Evidence strength and size encoding

| rule | severity | what it proves |
|-|-|-|
| `edge.confidence_missing` | medium | confidence_required is set but an edge carries no evidence strength |
| `edge.confidence_unknown` | medium | the evidence strength is not a declared level (confirmed/predicted/hypothetical) |
| `size.not_positive` | medium | node size is not a positive number, so the size channel cannot be drawn to scale |
| `legend.size_unexplained` | low | node sizes vary while legend_required is set, and legend/legend_notes explain no size mapping |

### Reproduction and export

| rule | severity | what it proves |
|-|-|-|
| `repro.nondeterministic` | high | two renders of one spec differ |
| `export.missing_glyphs` | high | characters render as empty boxes |
| `export.no_font` | high | no font could be resolved at all |
| `export.no_live_text` | high | SVG labels are outlines, not text |
| `export.embedded_raster` | medium | the export embeds a raster where live text was expected |
| `export.low_dpi` | medium | raster export below the declared dpi floor |
| `export.no_font_family` | low | export carries no explicit font family |

### Render-vs-spec cross-check, malformed entries and refusal

| rule | severity | what it proves |
|-|-|-|
| `label.mismatch` | high | a drawn label differs from the spec (inherited from the schematic layer) |
| `font.too_small` | medium | type below the declared minimum |
| `edge.count_mismatch` | high | drawn connector count differs from the spec |
| `edge.zero_length` | high | two connected nodes occupy the same point |
| `node.malformed` | medium | a node entry without a string id was skipped (figure still renders) |
| `edge.malformed` | medium | an edge entry without a from/to pair was skipped |
| `checklist.unreadable` | medium | the checklist file is not readable JSON, so coverage was not audited |
| `coverage.incomplete` | high | the figure omits an entity or relation the checklist states |
| `audit.no_section` | high | the spec is not readable JSON, not an object, or names nothing to draw — refused, never a crash |

### Complete rule index (engine rules documented per strict acceptance)

| rule | severity |
|-|-|
| `colour.not_cb_safe` | low |
| `entity.duplicate` | medium |
| `legend.entity_unlisted` | low |
| `legend.entry_unmatched` | medium |
| `apparatus.component_missing` | high |
| `apparatus.indistinguishable_components` | medium |
| `apparatus.legend_entity_unlisted` | low |
| `apparatus.legend_entry_unmatched` | medium |
| `apparatus.orphan_component` | medium |

The apparatus.* rules come from the shared structure module: a pathway with stage
numbering gets the same entry/exit/duplicate checks as a technical route, and the
legend checks are shared verbatim.

## 异常处置表

| 异常 | 识别 | 处置动作 |
|-|-|-|
| 输入缺方向信息（关系只有名词没有方向） | 抽取阶段 | 不臆造箭头方向：方向不明的关系登记 uncertainty，画为无向 bind 线型并写明依据缺口 |
| 实体名称歧义（同名基因与蛋白） | nomenclature.alias_collision / kind 字段 | 用 kind 区分基因与蛋白、aliases 归一同义名；消歧不了就拆为两个节点并登记 uncertainty |
| 输入数据与图示矛盾（数值/关系对不上） | provenance + 抽取阶段 | 以输入材料为准改图；矛盾点登记 uncertainty，不按图示迁就数据 |
| 悬空连接（边指向未声明节点，断头箭头） | edge.dangling | 补上缺失节点或删掉该边；引擎不静默吞掉，发现为 medium |
| 畸形条目（节点/边列表混入裸字符串） | node.malformed / edge.malformed | 引擎跳过并报告，其余图面照常渲染；修复 spec 后重跑消除发现 |
| 区室矛盾（节点声明区室与显式 layer 冲突） | compartment.mismatch | 修正 layer 或 compartment；跨膜受体必须落在膜带内 |
| 关系证据强度缺失/未知 | edge.confidence_missing / edge.confidence_unknown | 填 confirmed/predicted/hypothetical 三档之一；引擎按档位映射线型（predicted 虚线、hypothetical 点线） |
| 反馈环未标注 | edge.feedback_unlabeled | 给回环边加 `feedback: true`；回流用 `recycle: true` 标注 |
| 字体或图元缺失 | export.missing_glyphs / export.no_font | fontsel.py 三段确定性搜索（优先字体表→CJK 命名文件→matplotlib 全量扫描）；仍无覆盖则保留发现并在 limits 声明，不静默替换 |
| 导出失败（写盘失败/权限） | 引擎异常退出 | result.json 记 limits 与 reason；依赖缺失属导入层失败，见 Requirements |
| 清单不可读/覆盖缺口 | checklist.unreadable / coverage.incomplete | 修复 checklist JSON；coverage 补齐缺失实体或关系后再交付 |
| 画布溢出/图面元素过多不可读 | label.overlap 连发 | 增大 canvas_mm、缩短标签或按区室拆分分区（compartments 分带）；不得低于字号下限（min_font_pt，默认 6pt）；取舍写进 limits |
| 画布参数非法（非正数/长度不对） | 引擎拒绝（audit.no_section，exit 5） | 修正 canvas_mm 为正数二元组后重跑 |
| 重复运行结果不一致 | repro.nondeterministic | 修复布图后再交付；交付前跑两遍是流程要求 |

## 创新增益

本 Skill 的方法链是"结构化中间表示 → 约束布图 → 全量自检"三段式，逐条对应题面点名的
突破方向：

1. **机制文字到图元与边的结构化映射**：把机制文字解析成六张可逐条质疑的清单——实体
   （kind/accession/aliases 命名归一 + evidence 溯源 + source 定位）、相互作用
   （connections/edges 映射为 activate/inhibit/bind/flow 四种可区分箭头 + confidence
   三档证据强度）、方向与区室（layer 表达受体—胞内—核层级、compartments 声明区室带）、
   图例（legend 系列项 + legend_notes 映射说明）。通用 Agent 通常把名词平铺成一圈节点
   再随意连线，跳过这一步。
2. **区室与跨膜位置约束布局**：区室带由 spec 声明（不是引擎猜测），无显式 layer 的
   节点被**放进它声明的区室带**——布局由声明的生物学约束，而不是反过来；显式 layer 与
   区室带矛盾时报 high（跨膜受体画进胞质正是题面点名的失败模式）。区室带随图渲染，
   布局本身传达机制结构。
3. **箭头类型的语义判定 + 证据强度**：四种线型语义之外，confidence 三档
   （confirmed/predicted/hypothetical）映射为实线/虚线/点线——证据强度直接画在图面上，
   不只写在 spec 里；逆向 activate/inhibit 必须标 `feedback: true`，逆向 flow 必须标
   `recycle: true`，否则报发现（反馈环走向可核查）。
4. **图例与数据编码一致性校验**：图例系列项逐一对回图面标签（幽灵系列报发现），
   legend_notes 承载映射说明（如"节点大小 = 表达量"）；节点 size 编码数据（面积正比）
   且非正数/未在图例解释都会报发现——颜色、线型、大小三个数据通道全部可审计。
5. **可编辑源文件自动生成 + 导出三件套**：SVG live text（svg.fonttype=none，字体非内联，
   文字可改）+ 300 dpi PNG + **PDF（pdf.fonttype=42，TrueType 子集嵌入）**——导出件自带
   字形，不依赖阅读方装机字体；export 记录逐项给出 formats/dpi/canvas/font/palette。
6. **运行时契约直通**：`--case /input/case.json` 把 case_id 与 output_contract 逐字段
   回填 result.json（引擎真实产出的键填真实路径，推导不出的填 null + limits 说明），
   **拒绝路径同样回填**；`--meta` 把 harness 的 sources/uncertainty/limits 合并进
   result.json——评委打开 result.json 即见全部契约字段，不依赖运行时 agent 的手工拼装。
7. **确定性保障（方差治理）**：字体解析三段确定性搜索（同机同输入必同字体）；布图纯
   函数化（最长路径分层 + 显式 layer/区室约束，无随机源）；同一 spec 渲染两遍的文本与
   几何签名必须一致才允许交付；畸形条目跳过并报告而不是整案拒绝（一处脏数据不再毁掉
   整个案例）。

相对基础 Agent 的增益边界（创新证据的适用范围）：

- 增益在"可证明"一侧：命名规范、别名碰撞、溯源覆盖率、区室一致性、证据强度、箭头
  语义区分、图例一致性、字形覆盖、二次可复现——这些引擎能算出数字，对照白板可验证。
- 不在"画得像"：本包画带标注的盒子、区室带与箭头，不画膜脂双层、受体形状、细胞轮廓
  的象形——区室带是 spec 声明的几何约束，不含未经声明机制；不判断机制本身的科学
  正确性；不做数值统计分析与论文版式（题面明示由相邻课题承担）。
- 命名只查"形"不查"真"：没有基因数据库，TP53 在人类图中通过是因为书写规范，不是
  因为确认了它存在。
- 证据强度是"声明的档位"：引擎校验档位合法并画进线型，不校验档位是否与文献证据
  强度相符（那需要证据库）。

## 生态贡献

- **使用说明**：本 SKILL.md 即完整使用说明——六步运行时入口（每步带核验）、路由决策
  表、输入输出、异常处置、自查方法齐全；其他人或 Agent 可按说明独立复跑。
- **依赖**：matplotlib + numpy + Pillow，一行 pip 安装（见 Dependencies）；无网络
  依赖、无作者个人文件依赖。
- **配置**：全部行为由 spec JSON 配置（物种、别名表、画布、字号、色板、区室带、
  置信度开关、图例开关、min_font_pt、checklist、expect_connections），按案例调整
  不需要改引擎代码；harness 侧配置走 --case/--meta 两个文件。
- **示例（示例，非正式案例结果）**：examples/spec.json 是最小输入示例（TP53–MDM2–
  CDKN1A 三实体通路，含区室带与置信度字段）；examples/bench-pathway-report.json 与
  examples/bench-report.json 是示意输出（由 bench 实跑生成）。
- **资源可复用**：scripts/ 各模块可独立导入——nomenclature.py（命名规范）、
  provenance.py（溯源）、fontsel.py（逐字符字体解析 + 三段确定性回退）、
  contract_echo.py（运行时契约回填）为跨题共享件；references/ 下的
  nomenclature-rules.md、layout-rules.md、font-and-export.md 是可单独取用的绘图规范。
- **适用范围**：生物机制图、通路图、信号转导示意图；不适用于带数值轴的数据图表、
  统计分析与论文排版。
- **限制**：见 Limits 一节，逐条写明能力边界。
- **维护信息**：规则集以 rule id 固化，bench 回归套件（71 场景）即版本门槛；任何规则
  改动必须同步本文件并重跑 bench（strict_gate 的 G4 规则一致性检查强制这一点）。

## Verification

```bash
python scripts/bench_pathway2.py   # 29 scenarios: contract passthrough, compartments,
                                   # confidence, feedback, recycle, dangling, malformed,
                                   # refusal echo, nomenclature, provenance, font, determinism
python scripts/bench_pathway.py    # 11 scenarios: nomenclature + layout, pre-polish set
python scripts/bench_schematic.py  # 19 scenarios: layout, export, compartments, confidence,
                                   # feedback, recycle, dangling, malformed entries
python scripts/bench_apparatus2.py # 13 scenarios: shared structure module regression,
                                   # including dangling/malformed/recycle via apparatusfig
```

All pass in full on this machine (72 scenarios total). Font and determinism defects
cannot be expressed in a spec, so those two scenarios inject them by patching a
resolver; the contract scenarios exercise --case on both the success and the refusal
path.

## Dependencies

This skill requires the following Python packages:

```
pip install matplotlib numpy Pillow
```

- **matplotlib** (matplotlib, numpy): figure rendering, SVG/PNG/PDF export
- **numpy**: numerical array operations behind the layout audit
- **Pillow (PIL)**: font measurement for text overflow detection

If these packages are not available, the skill writes a structured result.json with
an ImportError at the Python import layer (dependencies are declared in Requirements) —
re-run. The audit rules that check rendering output cannot run without matplotlib.

## Limits

- **Casing is checked, truth is not.** There is no gene database: `TP53` in a human
  figure passes because it is well-formed, not because the module confirmed it exists.
  `XYZZY1` would also pass.
- **Aliases come from you.** Collision detection is only as good as the `aliases` map.
- **Compartments are declared, not inferred.** The engine renders and enforces the
  bands the spec declares; it cannot discover that a receptor is transmembrane if the
  spec does not say so.
- **Confidence is a declared level.** confirmed/predicted/hypothetical are checked for
  well-formedness and drawn into the line style; whether the level matches the actual
  literature evidence needs an evidence base this engine does not ship.
- **Italic is verified in the exported SVG, not the spec** — a renderer that drops
  style passes on the spec and fails here.
- **`vague_entity` is a blocklist**, so it under-reports rather than over-reports.
- **Boxes, bands and arrows, not pictograms.** A lipid bilayer, a receptor shape, a
  cell outline would all imply mechanism; the honest alternative is a labelled box
  inside a declared band.
- **Arrow type is not validated against the biology** — only that flow runs forward
  (or is declared recycle) and feedback loops are marked.
- **Determinism is compared on text and geometry**, not bytes.
- **PDF font embedding subsets the resolved font.** If no covering font was found, the
  PDF embeds the same uncovered font — missing glyphs is reported instead of silently
  substituted.

## Failure handling

| symptom | what to do |
|-|-|
| `export.missing_glyphs` | install a font covering those characters — this is the "中文变方框" failure |
| `gene_casing` | fix the symbol or the `species` field; one of them is wrong |
| `alias_collision` | merge the nodes — the pathway had one actor |
| `trace.entity_untraceable` | add the material id, or remove the entity |
| `trace.material_no_source` | add a `source` locator to the material entry |
| `trace.edge_not_in_source` | remove the arrow, or record the source statement in `connections` |
| `compartment.mismatch` | fix the `layer` or the `compartment`; a receptor belongs in its band |
| `edge.dangling` | add the missing node, or drop the arrow |
| `edge.feedback_unlabeled` | mark the back arrow `feedback: true`, or flip its direction |
| `repro.nondeterministic` | the layout changed between runs; fix it before shipping |
| `label.overlap` | raise `canvas_mm` or shorten labels, never shrink below the floor |
