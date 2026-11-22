---
name: compliance-audit
description: >
  学术规范与合规检查：把"这份材料哪里不合规"变成一组可定位、可核对、可交办的问题
  条目，而不是一段泛泛的规范提醒。四道审查面覆盖修订包（每条审稿意见都有答复、
  伦理类意见被分类处理、每条声称的修改都能落回其指名版本的稿件、必备声明逐项留痕）、
  引用纪律（每条论断绑定真实、可分类、可摘录原文的来源）、双语交付合规（数字、单位、
  引文、否定与限定语的保真，术语锁）和投稿要求合规（章节、字数、样式、导出与引用
  一致性逐条映射到稿件）。每条发现带规则 id、严重度、判定依据与可执行修改建议；
  确定性引擎保证同一份材料两次运行得到同一份清单。Use when a task asks for
  学术规范与合规检查, 学术诚信/利益冲突/伦理审查, 引用规范检查, 双语/翻译合规检查,
  or a journal-requirement conformance check of a manuscript.
---

# compliance-audit（学术规范与合规检查）

一份合规审查最容易输在两个极端，而两端都"看起来完成了"：

- 一端是概括性提醒——"建议检查参考文献格式是否规范"——没有条目、没有定位、没有依据；
- 另一端是大面积误报——把风格差异、学科惯例或作者的刻意选择判成学术不端；
- 夹在中间的更隐蔽：声称的修改（"we have added a vehicle control"）从未落进交付的
  稿件；译文悄悄翻转了一个否定词，或把 may contribute 写成了 contributes。

每一条都可以对材料的结构化读取做机械判定，所以每一条在这里都是规则。引擎不评文风、
不判动机：类型词表与容忍带全部显式声明，规则触发条件之外的差异一律保持安静。漏报与
误报同样扣分，所以每条规则同时配一个 bench 场景钉住它的触发与误报。

## 六步运行时入口（Harbor）

运行时原始输入固定为 /input/case.json 与 task.md；中间产物写 /app/work，最终结果写
/app/output。依序执行：

- **第 0 步·读案例**：读 /input/case.json，取 case_id 与 output_contract（结果必须
  保留的字段清单），再按 task.md 指向的路径读**实际材料文件**（修订稿、答复信、
  译文、期刊指南）。读实际文件，不按文件名或领域标签猜内容——实际输入文件是事实依据。
- **第 1 步·判形态路由**：按下方「任务措辞与形态 → 路由」决策表选 section；修订类
  材料跑 review_response，引用类跑 evidence_writing，双语类跑 translation，投稿
  合规类跑 format_template；材料跨多面时多跑几道再合并。
- **第 2 步·先产出目标产物**：先把审查单本身（逐条问题、位置、严重度、依据、建议）
  写进 /app/work 作为中间交付——预算有限时先有诚实的不完整清单，再增量补齐。
- **第 3 步·构造 spec**：把材料结构化抽取成所选 route 的 spec 字段（见 Workflow 第
  1 步的字段表），并带上 case_id 与 output_contract 原样传递。抽不到的字段留空并
  标注 missing——抽取缺口会变成发现（待复核），绝不静默跳过，也绝不编造字段值去
  "喂饱"规则。
- **第 4 步·审计**：跑 scripts/writeaudit.py，得 findings 与 result.json（退出码
  0/3/4/5，见下）。
- **第 5 步·修发现重跑**：逐条回原文复核 findings——定位错的重抽、答复漏的补答复、
  声明缺的补声明；确认是引擎口径内误报的按 Limits 处理并在报告中说明，不删条目。
  修完重跑直至清单稳定。
- **第 6 步·合并 result.json**：写 /app/output/result.json——回填 case_id 与
  output_contract 点名的每个字段（三段结构映射见下），引擎的 findings、
  severity_counts、pending、checked、limits 原样保留作为操作证据。

## 任务措辞与形态 → 路由

| 任务措辞 / 案例形态 | 跑什么 | 审什么 |
|-|-|-|
| 修订说明 / 答复信 / response letter / 学术诚信·伦理·利益冲突 | --section review_response | 意见覆盖、伦理类意见处理、决定与语气、修改落地、证据状态、必备声明（规则 resp.*） |
| 引用规范 / citation discipline / 论断-证据对账 | --section evidence_writing | 论断、来源、强度、不确定性四要素，双向引用覆盖（规则 ew.*） |
| 双语交付 / 翻译合规 / 中英对照 | --section translation | 输出形态、逐段对照、数字/单位/引文守恒、否定与限定语保真、术语锁（规则 xlate.*） |
| 投稿要求 / 期刊模板 / author guidelines 合规 | --section format_template | 章节、顺序、编号、字数、样式绑定、导出验证、引用一致、指南版本（规则 fmt.*） |
| "全面合规审查"无明确子项 | review_response 加 format_template 双跑 | 合并两份 findings，按材料位置排序 |
| 利益冲突 / 基金 / 数据可用性声明缺失 | --section review_response | required_declarations 加 declarations 两字段即覆盖 declaration_missing |
| 第三方图/表/代码/数据集的许可与署名、受限数据授权 | --section review_response | third_party[] 每条须有 source 与 license；restricted_data[] 每条须有授权 basis |
| 伦理审查意见是否被处理 | --section review_response | ethics 类型意见走同一覆盖规则；拒绝须写伦理依据（ethics_decline_without_basis） |
| 引文是否真实、是否张冠李戴 | --section evidence_writing | 引文逐字包含检验 quote_not_in_source、撤稿来源 retracted_source_used |
| 译文数字/单位/否定词是否保真 | --section translation | invariant_broken、negation_changed、hedge_strength_changed |
| 稿件是否照期刊指南改齐、导出是否可复用 | --section format_template | section_missing、word_limit_exceeded、heading_style_unbound、export_unverified、guide_version_missing |
| 润色改写 / 代写代投 / 数据重新分析 / 法务或伦理委员会正式意见 | 不属本 Skill | 明确说明边界，不产出审查单 |

## Workflow

### 第 1 步·抽取结构化 spec

读实际材料，为所选 route 写 spec。引擎审计你抽出的东西；抽不到的留空加注。

review_response spec —— 每个字段被哪些规则消费：

| 字段 | 消费者 |
|-|-|
| comments[] | {id, text, type, severity, subrequirements[]}——type 取 method / data / writing / format / ethics；severity 取 major / minor / editorial |
| responses[] | {comment_id, decision, tone, reason, changes[], evidence[]}——decision 取 accept / partial / reject；tone 取 accept / clarify / polite_rebuttal / appeal |
| responses[].changes[] | {what, location, manuscript_version, added_text} |
| responses[].evidence[] | {kind, status, alternative, ...}——status 取 provided / unavailable / alternative_given |
| manuscript_text, manuscript_version | 答复信声称的对照稿件 |
| required_declarations + declarations | 必备声明清单（coi / funding / data_availability / ethics_approval 等）与其实际内容 |
| third_party[] | 复用的第三方材料：{what, source, license}——声明后启用许可与署名检查 |
| restricted_data[] | 受限/个人/未公开数据使用：{kind, basis}——声明后启用授权依据检查 |
| anchors | 可选：答复信可指向的定位清单 |
| baseline_text | 可选：修订前稿件；声明已改而稿件与基线一致即 manuscript_unrevised |

伦理类意见（type 为 ethics）走与其他意见完全相同的覆盖与决定规则——未答即 high
发现；拒绝必须有理由，且理由须写明伦理依据（委员会/批件/知情同意/审查），否则
ethics_decline_without_basis。

evidence_writing spec：

| 字段 | 消费者 |
|-|-|
| claims[] | {id, claim, strength, strength_basis, uncertainty, sources[]}——strength 取 strong / moderate / weak；sources 携带 {key, quote, locator} |
| evidence[] | 来源表：{key, title, year, source_type, text, retracted}——source_type 取 primary / review / guideline / preprint |
| draft（或 text） | 论断必须出现的稿件 |

translation spec：

| 字段 | 消费者 |
|-|-|
| output_mode | plain / bilingual / tracked |
| source_text, target_text | 全文对比的两侧（无逐段对照时） |
| segments[] | bilingual/tracked 形态：{id, source, target} 逐句或逐段对 |
| glossary | {term: {preferred, variants, basis}}——术语锁 |
| conversions | 万/亿与 million/billion 换算记录 |
| components | 可选：figures / tables / footnotes / references 部件声明 |

format_template spec：

| 字段 | 消费者 |
|-|-|
| text | 改排后的稿件文本 |
| template | {sections, word_limit, spec, checks, guide, conflicts}——guide 记录所依据的作者指南及其 version/date |
| headings[] | {level, number, text, style} |
| input_units / output_units | 转换前后内容单元计数 |
| conversion_steps, export, checks_done | 转换留痕、导出验证、检查单执行记录 |
| references[], figures[] | 引用一致性与交叉引用检查 |

### 第 2 步·运行

```bash
python scripts/writeaudit.py --spec spec.json --out /app/output --section review_response
python scripts/writeaudit.py --spec spec.json --out /app/output --section evidence_writing
python scripts/writeaudit.py --spec spec.json --out /app/output --section translation
python scripts/writeaudit.py --spec spec.json --out /app/output --section format_template
```

退出码：0 clean，3 review（有 medium/low 待处理），4 blocked（有 high），5
undetermined（拒绝运行——见 Failure handling）。每次运行向 out 目录写 result.json。
确定性引擎：同一 spec 重跑得到同一份 findings。

### 第 3 步·交付

result.json 含 case_id、section、status、findings[]、severity_counts、pending、
checked、limits 以及 output_contract 点名的字段。把所跑 route 的 findings 合并成
一份按材料位置排序的条目清单；每条 finding 自带定位（comment_id、location、claim、
segment、key）与判定依据、修改建议，保持附着。引擎判不了的事项（材料缺失、原文歧义、
依据条款拿不到）在报告中标待复核——不编造判定，不悄悄丢条目。

## 规则库

### review_response —— 诚信、利益冲突、隐私与伦理处理（完整规则索引，30 条）

| rule | severity | 证明什么 |
|-|-|-|
| resp.no_comments | high | 未提供审稿意见，覆盖性无法判定（待复核而非定罪） |
| resp.no_letter | high | 未提供答复信 |
| resp.no_manuscript | high | 未提供修订稿，声称的修改无从核验 |
| resp.comment_type_unknown | low | 意见类型超出五类词表 |
| resp.comment_type_missing | medium | 意见未分类，行动项不明 |
| resp.severity_unknown | low | 严重度超出三级词表 |
| resp.severity_missing | medium | 意见无严重度，无法排优先级 |
| resp.comment_unanswered | high | 意见无对应答复 |
| resp.subrequirement_unanswered | high | 多段意见只答了一段 |
| resp.response_orphaned | medium | 答复指向不存在的意见 |
| resp.decision_undeclared | high | 答复未声明 accept/partial/reject |
| resp.decision_invalid | medium | 决定超出三词表 |
| resp.tone_missing | medium | 答复未声明语气 |
| resp.tone_invalid | low | 语气超出四词表 |
| resp.rebuttal_without_reason | high | 拒绝或部分接受无理由 |
| resp.change_unspecified | medium | 声称的修改未说明改了什么 |
| resp.change_unlocatable | high | 声称的修改无稿件定位 |
| resp.locator_not_in_manuscript | high | 定位串不出现在交付稿件中 |
| resp.version_mismatch | high | 修改所指版本与交付版本不一致 |
| resp.change_not_verifiable | high | 声称新增的文本未逐字出现在稿件中 |
| resp.evidence_status_missing | high | 补充证据未声明其状态 |
| resp.evidence_status_unknown | low | 证据状态超出三词表 |
| resp.evidence_without_alternative | high | 无法提供的证据无替代方案 |
| resp.evidence_source_missing | medium | 已提供的证据不可溯源 |
| resp.manuscript_unrevised | high | 稿件与声明基线一致而答复信声称已改 |
| resp.declaration_missing | medium | 必备声明（利益冲突/基金/数据可用性/伦理批件）缺席或为空 |
| resp.ethics_decline_without_basis | medium | 拒绝伦理类意见的理由未写明伦理依据 |
| resp.response_duplicated | medium | 同一答复体复用于多条意见——模板化未答复 |
| resp.third_party_unlicensed | medium | 复用的第三方材料缺来源或许可记录——复用条件无法对回 |
| resp.restricted_data_unauthorized | medium | 受限/个人/未公开数据的使用无授权依据 |

### evidence_writing —— 引用纪律（完整规则索引，25 条）

| rule | severity | 证明什么 |
|-|-|-|
| ew.claims_missing | high | 未提供论断清单 |
| ew.draft_missing | high | 未提供稿件文本 |
| ew.evidence_table_missing | high | 未提供证据表 |
| ew.duplicate_source | medium | 两条证据条目同题异键——来源被重复计数 |
| ew.reference_metadata_incomplete | medium | 证据条目缺题名/年份等识别信息 |
| ew.source_type_missing | medium | 条目未声明来源类型 |
| ew.source_type_unknown | low | 来源类型超出四词表 |
| ew.claim_no_id | high | 论断无标识符 |
| ew.claim_id_duplicate | high | 两条论断共享标识符 |
| ew.claim_empty | high | 论断无文本 |
| ew.strength_missing | high | 论断无证据强度标注 |
| ew.strength_invalid | medium | 强度超出三词表 |
| ew.strength_without_basis | high | 强度标注无依据 |
| ew.uncertainty_missing | high | 弱/中强度论断未写不确定性 |
| ew.claim_no_support | high | 论断未挂任何来源 |
| ew.link_no_source | high | 论断-来源链接未写来源键 |
| ew.source_not_in_table | high | 引用了证据表中不存在的键 |
| ew.link_no_quote | high | 链接无原文摘录——引而不证 |
| ew.link_no_locator | high | 引文无页码/章节定位 |
| ew.quote_not_in_source | high | 引文不出现在被引来源中——张冠李戴信号 |
| ew.retracted_source_used | high | 撤稿来源被用作支持 |
| ew.preprint_as_strong | medium | 预印本被用作 strong 论断的支持 |
| ew.claim_not_in_draft | medium | 清单中的论断未进入稿件 |
| ew.draft_overstates_strength | medium | 稿件措辞强于声明的证据强度 |
| ew.source_unused | medium | 证据表条目未支持任何论断 |

### translation —— 双语交付合规（完整规则索引，17 条）

| rule | severity | 证明什么 |
|-|-|-|
| xlate.mode_missing | high | 交付未声明输出形态 |
| xlate.mode_unknown | medium | 输出形态超出三词表 |
| xlate.segments_missing | high | 双语/修订形态无逐段对照 |
| xlate.segment_id_duplicate | high | 段标识重复 |
| xlate.segment_unpaired | high | 段缺一侧文本，可追溯性断裂 |
| xlate.missing_side | high | 单侧文本未提供 |
| xlate.invariant_broken | high | 源侧的数字/单位/引文在目标侧丢失 |
| xlate.invariant_added | high | 目标侧引入源侧没有的数字/单位/引文 |
| xlate.negation_changed | high | 否定词数量两侧不一致——语义可能被翻转 |
| xlate.hedge_strength_changed | high | 目标侧最强限定语级别与源侧不同——限定语被加固或削弱 |
| xlate.number_conversion_unexplained | medium | 万/亿量级换算未留痕 |
| xlate.component_untranslated | high | 声明的部件（图/表/脚注/文献）未进入目标 |
| xlate.untranslated_residue | medium | 目标侧残留源语言字符 |
| xlate.target_not_translated | high | 目标侧与源侧相同 |
| xlate.length_out_of_band | medium | 长度比超出方向化容忍带 |
| xlate.term_variant | medium | 锁定术语以变体形式出现 |
| xlate.term_entry_no_basis | medium | 术语条目未写明依据 |

### format_template —— 投稿要求合规（完整规则索引，30 条）

| rule | severity | 证明什么 |
|-|-|-|
| fmt.spec_missing | high | 模板格式规格未记录 |
| fmt.spec_value_missing | medium | 模板控制的格式字段无值 |
| fmt.conflict_unresolved | medium | 模板条款冲突未记录采用的版本 |
| fmt.guide_version_missing | medium | 作者指南记录未注明版本或日期——合规结论无法对回固定版本 |
| fmt.header_footer_unverified | medium | 声明的页眉页脚项无逐项状态 |
| fmt.section_missing | high | 模板要求的章节缺席 |
| fmt.section_order | medium | 章节顺序与模板不符 |
| fmt.heading_level_skip | medium | 标题层级跳级 |
| fmt.heading_style_unbound | high | 标题未绑定段落样式——只靠字号加粗 |
| fmt.numbering_gap | medium | 章节编号跳号 |
| fmt.toc_not_generated | high | 模板要求目录而未生成 |
| fmt.word_limit_exceeded | medium | 超出字数限制 |
| fmt.citation_not_in_reference_list | high | 正文引用不在文献表中 |
| fmt.reference_never_cited | medium | 文献表条目从未被引用 |
| fmt.reference_style_missing | medium | 未记录引用风格 |
| fmt.unit_lost | high | 转换丢失内容单元（图/表/公式/脚注） |
| fmt.unit_added | medium | 转换引入多余内容单元 |
| fmt.unit_counts_incomplete | high | 内容单元计数只有单侧 |
| fmt.conversion_undocumented | high | 转换步骤未留痕，无法复现 |
| fmt.export_unverified | high | 无导出验证记录 |
| fmt.font_not_embedded | high | 字体未嵌入，版面在他机漂移 |
| fmt.page_size_unverified | high | 页面尺寸未实测 |
| fmt.toc_not_refreshed | high | 目录未刷新，页码失效 |
| fmt.not_editable | high | 交付文件不可编辑 |
| fmt.export_field_missing | medium | 导出属性未报告——未知不等于合格 |
| fmt.page_numbers_unverified | medium | 声明必须页码而导出记录未确认可用 |
| fmt.figure_never_referenced | medium | 图从未被正文引用——装饰而非证据 |
| fmt.crossref_dangling | high | 正文指向不存在的图号 |
| fmt.content_rasterized | high | 导出把内容栅格化——文本不可再编辑 |
| fmt.checklist_incomplete | high | 模板检查单未逐项执行 |

### Failure handling —— 拒绝运行（1 条）

| rule | severity | 发生了什么 |
|-|-|-|
| audit.no_section | high | 案例无法按声明运行：spec 文件缺失或不可读、不是 JSON 对象、未声明 section 或 section 名未知——以 exit 5 拒收并写 status 为 undetermined 的 result.json，绝不抛 traceback；拒收路径只回填 spec 顶层能直接取到的 case_id，不执行契约回显 |

## 输出契约与三段结构映射

引擎级 result.json（writeaudit.py 直接产出）：schema_version、section、status（clean
/ review / blocked / undetermined）、findings[]（每条带 rule、severity、message、
kind、basis、fix 与定位字段——comment_id、location、claim、segment、key、declaration）、
severity_counts、pending（missing_input 类发现的清单，即待复核项）、checked（各
route 实际核查的对象数）、case_id（spec 顶层有则回填，拒收路径亦然）、output_contract
点名的每个键（spec 携带同名值且非大体积输入字段则原样拷入；推导不出则置 null 并在
limits 记一条说明）。

最终交付把引擎 findings 组装进 output_contract 点名的三段结构（字段名用评分口径原词）：

| 输出段 | result.json 键 | 组装来源与完成标准 |
|-|-|-|
| 审查报告 | audit_report[]：每条 {rule, severity, location, finding, basis, suggestion, category} | 由 findings[] 逐条映射；category 按风险面取学术诚信、引用规范、隐私与数据合规、版权与许可、伦理审查、投稿要求；完成标准：材料实际存在的风险面逐项查过 |
| 依据与边界 | evidence_and_boundaries：{manuscript_quotes[], material_evidence[], pending_review[]} | 稿件原文、引用/数据/方法证据与待复核项；完成标准：区分错误、证据不足和建议 |
| 结果状态 | result_status：{pass[], problems[], pending[], not_checked[]} 加 status 与 status_reason | 通过、问题、待复核和未检查项分别列出；完成标准：不凭空补齐缺失信息 |

finding 的 kind 字段即四类判定：norm_problem（规范问题）、fact_mismatch（与交付物
不符的事实断言）、missing_input（证据不足，进 pending 待复核）、advisory（建议性）。
status 映射：clean → 全部通过；review → 有 medium/low 待处理（status_reason 写明待补
什么）；blocked → 有 high（status_reason 列出）；undetermined → 运行失败（写明环节）。
材料缺失、无法判断、运行失败三种情况分开说明。

## 最小调用示例（示例）

输入 examples/spec-contract.json：case_id 为 challenge-de9f0708-case-01，
output_contract 点名 audit_report、evidence_and_boundaries、result_status 三个键；
修订包故意带两处缺陷（必备的 data_availability 声明缺席、意见 C2 无答复）。调用：

```bash
python scripts/writeaudit.py --spec examples/spec-contract.json --out out_example
```

引擎实跑输出（本机实测，节略；exit 4）：

```json
{
  "schema_version": "writeaudit/v1", "section": "review_response", "status": "blocked",
  "case_id": "challenge-de9f0708-case-01",
  "findings": [
    {"rule": "resp.declaration_missing", "severity": "medium",
     "declaration": "data_availability", "kind": "norm_problem",
     "basis": "口径：required_declarations 点名的声明逐项留痕（利益冲突/基金/数据可用性/伦理批件）",
     "fix": "在 declarations 中补齐该声明及其实际内容"},
    {"rule": "resp.comment_unanswered", "severity": "high",
     "comment_id": "C2", "kind": "norm_problem",
     "basis": "口径：审稿意见必须逐条答复",
     "fix": "为该意见补一条带 decision 与 tone 的答复；部分接受需写明理由"}
  ],
  "severity_counts": {"medium": 1, "high": 1},
  "pending": [],
  "checked": {"comments": 2, "responses": 1, "declarations_required": 3},
  "audit_report": null, "evidence_and_boundaries": null, "result_status": null
}
```

三个 contract 键引擎推导不出，置 null 并在 limits 说明——第 6 步由你把 findings 组装
填充（完整形状见 examples/result-example.json，标注为示例，不冒充正式案例结果）。

## Limits

- **引擎审计 spec，不直接读 PDF。** 从实际材料抽取意见、答复、论断、证据表与双语对
  是调用方的工作；抽不到的留空即被报出（待复核），而不是被修好。
- **词表闭合，不猜测。** 类型、决定、语气、严重度、强度、来源类型、证据状态都是上面
  声明的集合；词表外的值是 low/medium 发现（kind 为 advisory），绝不是不端判决。
- **子要求覆盖是词元重合判断。** subrequirement_unanswered 在子请求与答复正文的内容
  词重合低于 20% 时触发——改写得太彻底的合格答复可能漏报；这是留给复核者的缺口，
  不是误判。
- **change_not_verifiable 是逐字包含检验。** "We have added X" 以 added_text 出现在
  稿件中为准；换措辞的修改声明由 manuscript_unrevised（声明基线时）兜住。
- **译文守恒是数字/单位/引文级。** 措辞、语序、语域不在范围；只报可证伪的对（消失的
  数字、翻转的否定、加固的限定语）。单位经同典化（12 h 与 12 小时视为同一事实），
  3 倍与 3-fold 视为等值。
- **声明只查存在与内容留痕，不查真实。** 填了的利益冲突声明仍可能是假的——审计证明
  它存在且非空；内容真实性需要人工核对。
- **长度带是启发式并分方向声明**（zh→en 0.8–3.5，en→zh 0.15–2.0，短文 <200 字符不
  适用）；临界值只是复核信号，不是结论。
- **clean 运行只证明声明口径内的纪律成立。** 它不认证伦理批件本身、图片版权状态或
  来源的真实性——那些需要规则要求在场且可溯源的实物证据。

## 异常处置表

| 形态 / 故障 | 处置 |
|-|-|
| 材料缺页 / 无法解析（扫描件、OCR 噪声） | 置信不足的抽取在 spec 标 missing，对应检查项进 not_checked，相关条目进 pending——不静默跳过 |
| 引用信息不全（无年份/无来源类型） | reference_metadata_incomplete、source_type_missing 照报；引用本身无法核验的条目进 pending |
| 依据条款获取不到（期刊指南拿不到） | format_template 不硬编造条款；在报告中写明指南缺席，投稿要求检查项标未执行——不虚构版本号 |
| 材料涉及受限数据（无法读取原文） | 不读取、不转述受限内容；该风险面写进 not_checked，说明原因 |
| 答复信与稿件版本对不上 | version_mismatch 与 locator_not_in_manuscript 照报；两条合看即版本错位，先修版本再重跑 |
| 稿件超长 | 分章抽取、分块构造 spec、分块跑、合并 findings；每块记录 checked 计数 |
| 译文形态未声明 | mode_missing 报出（进 pending）；先向材料确认形态，绝不假定 plain |
| 数据与答复信冲突 | change_not_verifiable / manuscript_unrevised 照报，不自行裁决哪半正确 |
| spec 不可读 / 非 JSON 对象 / 无 section 名 | exit 5 拒收，仍写 undetermined 的 result.json，绝不抛 traceback |
| section 名不在支持清单 | exit 5——查本文路由表拼写 |
| 同一输出目录重复运行 | 引擎确定性幂等：同 spec 同 findings；重复运行只为复核，不叠加状态 |
| 嵌套字段类型错位（列表给了字符串、条目给了 null） | 引擎拒绝整案运行（exit 5），不猜测意图；修正 spec 后重跑 |
| 材料缺失、无法判断、运行失败 | 三类分别说明：no_comments 等是待复核发现、pending 是不确定性、undetermined 是运行状态——不互相冒充 |
| 学科惯例 / 风格差异 | 不报为缺陷（见 Limits）；确需提示的归 low 建议类 |

## 使用增益与对照方法

- **公平对照**：同一材料版本、相同检查面、相同预算下，不加载本 Skill 的基础 Agent
  与加载后各跑一次，按四个可数项对比：条目可定位率（每条意见有无意见 id/位置/段落
  定位）、依据可核验率（每条判定是否写明所依据的口径或条款）、误报数（风格差异被判
  为违规的条数）、风险面覆盖数（学术诚信、引用规范、隐私与数据合规、版权与许可、
  伦理审查、投稿要求各自查没查）。平台白板是对照基准，不是参赛者答案。
- **增益证据形式**：scripts/bench_writing.py 29 场景——每场景植入一个缺陷或钉住一个
  误报守卫（rr_ethics_ok、ft_guide_ok、各 clean 基线），clean 基线必须零发现；确定性
  引擎重跑同结果，增益可被第三方复跑验证。

## 验证

```bash
python scripts/bench_writing.py  # 29 scenarios: 每条新规则一场景加误报守卫
```

本机 29/29 通过；各 clean 基线必须零发现。

## Requirements

Python 3.9+（3.14 实测）。纯标准库实现，无第三方依赖，无安装步骤。

## 创新增益

本 Skill 相比通用 Agent 的新增能力（每条附能力边界与证据形式）：

1. **依据与建议随发现下发**：每条 finding 自动携带 basis（判定所依据的口径）与 fix
   （可执行的处置动作），四类判定 kind（规范问题/事实不符/证据不足/建议性）把"错误、
   证据不足、规范问题和建议性意见"分开——交付的是可交办清单，不是泛泛提醒。
   *边界*：依据是本文件声明的口径，不自动引用外部条款原文。
   *证据形式*：bench 每条 finding 断言 basis/fix/kind 字段存在（见示例输出）。
2. **修改声明的落地检验**：定位逐字包含检验（locator_not_in_manuscript）、新增文本
   逐字包含检验（change_not_verifiable）、版本一致性（version_mismatch）、基线比对
   （manuscript_unrevised）四层合围——"说改了"必须能被文件证实。
   *边界*：逐字匹配，轻微改写的修改声明会报出——这是设计行为，逼修改真正落地。
   *证据形式*：bench rr_unlocated 场景；示例 spec 中修改与稿件逐字对齐故 clean。
3. **闭环词表与误报抑制**：全部类型/决定/语气/严重度/强度/来源类型/证据状态词表闭合
   且显式声明；词表外只报 advisory；伦理类意见的拒绝必须带伦理依据关键词，模板化
   重复答复被点名——把"风格误判为不端"和"模板化未答复"两头都按住。
   *边界*：伦理依据是词元级判断（委员会/批件/知情同意等词出现与否），语义级辩护需
   人工复核。
   *证据形式*：bench rr_ethics_ok（正当拒绝零发现）与 rr_boilerplate（模板复用即报）。
4. **双语保真的可计算守恒**：数字/单位/引文/交叉引用四类守恒比对（单位同典化、量级
   换算豁免带留痕）、否定计数比对、五级限定语强度比对——每个守恒都是一条可证伪的
   断言，而不是"翻译腔"式的主观判断。
   *边界*：守恒是计数级，语序与语域不在范围；换算留痕可豁免合法的量级改写。
   *证据形式*：bench tr_dropped_num、tr_unit_changed 场景（丢失即报，守恒即静默）。

## 生态贡献

- **使用说明**：本文件含完整调用步骤（六步运行时入口与 Workflow）、输入输出解释
  （输出契约与三段结构映射）、关键方法（规则库与误报口径）、适用场景（路由表）、
  限制（Limits）、失败处理（Failure handling 与异常处置表）和自查方法（验证一节）。
- **依赖与配置**：Python 3.9+ 纯标准库、无第三方依赖、无安装步骤；必备声明经
  required_declarations 配置，术语锁经 glossary 配置，换算豁免经 conversions 配置。
- **示例（标注为示例）**：examples/ 四个 route 的最小 spec 加 contract 化输入
  spec-contract.json；result-example.json 是标注为示例的示意输出——不冒充正式案例
  结果。
- **检查清单可复用**：103 条规则（resp 30、ew 25、xlate 17、fmt 30、audit 1）每条带
  id、severity、kind 与"证明什么"，可直接当作合规 checklist 人工使用。
- **bench 回归门**：27 场景独立复跑（python scripts/bench_writing.py），改动引擎后
  必须全过——是他人验证本 Skill 行为的最短路径。
- **适用范围与不适用**：修订包、引用纪律、双语交付与投稿要求的合规审查；不负责润色
  改写、代写代投、数据重新分析、法务或伦理委员会正式意见（路由表末行明确拒识）。
- **失败处理**：拒收路径（exit 5 加 undetermined result.json，绝不 traceback）与
  14 行异常处置表覆盖扫描件、缺指南、超长、冲突、类型错位等常见故障。
- **维护信息**：规则 id 变更须同步本文规则表；bench 全过是合并条件；引擎内注释记录
  每条被移除规则的历史教训（避免回归）。
