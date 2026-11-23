# 最小调用示例（示意，非正式案例结果）

> 本示例仅说明接口与流程，**不是**正式案例的运行结果。
> **验证与限制声明（v2）**：本 Skill 仅做过本地合成验证；平台的 3 个隐藏
> 案例与对照基线未在本地运行，不声称任何分数。

## 输入

- `/input/case.json`（示意）：
  `{"case_id": "demo-001", "output_contract": ["notes_file", "summary_one_line"]}`
- `/input/paper.pdf`：一篇待读论文。

## 调用

```
python3 /skills/weekly-skill/scripts/inventory.py /input \
    --out /app/work/materials_register.md
# （人工）读论文 -> section_map.md -> /app/output/notes.md -> evidence_map.md
python3 /skills/weekly-skill/scripts/notes_check.py \
    --notes /app/output/notes.md --register /app/work/materials_register.md
python3 /skills/weekly-skill/scripts/selfcheck.py \
    --out /app/output --case /input/case.json \
    --register /app/work/materials_register.md
```

## 示意输出（片段，非正式案例结果）

notes.md 片段：

```markdown
## 主要结果
- 方法在测试集上准确率达到 91.4%（n=200，5 折交叉验证）[S1 p.6 §4.2 表2]
```

notes_check.py 输出（示意）：

```
[PASS] 必备章节齐全（11 组）
[PASS] 全部 14 个锚点均含定位信息
[PASS] 论断→证据映射 6 条论断全部带锚点
结论：通过
```

result.json（示意，字段名以真实 case.json 为准）：

```json
{"case_id": "demo-001", "status": "success",
 "notes_file": "notes.md", "summary_one_line": "……",
 "sources": ["S1"], "uncertainty": [], "change_log": ["v1 交付"]}
```
