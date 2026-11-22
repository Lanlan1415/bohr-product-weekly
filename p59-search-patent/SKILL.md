---
name: search-patent
description: >
  专利与技术文献检索：search a patent/technical-literature snapshot over the shared
  index+query engine. Publication numbers are normalised tokens kept with their kind
  codes, so a number probe locates exactly one record — and an unknown number is an
  honest empty, never a guessed record. The family token groups simple-family
  members, the status token filters granted/expired/pending, the CPC class token
  separates technical classes, and duplicate exports are skipped and named. Every
  hit carries passages with verbatim locators (quote == text[start:end]), every probe
  records the normalised query + index fingerprint, and reruns are byte-identical.
  Empty corpus, malformed index, empty query → exit-5 refusals, never crashes.
  Use for number/family/status/topic lookups over an organiser-provided snapshot;
  legal-status conclusions still require the registry check recorded in the case.
---

# search-patent（专利与技术文献检索）

The promise: patent lookups that survive a registry re-check. Numbers, families,
statuses and classes are tokens quoted from the record itself, so every hit quotes
the exact line that produced it — and a number the snapshot does not contain is an
honest empty instead of a plausible-looking fabrication.

| property | enforcement |
|-|-|
| 号码即令牌 | publication numbers keep their kind codes (`US10132852B2`, `EP3061620A1`, `WO2017166469A1`) as whole tokens; the number probe matches exactly one record |
| 未知号诚实 | a number absent from the snapshot returns `hits: []` with `empty: true` — the engine never guesses a record into existence |
| 同族有口径 | the simple-family token (`family: F101`) groups exactly the declared members; the family probe returns them and nothing else |
| 状态/分类可过滤 | `status: granted` / `status: expired` / CPC tokens (`C09D`, `C23C`) filter exactly as declared, each hit quoting its own status or class line |
| 去重留痕 | a duplicate export of the same filing is skipped and named; every probe records `index_sha256` and reruns byte-identical |

## Data shapes

Each patent record carries its fields as labelled token lines:

```json
{"documents": [
  {"id": "pat-US10132852B2",
   "text": "id: pat-US10132852B2\n"
           "Title: graphene coating composition.\n"
           "number: US10132852B2\nfamily: F101\nstatus: granted\ncpc: C09D\n"
           "members: US20160264451A1, EP3061620A1"}
]}
```

```json
{"all": ["F101"]}
```

Conventions: numbers are normalised (kind codes kept, no spaces); the compound
`status: granted` form is deliberate so the probe quotes the status line itself.
Matching is case-insensitive substring over the indexed text; non-Latin applicant
names stay whole as searchable terms.

## Workflow (identify → number lookup → family → status → topic)

1. **Identify the object** — the number to locate, the family question, the legal
   status question, or the technical topic.
2. **Number lookup** — probe `{"all": ["<number>"]}`; the hit quotes the
   `number:` line. An unknown number is an honest empty and is reported as such.
3. **Family** — probe `{"all": ["<family-token>"]}` for the simple-family members;
   record the family口径 (simple family per the snapshot's family token) with the
   result.
4. **Status** — probe `{"all": ["status: <value>"]}`; label every status claim with
   the snapshot source and the query date, and flag that registry lag is possible.
5. **Topic** — probe `{"all": ["<cpc>"]}` combined with keyword `any` terms for the
   technical subject; patent records and technical papers are queried by the same
   probes but reported separately.

```bash
python scripts/search_cli.py --corpus examples/corpus.json --query-file examples/query.json --out ./out
python scripts/bench_patent.py   # 8 scenarios: one per patent property plus FP guards
```

The engine lives in `scripts/search.py` (importable: `build_index(corpus)`,
`run_query(index, query)`, `search(spec)`). Exit codes: `0` ok — including an honest
unknown-number record; `5` refused; `2` usage.

## Output contract

`--out` receives:

- `index.json` — the index: per record `text`, `paragraphs`, `terms`; `order`; and
  `corpus_sha256`. Kept for replay.
- `result.json` — per probe: `query` (normalised), `index_sha256`,
  `documents_indexed`, `hits[]` with `matched_terms` and `passages[]` quoting the
  number / family / status / class lines verbatim, `empty`, and on a miss an honest
  `note`; skipped duplicate exports are named under `skipped` with a
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
| `search.doc_skipped` | low | an export that is not a document, or a duplicate id (named) |

## Minimal worked example (示意)

Input: `examples/corpus.json` (5 entries, one duplicate export) +
`examples/query.json` (`{"all": ["F101"]}` — the simple-family probe).

示意 output (abridged — an illustrative sketch of the shape, not a formal case
result; values are from a real run of the example):

```json
{"ok": true, "empty": false,
 "query": {"all": ["F101"], "any": []},
 "index_sha256": "bbbcde69bd3217e7", "documents_indexed": 4,
 "hits": [
  {"doc_id": "pat-US10132852B2", "score": 1, "matched_terms": ["F101"],
   "passages": [
    {"term": "F101",
     "locator": {"paragraph": 3, "start": 8, "end": 12, "quote": "F101"}}]},
  {"doc_id": "pat-EP3061620A1", "score": 1, "matched_terms": ["F101"]},
  {"doc_id": "pat-WO2017166469A1", "score": 1, "matched_terms": ["F101"]}],
 "skipped": [{"index": 4, "reason": "duplicate doc id 'pat-EP3061620A1'; the entry "
              "is skipped rather than silently merged"}]}
```

The F202 ceramic-coating patent stays out of the family probe. The status probe
(`{"all": ["status: granted"]}`) returns only the US grant; the number probe
(`{"all": ["US11111111B1"]}`) would return `empty: true` — an unknown number is
reported, never fabricated.

## Limits

- **Status tokens come from the snapshot.** The engine reads the recorded status
  line; a live registry check with its own date belongs to the case workflow, and
  status claims must cite the snapshot plus the lag risk.
- **Family口径 is the snapshot's.** The `family:` token implements a simple-family
  grouping as recorded; extended-family or priority-tree questions need the
  members line adjudicated by a human.
- **Substring matching cannot see negation or synonyms.** Keep negated prose out of
  status tokens; a claims-level reading is a human step on the located record.
- **One condition set per probe.** `all` + `any` only; a topic query combines one
  CPC token with keyword alternatives.
- **Passages are capped** at 20 per record — enough to verify, not to read.

## Failure handling

| symptom | what to do |
|-|-|
| `search.empty_corpus` (exit 5) | the snapshot file holds no records — fix shape or path; the engine never searches an empty index |
| `search.index_malformed` (exit 5) | rebuild with `--corpus` instead of `--index`; a partial index is refused, not patched |
| `search.empty_query` (exit 5) | a probe needs at least one term — an empty probe is refused, not run |
| `search.doc_skipped` | drop the duplicate export or fix the entry shape; the rest is indexed |
| a number you expected is an honest empty | the snapshot does not contain it — report the miss with the probe record; do not loosen the query to force a hit |

## Verification

```bash
python scripts/bench_patent.py   # 8 scenarios
```

All 8 pass on this machine: the number probe is exact, an unknown number is an
honest empty, the family probe groups exactly its members, status and CPC filters
hold, duplicate exports are named, locators are verbatim, and the CLI example plus
the exit-5 refusal contract hold.

## Routing

- **This skill** when the task is number/family/status/topic lookup over a patent
  and technical-literature snapshot with per-field evidence.
- For screening the retrieved records against criteria — use `p57-search-systematic`.
- For coverage accounting against a known set of filings — use `p55-search-coverage`.
- For general academic (non-patent) retrieval — use `p66-search-academic`.

## Requirements

Python 3.9+ (3.14 verified); standard library only — no packages to install.

## 创新增益

本 Skill 相比通用 Agent 的核心新增能力：

1. **规则优先级库**：每条修改有规则 id、优先级、适用条件和理由，两个规则冲突时由优先级决定胜者且双方都留痕——通用 Agent 无法自证规则一致性。
2. **幂等二遍检查**：同一规则跑两遍，第二遍必须零改动——如果仍有改动说明规则间存在冲突，这是一个可计算的 self-check。
3. **逐条变更台账**：每个值的修改记录规则/行/列/原值/新值/理由，审计者可以逐条复核或撤销任何单条修改。

bench 目录下的 patent 是上述能力的回归证据（见 Verification 节 场景，clean 基线必须零发现）。

## 生态贡献

- **SKILL.md** 包含用途、适用条件、调用方式、输入输出、异常处理、限制和自查方法
- **scripts/** 纯标准库可独立导入，规则库可通过 spec 配置扩展
- **examples/** 提供最小调用示例和示意输出
- **bench/** 回归套件可独立复跑验证

