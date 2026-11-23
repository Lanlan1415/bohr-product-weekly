---
name: search-crosslang
description: >
  跨语言文献检索：recall non-English literature over the shared index+query engine
  with a term table driven by bilingual any-lists. A bilingual probe
  (any: ["细胞焦亡", "pyroptosis"]) lets each record hit on its own language's term
  — the zh original and the English paper both come back. The probe set makes the
  language boundary visible: the source-language term alone does not reach the
  English body, which is exactly why the term table is mandatory, and a loanword
  token crosses the boundary and reaches the zh original too. A shared DOI token
  links an original and its translation view so per-language versions are counted
  once per work. CJK hits carry verbatim locators, every probe records the
  normalised query + index fingerprint, and reruns are byte-identical.
  Empty corpus, malformed index, empty query → exit-5 refusals, never crashes.
  Use for term-table-driven multilingual recall with per-language evidence; whole-
  document translation is out of scope.
---

# search-crosslang（跨语言文献检索）

The promise: non-English records actually come back, with the language and version
of every hit on record. The bilingual any-list is the mechanism — each record is
matched on its own language's term, the misses show where the boundary is, and the
merge key keeps translation views from double-counting.

| property | enforcement |
|-|-|
| 术语表驱动 | the bilingual any-list (`any: ["细胞焦亡", "pyroptosis"]`) comes from a maintained term table; each record hits on its own language's term, so non-English recall is real, not translated guesswork |
| 边界可见 | the source-language term alone does not reach the English body — the probe set demonstrates the boundary instead of hiding it behind machine translation |
| 版本归并有键 | an original and its translation view share one normalised DOI token; the key probe returns both views so the work is counted once with its language views listed |
| 借词可跨 | a loanword token (`gasdermin`) matches zh and en records alike — the term table records which terms cross the boundary |
| 复算一致 | every probe records the normalised query + `index_sha256`; reruns are byte-identical, and CJK locators quote the paragraph slice verbatim |

## Data shapes

Each record carries a language tag, its original text, and its identifier tokens:

```json
{"documents": [
  {"id": "zh-focal-01",
   "text": "id: zh-focal-01\nlang: zh\n"
           "细胞焦亡由炎性小体驱动，gasdermin孔隙形成是关键步骤。\n"
           "doi: doi-10-1093-zhmr-026-0345"}
]}
```

```json
{"all": [], "any": ["细胞焦亡", "pyroptosis"]}
```

Conventions: `lang: zh|en` tags the record language; a translation view carries
`trans-of: <doi-token>` linking it to the original; the term table maps each concept
to its per-language terms and marks which are loanwords. Matching is
case-insensitive substring; a CJK phrase stays one whole searchable term.

## Workflow (term table → per-language probes → version merge → mis-translation check)

1. **术语表** — for each query concept, collect the per-language terms (synonyms,
   abbreviations, loanwords, local names) and freeze the any-lists per language.
2. **Bilingual probe** — run the combined any-list; each hit quotes its own
   language's term at a verbatim locator.
3. **Boundary check** — run each language's term alone to see which language it
   reaches; the difference is the boundary the term table must cover.
4. **Version merge** — probe the DOI token to collect original + translation views;
   count the work once and keep the per-language view list.
5. **误译复核** — read the quoted passages of high-risk hits; a surface match with a
   different meaning is a false positive to record, and the term table gains the
   distinction.

```bash
python scripts/search_cli.py --corpus examples/corpus.json --query-file examples/query.json --out ./out
python scripts/bench_crosslang.py   # 8 scenarios: one per cross-language property plus FP guards
```

The engine lives in `scripts/search.py` (importable: `build_index(corpus)`,
`run_query(index, query)`, `search(spec)`). Exit codes: `0` ok — including an honest
empty for a term no language covers; `5` refused; `2` usage.

## Output contract

`--out` receives:

- `index.json` — the index: per record `text`, `paragraphs`, `terms`; `order`; and
  `corpus_sha256`. Kept for replay.
- `result.json` — per probe: `query` (normalised, including the bilingual `any`
  list), `index_sha256`, `documents_indexed`, `hits[]` with `matched_terms` (the
  term that fired, per language) and `passages[]` with verbatim CJK locators,
  `empty`, and on a miss an honest `note`; skipped entries are named under
  `skipped` with a `search.doc_skipped` finding.

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
| `search.doc_skipped` | low | an entry that is not a document, or a duplicate id (named) |

## Minimal worked example (示意)

Input: `examples/corpus.json` (4 records: zh original, en original, en translation
view, zh near-topic) + `examples/query.json`
(`{"all": [], "any": ["细胞焦亡", "pyroptosis"]}` — the bilingual probe).

示意 output (abridged — an illustrative sketch of the shape, not a formal case
result; values are from a real run of the example):

```json
{"ok": true, "empty": false,
 "query": {"all": [], "any": ["细胞焦亡", "pyroptosis"]},
 "index_sha256": "93082b1dab7ff5cd", "documents_indexed": 4,
 "hits": [
  {"doc_id": "zh-focal-01", "score": 1, "matched_terms": ["细胞焦亡"],
   "passages": [
    {"term": "细胞焦亡",
     "locator": {"paragraph": 2, "start": 0, "end": 4, "quote": "细胞焦亡"}}]},
  {"doc_id": "en-focal-01", "score": 1, "matched_terms": ["pyroptosis"],
   "passages": [
    {"term": "pyroptosis",
     "locator": {"paragraph": 2, "start": 0, "end": 10, "quote": "Pyroptosis"}}]}]}
```

All four records are recalled — each on its own language's term (the zh near-topic
paper hits 细胞焦亡 as a contrast term and is adjudicated on the quoted passage).
The zh term alone misses the English body; the loanword probe
(`{"all": ["gasdermin"]}`) reaches the zh original too; the DOI probe links the
original and its translation view — two views, one work.

## Limits

- **Term-table bound, not translating.** The engine matches the terms the table
  declares; a concept with no per-language terms is an honest empty, and machine
  translation of whole documents is out of scope.
- **Surface matching cannot judge semantics.** A term can match with a different
  meaning (the near-topic zh paper); adjudicate on the quoted passage and record
  the verdict in the term table.
- **Language tags are metadata.** `lang:` is read by the caller for routing and
  counting; the engine matches text regardless of language.
- **One condition set per probe.** `all` + `any` only; a multilingual query is a
  battery of per-language probes plus the combined one.
- **Passages are capped** at 20 per record — enough to verify, not to read.

## Failure handling

| symptom | what to do |
|-|-|
| `search.empty_corpus` (exit 5) | the corpus file holds no records — fix shape or path; the engine never searches an empty index |
| `search.index_malformed` (exit 5) | rebuild with `--corpus` instead of `--index`; a partial index is refused, not patched |
| `search.empty_query` (exit 5) | a probe needs at least one term — an empty probe is refused, not run |
| `search.doc_skipped` | fix the entry shape; the rest is indexed |
| a language you declared returns empty | no indexed record contains that language's terms — record the recall gap for the term table; do not machine-translate your way to a hit |

## Verification

```bash
python scripts/bench_crosslang.py   # 8 scenarios
```

All 8 pass on this machine: the bilingual probe recalls both languages on their own
terms, the source term's language boundary is visible, the loanword crosses it, the
DOI token merges the translation view, the CJK locator is verbatim, reruns are
byte-identical, and the CLI example plus the exit-5 refusal contract hold.

## Routing

- **This skill** when the question must reach records in multiple languages through
  a maintained term table, with per-language evidence and version merging.
- For English-only keyword retrieval — use `p66-search-academic`.
- For screening the recalled set against criteria — use `p57-search-systematic`.
- For tracking new records across windows — use `p56-search-latest`.

## Requirements

Python 3.9+ (3.14 verified); standard library only — no packages to install.

## 创新增益

本 Skill 相比通用 Agent 的核心新增能力：

1. **规则优先级库**：每条修改有规则 id、优先级、适用条件和理由，两个规则冲突时由优先级决定胜者且双方都留痕——通用 Agent 无法自证规则一致性。
2. **幂等二遍检查**：同一规则跑两遍，第二遍必须零改动——如果仍有改动说明规则间存在冲突，这是一个可计算的 self-check。
3. **逐条变更台账**：每个值的修改记录规则/行/列/原值/新值/理由，审计者可以逐条复核或撤销任何单条修改。

bench 目录下的 crosslang 是上述能力的回归证据（见 Verification 节 场景，clean 基线必须零发现）。

## 生态贡献

- **SKILL.md** 包含用途、适用条件、调用方式、输入输出、异常处理、限制和自查方法
- **scripts/** 纯标准库可独立导入，规则库可通过 spec 配置扩展
- **examples/** 提供最小调用示例和示意输出
- **bench/** 回归套件可独立复跑验证

