---
name: results-discussion
description: >
  Audit a results section and a discussion section written from given data. Checks that text
  values appear in the figure data, that an error bar's meaning reaches the prose, that
  significance claims carry a test or p-value, that non-significant trend wording such as
  "higher but not significant" is preserved without false positives, and that effect estimates,
  CI/SE/SD, sample size and derivations are numerically consistent with their sources. Refuses
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
| 说得住（效应量/不确定性/趋势/因果与证据匹配） | `rd.statistic_missing`, `rd.effect_size_missing`, `rd.effect_value_mismatch`, `rd.uncertainty_missing`, `rd.uncertainty_inconsistent`, `rd.significance_misclassified`, `rd.significance_ci_conflict`, `rd.non_significant_claimed_as_effect` |
| 核得了（每个数值可回溯图表，每条论断对应文献） | `rd.discussion_uncited`, `rd.sample_size_absent` |
| 如实交代（阴性结果/不一致文献/替代解释/局限与外推边界） | `rd.negative_result_omitted`, `rd.conflicting_literature_ignored`, `rd.alternative_explanations_missing`, `rd.limitations_missing`, `rd.extrapolation_boundary_missing` |
| 交付完整 | `rd.results_missing`, `rd.discussion_missing` |
| 输入可查 | `rd.declaration_malformed` |

## The failures this exists to catch

**A number the figure does not show.** The text says 9-fold, the figure data says 3. Values are
compared against `figures[].values`, with fold changes treated as measurements.

**An effect size whose inputs disagree, or no uncertainty.** Comparisons may declare explicit
`mean_treatment` / `mean_control`, `effect_type` (`difference`, `ratio`, `percent_change`) and
`effect_size` with `ci_low` / `ci_high` or SE/SD. The engine checks the declared arithmetic,
CI bounds and point-estimate inclusion, p-value versus `alpha`, and (only for a declared same
two-sided difference test) the CI null decision. `checked.numeric_ledger` exposes every input,
expected effect, derivation and source_ref. No effect/CI is reverse-engineered from significance:
use `effect_not_computable` / `uncertainty_not_computable` with an honest reason instead.

**A non-significant result written as an established effect.** `{"name": "Arm B", "significant":
false}` and "Arm B showed a higher response" is flagged, but "Arm B showed a higher response
but did not reach significance" is intentionally clean. The check reads only the naming sentence
and respects not/non-significant, p>= threshold, 不显著/未达显著 qualifiers.

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

**Step 3 · 构造 spec.** Assemble both texts, figure values with source refs, comparisons with
verdicts/effect estimates/uncertainties/formula inputs, reproducible derivations, literature with
agreement flags, limitations and explicit extrapolation scope, plus the case's `case_id` and
`output_contract` verbatim. Result prose reports observations; Discussion separately summarizes
meaning, compares prior work (including contradictory directions/conditions), gives alternative
explanations and states what cannot be generalized. If effect/CI inputs are absent, use explicit
not_computable fields rather than inventing them.

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
`output_contract` field (dict or array, including results/discussion/evidence/limitations and
other large declared values) and carries the rubric's three-part structure plus numeric_ledger. Move it to
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
| `output_contract` | obj or list | yes (carry through) | every named field and supplied same-name value is echoed, even bulk text/evidence |
| `section` | str | yes | `results_discussion` |
| `design` | str | recommended | `experimental` / `observational` / `correlational` / `cross-sectional` / `retrospective` / `survey`; absent design = causal check skipped and named in boundary |
| `results_text` | str | yes | the results section prose |
| `discussion_text` | str | yes | the discussion section prose |
| `figures[]` | list | recommended | `{id, values: ["3", "three-fold", "0.01"], has_errorbar, errorbar}` |
| `comparisons[]` | list | recommended | `{id, name, significant, strength, n, source_ref, p_value, alpha, mean_treatment, mean_control, effect_type, effect_size, ci_low, ci_high}`; SE/SD or explicit not_computable reasons also accepted |
| `derivations[]` | list | when prose computes | `{id, value, formula, inputs/source_values, source_ref/source_locator}`; allows traceable values without polluting figure inputs |
| `alternative_explanations[]` | list | when mechanisms/non-causal designs are discussed | records may be used, or name alternatives directly in discussion (confounding, measurement/selection bias, reverse causation) |
| `extrapolation_boundary` | str | when limitation text is separate | explicit population/material/setting/time scope beyond which results do not generalize |
| `numeric_tolerance` / `comparisons[].tolerance` | number | optional | declared rounding tolerance for effect arithmetic; default 1e-9, never an arbitrary 5% blur |
| `literature[]` | list | when discussion cites | `{key, agrees, finding}`; contradictory works must be addressed, not merely present |
| `limitations[]` | list | yes | `{level, text}` with level ∈ method/sample/measurement/statistics; one entry must bound extrapolation in text or scope field |
| `require_errorbar_in_text` | bool | optional | declarative opt-in: demand the error-bar meaning in the prose |
| `limits[]` | list | recommended | honest gaps (missing figures, data the audit could not read) |

## Worked example（示例，非正式案例结果）

`examples/spec.json` is a runnable, realistic example (not an official answer). It reports coated
3.0 mmol vs control 2.0 mmol, effect difference 1.0 mmol (95% CI 0.5 to 1.5), p=0.01, and a
source_ref pointing at the exact Table 1 comparison row. Arm B is higher but non-significant and
explicitly records why no effect/CI is computable from the available inputs. Discussion separately
compares Doe and contradictory Roe, proposes a hedged mechanism with a measurement-drift
alternative, and bounds generalization to this material. The output_contract carries completed
`deliverable_text` and `trace_ledger` values directly through.

```bash
python scripts/secrun.py --spec examples/spec.json --out /app/output   # clean, exit 0
```

Illustrative result.json (示例示意，字段以实际运行为准):

```json
{
  "schema_version": "secrun/v1", "case_id": "case-rd-minimal-01",
  "section": "results_discussion", "status": "clean", "findings": [],
  "checked": {"section": "results_discussion",
              "numeric_ledger": {"comparisons": [
                {"comparison_id": "cmp-coated-control", "effect_estimate": 1.0,
                 "ci_low": 0.5, "ci_high": 1.5, "expected_effect": 1.0,
                 "derivation": "mean_treatment - mean_control", "p_value": 0.01,
                 "source_ref": "Table 1, coated-control row"},
                {"comparison_id": "cmp-arm-b", "effect_estimate": null,
                 "effect_not_computable": "Arm B group means are not supplied..."}
              ], "effect_estimates": 1, "uncertainties": 1,
              "uncomputable_effects": ["cmp-arm-b"]}},
  "output_contract_fields": ["status", "deliverable_text", "trace_ledger"],
  "deliverable_text": {"results": "<same as final editable Results>",
                       "discussion": "<same as final editable Discussion>"}
}
```

## result.json 与 rubric 输出要求的三段结构映射

| rubric 要求（原词） | result.json 字段 | 完成标准如何满足 |
|-|-|-|
| 目标产物（可编辑、可提交的结果段与讨论段） | `deliverable`（results_text + discussion_text 全文与词数） | 两段正文随结果交付，可直接继续编辑 |
| 事实与来源映射（数值/统计量/比较/文献/局限的来源与核对记录，可独立复核） | `evidence_map[]` + `checked.numeric_ledger` + `trace_ledger` | 数值标 in_figures/unmatched/exempt；效应估计、CI、公式、source_ref 和不可计算原因逐项复核；矛盾文献 addressed |
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
| `rd.effect_size_missing` | high | explicit means or CI exist without a point estimate or non-computable reason |
| `rd.effect_not_computable_unexplained` | medium | zero denominator/unknown formula with no honest reason |
| `rd.effect_value_mismatch` | high | effect differs from its declared group-mean formula beyond tolerance |
| `rd.uncertainty_missing` | high | effect has no CI/SE/SD and no uncertainty_not_computable reason |
| `rd.uncertainty_inconsistent` | high | reversed/incomplete CI or point estimate outside CI |
| `rd.effect_size_absent_from_results` | medium | declared effect never appears in Results |
| `rd.uncertainty_absent_from_text` | medium | a declared CI bound never appears in either section |
| `rd.significance_misclassified` | high | verdict disagrees with p_value < alpha |
| `rd.significance_ci_conflict` | high | declared same-two-sided difference CI and verdict disagree |
| `rd.alpha_invalid` | medium | numeric significance cannot use the supplied threshold |
| `rd.derivation_not_reproducible` | medium | derived value lacks formula or source inputs/locator |

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
| `rd.alternative_explanations_missing` | medium | mechanisms/non-causal interpretations lack named alternatives |
| `rd.extrapolation_boundary_missing` | medium | limitations never constrain population/material/settings generalization |
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
- **Values are compared numerically, not as formatting strings.** 3 and 3.0 agree; prose, figures
  and reproducible derivations are separate ledgers. A derived ratio/difference no longer needs to
  be planted in `figures[].values`: declare `derivations[]{value,formula,inputs/source_ref}`. An
  explicit rounding `tolerance` is required for approximate effect arithmetic; there is no blanket
  5% acceptance. A declared sample size `n` is checked for presence, not planted into figure data.
- **Effect/uncertainty generation is input-gated.** Only declared group means/formulas permit the
  limited difference/ratio/percent-change check. No CI, SE, SD, effect or significance label is
  inferred from unavailable data. Declared not_computable reasons remain visible in numeric_ledger;
  they are not counted as an uncertainty estimate.
- **Non-significance detection reads the naming sentence only.** Higher/lower wording with an
  explicit not-significant qualifier in that same sentence is intentionally preserved. A null
  effect asserted in a later sentence without repeating the comparison name can still pass.
- **The hedge check is document-level for mechanisms**: one hedge anywhere in the discussion
  satisfies it.
- **The error-bar prose check is narrow.** It fires when the text mentions the bars without a
  meaning, or when the case declares `require_errorbar_in_text`; a section that leaves the
  meaning to the caption is not punished unless the case says otherwise.
- **`sample_size_absent` uses integer containment.** "n = 12" anywhere in the text satisfies
  it; "12" inside "120" also satisfies it. A heuristic, stated as such.
- **Limitation levels are declared.** The audit does not judge whether the stated limitation
  is the honest one.
- **Only limited arithmetic is recomputed.** Difference/ratio/percent-change is checked from
  declared means, with declared tolerance; the engine does not rerun the t-test, ANOVA, regression,
  or verify raw data. CI/significance cross-checking is limited to explicitly declared same
  two-sided difference inference; alternative adjusted tests must set a separate
  `ci_inference_relation`.

## Failure handling（修发现 → 重跑）

| symptom | what to do |
|-|-|
| `rd.value_not_in_figures` | use the figure's value. Statistics (p-values, test statistics, n, R², CI bounds) are exempt — never delete them from the text and never add them to the figure data to silence this rule |
| `rd.errorbar_meaning_undeclared` | state SD / SEM / CI in the figure record |
| `rd.errorbar_meaning_absent_from_text` | write the meaning into the prose ("error bars show SD") |
| `rd.statistic_missing` | name the test and the p-value |
| `rd.non_significant_claimed_as_effect` | keep any observed direction but state non-significance in the same sentence; do not claim an established effect |
| `rd.effect_size_missing` / `rd.uncertainty_missing` | compute only from supplied means or declare exact not_computable reason; never back-calculate CI from p |
| `rd.effect_value_mismatch` | correct either transcription or formula inputs from the actual table; keep source_ref and rounding tolerance explicit |
| `rd.uncertainty_inconsistent` / `rd.significance_ci_conflict` | return to actual statistical output; align point estimate, CI bounds and same-test inference |
| `rd.significance_misclassified` | align verdict with actual p_value and alpha; if thresholds differ, declare alpha explicitly |
| `rd.derivation_not_reproducible` | supply formula and actual source values/locator, or remove the unsupported derived number |
| `rd.alternative_explanations_missing` | name confounding/measurement/selection/reverse-causation alternatives and discriminating evidence if present |
| `rd.extrapolation_boundary_missing` | state measured population/material/setting/time scope and non-generalization boundary |
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
| `audit.no_section` / `audit.section_unknown` / `audit.section_error` (exit 5) | unreadable spec or no section / unknown section / caught audit failure; result.json and known contract still written, never a traceback |

## 异常处置表（运行异常 → 处置）

| exception | behaviour | where it shows |
|-|-|
| spec is not valid JSON | exit 5, `result.json` written with `audit.no_section`, message quotes the decode error | no traceback, ever |
| spec is not an object (list/string/number) | exit 5 refusal: "the spec file is not a JSON object" | `result.json` |
| spec file missing / unreadable | exit 5 refusal with the OS error text | `result.json` |
| no `section` declared | exit 5 refusal: "no section declared, so no rules apply" | `result.json` |
| unknown `section` (typo, wrong track) | exit 5 `audit.section_unknown`; valid sections are listed in `sections.py::SECTIONS`; readable case_id and full contract still echo | `result.json` |
| caught section audit error | exit 5 `audit.section_error` instead of traceback; fix actual data shape and rerun | `result.json` |
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
2. **效应量与不确定性数值账**：正文数值按数值而非字符串匹配（3=3.0），效应按声明公式
   复算，核对 CI 内部一致性、p/alpha 和显式双侧 CI 推断；`checked.numeric_ledger` 保存公式、
   source_ref 和不可计算原因。派生数字通过 formula+inputs 进入台账，绝不从 p 反推幅度/CI。
3. **阴性结果双段覆盖**：未达显著性的比较在结果段与讨论段分别检查缺席，"只报有效的"
   这一最常见的写作不诚实无处藏身；同时保留"方向更高但未显著"的正确口径，不误逼删改。
4. **IMRaD 组织与诚实边界**：结果只列观察/效应/区间，讨论处理意义、文献一致与冲突、替代
   解释和外推界限。显著性判决缺失、误差棒含义未声明、design 未识别和替代解释/外推缺失
   分别显式列出；不把观察性关联改成因果，也不把局限写成泛泛的 further work。

bench 目录下的 rd 套件（45 场景，每条规则至少一个 planted-defect 场景 + FP 守卫）与
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
  重跑 `bench_rd.py`（45）与 `bench_sections.py`（51）并保持全过。

## Verification

```bash
python scripts/bench_rd.py        # 45 scenarios: numeric calibers + one per rule + FP guards
python scripts/bench_sections.py  # 51 scenarios: cross-section regression plus false-positive guards
```

Both pass in full on this machine. The clean baseline in each must report nothing.
