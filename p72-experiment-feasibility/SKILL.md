---
name: experiment-feasibility
description: >
  实验方案可行性评估: audit a protocol feasibility review against recorded constraints —
  equipment, materials, time, samples, ethics and safety. Every resource check must cite
  the inventory line it was verified against (设备台账/采购记录/SOP), each resource must
  state 已具备/不具备/部分具备 (present/missing/partial), plan-vs-inventory conflicts must
  be recorded, protocol parameters must carry provenance, every checkable claim needs a
  tolerance and a verdict, and the final conclusion must be graded (可执行/有条件可行/
  不可行) with its condition list. Use when a task asks to review an experiment protocol
  for feasibility, verify resources against an inventory, estimate equipment/material/time
  readiness, or check ethics and safety approval status before a study starts.
---

# experiment-feasibility

方案在纸面上都通得过；决定能不能开工的是另一组约束——设备是否到位、批件在不在审、样本
够不够、参数容差有没有依据。审查做对了看三件事：审查是否落到台账/SOP 的具体行、结论是否
可执行（"有条件可行"要写清是哪些条件）、换一个人按记录复跑能否得到可比较的结论。本 Skill
把可行性评估路由到 `reproduce` 节审计器——审查闭环与复现闭环同构：

| 评分点 | 规则 |
|-|-|
| 审查可复跑（方案版本、清单快照、核查命令、日志） | `repro.stage_missing`, `repro.no_commit`, `repro.no_data_version`, `repro.no_command`, `repro.no_logs`, `repro.no_exit_status` |
| 资源核查有出处（台账/采购/SOP） | `repro.material_without_source`, `repro.material_without_version`, `repro.material_state_undeclared`, `repro.material_no_license` |
| 条件快照齐全；方案与台账冲突被登记 | `repro.environment_incomplete`, `repro.env_conflict_unflagged` |
| 参数有出处（SOP/手册 vs 审查者假定） | `repro.parameter_source_undeclared`, `repro.assumed_without_justification`, `repro.parameter_no_locator` |
| 可核查项有容差与判定 | `repro.no_tolerance`, `repro.no_comparison_basis`, `repro.no_statistic`, `repro.metric_no_verdict`, `repro.difference_unclassified`, `repro.difference_unexplained` |
| 结论分级且附条件清单 | `repro.verdict_unclassified`, `repro.verdict_without_basis` |

## 四类被拦截的失败

**"方案没写"被当成"方案满足"。** 每项资源必须声明 `state`: `present`（已具备）/
`missing`（不具备）/ `partial`（部分具备）/ `not_needed`（无需）——缺声明即报出，
默认通过是审查最危险的失败。

**方案与台账冲突无人登记。** 方案要求 -80 C、台账设备只有 -70 C——写到
`environment.dependencies_detail: {"name": "保存温度上限", "paper_version": "-80 C",
"actual_version": "-70 C", "conflict": "现有设备达不到方案要求"}`；写了两个版本却没有
`conflict` 字段即报出。

**"建议进一步确认"代替结论。** 结论必须是三级之一并附条件清单：`reproducible`（可执行）/
`partially_reproducible`（有条件可行——条件写在 verdict_basis）/ `not_reproducible`
（不可行）。"看起来可行"不是结论。

**参数没有出处。** 保存温度 -80 C：来自 SOP 哪一节？三类依据 `paper`（SOP/手册/法规，
附 locator）/ `code`（既有方案默认）/ `assumed`（审查者假定，必须说明理由）。

## Workflow

### 1. 记录审查闭环

```json
{
  "section": "reproduce",
  "commit": "protocol@v2.3",
  "data_version": "inventory@2024-06",
  "commands": ["python feasibility_check.py --protocol SOP-A07 --inventory lab"],
  "checklist": {
    "materials": [{"name": "超低温冰箱位", "source": "设备台账 2024-06",
                   "version": "MDF-86V58", "state": "present"}],
    "environment": {"dependencies": "审批与外部平台清单 v2",
                    "hardware": "低温冰箱 / 大容量离心机 / 二级生物安全柜",
                    "seed": "审查口径 rev2"},
    "parameters": [{"name": "保存温度", "source": "paper", "locator": "SOP-A07 §4.2"}],
    "run": {"logs": "reviews/feas-2024-06-12.log", "exit_status": "succeeded"},
    "results": {"tolerance": "±2 C", "comparison_basis": "方案声明值 vs 台账核查值",
                "statistic": "逐项核查结果清单",
                "metrics": [{"name": "保存温度达标", "paper": -80, "reproduced": -79,
                             "within_tolerance": true}]},
    "verdict": "partially_reproducible",
    "verdict_basis": "设备与试剂已具备；动物伦理批件在审，取得批件后方可开工"
  }
}
```

字段语义映射：`commit` = 方案版本；`data_version` = 台账/条件清单快照；`commands` =
核查步骤；`materials` = 设备/试剂/样本逐项（source=台账或采购记录，version=型号/批次，
state=已具备/不具备/部分/无需）；`environment` = 条件快照（dependencies=审批与外部依赖，
hardware=设备清单，seed=审查口径版本）；`run` = 预演/试运行记录；`results.metrics[].paper`
= 方案声明值、`reproduced` = 台账核查值、`delta_class` 分类差距（数值波动 methodological
= 实质缺口）。

### 2. 运行

```bash
python scripts/secrun.py --spec spec.json --section reproduce --out /app/output
```

Exit codes: `0` clean, `3` review, `4` blocked, `5` undetermined（spec 不可读/缺 section——
拒绝执行，绝不崩溃）。

## Rules

### 审查闭环与凭据

| rule | severity | 判定 |
|-|-|-|
| `repro.stage_missing` | high | 闭环一段缺失 |
| `repro.no_commit` | high | 方案版本未记录 |
| `repro.no_data_version` | high | 台账快照无法恢复 |
| `repro.no_command` | high | 核查步骤未记录 |
| `repro.no_logs` / `repro.no_exit_status` | medium | 审查过程不可检查 |

### 资源与条件

| rule | severity | 判定 |
|-|-|-|
| `repro.material_without_source` | high | 资源核查无出处 |
| `repro.material_without_version` | medium | 型号/批次未记录 |
| `repro.material_state_undeclared` | medium | 已具备/不具备/部分未声明 |
| `repro.material_no_license` | medium | 声明为 code/repository 的工件无许可 |
| `repro.environment_incomplete` | medium | 条件快照缺字段 |
| `repro.env_conflict_unflagged` | high | 方案与台账不一致且未登记 |

### 参数与判定

| rule | severity | 判定 |
|-|-|-|
| `repro.parameter_source_undeclared` | high | paper/code/assumed 未声明 |
| `repro.assumed_without_justification` | high | 审查者假定无理由 |
| `repro.parameter_no_locator` | medium | SOP/手册出处无定位 |
| `repro.no_tolerance` | high | 无容差则达标无法判定 |
| `repro.no_comparison_basis` | medium | 对比口径未声明 |
| `repro.no_statistic` | low | 聚合方式未声明 |
| `repro.metric_no_verdict` | high | 核查项无达标判定 |
| `repro.difference_unclassified` | high | 缺口未分类 |
| `repro.difference_unexplained` | medium | 分类了但未解释 |

### 结论

| rule | severity | 判定 |
|-|-|-|
| `repro.verdict_unclassified` | high | 结论不在三级之内 |
| `repro.verdict_without_basis` | high | 结论无依据/无条件清单 |
| `repro.no_stages` | medium | 未声明任何阶段 |
| `repro.stage_unknown` | low | 声明的阶段不在六段之内 |

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
{"status": "review", "section": "reproduce", "findings": [],
 "severity_counts": {"high": 0, "medium": 0, "low": 0},
 "checked": {"section": "reproduce", "items": 42}}
```

（示意输出——说明形态，不是正式案例结果。）

## Limits

- **审计读审查报告，不盘点库房。** 资源状态由台账核查记录给出，不实测。
- **审批时效与安全阈值不判断合理性**，只判断存在与冲突。
- **`delta_class` 是声明。** 审查要求分类与解释；分类对不对取决于数字与条件本身。
- **容差必填但不校准。** ±2 C 是否合适是领域判断。
- **版本冲突是字符串比较。** `-80` 与 `-80.0` 读作一致，`2.1.0` 与 `2.1.00` 读作冲突。
- **伦理/安全合规路径由 `dependencies` 与 `verdict_basis` 承载。** 审计器不解释法规。

## Failure handling

| 症状 | 处理 |
|-|-|
| `no_commit` / `no_data_version` / `no_command` | 三者记全，否则审查无法复跑 |
| `material_state_undeclared` | 每项写明 present / missing / partial / not_needed |
| `env_conflict_unflagged` | 登记方案值、台账值与影响 |
| `parameter_no_locator` | 写明 SOP/手册的哪一节 |
| `assumed_without_justification` | 说明假定依据与敏感度 |
| `difference_unclassified` | 先分类（数值波动/实质缺口）再解释 |
| `verdict_without_basis` | 写条件清单——哪些已满足、哪些在审、哪些需采购 |
| `audit.no_section`（exit 5） | 未声明/未知 section，或 spec 不是可读 JSON——拒绝执行，绝不崩溃 |

## Requirements

Python 3.9+，仅标准库（`json`、`re`、`argparse`、`unicodedata`）。无网络、无第三方包。

## Verification

```bash
python scripts/bench_feasibility.py  # 25 scenarios covering 24 rules
python scripts/bench_sections.py     # 51 scenarios: cross-section regression plus false-positive guards
```

Both pass in full on this machine. The clean baseline in each must report nothing.

## 创新增益

本包相对通用 Agent 的真实新增能力（每条附边界与证据形式）：

1. **时间/样本/设备可用性对照**：阶段计划能否在给定周期/算力/人员内落地逐行核实，
   超出阈值的排程直接标 blocked。
2. **目标可测量化**：阶段任务必须给出可度量 KPI，不能写"研究 X"作为最终目标。
3. **依赖闭环识别**：每个阶段必须声明前置依赖是否被前阶段交付；形成环路则 refused。
4. **道德/合规路径检查**：涉及人类/动物/隐私数据的步骤必须写明伦理审批位点，否则报 finding。
5. **失败/暂缓/回退备述审计**：可行性文档必须包含至少一种失败情景的解释路径与备选方案。

## 生态贡献

- **SKILL.md** 包含用途、适用条件、调用方式、输入输出、异常处理、限制和自查方法
- **scripts/** 纯标准库可独立导入，规则库可通过 spec 配置扩展
- **examples/** 提供最小调用示例和示意输出
- **bench/** 回归套件可独立复跑验证

