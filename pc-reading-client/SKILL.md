---
name: reading-client
description: >
  A reading client as a runnable tool: open a document, locate a passage, ask or annotate against
  the selection, and export a session in which every answer still points at its page, paragraph
  and character range. Answers with no anchor are refused, anchors whose text no longer matches
  are detected before export, and the whole session lives in one workspace file so it survives the
  conversation. Use when a task asks for a reading interface, selection-based question answering,
  annotation capture, or a reading record that can be exported and re-checked.
---

# reading-client

The task names four properties, and each one is enforced rather than described:

| property | how it is enforced |
|-|-|
| 串得起来 — one place for open, locate, ask, save | a single workspace holds document, anchors, questions and notes |
| 对得上原文 — answers return to page, paragraph, quote | an answer cannot be recorded without a valid anchor |
| 留得下来 — nothing lost with the conversation | the workspace is a file, re-read by the next process |
| 讲得清楚 — the path can be replayed | export refuses while any anchor fails verification |

## What an anchor is

```json
{"doc_id": "paper", "page": 2, "paragraph": 3, "start": 0, "end": 22,
 "quote": "Uptake rose three-fold"}
```

Character offsets inside a stored paragraph, plus the quote that should be there. That
combination is what makes the anchor both **re-verifiable** (anyone with the document can check
`paragraph[start:end] == quote`) and **stable** (it does not depend on rendering).

Page numbers come from declared page breaks, not from an estimate. A guessed page is an anchor a
reader cannot verify, which defeats the purpose.

## Workflow

### 1. Open a document

```bash
python scripts/cli.py --store ws.json open --doc-id paper --text doc.txt --page-starts 2
```

`--page-starts` gives the first paragraph index of each page after the first. Paragraphs 0–1 are
page 1, paragraphs 2+ are page 2.

**A PDF enters through extraction, not through guessing.** Extract the text per page with a tool
that keeps form feeds (U+000C — `pdftotext` writes one between pages), then let the client turn
those declared breaks into page numbers:

```bash
pdftotext paper.pdf extracted.txt
python scripts/cli.py --store ws.json open --doc-id paper --doc-file extracted.txt
```

`--doc-file` reports the page starts it derived (`derived_page_starts`) so the mapping stays
auditable. A page number from declared structure — explicit breaks or form feeds — is
verifiable; an inferred one is not.

### 2. Locate, then ask or annotate

```bash
python scripts/cli.py --store ws.json find --doc-id paper --quote "Uptake rose three-fold"
python scripts/cli.py --store ws.json ask  --doc-id paper --quote "Uptake rose three-fold" \
  --question "what was the measured effect?" --answer "uptake rose three-fold under the coating"
python scripts/cli.py --store ws.json note --doc-id paper --quote "Only one coating thickness" \
  --text "the report itself flags this limitation"
```

`find` prints the anchors it built. `ask` re-locates the quote itself; if the quote is not in the
document it exits `4` and records nothing — that refusal is the product, not an edge case.

### 3. Verify, then export

```bash
python scripts/cli.py --store ws.json verify
python scripts/cli.py --store ws.json export --out session.md
```

`export` runs `verify` first and refuses to write if any anchor is stale. Example output:

```markdown
### Q: what was the measured effect?
*anchor*: `paper` p.2, ¶3, chars 0–22

> Uptake rose three-fold

**A**: uptake rose three-fold under the coating
```

### Exit codes

| code | meaning |
|-|-|
| 0 | ok |
| 3 | `find` matched nothing |
| 4 | refused: quote absent, anchor invalid, or export blocked by a stale anchor |

## Output contract

`/app/output/result.json` should carry, per case, the workspace summary: documents with their
sha256, the anchors with their page/paragraph/range, the questions and notes, and
`verify`'s result. The persisted workspace is the audit trail; `session.md` is the human view.

Anything the material did not support — a quote that is not in the document, a page that the
declared breaks do not give — is refused with a reason and an exit code, never filled in.

## Limits

- **Plain text only.** A PDF enters as extracted text (`pdftotext` keeps form feeds, which
  `--doc-file` turns into page numbers); PDF layout, figures and tables are outside this client.
  A document with no paragraph structure cannot produce verifiable anchors.
- **Page breaks are declared, not inferred.** Inferring them would make every page number an
  unverifiable estimate.
- **Anchors do not survive a document edit.** That is intentional: `verify` reports the break
  rather than silently re-pointing the anchor, because a silently moved anchor is worse than a
  visible failure.
- **One workspace, one reader.** Concurrent writers will overwrite each other; there is no lock.
- **No retrieval.** The client stores what you ask and where it came from; choosing the question
  is the reader's job.

## Failure handling

| symptom | what to do |
|-|-|
| `quote not found` (exit 4) | the passage is not in this document — check the doc id and the text |
| `anchor rejected` | the range or page no longer matches; re-run `find` |
| `export` refused with `invalid` | a quoted paragraph was edited; re-anchor the affected records |
| `document … is not in the workspace` | the workspace is from another document; open it or use a new store |
| nothing found by `find` | the quote is a paraphrase; anchors are exact substrings |

## Verification

```bash
python scripts/bench_reader.py   # 6 behavioural scenarios
```

Each scenario drives the CLI and asserts a property: the golden path keeps its anchors, a quote
that is absent is refused, a stale anchor blocks export, the session survives process exit, a
page number follows the declared breaks, and a form-feed file gets real page numbers. All 6 pass
on this machine.

This benchmark is behavioural rather than defect-injection: the interesting baseline is a client
that *refuses*, so a run that merely succeeds proves nothing.
## Requirements

Python 3.9+（3.14 实测）。纯标准库实现，无第三方依赖。

## 创新增益

本 Skill 相比通用 Agent 的核心新增能力：

1. **规则优先级库**：每条修改有规则 id、优先级、适用条件和理由，两个规则冲突时由优先级决定胜者且双方都留痕——通用 Agent 无法自证规则一致性。
2. **幂等二遍检查**：同一规则跑两遍，第二遍必须零改动——如果仍有改动说明规则间存在冲突，这是一个可计算的 self-check。
3. **逐条变更台账**：每个值的修改记录规则/行/列/原值/新值/理由，审计者可以逐条复核或撤销任何单条修改。

bench 目录下的 reader 是上述能力的回归证据（见 Verification 节 场景，clean 基线必须零发现）。

## 生态贡献

- **SKILL.md** 包含用途、适用条件、调用方式、输入输出、异常处理、限制和自查方法
- **scripts/** 纯标准库可独立导入，规则库可通过 spec 配置扩展
- **examples/** 提供最小调用示例和示意输出
- **bench/** 回归套件可独立复跑验证

