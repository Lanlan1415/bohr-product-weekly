# 完整合成案例（写作09）

> **全合成声明：以下材料、数值、脚本输出均为演示而虚构，不对应任何真实实验或正式案例。** 用途：走查主流程与脚本行为。
>
> **验证与限制声明**：本 Skill 仅在本地合成 fixture 上验证（本文件所示）；平台的 3 个隐藏评测案例与对照组从未在本地运行，不声称任何评测分数。

## 1. 合成输入材料

`/input/case.json`：

```json
{
  "case_id": "syn-methods-001",
  "output_contract": {
    "methods_section": "方法章节成稿路径",
    "param_table": "参数表路径",
    "evidence_map": "来源映射路径"
  }
}
```

`/input/config.yaml`（S2）：

```yaml
model: resnet18
optimizer: adamw
learning_rate: 0.001
batch_size: 32
epochs: 100
dataset: cifar10
split: "8:1:1"
```

`/input/train.log`（S3，节选）：

```
[run 3] loaded config: learning_rate=0.01, batch_size=32, epochs=100
[run 3] dataset: CIFAR-10, 50000 train / 5000 val / 5000 test (seed=2024)
[run 3] final test acc: 0.914
```

`/input/notes.md`（S4）：作者笔记，记"batch size 64 效果较好"。

## 2. 走查要点

1. **材料清点**：`inventory.py` 登记 S1=case.json、S2=config.yaml、S3=train.log、S4=notes.md。
2. **冲突发现**：config 写 `learning_rate: 0.001`，日志第 3 次运行实际加载 `learning_rate=0.01` → 冲突；notes 的 batch size 64 与 config/日志的 32 → 冲突。
3. **处置**：日志为实际执行值，lr 取 0.01、batch_size 取 32；两取值全部记入 evidence_map.md 冲突表；notes 的 64 标记"笔记建议，未采纳"。
4. **缺口**：GPU 型号、PyTorch 版本材料未提供 → §3.1 标 [待确认]（Q1、Q2）。

## 3. param_check.py 实测（合成 fixture）

制造冲突 fixture：把上面 config.yaml、train.log 放 `fixture/materials/`，写一个含 `learning_rate: 0.001` 的草稿（与日志 0.01 冲突）。运行：

```
python3 scripts/param_check.py --materials fixture/materials --draft fixture/draft_bad.md --report fixture/report.md
```

输出（实测）：

```
[FAIL] 参数冲突: learning_rate
  - 0.001  (materials: config.yaml:L3)
  - 0.01  (materials: train.log:L1; draft: draft_bad.md:L1)
结果: 未通过（1 个 FAIL）退出码 1
```

把草稿改为 0.01 后复检：`结果: 通过（0 个 FAIL, 0 个 WARN）退出码 0`。

## 3b. v2 新增实测（合成 fixture）

**YAML 锚点/空值感知**：材料 config.yaml 含 `base_lr: &lr_anchor 0.01`、`learning_rate: *lr_anchor`、`weight_decay: ~`、`<<: *lr_anchor`。实测：锚点正常取值、别名解析为 0.01、空值记"声明未赋值"、合并键记提示——全部 INFO 级，退出码 0，报告含"## 4. YAML 锚点/别名/空值处理"小节。不误报冲突。

**负路径用例（必须被拒绝）**：草稿写"本次采用学习率为 0.001"（被日志 0.01 覆盖的旧 config 值，未标注）。实测：

```
[FAIL] 参数冲突：learning_rate（0.01 / 0.001）
  - 0.01  ← materials: config.yaml:L2(锚点); L3(别名); train.log:L1
  - 0.001 ← draft: draft_conflict.md:L4
结果：未通过（1 个 FAIL）退出码 1
```

键名"本次采用学习率"经后缀别名归一化为 learning_rate——把被覆盖旧值写成"本次采用"会被拦下（method_rules.md §2.7 的机器兜底）。

**contract_check.py（落盘前前置校验，建议性）**：草稿缺 `param_table`/`evidence_map` 契约字段与 `uncertainty` 时实测：`结果: 存在建议修复项（FAIL 3）退出码 1`——正确做法是补齐后复查一次（最多两轮），仍修不完的逐项写入 uncertainty 与 skipped_reason，然后照常落盘交付；字段齐全时 `结果: 无 FAIL 项（FAIL 0）退出码 0`。脚本退出码仅供定位问题，不作为交付门禁。

**selfcheck.py WARN 级**：v1 式参数表（无"被覆盖值/所属阶段"列）+ status=partial 无 skipped_reason 的交付实测 `结果: 通过（FAIL 0 / WARN 3）退出码 0`——新增检查只提醒，不把原本能通过的草稿判 FAIL。

## 4. 最终成稿片段（合成示意）

```markdown
### 3.1 实验设置
所有实验在 [待确认：GPU 型号材料未提供] 上完成，深度学习框架版本 [待确认]。
结果均为单次运行，随机种子 2024 [S3]。

### 3.4 参数设置
模型采用 AdamW 优化，学习率为 0.01，批大小为 32，训练 100 轮 [S3]。
（注：config.yaml 中 learning_rate 记录为 0.001，与日志实际加载值 0.01 不一致，
以日志为准；两值均登记于 evidence_map.md。）[S2, S3]
```

`result.json`：status=partial（2 项待确认），sources 列 S1..S4，change_log 记录冲突处置。`selfcheck.py` 退出码 0。
