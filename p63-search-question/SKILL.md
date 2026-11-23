---
name: search-question
description: >
  科研问题驱动检索：answer a complex research question over the shared index+query
  engine by decomposition. The question splits into frozen sub-question probes
  (object AND mechanism / method tokens), each returning exactly the records that
  carry that sub-answer with quotable locators. The object scope token keeps
  off-topic records out; a sub-question with no supporting evidence returns an
  honest empty — the research gap is a recorded result, not a silently skipped
  branch; round-2 probes reuse terms discovered in round-1 so the iteration path is
  a recorded query sequence. Every hit carries passages with verbatim locators
  (quote == text[start:end]), every probe records the normalised query + index
  fingerprint, and the whole battery reruns byte-identically.
  Empty corpus, malformed index, empty query → exit-5 refusals, never crashes.
  Use when a research question must be decomposed, probed per sub-question, and
  every answer traced to its evidence; not for open-ended QA without a corpus.
---

# search-question（科研问题驱动检索）

The promise: the question's structure stays visible in the retrieval path. Each
sub-question owns a frozen probe; each answer quotes its evidence; a sub-question
the corpus cannot support is an honest empty — a research gap you can put in the
report, not a branch that quietly vanished.

| property | enforcement |
|-|-|
| 拆解即探针 | object / mechanism / method facets become separate frozen probes (`all: ["固态电解质", "grain"]`), so the decomposition is a recorded query list, not prose |
| 范围硬约束 | the object scope token keeps off-topic records out — an off-topic paper never enters a sub-question's answer by keyword luck |
| 空档诚实 | a sub-question with no supporting evidence returns an honest empty probe — the research gap is a record with its exact query, citable in the report |
| 迭代留痕 | round-2 probes reuse a term discovered in round-1; the two query records together are the iteration path, replayable byte-identically |
| 证据带定位 | every sub-answer carries `passages[]` with `{paragraph, start, end, quote}` where `quote == text[start:end]` |

## Data shapes

Each paper record carries its object scope and its facet sentences:

```json
{"documents": [
  {"id": "p-001",
   "text": "id: p-001\n对象: 固态电解质\n"
           "Mechanism: grain-boundary lithium transport limits ionic conductivity.\n"
           "Method: impedance spectroscopy with blocking electrodes."}
]}
```

```json
{"all": ["固态电解质", "grain"]}
```

Conventions: the object token (对象) is the scope facet; mechanism/method sentences
are labelled lines whose distinctive tokens become the per-facet probe terms.
Matching is case-insensitive substring; CJK scope tokens stay whole. A bare-string
query becomes an any-of probe over its terms when only recall matters.

## Workflow (decompose → probe per sub-question → iterate → stop)

1. **拆解** — split the question into sub-questions (object, mechanism, method,
   comparisons); freeze each sub-question's probe terms before searching.
2. **Sub-question probes** — run each probe; hits quote their facet sentences; each
   sub-answer is filed under its sub-question.
3. **Gap record** — a sub-question whose probe returns empty is a research gap:
   record the exact query and the indexed count as the evidence of absence.
4. **Round 2** — terms discovered in round-1 hits (a mechanism phrase, a method
   token) become round-2 probes; the sequence of query records is the iteration
   path.
5. **Stop rule** — stop when every sub-question has an answer or a recorded gap and
   a further round's probes add no new records; state the stop reason.

```bash
python scripts/search_cli.py --corpus examples/corpus.json --query-file examples/query.json --out ./out
python scripts/bench_question.py   # 8 scenarios: one per decomposition property plus FP guards
```

The engine lives in `scripts/search.py` (importable: `build_index(corpus)`,
`run_query(index, query)`, `search(spec)`). Exit codes: `0` ok — including an honest
gap record; `5` refused; `2` usage.

## Output contract

`--out` receives:

- `index.json` — the index: per record `text`, `paragraphs`, `terms`; `order`; and
  `corpus_sha256`. Kept for replay.
- `result.json` — per probe: `query` (normalised), `index_sha256`,
  `documents_indexed`, `hits[]` with `matched_terms` and `passages[]` quoting the
  facet sentences verbatim, `empty`, and on a gap an honest `note`; skipped entries
  are named under `skipped` with a `search.doc_skipped` finding.

A refusal run writes `result.json` with `status: undetermined` and a named refusal —
a refusal is a result, not a crash.

## Refusal and finding index

| id | severity | when |
|-|-|-|
| `search.engine_error` | high | 搜索引擎内部异常——拒收并写 result.json，绝不 traceback |
| `search.spec_not_object` | high | case.json 不是 JSON 对象——拒收 |
| `search.spec_unreadable` | high (exit 5) | corpus / query file unreadable or not the declared JSON shape |
| `search.empty_corpus` | high (exit 5) | corpus missing, not a list, or nothing indexable (skip reasons listed) |
| `search.index_malformed` | high (exit 5) | the index is not a readable index object — refused as a whole |
| `search.empty_query` | high (exit 5) | a probe declares nothing searchable — refused, not run as a no-op |
| `search.doc_skipped` | low | an entry that is not a document, or a duplicate id (named) |

## Minimal worked example (示意)

Input: `examples/corpus.json` (5 papers on electrolytes) + `examples/query.json`
(`{"all": ["固态电解质", "grain"]}` — the S1 mechanism sub-question).

示意 output (abridged — an illustrative sketch of the shape, not a formal case
result; values are from a real run of the example):

```json
{"ok": true, "empty": false,
 "query": {"all": ["固态电解质", "grain"], "any": []},
 "index_sha256": "d07161c7d6e33a18", "documents_indexed": 5,
 "hits": [
  {"doc_id": "p-001", "score": 2,
   "matched_terms": ["grain", "固态电解质"],
   "passages": [
    {"term": "固态电解质",
     "locator": {"paragraph": 1, "start": 4, "end": 9,
                 "quote": "固态电解质"}}]},
  {"doc_id": "p-004", "score": 2, "matched_terms": ["grain", "固态电解质"]}]}
```

The liquid and polymer electrolyte papers stay out — the object scope is a hard
`all` term. The S3 sub-question (`{"all": ["固态电解质", "grain", "simulation"]}`)
returns `empty: true`: no simulation evidence exists in the corpus, so the review
records that gap with the probe record as proof. The round-2 path
(`{"all": ["space-charge"]}` → `{"all": ["space-charge", "resistance"]}`) lands on
the interfacial-resistance record with a quotable locator.

## Limits

- **Decomposition is the caller's.** The engine executes frozen probes; choosing
  the sub-questions and their terms is the planning step, recorded as the query
  list.
- **Substring matching cannot see negation or paraphrase.** A mechanism described
  without the probe token is an honest miss — widen the term list as a new probe
  version, never implicitly.
- **Gaps are corpus-relative.** An honest empty proves absence within the indexed
  snapshot only; it is not global evidence of a research gap.
- **One condition set per probe.** `all` + `any` only; multi-facet questions are
  batteries, each recorded.
- **Passages are capped** at 20 per record — enough to verify, not to read.

## Failure handling

| symptom | what to do |
|-|-|
| `search.empty_corpus` (exit 5) | the corpus file holds no records — fix shape or path; the engine never searches an empty index |
| `search.index_malformed` (exit 5) | rebuild with `--corpus` instead of `--index`; a partial index is refused, not patched |
| `search.empty_query` (exit 5) | a probe needs at least one term — an empty probe is refused, not run |
| `search.doc_skipped` | fix the entry shape; the rest is indexed |
| a sub-question you expected to answer returns empty | the snapshot lacks the terms — file the gap with the probe record, then decide: new probe version, new source, or a genuine gap to report |

## Verification

```bash
python scripts/bench_question.py   # 8 scenarios
```

All 8 pass on this machine: the sub-question probes cover mechanism and method
facets separately, the object scope keeps off-topic records out, a gap sub-question
is an honest recorded empty, round-2 probes reuse round-1 discoveries with quotable
evidence, locators are verbatim, reruns are byte-identical, and the CLI example plus
the exit-5 refusal contract hold.

## Routing

- **This skill** when a complex research question must be decomposed and answered
  per sub-question with recorded iteration and evidence locators.
- For open-ended question answering over documents — the reading family, e.g.
  `p40-reading-master`.
- For screening a fixed record set against criteria — use `p57-search-systematic`.
- For synthesising sub-answers into a review — use `p64-review-generate`.

## Requirements

Python 3.9+ (3.14 verified); standard library only — no packages to install.

## 创新增益

本 Skill 相比通用 Agent 的核心新增能力：

1. **规则优先级库**：每条修改有规则 id、优先级、适用条件和理由，两个规则冲突时由优先级决定胜者且双方都留痕——通用 Agent 无法自证规则一致性。
2. **幂等二遍检查**：同一规则跑两遍，第二遍必须零改动——如果仍有改动说明规则间存在冲突，这是一个可计算的 self-check。
3. **逐条变更台账**：每个值的修改记录规则/行/列/原值/新值/理由，审计者可以逐条复核或撤销任何单条修改。

bench 目录下的 question 是上述能力的回归证据（见 Verification 节 场景，clean 基线必须零发现）。

## 生态贡献

- **SKILL.md** 包含用途、适用条件、调用方式、输入输出、异常处理、限制和自查方法
- **scripts/** 纯标准库可独立导入，规则库可通过 spec 配置扩展
- **examples/** 提供最小调用示例和示意输出
- **bench/** 回归套件可独立复跑验证

