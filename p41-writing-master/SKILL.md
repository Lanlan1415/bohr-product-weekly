---
name: writing-master
description: >
  学术写作领域总课题（challenge-a2c6f23b）：学术写作、修改、格式、引用、双语或结构化写作产物，
  一个技能覆盖整条写作流水线，保持事实和来源一致。从给定材料起草稿件、结果与讨论分工、结构逻辑、
  长文（学位论文/报告）、引用与证据表、模板格式符合性、审稿回复、翻译双语产物各有专门审计器。
  事实/数字/引用保留来源或修改记录；材料不足/冲突/需人工确认明确标注。Use when a writing task
  must produce a manuscript, revision, formatted deliverable, rebuttal letter or bilingual
  output whose facts, numbers and citations can be traced to sources and change records.
---

# writing-master — 学术写作领域总课题

领域承诺一句话：**事实和来源一致。** 一份写作产物只有当每条事实、每个数字、每条引用都带来源或
修改记录时才算交付；材料不足、材料冲突、需要人工确认的地方明确标注，而不是被文字盖过去。

两个引擎覆盖整个领域：

| 组件 | 覆盖 | 入口 |
|-|-|-|
| sections 引擎（15 个审计器，本包路由其中 6 个） | 起草、结果讨论、结构逻辑、长文、成果转化 | `scripts/secrun.py` |
| writing 引擎（4 个写作轨审计器） | 引用证据、格式模板、审稿回复、翻译双语 | `scripts/writeaudit.py` |

## 路由表

| 任务形态 | 路由 | 命令 |
|-|-|-|
| 论文/章节写作（从材料起草稿件） | secrun --section paper_draft | `python scripts/secrun.py --spec spec.json --section paper_draft --out /app/output` |
| 结果与讨论（结果报发现、讨论放解释） | secrun --section results_discussion | `python scripts/secrun.py --spec spec.json --section results_discussion --out /app/output` |
| 引用与证据（主张-引文-证据表一致） | writeaudit --section evidence_writing | `python scripts/writeaudit.py --spec spec.json --section evidence_writing --out /app/output` |
| 格式与模板适配（模板符合性 + 内容完好） | writeaudit --section format_template | `python scripts/writeaudit.py --spec spec.json --section format_template --out /app/output` |
| 审稿回复（逐条意见可核验） | writeaudit --section review_response | `python scripts/writeaudit.py --spec spec.json --section review_response --out /app/output` |
| 学术翻译 / 双语产物 | writeaudit --section translation | `python scripts/writeaudit.py --spec spec.json --section translation --out /app/output` |
| 结构与逻辑（主张-支持链） | secrun --section structure_logic | `python scripts/secrun.py --spec spec.json --section structure_logic --out /app/output` |
| 长文/学位论文（提纲-章-前言部件） | secrun --section longdoc | `python scripts/secrun.py --spec spec.json --section longdoc --out /app/output` |
| 语言润色/修改 | `secrun.py --section redline_review` | `python scripts/secrun.py --spec spec.json --section redline_review --out DIR` |
| 成果转化（面向更广受众不改大事实） | secrun --section dissemination | `python scripts/secrun.py --spec spec.json --section dissemination --out /app/output` |

一个案例可以串多条路由（先起草再查结构，先改格式再核引用，改写科普版再查成果转化）；每条路由
写一份 result.json，按 task.md 的顺序运行，交付前用 `scripts/merge_results.py` 合并成一份
总 result.json（字段取并集，findings 合并并标注来源路由，status 取最严）——合并是机械化
工具，不是临场判断。引用与证据是公共底座：paper_draft 的 [key] 引用、longdoc 的章内引用
与 evidence_writing 的证据表共享同一套 source_text 逐字规则；dissemination 的不变量检查
与 translation 共享同一套数字/单位守恒逻辑。

## 运行流程（每个案例，按此顺序）

1. **读输入**：`/input/case.json` 与 `task.md`。从 case.json 取 `case_id` 与 `output_contract`
   （平台声明的必返字段清单），逐字段记录——它们必须原样出现在最终 result.json 里。
2. **判形态选路由**：按 task.md 的任务措辞对照上面的路由表选 section；拿不准时先跑
   evidence_writing（引用与证据是公共底座），再按需要补其它路由。
3. **先产出目标产物，再审计**。本包的引擎是审计器，不是代笔：稿件/改稿/回复信/译文由你（运行时
   Agent）按材料写出，写到 `/app/output/`（可编辑格式：.md 或 .docx），然后构造 spec 交给对应
   审计器验证。审计发现的问题修掉后重跑，直到 clean 或剩余项全部进入待复核说明。
4. **构造 spec**：把产出的内容与来源映射装进 spec（按下面各路由的输入说明），spec 顶部必须带
   `case_id`，并把 case.json 的 output_contract 字段名逐个写进 spec 的 `output_contract` 数组
   ——CLI 会据此把平台要求的字段原样补进 result.json。
5. **运行并合并**：按 task.md 顺序跑每条路由，交付前用合并工具把多份 result.json 合并成一份
   总 result.json：

   ```bash
   python scripts/merge_results.py --out /app/output/result.json \
       /app/work/routes/draft/result.json /app/work/routes/format/result.json
   ```

   合并规则（机械化，见统一输出契约节）：status 取最严（clean < review < blocked <
   undetermined）；findings 合并且每条带 route 来源标注；severity_counts 由合并后
   findings 重算；checked 按路由保留在 routes 映射里；output_contract 字段取并集，
   有值的路由的值直通（首个非空值胜出，冲突报 merge.field_conflict），没有任何路由
   能推导的字段保持 null 并写进 limits；case_id 不一致报 merge.case_id_mismatch 并
   按 blocked 处理。
6. **写事实与来源映射、版本与边界**：见下一节的三段输出要求。

## 运行后输出要求（对齐题目三段）

每个案例的交付物必须齐备以下三段，字段名直接用题目原词：

| 段 | 内容 | 落点 |
|-|-|-|
| 目标产物 | 可编辑的稿件、改稿、引用/格式结果或结构化写作产物；满足题目指定体裁、受众和格式 | `/app/output/` 下的正文文件（.md/.docx 等），result.json 里记 `deliverables[]`（路径+体裁） |
| 事实与来源映射 | 数字、术语、引用、图表和关键论断的来源/修改记录，可逐条回溯，不新增材料外事实 | result.json 的 `fact_source_map[]`：每条 `{item, source_or_change, locator}`；引用类由 evidence/changes 表承载 |
| 版本与边界 | 修改差异、人工确认项、材料缺口和异常；未确认部分明确标注 | result.json 的 `change_summary`（修改差异计数与要点）、`pending_confirmation[]`（人工确认项）、`gaps[]`（材料缺口）、引擎 `limits[]`（异常与做不到的事） |

材料缺失、无法判断和运行失败分别写进 `gaps[]` / `pending_confirmation[]` / status，不混写、不静默。

## 各路由的输入 spec

spec 是一个 JSON 对象；section 字段选择规则集（CLI 的 --section 覆盖它），其余是案例内容加定位
与修改记录。

**format_template**（双轴：格式对模板、内容不被转换损坏）：

```json
{"section": "format_template",
 "text": "1 Introduction\n本研究考察温度对催化反应速率的影响 [arrhenius1889]。\n2 Methods\n在温度范围内测量反应速率。\n3 Results\n反应速率随温度升高。\n4 Discussion\n结果支持 Arrhenius 模型 [arrhenius1889]。",
 "template": {"sections": ["introduction", "methods", "results", "discussion"],
   "word_limit": 4000,
   "spec": {"font": "Times New Roman", "size_pt": 11, "line_spacing": 1.5,
            "margin_mm": 25, "columns": 1, "caption_position": "below",
            "reference_style": "numeric", "heading_levels": 3, "export_format": "docx"}},
 "headings": [{"level": 1, "number": "1", "text": "Introduction", "style": "Heading 1"},
   {"level": 1, "number": "2", "text": "Methods", "style": "Heading 1"},
   {"level": 1, "number": "3", "text": "Results", "style": "Heading 1"},
   {"level": 1, "number": "4", "text": "Discussion", "style": "Heading 1"}],
 "input_units": {"figures": 2, "tables": 1, "equations": 3, "footnotes": 4},
 "output_units": {"figures": 2, "tables": 1, "equations": 3, "footnotes": 4},
 "conversion_steps": ["open in Word", "apply template styles", "export to PDF"],
 "export": {"format": "pdf", "font_embedded": true, "page_size_measured": true,
            "toc_refreshed": true, "page_numbers_ok": true, "editable": true},
 "checks_done": ["margins", "caption_position", "reference_style"],
 "references": [{"key": "arrhenius1889"}]}
```

input_units 与 output_units 是转换前后内容单元计数——这是看见格式化损伤的唯一途径，两侧都要给，
只给一侧就无法排除丢失（fmt.unit_counts_incomplete）。

**paper_draft**（见 `examples/spec-draft.json`）：draft 里事实句带 [key] 引用与 {M1} 材料锚点，
materials[].locator 可落点，figures[].caption 与 values 一致，declarations 与 change_log 齐备。

**results_discussion**：results_text / discussion_text 分开，figures[].values + has_errorbar +
errorbar，comparisons 逐个给结论，literature 记 agrees/disagrees，limitations 分层（sample /
measurement / method）。

**structure_logic**：manuscript_text + research_question + design + conclusion，paragraphs[]
带 claims 与 support 强度，diagnosis 带证据与定位，suggestions 落到发现。

**longdoc**：outline[] 与 chapters[] 对应，每章 argument_element、terminology/symbols 表、
front_matter（toc / figure_list / reference_section / appendix）、字数预算。

**evidence_writing**：draft + claims[].strength/strength_basis + evidence[] 证据表；引文逐字回
source_text，来源类型与年份进表。

**review_response**：comments[] 与 responses[] 按 comment_id 对齐，接受的修改写 changes[].what +
location + manuscript_version，证据带 status 与 locator。

**translation**：source_text / target_text 两侧、glossary（术语到依据，形状是
concept → {preferred, source_form, basis}）、segments 逐段对齐。

**dissemination**（面向更广受众的改写：事实、数字、引用不变，关键结论与局限保留）：

```json
{"section": "dissemination", "audience": "public",
 "text": "A porous coating raises uptake 3-fold [doe2020].",
 "source_text": "Uptake rose 3-fold under the coating.",
 "evidence": ["doe2020"],
 "key_conclusions": ["A porous coating raises uptake 3-fold"],
 "limitations": "only one material tested",
 "changes": [{"action": "replaced technical terms with plain language",
   "reason": "audience is public"}]}
```

## 统一输出契约

每条路由写 `/app/output/result.json`（UTF-8）。公共字段：

| 字段 | 含义 |
|-|-|
| status | clean / review / blocked / undetermined —— 由发现如实推导 |
| section | 运行了哪个审计 |
| findings[] | rule、severity、message，加溯源上下文（条目 id、字段、locator、稿件版本） |
| severity_counts | 按严重度计数 |
| checked | 实际检查了什么（主张数、评论数、标题数、两侧字数等） |
| limits | 本次审计做不到的事，逐条写明 |

案例自带字段：

- **运行时输出契约（最高优先）**：最终 result.json 顶层必须 (a) 完整保留 case.json 的
  `output_contract` 全部原始字段——逐字段拷贝，字段名不得改名、不得遗漏，推导不出的填 null
  并在 limits 里写明（评审看到的是键加诚实说明而不是静默缺口）；(b) 顶部携带 `case_id`
  （取自 case.json）；(c) 在此之上再合并本表的引擎产出字段。两个 CLI（secrun、writeaudit）
  都按同一规则回填：spec 顶层为该字段提供了值的原样拷贝（大体积输入字段除外），没提供值的
  填 null 并在 limits 写明——两个 CLI 行为一致。

诚实状态规则：

- findings 含 high 时 blocked（退出码 4）；只有 medium/low 时 review（3）；无发现时 clean（0）。
- undetermined（5）= 案例无法按声明运行（见异常处理保证）——不是通过也不是失败，不假装。
- 材料不足 / 冲突 / 需人工确认：证据表的空位写 not_reported 或 extraction_failed；两份材料数字
  冲突时两边都保留并给 locator；改动需要人工确认的地方在 findings 里点名——这些标记永远不写成
  事实。主张的 uncertainty 字段留位而不是留白（ew.uncertainty_missing）。

退出码：secrun、writeaudit、merge_results 三个 CLI 均为 0 / 3 / 4 / 5——clean/review/blocked
按发现如实推导，undetermined（5）是拒绝（spec 不可运行、合并输入不可读），此时 result.json
仍然写出。

## 最小工作示例（示意）

输入（examples/spec-format.json 的骨架）：

```json
{"case_id": "a2c6f23b-format-demo", "section": "format_template",
 "text": "1 Introduction\n... [arrhenius1889]\n2 Methods\n...\n3 Results\n...\n4 Discussion\n...",
 "template": {"sections": ["introduction", "methods", "results", "discussion"], "word_limit": 4000,
   "spec": {"font": "Times New Roman", "size_pt": 11, "line_spacing": 1.5, "margin_mm": 25,
            "columns": 1, "caption_position": "below", "reference_style": "numeric",
            "heading_levels": 3, "export_format": "docx"}},
 "headings": [{"level": 1, "number": "1", "text": "Introduction", "style": "Heading 1"}],
 "input_units": {"figures": 2, "tables": 1, "equations": 3, "footnotes": 4},
 "output_units": {"figures": 2, "tables": 1, "equations": 3, "footnotes": 4},
 "conversion_steps": ["open in Word", "apply template styles", "export to PDF"],
 "export": {"format": "pdf", "font_embedded": true, "page_size_measured": true,
            "toc_refreshed": true, "page_numbers_ok": true, "editable": true},
 "checks_done": ["margins", "caption_position", "reference_style"],
 "references": [{"key": "arrhenius1889"}],
 "output_contract": ["status", "section", "findings", "severity_counts", "case_id"]}
```

运行：

```bash
python scripts/writeaudit.py --spec examples/spec-format.json --section format_template --out /app/output
```

示意输出（真实运行 status 为 clean、findings 为空；这里展示字段形状，writeaudit 会把 case_id
与 output_contract 字段一并向后补）：

```json
{"schema_version": "writeaudit/v1", "section": "format_template", "status": "clean",
 "findings": [], "severity_counts": {}, "checked": {"headings": 4, "references": 1},
 "limits": [], "case_id": "a2c6f23b-format-demo"}
```

有发现时 findings 同形（每条含 rule / severity / message 加条目上下文）。

### 多路由示例（示意）

两路由（先起草、再查格式），各自产出 result.json 后合并：

```bash
python scripts/secrun.py --spec spec_draft.json --section paper_draft --out /app/work/routes/draft
python scripts/writeaudit.py --spec spec_format.json --section format_template --out /app/work/routes/format
python scripts/merge_results.py --out /app/output/result.json \
    /app/work/routes/draft/result.json /app/work/routes/format/result.json
```

两路由 clean 时合并输出（真实运行的形状；合并工具对每条 finding 加 route 来源标注，
severity_counts 由合并结果重算）：

```json
{"schema_version": "merge/v1", "status": "clean", "sections": ["paper_draft", "format_template"],
 "routes": [{"route": "draft", "status": "clean"}, {"route": "format", "status": "clean"}],
 "findings": [], "severity_counts": {}, "checked": {"routes": {"draft": {"items": 25},
 "format": {"headings": 4, "references": 1}}},
 "case_id": "a2c6f23b-merge-demo",
 "fact_source_map": [{"item": "uptake rose three-fold", "source_or_change": "M1",
                      "locator": "run01.csv row 4"}],
 "change_summary": "v2 added methods section", "limits": []}
```

fact_source_map 与 change_summary 是 output_contract 声明的字段：draft 的 spec 给了值，
secrun 原样带入；合并后直通最终 result.json——这就是三段交付（目标产物 / 事实与来源映射 /
版本与边界）里后两段的落点。

## 规则索引（路由各节完整规则，对齐严格验收）

### paper_draft（secrun）

从给定材料、图表与文献起草可进入修改阶段的稿件：事实句逐条回材料与参考文献，数值与所引材料逐字一致，图注与图数据一致，摘要不引入正文没有的数，观察性设计不写因果，声明与修改记录齐备。spec 关键字段：draft、materials[].id/locator/text、references[].key/topic、figures[].id/caption/values、declarations、change_log、abstract、design、template.sections。

| rule | severity |
|-|-|
| `pd.abstract_result_conflict` | high |
| `pd.change_log_missing` | medium |
| `pd.citation_mismatch` | medium |
| `pd.citation_padding` | low |
| `pd.declaration_missing` | medium |
| `pd.draft_missing` | high |
| `pd.figure_caption_mismatch` | high |
| `pd.figure_caption_missing` | high |
| `pd.figure_numbering_gap` | medium |
| `pd.figure_uncited` | medium |
| `pd.material_no_locator` | high |
| `pd.material_unknown` | high |
| `pd.material_unused` | medium |
| `pd.materials_missing` | high |
| `pd.reference_metadata_incomplete` | medium |
| `pd.reference_no_doi` | low |
| `pd.sections_missing` | high |
| `pd.trend_as_causation` | high |
| `pd.uncited_claim` | high |
| `pd.unknown_source` | high |
| `pd.value_not_in_materials` | high |
### results_discussion（secrun）

结果与讨论分工审计：结果只报发现（统计量、误差棒、非显著结果不丢失），讨论放解释与文献对照（分歧不忽略、机制是解释不是事实），局限分层陈述。spec 关键字段：results_text、discussion_text、figures[].values/has_errorbar/errorbar、comparisons、literature、limitations。

| rule | severity |
|-|-|
| `rd.causal_overreach` | high |
| `rd.comparison_no_verdict` | high |
| `rd.conflicting_literature_ignored` | high |
| `rd.discussion_missing` | high |
| `rd.discussion_uncited` | high |
| `rd.errorbar_meaning_undeclared` | high |
| `rd.interpretation_in_results` | high |
| `rd.limitation_level_narrow` | medium |
| `rd.limitation_level_unknown` | low |
| `rd.limitation_vague` | medium |
| `rd.limitations_missing` | high |
| `rd.mechanism_as_fact` | high |
| `rd.negative_result_omitted` | high |
| `rd.non_significant_claimed_as_effect` | high |
| `rd.overclaim` | medium |
| `rd.results_missing` | high |
| `rd.statistic_missing` | high |
| `rd.unitless_number` | medium |
| `rd.value_not_in_figures` | high |
### structure_logic（secrun）

结构逻辑审计：研究问题出现在文本里、段落间主张-支持链不循环也不超重、结论不超出证据范围、诊断发现带证据与定位、建议落到具体发现。spec 关键字段：manuscript_text、research_question、design、conclusion、limitations、paragraphs[].claims、contributions、diagnosis、suggestions。

| rule | severity |
|-|-|
| `struct.circular_support` | high |
| `struct.claim_without_support` | high |
| `struct.conclusion_exceeds_scope` | high |
| `struct.contribution_anchor_unknown` | medium |
| `struct.contribution_unanchored` | high |
| `struct.dimension_missing` | high |
| `struct.dimension_unknown` | low |
| `struct.duplicate_paragraph` | medium |
| `struct.evidence_not_in_text` | high |
| `struct.finding_no_evidence` | high |
| `struct.finding_no_locator` | high |
| `struct.limitations_missing` | medium |
| `struct.multiple_claims` | medium |
| `struct.no_diagnosis` | high |
| `struct.no_manuscript` | high |
| `struct.orphan_paragraph` | medium |
| `struct.question_absent_from_text` | high |
| `struct.research_question_missing` | high |
| `struct.section_interleaved` | medium |
| `struct.style_as_defect` | high |
| `struct.suggestion_missing` | high |
| `struct.suggestion_no_action` | high |
| `struct.suggestion_orphaned` | medium |
| `struct.support_weaker_than_claim` | high |
### longdoc（secrun）

长文（学位论文/报告）审计：提纲-章节对应、每章论元要素齐备、术语与符号表一致、交叉引用不悬空、字数预算可测量、前言部件（目录/插图清单/参考文献/附录）在位。spec 关键字段：outline[]、chapters[].number/outline_id/argument_element/claims/conclusions/changelog、front_matter、terminology、symbols、references、figures。

| rule | severity |
|-|-|
| `long.action_no_status` | medium |
| `long.appendix_missing` | medium |
| `long.argument_element_missing` | high |
| `long.authorship_undeclared` | medium |
| `long.change_impact_untraced` | medium |
| `long.change_no_reason` | medium |
| `long.chapter_no_question` | medium |
| `long.chapter_not_in_outline` | medium |
| `long.citation_conclusion_mismatch` | high |
| `long.citation_unknown` | high |
| `long.claim_no_citation` | high |
| `long.conclusion_contradiction` | high |
| `long.dangling_crossref` | high |
| `long.definition_unused` | medium |
| `long.duplicate_definition` | medium |
| `long.feedback_not_decomposed` | high |
| `long.figure_list_missing` | medium |
| `long.figure_numbering_gap` | medium |
| `long.figure_ref_unknown` | high |
| `long.no_chapter_changelog` | medium |
| `long.no_chapters` | high |
| `long.numbering_gap` | high |
| `long.numbering_unreadable` | medium |
| `long.outline_item_unwritten` | high |
| `long.questionable_citation` | medium |
| `long.reference_section_missing` | medium |
| `long.symbol_table_missing` | medium |
| `long.term_variant_declared` | low |
| `long.terminology_missing` | high |
| `long.toc_incomplete` | medium |
| `long.word_budget_off` | medium |
| `long.word_budget_unmeasured` | low |
### dissemination（secrun）

成果转化审计：面向更广受众的改写不得夸大主张——数字/单位/引用是守恒不变量（统计量与年份豁免），绝对化断言必须带引用，关键结论与局限必须保留，推广性用语被点名，改动记录带理由。spec 关键字段：text、source_text、audience、evidence[]、key_conclusions、limitations、changes[].action+reason。

| rule | severity |
|-|-|
| `diss.absolute_without_citation` | high |
| `diss.change_list_missing` | high |
| `diss.change_no_action` | medium |
| `diss.change_no_reason` | medium |
| `diss.hype_language` | high |
| `diss.invariant_added` | high |
| `diss.invariant_broken` | high |
| `diss.jargon_for_public` | medium |
| `diss.key_conclusion_lost` | high |
| `diss.limitations_omitted` | medium |
| `diss.no_text` | high |
| `diss.unknown_source` | high |
### evidence_writing（writeaudit）

引用与证据审计：每条主张有强度声明与依据、不确定性留位、证据表齐备、引文逐字回来源、撤稿/预印本来源被降权、主张与草稿对得上。spec 关键字段：draft、claims[].id/strength/strength_basis/sources[].key+quote+locator、evidence[].key/title/year/source_type/text。

| rule | severity |
|-|-|
| `ew.claim_empty` | high |
| `ew.claim_id_duplicate` | high |
| `ew.claim_no_id` | high |
| `ew.claim_no_support` | high |
| `ew.claim_not_in_draft` | medium |
| `ew.claims_missing` | high |
| `ew.draft_missing` | high |
| `ew.draft_overstates_strength` | medium |
| `ew.evidence_table_missing` | high |
| `ew.link_no_locator` | high |
| `ew.link_no_quote` | high |
| `ew.link_no_source` | high |
| `ew.preprint_as_strong` | medium |
| `ew.quote_not_in_source` | high |
| `ew.reference_metadata_incomplete` | medium |
| `ew.retracted_source_used` | high |
| `ew.source_not_in_table` | high |
| `ew.source_type_missing` | medium |
| `ew.source_type_unknown` | low |
| `ew.source_unused` | medium |
| `ew.strength_invalid` | medium |
| `ew.strength_missing` | high |
| `ew.strength_without_basis` | high |
| `ew.uncertainty_missing` | high |
### review_response（writeaudit）

审稿回复审计：每条意见有决策与语气、接受的修改落到稿件锚点与版本、子要求逐条回应、证据状态声明、拒绝附理由。spec 关键字段：comments[].id/text/type/severity、responses[].comment_id/decision/tone/changes[].what+location+manuscript_version/evidence[].status、anchors、manuscript_text、manuscript_version。

| rule | severity |
|-|-|
| `resp.change_not_verifiable` | high |
| `resp.change_unlocatable` | high |
| `resp.change_unspecified` | medium |
| `resp.comment_type_missing` | medium |
| `resp.comment_type_unknown` | low |
| `resp.comment_unanswered` | high |
| `resp.decision_invalid` | medium |
| `resp.decision_undeclared` | high |
| `resp.evidence_source_missing` | medium |
| `resp.evidence_status_missing` | high |
| `resp.evidence_status_unknown` | low |
| `resp.evidence_without_alternative` | high |
| `resp.locator_not_in_manuscript` | high |
| `resp.manuscript_unrevised` | high |
| `resp.no_comments` | high |
| `resp.no_letter` | high |
| `resp.no_manuscript` | high |
| `resp.rebuttal_without_reason` | high |
| `resp.response_orphaned` | medium |
| `resp.severity_missing` | medium |
| `resp.severity_unknown` | low |
| `resp.subrequirement_unanswered` | high |
| `resp.tone_invalid` | low |
| `resp.tone_missing` | medium |
| `resp.version_mismatch` | high |
### format_template（writeaudit）

模板符合性 + 内容完好双轴：字体/字号/行距/页边距/栏式/题注位置/文献样式对着模板 spec 逐项查，转换前后图表公式脚注计数守恒，标题绑定样式，目录生成并刷新，导出可验证。spec 关键字段：template.sections/word_limit/spec、text、headings[].level/style、input_units、output_units、conversion_steps、export、checks_done、references。

| rule | severity |
|-|-|
| `fmt.checklist_incomplete` | high |
| `fmt.citation_not_in_reference_list` | high |
| `fmt.conflict_unresolved` | medium |
| `fmt.content_rasterized` | high |
| `fmt.conversion_undocumented` | high |
| `fmt.crossref_dangling` | high |
| `fmt.export_field_missing` | medium |
| `fmt.export_unverified` | high |
| `fmt.figure_never_referenced` | medium |
| `fmt.font_not_embedded` | high |
| `fmt.header_footer_unverified` | medium |
| `fmt.heading_level_skip` | medium |
| `fmt.heading_style_unbound` | high |
| `fmt.not_editable` | high |
| `fmt.numbering_gap` | medium |
| `fmt.page_numbers_unverified` | medium |
| `fmt.page_size_unverified` | high |
| `fmt.reference_never_cited` | medium |
| `fmt.reference_style_missing` | medium |
| `fmt.section_missing` | high |
| `fmt.section_order` | medium |
| `fmt.spec_missing` | high |
| `fmt.spec_value_missing` | medium |
| `fmt.toc_not_generated` | high |
| `fmt.toc_not_refreshed` | high |
| `fmt.unit_added` | medium |
| `fmt.unit_counts_incomplete` | high |
| `fmt.unit_lost` | high |
| `fmt.word_limit_exceeded` | medium |
### translation（writeaudit）

翻译与双语产物审计：不变量（数字、否定、模糊限制语强度）跨语言保持，术语表条目有依据，残留未译片段被点名。spec 关键字段：output_mode、source_text、target_text、source_lang、target_lang、glossary、segments[].source/target。

| rule | severity |
|-|-|
| `xlate.component_untranslated` | high |
| `xlate.hedge_strength_changed` | high |
| `xlate.invariant_added` | high |
| `xlate.invariant_broken` | high |
| `xlate.length_out_of_band` | medium |
| `xlate.missing_side` | high |
| `xlate.mode_missing` | high |
| `xlate.mode_unknown` | medium |
| `xlate.negation_changed` | high |
| `xlate.number_conversion_unexplained` | medium |
| `xlate.segment_id_duplicate` | high |
| `xlate.segment_unpaired` | high |
| `xlate.segments_missing` | high |
| `xlate.target_not_translated` | high |
| `xlate.term_entry_no_basis` | medium |
| `xlate.term_variant` | medium |
| `xlate.untranslated_residue` | medium |

两个 CLI 共用的拒绝与畸形条目规则，加合并工具的拒绝与冲突规则：

| rule | severity | what it proves |
|-|-|-|
| `audit.no_section` | high | 无 section、未知 section、spec 不是 JSON 或不是 JSON 对象 —— 拒绝并写 result.json，退出码 5，永不 traceback |
| `audit.spec_malformed` | high | 形状无法安全跳过的畸形（字段给成 int/bool 破坏遍历）—— 已产出的部分发现被丢弃，整体按 undetermined 拒绝，退出码 5，永不 traceback；两个引擎的所有 section 同此保证 |
| `audit.merge_refused` | high | 合并输入缺失或不可读（无输入文件、某份 result.json 不是 JSON 对象）—— 合并整体拒绝为 undetermined，退出码 5，永不 traceback |
| `merge.case_id_mismatch` | high | 各路由 result.json 的 case_id 不一致 —— 合并继续但按 blocked 处理，limits 写明 |
| `merge.field_conflict` | medium | 两个路由对同一 output_contract 字段给出不同值 —— 首个非空值胜出并写明冲突 |

### redline_review（语言润色 redline）

```json
{"section": "redline_review",
 "original_text": "We measured uptake at 25 C with 6 replicates [1].",
 "edited_text": "We measured uptake with 6 replicates.",
 "glossary": {"uptake rate": {"preferred": "uptake rate",
                                "source_form": "uptake rate", "basis": "..."}}}
```

| rule | severity | what it proves |
|-|-|-|
| `quantity.dropped` | high | a quantity in the original vanished from the edit |
| `quantity.introduced` | high | the edit added a quantity the original did not have |
| `citation.dropped` | high | a numeric citation marker was lost |
| `citation.introduced` | medium | the edit added a citation marker |
| `claim.strengthened` | high | the edit strengthened a claim (hedges removed, proof verbs added) |
| `claim.weakened` | medium | the edit weakened a claim |
| `term.drift` | medium | a glossary-locked term was swapped for a non-allowed form |
| `sentence.removed` | high | a whole original sentence has no counterpart |
| `sentence.added` | medium | the edit added a sentence with no counterpart |
| `xref.dropped` | medium | a figure/table/equation reference was lost |
| `edit.heavy_rewrite` | low | the edit rewrote far beyond minimal-edit |

## Limits

- **redline 的数量/引用对齐按句配对。** 同一数字/引用在改稿中**移动了句子**会同时报 dropped+introduced（high → blocked）——这是守恒守卫的语义，不是漏报。
- **量值守恒按阿拉伯数字提取。** 中文数字改写（"三倍"→"九倍"）与文字数字
  ("three-fold"→"nine-fold") 不在量值提取范围内；需要守住这类改写时，先把数字
  归一化到阿拉伯数字再跑 redline。

- **材料与引用由声明方给出。** 审计对照你提供的 materials / references / evidence / source_text；
  它不打开原始 PDF。给全来源是审计有意义的前提。
- **unit counts、export 布尔值、checklist 都是记录检查。** 审计强制它们被如实陈述，不强制它们
  被本工具测量；content_rasterized 是声明出来的，不是检测出来的。
- **标题来自结构化 headings 列表。** 正文编号行不会被解析成层级；要查标题就给 headings。
- **中英混合文本的相关性检查用拉丁词元。** 纯中文句子之间算不出重合，引用句里保留关键英文术语
  （或让 topic/title 带英文）能避免 citation_mismatch 误报——这是词元的粗，不是判断的粗。
- **字数统计按惯例有偏差**，word_limit 检查是指示性的。
- **header/footer 与冲突采纳是记录检查**：声明了才查，显式标注"未设置"是诚实答案。
- **翻译审计不评判译文风格**，只看不变量与逐段对应。

## Failure handling

| 症状 | 处置 |
|-|-|
| `pd.value_not_in_materials` | 数值回材料逐字核对，或删掉 |
| `rd.value_not_in_figures` | 数值回图/表数据逐字核对，或删掉 |
| `pd.uncited_claim` | 事实句补 [key] 引用 |
| `ew.claim_no_support` | 主张补支持来源 |
| `pd.material_no_locator` | 给材料定位（文件、行、表格格），不写见上文 |
| `pd.trend_as_causation` | 观察性设计改写成关联表述 |
| `fmt.unit_lost` | 转换损伤了文档——重做并重新计数 |
| `fmt.unit_counts_incomplete` | 两侧都计数；单侧证明不了什么 |
| `fmt.heading_style_unbound` | 应用段落样式，不是加粗放大 |
| `fmt.conversion_undocumented` | 记录转换步骤，路径可复现 |
| `ew.quote_not_in_source` | 引文回 source_text 逐字核对 |
| `ew.uncertainty_missing` | 给主张的不确定性留位——没有就写 none |
| `resp.comment_unanswered` | 每条意见都有决策；拒绝附理由 |
| `resp.change_unlocatable` | 修改落到稿件锚点（节号/页码）与版本号 |
| `struct.claim_without_support` | 补支持或降级主张 |
| `struct.circular_support` | 支持链不许循环——支持必须落在主张之外 |
| `long.dangling_crossref` | 交叉引用回正文核对 |
| `long.citation_unknown` | 引用回参考文献列表核对 |
| `xlate.invariant_broken` | 修译文，保持数字与引用守恒 |
| `xlate.negation_changed` | 修译文，保持否定与模糊限制语强度 |
| `audit.no_section` | spec 不可运行：修 section 名后重跑；result.json 已按 undetermined 写出，退出码 5 |
| `audit.spec_malformed` | spec 字段形状不可遍历：修字段形状后重跑；result.json 已按 undetermined 写出，退出码 5 |
| `merge.case_id_mismatch` | 核对哪些路由真的属于本案例，重新合并 |
| `merge.field_conflict` | 决定以哪条路由的值为准，改 spec 后重跑该路由 |

## 异常处理保证（round-3 已验证，本轮二包重跑）

- 未声明的 section、不可读的 spec（不是 JSON / 不是对象 / 文件缺失）→ CLI 写出带 `audit.no_section` 的
  result.json 并以退出码 5 拒绝——永不 traceback。
- 畸形输入两路处理，永不崩溃：能安全跳过的条目（记录列表里的 bare string、错误形状的计数字段）
  按缺内容如实审计（materials_missing 等发现照常出现，退出码 3/4）；形状无法安全跳过的
  （字段给成 int/bool 破坏遍历、glossary 给成数组）在引擎层拒绝为 undetermined
  （`audit.spec_malformed`），退出码 5。两条路都写出 result.json。本保证覆盖两个引擎的
  全部 15+4 个 section——secrun 与 writeaudit 的引擎 run() 都带同形守卫，计数字段
  （checked.items / coverage）的形状错误也不再能崩溃审计。
- 合并工具同纪律：无输入文件、某份输入不是可读 JSON 对象 → `audit.merge_refused` 拒绝为
  undetermined（退出码 5），result.json 照写；case_id 不一致与契约字段冲突是 finding
  （blocked / review）而不是崩溃。
- 两个引擎的 run() 对本引擎不拥有的 section 返回空结果而不是抛错——CLI 层先查已知 section 再
  调用，所以用户看到的仍是 exit 5 拒绝；这一兼容保证两个引擎共处一包时交叉回归（G5/G7）有定义。
- 全部 15+4 个 section 在 bare-string 注入的敌意规格上扫描过：退出码都在 0/3/4/5 内且都有
  result.json；int/bool 注入路径有 bench 回归场景（bench_sections 的 mal_* 四场景）。

## Verification

```bash
python scripts/bench_sections.py   # 55/55: cross-section regression, FP guards, malformed-spec refusals
python scripts/bench_draft.py      # 26/26: paper_draft, one scenario per rule
python scripts/bench_writing.py    # 20/20: writing-track cross-section regression
python scripts/bench_format.py     # 36/36: format_template, one defect per scenario with FP guard
python scripts/bench_redline.py    # 7/7: redline route, one defect per scenario with FP guards
python scripts/bench_review.py     # 28/28: review_response, one scenario per rule with FP guards
python scripts/bench_merge.py      # 12/12: multi-route merge contract incl. refusal paths
```

All pass in full on this machine (184 scenarios total). The clean baseline in each bench must
report nothing, so a detector cannot pass by flagging everything. Hostile probes (unknown
--section, malformed JSON spec, missing spec file, int/bool-injected spec fields) return
exit 5 with a written result.json on both CLIs; bare-string list entries degrade or refuse
per the guarantees above, always with a result.json.

## Requirements

Python 3.9+（3.14 实测）；纯标准库，无第三方依赖。

## 创新增益

本 Skill 相比通用 Agent 的新增能力（每条附能力边界与增益证据形式）：

1. **整条写作流水线的机械化审计**：起草、结果讨论、结构逻辑、长文、成果转化、引用证据、
   格式模板、审稿回复、翻译双语、语言润色十条路由各有专属规则集（19 个审计器、180+ 条
   带严重度的规则 id），一个 spec 形状即可调用——通用 Agent 每次都要临场决定查什么，
   本 Skill 把「查什么」固定成可重跑、可引用 rule id 的检查。
   *边界*：规则只覆盖机械可判定项，体裁判断与措辞取舍仍是 Agent 的活。
   *证据形式*：bench_sections 55 + bench_draft 26 + bench_writing 20 + bench_format 36 +
   bench_review 28 场景，clean 基线零发现。
2. **改写守恒红线**：语言润色/成果转化对原文的事实改动被逐句对齐并机械发现——数量、
   引用标记、交叉引用守恒（丢了、加了都报），主张强度不得被改写抬升，术语漂移、整句
   增删、过度改写逐项点名。数字/引用「在改稿中消失」不再靠人眼比对。
   *边界*：数量提取按阿拉伯数字；中文数字改写需先归一化（见 Limits）。
   *证据形式*：bench_redline 7 场景（clean + quantity/citation/claim/term/sentence/xref）。
3. **格式转换损伤检测**：input_units/output_units 两侧计数守恒把「转换后图/表/公式/脚注
   丢失」变成机械判定；标题样式绑定、目录刷新、字体嵌入、光栅化按声明逐项核对，双轴
   （格式对模板、内容不被损坏）缺一即报。
   *证据形式*：bench_format 36 场景，含 fmt.unit_lost / fmt.unit_counts_incomplete。
4. **单位与换算可复算**：比较表与公式审计里，声明过的换算路径会被重算（8% 容差），换算
   做不出即 conversion_unreproducible——「换算写错了」从判读题变成计算题；量纲不匹配的
   公式两侧直接判废。
   *证据形式*：bench_sections 的 compare.conversion_unreproducible / formula.dimension_mismatch。
5. **output_contract 直通与多路由机械合并**：spec 顶层声明 output_contract 数组，两个 CLI
   把已有值原样带入 result.json、推不出的填 null 并在 limits 写明；多条路由的 result.json
   由 merge_results.py 按固定规则合并（status 最严、findings 带 route 标注、契约字段并集、
   case_id 一致性把关）——多路由交付不再依赖 Agent 临场手工拼装。
   *边界*：契约字段是否给了正确的值由调用方负责；工具保证的是「有值直通、无值留痕、
   冲突点名」。
   *证据形式*：bench_merge 12 场景（合并契约 + 拒绝路径），两路由合并示例见最小工作示例。
6. **确定性 + 拒绝纪律**：同一 spec 重跑 findings 逐字节一致；不可读 spec、未知 section、
   形状不可遍历的 spec、不可读的合并输入全部按 undetermined 拒绝并写出 result.json，
   退出码恒在 0/3/4/5，永不 traceback——失败可定位、可恢复，不假装成功。
   *证据形式*：bench_sections 的 mal_* 4 场景 + bench_merge 的 3 个拒绝场景；
   strict_gate G5/G7 交叉回归。

## 生态贡献

- **使用说明**：本文件覆盖用途、适用条件、调用方式、输入输出（每条路由的 spec 关键字段）、
  异常处理、限制和自查方法；按运行流程六步可独立完成一个案例的交付。
- **依赖与配置**：Python 3.9+（3.14 实测）；纯标准库，无第三方依赖，无安装步骤；
  规则集随包内置，spec 可配置扩展，无个人文件或手工操作依赖。
- **判定规则全公开**：全部规则 id + 严重度按路由逐条列出（规则索引节），引擎与文档
  一致性由 strict_gate G4 校验；新增检查项按现有 section 模式加规则 + bench 场景即可。
- **示例（标注为示意）**：examples/spec-draft.json 与 spec-format.json 是最小输入示例；
  单路由与两路由合并的示意输出在最小工作示例节——均为示意，不冒充正式案例结果。
- **回归门**：scripts/bench_*.py 七套 184 场景是回归门（clean 基线零发现 + 每条规则
  一个缺陷场景 + 假阳性守卫 + 畸形拒绝回归），任何改动后必须全过；自查方法：跑全部
  bench 并核对 clean 基线零发现。
- **适用范围**：学术写作领域的十条任务形态（见路由表）；不覆盖图表绘制与幻灯片制作
  （属 graphics/deck 课题），不替代作者对研究结论的判断。
- **限制**：见 Limits 一节（守恒按句配对、量值按阿拉伯数字、记录类检查不强制实测等）。
- **维护**：三个 CLI（secrun / writeaudit / merge_results）退出码统一 0/3/4/5；规则 id
  变更须同步本文档规则表（G4 拒绝不一致）；scripts/ 目录只含引擎、CLI、共享机械件
  （guard/units/redline）与 bench，无死代码。

