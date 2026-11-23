---
name: cross-document-compare
description: >
  Align several papers on the same question, entity, time, metric and units, then
  deliver a cell-level comparison matrix with verbatim anchors and explicit consensus,
  partial agreement, conflict or insufficient-evidence synthesis. Checks grid coverage,
  wrong-paper evidence, conversions, noncomparable pooling, both-sided difference causes
  and source quality. Use for 多文档比较、方法矩阵、跨论文证据整合和结论冲突解释.
  Do not use for single-paper summaries or bibliographic formatting.
---

# cross-document-compare

本包的主入口是 **comparison-workorder v2**，不是单篇摘要，也不只检查一段自报文字。
Agent 读取真实论文并构造矩阵；CLI 把逐格证据、对齐、换算和综合判定组装成实际交付。

## Runtime（/input → /app/output）

1. 读取 `/input/case.json`、`/input/comparison-workorder.json`、`task.md` 与工作单指定的全部
   语料。原样保留 `case_id` 和 `output_contract`。实际 PDF 先用平台 PDF/OCR 工具读取；
   不从文件名、领域标签或 DOI 猜内容。
2. 在 `/app/work/sources.json` 建立**真实来源快照**。下面是推荐结构；`page`、`section`、
   `table_id` 等只在原工具确实给出时填写。没有这些定位时必须标记 locator 限制，不能编页码。

```json
{"documents": [{
  "document_id": "D1",
  "publication_type": "journal_article",
  "version": "accepted-manuscript",
  "paragraphs": [{"paragraph_id": "T1-R2", "page": 4, "section": "Results",
                  "table_id": "T1", "row": 2, "column": "rate",
                  "text": "the measured rate was 1000 mg/L"}]
}]}
```

   也支持 `document.text` 纯文本；此时生成的 `P0001…` 只是 derived snapshot 段号，不冒充原 PDF
   段号。没有页/节/表/图/bbox/charspan 的记录会产生 `evidence.locator_vague`。
   `source_quality` 对未提供的 peer review/version/retraction 字段分别写 not_checked/not_reported。

3. 在 `/app/work/matrix.json` 中先写完整 **documents × field_defs** 网格，再运行：

```bash
python -I /skills/weekly-skill/scripts/compare_workorder.py \
  --case /input/case.json \
  --workorder /input/comparison-workorder.json \
  --matrix /app/work/matrix.json \
  --sources /app/work/sources.json \
  --out /app/output
```

4. 只修实际矩阵或证据后重跑。finding 尚未解决时交 `partial` 产物和明确 limits，绝不为了 exit 0
   删除冲突、补猜单元格或把不相似材料池化。先落盘已完成部分，再逐步扩展；运行预算以平台为准。

## matrix.json：统一字段与逐格证据

```json
{
  "documents": [{"doc_id": "D1"}, {"doc_id": "D2"}],
  "field_defs": [{"field_id": "rate", "group": "metric",
                  "definition": "24-hour dye-A removal rate", "target_unit": "g/L",
                  "alignment_keys": ["question_id", "entity", "time", "metric", "units",
                                     "material", "pollutant", "budget", "dataset"]}],
  "cells": [{
    "cell_id": "C1", "doc_id": "D1", "field_id": "rate", "status": "reported",
    "value": 1000, "unit": "mg/L", "normalized_value": 1.0,
    "comparable": true,
    "alignment": {"question_id": "Q1", "entity": "catalyst-X", "time": "24 h",
                  "metric": "removal-rate", "units": "g/L", "material": "catalyst-X",
                  "pollutant": "dye-A", "budget": "1 mg/mL", "dataset": "reference-2024"},
    "evidence": {"source_document_id": "D1", "paragraph_id": "T1-R2",
                 "quote": "1000 mg/L"}
  }],
  "synthesis": [{"field_id": "rate", "relation": "consensus",
                 "cell_ids": ["C1", "C2"], "evidence_strength": "strong",
                 "pooling_decision": "forbidden", "difference_causes": []}]
}
```

### Cell 约束

- `status` 只能是 `reported | not_reported | extraction_failed | not_applicable`。
  `not_reported` 要有 `search_note`，`extraction_failed` 要有 `failure_note`，
  `not_applicable` 要有 `reason`。没有证据不是 0，也不能留空后消失。
- 每个 reported cell 的 `evidence.source_document_id` 必须等于本列文档；`paragraph_id`
  必须在提供的 source snapshot 中存在，`quote` 是该段逐字子串。可另给 `context`，但 context
  必须也出现在该段且包含 quote。输出记录页/节/表/图和实际字符坐标。
- 默认对齐键是 `question_id/entity/time/metric/units/material/pollutant/budget/dataset`；
  field 或 workorder 可提供更合适的 `alignment_keys`。确实不适用写 `not_applicable`，不能静默缺失。
- conclusion 格还要有 `direction = increases|decreases|no_effect|mixed` 与
  `strength = strong|moderate|weak`。
- 数值保留原 `value + unit`。单位不同且 field 给 `target_unit` 时，必须另给
  `normalized_value`；CLI 用量纲和因子复算，不覆盖原值。未知/不同量纲单位不会被猜换算。

### 综合、冲突和证据强弱

`relation` 为 `consensus | partial | conflict | insufficient_evidence`：

- consensus 至少需要两篇 reported 证据，且归一方向/取值一致。
- 不同的 reported 归一取值只能标 partial/conflict，不能用 consensus 或 insufficient 掩盖。
- conflict 必须存在实际方向/取值分歧；partial/conflict 必须给一条以上
  `difference_causes`。`kind` 为 sample/method/condition/time/metric/dataset/unit/entity/unknown。
  已知原因要有 `explanation` 和双方 evidence anchors；确实无法归因则 `kind: unknown` 并说明，
  不虚构原因。
- `pooling_decision` 默认为 forbidden。只有 consensus、所有格 comparable、以及
  `pooling_alignment_keys` 实际一致时才可 allowed；不同数据集/染料/终点不会被池化。
- `evidence_strength` 是 strong/moderate/weak/insufficient 的显式判断，必须与保留的冲突、
  未报告和来源范围一起阅读，不由文本相似度自动加分。

## Output

`/app/output/` 总是包含：

| 文件/字段 | 内容 |
|-|-|
| `comparison_table.json` | documents、field_defs、完整 cells 和 synthesis |
| `evidence_cards.json` | 每格原值、归一值、条件、方向/强度和 verified evidence |
| `result.json` | 主结果、synthesis、findings、severity_counts、source_quality、uncertainty、limits、change_records |
| `case_id` | case.json 原值；缺失时 null + limits，绝不推断 |
| `output_contract` 全部字段 | **在 result 顶层逐字段保留**；引擎值 > case 自带值 > workorder 值 > null + limits；原 output_contract 也原样保留 |
| `output_contract_fields` | 实际处理的字段顺序；支持字符串和 `{field|name|key}` 条目 |

运行状态：`success`（exit 0，无 finding）、`review`（exit 3，仅 medium/low）、
`partial`（exit 4，有 high）、`undetermined`（exit 5，case/workorder/spec 不可运行）。
不可运行也写结构化 result，不用 traceback 当交付。输出目录物理不可写是唯一无法落盘的边界，
只能将结构化错误打印之后交给运行环境处理。

## 方法来源与实际落地（不是链接装饰）

1. **Docling / docling-core**（https://github.com/docling-project/docling ，
   https://github.com/docling-project/docling-core ）的 `DoclingDocument` 与 `ProvenanceItem`
   使用 `page_no`、`bbox`、`charspan` 管理图形和文本 provenance。本包落地为 document、
   paragraph、page/table/figure、paragraph/global char span 的 evidence ledger；没有把 lossless
   PDF 版式恢复偷偷宣称为已实现功能，bbox/charspan 只有原工具提供才输出。
2. **Ragas Faithfulness**（https://github.com/explodinggradients/ragas ，
   `src/ragas/metrics/_faithfulness.py`）先拆 atomic statements，再逐条对 context 做 NLI verdict。
   本包采用相同的“先拆格/子判断、再核 context”边界，但进一步区分四种关系和差异原因。
   本实现是标准库规则审计，**不是训练好的 NLI 模型**，不输出虚构 faithfulness 分数。

本地高分包 `common-field-comparison-matrix` 的 doc×field 网格、逐字 quote 和冲突落地机制
也被吸收到本 CLI；本包新增了单位复算、实际分歧不可隐藏、work-order schema 对账和全契约直通。

## Limits

- CLI 不解析 PDF、不联网、不查 Crossref、不验证 DOI 真伪；它核验的是用户提供的真实来源快照。
- 语义上的“同实体/同终点/同方法/某原因导致差异”仍由阅读 Agent 判定；CLI 检查证据存在、
  定位、数值、结构和判定内部一致性，不能把声明自动变成科学真值。
- 词面相似不用于支持判定。当前实现不用外部模型；跨语言 paraphrase 仍需 Agent 对原文判断。
- 扫描文本 OCR 错误、图表没有可读数据、全文未取得或版本不明均须明确记为未确定/未报告。
- `secrun.py --section compare_docs` 仅为旧结构审计兼容接口，不支持上述 v2 工作单主流程。

## Requirements 与可选作者核验

Python **3.10+**，标准库，无第三方依赖；3.14 实测。以下仅供作者验证，不是运行时必需步骤，
也不是正式案例或预制答案：

```bash
python -I scripts/bench_v2.py --suite functional  # 3 checks
python -I scripts/bench_v2.py --suite hostile     # 9 checks
python -I scripts/bench_v2.py --suite smoke       # 2 checks
```

覆盖 clean、mg/L↔g/L、CJK 冲突、not_reported、错源、错误换算、网格缺口、假共识、不可比池化、
无归因、隐藏分歧、畸形拒绝、幂等、冷导入与真实感定位输出。旧 bench 可另行用
`bench_compare.py` 和 `bench_sections.py` 回归；运行时不需要执行任何 bench。

最小示例可直接借鉴上面 synthetic schema；所有 bench 数据都是临时生成的 synthetic 示例，
不是组织方固定案例答案。
