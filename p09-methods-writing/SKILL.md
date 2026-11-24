---
name: methods-from-config
description: >
  Write method and experiment sections from real configs, logs, code and protocols, with
  file/line evidence for every parameter and actual protocol step. Audits prose numbers,
  design, variables, controls, materials/equipment, datasets/splits, sample size/repeats,
  randomisation/blinding, statistics, ethics/safety, reproducibility and limitations; outputs
  evidence, gaps and author questions instead of inventing experiments. Use for 写方法与实验
  章节/参数表/实验设置/可复现性. Do not use for paper reproduction verdicts or generic论文润色.
---

# Methods and experiments, with evidence before prose

Challenge: `product-arena-05-64faa4a2`（写作09｜方法与实验章节写作）.

This package preserves the historical numeric-consistency engine but replaces the shallow
“parameter row = step” wrapper. The primary `methodflow.py` pipeline is:

`actual files → recursive scalar/step extraction → evidence table → authored editable chapter →
number/condition audit → 13-category coverage and reproducibility gaps → result.json + artefacts`.

It does **not** run an experiment, infer scientific facts, execute subject randomisation, grant
ethics approval, or turn missing values into defaults.

## Runtime: six steps, deliverable first

0. **Read the case.** Read `/input/case.json` and `/input/task.md`. Keep top-level `case_id` and
   every field name in `output_contract`. Follow the actual files named in `materials`, not labels.
   Work in `/app/work`; final artefacts belong in `/app/output`. Budget: 64 model requests / 900 s;
   save an honest partial chapter early.
1. **Locate evidence.** Resolve **materials.config**, **config_dir**, **logs**, **code**, **protocol**,
   `notes`, and other supplied paths. Supported source text: JSON, YAML-like lines, logs, Markdown,
   INI/TOML-like assignments, Python/shell source (read only), CSV/TSV/XML. Directories are walked
   deterministically with bounded file counts. No repository code is executed.
2. **Write the actual chapter.** Create `/app/work/methods.md`, not an outline. Use the supplied
   design, ordered steps, settings, parameters, data, controls and limitations. Clearly distinguish
   training/validation/test conditions. When two files differ, name both rather than choosing a
   convenient value. A missing detail is `TODO-confirm(author)` plus a gap, never a guessed value.
   `references/16-full-method-chapter.md` is only an illustrative section-order example, not facts.
3. **Optionally declare scope decisions.** Create `/app/work/method-spec.json` only when the task
   actually establishes that a category is not applicable:

   ```json
   {"coverage_overrides": {
     "randomization_blinding": {
       "status": "not_applicable",
       "rationale": "fixed public benchmark; no subject allocation or human assessor",
       "source": "task.md benchmark protocol, paragraph 2"
     }
   }}
   ```

   `not_applicable` without both a case-specific rationale and locatable source is rejected as a
   gap. Never use an override to hide inconvenient missing evidence.
4. **Run extraction and audit.** The evaluator installs this skill at
   `/skills/weekly-skill`; commands run from `/app/work`, so always address the installed
   entry point explicitly rather than assuming the current directory:

   ```bash
   SKILL="${SKILL:-/skills/weekly-skill}"
   python3 -I "$SKILL/scripts/methodflow.py" \
     --case /input/case.json --input-root /input \
     --prose /app/work/methods.md --spec /app/work/method-spec.json \
     --work /app/work --out /app/output
   ```

   Omit `--spec` if there is no explicit scope decision. `--prose` defaults to the case's
   **materials.prose** or `methods.md`. Exit `0` success; `3` partial with named source/repro gaps;
   `4` partial with unsupported numbers/unit conflicts/same-key parameter conflicts; `5`
   refused/undetermined. Every exit writes structured `result.json`; bad JSON, unreadable inputs
   and unexpected processing errors do not leak a traceback.
5. **Repair the chapter, not the evidence.** Read `number_audit.unsupported`, `conflicts`,
   `coverage` and `gap_analysis`. Remove/correct an unsupported number or route it to author
   confirmation; resolve condition scopes from actual records; answer missing design/statistics/
   ethics questions only when evidence exists. Re-run until clean or honestly partial. Then check:

   ```bash
   SKILL="${SKILL:-/skills/weekly-skill}"
   python3 -I "$SKILL/scripts/validate_result.py" /app/output/result.json \
     --contract "$SKILL/resources/output_contract.json" --case /input/case.json
   ```

## What is actually extracted

| artefact | mechanism and boundary |
|-|-|
| `parameter_table[]` | Recursive JSON flattening preserves dotted paths; `name: value` / `name=value` lines keep source file + line; value/unit are separately recorded. Nested objects are **not skipped** as in the old wrapper. |
| `steps[]` | Only explicit numbered protocol steps or structured case steps. Parameters are never converted into steps. A `preprocess` key alone is not an ordered protocol. |
| `sources[]` / `evidence_map[]` | Each parameter has path, JSON path or line, verbatim quote, value and unit; protocol steps have their own locators. |
| `datasets[]` | Dataset/version/split-like keys only. Absence is `not_in_source`; no dataset name is guessed. |
| `number_audit` | Prose values can match parameters **or actual protocol/log excerpts**. Percent/rounded forms are labelled; wrong units and unsupported numbers block a clean exit. |
| `conflicts[]` | Same fully-qualified key with different values lists both sources and asks for condition scope. It never quietly takes the last value. |
| `reproducibility` | Checks code_version, data_version, environment, command and seed independently; a seed proves RNG configuration only, **not** allocation randomisation or blinding. |

The parser is intentionally conservative for non-JSON YAML (anchors, multiline objects and complex
expressions are not evaluated). Free-text numeric support is still matched to a verbatim supplied
excerpt; results that cannot be tied back remain unsupported.

## 13-category coverage contract

Every category appears in `coverage` as `reported`, `missing`, or explicitly `not_applicable`, with
actual evidence and `gap_question` where needed. `gap_analysis.json` is the author action list.

| category | what the writer must support from the case |
|-|-|
| design | study/experiment design; do not infer causality from a label |
| variables | independent/dependent variables, outcomes, covariates |
| controls | control/baseline identity, version and comparable conditions |
| materials_equipment | materials/reagents/instruments/manufacturer/model/hardware |
| steps | ordered actions; ideally input/action/output/decision condition per step |
| parameters | name, value, unit, target and precise origin |
| datasets | name, version, size, preprocessing, split, subset purpose |
| sample_size_repeats | sample size, biological/technical/independent repeats |
| randomization_blinding | allocation/order randomisation and blinding; RNG seed alone is insufficient |
| statistics | metrics, test/model, significance/interval/multiplicity as applicable |
| ethics_safety | approval/consent/exemption and hazards/safety as applicable |
| reproducibility | code/data/environment versions, command, seed, access route |
| limitations | concrete failure scenarios and applicability boundaries, not boilerplate |

## Result and strict output contract

`result.json` has top-level `case_id`, honest `status`, `status_reason`, `sources`, `uncertainty`,
`change_records`, `limits`, the fields above, `coverage`, `gap_analysis`, `findings`, and
`deliverable`. Runtime writes `methods.md`, `parameter_table.json`, `evidence_map.json`,
`gap_analysis.json` and `coverage.json` wholesale, so re-runs are idempotent.

Every case `output_contract` field is mirrored at the **top level**, with exact field spelling and
precedence **engine-derived value > case/spec value > null plus a limits entry**. In particular, a
case saying `status: success` cannot override an audit verdict. A malformed case that cannot reveal
its own field names still gets a structured refusal with a top-level null/unknown case id, but the
engine cannot invent the unreadable contract's names.

## Findings and exit handling

| rule | severity | meaning / action |
|-|-|-|
| `methods.unsupported_prose_number` | high / exit 4 | prose number or unit lacks support in parameters and actual excerpts; correct it or request confirmation |
| `methods.parameter_conflict` | high / exit 4 | same fully-qualified key differs across files; expose both and resolve condition scope |
| `methods.coverage_gap` | medium / exit 3 | one of the 13 categories lacks evidence or a justified N/A declaration; answer from source |
| `methods.prose_missing` | high / exit 3 | editable chapter missing/empty; parameters alone are not a result |
| `methods.input_unreadable` | high / exit 5 | declared config absent, no readable evidence, or malformed case/spec; structured refusal |

Additional `limits` name unreadable source files, missing declared paths, missing reproducibility
anchors and the fact that no computation/experiment was executed. `status=partial` is valid and
honest; do not upgrade it by deleting gap records.

## Minimal example（示例，非正式案例）

```bash
SKILL="${SKILL:-/skills/weekly-skill}"
python3 -I "$SKILL/scripts/run_example.py"
```

The toy config has seed/lr/epochs/batch_size/dropout and deliberately lacks a dataset and most
method categories. The runner proves that good prose is supported, an invented `99` is rejected,
the dataset remains `not_in_source`, the primary run is partial, and contract validation succeeds.
It refreshes `examples/minimal/example_result.json`, clearly labelled as a toy output.

## Verification

```bash
SKILL="${SKILL:-/skills/weekly-skill}"
python3 -B -I "$SKILL/scripts/bench_methodflow.py"  # 12 end-to-end scenarios
python3 -B -I "$SKILL/scripts/run_example.py"       # toy-case and numeric guard
```

The 12 scenarios cover a complete evidence-rich clean case, nested JSON, unsupported values,
parameters vs steps, RNG seed vs allocation, justified/unjustified N/A, parameter conflicts, missing
prose/config, malformed JSON refusal, contract precedence and byte-identical re-runs. They pass
12/12. The historical `assemble_result.py` is retained for compatibility only; it is not the main
workflow or a source of coverage claims.

## External mechanism adapted, not merely cited

GitHub 上 manubot/rootstock 项目把文稿生成机制化为构建流程：机器解析引用、CI 捕捉无效引用，
而不是让 prose 自我保证。 `methodflow.py` applies the same separation here:
the Agent authors the chapter, while deterministic source extraction and numeric/coverage checks
decide whether it can ship. 本环境无法稳定获取 paperswithcode/releasing-research-code，因此不声称复用了该项目；复现锚点
依据本正式题面 rubric 实现，并由本地端到端测试验证。

## Requirements and honest limits

Python 3.10+（3.14 实测），standard library only; no network, model call, YAML package, or
experiment runtime. The pinned evaluator entry point is `/skills/weekly-skill`. This is not a full YAML evaluator, statistical reanalysis, citation verifier, visual PDF
review, or reproduction runner. Keyword coverage locates evidence; it does not prove scientific
adequacy. Rounded numeric matches require human review. Different experimental conditions sharing
a key remain explicit conflicts until the author scopes them. Formula/equation semantics and actual
data splits are not recomputed.
