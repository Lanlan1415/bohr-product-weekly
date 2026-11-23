# 完整合成案例（全合成，非真实论文、非正式案例结果）

> 本案例的"论文"、数值、结论全部为演示而虚构，仅用于展示工作流与脚本用法。

## 1. 合成输入材料

`paperA.txt`（登记为 S1）：

> 本研究采用溶胶-凝胶法制备了 Li7La3Zr2O12（LLZO）固态电解质，在 25 °C 下测得离子电导率为 3.2e-4 S/cm。

`paperB.txt`（登记为 S2）：

> 我们比较了 LLZO 与 LATP 两种氧化物电解质的电化学窗口，发现 LLZO 对锂金属更稳定。

`case.json`（合成）：`{"case_id": "kg-synthetic-001", "output_contract": {"graph_summary": "...", "graph_files": "...", "queries": "..."}}`

## 2. 中间产物

**materials_register.md（inventory.py 实测生成，截选）**

| 来源编号 | 相对路径 | 类型 | 文本可读性 |
|---|---|---|---|
| S1 | paperA.txt | 文本 | 可读 |
| S2 | paperB.txt | 文本 | 可读 |

**schema_note.md**：本案例用到实体类型 Material/Method/Metric；关系用 prepares / has_metric / more_stable_than（均在 predicates.txt 内）。

**merge_decisions.md**：S1 的 "LLZO" 与 "Li7La3Zr2O12" 合并（依据 S1 缩写定义句）；S1 与 S2 各自的 LLZO 样品**不合并**（不同论文样品，红线 §3.3）——本合成例为简化演示共用 N001，正式案例中应建 `LLZO (S1 样品)` 与 `LLZO (S2 样品)` 两点。

## 3. 最终图文件（合成数据）

`graph_nodes.csv`：

```
node_id,label,type,aliases
N001,Li7La3Zr2O12,Material,LLZO;锂镧锆氧
N002,LATP,Material,Li1.3Al0.3Ti1.7(PO4)3
N003,溶胶-凝胶法,Method,sol-gel
N004,离子电导率,Metric,
```

`graph_edges.csv`（v2：含 value/unit/condition 列；比较边 E003 带比较条件，过比较-条件门）：

```
edge_id,subject,predicate,object,source_id,paragraph_id,quote,evidence_strength,value,unit,condition
E001,N003,prepares,N001,S1,sec2-p3,采用溶胶-凝胶法制备了 Li7La3Zr2O12,direct,,,
E002,N001,has_metric,N004,S1,sec3-p1,离子电导率为 3.2e-4 S/cm,direct,3.2e-4,S/cm,25 °C
E003,N001,more_stable_than,N002,S2,sec4-p2,LLZO 对锂金属更稳定,direct,,,对锂金属界面（电化学窗口比较）
```

`abbrev_candidates.csv`（v2，阅读时登记，graph_check --abbrevs 输入）：

```
abbr,full_form,source_id,paragraph_id
LLZO,Li7La3Zr2O12,S1,sec1-p2
```

## 4. 质量门实测（本 Skill 作者实跑）

> 说明：脚本退出码仅供定位问题，不作为交付门禁。正式任务中 graph_check 报 FAIL
> 时的正确做法是修一轮、复查一次，修不完的逐项记入 result.json 的
> uncertainty/skipped_reason 并照常落盘交付，而不是反复修到退出码 0。

通过情形：`graph_check.py --edges graph_edges.csv --nodes graph_nodes.csv --predicates predicates.txt --abbrevs abbrev_candidates.csv` →

```
[INFO] 边数 3；节点数 4；唯一 (s,p,o) 组合 3
[PASS] 悬空边 / 重复实体 / 无证据边 / 重复边 / 关系合法性 全部通过
结果：通过（0 个错误，0 个警告）   退出码 0
```

失败情形（人为制造：E002 删 source_id 与 quote、E003 指向未声明的 N999、复制 E001 为 E004、另建别名撞车的 N005/llzo）→

```
[FAIL 1] [重复实体] N005 的规范名 'llzo' 与 N001 的别名冲突，疑似同一实体重复建点
[FAIL 2] [无证据边] E002 缺少证据字段：source_id, quote
[FAIL 3] [悬空边] E003 的 object='N999' 未在节点表中声明
[FAIL 4] [重复边] E004 与 E001 均为 (N003, prepares, N001)，应合并为一条边并并列两组证据
结果：未通过（4 个错误，0 个警告）   退出码 1
```

v2 新增负路径（self_test.py 实测输出，必须被判 FAIL）：

```
[FAIL 1] [比较-条件门] E003 是比较类关系（more_stable_than）但 condition 为空：涉及对比的论断必须标明比较条件（温度/组成/测试协议等），否则结论不可比
[FAIL 1] [重复实体] 别名 'LLZO' 同时登记在 N001 与 N005 下（缩写候选冲突场景）
```

宽容路径：比较边存在但整表无 condition 列 → 只 WARN（退出码 0）；缩写候选未落点 → 只 WARN。

## 5. 查询演示（从图文件取数）

- **查询1：LLZO 的制备方法？** → 子图 {N001, N003, E001}；证据 "采用溶胶-凝胶法制备了 Li7La3Zr2O12" [S1 §sec2-p3]（direct）。
- **查询2：LLZO 报告了哪些指标？** → 子图 {N001, N004, E002}；证据 "离子电导率为 3.2e-4 S/cm" [S1 §sec3-p1]（direct）。
- **查询3：两篇论文对 LLZO 稳定性的结论是否一致？** → S2 报告 "LLZO 对锂金属更稳定"（E003, [S2 §sec4-p2]）；S1 无稳定性相关边 → **无法跨篇确证**，如实标注无法确定项。

## 6. 交付自查实测

`selfcheck.py --output <output_good> --case case.json`：14 项全部 PASS，退出码 0；
对缺契约字段、case_id 不符、无 CSV 的 `output_bad`：6 项 FAIL（case_id 不一致、契约字段缺失 graph_files/queries、图摘要缺失、三元组 CSV 缺失、来源标记缺失、查询不足 3 个），退出码 1。

## 7. v2 脚本实测（本 Skill 作者实跑，全合成）

**GraphML 导出 + 回导一致性**（`graphml_roundtrip.py`，上述合成图）：

```
[INFO] GraphML 已导出：graph.graphml（节点 4，边 3，边属性 predicate,source_id,paragraph_id,quote,evidence_strength,value,unit,condition）
[INFO] 回导比对字段：节点 4 个；边 11 个
[PASS] CSV → GraphML → 回导 完全一致（可回导）   退出码 0
```

篡改检测（手工把 GraphML 里"溶胶-凝胶法"改成"篡改-凝胶法"后 `--verify-only`）：

```
[FAIL] [节点] N003 的字段 'label' 不一致：CSV='溶胶-凝胶法' ≠ GraphML='篡改-凝胶法'
[FAIL] [边] E001 的字段 'quote' 不一致：……
结果：未通过（2 处不一致）   退出码 1
```

**契约前置校验**（`contract_check.py`，result.json 写盘前，建议性自查）：字段齐全的草稿
退出码 0；缺 graph_files/queries 的草稿退出码 1 并逐字段列出缺失。无论退出码如何
都应照常落盘 result.json：缺字段补 null 并写入 uncertainty/skipped_reason 后交付。

**端到端自测**（`self_test.py`）：15 项断言全部通过，覆盖 K01–K15（含 §4
的全部负路径、宽容路径、回导篡改检测、契约缺失、case_id 不符）。

## 8. 验证与限制声明

本案例与 §4/§6/§7 的实测均为**本地合成数据验证**，只证明脚本行为正确；
平台的 3 个隐藏评测案例与对照组未在本地运行，本 Skill 不声称任何分数。
