---
name: graphical-abstract
description: >
  Build a graphical abstract (图形摘要) from bound research material and audit the
  claim it makes before delivery. Renders a single-panel layered editable SVG plus a
  300 dpi PNG, then checks the three-part claim (problem, method, finding) is actually
  stated, that every number on the canvas or in the caption appears in the source
  values, that every panel traces to the input material, that the reading order,
  legend and colour coding hold, and that the labels really render — matplotlib's
  default font has no CJK glyphs, so a Chinese abstract silently becomes rows of
  empty boxes. Writes a structured result.json that carries the case's output_contract
  fields verbatim plus case_id, findings, provenance coverage, reproducibility and
  font coverage, and refuses with an undetermined result (exit code 5) instead of
  crashing when the input cannot be read. Use when a task asks for a graphical
  abstract, TOC graphic, or single-panel visual summary, or for a source-preserving
  edit of one.
---

# graphical-abstract（图形摘要）

一张图形摘要是论文、基金和成果汇报里被最多人看、却被核对得最少的一张图。本 Skill
围绕四条可计算的判据交付与自检：

| 判据 | 引擎回答的问题 |
|-|-|
| claim | 三段主张（问题 / 方法 / 发现）是否真的都在图上 |
| numbers | 图上和图注里的每个数字是否都能追到来源数值 |
| provenance | 每个面板是否都能追到输入材料 |
| render | 是否可读、可复现、并落在出版限制之内 |

## 运行时入口与输出契约（Harbor runtime contract）

平台把本 Skill 安装在 /skills/weekly-skill，运行时输入固定为 /input/case.json 与
/input/task.md；工作目录 /app/work，最终交付物与 result.json 必须写入 /app/output。
实际输入文件和原论文是事实依据；不依据错误的领域标签补造数据。

### 六步运行时入口（harness agent 按此执行）

1. **读 case**：读 /input/case.json，取 case_id 与 output_contract 全部字段；读
   task.md 拿任务措辞。两者决定路由（见下表）。
2. **判形态路由**：图形摘要 / 目录图 / 单页视觉摘要 / 已有图稿的保源编辑；材料是否
   附实体-关系清单；标签语言。路由到引擎入口或拒绝路径。
3. **先产出目标产物**：从材料提取三段主张、实体、关系、数值，先用引擎把
   figure.svg（分层可编辑源文件）与 figure.png（300 dpi 导出件）画出来——产物先于
   审计存在，没有任何产物就没有可审计的对象。
4. **构造 spec**：把提取结果写成 spec JSON（放 /app/work），带上 case_id 与
   output_contract 原文，让引擎能把契约字段直通回填进 result.json。抽不出的字段
   留空并登记 uncertainty，不臆造。
5. **审计并修发现重跑**：跑引擎，按 rule 逐条修发现（见异常处置表）后重跑，直到
   状态为 clean 或剩余发现全部属于"材料本身不支持、只能如实声明"的一类。
6. **合并 result.json**：按下述合成规则把引擎结果、来源定位、不确定性与修改记录
   合成最终 /app/output/result.json，并把 figure.svg、figure.png 一并放入
   /app/output。可编辑产物附带真实渲染出的预览件。

### 任务措辞 → 路由决策表

| 任务措辞 / 材料形态 | 路由 | 依据 |
|-|-|-|
| "graphical abstract" / 图形摘要 / TOC graphic / visual summary | `python scripts/ga_figure.py --spec spec.json --out /app/output` | 主路径：三段主张 + 溯源 + 数字核对 + 字形覆盖 |
| 材料附实体清单与关系清单（entities / relations） | `python scripts/schematic.py --spec spec.json --checklist checklist.json --out /app/output` | coverage 审计逐项核对图面是否漏画来源声明的实体与关系 |
| "在现有图稿上改" / source-preserving edit | 读原 spec（或从原 SVG 的 live text 读回 label 清单），最小修改后重跑主路径 | 修改记录写入 result.json 的 change_records；两遍渲染一致保证改动可复现 |
| 中文标签 / 标签含 CJK、希腊字母、单位符号 | 主路径（fontsel 逐字符解析字体） | 字体按"图面实际用字"解析；缺字形报 export.missing_glyphs |
| 材料只描述了部分要素（例如只有方法没有发现） | 停止并声明：三段主张缺任一段即不开始画 | 主张缺段是 high 发现；画半张摘要是最常见的误导 |
| 材料是数值表，任务要求数据图 | 主路径 + source_values 全量登记 | 引擎核对图上每个数字（含图注）与来源表一致；统计图重绘本身不在引擎内（见 Limits） |
| 任务要求 PDF/EPS 导出 | 主路径交付 SVG+PNG，limits 写明格式边界 | 引擎只产 live-text SVG 与 300 dpi PNG，不谎称产 PDF |
| case.json / task.md 缺失或不可解析 | 拒绝路径（见下） | 结构化 result.json，状态 undetermined 或 failed，绝不裸崩 |
| 任务给的是整篇论文而非图面素材 | 先做"面板—要点"映射再进主路径 | 哪些信息必须上图、哪些进图注，由三段主张与字数上限约束 |

### result.json 合成规则（顺序即覆盖优先级）

```
result.json =
  1. case.json 中 output_contract 的全部原始字段 —— 逐字段原文保留：
     引擎已产出的字段保持审计值（审计值优先于 spec 携带值），
     spec 携带值的字段逐字直通，
     两边都产不出的字段填 null 并在 limits 里点名 —— 绝不编造
  2. case_id —— 取自 case.json（经 spec 直通或 CLI --case-id）
  3. 主结果 —— figure.svg（分层可编辑源文件）+ figure.png（300 dpi 导出件）
  4. 引擎审计字段 —— status, findings, severity_counts, audits, artifacts,
     provenance, reproducibility, font
  5. sources —— 证据/来源定位：materials[].source + nodes[].evidence 的映射，
     以及 provenance.coverage 的覆盖计数
  6. uncertainty —— 待复核项：抽取缺口、歧义取舍、默认参数、需人工确认项
  7. change_records —— （编辑任务）本轮相对上一版的字段级修改 before/after
  8. limits —— 能力边界与"未检查项"的如实声明
```

### 题面输出字段对齐（用题面原词）

| 题面要求 | 本包落点 |
|-|-|
| 输入标识 | result.json 顶部 case_id；schema_version 标注引擎版本 |
| 主结果 | figure.svg + figure.png |
| 证据/来源定位 | spec 的 materials[].source、nodes[].evidence → result.json 的 sources 与 provenance.coverage |
| 运行状态 | status：clean=完成；review=可交付但带发现；blocked=存在未修复 high；undetermined=输入不可运行（拒绝路径） |
| 不确定性 | uncertainty 列表，逐条可复核 |
| 可编辑源文件 | figure.svg（live text，分层）；完成标准"实体、关系、图例和数据映射正确"由 trace/legend/coverage 审计背书 |
| 导出件 | figure.png + result.json 的 font 与导出检查：格式（svg/png）、尺寸（canvas_mm 对 size_limit_mm）、分辨率（300 dpi）、字体（family 与 missing_glyphs）、色彩（Okabe-Ito 色盲安全） |
| 来源与修改记录 | provenance（元素来源与覆盖计数）+ reproducibility（两遍渲染一致）+ change_records（编辑任务的字段级修改） |

### 材料缺失时拒绝而不是崩溃

材料缺失、无法判断、运行失败三种情形都必须落一份结构化 result.json 再退出；绝不
裸抛异常，也绝不交一个空白输出目录。引擎层的拒绝路径（spec 不是可读 JSON / 不是
JSON 对象 / 文件缺失 / 画不出来）由引擎直接落 result.json：状态 undetermined、发现
规则 audit.no_section（high）、退出码 5。

退出码全表：

| status | exit | 含义 |
|-|-|-|
| clean | 0 | 零发现，直接交付 |
| review | 3 | 带 medium/low 发现，可交付但须逐条处置或声明 |
| blocked | 4 | 存在 high 发现，修复前不得交付 |
| undetermined | 5 | 输入不可运行（坏 JSON / 非对象 / 文件缺失 / 渲染失败），什么都没画 |

拒绝是自包含路径：它运行在任何审计存在之前，只依赖 json 模块，不调用契约回填
（回填所依赖的 spec 恰恰是读不出来的那份输入）；CLI 显式传入的 case 标识仍然保留。

| 情形 | status | 处置 |
|-|-|-|
| spec 不是可读 JSON / 不是 JSON 对象 / 文件缺失 | undetermined（引擎直接落盘） | 退出码 5，永不 traceback |
| spec 能读但画不出来（节点缺失、类型错位） | undetermined（引擎直接落盘） | 发现写明原因；已画的部分作废，不交半成品 |
| case.json 或 task.md 缺失/不可解析 | failed | harness 合成 result.json：reason=missing_input，uncertainty 写明缺什么 |
| 材料抽不出三段主张 | failed | 不臆造面板；按拒绝模板落盘，limits 写明缺哪段 |
| 材料只覆盖部分要素 | review | 照常出图；limits 写明未覆盖面，uncertainty 逐条登记 |

拒绝模板（**示例**，非正式案例结果）：

```json
{
  "case_id": "（取自 case.json）",
  "status": "failed",
  "reason": "empty_claim",
  "sources": [],
  "uncertainty": ["材料只给出了方法段，没有可引用的发现陈述，无法声明三段主张"],
  "limits": ["拒绝绘制：画半张图形摘要比不画更误导"]
}
```

## 两种"看起来成功"的失败

**一个漂移的数字。** 来源写 `3-fold`，图上变成 `10x`。图形摘要是一个数字最容易被
四舍五入成更惊人版本、又最没人回头核对的地方。引擎把图面（含图注）里的每个数字
做值归一化后与 source_values 比对，对不上就是 high 发现。

**渲染成空方框的标签。** matplotlib 默认用 DejaVu Sans，**没有 CJK 字形**。
`吸收快 3 倍` 渲染成一行空方框：文件正常写出、正常打开、什么都不报错——主张就是
没人读得到。渲染器在画之前按"图面实际用字"逐字符解析字体，审计报告没被覆盖的字：

```
font: Microsoft YaHei   missing_glyphs: -        -> clean
font: DejaVu Sans       missing_glyphs: 吸收快倍   -> export.missing_glyphs (high)
```

覆盖是逐字符的，不是"这是不是中文字体"：一个覆盖了汉字的字体仍可能缺 `µ`、`λ`。

## 完整 worked example（**示例**，非正式案例结果）

最小输入（examples/spec.json，节选；完整字段以文件为准）：

```json
{
  "case_id": "ga-example-001",
  "output_contract": {"deliverable": "editable SVG plus 300 dpi PNG",
                      "status": "audit verdict"},
  "deliverable": "editable SVG plus 300 dpi PNG",
  "canvas_mm": [170, 70], "size_limit_mm": [180, 80], "max_words": 60,
  "source_values": ["42", "3"],
  "takeaways": {"problem": "p1", "method": "m1", "finding": "f1"},
  "reading_order": ["p1", "m1", "f1"],
  "legend": ["吸收缓慢", "多孔涂层 42 nm", "吸收快 3 倍"],
  "materials": [
    {"id": "mat1", "name": "缓慢吸收", "source": "Introduction ¶1"},
    {"id": "mat2", "name": "多孔涂层", "source": "Methods ¶2"},
    {"id": "mat3", "name": "吸收速率", "source": "Results Fig 3b"}
  ],
  "nodes": [
    {"id": "p1", "label": "吸收缓慢", "evidence": "mat1", "layer": 0, "color": "#D55E00"},
    {"id": "m1", "label": "多孔涂层 42 nm", "evidence": "mat2", "layer": 1, "color": "#0072B2"},
    {"id": "f1", "label": "吸收快 3 倍", "evidence": "mat3", "layer": 2, "color": "#009E73"}
  ],
  "edges": [{"from": "p1", "to": "m1", "type": "activate"},
            {"from": "m1", "to": "f1", "type": "activate"}]
}
```

调用（本机实跑）：

```bash
python scripts/ga_figure.py --spec examples/spec.json --out examples/out --case-id ga-example-001
```

实跑输出（示意，非正式案例结果）：

```
{"status": "clean", "case_id": "ga-example-001", "findings": [],
 "wrote": "examples\\out\\result.json"}
```

实跑 result.json 关键字段（示意，非正式案例结果）：

```
schema_version   ga-figure/v1
case_id          ga-example-001
status           clean
deliverable      editable SVG plus 300 dpi PNG      <- output_contract 字段直通
audits           layout_status=clean, claim_status=clean,
                 claim_checked{nodes:3, edges:2, words:7,
                 takeaways_declared:[finding, method, problem],
                 colours:3, legend_declared:true}
font             family=Microsoft YaHei, missing_glyphs=""
provenance       checked=true, coverage{materials_declared:3, materials_drawn:3,
                 entities:3, entities_traced:3}
reproducibility  deterministic=true（两遍渲染按文本与几何比对）
artifacts        figure.svg + figure.png
limits           []
```

## Workflow

### 1. 先固定主张，再画图

spec 是中间表示：来源对图面**说了什么**，在任何布图决策之前。

- 三段主张缺任何一段：来源还不支持一张图形摘要——停下来说明，而不是把有的那一半
  画出来。 illustrated-half 是图形摘要最常见的误导方式。
- 每个节点的 evidence 把它钉到 materials 条目。追不到材料的面板是为了视觉平衡
  加上去的面板，审计会点名。
- source_values 是论文实际报告的数值（字符串列表）。图注 caption 里的数字同样
  被核对。
- 面板用了两种以上颜色而未声明 legend 会报发现（纯装饰色用 legend_exempt 豁免）。

### 2. Run it

```bash
python scripts/ga_figure.py --spec spec.json --out /app/output
```

退出码：0 clean / 3 review / 4 blocked / 5 undetermined。写出 result.json、
figure.svg（live text 可编辑）与 figure.png（300 dpi）。

### 3. Read the numbers that matter

- reproducibility.deterministic — 同一 spec 两遍渲染按文本与几何比对；false 意味着
  别人复跑得不到同一张图。
- font.missing_glyphs — 空 = 每个字符都有字形。
- findings 里 trace.* — 面板溯源与材料覆盖。
- provenance.coverage — 材料/实体的覆盖计数，逐条可核。

## 题集六方面检查表（逐项落点）

交付前逐项核对；任何一项缺失都要么补齐、要么在 limits 里写明原因。

| 题集六方面 | spec/交付落点 | 引擎检查 |
|-|-|
| 科学实体 | materials[] + nodes[].evidence（每个实体可溯源） | trace.entity_untraceable, trace.evidence_not_in_materials, trace.material_not_drawn |
| 空间关系 | nodes[].layer 分层、edges[].from/to、reading_order、canvas_mm | ga.reading_order, ga.reading_order_unknown_node, edge.backward_flow, edge.zero_length, label.overlap, label.outside_canvas |
| 数据编码 | nodes[].color（Okabe-Ito 色盲安全色板）+ source_values 数值映射 | ga.value_not_in_source, ga.source_values_invalid, ga.source_values_unavailable, colour.not_cb_safe |
| 图例标注 | legend[]（两种以上颜色必须声明）+ caption | ga.legend_not_declared, legend.entry_unmatched, legend.entity_unlisted |
| 可编辑源文件 | figure.svg live text（分层，字体以非内联方式写入，文字可改） | export.no_live_text, export.embedded_raster, export.no_font_family |
| 导出格式 | figure.png（300 dpi）+ font 解析记录 | export.missing_glyphs, export.no_font, export.low_dpi, font.too_small, label.mismatch |

## Rules

### The claim（三段主张与数字）

| rule | severity | what it proves |
|-|-|-|
| `ga.missing_takeaway` | high | problem / method / finding 未全部声明（声明字段类型错位也按未声明计） |
| `ga.takeaway_not_placed` | high | 声明了的主张没有出现在任何画布标签上 |
| `ga.value_not_in_source` | high | 图上或图注里的数字不在来源数值里 |
| `ga.source_values_invalid` | medium | 声明的来源数值不是列表，数字无法核对 |
| `ga.source_values_unavailable` | medium | 没有来源数值，数字无法核对 |
| `ga.takeaway_panels_unlinked` | medium | 主张面板之间没有连线，读不成"问题→发现"的推进 |
| `ga.reading_order` | medium | 声明的阅读顺序与画出来的分层矛盾 |
| `ga.reading_order_unknown_node` | medium | 阅读顺序指向画布上不存在的面板 |
| `ga.text_too_long` | medium | 字数超过声明上限 |
| `ga.size_out_of_spec` | medium | 画布超过出版方最大尺寸 |
| `ga.empty_label` | medium | 面板没有标签文字，无法承载主张 |
| `ga.legend_not_declared` | medium | 两种以上颜色却未声明图例，色彩编码无解释 |

### Provenance（溯源）

| rule | severity | what it proves |
|-|-|-|
| `trace.entity_untraceable` | high | 面板没有材料引用 |
| `trace.evidence_not_in_materials` | high | 面板指向不存在的材料条目 |
| `trace.material_not_drawn` | medium | 来源要求的材料没有出现在图上 |
| `trace.edge_not_in_source` | high | 画出的连线是来源没说的关系（schematic 入口） |
| `trace.connection_not_drawn` | medium | 来源声明的连线没有画（schematic 入口） |
| `trace.no_connection_list` | low | 有材料清单但没有连线清单，画出的连线无法核对 |
| `coverage.incomplete` | high | 图面漏掉了清单声明的实体或关系（schematic 入口） |
| `route.numbering_vs_text` | medium | 步骤编号与正文顺序错位（schematic 入口） |

### Render and export（渲染与导出）

| rule | severity | what it proves |
|-|-|-|
| `repro.nondeterministic` | high | 同一 spec 两遍渲染不一致 |
| `export.missing_glyphs` | high | 字符没有字形，渲染成空方框 |
| `export.no_live_text` | high | SVG 标签是轮廓路径，不是文字，不可编辑 |
| `label.overlap` | high | 标签在固定画布上相互碰撞 |
| `label.wider_than_box` | medium | 标签溢出它自己的形状 |
| `label.mismatch` | high | 画出来的标签与 spec 不一致 |
| `label.outside_canvas` | high | 标签被画布边缘裁切 |
| `font.too_small` | medium | 字号低于声明下限 |
| `edge.backward_flow` | medium | 流向箭头指回更早的层 |
| `edge.count_mismatch` | high | 画出的连线数与 spec 不符 |
| `edge.zero_length` | high | 两个相连节点被放在同一个点 |
| `entity.duplicate` | medium | 两个节点标签与颜色全同，无法区分 |
| `export.embedded_raster` | medium | SVG 内嵌位图，无法干净缩放 |
| `export.low_dpi` | medium | 导出低于 300 dpi |
| `export.no_font` | high | 没有任何字体被解析出来 |
| `export.no_font_family` | low | 导出未声明字体族 |
| `colour.not_cb_safe` | low | 颜色在 Okabe-Ito 色盲安全色板之外 |
| `legend.entry_unmatched` | medium | 图例条目匹配不到任何画出的标签 |
| `legend.entity_unlisted` | low | 画出的标签没有图例条目解释（图例被要求时） |
| `audit.no_section` | high | 输入不可运行（拒绝路径的发现规则） |

## 异常处置表

| 异常 | 识别 | 处置动作 |
|-|-|-|
| 三段主张缺段（材料只给了部分） | ga.missing_takeaway | 停止绘制并声明缺口；画半张摘要比不画更误导 |
| 图上数字对不上来源 | ga.value_not_in_source | 用报告值或删掉它；绝不朝更惊人的方向取整 |
| 图注里出现未经来源核对的数字 | ga.value_not_in_source（where=caption） | 与图面数字同一标准：换回来源值或删除 |
| 面板无材料引用 | trace.entity_untraceable | 补材料 id 或删面板；不为视觉平衡留无源面板 |
| 字体缺字形（中文变方框） | export.missing_glyphs / export.no_font | fontsel 按图面实际用字逐字符搜索系统字体；仍无覆盖则保留发现并在 limits 声明，不静默换字体 |
| 标签碰撞 / 出界 | label.overlap / label.outside_canvas | 加大 canvas_mm 或缩短标签；不低于字号下限（min_font_pt，默认 6pt） |
| 字数超限 | ga.text_too_long | 细节移进图注；摘要承载主张，不承载证据 |
| 画布超出版面 | ga.size_out_of_spec | 先把 canvas_mm 改进 size_limit_mm 之内，再添加内容 |
| 两遍渲染不一致 | repro.nondeterministic | 修布图后重跑；交付前跑两遍是流程要求 |
| spec 类型错位（source_values/legend/reading_order 不是列表） | ga.source_values_invalid；其余按字段语义降级 | source_values 类型错位报发现；legend/reading_order/canvas_mm 非列表按"未声明/未指定"处理并在 limits 说明，不崩溃 |
| takeaways 不是对象 | ga.missing_takeaway | 按未声明处理（发现消息写明类型），审计继续，不崩溃 |
| spec 是坏 JSON / 非对象 / 文件缺失 | audit.no_section（引擎拒绝路径） | 状态 undetermined、退出码 5、落盘 result.json，永不 traceback |
| 引擎依赖缺失（matplotlib/Pillow） | Python 导入层 ImportError | CLI 无法在导入失败后写 result.json——依赖在 Dependencies 声明、平台镜像已提供；如实说明而非谎称可落盘 |
| 输出目录写不进（权限） | 引擎异常退出 | result.json 记 limits 与原因；换可写目录重跑 |
| 任务要求 PDF/EPS 导出 | 路由阶段 | 交付 SVG+PNG 并在 limits 写明格式边界，不谎称产 PDF |

## 创新增益

本 Skill 相比通用 Agent 的新增能力，全部是引擎可计算、白板可对照的：

1. **主张结构审计**：图形摘要被当作"问题—方法—发现"三段主张来验证——三段是否
   都声明、是否都真的画在画布上、面板是否连成推进、阅读顺序是否与分层一致。
   通用 Agent 直接从文字跳到画图，没有这一层图面合同。
2. **数值直通核对**：图面与图注里的每个数字做值归一化后与来源数值表比对，对不上
   即 high 发现——针对"摘要里的数字朝更惊人方向漂移"这一高频失败。
3. **逐字符字形覆盖**：字体按图面实际用字解析并逐字符验证，把"中文变方框"从
   静默失败变成 high 发现；覆盖记录（family 与缺失字符清单）进 result.json。
4. **确定性证明**：同一 spec 渲染两遍，按文本与几何签名比对，deterministic=true
   是交付条件而不是口号。
5. **溯源覆盖计数**：materials 声明数 / 画出数 / 实体追踪数逐项计数，任何人可以
   用来源材料复算这些数字。

增益边界（创新证据的适用范围）：增益在"可证明"一侧——主张完整性、数字一致性、
溯源覆盖、字形覆盖、二次可复现。不在"画得像"：本包画带标注的盒子与箭头，不做
仪器象形图，不判断科学合理性，不做统计图重绘（题面明示不属于本课题）。

## 生态贡献

- **使用说明**：本 SKILL.md 即完整使用说明——用途、适用条件、调用方式、输入输出、
  异常处理、限制和自查方法齐全；其他人或 Agent 可按说明独立复跑。
- **依赖**：matplotlib + numpy + Pillow，一行 pip 安装（见 Dependencies）；无网络
  依赖、无作者个人文件依赖。
- **配置**：全部行为由 spec JSON 配置（画布、字号上限下限、图例开关、豁免开关、
  min_font_pt、source_values），按案例调整不需要改引擎代码。
- **示例**：examples/spec.json 是含 case_id 与 output_contract 的最小输入示例（把
  上节 worked example 的命令指向任意可写目录即可实跑复现）；examples/bench-report.json
  与 examples/bench-ga-report.json 是示意输出。
- **资源可复用**：scripts/ 各模块可独立导入——fontsel.py（逐字符字体解析）、
  provenance.py（溯源与确定性）、contract_echo.py（契约回填）是跨题共享件；
  references/ 下两篇方法文档（主张规则、字体与导出）可单独取用。
- **适用范围**：单页图形摘要、目录图（TOC graphic）、单页视觉摘要、已有图稿的
  保源编辑；不适用于多面板数据图集与期刊排版适配。
- **限制**：见 Limits 一节，逐条写明能力边界。
- **维护信息**：规则集以 rule id 固化，bench 回归套件（4 个 bench 文件、42 个场景）
  即版本门槛；任何规则改动必须同步本文件并重跑 bench（strict_gate 的 G4 规则一致
  性检查强制这一点）。

## Verification

```bash
python scripts/bench_ga.py        # 9/9 scenarios: claim 与布图（打磨前规则集）
python scripts/bench_ga2.py       # 9/9: 溯源、字形覆盖、确定性（注入缺陷两个）
python scripts/bench_ga3.py       # 16/16: 新规则与守卫、契约回填、拒绝路径
python scripts/bench_schematic.py # 8/8: 布局与导出（schematic 入口）
```

四个 bench 在本机全量通过。字体与确定性的缺陷无法用 spec 表达，对应场景通过
patch 字体解析器与确定性检查注入——测的仍是检查器对真实缺陷的反应，不是 mock。
拒绝路径（坏 JSON / 非对象 / 文件缺失 → 状态 undetermined + 退出码 5 + 落盘
result.json）由 bench_ga3 与外部探针双重覆盖。

## Dependencies

This skill requires the following Python packages:

```
pip install matplotlib numpy Pillow
```

- **matplotlib**：渲染与 SVG/PNG 导出（schematic 渲染层）
- **numpy**：布局审计的数值运算
- **Pillow (PIL)**：字体测量（标签溢出检测）

If these packages are not available, the skill fails at import time and cannot
produce figures — the CLI cannot write a result.json from a failed import. This is
declared honestly rather than papered over: install the packages (they are present
in the pinned evaluation image) before running any command documented above.

## Limits

- **主张匹配是文本匹配。** 主张计为"已放置"当其声明文本以子串出现在某标签里，或
  节点 id 匹配。引擎不检查标签的**含义**是否等于主张说的意思。
- **数字核对只做值归一化。** `3` 与 `3.0` 视为同值；`3×` 与 `threefold` 不匹配，所以
  请写数字。单位变化（`3x` → `3%`）与限定词丢失（"up to 3x" → "3x"）检测不了，
  那需要读者。
- **字数统计覆盖标签与声明的图注。** 光栅化进位图的文字、事后在矢量编辑器里加的
  文字，引擎看不见。
- **没有内置期刊参数表。** size_limit_mm 与 max_words 是你声明的；内置一张期刊表
  会在出版方更新指南的那一刻变成错误来源。
- **盒子，不是象形图。** 图形摘要通常需要 imagery；发明象形图等于暗示引擎无法
  知道的机制。
- **统计图重绘不在引擎内。** 数据图表场景下引擎核对图上数字与来源表的一致性
  （source_values），绘制仍由 matplotlib 图层完成；需要真统计图时在 limits 声明。
- **它不能告诉你摘要是否公允** ——只能保证三段都在、数字是论文的、面板可溯源、
  渲染可复现。
