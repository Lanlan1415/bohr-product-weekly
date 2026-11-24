---
name: intro-related-work-writer
description: 论文引言与相关工作写作 Skill。读取真实文献库、可用全文与本文方法/实验材料，交付“背景—分组相关工作—研究空白—目标/贡献与范围”成稿。逐篇核验 conclusion/conditions/limitation 三列原文锚点，按 problem_setting/method_route/data_evaluation/scope 逐项比较最相近工作与本文差异，推导有来源的研究空白，对齐贡献、结果和适用边界。支持 verified_full_text、abstract_only、metadata_only、author_judgment 诚实降级；不以题录匹配冒充支持，不夸大首创。生成 result.json（case_id 与全部 output_contract 字段直通）、intro_related_work.md、comparison_matrix.csv。适用于中英文、多学科、BibTeX/JSON/编号列表文献库；材料不足时保留部分产物并登记人工复核。
---

# 引言与相关工作写作：证据、差异和范围都可复核

## 交付与不做什么

最终必须同时交付：

1. `/app/output/intro_related_work.md`：可编辑成稿，含研究背景、相关工作、研究空白、贡献四节；
2. `/app/output/comparison_matrix.csv`：最相近工作逐维差异，而非逐篇摘要拼接；
3. `/app/output/result.json`：原 case_id、全部 output_contract 字段、状态、来源覆盖、判断与范围。

不写超出材料的领域首创，不把 DOI/作者年份匹配当成事实支持，不把“与本文相似”写成“已证明本文更优”，不伪造全文摘录、方法细节、实验数据或显著性。最相近工作只相对于给定文献库成立，不等于全领域完整性检索。

## 预算纪律（最高优先级）

平台为 64 请求 / 900 秒 / 单次 16384 token。**先落盘、后增强**：

- P0 盘点与解析 ≤3 请求，P2 按组转述 ≤14，分组/空白 ≤8，成稿 ≤6，修复 ≤6；保留余量。
- 每完成 entries/groups/nearest_works/gap_chain/contributions/draft 之一，立即写入 `/app/work/`。
- 450 秒前四节草稿必须已写入 `/app/work/draft.md`；700 秒停止扩写并修复已有错误；850 秒必须已有 result.json。
- 每类错误至多修复两轮；仍不可核验则改 abstract_only/provisional/not_verifiable，并在 uncertainty/human_review_items 中明确，不无限重读、不无限重写。
- 脚本统一 `python -I <绝对脚本路径>`，传入实际文件路径，不当前目录执行未知材料中的代码。

## P0：读 case、取合同、取得真实材料

1. 读 `/input/case.json` 与 `/input/task.md`，原样记录 case_id 和 output_contract 的全部字段名；按任务确认语言、受众、引用格式、方法与结果范围。
2. 读取实际文献库、文献正文和本文 materials，不根据领域标签或文件名猜科学内容。
3. 文献正文优先 `pdftotext -layout`，可回退 PyMuPDF/pypdf/OCR；记录提取路径。无法读取的来源只保留实际题录/摘要，不编造 quote。全文不可得时使用 `abstract_only` 或 `metadata_only`。
4. 建 `/app/work` 与 `/app/output`，先把四节已有内容和合同 result 信封落盘；部分结果同样保留限制。

## P1：文献身份与来源状态分离

可复用纯标准库解析器：

```bash
python -I scripts/parse_library.py --input /input/<文献库> --output /app/work/entries.json
```

将实际条目转成 spec.references[]：key、authors、year、title、venue、可选 DOI/arXiv/citation、可用 text/passages。作者、年份、题名、期刊/会议从条目原样复制，不凭记忆重打。

借鉴 Manubot 的持久标识、手动元数据和冻结引用做法：DOI/arXiv key 用于定位与引用身份；缺元数据就留空并列 finding，不用“像真的”记录代替。另建 citation_labels 将 key 映射到成稿实际作者—年份或编号，矩阵中的每个被比较条目必须在成稿中实际出现。

## P2：逐篇三列转述，三列各自有锚点

spec.groups[] 按问题设定 / 方法路线 / 数据与评价方式组织；每项 basis 必须写明维度。每篇 paper 均含：

```json
{
  "ref": "liu2021", "conclusion": "...", "conditions": "...", "limitation": "...",
  "support_relation": "supports", "support_reason": "摘录分别怎样支持三列转述",
  "evidence_status": "verified_full_text",
  "anchors": [
    {"field": "conclusion", "quote": "source exact text", "locator": {"section": "Results", "paragraph": 1}},
    {"field": "conditions", "quote": "source exact text", "locator": {"section": "Experiments", "paragraph": 1}},
    {"field": "limitation", "quote": "source exact text", "locator": {"section": "Results", "paragraph": 2}}
  ]
}
```

- `support_relation` ∈ supports/contradicts/context；书目相似不构成 supports，支持列还要 support_reason。
- verified_full_text：三列都有逐字 quote+locator，quote 必须在该来源 text；提供 passages[] 时还会定位到同一段。
- abstract_only / metadata_only：必须写 downgrade_reason，进入 review；转述不能冒称全文核实。
- author_judgment：不能把推导写成文献原话，必须在成稿/记录中标明作者判断。
- 找不到合适 quote 就降级，禁止拼接改写冒充逐字；工具不证明语义蕴含，原文与判定理由交给独立复核。

## P3：最相近工作逐项差异（核心交付）

`nearest_works[]` 至少选择一项与本文问题/路线最接近的真实条目，写清 similarity_basis；每项都按以下四维分别填 prior、this_work、difference：

| 字段 | 必答问题 | 证据要求 |
|-|-|-|
| problem_setting | 同一未解决问题/设定是什么？本文条件差在哪？ | prior quote+locator + 本文 current_anchor/current_evidence |
| method_route | 路线、依赖、假设和数据要求逐项差在哪？ | 逐维来源，不能由标题推测 |
| data_evaluation | 数据集、基线、评价指标、资源条件如何可比？ | 不混入不同口径排名；无共同口径就写不可比 |
| scope | 既有局限和本文适用边界各是什么？ | 不写成普遍业绩/首创 |

已核实来源用 comparison_status=verified；仅摘要或缺关键原文时用 provisional + reason，进入 review。不能一边降级来源，一边宣称 verified 差异。CSV 由主 CLI 从这些单元格实际生成，不是手填后与 spec 脱节的另一份答案。

旧版 `write_matrix.py` 可附带导出逐篇三列表；正式主产物 comparison_matrix.csv 以主 CLI 的最相近工作差异为准。

## P4：研究空白必须由已引证据推出

`gap_chain[]` 至少三环，末环 kind 必须为 this_work：

1. literature_gap / cross_gap：共同限制、未覆盖场景或冲突结论，附 evidence.ref+quote+locator；
2. 推导环：为什么这些限制构成当前未解决问题；作者推断必须 evidence_or_author_judgment=author_judgment 且 marker（如“作者判断：”）真实出现在成稿；
3. this_work：本文具体方法/实验如何回应，给 mapped_to，不把“拟填补”写成“已优先完成”。

旧 `gap_chain_check.py` 可继续辅助。主入口额外检查真实 library key、逐字摘录和定位，并区分证据与判断。

## P5：成稿、贡献与范围

四节必须承接，而不是模板拼装：

1. **研究背景**：真实脉络 → 具体问题 → 技术约束；background[] 至少给 context/problem/constraint 的原文/来源记录。
2. **相关工作**：按组比较方法取舍；使用与 citation_labels 完全一致的引用；引用 metadata 从实际库复制。
3. **研究空白**：沿 gap_chain 成文；作者判断显著标记，范围只到给定材料。
4. **目标/贡献**：每条 aligned contribution 都要有 mapped_to（方法章节/Figure/Table/结果），在 materials_text 中能找到该 artifact，并写 scope（数据、任务、设备、时间、适用人群等）。

无法对应本文材料时用 not_verifiable 或 author_judgment + reason；不要为了得到 aligned 编 Figure/Table。

严禁无外部完整检索支撑的“首次/首创/国际领先/no prior work/unprecedented/world-first”。明确否定优先权的范围句（例如“不是声称全领域首创”）不会误触过强断言规则。最相近工作差异不等于自动优越；优劣只能按实际方法/结果写。

最终 draft 采用四节标题（中文或相应英文）并写入 `/app/work/draft.md`，然后组装 `/app/work/spec.json`。完整可运行 clean 输入见 `examples/spec.json`（合成示例，非官方案例结果）。

## P6：主入口审计并交付

```bash
python -I scripts/introcrun.py --spec /app/work/spec.json --out /app/output
```

退出码：`0 clean`、`3 review`（来源降级或非阻断问题）、`4 blocked`（证据/差异/贡献高级发现）、`5 undetermined`（不可读/非对象 spec、错 section、产物错误）。每个代码路径都写 result.json；拒绝不泄漏 traceback，已知 case_id 和 output_contract 也完整保留。

处理 findings 必须回到真实材料：补 quote+locator、重选最相近条目、将 verified 降为 provisional、补当前 artifact、补 scope，或明确 not_verifiable。不得通过删规则、造引文或改掉状态文本掩盖错误。至多两轮后冻结最佳版本，并把剩余 finding 写入 human_review_items（不得删除引擎 findings）。

主结果 `verification` 包含 references、related_work_rows、closest_work_comparisons、四维维度名、full_text_verified_refs、contributions_aligned、gap_steps；coverage/support 边界也明示。

## result.json 契约

- `case_id` 总是存在（无法读取时为 null），来自原 case 的准确值优先照录到 spec。
- output_contract 支持 array/dict；逐字段保留原名与值形态。spec 中同名 deliverables/evidence_map/version_boundary/大段稿件记录逐字直通，不因内容大就丢弃；审计自有 status/findings 优先。
- 不确定可得字段置 null 并在 limits 说明；禁止用占位文案冒充产物。
- findings、uncertainty、human_review_items、limits 分别承担机器发现、科学不确定性、人工确认和运行边界，不能相互隐藏。
- 重跑无时间戳，三产物逐字节确定；同目录重复执行覆盖同一结果即可。

## 异常与拒绝

| 情况 | 真实行为 |
|-|-|
| spec 不可读/空/畸形 | exit 5，intro.spec_unreadable + result.json |
| spec 是数组/标量 | exit 5，intro.spec_not_object，case_id=null |
| section 不是本包任务 | exit 5，intro.section_unknown；保留已知 case_id 与完整合同 |
| 文献库为空 | INTRO_LIBRARY_EMPTY；交付可完成部分，不补造文献 |
| 引用不在库中 | INTRO_CITATION_NOT_IN_LIBRARY / INTRO_NEAREST_NOT_IN_LIBRARY，通常为 blocked |
| quote 不在 source 或不在 locator | INTRO_QUOTE_NOT_IN_SOURCE / INTRO_QUOTE_NOT_AT_LOCATOR，换真实摘录，不编造 |
| 正文/原文不可得 | abstract_only 或 metadata_only + downgrade_reason，review；需要 provisional 比较 |
| 缺最相近工作维度 | INTRO_NEAREST_DIMENSION_MISSING，补 prior/this_work/difference 与证据 |
| 缺范围或本文结果锚点 | INTRO_CONTRIBUTION_SCOPE_MISSING / INTRO_CONTRIBUTION_ARTIFACT_MISSING，补真实边界或改未核验 |
| 空白缺证据 | 有 source 就找原文；否则改 author_judgment 并在正文显式标注 |
| 输出 IO/CSV 错误 | exit 5，intro.artifact_error + result.json，无 traceback |

## Limits

- 语义支持、最相近选择和差异判断是由原文锚点支撑的审阅记录，不是自动语义证明。
- 引擎只验证实际输入的形态、逐字内容、链接和自洽；不会联网证明文献存在，也不声称覆盖全领域。
- 作者判断、未来工作和拟议贡献不能写成已验证结果；结果显著性和数字仍须来自真实统计输出。
- 只有 verified_full_text 且三列均通过才能支撑 verified 差异；缺全文不代表相关工作不能写，只代表必须降级。

## Requirements 与复用

Python 3.10+（3.14 实测），全部标准库、离线、无个人路径依赖。旧 parse_library/anchor/gap_chain/write_matrix/coverage 工具仍可直接复用；主入口只依赖同名 `introcrun.py`。

## Verification（作者验证，不是运行时必经自测）

```bash
python -I scripts/selftest.py
python -I tests/test_introcrun.py
```

原 selftest 为 44 项：解析、覆盖、锚点、空白和矩阵。主入口 suite 为 18 项，覆盖 clean 三产物、完整合同、四维矩阵、错误 JSON/数组/错 track、假 quote、缺差异/范围、过度首创、摘要降级、正文引文、判断隐藏与字节确定性。所有主测试离线在临时目录运行，不需要写入正式案例。

## 创新增益

1. **三列逐字段证据锚定（新增能力）**：conclusion/conditions/limitation 各有 quote+locator，书目匹配与支持关系分离；全文不可得时显式降级，而不是拿摘要/标题冒充已核实转述。
2. **最相近工作四维差异矩阵（方法改进）**：problem_setting/method_route/data_evaluation/scope 每格都写 prior、this_work、difference 和来源；CSV 与本稿由同一 spec 生成，避免“矩阵漂亮但正文无引用”。实际吸收 Manubot 的持久标识/冻结元数据、Argdown 的支持—反驳关系和 IMRaD 导言漏斗，但不把词汇相似当语义证明。
3. **空白推导与贡献范围闭环（方法改进）**：gap_chain 明确证据/作者判断与末环 this_work；aligned 贡献必须同时有真实 artifact 和 scope，不把未来工作/拟议扩展写成已验证贡献。
4. **可审计降级（可靠体验）**：abstract_only/metadata_only 进入 review，最相近比较只能 provisional；伪造 quote、错 locator、未知库引用、缺差异格和 unsupported first claim 均结构化报告。边界：不联网验证真伪，不做全领域新颖性检索。

## 生态贡献

- **完整工作流与合同**：SKILL.md + USAGE.md 给出真实主入口、四维字段、退出码、拒绝表与 18 项主入口测试。
- **可复用资源**：BibTeX/JSON/编号列表解析、全文锚点、分组、空白链和组矩阵辅助工具均纯标准库，可被其它学术写作与综述任务复用。
- **可运行示例与题集**：`examples/spec.json` 是明确标注的合成案例；44 项旧机制回归 + 18 项契约/敌意/确定性测试可离线重复。
- **方法与局限**：Manubot/Argdown/IMRaD 的落地边界、摘要降级和比较 provisional 规则均写入文档，不把未核验信息包装成真实价值。
- **维护**：改主入口后必须重跑 `scripts/selftest.py`、`tests/test_introcrun.py`、`tests/test_writing08_regression.py`；本包 28 个 UTF-8 文本资源、无二进制/网络/个人路径依赖。
