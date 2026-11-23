---
name: pathway-figure
description: >
  Generate and edit biologically meaningful mechanism/pathway figures (生物机制图、信号通路、
  多区室调控图) from source-bound entities and interactions. Emits real editable layered SVG,
  300 dpi PNG and vector PDF, with gene/protein naming and registry checks, aliases, molecular
  states, compartment geometry, direction/feedback, eight arrow semantics, confidence line styles,
  colour/size/legend consistency and source-to-geometry mapping. Includes source-preserving SVG
  edits and strict case_id/output_contract passthrough. Not for invented pathways, decorative
  cell art, statistical inference or unsupported database claims.
---

# Biological mechanism and pathway sourcebind

主入口为 `scripts/sourcebind.py --mode pathway`，真实生成和编辑图稿；旧 `pathway.py`
保留兼容与回归测试，不是新案例的主工作流。每个节点和每条边是机制陈述，不是装饰。

## 六步运行时工作流

1. **读材料。** 读 `/input/case.json`、`/input/task.md`、实际正文/原始生物材料及既有图稿。
   提取 `case_id`、`output_contract` 和页/段/图号/材料版本。Figure03 等修订所指定的主生物
   来源必须实际读取；不可从北京赛题标签、包的示例或记忆中的常见通路补基因、关系、registry ID。
2. **建立机制中间表示 `/app/work/spec.json`。** 把实体、关系、区室、反馈和数据编码分别列清：
   - `materials[]`：材料 id、`name`、`source`/`quote`、`version`；节点 `evidence` 指向 id；
   - `nodes[]`：`id/label/kind/evidence/layer/compartment`，适当时加 `species`、
     `accession/accession_source`、`aliases`、`state_distinct/state`；
   - `connections[]`：来源明确写出的 `from/to/type/source`，缺 type 时只能核对端点，
     在 uncertainty 登记不可判定的关系类型；
   - `edges[]`：实际要画的对应边；额外包含 `confidence`、`feedback:true` 以表达明确声明；
   - `compartments[]`：来源/任务声明的区室带及合法 layers；`categories`、`legend`、
     `legend_notes` 记录数据映射含义。
3. **真实生成：**

   ```bash
   python -X utf8 "$SKILL/scripts/sourcebind.py" \
     --mode pathway --spec /app/work/spec.json \
     --case /input/case.json --meta /app/work/meta.json \
     --checklist /app/work/checklist.json --out /app/output
   ```

   `--meta/--checklist` 可选；无 case 文件时可传 `--case-id`。meta 可含
   `sources/uncertainty/limits`。checklist 为 `entities[{id}]`、`relations[{from,to}]`。
   case 若已显式内嵌 `spec.nodes` 可以只给 `--case`；自由文本机制材料仍由 Agent 先抽取，
   脚本不会用领域词猜测通路。无抽取 spec 时 exit 5。
4. **保存真实交付。** `/app/output` 应有 `figure.svg`、`figure.png`、`figure.pdf`、
   `mapping.json`、`spec.json`、`result.json`。SVG 中 `layer-compartments`、
   `layer-nodes`、`layer-edges`、`layer-legend` 可独立编辑；文字保持 `<text>/<tspan>`。
5. **读结果并修来源/spec。** `0=clean`、`3=review`、`4=blocked`、`5=undetermined`。
   blocked 不允许交付为正确机制图；修复 `nomenclature.*`、`trace.*`、`compartment.*`、
   `layout.*`、mapping 或 evidence，而不是删除检查、改箭头颜色掩盖冲突。
6. **重跑并复核。** 相同命令/输出路径下六个文件全部字节一致。另用 mapping/XML 比对实体、
   from/to 方向、marker、端口和 bbox；未实际打开图时 `visual_check` 为 `not performed`，
   不声称做过视觉判断。生物学意义最终仍由 Agent/native LLM judge 根据原材料判断。

## 最小机制 spec（EXAMPLE ONLY）

```json
{
  "case_id":"example-pathway",
  "species":"human",
  "aliases":{"TP53":["p53"]},
  "materials":[
    {"id":"m1","name":"TP53","source":"EXAMPLE Results ¶2","version":"v1"},
    {"id":"m2","name":"MDM2","source":"EXAMPLE Results ¶2: TP53 activates MDM2","version":"v1"}
  ],
  "connections":[{"from":"g1","to":"p1","type":"activate",
                  "source":"EXAMPLE Results ¶2: TP53 activates MDM2","confidence":"confirmed"}],
  "compartments":[
    {"id":"cytosol","label":"细胞质","layers":[0]},
    {"id":"nucleus","label":"细胞核","layers":[1]}
  ],
  "nodes":[
    {"id":"g1","label":"TP53","kind":"gene","evidence":"m1","layer":0,
     "compartment":"cytosol","accession":"HGNC:11998","accession_source":"hgnc"},
    {"id":"p1","label":"MDM2","kind":"protein","evidence":"m2","layer":1,
     "compartment":"nucleus","accession":"Q00987","accession_source":"uniprot"}
  ],
  "edges":[{"id":"r1","from":"g1","to":"p1","type":"activate","confidence":"confirmed"}],
  "categories":{"gene":"#56B4E9","protein":"#009E73"},
  "legend_notes":["箭头方向 = 来源声明的上下游；区室 = 材料声明"]
}
```

- `kind=gene` 规范基因书写并在 SVG 实际设置 italic；`kind=protein` 要求 roman。
- `accession_source` 支持 hgnc/uniprot/ensembl/ncbi_gene/chebi。acc/aliases 必须来自实际
  来源或用户可核验的权威映射，不能为了消警告而乱填。缺 acc 会如实 review。
- 同一 registry accession 默认是同一 actor；真正的翻译后状态须在**两个节点**都声明
  `state_distinct:true` 和不同 `state`，否则 `nomenclature.accession_collision`。
- `compartments` 是声明的约束，不是自动生物知识。无显式 layer 的节点被放入声明 band；
  显式 layer 矛盾时 `compartment.mismatch=high`。

## 图形语义与数据编码（真实上屏并回读）

| spec 语义 | 实际连接/标签 |
|-|-|
| `activate` | 蓝色三角箭头 |
| `inhibit` | 红色 T-bar；逆向调控必须有 `feedback:true` |
| `bind` | 绿色虚线 + 圆点，无方向箭头；方向不明时不得擅自改成 activate |
| `flow` | 灰色方向箭头；回流/反馈必须显式声明 |
| `phosphorylate` | 紫色箭头 + P |
| `ubiquitinate` | 橙色箭头 + Ub |
| `recruit` | 绿色箭头 + recruit |
| `transport` | 浅蓝箭头 + transport |
| `confirmed/predicted/hypothetical` | 实线 / 虚线 / 点线，置信度图例自动上屏 |
| 未知类型 | blocked；可见 UNRESOLVED + 菱形端点，绝不默认画 flow |

`connections[].type` 与 `edges[].type` 做双向来源核对。少画来源连接、增加来源没有连接、
把来源 inhibit 画成 activate 都是 high。反向 `from/to` 不会自动帮你翻回；几何从当前
source/target bbox 重新计算到端口，独立 XML 审计会比较实际坐标。长距离 feedback/recycle
使用预留上方走廊的三次贝塞尔 route，mapping 存下完整曲线 d/control_y；普通直线还会用
Liang–Barsky 相交检查拦截穿越第三方节点的连接。

`size` 是连续数据通道：线性尺寸按 `sqrt(size)` 缩放**一次**，因此 size=4 对应面积比 4；
mapping 同时保留原 size 和实际 bbox。`legend_required:true` 且 size 变化时，需在
`legend_notes` 说明含义。类别颜色与节点显式颜色冲突、同类别多色、未声明类别、必需图例
漏实体、phantom legend、size 无解释均产生对应 finding。长标签按字宽换行，保留 value/unit。

## 区室、分支与反馈布局

区室背景同步进入 SVG/PNG/PDF；节点 bbox 与 layer 由 mapping 记录。布局采用固定顺序的矩形
碰撞松弛（最多 80 轮，无随机源），借鉴 d3-force 的 bounded collision/静态固定步数思想；
未解决的重叠、跨出画布会报 high，不缩成不可读文字。自动端口通过源/目标真实 bbox 求得；
`from_port/to_port` 可用 schemdraw 风格 `start/end/in/out` 或 `N/E/S/W`。复杂分支、反馈和
多区室不是把名词排成一圈，而是按显式 layer/compartment 约束布局。任意极密反馈网络仍可能
需要人工分区；此时交付 blocked/partial，不承诺自动完成科学归纳。

## Source-preserving SVG 编辑

```bash
python -X utf8 "$SKILL/scripts/sourcebind.py" \
  --edit-svg /input/figure.svg --edits /app/work/edits.json \
  --case /input/case.json --out /app/output
```

支持 `rename`、`recolour`、`set_relation_type`，例如
`{"op":"set_relation_type","target_id":"r1","new_type":"inhibit"}`。target 必须精确匹配
id/node/edge，失败 exit 5。关系变更同步实际 marker 和 data-type，并补 defs；rename 保留
独立 value/unit；无关节点、区室和图例 XML 保留。随后**必须同步 spec/connections 并重新
跑来源审计**，因为编辑工具不能把新机制自动证明为真。

可额外传 `--spec updated-spec.json` 在 `preview_from_spec/` 生成更新后 spec 的 PNG/PDF；
它不会被冒充为任意第三方 SVG 的逐像素预览。无兼容 SVG 栅格化路径时仍交付编辑后 SVG，
review + limits，不伪造预览或 `visual_check`。

## output_contract 与结果核验

同时支持平面字段映射和 schema 形态 `fields[] / required[]+properties{}`：

- 原始 `case_id` 原样回填；平面契约每个 key 都解析；schema 声明原样保存在
  `output_contract`，所请求字段的真实值在 `contract_field_values`，适合者同步顶层；
- 显式 `deliverable_svg` 等案例值不改写；运行动态字段写真实 svg/png/pdf path、exports、
  mapping、font/export check；无法推导的字段 `null + limits`；
- 有效 case/可读 spec 的声明在**异常/拒绝路径**也回填；坏 JSON 本身无法猜出其字段。

`exports[]` 给出格式/大小/magic/sha256；PNG 读 pHYs dpi；PDF 检查 `%PDF` 和 `/FontFile`；
`mapping.json` 给逐节点 label/value/unit/evidence/compartment/size/bbox 与逐边
from/to/type/confidence/feedback/start/end/source。`change_records`、`sources`、
`uncertainty` 和真实 `source_files` SHA-256 支撑独立复核。

## 退出码与降级

| 条件 | exit/状态 |
|-|-|
| clean 全套图稿 | 0 |
| 中低危发现；缺 matplotlib 或 PNG/PDF 渲染失败 | 3 review，SVG/mapping 保留，partial+limits |
| 来源/命名/方向/区室/重叠/未知关系等 high | 4 blocked，已有真实图保留 |
| 坏 JSON、非对象、无节点、非法 layer/canvas、无抽取 spec、编辑 target 不存在 | 5 undetermined，结构化 result |
| 输出目录不可写 | 5；目录里不能虚构 result，stdout 给结构化错误 |

缺 matplotlib 时不会生成假 PNG/PDF；标准库 SVG/mapping 链仍可用。旧 `pathway.py` 的依赖
和旧 result 行为只用于兼容，新案例请以本文件为准。

## 真实验证（本机计数）

```bash
python -X utf8 "$SKILL/scripts/bench_sourcebind.py" --mode pathway
python -X utf8 "$SKILL/scripts/bench_pathway_semantics.py"
python -X utf8 "$SKILL/scripts/bench_pathway.py"
python -X utf8 "$SKILL/scripts/bench_pathway2.py"
python -X utf8 "$SKILL/scripts/bench_schematic.py"
python -X utf8 "$SKILL/scripts/bench_apparatus2.py"
```

- sourcebind 通用/敌意/契约/编辑/fresh-output/重跑：**27/27**；报告 `scripts/report_sourcebind.json`。
- 生物专项：**12/12**；报告 `scripts/report_pathway_semantics.json`。覆盖六类调控和
  flow、分支反馈、size=4 面积比、反向端点、type 篡改、同义名和 accession 冲突、合法
  分子状态、confidence 缺失、类别冲突、size 图例缺失。
- 旧回归：**11+38+19+13 = 81/81**。发现项包括命名、来源、区室、重叠、非法导出、
  confidence、feedback、malformed、deterministic、case refusal/success contract。

测试均使用临时目录，不预置正式答案。另真实打开过一个多区室/多关系/长距离反馈示例 PNG，
发现反馈跨节点后已改为走廊弧线并复看通过；这不代表见过平台私有案例或做过其视觉验收。
其余自动化证据是 XML、几何、magic 和可重复运行检查。

## Dependencies、方法来源与限制

- Python 3.10+；SVG/XML/mapping 为标准库。PNG/PDF、字体度量需要 matplotlib；真实字体缺失或
  缺字形会阻塞，不用空白方框冒充成功。用户 site-packages 环境按命令使用 `python -X utf8`。
- GitHub 方法参考：`d3/d3-force` 与 `d3/d3/docs/d3-force/{simulation,collide}.md` 的
  固定步数和碰撞松弛；`cdelker/schemdraw/docs/usage/placement.rst` 的命名 anchor/端口。
  本地 `p3i03` 提供 verb→箭头、区室和同义名图形语义基线。这些是设计参考，不是运行依赖。
- `nomenclature.py` 做书写/冲突/格式检查，不在本地联网验证基因是否真实存在；aliases 只
  覆盖输入给出的映射；confidence 只验证声明并画线型，不判断文献证据等级是否恰当。
- 本包提供可核对的区室带、基因/蛋白文字风格、complex 双边框和 receptor 线分隔，不生成
  未经来源指定的细胞膜、蛋白结构或细胞 pictogram。需要 Bioicons/SciDraw 类资产时应由
  任务材料/已授权图元供给，不能百度百科式猜图。
- 不提供统计结论，不判断机制成立与否，不处理论文排版；只保证结构化科学声明与实际图形、
  几何、图例、来源、导出和重跑记录可逐项复核。
