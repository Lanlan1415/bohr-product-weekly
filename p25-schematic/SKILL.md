---
name: schematic-figure
description: >
  Generate and edit source-bound scientific schematics (科研示意图、机制链条、实验流程) as
  real editable SVG with live text, 300 dpi PNG, vector PDF, semantic geometry mapping and
  provenance. Use when every node/edge, value and unit must trace to the source; when labels,
  categories and legends must stay consistent; or when an existing SVG needs an addressed,
  source-preserving edit. Performs deterministic text wrapping, rectangle collision handling,
  named-port connections, XML geometry verification and full case_id/output_contract passthrough.
  Not for statistical analysis, poster decoration or unsupported free-form pictograms.
---

# Source-bound schematic generation and editing

主入口是 `scripts/sourcebind.py`。它**真实生成/编辑图稿**，不是只写审计 JSON。旧的
`scripts/schematic.py` 保留作兼容/回归入口，但不是新案例的首选路径。

## Runtime：六步完成一个案例

1. **读真实输入。** 读 `/input/case.json`、`/input/task.md` 和实际材料/图稿。记录
   `case_id`、`output_contract`、案例材料路径和版本；正式图的科学内容只能来自这些输入。
   不按 challenge 名称猜图，不使用本包示例冒充正式答案。
2. **写来源绑定 spec 到 `/app/work/spec.json`。** `materials[]` 是材料清单；每个
   `nodes[]` 用 `evidence` 指向材料 id；`connections[]` 是来源明确陈述的关系；`edges[]`
   是要画的对应关系。来源没说的关系、数值、单位和节点不要补。填不出 key 时登记
   `uncertainty`，不要为了让审计通过而造值。
3. **运行真实生成链**（Skill 安装在 `/skills/weekly-skill` 时，令 `$SKILL` 指向该目录）：

   ```bash
   python -X utf8 "$SKILL/scripts/sourcebind.py" \
     --mode schematic --spec /app/work/spec.json \
     --case /input/case.json --meta /app/work/meta.json \
     --checklist /app/work/checklist.json --out /app/output
   ```

   `--meta` 与 `--checklist` 可选。`meta.json` 可含 `sources`、`uncertainty`、`limits`；
   checklist 可含 `entities[{id}]` 和 `relations[{from,to}]`。没有 `--case` 时可用
   `--case-id`。如果 case 已明确内嵌 `spec.nodes`，也可只给 `--case`；**自然语言 case
   不会由脚本自动猜成图**，仍由 Agent 先完成来源抽取。只给无 spec 的 case 会拒绝。
4. **先保存再修图。** 成功时 `/app/output` 包含 `figure.svg`、`figure.png`、`figure.pdf`、
   `mapping.json`、`spec.json` 和 `result.json`。SVG 是可编辑分层源；PNG 为 300 dpi；
   PDF 为矢量并含 TrueType `/FontFile` 嵌入证据；mapping 记录每个节点的 bbox、label、
   value/unit、evidence/compartment，以及每条边的 from/to/type、端口坐标和来源。
5. **读退出码并修 spec/源材料，而非删检查。** `0=clean`、`3=review/partial`、
   `4=blocked`、`5=undetermined/refused`。high 发现未解决时不得把 `clean` 写回去。
   交付前检查 `case_id`、`contract_field_values`、`exports`、`checked`、`sources`、
   `change_records` 和 `limits`。
6. **同命令重跑。** 相同路径下 SVG/PNG/PDF/mapping/spec/result 必须字节一致。PDF 元数据
   已固定，不能用“时间戳不同”掩盖图像几何变化。另做 SVG 结构检查；没有打开预览时，
   `visual_check` 明确是 `not performed`，不得声称做过人工/视觉验收。

## Source-preserving SVG 编辑

对已有 SVG 做精确寻址编辑，不写死示例图，不重建无关元素：

```bash
python -X utf8 "$SKILL/scripts/sourcebind.py" \
  --edit-svg /input/figure.svg --edits /app/work/edits.json \
  --case /input/case.json --out /app/output
```

`edits.json` 是列表，例如：

```json
[
  {"op":"rename", "target_id":"catalyst", "new_label":"催化剂 20 min"},
  {"op":"recolour", "target_id":"catalyst", "color":"#56B4E9"},
  {"op":"set_relation_type", "target_id":"r1", "new_type":"inhibit"}
]
```

target 按 `id`、`node-{id}`、`edge-{id}` 或对应 label id 精确解析；找不到就 exit 5，
绝不模糊匹配。rename 保留单独声明的 value/unit；recolour 只改目标形状；
`set_relation_type` 同步 data-type 与实际 marker-end，并在 defs 中加入所需 marker。
无关 body 元素数量和 live-text 结构写入 `edit.unrelated_elements_preserved`。
关系编辑后必须同步更新 spec/connections 并重跑来源审计，不能只让新箭头“看起来对”。

第三方 SVG 的精确 PNG/PDF 栅格化需要兼容 SVG 渲染器；本包不假定它存在。可额外传
`--spec /app/work/updated-spec.json`，将**更新后 spec** 的预览写入
`preview_from_spec/`。那是 spec 重渲预览，不冒充第三方 SVG 的逐像素一致预览。无兼容
路径时仍交付保留原结构的 SVG，状态 review，限制写清楚。

## 最小 spec（EXAMPLE ONLY，非正式答案）

```json
{
  "case_id":"example-schematic",
  "title":"catalyst relationship",
  "materials":[
    {"id":"m1","name":"基底","source":"EXAMPLE Methods ¶2","version":"v1"},
    {"id":"m2","name":"催化剂","source":"EXAMPLE Methods ¶2: catalyst binds substrate","version":"v1"}
  ],
  "connections":[
    {"from":"a","to":"b","type":"bind","source":"EXAMPLE Methods ¶2: bind"}
  ],
  "nodes":[
    {"id":"a","label":"基底","evidence":"m1","layer":0,"category":"reactant"},
    {"id":"b","label":"催化剂","evidence":"m2","layer":1,"category":"agent","value":20,"unit":"min"}
  ],
  "edges":[{"id":"r1","from":"a","to":"b","type":"bind"}],
  "categories":{"reactant":"#56B4E9","agent":"#009E73"},
  "canvas_mm":[180,90]
}
```

- `layer` 是非负整数，决定 DAG 的主方向；明确 `x/y` 也可给定中心坐标，重叠仍会被查出。
- `value` 与 `unit` 分开保存，都会真实上屏；不得把来源无单位数字补成测量值。
- `categories` 是类别到 Okabe–Ito 色值的映射，自动生成色样图例；颜色不是唯一语义通道，
  关系 marker 同时编码类型。
- `edges[].from_port/to_port` 支持 `N/E/S/W`，亦兼容 schemdraw 风格的 `start/end/in/out`
  别名；未声明时按真实源/目标 bbox 计算边界端口，不从盒心穿出。

## 实际图形语义

| 输入 | 真实图元 |
|-|-|
| `bind` | 绿色虚线 + 末端圆点，无方向箭头 |
| `activate` | 蓝色三角箭头 |
| `inhibit` | 红色 T-bar |
| `flow` | 灰色方向箭头 |
| `phosphorylate/ubiquitinate/recruit/transport` | 可区分配色、marker 与 P/Ub/recruit/transport 标签 |
| 未知关系 | blocked + 可见 UNRESOLVED 图例和菱形端点；绝不静默当 flow |
| 长中文/英文标签 | 按 East Asian 字宽换行，保留全部字符与数值单位 |
| 节点/类别 | `layer-nodes` / `layer-legend` 分组、稳定 id、data-evidence/bbox/layer |

布局借鉴 d3-force 的**有界碰撞半径/迭代松弛**思想，但使用矩形 bbox 和固定顺序，无随机
源；最多 80 轮，未解开会报 high。端口策略借鉴 schemdraw 的**命名 anchor、`at/anchor`
连接状态**思想，映射为明确 N/E/S/W/start/end/in/out 端口和真实几何回读。每个导出件都
按同一 mapping 绘制，bind 圆点、类别色样和区室不是 SVG 独有装饰。显式 feedback/recycle
以及任何穿过第三方节点的直线都使用预留走廊的贝塞尔绕行，mapping 记录 d/control_y/
reason；Liang–Barsky 检查直线不会穿越无关科学实体。

## `result.json` 与 output_contract

同时支持两种正式输入形态：

1. 平面映射：`{"case_id":"...","status":"...","exports":"..."}`；
2. schema 形态：`{"fields":[...]}`、`{"required":[...],"properties":{...}}`。

`case_id` 原样回填。平面契约的每个 key 都在 `output_contract` 中有对应值；schema 声明
保留在 `output_contract`，所有请求字段的实值在 `contract_field_values`，适合顶层暴露的
字段也会写顶层。案例/spec 显式携带的 `deliverable_svg` 等描述符原样保留；真实生成的
`case_id/status/exports/editable_source/figure_*/mapping_json/...` 用真实运行值；推导不出的
字段为 `null` 并在 `limits` 点明，绝不省略或伪造。

主要字段：`figure`、`editable_source`、`exports[]`（格式/字节数/magic/sha256/PNG dpi/
PDF font marker）、`provenance`、`sources`、`uncertainty`、`limits`、`checked`、
`visual_check`、`reproducibility`、`change_records`。来源文件可列在 `source_files[]`，
若可读会记录真实 SHA-256。

## 异常与退出码

| 情形 | 产物 | exit |
|-|-|-|
| clean，完整 SVG/PNG/PDF | 全套图稿、mapping、spec、result | 0 |
| 非 high 发现、matplotlib 不可用/导出失败 | SVG/mapping/result 保留，limits 指明 partial | 3 |
| 悬空边、未知关系、来源不一致、重叠/出界、缺字形 | 已有图稿保留，status=blocked | 4 |
| JSON 不可读、非对象、无节点、非法 canvas/layer、无抽取 spec | structured result，`audit.no_render` | 5 |
| 编辑 target 不存在、编辑指令缺失/畸形 | structured refusal | 5 |
| 输出目录不可写 | 无法在不可写目录落 result；stdout 给结构化错误 | 5 |

旧的 `schematic.py --spec ... --out ...` 没有本主链的 `--case` 与 source-preserving edit
能力；不要混用两套文档。兼容性回归仍覆盖旧渲染器的 label/legend/provenance/font/export
规则，避免新主链上线时破坏已有能力。

## 真实验证

```bash
python -X utf8 "$SKILL/scripts/bench_sourcebind.py" --mode schematic
python -X utf8 "$SKILL/scripts/bench_schematic.py"
python -X utf8 "$SKILL/scripts/bench_schematic2.py"
python -X utf8 "$SKILL/scripts/bench_schematic3.py"
```

本机实测：sourcebind 25/25；旧回归 11/11、7/7、8/8。测试使用临时目录，不污染包。
覆盖 clean 基线；fields/flat 两种契约；fresh-output 的显式 case-id；坏 JSON/非对象/空节点/NaN；
悬空/未知关系；反向端口和 marker 篡改；长 CJK 与 XML 注入；真实 PNG/PDF magic、PNG pHYs dpi、PDF
FontFile；同目录六件产物字节幂等；SVG 定点编辑和错误地址。`scripts/report_sourcebind.json`
是当前真实报告。另打开过一个本地示例 PNG，发现 bind 圆点/类别色样跨格式不一致并已修复；
这不代表见过平台私有案例或做过其视觉验收。

## Dependencies、参考与限制

- Python 3.10+；生成 editable SVG/mapping 只用标准库。PNG/PDF 与字体覆盖检查需要
  `matplotlib`（Agg）；本地用户 site-packages 时按示例用 `python -X utf8`，不要加 `-I`。
  缺 matplotlib 时导出件诚实缺失并 review，不能声称已渲染 PNG/PDF。
- 参考实现（只作方法来源，不是运行依赖）：GitHub `d3/d3-force` 及 `d3/d3` 的
  `docs/d3-force/{simulation,collide}.md`（固定步数/碰撞松弛）；GitHub `cdelker/schemdraw`
  的 `docs/usage/placement.rst`（命名 anchor、at/anchor、drawing state）。本地
  `p3i01` 的 SVG↔ledger 双向回查用于溯源设计。
- 本包生成通用科研语义图元，不凭领域标签虚构复杂仪器/蛋白象形图。装置/生物专用语义
  分别由对应 `apparatus` / `pathway` 模式扩展；需要图库级 pictogram 时须由来源提供图元。
- 自动布局防止可解的节点重叠，但不能保证任意高密反馈图无需人工排版。无法解决的要求
  保留 high finding，交付 partial/blocked，不缩到不可读字号。
- OCR、PDF 机制理解、实体消歧和金标准科学判断仍由 Agent/native judge 依据真实材料完成；
  脚本核对结构化声明与真实图元的一致性，不代替科学判断。
