---
name: result-interpretation
description: >
  实验结果解释与异常分析：把一批实验读数解释成可检查的结论。先按数据字典清洗
  （缺失不补零、单位换算留痕、重复记录与重复实验分开），再用两道检测器判定异常值——
  物理上下限（声明合理范围）与分布诊断（IQR 远离围栏），异常点必须给出保留/剔除/
  盖帽的理由；然后审计解读条目（spec.observations）：(a) 引用的数值与基线必须真实
  存在于数据表中，引用表中不存在的数字是 high finding；(b) 被规则标记的异常点必须
  带解释；(c) 解释里断言了原因就必须记录原因候选与支持证据——没有记录的机理猜测
  会被点名，相关不能冒充因果。五段结论各有机械规则：趋势方向必须与数据首末走向
  一致（矛盾是 high finding；无排序列或不足两个可解析点则明确报不可验证）；
  复核步骤必须可执行（动作动词 + 具体对象——文件/字段/批次/设备日志；"检查数据
  质量"这类句子会被点名）；每条后续实验建议必须绑定已记录的原因候选并注明风险
  与前提，未绑定或未标风险的建议不通过。解释按五段组织：结果趋势、异常点、可能
  原因、复核步骤、后续实验建议，每段都要能回指到具体数据行、判定阈值和记录在案
  的原因。Use when a task supplies experimental readings and asks for result
  interpretation, trend judgment, anomaly localization, cause analysis, review
  steps, or follow-up experiment suggestions whose conclusions must be traceable
  to specific data rows and thresholds.
---

# result-interpretation（实验结果解释与异常分析）

最容易漏掉的缺陷不是崩溃，而是一段通顺的解释：趋势是读数复述，正常波动被当成异常，
异常点归错样本，原因只是没有被排除过程的机理猜测，复核步骤写成"检查数据质量"这类
无法执行的话。本 Skill 让每条解释都能回指到具体数据行、判定阈值和记录在案的原因，
并让五段结论中的三个软段（趋势、复核、建议）各有机械判定规则。

七项机械保证：

1. **引用必须落地。** 解读条目里的数值（value）和基线（baseline）必须存在于表中
   （按列解析，容许带单位）；引用表中不存在的数字是 high finding——这个数字没有
   可追溯的来源。
2. **异常判定用两道检测器。** 物理上下限来自每列声明的合理范围（清洗通道 R05），
   分布诊断来自列自身的 IQR 远离围栏（3×IQR，至少 6 个解析值才启用——样本太少时
   分位数是噪声）。异常点必须有解释：保留、剔除还是盖帽，理由写在记录上。
3. **因果要留痕。** 解释文本里出现因果措辞（由于/导致/归因于/due to...）而观测条目
   没有记录 cause 字段，即报 `anomaly.cause_asserted`。引擎不判断原因**对不对**，
   只判断原因**有没有被记录**——候选原因与支持证据要写在观测条目上。
4. **趋势方向必须与数据一致。** 观测条目可用 trend_claim 声明方向（up/down/flat，
   或直接在解读文字里出现方向词）；引擎按 trend.order_column 排序、取指标列首末值
   相对变化（默认 2% 死区）机械重算方向，声称与重算矛盾即 high finding
   （`trend.direction_mismatch`）；无排序列、指标列不存在或不足两个可解析点时明确
   报 `trend.unverifiable`（medium）——不可验证的趋势句要补声明或降级为读数复述，
   不许蒙混过关。一句话混用相反方向词（"先升后降"）不算矛盾：引擎记录 limit 并
   拒绝裁决，要求拆分或改用 trend_claim 字段。
5. **复核步骤必须可执行。** 每条复核步骤要配对「动作动词 + 具体对象」：动词来自
   固定词表（回查/核对/复算/重跑/重测/复测/加做/补做/比对/调取/抽查/追溯/
   重复测量，或 verify/recompute/rerun/compare/repeat/cross-check/trace...），
   对象是具体文件名、字段、批次、设备日志、样本或可比计算量（均值/斜率/拟合...）。
   "检查数据质量"这类句子（"检查"不在动词表、无具体对象）会被
   `review.not_executable` 点名。记录了原因候选却没有配复核步骤 →
   `review.missing_for_cause`：排除过程无法由第二个人执行。
6. **建议必须绑定原因并注明风险。** 每条后续实验建议（next_experiments）必须有
   change（做什么）、addresses（针对哪个原因候选——必须已记录在同一观测的 cause
   或 spec 级 cause_candidates，否则 `next.dangling`）、risk（风险/前提——设备
   占用、安全边界、经费或"未经专家确认"）；缺 addresses 报 `next.unbound`，缺
   risk 报 `next.risk_missing`——不把未经确认的建议写成可执行事实。
7. **清洗不悄悄改值。** 每处修改带 rule id、行、列、原值、新值、理由；原始表原样
   存档并记录 sha256；缺失按"未报告"处理而不是补零。

## 路由决策表

| 任务信号 | 动作 |
|-|-|
| 实验读数 + 结果解释/异常分析/原因分析/复核建议 | 写 spec（rows/columns/observations）→ 跑 `scripts/cleandata.py` → 按 findings 补解释、修引用或降级措辞 |
| 只要清洗不要解读 | observations 留空，引擎只跑清洗与异常普查 |
| 异常判定阈值不明 | 不猜：把 plausible 范围与分布围栏都写进报告的"判定阈值"一节，标明来源；没有阈值就报 limits |
| 数据是曲线/图谱读数 | 先把读数落成表格（含批次/通道/时间维度），再走本流程；直接解释曲线不在范围内 |
| 趋势判读 | 观测条目带 metric 与 trend_claim（或文字方向词），spec 声明 trend.order_column；方向矛盾按 high finding 处理 |
| 要生成复核清单 | 观测条目带 review_steps（每条一个可执行动作）；有 cause 的观测必须至少一条 |
| 要给下一轮实验建议 | 观测条目带 next_experiments（change + addresses + risk）；addresses 必须指向已记录的原因候选 |
| 只要统计建模/假设检验/可视化 | 不在本包：用 p47 统计解读或绘图类技能；本包只做可回指的解释与异常审计 |

## 环境要求

Python 3.9+，仅标准库（无第三方依赖）。

## Workflow

### 1. 声明数据、上下限与解读条目

```json
{
  "rows": [
    {"sample": "S1", "batch": "B1", "hardness": "42.5", "cure_hours": "24"},
    {"sample": "S8", "batch": "B3", "hardness": "47.9", "cure_hours": "24"}
  ],
  "columns": [
    {"name": "sample", "semantic": "id"},
    {"name": "batch", "semantic": "categorical"},
    {"name": "hardness", "semantic": "numeric", "plausible": [0, 46]},
    {"name": "cure_hours", "semantic": "numeric"}
  ],
  "key_columns": ["sample"],
  "trend": {"order_column": "cure_hours", "deadband": 0.02},
  "observations": [
    {"observation": "S8 硬度 47.9，超出批内分布",
     "value": 47.9,
     "explanation": "超出该列物理合理上限与批内分布，建议剔除后复核 B3 批次记录",
     "cause": {"factor": "固化时间不足", "evidence": "B3 批固化日志缺 12 分钟记录"},
     "review_steps": ["回查 B3 批固化日志的固化时长字段", "复算剔除 S8 后的批内均值"],
     "next_experiments": [{"change": "补做 24h/36h 固化对照", "addresses": "固化时间不足",
                           "risk": "烘箱占用 12 小时，需排队"}],
     "trend_claim": {"metric": "hardness", "direction": "flat"}}
  ]
}
```

- rows 内联，或 `"table_path": "data.csv"`。带单位的单元格（`42.5 MPa`）按列解析；
  `plausible` 是**物理/工艺上下限**，来源要写进报告——抄别处的范围是异常制造机。
- `trend` 可选：order_column 是趋势的排序列（时间/剂量/循环），deadband 是"持平"
  判定的相对变化死区（默认 0.02）。
- observations 每条：observation（解读文字）、value（引用数值）、baseline（可选，
  引用的对照基线）、explanation（为什么——异常点在这里写保留/剔除/盖帽）、
  cause（可选，记录原因候选与证据；解释里有因果措辞而这里为空即 finding）、
  review_steps（可选，复核动作清单，每条一个可执行句）、next_experiments（可选，
  每条 {change, addresses, risk}）、trend_claim（可选，{metric, direction} 显式
  声明方向）、metric（可选，把引用检查限定到一列）。

### 2. 运行

```bash
python scripts/cleandata.py --spec spec.json --out /app/output
```

退出码表（含 undetermined → 5）：

| exit | status | 含义 |
|-|-|-|
| 0 | clean | 零 finding，可直接交付 |
| 3 | review | 有 medium/low finding——结论可用，但点名项必须先修或写进 limits |
| 4 | blocked | 有 high finding（引用不落地、趋势矛盾、重复运行等）——不得带病交付 |
| 5 | undetermined | 拒绝：spec 不可读或无行可分析——仍写出 result.json，不崩溃 |

写出 `result.json`、`cleaned.csv`、`original.json`。同一输入重复跑进同一输出目录
会被拒（exit 4，refusal 写 result-refused.json，原 result.json 保留作首跑证据）。

### 3. 判定点

- interpretation_audit 的 flagged 数组 — 两道检测器共同标记的异常（column、row、
  value、来源 plausible_range 或 iqr、围栏）。报告里的每个异常点都应该能在这里
  找到同源记录。
- interpretation_audit 的计数 — n_trend_claims（已检查的方向声明数）、
  n_review_steps / n_review_executable（复核步骤与其中可执行数）、
  n_next_experiments（建议数）——五段结论的机械覆盖一目了然。
- `changes[]` — 清洗台账：R05 的每条记录就是一次超范围判定，含值与范围。
- `findings` — 引用落地、异常解释覆盖、因果留痕、趋势方向、复核可执行、建议绑定
  的判定，加清洗层结论。

## 输出契约

`result.json`：`status`、`findings[]`、`severity_counts`、`rows`、`changes_by_rule`、
`changes[]`、`duplicates`、`anomalies`（每列缺失/未解析/被拒计数）、
`interpretation_audit`（异常普查、解释覆盖、趋势/复核/建议计数、limits）、
`quality_report`、`cleaned_table`、`idempotent`、`original_sha256`、`row_source`。

若 `/input/case.json` 声明了 `output_contract`，它点名的每个键都要出现——可推导则填，
不可推导则 `null` 加 `limits` 条目。

## 最小调用示例

输入：`examples/example-spec.json`（8 行三批次读数 + 1 条解读，解读带可执行复核
步骤）。

调用：

```bash
python scripts/cleandata.py --spec examples/example-spec.json --out out_example
```

输出（示意，节略——真实运行还会写出 cleaned.csv 与 original.json）：

```json
{
  "status": "clean",
  "findings": [],
  "idempotent": true,
  "interpretation_audit": {
    "n_observations": 1,
    "n_flagged_anomalies": 0,
    "n_explained_anomalies": 0,
    "n_trend_claims": 0,
    "n_review_steps": 1,
    "n_review_executable": 1,
    "n_next_experiments": 0,
    "flagged": [],
    "limits": []
  },
  "quality_report": {"rows": 8, "cells": 32, "missing_cells": 0}
}
```

（示意输出——说明接口与结果形状，不是正式案例结果。）

## 规则库与审计规则

清洗规则（R01–R08，同 p47 数据质量通道：空白修剪、未报告记号按缺失、测量解析、
单位换算留痕、合理范围标记 R05、实体键规范化、重复记录/重复实验分报、日期规范化）。
R05 的产出直接喂给异常判定：每条 R05 记录是一个超物理上下限的异常点。

审计 finding（引擎产出、按严重度）：

| rule | severity | 证明什么 |
|-|-|-|
| `observation.value_not_in_data` | high | 解读引用的数值或基线在表中不存在——结论没有可追溯来源 |
| `trend.direction_mismatch` | high | 声称的趋势方向与数据首末走向矛盾——数字不支持的结论不得交付 |
| `clean.not_idempotent` | high | 二遍清洗仍改值——规则优先级互相矛盾 |
| `clean.already_cleaned` | high | 同一输入已在此输出目录运行过——exit 4 拒绝二次叠加 |
| `clean.spec_unreadable` | high | spec 不可读或无行可分析——exit 5 拒绝，不崩溃 |
| `observation.malformed` | medium | 解读条目不是对象、或 observations 不是列表——跳过并点名，不静默 |
| `anomaly.unexplained` | medium | 被物理上下限或分布诊断标记的异常点没有解释（保留/剔除/盖帽的理由缺失） |
| `anomaly.cause_asserted` | medium | 解释断言了原因但没有记录 cause 字段——机理猜测缺少排除过程 |
| `trend.unverifiable` | medium | 方向词/方向声明无法从数据机械验证（无排序列、指标列不存在、可解析点不足、方向词非标准同义词）——补声明或降级措辞 |
| `review.not_executable` | medium | 复核步骤缺动作动词或缺具体对象——"检查数据质量"类句子无法由第二个人执行 |
| `review.missing_for_cause` | medium | 记录了原因候选但没有配任何复核步骤——排除过程缺失 |
| `review.step_malformed` | medium | 复核步骤既不是字符串也不是带 action 的对象——点名重写 |
| `next.malformed` | medium | 建议不是对象、或缺 change——重写为 {change, addresses, risk} |
| `next.unbound` | medium | 建议没有写明针对哪个原因候选 |
| `next.dangling` | medium | 建议指向的原因候选没有记录在案（同观测 cause 或 spec 级 cause_candidates 都没有） |
| `next.risk_missing` | medium | 建议没有注明风险/前提——未经确认的建议不得写成可执行事实 |
| `clean.missing_values` | medium | 有未报告值——按缺失处理，绝不补零 |
| `clean.unparsed_values` | medium | 无法解析的单元格保留为命名缺口 |
| `clean.duplicate_experiments` | medium | 同实体不同值——是两次测量，不得静默合并 |
| `clean.report_inconsistent` | medium | 手工报告与表计算的报告不一致——修报告，不改表 |
| `clean.duplicate_records` | low | 完全相同的行——复核后可删 |

方向词表（机械匹配规则：CJK 子串匹配，拉丁词按词边界；≥6 字母词干容许屈折变化）：
上升类 = 上升/增加/增大/提高/升高/增强/攀升/走强/增多、increas/rise/risen/rising/
elevat/grew/growth；下降类 = 下降/减少/降低/减小/减弱/回落/走低/缩减、decreas/
decline/drop/reduc/fell/fall/weaken；持平类 = 持平/保持稳定/保持不变/基本不变/
无明显变化/平台期/趋平、plateau/stable/unchanged/constant。同义词由
DIRECTION_SYNONYMS 归一。机械判定 = 按排序列排序后取首末值相对变化
（last−first）/max|value|，|相对变化| ≤ deadband（默认 2%）判持平，否则按符号。

复核动词表：回查/核对/复算/重跑/重测/复测/加做/补做/比对/调取/抽查/追溯/
重复测量/重新测量，或 verify/recompute/rerun/recheck/compare/repeat/cross-check/
re-measure/trace/inspect（"检查/确认/注意"**故意不在表内**）。具体对象词表：
文件名（含扩展名）、字段/列名/列号/行号、批次/日志/设备/样本/通道/孔位、对照/
平行/原始数据/原始表/工作簿/记录表/设备台账，可比计算量（均值/标准差/斜率/
拟合/残差/峰值/中位数/不确定度/检出限/回收率等），或拉丁对应词。

## Limits

- **不做因果推断。** 引擎不判断原因是否正确、不排序原因候选——它只强制：断言因果
  的解释必须记录原因候选与证据；建议必须绑定已记录的候选。排序与验证是下一步实验
  的事。
- **趋势是首末走向，不是拟合。** 机械判定用排序后首末值与死区，不做曲线拟合、不找
  拐点——拐点与平台期的叙事判读写在报告里，但方向结论必须先通过首末一致性。
- **分布诊断是辅助判定。** 3×IQR 远离围栏只抓显著偏离，1.5×IQR 的轻度离群围栏
  故意不用——正常波动被当成异常是本课题点名的失败模式。n 小于 6 时诊断跳过。
- **阈值来自声明。** plausible 范围来自数据字典或物理上下限；没有声明时只有分布
  诊断一道防线，报告应把这一点写进"判定阈值"一节。
- **异常覆盖按数值匹配。** 解释条目通过引用同一数值来"覆盖"异常点；引用别的列的
  数值不能覆盖（按 metric 或全表搜索定位）。
- **复核步骤是形态检查不是事实检查。** 引擎验证动词与对象在场（可执行形态），不
  验证步骤做了之后真能排除该原因——那是执行者的职责。
- **不补插。** 缺失是命名缺口；用均值填充 invent 数据。

## Failure handling

| 症状 | 处置 |
|-|-|
| `observation.value_not_in_data` | 把引用换成表中真实值（看 finding 的 cited 与搜索范围），或补数据并说明 |
| `trend.direction_mismatch` | 改判读方向与数据一致；若判读确实为噪声/两段式，拆成 trend_claim 分段声明或降级为读数复述 |
| `trend.unverifiable` | 声明 trend.order_column 与 metric（数据不足则补数据）；不打算补就删掉趋势措辞 |
| `review.not_executable` | 重写成「动词 + 对象」：回查哪个文件哪个字段、复算哪个量 |
| `review.missing_for_cause` | 给该观测补至少一条可执行复核步骤；不要让原因候选裸奔 |
| `next.unbound` | 补 addresses：写明该建议针对哪个已记录的原因候选 |
| `next.dangling` | 在 cause（或 spec 级 cause_candidates）记录该候选，或把 addresses 改成已记录的候选 |
| `next.risk_missing` | 注明该建议的风险/前提（设备、安全、经费、需专家确认） |
| `anomaly.unexplained` | 在对应观测条目写清保留/剔除/盖帽及理由；不要删数据不写记录 |
| `anomaly.cause_asserted` | 补 cause 字段（候选原因 + 支持证据），或把措辞降级为相关性描述 |
| `clean.spec_unreadable`（exit 5） | 读 findings；spec 不可读或没有行——修输入后重跑 |
| `clean.already_cleaned`（exit 4） | 换输出目录，或确认这是要拒绝的重复运行 |
| `clean.duplicate_experiments` | 同实体不同值是两次测量——分开保留，不要平均 |
| R04 拒绝（new 为 null） | 单位无法换算——命名单位，不静默丢行 |
| 分布诊断与物理范围不一致 | 以物理上下限优先；把两者围栏都写进报告，注明样本量限制 |

判读方法细节见 `references/judgement-notes.md`。

## 运行时入口与输出契约（Harbor，六步）

1. **读输入**：运行时原始输入固定为 `/input/case.json` 与 `task.md`。先读
   case.json 取 `case_id`、任务说明与 `output_contract`；材料是**实际数据文件**
   （CSV、工作簿、曲线/图谱读数表）——按 task.md 指向的路径读实际文件，不按
   文件名或领域标签猜内容。多 sheet 工作簿（如 12 sheet 主表）先选目标 sheet，
   把行列落成 `rows`；来源 sheet 名、字段名与单位歧义写进日志。
2. **建工作区**：中间产物写 `/app/work`（原始表快照、清洗台账、逐节 findings、
   日志）；尽早写出诚实的部分结果，再增量改进。
3. **跑引擎**：`cleandata.py --spec ... --out ...`；spec 顶层放 rows/columns/
   key_columns/trend/observations（observations 的每条解读带上 value/baseline/
   explanation/cause/review_steps/next_experiments）。exit 5 先修输入再重跑。
4. **回填契约**：最终结果写 `/app/output/result.json`——case_id 原样回填；
   output_contract 的每个原始字段逐字段拷贝（不改名不遗漏；不可推导的置 null
   并在 limits 写明）。CLI 已实现该回填；拒绝路径不回填契约，只写最小
   result.json。
5. **诚实状态**：status 映射——引擎 clean → done；review → partial（在
   status_reason 写明待补什么）；blocked / undetermined → failed（写明失败环节）。
   interpretation 五段（trend/anomaly_points/cause_candidates/review_steps/
   next_experiments）逐段给出，缺段在 status_reason 说明原因（如"数据只覆盖
   单指标，无趋势可言"）；sources 记录每条结论回指的数据文件/字段/行/阈值；
   uncertainty 记录待复核项；limits 记录边界。可渲染交付物（cleaned.csv、
   台账）随结果一并写出供查验。
6. **自查退出**：改任何脚本后重跑 `scripts/bench_interp.py`（27 场景必须全过）；
   按第 2 步的退出码表检查本次运行（含 undetermined → 5）。

result.json 的落地映射（三段输出结构对齐 rubric 原词）：

| rubric 输出段 | result.json 键 | 完成标准 |
|-|-|-|
| 实验方案（本课题 = 五段解释） | `interpretation`（trend / anomaly_points / cause_candidates / review_steps / next_experiments） | 实验人员可据此执行，或明确知道缺什么 |
| 依据与风险 | `evidence_and_risks`（data_refs 数据行引用、thresholds 判定阈值及来源、risks 风险与异常处置） | 假设和边界可复核 |
| 确认项 | `confirmation_items`（pending_review 待复核、expert_confirm 需专家确认、not_checked 未检查项） | 不把未经确认的建议写成可执行事实 |

- 五段与机械规则的对应：trend 段每条方向声明要过 trend.direction_mismatch /
  trend.unverifiable；anomaly_points 段每条要能在 interpretation_audit 的 flagged
  里找到同源记录并带保留/剔除/盖帽；cause_candidates 段每条要带 factor + 支持证据
  （cause_asserted 强制）；review_steps 段每条要过 review.not_executable；
  next_experiments 段每条要过 next.unbound / next.dangling / next.risk_missing。
- 六要素回指：每条结论注明它依据的假设与变量、对照设置、设备与材料批次、时间与
  成本约束、参数范围、风险判断——写不出的要素标「未报告」，不编造。
- 引擎产物（`changes`、`duplicates`、`anomalies`、`interpretation_audit`、
  `quality_report`、`cleaned_table`）整体保留在 result.json 中，作为操作证据。
- 引擎已实现该契约：spec 顶层提供的 output_contract 同名字段值会被 CLI 原样拷入
  result.json（大体积输入字段除外）；推导不出的字段填 null 并在 limits 里说明。
  把 interpretation / evidence_and_risks / confirmation_items 的字段值放进 spec
  顶层，即直通最终 result.json。

## 五段可检查结论模板

实际效果项要求把一份数据解释成五段可检查结论。缺一段就在 `status_reason` 里说明
为什么缺（如"数据只覆盖单指标，无趋势可言"），不许用读数复述凑数。**全部指标、
对照、重复与边界情况都要覆盖**——未解释的指标或异常写进
confirmation_items 的 not_checked 并在 `limits` 交代，不沉默。

1. **结果趋势** — 走势、拐点、平台期与偏离幅度；每条方向声明通过机械一致性检查
   （trend.direction_mismatch / trend.unverifiable），并写明所依据的区间、对照和
   拟合方式，回指具体数据行（文件 + 字段 + 行号）。"S8 是 47.9"是读数复述，不是
   趋势。
2. **异常点** — 绑定到样本/批次/通道/孔位/时间点维度；异常程度、判定阈值（物理
   上下限 R05 或 3×IQR 分布围栏，写明来源）、与对照或重复的偏离关系。引擎普查见
   interpretation_audit 的 flagged 数组——报告里的每个异常点都要能在那里找到同源
   记录；反之，普查标出的异常点不得沉默。正常波动不得判为异常。
3. **可能原因** — 按证据强度排序的候选清单：`factor` + 支持证据 + 排除证据 +
   「相关被误当因果」的风险标注。引擎强制 cause 留痕（`anomaly.cause_asserted`）
   且建议必须绑定已记录候选（next.dangling），排序与排除过程写在解释与复核步骤里。
4. **复核步骤** — 拆成第二个人可以执行的核查动作（review.not_executable 机械把关）：
   回查哪个文件哪个字段、核对哪条批次/设备日志、复算哪个量、加做哪个对照或几次
   平行重复。"检查数据质量"这类不可执行句不算复核步骤；记录了原因却不给步骤会被
   `review.missing_for_cause` 点名。
5. **后续实验建议** — 依据原因候选与证据缺口给出下一轮改动（补对照、加密采样点、
   调整参数范围、扩大重复数），每条注明它针对哪个原因候选（next.unbound /
   next.dangling 把关）并注明风险与前提（next.risk_missing 把关）。

## 数据形态与异常处置

| 形态 / 故障 | 处置 |
|-|-|
| 表格读数（CSV / 工作簿） | 直接进 rows；多 sheet 先选目标 sheet，行列写进日志 |
| 曲线 / 图谱读数 | 先把读数落成表格（含批次/通道/时间维度），再走本流程 |
| 多批次 | batch 声明为 categorical；异常按批次内分布判，不跨批混算 |
| 数据缺失 | `clean.missing_values`：按「未报告」处理不补零；解释不得引用缺失值 |
| 单位不一致 | R04 换算留痕；拒绝换算（new 为 null）时命名单位，不静默丢行 |
| 重复数不足 | 分布诊断 n<6 自动跳过；报告把「判定阈值仅物理上下限」写进判定阈值一节 |
| 对照缺失 | 报告明确「无对照」；偏离幅度只对绝对阈值判，不判相对效应 |
| 读数超量程或饱和 | R05 物理上下限标记；解释必须写保留/剔除/盖帽（`anomaly.unexplained`） |
| 趋势方向与数据相反 | `trend.direction_mismatch`（high，exit 4）：改方向或降级为读数复述，矛盾结论不得交付 |
| 无排序列却写趋势 | `trend.unverifiable`：声明 trend.order_column，或删掉趋势措辞 |
| 一句话混用相反方向词 | 不裁决：记录 limit，要求拆分声明或改用 trend_claim 字段 |
| 复核步骤不可执行 | `review.not_executable`：按「动词 + 对象」重写 |
| 建议未绑定原因 | `next.unbound`：补 addresses；`next.dangling`：先在 cause 记录该候选 |
| 建议未标风险 | `next.risk_missing`：注明设备/安全/经费等前提或"需专家确认" |
| 结论互相冲突 | 两条解读引用同一数值但结论相反 → 并列保留并标待复核，不自行仲裁 |
| spec 不可读 / 无行可分析 | exit 5 拒绝，仍写 result.json（`status: failed` + 原因），不崩溃 |
| 重复运行同一输入 | `clean.already_cleaned`（exit 4）：换输出目录或确认拒绝——防二遍叠加 |

## 使用增益与对照方法

- **公平对照**：同一份数据、相同权限下，不加载本 Skill 的基础 Agent 输出与加载后
  的五段结论对比，按「引用落地、趋势方向一致、异常定位、因果留痕、复核可执行、
  建议绑定原因并注明风险」六项逐条计数；平台白板是对照基准，不是参赛者答案。
- **增益证据形式**：`scripts/bench_interp.py` 27 场景（每场景植入一个缺陷或钉住一个
  FP guard），clean 基线零 high/medium finding；同输入重跑结果一致（确定性引擎）；
  方向声明可由任何持表人按排序列与死区独立重算。

## 验证

```bash
python scripts/bench_interp.py   # 27 scenarios：每个植入一个缺陷或证明一个 FP guard
```

本机 27/27 pass。clean 基线零 high/medium finding，异常普查计数与植入数据断言一致；
FP guard 钉住关键行为：异常点带着保留/剔除/盖帽理由后保持安静、记录了 cause 且配了
复核步骤的因果解释保持安静、方向声明与数据一致（显式 trend_claim 与文字方向词两条
路径）保持安静、混用相反方向词不被误判、可执行复核步骤（回查文件字段/复算均值）
通过形态检查、绑定已记录候选且注明风险的建议保持安静、带单位单元格与 metric 限定
的引用正常落地、真 0 不按缺失处理。

## Requirements

Python 3.9+（3.14 实测）。纯标准库实现，无第三方依赖。

## 创新增益

本 Skill 相比通用 Agent 的新增能力（每条附能力边界与增益证据形式）：

1. **两道检测器异常判定**：物理上下限（声明合理范围）+ 分布诊断（3×IQR 远离围栏，
   n≥6 才启用）双通道；异常点绑定列/行/批次维度，并强制写保留/剔除/盖帽的理由。
   *边界*：阈值来自声明，引擎不发明阈值；n<6 只有物理上下限一道防线。
   *证据形式*：bench_interp 异常普查计数与植入数据断言一致。
2. **趋势方向一致性判定**：方向声明（显式 trend_claim 或文字方向词）与按排序列
   重算的首末走向机械比对——矛盾是 high finding，不可验证明确点名（无排序列/
   可解析点不足），混用相反方向词不裁决。通用 Agent 的趋势句是读数复述或凭语感，
   无法防"数字说持平、结论写上升"这类错误。
   *边界*：首末走向不是曲线拟合，拐点与平台期的叙事判读仍在报告层。
   *证据形式*：bench trend_mismatch_high / trend_match_fp / trend_word_no_order /
   trend_mixed_words_fp。
3. **可执行复核清单强制**：复核步骤过「动作动词 + 具体对象」形态检查（"检查数据
   质量"被点名），记录原因必须配复核步骤——把"排除过程"从美德变成机械门槛，生成
   的清单第二个人可以直接照做。
   *边界*：形态检查不验证步骤做完真能排除原因。
   *证据形式*：bench review_not_executable / review_executable_fp /
   review_missing_for_cause / review_step_malformed。
4. **建议-原因-风险三重绑定**：每条后续实验建议必须写 change、绑定已记录的原因
   候选（否则 dangling）、注明风险与前提（否则 risk_missing）——直接产出 rubric
   的"确认项"段：未经确认的建议不会伪装成可执行事实。
   *边界*：引擎不判断建议本身是否值得做。
   *证据形式*：bench next_unbound_and_risk / next_dangling / next_bound_fp。
5. **引用落地检查**：解读引用的数值与基线必须在表中真实存在——结论回指数据行，
   引用不存在的数字是 high finding。
   *边界*：按列解析容许带单位；跨表搜索定位，找不到即报。
   *证据形式*：bench_interp 引用场景（带单位单元格与 metric 限定正常落地）。
6. **因果留痕**：因果措辞强制记录原因候选与支持证据；相关不能冒充因果。
   *边界*：引擎不判原因对错、不排序候选——排序与排除是判读层与下一轮实验的事。
   *证据形式*：bench_interp 记录了 cause 的因果解释保持安静（FP guard）。
7. **清洗台账与幂等**：每处修改带 rule/行/列/原值/新值/理由，原始表 sha256 存档，
   二遍清洗零改动自检——审计者可逐条复核或撤销任何单条修改。
   *证据形式*：bench_interp clean 基线零 high/medium finding。

## 生态贡献

- **使用说明**：本文件含完整调用步骤（Workflow）、输入输出解释（输出契约）、关键
  方法（两道检测器、趋势一致性、复核形态检查、建议绑定与 R01–R08 清洗通道）、
  适用场景与限制（Limits）、失败处理（Failure handling）和自查方法（bench）。
- **依赖与配置**：Python 3.9+（3.14 实测）纯标准库，无第三方依赖、无安装步骤；
  合理范围经 spec 的 `plausible` 配置、缺失记号经 `missing_tokens`、趋势死区经
  `趋势死区（trend 死区参数，默认 2%）` 配置——阈值是数据不是代码。
- **示例（标注为示例）**：`examples/example-spec.json` 是最小输入，本文「最小调用
  示例」的输出是示意输出——均为示例，不冒充正式案例结果。
- **判读词表可复用**：方向词表（上升/下降/持平三类同义词）、复核动词表与具体对象
  词表、因果措辞表（CAUSE_WORDS）都在引擎源码中成清单列出，他人可直接复用或扩展
  到自己的判读场景。
- **题集与金标准**：bench_interp 的 27 个场景即回归题集（每场景一条缺陷或一个 FP
  guard），report_interp.json 是可对比的运行记录。
- **判读经验沉淀**：`references/judgement-notes.md` 沉淀两道检测器的证据类型差异、
  "explained"的三种口径（保留/剔除/盖帽）、因果留痕的降级路径与引用容差依据。
- **限制**：见 Limits 一节（不做因果推断、趋势是首末走向、复核是形态检查、阈值来
  自声明、不补插）。
- **维护**：`scripts/bench_interp.py` 为回归门，改动后必须 27/27 全过；判读方法
  细节沉淀在 `references/judgement-notes.md`；规则 id 变更须同步本文档规则表。
