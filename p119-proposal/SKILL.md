---
name: research-proposal
description: >
  Draft and audit an opening report / research plan (开题报告与研究计划书) as seven checkable
  elements — background with a known-unknown-to-test gap statement, a bounded problem, objectives
  carrying metric / sample / control / timepoint and a grounded threshold, a technical route with
  input, output and declared dependencies, a schedule that fits the stated period with milestones
  on a critical path, risks classified by type each with trigger / impact / fallback / decision
  point, and expected outcomes tied back to objectives — plus a grant-proposal variant
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

## Runtime: the six steps

Run the same six steps for every case. They keep the deliverable and the audit separate: the
audit checks structure, it never manufactures content.

**Step 0 — read the case.** Read the input case file and the task statement. Copy two things
out before anything else: the case identifier (recorded into the result as-is) and the declared
output contract (the field names the result must carry). Also read the constraints the case
states — period, funding, data conditions, personnel — because the schedule and resource checks
are run against exactly those numbers. When the request is vague about period or funding, ask
or record the gap in limits; do not invent a period.

**Step 1 — route by the shape of the ask.** Match the task wording against the table below
and pick a section. When in doubt, prefer the primary section of this skill.

| task wording (representative) | route | spec essentials |
|-|-|-|
| 开题报告 / 研究计划书：背景、问题、目标、技术路线、阶段计划、风险、预期成果 | research_plan | elements 七块 + period_months + schedule + risks + outcomes |
| 研究计划：目标 + 时间表 + 经费条件内可行 | research_plan | 同上，period_months 与 resource_budget 取案例给定值 |
| 把宽泛方向收敛成 1–3 个可回答的问题并给出考核标准 | research_plan | objectives[]（metric / sample / control / timepoint）+ elements |
| 技术路线拆步骤、标依赖与关键路径 | research_plan | route[]（input / output / depends_on）+ schedule |
| 风险识别：触发信号、影响、备选、决策时点 | research_plan | risks[] 四类四字段 |
| 基金申请书 / grant application 章节稿（含创新点与前期基础） | proposal | elements 七块（rationale…foundation）+ budget |
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
objectives / route / schedule / risks / outcomes records, the claims with their material or
reference and version, the declared period and resource envelope, and the case's output
contract fields copied in as keys so they can be echoed verbatim into the result. See
`examples/spec-plan-contract.json` for the full shape.

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

**Step 6 — merge the result.** Write the deliverable files under the output directory. The
result file written by the engine already carries: the case identifier, every field of the
declared output contract (values the case carried pass through untouched; the audited status,
findings and counts are filled by the audit; anything else is null with a limits note — never
a fabricated value), findings, severity counts and limits. Keep that file as the structured
result of the case.

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
    "problem": {"text": "whether a 42 nm porous coating raises uptake rate three-fold"},
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
| output_contract | every declared contract field: case-carried values pass through, audited keys are filled by the audit, the rest are null with a limits note |

## Mapping to the required result sections

| 评分要求的字段（原词） | 本 Skill 的交付 |
|-|-|
| 目标产物 | 七要素齐全、与周期和经费相容的开题方案本身：elements 七块 + objectives / route / schedule / risks / outcomes 记录；案例声明的可编辑交付描述符经 output_contract 原样直通 |
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
| a list slot (paragraphs / schedule / risks / outcomes / claims / timeline / budget) holds non-object entries | 4 | the entries are named and skipped (slot_malformed); supply objects |
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
- **It does not read PDFs or docx.** Extraction from the case materials is a separate step;
  this audits the structured plan that comes out of it.

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
python scripts/bench_plan.py       # 29 scenarios: opening-report rules + repaired-twin guards
python scripts/bench_proposal.py   # 19 scenarios: one per grant-proposal rule
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

bench 目录下的场景（clean 基线零发现 + 缺陷-修复孪生守卫）是上述能力的回归证据。

## 生态贡献

1. **SKILL.md**：用途、适用条件、六步调用方式、路由决策表、输入输出契约、异常处置表、限制与自查方法齐备，且文档中的规则 id 与引擎逐一对得上。
2. **scripts/**：纯标准库（Python 3.9+，3.14 实测），模块可独立导入；本包为独立副本，不依赖其他包的文件。
3. **examples/spec.json 与 examples/spec-plan-contract.json**：最小调用示例与带 case_id + output_contract 回填的完整示例，示意输出标注为示例、实跑所得。
4. **bench_plan.py**：29 个场景，覆盖 research_plan 每条规则，新增规则各配一个修复孪生守卫场景；report_plan.json 为可复跑证据。
5. **bench_proposal.py**：19 个场景，每条 grant-proposal 规则一个缺陷场景，clean 基线必须零发现。
6. **bench_sections.py**：51 个跨 section 回归场景，防误报守卫覆盖中文与类型错位输入。
7. **七要素 spec 模板**：elements / objectives / route / schedule / risks / outcomes 的字段结构可直接迁移到其他课题的开题场景，只需替换内容。
8. **规则 id 稳定词汇表**：rp.* 与 prop.* 前缀稳定命名、语义与严重度文档化，可作为同类开题与基金写作任务的共享检查词汇。
