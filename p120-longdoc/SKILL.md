---
name: long-document
description: >
  Audit a thesis or long document at chapter scale, where what breaks is the joins rather than
  any one chapter. Checks the outline against the chapters actually written, that the argument's
  five parts each have a chapter, that front and back matter exist, that a terminology and symbol
  table keep one concept to one name, that no term is redefined in a later chapter, that every
  chapter claim is bound to a reference that matches it and carries retrievable metadata, that
  conclusions carry a direction so contradictions across chapters are detectable, that numbering
  and cross-references resolve for figures, tables and chapters, that the table of contents
  matches the document in both directions, and that each chapter records its change history with
  a reason and a traced impact. Use when a task asks for a thesis chapter, a long manuscript
  section, a revision against reviewer comments, or a multi-chapter document.
---

# long-document

In a 200-page document nothing fails locally. It fails at the seams: a chapter that answers an
outline item nobody wrote, a term defined twice with drifting meaning, a conclusion in chapter 5
that contradicts chapter 3, a figure or table reference pointing at a number that no longer
exists, a table-of-contents entry no chapter answers. Every one of those is mechanically
detectable at chapter scale, and none of them is visible by reading a single chapter.

The scoring points this task states, each as a rule:

| scoring point (rubric wording) | rule |
|-|-|
| 章节规划与提纲对应（立得住） | `long.outline_item_unwritten`, `long.chapter_not_in_outline`, `long.argument_element_missing`, `long.word_budget_off`, `long.word_budget_unmeasured` |
| 跨章节一致性（连得上） | `long.terminology_missing`, `long.duplicate_definition`, `long.term_variant_used`, `long.conclusion_contradiction`, `long.conclusion_without_direction` |
| 论断与文献绑定（查得清） | `long.claim_no_citation`, `long.citation_unknown`, `long.citation_conclusion_mismatch`, `long.reference_metadata_incomplete`, `long.questionable_citation` |
| 编号与交叉引用可解析（查得清） | `long.numbering_gap`, `long.dangling_crossref`, `long.figure_numbering_gap`, `long.figure_ref_unknown`, `long.table_numbering_gap`, `long.table_ref_unknown`, `long.toc_incomplete`, `long.toc_entry_unknown` |
| 局部修改可复核（改得动） | `long.no_chapter_changelog`, `long.change_no_reason`, `long.change_impact_untraced`, `long.feedback_not_decomposed`, `long.action_no_status` |
| 著录项齐全（立得住） | `long.reference_section_missing`, `long.figure_list_missing`, `long.appendix_missing` |

## The seven failures this exists to catch

**An outline item with no chapter.** The plan and the document disagree, and the gap is exactly
where a supervisor will look first. The word budget rules add the amount side: a chapter that
lands far from its planned length signals an unbalanced argument chain.

**A term defined in two chapters.** The second definition silently redefines the first, and
everything between them now means something slightly different. `_term_key` folds case, spacing
and hyphenation, so `Uptake-Rate` collides with `uptake rate`. When a chapter body really uses a
declared variant, the second name is named with its chapter.

**A claim citing a reference that does not match it — or cannot be found.** The citation exists
but the conclusion was rewritten (topic overlap is measured), or the reference lacks the title
and year a reviewer needs to retrieve it.

**Opposite conclusions in two chapters.** Declared as a direction, so a contradiction is
detectable rather than a matter of reading both chapters carefully. A conclusion without a
direction is reported, because it silently opts out of the contradiction check.

**A cross-reference or figure/table number that no longer resolves.** Cheap to introduce during
revision, invisible until an examiner finds it.

**A table of contents that disagrees with the document.** In both directions: chapters missing
from the TOC, and TOC entries no chapter answers.

**A chapter with no change history, or a revision nobody can trace.** A long document is
revised in rounds; a chapter with no record cannot be reverted or compared, and a term revision
whose other chapters are not listed as affected leaves paragraphs unfindable.

## Runtime: the six steps

Run the same six steps for every case. They keep the deliverable and the audit separate: the
audit checks structure, it never manufactures content.

**Step 0 — read the case.** Read the input case file (mounted at /input/case.json with a task
statement alongside it) and the task text. Copy two things out of the case before anything
else: the case identifier and the declared output contract (the field names the result must
carry). Note what this topic's cases supply: the complete original source arrives as sectioned
editable working chapters, not a completed thesis, and the actual edit targets plus the offline
local workflow scope are explicit in the case's workorder file (organizer-edit-workorder.json
when the case carries one). The bundled resources and preinstalled tools are listed in
environment/resources.yaml. The working chapters become the spec's chapters; the workorder's
edit targets decide which chapters the deliverable must touch.

**Step 1 — route by the shape of the ask.** Match the task wording against the table below and
pick a section. When in doubt, prefer the primary section of this skill: longdoc.

| task wording (representative) | route | spec essentials |
|-|-|-|
| 按提纲写学位论文章节 / 分章工作稿续写 | longdoc | outline + chapters（含 argument_element） |
| 跨章节术语/符号/定义一致性检查 | longdoc | terminology + symbols + chapters.definitions |
| 章节间结论冲突与引用核对 | longdoc | chapters.conclusions + references |
| 导师/评审意见分批改稿，意见拆成可执行项 | longdoc | reviewer_feedback + chapters.changelog |
| 局部修改后受影响段落追踪 | longdoc | changelog（what/why/term/impact） |
| 字数预算分配与实际篇幅对照 | longdoc | outline.word_budget + chapters.word_count |
| 图表编号与交叉引用修复 | longdoc | figures + tables + figure_refs / table_refs |
| 改稿前先抽取单篇文献结论（素材准备） | conclusion_extract | fields + source_text + conclusions |
| 与长文档无关的请求（单段润色、全文翻译） | none | refused as undetermined, never guessed |

**Step 2 — produce the target deliverable first.** Do the actual writing: work chapter by
chapter against the outline and the workorder's edit targets, and write or revise the chapter
text itself, keeping the terminology table, the per-chapter change records and the affected-
chapter list up to date. The audit in later steps checks structure; it cannot read the material
for you, so a hollow spec with a tidy schema is still a failed case.

**Step 3 — assemble the spec.** One JSON object holding the deliverable, the evidence base and
the contract: the case identifier, the section name from step 1, the outline with each item's
argument element and word budget, the front matter, the terminology and symbol tables, the
reference list (each with title and year), the figure and table lists, the chapters (each with
its outline id, argument element, definitions, claims bound to reference keys, conclusions with
a direction, figure/table references, word count, and change records), the reviewer feedback
decomposed into status-tracked actions, and the case's declared output contract fields copied
in as keys (such as the working chapters themselves) so they can be echoed verbatim into the
result. See `examples/spec-contract.json` for the full shape.

**Step 4 — audit.** Run the engine once:

```bash
python scripts/secrun.py --spec examples/spec-contract.json --out /app/output
```

Exit codes: `0` clean, `3` review (only low/medium findings), `4` blocked (any high finding),
`5` undetermined (the case could not be run as declared — unreadable spec, non-object spec,
missing or unknown section). Every exit writes a result file; the exit code never comes from a
traceback.

**Step 5 — fix findings and rerun.** Each finding names a rule and a chapter. Fix the document
(write the missing chapter, merge the duplicated definition, repoint the cross-reference, add
the reason to the change record), never the audit, and rerun. Repeat until exit 0 or 3, or
until a finding genuinely cannot be resolved — then leave it and record why in the run's
limits, because an honest blocked status beats a silenced rule.

**Step 6 — merge the result.** Write the deliverable files under the output directory. The
result file written by the engine already carries: the case identifier, every field of the
declared output contract (values the case carried pass through untouched; the audited status,
findings and counts are filled by the audit; anything else is null with a limits note — never a
fabricated value), findings, severity counts, and limits. Keep that file as the structured
result of the case.

## The spec, field by field

```json
{
  "case_id": "demo-longdoc-001",
  "section": "longdoc",
  "outline": [{"id": "O1", "title": "intro", "argument_element": "question",
               "word_budget": 3000}],
  "front_matter": {"toc": ["intro"], "figure_list": ["Fig 1"],
                   "reference_section": "yes", "appendix": "yes"},
  "terminology": [{"preferred": "uptake rate", "chapter": "1", "variants": []}],
  "symbols": [{"symbol": "r", "meaning": "uptake rate"}],
  "references": [{"key": "doe2020", "title": "coating raises uptake", "year": 2020,
                  "topic": "coating raises uptake"}],
  "figures": [{"number": 1, "caption": "uptake curves"}],
  "tables": [{"number": 1, "caption": "measured uptake rates"}],
  "chapters": [
    {"number": 1, "title": "intro", "outline_id": "O1", "argument_element": "question",
     "word_count": 2800,
     "definitions": [{"term": "uptake rate", "text": "rate of uptake per unit area"}],
     "claims": [{"text": "coating raises uptake", "reference": "doe2020"}],
     "conclusions": [{"statement": "coating raises uptake rate", "direction": "increases"}],
     "figure_refs": [], "table_refs": [],
     "changelog": [{"what": "v1 drafted", "why": "outline O1", "term": "",
                    "impact": []}]}
  ],
  "reviewer_feedback": [{"text": "chapter 2 reads thin", "actions": [{"text": "add the protocol", "status": "pending"}]}],
  "output_contract": {"case_id": "...", "status": "...", "working_chapters": "..."}
}
```

`argument_element` is one of `question`, `method`, `result`, `discussion`, `limitation` — the
five parts the task requires the document to carry. A chapter's `conclusions` need a `direction`
(increases / decreases / no_effect / mixed / conflicting); without one the conclusion cannot be
checked for contradictions. A changelog entry may be a plain string (legacy) or a dict with
`what`, `why`, `term` and `impact` (list of chapter numbers) — the impact check needs the term
to appear in other chapters' definitions, so a revision touching no shared term is never
flagged. Declaring `track_consistency: true` turns on the opt-in checks: every chapter must say
what question it answers (`answers`), which evidence it rests on (`evidence` or
`evidence_plan`), and whether its text is author-written or machine-generated
(`authorship_declared`).

## Worked example（示例）

Input `examples/spec-contract.json` — the spec shown above with five chapters, a declared word
budget per outline item, and a declared output contract of six fields, one of which (the
working chapters) is a deliverable the case carries. Run:

```bash
python scripts/secrun.py --spec examples/spec-contract.json --out /tmp/out
```

Console output（示例，路径随机器不同）:

```json
{"status": "clean", "section": "longdoc", "case_id": "demo-longdoc-001",
 "findings": [], "wrote": "/tmp/out/result.json"}
```

The written result（示例节选，实跑所得）:

```json
{
  "case_id": "demo-longdoc-001",
  "status": "clean",
  "output_contract": {
    "case_id": "demo-longdoc-001",
    "status": "clean",
    "section": "longdoc",
    "working_chapters": {"format": "per-chapter editable working chapters with change records",
                          "carries": ["outline mapping", "terminology table", "changelog per chapter"]},
    "findings": [],
    "severity_counts": {}
  }
}
```

The deliverable key passed through untouched, the audited keys were filled by the audit, and
the case identifier is recorded — exit 0.

## Output contract of the result

`/app/output/result.json` (written by the engine on every exit path):

| field | content |
|-|-|
| case_id | the case identifier, echoed from the spec or the command line |
| status | clean / review / blocked / undetermined |
| section | the audited section |
| findings[] | one per rule hit: rule, severity, message, plus the span (chapter, term, key, outline_id, figure, table) |
| severity_counts | findings by severity |
| checked | items audited (chapter count) |
| limits | what this run could not verify, including any contract field left null |
| output_contract | every declared contract field: case-carried values pass through, audited keys are filled by the audit, the rest are null with a limits note |

## Mapping to the required result sections

| 评分要求的字段（rubric 原词） | 本 Skill 的交付 |
|-|-|
| 目标产物 | 可编辑分章工作稿：chapters 文本（含 outline_id / argument_element / word_count）+ 术语表 + 符号表 + 图表清单，随 result 一并交付 |
| 事实与来源映射 | 每条 claim 绑定 reference 键并做主题重叠核对；引用元数据（title/year）齐备；编号与交叉引用（章/图/表）全部可解析；toc 双向一致 |
| 版本与边界 | 每章 changelog（what/why/term/impact）+ reviewer_feedback 逐条 action 携带 status + limits（不可核验处显式声明）+ case_id 回填 |

## Rules

### Outline and argument（立得住）

| rule | severity | what it proves |
|-|-|-|
| `long.no_chapters` | high | nothing to audit |
| `long.outline_item_unwritten` | high | an outline item has no chapter |
| `long.chapter_not_in_outline` | medium | a chapter maps to a missing outline item |
| `long.argument_element_missing` | high | the reasoning is missing a stage |
| `long.word_budget_off` | medium | a chapter lands >40% away from its planned length |
| `long.word_budget_unmeasured` | low | a budget is declared but no written count is recorded |

### Front and back matter（立得住）

| rule | severity | what it proves |
|-|-|-|
| `long.reference_section_missing` | medium | no reference section |
| `long.figure_list_missing` | medium | figure numbering cannot be checked by a reader |
| `long.appendix_missing` | medium | supporting material has nowhere to live |

### Consistency across chapters（连得上）

| rule | severity | what it proves |
|-|-|-|
| `long.terminology_missing` | high | nothing prevents one concept having two names |
| `long.symbol_table_missing` | medium | symbols cannot be checked for consistent meaning |
| `long.duplicate_definition` | medium | a later chapter silently redefines a term |
| `long.term_variant_declared` | low | a declared variant will appear as a second name |
| `long.term_variant_used` | medium | a chapter body really uses a declared variant |
| `long.conclusion_contradiction` | high | two chapters state opposite conclusions |
| `long.conclusion_without_direction` | medium | a conclusion cannot be checked for contradiction |
| `long.definition_unused` | medium | a definition no later chapter uses |
| `long.chapter_no_question` | medium | a chapter does not say what question it answers (opt-in) |
| `long.evidence_plan_missing` | medium | a chapter does not say which evidence it needs (opt-in) |
| `long.authorship_undeclared` | medium | author vs machine text is not declared (opt-in) |

### Claims, references, numbering（查得清）

| rule | severity | what it proves |
|-|-|-|
| `long.claim_no_citation` | high | a chapter claim tied to nothing |
| `long.citation_unknown` | high | a citation outside the list |
| `long.citation_conclusion_mismatch` | high | the reference does not match the claim |
| `long.questionable_citation` | medium | the reference barely overlaps the claim |
| `long.reference_metadata_incomplete` | medium | a reference lacks title or year |
| `long.numbering_unreadable` | medium | a chapter number is not an integer |
| `long.numbering_gap` | high | chapter numbers not 1..n |
| `long.dangling_crossref` | high | a cross-reference to a missing chapter |
| `long.figure_numbering_gap` | medium | figure numbers not 1..n |
| `long.figure_ref_unknown` | high | the text points at a figure that does not exist |
| `long.table_numbering_gap` | medium | table numbers not 1..n |
| `long.table_ref_unknown` | high | the text points at a table that does not exist |
| `long.toc_incomplete` | medium | the TOC omits an existing chapter |
| `long.toc_entry_unknown` | medium | a TOC entry matches no chapter |

### Revisions and feedback（改得动）

| rule | severity | what it proves |
|-|-|-|
| `long.no_chapter_changelog` | medium | a chapter cannot be reverted or compared |
| `long.change_no_reason` | medium | a revision entry says what changed but not why |
| `long.change_impact_untraced` | medium | a term revision leaves other chapters untraced |
| `long.feedback_not_decomposed` | high | a reviewer comment is not decomposed into actions (opt-in) |
| `long.action_no_status` | medium | an action item carries no status (opt-in) |

### Refusal

| rule | severity | what it proves |
|-|-|-|
| `audit.no_section` | high | the case could not be run as declared: no or unknown section, a non-object spec, or a spec that is not readable JSON — refused with exit 5, never a crash |

## Exception handling

| situation | exit | what happens / what to do |
|-|-|-|
| spec file missing or unreadable | 5 | refusal written with audit.no_section; re-check the path, rerun |
| spec is valid JSON but not an object (array, string, number) | 5 | refusal; wrap the payload in one object and rerun |
| section key missing, empty, or a list/dict instead of a string | 5 | refusal; declare the section from the routing table |
| section name unknown (typo or wrong level) | 5 | refusal naming the section; pick a route from the table |
| chapters slot empty or carries non-objects | 4 | no_chapters fires (non-object entries are skipped); supply chapter objects |
| a chapter number is a string like "III" or absent | 3 | numbering_unreadable fires; use integer numbers, or read the limits |
| a conclusion carries no direction | 3 | conclusion_without_direction; declare increases / decreases / no_effect / mixed / conflicting |
| a claim cites a key not in the references | 4 | citation_unknown; add the reference or fix the key |
| a reference lacks title or year | 3 | reference_metadata_incomplete; complete the metadata |
| a cross-ref or figure/table ref points nowhere | 4 | dangling_crossref / figure_ref_unknown / table_ref_unknown; renumber or repoint |
| a TOC entry matches no chapter | 3 | toc_entry_unknown; align the front matter with the document |
| a changelog entry is a plain string | — | accepted as legacy; the what/why/impact checks need the dict form |
| a term revision names a term other chapters define | 3 | change_impact_untraced; list the affected chapters in impact |
| reviewer_feedback present but track_consistency off | — | feedback checks are opt-in and stay silent; set track_consistency to true |
| chapters carry no body text | — | the variant-in-body and definition-usage checks stay silent; add text to enable them |
| output_contract is a list instead of an object | 0/3/4 | the run completes; the limits name that the contract cannot be echoed |
| a declared contract field the audit cannot derive | 0/3/4 | echoed as null with a limits note; fill it in the deliverable, never fabricate |
| extremely long strings | 0–5 | accepted; messages truncate, nothing crashes |
| rerun with an unchanged spec | — | byte-identical result; the audit is deterministic |

## Limits

- **Chapters arrive as structured items.** The audit does not parse a `.docx` into chapters; a
  text blob has no chapter boundaries to check. The case's working chapters are already
  sectioned, which is exactly the shape the spec needs.
- **Term collision folding is case, space and hyphen only.** A genuine synonym pair
  (`tumour`/`neoplasm`) will not collide unless the terminology table declares it.
- **Contradictions need declared directions.** Two chapters that disagree in prose but declare
  the same direction are not caught; a conclusion without a direction is reported instead of
  silently skipped.
- **Citation mismatch is topic overlap.** A correct citation on unfamiliar wording can read as
  a mismatch; the threshold is deliberately low at 0.15, and the 0.15–0.35 band is reported as
  questionable rather than wrong.
- **No figure or table content.** Only numbering and references are checked, not what the
  figures show.
- **The TOC match is substring-based** ("1 引言" matches a chapter titled 引言); a TOC built
  from page numbers alone will read as matching.
- **Change records are presence-checked**, not compared between versions; the impact check
  needs the shared term to appear in other chapters' definitions.
- **Word budgets compare declared numbers**, not counted text: the chapter's word_count is
  what the author records, and the audit checks the plan against that record.

## Failure handling

| symptom | what to do |
|-|-|
| `outline_item_unwritten` | write the chapter, or drop the outline item |
| `duplicate_definition` | define it once and refer back |
| `term_variant_used` | replace the variant with the preferred form in that chapter |
| `conclusion_contradiction` | decide which chapter is right, then align the other |
| `conclusion_without_direction` | declare the direction the chapter actually claims |
| `citation_conclusion_mismatch` | cite the source that supports the claim as written |
| `reference_metadata_incomplete` | add the title and year a reviewer needs |
| `dangling_crossref` | renumber or repoint the reference |
| `figure_ref_unknown` / `table_ref_unknown` | fix the figure/table number |
| `toc_entry_unknown` / `toc_incomplete` | align the TOC with the chapters |
| `change_impact_untraced` | list the affected chapters in the revision's impact |
| `no_chapter_changelog` | record what changed in the chapter |
| `word_budget_off` | rebalance the argument or update the plan |
| `audit.no_section` (exit 5) | the case could not be run as declared — fix the spec shape and rerun |

## Verification

```bash
python scripts/bench_longdoc.py   # 40 scenarios: one per rule plus repaired-twin guards
python scripts/bench_sections.py  # 51 scenarios: cross-section regression plus false-positive guards
python scripts/bench_contract.py  # 17 scenarios: the delivery contract under clean, refusal and hostile inputs
```

All three pass in full on this machine. The clean baselines must report nothing, so a
detector cannot pass by flagging everything; every new rule carries both a defect scenario
and a repaired-twin guard.

## Requirements

Python 3.9+（3.14 实测）。纯标准库实现，无第三方依赖。

## 创新增益

本 Skill 相比通用 Agent 直接写长文档的核心新增能力（全部为引擎真实运行的机制，bench 覆盖）：

1. **章节级一致性多重比对**：术语经大小写/空格/连字符折叠后跨章比对，重复定义、声明变体在正文中的真实出现均被点名到章——通用 Agent 逐章生成时没有跨章记忆，无法自证一名一形。
2. **论断-文献主题重叠绑定**：每条章节论断必须绑定 reference 键，主题重叠低于阈值报结论被改写，0.15–0.35 区间报存疑引用，引用缺 title/year 报不可检索——把"引用了但结论对不上"变成三档可判定规则。
3. **方向声明的矛盾检测**：结论必须携带 direction，两章方向相反即报矛盾；无方向的结论单独报出，使其无法静默逃过矛盾检查。
4. **编号闭包检查**：章号、图号、表号三套 1..n 闭包加交叉引用解析，toc 与文档双向一致（缺章与多余条目都报）——改稿期最容易引入、答辩期才暴露的断链全部前移到提交前。
5. **修改影响面追踪**：changelog 条目携带 what/why/term/impact，改了共享术语而未列出受影响章节即报，导师意见强制分解为带 status 的 action——"改得动、可回退"成为结构而非口头承诺。
6. **词数预算-实写对照**：提纲级 word_budget 与章节 word_count 偏差超过 40% 报出，论证链失衡在写作期可见。
7. **契约直通的 result.json**：case_id 与 output_contract 全字段回填——案例自带的值原样直通、审计派生的键由审计填写、其余置 null 并写入 limits，拒绝路径（exit 5）同样保留 case_id，部分结果也保持交付契约。
8. **引擎级崩溃免疫**：类型错位（section 放列表、chapters 放字符串、spec 不是对象）一律降级为发现项或拒绝，退出码只有 0/3/4/5 五种，绝不以 traceback 收场。

## 生态贡献

1. **SKILL.md**：用途、适用条件、六步调用方式、任务措辞路由表、与评分要求三段的逐项映射、异常处置表（19 行）、限制与自查方法齐备；明确记录本题型案例以分章可编辑工作稿交付、编辑目标见 workorder 的输入约定。
2. **scripts/**：纯标准库（Python 3.9+，3.14 实测），模块可独立导入，规则库可经 spec 配置扩展；本包为独立副本，不依赖其他包。
3. **examples/spec.json 与 examples/spec-contract.json**：最小调用示例与带契约回填的完整示例，示意输出标注为示例且为实跑所得。
4. **bench_longdoc.py**：40 个场景，每条 longdoc 规则一个缺陷场景加修复孪生守卫场景，clean 基线必须零发现；report_longdoc.json 为可复跑证据。
5. **bench_sections.py**：51 个跨 section 回归场景，防误报守卫覆盖中文与类型错位输入。
6. **bench_contract.py**：17 个契约回归场景（clean 契约回填、拒绝保契约、rerun 幂等、敌意输入拒收），report_contract.json 为可复跑证据。
7. **章节检查清单**：outline/front_matter/terminology/symbols/references/chapters 的字段模板可直接迁移到任何学位论文或多章报告场景。
8. **规则词表**：rule id 稳定命名并与引擎一一对应（文档-引擎一致性由门禁检查），可作为同类长文档一致性任务的共享词汇。
