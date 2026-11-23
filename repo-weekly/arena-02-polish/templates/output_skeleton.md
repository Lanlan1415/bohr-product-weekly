# 输出骨架：润色稿与修改记录

## 1. 润色稿（polished_text.md / 保持来稿格式）

- 完整全文，不是片段；保持来稿格式（Markdown/LaTeX/纯文本）与章节结构；
- 不在润色稿内插批注；待确认位置用与来稿格式兼容的方式标注（如 HTML 注释 `<!-- 【待确认】C017 见 change_log -->` 或任务允许的行内标记），并在 uncertainty 汇总；
- 如题目要求 Office 格式：另交付 docx 并渲染真实 PDF/PNG 预览；转换失败交 Markdown 并在 uncertainty 说明。

## 2. edits.jsonl 编辑记录格式（v2 流水线，verify.py 的输入）

每行一条 JSON（UTF-8，无 BOM）：

```json
{"edit_id": "C001", "sentence_id": "sent-0007", "level": "L1", "original": "<逐字抄当前原句>", "replacement": "<改后句>", "type": "grammar.agreement", "reason": "主语单数"}
{"edit_id": "C002", "sentence_id": "sent-0012", "level": "L3", "original": "<原句>", "replacement": "<改后句>", "type": "intentional.exception", "reason": "期刊指南要求统一 SI 单位（出处：journal_guide.txt 第3条）", "allow_conservation_break": true}
```

- `sentence_id` 来自 prepare.py 的 `sentences.tsv`；`original` 必须逐字抄
  该句**当前**文本（链式修改抄上一轮改后文本）；空白宽容、文字不宽容；
- `type` 取 `references/edit_types.md`；有意例外必须带
  `allow_conservation_break: true` + 充分 `reason`；
- 【备选】条目不写入本文件，写在 change_log.md 等作者定夺；
- 宽容路径：缺 `original` 的 id-only 记录可被接受但记 WARN（锚定核对
  失效，仅限实在无法抄录时）。

## 3. change_log.md 骨架（逐条修改记录）

```markdown
# 修改记录（change_log）

- case_id：<与 case.json 一致>
- 原文基线：/app/work/original_snapshot.md（封存，不再改动）
- 目标文体：<期刊英语/学位中文/基金/审稿回复>；术语表：/app/work/terms.txt
- 守恒门结果：<conservation_check.py 退出码与日期；有意例外见下方条目>

## 逐条记录

- C001 | L1 语法 | 摘要 第1句 | 原文：The electrolyte have attracted much attention [1]. | 改后：The electrolyte has attracted considerable attention [1]. | 类型：主谓一致/语域 | 理由：主语单数；much→considerable 去口语化（合并记录，属两条时拆开）。
- C002 | L1 语法 | 摘要 第5句 | 原文：This results suggest | 改后：These results suggest | 类型：指示代词单复数 | 理由：results 为复数。
- C003【备选】| L3 风格 | 结果 第2段 | 原文：The effect is significant. | 候选A（倾向）：The effect is substantial.（若指程度大）；候选B：保留原文（若指统计显著）| 理由：上下文无法判定，统计语境 significant 是术语。

## 有意守恒例外（无则写"无"）

- <条目号> | <被改的守恒对象> | <依据出处（任务书/期刊要求原文）>

## 限定词/否定词核对（WARN 项，无则写"无变化"）

- <位置> | <变化> | 核对结论：<强度未变，理由>
```

## 4. 最小可行交付

预算紧张时：全文 L1 语法级编辑记录 + verify 通过 + finalize 导出，
即为可交付基线；L2-L4 逐批追加并在 change_log 标注各级完成范围。
verify 未跑通时 finalize 也会导出原文 + skipped_reason——先交付诚实
部分，再迭代升级，绝不空手。
