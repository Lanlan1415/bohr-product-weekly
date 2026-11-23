# LaTeX 编译错误 → 根因 → 修复对照表（写作13）

按 `log_triage.py` 的分类组织。每类给出：日志特征、典型根因、修复动作、禁忌。**总纪律：从第一个 `!` 错误开始修，修一个重编一次；级联错误不批量盲改。**

## E1 未定义命令（undefined_control_sequence）

- 日志特征：`! Undefined control sequence.` + `l.<行号> \xxx`
- 根因 A：缺宏包（如 `\SI` 需 siunitx、`\toprule` 需 booktabs、`\subfloat` 需 subcaption）。
  修复：导言区补 `\usepackage{...}`，先确认模板未加载冲突包（method_rules.md §5）。
- 根因 B：命令拼写错误（`\textwidth` 打成 `\textwith`）。修复：改拼写。
- 根因 C：该命令属于另一引擎/类（如在 article 下用 `\chapter`）。修复：改用模板支持的等价结构。
- **禁忌**：直接删除出错命令"消错"——功能丢失（failure_modes F5）。

## E2 缺宏包/文档类（missing_package）

- 日志特征：`! LaTeX Error: File 'xxx.sty' not found.`（或 `xxx.cls`）
- 根因 A：环境未安装该宏包。修复：①优先改用环境已有宏包的等价写法（如算法环境 algorithm2e 缺失时改用模板自带方案）；②确需该包且允许安装时按发行版方式安装（tlmgr install xxx）并在 build_record 记录；③模板强制依赖且无法安装 → status=partial，日志留存。
- 根因 B：包名打错（`booktab` vs `booktabs`）。修复：改名。
- 根因 C：自建 .sty 未随工程交付。修复：补文件进工程。

## E3 数学模式错误（math_mode）

- 日志特征：`! Missing $ inserted.`、`! Double subscript.`、`! Double superscript.`、`! Display math should end with $$`、`! Extra }, or forgotten $.`
- 根因 A：正文文本模式写了数学符号（`x_i`、`α` 写成 `\alpha`、`_`、`^`）。
  修复：把符号包进 `$...$`；下划线要文本时用 `\_`。
- 根因 B：公式环境里又套 `$...$`（equation 内 `$x$`）。修复：去掉内层 `$`。
- 根因 C：`x_i_j` 双下标。修复：明确分组 `x_{i_j}` 或 `x_{i,j}`。
- 根因 D：`$$...$$` 或未闭合环境。修复：改用 equation/align 环境（style_guide.md §2）。
- **注意**：一处 Missing $ 会级联几十条后续错误，只修首处即重编。

## E4 环境不匹配（environment）

- 日志特征：`! LaTeX Error: \begin{X} on input line N ended by \end{Y}.`、`! Extra \end.`、`! Lonely \item--perhaps a missing list environment.`
- 根因 A：`\begin`/`\end` 名字不一致或漏 `\end`。修复：按 tex_static_check.py 报的行号补齐/改名。
- 根因 B：`\item` 出现在列表环境外。修复：包进 itemize/enumerate/description。
- 根因 C：嵌套顺序错误（先 \end 外层再 \end 内层）。修复：调整 \end 顺序。

## E5 浮动体错误（float）

- 日志特征：`! Unknown float option 'H'.`、`! Too many unprocessed floats.`、`! Not in outer par mode.`、`Float(s) lost.`
- 根因 A：`[H]` 需要 float 宏包未加载。修复：优先把 `[H]` 改回 `[htbp]`（更符合模板版式）；确需定死再加 `\usepackage{float}` 并记录理由。
- 根因 B：浮动体堆积（连续多图无正文间隔）。修复：调整位置参数、`\clearpage`、拆小浮动体；不靠缩放。
- 根因 C：在盒子/公式/页眉里放 figure。修复：移出到正文层。

## E6 编码与字体（encoding）

- 日志特征：`! Package inputenc Error: Unicode char ... not set up for use with LaTeX.`、`Missing character: There is no ... in font ...`、字体相关 `! fontspec error`。
- 根因 A：pdflatex 下出现中文/特殊 Unicode 字符（弯引号 ' '、破折号 —、希腊字母）。修复：替换为 LaTeX 写法（`---`、`$\alpha$`），或整体迁移 xelatex+ctex（以模板允许为准）。
- 根因 B：文件非 UTF-8 编码（GBK 残留）。修复：统一转 UTF-8 无 BOM。
- 根因 C：字体缺失（模板指定字体环境没有）。修复：换环境可用字体须在 change_log 说明；模板强制 → partial 并记录。

## E7 缺文件（file_not_found）

- 日志特征：`! LaTeX Error: File 'xxx' not found.`（xxx 为图/章节/.bib，非 .sty/.cls）、`! Package pdftex.def Error: File 'figs/x.pdf' not found.`
- 根因 A：\input/\includegraphics 路径错（大小写、相对层级）。修复：按工程实际结构改相对路径。
- 根因 B：文件根本没交付/没生成（漏拷贝、图未导出）。修复：补文件；图缺失时用占位图必须标注 [待确认] 并在 evidence_map 登记，不得静默留空。
- 根因 C：扩展名与引擎不兼容（pdflatex 引用 .eps）。修复：转 PDF/PNG 并记录转换。

## E8 引用与参考文献（citation / reference）

- 日志特征（多为 warning）：`LaTeX Warning: Citation 'xxx' on page N undefined.`、`Reference 'xxx' on page N undefined`、`There were undefined references.`、`Please (re)run Biber/BibTeX.`、`LaTeX Warning: Label(s) may have changed. Rerun to get cross-references right.`
- 根因 A：轮次不够（最常见）。修复：按 method_rules.md §2 补 bibtex/biber + 两遍 pdflatex。
- 根因 B：\cite 的 key 在 .bib 不存在（打错或 .bib 缺条目）。修复：tex_static_check.py 交叉核对；补条目或改 key。
- 根因 C：\ref 指向不存在的 \label。修复：补 \label 或修正引用；tex_static_check.py 检出。
- 根因 D：bib 条目语法错导致 bibtex 失败。修复：读 .blg 日志修条目。

## E9 版式警告（overfull）

- 日志特征：`Overfull \hbox (xxpt too wide) ...`、`Underfull \hbox ...`
- 定性：警告不是错误，最后统一处理；不阻塞交付但要在 build_record 记录严重项（>20pt）。
- 修复方向：长公式折行（split）、长 URL 用 `\url{}` 并考虑 `\sloppy` 局部、宽表按 style_guide §3 顺序治理、长单词加断字点 `\-`。
- **禁忌**：`\resizebox` 全局缩、把 `\hsize` 改大、调页边距——都是模板红线。

## E10 致命与中止（fatal）

- 日志特征：`! Emergency stop.`、`! Fatal error occurred, no output PDF file produced!`、`! TeX capacity exceeded`
- 根因 A：Emergency stop 多是前面某个错误的终点——往上找第一个 `!`。
- 根因 B：TeX capacity exceeded 多为无限递归宏或失控循环（如 \newcommand 自引用）。修复：检查最近新增的自定义命令。
- 根因 C：磁盘/权限问题（写不出 .aux）。修复：换可写工作目录 /app/work。

## 修复顺序建议

1. 先修 E2/E7（缺包缺文件）——这类错误让后续所有内容失去定义；
2. 再修 E4 环境不匹配与 E3 数学首错——级联大户；
3. 然后 E1 未定义命令、E6 编码；
4. 最后处理 E8 引用轮次与 E9 版式警告；
5. 每修一处即重编，以 log_triage.py 重新归类，直至退出码 0。
