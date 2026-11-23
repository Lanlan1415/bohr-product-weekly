---
name: search-coverage
description: >
  检索覆盖率与遗漏分析：对获授权的本地候选记录和冻结的已知相关集，按 DOI/PMID、
  标题加作者或年份及人工裁决，真实计算 known-set recall；逐篇保留命中/未命中、
  原字段证据、查询/字段/来源/时间窗，计算补检新增相关文献和剩余漏检。没有完整
  候选相关性标签时不报告 precision，不知道总体相关文献数时绝不伪造绝对覆盖率。
  适用于“算覆盖—列漏检—做补检—复核增益”；不用于全球新颖性、实时数据库覆盖、
  以检索结果反推分母、系统综述正式纳排或把未找到判为不相关。
---

# 检索覆盖率与遗漏分析：分母冻结，漏检不消失

## 1. 本 Skill 的真实交付

主入口 `scripts/coverage_cli.py` 读取原始 `case.json`，生成：

- `result.json`：顶层 `case_id`、原 `output_contract` 全部同名字段、覆盖率指标、逐篇台账、候选集和状态；
- `coverage_matrix.jsonl`：每个冻结参考作品恰好一行，状态为 `covered`、`missed` 或 `awaiting_adjudication`；
- `search_protocol.json`：实际提供的查询、字段、来源、检索日期和时间窗；不把未执行的查询写成已检索；
- `supplementary_search.json`：补检前后指标、真正新增命中的 ref_id、逐轮边际增益和剩余漏检。

核心等式为：

```text
known_set_recall = covered unique reference works / frozen unique reference works
covered + unmatched + awaiting_adjudication = frozen unique reference works
marginal_gain = |covered_after \ covered_before|
```

`missed_references` 是尚未确认覆盖的参考作品（包含 awaiting），不是“不相关文献”。参考集内 DOI/作品键重复会去重；撤稿、无全文、访问受限及相似题名仍需裁决的记录**不会从分母消失**。

## 2. 六步运行时入口

### 第一步：读取真实案例，保存早期 partial

读取 `/input/case.json`、`task.md` 及授权材料清单。确认科研问题、有限快照边界、参考集、候选集、已有查询与增量导入状态、目标 `output_contract`。在 `/app/work` 处理，最终写入 `/app/output`。不要用领域标签或文件名补造论文、查询结果或全文。

### 第二步：冻结已知相关集，而非用结果定义分母

支持 `reference_set`、`known_relevant`、`known_relevant_set`、`references`、`qrels` 及相应 `*_path`。每条参考记录可含：

```json
{"ref_id":"ref-01","doi":"10.xxxx/abc","title":"Original title",
 "author":"Family et al.","year":2023,"reference_source":"Europe PMC",
 "inclusion_reason":"Eligible study","availability":"no_full_text"}
```

冻结键优先 DOI，其次显式 `work_id/study_id`，再其次规范化标题+作者/年份。原始查询经验不能事后重写冻结集。重复参考条目有 `duplicate_ref_id`、保留键和合并理由。没有可识别参考集，退出 5 并结构化拒绝。

### 第三步：规范化候选记录并保留来源

支持内联 `documents/studies/corpus/records/candidates`，以及 JSON、JSONL、CSV、TXT、MD 本地材料路径。支持 Crossref `message/items/message.items` 和 Europe PMC `resultList.result`，保留原始 ID、DOI、PMID、题名、作者、年份、摘要/给定正文、来源、版本及文本可用范围。

同一作品的重复导出在**候选工作层面**归并，导入记录数和唯一候选作品数分开报告。找不到全文不等于找不到题录；没有标识、题名或文本的无效条目进入 `omissions`，不会无声丢失。

### 第四步：逐篇匹配，证据必须能切片复核

按以下顺序判决，不静默放松：

1. **identifier_exact**：规范化 DOI/PMID/显式记录或作品 ID 精确一致；
2. **title_exact_with_corroboration**：规范化题名一致，并且作者或年份一致；
3. **title_approximate_with_corroboration**：题名字符相似度 ≥0.92 且 title-token Jaccard ≥0.70，同时作者或年份一致，且另一个没有冲突；
4. **manual_adjudication**：只采纳调用者提供的明确裁决，保留 reviewer/rationale；
5. 题名像但缺作者/年份佐证 → `awaiting_adjudication`，不擅自算命中，也不当作确定漏检。

原字段证据采用浏览器可复核的 `{document_id, unit, source_field, start, end}`；`quote == source_field_text[start:end]`。拉丁词使用真实词边界，`cat` 不会命中 `catastrophe`；CJK 使用无空格字串语义并实测原偏移，不以 NFKC/casefold 后的字符串伪装原切片。

### 第五步：运行真实 CLI 并分析漏检、补检

平台安装后的标准命令：

```bash
python -I -X utf8 /skills/weekly-skill/scripts/coverage_cli.py \
  --case /input/case.json --out /app/output
```

本地示例的等价命令（从包根执行）：

```bash
python -I -X utf8 scripts/coverage_cli.py --case examples/case.json --out ./_run_example
```

每个未覆盖条目记录所有已声明查询的 `query_id/query/source/fields/returned_ids` 和题名判别词的缺项。归因分为：

- **可核验事实**：`time_window_excludes_reference`（参考年份确实被窗口排除）、`reference_source_not_queried`、`not_present_in_supplied_candidate_snapshot`；
- **词面线索而非唯一因果**：`query_lacks_reference_title_discriminators`，必须绑定具体查询、字段和缺失词；
- **身份待裁决**：`match_requires_manual_adjudication`，不能写成“库里没有”。

没有查询历史时只报告最终快照事实，不推断数据库原因。漏检相关补充查询必须在 `iterations/search_history/queries` 中有来源、字段、实际 `returned_ids`，或新增记录明确标为 supplementary。换同义词重跑但没有新增 covered ref_id，边际增益就是 0。

### 第六步：按原契约交付，不扩大断言

输出前核对：所有原契约字段同名存在；分子、分母、矩阵行数和计数闭合；证据切片通过；补检增益来自集合差；残余漏检全部列出。缺字段以 `null + limits + finding` 保留并进入 review；不能由 case 的伪 `status` 覆盖引擎状态。相同输入应逐字节重放。

## 3. recall、precision 与绝对覆盖的边界

| 指标 | 何时计算 | 口径 |
|-|-|-|
| `known_set_recall` | 有可识别冻结参考集 | 已覆盖参考作品 / 冻结去重参考作品；不是 hit / retrieved |
| `known_set_miss_rate` | 同上 | 尚未确认覆盖（含 awaiting）/ 冻结参考作品 |
| `candidate_precision` | 只有 `candidate_labels_complete:true` 且给出完整候选标签/判定 | 判为相关的候选中被匹配到冻结集的作品数 / 完整候选判定数 |
| `absolute_coverage` | 本地有限快照无法知道 | 永远为 `null`，附 `scope_note`，不做 capture-recapture 或全球分母臆测 |

这借鉴了 BEIR 的 **qrels 与 EvaluateRetrieval** 分工：相关性判定和检索结果分开，Recall@K/Precision@K 的分母可复算。本工具不下载 BEIR、不借用其分数，也不声称复现其任务。

## 4. 输出契约：rubric 三段逐项对应

| rubric 原词 | result.json 落点 | 独立核验 |
|-|-|-|
| `检索结果` | `候选文献`、`排序/筛选结果`（逐参考命中矩阵）、`元数据`、`来源定位`、`覆盖率`、`遗漏说明`、`补检增益` | 唯一候选作品数与版本视图分开；每个 ref_id 有状态 |
| `证据记录` | `参考集冻结`、`逐条命中与证据`、`查询字段来源`、`补检前后`、`复算入口`、`核验方法` | 分子分母来自冻结参考集；quote 切片；查询追溯到具体字段/来源 |
| `状态说明` | `运行状态`、`已完成`、`未完成`、`空结果`、`冲突`、`权限或接口异常`、`不确定性` | 拒绝/材料缺失/身份冲突/无结果分别陈述 |

同时提供英文可机读键：`coverage_metrics`、`coverage_matrix`、`missed_references`、`supplementary_search`、`candidate_set`、`evidence_ledger`、`uncertainty`、`change_records`。`output_contract` 支持字符串、字段名对象、字段名列表及 `{field,name,key}` 对象列表；正常和拒绝路径都执行**引擎值 > case 显式小字段 > null+limits**。

| status | exit | 含义 |
|-|-|-|
| `clean` | 0 | 分析完整；允许存在已如实列出的 residual miss 或 precision 不可评 |
| `review` | 3 | 部分记录无效、身份需人工裁决或契约字段不可推导 |
| `undetermined` | 5 | 无法读取、无参考集/候选集、材料形状或路径不可运行 |
| `case_not_object` | 4 | case 不是 JSON 对象 |
| 命令行用法错误 | 2 | argparse 的用法错误，不伪装成覆盖结果 |

## 5. 最小合成示例（不是组织方案例或预制答案）

`examples/case.json` 有 4 个冻结参考作品、4 条基线候选导入和 1 条补检新增记录，包含 DOI 大小写、重复导出、无全文参考和一个确实未命中的参考。

```json
{"case_id":"coverage-synthetic-example-v2","status":"clean",
 "coverage_metrics":{"reference_total_after_internal_dedup":4,
                     "covered_references":3,"missed_references":1,
                     "known_set_recall":0.75,"absolute_coverage":null},
 "supplementary_search":{"before":{"known_set_recall":0.5},
                         "after":{"known_set_recall":0.75},
                         "newly_covered_ref_ids":["ref-gamma"],"marginal_gain":1}}
```

这个 2/4 → 3/4 的回归 fixture 使第三方无需相信文字就能独立复算召回和补检增益。示例中的 DOI 均为合成标识，不是实际文献断言。

旧的 `search_cli.py + search.py` 仅保留通用布尔索引兼容；它不是覆盖率分析器。正式路径必须使用 `coverage_cli.py`。

## 6. 方法与优秀开源案例的实际落地

- **BEIR**（https://github.com/beir-cellar/beir）：README 的 `GenericDataLoader(...).load()` 分离 `corpus, queries, qrels`，`EvaluateRetrieval.evaluate(qrels, results, k_values)` 输出 Recall/Precision；本包对应分离参考判定与命中，分母先于结果，完整标签未知时不硬算 precision。
- **Pyserini / MIRACL**（https://github.com/castorini/pyserini 与其 MIRACL 复现页）：逐查询、逐语言保存 run，用 `trec_eval` 对照固定 qrels；启发了本包逐 query/来源留痕、补检按 ref_id 集合差计算而不是声称“加了同义词所以更好”。PRF/翻译属于 p62，不在本题偷换为覆盖证据。
- **本地高分检索包的可迁移工程**：采用 material-path/inline 兼容、复杂 output_contract 全字段直通、干净/复核/拒绝退出码、冷路径运行和字节确定性。没有复制其他课题的题答案，也未修改 p59/p60 或 p67。

## 7. 规则、异常和限制

| rule | 处置 |
|-|-|
| `coverage.case_unreadable` | case 缺失/坏 JSON/编码，exit 5 |
| `coverage.case_not_object` | case 非对象，exit 4 |
| `coverage.unknown_section` | 非 coverage 类任务，exit 5 |
| `coverage.no_reference_set` / `coverage.no_candidates` | 无可用参考集或候选集，exit 5 |
| `coverage.match_adjudication_required` | 相似题名证据不够，exit 3，等待人工确认 |
| `coverage.reference_records_skipped` / `candidate_records_skipped` | 重复或不可用条目有名、有理由，exit 3 |
| `coverage.precision_not_estimable` | 标签不完整，precision null；仍可 exit 0 |
| `coverage.contract_field_missing` | 原字段保留 null+limits，exit 3 |
| `coverage.internal_error` | 未预见异常封装为 exit 5 + result.json，不泄漏 traceback |
| `search.material_missing` / `material_unreadable` / `material_shape` / `material_unsupported` | 材料路径、形状或类型不可运行，exit 5；PDF 必须先用平台 PDF/OCR 工具提取 |

限制：规范化标题/作者/年份规则不会证明两条记录一定是同一项研究；attributed query clue 不是数据库内部漏检的唯一因果；无真实 query/returned_ids 时不能按查询还原 before；无全文不阻断题录覆盖；不做实时远程检索、全球召回、完整系统综述纳排、全文质量评价或引用真实性判断。所有 marginal gain 均限于本次提供的数据。

## 8. Verification（作者验证，不是运行时必做步骤）

从包根运行独立合成测试：

```bash
python -I -X utf8 scripts/bench_coverage.py           # 通用布尔回归 8/8
python -I -X utf8 scripts/bench_coverage_analysis.py  # 专项场景 12/12，含 2/4→3/4 独立复算
python -I -X utf8 scripts/probe_coverage.py           # 敌意/契约/退出码/幂等 15/15
python -I -X utf8 -c "import sys; sys.path.insert(0,'scripts'); import coverage, coverage_cli; print(coverage.SCHEMA_VERSION)"
```

第三轮 smoke 应把相同 case 写入两个冷输出目录，核对 `result.json`、`coverage_matrix.jsonl` 字节相同，并直接用矩阵重新数 covered=3、分母=4、补检新增=1。测试报告不含官方固定案例、白板、墙钟时间或平台分数。

## 9. Requirements 与生态

Python 3.9+（当前环境 Python 3.14 实测）；专项实现仅标准库；不需要 API key、网络、数据库或 authors 本机个人文件。`coverage.py` 可独立导入 `analyze()`，`case_common.py` 提供可复用的材料/证据/契约边界，示例、参考集模板、命中矩阵、漏检分类表和复算入口均可迁移到新主题。
