---
name: parsing-scientific-papers
description: 把科研 PDF（含双栏/多栏排版、扫描件）解析为可复核的结构化结果：PDF 文字层提取与版面栏序还原、章节树与元数据（标题/作者/单位/摘要/图表题注/公式编号/参考文献）元素级解析、图表-正文引用关系回链、逐区块解析置信度标注、扫描件/加密/缺页等异常分级处置。当评测任务是读取 /input/ 中的论文 PDF 并产出带页码与区块定位的解析结果、结构化字段或基于原文证据的回答时使用。纯翻译任务不要触发本技能（用翻译类技能）；非科研文档的通用格式转换也不要触发。
---

# 科研文献 PDF 解析

## 1. 用途与触发

把一份真实科研 PDF 解析为**可核验**的结构化交付：逐字保真的正文（正确栏序）、章节树、元数据、图表题注与正文引用回链、公式编号对照、参考文献条目，并为每个区块标注来源页码/区块号与解析置信度；读不出的部分显式标注 `[NOT_READABLE]`，绝不猜测补齐。

触发语境：评测输入 `/input/` 含论文 PDF（可能双栏、扫描、加密），任务要求"解析/提取/结构化/回答并给出依据"。

不应触发：
- 任务是**翻译**文献 → 用 translating-scientific-literature 技能；
- 输入是结构化数据（CSV/JSON）的统计计算，无 PDF 版面问题。

## 2. 运行环境契约

- 先读 `/input/case.json`，提取 `case_id` 与 `output_contract`；`/app/output/result.json` 必须含 `case_id` 和 output_contract 声明的**全部原始字段**（字段名以 case.json 为准）。
- 工作文件在 `/app/work/`，最终交付在 `/app/output/`：主产物 `parsed_document.md`、`evidence_map.md`、`survey.json`、`result.json`（诚实 status、sources、uncertainty、change_log）。
- 预算：64 次模型请求 / 900 秒 / 单次响应 16384 token。**步骤 0 之后立刻落盘一份诚实的 partial result.json，再迭代改进。**
- 性能预算意识（v2）：900 秒限制下，大 PDF 用 `pdf_survey.py --first-page/--last-page` 分块清点；pdftotext 导出的 layout/raw 文本**只跑一次、落盘复用**，后续步骤一律读落盘文本，禁止对同一 PDF 重复全量提取（dense-page 重复解析是已知的预算杀手）；每完成一个阶段即落盘中产物。
- 交付韧性（v2）：任何阶段失败/中断时，运行 `finalize.py` 固化交付——已完成的诚实部分 + 逐条 skipped_reason，而非整案失败；写入/交付 result.json 前后跑 `contract_check.py` 核对契约字段齐全（建议性核对，任何退出码都不阻止交付）。
- 禁止：预制答案、编造原文内容、把读不出的内容写成事实。
- 脚本只用 Python 标准库；PDF 文本提取调用环境中的 pdftotext，缺失时降级登记（fallback：pdf-render-tool 渲染 → OCR；若环境预装 PyMuPDF，可在交互中作为提取 fallback，脚本不硬依赖）。

## 3. 脚本调用规则

- 一律按技能目录绝对路径调用，路径用正斜杠：
  `python3 /skills/weekly-skill/scripts/inventory.py --input /input --output /app/work/materials_register.md`
  `python3 /skills/weekly-skill/scripts/pdf_survey.py --pdf /input/<论文>.pdf --output /app/work/survey`（大 PDF 加 `--first-page 1 --last-page 20` 分块）
  `python3 /skills/weekly-skill/scripts/contract_check.py --case /input/case.json --result /app/output/result.json`（契约字段核对，建议性、不阻塞落盘）
  `python3 /skills/weekly-skill/scripts/finalize.py --work /app/work --output /app/output --case /input/case.json --skipped "步骤3: 原因"`（交付固化兜底）
  `python3 /skills/weekly-skill/scripts/selfcheck.py --output /app/output --case /input/case.json`
  `python3 /skills/weekly-skill/scripts/selftest.py`（负路径自测，全合成 fixture，可在准备阶段验证脚本可用性）
- 脚本缺失/不可执行时的降级：inventory → 手工逐个登记文件名/大小/可读性；pdf_survey → 手工记录页数与加密迹象、用 pdftotext 直接导出文本后人工画章节树、人工登记 OCR 页覆盖清单与表格区域；contract_check → 对照 contract_notes.md 逐字段人工核对；finalize → 手工写诚实 partial result.json（含 skipped_reason）；selfcheck → 对照 references/element_checklist.md 逐条人工勾选。
- 脚本只读输入目录，输出只写参数指定路径；不得依赖当前工作目录（CWD）。

## 4. 主流程

**交付优先原则（v3，最高优先级，先于下列一切步骤）**：
- (a) 任何时刻 `/app/output/` 里都要有一份**当前最好的可交付物**：先完成再完美，每完成一个阶段就用当前版本更新交付物，绝不把"全部做好"当作落盘前提。
- (b) 请求预算分配建议：≤10 次读材料与契约，≤30 次产出主产物，≤10 次校验与修复，其余请求与时间余量全部留给 finalize 与交付固化。
- (c) 预算过半仍无落盘初稿 → 立即停止打磨，把当前版本落盘；剩余约 10 次请求 → 停止一切修复与校验循环，直接 finalize 交付。
- (d) 每个校验脚本最多运行 2 次（首次检查 + 修复后复查一次）；两轮之后无论结果如何都进入交付：剩余 FAIL 逐项写入 result.json 的 uncertainty 与 skipped_reason，照常落盘。校验是建议性的自查，任何脚本退出码都不阻止交付。

**步骤 0｜契约解析（最先做）**：读 `/input/case.json` → 在 `/app/work/contract_notes.md` 逐字段抄录 output_contract 与任务要求 → 立刻写最小 `/app/output/result.json`（case_id + 全部契约字段 + `status:"partial"`）。产出：contract_notes.md、最小 result.json。

**步骤 1｜材料清点**：运行 inventory.py。产出：`/app/work/materials_register.md`（S1..Sn 编号、类型、大小、文本层初判）。输入目录全程只读。

**步骤 2｜PDF 结构清点与异常分级**：对每个 PDF 运行 pdf_survey.py。产出：`/app/work/survey/survey.json`（页数/图片/字体/加密/文字层/异常分级、`ocr_pages` 逐页覆盖清单、`table_regions` 表格区域几何）、`section_tree.md`（启发式章节树）、`ocr_coverage.md`（OCR 页覆盖声明）、`table_registry.md`（候选表格区域几何登记）。据此定路线：有文字层→步骤 3；无文字层/部分页极稀→OCR 路线（ocr-tool），全部 OCR 文本 conf:low 起标；加密→诚实 partial 并登记 blocker。**哪些页走了 OCR 必须按 ocr_coverage.md 的清单在主产物中显式列出，禁止跳过 OCR 页却声称覆盖。**

**步骤 3｜逐页文字提取与栏序还原**：以 `pdftotext -layout` 为主、`-raw` 为对照（复用步骤 2 落盘的文本，不重复提取），逐页处理：剔除跨页重复的页眉/页脚/页码行；判定栏数并**先整栏读完左栏再接右栏**，通栏内容（标题、大图注）单独成块；合并行末连字符断词（experi- mental → experimental）；跨页段落标续接。产出：`/app/work/pages/page-###.md`，每块标 `[p.N][col.L/R|full]`（v2：同时标提取视图 layout/raw/OCR，见 method_rules §8 可溯源转写规则）。规则与反模式见 references/method_rules.md §1。**视觉复核**：OCR 页与 table_registry.md 登记的表格区域所在页，须用 pdf-render-tool 渲染页面做人工/视觉检查，复核页码清单留痕进 evidence_map（method_rules §9）。

**步骤 4｜元素级解析**：产出 `/app/work/elements/`：metadata.md（标题/作者/单位/摘要/关键词，逐字摘录）、section_tree.md（校正版章节树，含各节起始页码）、figures_tables.md（每个图表：编号、题注原文、所在页、正文首次引用处回链）、equations.md（编号公式原文对照，符号保真）、references.md（按编号切分的文献条目）。图表与公式按结构元素识别，不解释其科学含义。

**步骤 5｜置信度与溯源**：每个产出区块标注 `[conf:high|medium|low]` + 判定依据（如"文字层直提"/"OCR"/"跨页拼接"）；无法辨认处标 `[NOT_READABLE: 原因]`。汇总 `/app/work/evidence_map.md`（区块→[S#]+页码 映射、修改记录、待确认项）。

**步骤 6｜组装交付**：按 templates/parsed_document_skeleton.md 组装 `/app/output/parsed_document.md`（§1 概览必须含 OCR 页覆盖声明与提取视图说明）；复制 evidence_map.md、survey.json；**写 result.json 前后跑 contract_check.py 核对契约字段（建议性核对：缺字段能补则补一轮，补不齐记入 uncertainty，不阻止落盘）**，再补全 result.json（status、sources、uncertainty、change_log，有跳过事项时含 skipped_reason）。

**步骤 7｜自查与交付**：运行 selfcheck.py 做建议性自查；FAIL 项能修则修一轮并复查一次（本脚本最多两轮），两轮后仍有 FAIL 的逐项写进 result.json 的 uncertainty 与 skipped_reason，然后照常落盘交付——不追求全 PASS，任何脚本退出码都不阻止交付。任何时刻中断/预算耗尽：立即运行 finalize.py 固化已完成的诚实部分（skipped_reason 逐条），不整案失败。

## 5. 自查清单（不阻塞交付）

交付前对照 references/element_checklist.md 逐条勾选（这是质量自查清单而非门禁：勾选不完的项记入 result.json 的 uncertainty，不阻止交付），建议达标项：

- 正文抽查 ≥5 处与原文逐字一致（含大小写、上下标、希腊字母）；
- 双栏案例抽查栏序：左栏末句与右栏首句不得被拼成一段；
- 必备元素齐全：标题/作者/单位/摘要/关键词、章节层级、图表题注、公式编号、参考文献、脚注、页眉页脚处置说明；
- 每个区块都能指回 [S#]+页码+区块号；无"无来源"段落；
- 所有 low 置信度区块都写了原因；没有静默猜测；
- （v2）主产物 §1 含 OCR 页覆盖声明（哪些页走了 OCR 逐页列出，与 ocr_coverage.md 一致）；
- （v2）表格块能指回 table_registry.md 的 region_id；OCR 页与表格区有视觉复核留痕。

## 6. 反馈回路

validate → fix → deliver：每完成步骤 3/4/6 各跑一次 selfcheck.py；每个脚本最多两轮（检查 → 修一轮 → 复查），FAIL 项按输出明细逐条修复（补章节、补登记、补契约字段），修复记录写入 change_log；两轮后仍有 FAIL 的，逐项记入 result.json 的 uncertainty 与 skipped_reason、status 记 partial，**立即交付**，不再进入下一轮修复循环。

## 7. 异常处理

- 材料缺失/case.json 缺字段：result.json 记 partial，uncertainty 列出缺失项，不臆造字段。
- 加密 PDF（survey 报 blocker）：尝试 pdftotext 确认失败 → partial，说明需解密或 OCR 截图；不得跳过不报告。
- 无文字层扫描件：转 OCR；OCR 文本 conf:low 起标，错字不擅自改，存疑处 `[NOT_READABLE]`。
- 乱码字体（CID 缺映射）：如实保留乱码并标 `[NOT_READABLE: 字体映射缺失]`，不得"猜字"。
- 缺页/页码错乱：以 PDF 物理页序为准编号，在 evidence_map 登记逻辑页码差异。
- 临近预算耗尽：立即运行 finalize.py 固化 partial 交付（已落盘内容保留、skipped_reason 逐条、契约字段齐全），change_log 记录已完成的步骤，剩余工作列入待确认项。

## 8. 资源索引

- `references/element_checklist.md`：要素齐全性清单 + 评分锚点（自查清单依据，不阻塞交付）。
- `references/method_rules.md`：栏序/章节树/表格/公式/扫描件/置信度的判定标准与反模式。
- `references/style_guide.md`：解析输出的区块标记语法与文体规范。
- `references/failure_modes.md`：基础 Agent 在本题的 9 类典型失败及对策。
- `templates/parsed_document_skeleton.md`：主产物章节级骨架（含占位说明）。
- `templates/result_json_template.md`：output_contract 透传规则与示意 JSON。
- `templates/evidence_map_template.md`：材料登记 + 区块溯源映射模板。
- `examples/minimal_example.md`：最小调用示例（示意，非正式案例结果）。
- `examples/synthetic_case.md`：全合成小案例的完整流程演示。
- `examples/negative_case.md`：负路径自测演示（必须被拒绝的草稿实际输出，全合成）。
- `scripts/inventory.py`：材料清点；`scripts/pdf_survey.py`：PDF 结构清点、章节树抽取、OCR 页覆盖清单与表格区域几何登记、分块处理；`scripts/contract_check.py`：契约字段核对（建议性，不阻塞交付）；`scripts/finalize.py`：交付固化兜底（诚实部分 + skipped_reason）；`scripts/selfcheck.py`：交付自查（FAIL/WARN 两级）；`scripts/selftest.py`：负路径自测。

## 9. 验证与限制声明

- 本技能全部脚本与流程**仅在本地用全合成 fixture 验证**（`scripts/selftest.py` 18 项用例，含"必须被拒绝"的负路径用例）；评测平台的 3 个隐藏案例与基础 Agent 对照**未在本地运行**，本包不声称任何平台分数。
- 示例（examples/）全部为合成/示意，不冒充正式案例结果。
- 字节级 PDF 清点、章节树、表格区域均为启发式，结论以人工/视觉抽查为准；OCR 路线的文字可信度依赖 OCR 工具与逐页视觉复核。
