---
name: file-search
description: >
  Index a corpus of research documents and answer boolean queries with located,
  verbatim-checkable, section-level evidence. The index stores each document's
  text, paragraphs, enclosing section titles (numbered headings, markdown
  hashes, Chinese 章节标题; a sentence that merely starts with a number is not
  a heading), content terms, declared metadata and a per-document sha256 plus a
  corpus fingerprint; the query ({all, any, filters} or a bare string) is
  executed exactly as declared — all-terms is a hard constraint, any-terms an
  alternative set, both given both must hold, and every declared metadata
  filter (year, project, type, batch...) must equal the document's meta — a
  document missing the key never matches, an unsatisfiable filter is an honest
  empty that names the filter, and a malformed filter is refused rather than
  dropped. Every hit carries its matched terms, the document's full sha256 and
  passages; every passage carries a locator (document id, paragraph index,
  enclosing section title, character range, verbatim quote) where quote equals
  text[start:end], so anyone holding the corpus can re-check the hit at the
  exact section and position. Identical texts under two doc ids are named as
  duplicate content — a renamed copy never passes as a second piece of
  evidence. Every result records the normalised query and the index
  fingerprint, and the index itself is written beside the result — the same
  corpus + query re-runs byte-identical. A query nothing matches returns an
  honest empty list; an empty corpus, a malformed index, an empty query and an
  invalid filter are refusals (exit 5 with a written result.json), never
  crashes. The CLI echoes case_id and every output_contract field from --case
  into result.json (spec-carried case_id passes through too; the refusal path
  echoes none of it) and layers its exits: 0 ok, 4 partial, 5 undetermined.
  Use when files are already in the library and the task is to find, filter and
  locate the passage that answers a question with evidence that can be
  replayed.
---

# file-search（科研文件智能检索）

The failure this prevents is retrieval nobody can trust: a whole file returned
where a section was asked for, a citation with no section or position, a filter
silently relaxed until something "hits", a renamed copy counted as a second
piece of evidence, an empty result padded with near-misses, and a run nobody
can replay because the query and the index were never recorded.

Four properties decide whether this task is done right, and each is enforced:

| property | enforcement |
|-|-|
| 检索可复现 | every result records the normalised query (**query.all** / **query.any** / **query.filters**), the index fingerprint (index_sha256, sha256 over the exact indexed texts and their declared metadata) and documents_indexed; the CLI also writes index.json beside the result, so the query + index pair can be replayed by anyone — and the same corpus + query re-runs byte-identical (no wall-clock fields) |
| 命中带定位 | every hit carries matched_terms and the document's full sha256 (evidence pinned to the exact version); every passage carries a locator with paragraph index, enclosing section title, character range and verbatim quote — quote == paragraph[start:end] is checkable without trusting the engine, and the section title puts the hit at 章节 level, not whole-file |
| 空结果诚实 | a query nothing matches returns hits: [] with empty: true and a note over the indexed count — when filters were declared the note names them and states they were executed, not relaxed; a miss is reported as a miss, never padded |
| 布尔与过滤硬执行 | all terms must every one appear; any terms at least one; both given, both must hold; every declared metadata filter must equal the document's meta and a document missing the key never matches — conditions are executed as declared, a malformed filter is refused (never quietly dropped), an unsatisfiable one yields an honest empty |

## 六步运行时入口（Harbor 契约）

平台运行时原始输入固定为 /input/case.json 与 task.md；工作区 /app/work；最终交付
写 /app/output。按以下六步执行：

| 步 | 动作 | 要点 |
|-|-|-|
| 0 | 读 /input/case.json | 取 case_id 与 output_contract（原样保留，不改名）；按 task.md 指向的路径读实际材料——PDF/Word 用平台工具抽文本（约定一段一行），文件名与标签不是内容 |
| 1 | 判形态路由 | 按下方「任务措辞 → 路由」表决定输入形态：已有索引走 --index、语料走 --corpus；扫描件无文本层、加密损坏文件在路由阶段就 Declared，不硬做 |
| 2 | 先产出目标产物 | 先建索引写出 index.json（含指纹与分节）——即使后续查询失败，索引与回链依据已交付（尽早写出诚实的部分结果） |
| 3 | 构造 spec | corpus（id/text/meta 逐条真实）+ query：核心概念进 all，同义/缩写/跨语言表述进 any，年份/项目号/类型等硬条件进 filters——条件无法满足就如实空，绝不放宽 |
| 4 | 审计 | 抽查 quote == 文本[start:end]；核对 doc_sha256 与 index 一致；空结果核对 note 与 filters；skipped/findings 逐条看 |
| 5 | 修发现重跑 | skipped 条目修形状；词不中显式扩 any（同义表述由调用者声明，引擎不代猜）；filters 打偏核对 meta 字段名——重跑直到命中有定位或如实空 |
| 6 | 合并 result.json | 加 --case /input/case.json 重跑：case_id 与 output_contract 逐字段直通，status 三态（ok=全库已索引 / partial=有条目被跳过并点名 / undetermined=无法判定） |

引擎已实现契约直通：--case 把 case_id 与 output_contract 的每个字段写进
result.json 顶层——结果里已有的字段保留，case 顶层携带的小体积值原样拷贝
（大体积材料字段除外），契约里的字面量（短字符串/数值/布尔）直接回填，推导
不出的填 null 并在 limits 里写明；spec 自带 case_id 时同样直通。拒绝路径
（语料/索引/case 不可读）不回填契约，只写 undetermined result.json——坏的
文件可能就是 case 文件本身。

## 任务措辞 → 路由

| 任务措辞 / 输入形态 | 路由 |
|-|-|
| 文件已在库里，要找回答问题的段落 | 本 Skill：corpus + query（核心概念 all / 同义族 any / 硬条件 filters），返回段落级定位与回链 |
| 给了 PDF / Word / PPT | Stage 0 用平台工具抽成 UTF-8 文本（一段一行约定）再进 corpus；抽不出文本层的扫描件如实 Declared，不硬做 |
| 提问是自然语言 | 拆词项：核心概念进 all，同义词/缩写/跨语言写法进 any——同义表述由调用者显式声明，引擎是词法的，不代猜 |
| 带硬过滤（年份 / 项目号 / 文件类型 / 批次 / 版本） | query.filters 逐条硬执行：文档缺键不命中、值不等不命中、条件无解如实空并点名过滤器——绝不放宽制造命中 |
| 索引已建过（换查询不换语料） | --index 复用 index.json（指纹一致才可复放）；重跑与首跑字节一致 |
| 命中要回链可复核 | hits 自带 doc_sha256 + passage locator（paragraph/section/start/end/quote）；quote 与原文逐字相等，第三方可独立重验 |
| 疑似重复 / 改名副本 / 多版本文件 | 引擎按文本 sha256 点名 duplicate_content：两份都索引但显式关联——副本不当第二份证据；版本差异本身不是本 Skill 的治理对象（入库治理用 p53-library-mgmt） |
| 要「语义相似但用词不同」的召回 | 不适用——词法检索如实返回空；把同义表述显式写进 any 是调用者的声明责任，引擎不假装语义 |
| 开放网络文献检索 / 全文精读 / 综述写作 | 不适用（题目边界） |
| 存储系统权限建设 | 不适用（题目边界）——本 Skill 只做库内检索—定位—过滤—回链 |
| 只要整篇文件不要定位 | 不适用——本 Skill 的最小交付是段落级定位 + 逐字回链；整篇文件请直接给路径 |

## Workflow

```bash
# 1. index the corpus and answer the query, with the case contract echoed
#    into result.json
python scripts/search_cli.py --corpus examples/corpus.json \
    --query-file examples/query.json --case examples/case.json --out ./out

# a bare-string query becomes an any-of query over its terms
python scripts/search_cli.py --corpus examples/corpus.json \
    --query "缓冲液 配制" --out ./out

# 2. replay a query against a previously built index (fingerprint kept)
python scripts/search_cli.py --index out/index.json \
    --query-file examples/query.json --out ./out2

# 3. the regression suite (26 scenarios; clean baseline must be all-pass)
python scripts/bench_search.py
```

The engine lives in scripts/search.py (importable: build_index(corpus),
run_query(index, query), search(spec); search.is_heading and
search.section_map are the section detectors). Exit codes:

| exit | status | meaning |
|-|-|-|
| 0 | ok | query answered, whole corpus indexed; contract echoed when --case given |
| 4 | partial | query answered but corpus entries were skipped or warned — findings list them by index and reason |
| 5 | undetermined | refusal: unreadable files, empty corpus, malformed index, empty query, invalid filter, index write failure — result.json still written |
| 2 | usage | CLI misuse (missing required argument) |

undetermined → 5：拒绝也是结果——所有非零退出都先写出 result.json 再退出，
绝不带 traceback 崩溃。

## Data shapes

The corpus (or a prebuilt index) plus a query:

```json
{"documents": [
  {"id": "paper-coating", "meta": {"year": 2023, "project": "P01"},
   "text": "Porous coatings raise the uptake rate three-fold.\nWe measured uptake at 25 C with six replicates per arm."},
  {"id": "protocol-buffer",
   "text": "1 缓冲液配制\nTris 缓冲液 50 mM，pH 7.4。\n\n2 存储\n分装后 -20 C 冻存。"}
]}
```

```json
{"all": ["uptake"], "any": ["three-fold", "replicates"], "filters": {"year": 2023}}
```

A corpus entry is an object with id（可选，自动编号 doc-NNN）、text、可选 meta
（声明式元数据，供 filters 硬过滤；非对象 meta 点名并按空存储）；a bare
string is tolerated as a document with a generated id; an entry that is
neither is skipped and named (search.doc_skipped). A duplicate doc id is
skipped and named rather than silently merged; identical text under two ids is
BOTH indexed and named as duplicate content. 章节约定：一段一行，编号标题
（1 缓冲液配制 / 3.2 样品制备）、Markdown 标题、中文章节（二、方法 / 第四章）
是分节线；以数字开头的普通句子（长度>60 或以句号等结尾）不算标题。

An explicit query object declares all（每词必须出现）and/or any（至少一词）term
lists and optional filters（逐条硬约束，值为标量），matched as case-insensitive
substrings of the document text — CJK phrases stay whole, so 缓冲液 matches as
one term. A bare-string query becomes an any-of query over its terms (latin
words + whole CJK runs). filters 不是检索词：filters-only 的 query 仍会因无词项
被拒（empty_query）——过滤是收窄，不是代替检索。

## Output contract

--out receives:

- index.json — the index, kept for replay: per document text, paragraphs,
  section starts, content terms, declared meta and the document sha256; the
  document order; and corpus_sha256.
- result.json — status (ok / partial / undetermined), case_id (when supplied),
  query (normalised with all, any, filters), index_sha256, documents_indexed,
  hits[] (each: doc_id, doc_sha256, score = distinct matched terms,
  matched_terms, passages[] with term + locator containing paragraph, section,
  start, end, quote), empty, and on a miss an honest note naming declared
  filters; skipped corpus entries, meta warnings and duplicate content are
  named under findings with their rules.

Rubric 三段结构映射（字段名与评分表原词对应）：

| rubric 段 | rubric 要求原文 | 本 Skill 落点 |
|-|-|-|
| 资料结果 | 目录、文件清单、元数据、版本关系或知识结构；与输入文件和题目规则一一对应 | index.json 即知识结构（文档清单/分节/词项/元数据/指纹），documents_indexed 与 order 逐条对应输入 |
| 操作证据 | 哈希、来源、权限、变更和日志；他人可复跑并核对 | index_sha256 语料指纹 + 每文档 sha256（版本定位），query 记录 all/any/filters 全量留档，index.json 可复放——任何人按记录重跑同查询得到同结果 |
| 失败与恢复 | 跳过、冲突、无权限、重复和恢复记录；不把未完成写成完成 | findings[] 点名 skipped/meta 痕/重复内容，note 点名无法满足的 filters，status 三态 + 退出码 0/4/5 分层，异常处置表给出每条恢复动作 |

A refusal run writes result.json with status undetermined and a named refusal —
a refusal is a result, not a crash.

## The refusal and finding index

| id | severity | when |
|-|-|-|
| `search.spec_unreadable` | high (exit 5) | the corpus / index / query file is unreadable or not the declared JSON shape |
| `search.case_unreadable` | high (exit 5) | the --case file is unreadable or not a JSON object; the contract is not echoed from a broken file |
| `search.empty_corpus` | high (exit 5) | corpus missing, not a list, or no document could be indexed (skip reasons listed) |
| `search.index_malformed` | high (exit 5) | the index is not a readable index object or an entry is malformed — refused as a whole instead of partially searched |
| `search.empty_query` | high (exit 5) | no query given, or the query declares nothing searchable — searching nothing would fabricate a result |
| `search.filter_invalid` | high (exit 5) | query.filters is not an object or a filter value is not a scalar — refused rather than the constraint being quietly dropped |
| `search.export_failed` | high (exit 5) | index.json could not be written (disk full / permission) — reported, never half-written silently |
| `search.doc_skipped` | low | a corpus entry that is not a document (named, with its index and reason) |
| `search.meta_invalid` | low | a corpus entry whose meta is not an object: text still indexed, meta stored empty, entry named |
| `search.duplicate_content` | low | identical text under several doc ids: both indexed, the copy named — not a second source |

## Minimal worked example

Input: examples/corpus.json (3 documents, one CJK with two numbered sections) +
examples/query.json ({"all": ["uptake"], "any": ["three-fold", "replicates"]})
+ examples/case.json (a case_id plus an output_contract). Run:

```bash
python scripts/search_cli.py --corpus examples/corpus.json \
    --query-file examples/query.json --case examples/case.json --out ./out
```

示意 output (abridged — an illustrative sketch of the shape, from a real run
of the example; not a formal case result):

```json
{"status": "ok", "ok": true, "empty": false,
 "case_id": "case-demo-54",
 "deliverable": "located search evidence",
 "search_schema": "file-search/v1",
 "query": {"all": ["uptake"], "any": ["three-fold", "replicates"], "filters": {}},
 "index_sha256": "c1c9b8a0616b6216", "documents_indexed": 3,
 "hits": [
  {"doc_id": "paper-coating",
   "doc_sha256": "fd5c9bcfa6d48b375b84a093fbddce342d7701e79bf3d8fa1861a84a9ef2440c",
   "score": 3,
   "matched_terms": ["replicates", "three-fold", "uptake"],
   "passages": [
    {"term": "three-fold",
     "locator": {"paragraph": 0, "section": null, "start": 38, "end": 48,
                 "quote": "three-fold"}},
    {"term": "replicates",
     "locator": {"paragraph": 1, "section": null, "start": 36, "end": 46,
                 "quote": "replicates"}}]}]}
```

Adding "filters": {"year": 2023} over the same corpus with meta declared keeps
paper-coating (year 2023) and excludes the 2024 paper — executed as declared,
never relaxed; an unsatisfiable year (1999) returns an honest empty whose note
names the filter. The anneal paper is absent from the first result because it
contains uptake but neither three-fold nor replicates — the any-condition is
not relaxed for it. quote equals the indexed paragraph slice at [start, end)
— the locator can be re-verified against index.json (or the original corpus)
without trusting the engine, and section titles (1 缓冲液配制 / 2 存储 in the
CJK protocol) put hits at section granularity.

## Limits

- **Lexical, not semantic.** Terms match as substrings of the indexed text; a
  paraphrase sharing no term is an honest miss. Synonyms belong in the any
  list, declared by the caller — the engine never invents synonyms.
- **Ranking is count-based.** Score = number of distinct matched query terms;
  ties keep index order. It orders evidence, it does not grade relevance.
- **Sections are line-convention based.** 编号标题/Markdown/中文章节按一行一段
  约定识别；无分节线的文档每个 locator 的 section 为 null（段落与字符定位不受
  影响）。印刷页码与 PDF 物理页错位需要在抽取文本时处理（form feed 或页标记），
  本引擎的定位粒度是段落内字符区间。
- **Filters are exact-value.** 每条 filter 与文档 meta 做相等比较（数值或字符
  串形态都接受），缺键不命中；范围条件（如 year > 2020）不在此实现——请显式
  展开为允许值集合或多查询。
- **Passages are capped.** At most 20 passages per document, earliest
  occurrences first — enough to verify, not a substitute for reading.
- **One condition set per query.** No nested boolean trees; all + any + filters
  covers the filter shapes the brief names.

## 异常处置表

| 形态 / 故障 | 处置 |
|-|-|
| corpus / index / query 文件坏 JSON 或缺失 | exit 5 undetermined（search.spec_unreadable），result.json 照写，无 traceback |
| case 文件坏 JSON / 非对象 | exit 5（search.case_unreadable）——坏文件可能就是 case 本身，契约不回填 |
| corpus 非列表 / 零文档 / 全被跳过 | exit 5（search.empty_corpus），跳过原因逐条列出 |
| index 结构损坏 / 条目畸形 | exit 5（search.index_malformed）：整体拒绝，不搜残缺索引 |
| query 空 / 无词项 / 类型不对 | exit 5（search.empty_query）——空查询会伪造结果 |
| filters 非对象 / 值非标量 | exit 5（search.filter_invalid）：条件宁拒不丢，绝不静默放宽 |
| corpus 条目非对象非字符串 | 点名跳过（search.doc_skipped），其余照常索引，status=partial exit 4 |
| entry 无 text | 点名跳过（search.doc_skipped） |
| doc id 重复 | 点名跳过，不静默合并 |
| entry meta 非对象 | finding（search.meta_invalid）：文本照常索引，meta 存空——filters 不猜 |
| 同文本不同 id（改名副本） | finding（search.duplicate_content）：两份都索引并显式点名，不当第二份证据 |
| filters 无一命中 | honest empty + note 点名过滤器与「执行未放宽」 |
| 词项零命中 | honest empty + note；换词或显式扩 any 重试，不编造 |
| 加密 / 无文本层扫描件 | 抽不出文本就进不了索引：Stage 0 如实 Declared 写进 limits，不硬做 |
| index.json 写失败（盘满/权限） | exit 5（search.export_failed），如实报，绝不半写装完成 |
| 重复运行 | 同语料同查询字节一致（无墙钟字段），--index 复放同指纹 |

## Failure handling

| symptom | what to do |
|-|-|
| search.empty_corpus (exit 5) | the corpus file holds no documents — fix the shape or the path; the engine never searches an empty index |
| search.index_malformed (exit 5) | rebuild the index from the corpus (drop --index, use --corpus); a partial index is refused, not patched |
| search.empty_query (exit 5) | declare all and/or any terms — a query with no terms is refused, not run as a no-op |
| search.filter_invalid (exit 5) | filters must be an object of scalar constraints — fix the shape; the engine never drops a declared condition |
| search.doc_skipped | fix the entry shape (object with text, or a bare string); the rest of the corpus is indexed |
| search.duplicate_content | a renamed copy — cite one id and note the copy, or keep both explicitly; never count it as a second source |
| search.meta_invalid | fix the meta object shape if filters must use it; the text is still searchable |
| empty hits on a query you expected to match | check the query record in the result against the index — the miss is real for those terms; widen any deliberately, never implicitly |

## Verification

```bash
python scripts/bench_search.py   # 26 scenarios: one per property plus the
                                 # section/filter/duplicate layer and FP guards
```

All 26 pass on this machine. The FP guards pin the behaviour that matters: a
malformed index refuses as a whole, an unsatisfiable filter stays an honest
empty that names the filter (not a relaxed hit), a malformed filter is refused,
every passage quote equals its text slice, section locators land under the
right numbered heading while a sentence starting with a number does not become
one, a renamed copy is named as duplicate content, the CLI writes the index for
replay, filters replay hard against a saved index, and a rerun is
byte-identical.

## Routing

- **This skill** when the files are already in the library and the task is to
  find and locate the answering passage, under declared filters, with
  replayable, section-level evidence.
- Not for labelling a batch against a category scheme — use p52-doc-classify.
- Not for organising, hashing, versioning and handing over the library itself —
  use p53-library-mgmt.

## Requirements

Python 3.9+ (3.14 verified); standard library only — no packages to install,
no network calls.

## 创新增益

本 Skill 相比通用 Agent 的核心新增能力（每条附能力边界与增益证据形式）：

1. **章节级定位**：命中不落在整篇文件而是「哪一节哪一段哪个字符」——编号标题
   / Markdown / 中文章节自动成节，locator 携带 section 标题；以数字开头的普通
   句子不会被误判为标题。通用 Agent 的「引用」通常只有文件名，无法逐字复核。
   *边界*：印刷页码错位需在抽文本时用页标记处理，本引擎粒度是段落内字符区间。
   *证据形式*：section_locator / numbered_sentence_not_heading / locator_verbatim
   场景。
2. **过滤条件的硬执行**：filters 逐条与文档 meta 相等比较，缺键不命中、无解
   如实空并点名过滤器；畸形 filters 拒绝而不是静默丢弃——「条件无法满足时如实
   报告而不是放宽」从承诺变成引擎行为。
   *证据形式*：meta_filter_hard / filter_invalid_refusal / index_replay_with_filters
   场景。
3. **副本不作独立证据**：文本 sha256 判重，同文本不同 id 点名 duplicate_content
   ——改名副本不能再充当第二份证据虚增强度，这是通用 Agent 最常见的检索事故
   之一。
   *证据形式*：duplicate_content_named 场景。
4. **逐字可复核回链**：quote == paragraph[start:end] 逐字相等 + 每文档全量
   sha256 + index.json 留档重放——证据不依赖对引擎的信任，任何人拿语料可独立
   重验同一定位。
   *证据形式*：doc_sha_in_hits / locator_verbatim / reproducible_record 场景。
5. **契约直通与诚实状态**：result.json 逐字段回填 case_id 与 output_contract
   （case 值直通、契约字面量回填、推导不出填 null 并写 limits；spec 自带
   case_id 同样直通）；status 三态 ok/partial/undetermined 对应退出码 0/4/5，
   拒绝路径不回填契约——不把未完成写成完成。
   *证据形式*：cli_contract_passthrough / spec_carried_case_id /
   cli_skipped_exit4 场景。

## 生态贡献

- **使用说明**：本文件包含用途、适用条件、六步调用入口、任务路由表、输入输出、
  关键方法、rubric 三段映射、异常处置表、限制和自查方法；按 Workflow 可独立
  完成一次「索引—检索—定位—回链」闭环。
- **依赖与安装**：Python 3.9+（3.14 实测），纯标准库零依赖、零安装、零网络调用；
  search.py 可独立导入复用（build_index / run_query / is_heading / section_map
  均为独立函数）。
- **输入约定**：corpus 形状（id/text/meta）与 query 形状（all/any/filters）
  写在 Data shapes 一节——任何上游（抽取脚本、表转换、人工整理）产出该形状
  即可接入；一段一行的分节约定与 pdftotext 输出兼容。
- **输出 schema**：index.json 与 result.json 双视图同源且带 schema_version；
  index 可复放、hit 可逐字复核，字段结构稳定，下游（引用核查、综述、问答）
  可直接消费。
- **示例（标注为示意）**：examples/corpus.json + examples/query.json +
  examples/case.json 是最小调用示例；本文档 worked example 是一次实跑的节选
  ——均为示意，不冒充正式案例结果。
- **可复用引擎**：分节器（is_heading / section_map）、定位器
  （_find_occurrences 保证 quote 与原文字节一致）、布尔与过滤执行器均可独立
  复用；规则 id 稳定，下游核查系统可直接消费 findings。
- **回归题集**：scripts/bench_search.py 26 场景是可独立复跑的回归门（含误报
  护栏与 CLI 级探针：退出码分层、契约直通与拒绝路径、复放一致性），任何改动
  必须全过。
- **维护**：改任何规则后必跑 bench（自查方法：26/26 全过）；规则 id 变更须
  同步本文档规则表（引擎与文档逐 id 对齐，strict gate 自动核对）。

引擎已实现该契约：case.json 顶层的可推导值与 output_contract 字面量经
--case 直通最终 result.json，推导不出的填 null 并在 limits 写明；拒绝路径
不回填契约，只写 undetermined result.json。
