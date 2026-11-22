# 强度分级口径（strength scale）

本文件是 evidence-driven-writing 的强度分级锚点，供任何"论断—证据"写作任务直接复用。
审计器只检查标签存在、有依据、与正文动词相称；标签本身的判定依据本口径。

## 三级标签

| 标签 | 判定锚点（依据必须落在这些事实上） | 不确定性要求 |
|-|-|-|
| `strong` | 对照/随机设计，样本量足以支撑效应，独立重复验证，来源为正式发表的一次研究或多篇一致研究 | 可留空；但范围声明（人群/条件）建议仍写 |
| `moderate` | 单组前后对照或观察性研究，样本量中等，未经独立重复，或多篇研究结论方向一致但设计有缺陷 | 必填：说明最脆弱的一环（样本/设计/未重复） |
| `weak` | 个案、小样本、机制推测、仅摘要可读、预印本、或与部分证据冲突 | 必填：说明范围与反例 |

## 强度与动词对应表（draft_overstates_strength 的判定基础）

| 标签 | 允许的正文动词（中/英） | 被拦截的过强动词 |
|-|-|-|
| strong | show / demonstrate / establish / 显示 / 表明 | prove / proves（"证明"留给数学与形式化结果） |
| moderate | suggest / indicate / is consistent with / 提示 / 支持 | demonstrate, prove, 证明, 证实 |
| weak | may / might / appears to / 可能 / 或许 / 推测 | suggest 以上全部 |

审计规则 `ew.draft_overstates_strength` 对 weak/moderate 主张的成稿拦截
prove / proves / demonstrate / demonstrates / confirm / confirms / establish / establishes /
证明 / 证实。改写方向是降动词，不是删证据。

## 依据写法（strength_basis）

一句话回答"这个等级凭什么"：设计、样本、重复三者至少落在两个上。

- 合格：`controlled experiment, n=6, replicated`；`multi-site cohort, n=214, direction agrees with doe2020`
- 不合格：`we believe`；`significant`（没说设计）；`high quality`（无事实锚点）

## 来源类型与强度上限

| 来源情形 | 强度上限 | 机制 |
|-|-|-|
| 撤稿来源 | 不可用 | `ew.retracted_source_used` 直接拒绝 |
| 预印本 | 不可支撑 strong | `ew.preprint_as_strong` 降权提示 |
| 仅摘要（abstract_only） | 不可支撑 strong | `ew.support_abstract_only`；全文取得前主张降级 |
| 无正文可核（text 缺失） | 主张挂起 | `ew.quote_unverifiable`；登记 pending 直到取得全文 |

## 冲突登记

来源登记 `conflicts_with`（与其他证据冲突）或 `abstract_conflict`（自相矛盾）后，引用该来源
的每条主张必须带 `conflict_note`：说明冲突方向、采信理由。未登记即报
`ew.conflict_unregistered` / `ew.abstract_conflict_unregistered`。
