# Intro & Related Work Writer — 使用说明

主文档是 `SKILL.md`，主入口是 `scripts/introcrun.py`。本页只保留可直接复现的调用，不另设一套工作流。

## 环境与产物

- Python 3.10+（3.14 实测），纯标准库、离线；BibTeX/JSON/编号列表可先用 `parse_library.py` 解析。
- 输入：真实 case 材料整理出的 spec，含草稿、文献元数据、三列锚点、最相近工作四维差异、空白链、贡献与范围、case_id、output_contract。
- 产物：`result.json`、`intro_related_work.md`、`comparison_matrix.csv`，均由主 CLI 确定性生成。

## 最小运行

```bash
python -I scripts/introcrun.py --spec examples/spec.json --out /app/output
```

`examples/spec.json` 是合成示例，不是平台正式回答。运行成功返回 clean / exit 0。

实际 case 按 `SKILL.md` P0–P5 处理 `/input/case.json`、`task.md` 和真实文献/方法/结果文件，把最终草稿写入 `/app/work/spec.json`，然后：

```bash
python -I scripts/introcrun.py --spec /app/work/spec.json --out /app/output
```

退出码：0 clean；3 review（包括摘要/元数据降级）；4 blocked（高级证据/贡献问题）；5 undetermined（不可读、非对象、错 section 或产物错误）。每种情况都读取 `/app/output/result.json`；无 traceback。

## 关键字段

- `references[]`：key/authors/year/title/venue/可选 DOI/text，元数据与全文支持状态分离。
- `citation_labels`：library key 到成稿实际引用形式的映射。
- `groups[].basis`、`groups[].papers[]`：分组依据和三列转述；verified_full_text 每列各有 quote+locator。
- `nearest_works[]`：similarity_basis 与 problem_setting/method_route/data_evaluation/scope 四维，每格 prior/this_work/difference。
- `gap_chain[]`：至少三环，末环 this_work；证据与作者判断分开。
- `contributions[]`：aligned 必须有 mapped_to 和 scope，artifact 必须在 materials_text 中存在。
- `draft`：背景、相关工作、研究空白、贡献四节；引用必须真实出现于最终稿。
- `case_id`、`output_contract`：原样携带；同名交付/证据/边界大字段同样逐字直通，不丢内容。

## 文档与测试

`references/grouping-rules.md` 和 `references/claim-rules.md` 继续用于组织分工与空白推导。旧辅助脚本仍是可复用资源，但主入口不是那五个旧检查器的简称。

```bash
python -I scripts/selftest.py
python -I tests/test_introcrun.py
```

原 44 项机制回归 + 新 18 项主入口测试；后者包括 clean、四维矩阵、拒绝、伪造 quote、错误差异、范围、降级契约和字节确定性。作者验证不是正式案例的强制前置步骤。
