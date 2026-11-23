---
name: search-systematic
description: >
  系统性文献检索与纳排筛选：对本地固定题录和实际查询输入，保存数据库/平台/完整检索式/
  字段/时间范围/检索日期/语种限制，执行版本化标准、保守去重与预印本版本归并、题录及全文
  双阶段筛选、真实双人独立判断、第三方分歧仲裁和 PRISMA-style 计数闭合。逐条理由码必须
  指向真实题录或全文字段证据；旧标准版本自动触发重筛，缺 reviewer 或第二意见不能伪造成
  双人完成。适用于可复跑纳排和流程审计；不用于虚构数据库检索、无证据自动排除、全文质量
  评价、数据提取、统计合并或完整系统综述写作。
---

# 系统性文献检索与纳排筛选：每个数字都能沿日志走回去

## 1. 真实交付与核心边界

主入口 `scripts/systematic_cli.py` 对**固定输入**运行完整协议，生成：

- `result.json`：顶层 `case_id`、原 `output_contract` 全字段、检索协议、逐条纳排、证据和运行状态；
- `search_protocol.json`：数据库/平台/原查询式/字段/覆盖窗/检索日期/语种及其他限制，以及去重日志；
- `screening_decisions.jsonl`：每个去重后研究簇一行，分别保留题录和全文阶段意见、machine suggestion、最终判断；
- `flow_audit.json`：识别、去重/版本归并、题录、全文、最终纳入/排除/待定的闭合等式；
- `adjudication_and_agreement.json`：双人一致性、include/exclude 分歧、理由码分歧、仲裁人及版本。

流程可审计不等于流程已完成。`pending` 一直保留到真实 reviewer 作出判断；自动词面建议从不冒充双人筛选。该工具不做实时数据库请求，也不生成缺失的 query、文献或 reviewer。

## 2. 六步运行时入口

### 第一步：读取真实案例并冻结契约

读取 `/input/case.json`、`task.md`、环境资源清单和研究问题。确认 `output_contract`、实际题录、查询日志、标准版本、reviewer 输入与授权全文。工作文件放 `/app/work`，最终结果放 `/app/output`，先保存早期 partial。PDF 必须先用平台 PDF/OCR 工具提取实际文本，不把 PDF 文件名当全文证据。

支持内联 `documents/studies/corpus/records/candidates`，以及包内相对、`/input` 相对或绝对 JSON/JSONL/CSV/TXT/MD 路径。支持 Crossref `message/items/message.items`、Europe PMC `resultList.result`。只用给定有限快照，缺失材料与无结果分别报告。

### 第二步：冻结可复现检索协议

协议位于 `screening_protocol` 或 `protocol`。完整查询至少包括：

```json
{"database":"PubMed","platform":"NCBI",
 "query_string":"(type 2 diabetes[Title/Abstract]) AND (randomized controlled trial[Publication Type])",
 "fields":["Title","Abstract","Publication Type"],
 "coverage_from":"2000-01-01","coverage_to":"2025-01-31",
 "date_searched":"2025-02-01","language_limits":["en","pt"],
 "returned_ids":["rec-001"],"hit_count":1}
```

数据库、完整 query_string、fields、date_searched 缺任一项时进入 review；这些字段描述调用者提供的检索事实，不证明本工具重新访问了数据库。每轮 `returned_ids` 与去重后的 record/工作簇能对接，hit_count 保留原声明而不拿来补造本工具实际扫描条数。

标准中含 `inclusion_criteria` 和/或 `exclusion_criteria`。结构化判据示例：

```json
{"id":"INC-DESIGN","field":"design",
 "any":["randomized controlled trial","randomised controlled trial"],
 "reason_code":"EX-DESIGN"}
```

支持 `any/all/none/equals/exists` 词面规则。同一 `criteria + searches + review_mode` 生成 `protocol_sha256`；若声明了 `criteria_version`，它写入每条票和仲裁。标准变化不能沿用旧票，必须按当前版本重筛。

### 第三步：保守去重，区分记录、版本与研究簇

去重不是删除一行就完事，`search_protocol.deduplication.merge_log` 保留 removed_record_id、kept_record_id、合并键和理由。允许的关系：

1. DOI/PMID 精确一致，且不存在强题名冲突；
2. 显式 `work_id/study_id` 或 `version_of/is-preprint-of` 等作品版本关系；
3. DOI 缺失时，**规范化标题 + 第一作者 + 年份全部一致**。

两个不同 DOI 不会因相似题名合并；同 DOI 但题名大幅冲突的记录保留并触发 `systematic.identifier_conflict`。预印本与正式版标成 `version_linked`，普通副本是 `duplicate_removed`，分别计数。整批以研究簇筛选，避免同一研究被重复独立纳入。

### 第四步：逐条题录/全文判断并绑定原文证据

机器规则只生成 `machine_suggestion`：明确排除标准命中、或结构化纳入字段明确不符时可建议排除；只有所有纳入判据均满足时建议纳入。标题摘要中单纯“没搜到某词”是 `AWAIT-EVIDENCE`，不是 `EX-NOT-RELEVANT`。

人工判断使用真实输入 `reviewer_decisions/annotations/screening_decisions`：

```json
{"record_id":"rec-002","stage":"title_abstract","reviewer":"reviewer-A",
 "criteria_version":"proto-2026-01","decision":"exclude",
 "reason_code":"EX-DESIGN","evidence":["prospective cohort study"]}
```

`stage` 分为 `title_abstract`、`full_text`。reviewer 身份不可缺，排除必须有理由码；声明的 quote 找不到时该票无效并触发 `reviewer_evidence_unverified`。原字段证据使用 `{document_id, unit, source_field, start, end}` 或可核对的结构化 `source_field`；词面 slice 满足 `quote == source_text[start:end]`。全文的最终排除与题录排除分阶段记码。

### 第五步：双人独立分歧、仲裁和流程计数

默认 `dual_independent`。两位真实 reviewer 一致才形成该阶段 consensus；不同意见保留逐人判断，不能多数覆盖或简单平均：

- include vs exclude → `decision_disagreement`，等待具名第三人的 `adjudications`，并保留 decision、reason_code、rationale、criteria_version 和可验证原文证据；
- 同一 exclude 但理由码不同 → `reason_code_disagreement`，双方理由码都保留并 review，不抹平方法争议；
- 只有一个 reviewer → `pending`；只有把 review_mode 明确改为单人才允许单人定稿；
- 未解决分歧或缺第二全文票 → pending，不能算最终纳入/排除。

协议同时计算双人 agreement_rate 和可估计时的 Cohen's kappa；每人记录不足两名 reviewer 时 metric 为 null。多于两名时用排序后的前两名进行描述性统计并明确这一口径，最终决策仍不按多数票。

### 第六步：运行 CLI，闭合计数并按原契约交付

平台标准命令：

```bash
python -I -X utf8 /skills/weekly-skill/scripts/systematic_cli.py \
  --case /input/case.json --out /app/output
```

包内示例（从包根）：

```bash
python -I -X utf8 scripts/systematic_cli.py --case examples/case.json --out ./_run_example
```

独立复算使用：

```text
raw_records = invalid_records_named + duplicates_removed + other_versions_linked + unique_work_clusters
ta screened = ta excluded + advanced_to_full_text + ta pending
full_text assessed = full_text excluded + included + full_text pending
```

这些等式允许 pending 存在并仍能闭合，但 `process_complete=false`、状态为 review。闭合不是把 pending 偷偷塞入 include/exclude。随后核对 case_id、原 output_contract 全字段、所有原证据、去重链和标准版本，再做字节确定性复核。

## 3. 输出契约：rubric 三段逐项对应

| rubric 原词 | result.json 落点 | 核验方式 |
|-|-|-|
| `检索结果` | `候选文献`、`排序/筛选结果`、`纳入文献`、`排除文献`、`待复核`、`元数据`、`来源定位`、`流程计数` | number from record/version logs；每个工作簇恰一行 |
| `证据记录` | `检索协议`、`标准版本`、`去重依据`、`逐条判定`、`双人一致性`、`变更日志`、`复算入口` | 查询字段日期、决策证人、原文 quote、计数等式可重跑 |
| `状态说明` | `运行状态`、`已完成`、`未完成`、`空结果`、`冲突`、`权限或接口异常`、`不确定性` | 材料缺失、旧版本、分歧、待定分别说明 |

并提供 `search_protocol`、`protocol_sha256`、`criteria_version`、`screening_decisions`、`included_records`、`excluded_records`、`pending_records`、`prisma_flow`、`prisma_counts_closed`、`reviewer_agreement`、`evidence_ledger`、`change_records`。支持 output_contract 的字符串、字典、列表与 `{field,name,key}` 对象列表；拒绝路径同样回填，引擎值优先，未知字段为 null+limits，case 不能伪造运行 status。

| status | exit | 含义 |
|-|-|-|
| `clean` | 0 | 流程完成且计数闭合；仅有正常去重/已解决分歧的低级留痕 |
| `review` | 3 | 有待定、旧票、证据不符、协议缺项、记录无效、标识冲突或契约缺口 |
| `undetermined` | 5 | case/协议/材料无法运行，或无记录/无可执行标准 |
| `case_not_object` | 4 | case 不是 JSON 对象 |
| 命令行用法错误 | 2 | argparse 用法错误，不伪造筛选结果 |

## 4. 最小合成示例（非组织方案例、非预置答案）

`examples/case.json` 有 5 条导入：正式发表 RCT、同 DOI 重复导出、显式关联预印本、队列研究和一个人为制造双人意见分歧的错误人群 RCT。fixture 的查询、票及第三人都是**明确标注的合成输入**，不是真实人工审核或正式案例证据。

```json
{"case_id":"systematic-synthetic-example-v2","status":"clean",
 "flow_counts":{"identification":{"raw_records":5,"duplicates_removed":1,
                "other_versions_linked":1,"unique_work_clusters":3},
                "title_abstract":{"screened":3,"excluded":2,"advanced_to_full_text":1,"pending":0},
                "full_text":{"assessed":1,"excluded":0,"included":1,"pending":0},
                "overall":{"included":1,"excluded":2,"pending":0,"process_complete":true}},
 "prisma_counts_closed":true}
```

第三人将错误人群记录以 `EX-POP` 排除，rationale 和 quote 都保留。该例的独立复算就是 `5−1−1=3`、`3=2+1+0`、`1=0+1+0`。

旧的 `search_cli.py + search.py` 仅是原通用布尔工具兼容层，不能完成本 Skill 的协议、双人或计数闭合；正式任务使用 `systematic_cli.py`。

## 5. PRISMA-S 与开源评测案例的真实落地

- **PRISMA-S**（Rethlefsen et al., 2021, DOI `10.1186/s13643-020-01542-z`）：按其检索报告思想，保留数据库与平台、完整逐库检索式、字段和限制、检索日期、既有检索更新、总记录与去重管理。本包实际输出这些字段，而未宣称“PRISMA 2020 全文合规”或 PRISMA 官方认证。
- **BEIR**（https://github.com/beir-cellar/beir）：其 `qrels` 与 `results` 分离，启发本包把真实 reviewer 判定与引擎建议分开；同一输入、同一标准版本独立复跑，而非把机器词面分数当纳排真值。p55 中另有其 recall/precision 分母落地。
- **Pyserini**（https://github.com/castorini/pyserini）：可复现 run 保留 topics/index/query 和输出；本包对应固定查询、标准哈希、输入 IDs 和双阶段 ledger。p62 还实际采用其多语种/PRF 边界，而非在本筛选题混用扩展检索。

## 6. 规则、异常和限制

| rule | 含义与处置 |
|-|-|
| `systematic.case_unreadable` / `case_not_object` / `unknown_section` | exit 5 / 4 / 5，结构化拒绝 |
| `systematic.protocol_invalid` / `no_criteria` / `no_records` | 协议形状错误、无标准或无记录，exit 5 |
| `systematic.search_protocol_missing` / `search_protocol_incomplete` | 只能复跑部分流程，exit 3；不补数据库/日期 |
| `systematic.identifier_conflict` | 同标识但强题名冲突，不合并，exit 3 |
| `systematic.criteria_version_conflict` / `adjudication_version_conflict` | 旧票/旧仲裁不能沿用，重筛，exit 3 |
| `systematic.reviewer_identity_missing` / `reviewer_evidence_unverified` | 无名 reviewer 或伪 quote 的票无效，exit 3 |
| `systematic.review_version_unspecified` / `adjudication_version_unspecified` | 未声明来源版本，保留但必须复核，exit 3 |
| `systematic.exclusion_reason_missing` / `adjudication_reason_missing` / `adjudication_rationale_missing` | 缺排除理由或仲裁依据，不定稿，exit 3 |
| `systematic.decision_disagreement` / `reason_code_disagreement` | 分歧原样保留；无有效仲裁则 pending |
| `systematic.review_pending` | 仍有独立复核/全文工作，exit 3，但计数可闭合 |
| `systematic.count_not_closed` | 复算不符，exit 3，不隐藏差异 |
| `systematic.records_omitted` / `records_consolidated` | 无效条目或去重/版本归并逐项留痕 |
| `systematic.human_review_absent` | 只有建议，没有实际双人结论，exit 3 |
| `systematic.internal_error` | 未预见异常封装 exit 5 + result.json，不泄漏 traceback |

限制：text match 不等于科学语义裁决；去重不识别未声明的所有预印本关系；agreement/kappa 只描述输入票，不代表真实研究质量；无查询日志时只能复跑筛选子流程；不能证明全球召回、当前撤稿状态或数据库最新结果；不做全文偏倚评价、数据提取、统计综合或论文写作（这些也不属于本题）。

## 7. Verification（作者测试，不是运行时必经步骤）

```bash
python -I -X utf8 scripts/bench_systematic.py           # 通用布尔回归 8/8
python -I -X utf8 scripts/bench_systematic_analysis.py  # 专项协议/纳排/去重/仲裁/闭合 16/16
python -I -X utf8 scripts/probe_systematic.py           # 敌意/契约/退出/幂等 17/17
python -I -X utf8 -c "import sys;sys.path.insert(0,'scripts');import systematic,systematic_cli;print(systematic.SCHEMA_VERSION)"
```

第三轮 smoke 使用两个冷输出目录比较 result、screening_decisions 和 flow_audit，并从 merge_log 重新数出 `5−1−1=3`，从每个簇的 title_abstract/full_text 决策独立复算阶段数。所有报告是合成回归，不是官方分数、固定案例或真实人工筛选。

## 8. Requirements 与生态

Python 3.9+（Python 3.14 实测），专项实现仅标准库，无 API key、数据库或网络依赖。`systematic.py` 可导入 `analyze()`；协议模板、理由码、标注表、仲裁表、去重日志、PRISMA-style 流程与复算入口可直接迁移到新综述主题。没有依赖 p59/p60/p67，也未把它们的任务范围混入本题。
