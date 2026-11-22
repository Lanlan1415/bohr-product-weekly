---
name: source-chart
description: >
  科研数据图表生成与编辑：把"画一张图"变成一次可核验的数据编码。读真实数据表，
  用声明式编码把通道映射到列名（拒绝近似绘制），渲染柱状/折线/散点/箱线/
  热图与分组柱，交付可编辑 SVG、PDF 与 300 dpi PNG，并对结果做画布级审计：轴标签与
  单位、出界值、图例与系列对齐、误差线含义、图注样本量、显著性标记指向、图元到源行
  的双向溯源、PNG 物理分辨率实测、CJK 字体回退。每张图带 mark_to_row 台账——任何
  一根柱子都能回查到源数据的行与列。Use when a task supplies a data table and asks
  for a chart, figure panel, or an editable figure whose values must be traceable
  to the source.
---

# source-chart（科研数据图表生成与编辑）

一张图是对数据的一个断言。这个 Skill 让断言变得可检查：每个图元绑定源数据行，
每个通道绑定列名，导出在离开前被审计。

三个环节：

1. **encode** —— 把 spec 对照数据表验证，不合法即拒收
2. **render** —— 绘制并保留图元 → 源行映射
3. **audit** —— 校验标签、单位、出界、图例、溯源、导出

**第 1 步的拒收是特性。** 让文本列驱动数值通道得到的是一条指名道姓的错误，而不是
一张零值图。建立在误读列之上的图比没有图更糟——它看起来权威。

## 六步运行时入口（Harbor）

运行时原始输入固定为 /input/case.json 与 task.md；中间产物写 /app/work，最终结果
写 /app/output。依序执行：

- **第 0 步·读案例**：读 /input/case.json，取 case_id 与 output_contract（结果必须
  保留的字段清单），再按 task.md 指向的路径读**实际数据材料**（CSV/JSON 表、论文
  中的源数据表）。数值一律来自文件——凭记忆敲进 spec 的数字是捏造值。
- **第 1 步·判形态路由**：按下方「任务措辞与形态 → 路由」决策表定图型与 spec 形状；
  源数据在正文/表格材料里时先抽取成表文件（CSV/JSON），不在 spec 里内联数值。
- **第 2 步·先产出目标产物**：先出图与 result.json 写进 /app/work——预算有限时先
  有诚实的初版图与发现清单，再增量补齐导出参数与审计修复。
- **第 3 步·构造 spec**：写编码 spec（通道映射到列名，见 Workflow 第 2 步），带上
  case_id 与 output_contract 原样传递。材料没有的信息留空——空缺会变成发现或待复核，
  绝不编造数值或单位去"喂饱"规则。
- **第 4 步·审计**：跑 scripts/chartguard.py，得 findings、mark_to_row 与三件导出
  （SVG/PDF/PNG）。
- **第 5 步·修发现重跑**：逐条处理 findings——单位缺的补单位、图例错的调 legend、
  出界值先核实是否录入错误再决定改 limits；确认是口径内误报的按 Limits 说明，不删
  条目。修完重跑至 clean/review。
- **第 6 步·合并 result.json**：把引擎产物组装成三段交付（见输出契约映射）：可编辑
  源文件（SVG 加 spec）、导出件（PNG/PDF 加导出检查）、来源与修改记录（mark_to_row
  加 case_id）。回填 output_contract 点名的每个字段。

## 任务措辞与形态 → 路由

| 任务措辞 / 案例形态 | 图型与 spec | 说明 |
|-|-|-|
| 柱状图 / 组间比较 / treatment vs control | kind 为 bar，x 到类别列，y 到数值列 | 多组时加 group 通道；误差列用 y_err 并声明 error_meaning |
| 折线图 / 趋势 / 时间序列 | kind 为 line，x 到数值或序号列 | 数值 x 必须带单位；y_err 可画误差带 |
| 散点图 / 剂量-响应 / 相关 | kind 为 scatter，x、y 都到数值列 | x 为类别列会被拒收（散点 x 必须数值） |
| 箱线图 / 分布比较 | kind 为 box，按 group 分箱 | 每个观测仍记入 mark_to_row，分布可溯源到原始行 |
| 热图 / 矩阵 / 表达量 | kind 为 heatmap，x、y 定格，value 填色 | 缺格画为 NaN 空洞而非 0 |
| 多组分组柱 / grouped bars | bar + group 通道 | 组内按类别槽位错位绘制（dodge），不重叠 |
| 带误差线 / SD / SEM | 任意图型加 y_err 通道 | 必须声明 error_meaning，图注写明 |
| 中文标注 / CJK 材料 | 任意图型 | 引擎检测 CJK 字体能力，缺字体即报 label.cjk_font_missing 并给处置 |
| 期刊投稿 / 栏宽要求 | spec 加 export 的 width_mm 字段 | 实测图宽对回声明宽度；SVG 活字、PDF 合法性、PNG 分辨率逐一实测 |
| 显著性标记校验 | spec 加 significance[].between | 只校验标记指向的组存在于数据；画括号是人工步骤 |
| 示意图 / 机制图 / 流程图（无数据表） | 不属本 Skill | 无数据可映射，走示意图路径 |
| 从位图读数 / 数字化 / 描述已有图 | 不属本 Skill | 数字化读数不确定度必须保留，是另一条路径 |

## Workflow

### 第 1 步·读数据，不要重打

```bash
python scripts/chartguard.py --spec spec.json --data table.csv --out /app/output
```

值必须来自文件。数据表支持 UTF-8 CSV（含 BOM）与 JSON（行数组或 {"rows": [...]}）。

### 第 2 步·显式声明编码

```json
{
  "kind": "bar",
  "x_label": "Treatment", "x_unit": "dose",
  "y_label": "Response", "y_unit": "a.u.",
  "caption_n": 6,
  "legend": true,
  "error_meaning": "SD",
  "encoding": {
    "x": "condition",
    "y": "response",
    "y_err": "response_sd",
    "group": "group"
  }
}
```

| 字段 | 何时需要 | 含义 |
|-|-|-|
| `encoding.x` / encoding.y | 全部图型 | 通道映射到**列名**，不映射到值——间接层是溯源的前提 |
| encoding 的 value 通道 | heatmap | 单元格取值列 |
| encoding 的 group 通道 | 多系列 | 分组列；驱动配色与图例 |
| encoding 的 y_err 通道 | 有误差 | 每行误差量列；语义必须在 error_meaning 声明 |
| x_label / x_unit / y_label / y_unit | 全部 | 数值轴必须带单位；类别轴豁免单位 |
| caption_n | 图注声明 n | 与源表行数或 n 列对账 |
| error_meaning | 有误差线 | SD / SEM / CI / range，写进图注 |
| export 的 width_mm 字段 | 期刊栏宽 | 实测图宽须落在容差内（默认 2 mm） |
| significance[] | 显著性标记 | 每条 between 指向的两个组必须都在数据里 |
| figsize, dpi | 可选 | 默认 3.5×2.8 英寸、300 dpi |

### 第 3 步·读审计，修复，重跑

退出码：0 clean，3 review（有 medium/low 待处理），4 blocked（有 high），5 refused
（拒收——spec 或数据无法运行，见 Failure handling）。不要带着 blocked 或 refused
交付。每次运行向 out 目录写 result.json 并渲染三件导出。确定性引擎：同一 spec 与
数据重跑得到同一份 findings（字节级相同）。

### 第 4 步·验证引擎没有退化

```bash
python scripts/bench_chart.py
```

19 个场景，每个植入一个缺陷或钉住一个误报守卫（partial_blank_err、scatter_clean、
cjk_label 在有 CJK 字体的机器上必须保持安静）。clean 基线不得产生任何 high/medium
发现——靠全面开火通过的检测器过不了这一关。本机 19/19 通过。

## 规则库（完整规则索引，33 条）

### 编码与拒收（6 条）

| rule | severity | 证明什么 |
|-|-|-|
| `encoding.required_channel_unmapped` | high | 图型必需的通道未被映射——拒收而非近似 |
| `encoding.column_missing` | high | spec 点名了表中不存在的列 |
| `encoding.not_numeric` | high | 文本列驱动数值通道 |
| `encoding.unknown_chart_kind` | high | 请求的图型不受支持——拒收，不降级成相似图 |
| `encoding.bad_shape` | high | encoding 不是通道到列名的对象 |
| `data.no_rows` | high | 表无数据行——拒收，不崩溃 |

### 轴与值（6 条）

| rule | severity | 证明什么 |
|-|-|-|
| `axis.x_label_missing` | high | X 轴无标签，脱离题注即不可读 |
| `axis.y_label_missing` | high | Y 轴无标签，脱离题注即不可读 |
| `axis.x_unit_missing` | medium | X 数值轴未声明单位（类别轴豁免） |
| `axis.y_unit_missing` | medium | Y 数值轴未声明单位（类别轴豁免） |
| `axis.value_clipped` | high | 数据值落在绘制范围外——图元不可见而图面看似完整 |
| `caption.n_unparseable` | medium | 图注样本量不是数字，无法对账 |

### 系列、图例与误差（5 条）

| rule | severity | 证明什么 |
|-|-|-|
| `series.missing_from_chart` | high | 数据中的组未被绘制——等同丢了一个处理组 |
| `legend.absent` | medium | 多组着色而无图例，颜色无含义 |
| `legend.series_mismatch` | medium | 图例条目与实际绘制的系列不一致——颜色映射到错误的名字 |
| `error.column_not_drawn` | high | 误差通道已映射但未画出 |
| `error.meaning_undeclared` | medium | 误差线未声明含义（SD/SEM/CI/极差） |

### 溯源与数值（3 条）

| rule | severity | 证明什么 |
|-|-|-|
| `traceability.missing` | high | 图元无源行索引，图无法回溯 |
| `traceability.row_coverage` | medium | 图元少于源行——有行被静默过滤 |
| `encoding.drawn_value_mismatch` | high | 从画布图元读回的值不等于源数据——图改写了数据 |

### 标注与导出（8 条）

| rule | severity | 证明什么 |
|-|-|-|
| `label.cjk_font_missing` | medium | 标注含 CJK 而机器无 CJK 字体——将渲染为方框 |
| `caption.n_mismatch` | high | 图注样本量与源表（或 n 列）不符 |
| `annotation.unknown_comparison` | high | 显著性标记比较的组不在数据中 |
| `export.no_live_text` | high | SVG 无活字文本——标签转曲，不可编辑 |
| `export.pdf_invalid` | high | PDF 导出不是合法 PDF |
| `export.low_dpi` | medium | 位图低于 300 dpi |
| `export.png_dpi_mismatch` | medium | PNG 内嵌物理分辨率（pHYs 实测）低于 300 dpi |
| `export.width_out_of_band` | medium | 实测图宽超出声明的目标栏宽容差 |

### 拒收路径（4 条）

| rule | severity | 发生了什么 |
|-|-|-|
| `spec.unreadable` | high | spec 缺失或不可读——exit 5 拒收并写 result.json，绝不抛 traceback |
| `spec.not_object` | high | spec 不是 JSON 对象——exit 5 拒收并写 result.json |
| `data.unreadable` | high | 数据文件缺失或不可读——拒收 |
| `deps.unavailable` | high | matplotlib/numpy 缺失——诚实拒收并给安装指引，不产出残缺图 |
| `render.failed` | high | 渲染或审计内部异常——按拒收处理，绝不把 traceback 抛给调用方 |

## 输出契约与三段结构映射

引擎级 result.json（chartguard.py 直接产出）：schema_version、status（clean / review
/ blocked / refused）、findings[]（每条带 rule、severity、message、basis、fix 与
定位字段——row、value、channel、column、mark_index）、severity_counts、encoding
（图型、通道映射、源行数、图元数）、mark_to_row[]（{mark, row, x, y, series, y_err}）、
artifacts（svg/pdf/png 路径）、spec、case_id（spec 顶层有则回填，拒收路径亦然）、
output_contract 点名的每个键（spec 携带同名值则原样拷入；推导不出则置 null 并在
limits 记一条说明）。

最终交付把引擎产物组装进 output_contract 点名的三段结构（字段名用评分口径原词）：

| 输出段 | 组装来源 | 完成标准 |
|-|-|-|
| 可编辑源文件 | figure.svg（活字文本、分层图元）+ spec.json（编码可重跑） | 实体、关系、图例和数据映射正确——SVG 有活字（export.no_live_text 为证）、通道映射到列名 |
| 导出件 | figure.png（300 dpi 实测）、figure.pdf（合法性实测）+ 导出检查发现 | 目标格式、尺寸、分辨率、字体检查齐备；可在目标场景打开（width_mm 声明时实测宽度） |
| 来源与修改记录 | mark_to_row[]（图元↔源行双向台账）+ case_id + encoding 通道映射 + findings 修复轮记录 | 关键图面可核验——任何柱/点可回查到源行，任何行可定位到图元；异常有说明 |

status 映射：clean → 全部通过；review → 有 medium/low 待处理（写明待补什么）；
blocked → 有 high（列出）；refused → 无法运行（写明环节与修复动作）。材料缺失、
无法判断、运行失败三种情况分开说明。

## 最小调用示例（示例）

输入 examples/spec-contract.json（case_id 为 challenge-1bd90d8a-case-01，
output_contract 点名 editable_source、export_checks、provenance 三个键）与
examples/data-contract.csv（4 行分组数据）。调用：

```bash
python scripts/chartguard.py --spec examples/spec-contract.json --data examples/data-contract.csv --out out_example
```

引擎实跑输出（本机实测，节略；exit 0）：

```json
{
  "schema_version": "chartguard/v1", "status": "clean",
  "case_id": "challenge-1bd90d8a-case-01",
  "findings": [],
  "severity_counts": {},
  "encoding": {"chart_kind": "bar", "channels": {"x": "condition", "y": "response",
               "y_err": "response_sd", "group": "group"}, "rows_in_source": 4,
               "marks_drawn": 4},
  "mark_to_row": [
    {"mark": "bar0", "row": 0, "x": "control", "y": 12.4, "series": "WT", "y_err": 1.1}
  ],
  "artifacts": {"svg": "out_example/figure.svg", "pdf": "out_example/figure.pdf",
                "png": "out_example/figure.png"},
  "editable_source": null, "export_checks": null, "provenance": null
}
```

三个 contract 键引擎推导不出，置 null 并在 limits 说明——第 6 步由你把三段组装
填充；PNG/SVG/PDF 是真实渲染产物，可直接打开检查（示意输出标注为示例，不冒充
正式案例结果）。

## Limits

- **只支持五种图型。** bar、line、scatter、box、heatmap。小提琴、山脊、等高线与
  3D 图不在范围内——spec 被拒收，而不是被静默降级成相似图。
- **不做统计计算。** 误差线画自声明的误差列。引擎绝不自己算 SEM/SD/CI——一个算错
  的派生统计量与测得的统计量无法区分。表里只有重复测量时，先显式聚合并说明。
- **显著性标记只校验不绘制。** 审计检查声明的比较在数据中存在；画括号是人工步骤。
- **热图色阶截断不审计。** 被截断的色阶会夸大差异；检测它需要知道提问意图。
- **画布数值对账覆盖 bar 与 scatter 的逐图元读回**；line 与 heatmap 的图元与误差线
  对象混合（errorbar 容器、images），经 mark_to_row 台账对账而非逐 artist 读回。
- **审计证明编码，不证明推断。** 它能告诉你一根柱不可溯源；它不能告诉你 t 检验
  选错了——统计方法本身的选择由数据分析方向负责。
- **CJK 字体检查是环境相关的能力探测。** 装了 CJK 字体的机器上规则按设计保持安静；
  未装时报出并给安装与配置处置。
- **长度类检查有声明口径。** 宽度对账只在 spec 声明 export.width_mm 时触发；dpi
  实测依赖 PNG 的 pHYs 块（缺失则不判，记 unknown 而非失败）。

## 异常处置表

| 形态 / 故障 | 处置 |
|-|-|
| spec 不可读 / 非 JSON 对象 / 依赖缺失 | exit 5 拒收，仍写 refused 的 result.json，绝不抛 traceback；按 message 修复后重跑 |
| 数据文件缺失 / 不可读 | data.unreadable 拒收——核对 --data 路径与编码（UTF-8 CSV/JSON） |
| 数据缺列（spec 点名不存在的列） | encoding.column_missing 报出并列出可用列——按清单改名 |
| 空值 / 半空数值列 | 空单元格画为空洞（NaN），mark 行保留诚实 None；半空列按非数值拒收——清洗后显式重跑 |
| 量级异常（离群值） | axis.value_clipped 报出；先核实是否录入错误，再决定改 limits——不为迁就离群值压扁全图 |
| 标签过长 | 长标签照常渲染；重叠遮挡由人工按图面调整 figsize 或缩写——引擎在 limits 中声明此项不做 |
| 字体缺失（CJK） | label.cjk_font_missing 报出并给两种处置：装字体，或将 rcParams font.sans-serif 设为 CJK 族 |
| 导出失败 / 分辨率不符 | export.png_dpi_mismatch 以文件实测为准；重设 dpi 后重导并复查 |
| 图注 n 与表不符 | caption.n_mismatch 报出；先核对 n 列语义（per-group 还是总计），再修图注 |
| 数据行多于图元 | traceability.row_coverage 报出——排查被静默过滤的行 |
| 同一输出目录重复运行 | 引擎确定性幂等：同 spec 同数据得字节级相同的 result.json；重复运行只为复核 |
| 材料缺失、无法判断、运行失败 | 三类分别说明：拒收是运行状态、发现是图面问题、limits 是声明的不确定——不互相冒充 |

## 使用增益与对照方法

- **公平对照**：同一数据文件、同一图型要求、相同导出参数下，不加载本 Skill 的基础
  Agent 与加载后各跑一次，按四个可数项对比：数值对账率（图元读回值与源表一致的
  比例）、标注完整率（轴标签/单位/图例/误差含义/图注 n 五项齐备数）、可编辑性
  （SVG 活字 + 源文件可重跑）、溯源完整度（每个图元能否回查源行）。平台白板是对照
  基准，不是参赛者答案。
- **增益证据形式**：scripts/bench_chart.py 19 场景——每场景植入一个缺陷或钉住一个
  误报守卫；确定性引擎重跑同结果，增益可被第三方复跑验证。

## 验证

```bash
python scripts/bench_chart.py  # 19 scenarios: 每条规则一场景加误报守卫
```

本机 19/19 通过；clean 基线必须零发现。

## Requirements

- Python 3.9+（3.14 实测）
- matplotlib、numpy（渲染与画布对账）；本机 matplotlib 位于用户 site-packages，
  运行验证用 python -X utf8（不带 -I）以保证用户包可见
- Pillow 未被引擎依赖（文档历史条目，已移除）；依赖缺失时引擎以 deps.unavailable
  诚实拒收（exit 5），不产出残缺图

## 创新增益

本 Skill 相比通用 Agent 与现成绘图库的新增能力（每条附能力边界与证据形式）：

1. **图元↔源行双向台账**：mark_to_row 把每个图元钉到源数据行（mark/row/x/y/series/
   y_err），从图回查数据、从数据定位图元都是一次查表——"没人说得出每根柱的数字来自
   哪一列"的失败模式被台账直接消除。
   *边界*：台账到行级，不到字符偏移；line/heatmap 的画布读回经台账而非逐 artist。
   *证据形式*：bench clean 与 scatter_clean 场景断言台账与图元数一致。
2. **画布级数值对账**：渲染后从 matplotlib artist 读回柱高/散点值与源数据逐个对账
   （encoding.drawn_value_mismatch）——"画得像但不准"的幻影柱、静默丢值在交付前被
   抓住，而不是被审稿人抓住。
   *边界*：bar/scatter 逐 artist 读回；line/heatmap 混合容器经台账对账。
   *证据形式*：bench clean 基线在对账通过时保持安静；对账失败即 high。
3. **文件级导出实测**：PNG 分辨率从 pHYs 块读回实测（export.png_dpi_mismatch）、
   SVG 活字检查（export.no_live_text）、PDF 合法性、声明栏宽容差对账
   （export.width_out_of_band）——导出质量以交付物本身为证据，不采信参数。
   *边界*：pHYs 缺失记 unknown 不判负；宽度对账需声明 width_mm。
   *证据形式*：bench low_dpi 场景同时断言参数级与文件级两条规则。
4. **中文标注字体回退探测**：检测标注中的 CJK 字符并探测机器字体能力，缺失即报
   label.cjk_font_missing 并给安装/配置两种处置——"中文标注被替换成方框"从交付后
   才发现提前到导出前。
   *边界*：环境相关——装了 CJK 字体的机器按设计保持安静。
   *证据形式*：bench cjk_label 场景按机器能力条件断言。
5. **拒收纪律**：未知图型、文本列驱动数值通道、空表、不可读 spec、缺失依赖一律
   exit 5 指名拒收并写 result.json，绝不近似、绝不崩溃——错误形态是可处置的清单
   条目，而不是一张看起来完成的错图。
   *边界*：拒收只覆盖声明可判定的形状错误；语义级选型错误不在拒收范围。
   *证据形式*：bench unknown_chart_kind、empty_table、unreadable_spec、not_object、
   missing_data 五场景加探针 16 项。

## 生态贡献

- **使用说明**：本文件含完整调用步骤（六步运行时入口与 Workflow）、输入输出解释
  （输出契约与三段结构映射）、关键方法（规则库与误报口径）、适用场景（路由表）、
  限制（Limits）、失败处理（拒收路径与异常处置表）和自查方法（验证一节）。
- **依赖与配置**：Python 3.9+ 标准库加 matplotlib/numpy（版本与安装方式见
  Requirements 与 references/encoding-spec.md）；图型经 kind 配置，通道经 encoding
  配置，导出参数经 export 配置——全部声明式，可复用为团队规范。
- **示例（标注为示例）**：examples/ 最小 spec（example-spec.json）、数据
  （example-data.csv）、contract 化输入（spec-contract.json）与实跑产物说明；示意
  输出不冒充正式案例结果。
- **图型案例可复用**：33 条规则每条带 id、severity、basis 与 fix，可直接当作科研
  制图 checklist 人工使用；encoding-spec.md 是可复用的编码规范。
- **bench 回归门**：19 场景独立复跑（python scripts/bench_chart.py），改动引擎后
  必须全过——是他人验证本 Skill 行为的最短路径。
- **样式模板可复用**：色板固定为 Okabe-Ito（色盲安全），默认 svg.fonttype 为 none
  （活字）、300 dpi——三项默认值即为可复用的投稿导出预设。
- **适用范围与不适用**：有数据表的图稿生成与编辑；不负责示意图/机制图/流程图、
  位图数字化读数、统计方法选择与显著性计算（路由表末三行明确拒识）。
- **维护信息**：规则 id 变更须同步本文规则表与 references/audit-rules.md；bench
  全过是合并条件；引擎内注释记录每条规则的历史教训（如 caption n 列优先于行数）。
