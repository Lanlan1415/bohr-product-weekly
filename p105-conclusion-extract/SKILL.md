---
name: conclusion-extract
description: >
  Read target-fields.json and emit one structured row per requested field_id, preserving
  raw scalar/unit, exact quotation and paragraph/table/page locator, sample and groups,
  comparator, experimental conditions, endpoint, uncertainty and statistical basis.
  Separates reported, not_reported, source_conflict and extraction_failed; catches altered
  values, dropped hedges, endpoint substitution, invented units and association-to-causation
  upgrades. Use for 文献结论与数据提取、实验条件表、结论卡片、数值证据定位.
---

# conclusion-extract

主入口是 **target-fields v2**。目标不是缩短论文，而是把正文、表格、图注和补充材料中的
字段还原成可复核结构。每一条字段都有证据，不允许用整洁 schema 代替真实阅读。

## Runtime（/input → /app/output）

1. 读取 `/input/case.json`、`/input/target-fields.json`、`task.md` 和真实论文。原样保留
   `case_id/output_contract`。PDF/扫描件用平台实际 PDF/OCR 工具；不可读时写 extraction_failed，
   不从标题或已有 DOI 生成正文。
2. 在 `/app/work/sources.json` 保存实际来源快照。推荐结构：

```json
{"documents": [{"document_id": "P1",
  "publication_type": "journal_article", "version": "accepted-manuscript",
  "paragraphs": [{"paragraph_id": "R-12", "page": 7, "section": "Results",
                  "table_id": "T2", "row": 4, "column": "effect",
                  "text": "Treatment A was associated with 12% higher uptake ..."}]
}]}
```

   每段可以带 page、section、table_id/row/column、figure_id、bbox 或 charspan，但只记录工具
   实际提供的值。纯 `document.text` 也能用，生成的 P0001… 是 snapshot 段号，不冒充 PDF 原生段号。

3. 在 `/app/work/extraction.json` 写入 target 清单的每个 field_id，然后运行：

```bash
python -I /skills/weekly-skill/scripts/extract_workorder.py \
  --case /input/case.json \
  --targets /input/target-fields.json \
  --extraction /app/work/extraction.json \
  --sources /app/work/sources.json \
  --out /app/output
```

4. 根据 finding 回到原论文修复并重跑。尚未解决也保留 field_table 和 result，状态如实为 partial。
   先写已完成字段，再逐步补齐；未报告与提取失败不得补值。

## 每个 reported field 的结构

下面仅展示机制。数值与引文均为 synthetic，不是正式案例答案。

```json
{"fields": [{
  "field_id": "uptake", "status": "reported", "scalar": 12,
  "claim_kind": "conclusion", "claim_form": "associational",
  "endpoint_match": "exact",
  "evidence": [{"source_document_id": "P1", "paragraph_id": "R-12",
                "quote": "12% higher uptake"}],
  "unit": {"status": "reported", "value": "%",
           "evidence": [{"source_document_id": "P1", "paragraph_id": "R-12", "quote": "%"}]},
  "statistic": {"status": "reported", "test": "Welch t-test", "p_value": "0.002",
                 "confidence_interval": "95% CI 5–19", "effect_measure": "uptake difference",
                 "evidence": [{"source_document_id": "P1", "paragraph_id": "R-12", "quote": "p = 0.002"}]},
  "experimental_condition": {"status": "reported", "summary": "25 °C for 24 h",
    "evidence": [{"source_document_id": "P1", "paragraph_id": "R-12", "quote": "25 °C for 24 h"}]},
  "comparator": {"status": "reported", "name": "treatment B",
    "evidence": [{"source_document_id": "P1", "paragraph_id": "R-12", "quote": "treatment B"}]},
  "sample": {"status": "reported", "population": "mice",
    "groups": [{"name": "treatment A", "n": 6, "unit": "mice", "role": "intervention"},
               {"name": "treatment B", "n": 6, "unit": "mice", "role": "comparator"}],
    "evidence": [{"source_document_id": "P1", "paragraph_id": "R-12", "quote": "6 mice per group"}]},
  "endpoint": {"status": "reported", "name": "24-hour cellular uptake",
    "evidence": [{"source_document_id": "P1", "paragraph_id": "R-12", "quote": "uptake"}]},
  "uncertainty": {"status": "reported", "hedged": false, "qualifiers": [],
    "error_type": "95% CI", "error_value": "5–19",
    "evidence": [{"source_document_id": "P1", "paragraph_id": "R-12", "quote": "95% CI 5–19"}]},
  "statistical_basis": {"status": "reported", "analysis_population": "all randomized mice",
    "aggregation": "mean difference", "test": "Welch t-test", "p_value": "0.002",
    "multiple_testing": "single prespecified endpoint"}
}]}
```

### Component 规则

所有 reported 行都必须有这八个对象：`unit/statistic/experimental_condition/comparator/sample/
endpoint/uncertainty/statistical_basis`，并且每个对象有：

- `status: reported`：保留真实值；sample 需 groups.name/n/unit/role；comparator 保留比较组；
  condition、sample、comparator、endpoint、uncertainty 要有各自 evidence。统计组件可与主证据共享，不必复制。
- `status: not_reported`：原文未给，写 `search_note` 说明查过哪里。缺统计量是 not_reported，不是 0 或不显著。
- `status: not_applicable`：科学上不适用，写 `reason`，例如纯方向结论没有物理单位。不能用它掩盖漏读。

其他强制语义：

- `claim_kind = conclusion|data|limitation|speculation`，`claim_form = descriptive|associational|causal`。
  原文 associated/correlated/相关，不能直接升级为 causal；忠实 hedged 的因果推测允许保留。
- `claim_form` 不能代替不确定性：`uncertainty.hedged` 必须是 bool。原文 may/might/提示/可能
  与 hedged=false 不相容。限制条件放 qualifiers，不删除。
- 数值 scalar 必须出现在主引文；原 unit 也必须出现在主证据上下文。样本组 n 必须见于样本证据。
  不会允许真的 quote 配上另一个数或捏造单位。
- 原文有 p-value 时，statistic 或 statistical_basis 必须保留。CI、误差类型、分析人群、聚合方式、
  多检验口径属于统计/不确定性，不擅自补单位或换显著性。
- `endpoint_match = exact|alias|different|not_applicable`。different 不能回答目标字段；alias 必须给
  `endpoint_mapping_note`。主要终点、替代终点和事后分析不能偷换。
- 可选 `normalized_scalar + normalized_unit` 只有在 raw scalar/unit 可复算时成立；原值不覆盖。
  不支持的角度、百分数等换算会拒绝，不猜 `12% → 0.12 fraction` 这种显示/统计口径转换。

### 三种非 reported 行仍是完整 schema

- `not_reported`：scalar=null，evidence=[]，components 保留同样字段并继承 search_note；
  `verification_status=undetermined`。
- `extraction_failed`：写 failure_note，标清 OCR/表格/权限等人工接管位置，不填 0。
- `source_conflict`：给 conflict_note，并在 `conflicts`（或 evidence）放至少两个不同来源位置的
  原话；冲突双方均保留，不能只选喜欢的一条。

## Output and statuses

| 交付 | 内容 |
|-|-|
| `field_table.json` | 按 target-fields 原顺序逐字段 rows；缺 field_id 或重复会报 high finding |
| `result.json` | `fields`、`field_table`、source_quality、findings、severity_counts、uncertainty、limits、change_records |
| `case_id` / contract | `case_id` 原样；`output_contract` 原样保存且每个字段在顶层直通；引擎值 > case 值 > target 文件值 > null+limits |

`success` exit 0（无 finding）；`review` exit 3（只有 medium/low）；`partial` exit 4（high）；
`undetermined` exit 5（case/target/extraction 不可运行）。所有非参数用法错误均重结构 JSON，无 traceback。

## 开源机制如何真实落地

- **Docling / docling-core**（https://github.com/docling-project/docling ，
  https://github.com/docling-project/docling-core ）的 ProvenanceItem 使用 `page_no/bbox/charspan`。
  本包将 provenance 落到 `source_document_id + paragraph_id + page/table/figure + char offsets`，
  并对表格行列/图注保留独立定位，绝不把“同文件名”当字段证据。
- **Ragas Faithfulness**（https://github.com/explodinggradients/ragas ，
  `src/ragas/metrics/_faithfulness.py`）把回答拆成 statements，再逐条对 context 判定。本包同样
  逐 field、逐 evidence 分解核验，但增加 raw value/condition/endpoint/statistics 的绑定。
  本包无外部 NLI 模型，明示 claim_form 和 endpoint mapping 是需要语义阅读的声明，不冒充自动蕴含。

本地 `claim-condition-extractor` 的 value quote + condition quote + hedge guard 被保留，并进一步
实现 target 覆盖、完整统计组件、数值/单位/组 n 证据检查和两侧 source_conflict。

## Limits

- 不解析 PDF、不联网、不查 DOI、不重建扫描表格。只核验提供的 source snapshot；原工具解析失败照实记录。
- 逐字命中不证明语义正确。因果、终点同义映射、分析人群和科学合理性仍需 Agent/人工阅读。
- CJK 引文按实际 UTF-8 字符精确匹配，不做 NFKC 模糊放行，更不做翻译后“伪原文”命中。跨句/跨段证据须分别给出，
  不把不同段拼成一个假引文。
- `secrun.py --section conclusion_extract` 是旧 spec 审计器，保留兼容用，不替代 target-fields v2 CLI。

## Requirements 与可选作者核验

Python **3.10+**，纯标准库，3.14 实测；无安装步骤。Bench 是作者工具，不是运行时 step，也不是正式答案：

```bash
python -I scripts/bench_v2.py --suite functional  # 3 checks
python -I scripts/bench_v2.py --suite hostile     # 12 checks
python -I scripts/bench_v2.py --suite smoke       # 2 checks
```

覆盖 clean、CJK、未报告、相同/非法单位换算、相关改因果、丢 hedge、换终点、缺字段、错数、丢 p-value、
坏引文、单侧冲突、捏造单位、组 n 改变、拒绝、幂等和冷导入。旧 `bench_extract.py`、
`bench_sections.py` 可另行回归；运行时无需执行。
