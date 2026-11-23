# 全合成案例演示（文献翻译）

> **声明：本案例的论文、数据、术语、译文全部为虚构合成**，仅用于演示流程与产物形态，不冒充任何正式案例结果。

## 1. 合成输入

S1 = `synth_note.pdf`（虚构短文，文字层正常）。提取并分段后的 `/app/work/source_paras.md`（合成）：

```
[P001] Band-Gap Tuning of Synthetic ZnO Nanorods: A Demo Note
[P002] Abstract—We report a fully synthetic demo. The band gap of
       sample Z1 was determined to be 3.37 eV. [续接 p.1→p.1（演示标记）]
[P003] The nanorods were grown by hydrothermal synthesis at 90 °C for 6 h.
[P004] XRD patterns confirm the wurtzite phase; no impurity phase was
       observed, which may indicate high phase purity.
[P005] Figure 1. XRD patterns of ZnO nanorods (a) Z1 and (b) Z2.
```

## 2. 术语表（glossary.tsv，合成）

```
band gap = 带隙 ; 能隙, 禁带宽度
hydrothermal synthesis = 水热合成 ; 水热法合成
XRD = X 射线衍射
wurtzite phase = 纤锌矿相 ; 六方相
phase purity = 物相纯度
```

## 3. 双语对照译文（关键片段）

```
[P003] The nanorods were grown by hydrothermal synthesis at 90 °C for 6 h.
译文：纳米棒通过水热合成在 90 °C 下反应 6 h 制得。

[P004] XRD patterns confirm the wurtzite phase; no impurity phase was
       observed, which may indicate high phase purity.
译文：X 射线衍射（XRD）图谱证实了纤锌矿相；未观察到杂相，
      这**可能**表明物相纯度较高。（情态 may 保留为"可能"，不升级为"表明"）

[P005] Figure 1. XRD patterns of ZnO nanorods (a) Z1 and (b) Z2.
译文：图 1. ZnO 纳米棒的 XRD 图谱：(a) Z1 与 (b) Z2。
```

## 4. 机器核验结果（合成运行）

- `term_consistency.py`：5 条术语全部 PASS（首选译名出现 ≥1 次，禁用变体 0 次）。
- `align_check.py`：原文 5 段、译文 5 段，一一对应、顺序一致，FAIL 0。
- 人工清单：数字 3 处（3.37 eV、90 °C、6 h）一致；否定 1 处（no impurity phase→未观察到杂相）无翻转；引用编号 N/A（本合成片段无文献引用）。

## 5. 一个演示用的失败→修复循环（合成）

初稿 P003 误用禁用变体："通过水热法合成在 90 °C 反应 6 h"——
term_consistency.py 报 `[FAIL] hydrothermal synthesis = 水热合成 —— 禁用变体「水热法合成」出现于行 12`，
回填为"水热合成"后重跑 PASS，修复记入 change_log。这正是本 Skill 相对基础 Agent 的增益点：
错误被机器捕获，而不是靠人眼发现。

## 6. 句级锚定片段（v2，合成）

```
[P002-S01] [p.1] Abstract—We report a fully synthetic demo. || 摘要——我们报告一个全合成的演示。
[P002-S02] [p.1] The band gap of sample Z1 was determined to be 3.37 eV. || 样品 Z1 的带隙测定为 3.37 eV。
```

`sentence_anchor.py --anchors sentence_anchors.md --source source_paras.md`：5 段全覆盖、
锚号无重复无错位，PASS。零锚句段（漏段）会被判 FAIL——见 examples/negative_case.md。

## 7. 验证与限制声明（v2）

- 本案例**全合成**：论文、术语、译文均虚构；脚本 PASS 只证明其在合成 fixture 上按预期工作。
- 评测平台的 3 个隐藏案例与基础 Agent 对照**未在本地运行**，本案例不声称任何平台分数。
- 负路径（必须被拒绝的译稿）演示见 examples/negative_case.md；完整自测可用
  `python3 /skills/weekly-skill/scripts/selftest.py` 复现。
