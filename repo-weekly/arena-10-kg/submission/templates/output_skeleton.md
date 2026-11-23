# 输出骨架：graph_summary.md 与三元组 CSV

## 1. graph_summary.md 骨架（章节级，尖括号内为占位说明）

```markdown
# 文献知识图谱摘要：<本案例主题>

- case_id：<与 case.json 一致>
- 材料范围：[S1] <第一篇标识（DOI/标题）>；[S2] <第二篇标识>
- 构建时间范围/迭代说明：<如有增量更新，说明批次>

## 图统计
- 节点 <N> 个（Material x / Method x / Metric x / Claim x / …）
- 边 <M> 条（prepares x / has_metric x / outperforms x / …）
- 证据强度：direct x 条 / cited x 条 / inferred x 条
- 说明：以上数字由 graph_nodes.csv / graph_edges.csv 实际计数得出

## 实体与合并说明
<列出主要实体表：node_id | 规范名 | 类型 | 别名 | 来源>
<合并决策摘要：合并了哪些候选、依据；未合并的候选、理由（详见 evidence_map.md）>

## 查询演示（≥3 个，实际执行）

### 查询1：<查询语句>
- 结果子图：节点 <N00x…>；边 <E00x…>
- 支撑证据：<逐条：E00x — quote 原文 — [S# §段落ID] — 证据强度>
- 无法确定项：<图内无证据支持的部分，明确写"无法确定">

### 查询2：……（同结构）
### 查询3：……（同结构）

## 冲突与待确认
- <跨篇/源内冲突：两边各自的陈述与证据，并列呈现>
- <未报告项、读不出的材料、需要人工确认的合并候选>
- （无冲突时写"未发现冲突"，本节不省略）
```

## 2. 三元组 CSV 表头（必须与 graph_check.py 约定一致）

```
graph_nodes.csv: node_id,label,type,aliases
graph_edges.csv: edge_id,subject,predicate,object,source_id,paragraph_id,quote,evidence_strength[,value,unit,condition]
```

- 最小可行交付：≥1 篇论文、≥8 条有证据边即先落盘，再扩充；
- 数值结论的 value/unit/condition 列全表统一表头，没有的留空；
- **比较类边（outperforms/more_stable_than/compares）的 condition 列必填**（比较-条件门，graph_check.py 强制）；建议只要出现比较类边就给边表加上 value,unit,condition 三列。

## 3. GraphML 交付（v2）

- `graph.graphml` 由 `graphml_roundtrip.py` 从 CSV 自动生成并通过回导验证，**不要手工另写**；
- 交付清单：graph_nodes.csv + graph_edges.csv + graph.graphml + graph_summary.md + evidence_map.md + result.json。

## 4. 阅读期工作文件（v2，放 /app/work/）

- `abbrev_candidates.csv`：缩写候选表（表头 abbr,full_form,source_id,paragraph_id），graph_check --abbrevs 的输入；
- `alignment_roster.md`：对齐名册（模板 `templates/alignment_roster_template.md`）；
- 引用线索清单、任务问题清单：可并入对齐名册 §5。
