---
name: method-stats-audit
description: >
  研究方法与统计审查：按设计—问题匹配、独立单位/伪重复、随机盲法、样本量/功效、缺失、
  异常值、分布/方差、模型、多重比较、效应量/CI、p值解释、相关/因果、敏感性/稳健性、
  复现十四个检查面形成定位清楚的审查单。数值足够时真实重算 Welch/Student 检验、效应
  量与 CI、Levene/JB、OLS/BP/RESET/VIF、Pearson、BH/BY/Holm/Bonferroni 与正态近似功效；
  数据不足仅记 not_computable / reporting_gap，绝不等同方法错误。仍保留 method_stats /
  results_discussion / reproduce 历史高分规则。Use for 研究方法、统计报告、伪重复、
  多重比较、功效、p 值或模型诊断审查；不负责检索综述、翻译、代写结论或投稿决定。
---

# method-stats-audit（研究方法与统计审查）

方法学与统计审查在这些地方系统性失败，而每一种都"看起来完成了"：

- 给出一句"统计方法不当""建议补充样本量说明"，却指不出是第几节、哪张表、哪一句；
- 把"作者没有报告"和"作者做错了"混为一谈；
- 把可接受的做法判成硬伤，把真正的硬伤写成建议；
- 比较复现结果不设容差，"接近"与"偏离"无法区分；
- 超出容差的指标不说明差距是数值噪声还是方法学问题。

旧版把可由结构化读取判定的检查做成规则；本次新增的 v2 不把“字段填齐”冒充科学质量。
它先完成十四面证据审查，再对数字/原始数据做实际计算，并按构造区分“方法缺陷”、
“报告不全”、“数值不一致”、“诊断信号”和“审查自身不可判定”。

## 主工作流：十四面审查与真实统计重算（v2，正式案例优先）

### 第 0–2 步：来源、适用性与先交付

1. 读取 `/input/case.json`、`task.md`、实际稿件、统计表、补充材料与数据；保存 `case_id`、
   `output_contract`、稿件/数据/代码版本。不得按领域标签补研究设计或数字。
2. 先按 task 实际指定的方法学材料定位方法、结果、表格。`statsrun.py` 可直接读
   TXT/MD/TEX；PDF 在运行环境内惰性尝试 PyMuPDF → pypdf → pdftotext。无文本层的扫描件
   使用环境 OCR 后再审；仍不可读时把相关面列 not_checked，不制造清晰判断。
3. 先把当前发现与不可计算项写到 `/app/work`。每个实质发现均带 `source_quote`（必须真实
   出现在原稿）或 `source_locator`（具体节/页/表/行）；只有报告缺口可以仅给查过的范围。

### 第 3 步：真正走完十四面，不用统一模板替代判断

| dimension | 审查任务与不要误报之处 |
|-|-|
| design_question_match | 设计能否回答因果/诊断/预测/描述问题；观察性设计不是自动错误 |
| independent_units | 分配/实验/观察/分析单位是否相同，重复测量与聚类是否被模型承认 |
| randomization_blinding | 序列、隐藏、实施、开放/盲法与主要终点；开放标签是合法明确报告 |
| sample_size_power | n 的独立单位、效应来源、α/把握度/失访；功效必须使用同一模型口径 |
| missing_data | 缺失数量、位置、机制假设和处理；“未报告”不证明处理错误 |
| outliers | 检出、保留/剔除依据、是否预设；合格预设处理不报警 |
| distributions_variance | 分布与方差假设的图形/检验和稳健替代；非显著不等于“证明假设真” |
| model_choice | 结局类型、链接函数、数据结构、函数形式、异方差/共线性匹配 |
| multiplicity | 组族、方法、调整 p、探索/确证界限；探索性多终点不可硬套预设校正确证 |
| effect_size_ci | 效应大小、尺度、CI、自由度、精度；显著性不是效应大小 |
| p_value_interpretation | p 是 H0/模型下尾概率，不是 H0 后验概率；非显著不等于等效 |
| correlation_causation | 线性相关/显著性不提供因果方向；有时间/设计/识别证据才可谈因果 |
| sensitivity_robustness | 缺失、异常、模型、测量、未测混杂等结论敏感性及不一致解释 |
| reproducibility | 数据/代码/版本/命令/环境/种子/容差与实算差值；无记录不虚构状态 |

给已检查但不适用的面写 `dimension_coverage[dimension] = {status:"not_applicable",
rationale:"具体设计与原稿依据"}`；无 rationale 的标记不算完成。`review_complete:true`
只有在十四面确有输入/适用性决定、无 finding 且全部数值可算时才可能 clean，不能
单独用以产生“全部通过”。缺材料的面保留 `not_assessable_from_supplied_materials`。

### 第 4 步：录入可复核字段并真实计算

**摘要统计量检验。** `statistical_checks[]` 支持：

```json
{
  "type": "welch_t",                         // 或 independent_t / student_t
  "name": "Results Table 1 primary contrast",
  "source_locator": "Results Table 1",
  "source_quote": "原稿真实句子",
  "mean1": 5.2, "sd1": 1.2, "n1": 30,
  "mean2": 4.8, "sd2": 1.8, "n2": 35,
  "equal_var": false, "alternative": "two-sided", "confidence": 0.95,
  "reported_p": 0.29033248197735895,          // 可省略；有则比对
  "reported_statistic": 1.0668698993381636,
  "reported_df": 59.61035784930767,
  "reported_ci": [-0.3500696314290168, 1.1500696314290175],
  "reported_effect_size": 0.25758631737822185, "effect_type": "cohens_d"
}
```

必须给 `ddof=1` 的样本 SD。Welch 使用 \(SE=\sqrt{s_1^2/n_1+s_2^2/n_2}\) 与
Satterthwaite df；Student 使用合并方差；输出真实 t、df、两侧/单侧 p、均值差 CI、
Cohen d 与 Hedges g。`reported_p_operator` 可为 `< <= = >= >`，容差可声明；确实正确的
报告值不误报。p/CI 决策一致性只在两侧检验且 `confidence = 1 - alpha` 时比较，90% CI
配 α=0.05 不会被错判冲突。

**功效。** 用 `power_analyses[]` 或 type=power：

```json
{"name":"sample-size planning", "effect_size":0.5, "power":0.8,
 "alpha":0.05, "ratio":1.0, "alternative":"two-sided", "solve":"nobs1"}
```

`solve` 可选 power/effect_size/nobs1/ratio，`ratio=n2/n1`；nobs1 返回连续值、向上取整
和总 N。采用两组独立正态近似（不是 noncentral-t 精确功效）：上例实得每组
62.790884、向上各 63、总 N=126。`reported_power` 只在注明正态口径时比较，缺参只生成
not_computable。若论文说精确 t 功效，应借助环境 statsmodels `TTestIndPower.solve_power`
复核，不把本近似差值直接判为论文错误。

**多重比较。** `comparison_families[]` 含 `{name,method:bonferroni|holm|bh|by,
confirmatory:bool,comparisons:[{name,p,reported_adjusted_p}]}`。引擎按原 p 的真实值
计算并恢复输入顺序，支持 Bonferroni/Holm/BH/BY；确证组族未声明校正时是报告缺口；
未声明方法时默认 BH 仅标 hypothetical，绝不归属于作者。BY 记录一般依赖保守解释。

**原始数据诊断。** `diagnostics[]` 支持：

| type | 输入与真实输出 |
|-|-|
| levene | `groups:[[...],[...]]` 或 raw_data 的 group_column/value_column；center 为 median/mean/trimmed，以绝对偏差做单因素 ANOVA，输出 F、df、p |
| normality | `values` 或 column；计算 Jarque–Bera、偏度、超额峰度、chi2(df=2) p；不冒充 Shapiro |
| regression | `y`、`x`（可配 y_column/x_columns）；纯 Python OLS 系数/R²/RMSE，Durbin–Watson、BP、fitted-power RESET F、逐列 VIF |
| correlation | 成对 x/y 或 x_column/y_column；Pearson r、t(df=n−2) p、Fisher-z CI |

raw data 可直接放 `raw_data:[{column:value,...}]`；CSV 从 case 的 `data_path` 或用
`--data /input/data.csv` 提供。BP 使用平方残差对给定设计矩阵的辅助回归并同时给 LM 与
F 口径；RESET 加 fitted value 的二次/三次项并做 F 检验，拒绝不告知唯一正确模型；
VIF = 1/(1−辅助回归 R²)，只作逐预测变量信号，阈值不是“模型无效证明”。只有附加
`reported_*` 或调用方显式声明 alpha 阈值时，才产生数值不符/诊断 finding；不可拟合、
秩亏或缺列只写 unevaluated 原因。

**其他实算与解释：**
- `independence` 记录分配/分析单位、n_observations、n_independent_units、模型和是否明确
  处理聚类；实算 observations_per_independent_unit。独立单位少于观测且按行独立是高严重度。
- `missing_data` 记录 expected_n/observed_n/missing_count，实算缺失数与比例，再核账目、
  机制假设和处理；`outliers` 查预设、剔除与敏感性；`sensitivity_analyses` 记录真实结果。
- `model` + `outcome_type` 检查 linear/continuous、logistic/binary、Poisson/count、
  Cox/time_to_event 等；`conclusion` + `design` 门控因果过度。
- `p_value_statements[]` 含 p/alpha/effect_size/claim，区分原假设后验概率、非显著等效、
  显著即重大、用一个显著另一个不显著代替直接交互检验。
- `reproducibility.reported_values[]` 逐值给 reported/recomputed/tolerance，实算差值；
  `review_findings[]` 保留人工实质判断，但必须有源引/定位和有界 defect_class，伪引被拒。
- `legacy_sections` 默认 auto（忠实字段齐备时跑旧 method_stats / results_discussion /
  reproduce）；也可只挑选旧 pass，旧 finding 保留原 rule、严重度、reporting_gap 与定位。

### 第 5 步：主入口与退出码

```bash
python scripts/statsrun.py --case /input/case.json --out /app/output
python scripts/statsrun.py --case /input/case.json --manuscript /input/paper.pdf --data /input/data.csv --out /app/output
# 标注为示例的最小等价输入：
python scripts/statsrun.py --spec examples/spec-stats.json --out out_stats
```

0=clean；3=review（报告缺口、诊断信号、不可计算或面未查完）；4=blocked（高严重度
矛盾或证据伪造）；5=undetermined（无可用稿件也无可审结构输入）。运行重复同一路径
覆盖同一 result.json，不累积 findings；同输入字节级确定。

### 第 6 步：result.json 与证据复核

回原文复核每条 finding，修正错误 quote/抽取后重跑。最终自动保留 case_id 与
output_contract 全键（额外非输入值原样直通、不可推导 null + limits），并交付：
`audit_report[]`、`method_dimensions[14]`、`statistical_recalculations[]`、
`evidence_and_boundaries{manuscript_quotes,field_evidence,pending_review,not_checked,
not_computable}`、`result_status`、`overall_assessment`、两套 severity_counts、
checked、sources、limits 和 review_receipt。高严重度数值矛盾与报告缺口不混；
overall grade 不是 accept/reject，publication_decision 固定 null。

## 六步兼容入口（Harbor / Legacy，保留原高分路径）

运行时原始输入固定为 `/input/case.json` 与 `task.md`；中间产物写 `/app/work`，最终
结果写 `/app/output`。依序执行：

- **第 0 步·读案例**：读 `/input/case.json`，取 `case_id` 与 `output_contract`，再按
  `task.md` 指向的路径读**实际稿件**（PDF/文本）与方法学材料。读实际文件，不按文件
  名或领域标签猜内容——实际输入文件和原论文是事实依据。
- **第 1 步·判形态路由**：按「任务措辞与形态 → 路由」决策表选 section；完整方法学
  审查跑 method_stats 加 results_discussion（方法报告齐备性与结果报告纪律两道），
  有复现方案的任务加跑 reproduce。
- **第 2 步·先产出目标产物**：先把审查单本身（逐条问题、定位、缺陷类型、严重度、
  依据、修改建议）写进 `/app/work` 作为中间交付——预算有限时先有诚实的部分清单。
- **第 3 步·构造 spec**：把稿件方法节与统计报告抽取成所选 route 的 spec 字段。
  **论文没写的就是没写**：留空并标注——报告缺口正是要报的发现，不许替论文编一个
  声明去安静规则。
- **第 4 步·审计**：跑 `scripts/secrun.py`，得 findings 与 result.json。
- **第 5 步·修发现重跑**：逐条回原文复核——抽取错的重抽；确认论文确实没报告的，
  finding 保留（这就是审查单要交的东西）；引擎口径内误报按 Limits 处理并说明。
- **第 6 步·合并 result.json**：写 `/app/output/result.json`——回填 case_id 与
  output_contract 点名的每个字段（三段结构映射见下），引擎 findings、
  severity_counts、checked、limits 原样保留作为操作证据。

## 任务措辞与形态 → 路由

| 任务措辞 / 案例形态 | 跑什么 | 审什么 |
|-|-|-|
| 研究方法与统计审查 / 方法学审查 | `--section method_stats` 加 `--section results_discussion` | 设计-变量-样本量声明齐备性 + 结果报告纪律，合并两份 findings |
| 研究设计审查（设计类型、对照、盲法、主要终点） | `--section method_stats` | design_unstated、control_missing、randomisation_unstated、blinding_unstated、endpoint_not_primary |
| 变量定义审查（暴露/结局/协变量定义与类型） | `--section method_stats` | variable_undefined、variable_role_missing、variable_type_missing、cutpoint_unjustified、missing_handling_undeclared |
| 统计方法审查（模型与数据结构匹配、多重比较） | `--section method_stats` | model_unstated、model_type_mismatch、multiple_comparisons_unaddressed、ci_missing |
| 样本量与检验效能审查 | `--section method_stats` | sample_size_missing、sample_size_basis_missing、attrition_unaccounted |
| 结果报告审查（效应量、p 值、误差棒、局限） | `--section results_discussion` | 数值与图一致、显著性口径、阴性结果、冲突文献、局限分级 |
| 复现方案 / 验证报告（材料、环境、参数、容差） | `--section reproduce` | 六阶段闭环 + 四工件 + 差距分类 |
| 复现结果比较（"接近"与"偏离"要区分） | `--section reproduce` | no_tolerance、metric_no_verdict、difference_unclassified |
| 统计输出缺失 / 材料不足以判断 | 对应字段留空 | 缺口以 reporting_gap finding 呈现，不编造 |
| 阴性结果与冲突文献的诚实报告 | `--section results_discussion` | negative_result_omitted、conflicting_literature_ignored |
| 因果措辞与设计不匹配 | `--section results_discussion` | causal_overreach（observational/correlational 门控） |
| 文献检索综述 / 全文翻译 / 语言润色 / 投稿决策 | 不属本 Skill | 明确说明边界，不产出审查单 |

## Workflow

### 第 1 步·抽取结构化 spec

读实际稿件与补充材料，为所选 route 写 spec。

method_stats spec —— 每个字段被哪些规则消费：

| 字段 | 消费者 |
|-|-|
| design | 设计类型（experimental / observational / rct 等）；比较型设计门控对照/随机化/盲法检查 |
| controls, randomisation, blinding | 对照、分配方式、盲法声明（blinding 键缺席即报——"未设盲"也要明说） |
| endpoints[] | {name, primary, timepoint}——主要终点须事先标记 |
| variables[] | {name, role, type, definition, missing_handling, cutpoint, cutpoint_basis}——role 六选一，type 六选一 |
| model | 统计模型/检验名；与结局变量类型做匹配检查 |
| inferential | true 时 model 为空即报 |
| comparisons[] | 条数 ≥3 且未声明多重比较处理即报 |
| p_values_reported, confidence_intervals | 报了精确 p 值而未报 CI 即报 |
| sample_size, sample_size_basis | 样本量与其估算依据 |
| recruited_n, analysed_n, attrition_handling | 入组、分析、脱落处理 |

results_discussion spec：

| 字段 | 消费者 |
|-|-|
| design | experimental / observational / correlational——门控因果措辞 |
| results_text, discussion_text | 结果与讨论两半 |
| figures[] | {id, values, has_errorbar, errorbar}——正文数值必须出现在图数据中 |
| comparisons[] | {name, significant, strength}——每个比较要有显著性判定 |
| literature[] | {key, agrees, finding}——冲突文献必须被讨论回应 |
| limitations[] | {level, text}——level 是 method / sample / measurement / statistics |

reproduce spec（materials、environment、parameters、run、results、verdict 在 checklist 对象内）：

| 字段 | 消费者 |
|-|-|
| commit, data_version, commands | 第二台机器需要的工件 |
| materials[] | {name, source, version, state, kind}——kind 为 code/repository/weights/model 须带 license |
| environment | {dependencies, hardware, seed} + dependencies_detail[]（paper_version/actual_version/conflict） |
| parameters[] | {name, source}——source 是 paper / code / assumed；paper/code 需 locator，assumed 需 justification |
| run | {logs, exit_status} |
| results | {tolerance, comparison_basis, statistic, metrics[]}，metric 带 {name, paper, reproduced, within_tolerance, delta_class, explanation} |
| verdict, verdict_basis | 分级结论：reproducible / partially_reproducible / not_reproducible 及依据 |

### 第 2 步·运行

```bash
python scripts/secrun.py --spec spec.json --out /app/output --section method_stats
python scripts/secrun.py --spec spec.json --out /app/output --section results_discussion
python scripts/secrun.py --spec spec.json --out /app/output --section reproduce
```

退出码：0 clean，3 review，4 blocked（有 high finding），5 undetermined（拒绝运行
——见 Failure handling）。每次运行向 out 目录写 result.json。确定性引擎：同一 spec
重跑得到同一份审查单——复核人可以按记录独立重跑。

### 第 3 步·交付

result.json 含 case_id、section、status、findings[]、severity_counts、checked、limits
以及 output_contract 点名的字段。把多道 pass 的 findings 合并成一份按稿件位置排序的
审查单；每条 finding 自带定位字段（variable、stage、metric、field、句子文本），保持
附着。每条发现按缺陷性质分两类：方法缺陷（矛盾类——control_missing、
model_type_mismatch、non_significant_claimed_as_effect 等）与报告不全（声明缺失类，
finding 带 reporting_gap: true）。判不了的事项标待复核，不编造判定，不悄悄丢条目。

## 规则库

### statsrun v2 —— 实算、诊断、解释与证据（完整规则索引，40 条）

| rule | severity / 类型 | 真实触发条件 |
|-|-|-|
| `msv.design_question_mismatch` | high / 方法缺陷 | 明确研究问题类型与设计无法匹配 |
| `msv.pseudoreplication_independence_conflict` | high / 方法缺陷 | 分配/实验与分析单位不同且未处理依赖 |
| `msv.pseudoreplication_count_confirmed` | high / 方法缺陷 | 实算观测/独立单位 >1 且按独立行分析 |
| `msv.independent_unit_count_impossible` | high / 数值矛盾 | 独立单位数超过总观测数 |
| `msv.model_outcome_mismatch` | high / 方法缺陷 | 声明模型与结局类型不兼容 |
| `msv.reported_p_recompute_mismatch` | high / 数值矛盾 | 重算 p 与报告值/不等式在容差外不符 |
| `msv.reported_statistic_recompute_mismatch` | high / 数值矛盾 | 实算检验统计量与报告值不符 |
| `msv.reported_df_recompute_mismatch` | high / 数值矛盾 | 实算自由度与报告值不符 |
| `msv.reported_ci_recompute_mismatch` | high / 数值矛盾 | 实算 CI 与报告值不符 |
| `msv.reported_effect_recompute_mismatch` | high / 数值矛盾 | 实算 Cohen d/Hedges g 与报告效应不符 |
| `msv.p_ci_decision_conflict` | high / 数值矛盾 | 同一 α/置信水平/原值下 p 与 CI 决策冲突 |
| `msv.power_recompute_mismatch` | high / 数值矛盾 | 同一正态口径的功效与报告值不符 |
| `msv.adjusted_p_recompute_mismatch` | high / 数值矛盾 | 重算 Bonferroni/Holm/BH/BY 与调整 p 不符 |
| `msv.regression_coefficient_recompute_mismatch` | high / 数值矛盾 | OLS 按列顺序重算的系数与报告不符 |
| `msv.diagnostic_p_recompute_mismatch` | high / 数值矛盾 | BP/RESET p 与同输入诊断重算不符 |
| `msv.missing_count_inconsistent` | high / 数值矛盾 | 缺失数与 expected−observed 不一致 |
| `msv.data_driven_outlier_exclusion` | high / 方法缺陷 | 非预设异常剔除且无敏感性分析 |
| `msv.correlation_causal_overreach` | high / 解释错误 | 观察/相关设计配明确因果结论 |
| `msv.p_probability_of_null_misread` | high / 解释错误 | p 被解释为原假设为真的后验概率 |
| `msv.nonsignificant_as_no_effect` | high / 解释错误 | p≥alpha 被当作无效/等效证明 |
| `msv.significance_difference_without_direct_test` | high / 解释错误 | 用显著/不显著之差代替效应差的直接检验 |
| `msv.significance_equated_with_importance` | medium / 解释错误 | 只凭显著称重大/临床重要而无效应量 |
| `msv.effect_size_missing_for_claim` | medium / 报告缺口 | 显著性声称未含效应估计 |
| `msv.multiplicity_unaddressed` | medium / 报告缺口 | 多终点确证族无多重性方法 |
| `msv.missing_handling_missing` | medium / 报告缺口 | 有缺失但无处理说明，不推断方法错误 |
| `msv.missing_assumption_unreported` | medium / 报告缺口 | 命名缺失处理但无机制/假设依据 |
| `msv.outlier_handling_missing` | medium / 报告缺口 | 检出异常但无处理说明 |
| `msv.sensitivity_analysis_missing` | medium / 报告缺口 | 假设相关风险存在但无稳健性报告 |
| `msv.reanalysis_fields_missing` | medium / 报告缺口 | 重跑缺数据/代码版本、命令或种子 |
| `msv.reanalysis_value_mismatch` | high / 数值矛盾 | 已声明初值和复算值之差超过容差 |
| `msv.equal_variance_assumption_signal` | medium / 诊断 | Levene 拒绝且模型声明依赖等方差 |
| `msv.residual_normality_signal` | medium / 诊断 | JB 拒绝且模型声明依赖正态矩假设 |
| `msv.model_specification_signal` | medium / 诊断 | RESET 拒绝，不据此指定唯一模型 |
| `msv.heteroskedasticity_signal` | medium / 诊断 | BP 辅助回归显著，建议稳健方差/敏感性 |
| `msv.collinearity_signal` | medium / 诊断 | 某预测变量 VIF 超调用方声明启发阈值 |
| `msv.reviewer_substantiated_issue` | assessment 给定 | 有来源证据的实际方法学发现 |
| `msv.evidence_not_in_source` | high / 审查错误 | 输入 source_quote 不在实际原稿中 |
| `msv.reviewer_issue_unverified` | high / 审查错误 | 实质发现无来源且无报告缺口边界 |
| `msv.legacy_audit_failed` | high / 审查错误 | 请求的旧 pass 执行失败，不静默跳过 |
| `msv.input_not_readable` | undetermined | 既无可读原稿也无可审的结构化统计输入 |

报告缺口集中在 medium；数值冲突与可证实方法/解释错误的严重度单独输出，不从漏洞
数量推断总体质量。所有 non-computable 仅位于 evidence_and_boundaries，不列方法 finding。

### method_stats —— 研究设计·变量·统计方法·样本量（完整规则索引，19 条）

| rule | severity | 证明什么 |
|-|-|-|
| `msa.no_study` | high | 设计、变量、终点、比较均未声明——没有可审的研究 |
| `msa.design_unstated` | high | 声明了变量/终点但未声明研究设计（报告缺口） |
| `msa.control_missing` | high | 比较型设计没有声明对照/比较组——方法缺陷 |
| `msa.randomisation_unstated` | medium | 比较型设计未说明分组分配方式（报告缺口） |
| `msa.blinding_unstated` | medium | 比较型设计对盲法只字未提——"未设盲"也要明说（报告缺口） |
| `msa.endpoint_not_primary` | medium | 列了终点但无一标记为主要终点 |
| `msa.variable_undefined` | medium | 变量无定义，两个读者会填出两种值（报告缺口） |
| `msa.variable_role_missing` | medium | 变量未声明暴露/结局/协变量/分组角色（报告缺口） |
| `msa.variable_type_missing` | medium | 变量未声明测量类型，模型匹配无从检查（报告缺口） |
| `msa.variable_type_unknown` | low | 变量类型超出可识别集合 |
| `msa.cutpoint_unjustified` | medium | 分类切点无依据（文献/标准/预设）（报告缺口） |
| `msa.missing_handling_undeclared` | medium | 变量未声明缺失值处理，分析集无定义（报告缺口） |
| `msa.model_unstated` | high | 做了推断检验但未声明统计模型/检验 |
| `msa.model_type_mismatch` | high | 模型承载不了声明的结局类型——方法缺陷 |
| `msa.multiple_comparisons_unaddressed` | medium | ≥3 个比较而未声明多重比较处理（报告缺口） |
| `msa.ci_missing` | medium | 报了精确 p 值而未报置信区间（报告缺口） |
| `msa.sample_size_missing` | high | 全记录无任何样本量（报告缺口，high 因其影响每个估计的精度解读） |
| `msa.sample_size_basis_missing` | medium | 有样本量无估算依据（把握度/效应量来源/α）（报告缺口） |
| `msa.attrition_unaccounted` | medium | 入组多于分析且未说明脱落处理（报告缺口） |

### results_discussion —— 结果报告纪律（完整规则索引，19 条）

| rule | severity | 证明什么 |
|-|-|-|
| `rd.results_missing` | high | 无结果部分文本——交付物缺一半 |
| `rd.discussion_missing` | high | 无讨论部分文本 |
| `rd.value_not_in_figures` | high | 结果文本数值不在图表数据中——文图不一致 |
| `rd.errorbar_meaning_undeclared` | high | 画了误差棒但未说明是 SD/SE/CI |
| `rd.comparison_no_verdict` | high | 比较未给出显著性判定 |
| `rd.statistic_missing` | high | 声称显著却无检验统计量或 p 值 |
| `rd.non_significant_claimed_as_effect` | high | 不显著比较被描述成升高/降低 |
| `rd.interpretation_in_results` | high | 结果部分出现因果/解释性语言 |
| `rd.mechanism_as_fact` | high | 机制以事实口吻陈述而无任何限定 |
| `rd.discussion_uncited` | high | 讨论断言既不指向本研究数据也不指向文献 |
| `rd.causal_overreach` | high | 观察性/相关性设计使用因果措辞 |
| `rd.negative_result_omitted` | high | 不显著的比较在讨论中从未提及 |
| `rd.conflicting_literature_ignored` | high | 文献表记录的冲突在讨论中无回应 |
| `rd.limitations_missing` | high | 全文无任何局限说明 |
| `rd.limitation_vague` | medium | 局限只说"有待进一步研究" |
| `rd.limitation_level_unknown` | low | 局限级别超出 method/sample/measurement/statistics |
| `rd.limitation_level_narrow` | medium | 局限只覆盖单一层面 |
| `rd.unitless_number` | medium | 结果中的裸数字无单位无语境 |
| `rd.overclaim` | medium | 比较表无强度标注时使用绝对化措辞 |

### reproduce —— 复现链（完整规则索引，25 条）

| rule | severity | 证明什么 |
|-|-|-|
| `repro.stage_missing` | high | 复现闭环六阶段之一缺席，链条断 |
| `repro.stage_unknown` | low | 声明的阶段名超出六阶段 |
| `repro.no_stages` | medium | 未声明闭环阶段 |
| `repro.no_commit` | high | 未记录仓库版本，代码无法再次检出 |
| `repro.no_data_version` | high | 未记录数据版本，输入无法还原 |
| `repro.no_command` | high | 未记录产生结果的命令，运行无法重复 |
| `repro.material_without_source` | high | 材料无来源 |
| `repro.material_without_version` | medium | 材料未记录版本 |
| `repro.material_state_undeclared` | medium | 材料未声明 present/missing/partial |
| `repro.material_no_license` | medium | 可再分发的工件（code/repo/weights/model）无 license |
| `repro.environment_incomplete` | medium | 环境快照缺 dependencies/hardware/seed 之一 |
| `repro.env_conflict_unflagged` | high | 安装版本与论文声明版本不一致且未记录 |
| `repro.parameter_source_undeclared` | high | 参数未声明来自 paper/code/assumed |
| `repro.assumed_without_justification` | high | 复现者自选的参数无理由 |
| `repro.parameter_no_locator` | medium | 声称来自 paper/code 的参数无定位 |
| `repro.no_tolerance` | high | 无容差声明——"接近"与"偏离"无法判定 |
| `repro.no_comparison_basis` | medium | 未说明对齐的对象（表/曲线/指标） |
| `repro.no_statistic` | low | 未声明比较用统计量或聚合方式 |
| `repro.metric_no_verdict` | high | 比较的指标未给容差内/外判定 |
| `repro.difference_unclassified` | high | 超容差差距未分类为数值噪声或方法学 |
| `repro.difference_unexplained` | medium | 分类了但未解释 |
| `repro.verdict_unclassified` | high | 结论不在三级分类内 |
| `repro.verdict_without_basis` | high | 分级结论无依据 |
| `repro.no_logs` | medium | 运行无日志，执行过程不可查 |
| `repro.no_exit_status` | medium | 未记录代码是否成功结束 |

### Failure handling —— 拒绝运行（1 条）

| rule | severity | 发生了什么 |
|-|-|-|
| `audit.no_section` | high | 案例无法按声明运行：spec 缺失或不可读、不是 JSON 对象、未声明 section 或 section 名未知——以 exit 5 拒绝并写 status undetermined 的 result.json，绝不抛 traceback |

## 输出契约与三段结构映射

引擎级 result.json（secrun.py 直接产出）：schema_version、section、status（clean /
review / blocked / undetermined）、findings[]（每条带 rule、severity、message 与定位
字段——variable/stage/metric/field/句子文本，报告缺口类另带 reporting_gap: true）、
severity_counts、checked（检查的字段/句子数）、case_id（spec 顶层有则回填）、
output_contract 点名的每个键（spec 携带同名值则原样拷入；大体积输入字段除外；推导
不出则置 null 并在 limits 记一条说明）。

最终交付把引擎 findings 组装进 output_contract 点名的三段结构（字段名用评分口径原词）：

| 输出段 | result.json 键 | 组装来源与完成标准 |
|-|-|-|
| 审查报告 | audit_report[]：每条 {rule, severity, location, finding, basis, suggestion, defect_class} | 由 findings[] 逐条映射；defect_class 分"方法缺陷/报告不全"；完成标准：五个检查面（研究设计、变量定义、统计方法、样本量、结果报告）都查过 |
| 依据与边界 | evidence_and_boundaries：{manuscript_quotes[], field_evidence[], pending_review[]} | 稿件原文引用、字段声明证据、待复核项；完成标准：区分错误、证据不足和建议 |
| 结果状态 | result_status：{pass[], problems[], pending[], not_checked[]} 加 status 与 status_reason | 通过、问题、待复核和未检查项分别列出；完成标准：不凭空补齐缺失信息 |

status 映射：clean → 全部通过；review → 有 medium/low 待处理（status_reason 写明待补
什么）；blocked → 有 high（status_reason 列出）；undetermined → 运行失败（写明环节）。
材料缺失、无法判断、运行失败三种情况分开说明。

## 最小调用示例（示例）

输入 `examples/spec-contract.json`：case_id 为 challenge-9e7302fd-case-02，
output_contract 点名 audit_report、evidence_and_boundaries、result_status，研究记录
带五处缺陷（对照缺失、切点无依据、线性模型配 binary 结局、样本量无依据、16 例脱落
未说明）。调用：

```bash
python scripts/secrun.py --spec examples/spec-contract.json --out out_example
```

引擎实跑输出（本机实测，节略）：

```json
{
  "schema_version": "secrun/v1", "section": "method_stats", "status": "blocked",
  "findings": [
    {"rule": "msa.control_missing", "severity": "high"},
    {"rule": "msa.model_type_mismatch", "severity": "high",
     "model": "linear_regression", "outcome_type": "binary"},
    {"rule": "msa.cutpoint_unjustified", "severity": "medium",
     "variable": "pain_score", "reporting_gap": true},
    {"rule": "msa.sample_size_basis_missing", "severity": "medium", "reporting_gap": true},
    {"rule": "msa.attrition_unaccounted", "severity": "medium",
     "recruited": 80, "analysed": 64, "reporting_gap": true}
  ],
  "severity_counts": {"high": 2, "medium": 3},
  "checked": {"section": "method_stats", "items": 2},
  "case_id": "challenge-9e7302fd-case-02",
  "audit_report": null, "evidence_and_boundaries": null, "result_status": null
}
```

三个 contract 键引擎推导不出，置 null 并在 limits 说明——第 6 步由你把 findings 组装
填充（完整形状见 `examples/result-example.json`，标注为示例，不冒充正式案例结果）。

## Legacy Limits（旧 secrun 的边界；statsrun 已有独立重算能力）

- **引擎审计 spec，不直接读 PDF。** 从稿件抽取设计、变量、样本量与结果文本是调用方
  的工作；抽不到的留在 spec 外，由报告缺口规则呈现为发现——不是被悄悄跳过。
- **"报告不全"与"方法缺陷"按构造分开。** 声明缺失类 finding 带 reporting_gap: true，
  message 只断言"未声明"；只有矛盾类（模型-结局类型不匹配、安装版本与声明版本冲突、
  不显著被描述成效应）才判方法缺陷。引擎从不宣称"做法错了"除非声明本身矛盾。
- **模型-结局匹配按声明值判定。** 旧 `msa` 引擎不重跑分析，它核对声明的模型能否承载
  声明的结局类型；新 `statsrun` 在数值/原始数据齐备时另做真实重算，并把两种证据分层。
- **对照/随机化/盲法检查只对比较型设计门控。** single_arm 等设计合法地没有对照组，
  不触发 control_missing。
- **容差判断只在声明了 within_tolerance 时出现。** 引擎要求判定存在，不替你计算。
- **delta_class 是声明分类**（numeric_noise / methodological）；引擎检查分类存在且
  被解释，不检查分类正确。
- **因果与机制检查是词汇级。** 只在明确因果措辞（causes、导致、proves）上触发；
  "consistent with"、"may involve" 这类限定表达是可接受形式，保持安静。
- **误差棒查的是含义声明，不是对错。** SD 是否该用是判断题，spec 得声明。
- **局限覆盖按级别检查。** 规则核对声明的级别被处理；不为 spec 未描述的设计发明
  级别。

## 异常处置表

| 形态 / 故障 | 处置 |
|-|-|
| 扫描件 / 统计输出识别失败 | 置信降低的字段留空标 missing；对应检查项进 not_checked；报告 pending——不静默跳过 |
| 统计输出缺失（无 p 值/无 CI/无效应量） | 对应声明字段留空——ci_missing 等报告缺口规则呈现缺口，不编造数值 |
| 稿件缺页 / 方法节不全 | 缺什么抽什么；spec 声明 inferential 或 variables 时 design/model 缺失会照报——status_reason 说明是抽取缺口还是稿件缺口 |
| 图表无法解析 | figures 留空加注；文图一致规则不跑，结果状态写未检查 |
| 语言混杂（中英混排稿件） | 引擎 CJK 与拉丁断言/因果标记都识别；spec 保留原文措辞 |
| 变量类型与模型冲突 | model_type_mismatch 照报（high）；不自行改模型，建议在审查单中说明两种修法 |
| 样本量只在正文散落（无结构字段） | 用 sample_size 字段抄录声明值；全记录确实无 n 时报 sample_size_missing |
| spec 不可读 / 非 JSON 对象 / 无 section 名 | exit 5 拒绝，仍写 undetermined 的 result.json，绝不抛 traceback |
| section 名不在支持清单 | exit 5——查本文路由表拼写 |
| 同一输出目录重复运行 | 引擎确定性幂等：同 spec 同 findings；重复运行只为复核，不叠加状态 |
| 材料缺失、无法判断、运行失败 | 三类分开说明：materials_missing 类是发现、pending_review 是不确定性、undetermined 是运行状态——不互相冒充 |
| 多重比较条数不足 3 但声明了校正 | 无 finding；校正声明按 Limits 记录为存在性证据 |

## 使用增益与对照方法

- **公平对照**：同一稿件版本、相同输入格式、相同预算下，不加载本 Skill 的基础 Agent
  与加载后各跑一次，按四个可数项对比：条目可定位率（每条意见有无字段/表/句定位）、
  缺陷分级恰当率（方法缺陷与报告不全是否分开、严重度与性质是否相称）、报告缺口检出
  数（样本量依据、CI、脱落处理等声明的缺口抓到几条）、五检查面覆盖数。平台白板是对
  照基准，不是参赛者答案。
- **增益证据形式**：`scripts/bench_statsrun.py` 48 项检查（真实数值锚点、合格 RCT/
  观察性与聚类模型交叉验证、已知统计错误、不可计算降级）+ `scripts/bench_method.py`
  27 场景 + `scripts/bench_reproduce.py` 25 场景 + `scripts/bench_sections.py` 54 场景。
  每个实质缺陷有对应无误报守卫，两个引擎 clean baseline 都必须零发现且可确定复跑。

## 验证

```bash
python scripts/bench_statsrun.py   # 48 checks: 十四面主流程、数学锚点、已知错误交叉验证
python scripts/bench_method.py     # 27 scenarios: 旧五 facets 每规则与误报守卫
python scripts/bench_reproduce.py  # 25 scenarios: 旧复现链每规则与误报守卫
python scripts/bench_sections.py   # 54 scenarios: 旧跨 section 回归与误报守卫
```

本机全部通过；四个 bench 的 clean baseline 必须零发现。验证是作者维护工具，不是正式
案例编号工作流中的强制步骤；正式入口直接读实际材料并交付 result.json。

## Requirements

Python 3.9+（3.14 实测）。统计公式、分布尾概率、OLS 和 CSV 均由标准库实现，
NumPy/SciPy/statsmodels 不是冷导入依赖；正式环境若提供 statsmodels 可另用精确功效复核。
TXT/CSV 无额外依赖；直接读 PDF 时惰性使用环境已有的 PyMuPDF、pypdf 或 pdftotext，
都没有文字层则诚实记录不可读，不伪造原稿或分析结果。

## 创新增益

本 Skill 相比通用 Agent 的新增能力（每条附能力边界与增益证据形式）：

1. **可复核的审查单**：每条发现带规则 id、严重度、定位字段（variable / stage /
   metric / field / 句子文本）与 defect_class（方法缺陷或报告不全）——作者能逐条回复，
   复核人能按记录独立重跑得到同一份单子。
   *边界*：定位到字段/句/表，不到字符偏移。
   *证据形式*：bench 每条 finding 断言其定位字段存在；确定性引擎重跑逐字节一致。
2. **"没有报告"与"做错了"按构造分开**：声明缺失类发现带 reporting_gap 标记，message
   只断言声明缺失；只有矛盾类（模型-结局类型不匹配、不显著写成效应、安装版本与声明
   版本冲突）才判方法缺陷——直接对应 brief 点名的首要失败模式。
   *边界*：分类依据是 spec 声明；声明本身错了要靠人工复核（pending_review）。
   *证据形式*：bench_method 缺陷场景与 fp 守卫成对出现（gap 填上即安静）。
3. **模型-结局类型匹配检查**：声明的统计模型与结局变量类型可承载性核对（logistic
   需 binary、linear 需 continuous、cox 需 time_to_event 等）——"变量类型与后续统计
   模型对得上"从口号变成可计算规则。
   *边界*：按声明值判定，不重跑分析；混合结局类型的多模型论文按声明的首个结局判定，
   其余建议在审查单中人工核对。
   *证据形式*：bench model_type_mismatch 场景（线性模型配 binary 即报）。
4. **误报抑制的可计算守卫**：single-arm 设计不触发对照检查、显式 open-label 即满足
   盲法声明、正文内 n = 数字可替代样本量字段、比较少于 3 不要求多重比较声明、p 值
   未报不要求 CI——每条守卫都是 bench 里一个必须保持安静的 FP 场景。
   *边界*：守卫是声明级启发，边界情形以 Limits 口径人工复核。
   *证据形式*：bench_method 中 7 个 fp_ 前缀场景全部零发现。

## 方法学参考与实际落地

以下不是附录链接装饰，而是本包接口和计算规则的来源；为避免复制第三方实现，数值由
`statscore.py` 的标准库公式独立完成，并用 bench 中的数学锚点验证。

1. **SciPy（官方 GitHub）**：<https://github.com/scipy/scipy/blob/main/scipy/stats/_stats_py.py>。
   采用 `ttest_ind_from_stats` 的 Student/Welch SE 与 Welch–Satterthwaite df 定义、
   Levene 的 center=median/mean/trimmed 绝对偏差 ANOVA 机制、Pearson 线性相关限制。
   官方接口文档 <https://docs.scipy.org/doc/scipy/reference/generated/scipy.stats.ttest_ind_from_stats.html>
   与 <https://docs.scipy.org/doc/scipy/reference/generated/scipy.stats.levene.html>。
   本项目已实际计算 t/df/p/CI/效应量和 Levene F；并非仅写链接。
2. **statsmodels（官方 GitHub）**：诊断机制见
   <https://github.com/statsmodels/statsmodels/blob/main/statsmodels/stats/diagnostic.py>，
   功效接口见 <https://github.com/statsmodels/statsmodels/blob/main/statsmodels/stats/power.py>。
   按 Breusch–Pagan 残差平方辅助回归（LM/F）、Ramsey fitted-power RESET F、VIF 的
   1/(1−R_aux²) 与 `TTestIndPower.solve_power` 参数语义（effect_size/nobs1/ratio/alpha/
   alternative）落地；官方约束与非证明性解释见
   <https://www.statsmodels.org/stable/generated/statsmodels.stats.diagnostic.linear_reset.html>、
   <https://www.statsmodels.org/stable/generated/statsmodels.stats.diagnostic.het_breuschpagan.html>。
   本包的功效函数明确只到正态近似，不冒充精确 noncentral-t。
3. **SAMPL / CONSORT**：<https://www.equator-network.org/reporting-guidelines/sampl/> 与
   <https://www.equator-network.org/reporting-guidelines/consort/>。把研究设计、随机/盲法、
   样本量、参与者流/独立单位、统计方法、效应量/CI、精确 p、缺失/异常、敏感性和复现作为
   **报告完整性清单**，并显式保留这些指南“不是设计或质量评价证明”的边界；`msv.*`
   方法错误只能在独立正证据出现时才触发。

## 生态贡献

- **使用说明**：本文件含完整调用步骤（六步运行时入口与 Workflow）、输入输出解释
  （输出契约与三段结构映射）、关键方法（规则库与缺陷分类口径）、适用场景（路由表）、
  限制（Limits）、失败处理（Failure handling 与异常处置表）和自查方法（验证一节）。
- **依赖与配置**：Python 3.9+ 纯标准库、无第三方依赖、无安装步骤；比较型设计集合与
  模型-结局映射在引擎常量中声明，spec 字段全部可选、留空即报缺口。
- **示例（标注为示例）**：examples/spec-stats.json 是十四面主接口与正确数值的本地输入；
  examples/spec.json（旧 reproduce 路由）、examples/spec-contract.json（旧 method_stats
  contract 输入，exit 4 五条发现）、result-example.json 均为示意，不冒充正式案例答案。
- **检查清单可复用**：十四面 checklist + v2 40 条规则 + 历史 64 条规则
  （method_stats 19、results_discussion 19、reproduce 25、audit 1），每条带 id、
  severity 与证明/非证明边界，可直接人工复用。
- **bench 回归门**：四个 bench 共 154 项检查/场景（48 + 27 + 25 + 54），独立复跑，
  改动引擎后必须全过——是他人验证本 Skill 行为的最短路径。
- **适用范围与不适用**：研究设计、变量定义、统计方法、样本量与结果报告审查；不负责
  文献检索与综述、全文翻译、语言润色、代写审稿结论或投稿决策（路由表末行明确拒识）。
- **失败处理**：拒绝运行路径（exit 5 加 undetermined result.json）与 12 行异常处置表
  覆盖扫描件、统计输出缺失、缺页、混杂语言、模型冲突等常见故障。
- **维护信息**：规则 id 变更须同步本文规则表；bench 全过是合并条件；引擎内注释记录
  每条被移除规则的历史教训（避免回归）。
