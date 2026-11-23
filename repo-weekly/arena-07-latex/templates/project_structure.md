# LaTeX 工程结构模板与模板适配规则（写作13）

## 1. 推荐工程布局

```
<project>/
  main.tex            # 唯一编译入口：含 \documentclass，导言区，\input 各章
  preamble.tex        # （可选）自定义命令与宏包集中地，主文件 \input{preamble}
  sections/           # 章节，一章一文件
    intro.tex
    methods.tex
    experiments.tex
    conclusion.tex
  figures/            # 图：PDF（矢量）/PNG（位图）
  tables/             # （可选）复杂表格单独成文件 \input 进来
  refs.bib            # 参考文献（任务给定则沿用给定文件）
  <template>.cls      # 题目给定模板（只读，不改）
  <template>.sty      # 题目给定样式（只读，不改）
```

规则：
- 主文件唯一入口；章节用 `\input{sections/xxx}`（短章）或 `\include`（长章、需独立分页）；
- 所有引用用相对路径，禁止绝对路径与 `..`；
- 任务给定的模板文件、参考文献样式（.bst/.bbx）原样保留在工程根目录。

## 2. 主文件骨架（导言区组织）

```latex
\documentclass{<模板类>}        % 选项以模板文档为准，不自增版式选项
% ---- 宏包（只加模板没有的，逐个注释理由）----
\usepackage{amsmath,amssymb}   % 数学（若模板未含）
\usepackage{booktabs}          % 三线表
\usepackage{graphicx}          % 插图
% hyperref 最后加载（除非模板另有规定）
% ---- 自定义命令（集中、注释、防冲突命名）----
\newcommand{\ours}{Ours}
\begin{document}
% ---- 模板必填项（逐项核对，缺材料标 [待确认]）----
\title{...}
\author{...}
\maketitle
\begin{abstract}...\end{abstract}
\input{sections/intro}
\input{sections/methods}
\input{sections/experiments}
\input{sections/conclusion}
\bibliographystyle{<模板指定>}
\bibliography{refs}
\end{document}
```

## 3. 模板适配检查单

- [ ] 模板 .cls/.sty 与 /input 原件逐字节一致（未改）；
- [ ] documentclass 选项与模板示例一致；
- [ ] 必填项（title/author/affiliation/abstract/keywords，以模板示例为准）逐项落实或标 [待确认]；
- [ ] 旧稿迁入时清理了与模板冲突的宏包与自定义命令（change_log 有记录）；
- [ ] 新增宏包不与模板加载顺序冲突（hyperref/cleveref 顺序正确）。

## 4. 编译入口识别（材料已有工程时）

1. 找含 `\documentclass` 的 .tex → 候选主文件；多个候选时以任务说明/模板示例为准并记录依据；
2. grep `\bibliography` / `\addbibresource` / `thebibliography` 判断参考文献流程（bibtex/biber/手写）；
3. grep `\documentclass` 行与模板文件名判断引擎（ctex/字体包 → 可能需 xelatex）；
4. 把识别结果写进 `/app/work/structure_note.md`。
