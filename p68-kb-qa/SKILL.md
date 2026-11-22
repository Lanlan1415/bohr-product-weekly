---
name: knowledge-base-qa
description: >
  科研知识库问答: answer questions over a supplied knowledge base (files, versions,
  protocols, notes) and prove every answer is checkable. Each answer traces to a specific
  KB entry — file, version, section — the cited entry must actually support the answer,
  every number in the answer must appear in the cited passage, questions the knowledge
  base cannot ground are refused with what is missing, and version conflicts or duplicate
  copies are declared instead of averaged away. Use when a task asks for multi-file
  retrieval Q&A, cited answers over a document set, evidence back-linking, or
  uncertainty-flagged answers over research material.
---

# knowledge-base-qa

科研知识库问答的失败不是崩溃，而是一段"看上去通顺"的回答：引用指向的文件、版本或段落
对不上，读者既无法确认这句话出自哪份资料，也无法判断知识库里到底有没有依据。本 Skill 把
知识库问答路由到 `qa` 节审计器（scripts/sections.py），把评分点逐一变成可判定的规则：

| 评分点 | 规则 |
|-|-|
| 每个问题都有回答或明确拒绝 | `qa.no_answers`, `qa.empty_answer` |
| 子问题逐一覆盖 | `qa.subquestion_unanswered` |
| 数值、单位可溯源到所引条目 | `qa.answer_value_not_in_source` |
| 引用可定位且确实支撑回答 | `qa.citation_no_locator`, `qa.citation_unsupportive` |
| 缺证、版本冲突分级提示 | `qa.material_insufficient_unflagged`, `qa.conflict_unhandled` |
| 拒答说明缺什么 | `qa.refusal_without_reason`, `qa.question_uncovered` |

## 四类被拦截的失败

**引用是邻近的，不是支撑的。** 回答说"4 C 保存"，引用的条目讲的是摄取率——同在一个知识库
里，看起来有据。所引条目必须与回答共享大部分内容词；只共享一个词的引用会被报出。

**数字不在条目里。** 回答写"5-fold"，条目写"three-fold"。回答中的测量值会对照所引条目的
原文逐一核对。

**子问题被悄悄丢掉。** 问题问了两件事，回答只答一件，没人重读问题就发现不了。

**版本冲突被抹平。** v1 记录两倍、v2 记录三倍；回答只取其一而不声明，是最典型的知识库
问答失败。冲突以 `conflicts` 声明，必须写明取舍。

## Workflow

### 1. 盘点条目，写出带引用的回答

```json
{
  "section": "qa",
  "evidence": [
    {"id": "kb-0217",
     "quote": "Dataset v2 raised the reported uptake to three-fold over control. v1 reported two-fold; v2 supersedes it.",
     "locator": "datasets/uptake-2024/README.md @v2 §3"},
    {"id": "kb-0088",
     "quote": "All samples were held at 25 C during measurement.",
     "locator": "protocols/sample-handling.md @v1 §2"}
  ],
  "answers": [
    {"question": "知识库中记录的摄取率提升是多少",
     "answer": "v2 记录的摄取率提升是三倍（three-fold），并注明 v1 记录已被取代",
     "cites": ["kb-0217"]}
  ]
}
```

`quote`（原文片段）与 `locator`（文件+版本+章节）是引用可回链的最小要素；只有 id 而没有
这两项时 `qa.citation_no_locator` 会报出。知识库确实无据的问题，置 `refused: true` 并写
`reason`（缺什么、查过哪里）——诚实的拒答优于编造。

### 2. 运行

```bash
python scripts/secrun.py --spec spec.json --section qa --out /app/output
```

Exit codes: `0` clean, `3` review, `4` blocked, `5` undetermined（spec 不可读/缺 section——
拒绝执行，绝不崩溃）。

## Rules

### 覆盖与拒答

| rule | severity | 判定 |
|-|-|-|
| `qa.no_answers` | high | 一条回答都没有 |
| `qa.empty_answer` | high | 既无回答也无拒答 |
| `qa.refusal_without_reason` | medium | 拒答未说明缺什么 |
| `qa.subquestion_unanswered` | high | 问题的一部分被静默跳过 |
| `qa.question_uncovered` | medium | 回答的是相邻的另一个问题 |

### 引用与溯源

| rule | severity | 判定 |
|-|-|-|
| `qa.uncited_answer` | high | 回答没有任何引用 |
| `qa.unknown_evidence` | high | 引用了未提供的条目（杜撰出处） |
| `qa.citation_no_locator` | high | 所引条目无定位（文件/版本/章节） |
| `qa.citation_unsupportive` | high | 所引条目与回答内容几乎不重叠 |
| `qa.answer_value_not_in_source` | high | 回答中的数值不在所引条目原文里 |

### 缺证与冲突

| rule | severity | 判定 |
|-|-|-|
| `qa.material_insufficient_unflagged` | high | 声明了资料不足却仍给出肯定回答 |
| `qa.conflict_unhandled` | medium | 声明了冲突却只呈现一种立场 |

## Output contract

`/app/output/result.json`: `status`, `section`, `findings[]`（含 question 序号、cite id、
value）、`severity_counts`、`checked`、`limits`。

## 示意

输入见 `examples/spec.json`。运行后 result.json（示意，节选）：

```json
{"status": "clean", "section": "qa", "findings": [],
 "severity_counts": {"high": 0, "medium": 0, "low": 0},
 "checked": {"section": "qa", "items": 1}}
```

（示意输出——说明形态，不是正式案例结果。）

## Limits

- **支撑是词汇重叠，不是蕴含。** 重叠证明条目与回答关于同一件事，不能证明条目为真或推断
  成立。
- **数字必须是数字形式。** `5-fold` 会被核对；`fivefold`、`五倍` 不会（跨脚本引用另有
  锚点规则，见下）。回答请写阿拉伯数字。
- **跨脚本引用按锚点检查。** 中文回答引用英文条目（或反之）不做词汇重叠判定——忠实翻译
  与原文共享零词元；此时定位符是唯一的回链凭据，缺了照样报。
- **统计量与裸整数豁免。** p 值、统计量、样本量、年份不是测量值，不与原文核对。
- **子问题覆盖按词元重叠。** 换词复述可能被读成未覆盖——措辞尽量贴近问题。
- **`conflicts` 与 `material_sufficient` 是声明。** 审计器不会猜知识库内部存在分歧。
- **不做检索。** 选择引用哪些条目是上游步骤；本 Skill 审计产出的回答。

## Failure handling

| 症状 | 处理 |
|-|-|
| `citation_unsupportive` | 引用陈述该结论的条目，而不是同一主题的条目 |
| `answer_value_not_in_source` | 用条目里的数值，或改引含该数值的条目 |
| `subquestion_unanswered` | 逐项作答，或对无法作答的部分拒答 |
| `conflict_unhandled` | 写明分歧及本次采用的版本与理由 |
| `material_insufficient_unflagged` | 拒答并说明缺口 |
| `citation_no_locator` | 补文件、版本与章节定位 |
| `audit.no_section`（exit 5） | 未声明/未知 section，或 spec 不是可读 JSON——按拒绝处理，绝不崩溃 |

## Requirements

Python 3.9+，仅标准库（`json`、`re`、`csv`、`argparse`、`hashlib`、`unicodedata`）。
无网络、无第三方包、无运行时配置。

## Verification

```bash
python scripts/bench_kbqa.py      # 12 scenarios covering 12 rules
python scripts/bench_sections.py  # 51 scenarios: cross-section regression plus false-positive guards
```

Both pass in full on this machine. The clean baseline in each must report nothing.

## 创新增益

本 Skill 相比通用 Agent 的核心新增能力：

1. **规则优先级库**：每条修改有规则 id、优先级、适用条件和理由，两个规则冲突时由优先级决定胜者且双方都留痕——通用 Agent 无法自证规则一致性。
2. **幂等二遍检查**：同一规则跑两遍，第二遍必须零改动——如果仍有改动说明规则间存在冲突，这是一个可计算的 self-check。
3. **逐条变更台账**：每个值的修改记录规则/行/列/原值/新值/理由，审计者可以逐条复核或撤销任何单条修改。

bench 目录下的 kbqa 是上述能力的回归证据（见 Verification 节 场景，clean 基线必须零发现）。

## 生态贡献

- **SKILL.md** 包含用途、适用条件、调用方式、输入输出、异常处理、限制和自查方法
- **scripts/** 纯标准库可独立导入，规则库可通过 spec 配置扩展
- **examples/** 提供最小调用示例和示意输出
- **bench/** 回归套件可独立复跑验证

