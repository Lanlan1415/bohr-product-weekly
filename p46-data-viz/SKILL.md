---
name: data-viz
description: >
  科研数据可视化：从真实 CSV/TSV/JSON 数据表生成可复核、可编辑的科研图，而不只是给
  绘图建议。按字段类型与分析目的选择 bar/line/scatter/box/heatmap/histogram，显式记录
  field/type/channel 编码，输出标题、轴和单位、图例、误差定义、样本量或源行数、色盲友好
  且灰度可辨的系列样式、live-text SVG、300 dpi PNG、PDF、caption、完整 mark_to_row、
  resolved_spec 与输入哈希。画后回读实际图元坐标和值，检查重叠/错值、裁切、截断基线、
  双轴、文字越界和导出完整性。用于数据表绘图、分布/比较/趋势/相关/矩阵图及发表级导出。
  不用于无源数据的示意图、机制图、图像数字化或统计方法选择。
---

# data-viz（科研数据可视化）

一张图是关于数据的断言。本 Skill 的交付不是一句“建议画柱图”，而是**实际图件 + 图注 +
可复跑 CLI + 每个图元到源行的映射 + 画后审计**。不把肉眼未检查的布局说成已人工验收；
程序审计和实际打开图像（若执行者确实打开）分别记录。

## 运行时入口：读 case，尽早落盘，最终交付

平台输入是 `/input/case.json` 与 `task.md`。材料路径以实际文件为准，不按文件名猜内容。
在 `/app/work` 写 spec，在 `/app/output` 交付。预算内先保存诚实的部分结果，再改进。

| 步 | 必做动作 | 产物 |
|-|-|-|
| 0 读案例 | 记录 `case_id`，逐项抄下原始 `output_contract` 字段；读 task 与数据字典 | 契约清单、数据路径、问题目的 |
| 1 识别数据 | 读真实表头和行，确认连续/分类/时间/编码字段、缺失、重复、单位及样本口径 | 字段类型与分析粒度 |
| 2 先保存 | 把已知信息整理为 resolved spec 草案；若依赖或数据缺失，先写带 limits 的结果 | 部分结果，不伪造图件 |
| 3 选图 | 用自动模式产出可审 spec，或按下方决策表手工指定；不要用饼图、3D 或双轴掩盖比较 | kind + encoding + selection reason |
| 4 实跑 | 运行 CLI，得到真实 SVG/PNG/PDF、caption、mapping 和 result | 初版图件与审计 |
| 5 修并重跑 | 处理 high/medium findings；无法修的保留状态与限制，不把 review/blocked 改成 clean | 收敛结果或结构化失败 |
| 6 核对交付 | 检查文件非空、`case_id` 原样存在、原始契约每键齐全；需要时实际打开 PNG，另存说明 | `/app/output/result.json` 与全部产物 |

不要把本说明末尾的 Verification 当成正式案例的强制前置步骤；正式工作流在交付结束。

## CLI：两种真实出图方式

以下假设 Skill 安装在 `/skills/weekly-skill`；其他环境把前缀换为本包实际根目录。

### A. 显式编码（需要精确控制时）

```bash
python -X utf8 /skills/weekly-skill/scripts/chartguard.py \
  --spec /app/work/spec.json \
  --data /input/table.csv \
  --case /input/case.json \
  --task /input/task.md \
  --out /app/output
```

`--case` 只补充 spec 中尚无的 `case_id` 和 `output_contract`，不会把查询结果或案例正文
倾倒进 spec。`--task` 可选；显式模式的分析目的由 spec 记录。

最小 spec：

```json
{
  "kind": "bar",
  "title": "Treatment response by genotype",
  "caption": "Bars show source-row values; error bars are SD.",
  "x_label": "Treatment",
  "y_label": "Response",
  "y_unit": "a.u.",
  "errorbar_meaning": "SD",
  "caption_n": 6,
  "panel": "a",
  "legend": true,
  "encoding": {"x": "condition", "y": "response", "y_err": "response_sd", "group": "group"},
  "export": {"width_mm": 89, "tolerance_mm": 2}
}
```

通道映射的是**列名，不是手抄数值**。SD/SEM/CI 必须来自明确的源误差列与
`errorbar_meaning`；引擎不会从原始观察擅自计算一种误差再冒充题目要求的口径。

### B. 问题感知自动选型（仍会真实渲染）

```bash
python -X utf8 /skills/weekly-skill/scripts/chartguard.py \
  --auto --data /input/table.csv \
  --question "Compare response distributions by treatment" \
  --units '{"response":"a.u."}' \
  --case /input/case.json --out /app/output
```

可用 `--kind`、`--x`、`--y`、`--group`、`--x-err`、`--y-err` 覆盖推断；`--task` 可代替 `--question`。
自动分支先写 `resolved_spec.json`，再经过与手工 spec 完全相同的校验、渲染和审计。
字段类型和选择理由不是文档自述，而会进入 `encoding` 的 `field_types` 与 `selection`。
单位只来自数据字典/用户声明，未知时不编造。

## 图型与编码决策表

| 数据类型 + 问题 | 实际图型 | 关键约束 |
|-|-|-|
| 时间/有序字段 + 数值，问趋势 | line | x 保持数值顺序；每组独立线型、点形与颜色 |
| 两个连续字段，问相关/配对 | scatter | 不用并列柱丢失配对；缺失坐标不强排到行号 |
| 分类 + 每类一个数值，问比较 | bar | 从 0 起；同一 x+group 重复会拒绝，先显式聚合 |
| 分类 + 重复观察，问分布/组间差异 | box + 原始点 | 不只画均值；x×group 分组箱体和每个观察可回溯 |
| 一个连续字段，问分布 | histogram | 默认 10 bins，可声明 `bins`、`bin_edges`；完整边界、计数与成员行入 `aggregates` |
| 两个网格字段 + 数值，问强度面 | heatmap | 缺格为 NaN；声明 `color_range` 与 `value_unit`，重复格拒绝 |
| 多系列任何支持图 | Okabe-Ito + 冗余编码 | 颜色之外还有 hatch/dash/marker 和文字图例 |
| 高基数或多指标不同量纲 | 分面/显式标准化后重跑 | 不使用双 y 轴；>12 类别或 >8 系列给可读性 finding |

Vega-Lite 的 field、type、channel 明确类型模型、`detail` 分组和 `description` 可访问性思想
已落实为 `field_types`、encoding、源行映射及 SVG `<title>/<desc>`；seaborn 的集中数据映射和
逐通道 scale 设置用于统一推断与审计。参考实现来源见文末，运行时无需访问这些链接。

## spec 主要选项

| 字段 | 用途 |
|-|-|
| `kind`, `encoding` | 上述图型与 x/y/value/group/x_err/y_err 列映射 |
| `field_types` | 自动模式生成的 nominal/ordinal/quantitative/temporal 证据，也可显式提供 |
| `title`, `caption`, `x_label`, `y_label`, `value_label` | 真正画入图件的标题、图注、轴和色标文字 |
| `x_unit`, `y_unit`, `value_unit` | 真正附加到对应轴/色标，不把分类轴强行加单位 |
| `caption_n` | 声明样本量；与源行或 n 列对账。未声明时只写 source rows，不把行数冒充独立 n |
| `errorbar_meaning` | SD/SEM/CI/range 等；进入图注和 SVG description |
| `ylim`, `y_scale` | 实际应用后检查裁剪、非零柱基线和对数非正值 |
| `bins`、`bin_edges` | histogram 分箱；不隐藏派生变换 |
| `color_range` | heatmap 色标范围；数据越界为 high |
| `figsize`、`dpi`、`export` 的 `width_mm` | 画布、默认 300 dpi、栏宽约束和画后实测 |
| `accessibility_description` | 覆盖自动生成的 SVG 图意描述 |
| `case_id`, `output_contract` | 案例标识与原样契约，不省略失败路径可读部分 |

## 画后审计：不是“保存成功就算对”

- **实际几何回读**：bar 中心与高度、scatter/line/box 原始点、heatmap 格值与源行比对。
  分组柱使用共享类别顺序与 dodge 位置，不再叠在同一坐标。
- **数据完整性**：必需数值缺失留空并给 `data.missing_numeric`；不把 NULL/空值改成 0。
  完全重复源行保留并提示；bar/heatmap 的重复键会重叠，直接拒绝而非静默丢行。
- **图面语义**：标题、轴和单位、图例—系列、误差定义、样本量、色标、面板编号均可复核。
- **防误导**：裁切、截断柱基线、对数非正值、未声明双 y 轴、类别/系列过载均给规则。
- **文字与导出**：动态图注换行，再读取渲染后的文字 bounding box；越界为
  `layout.text_overflow`。检查 live text、SVG 可访问性节点、PNG 文件及 pHYs dpi、PDF 头、
  文件最小大小、实际画布栏宽和字体缺字。

## 输出契约与实际文件

`/app/output/result.json` 的核心字段：

| 字段 | 内容 |
|-|-|
| `status`, `findings`, `severity_counts` | clean/review/blocked/refused/undetermined、规则与级别 |
| `case_id` | 原样案例 ID；可读 spec/case 的失败路径同样回填 |
| `encoding` | 图型、通道、field_types、auto selection、源行数、图元数、分组布局 |
| `mark_to_row` | 全量源行索引、通道值、系列、误差及实际 rendered 几何，不截到前 200 行 |
| `aggregates` | histogram 边界、计数和成员行；无派生变换时为空 |
| `artifacts` | svg/png/pdf/caption/mark_to_row/resolved_spec/source_snapshot 的真实路径 |
| `provenance` | resolved spec 与源表 sha256、引擎/matplotlib/字体/dpi、源快照 |
| `accessibility`, `layout` | 调色板与冗余编码、SVG description、文字越界结果 |
| `limits` | 未覆盖语义、契约不可推导项、科学解释边界；契约缺键填 null 且逐键说明 |
| 原始 `output_contract` 其他键 | 引擎已有结果保留；spec 给定值直通；不可推导填 null + limits |

成功渲染会实际生成：`figure.svg`、`figure.png`、`figure.pdf`、`caption.txt`、
`mark_to_row.json`、`resolved_spec.json`、`source_snapshot.<suffix>` 和 `result.json`。
SVG 嵌入 `role="img"`、`<title>` 与 `<desc>`；这不等于声称完成人类视觉检查。

### 状态与退出码

| status | exit | 何时使用 |
|-|-|-|
| clean | 0 | 没有 finding；自动与显式 clean 实例都必须真的出图 |
| review | 3 | 仅 low/medium，例如缺单位、数值缺失、低样本或非致命可读性问题 |
| blocked | 4 | 已渲染但有 high，例如几何错值、裁剪、基线误导或文字越界 |
| refused | 5 | 渲染前拒绝：未知图型、列错误、重复 bar/heatmap 键、双轴等 |
| undetermined | 5 | 输入不可读、依赖不可用或渲染失败；能力不可确定，不伪造成功 |

所有可预见的 spec/data/render 错误都写结构化 `result.json`，不输出 traceback；CLI 参数本身
缺失由 argparse 以用法错误 2 报告。blocked/refused/undetermined 不是 clean，也不得在文字中
改称成功。

## 限制与不适用情况

- 支持六种图型；pie、3D、contour、violin 和任意未知图型不会被静默近似。
- **显著性比较只校验组名，不画括号**；若用了 `significance`，该限制必入 limits。
- 不从原始重复观察自动选择 SD/SEM/CI，不做统计检验，不验证研究假设。
- heatmap 画给定网格，不自动计算相关系数；先显式生成带行列/value 的相关矩阵表。
- 多量纲指标不使用双轴，需分面或先声明标准化；复杂拼版逐面板运行。
- 字符串展示字段超过 240 字符会截短并报 `input.label_truncated`，不能悄悄当成原文。
- 字体依赖系统字体目录；缺字或不可解析会报告。像素效果可因 matplotlib/字体版本不同。
- 自动选型是保守启发式，必须结合 task 和数据字典核对；它不会推断因果或独立实验单位。

## 异常处置

| 症状 | 结构与退出 | 正确处理 |
|-|-|-|
| JSON 不可读/非对象 | undetermined + `input.spec_unreadable/spec_not_object`, 5 | 修文件；若无 --case 可回显，真实不可读部分保持 unknown |
| 数据缺失/格式错/重复表头 | undetermined + `input.data_unreadable`, 5 | 从真实材料重新导出，不手工补数字 |
| matplotlib/numpy 不可用 | undetermined + `dependency.unavailable`, 5 | 在 scientific Python 环境运行，不生成空图充数 |
| 文本数值列/缺列/空表/未知图型 | refused + 对应 encoding/data 规则, 5 | 修映射或先明确清洗/聚合 |
| 同 x+group 重复 bar/heatmap 格 | refused + `data.duplicate_marks`, 5 | 显式聚合，或改 box/scatter 展示观察 |
| 双 y 轴 | refused + `encoding.dual_axis_unsupported`, 5 | 分面或声明标准化，不换隐蔽名次 |
| 数值缺失 | review + `data.missing_numeric`, 3 | 保持缺失与 limits，不填 0；必要时说明排除口径 |
| 画后几何不符/文本越界 | blocked + `encoding.drawn_value_mismatch/layout.text_overflow`, 4 | 修渲染与布局，不能只编辑 JSON |
| 契约字段不可推导 | 键为 null + limits | 不硬编码假值；根据真实产物补齐可补字段 |

## 完整 finding 规则索引

以下均为引擎实际会写出的 id；测试自检字符串不属于正式 finding。

- Encoding：`encoding.unknown_chart_kind`、`encoding.required_channel_unmapped`、
  `encoding.column_missing`、`encoding.not_numeric`、`encoding.unsupported_channel`、
  `encoding.unsupported_channel_for_kind`、`encoding.dual_axis_unsupported`、
  `encoding.time_as_bars`、`encoding.drawn_value_mismatch`、`input.encoding_not_object`。
- Data：`data.no_rows`、`data.duplicate_marks`、`data.duplicate_rows`、
  `data.missing_numeric`、`data.small_sample`、`traceability.missing`、`traceability.row_coverage`。
- Axis/readability：`axis.x_label_missing`、`axis.y_label_missing`、`axis.x_unit_missing`、
  `axis.y_unit_missing`、`axis.value_clipped`、`axis.truncated_baseline`、`axis.log_nonpositive`、
  `read.too_many_categories`、`layout.panel_missing`、`layout.text_overflow`。
- Annotation/series：`annotation.title_missing`、`annotation.errorbar_meaning_missing`、
  `annotation.unknown_comparison`、`caption.n_mismatch`、`error.column_not_drawn`、
  `legend.absent`、`legend.series_mismatch`、`series.missing_from_chart`。
- Colour：`color.range_clipped`、`color.range_invalid`、`color.range_undeclared`、`color.unit_missing`。
- Export/font：`export.accessibility_description_missing`、`export.empty_artifact`、`export.low_dpi`、
  `export.no_live_text`、`export.pdf_invalid`、`export.png_dpi_mismatch`、
  `export.width_invalid`、`export.width_out_of_band`、`font.glyph_missing`、`font.unresolved`。
- Input/runtime：`input.spec_unreadable`、`input.spec_not_object`、`input.data_unreadable`、
  `input.request_invalid`、`input.label_truncated`、`dependency.unavailable`、`render.failed`、`runtime.failed`。

## Requirements

Python 3.10+，`matplotlib` 3.x、`numpy`；字体度量使用 matplotlib `ft2font`，系统需有可用
字体。无网络、付费服务、 seaborn/Vega-Lite/SQLGlot 运行时依赖。Linux/Windows 使用
`python -X utf8`。科学运行环境缺依赖时是明确的 undetermined，不是可交付图件。

## 最小调用示例

`examples/example-data.csv`（4 行）与 `examples/example-spec.json` 是本包自建演示，不是官方
案例。运行本说明 A 命令即可复跑；`examples/example-result.json` 来自真实本地运行，仅规格化
了输出路径并加 `example_note`，不是预写的官方答案。几何测试还确认示例四根柱中心互不相同。

## 参考机制落地

- [Vega-Lite encoding 文档](https://github.com/vega/vega-lite/blob/main/site/docs/encoding.md)：落地 field、type、channel、分组、位置/
  误差通道和 SVG description，而非只附链接。
- [seaborn Plotter 实现](https://github.com/mwaskom/seaborn/blob/master/seaborn/_core/plot.py)：落地集中变量映射、逐通道 scale 与编译后 plotter
  审计思想；本包不引出 seaborn 依赖。
- 本地高分图表包的几何回读：从 ax artist 读回实际数值并与源行对账，解决“mapping 写对但画错”。

## Verification（作者自查，非运行时必需步骤）

```bash
python -X utf8 /skills/weekly-skill/scripts/bench_chart.py
```

当前 29/29 场景通过。包含 clean baseline、负面规则、重复/缺失/双轴、实际几何、图注语义、
SVG 可访问性、直方图计数、文字越界、错误退出码与 PNG/PDF/SVG 非空检查。测试图片全部写入
系统临时目录，不把二进制测试产物打进 Skill。正式案例交付仍以真实 case 的运行结果为准。
