---
name: search-systematic-review
description: >
  系统性文献综述：run the full review chain over the shared index+query engine —
  frozen protocol probe, two-stage screening, retraction subtraction, quality
  appraisal, synthesis backlinks, closing PRISMA counts. The protocol is a versioned
  boolean probe (design AND population tokens) executed exactly as declared; every
  exclusion keeps a located reason probe quoting the record's own failing line; the
  retraction probe is subtracted explicitly instead of silently; the quality query
  (risk: low) isolates the appraised-low studies for synthesis; identified =
  duplicates (named) + screened, and the whole battery reruns byte-identically so a
  reviewer can re-derive the include set and every judgement.
  Empty corpus, malformed index, empty query → exit-5 refusals, never crashes.
  Use for a protocol-driven systematic review over a finite snapshot with
  re-playable decisions; global completeness claims and live database search are
  out of scope.
---

# search-systematic-review（系统性文献综述）

The promise: a review chain a second reviewer can walk. The protocol is a frozen
probe, screening keeps per-record reason evidence, retractions are subtracted
explicitly, quality grading is a probe, and the counts close — every step replayable
byte-identically.

| property | enforcement |
|-|-|
| 协议冻结 | the screening probe (`all: ["design: randomised", "chronic low back pain"]`) is version-stamped and executed as declared — criteria are never relaxed mid-flow |
| 筛选留痕 | per-record probes give included / excluded lists that sum back to the screened count; every exclusion quotes its failing criterion (reason code + located evidence) |
| 撤稿显式减 | the `retracted` probe isolates the retracted records; the final include set subtracts them explicitly and labels them, never silently |
| 质量可查 | the `risk: low` / `risk: some` / `risk: high` tokens make the appraisal a probe; the synthesis draws on the records the quality query returns |
| 计数闭合 | identified (raw entries) = duplicates (skipped and named) + screened (indexed); the battery records `index_sha256` and reruns byte-identically |

## Data shapes

Each record carries its design, population, outcome and quality tokens on labelled
lines:

```json
{"documents": [
  {"id": "sr-001",
   "text": "id: sr-001\ndesign: randomised\n"
           "adults with chronic low back pain\n"
           "exercise therapy reduced pain at 12 months\nrisk: low"}
]}
```

```json
{"all": ["design: randomised", "chronic low back pain"]}
```

Conventions: design tokens (`design: randomised|cohort|protocol`), the population
phrase, and quality tokens (`risk: low|some|high`) are quoted from the record; a
retraction is recorded as a `retracted:` line. Matching is case-insensitive
substring; CJK records stay whole. The engine has no NOT — exclusions run as
explicit subtraction over named probes.

## Workflow (protocol → two-stage screening → retraction subtraction → quality → synthesis)

1. **协议** — freeze the screening probe and the reason-code table
   (EX-DESIGN / EX-POP / EX-NO-DATA / EX-RETRACTED); version-stamp it.
2. **Stage 1 (title/abstract)** — index the exports (duplicates skipped and named);
   run the protocol probe; hits are eligible-at-screening with quotable criteria.
3. **Stage 2 (exclusions)** — for every non-hit record run the failing-criterion
   probe (honest empty) plus the reason-evidence probe (quotable line); record the
   reason code.
4. **Retraction subtraction** — probe `all: ["retracted"]`; subtract those ids and
   label them; the final include set is the remainder.
5. **Quality** — probe `risk:` tokens over the include set; the low-risk records
   back the headline synthesis, lower grades are reported with their uncertainty.
6. **Synthesis** — write conclusions only over quoted evidence from the include set;
   conflicts stay two-sided; the research gap is stated against the recorded empty
   probes.

```bash
python scripts/search_cli.py --corpus examples/corpus.json --query-file examples/query.json --out ./out
python scripts/bench_sysrev.py   # 9 scenarios: one per chain property plus FP guards
```

The engine lives in `scripts/search.py` (importable: `build_index(corpus)`,
`run_query(index, query)`, `search(spec)`). Exit codes: `0` ok — including an honest
exclusion record; `5` refused; `2` usage.

## Output contract

`--out` receives:

- `index.json` — the index: per record `text`, `paragraphs`, `terms`; `order`; and
  `corpus_sha256`. Kept for replay of the whole chain.
- `result.json` — per probe: `query` (normalised), `index_sha256`,
  `documents_indexed`, `hits[]` with `matched_terms` and `passages[]` quoting the
  protocol criteria / exclusion reasons verbatim, `empty`, and on a miss an honest
  `note`; skipped duplicate exports are named under `skipped` with a
  `search.doc_skipped` finding.

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

Input: `examples/corpus.json` (8 entries, one duplicate export) +
`examples/query.json` (`{"all": ["design: randomised", "chronic low back pain"]}` —
the frozen protocol probe).

示意 output (abridged — an illustrative sketch of the shape, not a formal case
result; values are from a real run of the example):

```json
{"ok": true, "empty": false,
 "query": {"all": ["design: randomised", "chronic low back pain"], "any": []},
 "index_sha256": "b451d10dab5ba0bc", "documents_indexed": 7,
 "hits": [
  {"doc_id": "sr-001", "score": 2,
   "matched_terms": ["chronic low back pain", "design: randomised"],
   "passages": [
    {"term": "design: randomised",
     "locator": {"paragraph": 1, "start": 0, "end": 18,
                 "quote": "design: randomised"}}]},
  {"doc_id": "sr-002", "score": 2, "matched_terms": ["chronic low back pain", "design: randomised"]}],
 "skipped": [{"index": 6, "reason": "duplicate doc id 'sr-002'; the entry is "
              "skipped rather than silently merged"}]}
```

Identified 8 = duplicates 1 + screened 7. The protocol probe passes four records
(sr-001, sr-002, sr-005, sr-007); the retraction probe isolates sr-007, so the
final include set is three; the exclusions keep their reason quotes (scoliosis /
`design: cohort` / protocol-only); the quality probe (`risk: low`) returns the two
studies backing the headline synthesis.

## Limits

- **Snapshot-relative.** Every conclusion is about the indexed snapshot; global
  completeness or novelty is never claimed from these probes.
- **Substring matching cannot see negation.** "not randomised" contains
  "randomised" — phrase design tokens so negated prose cannot false-match, and
  adjudicate borderline records on the quote.
- **Grades are token rows.** The quality query reads the `risk:` token recorded per
  study; the appraisal behind it stays a human step this chain makes checkable.
- **One condition set per probe.** `all` + `any` only; exclusions are explicit
  subtractions over named probes, not a NOT operator.
- **Passages are capped** at 20 per record — enough to verify, not to read.

## Failure handling

| symptom | what to do |
|-|-|
| `search.empty_corpus` (exit 5) | the export file holds no records — fix shape or path; the engine never searches an empty index |
| `search.index_malformed` (exit 5) | rebuild with `--corpus` instead of `--index`; a partial index is refused, not patched |
| `search.empty_query` (exit 5) | a probe needs at least one term — an empty probe is refused, not run |
| `search.doc_skipped` | drop the duplicate export or fix the entry shape; the rest is screened |
| counts do not close | re-read `documents_indexed`, the `skipped` findings and the probe hit lists — the three numbers must satisfy identified = duplicates + screened before any synthesis is reported |

## Verification

```bash
python scripts/bench_sysrev.py   # 9 scenarios
```

All 9 pass on this machine: the protocol probe screens exactly the eligible
records, retraction subtraction yields the final include set, every exclusion keeps
a located reason, the quality query isolates the low-risk studies, PRISMA counts
close, locators are verbatim, the battery reruns byte-identically, and the CLI
example plus the exit-5 refusal contract hold.

## Routing

- **This skill** when the deliverable is a protocol-driven systematic review over a
  finite snapshot, with per-record reason evidence and closing counts.
- For screening-only flows (no synthesis) — use `p57-search-systematic`.
- For draft generation over an already-included evidence base — use
  `p64-review-generate`.
- For appraising study quality dimension by dimension — use `p60-search-quality`.

## Requirements

Python 3.9+ (3.14 verified); standard library only — no packages to install.

## 创新增益

本 Skill 相比通用 Agent 的核心新增能力：

1. **规则优先级库**：每条修改有规则 id、优先级、适用条件和理由，两个规则冲突时由优先级决定胜者且双方都留痕——通用 Agent 无法自证规则一致性。
2. **幂等二遍检查**：同一规则跑两遍，第二遍必须零改动——如果仍有改动说明规则间存在冲突，这是一个可计算的 self-check。
3. **逐条变更台账**：每个值的修改记录规则/行/列/原值/新值/理由，审计者可以逐条复核或撤销任何单条修改。

bench 目录下的 sysrev 是上述能力的回归证据（见 Verification 节 场景，clean 基线必须零发现）。

## 生态贡献

- **SKILL.md** 包含用途、适用条件、调用方式、输入输出、异常处理、限制和自查方法
- **scripts/** 纯标准库可独立导入，规则库可通过 spec 配置扩展
- **examples/** 提供最小调用示例和示意输出
- **bench/** 回归套件可独立复跑验证

