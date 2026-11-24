# result.json 与交付物契约（introcrun v1）

主入口 `scripts/introcrun.py` 生成三份产物。本文描述引擎实际写出的字段，不是预先编好的答案。

## 顶层

```json
{
  "schema_version": "introcrun/v1",
  "case_id": "<原值；不可读时为 null>",
  "section": "introduction_related_work",
  "status": "clean | review | blocked | undetermined",
  "findings": [{"code": "...", "severity": "high|medium|low", "detail": "...", "...": "定位/引用/id"}],
  "severity_counts": {"high": 0},
  "verification": {"references": 0, "related_work_rows": 0, "cited_rows": 0,
                   "closest_work_comparisons": 0, "comparison_dimensions_per_row": ["problem_setting", "method_route", "data_evaluation", "scope"],
                   "full_text_verified_refs": [], "contributions_aligned": 0,
                   "gap_steps": 0, "coverage_limit": "...", "support_limit": "..."},
  "uncertainty": [], "human_review_items": [], "deliverables": [],
  "limits": [], "output_contract_fields": []
}
```

`verification` 的计数来自本次 spec，不冒充全领域覆盖率。source/metadata 的完整正文不复制进验证计数，只保留结论和可复核引用。

## 合同直通

- output_contract 支持数组或对象；每个字段名出现在 `output_contract_fields`。
- 审计自有字段优先：`case_id`、`status`、`findings`、`verification`、`uncertainty`、`deliverables`、`limits`。
- spec 中其它同名交付字段（如 evidence_map、version_boundary、trace、正文记录）逐字复制，不因体积大而置 null。
- 不可推导字段写 null 并在 limits 点名。
- `undetermined` 且 spec 可读时同样回填 case_id 与合同。

## 交付物

| 文件 | 实际生成方式 |
|-|-|
| `intro_related_work.md` | spec.draft 原样写入，末尾加一个换行；运行时由 Agent 创作并审计 |
| `comparison_matrix.csv` | spec.nearest_works 逐项生成 UTF-8 CSV，含四维 prior/this_work/difference + current_anchor |
| `result.json` | 上述结构化结果 |

## 科学状态

- `verified_full_text` 要求三列 quote 均逐字存在、locator 完整；有 passages[] 时须命中对应定位。
- `abstract_only`/`metadata_only`/`author_judgment` 会产生 `INTRO_EVIDENCE_LIMITED`（review），且最相近工作比较必须为 provisional + reason。
- `aligned` 贡献必须有 mapped_to 和 scope；Figure/Table/方法/结果锚点必须出现在 materials_text。
- 任何 findings 不会被静默删除；作者人工待办放 human_review_items，不确定性放 uncertainty，运行边界放 limits。
