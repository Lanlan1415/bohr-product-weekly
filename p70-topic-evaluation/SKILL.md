---
name: topic-evaluation
description: >
  科研选题与创新性评估: audit a topic evaluation so a decision-maker can act on it. The
  research question must be broken into a testable statement with a boundary — broad
  qualifiers fire in English and in pure Chinese alike (全面/所有/一切/系统研究). Prior work
  must be compared in a matrix along task/method/data/metric/conclusion with evidence
  pointers, and every row that cannot be compared directly must state why. Every innovation
  claim must draw its boundary against the closest existing work, feasibility must be a
  costed route with risks and fallbacks rather than the words "technically feasible", and
  preliminary work must say whether it is done or planned. Use when a task asks to
  evaluate a research topic, judge novelty against existing work, define a research
  question, or assess whether a proposed study is feasible with the stated resources.
---

# topic-evaluation

选题评估被拒不是因为想法差，而是因为五件事含糊其一：问题不可检验、比较对象选错、不可直接
比较的原因不写、创新点与已有工作划不清边界、可行性只有一句"技术路线可行"。本 Skill 把选题
评估路由到 `proposal` 节审计器，七要素恰好对应评估报告的四个侧面：

| 评分点 | 规则（一行一 id） |
|-|-|
| 问题拆成可检验表述 | `prop.question_too_broad` |
| 要素内容齐备 | `prop.element_missing` |
| 要素没有空转 | `prop.element_no_text` |
| 论断型要素带证据指针 | `prop.element_no_evidence` |
| 段落归入要素 | `prop.paragraph_no_element` |
| 段落要素名合法 | `prop.paragraph_element_unknown` |
| 三级映射不断链 | `prop.paragraph_no_evidence` |
| 创新要素篇幅可支撑论证 | `prop.field_too_thin` |
| 可行性是可执行路线 | 见"问题、目标与路线"表 |

## 六类被拦截的失败

**问题没有边界。** "对 X 做全面评估"无法被一项工作回答；宽泛限定词在英文与纯中文里都会报出
（comprehensive/every 按词边界；全面/所有/一切/全部/系统研究/穷尽/全方位 按字面匹配）。

**比较矩阵不标不可比原因。** 已有工作按 task/method/data/metric/conclusion 逐面比较，
每行声明 comparable 与否；标记不可直接比较却不写原因，正好藏住了比较要暴露的鸿沟。

**目标没有度量。** "覆盖率更高"无法判断完成与否。`measure` 是观察什么，`outcome` 是
成功时什么不同；目标还要挂到研究内容（content_ref）和技术路线步骤上，一一对应。

**路线是方法清单。** 每一步必须声明 `input`、`output`、`risk`、`fallback`——少一步，
可行性就是断言而不是分析。

**前置工作说不清做没做。** 已完成（done）与拟开展（planned）混写，评估就比实际更成熟。
每条 foundation 链必须是 capability → evidence → relation 三环。

**"检索不到"当"尚无人研究"。** 创新要素只有一句"Novel."——论证性要素有最短篇幅门槛，
且必须带证据指针指向最近的已有工作。

## Workflow

### 1. 按七要素写出评估，做三级映射，再建比较矩阵

```json
{
  "section": "proposal",
  "elements": {
    "rationale": {"text": "现有对比止步于 2022 年……", "evidence": "M1 语料覆盖记录"},
    "question": {"text": "扩散式采样器在同一基准上是否比最强经典基线的覆盖率高至少 5 个百分点",
                 "evidence": "M1"},
    "objectives": {"text": "三项可检验目标：覆盖率、复现误差、语料覆盖", "evidence": "Sec 2"},
    "content": {"text": "冻结语料并复现三个已有基线，再对照评测", "evidence": "M2"},
    "innovation": {"text": "与已有工作只报告端到端精度不同，本评估在同一语料、同一预算下公布"
                          "每个基线的复现误差……", "evidence": "[doe2020]"},
    "technical_route": {"text": "三步：语料冻结、基线复现、对照评测", "evidence": "Sec 4"},
    "foundation": {"text": "实验室语料库与已有算力平台", "evidence": "M0"}
  },
  "paragraphs": [{"text": "为什么现在评估这个选题", "element": "rationale", "evidence": "M1"}],
  "objectives": [{"id": "O1", "measure": "同一基准上的覆盖率对比",
                  "outcome": "至少高出 5 个百分点", "content_ref": "C1"}],
  "content": [{"id": "C1", "text": "冻结语料并复现基线"}],
  "route": [{"id": "R1", "objective": "O1", "input": "2018-2024 标注语料",
             "output": "基线复现报告", "risk": "基线复现偏差",
             "fallback": "改用原作者公开检查点"}],
  "foundation_items": [{"name": "实验室语料库", "capability": "已收录 3,200 篇标注文献",
                        "evidence": "M0 run 2023-04",
                        "relation": "同一语料库支撑本次评估的检索范围", "status": "done"}],
  "comparison_matrix": [
    {"id": "M1", "work": "doe2020", "aspect": "method", "comparable": true,
     "evidence": "[doe2020] Sec 3, p.4"},
    {"id": "M2", "work": "roe2021", "aspect": "metric", "comparable": false,
     "reason": "评价指标不同（F1 对覆盖率），数值无法对齐",
     "evidence": "[roe2021] Table 1, p.5"}
  ],
  "timeline": [{"period": "Y1", "milestone": "基线复现通过容忍度检查"}],
  "budget": [{"item": "算力", "justification": "600 GPU 小时，按现有平台报价"}],
  "budget_justification": "每项按现有供应商报价与设备清单核算"
}
```

比较矩阵行模板（可复用，见 references/comparison_template.md）：每行一个 `work`（先有工作
标识）、一个 `aspect`（task/method/data/metric/conclusion 五选一）、一个 `comparable`
布尔、一个 `evidence` 指针；`comparable` 为 false 时 `reason` 必填，写明为什么数值或设计
无法直接对齐（指标不同/任务不同/数据集不可得/条件不可复现……）。

### 2. 运行

```bash
python scripts/secrun.py --spec spec.json --section proposal --out /app/output
```

Exit codes: `0` clean, `3` review, `4` blocked, `5` undetermined（spec 不可读/缺 section——
拒绝执行，绝不崩溃）。

## Rules

### 七要素与三级映射

| rule | severity | 判定 |
|-|-|-|
| `prop.element_missing` | high | 缺一个必需要素 |
| `prop.element_no_text` | high | 要素没有内容 |
| `prop.element_no_evidence` | high | 论断型要素没有证据指针 |
| `prop.paragraph_no_element` | medium | 段落未归入要素 |
| `prop.paragraph_element_unknown` | low | 要素名不在七要素之内 |
| `prop.paragraph_no_evidence` | high | 三级映射断链 |
| `prop.field_too_thin` | low | 论证型要素太短撑不起论证 |

### 问题、目标与路线

| rule | severity | 判定 |
|-|-|-|
| `prop.question_too_broad` | high | 问题无边界，不可回答（英文与纯中文宽泛词均触发） |
| `prop.objectives_missing` | high | 无可评估目标 |
| `prop.aim_without_measure` | high | 完成与否无法判断 |
| `prop.aim_without_outcome` | medium | 未说明成功时什么不同 |
| `prop.objective_unmapped` | high | 目标未挂到研究内容 |
| `prop.objective_content_unknown` | medium | 指向的内容项不存在 |
| `prop.objective_no_route` | high | 目标没有对应路线步骤 |
| `prop.route_no_io` | high | 步骤未声明输入与输出 |
| `prop.route_no_risk` | medium | 步骤未声明风险 |
| `prop.route_no_fallback` | medium | 步骤无回退方案 |

### 比较矩阵（已有工作比较）

| rule | severity | 判定 |
|-|-|-|
| `prop.comparison_missing` | high | 案例要求比较而矩阵整体缺席 |
| `prop.comparison_row_no_work` | medium | 比较行没有指明对照的已有工作 |
| `prop.comparison_no_aspect` | medium | 比较行没有声明比较面 |
| `prop.comparison_aspect_unknown` | medium | 比较面在 task/method/data/metric/conclusion 之外 |
| `prop.comparability_unstated` | medium | 比较行没有声明能否直接比较 |
| `prop.incomparable_without_reason` | high | 标记不可直接比较却未写原因 |
| `prop.comparison_no_evidence` | high | 比较行没有证据指针，异同无法回溯到材料 |
| `prop.comparison_row_skipped` | medium | 矩阵条目不是对象被跳过——畸形行点名，不静默缩水 |
| `prop.comparison_row_id_duplicate` | medium | 两行共用一个标识，评审无法指认单行 |

### 前置工作与预算

| rule | severity | 判定 |
|-|-|-|
| `prop.status_unlabelled` | high | 已完成与拟开展不可区分 |
| `prop.foundation_no_capability` | high | 基础链缺能力环 |
| `prop.foundation_no_evidence` | high | 基础链缺证据环 |
| `prop.foundation_no_relation` | high | 与本研究无关 |
| `prop.milestone_missing` | medium | 时间段无里程碑 |
| `prop.budget_unjustified` | medium | 预算无总体依据 |
| `prop.budget_line_unjustified` | medium | 预算行无依据 |

## 运行时入口（每案例）

1. 先读 `/input/case.json` 与 `task.md`，记录 `case_id` 与 case.json 里的
   `output_contract` 字段清单——两者必须原样出现在最终 result.json 顶层。
2. 从案例材料读取研究设想与已有文献（读实际文件，不按标签臆测）；按七要素与三级映射
   构造 spec，顶部带 `case_id`，并把 output_contract 字段名逐个写进 spec 的
   `output_contract` 数组。
3. 为每篇真正相近的已有工作建比较矩阵行：逐面声明 comparable，不可直接比较的行写明
   原因；矩阵证据指针与 objectives、content、route、foundation_items 的指针共用一套定位。
4. 运行审计；修复发现项后重跑，直到 clean 或剩余项全部进入待复核说明。
5. 按题目三段交付（下一节）。

## Output contract

`/app/output/result.json` 必须按此优先级携带：

1. **平台契约字段（原样）**：case.json 的 `output_contract` 全部字段逐字段拷贝（不得
   改名、不得遗漏；推导不出的填 null 并在 limits 里说明），顶层携带 `case_id`。
2. 引擎字段：`status`, `section`, `findings[]`（含 element、objective、step、item、row）、
   `severity_counts`、`checked`、`limits`。CLI 会把 spec 顶层提供的同名值原样拷入
   result.json——所以把 `deliverables`、`evidence_matrix`、`uncertainties`、`gaps`
   放进 spec，它们落进去就是实值而不是 null。
3. 题目三段交付，从引擎产出映射：
   - **研究产物** — 选题评估结论本体：七要素齐备且四项交付（问题定义、已有工作比较、
     创新点识别、可行性判断）相互一致；结论与研究问题和证据范围一致，记
     `deliverables[]`（产物路径）。
   - **证据矩阵** — `evidence_matrix[]`：每条判断一行 `{claim, source, locator,
     include_exclude_reason}`（文献来源、纳排理由、比较字段和定位），关键判断可回到
     材料；与比较矩阵行、objectives、content、route、foundation_items 的 evidence
     指针对应——比较矩阵的不可比原因就是纳排理由的一部分。
   - **不确定性** — `uncertainties[]`：冲突文献（结论相反的登记并说明取舍）、偏倚、
     证据空白、无法确定项各归其位；不越过证据范围扩展结论；材料缺口写 `gaps[]`，
     运行失败与不可判断写入 status/limits，分别说明不混写。

Rubric 对照：四项交付是否齐全一致 → 七要素表与比较矩阵表；创新点是否被已有工作覆盖 →
比较矩阵行 + innovation 要素证据指针；可行性前提是否成立 → route/foundation_items；
检索式与筛选标准可复核 → evidence 指针全表贯通。

拒绝纪律：spec 不可读/缺 section → 写 result.json（`audit.no_section`）退出码 5，
绝不 traceback；可安全跳过的畸形条目按内容缺失如实审计（退出码 3/4）。

## 示意

输入见 `examples/spec.json`。运行后 result.json（示意，节选）：

```json
{"status": "clean", "section": "proposal", "findings": [],
 "severity_counts": {"high": 0, "medium": 0, "low": 0},
 "checked": {"section": "proposal", "items": 1}}
```

（示意输出——说明形态，不是正式案例结果。）

## Limits

- **宽泛限定词分语种匹配。** 英文按词边界（all 不会命中 alloy）；中文按字面（全面/所有/
  一切/全部/系统研究/穷尽/全方位/无一遗漏），因为纯中文问句里词边界永不落在汉字之间。
  有意查全的合法问句应改写为有界陈述（列出基准、条件、样本），否则会被点名。
- **比较矩阵是声明式审计。** 审计器验证每行 five 要素齐备、不可比必带原因、证据指针存在；
  它不判定"这两项工作真的不可比"——那是矩阵作者的论证，位于 reason 字段。
- **篇幅门槛是启发式。** `field_too_thin` 用长度近似"论证密度"，不是语义判断。
- **证据指针只验证存在与指向，不验证内容。** evidence 为 "M1" 时指向调用方提供的材料。
- **`status` 三态是声明。** 审计器区分 done/planned/in_progress，但不核实是否真已完成。
- **不评估想法本身的好坏。** 边界、度量、路线齐备即通过；选题价值是人的判断。

## Failure handling

| 症状 | 处理 |
|-|-|
| `question_too_broad`（中/英） | 拆出对象、变量、基线与可证伪条件，把范围写成有界陈述 |
| `comparison_missing` | 为真正相近的工作逐面建行；确实检索不到就写检索式与时间窗，而不是空矩阵 |
| `incomparable_without_reason` | 写明无法对齐的具体原因（指标/任务/数据/条件） |
| `comparability_unstated` | 每行声明 comparable 真假；拿不准时先 false 并给原因 |
| `aim_without_measure` | 写明观察什么指标、与谁比较 |
| `objective_no_route` | 为该目标补一条带输入输出的路线步骤 |
| `route_no_fallback` | 写明步骤失败时的替代路径 |
| `status_unlabelled` | 每条前置工作标注 done / planned / in_progress |
| `foundation_no_relation` | 写清已有能力与本次评估的关系 |
| `element_no_evidence` | 补证据指针：文献、初步数据或设备清单行 |
| 检索为空 | 记录检索式、数据库与时间窗进 `gaps`；"检索不到"不等于"尚无人研究" |
| 文献过少 | 评估结论限定在已得证据范围内，缺口写入 `uncertainties` |
| `audit.no_section`（exit 5） | 未声明/未知 section，或 spec 不是可读 JSON——拒绝执行，绝不崩溃 |

## Requirements

Python 3.9+，仅标准库（`json`、`re`、`argparse`、`unicodedata`）。无网络、无第三方包。

## Verification

```bash
python scripts/bench_topic.py     # 40 scenarios covering all 33 proposal rules
python scripts/bench_sections.py  # 51 scenarios: cross-section regression plus false-positive guards
```

Both pass in full on this machine. The clean baseline in each must report nothing.

## 创新增益

本包相对通用 Agent 的新增能力，每条附边界与证据形式：

1. **七要素 + 三级映射（新增能力）**：设想被拆成 rationale/question/objectives/content/
   innovation/technical_route/foundation 七要素，objectives→content→route 三级逐条对齐
   （orphan 与悬空引用都报）——通用 Agent 的评估是散文，不可逐项清点。证据形式：
   bench_topic 38 场景逐规则实测；同输入下发现数差可复算。
2. **双语可证伪问题检测（方法改进）**：宽泛问句在英文（词边界）与纯中文（字面匹配）下都
   被点名（`prop.question_too_broad`）。纯中文"全面/所有"命中是本轮修复的关键缺陷——
   旧实现把中文词放进词边界组，汉字之间不存在词边界，五类纯中文宽泛问句 0/5 触发；
   修复后 5/5 触发且有界中文问句不误伤。证据形式：question_too_broad_zh_* 三场景 +
   question_bounded_zh_clean 守卫。
3. **比较矩阵不可比原因强制（新增能力）**：比较行沿 task/method/data/metric/conclusion
   五面声明 comparable；标记不可直接比较而原因缺失是 high 级发现
   （`prop.incomparable_without_reason`）——把"识别真正相近的工作，标出无法直接比较的原因"
   从叙述要求变成逐行可检查的义务。证据形式：comparison_* 七场景（缺行/缺面/缺因/缺指针
   各一）+ comparison_matrix_clean 守卫。
4. **证据指针回链**：每条要素、段落、比较行带 evidence 指针，指向不存在的材料被点名——
   评估不越过证据范围。证据形式：element_no_evidence / comparison_no_evidence 场景。
5. **前提可行性结构化**：foundation_items 带能力/证据/关系/状态四元组，"有条件可行"写成
   可复核的行而不是口号。证据形式：foundation_no_* 三场景。

## 生态贡献

- **使用说明**：SKILL.md 含用途、适用条件、调用方式、输入输出契约、五步运行时入口、
  异常处置表（13 行）与自查方法
- **比较矩阵模板**：references/comparison_template.md 提供行 schema、五面定义与
  不可比原因锚点（指标不同/任务不同/数据不可得/条件不可复现），跨题复用
- **评估口径**：七要素定义、comparable 判定锚点、证据指针写法全部落在 SKILL.md 与模板
- **题集**：bench_topic 38 场景（每规则一场景 + 中英宽泛词 + FP 守卫）+ bench_sections
  51 场景（跨节回归 + FP 守卫），`python scripts/bench_topic.py` 即可独立复跑
- **示例**：examples/ 提供最小调用示例 spec.json（含比较矩阵）与示意输出 bench-report.json，
  标注为示例
- **依赖与配置**：Python 3.9+ 纯标准库，无安装步骤、无网络、无个人文件依赖
- **适用范围与限制**：Limits 一节写明声明式边界、启发式门槛与匹配方式
- **维护信息**：规则库按节分表可扩展；本轮变更（宽泛词双语拆分、比较矩阵 7 规则）写入
  对应小节，报告 schema 带版本号（topic-bench/v1）
