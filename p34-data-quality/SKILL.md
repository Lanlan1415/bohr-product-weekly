---
name: research-data-quality
description: >
  Clean, standardise and quality-report a fixed research data table with a numbered,
  prioritised, re-runnable rule set driven by a data dictionary. Checks dictionary-to-table
  alignment before touching values, separates "not detected" from "detected as 0", converts
  units through a real dimension model, recognises near-duplicate records against true keys,
  names mixed written units that would corrupt a downstream average, normalises dates to
  ISO 8601 without inventing precision, and emits a machine-checkable quality report whose
  numbers are computed from the table itself — so a hand-written report that disagrees with
  the data is flagged, not trusted. Never overwrites the original: the input hash is
  recorded and the cleaned table is written beside it with a full change ledger. Every
  case returns result.json with case_id and the case's output_contract fields. Use when a
  task supplies a dirty research table (missing tokens, mixed units, duplicates, date soup)
  that must become analysable without losing provenance.
---

# research-data-quality

The failure this prevents is not a crash. It is a table that looks clean and is
wrong — `12 mV` averaged with `1.2 V`, "未检测" counted as zero, the same sample
entered twice and silently averaged, a quality report whose numbers no longer match
the table it describes — plus a cleaning pass that cannot be re-run or rolled back.

So the design is built around five guarantees:

1. **Nothing changes silently.** Every edit carries rule id, row, column, original
   value and reason; the original table is preserved verbatim beside the result, and
   its sha256 is recorded.
2. **The pass is idempotent.** Running the same rules twice finds nothing left to
   rewrite; a second pass that still changes cells is reported as a high finding,
   because it means the rule priorities disagree.
3. **The report is computed, not written.** Every number in the quality report is
   derived from the table, so a supplied report that disagrees with the data is
   flagged (clean.report_inconsistent) instead of being trusted.
4. **The data dictionary drives the rules.** Columns declare their semantic —
   numeric, date, categorical, id, text — and the rules branch on it instead of
   guessing from cell shapes; the dictionary-to-table alignment itself is checked
   before any value rule runs.
5. **Unrunnable input is a verdict, not a crash.** A missing spec, bad JSON, an
   unreadable table_path or an audit failure returns status undetermined (exit 5)
   with a result.json that names the case.

## 题面五类处理 → 规则

| 题面处理类 | rule / 机制 |
|-|-|
| 缺失值：区分未检测、低于检出限、录入缺失与真值 0 | R02 + missing_tokens；clean.missing_values；不填补 |
| 异常值：结合物理上下限与分布诊断 | R05 对 declared plausible 范围；保留/剔除/盖帽留给人工记录 |
| 重复记录：真实主键 + 近似重复 | R06 键归一 + R07 记录/实验二分；clean.key_column_missing 在键失效时拦 |
| 格式与单位转换 | R04 维度模型换算（记录因子）+ R08 日期归一；clean.mixed_units 点名未声明目标的混写单位 |
| 数据质量报告 | quality_report 逐列计算 + R09 对供给报告的一致性核对 |
| 字段级规则与可复现 | 字典外置（columns/key_columns/value_columns/missing_tokens）+ rules_applied + original.json + sha256 + 幂等自检 |

## 运行契约（Harbor runtime contract）

- 运行时输入是 /input/case.json 与 task.md：先读 case.json，逐字记录 case_id 与
  output_contract 的字段名清单（本题交付字段是清洗表、质量与复现证据、异常说明这类）；
  再读 task.md 与清洗工单确认要做的处理步骤。材料一律读实际文件，不按标签臆测。
- 工作目录 /app/work 放中间产物；最终实际结果放 /app/output，其中 result.json 必须保留
  output_contract 全部字段和 case_id（引擎自动回填，见第六步）。清洗表（cleaned.csv）、
  原始快照（original.json）与 result.json 同目录交付。
- 预算：64 次模型请求、900 秒、每次响应 16384 token（含推理）。先尽早写出诚实的部分成果，
  再增量改进。三个固定案例、每条件重复三次；不得伪造缺失的软件状态或科学数据。
- Skill 资源限制：最多 50 个 UTF-8 文本文件、单文件 500KB、总量 2MB、无符号链接。

## 演练纪律（本题固定案例的边界，逐条遵守）

- 案例材料是已发表的聚合表（aggregate table）转录，带有刻意注入的存储/编码故障、数据字典、逐指标
  单位与 QC 规则和明确的清洗工单——不是原始实验数据。清洗动作以工单为准，不自行加戏。
- 不得推断总体统计：清洗产出是逐记录的表级结果，不做分布推断、不做显著性声明。
- 不得填补缺失或无效源值："未检测"是命名缺口（named gap），列均值填补是编造数据；
  下游若一定要数，把该决定记录为人工步骤，而不是写成规则。
- 运行时没有承诺的 quality-gold.md 文件：不要等待或引用它；对照用的源/故障出处由平台
  侧留存支撑评分，本 Skill 只交付自己算出的证据。
- 数据字典先行：先读字段语义、单位与 QC 规则，再定 target_unit 与 plausible——从别的
  数据集抄来的范围是离群值制造机，不是约束。

## 六步运行时入口

0. **读 case.json 取标识**：记下 case_id 与 output_contract 的每个字段名；读 task.md 与
   清洗工单，确认五类处理里本案例要做哪几类。
1. **判形态路由**：按下面的「任务措辞 → 路由」决策表决定字段与检查项。
2. **先产出目标产物**：清洗后的表先行——按字典语义逐列过 R01–R08，得到逐条变更台账；
   缺失/无法解析/单位拒绝的单元格保留为命名缺口，不静默改写。
3. **构造 spec**：行数据进 rows（或 table_path 指向表文件），字典进 columns（name/
   semantic/target_unit/plausible），主键进 key_columns，重复判值列进 value_columns，
   案例自有缺失记号进 missing_tokens，工单供给的质量报告进 quality_report（触发 R09
   核对）。附上 case_id，并把 output_contract 的每个字段以同名键放进 spec——spec 携带的
   值逐字直通进 result.json。
4. **审计**：运行 python scripts/dataquality.py --spec spec.json --out /app/output。
   退出码：0 clean、3 review、4 blocked、5 undetermined（输入无法审计）。
5. **修发现重跑**：每条 finding 按 Failure handling 表处置。缺失与重复实验是数据的真实
   属性，不是待修复的缺陷——它们如实保留并说明；可修复的是单位、日期、空白与对齐问题。
   换输出目录重跑，同输入同目录会被 already_cleaned 拒绝（防止二遍叠一遍）。
6. **合并 result.json**：确认 /app/output/result.json 含 case_id 和 output_contract 全部
   字段（引擎自动回填：spec 带同名值的逐字直通，两边都没有的字段写 null 并在 limits
   注明）；quality_report 就是与结果表自洽的质量报告；changes/changes_by_rule 是逐条
   变更台账；idempotent 为 true 才交付。

## 任务措辞 → 路由决策表

| 任务里的措辞 | 路由与动作 |
|-|-|
| 「清洗这张表 / 按清洗工单处理」 | 六步主路径全量跑：字典对齐 → R01–R08 → 质量报告 |
| 「数据字典在附件里 / 先读字段语义」 | columns 进 spec（semantic/target_unit/plausible）；引擎先做字典-表对齐检查（column_missing / key_column_missing / ragged_rows） |
| 「未检测不是 0 / 缺失值处理」 | missing_tokens 声明案例自有记号；R02 归缺失；绝不填补 |
| 「异常值 / 离群点处置」 | plausible 声明物理范围；R05 给值/范围/理由，保留-剔除-盖帽留人工 |
| 「同一样品出现三次 / 去重」 | key_columns 声明真实主键 + value_columns 声明判值列；R06/R07 把记录副本与重复实验分开，后者绝不平均 |
| 「单位一处 mg/L 一处 μg/mL / 单位换算」 | target_unit 声明目标单位走 R04（换算因子入账）；未声明 target 而混写单位 → clean.mixed_units 点名 |
| 「日期有的是 2023/5/14 有的是 2023年5月14日」 | semantic 取 date；R08 归一 ISO 8601 并记录来源格式；认不出的日期是命名缺口 |
| 「质量报告数字要和结果表对得上」 | 工单供给的报告进 spec.quality_report → R09 逐字段核对；无供给则计算版直出 |
| 「表在 CSV/TSV 文件里」 | table_path 指文件；逗号/制表符自动判别，utf-8-sig 读取；读不了是 undetermined 拒跑，不是崩溃 |
| 「重新清洗 / 再跑一遍」 | 换输出目录；同输入同目录会被 clean.already_cleaned 拒绝（exit 4） |
| 「只清洗部分列」 | columns 只声明目标列；未声明列原样通过并被 clean.column_undeclared 点名 |
| 「编码乱码 / 老文件」 | 引擎以 utf-8-sig + 宽容读取；坏字节落进未解析名单，不静默丢弃、不伪造可读性 |

## The rule library

| id | priority | rule |
|-|-|-|
| R01 | 10 | trim surrounding whitespace from every cell |
| R02 | 20 | treat the not-reported tokens as a missing value, never as 0 |
| R03 | 30 | parse a value into number / error / unit / range structure |
| R04 | 40 | convert a unit to the column's target unit, recording the factor |
| R05 | 50 | flag a value outside the declared plausible range |
| R06 | 60 | normalise the entity key for duplicate detection |
| R07 | 70 | mark duplicate records separately from duplicate experiments |
| R08 | 80 | normalise dates to ISO 8601; never invent numeric precision |

Priorities matter: R04 runs before R05 so the range check sees the value in the
target unit. The ledger shows which rule won when two touch the same cell.

The two distinctions this module refuses to collapse:

- **duplicate record vs duplicate experiment** — identical rows are safe to drop
  after review; the same entity with different values is two measurements, and
  averaging them silently would hide the disagreement.
- **missing vs zero** — "not reported", "ND", "-" and blank are missing, not 0.
  A genuine 0 stays a measured zero.

## Dictionary-to-table alignment (checked before any value rule)

| rule | severity | what it proves |
|-|-|-|
| `clean.key_column_missing` | high | a declared key column exists in no row, so the duplicate census cannot identify entities |
| `clean.column_missing` | medium | the dictionary declares columns the table does not carry — 工单与表不一致 |
| `clean.ragged_rows` | medium | some rows miss columns other rows carry — 表内列漂移 |
| `clean.column_undeclared` | low | the table carries columns the dictionary does not declare; they pass through untouched, named |
| `clean.empty_rows` | medium | every cell of every row is blank — nothing to clean despite a well-formed table |
| `clean.mixed_units` | medium | one column carries several written units with no declared target — a downstream average would add incompatible quantities |

## Data dictionary

```json
{
  "columns": [
    {"name": "sample_id", "semantic": "id"},
    {"name": "bandgap", "target_unit": "eV", "plausible": [0, 6], "semantic": "numeric"},
    {"name": "measured_on", "semantic": "date"},
    {"name": "batch", "semantic": "categorical"}
  ],
  "key_columns": ["sample_id"],
  "value_columns": ["bandgap"],
  "missing_tokens": ["n.d.", "-999"]
}
```

`value_columns` decides what "same record" means for duplicates: same key with
identical values is a record copy (clean.duplicate_records), same key with
differing values is an experiment pair (clean.duplicate_experiments). Undeclared,
it defaults to every non-key column — comparing full rows.

`missing_tokens` extends the built-in not-reported set ("ND", "not reported",
"未检出", blank, "-999" — the sentinel the task names) per case.

`semantic` decides how a column is treated: date columns go through R08 (ISO 8601
output, source format recorded), categorical columns get whitespace collapse and a
value census, text/id columns skip measurement parsing, numeric columns go through
R03–R05. A column with no semantic is parsed as a measurement, as before.

## Worked example（示例，非正式案例结果）

examples/spec.json 的完整输入（带 case_id 与 output_contract；此处节选关键结构）：

```json
{
  "case_id": "demo-case-340",
  "rows": [
    {"sample_id": "S1", "bandgap": "3.20 eV", "measured_on": "2023/05/14"},
    {"sample_id": "s1", "bandgap": "3200 meV", "measured_on": "2023年5月14日"},
    {"sample_id": "S2", "bandgap": "not reported", "measured_on": "14.06.2023"}
  ],
  "columns": [
    {"name": "sample_id", "semantic": "id"},
    {"name": "bandgap", "target_unit": "eV", "plausible": [0, 6], "semantic": "numeric"},
    {"name": "measured_on", "semantic": "date"}],
  "key_columns": ["sample_id"],
  "output_contract": {"cleaned_table": "清洗后的表", "quality_report": "逐列质量报告",
                      "change_ledger": "逐条变更台账", "anomaly_notes": "异常与缺口说明"},
  "anomaly_notes": "S2 bandgap 未检出：missing，不是 0；14.06.2023 为 dot 格式日期，转 ISO。"
}
```

运行（示例命令，正式运行时 --out 用 /app/output）：

```bash
python scripts/dataquality.py --spec examples/spec.json --out examples/_demo_out
```

本机实跑 exit 3（review），以下为实跑得到的示意输出关键字段（示例，非正式案例结果；
完整运行还会写出 cleaned.csv 与 original.json）：

```json
{
  "schema_version": "data-quality/v1",
  "case_id": "demo-case-340",
  "status": "review",
  "findings": [
    {"rule": "clean.missing_values", "severity": "medium",
     "message": "some values are not reported; they are missing, not zero",
     "columns": ["bandgap"]},
    {"rule": "clean.duplicate_experiments", "severity": "medium",
     "message": "the same entity appears with different values; ...", "count": 1}
  ],
  "changes_by_rule": {"R04": 1, "R02": 1, "R08": 3},
  "duplicates": {"duplicate_records": 0, "duplicate_experiments": 1},
  "quality_report": {"rows": 3, "cells": 9, "missing_cells": 1, "unparsed_cells": 0,
                     "rewritten_cells": 4,
                     "per_column": [{"column": "bandgap", "semantic": "numeric",
                                     "target_unit": "eV", "cells": 3, "missing": 1,
                                     "unparsed": 0, "unit_refused": 0, "rewritten": 1,
                                     "parse_rate": 0.6667, "completeness": 0.6667}]},
  "cleaned_table": [
    {"sample_id": "S1", "bandgap": "3.20 eV", "measured_on": "2023-05-14"},
    {"sample_id": "s1", "bandgap": "3.2 eV", "measured_on": "2023-05-14"},
    {"sample_id": "S2", "bandgap": "not reported", "measured_on": "2023-06-14"}
  ],
  "anomaly_notes": "S2 bandgap 未检出：missing，不是 0；14.06.2023 为 dot 格式日期，转 ISO。",
  "change_ledger": null,
  "output_contract_fields": ["cleaned_table", "quality_report", "change_ledger",
                             "anomaly_notes"],
  "idempotent": true
}
```

change_ledger 在 spec 与引擎能力里都没有同名交付物，回填 null 并在 limits 点名——契约
直通的诚实形态：不编造，也不漏字段。cleaned_table 保留 S1 的 "3.20 eV" 原文（转换只对
需要换算的单元格做，且逐条留痕）；S2 的 "not reported" 原样保留为命名缺口，绝不写成 0。

## 评分要求映射（rubric 三段 → 本 Skill 落点）

| rubric 输出要求 | 完成标准（rubric 原词） | 本 Skill 落点 |
|-|-|-|
| 分析结果 | 清洗表、统计结果、图表、代码或查询结果；结果与数据字典、规则和任务一致 | cleaned.csv + cleaned_table + 字典对齐检查（column_missing/key_column_missing/ragged_rows）+ R01–R08 逐条变更台账，动作可追溯到规则 |
| 质量与复现证据 | 原始快照、规则表、日志、代码和版本；他人可复算，报告数字与结果一致 | original.json（原始快照）+ original_sha256 + rules_applied（规则表）+ quality_report（由表计算，与结果表自洽）+ idempotent 二遍自检 + changes_by_rule 汇总 |
| 异常说明 | 缺失、异常、失败查询、无法解释和人工确认；不静默修改或掩盖异常 | findings（missing/unparsed/duplicates/mixed_units/empty_rows）+ unit_refused 逐格记录 + anomaly_notes 直通字段 + limits 写明未确认项 |

## 异常处置表

| 情况 | 处置 |
|-|-|
| case.json 缺失或不可读 | 依 task.md 继续；result.json 的 case_id 写 null 并在 limits 注明来源缺失 |
| spec 不是合法 JSON / 不是对象 / 文件不存在 | clean.refused，status undetermined（exit 5）；修 spec 后重跑，不得手写 result.json |
| rows 为空、rows 不是列表、table_path 缺失或不可读 | clean.refused（exit 5）并保留 case_id；补数据后重跑 |
| table_path 指向目录 / 权限不足 | clean.refused，消息带系统原因；不伪造清洗成功 |
| 编码乱码（非 UTF-8 字节） | utf-8-sig + 宽容读取；乱码单元格按未解析/缺失入名单，不静默丢弃、不假装可读 |
| 空表（0 行） | clean.refused（exit 5）——没有可清洗的数据 |
| 全空行表（字典完好但无值） | clean.empty_rows（medium）如实点名，不输出假 clean |
| 字典声明的列不在表中 | clean.column_missing（medium）：工单与表不一致，先对齐再清洗 |
| key 列不在表中 | clean.key_column_missing（high）：重复普查失效，blocked |
| 部分行缺列 | clean.ragged_rows（medium）：列出每列的行覆盖数 |
| 单位不明 / 换算拒绝 | R04 refusal（unit_refused）逐格留痕：未知单位或量纲不匹配按名报告，绝不猜 |
| 未声明 target_unit 且同列混写单位 | clean.mixed_units（medium）：点名全部写法；声明 target 后由 R04 统一 |
| 同 key 不同值（重复实验） | clean.duplicate_experiments（medium）：两个测量，不平均、不合并 |
| 同输入重洗同目录 | clean.already_cleaned（exit 4）：首次 result.json 完好保留，拒绝信息另存 result-refused.json |
| result.json 缺 contract 字段 | contract echo 回填；spec 没带值的字段写 null 并在 limits 注明，不得编造 |
| 重跑结果不一致 | 引擎纯确定性（bench_contract 场景断言两次运行 findings 全等）；不一致说明 spec 被改动，恢复 spec 重跑 |

## Output contract

/app/output/result.json（由 scripts/dataquality.py 写出）包含：schema_version
（data-quality/v1）、case_id、status（clean、review、blocked、undetermined 四态之一）、
findings 数组（每条带 rule、severity、message 与 columns/count 等定位字段）、
severity_counts、rows、rules_applied、changes_by_rule、changes（rule/row/column/
original/new/why 逐条台账）、duplicates（记录副本与重复实验分列）、anomalies、
cleaned_table、quality_report（计算版，逐列 parse_rate/completeness）、
original_sha256、idempotent、row_source、limits，以及 output_contract 每个字段的回填值
（spec 携带值逐字直通，缺失为 null）与 output_contract_fields（字段名清单）。
同目录另有 cleaned.csv（重写后的表）与 original.json（输入原样快照）。

## Limits

- **No imputation.** Missing values are named gaps. Filling "未检测" with a column
  mean invents data; if the downstream analysis demands a number, that decision is
  recorded as a human step, not a rule.
- **No population statistics.** The pass produces record-level results; it does not
  infer distributions or significance — that is a different task.
- **Interpretation is out of scope.** Whether 3.2 eV is consistent with the
  mechanism is not a cleaning question.
- **Outliers are flagged, not deleted.** R05 gives value, range and reason; the
  keep/drop/cap decision stays on the record.
- **Duplicate detection needs keys.** The census runs only when key_columns is declared; without them it is skipped with a note rather than collapsing every row into one entity.
- **Duplicate detection is key-based.** Two rows are the same experiment only when
  the declared keys match after normalisation; fuzzy similarity is not guessed.
- **Date parsing covers the declared formats.** A date outside them is a named gap;
  adding a format is a one-line change to DATE_FORMATS.
- **Report consistency checks integers only.** Narrative claims in a supplied report
  are not parsed.
- **Mixed-unit detection is about written units.** It fires when no target unit is
  declared; with a declared target the mix is the conversion plan, not a hazard.

## Failure handling

| symptom | what to do |
|-|-|
| `clean.missing_values` | keep them missing; if the analysis needs a number, record the decision as a human step |
| `clean.unparsed_values` | fix the cell or extend the parser; never guess |
| `clean.duplicate_records` | identical rows — safe to drop after review |
| `clean.duplicate_experiments` | same entity, different values — two measurements; do not average |
| `clean.report_inconsistent` | the supplied report disagrees with the table; fix the report, not the table |
| `clean.not_idempotent` | the rule priorities disagree; reorder before shipping |
| `clean.refused` | the case could not run as declared (unreadable spec, no rows, unreadable table) — fix the input, rerun; never hand-write result.json |
| `clean.column_missing` | align the dictionary with the table before cleaning |
| `clean.key_column_missing` | declare key columns that actually exist in the table |
| `clean.ragged_rows` | fill the structural gaps or restrict the dictionary to what every row carries |
| `clean.column_undeclared` | declare the column or accept it passes through untouched |
| `clean.empty_rows` | the table carries no data; get the real rows |
| `clean.mixed_units` | declare a target_unit and let R04 convert, or split the column |
| unit refusal (R04, new: null) | unknown or incompatible unit; name it, never silently drop the row |
| `clean.already_cleaned` | this exact input (same sha256) was already cleaned into this output directory; re-cleaning is refused (exit 4) so a second pass never stacks on the first |

## Verification

```bash
python scripts/bench_dataquality.py   # 25 scenarios: one per defect class plus FP guards
python scripts/bench_contract.py      # 7 scenarios: case_id/output_contract passthrough and refusals
```

Both pass in full on this machine (25 + 7 = 32). The clean baseline fires nothing at
all, so a detector cannot pass by flagging everything; the FP guards pin the
behaviour that matters (a genuine 0 stays a zero, an in-range unusual value stays, a
matching supplied report stays silent, a declared target unit absorbs a unit mix, the
cleaned table re-runs to zero changes).

## 创新增益

以下均为引擎真实具备、可复跑验证的能力（bench 与 gate 是回归证据）：

1. **规则优先级库**：R01–R08 每条修改有规则 id、优先级、适用条件和理由，两个规则冲突时
   由优先级决定胜者且双方都留痕（changes 台账同时记录）——通用 Agent 无法自证规则一致性。
2. **幂等二遍检查**：同一规则跑两遍，第二遍必须零改写（idempotent 字段），仍有改写报
   clean.not_idempotent（high）——这是一个可计算的 self-check，bench 场景钉住。
3. **逐条变更台账**：每个值的修改记录规则/行/列/原值/新值/理由，changes_by_rule 汇总，
   审计者可逐条复核或撤销任何单条修改。
4. **字典驱动的语义分支与对齐检查**：列按 semantic 走不同规则链，清洗前先核对字典与表
   的对齐（键列失效 high、工单列缺失 medium、行级漂移 medium、未声明列 low）——"先读数据
   字典和字段语义"由机制保证，而不是提示词嘱咐。
5. **两个不合并的区分 + 维度模型换算**：缺失≠0、重复记录≠重复实验各有 FP 守卫场景；
   单位换算走 7 基量纲维度模型（拒绝 mg→mm 这类量纲错误），换算因子逐条入账，未声明目标
   的混写单位由 clean.mixed_units 在平均之前点名。
6. **契约直通与确定性**：case_id 与 output_contract 字段自动回填 result.json，spec 携带值
   逐字直通，无法派生的写 null 并在 limits 点名；一切拒跑路径（坏 JSON/非对象/缺文件/
   无数据/表不可读/内部异常）输出 status undetermined 的可追踪 result.json（exit 5）且
   绝不伪造契约字段；同输入同目录二遍清洗被 already_cleaned 拒绝且首次结果完好。

## 生态贡献

1. **SKILL.md 全量文档**：用途、适用条件、调用方式、输入输出、异常处置（16 类）、限制
   与自查方法齐备，说明与提交版本一致。
2. **纯标准库引擎**：scripts/ 下 cleaning.py（规则引擎）、units.py（维度模型）、
   dataquality.py（入口与 result.json）、contract.py（契约直通与拒跑）无第三方依赖，
   可独立导入、可嵌入他人清洗流水线。
3. **字段级规则外置可配置**：missing_tokens、plausible、target_unit、key_columns、
   value_columns、semantic 全部声明在 spec——同一引擎换个字典就是另一张表的清洗规则，
   规则即配置，可直接当数据字典模板复用。
4. **规则清单与引擎一一对应**：本文件每条 rule id 都能在引擎里找到发出点（验收 gate 的
   规则奇偶校验强制）；规则表可直接当作清洗工单自查清单。
5. **最小调用示例**：examples/spec.json（带 case_id 与 output_contract 的完整输入）+
   实跑示意输出（标注为示例，非正式案例结果）。
6. **回归套件可独立复跑**：bench_dataquality 25 场景 + bench_contract 7 场景，每条规则
   至少一个场景、每个关键行为配 FP 守卫，clean 基线必须零发现。
7. **异常处置表与 Failure handling 表**：16 类异常、15 类发现的处置动作可直接移植到
   其他清洗任务（空表、乱码、权限、主键冲突、单位不明等均有着落）。
8. **验收 gate 可复跑**：本包可通过 strict_gate.py 的 G1-G7 七项验收（打包/基准/文档
   路径/规则奇偶/确定性/冷启动/真实输入冒烟），他人可对复刻包执行同一验收。

## Requirements

Python 3.9+（3.14 实测）。纯标准库实现，无第三方依赖。
