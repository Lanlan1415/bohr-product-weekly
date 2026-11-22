---
name: stats-interpretation
description: >
  统计分析与结果解读：把一份带缺失值、异常值、重复记录的科研数据表清到可统计的
  状态，然后由引擎从数据本身重算统计层——每列描述统计（n、均值、SD、四分位、偏度、
  峰度、口径单位）、Welch t 检验与单因素 ANOVA（t、df、p 全部由纯标准库的不完全
  beta 函数算出，t/F 表锚点验证到 1e-6）、Cohen d 与 Hedges g 效应量、均值差 95%
  置信区间、Tukey 1.5-IQR 异常值、小样本偏度提示——再把声明的统计结论钉在重算值上：
  方向一致、显著性措辞一致、数值引用一致、声称的 p 与重算 p 不许矛盾。清洗全程
  留痕（rule id、行、列、原值、新值、理由），缺失按"未报告"处理绝不补零，重复
  记录与重复实验分开报告，result.json 回填 case_id 与 output_contract 全部字段。
  Use when a task supplies a research data table plus declared statistical claims
  or results that must be computed, checked, cleaned, and written up so the
  interpretation agrees with the numbers.
---

# stats-interpretation（统计分析与结果解读）

统计工作流里最贵的错误不是算错——是句子和数字对不上：实际更低的组被写成"更高"，
p=0.30 被写成"显著"，解读里引用一个表里根本不存在的数，三组数据被塞进两样本 t
检验而没人说第四组去哪了。这些错误在任何正确的算术之后都能存活，因为没有人把
句子拿回表里核对。本 Skill 做两次核对：先从表里把该算的数算出来，再把句子钉在
这些数上。

五个保证：

1. **统计层真实计算。** 描述统计（n、均值、SD、min/q1/中位/q3/max、IQR、偏度、
   峰度、观测到的单位口径）、Welch t、单因素 ANOVA（F、p、eta²）、Cohen d、
   Hedges g、均值差 95% CI 全部由引擎从数据行重算，纯标准库，t/F 分布经表锚点
   验证（t=2.2281, df=10 → p=0.05）。
2. **方向、显著性、数值、声称 p 四重一致。** 每条结论对照重算均值与 p：方向词
   矛盾、措辞与 p 矛盾、引用表算不出的数、声称的 p 与重算 p 的显著性判定相反，
   都会被点名——"p=0.04 被写成证明有效"有了引擎侧的对证。
3. **清洗不悄悄改值。** 每处修改带 rule id、行、列、原值、新值、理由；原始表
   原样存档并记录 sha256；清洗幂等，二遍还有改动即 high finding。
4. **异常是发现项不是崩溃。** 组内方差为零、样本量不足、缺失比例过半、三组只
   比两组、偏度异常——全部降级为命名发现项，退出码只有 0/3/4/5。
5. **无法核验的结论不算通过。** metric 不是表中的列、声称的分组不在数据里——
   这些是 high finding，不是静默跳过。

## Runtime：六步运行时入口

每个案例按同样六步执行。交付物与审计分离：审计检查结构，从不替你造数据。

**Step 0 — 读案例。** 读输入案例文件与任务说明。先抄出两样东西：案例标识
（case_id）与声明的输出契约（output_contract 点名的字段）。调用引擎时用 case
参数把案例文件带上，spec 忘了抄也会回填。

**Step 1 — 按任务形态路由。** 对照下表选主路径；拿不准就走完整通道（清洗 +
统计层 + 结论审计），它会安全降级——没声明的都被列名，不会被静默吞掉。

| 任务措辞（代表信号） | 路由 | spec 要点 |
|-|-|-|
| 数据表 + 声明的统计结论/结果解读需要核对 | 完整通道（清洗+统计层+审计） | rows/columns/stats |
| 只要清洗不要统计 | 清洗通道 | stats 留空 [] |
| "两组有没有差异、差异多大、多确定" | 完整通道：引擎直接给出重算的 t/p/d/CI | stats 可空，看 descriptives 与 stats_audit |
| 多组比较（三组及以上） | 完整通道：ANOVA（F/p/eta²）+ 多重比较提示 | stats 声明 correction 或 excluded_groups |
| 缺失值/异常值/重复记录疑虑 | 完整通道：缺失/越界/Tukey 异常值/重复实验分列 | missing_tokens、key_columns |
| 数据库里字段单位不明 | 清洗通道先声明口径，口径不明追问不硬算 | columns 的 target_unit、missing_tokens |
| 只要检验计算本身（scipy/statsmodels） | 上游做完检验，把结论放进 stats 让本 Skill 审 | stats[].p 用声称值 |
| 需要图表建议 | 完整通道：charts 给出推荐图型与理由 | — |
| 结果要写进报告，需要可复现证据 | 完整通道：run_manifest + original.json 存档 | — |
| 实验设计/样本量估算/论文写作 | none — 拒绝 | 超出本课题边界，不做 |
| 纯数值"算个 t 检验"而不给数据表 | none — 拒绝 | 没有行就无法重算，宁拒不猜 |

**Step 2 — 先产出目标产物。** 真正读表：哪些列、什么口径、哪些组、缺失与重复
在哪里。审计不能替你读数据，空心 spec 配上整齐的 schema 依然是失败案例。

**Step 3 — 组装 spec。** 一个 JSON 对象装下交付物、数据字典与契约：案例标识、
声明的输出契约字段（连同它点名的直通载荷）、列语义（numeric/date/categorical/
text/id）、目标单位与合理范围（范围要来自数据字典或物理上下限）、key_columns、
rows（内联或 table_path）、stats 结论数组（每条可带 direction、correction、
excluded_groups）。完整形状见 examples/spec-contract.json。

**Step 4 — 审计。** 跑引擎一次：

```bash
python scripts/cleandata.py --spec examples/spec-contract.json --out /app/output
```

退出码：0 clean，3 review（只有 low/medium 发现），4 blocked（出现 high 发现），
5 undetermined（案例无法按声明运行——spec 不可读/不是对象/没有行）。每个退出
路径都写出 result 文件；退出码永远不会来自 traceback。

**Step 5 — 修发现并重跑。** 每条发现点名规则与证据。修数据或修声明（改句子、
补口径、声明 excluded_groups），绝不修审计；修完重跑同一输出目录。同一输入
重复跑进同一目录会被 already_cleaned 拒绝（exit 4）——二遍永远不能叠在一遍上。

**Step 6 — 合并 result。** 引擎写出的 result 文件已携带：案例标识、output_contract
全部字段（案例自带值原样直通；引擎可推导键由审计填写；其余置 null 并写 limits，
绝不编造）、findings、severity_counts、stats_audit、descriptives、limits。保留该
文件作为案例的结构化结果，旁边是 cleaned.csv 与 original.json。

## Workflow：声明数据字典与统计结论

```json
{
  "case_id": "demo-stats-001",
  "rows": [
    {"subject": "S1", "group": "control", "response": "12.4 mg/L"},
    {"subject": "S4", "group": "drug", "response": "31.2 mg/L"}
  ],
  "columns": [
    {"name": "group", "semantic": "categorical"},
    {"name": "response", "semantic": "numeric", "plausible": [0, 100]}
  ],
  "key_columns": ["subject"],
  "missing_tokens": ["<LOQ"],
  "group_col": "group",
  "stats": [
    {"metric": "response", "test": "two-sample t-test",
     "group_col": "group", "group_a": "control", "group_b": "drug",
     "p": 0.01, "direction": "higher", "correction": "bonferroni",
     "interpretation": "给药组均值为31.23，高于对照组的12.37，差异有统计学意义"}
  ],
  "output_contract": {"case_id": "...", "status": "...", "stats_audit": "..."}
}
```

- rows 内联，或 table_path（逗号/制表符，UTF-8）。
- stats 每条是一个**声明**：引擎既审它也算它——重算记录会给出引擎自己算的
  t、df、p_computed、cohen_d、hedges_g、ci95。方向约定：interpretation 描述
  group_b 相对 group_a。p 接受数字或字符串（"<0.05"、"p=0.31"、"n.s."）。
  correction 声明多重比较校正；excluded_groups 声明被排除的组（三组只比两组
  时必须声明其一，否则 medium 提示）。
- value（可选）是声称的统计量（如均值差），与重算差值核对。

## 最小调用示例（示例）

输入：examples/example-spec.json（6 行两组数据 + 1 条结论）；examples/spec-contract.json
是带契约回填的完整版（含 case_id 与 output_contract）。

```bash
python scripts/cleandata.py --spec examples/spec-contract.json --out out_example
```

控制台输出（示意，路径随机器不同）：

```json
{"status": "clean", "case_id": "demo-stats-001", "findings": [],
 "stats_audit": {"n_claims": 1}, "wrote": "out_example/result.json"}
```

result 节选（示意，实跑所得，节略）：

```json
{
  "case_id": "demo-stats-001",
  "status": "clean",
  "stats_audit": {"claims": [{"metric": "response", "n_a": 3, "n_b": 3,
    "mean_a": 12.3667, "mean_b": 31.2333, "diff": 18.8667,
    "t_stat": 38.3344, "df": 3.89, "p_computed": 4e-06,
    "cohen_d": 31.2999, "hedges_g": 25.0399,
    "ci95_low": 17.4854, "ci95_high": 20.2479}]},
  "descriptives": [{"column": "group", "n_levels": 2,
                    "levels": {"control": 3, "drug": 3}},
                   {"column": "response", "n": 6, "mean": 21.8, "sd": 10.3478,
                    "median": 21.75, "units_seen": ["mg/L"]}],
  "charts": [{"column": "response", "chart": "box_plot",
              "why": "group comparison over 2 groups; show the spread, not just the mean"}],
  "figures": null,
  "limits": ["output_contract field 'figures' was not derivable by this audit"]
}
```

（示意输出——说明接口与结果形状，不是正式案例结果。）

## 输出契约

result.json 全字段（每个退出路径都写出）：

| 字段 | 内容 |
|-|-|
| case_id | 案例标识，从 spec 或 case 文件回显 |
| status | clean / review / blocked / undetermined |
| findings[] | 每条规则命中：rule、severity、message、证据（重算均值、p、异常行） |
| severity_counts | 按严重度计数 |
| stats_audit | 重算的声明记录：各组 n、均值、差值、t、df、p_computed、cohen_d、hedges_g、ci95、anova（多组时） |
| descriptives | 每列描述统计：数值列 n/均值/SD/四分位/偏度/峰度/单位口径；分类列 level 计数 |
| outliers | Tukey 1.5-IQR 栅栏外的值（行号+数值），列出不删除 |
| charts | 每种分析形状的图型推荐与理由 |
| pending_review | 待确认清单：无法解析、缺失、异常值、重复实验 |
| run_manifest | 引擎版本、解释器版本、行数、输入 sha256 前 16 位（无时间戳，逐字节可复现） |
| changes[] | 清洗台账：rule、row、column、original、new、why |
| cleaned_table / cleaned.csv | 清洗后可统计的表 |
| original.json | 原始行原样存档 |
| idempotent / quality_report / original_sha256 | 幂等自检、表算的质量报告、输入指纹 |
| output_contract_* | 契约点名的全部字段：直通/审计填写/null+limits |
| limits | 本轮无法做到的事，含置 null 的契约字段 |

## 映射到评分要求的字段（原词）

| 评分要求的字段（原词） | 本 Skill 的交付 |
|-|-|
| 分析结果（清洗表、统计结果、图表、代码） | cleaned_table + cleaned.csv；stats_audit 重算推断；descriptives；charts 图型推荐；run_manifest（可复现指纹） |
| 质量与复现证据（原始快照、规则表、日志、代码、版本） | original.json 原始存档；RULES 规则表随 result 输出；run_manifest 引擎/解释器/sha256；quality_report 表算值；bench 套件可复跑 |
| 异常说明（缺失、异常、失败查询、无法解释、人工确认） | findings 全量点名；pending_review 待确认清单；outliers 列出保留；limits 不可推导项 |

## 规则库与审计规则

清洗规则（带优先级，低号先跑；R04 在 R05 前所以范围检查看到的是换算后的值）：

| id | 优先级 | 规则 |
|-|-|-|
| R01 | 10 | 去除单元格首尾空白 |
| R02 | 20 | 未报告记号（ND、未检出、-999、空）按缺失处理，绝不按 0 |
| R03 | 30 | 把值解析为 数值/误差/单位/区间 结构 |
| R04 | 40 | 换算到目标单位并记录换算因子；换算被拒是命名缺口不是丢行 |
| R05 | 50 | 超出声明合理范围的值被标记（保留/剔除/盖帽由人在记录上决定） |
| R06 | 60 | 规范化实体键（大小写、空白、希腊/拉丁形近字；化学式数字保留——CO2≠CO） |
| R07 | 70 | 重复记录（同键同值）与重复实验（同键不同值）分开报告 |
| R08 | 80 | 日期规范化为 ISO 8601，不发明精度 |

审计 finding（引擎产出、按严重度；新增统计层规则加粗场景见 bench）：

| rule | severity | 证明什么 |
|-|-|-|
| `stats.direction_mismatch` | high | 结论方向与重算组均值矛盾（声称"高于"实际更低，或均值相等却声称有方向） |
| `stats.significance_mismatch` | high | 显著性措辞与 p 值矛盾（p 不小于 0.05 却写"显著"，或 p<0.05 却写"不显著"） |
| `stats.number_not_in_table` | high | 解读引用了表算不出的数字，或声称的统计量（value）与重算值不符 |
| `stats.metric_unknown` | high | 结论的 metric 不是表中的列，或该列没有数值——数字无法溯源 |
| `stats.group_unknown` | high | 声称的分组不在分组列里——比较无法从数据算出 |
| `stats.sample_too_small` | high | 某组可用值少于 2——没有方差就没有检验，显著性无从谈起 |
| `stats.zero_variance` | high | 某组方差为零——t 统计量无定义，比较不可审计 |
| `stats.p_mismatch` | medium | 声称的 p 与引擎重算的 p 显著性判定相反——声称值可能来自别的检验，先对证再交付 |
| `stats.groups_omitted` | medium | 分组列有 ≥3 组而结论只比两组——不声明 excluded_groups/correction 就不许读成全局结论 |
| `stats.multiple_comparison` | medium | ≥3 条两两比较声明且未声明校正——反复换对凑显著是常见的假阳性制造机 |
| `stats.missing_ratio_high` | medium | 某组超过一半的值缺失或不可用——比较建立在残缺样本上 |
| `stats.assumption_normality` | medium | 小样本偏度/峰度异常——参数检验读数前先核分布或改非参数 |
| `stats.outliers_iqr` | medium | Tukey 1.5-IQR 栅栏外的值——列出保留，去留由人决定 |
| `stats.claim_malformed` | medium | 声明不是对象、缺 interpretation、stats 不是列表、或声称的 p 无法解析——跳过并点名，显著性检查绝不静默失效 |
| `clean.missing_values` | medium | 有未报告值——按缺失处理，绝不补零 |
| `clean.unparsed_values` | medium | 无法解析的单元格保留为命名缺口 |
| `clean.duplicate_records` | low | 完全相同的行——复核后可删 |
| `clean.duplicate_experiments` | medium | 同实体不同值——是两次测量，不得静默合并 |
| `clean.not_idempotent` | high | 二遍清洗仍改值——规则优先级互相矛盾 |
| `clean.report_inconsistent` | medium | 手工报告与表计算的报告不一致——修报告，不改表 |
| `clean.spec_unreadable` | high | spec 不可读、不是对象、或无行可分析——exit 5 拒绝，不崩溃 |
| `clean.already_cleaned` | high | 同一输入已在此输出目录分析过——exit 4 拒绝二次叠加 |

## 异常处置表

| 情形 | 退出码 | 处置 |
|-|-|-|
| spec 文件缺失或不可读 | 5 | clean.spec_unreadable 拒绝；核对路径重跑 |
| spec 是合法 JSON 但不是对象（数组/字符串/数字） | 5 | 拒绝；包一层对象再跑 |
| rows 是字符串/数字而非列表 | 5 | 拒绝——绝不逐字符枚举 |
| rows 为空或没有记录对象 | 5 | 拒绝；先补数据 |
| table_path 指向的文件缺失 | 5 | 拒绝并说明来源（missing）；修路径 |
| 组内可用值 < 2 | 3（blocked 若在结论中） | stats.sample_too_small 系 high：补数据或放弃该比较 |
| 组内方差为零 | 3 | stats.zero_variance high；检查是否录入错误 |
| 某组缺失比例 > 50% | 3 | stats.missing_ratio_high medium；声明口径或补测 |
| 数据有 ≥3 组只比两组 | 3 | stats.groups_omitted medium；声明 excluded_groups 或 correction |
| ≥3 条两两比较未声明校正 | 3 | stats.multiple_comparison medium；声明 bonferroni 等 |
| 声称 p 与重算 p 判定相反 | 3 | stats.p_mismatch medium；对证检验来源，不许改措辞糊弄 |
| 小样本强偏度 | 3 | stats.assumption_normality medium；改非参数或核分布 |
| IQR 栅栏外异常值 | 3 | 列出保留；去留决策写进记录 |
| 单位无法换算 / 声明口径不明 | 3 | R04 拒绝命名缺口；target_unit/missing_tokens 声明口径 |
| 极长字符串 | 0/3 | 接受；消息截断，绝不崩溃 |
| 同一输入重复跑同一输出目录 | 4 | already_cleaned 拒绝；新一轮用新目录 |
| 手工 quality_report 与表算不符 | 3 | 修报告，不改表 |

## Limits

- **推断计算覆盖两族。** Welch 两样本 t 与单因素 ANOVA 由引擎直接计算；其余
  检验（配对、非参数、卡方）的 p 仍由上游给出，引擎把声明的 p 钉在措辞与重算
  描述统计上。检验族的选择建议来自形状提示（偏度/样本量），不是替你决定。
- **分布数学经锚点验证。** t/F 尾概率用不完全 beta 连分数实现，t=2.2281 df=10
  → 0.05 等锚点误差 ≤ 1e-6；但没有 Shapiro-Wilk / Levene——小样本形状提示是
  纯标准库下的诚实替代。
- **方向判定是词法级的。** 中英方向词表驱动；同时含两个方向词的句子按歧义跳过
  （不猜）。否定式方向（如"不再增加"）不在词表内，需要人复核。
- **数值引用按舍入容差匹配。** 引用值与计算值在 0.2% 或 0.006 绝对值内算一致。
- **CI 是均值差的区间。** 是"差值的 95% 置信区间"，不是个体取值范围，也不
  是效应量 d 的区间（后者需非中心 t，超出标准库诚实范围，明确不做）。
- **异常值检测池化全体数值。** 两组合并算栅栏；列可用值 < 8 时跳过（栅栏无意义）。
- **不补插。** 缺失是命名缺口；用均值填充 invent 数据。
- **run_manifest 无时间戳。** 同输入逐字节同 manifest；运行环境其余部分由平台记录。

## Failure handling

| 症状 | 处置 |
|-|-|
| `stats.direction_mismatch` | 改句子或改口径：重算均值在 finding 里，核对后重写结论 |
| `stats.significance_mismatch` | p 与措辞二选一改；不要靠换措辞把不显著写成显著 |
| `stats.p_mismatch` | 对证声称 p 的来源；若是上游检验口径不同，写明检验名再交付 |
| `stats.number_not_in_table` | 把引用数字换成 stats_audit.claims 里的重算值 |
| `stats.metric_unknown` / `stats.group_unknown` | 结论指向不存在的列或组——回数据字典改名，或补数据 |
| `stats.sample_too_small` / `stats.zero_variance` | 补数据或放弃该比较；不许硬算 |
| `stats.groups_omitted` | 声明 excluded_groups（哪些组被排除、为什么）或 correction |
| `stats.multiple_comparison` | 在 claims 上声明 correction；Bonferroni/Holm 由上游定 |
| `stats.missing_ratio_high` | 声明口径、补测，或把该组标注为不可比 |
| `stats.assumption_normality` | 改非参数检验，或先核分布再读参数 p |
| `stats.outliers_iqr` | 逐条决定去留并记录；不许静默删除 |
| `clean.spec_unreadable`（exit 5） | 读 findings；spec 不可读或没有行——修输入后重跑 |
| `clean.already_cleaned`（exit 4） | 换输出目录，或确认这是要拒绝的重复运行 |
| R04 拒绝（new 为 null） | 单位无法换算——命名单位，不静默丢行 |
| `clean.not_idempotent` | 规则优先级矛盾；先修规则再交付 |

方法细节（分布数学、Welch 选择、异常值栅栏、复现指纹）见 references/method-notes.md。

## 验证

```bash
python scripts/bench_stats.py   # 31 scenarios：每个植入一个缺陷或证明一个 FP guard
```

本机 31/31 pass（3.14）。clean 基线零 high/medium finding；重算记录与手算组均值
断言一致；分布数学对表锚点断言（t=2.2281 df=10 → 0.05、F=3.7083 (3,10) → 0.05、
t 分位数反解）。FP guard 钉住关键行为：p=0.30 配诚实措辞且重算 p 同向时保持安静、
三组表声明 excluded_groups 后安静、一位小数舍入引用不误报、真 0 不按缺失处理、
无 key_columns 时重复普查跳过。完整报告：report_stats.json。

## Requirements

Python 3.9+（3.14 实测）。纯标准库实现，无第三方依赖。

## 创新增益

本 Skill 相比通用 Agent 的核心新增能力（全部为引擎真实运行的机制，bench 覆盖）：

1. **纯标准库推断计算**：Welch t / 单因素 ANOVA 的 t、F、df、p 由不完全 beta 连分数直接计算（表锚点验证 1e-6），不依赖 scipy/statsmodels——通用 Agent 的 t 检验在无第三方环境不可复现，这里可以。
2. **效应量与区间绑定结论**：每条两组结论自动带 cohen_d、hedges_g 与均值差 95% CI——报告不再是裸 p 值，"统计显著≠实际意义"有数字可查。
3. **声称 p 的对证**：引擎重算的 p_computed 与声称 p 的显著性判定必须一致（stats.p_mismatch）——"p=0.04 被写成证明有效"有引擎侧对证，FP guard 证明重算同向时不误报。
4. **多重比较与组完整性审计**：≥3 条两两比较未声明校正、数据 ≥3 组只比两组，都是命名发现项；ANOVA（F/p/eta²）在多组时自动记录——"三组塞进两样本 t"被算术暴露。
5. **退化样本拒绝硬算**：样本量 <2、组内方差为零、缺失比例过半——全部 high/medium 发现而不是捏造统计量。
6. **Tukey 异常值列出保留**：1.5-IQR 栅栏（列 <8 个可用值时诚实跳过），异常值进待确认清单，去留由人。
7. **清洗幂等 + 逐条台账**：同规则二遍必须零改动；每处修改带 rule id/行/列/原值/新值/理由——可复核可撤销。
8. **契约直通的 result**：case_id 与 output_contract 全字段回填（直通/审计填写/null+limits），拒绝路径（exit 5）不带契约回显；run_manifest 让"换一台机器跑出同一组数字"有指纹可对。

## 生态贡献

1. **SKILL.md**：用途、适用条件、六步调用方式、路由表、逐字段 spec 说明、异常处置表、限制与自查方法齐备。
2. **scripts/**：纯标准库（Python 3.9+，3.14 实测），模块可独立导入；本包为独立副本，不依赖其他包的文件。
3. **examples/**：examples/example-spec.json（最小示例）与 examples/spec-contract.json（带契约回填的完整示例），示意输出标注为示例。
4. **bench_stats.py**：31 个场景，每条规则一个缺陷场景或修复孪生守卫，clean 基线零发现；report_stats.json 为可复跑证据。
5. **分布数学模块**：不完全 beta 连分数 + t/F 尾概率 + t 分位数反解，纯 stdlib 可直接迁移到其他无第三方依赖的统计任务。
6. **方法文档**：references/method-notes.md 说明每个统计决策的理由（为什么 Welch、为什么不用 Shapiro、锚点验证方法），他人可审计后复用。
7. **统计规范词汇**：direction/significance/citation/p_mismatch/groups_omitted 等稳定 rule id 与"声称 vs 重算"审计框架，可作为同类结果解读任务的共享词汇。
8. **可迁移的失败案例库**：bench 场景即误用案例库（方向抄反、p=0.30 写显著、三组塞两样本、零方差硬算、缺失过半硬比），可直接用于教学或评审清单。
