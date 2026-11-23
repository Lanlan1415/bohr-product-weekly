---
name: authoring-nanopublications
description: >-
  从真实科研论文中抽取原子化科学断言并发布为可机器读取的 Nanopublication（RDF TriG/Turtle）。
  当任务要求读取 /input 中的固定科研材料、依据 /input/case.json 的 output_contract 完成断言拆解、
  证据绑定、来源元数据记录或结构化 RDF 导出时使用。产出：断言登记表（assertion_table.md）、
  符合 Nanopublication 三部结构（assertion/provenance/publicationInfo）的 TriG 文件、
  证据映射 evidence_map.md 与符合契约的 result.json。核心能力：每条断言单一可判真假且带条件限定、
  最小充分证据片段回链页码/图表、DOI/ORCID 等来源元数据可解析、不确定断言带受控置信度标注、
  stdlib 实现的 Turtle/TriG 语法与三部结构机器校验。
---

# Nanopublication 创作

## 1. 用途与触发

把论文中的关键结论**拆得细**（一条断言一个可判真假的命题）、**对得上**
（每条断言挂最小充分证据片段与原文位置）、**追得回**（断言-证据-论文-作者-
年份-版本链路完整）、**读得懂**（导出 TriG/Turtle 可被下游程序直接解析）。

**触发**：任务给出科研论文，要求抽取科学断言、构建知识单元、绑定证据与来源、
或导出 Nanopublication / RDF 三元组结构。

**不应触发的邻近场景**：
- 只要求中文阅读笔记/章节摘要而不需要 RDF 导出（用 structuring-literature-notes）；
- 要求大批量文献计量统计（那是计量分析任务，不是原子断言构建）。

## 2. 运行环境契约

- Skill 安装在 `/skills/weekly-skill`；输入在 `/input/`（`case.json`、`task.md`、论文材料）。
- **第 0 步必须读 `/input/case.json`**，提取 `case_id` 与 `output_contract`；
  最终 `/app/output/result.json` 必须包含 `case_id` 和 `output_contract` 声明的
  全部原始字段，字段名以 case.json 为准，不臆造。
- 工作文件放 `/app/work/`；交付放 `/app/output/`：`nanopubs.trig`（主产物，
  全部断言的 nanopub 集合）、`assertion_table.md`（断言登记表）、
  `evidence_map.md`（证据与来源映射）、`result.json`。
- 预算 64 次请求 / 900 秒 / 单次 16384 token。**先尽早落盘一份诚实的部分结果
  （哪怕只有 2-3 条通过校验的 nanopub），再迭代增补**。
- 禁止预制答案、编造论文没有的断言或来源标识符；无法核验的断言不得包装成事实。
- 脚本只用 Python 标准库，不访问网络；IRI 仅作标识符书写，不做联网解析。

**验证与限制声明（v2）**：本 Skill 的脚本与流程仅在本地**合成 fixture**
（examples/，全部虚构数据）上做过验证；平台的 3 个隐藏案例与对照基线
**未在本地运行**，本 Skill 不声称任何平台分数。脚本报 PASS 只代表语法与
结构等确定性检查通过，不代表断言内容科学正确。

## 3. 脚本调用规则

一律用**绝对路径**调用，路径用正斜杠，不依赖 CWD：

```
python3 /skills/weekly-skill/scripts/inventory.py /input --out /app/work/materials_register.md
python3 /skills/weekly-skill/scripts/nanopub_check.py /app/output/nanopubs.trig
python3 /skills/weekly-skill/scripts/contract_check.py \
    --case /input/case.json --draft /app/work/result_draft.json
python3 /skills/weekly-skill/scripts/selfcheck.py --out /app/output \
    --case /input/case.json --main nanopubs.trig
```

v2 新增：nanopub_check.py 的 N4（证据挂接）/N5（置信度）/N6（条件范围与
证据形式）增强检查均为 WARN 级，不把 v1 能通过的稿件误判 FAIL
（校验器校准纪律）；contract_check.py 在写入 result.json **之前**核对
output_contract 字段（verify-then-write）；负路径自测见
examples/negative_cases.md。

**降级声明**：若脚本缺失或运行失败，改为手工执行同等检查（对照
references/element_checklist.md：前缀声明、句点结尾、三部结构、assertion 非空
逐条人工核对），并在 result.json 的 change_log 中记录"脚本降级为人工核查"。

## 4. 主流程

**交付优先原则（v3，最高优先级）**：
- (a) 任何时刻 `/app/output/` 里都要有一份当前最好的可交付物——先完成再完美，
  先落盘、后迭代，绝不留空输出目录；
- (b) 请求预算分配建议：≤10 次读材料与契约、≤30 次主产物（断言表/证据映射/
  nanopub 生成）、≤10 次校验修复、剩余全部留给 finalize 与 result.json 落盘；
- (c) 预算过半仍未落盘初稿 → 立即把当前版本落盘到 `/app/output/`；
  剩余约 10 次请求 → 停止一切修复，直接 finalize 交付；
- (d) 每个校验脚本最多运行 2 次（首次检查 + 修复后复查一次），之后无论结果
  如何都进入交付；脚本退出码仅供定位问题，不阻止交付。

**第 0 步｜解析契约**：读 `/input/case.json` 与 `/input/task.md`，把 `case_id`、
`output_contract` 字段清单、任务指定的证据范围抄入 `/app/work/contract_notes.md`。

**第 1 步｜材料清点**：运行 inventory.py 生成 `/app/work/materials_register.md`，
材料编号 S1..Sn；登记论文的 DOI/标题/作者/年份（在材料内找，不臆造，缺则标"未报告"）。

**第 2 步｜结论定位**：通读论文，定位含关键结论的段落/图表（摘要末段、结果节、
讨论节的论断句），写 `/app/work/claim_spots.md`：每处给候选论断原文句 + 锚点。

**第 3 步｜断言拆解**：按 references/method_rules.md 的粒度判据，把候选结论拆成
**原子断言**写入 `/app/output/assertion_table.md`（用
templates/assertion_table_template.md）：每条含 id、自然语言陈述（含条件限定）、
主体/关系/客体三元组草案、证据锚点、证据类型（直接/间接/作者声明）、
置信度（high/medium/low + 依据）。复合句必须拆开；并列条件并入每条断言的限定。
**v2 保守追加两个字段**（不动原有流程与字段）：
- **条件范围**：该断言生效的适用条件/边界（温度、浓度、体系、数据集版本……），
  无条件时写明"无条件（原因）"；
- **证据形式**：证据的形态分类——实验数据/计算结果/引用支持/作者声明，
  与原"证据类型（直接/间接/作者声明）"正交并存，不互相替代。
产出：assertion_table.md（机器可核对的中间文件）。

**第 4 步｜证据绑定**：为每条断言在 `/app/output/evidence_map.md` 登记最小充分
证据片段（原文引文 ≤30 字 + 锚点 [S# p.页 §节/图/表]），标注直接证据还是间接推论；
证据跨图表时两段锚点都记。找不到支撑片段的断言：标"证据不足"，降级为 low 置信度
或移出交付清单，不得硬挂无关证据。

**第 5 步｜生成 nanopub**：按 templates/nanopub_template.trig 的骨架为每条断言
生成一个 nanopub，合并写入 `/app/output/nanopubs.trig`：
- assertion 图：主体-关系-客体三元组 + 条件限定，词表优先用领域本体，
  无合适本体时用案例命名空间并保持一致；
- provenance 图：`prov:wasDerivedFrom` 挂论文 DOI/来源 IRI，
  `ex:hasEvidenceAnchor` 挂证据锚点串，`ex:evidenceType` 标证据类型；
  v2 可选增强（建议）：`ex:conditionScope` 标断言生效的条件范围，
  `ex:evidenceForm` 标证据形式（ex:ExperimentalData /
  ex:ComputationalResult / ex:CitationSupport / ex:AuthorStatement）；
- pubInfo 图：`pav:createdBy`（作者 ORCID 或标注"未报告"）、`dcterms:created`、
  许可、置信度（受控词表 high/medium/low）与置信度依据。
产出：nanopubs.trig（每条断言生成后立即跑校验，先小后多）。

**第 6 步｜自查与交付（建议性校验，照常落盘）**：运行 nanopub_check.py
做一轮自查，FAIL 项能修则修一轮；修不完的逐项写入 result.json 的
`uncertainty` 与 `skipped_reason`，然后照常交付。先把 result.json 草稿写到
`/app/work/result_draft.json`，运行 contract_check.py 核对 output_contract
字段（建议性自查：缺字段补 null + uncertainty 说明），**无论校验结果如何**
都把 `/app/output/result.json` 落盘，最后跑 selfcheck.py 记录自查结论。
任何脚本退出码都不阻止交付；质量门是自查清单而非门禁。
**交付韧性（v2）**：无论哪一步失败，finalize 都必须导出可交付物——
已通过校验的 nanopub 照常交付（少而合规优于多而错），未完成阶段在
result.json 的 `skipped_reason` 中逐条说明（阶段名+原因+人工接管位置），
而非整案失败、不交任何东西。

## 5. 质量门（自查清单，不阻塞交付）

交付前对照 references/element_checklist.md 逐条自查——这是自查清单而非门禁，
任何一项未达标都不阻止落盘交付，未达标项记入 uncertainty/skipped_reason：
- 每条断言单独可判真假，没有"整段话塞进一个字段"的断言；
- 每条断言的 assertion 图非空、带条件限定（无条件的断言要能说清为什么无条件）；
- 每条 nanopub 三部结构齐全，provenance 挂到真实来源标识符或标"未报告"；
- nanopub_check.py 通过：前缀闭合、句点结尾、四图齐全、assertion 非空；
- 不确定断言有置信度标注，证据不足的断言不被写成事实；
- result.json 字段与 case.json 的 output_contract 完全一致。

## 6. 反馈回路

每个脚本最多两轮（检查 → 修一轮 → 复查）；两轮后仍有 FAIL：记入
uncertainty/skipped_reason，立即交付。脚本退出码仅供定位问题，不作为交付门禁。
1. 运行 nanopub_check.py：FAIL 项修一轮（补前缀、补句点、补图、补三元组），
   复查一次后无论结果进入交付；v2 的 N4/N5/N6 WARN 项尽量顺手修，不阻塞交付。
2. 写 result.json 草稿到 /app/work/ 后运行 contract_check.py：FAIL 项补一轮
   契约字段（做不到的填 null + uncertainty 说明），无论结果都落
   /app/output/result.json。
3. 运行 selfcheck.py：FAIL 项补一轮（补产物、补契约字段、改诚实 status），
   之后照常交付。
4. 不整案重跑全部脚本；两轮后仍 FAIL 或预算将尽：status 改 partial，
   uncertainty 中说明缺口与人工接管位置，被跳过的阶段写入 skipped_reason
   （finalize 永远导出可交付物）。
validate → fix → record → deliver；每轮改动记入 change_log。

## 7. 异常处理

- **扫描件/无文本层 PDF**：inventory.py 标出；走 OCR；仍不可读的材料不得生成
  nanopub，在 assertion_table.md 标「材料不可读」，status=partial。
- **断言找不到支撑片段**：不硬挂证据；标"证据不足"+ low 置信度，或移出交付并
  在 uncertainty 说明。
- **断言与证据冲突**（正文与图表数值不一致）：两处锚点都记录，断言拆成两条
  分别挂证据，或标"材料冲突"后都不发；不擅自取其一。
- **证据跨图表**：provenance 中并列多个 ex:hasEvidenceAnchor，断言文本注明
  "综合图N与表M"。
- **DOI/ORCID 等材料内缺失**：写"未报告"，禁止编造标识符。
- **字段缺失/契约不明**：保留契约字段名、值给 null，uncertainty 说明。
- **预算不足**：立即停止修复与扩充，已生成 nanopub 按现状落盘交付（未通过
  校验的项记入 uncertainty/skipped_reason），未拆完的候选结论列入
  assertion_table.md 待确认区，status=partial。
- **finalize 韧性（v2）**：任何阶段失败都不允许"零交付"。已生成的
  nanopubs.trig / assertion_table.md / evidence_map.md 按现状交付；
  未完成阶段写入 result.json 的 `skipped_reason`（如
  `[{"stage": "nanopub_generation", "reason": "A6-A8 证据不足，仅发布 A1-A5"}]`）。
  只有连材料登记都完成不了时才 status=failed，仍须交付登记表与说明。

## 8. 资源索引

- `references/element_checklist.md`：断言/证据/来源/导出四维度要素清单与评分锚点。
- `references/method_rules.md`：断言粒度判据、证据最小充分性、关系类型映射、
  置信度标注规则与反模式。
- `references/style_guide.md`：Turtle/TriG 书写规范、命名空间与 IRI 规范、断言文本风格。
- `references/failure_modes.md`：基础 Agent 在本题的典型失败模式与对策。
- `templates/nanopub_template.trig`：语法正确、可直接通过校验的完整 TriG 示例。
- `templates/assertion_table_template.md`：断言登记表骨架（拆解中间产物）。
- `templates/evidence_map_template.md`：材料登记+证据绑定+修改记录+待确认项模板。
- `templates/result_json_template.md`：result.json 透传规则与示意 JSON。
- `examples/minimal_example.md`：最小调用示例（示意，非正式案例结果）。
- `examples/synthetic_case.md`：全合成小案例（论文片段→断言表→TriG→result.json）。
- `examples/negative_cases.md`：负路径自测（必须被拒绝的用例与实测输出，v2）。
- `examples/fixtures/`：负路径合成 fixture（无证据断言 TriG、缺契约字段草稿）。
- `scripts/inventory.py`：材料清点与文本层可读性探测，生成 S1..Sn 登记表。
- `scripts/nanopub_check.py`：stdlib 实现的 Turtle/TriG 语法与三部结构校验
  （本题专用）；v2 增 N4 证据挂接 / N5 置信度 / N6 条件范围与证据形式（WARN 级）。
- `scripts/contract_check.py`：契约前置校验——写入 result.json 前核对
  output_contract 字段齐全（verify-then-write，v2 新增）。
- `scripts/selfcheck.py`：交付自查（RDF 产物、result.json 契约、诚实字段）；
  v2 增 skipped_reason 建议（WARN 级）。
