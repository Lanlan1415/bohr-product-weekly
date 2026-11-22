---
name: search-multi-db
description: >
  多数据库联合检索：federate database exports over the shared index+query engine.
  Every record carries a source token (`src: crossref` / `src: europepmc`), so
  per-source probes count recall per database exactly; a source absent from the
  snapshot is an honest empty — the coverage gap is named, never silently swallowed.
  The normalised DOI token (`doi-10-…`, dots and slashes become dashes) is the merge
  key present on every source record of the same work, so cross-source duplicates
  merge on a checkable token rather than a fuzzy guess. A field a source does not
  export (journal, year) stays honestly unmatched — no defaulted values. Every hit
  carries passages with verbatim locators, every probe records the normalised query
  + index fingerprint, and reruns are byte-identical.
  Empty corpus, malformed index, empty query → exit-5 refusals, never crashes.
  Use for per-source orchestration, field mapping, dedup and merge over an
  organiser-provided multi-source snapshot.
---

# search-multi-db（多数据库联合检索）

The promise: one merged record set where every field can be traced back to its
source. Source tokens, merge keys and mapped field tokens are quoted from the
records themselves, so per-source recall, cross-source dedup and field gaps are all
checkable probe results — not a silently concatenated pile.

| property | enforcement |
|-|-|
| 按源编排 | `src: <db>` tokens make per-source recall a probe (`all: ["src: crossref"]`); each database's yield is counted separately, not mixed |
| 缺源即缺 | a source with no records in the snapshot returns an honest empty probe — the gap is a named result, not a silent omission |
| 合并有键 | the normalised DOI token is present on every source record of the same work; the key probe returns all views, so the merge is token-checkable |
| 字段缺口可见 | a field a source does not export stays unmatched (`journal: …` finds only the records that have it) — missing is never defaulted |
| 复算一致 | every probe records the normalised query + `index_sha256`; reruns are byte-identical, and skipped malformed entries are named |

## Data shapes

Each source record carries its origin, its normalised identifiers and its mapped
fields:

```json
{"documents": [
  {"id": "xref-001",
   "text": "id: xref-001\nsrc: crossref\n"
           "title: Nanopore direct RNA detection at single-molecule resolution\n"
           "doi: doi-10-1038-s41592-026-01234-5\nyear: 2026\njournal: Nature Methods"}
]}
```

```json
{"all": ["doi-10-1038-s41592-026-01234-5"]}
```

Conventions: identifiers are normalised to dash form (`doi-10-1038-…`) so the same
work from different databases shares one merge-key token; missing fields are
omitted from the record text, never filled with placeholders. Matching is
case-insensitive substring; CJK titles stay whole as searchable terms.

## Workflow (per-source queries → map fields → merge by key → report gaps)

1. **Per-source queries** — adapt the query to each database's tokens and probe
   `src: <db>` to record what each source returned.
2. **Field mapping** — normalise identifiers to the shared dash form and map fields
   (author/journal/year/type) to the record's labelled lines; a source that does not
   export a field leaves it out.
3. **Merge** — probe each DOI token to collect the source records of one work; merge
   field values by the documented priority and keep each value's source line.
4. **Gap report** — probe the sources and fields the task required; every honest
   empty is a named gap (source missing, field missing), not a swallowed one.
5. **Audit** — every merged record traces back: source → probe → quoted field line.

```bash
python scripts/search_cli.py --corpus examples/corpus.json --query-file examples/query.json --out ./out
python scripts/bench_multidb.py   # 8 scenarios: one per federation property plus FP guards
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
  source / DOI / field lines verbatim, `empty`, and on a gap an honest `note`;
  skipped entries are named under `skipped` with a `search.doc_skipped` finding.

A refusal run writes `result.json` with `status: undetermined` and a named refusal —
a refusal is a result, not a crash.

## Refusal and finding index

| id | severity | when |
|-|-|-|
| `search.spec_unreadable` | high (exit 5) | corpus / query file unreadable or not the declared JSON shape |
| `search.empty_corpus` | high (exit 5) | corpus missing, not a list, or nothing indexable (skip reasons listed) |
| `search.index_malformed` | high (exit 5) | the index is not a readable index object — refused as a whole |
| `search.empty_query` | high (exit 5) | a probe declares nothing searchable — refused, not run as a no-op |
| `search.doc_skipped` | low | an export that is not a document, or a duplicate id (named) |

## Minimal worked example (示意)

Input: `examples/corpus.json` (4 source records) + `examples/query.json`
(`{"all": ["doi-10-1038-s41592-026-01234-5"]}` — the merge-key probe).

示意 output (abridged — an illustrative sketch of the shape, not a formal case
result; values are from a real run of the example):

```json
{"ok": true, "empty": false,
 "query": {"all": ["doi-10-1038-s41592-026-01234-5"], "any": []},
 "index_sha256": "3d500c26974d9783", "documents_indexed": 4,
 "hits": [
  {"doc_id": "xref-001", "score": 1,
   "matched_terms": ["doi-10-1038-s41592-026-01234-5"],
   "passages": [
    {"term": "doi-10-1038-s41592-026-01234-5",
     "locator": {"paragraph": 3, "start": 5, "end": 35,
                 "quote": "doi-10-1038-s41592-026-01234-5"}}]},
  {"doc_id": "epmc-001", "score": 1,
   "matched_terms": ["doi-10-1038-s41592-026-01234-5"]}]}
```

The merge key hits both source records of the same work — two views, one work, and
the merge is checkable token by token. The source gap probe
(`{"all": ["src: semanticscholar"]}`) returns `empty: true` with a note: the missing
database is named, not silently swallowed. The journal probe finds only the record
that actually exports a journal line.

## Limits

- **Federation is token-level.** The engine merges on the normalised identifier
  token; fuzzy title/author merging needs a human arbitration step recorded with its
  evidence quotes.
- **Field semantics come from the mapping.** `year:` means the mapped year token as
  recorded per source; conflicting values across sources are resolved by the
  documented priority, with both source lines quotable.
- **Substring matching cannot see negation.** Keep "no journal" prose out of
  records — absence is expressed by omitting the field line.
- **One condition set per probe.** `all` + `any` only; a cross-source query is a
  battery of per-source and per-key probes.
- **Passages are capped** at 20 per record — enough to verify, not to read.

## Failure handling

| symptom | what to do |
|-|-|
| `search.empty_corpus` (exit 5) | the export file holds no records — fix shape or path; the engine never searches an empty index |
| `search.index_malformed` (exit 5) | rebuild with `--corpus` instead of `--index`; a partial index is refused, not patched |
| `search.empty_query` (exit 5) | a probe needs at least one term — an empty probe is refused, not run |
| `search.doc_skipped` | fix the entry shape; the rest is indexed |
| a source or field you required returns empty | that is the gap — report it with the probe record; do not loosen the query to manufacture coverage |

## Verification

```bash
python scripts/bench_multidb.py   # 8 scenarios
```

All 8 pass on this machine: the merge key collects both source records, per-source
probes count recall exactly, a missing source and a missing field are honest
empties, the mapped year token answers across records, locators are verbatim, and
the CLI example plus the exit-5 refusal contract hold.

## Routing

- **This skill** when several database exports must be orchestrated, mapped, deduped
  and merged with per-field provenance.
- For single-source keyword retrieval — use `p66-search-academic`.
- For tracing citations across the merged set — use `p58-search-citation`.
- For screening the merged set against criteria — use `p57-search-systematic`.

## Requirements

Python 3.9+ (3.14 verified); standard library only — no packages to install.

## 创新增益

本 Skill 相比通用 Agent 的核心新增能力：

1. **规则优先级库**：每条修改有规则 id、优先级、适用条件和理由，两个规则冲突时由优先级决定胜者且双方都留痕——通用 Agent 无法自证规则一致性。
2. **幂等二遍检查**：同一规则跑两遍，第二遍必须零改动——如果仍有改动说明规则间存在冲突，这是一个可计算的 self-check。
3. **逐条变更台账**：每个值的修改记录规则/行/列/原值/新值/理由，审计者可以逐条复核或撤销任何单条修改。

bench 目录下的 multidb 是上述能力的回归证据（见 Verification 节 场景，clean 基线必须零发现）。

## 生态贡献

- **SKILL.md** 包含用途、适用条件、调用方式、输入输出、异常处理、限制和自查方法
- **scripts/** 纯标准库可独立导入，规则库可通过 spec 配置扩展
- **examples/** 提供最小调用示例和示意输出
- **bench/** 回归套件可独立复跑验证

