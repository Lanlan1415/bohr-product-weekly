# 完整合成案例（全合成，非真实稿件、非正式案例结果）

> 本案例的"稿件"、术语表、修改记录全部为演示而虚构，仅用于展示工作流与脚本用法。

## 1. 合成输入

`original.md`（待润色稿，登记为 S1；含三处语法错误与守恒对象）：

> The Li7La3Zr2O12 (LLZO) solid electrolyte have attracted much attention [1]. In this work, the ionic conductivity of LLZO was measured at 25 degC and reaches 3.2e-4 S/cm, which is higher than LATP (1.1e-4 S/cm) [2,3]. As shown in Figure 1 and Table 2, the activation energy is 0.32 eV, fitted by $\sigma T = A \exp(-E_a/kT)$. This results suggest that LLZO may be a promising candidate for all-solid-state batteries [S1].

`terms.txt`（合成术语表）：Li7La3Zr2O12 / LLZO / LATP / all-solid-state batteries

## 2. 分级润色（L1 为主，最小编辑）

润色稿 `polished_text.md`：

> The Li7La3Zr2O12 (LLZO) solid electrolyte **has** attracted **considerable** attention [1]. In this work, the ionic conductivity of LLZO was measured at 25 degC and **reached** 3.2e-4 S/cm, which is higher than **that of** LATP (1.1e-4 S/cm) [2,3]. As shown in Figure 1 and Table 2, the activation energy is 0.32 eV, fitted by $\sigma T = A \exp(-E_a/kT)$. **These** results suggest that LLZO may be a promising candidate for all-solid-state batteries [S1].

`change_log.md`（截选）：

- C001 | L1 | 第1句 | have → has | 主谓一致（主语单数）；
- C002 | L3 | 第1句 | much → considerable | 去口语化量词，期刊语域；
- C003 | L1 | 第2句 | reaches → reached | 实验叙述时态统一为过去时；数值 3.2e-4 未动；
- C004 | L2 | 第2句 | higher than LATP → higher than that of LATP | 比较对象对齐（电导率 vs 电导率）；
- C005 | L1 | 第4句 | This results → These results | 指示代词单复数；
- 未改动：25 degC、3.2e-4、1.1e-4、0.32 eV、[1]、[2,3]、[S1]、Figure 1、Table 2、公式、may（限定强度保留）。

## 3. 守恒门实测（本 Skill 作者实跑）

> 说明：脚本退出码仅供定位问题，不作为交付门禁。正式任务中守恒门报 FAIL 时的
> 正确做法是修一轮（或确认有意例外并留依据），修不完的记入
> uncertainty/skipped_reason 并照常交付当前最好版本，而不是反复修到退出码 0。

**通过情形**（上述润色稿）：

```
[PASS] 数字 / 引用标记 / 图表公式编号 / 公式 / 术语 全部守恒
结果：通过（硬错误 0，警告 0）   退出码 0
```

**失败情形**（人为制造的"改坏稿"：3.2e-4→3.4e-4；删 [2,3] 与 [S1]；Figure 1→Figure 2 并删 Table 2；公式分母 kT→2kT；LLZO 3 处被换成泛指只剩 1 处；may→definitely）：

```
[FAIL] 【数字】不一致：原文缺失 '25'、'3.2e-4'、'1'；润色稿多出 '3.4e-4'
[FAIL] 【引用标记】不一致：缺失 '[2,3]'、'[S1]'
[FAIL] 【图表/公式编号】不一致：缺失 'figure1'、'table2'；多出 'figure2'
[FAIL] 【公式（LaTeX 段）】不一致：原公式被改写
[FAIL] 【术语表】术语 'LLZO'：原文 3 次 → 润色稿 1 次
[WARN] 限定词(英)计数变化：原文 2 → 润色稿 0（may/suggest 被删除）
结果：未通过（硬错误 17，警告 1）   退出码 1
```

## 4. 交付自查实测

`selfcheck.py --output <output_good> --case case.json`：14 项全部 PASS，退出码 0；
对缺契约字段、case_id 不符、无修改记录的 `output_bad`：5 项 FAIL（case_id 不一致、契约字段缺失 polished_text/notes、修改记录文件缺失、编号条目不足、无改前/改后对照），退出码 1。

## 5. 本案例演示的评分点

- 改得对：三处硬错误各有时类型与理由；说得像：much→considerable 的语域修改符合期刊文体；
- 没改坏：全部守恒对象原样保留，脚本背书；讲得清：每条修改可回溯到句子位置。

## 6. v2 五脚本流水线实测（本 Skill 作者实跑，全合成）

`self_test.py` 在临时目录自建合成 fixture（中英混合 + LaTeX 公式，4 句英文
+ 1 句中文），跑完整 prepare→verify→finalize→audit，**29 项断言全部通过**
（退出码 0）。负路径用例的实际输出（每条都必须被拒绝并回退）：

```
[REVERT] N01：守恒门违规，已自动回退：数字/单位不一致          ← 3.2e-4→3.4e-4 数字篡改
[REVERT] N02：守恒门违规，已自动回退：限定词强度变化：限定词(英) 2→1   ← may→is 限定词加强
[REVERT] N03：守恒门违规，已自动回退：引用标记不一致            ← 删 [2,3] 引用删除
[REVERT] N04：守恒门违规，已自动回退：数字/单位不一致；数学环境（LaTeX 公式）被改动  ← kT→2kT
[REVERT] N05：守恒门违规，已自动回退：否定范围变化：否定词(英) 1→0   ← do not→删否定
[REVERT] N06：守恒门违规，已自动回退：否定范围变化：否定词(中) 1→0   ← 不可能→可能
[REVERT] N07：锚定失败：original 与 sent-0001 的当前文本不符（空白宽容比对）
[WARN] C002：id-only 记录（无 original 字段），无法锚定核对……   ← 宽容路径
[WARN] C003：有意守恒例外……依据：作者书面确认该句证据充分、可直陈   ← 例外通道
```

宽容与可靠性用例：

- **T11** verify 未运行时 finalize 仍导出原文快照 + `skipped_reason`，
  status=partial，退出码 0（不整案失败）；
- **T12** 契约字段无法产出时置 null + uncertainty，不删字段；
- **T13** finalize 之后手工改动 polished_text.md，audit 检出
  "事后篡改：sha256 与 manifest 不符"，退出码 1；
- **T14** finalize 连跑两次，_manifest.json 哈希完全一致（重复运行确定）。

> audit/selfcheck 报 FAIL 不阻止交付：交付物在 finalize 一步已落盘，FAIL 项修一轮、
> 复查一次后仍存在的记入 uncertainty/skipped_reason 照常交付。

## 7. 验证与限制声明

本案例与 §6 的实测均为**本地合成数据验证**，只证明脚本行为正确；
平台的 3 个隐藏评测案例与对照组未在本地运行，不声称任何分数。
