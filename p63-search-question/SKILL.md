---
name: search-question
description: >
  科研问题驱动检索 v2：把对象、机制、方法、结局、时间和证据要求拆成有依赖关系的可检索子问题，
  保留同义词、缩写、跨语言映射、受控词候选与中英文 Boolean/字段检索式。先按依赖拓扑执行原始联合
  查询，未回答子问题才做诊断性分面迭代；单面命中绝不冒充联合答案，空结果只限固定快照。跨库请求
  计划可复现且 remote_hit_count 恒为 null（本工具不联网）。保留逐篇证据、BM25、版本去重、显式
  冲突、人工复核与停止理由；严格 case_id/output_contract 直通和正确退出码。Use for complex
  question decomposition and replayable fixed-corpus retrieval, not open-ended scientific QA,
  global research-gap proof, full-text interpretation, or fabricated query/database results.
---

# 科研问题驱动检索：不是“一轮关键词打天下”

## 1. 正式入口与运行时流程

正式入口为 **scripts/question_cli.py + question_engine.py + retrieval_common.py**，不依赖旧
`search_cli.py`。旧包仅保留兼容布尔探针，不负责问题分解。

```bash
python -I -X utf8 /skills/weekly-skill/scripts/question_cli.py \
  --case /input/case.json --out /app/output
```


本地等价命令（从包根目录）：

```bash
python -I -X utf8 scripts/question_cli.py --case examples/case.json --out ./_run_example
```


1. 读取原始 case/task 及授权材料，冻结 case_id`、`output_contract、时间/语言边界和概念映射。
2. 生成或读取子问题，校验唯一 ID、未知依赖、自依赖和依赖环；输出 scheduling_plan，实际查询按
   拓扑 ready set 重放，而不是仅画依赖图或伪报并行时延。
3. 为每个子问题冻结对象/人群范围、机制/方法/结局概念和原始 query。自动拆解时，共享对象/人群
   与非对象 facet 形成 对象 AND facet；显式 query 优先，不把查询语法再当自然语言扩张。
4. R01 执行原联合 query。只有联合执行没有直接证据，且子问题不是显式冻结查询时，R02 才逐 facet
   诊断哪一面缺失。R02 命中恒标 `diagnostic_partial_only=true`，不进入该子问题直接答案。
5. 合并每个子问题的直接证据，报告字段加权 BM25、概念命中、精确 quote、版本去重、元数据缺失及
   可比较证据冲突。只在同 comparison_key、明确 conflicting_opinion 或同 study_id 的记录之间
   判定语义立场冲突；两篇论文 wording 不同不等于矛盾。
6. 写入全部产物。所有子问题直接回答则按固定快照停止；有空缺或冲突则记录 bounded stop/human review。
   未执行的 OpenAlex/Crossref/Europe PMC 计划不会进入“已完成”。

程序先写早期 partial，纯 Python 3.9+ 标准库，无网络、随机数或墙钟字段。查询 URL 是计划，不是实际服务调用。

## 2. 实际材料与查询输入

内联 documents/records/corpus/studies/papers/works/candidates 均可。材料路径支持 JSON、JSONL、CSV、
RIS、TXT、MD；可识别 Crossref message/message.items、Europe PMC `resultList.result`、OpenAlex
results/abstract_inverted_index 及常用 authorship/journal/date 字段。没有摘要、期刊、DOI 或语言时
保持 null/缺失，不根据标题或领域标签补造。

PDF 必须先用平台真实 PDF/OCR 文本工具转成 JSON/TXT；本 CLI 不读 PDF，也不会把文件名当摘要。

research_question/subquestions/research_questions/question_plan.subquestions 均可声明子问题。
推荐复杂主题在 case 中明确冻结：

```json
{"research_question":"固态电解质中晶界如何影响电导率？",
 "concepts":[
  {"id":"object","label":"固态电解质","role":"object",
   "terms":["固态电解质","固体电解质"],
   "synonyms":["solid electrolyte","solid-state electrolyte"],"required":true},
  {"id":"grain","label":"晶界","role":"mechanism",
   "terms":["晶界"],"synonyms":["grain boundary","grain-boundary"],"required":true}
 ]}
```


显式多查询和依赖也可直接给出：

```json
{"subquestions":[
  {"id":"S1","question":"界面表征证据","query":{"all":["solid electrolyte","impedance"]}},
  {"id":"S2","question":"联合机制证据","depends_on":["S1"],
   "query":{"all":["solid electrolyte"],"any":["grain boundary","interfacial resistance"],"not":["polymer"]}}
]}
```


`all` 的每一项是必需概念组；`any` 是组内替代；`not` 硬排除。不要把 prose 的 and/or/not 字符串
当作已解析 AST。这些结构由真实引擎转换执行并记录。

## 3. 多轮收敛和停止条件

### 覆盖判据

- `answered`：原始联合查询有直接证据，不是任一 keyword 偶然出现。
- `answered_with_conflicts_human_review`：有直接证据，但明确可比较立场或版本元数据冲突未决。
- `bounded_gap_partial_facets_only`：联合查询为空，但 R02 某些单面有诊断命中；仍然不是联合回答。
- `bounded_gap_in_supplied_snapshot`：原联合查询与允许的诊断都无支持，结论仅限所给查询与语料。

### 停止判据

| 状态 | 条件 |
|-|-|
| `complete_for_this_frozen_snapshot` | 每个子问题都有直接联合证据；仍不表示全球覆盖 |
| bounded_local_stop_review_required | 已完成全部冻结查询与必要单面诊断，仍有固定范围空缺；转人工审查/执行计划，不继续无意义放宽 |
| stop_for_human_adjudication | 全部冻结查询完成，但声明立场或来源/版本冲突需要复核，不能多数票裁决 |

“没有发现”永远保存查询 ID、对象范围、字段、边界和远程 null，而不是全球 research-gap 证据。
若需要新同义词或真实数据库接入，必须形成新版本 query/plan；不把未执行计划算作本轮完成。

## 4. 查询、排序和证据的可复算性

每个子问题的 query_log 包含：

- 原始 concepts、同义词/翻译、受控词候选及标记来源；
- between_concepts=AND/OR、within_concept=OR、NOT 和 promotion rule；
- 检索字段 title/abstract/keywords/body、时间/语言边界与 snapshot date；
- OpenAlex search/filter/select/cursor/per-page、Crossref query.bibliographic/filter/select/rows/cursor、
  Europe PMC TITLE_ABS/FIRST_PDATE/format/pageSize/cursorMark 计划；
- 本地真实 local_snapshot_hit_count/work_ids、逐条边界排除、空结果处理及 `remote_hit_count=null`。

本地排序独立实现 BM25：`k1=1.2,b=0.75，title/abstract/keywords/body 权重 4/2/2.5/1`，
normalized_relevance=bm25/(bm25+4)。它只表达词面相关性，不是科研质量或真值概率。元数据完整性、
来源可追溯性和重复版本单独保留，不能用来源级别替代子问题相关性。

每个直接证据保留 fields.<field>、原始 dataset row、start/end/quote，必须满足
quote == fields.<field>[start:end]。紧邻的“不是固态电解质证据/not an additive manufacturing study”
等范围否定不会正向命中；不同字段的命中单独定位，未命中字段不会生成伪 quote。

去重按规范 DOI/规范题名形成 work_id/group_id，所有原始导出留在 dedup_audit，
duplicate_of 的次导出不重新算独立证据。预印本/正式版或来源值冲突升级复核，不自动删除。

## 5. 输出文件与 contract

| 文件 | 实际内容 |
|-|-|
| result.json | case 身份/契约、拆解、子问题答案/gap、查询与证据、停止、冲突、限制、产物 SHA-256 |
| question_plan.json | 子问题、依赖、ready sets、概念、停止规则、受控词说明 |
| `query_log.json / query_log.csv` | 实际每轮查询、原查询状态、真实本地命中、远程计划与 null |
| question_evidence.csv | 子问题—文献—相关性—字段—逐字 quote—冲突—元数据/来源逐行对应 |
| question_report.md | 子问题覆盖、直接证据与诊断证据分离、轮次和停止理由 |

rubric 三段映射：
- `检索结果`：候选文献、逐子问题状态、metadata、source locators 与未覆盖项。
- `证据记录`：冻结拆解、查询、`subquestion_results`、去重、逐字 evidence 与停止理由。
- 状态说明：执行状态、已完成本地查询、未回答/未决分支、空结果、冲突、权限/接口与不确定性。

case_id 在顶层。output_contract 支持字符串、字典、字符串列表及 field/name/key 对象列表；
原契约和 output_contract_fields 均保留。每个字段按 **引擎值 > case 显式非 bulky 来源值 > null+limits**
回填，案例自报 status 不可覆盖执行状态；拒绝路径也执行同一规则。

## 6. 状态与退出码

| status | exit | 说明 |
|-|-|-|
| clean | 0 | 所有子问题有直接证据且无未决发现；仍只限快照 |
| review | 3 | bounded gap、只有诊断线索、冲突、元数据缺失、权限或未识别契约字段 |
| blocked | 4 | 无子问题、空冻结查询、依赖环/未知依赖/重复 ID、非法输入/边界等 |
| undetermined | 5 | case/材料不可读、PDF 未抽取、格式不支持或内部异常 |
| usage | 2 | argparse 命令行用法错误 |

预期科学错误均写结构化 result.json，不泄漏 traceback。空命中与无法运行严格分开；
status=undetermined/blocked 不误写“正常空结果”。

## 7. 最小完整示例（合成流程，不是正式 case 或真实文献结果）

examples/case.json + records.json 有六条明确标注的合成导出和一次重复导出，研究范围同时给出
固态电解质、晶界、离子电导率、阻抗谱、界面电阻和分子动力学模拟的中英文概念。

实际本地运行示意结果：

- zh-grain-01 同时支持晶界、离子电导率、阻抗谱等不同子问题；
- 液态/聚合物材料句子中虽出现模拟术语，但因对象范围或否定不进入固态电解质直接答案；
- 分子模拟子问题为 bounded_gap_partial_facets_only，液态/聚合物单面命中只留诊断；
- 明确 conflicting_opinion=true 的两个合成立场进入复核，普通不同 stance 不误报冲突；
- 六行原始导出形成五个去重 work，所有无 DOI/期刊字段保持缺失，示例整体为 review，不伪称 clean。

examples/public_real_records.json 只供 clean 基线，包含实际 Crossref/DataCite 已核元数据；
不是本题正式 9 篇文献，也不是组织方白板或现场数据库响应。

## 8. 参考落地与限制

- PyAlex or_/_flatten_kv/_url_query/Paginator/invert_abstract → 查询分隔、游标计划、OpenAlex 倒排摘要恢复。
- Elasticsearch MatchQueryBuilder → 字段 query、analyzer/operator 和“缺失 field/value 必须拒绝”接口边界；
  本包独立实现字段 BM25，不声称 Lucene/Elastic 的全部功能。
- ASReview Record(duplicate_of/group_id,dataset_id/dataset_row) 与决策历史 → 重复导出、原始行留痕；
  本包不训练模型、不冒充 ASReview 学习排序。
- 本地 p54/p67/p60 → 字段 BM25、冻结协议与证据/复核契约；只在本目标包内置实现，不改共享 search 引擎。

主要局限：复杂拆解与扩词是确定性规则，不是语义理解器；小型 seed 词典不覆盖全学科，专业主题应显式
提供 concepts/subquestions；R02 不提供联合证据的替代证明；同义词/受控词候选不代表 MeSH 已映射；
不联网、不验证实时 DOI/撤稿/全文状态、不声称全球新颖性或 Recall@k；冲突处理只比较声明可比较记录，
不自动裁定哪个科学观点正确。

## 9. 规则与异常索引（逐项可核）

| 规则 ID | 触发与状态含义 |
|-|-|
| `retrieval.case_unreadable`、`retrieval.case_not_object` | case 不可读或非对象；exit 5 / 4，不吞掉身份/契约 |
| `retrieval.no_documents`、`retrieval.records_invalid`、`retrieval.record_invalid` | 空记录、records 非列表或记录类型非法 |
| `retrieval.material_missing`、`retrieval.material_shape`、`retrieval.material_unreadable`、`retrieval.material_unsupported` | 材料缺失、形状错误、不可读或 PDF/格式不支持 |
| `retrieval.invalid_temporal_boundary`、`retrieval.invalid_language_boundary` | 非法边界，不静默过滤删除条件 |
| `retrieval.contract_field_missing` | 契约未知值保持 null 加 limits，并进入 review |
| `question.no_subquestions`、`question.subquery_empty` | 无法拆解、空冻结查询，exit 4 |
| `question.dependency_cycle`、`question.dependency_unknown`、`question.subquestion_id_duplicate` | 依赖环、未知依赖或重复 ID，均 exit 4 |
| `question.only_partial_evidence`、`question.subquestion_unanswered` | 仅有单面诊断或联合问题未回答；进入 bounded-gap review，不伪装直接答案 |
| `question.evidence_conflict`、`question.evidence_metadata_incomplete` | 可比较立场/版本冲突，或直接证据元数据缺项 |
| `question.run_in_progress`、`question.internal_error` | 早期 partial 或封装意外异常；internal_error 为 exit 5 |
| `search.spec_unreadable`、`search.spec_not_object`、`search.empty_corpus` | 旧兼容入口的输入拒绝 |
| `search.empty_query`、`search.index_malformed`、`search.doc_skipped`、`search.engine_error` | 旧兼容入口的空查询、索引异常、重复导出和封装错误 |
| `query.bibliographic` | Crossref 查询参数名，不是 finding rule；只在未执行计划中出现 |
| `socket.connect` | 离线 audit hook 的测试事件名，不是实际网络错误或调用记录 |

## 10. 可选作者自查（非运行时步骤）

```bash
python -B -I -X utf8 scripts/bench_question.py      # 旧兼容 8/8
python -B -I -X utf8 scripts/bench_question_v2.py   # v2 23/23，含 clean 零发现基线
python -B -I -X utf8 scripts/probe_question_v2.py   # 敌意/退出码/契约 23/23
python -B -I -X utf8 scripts/smoke_question_v2.py   # 冷复制/中文/跨语言/确定性 7/7
```

`report_question_v2.json`、`report_question_hostile.json`、`report_question_smoke.json` 为本机真实测试
结果，不是平台分数，也不包含组织方固定案例答案。
