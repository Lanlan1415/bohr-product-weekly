---
name: claim-verification
description: >
  Verify a paper's claims against evidence and produce a checkable chain for each one:
  claim -> quoted span -> locator in the source -> support verdict -> rationale. Checks
  that the quote really occurs in the supplied text, that its locator can be followed,
  that a verdict carries a reason, that every sub-judgement of a compound claim is
  verified separately, and that a contested claim carries counter-evidence. For the
  six-category paper quality audit (fact verification, citation support, method
  design, statistical reporting, argument chain, academic norms) it runs mechanical
  rule sets per category — including dedicated method_design / stats_reporting /
  academic_norms review sections — and assembles an itemized findings list —
  location, excerpt, verdict, severity, fix — into a three-part result (审查报告 /
  依据与边界 / 结果状态). Use when a task asks for evidence cards, citation checks,
  fact verification, a paper quality / integrity review, or an audit of whether a
  review's claims are supported.
---

# claim-verification

The deliverable is not "this claim is supported". It is a chain a second reader can walk
without reopening the whole paper:

| link | rule when it is missing |
|-|-|
| claim | `verify.empty_claim` |
| quoted span that really exists | `verify.no_evidence`, `verify.quote_not_in_source` |
| locator you can follow | `verify.evidence_no_locator`, `verify.evidence_locator_vague` |
| support verdict | `verify.support_undeclared` |
| rationale | `verify.rationale_missing` |

A chain with a missing link is worse than no chain, because the verdict looks checked.

## The four failures this exists to catch

**Topic-related cited as support.** A passage about the same material, cited for a claim
it does not make. Overlap between the claim and the quote is measured, and a span below
0.25 is reported as unrelated rather than accepted.

**A quote that is not in the paper.** Paraphrased during extraction, or produced from
memory. The quote is matched literally against the supplied source text.

**One verdict covering several assertions.** "Coating increases uptake but reduces
stability" is two claims; a single supports-verdict hides which half was checked. A
compound claim must be decomposed, and each sub-judgement carries its own verdict.

**A one-sided report.** A claim the literature contests, presented with supporting
evidence only. A contested flag obliges counter-evidence.

## Workflow

### 1. Write the chain

```json
{
  "case_id": "cbe96f01-demo",
  "section": "claim_verify",
  "output_contract": ["audit_report", "evidence_bounds", "result_state"],
  "references": [{"key": "doe2020", "title": "Porous coatings for uptake", "year": 2020}],
  "source_text": "The porous coating increased the uptake rate three-fold. ...",
  "claims": [
    {"claim": "porous coating increases uptake rate",
     "support": "supports",
     "rationale": "the quoted sentence states the rate increase directly",
     "evidence": [{"source": "doe2020",
                   "quote": "The porous coating increased the uptake rate three-fold.",
                   "locator": "Fig 3b, p.7"}]}
  ]
}
```

`source_text` is what the quote is matched against — omit it and the literal check cannot
run. `support` is one of supports / partial / insufficient / refutes. The top-level
`case_id` and the `output_contract` array are the runtime contract hooks: the CLI copies
`case_id` into the result and back-fills every named contract field (see 运行时输出契约).

### 2. Run it

```bash
python scripts/secrun.py --spec spec.json --section claim_verify --out /app/output
```

Exit codes: 0 clean, 3 review, 4 blocked, 5 undetermined (refused — result.json is still
written; a traceback is never the outcome).

### 3. Run one spec per audit category

The six-category audit routes one section per category (see 六类问题审查指南); run each
category's spec through the same CLI, then merge that section's findings into the itemized
report. A case that provides only part of a paper is audited on the provided text only,
with the uncovered chapters named in the result rather than silently skipped.

## Rules

### The chain (claim_verify)

| rule | severity | what it proves |
|-|-|-|
| `verify.no_evidence` | high | a claim has no span at all |
| `verify.evidence_empty_quote` | high | a span carries no quoted text |
| `verify.quote_not_in_source` | high | the quote does not occur in the supplied text |
| `verify.evidence_no_locator` | high | no page/table/figure locator |
| `verify.evidence_locator_vague` | medium | the locator cannot be followed |
| `verify.support_undeclared` | high | no supports/partial/insufficient/refutes verdict |
| `verify.rationale_missing` | high | the verdict carries no reason |
| `verify.evidence_unrelated` | high | the span shares almost no content with the claim |
| `verify.unknown_source` | high | the span points outside the reference list |
| `verify.reference_metadata_incomplete` | medium | a reference lacks title or year |
| `verify.subjudgements_missing` | medium | a compound claim is not decomposed |
| `verify.subjudgement_empty` | high | a sub-judgement has no statement |
| `verify.subjudgement_verdict_missing` | high | part of the claim is unverified |
| `verify.subjudgement_kind_unknown` | medium | a sub-kind outside fact/comparison/causal/scope |
| `verify.counter_evidence_missing` | high | a contested claim shows only one side |
| `verify.empty_claim` | high | a claim entry has no text |
| `verify.no_claims` | high | nothing to verify |

### 事实核验 — conclusion_extract

| rule | severity | what it proves |
|-|-|-|
| `extract.no_items` | high | no extracted items were supplied |
| `extract.schema_missing` | high | no field schema declared, so the result cannot be re-run |
| `extract.field_undefined` | medium | a schema field has no definition |
| `extract.field_absent` | high | an item omits a field the schema declares |
| `extract.empty_claim` | high | an extraction item has no claim text |
| `extract.kind_undeclared` | high | conclusion/limitation/speculation not declared |
| `extract.kind_unknown` | medium | a kind outside the three |
| `extract.source_kind_missing` | medium | body/table/figure/supplement not declared |
| `extract.source_kind_unknown` | low | a source kind outside the four |
| `extract.missing_locator` | high | no page/paragraph/table/figure locator |
| `extract.locator_vague` | medium | locator names no page/section/cell/figure |
| `extract.missing_condition` | high | the conditions the finding holds under are absent |
| `extract.hedge_dropped` | high | extracted claim is absolute while the source hedged |
| `extract.gap_unclassified` | high | a blank field is not labelled not_reported/failed |
| `extract.value_without_unit` | medium | an extracted value carries no unit |
| `extract.value_not_in_source_text` | high | a verbatim value does not occur in the source |
| `extract.source_not_covered` | medium | a declared source kind was never used |

### 事实核验（问答式）— qa

| rule | severity | what it proves |
|-|-|-|
| `qa.no_answers` | high | no answers were supplied |
| `qa.empty_answer` | high | an answer has no text |
| `qa.subquestion_unanswered` | high | a sub-question got no answer |
| `qa.question_uncovered` | medium | a supplied question was never answered |
| `qa.uncited_answer` | high | an answer cites no evidence |
| `qa.unknown_evidence` | high | an answer cites evidence that does not exist |
| `qa.citation_no_locator` | high | the cited evidence has no locator |
| `qa.citation_unsupportive` | high | the cited evidence does not entail the answer |
| `qa.answer_value_not_in_source` | high | a number in the answer is not in the source |
| `qa.material_insufficient_unflagged` | high | thin material was answered without a gap note |
| `qa.conflict_unhandled` | medium | conflicting material was not reported as a conflict |
| `qa.refusal_without_reason` | medium | a refusal carries no reason |

### 方法设计 — method_design（审查专用）

审查一篇论文如何报告其方法设计：第二读者能否说清做了什么、多少单位、对照什么、用什么材料与仪器。spec 关键字段：methods_text（被审的方法章节原文，发现要引用它）、design、controls、randomisation、blinding、sample_size、sample_size_basis、subjects、materials[].name/source/version/locator、instruments[].name/model、parameters[].name/source/locator/justification。

| rule | severity | what it proves |
|-|-|-|
| `mrev.no_methods` | high | no methods text and no structured method records at all |
| `mrev.methods_text_missing` | medium | records exist but the methods text is absent, so no finding can quote the section |
| `mrev.design_unstated` | high | the study design is not stated |
| `mrev.control_missing` | high | a comparative design declares no control group |
| `mrev.randomisation_unstated` | medium | a comparative design does not state assignment |
| `mrev.blinding_unstated` | medium | a comparative design says nothing about blinding |
| `mrev.sample_size_missing` | high | no sample size anywhere in the declared record |
| `mrev.sample_size_basis_missing` | medium | a sample size with no basis (power, alpha) |
| `mrev.replicates_missing` | medium | an experimental design states no replicate count |
| `mrev.material_source_missing` | high | a material has no source |
| `mrev.material_version_missing` | medium | a material records no version or batch |
| `mrev.material_no_locator` | medium | a material record cannot be located in the methods text |
| `mrev.instrument_unspecified` | medium | an instrument names no model |
| `mrev.parameter_source_undeclared` | high | a parameter does not say paper/code/derived/assumed |
| `mrev.parameter_no_locator` | medium | a sourced parameter has no locator into the text |
| `mrev.assumed_without_justification` | high | an assumed parameter carries no justification |

对照组与随机化规则只对比较类设计触发（experimental、RCT、randomised、对照试验、随机对照……按子串匹配，自由措辞也能门控）；描述性单臂研究合法地不触发。

### 统计报告 — stats_reporting（审查专用）

审查统计报告的三件事：每个显著性结论能否追到检验、正文与表格数字是否一致、精度是否报告。spec 关键字段：results_text（结果章节原文）、claims[].comparison/significant/test/statistic/p_value、inferential、multiple_comparisons、figures[].has_errorbar/errorbar、cross_checks[].where_a/where_b/value_a/value_b（同一量在两处的数值对照）。

| rule | severity | what it proves |
|-|-|-|
| `srep.nothing_declared` | high | no results text, claim or cross-check was supplied |
| `srep.test_missing` | high | significance claimed without naming a test |
| `srep.statistic_value_missing` | high | a test is named but no statistic value is reported |
| `srep.p_value_missing` | high | a test or statistic is reported with no p value |
| `srep.sample_size_missing` | medium | the statistical record reports no sample size |
| `srep.ci_missing` | medium | exact p values but no confidence interval anywhere |
| `srep.multiple_comparisons_unaddressed` | medium | 3+ comparisons with no correction stated |
| `srep.errorbar_undeclared` | high | error bars without an SD/SEM/CI meaning |
| `srep.inconsistent_value` | high | the same quantity has two different numbers at two named locations |
| `srep.crosscheck_unlocated` | medium | a cross-check names no location or omits a value |

数值对照（cross_checks）把「正文/表格/图注/摘要自相矛盾」变成机械判定：两处定位 + 两个数值，不等即 high。样本量 n = 12 不算「已报告统计量」，样本量模式被刻意排除在统计量豁免之外。

### 学术规范 — academic_norms（审查专用）

审查署名、重复发表、数据与代码可用性、伦理与利益冲突声明以及引用卫生。spec 关键字段：manuscript_text、authorship / author_contributions、data_availability（data_used 非假时必查）、code_availability（code_used 真时必查）、ethics / consent（subjects 涉人时必查）、coi / competing_interests、funding、duplicate_publication.checked、references[].key/title/year/doi/needs_doi/retracted。

| rule | severity | what it proves |
|-|-|-|
| `norm.nothing_declared` | high | no manuscript, references or norms statement at all |
| `norm.authorship_undeclared` | high | no authorship or contribution statement |
| `norm.data_availability_missing` | high | data used but no data-availability statement |
| `norm.code_availability_missing` | medium | code used but no code-availability statement |
| `norm.ethics_missing` | high | human/animal subjects with no ethics approval |
| `norm.consent_missing` | medium | human subjects with no consent statement |
| `norm.coi_undeclared` | high | no conflict-of-interest statement |
| `norm.funding_undeclared` | medium | no funding statement |
| `norm.duplicate_publication_unchecked` | medium | duplicate publication was not checked |
| `norm.reference_metadata_incomplete` | medium | a reference lacks title or year |
| `norm.reference_no_doi` | low | a reference that should carry a DOI does not |
| `norm.retracted_source_used` | high | a retracted source is still cited |
| `norm.citation_padding` | low | one sentence carries four or more references |

### 统计与推理强度 — results_discussion（写作轨复用）

| rule | severity | what it proves |
|-|-|-|
| `rd.results_missing` | high | no results section supplied |
| `rd.discussion_missing` | high | no discussion section supplied |
| `rd.value_not_in_figures` | high | a results number is absent from the figure/table data |
| `rd.errorbar_meaning_undeclared` | high | error bars with no SD/SEM/CI meaning |
| `rd.comparison_no_verdict` | high | a comparison does not state significance |
| `rd.statistic_missing` | high | significance claimed without test or p-value |
| `rd.non_significant_claimed_as_effect` | high | a non-significant result described as an effect |
| `rd.interpretation_in_results` | high | causal language inside the results section |
| `rd.mechanism_as_fact` | high | a mechanism stated without any hedge |
| `rd.discussion_uncited` | high | a discussion claim attributed to nothing |
| `rd.causal_overreach` | high | causal language for an observational design |
| `rd.negative_result_omitted` | high | a non-significant comparison never mentioned |
| `rd.conflicting_literature_ignored` | high | a disagreeing source never mentioned |
| `rd.limitations_missing` | high | no limitation stated |
| `rd.limitation_vague` | medium | a limitation names no level of the study |
| `rd.limitation_level_narrow` | medium | limitations confined to a single level |
| `rd.limitation_level_unknown` | low | a level outside method/sample/measurement/statistics |
| `rd.unitless_number` | medium | a results number carries no unit |
| `rd.overclaim` | medium | an absolute claim with no strength label anywhere |

### 论证链 — structure_logic

| rule | severity | what it proves |
|-|-|-|
| `struct.no_manuscript` | high | neither text nor paragraphs supplied |
| `struct.research_question_missing` | high | no stated research question |
| `struct.question_absent_from_text` | high | the question shares no wording with the manuscript |
| `struct.contribution_unanchored` | high | a contribution is tied to no section |
| `struct.contribution_anchor_unknown` | medium | a contribution anchor is not in the text |
| `struct.no_diagnosis` | high | no structural diagnosis supplied |
| `struct.dimension_missing` | high | a required dimension was not diagnosed |
| `struct.dimension_unknown` | low | a dimension outside the six |
| `struct.finding_no_evidence` | high | a finding quotes no manuscript text |
| `struct.evidence_not_in_text` | high | quoted evidence does not occur in the manuscript |
| `struct.finding_no_locator` | high | a finding gives no location |
| `struct.style_as_defect` | high | a style preference reported as a structural defect |
| `struct.suggestion_missing` | high | a substantial finding carries no suggestion |
| `struct.suggestion_no_action` | high | a suggestion names no concrete action |
| `struct.suggestion_orphaned` | medium | a suggestion points at no finding |
| `struct.multiple_claims` | medium | a paragraph carries more than one claim |
| `struct.orphan_paragraph` | medium | a paragraph makes no claim |
| `struct.claim_without_support` | high | a claim has no support pointer |
| `struct.circular_support` | high | a claim supported by another claim in the same outline |
| `struct.support_weaker_than_claim` | high | the evidence is weaker than the claim |
| `struct.duplicate_paragraph` | medium | two paragraphs say largely the same thing |
| `struct.section_interleaved` | medium | a section resumes after another intervenes |
| `struct.conclusion_exceeds_scope` | high | causal wording beyond the design |
| `struct.limitations_missing` | medium | a boundary claim with no limitation |

### 学术规范（写作轨复用）— paper_draft

| rule | severity | what it proves |
|-|-|-|
| `pd.draft_missing` | high | no draft text supplied |
| `pd.sections_missing` | high | a template section is absent |
| `pd.declaration_missing` | medium | a required declaration is missing |
| `pd.materials_missing` | high | no material index supplied |
| `pd.material_no_locator` | high | a material has no location |
| `pd.material_unknown` | high | a cited material is not in the index |
| `pd.material_unused` | medium | an indexed material supports no sentence |
| `pd.uncited_claim` | high | a factual sentence carries no reference |
| `pd.unknown_source` | high | a cited reference is not in the list |
| `pd.citation_mismatch` | medium | the reference shares no topic with the sentence |
| `pd.citation_padding` | low | four or more references on one sentence |
| `pd.value_not_in_materials` | high | a number does not appear in the cited material |
| `pd.trend_as_causation` | high | causal language for an observational design |
| `pd.figure_caption_missing` | high | a figure has no caption |
| `pd.figure_caption_mismatch` | high | caption and figure data disagree |
| `pd.figure_uncited` | medium | a figure never referred to in the text |
| `pd.figure_numbering_gap` | medium | figure numbers skip |
| `pd.abstract_result_conflict` | high | an abstract number is absent from the body |
| `pd.reference_metadata_incomplete` | medium | a reference lacks identifying metadata |
| `pd.reference_no_doi` | low | a reference that should carry a DOI does not |
| `pd.change_log_missing` | medium | no revision trail supplied |

### 复现闭环 — reproduce（方法设计的事实核对）

| rule | severity | what it proves |
|-|-|-|
| `repro.stage_missing` | high | a stage of the reproduction loop is absent |
| `repro.stage_unknown` | low | a declared stage is outside the six |
| `repro.no_stages` | medium | no loop stages declared |
| `repro.no_commit` | high | the repository revision is not recorded |
| `repro.no_data_version` | high | the data version is not recorded |
| `repro.no_command` | high | the run command is not recorded |
| `repro.material_without_source` | high | a material has no source |
| `repro.material_without_version` | medium | a material records no version |
| `repro.material_state_undeclared` | medium | present/missing/partial not stated |
| `repro.material_no_license` | medium | a redistributable artefact records no license |
| `repro.environment_incomplete` | medium | the environment snapshot omits a field |
| `repro.env_conflict_unflagged` | high | an installed version differs from the paper's unflagged |
| `repro.parameter_source_undeclared` | high | a parameter does not say paper/code/assumed |
| `repro.assumed_without_justification` | high | an assumed parameter has no justification |
| `repro.parameter_no_locator` | medium | a sourced parameter has no locator |
| `repro.no_tolerance` | high | results compared without a tolerance |
| `repro.no_comparison_basis` | medium | the comparison does not say what is aligned |
| `repro.no_statistic` | low | no aggregation declared for the comparison |
| `repro.metric_no_verdict` | high | a metric does not say whether it landed in tolerance |
| `repro.difference_unclassified` | high | an out-of-tolerance gap is not classified |
| `repro.difference_unexplained` | medium | a classified gap is not explained |
| `repro.verdict_unclassified` | high | the verdict is outside the three grades |
| `repro.verdict_without_basis` | high | the verdict carries no basis |
| `repro.no_logs` | medium | the run records no log |
| `repro.no_exit_status` | medium | the run does not record success |

### 拒绝与畸形条目（全 section 共用）

| rule | severity | what it proves |
|-|-|-|
| `audit.no_section` | high | 无 section、未知 section、spec 不是 JSON 或不是 JSON 对象 —— 拒绝并写 result.json，退出码 5，永不 traceback |
| `audit.spec_malformed` | high | 形状无法安全跳过的畸形（字段给成 int/bool 破坏遍历）—— 已产出的部分发现被丢弃，整体按 undetermined 拒绝，退出码 5，永不 traceback |

两个拒绝路径都写出 result.json。bare string 混进记录列表属于可安全跳过的畸形：按缺内容如实审计，发现照常出现，退出码 3/4。

## Output contract

`/app/output/result.json`: `status`, `section`, `findings[]` (with claim index, quote,
locator), `severity_counts`, `checked`, `limits`.

## Limits

- **Overlap is lexical, not entailment.** It proves the span is *about* the claim, not that
  it supports it. A span that passes can still be misread — that is what `rationale` is for.
- **The verbatim check needs `source_text`.** Without it the rule cannot run, and the
  report should say so rather than implying the quote was checked.
- **Compound detection is a conjunction list.** It prompts decomposition; it does not judge
  whether the halves are truly separable.
- **A contested claim is declared.** The audit cannot know the literature; it can only refuse a
  one-sided report once you say the claim is disputed.
- **Opposing evidence is presence-checked.** Whether the counter-evidence is convincing is
  a reader's judgement.
- **It does not read PDFs.** Quoting and locating is the extraction step; this audits the
  chain that comes out of it.
- **方法设计的对照/随机化/盲法规则按设计词门控。** 描述性或单臂研究合法地没有对照组；设计词
  写清楚（哪怕 just "descriptive"）就不会被误报。
- **srep 数值对照按声明执行。** cross_checks 只核对声明出来的两处数值；没有声明的矛盾
  属于判读检查表（正文-表格-摘要逐数核对），不是引擎漏报。
- **norms 的相关性门控是声明的。** subjects / data_used / code_used 说"不涉及"就跳过对应
  规则——说错了是审查者的责任，不是引擎的。

## Failure handling

| symptom | what to do |
|-|-|
| `verify.quote_not_in_source` | re-read the passage; a paraphrase is not a quote |
| `verify.evidence_unrelated` | the passage discusses the topic but not this claim — find the right one |
| `verify.rationale_missing` | say why the verdict holds, in one sentence |
| `verify.subjudgements_missing` | split the claim; one verdict per assertion |
| `verify.counter_evidence_missing` | give the opposing span, or drop the contested flag and justify that |
| `verify.evidence_no_locator` | add page, table cell or figure number |
| `mrev.control_missing` | 补对照组或把设计改为描述性/单臂，二选一如实声明 |
| `mrev.sample_size_missing` | 在方法记录里给出 n = …；真没有就按报告缺口如实进入待复核 |
| `mrev.assumed_without_justification` | 给假设参数写依据，或改标来源 |
| `srep.test_missing` | 每个显著性结论补检验名（t-test / ANOVA / Mann-Whitney…） |
| `srep.statistic_value_missing` | 补统计量值（t(24) = 3.2、F(2,36) = …） |
| `srep.inconsistent_value` | 逐数核对正文/表格/摘要，改错的一方并在 change 记录里写明 |
| `srep.errorbar_undeclared` | 声明误差棒含义（SD / SEM / 95% CI），没有误差棒就写 none |
| `norm.authorship_undeclared` | 补署名与作者贡献声明；确无则记为报告缺口 |
| `norm.ethics_missing` | 补伦理批件号；不适用时明确写"not applicable"及原因 |
| `norm.retracted_source_used` | 换掉撤稿来源并在依据与边界里记录更正信息 |
| `audit.no_section` | spec 不可运行：修 section 名后重跑；result.json 已按 undetermined 写出，退出码 5 |
| `audit.spec_malformed` | spec 字段形状不可遍历：修字段形状后重跑；result.json 已按 undetermined 写出，退出码 5 |

## 运行时入口与输出契约（Harbor）

平台运行契约（challenge-cbe96f01 按此约定执行）：

1. **输入**：运行时原始输入固定为 /input/case.json 与 task.md。先读
   `case.json`，取 `case_id`、任务说明与 `output_contract`；再按 task.md 指向的
   材料路径读**实际文件**——PDF 用平台 pdf-text-tool 抽文本，扫描件走 OCR。标签、
   文件名、领域字段不是内容来源，一切判定以实际输入文件和原论文为事实依据。
2. **工作区**：中间产物一律写 /app/work（抽取文本、逐类 spec、逐节 findings、
   运行日志）；尽早写出诚实的部分结果，再增量改进。
3. **输出**：最终结果写 /app/output/result.json，结构如下（缺一处即不可复核）：

```json
{
  "case_id": "取自 case.json 顶层，原样回填",
  "…output_contract 的每个原始字段…": "逐字段原文拷贝，不改名不遗漏；不可推导的置 null 并在 limits 写明",
  "status": "done | partial | failed",
  "status_reason": "partial/failed 时的原因（一句话）",
  "audit_report":    [{"id": "F01", "category": "事实核验", "location": "p.7 Table 2 行3",
                       "excerpt": "原文摘录", "verdict": "事实错误", "severity": "high",
                       "fix": "修改建议"}],
  "evidence_bounds": {"excerpts": [], "citation_evidence": [], "pending_review": []},
  "result_state":    {"passed": [], "problems": [], "pending_review": [], "not_checked": []},
  "findings":        "引擎逐节产出的机械 finding（含 rule/severity/定位）",
  "severity_counts": {},
  "sources":         "每条判定的证据定位串，与 audit_report.location 一致",
  "uncertainty":     "待复核项清单（材料缺失/引文歧义/无法确认），不进 severity_counts",
  "limits":          "本次审查的边界声明"
}
```

- `output_contract` 原字段**逐字段拷贝**进 result.json 顶层；引擎产出可映射的映射
  填充（findings/severity_counts/status），不可推导的置 null 并在 limits
  加一条说明——绝不改名或遗漏。
- `status` 映射：引擎 clean → done；review → partial（status_reason 写明
  待补什么）；blocked / undetermined（exit 5）→ failed（status_reason 写明
  失败环节）。材料缺失、无法判断和运行失败分别说明，不凭空补齐。
- 每类 spec 跑完 `scripts/secrun.py` 后，把该节 findings 并入总 findings；条目化
  问题清单（audit_report）由 findings + 判读检查表合并生成。
- 直通机制：spec 顶层提供的 output_contract 同名字段值会被 CLI 原样拷入 result.json
  （大体积输入字段除外）；推导不出的字段填 null 并在 limits 里说明。因此把
  audit_report / evidence_bounds / result_state 三段的字段值放进 spec 顶层，
  即直通最终 result.json。

## 六类问题审查指南

题目要求覆盖六类问题。分工原则：**引擎规则可机械判定的交给引擎，需要判读的按检查
表执行，判读不出的标待复核**——三类产出都进同一条目化清单。六个类别现在全部有
对应的引擎 section 与机械规则（方法设计/统计报告/学术规范三类由本轮新增的
method_design / stats_reporting / academic_norms 承接）。

| # | 问题类别 | 引擎 section | 机械规则 | Agent 判读检查表 |
|-|-|-|-|-|
| 1 | 事实核验 | `qa`、`conclusion_extract` | `qa.answer_value_not_in_source`、`extract.value_not_in_source_text`、`extract.hedge_dropped`、`extract.gap_unclassified` | 数值与结论逐条回原文核对；预印本与正式版不一致、更正/撤稿未反映 → 判「事实错误」或「待复核」 |
| 2 | 引用支持 | `claim_verify` | `verify.quote_not_in_source`、`verify.evidence_unrelated`、`verify.support_undeclared`、`verify.subjudgements_missing`、`verify.counter_evidence_missing` | 四态判定 supports/partial/insufficient/refutes；识别「结论超出引文范围」的过度推断 |
| 3 | 方法设计 | `method_design`、`reproduce` | `mrev.design_unstated`、`mrev.control_missing`、`mrev.sample_size_missing`、`mrev.replicates_missing`、`mrev.material_source_missing`、`mrev.parameter_source_undeclared`、`mrev.assumed_without_justification` | 样本量、对照设置、重复数、仪器与材料批次、关键参数是否写全且可溯源；缺来源的方法细节判「证据不足」 |
| 4 | 统计报告 | `stats_reporting`、`results_discussion` | `srep.test_missing`、`srep.statistic_value_missing`、`srep.p_value_missing`、`srep.inconsistent_value`、`srep.errorbar_undeclared`、`rd.statistic_missing`、`rd.non_significant_claimed_as_effect`、`rd.unitless_number` | 每个显著性结论要有检验名、统计量、p 值、样本量；误差棒含义（SD/SEM/CI）必须声明；正文/表格/图注/摘要间的数字是否自相矛盾（cross_checks 机械核对 + 判读兜底） |
| 5 | 论证链 | `structure_logic`、`results_discussion` | `struct.circular_support`、`struct.conclusion_exceeds_scope`、`struct.support_weaker_than_claim`、`rd.causal_overreach`、`rd.mechanism_as_fact`、`rd.overclaim` | 结论跳跃、循环论证、以偏概全、缺少对照的推断：把「依据强度 < 结论强度」的每一处列出 |
| 6 | 学术规范 | `academic_norms`、`paper_draft` | `norm.authorship_undeclared`、`norm.data_availability_missing`、`norm.ethics_missing`、`norm.coi_undeclared`、`norm.retracted_source_used`、`pd.declaration_missing`、`pd.citation_padding` | 署名与作者贡献、数据与代码可用性、伦理批件、利益冲突声明、重复发表；凑数引用与未引用的结论 |

每条产出都是条目化问题清单的一行：**位置（页/段/图表/数据集条目的定位串）、原文
摘录、判定、严重度、修改建议**——五要素缺一不可；只有一段总体评价不算完成。

## 关键章节覆盖

方法、结果、讨论三个关键章节必须**各有条目**；某一章未发现问题时，也要把该章写入
result_state.passed 点名，而不是沉默。推荐分工：

- **方法** → `method_design`（机械）+ `reproduce`（参数溯源细节）：设计、对照、随机化、
  盲法、样本量与依据、重复数、材料来源与版本、仪器型号、参数 paper/code/assumed 分级；
- **结果** → `stats_reporting`（机械）+ `results_discussion` + `conclusion_extract`：
  统计三件套（检验/统计量/p 值）、样本量、CI、多重比较、误差棒含义、cross_checks
  数值一致性、单位与量纲（rd.unitless_number）、负结果是否遗漏；
- **讨论** → `claim_verify` + `structure_logic`：每条结论的引用支持链、因果措辞、
  限制是否诚实（rd.limitations_missing、rd.limitation_vague）、与文献冲突是否
  被回避（rd.conflicting_literature_ignored）；
- **规范**（全文）→ `academic_norms`：署名/贡献、数据与代码可用性、伦理与同意、
  利益冲突、基金、重复发表、撤稿来源、凑数引用。

材料只有部分章节（如仅摘要）时：只审提供的文本，未覆盖章节写进
result_state.not_checked 并在 limits 说明——宁可少而可查，不可全而不可查。

## 三段输出结构与五类分级

result.json 三段与 rubric「Skill 运行后的输出要求」一一对应：

| rubric 段 | result.json 键 | 完成标准 |
|-|-|-|
| 审查报告 | `audit_report[]` | 逐条问题（category/location/excerpt/verdict/severity/fix），覆盖六类问题与方法/结果/讨论关键章节 |
| 依据与边界 | `evidence_bounds` | 稿件原文摘录、引用/数据/方法证据及待复核项；完成标准：区分错误、证据不足和建议 |
| 结果状态 | `result_state` | 通过、问题、待复核和未检查项四张 id 清单；完成标准：不凭空补齐缺失信息 |

五类分级（verdict 与 severity 联合决定；severity 承接引擎 finding）：

| 分级 | 判定标准 | 引擎 finding 对应 |
|-|-|-|
| 事实错误 | 与原文/来源直接矛盾（数值、结论、版本、撤稿状态） | `extract.value_not_in_source_text`、`qa.answer_value_not_in_source`、`srep.inconsistent_value`、`norm.retracted_source_used` |
| 证据不足 | 断言缺证据或证据不支持（high） | `verify.no_evidence`、`verify.evidence_unrelated`、`srep.test_missing`、`mrev.sample_size_missing`、`rd.causal_overreach` |
| 规范问题 | 违反学术规范而非事实错误（medium） | `norm.authorship_undeclared`、`norm.data_availability_missing`、`pd.reference_no_doi`、`verify.reference_metadata_incomplete` |
| 建议性意见 | 可改进但构不成错误（low / 建议类 medium） | `extract.locator_vague`、`norm.citation_padding`、`pd.material_unused` |
| 待复核 | 材料取不到、引文歧义、无法确认——进 `uncertainty` 与 `result_state.pending_review`，不进 severity_counts | 无引擎规则，Agent 显式声明并写明缺什么才能确认 |

## 材料形态与异常处置

| 形态 / 故障 | 处置 |
|-|-|
| 电子全文 PDF | pdf-text-tool 抽文本进 spec；source_text 给全文，逐字匹配可跑满 |
| 扫描 PDF 无文本层 | 先 OCR 再进 spec；OCR 噪声导致的引文不匹配降级为「待复核」，不判事实错误 |
| 仅摘要 / 节选 | 只审提供的文本；未覆盖章节进 not_checked，limits 写明审查范围 |
| 原文取不到（被引文献无全文） | 引用支持只能按材料内语境判；标「外部原文未取得」→ 待复核，不猜内容 |
| 引文严重歧义（多处相似段落） | 取 overlap 最高处，locator 写明歧义与备选位置 |
| 来源撤稿 / 版本不一致 | norm.retracted_source_used 与 srep.inconsistent_value 机械报告；版本差异记进 evidence_bounds |
| 数据库权限不足 | 失败原因写进 limits；可复核部分照常交付，status: partial |
| PDF 无法解析 / spec 不可读 | 走 exit 5 拒绝路径：仍写 result.json（status: failed + 原因），不崩溃、不交空结果 |
| spec 字段形状错误（记录列表给成 int/bool） | audit.spec_malformed 拒绝：result.json 照写，退出码 5；bare string 条目则跳过并如实审计（3/4） |
| 重复运行 | 复用上轮 findings 之前先核对 case_id 与材料哈希；不叠加两轮结果 |

## 使用增益与对照方法

- **公平对照**：相同材料、相同工具权限下，不加载本 Skill 的基础 Agent 输出与加载
  后的条目化审查结果对比，按「召回（漏报问题数）、定位精度（定位串可回查率）、
  误报控制（判错条目数）」三项净变化计数；平台白板是对照基准，不是参赛者答案。
- **效率增益**：定位串 + 逐字存在性检查替代人工逐条回查与重复检索；每条 finding
  自带 rule id 与证据，复核人按记录走查即可，不需重读全文。方法设计/统计报告/
  学术规范三类的机械规则把「读方法节查对照、读结果节查统计三件套、全文查规范
  声明」从逐句人工阅读变成可重跑的检查。
- **增益证据形式**：`scripts/bench_verify.py` 16 场景 + `scripts/bench_sections.py`
  101 场景（clean 基线零发现），同输入重跑 findings 一致。

## Verification

```bash
python scripts/bench_verify.py    # 16/16: one per rule on the chain, clean baseline silent
python scripts/bench_sections.py  # 101/101: cross-section regression, one defect per rule
                                  #   for all 17 sections, false-positive guards included
```

Both pass in full on this machine. The clean baseline in each must report nothing.
bench_sections 含 4 个畸形 spec 场景（int/bool 注入 → audit.spec_malformed + 退出码 5
的回归）与 11 个假阳性守卫（描述性研究、非显著声明、非人体验研究不得误报）。

## Requirements

Python 3.9+（3.14 实测）。纯标准库实现，无第三方依赖。scripts/ 下每个 .py 都是
引擎或回归门：sections.py（规则引擎）、secrun.py（CLI）、guard.py / units.py
（共享机械件）、bench_verify.py / bench_sections.py（回归）、无死代码。

## 创新增益

本 Skill 相比通用 Agent 的新增能力（每条附能力边界与增益证据形式）：

1. **引文与结论的语义对齐**：「引用存在」≠「引用支持」——lexical overlap + 逐字存在
   性检查把「主题相关被当支持」和「引文不存在」变成可计算判定。
   *边界*：overlap 是词汇重叠不是蕴含，最终由 rationale 承接判读。
   *证据形式*：`bench_verify.py` 的 evidence_unrelated / quote_not_in_source 场景。
2. **六类审查全部机械化**：方法设计（对照组/随机化/盲法/样本量/材料版本/参数来源）、
   统计报告（检验名/统计量/p 值/CI/多重比较/误差棒含义/两处数值矛盾）、学术规范
   （署名/数据与代码可用性/伦理/利益冲突/撤稿引用）不再只是 Agent 检查表——三类
   各有 10-16 条机械规则、有 bench 场景一一对应，审查可以重跑并得到同一批发现。
   *边界*：设计词与相关性门控按声明执行；声明错了责任在输入，不在规则。
   *证据形式*：`bench_sections.py` 的 mrev_*/srep_*/norm_* 共 39 个缺陷场景 + 3 个
   假阳性守卫 + 3 个 clean 基线。
3. **两处数值矛盾的机械判定**：cross_checks 把「正文 vs 表格 vs 摘要」的自相矛盾
   从逐句人工比对变成 {where_a, value_a, where_b, value_b} 结构化输入上的不等判定。
   *边界*：只核对声明出的对照项；未声明的矛盾靠判读检查表兜底。
   *证据形式*：`bench_sections.py` 的 srep_inconsistent_value / srep_crosscheck_unlocated。
4. **严重度分级与待复核隔离**：事实错误/证据不足/规范/建议/待复核五类分开；
   待复核进 uncertainty 不进 severity_counts——低危条目不会稀释高危计数。
   *证据形式*：result.json 的 severity_counts 与 uncertainty 分离结构（见运行时
   输出契约节）。
5. **可复现的审查过程**：同一 spec 重跑 findings 逐字节一致（确定性引擎，无随机源）；
   全部规则有 id，逐条可复核、可反驳；两种畸形输入（不可读 spec、形状不可遍历）
   都按 undetermined 拒绝并写 result.json，退出码恒在 0/3/4/5。
   *证据形式*：`bench_sections.py` 101 场景跨节回归（含 4 个畸形拒绝回归），
   clean 基线零发现；strict_gate G5 确定性检查。

## 生态贡献

- **使用说明**：本文件包含用途、适用条件、调用方式、输入输出、关键方法、适用场景、
  限制、失败处理和自查方法；按 Workflow 一节可独立完成一次审查。
- **依赖与配置**：Python 3.9+（3.14 实测），纯标准库，无第三方依赖、无安装步骤；
  规则与阈值经 spec 配置扩展，无需改码。
- **判定规则全公开**：174 条规则 id + 严重度在本文档逐条列出并与引擎一一对齐
  （strict_gate G4 校验文档-引擎一致）；三条 review 规则集的设计模式与门控条件
  写在各自小节，他人可按同样模式加新类别。
- **示例（标注为示例）**：`examples/spec.json` 是最小输入示例（含 case_id 与
  output_contract 直通示范），`examples/bench-report.json` 是 bench 报告的示意
  输出——均为示例，不冒充正式案例结果。
- **回归门**：`bench_verify.py`（16）与 `bench_sections.py`（101）是两道回归门，
  clean 基线零发现 + 每条规则一个缺陷场景 + 假阳性守卫，任何改动后两套 bench
  必须全过；自查方法：跑两套 bench 并核对 clean 基线零发现。
- **适用范围**：引用支持、事实核验、方法设计、统计报告、论证链、学术规范六类审查；
  不负责论文润色、综述写作和数据分析建模，不替代作者对研究结论的判断。
- **限制**：见 Limits 一节（词汇重叠非蕴含、逐字检查依赖 source_text、不读 PDF、
  门控按声明执行等）。
- **维护**：规则 id 变更须同步本文档规则表（strict_gate G4 会拒绝文档与引擎不一致
  的提交）；scripts/ 目录只含引擎、CLI、共享件与回归门，无死代码。
