---
name: search-crosslang
description: >
  跨语言文献检索：从原问题与目标语种出发，以有 provenance 的概念表对齐学科术语、同义词、
  缩写、音译、本地名和拼写变体，真实生成逐语种 AND/OR 查询并在本地多语文档视图中检索。
  采用语言路由、词边界、RRF 跨语排序和 work-level 去重；原始、出版方全译文、英文摘要及
  精确副本不混计。支持原语言精确引文、版本冲突、已知相关集召回增益和可选 RM3-style
  伪相关反馈。译文/回译/PRF 不能冒充原文引文；不用于整篇翻译、实时全球召回或无依据新语种扩展。
---

# 跨语言文献检索：查询可以翻译，证据不能偷换

## 1. 真实交付

主入口 `scripts/crosslang_cli.py` 生成：

- `result.json`：case_id、原 output_contract 全字段、术语对齐、逐语查询、命中与版本、语言/状态/不确定性；
- `concept_alignment.json`：concept → language → variants 及每条术语的来源、受控类型、翻译服务/版本、许可；
- `multilingual_queries.jsonl`：逐语种、逐概念及组合查询与真实命中数，空结果保留；
- `original_evidence.jsonl`：每条命中在其语言/version view 的原字段、偏移和精确引文；
- `retrieval_evaluation.json`：逐语种结果、源语言基线与扩展召回、work/view 去重、PRF 运行与独立复算入口。

literature work 是召回计数单位，language/version view 是证据和匹配单位。精确重复导出不算新 view；原文、出版方完整译文和英文摘要仍是可检查的不同视图，但同属一个 work，不能把分子或分母抬高。

## 2. 六步运行时入口

### 第一步：读取真实案例，固定源语言、目标语种与契约

读取 `/input/case.json`、`task.md`、资源清单、`research_question`、`source_language`、`target_languages` 和 `output_contract`。在 `/app/work` 处理，保存早期 partial，最终结果放 `/app/output`。支持 `documents/views/studies/corpus/records/candidates` 及本地 JSON/JSONL/CSV/TXT/MD 路径、Crossref 和 Europe PMC 常见响应形状。

没有声明源语言时不会任意猜英语作为 baseline，而是标记 `source_language_unknown` 并 review，baseline recall 与 marginal gain 均为 null（不是 0）。没有参考集时只输出 lexical candidates，已知相关集召回为 null，绝不声称全球跨语言召回。

### 第二步：以概念表而不是整句机翻建立对齐

`concepts/term_table/terminology/concept_map` 支持：

```json
{"id":"cell-death","concept":"inflammatory programmed cell death",
 "terms":{"pt":[{"term":"piroptose","kind":"disciplinary_preferred",
                  "source":"curated glossary"},
               {"term":"morte celular inflamatória","kind":"descriptive_variant"}],
          "en":["pyroptosis","pyroptotic cell death"],
          "zh":["细胞焦亡","细胞炎性坏死"]},
 "controlled_terms":{"en":["Pyroptosis"],"zh":["焦亡"]},
 "spelling_variants":{"en":["pyroptotic"]},
 "abbreviations":{"en":["PCD"]},
 "transliteration":{"ja":["パイロトーシス"]},
 "translation_service":"human-curated terminology","translation_version":"v1",
 "source":"curated glossary reference","license":"resource license"}
```

术语条目有来源和类型；多个同义词在概念组内 OR，多概念组间 AND。额外支持 `local_names`、`misspellings`、`controlled_vocabulary` 等字段。缺某语言术语时输出行级缺口且不生成伪查询；声明翻译服务 timeout/quota/error 时继续使用既有受控词并 review，不捏造替代服务结果。

`concept_alignment` 只保存术语/翻译 provenance，不能把译文加入 `evidence_ledger` 冒充原文。正式查询文本是生成物，原始引文只能来自 case 提供的题录、摘要或正文。

### 第三步：识别语言与版本，真实去重

语言优先级是 **declared metadata > script/stopword clue > und**。拉丁字母本身不能区分英语/葡萄牙语；没有 kana 的汉字也不能完全区分中文/日文。无法可靠判断、或声明 en 与纯 CJK 正文冲突时，保留 `language_analysis` 并 review。

每条 view 记录：`language_analysis`、`version_kind`、`full_text_available`、`abstract_only` 和来源。`publisher_full_translation`、`machine_translation_view`、`translation_view`、`abstract_only`、`original_or_supplied_view` 明确分开；abstract-only 绝不升级为已读全文。

去重规则：

1. 相同作品标识 + 语言 + 版本类型 + **科学文本内容哈希**相同时算精确副本；ID、DOI、来源字符串不参与内容哈希，避免不同导出 ID 让副本复活；
2. 显式 `work_id/study_id` 或 DOI、version/translation relation 可聚合到同一 work；
3. 同作品/语言/版本类型但正文实质不同时保留双方并报告 `version_conflict`；
4. 不因译名相似就把不同工作合并，不把 view 数当 work 数。

只有题名、摘要、`text/full_text/body/sections/pages` 等科学文本参与匹配、语言识别和 PRF；记录 ID、DOI、source、language、journal 等元数据不会制造命中或反馈词。

### 第四步：逐语种查询、跨语排序与原文证据

计算实际 CLI：

```bash
python -I -X utf8 /skills/weekly-skill/scripts/crosslang_cli.py \
  --case /input/case.json --out /app/output
```

本地示例（从包根）：

```bash
python -I -X utf8 scripts/crosslang_cli.py --case examples/case.json --out ./_run_example
```

每个 query 记录 `query_id/language/kind/concept_ids/groups/expression/hit_count/empty`。语言查询路由到该语言的原始视图；不确定语言单独进入 `und` 池并标记 review。源语言 baseline 总会生成，即使源语言不在目标列表；扩展召回保留 baseline 结果，避免漏掉原有命中。

匹配与引用规则：

- 拉丁词与带空格词组按 Unicode-aware 单词边界，`cat` 不命中 `catastrophe`，`pyroptosis` 不命中 `pyroptosisx`；
- CJK 直接按无空格短语匹配，同时 PRF 分词实测每个 bigram 的偏移：`细胞焦亡 → 细胞[0:2]、胞焦[1:3]、焦亡[2:4]`，不重复加入整段 Han 词；
- 连续片假名/平假名作为真实日文 run，不把相邻“汉字+假名”错误并为一个词；
- 证据使用原字段 `{document_id,unit,source_field,start,end}`，`quote == original_field[start:end]`；
- `quotation_role` 区分 supplied original/abstract evidence 与 `translation_version_evidence_not_original_quotation`；机器译文另有 `is_machine_translated_quote=true`。出版方译文和机器译文均只能证明该译版内容，不能提升为原语原文。

跨语排序使用 reciprocal rank fusion（k=60）：每个 view 累积各查询的 `1/(60+rank)`；work 得分取**最佳 view 的得分而非把译版得分相加**，避免多译版优势。显式接受 PRF 时，每个接受分支按 `0.5/(60+rank)` 加权记录。最终 rank/score/query_ranks/best_original_view_id 全部可重算，lexical hit 不自动等于科学相关。

### 第五步：可选 PRF——真实实现，但默认不污染正式指标

`pseudo_relevance_feedback/prf/feedback` 声明后才启用：

```json
{"enabled":true,"fb_docs":3,"fb_terms":4,"min_document_frequency":2,
 "original_query_weight":0.5,"accept_prf":false}
```

机制不是把链接写进文档，而是实际执行：

1. 在每个语言的 `combined` 初始结果中取 top-N；
2. 只从这些原语言科学文本提取表面词/实测 CJK bigram，排除停止词、短词、已有概念项和元数据；
3. 以 document frequency ≥ 阈值选最多 fb_terms，保存每个词、来源反馈文档、df 和完整新查询；
4. 在原概念组仍命中之外要求 PRF 词出现，生成可审候选和原文证据，按 `original matched terms + PRF matched terms` 重新打分并重排，保存 candidate_ranking；
5. **默认 accept_prf=false**：仅输出 `unverified_original_text_terms_not_concept_translations`，不改变正式跨语召回；`accept_prf=true` 才加入带原查询权重的排序分支并记录 accepted_prf_query_count。

PRF 词不是受控译名，不能不经审核进入概念表，也不能算作翻译证据。反馈不足时输出 `no_initial_relevant_feedback_documents` 或 `no_safe_expansion_terms`，不硬造扩展词。

### 第六步：按 works 独立复算并交付契约

已知相关集放在 `reference_set/known_relevant/qrels`，以 work_id/DOI/显式 ID 对齐；仅在必要时用标题+作者/年份精确佐证，不猜不同语言的题名相等。计算：

```text
baseline_recall = source-language covered works / known relevant works
expanded_recall = (baseline + target-language covered works) / known relevant works
marginal_gain = |covered_after \ covered_before|
```

同时报告各语言自己的新 work 命中、empty query IDs 和增益来自哪一语言。`absolute_crosslingual_recall=null`，不知道全球相关集时不虚构分母。最后核对所有原始 output_contract 字段和两次运行的确定性。

## 3. 输出契约：rubric 三段逐项对应

| rubric 原词 | result.json 落点 | 核验方式 |
|-|-|-|
| `检索结果` | `候选文献`、`排序/筛选结果`、`逐语种结果`、`元数据`、`来源定位`、`跨语种召回增益`、`遗漏说明` | views/works 分列；语言命中与版本归属可复算 |
| `证据记录` | `概念与术语对齐`、`逐语种查询`、`原文证据`、`引文边界`、`伪相关反馈`、`复算入口` | 术语 provenance、RRF/PRF 查询、quote 切片与召回差集 |
| `状态说明` | `运行状态`、`已完成`、`未完成`、`空结果`、`冲突`、`权限或接口异常`、`不确定性` | 空语种、缺术语、服务失败、版本冲突分别陈述 |

英文键包括 `concept_alignment`、`multilingual_queries`、`query_results`、`ranked_results`、`candidate_set`、`language_summary`、`crosslingual_recall_gain`、`feedback_runs`、`evidence_ledger`、`uncertainty`、`change_records`。contract 支持字符串、字典、列表、field/name/key 对象列表；拒绝路径同样保留，不能让 case 的 status 覆盖引擎状态。

| status | exit | 含义 |
|-|-|-|
| `clean` | 0 | 可用目标语言都有有效查询和结果；精确副本/未接受 PRF 只有低级留痕 |
| `review` | 3 | 缺术语/参考集、语言不确定或无命中、版本/材料冲突、服务失败、契约缺口 |
| `undetermined` | 5 | case/材料不可用、无文档或无可执行概念表 |
| `case_not_object` | 4 | case 不是 JSON 对象 |
| 命令行用法错误 | 2 | argparse 用法错误，不伪装检索输出 |

## 4. 最小合成示例（非组织方案例，不是实际文献断言）

`examples/case.json` 是明确的合成 fixture：3 个 works、6 条导入 views；其中 w1 有葡萄牙语原文和出版方全译文的重复导出，w2 有葡萄牙语原文与英文 abstract-only，w3 为英文原文。去除 1 个精确副本后为 5 views，仍只有 3 works。

```json
{"case_id":"crosslang-synthetic-example-v2","status":"clean",
 "documents_indexed":6,"unique_input_views_after_exact_dedup":5,"unique_candidate_works":3,
 "crosslingual_recall_gain":{"before":{"known_set_recall":0.6666666666666666},
                             "after":{"known_set_recall":1.0},
                             "newly_covered_ref_ids":["ref-w3"],"marginal_gain":1},
 "accepted_prf_query_count":0}
```

baseline 是葡萄牙语 2/3，扩展英语后 3/3，增益按 ref/work set 差为 1，不能用两个 w1 译版证明新增。PRF 默认隔离，示例检索结果不依赖机器翻译服务。

旧的 `search_cli.py + search.py` 只留作通用 CJK/布尔兼容；本题正式入口是 `crosslang_cli.py`。

## 5. 优秀 GitHub 案例的真实落地

- **Pyserini**（https://github.com/castorini/pyserini）：MIRACL 复现页把 `--language`、`miracl-v1.0-<lang>-dev` topics、逐语 index 和 `trec_eval` 固定下来；本包据此保存逐语 query、独立语言结果和自定义合成 qrels，而非只报告混合语种平均数。其 `LuceneSearcher.set_rm3(fb_terms, fb_docs, original_query_weight)` 直接对应本包可配置的 top-N、反馈词数与原查询权重；本包是标准库的 deterministic lexical PRF，不声称调用 Lucene RM3 或复现其分数。
- **BEIR**（https://github.com/beir-cellar/beir）：`corpus, queries, qrels` 分离以及按 qrels 计算 Recall/Precision 的接口促使本包把 reference work set 与候选结果、排序分别保存，并对照 before/after ref set 计算真实增益；没有完整总体相关集时不 invention global qrels。p55 另落地其 recall/precision 分母纪律。
- **本地高分检索包**：复用 inline/material-path 兼容、复杂契约全字段直通、无 traceback 退出纪律与字节重放；但本题新增的是独立多语查询/版本/语言/PRF 实现，不是通用搜索脚本的换皮。

## 6. 规则、异常与限制

| rule | 处置 |
|-|-|
| `crosslang.case_unreadable` / `case_not_object` / `unknown_section` | exit 5 / 4 / 5，结构化拒绝 |
| `crosslang.no_documents` / `no_concepts` | 无视图或无概念表，exit 5 |
| `crosslang.term_translation_missing` / `language_query_incomplete` | 缺目标概念词或组合查询，exit 3，不机翻补造 |
| `crosslang.language_uncertain` / `language_conflict` | 语言不可确认或元数据/脚本冲突，exit 3 |
| `crosslang.language_has_no_results` | 声明语种无有效结果，保留所有空查询，exit 3 |
| `crosslang.source_language_unknown` | baseline 不可猜，exit 3 |
| `crosslang.known_set_missing` | 仅 lexical candidates，召回 null，exit 3 |
| `crosslang.version_conflict` | 相同 work/language/version 但正文不同，双视图保留，exit 3 |
| `crosslang.exact_duplicate_views` | 精确副本命名去除，计数不虚增；仅低级留痕 |
| `crosslang.translation_service_unavailable` | 服务失败/限额，用现有已核术语并 review，不补造译文 |
| `crosslang.records_omitted` | 不可用记录逐条命名，exit 3 |
| `crosslang.internal_error` | 未预见异常封装 exit 5 + result.json，不泄漏 traceback |

限制：不是完整机器翻译或自然语言分词系统；CJK bigram 只用于原偏移 PRF 特征，不声称句法分词；所有匹配都是 lexical candidates，语义误译与高风险命中仍需原语言专家复核；没有受控词表就不能保证未见语言召回；不做未授权跨境抓取、全篇质量评价或全球新颖性判断。

## 7. Verification（作者测试，不是运行时必经步骤）

```bash
python -I -X utf8 scripts/bench_crosslang.py           # 通用布尔/CJK 回归 8/8
python -I -X utf8 scripts/bench_crosslang_analysis.py  # 专项查询/排序/原文/PRF/召回 17/17
python -I -X utf8 scripts/probe_crosslang.py           # 敌意/版本/契约/退出/幂等 19/19
python -I -X utf8 -c "import sys;sys.path.insert(0,'scripts');import crosslang,crosslang_cli;print(crosslang.SCHEMA_VERSION)"
```

第三轮 smoke 在两个冷目录比较 result 和 original_evidence 字节，并独立验证 `6−1=5 views`、`3 works`、`2/3→3/3、gain=1`。测试全部来自独立合成 fixture 与实测 CJK 边界，不是正式案例、白板、分数或真实翻译服务记录。

## 8. Requirements 与生态

Python 3.9+（Python 3.14 实测）；专项实现仅标准库，无 API key/网络/MT 服务/Lucene 依赖。`crosslang.py` 可独立导入 `analyze()`、`tokenize_with_offsets()`；概念表、逐语查询模板、版本视图 ledger、评测入口和 PRF 配置可迁移到新主题，术语来源和许可由调用者按真实资源填写。
