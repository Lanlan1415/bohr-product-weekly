---
name: figure-parse
description: >
  Recover scientific figures into auditable structures rather than prose guesses.
  Calibrates linear/log axes, keeps units and explicit legend bindings, digitises
  coloured curves and solid bars with per-reading raster uncertainty intervals,
  ingests every original table, cross-checks explicitly anchored caption/body
  numeric claims, and refuses unreadable calibration without inventing values.
  Use for paper raster charts, axes/ticks, series values, error-bar candidates,
  figure/table evidence and chart-to-CSV tasks. Do not use for PDF full-text
  parsing, exact vector extraction, or uncalibrated micrograph interpretation.
---

# 科研图表解析：图表数据恢复 + 证据边界

正式挑战：阅读02｜科研图表解析（`challenge-f35e4ca5`）。

目标是把**给定的一张原图和全部原表**变成可复核结果。图像估计与原文表格严格分流：原表是原始数字，不再“从像素复原”；图像读数则一律标记为估计，不冒充原始精确值。

## 1. 必守规则

1. **不猜刻度和单位。** 像素位置由脚本测量；刻度值、轴名、单位由 Agent 从原图/OCR读取后显式写入 enriched case。没有足够标定就只给 `axis_fraction` 和 `partial`。
2. **估计不等于精确。** 每个标定点都有 `value_status=estimated_from_raster_not_exact`。`reading_intervals` 是栅格读取区间，**不是实验误差、标准差或 95% 置信区间**。不要只引用中心值而隐去区间。
3. **图例不靠顺序猜。** 只有声明的 `series_index`、`hue_bin` 或明确许可的单系列单图例条件才绑定名称。无法绑定时 `series_label=null`。
4. **误差线和显著性只是候选。** `error_bar_candidates` / `marker_candidates` 必须在原图上人工确认；不能把候选竖线直接写成 SD/SEM，也不能把星号候选直接写成显著结论。
5. **不替作者解释冲突。** 题注/正文数值通过 `text_claims` 与具体点绑定后核验。`inconsistent` 表示需要回查，不表示 Agent 可以挑一个数改掉；单位不一致不静默换算。
6. **双轴、比例尺、子图分别登记。** 当前只数字化左 y 轴。第二 y 轴放入 `other_axes`；显微图没有轴标定就不走曲线数字恢复，尺度尺信息放入 `scale_bars`，不能声称已经测出真实尺寸。

## 2. 实际运行流程

所有命令以安装后的 `/skills/weekly-skill` 为根，使用绝对路径。先尽早运行并保存一个诚实的结果，再补充图例或语境。

### 第 0 步：读权威输入

读取 `/input/case.json`、`task.md` 和实际文件。保留 `case_id` 与 `output_contract` 的**全字段**。材料修订要求每例处理实际给出的 1 张原图片与全部原表；其他只出现图注而未给像素的图必须列为缺口，不能“补齐”。

```bash
mkdir -p /app/work /app/output
cp -a /input/. /app/work/case/
python /skills/weekly-skill/scripts/figparse.py calibrate \
  --image /app/work/case/<实际图文件> --out /app/work/calibration.json
```

`calibrate` 只返回面板、框和 tick 像素位置。成功=0，部分=3，无法读取=5；指定 `--out` 时总会留下结构化报告。

### 第 1 步：在副本中补齐读取声明

编辑 `/app/work/case/case.json`，不修改 `/input`。下面是字段示意而非正式案例答案：

```json
{
  "case_id": "EXAMPLE-NOT-A-CASE",
  "images": [{
    "path": "figure.png",
    "x_tick_values": [0, 2, 4, 6, 8, 10],
    "y_tick_values": [100, 80, 60, 40, 20, 0],
    "x_unit": "time (s)", "y_unit": "potential (mV)",
    "x_scale": "linear", "y_scale": "auto",
    "figure_title": "原图标题或 null",
    "panel_label": "a",
    "caption": "原图题注原文",
    "caption_locator": "paper.pdf#page=4#figure=2a",
    "legend_entries": [
      {"series_index": 0, "label": "treatment", "locator": "figure:legend"}
    ],
    "other_axes": [{"name": "right y", "unit": "V", "digitised": false}],
    "scale_bars": []
  }],
  "tables": [{"path": "table1.csv", "locator": "Table S1"}],
  "text_claims": [{
    "claim_id": "body-result-1",
    "statement": "正文中的原数值陈述",
    "value": 42.0, "unit": "potential (mV)",
    "source_locator": "paper.pdf#page=5#paragraph=2",
    "image": "figure.png", "panel_id": "p1", "series_index": 0,
    "point_index": 20, "field": "y", "tolerance": 0
  }],
  "output_contract": {"case_id": "echo", "readings": "required", "answer": "required"}
}
```

- x 刻度值按左→右，y 按上→下。看不清的刻度填 `null`，不造数。正常 y 轴的拟合斜率通常为负；真实倒置轴必须设 `y_axis_inverted:true`。
- `x_scale` 与 `y_scale` 为 `linear`、`log` 或 `auto`。`auto` 同时拟合线性/对数，选择像素残差较小者；残差超过 2 px 即拒绝。
- `point_index` 是脚本 thinning 后的索引，并非论文实验序号。先跑一次，再从 `readings[]` 选与正文对应的实际点建立 claim；没有可对应的点就不要创建 `text_claims`。
- claim 只判断**数值及单位是否与链接区间相容**，不证明因果、统计显著性或整句语义等效。十九章图注等未给像素的内容不得建立伪读数链接。

### 第 2 步：一次完成图和全部原表

```bash
python /skills/weekly-skill/scripts/figparse.py run \
  --case /app/work/case/case.json --out /app/output
```

退出码：`0=success`、`3=partial`、`5=undetermined`。部分/拒绝不被包装成成功；脚本在三种路径均写 `result.json`，不会以 traceback 代替结果。同一路径重复运行原子覆盖当前结果，不追加重复表格。

产物：
- `result.json`：主结构化结果；
- `digitized.csv`：行级 x/y 中心估计、下界、上界、单位、图例与像素来源（至少一组标定点时生成）；
- 若需单独重读一个原表，也可运行 `python /skills/weekly-skill/scripts/tables.py --case /app/work/case/case.json --out /app/output <表格路径>`，但完整 case 已由上一步自动读表。

### 第 3 步：按题面交付而非只交脚本日志

`result.json` 已回填 `case_id` 和 output_contract 全部字段：引擎可推导的字段由引擎填写，case 自带的同名字段原样直通，无法推导者为 `null` 并进入 `limits[]`。Agent 必须用真实 recovery 结果补齐题目要求的答案/解释；不能为了补空字段编造。

| 评分要求 | 本 Skill 的真实产物 |
|-|-|
| 阅读/解析结果 | `panels[]`、`figure_metadata[]`、`readings[]`、`digitized.csv`、原表 `tables[]` |
| 证据与边界 | tick pairs、panel-local pixel、frame/panel origin、`sources[]`、claim locator、reading interval、`uncertainty[]`、`limits[]` |
| 运行状态 | `case_id`、success/partial/undetermined、结构化 `refusal`、退出码 0/3/5 |

## 3. 输出字段与精度口径

| 字段 | 含义 |
|-|-|
| `figure_metadata[]` | 标题、题注及其 locator、子图标签、x/y scale+unit+ticks、图例状态、其他轴和尺度尺 |
| `panels[].calibration.x/y` | `source`、`scale`、`slope`、`intercept`、`rms_px`、`tick_pairs`、`unit`；frame-edge 拟合无残差，带 caveat |
| `panels[].series[]` | 曲线或柱、index、显式 `series_label`、`legend_binding`、外观 hue、原始 x/y 数组 |
| `series[].reading_intervals[]` | 每点 x/y（或柱顶）的 `estimate`、`lower`、`upper`、`pixel_center`、`pixel_half_width` |
| `series[].value_status` | calibrated 时为 raster estimate；uncalibrated 时只允许 axis fraction |
| `readings[]` / `digitized.csv` | 以图/面板/系列/点定位的平铺数据，含上下界与单位 |
| `series[].error_bar_candidates` | 竖线候选；`annotations.marker_candidates` 是待确认 glyph，不是实验结论 |
| `tables[]` | 路径、shape、列类型、verbatim text 或显式数值列、非数值单元索引、单位提示 |
| `claim_alignment[]` | `consistent`、`inconsistent`、`unresolved`、claim/reading 双端定位、比较规则与原因 |
| `uncertainty[]` / `limits[]` | 估计性质、缺失像素、不可标定、未读第二轴、表格失败和语境冲突等 |

区间算法：x 取像素量化及 tick RMS；y 再叠加 stroke 半宽。frame-limit 标定没有残差，采用明确声明的 2 px 基础量。把区间两侧像素分别送入线性或 log 映射，故 log 区间天然不对称。它覆盖一部分**读数不精确性**，不覆盖系统性错轴、错误 OCR、曲线遮挡或科学实验误差。`y_uncertainty` 保留旧的 stroke-only 估算用于兼容；正式引用优先使用新的逐点区间。

曲线与柱采用不同机制：曲线按 hue mask 的每列中位数读出；柱要求平顶和共同 baseline，否则不声称是柱。实线/同色虚线、只有 marker 形状的系列会混合；灰度图、接触柱、复杂表格、因果/多模态语义仍需人工处理。

## 4. 方法来源与落地边界

参考了优秀开源工作的**问题分解与复核习惯**，本包代码是本地独立实现：
- [Google Research DePlot / ChartQA 生态](https://github.com/google-research/google-research/tree/master/deplot)：学习“图→底层数据表”的可评价目标。本包同样输出表，但刻意不运行生成式 checkpoint；改为 tick calibration + series masks + analytic ground-truth regression，避免自由生成数值。
- 图表恢复中的数值不能只报点估计。本包把估计与双侧栅格区间、单位、tick pairs 和像素位置一起交付，便于独立复量。它不是 DePlot 的复刻，也不声称在 ChartQA 上取得任何分数。

## 5. 失败处理

| 情况 | 行为与退出 |
|-|-|
| case 缺失、非法 JSON、非对象 | refusal code 为 case_unreadable，result 落盘，5 |
| 图片缺失/损坏、无面板 | 写入 limits；有其他数据可交为 partial(3)，否则 undetermined(5) |
| tick OCR 不全/轴无法拟合 | axis fraction；不把估计提升到物理单位 |
| 原表格式未知 | 逐表 `ok=false` 命名，不影响其他可读结果；不猜错表 |
| claim 无锚点/点不存在 | `unresolved`，不能宣称上文与图一致 |
| claim 单位或数值区间冲突 | `inconsistent`，两份证据都保留，在最终答复中说明待人工复核 |
| 无文本图例/第二 y 轴/未给像素图 | 对应字段显式缺口；不造名称或读数 |

`no readable data` 时 `refusal.code=figparse.no_readable_data`。退出码 5 是工具的可诊断结果，Agent 仍须交付可用的部分材料和人工接管位置。

## 6. 可选开发者复核（不在正式工作流中强制）

```bash
python /skills/weekly-skill/scripts/bench_figure.py --report /app/work/figure-bench.json
```

自包含基准在临时目录生成图，不向 Skill 目录写 PNG/cases。当前覆盖 10 场景：线性/对数 x/对数 y、交叉系列、markers+error bars、声明倒置轴、无框拒绝、柱图、柱顶标记、以及图例+原表+claim+契约+确定性。另有 `selftest.py` 的最小双曲线检验。它们只验证合成几何，不是平台三案成绩。

## 7. 依赖与限制

- Python 3.9+；运行使用预装的 `numpy`、`scipy`、`Pillow`。缺依赖属于环境安装问题，不谎称 result 已生成。
- 直接遇到 SVG/PDF 路径时应优先抽取矢量坐标（精确），不要退化为像素估计。
- 不能自动理解整句题注/正文，不能保证 OCR 正确，不读取灰度分离系列，不推断 SD/SEM/FDR，不做显微身份鉴定。
- 参考细节：`references/calibration-method.md`、`references/output-contract.md`、`references/failure-modes.md`、`references/bench-method.md`。
