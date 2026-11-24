# 示例 01 · LaTeX 编译体检演示（示例，非正式案例结果）

> 本示例为演示接口自写的 15 行迷你 .tex（含 1 个未定义引用 + 1 个环境不配对 + 1 个
> 数学 $ 不配对 + 1 个表格列数疑点），**不是正式案例结果**。静态检查输出为随包
> static_check.py 真实运行结果（逐字引用）；编译部分依本机环境而定（本示例环境无 TeX，
> 走降级路径——如实演示）。

## 1. 输入（自写夹具 `demo.tex`）

```latex
\documentclass{article}
\begin{document}
See Figure~\ref{fig:demo} and Eq $x^2$ plus $y_1 math.
\begin{itemize}
\item a
\end{enumerate}
\begin{tabular}{ll}
a & b & c \\
d & e \\
\end{tabular}
\end{document}
```

## 2. 调用方式

```bash
S=/skills/weekly-skill/scripts; W=/app/work; O=/app/output
python -I -B "$S/detect_tex.py" --out "$W/tex_env.json"    # 本机 exit 3 → 静态降级
python -I -B "$S/static_check.py" demo.tex --out "$W/static_report.json"
# 有 TeX 的环境则走全流程：
#   python -I -B "$S/build_loop.py" demo.tex --dir . --report "$W/build_report.json"
#   python -I -B "$S/parse_log.py" round_logs/last.log --out "$W/error_table.json"
#   python -I -B "$S/repro_record.py" --main demo.tex --rounds "$W/build_report.json" --out "$W/repro_record.json"
```

## 3. 真实输出（static_check.py，节选自实际运行）

```json
{
  "issues": [
    {"line": 1, "check": "table_column_mismatch", "severity": "warning",
     "message": "Row 1 in tabular (spec 'll', 2 columns) has 4 cell(s); rough check",
     "fix_hint": "Fix the number of '&' in this row or the column spec; 'Extra alignment tab has been changed to \\cr' traces back here."},
    {"line": 3, "check": "math_dollar_unbalanced", "severity": "error",
     "message": "Odd number of '$' characters: inline math opened on this line never closes",
     "fix_hint": "Count the '$' delimiters; the classic root cause is a missing closing $ (often 'Missing $ inserted' at compile time)."},
    {"line": 3, "check": "ref_undefined", "severity": "error",
     "message": "\\ref-family command targets 'fig:demo' but no \\label{fig:demo} exists anywhere",
     "fix_hint": "Add \\label{fig:demo} next to the target (figure/table/section/equation), or fix the key typo; after fixing, rerun the compile rounds."},
    {"line": 6, "check": "env_mismatch", "severity": "error",
     "message": "\\begin{itemize} (line 4) is closed by \\end{enumerate}",
     "fix_hint": "Change this to \\end{itemize} (or fix the \\begin at line 4); nested environments must close innermost first."}
  ],
  "summary": {"file_count": 1, "issue_count": 4,
              "by_severity": {"error": 3, "warning": 1, "info": 0}}
}
```

已知边界（如实标注）：表格行号归因是粗检（报告行 1 而非 tabular 实际起始行 7——
行号定位以编译期 parse_log 为准，静态检查只做"有无疑点"提示）。

## 4. 示意 result.json 信封（无 TeX 环境降级路径）

`status: "cannot_determine"`；`status_notes: "本环境无 pdflatex/latexmk/tectonic，
仅完成 static_check 静态检查，未实际编译；安装 TeX Live 后可走完整 build_loop 流程"`；
`result.static_check.run: true`（上面真实输出）；`result.build.tool: "none"`；
`evidence[]` 给每条 issue 的源码逐字片段；`method.steps` 如实记录"未运行 build_loop"。

> 再次声明：以上为**示例**；正式案例以平台源码与真实编译环境运行为准。
