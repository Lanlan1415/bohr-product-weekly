---
name: graphical-abstract
description: >
  从真实论文/实验材料生成或保源编辑 Graphical Abstract（图形摘要）。以一个可溯源
  core message 为视觉焦点，按 problem/input → method → finding/mechanism → conclusion
  组织一条完整视觉流；结果默认可画成零基线、直接标值的定量小图，附 n、单位、
  不确定性语义与来源范围/限制。渲染 live-text SVG、300 dpi PNG、矢量 PDF 与可重跑
  resolved_spec，核对结论是否越出证据、四段连边/阅读顺序、图上/图注/结果数值溯源、
  标签碰撞/出界、Okabe–Ito 与直接文字冗余编码、XML/PNG/PDF 结构和确定性。
  原样保留 case_id 及全部 output_contract 字段，输出 sources、uncertainty、
  visual_marks、change_records；缺材料绝不补造论文外结论。
---

# graphical-abstract（图形摘要）

GA 的任务不是画一张热闹的信息图，而是把论文唯一核心结论压成一条可回查证据的视觉叙事。**所有节点、核心信息、结果值、结论与限制均须来源绑定。**

## 六步运行时入口（Harbor）

1. **读 case 与真实材料**：输入 `/input/case.json`、`/input/task.md` 及实际论文/记录。原样记录 `case_id` 和 `output_contract` 全部字段；纸面材料是唯一科学事实依据。
2. **抽取单一主线**：选择一个 `core_message`，最多 5 个节点；建立 problem/input、method、finding/mechanism、conclusion 四段映射。不要平行堆叠多个故事。
3. **先落真实产物**：及早写 `/app/work/spec.json` 并调用主入口，交付 `/app/output/figure.svg`、`figure.png`、`figure.pdf`、`resolved_spec.json` 与 `result.json`。预算中断也保留诚实部分产物。
4. **补证据与数图形编码**：为每个节点、核心信息、每项结果与限制给材料 id；有定量结果用 `visual_data` 源值画柱/误差，不能把装饰图标当结果。
5. **审计并修发现**：退出码 0 clean、3 review、4 blocked、5 undetermined。缺类别/坏字段/不可渲染的结构化拒绝不能当完成图；来源不存在的内容不得为消 finding 而编造。
6. **合并最终 JSON**：保留实际审计值、case  authoritative 契约、来源映射、不确定性/限制、变更记录；无法推导的契约键置 null 并写 limits。正式 case 与草稿 spec 冲突时，**case_id/output_contract 以正式 case 为准**。

## 主入口

```bash
python scripts/ga_figure.py --case /input/case.json \
  --spec /app/work/spec.json --out /app/output
```

保留旧通用实体—关系图入口：

```bash
python scripts/schematic.py --spec spec.json --checklist checklist.json --out /app/output
```

主 GA 必须走 `ga_figure.py`，不要拿通用三盒 schematic 代替四段叙事。

## 来源约束的 spec

完整可运行示例为 `examples/spec.json`；骨架如下：

```json
{
  "case_id": "ga-example-001",
  "output_contract": {"fields": ["status", "sources", "uncertainty", "visual_marks"]},
  "canvas_mm": [180, 90], "size_limit_mm": [185, 95],
  "max_words": 80, "font_size": 8.4, "min_font_pt": 6,
  "core_message": {"text": "Porous coating restores uptake", "evidence": "mat3"},
  "takeaways": {"problem": "p1", "method": "m1", "finding": "f1", "conclusion": "c1"},
  "reading_order": ["p1", "m1", "f1", "c1"],
  "result_modality": "quantitative",
  "source_values": ["42", "3", "0.6", "1.8", "0.4", "0.8", "1.5", "2.1", "6"],
  "materials": [
    {"id": "mat1", "name": "Baseline uptake", "source": "Introduction ¶1"},
    {"id": "mat2", "name": "Porous coating", "source": "Methods ¶2"},
    {"id": "mat3", "name": "Uptake rates", "source": "Results Fig 3b"},
    {"id": "mat4", "name": "Scope", "source": "Discussion ¶2"}
  ],
  "nodes": [
    {"id": "p1", "label": "Uptake is slow", "evidence": "mat1", "layer": 0},
    {"id": "m1", "label": "42 nm porous coating", "evidence": "mat2", "layer": 1,
     "steps": ["Form coating", "Expose samples", "Measure uptake"]},
    {"id": "f1", "label": "3x faster uptake", "evidence": "mat3", "layer": 2,
     "visual_data": {"kind": "bar", "unit": "uptake rate (a.u.)",
       "n": 6, "n_caption": "n = 6 per group", "uncertainty": "95% CI",
       "items": [
         {"label": "Before", "value": 0.6, "lower": 0.4, "upper": 0.8, "evidence": "mat1"},
         {"label": "Coated", "value": 1.8, "lower": 1.5, "upper": 2.1, "evidence": "mat3"}]}},
    {"id": "c1", "label": "Coating aids in-vitro uptake", "evidence": "mat4", "layer": 3}
  ],
  "edges": [
    {"from": "p1", "to": "m1", "type": "activate"},
    {"from": "m1", "to": "f1", "type": "activate"},
    {"from": "f1", "to": "c1", "type": "activate"}
  ],
  "limitations": [{"text": "In vitro only; durability untested", "evidence": "mat4"}]
}
```

### 视觉与科学约束

- **一个核心信息**：顶部只放 `core_message.text`；`evidence` 必须指向材料。若核心句只是在总结四个面板，也不能无源。
- **完整视觉流**：四段由 `takeaways` 指定，阅读顺序与 layer 一致，且四个节点之间三条相邻边必须全部存在。跳过结论或只连任意一条都不够。
- **定量结果是图，不是数字装饰**：默认 `result_modality=quantitative`，finding 节点必须有 visual_data。每项 1–4 根柱，值来自 source_values，baseline 必须为 0。下/上端点若存在，必须夹住中心值；标签放在误差线之外。
- **单位、n、语义必须可见**：unit 可为明确 dimensionless，但不能空白；n_caption 用简短文字（每组 n = 6），uncertainty 写 95% CI/SD/SEM。长说明移到 caption 或 result limits。
- **纯定性结果**：确无论文定量结果时显式 `result_modality=qualitative`，不要为了“补齐图表”创造数据。文字/图注/核心句中出现的数值仍与 source_values 对账。
- **少字且可访问**：Okabe–Ito 只是颜色层；另有角色标题、直接标签、hatch、箭头，不靠颜色独立承载意义。无 3D、渐变炫技、双轴或误导截断。
- **限制不是免责声明编造器**：limitations[] 记录论文真正的范围、局限或适用条件。未提取到时进入 review 并在 uncertainty/limits 说明，不能写“无限制”或猜一个限制。
- **结论不越界**：c1 与核心句都须有材料引用；体外结果不能自动升级为体内有效、临床有效或普遍适用。

## 保源编辑

```bash
python scripts/ga_figure.py --case /input/case.json \
  --spec /app/work/base-spec.json --edit /app/work/patch.json \
  --base-figure /app/work/figure.svg --out /app/output
```

- base SVG 必须是可解析 XML 且含 live text；不会把位图截图当源文件。
- patch 按 JSON merge 合并，允许有来源的样式/表达修改；**禁止替换 `materials`、`source_values`、`takeaways`**。节点文字或结果的改变仍重新过数值/证据审计。
- 输出 `change_records.json` 与 result 同级记录，逐项 `{path,before,after}`；`resolved_spec.json` 可复跑，sources 记录 base spec/SVG。

## result.json 与输出契约

| 字段 | 实际内容 |
|-|-|
| `case_id` / output_contract 全字段 | case 原文标识与每一字段；审计值优先于 spec 假称；未知字段 null + limits |
| `status` / `findings` / `severity_counts` | clean/review/blocked/undetermined，规则定位与严重度汇总 |
| `artifacts` | SVG、300 dpi PNG、PDF、caption.txt、resolved_spec；编辑时另有 change_records |
| `visual_narrative` | core_message、四段 takeaways、阅读顺序、结果模态 |
| `visual_marks[]` | 每个结果柱的 node/item/evidence、source_value、rendered_value、baseline、unit、lower/upper、实际几何 |
| `sources[]` | 材料 id/name/source，以及 used_by 面板；可补 base spec/SVG |
| `limitations[]` / `uncertainty[]` | 来源限制与待人工确认缺口，不互相冒充 |
| `change_records[]` | 保源编辑字段级变化；非编辑任务为空 |
| `provenance` / `reproducibility` | 材料覆盖、实体追溯；同 spec 两次渲染文本/几何签名比较 |
| `font` / `accessibility` | 逐字符缺字检查、字体路径、色板与 SVG title/desc；不冒称科学同行评审 |

SVG 用 XML 解析验证 live text，无内嵌位图；PNG 读取签名及 pHYs 物理 dpi；PDF 验证 `%PDF`。时间元数据与随机 SVG 定义 id 被确定化，实测重跑文件可字节一致。

## 实际规则索引

| 类别 | rule（severity） |
|-|-|
| 四段与核心信息 | `ga.missing_takeaway`(high), `ga.takeaway_not_placed`(high), `ga.core_message_missing`(high), `ga.core_message_untraceable`(high), `ga.takeaway_panels_unlinked`(medium), `ga.reading_order`(medium), `ga.reading_order_unknown_node`(medium) |
| 来源与结论边界 | `trace.entity_untraceable`(high), `trace.evidence_not_in_materials`(high), `trace.material_not_drawn`(medium), `trace.edge_not_in_source`(high), `trace.connection_not_drawn`(medium), `trace.no_connection_list`(low), `coverage.incomplete`(high), `route.numbering_vs_text`(medium), `ga.limitations_missing`(medium), `ga.limitation_untraceable`(medium) |
| 数值与结果映射 | `ga.value_not_in_source`(high), `ga.source_values_invalid`(medium), `ga.source_values_unavailable`(medium), `ga.visual_data_invalid`(high), `ga.visual_unit_missing`(medium), `ga.misleading_baseline`(high), `ga.visual_value_not_in_source`(high), `ga.visual_value_untraceable`(high), `ga.visual_interval_invalid`(high), `ga.quantitative_visual_missing`(high), `ga.visual_render_mismatch`(high) |
| 少字/图例 | `ga.empty_label`(medium), `ga.legend_not_declared`(medium), `ga.text_too_long`(medium), `ga.size_out_of_spec`(medium), `legend.entry_unmatched`(medium), `legend.entity_unlisted`(low), `entity.duplicate`(medium), `colour.not_cb_safe`(low) |
| 布局/箭头/字体 | `label.mismatch`(high), `label.overlap`(high), `label.outside_canvas`(high), `label.wider_than_box`(medium), `font.too_small`(medium), `edge.count_mismatch`(high), `edge.zero_length`(high), `edge.backward_flow`(medium), `export.no_font`(high), `export.missing_glyphs`(high) |
| 导出 | `export.empty_artifact`(high), `export.no_live_text`(high), `export.svg_invalid`(high), `export.embedded_raster`(medium), `export.png_invalid`(high), `export.pdf_invalid`(high), `export.low_dpi`(medium), `export.png_dpi_mismatch`(medium), `export.no_font_family`(low), `repro.nondeterministic`(high) |
| 拒绝 | `audit.no_section`(high)：坏/非对象 spec、缺失文件、无法布局/渲染或缺科学依赖；status undetermined、exit 5、保留可读契约 |

## 异常处理与能力边界

- 材料缺四段之一、无核心来源、结果根本无证据： blocked 或结构化拒绝，不自动补一个“合理结论”。
- 坏 JSON、非对象、空 nodes、错类型、base SVG 无 live text：undetermined + exit 5 + result.json，不裸 traceback。
- 结果值不在 source_values、上下限不夹中心、基线非零、独立几何与源值不符：blocked + exit 4。
- 缺单位、缺来源限制、文字过宽/超上限/字号过小、图例不一致：review + exit 3。长注记不要缩到难读，移到 caption。
- matplotlib/numpy/Pillow 缺失：仅在标准库依赖下保留 JSON 拒绝路径，明确不产 SVG/PNG/PDF；不能拿空壳文件充数。正常 Agg 环境会真实光栅渲染，不需 GUI。
- 不计算新的均值/SD/SEM/CI，不做统计检验、正文写作或实验设计。错误研究判断不能由结构、单位、几何审计替代。
- 角色配色只承载导航，不代替领域象形图。平台如果要求未声明的分子/细胞精细画像，需有来源明确实体与安全图标资源；不能从标签臆造机制。
- 文本数值核对按值归一化；`3` 与 `3.0` 一致，不能证明叙述的因果语义，仍需作者确认。

## Requirements

Python 3.9+，matplotlib、numpy、Pillow；标准库 JSON/XML 拒绝路径不依赖网络。Windows 推荐 `python -X utf8`。正常平台镜像直接真实渲染 SVG/PNG/PDF。

## 参考实现落地

- SiliCoDraw（https://github.com/Alex-D-C/SiliCoDraw）的**可编辑 JSON、面板编号与箭头、多阶段图形摘要、typed-value chart** 对本包有直接实现影响：`resolved_spec`、四段卡片和 visual_data/柱标/CI 均是可运行实现，不是仅列链接。
- 本地高分 schematic/provenance/fontsel 机制保留：材料覆盖、逐字符字体、标签几何、确定性复查；主 GA 则替换旧三盒图为四段叙事并新增 PDF/源值图。

## Optional verification（非运行时必需步骤）

```bash
python scripts/bench_ga.py        # 9：四段主张、数字、文字/尺寸与流程
python scripts/bench_ga2.py       # 9：完整渲染、溯源、字形、确定性注入
python scripts/bench_ga3.py       # 26：四段核心/结果/限制规则、契约、拒绝、FP guard
python scripts/bench_schematic.py # 8：独立通用 schematic 回归
```

共 52 场景。额外 CLI 探针实际覆盖 case 优先契约、编辑/禁改源内容、坏输入、四种退出码、长注记、XML/PNG/PDF 和 7 个交付文件重跑字节一致；CJK 与英文 smoke 输出均已真实打开检查。
