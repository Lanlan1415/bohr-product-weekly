# result.json 编写规则与示意（阅读10）

## 透传规则

1. 打开 `/input/case.json`，记录 `case_id` 与 `output_contract`。
2. `output_contract` 声明的**全部原始字段**必须出现在 result.json 顶层，
   字段名逐字照抄（大小写、下划线都不改），不得以"意思相同"为由改名。
3. 契约字段的值由本任务产物填充；确实无法填充的字段保留字段名、值给 null
   并在 uncertainty 中说明，**不得删除字段**。
4. 除契约字段外，必须另有：`case_id`、`status`、`sources`、`uncertainty`、
   `change_log`。若契约字段与这些重名，以 case.json 为准。
5. **契约草稿核对（v2 引入，v3 起为建议性、不阻塞交付）**：先把草稿写到
   `/app/work/result_draft.json`，运行 `python3 /skills/weekly-skill/scripts/contract_check.py --case
   /input/case.json --draft /app/work/result_draft.json`；脚本报 FAIL 时的正确做法是：
   缺字段能补则补一轮，补不齐的保留字段并记入 uncertainty/skipped_reason，
   然后照常落盘 `/app/output/result.json`——**脚本退出码仅供定位问题，不作为交付门禁**。
6. **交付韧性（v2）**：status 为 partial/failed 时增加 `skipped_reason`
   字段（数组，元素为 `{"stage": 阶段名, "reason": 原因}`），逐条列出被跳过
   或未完成的阶段与人工接管位置；finalize 永远导出可交付物，不允许零交付。

## 示意 JSON（字段名仅为示意，实际以 case.json 为准）

```json
{
  "case_id": "arena-06-case-001",
  "status": "partial",
  "notes_file": "notes.md",
  "evidence_map_file": "evidence_map.md",
  "comparison_matrix_file": null,
  "summary_one_line": "本文提出X方法，在Y数据集上将Z指标提升至……",
  "sources": ["S1", "S2"],
  "uncertainty": [
    "S1 图3为矢量图内嵌公式，未能解析，相关结果仅引用正文文字",
    "样本量未在正文报告，字段按'未报告'处理"
  ],
  "skipped_reason": [
    {"stage": "comparison_matrix", "reason": "单篇案例，横向对比按流程跳过"}
  ],
  "change_log": [
    "v1 落盘 notes.md 字段区与 evidence_map.md 初稿",
    "notes_check.py FAIL：论断 C4 缺锚点 -> 补 [S1 p.6 §4.2]",
    "selfcheck.py 复查后照常交付（退出码仅供定位问题，不作为交付门禁）"
  ]
}
```

## status 判定

- success：自查清单（references/element_checklist.md）A-E 全部通过，无待确认项。
- partial：任一要素缺口存在；必须在 uncertainty 中逐条说明缺口与人工接管位置。
- failed：主材料不可读或契约无法解析，仍须交付已完成的登记与说明文件。
