# 限定词分级词表（CN+EN · 学术语言润色 · v2）

限定强度守恒是"没改坏"评分点的核心。**跨级移动禁止**（verify.py 的守恒门
按计数变化自动回退）；**同级替换**也须谨慎，语义有差时走【备选】机制。

## 分级（强 → 弱）

| 级 | 含义 | EN | CN |
|---|---|---|---|
| Q0 断言 | 无条件直陈 | show / demonstrate / prove（慎用）/ is / confirms | 表明 / 证明 / 证实 / 是 |
| Q1 强倾向 | 证据强的肯定 | establish / reveal / confirm | 确认了 / 明确了 |
| Q2 中断言 | 常规学术肯定 | indicate / suggest / imply / support | 提示 / 表明（弱读）/ 支持 |
| Q3 弱断言 | 明显保留 | may / might / could / appear / seem / likely / possibly / potentially | 可能 / 或许 / 有望 / 似乎 / 一定程度上 |
| Q4 约数/近似 | 数值限定 | approximately / about / roughly / around / ~ | 约 / 大约 / 大致 / 近 |
| Q5 否定与限制 | 否定范围 | not / no / never / neither / without / hardly / scarcely / only / merely | 不 / 无 / 未 / 没有 / 并非 / 无法 / 毫不 / 难以 / 仅 / 只 |

## 使用规则

1. **同级替换**：允许但需理由（如语域：about → approximately 是期刊语域
   提升，计数不变、强度不变）；语义有差时给【备选】（significant vs
   substantial 类）。
2. **跨级移动 = 违规**：may(Q3) → demonstrate(Q0) 是加强；show(Q0) →
   suggest(Q2) 是削弱；both 都被守恒门拒绝并回退。唯一例外：作者/任务书
   书面依据 + `allow_conservation_break` + reason，并在 change_log 留痕。
3. **Q4 与数字绑定**：约数词随数字一起守恒；"约 25 °C" → "25 °C" 同时
   丢Q4 与精度信息，双违规。
4. **Q5 否定范围**：否定词计数变化必被拒；"not significantly affect" 不可
   润成 "barely affect"（否定变弱化≈方向漂移）；"仅/only" 的范围改动同理。
5. **因果词视同限定**：correlate with / 与…相关（弱）≠ cause / 导致（强）；
   associate → cause 的升级按跨级移动处理。
6. **时态语态不改变级别**："may have suggested" → "may suggest" 是语法修正，
   不构成跨级。

## 与脚本的对应

- `verify.py` / `conservation_check.py` 内置的 HEDGES/NEG 清单覆盖上表
  高频词；遇到表外限定词（如 "arguably"、"从某种意义上说"），人工按同级
  原则核对并在 change_log 记录——脚本只保高频，判断责任在 Agent。
