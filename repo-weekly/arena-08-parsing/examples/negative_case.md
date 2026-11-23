# 负路径自测演示（文献文档解析，全合成）

> **声明：本文件全部 fixture 与输出为全合成**，由 `scripts/selftest.py` 在本地临时目录
> 生成并真实运行得到（可用 `python3 /skills/weekly-skill/scripts/selftest.py --keep-dir` 复现）。
> 仅做本地合成验证；平台 3 个隐藏案例与对照未在本地运行，不声称分数。

负路径自测的意义：校验器不仅要"放过好草稿"，更要**拦下必须被拒绝的草稿**——
尤其是"跳过 OCR 页却声称覆盖"这类不诚实交付。

> **交付语义说明（v3）**：本文件演示的是校验器在本地合成 fixture 上的拦截力（开发期自测），**不是交付门禁**。真实评测中脚本报 FAIL 时的正确做法是：逐项把缺口记录到 result.json 的 uncertainty / skipped_reason，然后照常交付；脚本退出码仅供定位问题，不作为交付门禁。

## N1：缺 result.json → 必须被拒绝

output-bad/ 缺 result.json：`selfcheck.py` 退出码 **1**，首行
`[FAIL] result.json 存在且可读`。

## N2：声称"扫描页已全部 OCR 并完整覆盖"，但缺必备章节、引用未登记来源 → 必须被拒绝

合成草稿谎称全覆盖，实际缺"公式"章节且引用了未登记的 [S9]。实际输出（退出码 **1**）：

```
[FAIL] 主产物含必备章节：公式
[FAIL] 引用的 [S#] 均已登记 —— 未登记：S9
[WARN] W4 有 OCR 页但主产物缺 OCR 页覆盖声明 —— survey.json 标记需 OCR 的页：p.2；禁止跳过 OCR 页却声称覆盖——照抄 ocr_coverage.md 的清单
[WARN] W5 主产物缺“未决事项/待确认”小节 —— 诚实声明未完成与存疑项是可核验性的评分点
[selfcheck] PASS 16，WARN 2，FAIL 2（WARN 不影响退出码）
```

## N3：result.json 缺 output_contract 字段 → 必须被拒绝

草稿删掉契约字段 `survey_path`：`contract_check.py` 退出码 **1**：

```
[FAIL] output_contract 字段齐全 —— 缺失：survey_path
[contract_check] PASS 5，WARN 0，FAIL 1
```

## C1：校准纪律——内容齐全但 partial 无 uncertainty → 只 WARN、不判 FAIL

新增检查项一律 WARN 起步，**不把原本能通过的草稿判 FAIL**。实际输出（退出码 **0**）：

```
[PASS] output_contract 字段齐全 —— 7 个字段齐全
…（其余 PASS 略）
[WARN] W1 status 为 partial 但 uncertainty 为空 —— partial/failed 必须逐条说明限制与未完成项
[WARN] W3 partial 但未说明跳过原因 —— 建议用 finalize.py 固化交付并写 skipped_reason
[selfcheck] PASS 18，WARN 2，FAIL 0（WARN 不影响退出码）
```

## 正向对照：finalize 中断兜底

模拟"主流程中断、只有 work 目录"的现场，`finalize.py` 退出码 **0**：
缺失主产物写诚实 NOT_COMPLETED 占位（不编造内容）、result.json 补齐全部契约字段、
写入 `skipped_reason`、status=partial——**诚实部分永远可交付，而非整案失败**。

## 自测汇总（本地实际运行，全合成）

`selftest.py` 共 18 项用例全部符合预期：9 项正向（含 inventory/pdf_survey×4 含分块/
selfcheck/contract_check/finalize/--help×5），3 项负路径（N1/N2/N3 退出码均为 1），
1 项校准纪律（C1 退出码 0 且含 [WARN]），pdf_survey 对混合页 PDF 正确把 p.2 列入
ocr_pages 并生成 ocr_coverage.md 与 table_registry.md。
