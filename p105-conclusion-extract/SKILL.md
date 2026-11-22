---
name: conclusion-extract
description: >
  Extract a paper's conclusions and numbers into one field table, with every value
  verbatim, every field locatable, and every gap labelled as not-reported,
  extraction-failed or source-conflict. Distinguishes an author's conclusion from a
  limitation and from a speculative remark, and keeps every number bound to the
  conditions it holds under. Use when a task asks for structured extraction of
  results, experimental conditions, key metrics or conclusion cards from a paper,
  and the output must be checkable against the text rather than being a shorter
  summary.
---

# conclusion-extract

The task states that the point is not to compress the paper. It is to restore claims and
numbers scattered across body, tables, figure captions and supplement into one field
table where every field can be traced back to a location.

That yields four checks, and each one corresponds to a scoring point:

| scoring point | rule |
|-|-|
| one field table across body / table / figure / supplement | `extract.source_*`, `extract.field_*` |
| values verbatim; conclusion vs limitation vs speculation | `extract.value_not_in_source_text`, `extract.kind_*` |
| a gap is "not reported" **or** "extraction failed" **or** "sources conflict" | `extract.gap_unclassified`, `extract.conflict_without_note` |
| every field locatable to page / section / cell / figure | `extract.locator_vague` |

## The four failures this exists to catch

**A number that was quietly converted.** `3-fold` becoming `3×` or `300%` on the way in.
Values are checked verbatim against the supplied source text.

**A gap that is just blank.** "The paper never reported this", "I failed to extract it"
and "the paper's own sources disagree" are three different facts, and a blank cell
collapses them. Every empty field must carry a status of `not_reported`,
`extraction_failed` or `source_conflict`, and a conflict must also record which sources
disagree.

**A limitation recorded as a conclusion.** "Only one thickness was tested" is the paper
telling you what it does not claim; filing it as a finding inverts the paper's position.

**A locator too coarse to verify.** "见上文" is not a locator. The rule accepts page
(`p.7`, `第7页`), section (`Sec 3.2`), table cell (`Table 2 row 3`, `表2 行3`) and
figure (`Fig 3b`, `图3b`) shapes.

## Runtime: the six steps

Run the same six steps for every case. They keep the deliverable and the audit separate:
the audit checks structure, it never manufactures content.

**Step 0 — read the case.** Read the input case file and the task statement. Copy two
things out of the case before anything else: the case identifier and the declared output
contract (the field names the result must carry). Also copy any concrete target-field
list the case supplies — those field ids become the field table's rows.

**Step 1 — route by the shape of the ask.** Match the task wording against the table
below and pick a section. When in doubt, prefer the primary section of this skill.

| task wording (representative) | route | spec essentials |
|-|-|-|
| 抽取结论/构建字段表/结论卡片/数据点定位（单篇） | conclusion_extract | fields + source_text + conclusions |
| 逐条字段取值：给 target-fields 清单，逐 field_id 回答 | conclusion_extract | 同上，fields 取自清单 |
| 判断某条论断是否被某段证据支撑（claim-evidence） | claim_verify | claims + evidence + source_text |
| 多篇论文同一指标横向对比（合并表） | compare_docs | documents + fields + 统一 schema |
| 针对材料的问答，需引用出处 | qa | evidence + answers |
| 公式结构/符号表/数值代入核验 | formula | formulas + variables + numeric |
| 复现报告/复跑清单的结构完整性 | reproduce | checklist + commit + commands |
| 论文初稿/章节稿写作与事实核对 | paper_draft | draft + materials + references |
| 与抽取无关的请求（改写、翻译全文、泛读摘要） | none | refused as undetermined, never guessed |

**Step 2 — produce the target deliverable first.** Do the actual reading: work through
body, tables, figure captions and supplement, and write the field table itself. The
audit in later steps checks structure; it cannot read the paper for you, so a hollow
spec with a tidy schema is still a failed case.

**Step 3 — assemble the spec.** One JSON object holding the deliverable, the evidence
base and the contract: the case identifier, the section name from step 1, the field
schema with a definition per field, the source text the verbatim check runs against,
the extracted items, and the case's declared output contract fields copied in as keys
(such as the deliverable table itself) so they can be echoed verbatim into the result.
See `examples/spec-contract.json` for the full shape.

**Step 4 — audit.** Run the engine once:

```bash
python scripts/secrun.py --spec examples/spec-contract.json --out /app/output
```

Exit codes: `0` clean, `3` review (only low/medium findings), `4` blocked (any high
finding), `5` undetermined (the case could not be run as declared — unreadable spec,
non-object spec, missing or unknown section). Every exit writes a result file; exit
never comes from a traceback.

**Step 5 — fix findings and rerun.** Each finding names a rule and an item. Fix the
extraction (restore the verbatim string, label the gap, add the locator, declare the
comparator), never the audit, and rerun. Repeat until exit 0 or 3, or until a finding
genuinely cannot be resolved — then leave it and record why in the run's limits, because
an honest blocked status beats a silenced rule.

**Step 6 — merge the result.** Write the deliverable files under the output directory.
The result file written by the engine already carries: the case identifier, every field
of the declared output contract (values the case carried pass through untouched; the
audited status, findings and counts are filled by the audit; anything else is null with
a limits note — never a fabricated value), findings, severity counts, and limits. Keep
that file as the structured result of the case.

## The spec, field by field

```json
{
  "case_id": "demo-extract-001",
  "section": "conclusion_extract",
  "fields": [
    {"name": "effect_size", "definition": "reported fold change in uptake rate"},
    {"name": "sample_n", "definition": "number of replicates per group"}
  ],
  "source_text": "The porous coating improved uptake 3-fold (Fig. 3b, p.7). ...",
  "sources_present": ["body", "figure"],
  "conclusions": [
    {"claim": "涂层的吸收速率提高到原来的 3 倍",
     "condition": "每组 n = 6，25 °C，单一厚度",
     "comparator": "未涂层对照组（同一温度）",
     "locator": "Fig 3b, p.7",
     "claim_kind": "conclusion", "source_kind": "figure", "hedged": true,
     "effect_size": "3-fold", "sample_n": 6,
     "values": [{"value": 3, "unit": "fold", "verbatim": "3-fold"}]},
    {"claim": "只测试了一种涂层厚度，结论不能外推",
     "condition": "局限说明",
     "locator": "p.7",
     "claim_kind": "limitation", "source_kind": "body", "hedged": true,
     "effect_size": "", "effect_size_status": "not_reported",
     "sample_n": 6,
     "values": []}
  ],
  "output_contract": {"case_id": "...", "status": "...", "field_table": "..."}
}
```

`fields` is the schema and ships with the result — without it nobody can re-run the same
extraction or compare two papers. `source_text` is what the verbatim check runs against.
`sources_present` says which of body/table/figure/supplement the paper actually has, so
an unused source can be reported. Each item may also carry `comparator` (the baseline a
comparative claim was measured against) and, on any field whose status is
`source_conflict`, a `conflict_note` naming which sources disagree and by how much.

**Conditions carry the same discipline as findings.** The experimental setting (`n = 6`,
25 °C, single thickness) belongs on the item as its `condition`, with its own locator —
a finding whose setting is lost is exactly what `extract.missing_condition` exists for.
When the condition sentence carries a number the paper states, put that number in the
item's `values` too, so the verbatim check covers it the same way it covers effect sizes;
a condition the paper never states is `not_reported`, not silence.

## Worked example（示例）

Input `examples/spec-contract.json` — the spec shown above plus a declared output
contract with six fields, one of which (`field_table`) is a deliverable the case itself
carries. Run:

```bash
python scripts/secrun.py --spec examples/spec-contract.json --out /tmp/out
```

Console output（示例，路径随机器不同）:

```json
{"status": "clean", "section": "conclusion_extract", "case_id": "demo-extract-001",
 "findings": [], "wrote": "/tmp/out/result.json"}
```

The written result（示例节选，实跑所得）:

```json
{
  "case_id": "demo-extract-001",
  "status": "clean",
  "output_contract": {
    "case_id": "demo-extract-001",
    "status": "clean",
    "section": "conclusion_extract",
    "field_table": {"format": "per-claim rows, one column per declared field"},
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
| findings[] | one per rule hit: rule, severity, message, item index, locator, verbatim context |
| severity_counts | findings by severity |
| checked | items audited (and the coverage matrix for comparison runs) |
| limits | what this run could not verify, including any contract field left null |
| output_contract | every declared contract field: case-carried values pass through, audited keys are filled by the audit, the rest are null with a limits note |

## Mapping to the required result sections

| 评分要求的字段（原词） | 本 Skill 的交付 |
|-|-|
| 阅读/解析结果 | 字段表本身：fields 定义 + conclusions[] 主产物，随 result 一并交付 |
| 证据与边界 | 每条 item 的 locator（页/节/表行列/图注）、空缺三态（not_reported / extraction_failed / source_conflict + conflict_note）、limits |
| 运行状态 | status（clean / review / blocked / undetermined 及原因）+ findings + case_id |

## Rules

### The field table

| rule | severity | what it proves |
|-|-|-|
| `extract.schema_missing` | high | no field schema, so the result is not re-runnable |
| `extract.field_undefined` | medium | a field has no definition |
| `extract.field_absent` | high | an item omits a declared field entirely |
| `extract.gap_unclassified` | high | a blank field is not labelled not-reported vs extraction-failed vs source-conflict |
| `extract.conflict_without_note` | medium | a declared source conflict records no conflicting sources |
| `extract.source_not_covered` | medium | a source the paper contains was never used |

### Claim kind and strength

| rule | severity | what it proves |
|-|-|-|
| `extract.kind_undeclared` | high | conclusion / limitation / speculation not stated |
| `extract.kind_unknown` | medium | the kind is outside those three |
| `extract.hedge_dropped` | high | an absolute claim where the source hedged |
| `extract.hedge_misdeclared` | medium | declared hedged, but the wording is absolute |
| `extract.comparator_missing` | medium | a comparative claim records no baseline |
| `extract.empty_claim` | high | an item has no claim text |

### Evidence and values

| rule | severity | what it proves |
|-|-|-|
| `extract.missing_locator` | high | no locator at all |
| `extract.locator_vague` | medium | the locator is too coarse to land on the sentence |
| `extract.missing_condition` | high | the finding lost its sample/setting/baseline |
| `extract.value_not_in_source_text` | high | a verbatim value does not occur in the source text |
| `extract.value_without_unit` | medium | a value with no unit |
| `extract.unit_verbatim_mismatch` | medium | the recorded unit never occurs in the quoted text |
| `extract.source_kind_missing` | medium | the source of the item is not stated |
| `extract.source_kind_unknown` | low | the source kind is outside the four |
| `extract.no_items` | high | nothing was extracted |

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
| section name unknown (typo or wrong level) | 5 | refusal listing nothing to run; pick a route from the table |
| conclusions slot carries a string or number instead of a list | 4 | degrades to no_items; supply a list of objects |
| an item is a bare string instead of an object | 4 | the entry is skipped, no_items fires; supply objects |
| a value slot is non-numeric (`"abc"`) | 4 | reported as ambiguous (value_without_unit), never a crash; fix the value |
| a declared field is absent from an item | 4 | field_absent; add the key or a status-labelled gap |
| a blank field carries no status | 4 | gap_unclassified; choose not_reported / extraction_failed / source_conflict |
| status is source_conflict with no note | 3 | conflict_without_note; record which sources disagree |
| claim wording absolute while hedged is declared true | 3 | hedge_misdeclared; fix wording or declaration |
| comparative claim without a comparator | 3 | comparator_missing; record the baseline |
| recorded unit absent from the verbatim | 3 | unit_verbatim_mismatch; recheck the unit or the quote |
| source_text omitted | 0/3/4 | verbatim check is skipped, not silently passed; supply the paper text to enable it and say so in limits |
| a declared source has no items from it | 3/4 | source_not_covered; read that source or correct the declaration |
| rerun with an unchanged spec | — | byte-identical result; the audit is deterministic |
| extremely long strings | 0–5 | accepted; messages truncate to 100 chars, nothing crashes |

## Limits

- **`hedged` and `claim_kind` are declared by the extractor.** The audit checks they are
  present and consistent with the wording (both directions: a dropped hedge and a
  misdeclared hedge); it cannot read the paper to decide whether a statement really was
  hedged.
- **The verbatim check needs the source text.** Without `source_text` the rule is skipped
  rather than passing silently, and the run's `limits` say so only if you add it there.
- **Absolute-word detection is a list.** Chinese and English markers are covered; a claim
  made absolute by phrasing rather than vocabulary will pass.
- **Bare integers are counts, not unit-less measurements.** `n = 6` or "3 groups" carries no
  unit by convention and is not flagged. A ratio word in the verbatim ("3-fold", "300%") or a
  non-integer value ("3.5") is still reported as ambiguous. Never invent a unit to silence
  the finding — a fabricated unit is worse than a flagged count.
- **Statistics are exempt from the unit check.** A verbatim that is a p-value, a test
  statistic with df, a sample size or a CI bound carries no unit by convention; demanding
  one would push fabricated units into the table.
- **Locator shapes, not correctness.** `Fig 3b` passes the shape test even if the figure
  is really `Fig 3a`; cross-checking the label is the extractor's job.
- **`sources_present` is a declaration.** Reporting an unused source requires the case to
  say the source exists.
- **It does not read PDFs.** Extraction from the document is a separate step; this audits
  the structure that comes out of it.

## Failure handling

| symptom | what to do |
|-|-|
| `schema_missing` | declare the field table; it is part of the deliverable |
| `gap_unclassified` | label every blank as `not_reported`, `extraction_failed` or `source_conflict` — decide which |
| `conflict_without_note` | name the sources that disagree and by how much |
| `kind_undeclared` | classify the item; a limitation is not a conclusion |
| `locator_vague` | give a page, section, table cell or figure, not "见上文" |
| `value_not_in_source_text` | check the text once more, or drop the verbatim claim |
| `value_without_unit` | add the paper's own unit; a count may stay bare |
| `unit_verbatim_mismatch` | align the recorded unit with what the text actually quotes |
| `comparator_missing` | record the baseline the comparison was made against |
| `hedge_misdeclared` | fix the wording or the declaration — they must agree |
| `source_not_covered` | the paper's supplement or table was never read |
| `hedge_dropped` | restore the hedge or mark the item as speculation |

## Verification

```bash
python scripts/bench_extract.py   # 29 scenarios: one per rule plus false-positive guards
python scripts/bench_sections.py  # 51 scenarios: cross-section regression plus false-positive guards
```

Both pass in full on this machine. The clean baseline in each must report nothing, so a
detector cannot pass by flagging everything. New rules are each covered by a defect
scenario and a repaired-twin guard scenario.

## Requirements

Python 3.9+（3.14 实测）。纯标准库实现，无第三方依赖。

## 创新增益

本 Skill 相比通用 Agent 直接抽取的核心新增能力（全部为引擎真实运行的机制，bench 覆盖）：

1. **逐值回原文校验**：每个 value 的 verbatim 必须逐字出现在提供的原文中，任何改写、合并、换算（3-fold 写成 300%）都会被点名——通用 Agent 无法对自己产出的数值自证未改动。
2. **空缺三态语义**：not_reported / extraction_failed / source_conflict 是三种不同的事实，空字段必须显式选型，来源冲突还必须记录冲突双方——把"未报告"与"抽取失败"与"文献间冲突"在数据层面分开。
3. **条件与数值同源绑定**：每条结论强制携带 condition（样本/设置/基线），比较性结论强制携带 comparator；条件句里的数字同样进入 verbatim 校验。
4. **定位符形状语法**：页码/章节/表行列/图注四类形状、中英文双重模式（p.7、第7页、表2 行3、图3b），给出可机械判定的粒度下限。
5. **结论强度分层与双向 hedge 校验**：结论/限制/推测必须分层；hedge 声明与措辞做一致性双向检查（丢了 hedge 高危，声明 hedge 但措辞绝对也报）。
6. **统计表达式豁免**：p 值、t 值、CI、n 等统计量永不要求单位，避免逼出捏造单位。
7. **契约直通的 result.json**：case_id 与 output_contract 全字段回填——案例自带的值原样直通、审计派生的键由审计填写、其余置 null 并写入 limits，部分结果也保持交付契约。
8. **引擎级崩溃免疫**：类型错位（列表槽位放字符串/数字、非数值 value）一律降级为发现项，退出码只有 0/3/4/5 五种，绝不以 traceback 收场。

## 生态贡献

1. **SKILL.md**：用途、适用条件、六步调用方式、输入输出契约、异常处置表、限制与自查方法齐备。
2. **scripts/**：纯标准库（Python 3.9+，3.14 实测），模块可独立导入，规则库可经 spec 配置扩展；本包为独立副本，不依赖其他包。
3. **examples/spec.json 与 examples/spec-contract.json**：最小调用示例与带契约回填的完整示例，示意输出标注为示例。
4. **bench_extract.py**：29 个场景，每条规则一个缺陷场景加修复孪生守卫场景，clean 基线必须零发现；report_extract.json 为可复跑证据。
5. **bench_sections.py**：51 个跨 section 回归场景，防误报守卫覆盖中文与类型错位输入。
6. **规则词表**：rule id 稳定命名并与引擎一一对应（文档-引擎一致性由门禁检查），可作为同类抽取任务的共享词汇。
7. **字段表模板**：fields + definition 的 schema 结构可直接迁移到其他论文与领域，只需替换字段定义。
8. **定位符词表**：中英文四类定位形状（页/节/表行列/图注）的正则词表随 guard.py 复用，可服务其他文献阅读类任务。
