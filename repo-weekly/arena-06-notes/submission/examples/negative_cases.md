# 负路径自测用例（必须被拒绝的输入，v2 新增）

> 本文件登记**必须被脚本拒绝**的用例：只有正路径通过的校验器是不完整的。
> 全部 fixture 为**全合成**数据，位于 examples/fixtures/。
> 期望：每条命令退出码为 1（未通过）。若某条意外通过，说明校验器被削弱，必须修复。
>
> **交付语义说明（v3）**：本文件演示的是校验器在本地合成 fixture 上的拦截力
> （开发期自测），**不是交付门禁**。真实评测中脚本报 FAIL 时的正确做法是：
> 逐项把缺口记录到 result.json 的 uncertainty / skipped_reason，然后照常交付；
> 脚本退出码仅供定位问题，不作为交付门禁。

## 用例 1：笔记引用未登记来源（红线：来源造假）

命令：

```
python3 /skills/weekly-skill/scripts/notes_check.py \
    --notes /skills/weekly-skill/examples/fixtures/bad_notes_unregistered.md \
    --register /skills/weekly-skill/examples/fixtures/materials_register.md
```

预期与实际输出（本地合成验证，退出码 1）：

```
[FAIL] 锚点缺定位信息（页/节/段/图表）1 处，示例：[S9]
[FAIL] 锚点引用未登记的来源编号 3 处：[S9 p.9 §9]、[S9]
检查结果：FAIL=2 WARN=0
结论：未通过
```

## 用例 2：result.json 草稿缺 output_contract 字段（契约草稿核对拦截）

命令：

```
python3 /skills/weekly-skill/scripts/contract_check.py \
    --case /input/case.json \
    --draft /skills/weekly-skill/examples/fixtures/bad_result_missing_contract.json
```

（本地复现时把 --case 指向任一含 `"output_contract": ["notes_file",
"summary_one_line"]` 的 case.json。）

预期与实际输出（本地合成验证，退出码 1）：

```
[FAIL] 草稿缺少 output_contract 声明的字段 1 个：summary_one_line
契约前置校验：FAIL=1 WARN=0
结论：未通过（建议修复一轮后复查；缺口记入 uncertainty/skipped_reason 后照常交付）
```

## 校验器校准纪律

- 以上负路径用例在每次改动脚本后必须重跑，退出码必须保持为 1。
- 同时必须重跑正路径（examples/synthetic_case.md 对应的良好笔记），
  确认**原本能通过的草稿不被新增检查误判 FAIL**；新增检查项一律只加 WARN。
