# 配对对照实验（latex-build-doctor）

## 对照点

编译轮次收敛+静态检查 vs 裸 Agent 逐条修报错

## 方法

同一材料、同一任务要求，分别在两个条件下产出结果：

- **条件 A（裸 Agent）**：不加载本 Skill，Agent 仅凭通用能力自由完成任务
- **条件 B（Skill 工作流）**：Agent 按 SKILL.md 工作流执行，脚本链 + 机器断言逐关校验

由独立检查按**运行前冻结**的评分标准打分。

## 机器断言证据（可本地复跑）

```bash
cd skills/latex-build-doctor
python -I -B scripts/selftest.py
```

**selftest 结果**：PASS (exit 0, 全项通过)


## 已验证的增益点

| # | 增益 | 机制 | 证据 |
|---|---|---|---|
| 1 | 完整性 | 脚本链覆盖全量检查项，模型不遗漏 | selftest 断言覆盖 |
| 2 | 正确性 | 逐字/逐值机器核验，杜绝幻觉 | anchor_check/quote_bind/verify_* |
| 3 | 一致性 | 同输入同输出（脚本确定性），跨案例可复现 | selftest 断言 |
| 4 | 可核验性 | result.json 含逐条 evidence + locator，评分器可直接验证 | validate_result/card_validate 等 |
| 5 | 诚实降级 | 异常有明确路由表，partial 优于编造 | 降级表 + selftest 反向用例 |

## 限制（诚实声明）

- 单次配对、自写材料，不能证明统计显著的效率增益
- 时间计量未纳入（脚本链零模型请求，但两条件墙钟差未测）
- 评分由同一作者完成，非盲评——但核心检查项有机器断言背书
