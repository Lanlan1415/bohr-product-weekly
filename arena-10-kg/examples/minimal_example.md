# 最小调用示例（示意输出，非正式案例结果）

> 本示例仅说明接口与流程，输出为**示意**，不冒充正式案例结果。

## 输入

```
/input/case.json        # 含 case_id 与 output_contract
/input/task.md
/input/primary-material.json    # 第一篇论文（JATS 段落索引）
/input/secondary-material.json  # 第二篇论文
/input/corpus-manifest.json     # DOI/哈希/许可证清单
```

## 调用

```bash
# 1) 材料清点
python3 /skills/weekly-skill/scripts/inventory.py --input /input --output /app/work/materials_register.md
# 2)（模型按 SKILL.md 第 2-5 步抽取、对齐名册裁决、成图，产出 CSV 与缩写候选表后）图质量门
python3 /skills/weekly-skill/scripts/graph_check.py \
  --edges /app/output/graph_edges.csv --nodes /app/output/graph_nodes.csv \
  --predicates /skills/weekly-skill/references/predicates.txt \
  --abbrevs /app/work/abbrev_candidates.csv \
  --report /app/work/graph_check_report.md
# 3) GraphML 导出 + 回导一致性验证
python3 /skills/weekly-skill/scripts/graphml_roundtrip.py \
  --nodes /app/output/graph_nodes.csv --edges /app/output/graph_edges.csv \
  --graphml /app/output/graph.graphml
# 4) result.json 写盘前契约前置校验 → 复制进 output → 交付自查
python3 /skills/weekly-skill/scripts/contract_check.py --case /input/case.json --result /app/work/result_draft.json
python3 /skills/weekly-skill/scripts/selfcheck.py --output /app/output --case /input/case.json
```

## 示意输出（截选）

`graph_edges.csv` 两行（示意，v2 带可选属性列）：

```
edge_id,subject,predicate,object,source_id,paragraph_id,quote,evidence_strength,value,unit,condition
E001,N003,prepares,N001,S1,sec2-p3,采用溶胶-凝胶法制备了 Li7La3Zr2O12,direct,,,
E002,N001,has_metric,N004,S1,sec3-p1,离子电导率为 3.2e-4 S/cm,direct,3.2e-4,S/cm,25 °C
```

graph_check.py 输出（示意）：

```
[INFO] 边数 3；节点数 4；唯一 (s,p,o) 组合 3
[PASS] 悬空边 / 重复实体 / 无证据边 / 重复边 / 关系合法性 全部通过
结果：通过（0 个错误，0 个警告）
```

> 脚本退出码仅供定位问题，不作为交付门禁：报 FAIL 时修一轮、把修不完的缺口
> 记入 uncertainty/skipped_reason，然后照常交付当前最好版本。

`graph_summary.md` 查询节一行（示意）：

> 查询1：LLZO 的制备方法？→ 子图 {N001, N003, E001}；证据 "采用溶胶-凝胶法制备了 Li7La3Zr2O12" [S1 §sec2-p3]（direct）。

完整可运行样例（含负路径、GraphML 回导与自测实测）见 `examples/synthetic_case.md`（全合成）。

## 验证与限制

本示例为**合成示意**；本地仅做过合成数据验证，平台的 3 个隐藏评测案例
与对照组未在本地运行，本 Skill 不声称任何具体分数。
