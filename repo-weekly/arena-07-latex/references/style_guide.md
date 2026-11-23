# LaTeX 源码风格规范（写作13）

## 1. 源码可读性

- 一句一行（或按语义断行），便于 diff 与审阅；不用 2000 字符长行；
- 章节入口用 `% ===== 章节名 =====` 风格的分隔注释；自定义命令集中定义并注释用途；
- 不留大段注释掉的死代码；临时注释写明原因（`% TODO(待确认): ...`）；
- 缩进体现环境嵌套层次；`\begin`/`\end` 成对同行内可快速目检；
- 事实性内容（数值、版本、数据）来源用行尾注释 `% [S#]` 标注，并登记 evidence_map.md。

## 2. 数学公式

- 行内公式 `$...$`，独立公式用 `equation`/`align` 环境，不用 `$$...$$`（LaTeX 中已废弃）；
- 需要引用的公式必须 `\label` + `\eqref`；不引用的用 `equation*`；
- 多行公式用 `align`/`aligned` 在关系符号处对齐；长公式折行用 `split`；
- 变量斜体、函数与算子正体（`\sin,\log,\max`，自定义算子 `\DeclareMathOperator`）；单位正体（`\mathrm{m/s}` 或 siunitx `\SI{}{}`）；
- 上下标多层时用花括号明确分组：`x_{i+1}` 不依赖"恰好没出错"；避免双下标裸写 `x_i_j`；
- 符号全文一致：与材料/模板既有记法对齐，不在本稿自创冲突符号。

## 3. 表格

- 三线表：`\toprule`、`\midrule`、`\bottomrule`（booktabs），不用竖线与 `\hline` 网格；
- 列格式明确：数值列用 `S`（siunitx）或 `r`，文本列 `l`/`p{宽度}`；
- 宽表治理顺序：精简列 → `p{}` 列换行 → `\small`/`\footnotesize` → `tabularx` → 旋转页；不用 `\resizebox`；
- 跨页长表用 `longtable`，表头重复设置正确；
- 表内数值与材料逐字一致，单位进表头不进单元格（如 "温度 (K)"）。

## 4. 图与浮动体

- 位图用 PNG/JPG、矢量图用 PDF；与 pdflatex 链兼容（EPS 需 epstopdf，避免）;
- `\includegraphics[width=0.8\textwidth]{...}` 相对宽度；不写死 `17cm` 这类依赖版心的尺寸；
- 浮动参数默认 `[htbp]`；图/表都有 `\caption` 与 `\label`，且正文用 `\ref` 引用（"Figure~\ref{fig:x}"，用 `~` 防断行）；
- 子图用 `subcaption` 宏包的 `subfigure` 环境（不用过时 subfigure 包）。

## 5. 引用与参考文献

- 文献引用统一 `\cite{key}`，key 用 `作者年关键词` 风格（`smith2020deep`），新增 .bib 条目字段完整（author/title/year/journal 或 booktitle）；
- \cite 前用 `~` 连接（`as shown in~\cite{...}`）；
- 不用手写 `thebibliography` 替代任务给定的 .bib 流程；
- 交叉引用：章节 `\label{sec:methods}`、图 `fig:`、表 `tab:`、公式 `eq:`，前缀风格全文统一；
- 参考文献样式以模板为准（模板给 .bst/biblatex 设置就不自加）。

## 6. 编码与中文

- 全部源文件 UTF-8 无 BOM（脚本读取用 utf-8-sig 容错，但交付统一无 BOM）；
- pdflatex 工程：`\usepackage[utf8]{inputenc}`（老发行版需要）；中文内容用 xelatex + ctex/xeCJK 方案，不在 pdflatex 下硬编中文；
- 特殊字符转义：`% & # _ ^ ~ \ $`；URL 用 `\url{}` 不裸贴；
- 中文与西文混排时空格交给 xeCJK 处理，不手工塞 `~`。

## 7. 与模板共处

- 模板已定义的命令/环境优先使用（如模板自己的 \abstract 环境、定理环境）；
- 自定义命令加项目前缀防冲突（`\newcommand{\ours}{...}`），不覆盖模板命令；
- 版式参数（页边距、行距、字号）一律不碰，交给模板。
