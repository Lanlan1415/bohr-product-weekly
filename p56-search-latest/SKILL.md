---
name: search-latest
description: >
  最新文献发现与追踪：run an incremental tracking loop over the shared index+query
  engine. Every record carries a leading date token, so a watermark window is a
  boolean query (all: ["YYYY-MM"]) that returns exactly the in-window records — and
  an empty window is an honest empty, not a padded reminder. Version duplicates share
  one normalised DOI token (the merge key), retracted records stay retrievable so
  they can be subtracted explicitly and labelled, and a CJK record hits with a
  verbatim locator. Every probe records the normalised query and the index
  fingerprint; the index is written beside the result and reruns are byte-identical.
  Empty corpus, malformed index, empty query → exit-5 refusals, never crashes.
  Use when the deliverable is a repeatable subscription increment (新增清单 + 依据),
  not a one-shot topic search.
---

# search-latest（最新文献发现与追踪）

The promise: an increment you can replay. Each window's answer is a boolean probe
over a fingerprinted index — the new records come with locators, the old ones stay
out, the retracted ones are subtractable, and rerunning the probe reproduces the
increment byte-identically.

| property | enforcement |
|-|-|
| 窗口是查询 | the watermark window is `all: ["YYYY-MM"]` over the leading date token — in-window records only; the previous window's records are never re-swept |
| 空窗诚实 | a window with no new records returns `hits: []` with `empty: true` and a note — an empty increment is reported, never padded |
| 版本合并有键 | preprint / published / translation views share one normalised DOI token; the token probe returns every view of one work so dedup counting is checkable |
| 撤稿可 subtraction | retracted records keep their `retracted` token, so the retraction probe isolates them for explicit subtraction and labelling — never silently dropped |
| 增量可复算 | every probe records the normalised query + `index_sha256`; reruns are byte-identical, and duplicate feed exports are skipped and named |

## Data shapes

Each record carries a leading date token, a normalised DOI token, and a status token:

```json
{"documents": [
  {"id": "snap-a1",
   "text": "[2026-03-02] Cryo-EM structures of the spike at 2.1 A resolution.\n"
           "doi: doi-10-1038-s41586-026-08101-3\nstatus: published"}
]}
```

```json
{"all": ["2026-03"]}
```

Conventions: the date token `[YYYY-MM-DD]` opens the record text; DOI/identifier
tokens are normalised to `doi-10-…` form (dots and slashes become dashes) so the
same work from different feeds shares one merge key; status tokens are
`published` / `preprint` / `retracted`. Matching is case-insensitive substring over
the indexed text; CJK titles stay whole as searchable terms.

## Workflow (watermark → window probe → increment)

1. **Record the watermark** — the last snapshot's highest date token, kept in the
   subscription config.
2. **Index the fresh pulls** — every feed export enters the corpus; duplicates
   (same id re-exported) are skipped and named so counts stay honest.
3. **Window probe** — `all: ["YYYY-MM"]` for the new window. Only in-window records
   return; each carries its locator.
4. **Merge keys** — probe each DOI token to collect its views (preprint mirror,
   translation, publisher version); count the work once, keep the version list.
5. **Retraction subtraction** — probe `all: ["retracted"]`; subtract those ids from
   the increment and label them 更正/撤稿 instead of new findings.
6. **Reminder** — the increment is: new works (merged), version updates, retractions;
   an empty window is reported as an honest empty.

```bash
python scripts/search_cli.py --corpus examples/corpus.json --query-file examples/query.json --out ./out
python scripts/bench_latest.py   # 8 scenarios: one per tracking property plus FP guards
```

The engine lives in `scripts/search.py` (importable: `build_index(corpus)`,
`run_query(index, query)`, `search(spec)`). Exit codes: `0` ok — including an honest
empty window; `5` refused; `2` usage.

## Output contract

`--out` receives:

- `index.json` — the index: per record `text`, `paragraphs`, `terms`; `order`; and
  `corpus_sha256`. Kept for replay of any increment.
- `result.json` — per probe: `query` (normalised), `index_sha256`,
  `documents_indexed`, `hits[]` with `passages[]` carrying verbatim locators,
  `empty`, and on an empty window an honest `note`; skipped duplicate exports are
  named under `skipped` with a `search.doc_skipped` finding.

A refusal run writes `result.json` with `status: undetermined` and a named refusal —
a refusal is a result, not a crash.

## Refusal and finding index

| id | severity | when |
|-|-|-|
| `search.spec_unreadable` | high (exit 5) | corpus / query file unreadable or not the declared JSON shape |
| `search.empty_corpus` | high (exit 5) | corpus missing, not a list, or nothing indexable (skip reasons listed) |
| `search.index_malformed` | high (exit 5) | the index is not a readable index object — refused as a whole |
| `search.empty_query` | high (exit 5) | a probe declares nothing searchable — refused, not run as a no-op |
| `search.doc_skipped` | low | a feed export that is not a document, or a duplicate id (named) |

## Minimal worked example (示意)

Input: `examples/corpus.json` (5 entries, one duplicate feed export) +
`examples/query.json` (`{"all": ["2026-03"]}` — the March window probe).

示意 output (abridged — an illustrative sketch of the shape, not a formal case
result; values are from a real run of the example):

```json
{"ok": true, "empty": false,
 "query": {"all": ["2026-03"], "any": []},
 "index_sha256": "c78e6549fde3b1bf", "documents_indexed": 4,
 "hits": [
  {"doc_id": "snap-a1", "score": 1, "matched_terms": ["2026-03"],
   "passages": [
    {"term": "2026-03",
     "locator": {"paragraph": 0, "start": 1, "end": 8, "quote": "2026-03"}}]},
  {"doc_id": "snap-c1", "score": 1, "matched_terms": ["2026-03"]},
  {"doc_id": "snap-d1", "score": 1, "matched_terms": ["2026-03"]}],
 "skipped": [{"index": 1, "reason": "duplicate doc id 'snap-a1'; the entry is "
              "skipped rather than silently merged"}]}
```

The February baseline record stays out; the retraction record (`snap-c1`) enters the
window but the `retracted` probe isolates it for labelling; the CJK record
(`snap-d1`) hits with a verbatim locator. A probe for `{"all": ["2026-04"]}` would
return `empty: true` — an empty window, honestly reported.

## Limits

- **The engine matches tokens, it does not know time.** The window discipline comes
  from the date-token convention and the recorded watermark; a record pulled late
  must keep its publication date token, or it will land in the wrong window.
- **Delayed ingest is explicit.** A record dated in a past window is re-found by its
  DOI token probe, not silently back-filled into an old increment.
- **Lexical matching cannot see negation or synonymy.** "not retracted" contains
  "retracted" — keep negated prose out of status tokens.
- **One condition set per probe.** `all` + `any` only; no nested boolean trees.
- **Passages are capped** at 20 per record — enough to verify, not to read.

## Failure handling

| symptom | what to do |
|-|-|
| `search.empty_corpus` (exit 5) | the pull file holds no records — fix shape or path; the engine never searches an empty index |
| `search.index_malformed` (exit 5) | rebuild with `--corpus` instead of `--index`; a partial index is refused, not patched |
| `search.empty_query` (exit 5) | a probe needs at least one term — an empty probe is refused, not run |
| `search.doc_skipped` | drop the duplicate export or fix the entry shape; the rest is indexed |
| empty window you expected to be non-empty | compare the query record against the index — the miss is real for those date tokens; check the watermark and time zone, then re-probe with the corrected window |

## Verification

```bash
python scripts/bench_latest.py   # 8 scenarios
```

All 8 pass on this machine: the window probe keeps old records out, the merge key
collapses version duplicates, the retraction probe isolates label-able records, a
CJK record's locator is verbatim, reruns are byte-identical, an empty window is
honest, and the CLI example plus the exit-5 refusal contract hold.

## Routing

- **This skill** when the task is a repeatable subscription increment over dated
  records with dedup, retraction handling, and replayable probes.
- For general academic retrieval without a watermark — use `p66-search-academic`.
- For measuring coverage against a frozen reference set — use `p55-search-coverage`.
- For screening records against inclusion/exclusion criteria — use `p57-search-systematic`.

## Requirements

Python 3.9+ (3.14 verified); standard library only — no packages to install.

## 创新增益

本 Skill 相比通用 Agent 的核心新增能力：

1. **规则优先级库**：每条修改有规则 id、优先级、适用条件和理由，两个规则冲突时由优先级决定胜者且双方都留痕——通用 Agent 无法自证规则一致性。
2. **幂等二遍检查**：同一规则跑两遍，第二遍必须零改动——如果仍有改动说明规则间存在冲突，这是一个可计算的 self-check。
3. **逐条变更台账**：每个值的修改记录规则/行/列/原值/新值/理由，审计者可以逐条复核或撤销任何单条修改。

bench 目录下的 latest 是上述能力的回归证据（见 Verification 节 场景，clean 基线必须零发现）。

## 生态贡献

- **SKILL.md** 包含用途、适用条件、调用方式、输入输出、异常处理、限制和自查方法
- **scripts/** 纯标准库可独立导入，规则库可通过 spec 配置扩展
- **examples/** 提供最小调用示例和示意输出
- **bench/** 回归套件可独立复跑验证

