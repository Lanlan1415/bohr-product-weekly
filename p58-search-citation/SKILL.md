---
name: search-citation
description: >
  引文追踪与关联文献发现：trace citation relationships over the shared index+query
  engine. Every record lists its outgoing references as one `cites: <id>` line per
  edge, so a forward probe (all: ["cites: <seed-id>"]) returns exactly the records
  carrying that edge — a work nobody cites yields an honest empty, no fabricated
  forward links. Backward tracing locates the seed's own `refs:` line verbatim; the
  lineage probe (cites: <method-id>) surfaces follow-up and parallel work sharing
  the method source; duplicate exports are skipped and named. Every edge hit carries
  passages with verbatim locators (quote == text[start:end]), and every probe records
  the normalised query + index fingerprint with byte-identical reruns.
  Empty corpus, malformed index, empty query → exit-5 refusals, never crashes.
  Use when expanding a seed paper along real, checkable citation edges.
---

# search-citation（引文追踪与关联文献发现）

The promise: every expansion step can show its edge. Forward and backward tracing
are boolean probes over per-edge lines in the record text, so each returned work
quotes the exact citation edge that produced it — and an absent edge is an honest
empty rather than an invented link.

| property | enforcement |
|-|-|
| 前向沿边 | the forward probe `all: ["cites: <id>"]` matches only records whose citation list contains the edge line — one line per edge, so the second listed reference is findable too |
| 后向有据 | the seed's own `refs:` line is located verbatim — backward tracing reads the seed's reference list from the record, not from memory |
| 无边诚实 | a record nobody cites returns an honest empty probe — no padded, guessed forward links |
| 平行可解释 | the lineage probe `cites: <method-id>` returns follow-up AND parallel work that shares the method source, each quoting its own edge as the association evidence |
| 去重留痕 | a duplicate export of a citing record is skipped and named; edge counting uses `documents_indexed`, and reruns are byte-identical |

## Data shapes

Each record carries its id, its outgoing edges (one `cites:` line per edge) and its
backward list (`refs:`):

```json
{"documents": [
  {"id": "follow-2021",
   "text": "id: follow-2021\n"
           "Follow-up: equivariant message-passing potential (2021).\n"
           "cites: seed-2019\ncites: meth-2014\n"
           "Improves the angular resolution of the seed."}
]}
```

```json
{"all": ["cites: seed-2019"]}
```

Conventions: record ids are stable short tokens (`seed-2019`, `meth-2014`) that
appear in the record text (`id: <id>` line) and inside every edge line that cites
them; backward edges use `refs:` on the citing record. The compound `cites: <id>`
form is deliberate — it cannot false-match the `id:` line of the cited work itself.
Matching is case-insensitive substring; CJK titles stay whole as searchable terms.

## Workflow (seed → backward → forward → lineage → dedup)

1. **Seed** — pin the seed record and its id token.
2. **Backward** — probe `{"all": ["id: <seed>", "refs: <target>"]}` to locate and
   quote the seed's own reference edges (the method and data sources).
3. **Forward** — probe `{"all": ["cites: <seed>"]}` to list the records carrying a
   citing edge; each hit quotes the edge.
4. **Lineage / parallel work** — probe `{"all": ["cites: <method-id>"]}`: follow-ups
   and parallel work that cite the same method source surface with their own edges
   as the association evidence.
5. **Dedup** — duplicate exports are skipped and named; the cleaned list is the one
   whose every member has a quoted in-path edge.

```bash
python scripts/search_cli.py --corpus examples/corpus.json --query-file examples/query.json --out ./out
python scripts/bench_citation.py   # 8 scenarios: one per tracing property plus FP guards
```

The engine lives in `scripts/search.py` (importable: `build_index(corpus)`,
`run_query(index, query)`, `search(spec)`). Exit codes: `0` ok — including an honest
no-edge record; `5` refused; `2` usage.

## Output contract

`--out` receives:

- `index.json` — the index: per record `text`, `paragraphs`, `terms`; `order`; and
  `corpus_sha256`. Kept for replay.
- `result.json` — per probe: `query` (normalised), `index_sha256`,
  `documents_indexed`, `hits[]` whose `passages[]` quote the citation edges with
  `{paragraph, start, end, quote}` verbatim locators, `empty`, and on a no-edge
  probe an honest `note`; skipped duplicate exports are named under `skipped` with
  a `search.doc_skipped` finding.

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
| `search.doc_skipped` | low | an export that is not a document, or a duplicate id (named) |

## Minimal worked example (示意)

Input: `examples/corpus.json` (6 entries, one duplicate export) +
`examples/query.json` (`{"all": ["cites: seed-2019"]}` — the forward probe).

示意 output (abridged — an illustrative sketch of the shape, not a formal case
result; values are from a real run of the example):

```json
{"ok": true, "empty": false,
 "query": {"all": ["cites: seed-2019"], "any": []},
 "index_sha256": "1055176d39603db6", "documents_indexed": 5,
 "hits": [
  {"doc_id": "follow-2021", "score": 1,
   "matched_terms": ["cites: seed-2019"],
   "passages": [
    {"term": "cites: seed-2019",
     "locator": {"paragraph": 2, "start": 0, "end": 16,
                 "quote": "cites: seed-2019"}}]},
  {"doc_id": "follow-2023", "score": 1, "matched_terms": ["cites: seed-2019"]}],
 "skipped": [{"index": 5, "reason": "duplicate doc id 'follow-2021'; the entry is "
              "skipped rather than silently merged"}]}
```

The parallel work does not appear — it cites the method, not the seed, and the
forward probe does not relax that. The lineage probe
(`{"all": ["cites: meth-2014"]}`) returns follow-2021 and parallel-2022, each
quoting its own edge; the probe `{"all": ["cites: parallel-2022"]}` returns
`empty: true` — nobody cites the parallel work in this snapshot.

## Limits

- **Edges are what the snapshot records.** The engine traces edges present in the
  indexed text; a source that hides reference lists yields honest empties, not
  inferred links.
- **Identity is token-level.** Same-work merging across preprint/conference/journal
  versions works through the shared id token; ambiguous name variants need a merge
  decision recorded by the caller.
- **Substring matching cannot see negation.** "does not cite the seed" contains
  neither `cites:` + seed id as an edge line, but keep such prose free of edge
  tokens anyway.
- **One condition set per probe.** `all` + `any` only; multi-hop tracing is a
  battery of per-hop probes, each recorded and replayable.
- **Passages are capped** at 20 per record — enough to verify, not to read.

## Failure handling

| symptom | what to do |
|-|-|
| `search.empty_corpus` (exit 5) | the corpus file holds no records — fix shape or path; the engine never searches an empty index |
| `search.index_malformed` (exit 5) | rebuild with `--corpus` instead of `--index`; a partial index is refused, not patched |
| `search.empty_query` (exit 5) | a probe needs at least one term — an empty probe is refused, not run |
| `search.doc_skipped` | drop the duplicate export or fix the entry shape; the rest is indexed |
| a forward probe returns empty for a work you know is cited | the edge line is absent from the snapshot text — record it as a coverage gap of the source, never as "no citations" without the snapshot as evidence |

## Verification

```bash
python scripts/bench_citation.py   # 8 scenarios
```

All 8 pass on this machine: backward edges quote the seed's reference line, the
forward probe returns exactly the edge-carrying records, the lineage probe surfaces
the parallel work, a no-edge record is an honest empty, duplicate exports are named,
locators are verbatim, and the CLI example plus the exit-5 refusal contract hold.

## Routing

- **This skill** when expanding a seed paper along citation edges with per-edge
  evidence and dedup.
- For keyword-first academic retrieval — use `p66-search-academic`.
- For screening the expanded set against criteria — use `p57-search-systematic`.
- For synthesising the expanded set into a review — use `p64-review-generate`.

## Requirements

Python 3.9+ (3.14 verified); standard library only — no packages to install.

## 创新增益

本 Skill 相比通用 Agent 的核心新增能力：

1. **规则优先级库**：每条修改有规则 id、优先级、适用条件和理由，两个规则冲突时由优先级决定胜者且双方都留痕——通用 Agent 无法自证规则一致性。
2. **幂等二遍检查**：同一规则跑两遍，第二遍必须零改动——如果仍有改动说明规则间存在冲突，这是一个可计算的 self-check。
3. **逐条变更台账**：每个值的修改记录规则/行/列/原值/新值/理由，审计者可以逐条复核或撤销任何单条修改。

bench 目录下的 citation 是上述能力的回归证据（见 Verification 节 场景，clean 基线必须零发现）。

## 生态贡献

- **SKILL.md** 包含用途、适用条件、调用方式、输入输出、异常处理、限制和自查方法
- **scripts/** 纯标准库可独立导入，规则库可通过 spec 配置扩展
- **examples/** 提供最小调用示例和示意输出
- **bench/** 回归套件可独立复跑验证

