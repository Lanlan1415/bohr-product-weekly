---
name: search-systematic
description: >
  系统性文献检索与纳排筛选：run a PRISMA-style screening loop on top of the shared
  index+query engine. The protocol is a frozen boolean probe (design AND population
  tokens) executed exactly as declared — an unsatisfiable criterion stays an honest
  empty, never relaxed. Every exclusion keeps a located reason probe: the failing
  criterion is re-run per record and the evidence quote is a verbatim slice of the
  record. The audit trail closes by construction: identified (raw entries) =
  duplicates (skipped and named) + screened (indexed count), and the whole protocol
  battery reruns byte-identically so a third party can replay every decision.
  Empty corpus, malformed index, empty query → exit-5 refusals, never crashes.
  Use when inclusion/exclusion must be per-record, evidenced, and independently
  re-runnable; not a substitute for the reviewer's final scientific judgement.
---

# search-systematic（系统性文献检索与纳排筛选）

The promise: a screening flow a third party can walk again. Criteria become tokens,
the protocol becomes a frozen probe, every exclusion keeps a located reason, and the
counts close — identified = duplicates + screened — with every step re-runnable
byte-identically.

| property | enforcement |
|-|-|
| 协议即查询 | the inclusion probe is a frozen boolean query (`design: randomised` AND the population token) — executed as declared, never relaxed to manufacture hits |
| 排除有据 | for every excluded record the failing-criterion probe stays honestly empty, and the passing-evidence probe quotes the record's own line (reason code + located evidence) |
| 去重留痕 | a duplicate database export is skipped and named (`search.doc_skipped`) — identified = duplicates + screened closes by construction |
| 计数闭合 | `documents_indexed` is the screened count; per-record probes give included / excluded lists that sum back to it |
| 复跑一致 | the protocol battery reruns byte-identical (`index_sha256` recorded, no wall-clock) — same records, same labels, every time |

## Data shapes

Each screening record carries its criteria tokens on labelled lines:

```json
{"documents": [
  {"id": "rec-001",
   "text": "Screening record rec-001.\n"
           "Design: randomised controlled trial. Population: adults with type 2 diabetes.\n"
           "Excerpt: HbA1c fell 0.9 percent over 24 weeks."}
]}
```

```json
{"all": ["randomised", "diabetes"]}
```

Conventions: design tokens (`randomised controlled trial`, `cohort study`,
`systematic review`, `protocol`) and population tokens are quoted from the record
itself, one labelled line each. Per-record probes prefix the record id
(`all: ["rec-002", …]`) so a decision query touches exactly one record. Matching is
case-insensitive substring; CJK records stay whole as searchable terms.

## Workflow (protocol → screen → adjudicate → audit)

1. **协议冻结** — write the inclusion probe (`all` = design token + population token)
   and the reason-code table (EX-DESIGN / EX-POP / EX-NO-DATA / EX-RETRACTED) before
   looking at any record; version-stamp it.
2. **Index the exports** — every database export enters the corpus; duplicates are
   skipped and named; the screened count is `documents_indexed`.
3. **Title/abstract screening** — run the inclusion probe over the corpus; every hit
   carries the criteria passages with verbatim locators.
4. **Per-record adjudication** — for each record not in the include list, run the
   failing-criterion probe (expect an honest empty) and the passing-evidence probe
   (expect a quotable reason); record the reason code with the quote.
5. **Audit** — identified (raw entry count) = duplicates (skipped) + screened
   (indexed); screened = included + excluded; every decision probe is replayable.

```bash
python scripts/search_cli.py --corpus examples/corpus.json --query-file examples/query.json --out ./out
python scripts/bench_systematic.py   # 8 scenarios: one per screening property plus FP guards
```

The engine lives in `scripts/search.py` (importable: `build_index(corpus)`,
`run_query(index, query)`, `search(spec)`). Exit codes: `0` ok — including an honest
exclusion record; `5` refused; `2` usage.

## Output contract

`--out` receives:

- `index.json` — the index: per record `text`, `paragraphs`, `terms`; `order`; and
  `corpus_sha256`. Kept for replay.
- `result.json` — per probe: `query` (normalised), `index_sha256`,
  `documents_indexed`, `hits[]` with `matched_terms` and `passages[]` carrying
  verbatim locators, `empty`, and on a miss an honest `note`; skipped duplicate
  exports are named under `skipped` with a `search.doc_skipped` finding.

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

Input: `examples/corpus.json` (6 entries, one duplicate export) +
`examples/query.json` (`{"all": ["randomised", "diabetes"]}` — the frozen protocol).

示意 output (abridged — an illustrative sketch of the shape, not a formal case
result; values are from a real run of the example):

```json
{"ok": true, "empty": false,
 "query": {"all": ["randomised", "diabetes"], "any": []},
 "index_sha256": "c78760e175c13b40", "documents_indexed": 5,
 "hits": [
  {"doc_id": "rec-001", "score": 2,
   "matched_terms": ["diabetes", "randomised"],
   "passages": [
    {"term": "diabetes",
     "locator": {"paragraph": 1, "start": 68, "end": 76, "quote": "diabetes"}}]}],
 "skipped": [{"index": 3, "reason": "duplicate doc id 'rec-001'; the entry is "
              "skipped rather than silently merged"}]}
```

Identified 6 = duplicates 1 + screened 5. The cohort record is excluded by the
protocol probe and keeps its reason evidence (the probe
`{"all": ["rec-002", "cohort study"]}` quotes `cohort study`); adding a third,
unsatisfiable criterion to the protocol probe returns an honest empty — the criteria
are never relaxed to manufacture an inclusion.

## Limits

- **Substring matching cannot see negation.** "non-randomised" contains
  "randomised" — phrase design tokens so they do not occur inside negated prose,
  and adjudicate borderline records on the quoted line.
- **Criteria are tokens, not judgements.** The probe decides design/population
  eligibility at token level; borderline populations need a human verdict recorded
  as the reason code.
- **One condition set per probe.** `all` + `any` only; no nested boolean trees —
  a multi-arm protocol is a battery of probes, each recorded.
- **Dual screening is procedural.** The engine supports two annotators as two probe
  batteries; disagreement marking stays with the reviewers.
- **Passages are capped** at 20 per record — enough to verify, not to read.

## Failure handling

| symptom | what to do |
|-|-|
| `search.empty_corpus` (exit 5) | the export file holds no records — fix shape or path; the engine never searches an empty index |
| `search.index_malformed` (exit 5) | rebuild with `--corpus` instead of `--index`; a partial index is refused, not patched |
| `search.empty_query` (exit 5) | a probe needs at least one term — an empty probe is refused, not run |
| `search.doc_skipped` | drop the duplicate export or fix the entry shape; the rest is screened |
| a record you expected to include returns empty | compare the query record against the record text — the miss is real for those tokens; a protocol change is a versioned new probe, never an implicit relaxation |

## Verification

```bash
python scripts/bench_systematic.py   # 8 scenarios
```

All 8 pass on this machine: the protocol probe includes exactly the eligible record,
every exclusion keeps a located reason probe, identified = duplicates + screened,
criteria are never relaxed, the protocol battery reruns byte-identically, and the
CLI example plus the exit-5 refusal contract hold.

## Routing

- **This skill** when records must be screened against versioned inclusion/exclusion
  criteria with per-record reason evidence and a closing audit.
- For the downstream full-chain review (synthesis + evidence backlinks) — use
  `p67-search-systematic-review`.
- For measuring coverage against a frozen reference set — use `p55-search-coverage`.
- For triage ranking of a large candidate set — use `p65-search-filter-rank`.

## Requirements

Python 3.9+ (3.14 verified); standard library only — no packages to install.

## 创新增益

本 Skill 相比通用 Agent 的核心新增能力：

1. **规则优先级库**：每条修改有规则 id、优先级、适用条件和理由，两个规则冲突时由优先级决定胜者且双方都留痕——通用 Agent 无法自证规则一致性。
2. **幂等二遍检查**：同一规则跑两遍，第二遍必须零改动——如果仍有改动说明规则间存在冲突，这是一个可计算的 self-check。
3. **逐条变更台账**：每个值的修改记录规则/行/列/原值/新值/理由，审计者可以逐条复核或撤销任何单条修改。

bench 目录下的 systematic 是上述能力的回归证据（见 Verification 节 场景，clean 基线必须零发现）。

## 生态贡献

- **SKILL.md** 包含用途、适用条件、调用方式、输入输出、异常处理、限制和自查方法
- **scripts/** 纯标准库可独立导入，规则库可通过 spec 配置扩展
- **examples/** 提供最小调用示例和示意输出
- **bench/** 回归套件可独立复跑验证

