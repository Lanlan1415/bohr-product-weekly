---
name: paper-structure
description: >
  论文逻辑与论证审查：把一篇稿件的一轮结构诊断变成可逐条复核的交付物。抽取研究问题、
  主张与贡献后按六个维度（研究问题、章节结构、论证链、段落关系、重复、结论范围）逐维
  审查，每条发现必须逐字引用稿件中真实存在的句子并给出定位，重大发现必须给出可执行的
  修改建议；引言承诺的问题必须在交付章节兑现（承诺-交付核查），摘要与结论口径必须一致，
  观察性设计不得写因果结论。风格偏好被拒绝冒充结构缺陷，无法确认的条目进入待复核
  而不是凭空补结论。结果回填案例的 output_contract 字段与 case_id。Use when a task asks
  for a structural review, a logic diagnosis, or a revision plan for a manuscript, where
  every finding must be traceable to a sentence that actually exists in the paper.
---

# paper-structure（论文逻辑与论证审查）

The deliverable is a diagnosis the author can act on. That makes the diagnosis itself the
thing under test, not just the manuscript — and the sharpest rule here is the one that
protects the author from a plausible-sounding invention:

> **every finding must quote text that exists in the manuscript**

| scoring point | rule |
|-|-|
| a complete diagnosis, not a style opinion | `struct.dimension_missing`, `struct.style_as_defect` |
| judgements matching the actual text | `struct.evidence_not_in_text`, `struct.finding_no_evidence` |
| suggestions the author can execute | `struct.suggestion_missing`, `struct.suggestion_no_action`, `struct.suggestion_not_executable` |
| every judgement locatable | `struct.finding_no_locator`, `struct.finding_locator_vague` |
| cross-section consistency | `struct.promise_not_delivered`, `struct.abstract_overclaim`, `struct.abstract_conclusion_mismatch` |
| the six dimensions covered | `struct.dimension_missing` |

## The seven failures this exists to catch

**A fabricated defect.** "The abstract contradicts the results table" — with no such text in
the paper. The quote is matched literally against the manuscript, so an invented finding is
reported rather than rewarded.

**A style preference dressed as structure.** Labelling a finding as a style preference is
refused; taste is not a structural defect and mixing them is how a diagnosis loses its
authority.

**A dimension quietly skipped.** Six dimensions are required. A gap is only acceptable if it
is the paper's least important problem, which is the author's call to make with the gap
visible.

**A claim supported by another claim.** A→B and B→A is a cycle: the argument rests on itself.
Also caught: support weaker than the claim it is asked to carry.

**A finding with no suggestion.** A substantial finding without an action is an observation,
not a revision plan. Round two adds the sharper half: an action with no edit verb
("this should be improved") still leaves the author to invent the edit, so it is reported
too.

**A promise the paper never keeps.** The introduction promises an analysis; the deliverable
sections never mention it. The promise and the deliverable text are checked against each
other, and a promise none of whose content words reappears is reported.

**A front door that disagrees with the back door.** The abstract is where an overclaim does
the most damage: causal wording for an observational design in the abstract is refused, and
an abstract that shares no content with the conclusion is reported as a mismatch.

## 主入口：全文主张—证据—推理链审查

运行时输入为 `/input/case.json` 与 `task.md`。先读实际全文；扫描 PDF 用平台 OCR/PDF 工具求真文本，
不能根据领域标签编造一篇论文，也不能只写六个占位 diagnosis 就声称完成。

```bash
python scripts/logiccheck.py --case /input/case.json --out /app/output
# PDF/OCR 后：
python scripts/logiccheck.py --case /input/case.json \
  --material /app/work/manuscript.txt --out /app/output
```

引擎参照开源 argdown/argdown 的主张、前提、支持/反驳关系组织结果，但不假装词汇对齐等于逻辑
蕴含。`argument_map[]` 每条含 claim id、原句与页/段/句定位、作者设计、claim strength、限定语、
结果证据及 locator、warrant 状态和替代解释检查。`reasoning_gaps` 是实际逻辑发现；
`cross_section_checks` 保存承诺—交付与矛盾两侧证据。

退出码为 0 clean、3 review/partial、4 blocked（有 high）、5 undetermined。每个非命令行用法错误
路径都写 `result.json`、`audit_report.md`、`run_log.json`，无 traceback。先核对原句，再把修改建议
交给作者；不得把"证据尚未链接"升级成"结论已被证伪"。

### 实际规则、严重度与修改方式

| rule | 触发边界 | 可执行修改 |
|-|-|-|
| `logic.causal_overreach` | 方法证据为观察/相关设计，作者在摘要/讨论/结论使用无限定因果词；转述、假设和 hedged association 不触发 | 把因果动词改为 association，保留人群/时间窗，或补真正的因果设计 |
| `logic.non_significant_result_claimed_as_effect` | 链接的结果明确 non-significant，却被写成效应 | 对齐显著性、效应方向与结果，给双侧位置 |
| `logic.species_or_population_extrapolation` | 非人体方法/证据被直接外推到人一样确定结论 | 限定到 measured species/cohort，补人体验证 |
| `logic.sample_scope_extrapolation` | 单中心/有限样本等却写 universal/all/widely applicable | 限定样本与外推范围，补外部验证 |
| `logic.evidence_link_missing` | 强结论无结果句、图表指针或引文，且 lexical evidence 也不存在 | 添加能蕴含该子结论的结果/表图与不确定性，或删降该句；不等于结论为假 |
| `logic.alternative_explanations_not_addressed` | 观察设计却断言机制/因果链，全文没有 limitation/confound/alternative | 明确讨论混杂、反向因果、测量偏倚及各自能否排除 |
| `logic.boundary_conditions_missing` | 绝对/强结论没有任何边界条件 | 加群体、时间窗、测量与适用限制 |
| `logic.promise_not_delivered` | 引言 aim/compare/evaluate 的内容在方法/结果/讨论无最低文本对应 | 补具名分析及结果定位，或一致删除承诺 |
| `logic.cross_section_contradiction` | 高度对齐的摘要/正文出现不同效应值、相反方向或非显著口径；共享对照值不妨碍识别另一值变化 | 给两侧原句，回到底表判断哪侧错误并记录修正 |
| `logic.case_unreadable` / `logic.case_not_object` / `logic.no_manuscript` / `logic.internal_error` / `logic.runner_error` | 案例无法运行，不猜科学问题 | structured undetermined；明确缺什么及如何重跑 |

### 误报抑制与范围

- 明确标注的研究假设、`may/might/suggest/associated with/consistent with/limited to`、
  `according to` / `Smith et al.` 的他人观点都不是作者的过强结论，可保留在 map 但不触发。
- `et al.` 不作为句号切开，意图性随机对照/实验设计不会被观察性因果规则误报；设计未知时只记
  pending，不假定观察性。
- 结果链接是**待复核支持候选**，不是自动蕴含证明。每侧原文、定位、claim coverage 和 warrant
  均公开，供复核人接受或否定。
- 只有短节选、无结果或无讨论/结论时在 uncertainty 明写，不宣称完成全文审查。统计复算、原始
  数据验证、他人来源事实真伪属于 `not_checked`。

### 输出与严格契约

`audit_report[]` 每条包含 rule、category、kind、severity、severity_basis、location、excerpt、verdict、
basis、fix，适用时带 `evidence_quote / evidence_locator / replacement_text`。另输出
`argument_map`、`reasoning_gaps`、`promise_checks`、`contradiction_checks`、`evidence_bounds`、
`result_state`、`sources`、`checked`、`severity_counts`、`uncertainty` 和 `change_records`。

原始 `case_id` 位于顶层；`output_contract` 每个字段原名保留，优先级严格为
**引擎值 > case 显式值 > null + limits**。支持字符串/dict/field/name/key 对象；`审查报告 /
依据与边界 / 结果状态` 原名直通实际三段。structured refusal 同样执行。离线同案重跑三个工件
逐字节一致，无时间戳。

`examples/case.json` 为合成完整试验稿（非正式答案），clean 基线要求 0 finding、exit 0。

```bash
python scripts/bench_logic_case.py   # 17 个功能/误报/跨章节场景
python scripts/probe_logic_case.py   # 14 个敌意、契约、拒绝、冷导入与幂等探针
```

引擎只用 Python 标准库；`review_common.py` 在 review 新家族三包中保持字节一致，共享修改必须
同步并回归。

---

## Legacy structured-spec 路由（可选补充）

| 任务措辞信号 | 路由 |
|-|-|
| 结构审查 / 逻辑诊断 / 论证审查 / revision plan | 走六步全流程（0–6），六维度全部覆盖 |
| 逐条问题 + 位置 + 严重度 + 建议 | findings 逐条带 locator 与逐字 evidence；major 及以上必须挂建议 |
| 主张-证据对齐 / claim-evidence audit | 抽取 claims 与 support 指针，走 claim_without_support、circular_support、support_weaker_than_claim |
| 因果表述审查 / causal overreach | 摘要、结论两处分别核查（design 与措辞口径） |
| 摘要与正文一致性 | abstract 与 conclusion 重叠核查 + 摘要过度声明 |
| 引言承诺核查 / 前后呼应 | promises 与 delivery_text 核查（promise_not_delivered） |
| 段落级诊断 / 段落功能 | paragraphs 带 claims 与 strength，走 multiple_claims、orphan_paragraph、duplicate_paragraph |
| 润色 / 语言表达优化 | 不在本包范围：风格偏好被拒绝冒充缺陷；明确声明该部分未覆盖 |
| 查重 / 学术不端判定 / 参考文献格式 | 超出边界，声明未检查，不凭空补结论 |
| 原始数据重分析 / 统计复算 | 超出边界：本包只审主张与证据的对应，不算数 |
| 扫描版 PDF / 无文本层 | 解析失败如实进入待复核与 limits，不得宣称完成全文审查 |

## Workflow

### 1. Write the diagnosis, not the essay

``json
{
  "section": "structure_logic",
  "case_id": "demo-structure-001",
  "output_contract": ["status", "findings", "severity_counts", "checked", "limits"],
  "manuscript_text": "1 Introduction\nUptake is limited by surface area. ...\n",
  "research_question": "whether a porous coating raises uptake",
  "design": "experimental",
  "abstract": "Uptake rose three-fold with a porous coating, consistent with a surface-area mechanism.",
  "conclusion": "The effect is consistent with a surface-area mechanism.",
  "limitations": "single material, one coating thickness",
  "promises": [{"statement": "we measure uptake under the coating", "locator": "1 Introduction"}],
  "delivery_text": "We coated samples and measured uptake. Uptake rose three-fold.",
  "contributions": [{"claim": "a porous coating raises uptake", "anchor": "3 Results"}],
  "paragraphs": [
    {"id": "p1", "section": "Introduction", "text": "Uptake is limited by surface area",
     "claims": [{"claim": "uptake is limited by surface area", "support": "[doe2020]",
                 "strength": "moderate", "support_strength": "moderate"}]}
  ],
  "diagnosis": [
    {"id": "RES", "dimension": "research_question", "finding": "question stated late",
     "evidence": "We ask whether a porous coating raises uptake",
     "locator": "1 Introduction", "severity": "minor"}
  ],
  "suggestions": [
    {"for_finding": "RES", "action": "move the question sentence to the opening paragraph"}
  ]
}
``

dimension 取六个之一：research_question、section_structure、argument_chain、
paragraph_relation、duplication、conclusion_scope。evidence 必须是 manuscript_text 的
逐字子串。severity 用 major、medium、minor 区分轻重——全部标同一档会让评审无法判断
先改哪里；major 与 medium 的发现必须挂 suggestion。suggestion 的 action 必须含编辑动词
（move、merge、split、cut、add、删除、合并、改写……），"这里读起来怪"不是建议。

作者有意设置的对照组、明确标注的假设情形、转述他人观点，不是缺陷：它们不进 diagnosis，
或以 minor 级注明"为作者有意设置，无需修改"。误报这类条目比漏报更伤诊断的权威性。

### 2. Run it

``bash
python scripts/secrun.py --spec spec.json --section structure_logic --out /app/output
``

退出码：0 clean、3 review（只有 low/medium）、4 blocked（有 high）、5 undetermined
（spec 不可读、非对象或未声明 section——写 result.json，绝不 traceback）。

## 规则

### The diagnosis

| rule | severity | what it proves |
|-|-|-|
| `struct.no_manuscript` | high | nothing to diagnose |
| `struct.no_diagnosis` | high | the deliverable is absent |
| `struct.dimension_missing` | high | a required dimension is not diagnosed |
| `struct.dimension_unknown` | low | a dimension outside the six |
| `struct.finding_no_evidence` | high | a finding quotes nothing |
| `struct.evidence_not_in_text` | high | **the quoted defect does not exist in the paper** |
| `struct.finding_no_locator` | high | the author cannot go and look |
| `struct.finding_locator_vague` | low | the locator names the paper as a whole, not a place in it |
| `struct.style_as_defect` | high | a preference reported as structure |
| `struct.suggestion_missing` | high | a substantial finding with no action |
| `struct.suggestion_no_action` | high | a suggestion with an empty action |
| `struct.suggestion_not_executable` | medium | an action with no edit verb — still an observation |
| `struct.suggestion_orphaned` | medium | a suggestion for a finding that does not exist |

### Question, promises, contributions, conclusion

| rule | severity | what it proves |
|-|-|-|
| `struct.research_question_missing` | high | no question, so structure has no target |
| `struct.question_absent_from_text` | high | the question shares no wording with the paper |
| `struct.promise_not_delivered` | high | an introduction promise no deliverable section mentions |
| `struct.contribution_unanchored` | high | a contribution not tied to a section |
| `struct.contribution_anchor_unknown` | medium | an anchor the manuscript lacks |
| `struct.conclusion_exceeds_scope` | high | causal wording for an observational design (conclusion) |
| `struct.abstract_overclaim` | high | causal wording for an observational design (abstract) |
| `struct.abstract_conclusion_mismatch` | medium | abstract and conclusion share no content |
| `struct.limitations_missing` | medium | a boundary claim with no limitation stated |

### Paragraphs and argument

| rule | severity | what it proves |
|-|-|-|
| `struct.multiple_claims` | medium | a paragraph argues two things |
| `struct.orphan_paragraph` | medium | a paragraph claims nothing |
| `struct.claim_without_support` | high | a claim with no pointer |
| `struct.circular_support` | high | A supports B and B supports A |
| `struct.support_weaker_than_claim` | high | the evidence cannot carry the claim |
| `struct.duplicate_paragraph` | medium | two paragraphs say the same thing |
| `struct.section_interleaved` | medium | a section resumes after another intervenes |

## 输出契约

/app/output/result.json 必须按以下优先级合并：

1. **平台契约字段，逐字**：case.json 的 output_contract 点名的每个字段——引擎已推导的
   保留原值，spec 携带的直通拷贝（大体积输入除外），推导不了的填 null 并在 limits 记一条
   说明；case_id 置于顶层。
2. 引擎字段：status、section、findings[]（每条带 finding id、所依托的原句或段落及计数）、
   severity_counts、checked（本例实际查了什么：维度覆盖清单、promises 数、条目数）、
   limits。spec 不可读时的 undetermined 路径不回填契约字段——没有可信来源可回填，如实声明。
3. 任务要求的三段审查结果，从引擎输出映射：

| rubric 行 | rubric 要求要点 | result.json 落位 |
|-|-|-|
| 审查报告 | 逐条问题、位置、严重度和修改建议；覆盖题目要求的检查项 | findings[]：位置（locator + 逐字 evidence）、类型（rule id）、严重度（major/medium/minor→high/medium/low）、修改建议（suggestions，必须含编辑动词）；覆盖六个维度 + 承诺-交付 + 摘要-结论 |
| 依据与边界 | 稿件原文、引用/数据/方法证据及待复核项；区分错误、证据不足和建议 | evidence 与稿件逐字子串匹配，high=错误、medium/low=证据不足或边界；无法确认的条目进 pending_confirmation（spec 顶层直通），转述引用会被拒绝而不是被奖励 |
| 结果状态 | 通过、问题、待复核和未检查项；不凭空补齐缺失信息 | status（clean/review/blocked/undetermined）、checked（六维度逐维覆盖清单）、limits[]（未检查项）、gaps[]（案例未提供的材料，spec 顶层直通） |

Refusal discipline：spec 不是可读 JSON、不是对象、未声明 section 或 section 不在清单里
→ result.json 带 `audit.no_section`，退出码 5；列表里的坏条目（字符串冒充对象）安全降级
为跳过，绝不 traceback。

## Limits

- **Evidence matching is a substring test.** A finding that quotes a *paraphrase* of the
  manuscript will be reported as fabricated. Quote the text as it appears.
- **Dimension coverage is counted, not judged.** The audit cannot tell whether the diagnosed
  gap is the paper's most important problem.
- **Duplication is lexical overlap above 0.75.** Two paragraphs making the same point in
  different words can pass.
- **Circularity is detected within the supplied outline**, one pass, so a cycle whose first
  link appears after its second may be missed.
- **Causal wording is a word list.** Careful phrasing can slip through.
- **Promise delivery is word-level.** A promise whose content words are all paraphrased
  away reads as delivered; the check catches dropped promises, not rewritten ones.
- **Abstract-conclusion agreement is an overlap floor (0.2).** Two passages can share
  vocabulary yet disagree in substance; the check catches drift, not subtle contradiction.
- **Degree of "style" is not modelled.** The refusal covers findings explicitly labelled
  style; a stylistic objection labelled minor passes.
- **The engine reads the spec you build, not the PDF itself.** 抽稿件的忠实度由第 3 步的
  逐字摘录纪律保证；PDF 解析失败时如实进入待复核。

## 异常处置表

| 症状 | 引擎行为 | 处置 |
|-|-|-|
| spec 不是可读 JSON | undetermined，finding `audit.no_section`，exit 5 | 重新导出 spec；检查是否被截断或编码损坏 |
| spec 是列表/字符串而非对象 | undetermined，`audit.no_section`，exit 5 | spec 顶层必须是对象 |
| 未声明 section 或 section 未知 | undetermined，`audit.no_section`，exit 5 | 用 --section structure_logic 或在 spec 里声明 section |
| 发现引用的句子稿件里没有 | high，`struct.evidence_not_in_text` | 逐字重抄原句，或删掉该发现——不猜"大概是这句" |
| 发现没有任何引用 | high，`struct.finding_no_evidence` | 回原文找句子；找不到就标记待复核 |
| 只给了章节名级定位 | low，`struct.finding_locator_vague` | 补到段落/句子级（页码、节号、段落 id） |
| 大发现没有建议 | high，`struct.suggestion_missing` | 补可执行建议（move/merge/split/cut/add） |
| 建议没有编辑动词 | medium，`struct.suggestion_not_executable` | 把意见改写成具体编辑动作 |
| 摘要用了因果措辞而设计是观察性 | high，`struct.abstract_overclaim` | 降口径为 association，或改述设计依据 |
| 摘要与结论几乎不重叠 | medium，`struct.abstract_conclusion_mismatch` | 对齐两者，或在 limits 里说明差异原因 |
| 引言承诺未兑现 | high，`struct.promise_not_delivered` | 在结果/讨论中交付该分析，或删掉承诺并说明 |
| 六维度缺一个 | high，`struct.dimension_missing` | 补诊断，或声明该维度对本文不适用及原因 |
| 段落引用成环 | high，`struct.circular_support` | 打破环路：其中一条主张需要外部证据 |
| 证据强度低于主张强度 | high，`struct.support_weaker_than_claim` | 弱化主张或加强证据 |
| 风格偏好标成了缺陷 | high，`struct.style_as_defect` | 重新归类为风格意见，或找到其结构后果 |
| PDF 解析失败 / 扫描版无文本 | 不进引擎；稿件快照为空时引擎报 no_manuscript | 在 limits 与待复核里声明"全文审查未完成"，不得宣称完成 |
| 稿件超长（预算内读不完） | 分段抽取；未覆盖段落记入 limits | 分段处理并显式记录每段状态，不静默截断 |
| 列表条目是字符串而非对象 | 安全跳过（degrade），不崩溃 | 修 spec 该条目的结构后重跑 |
| output_contract 字段推导不了 | 该键填 null，limits 记一条 | 在三段结果的"结果状态"里向读者说明缺失原因 |
| output_contract 本身是垃圾类型 | 不崩溃，limits 记一条说明 | 修 case.json 引用方式；契约清单须为字符串列表 |

## 最小调用示例

输入：examples/spec.json（含 case_id 与 output_contract 声明）。

调用：

``bash
python scripts/secrun.py --spec examples/spec.json --section structure_logic --out out_example
``

实跑退出码 0；完整示意输出见 examples/example-result.json（由上述 spec 实跑生成、标注为
示例）。形状如下：

``json
{
  "schema_version": "secrun/v1",
  "section": "structure_logic",
  "status": "clean",
  "case_id": "demo-structure-001",
  "findings": [],
  "severity_counts": {},
  "checked": {"section": "structure_logic", "items": 3,
              "dimensions_covered": ["argument_chain", "conclusion_scope", "duplication",
                                     "paragraph_relation", "research_question",
                                     "section_structure"],
              "promises_declared": 0},
  "limits": []
}
``

（示意输出——说明接口与结果形状，不是正式案例结果；output_contract 点名的五个键全部
在结果中出现，case_id 在顶层。）

## Verification

``bash
python scripts/bench_structure.py  # 28 scenarios: one per rule, clean baseline silent
python scripts/bench_sections.py   # 51 scenarios: cross-section regression plus false-positive guards
``

两者在本机全部通过（28/28、51/51）。每个 bench 的 clean 基线必须零发现，FP guard 钉住
标准科研散文不误报（表指针、统计表达式、数据指涉句不触发引用要求）。另有 15 项敌意探针
（坏 JSON、非对象、未知 section、文件缺失、类型错位、契约垃圾类型、超长、CJK、重跑幂等）
全部通过：退出码落在 0/3/4/5，result.json 必在，无 traceback。

## Requirements

Python 3.9+（3.14 实测）。纯标准库实现，无第三方依赖；全部脚本可独立导入。

## 创新增益

本包相对通用 Agent 的新增能力（边界与证据形式一并写明，全部为引擎真实实现）：

1. **伪造缺陷拦截**：每条诊断必须逐字引用稿件中存在的句子（`struct.evidence_not_in_text` /
   `struct.finding_no_evidence`），"看起来像模像样"的虚构问题被点名而不是被奖励。
   边界：字面子串匹配，转述引用会被报为伪造——这是刻意的保守。证据：bench_structure
   evidence_fabricated 场景。
2. **六维度强制覆盖 + 覆盖清单回执**：研究问题、章节结构、论证链、段落关系、重复、结论
   范围逐维清点（`struct.dimension_missing`），result.json 的 checked 里回执 dimensions_covered
   清单——评审不需要重新数。边界：只清点覆盖，不判断缺口是否该容忍。
3. **承诺-交付核查**：引言承诺与交付章节文本逐词核对（`struct.promise_not_delivered`），
   直击"引言承诺要分析的问题在结果章节没有交付"这一跨章节断裂。边界：词级匹配，全部
   改写的承诺读作已交付。证据：bench_structure promise_not_delivered 场景。
4. **摘要-结论口径核查**：摘要因果措辞与设计不匹配被点名（`struct.abstract_overclaim`），
   摘要与结论零重叠被点名（`struct.abstract_conclusion_mismatch`）——评审最先读到的
   过度声明不再漏检。边界：重叠下限 0.2，词汇共享但实质矛盾的表述可能滑过。证据：
   bench_structure abstract_overclaim / abstract_conclusion_mismatch 场景。
5. **可执行建议的动词门槛**：空建议（`struct.suggestion_no_action`）与"有话但没动作"
   （`struct.suggestion_not_executable`）分别报——评审拿到的每条建议都能直接落到句子。
   边界：动词词表覆盖中英文常用编辑动词，生僻表述可能误过。
6. **循环支持链检测**：A→B→A 的论证环与弱证据扛强主张都被报（`struct.circular_support` /
   `struct.support_weaker_than_claim`）。边界：单遍扫描，环的首尾跨扫描顺序时可能漏。
   证据：bench_structure circular_support / support_weaker_than_claim 场景。

## 生态贡献

- **SKILL.md**：用途、适用条件、六步调用方式、输入输出、异常处置表（20 行）、限制和自查方法
- **scripts/sections.py**：structure_logic 全部规则独立成函数，其余十三节规则同库可查，
  纯标准库可独立导入；规则库随 spec 字段扩展
- **scripts/secrun.py**：通用 CLI——任何一节的 spec 都能跑，契约回填与 undetermined
  处理可直接复用
- **scripts/guard.py / units.py / redline.py**：句子切分、量值抽取、术语与措辞强度度量，
  三个模块可在任何稿件审查项目里独立复用
- **examples/**：最小调用示例三件套（spec 含 case_id 与 output_contract、实跑 result、
  bench 报告样张，示意输出已标注）
- **scripts/bench_structure.py**：28 场景逐条对应规则，一键复跑
- **scripts/bench_sections.py**：51 场景跨节回归 + FP guard，一键复跑
- **维护信息**：依赖声明（纯标准库）、平台限制（50 文件/500KB/2MB 内无二进制）、已知边界
  全部写入 Limits 与异常处置表
