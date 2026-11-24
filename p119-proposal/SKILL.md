---
name: research-proposal
description: >
  Draft and audit an opening report / research plan (开题报告与研究计划书) as seven checkable
  elements — background with a known-unknown-to-test gap statement, a bounded problem, objectives
  carrying metric / sample / control / timepoint and a grounded threshold, a technical route with
  input, output and declared dependencies, a schedule that fits the stated period with milestones
  on a critical path, risks classified by type each with trigger / impact / fallback / decision
  point, and expected outcomes tied back to objectives. It additionally links every objective
  to a falsifiable hypothesis, an owned work package, data collection/quality/analysis, explicit
  applicable-or-not ethics governance and acceptance evidence, then emits an editable Markdown
  plan plus objective/work-package/evidence matrices — plus a grant-proposal variant
  (rationale, question, objectives, content, innovation, route, foundation). Every claim keeps a
  material or reference and a version, the resource need is checked against the envelope, and the
  result echoes the case identifier and every declared output contract field. Use when a task asks
  for an opening report, research plan, 开题报告, 研究计划书, proposal section or grant application
  draft that must survive review rather than merely read well.
---

# research-proposal

What gets a proposal rejected is rarely a bad idea. It is a background that lists literature
instead of a gap, an aim nobody can assess, a route that names methods instead of steps, a
schedule that ignores the calendar it was given, risks with no trigger, or a claim nobody can
trace. Each of those is checkable, and each is a rule here.

The task names four questions, and each maps to rules:

| the brief's question | what the audit proves |
|-|-|
| 立得住 (the problem is real and bounded) | the background separates 已知 / 未知 / 待验证; the question carries a boundary; claims trace to a material or reference with a version |
| 对得上 (goals, route, evidence, outcomes correspond) | every objective carries metric / sample / control / timepoint and a threshold basis; every route step serves an objective; every outcome names the objective it delivers |
| 排得开 (the plan fits period and resources) | schedule end months stay inside the declared period, in calendar order, with a deliverable per phase and a marked critical path; resource need fits the envelope |
| 说得清 (risks and sources are explicit) | risks are classified, each with trigger / impact / fallback / decision point; the two core risk kinds are covered; the budget has a basis |

## The five failures this exists to catch

**A background that is a literature list.** 已知、未知、待验证 are three different sentences.
A background without the split is refused as a gap statement.

**An aim with no measure.** "提高吸收效率" cannot be completed. `metric` is what would be
observed, `control` is what it is compared against, `timepoint` is when, and a numeric
`threshold` needs a stated basis.

**A route made of method names.** Each step declares `input`, `output` and — from the second
step on — at least one declared `depends_on`. A step without them is a paragraph from a
methods section, not a plan.

**A schedule that ignores the calendar.** Phases ending after the declared period, a later
phase ending before an earlier one, or a period declared with no schedule at all, are all
refused: the plan is asserted to fit, not shown to fit.

**Outcomes written separately from objectives.** An expected outcome that names no objective
is the "各写各的" failure — goals and deliverables that never touch.

**A route without an executable governance layer.** Each objective must have a falsifiable
hypothesis/design prediction; each route step must belong to a work package naming method,
data, deliverable and acceptance. `data_plan` records sources/collection/quality/analysis;
The ethics `applicable` field is an explicit boolean. Applicable ethics requires governance fields,
while a false declaration needs its own scope explanation. `pending institutional review`
is honest; an invented approval number is not.

## Runtime: the six steps

Run the same six steps for every case. They keep the deliverable and the audit separate: the
audit checks structure, it never manufactures content.

**Step 0 — read the case.** Read the input case file and the task statement. Copy two things
out before anything else: the case identifier (recorded into the result as-is) and the declared
output contract (the field names the result must carry). Every declared contract field is written
at the **top level** of result.json and listed in `output_contract_fields`; the nested
`output_contract` copy remains for compatibility. Also read the constraints the case states —
period, funding, data conditions, personnel — because the schedule and resource checks are run
against exactly those numbers. When the request is vague about period or funding, ask or record
the gap in limits; do not invent a period, an amount, or applicant evidence.

**Step 1 — route by the shape of the ask.** Match the task wording against the table below
and pick a section. When in doubt, prefer the primary section of this skill.

| task wording (representative) | route | spec essentials |
|-|-|-|
| 开题报告 / 研究计划书：背景、问题、目标、技术路线、阶段计划、风险、预期成果 | research_plan | elements 七块 + period_months + schedule + risks + outcomes |
| 研究计划：目标 + 时间表 + 经费条件内可行 | research_plan | 同上，period_months 与 resource_budget 取案例给定值 |
| 把宽泛方向收敛成 1–3 个可回答的问题并给出考核标准 | research_plan | objectives[]（metric / sample / control / timepoint）+ elements |
| 技术路线拆步骤、标依赖与关键路径 | research_plan | route[]（input / output / depends_on）+ schedule |
| 风险识别：触发信号、影响、备选、决策时点 | research_plan | risks[] 四类四字段 |
| 基金申请书 / grant application 章节稿（含创新点与前期基础） | proposal | elements 七块（rationale…foundation）+ budget；完整评审档再加 grant_profile=nsfc_full 与下列完整字段 |
| 完整基金评审：科学问题属性、创新边界、关键问题、可行性、年度计划、风险伦理、预算逻辑 | proposal | architecture 八层 + science_question + innovations[] + key_questions[] + feasibility + applicant_evidence + outcomes[] + risks[] + ethics + budget[] |
| 论证段落→要素→证据三级映射的改稿 | proposal | paragraphs[] + foundation_items[] |
| 开题初稿成文（正文写作而非结构化要素） | paper_draft | draft + materials + references |
| 无关请求（翻译、泛读、降重） | none | refused as undetermined, never guessed |

**Step 2 — produce the target deliverable first.** Do the actual work: draft the seven
elements, the objectives, the route steps, the schedule phases, the risks, the outcomes —
grounded in the case materials, never fabricated. The audit in later steps checks structure;
it cannot read the case for you, so a hollow spec with a tidy schema is still a failed case.
Keep the deliverable editable (the text of every element goes into the spec verbatim, and any
docx/markdown descriptor the case declares passes through into the result untouched).

**Step 3 — assemble the spec.** One JSON object holding the deliverable, the evidence base and
the contract: the case identifier, the section name from step 1, the seven element blocks, the
objectives / hypotheses / work_packages / route / schedule / risks / outcomes records, the
`data_plan`, explicit `ethics`, the claims with their material or reference and version, the
declared period and resource envelope, and the case's output contract fields copied in as keys
so they can be echoed verbatim into the result. See `examples/spec-plan-contract.json` for
the complete runnable clean baseline, including both objectives and their work-package links.

**Step 4 — audit.** Run the engine once:

```bash
python scripts/secrun.py --spec examples/spec-plan-contract.json --out /app/output
```

Exit codes: `0` clean, `3` review (only low/medium findings), `4` blocked (any high finding),
`5` undetermined (the case could not be run as declared — unreadable spec, non-object spec,
missing or unknown section). Every exit writes a result file; an exit never comes from a
traceback.

**Step 5 — fix findings and rerun.** Each finding names a rule and an item. Fix the draft
(state the threshold basis, declare the dependency, add the decision point), never the audit,
and rerun. Repeat until exit 0 or 3, or until a finding genuinely cannot be resolved — then
leave it and record why in the run's limits, because an honest blocked status beats a
silenced rule.

**Step 6 — merge the result with the real editable artifacts.** A valid `research_plan` run
writes `research_plan.md` (seven elements plus hypotheses, packages, data, ethics and sources),
`plan_matrix.json` (objective↔hypothesis↔route↔package↔outcome links) and
`evidence_matrix.csv` (claim/material/reference/version) before `result.json`; its `artifacts`
index reports only files actually generated. The result file also carries the case identifier
and every declared contract field (case values pass through untouched; audited status, findings
and counts are filled; unknown fields are null with a limits note). Render any docx requested
by the case from `research_plan.md` with the provided Office tool; never invent a docx or PDF
file that was not actually written.

## The spec, field by field (research_plan, the primary route)

```json
{
  "case_id": "demo-plan-001",
  "section": "research_plan",
  "period_months": 18,
  "resource_budget": 40, "resource_needed": 32,
  "materials": [{"id": "M1", "name": "2025-03 coating runs"}],
  "references": [{"key": "doe2020", "title": "Porous coatings", "year": 2020}],
  "elements": {
    "background": {"known": "...", "unknown": "...", "to_test": "...", "text": "..."},
    "problem": {"text": "whether a 42 nm porous coating raises uptake rate three-fold",
                 "falsification": "paired estimate fails the justified direction or threshold"},
    "objectives": {"text": "..."}, "technical_route": {"text": "..."},
    "schedule": {"text": "..."}, "risks": {"text": "..."}, "outcomes": {"text": "..."}
  },
  "objectives": [{"id": "O1", "metric": "uptake rate ratio", "sample": "n = 6 per arm",
                   "control": "uncoated substrate", "timepoint": "24 h",
                   "threshold": 3.0, "threshold_basis": "reported by [doe2020] at 40 nm"}],
  "route": [{"id": "R1", "objective": "O1", "input": "monomer solution",
              "output": "coated substrate", "risk": "pore collapse",
              "fallback": "lower-temperature template removal", "depends_on": []},
             {"id": "R2", "depends_on": ["R1"], "input": "...", "output": "...",
              "risk": "...", "fallback": "...", "objective": "O2"}],
  "schedule": [{"period": "2025-03 to 2025-08", "end_month": 6,
                 "deliverable": "coating protocol and first dataset",
                 "on_critical_path": true}],
  "claims": [{"text": "40 nm coatings raised uptake", "reference": "doe2020",
              "version": "v2.1"}],
  "risks": [{"id": "K1", "type": "method_feasibility", "trigger": "two collapses in one week",
              "impact": "R1 stalls", "fallback": "lower-temperature removal",
              "decision_point": "end of month 2"}],
  "outcomes": [{"id": "W1", "objectives": ["O1"], "kind": "paper",
                "assessment": "rate ratio confirmed by a second operator"}],
  "hypotheses": [{"id": "H1", "objective": "O1", "statement": "42 nm raises ratio to >=3",
                  "test": "paired assay at 24 h", "null_result": "threshold or direction not met"},
                 {"id": "H2", "objective": "O2", "statement": "uniformity supports a controlled test",
                  "test": "profilometry", "null_result": "nonuniformity triggers redesign"}],
  "work_packages": [{"id": "WP1", "title": "coating and assay", "objectives": ["O1", "O2"],
                     "route_steps": ["R1", "R2"], "method": "deposition and paired assay",
                     "data": "M1 and paired rate runs", "deliverable": "protocol and dataset",
                     "acceptance": "O1 evaluated with retained raw data", "start_month": 1, "end_month": 6}],
  "data_plan": {"sources": [{"id": "M1", "version": "2025-03-14"}],
                 "collection_method": "paired measurements", "quality_control": "independent repeat",
                 "analysis": "paired ratio with uncertainty", "data_availability": "raw tables with report"},
  "ethics": {"applicable": false,
             "scope_explanation": "inorganic samples; no people, personal data or animals"},
  "output_contract": {"case_id": "...", "status": "...", "section": "...",
                       "findings": "...", "severity_counts": "..."}
}
```

`period_months`, `resource_budget` and `resource_needed` are the case's own constraints — the
schedule and resource checks are only as honest as these numbers, so take them from the case,
never from imagination. A claim can point at a `material` id or a `reference` key (or both);
whatever it points at must exist, and it must record which `version` was used.

The grant-application variant (`proposal`) keeps its own seven elements — rationale, question,
objectives, content, innovation, technical_route, foundation — plus paragraphs mapped to
elements, a capability-evidence-relation foundation chain with a done / planned status, and a
budget with a justification. See `examples/spec.json`.

## Full grant-review profile (`grant_profile: nsfc_full`)

The organizer's grant cases add a full review structure beyond the legacy seven elements. Set
`grant_profile` (or `review_profile`) to `nsfc_full` only when the task asks for that complete
chapter; legacy seven-element inputs stay valid. The complete explained example is
`examples/spec.json`.

```json
{
  "grant_profile": "nsfc_full",
  "architecture": {"background": "...", "gap": "...", "question": "...",
                   "hypothesis": "...", "objectives": "...", "content": "...",
                   "technical_route": "...", "outcomes": "..."},
  "science_question": {"property": "需求牵引，突破瓶颈", "central_question": "...",
                       "hypothesis": "...", "boundary": "...", "falsifiability": "..."},
  "innovations": [{"id": "I1", "text": "...", "comparison_target": "named work [ref]",
                   "difference": "bounded scientific/technical delta", "why_hard": "...",
                   "feasibility_evidence": "M1", "evidence": "[ref]; M1"}],
  "key_questions": [{"id": "KQ1", "text": "...", "content_ref": "C1",
                     "attribute": "mechanism", "answer_measure": "..."}],
  "feasibility": {"technical": "...", "team": "...", "resource": "...", "time": "...",
                  "preliminary_status": "provided|partial|not_provided",
                  "preliminary_gap": "required when partial/not_provided"},
  "applicant_evidence": {"status": "provided|partial|not_provided", "items": [],
                         "gap_note": "state missing applicant evidence; never invent it"},
  "outcomes": [{"id": "W1", "objectives": ["O1"], "assessment": "..."}],
  "risks": [{"id": "K1", "type": "method_feasibility", "trigger": "...", "impact": "...",
             "fallback": "...", "decision_point": "..."}],
  "ethics": {"applicable": false, "scope_explanation": "why no human/animal/personal data"},
  "budget": [{"item": "consumables", "amount_status": "not_provided", "amount": null,
              "purpose": "which research activity", "basis": "quantity/price basis",
              "justification": "why this line exists"}]
}
```

Contract rules made executable by this profile:

- **立得住**: eight architecture layers are separate; the scientific question carries its
  attribute, hypothesis, boundary and a falsifiable test. A policy slogan cannot satisfy them.
- **说得准**: each innovation names a comparator, a bounded difference, why it is hard and the
  evidence that this team can do it. `首次/国际领先/填补空白`-type absolutes are blocked; generic
  “use advanced methods” differences are flagged weak.
- **对得上**: key questions map to content ids; objectives map to content and route; every
  timeline phase maps to objectives and has a deliverable; every outcome maps back to an objective
  with an assessment criterion.
- **查得到 / 不编造**: foundation items name their owner; applicant evidence is an explicit
  provided/partial/not_provided ledger with a gap note. Missing precedent and missing amounts are
  recorded (`preliminary_gap`, `amount_status=not_provided`), never turned into invented results,
  approvals or currency figures.

External mechanisms implemented here: `https://github.com/crce-ux/grant-diagnosis` contributes
the eight-layer collapse diagnosis, bounded comparative innovation and reviewer-perspective
discipline; `https://github.com/haimingz/NSFC-LaTeX` contributes the annual-template warning
(check the current official guide; the class does not certify current compliance). This package
adds machine-checkable fields, does not copy proposal prose, and does not claim to replace the
current NSFC guide or institutional review.

## Worked example（示例）

Input `examples/spec-plan-contract.json` — the research_plan spec shown above plus a declared
output contract with six fields, one of which is a deliverable descriptor the case itself
carries. Run:

```bash
python scripts/secrun.py --spec examples/spec-plan-contract.json --out /tmp/out
```

Console output（示例，路径随机器不同）:

```json
{"status": "clean", "section": "research_plan", "case_id": "demo-plan-001",
 "findings": [], "wrote": "/tmp/out/result.json"}
```

The written result（示例节选，实跑所得）:

```json
{
  "case_id": "demo-plan-001",
  "status": "clean",
  "section": "research_plan",
  "output_contract": {
    "case_id": "demo-plan-001",
    "status": "clean",
    "section": "research_plan",
    "findings": [],
    "severity_counts": {},
    "deliverable_docx": {"format": "docx", "heading_numbering": "1 / 1.1", "editable": true}
  }
}
```

The deliverable key passed through untouched, the audited keys were filled by the audit, and
the case identifier is recorded — exit 0.

## Output contract of the result

`/app/output/result.json` (written by the engine on every exit path):

| field | content |
|-|-|
| case_id | the case identifier, echoed from the spec or the command line |
| status | clean / review / blocked / undetermined |
| section | the audited section |
| findings[] | one per rule hit: rule, severity, message, and the named item |
| severity_counts | findings by severity |
| checked | the section and the number of records audited |
| limits | what this run could not verify, including any contract field left null |
| artifacts | the actual `research_plan.md`, `plan_matrix.json` and `evidence_matrix.csv` written under the output directory |
| output_contract | compatibility view of every declared contract field: case-carried values pass through, audited keys are filled by the audit, the rest are null with a limits note; the same fields are also at top level |
| output_contract_fields | the exact declared field-name list, so the echo can be checked without re-reading the case |

## Mapping to the required result sections

| 评分要求的字段（原词） | 本 Skill 的交付 |
|-|-|
| 目标产物 | 实际生成的 research_plan.md：七要素 + hypotheses / work_packages / data_plan / ethics + objectives / route / schedule / risks / outcomes；plan_matrix.json 给出目标—假设—路线—工作包—成果闭环；案例原描述符原样直通 |
| 事实与来源映射 | claims[] 每条论断绑定 material 或 reference 并记录 version，引用与材料的存在性由 citation_unknown / material_unknown 核验 |
| 版本与边界 | findings + severity_counts（逐条规则、逐条定位）、limits（不可核验项）、undetermined 拒绝路径（材料缺失时如实报不可判定，绝不补造） |

## Rules

### research_plan (primary)

| rule | severity | what it proves |
|-|-|-|
| `rp.element_missing` | high | a required element of the opening report is absent |
| `rp.element_no_text` | high | an element exists but says nothing |
| `rp.background_gap_incomplete` | high | the background does not split 已知 / 未知 / 待验证 |
| `rp.period_undeclared` | high | no period declared, so schedule fit cannot be judged |
| `rp.schedule_missing` | high | a period is declared but no schedule phases are supplied |
| `rp.claim_no_citation` | high | a claim is tied to neither a material nor a reference |
| `rp.material_unknown` | high | a claim points at a material that is not in the index |
| `rp.citation_unknown` | high | a claim cites a reference that is not in the list |
| `rp.claim_no_version` | medium | a claim records no source version |
| `rp.objectives_missing` | high | no assessable aim |
| `rp.objective_no_criteria` | high | metric / sample / control / timepoint incomplete |
| `rp.threshold_no_basis` | high | a numeric threshold with no stated basis |
| `rp.route_no_io` | high | a step with no input or output |
| `rp.route_no_dependency` | medium | a later step declares no dependency |
| `rp.route_dependency_unknown` | high | a step depends on a step that does not exist |
| `rp.schedule_exceeds_period` | high | work scheduled beyond the available period |
| `rp.schedule_not_monotonic` | medium | a later phase ends before an earlier one |
| `rp.schedule_unreadable` | medium | a phase has no numeric end month |
| `rp.milestone_no_deliverable` | high | a phase produces nothing identifiable |
| `rp.critical_path_unmarked` | medium | no phase marked on the critical path |
| `rp.risks_missing` | high | no risk identified |
| `rp.risk_type_missing` | high | a risk is not classified |
| `rp.risk_type_unknown` | medium | a risk type outside the four |
| `rp.risk_no_trigger` | medium | no trigger signal |
| `rp.risk_no_impact` | medium | no impact stated |
| `rp.risk_no_fallback` | high | no fallback |
| `rp.risk_no_decision_point` | medium | no decision point |
| `rp.risk_type_uncovered` | medium | data_access or method_feasibility never addressed |
| `rp.outcomes_missing` | high | no expected outcome |
| `rp.outcome_no_assessment` | high | an outcome says no how it will be judged |
| `rp.outcome_unmapped` | high | an outcome names no (existing) objective |
| `rp.outcome_kind_unknown` | low | a kind outside paper/dataset/code/method/thesis/prototype |
| `rp.resource_exceeds_budget` | high | resource need exceeds the envelope |
| `rp.resource_unreadable` | medium | resource figures not numeric |
| `rp.problem_not_falsifiable` | medium | no result that could falsify or reject the bounded problem |
| `rp.hypothesis_missing_for_objective` | high | an objective lacks a hypothesis/design prediction |
| `rp.hypothesis_incomplete` | high | missing statement/test/null_result/objective |
| `rp.hypothesis_unknown_objective` | high | hypothesis points at a missing objective |
| `rp.work_packages_missing` | high | no work package joins aims, execution and acceptance |
| `rp.work_package_incomplete` | high | missing objectives/route/method/data/deliverable/acceptance |
| `rp.work_package_ref_unknown` | high | package points at missing objective or route id |
| `rp.route_not_in_work_package` | high | route step executes in no declared package |
| `rp.work_package_schedule_invalid` | high | package interval unreadable, inverted or beyond total period |
| `rp.route_dependency_cycle` | high | no executable start order in route dependencies |
| `rp.data_plan_missing` | high | no data plan |
| `rp.data_plan_incomplete` | high | sources/collection/quality/analysis incomplete |
| `rp.ethics_undeclared` | medium | applicability or non-applicability basis left implicit |
| `rp.ethics_incomplete` | high | applicable ethics lacks approval status/consent/privacy/retention/oversight |
| `rp.ethics_data_mismatch` | high | sensitive data is declared but ethics applicability is false/missing |

### proposal (grant-application variant)

| rule | severity | what it proves |
|-|-|-|
| `prop.element_missing` | high | a required element is absent |
| `prop.element_no_text` | high | an element has no text |
| `prop.element_no_evidence` | high | a claiming element has no evidence pointer |
| `prop.paragraph_no_element` | medium | a paragraph is not assigned to an element |
| `prop.paragraph_no_evidence` | high | the three-level mapping is broken |
| `prop.paragraph_element_unknown` | low | an element name outside the seven |
| `prop.status_unlabelled` | high | done and planned are indistinguishable |
| `prop.foundation_no_capability` | high | the foundation names no capability |
| `prop.foundation_no_evidence` | high | the foundation names no evidence |
| `prop.foundation_no_relation` | high | no link to this study |
| `prop.question_too_broad` | high | the question has no boundary |
| `prop.objectives_missing` | high | no assessable aims |
| `prop.aim_without_measure` | high | completion cannot be judged |
| `prop.aim_without_outcome` | medium | no difference stated |
| `prop.objective_unmapped` | high | aim and content not in correspondence |
| `prop.objective_content_unknown` | medium | points at a missing content item |
| `prop.objective_no_route` | high | no plan for how it will be achieved |
| `prop.route_no_io` | high | a step with no input or output |
| `prop.route_no_risk` | medium | feasibility asserted, not analysed |
| `prop.route_no_fallback` | medium | a failed step stops the project |
| `prop.milestone_missing` | medium | progress unmeasurable |
| `prop.budget_unjustified` | medium | no basis for the budget |
| `prop.budget_line_unjustified` | medium | a line item with no reason |
| `prop.field_too_thin` | low | an argumentative element too short to argue |

### proposal full profile (declared-only)

| rule | severity | what it proves |
|-|-|-|
| `prop.architecture_missing` / `prop.architecture_layer_missing` | high | the eight layers are supplied as separate, non-empty fields |
| `prop.science_question_missing` | high | the scientific question is structured |
| `prop.science_property_missing` | high | its funding/scientific-problem attribute is stated |
| `prop.science_question_no_central` | high | one central question exists |
| `prop.science_question_no_hypothesis` | high | a testable hypothesis exists |
| `prop.science_question_no_boundary` | high | scope boundaries exist |
| `prop.science_question_no_falsifiability` | high | the observation that would falsify it is stated |
| `prop.innovation_items_missing` | high | innovation is decomposed into items |
| `prop.innovation_no_comparator` | high | a concrete prior work/comparator is named |
| `prop.innovation_no_difference` | high | the bounded scientific delta is stated |
| `prop.innovation_no_difficulty` | high | why the step is hard is stated |
| `prop.innovation_no_feasibility` | high | execution evidence exists |
| `prop.innovation_no_evidence` | high | the comparative claim has a traceable source |
| `prop.innovation_overclaimed` | high | unverifiable absolute novelty language is blocked |
| `prop.innovation_weak` | medium | generic “advanced method” delta is flagged |
| `prop.key_questions_missing` | high | key scientific questions exist |
| `prop.key_question_no_text` | high | a key question has content |
| `prop.key_question_unmapped` | high | it maps to a content item |
| `prop.key_question_no_attribute` | high | its question type/attribute is declared |
| `prop.key_question_no_measure` | high | it has an answer criterion |
| `prop.key_question_content_unknown` | high | its content reference exists |
| `prop.content_item_no_text` | high | a content item is answerable text, not just an id |
| `prop.feasibility_missing` | high | a structured feasibility account exists |
| `prop.feasibility_dimension_missing` | high | technical/team/resource/time are all stated |
| `prop.feasibility_preliminary_unaccounted` | high | missing preliminary evidence is declared with a gap/alternative |
| `prop.applicant_evidence_undeclared` | high | applicant-owned evidence is explicitly separated |
| `prop.applicant_evidence_gap_note_missing` | high | partial/missing applicant evidence is recorded as a gap |
| `prop.applicant_evidence_items_missing` | high | “provided” names actual evidence items |
| `prop.applicant_item_no_capability` | high | an applicant item states the capability |
| `prop.applicant_item_no_source` | high | an applicant item names its source |
| `prop.applicant_item_no_relation` | high | it links to this study |
| `prop.applicant_item_no_completion` | high | done vs planned is explicit |
| `prop.foundation_owner_missing` | high | external/team foundation evidence names its owner |
| `prop.timeline_missing` | high | an annual/phase plan exists |
| `prop.timeline_period_missing` | high | each phase names its period |
| `prop.timeline_deliverable_missing` | high | each phase has a deliverable |
| `prop.timeline_objective_unmapped` | high | each phase serves an objective |
| `prop.timeline_objective_unknown` | high | phase objective ids exist |
| `prop.outcomes_missing` | high | expected outcomes exist |
| `prop.outcome_unmapped` | high | each outcome delivers an objective |
| `prop.outcome_objective_unknown` | high | outcome objective ids exist |
| `prop.outcome_no_assessment` | high | each outcome has an assessment criterion |
| `prop.risks_missing` | high | risks are classified |
| `prop.risk_type_unknown` | medium | risk type is one of the four |
| `prop.risk_field_missing` | high | trigger/impact/fallback/decision point all exist |
| `prop.ethics_undeclared` | high | ethics applicability is explicit, with scope reason for false |
| `prop.ethics_incomplete` | high | applicable ethics governance is complete without invented approvals |
| `prop.budget_logic_missing` | high | costed activity logic exists |
| `prop.budget_purpose_missing` | high | each line names its research activity |
| `prop.budget_basis_missing` | high | each line has a quantity/price basis |
| `prop.budget_amount_status_missing` | high | provided vs not_provided is explicit |
| `prop.budget_amount_missing` | high | a “provided” amount is actually present |

### Input hygiene and refusal

| rule | severity | what it proves |
|-|-|-|
| `spec.slot_malformed` | medium | a spec slot holds non-object entries (or is not a list); the malformed entries are named and skipped |
| `audit.no_section` | high | the case could not be run as declared: no or unknown section, a non-object spec, or a spec that is not readable JSON — refused with exit 5, never a crash |

## Exception handling

| situation | exit | what happens / what to do |
|-|-|-|
| spec file missing or unreadable | 5 | refusal written with audit.no_section; re-check the path, rerun |
| spec is valid JSON but not an object (array, string, number) | 5 | refusal; wrap the payload in one object and rerun |
| section key missing, empty or not a string | 5 | refusal; declare the section from the routing table |
| section name unknown (typo or wrong level) | 5 | refusal; pick a route from the table |
| elements is a list or string instead of an object | 4 | every element reads as absent plus a slot_malformed note; supply an object keyed by element name |
| an element block is a bare string instead of an object | 4 | that block reads as absent plus a slot_malformed note; give it text and evidence fields |
| a list slot (paragraphs / hypotheses / work_packages / schedule / risks / outcomes / claims / timeline / budget) holds non-object entries | 4 | the entries are named and skipped (slot_malformed); supply objects |
| ethics.applicable=true but approval is only pending | 3/4 | pending is allowed and must be stated as such; approval status plus consent/privacy/retention/oversight must still be supplied; never invent an approval number |
| ethics.applicable=false | clean if explained | supply scope_explanation proving why no human/animal/personal-data protocol applies; a bare false without explanation is review |
| a work package interval is inverted, unreadable or after period_months | 4 | correct the actual plan or honestly narrow scope; do not move the total-period number |
| route dependencies form a cycle | 4 | remove/reorder dependencies so an executable DAG exists; identifying valid ids alone is insufficient |
| objectives slot is a string or number instead of a list | 4 | degrades to objectives_missing; supply a list of objects |
| a schedule phase carries a non-numeric end month | 3 | schedule_unreadable; give the month number the phase ends in |
| period and resource figures are non-numeric | 3 | resource_unreadable; supply the case's own numbers |
| an objective has a threshold but no basis | 4 | threshold_no_basis; state where the threshold comes from |
| an outcome references an objective id that does not exist | 4 | outcome_unmapped; align the ids |
| extremely long strings anywhere | 0–5 | accepted; messages truncate to ~100 chars, nothing crashes |
| empty strings instead of missing keys | 3/4 | an empty string is treated as absent and fired on; write the content |
| CJK text in any field | 0–5 | accepted; 已知 / 未知 / 待验证 and broad-question word lists cover Chinese |
| rerun with an unchanged spec | — | byte-identical result; the audit is deterministic |

## Limits

- **Measure quality is not judged.** The audit checks that a metric, control, sample and
  timepoint exist and that a threshold carries a stated basis — not that the threshold is the
  right one.
- **Route feasibility is not assessed.** Input / output / dependency / risk / fallback must be
  present; whether the risk is the real one is a reader's call.
- **Schedule arithmetic is calendar-agnostic.** end_month is compared against period_months as
  plain numbers; a plan expressed in quarters must still declare month numbers.
- **Broadness detection is a word list** (all / every / comprehensive / 全面 / 所有). A vague
  question phrased without them passes.
- **Claim support is not semantically verified.** A claim bound to a real reference with a
  version passes; whether that reference actually supports it is the reviewer's judgement.
- **The first route step is exempt from the dependency rule** — something has to come first.
- **No funder template is enforced.** Element names are the seven the task lists, per variant.
  `nsfc_full` is an organizer/controlled-review structure, not the current annual NSFC policy;
  verify the year's official guide, forms and AI-use rules before a real submission.
- **Full-profile depth is structural.** Comparator presence, bounded difference, eight layers and
  budget arithmetic are checkable; whether the comparator is the closest work and whether the
  hypothesis is true remains scholarly judgement. Missing applicant evidence/amounts are reported,
  not filled.
- **It does not read PDFs or docx.** Extraction from the case materials is a separate step;
  this audits and renders the structured plan that comes out of it.
- **Ethics presence is not legal approval.** The run verifies applicability and governance fields,
  not whether an institution approved them. A pending status must remain pending.
- **Work-package completeness is structural.** `owner`, `start_month`, `end_month` and `acceptance` are
  editable planning fields; the audit does not prove staff availability or scientific feasibility.
- **Rendered Markdown echoes supplied claims.** `plan_matrix.json` proves cross-links, not that a
  hypothesis is true or that sources actually support an assertion; those require the cited material.

## Failure handling

| symptom | what to do |
|-|-|
| `rp.background_gap_incomplete` | write the three sentences: what is known, what is unknown, what this project will test |
| `rp.period_undeclared` | take the period from the case constraints; if the case states none, say so in limits |
| `rp.schedule_missing` | lay the phases on the calendar the case gives |
| `rp.schedule_exceeds_period` | cut scope or state the overrun honestly — do not shrink the numbers |
| `rp.route_no_dependency` | say which earlier step each later step waits for |
| `rp.objective_no_criteria` | give metric, sample, control and timepoint |
| `rp.threshold_no_basis` | cite the prior work or preliminary data the threshold comes from |
| `rp.outcome_unmapped` | name the objective each outcome delivers, or fix the id |
| `rp.claim_no_citation` | bind the claim to a material or a reference |
| `rp.claim_no_version` | record which version of the source was used |
| `rp.risk_no_fallback` | say what happens when the risk triggers |
| `rp.risk_type_uncovered` | address data access and method feasibility at minimum |
| `rp.resource_exceeds_budget` | re-plan inside the envelope, or flag the shortfall to the reviewer |
| `prop.status_unlabelled` | mark each preliminary result done / in progress / planned |
| `prop.foundation_no_relation` | say how the capability bears on this study |
| `prop.question_too_broad` | narrow it to something one project can answer |
| `audit.no_section` (exit 5) | the case could not be run as declared: no or unknown section, or the spec file is not readable JSON — refused, never a crash |

## Verification

```bash
python scripts/bench_plan.py       # 45 scenarios: opening-report + hypothesis/package/data/ethics + repaired twins
python scripts/bench_proposal.py   # 37 scenarios: legacy rules + full-profile layers/links/budget/CJK guard
python scripts/bench_sections.py   # 51 scenarios: cross-section regression plus false-positive guards
```

All pass in full on this machine. The clean baseline in each must report nothing, so a
detector cannot pass by flagging everything. Rules added against the brief's four questions
each carry a defect scenario and a repaired-twin guard.

## Requirements

Python 3.9+（3.14 实测）。纯标准库实现，无第三方依赖。

## 创新增益

本 Skill 相比通用 Agent 直接撰写开题报告的核心新增能力（全部为引擎真实运行的机制，bench 覆盖）：

1. **缺口三段式强制**：背景必须显式拆出已知 / 未知 / 待验证（known / unknown / to_test），否则判为文献罗列——把"立得住"从写作直觉变成机械可查的字段约束。
2. **目标四要素与阈值依据**：每个目标强制携带 metric / sample / control / timepoint，数值阈值必须声明 threshold_basis——"可考核"落到字段级。
3. **计划-周期相容性校验**：schedule 的 end_month 逐相与 period_months 比较（超期报、倒挂报、有周期无计划也报），并强制 deliverable 与关键路径标注——"排得开"可复算。
4. **依赖声明检查**：第二个及之后的路线步骤必须声明 depends_on 且引用必须存在——前后依赖从默认隐含变成显式契约，可并行的部分由此可判定。
5. **成果-目标映射**：预期成果必须指回 objectives 中的既有 id，杜绝"目标、成果各写各的"——"对得上"在数据层面闭环。
6. **风险分类学**：四类（数据获取 / 方法可行性 / 进度 / 伦理合规）分类 + 每条风险四字段（trigger / impact / fallback / decision_point）+ 两大核心类别覆盖强制——风险条目可逐字段评分。
7. **论断可追溯三键**：每条关键论断绑定 material 或 reference 并记录 version，引用与材料存在性由引擎核验——"说得清"可逐条回溯。
8. **契约直通的 result.json 与崩溃免疫**：case_id 与 output_contract 全字段回填（案例自带值原样直通、审计键由审计填写、其余置 null 并写入 limits）；类型错位一律降级为发现项，退出码只有 0/3/4/5，绝不以 traceback 收场。
9. **目标—假设—工作包闭环**：每个 objective 均有 statement/test/null_result，route step 必须属于 work_package；包内 method/data/deliverable/acceptance 与目标 ID 同步，依赖有向图额外查环，消除“要素齐全却无法开工”。
10. **数据—伦理双线治理**：data_plan 拆解 sources/collection_method/quality_control/analysis；ethics 显式声明适用性，涉及人/个人数据/动物即与 false 冲突，适用时保留 pending 而非补造批准号。
11. **真实可编辑交付**：除 JSON 审计外，实际生成结构化写作本体 research_plan.md、链接矩阵 plan_matrix.json 和证据 CSV，`artifacts` 仅登记磁盘上真实生成的文件。
12. **完整基金评审档**：八层分离、科学问题属性、创新与具体已有工作的差异/难度/可行性、关键问题—内容—目标—路线—时间—成果闭环、证据 owner/申请人缺口、伦理与预算逻辑全部机械可查；不把外部成果冒充申请人成果，不把缺金额补成数字。
13. **顶层契约直通**：case_id 与 output_contract 全字段既保留兼容视图，又逐字写到 result.json 顶层，并给出 output_contract_fields；拒绝路径也保留相同字段骨架。

bench 目录下的场景（clean 基线零发现 + 缺陷-修复孪生守卫）是上述能力的回归证据。

## 生态贡献

1. **SKILL.md**：用途、适用条件、六步调用方式、路由决策表、输入输出契约、异常处置表、限制与自查方法齐备，且文档中的规则 id 与引擎逐一对得上。
2. **scripts/**：纯标准库（Python 3.9+，3.14 实测），模块可独立导入；本包为独立副本，不依赖其他包的文件。
3. **examples/spec.json 与 examples/spec-plan-contract.json**：最小调用示例与带 case_id + output_contract 回填的完整示例，示意输出标注为示例、实跑所得。
4. **bench_plan.py**：45 个场景，覆盖 research_plan 全部规则、可证伪性/工作包/数据/伦理和修复孪生守卫；report_plan.json 为可复跑证据。
5. **bench_proposal.py**：37 个场景，覆盖 legacy 七要素与 nsfc_full 八层/科学问题/创新比较/申请人证据/预算逻辑/CJK 误报守卫，clean 基线必须零发现。
6. **bench_sections.py**：51 个跨 section 回归场景，防误报守卫覆盖中文与类型错位输入。
7. **完整计划模板**：elements / objectives / hypotheses / work_packages / data_plan / ethics / route / schedule / risks / outcomes 结构可迁移到其他课题；实跑另交付 research_plan.md 与两个矩阵，避免空有检查清单。
8. **规则 id 稳定词汇表**：rp.* 与 prop.* 前缀稳定命名、语义与严重度文档化，可作为同类开题与基金写作任务的共享检查词汇。
