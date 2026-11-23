# 全合成案例演示（文献文档解析）

> **声明：本案例的论文、数据、引用全部为虚构合成**，仅用于演示流程与产物形态，不冒充任何正式案例结果。

## 1. 合成输入

`/input/` 中有 `synth_zno.pdf`（S1）：一篇虚构的 2 页双栏短文，文字层正常，含 1 张表、1 条编号公式、3 条参考文献。`pdftotext -layout` 得到的文本（合成）：

```
       Hydrothermal Synthesis of Nano-ZnO: A Synthetic Demo
       A. Example1, B. Example2
       1 Institute of Synthetic Materials, Demo City

       Abstract—We demonstrate a parsing pipeline on a fully
       synthetic two-column paper. No real data are reported.

       1 Introduction
       Zinc oxide (ZnO) is a wide band-gap semiconductor ...
       2 Methods
       The precursor was stirred at 60 °C for 2 h ...
       3 Results
       The band gap Eg follows Eq. (1):
              Eg = 3.37 eV − αT²/(T + β)          (1)
       Table 1  Synthetic lattice parameters
            Sample    a (Å)    c (Å)
            Z1        3.250    5.207
            Z2        3.251    5.209
       References
       [1] A. Demo, Synth. Mater. 1 (2020) 1.
       [2] B. Demo, J. Imaginary 2 (2021) 5.
       [3] C. Demo, Fake Lett. 3 (2022) 9.
```

## 2. 中间产物（关键片段）

`survey.json` 片段：

```json
{"page_count_heuristic": 2, "encrypted": false, "text_layer_present": true,
 "section_headings_found": 4,
 "anomalies": [{"level": "minor", "code": "MULTI_COLUMN", "detail": "…按栏切分…"}]}
```

`section_tree.md` 片段：

```
- Abstract
- 1 Introduction
- 2 Methods
- 3 Results
- References
```

## 3. 最终输出（关键片段）

parsed_document.md 正文区块：

```
[B005] [p.1] [col.L] [S1] [conf:high]
The precursor was stirred at 60 °C for 2 h ...

[B007] [p.1] [col.R] [S1] [conf:medium]
式(1) 原文行：Eg = 3.37 eV − αT²/(T + β)
置信度依据：T² 为上标线性化记法，希腊字母 α/β 保留 Unicode。
```

图表表：

```
| 编号 | 题注原文（逐字） | 所在页 | 正文首次引用区块 | conf |
| Table 1 | Synthetic lattice parameters | p.1 | B006 | high |
```

置信度汇总：`high 9 / medium 1 / low 0`；无 [NOT_READABLE]；参考文献 [1]-[3] 编号连续。

## 4. 自查结果

`selfcheck.py --output /app/output --case /input/case.json` 全部 PASS（result.json 含 case_id 与契约字段，主产物各章节齐全，[S1] 已登记）。

## 5. 验证与限制声明（v2）

- 本案例**全合成**：论文、数据、引用均虚构；selfcheck 的 PASS 只证明脚本在合成 fixture 上按预期工作。
- 评测平台的 3 个隐藏案例与基础 Agent 对照**未在本地运行**，本案例不声称任何平台分数。
- 负路径（必须被拒绝的草稿）演示见 examples/negative_case.md；完整自测可用 `python3 /skills/weekly-skill/scripts/selftest.py` 复现。
