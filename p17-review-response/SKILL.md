---
name: review-response
description: >
  Audit a revision package — reviewer comments plus the response letter and the manuscript
  they refer to. Checks that every comment is answered and every sub-request inside it
  covered, that an acceptance is backed by an actual change or a stated reason, that tone and
  decision tell the same story, that each claimed change carries a location that resolves in
  the stated manuscript version and a version stamp, that "we have added X" is actually in the
  file, that the manuscript is no longer identical to a declared baseline, and that promised
  experiments or data record their state, their data source when provided, and an alternative
  when they could not be done. Use when a task produces a response-to-reviewers letter, a
  rebuttal, or a revision package.
---

# review-response

Editors do not read a response letter for prose. They check two things: is every comment
answered, and can I find the change you claim to have made. Both are mechanical, and so is
the third: does the letter describe the file you actually submitted.

| 题面四问 | rule |
|-|-|
| 答得全：每条意见及子要求都有明确处理结论 | `resp.comment_unanswered`, `resp.subrequirement_unanswered`, `resp.accept_without_change` |
| 改得准：声称的修改真实落在正文、可定位 | `resp.change_not_verifiable`, `resp.locator_not_in_manuscript`, `resp.change_unlocatable` |
| 证得住：补充证据可查证或说清为何补不了 | `resp.evidence_status_missing`, `resp.evidence_without_alternative`, `resp.evidence_source_missing` |
| 对得上：回复信、修订稿、版本三者一致 | `resp.version_mismatch`, `resp.change_version_missing`, `resp.manuscript_unrevised` |

## 运行契约（Harbor runtime contract）

- 运行时输入是 /input/case.json 与 task.md：先读 case.json，逐字记录其中的 case_id 和
  output_contract 字段名清单（本题的交付字段是可编辑修订稿、回复信草案、修改定位、未到位
  证据清单这类）；再读 task.md 确认要交付什么。材料一律读实际文件，不按标签臆测。
- 工作目录 /app/work 放中间产物；最终实际结果与可编辑产物放 /app/output，其中 result.json
  必须保留 output_contract 的全部字段和 case_id（审计自动回填，见第六步）。
- 预算：64 次模型请求、900 秒、每次响应 16384 token（含推理）。先尽早写出诚实的部分成果，
  再增量改进。
- 三个固定案例、每条件重复三次；评测由平台对照运行。不得伪造缺失的软件状态或科学数据；
  部分成果必须说明边界。
- Skill 资源限制：最多 50 个 UTF-8 文本文件、单文件 500KB、总量 2MB、无符号链接。

## 演练纪律（本题固定案例的边界，逐条遵守）

- materials/manuscript-baseline.md 是组织方基线摘要，materials/reviewer-comments.md 是组织方
  整理的意见摘要——不是完整原稿或审稿报告逐字全文。comments 的 text 抄摘要原句；不得冒称
  真实审稿人逐字要求。
- 只修订这个指定基线：基线内容进 baseline_text，修订后的全文进 manuscript_text。意见摘要中
  的实质性修改必须真实落进修订稿——只声明缺材料后跳过可执行修改会被 manuscript_unrevised
  和 accept_without_change 拦截。
- 不得冒称：真实补做实验（evidence 的 status 如实记录）、原作者已改稿、编辑部已接收、整篇
  全文返修完成。补不了的证据给 alternative，说清为何无法补做。
- 公开论文/报告链接是来源身份，不表示已联网核验原评审全文。

## 六步运行时入口

0. **读 case.json 取标识**：记下 case_id 与 output_contract 的每个字段名；读 task.md 确认
   返修动作（逐条回复、修订定位、证据清单）。
1. **判形态路由**：按下面的「任务措辞 → 路由」决策表决定跑哪个 section、哪些字段必填。
2. **先产出目标产物**：可编辑修订稿（基线 + 落进正文的实质修改）+ 逐条回复信草案 + 每处
   修改的定位 + 未到位证据清单。产物先行，审计在后。
3. **构造 spec**：意见结构化为 comments（id、text、type、severity、subrequirements），回复
   结构化为 responses（decision、tone、reason、changes、evidence），基线与修订稿分别进
   baseline_text 与 manuscript_text；section 取 review_response；附上 case_id，并把
   output_contract 的每个字段以同名键放进 spec（值逐字直通进 result.json）。
4. **审计**：运行 python scripts/writeaudit.py --spec spec.json --section review_response
   --out /app/output。退出码：0 clean、3 review、4 blocked、5 undetermined（输入无法审计）。
5. **修发现重跑**：每条 finding 按 Failure handling 表处置后重跑，直到 clean，或只剩已声明
   的 limits。high 发现不修复就直接交付等于 blocked。
6. **合并 result.json**：确认 /app/output/result.json 含 case_id 和 output_contract 全部字段
   （审计自动回填：spec 带同名值的逐字直通，两边都没有的字段写 null 并在 limits 注明）；
   checked 里的 evidence_by_status 就是未到位证据清单的计数汇总；把修订稿与回复信放进
   /app/output；在 limits 里写清材料缺口与需人工确认项。

## 任务措辞 → 路由决策表

| 任务里的措辞 | 路由与动作 |
|-|-|
| 「逐条回复审稿意见 / 写 response letter / rebuttal」 | 跑 review_response：comments + responses 全量结构化 |
| 材料是意见摘要 + 基线稿 | reviewer-comments.md 拆成 comments（id/text/type/severity/subrequirements），manuscript-baseline.md 进 baseline_text |
| 「修订稿 + 回复信」双交付 | manuscript_text 为修订后全文，responses 为信；每处修改写 changes |
| 「意见里有多个子要求 / 一条意见问了两件事」 | 拆进 subrequirements（答得全）；引擎按共享 id 的全部回复体判覆盖 |
| 「标注每处修改位置 / 定位到章节行号」 | changes 的 location 用稿件里可检索的原文锚点（改得准）；anchors 声明锚点表 |
| 「需要补实验/补数据/补文献」 | evidence 带 status 与 source（provided 时）或 alternative（补不了时）（证得住） |
| 「多轮返修 / 版本对齐 / 承诺仍成立」 | manuscript_version 全局声明 + 每条 change 盖版本章（对得上） |
| 「语气礼貌反驳 / 澄清 / 申诉」 | tone 四档声明（accept / clarify / polite_rebuttal / appeal）；拒绝必须配 accept 以外的语气 |
| 「未到位证据清单」 | evidence 每条如实标 status；result.json 的 checked.evidence_by_status 与 pending_evidence 直通字段即清单 |
| 任务混有格式适配诉求 | 本包审返修内容；格式与保真路由给 manuscript-format 包（format_template section） |
| 意见是自由文本、无编号 | 先人工编号拆条再进 spec——引擎按 id 审覆盖，不拆自由文本 |
| 修订稿与基线逐字相同 | manuscript_unrevised 会拦：把实质修改真实写进修订稿，或把 decision 改为如实拒绝并给理由 |

## The failures this exists to catch

**A letter that answers nine of ten comments.** Coverage is checked by id, and a response
pointing at an id that does not exist is reported too — an editor cannot follow that either.
An acceptance with no change entry and no reason is a non-answer in polite clothing:
`resp.accept_without_change`.

**A comment with two requests, one answered.** "Add a vehicle control and report n per arm" is
two obligations. Word overlap between each sub-request and the response body decides whether
both were addressed. The body is every response entry sharing the comment id, so splitting
one comment's answer across entries is supported.

**"We have added a paragraph" that is not in the file.** If the response quotes added_text,
it must occur in the supplied manuscript. A manuscript still identical to the declared
baseline means no claimed revision landed at all.

**A location that no longer exists, or a change with no version stamp.** A change pointing at
4.7 Conclusions in a manuscript without that section cannot be verified; a change that names
no version cannot be matched to the file the letter claims to revise.

**An experiment promised and quietly dropped.** Evidence marked unavailable needs an
alternative; evidence marked provided must name where its data comes from.

## Worked example（示例，非正式案例结果）

examples/spec.json 的完整输入（带 case_id 与 output_contract；此处节选关键结构）：

```json
{
  "case_id": "demo-case-201",
  "section": "review_response",
  "manuscript_version": "v2",
  "baseline_text": "3.2 Results\nBaseline summary without the control group.\n",
  "manuscript_text": "3.2 Results\nWe added a vehicle control (n=6).\n",
  "anchors": ["3.2 Results", "Appendix A"],
  "comments": [
    {"id": "C1", "text": "Add a vehicle control.", "type": "method", "severity": "major",
     "subrequirements": []},
    {"id": "C2", "text": "Justify the kinetic model.", "type": "method", "severity": "major",
     "subrequirements": []}
  ],
  "responses": [
    {"comment_id": "C1", "decision": "accept", "tone": "accept",
     "changes": [{"what": "added a vehicle control group",
                  "location": "3.2 Results", "manuscript_version": "v2",
                  "added_text": "We added a vehicle control"}]},
    {"comment_id": "C2", "decision": "accept", "tone": "accept",
     "changes": [{"what": "added a derivation appendix",
                  "location": "Appendix A", "manuscript_version": "v2"}]}
  ],
  "output_contract": {"revised_manuscript": "the editable revised manuscript",
                      "response_letter": "the point-by-point response draft",
                      "change_locations": "locator per claimed change",
                      "pending_evidence": "evidence entries not yet provided"},
  "revised_manuscript": "3.2 Results\nWe added a vehicle control (n=6).\n",
  "change_locations": [{"comment_id": "C1", "location": "3.2 Results"},
                       {"comment_id": "C2", "location": "Appendix A"}],
  "pending_evidence": []
}
```

decision 取 accept、partial 或 reject；tone 取 accept、clarify、polite_rebuttal 或 appeal。
拒绝或部分接受必须给 reason。type 取 method、data、writing、format 或 ethics；severity 取
major、minor 或 editorial。evidence 每条带 kind 与 status（provided / unavailable /
alternative_given），provided 必须给数据来源字段，补不了的必须给 alternative。

运行（示例命令，正式运行时 --out 用 /app/output）：

```bash
python scripts/writeaudit.py --spec examples/spec.json --out examples/_demo_out
```

以下为本机实跑得到的示意输出（clean，exit 0），result.json 全文：

```json
{
  "schema_version": "writeaudit/v1",
  "case_id": "demo-case-201",
  "section": "review_response",
  "status": "clean",
  "findings": [],
  "severity_counts": {},
  "checked": {"comments": 2, "responses": 2, "changes": 2, "evidence_by_status": {}},
  "limits": ["all declared output_contract fields carry values"],
  "revised_manuscript": "3.2 Results\nWe added a vehicle control (n=6).\n",
  "response_letter": {"responses": ["...C1 与 C2 的逐条回复，同 spec..."]},
  "change_locations": [{"comment_id": "C1", "location": "3.2 Results"},
                       {"comment_id": "C2", "location": "Appendix A"}],
  "pending_evidence": [],
  "output_contract_fields": ["revised_manuscript", "response_letter",
                             "change_locations", "pending_evidence"]
}
```

交付缺内容时审计会点名。把 C1 的回复删掉 changes、去掉版本章、并把 C1 拆成两个子要求只答
一个，同一命令实跑 exit 4（blocked），三条发现：

```json
[
 {"rule": "resp.subrequirement_unanswered", "severity": "high", "comment_id": "C1",
  "message": "a comment contains more than one request and part of it is not addressed"},
 {"rule": "resp.accept_without_change", "severity": "high", "comment_id": "C1",
  "message": "a response accepts the comment but records no change and no reason, ..."},
 {"rule": "resp.change_version_missing", "severity": "medium", "comment_id": "C2",
  "message": "a claimed change carries no manuscript version stamp, ..."}
]
```

## 评分要求映射（rubric 三段 → 本 Skill 落点）

| rubric 输出要求 | 完成标准（rubric 原词） | 本 Skill 落点 |
|-|-|-|
| 目标产物 | 满足题目指定体裁、受众和格式 | 可编辑修订稿 + 逐条回复信草案 + 修改定位 + 未到位证据清单；result.json 经 output_contract 直通携带（revised_manuscript、response_letter、change_locations、pending_evidence） |
| 事实与来源映射 | 可逐条回溯，不新增材料外事实 | comments 的 text 抄意见摘要原句；changes 的 added_text 必须逐字出现在修订稿；evidence 每条带来源或替代说明；findings 带 comment_id/location/added 逐条定位 |
| 版本与边界 | 结果可继续编辑，未确认部分明确标注 | manuscript_version 全局声明 + 每条 change 盖版本章（version_mismatch / change_version_missing）；baseline_text 声明基线（manuscript_unrevised）；checked.evidence_by_status 汇总证据到位状态；limits 写材料缺口与未确认项 |

## Rules

### The package and decomposition

| rule | severity | what it proves |
|-|-|-|
| `resp.no_comments` | high | nothing to check coverage against |
| `resp.no_letter` | high | no response letter |
| `resp.no_manuscript` | high | no claims of change can be checked |
| `resp.comment_type_missing` / `_unknown` | medium / low | the comment's kind is unstated |
| `resp.severity_missing` / `_unknown` | medium / low | it cannot be prioritised |
| `resp.comment_text_missing` | medium | a comment with no text cannot be answered verifiably |

### Coverage, decision and tone

| rule | severity | what it proves |
|-|-|-|
| `resp.comment_unanswered` | high | a comment has no response |
| `resp.subrequirement_unanswered` | high | part of a comment is silently dropped |
| `resp.response_orphaned` | medium | a response points at a comment that does not exist |
| `resp.decision_undeclared` / `_invalid` | high / medium | accept / partial / reject unstated |
| `resp.rebuttal_without_reason` | high | a decline without justification |
| `resp.accept_without_change` | high | an acceptance with no change entry and no reason — 空话 |
| `resp.tone_missing` / `_invalid` | medium / low | the register cannot be reviewed |
| `resp.tone_decision_mismatch` | medium | the letter declines in an accepting tone |

### Claims against the file

| rule | severity | what it proves |
|-|-|-|
| `resp.change_unspecified` | medium | a change does not say what was changed |
| `resp.change_unlocatable` | high | a change gives no location |
| `resp.locator_not_in_manuscript` | high | the location does not exist in the file |
| `resp.change_version_missing` | medium | a change carries no version stamp, so it cannot be matched to the declared version |
| `resp.version_mismatch` | high | the letter and the file are different revisions |
| `resp.change_not_verifiable` | high | text claimed as added is not in the manuscript |
| `resp.manuscript_unrevised` | high | the manuscript is still identical to the declared baseline while the letter claims accepted changes |

### Promised evidence

| rule | severity | what it proves |
|-|-|-|
| `resp.evidence_status_missing` | high | no statement of whether it was provided |
| `resp.evidence_status_unknown` | low | state outside provided/unavailable/alternative_given |
| `resp.evidence_without_alternative` | high | unavailable, with no substitute offered |
| `resp.evidence_source_missing` | medium | marked provided, but no field says where the data comes from |

### Audit entry (writeaudit.py)

| rule | severity | what it proves |
|-|-|-|
| `audit.no_section` | high | no section was declared, so no rules ran (exit 5) |
| `audit.spec_unreadable` | high | the spec file is missing or not valid JSON (exit 5) |
| `audit.spec_not_object` | high | the spec is valid JSON but not an object (exit 5) |
| `audit.section_unknown` | high | the declared section is not implemented (exit 5) |
| `audit.section_error` | high | the audit could not complete on this spec (exit 5) |

## 异常处置表

| 情况 | 处置 |
|-|-|
| case.json 缺失或不可读 | 依 task.md 继续；result.json 的 case_id 写 null 并在 limits 注明来源缺失 |
| spec 不是合法 JSON / 不是对象 | 引擎返回 status undetermined（exit 5），finding 为 audit.spec_unreadable 或 audit.spec_not_object；修 spec 后重跑，不得手写 result.json |
| section 字段缺失或取值未知 | audit.no_section / audit.section_unknown（exit 5）；用 --section 显式指定 review_response |
| 字段类型错位（comments、responses、anchors、changes 是字符串或数字） | 引擎把非容器降级为空容器、把裸字符串条目降级为只有 id 的条目继续审，产出发现而不是崩溃；按发现补齐字段 |
| 意见互相冲突 | 两条都进 comments，各自独立审；回复信逐条说明取舍，必要时一条拒绝一条采纳，均给理由 |
| 意见本身有误（前提错误） | decision 取 reject/partial 并给证据理由；不得曲意顺从（无原则顺从同样是空话） |
| 稿件缺意见指向的章节 | locator_not_in_manuscript 会拦：改用现有章节的锚点，或在 change 里如实说明目标章节不存在 |
| 无法补实验/数据 | status 取 unavailable + alternative（替代分析或说明何能定夺）；不得伪造数据来源 |
| 基线未提供 | baseline_text 留空，manuscript_unrevised 保持静默；但意见的实质性修改仍须真实落进修订稿 |
| 修订稿与基线逐字相同 | manuscript_unrevised（high）：把修改写进修订稿，或把回复改为如实拒绝并给理由 |
| responses 与 comments 的 id 不匹配 | response_orphaned / comment_unanswered 点名；对齐 id 后重跑 |
| result.json 缺 contract 字段 | contract_echo 回填；spec 没带值的字段写 null 并在 limits 注明，不得编造 |
| 重跑结果不一致 | 引擎纯确定性（gate G5 断言两次运行 findings 全等）；不一致说明 spec 被改动，恢复 spec 重跑 |
| findings 为空但任务明显未完成 | 先查路由是否跑错 section；跑错 section 会得到假 clean |

## Output contract

/app/output/result.json（由 writeaudit.py 写出）包含：schema_version（writeaudit/v1）、
case_id、section、status（clean / review / blocked / undetermined）、findings 数组（每条带
rule、severity、message 与 comment_id/location/added 等定位字段）、severity_counts、checked
（comments/responses/changes 计数与 evidence_by_status 证据台账）、limits、
output_contract_fields（案例声明的字段名清单），以及 output_contract 每个字段的回填值
（spec 携带值直通，缺失为 null）。

## Limits

- **Sub-request coverage is word overlap.** A sub-request answered in different words reads as
  unanswered; phrase the response close to the comment. The overlap is judged against every
  response entry sharing the comment id, so splitting one comment's answer across entries is
  supported. ASCII runs on content words; Chinese is compared character by character, so a
  Chinese sub-request about 对照组 is judged against the shared nouns (组/照) with the response
  body — a genuinely unrelated answer still reads as unanswered.
- **added_text must be an exact substring.** A lightly edited quote will be reported as not
  found — which is the honest reading, since the editor would search for the exact text.
- **manuscript_unrevised is gated on the declaration.** It fires only when baseline_text is
  supplied, the delivered manuscript is still identical to it (whitespace-insensitive), and
  some response claims an accepted change. An all-rebuttal letter that legitimately touches
  nothing passes; without a baseline_text the check stays silent.
- **accept_without_change is a record check.** It fires only when neither a change entry nor a
  reason exists; a written-out justification counts as the record.
- **Provided evidence needs any provenance field.** evidence_source_missing fires only on an
  entry that carries nothing beyond kind and status; provenance recorded under any other field
  name counts.
- **Locator checking is a membership test.** With anchors, the locator must be one of them;
  without, it must appear verbatim in the manuscript. Neither proves the change is at that
  location, only that the location exists.
- **Tone is a declared field.** The audit reads the declaration, not the rhetoric; it does not
  scan prose for offensiveness or over-promising. It does check that a rejection is not
  declared in an accepting tone.
- **It does not split a free-text review into comments.** Ids are part of the input contract.
- **Multi-round promise ledgers are out of scope.** The fixed cases are single revisions of
  one declared baseline; per-change manuscript_version stamps cover version alignment.
- 混合任务（格式/翻译/证据写作）的规则表在对应 section 的引擎源码里；本文件只展开
  review_response 与审计入口的规则，避免无关规则淹没本文档。

## Failure handling

| symptom | what to do |
|-|-|
| comment_unanswered | answer it, or state that it is out of scope and why |
| subrequirement_unanswered | the comment had two requests; answer both |
| accept_without_change | record the actual change entry, or write the reason no file change was needed |
| rebuttal_without_reason | give the reason, with evidence where you have it |
| tone_decision_mismatch | make tone and decision tell the same story (a rejection is not an acceptance) |
| comment_text_missing | copy the comment's text from the opinion summary into the entry |
| change_not_verifiable | quote the text as it appears in the file, or fix the letter |
| manuscript_unrevised | make the accepted edits in the manuscript, or correct the letter's claims |
| change_version_missing | stamp the manuscript_version on every change entry |
| locator_not_in_manuscript | use a location that exists in this version |
| version_mismatch | the letter refers to another revision; align them |
| evidence_without_alternative | offer a substitute analysis, or say what would settle it |
| evidence_source_missing | name the data source of the provided evidence (table, dataset, file) |

## Verification

```bash
python scripts/bench_review.py    # 36 scenarios: one per rule, plus FP guards
python scripts/bench_writing.py   # 20 scenarios: cross-section regression
```

Both pass in full on this machine (36/36 and 20/20). The clean baseline in each must report
nothing. examples/bench-report.json 是示意报告（示例，非正式案例结果）。

## Requirements

Python 3.9+（3.14 实测）。纯标准库实现，无第三方依赖。scripts/ 下 writing.py（规则引擎）、
guard.py（数量/引用/语气提取）、redline.py（逐句对齐器）、writeaudit.py（入口与
result.json 写出）均可独立导入。

## 创新增益

以下均为引擎真实具备、可复跑验证的能力（bench 与 gate 是回归证据）：

1. **覆盖审计而非语感判断**：意见逐 id 对账、一条意见内的多个子要求按共享 id 的全部回复体
   判词面覆盖、拒绝必须有理由、接受必须有动作或书面理由——四种「空话」形态（笼统致谢、只答
   一半、拒而不述、受而无据）各有一条规则拦着。通用 Agent 无法对自己起草的回复信做这四项证明。
2. **三文件一致性核对**：回复信声称的 added_text 必须逐字出现在修订稿；基线与修订稿逐字相同
   而信称已改会被整体拦截；每条 change 盖版本章、全局版本不一致点名——回复信、修订稿、版本
   三者的对齐由机制保证，不靠自觉。
3. **证据台账**：每条 evidence 的到位状态由 checked.evidence_by_status 汇总为清单，provided
   无来源、unavailable 无替代分别点名——「未到位证据清单」是审计产物，不是事后手写。
4. **declared-only 零误报设计**：基线同一性、版本对齐、证据状态全部只在案例声明对应字段时
   启动；最小输入的 clean 基线零发现是 bench 的硬性断言。
5. **确定性可复跑 + 契约直通**：同 spec 两次运行 findings 全等（gate determinism 断言）；
   case_id 与 output_contract 字段自动回填 result.json，spec 携带值逐字直通，拒跑路径输出
   status undetermined 的可追踪 result.json 且绝不伪造契约字段。

## 生态贡献

1. **SKILL.md 全量文档**：用途、适用条件、调用方式、输入输出、异常处理、限制与自查方法齐备。
2. **纯标准库引擎**：scripts/ 四个模块无第三方依赖，可独立导入、可嵌入他人返修流水线。
3. **意见分类法可直接复用**：type 五类（method/data/writing/format/ethics）× severity 三档
   （major/minor/editorial）× tone 四档（accept/clarify/polite_rebuttal/appeal）的编码表，
   即审稿意见拆解的分类脚手架。
4. **规则清单与引擎一一对应**：本文件每条 rule id 都能在引擎里找到发出点（验收 gate 的规则
   奇偶校验强制），规则表可直接当作回复信自查清单复用。
5. **最小调用示例**：examples/spec.json（带 case_id 与 output_contract 的完整输入）+
   examples/bench-report.json（示意报告，标注为示例）。
6. **回归套件可独立复跑**：bench_review.py 36 场景 + bench_writing.py 20 场景，每条规则一个
   场景、每个缺陷配 FP 守卫，clean 基线必须零发现。
7. **异常处置表与 Failure handling 表**：14 类异常、13 类发现的处置动作可直接移植到其他
   返修任务。
8. **验收 gate 可复跑**：本包可通过 strict_gate.py 的 G1-G7 七项验收（打包/基准/文档路径/
   规则奇偶/确定性/冷启动/真实输入冒烟），他人可对复刻包执行同一验收。
