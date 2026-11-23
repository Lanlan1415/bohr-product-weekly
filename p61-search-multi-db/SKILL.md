---
name: search-multi-db
description: >
  多数据库联合检索。用于把 retained Crossref/Europe PMC/OpenAlex/Semantic Scholar/arXiv 导出
  规范为可复算联合结果：逐库原生查询翻译、DOI/标题模糊去重、显式版本合并、字段级来源谱系、
  冲突元数据保留、单库独有/重合覆盖及闭合计数。不执行未授权实时抓取，不把拼接记录叫去重。
---

# search-multi-db（多数据库联合检索）

主引擎为 multi-db-search/v2；旧 file-search/v1 文本探针仍保留兼容。主引擎处理**实际 retained exports**，不做网络调用。`query_translations` 是计划/配置，`executed_query` 只记录材料里真实提供的查询，不把生成语句谎称已执行。

## 核心能力

| rubric | 实际机制 |
|-|-|
| 多源查询翻译 | Crossref `query.bibliographic`、`query.author` 与 pub-date filter；Europe PMC `TITLE`、`AUTH`、`FIRST_PDATE`；OpenAlex `search`、`title.search`、publication_date filter；Semantic Scholar Graph 字段；arXiv `ti` 与 `au` |
| 来源覆盖 | required sources 逐库记录 status、raw response ref、pages/request、records seen/valid/included/rejected/filtered、合并后 work ids |
| 字段标准化 | 支持 Crossref `DOI`、`author`、`container-title`、`issued`，OpenAlex `display_name`、`publication_year`、`externalIds`，以及 Europe PMC PMID/日期等常见结构与通用字段 |
| DOI/标题去重 | 规范 DOI/PMID/PMCID/arXiv 精确键；标题归一及 `>=0.94` 模糊匹配 + 作者重叠 + ±1 年；不同 DOI 与传递桥接均否决 |
| 版本合并 | 仅显式 `version_group`、`work_family` 或 `canonical_work_id` 可连通不同 DOI 的预印本/期刊版本；所有版本和 DOI 都保留 |
| 冲突与谱系 | 每个字段保存所有 source/record/value/raw locator；展示值按 source priority 稳定选择，alternative values 永不丢弃；raw record 原样附在 source_lineage |
| 联合计数 | `identified = valid + rejected`；`valid = included + filtered`；`included = unique + duplicate observations`；`unique = single-source + multi-source`，并附逐式 closed |
| 异常降级 | timeout/permission/missing/error、坏记录、字段缺失、identity conflict 显式输出；不静默把部分联合集合称为完整 |

## 运行流程（结束于 deliverable）

1. 读取 `/input/case.json`、`task.md` 与所有实际源响应，固定 required sources、字段和原始请求。保留 `case_id` 与完整 `output_contract`；正式固定 cases 未随公开 challenge 下载，不使用示例代替。
2. 将真实快照整理成 `/app/work/multidb_case.json`，`mode` 设为 `multi_db`。没有的值留空；不要把另一个库的字段猜填进来。
3. 运行并交付 `/app/output/result.json`：

```bash
python /skills/weekly-skill/scripts/search_cli.py \
  --case /app/work/multidb_case.json --out /app/output
```

4. 核对每条记录的 `source_records → field_provenance → merge_decisions → metadata_conflicts`，以及 `count_reconciliation.closed=true`。缺源仍可交付带缺口的 `review` 结果，但不能声称全域完整。

本地合成演示（不是正式答案）：

```bash
python scripts/search_cli.py --case examples/multidb_case.json --out ./out
```

## 输入结构

```json
{
  "case_id": "caller-id",
  "mode": "multi_db",
  "output_contract": ["case_id", "merged_records", "count_reconciliation", "custom_field"],
  "custom_field": {"preserved": true},
  "required_sources": ["crossref", "europepmc", "openalex"],
  "required_fields": ["title", "doi", "authors", "year", "journal"],
  "query": {"title": "assay title", "author": "J. Doe",
            "from_date": "2024-01-01", "until_date": "2026-12-31"},
  "sources": {
    "crossref": {
      "status": "ok",
      "query": {"query.bibliographic": "actually recorded request"},
      "request": {"rows": 20},
      "raw_response_ref": "materials/crossref.json",
      "pages_retained": [1],
      "records": [
        {"id": "cr-1", "DOI": "10.1000/example", "title": "Example",
         "author": [{"given": "Jane", "family": "Doe"}],
         "issued": {"date-parts": [[2025, 4, 1]]}, "container-title": ["Journal A"]}
      ]
    },
    "europepmc": {"status": "timeout", "error": "actual deadline error", "records": []}
  }
}
```

也可用扁平 `records` 或 `documents`，每条带 `source` 或 `database`。`exclude_terms` 或记录 `include:false` 会产生有姓名的 filtered record；否则源响应记录视为已由 source-native query 命中，原因明写 `screening_reason`，不再假装进行了全文纳排。

## 去重、版本与合并的边界

1. DOI 去 resolver/小写规范化后精确分组；PMID/PMCID/arXiv 可作为次级精确键，但不能推翻冲突 DOI。
2. 标题变音符和标点归一。完全相同标题需作者姓+名首字母重叠、双方无作者，或明确版本组；模糊标题阈值 `0.94`，并要求作者重叠与年份差不超过 1。
3. 双方都声明不同 DOI 时普通模糊规则拒绝合并。Union 前检查组间所有 DOI，避免缺失 DOI 的记录成为错误桥梁。
4. 不同 DOI 的预印本与期刊版只有显式版本关系才合并。展示 DOI 优先非 preprint，但 `identifiers.doi` 与 `version_records` 保留全部版本。
5. 字段不是“择一后删其余”。`title`、`year`、`journal`、`type`、`authors` 的每个观察值都进入 `field_provenance`；不同值进入 `metadata_conflicts`，标明 selected value、稳定优先级和 alternatives。

## 主要输出

- `merged_records[]` / `records[]`：唯一工作、所有源、原始记录谱系、标识符集合、版本、字段来源、冲突和筛选理由。
- `query_translations[]`：库、原生翻译、材料中的 executed query、`retained_export_only`。
- `source_coverage[]` 与 `coverage`：缺源、单库独有 work ids、pairwise overlap、required fields present/missing + work ids。
- `merge_decisions[]`：精确/模糊/版本合并，含 similarity/shared creators/year gap；否决项也留记录。
- `count_reconciliation`：全部计数及四条可复算等式；`duplicate_observations = included_source_records - unique_works`。
- `evidence_records`、`rejected_records`、`filtered_records`、`findings`、`limits`、`uncertainty`、`change_log`、`snapshot_sha256`。
- 顶级 `case_id` 原位保留。`output_contract` 数组/对象键/单字符串均可；引擎字段优先，其他调用方字段直通，未知必需字段写 null + limits。

退出码：`clean=0`、`review=3`、`undetermined=5`、usage=2。错误会有结构化 result，不会 traceback，也不会把 refusal 改成 clean。

## Finding、refusal 与查询原语索引

| id | 真实触发/含义 |
|-|-|
| `multidb.no_sources` | 无源配置也无 retained 记录，undetermined |
| `multidb.engine_error` | 联合引擎异常，undetermined |
| `multidb.source_incomplete` | required source 缺失、timeout、permission 或 error |
| `multidb.record_rejected` | 记录非对象或无 id/title，保留原因 |
| `multidb.record_filtered` | 声明的 include/exclude 规则过滤，保留原因 |
| `multidb.metadata_conflicts_retained` | 同字段多值，保留所有观察而非静默覆盖 |
| `multidb.count_not_closed` | 任一计数恒等式未闭合，review |
| `search.spec_unreadable` | case/corpus/query/index JSON 不可读，exit 5 |
| `search.spec_not_object` | case 不是 JSON 对象，exit 5 |
| `search.engine_error` | 旧引擎异常，exit 5 |
| `search.empty_corpus` | 无可索引记录，exit 5 |
| `search.index_malformed` | index 结构不完整，exit 5 |
| `search.empty_query` | query 无可检索内容，exit 5 |
| `search.doc_skipped` | 旧路径 malformed/duplicate doc 被命名 |
| `query.bibliographic` | Crossref 的书目检索参数，不是 finding |
| `query.author` | Crossref 的作者检索参数，不是 finding |

## 旧版兼容

```bash
python scripts/search_cli.py --corpus examples/corpus.json \
  --query-file examples/query.json --out ./out-legacy
```

旧接口只是带 verbatim locators 的文本命中，不能代替多库身份归并。

## 方法来源如何落地

**Zotero `duplicates.js`** 的 DOI/ISBN 精确键、标题规范化、作者姓+首字母、±1 年与并查集直接启发了本地 identity pass。额外实现的不同 DOI 否决、跨组传递否决、显式版本组和字段级来源保留，针对多库联合检索，而不是复制 Zotero UI 行为。
https://github.com/zotero/zotero/blob/main/chrome/content/zotero/xpcom/duplicates.js

**OpenAlex `work.py`** 将 cited reference graph 与 related work 分开，提示本包把“同工作多观察”与“相关但不同工作”严格区分：只有证据键/版本关系进入 union；source overlap 只是计数，不会自动合并主题相似论文。
https://github.com/ourresearch/openalex-guts/blob/main/models/work.py

## 限制

- API 查询字符串可构造，但本 Skill 不调度实时请求、分页抓取或限流重试；request/pages/raw response ref 只能来自实际材料。生成计划不是成功执行证据。
- 标题模糊规则刻意保守。字幕变化大、作者全缺或版本关系未声明时可能需要人工仲裁；不会用主题相似冒充同文。
- 某库 empty/timeout 只描述 retained snapshot；单库独有并不等于全域唯一，联合 unique count 不外推数据库总体覆盖率。

## Requirements 与验证

Python 3.9+，仅标准库。`scripts/federated_search.py` 支持独立 `run(spec)`；映射、去重、合并、examples 均可复用。

可选作者核验（非 runtime 步骤）：

```bash
python scripts/bench_multidb.py
```

当前 20 个场景：旧接口、10 条手工跨库记录计数、原生翻译、精确/模糊/传递否决、版本谱系、冲突保留、缺源降级、坏记录、冷导入/契约/确定性。结果写 `scripts/report_multidb.json`。
