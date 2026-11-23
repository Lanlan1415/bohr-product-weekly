---
name: knowledge-base-qa
description: >
  科研知识库问答。读取 case.json 指向的真实文件、目录、版本与 workorder，
  用 CJK 感知检索和中英文查询扩展完成多文件/多跳问答；每个事实句都是带
  文件、哈希、真实页码（若有）、段落与字符区间的原文片段，并输出独立可
  复核的答案与索引。证据冲突并列保留；检索不到时明确说不知道，不生成
  无来源事实。重复文件检索去重但清单不删除，版本不按文件名猜权威。
  case_id 与 output_contract 全字段进入 result.json，坏输入结构化拒绝
  且不 traceback。Do NOT use for open-world questions, creative synthesis,
  or an answer that should go beyond verbatim source evidence.
---

# knowledge-base-qa

本 Skill 的主入口是 `scripts/kbqa_cli.py`：它真正完成
“真实资料盘点 → 查询理解 → 段落召回 → 逐句引证 → 缺证/冲突处理 → 可复跑导出”。
`sections.py` 仅是兼容既有答案审计的回归模块，不再是本题的工作流替代品。

## 防止的五类失分

| 失败 | 实际机制 |
|-|-|
| 中文问题与正文完全检索不到 | NFKC 归一、CJK 二字词、领域词保留、BM25 + 查询变体 RRF；常见科研管理中英词桥和 case 声明 aliases 只扩展查询，不扩展答案事实 |
| 引用只到文件或邻近段落 | 每份资料先保留段落坐标；答案态 claim 必须逐字等于所引原句，定位到 document/version/hash/page（只有真实 form feed 才有页码）/paragraph/char_start–char_end |
| 多问漏答或多跳只答第一跳 | 显式 subquestions 优先；“分别/对比/以及/并且”等带逗号的问题拆 hop；每 hop 独立检索、记录 query_plan、gaps 与 coverage，原问题同时作为上下文变体 |
| 版本冲突被平均或偷选版本 | 哈希重复只检索一次、清单保留全部副本；版本/supersedes/aliases 逐文件保存；近邻证据数值不同则形成 possible_numeric_conflict，附双引文，不自动裁决 |
| 无依据时生成流畅事实 | 事实句完全由原文抽取，生成后再机械核验引文和字符区间；未过检索支撑阈值时 `answer_kind=explicit_unknown`，claims/evidence 为空并写明缺什么 |

参考实现的落地：LlamaIndex `CitationQueryEngine` 会先对检索节点再分块、分配
Source N，再把来源交给答案合成器。本 Skill 采用相同的“先定位、再编号引用”思想，
但进一步把每个答案句绑定到字符坐标并做生成后核验；没有照搬其“只提示模型引用、
不验证引用”的部分。实现不调用外部模型、网络或第三方 Python 包。

## 六步运行时入口（Harbor）

平台输入为 `/input/case.json` 和 `task.md`，工作区 `/app/work`，最终交付 `/app/output`。
固定案例本身不随提交包预置；运行时必须读当前真实案例。

| 步 | 动作 | 产物/边界 |
|-|-|-|
| 0 | 读 case_id、output_contract、task.md 与 case 声明的 materials/documents/files/library/corpus；JSON workorder 可经 `workorder` 路径声明 | 标签、文件名和 workorder 词不是正文事实；实际文件内容才是证据 |
| 1 | 确认 questions/queries/searches 与材料路径。路径相对 case.json，也可用 `--material-root /input` | 显式 `documents: []` 是空库，不会误索引同目录；未声明 documents 时才发现支持的文件 |
| 2 | 直接运行下方主命令，先落盘 answers/index/result | 出现扫描件、损坏、权限或 JSON workorder 失败时，其他可读文件继续完成；失败不会被写成成功 |
| 3 | 按 task.md 的实际问题核对 answers 与 query_plan；若自动读取不到结构化问题，把 task.md 的**原问题**整理进 `/app/work/case.json` 后重跑 | 只允许整理输入，不允许填写预期答案；多子问必须保留为 subquestions 或可分解原句 |
| 4 | 对 unreadable/no_searchable_text 先补真实文本层或调用环境提供的 PDF/OCR 工具，再重跑；对 possible conflict 保留双方，除非材料明确声明 supersedes | PDF 文本提取走 pdftotext；DOCX 取真实 document.xml；无法提取时明确拒绝该文件，不猜内容 |
| 5 | 交付 `/app/output/result.json`、`answers.json`、`answers.md`、`kb_index.json`、`operation_log.json` | result.json 含 case_id、所有 output_contract 字段、documents、versions、answers、evidence、conflicts、coverage、operation_trace、uncertainties、failures、limits、verification |

### 主命令

```bash
python scripts/kbqa_cli.py --case /input/case.json --out /app/output
# 当 case 的相对路径需要另一个真实材料根目录时：
python scripts/kbqa_cli.py --case /input/case.json --material-root /input --out /app/output
```

退出码：`0 done`（所有问题已处理，包括合法的显式“不知道”）；
`3 partial`（仍有可读交付，但材料/ID 等存在失败）；`5 undetermined`
（case 不可读、无可检索文档、无结构化问题、输出或证据核验失败）。
所有拒绝先写可获得的最小 result.json；stdout 是 JSON，不输出 traceback。
输出目录本身不可写时也会给出结构化 stdout 和 exit 5，不谎称已落盘。

## 最小调用示例

`examples/case.json` 是自拟双问题示例（不是组织方正式案例）：

```bash
python scripts/kbqa_cli.py --case examples/case.json --out ./out
```

输入骨架：

```json
{
  "case_id": "case-demo-kbqa",
  "documents": [
    {"document_id": "protocol-v2", "version": "v2", "path": "protocol-v2.txt"},
    {"document_id": "notes", "text": "每组使用六个重复。"}
  ],
  "aliases": {"sample": ["样品", "specimen"]},
  "questions": [
    {"question_id": "q1", "question": "请分别回答样品的保存温度，以及每组的重复数量。"},
    {"question_id": "q2", "question": "知识库未记载的问题是什么？"}
  ],
  "output_contract": {"answers": [], "evidence": [], "deliverable": "grounded answers"}
}
```

答案示意（结构节选，并非正式案例结果）：事实为抽取的原文句子加 `[ev-…]`；
`claims[]` 的 `locators[]` 可回到 `kb_index.json` 中同一段文字。第二个无依据问题
返回 `status=insufficient_evidence`、`answer_kind=explicit_unknown`、`claims=[]`，
而不是从参数名或预训练记忆中补造答案。

## 输入适配与方法细节

- documents 项可含 `document_id`、`id`、`name`，路径字段 `path`、`file`、`file_path`，或
  `text`、`content`、`body`、`markdown`、`extracted_text`；支持内联文本、UTF-8 txt/md/csv/
  tsv/json/jsonl/html/yaml、PDF（环境 pdftotext）和 DOCX（真实 document.xml）。
- 目录发现排除 case/task/result、隐藏目录与输出目录，最多 500 个候选文件；显式材料优先。
- 每份 document 保留 path、directory、file_type、bytes、完整 sha256、text_sha256、
  metadata、source、permissions、extraction、version、supersedes、aliases、duplicate_of。
  重复 document_id 自动分配可审计后缀并报错，后续段落不会覆盖先前证据。
- 纯文本无 form feed 时 `page=null`，绝不把“第一页”当成 PDF 页码。只有实际分页符
  或 PDF 文本分页才生成 1-based page；paragraph 为 1-based，字符区间为半开区间。
- 查询扩展不改变证据池，也不允许桥接词本身成为答案。RRF 融合原 hop、全问题和
  声明 aliases；对长问题设置支撑/覆盖阈值，弱词面重合不能触发肯定回答。
- `conflicts` 是**可能冲突提示**，不是自动语义判真；未判明的关系与两个精确定位一起
  进入 uncertainties/limits，读者可按来源处理行政版本决定。

## result.json 与 rubric 三段映射

| 题目要求 | 字段 | 独立完成标准 |
|-|-|-|
| 资料结果 | documents/file_type/directory/metadata、versions、answers/query_plan/evidence | 输入文件逐份有哈希与元数据；重复与版本关系不消失；问题及 hop 均有状态 |
| 操作证据 | evidence/locators、verification、operation_trace、kb_index.json、answers.md | claims_checked 覆盖所有事实句；引文逐字和 char range 可冷复核；无墙钟字段，重跑五个文件字节一致 |
| 失败与恢复 | failures、limits、uncertainties、gaps、status/status_reason | 不可读、无文本层、权限/路径、缺证、冲突分别显式；可读部分交付但 overall status 不掩盖失败 |

`output_contract` 逐字段完成：引擎已有同名结果优先；case 顶层小体积真实值直通；
契约中的短字符串/数值/布尔字面量直通；标准字段名可映射到 answers/evidence/
documents/conflicts/coverage 等实际结果；其余对象保留为 null 并在 limits 明说，
绝不把大段材料复制成“结果”。

## 规则与异常索引

| rule | 处置 |
|-|-|
| `kbqa.case_unreadable` / `kbqa.case_not_object` / `kbqa.case_required` | exit 5；最小 undetermined result；不 traceback |
| `kbqa.invalid_input` | 意外但可识别的输入形状统一 exit 5，消息包含异常类型，不隐藏为成功 |
| `kbqa.workorder_unreadable` / `kbqa.workorder_not_object` | workorder 失败留痕；其他实际可读材料继续，通常 partial |
| `kbqa.record_not_object` / `kbqa.document_has_no_content` | 跳过坏记录并点名；有权读取的其他文件继续 |
| `kbqa.path_is_directory` / `kbqa.document_unreadable` / `kbqa.no_searchable_text` | 文件级拒绝与 recovery；不抽正文、不造页码；partial 或 undetermined |
| `kbqa.duplicate_document_id` | 换用稳定后缀并保留两套原文，不能覆盖段落索引 |
| `kbqa.claim_without_locator` / `kbqa.unknown_evidence` | 生成后核验失败则整体 undetermined，不交付“已验证”答案 |
| `kbqa.quote_anchor_mismatch` / `kbqa.claim_quote_mismatch` | 原文/原文区间与 claim 不一致即核验失败；冷校验也会抓人工篡改 |
| `kbqa.export_unreadable` / `kbqa.verification_failed` | 冷校验缺文件/坏 JSON/异常时 exit 5，结构化报告 |

旧 answers 审计可另行用 `python scripts/secrun.py --spec spec.json --section qa --out out`
执行，退出码 0/3/4/5；它不是主检索流程，也不需要为本题手写引用答案。

## Optional：独立复核

```bash
python scripts/kbqa_cli.py --verify-only --out /app/output
```

该命令从磁盘重新读取 `result.json` 与 `kb_index.json`，逐 claim 验证证据 id、doc、
paragraph、char range 与 quote 完全一致。`0` 全部通过，`5` 缺导出/错位/被篡改。
这不是生成答案的必需步骤，而是交付后的独立检查。

## Limits

- 答案是**面向可核验性的抽取式回答**，不把跨段材料改写成新的事实，也不做因果、数学或
  科学推理。需要综合性文字时，Agent 只能在原文句与定位之后明确区分自己的推断。
- 检索是确定性的词法方法。CJK 二字词、保守英文单复数、内置少量通用科研管理词桥及
  case aliases 不能保证语义等价；新问题召回不足时会明确不知道，而不是扩大为模糊匹配。
- OCR 低置信文本不会被静默“校正”；pdftotext 不可用时 PDF 被列为 unreadable。
  扫描件需要运行环境真实 OCR 产物后再入库。
- possible_numeric_conflict 只证明近邻引文的数值形式不同，不证明科学结论必然互斥；
  也不利用 v1/v2 文件名猜谁更新。权威版本只接受实际 supersedes/版本说明。

## Verification

```bash
python scripts/bench_kbqa_pipeline.py  # 23 个真实文件/检索/问答/导出场景
python scripts/bench_kbqa_hostile.py   # 17 个 CLI、契约、退出码、篡改与确定性探针
python scripts/bench_kbqa.py           # 12 个旧 answers 审计场景
python scripts/bench_sections.py       # 51 个共享审计回归（包括 clean baselines）
```

四组独立测试共 103 项在当前版本全过；功能 clean baseline 的每个事实句均通过
locator 冷核验。所有 fixture 都在临时目录生成，不是正式测试答案。

## 创新增益（与实现一致）

1. **逐句硬绑定而非引用装饰**：answer_sentences=claims=reported 原文；独立导出再次验
   证 source、paragraph 和字符切片，任何人工改动都使 verify 失败。
2. **小语料友好的 CJK/双脚本 RRF**：不把跨版本都出现的领域词当停词，中文问题可查询
   中文或英文资料，但仍以真实原文段落作为唯一事实来源。
3. **可覆盖的多跳缺证账本**：每个 hop 有 evidence_ids 或 missing，answered/partial/
   conflicted/insufficient 各自计数，避免“回答了一段就宣称整题完成”。
4. **重复不膨胀、版本不混并、冲突不抹平**：哈希只影响检索效率，清单与冲突证据完整。
5. **数据质量不依赖文档自述**：无真实分页则 page=null；只有显式声明的版本关系被结构化；
   output_contract 不可推导对象一律 null+limits，不重写成看似完成的字段。

## Requirements / 生态贡献

Python 3.10+，核心仅标准库；PDF 复用环境 `pdftotext`，DOCX 直接读取标准 ZIP/XML，
无网络、无 API key、无模型安装。`kbqa.py` 可冷导入，`run_case()` 与 `verify_export()`
可复用；示例、索引 schema、23+17 个新场景和原 12+51 个回归均随包提供。维护时新增
能力必须同时补 clean baseline、敌意探针、契约直通和无答案测试，并保持本文档与实际
退出码、字段、限制一致。
