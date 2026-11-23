---
name: experiment-optimize
description: >
  实验参数优化建议：从带来源的有限参数域、设备/材料/安全硬约束和明确响应模型或重复实测，
  确定性搜索可执行候选。包括目标函数与方向、基线、收益/成本多目标评分、搜索预算与停止
  规则、响应定义及容差、独立重复与统计不确定性、Morris 敏感度和权重扰动复排、参数出处
  与可复跑记录。没有可行完备点则拒绝推荐，不把模型预测伪装成实测；用于参数搜索而不是
  随意编造经验最优值。
---

# experiment-optimize

主入口 `scripts/bounded_optimize.py` 直接执行有限域优化；不是只审计已有优化报告。
所有具体系数、范围、基线与实测都来自 case 原文或材料，程序不会从科研常识补齐数值，
不会把目标变成性能实测。

## 实际运行

1. 读 `/input/case.json` 和 `task.md` 指向的实际材料，保存 `case_id`、`output_contract`。
   将原文参数域、单位、约束、响应定义、模型校准记录与 raw-data locator 映射到 spec；
   模型与设备手册分开记录。版本和工作稿放 `/app/work`，答案放 `/app/output`。
2. 每个有限变量必须有 name、kind、source，另可给 locator。有 `values` 则取明确的离散网格；
   连续参数可用 lower、upper、step，对不上网格的端点必须显式允许
   `allow_final_partial_step`，否则拒绝。支持 `categorical` 枚举。
3. 在 spec 声明目标 `{name,direction: maximize|minimize,weight,unit,measurement,tolerance}`。
   响应名字既可为实验响应，也可为 `total_cost`、`total_time_hours`、`total_samples`。
4. 运行：

```bash
python /skills/weekly-skill/scripts/bounded_optimize.py \
  --spec /app/work/bounded-spec.json --case /input/case.json --out /app/output
```

5. 原始 `output_contract` 的每个键均保留：优先使用已经计算出的同名产物，明确要求
   回传的非大体积字段逐项拷贝，不可推导为 `null + limits`。`case_id` 从工作 spec 优先
   回填，其次取原 case。即使拒绝路径，也能从 `--case` 恢复契约字段；没有输入中的字段
   绝不凭空补造。
6. 检查 `findings`、`recommended_parameters`、`candidate_evaluations` 和 `limits`。
   状态为运行结论，不是实验已完成承诺：clean 映射 done，review 映射 partial，blocked 映射 failed；
   CLI 对 `undetermined` 另返回 5。若点仅有模型结果，`recommendation.pending_validation`
   为 true，必须保留待定批准、独立验证与风险说明。

示例输入 `examples/bounded-spec.json` 使用众所周知的 F(60,1.2,-0.006) 合成多项式仅为算式
演示，不是真实论文、设备、报价或已测响应。示意输出只求证形状，禁止冒充固定案例答案。

## 参数、目标与来源

```json
{
  "variables": [{"name": "temperature", "kind": "continuous", "values": [60, 80, 100],
                  "unit": "C", "source": "equipment-file §2", "locator": "row 5"}],
  "hard_constraints": [{"id": "T", "metric": "parameter.temperature", "op": "<=",
    "value": 100, "unit": "C", "source": "equipment-manual rev2"}],
  "response_models": {"yield": {"kind": "polynomial", "intercept": 60,
    "coefficients": {"temperature": 1.2}, "quadratic": {"temperature": -0.006},
    "source": "calibration-file model C"}},
  "cost_model": {"intercept": 10, "coefficients": {"temperature": 0.1},
    "source": "prospective-price-ledger v3"},
  "objectives": [
    {"name": "yield", "direction": "maximize", "weight": 0.7,
      "measurement": "declared measurement method", "tolerance": {"absolute": 0.5}}
  ],
  "baseline": {"parameters": {"temperature": 60}},
  "study_design": {"independent_replicates": 3},
  "search": {"seed": 42, "max_evaluations": 12, "patience": 2,
    "improvement_tolerance": 0.001, "initial_fraction": 0.6}
}
```

完整案例可任意添加 `time_model`、`sample_model`、`observed_runs`。响应多项式支持显式
`intercept`、`coefficients`、`quadratic`、`interactions`（变量名以冒号连接），不偷偷做题
目拟合。多个响应模型分别给出 `source`。`observed_runs` 中的
parameters、responses、source、locator 依次指明其参数、结果与出处，匹配观测优先于相同变量组合的模型响应；每条响应可以是
`[重复值1, ...]`。同一变量的匹配有数值近似容差 `1e-8`，非数值变量精确匹配，避免
`60` 与不完全相同的单位记录混为一谈。凡有实测 run 缺来源，整案结构化拒绝。

硬约束支持 `<=,<,>=,>,==,!=,in,not_in`，metric 可为 `parameter.<name>`、`response.<name>`、
`total_cost,total_time_hours,total_samples` 或显式 `metrics`。资源上限可从
`resources` 的同一命名值生成；相应每一个 cost_model、time_model、sample_model 的
公式输出均乘 `study_design.independent_replicates`，同时记录计算因子。技术重复不能替代
此独立重复。未知响应不会回退为模型猜测。

## 搜索与选择（真实机制）

- 预算由 `max_evaluations` 给定；上限 5000，乘积域总大小超过 20000 cell 会结构化拒绝，
  不会无界展开。未给预算时取 `min(1000, full_grid_size)` 并产生 `budget_defaulted`。
- 先加入合法的 baseline 中的 parameters；较小域穷举，较大域取前缀加**显式 seed**的
  分层 LHS 初始点，再以当前完整可行候选作中心作单变量坐标邻域搜索。
  没给 seed 时用 0 但发出 `seed_missing`，不掩盖来源缺失。
- 停止条件是预算耗尽、每个有限邻点都已检查，或新点评分改进不超过
  `improvement_tolerance` 达到 patience 轮。每轮实际经过的点、来源、预算与停止理由见
  `search_record`，不能仅写一个“运行至收敛”。
- 采用 pymoo 式**可行优先**：`infeasible` 不参与加权评分；只有 gate=feasible 且全部
  目标都可求值的点才可入选。`unknown` 不当作约束满足。冲突候选有归一化 CV，
  类别不一致用有限的非物理 CV=1 提供诊断，不产生 NaN/Infinity JSON。
- 目标方向分开：最大化 `(value-min)/(max-min)`，最小化 `(max-value)/(max-min)`；
  权重归一化后求和，常数指标满分 1。评分覆盖当前完整可行评估池，不代表全局/临床最优。
  收益和成本可以方向相反地同时入目标；`weight_sensitivity` 将每个权重分别乘
  0.8/1.2、重归一化并在**整个**可行候选集重新排名，报告 winner_changed。
- `baseline_comparisons` 用源数据或模型给出原始差值及非零基线的相对差值，不适合比较的
  用 null。若基线与候选都有重复实测，则报告 pooled-SD Cohen d，作为效应量而非因果结论。

## 重复、容差、统计不确定性与 Morris

对与点匹配的观测，计算 `n_independent`、重复值数组、mean、sample_sd、standard_error、
`mean_ci95 = mean ± t(0.975,n-1)*SE`；n=1 不伪造 SD 或 CI，df>30 明示 t 临界值近似 2.0。
`response_models[].sd` 仅作为模型 SD，不代替实验 SD。缺 `measurement` 会报响应容差背景
缺失，数值容差原样保留，禁止自造目标通过结论。

`parameter_sensitivity` 使用 SALib/Morris 的基本效应，沿所选点有限网格改变一个变量：
`EE=(f(x_i+delta)-f(x_i))/delta`，报告 `mu`、`mu_star`、样本 `sigma`、具体点及
gate 状态。网格超过 4 个 levels 只取低/中/高局部筛选；路径少时不将 sigma 当作交互显著性。
它也是重新调用硬约束与响应计算，不是把目标值做形式微分出去。

## 输出与规则

主结果包括 `experiment_plan`、`evidence_and_risks`、`confirmation_items`、
`recommended_parameters`（或无推荐原因）、`objective_declaration`、`parameter_domains`、
所有候选的完整 `gate`，资源公式与响应统计，`sources`、`uncertainty`、`limits`、
`search_trace`、`weight_sensitivity`、`parameter_sensitivity`、
`reproducibility.domain_sha256` 和固定 CLI。输入没有模型或观测能支撑目标时，
`recommendation.status=not_recommended`，原因保留在高严重度 finding。

| rule | 说明 |
|-|-|
| `optimization.no_feasible_complete_point` | high，无同时通过全部界限和完整目标的点，拒绝伪最优 |
| `optimization.spec_unreadable` | high，拒绝结构错误、缺失来源/目标/有限域或过大展开，exit 5 |
| `optimization.validation_required` | low，即使选择合法也不得跳过实验验证 |
| `optimization.budget_defaulted` | medium，未声明搜索预算，写出实际回退值 |
| `optimization.seed_missing` | medium，未声明 seed，写出确定性回退 seed 0 |
| `optimization.response_model_only` | medium，只有显式模型而非已测响应 |
| `optimization.response_tolerance_undeclared` | medium，响应测量方法/容差依据未声明完整 |
| `optimization.baseline_missing` | medium，无可用基线，不声称有改善比例 |
| `audit.no_section` | 仅旧审计入口 `scripts/secrun.py` 的 exit 5 拒绝，主 CLI 不依赖它 |

`0=clean, 3=review, 4=blocked, 5=undetermined`；正常完成模型但不会写成湿实验事实。
输出目录复跑是**幂等计算**，会确定性重写同一结果，而不是叠加数值/指数；相同 spec 与
seed 的两次独立运行应逐字节一致。

## 边界与不适用

这不是任意闭式连续优化器、统计显著性判定器或自动实验执行器。正在使用未校准经验公式时
只能把它标成模型；缺原文单位、设备量程、安全阈值、审批与高危操作细节时交由专家确认，
不得擅自更改约束。外部 PDF/工作簿/计划档的提取工具应在运行环境里实际调用；没法读的
部分必须在 limits 暴露。模型校准数据未提供不会触发联网猜取。

旧 `scripts/secrun.py`、旧 bench 作为兼容性检查仍保留，但不是生成优化建议的主路径。
Requirements：Python 3.9+，仅标准库，无 NumPy 或 SciPy 必需依赖。无网络或第三方安装即可复跑。

## 作者自查与公开方法

可选运行 `python scripts/bench_bounded_optimize.py`（18 场景：已知最优点、上限改最优、
双目标、无模型/无可行解、重复 CI/Cohen d、类别 CV、LHS 复跑、契约拒绝等）；旧 25/51
回归保持可选。自查不是固定案例运行时必需步骤。

具体开源机制来源与落地：
- **pymoo Constraints / Feasibility First**：<https://pymoo.org/constraints/index.html>；
  已实现完整硬约束 gate，代价换租的不可行点不参与多目标排名。
- **SciPy QMC LatinHypercube**：
  <https://docs.scipy.org/doc/scipy/reference/generated/scipy.stats.qmc.LatinHypercube.html>；
  已实现有限网格的分层初始设计和显式 seed；不宣称从连续区间获得自动高维全局覆盖。
- **SALib Morris 源码**：<https://github.com/SALib/SALib/blob/main/src/SALib/analyze/morris.py>；
  已实现 elementary effect 与 mu/mu_star/sigma 的实际重算，并显式说明局部少路径边界。

GITHUB_URL.txt 给出公开作品路径；它不能替代固定案例的真实运行：`candidate_evaluations`
和可复跑的 spec hash 才能支撑复算。
