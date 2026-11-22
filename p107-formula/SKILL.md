---
name: formula-parse
description: >
  Turn a paper's equations into a structured record a reader can check: a variable table
  where every symbol is defined, sourced (paper / inferred / convention) and locatable,
  derivation steps with justifications and declared cross-formula dependencies, boundary
  conditions, and a numeric substitution that is actually evaluated in a sandboxed
  arithmetic evaluator. Checks bracket and LaTeX-environment balance, symbol coverage
  against the expression (matrix and piecewise environments included), brace integrity of
  multi-character sub/superscripts, dimensional agreement of the two declared sides,
  whether substituted symbols are anchored in the table, whether table values contradict
  substituted values, and whether the stated arithmetic reproduces the stated result.
  Reads MathML (mfrac/msub/msup) from publisher XML when provided. Use when a task asks
  for formula recognition, LaTeX recovery, a variable table, derivation checking, symbol
  consistency, unit or dimension checks, or numeric verification of an equation.
---

# formula-parse（公式解析与数学推理）

The task is not "produce LaTeX". It is to produce something a reader can check, which the
rubric states as four questions:

| rubric 四问 | 本 Skill 的回答 | rules when it fails |
|-|-|-|
| 认得准（结构、上下标、括号层级、希腊字母、单位不错位不丢项） | 结构完整性逐项检查 + 符号覆盖闭环 | `formula.unbalanced_braces`, `formula.unbalanced_delimiters`, `formula.environment_unclosed`, `formula.bare_script`, `formula.variable_not_extracted` |
| 讲得清（每个符号有可指回原文的定义、取值范围与单位） | 变量表三要素：definition + source 三级 + locator | `formula.variable_undefined`, `formula.variable_source_undeclared`, `formula.variable_no_locator`, `formula.input_value_conflicts_variable` |
| 推得顺（推导拆成可检查步骤，标明假设与跨公式依赖） | 步骤双端 + 理由 + uses 依赖闭环 | `formula.derivation_missing`, `formula.step_incomplete`, `formula.step_unjustified`, `formula.step_dependency_undeclared`, `formula.step_unknown_dependency`, `formula.boundary_conditions_missing` |
| 算得回（可计算公式代入复算，发现符号/单位/数量级错误） | 沙箱算术求值器实算 + 数值-表格交叉核对 | `formula.substitution_mismatch`, `formula.numeric_incomplete`, `formula.numeric_malformed`, `formula.numeric_input_undeclared`, `formula.tolerance_undeclared`, `formula.substitution_not_evaluable`, `formula.no_numeric_check`, `formula.dimension_mismatch`, `formula.unit_unknown` |

A pasted LaTeX line scores nothing here, because none of the four questions can be checked
from it. A symbol with no row in the variable table, a variable with no locator, a
substitution that does not compute, and a formula with no stated conditions are the four
failures this skill exists to catch — each is a computed finding, not an eyeball judgement.

## Runtime entry — from /input/case.json and task.md to /app/output/result.json

**Step 0 · 读输入.** Load `/input/case.json` first: keep `case_id` and `output_contract`
verbatim (every contract field must reappear in the final result.json), and read the task
text. Then read the actual material files the case names — a PDF, or the publisher XML the
case ships (its formula nodes carry MathML with 分式/上下标 and source IDs). Read actual
files, never infer content from a label or a filename.

**Step 1 · 判形态路由.** From the task wording decide the deliverable (routing table
below). This challenge routes to the formula record; the engine routes by the spec 的
section 字段 (this package audits section formula, and also carries section reproduce for
method-verification cases).

**Step 2 · 先产出目标产物.** Write the structured formula record FIRST, to
`/app/work/formula-record.json`: one entry per formula — latex (transcribed from MathML
preserving 分式/上下标 nesting when that is the source), variable table, derivation steps,
boundary conditions, numeric substitution. Save the partial record early, then improve.
The record is the deliverable; the audit only proves it.

**Step 3 · 构造 spec.** Assemble the audit spec: the record's content under `formulas`,
plus `case_id` and `output_contract` carried over verbatim, plus an honest `limits` list
for anything the material did not provide.

**Step 4 · 运行审计.**

```bash
python scripts/secrun.py --spec /app/work/spec.json --out /app/output
```

Exit codes: `0` clean, `3` review (medium/low findings), `4` blocked (any high), `5`
undetermined (refused — unreadable JSON, non-object spec, missing or unknown section; a
result.json is still written, never a traceback).

**Step 5 · 修发现重跑.** Fix what the Failure-handling table names (add the missing
symbol row, add the locator, declare the tolerance, state the boundary conditions), then
re-run until the status is acceptable or the remaining findings are recorded honestly.

**Step 6 · 合并 result.json.** The script's result.json already echoes `case_id` and
every `output_contract` field (null + a limit note where the audit cannot derive one) and
carries the rubric's three-part structure. Move it to `/app/output/result.json` beside
the deliverable; fill any null contract field by hand from the record — never silently.

## 任务措辞 → 路由决策表

| task.md wording | route | why |
|-|-|-|
| "把公式转成 LaTeX / 还原公式结构" | record latex, run the structural rules | braces, delimiters, environments and scripts are mechanically checkable |
| "给变量表 / 解释每个符号" | variables[] with definition + source + locator | 讲得清 is exactly those three fields per row |
| "推导分步解释" | steps[] with from/to/justification and uses | 推得顺: each step re-walkable, dependencies declared |
| "代入数值验证这个公式" | numeric block: expression + inputs + expected + tolerance | 算得回: the engine evaluates, it does not eyeball |
| "检查符号一致性 / 上下标" | symbol coverage + bare_script rules | lexical extraction vs the declared table |
| "单位 / 量纲检查" | declare lhs_unit and rhs_unit | the dimension check runs only on declared units |
| "矩阵 / 分段函数" | environments in latex; environment balance is checked | \begin without \end will not typeset |
| 材料给的是出版商 XML（MathML） | transcribe MathML mfrac/msub/msup into latex; the node's source id goes into locator | the formula catalog is the source, not a linearised answer |
| 材料只有公式图像 | recognition is upstream: transcribe to latex, then audit; say the image was the source in limits | the engine audits the record, not the pixels |
| 案例没有公式材料（真实缺失分支） | do NOT fabricate formulas or fill unknowns with 0 | report status partial / insufficient_evidence and name what is missing in limits |
| 案例要核对指标但没有可复算公式 | verify the stated metrics against the stated conditions only | derivation or recomputation of missing objects must be reported partial, never back-invented |
| task asks another track (comparison, QA, drafting) | use the section the case declares; this doc details formula | the engine routes by the spec 的 section 字段 |

## Spec fields（构造 spec 的字段表）

| field | type | required | meaning |
|-|-|-|-|
| `case_id` | str | yes (carry through) | input identifier, echoed into result.json |
| `output_contract` | obj | yes (carry through) | every named field is echoed into result.json |
| `section` | str | yes | `formula`（本包也实现 reproduce 等节，按 spec 路由） |
| `formulas[]` | list | yes | one record per formula |
| `formulas[].id` | str | yes | referenced by steps' uses and by findings |
| `formulas[].latex` | str | yes | the expression as transcribed |
| `formulas[].lhs_unit` / `rhs_unit` | str | recommended | the dimension check runs only when both are declared |
| `formulas[].variables[]` | list | yes | {name, definition, source, locator} + optional unit, value |
| `formulas[].variables[].source` | str | yes | paper / inferred / convention — 三级来源 |
| `formulas[].variables[].locator` | str | yes | Eq. n, p.n / Table n / Fig n / MathML source id |
| `formulas[].variables[].value` | number/str | optional | the value the paper gives; cross-checked against numeric inputs |
| `formulas[].steps[]` | list | recommended | {from, to, justification, uses[]} |
| `formulas[].boundary_conditions` | str | recommended | validity range and approximations |
| `formulas[].verified` | bool | yes | an explicit check verdict, not transcription |
| `formulas[].numeric` | obj | recommended | {expression, inputs, expected, tolerance} |
| `formulas[].note_numeric` | bool | optional | set false only when the formula truly permits no substitution |
| `limits[]` | list | recommended | honest gaps (blurry image, missing units in the paper) |

## Worked example（示例，非正式案例结果）

Spec — assembled from a case whose task says "把 Eq.1 转成 LaTeX，给变量表并代入复算"
(`case_id` and `output_contract` come from `/input/case.json` verbatim). This exact file
is `examples/spec.json` and the run below is the verified output of this machine:

```json
{
  "case_id": "case-formula-demo-01",
  "output_contract": {"status": "…", "findings": "…", "evidence_map": "…", "boundary": "…"},
  "section": "formula",
  "formulas": [
    {"id": "F1",
     "latex": "E = h c / \\lambda",
     "lhs_unit": "J", "rhs_unit": "J",
     "variables": [
       {"name": "E", "definition": "photon energy", "source": "paper",
        "locator": "Eq. 1, p.3", "unit": "J"},
       {"name": "h", "definition": "Planck constant", "source": "convention",
        "locator": "Eq. 1, p.3", "unit": "J*s", "value": 6.626e-34},
       {"name": "c", "definition": "speed of light", "source": "convention",
        "locator": "Eq. 1, p.3", "unit": "m/s", "value": 2.998e8},
       {"name": "λ", "definition": "wavelength", "source": "paper",
        "locator": "Eq. 1, p.3", "unit": "m", "value": 5.32e-7}
     ],
     "steps": [{"from": "E = h ν", "to": "E = h c / λ",
                "justification": "ν = c / λ for light in vacuum"}],
     "boundary_conditions": "single photon, vacuum",
     "verified": true,
     "numeric": {"expression": "h*c/lambda",
                 "inputs": {"h": 6.626e-34, "c": 2.998e8, "lambda": 5.32e-7},
                 "expected": 3.734e-19, "tolerance": 1e-21}}
  ]
}
```

```bash
python scripts/secrun.py --spec examples/spec.json --out /app/output   # exit 0
```

Illustrative result.json (示例示意，字段以实际运行为准):

```json
{
  "schema_version": "secrun/v1",
  "case_id": "case-formula-demo-01",
  "section": "formula",
  "status": "clean",
  "severity_counts": {},
  "findings": [],
  "checked": {"section": "formula", "items": 1, "formulas": 1, "variables": 4,
              "steps": 1, "numeric_checks": 1},
  "deliverable": {"kind": "formula_record", "formulas": 1, "ids": ["F1"],
                  "symbol_rows": 4, "derivation_steps": 1, "numeric_checks": 1,
                  "verified_true": 1, "verified_false": 0},
  "evidence_map": [
    {"kind": "formula", "id": "F1", "symbols_missing": [], "dimension": "match",
     "numeric": "match", "verified": true,
     "variables": [{"name": "E", "source": "paper", "has_locator": true},
                   {"name": "h", "source": "convention", "has_locator": true},
                   {"name": "c", "source": "convention", "has_locator": true},
                   {"name": "λ", "source": "paper", "has_locator": true}]}
  ],
  "boundary": {"human_review_and_gaps": [], "declared_limits": []},
  "limits": []
}
```

Greek symbols are named by their character in the variable table (`λ`) while the
expression may spell them (`\lambda`) — the two spellings are matched, and the numeric
evaluator aliases keyword names (`lambda`) so they evaluate normally. The numeric block's
expression is arithmetic over the names in inputs: numbers and `+ - * / ** %`, plus `abs/min/max`.

## result.json 与 rubric 输出要求的三段结构映射

| rubric 要求（原词） | result.json 字段 | 完成标准如何满足 |
|-|-|-|
| 阅读/解析结果（答案、结构化字段；覆盖任务要求且能回到材料定位） | `deliverable`（公式记录概要）+ `findings[]`（逐条 rule/定位） | 变量表、推导步、边界条件、代入核验全部随结果交付，每条 finding 带公式 id |
| 证据与边界（页码、段落、图表或公式位置；未报告和不确定项；无法判断不写成事实） | `evidence_map[]`（每符号 source + has_locator、量纲判定、代入判定）+ `boundary`（human_review_and_gaps、declared_limits） | 每个符号的 locator 可回查 Eq./p./MathML source id；inferred 来源与默认容差进 boundary 而不是冒充事实 |
| 运行状态（成功、部分完成、无法判断或拒答及原因） | `status`（clean/review/blocked/undetermined）+ `severity_counts` + `checked` + `limits` | 异常原因写进 limits 与 boundary，exit 5 拒绝路径仍写 result.json，可人工接管 |

## Rules

### Structure and symbols（认得准）

| rule | severity | what it proves |
|-|-|-|
| `formula.unbalanced_braces` | high | the expression will not typeset |
| `formula.unbalanced_delimiters` | high | brackets do not pair |
| `formula.environment_unclosed` | high | a matrix/cases/aligned environment is opened but never closed |
| `formula.variable_not_extracted` | high | the expression uses symbols the table never defines |
| `formula.bare_script` | low | a multi-character sub/superscript lacks braces (`x_12` typesets as `x_1`) |

### Variable table（讲得清）

| rule | severity | what it proves |
|-|-|-|
| `formula.variable_undefined` | high | no definition |
| `formula.variable_no_locator` | high | the definition cannot be traced to the paper |
| `formula.variable_source_undeclared` | medium | no paper / inferred / convention label |
| `formula.input_value_conflicts_variable` | medium | the substitution inputs a value contradicting the table's declared value for the same symbol |

### Derivation, conditions and verdict（推得顺）

| rule | severity | what it proves |
|-|-|-|
| `formula.derivation_missing` | medium | no steps, so the route cannot be followed |
| `formula.step_incomplete` | high | a step records only one side of the transition |
| `formula.step_unjustified` | medium | a step gives no rule or assumption |
| `formula.step_dependency_undeclared` | medium | a step names another formula in its text but never declares it in uses |
| `formula.step_unknown_dependency` | medium | a declared uses points outside the formula set |
| `formula.boundary_conditions_missing` | medium | the validity range is unstated |
| `formula.verification_missing` | medium | no boolean verdict, so transcription and check look alike |

### Numeric substitution（算得回）

| rule | severity | what it proves |
|-|-|-|
| `formula.substitution_mismatch` | high | the arithmetic does not reproduce the stated result |
| `formula.numeric_incomplete` | high | a check without both expression and expected value |
| `formula.numeric_malformed` | high | the numeric block is not an object, so nothing can be evaluated |
| `formula.numeric_input_undeclared` | medium | a substituted symbol has no row in the variable table |
| `formula.substitution_not_evaluable` | medium | the check cannot run, so it proves nothing |
| `formula.tolerance_undeclared` | low | no pass bound stated; the engine default applies silently |
| `formula.no_numeric_check` | low | no substitution attempted where the formula allows one |
| `formula.unit_unknown` | medium | a unit outside the model, so no dimensional check was possible |
| `formula.dimension_mismatch` | high | the two sides are different kinds of quantity |
| `formula.no_items` | high | no formulas were supplied at all |

## Limits

- **The evaluator is arithmetic only.** Numbers, named inputs and `+ - * / ** %`, plus
  `abs/min/max`. It deliberately cannot call anything, so a formula that needs a special
  function has to be checked by hand and said so.
- **Symbol extraction is lexical.** It reads single letters and Greek characters, minus
  subscripts, function names, environment words and text blocks. A `\text{...}` block's
  content is prose and is dropped whole: a symbol used only inside a text block will not
  be extracted (the conservative direction — it can miss an omission, never invent one).
- **Dimensional checks need both sides declared.** Without lhs_unit and rhs_unit the rule
  is skipped rather than guessed.
- **A variable's unit is checked only when one is declared.** A symbols-only case must
  never be answered with invented units; the dimension check runs on declared units.
- **Single-character scripts are correct as written.** `x_i` and `10^2` never fire; only
  multi-character scripts without braces are flagged.
- **Dependencies: declared ones must resolve; named ones must be declared.** A step that
  names no formula and declares no uses is not flagged; naming one in the step text or
  declaring it in uses each carries an obligation.
- **Boundary conditions are presence-checked.** Whether they are the right ones is a
  reader's judgement, not a rule's.
- **Value cross-checks fire only on declarations.** The table-value-vs-input comparison
  runs only where the variable actually declares a value; nothing forces a value into
  being invented.
- **It does not read the formula image.** Recognition is a separate step; this audits the
  record that comes out of it. A case whose material contains no formula is reported
  partial / insufficient_evidence — the record is never back-invented and unknowns are
  never filled with 0.

## Failure handling（修发现 → 重跑）

| symptom | what to do |
|-|-|
| `variable_not_extracted` | add the symbol to the table — the finding lists which are missing |
| `variable_no_locator` | say where in the paper it is defined, or mark it convention |
| `environment_unclosed` | close the environment (add the matching \end) |
| `bare_script` | brace the script: write it as x with the script in braces |
| `dimension_mismatch` | the equation as written cannot hold; re-read the original |
| `input_value_conflicts_variable` | one of table value and substituted value is wrong — re-read the source |
| `numeric_input_undeclared` | the substituted symbol needs a table row |
| `substitution_mismatch` | recompute by hand; either an input or the transcribed formula is wrong |
| `numeric_malformed` | make the numeric block an object with expression/inputs/expected |
| `tolerance_undeclared` | state the pass bound the case's precision implies |
| `step_dependency_undeclared` | declare the named formula in uses (and make sure it exists) |
| `step_unknown_dependency` | the declared uses points outside the set — add the formula or fix the id |
| `derivation_missing` | record the steps; a result without a route cannot be checked |
| `boundary_conditions_missing` | state the validity range and the approximations |
| `verification_missing` | record an explicit true/false verdict |
| `audit.no_section`（exit 5） | the case could not be run as declared: no or unknown section, unreadable JSON, non-object spec — refused, never a crash |

## 异常处置表（运行异常 → 处置）

| exception | behaviour | where it shows |
|-|-|
| spec 不是合法 JSON | exit 5 refusal; result.json written with `audit.no_section`, message quotes the decode error | no traceback, ever |
| spec 是列表/字符串/数字（非对象） | exit 5 refusal: "the spec file is not a JSON object" | result.json |
| spec 文件缺失 / 不可读 | exit 5 refusal with the OS error text | result.json |
| 无 section 声明 | exit 5 refusal: "no section declared, so no rules apply" | result.json |
| 未知 section（拼错、跨轨误用） | exit 5 refusal naming the unknown value; valid sections live in scripts/sections.py | result.json |
| formulas 为空数组 | `formula.no_items` high — 声称有公式却什么都没给，属 blocked | findings |
| 案例材料本身无公式（真实缺失分支） | 不构造虚构 spec；result.json 标 partial / insufficient_evidence，limits 写明缺失对象；不得反推公式、不得把未知填 0 | status + limits |
| numeric 块是字符串/列表/数字 | `formula.numeric_malformed` high — 不是核对，是坏声明 | findings |
| numeric.inputs 类型错位（列表/字符串） | substitution_not_evaluable medium，reason 写明求值失败点 | findings |
| 变量条目非对象（裸字符串/数字） | 该条目降级跳过，其余条目照常审——不崩溃、不整单作废 | findings only from object entries |
| 单位不在模型内 | `formula.unit_unknown` medium：量纲检查跳过并点名牌，不猜测 | findings |
| 代入无解 / 需要特殊函数 | `formula.substitution_not_evaluable` medium + limits 声明算术求值器边界，按记录人工接管 | findings + limits |
| 图像模糊 / 公式截断 | 识别层如实标注（来源为图像、置信度低）进 boundary 与 limits；引擎只审转写记录 | boundary |
| 重复运行 | 同 spec 重跑 findings 逐字节一致（确定性引擎，无随机源） | 不叠加两轮结果 |
| output_contract 字段不可推导 | 该字段置 null 并在 limits 写一条说明；提交前人工补齐 | limits |

## Requirements

Python 3.9+（3.14 实测）。纯标准库实现，无第三方依赖、无网络、无模型调用。

## Verification

```bash
python scripts/bench_formula.py   # 32 scenarios: one per rule plus false-positive guards
python scripts/bench_sections.py  # 60 scenarios: cross-section regression plus false-positive guards
```

Both pass in full on this machine. The clean baseline in each must report nothing.
Snapshots: examples/bench-report.json and examples/bench-sections-report.json.

## 创新增益（真实能力，bench 可复跑验证）

1. **符号覆盖闭环**：词法符号抽取（希腊字母映射、下标归基、环境词与 text 块剔除、数字
   后单字母按单位处理）对表达式与变量表求差——「表达式用了表里没有的符号」是可计算判
   定，通用 Agent 无法对自己证明符号全覆盖。*边界*：词法抽取，不做视觉识别。
   *证据形式*：bench 的 variable_not_extracted、fp_env_balanced、fp_fo_env_prose 场景。
2. **代入必算**：沙箱 AST 求值器（仅算术节点，lambda/λ/k_B 等非标识符符号内部别名）
   实算每条数值核对，mismatch / malformed / not_evaluable / tolerance 未声明四种结论分
   开——「声称算过」和「真的算过」被区分。*证据形式*：substitution_mismatch、
   numeric_malformed、tolerance_undeclared 场景 + evidence_map 的 numeric 判定。
3. **数值-表格交叉核对**：numeric inputs 与变量表声明的 value 逐符号对比，纯相对差
   （无绝对下限，普朗克常数量级不失效）——代入值与表格值各说各话时点名是谁错。
   *证据形式*：input_value_conflicts_variable 与 fp_input_value_match 场景。
4. **诚实边界结构**：evidence_map（每符号 source/has_locator、量纲与代入判定）与
   boundary（人工确认项、不确定项）分离——inferred 来源、默认容差、未尝试代入都进
   boundary 待确认，不进 severity_counts，低危不稀释高危。*证据形式*：result.json 的
   boundary 与 evidence_map 结构（见 worked example）。

## 生态贡献

- **使用说明**：本文件含从 /input/case.json + task.md 到 /app/output/result.json 的六步
  流程、路由决策表 12 行、spec 字段表、worked example（标注"示例"，本机实跑验证）、
  rubric 三段映射、异常处置表 15 行。
- **依赖**：Python 3.9+（3.14 实测）；纯标准库，无安装步骤、无网络。
- **配置**：声明式——变量表、推导步、数值核对、量纲声明均按 spec 声明生效，未声明不
  惩罚（如 lhs_unit/rhs_unit 缺省则量纲检查跳过并点名牌）；spec 字段表即配置说明。
- **示例标注**：examples/spec.json 是最小调用示例（含 case_id 与 output_contract），
  examples/bench-report.json 与 examples/bench-sections-report.json 是 bench 实跑报告
  快照——均为示例，不冒充正式案例结果。
- **资源复用**：scripts/units.py 是独立可导入的单位解析与换算模块（前缀、复合单位、
  量纲向量）；scripts/sections.py 的规则库可经 spec 扩展；两套 bench 可独立复跑验证。
- **适用范围**：行间公式、上下标、矩阵/分段环境、希腊字母、单位量纲、数值代入核验；
  也覆盖 reproduce 等同引擎其余 section（按 spec 的 section 字段路由）；不负责图像识
  别本身与公式的视觉渲染。
- **限制**：见 Limits——算术求值器、词法抽取、量纲需双侧声明、text 块整体剔除等。
- **维护**：规则与场景一一对应（新增规则必须带 bench 场景 + clean 守卫）；改脚本后必须
  重跑 bench_formula.py（32）与 bench_sections.py（60）并保持全过；规则 id 变更须同步
  本文档规则表（自查方法：跑两套 bench 并核对 clean 基线零发现）。

引擎已实现输出契约：spec 顶层提供的 case_id 原样回填 result.json；output_contract 的每
个字段——result 已携带的保留、spec 顶层提供同名值的原样拷入（大体积输入字段除外）、
推导不出的置 null 并在 limits 说明。因此把交付字段值放进 spec 顶层即直通最终 result.json。
