# 示例 01 · 引言与相关工作全链演示（示例，非正式案例结果）

> 本示例使用 `scripts/fixtures/` 中自写的虚构夹具（主题：时序异常检测，虚构方法
> PathFuse），**不是任何真实论文，也不是正式案例结果**。脚本输出为在随包脚本上真实运行
> 的结果；模型步骤（分组转述/gap 链/成稿）此处用夹具中已写好的示意代替（已标注）。

## 1. 输入

- 文献库：`scripts/fixtures/library.bib`（5 条虚构条目：liu2021arimad / chen2020mp /
  wang2022lstmae / zhao2023transc / li2021gdnx，均带 abstract）。
- 本文素材：`scripts/fixtures/materials.md`（虚构方法 PathFuse 的摘要与图表清单）。
- `/input/case.json`（示意）：`{"case_id": "demo-intro-01", "task": "起草引言与相关工作",
  "style": "编号引用"}`。

## 2. 调用方式

```bash
S=/skills/weekly-skill/scripts; W=/app/work; O=/app/output; F=$SKILL/scripts/fixtures
python -I -B "$S/parse_library.py" --input "$F/library.bib" --output "$W/entries.json"
# —— 模型步骤（示意见 fixtures/groups.json、gap_chain.json、contributions.json）——
python -I -B "$S/anchor_check.py" --anchors "$F/fixtures-anchors.json" \
  --entries "$W/entries.json" --report "$W/anchor_report.json"
python -I -B "$S/coverage_check.py" --draft "$F/draft.md" --entries "$W/entries.json" \
  --groups "$F/groups.json" --contributions "$F/contributions.json" \
  --materials "$F/materials.md" --report "$W/coverage_report.json"
python -I -B "$S/gap_chain_check.py" --chain "$F/gap_chain.json" \
  --review "$F/review_items.json" --entries "$W/entries.json" --report "$W/chain_report.json"
python -I -B "$S/write_matrix.py" --groups "$F/groups.json" --entries "$W/entries.json" \
  --output "$O/comparison_matrix.csv"
```

## 3. 示意中间产物（节选，来自夹具）

分组（groups.json 节选）：3 组——统计与距离基线（2 篇）/ 深度序列模型（2 篇）/
图拓扑方法（1 篇，标注"仅 1 篇，无法组内比较"）。每篇三列（结论/条件/局限）+ 逐字锚点，
如：`"anchor": {"quote": "依赖平稳性假设，在趋势漂移场景下误报率显著上升", …}`。

空白推导链（gap_chain.json 节选）：

```text
step1 literature_gap  统计基线依赖平稳性假设，趋势漂移下误报率上升 [evidence: liu2021arimad]
step2 cross_gap       免训练方法依赖人工窗口设定 [evidence: chen2020mp]
step3 cross_gap       低算力少标注场景下同时满足低误报与低算力的方案缺失 [author_judgment → 进 human_review_items]
step4 this_work       PathFuse：统计残差与图信号轻量融合，CPU 可推理
```

贡献对齐（contributions.json 节选）：`"F1 提升 6.2 个百分点" → Table 1（主结果），
status: aligned`。

## 4. 示意核验输出（真实脚本行为）

- `coverage_report.json`：`fabricated_refs: 0`（成稿 5 处引用全部在库）；覆盖率 5/5；
  单篇组告警 1 条（图拓扑方法）。
- `chain_report.json`：`errors: 0`；`LAST_STEP_NOT_THIS_WORK` 无；author_judgment 环
  已在 review_items。
- `comparison_matrix.csv`：1 表头 + 5 行 × 3 组。

## 5. 示意 result.json 信封（关键字段）

`status: "success"`；`result.verification: {anchor: {errors: 0, checked: 5},
coverage: {fabricated_refs: 0, coverage_ratio: 1.0, single_paper_groups: 1},
chain: {errors: 0, last_step_this_work: true}}`；`human_review_items: ["step3 为作者判断…"]`。

> 再次声明：以上全部为**示例**；正式案例以平台提供的材料实际运行为准。
