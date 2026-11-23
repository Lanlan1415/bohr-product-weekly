---
name: apparatus-figure
description: >
  Generate and edit experimental apparatus, material/energy/information flow diagrams and
  technical roadmaps (实验装置、仪器连接、分流回流、工艺路线). Emits editable SVG, 300 dpi PNG
  and vector PDF from source-bound BOM/components, named ports, stages and milestones. Implements
  pump/valve/vessel/sensor/detector/source/sink symbols, four physical flow channels, branching,
  non-crossing recycle/bypass arcs, S01…Sn stage labels, route entry/exit checks, provenance,
  source-preserving SVG edits and strict case_id/output_contract passthrough. Does not invent
  connections, physical specifications or unsupported instrument symbols.
---

# Apparatus and technical-route sourcebind

主入口是 `scripts/sourcebind.py --mode apparatus`。它生成**实际装置图/技术路线图**和
PDF/PNG，而不是只报一份检查 JSON。旧 `apparatusfig.py` / `pathway.py` 保留兼容回归。

## 六步运行时工作流

1. **读取事实。** 读取 `/input/case.json`、`/input/task.md`、实际 Methods/装置清单/工艺段/
   输入图稿。保留 `case_id`、`output_contract`、真实文件版本和页/段/图号。不按“装置图”
   标签臆造冷阱、泵、阀、回流、接口、参数或单位。
2. **写 `/app/work/spec.json` 中间表示：**
   - `materials[]` 为材料/设备条目（id、name、source/quote、version），节点以 evidence 溯源；
   - `components[]` 为可选 BOM，节点缺件会是 high；nodes 写 `part_kind`、label、stage/instance；
   - `connections[]` 逐条记录来源的 from/to/type/source，edges 是实际要画的对应管路与流；
   - `flow_kind` 明确 material/energy/information/waste；flow_kind 不能靠布局推断；
   - `step_order` 与 nodes.stage 一一对应（常规从 1 连续编号），`from_port/to_port` 是接口；
   - `figure_kind:"route"` 启用技术路线的入口/出口与 stage 约束；`milestone:true` 只用于
     来源明确声明的里程碑。未知字段留 uncertainty，而不是补成事实。
3. **真实生成：**

   ```bash
   python -X utf8 "$SKILL/scripts/sourcebind.py" \
     --mode apparatus --spec /app/work/spec.json \
     --case /input/case.json --meta /app/work/meta.json \
     --checklist /app/work/checklist.json --out /app/output
   ```

   `--meta/--checklist` 可选，无 case 文件时用 `--case-id`。meta 支持
   `sources/uncertainty/limits`；checklist 支持 entities/from-to relations。case 已显式
   内嵌 `spec.nodes` 可只给 `--case`；自由文本仍由 Agent 先读材料写 spec，脚本不猜工艺。
4. **检查实际产物。** `/app/output` 包含 `figure.svg`、`figure.png`、`figure.pdf`、
   `mapping.json`、`spec.json`、`result.json`。SVG 保持 live text 和 compartments/nodes/
   edges/legend 分层；mapping 给部件 bbox、stage/milestone、接口、from/to/type/flow_kind/
   route/control_y 和 source locators。
5. **修真实问题。** `0=clean`、`3=review/partial`、`4=blocked`、`5=undetermined`。
   missing BOM、反向但来源不一致的管路、断头、未知 flow、route 无入口/出口、stage 重复、
   decision 单支路、跨节点管线或重叠不可作为成功图交付。修 spec/源材料，不删检查。
6. **复跑。** 同一输出路径下 SVG/PNG/PDF/mapping/spec/result 必须字节一致；PDF 元数据
   固定，时间戳不作为豁免。XML/几何/magic 是自动证据；未打开预览时 visual_check 为
   `not performed`，不声称做过视觉检查。

## 最小装置 spec（EXAMPLE ONLY）

```json
{
  "case_id":"example-apparatus",
  "figure_kind":"apparatus",
  "materials":[
    {"id":"m1","name":"循环泵 P-101","source":"EXAMPLE Methods ¶2: pump P-101","version":"v1"},
    {"id":"m2","name":"膜阀 V-102","source":"EXAMPLE Methods ¶3: valve V-102","version":"v1"}
  ],
  "components":["循环泵 P-101","膜阀 V-102"],
  "connections":[{"from":"pump","to":"valve","type":"flow",
                  "source":"EXAMPLE Methods ¶2–3: material enters valve"}],
  "nodes":[
    {"id":"pump","label":"循环泵 P-101","part_kind":"pump","evidence":"m1","stage":1},
    {"id":"valve","label":"膜阀 V-102","part_kind":"valve","evidence":"m2","stage":2}
  ],
  "edges":[{"id":"f1","from":"pump","to":"valve","type":"flow",
            "flow_kind":"material","from_port":"E","to_port":"W"}],
  "step_order":["pump","valve"]
}
```

## 装置图元、接口和流向

| spec | 真实表达 |
|-|-|
| `part_kind:pump` | 圆形泵体 + 不遮挡标签的上置方向三角 |
| `part_kind:valve` | 双三角阀 |
| `part_kind:vessel` | 圆角容器与内分隔线 |
| `part_kind:sensor/detector` | 圆形检测单元与传感器线 |
| `part_kind:source/sink` | 菱形入口/出口 |
| `flow_kind:material` | 灰色实线物料流 |
| `flow_kind:energy` | 橙色实线能量流 |
| `flow_kind:information` | 蓝色 `8,5` 虚线信息流 |
| `flow_kind:waste` | 红色 `2,5` 点线废物流/出口 |
| 未知 flow_kind | blocked + UNRESOLVED FLOW；不静默画成物料 |
| `milestone:true` | 蓝色粗描边 + 自动里程碑图例；仅来自显式声明 |

圆形/检测部件使用容纳 stage+仪器标签的方形 bbox，避免“圆看着正常，文字伸出轮廓”。
SVG 与 PNG/PDF 的色样、实际颜色、虚线和图例一致。`from_port/to_port` 支持 `N/E/S/W`，
也支持 schemdraw 风格 `start/end/in/out`；未指定时端口由真实源/目标边框计算，不贯穿盒心。

## 技术路线、反馈与布局

- `figure_kind:"route"` 保留 route 子类型，不被 apparatus renderer 覆盖；至少要有入口和
  一个终止节点。闭合流程没有入口/出口时，分别报 `route.no_entry/no_exit`。
- stage 真实显示为 `S01 | …` 等；`step_order` 与 Methods 文本顺序不一致时报
  `route.numbering_vs_text`。stage 重号、跳号、决策少于两条出边分别对应专用 finding。
- `kind:"decision"` 且有两个真实出边才算分流；废料/支路有明确 sink，不产生断头箭头。
- 显式 `feedback:true` / `recycle:true` 回路由上方预留通道绕行；**任何普通直线若穿过
  第三方部件，也会自动改为绕行曲线**，mapping 的 `route.reason` 记录
  `feedback/recycle` 或 `unrelated-node-bypass` 以及避让节点。
- 曲线使用三次贝塞尔几何和真实末端 tangent；控制点 >=34，避免回流标签裁出画布。
  Liang–Barsky 直线/bbox 检查防止边穿越无关节点；d3 风格矩形碰撞迭代最多 80 轮。
  高密极复杂图仍可能需人工分区，不缩字伪造 clean。

## Source-preserving SVG 编辑

```bash
python -X utf8 "$SKILL/scripts/sourcebind.py" \
  --edit-svg /input/figure.svg --edits /app/work/edits.json \
  --case /input/case.json --out /app/output
```

`rename/recolour/set_relation_type` 按精确 id 定点修改；未知 target、畸形指令和缺 edits
均 exit 5。重命名保留独立 value/unit；关系变更同步 data-type 与实际 marker；无关 body
元素和 live text 保留并记录 before/after。编辑后须同步 spec/connections 并重跑来源审计。

可附 `--spec updated-spec.json`，在 `preview_from_spec/` 生成该更新 spec 的 PNG/PDF；
它不会冒充第三方原 SVG 的逐像素一致预览。无兼容渲染路径时，编辑后 SVG 保留并 review，
限制写清，绝不声称渲染成功。

## result.json、契约与证据

支持平面 `output_contract` 和 `fields[]/required[]+properties{}` 两种正式形态。

- `case_id` 原样回填；平面契约逐 key 解析；schema 声明原样保留，所有请求字段的实值在
  `contract_field_values`，适合字段同时写顶层。显式 `deliverable_svg` 等案例值原样保留。
- 实际导出/映射字段写真实运行结果；不能推导的字段为 `null` 并在 limits 说明。
  有效 case 与可读 spec 的声明在拒绝路径同样回填。
- `exports[]` 有格式/大小/magic/SHA-256；PNG pHYs 验 dpi；PDF 验 `%PDF` 与 `/FontFile`。
  老版主入口没有 --case 和 PDF 的问题不适用于 sourcebind。
- `mapping.json` 给每个节点 label/value/unit/evidence/stage/milestone/bbox 与每条边
  from/to/type/flow_kind/ports/route/source；`change_records`、`sources`、`uncertainty`、
  可读 `source_files` SHA-256 支撑独立复核。

## 退出码与限制

| 情形 | exit |
|-|-|
| clean 全套装置/路线图与三件套 | 0 |
| 中低危发现、缺 matplotlib/PNG/PDF 导出失败 | 3；SVG/mapping/result 保留，partial+limits |
| 来源缺件、未知 flow、悬空连接、无 route 入口/出口、stage 重复、设备/文字重叠 | 4；真实已有图保留，blocked |
| 坏 JSON、非对象、空 nodes、非法 canvas/layer、无抽取 spec、编辑无 target | 5 structured refusal |
| 目录不可写 | 5，不能在目录内谎称写了 result；stdout 结构化错误 |

依赖 Python 3.10+；SVG/metadata 由标准库生成。PNG/PDF 与字形覆盖检查需要 matplotlib（Agg）。
缺 matplotlib 不伪造位图/PDF。除已知装置图元外不做无来源仪器象形图；接口是声明+几何，
不模拟真实螺纹/密封面/力学装配；不拟合数据、不评判实验方案是否合理、不做论文排版。

## 真实验证

```bash
python -X utf8 "$SKILL/scripts/bench_sourcebind.py" --mode apparatus
python -X utf8 "$SKILL/scripts/bench_apparatus_routes.py"
python -X utf8 "$SKILL/scripts/bench_apparatus.py"
python -X utf8 "$SKILL/scripts/bench_apparatus2.py"
python -X utf8 "$SKILL/scripts/bench_pathway.py"
python -X utf8 "$SKILL/scripts/bench_pathway2.py"
python -X utf8 "$SKILL/scripts/bench_schematic.py"
```

- sourcebind clean/敌意/契约/fresh-case-id/编辑/重跑：**27/27**（`report_sourcebind.json`）。
- 装置与路线专项：**18/18**（`report_apparatus_routes.json`）。真实覆盖四介质、
  泵/阀/检测器/sink、命名端口、S01–S05、绕开废液部件、回流、里程碑、decision 分支、
  route 无入口/出口、stage 错号/重号、缺件、未知 flow、孤立件与循环重跑。
- 旧回归：**11+9+11+10+8 = 49/49**。
- 另打开真实四介质+回流示例 PNG 复看：截断回流标签、圆形长标签溢出、图例色样/线型和
  泵符号遮字均已实际修复并复看通过；没有见过或用此代替平台私有案例。

测试全部用临时目录和 EXAMPLE-ONLY 合成材料，不携带正式答案。

## 方法参考

GitHub `cdelker/schemdraw/docs/usage/placement.rst` 的 `anchors / at / anchor / hold / drop`
用于命名端口与连接状态；GitHub `d3/d3-force`、`d3/d3/docs/d3-force/{simulation,collide}.md`
用于固定顺序碰撞松弛；本地 `p3i04` 的 parts/connections/steps→SVG 回查用于来源绑定。
这些是方法来源，不是运行依赖，也不需要联网或安装 schemdraw/d3。
