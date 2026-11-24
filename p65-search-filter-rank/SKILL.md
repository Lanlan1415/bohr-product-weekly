---
name: search-filter-rank
description: >
  文献筛选与智能排序 v2：对给定候选集逐条完成标题/摘要级纳排、分层、去重与可解释排序。
  显式 inclusion/exclusion criteria 与派生词面规则严格区分；缺少派生条件只能进入待定，不能以标题
  词面直接误排。输出每条 criterion/字段/quote、直接/间接/不相关标签、include/pending/exclude、
  BM25 相关性、标准覆盖、元数据完整性、来源可追溯性和完整加权分数。处理 DOI/题名重复、预印本正式版、
  规范冲突、同分/近同分、置信阈值与真实人工复核；没有 reviewer+rationale 就不会记成人工完成。
  借鉴 ASReview 原始行、duplicate_of/group_id 和决策历史，保证全记录计数闭合。Use for deterministic,
  replayable candidate triage, not full-text systematic-review adjudication, learned relevance claims,
  remote database hits or invented metadata/human decisions.
---

# 文献筛选与智能排序：门控先于分数，理由先于顺序

## 1. 正式运行入口

正式入口是 **scripts/screening_cli.py + screening_engine.py + retrieval_common.py**。旧
search_cli.py/search.py 只保留旧 all/any 检索探针，不会自动做本题的完整纳排和排序。

```bash
python -I -X utf8 /skills/weekly-skill/scripts/screening_cli.py \
  --case /input/case.json --out /app/output
```


本地等价命令（从包根目录）：

```bash
python -I -X utf8 scripts/screening_cli.py --case examples/case.json --out ./_run_example
```


纯 Python 3.9+ 标准库，离线、无安装包，先写 partial 再覆盖实际结果。没有联网查询、远程命中数、
随机排序、伪造时间或“已训练智能模型”。实际是透明可复算的规则与 BM25 加权排序。

## 2. 六步运行路径

1. **读取案例和契约。** 固定 case_id/output_contract、候选集、时间/语言边界、纳排标准、权重、k 和复核阈值。
2. **归一化并全量登记。** 支持内联 records/documents/corpus/studies/papers/works/candidates，以及
   JSON/JSONL/CSV/RIS/TXT/MD 材料，兼容 Crossref/OpenAlex/Europe PMC 响应。每个原始导出有
   (dataset_id,dataset_row)；PDF 必须先有平台真实文字/OCR 提取，本 CLI 不伪装读 PDF。
3. **冻结标准并去重。** 解析 include/exclude 条件、字段、all/any、minimum_should_match、required、
   优先级和冲突政策。按规范 DOI/规范题名形成 work_id/group_id，保留所有原始行和 duplicate_of。
4. **逐篇判纳排。** 在声明字段内执行标准。明确排除按冻结优先级处理；include+exclude 冲突可
   exclusion_wins 或 manual_review。标题/摘要/年缺失、访问受限、派生标准缺证据进入 pending，
   不靠猜补齐。输出逐条 reason codes、直接/间接/不相关/未定类别和真实命中 quote。
5. **门控后排序。** 只对 eligibility 排序池计算确定性特征：BM25 词面相关性、必需标准覆盖、元数据完整性、
   来源可追溯性；精确同分按规范题名、DOI、work_id 排列，近同分和低于置信阈值进入人工复核队列。
6. **应用真实复核并闭合。** 仅接受目标存在、reviewer/user_id、rationale/reason/note 和合法决定齐全的
   人工记录。保留原 engine 判定、最终判定、reviewer、理由和 change records；冲突标签没有 adjudicator
   必须 pending。最后校验全部原始 row 都有最终去向，每条重复导出不被算第二次独立证据。

## 3. 筛选协议是可以执行的规则

```json
{"screening_protocol":{
  "criterion_priority":"exclusion_wins",
  "inclusion_criteria":[
    {"id":"INC-OBJECT","description":"研究对象属于增材制造",
     "fields":["title","abstract"],"required":true,
     "terms":["additive manufacturing","3D printing","增材制造"]},
    {"id":"INC-EVIDENCE","description":"有凝固/组织证据",
     "fields":["title","abstract"],
     "any":["cooling rate","solidification","microstructure","凝固","微观组织"]}
  ],
  "exclusion_criteria":[
    {"id":"EX-DESIGN","terms":["not an additive manufacturing study"]}
  ],
  "human_review_thresholds":{"confidence_below":0.70,"tie_margin":2.0}
}}
```


- `terms` 是一个 OR 同义表达组；`all` 产生多个必须满足的组；`any` 是任意一个可命中组；
  `synonyms` 加入现有组；`minimum_should_match` 可指定一个标准至少满足多少组。
- fields 只能是 title/abstract/keywords/body 子集。正文只表示所提供文本，不自动证明是全文。
- 显式标准缺 required 条件，按 explicit protocol 决定排除并给 EX-MISSING + criterion codes；
  **从自然语言推导的 `DERIVED-*` 词面标准缺证据只会 pending/UNCLEAR**，避免未声明 paraphrase
  导致错误排除。
- 无 title 与 abstract 是 INSUFFICIENT-TEXT，不是无关；缺 year/language 不能满足边界时是
  MISSING-BOUNDARY-METADATA；已知越界是 EX-BOUNDARY。访问受限正文不索引，进入待定。
- criterion_priority=exclusion_wins 明确定义排除优先；manual_review 把同时出现的纳入/排除证据
  转为 CRITERION-CONFLICT，不静默挑一条。

inclusion_criteria/exclusion_criteria/screening_criteria 也能作为输入别名。标准 ID 必须唯一，字段、
minimum_should_match、权重、thresholds 非法会结构化退出 4，不能静默丢掉条件。

## 4. 排序特征、分数和人工复核门槛

### 字段加权 BM25

k1=1.2、 b=0.75、title/abstract/keywords 权重 4/2/2.5；按实际命中项计算字段和词项贡献，
normalized_relevance=bm25/(bm25+4)。范围否定紧邻的“不是/不属于/not a/no/off-scope”不算正向
命中或 tf；其他复杂语言表达仍可能误判，需要读 quote。

### 默认加权总分（可配置）

```text
priority_score = 100 * (
    0.70 * normalized_relevance
  + 0.20 * required_criteria_coverage
  + 0.05 * metadata_completeness
  + 0.05 * source_trace_quality
)
```


权重必须非负且总和为 1。保存 score_components、weighted_components、priority_score、
BM25、matched_terms、field_components 以及 criteria matches，任何一项都可独立复算。

**门控与分数分离：**明确排除不会因词面丰富或来源更好而进入保留区；metadata completeness 不等于
元数据事实正确；source trace 不等于同行评议/研究质量；priority 不是校准概率、学习模型或科学价值判断。

### 决策置信度与复核规则（确定性启发规则，非统计置信区间）

- 完全匹配 include 初始 0.95，pending 初始 0.60，exclude 初始 0.90；
- 无 abstract 上限 0.55，缺 required 上限 0.55，版本/来源冲突上限 0.35，纳排冲突上限 0.30；
- 低于 confidence_below（默认 0.70）、pending、版本冲突、title/abstract/year 缺项，或相邻排序差
  <= tie_margin`（默认 2.0），进入 `review_queue；
- exclude 的缺文本/近同分等复核情况也不删除原排除记录；真实人工决定后不抹掉自动历史；
- 同分以规范题名、DOI、work_id 固定顺序。稳定 tie-break 不代表语义优劣，近同分仍保留复核。

include/pending/exclude` 三个层各自编号，`top_k 只作用于最终 include 层；pending/exclude 不算入 k。
如果没有保留项，状态是 review，完整展示排除和待定，而不是返回零个候选装成功。

## 5. 人工复核与 ASReview 风格历史

``json
{"review_decisions":[
  {"record_id":"candidate-or-duplicate-export-id",
   "decision":"include","reviewer":"reviewer-B",
   "rationale":"按冻结 INC-OBJECT 与摘要证据复核","time":"2026-11-24T00:00:00Z"}
]}


合法决定为 include/pending/exclude 及常见中英别名。目标可为原 record_id 或 work_id；
**重复次导出 record_id 也通过 duplicate_of/group_id 定位**，历史保留被标的原始 record_id。
只有合法目标、reviewer、理由、决定齐全才改变 final_decision，其他一律发现而不应用。

每次有效记录保存：

``json
{"record_id":"...","work_id":"...","label":1,
 "classifier":"fielded-bm25-protocol-v2",
 "querier":"confidence_threshold_plus_tie_margin",
 "feature_extractor":"title_abstract_keywords_bm25_and_criteria",
 "training_set":null,"time":"仅为输入提供的真实时间或 null",
 "note":"真实理由","user_id":"reviewer-B"}


同工作组相反票保持 pending；只有带 `adjudication:true` 或 `role:adjudicator` 的合法决定及理由才作
真实声明的裁决。`review_resolution` 区分 consistent human review、adjudicated、unresolved conflict。
普通记录里的 decision/included 不是足够的人工证据，不会自动生成 human history。

## 6. 输出文件、计数闭合与 contract

| 文件 | 内容 |
|-|-|
| result.json | case/契约、所有作品组决定、分层排序、原始行日志、特征、队列、复核历史、冲突、状态与 SHA-256 |
| screening_protocol.json | 纳排条件、字段、Boolean、优先级、权重、阈值、去重和时间/语言范围 |
| screened_records.json | 每条的 criteria/evidence、engine/final、维度分数、rank/top-k、同分和复核信息 |
| screening_log.csv` | 每条原始导出 `(dataset_id,dataset_row)、group/duplicate、最终决定、理由及“非独立证据”标记 |
| ranked_candidates.csv | 三层顺序、k、逐条 criteria、引用、分特征和复核原因 |
| review_queue.csv | pending/低置信/近同分/版本冲突，是否已有合法人工历史、是否仍需解决 |
| screening_report.md | 可读的全集分层、分数、理由和限制 |

rubric 三段：
- 检索结果：全候选、保留/待定/排除、元数据、来源定位和缺失说明。
- 证据记录：冻结协议、原始行日志、逐标准 evidence、排序特征/权重、原始查询与复核历史。
- 状态说明：已完成计数、未完成队列、included-empty、冲突、权限、计数闭合及不确定性。

核心闭合校验：原始 rows == screening_log rows；每个去重 group 恰有唯一 final_decision；
`include + pending + exclude == expected_groups`。任何失败产生高等级 finding，不能漂亮报告掩盖计数断裂。

`output_contract` 支持字符串、字典、字符串列表和 field/name/key 对象列表；顶层保留 case_id、
原 output_contract 与 output_contract_fields。字段优先级 **引擎值 > case 显式非 bulky 来源值 > null+limits**；
拒绝路径同样执行，case 自报 status 不可覆盖真实状态。

## 7. 状态与退出码

| status | exit | 含义 |
|-|-|-|
| clean | 0 | 全部候选已判定，无元数据/冲突/近同分/空保留/未知契约等未决发现 |
| review | 3 | 有待定、复核队列、无保留、版本或冲突、元数据缺失、人工票冲突、未知契约字段 |
| blocked | 4 | 空候选、无协议、非法标准/字段/权重/阈值/负 top-k、case 形态等调用层阻断 |
| undetermined | 5 | case/材料不可读、PDF 未抽取、不支持格式或内部错误 |
| usage | 2 | argparse 缺参等用法错误 |

这些失败都会写 result.json；控制台仅一行 JSON，不打印 traceback。`included_empty=true` 与运行失败
严格分开。`candidate_set_empty` 不用于掩盖空输入；真正的空输入直接 blocked。

## 8. 最小完整示例（九行合成筛选夹具，非正式答案）

examples/case.json + records.json 显式包含九条合成导出：两个相关、两篇版本变体、对象错误、
明确缺证据、范围否定、仅题名和元数据缺失。不是九篇真实文章，不是组织方固定 9 篇材料，没有 DOI/真实摘要或人工复核预填。

本次真实本地 smoke：保留 2、待定 2、排除 4；九行原始导出 → 八个 work/version 组；
词面更高的 conventional casting 仍因缺 INC-OBJECT 排除；版本冲突组 primary 展示正式版但全组待定，
重复行仍完整保留；结果整体 review，无 `human_review_history` 伪造。

examples/public_real_records.json 仅用于 clean 零发现回归。其 AlphaFold DOI 已经 Crossref 核验，
Attention 的 arXiv DOI 已区分为 DataCite；不是本题正式 case 或当前查询命中。

## 9. 方法落地与限制

- **ASReview** 官方 asreview/data/record.py 的原 (dataset_id,dataset_row)、DOI/年/标题、
  duplicate_of/group_id，以及 asreview/simulation/simulate.py 的 label/classifier/querier/training_set/note/user
  决策字段 → 落实到原始行审计、版本组和真实复核历史；没有复制其学习模型或宣称模型训练。
- **Elasticsearch MatchQueryBuilder** 的字段/查询/analyzer/operator 边界 → 独立实现字段化 BM25；
  **PyAlex** 的倒排摘要恢复与过滤构造 → OpenAlex 解析及原始查询保留；没有联网和假分页/命中量。
- 本地 p54/p67/p60 → 字段评分、冻结状态机、证据和复核完整性；本包独立实现，不改共享 search 引擎。

限制：这是标题/摘要/关键词规则排序，不是全文纳排结论或系统综述；非显式同义词和复杂否定可能漏判；
local negative evidence 不能自动证明不相关；元数据缺失不等于事实错误，source trace 不是研究质量；
冲突和近同分仍需领域人员；无已训练模型、远程 DB 查询、全球 Recall/nDCG/Precision 或虚构提升百分比。

## 10. 规则与异常索引（逐项可核）

| 规则 ID | 触发与状态含义 |
|-|-|
| `retrieval.case_unreadable`、`retrieval.case_not_object` | case 不可读或非对象；exit 5 / 4，并保留可读身份/契约 |
| `retrieval.no_documents`、`retrieval.records_invalid`、`retrieval.record_invalid` | 空候选、候选形态或单条记录类型非法 |
| `retrieval.material_missing`、`retrieval.material_shape`、`retrieval.material_unreadable`、`retrieval.material_unsupported` | 材料缺失、形状错误、不可读或 PDF/格式不支持 |
| `retrieval.invalid_temporal_boundary`、`retrieval.invalid_language_boundary` | 非法边界；exit 4，不静默删除 |
| `retrieval.contract_field_missing` | 未知契约字段保持 null 加 limits，status 转 review |
| `screening.protocol_missing`、`screening.criterion_empty`、`screening.criterion_invalid` | 无协议、空标准或标准类型非法 |
| `screening.criterion_id_duplicate`、`screening.criterion_kind_invalid`、`screening.criterion_fields_invalid` | 重复标准 ID、非法纳排类型或字段 |
| `screening.minimum_match_invalid`、`screening.thresholds_invalid`、`screening.rank_weights_invalid` | 非法最小命中数、复核阈值或权重不满足非负且总和 1 |
| `screening.top_k_invalid`、`screening.reviews_invalid`、`screening.review_invalid` | 非法 top-k、复核容器或单条复核缺目标/reviewer/理由/合法决定 |
| `screening.metadata_incomplete`、`screening.evidence_locator_unresolved` | 元数据缺项；或分数/标准证据无法切片，后者为高等级发现 |
| `screening.version_conflict_review`、`screening.human_label_conflict` | 版本元数据冲突或未裁决人工票冲突，均进入 review |
| `screening.review_required`、`screening.no_retained_records` | 低于门槛、近同分或冲突进入复核；无保留项保留全部结果并 review |
| `screening.accounting_broken` | 原始行与筛选日志不闭合，高等级发现 |
| `screening.run_in_progress`、`screening.internal_error` | 早期 partial 或封装意外异常；internal_error 为 exit 5 |
| `search.spec_unreadable`、`search.spec_not_object`、`search.empty_corpus` | 旧兼容入口的输入拒绝 |
| `search.empty_query`、`search.index_malformed`、`search.doc_skipped`、`search.engine_error` | 旧兼容入口的空查询、索引异常、重复导出和封装错误 |
| `query.bibliographic` | Crossref 参数名，不是 finding rule；基础文献接口仅计划/保留来源，不联网 |
| `socket.connect` | 测试 audit hook 的事件名，用于证明不联网，并非实际网络调用 |

## 11. 可选作者自查（非运行时步骤）

```bash
python -B -I -X utf8 scripts/bench_filter_rank.py      # 旧兼容 8/8
python -B -I -X utf8 scripts/bench_filter_rank_v2.py   # v2 31/31，含 clean 零发现基线
python -B -I -X utf8 scripts/probe_filter_rank_v2.py   # 敌意/复核/退出码 26/26
python -B -I -X utf8 scripts/smoke_filter_rank_v2.py   # 冷复制/中文/重复标签/确定性 7/7
```

结果保存在本包相应 `report_*.json`；都是本机独立回归，不是平台分数或预写正式输出。
