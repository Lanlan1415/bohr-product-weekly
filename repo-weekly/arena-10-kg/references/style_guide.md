# 风格与格式规范（文献知识图谱构建）

## 1. 文件格式

### graph_nodes.csv（UTF-8 无 BOM，逗号分隔，首行表头）

```
node_id,label,type,aliases
N001,Li7La3Zr2O12,Material,LLZO;锂镧锆氧
```

- `aliases` 内用半角分号分隔多个别名；无别名留空；
- label 中含逗号时用双引号包裹（CSV 标准转义）。

### graph_edges.csv

```
edge_id,subject,predicate,object,source_id,paragraph_id,quote,evidence_strength
E001,N003,prepares,N001,S1,sec2-p3,采用溶胶-凝胶法制备了 Li7La3Zr2O12,direct
```

- `subject`/`object` 填 node_id，不填名字；
- `quote` 逐字摘录 ≤40 字，删节用 …，含逗号加双引号；
- `evidence_strength` ∈ {direct, cited, inferred}；
- 可选属性列（value, unit, condition）固定追加在最后，全表表头一致。

### graph.jsonld（可选加分项）

`@context` 自拟但全文件一致；每个节点 `@id` 用 node_id；边用带 `source`、`paragraph`、`quote` 属性的 relationship 对象表达。提供 JSON-LD 时 CSV 仍是主交付，二者内容必须一致。

## 2. ID 与命名规范

- 节点：`N` + 三位流水号（N001, N002, …）；边：`E` + 三位流水号；**语义无关、只增不改、废而不删**（增量更新硬要求）；
- 编号按"首次出现在抽取工作稿中的顺序"分配，保证重复运行结果稳定；
- 来源编号 S1..Sn 由 inventory.py 按路径排序生成，全链路一致，中途不得重排；
- 规范名（label）用信息最完整的写法（化学式优先），其余写法一律进 aliases。

## 3. graph_summary.md 写作规范

- 结构按 `templates/output_skeleton.md`；中文为主，实体名保留原文写法；
- 图统计必须来自对 CSV 的实际计数（节点数、边数、按类型/关系统计、证据强度分布），**与文件行数一致**，禁止写"约"；
- 查询节每个查询固定四段式：查询语句 → 结果子图 → 支撑证据（quote 原文）→ 无法确定项；
- "冲突与待确认"节不省略，没有冲突就写"未发现"，不能不写；
- 全文不出现未经 case.json 确认的论文背景信息。

## 4. 引用与标记

- 文内来源标记统一 `[S#]`（如 [S1]），与材料登记表一致；
- 段落定位写作 `[S1 §sec2-p3]` 的形式；
- 跨篇对照写作 `[S1 §sec3-p1] vs [S2 §sec4-p2]`；
- 不写"第 X 页"——本任务输入无 PDF 页码概念。

## 5. result.json 风格

- status 诚实：`partial` 时必须能在 uncertainty 里逐条说出缺了什么；
- change_log 每条格式：`[时间或步骤] 动作：对象 → 原因`；
- uncertainty 每条格式：`事项 → 影响 → 建议人工接管位置`。
