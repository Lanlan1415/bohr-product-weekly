# result.json 模板与透传规则（写作09｜方法与实验章节写作）

## 透传规则（契约红线）

1. `case_id` 逐字取自 `/input/case.json`；
2. `output_contract` 声明的**全部原始字段**必须出现在 result.json 顶层，**字段名一字不差**——不臆造、不改名、不漏项。值可以是文件路径、数组或对象，按字段语义填；
3. 契约字段之外可自由增加辅助字段（如本模板的 status/sources 等）；
4. 字段语义做不到时填 null 并在 uncertainty 说明，不要删字段；
5. **落盘前置校验（建议性）**：先在 `/app/work/result_draft.json` 起草，运行
   `python3 /skills/weekly-skill/scripts/contract_check.py --case /input/case.json --result /app/work/result_draft.json`，
   FAIL 项能修则修一轮，修不完的逐项写入 uncertainty 与 skipped_reason，然后照常复制为
   `/app/output/result.json`——脚本退出码仅供定位问题，不作为交付门禁；
6. **交付韧性（skipped_reason）**：任何阶段被跳过/未完成时，必须附 `skipped_reason` 字段逐条写明原因；finalize 永远导出已完成的诚实部分，不留空交付。

## 示意 JSON（合成示意，非正式案例结果）

```json
{
  "case_id": "methods-demo-000",
  "methods_section": "methods_section.md",
  "param_table": "param_table.md",
  "evidence_map": "evidence_map.md",
  "language": "zh",
  "status": "partial",
  "sources": [
    {"source_id": "S1", "file": "task.md", "note": "任务说明"},
    {"source_id": "S2", "file": "config.yaml", "note": "训练配置，参数主要来源"},
    {"source_id": "S3", "file": "train.log", "note": "三次运行日志；第3次为最终实验"},
    {"source_id": "S4", "file": "notes.md", "note": "作者笔记，batch size 与 S2 冲突，已按 S3 处置"}
  ],
  "uncertainty": [
    "随机种子未在 S2/S3 中找到 → 成稿 §3.1 标 [待确认]（Q1）",
    "数据集版本未注明 → §3.2 标 [待确认]（Q2），可能影响复现"
  ],
  "change_log": [
    "[第1步] 登记材料 4 份（S1..S4），S4 与 S2 存在 batch_size 冲突",
    "[第3步] param_check 报 batch_size 冲突 → 以 S3 日志加载值 32 为准，两值均登记",
    "[第4步] 初稿落盘：六类要素齐全，2 处 [待确认]",
    "[第6步] selfcheck 通过；status=partial（2 项待确认）"
  ],
  "element_coverage": {"steps": true, "setup": true, "parameters": true, "dataset": true, "baselines": true, "reproducibility": true},
  "open_questions": ["Q1 随机种子", "Q2 数据集版本"],
  "skipped_reason": ["英文版未撰写：预算优先保证中文全要素版（第4步预算耗尽）"],
  "quality_gate": {"contract_check": "pass", "param_check": "pass", "selfcheck": "pass"}
}
```

> `skipped_reason` 仅在确有跳过/未完成阶段时填写；全部完成可省略或写空列表。

## 校验

落盘前：`python3 /skills/weekly-skill/scripts/contract_check.py --case /input/case.json --result /app/work/result_draft.json`
落盘后：`python3 /skills/weekly-skill/scripts/selfcheck.py --output /app/output --case /input/case.json`
