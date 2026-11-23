---
name: experiment-plan-compare
description: >
  实验方案比较与选择：把同一目标下的多个版本化候选方案放入统一比较口径，逐项重算一次性/
  按次成本及准备、执行、预约排队、期望返工时间，先用设备/耗材/审批/预算/时间窗硬门槛淘汰
  或标未知，再做带方向的 min–max 归一化和加权评分。每个单元保留原值、量纲、尺度、权重贡献、
  文献/手册/报价/预实验定位与评分理由；输出淘汰原因、权衡、精确权重翻转阈值、权重和证据区间
  敏感性、推荐与备选触发条件。Use for aligned_plan_comparison_and_choice, experiment-plan choice,
  protocol MCDA, feasibility/cost/time/risk/evidence comparison, or defensible plan recommendation.
  Do NOT use for original protocol generation, single-plan feasibility assessment, post-hoc data analysis,
  unsupported scoring, or choosing a soft-score winner that violates a hard constraint.
---

# 实验方案比较与选择（硬门槛 + 证据矩阵 + 加权选择）

普通 Agent 常把三个方案各写一遍，却使用三套字段，最后凭语气说“综合推荐”。本 Skill 强制：
**同一目标、同一硬约束、同一指标/单位/尺度、同一证据要求，先门槛后评分。**

推荐只是前瞻性决策：`recommended_for_review_not_execution`。成本估算不是供应商报价，
评分不是实测成功率，MCDA 不证明因果、安全或科学优越性。示例全部为虚构接口演示。

## Harbor 六步入口

### 0. 读取真实案例

读取 `/input/case.json`、`task.md` 及其实际科研材料。固定 `case_id`、研究目标、三个候选版本、
统一资源约束和 `output_contract`。页码、表行、手册章节、预约记录、价格记录、预实验或历史日志
都要作为 locator 保留；不从领域标签推断设备、报价、审批或风险。

### 1. 建立统一比较骨架

先把所有候选转换成相同字段；原始缺失就是缺失，不补零、不赋予“默认安全/可用”。
保留 `plan_id/version/based_on/changes` 和源版本内容哈希。若缺硬约束、权重或尺度，先运行得到
review/blocked 的部分结果，再回原材料核对；不能为使某方案胜出临时改权重。

### 2. 运行 CLI

原始案例适配：

```bash
python /skills/weekly-skill/scripts/compare_cli.py \
  --case /input/case.json --out /app/output
```

适配器支持顶层 spec 及 `spec/inputs/input_data/case_data` 包装，识别常见 candidates/plans
与目标字段。字段不完全匹配时，Agent 按本文 schema 将真实案例转换为 `/app/work/spec.json`：

```bash
cd /skills/weekly-skill
python scripts/compare_cli.py --spec /app/work/spec.json --out /app/output
```

退出码：**0 clean / 3 review / 4 blocked / 5 undetermined**。不可读 JSON、非对象、缺
case_id/objective、少于两个候选、空/非法 criteria、重复 plan_id 等均结构化 exit 5，写
`result.json`，不输出 traceback。findings 导致的 review/blocked 不是运行崩溃。

### 3. 审核门槛与证据，不以总分压过失败

逐个查看 `constraint_results` 和 `eliminated_plans`：

- `failed`：有确定违反，不能进入排名；
- `unknown`：值缺失、类型不可比，或声明的不确定区间跨过门槛，也不能进入排名；
- `passed`：仅在已声明且当前可核验的全部硬门槛内。

随后查看 `evidence_matrix`：每个候选 × 每个指标都应有原值、单位、方向、归一化、权重贡献、
source/locator 和评分理由。抽取错误改 spec；源材料未提供的保留 finding/limits。

### 4. 审核权衡、敏感性与备选

- `tradeoffs` 同时列出赢者优势与**实际承受的劣势**，不能只复述优点；
- `sensitivity_analysis` 给出逐权重扰动排名及前两名精确翻转阈值；
- `uncertainty_analysis` 对声明的 lower/upper 区间逐单元跑角落情境，不假定概率分布；
- `fallback_plan.triggers` 必须是可观察的切换事件与动作，不是“必要时考虑其他方案”。

触发备选时仍需按当前状态重算硬门槛；历史 eligible 不自动等于当下可执行。

### 5. 确认完整交付和原始契约

交付目录包含：

| 文件 | 内容 |
|---|---|
| `result.json` | 原生比较结果、findings、运行记录与全部原 output_contract 字段 |
| `recommendation.md` | 权重、硬门槛、排名、权衡、推荐和备选的审阅版 |
| `comparison_matrix.csv` | 所有候选统一字段的 raw/normalised/weight/contribution/rationale |
| `evidence_matrix.csv` | 每单元 source/locator/quote、计算底稿、评分依据和不确定性 |
| `sensitivity.json` | 权重情境、精确阈值和证据区间角落情境 |
| `change_records.json` | 原改动与本次输入哈希记录 |

`case_id` 必须在顶层。`output_contract` 字段逐字保留，优先级严格为：
**引擎字段 > case 顶层携带值 > null + limits**。引擎状态不可被输入 fake status 覆盖；
未知字段不可省略、改名或编造。拒绝路径也尽可能保留契约。

## 输入 schema

`examples/spec.json` 是完整虚构示例，含三个版本、五个共同指标、四个硬门槛、证据区间和两个
备选触发器。正式案例不得照抄其数值。

### 统一目标、来源与候选

| 字段 | 含义 |
|---|---|
| `case_id`, `objective` | 必需；比较目标和输入标识 |
| `sources[]` 或对象 | source registry；有 registry 时 evidence source_id 必须可解析 |
| `candidate_plans[]` | 至少两个 `{plan_id,version,based_on,changes,plan}`；plan_id 唯一 |
| `criteria[]` | 必需统一评价维度和权重 |
| `hard_constraints[]` | 统一硬门槛；省略会产生 review，而非视为全部通过 |
| `fallback_triggers[]` | `{trigger,action,target_plan_id,source}`；target 必须真实存在 |
| `pending_review[]`, `change_records[]`, `limits[]` | 原文确认项、版本变化和额外边界 |
| `output_contract` | 原对象或字段名列表 |

`plan` 主要字段：

```json
{
  "n_runs":10,
  "resources":{"equipment_available":true,"approval_confirmed":true},
  "metrics":{"scientific_alignment":5,"total_cost":140,"total_time_hours":16,
             "risk_score":3,"evidence_strength":5},
  "evidence":{"risk_score":[{"source_id":"SRC-RISK","locator":"R-01 P3","quote":"..."}]},
  "rationales":{"risk_score":"3/5：比 P1 风险高，但有回退触发器"},
  "uncertainties":{"total_cost":{"lower":120,"upper":160,"source":"SRC-QUOTE"}}
}
```

`evidence` 值可为 source_id 字符串或 `{source_id,locator,quote}` 列表。虽然最终推荐只对合格者
评分，比较矩阵会保留所有候选的统一字段；被淘汰方案仍可由审计者查看，但不获得名次。

### 统一维度与权重

每个 criterion：

| 字段 | 规则 |
|---|---|
| `name` | 必须唯一，与 `metrics` 或 `cost/time` 引擎计算字段对应；点路径可读取 plan/resources |
| `weight` | 非负数，总和>0；引擎归一化并保留 original_weight |
| `direction` | `max` 或 `min`，分别用于收益/成本型指标 |
| `scale_bounds` | `[raw_min,raw_max]` 且 max>min；评分尺度与硬阈值分开。缺失时从当前候选观察范围推导并 review，提示新增候选可能导致 rank reversal |
| `unit`, `weight_basis` | 统一量纲与权重理由 |

min–max 为：benefit `(x-min)/(max-min)`；cost `1-(x-min)/(max-min)`。
超出尺度的原值会 clip 并 finding，不能悄悄改原值。常量指标归一为 1 并注明无区分度。
`score=100*Σ(normalised_i*weight_i)`；同分按 plan_id 稳定排序并标 `recommendation.tie`，
不伪装成明确专家偏好。

### 成本核算（引擎值覆盖声明值）

`cost_items[]` 每项：

```json
{"id":"P3-ASSAY","kind":"consumable","quantity":1,"unit":"run",
 "unit_cost":8,"currency":"CNY","basis":"per_run","source":"SRC-QUOTE"}
```

- `basis=per_plan/per_run/per_measurement`，分别取 1、`n_runs`、`n_measurements`；
- `total_cost=Σ quantity×unit_cost×basis_multiplier`；
- 一次性与 recurring 可显式标记；不同币种不直接相加，需先由案例给出有日期的换算来源；
- 声明 `metrics.total_cost` 与逐项重算不一致产生 high finding，并在结果中保留 declared/computed；
- 只有总数没有 items 会产生 `cost.not_itemised` review，不能声称已独立复算。

### 时间核算（不遗漏排队与返工）

`time_items[]` 每项 `{kind,hours,basis,probability,source}`：

`total_time_hours=Σ hours×basis_multiplier×probability`。

kind 应区分 preparation、execution、queue、rework；返工概率与工时必须来自案例记录，结果叫
**expected total time**，不冒称已发生耗时。声明总数与重算不一致产生 `time.total_mismatch` high。

### 硬门槛与不确定性门控

```json
{"id":"HC-BUDGET","metric":"total_cost","op":"<=","value":200,
 "unit":"CNY","source":"SRC-QUOTE"}
```

支持 `<=,<,>=,>,==,!=,in,contains`。若候选为该 metric 声明 `[lower,upper]`，两端对门槛的
判定不一致时状态变 `unknown` 且不进入排名。这防止“均值满足，但区间上界已超预算”被当成可行。

全部不可行或评分字段不全时 `recommendation=null`、exit 4。任何高证据/算术 finding 也使
推荐状态为 `blocked_by_findings_do_not_execute`，不得当作放行。

## 评分证据、Trade-off 与推荐

`evidence_matrix` 每行字段：

- `plan_id/criterion/raw/unit/direction/scale_bounds`；
- `normalised/weight/weighted_contribution`；
- `evidence[]`（source_id、locator、quote）和 `evidence_refs[]`；
- `rationale`（为什么是这个原值/等级）；
- `calculation`（成本/时间逐项底稿）；
- `uncertainty`（lower/upper/source/meaning）；
- `note/evidence_status`。

推荐明确列出赢者相对 runner-up 的 `winner_advantages`、`winner_disadvantages`、按绝对权重差
排序的 `decisive_criteria`，以及 source refs。示例中 P3 以更高成本、更多时间和更高风险换更强
目标覆盖/证据——这些劣势不会被“综合较好”掩盖。

## 敏感性与不确定性算法

### 权重扰动

默认逐指标 ×0.8/×1.2（可用 `sensitivity.weight_delta` 改，0<delta≤1），其余权重按比例
归一化，完整重排并记录 winner_changed。变化产生 medium finding，推荐不再声称稳健。

### 前两名精确翻转阈值

对每个指标 i，保持其他权重相对比例，计算前两名标准分之差随 `w_i∈[0,1]` 的线性变化，
若根在 (0,1)，输出 `weight_at_tie`、当前权重、赢家和 runner-up。它不是概率置信区间。

### 证据区间角落

对声明的每个 criterion lower/upper 单点替换，其他单元保持基准，完整重排；不假设分布、
不把 corner probe 当 Monte Carlo。无区间时 `assessed=false` 并说明，不生成伪敏感性。
硬门槛区间已在排名前做最坏情形门控。

## 输出契约与规则索引

### 原生字段

`criteria`、`plan_versions`、`constraint_results`、`eliminated_plans`、
`candidate_evaluations`、`scoring_matrix`、`evidence_matrix`、`ranking`、`tradeoffs`、
`sensitivity_analysis`、`uncertainty_analysis`、`recommendation`、`fallback_plan`、
`pending_review`、`change_records`、`comparison_summary`、`findings`、`severity_counts`、
`checked`、`limits`、`reproducibility`、`run_state`。

### 主要 finding

| 类别 | 规则与行为 |
|---|---|
| 输入拒绝 | `spec.refused` exit 5；坏 JSON、少候选、坏 criteria 绝不 traceback |
| 门槛 | `constraint.none_declared/malformed`；失败/未知见 constraint_results；全不可行 `compare.no_feasible_plan` |
| 评分字段 | `criterion.value_missing/bounds_derived/outside_scale`；缺失不补零，推导尺度会提示 rank reversal |
| 证据 | `evidence.missing/unknown_source/rationale_missing`；来源和逐项依据不可省 |
| 成本 | `cost.invalid_item/multiplier_missing/currency_mixed/total_mismatch/not_itemised` |
| 时间 | `time.invalid_item/invalid_multiplier/total_mismatch/not_itemised` |
| 不确定性 | `uncertainty.malformed/invalid_interval/winner_unstable`；区间跨门槛使候选 unknown |
| 敏感性 | `sensitivity.winner_unstable`；权重变化时推荐须条件化 |
| 推荐 | `recommendation.tie`；top tie 不隐藏 |
| 备选 | `fallback.triggers_missing/malformed/no_runner_up`；无合格备选时停止并重设计 |

clean baseline 要求 `findings=[]`。候选被硬门槛正常淘汰不自动构成 finding；这是有效比较，而非程序错误。

## 最小示例与真实验证

```bash
cd /path/to/this/skill
python scripts/compare_cli.py --spec examples/spec.json --out /tmp/compare-demo
```

虚构示例的成本为 P1/P2/P3=100/210/140 CNY，期望时间为 12/20/16 h；P2 因超过 200 CNY
硬预算而无名次，P3/P1 得分 66.8/62.25。输出 15 个证据单元、10 个权重情境、10 个区间情境、
5 个精确阈值和两个备选触发器。这些是接口示例的机械复算，不是平台成绩或真实实验结果。

本机实际验证：

```bash
# Round 1: full bench + clean baseline，78/78
python scripts/bench_compare.py --report examples/bench-report.json
# Round 2: hostile/contract/exit/idempotence，21/21
python scripts/verify_independent.py probe --report examples/probe-report.json
# Round 3: realistic smoke/cold import/determinism，15/15
python scripts/verify_independent.py smoke --report examples/smoke-report.json
```

随包最新报告为 **78/78、21/21、15/15 通过**：clean baseline、成本/时间/公式、硬门槛、区间门控、证据、
权重翻转、全部不可行、tie、fallback、契约、CLI 0/3/4/5/敌意输入、cold import 和字节确定性均覆盖。
这些数字只是本地测试断言，不是平台得分，也不替代正式三案例评测。

## Requirements 与 limits

- Python 3.9+，仅标准库，无网络、无第三方包；不需要安装 pyMCDM。
- 引擎不替 Agent 读 PDF；实际来源抽取和 locator 由 Agent 从原案例材料完成。
- WSM/min–max 对权重、尺度和候选集合敏感；它不能证明科学正确、因果、安全、伦理或未来表现。
- 序数评分必须由领域负责人确认；证据存在性/定位检查不等于证据内容必然真实。
- 返工期望值不是实测；历史价格、预约、设备状态在切换备选时必须重新确认。
- 不做原始方案创新设计、文献综述、结果统计建模或实验执行。若需生成/修订方案，使用生成类 Skill。
