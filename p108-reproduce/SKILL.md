---
name: reproduce-paper
description: >
  Audit a paper-reproduction report as a closed loop: material location, environment,
  parameter recovery, code run, result comparison, graded verdict. Checks that another
  machine could re-run it — commit, data version, command and logs recorded, and no
  blank commands — that every material carries source, version and state (license for
  redistributable artefacts), that parameters are classed as paper / code / assumed with
  a basis AND a value, that a dependency differing from the paper's declaration is
  flagged, that a comparison carries a tolerance and a basis, that a metric with no
  values is named, that an out-of-tolerance metric says whether the gap is numeric noise
  or methodological and why, and that the graded verdict agrees with its own record —
  never reproducible over missing materials, never partial without a named gap. Use when
  a task asks to reproduce a paper, verify its method, align hyper-parameters into an
  executable table, or report on whether results can be rebuilt.
---

# reproduce-paper（论文复现与方法验证）

## v4 · execute the supplied candidate methods before making a reproduction claim

The official revised task says that two supplied candidate numerical methods must actually run.
The old report-only checklist is therefore not sufficient. Use this real runner once the actual
case files have been inventoried:

```bash
python3 /skills/weekly-skill/scripts/rerun.py \
  --manifest /app/work/execution.json --workspace /app/work/materials \
  --out /app/work/execution --case /input/case.json
```

`rerun.py` verifies every declared file SHA-256 before launching. Each command has a unique id,
one **workspace-local, hash-declared** Python `.py` entry script and explicit argument array. It
runs `sys.executable -I`, no shell, `stdin=DEVNULL`, a timeout and declared seed (`PYTHONHASHSEED`
and `SEED` environment variables); options such as `--seed` must also be declared in the command.
There is no automatic `pip` installation, external executable, `-c`, `-m` or out-of-workspace path.
A missing file/hash/dependency refuses with exit 5; an actual nonzero exit or timeout writes its
real status/logs and exits 4; completed metric mismatches exit 3; checks that all completed and
all matched exit 0. Every branch writes `result.json`. This is a controlled argument runner,
**not a malware sandbox or a container claim**; reviewed scientific methods only, no downloaded
arbitrary executable.

Minimal manifest (values must come from the real paper/repository, not from this illustrative
example; the expected number and tolerance are decided before execution):

```json
{
  "schema_version": "candidate-execution/v1",
  "code_version": "ACTUAL COMMIT OR LOCAL SNAPSHOT ID",
  "data_version": "ACTUAL DATASET VERSION", "seed": 41, "timeout_s": 60,
  "files": {"candidate.py": {"sha256": "ACTUAL SHA256", "license": "ACTUAL LICENSE"}},
  "dependencies": ["numpy==ACTUAL.VERSION"],
  "parameters": [{"name": "n", "source": "paper", "value": 64, "locator": "Table 1"}],
  "commands": [{"id": "method-A", "seed": 41,
    "argv": ["{python}", "candidate.py", "--seed", "41"],
    "metrics": [{"name": "integral", "paper": 0.3333333333333333,
      "paper_locator": "analytic/source value", "statistic": "single deterministic grid",
      "tolerance": {"abs": 0.00005, "rel": 0}, "json_path": "integral"}]}]
}
```

A repeated command may declare the same `"series"` for genuine seed-variation aggregation. Never
pool different algorithms and call their disagreement random variation. Use `output:"result.json"`
when a candidate writes a JSON file; without it the runner parses only the **last non-empty stdout
line** as JSON. `json_path` uses dotted paths or JSON Pointer. Not-created/malformed/missing
output is undetermined/failure evidence, not 0 and not a fabricated reproduction metric.

The actual outputs are `result.json`, `run-manifest.json`, and
`runs/<command-id>/stdout.log + stderr.log`. They include real interpreter/platform/dependency
versions, actual file hashes, argv, seed, return code, metric source, raw metric value, and
predeclared abs+relative tolerance. No runtime identities or result scores are fabricated. Put
the result path or its JSON object in `actual_run` before running `secrun.py`; the audit will
reject a `reproducible` verdict over no actual launch, differing code/data versions, failure,
missing metrics or a tolerance miss. `execution_records`, `environment_snapshot`,
`comparison_metrics` and `run_manifest` are available contract aliases.

Failure classification is separate from scientific mismatch: `dependency_error`,
`missing_material`, `declaration_or_output_error`, `timeout`, `execution_error`,
`metric_undetermined`, `metric_out_of_tolerance` (methodological), plus an actionable next step.
The runner records `paper_reproduction_claim:false` for this candidate-only verification: it can
prove what this snapshot did, never recreate a missing original repository/dataset/container or
physical experiment. The `run-manifest.json` manifests a local synthetic candidate in benches;
it does not constitute an official-paper replication. `secrun.py` continues to audit a complete
report when no execution has been claimed; it does not turn planning into completed execution.

A reproduction report is only useful if a second person can act on it. The rubric states
this as four questions, and the loop as seven links — every link is mechanically
checkable, and a missing link is a finding, not an opinion:

| rubric 四问 | 本 Skill 的回答 | rules when it fails |
|-|-|-|
| 找得齐（代码、数据、参数、依赖、许可证定位到版本，缺失显式登记） | materials[] 三要素 + 四件复跑工件（commit / data_version / commands / logs） | `repro.material_without_source`, `repro.material_without_version`, `repro.material_state_undeclared`, `repro.material_no_license`, `repro.no_commit`, `repro.no_data_version`, `repro.no_command`, `repro.command_blank`, `repro.stage_missing`, `repro.no_stages` |
| 跑得对（环境与关键参数按论文复原，不按仓库默认或本机习惯） | 环境快照三字段 + 依赖版本冲突核对 + 参数三级来源、取值与定位 | `repro.environment_incomplete`, `repro.env_conflict_unflagged`, `repro.parameter_source_undeclared`, `repro.parameter_no_value`, `repro.parameter_no_locator`, `repro.assumed_without_justification` |
| 对得上（结果与论文指标可比，偏差落在事前容差内） | 容差 + 比较口径 + 统计方式 + 逐指标双侧数值与判决 | `repro.no_tolerance`, `repro.no_comparison_basis`, `repro.no_statistic`, `repro.metric_value_missing`, `repro.metric_no_verdict`, `repro.no_logs`, `repro.no_exit_status` |
| 讲得清（差异归因到具体原因，结论可独立复核） | 差异二分类 + 解释 + 结论分级与依据互相咬合 | `repro.difference_unclassified`, `repro.difference_unexplained`, `repro.verdict_unclassified`, `repro.verdict_without_basis`, `repro.verdict_inconsistent_with_missing`, `repro.partial_verdict_without_gaps`, `repro.stage_unknown` |

## The four failures this exists to catch

**A report nobody can re-run.** No commit, no data version, no command — or a commands
list whose every entry is blank. The verdict may be honest and it is still unverifiable.

**A version difference nobody recorded.** The installed torch is 2.3.1 and the paper says
2.1.0. Left unflagged, every later divergence has no explanation — versions are the first
thing that explains a divergence.

**A parameter table that cannot be executed.** A learning rate with provenance but no
value, or chosen by the reproducer with no justification. Three categories — paper, code,
assumed — and each carries an obligation: paper/code must locate, assumed must justify,
and all must state the value.

**A verdict its own record cannot support.** "Reproducible" while a declared material is
missing; "partial" while no metric misses tolerance, no material is missing and no
dependency conflicts — the gap that justifies "partial" is never named. And a metric
outside tolerance with no delta_class leaves "the method failed" and "the run was
unlucky" indistinguishable, which is the whole point of the exercise.

## Runtime entry — from /input/case.json and task.md to /app/output/result.json

**Step 0 · 读输入.** Load `/input/case.json` first: keep `case_id` and `output_contract`
verbatim (every contract field must reappear in the final result.json), and read the task
text. Then read the actual material files the case names — paper text, repository
manifests, training logs, or the packaged candidate numerical methods the case ships.
Read actual files; the paper text and the actual input files are the factual basis, and a
wrong domain label never licenses invented data.

**Step 1 · 判形态路由.** From the task wording decide the deliverable (routing table
below). This challenge routes to the reproduction report; the engine routes by the spec
的 section 字段 (this package audits section reproduce, and also carries section formula
for numeric re-verification).

**Step 2 · 先产出目标产物.** Write the reproduction report FIRST, to
`/app/work/repro-report.json`: the six loop stages in order — materials with source and
version and state, the environment snapshot, the parameter table with values and
provenance, the run record with logs and exit status, the comparison with tolerance and
per-metric verdicts, the graded verdict with its basis. Save the partial report early,
then improve.

**Step 3 · 构造 spec.** Assemble the audit spec: the report's content, plus `case_id` and
`output_contract` carried over verbatim, plus an honest `limits` list for anything the
material did not provide (缺失原始数据/仓库时显式登记，不冒充满分复现).

**Step 4 · 运行审计.**

```bash
python3 /skills/weekly-skill/scripts/secrun.py --spec /app/work/spec.json --out /app/output
```

Exit codes: `0` clean, `3` review (medium/low findings), `4` blocked (any high), `5`
undetermined (refused — unreadable JSON, non-object spec, missing or unknown section; a
result.json is still written, never a traceback).

**Step 5 · 修发现重跑.** Fix what the Failure-handling table names (record all three
artefacts, pin the version, class the parameter, classify the gap, align the verdict with
its record), then re-run until the status is acceptable or the remaining findings are
recorded honestly.

**Step 6 · 合并 result.json.** The script's result.json already echoes `case_id` and
every `output_contract` field (null + a limit note where the audit cannot derive one) and
carries the rubric's three-part structure. Move it to `/app/output/result.json` beside
the deliverable; fill any null contract field by hand from the report — never silently.

## 任务措辞 → 路由决策表

| task.md wording | route | why |
|-|-|-|
| "复现这篇论文 / 报告复现状态" | full loop record, then audit | the deliverable is the six-stage closed loop |
| "把正文/附录/仓库的超参对齐成可执行参数表" | parameters[] with source + value + locator | 跑得对: provenance, value and location per row |
| "把训练日志与论文表格对齐成带容差的对比表" | results with tolerance + basis + per-metric verdicts | 对得上: the comparison is checkable, not eyeballed |
| "结果对不上，拆解原因" | out-of-tolerance metrics need delta_class + explanation | 讲得清: noise vs methodological, explained |
| "给出两份候选实现/方法，问哪份与论文一致" | one report per candidate, audit each, compare per-metric verdicts; state 事前容差 before comparing | the case's stated tolerance, not a post-hoc one |
| "环境快照 / 能否在其他机器重建" | environment three fields + dependencies_detail | a rebuild needs dependencies, hardware and seed |
| "仓库/代码不可访问" | material state missing, explicitly registered | a missing item is recorded, never skipped silently |
| "数据需申请 / 评价脚本缺失" | record the gap in the material row and in limits; verdict reflects it | partial coverage must shape the verdict, not hide |
| "依赖版本与论文不一致" | dependencies_detail with both versions + conflict note | the divergence explanation starts at versions |
| "生成复现报告（可复现/部分/不可复现）" | verdict in the three grades + basis | 讲得清: the grade and its basis are checkable |
| 案例材料缺原始数据/仓库（真实缺失分支） | verify only the stated metrics against stated conditions; report partial / insufficient_evidence | never back-invent missing objects or fill unknowns with 0 |
| task asks another track (formula, QA, drafting) | use the section the case declares; this doc details reproduce | the engine routes by the spec 的 section 字段 |

## Spec fields（构造 spec 的字段表）

| field | type | required | meaning |
|-|-|-|-|
| `case_id` | str | yes (carry through) | input identifier, echoed into result.json |
| `output_contract` | obj | yes (carry through) | every named field is echoed into result.json |
| `section` | str | yes | `reproduce`（本包也实现 formula 等节，按 spec 路由） |
| `commit` | str | yes | the code revision the results come from |
| `data_version` | str | yes | the data version the inputs came from |
| `commands` | list | yes | the commands that produced the results (non-blank) |
| `stages` | list | optional | declare the loop stages; must name the six the loop defines |
| checklist.materials[] | list | yes | {name, source, version, state} + kind/license for redistributable artefacts |
| checklist.environment | obj | yes | {dependencies, hardware, seed} + dependencies_detail[] |
| checklist.environment.dependencies_detail[] | list | when versions differ | {name, paper_version, actual_version, conflict} |
| checklist.parameters[] | list | yes | {name, source(paper/code/assumed), value, locator, justification} |
| checklist.run | obj | yes | {logs, exit_status} |
| checklist.results | obj | yes | {tolerance, comparison_basis, statistic, metrics[]} |
| checklist.results.metrics[] | list | yes | {name, paper, reproduced, within_tolerance, delta_class, explanation} |
| checklist.verdict | str | yes | reproducible / partially_reproducible / not_reproducible |
| checklist.verdict_basis | str | yes | the metrics and tolerances the grade rests on |
| `limits[]` | list | recommended | honest gaps (repository inaccessible, data needs application, eval script missing) |

## Worked example（示例，非正式案例结果）

Spec — assembled from a case whose task says "按论文复现 Table 2 的主指标并给出分级结论"
(`case_id` and `output_contract` come from `/input/case.json` verbatim). This exact file
is examples/spec.json and the run below is the verified output of this machine:

```json
{
  "case_id": "case-reproduce-demo-01",
  "output_contract": {"status": "…", "findings": "…", "evidence_map": "…", "boundary": "…"},
  "section": "reproduce",
  "commit": "a1b2c3d4e5f6",
  "data_version": "dataset@2024-05",
  "commands": ["python train.py --config cfg/a.yaml"],
  "checklist": {
    "materials": [{"name": "dataset", "source": "repo", "version": "v1.2",
                   "state": "present"}],
    "environment": {"dependencies": "pinned in requirements.txt",
                    "hardware": "A100 40GB", "seed": "0"},
    "parameters": [{"name": "lr", "source": "paper", "value": "3e-4",
                    "locator": "Table 1, p.4"}],
    "run": {"logs": "logs/train.log", "exit_status": "succeeded"},
    "results": {"tolerance": "1e-3",
                "comparison_basis": "Table 2 main metric",
                "statistic": "mean of 5 seeds",
                "metrics": [{"name": "accuracy", "paper": 0.912,
                             "reproduced": 0.9108, "within_tolerance": true}]},
    "verdict": "reproducible",
    "verdict_basis": "all metrics within tolerance"
  }
}
```

```bash
python3 /skills/weekly-skill/scripts/secrun.py --spec /skills/weekly-skill/examples/spec.json --out /app/output   # exit 0
```

Illustrative result.json (示例示意，字段以实际运行为准):

```json
{
  "schema_version": "secrun/v1",
  "case_id": "case-reproduce-demo-01",
  "section": "reproduce",
  "status": "clean",
  "severity_counts": {},
  "findings": [],
  "checked": {"section": "reproduce", "items": 7, "stages_present": 6,
              "materials": 1, "parameters": 1, "metrics": 1, "verdict": "reproducible"},
  "deliverable": {"kind": "reproduction_report",
                  "stages_present": ["materials", "environment", "parameters", "run",
                                     "results", "verdict"],
                  "artefacts": {"commit": true, "data_version": true, "commands": true},
                  "verdict": "reproducible", "metrics": 1, "out_of_tolerance": 0},
  "evidence_map": [
    {"kind": "stage", "stage": "materials", "present": true},
    {"kind": "material", "name": "dataset", "source": "repo", "state": "present",
     "has_version": true},
    {"kind": "parameter", "name": "lr", "source": "paper", "has_value": true,
     "has_locator": true},
    {"kind": "metric", "name": "accuracy", "paper": 0.912, "reproduced": 0.9108,
     "within_tolerance": true, "delta_class": null}
  ],
  "boundary": {"human_review_and_gaps": [], "declared_limits": []},
  "limits": []
}
```

A dependency divergence is recorded in environment.dependencies_detail:
`{"name": "torch", "paper_version": "2.1.0", "actual_version": "2.3.1", "conflict": "..."}`.
A metric outside tolerance needs `delta_class` — numeric_noise or methodological — plus an
explanation, and the graded verdict must name the gap that justifies it.

## result.json 与 rubric 输出要求的三段结构映射

| rubric 要求（原词） | result.json 字段 | 完成标准如何满足 |
|-|-|-|
| 阅读/解析结果（答案、结构化字段；覆盖任务要求且能回到材料定位） | `deliverable`（复现报告概要：六阶段、四工件、结论分级）+ `findings[]`（逐条 rule/定位） | 参数表、环境快照、对比表与分级结论全部随结果交付，每条 finding 带阶段/条目定位 |
| 证据与边界（页码、段落、图表、字段或公式位置；未报告和不确定项） | `evidence_map[]`（每阶段 present、每材料 state、每参数 source/value/locator、每指标 within_tolerance/delta_class）+ `boundary`（human_review_and_gaps、declared_limits） | 每个参数可回查 Table/p.，版本差异与 assumed 参数进 boundary 待确认，缺失材料显式登记 |
| 运行状态（成功、部分完成、无法判断或拒答及原因） | `status`（clean/review/blocked/undetermined）+ `severity_counts` + `checked` + `limits` | 异常原因写进 limits 与 boundary，exit 5 拒绝路径仍写 result.json，可人工接管 |

## Rules

### Loop and artefacts（找得齐：闭环与四件工件）

| rule | severity | what it proves |
|-|-|-|
| `repro.stage_missing` | high | a loop stage is absent or empty |
| `repro.no_stages` | medium | no loop path was declared (explicitly empty or non-list stages) |
| `repro.stage_unknown` | low | a declared stage is outside the six the loop defines |
| `repro.no_commit` | high | the code revision is not recorded |
| `repro.no_data_version` | high | the inputs cannot be restored |
| `repro.no_command` | high | the run cannot be repeated |
| `repro.command_blank` | low | every commands entry is blank, so nothing is runnable |
| `repro.no_logs` / `repro.no_exit_status` | medium | execution cannot be inspected |

### Materials（找得齐：材料定位）

| rule | severity | what it proves |
|-|-|-|
| `repro.material_without_source` | high | a material has no provenance |
| `repro.material_without_version` | medium | the version is unrecorded |
| `repro.material_state_undeclared` | medium | present / missing / partial not stated |
| `repro.material_no_license` | medium | a declared code/repository/weights artefact records no license |

### Environment and parameters（跑得对）

| rule | severity | what it proves |
|-|-|-|
| `repro.environment_incomplete` | medium | a rebuild field is missing |
| `repro.env_conflict_unflagged` | high | an installed version differs from the paper's |
| `repro.parameter_source_undeclared` | high | paper / code / assumed not stated |
| `repro.parameter_no_value` | medium | provenance without the value — the table cannot be executed |
| `repro.assumed_without_justification` | high | a chosen parameter is unjustified |
| `repro.parameter_no_locator` | medium | a claimed source is not located |

### Comparison and verdict（对得上 + 讲得清）

| rule | severity | what it proves |
|-|-|-|
| `repro.no_tolerance` | high | agreement cannot be judged |
| `repro.no_comparison_basis` | medium | what is being aligned is unstated |
| `repro.no_statistic` | low | no aggregation declared |
| `repro.metric_value_missing` | medium | a metric records neither value, so nothing is compared |
| `repro.metric_no_verdict` | high | a metric does not say whether it passed |
| `repro.difference_unclassified` | high | the gap is neither noise nor methodological |
| `repro.difference_unexplained` | medium | classified but not explained |
| `repro.verdict_unclassified` | high | the grade is not one of the three |
| `repro.verdict_without_basis` | high | the grade carries no reason |
| `repro.verdict_inconsistent_with_missing` | high | "reproducible" over declared-missing materials |
| `repro.partial_verdict_without_gaps` | medium | "partial" names no metric miss, no missing material, no conflict |
| `repro.execution_claim_unsupported` | high | reproducible verdict without actual launch/completion |
| `repro.execution_revision_mismatch` | high | code/data version differs between actual run and report |
| `repro.execution_record_unreadable` / `repro.execution_record_incomplete` | high | actual record is unreadable or lacks command, return-code/log evidence |
| `repro.execution_command_failed` | high | actual command did not complete; classify failure, never suppress it |
| `repro.execution_metric_malformed` | high | alleged computed metric record is not an object |
| `repro.execution_metric_undetermined` | medium | actual metric cannot be compared and must not be presented as passing |
| `repro.execution_difference_unexplained` | medium | actual out-of-tolerance difference has no concrete explanation |
| `repro.execution_without_comparison` | medium | zero exit alone; no metrics compared |
| `repro.verdict_inconsistent_execution` | high | declared reproducible or within-family verdict conflicts with execution/tolerances |
| `repro.env_version_conflict` | high | actual dependency version differs from declared run requirement |
| `repro.log_truncation_review` | medium | a retained stdout/stderr file exceeds the review cap |
| `repro.execution_failed` / `repro.run_incomplete` / `repro.metric_spec_malformed` | high | actual runner error evidence with next action |
| `repro.metric_out_of_tolerance` / `repro.metric_undetermined` | high / medium | actual metric gap or inability to compare |
| `repro.refused` | high | no attempt is made until declaration/material/hash errors are corrected |

## Limits

- **There are two entry points with different evidence.** `secrun.py` without `actual_run`
  audits a report, not execution. `rerun.py` actually launches declared methods; with
  `actual_run`, execution_checks revalidates that the report matches the record.
- **This is not container isolation.** The runner restricts paths/argv and uses `python -I`, but
  cannot prove arbitrary candidate code is harmless. Run only reviewed declared scientific
  materials; no package installation or external shell commands are provided.
- **Hardware and version adequacy is not judged**, only presence and conflict.
- **delta_class is declared.** The audit requires a class and an explanation; it cannot
  decide which one is right without the numbers and the method.
- **A tolerance is required but not validated.** Whether 1e-3 is appropriate for the
  metric is a domain judgement — the case's 事前容差, not a post-hoc one, belongs in the
  spec.
- **Version conflicts are string comparisons.** 2.1.0 vs 2.1.00 reads as a conflict.
- **It does not bootstrap an environment.** Building the snapshot is outside this skill.
- **Missing data or a missing repository is a recorded branch, not a failure to hide.**
  The material row says missing, the limits say what could not be covered, and the
  verdict reflects it — missing objects are never back-invented and unknowns are never
  filled with 0.
- **The license check is gated on a declared kind.** Only code, repository and weights
  artefacts are asked for a license; a paper or dataset without the field is never
  flagged.

## Failure handling（修发现 → 重跑）

| symptom | what to do |
|-|-|
| `no_commit` / `no_data_version` / `no_command` | record all three; without them the verdict is hearsay |
| `command_blank` | put the actual runnable command in the list |
| `env_conflict_unflagged` | record both versions and what the difference might explain |
| `material_without_version` | pin the version the run used |
| `material_state_undeclared` | say present / missing / partial — missing is an honest answer |
| `parameter_no_value` | carry the value itself, not just its provenance |
| `parameter_no_locator` | say where in the paper or code the value comes from |
| `assumed_without_justification` | state why that value, with a sensitivity note if possible |
| `difference_unclassified` | decide noise or method; then explain it |
| `metric_value_missing` | record both the paper value and the reproduced value |
| `verdict_inconsistent_with_missing` | either the material is recovered, or the verdict drops to partial |
| `partial_verdict_without_gaps` | name the metric miss, the missing material or the conflict that justifies "partial" |
| `verdict_without_basis` | give the basis — the metrics and their tolerances |
| `audit.no_section`（exit 5） | the case could not be run as declared: no or unknown section, unreadable JSON, non-object spec — refused, never a crash |

## 异常处置表（运行异常 → 处置）

| exception | behaviour | where it shows |
|-|-|
| spec 不是合法 JSON | exit 5 refusal; result.json written with `audit.no_section`, message quotes the decode error | no traceback, ever |
| spec 是列表/字符串/数字（非对象） | exit 5 refusal: "the spec file is not a JSON object" | result.json |
| spec 文件缺失 / 不可读 | exit 5 refusal with the OS error text | result.json |
| 无 section 声明 | exit 5 refusal: "no section declared, so no rules apply" | result.json |
| 未知 section（拼错、跨轨误用） | exit 5 refusal naming the unknown value; valid sections live in scripts/sections.py | result.json |
| checklist 缺失或非对象 | 六阶段全报 stage_missing——闭环没有记录就没有闭环 | findings |
| materials 条目非对象（裸字符串/数字） | 该条目降级跳过，其余条目照常审——不崩溃、不整单作废 | findings only from object entries |
| parameters / metrics 类型错位（字符串/数字当列表） | 降级为空列表按缺 stage 处理；字段错位由 stage_missing 与 no_tolerance 点名 | findings |
| 材料缺失 / 数据需申请 / 仓库不可访问 | material state 记 missing 并登记进 limits 与 boundary；verdict 必须反映（reproducible 会被 verdict_inconsistent_with_missing 拦下） | findings + limits + boundary |
| 依赖版本冲突未标注 | `repro.env_conflict_unflagged` high——后续偏差的第一解释位 | findings |
| delta_class 拼写错误 | `repro.difference_unclassified` high：只认 numeric_noise / methodological | findings |
| verdict 拼写错误 | `repro.verdict_unclassified` high：只认三档 | findings |
| commands 全空白 | `repro.command_blank` low（no_command 不误报） | findings |
| 超长日志 / 超大 spec | 单遍正则与字典检查，无模型调用；超大 spec 数秒内审完 | status unaffected |
| 重复运行 | 同 spec 重跑 findings 逐字节一致（确定性引擎，无随机源） | 不叠加两轮结果 |
| output_contract 字段不可推导 | 该字段置 null 并在 limits 写一条说明；提交前人工补齐 | limits |

## Requirements

Python 3.9+（3.14 实测）。纯标准库实现，无第三方依赖、无网络、无模型调用。

## Verification

```bash
python3 /skills/weekly-skill/scripts/bench_reproduce.py  # 33 scenarios: checklist plus FP guards
python3 /skills/weekly-skill/scripts/bench_sections.py   # shared cross-section regression
python3 /skills/weekly-skill/scripts/bench_execution.py  # 19 real-run/exit/hash/determinism checks
```

The clean baseline in each must report nothing. The executable bench really runs two distinct
methods (trapezoid and Simpson) plus one same-series trapezoid seed repeat for `∫₀¹x²dx`, and
independently verifies `1/3 + 1/(6·64²)` for trapezoid and `1/3` for Simpson, rather than trusting
its own stdout. It also tests an actual timeout, an actual nonzero exit, missing/hash-mismatched
materials, dependency absence, a forbidden `-c`/outside path, malformed declaration, byte-
identical results and full case contract passthrough. Reports remain synthetic verification,
not an original paper or platform score. Snapshots: examples/bench-report.json,
examples/bench-sections-report.json and scripts/report_execution.json.

## 创新增益（真实能力，bench 可复跑验证）

1. **复现闭环的机械咬合**：六阶段逐一 presence-check、四件复跑工件（commit / data
   version / command / logs）逐一登记，命令空白单独点名——"报告看起来完整"和"第二台
   机器真能重跑"被区分开，通用 Agent 无法对自己证明闭环无缺口。*边界*：读报告不执行
   代码。*证据形式*：bench_reproduce 的 stage_missing / no_stages / command_blank 等场景。
2. **参数表可执行性**：三级来源（paper / code / assumed）+ 取值本身 + 定位 + assumed 的
   理由，四要素逐行核对——"有出处没取值"的参数表不可执行，被单独点名。*证据形式*：
   parameter_no_value / parameter_no_locator / assumed_without_justification 场景。
3. **结论与记录咬合检查**：verdict 必须与自己的记录一致——"reproducible" 压在缺失材料
   上、"partial" 说不缺口、指标超容差不分类不解释，三种"结论脱离记录"都是计算判定。
   *证据形式*：verdict_inconsistent_with_missing、partial_verdict_without_gaps +
   fp_partial_with_gap 场景。
4. **诚实边界结构**：evidence_map（每阶段/材料/参数/指标一条账）与 boundary（人工确认
   项、不确定项）分离——版本差异、assumed 参数、缺失材料进 boundary 待确认，不进
   severity_counts；缺失数据/仓库分支显式登记而非冒充满分复现。*证据形式*：result.json
   的 boundary 与 evidence_map 结构（见 worked example）。

## 生态贡献

- **使用说明**：本文件含从 /input/case.json + task.md 到 /app/output/result.json 的六步
  流程、路由决策表 12 行、spec 字段表、worked example（标注"示例"，本机实跑验证）、
  rubric 三段映射、异常处置表 15 行。
- **依赖**：Python 3.9+（3.14 实测）；纯标准库，无安装步骤、无网络。
- **配置**：声明式——材料状态、参数分级、容差口径、依赖明细均按 spec 声明生效，未声明
  不误报（如 license 检查只在声明 kind 的条目上触发）；spec 字段表即配置说明。
- **示例标注**：examples/spec.json 是最小调用示例（含 case_id 与 output_contract），
  examples/bench-report.json 与 examples/bench-sections-report.json 是 bench 实跑报告
  快照——均为示例，不冒充正式案例结果。
- **资源复用**：复现清单模板即 spec 字段表（materials/environment/parameters/run/
  results/verdict 可直接改用）；scripts/sections.py 的规则库可经 spec 扩展；两套 bench
  可独立复跑验证。
- **适用范围**：参数/代码/指标验算与差异归因子场景——超参对齐、日志对表格、带容差的
  结果比较、分级复现结论；也覆盖 formula 等同引擎其余 section（按 spec 的 section 字段
  路由）；不负责实际执行训练或自举环境。
- **限制**：见 Limits——读报告不跑代码、版本冲突是字符串比较、容差不校验合理性、
  delta_class 申报制等。
- **维护**：规则与场景一一对应（新增规则必须带 bench 场景 + clean 守卫）；改脚本后必须
  重跑 bench_reproduce.py（33）、bench_sections.py（全部共享回归）与 bench_execution.py（19）
  并保持全过；规则 id 变更须同步本文档规则表（自查方法：跑全部 bench 并核对 clean 基线
  零发现）。方法参考 https://github.com/mlcommons/mlcube 和 mlcube_examples 的固定任务/runner
  思路；真实落地是 rerun.py::execute / finalize、execution_checks.py::audit 的哈希/命令/
  环境/日志/容差记录，不声称采用了未运行的 MLCube 容器或原训练代码。

引擎已实现输出契约：spec 顶层提供的 case_id 原样回填 result.json；output_contract 支持 dict
及 list 中的 name/field/key/id 声明。result 已携带的保留，spec 顶层同名完整值按原类型直通
（包括 formulas/run 等数组对象），无法推导的置 null 并在 limits 说明。已知 case 的
undetermined/unknown-section 退出 5 也保留 case_id 和全契约字段；不可解析 JSON 则结构化
refusal，不伪造不存在的标识。因此把交付字段值放进 spec 顶层即直通最终 result.json。
