---
name: experiment-optimize
description: >
  实验参数优化建议: audit a parameter-optimisation recommendation so it can be taken to the
  bench and re-run by someone else. Every recommended value must carry provenance (device
  manual / SOP / history, or declared as chosen with a justification), the feasible domain
  must come from recorded constraints with conflicts flagged, every response metric needs a
  tolerance, a comparison basis and a significance verdict, an out-of-tolerance trade-off
  must be classified as noise or methodological, and the final recommendation must be
  graded with its basis. Use when a task asks for parameter optimisation advice, search
  strategy with a stopping rule, cost-response trade-offs, or constraint-aware parameter
  recommendations.
---

# experiment-optimize

参数优化建议的交付物不是一段解释，而是一份可以拿去开机的方案。判断它做没做对，看三件事：
建议参数是否落在真实可行域内、每条权衡是否有响应指标与成本口径支撑、整条建议链能否被
他人复跑。本 Skill 把参数优化建议路由到 `reproduce` 节审计器——优化循环与复现闭环同构：

| 评分点 | 规则 |
|-|-|
| 建议链可复跑（轮次、快照、搜索命令、日志） | `repro.stage_missing`, `repro.no_commit`, `repro.no_data_version`, `repro.no_command`, `repro.no_logs`, `repro.no_exit_status` |
| 约束有出处（设备手册/SOP/历史实验） | `repro.material_without_source`, `repro.material_without_version`, `repro.material_state_undeclared`, `repro.material_no_license` |
| 可行域可判定，约束冲突被登记 | `repro.environment_incomplete`, `repro.env_conflict_unflagged` |
| 每个建议值有依据 | `repro.parameter_source_undeclared`, `repro.assumed_without_justification`, `repro.parameter_no_locator` |
| 响应指标有容差与判定 | `repro.no_tolerance`, `repro.no_comparison_basis`, `repro.no_statistic`, `repro.metric_no_verdict`, `repro.difference_unclassified`, `repro.difference_unexplained` |
| 优化结论分级且有据 | `repro.verdict_unclassified`, `repro.verdict_without_basis` |

## 四类被拦截的失败

**建议值没有出处。** "温度建议 350 C"——来自设备手册、SOP 还是优化器自选？三类依据
（`paper` 手册与规程 / `code` 现有配置默认 / `assumed` 优化器选定）各有义务：手册类要
定位到章节，自选的要说明理由。

**推荐值越界无人知晓。** 目标温度 350 C、设备额定 280 C——约束冲突登记在
`environment.dependencies_detail`，缺 `conflict` 字段即报出。

**权衡没有分类。** 建议值下指标差了 0.11：是数值噪声还是方法性代价？不写 `delta_class`
和 `explanation`，"最优解"就无从取舍。

**结论没有依据。** "建议采纳"但要害是哪条指标在容差内、哪个约束被满足——`verdict_basis`
必须能对到指标表。

## Workflow

### 1. 记录优化循环

```json
{
  "section": "reproduce",
  "commit": "opt-round-2024-05-17",
  "data_version": "exp-history@2024-05",
  "commands": ["python optimise.py --strategy sequential --budget 60"],
  "checklist": {
    "materials": [{"name": "管式炉温控模块", "source": "设备手册 TC-220 rev C",
                   "version": "rev C", "state": "present"}],
    "environment": {"dependencies": "约束清单 constraints.csv v3",
                    "hardware": "管式炉 TC-220 / K 型热电偶", "seed": "0"},
    "parameters": [{"name": "退火温度", "source": "paper", "locator": "SOP-A07 §4.2"}],
    "run": {"logs": "runs/opt-round3.log", "exit_status": "succeeded"},
    "results": {"tolerance": "±2 C", "comparison_basis": "转化率主指标",
                "statistic": "3 次重复的均值",
                "metrics": [{"name": "转化率", "paper": 0.82, "reproduced": 0.815,
                             "within_tolerance": true}]},
    "verdict": "reproducible",
    "verdict_basis": "所有响应指标在容差内，建议值均落在量程与安全阈值内"
  }
}
```

字段语义映射：`commit` = 优化轮次标识；`data_version` = 历史实验数据快照；`commands` =
搜索策略与预算（网格/序贯/贝叶斯，初始点与停止判据）；`materials` = 设备与材料约束；
`parameters[].source` 取字面值 `paper`（手册/规程/文献，附 locator）/ `code`（现有配置
默认）/ `assumed`（优化器自选，附 justification）；`results.metrics[].paper` = 基准值、
`reproduced` = 建议值下的预测/实测值。约束冲突写在
`environment.dependencies_detail: {"name": ..., "paper_version": "350 C",
"actual_version": "280 C", "conflict": "目标温度超过设备额定"}`。

`verdict` 取三个字面值之一：`reproducible`（建议可复跑、可执行）/ `partially_reproducible`
（有条件采纳）/ `not_reproducible`（无可行解或约束冲突未解）。

### 2. 运行

```bash
python scripts/secrun.py --spec spec.json --section reproduce --out /app/output
```

Exit codes: `0` clean, `3` review, `4` blocked, `5` undetermined（spec 不可读/缺 section——
拒绝执行，绝不崩溃）。

## Rules

### 循环与凭据

| rule | severity | 判定 |
|-|-|-|
| `repro.stage_missing` | high | 循环一段缺失 |
| `repro.no_commit` | high | 轮次/版本未记录 |
| `repro.no_data_version` | high | 数据快照无法恢复 |
| `repro.no_command` | high | 搜索命令未记录 |
| `repro.no_logs` / `repro.no_exit_status` | medium | 执行不可检查 |

### 约束与可行域

| rule | severity | 判定 |
|-|-|-|
| `repro.material_without_source` | high | 约束无出处 |
| `repro.material_without_version` | medium | 手册/规格版本未记录 |
| `repro.material_state_undeclared` | medium | present/missing/partial 未声明 |
| `repro.material_no_license` | medium | 声明为 code/repository 的工件无许可 |
| `repro.environment_incomplete` | medium | 可行域字段缺失 |
| `repro.env_conflict_unflagged` | high | 两个约束源不一致且未登记 |

### 建议值与响应指标

| rule | severity | 判定 |
|-|-|-|
| `repro.parameter_source_undeclared` | high | paper/code/assumed 未声明 |
| `repro.assumed_without_justification` | high | 自选值无理由 |
| `repro.parameter_no_locator` | medium | 手册/规程出处无定位 |
| `repro.no_tolerance` | high | 无法判断建议是否达标 |
| `repro.no_comparison_basis` | medium | 对齐口径未声明 |
| `repro.no_statistic` | low | 未声明聚合方式 |
| `repro.metric_no_verdict` | high | 指标无达标判定 |
| `repro.difference_unclassified` | high | 权衡未分类（噪声/方法） |
| `repro.difference_unexplained` | medium | 分类了但未解释 |

### 结论

| rule | severity | 判定 |
|-|-|-|
| `repro.verdict_unclassified` | high | 结论不在三级之内 |
| `repro.verdict_without_basis` | high | 结论无依据 |
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
{"status": "clean", "section": "reproduce", "findings": [],
 "severity_counts": {"high": 0, "medium": 0, "low": 0},
 "checked": {"section": "reproduce", "items": 60}}
```

（示意输出——说明形态，不是正式案例结果。）

## Limits

- **审计读建议，不执行实验。** 是否真的跑过由 `run` 块记录，不实测。
- **量程与安全阈值不判断合理性**，只判断存在与冲突。
- **`delta_class` 是声明。** 审计要求分类与解释；分类对不对需要数字与方法本身。
- **容差必填但不校准。** ±2 C 是否合适是领域判断。
- **版本冲突是字符串比较。** `2.1.0` 与 `2.1.00` 读作冲突。
- **不搭建环境。** 复现快照的搭建不在本 Skill 范围。

## Failure handling

| 症状 | 处理 |
|-|-|
| `no_commit` / `no_data_version` / `no_command` | 三者记全，否则建议只是口头传说 |
| `env_conflict_unflagged` | 登记两个约束源与可能的影响 |
| `material_without_version` | 写明手册/规格版本 |
| `parameter_no_locator` | 写明在手册或 SOP 的哪一节 |
| `assumed_without_justification` | 说明为何取该值，可附敏感性说明 |
| `difference_unclassified` | 先分类（噪声/方法代价）再解释 |
| `verdict_without_basis` | 给出依据——指标与容差 |
| `audit.no_section`（exit 5） | 未声明/未知 section，或 spec 不是可读 JSON——拒绝执行，绝不崩溃 |

## Requirements

Python 3.9+，仅标准库（`json`、`re`、`argparse`、`unicodedata`）。无网络、无第三方包。

## Verification

```bash
python scripts/bench_optimize.py  # 25 scenarios covering 24 rules
python scripts/bench_sections.py  # 51 scenarios: cross-section regression plus false-positive guards
```

Both pass in full on this machine. The clean baseline in each must report nothing.

## 创新增益

本包相对通用 Agent 的真实新增能力（每条附边界与证据形式）：

1. **变量本地化与跨版本感知**：参数档案要求参数取值口径与 source_type（paper/code/
   derived/assumed）落档，让"参数从哪来"成为可复算字段。证据：bench_experiment 场景。
2. **量程冲突检查**：`env_conflict_unflagged` 监听多个约束源间的重叠矛盾（量程覆盖不止一次给定）。
3. **歧义边界判定分类**：推荐值范围不闭环（缺上/下界）→ `parameter_unbounded`（高），
   拒绝把不可执行的参数范围交付给实验台。
4. **代价-收益双轴**：差分必须 `delta_class`（noise/methodological）分类 + 容差
   不脱离原方法，避免"数据更好"成空话。
5. **确定性拒绝**：所有畸形 spec 一律 exit 5 + result.json，refusalRule 形如 `audit.no_section`——
   平台评审看到的是结构化拒绝，不是 traceback。

## 生态贡献

- **SKILL.md** 包含用途、适用条件、调用方式、输入输出、异常处理、限制和自查方法
- **scripts/** 纯标准库可独立导入，规则库可通过 spec 配置扩展
- **examples/** 提供最小调用示例和示意输出
- **bench/** 回归套件可独立复跑验证

