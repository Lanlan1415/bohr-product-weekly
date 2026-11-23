# 完整合成案例（**全合成**：人名、刊名、DOI 均虚构，仅演示流程与产物形态）

## 0. 输入材料（合成）

`case.json`：`{"case_id": "syn-03-demo", "output_contract": {"revised_manuscript": "str", "citation_report": "str"}}`

`draft.md`（合成原稿，含三类典型问题）：

```markdown
低资源命名实体识别近年来受到广泛关注 [1-3]。迁移方法依赖同源语对 [2]。
## 参考文献
[1] 张三, 李四. 图神经网络综述[J]. 软件学报, 2021, 32(5): 1301-1320.
[2] Smith J, Doe A. Attention is all you need[J]. Journal of Synthetic Studies, 2022, 15(2): 100-117. DOI: 10.1234/jss.2022.015.
[3] Smith J, Doe A. Attention is all you need[J]. J Synth Stud, 2022, 15(2): 100-117. DOI: 10.1234/jss.2022.015.
[4] 王五. 中文信息处理基础[M]. 北京: 合成出版社.
```

问题：[1-3] 段末堆引；[2]/[3] 重复（同 DOI）；[4] 未被引用且缺年份。

## 1. 中间产物（合成）

- `materials_register.md`：inventory.py 登记 3 个输入文件。
- `reflib_snapshot.md`：原样快照。
- `dedupe_report.md`：候选 1 对——[2]×[3]（同 DOI + 相似度 0.91 + 同年）→
  决策：保留 [2]（全称刊名信息更全），[3] 并入。
- S 登记：S1=[1]、S2=[2]、S3=[3]（并入 S2）、S4=[4]。

## 2. 处理（合成）

- 段末 [1-3] 拆开逐句挂引：第一句为泛化断言，改写为「低资源命名实体识别旨在
  ……[1]」；迁移句保留 [2]；[4] 无任何论断支撑 → 从文献表删除并记录。
- [4] 删除后重排：[3] 并入 [2] 后列表剩 2 条；正文 [2] 不变。
- S4（王五条目）曾缺年份：原条目如被保留应标「[缺: 年份]」，本例因未引用而删除。

## 3. 最终输出关键片段（合成）

`manuscript_revised.md`：

```markdown
低资源命名实体识别旨在标注稀缺语料中的实体 [1]。迁移方法依赖同源语对 [2]。
## 参考文献
[1] 张三, 李四. 图神经网络综述[J]. 软件学报, 2021, 32(5): 1301-1320.
[2] Smith J, Doe A. Attention is all you need[J]. Journal of Synthetic Studies, 2022, 15(2): 100-117. DOI: 10.1234/jss.2022.015.
```

`citation_check.py` 复跑：`制式=numeric ERROR=0 WARN=0 -> PASS`。

> 若复查后仍有 FAIL：逐项记入 result.json 的 uncertainty 与 skipped_reason 并
> 照常交付（本例修一轮即收敛）。脚本退出码仅供定位问题，不作为交付门禁。

`result.json`（合成）：

```json
{
  "case_id": "syn-03-demo",
  "status": "success",
  "revised_manuscript": "manuscript_revised.md",
  "citation_report": "citation_check_report.md",
  "sources": ["S1", "S2"],
  "uncertainty": "S4 因正文无论断支撑而删除，如原任务要求全量保留需人工恢复。",
  "change_log": ["[3] 并入 [2]（同 DOI）", "删除未引用条目 [4]", "段末堆引拆分为逐句挂引"]
}
```

配套产物（v2）：`numbering_map.md`（原 [1]→新 [1]、原 [2]→新 [2]、原 [3]→并入
新 [2]、原 [4]→删除，mapping_check.py 通过）；`roundtrip_report.md`
（roundtrip_check.py：2 条全部字段无损往返）。

> **验证与限制声明**：本案例为全合成；技能的脚本与流程仅在这类本地合成数据上
> 验证过（`scripts/run_selftest.py` 可复跑，含编造 DOI、幽灵引用等必须被拒绝的
> 负路径用例）。平台评测的 3 个隐藏案例与对照组未在本地运行，本包不声称、不
> 预测任何评测分数。
