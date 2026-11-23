# LaTeX 写作与编译：判定标准与反模式（写作13）

> 目录
> 1. 工程结构组织规则
> 2. 编译链与轮次规则（含编译器选择顺序）
> 3. 编译日志阅读法（从第一个错误开始）
> 4. 模板适配规则（不擅改的红线）
> 5. 宏包引入规则
> 6. 浮动体与图表规则
> 7. 可重复构建规则
> 8. "改了等于没改"反模式集
> 9. 脚本红线：只诊断不改写（v2）

## 1. 工程结构组织规则

1. 主文件唯一：只有一个含 `\documentclass` 的文件作为编译入口；存在多个候选时以任务说明/模板示例为准，并在 structure_note 记录选择依据。
2. 分层组织：章节进 `sections/` 或 `chapters/`（\input/\include），图进 `figures/`，参考文献进 `.bib`，自定义命令集中在导言区一个 `\input{preamble}` 或主文件导言区内——不散落在各处。
3. 相对路径：`\input{sections/methods}`、`\includegraphics{figures/x.pdf}`，禁止绝对路径与 `..`。
4. 迁移已有稿件进模板时：保留模板示例文件的骨架顺序（标题→作者→摘要→正文→致谢→参考文献），只替换内容不重排结构。

## 2. 编译链与轮次规则

| 工程特征 | 正确编译链 |
|----------|-----------|
| 无参考文献、无交叉引用变更 | `pdflatex main`（1 遍） |
| 有 \ref/\cite、用 BibTeX | `pdflatex main && bibtex main && pdflatex main && pdflatex main` |
| 用 biblatex+biber | `pdflatex main && biber main && pdflatex main && pdflatex main` |
| 不确定/图省事 | `latexmk -pdf -interaction=nonstopmode main`（自动定轮次） |
| 中文模板要求 XeLaTeX/LuaLaTeX | 以模板文档为准替换引擎，轮次规则相同 |

规则：
1. **编译器选择顺序（v2，失败教训固化）**：**题目/模板指定 > 工程现有配置（latexmkrc、Makefile、.cls 的引擎选项、注释中的构建说明）> 启发式默认（pdflatex）**。**禁止强制更换编译器**——真实教训：只因稿件含汉字就强制换 XeLaTeX，反而破坏了题目指定的编译链导致掉分。模板用 ctex/字体宏包常要求 xelatex，不要擅自用 pdflatex 硬编再报"模板有问题"；反之，题目/模板指定 pdflatex 时也不要擅自换 xelatex。确需更换引擎的情形只有：模板/工程明确要求，或当前引擎确认无法支持（缺字体且无法安装、模板类文件强制引擎特性）——必须写入 change_log 说明依据；
2. 每轮都用 `-interaction=nonstopmode` 并保留日志（`build_roundN.log`）；
3. 收敛判据：最后一轮日志无 "Rerun"、无 "undefined references/citations"、无 `!` 错误；
4. 改了 .bib 必须重跑 bibtex/biber 再两遍 pdflatex，只跑一遍 pdflatex 等于没更新参考文献；
5. **依赖构建**：动手编译前先从 .tex/.bib 依赖关系理清工程（\input/\include 链、\bibliography 指向、图片引用），tex_static_check.py 即按此依赖图检查；多轮编译直至引用稳定（收敛判据见上），最终预览必须是本次真实编译的 PDF。

## 3. 编译日志阅读法（从第一个错误开始）

1. 真正的错误以行首 `!` 开头；其后的 `l.<行号>` 给出源文件行号——这是定位锚点；
2. **级联规律**：一个错误常引发后面几十条错误（典型：缺 `$` 后全文报数学错误；缺 `.sty` 后所有该包命令报 Undefined control sequence）。只修第一个错误，重编，再评估；
3. 警告分级：`Undefined references/citations` 多为轮次不够，按 §2 补轮次，不急着改源码；`Overfull \hbox` 是版式警告，最后统一处理；
4. 定位文件：日志用成对圆括号标记进入/离开文件，出错位置前最近打开的 .tex 即出错文件；log_triage.py 自动做近似定位；
5. 禁止停在第一条错误信息上就交付"无法修复"——先用 log_triage.py 归类全部错误再制定修复顺序。

## 4. 模板适配规则（不擅改的红线）

1. 题目给定的 `.cls`/`.sty` **逐字节不得修改**；版式不合预期时先查模板文档的用法选项（documentclass 选项、模板提供的命令），不改模板本体；
2. 不用 `\renewcommand` 重定义模板内部命令来"微调"版式（行距、页边距、标题样式）——这违反"遵守模板样式"要求；
3. 模板必填项逐项核对（题名/作者/单位/摘要/关键词/基金等，以模板示例为准），缺材料填不了的标 [待确认]，不编假作者假单位；
4. 迁入旧稿时，旧稿导言区与模板冲突的宏包/命令必须清理并在 change_log 记录；
5. 模板给的示例 .tex 是最权威用法说明，先读示例再动笔。

## 5. 宏包引入规则

1. 新增宏包前先确认模板没已加载同名/同功能包（grep 模板与主文件 `\usepackage`）；
2. 已知冲突组合避免：amsmath 先于一切数学包；hyperref 基本最后加载（cleveref 在 hyperref 之后）；inputenc/fontenc 在 xelatex 下不要加载；
3. 每加一个宏包，在 change_plan 写一行"为什么需要它"；编译行为变化时先怀疑最近加的包；
4. 缺宏包（`File 'xxx.sty' not found`）：优先用环境已有包实现同等功能；确属环境缺失且无法安装 → 按异常处理诚实标注 partial。

## 6. 浮动体与图表规则

1. 位置约束按 `[htbp]` 起步，不要无脑 `[H]`（会制造大片空白与连锁乱版）；"Too many unprocessed floats" 说明浮动体堆积，用 `\clearpage`/调整位置解决，不是靠缩放；
2. 图：宽度用 `\textwidth` 的相对值（如 `width=0.8\textwidth`），不写死厘米；位图分辨率不足如实记录，不用拉伸掩盖；
3. 表：优先三线表（booktabs：\toprule/\midrule/\bottomrule），不用竖线网格；宽表用 `tabularx`/`\small`/旋转页（pdflscape）解决，**禁止 `\resizebox{\textwidth}{!}{...}` 缩表**（字号失控、掩盖设计问题）；
4. 每个浮动体有 `\caption` + `\label` 且正文有引用（"如表 1 所示"）；浮动体不得先于首次引用出现太远。

## 7. 可重复构建规则

1. build_record.md 必含：TeX 发行版与版本（如 TeX Live 2024）、引擎、完整命令序列、轮次数、非标准宏包与字体清单；
2. 工程自包含：所有 \input/\includegraphics/.bib 引用的文件都在工程内；
3. 不把本机特有的字体作为唯一方案；用了系统字体在 build_record 写明；
4. 清理中间文件后（latexmk -c 等价物）重编一次确认仍能从头构建。

## 8. "改了等于没改"反模式集

1. 只跑一遍 pdflatex 就交付——交叉引用和参考文献全是 `??`；
2. 看到 "Undefined control sequence" 就把那条命令删掉——功能没了，错误"消失"了；
3. 用 `\resizebox`/`\scalebox` 缩表格缩图来"修复" Overfull——字号忽大忽小，版式不合模板；
4. 给所有浮动体加 `[H]`——浮动体不再浮动，页面大片空白，还引入 float 包依赖；
5. 编译失败就改模板 .cls——违反模板红线，且通常修错方向；
6. 错误一大堆时从后往前改、批量盲改——级联错误越修越乱；
7. 交付"编译成功"但 PDF 是旧文件/截图，.log 里全是 `!`——编造编译状态，本题最重违规；
8. 把 main.tex 之外的 \input 文件漏交——别人拿到工程编不过；
9. 参考文献用手写 thebibliography 凑数而任务给了 .bib——编号与 \cite 对不上；
10. 中文内容直接塞进 pdflatex 工程不加 xeCJK/ctex 方案——编出一堆 Missing character。**但处置不等于强制换引擎**：按 §2 编译器选择顺序判断——题目/模板指定了引擎就服从指定（ctex 宏包在 pdflatex 下亦可处理中文）；只有模板/工程明确要求或现有引擎确认无法支持时才换 xelatex，并记 change_log；
11. 见汉字就强制换 XeLaTeX、重写用户导言区——破坏题目指定编译链与模板配置，真实迭代中因此掉分；
12. 写脚本批量改写用户 .tex 源码"自动消错"——脚本只能诊断，改写把语义风险转嫁给正则，等于盲改。

## 9. 脚本红线：只诊断不改写（v2）

1. **脚本只做诊断与建议**：tex_static_check.py / log_triage.py / selfcheck.py / contract_check.py 全部只读输入、只输出报告与退出码，**绝不自动改写用户的 .tex/.bib/.cls 源码**。是否修改、如何修改由模型按诊断结果与真实根因判断执行，并逐条记入 build_record/change_log。
2. **诊断分级，不夸大**：log_triage.py 输出分两级——**错误（阻断编译，必须修）**与**警告（不阻断，按需处理）**；警告不得说成错误（如 undefined references 首先是轮次问题），未验证的猜测不得写成"根因"——只能说"疑似，待重编验证"。
3. **真实根因优先**：每条修复记录写"错误类型 + 文件:行号 + 真实根因 + 改法"；根因未确认时先修首错重编再评估（§3 级联纪律），不靠错误条数谎报进度。
4. **失败教训来源**：53→58→62 的迭代表明——恢复成稿、契约字段、来源记录与**指定编译器**四项是基本盘；去掉"汉字强制 XeLaTeX"、去掉"脚本改写用户源码"后才稳定涨分。本红线即由此固化。
