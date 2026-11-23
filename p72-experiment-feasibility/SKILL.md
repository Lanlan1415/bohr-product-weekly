---
name: experiment-feasibility
description: >
  实验方案可行性评估：真实核算多个方案版本的设备、材料、样本、时间与成本，保留
  source 和 locator，区分 feasible / conditional / infeasible。检查七类检查项、
  硬约束、伦理与安全，给出冲突、缺证据项及补救后的复验要求。方案没写的东西绝不
  视为满足，待采购/预约/审批不等于已到位。用于带资源清单、候选版本和约束的审查；
  不用于执行实验、虚构供应商报价/批件，或仅凭文字猜测合规性。
---

# experiment-feasibility

本包的主要入口是 `scripts/feasibility.py`，不是仅检查报告措辞的通用 reproduce 审计。
它逐版本计算需求与实际约束，输出可复核的三级结论。每个值都有来源、算术或
unknown 标记；不同原始版本之间不覆盖、不串参数。

## 运行契约

1. 读取 `/input/case.json` 与 `task.md`，实际打开所指向的方案、设备/采购/预约清单、
   SOP 与伦理材料。保留 `case_id` 和原始 `output_contract`，凭原文提取，不用文件名
   猜事实。中间引用和提取稿写 `/app/work`，最终文件写 `/app/output`。
2. 把**全部**版本（`plan_versions`，也接受 `versions` / `candidate_plans` / 单个 `plan`）
   映射成下面的 spec。若原文没有给出数字或条件，则不写，不自行补齐。每个硬约束
   `source` 必填，并尽可能提供 `locator`；不要杜撰成本、到货时间、样本量或批准状态。
3. 执行：

```bash
python /skills/weekly-skill/scripts/feasibility.py \
  --spec /app/work/feasibility-spec.json --case /input/case.json --out /app/output
```

4. `result.json` 在每个输出契约字段上都落地。优先放引擎已经推导的同名结果；其余
   输入明确要求原样返回的非大体积字段原样保留；无法推导的则是 `null` 加 `limits`，
   不用占位假结果。正常退出码 `0=clean`、`3=review`、`4=blocked`、`5=undetermined`。
   `status` 分别对应 `delivery_status=done/partial/failed`；异常输入写出结构化 JSON。

原型中已产生结果的三个键是：
- `feasibility_review`：每个版本的 `source_version`、`verdict`、七类覆盖、阻塞条件与
  未决条件，以及整体 `conclusion_level`。
- `evidence_and_risks`：逐版本约束值/所需值/source/locator、算术输入、补救与复验路径。
- `confirmation_items`：未通过项逐项对应的待补证据、开工前要求和理由。

原始契约可能选用不同键名，按它自己的字段名保留，不把本包示例键名当成固定答案。

## 输入形状（全部为声明值）

```json
{
  "units": {"total_samples": "samples", "parameter.temperature": "C"},
  "inventory": [{"resource_id": "oven-A", "status": "present",
                  "source": "equipment-ledger rev2",
                  "capabilities": {"max_temperature": {"value": 120, "unit": "C"}}}],
  "hard_constraints": [{"id": "sample-limit", "metric": "total_samples",
                         "op": "<=", "value": 30, "source": "allocations rev1",
                         "category": "time_samples", "locator": "line 4"}],
  "plan_versions": [{
    "plan_id": "plan-v2", "source_version": "protocol@2", "source_locator": "plan §3",
    "hypothesis": "recorded hypothesis", "variables": {"independent": "temperature"},
    "controls": [{"control_id": "baseline", "source": "plan §2"}],
    "judgement_criteria": "recorded acceptance and response rules",
    "steps": [{"step_id": "measure", "independent_runs": 2,
                "sample_units": 6, "device_hours": 1, "person_hours": 1,
                "waiting_hours": 2, "elapsed_hours": 3, "material_quantity": 1,
                "unit_price": {"amount": 100, "currency": "CNY"}}],
    "sampling": {"per_step": true},
    "parameters": {"temperature": 80},
    "parameter_domains": {"temperature": [60, 80, 100]},
    "equipment_requirements": [{"resource_id": "oven-A",
      "capability": "max_temperature", "min_value": 100, "unit": "C",
      "source": "plan §2"}],
    "material_requirements": [{"resource_id": "matrix-A", "quantity": 2,
      "unit": "bottle", "source": "plan §2"}],
    "ethics": {"involvement": {"human_samples": false, "animals": false,
      "personal_data": false, "biohazard": false}, "approvals": []},
    "safety": {"hazards": []},
    "risks": [{"trigger": "out of range", "response": "stop and review", "source": "SOP §7"}]
  }]
}
```

完整可运行的示意输入见 `examples/feasibility-spec.json`。其中的实体、价格、清单
明确都是合成方法示例，不是真实验室、保证交付的报价或正式测试案例的结果。

### 字段与来源

| 项目 | 支持的声明 | 实际判定 |
|-|-|-|
| 通用硬约束 | `{id,metric,op,value,unit,source,locator}` | `<=,<,>=,>,==,!=,in,not_in,contains,not_contains`；metric 缺失或类型错为 unknown |
| 聚合指标 | `total_samples,total_cost,device_hours,person_hours,waiting_hours,elapsed_hours` | 显式步骤算术；也可用 plan 下的 metrics 提供总额。禁止把技术重复当独立样本 |
| 参数与其它指标 | `parameter.<name>`、`metrics.<name>`、`resources.<name>` | 每个版本在自己的数值和单位下检查 |
| 设备 | `equipment_requirements[].resource_id/capability/min_value/unit` | 台账 `present`、`external_confirmed+confirmed`、能力范围分别检查；预约意向不是已到位 |
| 材料 | `material_requirements[].resource_id/quantity/unit` | `available_quantity >= quantity` 才可算在库满足；`external_confirmed` 加确认与货期仅为**计划**供货；不一致单位为 unknown |
| 伦理 | ethics 中的 involvement 与 approvals 数组 | 涉人体样本/动物/个人数据/生物危害时必须有对应审批；pending 不是批件 |
| 安全 | `safety.hazards[].required_controls[]` | 每项已要求的控制都必须 `verified=true`；缺失不推定安全 |
| 七类审查 | 假设变量、对照、设备材料、时间样本、参数范围、风险异常、伦理安全 | 三级为 reported、partial、unknown；不适用也应显式声明，而非默认通过 |

样本量可用步骤 `sample_units * independent_runs` 累加，或用
`sampling.groups[].units * independent_batches`。`technical_replicates` 从不增加独立
样本数；如需独立重复，必须是独立实验单位的来源。成本为
`sum(material_quantity*unit_price*(independent_runs or parallel_runs))`，多币种混合时
拒绝汇总为虚假总价，需有显式换算记录。时间分解为设备、人工、等待与历时四项，
不把等待当人工，不把计划排期当实际预约；设备预约或到货的额外硬约束单独登记。

## 判定与补救（可行优先，不是惩罚分换优）

- `infeasible / blocked`：至少一条硬约束 false、已声明伦理介入却没有适用审批、
  或必要安全控制未核验。不能用好其它指标抵消硬缺陷。
- `conditional / review`：没有已知硬违反，但采购/预约/审批/来源/算术/七类任一未决。
  引擎自动列出 `unresolved_conditions` 与 `confirmation_items`，并提供“更新 source
  version 后对全部版本复验”的补救路径，**不会自动把条件变为通过**。
- `feasible / clean`：所有硬检查通过、七类完整申报且所声明前置条件已核验。对于
  prospective 外协或供应合同，这只是在该声明契约下的规划可行，不是交付或审批保证。

`change_records[]` 保留每个版本的版本号，不修改原始清单。`reproducibility` 记录完整
spec 的 sha256、固定版 CLI 与确定性属性。独立复跑同一 spec 输出相同 bytes。

## 发现项

| rule | severity | 含义 |
|-|-|-|
| `feasibility.hard_constraint_violated` | high | 硬界限、短缺或必要伦理/安全控制违反 |
| `feasibility.constraint_unknown` | medium | 证据、货源、取值、单位或审批处于未知/待确认 |
| `feasibility.coverage_incomplete` | medium | 七类检查项缺申报，不把 missing 写成 pass |
| `feasibility.arithmetic_unknown` | medium | 成本/样本/时间项缺数值，无法完整复算 |
| `feasibility.no_feasible_version` | high | 所有版本均有硬阻塞，不把较不坏称为可行 |
| `feasibility.spec_unreadable` | high | spec/case 非 JSON、非对象、缺少可审版本、计算无法完成；exit 5 |
| `audit.no_section` | high | 仅旧审计 CLI `scripts/secrun.py` 的退出 5 拒绝 |

本引擎对清单之外没有证明的能力、价格、排期、供应商、伦理状态都不作推断。
若某类完全不适用，应写清 `not_applicable` 及理由；不能从“没提到有伦理问题”得出
“伦理已通过”。`source` 是输入的来源记录，不意味着脚本已联网验证真伪。

## 何时改用其它方法

12 列以内的有限离散域的**逐点目标选择/优化**，用约束感知参数优化工具；本包评估的是
“能否开工”，并不准确寻找响应最优点。成熟系统可再接真实库存、排期或审批 API，
但这版离线 CLI 不接入这些系统。`scripts/bench_feasibility.py` 与
`scripts/bench_sections.py` 只是仍保留的旧结构化复查器，不是主要生成流程。

## 验证与参考实现

无需第三方包，Python 3.9+。可选作者自查：运行
`python scripts/bench_feasibility_v2.py`（19 个算术、冲突、审批、契约、拒绝与
确定性场景）以及原有回归测试。自查不是运行时步骤，正式运行时只读真实材料。

落地参考：
- **pymoo Constraint Handling / Feasibility First**
  <https://pymoo.org/constraints/index.html>：可行候选优于任何不可行候选。这里进一步
  区分 unknown 与 false，不将违规硬界限简单换算成一个可加权重分数。
- 本包将样本、成本、时间和七类覆盖作为独立可复算证据，而非仅以文字“建议确认”。

## 生态与局限

CLI、19 场景回归、真实字段模板、逐版本检查记录都可独立复用。默认离线，不读取
个人绝对路径或私有服务，不依赖隐藏的正式答案。若 case 所需的 PDF/工作簿抽取工具
不可用，应在 limits 说明未覆盖的源而不是补写资源。`output_contract` 的拒绝路径也可
通过 `--case` 字段名完整保留；运行失败与信息缺失分开记录。

GITHUB_URL.txt 提供本作品的公开仓库位置；不以此替代运行证据。
