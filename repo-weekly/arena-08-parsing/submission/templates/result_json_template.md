# result.json 透传规则与示意（文献文档解析）

## 透传规则（契约红线）

1. 打开 `/input/case.json`，逐字复制 `case_id` 的值。
2. `output_contract` 声明的**每一个字段名**都必须作为 `/app/output/result.json` 的顶层键出现：
   - 字段名逐字一致（大小写、下划线都不改）；
   - 不得新增臆造字段，也不得省略"暂时没有值"的字段（填空值并在 uncertainty 说明）；
   - 字段类型按 case.json 中的声明/示例值对齐（字符串/数组/对象）。
3. `status` 只允许 `success` / `partial` / `failed`：任何元素缺失、异常未完全处置、自查仍有 FAIL 时必须是 `partial`，并在 `uncertainty` 中逐条说明。
4. 步骤 0 就落盘最小 result.json（全字段 + `status:"partial"`），之后每完成一步迭代更新——防止预算耗尽时无交付。
5. （v2 引入，v3 起为建议性）**契约字段核对**：写入/交付 result.json 前后跑 `scripts/contract_check.py --case /input/case.json --result <草稿>`；脚本报 FAIL 时的正确做法是：缺字段能补则补一轮，补不齐的把缺口逐项记入 `uncertainty` 与 `skipped_reason`，然后照常交付——**脚本退出码仅供定位问题，不作为交付门禁**。
6. （v2）**skipped_reason**：任何阶段被跳过/中断时，在 result.json 顶层加 `skipped_reason` 数组逐条说明（格式 `"步骤N: 事项: 原因"`），并同步摘要进 `uncertainty`；有 skipped_reason 时 status 不得为 `success`。中断兜底用 `scripts/finalize.py` 自动完成上述全部动作。

## 示意 JSON（字段名仅为示例，实际以 case.json 为准）

```json
{
  "case_id": "示例-case-id-以-case.json-为准",
  "status": "partial",
  "parsed_document_path": "/app/output/parsed_document.md",
  "evidence_map_path": "/app/output/evidence_map.md",
  "survey_path": "/app/output/survey.json",
  "sources": [
    {"id": "S1", "file": "paper.pdf", "pages": 12, "route": "text-layer", "text_layer": true}
  ],
  "uncertainty": [
    "p.7 表 3 为图片型表格，标记 [NOT_READABLE]，单元格数值未提取",
    "p.9-10 栏序经人工抽查 3 处确认，其余页面为启发式判定",
    "skipped: 步骤5: p.7-8 OCR 视觉复核未完成: 预算耗尽"
  ],
  "skipped_reason": ["步骤5: p.7-8 OCR 视觉复核未完成: 预算耗尽"],
  "change_log": [
    {"step": 0, "action": "落盘最小 result.json（partial）"},
    {"step": 2, "action": "pdf_survey 完成：无加密，文字层正常"},
    {"step": 7, "action": "selfcheck 第 1 轮 2 项 FAIL（缺公式章节、[S2] 未登记），已修复并复查 PASS"}
  ]
}
```
