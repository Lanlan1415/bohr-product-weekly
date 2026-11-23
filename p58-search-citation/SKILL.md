---
name: search-citation
description: >
  引文追踪与关联文献发现。用于从种子论文沿真实 retained citation graph 做前向/后向、多跳、
  共被引与文献耦合扩展，交付逐边来源、引用语境、最短路径和版本身份合并证据。
  不适合无来源编引文、普通关键词检索、全文阅读或未授权抓取。
---

# search-citation（引文追踪与关联文献发现）

本包有两条互不混淆的路径：

1. **citation-trace/v2 图追踪**：结构化 works + citing→cited edges + seed + depth，完成真正的图遍历和关联发现。
2. **旧版 file-search/v1 布尔探针**：保留 `--corpus` 与 `--query` 兼容性；它只是文本检索，不宣称完成多跳图追踪。

## 核心能力

| rubric | 实际机制与输出 |
|-|-|
| 前向/后向与多层 | 对 `citing_id -> cited_id` 构建双向邻接表，BFS；`forward` 找施引文献，`backward` 找参考文献，`both` 可混合逐跳；默认深度 2、节点 200 |
| 路径与语境 | 每个候选保留最短路径；每跳记录遍历方向、真实两端、edge id、数据源、引用语境及定位；`depth=1` 为 direct，`>1` 为 indirect |
| 共被引/文献耦合 | 共被引要求第三方同时引用 seed 与候选；文献耦合要求共享参考节点；`associations` 单列，不伪造直接引用边 |
| 论文身份/版本 | DOI 精确键；同版本组显式合并；标题归一/模糊比对必须同时满足作者、±1 年与 DOI 否决；保留所有版本及冲突 |
| 网络结构 | 在该 seed-centred retained graph 内标出 bridge/foundational_in_snapshot/recent/peripheral；不是全领域中心性结论 |
| 停止与缺口 | 深度、节点预算、循环去重、源失败、身份歧义、语境缺失都有记录；预算截断为 `review`，不冒充完整覆盖 |
| 可复算 | `snapshot_sha256`、稳定排序、无系统时钟；同输入字节一致 |

## 运行流程（结束于 deliverable）

1. 读取 `/input/case.json`、`task.md` 和实际提供的 snapshot/source exports，保留 `case_id` 与完整 `output_contract`。公开下载的 challenge 不包含正式三套 case；不要以 examples 冒充正式答案。
2. 把 **实际材料** 规范成 `/app/work/citation_case.json`。若原 case 已是下列结构可直接使用。缺字段保持 null/缺失，不凭记忆补文献、引文、语境或覆盖。
3. 调用图追踪并写最终 `/app/output/result.json`：

```bash
python /skills/weekly-skill/scripts/search_cli.py \
  --case /app/work/citation_case.json --out /app/output
```

4. 核对 `seed`、逐跳 `paths`、`citation_edges`、`associations`、`identity_merges`、`source_status`、`limits`。只有结构已知时才运行；缺 seed 得到结构化 refusal，不编造结果。

本地最小演示（合成数据，非正式 case）：

```bash
python scripts/search_cli.py --case examples/citation_case.json --out ./out
```

## 结构化输入约定

```json
{
  "case_id": "caller-id",
  "mode": "citation",
  "output_contract": ["case_id", "candidates", "paths", "status", "custom_field"],
  "custom_field": "preserved verbatim",
  "seed_id": "10.1000/seed",
  "works": [
    {"id": "seed", "doi": "10.1000/seed", "title": "Seed", "year": 2024,
     "version_group": "family-seed", "source": "crossref"},
    {"id": "follow", "doi": "10.1000/follow", "title": "Follow-up", "source": "openalex"}
  ],
  "edges": [
    {"citing_id": "follow", "cited_id": "10.1000/seed", "source": "openalex",
     "source_record_id": "openalex-follow-ref-1",
     "context": "verbatim retained citing passage if actually supplied",
     "context_locator": {"record": "follow", "field": "references[0]"}}
  ],
  "max_depth": 2, "direction": "both", "max_nodes": 200,
  "source_status": {"openalex": {"status": "ok"}}
}
```

也接受 work 内的 `references` 与 `referenced_works`（该 work 引用别人）、`citations` 与 `cited_by`（别人引用该 work）、旧记录文本中的逐行 `refs:` 与 `cites:`。显式边中的 `citing_id` 和 `cited_id` 永远按引用语义解析，**不是遍历方向**。来源不同但相同 edge 的记录会按 source、context、record id 留谱系；完全相同的导出边只计一次并命名。

### 身份规则与可仲裁性

- 规范化 DOI 会去掉 resolver 前缀、转小写；标题去变音符/标点、统一空白。
- 精确 DOI 和明确 `version_group`、`work_family` 或 `canonical_work_id` 先分组；版本组允许预印本和期刊 DOI 不同，二者都保留。
- 标题完全相同：需作者姓+名首字母重叠、双方都无作者，或显式版本组；标题模糊相似度须 `>=0.94` 且有作者重叠。两份记录有年份时间隔最多 1 年。
- 双方都声明不同 DOI 时禁止普通模糊合并；并查集 Union 前还检查组间 DOI，防止“无 DOI 中间记录”把两个不同工作传递合并。被否决或歧义的项留在 limits/decision 中等待人工仲裁。

## 主要输出

- `seed`、`candidates[]`：工作元数据、`version_records`、`conflicting_metadata`、depth、direct/indirect、推荐理由、`shortest_path`。
- `citation_edges[]`：`edge_id`、`citing_id`、`cited_id`、`direction`、`source`、`source_record_id`、`citation_context`、`context_locator`。
- `paths[]`：可由 edge 表逐跳复核的最短路径。
- `associations[]`：`co_citation`、`bibliographic_coupling` 或两者，含 shared citing works/references/edge ids。
- `network_summary`、`coverage`、`source_status`、停止原因。
- `identity_merges`、`duplicate_edges`、`evidence_records`、`findings`、`limits`、`uncertainty`、`change_log`、`snapshot_sha256`。
- 顶级 `case_id` 原位保留。`output_contract` 支持字段数组、对象键或单字符串；引擎字段优先，其他调用方字段保留，未知必需字段写 null 并加入 limits，不静默漏字段。

状态与退出码：`clean→0`；数据仍可用但有预算截断、源缺口或高严重性问题 `review→3`；不能确定 seed/读取输入等 `undetermined→5`；CLI 用法错误 `2`。refusal 也写 `result.json`，绝不把 refusal 改写为 clean。

## Finding 与 refusal 索引

| id | 真实触发 |
|-|-|
| `citation.seed_unresolved` | seed 缺失或标识歧义，undetermined |
| `citation.engine_error` | 图引擎异常，undetermined |
| `citation.budget_stopped` | max_nodes 截断，停止原因保留 |
| `citation.identity_ambiguous` | 一个标识映射多个身份簇，需仲裁 |
| `citation.context_missing` | edge 没有 retained citation context，不补造 |
| `citation.edge_deduplicated` | 完全相同的 edge 导出只保留一次 |
| `search.spec_unreadable` | case/corpus/query/index JSON 不可读，exit 5 |
| `search.spec_not_object` | case 不是 JSON 对象，exit 5 |
| `search.engine_error` | 旧引擎异常，exit 5 |
| `search.empty_corpus` | 无可索引记录，exit 5 |
| `search.index_malformed` | index 结构不完整，exit 5 |
| `search.empty_query` | query 无可检索内容，exit 5 |
| `search.doc_skipped` | 旧路径 malformed/duplicate doc 被命名 |

## 旧版兼容调用

```bash
python scripts/search_cli.py --corpus examples/corpus.json \
  --query-file examples/query.json --out ./out-legacy
```

这条路径输出 hits/passages，其中 quote 可由文本偏移复核。它不替代图追踪输出。

## 方法来源如何落地（不是只附链接）

- **OpenAlex work.py（ourresearch/openalex-guts）** 将 `referenced_works`、`cited_by_api_url` 和 `related_works` 分开。这里对应实现为：真实 references/citations 进入双向 edge 表，BFS 路径只沿边；共被引/耦合依据放在 `associations`，绝不混成引用事实。
  https://github.com/ourresearch/openalex-guts/blob/main/models/work.py
- **Zotero duplicates.js（zotero/zotero）** 实际组合 DOI/ISBN 精确键、标题去变音符/标点、作者姓+名首字母、±1 年与 DisjointSetForest。这里在其思路上加入 DOI 冲突否决、显式版本组与组间传递冲突检查，并让所有 merge decision 可回放。
  https://github.com/zotero/zotero/blob/main/chrome/content/zotero/xpcom/duplicates.js

## 异常与限制

- snapshot 没边只会得出“当前 retained graph 无记录”，不证明论文在现实中零被引。来源 timeout/permission/malformed 必须保留为覆盖缺口。
- 缺 `citation_context` 不妨碍验证已知 edge id/来源，但会标 `citation.context_missing`；绝不从摘要或标题编造引用语境。
- path 是 retained graph 内按确定顺序求出的最短链，不保证所有历史 API 路径、全文中的隐含关系或全域最短链。
- 图算法不执行远程检索、绕过权限、下载全文或评价撤稿科学结论。外部 API 快照时间以材料为准。

## Requirements 与可复用资源

Python 3.9+，仅标准库。`scripts/citation_graph.py` 可独立 `run(spec)`；`search_cli.py` 保留旧接口；`examples/citation_case.json` 是可改写的合成输入。

可选作者核验（不是 runtime 必需步骤）：

```bash
python scripts/bench_citation.py
```

当前套件 21 个场景，含旧路径回归、手工小图复算、DOI/版本否决、预算停止、契约/退出码、冷导入与确定性；结果写 `scripts/report_citation.json`。
