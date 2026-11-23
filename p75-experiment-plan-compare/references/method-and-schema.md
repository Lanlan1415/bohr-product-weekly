# 方法来源、落地映射与比较复核

## 1. 外部开源案例（2026-11-24 实际查阅）

### pyMCDM — kotbaton/pymcdm（MIT）

- 项目：https://github.com/kotbaton/pymcdm
- 实际阅读：master `README.md` 中 WSM（Weighted Sum Model）、TOPSIS、COMET/SPOTIS、equal weighting、
  min–max normalization、rank correlation 与方法示例。
- 学术来源：Kizielewicz, Shekhovtsov & Sałabun (2023), SoftwareX 22, 101368，
  DOI 10.1016/j.softx.2023.101368。

**方法已落到可执行规则：**

| 参考概念 | 本包具体实现与字段 |
|---|---|
| 方案 × 指标决策矩阵 | `scoring_matrix` 每个候选使用同一 criteria，不允许各写一套字段 |
| benefit/cost 方向 | `direction=max/min` 分别 `(x-min)/(max-min)` 与 `1-(x-min)/(max-min)` |
| 归一化 | 声明 `scale_bounds`；观察范围缺失派生会 review 并提示 rank reversal |
| WSM | `score=100*Σ(normalised×weight)`；逐单元保存 weighted_contribution |
| 权重敏感性 | 每维 ±20% 重排；前两名精确 weight_at_tie；其余权重保持相对比例 |
| 排名不确定性 | 每个声明 lower/upper 单元跑角落情境，记录完整新排名，不假定概率分布 |
| 证据纪律 | 每单元 source/locator/quote/rationale 与计算底稿，不能只给总分 |

本包仅使用透明的 WSM/min–max 思想，不依赖或冒称实现 pyMCDM 的全部 MCDA 方法。
硬门槛必须在 WSM 之前，这是针对正式题面的关键加强：软分不能补偿预算/审批等硬失败。

### pyDOE3 — relf/pyDOE3（BSD-3-Clause）

同时查阅其 `README.md` 与 `doe_factorial.py`，用于确认方案比较与设计生成边界：这里不重排
实验响应或挑选单个 DoE 点，而是比较完整候选路线；原始设计创新不属本题主要贡献。

## 2. 本地已出分包复用与错位修正

- `p72-experiment-feasibility`（75.33）：复用 present/missing/partial、资源台账 locator、审批 pending、
  方案 vs 台账冲突。这里扩大为**所有候选统一硬门控**；不会把单方案可行性包错交本题。
- `p71-experiment-optimize`（66.67）：复用参数/成本/source/locator 和分级结论纪律；这里不做
  单路线参数推荐，而是重算候选成本时间、比较并给备选触发条件。
- `p48-result-interpretation`（65.67）：复用结论回指记录、建议带风险/前提；这里不确定性只
  进入区间情境，不把历史结果解释为当前候选的实测表现。

历史分来自本地 `PASS_RATE_v2.md`，不是本包自报分数。

## 3. 正式 rubric → 可核验落地

| 正式关注点 | 实现 |
|---|---|
| 比较口径统一 | `criteria` 固定 name/direction/unit/weight/scale_bounds；所有候选同一 evidence matrix |
| 约束硬门槛 | `hard_constraints` 先执行；failed/unknown 不排名；全不可行不给推荐 |
| 成本口径完整 | 一次性/per-run/per-measurement，逐项来源；声明值 vs 计算值不一致 high |
| 时间口径完整 | preparation/execution/queue/rework；probability 明示，返回 expected_hours |
| 可行性与当前资源 | 点路径读取 resources；设备/审批/预算/时间失败保留原值和来源 |
| 风险 | 独立风险维度；winner_disadvantages 明确承受的越高风险；触发备选 |
| 证据矩阵 | 每格 raw、normalized、weight、contribution、source/locator/quote、rationale |
| 逐项评分依据 | rationales 缺失 review；无证据 high；未知 source registry ref high |
| 敏感性 | 权重扰动 + 前两名精确翻转阈值 + 证据区间角落重排 |
| 权衡 | winner_advantages、winner_disadvantages、decisive_criteria、score_difference |
| 推荐与舍弃理由 | recommendation 仅合格者；eliminated_plans 逐约束说明 failed/unknown |
| 备选条件 | fallback_plan 明确 runner-up、可观察 trigger/action/target/source，切换时重算门控 |
| 版本与可复算 | plan_versions、plan_sha256、input_sha256、CSV/JSON/MD、确定性排序与 tie finding |
| 原契约与可靠性 | case_id 顶层，引擎 > case 值 > null+limits；0/3/4/5；畸形 spec 无 traceback |

## 4. 复核算术示例（虚构接口示例）

- P1 成本 `40 + 10×6 = 100 CNY`；P2 `80 + 10×13 = 210`；P3 `60 + 10×8 = 140`。
- P1 时间 `2 + 10×0.6 + 3 + 4×0.25 = 12 h`；P2 `3 + 10×1 + 5 + 4×0.5 = 20`；
  P3 `2 + 10×0.8 + 4 + 4×0.5 = 16`。
- 硬预算为 200，因此 P2 无排名，即使其他软指标优秀也不补偿。
- P3 vs P1 在 cost/time/risk 上吃亏，但 scientific_alignment/evidence_strength 占优势；
  输出同时列出两类，而非只列赢者优点。
- 所有数字都是示例固定输入的机械复算，不是实测价格、工时或实验结果。

## 5. 审阅清单

1. 目标、硬约束、criteria 是否在比较任何候选之前固定？
2. 权重总和、原始权重、方向、scale_bounds、weight_basis 是否留痕？
3. 每个成本是否含 setup/per-run，币种是否一致，声明总数是否与底稿一致？
4. 时间是否包含准备、排队和期望返工，是否误称已发生？
5. 每格原值是否有来源、定位和具体评分理由？来源 ID 能否解析？
6. 区间是否可能跨硬门槛？unknown 是否被错误当成 passed？
7. 所有失败方案是否有具体淘汰原因，全部失败时是否停止？
8. 权重扰动和证据区间是否实际重排，而不只是写“做敏感性分析”？
9. 推荐是否承受明确劣势，top tie 是否披露？
10. 备选是否有可观察触发器，切换时要求重算当前门控？
11. output_contract 是否逐字保留，未知字段是否 null+limits？
12. 同输入重跑是否字节一致，是否始终标明未执行实验？
