---
name: research-plan
description: >
  Audit an opening report or research plan against its own seven elements — background,
  problem, objectives, technical route, schedule, risks, expected outcomes — and against the
  period and resources it was given. Requires the background to separate known from unknown
  and testable, objectives to carry metric/sample/control/timepoint with a grounded threshold,
  every claim to record material, reference and version, schedule phases to deliver something
  inside the available months, risks to be classified with trigger, impact, fallback and a
  decision point, and outcomes to say how they will be judged. Use when a task asks for a
  research proposal, thesis opening report, or project plan.
---

# research-plan

This is a different document from a grant application, and checking it with a grant's rubric
would test the wrong things. Its elements are:

**background · problem · objectives · technical route · schedule · risks · expected outcomes**

plus the two constraints that decide whether the plan is executable at all: the **period** it is
given, and the **resources** it is given.

## The six failures this exists to catch

**A background that is a literature list.** It must separate what is *known* from what is
*unknown* from what this project will *test*. Without the three parts there is no gap, only
reading.

**A threshold with no basis.** "Rate ratio ≥ 3" passes or fails a student, so the number needs a
reason — a pilot run, a field convention, a prior study.

**A schedule that does not fit the period.** 24 months of work in an 18-month programme is not
an optimistic plan, it is an undeliverable one. Phases also need a deliverable each, and at
least one phase must be marked as the critical path or a delay cannot be traced.

**A risk with no decision point.** "We will monitor the vendor" is not a fallback. Each risk
needs a **trigger signal**, an **impact**, a **fallback** and a **decision point** — the moment
at which the fallback is taken.

**An expected outcome with no assessment.** "A paper will be published" is not assessable;
"submitted to a peer-reviewed journal" is.

**A claim with no version.** A judgement drawn from a dataset must record which version, or the
next person cannot reproduce the judgement.

## Workflow

### 1. Write the seven elements and the two envelopes

```json
{
  "section": "research_plan",
  "period_months": 24,
  "resource_budget": 100.0,
  "resource_needed": 80.0,
  "elements": {
    "background": {"text": "surface-area limitation",
                   "known": "uptake is surface limited",
                   "unknown": "whether a 42 nm coating changes the rate",
                   "to_test": "rate under paired controls"},
    "problem": {"text": "the rate is the bottleneck"},
    "objectives": {"text": "two measurable objectives"},
    "technical_route": {"text": "three steps"},
    "schedule": {"text": "four quarters"},
    "risks": {"text": "classified risks"},
    "outcomes": {"text": "two assessable outcomes"}
  },
  "claims": [{"text": "uptake is surface limited", "material": "M1", "version": "2024-05"}],
  "objectives": [{"id": "O1", "metric": "rate ratio", "sample": "n=6 per arm",
                  "control": "uncoated", "timepoint": "week 8",
                  "threshold": 3.0, "threshold_basis": "pilot run M1 showed 2.8"}],
  "route": [{"id": "R1", "input": "monomer solution", "output": "coated sample"},
            {"id": "R2", "input": "coated sample", "output": "rate curve",
             "depends_on": ["R1"]}],
  "schedule": [{"period": "Q1", "end_month": 6, "deliverable": "coating built",
                "on_critical_path": true}],
  "risks": [{"id": "K1", "type": "data_access", "trigger": "vendor delay over 2 weeks",
             "impact": "Q1 slips", "fallback": "use in-house monomer",
             "decision_point": "week 3 of Q1"}],
  "outcomes": [{"id": "P1", "kind": "paper",
                "assessment": "submitted to a peer-reviewed journal"}]
}
```

`risks[].type` is `data_access`, `method_feasibility`, `schedule` or `ethics_compliance`.

### 2. Run it

```bash
python scripts/secrun.py --spec spec.json --section research_plan --out /app/output
```

Exit codes: `0` clean, `3` review, `4` blocked.

## Rules

### Elements and background

| rule | severity | what it proves |
|-|-|-|

### Period, resources, claims

| rule | severity | what it proves |
|-|-|-|

### Objectives

| rule | severity | what it proves |
|-|-|-|

### Route and schedule

| rule | severity | what it proves |
|-|-|-|

### Risks and outcomes

## Output contract

`/app/output/result.json`: `status`, `section`, `findings[]` (with element, objective, step,
risk, outcome), `severity_counts`, `checked`, `limits`.


|-|-|
| `long.action_no_status` | medium |
| `long.appendix_missing` | medium |
| `long.argument_element_missing` | high |
| `long.authorship_undeclared` | medium |
| `long.change_impact_untraced` | medium |
| `long.change_no_reason` | medium |
| `long.chapter_no_question` | medium |
| `long.chapter_not_in_outline` | medium |
| `long.citation_conclusion_mismatch` | high |
| `long.citation_unknown` | high |
| `long.claim_no_citation` | high |
| `long.conclusion_contradiction` | high |
| `long.dangling_crossref` | high  |
| `long.definition_unused` | medium |
| `long.duplicate_definition` | medium |
| `long.feedback_not_decomposed` | high |
| `long.figure_list_missing` | medium |
| `long.figure_numbering_gap` | medium |
| `long.figure_ref_unknown` | high |
| `long.no_chapter_changelog` | medium |
| `long.no_chapters` | high |
| `long.numbering_gap` | high |
| `long.numbering_unreadable` | medium |
| `long.outline_item_unwritten` | high |
| `long.questionable_citation` | medium |
| `long.reference_section_missing` | medium |
| `long.symbol_table_missing` | medium |
| `long.term_variant_declared` | low |
| `long.terminology_missing` | high |
| `long.toc_incomplete` | medium |
| `long.word_budget_off` | medium |
| `long.word_budget_unmeasured` | low |

## Limits

- **Threshold bases are declared, not judged.** The audit requires a reason; whether the pilot
  run justifies 3.0 is a reader's call.
- **Schedule compatibility is arithmetic** on `end_month` against `period_months`. Overlapping or
  under-specified phases are not modelled.
- **Risk quality is presence-checked.** A trigger that will never fire still passes.
- **Resource envelope is a single number.** Mixed units (money, time, compute) are not separated.
- **Outcome assessment is a string.** Its rigour is not scored.
- **No funder or school template is enforced.** The seven elements are the ones this task lists.

## Failure handling

| `audit.no_section` | high | the case could not be run as declared: no or unknown section, or the spec file is not readable JSON — refused with exit 5, never a crash |

| symptom | what to do |
|-|-|
| `background_gap_incomplete` | write the known / unknown / to-test triple |
| `threshold_no_basis` | cite the pilot, convention or prior work behind the number |
| `schedule_exceeds_period` | cut scope or extend the plan within the period |
| `risk_no_fallback` | state what you do if it fires, and when you decide |
| `risk_type_uncovered` | address data access and method feasibility explicitly |
| `outcome_no_assessment` | say how the outcome will be judged |
| `claim_no_version` | record the dataset or document version |

## Verification

```bash
python scripts/bench_plan.py      # 26 scenarios: one per rule
python scripts/bench_sections.py  # 45 scenarios: cross-section regression plus false-positive guards
```

Both pass in full on this machine. The clean baseline in each must report nothing.
## Requirements

Python 3.9+（3.14 实测）。纯标准库实现，无第三方依赖。

## 创新增益

本 Skill 相比通用 Agent 的核心新增能力：

1. **规则优先级库**：每条修改有规则 id、优先级、适用条件和理由，两个规则冲突时由优先级决定胜者且双方都留痕——通用 Agent 无法自证规则一致性。
2. **幂等二遍检查**：同一规则跑两遍，第二遍必须零改动——如果仍有改动说明规则间存在冲突，这是一个可计算的 self-check。
3. **逐条变更台账**：每个值的修改记录规则/行/列/原值/新值/理由，审计者可以逐条复核或撤销任何单条修改。

bench 目录下的 plan 是上述能力的回归证据（见 Verification 节 场景，clean 基线必须零发现）。

## 生态贡献

- **SKILL.md** 包含用途、适用条件、调用方式、输入输出、异常处理、限制和自查方法
- **scripts/** 纯标准库可独立导入，规则库可通过 spec 配置扩展
- **examples/** 提供最小调用示例和示意输出
- **bench/** 回归套件可独立复跑验证

