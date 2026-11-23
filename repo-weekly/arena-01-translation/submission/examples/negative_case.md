# 负路径自测演示（文献翻译，全合成）

> **声明：本文件全部 fixture 与输出为全合成**，由 `scripts/selftest.py` 在本地临时目录
> 生成并真实运行得到（可用 `python3 /skills/weekly-skill/scripts/selftest.py --keep-dir` 复现）。
> 仅做本地合成验证；平台 3 个隐藏案例与对照未在本地运行，不声称分数。

负路径自测的意义：校验器不仅要"放过好译稿"，更要**拦下必须被拒绝的译稿**——
尤其是"漏段却报 complete"这类不诚实交付（段级 + 句级双闸门）。

> **交付语义说明（v3）**：本文件演示的是校验器在本地合成 fixture 上的拦截力（开发期自测），**不是交付门禁**。真实评测中脚本报 FAIL 时的正确做法是：逐项把缺口记录到 result.json 的 uncertainty / skipped_reason，然后照常交付；脚本退出码仅供定位问题，不作为交付门禁。

## N1：译文使用术语表禁用变体 → 必须被拒绝

译稿把锁定译名"带隙"写成禁用变体"能隙"、"水热合成"写成"水热法合成"：
`term_consistency.py` 退出码 **1**（禁用变体逐条给出行号）。

## N2：译文漏段（P002 未译）→ 必须被拒绝（段级闸门）

`align_check.py` 退出码 **1**，实际输出：

```
[align_check] 原文段号 3 个，译文段号 2 个
[FAIL] 译文缺失段号 P002（漏译）
[align_check] FAIL 1，WARN 0
```

## N3：锚定记录零锚句段 + 空译文 → 必须被拒绝（句级闸门）

锚定记录里 P002 整段一句未锚、P003 译文为空——这就是"漏段却报 complete"的
句级形态。`sentence_anchor.py` 退出码 **1**，实际输出：

```
[sentence_anchor] 锚句 2 条，覆盖段落 2 个
[FAIL] 锚号 P003-S01 译文侧为空（漏译句）
[WARN] 锚号 P003-S01 译文侧无汉字（疑似未译或非中英任务，请确认）
[FAIL] 段 P002 零锚句（该段一句都没译——漏段却报 complete 的句级形态）
[sentence_anchor] FAIL 2，WARN 1
```

## N4：交付主产物缺"术语表"必备章节 → 必须被拒绝

`selfcheck.py` 退出码 **1**：`[FAIL] 主产物含必备要素：术语表章节`。

## N5：result.json 缺 output_contract 字段 → 必须被拒绝

草稿删掉契约字段 `glossary_path`：`contract_check.py` 退出码 **1**：

```
[FAIL] output_contract 字段齐全 —— 缺失：glossary_path
[contract_check] PASS 5，WARN 0，FAIL 1
```

## C1：校准纪律——内容齐全但 partial 无 uncertainty → 只 WARN、不判 FAIL

新增检查项一律 WARN 起步，**不把原本能通过的草稿判 FAIL**。实际输出（退出码 **0**）：

```
[PASS] output_contract 字段齐全 —— 7 个字段齐全
…（其余 PASS 略）
[WARN] W1 status 为 partial 但 uncertainty 为空 —— partial/failed 必须逐条说明限制与未完成项
[WARN] W3 partial 但未说明跳过原因 —— 建议用 finalize.py 固化交付并写 skipped_reason
[selfcheck] PASS 15，WARN 2，FAIL 0（WARN 不影响退出码）
```

## 正向对照：finalize 中断兜底

模拟"预算耗尽、work 里只有 translation_draft.md"的现场，`finalize.py` 退出码 **0**：
以草稿固化出 bilingual_translation.md（已译段落双语对照原样保留，不编造译文）、
result.json 补齐全部契约字段、写入 `skipped_reason`、status=partial——
**诚实部分永远可交付，而非整案失败**。

## 自测汇总（本地实际运行，全合成）

`selftest.py` 共 20 项用例全部符合预期：正向 14 项（inventory/term_consistency/
align_check/sentence_anchor/selfcheck/contract_check/finalize/--help×7），
负路径 5 项（N1–N5 退出码均为 1），校准纪律 1 项（C1 退出码 0 且含 [WARN]）。
