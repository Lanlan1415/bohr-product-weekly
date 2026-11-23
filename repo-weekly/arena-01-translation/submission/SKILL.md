---
name: translating-scientific-literature
description: 把科研文献（PDF 或纯文本）翻译为可复核的段号对齐双语对照稿：术语表驱动翻译（抽取→锁定→全篇一致性强制）、长文语义分段续译（跨页跨栏上下文携带）、段号一一对应的双语输出、译文核验清单（数字/单位/公式/引用编号/否定与限定关系）、译不准处显式 [UNSURE] 标注。当评测任务是读取 /input/ 中的文献并完成全文或指定区间的翻译、术语统一或译文核验时使用。只要求解析版面结构而不翻译的任务不要触发（用解析类技能）；日常对话级短句翻译也不要触发。
---

# 科研文献翻译（术语锁定 + 段号对齐双语对照）

## 1. 用途与触发

把一篇（或指定段落区间的）真实科研文献翻译为**可核验**的双语对照交付：先抽取并锁定术语表，再按语义分段、携带上下文逐段续译，段号与原文一一对应，最后用机器脚本 + 人工清单核验数字、单位、公式、引用编号与否定/限定关系；译不准处显式标注 `[UNSURE]`，绝不含混润色过去。

触发语境：评测输入 `/input/` 含论文 PDF/文本，任务要求"翻译/双语对照/术语统一/译文核验"；也包括**对给定译稿做修订**（supplied-draft correction：句意复核 + 限于修订边界的有针对性的改前/改后变更，见主流程"修订模式"）。

不应触发：
- 任务只要求 PDF **版面解析/结构提取**而不翻译 → 用 parsing-scientific-papers 技能；
- 非文献的日常短句翻译（无术语表与段号对齐需求）。

## 2. 运行环境契约

- 先读 `/input/case.json`，提取 `case_id` 与 `output_contract`；`/app/output/result.json` 必须含 `case_id` 和 output_contract 声明的**全部原始字段**（字段名以 case.json 为准）。
- 工作文件在 `/app/work/`，最终交付在 `/app/output/`：主产物 `bilingual_translation.md`、`glossary`（术语表）、`evidence_map.md`、`result.json`（诚实 status、sources、uncertainty、change_log）。
- 预算：64 次模型请求 / 900 秒 / 单次响应 16384 token。**步骤 0 之后立刻落盘一份诚实的 partial result.json，再逐段迭代改进。**
- 性能预算意识（v2）：原文提取（pdftotext/OCR）只跑一次、落盘复用，禁止对同一 PDF 重复全量提取；长文按 5–10 段一批推进、每批落盘；预算剩余 <120 秒时停止开新批次，直接 finalize。
- 交付韧性（v2）：任何阶段失败/中断时，运行 `finalize.py` 固化交付——已译段落保持双语对照 + 未译/跳过事项逐条 skipped_reason，而非整案失败；写入/交付 result.json 前后跑 `contract_check.py` 核对契约字段齐全（建议性核对，任何退出码都不阻止交付）。
- 禁止：预制译文、编造原文没有的内容、把译不准的内容写得像确定译文。
- 脚本只用 Python 标准库；原文文字层提取调用环境中的 pdftotext，缺失时降级登记。

## 3. 脚本调用规则

- 一律按技能目录绝对路径调用，路径用正斜杠：
  `python3 /skills/weekly-skill/scripts/inventory.py --input /input --output /app/work/materials_register.md`
  `python3 /skills/weekly-skill/scripts/term_consistency.py --glossary /app/work/glossary.tsv --translation /app/work/translation_draft.md --source /app/work/source_paras.md --report /app/work/term_report.md`
  `python3 /skills/weekly-skill/scripts/align_check.py --source /app/work/source_paras.md --translation /app/work/translation_draft.md --report /app/work/align_report.md`
  `python3 /skills/weekly-skill/scripts/sentence_anchor.py --anchors /app/work/sentence_anchors.md --source /app/work/source_paras.md --report /app/work/anchor_report.md`（句级锚定 + 来源清点与对齐审计）
  `python3 /skills/weekly-skill/scripts/contract_check.py --case /input/case.json --result /app/output/result.json`（契约字段核对，建议性、不阻塞落盘）
  `python3 /skills/weekly-skill/scripts/finalize.py --work /app/work --output /app/output --case /input/case.json --skipped "步骤4: 原因"`（交付固化兜底）
  `python3 /skills/weekly-skill/scripts/selfcheck.py --output /app/output --case /input/case.json`
  `python3 /skills/weekly-skill/scripts/selftest.py`（负路径自测，全合成 fixture）
- 脚本缺失/不可执行时的降级：inventory → 手工登记文件清单；term_consistency → 用编辑器全文检索逐一核对每个锁定译名与禁用变体；align_check → 人工对照两侧段号序列；sentence_anchor → 人工逐句核对锚定记录的段号覆盖；contract_check → 对照 contract_notes.md 逐字段人工核对；finalize → 手工写诚实 partial result.json（含 skipped_reason）；selfcheck → 对照 references/element_checklist.md 逐条人工勾选。
- 脚本只读输入目录，输出只写参数指定路径；不得依赖当前工作目录（CWD）。

## 4. 主流程

**交付优先原则（v3，最高优先级，先于下列一切步骤）**：
- (a) 任何时刻 `/app/output/` 里都要有一份**当前最好的可交付物**：先完成再完美，每完成一个阶段就用当前版本更新交付物，绝不把"全部做好"当作落盘前提。
- (b) 请求预算分配建议：≤10 次读材料与契约，≤30 次产出主产物（分段续译与双语对照稿），≤10 次校验与修复，其余请求与时间余量全部留给 finalize 与交付固化。
- (c) 预算过半仍无落盘初稿 → 立即停止打磨，把当前版本落盘；剩余约 10 次请求 → 停止一切修复与校验循环，直接 finalize 交付。
- (d) 每个校验脚本最多运行 2 次（首次检查 + 修复后复查一次）；两轮之后无论结果如何都进入交付：剩余 FAIL 逐项写入 result.json 的 uncertainty 与 skipped_reason，照常落盘。校验是建议性的自查，任何脚本退出码都不阻止交付。

**步骤 0｜契约解析（最先做）**：读 `/input/case.json` → `/app/work/contract_notes.md` 逐字段抄录 output_contract、翻译区间与目标语言要求 → 立刻写最小 `/app/output/result.json`（case_id + 全部契约字段 + `status:"partial"`）。

**步骤 1｜材料清点**：运行 inventory.py，确认原文是 PDF（有无文字层）还是纯文本、有无随附术语表。产出：`/app/work/materials_register.md`。

**步骤 2｜原文获取与语义分段编号**：PDF 用 `pdftotext -layout` 取文字层（只跑一次、落盘复用；无文字层→先 OCR，OCR 错字不擅自改并记入 uncertainty）；**多栏版面警告**：inventory 或提取文本提示疑似多栏时，必须先验证栏序（左栏读完→右栏）再分段，禁止照抄文本流物理顺序。按**语义边界**分段：段落、图表题注、表头行、公式行、文献条目各自成段；跨页/跨栏被切断的句子先续接再分段；每段赋段号 `[P001]`、`[P002]`……连续不跳号。产出：`/app/work/source_paras.md`（兼作来源清点 source inventory 的底账）。规则见 references/method_rules.md §2、§10。

**步骤 3｜术语表构建与锁定**：通读 source_paras.md，抽取领域术语、缩写、符号、材料/方法名；为每条定唯一首选译名，并列出常见但禁用的变体；写 `/app/work/glossary.tsv`（格式见 scripts/term_consistency.py 文档字符串）。**先锁术语再翻译**；翻译中途确需改译名时，改表并全篇回填，重跑一致性脚本。规则见 references/method_rules.md §1。

**步骤 4｜分段续译（携带上下文）+ 句级锚定（v2）**：逐段翻译，每次携带：① 术语表全表；② 前一段的末句原文与译文；③ 本段段号。段号原样带入译文稿。**句级锚定**：先定位原句再译，边译边写 `/app/work/sentence_anchors.md`，每行一句 `[P###-S##] [p.N] 原句 || 译文`——译文逐句回链原句（格式见 scripts/sentence_anchor.py 文档字符串与 references/method_rules.md §7）。产出：`/app/work/translation_draft.md`（`[P###] 原文…` / `译文：…` 成对）+ `sentence_anchors.md`。长文按 5–10 段一批推进，每批落盘一次。规则见 references/method_rules.md §3。

**步骤 5｜机器核验 + 人工清单**：先跑 term_consistency.py、align_check.py 与 sentence_anchor.py（来源清点 + 对齐审计：零锚句段=漏段，FAIL），FAIL 项能修则修一轮并复查一次（每个脚本最多两轮），修不完的逐项记入 result.json 的 uncertainty 与 skipped_reason，不反复重跑；再按 references/method_rules.md §5 的人工核验清单逐项核对：数字、单位、公式编号、图表编号、文献引用编号、否定词、限定条件、指代关系。产出：`/app/work/verify_report.md`（三份脚本输出 + 人工清单勾选结果）。

**步骤 6｜组装交付**：按 templates/bilingual_skeleton.md 组装 `/app/output/bilingual_translation.md`（头部元数据 + 术语表 + 双语对照正文 + 核验清单 + 未决项）；术语表复制为 `/app/output/glossary.tsv`；写 evidence_map.md（段号→页码映射、术语决策记录、句级锚定审计留痕）；**写 result.json 前后跑 contract_check.py 核对契约字段（建议性核对：缺字段能补则补一轮，补不齐记入 uncertainty，不阻止落盘）**，再补全 result.json（有跳过事项时含 skipped_reason）。最终按任务契约交付。

**步骤 7｜自查与交付**：运行 selfcheck.py 做建议性自查；FAIL 项能修则修一轮并复查一次（本脚本最多两轮），两轮后仍有 FAIL 的逐项写进 result.json 的 uncertainty 与 skipped_reason，然后照常落盘交付——不追求全 PASS，任何脚本退出码都不阻止交付。任何时刻中断/预算耗尽：立即运行 finalize.py 固化已译段落的诚实部分（skipped_reason 逐条），不整案失败。

**修订模式（supplied-draft correction，v2）**：当 case 提供既有译稿要求修订时，跳过步骤 3-4 的全量翻译，改为：① 对给定译稿逐句做句意复核（对照 source_paras.md 与句级锚定）；② 变更**限于任务声明的修订边界**（如只修术语一致性/只修指定段落），边界外一字不动；③ 每处变更登记"改前 → 改后 + 依据"进变更表（evidence_map §7）；④ 复核后重跑 term_consistency.py / align_check.py / sentence_anchor.py。规则见 references/method_rules.md §9。

## 5. 自查清单（不阻塞交付）

交付前对照 references/element_checklist.md 逐条勾选（这是质量自查清单而非门禁：勾选不完的项记入 result.json 的 uncertainty，不阻止交付），建议达标项：

- term_consistency.py 与 align_check.py 均已运行且输出留存（FAIL 项已修一轮并复查，或逐项记入 uncertainty）；
- （v2）sentence_anchor.py 已运行且报告留存：逐句回链齐全、无零锚句段（漏段却报 complete 的句级拦截）；仍有 FAIL 的记入 uncertainty/skipped_reason，不阻塞交付；
- 段号连续、两侧一一对应、顺序一致；无漏段、无重段；
- 每个锁定术语在标题/摘要/正文/图注/结论中译名唯一；
- 抽查 ≥5 处数字+单位、≥2 处公式编号、≥3 处引用编号与原文完全一致；
- 否定与限定（no/not/only/except/unless/at most）逐处核对，无翻转；
- 所有 `[UNSURE]` 处都在未决项中列出原文与候选译法。

## 6. 反馈回路

validate → fix → deliver：步骤 4 每批译文落盘后跑 align_check.py；步骤 5 脚本 FAIL → 回填修复一轮 → 复查一次；步骤 7 selfcheck FAIL → 补章节/补登记/补契约字段 → 复查一次。每个脚本最多两轮（检查 → 修一轮 → 复查），修复记录写入 change_log。两轮后仍有 FAIL 的，逐项记入 uncertainty 与 skipped_reason、status 降级 partial，**立即交付**，不再进入下一轮修复循环。

## 7. 异常处理

- 材料缺失/case.json 缺字段：partial + uncertainty 列缺失项，不臆造。
- 文字层缺失/扫描件模糊：先 OCR 再译；OCR 可疑字符处标 `[UNSURE: OCR 原文存疑，原字形为…]`。
- 公式/表格为图片：公式编号保留、公式体不译并标 `[NOT_TRANSLATED: 图片型公式]`；表格题注与表头照译，图片型数据格不编造。
- 参考文献无法解析：保留原文条目不译（文献条目按惯例不翻译），只核对编号对应。
- 原文残缺或语言混杂：残缺处标 `[NOT_TRANSLATED: 原文缺失]`；混杂语言段落在 evidence_map 登记后按主语言译。
- 临近预算耗尽：立即运行 finalize.py 固化交付——已完成段落保持双语对照，未译段落保留 `[P###] 原文 + [NOT_TRANSLATED: 预算耗尽]`，skipped_reason 逐条，status 记 partial。

## 8. 资源索引

- `references/element_checklist.md`：翻译要素齐全性清单 + 评分锚点（自查清单依据，不阻塞交付）。
- `references/method_rules.md`：术语锁定、语义分段、续译上下文、核验清单的判定标准与反模式。
- `references/style_guide.md`：科研中译文体规范（句式、数字单位、标注语法）。
- `references/failure_modes.md`：基础 Agent 在本题的 9 类典型失败及对策。
- `templates/bilingual_skeleton.md`：双语对照主产物骨架（含占位说明）。
- `templates/result_json_template.md`：output_contract 透传规则与示意 JSON。
- `templates/evidence_map_template.md`：材料登记 + 段号/术语溯源映射模板。
- `examples/minimal_example.md`：最小调用示例（示意，非正式案例结果）。
- `examples/synthetic_case.md`：全合成小案例的完整流程演示。
- `examples/negative_case.md`：负路径自测演示（必须被拒绝的译稿实际输出，全合成）。
- `scripts/inventory.py`：材料清点（含多栏版面警告）；`scripts/term_consistency.py`：术语一致性强制检查；`scripts/align_check.py`：段号对齐核对；`scripts/sentence_anchor.py`：句级锚定审计（来源清点 + 对齐审计）；`scripts/contract_check.py`：契约字段核对（建议性，不阻塞交付）；`scripts/finalize.py`：交付固化兜底；`scripts/selfcheck.py`：交付自查（FAIL/WARN 两级）；`scripts/selftest.py`：负路径自测。

## 9. 验证与限制声明

- 本技能全部脚本与流程**仅在本地用全合成 fixture 验证**（`scripts/selftest.py` 20 项用例，含"必须被拒绝"的负路径用例）；评测平台的 3 个隐藏案例与基础 Agent 对照**未在本地运行**，本包不声称任何平台分数。
- 示例（examples/）全部为合成/示意，不冒充正式案例结果。
- 句级锚定到句号粒度依赖人工/模型分段质量；机器审计保证"每段至少有锚、锚号不错位"，语义对错仍以人工核验清单为准。
