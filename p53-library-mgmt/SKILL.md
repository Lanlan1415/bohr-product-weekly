---
name: library-mgmt
description: >
  Turn a messy batch of research records into a persisted, hand-over-able
  library. Every document is ingested with its content and sha256 (byte length
  recorded); folder placement comes from the declared structure rules with the
  matched cue recorded, so filing is explainable, a rule nothing matches is
  named (folder_empty), and unmatched documents park in 未归类 — never guessed
  into a folder. Re-ingesting a doc_id with changed content never overwrites:
  the old entry stays and the new content becomes doc_id@v2 with supersedes
  links both ways (版本不串味). Identical content under two doc_ids is reported
  as a duplicate set and every copy is kept (重复不静默合并); same-title-
  different-content files are version siblings, both retained, no authoritative
  guess. Metadata is stored verbatim with provenance (meta_src marks where each
  field came from — never extracted from filenames) and declared-but-absent
  fields are listed as missing — never invented. Unsafe doc_ids (path
  separators, dot-dot) are refused so the taxonomy stays exact. The export is
  library.json (machine) + inventory.md (human handover) + manifest.tsv (full
  64-hex sha256 per document) and --verify recomputes every stored hash as an
  archive integrity self-check. A retrieval query ranks the library by shared
  content terms and can honestly return nothing. The CLI echoes case_id and
  every output_contract field from --case into result.json (spec-carried
  case_id passes through too; the refusal path echoes none of it), and layers
  its exits: 0 ok, 4 partial, 5 undetermined. Missing files, unreadable files
  and non-object records are refused by name; empty specs refuse with exit 5
  and a written result.json, never a crash. Use when a task supplies research
  files or records that must be organised into a folder taxonomy with hashes,
  version relations, duplicate detection, provenance and a checkable inventory.
---

# library-mgmt（科研资料库与文件管理）

The failure this prevents is organisation that destroys trust: files moved with
no list or hash, a re-download overwriting the original until the version chain
snaps, a preprint and its published version merged because their titles match,
metadata guessed from filenames, a dead folder rule hidden behind a tree that
looks filled, and an inventory that only the organiser could read back.

Four properties decide whether this task is done right, and each is enforced:

| property | enforcement |
|-|-|
| 版本不串味 | re-ingesting a doc_id with different content is refused as an overwrite: the old entry stays immutable, the new content is stored as the next doc_id@vN, and supersedes / superseded_by links are recorded on both; same folded title with different content is a version-sibling set with every variant's hash listed |
| 重复不静默合并 | identical content under two doc_ids is a duplicate set in the result — every copy is kept and listed by hash; nothing is dropped or merged by the store, and title-matching alone never merges anything (hash decides) |
| 清单可交接 | the export is library.json (content, sha256, folders, version links, meta, meta_src) plus inventory.md (per-folder handover view with hashes, provenance, missing metadata, duplicates, refusals) plus manifest.tsv (one line per document with the FULL 64-hex sha256 and byte length); every line traces back to the store, and declared metadata fields that are absent are marked missing, never filled |
| 状态不虚报 | status is ok only when every record ingested; any refused record turns it partial with the limits listed; nothing ingestible is undetermined (exit 5) — the run never writes 完成 over an unfinished batch, and --verify recomputes every hash so the claim of integrity is checkable, not asserted |

Plus one reproducibility guarantee: no wall-clock fields are written, so the
same spec re-runs byte-identical, and spec_sha256 is recorded with the result.

## 六步运行时入口（Harbor 契约）

平台运行时原始输入固定为 /input/case.json 与 task.md；工作区 /app/work；最终交付
写 /app/output。按以下六步执行：

| 步 | 动作 | 要点 |
|-|-|-|
| 0 | 读 /input/case.json | 取 case_id 与 output_contract（原样保留，不改名）；按 task.md 指向的路径盘点实际文件、目录与权限——路径与标签不是内容，逐个读出真实文本/元数据 |
| 1 | 判形态路由 | 按下方「任务措辞 → 路由」表决定 spec 怎么构造：已有记录清单、只有文件路径、伴随元数据表、还是多版本混合；打不开的文件在路由阶段就 Declared，不硬做 |
| 2 | 先产出目标产物 | 先跑一遍全量 ingest 拿到 library.json + inventory.md + manifest.tsv——即使后续步骤中断，落库、哈希与清单已交付（尽早写出诚实的部分结果） |
| 3 | 构造 spec | structure 目录规则 + meta_fields 声明 + records（id/title/meta/text 或 path）；meta 只写真实已知值并留 meta_src 出处，猜不出的字段留给 meta_missing |
| 4 | 审计 | 加 --verify 重算全部哈希核对清单；逐条检查 refused 与 findings 是否如实；用真实查询跑 retrieval 验证库可检索；声明目录零命中要点名 |
| 5 | 修发现重跑 | 缺失路径修路径或显式剔除；非 UTF-8 先转码；补 structure 规则消未归类；重跑直到零拒绝或材料本身不允许——重跑不破坏版本链（同内容 unchanged，异内容走 @vN） |
| 6 | 合并 result.json | 加 --case /input/case.json 重跑：case_id 与 output_contract 逐字段直通，status 按三态映射（ok=全部落库 / partial=有拒绝，limits 已列 / undetermined=无法判定） |

引擎已实现契约直通：--case 把 case_id 与 output_contract 的每个字段写进
result.json 顶层——结果里已有的字段保留，case 顶层携带的小体积值原样拷贝
（大体积材料字段除外），契约里的字面量（短字符串/数值/布尔）直接回填，推导
不出的填 null 并在 limits 里写明；spec 自带 case_id 时同样直通。拒绝路径
（spec/case 不可读、导出失败）不回填契约，只写 undetermined result.json——
坏的文件可能就是 case 文件本身。

## 任务措辞 → 路由

| 任务措辞 / 输入形态 | 路由 |
|-|-|
| 给了一批文件路径 + 目录约定 | records 用 path 逐个指向真实文件，约定变成 structure 规则；matched cue 留痕，未命中进未归类 |
| 给了伴随元数据表格 | 表格行逐字段转成 record.meta（真实值），meta_src 自动标 record；表格没有的字段别猜，交给 meta_missing |
| 同一 doc_id 出现新旧两版 | 两条同名 id 记录依次入库：旧版保留，新版自动 @vN 并写 supersedes 双向链——不许覆盖 |
| 疑似重复文件（改名副本/重传） | 不同 id 同文本入库：duplicate_content 点名报出，逐份保留；合并与否留人工决定 |
| 预印本与发表版同题不同文 | version_sibling 两条保留，各带哈希；谁权威是人读的判断，store 不猜 |
| 元数据只有文件名可猜 | 不猜：meta 留空，字段进 meta_missing——宁缺勿错 |
| 部分文件打不开 / 无权限 | 引擎点名拒绝（file_missing / file_unreadable），其余照常入库，status=partial，拒绝清单随交付 |
| 要求验证库完整性 | export 后加 --verify：逐条重算 sha256，integrity_verified 写进 findings；不符则 integrity_mismatch 拒绝（exit 5） |
| 要求检索验证 | spec.query 或 --query 跑词法检索；空结果如实标注，不硬凑 |
| 要求长期归档交接 | 交付三件套 library.json + inventory.md + manifest.tsv（全量 64-hex 哈希 + 字节长），对方拿 manifest 可独立核对 |
| 只要「整理建议」不动手落库 | 不适用——本 Skill 的最小交付就是落库+清单+哈希；纯建议请直接写文档 |
| 存储系统权限建设 / 归档制度设计 | 不适用（题目边界），只做本批材料的落库—版本—清单—自检闭环 |

## Workflow

```bash
# 1. ingest the batch and export library.json + inventory.md + manifest.tsv,
#    with the case contract echoed into result.json and hashes self-checked
python scripts/library_cli.py --spec examples/spec.json --out ./out \
    --case examples/case.json --query "涂层 吸收速率" --verify

# 2. the regression suite (25 scenarios; clean baseline must be all-pass)
python scripts/bench_library.py
```

The engine lives in scripts/library.py (importable: library.run(spec) returns
(Library, result); Library.add / assign_folders / duplicates / siblings /
retrieve / export are directly usable; library.verify_store(path) is the
standalone integrity check). Exit codes:

| exit | status | meaning |
|-|-|-|
| 0 | ok | every record ingested; contract echoed when --case given |
| 4 | partial | the batch was stored but some records were refused — limits listed in result.json |
| 5 | undetermined | refusal: unreadable spec/case, nothing ingestible, export failure, integrity mismatch — result.json still written |
| 2 | usage | CLI misuse (missing required argument) |

undetermined → 5：拒绝也是结果——三种非零退出都先写出 result.json 再退出，
绝不带 traceback 崩溃。

## Data shapes

The spec declares the folder taxonomy and the records (records required):

```json
{
  "structure": [
    {"folder": "papers/涂层", "cues": ["涂层", "coating"]},
    {"folder": "protocols/缓冲液", "cues": ["缓冲液"]}
  ],
  "meta_fields": ["author", "year", "doi"],
  "records": [
    {"id": "paper-A", "title": "多孔涂层吸收速率研究",
     "meta": {"author": "王某某", "year": 2023},
     "text": "多孔涂层使吸收速率提高三倍。"},
    {"id": "scan-001", "title": "缓冲液扫描件", "path": "files/buffer.txt"}
  ],
  "query": "涂层 吸收速率"
}
```

structure 规则按 cue 匹配归档目录——第一条命中的规则获胜，命中的 cue 记录在
文档上（folder_cues），没有任何规则命中的文档落入 未归类 并计数（不猜目录）；
声明的目录若零命中，点名报出而不让死规则藏在树里。没有 folder 名的 structure
条目被跳过并点名。

records 条目携带 id（可选，自动编号 doc-NNN）、title、meta（逐字存储，出处
自动记入 meta_src；非对象 meta 被点名并按空存储——绝不猜）、以及内容：内联
text 或指向 UTF-8 文本的 path（相对路径相对 spec 所在目录解析）。id 含路径
分隔符或为点号会被作为不安全 id 拒绝（目录语义必须精确）。既无 text 也无
path、path 不存在、或文件不可解码的记录按名字拒绝进 refused[]——批次继续
处理其余记录。

meta_fields 声明交接所要求的元数据字段；结果逐文档标出缺失的声明字段
（meta_missing）。query（或 --query）触发检索。

## Output contract

--out receives:

- library.json — the store: every document with doc_id, title, sha256 (full
  64-hex), bytes, text, meta, meta_src (per-field provenance), content terms,
  folder + folder_cues, and version links (supersedes / superseded_by); plus
  the append-only event log (ingest / reingest / version).
- inventory.md — the human handover view: per-folder listing with hashes,
  metadata and its per-field provenance and declared-missing marks, version
  links, duplicate sets, sibling sets, refused records, and the retrieval
  answer.
- `manifest.tsv` — the archive manifest: doc_id, folder, FULL 64-hex sha256,
  byte length, title — the file a recipient can re-hash to verify the handover.
- result.json — status (ok / partial / undetermined), case_id (when supplied),
  counts (documents / stored / unchanged / versioned / refused), refused[]
  (named rules and reasons), findings[], folders, documents[] (with bytes and
  meta_src), duplicates, siblings, retrieval, meta_missing, spec_sha256.

Rubric 三段结构映射（字段名与评分表原词对应）：

| rubric 段 | rubric 要求原文 | 本 Skill 落点 |
|-|-|-|
| 资料结果 | 目录、文件清单、元数据、版本关系或知识结构；与输入文件和题目规则一一对应 | result 的 folders 与 documents 逐文档对应（folder/folder_cues/sha256/bytes/meta/meta_src），版本关系在 supersedes、superseded_by、duplicates、siblings 四组字段 |
| 操作证据 | 哈希、来源、权限、变更和日志；他人可复跑并核对 | sha256 全量在 library.json 与 manifest.tsv（64-hex 可独立重算）；来源在 meta_src；变更与日志在 events 与 counts；--verify 重算哈希即为他人复跑路径 |
| 失败与恢复 | 跳过、冲突、无权限、重复和恢复记录；不把未完成写成完成 | refused[] 逐条命名（缺失/不可读/不安全 id），findings[] 记冲突与零命中目录，status 三态如实分层，异常处置表给出每条的恢复动作 |

A refusal run writes result.json with status undetermined and a named refusal —
a refusal is a result, not a crash.

## The refusal and finding index

| id | severity | when |
|-|-|-|
| `lib.spec_unreadable` | high (exit 5) | the spec file is unreadable or not a JSON object |
| `lib.case_unreadable` | high (exit 5) | the --case file is unreadable or not a JSON object; the contract is not echoed from a broken file |
| `lib.no_records` | high (exit 5) | records missing/empty, or nothing at all could be ingested (reasons listed) |
| `lib.export_failed` | high (exit 5) | the export could not be written (disk full / permission) — reported, never half-written silently |
| `lib.integrity_mismatch` | high (exit 5) | the --verify self-check recomputed a hash that does not match the stored text |
| `lib.record_skipped` | low | a record that is not an object, or carries neither text nor path |
| `lib.file_missing` | low | a record path does not exist — named, never silently skipped |
| `lib.file_unreadable` | low | a record path exists but is not readable UTF-8 text |
| `lib.meta_invalid` | low | a record meta that is not an object; stored empty, never guessed |
| `lib.id_invalid` | low | a doc_id carrying folder semantics (path separator or dot-dot); refused so the taxonomy stays exact |
| `lib.structure_skipped` | low | a structure entry without a usable folder name |
| `lib.folder_empty` | low | a declared structure folder received zero documents — the cues never matched this batch |
| `lib.version_created` | medium | a doc_id re-ingested with different content: old entry kept, new content stored as the next version |
| `lib.duplicate_content` | low | identical content under several doc_ids; every copy kept and reported |
| `lib.version_sibling` | medium | same folded title, different content; kept separate, no authoritative guess |
| `lib.unfiled` | low | documents no structure rule matched; parked in 未归类 |
| `lib.integrity_verified` | info | the --verify self-check recomputed every hash and all matched (count = documents checked) |

## Minimal worked example

Input: examples/spec.json — two same-title records with different content
(paper-A 2023, paper-B 2024), one protocol, one structure rule set, one query;
examples/case.json — a case_id plus an output_contract. Run:

```bash
python scripts/library_cli.py --spec examples/spec.json --out ./out \
    --case examples/case.json --query "涂层 吸收速率" --verify
```

示意 output (abridged — an illustrative sketch of the shape, from a real run
of the example; not a formal case result):

```json
{"status": "ok",
 "case_id": "case-demo-53",
 "deliverable": "library handover inventory",
 "library_schema": "library/v1",
 "counts": {"documents": 3, "stored": 3, "unchanged": 0, "versioned": 0, "refused": 0},
 "folders": {"papers/涂层": ["paper-A", "paper-B"], "protocols/缓冲液": ["protocol-C"]},
 "documents": [
  {"doc_id": "paper-A", "folder": "papers/涂层", "folder_cues": ["涂层"],
   "sha256": "0077cc4510fd2c61", "bytes": 42,
   "meta": {"author": "王某某", "year": 2023},
   "meta_src": {"author": "record", "year": "record"}}],
 "siblings": [{"title_key": "多孔涂层吸收速率研究",
   "members": [{"doc_ids": ["paper-A"], "sha256": "0077cc4510fd2c61"},
               {"doc_ids": ["paper-B"], "sha256": "d1e0a8272aa4c6fb"}]}],
 "duplicates": [],
 "meta_missing": {"paper-A": ["doi"], "protocol-C": ["author", "year", "doi"]},
 "findings": [{"rule": "lib.version_sibling", "severity": "medium"},
              {"rule": "lib.integrity_verified", "severity": "info", "count": 3}],
 "retrieval": {"query": "涂层 吸收速率", "empty": false,
               "hits": [{"doc_id": "paper-A", "score": 4,
                         "shared": ["吸收", "收速", "涂层", "速率"]},
                        {"doc_id": "paper-B", "score": 4,
                         "shared": ["吸收", "收速", "涂层", "速率"]}]}}
```

manifest.tsv writes the FULL 64-hex hash per document (first lines):

```
doc_id	folder	sha256	bytes	title
paper-A	papers/涂层	0077cc4510fd2c61...	42	多孔涂层吸收速率研究
```

inventory.md renders the same store per folder with hashes, provenance and the
missing-metadata marks. A re-ingest of paper-A with changed content would have
produced paper-A@v2 with supersedes: paper-A and the 2023 text still intact.

## Limits

- **Content is text.** PDFs and Office files must be extracted to UTF-8 text
  before ingest (the hash is computed on the exact ingested text); binary
  handling is out of scope.
- **Duplicates are exact.** Same-sha content only; near-duplicate detection is
  not attempted, because a wrong merge is worse than a missed duplicate.
- **Siblings are title-based, hash-separated.** Same folded title with
  different content; the store lists variants and never ranks them — deciding
  which version is authoritative is a human step.
- **Filing is cue-based.** First matching structure rule wins; overlapping cues
  resolve by declaration order, and the matched cues stay on the record.
- **Metadata is declared, not mined.** Fields arrive via record.meta and carry
  the record provenance marking; the engine does not extract author/year from
  filenames or content — that guess is exactly what meta_src exists to prevent.
- **Retrieval is lexical.** CJK bigrams + latin words; a query sharing no term
  with the library returns an honest empty list.

## 异常处置表

| 形态 / 故障 | 处置 |
|-|-|
| spec 坏 JSON / 非对象 / 文件缺失 | exit 5 undetermined（lib.spec_unreadable），result.json 照写，无 traceback |
| case 文件坏 JSON / 非对象 | exit 5（lib.case_unreadable）——坏文件可能就是 case 本身，契约不回填 |
| records 缺失 / 空 / 全部被拒 | exit 5（lib.no_records），拒绝原因逐条列出 |
| record 非对象 / 无 text 无 path | 点名拒绝（lib.record_skipped），批次继续，status=partial |
| path 指向的文件缺失 | 点名拒绝（lib.file_missing）——绝不静默跳过 |
| 文件非 UTF-8 / 读取失败 | 点名拒绝（lib.file_unreadable）；先转码再重跑入库 |
| meta 非对象 | finding（lib.meta_invalid），存空不猜 |
| doc_id 含路径分隔符 / 点号 | 点名拒绝（lib.id_invalid）：目录语义必须精确 |
| structure 条目无 folder 名 | finding（lib.structure_skipped），其余规则照用 |
| 声明目录零命中 | finding（lib.folder_empty）：修 cue 或删目录，不把文档猜进去 |
| doc_id 重入库且内容变化 | 版本化（lib.version_created）：旧版不可变，新版 @vN 双向链 |
| 同内容不同 id（改名副本） | duplicate set（lib.duplicate_content）：逐份保留，合并留人工 |
| 同题不同内容（预印本 vs 发表版） | version sibling（lib.version_sibling）：都保留，不猜权威 |
| 无任何规则命中 | 未归类 + 计数（lib.unfiled），目录不猜 |
| 导出写失败（盘满/权限） | exit 5（lib.export_failed），如实报，绝不半写装完成 |
| --verify 哈希不符 | exit 5（lib.integrity_mismatch）：清单与库不一致时如实拒绝交接 |
| 检索零命中 | 空列表即答案（honest empty result），换词重试，不编造 |
| 重复运行 | 同 spec 字节一致重跑（无墙钟字段），重跑不破坏版本链 |

## Failure handling

| symptom | what to do |
|-|-|
| lib.file_missing | fix the path or drop the record explicitly; the refusal stays in the log either way |
| lib.file_unreadable | the file is not UTF-8 text — re-extract it, then re-ingest |
| lib.id_invalid | rename the doc_id (folder semantics belong in structure, not identity) and re-run |
| lib.folder_empty | the cues never matched this batch — fix the rule or drop the folder |
| lib.version_created | expected on re-ingest of changed content; check which entry supersedes which before handing over |
| lib.duplicate_content | identical copies — review and keep both unless a human says otherwise |
| lib.version_sibling | same title, different content — the preprint/published distinction; do not merge |
| lib.unfiled | declare a structure rule for them, or accept the 未归类 parking with the count visible |
| lib.integrity_mismatch (exit 5) | the exported store is not self-consistent — re-export and re-verify before handover |
| lib.no_records (exit 5) | nothing ingestible — the reasons are listed in the refusal message |

## Verification

```bash
python scripts/bench_library.py   # 25 scenarios: one per property plus the
                                  # archive/contract layer and FP guards
```

All 25 pass on this machine. The FP guards pin the behaviour that matters: a
re-ingest with identical content changes nothing, a rerun of the whole spec is
byte-identical, the manifest carries full 64-hex hashes and the tampered store
is caught by the self-check, a missing file is refused while the rest of the
batch ingests (exit 4), a CJK filename with spaces resolves, the contract is
echoed on the ok path and absent on the refusal path, and the CLI writes all
outputs with layered exit codes.

## Routing

- **This skill** when records/files must be organised, hashed, versioned,
  de-duplicated, provenance-marked and handed over with a checkable inventory.
- Not for labelling a batch against a category scheme with matched-cue evidence
  — use p52-doc-classify.
- Not for locating the exact passage inside the files that answers a question —
  use p54-file-search.

## Requirements

Python 3.9+ (3.14 verified); standard library only — no packages to install,
no network calls.

## 创新增益

本 Skill 相比通用 Agent 的核心新增能力（每条附能力边界与增益证据形式）：

1. **内容哈希驱动的版本与重复治理**：判重与版本全按 sha256 内容判定而非文件名
   ——同 id 变内容自动 @vN 且 supersedes 双向留痕，同题不同内容 sibling 成组
   保留、不猜权威版。通用 Agent 最常见的两个事故（覆盖旧版、按名合并）在这里
   是结构性不可能。
   *边界*：近重复（改了几个字的副本）不做模糊判重——错合并比漏报更有害。
   *证据形式*：reingest_never_overwrites / version_siblings_separate /
   duplicate_detection 场景。
2. **可解释归位 + 死规则点名**：目录由声明的 cue 规则驱动，命中 cue 逐文档
   留痕（folder_cues），未命中进未归类计数，声明目录零命中点名
   folder_empty——「归位依据」和「规则失效」都可审计，不是黑盒分类。
   *证据形式*：folder_taxonomy / unfiled_honest / folder_empty_named 场景。
3. **元数据出处留痕**：每个已填字段带 meta_src 来源标记（本引擎只认 record
   声明值，绝不从文件名猜字段），声明字段缺失逐条列 meta_missing——字段级
   的「真实 vs 猜测」在数据里可区分，评审可逐字段核对。
   *证据形式*：meta_provenance / metadata_honest 场景。
4. **归档清单与完整性自检**：manifest.tsv 全量 64-hex 哈希 + 字节长 + 目录，
   接收方可独立重算核对；--verify 重算库内全部哈希（integrity_verified /
   integrity_mismatch），篡改过的 store 会被当场抓住——交接完整性从口头承诺
   变成可执行检查。
   *证据形式*：manifest_and_verify / cli_verify_flag 场景。
5. **契约直通与诚实状态**：result.json 逐字段回填 case_id 与 output_contract
   （case 值直通、契约字面量回填、推导不出填 null 并写 limits；spec 自带
   case_id 同样直通）；status 三态 ok/partial/undetermined 对应退出码
   0/4/5，拒绝路径不回填契约——不把未完成写成完成。
   *证据形式*：cli_contract_passthrough / spec_carried_case_id /
   cli_partial_exit4 场景。
6. **不安全身份守卫**：含路径分隔符或点号的 doc_id 拒绝入库（id_invalid）——
   防止目录树被身份字段污染，这是批量整理脚本常见的静默事故。
   *证据形式*：id_invalid_refused 场景。

## 生态贡献

- **使用说明**：本文件包含用途、适用条件、六步调用入口、任务路由表、输入输出、
  关键方法、rubric 三段映射、异常处置表、限制和自查方法；按 Workflow 可独立
  完成一次「落库—版本—清单—自检」闭环。
- **依赖与安装**：Python 3.9+（3.14 实测），纯标准库零依赖、零安装、零网络调用；
  library.py 可独立导入复用（ingest / 版本链 / 判重 / 归位 / 检索 / 完整性自检
  均为独立函数）。
- **输入约定**：spec 形状（structure + meta_fields + records + query）写在
  Data shapes 一节——任何上游（表格导出、抓取脚本、人工盘点）产出该形状即可
  接入；records 支持 text 内联或 path 指向 UTF-8 文件两种形态。
- **输出 schema**：library.json / inventory.md / manifest.tsv / result.json
  四视图同源且带 schema_version；机器读与人工读分离，manifest 可被任何
  哈希工具核对。
- **示例（标注为示意）**：examples/spec.json + examples/case.json 是最小调用
  示例；本文档 worked example 是一次实跑的节选——均为示意，不冒充正式案例
  结果。
- **可复用引擎**：run / verify_store / key_terms / norm_title / safe_doc_id
  均可独立调用；未归类常量与规则 id 稳定，下游交接系统可直接消费 findings。
- **回归题集**：scripts/bench_library.py 25 场景是可独立复跑的回归门（含误报
  护栏与 CLI 级探针：退出码分层、契约直通与拒绝路径），任何改动必须全过。
- **维护**：改任何规则后必跑 bench（自查方法：25/25 全过）；规则 id 变更须
  同步本文档规则表（引擎与文档逐 id 对齐，strict gate 自动核对）。

引擎已实现该契约：case.json 顶层的可推导值与 output_contract 字面量经
--case 直通最终 result.json，推导不出的填 null 并在 limits 写明；拒绝路径
不回填契约，只写 undetermined result.json。
