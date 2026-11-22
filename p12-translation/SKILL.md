---
name: bilingual-writing
description: >
  Translate academic text between Chinese and English in the shape the task asks for — plain
  translation, bilingual pairs or tracked changes — and prove the translation kept its facts.
  Compares numbers, units, citations and figure references as document-level invariants;
  checks that negation count and hedge strength survive; verifies that figures, tables,
  footnotes and references were translated too; requires magnitude conversions (万/亿 versus
  million/billion) to be recorded; and keeps terminology to a glossary whose locked terms
  actually reach the target. Also checks that bilingual pairs carry the whole declared source
  and are individually addressable, that a declared back-translation pass covered the
  high-risk sentences, that unresolved markers are registered for human review, that a
  scanned PDF records its OCR step, that the language pair is not degenerate, and that
  encoding damage (U+FFFD) is named instead of silently audited. Use when a task asks for a
  translated abstract, section or manuscript, or a bilingual version that must match the
  source item by item.
---

# bilingual-writing（学术翻译与双语写作）

A translation is judged by what it did **not** change. This skill audits a delivered
translation or bilingual document against its source: the model writes the translation,
the scripts in `scripts/` prove that numbers, units, citations, negation scope, hedge
strength, terminology and coverage survived, and `result.json` carries the item-level
ledger a reviewer can check line by line.

## Rubric coverage map（评分点 → 规则）

| rubric 关注点 | rule ids |
|-|-|
| 术语稳（同一术语全篇同译法） | `xlate.term_variant`, `xlate.term_missing`, `xlate.term_entry_no_basis`, `xlate.glossary_conflict` |
| 数字实（数字/单位/量级原样落地） | `xlate.invariant_broken`, `xlate.invariant_added`, `xlate.number_conversion_unexplained`, `xlate.length_out_of_band` |
| 对得齐（句段一一对应、图表题注脚注文献在位） | `xlate.segments_missing`, `xlate.segment_unpaired`, `xlate.segment_id_duplicate`, `xlate.segment_id_absent`, `xlate.segment_coverage_low`, `xlate.segment_malformed`, `xlate.component_untranslated` |
| 边界清（否定/限定/引用/归属保持原意） | `xlate.negation_changed`, `xlate.hedge_strength_changed`, `xlate.backcheck_missing`, `xlate.backcheck_orphaned`, `xlate.placeholder_unregistered`, `xlate.ocr_degradation_unrecorded` |
| 交付形态可接受 | `xlate.mode_missing`, `xlate.mode_unknown`, `xlate.missing_side`, `xlate.untranslated_residue`, `xlate.target_not_translated` |
| 输入可运行、未损坏 | `xlate.language_pair_degenerate`, `xlate.replacement_char_present`, `xlate.glossary_entry_malformed` |

## The failures this exists to catch

**A dropped quantifier.** `3-fold` becoming "markedly". Numbers, units, citations and figure
references are compared as multisets in both directions.

**An inverted claim.** One extra or missing "not" flips the finding, and it is invisible in a
fluent translation. Negation counts are compared.

**A hedge turned into an assertion.** `可能提高` becoming "clearly increases". The strongest
claim on each side is compared by level.

**A body-only translation.** Captions, footnotes and the reference list are part of the
paper; a translation that covers only running text is incomplete.

**A magnitude silently converted.** `300 万` becoming `3 million` is correct arithmetic
nobody can check afterwards unless the conversion is recorded.

**A locked term that never arrived.** The glossary locks 吸附 → sorption; the translation
drops the concept entirely. The source form is looked up in the source and the locked
rendering in the target.

**A pass that was declared but not run.** Declaring `backcheck` asserts a back-translation
pass; the records are then checked against exactly the high-risk segments.

**Work marked but not registered.** A 待确认 left in the text is honest marking — but if no
human-review entry or limit records it, no reviewer is ever routed to it.

**A scan that reads as verified text.** A PDF without a text layer rests on OCR; a result
that records neither the OCR step nor its uncertainty presents recognised text as checked
text.

## Runtime entry — from `/input/case.json` and `task.md` to `/app/output/result.json`

**Step 0 · Read the inputs.** Load `/input/case.json` (keep `case_id` and `output_contract`
from it verbatim; the source text is usually embedded or named by a path inside it) and
`/input/task.md` (what shape, scope and constraints the task asks for). Never assume the
source content from labels — read the actual text.

**Step 1 · 判形态选路由.** Decide `section: "translation"` and the `output_mode` from the
task wording (table below). If the task names a language pair the case does not support,
stop and record it in `limits` — do not translate into the wrong language.

**Step 2 · 先产出目标产物.** Write the translation itself first — the full target text
(`target_text`) or the pairs (`segments[]`) — into `/app/work/deliverable.md` (or `.json`).
This is the artifact the grader edits; save it early and improve incrementally. A partial
translation must say which parts are missing (`limits`).

**Step 3 · 构造 spec.** Assemble the audit spec (field table below): the deliverable, the
declared source, the glossary with bases, recorded conversions, declared components and
markers, and the case's `case_id` + `output_contract` carried over verbatim.

**Step 4 · 运行审计.**

```bash
python scripts/writeaudit.py --spec /app/work/spec.json --out /app/output
```

Exit codes: `0` clean, `3` review, `4` blocked, `5` undetermined (refused — bad JSON,
missing file, non-object spec, missing or unknown section; `result.json` is still written,
never a traceback).

**Step 5 · 修发现重跑.** Fix the findings the Failure-handling table names (restore the
dropped number, add the missing pair, register the marker), re-run, and repeat until the
status is acceptable or the remaining findings are honest limits.

**Step 6 · 合并 result.json.** The script's `result.json` already echoes `case_id` and
every `output_contract` field (kept, copied from the spec, or null + a note naming what was
not derivable) and carries the three-part structure the rubric asks for. Move it to
`/app/output/result.json` alongside the deliverable, and fill any null contract field by
hand when the audit cannot derive it — never silently.

## 任务措辞 → 路由决策表

| task.md wording | route | why |
|-|-|-|
| "翻译这段/整篇摘要"（no alignment demanded） | `plain` + `target_text` | a continuous translation is the deliverable |
| "双语对照 / 逐句对照 / bilingual" | `bilingual` + `segments[]` with ids | alignment is the point; pairs make it editable |
| "带修订标记 / tracked changes / 修订模式" | `tracked` + `segments[]` | changes are per-segment by definition |
| "只译摘要，图表题注不译" | `plain` + `limits` naming the skip | honesty about scope beats silent omission |
| "术语全篇统一 / 保持术语一致" | declare `glossary{concept: {preferred, variants, source_form, abbreviation, basis}}` | locks make consistency checkable, `basis` makes it reviewable |
| "数字单位不要动 / 保留所有数据" | invariants run always; declare `conversions` if 万/亿 ↔ million/billion arithmetic is intended | deliberate conversion ≠ broken invariant |
| "这是扫描件 / PDF 无文本层" | `source_format: "pdf"`, `text_layer: false` + `ocr{engine, confidence}` or an OCR note in `limits` | recognised text must not pass as verified text |
| "表格、图注、脚注、参考文献也要" | `components{figures, tables, equations, footnotes, references}` + `*_marker` | the audit checks each marker reaches the target |
| "拿不准的地方标出来" | leave 待确认/TODO markers in the text AND register them in `limits` | marking + routing both required |
| "逐段可修改 / 可以对照修改" | `bilingual` with ids `s1, s2, …` and full source coverage | segment addressing + `segment_coverage_low` guard |
| "中文稿翻成英文再翻回校验" (declared back-translation) | `backcheck: [{segment: s1, verdict: match}, …]` | declaring the pass makes it checkable |
| task names another section (evidence writing / review response / format) | use the section the case declares; this doc covers `translation` | the engine routes by `spec 的 section 字段` |

## Spec fields（构造 spec 的完整字段表）

| field | type | required | meaning |
|-|-|-|-|
| `case_id` | str | yes (carry through) | input identifier, echoed into result.json |
| `output_contract` | obj | yes (carry through) | every named field is echoed into result.json |
| `section` | str | yes | `translation` (this doc) |
| `output_mode` | str | yes | `plain` / `bilingual` / `tracked` |
| `source_lang`, `target_lang` | str | yes | e.g. `zh`, `en`; equal values fire `language_pair_degenerate` |
| `source_text` | str | yes* | declared source; with pairs it is the coverage baseline |
| `target_text` | str | * | the plain-mode deliverable |
| `segments[]` | list | for bilingual/tracked | `{id, source, target}`; non-object entries fire `segment_malformed` |
| `components{}` | obj | optional | counts + `*_marker` for figures/tables/equations/footnotes/references |
| `glossary{}` | obj | optional | concept → `{preferred, variants, source_form, abbreviation, basis}` |
| `conversions[]` | list | when magnitude words moved | e.g. `{"from": "3万", "to": "30,000", "factor": 10000}` |
| `backcheck[]` | list | when a back-translation pass was run | `{segment: "s1", verdict: "match"}` |
| `source_format`, `text_layer`, `ocr{}` | mixed | for scanned sources | `pdf` + `false` demands an OCR record or an OCR note in limits |
| `limits[]` | list | recommended | honest gaps; also registers placeholder markers |

## Worked example（示例，非正式案例结果）

Spec — assembled from a case whose task says "整篇双语对照，术语锁定，回译校验"
(`case_id` and `output_contract` come from `/input/case.json` verbatim):

```json
{
  "case_id": "case-xlate-demo-01",
  "output_contract": {"status": "…", "deliverable_text": "…", "coverage": "…"},
  "section": "translation",
  "output_mode": "bilingual",
  "source_lang": "zh",
  "target_lang": "en",
  "source_text": "涂层的吸收率提高到原来的3倍[1]。样本量达到 300 万[2]。样品在25 °C下测量[3]。",
  "target_text": "",
  "segments": [
    {"id": "s1", "source": "涂层的吸收率提高到原来的3倍[1]。",
     "target": "The coating improved uptake 3-fold [1]."},
    {"id": "s2", "source": "样本量达到 300 万[2]。",
     "target": "The sample size reached 3 million [2]."},
    {"id": "s3", "source": "样品在25 °C下测量[3]。",
     "target": "Samples were measured at 25 °C [3]."}
  ],
  "glossary": {"吸收率": {"preferred": "uptake", "variants": ["sorption"],
                          "source_form": "吸收率", "basis": "field convention in coating tests"}},
  "conversions": [{"from": "300 万", "to": "3 million", "factor": "1e6"}],
  "backcheck": [{"segment": "s1", "verdict": "match"},
                {"segment": "s2", "verdict": "match"},
                {"segment": "s3", "verdict": "match"}],
  "limits": ["figure captions are not part of the supplied source and are not translated"]
}
```

```bash
python scripts/writeaudit.py --spec /app/work/spec.json --out /app/output   # exit 0
```

Illustrative result.json (示例示意，字段以实际运行为准):

```json
{
  "schema_version": "writeaudit/v1",
  "case_id": "case-xlate-demo-01",
  "section": "translation",
  "status": "clean",
  "severity_counts": {},
  "findings": [],
  "checked": {"source_chars": 47, "target_chars": 107, "segments": 3,
              "glossary_terms": 1, "backcheck_records": 3},
  "deliverable": {"kind": "bilingual", "shape": "segments", "segment_count": 3,
                  "target_text": "The coating improved uptake 3-fold [1]. …"},
  "evidence_map": [
    {"kind": "quantity", "value": 3.0, "unit": null, "count": 1, "verdict": "match"},
    {"kind": "quantity", "value": 3000000.0, "unit": null, "count": 1, "verdict": "match"},
    {"kind": "citation", "marker": "[1]", "verdict": "match"},
    {"kind": "term", "concept": "吸收率", "preferred": "uptake", "basis": "field convention"}
  ],
  "boundary": {"human_review_and_gaps": [], "declared_limits": ["figure captions …"]},
  "limits": ["output_contract field 'coverage' was not derivable by this audit"],
  "status_note": "示例：output_contract 中 'coverage' 为 null 时需人工补齐后提交"
}
```

## result.json 与 rubric 输出要求的三段结构映射

| rubric 要求（原词） | result.json 字段 | 完成标准如何满足 |
|-|-|-|
| 目标产物（可编辑的稿件/双语对照/结构化产物） | `deliverable`（kind、segment_count、target_text 全文） | 满足任务指定的形态（plain/bilingual/tracked），可直接进入作者修改流程 |
| 事实与来源映射（数字、术语、引用、图表的来源/修改记录，可逐条回溯） | `evidence_map[]`（quantity/citation/xref/term/component/backcheck，每条带 verdict） | 每个数字、引用、术语的保留与否逐条可见，不改写原文事实 |
| 版本与边界（修改差异、人工确认项、材料缺口和异常） | `boundary`（human_review_and_gaps、declared_limits）+ `findings[]` + `limits[]` | 未确认部分有 marker 且有记录；材料缺口显式命名 |
| 输入标识 + 运行状态 + 不确定性 | `case_id` + `status`（clean/review/blocked/undetermined）+ `severity_counts` | grader 能定位输入、判断运行状态与不确定性 |

## Rules

### Output shape and traceability

| rule | severity | what it proves |
|-|-|-|
| `xlate.mode_missing` / `mode_unknown` | high / medium | the delivery does not state its shape |
| `xlate.segments_missing` | high | a bilingual delivery with no pairs |
| `xlate.segment_unpaired` | high | a segment with one side missing |
| `xlate.segment_id_duplicate` | high | a segment cannot be pointed at |
| `xlate.segment_id_absent` | medium | no segment carries an id, so nothing is addressable |
| `xlate.segment_malformed` | medium | a segment entry is not an object |
| `xlate.segment_coverage_low` | medium | the pairs carry under 75% of the declared source |
| `xlate.missing_side` | high | one whole side is empty |

### Invariants

| rule | severity | what it proves |
|-|-|-|
| `xlate.invariant_broken` | high | a number, unit, citation or figure reference was lost |
| `xlate.invariant_added` | high | the target introduces one the source does not have |
| `xlate.negation_changed` | high | the negation count differs |
| `xlate.hedge_strength_changed` | high | hedging was strengthened or weakened |
| `xlate.number_conversion_unexplained` | medium | 万/亿 or million/billion used without a recorded conversion |

### Coverage, residue, terminology, input health

| rule | severity | what it proves |
|-|-|-|
| `xlate.component_untranslated` | high | captions, footnotes or references not translated |
| `xlate.untranslated_residue` | medium | source-script characters left in the target |
| `xlate.target_not_translated` | high | the target is not in the target language |
| `xlate.length_out_of_band` | medium | the length implies omission or padding |
| `xlate.term_variant` | medium | a glossary term in a non-preferred form |
| `xlate.term_missing` | medium | a locked concept in the source never reaches the target |
| `xlate.term_entry_no_basis` | medium | a glossary choice that cannot be reviewed |
| `xlate.glossary_conflict` | medium | two concepts claim the same preferred form |
| `xlate.glossary_entry_malformed` | medium | a glossary entry is not an object |
| `xlate.backcheck_missing` | high | a declared pass has no record for a high-risk segment |
| `xlate.backcheck_orphaned` | low | a record points at a nonexistent segment id |
| `xlate.placeholder_unregistered` | medium | a work marker in the text no record routes to a human |
| `xlate.ocr_degradation_unrecorded` | medium | a scanned source presented as verified text |
| `xlate.language_pair_degenerate` | medium | source_lang equals target_lang |
| `xlate.replacement_char_present` | high | U+FFFD proves the input was decoded wrong |

## Limits

- **Multiset comparison is order-blind.** A translation that swaps two numbers keeps the
  multiset identical and passes.
- **Units are compared across languages through a canonical table.** `12 h` and `12 小时`,
  `3 days` and `3 天`, `25 °C` and `25 ℃` are the same fact in two scripts and compare equal.
  Converting `1 h` to `60 min` is still reported, because the invariant is "same value, same
  unit" — record it in `conversions` to make it deliberate.
- **A declared magnitude conversion changes the digits by design.** With `conversions`
  filled and 万/亿/million/billion in the source, values that differ by a power of ten are
  read as the recorded conversion. Values that change with no record and no magnitude word
  behind them still fire.
- **Comma-grouped numbers are unwound before comparison.** `30,000` is one value; a
  faithful `30000` in the target passes.
- **Negation is counted, not understood.** Two negations in the source and two in the target
  pass even if they sit on different clauses.
- **Hedge comparison uses the strongest claim per side.** A localised weakening inside a
  paragraph whose strongest claim is unchanged will pass.
- **The length band is a heuristic**, per direction: zh→en (0.8–3.5), en→zh (0.15–2.0 —
  Chinese compresses three- to four-fold), other pairs (0.3–3.0). It applies only above
  ~200 source characters. It catches gross omission, not a paragraph shortened by a fifth.
- **Numeral forms only.** `三倍` in characters is not recognised as 3; the invariant needs
  digits.
- **Segment coverage is character-based and thresholded** (0.75). It runs only when both a
  non-empty `source_text` and pairs are declared, and only in bilingual/tracked mode.
  Merging or splitting segments must not fire it — dropping content does.
- **Back-check rules are declarative.** Nothing is demanded unless `backcheck` is present.
  A record needs only the segment id; its verdict text is not interpreted.
- **`term_missing` is word-bounded on ASCII forms.** A term `min` does not count as present
  inside `minimum`. It fires only when the declared `source_form` (or a variant) occurs in
  the source and neither the preferred form, the declared `abbreviation`, nor the source
  form itself reaches the target — a target that keeps the English term passes, because
  established abbreviations legitimately stay in English in Chinese text.
- **Placeholder detection matches literal markers only.** TODO/TBD/FIXME/PLACEHOLDER,
  待译/待补/待确认/待定/待核/待填, 占位符, `[?]`, `【?】`. A marker that any of
  `limits`/`notes`/`uncertainty`/`human_review` carries counts as registered — keep the
  marker in the text and add the record; never delete the marker to silence the finding.
- **The OCR rule is declarative.** It fires only when `source_format` declares a PDF and
  `text_layer` is explicitly false, and neither an `ocr` record nor an OCR/扫描/文本层
  mention in `limits` exists.
- **Translation quality is not judged.** Fluency, register and idiom are outside the audit.

## Failure handling（修发现 → 重跑）

| symptom | what to do |
|-|-|
| `invariant_broken` | restore the number/unit/marker in the target |
| `invariant_added` | remove the figure the source never stated |
| `negation_changed` | re-check the clause; one missing "not" inverts the claim |
| `hedge_strength_changed` | restore `may`/`可能` or soften the verb |
| `component_untranslated` | translate the captions, footnotes and reference list too |
| `number_conversion_unexplained` | record the conversion (万 → million) and its arithmetic |
| `term_entry_no_basis` | say what the rendering rests on |
| `term_missing` | translate the concept with the locked rendering, or declare its abbreviation |
| `glossary_conflict` | give one concept a different preferred form; both entries keep their basis |
| `segments_missing` | a bilingual delivery needs pairs, not one block of text |
| `segment_id_absent` | give every pair an id (`s1`, `s2`, …) |
| `segment_coverage_low` | add pairs for the uncovered source; do not delete the declaration |
| `backcheck_missing` | back-translate that segment and record the verdict |
| `backcheck_orphaned` | fix the segment id the record points at |
| `placeholder_unregistered` | keep the marker; add a human-review entry or a limit that names it |
| `ocr_degradation_unrecorded` | record the OCR engine/step, or state the uncertainty in `limits` |
| `language_pair_degenerate` | fix the declared pair, or stop and record that the pair is not supported |
| `replacement_char_present` | re-decode the source bytes with the right encoding; the audit result is not trustworthy until then |

## 异常处置表（运行异常 → 处置）

| exception | behaviour | where it shows |
|-|-|
| spec is not valid JSON | exit 5, `result.json` written with `audit.no_section`, message quotes the decode error | no traceback, ever |
| spec is not an object (list/string/number) | exit 5 refusal: "the spec file is not a JSON object" | `result.json` |
| spec file missing / unreadable | exit 5 refusal with the OS error text | `result.json` |
| no `section` declared | exit 5 refusal: "no section was declared" | `result.json` |
| unknown `section` (typo, wrong track) | exit 5 refusal naming the unknown value; valid ones: evidence_writing / translation / review_response / format_template | `result.json` |
| empty fields (no source or empty target) | `xlate.missing_side` high finding; audit stops after comparing nothing | findings |
| fields of the wrong type (segments as string, non-object entries) | `xlate.segment_malformed` / `xlate.glossary_entry_malformed` medium findings; object entries still audited | findings |
| 超长文本（hundreds of segments） | audit is single-pass regex/counter work, no model calls; it scales; length band applies above 200 source chars | status unaffected |
| 语向不支持（same-language pair, unsupported pair） | `xlate.language_pair_degenerate` medium; unsupported pairs keep the generic 0.3–3.0 length band | findings + limits |
| 术语表冲突 | `xlate.glossary_conflict` medium naming both concepts | findings |
| 引用格式异常（numeric `[12]`, author-year `(Smith 2020)`, inline `Smith et al. (2020)`） | all three are extracted and compared as multisets; an unmatched style degrades to no finding, not a wrong one | findings only when a marker is really lost/added |
| 输入编码错误（U+FFFD, mojibake bytes） | `xlate.replacement_char_present` high; fix the decoding before trusting any result | findings |
| 依赖缺失 | pure Python 3.9+ standard library; no third-party packages; if `python` itself is absent, report that honestly in `limits` instead of fabricating an audit | limits |
| contract field not derivable | field set to `null` plus a limit note; fill by hand before submitting | `limits` |

## Requirements

Python 3.9+（3.14 实测）。纯标准库实现，无第三方依赖。

## 创新增益（真实能力，bench 可复跑验证）

1. **双语不变量多重集审计**：数字+单位、引用标记、图表交叉引用在源语与译语两侧做
   多重集双向对比，跨语言单位先经规范表归一（`12 h` = `12 小时`），逗号分组数先解包
   （`30,000` = `30000`）——通用 Agent 无法对自己证明"没丢一个数字"。
2. **声明式回译检查**：`backcheck` 声明把回译承诺变成可检验对象——高风险句段（含数字/
   引用/交叉引用/否定/模糊限制语）逐一定位缺记录者，孤儿记录单独报告。
3. **术语锁定的闭环**：term_variant（变体即违规）+ term_missing（源语出现而锁定译法未
   到达）+ glossary_conflict（两条目争用同一译法）+ basis（每个选择可评审）。
4. **诚实边界**：OCR 未记录、占位符未登记、语向退化、编码损坏全部显式命名，而不是把
   不可靠结果包装成已验证结果。

bench 目录下的 translation 套件（35 场景，每条规则至少一个 planted-defect 场景 + 一个
clean 守卫）是上述能力的回归证据。

## 生态贡献

- **使用说明**：SKILL.md 从 `/input/case.json` + `task.md` 到 `/app/output/result.json`
  全流程六步、路由决策表 12 行、字段表、worked example（标注"示例"）。
- **依赖**：纯 Python 标准库，3.9+（3.14 实测），无第三方包、无网络、无模型调用。
- **配置**：所有规则声明式触发——glossary/conversions/backcheck/components/ocr 均
  "声明才检查"，未声明不惩罚；spec 字段表即配置说明。
- **示例标注**：examples/spec.json 为最小调用示例（含 case_id/output_contract），
  examples/glossary.json 为可复用术语表模板（四条术语规则即用）；SKILL.md 内
  result.json 标注"示例示意，字段以实际运行为准"，不冒充正式案例结果。
- **资源复用**：examples/glossary.json 术语表模板可直接改用；`guard.py`（数量/引用/交叉引用抽取、模糊限制语强度、术语表检查）、
  `redline.py`（单调 DP 句级对齐 + 多重集差分）可独立导入复用；bench 套件可独立复跑。
- **适用范围**：zh↔en 学术翻译与双语对照交付（abstract/章节/整篇），其他语对走通用
  长度带；四个 writing-track section 共享同一 runner 与退出码契约。
- **限制**：见 Limits——多重集序不敏感、否定计数不理解辖域、长度带为启发式、翻译
  质量不在审计范围。
- **维护**：规则与场景一一对应（新增规则必须带 bench 场景 + clean 守卫）；改脚本后
  必须重跑 `bench_translate.py`（35）与 `bench_writing.py`（20）并保持全过。

## Verification

```bash
python scripts/bench_translate.py  # 35 scenarios: one per rule plus FP guards
python scripts/bench_writing.py    # 20 scenarios: cross-section regression
```

Both pass in full on this machine. The clean baseline in each must report nothing.
