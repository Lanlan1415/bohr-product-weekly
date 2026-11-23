# result.json 模板与透传规则（写作13｜LaTeX 写作与编译）

## 透传规则（契约红线）

1. `case_id` 逐字取自 `/input/case.json`；
2. `output_contract` 声明的**全部原始字段**必须出现在 result.json 顶层，**字段名一字不差**——不臆造、不改名、不漏项。值可以是文件路径、数组或对象，按字段语义填；
3. 契约字段之外可自由增加辅助字段（如本模板的 status/sources 等）；
4. 字段语义做不到时填 null 并在 uncertainty 说明，不要删字段；
5. **落盘前置校验（建议性）**：先在 `/app/work/result_draft.json` 起草，运行
   `python3 /skills/weekly-skill/scripts/contract_check.py --case /input/case.json --result /app/work/result_draft.json`，
   FAIL 项能修则修一轮，修不完的逐项写入 uncertainty 与 skipped_reason，然后照常复制为
   `/app/output/result.json`——脚本退出码仅供定位问题，不作为交付门禁；
6. **交付韧性（skipped_reason）**：任何阶段被跳过/未完成时，必须附 `skipped_reason` 字段逐条写明原因；finalize 永远导出已完成的诚实部分（工程源码、日志、记录），不留空交付、不谎称成功。

## 示意 JSON（合成示意，非正式案例结果）

```json
{
  "case_id": "latex-demo-000",
  "manuscript_source": "manuscript/",
  "pdf_preview": "manuscript/main.pdf",
  "build_record": "build_record.md",
  "evidence_map": "evidence_map.md",
  "status": "partial",
  "sources": [
    {"source_id": "S1", "file": "task.md", "note": "任务说明，含改动点清单"},
    {"source_id": "S2", "file": "template/journal.cls", "note": "题目给定模板，未改动"},
    {"source_id": "S3", "file": "draft.md", "note": "原始稿件内容来源"},
    {"source_id": "S4", "file": "refs.bib", "note": "参考文献库"}
  ],
  "uncertainty": [
    "模板要求补充作者单位信息，材料未提供 → main.tex 中标 [待确认]",
    "figure2 原始位图缺失，用占位图编译通过 → 需作者提供原图"
  ],
  "change_log": [
    "[第2步] 迁入模板：清理旧稿 inputenc（模板已 xelatex），登记 change_plan",
    "[第4步] R1 编译：2 个数学模式错误（methods.tex:42,57）→ 已修复",
    "[第4步] R2：citation undefined ×3 → 补 bibtex 轮次后收敛",
    "[第6步] 最终 3 轮编译收敛，PDF 4 页；log_triage 退出码 0"
  ],
  "build": {
    "engine": "pdflatex",
    "engine_choice_basis": "题目/模板未指定，沿用工程默认 pdflatex（选择顺序见 method_rules.md §2）",
    "rounds": 3,
    "bibliography": "bibtex",
    "final_log_clean": true,
    "template_modified": false
  },
  "skipped_reason": [],
  "quality_gate": {"contract_check": "pass", "tex_static_check": "pass", "log_triage": "pass", "selfcheck": "pass"}
}
```

> 编译失败情形：`pdf_preview` 填 null，`build_record` 指向含失败日志分析的 build_record.md，完整 .log 随 /app/output 交付，status=partial/failed，uncertainty 写明卡点（缺宏包/缺字体/模板缺失等），`skipped_reason` 写明未能完成的阶段。严禁 status=success 而实际编译失败。
> `engine` 必须填实际使用的编译器；`engine_choice_basis` 说明选择依据（题目/模板指定 / 工程现有配置 / 启发式默认）。`skipped_reason` 仅在确有跳过阶段时填写，全部完成可省略或写空列表。

## 校验

落盘前：`python3 /skills/weekly-skill/scripts/contract_check.py --case /input/case.json --result /app/work/result_draft.json`
落盘后：`python3 /skills/weekly-skill/scripts/selfcheck.py --output /app/output --case /input/case.json`
