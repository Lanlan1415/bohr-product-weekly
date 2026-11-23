# 最小调用示例（写作09）

> **说明：本示例的输入、调用与输出均为示意，非正式案例结果。**
> **验证限制**：本包仅做过本地合成验证；平台 3 个隐藏案例与对照未在本地运行，不声称分数。

## 输入（示意）

```
/input/
  case.json        # {"case_id": "demo-001", "output_contract": {"methods_section": "...", "param_table": "...", "evidence_map": "..."}}
  task.md          # 任务说明：依据材料撰写中文方法与实验章节
  config.yaml      # 训练配置
  train.log        # 训练日志
```

## 调用（按绝对路径，不依赖 CWD）

```bash
# 第1步：材料清点
python3 /skills/weekly-skill/scripts/inventory.py --input /input --out /app/work/materials_register.md

# 第2-4步：人工+模型完成要素抽取、参数表、成稿（骨架见 templates/methods_skeleton_zh.md）

# 第3/5步：参数冲突检测（材料 vs 成稿，YAML 锚点/空值感知）
python3 /skills/weekly-skill/scripts/param_check.py --materials /input --draft /app/output/methods_section.md --report /app/work/param_check_report.md

# 第6步a：result.json 落盘前的契约前置校验（建议性：FAIL 能修则修一轮，修不完记入 uncertainty 后照常落盘；退出码仅供定位问题，不作为交付门禁）
python3 /skills/weekly-skill/scripts/contract_check.py --case /input/case.json --result /app/work/result_draft.json

# 第6步b：交付自查
python3 /skills/weekly-skill/scripts/selfcheck.py --output /app/output --case /input/case.json
```

## 示意输出（非正式案例结果）

`param_check.py` 正常情况：

```
参数抽取与冲突检测报告
材料来源: 2 个文件; 成稿: 1 个文件
抽取参数出现点 11 处, 归并参数 6 个
[PASS] 无取值冲突
[WARN] 成稿参数 'weight_decay' 在材料中无来源（--strict 时计 FAIL）
结果: 通过（0 个 FAIL, 1 个 WARN）退出码 0
```

`selfcheck.py` 正常情况末行：

```
结果：通过（FAIL 0 / 共 12 项）
```

最终 `/app/output/`：`methods_section.md`、`param_table.md`、`evidence_map.md`、`result.json`（含 case_id 与契约字段，status 诚实）。

脚本报 FAIL 时的正确做法是：修一轮后复查一次（每个脚本最多两轮），仍无法修复的逐项写入 result.json 的 uncertainty 与 skipped_reason，然后照常交付。脚本退出码仅供定位问题，不作为交付门禁。

完整走查见 `examples/synthetic_case.md`。
