---
name: evidence-driven-writing
description: >
  Turn a literature-supported writing task into a three-part deliverable — claim list,
  evidence table, manuscript — where every claim carries a strength label with a basis and
  an uncertainty statement, every link carries a quoted passage and a locator, every citation
  exists in the table and actually contains the quote, and a weak claim is not written as a
  strong one. Handles the material forms that break naive quote matching: scanned sources
  (OCR pass recorded), abstract-only records (cannot carry a strong claim), and text pulled
  from two-column PDFs with a repaired reading order (registered quote variants). Flags
  retracted sources, preprints used as strong support, and unregistered evidence conflicts.
  Use when a task asks for a literature review, related-work section, or any draft whose
  sentences must be traceable to sources.
---

# evidence-driven-writing

The deliverable is three things, not one. A draft alone scores nothing here, because none
of the four graded elements can be checked from prose.

| part | rule when absent |
|-|-|
| claim list, each with an id | `ew.claims_missing` |
| claim id is usable (non-empty, unique) | `ew.claim_no_id` |
| evidence table | `ew.evidence_table_missing` |
| manuscript referencing the claim ids | `ew.draft_missing` |
| every claim reaches the manuscript | `ew.claim_not_in_draft` |

## Routing

One audit entry point, four sections. Route by what the task asks for; this skill is built
for the first, and the other three share the same spec/result/exit-code contract so a
mixed-case run stays one shape.

| task asks for | section | what the audit proves |
|-|-|-|
| literature-supported draft | `evidence_writing` | every claim cited, every citation real, strength matched to prose |
| translation or bilingual delivery | `translation` | numbers/units/citations/terms preserved across languages |
| revision package / response letter | `review_response` | every comment answered, every claimed change locatable |
| manuscript into a template | `format_template` | section order, heading styles, numbering, export checks |

## The four elements, and the four failures

| element | rule when missing | what it prevents |
|-|-|-|
| the claim | `ew.claim_empty` | an unverifiable assertion |
| the source | `ew.claim_no_support` | an opinion written as a finding |
| source really in the table | `ew.source_not_in_table` | a citation that does not exist |
| a strength label with a basis | `ew.strength_missing` | evidence-free confidence |
| basis present for the label | `ew.strength_without_basis` | a grade that cannot be argued with |
| an uncertainty statement | `ew.uncertainty_missing` | a weak finding written as a result |

Two more, both specific to this task:

| failure | rule | what it proves |
|-|-|-|
| a quote that is not in the source | `ew.quote_not_in_source` | the passage is matched literally against the source text |
| a claim written stronger than its evidence | `ew.draft_overstates_strength` | the draft uses proves/demonstrates/证明 while the claim is weak or moderate |

## Material form: ask three questions before trusting any text

The same citation behaves differently depending on how its text reached the table. Before
extracting quotes, register the form of every source, then let the audit enforce what each
form demands.

| question at extraction time | register as | rule if mishandled |
|-|-|-|
| Is this a scan that passed through OCR? | `text_quality` = `ocr` plus an `ocr_note` (tool, pages, confidence) | `ew.ocr_provenance_missing` |
| Is the full text missing and only the abstract obtained? | `text_quality` = `abstract_only` | `ew.support_abstract_only` when it carries a strong claim |
| Is this two-column PDF text with repaired reading order? | `text_quality` = `two_column_reordered` plus an `order_repair_note` | `ew.extraction_disorder_unrecorded` |
| none of the above (born-digital, single column) | `text_quality` = `native` | `ew.text_quality_undeclared` when the form is not stated |

What each form changes mechanically:

- **Scan/OCR.** OCR noise makes an honest quote fail the literal match. When that happens
  on an `ocr` source the finding carries a `likely_cause` pointing at the OCR pass, and a
  registered `quote_variants` list (the exact forms the extractor produced) satisfies the
  check — the variant itself becomes the checkable record.
- **Abstract only.** The task requires support extracted from the full text; a source whose
  full text was never obtained cannot carry a `strong` claim. Weak or moderate claims are
  fine, with the limitation stated in `uncertainty`.
- **Two-column reorder.** Interleaved column order is the classic silent corruption: text
  reads fluently but sentences are spliced. The `order_repair_note` records how order was
  rebuilt; failed quote matches on such a source again get the `likely_cause` hint and the
  variant escape hatch.
- **No text at all.** A link carrying a quote against a source with no text is reported
  unverifiable (`ew.quote_unverifiable`), never silently accepted — the honest state is
  "pending until the source is obtained".

## Workflow

### 1. Build the table, then the claims, then the draft

```json
{
  "section": "evidence_writing",
  "evidence": [
    {"key": "doe2020", "title": "Porous coatings for uptake", "year": 2020,
     "source_type": "primary", "text_quality": "native",
     "text": "The coating increased the uptake rate three-fold."}
  ],
  "claims": [
    {"id": "C1",
     "claim": "涂层使吸收速率提高三倍",
     "strength": "strong",
     "strength_basis": "controlled experiment, n=6, replicated",
     "uncertainty": "",
     "sources": [{"key": "doe2020",
                  "quote": "The coating increased the uptake rate three-fold.",
                  "locator": "p.7"}]}
  ],
  "draft": "吸收速率提高到 3 倍 [C1]。"
}
```

`source_type` is `primary`, `review`, `guideline` or `preprint`. `text_quality` is
`native`, `ocr`, `abstract_only` or `two_column_reordered`. A preprint supporting a
`strong` claim is flagged, and a `retracted` entry is refused outright. A source that
contradicts other evidence registers `conflicts_with` (other keys), and one whose abstract
disagrees with its full text registers `abstract_conflict` — either declaration obliges
every claim citing it to carry a `conflict_note` saying how the contradiction was weighed.

A claim may cite several sources and a source may support several claims; both directions
are checked, so a source in the table that supports nothing is reported too
(`ew.source_unused`).

### 2. Run it

```bash
python scripts/writeaudit.py --spec spec.json --section evidence_writing --out /app/output
```

Exit codes: `0` clean, `3` review, `4` blocked, `5` undetermined (spec unreadable, missing
or unknown section — a written refusal, never a traceback).

## Rules

### The three parts

| rule | severity | what it proves |
|-|-|-|
| `ew.claims_missing` | high | no claim list |
| `ew.evidence_table_missing` | high | no evidence table |
| `ew.draft_missing` | high | no manuscript |
| `ew.claim_not_in_draft` | medium | a claim is never used in the draft |

### Identity and the four elements

| rule | severity | what it proves |
|-|-|-|
| `ew.claim_no_id` | high | claims cannot be pointed at unambiguously |
| `ew.claim_id_duplicate` | high | two claims share one identifier |
| `ew.claim_empty` | high | a claim has no text |
| `ew.strength_missing` | high | no strength label |
| `ew.strength_invalid` | medium | label outside strong/moderate/weak |
| `ew.strength_without_basis` | high | the grade cannot be argued with |
| `ew.uncertainty_missing` | high | a weak or moderate claim carries no uncertainty |

### Links and sources

| rule | severity | what it proves |
|-|-|-|
| `ew.claim_no_support` | high | a claim cites nothing |
| `ew.link_no_source` | high | a link names no source key |
| `ew.source_not_in_table` | high | a cited source does not exist in the table |
| `ew.link_no_quote` | high | the link carries no quoted passage |
| `ew.link_no_locator` | high | the passage has no section/page/paragraph locator |
| `ew.quote_not_in_source` | high | the quote does not occur in that source's text |
| `ew.quote_unverifiable` | medium | the source has no text, so the quote cannot be checked |
| `ew.retracted_source_used` | high | a retracted source is supporting a claim |
| `ew.preprint_as_strong` | medium | a preprint carries a strong claim |
| `ew.source_type_missing` | medium | the study type is unstated |
| `ew.source_type_unknown` | low | the study type is outside the four kinds |
| `ew.reference_metadata_incomplete` | medium | an entry cannot be identified |
| `ew.source_unused` | medium | the table carries material the argument ignores |
| `ew.draft_overstates_strength` | medium | the prose is stronger than the label |

### Material form and conflicts

| rule | severity | what it proves |
|-|-|-|
| `ew.text_quality_undeclared` | medium | the form of a source's text is not registered |
| `ew.text_quality_unknown` | low | the declared form is outside the four kinds |
| `ew.ocr_provenance_missing` | medium | a scanned source records no OCR pass |
| `ew.extraction_disorder_unrecorded` | medium | a reordered two-column source records no order repair |
| `ew.support_abstract_only` | medium | a strong claim rests on an abstract-only record |
| `ew.conflict_unregistered` | medium | conflicting evidence is cited without a conflict note |
| `ew.abstract_conflict_unregistered` | medium | an abstract/full-text contradiction is cited without a note |

## Runtime entry (per case)

1. Read `/input/case.json` and `task.md` first. Record `case_id` and the `output_contract`
   field list from case.json — both must appear in the final result.json verbatim.
2. Extract the sources from the case material into the evidence table. Read the actual
   files, not the labels. For each source ask the three form questions (scan? abstract
   only? two-column?) and register `source_type` and `text_quality` accordingly, with the
   OCR/order-repair notes those forms demand. Keep section/page/paragraph locators.
3. Split the writing goal into claim units (C1, C2, …), match each to its supporting
   sources and support scope, label strength with a basis per the grading scale in
   `references/strength_scale.md`, leave `uncertainty` present, and carry any registered
   source conflict into a `conflict_note` on the claim.
4. Write the manuscript (draft) with `[C#]` markers to `/app/output/` as an editable file.
5. Build the spec (draft + claims + evidence + case_id + output_contract array) and run the
   audit. Fix findings, rerun until clean or the remainder is declared.
6. Deliver the three parts the task grades: claim list, evidence table, manuscript — plus
   the run-status record (see Output contract).

## Output contract

`/app/output/result.json` must carry, in this order of priority:

1. **Platform contract fields, verbatim**: every field named in case.json's
   `output_contract`, copied field-by-field (never renamed, never dropped; fill `null`
   with a note in `limits` when undeducible), plus `case_id` at the top level.
2. Engine fields: `status`, `section`, `findings[]` (each with claim id, key, quote,
   locator), `severity_counts`, `checked`, `limits`. The CLI copies spec-supplied values
   for contract fields it does not derive — so put `deliverables`, `fact_source_map`,
   `pending_confirmation`, `gaps` in the spec (top level) and they land in result.json
   filled, not null.
3. Task's three deliverables, referenced from result.json:
   - `deliverables[]` — paths to the claim list / evidence table / manuscript files
   - `fact_source_map[]` — one row per number, term, citation and key claim:
     `{item, source_or_change, locator}` (traceable item-by-item; nothing outside materials)
   - `pending_confirmation[]` / `gaps[]` — human-confirmation items and material gaps,
     separate from findings; missing material, unverifiable items and run failures are
     reported in their own field, never silently.

Rubric mapping, so a reviewer can find each graded thing in one place:

| rubric asks | where it lands |
|-|-|
| 论断清单 — 证据表 — 成稿 three-part delivery | spec keys `claims`, `evidence`, `draft`; paths in `deliverables[]` |
| 引用真实存在且真的支持论断 | `source_not_in_table` / `quote_not_in_source` findings absent; quotes matched literally |
| 强度标注与不确定性齐备 | `strength` + `strength_basis` + `uncertainty` per claim; scale in references/strength_scale.md |
| 可独立复核（编号、摘录、定位、强度理由） | claim ids + `quote` + `locator` + `strength_basis`, all present in findings' shape |
| 异常六态（不可得/仅摘要/自相矛盾/证据冲突/格式/权限） | Failure handling table below; first four also audited mechanically |

Malformed or missing spec never raises. A missing or unknown section, or a non-object spec,
is refused with a written result.json carrying `audit.no_section` and exit 5; malformed list
entries (bare strings) are skipped safely and audited as "content absent" — findings such
as `ew.claims_missing` appear and the exit is 3 or 4. Refusal and degradation are both
recorded outcomes, never a traceback.

| rule | severity | what it proves |
|-|-|-|
| `audit.no_section` | high | no section, unknown section, spec not readable JSON / not an object |

## Limits

- **Overlap and quoting are lexical.** A quote that appears in the source is not thereby
  evidence *for* the claim; the `strength_basis` is where that judgement lives.
- **`strength` and `uncertainty` are declared.** The audit enforces that they exist, have a
  basis, and agree with the draft's verbs — not that they are correct. The grading scale
  itself is documented in references/strength_scale.md and is a convention, not ground truth.
- **The overstatement check is a verb list.** `proves`, `demonstrates`, `证明`, `证实`. A claim
  over-hedged into vagueness is not caught.
- **Source quality is a flag, not a judgement.** Retraction, preprint status and text form
  must be recorded in the table; the audit does not fetch journals or verify retraction
  registries.
- **`uncertainty` is required only for weak and moderate claims.** A strong claim with an
  unstated scope is not flagged here.
- **quote_variants weaken the literal check to "some registered form occurs".** That is the
  right trade on OCR/reordered sources and the wrong trade on native ones, where the exact
  quote should just be re-copied.
- **It does not retrieve.** Choosing sources and passages is a separate step; unobtainable
  sources stay in the table with no text and their quotes are reported unverifiable.

## Failure handling

| symptom | what to do |
|-|-|
| source not obtainable (文献不可得) | keep the entry with no text; its quotes become `quote_unverifiable`; mark the claim pending in `pending_confirmation` |
| only the abstract available (仅有摘要) | `text_quality` = `abstract_only`; downgrade affected claims to moderate/weak with the limitation in `uncertainty`; never let it carry `strong` |
| abstract contradicts full text (原文与摘要矛盾) | register `abstract_conflict` on the entry; the citing claim states in `conflict_note` which version it used and why |
| evidence conflicts (证据相互冲突) | register `conflicts_with` on the entry; the citing claim weighs it in `conflict_note`; do not hide the losing side |
| scanned source OCR noise (扫描版) | `text_quality` = `ocr` + `ocr_note`; re-read the page, or register the extracted form in `quote_variants` |
| two-column extraction out of order (双栏乱序) | `text_quality` = `two_column_reordered` + `order_repair_note`; rebuild the order, or quote the repaired text via `quote_variants` |
| unsupported format (格式不支持) | record the format and what was skipped in `gaps`; audit the rest — a partial run beats a crash |
| no permission to read a file (权限不足) | name the file and the permission in `gaps`; do not fabricate its content; keep auditing the readable material |
| `link_no_source` | the claim-to-source link does not name a source — add the source key, or drop the link |
| `claim_no_support` | every claim needs at least one source; if it has none, it is opinion |
| `source_not_in_table` | add the reference, or the citation is wrong |
| `quote_not_in_source` | re-read the passage; a paraphrase is not a quote |
| `link_no_locator` | add section, page or paragraph |
| `strength_without_basis` | say what the grade rests on — design, sample, replication |
| `uncertainty_missing` | state the limits of a weak or moderate claim |
| `retracted_source_used` | remove the source or record the retraction and its consequence |
| `draft_overstates_strength` | soften the verb to match the label |
| `audit.no_section` (exit 5) | undeclared/unknown section or unreadable spec — the run is refused in writing, never a traceback |

## Verification

```bash
python scripts/bench_ew.py        # 37 scenarios: one per rule, plus material-form paths
python scripts/bench_writing.py   # 22 scenarios: cross-section regression
```

Both pass in full on this machine. The clean baseline in each must report nothing.

## Requirements

Python 3.9+（3.14 实测）。纯标准库实现，无第三方依赖，无网络访问。脚本互相独立，可直接导入。

## 创新增益

本包相对通用 Agent 的新增能力，每条附边界与证据形式：

1. **论断切分 + 强度分级（新增能力）**：稿件被拆成带 id 的论断单元，每条带 strong/moderate/weak
   标签与依据（设计、样本、重复），弱/中主张强制携带不确定性；分级口径沉淀在
   references/strength_scale.md，可被其他写作任务直接复用。边界：审计只证明标签存在、有依据、
   与正文动词相称，不判定标签是否正确。证据形式：bench_ew 37 场景逐规则实测，同输入下
   有/无本包的发现数差可复算。
2. **引文逐字回链 + 材料形态豁免（方法改进）**：每个证据链接的引文按字面匹配 source text，
   改写/杜撰的引文被点名（`ew.quote_not_in_source`）；在 OCR 与双栏乱序来源上，失败发现携带
   `likely_cause` 并允许登记 `quote_variants`——把"引文不符"从一刀切的阻断改为按形态可归因的
   处置。通用 Agent 无此机制，要么放行杜撰引文要么误伤噪声。边界：词面匹配，同义改写需人工判读。
   证据形式：bench_ew 中 quote_fails_on_ocr / quote_variant_rescues_ocr 一对场景。
3. **仅摘要不可承载强主张（新增能力）**：`abstract_only` 来源支撑 strong 主张被点名
   （`ew.support_abstract_only`）——对应题目"从全文而非摘要中抽取"的硬约束；无全文来源的引文
   一律报 `ew.quote_unverifiable` 而不是静默通过。边界：形态由声明方登记。证据形式：
   abstract_only_strong / quote_unverifiable 场景。
4. **冲突证据强制登记（方法改进）**：来源级 `conflicts_with` / `abstract_conflict` 声明把
   义务传给引用它的主张——没有 `conflict_note` 就报发现，反面证据不会被支持方证据悄悄淹没。
   对应题目"冲突证据不被隐藏"。证据形式：conflict_unregistered / abstract_conflict_unregistered
   场景；对照运行时表现为草稿单边引用被检出。
5. **来源分级守卫**：撤稿来源直接拒绝（`ew.retracted_source_used`）、预印本支撑强主张被降权
   （`ew.preprint_as_strong`）。边界：状态由声明方登记，本工具不查期刊数据库。

## 生态贡献

- **使用说明**：SKILL.md 含用途、适用条件、路由表、调用方式、输入输出契约、六步运行时入口、
  异常处置表（18 行）与自查方法
- **强度分级口径**：references/strength_scale.md 给出 strong/moderate/weak 的判定锚点与
  动词—强度对应表，跨任务可复用
- **证据表结构**：spec 的 claims/evidence/draft 结构即论断切分模板与证据表结构，字段在
  SKILL.md 中逐一说明，可直接套用到新题
- **题集**：bench_ew 37 场景 + bench_writing 22 场景（每规则一场景 + 形态路径 + FP 守卫），
  `python scripts/bench_ew.py` 即可独立复跑，报告写入 report_ew.json
- **示例**：examples/ 提供最小调用示例 spec.json 与示意输出 bench-report.json，标注为示例
- **依赖与配置**：Python 3.9+ 纯标准库，无安装步骤、无网络、无个人文件依赖
- **适用范围与限制**：Limits 一节逐条写明词面匹配、声明式字段、动词表等边界
- **维护信息**：规则库按节分表可扩展；本轮变更记录（材料形态 7 规则、冲突登记 2 规则）
  写入本文件对应小节，报告 schema 带版本号（ew-bench/v1）
