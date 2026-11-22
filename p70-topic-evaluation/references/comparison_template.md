# 比较矩阵模板（prior-work comparison matrix）

本模板是 topic-evaluation 的已有工作比较行 schema，供任何"创新点边界"评估直接复用。
审计器（`proposal` 节）逐行检查下表字段；rubric 对应要求是"按任务、方法、数据、评价方式
和结论建立比较矩阵，识别真正相近的工作，标出无法直接比较的原因"。

## 行 schema

```json
{"id": "M2", "work": "roe2021", "aspect": "metric", "comparable": false,
 "reason": "评价指标不同（F1 对覆盖率），数值无法对齐",
 "evidence": "[roe2021] Table 1, p.5"}
```

| 字段 | 必填 | 说明 |
|-|-|-|
| `id` | 建议 | 行标识，发现项用它回指 |
| `work` | 必填 | 对照的已有工作标识（引用键、文件名或材料编号） |
| `aspect` | 必填 | 比较面，五选一：`task` / `method` / `data` / `metric` / `conclusion` |
| `comparable` | 必填 | 布尔：该面上两项工作能否直接比较 |
| `reason` | comparable=false 时必填 | 为什么无法直接对齐（见锚点表） |
| `evidence` | 必填 | 证据指针（文献定位、材料编号），异同判断由此回查 |

## 五个比较面的定义与典型可比判据

| aspect | 比较什么 | 可直接比较的最低要求 |
|-|-|-|
| `task` | 解决的任务与输入输出 | 同一任务定义；任务不同即不可比 |
| `method` | 方法族与机制假设 | 同一问题设定下方法可替换 |
| `data` | 数据集/语料/样本 | 同一数据集或可说明等价的切分 |
| `metric` | 评价指标与口径 | 同一指标、同一聚合方式；指标不同数值不可对齐 |
| `conclusion` | 结论方向与强度 | 同一条件下方向可比；条件不同需注明 |

## 不可比原因锚点（reason 写法）

一句话回答"为什么数值或设计无法对齐"，落到下列锚点之一并给出具体差异：

- 指标不同：`F1 对 coverage，数值不可对齐`
- 任务不同：`分类任务对生成任务，误差不可比`
- 数据不可得：`其语料未公开，仅摘要可查`
- 条件不可复现：`训练预算差一个量级，效率结论不可比`
- 版本差异：`对照的是 v1，现行为 v3，方法已换代`

## 与其他交付的衔接

- 比较行的 `evidence` 指针与 objectives / content / route / foundation_items 的指针共用
  一套材料定位，全部汇聚到 result.json 的 `evidence_matrix[]`。
- 不可比原因即纳排理由：写进 `evidence_matrix[]` 行的 `include_exclude_reason`。
- 结论相反的文献同时登记进 `uncertainties[]` 并说明取舍——比较矩阵管"边界"，不确定性
  清单管"反面证据"，两者都不许缺席。
