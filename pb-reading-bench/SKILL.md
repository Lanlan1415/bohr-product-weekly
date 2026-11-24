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

## v2 · source-conditioned workorder, held-out evaluation and reproducible evidence

Run the actual workorder (or its supplied `--items` 或 `--outputs` overrides), keeping `case_id` and
all `output_contract` fields intact:

```bash
python3 /skills/weekly-skill/scripts/evalrun.py --case /input/case.json --out /app/output
```

The tool evaluates supplied raw outputs; **it does not call a model or invent outputs**. Items
written with `workorder`, `items` or `itemset` are accepted, as are `item_id`、`question_id`,
`instruction`、`question`, `input_text`、`source_text`、`context`、`passage`, and
`reference_answer`、`gold_answer`、`reference_output`、`answer_key`. Each final item still needs a valid
observable rubric. If it cannot be graded, the CLI returns structured `undetermined` with exit 5,
not an average of undefined scores. `0` = complete valid run, `3` = partial output/leakage/fairness
coverage, `5` = unreadable/malformed/undecidable workorder. Every branch writes result.json.

**Data split and leakage.** Explicit `train`、`dev`、`test` declarations are respected; the primary
score and paired bootstrap use **test only** (`metrics.scope=held_out_test`), with train/dev kept
out of that claim. An unpartitioned benchmark-DRAFT is explicitly an
`unpartitioned_workorder_diagnostic`, not held-out validation. Alternatively,
`evalkit.py::make_split` deterministically assigns **whole source groups** by hash with a saved
seed. `leakage_audit` reports source-group overlap, identical normalised input, and duplicate
query IDs across splits, plus pretraining/semantic-duplicate uncertainty. These are hard audit errors, not silent warnings. Findings have explicit IDs:
`benchmark.leakage_duplicate_query_id_within_split`, `benchmark.leakage_declared_split_mismatch`,
`benchmark.leakage_source_group_overlap`, `benchmark.leakage_query_id_overlap`,
`benchmark.leakage_exact_input_overlap`, and `benchmark.leakage_other` for a future unclassified kind.
`model_view.json` is a sorted, whitelisted model view with reference
answers/rubrics/qrels excluded. A reference appearing in actual source text is not leakage; the
model needs that evidence. It appearing as extra answer-scoring hints is flagged.

**Task and metric implementation.** `benchkit.py` preserves the lexical reading graders and
0/1/2 records but grades structured output on `text`/`answer` only (optional `output_field`),
never on an embedded golden quote. Weights must be finite/non-negative and sum 100 by default;
`regex`、`min_count`、`max_words` parameters are validated before grading, nested unbounded quantifiers
are refused, and explicit `ci:true` accepts case variants. `anchor` still requires a real quote
in given input. These are lexical judgments, not claimed semantic equivalence.

For retrieval tasks, `evalkit.py::evaluate_retrieval` independently implements the BEIR
(https://github.com/beir-cellar/beir) conventions: `qrels={qid:{docid:relevance}}` and
`results={qid:{docid:score}}` produce **nDCG/MAP/Recall/Precision/MRR@1,3,5,10** per item and
macro means. Stable tie ordering, graded nDCG ideal ranking, `min(#relevant,k)` denominator for
MAP, and skipped-not-positive/missing-result queries are explicit. No missing qrels becomes 0 or
100 as a convenience. `bm25_baseline` really tokenises the supplied corpus, computes document
scores and is evaluated against the same qrels and metrics, so `delta_vs_candidate` is a fair
metric calculation when the corpus is present; no baseline name-only placeholder or invented
retrieval score. The corpus, queries and both raw rankings stay in `retrieval_evaluation`.

**Variation, confidence and fair comparison.** `paired_bootstrap` resamples item indices with
a fixed seed (default 2026, 1000 iterations), computes percentile intervals of each agent's
observed metric and the paired difference; paired inputs must have identical ordered IDs and the
same item-set digest. Small item counts are marked descriptive, not proof of low variance.
`run_stability` records repeat-run mean/stdev/min/max; `fairness` refuses silent like-for-like
comparison if tool permissions, prompt, budget or item set differ. A baseline is a declared
condition, not evidence of causality. `bootstrap_iterations` needs to be in 100..100000.

`result.json` includes: full item-set validation/version, data split and leakage audit, raw output
and per-criterion decisions, trace for every item ID, held-out primary metrics and per-item
scores, BEIR per-query/mean metrics when supplied, real baseline comparison, bootstrap intervals,
fairness/stability, typed failure sample library, and command/config digests for rerun.
`evaluation.json` and `evaluation_report.md` accompany local case results. Reporter and fixtures
explicitly label technical synthetic checker results as **not DSH scores or independent semantic
validation**. Unknown output-contract fields become null with a limit reason, rather than fake data.

Example CLI declarations for an explicit retrieval workorder can be used standalone:

```bash
python3 /skills/weekly-skill/scripts/evalrun.py \
  --case /input/case.json --qrels /app/work/qrels.json --results /app/work/results.json \
  --corpus /app/work/corpus.json --out /app/output
```

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

`/app/output/result.json` should carry, per case: the item set with its digest, held-out scope,
model-view and leakage audits, raw run record with per-item/per-criterion results and evidence,
raw outputs, reproducible command/config/seed, retrieval metrics and real baseline (when supplied),
bootstrap intervals, fairness/stability records, and failure types/samples. With `evalrun.py`,
per-field case contracts are satisfied and unknown fields get null + explicit limits; fatal work-
order failures use `benchmark.workorder_refused` and exit 5, not traceback-only. Versions and
failure classes are not swapped after inspecting results.

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
python3 /skills/weekly-skill/scripts/bench_benchkit.py      # 27 legacy behavioural scenarios
python3 /skills/weekly-skill/scripts/bench_eval_execution.py # 23 metric/leakage/CI/CLI checks
```

About half of the legacy scenarios assert a refusal or a zero-finding guard; clean baselines must
find no finding. The second suite independently hand-computes nDCG/MAP/Precision/Recall/MRR,
uses qrels with a non-positive/missing query, detects identical source input across splits, checks
a real BM25 baseline, repeats bootstrap with identical results, keeps train out of test-only CLI
primary outputs, covers structured refusal, idempotence and full contract passthrough, and tests
that an embedded quote cannot enlarge content scores. All local benches pass; examples and reports
are synthetic interface checks, never platform-scored results or independent semantic validation.
## Requirements

Python 3.9+（3.14 实测）。纯标准库实现，无第三方依赖。

## 创新增益

本 Skill 相比通用 Agent 的核心新增能力：

1. **source-group disjoint split + model-view 隔离**：真实可复跑的 held-out 评分和泄漏硬审计，而不是把 train 也计入展示总分。
2. **BEIR 指标与真实 BM25 基线**：不是截图或名为基线的数字；同一 qrels 下实际 rank/score/mean/delta 可复算。
3. **确定性 paired bootstrap + 公平性/失败样例库**：相同 item 抽样化为各 agent 成绩与差值置信区间，实际重复运行波动与不公平配置保留，不把缺失答案当科学语义零分。
4. **可溯源且防 quote 泄漏的 structured-output grader**：原始 output 和 criterion evidence 随分数保存，默认只看 text/answer，避免附带 quote 偶然补足内容短语。

所有能力由 scripts/evalkit.py 与 evalrun.py 真实实现，并以 bench_eval_execution.py 的 23 项本地
合成测试验证。旧 benchkit 的 rubric 与 retarget 路径保持回归覆盖（bench_benchkit.py 的 27 项）。

## 生态贡献

- **SKILL.md** 包含用途、适用条件、调用方式、输入输出、异常处理、限制和自查方法
- **scripts/** 纯标准库可独立导入，规则库可通过 spec 配置扩展
- **examples/** 提供最小调用示例和示意输出
- **bench/** 回归套件可独立复跑验证

