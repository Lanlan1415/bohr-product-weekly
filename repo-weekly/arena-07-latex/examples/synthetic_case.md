# 完整合成案例（写作13）

> **全合成声明：以下工程、日志、数值、脚本输出均为演示而虚构，不对应任何真实论文或正式案例。** 用途：走查主流程与脚本行为（脚本输出为实际运行结果）。
>
> **验证与限制声明**：本 Skill 仅在本地合成 fixture 上验证（本文件所示）；平台的 3 个隐藏评测案例与对照组从未在本地运行，不声称任何评测分数。

## 1. 合成输入

`/input/case.json`：

```json
{
  "case_id": "syn-latex-001",
  "output_contract": {
    "manuscript_source": "可编译工程目录",
    "pdf_preview": "真实编译的 PDF",
    "build_record": "编译记录"
  }
}
```

材料：模板 `journal.cls`（S2，只读）、稿件 `draft.md`（S3）、`refs.bib`（S4）。任务：迁入模板、补实验章节、编译交付。

## 2. 走查要点

1. **工程组织**：按 `templates/project_structure.md` 建 `main.tex + sections/ + figures/ + refs.bib`；模板 .cls 原样复制不改动。
2. **静态检查先行**：初版工程含 5 处静态错误（见 §3 实测），修一轮并复查一次后进入编译——避免浪费编译轮次；两轮后仍修不完的记入 uncertainty，不阻塞编译与交付。
3. **编译与日志分类**：首轮编译报 6 条错误（见 §4 实测），按"只修首错"纪律逐轮修复；undefined citation 属轮次问题，补 bibtex 轮次后收敛。
4. **诚实交付**：若最终因环境缺宏包编不过，保留完整 .log、status=partial（selfcheck 会拦截"无 PDF 却标 success"的谎报，见 §5 实测）。

## 3. tex_static_check.py 实测（合成 fixture）

坏工程：`main.tex` 引用不存在的 `sections/ghost.tex`、`\ref{tab:nope}` 悬空、`\cite{missing2021}` 不在 refs.bib；`sections/part1.tex` 有未闭合 `itemize`、引用缺失图片 `bad.pdf`。实际运行输出：

```
[错误] 缺失的 \input/\include 文件：.../bad/sections/ghost.tex
[错误] .../bad/sections/part1.tex:4：\begin{itemize} 缺少对应 \end
[错误] main.tex:5：\ref{tab:nope} 无对应 \label（悬空引用，编译必出 ??）
[错误] main.tex:5：\cite{missing2021} 在 .bib 中无条目
[错误] part1.tex:6：\includegraphics 引用的图片缺失：bad.pdf
结果：未通过（错误 5，警告 0）退出码 1
```

修复后的好工程复检：`结果：通过（错误 0，警告 0）退出码 0`。

## 4. log_triage.py 实测（合成日志）

对一份含 6 条错误 + 3 条警告的合成 .log 实际运行：

```
[错误][E1 未定义命令] ./main.tex:42  Undefined control sequence.
[错误][E3 数学模式错误] ./main.tex:57  Missing $ inserted.
[错误][E2 缺宏包/文档类] ./main.tex:?  LaTeX Error: File `fancyhdrx.sty' not found.
[错误][E4 环境不匹配] ./main.tex:9  LaTeX Error: \begin{table} on input line 3 ended by \end{figure}.
[错误][E10 致命中止] ./main.tex:?  Emergency stop.
[错误][E10 致命中止] ./main.tex:?  ==> Fatal error occurred, no output PDF file produced!
[警告][E8] ×3
结果：未通过（6 个错误）退出码 1
```

干净日志：`结果：通过（0 个错误）退出码 0`；仅含警告的日志非 strict 退出码 0、`--strict` 退出码 1。报告中每条错误附修复建议（对照 `references/error_fix_table.md` 的 E1..E10）。

## 5. selfcheck.py 实测（合成输出目录）

- 齐全交付（工程+PDF+记录）：`结果：通过（FAIL 0 / WARN 0 / 共 15 项）`，退出码 0；
- 谎报情形（无 PDF 且 status=success、缺契约字段）：5 项 FAIL，含"无 PDF 时 status 必须为 partial/failed——禁止谎称编译成功"，退出码 1——**负路径用例：谎称编译成功必须被拦截**；
- 诚实 partial（无 PDF + 保留 main.log + status=partial）：`结果：通过（FAIL 0 / WARN 2 / 共 18 项）`，退出码 0——v2 新增的 skipped_reason 与"编译记录写明引擎"两项只 WARN、不判 FAIL。

## 5b. v2 新增实测（合成 fixture）

- **log_triage.py 两级输出**：报告标题分"## 错误（阻断编译，必须修）"与"## 警告（不阻断编译……）"；仅含警告的日志非 strict 退出码 0——警告不夸大成错误。
- **contract_check.py（result.json 落盘前前置校验，建议性）**：缺 `manuscript_source/pdf_preview/build_record` 契约字段的草稿实测 `结果：存在建议修复项（FAIL 1）退出码 1`——正确做法是补齐后复查一次（最多两轮），仍修不完的逐项写入 uncertainty 与 skipped_reason，然后照常落盘交付；字段齐全时 `结果：无 FAIL 项（FAIL 0）退出码 0`。脚本退出码仅供定位问题，不作为交付门禁。
- **编译器选择顺序**（规则固化，见 method_rules.md §2）：题目/模板指定 > 工程现有配置 > 启发式默认；本案例模板未指定引擎，沿用工程默认 pdflatex——不因内容含汉字而强制换 XeLaTeX。

## 6. 最终交付片段（合成示意）

`result.json`：status=success（真实编译通过情形），`build` 字段记录 engine=pdflatex、rounds=3、bibliography=bibtex、template_modified=false；`build_record.md` 记录三轮编译与两处修复（math_mode ×1、citation 轮次 ×1）。
