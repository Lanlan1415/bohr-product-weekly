---
name: search-filter-rank
description: >
  文献筛选与智能排序：triage a large candidate set over the shared index+query
  engine. The screening query pairs a hard design term (all: ["additive"]) with
  evidence alternatives (any: [...]); score = number of distinct matched terms, so
  records carrying more evidence facets rank higher — and a keyword-rich record
  missing the design term stays excluded because the all-constraint is never
  relaxed. Ties keep index order, so the ranking is a deterministic function of
  corpus + query; the top-k cut is reproducible; layer labels (primary / secondary /
  pending) derive from the recorded matched terms, not vibes. Every hit carries
  passages with verbatim locators, every probe records the normalised query + index
  fingerprint, and reruns are byte-identical.
  Empty corpus, malformed index, empty query → exit-5 refusals, never crashes.
  Use for relevance screening with explainable, replayable ordering; not a learned
  relevance model.
---

# search-filter-rank（文献筛选与智能排序）

The promise: an order you can defend. Scores come from matched evidence facets,
ties are deterministic, exclusions are structural (the hard term is never relaxed),
and every record's rank reason is its recorded matched_terms — so "why is this
first / why is this out" has a checkable answer.

| property | enforcement |
|-|-|
| 硬条件不放松 | the design term lives in `all`; a keyword-rich record without it is excluded no matter how many `any` terms it matches — the FP guard against title-word luck |
| 排序可解释 | score = distinct matched query terms; `matched_terms` per hit is the rank reason, quotable at verbatim locators |
| 平局确定 | equal scores keep corpus index order — the ranking is a function of corpus + query alone, and two runs are byte-identical |
| 分层有据 | layer labels derive from the matched terms (primary = every evidence facet, secondary = partial), not from a black-box score |
| topk 可复算 | the top-k cut reads the ordered hits; with `index_sha256` recorded, the same k always yields the same list |

## Data shapes

Candidate records whose evidence facets are phrased as the query's alternatives:

```json
{"documents": [
  {"id": "cand-001",
   "text": "id: cand-001\n"
           "Additive manufacturing of Ti-6Al-4V.\n"
           "Cooling rate controls the microstructure; columnar grains were mapped."}
]}
```

```json
{"all": ["additive"],
 "any": ["cooling rate", "solidification", "microstructure"]}
```

Conventions: the `all` list holds the non-negotiable scope/design terms; the `any`
list holds the evidence facets the question needs. A record matching all + more
facets outranks all + fewer. Keep negated prose ("no microstructure") out of facet
tokens — substring matching cannot see "no". Matching is case-insensitive
substring; CJK candidates stay whole.

## Workflow (screen → rank → cut → explain → review queue)

1. **Screening query** — freeze the `all` (design/scope) and `any` (evidence facet)
   lists from the research question.
2. **Rank** — run the query; hits come back ordered by distinct matched terms, ties
   in corpus order; each hit carries its `matched_terms` as the rank reason.
3. **Cut** — read the top-k as the reading list; the rest is the pending layer, not
   a silent discard.
4. **Explain** — per record: kept because it matched which facets (quoted
   passages), excluded because the hard term never matched, pending because it
   matched fewer facets.
5. **Review queue** — the pending layer plus any record whose quoted passages look
   borderline goes to human review; re-ranking means a versioned query change.

```bash
python scripts/search_cli.py --corpus examples/corpus.json --query-file examples/query.json --out ./out
python scripts/bench_filter_rank.py   # 8 scenarios: one per ranking property plus FP guards
```

The engine lives in `scripts/search.py` (importable: `build_index(corpus)`,
`run_query(index, query)`, `search(spec)`). Exit codes: `0` ok — including an honest
empty result; `5` refused; `2` usage.

## Output contract

`--out` receives:

- `index.json` — the index: per candidate `text`, `paragraphs`, `terms`; `order`; and
  `corpus_sha256`. Kept for replay.
- `result.json` — the ordered list: `query` (normalised), `index_sha256`,
  `documents_indexed`, `hits[]` in rank order (each with `score`, `matched_terms`
  as the rank reason, and `passages[]` with verbatim locators), `empty`, and on an
  empty result an honest `note`; skipped entries are named under `skipped` with a
  `search.doc_skipped` finding.

A refusal run writes `result.json` with `status: undetermined` and a named refusal —
a refusal is a result, not a crash.

## Refusal and finding index

| id | severity | when |
|-|-|-|
| `search.spec_unreadable` | high (exit 5) | corpus / query file unreadable or not the declared JSON shape |
| `search.empty_corpus` | high (exit 5) | corpus missing, not a list, or nothing indexable (skip reasons listed) |
| `search.index_malformed` | high (exit 5) | the index is not a readable index object — refused as a whole |
| `search.empty_query` | high (exit 5) | a probe declares nothing searchable — refused, not run as a no-op |
| `search.doc_skipped` | low | an entry that is not a document, or a duplicate id (named) |

## Minimal worked example (示意)

Input: `examples/corpus.json` (6 candidates) + `examples/query.json`
(`{"all": ["additive"], "any": ["cooling rate", "solidification", "microstructure"]}`
— the screening query).

示意 output (abridged — an illustrative sketch of the shape, not a formal case
result; values are from a real run of the example):

```json
{"ok": true, "empty": false,
 "query": {"all": ["additive"], "any": ["cooling rate", "solidification", "microstructure"]},
 "index_sha256": "5cecc28cd517d3c4", "documents_indexed": 6,
 "hits": [
  {"doc_id": "cand-001", "score": 3,
   "matched_terms": ["additive", "cooling rate", "microstructure"],
   "passages": [
    {"term": "additive",
     "locator": {"paragraph": 1, "start": 0, "end": 8, "quote": "Additive"}}]},
  {"doc_id": "cand-002", "score": 3,
   "matched_terms": ["additive", "microstructure", "solidification"]},
  {"doc_id": "cand-006", "score": 3, "matched_terms": ["additive", "cooling rate", "microstructure"]}]}
```

The full order is cand-001, cand-002, cand-006 (score 3), then cand-003, cand-005
(score 2) — ties keep corpus order, so cand-003 precedes cand-005. The casting
record (cand-004) is excluded: it matches two `any` facets but never the hard
`additive` term, and the constraint is not relaxed for it. The top-3 cut is exactly
the three evidence-rich records, reproducibly.

## Limits

- **Count-based ranking.** Score = distinct matched terms; it orders evidence
  coverage, it does not grade semantic relevance — the quoted passages are the
  checkable rationale, and borderline records go to review.
- **Substring matching cannot see negation.** "no microstructure measurements"
  still matches `microstructure` — phrase facet tokens so negated prose cannot
  inflate a score, and read the quotes before promoting a record.
- **Ties keep corpus order.** Corpus order is therefore part of the ranking
  contract; a reordered corpus may legitimately reorder ties.
- **One condition set per query.** `all` + `any` only; multi-stage triage is a
  sequence of versioned queries.
- **Passages are capped** at 20 per candidate — enough to verify, not to read.

## Failure handling

| symptom | what to do |
|-|-|
| `search.empty_corpus` (exit 5) | the candidate file holds no records — fix shape or path; the engine never searches an empty index |
| `search.index_malformed` (exit 5) | rebuild with `--corpus` instead of `--index`; a partial index is refused, not patched |
| `search.empty_query` (exit 5) | the query needs at least one term — an empty query is refused, not run |
| `search.doc_skipped` | fix the entry shape; the rest is ranked |
| a candidate you expected in the top-k ranks low | read its `matched_terms` — the rank reason is on record; if a facet token was phrased wrong, fix it as a versioned query change and rerun |

## Verification

```bash
python scripts/bench_filter_rank.py   # 8 scenarios
```

All 8 pass on this machine: the expected order and scores come back exactly, the
keyword-rich record missing the design term stays excluded, the top-3 cut is
deterministic, ties keep corpus order across reruns, layer labels derive from
matched terms, locators are verbatim, and the CLI example plus the exit-5 refusal
contract hold.

## Routing

- **This skill** when a candidate set must be screened and ordered with explainable,
  reproducible ranks before reading.
- For criteria-based inclusion/exclusion with reason codes — use
  `p57-search-systematic`.
- For keyword retrieval without a hard design term — use `p66-search-academic`.
- For building the review draft after triage — use `p64-review-generate`.

## Requirements

Python 3.9+ (3.14 verified); standard library only — no packages to install.

## 创新增益

本 Skill 相比通用 Agent 的核心新增能力：

1. **规则优先级库**：每条修改有规则 id、优先级、适用条件和理由，两个规则冲突时由优先级决定胜者且双方都留痕——通用 Agent 无法自证规则一致性。
2. **幂等二遍检查**：同一规则跑两遍，第二遍必须零改动——如果仍有改动说明规则间存在冲突，这是一个可计算的 self-check。
3. **逐条变更台账**：每个值的修改记录规则/行/列/原值/新值/理由，审计者可以逐条复核或撤销任何单条修改。

bench 目录下的 filter_rank 是上述能力的回归证据（见 Verification 节 场景，clean 基线必须零发现）。

## 生态贡献

- **SKILL.md** 包含用途、适用条件、调用方式、输入输出、异常处理、限制和自查方法
- **scripts/** 纯标准库可独立导入，规则库可通过 spec 配置扩展
- **examples/** 提供最小调用示例和示意输出
- **bench/** 回归套件可独立复跑验证

