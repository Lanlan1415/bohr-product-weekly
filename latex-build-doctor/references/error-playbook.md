# error-playbook — LaTeX 错误/警告分类与修复知识表

版本 1.0.0。本表由 parse_log.py 内置规则生成（类别与正则一一对应），修复时先查本表。

## 1. 错误类别（parse_log.py ERROR_RULES，first-match-wins）

| category | 识别特征 | 修复模板 |
|--|--|--|
| `missing_package`（缺宏包） | `File `[^']+\.sty' not found…` | Package not installed: TeX Live -> tlmgr install <pkg>; MiKTeX -> miktex packages install <pkg>; also check \usepackage spelling. Or compile with MiKTeX --enable-installer. |
| `missing_class`（缺文档类） | `File `[^']+\.cls' not found…` | Template class missing: copy the .cls (and its .def/.clo/.fd companions) next to the main file or install the full template bundle; check \documentclass spelling. |
| `missing_file`（缺输入文件） | `I can't find file\|File `[^']+' not found\|No file `[^']+'…` | Input file missing or path wrong: check \input/\include/\includegraphics path, case sensitivity, and that the working directory is the one holding the file. |
| `undefined_control_sequence`（未定义控制序列） | `Undefined control sequence…` | Macro misspelled or never defined; or the package that defines it is not loaded (e.g. \eqref needs amsmath, \ SI needs siunitx). Look at the fragment shown after l.<n>. |
| `math_mode_error`（数学模式错误） | `Missing \$ inserted\|Bad math environment delimiter\|Display math should…` | Math/material mode conflict: math-only command used in text (wrap in $...$ or \(...\)), or text-only content inside math; check \left/\right pairing. |
| `environment_mismatch`（环境不配对） | `ended by \\end\{\|Extra \\end\{\|Environment\s+\S+\s+undefined\|\\begin\{…` | \begin{X} closed by \end{Y} (or environment never defined): fix the name pair; nested environments must close innermost first. |
| `runaway_argument`（参数失控/括号不匹配） | `Runaway argument\|Paragraph ended before\|File ended while scanning\|Miss…` | Unbalanced brace or a blank line inside a command argument: close the {..} opened earlier; blank lines are not allowed inside most arguments (use \par-free content). |
| `table_column_mismatch`（表格列数不匹配） | `Extra alignment tab\|Misplaced alignment tab character…` | Row has more/fewer & cells than the tabular preamble declares; fix the column spec or the row (also check \multicolumn spans). |
| `unicode_error`（字符编码） | `Unicode character .{0,40} not set up\|Invalid UTF-8 byte\|inputenc Error…` | Character the engine cannot typeset: pdflatex -> declare with \DeclareUnicodeCharacter or use xelatex/lualatex + ctex/fontspec for CJK; re-save the file as UTF-8. |
| `float_problem`（浮动体问题） | `Float\(s\) lost\|Too many unprocessed floats…` | Float placed where it cannot be shipped out (e.g. inside a box/minipage): move \begin{figure} to top level; or add more \clearpage/[!t] placement. |
| `emergency_stop`（紧急停止（后续症状）） | `Emergency stop\|Fatal error…` | TeX gave up after earlier (often missing-file) errors: fix the FIRST error in the table, not this one. |
| `font_problem`（字体问题） | `Font .* not found\|Font shape .* undefined.*using…` | Requested font unavailable: install the font package or switch to a declared font family. |
| `other`（其他（人工判读）） | `（兜底：无匹配时）` | Read the error text and the l.<n> context fragment; map to the closest category in references/error-playbook.md. |

## 2. 警告类别（WARNING_RULES）

| category | 识别特征 | 修复模板 |
|--|--|--|
| `undefined_reference`（未定义引用） | `Reference `[^']+' .*undefined\|There were undefined references…` | \ref/\pageref target has no \label (or the label comes later in the text and another compile round is needed): add the \label or rerun. |
| `undefined_citation`（未定义文献引用） | `Citation `[^']+' .*undefined\|There were undefined citations\|empty `the…` | \cite key not resolved: check the key spelling against the .bib/.bibitem, ensure the bib step ran (bibtex/biber) and two more compile rounds follow. |
| `rerun_needed`（需要再编译一轮） | `Rerun to get\|Label\(s\) may have changed\|rerunfilecheck\|Rerun LaTeX…` | Cross-reference/citation data changed: run another compile round (build_loop.py does this automatically until the aux label hash is stable). |
| `multiply_defined_label`（label 重复定义） | `Label `[^']+' multiply defined…` | The same \label{key} appears twice: rename one occurrence (duplicate labels break \ref). |
| `overfull_box`（内容超宽） | `^Overfull \\hbox…` | BOX_HINT见下 |
| `underfull_box`（内容过松） | `^Underfull \\[hv]box…` | BOX_HINT见下 |
| `font_problem`（字体替换） | `LaTeX Font Warning\|Font shape .*undefined\|Size substitution…` | Font shape substitution: usually cosmetic; install the family or accept the substitution. |
| `bibliography_problem`（参考文献数据问题） | `Package natbib Warning\|Package biblatex Warning\|BibTeX warning\|biber w…` | Bibliography backend reports a data problem (missing field, duplicate key, style issue): fix the .bib entry, then re-run the bib step. |
| `package_warning`（宏包级警告） | `Package\s+\S+\s+Warning\|Class\s+\S+\s+Warning…` | Package-level warning: read the package name in the message; usually formatting advice, fix only if it affects required output. |

## 3. 盒子提示常量

- overfull_box: Content wider than the line/column: allow a line break, use \\linebreak, tighten spacing, or widen the box; do NOT hide it with tiny fonts or graphicx scaling.
- underfull_box: Loose spacing from forced breaks (\\\\, \\linebreak, sloppy par): remove the forced break or use \\looseness=-1; cosmetic unless the template forbids it.

## 4. 修复优先级

1. 先修表中**第一条**根因错误（emergency_stop 是后续症状，不要先修它）。
2. undefined_reference/undefined_citation 多数靠完整轮次协议（bib 步 + 两轮 pdflatex）解决，先确认轮次再改源码。
3. 每处改动记录 {file, diff_summary, reason(类别+依据)}。
4. 3 轮修不完 → partial，error_table 摘要进 status_notes。
