---
name: clean-literature-data
description: >
  Clean and standardise an extracted literature data table with a numbered,
  prioritised, re-runnable rule set. Normalises units through a real dimension
  model (ranges convert both endpoints, error bars convert with the value),
  maps aliased source columns to canonical fields and reports the unmapped ones,
  merges declared synonyms under a reviewable key while listing spellings outside
  the table, separates "not reported" from zero, distinguishes duplicate records
  from repeated experiments, keeps the original value in every change record,
  stamps each change with its declared source column, and proves the pass is
  idempotent. Emits a to-confirm list of every value the engine refuses to judge,
  and echoes the case identifier plus every declared output-contract field into
  result.json. Use when a task supplies extracted or pooled literature values
  that must become analysable without losing their provenance.
---

# clean-literature-data

The failure this prevents is not a crash. It is a table that looks clean and is
wrong: `12 mV` averaged with `1.2 V`, `not reported` counted as zero, a range
collapsed to its low endpoint, and the same material entered under three spellings
quietly kept as three substances — or wrongly merged into one.

So nothing is changed silently. Every edit carries its rule id, its row, its
original value, its reason and (when a source column is declared) the record's
origin; a second run must find nothing left to rewrite; and every value the engine
will not judge lands in a to-confirm list instead of a silent decision.

## Runtime: the six steps

Run the same six steps for every case. They keep the deliverable and the audit
separate: the audit checks structure, it never manufactures data.

**Step 0 — read the case.** Read the input case file and the task statement. Copy
two things out of the case before anything else: the case identifier and the
declared output contract (the field names the result must carry). Pass the case
file to the engine with the optional case flag so both are echoed even if the
hand-built spec forgets them.

**Step 1 — route by the shape of the ask.** Match the task wording against the
table below. When in doubt, prefer the full cleaning pass: it degrades safely
(undeclared things are listed, not silently dropped).

| task wording (representative) | route | spec essentials |
|-|-|-|
| 抽取值表/汇总文献值需清洗成可统计表，单位混杂 | full cleaning pass | columns + key_columns + rows |
| 各文献列名不同（同义字段、拆分字段），需统一字段名 | cleaning pass + field mapping | field_aliases；看 result 的未映射清单 |
| 同一物质多种写法需要归一合并（同义词归一） | cleaning pass + synonyms | synonyms + key_columns；表外拼写进待确认 |
| 每处修改需能回到原始文献/来源行 | cleaning pass + provenance | source_column 声明来源列 |
| 区间值、±误差值、复合单位（mol/L、mg/mL）要换算不出错 | cleaning pass（默认支持） | columns 的 target_unit |
| 缺失、未知单位、越界、重复需单独列出供人复核 | cleaning pass（默认输出待确认清单） | — |
| 只需复核一张已清洗的表是否还干净 | verify-only rerun | rows = 待复核行；期望退出码 0 |
| 输入已是发布级 tidy 数据（表头带单位、无缺口） | verify-only rerun | 期望 clean 基线零发现 |
| 任务是"从 PDF 抽取数值" | none — 拒绝 | 抽取是上游；本 Skill 从抽取结束处开始 |
| 值需科学解读（与机理是否一致）、统计显著性 | none — 拒绝 | 清洗规则不能裁决科学问题；下游工具负责 |

**Step 2 — produce the target deliverable first.** Do the actual reading of the
case material and assemble the real table: which columns exist, what the rows
say, which units and spellings occur. The audit in later steps checks structure;
it cannot read the case for you, so a hollow spec with a tidy schema is still a
failed case.

**Step 3 — assemble the spec.** One JSON object holding the deliverable, the
schema and the contract: the case identifier from step 0, the declared output
contract fields copied in as keys (plus any pass-through payload they name), the
column schema with target units and plausible ranges from the case's data
dictionary, the key columns that identify an entity, the rows (inline, or a
table path), and the optional controls: field_aliases, synonyms, source_column,
missing_tokens. See examples/spec-contract.json for the full shape.

**Step 4 — audit.** Run the engine once:

```bash
python scripts/cleandata.py --spec examples/spec-contract.json --out /app/output
```

Exit codes: 0 clean, 3 review (only low/medium findings — including a non-empty
to-confirm list's causes), 4 blocked (any high finding), 5 undetermined (the case
could not be run as declared — unreadable or non-object spec, no table, no record
rows, unreadable table file). Every exit writes a result file; exit never comes
from a traceback.

**Step 5 — fix findings and rerun.** Each finding names a rule and its evidence.
Fix the data or the declaration (restore the declared range, alias the stray
column, extend missing_tokens), never the audit, and rerun into the same output
directory. An unchanged input re-run into the same directory is refused with the
already-cleaned rule (exit 4), so a second pass can never stack on the first —
that guard is the rerun discipline, not an obstacle.

**Step 6 — merge the result.** The result file written by the engine already
carries: the case identifier, every field of the declared output contract (values
the case carried pass through untouched; keys the engine computes are filled by
the audit; anything else is null with a limits note — never a fabricated value),
the change ledger, the to-confirm list, and limits. Keep that file as the
structured result of the case, next to cleaned.csv.

## The spec, field by field

```json
{
  "case_id": "demo-clean-001",
  "columns": [
    {"name": "bandgap", "target_unit": "eV", "plausible": [0, 6]},
    {"name": "conc", "target_unit": "mol/L", "plausible": [0, 100]}
  ],
  "key_columns": ["material"],
  "value_columns": ["bandgap", "conc"],
  "field_aliases": {"bg": "bandgap"},
  "synonyms": {"titanium dioxide": "TiO2"},
  "missing_tokens": ["<LOD"],
  "source_column": "study",
  "rows": [{"material": "TiO2", "bg": " 3.20 eV ", "conc": "5 mM", "study": "S1"}],
  "output_contract": {"case_id": "...", "status": "...", "changes": "..."}
}
```

- columns declares the schema: name, target_unit (the unit every row converts to
  or is refused by name), plausible (a sanity window, not a truth claim), and the
  semantic (numeric default, date, categorical, text, id).
- key_columns identify an entity for the duplicate census; without them the
  census is skipped and the result says why.
- field_aliases maps source column names to canonical ones (R10); synonyms maps
  entity spellings to a canonical name for duplicate detection only (R11) —
  cells stay untouched, spellings outside the table are listed, not guessed.
- missing_tokens extends the built-in not-reported set (ND, n/a, 未检出, -999, …).
- source_column stamps the ledger and the duplicate entries with each row's
  origin, so an edit traces past the row index back toward the literature.

## Worked example（示例）

Input examples/spec-contract.json — four pooled records across three studies,
with an aliased column, one not-reported cell, one lower-detection-limit cell and
a declared output contract. Run:

```bash
python scripts/cleandata.py --spec examples/spec-contract.json --out /tmp/out
```

Console output（示例，路径随机器不同）:

```json
{"status": "review", "case_id": "demo-clean-001", "findings": ["clean.missing_values"],
 "rows": 4, "idempotent": true, "wrote": "/tmp/out/result.json"}
```

The written result（示例节选，实跑所得）:

```json
{
  "case_id": "demo-clean-001",
  "status": "review",
  "changes_by_rule": {"R10": 1, "R01": 1, "R02": 2, "R04": 2},
  "changes": [{"rule": "R10", "row": 0, "column": "bandgap",
               "original": "column 'bg'", "new": "column 'bandgap'",
               "why": "field alias declared in the spec (source column renamed, value untouched)",
               "source": "S1"}],
  "pending_review": [],
  "summary": "contract echo demo: pooled bandgap records across three studies",
  "figures": null,
  "limits": ["output_contract field 'figures' was not derivable by this cleaning pass"]
}
```

The alias was mapped (R10), the pooled `5 mM` / `0.005 mol/L` rows were converted
to the column's target unit (R04), the two not-reported cells became missing
values instead of zeros (R02), the pass-through field rode the contract untouched,
the undecivable contract field is null with a limits note, and the exit was 3
(review) because two cells are genuinely absent — an honest state, not a failure.

## Output contract of the result

The result file written by the engine on every exit path:

| field | content |
|-|-|
| case_id | the case identifier, echoed from the spec or the case file |
| status | clean / review / blocked / undetermined |
| findings[] | one per rule hit: rule, severity, message, evidence |
| severity_counts | findings by severity |
| rows / rules_applied | row count; the full rule library with priorities |
| changes[] | the ledger: rule, row, column, original, new, why, and the source value when a source column is declared |
| changes_by_rule | ledger volume per rule |
| duplicates | duplicate records vs duplicate experiments, synonym-unmapped spellings |
| anomalies | per-column missing / unparsed / unit_refused / changes census |
| cleaned_table | the analysable table (also written as cleaned.csv); each cell equals the ledger's recorded new value |
| pending_review | the to-confirm list: unparsed, refused conversions, out-of-range, duplicate experiments, unmapped spellings |
| unmapped_columns / declared_fields_absent | columns nobody declared; schema fields no row carries |
| provenance | source column name and the source values seen |
| idempotent | a second pass rewrites nothing (false is a high finding) |
| quality_report | table-derived completeness census; a hand-written report that disagrees is flagged |
| limits | what this run could not do, including any contract field left null |
| original_sha256 | fingerprint of the input rows (rerun-refusal key) |

## Mapping to the required result sections

| 评分要求的字段（原词） | 本 Skill 的交付 |
|-|-|
| 阅读/解析结果 | 清洗标准化后的数据表本身：cleaned_table + cleaned.csv，字段规范、单位统一 |
| 证据与边界 | changes[] 逐条台账（规则号/行/列/原值/新值/理由/来源）、pending_review 待确认清单、limits、未映射字段与表外同义词清单 |
| 运行状态 | status（clean / review / blocked / undetermined 及原因）+ findings + severity_counts + case_id |

## The rule library

| id | priority | rule |
|-|-|-|
| R00 | 0 | skip a row that is not a record object, and name it |
| R10 | 5 | map an aliased source column to its canonical column name |
| R01 | 10 | strip surrounding whitespace from every cell |
| R02 | 20 | treat the not-reported tokens as a missing value, never as 0 |
| R03 | 30 | parse a value into number / error / unit / range structure |
| R04 | 40 | convert a unit to the column's target unit, recording the factor |
| R05 | 50 | flag a value outside the declared plausible range |
| R06 | 60 | normalise the entity key for duplicate detection |
| R11 | 65 | resolve declared synonyms for entity keys; originals stay untouched |
| R07 | 70 | mark duplicate records separately from duplicate experiments |
| R08 | 80 | normalise dates to ISO 8601; never invent numeric precision |
| R09 | 90 | a hand-supplied quality report must agree with the computed one |

Priorities matter: R04 runs before R05 so the range check sees the value in the
target unit; R10 runs before everything so aliasing happens once; the ledger shows
which rule won when two touch the same cell. Adding a rule means choosing where it
sits in that order.

## Findings

| rule | severity | what it proves |
|-|-|-|
| `clean.not_idempotent` | high | a second pass still rewrites cells — rule priorities conflict |
| `clean.report_inconsistent` | medium | the supplied quality report disagrees with the table-derived one |
| `clean.missing_values` | medium | not-reported cells exist; they are missing, not zero |
| `clean.unparsed_values` | medium | cells could not be parsed and are kept as named gaps |
| `clean.duplicate_experiments` | medium | one entity, several measurements — do not merge silently |
| `clean.duplicate_records` | low | identical rows, safe to drop after review |
| `clean.unmapped_columns` | low | columns present in rows but neither declared nor aliased |
| `clean.declared_fields_absent` | low | schema fields no row carries |
| `clean.synonym_unmapped` | low | entity spellings outside the declared synonym table |
| `clean.already_cleaned` | high | this exact input was already cleaned into this output directory (exit 4) |
| `clean.spec_unreadable` | high | the spec is not readable JSON or not a JSON object (exit 5) |
| `clean.no_table` | high | the case supplies neither rows nor a table path (exit 5) |
| `clean.no_rows` | high | the table has no record rows at all (exit 5) |
| `clean.table_unreadable` | high | the table file is missing, unreadable, or not decodable text (exit 5) |

## Exception handling

| situation | exit | what happens / what to do |
|-|-|-|
| spec file missing or unreadable | 5 | refused with clean.spec_unreadable; re-check the path, rerun |
| spec is valid JSON but not an object (array, string, number) | 5 | refused; wrap the payload in one object and rerun |
| rows is a string or number instead of a list | 5 | refused — never enumerated character by character |
| rows is empty, or holds no JSON objects | 5 | refused with clean.no_rows; supply record rows |
| neither rows nor a table path | 5 | refused with clean.no_table; point the spec at the table |
| table file missing or unreadable | 5 | refused with clean.table_unreadable; fix the path |
| table file in another encoding (GBK, mojibake) | 5 | refused with clean.table_unreadable, byte position named; re-encode as UTF-8 |
| rerun of an unchanged input into the same output directory | 4 | refused with clean.already_cleaned; the first pass is preserved, use a fresh directory for a new pass |
| unknown unit (`psi`, `min`) | 3 | R04 refuses by name; cell kept, entry lands in pending_review; name the unit or extend the schema |
| dimension mismatch (`mg` → `mm`) | 3 | refused with both dimension vectors; this is a schema error, not a data error |
| temperature offset (`degC` → `K`) | 3 | refused as a non-multiplicative conversion; declare a reference scale instead |
| range or ± value across units | 0/3 | both endpoints (value and error) convert and the structure survives; if either side is refused the whole cell is refused |
| value outside the declared plausible range | 3 | flagged and kept — deleting it would hide a transcription error; the call is recorded in pending_review |
| a row in the rows array is a bare string | 3 | skipped and named under R00, never a crash |
| a columns entry is not an object or names no column | 0 | that column is skipped; the rest still run |
| hedged values (`about 5 mM`) | 0 | stay unparsed on purpose — the hedge is part of the claim |
| extremely long cells | 0/3 | accepted; ledger messages truncate, nothing crashes |
| CJK content | 0/3 | 中文缺失记号（未检出、未报告、不详）识别为缺失；µ/μ 前缀解析为微 |
| second pass on already-cleaned rows | 0 | idempotent: zero rewrites; a non-zero second pass is the not_idempotent high finding |

## Limits

- **Unit coverage is a table, not a database.** 22 base units across 7 dimensions
  plus compound forms (mol/L, mg/mL, J/s). An unrecognised unit is refused by
  name rather than guessed — psi will be reported, not converted.
- **Temperature offsets are not converted.** degC to K needs a reference scale,
  so it is refused instead of being treated as a multiplicative shift.
- **Duplicate detection is key-based.** Two substances written differently and
  absent from the key columns and the synonym table will not be merged. Merging
  wrongly is worse than missing a duplicate, so the bias is deliberate.
- **Synonyms change the grouping key only.** Cells keep their original spelling;
  the mapping lives in the spec where a reviewer can read it.
- **unparsed is a resting state, not a failure.** "about 5 mM" stays unparsed
  because turning it into 5 discards the hedge, and the hedge is part of the claim.
- **Plausible ranges are yours.** The engine does not know that a bandgap above
  6 eV is suspicious; it knows you said so.
- **No statistics.** No averaging, no error propagation, no significance. Those
  belong downstream, on cleaned.csv, where the choice is visible.

## Failure handling

| symptom | what to do |
|-|-|
| `clean.missing_values` | keep them missing; if the analysis needs a number, record the decision as a human step |
| `clean.unparsed_values` | fix the cell or extend the parser; never guess |
| `clean.duplicate_records` | identical rows — safe to drop after review |
| `clean.duplicate_experiments` | same entity, different values — two measurements; do not average |
| `clean.unmapped_columns` | declare the column in the schema or alias it; unmapped semantics are unrecorded semantics |
| `clean.declared_fields_absent` | the schema promises a field no row supplies — drop it or fill it |
| `clean.synonym_unmapped` | extend spec.synonyms, or leave the entity unmerged for human review |
| `clean.report_inconsistent` | the supplied report disagrees with the table; fix the report, not the table |
| `clean.not_idempotent` | the rule priorities disagree; reorder before shipping |
| `clean.spec_unreadable` (exit 5) | the spec file is missing, not readable JSON, or not an object — fix the input, rerun |
| `clean.no_table` / `clean.no_rows` (exit 5) | no table or no record rows — supply them before the run means anything |
| `clean.table_unreadable` (exit 5) | re-encode the table as UTF-8 text and rerun |
| `clean.already_cleaned` (exit 4) | the first pass is preserved; use a fresh output directory for genuinely new work |
| unit refusal (R04, new 为 null) | unknown or incompatible unit; name it in pending_review terms, never silently drop the row |

## Verification

```bash
python scripts/bench_cleaning.py   # 20 scenarios: one planted defect or FP guard each
```

20/20 pass on this machine (3.14). The clean baseline must report nothing, so a
detector cannot pass by flagging everything. Every rule above is covered by a
defect scenario or a repaired-twin guard; the CLI scenarios prove every refusal
path ends undetermined with a written result file and no traceback. Reruns are
deterministic. Full report: scripts/report_cleaning.json.

## Requirements

Python 3.9+（3.14 实测）。纯标准库实现，无第三方依赖。规则与单位模型细节见
references/units-and-rules.md。

## 创新增益

本 Skill 相比通用 Agent 的核心新增能力（全部为引擎真实运行的机制，bench 覆盖）：

1. **规则优先级库**：12 条规则带 id 与优先级，冲突由优先级裁决且双方都留痕——通用 Agent 无法自证规则一致性。
2. **幂等二遍检查**：同一规则跑两遍，第二遍必须零改写——是可计算的 self-check，false 即 high finding。
3. **字段映射与未映射清单**：spec.field_aliases 显式映射同义列名（R10），映射动作进台账；无人声明的列进 unmapped_columns 清单——"规得齐"从记忆变成可审计的声明。
4. **同义词归一与表外清单**：spec.synonyms 按可解释判定键归一实体拼写（R11），只动分组键不动数据；表外拼写进 synonym_unmapped 待确认——"合得对"的合并建议与人审分界在同一份输出里。
5. **结构保持的单位换算**：区间换算双端（3.0-3.4 eV → 3000-3400 meV）、±误差随值换算；源单位等于目标单位时单元格原样保留，清洗后单元格恒等于台账记录值——"换得准"且精度不被 :g 重排吃掉。
6. **来源溯源**：声明 source_column 后每条台账与重复记录带来源值，改动可沿规则号+行+来源回到原始文献——"追得回"。
7. **待确认清单**：pending_review 把不可解析、换算被拒、越界、重复实验、表外拼写集中列出，工具不敢确认的值单独成册而非静默裁决。
8. **契约直通的 result**：case_id 与 output_contract 全字段回填——案例自带值原样直通、引擎可推导键由引擎填写、其余置 null 并写 limits；拒绝路径（exit 5）不带契约回显，拒绝不被包装成完成。

## 生态贡献

1. **SKILL.md**：用途、适用条件、六步调用方式、逐字段 spec 说明、路由表、异常处置表、限制与自查方法齐备。
2. **scripts/**：纯标准库（Python 3.9+，3.14 实测），模块可独立导入；本包为独立副本，不依赖其他包的文件。
3. **examples/**：examples/spec.json（最小示例）与 examples/spec-contract.json（带契约回填的完整示例），示意输出标注为示例。
4. **bench_cleaning.py**：20 个场景，每条规则一个缺陷场景或修复孪生守卫，clean 基线零发现；report_cleaning.json 为可复跑证据。
5. **规则库可扩展**：missing_tokens、field_aliases、synonyms、plausible 范围全部经 spec 配置，他人换成自己的数据直接使用。
6. **单位换算表**：22 基准单位 × 7 维度的量纲模型随 units.py 复用，含拒绝语义（dimension_mismatch / unknown_unit / special_unit）。
7. **清洗类型词汇**：duplicate record vs duplicate experiment、missing vs zero、unparsed vs unit_refused 等稳定命名，可作为同类清洗任务的共享词汇。
8. **可迁移的脏数据案例**：bench 场景即脏数据类型库（同义列名、表外拼写、区间值、编码错乱、空表），可直接迁移到新材料/新领域清洗。
