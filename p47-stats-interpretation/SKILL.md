---
name: stats-interpretation
description: >
  统计分析与结果解读：读取科研 CSV/TSV、内联表或只读 SQLite，在清洗后的真实表上
  计算描述统计、独立/配对/非参数检验、效应量、置信区间、假设诊断、多重比较和
  Pearson/Spearman；生成与数值一致的结果文字，并审计声明的方向、p 值和引用。
  缺失不补零，重复不静默放大 n，样本量不足和不可定义量标 undetermined，相关不等于
  因果。Use for rigorous statistical computation and prose checking; not for causal proof,
  experimental design, imputation, or prospective sample-size planning.
---

# stats-interpretation（统计分析与结果解读）

本 Skill 不只是“给 p 值”。它把数据字典、清洗记录、分析总体、方法假设、效应量、区间、
多重校正、结果文字和复现指纹放进同一个可复核结果。所有数值来自实际计算；不能计算的
字段为 `null`/`undetermined` 并说明原因，**不把 0、均值或模型输出伪造成观测值**。

## 固定案例与硬件契约

- 当前题面包含完整 Concrete(1030)、Iris(150，显式 bezdek 来源变体)、Wine(178) 数据快照及
  真实 SQLite 场景。读运行时实际文件和字典，不依据标签补答案，不把旧论文基线改名为新
  数据集版本。固定案例由平台提供，本包不携带那些答案。
- 输入 `/input/case.json`、`task.md` 与案例材料；输出 `/app/output`，中间文件 `/app/work`。
  先读 `case_id` 和 `output_contract` 原字段，再构造 spec，并用 `--case` 保证回填。
- 预算：64 次模型请求、900 秒、16384 tokens/响应。Skill 资源最多 50 个 UTF-8 文件、
  单文件 500KB、总量 2MB、无符号链接。先保存诚实部分结果，再改进。

## 六步运行

0. 读案例与字典，逐字记录合同字段。确认因变量、分组变量、独立/配对设计、配对 ID、真实
   主键、单位及分析族；单位不明不能硬算。
1. 选择输入：内联 `rows`，`table_path` 指向 CSV/TSV，或 `sqlite_path` + 一条只读 SELECT。
2. 先明确重复策略。默认 `duplicate_policy=review`：发现记录副本/同键不同值时，推断请求
   返回 undetermined，绝不让重复悄悄放大 n。见下文“重复与设计守卫”。
3. 在 `analyses` 写直接计算请求；需要审句子时把声明放在 `stats`。相关请求放
   `correlations`。没有字典时引擎只做保守类型推断，**不推断主键、单位或研究设计**。
4. 运行：

   ```bash
   python scripts/cleandata.py \
     --spec /app/work/spec.json --case /input/case.json --out /app/output
   ```

   退出码：`0 clean`、`3 review`、`4 blocked`、`5 undetermined`。每条路径都有结构化
   结果；非零不是 traceback，也不代表可以忽略 findings。
5. 修输入、设计或声明后换目录重跑。同输入写同目录被 `clean.already_cleaned` 拒绝，首次
   结果不覆盖，另写 `result-refused.json`。不得为了让审计变绿而改数值口径。
6. 检查 `analysis_results`、`stats_audit`、`assumptions`、`assumption_diagnostics`、
   `analysis_population`、`result_text` 和 limits。确认统计文字只引用实际输出；区间、效应量
   或 p 不可定义时保留 undetermined，不手工补造。

## 输入与数据库

```json
{
  "case_id": "demo-sqlite",
  "sqlite_path": "/input/concrete.db",
  "query": "SELECT cement, strength FROM concrete",
  "max_rows": 100000,
  "correlations": [{"x": "cement", "y": "strength", "method": "pearson"}],
  "output_contract": {"case_id": "id", "correlations": "computed", "result_text": "interpretation"}
}
```

SQLite 由 Python 标准库 `sqlite3` 以 `mode=ro` 和 `PRAGMA query_only=ON` 打开；仅接受
单条 `SELECT`/`WITH`，拒绝多语句和 DELETE/UPDATE 等操作。查询 SQL、表清单、字段、返回行数、
文件 SHA-256 进入 `input_metadata`。返回行数超过 `max_rows` 会拒绝，不静默截断。
CSV/TSV 严格检查表头、编码与超宽行；支持声明编码、BOM/UTF-8/GB18030，实际读取证据入日志。

## 直接分析请求（`analyses`）

| 研究设计 | spec 字段 | 实际输出 |
|---|---|---|
| 两个独立组 | `metric/group_col/test=welch`（两组默认） | n、组均值/SD、Welch t/df/p、b-a 均值差及 95% CI、Cohen d、Hedges g |
| 两独立组秩检验 | `test=mann_whitney` | U、精确小样本或平局校正近似 p、rank-biserial；不伪造均值差 CI |
| 三个及以上独立组 | `test=anova`（多组默认） | F/df/p、eta²、omega²、Cohen f、全部两两比较及真实校正 |
| 多组秩检验 | `test=kruskal_wallis` | H/df/p、epsilon²、平局校正、两两 Mann–Whitney 及校正 |
| 配对设计 | `design=paired/pair_id/group_a/group_b/test=paired_t` | 完整配对数、差值均值/SD、t/df/p、Cohen dz、95% CI |
| 配对秩检验 | 同上，`test=wilcoxon` | 零差剔除、W+/W-、精确或近似 p、matched rank-biserial |
| 自动选择 | `test=auto` | 小样本/JB 非正态走秩检验，否则独立 Welch/ANOVA 或配对 t；记录 `selection_reason` |
| 相关 | `correlations=[{x,y,method:pearson|spearman}]` | 成对完整 n、r、t/df/p、Fisher z 95% CI（适用时）、因果警示 |

`alpha` 默认 0.05，逐请求可覆盖。独立两组 `auto` 在小样本或 JB 诊断拒绝正态时选
Mann–Whitney；多组选 Kruskal–Wallis；配对选 Wilcoxon。自动选择是透明的规则，不把“正态性
未拒绝”说成“已证明正态”，也不宣称秩检验天然回答均值差。若科学问题明确要求某检验，
应直接指定而不是依赖 auto。

### 独立两组最小示例

```json
{
  "case_id": "demo-direct",
  "rows": [
    {"group": "a", "response": 1}, {"group": "a", "response": 2},
    {"group": "a", "response": 3}, {"group": "b", "response": 4},
    {"group": "b", "response": 5}, {"group": "b", "response": 6}
  ],
  "columns": [{"name": "group", "semantic": "categorical"},
              {"name": "response", "semantic": "numeric"}],
  "analyses": [{"metric": "response", "group_col": "group", "test": "welch"}],
  "output_contract": {"case_id": "id", "analysis_results": "computed",
                      "result_text": "numeric interpretation"}
}
```

也可运行 `examples/direct-analysis-spec.json`。示例不冒充平台固定案例结果。

## 重复与分析总体

```json
{
  "key_columns": ["subject"],
  "duplicate_policy": "drop_exact_copies",
  "duplicate_justification": null
}
```

- `review`（默认）：记录副本或重复实验出现时阻断推断结果，输出
  `stats.duplicates_unresolved` 和 undetermined 请求。
- `drop_exact_copies`：只删除同键同值的后续副本；`analysis_population` 记录被删零基行号，
  另写 `analysis.csv`。同键不同值仍然阻断，不会被“去重”掩盖。
- `keep_as_independent` / `keep_replicates`：只有同时提供具体、可审查的
  `duplicate_justification` 才保留全部行；理由进入结果，空理由无效。
- 无 `key_columns`：只报告 key-based duplicate census 无法评价，不伪造“无重复”结论。

`analysis_population` 同时记录输入行、清洗行、实际分析行、重复策略和排除原因；缺失、未解析
和非有限值按分析逐项排除并计数，不补零、不插补。所有推断使用**清洗及显式去重后的表**，不是
单位转换前的原始单元格；`cleaned_table` 仍保留供审查。

## 假设、效应量与多重比较

- 正态性：Jarque–Bera（JB，渐近 χ² df=2），每组或配对差值单独输出；n<8/零方差为
  undetermined。另有偏度/超额峰度提示。**未拒绝不等于证明正态。**
- 方差：Brown–Forsythe（以组中位数为中心的 Levene 形式）输出 F/df/p；Welch 默认不依赖
  方差齐性。 classical ANOVA 中方差诊断显著时给 review finding。
- 均值差：Welch 或配对 t 的 95% CI 以对应 t 分位数计算，是参数不确定区间，不是个体范围，
  也不是 Cohen d 的 CI。无公认区间时不编造。
- 效应量：Hedges g/Cohen d、配对 Cohen dz、eta²/omega²/Cohen f、rank-biserial、epsilon² 均按
  设计输出；方向和 `b-a` 口径明确。
- 多组两两比较：ANOVA 后 Welch，Kruskal 后 Mann–Whitney，默认 Holm。支持
  `bonferroni`、`holm`、`fdr_bh`、`none`，每项给 `p_raw`、`p_adjusted`、`reject`、`m`、`alpha`、`method`。
- 声明族 `stats` 至少两个可重算 p 时也计算 `claim_multiplicity` 和各声明 `p_adjusted`；
  无声明方法默认 Holm，并在 `applied_by` 标明 `engine_default_holm`，不冒充用户已选择。

统计输出设计参考 **statsmodels** 的 `multipletests`（校正 p 与 reject 决策）、
`TTestIndPower` 的功效输入边界和效应量/ANOVA 报告方式，但以纯标准库独立实现，不依赖
statsmodels/SciPy。项目地址：https://github.com/statsmodels/statsmodels 。

### 功效与样本量限制

每个直接分析都有 `power_and_sample_size`：实际可用 n、未提供前瞻效应量/目标功效/分配与
设计假设时 `status=undetermined`，且 `post_hoc_power_computed=false`。本题不做样本量规划；
**不把观测功效当独立证据，不把 p≥0.05 写成等效或证明无效。** 若需 TOST、混合模型、回归、
设计样本量，应在相应的上游方法中另做，本包不伪造其输出。

## 结果文字与声明审计

`result_text` 由计算字段生成，包含检验、统计量、自由度（适用时）、精确 p/小 p 阈值、效应量、
CI 或 undetermined 原因、有效 n、必要限制和“相关不等于因果/显著不等于实际重要”。

`stats` 中的已有结论继续接受四重核对：组方向、显著性措辞、引用值与重算值、声称 p 与重算 p。
多重校正后措辞不一致可触发 `stats.adjusted_significance_mismatch`。方向词法检查有歧义时不猜，
发表前仍需人工确认实际意义及因果设计。

## `result.json` 与文件

| 内容 | 字段/文件 |
|---|---|
| 主分析 | `analysis_results`、`correlations`、`stats_audit`、`descriptives`、`result_text` |
| 诊断 | 每条分析的 `assumptions`、`assumption_diagnostics`、`outliers`、`charts` |
| 数据口径 | `data_dictionary`、`analysis_population`、`analysis_table`/`analysis.csv`（发生显式去重时） |
| 多重比较/功效 | `multiple_testing_families`、`claim_multiplicity`、`power_and_sample_size` |
| 复现 | `original.json`、`cleaned.csv`、`analysis.json`、`run_manifest`、`input_metadata`、`changes` |
| 异常与合同 | `findings`、`pending_review`、`limits`、`case_id`、`output_contract_fields`、合同原字段 |

`schema_version=stats-interp/v3`。可读取 case/spec 的拒绝结果也保留 `case_id` 和全部合同
字段：案例自带值直通，无法推导的产物为 null+limits，绝不缺键或伪装完成。完全没有可读元数据时
`case_id=null` 并说明。

## 异常与退出码

| 情况 | 行为 |
|---|---|
| spec 坏 JSON/非对象/rows 类型错/无行 | `clean.spec_unreadable`，undetermined，exit 5 |
| SQLite 非 SELECT、多语句、无权限、超限 | read-only 失败原因入 findings，undetermined，exit 5 |
| 样本不足、零方差、全平局、无完整配对 | 相应 p/CI/effect 为 null，undetermined；不硬算 |
| 未解决重复 | `stats.duplicates_unresolved`，推断请求 undetermined；按策略处置 |
| JB/Brown–Forsythe 不支持参数假设 | 诊断 finding，review 或改指定非参数方法 |
| 多组/多检验未给出明确族 | 多组直接分析默认 ANOVA+Holm；声明族默认 Holm并标注 engine default |
| 同输入写同目录 | `clean.already_cleaned`，exit 4，首次结果保留 |
| 输出含 NaN/Infinity 或不可序列化 | `stats.output_refused`，不输出伪 JSON |

## 机器可读规则索引

- 清洗：`clean.missing_values`、`clean.unparsed_values`、`clean.duplicate_records`、
  `clean.duplicate_experiments`、`clean.not_idempotent`、`clean.report_inconsistent`。
- 运行：`clean.spec_unreadable`、`clean.already_cleaned`、`stats.internal_refused`、
  `stats.output_refused`。
- 设计与方法：`stats.duplicates_unresolved`、`stats.analysis_malformed`、
  `stats.analysis_undetermined`、`stats.sample_too_small`、`stats.zero_variance`、
  `stats.assumption_normality`、`stats.normality_diagnostic`、`stats.variance_diagnostic`。
- 声明与数值：`stats.direction_mismatch`、`stats.significance_mismatch`、
  `stats.number_not_in_table`、`stats.metric_unknown`、`stats.group_unknown`、
  `stats.p_mismatch`、`stats.claim_malformed`、`stats.missing_ratio_high`。
- 多重/相关/展示：`stats.multiple_comparison`、`stats.groups_omitted`、
  `stats.adjusted_significance_mismatch`、`stats.correlation_malformed`、
  `stats.correlation_undetermined`、`stats.outliers_iqr`。

## 验证

```bash
python scripts/bench_stats.py      # 31 个清洗/声明/契约/旧回归场景
python scripts/bench_statscore.py  # 14 个直接统计与数据库场景
```

本机结果 **31/31 + 14/14**。第二轮敌意/合同/退出码/幂等探针另为 **11/11**；第三轮
30 行三组 SQLite smoke、双冷启动字节一致性，以及独立 Pearson、全 U 分布枚举和手算
配对 t 交叉核验全部通过（仅为本地验收证据，不是正式案例答案）。
独立锚点包括：配对差 `[1,2,3]` 的 `t=2√3, df=2,
p=0.0741799002`；`[1,2] vs [3,4]` 的 Mann–Whitney `U=4, exact p=2/6`；三组秩和
`6,15,24` 的 `H=7.2, p=e^-3.6`；Holm `[.01,.04,.03] -> [.03,.06,.06]`。另以与实现独立的
基本公式复核 Pearson r。`report_stats.json`、`report_statscore.json` 是可重跑证据。

## Limits / Requirements

Python 3.10+（本机 3.14 实测），纯标准库。没有 Shapiro–Wilk、非中心 t 的 d 区间、HL 区间、
混合效应模型或因果识别；这些字段不被捏造。小样本精确秩检验在无平局采用真实分布枚举，平局
使用明示的渐近校正。相关和组间差异不自动支持因果结论，统计显著不等于实际意义。