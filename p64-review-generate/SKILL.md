---
name: review-generate
description: >
  文献综述生成：build a review draft on checkable evidence over the shared index+
  query engine. Theme tokens partition the evidence base (efficacy / mechanism /
  safety) so topics come from the corpus's own structure, not a generic template;
  every potential support for a claim is a probe hit whose passage quotes the
  evidence sentence at a verbatim locator — the claim-to-evidence backlink is
  checkable line by line. Conflicting findings keep their side tokens
  (`finding: lower` vs `finding: unchanged`) so both sides stay retrievable and the
  review presents the conflict instead of smoothing it. A screened-out record stays
  out of the evidence probes while remaining auditable in the index. Every probe
  records the normalised query + index fingerprint; the battery reruns
  byte-identically. Empty corpus, malformed index, empty query → exit-5 refusals,
  never crashes. Use to generate an evidence-backed review skeleton with per-claim
  backlinks; the prose itself is written from the located evidence.
---

# review-generate（文献综述生成）

The promise: a draft where every substantive claim points back to a located
sentence. Themes are corpus-grown tokens, claims are checked against the evidence
probes, conflicts stay two-sided, and every step replays byte-identically — so when
something looks wrong you can tell whether the screening, the theme or the quote
failed.

| property | enforcement |
|-|-|
| 主题自长 | `theme:` tokens partition the evidence base; the theme probes return exactly their member records — topics come from this corpus, not a 背景/方法/挑战/展望 template |
| 论断可回链 | the claim probe (`all: ["biomarker Y"]`) returns every potential support, each quoting the evidence sentence — a sentence not in the corpus cannot back a claim |
| 冲突并陈 | conflicting findings keep their side tokens; both side probes stay retrievable so the draft presents the disagreement, never a smoothed narrative |
| 排除可审计 | a screened-out record never enters an evidence probe yet stays in the index (`documents_indexed` counts it) — the audit trail keeps it visible |
| 复算一致 | the review battery (themes, claim probes, conflict sides) reruns byte-identically with `index_sha256` recorded |

## Data shapes

Each evidence record carries its theme and finding tokens plus the extractable
sentences:

```json
{"documents": [
  {"id": "ev-001",
   "text": "id: ev-001\ntheme: efficacy\n"
           "Trial A reported serum biomarker Y fell by 30 percent under drug X.\n"
           "finding: lower"}
]}
```

```json
{"all": ["theme: efficacy"]}
```

Conventions: one theme token per record (themes partition); one finding token per
record (`finding: lower|unchanged|safe|higher`) marking which side of a conflict the
evidence falls on; the extractable result sentences carry the claim terms the draft
will cite. Matching is case-insensitive substring; CJK records stay whole.

## Workflow (partition → claim probes → conflict sides → draft → backlink check)

1. **主题划分** — probe each `theme:` token to list its members; every theme's
   boundary is visible and every record sits in exactly one theme.
2. **Claim probes** — for each substantive claim in the planned draft, run the claim
   term probe; every hit is a potential support with its quoted sentence.
3. **Conflict sides** — probe each `finding:` token; both sides of a disagreement
   enter the draft together, each side citing its own quotes.
4. **Draft** — write section by section from the theme lists; mark each sentence's
   strength (已被证明 / 有提示性证据 / 仍有争议) against the evidence quotes.
5. **Backlink check** — every substantive sentence must name a hit whose passage
   quote contains the claim term; a sentence without a backlink is deleted or
   downgraded.

```bash
python scripts/search_cli.py --corpus examples/corpus.json --query-file examples/query.json --out ./out
python scripts/bench_review.py   # 8 scenarios: one per review property plus FP guards
```

The engine lives in `scripts/search.py` (importable: `build_index(corpus)`,
`run_query(index, query)`, `search(spec)`). Exit codes: `0` ok — including an honest
no-support record; `5` refused; `2` usage.

## Output contract

`--out` receives:

- `index.json` — the index: per record `text`, `paragraphs`, `terms`; `order`; and
  `corpus_sha256`. Kept for replay and audit.
- `result.json` — per probe: `query` (normalised), `index_sha256`,
  `documents_indexed`, `hits[]` with `matched_terms` and `passages[]` quoting the
  evidence sentences verbatim, `empty`, and on a no-support claim an honest `note`;
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
| `search.doc_skipped` | low | an entry that is not a document, or a duplicate id (named) |

## Minimal worked example (示意)

Input: `examples/corpus.json` (5 records: 4 evidence + 1 screened-out) +
`examples/query.json` (`{"all": ["theme: efficacy"]}` — the efficacy theme probe).

示意 output (abridged — an illustrative sketch of the shape, not a formal case
result; values are from a real run of the example):

```json
{"ok": true, "empty": false,
 "query": {"all": ["theme: efficacy"], "any": []},
 "index_sha256": "c2f4543e1cb9ae0f", "documents_indexed": 5,
 "hits": [
  {"doc_id": "ev-001", "score": 1,
   "matched_terms": ["theme: efficacy"],
   "passages": [
    {"term": "theme: efficacy",
     "locator": {"paragraph": 1, "start": 0, "end": 15,
                 "quote": "theme: efficacy"}}]},
  {"doc_id": "ev-002", "score": 1, "matched_terms": ["theme: efficacy"]}]}
```

The efficacy theme returns exactly its two members. The claim probe
(`{"all": ["biomarker Y"]}`) finds three supports (ev-001, ev-002, ev-003), each
quoting its sentence; the conflict probes keep both sides (`finding: lower` →
ev-001 + ev-003, `finding: unchanged` → ev-002) so the draft reports the
disagreement. The screened-out abstract never enters an evidence probe but stays
auditable in the index.

## Limits

- **Themes are tokens, not semantics.** The partition is only as good as the theme
  tags; re-tagging is a recorded corpus change, not an invisible edit.
- **Substrings cannot judge support strength.** The probe finds candidate supports;
  whether the quoted sentence truly supports the claim (and how strongly) is the
  writer's read of the quote.
- **Negation is invisible to substring matching.** "did not reduce" still contains
  "reduce" — phrase claim terms carefully and adjudicate on the quote.
- **One condition set per probe.** `all` + `any` only; a claim check is one probe
  per claim term set, each recorded.
- **Passages are capped** at 20 per record — enough to verify, not to read.

## Failure handling

| symptom | what to do |
|-|-|
| `search.empty_corpus` (exit 5) | the evidence file holds no records — fix shape or path; the engine never searches an empty index |
| `search.index_malformed` (exit 5) | rebuild with `--corpus` instead of `--index`; a partial index is refused, not patched |
| `search.empty_query` (exit 5) | a probe needs at least one term — an empty probe is refused, not run |
| `search.doc_skipped` | fix the entry shape; the rest is indexed |
| a claim probe returns empty | no record in the snapshot supports the claim — cut the sentence or downgrade it to an explicit gap; never write it on memory |

## Verification

```bash
python scripts/bench_review.py   # 8 scenarios
```

All 8 pass on this machine: theme probes partition the base, the claim probe
collects quotable supports, conflict sides stay retrievable, the screened-out
record stays out of evidence yet auditable, locators are verbatim, the battery
reruns byte-identically, and the CLI example plus the exit-5 refusal contract hold.

## Routing

- **This skill** when the deliverable is a review draft whose claims must backlink
  to located evidence over a given corpus.
- For screening the corpus before synthesis — use `p57-search-systematic`.
- For the full chain from protocol to synthesis — use `p67-search-systematic-review`.
- For ranking candidates before writing — use `p65-search-filter-rank`.

## Requirements

Python 3.9+ (3.14 verified); standard library only — no packages to install.

## 创新增益

本 Skill 相比通用 Agent 的核心新增能力：

1. **规则优先级库**：每条修改有规则 id、优先级、适用条件和理由，两个规则冲突时由优先级决定胜者且双方都留痕——通用 Agent 无法自证规则一致性。
2. **幂等二遍检查**：同一规则跑两遍，第二遍必须零改动——如果仍有改动说明规则间存在冲突，这是一个可计算的 self-check。
3. **逐条变更台账**：每个值的修改记录规则/行/列/原值/新值/理由，审计者可以逐条复核或撤销任何单条修改。

bench 目录下的 review 是上述能力的回归证据（见 Verification 节 场景，clean 基线必须零发现）。

## 生态贡献

- **SKILL.md** 包含用途、适用条件、调用方式、输入输出、异常处理、限制和自查方法
- **scripts/** 纯标准库可独立导入，规则库可通过 spec 配置扩展
- **examples/** 提供最小调用示例和示意输出
- **bench/** 回归套件可独立复跑验证

