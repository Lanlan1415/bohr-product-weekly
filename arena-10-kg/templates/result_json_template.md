# result.json 模板与透传规则（文献知识图谱构建）

## 透传规则（契约红线）

1. `case_id` 逐字取自 `/input/case.json`；
2. `output_contract` 声明的**全部原始字段**必须出现在 result.json 顶层，**字段名一字不差**——不要臆造、不要改名、不要漏项。值可以是文件路径、数组或对象，按字段语义填；
3. 契约字段之外可自由增加辅助字段（如本模板的 status/sources 等）；
4. 字段语义做不到时填 null 并在 uncertainty 说明，不要删字段。

## 示意 JSON（合成示意，非正式案例结果）

```json
{
  "case_id": "kg-demo-000",
  "graph_summary": "graph_summary.md",
  "graph_files": ["graph_nodes.csv", "graph_edges.csv"],
  "queries": [
    {"q": "LLZO 的制备方法？", "answer_edge_ids": ["E001"], "evidence": ["[S1 §sec2-p3]"]}
  ],
  "status": "partial",
  "sources": [
    {"source_id": "S1", "file": "primary-material.json", "note": "第一篇论文，JATS 段落索引"},
    {"source_id": "S2", "file": "secondary-material.json", "note": "第二篇论文；根 DOI 属 S1，未套用"}
  ],
  "uncertainty": [
    "S2 中 'better stability' 的比较条件未明确给温度 → E003 边未挂 condition，影响跨篇可比性 → 建议人工核对 S2 §sec4"
  ],
  "change_log": [
    "[第3步] 初版落盘：S1 抽取 6 边，通过 graph_check",
    "[第4步] 合并候选 LLZO/li7la3zr2o12 → 依据 [S1 §sec1-p2] 缩写定义；样品节点不跨篇合并",
    "[第5步] graph_check 报 1 条无证据边 → 回原文补 quote 后复检通过"
  ],
  "stats": {"nodes": 9, "edges": 7, "edges_direct": 5, "edges_cited": 2},
  "skipped_reason": ["S2 的 PDF 文本层未读出 → 该篇仅登记未抽取 → 补读后可从第 3 步继续"],
  "quality_gate": {"graph_check": "pass", "graphml_roundtrip": "pass",
                   "contract_check": "pass", "selfcheck": "pass"}
}
```

## v2 字段说明

- `skipped_reason`：被跳过/降级阶段的诚实原因；存在时 status 不得为 success；
- `quality_gate`：四道门的最终结果——graph_check（图质量门）、
  graphml_roundtrip（GraphML 回导一致性）、contract_check（写盘前契约前置
  校验）、selfcheck（交付结构自查）。

## 校验（写盘顺序）

```bash
# 1) 先在 /app/work 写 result_draft.json，做契约前置校验（建议性自查）
python3 /skills/weekly-skill/scripts/contract_check.py --case /input/case.json --result /app/work/result_draft.json
# 2) 无论校验结果如何都复制为 /app/output/result.json（缺项补 null 并记入
#    uncertainty/skipped_reason 照常交付），再跑结构自查
#    ——脚本退出码仅供定位问题，不作为交付门禁
python3 /skills/weekly-skill/scripts/selfcheck.py --output /app/output --case /input/case.json
```
