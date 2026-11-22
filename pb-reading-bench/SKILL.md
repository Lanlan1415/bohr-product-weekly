---
name: reading-benchmark
description: >
  A literature-reading benchmark you can actually run: an item set whose rubrics are observable
  predicates, a grader that scores every criterion with its evidence, a run record from which any
  score traces back to the raw output and configuration, and a retarget step that turns a failure
  into a new targeted item while recomputing only that item. Refuses an item whose criterion is
  free text, whose rubric does not sum to 100, or whose quote cannot be found in its input. Use
  when a task asks for a question set, an evaluation tool, or a scoring harness for reading tasks.
---

# reading-benchmark

The four properties this task names are the four things the harness enforces:

| property | mechanism |
|-|-|
| 判得动 — two graders reach the same verdict | every criterion is a machine predicate with declared parameters; a free-text criterion is refused at load |
| 跑得一致 — repeated runs agree | `reproduce` runs twice and reports any per-item delta instead of averaging it |
| 查得回 — a score traces to its origin | every result carries the raw output itself, the criterion, its evidence, the run configuration and the item-set digest |
| 改得动 — a failure becomes a better item | `retarget` maps a failure type to a new item and names the only score to recompute |

## Why criteria must be predicates

A rubric line like *"the answer reads well"* cannot be applied twice the same way, so two graders
disagree and the item is not gradeable. The harness therefore accepts only these:

| predicate | meaning |
|-|-|
| `contains` | all listed strings present |
| `any_of` | **any** one present — this is how legitimate wording variants are accepted |
| `not_contains` | none of the listed strings present |
| `regex` / `min_count` | pattern must match / must occur at least N times |
| `anchor` | the quote the answer claims must exist in the item's input |
| `max_words` | length ceiling |
| `manual` | **declared** human review: deferred with its note, excluded from the machine score |

`anchor` is the one that makes reading gradeable without a second human: an answer that quotes text
not present in the paper fails, and the failure is attributed as `evidence_not_located`.

`manual` is the honest escape hatch, not a loophole: prose that *claims* to be gradable is refused,
while a criterion the author explicitly declares human-judged is recorded as `needs_review` and its
weight stays out of the machine score — which is the 评分表's 规则评分与人工复核 split.

## Workflow

### 1. Write the item set

```json
[
  {
    "id": "R1",
    "task": "State the measured effect of the coating on uptake.",
    "input": "Uptake rose three-fold under the coating. Only one thickness was tested, …",
    "reference": "uptake rose three-fold under the coating",
    "rubric": [
      {"criterion": "effect stated with magnitude", "predicate": "any_of", "weight": 40,
       "values": ["three-fold", "3-fold", "tripled"]},
      {"criterion": "quote located in the input", "predicate": "anchor", "weight": 40,
       "field": "quote"},
      {"criterion": "no invented significance", "predicate": "not_contains", "weight": 20,
       "values": ["p < 0.05"]}
    ]
  }
]
```

Weights must sum to 100, or cross-item totals are not comparable. The optional card fields the
题集管理 direction names — `difficulty`, `license`, `data_authorization` — are checked only when
declared: a declared-but-empty field is refused, an absent field is never a problem.

### 2. Validate, grade, reproduce

```python
import benchkit as K
items = [...]
assert K.validate_itemset(items)["ok"]
record = K.run(items, outputs, {"model": "…", "budget": 64})
K.reproduce(items, outputs, {"model": "…"})    # -> {"stable": true, "deltas": []}
K.trace(record, "R1")                          # -> score, raw_output, decided_by, config
```

`outputs` maps item id to the raw model output. The record keeps every raw output verbatim, so
查得回 ends at the output itself, not a digest of it. An item with no output scores 0 with
`failure_type: not_attempted`; an output that is blank scores 0 as `empty_output`; an output that
is neither text nor a structured record scores 0 as `malformed_output` — all three are identified
instead of being graded into a misleading content failure.

Declare `score_scale: "0-1-2"` in the config and every result also carries `score_012`
(2 correct, 1 partial, 0 wrong or missing — the 评分表's suggested record, kept beside the
percentage). An unsupported declared scale is refused, never silently ignored.

### 3. Retarget a failure

```python
K.retarget(items, record, "R2", new_item)
# -> {"recompute_only": ["R2b"], "unchanged_scores": {...}, "from_version": …, "to_version": …}
```

The new item must be gradable; the old scores stay valid for the old item-set version, which is
what makes the set improvable without re-running everything.

### 4. Read the results back

```python
K.failures(items, record)       # 失败样例库: errors indexed by type, each with item, raw output, reason
K.panel([record_a, record_b])   # 结果面板: by agent x item-set version — distributions, not one total
K.diff_itemsets(v1, v2)         # 版本对比: which card fields changed, which historical scores stay comparable
```

`failures` is the library the 失败样例库 direction asks for: every typical error kept with the
item, the raw output and the reason, retrievable by failure type. `panel` groups runs by agent
and item-set digest so strengths, weaknesses and score distributions are visible instead of one
total. `diff_itemsets` names the changed card fields (`task`, `input`, `reference`, `rubric`) per
item and lists the unchanged items whose historical scores remain comparable.

## Output contract

`/app/output/result.json` should carry, per case: the item set with its digest, the run record with
per-item and per-criterion results and evidence, each raw output as retained in the record, the
reproduction comparison, the failure tally by type (with the failure sample library for anything
non-zero), the declared score scale if one was used, and for any retarget the two version digests
and the recompute list.

## Limits

- **Predicates are lexical.** `contains` cannot tell a correct use of a phrase from an incidental
  one; `any_of` accepts variants but cannot judge whether a variant is legitimate.
- **`anchor` checks existence, not support.** A quote that exists in the paper is accepted even if
  it does not answer the question — that is why `contains` criteria sit alongside it.
- **Reproduction here re-runs the grader, not the model.** Two model runs are the evaluator's job;
  this proves the *grading* is deterministic, which is the half a benchmark author controls.
- **Weights are declared, not validated for fairness.** A rubric summing to 100 can still weight
  the wrong thing.
- **`manual` criteria are deferred, never decided.** The recorded score covers only the
  machine-decidable weight; the deferred judgement is listed in `needs_review`, not folded in.
- **`diff_itemsets` compares card fields structurally.** Equality per field, no semantic
  similarity: a reworded-but-equivalent task still counts as changed.
- **`panel` aggregates, it does not interpret.** It surfaces distributions and failure tallies;
  reading them is the author's job.
- **Empty and malformed outputs are identified, not repaired.** They score 0 with their own
  failure kind; recovering the answer is the caller's move.
- **`score_012` bands the machine score.** A pending `manual` criterion does not lower the band;
  the human verdict is recorded separately as `needs_review`.

## Failure handling

| symptom | what to do |
|-|-|
| `predicate 'prose' is not one of …` | rewrite the criterion as an observable predicate |
| `rubric weights sum to 40, not 100` | fix the weights or set `normalise: false` deliberately |
| `evidence_not_located` | the answer quotes text absent from the input — the item is doing its job |
| `empty_output` | the answer came back blank — re-run the agent; do not retarget the item for it |
| `malformed_output` | the output is neither text nor a structured record — fix the exporter, not the rubric |
| `score_scale '…' is not supported` | declare `'0-1-2'` or omit the scale; the harness refuses to silently ignore a declared one |
| `manual criterion needs a note` | state what the human judge applies, or make the criterion a predicate |
| `difficulty declared but empty` | fill the declared card field or drop it from the card |
| `stable: false` | the grader is non-deterministic or the outputs changed; investigate before scoring |
| `did not fail, so there is nothing to retarget` | retarget works from a real failure |
| `the new item is not gradable` | validate it first; the harness reports why |

## Verification

```bash
python scripts/bench_benchkit.py   # 27 behavioural scenarios
```

About half assert a refusal or a zero-finding guard, and every new rule ships with both a defect
scenario and its false-positive guard (correct input must find nothing): an ungradable criterion,
an unsourced quote, a retarget with no failure, an empty and a malformed output, an unsupported
declared scale, a manual criterion without a note, a declared-but-empty card field — each paired
with the clean-run guard for the same rule. All 27 pass on this machine.
## Requirements

Python 3.9+（3.14 实测）。纯标准库实现，无第三方依赖。

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

