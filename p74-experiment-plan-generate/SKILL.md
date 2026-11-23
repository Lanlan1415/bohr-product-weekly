---
name: experiment-plan-generate
description: >
  实验方案生成与优化：把研究目标、原始科研材料、资源/价格/预约约束和最多三个版本化
  候选方案转成可排期、可复核的前瞻性实验计划。保留假设与操作化变量，匹配对照，展开
  有限参数域，复算独立样本量/重复/成本/时间，生成带种子的随机运行顺序、盲法、步骤依赖、
  设备材料、统计计划、判定阈值、安全伦理确认、风险止损与备选、优化循环和版本记录。
  先用设备量程、预算、时间窗和样本上限做硬门控，再按声明的量表/权重比较完整候选设计；
  不从全因子中挑选单个“最优”点，不把预测写成实测。Use for generate_and_revise_plan,
  experiment plan generation, protocol design/revision, DoE planning, or prospective plan
  optimisation with real source and resource constraints. Do NOT use for parameter-only tuning,
  single-plan feasibility review, choosing among already aligned plans without generating/revising
  a protocol, actual experiment execution, or post-hoc result interpretation.
---

# 实验方案生成与优化（前瞻性计划，不执行实验）

本 Skill 的交付不是“准备样品—设置对照—检测分析”的通用提纲，而是 `result.json`、逐步方案、
逐 run 设计矩阵和版本改动台账。它帮助 Agent 完成两件事：

1. 从真实材料生成/修订一个**结构完整且缺口明确**的方案；
2. 对有限参数域和候选版本做**可复算、硬约束优先**的前瞻性优化。

所有输出均带 `lifecycle=planned_not_executed`；不会发生实验、检测、统计分析或安全/伦理审批。
示例中的记录、价格、设备和数值均为接口演示，不是正式案例答案或真实业务凭据。

## Harbor 六步入口

平台把本 Skill 安装为 `/skills/weekly-skill`。原始输入是 `/input/case.json` 与 `task.md`。

### 0. 读原始案例和材料

读取 `case_id`、`output_contract`、研究目标、资源/价格/预约约束和 `task.md` 指向的实际论文、
PDF、表格或历史记录。必须读真实文件并保留页码/章节/表行；不得从文件名或领域标签猜内容。
预约、估价和审批信息仅按案例给定的**前瞻性规划口径**使用，不冒称真实供应商报价、已批准
安全/伦理状态或未来实测响应。

### 1. 先保存诚实的部分结果

在 `/app/work/spec.json` 建立输入；预算紧时先运行一次，使 `/app/output/result.json` 尽早存在。
案例含三个候选版本时逐一保留 `plan_id/version/based_on/changes`；不要只保留最后一版。
缺设备量程、预算、效应量或审批信息时留空并产生 finding/limits，不为得到 clean 而补造。

### 2. 运行真实 CLI

可先尝试原始案例适配器：

```bash
python /skills/weekly-skill/scripts/plan_cli.py \
  --case /input/case.json --out /app/output
```

适配器支持顶层 spec 及 `spec/inputs/input_data/case_data` 包装，识别
`candidate_plans/versioned_candidate_plans/candidates/plans` 和常见目标字段。
如果案例字段与本文 schema 不同，Agent 应按下一节把**实际内容**转换成 `/app/work/spec.json`，
然后运行（不要运行 `examples/spec.json` 代替正式案例）：

```bash
cd /skills/weekly-skill
python scripts/plan_cli.py --spec /app/work/spec.json --out /app/output
```

退出码：**0 clean / 3 review / 4 blocked / 5 undetermined**。所有状态都会写
`result.json`；不可读 JSON、非对象、缺 `case_id/objective`、空/非法参数域、组合数超限等
均为结构化 exit 5 拒绝，不输出 traceback。review/blocked 是已运行但有明确发现，不是崩溃。

### 3. 读发现，回到原输入修正

先读 `findings[]`、`candidate_summaries[].constraint_results` 和 `selected_plan`。
抽取错误要改 spec；原始材料确实没写的内容则保留 finding 并在 `pending_review/limits` 解释。
不得把“材料未提供”改成“已满足”，也不得把 high finding 删除来伪造 clean。
没有版本/来源/运行记录时，只能交付标明缺口的部分方案。

### 4. 复核优化循环与交付物

- `plan.md`：可读的完整方案；
- `design_matrix.csv`：全部因子组合、独立重复、声明的额外对照/中心点和随机运行顺序；
- `change_records.json`：候选源版本改动 + 本次具体设计物化记录；
- `result.json`：原生字段、findings、严重度、检查计数和原 `output_contract` 字段。

下一轮只有在获得**真实 run-level observations** 后才能执行：按 `run_id` 关联结果，检查预注册
阈值，估计效应与不确定度，经专家确认修改参数域，新建 `source_version` 后重跑。优化器自身
不执行这一步，也不声称已有响应。

### 5. 最终契约核对

`case_id` 必须在 result.json 顶层。case 的 `output_contract` 每个字段名逐字保留，优先级为：

> 引擎已推导字段 > case 顶层携带值 > `null` 并在 `limits[]` 指明不可推导原因。

例如输入顶层 `status="fake"` 不会覆盖引擎状态；`caller_note` 可直通；未提供的
`nonexistent_attachment` 返回 null，而不是省略或编造。拒绝路径同样尽可能保留 case_id 和契约。

## 输入 schema

完整的最小可运行示例为 `examples/spec.json`（明确标注虚构演示）。主要字段如下。

### 顶层与三个版本

| 字段 | 必需性与含义 |
|---|---|
| `case_id`, `objective` | 必需；输入标识和统一研究目标 |
| `sources[]` | 实际文献/手册/预实验/历史记录及 locator；示例 ID 不可搬入正式案例 |
| `assumptions[]`, `uncertainties[]`, `pending_review[]` | 明示假设、数值/评分不确定性和专家确认项 |
| `factors[]` | 非空有限参数域；每项 `{name,unit,levels,source,rationale,equipment_id}` |
| `resources` | 可选 `budget{amount,currency,source}`、`time_window_hours`、`sample_limit` |
| `hard_constraints[]` | 其他 `{id,metric,op,value,unit,source}`；支持 `<=,<,>=,>,==,!=,in,contains` |
| `plan_template` | 三版本共享的方案骨架；候选版本下同名字段覆盖模板 |
| `candidate_plans[]` | 省略时为单版本 P1；支持三版本 `{plan_id,version,based_on,changes,source,metrics,evidence,rationales,cost_items,time_items,plan}` |
| `optimization` | `max_combinations`（默认 256，允许 1–1024）和 `criteria[]` |
| `output_contract` | 原案例契约对象或字段名列表；不是让 Agent 随意改名的模板 |

每个 factor 使用下列一种**有限**形式：

```json
{"name":"temperature", "unit":"C", "equipment_id":"EQ-TEMP",
 "levels":[{"value":20,"source":"MANUAL §3","rationale":"低水平"},
           {"value":30,"source":"MANUAL §3","rationale":"高水平"}]}
```

或 `{"name":"temperature","domain":{"min":20,"max":30,"step":5}}`。
Decimal 步进包含上界，避免浮点累加漂移。水平可带独立 source/rationale。
`levels` 为空、step≤0、max<min、NaN/Infinity、重名和组合爆炸均被拒绝。

### 假设、变量、对照与参数依据

`plan_template` 或候选 `plan` 支持：

| 字段 | 每个条目应记录 |
|---|---|
| `hypotheses[]` | `statement`, `primary_outcome`, `falsification`；可检验而非目标复述 |
| `variables[]` | `name`, `role`, `operational_definition/definition`；结局另需 `measurement`；混杂另需 `control_strategy` |
| `controls[]` | `type`, `purpose`, `excludes_confounder`, `condition`；可为 negative/positive/process/dose 等，按目标匹配，不机械要求全部类型 |
| `randomization/randomisation` | `method`, 整数 `seed`, allocation/block 信息；或 `not_applicable + rationale` |
| `blinding` | 谁被盲、编码/揭盲过程；不能盲时写 `status=none/not_feasible + rationale` |
| `steps[]` | `id`, `action`, `depends_on`, `duration_minutes`, 材料设备引用，`parameter_bindings`, `acceptance_criteria`, `failure_action` |
| `materials[]`, `equipment[]` | 名称、规格/型号/量程、`state=present/missing/partial`、source；设备可用 `parameter_ranges` 约束 factor |
| `statistical_plan` | 主要结局、检验/模型、α、缺失、排除标准、软件；多细胞还须 multiplicity；写效应量/CI 与敏感性口径 |
| `decision_thresholds[]` | metric/op/value/unit/source/action_if_met/action_if_not_met |
| `risks[]` | trigger、后果、缓解、fallback、stop_rule；可另记 likelihood/severity/owner/decision_point |
| `safety`, `ethics` | 状态、来源、审批边界；`pending/required_not_approved` 使执行 HOLD；`not_required` 须理由 |

`parameter_bindings` 不替某个步骤暗定一个值：最终步骤显示因子水平数组，执行时由当前
run 的 design_matrix 列取值。步骤依赖做未知引用与环检测，并计算最早开始/结束分钟；
队列、准备和返工可同时纳入独立时间项，避免只算“上机时间”。

### 样本量、重复与对照/中心点

```json
"sample_size": {
  "experimental_unit":"独立培养批次", "n_per_cell":3,
  "technical_replicates":2, "basis":"pilot/历史精度/资源约束依据"
},
"design": {"control_runs_per_replication":0,"center_points":0}
```

- 独立 n 是 `n_per_cell`；技术复测只增加测量数，不能冒充生物学/独立重复。
- `total_independent_runs = cells*n + (extra_controls+center_points)*n`；
  `total_measurements = total_runs * technical_replicates`。
- 每个额外对照每轮的条件必须在 `design.control_conditions[]` 逐一给出；每个中心点的实际
  `design.center_values` 必须给出。缺定义会 high finding，引擎不会猜中点或对照条件。
- 若提供 `minimum_effect/sd/alpha/power/attrition_rate`，仅对**两个独立组**计算双侧正态近似：
  `n=ceil(2*((z_(1-alpha/2)+z_power)*sd/effect)^2)`，再做脱落校正 `ceil(n/(1-attrition))`。
  记录所有输入和公式；声明 n 不足产生 `sample_size.underpowered`。2×2 等多细胞设计拒绝套用，
  应由领域统计人员提供合适计算或明确 pilot 依据。

### 成本、时间与硬门控

候选成本项 `{quantity,unit_cost,currency,basis,source}`，`basis` 为 `per_plan/per_run/per_measurement`：

`total_cost = Σ quantity × unit_cost × basis_multiplier`，不同币种不直接相加。

时间项 `{kind,hours,basis,probability,source}`，kind 明确 preparation/execution/queue/rework：

`total_time_hours = Σ hours × basis_multiplier × probability`。期望返工不是已发生返工。

门控顺序固定：

1. 生成某版本的**整个全因子设计**；
2. 检查设备每个因子水平的量程，以及总成本、总时间、样本上限和其他硬约束；
3. 任一组合失败，整个候选版本不进入加权排序；未知量程/未知成本不是通过；
4. 仅在全部组合通过的版本中按声明 criteria 选择；
5. 全部不可行时 `selected_plan=null`、exit 4，不选择“最不差”的失败方案。

### 优化评分与不确定性

`optimization.criteria[]` 每项：

```json
{"name":"total_cost", "weight":0.2, "direction":"min",
 "scale_bounds":[0,200], "unit":"CNY", "rationale":"统一成本口径"}
```

权重归一化；min/max 归一化后 WSM 得分 0–100。`metrics` 提供 cost/time 之外的候选级数值，
`evidence` 按指标挂来源，`rationales` 解释每个原值。缺原值不补零，缺证据/理由/量表均有 finding。
不给 criteria 时仅按稳定 ID 选首个可行版本，并明确“不是科学最优”。

引擎执行逐指标权重 ×0.8/×1.2、其余权重比例归一化的重排，记录 winner 是否改变。
这是决策敏感性，不是未来响应概率。科学响应未提供时不得虚构响应面或“预测成功率”。

## 输出字段与机械规则

### 原生结果

| 字段 | 内容 |
|---|---|
| `selected_plan` | 目标、假设、变量、对照、参数域、样本量、随机化/盲法、步骤、材料设备、排程、成本、统计、阈值、风险、安全伦理、门控与选择依据 |
| `plan_versions[]`, `change_records[]` | 源版本、基于关系、具体改动与选中设计的物化记录 |
| `candidate_summaries[]` | 每版本每组合的约束原值/要求/状态；失败不被隐藏 |
| `design_matrix[]` | cell、independent_replicate、run_id、run_order、因子水平、已声明额外对照/中心点 |
| `scoring_matrix[]`, `ranking[]` | 每指标 raw/normalised/weight/contribution/rationale/evidence_refs 与排名 |
| `sensitivity_analysis` | 权重扰动及完整重排 |
| `optimization_loop` | 枚举→硬门控→加权→真实结果驱动的下一版本；`actual_results_executed=false` |
| `evidence_and_boundaries` | sources、assumptions、score cells 与科学/审批边界 |
| `pending_review`, `uncertainties`, `limits` | 未确认内容，不写成事实 |
| `status`, `findings[]`, `severity_counts`, `checked`, `run_state`, `reproducibility` | 运行状态、规则定位、退出意义、接管方式、输入 SHA-256 与确定性记录 |

### 主要 finding（high 通常 exit 4；medium/low exit 3）

| 类别 | 规则示例与意义 |
|---|---|
| 设计输入 | `spec.refused`（exit 5）；`candidate.malformed`；输入不可读时绝不 traceback |
| 样本量 | `sample_size.missing/basis_missing/technical_invalid/underpowered/power_model_mismatch/power_inputs_invalid` |
| 假设变量对照 | `hypothesis.missing/not_falsifiable`、`variable.undefined/measurement_missing/confounder_uncontrolled`、`control.missing/incomplete` |
| 分配与盲法 | `randomization.incomplete/rationale_missing`、`blinding.incomplete` |
| 步骤资源 | `steps.missing/incomplete/decision_missing/unknown_dependency/dependency_cycle`、`materials/equipment.missing/provenance_missing/unavailable` |
| 统计判据 | `statistics.incomplete/multiplicity_missing`、`threshold.missing/incomplete` |
| 风险审批 | `risk.missing/incomplete`、`safety/ethics.status_missing/approval_pending/rationale_missing` |
| 成本时间 | `cost.invalid_item/unknown_multiplier/currency_mixed`、`time.invalid_item/invalid_multiplier` |
| 约束选择 | `optimize.no_feasible_plan`、`optimize.criteria_missing`、`criterion.value_missing/evidence_missing/rationale_missing/bounds_derived` |
| 额外设计行 | `design.control_conditions_mismatch`、`design.center_values_missing` |

clean baseline 必须 `findings=[]`；约束淘汰本身可以是有效比较结果，不为了“有 finding”而制造 finding。

## 最小示例与真实验证

运行虚构接口示例：

```bash
cd /path/to/this/skill
python scripts/plan_cli.py --spec examples/spec.json --out /tmp/plan-demo
```

该示例含三个版本、2×2 全因子、每细胞 3 个独立批次和 2 次技术测量，输出 12 个独立 run /
24 次测量，展示 case 值直通和未知契约字段 null+limits。它不是正式测试答案。

本机实际验证命令：

```bash
# Round 1: full bench + clean baseline，75/75
python scripts/bench_generate.py --report examples/bench-report.json
# Round 2: hostile/contract/exit/idempotence，21/21
python scripts/verify_independent.py probe --report examples/probe-report.json
# Round 3: realistic smoke/cold import/determinism，12/12
python scripts/verify_independent.py smoke --report examples/smoke-report.json
```

最新随包报告为 **75/75、21/21、12/12 通过**，覆盖 clean baseline、全因子/样本量/成本/时间/功效算术、
审批与资源、统计与风险规则、输出契约、CLI 0/3/4/5、敌意 JSON/UTF-8、case 适配器、
cold import、双目录字节重跑和真实感 smoke；这些数字只指本地断言，不是平台得分。

## Requirements 与 limits

- Python 3.9+，仅标准库，无网络与第三方依赖；不需要安装 pyDOE3/pyMCDM。
- 读取实际输入/论文由 Agent 完成；本引擎不代替 PDF 抽取，也不从标签补造事实。
- 全因子适合有限小域；默认上限 256，最大 1024。更大问题需另行声明分数/序贯设计、混叠结构
  与预算，不能静默截断笛卡尔积。
- 量程、参数依据、对照是否合理由领域专家判断；引擎核对出处、结构和算术，不证明科学正确。
- 内置功效计算只适用于两个独立组的近似；其他设计不自动计算。
- WSM 和量表是决策助手，不估计因果、成功率或实测效应；权重/证据变化可能改变选择。
- 不执行实验、不做安全/伦理批准、不验证预约/报价真实性、不伪造日志。所有执行前仍需负责人复核。
