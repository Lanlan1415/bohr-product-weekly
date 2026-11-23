---
name: search-systematic-review
description: >
  系统性文献综述的端到端可复现工作流。把 PICO 变成含同义词/受控词和字段布尔逻辑的检索式，
  逐源记录数据库、接口、日期、时间语言边界与 executed/fixed_corpus/prospective 状态；执行 DOI/题名
  去重、自动化/其他移除、题录与全文两轮纳排、双人分歧裁决、理由代码和 PRISMA 计数闭合。
  纳入研究逐域做 ROB2/ROBINS-I/QUADAS-2/generic 质量与偏倚评价并计算总体等级，保留原文证据，
  报告临床/方法异质性、Q/I²/tau²、固定效应与 DL 随机效应、高偏倚敏感性和有界研究空白。
  未执行真实库检索时 PRISMA 外部计数为 null，绝不伪造零或纳入数。
  Use for reproducible systematic reviews, PRISMA flow, two-stage screening, risk-of-bias tables,
  narrative/quantitative evidence synthesis and sensitivity analysis. No live database access is implied.
---

# search-systematic-review（系统性文献综述）

正式入口是 `scripts/sysrevrun.py` + `scripts/sysrev_engine.py`。旧 `search_cli.py` 仅保留布尔探针兼容，
**几个关键词命中不是系统综述**。新入口直接生成检索日志、两轮筛选、PRISMA 流向、逐域偏倚、
证据矩阵、异质性/合并结果和系统综述报告。共享 `search.py/search_cli.py` 未改动。

## 输出文件

| 文件 | 内容 |
|-|-|
| `systematic_review.md` | PICO、检索式、两轮筛选、PRISMA、偏倚、异质性、综合、空白与限制 |
| `search_protocol.csv` | 每源原检索式、字段、同义词/受控词、过滤、日期、执行状态、真实命中或 null、供入行 |
| `screening_log.csv` | 重复、预筛、题录、全文和未获取全文的逐条决定、理由、判定人、裁决 |
| `prisma_flow.csv` | PRISMA2020 data/box/n/单位/原因明细；固定快照和前瞻协议严格区分 |
| `quality_appraisal.csv` | 研究×工具×域 judgment、理由、证据、计算总体；不加权汇总另见 result.json |
| `evidence_matrix.csv` | 报告/研究/来源、quote、精确 locator、比较组、纳入状态 |
| `evidence_synthesis.csv` | 每个综合论断支持与相反证据、强度、locator、偏倚敏感性 |
| `heterogeneity.csv` | 临床/方法差异、效应量、Q/df/I²/tau²、固定与 DL 随机模型、敏感性 |
| `result.json` | 全部机读结果、六类 PRISMA 恒等式、覆盖、findings、artifact SHA-256、原平台字段 |

所有数字来自本次真实输入行，不把合成示例计数或外部假设当组织方案例结果。

## 六步正式运行路径

0. **读取实际材料。** 先读 `/input/case.json`、`/input/task.md` 和全部导出/论文，冻结 case_id 与
   output_contract。PDF 用真实 PDF/OCR 工具，不能凭文件名或领域标签补内容；建 `/app/work`、`/app/output`。
1. **先冻结协议。** 在 `/app/work/sysrev-spec.json` 写 research_question 和 search_protocol：PICO、版本、
   数据库、逐源检索式、字段、同义词/受控词、时间/语言、纳排条款、条款优先级与冲突裁决。
2. **执行可复现筛选。** 逐行写 records。先保重复审计轨迹，再做题录与全文两级 include/exclude/undetermined；
   每次排除写 reason_code+reason+reviewer，未获取全文单列。双人决策分歧必须有第三方/预设裁决理由。
   不能把标准在筛选途中改宽，也不能删除重复或相反结果来“修好”计数。
3. **评价与综合。** 纳入研究每个质量域写 judgment+evidence_refs+rationale；overall 由引擎计算。
   证据表保留 method/data/outcome/conclusion 与 effect 定位。按 comparison_key 写综合论断，
   同时引用支持和相反方向；只有完整同组效应参数齐全且协议允许时才做定量合并。
4. **运行正式 CLI。** 在技能目录运行：

   ```bash
   python -I -X utf8 scripts/sysrevrun.py \
     --spec /app/work/sysrev-spec.json --case /input/case.json --out /app/output
   ```

   Python 标准库，离线，无第三方包。引擎不会访问数据库或把潜在结果写成已执行。
5. **复核计数、证据和结果。** 修 findings 中的错行者、漏理由、双人分歧、域覆盖、坏 locator、漏相反证据、
   伪命中数或计数不闭合；不得改原始材料迎合预期结论。最后核对 case_id 来自原 case、output_contract
   全字段同名存在，CSV/Markdown/result.json 一致。材料不足保留 review/blocked/undetermined。

## 输入规格

### 1. 研究结构和 search_protocol

```json
{
  "research_question": {"population": "成人慢性疼痛", "intervention": "数字居家运动",
                        "comparator": "常规照护", "outcome": "12周疼痛"},
  "search_protocol": {
    "status": "fixed_corpus", "version": "sr-v1-frozen",
    "start_date": "2019-01-01", "end_date": "2026-11-24",
    "languages": ["English", "Chinese"],
    "inclusion_criteria": ["可判定纳入条款"],
    "exclusion_criteria": ["EX-POP ...", "EX-DESIGN ..."],
    "criterion_priority": "先去重，再题录，再全文；禁止后见改判",
    "conflict_policy": "保留双人原票并由第三方依冻结条款裁决",
    "databases": [{
      "name": "OpenAlex snapshot", "interface": "case export",
      "query": "TITLE_ABSTRACT:(exercise) AND TITLE_ABSTRACT:(chronic pain)",
      "fields": ["title", "abstract"],
      "synonyms": ["exercise therapy", "home exercise"],
      "controlled_terms": ["Exercise Therapy", "Chronic Pain"],
      "filters": {"language": ["en", "zh"]},
      "coverage": "2019-2026 snapshot", "snapshot_date": "2026-11-24"
    }]
  }
}
```

三种状态不能混用：

- `executed`：每个来源真实 search_date + 非负整数 hit_count；引擎强制**每源 hit_count=实际供入导出 records 行数**，否则 blocked。
- `fixed_corpus`：以 snapshot_date/实际日期和实际 records 行复算固定快照；不得出现 hit_count，不声称数据库完备。
- `prospective`：只形成将要执行的协议；外部 PRISMA 计数全为 null，状态固定为 `review / sr.prospective_protocol_only`（exit 3）。null 不是 0，报告不得写成已完成筛选。

每源 query 必须含受控字段/引号/通配或布尔结构，不接受关键词串充当可复现检索式；synonyms 与 controlled_terms
至少一种具体列出，另一项可空但在文档说明该库无受控词。还可记录 interface/filters/coverage。

### 2. records：报告、研究和两轮筛选

每篇报告使用 `report_id`，并用 `study_id` 把同一研究多篇报告聚到一起。常用字段：

- `doi/title/year/source_database`：重复识别与来源核对；DOI 去 URL 前缀，无 DOI 用规范题名；
- `duplicate_of`：可选；同 DOI/题名自动识别后进版本并保留 duplicate_of；
- `automation_exclude/automation_reason`：自动化移除；`pre_screen_exclude/pre_screen_reason`：其他预筛移除；
- `ta_decision`：include/exclude/undetermined； exclude 必须有 `ta_reason_code/ta_reason`；
- `ta_reviewer` 或 `ta_reviews`（reviewer+decision 列表）；分歧必须 `ta_adjudication={decision,reason,...}` 且匹配最终决定；
- `fulltext_status`：retrieved/not_retrieved；后者需要 retrieval_reason，不算全文排除；
- `ft_decision`、`ft_reason_code/ft_reason`、`ft_reviewer/ft_reviews/ft_adjudication`：全文级同规则。

纳入报告还必须写 design/population/intervention/comparator/outcome/followup/method/data/conclusion/
comparison_key/direction（positive/negative/no_effect/mixed/not_reported）和 field_evidence。每个
`evidence` 项为 `{id,fields,quote,locator}`；附 source_excerpt 后 quote 必须是原文逐字子串。
每研究只设一个 `synthesis_role=primary`，其他报告为 secondary，防止 meta 分析重复计算同一研究。

### 3. 质量/偏倚评价

```json
{
  "study_id": "S1", "tool": "ROB2", "overall_reported": "low",
  "domains": [{"domain": "D1", "judgement": "low",
               "rationale": "随机序列与分配隐藏已报告",
               "evidence_refs": ["R1:Q1"]}]
}
```

- ROB2 必须 D1–D5；judgement 为 low/some_concerns/high/no_information/not_applicable。任一 high ⇒ overall high；
  否则 some_concerns/no_information 阻止 low 并为 some_concerns。
- ROBINS-I 必须 D1–D7，支持 low/moderate/serious/critical/no_information/not_applicable；总体取最严重有效域。
- QUADAS-2 使用 D1–D4；generic 至少一个声明域。每域必须引用本纳入研究的精确 evidence。
- `overall_reported` 可省略；一旦填写与域计算不一致就 high。域汇总是**不加权** counts+proportions，
  不把研究样本量或效应权重混入偏倚构成。

### 4. 证据综合、异质性与敏感性

`synthesis_settings`：

```json
{"allow_meta_analysis": true, "primary_overall": ["low", "some_concerns"],
 "heterogeneity_rule": "I2>=75% exploratory only"}
```

`synthesis_claims[]` 每项含 id/type/comparison_key/statement/support_evidence_refs/
contradicting_evidence_refs。contradiction 必须有独立两侧；同组相反方向未全部纳入双向综合会 blocked。
高/未明风险研究不被静默删除，而进入 all-study 结果并另算 primary_overall 集合；证据基础改变时标
`sensitivity_changed=true` 并写入不确定性。

主记录 `effect` 形如：

```json
{"measure": "MD", "estimate": -1.20, "se": 0.35, "evidence_ref": "R1:E"}
```

只有整组 ≥2 个独立研究、同 measure、所有 estimate 有限、所有 se>0 且协议允许时才计算。输出逆方差固定
效应、DerSimonian–Laird 随机效应、Q、df、I²、tau² 和正态 95% CI；不能只挑同方向子集。I²≥75% 标
exploratory_only_high_heterogeneity，禁止作无条件 headline。效应模型公式与边界见
`references/prisma_protocol.md`。

### 5. 研究空白

`research_gaps[]` 需要 statement、positive_evidence_refs 和 scope_checks；每个 scope check 含
source/query/covered_years/outcome。只有正向原文证据+完整范围核查才输出 supported_bounded_gap；
单独“没有检索到”永远是 undetermined，结论必须限固定语料/数据库/日期。

## PRISMA 计数闭合（真实执行/固定快照）

引擎输出 `prisma_flow.checks`，全部必须为 true 才可声称流程完整：

1. identified = malformed + duplicates + automation removed + other removed + records screened；
2. records screened = title/abstract excluded + undetermined + reports sought；
3. reports sought = reports not retrieved + full text assessed；
4. full text assessed = full text excluded + undetermined + reports included；
5. 题录排除理由代码合计 = 题录排除总数；
6. 全文排除理由代码合计 = 全文排除总数。

报告与研究分别计数；无 previous-review 臂时 total=new，不凭空加前次研究。`records_undetermined`/
`fulltext_undetermined` 非零会产生 high。前瞻协议不计算这些外部数，也不会把 null 强转为 0。

## Output contract 与 Rubric 三段

| 内容 | 实际交付 |
|-|-|
| 研究产物 | `systematic_review.md` + result.json：问题拆解、检索、纳排、质量、综合、冲突和研究空白完整链路 |
| 证据矩阵 | 原文检索式、检索日期/数据库、两轮筛选、质量域证据、quote+locator、合并参数和敏感性全留痕 |
| 不确定性 | 未获取全文、双人分歧、高偏倚敏感性、临床/统计异质性、冲突、检索范围、前瞻未决分别列出 |

正常和拒绝路径都尽量保留可读 case 的 case_id、原 output_contract 对象与全部同名字段。支持字典、字符串、
字符串列表和 field/name/key 对象列表。原 case 身份优先，引擎值优先于 spec 自报，未知字段为 null+limits。

## 状态与退出码

| status | exit | 用法 |
|-|-|-|
| clean | 0 | 结构、计数和引用审计无发现；仍不构成全球完备或 GRADE 证明 |
| review | 3 | medium/low：如缺同义词、未使用纳入报告、缺口范围不足，需人工复核 |
| blocked | 4 | high：计数不闭合、纳排未决、错引、质量域缺失、冲突未并陈等；输出保留但不冒充完成 |
| undetermined | 5 | spec/case 不可读、不可运行或输出失败；写结构化 result.json，绝不 traceback |

检索为空不填 0 假装执行；数据库/权限超时写实际来源状态；全文不可得走 not_retrieved；条款冲突按冻结优先级；
术语同义/受控词写进协议；矛盾纳入文献双列；所有错误产物都尽可能留下供审查，不带 traceback。

## 核心规则索引

| rule 前缀 | 检查 |
|-|-|
| `sr.pico_*` / `sr.criteria_*` / `sr.criterion_*` | PICO、纳排和优先级/裁决 |
| `sr.database_*` / `sr.query_*` / `sr.search_*` / `sr.hit_count_*` | 可执行检索式、日期、执行状态和真实命中 |
| `sr.export_count_mismatch` / `sr.record_source_unknown` | 来源导出与声明总量一致 |
| `sr.ta_*` / `sr.ft_*` / `sr.reviewer_*` / `sr.review_*` | 两轮决定、理由、判定人和分歧裁决 |
| `sr.prisma_*` / `sr.screening_incomplete` | 流向计数闭合与未决筛选 |
| `sr.evidence_*` / `sr.quote_*` / `sr.field_evidence_*` | 原文 quote、locator、字段证据与错引 |
| `sr.quality_*` | 工具域覆盖、judgement、证据、总体计算和报告一致 |
| `sr.claim_*` / `sr.contradiction_*` / `sr.conflict_*` | 综合论断引用、相反方向和双向综合 |
| `sr.primary_report_count_invalid` | 多报告研究不被定量综合重复计数 |
| `sr.gap_*` | 研究空白正向证据和范围核查 |

## Limits

- 不联网、不自动访问 closed full text、不验证 DOI 真实存在、不根据标签猜研究设计。真实库返回必须由输入提供。
- 纳排和质量 judgment 是阅读者的可核声明；脚本验证留痕、计数与总体逻辑，不替代领域判断。
- comparison_key 只表示声明可比，不能自动证明临床同质。I²/Q/tau² 也不独立决定是否应该合并。
- 内置定量模型是透明逆方差与 DL，不替代小样本校正、比例/稀有事件专用模型、发表偏倚分析或 GRADE。
- 示例为合成接口验证，8 原始行和 4 纳入只用于复算示例，不是组织方固定案例筛选数量。
- 同输入同输出目录字节确定；CSV 使用 UTF-8 BOM 便于 Excel，JSON/Markdown 为 UTF-8。

## 可选作者自查（非正式运行步骤）

```bash
python -B -I -X utf8 scripts/bench_sysrev.py        # 旧探针兼容回归
python -B -I -X utf8 scripts/bench_sysrev_engine.py # 新 PRISMA/质量/统计/契约回归
python -B -I -X utf8 scripts/probe_sysrev_v2.py     # 敌意 CLI/幂等/冷导入
```

Python 3.9+，仅标准库。完整合成示例：`examples/sysrev-spec.json`、`examples/case.json`。
外部 GitHub 方法与落地差异：`references/prisma_protocol.md`。

## 创新增益与生态贡献

1. **状态机而非检索探针**：纳排历史、判定人、裁决、未取全文和理由代码共同决定 PRISMA，不能后补一个图。
2. **真正可复算的双层计数**：报告与研究分层，六类恒等式和原因合计都过才 complete；前瞻 null 防止假零。
3. **逐域质量证据与总体一致性**：robvis 风格研究×域结构，计算总体、无权重域汇总、偏倚敏感性全闭合。
4. **综合不消灭异质性**：自动比较设计/对象/干预/结局/随访和方向，公开固定+DL 模型全部输入与统计量。
5. **可复用生态**：检索式模板、两轮筛选表、PRISMA CSV、ROB2/ROBINS-I/QUADAS-2/通用质量表、
   证据表、异质性表、合成 CLI、独立回归与敌意探针；未复制外部项目代码或答案。
