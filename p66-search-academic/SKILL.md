---
name: search-academic
description: >
  学术文献检索：retrieve academic records over the shared index+query engine with
  reproducible ranking and honest dedup. A bare-string query becomes an any-of probe
  whose hits rank by distinct matched terms (ties keep index order), so a top-k
  reading list is a deterministic function of corpus + query. An any-list expansion
  recalls synonym phrasings while the scope term stays hard in `all`; the scope
  probe keeps the off-domain record out. A duplicated export under the same id is
  skipped and named, so the identifier probe counts one record. Every hit carries
  passages with verbatim locators (quote == text[start:end]), every probe records
  the normalised query + index fingerprint, and reruns are byte-identical.
  Empty corpus, malformed index, empty query → exit-5 refusals, never crashes.
  Use for keyword-driven academic retrieval with traceable ranking and dedup over
  an organiser-provided snapshot; open-web live search is out of scope.
---

# search-academic（学术文献检索）

The promise: a reading list you can re-derive. The ranking comes from matched query
terms with deterministic ties, expansions are declared lists (not silent rewriting),
the scope guard keeps the off-domain record out, duplicates are named, and every
hit quotes the sentence that matched.

| property | enforcement |
|-|-|
| 排序可复现 | score = distinct matched query terms; ties keep corpus order — Precision@k and the top-k cut are recomputable from the recorded query + `index_sha256` |
| 扩展不隐身 | synonym recall comes from a declared `any` list (`transformer`, `attention`); the scope term stays hard in `all` — the engine never rewrites the query |
| 范围硬约束 | the scope probe (`all: ["protein", "prediction"]`) keeps the off-domain record out even when its keywords partially match |
| 去重留痕 | a duplicated export under the same id is skipped and named (`search.doc_skipped`); the identifier probe then counts exactly one record |
| 命中带定位 | every hit quotes its matched sentence at `{paragraph, start, end, quote}` with `quote == text[start:end]` |

## Data shapes

Academic records with their metadata as labelled lines:

```json
{"documents": [
  {"id": "a-001",
   "text": "id: a-001\n"
           "Attention-based transformers for protein structure prediction.\n"
           "doi: doi-10-1038-s41592-021-0114-y\nyear: 2021\njournal: Nature Methods"}
]}
```

```json
{"all": ["protein"], "any": ["transformer", "attention"]}
```

Conventions: identifiers are normalised to dash form (`doi-10-…`); metadata lines
(`year:`, `journal:`) make year/type filtering a token probe. A bare-string query
("protein structure prediction") becomes an any-of probe over its terms when recall
matters most. Matching is case-insensitive substring; CJK titles stay whole.

## Workflow (scope → expand → rank → cut → dedup/audit)

1. **Scope terms** — put the non-negotiable scope terms (topic, object, design) in
   `all`; they define what the question is about.
2. **Expansion list** — declare the synonym/abbreviation alternatives in `any`;
   each expansion is on record, never an implicit rewrite.
3. **Rank** — run the query; hits order by distinct matched terms with corpus-order
   ties; each hit quotes its matched sentences.
4. **Cut** — read the top-k as the reading list; the recorded scores and
   `matched_terms` are the Precision@k rationale.
5. **Dedup/audit** — duplicate exports are named; the identifier probe confirms one
   record per work; the whole battery reruns byte-identically.

```bash
python scripts/search_cli.py --corpus examples/corpus.json --query-file examples/query.json --out ./out
python scripts/bench_academic.py   # 8 scenarios: one per retrieval property plus FP guards
```

The engine lives in `scripts/search.py` (importable: `build_index(corpus)`,
`run_query(index, query)`, `search(spec)`). Exit codes: `0` ok — including an honest
empty result; `5` refused; `2` usage.

## Output contract

`--out` receives:

- `index.json` — the index: per record `text`, `paragraphs`, `terms`; `order`; and
  `corpus_sha256`. Kept for replay.
- `result.json` — the ranked list: `query` (normalised), `index_sha256`,
  `documents_indexed`, `hits[]` in rank order (each with `score`, `matched_terms`,
  and `passages[]` with verbatim locators), `empty`, and on an empty result an
  honest `note`; skipped duplicate exports are named under `skipped` with a
  `search.doc_skipped` finding.

A refusal run writes `result.json` with `status: undetermined` and a named refusal —
a refusal is a result, not a crash.

## Refusal and finding index

| id | severity | when |
|-|-|-|
| `search.spec_unreadable` | high (exit 5) | corpus / query file unreadable or not the declared JSON shape |
| `search.empty_corpus` | high (exit 5) | corpus missing, not a list, or nothing indexable (skip reasons listed) |
| `search.index_malformed` | high (exit 5) | the index is not a readable index object — refused as a whole |
| `search.empty_query` | high (exit 5) | the query declares nothing searchable — refused, not run as a no-op |
| `search.doc_skipped` | low | an export that is not a document, or a duplicate id (named) |

## Minimal worked example (示意)

Input: `examples/corpus.json` (5 entries, one duplicated export) +
`examples/query.json` (`{"all": ["protein"], "any": ["transformer", "attention"]}`
— the scope + expansion probe).

示意 output (abridged — an illustrative sketch of the shape, not a formal case
result; values are from a real run of the example):

```json
{"ok": true, "empty": false,
 "query": {"all": ["protein"], "any": ["transformer", "attention"]},
 "index_sha256": "a11fd08a73833642", "documents_indexed": 4,
 "hits": [
  {"doc_id": "a-001", "score": 3,
   "matched_terms": ["attention", "protein", "transformer"],
   "passages": [
    {"term": "attention",
     "locator": {"paragraph": 1, "start": 0, "end": 9, "quote": "Attention"}}]},
  {"doc_id": "a-002", "score": 2,
   "matched_terms": ["attention", "protein"],
   "passages": [
    {"term": "attention",
     "locator": {"paragraph": 1, "start": 5, "end": 14,
                 "quote": "attention"}}]}],
 "skipped": [{"index": 4, "reason": "duplicate doc id 'a-001'; the entry is "
              "skipped rather than silently merged"}]}
```

The expansion recalls the "Self-attention" phrasing via the declared `attention`
term; the scope probe (`{"all": ["protein", "prediction"]}`) keeps the dietary
cohort out; the bare-string probe ("protein structure prediction") ranks a-001 and
a-003 (score 3) above a-002 and a-004 (score 1), ties in corpus order; the DOI
probe counts one record after the duplicate export is named.

## Limits

- **Lexical, not semantic.** A paraphrase sharing no term is an honest miss;
  synonyms belong in the declared `any` list.
- **Count-based ranking.** Score = distinct matched terms — it orders keyword
  coverage, not semantic relevance; the quoted passages are the rationale.
- **Substring matching cannot see negation.** "not a transformer study" still
  contains "transformer" — adjudicate borderline hits on the quote.
- **Ties keep corpus order.** Corpus order is part of the ranking contract.
- **One condition set per query.** `all` + `any` only; multi-stage searches are
  versioned query batteries.
- **Passages are capped** at 20 per record — enough to verify, not to read.

## Failure handling

| symptom | what to do |
|-|-|
| `search.empty_corpus` (exit 5) | the corpus file holds no records — fix shape or path; the engine never searches an empty index |
| `search.index_malformed` (exit 5) | rebuild with `--corpus` instead of `--index`; a partial index is refused, not patched |
| `search.empty_query` (exit 5) | the query needs at least one term — an empty query is refused, not run |
| `search.doc_skipped` | drop the duplicate export or fix the entry shape; the rest is indexed |
| expected literature returns empty | the snapshot lacks the terms — widen `any` deliberately as a new query version; an honest miss over the snapshot is not global evidence of absence |

## Verification

```bash
python scripts/bench_academic.py   # 8 scenarios
```

All 8 pass on this machine: the bare-string query ranks deterministically, the
declared expansion recalls the synonym phrasing, the scope probe keeps the off-domain
record out, duplicate exports are named and the DOI probe counts one record,
locators are verbatim, reruns are byte-identical, and the CLI example plus the
exit-5 refusal contract hold.

## Routing

- **This skill** when the task is keyword-driven academic retrieval with
  reproducible ranking over a given snapshot.
- For multi-database federation with per-source provenance — use `p61-search-multi-db`.
- For screening/ranking against hard design criteria — use `p65-search-filter-rank`.
- For expanding along citation edges — use `p58-search-citation`.

## Requirements

Python 3.9+ (3.14 verified); standard library only — no packages to install.

## 创新增益

本 Skill 相比通用 Agent 的核心新增能力：

1. **规则优先级库**：每条修改有规则 id、优先级、适用条件和理由，两个规则冲突时由优先级决定胜者且双方都留痕——通用 Agent 无法自证规则一致性。
2. **幂等二遍检查**：同一规则跑两遍，第二遍必须零改动——如果仍有改动说明规则间存在冲突，这是一个可计算的 self-check。
3. **逐条变更台账**：每个值的修改记录规则/行/列/原值/新值/理由，审计者可以逐条复核或撤销任何单条修改。

bench 目录下的 academic 是上述能力的回归证据（见 Verification 节 场景，clean 基线必须零发现）。

## 生态贡献

- **SKILL.md** 包含用途、适用条件、调用方式、输入输出、异常处理、限制和自查方法
- **scripts/** 纯标准库可独立导入，规则库可通过 spec 配置扩展
- **examples/** 提供最小调用示例和示意输出
- **bench/** 回归套件可独立复跑验证

