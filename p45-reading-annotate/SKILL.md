---
name: reading-annotate
description: >
  Turn extracted reading annotations into structured, retrievable, verifiable
  notes and finish with a contract-carrying result.json. Every annotation is
  anchor-verified against the loaded document — a quote that does not exist is
  refused by name, and an OCR-drifted quote is refused WITH its closest real
  paragraph so the reader can re-extract. Highlight/underline/margin/handwriting
  types and their colours survive verbatim (unknown extractor types are kept,
  never collapsed); same-quote records from different file versions stay separate
  with their own source hashes and are linked explicitly as version siblings;
  duplicate downloads of one file are reported, not merged; notes are typed
  (question / method / result / reusable / doubt / context) from cues or a
  declared kind; notes link only within the same kind on >=2 shared content terms;
  retrieval ranks notes against a real question with kind/doc/tag filters and
  returns nothing when nothing matches. Echoes the platform case_id and every
  output_contract field into result.json. Use when a task supplies already-extracted
  annotations (from PDF highlights, margins, web clips) that must become a usable,
  checkable, retrievable knowledge base.
---

# reading-annotate

The failure this prevents is annotations that were extracted fine but are unusable:
anchors hung on neighbouring paragraphs, OCR-drifted quotes refused with no hint,
red highlights and yellow underlines collapsed into one pile, unknown types
silently re-typed, notes reduced to 摘抄 with no source, duplicate downloads
splitting one batch into two, and "knowledge links" made by sharing a single word.

Four things decide whether this task is done right, and each is enforced:

| property | enforcement |
|-|-|
| 批注能逐条回到原文的具体页与位置 | every quote is located by exact match across ALL occurrences; the declared page (or character offset) picks the right one, an ambiguous quote is refused naming every occurrence, a page- or offset-contradicting declaration is refused at ingest time, and a drifted quote is refused with its closest real candidate |
| 类型与标签不丢 | `type` is preserved verbatim (the five known values plus whatever the extractor emits — an unknown type stays itself, never re-typed), `color` and `tags` are kept as-is on every note |
| 版本不串味、重复不分裂 | same-quote records from different files stay separate records with per-file sha256, AND the split is made explicit as a version-sibling link; a file loaded twice under two ids is reported as a duplicate |
| 笔记可检索、可复跑 | notes carry content terms and tags; retrieval ranks by shared terms with kind/doc/tag filters and returns an honest empty list; the export is notes.md + index.json that anyone can re-check |

## 六步运行时入口（Harbor 契约）

平台运行时原始输入固定为 `/input/case.json` 与 `task.md`；工作区 `/app/work`；
最终交付写 `/app/output`。按以下六步执行：

| 步 | 动作 | 要点 |
|-|-|-|
| 0 | 读 `/input/case.json` | 取 `case_id`、任务说明与 `output_contract`（原样保留，不改名）；按 `task.md` 指向的路径读**实际材料**——PDF 用平台工具抽文本（form feed 分页），批注导出用真实导出文件；标签与文件名不是内容来源 |
| 1 | 判形态路由 | 按下方「任务措辞 → 路由」表决定 Stage 0 谁做、批注从哪来；扫描件无文本层、加密损坏文件在路由阶段就 Declared，不硬做 |
| 2 | 先产出目标产物 | 先 `load` 文档再 `ingest` 已有批注——即使后续步骤中断，已验证的批注与锚点已在 store 里（尽早写出诚实的部分结果） |
| 3 | 构造输入 | 批注记录装进 JSON 列表（quote/page/type/color/note/kind/tags）；不确定的锚点先 `verify`，别把猜测写进 store |
| 4 | 审计 | `verify` 复核每个锚点；`retrieve` 用真实问题验证笔记可检索；`export` 产出 notes.md + index.json |
| 5 | 修发现重跑 | 被拒绝的记录逐条按 failure_recovery 的 recovery 动作处理（OCR 漂移→按建议段落重抽；页码冲突→改声明；歧义→补 page 或 start），重跑 ingest 直到零拒绝或材料本身不允许 |
| 6 | 合并 result.json | 跑 `result --out /app/output --case /input/case.json`：case_id 与 output_contract 逐字段直通，status 按映射写成 done/partial/failed，refusals/uncertainty/limits 随附 |

引擎已实现契约直通：`result --case case.json` 把 `case_id` 与 `output_contract` 的
每个字段写进 result.json 顶层——结果里已有的字段保留，case 顶层携带的小体积值
原样拷贝，契约里的字面量（短字符串/数值/布尔）直接回填，推导不出的填 null 并在
limits 里写明。拒绝路径（store/case 不可读）不回填契约，只写 undetermined
result.json。

## 任务措辞 → 路由

| 任务措辞 / 输入形态 | 路由 |
|-|-|
| 给了 PDF + 高亮导出（JSON/CSV） | Stage 0 自己做：pdftotext（或平台 pdf 工具）抽文本成 extracted.txt，高亮导出转成批注记录列表 → load → ingest |
| 给了已抽取的批注 JSON | 直接 ingest；quote 必须逐字存在于已加载文档 |
| 扫描件无文本层 | 先 OCR；OCR 漂移的批注会被 ann.anchor_ocr_drift 点名并附最接近的真实段落——按建议重抽，不许模糊匹配放行 |
| 加密 / 损坏文件 | load 拒绝（exit 4）并写明原因；可处理的其余文件照常走完，不把未完成写成完成 |
| 同一文献多版本（v1/v2） | 分开 load（各自 sha256），同 quote 批注保持独立记录 + version-sibling 显式连接 |
| 重复下载同一文件 | load 报 duplicate_of；保留一个 id 或在笔记里记录别名，不拆成两批 |
| 批注引用旧版本文本 | verify 会点名失效锚点：重锚到当前版本，或保留旧版本文件并注明 |
| 要求「按主题/实体/标签检索」 | retrieve --question 配 --kind/--doc-id/--tag 过滤；词法检索召回不足如实返回空，不硬凑 |
| 要求「待验证疑点单独归类」 | 批注 note 写「存疑/待验证…」或声明 kind 为 doubt；疑点不与结论混类 |
| 只要摘抄不要结构 | 不适用——本 Skill 的最小交付就是带锚点与类型的结构化笔记；纯摘抄请直接复制原文 |
| 目录级归档治理 / 长期档案制度 | 不适用（题目边界），只做本批材料的抽取—结构化—关联—入库闭环 |

## Workflow

```bash
# 1. load the document (UTF-8 text; form feeds mark page boundaries)
python scripts/annotate_cli.py --store ws.json load --doc-id paper --doc-file extracted.txt

# 2. ingest annotations (refused ones are named WITH rule id and recovery, never dropped)
python scripts/annotate_cli.py --store ws.json ingest --doc-id paper --annotations ann.json

# 3. re-check every anchor still resolves
python scripts/annotate_cli.py --store ws.json verify

# 4. ask the notes a real question (filters optional)
python scripts/annotate_cli.py --store ws.json retrieve --question "uptake 提高了多少倍" --kind result

# 5. export the structured notes and the machine-readable index
python scripts/annotate_cli.py --store ws.json export --out ./out

# 6. finish: result.json with case contract passthrough
python scripts/annotate_cli.py --store ws.json result --out /app/output --case /input/case.json
```

批注记录形状（一个 JSON 列表）：

```json
[
  {"quote": "three-fold", "page": 1, "type": "highlight", "color": "yellow",
   "note": "结果：涂层使吸收速率提高三倍", "tags": ["uptake"]},
  {"quote": "six replicates", "page": 2, "type": "underline",
   "note": "方法：每组六个重复"},
  {"quote": "存疑的结论句", "type": "margin", "kind": "doubt", "note": "存疑：单一厚度能否外推"}
]
```

`quote` 是锚点，必须逐字存在于已加载文档；`page`/`start` 可省略（由文本解析），
声明了就参与消歧；`type` 原样保留（未知类型不折叠）；`kind` 声明合法值
（question/method/result/reusable/doubt/context）否则拒绝；`tags` 原样保留并可用于
检索过滤。

退出码：`0` ok / done；`2` usage（未知 kind 等）；`4` refused 或 failed（锚点拒绝、
verify 失败、文件不可读、result 判 failed）；`5` undetermined（store/case 文件不可读
——仍写 result.json，绝不 traceback）。

## Rules

| rule | severity | what it proves |
|-|-|-|
| `ann.doc_not_loaded` | refusal | 批注要挂到的文档没有加载——先 load，store 存文档不存假设 |
| `ann.no_quote` | refusal | 记录没有 quote——空锚点一律拒绝 |
| `ann.record_not_object` | refusal | 一条记录不是 JSON 对象——点名行号 |
| `ann.annotations_not_list` | refusal | 批注文件不是 JSON 列表 |
| `ann.declared_kind_unknown` | refusal | 声明的 kind 不在六类之内——拒绝而不是静默改类型 |
| `ann.anchor_mismatch` | refusal | quote 不存在于文档——点名并拒绝，绝不静默改挂相邻段 |
| `ann.anchor_ocr_drift` | refusal | 错位像 OCR 漂移/重排：拒绝并附最接近的真实段落（suggestion：paragraph、similarity、candidate） |
| `ann.anchor_page_conflict` | refusal | 声明页码与文档矛盾——点名 quote 实际所在页 |
| `ann.anchor_offset_conflict` | refusal | 声明字符偏移与所有出现位置不符 |
| `ann.anchor_ambiguous` | refusal | quote 出现多次且无法消歧——点名全部出现段落，要求补 page 或 start |
| `ann.duplicate_document` | info | 同一内容文件被加载两次（哈希相同）——报告 duplicate_of，不静默合并 |
| `ann.doc_file_missing` / `ann.doc_file_unreadable` | refusal | load 的文件缺失/非 UTF-8/不可读 |
| `ann.annotations_unreadable` | refusal | 批注文件不是可读 JSON |
| `ann.store_unreadable` / `ann.store_unwritable` | refusal | store 损坏或不可写——exit 5 诚实拒绝，不 traceback |

## Output contract 与 rubric 三段映射

`result` 命令写 `result.json`，顶层字段：`schema_version`、`status`、
`status_reason`、`case_id`、…output_contract 的每个原始字段…、`documents[]`
（doc_id、paragraphs、sha256_12、duplicate_of）、`notes[]`（每条含 anchor、type、
color、tags、note_kind、source_sha、ingested_at、terms）、`links[]`（shared_terms
即关联依据）、`version_siblings[]`、`verify`（anchors、invalid、ok）、
`operation_trace[]`（事件流水）、`failure_recovery[]`（每条失败的接管动作）、
`uncertainty[]`、`limits[]`。`export` 另写 `notes.md`（人读视图）与 `index.json`
（机器视图：notes + links + version_siblings）。

对应题目「Skill 运行后的输出要求」的三段：

| rubric 要求的输出 | result.json 承载 | 完成标准 |
|-|-|-|
| 资料结果（清单、元数据、版本关系或知识结构） | `documents` + `notes` + `links` + `version_siblings` | 与输入文件一一对应：每条笔记有锚点（doc/page/paragraph/chars）与原文哈希 |
| 操作证据（哈希、来源、权限、变更和日志） | `documents[].sha256_12` + `notes[].source_sha/ingested_at` + `verify` + `operation_trace` | 他人可复跑并核对：同 store 同输入重跑，notes/links 逐条一致 |
| 失败与恢复（跳过、冲突、无权限、重复和恢复记录） | `failure_recovery`（rule + reason + recovery）+ `uncertainty` + refusals | 不把未完成写成完成：status failed/partial 时 status_reason 写明差什么 |

refusals 袋按文档保留**最近一次 ingest** 的记录级拒绝（读者修复后重跑即清除，
历史计数仍在 operation_trace 的事件流水里）；命令级拒绝（文档未加载、批注文件
不是列表）发生在没有任何记录入库之前，只进事件流水与当次返回，不滞留在
failure_recovery 里——status 反映的是当前可交付状态，不是过期状态。

status 映射：`done`（有笔记、verify 全过、零拒绝）→ exit 0；`partial`（有拒绝记录
或 verify 失效锚点，可复核部分照常交付）→ exit 3；`failed`（零条批注被接受——
材料不允许或全部被拒）→ exit 4；store/case 不可读 → undetermined → exit 5。

## Minimal worked example（示意）

输入 `examples/extracted.txt`（3 页文本，form feed 分页）与
`examples/annotations.json`（3 条批注），实际运行：

```bash
python scripts/annotate_cli.py --store ws.json load --doc-id paper --doc-file examples/extracted.txt
python scripts/annotate_cli.py --store ws.json ingest --doc-id paper --annotations examples/annotations.json
python scripts/annotate_cli.py --store ws.json retrieve --question "uptake 提高了多少倍"
python scripts/annotate_cli.py --store ws.json result --out out --case case.json
```

示意输出（节选自一次实跑，标注为示例——不是正式案例结果）：

```json
{"ok": true, "accepted": [
  {"doc_id": "paper", "page": 1, "paragraph": 1, "start": 38, "end": 48,
   "quote": "three-fold", "type": "highlight", "color": "yellow",
   "note_kind": "result", "tags": [], "source_sha": "7616814fa13afbe0",
   "annotation_id": "063ddced7703"}],
 "refused": []}
```

result.json（同一实跑，`--case` 带 case_id 与 output_contract）：

```json
{"schema_version": "annotate/v2", "status": "done", "status_reason": "",
 "case_id": "case-demo-annotate",
 "deliverable": "structured annotation notes + index",
 "documents": [{"doc_id": "paper", "paragraphs": 6, "sha256_12": "7616814fa13a"}],
 "notes": [{"annotation_id": "063ddced7703", "quote": "three-fold",
            "anchor": {"page": 1, "paragraph": 1, "start": 38, "end": 48},
            "type": "highlight", "color": "yellow", "note_kind": "result"}],
 "verify": {"anchors": 3, "invalid": [], "ok": true},
 "failure_recovery": [], "uncertainty": [], "limits": []}
```

一个 quote 出现两次且未声明页码会被拒绝并点名两个段落；声明页码与文档矛盾在
ingest 时被拒；OCR 漂移的 quote 被拒时附带最接近的真实段落；重复 ingest 同一文件
不产生重复锚点；同一 quote 出现在两个版本文件中保持两条独立记录并生成
version-sibling 连接。

## Limits

- **The document enters as text.** A PDF's highlights must be extracted first (any
  extractor that yields page + quote records); this skill is the half that makes
  extracted annotations usable — anchor-verified, typed, linked, retrievable.
- **Anchors are exact substring matches.** An OCR'd quote with drifted characters
  is refused WITH a suggested paragraph, but fixing the text stays the reader's
  step — the skill never loosens the match on its own.
- **Linking is term-based and kind-constrained.** Two notes link when they share
  >=2 content terms AND the same kind; the shared terms are recorded as the link's
  evidence. A causal or contradiction relation between notes is not inferred —
  that is analysis, not bookkeeping.
- **Retrieval is lexical.** It ranks shared content terms within the filtered pool;
  a paraphrased question that shares no terms returns an honest empty list. 召回
  不足时如实返回空并提示换词/去过滤，不硬凑结果。
- **One store, one reader.** Concurrent writers overwrite each other; no lock.
- **`ingested_at` 是墙钟时间.** 除时间戳外同一 store 重跑 notes/links 逐条一致；
  幂等性按 notes/links 比对，不按整文件字节比对。

## 异常处置表

| 形态 / 故障 | 处置 |
|-|-|
| 文档文件缺失 / 目录 / 无权限 | load 拒绝（exit 4），写明 ann.doc_file_missing 或不可读原因；其余文件照常 |
| 文档非 UTF-8 | load 拒绝并附解码错误；先转码再 load |
| store 损坏 / 路径是目录 | exit 5 undetermined（ann.store_unreadable），result 命令仍写 undetermined result.json |
| store 不可写（盘满/权限） | exit 5 undetermined（ann.store_unwritable），不丢已内存状态但如实报告 |
| 批注文件坏 JSON / 非 list | ingest 拒绝（exit 4），不崩溃 |
| 批注针对未加载文档 | ann.doc_not_loaded 拒绝——先 load |
| quote 不存在（普通错位） | ann.anchor_mismatch：修 quote 或重抽；绝不模糊放行 |
| quote 不存在（OCR 漂移样） | ann.anchor_ocr_drift：按 suggestion 的段落与相似度重抽精确文本 |
| quote 重复出现 | ann.anchor_ambiguous：补 page 或 start 消歧；声明 start 与位置不符则 ann.anchor_offset_conflict |
| 声明页码矛盾 | ann.anchor_page_conflict：改声明或省略由文本解析 |
| 加密/损坏/无文本层扫描件 | Stage 0 处理不了：如实写进 limits；可处理文件照常走完闭环 |
| 同文件重复加载 | duplicate_of 报告：保留一个 id 或记别名，不拆批 |
| 跨版本 quote 相同 | 两条独立记录 + version-sibling 连接，各带 source_sha |
| 重复运行 | store 幂等：同记录不重复入库、锚点不膨胀；比对 notes/links 而非文件字节 |
| 检索无命中 | 空列表即答案；换词或去过滤重试——不编造结果 |

## Verification

```bash
python scripts/bench_annotate.py   # 29 scenarios: anchors, OCR-drift suggestion,
                                   # typed preservation, doubt kind, duplicates,
                                   # version siblings, filters, contract passthrough,
                                   # honest failed status, corrupt-store refusal
```

All 29 pass on this machine. The FP guards pin the behaviour that matters: a
mismatched anchor is refused by name, a drifted quote gets a suggestion but a
gibberish quote does not, an unknown type survives verbatim, two same-kind notes
sharing exactly one term do not link while a positive link carries its shared
terms, the same file loaded twice is reported symmetrically, and an empty store
reports failed instead of pretending success.

## Requirements

Python 3.9+ (3.14 verified); standard library only — no packages to install, no
network calls.

## 创新增益

本 Skill 相比通用 Agent 的新增能力（每条附能力边界与增益证据形式）：

1. **扫描件批注锚点校正建议**：漂移 quote 不是裸拒绝——引擎滑窗比对全文，给出
   最接近的真实段落、相似度与候选文本，OCR 置信度低场景从「人工大海捞针」变成
   「按建议段落重抽」。
   *边界*：建议不是改写——放行与否仍由精确匹配决定。
   *证据形式*：ocr_drift_suggested / ocr_drift_no_suggestion 场景。
2. **跨版本批注归并的第三条路**：既不静默合并（版本串味）也不放任分裂（找不到
   同源批注）——独立记录 + version-sibling 显式连接，证据是同 quote 同类型跨文件，
   双方各带 source_sha。重复下载的同文件用哈希对称报告 duplicate_of。
   *证据形式*：version_siblings_linked / versions_separate / duplicate_document 场景。
3. **锚点消歧的完整闭环**：全量定位 → 页码消歧 → 字符偏移消歧 → 歧义点名全部
   出现位置——同段重复 quote 也能精确挂锚，这是「锚点错位」失败的机械根治。
   *证据形式*：offset_disambiguation / ambiguous_refused / page_mismatch_refused 场景。
4. **类型语义零损耗**：五类已知批注类型 + 未知类型原样保留（不折叠成 highlight），
   color 与 tags 逐字随行；声明的非法 kind 拒绝而不是静默改写——类型不丢从承诺
   变成规则。
   *证据形式*：types_preserved / type_unknown_preserved / declared_kind_unknown 场景。
5. **契约直通与诚实状态**：result.json 逐字段回填 output_contract 与 case_id；
   status 由 verify + refusals 推导（done/partial/failed），空库如实 failed，损坏
   store 如实 exit 5——不把未完成写成完成。
   *证据形式*：result_contract_passthrough / result_failed_honest / store_corrupt_refused 场景。

## 生态贡献

- **使用说明**：本文件包含用途、适用条件、六步调用入口、任务路由表、输入输出、
  关键方法、异常处置表、限制和自查方法；按 Workflow 可独立完成一次「抽取—
  结构化—关联—入库—检索」闭环。
- **依赖与安装**：Python 3.9+（3.14 实测），纯标准库零依赖、零安装、零网络调用；
  annotate.py / reader.py 可独立导入复用（锚点定位器、笔记结构器、关联与检索器）。
- **输入目录约定**：文本 + form feed 分页（pdftotext 同款约定）；批注是
  {quote, page, type, color, note, kind, tags} 记录列表——任何抽取器产出该形状即可
  接入，约定写在 Data shapes 与 Stage 0 一节。
- **输出 schema**：notes/links/version_siblings/anchors 的字段结构稳定且带
  schema_version，下游（综述、卡片、图谱）可直接消费；notes.md 人读、index.json
  机器读，双视图同源。
- **示例（标注为示例）**：`examples/extracted.txt` + `examples/annotations.json`
  是最小调用示例；本文档 worked example 是一次实跑的节选——均为示意，不冒充
  正式案例结果。
- **关联规则可复用**：同 kind + ≥2 共享词的关联判定与 shared_terms 依据格式、
  version-sibling 判定均可独立复用；阈值 min_shared 是参数不是硬编码。
- **回归题集**：`scripts/bench_annotate.py` 29 场景是可独立复跑的回归门（含误报
  护栏与 CLI 级探针），任何改动必须全过。
- **维护**：改任何规则后必跑 bench（自查方法：29/29 + FP 护栏全过）；规则 id
  变更须同步本文档规则表（引擎与文档逐 id 对齐，strict gate 自动核对）。

引擎已实现该契约：case.json 顶层的可推导值与 output_contract 字面量经
`result --case` 直通最终 result.json，推导不出的填 null 并在 limits 写明；拒绝
路径不回填契约，只写 undetermined result.json。
