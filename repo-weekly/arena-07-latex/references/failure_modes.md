# 基础 Agent 在本题的 10 类典型失败与对策（写作13）

以下失败模式来自基础 Agent 在"LaTeX 写作与编译"任务上的常见表现，每条给出本 Skill 的对策及其落地位置。这些对策直接支撑"使用增益/创新增益"评分。

## F1 编译一遍就交付，引用全是 ??

- **表现**：只跑一次 pdflatex，交叉引用和参考文献全是 `??`，还声称"编译成功"。
- **对策**：编译链规则（method_rules.md §2）强制正确轮次；收敛判据写进质量门（最终日志无 Rerun/undefined）；`log_triage.py` 检出 undefined references 提示补轮次。

## F2 停在第一条错误信息上

- **表现**：日志里几十条错误，Agent 看了第一条就宣布"无法修复"或开始乱改；不知道后面的错误多是级联。
- **对策**：`log_triage.py` 把全部 `!` 错误按类型归类并定位 文件:行号；method_rules.md §3 明确"只修首错、重编再评估"的级联处置纪律。

## F3 编造编译状态

- **表现**：实际编译失败，却交付旧 PDF/截图并声称成功；或把 Overfull 警告说成"无错误通过"。
- **对策**：契约强制"编译失败保留 .log + status=partial"；`selfcheck.py` 检查 PDF 缺失时必须有日志与说明；build_record.md 要求记录真实命令与轮次。

## F4 擅改模板样式

- **表现**：直接改题目给定的 .cls/.sty，或 \renewcommand 重定义模板命令"微调"版式。
- **对策**：模板红线（method_rules.md §4）：模板逐字节不改，质量门要求与 /input 原件比对；版式问题只能走模板选项与文档。

## F5 删命令消错误

- **表现**：遇到 Undefined control sequence 就删除"出错"的命令/环境——功能随之消失，错误"消失"。
- **对策**：error_fix_table.md 对每类错误给出"保功能"修法（Undefined control sequence → 补宏包或改用等价命令，而非删除）；change_log 要求记录每个修复的根因。

## F6 缩放掩盖版式问题

- **表现**：`\resizebox{\textwidth}{!}{表格}` 缩到 6pt 字号；所有浮动体 `[H]` 定死位置造成大片空白。
- **对策**：浮动体与图表规则（method_rules.md §6 + style_guide.md §3/4）给出宽表治理顺序与 `[htbp]` 默认；反模式集明确禁止。

## F7 工程不可重建

- **表现**：只交 main.tex，漏交 \input 的章节文件和图片；路径写绝对路径；不记录 TeX 版本与命令。
- **对策**：`tex_static_check.py` 检查 \input/\include 文件存在性；templates/project_structure.md 规范工程组织；build_record_template.md 强制记录环境+命令+轮次；质量门要求清理中间文件后重编验证。

## F8 参考文献流程混乱

- **表现**：任务给了 .bib 却手写 thebibliography；改了 .bib 不重跑 bibtex；\cite key 打错没人发现。
- **对策**：编译链规则含 bibtex/biber 轮次；`tex_static_check.py` 交叉核对 \cite 与 .bib 条目，缺失即报错；style_guide.md §5 规范引用写法。

## F9 强制更换编译器

- **表现**：见稿件含汉字就把题目/模板指定的 pdflatex 编译链强制换成 XeLaTeX，还改写导言区适配——破坏了题目指定的构建方式，真实迭代（53→58 分段）中因此掉分。
- **对策**：编译器选择顺序（method_rules.md §2）：题目/模板指定 > 工程现有配置 > 启发式默认；**禁止强制更换引擎**，确需更换必须有模板/工程依据并记 change_log；selfcheck WARN 提醒 build_record 写明实际引擎，便于复核。

## F10 脚本改写源码、诊断夸大

- **表现**：写脚本用正则批量"自动修复"用户 .tex（误改语义、引入新错）；或把日志里的警告说成"编译失败"、把猜测写成"根因"——用户失去对诊断的信任。
- **对策**：脚本红线（method_rules.md §9）：tex_static_check/log_triage/selfcheck/contract_check 只诊断与建议、绝不改写源码，改写由模型按真实根因判断；log_triage.py 输出分"错误（阻断编译）/警告（不阻断）"两级，警告不夸大成错误。
