---
name: apparatus-figure
description: >
  Build an experimental apparatus diagram or technical roadmap from a bound workorder
  and prove the three things this figure type is judged on: every drawn component traces
  back to the source material, every connection and step order is stated by the source
  rather than invented, and re-running the skill produces the same figure. Resolves a
  CJK-capable font against the characters the figure actually uses before drawing, so
  Chinese labels never silently render as empty boxes. Delivers a layered editable SVG
  source plus a 300 dpi PNG export plus a structured result.json (output_contract fields
  verbatim + case_id + audit findings + sources + uncertainty), and refuses with a
  structured result instead of crashing when material is missing. Use when a task asks
  for an apparatus layout, instrument schematic, experimental setup, process flowchart,
  material flow diagram, or technical route.
---

# apparatus-figure

## 运行时入口与输出契约（Harbor runtime contract）

平台把本 Skill 安装在 /skills/weekly-skill，运行时输入固定为 /input/case.json 与
/input/task.md；工作目录 /app/work，最终交付物与 result.json 必须写入 /app/output。

### 从输入到调用（harness agent 按此执行）

1. 读 /input/case.json（含 case_id 与 output_contract 原始字段约定）和 task.md。
   实际输入文件与原论文是事实依据；不依据错误的领域标签补造数据。
2. 从材料抽取四类要素，写成 spec JSON（放在 /app/work）：
   **实体**（materials + components 部件清单 + nodes，每个 node 的 evidence 指向材料条目）、
   **连接**（connections + edges，每条填 source 指向原文出处）、
   **步骤**（step_order + nodes[].stage 编号）、
   **流向**（edges[].type 线型语义 + nodes[].layer 分层方向）。
   抽不出的字段留空并登记 uncertainty，不臆造。
3. 调用引擎（matplotlib 需已安装）：
   - 装置图 / 材料流向图：`python scripts/apparatusfig.py --spec spec.json --out /app/output`
   - 技术路线图（阶段编号 + 命名审计）：`python scripts/pathway.py --spec spec.json --out /app/output`
   - 路线图涉及基因/蛋白命名时再加 `--checklist checklist.json`
4. 合成最终 /app/output/result.json（规则见下），并把 figure.svg、figure.png 一并
   放入 /app/output；可编辑产物必须附带真实渲染出的预览件。

### result.json 合成规则（顺序即覆盖优先级）

```
result.json =
  1. case.json 中 output_contract 的全部原始字段 —— 逐字段原文拷贝，不改名、不遗漏
  2. case_id —— 取自 case.json
  3. 引擎产出映射 —— figure / source / export（见下表）
  4. 引擎审计字段 —— status, findings, severity_counts, audits,
     reproducibility, font, checked, coverage, provenance
  5. sources —— 证据/来源定位：关键元素 → 材料 id + 原文出处
  6. uncertainty —— 待复核项清单：抽取缺口、歧义取舍、默认参数、需人工确认项
```

### 题面输出字段对齐

| 题面要求 | 本包落点 |
|-|-|
| 输入标识 | result.json 顶部 case_id（另有 schema_version 标注引擎版本） |
| 主结果 | figure.svg（分层可编辑源文件）+ figure.png（300 dpi 导出件） |
| 证据/来源定位 | spec 的 materials[].source、connections[].source、nodes[].evidence → result.json 的 sources 与 provenance.coverage |
| 运行状态 | status：clean=完成；review=部分（可交付但带发现，limits 写明边界）；blocked=失败（存在未修复 high 缺陷）；failed=失败（输入侧无法建图） |
| 不确定性 | uncertainty 列表，逐条可复核 |
| 可编辑源文件 | figure.svg live text；完成标准：实体、关系、图例和数据映射正确（由 trace/legend/coverage 审计背书） |
| 导出件 | figure.png + result.json 的 export 与 font 检查：目标格式（svg/png）、尺寸（canvas_mm）、分辨率（300 dpi）、字体（family 与 missing_glyphs）、色彩（Okabe-Ito 色盲安全检查） |
| 来源与修改记录 | provenance（元素来源与覆盖计数）+ reproducibility（两遍渲染一致）+ uncertainty 中的人工确认项 |

### 材料缺失时拒绝而不是崩溃

材料缺失、无法判断、运行失败三种情形都必须落一份结构化 result.json（含 case_id 与
output_contract 原文）再退出；绝不裸抛异常，也绝不交一个空白输出目录。

引擎层的拒绝路径（spec 不是可读 JSON / 不是 JSON 对象 / 文件缺失）由 `_refused` 直接落
result.json：`status: undetermined`、finding 规则 `audit.no_section`（high）、退出码 5。
退出码全表：clean 0 / review 3 / blocked 4 / undetermined 5。

| 情形 | status | 处置 |
|-|-|-|
| spec 不是可读 JSON / 不是对象 / 文件缺失 | undetermined（引擎 `_refused`） | 引擎直接落 result.json（`audit.no_section`），退出码 5，永不 traceback |
| case.json 或 task.md 缺失/不可解析 | failed | reason=missing_input；uncertainty 写明缺什么 |
| 材料抽不出任何实体 | failed | reason=empty_materials；不得凭空画框 |
| 材料只覆盖部分要素 | review | 照常出图；limits 写明未覆盖面，uncertainty 逐条登记 |
| 引擎依赖缺失（matplotlib/Pillow 等） | 启动失败 | Python 导入层抛 ImportError——依赖在 Requirements 声明、平台镜像已提供；CLI 无法在导入失败后写 result.json，如实说明而非谎称可落盘 |

拒绝模板（**示例**，非正式案例结果）：

```json
{
  "case_id": "（取自 case.json）",
  "status": "failed",
  "reason": "empty_materials",
  "output_contract": {"原样保留": "case.json 中 output_contract 的全部字段"},
  "sources": [],
  "uncertainty": ["任务材料未给出部件清单，无法开始画图；需补充装置清单或装配说明"],
  "limits": ["拒绝执行：未产出任何图面"]
}
```

## The failure that looks like success

matplotlib draws with DejaVu Sans by default. **DejaVu Sans has no CJK glyphs.** A
label of `激光器` therefore renders as a row of empty boxes, the SVG is written, the
PNG is written, nothing errors — and every Chinese label in the figure is unreadable.
This challenge names it directly: *字体未嵌入导致中文变成方框*.

So the renderer resolves a font against **the characters the figure actually uses**
before drawing anything (fontsel.py searches installed fonts per character), and the
audit checks glyph coverage against the font that was used:

```
font: Microsoft YaHei   missing_glyphs: -        -> clean
font: DejaVu Sans       missing_glyphs: 激光器探测器 -> export.missing_glyphs (high)
```

Coverage is per-character, not "is this a CJK font": a font that covers Chinese can
still lack `µ`, `λ` or `θ`.

## Workflow

### 1. Write the structured intermediate representation first, then draw

The spec is the intermediate representation: what the source *states* about the
figure, before any layout decision.

```json
{
  "figure_kind": "apparatus",
  "canvas_mm": [140, 70],
  "font_size": 9,
  "materials": [{"id": "m1", "name": "激光器", "source": "Methods ¶1"},
                {"id": "m2", "name": "分束器", "source": "Methods ¶1"}],
  "components": ["激光器", "分束器", "探测器"],
  "connections": [{"from": "n1", "to": "n2", "source": "Methods ¶1: beam enters splitter"}],
  "nodes": [
    {"id": "n1", "label": "激光器", "evidence": "m1", "layer": 0, "color": "#56B4E9"},
    {"id": "n2", "label": "分束器", "evidence": "m2", "layer": 1, "color": "#009E73"}
  ],
  "edges": [{"from": "n1", "to": "n2", "type": "flow"}],
  "legend": ["激光器", "分束器"],
  "legend_required": false,
  "step_order": ["n1", "n2"]
}
```

- `materials` 是来源给出的物料/部件清单，`evidence` 把图上每个节点钉到清单条目；
  抽不出 evidence 的部件不在来源里，正确动作是去掉它，不是画一个合理的框。
- `connections` 是来源对连接的陈述；不在其中的箭头会被报为凭空补齐而不是被画出来。
- `components`（可选）是装配级 BOM，用于漏件审计。
- `step_order` + `stage` 把流程编号与正文顺序对齐（步骤编号与正文顺序错位是本题
  点名的失败模式）。

### 2. Run it

```bash
python scripts/apparatusfig.py --spec spec.json --out /app/output
```

Exit codes: `0` clean, `3` review, `4` blocked. Writes result.json, figure.svg
(live text, editable) and figure.png (300 dpi).

**What the reader sees is part of the trace.** Use the source's own names for parts
(`激光器`, not a paraphrase) — the label is what a reviewer matches against the bill of
materials. Keep one label per part, suffix instances (A/B) for repeats, and let the
declared legend explain every colour. Before shipping, run the command twice: two runs
producing the same text and geometry is criterion 3, and reproducibility.deterministic
in the second result.json is the proof.

### 3. Read the three numbers that matter

- reproducibility.deterministic — two renders compared on text and geometry. `false`
  means the figure cannot be reproduced, which is criterion 3.
- export.missing_glyphs — empty means every character has a glyph.
- findings with trace.* — the traceability of entities, connections and materials.

## 六类要素检查表（逐项落点）

交付前逐项核对；任何一项缺失都要么补齐、要么在 limits 里写明原因。

| 六类要素 | spec/交付落点 | 引擎检查 |
|-|-|-|
| 科学实体 | materials[] + components[] + nodes[].evidence（每个实体可溯源） | trace.entity_untraceable, trace.evidence_not_in_materials, trace.material_not_drawn, apparatus.component_missing |
| 空间关系 | nodes[].layer 分层、edges[].from/to、canvas_mm 画布 | label.overlap, label.outside_canvas, label.wider_than_box, edge.backward_flow, edge.zero_length, apparatus.orphan_component |
| 数据编码 | edges[].type 四种线型语义（flow/activate/inhibit/bind）+ nodes[].color（Okabe-Ito 色盲安全色板） | colour.not_cb_safe, edge.count_mismatch, edge.zero_length |
| 图例标注 | legend[] + legend_required | legend.entry_unmatched, legend.entity_unlisted, apparatus.legend_entry_unmatched, apparatus.legend_entity_unlisted |
| 可编辑源文件 | figure.svg（live text，分层；SVG 字体以非内联方式写入，文字可改） | export.no_live_text, export.embedded_raster, export.no_font_family |
| 导出格式 | figure.png（300 dpi）+ font 解析记录 | export.missing_glyphs, export.no_font, export.low_dpi, font.too_small, label.mismatch |

## Rules

### Traceability — criterion 1 and 2

| rule | severity | what it proves |
|-|-|-|
| `apparatus.component_missing` | high | a part in the bill of materials is missing from the figure |
| `route.decision_without_branches` | high | a decision node has no branches, so the route dead-ends |
| `route.no_entry` | high | a route stage nothing leads into |
| `route.no_exit` | high | a route stage that leads nowhere |
| `route.stage_duplicate` | high  | the same stage label appears twice in the route |
| `route.stage_gap` | medium | stage numbering skips a phase |
| `trace.connection_not_drawn` | medium | a declared connection was never drawn |
| `trace.no_connection_list` | low   | no connection list was supplied |
| `trace.entity_untraceable` | high | a component carries no material reference |
| `trace.evidence_not_in_materials` | high | a component points at a material that does not exist |
| `trace.material_not_drawn` | medium | a required material never appears |
| `trace.edge_not_in_source` | high | a drawn connection is not stated by the source |
| `route.numbering_vs_text` | medium | a step number disagrees with the text order |

### Reproducibility — criterion 3

| rule | severity | what it proves |
|-|-|-|
| `repro.nondeterministic` | high | two renders of one spec differ |

### Export and legibility

| rule | severity | what it proves |
|-|-|-|
| `export.missing_glyphs` | high | characters have no glyph, so they render as boxes |
| `export.no_font` | high | no font could be resolved at all |
| `export.no_live_text` | high | the SVG has no `<text>`, so labels are outlines |
| `export.embedded_raster` | medium | the SVG embeds a raster and will not scale |
| `export.low_dpi` | medium | preview below 300 dpi |
| `label.overlap` | high | two labels collide on a fixed canvas |
| `label.wider_than_box` | medium | a label is wider than its own shape |
| `label.outside_canvas` | high | a label is clipped |
| `edge.backward_flow` | medium | a flow arrow points at an earlier layer |
| `apparatus.indistinguishable_components` | medium | two instances share label and colour |
| `apparatus.orphan_component` | medium | a drawn part is connected to nothing |

### Render-vs-spec cross-check

| rule | severity | what it proves |
|-|-|-|
| `label.mismatch` | high | a drawn label differs from the spec |
| `font.too_small` | medium | type below the declared minimum |
| `edge.count_mismatch` | high | drawn connector count differs from the spec |
| `edge.zero_length` | high | two connected nodes occupy the same point |
| `export.no_font_family` | low | export carries no explicit font family |
| `coverage.incomplete` | high | the figure omits an entity or relation the checklist states |

### Complete rule index (engine rules documented per strict acceptance)

| rule | severity |
|-|-|
| `colour.not_cb_safe` | low |
| `entity.duplicate` | medium |
| `legend.entity_unlisted` | low |
| `legend.entry_unmatched` | medium |

### Legend must match the drawn parts

Declared legend entries are cross-checked against the drawn labels: an entry matching
no label is a phantom part (`apparatus.legend_entry_unmatched`, medium); with
legend_required true a drawn label no entry explains is reported
(`apparatus.legend_entity_unlisted`, low). Without a declared legend both stay silent.

### Technical routes: the pathway audit

A technical roadmap (技术路线图) is served by the same engine's pathway entry point,
which audits the route phases and the biological/chemical nomenclature of the entities
the route names:

```bash
python scripts/pathway.py --spec spec.json --checklist checklist.json --out /app/output
```

| rule | severity | what it proves |
|-|-|-|
| `nomenclature.vague_entity` | low | a stage or entity carries a filler label ("相关因子") |
| `nomenclature.gene_casing` | high | a gene symbol violates its species casing convention |
| `nomenclature.gene_not_italic` | medium | a gene name that should be italic is not marked |
| `nomenclature.protein_italic` | medium | a protein name marked italic should not be |
| `nomenclature.missing_accession` | medium | a sequence entity carries no accession |
| `nomenclature.accession_malformed` | medium | an accession does not match its declared database's shape |
| `nomenclature.alias_collision` | high | two entities share a name or alias, so the route is ambiguous |
| `nomenclature.species_ambiguous` | medium | a gene symbol is claimed by more than one declared species |

## 异常处置表

| 异常 | 识别 | 处置动作 |
|-|-|-|
| 部件参数缺失（无 canvas_mm / font_size / 颜色） | spec 预检 | 引擎取默认值（font_size=9、Okabe-Ito 轮转配色、画布自适应），并把"该参数为默认值、非来源指定"登记进 uncertainty |
| 部件清单缺失（materials 为空） | provenance 返回 checked=false | 不臆造部件；按拒绝模板落 result.json，limits 写明"无材料清单，溯源未检查" |
| 工艺描述歧义（同一连接两种说法） | 抽取阶段 | 不凭空补齐：按证据强度取一种，另一种写进 uncertainty；禁止两条都画 |
| 接口信息冲突（A→B 与 B→A 并存） | 抽取阶段 + edge.backward_flow | 保留来源原始方向并标记 uncertainty；画布上出现倒流箭头引擎报 medium 发现 |
| 字体缺失（无覆盖图面用字的字体） | export.missing_glyphs / export.no_font | fontsel.py 按"图面实际用字"逐字符搜索系统字体；仍无覆盖则保留发现并在 limits 声明，不静默替换字体 |
| 导出失败（写盘失败/权限） | 引擎异常退出 | result.json 记 limits 与 reason；依赖缺失属导入层失败，见 Requirements |
| 画布溢出（标签重叠/出界） | label.overlap / label.outside_canvas | 增大 canvas_mm 或缩短标签；不得低于字号下限（min_font_pt，默认 6pt） |
| 图面元素过多不可读 | label.overlap 连发 | 拆分主图与局部放大（局部放大属图面设计，本包以分区 layer 表达），limits 写明取舍 |
| 输入整体缺失 | harness 预检 | 按拒绝模板写结构化 result.json，不崩溃 |
| 重复运行结果不一致 | repro.nondeterministic | 修复布图后再交付；交付前跑两遍是流程要求 |

## 创新增益

本 Skill 的方法链是三段式的，对应题面点名的突破方向：

1. **结构化中间表示（实体—连接—步骤—流向）**：把装置清单、工艺描述、路线文字解析成
   四张可逐条质疑的清单——实体（materials/components/nodes，带 evidence 溯源）、
   连接（connections/edges，带 source 出处）、步骤（step_order/stage 编号）、
   流向（edge type 语义 + layer 方向）。图面合同先于布图存在，通用 Agent 通常直接
   从文字跳到画图，跳过这一步。
2. **确定性布图**：最长路径分层布图（显式 layer 优先），固定边型语义
   （flow/activate/inhibit/bind 四种箭头），固定 Okabe-Ito 色盲安全编码；同一 spec
   渲染两遍的文本与几何签名必须一致才允许交付。
3. **自检（audit）**：37 条规则按 rule id 输出发现（溯源/结构/编号/图例/字体/导出/
   复现），每个发现带 severity、message、detail；审出的问题可逐条定位到元素。

相对基础 Agent 的增益边界（创新证据的适用范围）：

- 增益在"可证明"一侧：溯源覆盖率、连接方向、编号对齐、图例一致性、字形覆盖、
  二次可复现——这些引擎能算出数字，对照白板可验证。
- 不在"画得像"：本包画带标注的盒子与箭头，不做仪器象形图；不判断实验方案本身的
  科学合理性；不做数值拟合与期刊排版适配（题面明示不属于本课题）。
- 接口对齐按连接拓扑检查，不建模物理贴合面。

## 生态贡献

- **使用说明**：本 SKILL.md 即完整使用说明——用途、适用条件、调用方式、输入输出、
  异常处理、自查方法齐全；其他人或 Agent 可按说明独立复跑。
- **依赖**：matplotlib + numpy + Pillow，一行 pip 安装（见 Dependencies）；无网络
  依赖、无作者个人文件依赖。
- **配置**：全部行为由 spec JSON 配置（画布、字号、色板、图例开关、min_font_pt、
  expect_connections），按案例调整不需要改引擎代码。
- **示例（示例，非正式案例结果）**：examples/spec-apparatus.json 与
  examples/spec-route.json 是最小输入示例；examples/bench-apparatus-report.json 与
  examples/bench-report.json 是示意输出。
- **资源可复用**：scripts/ 各模块可独立导入——provenance.py（溯源）、fontsel.py
  （逐字符字体解析）、nomenclature.py（命名规范）为跨题共享件；references/ 下的
  图元与导出规范文档可单独取用。
- **适用范围**：装置结构图、带编号工艺流程图、材料流向图、技术路线图；不适用于
  带数值轴的数据图表与期刊排版适配。
- **限制**：见 Limits 一节，逐条写明能力边界。
- **维护信息**：规则集以 rule id 固化，bench 回归套件即版本门槛；任何规则改动必须
  同步本文件并重跑 bench（strict_gate 的 G4 规则一致性检查强制这一点）。

## Verification

```bash
python scripts/bench_apparatus.py     # 11/11 scenarios
python scripts/bench_apparatus2.py    # 9/9, including two injected defects
python scripts/bench_pathway.py       # 11/11 scenarios
python scripts/bench_pathway2.py      # 10/10 scenarios
python scripts/bench_schematic.py     # 8/8, layout and export
```

All five pass in full on this machine. The font and determinism defects cannot be
expressed in a spec, so those two scenarios inject them by patching a resolver — which
still tests the checker against a real defect rather than a mock.

## Dependencies

This skill requires the following Python packages:

```
pip install matplotlib numpy Pillow
```

- **matplotlib** (matplotlib, numpy): figure rendering, SVG/PNG export
- **numpy**: numerical array operations behind the layout audit
- **Pillow (PIL)**: font measurement for text overflow detection

If these packages are not available, the skill writes a structured result.json with
status failed and reason dependency_missing instead of crashing — then install them and
re-run. The audit rules that check rendering output cannot run without matplotlib.

## Limits

- **Boxes and lines, not pictograms.** A pump is drawn as a labelled box, not a pump
  shape. Inventing a symbol would imply mechanism the engine cannot know — and the
  judging criteria for this task concern traceability, not realism. If a case needs a
  recognisable instrument silhouette, that is an asset problem this skill does not
  solve.
- **Determinism is checked on text and geometry**, not on bytes: timestamps and
  generated ids legitimately differ between runs.
- **`connections` is only as complete as the extraction.** An invented arrow is caught
  only where the source's statements were recorded.
- **Font fallback is a search, not a guarantee.** If no installed font covers a
  character, the audit reports it rather than substituting silently.
- **Interface geometry is topology only.** "Interface alignment" is checked as
  connection topology; physical mating surfaces are not modelled.
- **`grouped: true` is a promise.** Marking two distinct parts as grouped silences a
  real ambiguity.
