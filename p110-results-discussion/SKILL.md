---
name: results-discussion
description: >
  Audit a results section and a discussion section written from given data. Checks that text
  values appear in the figure data, that an error bar's meaning reaches the prose, that
  significance claims carry a test or p-value, that a non-significant comparison is not
  described as an effect, and that a declared sample size is traceable in the text. Refuses
  causal wording for observational, correlational, cross-sectional, retrospective or survey
  designs, requires proposed mechanisms to be hedged, requires negative results and
  conflicting literature to be reported in both sections, requires limitations to name a
  level of the study, and flags a number that appears in the discussion from nowhere. Use
  when a task asks for a results or discussion section.
---

# results-discussion（结果与讨论章节写作）

Two sections, two different disciplines, and the boundary between them is the point:

- **results** describe what was observed
- **discussion** interprets it, attributes it, and states what it cannot conclude

Mixing them is the most common failure, and it is checkable: causal language appearing in the
results section is reported.

## Rubric coverage map（评分点 → 规则）

| rubric 关注点 | rule ids |
|-|-|
| 读得准（图表数值/单位/误差棒/统计量正确读入正文） | `rd.value_not_in_figures`, `rd.errorbar_meaning_undeclared`, `rd.errorbar_meaning_absent_from_text`, `rd.unitless_number`, `rd.discussion_value_unsourced` |
| 分得清（结果段只写观察，讨论段承担解释） | `rd.interpretation_in_results`, `rd.mechanism_as_fact`, `rd.causal_overreach` |
| 说得住（趋势/差异/因果有检验支撑，语气与证据强度匹配） | `rd.statistic_missing`, `rd.comparison_no_verdict`, `rd.non_significant_claimed_as_effect`, `rd.overclaim` |
| 核得了（每个数值可回溯图表，每条论断对应文献） | `rd.discussion_uncited`, `rd.sample_size_absent` |
| 如实交代（阴性结果/不一致文献/局限） | `rd.negative_result_omitted`, `rd.negative_result_absent_from_results`, `rd.conflicting_literature_ignored`, `rd.limitations_missing`, `rd.limitation_vague`, `rd.limitation_level_narrow`, `rd.limitation_level_unknown` |
| 交付完整 | `rd.results_missing`, `rd.discussion_missing` |
| 输入可查 | `rd.declaration_malformed` |

## The failures this exists to catch

**A number the figure does not show.** The text says 9-fold, the figure data says 3. Values are
compared against `figures[].values`, with fold changes treated as measurements.

**A non-significant result written as an effect.** `{"name": "Arm B", "significant": false}` and
then "Arm B showed a higher response". The check reads only the sentence that names the
comparison.

**A negative result left out.** If a comparison did not reach significance and neither section
names it, the paper reports only what worked — the results section is checked separately from
the discussion.

**A mechanism stated as fact.** "The mechanism involves X" with no hedge. A proposal must read
as a proposal.

**A limitation that constrains nothing.** "Further work is needed" names no level of the study.
Limitations must reach method, sample, measurement or statistics — and at least two of them.

**Error bars with no readable meaning.** "Error bars are shown for every group" declares
nothing about SD, SEM or a CI.

**A number that appears from nowhere.** The discussion says 5-fold; the figure data and the
results text never carried it. Nobody can trace where it was read from.

## Runtime entry — from `/input/case.json` and `task.md` to `/app/output/result.json`

**Step 0 · Read the inputs.** Load `/input/case.json` (keep `case_id` and `output_contract`
verbatim; the data, figures and any draft prose are embedded or named by paths inside it) and
`/input/task.md` (which sections, which audience, which format). Read the actual data files —
never infer values from a label.

**Step 1 · 判形态选路由.** This challenge routes to `section: "results_discussion"`. Decide
from the task wording what the deliverable is (table below): draft both sections, audit an
existing draft, or repair named defects. If the case carries figures but the task says "results
only", record the missing discussion in `limits` — the audit still demands both sections.

**Step 2 · 先产出目标产物.** Write the results section and the discussion section first, into
`/app/work/deliverable.md` (editable prose, section headings included). Save the partial draft
early, then improve. Values, units, statistics and comparison names must come from the case's
data, not from invention.

**Step 3 · 构造 spec.** Assemble the audit spec (field table below): both texts, the declared
figure values, comparisons with verdicts, literature with agreement flags, limitations with
levels, and the case's `case_id` + `output_contract` carried over verbatim.

**Step 4 · 运行审计.**

```bash
python scripts/secrun.py --spec /app/work/spec.json --out /app/output
```

Exit codes: `0` clean, `3` review, `4` blocked, `5` undetermined (refused — bad JSON, missing
file, non-object spec, missing or unknown section; `result.json` is still written, never a
traceback).

**Step 5 · 修发现重跑.** Fix what the Failure-handling table names (use the figure's value,
state the error-bar meaning, name the test, move the interpretation to the discussion), then
re-run until the status is acceptable or the remaining findings are recorded as honest limits.

**Step 6 · 合并 result.json.** The script's `result.json` already echoes `case_id` and every
`output_contract` field and carries the rubric's three-part structure. Move it to
`/app/output/result.json` beside the deliverable; fill any null contract field by hand when the
audit cannot derive it — never silently.

## 任务措辞 → 路由决策表

| task.md wording | route | why |
|-|-|-|
| "根据数据撰写结果与讨论章节" | draft both texts, then audit | the deliverable is both sections |
| "只写结果段" | still declare `discussion_text` (or record the gap in `limits`) | the audit treats half a deliverable as missing |
| "检查我写的结果/讨论段" | audit as-is, findings drive revision | the engine is an audit, not a rewriter |
| "图 X 的数值要写进正文" | declare `figures[].values` exactly as the figure shows | value matching runs against the declared list |
| "误差棒要说明含义" | declare `has_errorbar` + `errorbar: SD/SEM/CI` and state it in prose | two rules check declaration and prose |
| "结果和讨论不要混" | `interpretation_in_results` / causal checks police the boundary | mechanical, sentence-level |
| "观察性/问卷调查数据" | `design: observational / cross-sectional / survey / ...` | causal language is refused for those designs |
| "阴性结果也要写" | declare non-significant comparisons with `significant: false` | omission is checked in BOTH sections |
| "每个论断都要可追溯" | cite `[key]` per claim or point at this study's data | `discussion_uncited` + `discussion_value_unsourced` |
| "局限要具体" | `limitations[].level` ∈ method/sample/measurement/statistics | vague limitations and single-level accounts are reported |
| "统计口径写清楚（n 多少）" | declare `comparisons[].n` | `sample_size_absent` checks the prose carries it |
| task names another writing section (evidence, translation, format) | use the section the case declares; this doc covers `results_discussion` | the engine routes by `spec 的 section 字段` |

## Spec fields（构造 spec 的完整字段表）

| field | type | required | meaning |
|-|-|-|-|
| `case_id` | str | yes (carry through) | input identifier, echoed into result.json |
| `output_contract` | obj | yes (carry through) | every named field is echoed into result.json |
| `section` | str | yes | `results_discussion` |
| `design` | str | recommended | `experimental` / `observational` / `correlational` / `cross-sectional` / `retrospective` / `survey`; absent design = causal check skipped and named in boundary |
| `results_text` | str | yes | the results section prose |
| `discussion_text` | str | yes | the discussion section prose |
| `figures[]` | list | recommended | `{id, values: ["3", "three-fold", "0.01"], has_errorbar, errorbar}` |
| `comparisons[]` | list | recommended | `{name, significant, strength, n}` |
| `literature[]` | list | when discussion cites | `{key, agrees, finding}` |
| `limitations[]` | list | yes | `{level, text}` with level ∈ method/sample/measurement/statistics |
| `require_errorbar_in_text` | bool | optional | declarative opt-in: demand the error-bar meaning in the prose |
| `limits[]` | list | recommended | honest gaps (missing figures, data the audit could not read) |

## Worked example（示例，非正式案例结果）

Spec — assembled from a case whose task says "把图 1 的数据写成结果段和讨论段，统计口径写清楚"
(`case_id` and `output_contract` come from `/input/case.json` verbatim):

```json
{
  "case_id": "case-rd-demo-01",
  "output_contract": {"status": "…", "section_word_counts": "…", "trace_ledger": "…"},
  "section": "results_discussion",
  "design": "experimental",
  "results_text": "Uptake rose three-fold in the coated group (p < 0.01, t-test, n = 12). Arm B showed no change (n = 10). Error bars show SD.",
  "discussion_text": "The coated samples showed higher uptake, consistent with earlier work [doe2020]. The mechanism may involve increased surface area [doe2020]. Arm B did not reach significance. Roe reports a conflicting result [roe2021].",
  "figures": [{"id": "Fig 1", "values": ["3", "three-fold", "0.01"],
               "has_errorbar": true, "errorbar": "SD"}],
  "comparisons": [{"name": "coated vs control", "significant": true, "strength": "strong", "n": 12},
                  {"name": "Arm B", "significant": false, "n": 10}],
  "literature": [{"key": "doe2020", "agrees": true},
                 {"key": "roe2021", "agrees": false, "finding": "no effect at low dose"}],
  "limitations": [{"level": "sample", "text": "single material system tested"},
                  {"level": "measurement", "text": "one coating thickness measured"}]
}
```

```bash
python scripts/secrun.py --spec /app/work/spec.json --out /app/output   # exit 0
```

Illustrative result.json (示例示意，字段以实际运行为准):

```json
{
  "schema_version": "secrun/v1",
  "case_id": "case-rd-demo-01",
  "section": "results_discussion",
  "status": "clean",
  "severity_counts": {},
  "findings": [],
  "checked": {"section": "results_discussion", "items": 0, "figures": 1, "comparisons": 2,
              "literature": 2, "limitations": 2, "results_words": 24, "discussion_words": 31},
  "deliverable": {"kind": "results_and_discussion", "results_text": "…",
                  "discussion_text": "…", "results_words": 24, "discussion_words": 31},
  "evidence_map": [
    {"kind": "statistic", "value": 0.01, "verdict": "exempt"},
    {"kind": "statistic", "value": 12.0, "verdict": "exempt"},
    {"kind": "comparison", "name": "coated vs control", "significant": true, "strength": "strong"},
    {"kind": "literature", "key": "roe2021", "agrees": false, "addressed": true},
    {"kind": "limitation", "level": "sample", "vague": false}
  ],
  "boundary": {"human_review_and_gaps": [], "declared_limits": []},
  "limits": ["output_contract field 'section_word_counts' was not derivable by this audit"],
  "status_note": "示例：n=12/n=10 是样本量口径，evidence_map 中按统计量 exempt 处理；output_contract 中 null 字段需人工补齐后提交"
}
```

## result.json 与 rubric 输出要求的三段结构映射

| rubric 要求（原词） | result.json 字段 | 完成标准如何满足 |
|-|-|-|
| 目标产物（可编辑、可提交的结果段与讨论段） | `deliverable`（results_text + discussion_text 全文与词数） | 两段正文随结果交付，可直接继续编辑 |
| 事实与来源映射（数值/统计量/比较/文献/局限的来源与核对记录，可独立复核） | `evidence_map[]`（value/statistic/comparison/literature/limitation，每条带 verdict） | 每个数值标 in_figures / unmatched / exempt；每条文献标 addressed |
| 版本与边界（修改差异、人工确认项、材料缺口和异常） | `boundary`（human_review_and_gaps、declared_limits）+ `findings[]` + `limits[]` | 无显著性判决的比较、误差棒含义未声明、design 未识别等显式列为待确认 |
| 输入标识 + 运行状态 + 不确定性 | `case_id` + `status` + `severity_counts` | grader 能定位输入、判断运行状态与不确定性 |

## Rules

### Sections, values, figures

| rule | severity | what it proves |
|-|-|-|
| `rd.results_missing` / `rd.discussion_missing` | high | half the deliverable absent |
| `rd.value_not_in_figures` | high | prose and figure disagree |
| `rd.errorbar_meaning_undeclared` | high | bars with no stated meaning (declaration side) |
| `rd.errorbar_meaning_absent_from_text` | medium | bars mentioned without a meaning in the prose, or prose silent when the case requires the meaning in text |
| `rd.unitless_number` | medium | a number with no unit |
| `rd.discussion_value_unsourced` | medium | a discussion number traceable to nothing |
| `rd.declaration_malformed` | medium | a declared field is not a list, so its entries cannot be checked |

### Statistics

| rule | severity | what it proves |
|-|-|-|
| `rd.statistic_missing` | high | significance claimed without a test or p-value |
| `rd.comparison_no_verdict` | high | a comparison with no significance verdict |
| `rd.non_significant_claimed_as_effect` | high | a null result described as an increase or decrease |
| `rd.overclaim` | medium | absolute wording with no strength label |
| `rd.sample_size_absent` | medium | a declared n that the text never carries |

### Description vs interpretation

| rule | severity | what it proves |
|-|-|-|
| `rd.interpretation_in_results` | high | causal or interpretive language in the results |
| `rd.mechanism_as_fact` | high | a mechanism proposed without a hedge |
| `rd.causal_overreach` | high | causal wording for an observational / correlational / cross-sectional / retrospective / survey design |
| `rd.discussion_uncited` | high | a discussion claim with no data or reference |

### Honesty about the whole result

| rule | severity | what it proves |
|-|-|-|
| `rd.negative_result_omitted` | high | a non-significant comparison never mentioned in the discussion |
| `rd.negative_result_absent_from_results` | medium | a null comparison never named in the results section |
| `rd.conflicting_literature_ignored` | high | a contradicting source never addressed |
| `rd.limitations_missing` | high | no limitation at all |
| `rd.limitation_vague` | medium | a limitation that names nothing |
| `rd.limitation_level_narrow` | medium | limitations confined to one level |
| `rd.limitation_level_unknown` | low | a level outside the four |

## Limits

- **Statistics are exempt from the number checks.** A p-value, a test statistic with df, n,
  R², or CI bounds carries no unit by convention and is not a plotted value; the audit does
  not flag them as unitless and does not require them in the figure data. Reporting correct
  statistics is never a reason to rewrite them.
- **A discussion sentence that points at this study's data counts as attributed.** "Consistent
  with the dose dependence in Fig. 3" needs no reference key. Only assertions with neither a
  citation, a placeholder, nor a figure/table/study reference are flagged.
- **"The results in Table 1" is a pointer, not causal language.** The causal check matches
  causes/leads to/due to/because/therefore — not "results in" or "demonstrates", which are
  standard descriptive results prose.
- **Value matching is per-number against the declared figure values.** A derived value
  computed from the figure (a ratio, a difference) will be reported as absent; declare it in
  `values`. A declared sample size `n` is a caliber, not a plotted value: it is checked for
  presence in the prose (`sample_size_absent`), not against the figure data.
- **Non-significance detection reads the naming sentence only.** A null result described in a
  later sentence without repeating the comparison name will pass.
- **The hedge check is document-level for mechanisms**: one hedge anywhere in the discussion
  satisfies it.
- **The error-bar prose check is narrow.** It fires when the text mentions the bars without a
  meaning, or when the case declares `require_errorbar_in_text`; a section that leaves the
  meaning to the caption is not punished unless the case says otherwise.
- **`sample_size_absent` uses integer containment.** "n = 12" anywhere in the text satisfies
  it; "12" inside "120" also satisfies it. A heuristic, stated as such.
- **Limitation levels are declared.** The audit does not judge whether the stated limitation
  is the honest one.
- **No statistical recomputation.** It checks that a test is named, not that it was the right
  test.

## Failure handling（修发现 → 重跑）

| symptom | what to do |
|-|-|
| `rd.value_not_in_figures` | use the figure's value. Statistics (p-values, test statistics, n, R², CI bounds) are exempt — never delete them from the text and never add them to the figure data to silence this rule |
| `rd.errorbar_meaning_undeclared` | state SD / SEM / CI in the figure record |
| `rd.errorbar_meaning_absent_from_text` | write the meaning into the prose ("error bars show SD") |
| `rd.statistic_missing` | name the test and the p-value |
| `rd.non_significant_claimed_as_effect` | say "no significant difference" and stop there |
| `rd.sample_size_absent` | carry the declared n into the prose ("n = 12") |
| `rd.discussion_value_unsourced` | trace the number to a figure/result, or delete it |
| `rd.interpretation_in_results` | move the interpretation to the discussion |
| `rd.mechanism_as_fact` | mark it as a proposal |
| `rd.causal_overreach` | use association language for non-experimental designs |
| `rd.negative_result_omitted` | report the comparison that did not work — in the discussion |
| `rd.negative_result_absent_from_results` | name the null comparison in the results section too |
| `rd.conflicting_literature_ignored` | address the contradicting source |
| `rd.limitation_vague` | name the level: method, sample, measurement, statistics |
| `rd.declaration_malformed` | fix the spec field's shape (send a list, not a string/number) |
| `audit.no_section` (exit 5) | the case could not be run as declared: no or unknown section, unreadable JSON, non-object spec — refused, never a crash |

## 异常处置表（运行异常 → 处置）

| exception | behaviour | where it shows |
|-|-|
| spec is not valid JSON | exit 5, `result.json` written with `audit.no_section`, message quotes the decode error | no traceback, ever |
| spec is not an object (list/string/number) | exit 5 refusal: "the spec file is not a JSON object" | `result.json` |
| spec file missing / unreadable | exit 5 refusal with the OS error text | `result.json` |
| no `section` declared | exit 5 refusal: "no section declared, so no rules apply" | `result.json` |
| unknown `section` (typo, wrong track) | exit 5 refusal naming the unknown value; valid sections are listed in `sections.py::SECTIONS` | `result.json` |
| empty texts (both sections empty) | `rd.results_missing` + `rd.discussion_missing` high; audit proceeds to the data checks | findings |
| fields of the wrong type (figures as string, comparisons as number) | `rd.declaration_malformed` medium naming the field and the type found | findings |
| null / non-object list entries | degraded silently by `_records`; the object entries still checked | findings only from object entries |
| 缺图（no figures declared） | value matching skipped, gap named in `checked.figures = 0` | checked + limits |
| 缺统计量 | `rd.statistic_missing` / `rd.comparison_no_verdict` high | findings |
| 单位不明 | `rd.unitless_number` medium | findings |
| 引用找不到（cite key not in literature） | `rd.discussion_uncited` unless the sentence points at this study's data | findings |
| 图表读数不清（error bars without meaning） | `rd.errorbar_meaning_undeclared` / `..._absent_from_text` | findings |
| design 未识别 | causal-overreach check skipped; the gap is named in `boundary` | boundary |
| 超长文本 | single-pass regex work, no model calls; 20k-word drafts audit in ~1.5 s | status unaffected |
| 依赖缺失 | pure Python 3.9+ standard library; no third-party packages; if `python` itself is absent, report that honestly in `limits` instead of fabricating an audit | limits |
| contract field not derivable | field set to `null` plus a limit note; fill by hand before submitting | `limits` |

## Requirements

Python 3.9+（3.14 实测）。纯标准库实现，无第三方依赖。

## 创新增益（真实能力，bench 可复跑验证）

1. **结果段/讨论段边界的机械检查**：因果词、机制名词、模糊限制语按句定位，结果段的
   解释、观察设计下的因果越界、未加对冲的机制全部逐句报告——通用 Agent 无法对自己证明
   "结果段没有夹带解释"。
2. **数值三级回溯账**：正文数值逐个分类为 in_figures / unmatched / exempt（统计口径），
   讨论段数字单独查来源，声明的 n 单独查口径落文——每个数字都能被第三方独立复核。
3. **阴性结果双段覆盖**：未达显著性的比较在结果段与讨论段分别检查缺席，"只报有效的"
   这一最常见的写作不诚实无处藏身。
4. **诚实边界**：无显著性判决的比较、含义未声明的误差棒、未识别的 design、畸形声明全部
   显式列为待确认或异常，而不是静默跳过。

bench 目录下的 rd 套件（32 场景，每条规则至少一个 planted-defect 场景 + FP 守卫）与
sections 套件（51 场景，跨 section 回归）是上述能力的回归证据。

## 生态贡献

- **使用说明**：SKILL.md 从 `/input/case.json` + `task.md` 到 `/app/output/result.json`
  全流程六步、路由决策表 12 行、字段表、worked example（标注"示例"）。
- **依赖**：纯 Python 标准库，3.9+（3.14 实测），无第三方包、无网络、无模型调用。
- **配置**：声明式触发——figures/comparisons/literature/limitations/design/
  require_errorbar_in_text 均按声明生效，未声明不惩罚；spec 字段表即配置说明。
- **示例标注**：examples/spec.json 为最小调用示例（含 case_id/output_contract），
  examples/bench-report.json 为 bench 实跑报告快照，examples/limitations-checklist.json
  为四层局限检查清单模板（levels/examples/anti_patterns 可直接改用）；SKILL.md 内 result.json 标注"示例
  示意，字段以实际运行为准"，不冒充正式案例结果。
- **资源复用**：examples/limitations-checklist.json 局限模板可直接改用；`sections.py` 的 `_stat_values`（统计口径豁免）、`_DATA_REF`（自引数据
  归因）与 CAUSAL_WORDS、MECHANISM、HEDGE、VAGUE_LIMIT 四组内嵌词表可独立复用；bench_rd.py 与
  bench_sections.py 可独立复跑。
- **适用范围**：由数据/图表撰写与审计结果段+讨论段（英或中），实验/观察/横断面/回顾/
  问卷调查设计均覆盖；其他 section 由同引擎按 `spec 的 section 字段` 路由。
- **限制**：见 Limits——统计不重算、机制对冲是文档级、误差棒正文检查为窄触发、
  n 匹配为整数包含启发式。
- **维护**：规则与场景一一对应（新增规则必须带 bench 场景 + clean 守卫）；改脚本后必须
  重跑 `bench_rd.py`（32）与 `bench_sections.py`（51）并保持全过。

## Verification

```bash
python scripts/bench_rd.py        # 32 scenarios: one per rule
python scripts/bench_sections.py  # 51 scenarios: cross-section regression plus false-positive guards
```

Both pass in full on this machine. The clean baseline in each must report nothing.
