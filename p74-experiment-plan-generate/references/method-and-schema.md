# 方法来源、落地映射与 schema 复核

## 1. 外部开源案例（2026-11-24 实际查阅）

### pyDOE3 — relf/pyDOE3（BSD-3-Clause）

- 项目：https://github.com/relf/pyDOE3
- 实际阅读：master `README.md`；`pyDOE3/doe_factorial.py` 的 `fullfact`、`ff2n`、`fracfact`。
- README 明确列出 general full-factorial、factorial/response-surface/randomized/optimal designs；
  `fullfact(levels)` 按各因子水平数生成编码设计矩阵，`ff2n` 使用 Cartesian product。
- 项目 README 同时说明已归档并建议迁移到 PyDOE；因此本包**不引入其运行时依赖**，也不声称
  支持其全部 DoE 方法。

**真正落地，而非附链接：**

| 参考方法 | 本包实现 | 输出证据 |
|---|---|---|
| 有限因子水平全组合 | `itertools.product`，按声明 factor 顺序展开；Decimal 步进支持连续有限域 | `design_matrix.csv` 每 cell、factor 原始水平 |
| 重复与设计矩阵分离 | 独立 n 展开到 run，技术复测只在测量计数 | `run_id`、`independent_replicate`、`total_measurements` |
| 可复跑分配 | 声明整数 seed 后用独立 `random.Random(seed)` 排列完整 run | `run_order`、`randomization.run_order_generated` |
| 设计边界 | 默认 256 组合、上限 1024；超限结构化拒绝，不静默截断 | `spec.refused`、max_combinations、input SHA-256 |
| 混叠诚信 | 本包只做 full factorial，不冒充分数因子/响应面/最优设计 | SKILL limits；下一轮需真实结果，不伪造响应面 |
| 资源约束下的完整 DoE | 某版本的任一全因子 cell 越过硬门槛，则整个版本不排名 | `candidate_summaries.constraint_results` |

### pyMCDM — kotbaton/pymcdm（MIT，生成题仅借鉴透明 WSM 部分）

- 项目：https://github.com/kotbaton/pymcdm
- 实际阅读：master `README.md` 的 WSM、min–max normalization、equal weights 与方法示例。
- 文献：Kizielewicz, Shekhovtsov & Sałabun (2023), *pymcdm—The universal library for solving
  multi-criteria decision-making problems*, SoftwareX 22, 101368，DOI 10.1016/j.softx.2023.101368。

**落地：**criteria 显式 direction/weight/scale_bounds；硬门控后归一化加权；原始分、贡献、
evidence/rationale 同单元输出；±20% 权重扰动保留完整排名。无响应数据时不创建伪目标函数。

## 2. 本地已出分实验包复用与错位修正

- `p72-experiment-feasibility`（本地汇总 75.33）：复用资源 `present/missing/partial`、方案值 vs
  台账值、参数 source/locator、审批 pending 使执行 HOLD。这里变成**生成时硬门控**，不是
  把可行性审查包错交本题。
- `p71-experiment-optimize`（66.67）：复用参数依据、量程冲突、优化轮次和数据快照。这里新增
  目标→假设/变量/对照→完整 DoE→步骤/统计/风险链；不交付 `section=reproduce` 的参数审计。
- `p48-result-interpretation`（65.67）：复用 run-level 回指、阈值和后续实验绑定原因的纪律；
  本包只声明下一轮需要真实 run_id 观察，不解释尚未存在的结果。

这些分数仅是 `PASS_RATE_v2.md` 的历史平台分，不是本包的声称得分。

## 3. 正式题面/rubric → 原生字段

| 正式要求 | 机械实现 / 字段 |
|---|---|
| 目标→可检验假设与变量 | `selected_plan.hypotheses/variables`；falsification、操作定义、测量、混杂控制规则 |
| 对照排除混杂 | `controls[].purpose/excludes_confounder/condition`；可另加 control_conditions |
| 设备材料、量程、型号、来源、替代边界 | `materials/equipment`、`parameter_ranges`、source/state；缺失不默认可用 |
| 样本量、独立/技术重复 | `sample_size`，功效近似仅限两组，公式和脱落调整全记录 |
| 随机化、盲法 | `design_matrix.run_order`、seed、coding/unblinding、不适用理由 |
| 步骤和排期 | DAG、最早开始/结束、输入输出/acceptance/failure、准备/排队/返工时间 |
| 成本口径 | 逐项 quantity×unit_cost×basis；币种不混加；总价可复算 |
| 参数依据 | 每 level source/rationale，设备范围逐 cell 检查 |
| 统计计划与判定阈值 | primary outcome/test/alpha/multiplicity/missing/exclusion/software + 双向 action |
| 安全、伦理和专家确认 | HOLD、pending_review、状态与来源；不从字段推断批准 |
| 风险与备选 | trigger/consequence/mitigation/fallback/stop_rule |
| 优化循环与版本复核 | plan_versions、change_records、全因子→硬门控→权重→真实 observations 下一轮 |
| 可复现记录 | input SHA-256、无时间戳确定性输出、run_id、CSV/JSON/MD 工件 |
| 不编造已执行实验 | `planned_not_executed`、`measured_response_claimed=false`、run_state false |
| output_contract | case_id 顶层；引擎 > case 值 > null+limits；拒绝无 traceback |

## 4. 交付前 schema 检查

1. `case_id`、目标和 output_contract 是否来自原案例？
2. 三个源版本的 `plan_id/version/based_on/changes` 是否均保留？
3. 每个因子是否有有限水平、单位、依据与设备范围？组合数是否低于显式上限？
4. 独立 n、技术复测、额外对照/中心点是否分开且条件具体？
5. 随机顺序是否可复跑，盲法不适用的理由是否记录？
6. 每步是否有依赖、时长、资源、验收和失败动作？是否有环？
7. 成本和时间是否能逐项复算，是否含排队和返工？
8. 主要结局、模型、α、多重性、缺失、排除和阈值是否预先声明？
9. 风险是否有可观察触发、止损和备选？安全/伦理/设备确认是否未决？
10. 高分版本是否所有 cell 都过硬门槛？全部不可行时是否停止而非硬选？
11. findings 是否逐项处理，未知契约字段是否 null+limits？
12. 重跑 result.json 是否字节一致，是否从未写入实际实验已执行的假声明？
