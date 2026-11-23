# 最小调用示例（示例非正式案例结果）

> 以下输入、命令、输出均为示意，用于说明接口与流程，不是正式案例的
> 运行结果。
>
> **验证与限制声明**：本技能全部脚本仅在此类本地合成/示意数据上验证
> （`scripts/run_selftest.py` 可复跑，含幽灵引用等必须被拒绝的负路径
> 用例）；平台评测的 3 个隐藏案例与对照组未在本地运行，本包不声称、
> 不预测任何评测分数。

## 输入（示意）

```
/input/case.json   -> {"case_id": "demo-001", "output_contract": {"introduction_draft": "...", "evidence_map": "..."}}
/input/task.md     -> 「依据给定材料撰写引言与相关工作，中文，著者-出版年制」
/input/paper_notes.md -> 本文方法、实验设置与结果（含表 2、图 3）
/input/reflib.md   -> 文献库 5 条题录与摘要
```

## 调用

```
python3 /skills/weekly-skill/scripts/inventory.py --input /input --output /app/work/materials_register.md
# （模型按主流程抽取 source_cards / claim_pool → 分组对比表 → 缺口+反例界定 → 贡献列表 → 成稿）
python3 /skills/weekly-skill/scripts/structure_check.py --draft /app/output/manuscript.md --evidence /app/output/evidence_map.md --output /app/output/structure_check_report.md
python3 /skills/weekly-skill/scripts/selfcheck.py --output-dir /app/output --case-json /input/case.json
```

## 示意输出（截取，非正式案例结果）

```
[结构检查] ERROR=2 WARN=3 -> FAIL
  [ERROR] 漏斗结构缺段：未找到「研究空白/缺口」对应标题
  [ERROR] 幽灵来源：正文 [S#] 未在证据表登记: S4
  [WARN ] 疑似空转铺垫且无引用支撑：「近年来低资源 NLP 受到广泛关注…」
  [WARN ] 贡献条目缺证据指针（图/表/节/[S#]）：「2. 提出了一种高效的方法」
...按 method_rules 与 funnel_writing_guide 修复后复跑...
[结构检查] ERROR=0 WARN=0 -> PASS
[PASS] 输出目录非空 — 4 个文件
...
自查结论: PASS（FAIL 0 项）
```

structure_check.py 发现问题是**正常工作方式**（退出码 1 表示「有项待
处理」）。脚本报 FAIL 时的正确做法是：修一轮后复查一次（每个脚本最多两轮），
仍无法修复的逐项写入 result.json 的 uncertainty 与 skipped_reason，然后照常
交付。脚本退出码仅供定位问题，不作为交付门禁。
