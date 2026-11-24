---
name: talk-org
description: >
  Organize an academic talk around its objective, audience and fixed time, then generate the real
  editable PPTX and reviewable presentation plan. Use for group meetings, thesis defense, project review,
  paper-to-talk restructuring or rehearsal. Enforces conclusion-style titles, one claim per slide,
  narrative roles/order, audience emphasis, evidence strength/rationale, slide timing and Q&A reserve,
  closing takeaway, limitations, selection ledger and evidence-backed anticipated questions. Verifies
  these against the delivered slides, notes and visible sources; also checks overflow, bounds, overlap,
  fonts, contrast, deterministic rebuilds and full case/output_contract passthrough with structured exits.
---

# talk-org：按听众和时长组织“可上台”的汇报，而不是压一遍论文

本技能交付 **真实可编辑的 PPTX、可见来源、speaker notes、演示计划和取舍记录**，不是内容大纲建议。
输入材料决定能说什么；目标、听众与时间决定说什么、按什么顺序说、舍掉什么。禁止为了获得 clean
而编造研究结论、图号、数字、实验对照或预期问答答案。

## 固定运行入口

原始输入是 `/input/case.json`、`/input/task.md` 与实际科研材料。工作文件放 `/app/work`，正式结果放 `/app/output`。

0. **读案例与任务约束。** 原样记录 `case_id` 与 `output_contract` 全字段；固定汇报类型（组会/中期/答辩/评审）、
   受众、时长、页数、模板、导出和问答要求。打开实际 PDF 和附件，不依据任务标签猜研究内容。
1. **先声明目标与听众适配。** 写 `goal.objective/audience/minutes`，必要时加 `qa_minutes` 和页数上限。
   `audience_plan` 写听众先验、想让对方做到什么决定，以及重点节拍，不把“同行”两个字当完整听众画像。
2. **形成逐页故事板。** 先提炼问题—方法—结果—限制；每页一个可反驳 claim、一个 role、一个结论式标题和
   evidence。补充 `strength` 与 `strength_rationale`、逐页时间、选择理由、讲者备注。末页留下可复述结论，
   写清局限/下一步；backup 可放在其后，但不占主线时间，也不能顶替结束页。
3. **把取舍变成记录。** 写清哪些内容 kept、哪些 omitted、各自 source locator 和 reason。预判机制/数据/对照/局限
   追问，准备 answer 或 answer_slide，必要时附 evidence pointer。没有证据支持的问答应列 uncertainty，不编确定口径。
4. **尽早生成真实 deck。** 按下面 schema 写 `/app/work/spec.json`，用 CLI 生成 PPTX 并读回最终文件；
   不用“先写讲稿建议”代替成品。可保留实际 source_deck 或套入真实 template.file，见共用边界。
5. **修发现并重跑。** 时间超预算先砍背景/重复结果，不强行加速；标题只写主题改成结论；故事倒序重排；
   takeaway 没落页要修文件；不能只删 finding。缺材料就把缺口写入 uncertainty/gaps/limits。
6. **交付前独立复核。** 核对主线最后一页、备注和证据、PPTX/PDF 页数、演示计划与合同。没有 renderer 时只做结构
   几何检查，不能声称完成视觉验收或伪造 PDF。

## 真实 CLI

```bash
python -I -X utf8 scripts/deckbuild.py \
  --spec /app/work/spec.json \
  --case /input/case.json \
  --out /app/output
```

可选 `--case-id` 只在 case 文件缺失时提供已知标识。Python 3.10+，核心标准库；Pillow/matplotlib 是可选加速而非导入依赖。
渲染器自动尝试 PATH 和常见 LibreOffice 安装位置。`DECKBUILD_NO_RENDER=1` 仅供作者回归，正式案例不要设置。

主要产物：

- `deck.pptx`：真实可编辑 PresentationML，含母版、版式、图形和媒体关系；speaker notes 在真实 body placeholder；
- `deck.pdf`：仅真实渲染成功时生成，record 含 renderer、字节数和有效文件头；
- `result.json`：status/findings、deck、preview、checked、evidence_map、presentation_plan、version_record 和完整合同；
- `presentation_plan.json`：goal、audience_plan、narrative、selection_ledger、qa_prep、逐页 claim/role/strength/时间/选择理由；
- `evidence_map.json`、`change_records.json`：页级定位和版本记录。

`presenter_notes`、`qa_ledger`、`timing_plan` 只派生真实存在的数据。spec 已显式提供 `presenter_notes`/`qa_ledger` 时，
原文按 contract 直通，不被空数组或自报样式覆盖；无法推导的字段保留原名为 null 并写 limits。

## 报告目标、听众与时间

```json
{
  "goal": {
    "objective": "让评审认可对照证据，并接受外推边界",
    "audience": "懂吸附实验但非制造方向的评审",
    "minutes": 12,
    "qa_minutes": 2
  },
  "audience_plan": {
    "prior_knowledge": "理解对照实验，不熟悉制造细节",
    "decision": "判断比较条件是否支持结论与外推",
    "emphasis": ["method", "result", "limit"],
    "max_background_slides": 0
  }
}
```

`minutes` 是包含问答的总 slot，`qa_minutes` 是预留问答时间。主讲逐页 `pace_minutes` 总和不能超过二者之差；
`require_timing` 时每个主线页必须分配时间，非正值、超预算、低于主讲预算 75% 的时间使用不足分别报告。
平均语速另作提示：过密会触发 pace_too_fast，过稀会触发 pace_too_slow。backup/appendix 不计主线页数与 pace。
有余量用于衔接是可以的，不要为了凑满时长补造内容。

听众重点 `emphasis` 必须能在主线 role 中找到落点；`max_background_slides` 只计算 role=background/context，
不会把 question 机械等同于背景。普通实验会议也建议调用它避免背景占满汇报。

## 逐页 schema：一个主张、可见证据和选择理由

```json
{
  "section": "talk_org",
  "case_id": "demo-only",
  "goal": {"objective": "让评审理解证据边界", "audience": "研究评审", "minutes": 8, "qa_minutes": 2},
  "narrative": ["question", "method", "result", "limit"],
  "require_role": true,
  "require_single_claim": true,
  "require_evidence_rationale": true,
  "require_evidence_on_slide": true,
  "require_timing": true,
  "require_closing": true,
  "require_limitations": true,
  "require_qa_prep": true,
  "require_qa_evidence": true,
  "required_qa_topics": ["mechanism", "data", "limitations"],
  "require_audience_plan": true,
  "require_selection_ledger": true,
  "require_selection_reasons": true,
  "require_notes": true,
  "spacing": {"title": 32, "body": 20},
  "font_latin": "Arial", "font_ea": "Microsoft YaHei",
  "min_font_pt": 14, "max_bullets_per_slide": 5, "min_slides": 4, "max_slides": 8,
  "available_evidence": ["Sec. 2, p.3", "Fig. 3b, p.7", "Sec. 5.2, p.12"],
  "audience_plan": {"prior_knowledge": "懂对照实验", "decision": "判断外推边界",
                     "emphasis": ["method", "result", "limit"], "max_background_slides": 0},
  "selection_ledger": {
    "kept": [{"content": "直接对照", "evidence": "Fig. 3b, p.7", "reason": "直接支持核心比较"}],
    "omitted": [{"content": "整段理论综述", "evidence": "Sec. 2, p.3", "reason": "听众已具备先验"}
  ]},
  "qa_prep": [
    {"topic": "data", "question": "2.52 倍如何计算？",
     "answer": "31.2 / 12.4 = 2.52，回到原对照", "answer_slide": 3, "evidence": "Fig. 3b, p.7"},
    {"topic": "limitations", "question": "能推广到其他厚度吗？",
     "answer": "当前数据不支持，需要厚度矩阵", "answer_slide": 4, "evidence": "Sec. 5.2, p.12"},
    {"topic": "mechanism", "question": "是否只有热效应？",
     "answer": "需由等温对照区分", "answer_slide": 2, "evidence": "Sec. 2, p.3"}
  ],
  "slides": [
    {"title": "吸收速率是当前工艺瓶颈", "layout": "title", "role": "question",
     "claim": "可用表面积是关键约束", "strength": "moderate",
     "strength_rationale": "Sec. 2 的问题定义直接限定研究取舍", "evidence": "Sec. 2, p.3",
     "pace_minutes": 1, "selection_reason": "先建立待回答问题", "notes": "先立问题，再进入对照。"},
    {"title": "等温对照分离结构效应与热效应", "layout": "content", "role": "method",
     "claim": "等温配对对照能够区分这两种解释", "strength": "measured",
     "strength_rationale": "两组等温且每组 n = 6", "evidence": "Sec. 2, p.3",
     "pace_minutes": 1.5, "selection_reason": "先交代评审需要的比较条件",
     "bullets": ["两组等温", "每组 n = 6"], "notes": "只解释支撑判断的变量。"},
    {"title": "涂层组速率为对照组 2.52 倍", "layout": "content", "role": "result",
     "claim": "31.2 / 12.4 = 2.52，本对照支持速率提升", "strength": "strong",
     "strength_rationale": "Fig. 3b 的 n = 6 直接对照同时给出两组实测速率",
     "evidence": "Fig. 3b, p.7", "caption": "Fig. 3b, p.7 — 直接对照",
     "pace_minutes": 2, "selection_reason": "最直接定量证据",
     "bullets": ["对照 12.4 a.u.", "涂层 31.2 a.u."], "notes": "强调精确数值与对照。"},
    {"title": "变温与厚度范围限制外推", "layout": "content", "role": "limit",
     "takeaway": "变温与厚度范围限制外推",
     "claim": "这些发现不能推广到未测厚度或长期条件", "strength": "moderate",
     "strength_rationale": "只有单厚度和有限时长，Sec. 5.2 列出验证缺口",
     "evidence": "Sec. 5.2, p.12", "pace_minutes": 1.5,
     "selection_reason": "结论必须同时说明贡献和边界",
     "limitations": ["仅测一个厚度", "未评估长期稳定性"],
     "bullets": ["仅测一个厚度", "长期稳定性尚未评估"], "notes": "以范围化结论结束。"}
  ]
}
```

正式运行必须用源材料真实值替换演示文字，不能把示例变体当正式答案。`strength_rationale` 不重复图号，
要解释为什么该证据支撑这个强度；简单 measured/strong/weak 标签本身不构成证据评价。

### 页面上的来源和图

- `evidence` 精确命中 `available_evidence`，并在 `require_evidence_on_slide` 时写入真实 slide 的 Caption/Source 带。
  它不是只在 result.json 中存在的字段；缺失时触发 `deck.evidence_not_landed`。
- 有图时提供 `image`、`image_alt`、`caption`、`evidence`。由原图头计算内在比例并等比放置；不把重绘图或假曲线用于代替缺失证据。
- caption 写条件、样本、面板含义和实际 source locator；已含 evidence 时不重复拼写。
- `notes` 写如何解释、过渡、停顿和答复，不只重复标题；追加问答页也要保留证据。

## 叙事、结束页、局限与 backup

`narrative` 声明主线节拍序列，例如 `question → method → result → limit`。规则检查：

- 每拍是否实际出现、每页 role 是否存在、是否落在声明集合中；
- 顺序是否倒退——不是只有“四拍都出现了”就能通过；
- 主题式短标题（如“结果”“方法概述”）与主题式 claim 分别检查；`require_single_claim` 默认启用，一页多个独立句级主张会报告；
- backup/appendix/qa 可在声明主线之外存在，不计主线顺序和时间，不触发 role_undeclared；
- `require_closing` 时最后一个 **主线页** 必须是 closing/conclusion/takeaway/limit/next_steps 之一，且 takeaway
  （未显式填写时回退 title）必须真的出现在该交付页；backup 放在最后不会把这个检查绕过去；
- `require_limitations` 时主线必须有 limit/limitations 角色页，并含 limitations、bullets、takeaway 或 claim 实质内容。

不要为了规避检查只把最后一页 role 改名为 limit；实际标题、局限和备注也必须对应该页的科学内容。

## 证据强度与问答

`strength_scale` 可扩展，默认标签为 weak/moderate/strong/measured/supported/suggested/cited。
开启 `require_evidence_rationale` 后，claim 必须给出强度理由。`strong` 附近出现 preliminary、uncertain、探索性、
初步等限定词会触发 strength_overstated，避免强结论和责任规避同时存在。

`require_qa_prep` 时，每条 qa_prep 必须有 question 与 answer 或 answer_slide。额外：
- `required_qa_topics` 指定必须准备的类别，question 项写对应 `topic`，缺类别报 qa_topics_missing；
- answer_slide 必须落在真实页范围内；
- `require_qa_evidence` 要求每条有 evidence 或 answer_slide；
- 重复问题另报 low，避免问答台账数量好看但覆盖面虚高。

## 取舍台账：从源材料到页面怎样选择

`require_selection_ledger` 时，kept/omitted 每条都要 `content + evidence + reason`。
`require_selection_reasons` 时每个主线页再写 `selection_reason`，解释这页为什么值得占一个时段；backup 不强制占主讲时间。
这些进入 result 和 presentation_plan，供复核者判断重点是否服务于目标，而不是事后泛泛自述“结构清晰”。

## 共用模板、源稿与页面约束

`source_deck` 保留原包部件执行明确 DrawingML 修改；`template.file` 实测并应用真实 master/layout/theme 和 title/body 占位符。
不需要套真实模板时，仅在 JSON 里写 layout=title/content 等 authoring 标签，不启用 template.* 检查；需要检查时按任务声明 template。

`style.margins_in` 为上/右/下/左（TRBL）。主题色、Footer、Logo、动态 slidenum 都可实际生成。
最终审计包含 CJK 字形宽度与中文断行的宽/高溢出、字号下限、要点密度、图比例、空白页、出画布/重叠/零尺寸、明确 RGB 对比度、
字体发现/缺字、母版链、包完整性和两次生成 slide 文本/几何/notes 一致性。套用真实模板时，caption/source band 会保留，
不让全高正文框覆盖它。

几何检查只覆盖显式 slide shapes/pictures，不模拟全部 group transform、PowerPoint 自动布局和字体替换。
溢出度量用 glyph advance（有字体文件时），不含 kerning/ligature。PDF 产生不等于逐像素一致，须光栅化关键页；
无法渲染/查看必须在 limits 中说明。科学 claim 与证据语义仍需回读原论文。

## 状态、结构化拒绝和退出码

| status | exit | 用法 |
|-|-|-|
| clean | 0 | 无 findings，仍需回读科学源材料 |
| review | 3 | 仅 medium/low，可交付但必须披露剩余问题 |
| blocked | 4 | 至少一个 high，不得冒充已完成 |
| undetermined | 5 | 输入/spec 缺失、坏 JSON、非对象、未知 section、源文件无法运行等 |

主要组织 finding 包括：org.goal_missing（high）、org.closing_missing、org.limitations_missing、org.narrative_incomplete、
org.narrative_order、org.title_is_topic、org.multiple_claims、org.pace_slide_missing、org.pace_budget_exceeded、
org.audience_emphasis_missing、org.strength_rationale_missing、org.strength_overstated、org.qa_topics_missing、
org.takeaway_not_landed（high）、org.content_dropped（high）、deck.evidence_not_landed（high）。
完整规则含义和实际触发证据都保留在 result 的 findings[]，不得为了让交付好看而静默删字段。

CLI 永不裸抛 traceback。可读 case（或有效的 spec）的 case_id 和 output_contract 在正常/拒绝路径都保留所有字段；
未知 section 可以 undetermined，但不得丢掉已知身份。无法生成的路径或导出状态写 null/limits。
`audit.no_section` 与旧别名 `audit.refused` 共用 undetermined/5；`image.source_missing` 与旧别名 `image.file_missing` 共用 blocked/4。

## 完整 worked example（接口示例，非正式答案）

`examples/spec.json` 含 5 页主线 + 1 页 backup：12 分钟总 slot（2 分钟问答预留、9 分钟逐页主讲、1 分钟衔接余量），
question→method→result→limit，结尾含局限，QA 覆盖 mechanism/data/limitations，kept/omitted 全有来源与理由。

```bash
python -I -X utf8 scripts/deckbuild.py --spec examples/spec.json --case-id demo-case-320 --out /app/output
```

本工作流已在本机这类规格上得到 status=clean、6 个 slide/notes/slide-number field 和真实 PDF。
平台实际预览以运行时 `preview` 为准，不把作者渲染环境当保证；示例数值不是组织方固定案例数据。

## 开源机制的实际落地

- **PptxGenJS**：真实 slide/master 关系、TRBL margins、bodyPr、主题字体/颜色和 slidenum field；
  `pptxgen.py` 用于从零生成，source/template 部件继续保留连接。其源码没有通用 overflow/off-slide 检测，故本包另写。
- **python-pptx**：layout placeholder 类型/idx/继承、notes body placeholder；source 和 template 流程不丢这些关系。
  起因于普通 notes 文本框不能被 Notes pane 识别的问题，现以真实 placeholder 写讲者备注。
- **reveal.js**：固定画布、剩余空间布局、媒体等比 fit，启发 Caption/Source band 与媒体 placement；实际输出为 PPTX。
  报告目标、叙事顺序、证据强度/时机、Q&A 和取舍台账是本包另外的可执行组织机制，不冒充开源已有功能。

参考：gitbrent/PptxGenJS、scanny/python-pptx、hakimel/reveal.js；核心运行不依赖这些第三方包。

## 作者侧回归（不是正式运行时主路径）

```bash
DECKBUILD_NO_RENDER=1 python -I -X utf8 scripts/bench_deck.py
DECKBUILD_NO_RENDER=1 python -I -X utf8 scripts/bench_deck2.py
DECKBUILD_NO_RENDER=1 python -I -X utf8 scripts/bench_contract.py
DECKBUILD_NO_RENDER=1 python -I -X utf8 scripts/bench_extra.py
DECKBUILD_NO_RENDER=1 python -I -X utf8 scripts/bench_delivery4.py
DECKBUILD_NO_RENDER=1 python -I -X utf8 scripts/probe_delivery4.py
```

61 个 legacy 场景覆盖基础 deck/组织/contract/规则；17 个新增 artifact 场景覆盖完整 clean 故事、主题标题、多主张、
倒叙、结尾/局限、听众重点、超时/缺时、QA 主题/指针、强度理由、过强结论、取舍与可见来源；
27 个真实 CLI 探针覆盖拒绝、全字段、幂等、源稿保留和退出码。报告 `scripts/report_*.json`，不是平台正式成绩。

## 适用边界

- Agent 负责论文精读、科学取舍、源值核对和视觉复核；引擎不臆造 claim/evidence，不用文件标签替代原文。
- 复杂动画、OLE/SmartArt 内部、复杂 group transforms、位图内部数据系列不在完整修改能力内；图表内部不成为原生可编辑数据。
- 支持 DrawingML 文本、样式/几何和常见 title/body placeholders，不是整个 PowerPoint 排版引擎复刻。
- 字体声明不等于嵌入；缺字体/缺字形/预览缺失全部独立留痕。`clean` 不代表专家认可研究叙事或事实无误。
