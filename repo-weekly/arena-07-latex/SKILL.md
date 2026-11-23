---
name: compiling-latex-manuscripts
description: 在给定 LaTeX 工程与模板约束下完成稿件写作、修复与可重复构建：先清点工程结构并确认模板与编译链，用静态检查脚本发现未闭合环境、未定义 \ref/\cite、缺文件等问题，按 pdflatex→bibtex/biber→pdflatex×2 或 latexmk 链实际编译并用日志分类脚本把错误按未定义引用/缺宏包/数学模式/浮动体/编码等类型定位到文件行号逐个修复，遵守模板样式不擅改，交付可编译源码、真实编译 PDF 预览与编译记录；编译失败时保留日志并诚实标注 partial。当任务要求读取 /input/case.json 并完成"LaTeX 写作/编译修复/模板适配/可重复构建"时使用。
---

# LaTeX 写作与编译（Compiling LaTeX Manuscripts）

## 用途与触发

当任务要求在给定材料与模板约束下**撰写/补全 LaTeX 源码、修复编译错误、适配期刊会议模板、交付可编译工程与 PDF 产物**时使用本 Skill。核心目标四句话（对应题面"编译得通/改得对/交得可用/复现得了"）：

- **编译得通**：按正确编译链与轮次编译通过，每个报错定位到文件、行号与根因，不停在第一条错误信息上；
- **改得对**：公式、表格、交叉引用、参考文献、版式既合原文意图又合模板要求；
- **交得可用**：交付结构清楚、可继续编辑的 .tex 源码与配套文件，不用 PDF 截图或不可编译片段冒充结果；
- **复现得了**：编译记录写明 TeX 发行版、宏包/字体依赖、编译命令与轮次，他人能重建同一份 PDF。

**不应触发的邻近场景**：① 只要求把一段 LaTeX 公式翻译成自然语言或解释其含义（按一般问答处理）；② 任务交付物是 Word/Markdown 稿件、不要求 .tex 源码与编译（用写作类 Skill，不要强行 LaTeX 化）。

## 运行环境契约

1. 输入在 `/input/`：`case.json`、`task.md` 与材料文件（可能是 .tex 工程、模板 .cls/.sty、.bib、图片、参考 PDF）。**先读真实文件**，不按文件名臆测内容。
2. 先解析 `/input/case.json`：取 `case_id` 与 `output_contract`；最终 `/app/output/result.json` 必须含 `case_id` 和 `output_contract` 声明的**全部原始字段**（字段名以 case.json 为准）。
3. 工作文件放 `/app/work/`，最终交付放 `/app/output/`：.tex 工程源码（含配套 .bib/图/样式文件）、真实编译的 PDF 预览、`build_record.md`、`evidence_map.md`、`result.json`（诚实 status: success/partial/failed + sources + uncertainty + change_log）。
4. 环境提供 latex-compiler（以 environment/resources.yaml 为准）；**编译失败时保留完整 .log 到 `/app/output/` 并在 result.json 诚实标注 partial，严禁谎称编译成功**。
5. 预算：64 次模型请求 / 900 秒 / 每响应 16384 token。**先落盘一版能编译的最小骨架（哪怕内容不全），再迭代补内容**。
6. 禁止：预制答案、编造编译状态或科学数据、擅自改动题目给定模板的样式定义。
7. **验证与限制声明**：本 Skill 的脚本与流程只在本地合成 fixture 上验证过（examples 中均标注合成）；平台的 3 个隐藏评测案例与对照组从未在本地运行，本包不声称、不暗示任何评测分数。所有工程与日志以运行时 `/input/` 实际文件为准。

## 脚本调用规则

五个脚本均在 `/skills/weekly-skill/scripts/`，**必须用绝对路径**调用，不依赖 CWD：

```bash
python3 /skills/weekly-skill/scripts/inventory.py --input /input --out /app/work/materials_register.md
python3 /skills/weekly-skill/scripts/tex_static_check.py --main /app/work/main.tex --report /app/work/static_check.md
python3 /skills/weekly-skill/scripts/log_triage.py --log /app/work/main.log --report /app/work/log_triage.md
python3 /skills/weekly-skill/scripts/contract_check.py --case /input/case.json --result /app/work/result_draft.json
python3 /skills/weekly-skill/scripts/selfcheck.py --output /app/output --case /input/case.json
```

- `tex_static_check.py`：编译前的源码静态检查（未闭合环境、未定义 \ref/\cite、缺 \input 文件、括号/数学模式失衡）。退出码 1 = 存在错误级发现。
- `log_triage.py`：解析 .log，输出分**两级——错误（阻断编译）/警告（不阻断）**，错误按类型归类（未定义引用/缺宏包/数学模式/浮动体/编码/缺文件/其他），给出修复建议并定位到文件与行号。退出码 1 = 日志中存在错误（`!` 开头）。
- `contract_check.py`：**写 result.json 之前的契约前置校验（建议性）**——草稿先过它核对 case_id 与 output_contract 全部字段齐全；退出码 1 表示存在建议修复项，能修则修一轮，修不完的逐项写入 uncertainty 与 skipped_reason，然后照常落盘为 `/app/output/result.json`；任何退出码都不阻止交付。
- **脚本红线（v2）**：所有脚本只做**诊断与建议**（只读源码/日志、输出报告），**绝不自动改写用户的 .tex/.bib 源码**；是否改、怎么改由模型按诊断与真实根因判断。诊断不得夸大：警告就是警告，不把警告说成错误，不把猜测说成根因。
- **降级声明**：若脚本缺失或运行失败，不得中断任务——改用手工执行同等检查（通读配对的 \begin/\end、grep 全部 \ref 与 \label、从日志第一个 `!` 逐条人工归类、对照 case.json 逐字段打勾），并在 `result.json` 的 `change_log` 中记录"脚本不可用，已手工复核"。

## 主流程（七步）

### 交付优先原则（v3，最高优先级）

- **先有交付，再求完美**：任何时刻 `/app/output/` 里都要有一份当前最好的可交付物（哪怕是 status=partial 的诚实工程 + 日志 + result.json）；先完成、再完美，严禁把"全部校验通过"作为落盘前提；
- **请求预算分配（64 次）**：≤10 次读材料与契约；≤30 次产出主交付物（工程 + 编译）；≤10 次校验与修复；剩余全部留给 finalize（落盘交付物 + 写 result.json）；
- **预算红线**：预算过半仍未落盘初稿 → 立即停止新探索，把当前版本落盘；剩余约 10 次请求 → 停止一切修复与校验，直接 finalize；
- **脚本两轮封顶**：每个脚本最多运行 2 次（首次检查 + 修复后复查一次）；两轮后无论结果如何都进入交付，未修复项逐项写入 result.json 的 uncertainty 与 skipped_reason。任何脚本退出码都不阻止交付。

### 第 0 步　解析契约
读 `/input/case.json` 与 `/input/task.md`：记下 `case_id`、`output_contract` 全部字段名、任务要求的改动点清单、指定模板与编译方式。逐条抄到 `/app/work/contract_note.md`，后续所有产出对照此清单。

### 第 1 步　工程清点与模板确认
运行 `inventory.py` 生成 `/app/work/materials_register.md`（S1..Sn）。确认：主文件是哪个（含 \documentclass 者）、章节/图表/参考文献如何组织、题目给定模板（.cls/.sty）是哪些。**模板样式文件只读不改**；在 `/app/work/structure_note.md` 画出工程结构（对照 `templates/project_structure.md`），标出模板必填项（题名/作者/摘要/关键词等）现状。

### 第 2 步　内容写作/迁移（改动点逐项落实）
按任务要求完成写作或迁入模板。规则（详见 `references/method_rules.md` 与 `references/style_guide.md`）：
- 每个改动点对应可定位的源码改动，记入 `/app/work/change_plan.md`；
- 事实与数值只能来自给定材料，来源挂 `[S#]` 注释或登记 `evidence_map.md`；
- 公式、表格、浮动体、引用写法遵守 style_guide；新增宏包前查与模板加载顺序的冲突，并在 change_plan 说明理由。
产出：`/app/work/` 下的完整工程（主文件 main.tex 或任务指定名）。

### 第 3 步　编译前静态检查
运行 `tex_static_check.py`。所有错误级发现先修复（静态错误编译必炸或必出 ??），修复后复查一次（每个脚本最多两轮）再进编译——这一步能省掉大量编译轮次；两轮后仍有错误的记入 uncertainty，不阻塞后续编译与交付。

### 第 4 步　按正确编译链构建
**先定编译器，顺序：题目/模板指定 > 工程现有配置（latexmkrc/Makefile/.cls 要求）> 启发式默认（pdflatex）。禁止强制更换编译器**——不因"含汉字"就强制换 XeLaTeX；确需更换必须有任务/模板/工程依据并记 change_log（规则详见 `references/method_rules.md` §2）。再按 `references/method_rules.md` §2 选链：
- 有 .bib 用 BibTeX：`pdflatex → bibtex → pdflatex → pdflatex`；
- 用 biblatex/biber：`pdflatex → biber → pdflatex → pdflatex`；
- 或 `latexmk -pdf`（自动处理轮次）。
工作目录设为工程目录，所有编译在 `/app/work/` 进行。**每轮编译日志留存**（`build_round1.log` …），交叉引用类警告必须编到收敛（日志无 "Rerun" 提示、无 undefined references）。**依赖构建**：先从 .tex/.bib 依赖关系（\input/\includegraphics/\bibliography）理清工程再动手；多轮编译直至引用稳定，最终以真实编译的 PDF 作预览，不用截图或旧文件冒充。

### 第 5 步　错误分类与修复闭环
编译失败或有错误：运行 `log_triage.py` 解析最新 .log——输出分两级：**错误（阻断编译，必须修）/警告（不阻断，按需处理）**。按 `references/error_fix_table.md` 的对照表**从第一个错误开始**修（级联错误常由首错引发，修一个重编一次，不批量盲改）。每个修复记录：错误类型、文件:行号、**真实根因**、改法，写入 `build_record.md`；诊断按脚本报告与日志原文说话，不夸大（警告不说成错误）、不臆断根因。修复→重编→再解析，直至编译通过、确认是环境缺失（缺宏包/字体且无法安装），或触发预算红线（见"交付优先原则"：临近预算上限立即停止修复，保留日志、按 status=partial 照常交付当前工程）。**改写由模型判断执行**，不用脚本批量改写源码。

### 第 6 步　交付与自查
1. 把工程源码（.tex/.bib/图/任务提供的模板文件）与最终 PDF 复制到 `/app/output/`；编译失败时复制最后一份完整 .log 并在 PDF 位置放 `PDF_FAILED.md` 说明；
2. 填 `/app/output/build_record.md`（模板 `templates/build_record_template.md`）：TeX 发行版、编译链、轮次、错误与修复记录、字体/宏包依赖；
3. 填 `/app/output/evidence_map.md`（模板 `templates/evidence_map_template.md`）：材料登记、改动点→源码位置映射、待确认项；
4. **契约前置校验（建议性）**：result.json 先起草为 `/app/work/result_draft.json`（模板 `templates/result_json_template.md`；失败/跳过阶段附 skipped_reason），运行 `contract_check.py --case /input/case.json --result /app/work/result_draft.json`；FAIL 项能修则修一轮并复查一次，修不完的逐项写入 uncertainty 与 skipped_reason，然后**照常落盘为 `/app/output/result.json`**——退出码仅供定位问题，不作为交付门禁；
5. 运行 `selfcheck.py`：有 FAIL 修复后复查一次（每个脚本最多两轮）；两轮后仍无法修复的在 uncertainty 说明、降 status 为 partial 并照常交付。WARN 项只提醒、不阻断交付，但需在 change_log 记录已知 WARN。

## 质量门（自查清单，不阻塞交付）

本节是交付前的自查清单而非门禁：任何一项不满足都不阻止交付——FAIL 项能修则修一轮，修不完的逐项写入 result.json 的 uncertainty 与 skipped_reason，然后照常落盘交付。对照 `references/element_checklist.md` 逐项打勾，关键锚点（建议性）：

- [ ] `tex_static_check.py` 已运行且错误级发现已修一轮（编译前；两轮后剩余项记入 uncertainty）；
- [ ] 编译链与轮次正确，最终日志无 `!` 错误、无 undefined references/citations（log_triage.py 验证）；
- [ ] PDF 是本次真实编译产物，不是旧文件或截图（build_record 记录编译时间与命令）；
- [ ] 模板 .cls/.sty 零改动（与 /input 原件逐字节一致）；
- [ ] 任务改动点逐项落实并可在 evidence_map 回溯；
- [ ] 编译器选择符合"题目/模板指定 > 工程现有配置 > 启发式默认"顺序，未强制更换引擎；换引擎必有依据且记 change_log；
- [ ] `result.json` 含 case_id 与契约全部字段，status 诚实（编译失败=partial/failed 且附日志）；落盘前已运行 `contract_check.py`（FAIL 项已记入 uncertainty）；
- [ ] **负路径自测已做**：至少跑过一个"必须被拒绝"的用例并确认被拦截（退出码 1），如：无 PDF 却 status=success 的 result.json（selfcheck 应 FAIL）、缺契约字段的 result 草稿（contract_check 应 FAIL）、含 `!` 错误的日志（log_triage 应报错）。负路径用例放 `/app/work/` 并标注合成，不得混入 `/app/output/` 交付物。

## 反馈回路

```
log_triage.py 归类错误 → 回第 2/3 步修首错 → 重跑 tex_static_check.py
→ 重新编译 → 再解析日志 → 收敛后跑 selfcheck.py → FAIL 修一轮后复查一次
→ 两轮后仍有 FAIL：记入 uncertainty/skipped_reason，立即交付
预算将尽 → 停止扩内容与修复，保证当前工程、PDF（或完整日志）与记录已落盘，
  按诚实 status 直接 finalize
```

**宁可交付内容较少但编译通过、记录完整的工程，不交付内容很全但编不过的工程。**

## 异常处理

- **finalize 永不空手（交付韧性）**：无论哪个阶段失败或超时，finalize 都必须导出可交付物——已完成的阶段按诚实状态交付（可编译工程/静态检查报告/日志分析），未完成/跳过的阶段在 result.json 的 `skipped_reason` 字段逐条写明原因；绝不允许 `/app/output/` 空交付或谎称成功；
- **新增检查只加 WARN**：selfcheck.py 后续新增的检查项一律 WARN 级——只提醒、不把原本能通过的交付判 FAIL；退出码只由 FAIL 项决定；
- **缺宏包/缺字体且环境无法安装**：改用在环境内可用的等价方案须在 change_log 说明；若模板强制依赖 → status=partial，保留日志并在 uncertainty 写明缺什么；
- **模板类文件缺失/损坏**：不得自己伪造同名 .cls，status=partial 并说明；
- **报错级联**（一处错误引发几十条）：只修首错，重编再评估，禁止按错误条数谎报进度；
- **材料与模板要求冲突**（如材料给的图是 .wmf 而模板只接受 PDF/PNG）：转换或重绘并记录，无法处理列待确认项；
- **权限不足/编译器缺失**：静态检查全做、工程交付、status=partial，build_record 写明"未能实际编译"及已做的替代验证；
- **超时/中断**：保证 `/app/output/` 已有可编译的工程 + PDF 或日志 + 诚实 status。

## 资源索引

- `references/element_checklist.md`——要素齐全性清单与评分锚点（交付前逐项勾）；
- `references/method_rules.md`——工程结构、编译链、错误定位与修复优先级的判定标准及"改了等于没改"反模式（>100 行，顶部有目录）；
- `references/style_guide.md`——LaTeX 源码风格：公式、表格、浮动体、引用、注释规范；
- `references/failure_modes.md`——基础 Agent 在本题的 8 类典型失败与对策；
- `references/error_fix_table.md`——编译错误→根因→修复对照表（按类型组织，log_triage.py 的分类依据）；
- `templates/project_structure.md`——标准工程结构与模板适配规则；
- `templates/build_record_template.md`——编译记录模板（环境、命令、轮次、修复留痕）；
- `templates/result_json_template.md`——result.json 透传规则与示意；
- `templates/evidence_map_template.md`——材料登记 + 改动点映射 + 待确认项模板；
- `examples/minimal_example.md`——最小调用示例（示意输出，非正式案例结果）；
- `examples/synthetic_case.md`——完整合成案例（全合成标注），含脚本实测与负路径用例；
- `scripts/inventory.py`——材料清点；`scripts/tex_static_check.py`——源码静态检查（只诊断不改写）；`scripts/log_triage.py`——编译日志分类（错误/警告两级）；`scripts/contract_check.py`——result.json 落盘前的契约字段前置校验；`scripts/selfcheck.py`——交付自查（新增项只 WARN）。
