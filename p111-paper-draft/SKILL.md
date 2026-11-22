---
name: paper-draft
description: >
  Audit a manuscript draft written from supplied materials, figures and literature, so a
  reader can check it: each factual sentence must cite a reference or carry a material
  anchor with a locatable source; numbers must appear in the material they anchor to and
  the sample size must match the records; figure captions must agree with the figure data;
  the abstract must not contain numbers the body lacks; the glossary terminology must not
  drift; causal wording is refused for observational designs; and the required
  declarations, change log and human-confirmation points must be present.
  Use when a task asks for a section draft, manuscript, or results write-up built on given
  experimental records and references, or for a fact-consistency pass over such a draft.
---

# paper-draft

The deliverable is a draft that can enter revision, which means a reader can check it:

| scoring point | rule |
|-|-|
| a real section draft, not an outline | `pd.draft_missing`, `pd.sections_missing` |
| facts matching the materials | `pd.value_not_in_materials`, `pd.sample_size_mismatch`, `pd.figure_caption_mismatch` |
| every factual claim tracing to a material **and** a reference | `pd.uncited_claim`, `pd.material_no_locator`, `pd.unknown_source` |
| template sections, figures, references, declarations | `pd.sections_missing`, `pd.declaration_missing` |
| terminology and abbreviations uniform | `pd.term_variant`, `pd.abbreviation_not_introduced` |
| the revision trail and the human-confirmation list | `pd.change_log_missing`, `pd.review_points_missing` |

## The failures this exists to catch

**A number with no trace.** The draft says 9 mM and the material says 3 mM. Numbers are
compared against the text of the material the sentence anchors to, with `{M1}`-style anchors.

**A sample size the records do not state.** The draft says n = 12 where the anchored record
says n = 6. Statistics are exempt from the general number check (a p-value is not a
measurement), so the sample size gets its own comparison: it fires only when both sides
state an n and they never agree.

**A claim with no reference.** Asserting sentences need `[doe2020]`. The check runs **per
line**, then per sentence — a citation on the last line must not vouch for a claim on the
first, which is exactly what a whole-document scan would allow.

**A caption disagreeing with its figure.** The figure data says `three-fold`; the caption omits
it. Captions are checked against the figure's own values.

**A trend written as a cause.** "The coating causes higher uptake" in an observational study.

**An abstract the body does not support.** A number in the abstract that appears nowhere in the
draft means the two halves disagree.

**Terminology drift.** The glossary declares one preferred form; the draft uses a variant, or
uses an abbreviation before introducing it.

## Runtime: the six steps

Run the same six steps for every case. They keep the deliverable and the audit separate:
the audit checks structure and traceability, it never manufactures content.

**Step 0 — read the case.** Read the input case file and the task statement. Copy two
things out of the case before anything else: the case identifier and the declared output
contract (the field names the result must carry). Also read the supplied materials
(records, figures, references) — the actual files are the fact base, never the label on
the folder.

**Step 1 — route by the shape of the ask.** Match the task wording against the table
below and pick a section. When in doubt, prefer the primary section of this skill.

| task wording (representative) | route | spec essentials |
|-|-|-|
| 依据实验记录写章节稿/初稿/结果段 | paper_draft | draft + materials + references |
| 校对已成稿：事实、引用、图注核对 | paper_draft | 成稿放入 draft，材料放入 materials |
| 图表与正文三向对齐检查 | paper_draft | draft + materials + figures |
| 引用核对：每条引用是否支撑所在论断 | paper_draft | draft + references |
| 结构诊断：论证跳跃、段落关系、结论范围 | structure_logic | manuscript_text + diagnosis + suggestions |
| 结果与讨论章：显著性、文献对话、局限 | results_discussion | results_text + discussion_text + literature |
| 多章长文组织/章节约束 | longdoc | outline + chapters + front_matter |
| 研究提案/开题报告结构 | proposal | elements + objectives + route |
| 科普化改写/传播产物 | dissemination | text + audience + evidence |
| 与写作无关的请求（全文翻译、纯摘要压缩） | none | refused as undetermined, never guessed |

**Step 2 — produce the target deliverable first.** Do the actual writing or the actual
fact pass: draft the section from the materials with anchors and citations in place, or
read the given draft against the records. The audit in later steps checks structure and
traceability; it cannot write the manuscript for you, so a hollow spec with a tidy schema
is still a failed case.

**Step 3 — assemble the spec.** One JSON object holding the deliverable, the evidence
base and the contract: the case identifier, the section name from step 1, the draft
text with `{M}` material anchors and `[key]` reference keys, the material index (each
entry with a locator and its own text), the reference list, figures with captions and
their own values, declarations, change log, and the case's declared output contract
fields copied in as keys (such as the deliverable file descriptor) so they can be echoed
verbatim into the result. See `examples/spec-contract.json` for the full shape.

**Step 4 — audit.** Run the engine once:

```bash
python scripts/secrun.py --spec examples/spec-contract.json --out /app/output
```

Exit codes: `0` clean, `3` review (only low/medium findings), `4` blocked (any high
finding), `5` undetermined (the case could not be run as declared — unreadable spec,
non-object spec, missing or unknown section). Every exit writes a result file; exit
never comes from a traceback.

**Step 5 — fix findings and rerun.** Each finding names a rule and a sentence. Fix the
draft (add the citation, correct the number against the record, anchor the sentence,
introduce the abbreviation), never the audit, and rerun. Repeat until exit 0 or 3, or
until a finding genuinely cannot be resolved — then leave it, record it as a
human-confirmation point, and say why in the run's limits, because an honest blocked
status beats a silenced rule.

**Step 6 — merge the result.** Write the deliverable files under the output directory
(the draft itself in an editable format, plus the material-to-claim mapping). The result
file written by the engine already carries: the case identifier, every field of the
declared output contract (values the case carried pass through untouched; the audited
status, findings and counts are filled by the audit; anything else is null with a limits
note — never a fabricated value), findings, severity counts, and limits. Keep that file
as the structured result of the case.

## The spec, field by field

```json
{
  "case_id": "demo-draft-001",
  "section": "paper_draft",
  "draft": "1 Introduction\nThe coating raises uptake [doe2020] {M1}.\n2 Methods\nWe measured 3 mM samples with n = 6 {M2}.\n3 Results\nUptake rose three-fold [doe2020] {M1} (Fig 1).\n",
  "abstract": "The coating raised uptake three-fold.",
  "design": "experimental",
  "template": {"sections": ["introduction", "methods", "results"]},
  "materials": [
    {"id": "M1", "locator": "run01.csv row 4",
     "text": "uptake rose three-fold with the coating"},
    {"id": "M2", "locator": "notes.md 12:04",
     "text": "samples were prepared at 3 mM with n = 6"}
  ],
  "references": [
    {"key": "doe2020", "authors": "Doe J", "year": 2020, "journal": "J Uptake",
     "topic": "coating raises uptake", "doi": "10.1000/x"}
  ],
  "figures": [{"id": "Fig 1", "caption": "Uptake rose three-fold with the coating",
               "values": ["three-fold"]}],
  "glossary": {"uptake rate": {"preferred": "uptake rate", "variants": ["absorption rate"]}},
  "declarations": {"data_availability": "on request", "author_contributions": "all authors",
                   "competing_interests": "none", "funding": "grant 123"},
  "change_log": ["v1 initial", "v2 anchored methods to records"],
  "require_review_points": true,
  "review_points": ["confirm the 3 mM preparation step against lab notes"],
  "output_contract": {"case_id": "...", "status": "...", "manuscript_file": "..."}
}
```

Two different anchors, deliberately:

- `{M1}` — a **material** anchor, pointing into the data. A number must appear in that
  material's `text`; the sample size must be the one that text states.
- `[doe2020]` — a **reference** key, pointing into the literature. An asserting sentence needs
  one.

`glossary` is opt-in: concept name to preferred form, variants and abbreviation. When it is
declared, the draft is checked against it; when it is not, no terminology findings are
produced. `require_review_points` is opt-in the same way: a case that asks for
fact-consistency checking owes a list of points a human must confirm.

## Worked example（示例）

Input `examples/spec-contract.json` — the spec shown above plus a declared output
contract with five fields, one of which (`manuscript_file`) is a deliverable descriptor
the case itself carries. Run:

```bash
python scripts/secrun.py --spec examples/spec-contract.json --out /tmp/out
```

Console output（示例，路径随机器不同）:

```json
{"status": "clean", "section": "paper_draft", "case_id": "demo-draft-001",
 "findings": [], "wrote": "/tmp/out/result.json"}
```

The written result（示例节选，实跑所得）:

```json
{
  "case_id": "demo-draft-001",
  "status": "clean",
  "checked": {"section": "paper_draft", "items": 2},
  "output_contract": {
    "case_id": "demo-draft-001",
    "status": "clean",
    "manuscript_file": {"format": "markdown", "path": "draft.md"},
    "findings": [],
    "severity_counts": {}
  }
}
```

The deliverable key passed through untouched, the audited keys were filled by the audit,
and the case identifier is recorded — exit 0.

## Output contract of the result

`/app/output/result.json` (written by the engine on every exit path):

| field | content |
|-|-|
| case_id | the case identifier, echoed from the spec or the command line |
| status | clean / review / blocked / undetermined |
| section | the audited section |
| findings[] | one per rule hit: rule, severity, message, sentence index, material, key, value |
| severity_counts | findings by severity |
| checked | items audited |
| limits | what this run could not verify, including any contract field left null |
| output_contract | every declared contract field: case-carried values pass through, audited keys are filled by the audit, the rest are null with a limits note |

## Mapping to the required result sections

| 评分要求的字段（原词） | 本 Skill 的交付 |
|-|-|
| 目标产物 | 可继续编辑的稿件本体（Markdown/文本，含章节层级、图注编号、锚点与引用标记），随 result 一并交付 |
| 事实与来源映射 | `{M}` 材料锚点 + `[key]` 引用键逐句对应；数值必须出现在锚定材料文本中；findings 给出每处不符的句子索引 |
| 版本与边界 | change_log 修改留痕 + review_points 人工确认项 + limits（材料缺口与不可判定项）+ status |

## Rules

### Structure and declarations

| rule | severity | what it proves |
|-|-|-|
| `pd.draft_missing` | high | nothing to review |
| `pd.sections_missing` | high | a template section is absent |
| `pd.declaration_missing` | medium | data availability / contributions / COI / funding missing |

### Materials

| rule | severity | what it proves |
|-|-|-|
| `pd.materials_missing` | high | no index, so nothing is traceable |
| `pd.material_no_locator` | high | a material cannot be found |
| `pd.material_unknown` | high | a `{M}` anchor the index does not contain |
| `pd.material_unused` | medium | the index carries material the draft ignores |

### Claims, citations, values

| rule | severity | what it proves |
|-|-|-|
| `pd.uncited_claim` | high | an asserting sentence with no reference |
| `pd.unknown_source` | high | a citation outside the reference list |
| `pd.citation_mismatch` | medium | the reference topic barely overlaps the sentence |
| `pd.citation_padding` | low | four or more references on one sentence |
| `pd.value_not_in_materials` | high | a number absent from the material it anchors to |
| `pd.sample_size_mismatch` | medium | an n = value the anchored record does not state |
| `pd.trend_as_causation` | high | causal wording for an observational design |

### Figures, abstract, references, trail

| rule | severity | what it proves |
|-|-|-|
| `pd.figure_caption_mismatch` | high | a caption omits a value the figure has |
| `pd.figure_caption_missing` | high | a figure with no caption |
| `pd.figure_uncited` | medium | a figure never referred to in the text |
| `pd.figure_numbering_gap` | medium | figure numbers skip, which reads as a deleted figure the text may still cite |
| `pd.abstract_result_conflict` | high | a number in the abstract absent from the body |
| `pd.term_variant` | medium | the draft uses a variant where the glossary declares one preferred form |
| `pd.abbreviation_not_introduced` | low | an abbreviation used before its full form appears |
| `pd.reference_metadata_incomplete` | medium | authors / year / journal missing |
| `pd.reference_no_doi` | low | a reference declared `needs_doi` carries no DOI |
| `pd.change_log_missing` | medium | the revision trail is lost |
| `pd.review_points_missing` | medium | a fact-consistency case owes human-confirmation points and records none |

### Refusal

| rule | severity | what it proves |
|-|-|-|
| `audit.no_section` | high | the case could not be run as declared: no or unknown section, a non-object spec, or a spec that is not readable JSON — refused with exit 5, never a crash |

## Exception handling

| situation | exit | what happens / what to do |
|-|-|-|
| spec file missing or unreadable | 5 | refusal written with audit.no_section; re-check the path, rerun |
| spec is valid JSON but not an object (array, string, number) | 5 | refusal; wrap the payload in one object and rerun |
| section key missing, empty or not a string | 5 | refusal; declare the section from the routing table |
| section name unknown (typo or wrong level) | 5 | refusal; pick a route from the table |
| draft slot empty or whitespace only | 4 | draft_missing; supply the manuscript text |
| materials slot carries a string or number instead of a list | 4 | degrades to materials_missing; supply a list of objects |
| an entry of materials/references/figures is a bare string | 4 | the entry is skipped, its checks cannot fire; supply objects |
| template slot carries a string instead of an object | 4/3 | template ignored (sections check cannot fire); supply an object with a sections list |
| declarations slot carries a string | 4/3 | degrades to declaration_missing for all four; supply an object |
| a value slot is non-numeric in a figure's values | 3/4 | values are compared as strings; keep them as the figure states them |
| materials declared but the draft cites none | 3/4 | material_unused plus any unanchored claim; anchor sentences or trim the index |
| require_review_points set with an empty list | 3 | review_points_missing; record the human-confirmation points |
| glossary declared with an empty object | 0 | nothing to check, no findings; a non-object glossary is ignored |
| source text missing from a material entry | 0/3/4 | the value check for that anchor is skipped, not silently passed; supply the record text |
| rerun with an unchanged spec | — | byte-identical result; the audit is deterministic |
| extremely long draft strings | 0–5 | accepted; messages truncate to 100 chars, nothing crashes |

## Limits

- **Checks run per line, then per sentence.** A very long paragraph is still one unit per line;
  a claim and its citation must sit in the same line.
- **Materials must carry their own text.** The value check compares against the material's
  `text`; without it the number cannot be checked and is not compared.
- **A sentence anchored to a material is attributed.** `{M}` markers are the declared
  provenance for data; a factual sentence carrying one does not also need a reference key.
  Never attach a reference that does not exist just to silence `pd.uncited_claim`.
- **Statistics are exempt from the number checks.** p-values, test statistics with df, R2
  and CI bounds carry no unit by convention and are not measurements; they are never flagged
  as unit-less and never need to appear in the material text. The sample size is the one
  statistic that gets its own comparison — against the anchored record, and only when the
  record states one. Do not delete correct statistics from the draft to silence a finding.
- **The sample-size rule needs both sides.** A draft n = 12 with no n in the anchored
  material stays silent; the audit does not invent a sample size the records never gave.
- **Assertion detection is verb-stem based**, so a noun-phrase claim can pass uncited.
- **Citation relevance is keyword overlap.** A genuinely relevant source on an unfamiliar topic
  may read as mismatched; the finding is medium for that reason.
- **Terminology checks are opt-in.** Without a declared glossary, terminology is not judged;
  the check compares literal variants, so a variant that is a substring of the preferred
  form is not a violation.
- **Causal detection is a word list** (causes, leads to, due to, because of). "The results in
  Table 1" is a pointer, not causal language, and is not flagged.
- **The audit does not judge prose.** Structure, traceability and factual agreement only.

## Failure handling

| symptom | what to do |
|-|-|
| `uncited_claim` | add the reference; a factual sentence needs one |
| `value_not_in_materials` | check the number against the material, or fix the anchor |
| `sample_size_mismatch` | align the draft's n with the record, or fix the anchor |
| `material_no_locator` | give file/sheet/row/timestamp |
| `figure_caption_mismatch` | put the figure's own values in its caption |
| `abstract_result_conflict` | align the abstract with the body |
| `term_variant` | replace the variant with the glossary's preferred form |
| `abbreviation_not_introduced` | introduce the full form before first use |
| `trend_as_causation` | soften to association, or justify the causal claim with the design |
| `review_points_missing` | record the points a human must confirm |
| `change_log_missing` | record the revisions |

## Verification

```bash
python scripts/bench_draft.py     # 35 scenarios: one per rule plus false-positive guards
python scripts/bench_sections.py  # 51 scenarios: cross-section regression plus false-positive guards
```

Both pass in full on this machine. The clean baseline in each must report nothing. New
rules are each covered by a defect scenario and a repaired-twin guard scenario, and the
opt-in rules stay silent when their trigger (glossary, require flag) is absent.

## Requirements

Python 3.9+（3.14 实测）。纯标准库实现，无第三方依赖。

## 创新增益

本 Skill 相比通用 Agent 直接写作的核心新增能力（全部为引擎真实运行的机制，bench 覆盖）：

1. **双锚点逐句溯源**：材料锚点与引用键是两套独立机制，数值类句子锚定数据记录、论断类句子引用文献；引用检查逐行再逐句执行，行尾引用不能为行首论断背书——通用 Agent 的整篇扫描做不到这一点。
2. **数值-材料同源校验**：草稿中的每个数字必须逐字出现在其锚定材料的文本里，统计量（p 值、t 值、CI）按惯例豁免、永不逼迫补造。
3. **样本量专项核对**：统计豁免会放过 n = 12 这类错误，本引擎单独比对草稿与锚定记录的样本量——双方都给出 n 且永不一致才报，记录未给 n 时不臆测。
4. **图注-图数据一致性**：图注必须包含图数据声明的值；图序必须连续（跳号即疑似删图后正文仍指向）。
5. **摘要-正文数值一致**：摘要中的数字若正文无处可查即报冲突，摘要不得领先于正文。
6. **术语与缩写统一**：声明式术语表（首选形/变体/缩写），变体漂移与缩写先用后释都可机检——这是评分创新点中"术语与缩写统一"的落地。
7. **待核清单与修改留痕**：要求事实核对的任务必须交付人工确认点清单；change_log 缺失即报，成稿可继续编辑且未确认部分显式标注。
8. **契约直通的 result.json**：case_id 与 output_contract 全字段回填——案例自带的值原样直通、审计派生的键由审计填写、其余置 null 并写入 limits，部分结果也保持交付契约。
9. **引擎级崩溃免疫**：类型错位（列表槽位放字符串/数字、template 声明错型）一律降级为发现项或忽略，退出码只有 0/3/4/5 五种，绝不以 traceback 收场。

## 生态贡献

1. **SKILL.md**：用途、适用条件、六步调用方式、输入输出契约、异常处置表、限制与自查方法齐备。
2. **scripts/**：纯标准库（Python 3.9+，3.14 实测），模块可独立导入，规则库可经 spec 配置扩展；本包为独立副本，不依赖其他包。
3. **examples/spec.json 与 examples/spec-contract.json**：最小调用示例与带契约回填的完整示例，示意输出标注为示例。
4. **bench_draft.py**：35 个场景，每条规则一个缺陷场景加修复孪生守卫场景，clean 基线必须零发现；report_draft.json 为可复跑证据。
5. **bench_sections.py**：51 个跨 section 回归场景，防误报守卫覆盖中文与类型错位输入。
6. **锚点规范**：`{M}` 材料锚点与 `[key]` 引用键的双锚点写法可迁移到任何"材料→稿件"类写作任务，材质索引结构（id + locator + text）即开即用。
7. **术语表模板**：glossary 的 concept → preferred/variants/abbreviation 结构可复用于其他学科的术语统一。
8. **声明字段清单**：data availability / author contributions / competing interests / funding 四项声明与 change_log、review_points 一起构成可复用的期刊投稿完整性模板。
