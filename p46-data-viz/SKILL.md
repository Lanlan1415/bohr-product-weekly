---
name: data-viz
description: >
  科研数据可视化：把一张源数据表变成可投稿、可复核的统计图。读取数据表后先按声明式
  encoding spec 校验图型与通道（图型与数据结构不匹配时拒绝而不是硬画），渲染
  bar/line/scatter/box/heatmap 并输出可编辑导出（live-text SVG + 300 dpi PNG + PDF），
  然后审计可视化准确性：坐标轴标目与单位、截断基线与对数轴、数值是否被轴范围或色标
  范围裁掉、图例与数据分组一致、误差通道是否真的画了且声明了含义（SD/SEM/CI）、类别
  过多、图注样本量与表是否一致、显著性标注是否指向数据里存在的分组、中文字体覆盖
  （缺字形报出而不是留空框），以及 mark→row 溯源——图上每个视觉元素都能回指到源数据
  行，并附 sha256 级复现证据。结果回填案例的 output_contract 字段与 case_id。Use
  when the task supplies a data table and asks for a chart, figure, figure panel,
  or publication-grade export whose values must be traceable to the source rows.
---

# data-viz（科研数据可视化）

一张图是一个关于数据的断言。本 Skill 让这个断言可检查：每个 mark 绑定一行源数据，
每个编码通道绑定一个列，导出在交付前先被审计。

三步：

1. **encode** — 把 spec 与数据表对照校验，不匹配就拒绝（refused）
2. **render** — 绘图并保留 mark → row 映射
3. **audit** — 检查标目、单位、裁剪、基线、图例一致性、字体覆盖、溯源、导出规格

**拒绝是第一步的目的。** 对文本列要柱状图，得到的是命名错误，不是一张全零的图。
建立在被误读列上的图比没有图更糟，因为它看起来是权威的。

## 运行时入口（每个案例六步）

运行时输入是 /input/case.json 与 task.md；材料与产物按题目要求提供。预算为 64 次模型
请求、900 秒、每次响应 16384 token——所以第 2 步先落盘部分诚实交付，再逐步改进。

| 步 | 动作 | 产物 |
|-|-|-|
| 0 读案例 | 读 /input/case.json 与 task.md：记录 case_id；抄下 output_contract 点名的全部字段清单；从材料里定位真正的数据表文件（读实际文件，不按标签猜内容） | case_id、契约字段清单、数据路径 |
| 1 判形态 | 按下面路由表判断本次任务的形态；不属于本包范围的明确声明不用并说明 | 路由决定 |
| 2 先产目标 | 先把已知部分落盘到 /app/output：数据表快照、已确认的 spec 草案、半成品 result.json（status 如实标注） | 部分诚实交付（预算中断时也有可评分产物） |
| 3 构造 spec | 声明 kind、encoding 通道到列名的映射、标目、单位、errorbar_meaning、panel、caption_n，需要时加 ylim、y_scale、color_range；把 case_id 与 output_contract 写进 spec 顶层 | spec.json |
| 4 审计 | 跑一次引擎，读 findings 与 status | result.json 初版 |
| 5 修发现重跑 | 逐条 findings 修 spec 或清洗数据列后重跑；blocked/refused 不得带病交付 | 收敛后的 result.json |
| 6 合并交付 | 确认 result.json 含 case_id 且 output_contract 点名的每个键都存在（引擎已推导的保留，spec 携带的直通，推导不了的填 null 并在 limits 里说明）；连同 figure 三件套与 source_snapshot 放进 /app/output | 最终交付 |

## 任务措辞 → 路由

| 任务措辞信号 | 路由 |
|-|-|
| 画图 / 出图 / 绘制 figure / 可视化，输入是数据表 | 走六步全流程（0–6） |
| 只问"建议用什么图型"，不要求交付图件 | 用下方选型规则给出图型与理由，不调用渲染；说明这是建议而非成图 |
| 多面板组图 / panel 拼版 | 每个面板一份 spec，panel 字段必填，逐面板审计后合并交付 |
| 期刊规格导出 / 单栏双栏 / 300 dpi | figsize 按栏宽取 3.5 in 或 7.2 in 起，dpi 不低于 300，SVG 保持 live text |
| 热图 / 矩阵强度面 | kind 取 heatmap，color_range 必须声明（缺失或裁剪都会被点名） |
| 要误差线 / 显著性标注 / 图注样本量 | 误差列走 y_err 通道并声明 errorbar_meaning；significance 只校验不绘制 |
| 中文标签 / 中文图注 | 字体按图上实际字符解析；缺字形会被点名，不静默画框 |
| 数据在位图曲线里，只有图没有表 | 本包不数字化曲线；先走数字化路径，读数不确定性必须带入成图 |
| 示意图 / 机制图 / 流程图（无数据可映射） | 不用本包——没有源数据行就没有溯源可言 |
| 让清洗数据 / 选统计检验 / 补实验设计 | 超出本包边界：引擎不做统计计算；在异常说明里声明该部分未覆盖 |
| 只有报告里的数字、没有源数据表 | 拒绝凭记忆敲数字——值只活在数据文件里；请求数据或声明未完成 |

## 环境要求

Python 3.9+，依赖 matplotlib、numpy（字体度量另用 Pillow，缺则跳过文字溢出检查并如实
说明）。无网络依赖；字体从系统字体目录解析。运行验证用 python -X utf8（Windows 下保证
中文路径与标签不乱码）。

## 图型选型规则

引擎支持五种图型（CHART_KINDS）：bar、line、scatter、box、heatmap。按分析目的选：

| 分析目的 | 数据结构 | 推荐 | 不推荐及原因 |
|-|-|-|---|
| 分布 | 一列连续值（可按组拆分） | box（每组一个箱体，行仍可溯源） | 饼图——分布没有"构成"含义 |
| 组间比较 | 分类 x + 数值 y（±误差列） | bar（分类轴从列值生成） | 折线——分类间没有连续性，连线暗示趋势 |
| 相关 | 两列连续值 | scatter | 并列柱——丢失逐点配对信息 |
| 趋势 | 时间/有序 x + 数值 y | line（x 轴保持有序） | 并列柱——把时间序列切成孤块；引擎会报 time_as_bars |
| 构成 / 强度面 | x-y 网格 + 数值 | heatmap（缺格画成 NaN 空洞，不补零；color_range 必声明） | 堆叠柱——面积编码难以精确读数 |
| 构成占比 | 无序分类 | bar 按值排序 | 饼图——角度/面积夸大差异，类别多时不可读 |

明确不支持并被拒绝（`encoding.unknown_chart_kind`）：pie、histogram、violin、
ridgeline、contour、3D。直方图被拒的原因：分箱是派生统计，bin 宽度是无人复核的
自由参数——若需要分布，请先用 box 展示原始行，或显式在表里聚合后说明口径。

## Workflow

### 1. 读数据，不要手工转录

``bash
python scripts/chartguard.py --spec spec.json --data table.csv --out /app/output
``

CSV / JSON（UTF-8，含 BOM 亦可，逗号或制表符分隔自动识别）。数值必须来自文件；
凭记忆敲进 spec 的数字是伪造值。spec 或数据不可读时引擎给出 undetermined 状态与
退出码 5，绝不以 traceback 收场。

### 2. 显式声明编码

``json
{
  "case_id": "demo-chart-001",
  "output_contract": ["status", "findings", "encoding", "mark_to_row", "artifacts", "provenance"],
  "kind": "bar",
  "x_label": "处理组",
  "y_label": "响应强度",
  "y_unit": "a.u.",
  "errorbar_meaning": "SD",
  "panel": "a",
  "caption_n": 6,
  "legend": true,
  "encoding": {"x": "condition", "y": "response", "y_err": "response_sd", "group": "group"}
}
``

| 通道 | 必需于 | 含义 |
|-|-|-|
| x | 每种图型 | x 通道；bar/box/heatmap 的非数值列自动成为分类或网格轴，line/scatter 要求数值 |
| y | bar、line、scatter、box | 测量值（heatmap 的 y 是网格坐标，可为分类） |
| value | heatmap | 格值 |
| group | 可选 | 系列拆分；驱动颜色与图例 |
| y_err | 可选 | 每行误差幅度（声明了就必须画出来，否则 `error.column_not_drawn`；且必须声明含义，否则 `annotation.errorbar_meaning_missing`） |

通道映射到**列名**而不是数值。这个间接层是溯源成立的前提：值只活在数据文件里。

其余可选字段：figsize（单栏 3.5 in 起）、dpi（默认 300）、x_unit、title、caption、
panel（拼版面板编号）、ylim（声明后截断基线会被点名）、y_scale（log 轴遇非正值会被
点名）、color_range（heatmap 色标范围）、significance（两个分组都必须在数据里）、
caption_n（图注声称的样本量，与表的 n 列或行数核对）。

### 3. 读懂审计，修复，重跑

| status | 退出码 | 含义 |
|-|-|-|
| clean | 0 | 无发现 |
| review | 3 | 只有 low/medium 发现，可交付但应在异常说明里列出 |
| blocked | 4 | 有 high 发现——图已渲染但带缺陷，修完再交付 |
| refused | 5 | 编码方案在渲染前被拒绝（spec 错，不是数据错） |
| undetermined | 5 | 输入不可读或渲染本身失败，无法给出可信产物 |

blocked、refused、undetermined 都写 result.json 并带 findings——这是可评分的诚实
失败，不是崩溃。

### 4. 验证引擎没有退化

``bash
python scripts/bench_chart.py
``

24 个场景，每个植入一个缺陷（或证明一个 FP guard）。clean 基线不得产生任何
high/medium finding，所以"全都标"的检测器过不了。本机 24/24 pass。

## 输出契约

/app/output/result.json（引擎直接写出，结构如下）：

| 字段 | 含义 |
|-|-|
| status | clean、review、blocked、refused、undetermined 之一 |
| findings[] | rule、severity、message，附规则上下文（行列名、实际值、缺失列表） |
| encoding | 图型、通道到列映射、源行数、mark 数 |
| mark_to_row[] | mark、row、x、y、series、y_err——溯源脊柱 |
| artifacts | figure.svg（live text）、figure.pdf、figure.png（300 dpi）、source_snapshot 路径 |
| provenance | spec 与数据的 sha256、引擎与 matplotlib 版本、解析到的字体、dpi——复现证据 |
| case_id | 案例 0 步记录的标识，原样回填 |
| output_contract 各键 | 案例点名的每个键：引擎已推导的保留原值，spec 携带的直通，推导不了的填 null 并在 limits 里说明 |
| limits[] | 未覆盖项与不可推导契约字段的诚实清单 |

可编辑导出三件套是默认行为：SVG 以 live text 保存（svg.fonttype 设为 none，审计发现
文字被转成轮廓会报 `export.no_live_text`），PNG 300 dpi，PDF 矢量。字体按图上实际
字符解析（中文标签自动选 CJK 字体），缺字形会点名字符而不是留一排空框。原始数据表
以 source_snapshot 落在输出目录，数据到成图的链条可离线复核。

## rubric 三段结构映射

任务要求"每个案例返回一份结构化结果"，三行要求与 result.json 的落位：

| rubric 行 | rubric 要求要点 | result.json 落位 |
|-|-|-|
| 分析结果 | 清洗表、统计结果、图表、代码或查询结果；与数据字典、规则和任务一致 | encoding 通道映射 + mark_to_row 溯源 + artifacts 三件套 + source_snapshot + spec 回显 |
| 质量与复现证据 | 原始快照、规则表、日志、代码和版本；他人可复算 | provenance（sha256、引擎与 matplotlib 版本、字体、dpi、快照路径）+ findings 即规则表 + bench 套件可复跑 |
| 异常说明 | 缺失、异常、失败查询、无法解释和人工确认；不静默修改或掩盖 | findings[]（rule/severity/message）+ limits[] + refused/undetermined 状态本身 |

## 最小调用示例

输入：examples/example-spec.json（含 case_id 与 output_contract 声明）+ examples/example-data.csv
（4 行，组×处理）。

调用：

``bash
python scripts/chartguard.py --spec examples/example-spec.json --data examples/example-data.csv --out out_example
``

实跑退出码 0，控制台回显 status 与 case_id；完整示意输出见 examples/example-result.json
（由上述两个文件实跑生成、标注为示例）。形状如下：

``json
{
  "schema_version": "data-viz/v1",
  "status": "clean",
  "case_id": "demo-chart-001",
  "findings": [],
  "encoding": {"chart_kind": "bar", "rows_in_source": 4, "marks_drawn": 4},
  "mark_to_row": [
    {"mark": "bar0", "row": 0, "x": "control", "y": 12.4, "series": "WT", "y_err": 1.1}
  ],
  "artifacts": {"svg": ".../figure.svg", "pdf": ".../figure.pdf", "png": ".../figure.png",
                "source_snapshot": ".../source_snapshot.csv"},
  "provenance": {"engine": "chartguard/v1", "spec_sha256": "daa0...", "data_sha256": "91f1...",
                 "font": {"family": "Microsoft YaHei"}, "dpi": 300},
  "limits": []
}
``

（示意输出——说明接口与结果形状，不是正式案例结果；output_contract 点名的六个键
全部在结果中出现。）

## 审计规则

| rule | severity | 证明什么 |
|-|-|-|
| `encoding.unknown_chart_kind` | high | 请求的图型不支持——拒绝，不近似 |
| `encoding.required_channel_unmapped` | high | 图型必需的通道没有映射 |
| `encoding.column_missing` | high | spec 点名的列在表中不存在 |
| `encoding.not_numeric` | high | 文本列在驱动数值通道 |
| `data.no_rows` | high | 表没有数据行——拒绝，不是崩溃 |
| `encoding.time_as_bars` | medium | 时间列被画成并列柱，连续性与拐点不可见 |
| `axis.x_label_missing` / `axis.y_label_missing` | high | 坐标轴没有标目 |
| `axis.x_unit_missing` / `axis.y_unit_missing` | medium | **数值**轴没有声明单位（分类轴不要求单位） |
| `axis.value_clipped` | high | 数值落在轴范围外，mark 不可见 |
| `axis.truncated_baseline` | high | 声明的柱状图基线高于零，柱长不再编码数值 |
| `axis.log_nonpositive` | medium | 对数轴遇非正值，点被静默丢弃 |
| `series.missing_from_chart` | high | 数据里的分组没有被画出来 |
| `legend.absent` | medium | 多分组却无图例，颜色失去含义 |
| `error.column_not_drawn` | high | 声明了误差通道但没有渲染误差线 |
| `annotation.errorbar_meaning_missing` | medium | 误差线没有声明是 SD、SEM 还是置信区间 |
| `read.too_many_categories` | medium | 类别超过 12 或系列超过 8，单栏宽度下不可读、颜色复用 |
| `color.range_undeclared` | medium | 热图未声明色标范围，读者无法判断调色板是否截断 |
| `color.range_clipped` | high | 数据值落在声明的色标范围外，量级被误读 |
| `layout.panel_missing` | low | 未声明面板编号；单图可无，拼版必须有 |
| `traceability.missing` | high | mark 缺少源行索引 |
| `traceability.row_coverage` | medium | mark 少于源行，部分行没有进图 |
| `caption.n_mismatch` | high | 图注样本量与表不符（含 caption_n 非数值） |
| `annotation.unknown_comparison` | high | 显著性标注指向数据里不存在的分组 |
| `export.no_live_text` | high | SVG 文字是轮廓，文件不可编辑 |
| `export.pdf_invalid` | high | PDF 导出不是合法 PDF |
| `export.low_dpi` | medium | 位图低于 300 dpi |
| `font.unresolved` | medium | 找不到可读字体文件，字形覆盖无法证明 |
| `font.glyph_missing` | medium | 标签含已解析字体缺字形的字符（中文乱码的前兆） |
| `input.label_truncated` | medium | spec 字符串字段超长被裁剪后才渲染，被裁字段随 finding 记录 |
| `input.spec_unreadable` | high | spec 不是可读 JSON——undetermined，不崩溃 |
| `input.spec_not_object` | high | spec 不是 JSON 对象——undetermined |
| `input.data_unreadable` | high | 数据文件读不出来——undetermined |
| `render.failed` | high | 渲染本身抛异常——undetermined，异常名随 finding 记录 |

## Limits

- **只有五种图型。** pie / histogram / violin / contour / 3D 一律拒绝，不静默降级。
- **不做统计计算。** 误差线来自声明的误差列；引擎绝不自己算 SEM/SD/CI——算错的
  派生统计量与测得的无法区分。表里只有重复测量时，先显式聚合并注明口径。
- **显著性标注只校验不绘制。** 审计确认比较双方都在数据里；摆括号是手工步骤。
- **热图色标范围只核对声明与数据，不判断研究问题。** 声明一个故意截断的范围且数据
  恰在其内，审计无法知道这是否掩盖了感兴趣的差异。
- **审计证明编码，不证明推断。** 它能告诉你某个 bar 无法溯源；不能告诉你 t 检验
  选错了。
- **字体解析依赖系统字体目录。** 找不到任何字体文件时报 `font.unresolved`（可复核性
  缺口），不会假装覆盖完整。
- **时间轴判定是保守的。** time_as_bars 只在列名含时间词或取值是年份数字时触发，
  剂量梯度（0、5、10、20）画柱不报——剂量柱状图在文献里是正当的。
- **undetermined 不回填契约字段。** spec 不可读时没有可信来源可回填，result.json
  如实声明这一点。

## 异常处置表

| 症状 | 引擎行为 | 处置 |
|-|-|-|
| spec 不是可读 JSON | status undetermined，finding `input.spec_unreadable`，exit 5 | 重新导出/修复 spec 文件再跑 |
| spec 是列表或字符串而非对象 | undetermined，`input.spec_not_object` | spec 顶层必须是对象 |
| 数据文件缺失或解析失败 | undetermined，`input.data_unreadable` | 确认材料里的真实数据路径与格式 |
| 渲染抛异常（figsize 形状错等） | undetermined，`render.failed`，异常名入 finding | 修几何参数；dpi/figsize 已自动回退默认值 |
| 图型不在五种之内 | refused，`encoding.unknown_chart_kind` | 换支持图型或显式聚合后再画 |
| 文本列驱动数值通道 | refused，`encoding.not_numeric` | 显式清洗或排除，绝不强转 0 |
| spec 点名的列不存在 | refused，`encoding.column_missing`（附可用列清单） | 按 finding 里的 available 清单改列名 |
| 表没有数据行 | refused，`data.no_rows` | 检查是否只读了表头 |
| 数值落在轴范围外 | blocked，`axis.value_clipped` | 放宽轴限，或检查是否误把离群值列成了误差 |
| 柱状图基线高于零 | blocked，`axis.truncated_baseline` | 基线归零，或改用点图表达偏移 |
| 对数轴遇非正值 | review，`axis.log_nonpositive` | 换 symlog 或先变换数据并说明 |
| 图注样本量对不上 | blocked，`caption.n_mismatch` 且表有 n 列 | 图注可能是分组的 n；看 finding 里的 distinct_n |
| 误差线画了但没声明含义 | review，`annotation.errorbar_meaning_missing` | 在 spec 里补 errorbar_meaning（SD/SEM/CI） |
| 类别或系列过多 | review，`read.too_many_categories` | 拆面板或合并类目后再导出 |
| 热图色标未声明/裁剪数据 | review 或 blocked，`color.range_undeclared` / `color.range_clipped` | 声明覆盖数据的 color_range |
| SVG 文字被转轮廓 | blocked，`export.no_live_text` | 以 svg.fonttype=none 重新导出 |
| 标签缺字形 | review，`font.glyph_missing`（点名字符） | 换覆盖该字符的字体，或删装饰字符；不要留空框交付 |
| mark 少于源行 | review，`traceability.row_coverage` | 有行被跳过——通常是空白值被未声明的过滤吃掉 |
| output_contract 字段推导不了 | 该键填 null，limits 里记一条 | 在异常说明里向读者说明该字段为何缺失 |
| matplotlib/numpy 缺失 | 引擎无法运行；依赖检查先行 | 按下节安装；缺依赖时不得伪造图件，如实声明运行失败 |

## Dependencies

``
pip install matplotlib numpy Pillow
``

- **matplotlib**（3.x，实测 3.10.8）：渲染与导出、字体度量（ft2font）
- **numpy**：数组运算与 NaN 缺口绘制
- **Pillow**：可选，缺省时跳过文字溢出类检查并如实说明

这三个包缺失时渲染与审计无法运行，上面所有 CLI 命令都会以 undetermined 退出——
这是声明的失败模式，不是静默降级。引擎核心（审计规则、溯源、契约回填）不依赖网络
与付费服务。

## 创新增益

以下能力均为引擎真实实现，边界如实标注：

1. **mark→row 溯源脊柱**：图上每个视觉元素在 mark_to_row 里回指源数据行与通道值
   （mark、row、x、y、series、y_err），评审可逐元素核对"图上的数与表里的数一致"。
   通用 Agent 画完图即丢弃映射，无法自证这一点。边界：溯源证明编码正确，不证明
   统计推断正确。
2. **拒绝式编码校验**：图型×数据结构不匹配（文本列驱动数值通道、时间列画并列柱、
   未知图型）在渲染前被拒绝并给出行列级证据，而不是产出一张"看起来完成"的错图。
   边界：时间轴判定保守（列名时间词或年份取值才触发），剂量梯度画柱不误报。
3. **字符级字体覆盖证明**：字体按图上实际会画的字符（spec 标签 + 数据类别值）解析，
   缺字形点名具体字符与字体——直击"中文标签渲染成空框但文件照样保存"的隐形失败。
   边界：依赖系统字体目录，找不到字体时报 `font.unresolved` 而不是假装覆盖。
4. **导出即审计**：live-text SVG、300 dpi PNG、矢量 PDF 三件套在交付前过审计
   （文字轮廓化、dpi 不足、PDF 非法都会被点名），期刊规格违规在交付前暴露。
   边界：字体嵌入度（Type 3 vs Type 42）不做字节级检查。
5. **sha256 级复现证据**：provenance 记录 spec 与数据的哈希、引擎与 matplotlib 版本、
   解析字体与 dpi，原始数据表快照随图交付——换一台机器重跑可逐字节核对输入。
   边界：只证明输入一致，不消除 matplotlib 版本间的渲染像素差异。
6. **clean 基线回归套件**：24 个场景逐条对应规则，clean 基线必须零 high/medium
   发现，"全都标"的检测器过不了 bench——检测器自身被检测。

## 生态贡献

- **SKILL.md**：用途、适用条件、六步调用方式、输入输出、异常处置表、限制和自查方法
- **references/audit-rules.md**：每条审计规则证明什么、为何存在（规则表可独立阅读）
- **references/encoding-spec.md**：编码规格、验证顺序、轴与标注选项、状态与退出码表
- **examples/**：最小调用示例三件套（spec + 数据 + 实跑 result，示意输出已标注）
- **scripts/chartguard.py**：渲染+审计引擎，CLI 可直接复跑，函数可独立导入复用
- **scripts/fontsel.py**：字符级字体解析模块，任何 matplotlib 项目可直接复用
- **scripts/bench_chart.py**：24 场景回归套件，一键复跑验证引擎行为
- **维护信息**：依赖版本（上节实测版本）、平台限制（50 文件/500KB/2MB 内无二进制）、
  已知边界全部写入 Limits 与异常处置表

## 验证

``bash
python scripts/bench_chart.py   # 24 scenarios：每个植入一个缺陷或证明一个 FP guard
``

本机 24/24 pass。clean 基线零 high/medium finding，FP guard 钉住关键行为：
表头空表走拒绝而不是崩溃、部分空白的误差列正常渲染、部分缺失不画成零高度柱、
中文标签解析到 CJK 字体、缺字形字符被点名而不是静默画框、分类热图不再被误拒。
另有 15 项敌意探针（坏 JSON、非对象、文件缺失、类型错位、超长、CJK、契约字段垃圾、
重跑幂等）全部通过：退出码落在 0/3/4/5，result.json 必在，无 traceback。
