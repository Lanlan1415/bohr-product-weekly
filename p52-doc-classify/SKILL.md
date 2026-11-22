---
name: doc-classify
description: >
  Classify a batch of research documents (text records) into a declared cue-based
  taxonomy, then land the labels as real directory work with a five-step protocol
  that is engine-implemented end to end. Every label records the exact cues and
  example snippets that matched, and the confidence is that label's share of all
  cue hits — recomputable by anyone holding the record and the taxonomy. A record
  may carry several labels at once (multi-label is recorded with a primary, never
  collapsed); a record nothing matches lands in 未分类 with the reason. Batch
  runs are byte-identical on rerun. The landing protocol turns labels into
  inventory (P1: per-file sha256, size, type, readability — 0-byte, encrypted
  PDF and unreadable files named), a naming plan (P3: category/year directories,
  author-year-title template with a declared degradation chain, collision solved
  by hash suffix), dedup and version separation (P4: exact duplicates by hash
  archived never deleted, near duplicates by DOI or title+author+year kept for
  manual confirm, preprint-vs-published relations) and a reversible journal
  (P5: both-end sha256 per move, never overwrite a differing target, manifest
  resume makes a rerun zero-ops, rollback restores the original tree verified
  by hash). Use when a task supplies documents (records or files) plus a
  category scheme that must be applied, audited, renamed, deduplicated,
  versioned and summarised over a whole batch.
---

# doc-classify（文献与资料自动分类）

The failure this prevents is classification that cannot be audited and
organisation that stops at suggestions: a chat reply of tags nobody can
re-check, a document spanning two categories forced into one, a document that
fits nothing pushed into the least-bad drawer, renames and dedup that overwrite
or delete irreversibly, and a batch that cannot be replayed, summarised or
rolled back.

Five properties decide whether this task is done right, and each is enforced by
the engine (not by prose):

| property | enforcement |
|-|-|
| 分类规则可解释 | every label carries matched_cues and matched_examples (the exact declared strings found in the record) plus a confidence that is the label's share of all cue hits; the declared taxonomy is echoed in the result, so any label can be recomputed from the record text alone |
| 多标签 | every category with at least one cue hit becomes a label; the primary is the strongest by cue hits, ties resolve by declared taxonomy order, runner-ups stay on the record with multi_label true — never collapsed |
| 未分类诚实 | a record no cue matches gets primary 未分类 and a stated reason; the batch carries an cls.unclassified finding naming the ids — an honest miss is reported, never padded into a guess |
| 批次汇总 | the result carries summary 的 per_category（主标签计数）、label_mentions（含次标签）、multi_label_ids 与 unclassified_ids；CLI 把同一张表渲染成 summary.md |
| 落地可回滚 | the landing engine produces an inventory with per-file hashes, an old→new plan, dedup/version verdicts and a journalled execution whose every move is reversible by hash-verified rollback — labels become directory changes, not advice |

Plus one reproducibility guarantee: neither engine writes wall-clock fields, so
re-running the same spec is byte-identical, and the input fingerprint
(spec_sha256) is recorded with the output.

## Data shapes

The spec declares the taxonomy and the records (both required):

```json
{
  "taxonomy": [
    {"category": "实验方法", "cues": ["方法", "we measured", "步骤"],
     "examples": ["We measured uptake at 25 C with six replicates."]},
    {"category": "研究结果", "cues": ["结果", "three-fold", "表明"]}
  ],
  "records": [
    {"id": "doc-002", "title": "实验记录",
     "text": "方法：we measured uptake at 25 C，每组六个重复。结果：重复性良好。"},
    "结果：three-fold 提升明显"
  ]
}
```

**spec.taxonomy** is a list of `{category, cues, examples}`. Cues are keywords
matched as case-insensitive substrings (CJK and latin alike); examples are
reference snippets matched verbatim — a paraphrase does not count. A taxonomy
entry that is not an object with a non-empty category is skipped and named
(cls.taxonomy_entry_skipped).

**spec.records** entries are objects with `id` (optional, auto-numbered
rec-NNN), `title` (optional) and `text`; a bare string is tolerated as a
record with no metadata — it is classified by its text, not refused. An entry
that is neither an object nor a string is skipped and named
(cls.record_skipped), never silently dropped.

Optional: `min_hits` (CLI --min-hits, default 1) raises the bar — a category
needs at least that many cue hits to become a label.

## Workflow

```bash
# P2 label pass: records + taxonomy -> labels, summary, findings
python scripts/classify_cli.py --spec examples/spec.json --out ./out

# P1/P3/P4/P5 landing pass: a real directory -> inventory, plan, dedup,
# version relations, journalled execution
python scripts/land_cli.py --spec land_spec.json --root ./batch --out ./out   # plan only
python scripts/land_cli.py --spec land_spec.json --root ./batch --out ./out --execute

python scripts/bench_classify.py   # 24 scenarios: one per property or rule, plus FP guards
```

The engines live in `scripts/classify.py` and `scripts/land.py` (importable:
run(spec) from the classify module, land_run(spec, root, out, execute_now=…)
from the land module); the CLIs add spec reading and output writing. Exit codes:

| exit | status | when |
|-|-|-|
| 0 | ok | run finished with no medium or high finding |
| 3 | review | medium findings (e.g. dup.near manual-confirm, inv.unreadable, plan.entry_not_found) — result usable, items need a human |
| 4 | blocked | high finding (exec.skipped_conflict, exec.mismatch) — nothing may ship half-organised |
| 5 | undetermined | refusal: unreadable spec, missing root, empty entries / empty taxonomy / no records — result.json still written |

2 is argparse usage (bad flags). A refusal is a result, not a crash: the
refusal path writes result.json and never echoes the output contract.

## The landing protocol: entries spec

The land CLI joins three things: the P1 inventory (computed from the real
directory), per-file metadata entries (the runner's P2 output: category from
classification plus author/year/title/doi/version extracted from the file or
marked 未报告), and organize options:

```json
{
  "case_id": "case-p52-1",
  "root": "./batch",
  "entries": [
    {"path": "a_published.pdf", "category": "研究结果", "author": "Zhang San",
     "year": 2023, "title": "Coating uptake", "doi": "10.1/xyz",
     "version": "published"},
    {"path": "b_preprint.pdf", "category": "研究结果", "author": "Zhang San",
     "year": 2022, "title": "Coating uptake preprint", "doi": "doi:10.1/XYZ",
     "version": "preprint"}
  ],
  "organize": {"naming_template": "author-year-title", "year_subdir": true,
               "max_name_len": 60, "dupes_dir": "duplicates"}
}
```

Metadata fields the file does not supply are left out or set to null — the
degradation chain uses what exists and names what is missing. Inventing an
author, year or DOI is the failure mode this topic calls out by name.

## Mechanical rule index

Every engine decision is a named, recomputable rule (severity drives the exit
code: any high → 4 blocked, any medium → 3 review, else 0 ok).

| rule | severity | step | fires when |
|-|-|-|-|
| `cls.empty_taxonomy` | high (exit 5) | P2 | taxonomy missing/empty/ unusable — never run against a guessed schema |
| `cls.no_records` | high (exit 5) | P2 | records missing, empty or all malformed |
| `cls.spec_unreadable` | high (exit 5) | P2 | spec file unreadable or not a JSON object |
| `cls.record_skipped` | low | P2 | a record entry that is neither object nor string, named with its index |
| `cls.taxonomy_entry_skipped` | low | P2 | a taxonomy entry without a usable category name |
| `cls.cue_collision` | medium | P2 | one cue declared in ≥2 categories; counts for each, overlap visible |
| `cls.unclassified` | low | P2 | records no cue matched, listed by id — honest misses |
| `inv.unreadable` | medium | P1 | a file cannot be read/stat-ed; stays in inventory, excluded from organising |
| `inv.zero_byte` | low | P1 | 0-byte file — damage candidate, excluded until inspected |
| `inv.pdf_encrypted` | medium | P1 | PDF carries an /Encrypt marker — no text layer, degrade to filename cues at low confidence |
| `plan.entry_not_found` | medium | P3 | entry names a file absent from the inventory |
| `plan.duplicate_entry` | medium | P3 | two entries name the same file; only the first plans it |
| `plan.uncovered_files` | low | P3 | usable inventory files with no entry — six-element check wants a stated reason |
| `name.collision_resolved` | low | P3 | two entries map to one target name; hash suffix, not overwrite |
| `name.degraded` | low | P3 | name fell below the full author-year-title template; missing fields on the record |
| `dup.exact` | low | P4 | identical sha256 — keep one (metadata completeness, then shorter path, then lexicographic), archive the rest |
| `dup.near` | medium | P4 | same DOI or same title+author+year with different bytes — manual confirm, both stay |
| `ver.relation` | low | P4 | preprint vs published distinguished from a declared version field or filename cues |
| `ver.ambiguous` | low | P4 | candidate duplicates but no version evidence; both stay until a human decides |
| `exec.source_missing` | medium | P5 | planned source gone and target does not carry its content |
| `exec.skipped_conflict` | high (exit 4) | P5 | target exists with different content — never overwritten |
| `exec.move_failed` | high (exit 4) | P5 | the filesystem refused the move |
| `exec.mismatch` | high (exit 4) | P5 | post-move hash ≠ inventory hash; the op is auto-rolled-back |
| `rollback.source_missing` | high | P5 | journalled target gone, original path does not carry its content |
| `rollback.failed` | high | P5 | a restore move failed on the filesystem |
| `rollback.mismatch` | high | P5 | a restored file's hash disagrees with the journal — inspect by hand |

## Output contract

classify_cli `--out` receives:

- `result.json` — `status`, `records[]` (each: `id`, `primary`, `confidence`,
  `multi_label`, `labels[]` with matched cues/examples and hit counts,
  `reason`, `cue_hits_total`), `summary` (per-category primary counts, label
  mentions, multi_label_ids, unclassified_ids), `findings[]`, the
  `taxonomy_declared` echo, and `spec_sha256`.
- `summary.md` — the per-category summary table for handover (written on
  status ok).

land_cli `--out` receives:

- `result.json` — `status`, `mode` (plan or resume), `inventory` (files with
  path/size/sha256/kind/usable, skipped, counts), `plan[]` (old→new rows with
  op, sha256, name basis, missing fields), `plan_coverage`,
  `duplicates`, `near_duplicates`, `version_relations`, `findings[]`,
  `severity_counts`; with --execute also `executed` (changed, already_done,
  journal_path) and `idempotent`.
- `plan.md` — the old→new plan as a handover table (written on ok/review).
- `manifest.json` — the executed plan (resume source for idempotent reruns).
- `journal.jsonl` — one line per executed move: seq, op, from, to, sha256,
  sha256_verified, why. `rollback.jsonl` records reversals.

A refusal run writes `result.json` with `status: undetermined` and a named
`refusal` — a refusal is a result, not a crash.

## Minimal worked example

Input: `examples/spec.json` (3 categories, 3 records — one clean, one spanning
实验方法 and 研究结果, one matching nothing). Verified by an actual CLI run on
this machine.

示意 output (abridged — an illustrative sketch of the shape, not a formal case
result):

```json
{"status": "ok",
 "records": [
  {"id": "doc-001", "primary": "研究结果", "confidence": 1.0, "multi_label": false,
   "labels": [{"category": "研究结果", "cue_hits": 2,
               "matched_cues": ["结果", "three-fold"], "matched_examples": []}],
   "reason": "top label by cue hits (结果, three-fold)"},
  {"id": "doc-002", "primary": "实验方法", "confidence": 0.6667, "multi_label": true,
   "labels": [
    {"category": "实验方法", "cue_hits": 2, "matched_cues": ["方法", "we measured"]},
    {"category": "研究结果", "cue_hits": 1, "matched_cues": ["结果"]}],
   "reason": "top label by cue hits (方法, we measured); runner-up 研究结果 also matched"},
  {"id": "doc-003", "primary": "未分类", "confidence": 0.0, "multi_label": false,
   "reason": "no declared cue or example appears in the record text"}],
 "summary": {"per_category": {"实验方法": 1, "研究结果": 1, "数据集": 0, "未分类": 1},
             "multi_label_ids": ["doc-002"], "unclassified_ids": ["doc-003"]}}
```

`summary.md` renders the same counts as a table (primary count and label
mentions per category, including the 未分类 row).

Landing worked example (verified by an actual land_run call): a batch of
a_published.pdf + b_preprint.pdf (same DOI, different bytes, declared
versions), dup.txt + sub/dup.txt (identical bytes), note.txt (full metadata)
plans five rows —

| old | new | name basis |
|-|-|-|
| a_published.pdf | 研究结果/2023/Zhang-2023-Coating-uptake.pdf | author-year-title |
| b_preprint.pdf | 研究结果/2022/Zhang-2022-Coating-uptake-preprint.pdf | author-year-title |
| note.txt | 实验方法/2024/Li-Si-2024-Protocol-draft.txt | author-year-title |
| dup.txt | 数据集/uncategorized-dup.txt | uncategorized prefix（元数据缺失降级） |
| sub/dup.txt | duplicates/dup.txt | archive-duplicate（sha256 与 dup.txt 相同） |

— with findings dup.exact, dup.near（doi:10.1/xyz，decision manual_confirm）、
ver.relation（formal a_published.pdf / preprint b_preprint.pdf，依据声明的
version 字段）与 name.degraded；execution journals five moves, a rerun reports
already_done 5 / changed 0 / idempotent true, and rollback restores all five
original paths with matching hashes.

## Routing

| 任务信号 | 入口 | 说明 |
|-|-|-|
| 一批文件/记录 + 声明好的类别体系，要求打标签、可审计、可汇总 | classify_cli（P2） | 纯标签层：records + taxonomy → labels + summary |
| 标签要落成真实目录变更（改名/移动/去重/版本） | land_cli（P1/P3/P4/P5） | entries = 分类结果 + 元数据；先 plan 后 execute |
| 只需要盘点哈希与损坏/加密/权限清单，暂不整理 | land_cli（plan-only） | result.json 的 inventory 即交接清单 |
| 需要追踪库级版本链与借阅交接 | 用 `p53-library-mgmt` | 本包是单批次整理，不是长期库管理 |
| 需要在文件内定位回答问题的段落 | 用 `p54-file-search` | 本包不抽取答案段落 |

## 运行时入口与输出契约（Harbor，六步）

1. **读输入**：运行时原始输入固定为 `/input/case.json` 与 `task.md`。先读
   case.json 取 `case_id`、任务说明与 `output_contract`；材料是**实际文件与
   目录**——按 task.md 指向的路径盘点输入文件、目录和权限，实际打开文件抽取
   文本（PDF 用 pdf-text-tool，扫描件走 OCR），不按文件名或领域标签猜内容、
   不编造元数据。
2. **建工作区**：中间产物写 `/app/work`（盘点清单、抽取文本、分类结果、整理
   计划、操作日志）；尽早写出诚实的部分结果，再增量改进。
3. **跑引擎**：P2 标签层 `classify_cli.py --spec ... --out ...`；落地层把每
   个文件的 category 与元数据写进 entries，跑 `land_cli.py`（先 plan-only 检
   查 plan.md，再 `--execute`）；任何一步被拒（exit 5）就先修输入再重跑。
4. **回填契约**：最终结果写 `/app/output/result.json`——case_id 原样回填，
   output_contract 的每个原始字段逐字段拷贝（不改名不遗漏；不可推导的置
   null 并在 limits 写明）。两个 CLI 都实现了该回填；拒绝路径不回填契约，
   只写最小 result.json。
5. **诚实状态**：status 映射——全批处理完且零未决 → done；有跳过/冲突但主
   体完成 → partial（写明哪些未完成）；拒绝或灾难性失败 → failed（写原因）。
   sources 记录每个标签回指的文件与命中片段，uncertainty 记录低置信/无文本
   层/歧义归属，limits 记录本次整理的边界；可渲染的交付物（如 plan.md）随结
   果一并写出供查验。
6. **自查退出**：改任何脚本后重跑 `scripts/bench_classify.py`（24 场景必须
   全过）；按 Workflow 一节的退出码表检查本次运行（含 undetermined → 5）。

result.json 的落地映射（三段输出结构对齐 rubric 原词）：

| rubric 输出段 | result.json 键 | 完成标准 |
|-|-|-|
| 资料结果 | `library_result`（清单、标签、目录层级、新名、元数据、版本关系） | 与输入文件和题目规则一一对应 |
| 操作证据 | `operation_evidence`（前后哈希、来源、权限、变更日志、manifest 与 journal） | 他人可复跑并核对 |
| 失败与恢复 | `failure_recovery`（跳过、冲突、无权限、重复、恢复记录） | 不把未完成写成完成 |

- 引擎产物的对应关系：inventory → library_result 清单与 operation_evidence
  哈希；plan → library_result 目录层级与新名；duplicates / version_relations
  → library_result 去重结论与版本关系；journal / rollback → operation_evidence
  变更日志与 failure_recovery 恢复记录；findings → failure_recovery（skipped、
  conflicts、denied、duplicates 各有落点）。
- 引擎已实现该契约：spec 顶层提供的 output_contract 同名字段值会被 CLI 原样
  拷入 result.json（大体积输入字段除外）；推导不出的字段填 null 并在 limits
  里说明。把 library_result / operation_evidence / failure_recovery 的字段值
  放进 spec 顶层，即直通最终 result.json。

## 自动命名模板与降级规则（P3 机械实现）

模板默认 author-year-title；可用 organize.naming_template 切到 doi 或 keep。
降级链是引擎代码，不是建议：

| 情况 | 引擎行为 |
|-|-|
| 特殊字符 | slug 化：文件系统禁字符剔除、空白转单连字符、重复连字符折叠；CJK 与多语言保留原文，不做音译或翻译 |
| 超长标题 | 超过 max_name_len（默认 60）截断并追加内容短哈希后缀，保证唯一 |
| 作者/年份缺失 | 降级链：author-year-title → doi → title → 原文件名，缺失字段写入 missing_fields 并标 metadata_incomplete |
| 全部缺失 | 保留原文件名加 uncategorized- 前缀，绝不编造字段 |
| 目标名冲突 | 第二个文件追加内容哈希后缀（name.collision_resolved），永不覆盖 |
| 目录层级 | slug(类别)/年份（有年份才建）/规范名；类别缺失归 未分类/ |

**元数据补齐**：标题、作者、年份、期刊、DOI 只从文件内容（首页、文本层、内
嵌元数据）抽取；取不到的字段如实标「未报告」——凭空补作者、年份或 DOI 是本
题点名的失败模式，降级链保证缺失也能命名。

## 去重与版本区分（P4 机械实现）

| 关系 | 判定（引擎） | 处置（引擎） |
|-|-|-|
| 精确重复 | sha256 相同 | 保留元数据最全（并列取更短路径、再取字典序）的一份，其余移入 duplicates/，**永不删除** |
| 近似重复 | 归一化 DOI 相同，或 标题+作者+年份 相同而字节不同 | decision=manual_confirm，两份都原地保留，写明判定依据 |
| 预印本 vs 正式版 | 声明的 version/pubstate 字段，或文件名线索（preprint/arxiv/submitted… 对 published/final/accepted…） | 正式版进主目录，预印本保留并写 version_relations（basis 声明来源） |
| 版本不明 | 近似重复但双方都无版本证据 | ver.ambiguous：两份都保留，等人工判定 |

## 执行与回滚（P5 机械实现）

- **计划先行**：任何移动只按 plan 的 old→new 行执行；plan-only 模式不碰文件。
- **每步留痕**：journal.jsonl 每行记录 seq、op、from、to、两端 sha256 与理由；
  移动后立即复核目标哈希，不一致自动撤回该步（exec.mismatch）。
- **绝不覆盖**：目标已存在且内容不同 → exec.skipped_conflict（exit 4）；
  内容相同 → 记 already，不重写。
- **幂等续跑**：执行前把 plan 存为 manifest.json；重跑命中 manifest，逐行比
  对"源已不在、目标哈希吻合"→ already_done 计数、changed=0、idempotent=true。
  新批次用 --fresh 重盘。
- **可回滚**：rollback 按逆序撤move，恢复后逐一核对哈希（rollback.jsonl 留
  痕）；任何不一致都点名（rollback.mismatch）。

## 六类要素逐一交代

输入批次的全部文件都要出现在结果里，六类要素各有引擎落点：

| 要素 | 引擎落点 |
|-|-|
| 文件类型 | P1 inventory 的 kind（按扩展名分类）与 inv.pdf_encrypted 标记 |
| 元数据字段 | entries 元数据 + name.degraded 的 missing_fields（缺失如实标注） |
| 目录层级 | plan 的 new 路径（类别/年份/规范名） |
| 重复文件 | dup.exact / dup.near 结论与 duplicates/ 目录 |
| 版本差异 | version_relations 与 ver.ambiguous |
| 权限与来源 | inv.unreadable / inv.zero_byte 与 journal 的来源哈希（operation_evidence） |

## 文件形态与异常处置

| 形态 / 故障 | 引擎处置 |
|-|-|
| 损坏文件（0 字节） | inv.zero_byte：留在清单、排除整理、标 damage candidate |
| 加密 PDF | inv.pdf_encrypted：识别 /Encrypt 标记，无文本层 → 按文件名降级分类、标低置信 |
| 不可读/无权限 | inv.unreadable：点名并继续整批，不中断 |
| 扫描件无文本层 | OCR 失败 → 标「未分类-无文本」，不硬塞类别 |
| 中文乱码 | 先编码探测；仍乱码 → 按哈希去重、记 skipped，不猜内容 |
| 同名不同版本 | sha256 + 版本字段区分，绝不覆盖；正式版进主目录，其余归档 |
| 目标名冲突 | name.collision_resolved：哈希后缀，不覆盖 |
| 重复运行 | manifest 比对后零改动（idempotent=true）；新文件 --fresh 增量重盘 |
| 整理中断 | 按 manifest 与 journal 续跑；rollback 可整批逆向恢复并核对哈希 |
| entries 指向不存在的文件 | plan.entry_not_found：点名，不给该文件出计划 |
| 同一文件两条 entries | plan.duplicate_entry：只按第一条出计划，不移动两次 |
| spec 不可读 / 空词表 / 无记录 | exit 5 拒绝并写出 result.json（status undetermined），不崩溃 |

## 使用增益与对照方法

- **公平对照**：相同输入和目录快照下，基础 Agent 输出与本 Skill 的整理结果
  对比，按「归属正确、标签可核对、命名合规、去重正确、操作可回滚」五项逐文
  件计数；平台白板是对照基准，不是参赛者答案。
- **增益证据形式**：`scripts/bench_classify.py` 24 场景（每场景一个性质、一
  条机械规则或一个 FP guard），同输入重跑字节级一致；标签置信度可由记录与词
  表独立重算；land 场景在临时目录实跑 plan/execute/rollback 全链。

## Verification

```bash
python scripts/bench_classify.py   # 24 scenarios: one per property or rule, plus FP guards
```

All 24 pass on this machine. The FP guards pin the behaviour that matters: a
cue collision still classifies multi-label correctly; a rerun is byte-identical;
min_cue_hits honestly demotes weak records to 未分类; the CLI writes summary.md
on success; an empty taxonomy refuses with exit 5 while still writing
result.json; inventory hashes are stable and every anomaly file is named;
the naming plan is deterministic with hash-suffix collision resolution; exact
duplicates are archived with zero deletions; near duplicates wait for manual
confirm while version relations are recorded; execution journals both-end
hashes and rollback restores the tree byte-identically; a rerun is zero-ops;
a differing target is never overwritten.

## Limits

- **Lexical, not semantic.** Classification is cue matching against the declared
  taxonomy; a paraphrase that shares no cue is honestly 未分类. Improving recall
  means declaring more cues, not loosening the match.
- **Confidence is a share, not a probability.** It says how concentrated the cue
  evidence is; it is recomputable from the record text and the declared taxonomy.
- **Examples are matched verbatim.** A snippet counts only when it appears
  character-for-character in the record.
- **Ties resolve by declared order.** Two categories with equal cue hits give
  the primary to whichever the spec declares first — deterministic, and the
  runner-up stays on the record.
- **One record, one text field.** PDFs must be extracted to text before
  classification; this skill is the labelling half, not the extraction half.
- **The land engine moves, never edits.** File contents are untouched (hashes
  prove it); metadata extraction from PDFs is the runner's job and enters the
  engine only through entries.
- **Near duplicates stay put.** Only byte-identical copies are auto-archived;
  DOI/title collisions wait for a human, because a false dedup is worse than a
  missed one.

## Failure handling

| symptom | what to do |
|-|-|
| `cls.empty_taxonomy`（exit 5） | declare the categories first; the batch refuses to invent a schema |
| `cls.no_records`（exit 5） | the case supplied nothing classifiable; fix the records key |
| `land.no_entries`（exit 5） | entries 是整理计划的输入：每文件一条（路径 + 元数据 + 类别），缺失即拒绝 |
| `land.root_missing`（exit 5） | root 必须是实际存在的目录；路径写错或目录未建都会被拒 |
| `land.spec_unreadable`（exit 5） | spec 不可读或缺失——拒收并写 result.json，绝不 traceback |
| `cls.record_skipped` | fix the entry shape (object with text, or a bare string); the rest of the batch still ran |
| `cls.cue_collision` | two categories share a cue — split or rename it, or accept the documented multi-label behaviour |
| many `cls.unclassified` | the cues do not cover the batch's vocabulary; extend the declared cues — never lower the evidence bar silently |
| `inv.unreadable` | 先修权限再重跑盘点；取不到就保持 excluded，不硬塞 |
| `inv.pdf_encrypted` | 用 OCR/解密工具取文本层；取不到就按文件名降级并标低置信，不硬塞 |
| `plan.entry_not_found` | entries 与实际树不同步：重跑 P1 盘点并更新 entries，再出计划 |
| `exec.skipped_conflict`（exit 4） | 目标已有不同内容：先人工处置该文件（改名/移走/确认保留），或修 plan 后 --fresh 重盘；绝不覆盖 |
| `exec.mismatch` | 移动后哈希不符：引擎已自动撤回该步；检查磁盘/杀毒软件干扰后重跑 |
| 需要撤销整批 | 用 journal 调 rollback（逆序恢复并核对哈希）；确认无误后再整理 |

## Requirements

Python 3.9+ (3.14 verified); standard library only — no packages to install.

## 创新增益

本 Skill 相比通用 Agent 的新增能力（每条附能力边界与增益证据形式）：

1. **可复算的标签置信度**：confidence 是该标签 cue 命中占全部命中的份额，任何拿着
   记录文本与词表的人都能重算；每个标签留痕 matched_cues 与 matched_examples。
   *边界*：词汇匹配不是语义理解，改写无命中词的文档会诚实落入未分类。
   *证据形式*：bench 的 matched_cues_explainable 与逐场景命中核对。
2. **多标签不折叠 + 碰撞显式化**：跨类文档保留 primary + 次标签（multi_label），
   同一 cue 声明在两类时报告碰撞而不是悄悄双算——通用 Agent 常把两者都压成一个
   标签或静默覆盖。
   *证据形式*：bench 的 multi_label_recorded 与 cue_collision_finding。
3. **诚实未分类**：无命中 → 未分类 + 理由 + 批次级 id 清单；证据不足不硬塞。
   *证据形式*：bench 的 unclassified_honest 与 min_cue_hits_threshold。
4. **五步落地协议全链机械化（P1/P3/P4/P5 引擎实现）**：盘点即哈希（损坏/加密/
   无权限文件点名不丢弃）、命名即降级链（禁字符/截断加哈希/缺失字段降级、冲突
   加后缀永不覆盖）、去重即三档判定（精确哈希归档不删、近似双证留人工、版本
   关系落记录）、执行即双端哈希台账（manifest 续跑零改动、rollback 逆向核对、
   不同内容目标绝不覆盖）。
   *边界*：引擎移动文件但从不编辑内容；元数据抽取是 runner 的前置职责，经
   entries 进入引擎；近似重复不自动合并。
   *证据形式*：bench 的 10 个 land 场景（inventory/flags/degradation/collision/
   dup_exact/dup_near_version/journal_rollback/idempotent/conflict/cli）。
5. **字节级幂等批次与汇总**：两个引擎都不写时钟字段，同输入重跑逐字节一致；
   批次汇总表（主标签计数 + 标签提及 + 多标签/未分类 id）直接可交接；执行层
   幂等由 manifest 保证（already_done 计数、changed=0）。
   *证据形式*：bench 的 rerun_identical 与 land_exec_idempotent_noop。

## 生态贡献

- **使用说明**：本文件含完整调用步骤（Workflow）、输入输出解释（Output
  contract）、关键方法（cue 匹配、置信度、五步协议）、适用场景与限制
  （Limits/Routing）、失败处理（Failure handling）和自查方法（bench）。
- **依赖与配置**：Python 3.9+（3.14 验证）纯标准库，无第三方依赖、无安装步骤；
  词表、min_hits、命名模板（naming_template/max_name_len/year_subdir/dupes_dir）
  全部经 spec 配置，无需改码。
- **示例（标注为示例）**：`examples/spec.json` 是最小输入；本文「Minimal worked
  example」与 land 工作例是示意输出（实跑核对过的节略形状）——均为示例，不冒
  充正式案例结果。
- **规则词表与模板可复用**：taxonomy 的 cues/examples、命名降级链、去重阈值
  （sha256 / DOI / 标题+作者+年份）与版本线索词表（preprint/formal cues）都是
  数据不是代码，他人可直接套用到自己的资料库。
- **题集与金标准**：bench 的 24 个场景即回归题集（每场景钉住一条规则或一个
  FP guard），report_classify.json 是可对比的运行记录。
- **适用范围**：文献/资料的分类、标签、命名、去重与批量整理落地；不负责单篇
  精读、全文翻译、写作润色，也不负责文献检索发现。
- **限制**：见 Limits 一节（词汇非语义、examples 逐字匹配、PDF 抽取是前置步
  骤、引擎只移动不编辑、近似重复留人工）。
- **维护**：`scripts/bench_classify.py` 为回归门，改动后必须 24/24 全过；词表
  与命名模板变更只需改 spec 配置并重跑 bench 确认零回归；规则 id 变更须同步
  本文档机械规则索引表。

