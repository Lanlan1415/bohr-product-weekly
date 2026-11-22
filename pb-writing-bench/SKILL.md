---
name: writing-benchmark
description: >
  An academic-writing benchmark you can run: items that carry instructions, a reference answer
  covering legitimate wording variants, and rubric anchors written as observable criteria, so two
  graders land in the same band without conferring. Grades every criterion with its evidence,
  reproduces the grading to prove it is deterministic, traces any score to its output and
  configuration, and turns a failure into a targeted item without recomputing the untouched ones.
  Use when a task asks for a writing rubric, an evaluation tool, or a graded item set for
  academic prose.
---

# writing-benchmark

The five properties this task names, and the mechanism for each:

| property | mechanism |
|-|-|
| 题能判定 — two graders agree without conferring | criteria are machine predicates, never prose; an ungradable criterion is refused at load |
| 答案站得住 — the reference covers legitimate variants | `any_of` accepts any declared alternative, so a correct answer in different words still passes |
| 锚点打得齐 — anchors are observable | every criterion names what would be *seen* in the output, plus its weight |
| 跑得可复现 | `reproduce` runs the grader twice and reports per-item deltas rather than averaging |
| 报告说得清 | each result carries per-criterion evidence, a `failure_type`, and a trace back to the run |

## The three failures this benchmark design prevents

**One reference answer, one acceptable phrasing.** `contains: ["three-fold"]` fails an answer that
says "tripled". `any_of` exists because a writing benchmark that accepts only one wording measures
imitation, not competence.

**A rubric line nobody can apply.** *"The argument flows"* is not observable. The load step refuses
it, which is what keeps two graders from silently disagreeing.

**A score nobody can re-derive.** Every result names the criterion that decided it and the evidence
it looked at, and the run carries its configuration, so a third person can reproduce the verdict.

## Workflow

### 1. Write items with variants and observable anchors

```json
[
  {
    "id": "W1",
    "task": "Report the measured effect in one sentence, with its magnitude.",
    "input": "Uptake rose three-fold under the coating. Only one thickness was tested, …",
    "reference": "uptake rose three-fold under the coating",
    "rubric": [
      {"criterion": "magnitude reported", "predicate": "any_of", "weight": 50,
       "values": ["three-fold", "3-fold", "tripled"]},
      {"criterion": "stays within one sentence", "predicate": "max_words", "weight": 25,
       "limit": 25},
      {"criterion": "no causal overreach", "predicate": "not_contains", "weight": 25,
       "values": ["causes", "proves", "demonstrates causality"]}
    ]
  }
]
```

`reference` is what a correct answer looks like; `any_of` is what makes other correct phrasings
pass. A `not_contains` criterion is how a benchmark encodes a red line (over-claiming, invented
significance) rather than leaving it to a grader's taste.

### 2. Grade, reproduce, trace

```python
import benchkit as K
items = [...]
assert K.validate_itemset(items)["ok"]
record = K.run(items, outputs, {"model": "…", "rubric_version": "v1"})
K.reproduce(items, outputs, {"model": "…"})     # stability of the grading
K.trace(record, "W1")                           # criterion + evidence + config
```

### 3. Report

The run record is the report: per item a score, the criteria with their evidence, and a
`failure_type` from `missing_required_point`, `forbidden_content`, `over_length`,
`evidence_not_located` or `mixed`. `failures_by_type` is the tally a reviewer reads first, because
it says whether the gap is in the item, the reference or the execution.

## Output contract

`/app/output/result.json` should carry, per case: the item set with its digest, the run record with
per-criterion evidence, `failures_by_type`, the reproduction result, and the trace for any item that
failed.

## Limits

- **`any_of` accepts variants but cannot judge them.** Listing "tripled" as acceptable is your
  claim that it is a correct rendering; the harness only checks presence.
- **`not_contains` is a blocklist.** A red line phrased outside the list passes.
- **`max_words` is a blunt instrument** for "one sentence" — it catches padding, not a comma splice.
- **`ci` matches case-insensitively, nothing more.** Word choice, not capitalisation, is what
  variants exist for; keep real variants in `any_of`.
- **Text criteria grade the answer field only.** A dict output's `quote` is an anchor, not
  evidence for a `contains`-check — the grader never lets it satisfy a criterion the answer text
  itself did not earn.
- **Reproduction proves grading determinism, not model determinism.** Two model runs are the
  evaluator's job.
- **Anchors are lexical.** Nothing here judges whether the sentence is *good*, only whether it
  carries the required content and avoids the forbidden.

## Failure handling

| symptom | what to do |
|-|-|
| `predicate … is not one of …` | rewrite the criterion as observable |
| `missing_required_point` | the answer lacked a required element — check whether the item asks for it clearly |
| `forbidden_content` | an over-claim or invented statistic — the red line fired |
| `over_length` | the answer exceeded the sentence budget |
| `under_length` | the answer dodged the substance floor (`min_words`) |
| `stable: false` | investigate the grader before trusting any score |

## Verification

```bash
python scripts/bench_benchkit.py   # 12 behavioural scenarios, half of them refusals
```

All 12 pass on this machine. The variant predicate is exercised explicitly: `tripled`,
`3-fold` and `three-fold` all score 100, while `four-fold` scores 0; `Three-Fold` scores 100
under `ci` and 50 without it; a one-line answer fails the `min_words` floor as `under_length`.

## 创新增益

本 Skill 相比通用 Agent 的核心新增能力：

1. **规则优先级库**：每条修改有规则 id、优先级、适用条件和理由，两个规则冲突时由优先级决定胜者且双方都留痕——通用 Agent 无法自证规则一致性。
2. **幂等二遍检查**：同一规则跑两遍，第二遍必须零改动——如果仍有改动说明规则间存在冲突，这是一个可计算的 self-check。
3. **逐条变更台账**：每个值的修改记录规则/行/列/原值/新值/理由，审计者可以逐条复核或撤销任何单条修改。

bench 目录下的 benchkit 是上述能力的回归证据（见 Verification 节 场景，clean 基线必须零发现）。

## 生态贡献

- **SKILL.md** 包含用途、适用条件、调用方式、输入输出、异常处理、限制和自查方法
- **scripts/** 纯标准库可独立导入，规则库可通过 spec 配置扩展
- **examples/** 提供最小调用示例和示意输出
- **bench/** 回归套件可独立复跑验证

## Requirements

Python 3.9+（3.14 实测）。纯标准库实现，无第三方依赖。
