---
name: reading-master
description: >
  文献阅读领域总课题（challenge-a028c71c）：文档解析、图表理解、内容理解、翻译、问答和知识提取，
  一个技能覆盖整条阅读流水线。把栅格图表读成带读数层级（calibrated / axis_fraction）的数字、把
  论文的结论与数值提取成可溯源的字段表、核验论断与证据的关系、回答带原文定位的问题、对照多篇
  文档的同名字段、审计翻译双语产物、审计证据驱动的引用写作。关键结果回到原文证据（页码/段落/
  字段/图表定位），未报告/无法判断/材料冲突明确说明而不是写成事实。Use when a reading task must
  produce checkable results — extraction tables, verified claims, anchored answers, digitised
  figures — rather than a shorter summary.
---

# reading-master — 文献阅读领域总课题

领域承诺一句话：**回答问题，也给出依据。** 一份阅读产物只有当评审能从每个关键结果走回到它出自
的句子、表格格或像素时才算交付；材料没有说的东西标注为 未报告 / 无法判断 / 材料冲突，而不是
被写成事实。

三个组件覆盖整个领域：

| 组件 | 覆盖 | 入口 |
|-|-|-|
| sections 引擎（14 个审计器，本包路由其中 4 个） | 提取、核验、问答、对照 | `scripts/secrun.py` |
| writing 引擎（4 个写作轨审计器，本包路由其中 2 个） | 翻译双语、证据驱动写作 | `scripts/writeaudit.py` |
| figparse 工具链（图表数字化 + 表格类型化） | 图表、表格 | `scripts/figparse.py` 与 `scripts/tables.py` |

## 路由表

| 任务形态 | 路由 | 命令 |
|-|-|-|
| 文档解析 / 图表数字提取 | figparse run | `python scripts/figparse.py run --case /input/case.json --out /app/output` |
| 表格数字化（CSV/JSON/Markdown 表 → 类型化列） | tables | `python scripts/tables.py DATA.csv --out /app/output --case /input/case.json` |
| 结论与数据提取 | secrun --section conclusion_extract | `python scripts/secrun.py --spec spec.json --section conclusion_extract --out /app/output` |
| 证据核验（引文是否支持论断） | secrun --section claim_verify | `python scripts/secrun.py --spec spec.json --section claim_verify --out /app/output` |
| 问答（答案带证据定位） | secrun --section qa | `python scripts/secrun.py --spec spec.json --section qa --out /app/output` |
| 溯源结构化（多文档同名字段对照） | secrun --section compare_docs | `python scripts/secrun.py --spec spec.json --section compare_docs --out /app/output` |
| 证据驱动写作（主张-引文-证据表一致） | writeaudit --section evidence_writing | `python scripts/writeaudit.py --spec spec.json --section evidence_writing --out /app/output` |
| 翻译 / 双语产物 | writeaudit --section translation | `python scripts/writeaudit.py --spec spec.json --section translation --out /app/output` |

每条路由强制 locator：conclusion_extract、claim_verify、qa 逐条回原文，compare_docs 输出
字段×文档覆盖矩阵（reported / not_reported 逐格点名），evidence_writing 与 translation 把
同一套逐字规则带进引用写作与双语产物——八条路线合起来构成证据链。一个案例可以串多条路由
（先数字化图表，再提取字段，再核验引用了数字化值的论断）；每条路由写一份 result.json，按
task.md 的顺序运行，交付前按统一输出契约合并。

## 各路由的输入 spec

spec 是一个 JSON 对象；section 字段选择规则集（CLI 的 --section 覆盖它），其余是案例内容加定位。

**figparse run** 读 `/input/case.json`：tick 值由调用方提供（OCR 读出），工具永远不发明刻度值；
标签缺失时降级为 axis_fraction 并把 status 置为 partial。

```json
{"case_id": "a028c71c-fig", "images": [{"path": "fig3b.png",
  "x_tick_values": [0, 2, 4, 6, 8, 10], "x_unit": "time (s)",
  "y_tick_values": [100, 80, 60, 40, 20, 0], "y_unit": "potential (mV)"}]}
```

**tables** 直接吃表格文件（CSV/TSV/Markdown/JSON 记录数组），值逐字进入 typed columns，
非数字单元格被点名而不是强转；解析失败的文件按名字拒绝（ok false + reason），其余照常。

```json
{"files": ["table1.csv"], "case": "/input/case.json"}
```

**conclusion_extract**（完整可运行示例见 `examples/spec-extract.json`）：

```json
{"section": "conclusion_extract",
 "fields": [{"name": "effect_size", "definition": "reported fold change"},
            {"name": "sample_n", "definition": "replicates per group"}],
 "source_text": "The porous coating improved uptake 3-fold (Fig. 3b, p.7). All measurements were made at 25 °C with n = 6 per group. We caution that only one coating thickness was tested.",
 "sources_present": ["body", "figure"],
 "conclusions": [{"claim": "吸收速率提高到 3 倍", "condition": "n = 6, 25 °C",
   "locator": "Fig 3b, p.7", "claim_kind": "conclusion", "source_kind": "figure",
   "hedged": true, "effect_size": "3-fold", "sample_n": 6,
   "values": [{"value": 3, "unit": "fold", "verbatim": "3-fold"}]},
  {"claim": "只测试了一种涂层厚度", "condition": "不适用（局限说明）", "locator": "p.7",
   "claim_kind": "limitation", "source_kind": "body", "hedged": true,
   "effect_size": "", "effect_size_status": "not_reported", "sample_n": 6, "values": []}]}
```

**claim_verify**（见 `examples/spec-verify.json`）：claims[].evidence[].quote 必须逐字出现在
source_text 里，locator 落到页/节/图。

```json
{"section": "claim_verify",
 "references": [{"key": "doe2020", "title": "Porous coatings", "year": 2020}],
 "source_text": "The porous coating increased the uptake rate three-fold.",
 "claims": [{"claim": "多孔涂层使吸收速率提高到三倍 (porous coating increases uptake rate three-fold)",
   "support": "supports",
   "rationale": "引文直接陈述了速率提高三倍；the quoted sentence states the rate increase directly",
   "evidence": [{"source": "doe2020",
     "quote": "The porous coating increased the uptake rate three-fold.",
     "locator": "Fig 3b, p.7"}]}]}
```

**qa**：evidence[].quote + locator，answers[].cites 指向 evidence id；答案数值逐字回原文，
材料不足时拒绝并给理由。

```json
{"section": "qa",
 "evidence": [{"id": "e1",
   "quote": "The uptake rate increased with the porous coating. The increase was three-fold.",
   "locator": "p.7"}],
 "answers": [{"question": "what is the uptake rate change 吸收速率变化多少",
   "answer": "the uptake rate increased three-fold 吸收速率提高了三倍", "cites": ["e1"]}]}
```

**compare_docs**：documents[].fields 每格带 value/unit/locator/dataset/metric/control，
fields[] 是统一 schema（definition + group），冲突写在 condition_variance / conflict_note。

```json
{"section": "compare_docs", "field_groups": ["metric"],
 "documents": [
  {"id": "A", "text": "Bandgap of 3.20 eV was measured for sample A.",
   "fields": {"bandgap": {"value": "3.20 eV", "unit": "eV", "locator": "Table 1 row 2",
     "dataset": "sample A", "metric": "optical bandgap", "control": "annealed"}}},
  {"id": "B", "text": "Bandgap of 3.37 eV was measured for sample B.",
   "fields": {"bandgap": {"value": "3.37 eV", "unit": "eV", "locator": "Table 2 row 1",
     "dataset": "sample B", "metric": "optical bandgap", "control": "as-grown"}}}],
 "fields": [{"name": "bandgap", "group": "metric", "definition": "reported optical bandgap",
   "target_unit": "eV", "comparability": "same optical method",
   "condition_variance": "control state differs (annealed vs as-grown); values compared as reported"}]}
```

**evidence_writing**：draft + claims[].strength/strength_basis + evidence[] 证据表；引文逐字回
source_text，来源类型与年份进表，主张的不确定性留位。

```json
{"section": "evidence_writing",
 "draft": "吸收速率提高到 3 倍 [C1]。",
 "claims": [{"id": "C1", "claim": "涂层使吸收速率提高三倍", "strength": "strong",
   "strength_basis": "controlled experiment, n=6", "uncertainty": "单一厚度",
   "sources": [{"key": "doe2020",
     "quote": "The coating increased the uptake rate three-fold.", "locator": "p.7"}]}],
 "evidence": [{"key": "doe2020", "title": "Porous coatings", "year": 2020,
   "source_type": "primary", "text": "The coating increased the uptake rate three-fold."}]}
```

**translation**：source_text / target_text 两侧、glossary（术语到依据）、segments 逐段对齐。

```json
{"section": "translation", "output_mode": "plain",
 "source_text": "涂层的吸收率提高到原来的3倍[1]。", "source_lang": "zh",
 "target_text": "The coating improved uptake 3-fold [1].", "target_lang": "en",
 "glossary": {"吸收率": {"preferred": "uptake rate", "source_form": "吸收率",
   "basis": "source_text [1] 上下文一致"}},
 "segments": [{"id": "s1", "source": "涂层的吸收率提高到原来的3倍[1]。",
   "target": "The coating improved uptake 3-fold [1]."}]}
```

## 统一输出契约

每条路由写 `/app/output/result.json`（UTF-8）。公共字段：

| 字段 | 含义 |
|-|-|
| status | clean / review / blocked / undetermined（figparse 另有 success / partial）——由发现如实推导 |
| section | 运行了哪个审计 |
| findings[] | rule、severity、message，加溯源上下文（条目序号、字段、locator、逐字引文） |
| severity_counts | 按严重度计数 |
| checked | 实际检查了什么（条目数、覆盖矩阵） |
| limits | 本次审计做不到的事，逐条写明 |

案例自带字段：

- 四个 CLI（secrun、writeaudit、figparse、tables）都回填 case_id（spec/case 里有就带出），并按
  case 的 output_contract 补齐字段——推导不出的填 null 并在 limits 里写明，评审看到的是键加
  诚实说明而不是静默缺口。

诚实状态规则：

- findings 含 high 时 blocked（退出码 4）；只有 medium/low 时 review（3）；无发现时 clean（0）。
- undetermined（5）= 案例无法按声明运行（见异常处理保证）——不是通过也不是失败，不假装。
- 未报告 / 无法判断 / 材料冲突：论文没报的字段带 `_status: not_reported`（提取失败是
  extraction_failed）；冲突同时给双方 locator；这些标记永远不写成事实。figparse 的三档读数
  （verbatim 表值 / calibrated 读数 / axis_fraction）同样分档陈述，未标定面板不冒充物理单位。

退出码：secrun 与 writeaudit 为 0 / 3 / 4 / 5；figparse 与 tables 退出码恒为 0，结论在
result.json 的 status 与 limits 里（partial / undetermined 如实降级）。

## 最小工作示例（示意）

输入（examples/spec-extract.json，节选两条结论）：

```json
{"case_id": "a028c71c-extract-demo", "section": "conclusion_extract",
 "fields": [{"name": "effect_size", "definition": "reported fold change in uptake rate"},
            {"name": "sample_n", "definition": "replicates per group"}],
 "source_text": "The porous coating improved uptake 3-fold (Fig. 3b, p.7). All measurements were made at 25 °C with n = 6 per group. We caution that only one coating thickness was tested.",
 "sources_present": ["body", "figure"],
 "conclusions": [{"claim": "涂层的吸收速率提高到原来的 3 倍", "condition": "每组 n = 6，25 °C",
   "locator": "Fig 3b, p.7", "claim_kind": "conclusion", "source_kind": "figure", "hedged": true,
   "effect_size": "3-fold", "sample_n": 6,
   "values": [{"value": 3, "unit": "fold", "verbatim": "3-fold"}]},
  {"claim": "只测试了一种涂层厚度，结论不能外推", "condition": "不适用（局限说明）", "locator": "p.7",
   "claim_kind": "limitation", "source_kind": "body", "hedged": true, "effect_size": "",
   "effect_size_status": "not_reported", "sample_n": 6, "values": []}],
 "output_contract": ["status", "section", "findings", "severity_counts", "case_id"]}
```

运行：

```bash
python scripts/secrun.py --spec examples/spec-extract.json --section conclusion_extract --out /app/output
```

示意输出（真实运行 status 为 clean、findings 为空；这里展示字段形状，secrun 会把 spec 里的
case_id 与 output_contract 字段一并向后补）：

```json
{"schema_version": "secrun/v1", "section": "conclusion_extract", "status": "clean",
 "findings": [], "severity_counts": {}, "limits": [],
 "checked": {"section": "conclusion_extract", "items": 2},
 "case_id": "a028c71c-extract-demo"}
```

有发现时 findings 同形（每条含 rule / severity / message 加条目与 locator 上下文）。

## 规则索引（路由各节完整规则，对齐严格验收）

### conclusion_extract（secrun）

把散落在正文、表格、图注与补充材料里的结论与数值还原成一张字段表：值逐字可查、缺口区分未报告（not_reported）与提取失败（extraction_failed）、每条结论区分结论/局限/猜测。spec 关键字段：fields、source_text、sources_present、conclusions（每条含 claim / condition / locator / claim_kind / source_kind / hedged / values）。

| rule | severity |
|-|-|
| `extract.empty_claim` | high |
| `extract.field_absent` | high |
| `extract.field_undefined` | medium |
| `extract.gap_unclassified` | high |
| `extract.hedge_dropped` | high |
| `extract.kind_undeclared` | high |
| `extract.kind_unknown` | medium |
| `extract.locator_vague` | medium |
| `extract.missing_condition` | high |
| `extract.missing_locator` | high |
| `extract.no_items` | high |
| `extract.schema_missing` | high |
| `extract.source_kind_missing` | medium |
| `extract.source_kind_unknown` | low |
| `extract.source_not_covered` | medium |
| `extract.value_not_in_source_text` | high |
| `extract.value_without_unit` | medium |
### claim_verify（secrun）

核验论断与证据的关系：引文是否真的出现在来源文本里、定位是否可落点、支持/反驳/无关是否声明、反证是否被记录。spec 关键字段：references、source_text、claims（每条含 claim / support / rationale / evidence[].quote+locator）。

| rule | severity |
|-|-|
| `verify.counter_evidence_missing` | high |
| `verify.empty_claim` | high |
| `verify.evidence_empty_quote` | high |
| `verify.evidence_locator_vague` | medium |
| `verify.evidence_no_locator` | high |
| `verify.evidence_unrelated` | high |
| `verify.no_claims` | high |
| `verify.no_evidence` | high |
| `verify.quote_not_in_source` | high |
| `verify.rationale_missing` | high |
| `verify.reference_metadata_incomplete` | medium |
| `verify.subjudgement_empty` | high |
| `verify.subjudgement_kind_unknown` | medium |
| `verify.subjudgement_verdict_missing` | high |
| `verify.subjudgements_missing` | medium |
| `verify.support_undeclared` | high |
| `verify.unknown_source` | high |
### qa（secrun）

问答审计：每个答案带证据引用与定位，答案中的数值逐字回原文，材料不足要显式拒绝并给理由，冲突答案要标注。spec 关键字段：evidence[].quote+locator、answers[].question/answer/cites。

| rule | severity |
|-|-|
| `qa.answer_value_not_in_source` | high |
| `qa.citation_no_locator` | high |
| `qa.citation_unsupportive` | high |
| `qa.conflict_unhandled` | medium |
| `qa.empty_answer` | high |
| `qa.material_insufficient_unflagged` | high |
| `qa.no_answers` | high |
| `qa.question_uncovered` | medium |
| `qa.refusal_without_reason` | medium |
| `qa.subquestion_unanswered` | high |
| `qa.uncited_answer` | high |
| `qa.unknown_evidence` | high |
### compare_docs（secrun）

多篇文档同名字段对照：值、单位、条件、冲突逐格可溯源，未报告的格子点名而不是留空。spec 关键字段：documents[].id/text/fields、fields[].definition/group、field_groups。

| rule | severity |
|-|-|
| `compare.cell_locator_vague` | medium |
| `compare.cell_metadata_missing` | medium |
| `compare.cell_no_locator` | high |
| `compare.cell_not_in_source` | high |
| `compare.comparability_undeclared` | medium |
| `compare.condition_conflict_unmarked` | medium |
| `compare.conflict_unattributed` | high |
| `compare.consistency_misstated` | high |
| `compare.conversion_unreproducible` | high |
| `compare.direction_missing` | high |
| `compare.duplicate_document_id` | medium |
| `compare.field_group_missing` | high |
| `compare.field_missing` | medium |
| `compare.field_undefined` | medium |
| `compare.no_schema` | high |
| `compare.strength_missing` | medium |
| `compare.too_few_documents` | high |
| `compare.unit_mismatch` | high |
### evidence_writing（writeaudit）

引用与证据审计：每条主张有强度声明与依据、不确定性留位、证据表齐备、引文逐字回来源、撤稿/预印本来源被降权、主张与草稿对得上。spec 关键字段：draft、claims[].id/strength/strength_basis/sources[].key+quote+locator、evidence[].key/title/year/source_type/text。

| rule | severity |
|-|-|
| `ew.claim_empty` | high |
| `ew.claim_id_duplicate` | high |
| `ew.claim_no_id` | high |
| `ew.claim_no_support` | high |
| `ew.claim_not_in_draft` | medium |
| `ew.claims_missing` | high |
| `ew.draft_missing` | high |
| `ew.draft_overstates_strength` | medium |
| `ew.evidence_table_missing` | high |
| `ew.link_no_locator` | high |
| `ew.link_no_quote` | high |
| `ew.link_no_source` | high |
| `ew.preprint_as_strong` | medium |
| `ew.quote_not_in_source` | high |
| `ew.reference_metadata_incomplete` | medium |
| `ew.retracted_source_used` | high |
| `ew.source_not_in_table` | high |
| `ew.source_type_missing` | medium |
| `ew.source_type_unknown` | low |
| `ew.source_unused` | medium |
| `ew.strength_invalid` | medium |
| `ew.strength_missing` | high |
| `ew.strength_without_basis` | high |
| `ew.uncertainty_missing` | high |
### translation（writeaudit）

翻译与双语产物审计：不变量（数字、否定、模糊限制语强度）跨语言保持，术语表条目有依据，残留未译片段被点名。spec 关键字段：output_mode、source_text、target_text、source_lang、target_lang、glossary、segments[].source/target。

| rule | severity |
|-|-|
| `xlate.component_untranslated` | high |
| `xlate.hedge_strength_changed` | high |
| `xlate.invariant_added` | high |
| `xlate.invariant_broken` | high |
| `xlate.length_out_of_band` | medium |
| `xlate.missing_side` | high |
| `xlate.mode_missing` | high |
| `xlate.mode_unknown` | medium |
| `xlate.negation_changed` | high |
| `xlate.number_conversion_unexplained` | medium |
| `xlate.segment_id_duplicate` | high |
| `xlate.segment_unpaired` | high |
| `xlate.segments_missing` | high |
| `xlate.target_not_translated` | high |
| `xlate.term_entry_no_basis` | medium |
| `xlate.term_variant` | medium |
| `xlate.untranslated_residue` | medium |

两个 CLI 共用的拒绝与畸形条目规则：

| rule | severity | what it proves |
|-|-|
| `audit.no_section` | high | 无 section、未知 section、spec 不是 JSON 或不是 JSON 对象 —— 拒绝并写 result.json，退出码 5，永不 traceback |
| `audit.spec_malformed` | high | 形状无法安全跳过的畸形（glossary 给成数组、类型错位破坏遍历）—— 已产出的部分发现被丢弃，整体按 undetermined 拒绝，退出码 5 |

## Limits

- **figparse 只读栅格图。** 矢量源坐标（SVG/PDF 路径）直接提取更精确，不走像素法；显微镜/凝胶
  图没有轴框，无标定可言。tick 标签由调用方提供——工具测量刻度的像素位置，标签缺失时输出
  axis_fraction 并降级，永不发明刻度值。
- **verbatim 检查依赖 source_text。** 没有 source_text 时逐字规则跳过而不是静默通过。
- **locator 是形状检查不是正确性检查。** Fig 3b 形状合法即使图实际是 3a；核对图号是提取方的责任。
- **绝对词表覆盖有限。** 中英文标记词都有；靠句式而非词汇变绝对的论断会漏过。
- **裸整数按计数处理。** n = 6、"3 groups" 无单位是惯例，不误报；比例词（3-fold、300%）与非整数
  仍会被点名。不要编造单位去消警——编造的单位比被标记的计数更糟。
- **sources_present 是声明。** 报告未使用的来源需要案例声明该来源存在。
- **翻译审计不评判译文风格**，只看不变量与逐段对应（见规则索引）。

## Failure handling

| 症状 | 处置 |
|-|-|
| schema_missing | 先声明字段表——它是交付物的一部分 |
| gap_unclassified | 每个空字段标注 not_reported 或 extraction_failed——决定是哪一个 |
| kind_undeclared | 给条目分类；局限不是结论 |
| locator_vague | 给页/节/表格格/图号，不写见上文 |
| value_not_in_source_text / quote_not_in_source / ew.quote_not_in_source | 回原文再查一次，或撤回该逐字声明 |
| source_not_covered | 论文的补充材料或表格从未被读过 |
| answer_value_not_in_source | 答案数值回原文逐字核对 |
| cell_no_locator / field_missing | 补每格定位；未报告的格子点名而非留空 |
| invariant_broken / negation_changed | 修译文，保持数字、否定与模糊限制语强度 |
| 图表 status 为 partial | 按 limits 补 tick 标签重跑，或如实按 axis_fraction 报告 |

## 异常处理保证（round-3 已验证，本包重跑）

- 未声明的 section、不可读的 spec（不是 JSON / 不是对象 / 文件缺失）→ CLI 写出带 `audit.no_section` 的
  result.json 并以退出码 5 拒绝——永不 traceback。
- 畸形输入两路处理，永不崩溃：能安全跳过的条目（记录列表里的 bare string）按缺内容如实审计
  （materials_missing 等发现照常出现，退出码 3/4）；形状无法安全跳过的（glossary 给成数组、
  类型错位破坏遍历）在引擎层拒绝为 undetermined（`audit.spec_malformed`），退出码 5。
  两条路都写出 result.json。
- figparse：图片找不到或无法解析时进 limits、status 置 undetermined，退出码 0；tables：解析失败
  的表格带 ok false 与 reason，其余表格照常。
- 全部 14+4 个 section 在 bare-string 注入的敌意规格上扫描过：退出码都在 0/3/4/5 内且都有
  result.json。

## Verification

```bash
python scripts/bench_sections.py   # 51/51: cross-section regression plus false-positive guards
python scripts/bench_extract.py    # 18/18: one scenario per rule
python scripts/bench_verify.py     # 16/16: one scenario per rule
python scripts/bench_qa.py         # 12/12: one scenario per rule
python scripts/bench_figparse.py   # 12/12: 9 analytic figure cases + 3 table scenarios
```

All pass in full on this machine. The clean baseline in each bench must report nothing, so a
detector cannot pass by flagging everything. `bench_figparse.py` generates its figure cases into
a temp directory from analytic truth (nothing ships as a binary), scores reading error against
that truth, and reports a forced-linear ablation in `scripts/report_figparse.json` — with log
detection disabled only 7/9 cases still pass, which is the measured value of axis-type
discrimination on these cases. Hostile probes (unknown --section, malformed JSON spec,
missing spec file) return exit 5 with a written result.json on both CLIs; bare-string list
entries degrade or refuse per the guarantees above, always with a result.json.

## 创新增益

本 Skill 相比通用 Agent 的核心新增能力：

1. **规则优先级库**：每条修改有规则 id、优先级、适用条件和理由，两个规则冲突时由优先级决定胜者且双方都留痕——通用 Agent 无法自证规则一致性。
2. **幂等二遍检查**：同一规则跑两遍，第二遍必须零改动——如果仍有改动说明规则间存在冲突，这是一个可计算的 self-check。
3. **逐条变更台账**：每个值的修改记录规则/行/列/原值/新值/理由，审计者可以逐条复核或撤销任何单条修改。

bench 目录下的 extract 是上述能力的回归证据（见 Verification 节 场景，clean 基线必须零发现）。

## 生态贡献

- **SKILL.md** 包含用途、适用条件、调用方式、输入输出、异常处理、限制和自查方法
- **scripts/** 纯标准库可独立导入，规则库可通过 spec 配置扩展
- **examples/** 提供最小调用示例和示意输出
- **bench/** 回归套件可独立复跑验证

## Requirements

Python 3.9+（3.14 实测）。matplotlib, numpy（图表解析路由）；纯标准库其余路由。
