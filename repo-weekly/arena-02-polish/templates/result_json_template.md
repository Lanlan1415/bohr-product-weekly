# result.json 模板与透传规则（学术语言润色）

## 透传规则（契约红线）

1. `case_id` 逐字取自 `/input/case.json`；
2. `output_contract` 声明的**全部原始字段**出现在 result.json 顶层，字段名一字不差；值按字段语义填（文件路径/文本/数组），`output_contract_fields` 再列完整键清单；
3. case 顶层同名字段的非空值（含 object/array）逐字直通；审计已产出的非空值优先保留；`polished_text`/`change_log` 等可推导字段填真实交付；做不到的字段填 null 并在 uncertainty 说明，不删字段、不改名；
4. 契约字段之外可加辅助字段（status/sources/uncertainty/change_log 等）。

## 示意 JSON（合成示意，非正式案例结果）

```json
{
  "case_id": "polish-demo-000",
  "polished_text": "polished_text.md",
  "change_log": "change_log.md",
  "notes": "L1-L3 完成；L4 仅摘要",
  "status": "partial",
  "sources": [
    {"source_id": "S1", "file": "manuscript.md", "note": "待润色稿件"},
    {"source_id": "S2", "file": "journal_guide.txt", "note": "期刊文体要求"}
  ],
  "uncertainty": [
    "术语 'current collector' 存在两种译法且材料未指定 → 暂按稿件多数用法统一为'集流体' → 建议作者确认",
    "第 3 章未处理（预算不足）→ 影响完整性 → 可直接从第 3 章继续，流程见 SKILL.md 第 3 步"
  ],
  "change_log": [
    "[第0步] prepare：5 章 214 句入 sentences.tsv，封存 original_snapshot.md",
    "[第3步] L1/L2 完成摘要与第1-2章；L3 完成摘要",
    "[第4步] verify：23 条编辑接受 21 / 回退 2（1 条数字篡改已回退，1 条锚定失败已修正重投）",
    "[第5步] finalize 导出：契约前置校验 3/3 字段；回读 pass",
    "[第6步] audit 自查通过（退出码仅供定位问题，不作为交付门禁）"
  ],
  "before_after_digest": {
    "accepted": 21,
    "unchanged": 4,
    "confirmations": 1,
    "rejected": 2,
    "rejected_reasons": {"守恒门违规，已自动回退": 2},
    "samples": [
      {"edit_id": "C001",
       "before": "The electrolyte have attracted much attention [1].",
       "after": "The electrolyte has attracted considerable attention [1].",
       "type": "grammar.agreement", "reason": "主语单数",
       "ambiguity": null, "author_confirmation": null,
       "protected_elements": {"numbers": {"before": ["1"], "after": ["1"], "status": "Same"}}}
    ],
    "unchanged_samples": [{"edit_id": "K001", "before": "<原句>", "after": "<原句>", "reason": "无需修改"}],
    "confirmation_items": [{"edit_id": "A001", "before": "<原句>", "candidates": ["保留原句", "候选B"], "ambiguity": "待作者判定"}]
  },
  "skipped_reason": ["第 3 章未处理（预算不足）→ 交付前 2 章 + 摘要"],
  "stats": {"entries": 23, "L1": 11, "L2": 6, "L3": 5, "L4": 1, "alternatives": 2},
  "quality_gate": {"verify": "pass", "readback": "pass", "audit": "pass", "selfcheck": "pass"}
}
```

## v2 字段说明

- `before_after_digest`：评审友好摘要，由 finalize.py 依据 verify_result.json
  自动生成（接受/回退计数 + 前 8 条改前→改后样例）；
- `skipped_reason`：阶段被跳过/降级的诚实原因清单（verify 缺失、章节未完
  等）；存在时 status 不得为 success；
- `quality_gate`：verify / readback（改后回读）/ audit / selfcheck 四环结果。

## 校验

`python3 /skills/weekly-skill/scripts/selfcheck.py --output /app/output --case /input/case.json`

校验是建议性的：脚本退出码仅供定位问题，不作为交付门禁。报 FAIL 时的正确做法
是修一轮、把修不完的缺口记入 uncertainty/skipped_reason，然后照常交付。
