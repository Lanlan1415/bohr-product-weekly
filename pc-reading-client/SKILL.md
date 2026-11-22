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

## 运行时入口（每案例六步）

1. **读输入**：`/input/case.json` 与 `task.md`。从 case.json 取 `case_id` 与 `output_contract`
   字段清单——两者必须出现在最终 result.json 里。
2. **取文本**：PDF 先用 `pdftotext`（保留换页符 U+000C）抽成带分页结构的文本；纯文本直接用。
   抽不出文本层（扫描件）→ 如实走拒绝路径，不猜。
3. **打开文档**：`open --doc-file`（分页符自动变页码）或 `open --text --page-starts`。
4. **定位与提问/批注**：`find` → `ask`（可带 `--evidence-quote` 让答案自带证据）→ `note`。
5. **复核**：`verify` → `export`（锚点失效即拒写）。
6. **落盘契约**：`result --case /input/case.json --out /app/output`——写 result.json，
   case_id + output_contract 全字段回填（引擎已有值保留、spec 携带值直通、推导不出 null+limits）。

任务措辞 → 动作：找段落→find；选中文本问答→ask；划线批注→note；生成阅读记录→export；
只问不读/网络检索→越界，如实说明本客户端不做检索。

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

## Quick start

```bash
python scripts/cli.py --store ws.json open --doc-id paper --doc-file extracted.txt
python scripts/cli.py --store ws.json find --doc-id paper --quote "Uptake rose three-fold"
python scripts/cli.py --store ws.json ask  --doc-id paper --quote "Uptake rose three-fold" \
  --question "what was the measured effect?" --answer "uptake rose three-fold" \
  --evidence-quote "Only one coating thickness was tested"
python scripts/cli.py --store ws.json note --doc-id paper --quote "Only one coating thickness" \
  --text "the report itself flags this limitation"
python scripts/cli.py --store ws.json verify
python scripts/cli.py --store ws.json export --out session.md
python scripts/cli.py --store ws.json result --case /input/case.json --out /app/output
```

`export` runs `verify` first and refuses to write if any anchor is stale. `ask` refuses an answer
whose `--evidence-quote` is not in the document — an answer carrying no evidence is a refusal,
not an edge case.

## Output contract

每个案例 result.json 三段对齐题目要求：

| 题目三段 | result.json 落点 | 完成标准 |
|-|-|-|
| 阅读/解析结果 | `reading_result`（documents+sha256、anchors、verify 结果） | 覆盖任务要求且能回到材料定位 |
| 证据与边界 | `evidence_and_boundaries`（逐锚点 + unreported 清单） | 关键结论可复核，无法判断不写成事实 |
| 运行状态 | `status`（done/review/undetermined）+ `run_state`（退出码语义与人工接管位置） | 异常原因与接管位置清楚 |

`case_id` 顶层回填；`output_contract` 字段——引擎已有的保留、spec 携带的直通、推导不出的
null + limits 注记。拒绝路径（store/case 不可读）写 undetermined result.json，exit 5，永不
traceback。

## Exit codes

| code | meaning |
|-|-|
| 0 | ok / result written |
| 2 | usage error |
| 3 | `find` matched nothing |
| 4 | refused: quote absent, evidence absent, anchor invalid, or export blocked |
| 5 | undetermined: unreadable store/case/document, unwritable output |

## Limits

- **Plain text only.** A PDF enters as extracted text (`pdftotext` keeps form feeds, which
  `--doc-file` turns into page numbers); PDF layout, figures and tables are outside this client.
  A scanned page with no text layer cannot produce verifiable anchors — declared, not guessed.
- **Page breaks are declared, not inferred.** Inferring them would make every page number an
  unverifiable estimate.
- **Anchors are exact substrings.** A paraphrase cannot anchor; a selection spanning a page
  break lands on the paragraph that holds the quote, and the export shows that page only.
- **Anchors do not survive a document edit.** That is intentional: `verify` reports the break
  rather than silently re-pointing the anchor.
- **One workspace, one reader.** Concurrent writers will overwrite each other; there is no lock.
- **No retrieval.** The client stores what you ask and where it came from; choosing the question
  is the reader's job.

## 异常处置

| 情形 | 处置 |
|-|-|
| 扫描件无文本层 | 抽取为空 → 如实拒绝（exit 5），建议先 OCR；不猜测内容 |
| 加密 / 超大文件 | 读取失败 exit 5 + 原因；超大文件建议先切分再打开 |
| 选区跨页 | 锚点落在引文所在段落，页码取该段所属页；导出如实标注 |
| 引文是转述不在原文 | find 无命中 exit 3 / ask exit 4 —— 锚点只收逐字串 |
| 问答缺少依据 | `--evidence-quote` 不在原文 → exit 4 拒绝记录该答案 |
| 批注写入失败 | store 不可写 exit 5 + 原因，数据不丢（内存态不假装已保存） |
| 导出被失效锚点拦截 | exit 4 + invalid 清单，重新 find 后再导出 |
| workspace 损坏 / 不是 JSON | result 命令写 undetermined result.json`rc.refused`，其余命令一行 JSON 原因，exit 5 |
| 文档重开内容已变 | verify 点名失效锚点，不静默改址 |
| case.json 不可读 | result 命令写 undetermined result.json，exit 5 |

## Verification

```bash
python scripts/bench_reader.py   # 10 behavioural scenarios
```

Each scenario drives the CLI and asserts a property: the golden path keeps its anchors, a quote
that is absent is refused, a stale anchor blocks export, the session survives process exit, a
page number follows the declared breaks, a form-feed file gets real page numbers, the result
echoes case_id + output_contract (carried value直通, undeducible null+limits), bad case/store
refuse exit 5 with result.json, a missing document refuses exit 5, and an answer whose
evidence quote is absent is refused while a real one is bound. All 10 pass on this machine.

## Requirements

Python 3.9+（3.14 实测）。纯标准库实现，无第三方依赖。

## 创新增益

1. **可复验证锚点**：page+paragraph+char range+quote 四元组，任何人可复算
   `paragraph[start:end] == quote`——通用 Agent 的引用通常是页码级，无法机械复核。
   边界：不适用扫描件（无文本层），已声明。
2. **声明式页码**：页码来自显式分页结构（分页符），不是推断——页码可审计
   （`derived_page_starts` 留痕）。证据：bench page_attribution + docfile_formfeed。
3. **答案自带证据**：`--evidence-quote` 强制答案引用原文并先定位后入库——"答案没有依据"
   被机械拒绝（rubric 点名失败模式）。证据：bench ask_evidence_quote。
4. **会话文件化**：workspace 是磁盘文件，进程退出后重读——阅读状态跨会话保持且可复放。
5. **拒绝即产品**：引文缺失/锚点失效/证据缺失全部结构化拒绝，不静默填空。
   证据：bench quote_absent + anchor_goes_stale + result_refusals。

## 生态贡献

- **SKILL.md**：用途、触发条件、六步运行时入口、任务措辞路由、输出契约、异常处置 10 行、限制
- **scripts/**：`reader.py`（工作区/锚点/导出库）与 `cli.py`（命令入口）纯标准库可独立导入
- **examples/**：最小调用示例与示意输出（标注"示例"）
- **scripts/bench_reader.py**：10 场景行为回归可独立复跑，report_reader.json 留痕
- **数据格式**：workspace JSON 与 session.md 导出格式有文档，第三方可复用
- **适用范围**：文本层 PDF 与纯文本；扫描件边界已声明
- **限制**：Limits 节逐条列出
- **维护**：退出码语义与运行契约固定，版本随包提交
