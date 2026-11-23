---
name: source-chart
description: >
  科研数据图表生成与保源编辑。读取真实 CSV/TSV/JSON 数据表，按 nominal/ordinal/
  quantitative/temporal 字段类型选择或验证 bar/line/scatter/box/heatmap/histogram，
  用显式 encoding 把图元绑定到源行，渲染可编辑 live-text SVG、300 dpi PNG 与 PDF。
  支持日期轴、分组避让、源值柱标、预聚合对称/非对称误差棒和 CI errorband；核查标题、
  轴标目/单位、图例、样本量、误差语义、截断基线、双轴、裁剪、字形与 XML/文件结构。
  支持用 JSON merge patch 编辑既有 spec 与 live-text SVG，并输出 before/after
  change_records。保留 case_id 和全部 output_contract 字段、sources、uncertainty、
  mark_to_row、输入 sha256；例如有源数据表时要真实生成或修改可复核科研图表。
---

# source-chart（科研数据图表生成与编辑）

一张科研图是对数据的断言。此包不只“画图”：字段类型决定图型，源列决定图元，实际渲染几何再回对源值。

## 六步运行时入口（Harbor）

输入为 `/input/case.json`、`/input/task.md` 与题目所指真实材料；工作文件放 `/app/work`，最终交付放 `/app/output`。

1. **读 case 和材料**：原样保留 `case_id` 与 `output_contract` 的**全部字段名**及其形状。只从实际 CSV/TSV/JSON 或从论文源表诚实抽取出的表文件读取数值；不要从标签猜数据。
2. **先落可交付产物**：优先用下方显式或自动入口写出 `figure.svg`、`figure.png`、`figure.pdf` 与 `result.json` 到目标目录，再修复 findings。没有可用数值/单位时留空并在 uncertainties/limits 说明，不补造。
3. **确定图型与 spec**：变量类型和分析目的共同决定图型。重复原始观测优先 box，一次聚合的类间比较用 bar；两个连续变量用 scatter；时间/有序量用 line；两网格字段加数值用 heatmap；显式分箱的分布用 histogram。拒绝饼图、3D 与双量纲双轴。
4. **生成与审计**：运行 `scripts/chartguard.py`。退出码 0 clean、3 review、4 blocked、5 refused/undetermined。blocked/refused/undetermined 不得冒充完成。
5. **修发现并重跑**：只修有证据的字段。单位须来自材料；`caption_n` 必须能对回 n 列或行数；误差语义写 SD/SEM/95% CI/range。误改源数据不是修图。
6. **合并最终交付**：保留引擎审计值；spec 携带的契约字段直通；无法推导的契约键置 null 并在 limits 说明。补齐 `sources`、`uncertainty`、`change_records`，连同 `resolved_spec.json`、`mark_to_row.json`、`source_snapshot.*`、`caption.txt` 一起交付。

## 生成入口

### A. 显式 encoding（提倡，最可控）

```bash
python scripts/chartguard.py --spec /app/work/spec.json --data /input/source.csv --out /app/output
```

```json
{
  "case_id": "case-from-input",
  "output_contract": ["status", "sources", "uncertainty", "custom_tail"],
  "kind": "bar",
  "title": "Treatment response by genotype",
  "caption": "Source-row values; bars carry a colour and a hatch.",
  "x_label": "Treatment",
  "y_label": "Response",
  "y_unit": "a.u.",
  "caption_n": 6,
  "n_semantics": "biological replicates per group",
  "legend": true,
  "panel": "a",
  "value_labels": true,
  "errorbar_meaning": "SD",
  "encoding": {"x": "condition", "y": "response", "y_err": "response_sd", "group": "group"}
}
```

类别轴不要求单位。单位/样本量的复制单位不是证明。`caption_n` 与 n 列（n/sample_size/samples/n_obs）或源行数对账；无声明时图注明确“源行不是独立 n”。`sample_size` 记录每组源观测数，不将其擅称为生物学重复。

### B. 类型感知自动选图

```bash
python scripts/chartguard.py --auto --data /input/source.csv \
  --case /input/case.json --task /input/task.md \
  --question "show correlation" --units '{"dose":"mg/kg","response":"a.u."}' \
  --out /app/output
```

自动模式把 nominal/ordinal/quantitative/temporal 推断写入 encoding 的 field_types，把选择理由写入 selection，并拒绝常见替代误用。可用 `--kind bar|line|scatter|box|heatmap|histogram`、`--x`、`--y`、`--group` 覆盖；kind 不会误注入 encoding。自动无法知道材料的单位；不给 `--units` 时缺单位会如实进入 review。

### C. 时间、CI 与非对称不确定性

- ISO 日期/日期时间在 line 中转换为真实日期坐标并使用日期刻度；不会退化为行号。bar 使用时间字段触发 `encoding.time_as_bars`。
- `y_err`、`x_err` 是上侧幅度，`y_err2`、`x_err2` 是下侧正幅度（非对称 Vega-Lite 式分层 errorbar）。负幅度触发 high。
- line 可同时映射 `y_lower`、`y_upper` 两个**绝对端点列**，实际画出独立 CI/errorband 层和中心线。两端必须成对，且每行须满足 lower ≤ centre ≤ upper。
- 任一误差/区间通道都需要 `errorbar_meaning`（旧字段 `error_meaning` 可兼容；二者冲突则拒绝）。这些端点全部来自源表，引擎不自行计算 SD/SEM/CI。

```json
{
  "kind": "line", "title": "Mean response with interval",
  "x_label": "Time", "x_unit": "day", "y_label": "Response", "y_unit": "a.u.",
  "caption_n": 4, "n_semantics": "independent cultures", "panel": "a",
  "errorbar_meaning": "95% CI",
  "encoding": {"x":"day", "y":"response", "y_lower":"ci_low", "y_upper":"ci_high"}
}
```

小数据集 bar 可加 `value_labels:true`：使用 Matplotlib grouped-bar 案例的 container 读回值标注，不重打数字。分组柱按类别槽位避让；颜色之外再用 hatch/marker/dash 和图例文字，采用 Okabe–Ito。

## 保源编辑

对上次生成的 spec 或 live-text SVG 做最小声明式修改，而非随机重画：

```bash
python scripts/chartguard.py --spec /app/work/base-spec.json \
  --edit /app/work/patch.json --base-figure /app/work/figure.svg \
  --data /input/source.csv --out /app/output
```

patch 使用 JSON merge 语义，嵌套 dict 局部合并、标量与数组替换。例如：

```json
{"title":"Edited title retaining the source CI", "y_label":"Edited response label"}
```

引擎验证 base SVG 是 XML 且含 live text，禁止 patch 替换 `data`、`data_file`、`rows`、`source_snapshot`；数据哈希、逐行 mark/CI 端点保持可回对。输出字段级 `{path,before,after}` 到 `change_records.json` 与 result；来源记录包含 base spec/SVG。编encoding 时仍重新验证列和类型。

## 输出契约

`result.json` 至少含：

- `case_id`、`status`、`findings[]`（rule/severity/message 与定位）、`severity_counts`、`limits`；
- `encoding`：chart_kind、channels、source rows、mark 数、字段类型及自动选择理由；
- `mark_to_row[]`：mark、row、x/y、series、误差或非对称端点、实际 rendered 几何；另有 `mark_to_row_sha256`；
- `sample_size`、`aggregates`（histogram bin↔源行）、`accessibility`（色板、冗余编码、SVG title/desc）；
- `artifacts`：figure.svg/png/pdf、caption、mark_to_row、resolved_spec、source_snapshot、编辑时 change_records；
- `provenance`：spec/data sha256、引擎与 matplotlib 版本、字体、dpi、输入快照；
- `sources`、`uncertainty`、`change_records`；
- **全部 output_contract 字段**：正式 case 同名覆盖 spec 草稿；引擎审计值覆盖试图回填的 status 等实际结果；其余 spec 原值直通，否则 null + limits。支持字段列表、dict、`fields` 容器与 `{name|field|key}` 项。

SVG 经 XML 解析并保留 live text、title、desc 和 role=img；PNG 检查签名与 pHYs  dpi；PDF 检查 `%PDF`。SVG 定义 id 被确定化，三种格式移除/固定墙钟元数据。相同路径与输入重跑可字节复现 result、SVG、PNG、PDF、映射与图注。

## 主要规则（实际引擎规则索引）

| 类别 | rule（severity） |
|-|-|
| 图型/数据类型 | `encoding.unknown_chart_kind`(high), `encoding.required_channel_unmapped`(high), `encoding.column_missing`(high), `encoding.not_numeric`(high), `encoding.time_as_bars`(medium), `encoding.unsupported_channel`(high), `encoding.unsupported_channel_for_kind`(high), `encoding.dual_axis_unsupported`(high), `encoding.incomplete_interval`(high), `input.encoding_not_object`(high) |
| 数据完整性 | `data.no_rows`(high), `data.duplicate_marks`(high), `data.duplicate_rows`(low), `data.missing_numeric`(medium), `data.small_sample`(low) |
| 标注/轴 | `annotation.title_missing`(medium), `annotation.unknown_comparison`(high), `axis.x_label_missing`/`axis.y_label_missing`(high), `axis.x_unit_missing`/`axis.y_unit_missing`(medium), `axis.value_clipped`(high), `axis.truncated_baseline`(high), `axis.log_nonpositive`(medium), `layout.panel_missing`(low), `layout.caption_outside_canvas`(high) |
| 图例/系列 | `series.missing_from_chart`(high), `legend.absent`(medium), `legend.series_mismatch`(medium) |
| 不确定性 | `error.column_not_drawn`(high), `error.invalid_interval`(high), `error.invalid_value`(high), `annotation.errorbar_meaning_missing`(medium) |
| 样本量 | `caption.n_mismatch`(high) |
| 色阶/可读性 | `color.unit_missing`(medium), `color.range_undeclared`(medium), `color.range_invalid`(medium), `color.range_clipped`(high), `read.too_many_categories`(medium) |
| 映射 | `traceability.missing`(high), `traceability.row_coverage`(medium), `encoding.drawn_value_mismatch`(high) |
| 导出/字体 | `export.empty_artifact`(high), `export.no_live_text`(high), `export.svg_invalid`(high), `export.png_invalid`(high), `export.pdf_invalid`(high), `export.accessibility_description_missing`(medium), `export.low_dpi`(medium), `export.png_dpi_mismatch`(medium), `export.width_invalid`(medium), `export.width_out_of_band`(medium), `font.unresolved`(medium), `font.glyph_missing`(medium) |
| 输入/运行 | `input.spec_unreadable`(high), `input.spec_not_object`(high), `input.data_unreadable`(high), `input.label_truncated`(medium), `input.conflicting_uncertainty_semantics`(high), `input.request_invalid`(high), `dependency.unavailable`(high), `render.failed`(high), `runtime.failed`(high) |

## 失败处置与边界

- 缺列、文本驱动数值通道、空表、未知图型、非对称区间缺端点、双轴/3D 请求：结构化 refusal，exit 5，不生成貌似正确的图。
- 坏 JSON、非对象、坏 UTF-8、文件缺失、渲染异常：结构化 undetermined，exit 5；尽可能保留可读 case 契约，绝不抛用户 traceback。
- 数值/CI 端点出轴、负误差、lower/upper 未夹住中心、图值与源值不符：blocked，exit 4。
- 缺源单位/误差语义、类别过多、低 dpi：review，exit 3；不得为消发现而编单位或显著性。
- 仅六种图型。显著性声明仅核查组是否存在，不绘制/选择检验。 violin/pie/contour/3D 不做；双量纲请分面或经声明归一化。
- 不替材料推断统计分布或独立样本单位；不做科学实体的语义识别；几何/文件审计不等于人工视觉验收。
- 长标签以 240 字符截断并报告；更进一步的遮挡需调整 figsize/文案。当前不做任意 Office 文件导入。
- 字体依赖系统字体。缺字会点名；缺字体/GUI 不阻止 Agg 输出，若无可用渲染依赖则结构化拒绝并明确限制。

## Requirements

Python 3.9+，matplotlib、numpy；无网络依赖。Windows 可用 `python -X utf8`；依赖不可用时生成 `undetermined` 结果，不伪造图件。

## 参考实现落地

- Vega-Lite `layer_line_errorband_ci` 的**独立 errorband + centre line** 与本包 line 的 y_lower/y_upper 分层一致；其 pre-aggregated asymmetric errorbar 思路对应 x/y_err + x/y_err2。字段类型、显式通道与源数据值对应 declarative grammar，而非只附链接。
- Matplotlib “Grouped bar chart with labels” 的**槽位避让 + container 值标注**实现为稳定 dodge、Okabe–Ito/hatch 冗余编码和可选 `value_labels`。
- 本地高分 data-viz v2 的字段推断、自动选图、零基线/裁剪/双轴/重复图元/字体检查已并入并扩展到本包 source-chart/v3。

## Optional verification（不是运行时必需步骤）

```bash
python scripts/bench_chart.py
```

34 个场景使用临时目录，包含 clean 基线、每类缺陷和 FP guard，并检查 CI 源映射、非对称误差、真实日期几何、XML 结构、柱值标注。另有 CLI 敌意探针覆盖自动覆盖、契约、保源编辑、坏输入、退出码和重跑字节一致性。

仅供测试失败定位的 bench-only 断言（不是交付 findings）为 `test.grouped_bar_overlap`、`test.caption_semantics_missing`、`test.accessibility_metadata_missing`、`test.histogram_count_mismatch`、`test.errorband_not_source_mapped`、`test.source_value_label_missing`、`test.asymmetric_interval_not_source_mapped`、`test.temporal_geometry_missing`、`test.svg_root_invalid`、`test.svg_not_parseable`。
