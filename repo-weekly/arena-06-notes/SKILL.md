---
name: structuring-literature-notes
description: >-
  把真实科研论文转成结构化、可核验、可复用的中文笔记。当任务要求读取 /input 中的固定科研材料
  （论文 PDF/文本）并依据 /input/case.json 的 output_contract 完成文献总结、论文卡片、章节摘要、
  知识点提取或来源回链时使用。产出：与论文章节对齐的结构化笔记（研究问题/方法/数据/结果/局限/
  证据锚点/可复用要素）、三级分层摘要、论断→证据映射表、多篇横向对比矩阵、materials_register.md
  与符合契约的 result.json。核心能力：每条关键结论带页码/章节/段落/图表级锚点，未报告与不确定项
  显式标注，机器可校验的字段完整性与锚点检查。
---

# 文献总结与结构化笔记

## 1. 用途与触发

把一篇（或多篇）真实论文变成**对得上、留得住、找得回、用得上**的结构化笔记：
骨架跟随论文自身章节而非通用摘要模板；研究问题/数据/方法条件/发现/局限全部落字段；
每条关键结论可回链到原文位置；笔记可检索、可比较、可继续加工。

**触发**：任务给出一篇或多篇科研论文（PDF 或文本），要求文献总结、结构化笔记、论文卡片、
章节摘要、知识点提取、证据定位或阅读问答。

**不应触发的邻近场景**：
- 要求生成新的综述、研究计划或论文初稿（那是写作任务，不是阅读笔记）；
- 要求把结论拆成原子断言并导出 RDF/Nanopublication（用 authoring-nanopublications）。

## 2. 运行环境契约

- Skill 安装在 `/skills/weekly-skill`；输入在 `/input/`（`case.json`、`task.md`、论文材料）。
- **第 0 步必须读 `/input/case.json`**，提取 `case_id` 与 `output_contract`；
  最终 `/app/output/result.json` 必须包含 `case_id` 和 `output_contract` 声明的全部原始字段，
  字段名以 case.json 为准，不臆造。
- 工作文件放 `/app/work/`；交付放 `/app/output/`：`notes.md`（主产物）、
  `evidence_map.md`（来源与论断映射）、`result.json`（诚实 status/sources/uncertainty/change_log）。
- 预算 64 次请求 / 900 秒 / 单次 16384 token。**先尽早落盘一份诚实的部分结果，再迭代改进**。
- 禁止预制答案、编造原文没有的数据；无法判断就写"无法判断"并给原因。
- 脚本只用 Python 标准库；环境另有 pdftotext、OCR 等工具（以 environment/resources.yaml 为准）。

**验证与限制声明（v2）**：本 Skill 的脚本与流程仅在本地**合成 fixture**
（examples/，全部虚构数据）上做过验证；平台的 3 个隐藏案例与对照基线
**未在本地运行**，本 Skill 不声称任何平台分数。交付时同样遵守该诚实原则：
脚本报 PASS 只代表确定性检查通过，不代表内容科学正确。

## 3. 脚本调用规则

一律用**绝对路径**调用，路径用正斜杠，不依赖 CWD：

```
python3 /skills/weekly-skill/scripts/inventory.py /input --out /app/work/materials_register.md
python3 /skills/weekly-skill/scripts/notes_check.py --notes /app/output/notes.md \
    --register /app/work/materials_register.md \
    [--section-map /app/work/section_map.md]
python3 /skills/weekly-skill/scripts/contract_check.py \
    --case /input/case.json --draft /app/work/result_draft.json
python3 /skills/weekly-skill/scripts/selfcheck.py --out /app/output \
    --case /input/case.json --register /app/work/materials_register.md
```

v2 新增：notes_check.py 支持 `--section-map`（章节完整性比对，WARN 级）；
contract_check.py 对 result.json 草稿做 output_contract 字段核对
（v3 起为建议性自查：核对用于定位问题，任何退出码都不阻塞落盘交付）。
两脚本的新增检查均为 WARN 级：不把 v1 能通过的草稿
误判 FAIL（校验器校准纪律）；负路径自测见 examples/negative_cases.md。

**降级声明**：若脚本缺失或运行失败，改为手工执行同等检查（对照
references/element_checklist.md 逐条勾选），并在 result.json 的 change_log 中记录"脚本降级为人工核查"。

## 4. 主流程

**交付优先原则（v3，最高优先级，先于下列一切步骤）**：
- (a) 任何时刻 `/app/output/` 里都要有一份**当前最好的可交付物**：先完成再完美，
  每完成一个阶段就用当前版本更新交付物，绝不把"全部做好"当作落盘前提。
- (b) 请求预算分配建议：≤10 次读材料与契约，≤30 次产出主产物（notes.md 与
  evidence_map.md），≤10 次校验与修复，其余请求与时间余量全部留给 finalize 与交付固化。
- (c) 预算过半仍无落盘初稿 → 立即停止打磨，把当前版本落盘；剩余约 10 次请求 →
  停止一切修复与校验循环，直接 finalize 交付。
- (d) 每个校验脚本最多运行 2 次（首次检查 + 修复后复查一次）；两轮之后无论结果
  如何都进入交付：剩余 FAIL 逐项写入 result.json 的 uncertainty 与 skipped_reason，
  照常落盘。校验是建议性的自查，任何脚本退出码都不阻止交付。

**第 0 步｜解析契约**：读 `/input/case.json` 与 `/input/task.md`，把 `case_id`、
`output_contract` 字段清单、问题边界抄入 `/app/work/contract_notes.md`。
产出：contract_notes.md。

**第 1 步｜材料清点**：运行 inventory.py 生成 `/app/work/materials_register.md`，
全部材料编号 S1..Sn；扫描件/加密件在此步识别并记降级方案。
产出：materials_register.md（机器可校验）。

**第 2 步｜章节结构对齐**：通读主论文，抽取其**实际章节骨架**（含编号与起始页），
写成 `/app/work/section_map.md`；笔记骨架必须复用该章节顺序，禁止套通用 IMRaD 模板
顶替真实结构。同时登记图/表清单（图1..n、表1..n 及其页码）。
产出：section_map.md。

**第 3 步｜字段化笔记+分层摘要**：按 templates/note_skeleton.md 填 `/app/output/notes.md`：
三级摘要（一句话/一段/详细）→ 字段区（研究问题、方法与条件、数据与材料、主要结果、
局限与适用边界、未报告与不确定项、可复用要素）→ 章节摘要（每节 2-5 条，保留节间承接）。
每个字段条目带锚点 `[S# p.页 §节 ¶段]` 或 `[S# fig.图号]`/`[S# 表号]`；原文没有的内容
写"未报告"，不写"无"。
**v2 锚点升级**：关键论断优先用"页+章节+行区间"复合定位
（如 `[S1 p.3 §3.1 L12-15]`，L 编号指抽取文本中的稳定行区间），并优先使用
章节号/图表号等**稳定原文定位符**（重排页面后仍能找到）；详见
references/method_rules.md §3。
产出：notes.md 初稿（尽早落盘，后续迭代）。

**第 4 步｜论断→证据映射**：把主要结果/结论中的关键论断逐条列入
`/app/output/evidence_map.md`（用 templates/evidence_map_template.md）：
每条论断给原文引文（≤30 字）、锚点、证据类型（直接数据/图表/推论）、核验状态。
产出：evidence_map.md。

**第 5 步｜多篇横向对比（多篇案例必做）**：两篇及以上文献时，按
templates/comparison_matrix_template.md 生成 `/app/output/comparison_matrix.md`，
行是要素（问题/数据/方法条件/指标/结论/局限），列是各文献，每格带锚点；
分歧与互补关系单独成节。单篇案例跳过并在 result.json 注明。
产出：comparison_matrix.md（可选）。

**第 6 步｜自查与交付（建议性校验，不阻塞交付）**：运行 notes_check.py，
FAIL 项能修则修一轮并复查一次（本脚本最多两轮），修不完的逐项记入
uncertainty/skipped_reason；把 result.json 草稿写到
`/app/work/result_draft.json`，运行 contract_check.py 核对 output_contract
字段齐全，缺字段能补则补一轮、补不齐记入 uncertainty，然后**照常落盘**
`/app/output/result.json`，最后跑 selfcheck.py（同样最多两轮）。
（case_id、契约字段、status、sources、uncertainty、change_log）。
任何脚本退出码都不阻止交付。
**交付韧性（v2）**：无论哪一步失败，finalize 都必须导出可交付物——
已完成的诚实部分照常交付，未完成阶段在 result.json 的 `skipped_reason`
中逐条说明（阶段名+原因+人工接管位置），而非整案失败、不交任何东西。
产出：result.json。

## 5. 自查清单（不阻塞交付）

交付前对照 references/element_checklist.md 逐条勾选（它把评分维度转成了可勾选项；
这是质量自查清单而非门禁：勾选不完的项记入 result.json 的 uncertainty，不阻止交付），
建议达标项：
- 笔记章节顺序与论文实际章节一致，不是通篇压缩摘要；
- 研究问题/数据/方法条件/结果/局限六要素全部有字段且有内容或显式"未报告"；
- 每条关键论断有带定位的锚点，锚点编号在登记表中；
- 未报告、无法判断、材料冲突三类事项分别列出，没有写成事实；
- result.json 字段与 case.json 的 output_contract 完全一致。

## 6. 反馈回路

1. 运行 notes_check.py：FAIL 逐条修复一轮（缺章节补章节、锚点补定位、映射补锚点）
   后复查一次；v2 的 WARN 项（章节完整性、复合定位）尽量顺手修，不阻塞交付。
2. 写 result.json 草稿到 /app/work/ 后运行 contract_check.py：FAIL 能补则补一轮
   契约字段，补不齐的记入 uncertainty/skipped_reason，然后**照常落盘
   /app/output/result.json**（核对是建议性的，不阻塞交付）。
3. 运行 selfcheck.py：FAIL 逐条修复一轮（补产物、补契约字段、改诚实 status）后复查一次。
4. 每个脚本最多两轮（检查 → 修一轮 → 复查），两轮后无论结果如何都进入交付，
   不再重跑全部脚本；
5. 两轮后仍有 FAIL 的项：status 改 partial，在 uncertainty 中说明具体缺口与人工接管
   位置，被跳过的阶段写入 skipped_reason（finalize 永远导出可交付物）。
validate → fix → deliver，每轮把改动记入 change_log。

## 7. 异常处理

- **扫描件/无文本层 PDF**：inventory.py 会标出；走 OCR；OCR 不可用时相关字段记
  "未报告（材料不可读）"，status=partial。
- **双栏错序/图表公式缺失**：以章节标题与图表编号为锚重新排序；读不出的图表在
  不确定项中声明"图N内容未能解析"，不得编造图中数值。
- **材料冲突**（如正文与附录数据不一致）：两处锚点都记录，写入"材料冲突"清单，
  不擅自取其一。
- **非中文论文**：笔记正文用中文，术语保留英文原词并给中文译名；引文保留原文。
- **超长文/预算不足**：先保 notes.md 字段区与证据映射（核心交付），章节摘要可降粒度，
  status=partial 并说明覆盖比例。
- **case.json 缺失或损坏**：能读 task.md 就按题面通用契约交付，status=partial，
  uncertainty 中说明契约未能解析。
- **finalize 韧性（v2）**：任何阶段失败都不允许"零交付"。已生成的 notes.md /
  evidence_map.md / comparison_matrix.md 按现状交付；未完成阶段写入
  result.json 的 `skipped_reason`（如
  `[{"stage": "comparison_matrix", "reason": "预算耗尽，仅完成 S1 笔记"}]`），
  status=partial。只有连材料登记都完成不了时才 status=failed，仍须交付
  materials_register.md 与说明。

## 8. 资源索引

- `references/element_checklist.md`：要素齐全性清单与评分锚点，自查清单依据（不阻塞交付）。
- `references/method_rules.md`：章节对齐、字段判定、锚点格式、未报告标注的判定标准与反模式。
- `references/style_guide.md`：笔记文体、术语、锚点书写规范。
- `references/failure_modes.md`：基础 Agent 在本题的典型失败模式与对策。
- `templates/note_skeleton.md`：notes.md 章节级骨架（含占位说明与字段字典）。
- `templates/comparison_matrix_template.md`：多篇文献横向对比矩阵骨架。
- `templates/evidence_map_template.md`：材料登记+论断映射+修改记录+待确认项模板。
- `templates/result_json_template.md`：result.json 透传规则与示意 JSON。
- `examples/minimal_example.md`：最小调用示例（示意，非正式案例结果）。
- `examples/synthetic_case.md`：全合成小案例（输入→中间产物→输出片段）。
- `examples/negative_cases.md`：负路径自测（必须被拒绝的用例与实测输出，v2）。
- `examples/fixtures/`：负路径合成 fixture（未登记来源笔记、缺契约字段草稿、
  单来源登记表）。
- `scripts/inventory.py`：材料清点与文本层可读性探测，生成 S1..Sn 登记表。
- `scripts/notes_check.py`：笔记字段完整性与证据锚点检查（本题专用）；
  v2 增 --section-map 章节完整性与复合定位建议（WARN 级）。
- `scripts/contract_check.py`：契约字段核对——对 result.json 草稿核对
  output_contract 字段齐全（v2 新增；v3 起为建议性核对，不阻塞落盘交付）。
- `scripts/selfcheck.py`：交付自查（产物齐全、result.json 契约、来源标记登记）；
  v2 增 skipped_reason 建议（WARN 级）。
