# 最小调用示例（示例非正式案例结果）

> 以下输入、命令、输出均为示意，用于说明接口与流程，不是正式案例的运行结果。
>
> **验证与限制声明**：本技能全部脚本仅在此类本地合成/示意数据上验证
> （`scripts/run_selftest.py` 可复跑，含必须被拒绝的负路径用例）；平台评测的
> 3 个隐藏案例与对照组未在本地运行，本包不声称、不预测任何评测分数。

## 输入（示意）

```
/input/case.json   -> {"case_id": "demo-001", "output_contract": {"revised_manuscript": "...", "citation_report": "..."}}
/input/task.md     -> 「将稿件引用整理为 GB/T 7714 顺序编码制，合并重复文献」
/input/draft.md    -> 正文引用了 [1][3]；文献表有 [1][2][4] 且 [2] 与 [4] 同 DOI
/input/reflib.bib  -> 文献库导出
```

## 调用

```
python3 /skills/weekly-skill/scripts/inventory.py --input /input --output /app/work/materials_register.md
python3 /skills/weekly-skill/scripts/dedupe_refs.py --refs /app/work/reflist_raw.md --output /app/work/dedupe_report.md
# （模型按 method_rules 完成引用定位、去重合并、GB/T 著录与编号重排）
python3 /skills/weekly-skill/scripts/citation_check.py --manuscript /app/output/manuscript_revised.md --output /app/output/citation_check_report.md
python3 /skills/weekly-skill/scripts/selfcheck.py --output-dir /app/output --case-json /input/case.json
```

## 示意输出（截取，非正式案例结果）

```
[去重] 条目=4 候选=1 防误并=0 -> FAIL      # 发现 [2]×[4] 同 DOI，需合并决策
[校验] 制式=numeric ERROR=1 WARN=2 -> FAIL  # 引而无目：[3]
...修复后...
[校验] 制式=numeric ERROR=0 WARN=0 -> PASS
自查结论: PASS（FAIL 0 项）
```

dedupe_refs.py 与 citation_check.py 发现问题是**正常工作方式**（退出码 1 表示
「有项待处理」）。脚本报 FAIL 时的正确做法是：修一轮后复查一次（每个脚本最多
两轮），仍无法修复的逐项写入 result.json 的 uncertainty 与 skipped_reason，
然后照常交付。脚本退出码仅供定位问题，不作为交付门禁。
