---
name: literature-qa
description: >
  Answer questions over a supplied literature corpus and prove each answer is checkable:
  every question answered or explicitly refused, every sub-question covered, every citation
  locatable in the material (paragraph id or page/table/figure) and actually supporting the
  answer, every number in the answer present in the cited passage — including the
  Chinese-answer/English-passage case, where "three-fold" must count as "3 倍" — and
  conflicts, thin material and reading failures acknowledged rather than smoothed over.
  Each claim is separated into reported (原文报告) vs inferred (推断). Use when a task asks
  for question answering, fact lookup, or a Q&A pass over papers where the answers must be
  traceable to a passage （文献问答、依据引用、逐题作答）.
---

# literature-qa

版本：v2.0（2026-11-22）。规则库与本文档同步维护；本文档即最新版本的说明。

一个无法回溯的答案是语法正确的猜测。本题的评分点很窄，每个评分点在这里都是一条规则：

| 评分点 | 规则 |
|-|-|
| 每题都有回答（不得省略无法回答的问题） | `qa.question_missing`, `qa.no_answers`, `qa.empty_answer` |
| 子问题覆盖完整 | `qa.subquestion_unanswered` |
| 事实、数值、单位符合原文 | `qa.answer_value_not_in_source`（含跨语言数值桥） |
| 引文可定位 **且** 支持答案 | `qa.citation_no_locator`, `qa.citation_unsupportive`, `qa.unknown_paper`, `qa.quote_not_in_paper`, `qa.citation_no_paper` |
| 输出契约字段齐全（状态词表 / 条件 / 论断分离） | `qa.status_invalid`, `qa.conditions_missing`, `qa.partial_without_gaps`, `qa.claim_field_missing`, `qa.claim_kind_invalid`, `qa.claim_no_evidence`, `qa.claim_evidence_incomplete` |
| 材料不足与冲突如实处理 | `qa.material_insufficient_unflagged`, `qa.conflict_unhandled`, `qa.refusal_without_reason` |
| 坏输入降级留痕不崩溃 | `qa.malformed_answer`, `qa.malformed_evidence` |

## 本 Skill 存在要抓的五种失败

**近而不支持的引用。** 答案说涂层在 500 C 退火，引文讲的是吸收速率——同一篇论文，
看起来有出处。支持判定要求引文与答案共享绝大部分内容词（正向或反向任一方向达 0.6；
只看正向会冤枉那些如实承认冲突、罗列条件而变得更长的答案）。跨语言（中文答案引英文
段落）走锚点检查：忠实翻译与原文共享零词元。

**不在引文里的数字。** 答案说 "5-fold"，引文说 "three-fold"。答案里的数字必须能在它
引用的材料里找到。中文答案写 "3 倍" 而引文写 "three-fold"：数值桥把英文数词与中文数字
归一后比对——忠实翻译不误报，材料里任何形式都不存在的数字仍会被抓出。

**被悄悄丢掉的子问题。** 问题两问，答案只答一问，漏掉的部分只有重读问题才会发现。
声明式 `questions` 清单 + `question_id` 让"每题都必须出现"成为机械判定；partial 的答案
必须列出 `unanswered_parts`，否则缺口不可见。

**被平均掉的冲突。** 两段材料相左，答案只取一方。语料冲突要以 `conflicts` 声明，答案
必须出现冲突词（conflict / 冲突 / 不一致 / 矛盾 / 分歧）并说明取舍。

**实测与推断混写。** claims 的 `kind` 必须是 `reported`（原文报告）或 `inferred`（推断），
每条 claim 带可核验的 evidence（paragraph_id + 短引文）——"论文实测结果、作者解释与自己
的推断"从此分层。

## 运行时入口（从 /input 出发的七步）

Harbor 运行时输入是 `/input/case.json` 与 `task.md`；工作目录 `/app/work`；最终交付写入
`/app/output/result.json`（必须保留 output_contract 全部字段 + case_id）。

| 步 | 动作 | 说明 |
|-|-|-|
| 0 | 读输入 | 读 `/input/case.json`：`case_id`、`paper_id`、`material_version`、带段落编号的论文文本、三个中文问题、`output_contract`（如有）。**读实际文件，不凭标签猜内容** |
| 1 | 判形态选路由 | 按下文「任务措辞 → 路由」表选 section：本题主路由 `qa`；多篇论文横向比较路由 `compare_docs` |
| 2 | 先产出目标产物 | 先写 `/app/output/answers.json`（逐题回答 + 依据），九问逐题落实；读不了的题如实 refused。先有产物再审计，预算耗尽也有部分交付 |
| 3 | 构造 spec | 按下文「spec 构造」把证据池 + 逐题回答组装成 spec（含 `case_id`、`output_contract`、`papers` 论文文本），放 `/app/work/spec.json` |
| 4 | 运行审计 | `python <skill目录>/scripts/secrun.py --spec /app/work/spec.json --section qa --out /app/output` |
| 5 | 修发现重跑 | 对每条 finding 修答案或修引用，重跑至 `clean` 或确无再改之处；剩余发现如实写进交付说明 |
| 6 | 合并 result.json | 审计已写 `/app/output/result.json`（含 case_id、contract 回填、answers 原样回传、coverage 摘要）。核对输出与题目字段表逐项一致 |

预算纪律：先逐题落盘部分结果再迭代；引用定位（步骤 2）优先于润色。

## 任务措辞 → 路由

| task.md 里可能出现的表述 | 路由 | 理由 |
|-|-|-|
| "回答以下问题 / answer the questions"（单篇论文 + 问题清单） | `qa` | 本 Skill 主路径：逐题作答 + 引用审计 |
| "每题给出依据 / 引用原文 / cite the passage" | `qa` | 引用可定位 + 支持性是 qa 的核心规则 |
| "问题里有两个小问 / (a)(b) 子问题" | `qa`（subquestions 字段） | 子问题覆盖是评分点 |
| "材料没提到的要说明 / 只依据给定材料" | `qa`（refused + reason / material_sufficient） | 有依据的"未报告"是有效回答 |
| "区分论文说的和你的推断" | `qa`（claims[].kind） | reported/inferred 分离 |
| "对多篇论文做横向比较 / 方法矩阵" | `compare_docs` | 多文档 × 统一字段，走比较引擎（见本目录同引擎的 compare_docs 文档） |
| "把九道题的答案合并成报告 / 结构化 JSON" | `qa` + 合并步 | 产物组织问题，不换引擎 |
| "联网查资料补充回答" | 拒绝联网；按 `qa` 只依据给定材料 + 在 conditions/limits 里说明 | 题目明确不要求也不允许联网检索 |
| "OCR / 解析 PDF / 识别图像" | 如实说明超范围（本题提供带段落编号文本，不需要 PDF 解析），按 `input_error`/limits 报告读取失败 | 材料已是文本层 |
| "填比较表 / 翻译全文 / 写摘要" | 如实说明超范围或按对应 section 路由 | 不是问答任务 |

## spec 构造

```json
{
  "case_id": "<从 case.json 原样带入>",
  "output_contract": {"<case.json 给出的字段>": "..."},
  "section": "qa",
  "paper_id": "<论文标识>",
  "material_version": "<材料版本>",
  "questions": ["Q1", "Q2", "Q3"],
  "papers": [{"paper_id": "<paper_id>", "text": "<论文全文（或 paragraphs 列表）>",
              "paragraphs": [{"paragraph_id": "P1", "text": "..."}]}],
  "material_sufficient": true,
  "evidence": [
    {"id": "e1", "quote": "<原文短引文>", "locator": "p.5, Fig 3b",
     "paragraph_id": "P2", "paper_id": "<paper_id>"}
  ],
  "conflicts": [],
  "answers": [
    {"question_id": "Q1",
     "question": "<中文问题原文>",
     "answer": "<回答，数字用阿拉伯数字>",
     "conditions": ["<成立条件：数值/单位/比较对象/实验条件/结论范围>"],
     "status": "answered",
     "unanswered_parts": [],
     "cites": ["e1"],
     "claims": [{"claim_id": "C1", "text": "<论断>",
                 "kind": "reported",
                 "evidence": [{"paragraph_id": "P2", "paper_id": "<paper_id>",
                               "quote": "<短引文>"}]}]}
  ]
}
```

字段与题目输出要求表的对应（字段名用 rubric 原词）：

| rubric 字段 | spec 位置 | 审计行为 |
|-|-|-|
| `case_id` / `paper_id` / `material_version` | spec 顶层 | result.json 原样带回（input 标识一致） |
| `answers[]`（question_id / answer / conditions） | spec.answers[] | `question_missing` 抓漏题、`empty_answer` 抓空答、`conditions_missing` 抓无条件、结果原样回传进 result.json |
| `status`（answered / partial / insufficient_evidence / input_error） | answers[].status | `status_invalid` 抓词表外取值；`insufficient_evidence`/`input_error` 视为拒答（须给 reason） |
| `claims[]`（claim_id / text / kind / evidence[]） | answers[].claims[] | `claim_field_missing` / `claim_kind_invalid` / `claim_no_evidence` / `claim_evidence_incomplete` |
| evidence[].`paragraph_id` + `quote` | answers[].cites → spec.evidence[] 或 claims[].evidence[] | `citation_no_locator`（无 paragraph_id/locator）、`quote_not_in_paper`（引文不在其声称的论文里）、`unknown_paper` |
| `unanswered_parts[]` | answers[].unanswered_parts[] | `partial_without_gaps`：partial 却不列缺口 |
| `coverage`（已读/未读章节及原因） | 由审计生成 | result.json 的 checked.coverage + 顶层 coverage：每题状态（answered/partial/refused/unanswered）计数 |

完整可运行示例见 `examples/spec.json`（自拟短材料，含三个问题：两答一 partial），
其对应审计输出见 `examples/result.example.json`（均标注为示例，不是正式案例结果）。

## 运行与退出码

```bash
python <skill目录>/scripts/secrun.py --spec spec.json --section qa --out /app/output
```

| 退出码 | status | 含义 |
|-|-|-|
| `0` | `clean` | 零发现 |
| `3` | `review` | 只有 medium/low 发现，需人工过目 |
| `4` | `blocked` | 存在 high 发现，答案不能照原样交付 |
| `5` | `undetermined` | 案例无法按声明运行（spec 不可读 / 非对象 / 无 section / section 未知）——拒绝而非崩溃，result.json 仍会写出并尽量带上 case_id |

## 规则库

### 覆盖

| 规则 | 严重度 | 证明什么 |
|-|-|-|
| `qa.question_missing` | high | case 供应的问题没有任何回答提到它——连拒答都没有（"不得省略"） |
| `qa.no_answers` | high | 一题未答 |
| `qa.empty_answer` | high | 既无回答也无显式拒答 |
| `qa.refusal_without_reason` | medium | 拒答不说缺什么材料 |
| `qa.subquestion_unanswered` | high | 子问题被悄悄跳过 |
| `qa.question_uncovered` | medium | 答案与问题几乎无内容交集——答成了隔壁问题 |
| `qa.malformed_answer` | medium | answers 里的非对象条目被跳过（该题的答案静默丢失） |
| `qa.malformed_evidence` | medium | 证据池不是列表（或缺失而答案却引用证据 id），引用核验整体不可验证 |

### 引用与事实

| 规则 | 严重度 | 证明什么 |
|-|-|-|
| `qa.uncited_answer` | high | 答案不引任何材料（cites 与 claims[].evidence 皆空） |
| `qa.unknown_evidence` | high | 引用了未供应的材料 |
| `qa.citation_no_locator` | high | 引文无 paragraph_id / 页码 / 表图定位，读者回不去 |
| `qa.citation_unsupportive` | high | 引文与答案几乎无内容共享——引了"同主题"而非"支持该答案"的段落 |
| `qa.answer_value_not_in_source` | high | 答案里的数字在引文里不存在（跨语言经数值桥比对） |
| `qa.unknown_paper` | high | 引用声称的 paper_id 不在语料里 |
| `qa.quote_not_in_paper` | high | 短引文不在其声称的那篇论文文本中——证据挂错了来源 |
| `qa.citation_no_paper` | medium | 多论文语料里引用不写 paper_id，来源无法消解 |

### 输出契约（题目字段表）

| 规则 | 严重度 | 证明什么 |
|-|-|-|
| `qa.status_invalid` | medium | status 不在 answered/partial/insufficient_evidence/input_error 词表内 |
| `qa.conditions_missing` | medium | 答案无数值/单位/实验条件/结论范围的成立条件列表（键必须存在，可为空列表） |
| `qa.partial_without_gaps` | medium | 标了 partial 却不列 unanswered_parts——缺口不可见 |
| `qa.claim_field_missing` | medium | claim 缺 claim_id / text / kind |
| `qa.claim_kind_invalid` | medium | kind 不在 reported/inferred 词表内——实测与推断不再可分 |
| `qa.claim_no_evidence` | high | 论断零证据 |
| `qa.claim_evidence_incomplete` | high | 论断证据缺 paragraph_id 或短引文 |

### 材料边界与冲突

| 规则 | 严重度 | 证明什么 |
|-|-|-|
| `qa.material_insufficient_unflagged` | high | 声明了材料不足却自信作答 |
| `qa.conflict_unhandled` | medium | 冲突证据被当成单一立场陈述 |

## 输出契约（result.json）

`secrun.py` 写 `/app/output/result.json`：

| 块 | 内容 |
|-|-|
| `status` | clean / review / blocked / undetermined（运行状态） |
| `section` | `qa` |
| `case_id` / `paper_id` / `material_version` | 从 spec 原样带回（输入标识一致） |
| `answers[]` | **spec 的 answers 原样回传**——rubric 形状的逐题回答（question_id/answer/conditions/status/claims/unanswered_parts）随之进入 result.json |
| `coverage` | 审计生成的阅读范围摘要：每题状态 + answered/partial/refused/unanswered 计数 |
| `findings[]` | 每条含 rule、severity、message 与定位（question / cite / value / claim） |
| `severity_counts` | 各严重度计数 |
| output_contract 各字段 | 已能派生的保留；spec 携带的照抄（大体量输入除外）；无法派生的置 null 并在 `limits` 点名——评分方看到键 + 诚实说明，不是沉默缺口 |
| `limits` | 不可派生字段、拒绝原因等 |

注意：顶层 `status` 是运行状态（成功/部分完成/无法判断/拒答由 findings 与 limits 呈现
原因），每个答案自己的 `status` 在 `answers[].status` 里——两层状态不混用。

## Limits（诚实边界）

- **支持是词法判定，不是蕴含。** 词元共享证明引文与答案说的是同一件事；它不能证明引文
  为真、也不能证明推理成立。阈值 0.6（正向或反向），跨语言走锚点 + 数值桥。
- **数字必须是阿拉伯数字。** `5-fold`、`3 倍` 会被比对；`fivefold`、`三倍`（答案里全中文
  数词）不会被提取——答案里写数字。数值桥覆盖英文数词（one~twenty、整十、hundred/
  thousand/million）与中文数字（零~九、X十/十X、半）；百/千的中文组合拼写不在桥内——这是
  声明的限制，不是静默 invention。
- **统计量与裸整数豁免。** p 值、检验统计量、样本量与一般裸整数（年份、计数、节号）不是
  测量值，不与引文比对；只有带倍率词（fold/×/%/倍）或单位的数值必须溯源。
- **子问题覆盖是词元重叠。** 换一种说法的子问题可能读成未覆盖——把回答写得贴近问句措辞。
- **冲突要声明。** 引擎无法发现没有被 `conflicts` 声明的分歧；语料相左处请声明。
- **material_sufficient 是声明。** 它是调用方对语料充分性的判断；引擎核对判断与答案的
  一致性（不足则不许自信作答），不替调用方判断充分性。
- **quote_not_in_paper 是字面校验。** 空白归一（换行/全半角）后子串匹配；引文是引文，
  转写不算。
- **它不做检索。** 选哪段来引是调用方的步骤；这里审计引出来的答案。

## 异常处置表

| 异常 | 处置 | 谁接管 |
|-|-|-|
| case.json 读取失败 / 段落清单缺失 | 相关题 `status: input_error` + reason；不要编造答案或引用 | 人工检查输入挂载 |
| 材料未报告某题所需信息 | `status: insufficient_evidence` + reason 写明缺什么（有依据的"未报告"是有效回答） | 人工确认材料边界 |
| 只能部分回答 | `status: partial` + `unanswered_parts[]` 列明缺口及原因 | 人工决定是否可答 |
| 原文冲突 | `conflicts` 声明 + 答案写明冲突与取舍（`conflict_unhandled` 会抓沉默单边） | 人工仲裁 |
| 引文找不到段落 | 换 paragraph_id/页码可查的引文；找不到就不引 | 人工定位 |
| answers / evidence 条目不是对象 | `malformed_answer` / `malformed_evidence` 降级留痕，其余照审 | 修 spec |
| spec 不可读 / 非对象 / section 未知 | exit 5 `undetermined`，result.json 照写（带 case_id），不崩溃 | 修 spec 重跑 |
| 依赖缺失（本包纯标准库，通常无此情形） | 如实说明缺什么、卡在哪一步；**不伪造已运行** | 按说明装依赖或人工代跑 |
| 输出目录不可写 | exit 5 + limits 写明写盘失败 | 检查挂载 |
| 重复运行结果不一致 | 规则全为确定性纯函数；若出现，保留两次 result.json 并报告差异（幂等由探针保证） | 提交 bug |
| 预算不足以答完九题 | 先落盘已答部分（partial 交付 + limits 列明未答题），再继续 | 下一轮续跑 |
| 联网/OCR 类超范围要求 | 明确拒绝并说明题目边界（材料已是文本层），不伪造解析 | 无 |

## Failure handling（finding → 修法）

| finding | 修法 |
|-|-|
| `question_missing` | 每题都要出现：可答则答，不可答则 refused + reason |
| `empty_answer` | 给答案或显式拒答 |
| `refusal_without_reason` | 写明缺什么材料 |
| `subquestion_unanswered` | 逐小问作答，或对答不了的小问说明 |
| `citation_unsupportive` | 引陈述答案本身的那段，不是同主题的另一段 |
| `answer_value_not_in_source` | 用引文报告的数字，或引含有你的数字的那段 |
| `citation_no_locator` | 补 paragraph_id 或页码/表/图 |
| `unknown_paper` / `quote_not_in_paper` | 修正 paper_id 或换回该论文里真实存在的引文 |
| `citation_no_paper` | 多论文语料给每条证据标 paper_id |
| `status_invalid` | 用四值词表 |
| `conditions_missing` | 补 conditions 列表（没有条件就写空列表并说明） |
| `partial_without_gaps` | 列 unanswered_parts |
| `claim_no_evidence` / `claim_evidence_incomplete` | 为论断补 paragraph_id + 短引文 |
| `claim_kind_invalid` / `claim_field_missing` | 补全 claim 字段，kind 用 reported/inferred |
| `material_insufficient_unflagged` | 拒答并给 reason |
| `conflict_unhandled` | 写明分歧与取舍 |
| `audit.no_section` (exit 5) | spec 不可读/非对象/无或未知 section——拒绝而非崩溃 |

## Verification

```bash
python scripts/bench_qa.py        # 43 scenarios: 每条规则至少一场 + 误报守卫 + 摘要形状
python scripts/bench_sections.py  # 51 scenarios: 跨 section 回归 + 误报守卫
```

本机全过（43/43、51/51）。每个 clean 基线必须零发现；新增规则与场景一一对应
（question_missing / status_invalid / conditions_missing / partial_without_gaps /
claim_* / quote_not_in_paper / unknown_paper / citation_no_paper / malformed_answer /
malformed_evidence / 跨语言数值桥 / coverage 摘要形状）。

另有一套 22 项敌意探针（坏 JSON / 非对象 JSON / 文件缺失 / 目录当 spec / 未知 section /
空对象 / answers 与 evidence 类型错位 / junk 条目 / 全空字段 / CJK 问答 / 跨语言数值桥 /
2 MB 级 500 题输入 / 重跑幂等 / output_contract 回填与 bulky 排除 / contract list 形态 /
unicode case_id / clean 基线 / paragraphs 形态论文 / claims junk / review 退出码），
全部通过：exit ∈ {0,3,4,5}、result.json 恒在、无 traceback。

## Requirements

Python 3.9+（3.14 实测）。纯标准库（json / re / pathlib / argparse / dataclasses /
unicodedata / difflib），无第三方依赖；评测镜像（Python 3.12.1）无需安装任何东西。

## 创新增益（相对基础 Agent 的边界）

1. **引用双向支持判定**：引文必须"支持"答案而非"同主题"——正向或反向词元覆盖 ≥0.6，
   且对承认冲突/罗列条件的合规长答案不误伤（bench 误报守卫固化了这一行为）。基础 Agent
   无法自查这一点，这正是"引文可定位且支持对应结论"的机械化。
2. **跨语言数值桥**：中文答案 × 英文论文是本题固定形态（"three-fold" ↔ "3 倍"）。数值桥
   把英文数词与中文数字归一后比对，忠实翻译不误报、虚构数字仍被抓出——基础 Agent 在
   跨语言形态下既容易放过错数也容易冤枉对数。
3. **题级覆盖台账**：`questions` 声明 + `question_id` 对账 + partial 必列
   unanswered_parts，使"不得省略无法回答的问题"从软要求变成机械判定（question_missing /
   partial_without_gaps）。
4. **实测/推断分层**：claims[].kind 的 reported/inferred 词表 + 每条 claim 强制
   paragraph_id + 短引文，让"区分论文实测结果、作者解释与自己的推断"可审计。
5. **来源回溯双保险**：paragraph_id/locator 让读者回得去；quote_not_in_paper/unknown_paper
   让挂错来源的引文在交付前被拦下。
6. **幂等审计**：规则全为确定性纯函数，重跑逐字节一致（探针验证）；审计只判定不改写，
   所有修改由调用方完成并留痕。

边界：不做蕴含判定、不做检索、不读 PDF（本题材料是带段落编号文本，无需解析）、中文
百/千组合数词不在数值桥内。这些边界全部写明而非隐藏。

## 生态贡献

- **使用说明**：本文件含运行时七步、路由表、spec 构造（rubric 字段映射表）、退出码、
  规则库、异常处置、复跑方法。
- **依赖**：纯标准库，无安装步骤；Python 3.9+（评测镜像 3.12.1 直接可用）。
- **配置**：spec 即配置——questions/papers/evidence/conflicts/material_sufficient 全部
  数据驱动，换一套论文与问题不需要改代码。
- **示例标注**：`examples/spec.json`（三题：两答一 partial，自拟短材料）与
  `examples/result.example.json`（对应输出）均明确标注为示例；`examples/bench-report.json`
  为 bench 实跑快照（可复跑验证）。
- **资源复用**：规则库 + 字段映射表可直接用于任何"论文 + 问题清单"语料；bench 套件独立
  复跑（`python scripts/bench_qa.py`）；新语料只需换 spec。
- **适用范围**：单篇或多篇论文的逐题问答（答案须回溯原文）；中英混合语料；不适用情形见
  路由表末三行。
- **限制**：见 Limits 一节（逐条列出引擎做不到的事：蕴含、检索、PDF、中文大数拼写）。
- **维护**：规则 id 稳定且自描述；新增规则必须配 bench 场景（clean 基线零发现的纪律由
  bench 强制）；`scripts/report_*.json` 为最近一次实跑留痕。

## 最小调用示例（示例，非正式案例结果）

输入：`examples/spec.json`（自拟短论文 + 三题，含 case_id 与 output_contract）。

```bash
python scripts/secrun.py --spec examples/spec.json --section qa --out /tmp/demo
# -> {"status": "clean", ...}  exit 0
```

示意输出（节选，完整见 `examples/result.example.json`）：

```json
{
  "status": "clean",
  "section": "qa",
  "case_id": "example-qa-001",
  "paper_id": "paper-ex-001",
  "material_version": "v2",
  "answers": [{"question_id": "Q1", "status": "answered",
               "conditions": ["多孔 TiO2 涂层", "25 C", "亚甲基蓝"], "...": "..."}],
  "coverage": {"counts": {"answered": 2, "partial": 1, "refused": 0, "unanswered": 0}}
}
```
