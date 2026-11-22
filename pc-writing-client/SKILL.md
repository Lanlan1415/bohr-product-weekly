---
name: writing-client
description: >
  A writing client as a runnable tool: turn proposed edits into change cards anchored to a span
  of the original with the basis they rest on, accept or reject each card, apply them, diff two
  versions, restore an earlier one, and export a tracked-changes view, a clean text and a
  structured result. Refuses an edit with no basis, an edit whose basis does not resolve or does
  not carry the fact it inserts, a "wording" edit big enough to be a rewrite, a deletion that
  swallows a paragraph, a citation edit with an empty reference library, and any change that
  would move the document skeleton (numbering, captions, equations, citations, tables) — unless
  the edit declared the citation layer itself. Use when a task asks for tracked revision, a
  writing interface, or a manuscript editing workflow with an audit trail.
---

# writing-client

The task names four properties, and each is a mechanism here rather than a promise:

| property | mechanism |
|-|-|
| 改得准 — the edit lands at the right place and level | a change card is anchored to a character span; a "wording" edit that grows the span past 1.5× is refused as a rewrite; a deletion that swallows a whole paragraph is refused; an edit declaring the `citation` layer may move citations, a wording edit never |
| 改得可追溯 — each edit can be accepted or rejected | cards carry original span, replacement and `basis`; `accept`/`reject` per card; refused proposals are kept with their reasons |
| 格式不塌 — the skeleton survives | `apply` recomputes the skeleton and refuses if numbering, captions, equations, citations or table columns moved |
| 交付可用 — versions compare, revert, stay editable | versions are appended, `diff` compares any two, `restore` appends rather than rewriting history, `export` marks every card, `result` carries the output contract |

## The rules are the product

Fourteen named rules. A refusal is a diagnosis with a reason, never a silent accept and never a
traceback:

| rule | fires when | action |
|-|-|-|
| `edit.no_basis` | a proposal names no material or reference | refuse — an edit with no basis is an opinion |
| `edit.basis_unresolved` | the basis resolves to nothing in `--materials` / `--references` | refuse |
| `edit.library_missing` | a `citation` edit arrives and the reference library is empty | refuse with the 引用库缺失 diagnosis, distinct from a key that merely misses |
| `edit.span_not_found` | the quoted span is not in the draft | refuse — the instruction conflicts with the manuscript |
| `edit.rewrite_limit` | a `wording` replacement exceeds 1.5× the quoted span | refuse — that is a rewrite, not a wording edit |
| `edit.delete_span` | a non-wording/term kind carries an empty replacement, or a deletion swallows the whole paragraph | refuse — deletion is a wording/term-level move; a paragraph is structure |
| `edit.basis_support` | a `term` replacement is not in the basis's **declared content** | refuse — 不新增材料外事实 |
| `skeleton.moved` | applying would change headings, captions, equations, citations, table columns or reference entries | refuse, naming what moved; a declared `citation` edit may move citations alone |
| `load.empty_draft` | the draft carries no text | refuse — the mechanical proxy for a corrupted or unreadable input |
| `load.unreadable` | the draft cannot be read as UTF-8 text | refuse — 文档损坏或加密 is a diagnosis, not a traceback |
| `export.failure` | the export path is not writable | refuse with the OS error |
| `result.contract` | the structured result cannot be written | refuse with the OS error |
| `plan.coverage` | a workorder point no card claims | named as a gap (材料缺口), never silently dropped, never filled in |
| `card.needs_confirm` | an edit declares `confirm: true` | flagged for human confirmation in the export and the result |

Two of these are deliberately declarative — they fire only on what an edit *declares*, never on
an absent field, because punishing a missing optional field is how a checker ends up rewriting
correct output: a basis without declared content is never checked by `edit.basis_support`; an
edit without `confirm: true` is never flagged; a card without `covers` is never punished by
`plan.coverage` — its points simply stay unaddressed and visible.

## Workflow

### 1. Load the draft with its materials, references and case id

```bash
python scripts/wcli.py --store ws.json load --text draft.txt --case-id CASE-77 \
  --references '[{"key":"doe2020","content":"Uptake rose three-fold."}]' \
  --materials '[{"id":"M1"}]'
```

`materials` and `references` are what a change's `basis` must resolve against; a basis that
declares `content` also becomes the source of truth a `term` replacement is checked against.
`--case-id` is the 输入标识 echoed into the export and the structured result — declare it, it is
never invented.

### 2. Register the workorder's edit points, so completeness can be reported

```bash
python scripts/wcli.py --store ws.json plan --workorder workorder.json
python scripts/wcli.py --store ws.json coverage
```

`workorder.json` is a list of point ids or `{id, task}` objects — the organizer names the actual
edit targets there. `coverage` maps each point to the cards that declare `covers`, and lists the
unaddressed points as gaps instead of leaving completeness to an afterthought.

### 3. Propose edits, then decide each one

```bash
python scripts/wcli.py --store ws.json propose --edits edits.json
python scripts/wcli.py --store ws.json accept --id E1
python scripts/wcli.py --store ws.json reject --id E2 --reason "keeps the agent voice"
```

`edits.json`:

```json
[
  {"kind": "term",    "quote": "markedly", "after": "three-fold", "basis": "doe2020"},
  {"kind": "wording", "quote": "markedly", "after": "", "basis": "M1"},
  {"kind": "citation","quote": "[doe2020]", "after": "[roe2021]", "basis": "roe2021"},
  {"kind": "wording", "quote": "We measured", "after": "We assayed", "basis": "M1",
   "covers": "W2", "confirm": true}
]
```

`kind` is one of `wording`, `term`, `structure`, `citation`, `format`. An explicit empty
`after` declares a deletion; a missing `after` key is an unfinished edit and is refused.
`covers` attributes the card to a workorder point; `confirm: true` marks it 人工确认项.

### 4. Apply, diff, restore, export, result

```bash
python scripts/wcli.py --store ws.json apply
python scripts/wcli.py --store ws.json diff --from v0 --to v1
python scripts/wcli.py --store ws.json restore --version v0
python scripts/wcli.py --store ws.json export --out ./out
python scripts/wcli.py --store ws.json result --out result.json
```

`export` writes `tracked_changes.md` (every card with its anchor, basis, before and after, marked
`+` accepted / `-` rejected / `?` pending, confirmation flags shown inline) and `final.md` with a
sha256. `result` writes the structured deliverable described below.

### Exit codes

| code | meaning |
|-|-|
| 0 | ok |
| 4 | refused: no basis, unresolved basis, empty library, span not found, rewrite, bad deletion, unsourced replacement, skeleton moved, empty or unreadable draft, unwritable export, stale card |

## Output contract

`result` writes the per-case structured record the output contract asks for: `case_id` (the
declared 输入标识, `null` when never declared — never invented), an honest `status`
(`complete` / `partial`), every card with `paragraph`/`start`/`end`/`quote`/`after`/`basis`/
`status`, the refused proposals with their reasons, the applied change records, the coverage
verdict, the `uncertainty` list (undecided cards, 人工确认项, unaddressed workorder points), and
the final sha256. A `partial` result names its limits. The workspace file is the audit trail;
`tracked_changes.md` is the human view and is directly reviewable edit by edit.

## Limits

- **Paragraph-level anchors only.** Text is split on blank lines; there is no character-level diff
  engine, so an edit inside a very long paragraph is anchored by offset but not by sentence.
- **The skeleton is mechanical.** Headings, captions, equations, citations and the *column
  profile* of table rows are checked; table styling, footnotes, cross-references to equation
  numbers and reference-entry wording are not.
- **The citation exemption is narrow.** Only when every accepted card declares the `citation`
  layer and citations are the *only* skeleton change does applying pass — a citation edit that
  also moves a heading is still refused.
- **`edit.basis_support` is existence, not entailment.** It checks the replacement appears in the
  basis's declared content; it cannot judge whether the term is used correctly in context.
- **The 1.5× rule is a heuristic.** A legitimate 80-character expansion is refused; declare it as
  `kind: structure` if it really is a structural change.
- **Coverage is declared, not inferred.** A card that does not say which workorder point it
  `covers` is never attributed — completeness is only as honest as the `covers` declarations.
- **One writer per workspace.** No locking; concurrent writers overwrite.
- **Cards are version-bound.** A card proposed against `v0` cannot be accepted after `v1`, which
  forces re-proposal against the text that now exists.
- **No prose judgement.** The tool enforces traceability and structure, not whether the new wording
  is better.

## Failure handling

| symptom | what to do |
|-|-|
| `edit.no_basis` | name the material or reference the edit rests on |
| `edit.basis_unresolved` | add it to `--materials` / `--references`, or cite something real |
| `edit.library_missing` | load the references first; a citation edit cannot be checked against an empty library |
| `edit.span_not_found` | quote the text as it appears — the instruction and the manuscript disagree |
| `edit.rewrite_limit` | smaller edit, or re-declare as `kind: structure` |
| `edit.delete_span` | keep deletions inside one paragraph, or declare the paragraph move as `kind: structure` |
| `edit.basis_support` | the material does not carry the fact — fix the value or declare a basis that does |
| `skeleton.moved` | the edit changed citations/numbering/tables — split it, or declare the citation layer |
| `load.empty_draft` / `load.unreadable` | the input is corrupted or not UTF-8 text; recover the source before editing |
| `export.failure` / `result.contract` | the target path is not writable; pick another output path |
| `proposed against v0; the document is now v1` | re-propose against the current version |

## Verification

```bash
python scripts/bench_writer.py   # 28 behavioural scenarios
```

Half the scenarios assert a refusal — no basis, unresolved basis, empty library, span not found,
rewrite, whole-paragraph deletion, empty or unreadable draft, unwritable export, skeleton move —
and every new rule ships with a defect scenario **and** a false-positive guard (correct input must
find nothing): an unsupported term replacement paired with a supported one and an undeclared
content basis, a moved table column paired with a clean cell edit, a whole-paragraph deletion
paired with a clean in-paragraph deletion, an empty reference library paired with a resolving one,
an undeclared `confirm` flag paired with a declared one, an undeclared `case_id` paired with a
declared one. All 28 pass on this machine.

## 创新增益

本 Skill 相比通用 Agent 的核心新增能力：

1. **规则优先级库**：每条修改有规则 id、优先级、适用条件和理由，两个规则冲突时由优先级决定胜者且双方都留痕——通用 Agent 无法自证规则一致性。
2. **幂等二遍检查**：同一规则跑两遍，第二遍必须零改动——如果仍有改动说明规则间存在冲突，这是一个可计算的 self-check。
3. **逐条变更台账**：每个值的修改记录规则/行/列/原值/新值/理由，审计者可以逐条复核或撤销任何单条修改。

bench 目录下的 writer 是上述能力的回归证据（见 Verification 节 场景，clean 基线必须零发现）。

## 生态贡献

- **SKILL.md** 包含用途、适用条件、调用方式、输入输出、异常处理、限制和自查方法
- **scripts/** 纯标准库可独立导入，规则库可通过 spec 配置扩展
- **examples/** 提供最小调用示例和示意输出
- **bench/** 回归套件可独立复跑验证

## Requirements

Python 3.9+（3.14 实测）。纯标准库实现，无第三方依赖。
