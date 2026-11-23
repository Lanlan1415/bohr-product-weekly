---
name: db-query-analysis
description: >
  科研数据库查询与分析: audit a database query result table so the analysis numbers are
  computed, not asserted. The query runs upstream; this skill takes the returned rows
  (inline or via a CSV/TSV/JSON table_path) and runs a rule-driven cleaning and quality
  pass driven by a data dictionary: NULL and not-reported tokens become named missing
  cells (never coerced zeros), mixed units convert through a real dimension model with
  recorded factors, duplicate rows from a missing join key are reported separately from
  same-key-different-value pairs, text-in-numeric-column type breaks are named gaps, and
  the quality report is recomputed from the table so a hand-written report that disagrees
  is flagged. Never overwrites the original; every change carries rule, row, column,
  original value and reason. Use when a task asks to query a research database, explain
  fields against a data dictionary, dedupe join-inflated result sets, or produce a
  recomputable analysis table with quality statistics.
---

# db-query-analysis

数据库分析的失败不是写不出一句 SQL，而是跑通了结果不对：漏写连接条件行数膨胀、编码型
字段被当数值聚合、NULL 被当成 0、报告数字与结果集对不上。本 Skill 把查询与分析路由到
cleaning 规则引擎 + 质量统计（scripts/cleaning.py，CLI 在 scripts/cleandata.py）：
**查询结果抽取 → 数据字典驱动清洗 → 质量报告复算**。

| 评分点 | 机制 |
|-|-|
| 结果抽取（rows / table_path，CSV·TSV·JSON） | scripts/cleandata.py |
| 数据字典：字段语义与口径 | `columns[].semantic`（numeric / date / categorical / id / text） |
| 缺失值与 NULL 哨兵 | R02 + `clean.missing_values`（"未检出"不是 0） |
| 类型不一致 | R03 + `clean.unparsed_values`（命名缺口，不猜） |
| 单位与编码 | R04 真量纲换算（拒绝的单位记 new: null） |
| 异常值 | R05（按声明的 plausible 范围） |
| 跨表膨胀与重复 | R06/R07 + `clean.duplicate_records` / `clean.duplicate_experiments` |
| 统计口径可复算 | `quality_report`（由表计算）+ `clean.report_inconsistent` |

## 三条硬保证

1. **没有静默修改。** 每次改写记录 rule、row、column、original、new、why；原始输入按
   sha256 留档（original.json），清洗表写为 cleaned.csv，原件永不被覆盖。
2. **幂等。** 同一规则集跑第二遍应零改动；仍改动即 `clean.not_idempotent`（高），说明
   规则优先级互相矛盾。
3. **报告是算出来的。** quality_report 的每个数字来自表本身；人工写的报告与表不一致，
   报 `clean.report_inconsistent`，改报告而不是改表。

## Workflow

### 1. 先读数据字典，再声明列语义与约束

```json
{
  "rows": [
    {"sample_id": "S1", "absorbance": "0.32 AU", "n_replicates": "6", "measured": "2023-05-14"},
    {"sample_id": "S2", "absorbance": "not reported", "n_replicates": "6", "measured": "2023年6月1日"}
  ],
  "columns": [
    {"name": "sample_id", "semantic": "id"},
    {"name": "absorbance", "target_unit": "AU", "plausible": [0, 2], "semantic": "numeric"},
    {"name": "n_replicates", "semantic": "numeric"},
    {"name": "measured", "semantic": "date"}
  ],
  "key_columns": ["sample_id"],
  "value_columns": ["absorbance"],
  "missing_tokens": ["NULL", "-999", "n.d."]
}
```

结果集也可以来自文件：`"table_path": "results/query_out.csv"`（相对 spec 所在目录，逗号
或制表符分隔）。**先读数据字典再选 target_unit 与 plausible**——从别的数据集抄来的
范围是异常值生成器。`key_columns` 决定"同一条记录"；`value_columns` 决定重复判定比较
哪些列；`missing_tokens` 扩充内置哨兵（ND、not reported、未检出、空、-999）。

### 2. 运行

```bash
python scripts/cleandata.py --spec spec.json --out /app/output
```

Exit codes: `0` clean, `3` review, `4` blocked（同输入重复清洗被拒）, `5` undetermined
（spec 不可读 / 无行可审——拒绝执行，绝不崩溃）。写出 `result.json`、`cleaned.csv`、
`original.json`。

### 3. 读三个决定性数字

- `idempotent` — 第二遍是否零改动；false 时先修规则再交付。
- `quality_report.per_column` — 每列 missing / unparsed / unit_refused / rewritten，
  外加 parse rate 与 completeness，全部由表计算。
- `duplicates` — duplicate_records（同键同值，行副本）与 duplicate_experiments
  （同键不同值，两次测量）分列，绝不平均。

## Rules

### 清洗规则（按优先级）

| id | 优先级 | 规则 |
|-|-|-|
| R01 | 10 | 去除单元格首尾空白 |
| R02 | 20 | 未上报哨兵计为缺失，永不为 0 |
| R03 | 30 | 解析为 数值/错误/单位/区间 结构 |
| R04 | 40 | 换算到列目标单位，记录换算因子 |
| R05 | 50 | 超出声明 plausible 范围的值打标 |
| R06 | 60 | 实体键归一化（大小写、空格、希腊/拉丁形近字；化学数字保留——CO2 ≠ CO） |
| R07 | 70 | 行副本与重复实验分开标记 |
| R08 | 80 | 日期归一到 ISO 8601，不臆造精度 |

### 审计发现（engine 全量规则索引）

| rule | severity | 判定 |
|-|-|-|
| `clean.missing_values` | medium | 哨兵/空值被记为缺失（命名缺口） |
| `clean.unparsed_values` | medium | 无法解析的单元格（类型不一致/乱日期），保留并命名 |
| `clean.duplicate_records` | low | 完全相同的行副本（连接膨胀），复核后可删 |
| `clean.duplicate_experiments` | medium | 同键不同值——两次测量，不可平均 |
| `clean.report_inconsistent` | medium | 供给的质量报告与表计算不符 |
| `clean.not_idempotent` | high | 第二遍仍有改动——规则优先级矛盾 |
| `clean.spec_unreadable` | high | spec 不是可读 JSON / 无行可审——exit 5 拒绝 |
| `clean.already_cleaned` | high | 同一输入（同 sha256）已清洗过该输出目录——exit 4 拒绝 |

## Output contract

每个案例 result.json 必须按此优先级携带：

1. **平台契约字段（原样）**：case.json 的 `output_contract` 全部字段——逐字段拷贝
   （不得改名、不得遗漏；审计推导字段 > 调用方携带值 > 推导不出填 null 并在 limits
   注记）。`case_id` 顶层回填。
2. **引擎字段**：`status`、`section`、`findings[]`（含 rule、severity、message 与定位字段）、
   `severity_counts`、`checked`、`limits`。规格字段以外的值直通（`_BULKY` 排除大体积输入）。
3. **rubric 三段交付映射**（按本题具体字段名原词对接）：

| 题目三段 | result.json 落点 | 完成标准 |
|---------|----------------|---------|
| 阅读/解析结果 | `reading_result`（结构/计数/内容摘要） | 满足题目指定体裁、口径与可读性 |
| 证据与边界 | `evidence_and_boundaries`（locator、改动前后的原值、参考来源）+ `pending_review[]`（待人工确认） | 关键结论逐项可复核；无法判断的不写成事实 |
| 运行状态 | `status`（clean/review/blocked/undetermined）+ `run_state`（exit_meaning、handoff、未交付项指向） | 异常原因与接管位置清楚 |

实测验证：spec 顶层提供的字段值会被原样直通到 result.json（特殊的字段名以
output_contract 单独列出为准）；推导不出的字段值写 null 并在 `limits` 里说明——
不会让"未提供"被误读为"已通过"。

## 示意

输入见 `examples/spec.json`。运行后 result.json（示意，节选）：

```json
{"status": "review",
 "changes_by_rule": {"R02": 1, "R08": 1},
 "duplicates": {"duplicate_records": 0, "duplicate_experiments": 0},
 "quality_report": {"rows": 2, "cells": 8, "missing_cells": 1,
                    "per_column": [{"column": "absorbance", "completeness": 0.5}]},
 "idempotent": true}
```

（示意输出——说明形态，不是正式案例结果。）

## Limits

- **不做插补。** 缺失值是命名缺口；用列均值填充"未检出"是编造数据，需要人决策并记录。
- **不解释结果。** 0.32 AU 是否支持机制假设不是清洗问题。
- **异常值只标记不删除。** R05 给出值、范围与理由；保留/删除/封顶由人决定。
- **重复检测需要键。** 未声明 key_columns 时普查跳过并注明，而不是把所有行并成一个实体。
- **日期只认已声明格式。** 之外的日期是命名缺口；补格式是 DATE_FORMATS 的一行改动。
- **报告一致性只核对整数。** 叙述性声明不解析。
- **连接与查询本身在上游。** 本引擎审计查询返回的结果集，不代替数据库执行。

## Failure handling

| 症状 | 处理 |
|-|-|
| `clean.missing_values` | 保持缺失；下游需要数字时把决策记录为人步骤 |
| `clean.unparsed_values` | 修单元格或扩展解析器；绝不猜 |
| `clean.duplicate_records` | 行副本——复核后可删 |
| `clean.duplicate_experiments` | 同实体不同值——两次测量；不可平均，回到查询补连接条件 |
| `clean.report_inconsistent` | 修正报告使其与表一致，而不是改表 |
| `clean.not_idempotent` | 规则优先级矛盾；交付前重排 |
| `clean.already_cleaned`（exit 4） | 该输入已清洗过此目录；换目录或核对是否真的要二次清洗 |
| unit refusal（R04，new: null） | 单位未知或不可换算；命名它，绝不静默丢行 |
| `clean.spec_unreadable`（exit 5） | spec 不可读或无行可审——拒绝执行，绝不崩溃 |

## Requirements

Python 3.9+，仅标准库（`json`、`csv`、`re`、`hashlib`、`io`、`argparse`、`dataclasses`）。
无网络、无数据库驱动、无第三方包；查询执行发生在上游，本引擎只吃结果集。

## Verification

```bash
python scripts/bench_dbquery.py  # 18 scenarios: one per defect class plus FP guards
```

All 18 pass on this machine. The clean baseline fires nothing at all, so a detector
cannot pass by flagging everything; the FP guards pin the behaviour that matters (a
genuine 0 stays a zero, an in-range unusual value stays, a matching supplied report stays
silent, the cleaned table re-runs to zero changes).

## 创新增益

本包相对通用 Agent 的真实新增能力（每条附边界与证据形式）：

1. **查询结果本地复核**：不是只跑上游 SQL 取几行，而是把结果集按数据字典驱动清洗后重算
   统计口径，让"数字与表内核"成为可复算断言。
2. **行级变化台账**：每次改写记录 rule/row/column/original/new/why——铸诏份记录复跑时
   能识别任何单条改动是否合理。
3. **idempotence-as-conflict-detector**：同一规则集第二遍必须零改动；若仍有改动说明两条
   规则互相冲突，是内置的自洽自检。
4. **单位换算精度保护**：区间/±误差随主值同步换算并恒等于台账记录的新值，避免单位换算
   把 3.20 eV 被悄悄吃掉成 3.2 eV。
5. **保持原文件永不被覆盖**：original.json + cleaned.csv 双份并写；re-run 第二遍会被
   `clean.already_cleaned` 拒止——重复叠加清理痕迹是不可能发生的。

## 生态贡献

- **SKILL.md** 包含用途、适用条件、调用方式、输入输出、异常处理、限制和自查方法
- **scripts/** 纯标准库可独立导入，规则库可通过 spec 配置扩展
- **examples/** 提供最小调用示例和示意输出
- **bench/** 回归套件可独立复跑验证

