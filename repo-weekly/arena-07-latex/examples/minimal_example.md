# 最小调用示例（写作13）

> **说明：本示例的输入、调用与输出均为示意，非正式案例结果。**
> **验证限制**：本包仅做过本地合成验证；平台 3 个隐藏案例与对照未在本地运行，不声称分数。

## 输入（示意）

```
/input/
  case.json        # {"case_id": "demo-002", "output_contract": {"manuscript_source": "...", "pdf_preview": "...", "build_record": "..."}}
  task.md          # 任务：把 draft.md 迁入给定模板并编译交付
  template/journal.cls
  draft.md
  refs.bib
```

## 调用（按绝对路径，不依赖 CWD）

```bash
# 第1步：材料与工程清点
python3 /skills/weekly-skill/scripts/inventory.py --input /input --out /app/work/materials_register.md

# 第2步：按 templates/project_structure.md 组织工程并迁入内容（模型完成）

# 第3步：编译前静态检查
python3 /skills/weekly-skill/scripts/tex_static_check.py --main /app/work/main.tex --report /app/work/static_check.md

# 第4步：先定编译器（题目/模板指定 > 工程现有配置 > 启发式默认，禁止强制更换），再编译（工作目录为工程目录）
cd /app/work && pdflatex -interaction=nonstopmode main.tex && bibtex main && pdflatex main && pdflatex main

# 第5步：出错时解析日志（输出分 错误(阻断)/警告(不阻断) 两级；脚本只诊断不改写源码）
python3 /skills/weekly-skill/scripts/log_triage.py --log /app/work/main.log --report /app/work/log_triage.md

# 第6步a：result.json 落盘前的契约前置校验（建议性：FAIL 能修则修一轮，修不完记入 uncertainty 后照常落盘；退出码仅供定位问题，不作为交付门禁）
python3 /skills/weekly-skill/scripts/contract_check.py --case /input/case.json --result /app/work/result_draft.json

# 第6步b：交付自查
python3 /skills/weekly-skill/scripts/selfcheck.py --output /app/output --case /input/case.json
```

## 示意输出（非正式案例结果）

`log_triage.py` 对含错日志：

```
编译日志错误分类报告
错误 2 条，警告 3 条
[E3 math_mode] methods.tex:42  ! Missing $ inserted.
  修复建议：正文中的数学符号须包进 $...$；下划线文本用 \_（见 error_fix_table.md E3）
[E8 citation] main.log  Citation 'smith2020' undefined
  修复建议：多为轮次不够，按 pdflatex→bibtex→pdflatex×2 重编；仍缺则核对 .bib key
结果：未通过（2 个错误）退出码 1
```

`tex_static_check.py` 正常情况末行：`结果：通过（错误 0，警告 1）退出码 0`。

最终 `/app/output/`：工程源码、真实编译的 main.pdf、build_record.md、evidence_map.md、result.json（status 诚实）。

脚本报 FAIL 时的正确做法是：修一轮后复查一次（每个脚本最多两轮），仍无法修复的逐项写入 result.json 的 uncertainty 与 skipped_reason，然后照常交付。脚本退出码仅供定位问题，不作为交付门禁。

完整走查见 `examples/synthetic_case.md`。
