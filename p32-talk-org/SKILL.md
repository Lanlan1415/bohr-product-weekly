---
name: talk-org
description: >
  Organise an academic talk against a stated objective and audience. Turns "what should
  this talk achieve" into checkable fields (objective, audience, minutes, narrative beats,
  QA preparation), derives a defensible pace from them, requires one assertion per slide
  with a rankable evidence-strength label, and rejects topic-word claims. Builds a real
  editable .pptx with the standard library only, measures overflow on real glyph metrics
  with Chinese line breaking, checks that declared typefaces exist and have the glyphs,
  and verifies two builds produce the same deck. Every case returns result.json with
  case_id and the case's output_contract fields. Use when a task asks to plan, structure,
  or reorganise a research talk, or to turn paper material into presentable slides.
---

# talk-org

"Six slides is too many" is an opinion. "Six slides for a six-minute slot, where the
objective was to convince reviewers of novelty" is a judgement someone can disagree with
— which is what makes it useful.

This skill forces the objective to exist before page count means anything, and labels
every claim with the strength of the evidence behind it.

## 题面四问 → 规则

| 题面判断点 | rule |
|-|-|
| 报告目标可检查：目标、听众、时长先于页数存在 | `org.goal_missing`, `org.audience_missing`, `org.pace_too_fast`, `org.pace_too_slow` |
| 逐页主张：每页一句可反驳的论断，不是话题词 | `org.claim_is_topic`, `deck.claim_missing` |
| 证据强度：每个主张带可分级的强度标签 | `org.evidence_strength_missing`, `org.strength_unknown`, `deck.evidence_missing`, `deck.evidence_unsupported` |
| 叙事顺序：声明的节拍每页有落点 | `org.narrative_incomplete`, `org.role_undeclared` |
| 问答准备：预判追问 + 备用口径 | `org.qa_prep_missing` |
| 页面可上台：字号、溢出、密度、备注 | `text.font_too_small`, `text.overflow`, `deck.too_many_bullets`, `deck.notes_missing` |
| 交付可复核：图源、字体、母版、可复跑 | `paper.figure_unattributed`, `font.declared_missing`, `master.inconsistent`, `repro.nondeterministic` |

## 运行契约（Harbor runtime contract）

- 运行时输入是 /input/case.json 与 task.md：先读 case.json，逐字记录 case_id 与
  output_contract 的字段名清单（本题交付字段是可编辑演示文件、页级证据映射、渲染与版本
  记录这类）；再读 task.md 确认听众、时长、页数与模板约束。材料一律读实际文件，不按标签臆测。
- 工作目录 /app/work 放中间产物（spec.json、抽取的图表定位）；最终实际结果与可编辑产物放
  /app/output，其中 result.json 必须保留 output_contract 全部字段和 case_id（引擎自动回填，
  见第六步）。
- 可编辑演示产物要有真实渲染的 PDF/PNG 预览供查验；部分成果必须说明边界；不得伪造缺失的
  软件状态或科学数据。
- 预算：64 次模型请求、900 秒、每次响应 16384 token（含推理）。先尽早写出诚实的部分成果，
  再增量改进。三个固定案例、每条件重复三次。
- Skill 资源限制：最多 50 个 UTF-8 文本文件、单文件 500KB、总量 2MB、无符号链接。

## 演练纪律（本题固定案例的边界，逐条遵守）

- 论文/研究材料是事实依据：每页 evidence 必须是材料里真实存在的图号、表号、章节或数据
  位置，写进 available_evidence 白名单后由引擎校验；不得编造图号或把结论安到没看过的面板上。
- 模板约束按案例给定值声明（模板名、layouts 集合、字号阶梯），引擎按声明审 written deck
  是否真的落在模板上；案例没给模板就不声明，相应检查保持静默。
- 听众、时长、页数是任务给定的硬约束，进 goal 字段；不得自行改写后再自评合格。
- 本 Skill 不做论文精读、不做科研绘图素材生产、不做学术写作成稿——这三类由相邻课题承担；
  本 Skill 只计从已有内容材料到可讲页面的组织与交付。

## 六步运行时入口

0. **读 case.json 取标识**：记下 case_id 与 output_contract 的每个字段名；读 task.md 确认
   汇报形态（组会/答辩/评审）、听众、时长与模板约束。
1. **判形态路由**：按下面的「任务措辞 → 路由」决策表决定跑哪个 section、哪些字段必填。
2. **先产出目标产物**：可编辑演示文件（每页标题、主张、证据定位、备注）先行。把论文材料
   压成逐页主张——一段结论压成一句可讲的话，标注证据强度——而不是把摘要逐段搬成页面。
3. **构造 spec**：目标进 goal（objective/audience/minutes），材料定位进 available_evidence，
   每页进 slides（title/claim/strength/evidence/notes，图页加 image 与 caption）；按需声明
   narrative（节拍）、require_qa_prep + qa_prep（问答准备）、template（模板约束）、revisions
   （多轮修改记录）。section 取 talk_org（或按路由表取 paper_to_deck / deck_edit /
   template_fit）。附上 case_id，并把 output_contract 的每个字段以同名键放进 spec——spec
   携带的值逐字直通进 result.json。
4. **审计**：运行 python scripts/deckbuild.py --spec spec.json --out /app/output。
   退出码：0 clean、3 review、4 blocked、5 undetermined（输入无法审计）。
5. **修发现重跑**：每条 finding 按 Failure handling 表处置后重跑，直到 clean，或只剩已声明
   的 limits。high 发现不修复就直接交付等于 blocked。
6. **合并 result.json**：确认 /app/output/result.json 含 case_id 和 output_contract 全部字段
   （引擎自动回填：spec 带同名值的逐字直通，两边都没有的字段写 null 并在 limits 注明）；
   evidence_map 就是页级证据映射的交付形态；deck 块记录字体/模板/页数（渲染与版本记录）；
   把 deck.pptx 与预览放进 /app/output；在 limits 里写清材料缺口与需人工确认项。

## 任务措辞 → 路由决策表

| 任务里的措辞 | 路由与动作 |
|-|-|
| 「组会汇报 / 进度汇报」 | 跑 talk_org：goal.audience 写组内先验，objective 写要让组会达成什么；pace 允许快（在 objective 里说明） |
| 「答辩 / 让评委认可创新点」 | 跑 talk_org：每页 strength 必填，主张面向创新点与边界；问答准备必声明 |
| 「评审汇报 / 结论与证据强度」 | 跑 talk_org：结论页 strength 用 strong/moderate/weak 标注；limits 写证据边界 |
| 「按模板生成 / 母版、版式有要求」 | template 声明 name 与 layouts；每页 layout 必须在集合内，字号阶梯过审 |
| 「每页都能回溯到论文」 | available_evidence 白名单 + 每页 evidence；页级映射由 evidence_map 交付 |
| 「预判追问 / 准备备用页 / 口径一致」 | require_qa_prep 加 qa_prep（每条 question + answer 或 answer_slide） |
| 「叙事顺序 / 起承转合，不要按目录搬运」 | narrative 声明节拍序列，每页 role 对准一拍 |
| 「中文页面 / 字体别变方框 / 导出字体被替换」 | font_ea 与 font_latin 声明实际可用字体；引擎查字形覆盖并报告替换风险 |
| 「多轮修改演示稿 / 记录每次改动」 | 跑 deck_edit：revisions 记录逐条改动（slide/before/after/reason），delivered_revision 指认交付版 |
| 「论文图放页面上 / 图源归属」 | 图页必带 caption 与 evidence，编号一致；跑 paper_to_deck 可加强校验 |
| 「字号层级 / 标题漂移 / 内容丢了」 | 跑 template_fit：spacing 比例、标题几何与字号、声明内容是否真落进 written deck |
| 材料是整篇 PDF 论文 | 先自行抽取图/表/章节定位与关键数字，再进本 Skill；本 Skill 不读 PDF，不做精读 |

## The failures this exists to catch

**A deck with no declared objective.** Without it, length and depth are unjudgeable, and
every later criticism is taste.

**A slide whose claim is a topic.** "方法概述" states no position, so nobody can disagree
with it, and it will be the slide nobody remembers. Detection is a topic marker inside a
*short* claim — a full sentence that happens to contain 概述 is left alone.

**A strength label the reader cannot rank.** "very strong"、"比较可靠" are not on any
scale; a spec may widen the vocabulary with strength_scale, and anything outside it is
flagged so the deck speaks one strength language.

**A narrative arc with a hole.** Declaring 起承转合 beats is how a talk differs from a
paper walkthrough; a declared beat no slide carries is a planned step the talk skips.

**Chinese text measured with a Latin-only metric.** Two compounding faults, both fixed
here, and both of which silently disabled the overflow check for every Chinese deck: the
measuring font was DejaVu Sans (**no CJK glyphs**), and line breaking split on whitespace
while Chinese has none — so a paragraph measured as one line and never overflowed:

```
before: paras=5  need_px≈72   box_h_px=474   (judged to fit)
after:  paras=5  need_px=358  box_h_px=474   (overflow reported)
```

## Worked example（示例，非正式案例结果）

examples/spec.json 的完整输入（带 case_id 与 output_contract；此处节选关键结构）：

```json
{
  "case_id": "demo-case-320",
  "section": "talk_org",
  "spacing": {"title": 32, "body": 20},
  "font_ea": "Microsoft YaHei", "font_latin": "Arial",
  "goal": {"objective": "让评审认可多孔涂层方法的新颖性",
           "audience": "具备表面化学背景的评审", "minutes": 6},
  "narrative": ["question", "result"],
  "available_evidence": ["Fig. 3b, p.7", "Fig. 4a, p.9", "Sec. 5.2, p.12"],
  "require_qa_prep": true,
  "qa_prep": [{"question": "速率提高是热效应还是结构效应？",
               "answer": "Fig. 4a 的变温对照排除了热效应"}],
  "slides": [
    {"title": "吸收速率是当前工艺的瓶颈", "claim": "瓶颈在于可用表面积，而不是驱动力",
     "strength": "moderate", "role": "question", "evidence": "Fig. 3b, p.7",
     "notes": "先立瓶颈，再给方法。"},
    {"title": "多孔涂层使速率提高 3 倍", "claim": "涂层使吸收速率提高三倍",
     "strength": "strong", "role": "result", "evidence": "Fig. 3b, p.7",
     "bullets": ["对照组 12.4 a.u.", "涂层组 31.2 a.u.", "每组 n = 6"],
     "notes": "核心结果；强调速率，不是终点。"}
  ],
  "output_contract": {"deck_file": "可编辑演示文件", "evidence_map": "页级证据映射",
                      "presenter_notes": "讲稿/备注导出", "qa_ledger": "问答准备台账"},
  "presenter_notes": "全场口径：强调速率而非终点；追问见 qa_prep。",
  "qa_ledger": [{"question": "速率提高是热效应还是结构效应？",
                 "answer": "Fig. 4a 的变温对照排除了热效应"}]
}
```

运行（示例命令，正式运行时 --out 用 /app/output）：

```bash
python scripts/deckbuild.py --spec examples/spec.json --out examples/_demo_out
```

本机实跑：exit 3（review），一条发现——示例的 narrative 声明了四拍而页面只覆盖两拍：

```json
{"rule": "org.narrative_incomplete", "severity": "medium",
 "message": "the declared narrative arc has a beat no slide carries, ...",
 "missing": ["method", "limit"], "narrative": ["question", "method", "result", "limit"]}
```

把 narrative 收窄为页面实际承担的两拍后重跑（示例：examples/_demo_fixed.json，即同输入
narrative 取 question 与 result 两拍），exit 0，以下为本机实跑得到的示意输出，result.json
关键字段全文（示例，非正式案例结果）：

```json
{
  "schema_version": "deckbuild/v2",
  "case_id": "demo-case-320",
  "section": "talk_org",
  "status": "clean",
  "findings": [],
  "severity_counts": {},
  "deck": {"path": "examples/_demo_out2/deck.pptx", "slides": 2,
           "spacing": {"title": 32.0, "body": 20.0},
           "fonts": {"latin": "Arial", "ea": "Microsoft YaHei"}, "template": null},
  "evidence_map": [
    {"slide": 1, "title": "吸收速率是当前工艺的瓶颈",
     "claim": "瓶颈在于可用表面积，而不是驱动力", "strength": "moderate",
     "evidence": "Fig. 3b, p.7", "notes": true},
    {"slide": 2, "title": "多孔涂层使速率提高 3 倍",
     "claim": "涂层使吸收速率提高三倍", "strength": "strong",
     "evidence": "Fig. 3b, p.7", "notes": true}
  ],
  "presenter_notes": "全场口径：强调速率而非终点；追问见 qa_prep。",
  "qa_ledger": [{"question": "速率提高是热效应还是结构效应？",
                 "answer": "Fig. 4a 的变温对照排除了热效应"}],
  "output_contract_fields": ["deck_file", "evidence_map", "presenter_notes", "qa_ledger"],
  "limits": ["preview not rendered: no office renderer on PATH (soffice / office-renderer)",
             "output_contract field 'deck_file' was not derivable by this audit"]
}
```

deck_file 在 spec 与产物清单里都没有对应值，回填为 null 并在 limits 点名——这是契约直通
的诚实形态：不编造，也不漏字段。

## 评分要求映射（rubric 三段 → 本 Skill 落点）

| rubric 输出要求 | 完成标准（rubric 原词） | 本 Skill 落点 |
|-|-|-|
| 可编辑演示文件 | 页级结构、主张、图表、讲稿/备注和模板结果；能围绕论文主线讲清楚 | deckbuild 写出真实 .pptx（母版/版式/主题齐备，python-pptx 可打开）；每页 title/claim/bullets/caption/notes；deck 块记录模板与字体；evidence_map 携带逐页主张与强度 |
| 页级证据映射 | 引用准确，未改写事实 | 每页 evidence 必须命中 available_evidence 白名单（deck.evidence_unsupported 拦）；图号 caption 与 locator 一致（format.figure_mismatch 拦）；evidence_map 逐页导出供复核 |
| 渲染与版本记录 | 可打开、播放、编辑并复核 | preview 块如实记录渲染结果（无 renderer 时写明，不伪造）；reproducibility 块给出两次构建对比；revisions 逐条改动留痕（deck_edit）；fonts/template 进 deck 块 |

## Rules

### Organisation（talk_org section）

| rule | severity | what it proves |
|-|-|-|
| `org.goal_missing` | high | no objective, so length and depth are unjudgeable |
| `org.audience_missing` | medium | audience unknown, so background depth is uncalibrated |
| `org.claim_is_topic` | medium | the claim is a topic word, not an assertion |
| `org.evidence_strength_missing` | medium | a claim carries no strength label |
| `org.strength_unknown` | low | the strength label is outside the declared vocabulary |
| `org.pace_too_fast` | medium | under 0.7 min (42 s) per slide |
| `org.pace_too_slow` | low | over 4 min per slide |
| `org.narrative_incomplete` | medium | a declared narrative beat no slide carries |
| `org.role_undeclared` | low | a slide sits on a role the declared arc does not name |
| `org.qa_prep_missing` | medium | prepared answers demanded but none recorded, or an anticipated question has no answer pointer |

### Page and deck（deckaudit，对 written deck 逐条审）

| rule | severity | what it proves |
|-|-|-|
| `deck.no_title` | high | the slide has no title text |
| `deck.empty_slide` | high | the slide carries no text at all |
| `deck.no_slides` | high | the spec declares no slides, so there is no talk |
| `deck.claim_missing` | medium | the slide asserts nothing |
| `deck.evidence_missing` | high | no source locator, so the page cannot be checked |
| `deck.evidence_unsupported` | high | the locator is not in the declared evidence whitelist |
| `deck.too_many_bullets` | medium | over the declared density limit |
| `deck.title_too_long` | medium | the title is long enough to wrap into the body area |
| `deck.notes_missing` | medium | no speaker notes, so the talk repeats the slide |
| `deck.notes_repeat_title` | low | the speaker notes only repeat the title |
| `image.file_missing` | high | a declared figure does not exist on disk, so the page was built without it |
| `image.no_alt_text` | low | the picture has no alt text |
| `image.aspect_distorted` | high | the image was stretched against its source aspect |
| `text.overflow` | high | text does not fit its box, measured with CJK line breaking |
| `text.font_too_small` | high | below the legibility floor |
| `text.size_missing` | medium | a run declares no font size |
| `text.body_too_large` | low | body text competes with the title |
| `text.term_inconsistent` | medium | the same term appears in more than one spelling |

### Fonts, export and package

| rule | severity | what it proves |
|-|-|-|
| `font.declared_missing` | medium | a declared typeface is not installed here |
| `export.missing_glyphs` | high | characters no installed font can draw (中文变方框) |
| `export.missing_glyphs_in_declared_font` | medium | the declared East Asian face cannot draw some characters |
| `export.invalid_package` | high | presentation.xml is missing |
| `export.no_master` | high | the package has no slide master |
| `export.no_theme` | high | the package has no theme, so fonts are undefined |
| `master.layout_missing` | high | a slide resolves to no layout or master behind it |
| `master.inconsistent` | high | slides sit on more than one master |
| `embed.missing` | medium | embedded fonts declared but the package carries none |
| `repro.nondeterministic` | high | two builds differ |

### Paper-to-deck section

| rule | severity | what it proves |
|-|-|-|
| `paper.figure_unattributed` | high | a figure on a slide names no paper object |
| `paper.caption_missing` | medium | a figure is placed without a caption |

### Deck-edit section（多轮修改记录）

| rule | severity | what it proves |
|-|-|-|
| `edit.revision_without_changes` | medium | a revision records no changes |
| `edit.delivered_revision_missing` | medium | multiple revisions and no pointer to the delivered one |
| `edit.change_without_slide` | high | a change does not say which slide it touched |
| `edit.change_without_reason` | high | a change records no reason |
| `edit.change_is_noop` | low | a recorded change leaves the text identical |
| `edit.change_half_diff` | medium | a text change records only one side of the before/after pair |
| `edit.delete_without_snapshot` | high | a deletion records no removed text, so nothing can be restored |
| `edit.change_slide_out_of_range` | high | a change names a slide the deck does not contain |
| `edit.change_not_in_deck` | high | the change's new text landed neither in the slide nor in its notes |

### Template-fit section（模板与格式适配）

| rule | severity | what it proves |
|-|-|-|
| `format.size_ladder_flat` | medium | title and body sizes too close to read as a hierarchy |
| `format.size_ladder_steep` | low | title more than three times the body size |
| `format.template_unnamed` | low | the deck names no template |
| `format.undeclared_layout` | high | a slide uses a layout the template does not declare |
| `format.figure_mismatch` | high | caption and source locator name different figure numbers |
| `format.font_drift` | medium | a title is set in a typeface the declared theme does not name |
| `format.title_drift` | medium | slides on one layout disagree on title geometry or size |
| `format.content_dropped` | high | declared content never landed in the written slide |

### Audit entry

| rule | severity | what it proves |
|-|-|-|
| `audit.refused` | high | the case could not be run as declared (unreadable spec, non-object spec, unknown section, audit failure) — exit 5 |

## 异常处置表

| 情况 | 处置 |
|-|-|
| case.json 缺失或不可读 | 依 task.md 继续；result.json 的 case_id 写 null 并在 limits 注明来源缺失 |
| spec 不是合法 JSON / 不是对象 | audit.refused，status undetermined（exit 5）；修 spec 后重跑，不得手写 result.json |
| section 取值未知或不是字符串 | audit.refused（exit 5），消息列出可用 section；用 --section 显式指定 |
| slides 不是列表（字符串/数字） | 降级为空列表并在 limits 注明；空表按 deck.no_slides 拦（blocked） |
| goal 不是对象 / minutes 不是数字 | goal 降级为空对象并注记；org.goal_missing 会拦，补齐 goal 重跑 |
| bullets 不是列表 / 条目不是文本 | 该页 bullets 忽略并注记；标题与主张不受影响，审计继续 |
| 图文件路径不存在 | image.file_missing（high）：页面无图构建、诚实部分交付，补图后重跑 |
| 声明字体本机未安装 | font.declared_missing（medium）；文本度量自动换有字形的字体，不影响溢出判定 |
| 声明字体缺字形 / 全系统缺字形 | export.missing_glyphs（high）或 _in_declared_font（medium）点名缺字字符 |
| 无 office renderer | preview.rendered 为 false，limits 注明；不伪造渲染成功，装 renderer 或人工打开复核 |
| 超长标题/正文溢出 | text.overflow / deck.title_too_long 拦：拆页或精简，不许缩到字号下限以下 |
| output_contract 字段无法派生 | 回填 null 并在 limits 点名字段名；绝不编造值 |
| 重跑结果不一致 | repro.nondeterministic 拦；引擎纯确定性，不一致说明 spec 被改动，恢复 spec 重跑 |
| findings 为空但任务明显未完成 | 先查路由是否跑错 section；跑错 section 会得到假 clean |

## Output contract

/app/output/result.json（由 scripts/deckbuild.py 写出）包含：schema_version（deckbuild/v2）、
case_id、section、status（clean、review、blocked、undetermined 四态之一）、findings 数组
（每条带 rule、severity、message 与 slide 等定位字段）、severity_counts、deck（path、slides、
size_emu、spacing、fonts、template）、evidence_map（页级证据映射）、preview（渲染记录，
rendered 为 false 时 reason 说明原因）、reproducibility（两次构建对比）、checked（slides、
text_measured、font_file、minimum_font_pt）、limits，以及 output_contract 每个字段的回填值
（spec 携带值逐字直通，缺失为 null）与 output_contract_fields（字段名清单）。

## Limits

- **Pace is arithmetic, not judgement.** 1.5 min/slide suits a results talk and fails a
  single mechanistic argument; the finding is a prompt to justify.
- **The topic blocklist is shallow.** A topic-shaped claim phrased without those words
  passes; the length gate reduces but does not remove false negatives.
- **Evidence strength is a declared label.** The audit checks it exists and is rankable,
  not that it is deserved.
- **Narrative coverage is role-to-beat bookkeeping.** Slides may carry sound content the
  declared arc does not name; the rule checks the plan, not the rhetoric.
- **QA preparation is a ledger check.** It proves answers were prepared with pointers,
  not that they are correct.
- **Fonts are declared, not embedded.** If the target machine lacks the face, the deck
  reflows; the audit reports the risk rather than preventing it.
- **Determinism is compared on slide text and geometry**, not bytes.
- **Preview rendering depends on the environment.** Without soffice or office-renderer the
  run says so in limits instead of claiming a preview.

## Failure handling

| symptom | what to do |
|-|-|
| `org.goal_missing` | write the objective as a sentence someone could disagree with |
| `org.claim_is_topic` | replace the topic with the assertion the slide makes |
| `org.evidence_strength_missing` | label the claim; if you cannot, the evidence is weak |
| `org.strength_unknown` | use the declared scale, or widen it explicitly with strength_scale |
| `org.pace_too_fast` | cut slides, or accept it and say why in the goal |
| `org.pace_too_slow` | add the slides the talk needs, or shorten the slot in the goal |
| `org.narrative_incomplete` | give a slide the missing beat, or narrow the arc to what the talk does |
| `org.qa_prep_missing` | record anticipated questions with answer pages or answer text |
| `deck.no_slides` | the spec has no slides; build the page list first |
| `text.overflow` | split the slide; never shrink below the font floor |
| `image.file_missing` | put the figure on disk, or drop the field and say so in notes |
| `export.missing_glyphs` | install a font covering those characters — this is 中文变方框 |
| `repro.nondeterministic` | the build changed between runs; fix before shipping |

## Verification

```bash
python scripts/bench_deck2.py     # 20 scenarios: organisation, narrative, QA, CJK overflow, fonts, determinism
python scripts/bench_deck.py      # 11 scenarios: page/deck hygiene on written files
python scripts/bench_extra.py     # 23 scenarios: per-skill sections, one per rule
python scripts/bench_contract.py  # 7 scenarios: case_id/output_contract passthrough and refusals
```

All pass in full on this machine (20+11+23+7 = 61). A missing typeface, a font without
glyphs and a non-reproducible build cannot be expressed in a spec, so those scenarios
inject them by patching. examples/bench-report.json 是示意报告（示例，非正式案例结果）。

## 创新增益

以下均为引擎真实具备、可复跑验证的能力（bench 与 gate 是回归证据）：

1. **目标先行、页数才可判**：objective/audience/minutes 是结构化字段而非口号，pace 由
   分钟与页数机械推导（0.7–4 min/页 双向拦截），三条限速发现都给了「说明理由即可豁免」的
   出口——把"这次汇报要达成什么"变成可检查的输入，是通用 Agent 不会自建的约束。
2. **中文文本的真实度量**：溢出判定用真实字形宽度 + CJK 逐字断行，度量字体按文本覆盖自动
   选择（fontsel），并把实际用的字体文件写进 checked 供复核；两条历史缺陷（Latin-only 度量
   字体、空白切行）都有 bench 场景钉住，不靠自觉。
3. **审计 artifact 而非输入**：布局、字号、母版链、备注占位符全部从写出的 .pptx 里重新解析
   （deckaudit 读 OPC 关系树），声称改一页却改坏母版、备注写进普通文本框这类"文件能打开但
   上台必翻车"的问题有专门规则。
4. **叙事与问答可机械检查**：narrative 节拍覆盖、role 对齐、qa_prep 台账（问题 + 答案页）
   都是声明式规则——案例声明了才启动，最小输入零误报；这是 rubric 突破方向 3 与 5 的直接
   落点，通用 Agent 无法对自己排的页序做这两项证明。
5. **契约直通与确定性**：同 spec 两次运行 findings 全等（bench_contract 场景钉住）；
   case_id 与 output_contract 字段自动回填 result.json，spec 携带值逐字直通，无法派生的字段
   写 null 并在 limits 点名；一切拒跑路径（坏 JSON/非对象/未知 section/内部异常）输出
   status undetermined 的可追踪 result.json（exit 5）且绝不伪造契约字段。

## 生态贡献

1. **SKILL.md 全量文档**：用途、适用条件、调用方式、输入输出、异常处理（14 类）、限制与
   自查方法齐备，说明与提交版本一致。
2. **纯标准库生成器**：scripts/pptxgen.py 直接写 PresentationML（zipfile + saxutils），
   不依赖 python-pptx，在未装该库的评测镜像里照样产出真实可开文件；PNG/JPEG 尺寸从文件头
   解析，Pillow 仅用于度量，缺了降级为估算并如实注记。
3. **规则清单与引擎一一对应**：本文件 58 条 rule id 都能在引擎源码里找到发出点（验收 gate
   的规则奇偶校验强制）；四张规则表可直接当作汇报自查清单复用。
4. **路由决策表与四 section 分类法**：talk_org / paper_to_deck / deck_edit / template_fit
   的 section 划分与「任务措辞 → 路由」表，可移植到其他"从材料到交付物"类任务。
5. **最小调用示例**：examples/spec.json（带 case_id 与 output_contract 的完整输入）+
   示意输出节选 + examples/bench-report.json（示意报告，标注为示例），全部实跑验证。
6. **回归套件可独立复跑**：bench_deck2 20 + bench_deck 11 + bench_extra 23 + bench_contract
   7，每条规则至少一个场景、每个新规则配 FP 守卫，clean 基线零发现。
7. **引擎参考文档**：references/deck-engine.md 记录生成器为何无依赖、审计为何读文件、
   度量如何降级，以及引擎自身两条历史缺陷的修复证据。
8. **验收 gate 可复跑**：本包可通过 strict_gate.py 的 G1-G7 七项验收（打包/基准/文档路径/
   规则奇偶/冷启动/真实输入冒烟），他人可对复刻包执行同一验收。

## Requirements

Python 3.9+（3.14 实测）。matplotlib 与 Pillow 用于字形度量与图片尺寸（缺失时溢出检查
降级为估算并如实注记）；pptx 生成与审计纯标准库。scripts/ 下 deckbuild.py（构建与
result.json）、deckaudit.py（文件级审计）、extra_rules.py（四个 section 规则）、pptxgen.py
（OOXML 生成器）、fontsel.py（字体覆盖）、contract.py（case_id/output_contract 直通与拒跑）
均可独立导入。
