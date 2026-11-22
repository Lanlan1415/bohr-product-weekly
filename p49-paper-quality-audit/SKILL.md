---
name: paper-quality-audit
description: >
  论文质量审查：把"这篇稿子哪里有问题"变成一组可定位、可核对、可交办的问题条目，
  而不是一段评语。三道审查面覆盖期刊论文与学位论文：draft-and-citation pass（正文
  论断与材料/文献逐条对照、摘要-正文-图表数值一致、声明齐备、术语统一、章节齐备且
  顺序正确）、structure-logic pass（研究问题-论证链-结论闭环、诊断证据必须真实存在
  于稿件原文、每条发现可定位可执行）、longdoc pass（学位论文章章衔接：大纲 vs 已写
  章节、跨章术语与符号、章际矛盾、交叉引用、修改留痕）。每条发现带规则 id、严重度
  与原文定位，确定性引擎保证同一稿子两次运行得到同一份清单。Use when a task asks
  for 论文质量审查, 稿件质量审查, 结构与论证链审查, 学术规范审查, or a
  pre-submission quality check of a manuscript.
---

# paper-quality-audit（论文质量审查）

一份质量审查最容易输在这些地方，而每一种都"看起来完成了"：

- 交回来的是概括——"本文结构完整、论证较充分"——没有条目、没有定位；
- 说"引用不支持观点"，却不给句子、不给文献、不给文献实际主张；
- 把风格偏好判成结构缺陷，把真正的缺口写成建议；
- 摘要与正文数字不一致，没有人查；
- 某节、某声明、某修改记录缺失时被静默跳过，清单看起来完整，一半检查根本没跑。

每一条都可以对稿件的结构化读取做机械判定，所以每一条在这里都是规则。引擎不评 prose
好坏——它审计抽取出的结构化 spec，因此同一份稿子永远产出同一批发现、同一形状。

## 六步运行时入口（Harbor）

运行时原始输入固定为 `/input/case.json` 与 `task.md`；中间产物写 `/app/work`，最终
结果写 `/app/output`。依序执行：

- **第 0 步·读案例**：读 `/input/case.json`，取 `case_id` 与 `output_contract`（结果
  必须保留的字段清单），再按 `task.md` 指向的路径读**实际稿件文件**（PDF/文本/图）。
  读实际文件，不按文件名或领域标签猜内容——实际输入文件和原论文是事实依据。
- **第 1 步·判形态路由**：按下方「任务措辞与形态 → 路由」决策表选 section；全文质量
  审查跑 paper_draft 加 structure_logic 两道并合并，学位论文跑 longdoc。
- **第 2 步·先产出目标产物**：先把审查单本身（逐条问题、位置、严重度、依据、建议）
  写进 `/app/work` 作为中间交付——预算有限时先有诚实的不完整清单，再增量补齐。
- **第 3 步·构造 spec**：把稿件结构化抽取成所选 route 的 spec 字段（见 Workflow 第
  1 步的字段表）。抽不到的字段留空并标注 missing——抽取缺口会变成 finding，绝不静默
  跳过，也绝不编造字段值去"喂饱"规则。
- **第 4 步·审计**：跑 `scripts/secrun.py`，得 findings 与 result.json。
- **第 5 步·修发现重跑**：逐条回原文复核 findings——证据引用错的重抽；抽取缺口补
  spec 后重跑；确认是引擎口径内误报的按 Limits 处理并在报告中说明，不删条目。
- **第 6 步·合并 result.json**：写 `/app/output/result.json`——回填 case_id 与
  output_contract 点名的每个字段（三段结构映射见下），引擎的 findings、
  severity_counts、checked、limits 原样保留作为操作证据。

## 任务措辞与形态 → 路由

| 任务措辞 / 案例形态 | 跑什么 | 审什么 |
|-|-|-|
| 论文质量审查 / 稿件质量审查 / pre-submission quality check | `--section paper_draft` | 正文论断 vs 材料与文献、摘要-正文-图表一致、声明齐备、术语统一、章节齐备且有序（规则 pd.*） |
| 结构与论证链审查 / argument chain / 逻辑一致性 | `--section structure_logic` | 研究问题-论证链-结论闭环、诊断证据落地、建议可执行（规则 struct.*） |
| 学位论文 / thesis / 学期论文（有 chapters 与 outline） | `--section longdoc` | 大纲 vs 章节、前后件、跨章术语与符号、章际矛盾、交叉引用、修改留痕（规则 long.*） |
| "全文质量审查"无明确子项 | paper_draft 与 structure_logic 双跑 | 合并两份 findings，按稿件位置排序 |
| 事实核验 / 数值一致性（摘要、正文、图表、材料互对） | `--section paper_draft` | 其数值规则即覆盖：value_not_in_materials、abstract_result_conflict、figure_caption_mismatch |
| 引用支持 / citation support | `--section paper_draft` | 引用在表、主题相配、作者-年份引用同权解析 |
| 学术规范 / declarations / 可发表性 | `--section paper_draft` | 四项声明、DOI、修改记录存在性 |
| 结论是否回应引言问题 / 贡献是否落地 | `--section structure_logic` | conclusion_missing、contribution_unanchored、conclusion_exceeds_scope |
| 章节层级 / 顺序 / 缺失 | `--section paper_draft` | sections_missing 加顺序检查 |
| 跨章术语、章际矛盾、交叉引用（长文档） | `--section longdoc` | terminology、conclusion_contradiction、dangling_crossref |
| 审稿意见分解、作者/机器文本声明（thesis） | `--section longdoc` 加 `track_consistency: true` | feedback_not_decomposed、authorship_undeclared |
| 润色改写 / 翻译 / 查重 / 排版类请求 | 不属本 Skill | 明确说明边界，不产出审查单 |

## Workflow

### 第 1 步·抽取结构化 spec

读实际稿件（及案例随附的材料/文献/图），为所选 route 写 spec。引擎审计你抽出的东西。

paper_draft spec —— 每个字段被哪些规则消费：

| 字段 | 消费者 |
|-|-|
| draft（或 text） | 全部逐句规则 |
| abstract | 摘要-正文数值一致 |
| design | experimental / observational / correlational，门控因果措辞检查 |
| template → sections | 必备章节，如 ["introduction", "methods", "results"] |
| materials[] | {id, locator, text}——出处索引；正文 {M1} 标记指向这里 |
| references[] | {key, authors, year, journal, topic, doi, needs_doi}——[key] 与作者-年份引用都指向这里 |
| terminology[] | {preferred, variants}——可选项，声明后启用术语一致性检查 |
| figures[] | {id, caption, values, number} |
| declarations | {data_availability, author_contributions, competing_interests, funding} |
| change_log | 修改留痕 |

structure_logic spec：

| 字段 | 消费者 |
|-|-|
| manuscript_text | 证据落地检查的对照文本 |
| research_question | 必须存在且与正文措辞重叠 |
| design, conclusion, limitations | 结论口径检查（结论缺席本身即 finding） |
| contributions[] | {claim, anchor}——anchor 必须出现在正文 |
| paragraphs[] | {id, section, text, claims[]}，claim 带 {claim, support, strength, support_strength} |
| diagnosis[] | {id, dimension, finding, evidence, locator, severity}——dimension 六选一 |
| suggestions[] | {for_finding, action} |

longdoc spec：

| 字段 | 消费者 |
|-|-|
| chapters[] | {number, title, outline_id, argument_element, claims[], conclusions[], definitions[], changelog[], crossrefs[], figure_refs[]} |
| outline[] | {id, title, argument_element, word_budget?} |
| front_matter | {toc, figure_list, reference_section, appendix} |
| terminology[], symbols[], references[], figures[] | 术语表、符号表、引用与图检查 |
| track_consistency | 可选 true——启用四个 opt-in 一致性规则 |
| reviewer_feedback[] | 配合 track_consistency：每条意见须分解为带 status 的 actions[] |

抽不到的字段标 missing/留空加注——规则会报出缺席而不是假定没问题。绝不编造值。

### 第 2 步·运行

```bash
python scripts/secrun.py --spec spec.json --out /app/output --section paper_draft
python scripts/secrun.py --spec spec.json --out /app/output --section structure_logic
```

退出码：0 clean，3 review，4 blocked（有 high finding），5 undetermined（拒绝运行
——见 Failure handling）。每次运行向 out 目录写 result.json。确定性引擎：同一 spec
重跑得到同一份 findings。

### 第 3 步·交付

result.json 含 case_id、section、status、findings[]、severity_counts、checked、limits
以及 output_contract 点名的字段。把两道 pass 的 findings 合并成一份按稿件位置排序的
条目清单；每条 finding 自带定位（句子序号、material/figure/chapter id、value），保持
附着。引擎判不了的事项（抽取不可能、原文歧义、材料读不出）在报告中标待复核——不编
造判定，不悄悄丢条目。

## 规则库

### paper_draft —— 正文、引用、图、声明（完整规则索引，23 条）

| rule | severity | 证明什么 |
|-|-|-|
| `pd.draft_missing` | high | 没有提供正文，无稿可审 |
| `pd.sections_missing` | high | 学科模板要求的章节在正文中缺席 |
| `pd.section_order_wrong` | medium | 必备章节出现顺序与模板不符——层级被打乱 |
| `pd.declaration_missing` | medium | 四项必备声明之一缺失 |
| `pd.materials_missing` | high | 无材料索引，任何事实论断都无法溯源 |
| `pd.material_no_locator` | high | 材料无位置，引用它的论断无法核验 |
| `pd.material_unknown` | high | 正文引用了索引中不存在的材料 |
| `pd.material_unused` | medium | 索引中的材料没有任何句子引用 |
| `pd.uncited_claim` | high | 断言句无引用无材料锚点，读者无法核对 |
| `pd.unknown_source` | high | 引用了文献表中不存在的文献（方括号键与作者-年份两种写法同权） |
| `pd.citation_mismatch` | medium | 被引文献与句子主题重合低于 15%——装饰性引用信号 |
| `pd.citation_padding` | low | 一句挂四条以上引用——通常是凑数 |
| `pd.trend_as_causation` | high | 观察性研究使用因果措辞 |
| `pd.value_not_in_materials` | high | 正文数值不在其引用的材料中 |
| `pd.figure_caption_missing` | high | 图无题注 |
| `pd.figure_caption_mismatch` | high | 图数据中的值不在题注里——图文不一致 |
| `pd.figure_uncited` | medium | 图备好了但正文从未提及 |
| `pd.figure_numbering_gap` | medium | 图编号跳号——疑似删图后未同步 |
| `pd.abstract_result_conflict` | high | 摘要中的数值不在正文出现——两半不一致 |
| `pd.term_variant_used` | medium | 术语的已声明变体出现在正文——同一概念两种写法 |
| `pd.reference_metadata_incomplete` | medium | 文献缺作者/年份/期刊等识别信息 |
| `pd.reference_no_doi` | low | 声明需要 DOI 的文献没有 DOI |
| `pd.change_log_missing` | medium | 无修改记录，修订轨迹丢失 |

### structure_logic —— 论证链与结构诊断（完整规则索引，25 条）

| rule | severity | 证明什么 |
|-|-|-|
| `struct.no_manuscript` | high | 正文与段落都未提供 |
| `struct.research_question_missing` | high | 无明确研究问题 |
| `struct.question_absent_from_text` | high | 研究问题与正文措辞几乎不重叠 |
| `struct.conclusion_missing` | high | 有研究问题但没有结论——引言提出的问题没有被回应 |
| `struct.contribution_unanchored` | high | 声称的贡献未锚定到交付它的章节 |
| `struct.contribution_anchor_unknown` | medium | 贡献指向正文不存在的位置 |
| `struct.no_diagnosis` | high | 未提供结构诊断——交付物缺失 |
| `struct.dimension_missing` | high | 六个必查维度有缺 |
| `struct.dimension_unknown` | low | 诊断维度超出任务定义的六维 |
| `struct.finding_no_evidence` | high | 发现不引用原文——无法与想象出的缺陷区分 |
| `struct.evidence_not_in_text` | high | 发现所引文本在稿件中不存在——疑似编造 |
| `struct.finding_no_locator` | high | 发现无章节/段落/页定位 |
| `struct.style_as_defect` | high | 风格偏好被报成结构缺陷 |
| `struct.suggestion_missing` | high | 实质性发现无修改建议 |
| `struct.suggestion_no_action` | high | 建议无可执行动作（移/合/拆/删/增） |
| `struct.suggestion_orphaned` | medium | 建议指向不存在的发现 |
| `struct.multiple_claims` | medium | 一段承载多个论点 |
| `struct.orphan_paragraph` | medium | 段落无论点——装饰性段落 |
| `struct.claim_without_support` | high | 论点无支持指针（引用/图/表/段落） |
| `struct.circular_support` | high | 论点由同一大纲中的另一论点支持——自我循环 |
| `struct.support_weaker_than_claim` | high | 证据弱于它被要求承载的论点 |
| `struct.duplicate_paragraph` | medium | 两段内容高度重复 |
| `struct.section_interleaved` | medium | 章节中断后恢复——疑似块错位 |
| `struct.conclusion_exceeds_scope` | high | 结论使用了设计无法支持的因果措辞 |
| `struct.limitations_missing` | medium | 有边界性结论却全文无局限说明 |

### longdoc —— 学位论文章章一致性（完整规则索引，32 条）

| rule | severity | 证明什么 |
|-|-|-|
| `long.no_chapters` | high | 未提供章节 |
| `long.outline_item_unwritten` | high | 大纲条目无对应章节——计划与文档不符 |
| `long.chapter_not_in_outline` | medium | 章节映射到不存在的大纲条目 |
| `long.argument_element_missing` | high | 论证的一段（问题/方法/结果/讨论/局限）无章承载 |
| `long.reference_section_missing` | medium | 无参考文献部分 |
| `long.figure_list_missing` | medium | 无插图清单 |
| `long.appendix_missing` | medium | 未声明附录 |
| `long.terminology_missing` | high | 无术语表——同一概念可被写成两种样子 |
| `long.symbol_table_missing` | medium | 无符号表 |
| `long.term_variant_declared` | low | 术语声明了变体 |
| `long.duplicate_definition` | medium | 同一术语在两章定义 |
| `long.claim_no_citation` | high | 章内论断未绑定引用 |
| `long.citation_unknown` | high | 章内引用了文献表之外的文献 |
| `long.citation_conclusion_mismatch` | high | 被引文献与论断主题几乎不重叠 |
| `long.questionable_citation` | medium | 重合度 15%-35%——疑似二手引用，需人工复核 |
| `long.conclusion_contradiction` | high | 两章对同一事项给出相反结论 |
| `long.numbering_unreadable` | medium | 章号非整数，编号无法核对 |
| `long.numbering_gap` | high | 章号不是 1..n——缺章或重号 |
| `long.dangling_crossref` | high | 交叉引用指向不存在的章 |
| `long.figure_numbering_gap` | medium | 图编号不是 1..n |
| `long.figure_ref_unknown` | high | 正文指向文档中不存在的图号 |
| `long.definition_unused` | medium | 定义未被任何后续章节使用 |
| `long.toc_incomplete` | medium | 目录漏掉已存在的章 |
| `long.no_chapter_changelog` | medium | 章无修改历史 |
| `long.change_no_reason` | medium | 修改条目只说改了什么不说为什么 |
| `long.change_impact_untraced` | medium | 修改涉及他章定义的术语但未列出波及章 |
| `long.word_budget_unmeasured` | low | 声明了字数预算但未记录实际字数 |
| `long.word_budget_off` | medium | 实际字数偏离预算 40% 以上——论证失衡信号 |
| `long.chapter_no_question` | medium | opt-in：章未声明它回答什么问题 |
| `long.authorship_undeclared` | medium | opt-in：章未声明作者撰写还是机器生成 |
| `long.feedback_not_decomposed` | high | opt-in：审稿意见未分解为可跟踪动作 |
| `long.action_no_status` | medium | opt-in：动作项无状态 |

### Failure handling —— 拒绝运行（1 条）

| rule | severity | 发生了什么 |
|-|-|-|
| `audit.no_section` | high | 案例无法按声明运行：spec 文件缺失或不可读、不是 JSON 对象、未声明 section 或 section 名未知——以 exit 5 拒绝并写 status undetermined 的 result.json，绝不抛 traceback |

## 输出契约与三段结构映射

引擎级 result.json（secrun.py 直接产出）：schema_version、section、status（clean /
review / blocked / undetermined）、findings[]（每条带 rule、severity、message 与定位
字段——句子序号、material/figure/chapter id、value）、severity_counts、checked（含
检查的句数或条目数）、case_id（spec 顶层有则回填）、output_contract 点名的每个键
（spec 携带同名值则原样拷入；大体积输入字段除外；推导不出则置 null 并在 limits 记
一条说明）。

最终交付把引擎 findings 组装进 output_contract 点名的三段结构（字段名用评分口径原词）：

| 输出段 | result.json 键 | 组装来源与完成标准 |
|-|-|-|
| 审查报告 | audit_report[]：每条 {rule, severity, location, finding, basis, suggestion, category} | 由 findings[] 逐条映射；category 取六类检查项（事实核验、引用支持、方法设计、统计报告、论证链、学术规范）；完成标准：相关检查项都查过 |
| 依据与边界 | evidence_and_boundaries：{manuscript_quotes[], material_evidence[], pending_review[]} | 稿件原文引用、材料/数据/方法证据、待复核项；完成标准：区分错误、证据不足和建议 |
| 结果状态 | result_status：{pass[], problems[], pending[], not_checked[]} 加 status 与 status_reason | 通过、问题、待复核和未检查项分别列出；完成标准：不凭空补齐缺失信息 |

status 映射：clean → 全部通过；review → 有 medium/low 待处理（status_reason 写明待补
什么）；blocked → 有 high（status_reason 列出）；undetermined → 运行失败（写明环节）。
材料缺失、无法判断、运行失败三种情况分开说明。

## 最小调用示例（示例）

输入 `examples/spec-contract.json`：case_id 为 challenge-0999879e-case-01，
output_contract 点名 audit_report、evidence_and_boundaries、result_status 三个键，
稿件故意带三处缺陷（引用不在文献表、摘要 9-fold 与正文 three-fold 冲突、声明要 DOI
的文献缺 DOI）。调用：

```bash
python scripts/secrun.py --spec examples/spec-contract.json --out out_example
```

引擎实跑输出（本机实测，节略）：

```json
{
  "schema_version": "secrun/v1", "section": "paper_draft", "status": "blocked",
  "findings": [
    {"rule": "pd.unknown_source", "severity": "high", "sentence": 2, "key": "roe2021"},
    {"rule": "pd.abstract_result_conflict", "severity": "high", "value": 9.0},
    {"rule": "pd.reference_no_doi", "severity": "low", "key": "doe2020"}
  ],
  "severity_counts": {"high": 2, "low": 1},
  "checked": {"section": "paper_draft", "items": 7},
  "case_id": "challenge-0999879e-case-01",
  "audit_report": null, "evidence_and_boundaries": null, "result_status": null
}
```

三个 contract 键引擎推导不出，置 null 并在 limits 说明——第 6 步由你把 findings 组装
填充（完整形状见 `examples/result-example.json`，标注为示例，不冒充正式案例结果）。

## Limits

- **引擎审计 spec，不直接读 PDF。** 从实际稿件抽取章节、句子、材料与文献是调用方的
  工作；抽取错了会被报出（或被证据落地规则拒绝），而不是被修好。
- **主题重合是词汇级判断。** citation_mismatch 在文献主题与句子内容词重合低于 15%
  时触发——改写得太彻底的相配引用可能漏报；重合度临界只是待复核信号，不是结论。
- **uncited_claim 读断言标记。** 带模糊限制语的句子（may contribute）不要求引用；
  措辞软到无标记触发的论断不报。
- **数值检查跳过统计量与章节号。** p 值、检验统计量、样本量不要求出现在材料中——
  只查测量值；摘要-正文一致检查同理。
- **声明只查存在，不查真实。** 填了的利益冲突声明仍可能是假的——审计证明它存在。
- **作者-年份解析是姓名级。** 姓名+年份与文献表匹配成功即视为已引用；同名不同人、
  姓氏缩写差异需要人工复核。
- **longdoc opt-in 规则**（chapter_no_question、authorship_undeclared、
  feedback_not_decomposed、action_no_status）只在 spec 声明 track_consistency 为
  true 时触发。
- **不评 prose 质量。** 风格、措辞、行文不在范围；诊断里的风格意见会被
  struct.style_as_defect 点名，而不是被产出。
- **学科惯例与期刊格式差异不报为缺陷。** 引用风格混杂（方括号与作者-年份并存）是
  常态，引擎两种都识别；确属规范问题的条目归 low 并写明依据。

## 异常处置表

| 形态 / 故障 | 处置 |
|-|-|
| 扫描 PDF / OCR 噪声大 | 置信降低的抽取在 spec 标 missing，对应检查项进 not_checked，报告 pending——不静默跳过 |
| 图读不出 / 图表数据缺失 | figures 留空加注；figure 类规则不跑，结果状态写未检查 |
| 参考文献表抽不出 | references 为空会使引用类发现密集报出——在 status_reason 说明这是抽取缺口而非稿件缺陷，并重抽 |
| 稿件超长 | 分章抽取、分块构造 spec、分块跑、合并 findings；每块记录 checked.items |
| 数据与结论冲突 | abstract_result_conflict / value_not_in_materials 照报，不自行裁决哪半正确 |
| 原文表述歧义 | 相关条目标 pending_review，写明歧义点，不强行判定 |
| 引用风格混杂 | 引擎方括号与作者-年份同权解析——不需为此改稿，也不报缺陷 |
| spec 不可读 / 非 JSON 对象 / 无 section 名 | exit 5 拒绝，仍写 undetermined 的 result.json，绝不抛 traceback |
| section 名不在支持清单 | exit 5——查本文路由表拼写 |
| 同一输出目录重复运行 | 引擎确定性幂等：同 spec 同 findings；重复运行只为复核，不叠加状态 |
| 材料缺失、无法判断、运行失败 | 三类分别说明：materials_missing 是发现、pending 是不确定性、undetermined 是运行状态——不互相冒充 |
| 期刊格式 / 学科惯例差异 | 不报为缺陷（见 Limits）；确需提示的归 low 建议类 |

## 使用增益与对照方法

- **公平对照**：同一稿件版本、相同检查项、相同预算下，不加载本 Skill 的基础 Agent
  与加载后各跑一次，按四个可数项对比：条目可定位率（每条意见有无句子/图表/章节定位）、
  证据可核验率（引用的原文是否真实存在）、误报数（学科惯例被判为缺陷的条数）、六检查
  项覆盖数（事实核验、引用支持、方法设计、统计报告、论证链、学术规范各自查没查）。
  平台白板是对照基准，不是参赛者答案。
- **增益证据形式**：`scripts/bench_draft.py` 35 场景 + `scripts/bench_sections.py`
  55 场景——每场景植入一个缺陷或钉住一个误报守卫，clean 基线必须零发现；确定性引擎
  重跑同结果，增益可被第三方复跑验证。

## 验证

```bash
python scripts/bench_draft.py     # 35 scenarios: 每规则一场景加误报守卫
python scripts/bench_sections.py  # 55 scenarios: 跨 section 回归加误报守卫
```

本机全部通过；两个 bench 的 clean 基线必须零发现。

## Requirements

Python 3.9+（3.14 实测）。纯标准库实现，无第三方依赖，无安装步骤。

## 创新增益

本 Skill 相比通用 Agent 的新增能力（每条附能力边界与增益证据形式）：

1. **可定位条目化清单**：每条发现带规则 id、严重度、定位字段（句子序号、材料/图/章
   id、值）——交付的是可交办清单，不是整篇评语。
   *边界*：定位粒度到句/行/图/章，不到字符偏移。
   *证据形式*：bench 每条 finding 断言其定位字段存在。
2. **引用主张逐条对照**：方括号键与作者-年份两种引用风格同权解析；引用在表检查、
   主题重合检查、正文数值与材料对账、摘要-正文-图表三方一致。
   *边界*：主题重合是词汇级；统计量豁免（p 值不进材料对账）。
   *证据形式*：bench author_year_resolved / author_year_unknown / value_not_in_materials
   等场景。
3. **反造假证据检查**：结构诊断引用的原文必须真实存在于稿件
   （struct.evidence_not_in_text），数值必须能回到材料（pd.value_not_in_materials），
   贡献必须锚定到真实位置——把"想象出的缺陷"挡在清单外。
   *边界*：逐字包含匹配，轻微改写的引用会被拒——这是设计行为，逼重抽。
   *证据形式*：bench fp 守卫（正确引用保持安静）与缺陷场景（编造证据即报）。
4. **误报抑制的可计算守卫**：统计量豁免、材料锚点归因（{M} 标记即视作已溯源）、
   方法段不强制材料锚点、标识符注解容忍（带括号注解的键/图号照常解析）——每条守卫
   都是 bench 里一个必须保持安静的 FP 场景。
   *边界*：守卫是词汇级启发，边界情形以 Limits 口径人工复核。
   *证据形式*：bench 中 18 个 fp_ 前缀场景全部零发现。

## 生态贡献

- **使用说明**：本文件含完整调用步骤（六步运行时入口与 Workflow）、输入输出解释
  （输出契约与三段结构映射）、关键方法（规则库与误报口径）、适用场景（路由表）、
  限制（Limits）、失败处理（Failure handling 与异常处置表）和自查方法（验证一节）。
- **依赖与配置**：Python 3.9+ 纯标准库、无第三方依赖、无安装步骤；模板章节经
  template 配置，术语表经 terminology 配置，opt-in 规则经 track_consistency 配置。
- **示例（标注为示例）**：examples/ 三个 route 的最小 spec 加 contract 化输入
  spec-contract.json；result-example.json 是标注为示例的示意输出——不冒充正式案例
  结果。
- **检查清单可复用**：81 条规则（pd 23、struct 25、long 32、audit 1）每条带 id、
  severity 与"证明什么"，可直接当作审稿 checklist 人工使用。
- **bench 回归门**：两个 bench 共 90 场景，独立复跑（python scripts/bench_draft.py
  等），改动引擎后必须全过——是他人验证本 Skill 行为的最短路径。
- **适用范围与不适用**：论文与学位论文的质量、引用、事实、结构、规范审查；不负责
  润色改写、翻译、查重、投稿排版（路由表末行明确拒识）。
- **失败处理**：拒绝运行路径（exit 5 加 undetermined result.json）与 12 行异常处置
  表覆盖扫描件、缺文献表、超长、冲突、歧义等常见故障。
- **维护信息**：规则 id 变更须同步本文规则表；bench 全过是合并条件；引擎内注释记录
  每条被移除规则的历史教训（避免回归）。
