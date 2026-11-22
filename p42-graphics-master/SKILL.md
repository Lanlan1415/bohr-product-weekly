---
name: graphics-master
description: >
  科研绘图领域总课题（challenge-38e0cc33）：依据固定科研材料生成或编辑可复用的科研图稿，
  一个技能覆盖四条绘图路线。数据图表从表文件画出并保留 mark→row 溯源；生物通路图核对每个
  标签是良构、无歧义的实体；装置/实验路线图核对部件清单、孤件与阶段编号；通用示意图核对
  版式与导出。四条路线共同承诺：实体关系与数据映射可回溯到材料、交付可编辑源文件
  （live-text SVG）加导出件（300 dpi PNG）、标注每个关键元素的来源与导出检查结果、重跑同图。
  字体按图面实际字符解析（中文不变成方框），畸形输入拒绝而不是近似。Use when a task asks
  for a figure whose entities, arrows or marks must be traceable to source material and
  whose source file must stay editable.
---

# graphics-master — 科研绘图领域总课题

领域承诺一句话：**生成图稿，也保留可编辑来源。** 一份图稿只有当评审能把每个关键元素走回到
它出自的材料条目、把每个 mark 走回到数据行、并且拿到一个还能再编辑的源文件时才算交付；
图面写不下的、引擎做不到的，进 limits 如实说明，而不是被一张好看的位图盖过去。

四个引擎覆盖整个领域：

| 组件 | 覆盖 | 入口 |
|-|-|-|
| chartguard 引擎（数据图表 + 编码审计） | 数据图表 | `scripts/chartguard.py` |
| schematic 引擎（版式 + 导出审计） | 通用示意图 | `scripts/schematic.py` |
| pathway 引擎（schematic + nomenclature + provenance） | 生物通路图 | `scripts/pathway.py` |
| apparatusfig 引擎（schematic + apparatus 结构审计） | 装置/实验路线 | `scripts/apparatusfig.py` |

共享件：`scripts/fontsel.py`（按图面实际字符选字体）、`scripts/provenance.py`（材料溯源 +
确定性重跑）、`scripts/nomenclature.py`（命名规约）、`scripts/apparatus.py`（结构审计）。

## 路由表

| 任务形态 | 路由 | 命令 |
|-|-|-|
| 数据图表（表格 → bar/line/scatter/box/heatmap） | chartguard | `python scripts/chartguard.py --spec spec.json --data table.csv --out /app/output` |
| 生物通路图 / 机制图 | pathway | `python scripts/pathway.py --spec spec.json --out /app/output` |
| 装置图 / 实验路线图 | apparatusfig | `python scripts/apparatusfig.py --spec spec.json --out /app/output` |
| 通用示意图（流程、关系、版式） | schematic render+audit | `python scripts/schematic.py --spec spec.json [--checklist checklist.json] --out /app/output` |

一个案例只走一条路由为主；task.md 若要求多张图，每张图跑一次并把 out 指到不同子目录。选路
口诀：**材料是数字表格** → chartguard；**材料描述分子间调控** → pathway；**材料描述仪器
连接或分步路线** → apparatusfig；其余（概念流程、分组框图）→ schematic。图面是栅格图需要
先数字化、或只需要"描述"一张已有图的，不在本技能范围。

## 各路由的输入 spec

spec 是一个 JSON 对象。所有路由的值都来自材料，不从记忆补数——编造的数值比被审计点名更糟。

**chartguard**（完整可运行示例见 `examples/spec-chart.json` 与 `examples/data-chart.csv`）：
encoding 的值是**列名**，不是数值——这个间接层让每个 mark 能走回到行。

```json
{"kind": "bar", "x_label": "Treatment", "y_label": "Response", "y_unit": "a.u.",
 "caption_n": 6, "legend": true,
 "encoding": {"x": "condition", "y": "response", "y_err": "response_sd", "group": "group"}}
```

**pathway**（见 `examples/spec-pathway.json`）：materials + 每个 node 的 evidence 让溯源
成立；connections 是材料明说的关系清单——画了清单外的箭头是 `trace.edge_not_in_source`，
材料说了没画是 `trace.connection_not_drawn`；aliases 从材料文本构建，让别名冲突可查。

```json
{"species": "human", "aliases": {"TP53": ["Tp53", "p53"]},
 "materials": [{"id": "m1", "name": "TP53"}, {"id": "m2", "name": "MDM2"}],
 "connections": [{"from": "g1", "to": "p1"}],
 "nodes": [{"id": "g1", "label": "TP53", "kind": "gene", "evidence": "m1", "layer": 0,
            "accession": "HGNC:11998", "accession_source": "hgnc", "color": "#56B4E9"},
           {"id": "p1", "label": "MDM2", "kind": "protein", "evidence": "m2", "layer": 1}],
 "edges": [{"from": "g1", "to": "p1", "type": "activate"}]}
```

**apparatusfig**（见 `examples/spec-apparatus.json`）：components（材料/清单部件名）必须
都出现在图面；figure_kind 为 route 时 stage 连续唯一、decision 节点有分支、路线有入口有
出口；step_order 让步骤编号与正文顺序可核对。

```json
{"figure_kind": "apparatus",
 "materials": [{"id": "m1", "name": "激光器"}, {"id": "m2", "name": "分束器"}],
 "connections": [{"from": "n1", "to": "n2"}],
 "nodes": [{"id": "n1", "label": "激光器", "evidence": "m1", "layer": 0},
           {"id": "n2", "label": "分束器", "evidence": "m2", "layer": 1}],
 "edges": [{"from": "n1", "to": "n2", "type": "flow"}]}
```

**schematic**（见 `examples/spec-schematic.json`）：nodes + edges + 可选 canvas_mm（期刊
栏宽是约束不是建议）、legend / legend_required（图例与图面逐项一致）、checklist.json
（从材料提取的 entities/relations 清单，触发 coverage 比对）。

```json
{"font_size": 9,
 "nodes": [{"id": "A", "label": "Substrate", "layer": 0, "color": "#56B4E9"},
           {"id": "B", "label": "Complex", "layer": 1, "color": "#009E73"}],
 "edges": [{"from": "A", "to": "B", "type": "bind"}]}
```

## 运行时入口与输出契约（Harbor runtime contract）

平台把本 Skill 安装在 /skills/weekly-skill，运行时输入固定为 /input/case.json（含
case_id 与 output_contract 原始字段约定）与 /input/task.md；工作目录 /app/work，
最终交付物与 result.json 必须写入 /app/output。

### 从输入到调用（harness agent 按此执行）

1. 读 /input/case.json 与 task.md。实际输入文件与原论文是事实依据；不依据错误的
   领域标签补造数据。
2. 按「路由表」选路：材料是数字表格 → chartguard；描述分子调控 → pathway；描述
   仪器连接或分步路线 → apparatusfig；其余 → schematic。
3. 从材料抽取「实体—连接—步骤—流向」结构化中间表示，写成 spec JSON（/app/work）：
   实体带 evidence 指向材料条目，连接填 source 指向原文；抽不出的字段留空并登记
   uncertainty，不臆造。
4. 跑对应路由的 CLI（--out 指向 /app/output 下按图编号命名的子目录）。
5. 合成最终 /app/output/result.json（见下），figure.svg / figure.png 等产物一并放入
   /app/output；可编辑产物必须附带真实渲染出的预览件。

### result.json 合成规则（顺序即覆盖优先级）

```
result.json =
  1. case.json 中 output_contract 的全部原始字段 —— 逐字段原文拷贝，不改名、不遗漏
  2. case_id —— 取自 case.json
  3. 引擎产出映射 —— figure / source / export（见下表）
  4. 引擎审计字段 —— status, findings, severity_counts 及各路由溯源字段
  5. sources —— 证据/来源定位：关键元素 → 材料 id + 原文出处（或 mark → 数据行）
  6. uncertainty —— 待复核项清单：抽取缺口、歧义取舍、默认参数、需人工确认项
```

### 题面输出字段对齐

| 题面要求 | 本包落点 |
|-|-|
| 输入标识 | result.json 顶部 case_id（另有 schema_version 标注路由引擎版本） |
| 主结果 | figure.svg（分层可编辑源文件）+ figure.png / figure.pdf（导出件） |
| 证据/来源定位 | spec 的 materials[].source、connections[].source、nodes[].evidence；chartguard 的 mark_to_row[] → result.json 的 sources |
| 运行状态 | status：clean=完成；review=部分（可交付但带发现，limits 写明边界）；blocked=失败（存在未修复 high 缺陷）；undetermined/refused=失败（输入侧无法建图） |
| 不确定性 | uncertainty 列表，逐条可复核 |
| 可编辑源文件 | figure.svg live text；完成标准：实体、关系、图例和数据映射正确（trace/legend/coverage 审计背书） |
| 导出件 | figure.png（300 dpi）+ result.json 的导出检查：目标格式、尺寸（canvas_mm）、分辨率、字体（family 与 missing_glyphs）、色彩（Okabe-Ito / 色觉安全检查） |
| 来源与修改记录 | provenance（元素来源与覆盖计数）+ materials/nodes 的 version 字段回显 + reproducibility（两遍渲染一致）+ uncertainty 人工确认项 |

### 材料缺失时拒绝而不是崩溃

拒绝是本包的一等行为：spec 不可读、不是 JSON 对象、无可画节点、数据表不可读、未知
图型，引擎一律写出带 rule id 的 result.json 并以退出码 5 正常退出，永不 traceback。
材料缺失、无法判断、运行失败三种情形都必须落一份结构化 result.json（含 case_id 与
output_contract 原文）；绝不裸抛异常，也绝不交一个空白输出目录。

| 情形 | status | 处置 |
|-|-|-|
| case.json 或 task.md 缺失/不可解析 | failed | reason=missing_input；uncertainty 写明缺什么 |
| spec 不可读/不可画 | undetermined | 引擎拒绝路径（audit.no_section，exit 5） |
| 数据表不可读/为空/未知图型 | refused | data.unreadable / data.no_rows / encoding.unknown_chart_kind（exit 5） |
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
  "uncertainty": ["任务材料既无数据表也无图面描述，无法选路；需补充材料"],
  "limits": ["拒绝执行：未产出任何图面"]
}
```

## 统一输出契约

每条路由向 --out 目录写（UTF-8）：

| 产物 | 含义 |
|-|-|
| result.json | status / findings[] / severity_counts / 审计上下文（见下） |
| figure.svg | **可编辑源文件**：live-text（`svg.fonttype=none`），标签是文本不是轮廓 |
| figure.png | 300 dpi 导出件（chartguard 另写 figure.pdf） |

result.json 公共字段：status（clean / review / blocked；chartguard 拒绝时 refused）、
findings（rule + severity + message + 溯源上下文：节点 id、材料 id、边、行号）、
severity_counts，以及按路由的溯源字段——chartguard 的 encoding + mark_to_row[]（每个 mark
的 {mark, row, x, y, series, y_err}），pathway 的 provenance.coverage + coverage.incomplete
+ font（family、missing_glyphs），apparatusfig 的 figure_kind + font（含 path），schematic
的 reproducibility + provenance + font。

交付（result.json 最终形态）：把 `/input/case.json` 的 case_id 与 output_contract 字段并入
--out 里那份 result.json，作为 /app/output/result.json。推导不出的契约字段填 null 并在
limits 写明原因——评审看到的是键加诚实说明，不是静默缺口。多图案例每张图各留一份
result.json（按图编号命名子目录），合并时保留全部 findings。

溯源与导出契约（四条路线共同）：

- **实体溯源**：每个节点带 evidence 指向 materials 条目；悬空引用（`trace.evidence_not_in_materials`）与无引用（`trace.entity_untraceable`）都是 high。
- **关系由材料声明**：connections 是白名单，箭头画多或画少都被点名。
- **重跑同图**：同一 spec 渲染两次，在文本与几何上指纹一致（reproducibility.deterministic）。
- **导出检查**：字符全覆盖（无方框）、SVG 有 live text、PNG ≥300 dpi、颜色落在色觉安全
  色板内、PDF 导出是合法 PDF（chartguard）。
- **不覆盖、不越界**：引擎只写进你给的 --out 目录（spec 与数据文件只读）；一个案例多张图
  时每张图用独立子目录，互不覆盖；最终 /app/output/result.json 由合并步写一次。

## 六类要素检查表（逐项落点）

交付前逐项核对；任何一项缺失都要么补齐、要么在 limits 里写明原因。四条路由按各自
引擎落点覆盖同一组要素：

| 六类要素 | spec/交付落点 | 引擎检查（按路由） |
|-|-|-|
| 科学实体 | pathway：materials + nodes（kind/accession/aliases）；apparatusfig：materials + components + evidence；chartguard：数据行与列 | trace.entity_untraceable, trace.evidence_not_in_materials, apparatus.component_missing, nomenclature.gene_casing |
| 空间关系 | nodes[].layer 分层与区室/上下游位置、edges[].from/to、canvas_mm | label.overlap, label.outside_canvas, edge.backward_flow, route.no_entry, route.no_exit, edge.zero_length |
| 数据编码 | chartguard：encoding 通道映射（x/y/group/y_err → 列名）；其余路由：edges[].type 四种线型 + Okabe-Ito 色板 | encoding.required_channel_unmapped, encoding.not_numeric, error.column_not_drawn, colour.not_cb_safe, axis.value_clipped |
| 图例标注 | legend[] + legend_required；chartguard 的 legend + 系列-图例一致性 | legend.entry_unmatched, legend.entity_unlisted, legend.absent, series.missing_from_chart |
| 可编辑源文件 | figure.svg live text（SVG 字体以非内联方式写入，标签是文本不是轮廓） | export.no_live_text, export.embedded_raster, export.no_font_family |
| 导出格式 | figure.png 300 dpi（chartguard 另出 figure.pdf）+ 字体解析记录 | export.missing_glyphs, export.no_font, export.low_dpi, export.pdf_invalid, font.too_small |

诚实状态规则：findings 含 high → blocked（退出码 4）；只有 medium/low → review（3）；
无发现 → clean（0）；案例无法按声明运行（spec 不可读、不是对象、无可画节点、数据表不可
读、未知图型）→ undetermined / refused（5）——不是通过也不是失败，不假装。

退出码：`0` clean，`3` review，`4` blocked，`5` 拒绝（undetermined / refused）。四条路线
全部如此。

## 最小工作示例（示意）

输入（`examples/spec-pathway.json` 的骨架）：

```json
{"species": "human", "aliases": {"TP53": ["Tp53", "p53"]},
 "materials": [{"id": "m1", "name": "TP53"}, {"id": "m2", "name": "MDM2"},
               {"id": "m3", "name": "CDKN1A"}],
 "connections": [{"from": "g1", "to": "p1"}, {"from": "p1", "to": "g2"}],
 "nodes": [{"id": "g1", "label": "TP53", "kind": "gene", "evidence": "m1", "layer": 0,
            "accession": "HGNC:11998", "accession_source": "hgnc", "color": "#56B4E9"},
           {"id": "p1", "label": "MDM2", "kind": "protein", "evidence": "m2", "layer": 1,
            "accession": "Q00987", "accession_source": "uniprot", "color": "#009E73"},
           {"id": "g2", "label": "CDKN1A", "kind": "gene", "evidence": "m3", "layer": 2,
            "accession": "HGNC:1784", "accession_source": "hgnc", "color": "#E69F00"}],
 "edges": [{"from": "g1", "to": "p1", "type": "activate"},
           {"from": "p1", "to": "g2", "type": "inhibit"}]}
```

运行：

```bash
python scripts/pathway.py --spec examples/spec-pathway.json --out /app/output
```

示意输出（真实运行 status 为 clean、findings 为空；这里展示字段形状）：

```json
{"schema_version": "pathway/v1", "status": "clean", "findings": [], "severity_counts": {},
 "reproducibility": {"deterministic": true, "note": "two renders of the same spec, compared on text and geometry only"},
 "provenance": {"checked": true, "coverage": {"materials_declared": 3, "entities": 3, "entities_traced": 3,
                "connections_declared": 2}},
 "font": {"family": "Microsoft YaHei", "missing_glyphs": ""},
 "checked": {"nodes": 3, "edges": 2, "dpi": 300}}
```

有发现时 findings 同形（每条含 rule / severity / message 加节点、边或行号上下文）。
其余三条路线的示例同构：chartguard 真实运行 marks=4、status clean；apparatusfig 与
schematic 真实运行 status clean、字体 Microsoft YaHei。

## 规则索引（四条路线完整规则，对齐严格验收）

### chartguard（数据图表）

把表文件画成图并保留 mark→row 溯源：编码声明对着表逐列核，数值通道拒收文本列，轴标签/单位、
图例与系列一致、误差列必须真画、caption 样本量与表一致、导出三件套可核。spec 关键字段：
kind、encoding（x/y/value/group/y_err → 列名）、x_label/y_label、x_unit/y_unit、caption_n、
significance。

| rule | severity | what it proves |
|-|-|-|
| `annotation.unknown_comparison` | high | 显著性标注比较的组不全在数据里 |
| `axis.value_clipped` | high | 数据值落在绘制范围外，mark 不可见 |
| `axis.x_label_missing` / `axis.y_label_missing` | high | 坐标轴没有标签 |
| `axis.x_unit_missing` / `axis.y_unit_missing` | medium | 数值轴声明了映射却没有单位 |
| `caption.n_mismatch` | high | caption 声明的样本量表不支持 |
| `data.no_rows` | high | 表没有数据行——拒绝而非崩溃 |
| `data.unreadable` | high | 数据表不可读（缺文件、坏编码）——拒绝 |
| `encoding.column_missing` | high | spec 引用了表里不存在的列 |
| `encoding.not_numeric` | high | 文本列驱动数值通道 |
| `encoding.required_channel_unmapped` | high | 图型必需的通道没有映射 |
| `encoding.unknown_chart_kind` | high | 未知图型——拒绝而非近似 |
| `error.column_not_drawn` | high | 误差通道映射了但没有误差棒被画出 |
| `export.low_dpi` | medium | 栅格预览低于 300 dpi |
| `export.no_live_text` | high | SVG 标签是轮廓，文件不可编辑 |
| `export.pdf_invalid` | high | PDF 导出不是合法 PDF |
| `legend.absent` | medium | 多系列却没有图例，颜色失去含义 |
| `series.missing_from_chart` | high | 数据里的组没有被画出来 |
| `traceability.missing` | high | mark 没有源行索引，图无法回溯 |
| `traceability.row_coverage` | medium | mark 数少于行数，有行未被表示 |

### pathway（生物通路图）

layout + nomenclature + provenance 三审计合一：每个标签是良构、无歧义的实体，每条关系由
材料声明，重跑同图。spec 关键字段：species、aliases、materials、connections、nodes（含
kind/accession/evidence）、edges。

| rule | severity | what it proves |
|-|-|-|
| `coverage.incomplete` | high | 图遗漏了 checklist 声明的实体或关系 |
| `nomenclature.accession_malformed` | medium | accession 与其声明格式不符 |
| `nomenclature.alias_collision` | high | 两个节点是同一实体的不同名字 |
| `nomenclature.gene_casing` | high | 符号大小写与声明物种的规约矛盾 |
| `nomenclature.gene_not_italic` | medium | 基因符号排成 roman |
| `nomenclature.missing_accession` | medium | 实体无可解析标识符 |
| `nomenclature.protein_italic` | medium | 蛋白名排成 italic |
| `nomenclature.species_ambiguous` | medium | 混用人/鼠大小写且未声明物种 |
| `nomenclature.vague_entity` | low | 过程词被画成节点 |
| `repro.nondeterministic` | high | 同 spec 两次渲染结果不同 |
| `trace.connection_not_drawn` | medium | 材料声明的关系没有画进图 |
| `trace.edge_not_in_source` | high | 画了材料没声明的箭头 |
| `trace.entity_untraceable` | high | 实体没有指向材料条目 |
| `trace.evidence_not_in_materials` | high | evidence 指向不存在的材料 |
| `trace.material_not_drawn` | medium | 材料清单里的条目从未出现在图面 |
| `trace.no_connection_list` | low | 声明了材料但没给关系清单，箭头无法核对 |

### schematic 与 apparatusfig（示意图 / 装置与路线图）

layout 与导出审计（schematic 层，两条路线共用）：

| rule | severity | what it proves |
|-|-|-|
| `audit.no_section` | high | spec 不可读 / 不是 JSON 对象 / 无可画节点——拒绝并写 result.json，退出码 5，永不 traceback |
| `colour.not_cb_safe` | low | 颜色落在色觉安全色板之外 |
| `edge.backward_flow` | medium | flow 箭头指向同层或更早层 |
| `edge.count_mismatch` | high | 画出的连接数与 spec 不符 |
| `edge.zero_length` | high | 两个相连节点被放在同一点 |
| `entity.duplicate` | medium | 两节点同标签同色，图面无法区分 |
| `export.embedded_raster` | medium | SVG 内嵌位图，印刷缩放会糊 |
| `export.low_dpi` | medium | 栅格导出低于声明的 300 dpi 地板 |
| `export.no_font` | high | 没有解析到任何字体文件，标签可能成空框 |
| `export.no_font_family` | low | SVG 未声明 font-family，替换字体会改变度量 |
| `export.no_live_text` | high | SVG 无 text 元素，标签是路径，不可编辑 |
| `export.missing_glyphs` | high | 标签字符在所用字体里没有字形——中文变方框 |
| `font.too_small` | medium | 字号低于可读性地板 |
| `label.mismatch` | high | 画出的标签与 spec 不一致 |
| `label.outside_canvas` | high | 标签被画布边缘裁切 |
| `label.overlap` | high | 两个标签在画布上重叠 |
| `label.wider_than_box` | medium | 标签溢出它所属的形状 |
| `legend.entity_unlisted` | low | legend_required 开启而图面标签没有图例项 |
| `legend.entry_unmatched` | medium | 图例条目匹配不到任何图面标签（幽灵系列） |

apparatus 结构审计（apparatusfig 在 schematic 层之上追加）：

| rule | severity | what it proves |
|-|-|-|
| `apparatus.component_missing` | high | 材料清单点名的部件没有出现在图面 |
| `apparatus.indistinguishable_components` | medium | 两个独立实例同标签同外观，图面无法区分 |
| `apparatus.legend_entry_unmatched` | medium | 图例条目匹配不到图面标签 |
| `apparatus.legend_entity_unlisted` | low | legend_required 开启而图面部件没有图例项 |
| `apparatus.orphan_component` | medium | 部件与任何东西都不相连，通常是遗留 |
| `route.decision_without_branches` | high | decision 节点出边少于两条，不是决策 |
| `route.no_entry` | high | 每个节点都有入边，路线是环、没有起点 |
| `route.no_exit` | high | 没有任何节点终止，路线走不完 |
| `route.numbering_vs_text` | medium | 步骤编号与正文呈现顺序错位 |
| `route.stage_duplicate` | high | 两个阶段共用一个编号 |
| `route.stage_gap` | medium | 阶段编号不连续，读作缺了一步 |

两个 CLI 共用的拒绝规则：spec 不是 JSON、不是 JSON 对象、或没有可画的节点 → 写出带
`audit.no_section` 的 result.json 并以退出码 5 拒绝；chartguard 对不可读数据表给
`data.unreadable`，对未知图型给 `encoding.unknown_chart_kind`——全部是拒绝（5），不是
近似，也永不 traceback。

### 编辑已有图稿（保留可编辑来源）

本 Skill 的可编辑来源就是 spec 本身：对既有图稿的每次修改都落在 spec 上，重跑同一 CLI 即再生成——SVG 始终携带 live text，不需要触碰渲染器。把既有图稿改对的三步：改 spec 的对应字段（节点/连接/数据）→ 重跑该路由的 CLI → 核对 result.json 的 findings 与导出检查。两次运行文本+几何一致（确定性已在 reproducibility.deterministic 中证明）。

- 元素级版本标注：materials/nodes 可携带 `version` 字段，provenance 的 `versions` 块把它回显到 result.json——来源与版本一起可核验。
- `edge.unknown_endpoint`（medium）：spec 声明的连接引用了图上不存在的节点，该连接不会被绘制，审计点名这条悬空边。
- `export.missing_glyphs`（high）：数据图表路由现在与其它三条路线共享字形覆盖检查。

## Limits

- **值来自声明，真伪不由引擎判。** accession 形状合法即通过（没有基因数据库）；材料清单
  和 connections 由调用方从材料构建——清单给错，审计对照的就是错的。
- **五类数据图。** bar/line/scatter/box/heatmap；violin、ridgeline、3D 会被拒绝而不是
  近似成相似图型。误差棒来自误差列，引擎不自己算 SEM/SD/CI；显著性标注只核存在性，画
  括号是手动的。
- **盒图不是象形。** 膜、受体形状、细胞轮廓都会暗示机制；诚实的替代是带标签的盒子。
- **大小写是检查不是事实。** `TP53` 在人类图里通过是因为它良构，不是因为确认了它存在。
- **casing 规约之外没有命名真伪检查**，vague_entity 是短黑名单，漏报多于误报。
- **确定性按文本与几何比较**，不逐字节；字体按图面实际字符解析，找不到全覆盖字体时如实
  报 missing_glyphs 而不是换字体蒙混。
- **checklist 比对是对声明负责**：coverage 只对照你给的 entities/relations 清单。

## Failure handling

| 症状 | 处置 |
|-|-|
| `export.missing_glyphs` | 换一个覆盖这些字符的字体——这就是"中文变方框"失败 |
| `trace.entity_untraceable` | 给节点补材料 id，或删掉该实体 |
| `trace.edge_not_in_source` | 删箭头，或把材料原句记进 connections |
| `encoding.not_numeric` | 清洗或剔除非数值单元格，绝不强转 0 |
| `caption.n_mismatch` | 有 n 列时查 distinct_n——caption 可能是每组样本量 |
| `label.overlap` | 加大 canvas_mm 或缩短标签，不许缩字号过地板 |
| `edge.backward_flow` | 调 layer 布局，让 flow 顺向 |
| `route.no_entry` / `route.no_exit` | 路线是环或断头——补起点/终点 |
| `apparatus.orphan_component` | 删遗留件或补连线 |
| `repro.nondeterministic` | 布局在两次运行间变了——先修再交付 |
| `axis.value_clipped` | 放宽轴范围或核对离群值 |
| status 为 refused / undetermined | 读 findings 里的原因——是 spec 错了，不是数据错了 |
| 引擎依赖缺失（matplotlib 不可用） | 启动失败 | Python 导入层抛 ImportError——依赖在 Requirements 声明、平台镜像已提供；如实说明，不谎称可落盘 |
| 输出目录不可写（权限问题） | 开跑前预检 /app/output 可写性；不可写时把 spec、诊断与拒绝模板 result.json 留存 /app/work 并向 harness 报告写盘失败，不静默丢产物 |

## 异常处理保证（本包重跑验证）

- 不可读的 spec（坏 JSON、JSON 数组）、无可画节点（空 nodes）→ pathway / schematic /
  apparatusfig 各自写出带 `audit.no_section` 的 result.json 并以退出码 5 拒绝——永不
  traceback。
- chartguard：未知图型 → `encoding.unknown_chart_kind`（5）；不可读数据表 →
  `data.unreadable`（5）；空表 → `data.no_rows`（5）；坏 JSON spec → `audit.no_section`（5）。
- 敌意探针（坏 JSON / 非对象 spec / spec 文件缺失 / 未知图型，六路 CLI × 三探针）在本机全部实测：退出码 4/5 且都有 result.json，无 traceback。
- 部分空白误差列渲染为跳过该棒（NaN），mark 行保留诚实的 None，不崩溃。

## Verification

```bash
python scripts/bench_chart.py       # 13/13 scenarios pass：编码、溯源、导出、空表拒绝、CJK 字体块
python scripts/bench_schematic.py   # 8/8 scenarios pass：版式与导出
python scripts/bench_pathway.py     # 11/11 scenarios pass：命名 + 版式
python scripts/bench_pathway2.py    # 10/10 pass：溯源 + 字体 + 确定性（注入）
python scripts/bench_apparatus.py   # 11/11 scenarios pass：装置与路线结构
python scripts/bench_apparatus2.py  # 9/9 pass：端到端 + 注入（glyph、非确定性）
```

合计 62/62，全部在本机全量通过；`examples/bench-report.json` 是汇总。每个场景只种一个
缺陷并指名必须触发的规则；clean 基线必须零 high/medium 发现，所以"全部点名"不可能通过。
字形与确定性缺陷无法用 spec 表达，由 bench_pathway2 / bench_apparatus2 打补丁注入真实
缺陷。每次运行会在 scripts/ 旁重写 report*.json；交付包里携带的是验证那次运行的原样副本。

## Requirements

Python 3.9+（3.14 实测）；依赖 matplotlib、numpy（本机 3.10.8 / 2.4.4 实测，未固定）；fontsel 为纯标准库实现。

## Dependencies

This skill requires the following Python packages:

```
pip install matplotlib numpy Pillow
```

- **matplotlib** (matplotlib, numpy): chart rendering, axis calibration
- **numpy**: numerical array operations for data extraction
- **Pillow (PIL)**: font measurement for text overflow detection and image handling

If these packages are not available, the skill will fail to produce figures. The
audit rules that check rendering output cannot run without matplotlib. Install them
before running any CLI command documented above.

## 创新增益

本 Skill 的方法链是三段式的，四条路由共享：

1. **结构化中间表示（实体—连接—步骤—流向）**：把材料解析成四张可逐条质疑的清单——
   实体（materials/nodes/数据列，带 evidence 或 mark→row 溯源）、连接（connections/
   edges，带 source 出处，白名单核对）、步骤（step_order/stage 编号与正文对照）、
   流向（edges[].type 线型语义 + layer 方向；chartguard 的轴方向与数值通道）。
   通用 Agent 通常从文字直接跳到画图，跳过这一步；本包把这一步做成 spec，图面合同
   先于布图存在。
2. **约束布图**：最长路径分层布图（显式 layer 优先），固定线型语义与色觉安全色板，
   期刊栏宽作为画布约束；同一 spec 渲染两遍的文本与几何签名必须一致才允许交付。
3. **自检（audit）**：56 条规则按 rule id 输出发现（溯源/结构/命名/编码/图例/字体/
   导出/复现），每条带 severity、message、元素或行号上下文；路由选择本身就是领域
   知识的四路复用——同一审计家族覆盖数据图表、通路图、装置图与通用示意图。

相对基础 Agent 的增益边界（创新证据的适用范围）：

- 增益在"可证明"一侧：溯源覆盖率、编码列核对、图例一致性、字形覆盖、确定性重跑、
  拒绝行为——引擎能算出数字，62 个 bench 场景每场景只种一个缺陷并点名必须触发的
  规则，clean 基线必须零发现。
- 不在"画得像"与"判真伪"：accession 形状合法即通过（无基因数据库）；不判断机制或
  方案的科学合理性；不做数值统计结论与期刊投稿排版（相邻课题承担）。
- 五类数据图之外（violin、ridgeline、3D）拒绝而不是近似；栅格图数字化不在范围内。

## 生态贡献

- **使用说明**：本 SKILL.md 即完整使用说明——用途、适用条件、路由表、调用方式、
  输入输出、异常处理、自查方法齐全；其他人或 Agent 可按说明独立复跑。
- **依赖**：Python 3.9+；matplotlib + numpy + Pillow 一行 pip 安装（见 Requirements
  与 Dependencies）；无网络依赖、无作者个人文件依赖。
- **配置**：全部行为由 spec JSON 配置（画布、字号、色板、图例开关、encoding 映射、
  min_font_pt、checklist），按案例调整不需要改引擎代码。
- **示例（示例，非正式案例结果）**：examples/spec-chart.json + examples/data-chart.csv、
  examples/spec-pathway.json、examples/spec-apparatus.json、examples/spec-schematic.json
  是四条路由的最小输入示例；examples/bench-report.json 是示意输出（bench 汇总）。
- **资源可复用**：scripts/ 各模块可独立导入——fontsel.py（逐字符字体解析）、
  provenance.py（溯源）、nomenclature.py（命名规约）、apparatus.py（结构审计）为跨题
  共享件，其他绘图包可直接取用。
- **适用范围**：数据图表（bar/line/scatter/box/heatmap）、生物通路/机制图、装置与
  技术路线图、通用示意图；不适用于栅格图数字化、"只描述不画图"的任务与期刊排版适配。
- **限制**：见 Limits 一节，逐条写明能力边界。
- **维护信息**：规则集以 rule id 固化，六个 bench 套件即版本门槛；任何规则改动必须
  同步本文件并重跑 bench（strict_gate 的 G4 规则一致性检查强制这一点）。

