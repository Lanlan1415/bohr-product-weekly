---
name: paper-quality-audit
description: >
  论文质量审查：先对问题重要性、创新、设计、数据、分析、结果、论证、写作、引用、
  复现、伦理合规十一维逐维形成有原文证据的评价，再按严重度汇总实质问题与总体分级；
  绝不以低严重度模板问题代替审查。每条评价和 issue 带原句、定位、判断依据、缺陷类型
  和可执行建议，审稿证据逐字回查，设计—问题错配、因果越界、数值冲突等可判定问题由
  确定性引擎复核。仍保留 paper_draft / structure_logic / longdoc 三套历史高分规则。
  Use when a task asks for 论文质量审查、稿件质量审查、pre-submission quality review、
  可发表性证据审查；不要用于翻译、润色、查重、排版或直接替代期刊录用决定。
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

## 主工作流：十一维证据化审查（v2，正式案例优先）

不能只看模板是否填完。内容正确性来自**真实通读与逐维判断**；脚本负责强制证据落地、
数值重算、误报门控、稳定分级和契约完整性。`examples/spec-quality.json` 是明确标注的
本地输入示例，不是组织方案例或预制答案。

### 第 0–2 步：读原稿并先保存诚实的部分审查

1. 读取 `/input/case.json`、`task.md` 和实际稿件/图表/附件，保留 `case_id`、
   `output_contract`、稿件版本与来源路径。只允许从实际输入判断研究内容。
2. PDF 优先使用环境提供的 PDF 文本工具；也可让 `qualityrun.py` 惰性调用
   PyMuPDF → pypdf → pdftotext。扫描页没有文字层时必须进入 `limits` 与
   `pending_review`，不能把 OCR 失败写成论文缺陷。
3. 在 `/app/work` 先保存当前十一维审查单；缺页或读不到的维度标 `not_assessed`，
   不为凑齐表格而编造评价。再逐段回查、补充实质发现。

### 第 3 步：逐维形成 assessment，而不是套缺陷模板

在 spec 中写 `manuscript_text`（或 `manuscript_path`）、`source_scope`、
`manuscript_version` 和 `quality_assessments[]`。十一维必须逐一出现：

| dimension | 需要真正判断什么 | 至少寻找的原稿证据 |
|-|-|-|
| problem_importance | 问题是否明确、重要、范围可回答 | 研究问题、意义、空白/需求原句 |
| innovation | 新在何处，与最近工作相比是否真的不同 | 贡献声称 + 先行工作/基线对照 |
| design | 设计能否回答问题，对照/单位/偏倚控制是否成立 | 设计、抽样、分组、主要终点 |
| data | 来源、独立单位、选择/排除、数量账目是否一致 | 数据来源、样本流、版本、纳排 |
| analysis | 指标/模型是否合适，假设、效应与不确定性是否可解释 | 模型、变量类型、假设、CI |
| results | 主要结局是否完整，文/图/表数值是否一致 | 效应、精度、精确 p、图表定位 |
| argumentation | 假设—证据—结论是否闭合，外推/因果是否越界 | 核心论断、支持、局限、结论 |
| writing | 结构与术语是否服务论证（不是润色打分） | 章节、交叉引用、术语/序号 |
| citations | 引用是否可解析且支持对应论断 | 论断原句与文献主张的对应证据 |
| reproducibility | 独立读者能否重跑并比较结果 | 数据/代码版本、命令、环境、参数、容差 |
| ethics_compliance | 伦理、知情同意、隐私、利益冲突、许可声明是否适用且充分 | 实际声明与适用性依据；不适用须说明理由 |

每个 assessment 的形状：

```json
{
  "dimension": "design",
  "rating": "adequate | minor_concern | major_concern | not_applicable | not_assessable",
  "rationale": "有界的实际判断，不是固定祝福或模板罪名",
  "evidence": ["必须与 manuscript_text 逐字一致的原句（允许空白差异）"],
  "concerns": [{
    "finding": "具体实质问题",
    "severity": "high | medium | low",
    "evidence_quote": "触发该判断的原文；报告缺口可省略",
    "basis": "为什么该证据支持这个判断；缺证据缺口须写清查过的范围",
    "defect_class": "method_defect | numeric_inconsistency | reporting_gap | suggestion",
    "suggestion": "可由作者执行且不编造事实的修复"
  }]
}
```

严重度锚点：`high` = 改变主要结论可信度/使关键分析无效/账目或因果矛盾；
`medium` = 影响解释或复核的重要报告缺口；`low` = 不改变主要结论的局部改进。
`method_defect` 需要正证据；仅“没有写”必须归为 `reporting_gap` 并有检索范围，绝不
升级为“研究没做”。`scope=review_process` 表示审查自身未完成或证据伪造，不污染论文
severity_counts。可声明某维 `not_applicable`，但需 rationale；无证据评级会触发
`pqa.assessment_without_evidence`。

### 第 4 步：构造可机械复核的字段，并运行旧规则（适用时）

- `research_question_type` + `design`：仅在二者明确时检查设计—问题匹配；观察性研究不是
  自动缺陷，但观察性设计 + 明确因果结论是实质问题。
- `controls`、`recruited_n`、`analysed_n`：对照与样本账目；分析数大于入组数实际计算差值。
- `reported_values[]`：`{name,value,comparator_value,tolerance,quote}`，引擎真实计算差值
  并与声明容差比较；缺任意数值就写 `not_computable`，不编造。
- `data_availability` / `code_availability` / `ethics_statement` / `competing_interests`：
  原稿里已有声明就无需重复构造；只有 full_article 或明确适用时才触发缺口。
- `legacy_sections: ["paper_draft", "structure_logic", "longdoc"]`：当选中的旧输入字段
  已从原文忠实抽取时才运行。尤其是 `structure_logic.diagnosis[]` 是**旧审查输出结构**，
  不应凭空白论文自动生成；不满足前置字段时不要硬跑留待新 assessment 判断。
  旧 findings 原样保留 rule/severity/定位并映射到十一维，能力不回退。

### 第 5 步：运行并逐条回原文核对

```bash
python scripts/qualityrun.py --case /input/case.json --out /app/output
# 若稿件单独传入：
python scripts/qualityrun.py --case /input/case.json --manuscript /input/manuscript.pdf --out /app/output
# 本地等价输入：
python scripts/qualityrun.py --spec examples/spec-quality.json --out out_quality
```

退出码 0=clean，3=review（次要问题或审查未完成），4=blocked（实质 high 或伪造审查
证据），5=undetermined（输入不可运行）。只有成功完成内容审查且没有机械 finding 才可为
clean；十一维 assessment 缺失会得到 `review_incomplete`，不是“论文只有 medium 缺陷”。

### 第 6 步：复核并交付全字段 result.json

1. 对每个 `pqa.review_evidence_not_in_source` 修正原句并重跑，不能保留伪造证据。
2. 把发现从“泛泛建议”改成实际证据支持的结论；不删除合理 finding 以追求 clean。
3. `result.json` 自动包含 `case_id`、`output_contract` 全键、`audit_report[]`、
   `dimension_reviews[11]`、`overall_assessment`、`evidence_and_boundaries`、
   `result_status`、`severity_counts`、`review_process_severity_counts`、
   `recomputations[]`、`sources[]`、`limits[]`、`review_receipt`。调用方额外提供的
   非输入型 contract 值原样直通；不能推导的键保留 null 并在 limits 中具名。
4. `overall_assessment.grade` 仅取 `major_revision / minor_revision /
   review_incomplete / no_major_defect_detected / not_assessable`；它由最高严重度的
   **论文层面**问题决定，不是期刊 accept/reject，`publication_decision` 固定为 null。

## 六步兼容入口（Harbor / Legacy，保留原高分路径）

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

### qualityrun v2 —— 十一维评价与证据 gate（完整规则索引，19 条）

| rule | 默认 severity | 判定与边界 |
|-|-|-|
| `pqa.reviewer_substantiated_issue` | 由 assessment 给出并受锚点约束 | 经原文证据验证的实际逐维问题，不是模板 finding |
| `pqa.novelty_without_contrast` | medium | 有创新声称但未定位先行工作/基线对照；报告缺口 |
| `pqa.design_question_mismatch` | high | 明确声明的研究问题类型与设计不能回答彼此 |
| `pqa.comparative_design_no_control` | high | 比较型实验设计无对照/比较组声明 |
| `pqa.causal_conclusion_exceeds_design` | high | 非实验设计出现明确因果结论 |
| `pqa.sample_accounting_impossible` | high | 实算 analysed_n − recruited_n > 0 |
| `pqa.numeric_reporting_inconsistent` | high | 两个声明数值之差的绝对值实际超过容差 |
| `pqa.full_article_sections_missing` | high | 明确 full_article 的必要章节缺失；先排查抽取完整性 |
| `pqa.references_section_unresolved` | high | 有引用标记但 full article 未能解析参考文献节 |
| `pqa.data_availability_missing` | medium | full article 无数据可用性声明（正文已有声明时不报） |
| `pqa.code_availability_missing` | medium | 明确 computational study 无代码/伪代码声明 |
| `pqa.ethics_statement_missing` | medium | 明确人/动物研究无伦理/知情声明，属于报告缺口 |
| `pqa.competing_interests_missing` | medium | full article 无利益冲突声明 |
| `pqa.dimension_not_assessed` | review_process | 十一维之一没有审查 assessment；不等于论文方法错误 |
| `pqa.assessment_without_evidence` | review_process | 有维度评级但无原句，也无有界不可评说明 |
| `pqa.review_evidence_not_in_source` | high / review_process | 审查所引原句经空白归一化后仍不在原稿，阻止提交 |
| `pqa.concern_without_source` | high / review_process | 具体实质 concern 没有原句且无报告缺口边界 |
| `pqa.legacy_audit_failed` | review_process | 已请求旧规则但该旧 pass 不能执行；不掩盖失败 |
| `pqa.input_not_readable` | undetermined | 无原稿或原稿文字层不可读，十一维均未检查 |

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
- **增益证据形式**：`scripts/bench_quality.py` 21 项检查（合格 RCT 与合格观察性设计
  双向误报对照、伪造证据拒绝、十一维覆盖、真实差值重算）+ `scripts/bench_draft.py`
  35 场景 + `scripts/bench_sections.py` 55 场景。每场景植入一个缺陷或钉住误报守卫，
  两个引擎的 clean baseline 都必须零发现；确定性重跑同一结果，增益可第三方复跑。

## 验证

```bash
python scripts/bench_quality.py   # 21 checks: 十一维主工作流 + 合格设计交叉验证
python scripts/bench_draft.py     # 35 scenarios: 旧 paper_draft 每规则与误报守卫
python scripts/bench_sections.py  # 55 scenarios: 旧跨 section 回归与误报守卫
```

本机全部通过；三套 bench 的 clean baseline 必须零发现。验证是作者维护工具，不是正式
案例运行中的强制步骤；正式入口只做实际审查并交付 result.json。

## Requirements

Python 3.9+（3.14 实测），规则与数值比较使用标准库。TXT/MD/TEX 无额外依赖；直接读
PDF 时惰性使用环境已有的 PyMuPDF、pypdf 或 pdftotext，三者都没有文字层则结构化拒绝，
不伪造解析结果。旧规则路径不需要安装第三方包。

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
- **检查清单可复用**：十一维评价结构 + v2 19 条规则 + 历史 81 条规则（pd 23、
  struct 25、long 32、audit 1），每条带 id、severity 与判定边界，可直接人工复用。
- **bench 回归门**：三个 bench 共 111 项检查/场景（21 + 35 + 55），独立复跑，
  改动引擎后必须全过——是他人验证本 Skill 行为的最短路径。
- **适用范围与不适用**：论文与学位论文的质量、引用、事实、结构、规范审查；不负责
  润色改写、翻译、查重、投稿排版（路由表末行明确拒识）。
- **失败处理**：拒绝运行路径（exit 5 加 undetermined result.json）与 12 行异常处置
  表覆盖扫描件、缺文献表、超长、冲突、歧义等常见故障。
- **维护信息**：规则 id 变更须同步本文规则表；bench 全过是合并条件；引擎内注释记录
  每条被移除规则的历史教训（避免回归）。
