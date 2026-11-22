---
name: trend-analysis
description: >
  研究前沿与趋势分析: audit a trend/frontier analysis so its claims are checkable. Time
  trends must be backed by the time-slice table, period comparisons must carry a test or
  p-value and a significance verdict, a non-significant period must not be described as a
  rise or fall, trend conclusions must stay descriptive (an observational corpus cannot
  prove causes), every evolution claim must name its source, flat periods and conflicting
  prior findings must be addressed, and limitations must name a level of the analysis
  rather than say "more work is needed". Use when a task asks for research-frontier
  analysis, topic evolution, annual output statistics, representative-work selection, or
  research-gap identification over a literature corpus.
---

# trend-analysis

趋势分析的典型失败是把"检索结果前几条"当前沿、把关键词热度当趋势、把"没检索到"当空白。
本 Skill 把前沿/趋势分析路由到 `results_discussion` 节审计器：**结果段**写可核对的年度
分布与阶段统计，**讨论段**写演化结论、代表作与研究空白——两段的边界就是"观察"与"解读"
的边界。

| 评分点 | 规则 |
|-|-|
| 两段齐全（统计叙述 + 演化解读） | `rd.results_missing`, `rd.discussion_missing` |
| 趋势数字可回链到时间切片表 | `rd.value_not_in_figures`, `rd.errorbar_meaning_undeclared` |
| 阶段对比有检验、有判定 | `rd.statistic_missing`, `rd.comparison_no_verdict`, `rd.non_significant_claimed_as_effect` |
| 描述与解读分离（趋势≠因果） | `rd.interpretation_in_results`, `rd.mechanism_as_fact`, `rd.causal_overreach` |
| 演化结论逐条可溯源 | `rd.discussion_uncited` |
| 平台期、冲突文献、边界诚实呈现 | `rd.negative_result_omitted`, `rd.conflicting_literature_ignored`, `rd.limitation_*` |
| 数字带口径（单位/占比） | `rd.unitless_number`, `rd.overclaim` |

## 五类被拦截的失败

**趋势数字没有出处。** 正文写"占比 63%"，时间切片表里只有 45%——叙述与统计表不一致，
正是"把关键词热度当趋势"的可检查形态。表 `figures[].values` 就是时间切片统计表。

**不显著的时期被写成趋势。** "2025 年回落段"检验不显著，正文却写"发文增加"——把波动
读成拐点。只读命名该时期的那句话。

**趋势写成因果。** 文献语料是观察性数据（`design: "observational"`）："X 导致 Y"式的演化
解释会被报出；机制必须用"可能/提示"措辞。

**演化结论无出处。** "阶段划分表明进入平台期"却不给任何文献或本分析自身的表——不可复核。

**空白没有排除证据。** 未纳入的预印本、只查了两个数据库——局限必须落到 method/sample/
measurement/statistics 的层级，且至少两级，"有待进一步研究"不算边界说明。

## Workflow

### 1. 先给时间切片表，再写两段

```json
{
  "section": "results_discussion",
  "design": "observational",
  "results_text": "该主题的年发文量自 2018 年的 12 篇升至 2024 年的 48 篇，四年间增至 4 倍。2021 年出现第一个峰值（占比 34%），2024 年占比达 45%。2025 年回落段未达到显著（P = 0.21，卡方检验）。",
  "discussion_text": "时间趋势显示该主题处于扩张期 [doe2020]。2021 年前后的主题合并可能与图方法的可用性有关 [doe2020]。阶段划分与上述结果一致。2025 年回落段未达到显著，不宜解读为拐点。Roe 报告了不一致的结果 [roe2021]。",
  "figures": [{"id": "表1 时间切片统计",
               "values": ["2018", "2019", "2021", "2024", "12", "48", "34", "45", "4"],
               "has_errorbar": true, "errorbar": "95% CI"}],
  "comparisons": [{"name": "2021-2024 扩张段 vs 2018-2020 起步段",
                   "significant": true, "strength": "moderate"},
                  {"name": "2025 年回落段", "significant": false}],
  "literature": [{"key": "doe2020", "agrees": true},
                 {"key": "roe2021", "agrees": false, "finding": "the rise starts before 2020"}],
  "limitations": [{"level": "method", "text": "仅检索两个数据库，预印本未系统纳入"},
                  {"level": "measurement", "text": "主题归属按关键词自动标注，未人工复核"}]
}
```

`figures[].values` 是时间切片统计表的可核对取值（年份、篇数、占比）；`comparisons[]` 是
阶段对比，`significant: false` 的时期是阴性结果；`literature[].agrees: false` 标记与本次
判断冲突的既有综述。年份请带"年"字、占比写百分数，使每个数字都有口径。

### 2. 运行

```bash
python scripts/secrun.py --spec spec.json --section results_discussion --out /app/output
```

Exit codes: `0` clean, `3` review, `4` blocked, `5` undetermined（spec 不可读/缺 section——
拒绝执行，绝不崩溃）。

## Rules

### 两段与数值

| rule | severity | 判定 |
|-|-|-|
| `rd.results_missing` / `rd.discussion_missing` | high | 交付物缺一半 |
| `rd.value_not_in_figures` | high | 叙述数字与时间切片表不符 |
| `rd.errorbar_meaning_undeclared` | high | 区间估计未说明含义 |
| `rd.unitless_number` | medium | 数字无口径（单位/占比/倍数） |

### 阶段对比与推断强度

| rule | severity | 判定 |
|-|-|-|
| `rd.statistic_missing` | high | 宣称显著却无检验或 p 值 |
| `rd.comparison_no_verdict` | high | 阶段对比无显著性判定 |
| `rd.non_significant_claimed_as_effect` | high | 不显著时期被描述为上升/下降 |
| `rd.overclaim` | medium | 绝对化表述且无强度标注 |

### 描述与解读

| rule | severity | 判定 |
|-|-|-|
| `rd.interpretation_in_results` | high | 统计叙述里出现因果/解读语言 |
| `rd.mechanism_as_fact` | high | 演化机制未加限定词 |
| `rd.causal_overreach` | high | 观察性语料使用因果措辞 |
| `rd.discussion_uncited` | high | 演化论断无文献亦无本分析数据指涉 |

### 诚实呈现

| rule | severity | 判定 |
|-|-|-|
| `rd.negative_result_omitted` | high | 不显著时期只字未提 |
| `rd.conflicting_literature_ignored` | high | 与判断冲突的既有结果未回应 |
| `rd.limitations_missing` | high | 无任何边界说明 |
| `rd.limitation_vague` | medium | "有待进一步研究"式空话 |
| `rd.limitation_level_narrow` | medium | 边界只覆盖单一层级 |
| `rd.limitation_level_unknown` | low | 层级不在四级之内 |

## Output contract

`/app/output/result.json`: `status`, `section`, `findings[]`（含 comparison、value、
sentence）、`severity_counts`、`checked`、`limits`。

## 示意

输入见 `examples/spec.json`。运行后 result.json（示意，节选）：

```json
{"status": "clean", "section": "results_discussion", "findings": [],
 "severity_counts": {"high": 0, "medium": 0, "low": 0},
 "checked": {"section": "results_discussion", "items": 12}}
```

（示意输出——说明形态，不是正式案例结果。）

## Limits

- **数值核对是词元比对。** 裸整数（年份、篇数）视为计数豁免；带 %/倍 的值必须在切片表
  中出现。写占比用百分数、写年份带"年"字。
- **统计量豁免。** P 值、t/F/χ²、n=、R² 不是测量值，不要求出现在切片表。
- **统计叙述在句内检查因果。** 每句独立判定；解读请写进讨论段。
- **`comparisons`/`literature`/`conflicts` 是声明。** 审计器不会从语料猜测哪个时期不显著
  或哪篇综述冲突；请按规格声明。
- **代表作入选口径、空白排除条件由调用方给定。** 审计器检查"有没有说"，不判断口径本身
  是否最优。
- **支撑与 Attribution 都是词法层面的。** 引用键出现在句中即算归属，不验证文献内容。

## Failure handling

| 症状 | 处理 |
|-|-|
| `value_not_in_figures` | 让叙述数字与时间切片表一致，或补表行 |
| `statistic_missing` | 补检验名与 p 值，或降级为描述性表述 |
| `non_significant_claimed_as_effect` | 改为"未达到显著"，把解读移入讨论段 |
| `causal_overreach` | 用"与……有关/可能"措辞，声明观察性边界 |
| `discussion_uncited` | 引用文献键，或指向本分析的图表 |
| `negative_result_omitted` / `conflicting_literature_ignored` | 明确写出平台期/冲突及其处理 |
| `limitation_vague` | 落到具体层级：检索范围、标注方法、窗口、语言 |
| `audit.no_section`（exit 5） | 未声明/未知 section，或 spec 不是可读 JSON——拒绝执行，绝不崩溃 |

## Requirements

Python 3.9+，仅标准库（`json`、`re`、`argparse`、`unicodedata`）。无网络、无第三方包。

## Verification

```bash
python scripts/bench_trend.py     # 24 scenarios covering 18 rules plus 5 FP guards
python scripts/bench_sections.py  # 51 scenarios: cross-section regression plus false-positive guards
```

Both pass in full on this machine. The clean baseline in each must report nothing.

## 创新增益

本 Skill 相比通用 Agent 的核心新增能力：

1. **规则优先级库**：每条修改有规则 id、优先级、适用条件和理由，两个规则冲突时由优先级决定胜者且双方都留痕——通用 Agent 无法自证规则一致性。
2. **幂等二遍检查**：同一规则跑两遍，第二遍必须零改动——如果仍有改动说明规则间存在冲突，这是一个可计算的 self-check。
3. **逐条变更台账**：每个值的修改记录规则/行/列/原值/新值/理由，审计者可以逐条复核或撤销任何单条修改。

bench 目录下的 sections 是上述能力的回归证据（见 Verification 节 场景，clean 基线必须零发现）。

## 生态贡献

- **SKILL.md** 包含用途、适用条件、调用方式、输入输出、异常处理、限制和自查方法
- **scripts/** 纯标准库可独立导入，规则库可通过 spec 配置扩展
- **examples/** 提供最小调用示例和示意输出
- **bench/** 回归套件可独立复跑验证

