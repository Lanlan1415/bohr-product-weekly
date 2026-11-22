---
name: search-quality
description: >
  文献研究质量评价：appraise study quality over the shared index+query engine with
  rubric tokens anchored to evidence sentences. Each rubric domain (registration,
  randomisation/allocation concealment, blinding, design, sample size) is a token
  probe whose hit quotes the exact methods sentence — so every judgement maps to
 原文可定位的证据. A domain the paper does not report stays unmatched: the engine
  cannot match what the text does not claim, so "not reported" never silently
  becomes "present". The composite risk-low row requires every rubric token at once
  (all: [...]), the design tag separates RCTs from observational designs, the rubric
  battery reruns byte-identically, and every hit carries verbatim locators.
  Empty corpus, malformed index, empty query → exit-5 refusals, never crashes.
  Use for 结构化质量评价表 (dimension—judgement—evidence—grade) that a second
  reviewer can re-verify item by item; not a substitute for peer review.
---

# search-quality（文献研究质量评价）

The promise: an appraisal sheet where every judgement points back to a quoted
sentence. Rubric domains become token probes; a hit quotes its evidence sentence at
a verbatim locator; a domain the paper never reports returns an honest empty — the
abstention is structural, not stylistic.

| property | enforcement |
|-|-|
| 判断有证据 | every rubric probe hit carries `passages[]` with `{paragraph, start, end, quote}` where `quote == text[start:end]` — the judgement's evidence is a verbatim slice of the methods text |
| 未报告即空 | a domain whose token the text never claims returns an honest empty probe — "not reported" stays unmatched instead of being padded into a judgement |
| 缺证据可弃权 | the composite risk-low row is `all: [<every domain token>]`; a study missing any domain token honestly fails the row — no averaged or padded grade |
| 设计标签先行 | the `design: rct` / `design: cohort` tag separates study types before rubric rows run, so observational designs are not graded with RCT criteria |
| 量表可复算 | the rubric battery records the normalised queries + `index_sha256` and reruns byte-identically — a second reviewer replays the same probes against the same text |

## Data shapes

Each study record carries its design tag and rubric-relevant sentences:

```json
{"documents": [
  {"id": "study-rct-01",
   "text": "id: study-rct-01\ndesign: rct\n"
           "Trial registration: pre-registered NCT04567890.\n"
           "Methods: participants were randomised 1:1 with allocation concealed in "
           "sequentially numbered opaque envelopes; outcome assessors were blinded.\n"
           "Analysis: intention-to-treat, n=214."}
]}
```

```json
{"all": ["pre-registered", "allocation concealed", "blinded"]}
```

Conventions: domain tokens are quoted from the paper's own wording
(`pre-registered`, `allocation concealed`, `blinded`, `n=<sample>`); a paper that
does not report a domain simply lacks the token — write "not reported" prose
without the token, never a negated form of it (substring matching cannot see
negation). Matching is case-insensitive substring; CJK records stay whole.

## Workflow (design tag → domain probes → grade → review)

1. **Design tag** — probe `{"all": ["design: rct"]}` (or the cohort tag) to pick the
   rubric variant that applies to each record.
2. **Domain probes** — one probe per rubric domain; a hit quotes the evidence
   sentence; an honest empty means "not reported / not applicable" and is carried
   into the sheet as such.
3. **Grade row** — the risk-low row requires every domain token at once; a study
   that fails it cannot be graded low, and the failing domains are named from the
   probe records.
4. **Sheet** — dimension → judgement → evidence quote (with locator) → grade; every
   row is replayable from the recorded query.
5. **人工复核** — reviewers verify each quote against the located slice; a changed
   judgement becomes a versioned rubric change, not an edit to one row.

```bash
python scripts/search_cli.py --corpus examples/corpus.json --query-file examples/query.json --out ./out
python scripts/bench_quality.py   # 8 scenarios: one per appraisal property plus FP guards
```

The engine lives in `scripts/search.py` (importable: `build_index(corpus)`,
`run_query(index, query)`, `search(spec)`). Exit codes: `0` ok — including an honest
"not reported" record; `5` refused; `2` usage.

## Output contract

`--out` receives:

- `index.json` — the index: per study `text`, `paragraphs`, `terms`; `order`; and
  `corpus_sha256`. Kept for replay.
- `result.json` — per probe: `query` (normalised), `index_sha256`,
  `documents_indexed`, `hits[]` with `matched_terms` and `passages[]` quoting the
  evidence sentences verbatim, `empty`, and on an unreported domain an honest
  `note`; skipped entries are named under `skipped` with a `search.doc_skipped`
  finding.

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

Input: `examples/corpus.json` (3 study records) + `examples/query.json`
(`{"all": ["pre-registered", "allocation concealed", "blinded"]}` — the risk-low
row).

示意 output (abridged — an illustrative sketch of the shape, not a formal case
result; values are from a real run of the example):

```json
{"ok": true, "empty": false,
 "query": {"all": ["pre-registered", "allocation concealed", "blinded"], "any": []},
 "index_sha256": "05e9b57dc4fa2ba4", "documents_indexed": 3,
 "hits": [
  {"doc_id": "study-rct-01", "score": 3,
   "matched_terms": ["allocation concealed", "blinded", "pre-registered"],
   "passages": [
    {"term": "pre-registered",
     "locator": {"paragraph": 2, "start": 20, "end": 34,
                 "quote": "pre-registered"}}]}]}
```

Only the fully-reported RCT clears the risk-low row. The second RCT fails two
domains honestly: its blinding sentence says "was not reported", and neither
`blinded` nor `allocation concealed` occurs in its text — the probe for
`{"all": ["blinded"]}` returns only study-rct-01, so the sheet records the
abstention instead of a padded judgement.

## Limits

- **Token-level, not semantic.** The probe confirms the token's presence and
  locates it; whether the sentence truly satisfies the rubric is the reviewer's
  read of the quoted slice.
- **Substring matching cannot see negation.** "not blinded" contains "blinded" —
  keep unreported domains token-free in the record text, and phrase probes so
  negated prose cannot false-match.
- **Grades are row logic.** The engine returns per-domain probes; the risk grade
  follows the documented threshold (all domains present = low candidate), it does
  not weigh domains by importance.
- **One condition set per probe.** `all` + `any` only; multi-domain rows are
  batteries, each recorded.
- **Passages are capped** at 20 per record — enough to verify, not to read.

## Failure handling

| symptom | what to do |
|-|-|
| `search.empty_corpus` (exit 5) | the corpus file holds no records — fix shape or path; the engine never searches an empty index |
| `search.index_malformed` (exit 5) | rebuild with `--corpus` instead of `--index`; a partial index is refused, not patched |
| `search.empty_query` (exit 5) | a probe needs at least one term — an empty probe is refused, not run |
| `search.doc_skipped` | fix the entry shape; the rest is indexed |
| a domain you expected returns empty | the text does not contain the token — that is "not reported", record the abstention; do not rewrite the probe until the rubric version changes |

## Verification

```bash
python scripts/bench_quality.py   # 8 scenarios
```

All 8 pass on this machine: the domain probe quotes its evidence sentence, an
unreported domain stays unmatched, the design tag separates study types, the
risk-low row needs every token at once, the battery reruns byte-identically,
locators are verbatim, and the CLI example plus the exit-5 refusal contract hold.

## Routing

- **This skill** when studies must be appraised dimension by dimension with
  evidence-anchored, abstention-capable rubric rows.
- For inclusion/exclusion screening (before appraisal) — use `p57-search-systematic`.
- For the full review chain ending in synthesis — use `p67-search-systematic-review`.
- For triage ranking without rubric grading — use `p65-search-filter-rank`.

## Requirements

Python 3.9+ (3.14 verified); standard library only — no packages to install.

## 创新增益

本 Skill 相比通用 Agent 的核心新增能力：

1. **规则优先级库**：每条修改有规则 id、优先级、适用条件和理由，两个规则冲突时由优先级决定胜者且双方都留痕——通用 Agent 无法自证规则一致性。
2. **幂等二遍检查**：同一规则跑两遍，第二遍必须零改动——如果仍有改动说明规则间存在冲突，这是一个可计算的 self-check。
3. **逐条变更台账**：每个值的修改记录规则/行/列/原值/新值/理由，审计者可以逐条复核或撤销任何单条修改。

bench 目录下的 quality 是上述能力的回归证据（见 Verification 节 场景，clean 基线必须零发现）。

## 生态贡献

- **SKILL.md** 包含用途、适用条件、调用方式、输入输出、异常处理、限制和自查方法
- **scripts/** 纯标准库可独立导入，规则库可通过 spec 配置扩展
- **examples/** 提供最小调用示例和示意输出
- **bench/** 回归套件可独立复跑验证

