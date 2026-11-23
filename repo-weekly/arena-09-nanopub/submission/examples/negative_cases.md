# 负路径自测用例（必须被拒绝的输入，v2 新增）

> 本文件登记**必须被脚本拒绝**的用例：只有正路径通过的校验器是不完整的。
> 全部 fixture 为**全合成**数据，位于 examples/fixtures/。
> 期望：每条命令退出码为 1（未通过）。若某条意外通过，说明校验器被削弱，必须修复。
> 注意：脚本退出码仅供定位问题，不作为交付门禁——正式任务中脚本报 FAIL 时的
> 正确做法是修一轮、把修不完的缺口记入 result.json 的 uncertainty/skipped_reason，
> 然后照常落盘交付，而不是反复修到退出码 0。

## 用例 1：断言无证据链（红线：无证据断言不得发布）

bad_assertion_no_evidence.trig 中 assertion 图有一条三元组，但整个 nanopub
没有 provenance 图（没有 wasDerivedFrom / hasEvidenceAnchor）。

命令：

```
python3 /skills/weekly-skill/scripts/nanopub_check.py \
    /skills/weekly-skill/examples/fixtures/bad_assertion_no_evidence.trig
```

预期与实际输出（本地合成验证，退出码 1）：

```
  [FAIL] 缺少 nanopub 三部结构谓词：hasProvenance
  [FAIL] 缺少命名图：provenance（需 Head/assertion/provenance/pubInfo）
校验结论：未通过（共 1 个文件）
```

## 用例 2：result.json 草稿缺 output_contract 字段（verify-then-write，建议性自查）

命令：

```
python3 /skills/weekly-skill/scripts/contract_check.py \
    --case /input/case.json \
    --draft /skills/weekly-skill/examples/fixtures/bad_result_missing_contract.json
```

（本地复现时把 --case 指向任一含 `"output_contract": ["nanopub_file",
"assertion_count"]` 的 case.json。）

预期与实际输出（本地合成验证，退出码 1）：

```
[FAIL] 草稿缺少 output_contract 声明的字段 1 个：assertion_count
契约前置校验：FAIL=1 WARN=0
结论：未通过（修复后再写入 /app/output/result.json）
```

（正式任务中的正确做法：补一轮缺失字段，做不到的填 null 并写入
uncertainty/skipped_reason，然后照常落盘 /app/output/result.json 交付——
退出码 1 只用于定位缺口，不阻止交付。）

## 校验器校准纪律

- 以上负路径用例在每次改动脚本后必须重跑，退出码必须保持为 1。
- 同时必须重跑正路径（templates/nanopub_template.trig 与
  examples/synthetic_case.md 对应的良好 TriG），确认**原本能通过的稿件不被
  新增检查误判 FAIL**；v2 的 N4/N5/N6 增强检查一律只加 WARN。
