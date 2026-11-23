---
name: research-data-quality
description: >
  Dictionary-driven scientific table cleaning with explicit missing/zero semantics,
  units, dates, duplicates, range/type checks, CSV encoding validation, before/after
  reconciliation and reversible edit logs. Emits per-expectation validation results
  and a structured result.json preserving case_id plus every output_contract field,
  including honest refusals. Use for dirty research CSV/TSV/inline tables with a data
  dictionary and cleaning workorder. Do NOT use to impute source values, infer population
  statistics, run hypothesis tests, or design experiments.
---

# research-data-quality（科研数据清洗与处理）

把“看起来干净了”变成可逐格证明：输入原值仍在、每次修改有规则依据、最终表上的
quality gate 可以被重算，且台账能实际回滚。**缺失值只标记、不填补；异常只标记、不
擅自删改；重复记录与重复实验不混为一谈。**

## 本题边界与运行时

- 固定案例是已发表聚合表的转录及注入的存储/编码故障，附数据字典、逐指标单位/QC
  规则和清洗工单，不是原始实验。按案例自己的工单执行，不套别的数据集范围。
- **不得推断总体统计，不得填补缺失或无效源值。** `ND`、`<LOQ`、`-999`、空白不是 0。
  运行时没有承诺的 `quality-gold.md`，不要等待、引用或伪造该文件。
- 原始输入在 `/input/case.json` 与 `task.md`。先读实际文件、字典和工单，再构造 spec；
  不按文件名猜科学内容。中间文件放 `/app/work`，最终交付放 `/app/output`。
- 执行预算：64 次模型请求、900 秒、单次响应 16384 tokens。Skill 资源最多 50 个 UTF-8
  文本文件、单文件 500KB、总计 2MB、无符号链接。先保存诚实的部分结果，再改进。

## 六步调用

0. 从 `case.json` 逐字段记录 `case_id` 与 `output_contract`；确定工单要求的动作。
1. 定位真实表和字典。内联记录放 `rows`，CSV/TSV 放 `table_path`；声明各列 `semantic`、
   `target_unit`、`plausible`，真实键放 `key_columns`，重复判值列放 `value_columns`。
2. 把案例自有缺失记号加入 `missing_tokens`。不要把未检测、低于检出限、录入缺失改写为
   数值 0；不要均值/中位数/模型填补。
3. 工单若有旧质量报告，放 `quality_report`，引擎会对供给值和实算值做一致性检查。
4. 运行：

   ```bash
   python scripts/dataquality.py \
     --spec /app/work/spec.json --case /input/case.json --out /app/output
   ```

   退出码：`0=clean`、`3=review`、`4=blocked`、`5=undetermined`。退出码非 0 也可有
   合法、完整的结构化结果；查看 findings 和 limits，不把异常吞掉。
5. 核对 `cleaned.csv`、`validation_results.json`、`before_after` 与 `change_ledger`。
   修复输入或规则后换输出目录重跑。同一输入写同目录会被 `clean.already_cleaned`
   拒绝并保留首次 `result.json`，拒绝详情另存 `result-refused.json`。
6. 确认 `result.json` 的 `case_id` 和 `output_contract_fields` 完整，`idempotent=true`，
   `report_reconciliation.all_match=true`。若合同字段不可推导，其值必须是 `null` 且
   `limits` 给出原因，不得编造一个漂亮字段。

## spec 最小示例

`examples/spec.json` 是可运行的脱敏示例，不冒充正式案例。核心形状：

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
    {"name": "bandgap", "semantic": "numeric", "target_unit": "eV", "plausible": [0, 6]},
    {"name": "measured_on", "semantic": "date"}
  ],
  "key_columns": ["sample_id"],
  "output_contract": {
    "cleaned_table": "清洗表", "quality_report": "质量报告",
    "change_ledger": "变更台账", "anomaly_notes": "异常说明"
  },
  "anomaly_notes": "S2 未报告：保留为 missing，不是 0。"
}
```

```bash
python scripts/dataquality.py --spec examples/spec.json --out /app/work/demo-clean
```

示例实跑为 `review`：一个单位换算、三个日期归一、一个命名缺失和一组同键不同值均
进入台账；`change_ledger` 就是真实的 `changes` 数组，不再被置空。S2 的 `not reported`
原样保留。这里的数值只是脱敏接口示例，不是正式评分答案。

## 规则与字段语义

| 规则 | 实际行为 | 证据 |
|---|---|---|
| R01 空白 | 去首尾空白；分类值折叠内部空白 | row/column/original/new |
| R02 缺失 | 内建及案例声明的 token 归为 missing，真 0 保持测量值 | missing 计数、行定位；不填补 |
| R03 类型 | 数值、误差、区间和文本解析；无法解析保留命名缺口 | unparsed/unit_refused 计数 |
| R04 单位 | 7 基量纲模型，先换算再查范围；未知或异量纲拒绝 | 原单位、目标单位、公式、因子 |
| R05 范围 | 只查字典声明的 `plausible=[lo,hi]`；越界保留待确认，不盖帽、不删除 | 值、范围、规则理由 |
| R06/R07 重复 | 键大小写/空白/连字符归一；同键同值与不同值分组 | 记录副本与键冲突分组、行号 |
| R08 日期 | 支持 ISO、slash、dot、中文日期和月精度；输出 ISO 8601 | 原格式、粒度、原值、新值 |
| R09 报告 | 供给报告与表算报告逐字段比较 | claimed/computed；修报告而非造数据 |

`semantic` 可为 numeric、date、categorical、text 或 id。字典与表先做对齐检查：声明列缺失、
真实键缺失、行级列漂移、未声明列都会分别报告。未声明列原样通过，不静默清洗。

CSV/TSV 还检查重复表名、空表头、超宽行。编码按声明值或 BOM/UTF-8/GB18030 顺序严格
解码，实际编码、分隔符、字节数与文件 SHA-256 写入 `input_metadata`。无法解码、权限不足、
目录冒充文件都是结构化拒绝，不使用 `errors=replace` 悄悄制造乱码。

## 清洗前后、expectation 与可逆台账

### `validation_results`

借鉴 Great Expectations 的 completeness/validity/uniqueness/schema 工作流及 validation
result 思路，但**实现不依赖该包**。每个 expectation 都记录：

- `dimension`、`column`、`parameters`：检查对象与声明阈值；
- `observed_count`、`before_failed`、`after_failed`、`success`、`success_rate`：真实计数；
- `failing_rows`、`evidence`：可回指的行和原因；未声明主键时 uniqueness 明写
  `not_evaluated`，不假装通过。

覆盖 schema、非缺失完整性、声明类型、声明范围、目标单位一致性、记录副本唯一性和
键冲突。`validation_summary` 分别汇总 before/after 失败数；`success` 只评价真实最终表。

### `before_after` 与 `report_reconciliation`

`before_after` 给出清洗前后的行、列、单元格、缺失、未解析、重写、重复计数及差分，
实际修改坐标、增加/删除行数、缺失填补数、输入/输出 SHA-256。当前规则不自动删行、不填补，
对应计数应为真实 0，而不是文档假定。

`report_reconciliation` 另用一次直接 row/cell 遍历核对最终表的 rows/columns/cells/
missing_cells；任何不一致产生 `clean.report_table_mismatch` 高严重度 finding。

### 真实回滚

`reversible_log` 只含真正改写值的 R01/R04/R08；R02/R03/R05 是诊断，不伪称撤销对象。
`scripts/undo_cleaning.py` 按台账逆序恢复原值，遇到台账漂移会拒绝覆盖：

```bash
python scripts/undo_cleaning.py \
  --result /app/output/result.json --out /app/work/restored
```

写出 `restored.json`、`restored.csv` 和 `restoration.json`。只有与 `original.json` 完全
一致才退出 0；无原快照可验证退出 3；失配/错误退出 5。台账达到 2000 条上限时
`reversible_log_complete=false` 且 limits 明说不能验证全量回滚。

## `result.json` 输出契约

| 组 | 字段/文件 |
|---|---|
| 运行状态 | `schema_version=data-quality/v3`、`case_id`、`status`、`findings`、`severity_counts`、`limits` |
| 主结果 | `cleaned_table`、`cleaned.csv`、`original.json`、`input_metadata` |
| 质量结果 | `quality_report`、`validation_results`、`validation_summary`、`before_after`、`report_reconciliation` |
| 证据 | `rules_applied`、`changes`/`change_ledger`、`changes_by_rule`、`reversible_log`、`original_sha256`、`idempotent`、`data_dictionary` |
| 异常 | missing/unparsed/unit_refused/range/duplicate findings、拒绝消息与人工确认项 |
| 合同 | `output_contract_fields` 以及合同原字段：已算保留、案例自带值直通、未知为 null+limits |

**拒绝也有合同纪律。** 可读取的 spec/case 提供 `case_id` 和合同字段时，即使坏表、无行、
SQL/文件读取失败或内部拒绝，仍保留这些键；无法推导的产物字段为 `null` 并在 limits 解释。
没有可读 case 元数据时 `case_id=null`，不虚构标识。

## 题面评分点映射

| Rubric | 可运行落点 |
|---|---|
| 缺失/异常/重复/格式转换/质量报告 | R01-R09、真实主键分组、量纲模型、逐 expectation 结果 |
| 结果正确与完整 | 字典对齐、缺失≠0、重复副本≠重复实验、只读原值和真实前后差分 |
| 可复核与复跑 | original.json、SHA-256、逐格台账、直接重计数、幂等检查、可执行 undo |
| 稳定性与异常 | 编码/表头/权限/空表/未知单位/键冲突/重复运行全为命名状态，退出码固定 |
| 可复用生态 | spec 即数据字典模板，纯标准库引擎、脱敏示例、独立 bench 和回滚工具 |

## 失败处置

| 症状 | 行动 |
|---|---|
| `clean.refused` / exit 5 | 修 spec、表路径、编码、表头或权限后重跑；查看合同字段和 limits，不手写成功结果 |
| `clean.missing_values` | 保持缺口；下游需要数值时记录人工决策，不由本 Skill 填补 |
| `clean.unparsed_values` / unit_refused | 修原值或补充字典映射；不猜单位、不删行 |
| `clean.duplicate_records` | 审查记录副本；本包不自动删除，工单决定去留 |
| `clean.duplicate_experiments` | 同键不同值是独立测量或键冲突；不平均、不合并 |
| `clean.report_inconsistent` | 修供给报告，不能倒改表让数字“对上” |
| `clean.not_idempotent` / report_table_mismatch | 停止交付，修规则和报告一致性后换目录重跑 |
| `clean.already_cleaned` / exit 4 | 使用新输出目录；首次结果未被覆盖 |

## 机器可读规则索引

以下 ID 与引擎发出点一一对应，便于结构化处理而非只靠自然语言：

- 输入/结构：`clean.refused`、`clean.dictionary_refused`、`clean.column_missing`、
  `clean.column_undeclared`、`clean.key_column_missing`、`clean.ragged_rows`、`clean.empty_rows`。
- 值与单位：`clean.missing_values`、`clean.unparsed_values`、`clean.unit_refused`、
  `clean.mixed_units`。
- 重复：`clean.duplicate_records`、`clean.duplicate_experiments`。
- 一致性/恢复：`clean.report_inconsistent`、`clean.report_table_mismatch`、
  `clean.not_idempotent`、`clean.already_cleaned`、`clean.undo_refused`。
- Gate 命名：`schema.columns_present`、`validity.declared_type`、`validity.declared_range`、
  `uniqueness.no_record_copies`；其余 expectation 名称也在 `validation_results` 原样输出。

## 验证与参考落地

```bash
python scripts/bench_dataquality.py  # 25 个规则/FP 场景
python scripts/bench_contract.py     # 10 个合同、拒绝、编码、回滚场景
```

本轮本机结果为 **25/25 + 10/10**。第二轮敌意/合同/退出码/幂等探针另为 **9/9**，第三轮
GB18030 聚合表 smoke、双冷启动字节一致性与 undo 精确回滚通过（这些仅为本地验收证据，
不是正式案例答案）。clean baseline 零
high/medium，真 0、合理范围、匹配报告、目标单位混写均设 FP guard；--case 拒绝回填、
GB18030、重复表头拒绝、台账逆序回滚和独立 undo CLI 都有实测。

参考项目：**Great Expectations 数据质量工作流**（completeness、validity、uniqueness、
schema 与 validation results）。落地是上述逐 expectation 对象、前后失败数、行级证据和
直接重计数，而非只附链接。项目地址：https://github.com/great-expectations/great_expectations 。

## Requirements / Limits

Python 3.10+（本机 3.14 实测），纯标准库。日期仅覆盖已声明格式；数值引用和聚合统计
不属于本清洗题；不做总体推断、缺失插补、因果解释、图表美化、数据库运维或实验设计。