# result.json 编写规则与示意（阅读14：Nanopublication）

## 透传规则

1. 打开 `/input/case.json`，记录 `case_id` 与 `output_contract`。
2. `output_contract` 声明的**全部原始字段**必须出现在 result.json 顶层，
   字段名逐字照抄（大小写、下划线都不改），不得以"意思相同"为由改名。
3. 契约字段的值由本任务产物填充；确实无法填充的字段保留字段名、值给 null
   并在 uncertainty 中说明，**不得删除字段**。
4. 除契约字段外，必须另有：`case_id`、`status`、`sources`、`uncertainty`、
   `change_log`。若契约字段与这些重名，以 case.json 为准。
5. **契约前置校验（v2，建议性、不阻塞落盘）**：先把草稿写到
   `/app/work/result_draft.json`，运行 `python3 /skills/weekly-skill/scripts/
   contract_check.py --case /input/case.json --draft /app/work/result_draft.json`
   核对契约字段；**无论校验结果如何都落盘** `/app/output/result.json`——
   脚本报 FAIL 时的正确做法是补一轮缺失字段（做不到的填 null 并写入
   uncertainty/skipped_reason）并照常交付；脚本退出码仅供定位问题，
   不作为交付门禁。
6. **交付韧性（v2）**：status 为 partial/failed 时增加 `skipped_reason`
   字段（数组，元素为 `{"stage": 阶段名, "reason": 原因}`），逐条列出被跳过
   或未完成的阶段与人工接管位置；finalize 永远导出可交付物，不允许零交付。

## 示意 JSON（字段名仅为示意，实际以 case.json 为准）

```json
{
  "case_id": "arena-09-case-001",
  "status": "partial",
  "nanopub_file": "nanopubs.trig",
  "assertion_count": 8,
  "assertion_table_file": "assertion_table.md",
  "sources": ["S1"],
  "uncertainty": [
    "S1 未给出 DOI，provenance 以文件名锚点代替并标注未报告",
    "断言 A6 证据不足（仅作者观点句），置信度 low"
  ],
  "skipped_reason": [
    {"stage": "nanopub_generation", "reason": "A6 证据不足未发布，留待人工复核"}
  ],
  "change_log": [
    "v1 发布 3 条 nanopub 并通过 nanopub_check.py",
    "v2 增补至 8 条；修复 A3 缺 pubInfo 图（FAIL -> PASS）",
    "selfcheck.py 自查后照常交付（退出码不作为门禁）"
  ]
}
```

## status 判定

- success：质量门（references/element_checklist.md）A-E 全部通过，
  nanopub_check.py 与 selfcheck.py 均通过，无待确认项。
- partial：任一缺口存在（材料不可读、部分断言证据不足、契约字段无法填充等）；
  uncertainty 逐条说明缺口与人工接管位置。
- failed：主材料不可读或契约无法解析；仍须交付登记表与说明。
