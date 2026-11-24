---
name: search-academic
description: >
  学术文献检索 v2：在实际提供的 Crossref、OpenAlex、Europe PMC、JSON/JSONL、CSV、RIS、TXT/MD
  科学记录上做可复现的多轮检索。把科研问题拆成概念组，显式保存同义词、跨语言映射、待核验受控词、
  Boolean、字段和时间/语言边界，生成真实 OpenAlex/Crossref/Europe PMC 请求计划；本地快照以
  字段加权 BM25 排序，逐命中保留可切片证据。DOI/题名去重与预印本/正式版冲突留痕，相关性、
  元数据完整性、来源可追溯性分开。无结果、权限受限、错误查询和未知 output_contract 字段均结构化处理。
  不把离线样例说成数据库命中。适用于固定导出检索与查询规划；不用于宣称已执行实时联网、
  全球覆盖/最新性、全文质量评价，或补造 DOI、摘要、收录数和作者。
---

# 学术文献检索：查到的是供入记录，查到过程可重放

## 1. 正式运行入口和边界

正式入口是 **scripts/academic_cli.py + academic_engine.py + retrieval_common.py**。旧
search_cli.py/search.py 仅保留旧 `{all, any}` 词项探针兼容，不是本题主检索器。

在平台安装后的运行路径：

```bash
python -I -X utf8 /skills/weekly-skill/scripts/academic_cli.py \
  --case /input/case.json --out /app/output
```


本包示例的本地等价命令（从包根运行）：

```bash
python -I -X utf8 scripts/academic_cli.py --case examples/case.json --out ./_run_example
```


纯 Python 3.9+ 标准库，离线、无安装步骤。程序先写诚实的早期 partial，再覆盖为实际结果；
没有网络调用，不写墙钟时间、随机数、虚构工具调用时延或平台分数。

**PDF 不在这个 CLI 的输入格式内。** 若材料是 PDF，先用平台实际 PDF/OCR 工具生成带来源的
JSON/TXT，再交给本 Skill。不得把 PDF 二进制或文件名当作已检索正文。

## 2. 运行时六步

1. **读原始 case。** 读取 /input/case.json、task.md 和声明材料，保留原始 case_id 与
   `output_contract`；嵌套 `spec` 与顶层字段合并时，原 case 的身份和契约不被覆盖。
2. **冻结范围。** 从 research_question/question/query/concepts 确定主题、同义词、翻译、
   上下位概念的显式输入、`controlled_terms`、start_date/end_date、`languages` 与 `top_k`。
   仅有结构化 `{all, any, not}` 时严格按原查询集合执行，绝不再把字段名当自然语言生成宽松 OR 查询。
3. **归一化供入记录。** 支持顶层 documents/records/corpus/studies/papers/works/candidates 内联列表，
   或 case 声明的相对/绝对 JSON、JSONL、CSV、RIS、TXT、MD 材料。支持 Crossref `message` 内的 `items`、
   Crossref 单篇 `message`、Europe PMC `resultList.result`、OpenAlex `results` 与
   `abstract_inverted_index`。路径相对 case，其次 /input。RIS 的常用题名/作者/摘要/DOI/年字段可读取。
4. **去重、执行、扩展。** 先保留每条导出的 `(dataset_id,dataset_row)`，再按规范 DOI 或规范题名聚成
   work_id/group_id。同 DOI/同年同题名为重复或版本候选；同题名不同 DOI/年份，或预印本与正式版
   混合，进入冲突复核而非静默算两篇。R00 执行每个实际供入 query；自然语言检索依次执行 R01 原问题
   词面探针、R02 显式同义词/跨语言展开、R03 未覆盖概念诊断。
5. **字段加权排序。** 硬性日期/语言/all/any/not 条件先于排序。仅给真实匹配项计算 BM25，输出每个
   查询贡献、字段贡献、相关概念、原始导出成员和 `fields.<field>[start:end] == quote` 的证据切片。
6. **保存并审阅结果。** 检查 `candidate_set_summary`、空查询、缺失元数据、版本冲突、权限异常、
   未执行远程计划和所有 output_contract 字段。正常和拒绝路径都写 /app/output/result.json，
   不用 traceback 充当结果，也不会把失败改写成 clean。

## 3. 查询构造是真实代码，不是链接清单

`retrieval_common.py` 生成三个来源的可重放请求参数和 URL，并明确标记：

```json
{"execution_status":"planned_not_executed", "remote_hit_count":null}
```


| 来源 | 实际实现 | 特别边界 |
|-|-|-|
| OpenAlex | `search` 中概念组内 OR、组间 AND；`filter` 含 from_publication_date/to_publication_date/language；`select`、`per-page=200`、`cursor=*` | `|` 是同字段 OR，参考 PyAlex `_flatten_kv`；未实际分页或取回响应 |
| Crossref | `query.bibliographic` + from-pub-date/until-pub-date filters、`select`、`rows=100`、`cursor=*` | 不谎称 Crossref 支持本包的全部本地 Boolean 文法 |
| Europe PMC | `TITLE_ABS:(...) AND ...`、`FIRST_PDATE:[start TO end]`、`format=json`、`pageSize=100`、`cursorMark=*` | 候选 MeSH 不混入已执行查询；需先核验受控词 |

本地查询日志另行记录 execution_status=fixed_snapshot_scanned、概念 Boolean、字段、时间/语言、
local_snapshot_hit_count/local_snapshot_hit_work_ids、逐条边界排除理由，以及
`source_queries[*].remote_hit_count=null`。供入响应中的 `source_hit_count` 可原样留作来源字段，
不会被当成本次远程命中量。

### 关键词和受控词

小型的 SEED_GROUPS 只覆盖若干常见科研概念（蛋白质结构预测/注意力、固态电解质/晶界/离子电导、
增材制造/微观组织、随机试验/慢性疼痛/运动疗法等），其来源明确写 declared_seed_lexicon。专业问题
应在 case 中提供自己的 `concepts`：

```json
{"concepts":[
  {"id":"object","label":"固态电解质","role":"object",
   "terms":["固态电解质","固体电解质"],
   "synonyms":["solid electrolyte","solid-state electrolyte"],
   "controlled_terms":[{"vocabulary":"example vocabulary","term":"case declared term"}],
   "required":true}
]}
```


mapping 含 candidate/verify/unverified 的受控词只进入
controlled_vocabulary_pending_review，**不会执行**。没有受控词的空列表不是错误，也不暗示
OpenAlex/Crossref 有 MeSH。中文长句的词面基线采用披露过的 CJK bigram 回退，不等同于分词或语义翻译。

## 4. 排序、去重和证据如何复核

每个 work 的字段为 title/abstract/keywords/body。BM25 使用 k1=1.2, b=0.75，字段权重依次
4/2/2.5/1，IDF 为 log(1+(N-df+0.5)/(df+0.5))；`bm25` 是各命中项贡献之和，
normalized_relevance = bm25/(bm25+4)，不是概率或论文质量分。

- relevance：实际匹配词、概念、BM25/字段/词项分数及证据；纯词面相关性。
- metadata_completeness：题名、作者、年、期刊、DOI、摘要六项存在性比例与缺失清单；存在不等于事实核验。
- source_quality：提供的来源响应/注册元数据可追溯性启发分，**不是研究质量、同行评议或期刊声望分**。
- dedup_audit：每条原始行的 record_id/dataset_id/dataset_row、work_id/group_id、
  `duplicate_of` 与原始行是否独立证据。主记录只是排序展示，不删除其他导出。
- `evidence`：字段、精确字符起止、quote 与 dataset locator；中文与英文都能检查。未解析 locator 会引发高等级发现，而不是补一个引文。

紧邻命中词的 不是/并非/不属于/not a/no/off-scope 等范围否定不会算作正向命中或增加 tf。
遇到“先否定、后在别处正向研究同一术语”则引用正向出现位置。它不理解所有复杂句法，也不把阴性
医学结论一律当作离题。

## 5. 输出文件与 rubric 三段

| 文件 | 内容 |
|-|-|
| `result.json` | `case_id`、完整契约字段、候选、查询、评分、去重、冲突、findings、状态与产物 SHA-256 |
| query_plan.json | 问题概念、同义词/翻译/受控词、时间范围、三类 API 请求计划、停止理由 |
| query_log.json / query_log.csv | 每轮原始/归一化查询、执行状态、真实本地命中、远程 null、空结果与边界排除 |
| candidate_set.json / candidate_set.csv | 去重候选、元数据、来源、三维分数、top-k 和逐字段证据 |
| `dedup_audit.csv` | 全原始导出与 duplicate_of/group_id 去向 |
| `retrieval_report.md` | 固定快照查询、候选、空结果、冲突与限制的可读报告 |

| rubric 原词 | 结构落点 |
|-|-|
| `检索结果` | `候选文献`、排序/筛选结果、`元数据`、`来源定位`、`遗漏说明` |
| `证据记录` | `query_plan`、`query_log`、`dedup_audit`、`evidence_ledger` 和可复算 BM25 口径 |
| `状态说明` | 运行状态、已完成本地 query、尚未执行远程计划、空结果、冲突、权限或接口异常、不确定性 |

正常与拒绝结果都尽量保留读取成功的原 `case_id`。`output_contract` 支持字符串、字典、字符串列表、
field/name/key 对象列表；原对象在 `output_contract` 回显，字段名在 `output_contract_fields`。
每个字段遵守 **引擎值 > 原 case 显式来源值（非 bulky）> null + limits**，案例自报的 status 不覆盖真实执行状态。

## 6. 状态、退出码与异常

| status | exit | 定义 |
|-|-|-|
| clean | 0 | 所有计划内本地查询运行，未决发现为零；仍不证明全球覆盖 |
| review | 3 | 有用输出但需复核：空结果、候选元数据缺失、来源/版本冲突、权限、空查询分支或未知契约字段 |
| blocked | 4 | case/记录形态错误、无候选、无可执行 query、非法负 top-k、非法时间/语言/查询结构等调用层阻断 |
| undetermined | 5 | case/材料不可读、PDF 未抽取、输入不支持或内部异常；真实结构化错误写入 result.json |
| argparse usage | 2 | 缺 --case/--out 等命令行错误；argparse 自然输出 usage，不伪装为学术结果 |

`空结果` 是范围受限的正常检索状态，与 blocked/undetermined 分开。空分支保留精确 query、下一
可执行计划和“仅固定快照未命中”说明，不以假文献补齐。远程未执行统一是 null，不是 0。

## 7. 最小示例（示意运行，不是组织方案例）

examples/case.json + records.json 含三行导出：两份相同 AlphaFold 公共 Crossref 元数据和一份
“Attention Is All You Need”的公共 DataCite 元数据。AlphaFold DOI 10.1038/s41586-021-03819-2
经 Crossref 核验；arXiv DOI 10.48550/arXiv.1706.03762 经注册机构区分为 DataCite 而非 Crossref。
示例 Orchestration 是合成的，不是正式 3 case；AlphaFold 作者只保留示例明确列出的节选，不称全量。

本次实测示意：中文问题“蛋白质结构预测中，Transformer 与注意力机制有哪些应用？”的
QBASE=0、QEXP=2，三行导出形成两个 work；DataCite 行未提供摘要/期刊，结果和示例中故意留下的
未知契约字段都如实进入 review/null。旧 examples/corpus.json 全部是合成 record-token。
**不是 DOI**。不得把任何示例计数写成正式数据库命中量或全球 Recall@k。

## 8. 真实参考落地与局限

- **PyAlex/OpenAlex**（pyalex/api.py 的 or_、_flatten_kv、_url_query、Paginator、
  `invert_abstract`）：落实过滤值 OR、游标与倒排摘要恢复；本包没有复制其 requests 代码，也不联网。
- **Elasticsearch MatchQueryBuilder**（官方 server/.../MatchQueryBuilder.java）：落实逐字段 query、
  operator/analyzer 配置和“字段必须有值”的错误边界；本包独立实现 BM25，不声称 Elastic 分布式索引、
  模糊扩展或 Lucene 语义。
- **ASReview**：`Record` 保留原始 dataset_id/dataset_row、DOI/年/题名、duplicate_of/group_id；
  Simulate 决策历史含 record、label、classifier、querier、feature extractor、training set、note 和 user。
  本包落实来源行/版本组审计；没有训练 ASReview 模型或宣称学习语义。
- **本地高分包方法**：借鉴 p54 的字段加权 BM25、p67 的冻结查询协议与严格契约、p60 的证据/复核台账；
  三份目标包各自内置实现，没有改其他包的共享 search.py。

主要局限：词面扩展会漏未声明 paraphrase；任何本地 empty 不是全球研究空白；DOI 规范化和语法检查
不证明 DOI 注册、当前可访问、没有撤稿或版本关系已核实；不抓实时引用数、全文或收录总量；不宣称
Precision@k、nDCG@k、Recall@k 和提升百分比，除非有独立人工标注与同预算公平对照。

## 9. 规则与异常索引（逐项可核）

| 规则 ID | 触发与状态含义 |
|-|-|
| `retrieval.case_unreadable`、`retrieval.case_not_object` | case 不可读或非对象；exit 5 / 4，保留可读身份和契约 |
| `retrieval.no_documents`、`retrieval.records_invalid`、`retrieval.record_invalid` | 空记录、records 非列表或单条记录类型不支持；不检索猜测索引 |
| `retrieval.material_missing`、`retrieval.material_shape`、`retrieval.material_unreadable`、`retrieval.material_unsupported` | 材料缺失、形状错误、不可读或 PDF/格式不支持 |
| `retrieval.invalid_temporal_boundary`、`retrieval.invalid_language_boundary` | 非法时间/语言值；exit 4，不静默丢弃边界 |
| `retrieval.contract_field_missing` | 契约字段不可推导；null 加 limits，进入 review |
| `academic.query_missing`、`academic.query_not_executable`、`academic.top_k_invalid` | 缺少可执行查询、查询无有效词或 top-k 非法 |
| `academic.metadata_incomplete`、`academic.doi_syntax_invalid` | 元数据缺项或 DOI 语法错误；不补造、不用于注册背书 |
| `academic.source_version_conflict`、`academic.access_blocked` | 版本/来源冲突，或权限限制 |
| `academic.evidence_locator_unresolved` | 分数对应原句无法定位；高等级发现，不伪造 quote |
| `academic.empty_result` | 固定快照没有最终候选；远程计数仍为 null |
| `academic.run_in_progress`、`academic.internal_error` | 早期 partial 标识或封装意外异常 |
| `search.spec_unreadable`、`search.spec_not_object`、`search.empty_corpus` | 旧兼容入口的输入拒绝 |
| `search.empty_query`、`search.index_malformed`、`search.doc_skipped`、`search.engine_error` | 旧兼容入口的空查询、索引异常、重复导出和封装错误 |
| `query.bibliographic` | Crossref 请求参数名，不是 finding rule；只用于明确标注的未执行 plan |
| `socket.connect` | 测试 audit hook 事件名，用于证明 CLI 不联网，不是线上错误 |
| `fixture.ris` | RIS 适配测试合成夹具文件名，不是 finding rule 或真实文献 |

## 10. 可选作者自查（不是运行时必需步骤）

```bash
python -B -I -X utf8 scripts/bench_academic.py        # 旧兼容 8/8
python -B -I -X utf8 scripts/bench_academic_v2.py     # v2 21/21，含 clean 零发现基线
python -B -I -X utf8 scripts/probe_academic_v2.py     # 敌意/契约/退出码/幂等 22/22
python -B -I -X utf8 scripts/smoke_academic_v2.py     # 冷复制/中文/跨语言/确定性 7/7
```

对应 `report_*.json` 为本次真实回归报告。测试只用公开真实 DOI 元数据和明示合成、无 DOI 的夹具；
不是正式测试成绩或预写答案。
