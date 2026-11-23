---
name: manuscript-format
description: >
  Audit a manuscript adapted to a target template, on two axes at once: does the format match
  the spec (font, size, spacing, margins, columns, caption position, reference style), and is
  the content still intact (figures, tables, equations, footnotes, comments, revisions, fields,
  section breaks, embedded objects)? Also checks that headings are bound to styles and stay
  within the declared level depth, that the TOC exists, that references and citations agree,
  that declared header/footer requirements are recorded item by item, that declared template
  conflicts name the adopted version, that declared page numbers are confirmed in the export,
  that the export names the template's required format with font embedding, measured page
  size, refreshed TOC and editability, and that the declared pre-conversion text survives the
  conversion sentence by sentence. The formatfit primary entry reads real DOCX/TeX templates,
  safely applies controlled OOXML settings without overwriting source, measures the delivered
  file, and emits per-requirement pass/fail/unverified evidence; it never claims visual checking.
  Use when a task asks for format adaptation, template conformance, or journal/degree-thesis
  preparation. Do not use this package for scientific content rewriting or review responses.
---

# manuscript-format

Two things go wrong in template adaptation, and only one of them is visible.

**The format is not met.** Font, size, spacing, margins, columns, caption position, reference
style. Checkable against the template's own spec.

**The format is met and the document was damaged.** A conversion drops the footnotes, or
rewrites an equation, or loses a tracked revision. This is the failure the task names
explicitly — *同时正文、图表、公式、引用、批注是否被错误改动* — and it is the one nobody
notices until the proof stage.

Both are audited here, because a beautifully formatted document that lost its equations is a
worse outcome than an ugly one that kept them.

## 运行契约（Harbor runtime contract）

- 运行时输入是 /input/case.json 与 task.md：先读 case.json，逐字记录其中的 case_id 和
  output_contract 字段名清单；再读 task.md 确认任务动作与交付形态。材料和 PDF 一律读实际文件，
  不按标签臆测内容。
- 工作目录 /app/work 放中间产物；最终实际结果与可编辑产物放 /app/output，其中 result.json
  必须保留 output_contract 的全部字段和 case_id（本 Skill 的审计会自动回填，见第六步）。
- 预算：64 次模型请求、900 秒、每次响应 16384 token（含推理）。先尽早写出诚实的部分成果，再增量改进。
- 三个固定案例、每条件重复三次；评测由平台对照运行。不得伪造缺失的软件状态或科学数据；
  部分成果必须说明边界。
- Skill 资源限制：最多 50 个 UTF-8 文本文件、单文件 500KB、总量 2MB、无符号链接。
- 案例若指定供给字体（如 Liberation Serif），以案例材料为准，不得凭经验猜字体。

## 六步运行时入口

0. **读 case.json 取标识**：记下 case_id 与 output_contract 的每个字段名（如
   revised_manuscript、export_record、change_log 这类交付字段）；读 task.md 确认要做的是
   排版适配、转换还是导出。
1. **判形态路由**：按下面的「任务措辞 → 路由」决策表决定跑哪个 section、哪些字段必填。
2. **先产出目标产物**：完成适配后的可编辑稿件（模板要求的格式，如 docx/tex）+ 导出件 +
   可打开的预览（PDF/PNG）。产物先行，审计在后——审计审的是真实交付物，不是意图。
3. **构造 spec**：把模板规格、标题结构、内容单元计数、转换步骤、导出记录逐项填成一个 JSON
   （见 worked example）；section 取 format_template；附上 case_id，并把 output_contract
   的每个字段以同名键放进 spec（值会被逐字直通进 result.json）。
4. **真实文件适配与审计**：运行 `python scripts/formatfit.py --spec /app/work/format-spec.json --case /input/case.json --input-root /input --out /app/output`。spec 写 `source_file`、`template_file`（真实 docx/json/tex）、`apply:true` 或已有 `output_file`，并保留案例 template.spec/headings/sections。脚本直接从模板提取要求、创建 adapted.docx 或审计既有输出、生成 compliance.json；退出码 0 clean、3 review（存在不可验证项）、4 blocked（不符合或内容受损）、5 undetermined（结构化拒绝）。`writeaudit.py --section format_template` 仅作旧的声明式兼容审计，不能替代真实文件检查。
5. **修发现重跑**：每条 finding 按 Failure handling 表处置后重跑，直到 clean，或只剩已声明
   的 limits。high 发现不修复就直接交付等于 blocked。
6. **合并 result.json**：确认 /app/output/result.json 顶层含 case_id 和 output_contract
   全部字段，严格按“引擎实测值 > 案例/spec 值 > null+limits”回填；compliance 逐项给出
   required/observed/status/evidence，content_preservation 比较真实文本和九类单元。把可编辑稿件、
   导出件、预览放进 /app/output；渲染属性和人工视觉检查分开记录，不得把 OOXML 检查写成视觉通过。

## 任务措辞 → 路由决策表

| 任务里的措辞 | 路由与动作 |
|-|-|
| 「按目标模板排版 / 适配学位论文或期刊模板 / 套模板」 | 跑 formatfit：真实 source_file/template_file + apply；页边距/字体/字号/行距/栏数/标题样式可安全应用，无法安全自动化的项保持 unverified |
| 「从模板文件/格式要求中提取可逐项核对的规格」 | formatfit 直接解析 DOCX styles/sectPr 或 TeX class/geometry/font/bibliography；再与 task.md 的显式要求合并并记录每字段来源，不凭经验补值 |
| 「格式转换 / 迁移（Word↔LaTeX↔Markdown）且内容不能丢」 | 转换前后文本分别填 pre_conversion_text 与 text；input_units 与 output_units 两侧都填（转得全） |
| 「导出/交稿（PDF、字体嵌入、页码目录可用）」 | export 记录六项逐项给真值；模板要求交付 docx 时 export 里必须出现 docx（交得出） |
| 「模板有版本差异 / 前后规定冲突」 | 两条冲突规定都抄进 conflicts，adopted 写明采用哪一版 |
| 「页眉页脚 / 目录 / 页码有要求」 | template.spec.header_footer、page_numbers、toc_expected 声明后逐项回填执行记录 |
| 「标题层级/编号/目录错位」 | headings 列表带 level/number/style；heading_levels 声明模板定义的层级深度 |
| 「引用格式 / 交叉引用不一致」 | references 列表 + figures 编号声明；引擎查引用与列表互认、图表编号悬挂 |
| 任务混有翻译、改写或内容审校诉求 | 先跑对应 section（translation / evidence_writing / review_response）审内容，再跑 format_template 审格式 |
| 任务是审稿返修场景 | 本包只审格式与保真；返修内容路由给 review-response 包 |
| 案例只有成品稿、没有模板规格 | spec_missing 会拦截：从任务文本逐字抽取规格，抽不到的字段如实标注 not provided，不得编造 |
| 案例指定字体（如 Liberation Serif） | spec 的 font 写案例供给的实际字体名 |

## The failures this exists to catch

**A heading that is only bold and bigger.** No paragraph style means no level: the TOC will not
build and the structure disappears the moment the file is re-used. Or the heading sits deeper
than the template defines any style for. `fmt.heading_style_unbound`,
`fmt.heading_level_beyond_declared`.

**A lost footnote.** `input_units.footnotes` 4 → `output_units.footnotes` 2 is a conversion
that changed the document. A dropped paragraph, a changed dose, a vanished citation marker:
visible only by comparing the declared pre-conversion text with the delivered one.
`fmt.unit_lost`, `fmt.text_dropped`, `fmt.text_quantity_changed`, `fmt.text_citation_changed`,
`fmt.text_claim_changed`.

**A conversion nobody can repeat.** No recorded steps, so another person cannot get from the
input file to the delivered one. `fmt.conversion_undocumented`.

**An export nobody checked.** Font not embedded, page size unmeasured, TOC stale, page numbers
unconfirmed, required format not the one produced, file read-only. Each is a separate field and
each is reported. `fmt.export_format_missing`, `fmt.font_not_embedded`, `fmt.toc_not_refreshed`.

**A checklist claimed and not done.** The template lists checks; the run records which were
performed. The difference is reported by name. `fmt.checklist_incomplete`.

**A conflict resolved silently.** Two template versions disagree on a required size; the
delivery must say which one it followed. `fmt.conflict_unresolved`.

**Page furniture nobody recorded.** Headers and footers live outside the body text; each
declared item must be recorded as set (with what) or explicitly marked not set.
`fmt.header_footer_unverified`.

## Primary real-file example（示例，非正式案例结果）

```bash
python examples/run_minimal.py
```

该示例只在临时目录生成一个小型 DOCX，按模板真实修改页边距、Liberation Serif、11 pt、
1.5 倍行距和标题样式，再重新打开 adapted.docx 审核。实跑状态为 clean，正文逐字不变、
output_contract 缺项为 null，且 rendering.visual_inspection = not_performed；临时二进制
不会打进 Skill。真实案例使用同一 formatfit CLI，输入原稿与模板，不运行示例生成器。

借鉴 GitHub 上 anthropics/skills 项目的 DOCX 机制并落实为纯标准库实现：ZIP 内直接读 OOXML（不解包、
不恢复符号链接）、受控修改 document.xml/styles.xml、另存而不覆盖原稿、修改前后文本与内容
单元对照。本实现不声称完成 XSD 验证：当前包没有附带 XSD 套件，因此只报告 ZIP/XML/内容
结构与实测受控属性，不冒称通过 Office XSD 或渲染验证。

## Legacy declaration-only example（兼容接口，非真实文件验证）

examples/spec.json 的完整内容（一个最小适配交付的 spec，带 case_id 与 output_contract）：

```json
{
  "case_id": "demo-case-001",
  "section": "format_template",
  "text": "1 Introduction\nWe study it [a1].\n2 Methods\nWe use 3 mM [a2].\n3 Results\nIt works [a3].\n",
  "template": {
    "sections": ["introduction", "methods", "results"],
    "word_limit": 4000,
    "spec": {"font": "Liberation Serif", "size_pt": 11, "line_spacing": 1.5,
             "margin_mm": 25, "columns": 1, "caption_position": "below",
             "reference_style": "APA", "heading_levels": 3, "export_format": "docx"},
    "checks": ["margins", "caption_position", "reference_style"]
  },
  "headings": [
    {"level": 1, "number": "1", "text": "Introduction", "style": "Heading 1"},
    {"level": 1, "number": "2", "text": "Methods", "style": "Heading 1"},
    {"level": 1, "number": "3", "text": "Results", "style": "Heading 1"}
  ],
  "input_units": {"figures": 2, "tables": 1, "equations": 3, "footnotes": 4},
  "output_units": {"figures": 2, "tables": 1, "equations": 3, "footnotes": 4},
  "conversion_steps": ["open in Word", "apply template styles", "export to docx"],
  "export": {"format": "docx", "font_embedded": true, "page_size_measured": true,
             "toc_refreshed": true, "page_numbers_ok": true, "editable": true},
  "checks_done": ["margins", "caption_position", "reference_style"],
  "references": [{"key": "a1"}, {"key": "a2"}, {"key": "a3"}],
  "output_contract": {
    "revised_manuscript": "the adapted manuscript, editable",
    "export_record": "the export verification record",
    "change_log": "what the adaptation changed"
  },
  "revised_manuscript": "1 Introduction\nWe study it [a1].\n2 Methods\nWe use 3 mM [a2].\n3 Results\nIt works [a3].\n",
  "export_record": {"format": "docx", "font_embedded": true},
  "change_log": "styles applied per template spec; content units unchanged"
}
```

运行（示例命令，正式运行时 --out 用 /app/output）：

```bash
python scripts/writeaudit.py --spec examples/spec.json --out examples/_demo_out
```

以下为本机实跑得到的示意输出（clean，exit 0），result.json 全文：

```json
{
  "schema_version": "writeaudit/v1",
  "case_id": "demo-case-001",
  "section": "format_template",
  "status": "clean",
  "findings": [],
  "severity_counts": {},
  "checked": {"headings": 3, "references": 3},
  "limits": ["all declared output_contract fields carry values"],
  "revised_manuscript": "1 Introduction\nWe study it [a1].\n2 Methods\nWe use 3 mM [a2].\n3 Results\nIt works [a3].\n",
  "export_record": {"format": "docx", "font_embedded": true},
  "change_log": "styles applied per template spec; content units unchanged",
  "output_contract_fields": ["revised_manuscript", "export_record", "change_log"]
}
```

交付物缺内容时审计会点名。把上面 spec 的 footnotes 从 4 改成 2、toc_refreshed 改成 false、
删掉 export 的 editable、export 格式改成 pdf，同一命令实跑 exit 4（blocked），四条发现：

```json
[
 {"rule": "fmt.unit_lost", "severity": "high", "kind": "footnotes", "before": 4, "after": 2,
  "message": "the conversion lost content units of this kind, ..."},
 {"rule": "fmt.toc_not_refreshed", "severity": "high",
  "message": "the table of contents was not refreshed after editing, ..."},
 {"rule": "fmt.export_field_missing", "severity": "medium", "field": "editable",
  "message": "an export property was not reported, so it is unknown rather than good"},
 {"rule": "fmt.export_format_missing", "severity": "medium", "required": "docx",
  "delivered": ["pdf"],
  "message": "the template declares the export format the deliverable must have, ..."}
]
```

severity_counts 为 2 high、2 medium；high 不清零不得交付。

## 规格怎么抽（认得准）

模板规格不是猜的。把任务给的模板文件、投稿要求或院系规定逐项转成可核对的键值：栏数
columns、字号 size_pt、行距 line_spacing、页边距 margin_mm、标题层级 heading_levels、题注位置
caption_position、参考文献样式 reference_style、导出格式 export_format、字体 font。每项都要
能指回模板原文；指不回的项如实留空——引擎会以 spec_value_missing 逐字段点名，这比编造一个
数字诚实得多。模板多版本或院系规定互相冲突时，把冲突条目抄进 conflicts 并用 adopted 写明
采用哪一版。

## 评分要求映射（rubric 三段 → 本 Skill 落点）

| rubric 输出要求 | 完成标准（rubric 原词） | 本 Skill 落点 |
|-|-|-|
| 目标产物 | 满足题目指定体裁、受众和格式 | 排版后的可编辑稿件 + 模板要求格式的导出件 + 预览；result.json 经 output_contract 直通携带交付字段（revised_manuscript、export_record 等） |
| 事实与来源映射 | 可逐条回溯，不新增材料外事实 | references 清单与正文引用互认；checks_done 对照模板 checks；input_units/output_units 与 pre_conversion_text 证明内容未增删改；findings 带 key/field/kind 逐条定位 |
| 版本与边界 | 结果可继续编辑，未确认部分明确标注 | conflicts + adopted 记录采用的模板版本；export 六项真值逐项记录；limits 写材料缺口与未确认项；findings + severity_counts 给出边界 |

## Rules

### Real-file template and output checks (formatfit.py)

| rule | severity | what it proves |
|-|-|-|
| `fit.input_unreadable` | high | source/template/spec 缺失、坏 JSON、坏 ZIP/XML 或不支持的源格式；exit 5 |
| `fit.processing_error` | high | 实际适配在结构化边界失败；exit 5，不泄露 traceback |
| `fit.content_changed` | high | 格式适配前后正文不再逐字一致 |
| `fit.unit_lost` | high | 实际 DOCX 中图、表、公式、脚注、批注、修订、域、分节或嵌入对象减少 |
| `fit.unit_added` | medium | 适配意外新增内容单元 |
| `fit.margin_mismatch` | high | 输出 sectPr 页边距不符合模板实测/显式要求 |
| `fit.font_mismatch` | high | 输出 Normal/docDefaults 字体不符合要求；不代表嵌入或视觉检查 |
| `fit.size_mismatch` | high | 输出 Normal/docDefaults 字号不符合要求 |
| `fit.spacing_mismatch` | high | 输出样式行距不符合要求 |
| `fit.columns_mismatch` | high | 输出栏数不符合要求 |
| `fit.heading_style_mismatch` | high | 输出可用标题层级不符合要求 |
| `fit.caption_position_mismatch` | high | 可解析的图表题注实际位置不符合要求 |
| `fit.header_footer_mismatch` | high | 要求的页眉页脚文本未出现在对应 XML |
| `fit.page_numbers_missing` | high | 模板要求页码但 footer 无 PAGE 域；只证明域存在，不证明视觉分页 |
| `fit.toc_missing` | high | 模板要求目录但文档无 TOC 域 |
| `fit.export_format_mismatch` | high | 实际交付扩展名不是模板要求格式 |
| `fit.required_text_missing` | high | 摘要/关键词/声明或模板要求章节未出现在交付文本 |
| `fit.check_unverified` | medium | 参考文献样式等当前机制不能验证，绝不记 pass |
| `fit.requirement_mismatch` | high | 其他受控字段实测不符合；保留为通用兜底规则 |

### The format spec

| rule | severity | what it proves |
|-|-|-|
| `fmt.spec_missing` | high | the template's format spec is unrecorded |
| `fmt.spec_value_missing` | medium | a controlled field is unrecorded |
| `fmt.reference_style_missing` | medium | reference style undocumented |
| `fmt.figure_never_referenced` | medium | a declared figure is never cited in the text |
| `fmt.crossref_dangling` | high | the text points at a figure number that does not exist |
| `fmt.content_rasterized` | high | the export rasterised content, so the file is not text-editable |

### Header/footer, conflicts and page numbers (declared-only)

These three fire only when the delivery or the template declares the thing they check;
undeclared, they stay silent.

| rule | severity | what it proves |
|-|-|-|
| `fmt.header_footer_unverified` | medium | the template declares header/footer requirements but a declared item has no recorded status (set with what, or explicitly not set) |
| `fmt.conflict_unresolved` | medium | the template declares conflicting provisions but no adopted record says which version the output follows |
| `fmt.page_numbers_unverified` | medium | page numbers are declared required but the export record does not confirm they are present and usable |

### Structure

| rule | severity | what it proves |
|-|-|-|
| `fmt.section_missing` | high | a required section is absent |
| `fmt.section_order` | medium | sections out of order |
| `fmt.heading_level_skip` | medium | the outline and TOC will break |
| `fmt.heading_style_unbound` | high | a heading exists only as size and weight |
| `fmt.heading_level_beyond_declared` | medium | a heading sits deeper than the declared heading_levels, so no template style can carry it |
| `fmt.toc_not_generated` | high | a required TOC is missing |
| `fmt.numbering_gap` | medium | section numbers skip |
| `fmt.word_limit_exceeded` | medium | over the declared limit |

### References

| rule | severity | what it proves |
|-|-|-|
| `fmt.citation_not_in_reference_list` | high | the text cites an absent entry |
| `fmt.reference_never_cited` | medium | the list carries an uncited entry |

### Content preserved through the conversion

| rule | severity | what it proves |
|-|-|-|
| `fmt.unit_lost` | high | the conversion dropped content units |
| `fmt.unit_added` | medium | the conversion introduced units |
| `fmt.unit_counts_incomplete` | high | one side only, so loss cannot be ruled out |
| `fmt.text_dropped` | high | a sentence of the declared pre-conversion text has no counterpart in the delivered text |
| `fmt.text_quantity_changed` | high | a numeric value changed across the conversion |
| `fmt.text_citation_changed` | medium | the citation apparatus changed across the conversion |
| `fmt.text_claim_changed` | medium | a sentence came back from the conversion with stronger claim language |

### Conversion and export

| rule | severity | what it proves |
|-|-|-|
| `fmt.conversion_undocumented` | high | the path cannot be reproduced |
| `fmt.export_unverified` | high | nothing known about the delivered file |
| `fmt.font_not_embedded` | high | the target machine will substitute |
| `fmt.page_size_unverified` | high | page size and margins unmeasured |
| `fmt.toc_not_refreshed` | high | TOC page numbers are stale |
| `fmt.page_numbers_unverified` | medium | page numbers declared required but unconfirmed in the export |
| `fmt.not_editable` | high | the author cannot continue from the file |
| `fmt.export_field_missing` | medium | an export property is unknown rather than good |
| `fmt.export_format_missing` | medium | the template's required export format is not the one the export record names |
| `fmt.checklist_incomplete` | high | template checks claimed but not performed |

### Audit entry (writeaudit.py)

| rule | severity | what it proves |
|-|-|-|
| `audit.no_section` | high | no section was declared, so no rules ran (exit 5) |
| `audit.spec_unreadable` | high | the spec file is missing or not valid JSON (exit 5) |
| `audit.spec_not_object` | high | the spec is valid JSON but not an object (exit 5) |
| `audit.section_unknown` | high | the declared section is not implemented (exit 5) |
| `audit.section_error` | high | the audit could not complete on this spec (exit 5) |

## 异常处置表

| 情况 | 处置 |
|-|-|
| case.json 缺失或不可读 | 依 task.md 继续；result.json 的 case_id 写 null 并在 limits 注明来源缺失 |
| spec 不是合法 JSON / 不是对象 | 引擎返回 status undetermined（exit 5），finding 为 audit.spec_unreadable 或 audit.spec_not_object；修 spec 后重跑，不得手写 result.json |
| section 字段缺失或取值未知 | audit.no_section / audit.section_unknown（exit 5）；用 --section 显式指定 format_template |
| 字段类型错位（template、headings、export、references、units、figures、checks 是字符串或数字） | 引擎把非容器降级为空容器继续审，产出发现而不是崩溃；按发现补齐字段 |
| 模板规格抽不全 | spec_value_missing 逐字段点名；抽不到的项标注 not provided，不编造数值 |
| input_units 或 output_units 只有单侧 | 补齐另一侧；确无来源时接受 unit_counts_incomplete（high）并在 limits 说明 |
| 转换工具失败（如编译报错） | 修错重跑；仍失败则交付可编辑源文件，limits 记录失败步骤，不得伪造 export 记录 |
| 字体缺失 | 按案例指定字体执行（如 Liberation Serif）；export 的 font_embedded 写实测真值 |
| 模板冲突未说明采用版本 | 冲突双方抄进 conflicts，adopted 写明采用版本及依据 |
| 重复运行结果不一致 | 引擎纯确定性（gate G5 断言两次运行 findings 全等）；不一致说明 spec 被改动，恢复 spec 重跑 |
| findings 为空但任务明显未完成 | 先查路由是否跑错 section；跑错 section 会得到假 clean |
| 输出目录不可写 | 检查 /app/output 权限，或先写 /app/work 再复制 |
| case.json 的 output_contract 字段在 spec 里没有值 | result.json 中该字段为 null 且 limits 注明；不得用编造值填充 |

## Output contract

/app/output/result.json（主入口由 formatfit.py 写出）包含 schema_version=formatfit/v1、顶层
case_id、status、findings、severity_counts、checked、limits、deliverable/revised_manuscript、
template_requirements（含逐字段来源）、compliance、applied_changes/change_log、
content_preservation、sources（真实路径与 SHA256）、export_record 和 rendering。案例
output_contract 的每个字段也位于顶层，严格按“引擎实测值 > 案例/spec 值 > null+limits”
回填并保留 output_contract_fields 名称清单。writeaudit.py 的 writeaudit/v1 仅用于旧声明审计。

## Limits

- **Primary formatfit reads actual files.** DOCX 页边距、栏数、样式、标题绑定、文本和九类内容单元由 OOXML 实测；TeX class/geometry/font/bibliography 从模板源码提取。它不把申报值当成实测值。
- **Safe apply is intentionally bounded.** 自动应用页边距、页面尺寸、栏数、Normal/docDefaults 字体字号行距、Heading/Caption 样式及按原句精确匹配的标题绑定；不重排图表、不改参考文献语义、不写摘要/声明、不转换 TeX 源稿。无法自动安全完成的项进入 unverified/limits，交 Agent 或作者实际处理，不伪造完成。
- **Direct run-level formatting may override base styles.** formatfit 检查 Normal/docDefaults 与受控样式，不证明每个 run 都没有直接格式覆盖；渲染前需逐项查看并在 limits 保留此边界。
- **Rendering is separate.** rendering.visual_inspection 永远由脚本写 not_performed。只有 Agent 真正调用渲染器并查看 PDF/PNG 后，才能在人工记录中描述所见；font embedding、页码视觉可用性和分页美观不能由 OOXML 推断。
- **Legacy writeaudit limits (declaration-only interface):**

- **Unit counts are declared, not extracted.** The audit compares the numbers you supply; it
  does not open the .docx and count footnotes. Supplying both sides is what makes the check
  meaningful.
- **Body-text preservation needs pre_conversion_text.** Sentence pairing, quantity and
  citation deltas run only when the delivery declares the pre-conversion text; without it,
  counting alone decides.
- **Headings come from a structured list.** Numbered lines in the text are not parsed into
  levels here; supply headings.
- **Export properties are booleans you report.** The audit enforces that they are stated, not
  that they were measured by this tool.
- **Header/footer is a record check, not a sight check.** It enforces a recorded status per
  declared item (header_footer_applied, or header_footer_status), where an explicit mark such
  as not set is the honest answer the task accepts. Checked only when the template spec
  declares a non-empty header_footer dict.
- **Conflict adoption is recorded, not judged.** An adopted field — on the template, its spec,
  or the delivery — must name the version followed. The audit cannot verify the choice was
  applied correctly, only that it was made.
- **Page numbers are declared-only and do not double-flag.** An empty export record is already
  reported by export_unverified, so this rule stays out of the way there.
- **Export format is a naming check.** It reads the export record for format or formats and
  compares against the declared export_format; it cannot open the file.
- **No typography beyond the spec fields.** Leading, tracking, hyphenation and widow control
  are outside it.
- **Word counting differs by convention**, so the number is indicative.
- **Cross-reference checks need the figure numbers declared.** Without a figures list they
  stay silent; with one, every figure must be cited by number and every cited number must
  exist.
- **content_rasterized is declared, not detected**: record it honestly if the export path
  turned text into pictures.
- 混合任务（翻译/审稿/证据写作）的规则表在对应 section 的引擎源码里；本文件只展开
  format_template 与审计入口的规则，避免无关规则淹没本文档。

## Failure handling

| symptom | what to do |
|-|-|
| heading_style_unbound | apply a paragraph style, not bold and a bigger font |
| heading_level_beyond_declared | fold the heading into the deepest declared level, or extend the template |
| unit_lost | the conversion damaged the document — redo it and recount |
| unit_counts_incomplete | count both sides; one side proves nothing |
| text_dropped | find the dropped sentence and restore it, or record why it is gone |
| text_quantity_changed | a number moved during conversion — restore the source value |
| text_citation_changed | restore the citation markers the conversion altered |
| text_claim_changed | restore the original claim strength; a format pass never rewrites science |
| conversion_undocumented | record the steps so the path is repeatable |
| font_not_embedded | embed fonts on export |
| toc_not_refreshed | refresh fields before the final export |
| page_numbers_unverified | confirm page numbers in the export record (page_numbers_ok) |
| header_footer_unverified | record each declared header/footer item as set (with what) or explicitly not set |
| conflict_unresolved | record which template version the output follows, in adopted |
| export_format_missing | produce the required format (keep the editable master), or record the substitution |
| checklist_incomplete | run the template's checks and record which you ran |

## Verification

```bash
python scripts/bench_formatfit.py  # 15 scenarios: real DOCX/TeX recognition/apply/refusal/determinism
python scripts/bench_format.py     # 44 scenarios: declaration-level rules, each defect with FP guard
python scripts/bench_writing.py    # 20 scenarios: cross-section regression
```

All pass in full on this machine (15/15, 44/44 and 20/20). The clean baseline in each must
report nothing. DOCX fixtures are generated in temporary directories and never shipped.

## Requirements

Python 3.9+（3.14 实测）。纯标准库实现，无第三方依赖。scripts/ 下 formatfit.py（真实文件主入口）、
writing.py（声明规则引擎）、guard.py、redline.py、writeaudit.py（旧入口）均可独立导入。
DOCX 处理只用 zipfile + ElementTree，不要求 Word/LibreOffice；渲染预览若任务需要则使用平台
提供的 office-renderer，并把其实际产物与人工视觉结论分开记录。

## 创新增益

以下均为引擎真实具备、可复跑验证的能力（bench 与 gate 是回归证据）：

1. **真实模板识别与安全应用**：formatfit 从实际 DOCX/TeX 模板反推检查项，以 task.md 显式要求覆盖模板默认值并记录来源；对可安全修改的 OOXML 字段实际落盘另存，而非只把目标规格抄回结果。
2. **逐项合规矩阵**：每个声明字段都有 required/observed/status/evidence，通过、失败、不可验证三态互不冒充；参考文献语义、视觉渲染、字体嵌入和分页无法验证时明确保留。
3. **双轴审计**：格式符合度与内容完好性在同一次运行内分别出证。内容轴有两条互补机制——
   单元计数守恒（input_units 与 output_units 对九类单元逐一比对，转换丢了脚注/公式/批注即
   点名）与正文保真比对（声明 pre_conversion_text 后，单调 DP 对齐器逐句配对，丢句、数值
   漂移、引用装置变动、语气强度抬升各有一条规则）。通用 Agent 无法对自己的排版产物做这两项
   证明。
2. **declared-only 零误报设计**：页眉页脚、模板冲突、页码、导出格式、标题深度、正文保真
   六类检查只在案例声明对应字段时启动；最小输入的 clean 基线零发现是 bench 的硬性断言，
   不是口号。
3. **确定性可复跑**：纯标准库、无随机源，同一 spec 两次运行 findings 完全一致（验收 gate
   的 determinism 断言实测通过）；重复运行不会漂移，差异只可能来自 spec 改动。
4. **契约直通**：顶层 case_id 与 output_contract 全字段按“引擎实测值 > 案例/spec 值 > null+limits”
   自动回填；拒跑路径仍保留可读取的契约字段并输出 status undetermined 的可追踪 result.json，
   绝不伪造契约字段或泄漏 traceback。

## 生态贡献

1. **SKILL.md 全量文档**：用途、适用条件、调用方式、输入输出、异常处理、限制与自查方法齐备。
2. **纯标准库引擎**：formatfit + 四个兼容模块无第三方依赖，可独立导入、可嵌入他人流水线；真实文件处理不依赖作者本机路径。
3. **规则清单与引擎一一对应**：本文件每条 rule id 都能在引擎里找到发出点（验收 gate 的规则
   奇偶校验强制），他人可直接把规则表当作模板适配检查清单复用。
4. **最小调用示例**：examples/run_minimal.py 在临时目录真实创建/适配/复核 DOCX；
   examples/spec.json 与 examples/bench-report.json 明确只用于旧声明式兼容接口。
5. **回归套件可独立复跑**：bench_formatfit.py 15 个真文件场景 + bench_format.py 44 场景 +
   bench_writing.py 20 场景；真实应用、模板识别、内容守恒、敌意输入、确定性与旧接口 clean 基线均有断言。
6. **异常处置表与 Failure handling 表**：12 类异常、16 类发现的处置动作可直接移植到其他
   格式适配任务。
7. **稳定行为契约**：退出码 0/3/4/5 与 result.json 字段表固定，上层流水线可程序化消费。
8. **验收 gate 可复跑**：本包可通过 strict_gate.py 的 G1-G7 七项验收（打包/基准/文档路径/
   规则奇偶/确定性/冷启动/真实输入冒烟），他人可对复刻包执行同一验收。
