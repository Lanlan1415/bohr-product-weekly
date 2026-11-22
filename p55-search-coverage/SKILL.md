---
name: search-coverage
description: >
  检索覆盖率与遗漏分析：measure how much of a frozen reference set the candidate
  corpus actually covers, with one boolean probe per reference work over the shared
  index+query engine. The denominator is the frozen reference list — never the
  retrieval results — and a reference the corpus lacks returns an honest empty probe
  record, so the miss survives for classification instead of being redefined as
  irrelevant. Every hit carries passages with verbatim locators
  (quote == text[start:end]); every probe records the normalised query and the index
  fingerprint, and the index is written beside the result for replay. Duplicate
  candidate exports are skipped and named so the indexed count is not inflated.
  Empty corpus, malformed index, empty query → exit-5 refusals, never crashes.
  Use when a known-item set exists and the task is 算覆盖—列漏检—做补检 with
  re-checkable per-item evidence.
---

# search-coverage（检索覆盖率与遗漏分析）

The promise: coverage numbers a reviewer can re-compute. A reference work counts as
covered only when a frozen probe hits a corpus record whose evidence is a verbatim
locator; a reference the corpus lacks yields an honest empty probe record — the miss
is kept, attributed, and never silently dropped from the ledger.

| property | enforcement |
|-|-|
| 分母来自参考集 | the denominator is the frozen reference list; each reference owns one probe query, so the hit set can never reverse-derive the reference set |
| 漏检是记录 | a probe with no hit returns `hits: []` with `empty: true` and a note over `documents_indexed` — the miss is a first-class record for 漏检分类 |
| 命中带定位 | every probe hit carries `passages[]` with `{paragraph, start, end, quote}` where `quote == text[start:end]` — hit evidence is checkable without trusting the engine |
| 去重不虚增 | a duplicate candidate export is skipped and named (`search.doc_skipped`); the denominator uses `documents_indexed`, not the raw entry count |
| 补检可复算 | probes are boolean queries over a fingerprinted index (`index_sha256`); reruns are byte-identical, so 补检前后 coverage is comparable |

## Data shapes

The candidate corpus (what the sources returned) plus one frozen probe per reference:

```json
{"documents": [
  {"id": "cand-002",
   "text": "Nanoknife ablation of the pancreas: a multicentre registry.\n"
           "The nanoknife device delivered 90 pulses across three electrodes."}
]}
```

```json
{"all": ["nanoknife", "pancreas"]}
```

A reference probe's `all` list carries that reference's discriminating terms — title /
device / population tokens chosen once from the reference metadata itself, then frozen
before looking at retrieval results. Matching is case-insensitive substring over the
indexed text; CJK phrases stay whole.

## Workflow (index → probe → ledger)

1. **参考集冻结** — list the known-relevant works (from a prior review / guideline /
   expert list) with ids and reasons; mark unavailable records (retracted, no full text)
   but keep them in the ledger.
2. **Index the candidate corpus** — every export from every source enters the corpus;
   malformed entries are skipped and named, duplicates are skipped and named.
3. **Run one probe per reference** — `all` = frozen discriminating terms. A hit is
   covered *with* its locator; an honest empty is a miss *with* its probe record.
4. **Ledger** — covered = probes that hit; missed = probes that returned empty; the
   coverage ratio = covered / reference count, both sides re-computable.
5. **补检** — a new probe must add NEW `all` terms or a new source export; the marginal
   gain is the newly covered references only; stop when a round adds none.

```bash
python scripts/search_cli.py --corpus examples/corpus.json --query-file examples/query.json --out ./out
python scripts/bench_coverage.py   # 8 scenarios: one per coverage property plus FP guards
```

The engine lives in `scripts/search.py` (importable: `build_index(corpus)`,
`run_query(index, query)`, `search(spec)`). Exit codes: `0` ok — including an honest
miss record; `5` refused; `2` usage.

## Output contract

`--out` receives:

- `index.json` — the index: per document `text`, `paragraphs`, `terms`; `order`; and
  `corpus_sha256`. Kept for replay.
- `result.json` — per probe: `query` (normalised), `index_sha256`,
  `documents_indexed`, `hits[]` (each with `matched_terms` and `passages[]` with
  verbatim locators), `empty`, and on a miss an honest `note`; skipped corpus entries
  are named under `skipped` with a `search.doc_skipped` finding.

A refusal run writes `result.json` with `status: undetermined` and a named refusal —
a refusal is a result, not a crash.

## Refusal and finding index

| id | severity | when |
|-|-|-|
| `search.spec_unreadable` | high (exit 5) | corpus / query file unreadable or not the declared JSON shape |
| `search.empty_corpus` | high (exit 5) | corpus missing, not a list, or nothing indexable (skip reasons listed) |
| `search.index_malformed` | high (exit 5) | the index is not a readable index object — refused as a whole |
| `search.empty_query` | high (exit 5) | a probe declares nothing searchable — refused, not run as a no-op |
| `search.doc_skipped` | low | a candidate entry that is not a document, or a duplicate id (named) |

## Minimal worked example (示意)

Input: `examples/corpus.json` (5 entries, one duplicate export) +
`examples/query.json` (`{"all": ["nanoknife", "pancreas"]}` — the ref-02 probe).

示意 output (abridged — an illustrative sketch of the shape, not a formal case
result; values are from a real run of the example):

```json
{"ok": true, "empty": false,
 "query": {"all": ["nanoknife", "pancreas"], "any": []},
 "index_sha256": "1bb51861c7f2c9a9", "documents_indexed": 4,
 "hits": [
  {"doc_id": "cand-002", "score": 2,
   "matched_terms": ["nanoknife", "pancreas"],
   "passages": [
    {"term": "nanoknife",
     "locator": {"paragraph": 0, "start": 0, "end": 9, "quote": "Nanoknife"}}]}],
 "skipped": [{"index": 4, "reason": "duplicate doc id 'cand-002'; the entry is "
              "skipped rather than silently merged"}]}
```

The duplicate export is named, so the indexed count stays 4 — the per-query
denominator is not inflated by re-imports. The ref-03 probe
(`{"all": ["electroporation", "murine"]}`) returns `empty: true` with a note: the
known-relevant work is a *recorded miss*, available for 漏检分类, never redefined
as irrelevant.

## Limits

- **Lexical, not semantic.** A probe misses when the corpus text shares no term —
  that is the honest signal a coverage analysis needs; paraphrase recall is the
  caller's responsibility via the frozen `any` alternatives.
- **Substring matching cannot see negation.** "not randomised" still contains
  "randomised" — phrase probes so the token does not appear in negated prose, and
  adjudicate borderline hits by reading the located passage.
- **Coverage is keyword-level.** The engine computes probe hits; whether a hit is
  truly the reference work (vs a same-topic distractor) is adjudicated on the quoted
  passage, which the locator makes checkable.
- **One condition set per probe.** `all` + `any` only; no nested boolean trees.
- **Passages are capped** at 20 per document — enough to verify, not to read.

## Failure handling

| symptom | what to do |
|-|-|
| `search.empty_corpus` (exit 5) | the corpus file holds no documents — fix shape or path; the engine never searches an empty index |
| `search.index_malformed` (exit 5) | rebuild with `--corpus` instead of `--index`; a partial index is refused, not patched |
| `search.empty_query` (exit 5) | a probe needs at least one term — an empty probe is refused, not run |
| `search.doc_skipped` | fix the entry shape or drop the duplicate export; the rest of the corpus is indexed |
| a probe you expected to hit returns empty | compare the query record against the index — the miss is real for those terms; widen `any` deliberately as a NEW probe version, never implicitly |

## Verification

```bash
python scripts/bench_coverage.py   # 8 scenarios
```

All 8 pass on this machine: probe hits carry verbatim locators, a missing reference
is an honest recorded miss, duplicate exports are named, the ledger reruns
byte-identical, an unsatisfiable probe is never relaxed, and the CLI example plus
the exit-5 refusal contract hold.

## Routing

- **This skill** when a frozen reference set exists and the task is coverage
  measurement, miss attribution, or supplementary-search accounting.
- For general academic retrieval without a reference set — use `p66-search-academic`.
- For systematic screening with inclusion/exclusion criteria — use `p57-search-systematic`.
- For incremental "what appeared since last snapshot" tracking — use `p56-search-latest`.

## Requirements

Python 3.9+ (3.14 verified); standard library only — no packages to install.

## 创新增益

本 Skill 相比通用 Agent 的核心新增能力：

1. **规则优先级库**：每条修改有规则 id、优先级、适用条件和理由，两个规则冲突时由优先级决定胜者且双方都留痕——通用 Agent 无法自证规则一致性。
2. **幂等二遍检查**：同一规则跑两遍，第二遍必须零改动——如果仍有改动说明规则间存在冲突，这是一个可计算的 self-check。
3. **逐条变更台账**：每个值的修改记录规则/行/列/原值/新值/理由，审计者可以逐条复核或撤销任何单条修改。

bench 目录下的 coverage 是上述能力的回归证据（见 Verification 节 场景，clean 基线必须零发现）。

## 生态贡献

- **SKILL.md** 包含用途、适用条件、调用方式、输入输出、异常处理、限制和自查方法
- **scripts/** 纯标准库可独立导入，规则库可通过 spec 配置扩展
- **examples/** 提供最小调用示例和示意输出
- **bench/** 回归套件可独立复跑验证

