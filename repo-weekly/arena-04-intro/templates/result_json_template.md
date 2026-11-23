# result.json 透传规则与示意

## 透传规则（红线）

1. 打开 `/input/case.json`，原样读取 `case_id` 与 `output_contract`；
2. `output_contract` 声明的**每一个字段名**都必须出现在 result.json
   顶层，字段名一字不差（大小写、下划线），不得臆造、增删、改名；
3. 字段值填写实际交付物的相对路径或内容摘要；确实无法产出的字段填
   null 并在 uncertainty 说明；
4. 除契约字段外，必须另有：`status`（success/partial/failed）、
   `sources`、`uncertainty`、`change_log`；
5. partial 也是合法结果：写明已完成什么、缺什么、为什么（如
   「成稿完成，缺口 2 的反例界定因材料不足标注待确认」）；
6. **交付韧性**：status 为 partial/failed 时增加 `skipped_reason`（字符串
   或列表），逐项列出未完成阶段及原因；finalize 永远要产出 result.json；
7. **写入前建议跑契约前置校验（建议性）**：先写 `/app/work/result_draft.json`，
   运行 `scripts/contract_check.py` 核对；FAIL 项能修则修一轮，修不完的逐项写入
   uncertainty 与 skipped_reason，然后照常复制为 `/app/output/result.json`——
   脚本退出码仅供定位问题，不作为交付门禁。

## 示意 JSON（示意结构，非正式案例结果；字段名以实际 case.json 为准）

```json
{
  "case_id": "<与 case.json 完全一致>",
  "status": "partial",
  "introduction_draft": "manuscript.md",
  "related_work_table": "manuscript.md#相关工作",
  "evidence_map": "evidence_map.md",
  "structure_report": "structure_check_report.md",
  "sources": ["S1", "S2", "S3", "S4"],
  "uncertainty": "材料库无 2024 年后文献，近期进展覆盖受限；S3 原文不可得，转述基于题录；目标期刊未指定，采用著者-出版年制。",
  "change_log": [
    "相关工作由逐篇罗列改写为按方法路线两组比较",
    "缺口 2 补充反例界定（S4 不构成填补的理由）",
    "贡献由 4 条口号改写为 2 条可核对表述，与缺口一一对应"
  ]
}
```
