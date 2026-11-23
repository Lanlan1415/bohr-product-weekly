# 最小调用示例（示意输出，非正式案例结果）

> 本示例仅说明接口与流程，输出为**示意**，不冒充正式案例结果。

## 输入

```
/input/case.json          # 含 case_id 与 output_contract
/input/task.md            # 指定润色范围与目标文体
/input/manuscript.md      # 待润色稿件
/input/journal_guide.txt  # （可选）期刊/学校文体要求
```

## 调用

```bash
# 1) 材料清点 + prepare（契约解析、原文快照、句级切分）
python3 /skills/weekly-skill/scripts/inventory.py --input /input --output /app/work/materials_register.md
python3 /skills/weekly-skill/scripts/prepare.py --text /input/manuscript.md --workdir /app/work --case /input/case.json
# 2)（模型按 SKILL.md 第 2-3 步建术语表、产出锚定编辑记录 edits.jsonl 后）verify
python3 /skills/weekly-skill/scripts/verify.py --workdir /app/work --edits /app/work/edits.jsonl
# 3) finalize 无条件导出 + audit 审计 + selfcheck 结构自查
python3 /skills/weekly-skill/scripts/finalize.py --workdir /app/work --output /app/output --case /input/case.json
python3 /skills/weekly-skill/scripts/audit.py --output /app/output --case /input/case.json --workdir /app/work
python3 /skills/weekly-skill/scripts/selfcheck.py --output /app/output --case /input/case.json
```

## 示意输出（截选）

`edits.jsonl` 一条（示意，注意先抄原句再写改文）：

> {"edit_id": "C001", "sentence_id": "sent-0001", "level": "L1", "original": "The electrolyte have attracted much attention [1].", "replacement": "The electrolyte has attracted considerable attention [1].", "type": "grammar.agreement", "reason": "主语单数"}

verify.py 输出（示意）：

```
[INFO] 编辑 5 条：接受 4 / 回退 1 / 警告 0
[REVERT] N01：守恒门违规，已自动回退：数字/单位不一致
```

> 脚本退出码仅供定位问题，不作为交付门禁：被回退的编辑修一轮后重投或记入
> skipped_reason；finalize 无条件导出当前最好版本。

完整可运行样例（含失败情形与五脚本流水线实测）见 `examples/synthetic_case.md`（全合成）。

## 验证与限制

本示例为**合成示意**；本地仅做过合成数据验证，平台的 3 个隐藏评测案例
与对照组未在本地运行，本 Skill 不声称任何具体分数。
