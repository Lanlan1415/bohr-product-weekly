---
name: deck-edit
description: >
  Create and revise real academic PPTX files without losing evidence or version history.
  Use for generating, editing, shortening, expanding, translating, re-templating or iterating
  an academic presentation. Preserves a supplied source deck and applies DrawingML text,
  geometry and style edits; creates editable slide layouts, notes, figures, theme colors,
  footers, logos and dynamic slide numbers; verifies evidence locators, before/after records,
  fonts, glyph coverage, canvas bounds, overlap, contrast and deterministic reruns; returns
  case_id and every output_contract field with structured 0/3/4/5 exits.
---

# deck-edit：真实生成/编辑学术 PPT，并保留证据与版本

本技能交付的是 **可打开的 .pptx、实际导出件（渲染器可用时）和可复核记录**，不是内容建议。
先看论文、研究材料、起始 deck 和模板，再写页面。材料没有支持的数字、图号、结论、模板状态、
字体状态或预览不得补造。`clean` 是机械审计结论，不等于科学内容已经获得专家认可。

## 固定运行入口

运行环境把技能装在 `/skills/weekly-skill`。输入是 `/input/case.json`、`/input/task.md` 及其实际附件；
中间文件放 `/app/work`，正式产物放 `/app/output`。按以下顺序完成，不要先做长时间的文字规划而迟迟不落盘。

0. **读输入和契约。** 读 case 的 `case_id`、原 `output_contract` 的每个字段；读 task 的受众、时长、
   页数、编辑轮次、起始 deck、模板、语言和导出要求。枚举实际 PDF、数据、图、PPTX/POTX；标签不是证据。
   PDF 要读原文件，不假设存在预抽取答案。
1. **建立主线与页级计划。** 从材料提取研究问题、方法、结果和限制；指定 `goal.objective/audience/minutes`。
   每页只承担一个可反驳 `claim`、一个 `role`、一个 `pace_minutes`（有时长时），标题直接写该页结论，
   不写“结果”“方法概述”这类主题词。最后一页给可复述结论与局限/下一步，备用页不得挤掉结论。
2. **先形成诚实版本。** 页级标题、claim、evidence、bullets、caption、notes 和修改记录写入
   `/app/work/spec.json`。每页 evidence 精确命中 `available_evidence` 中真实存在的图、表、公式、章节或数据定位。
   图页同时给 `image/image_alt/caption/evidence`；caption 保留条件、样本和面板含义，不生成替代曲线。
   speaker notes 写讲述顺序、解释和过渡，不复读标题。
3. **选择真实产物路径。** 无起始稿时从零生成；有 `source_deck` 时先抽取源稿并保包编辑；有
   `template.file` 时测量并套用实际母版/版式/主题。三条路径可组合，但 spec 的 slides 必须描述交付版。
4. **生成并读回审计。** 在技能目录执行下述 CLI。引擎先写 `/app/output/deck.pptx`，读取最终 OPC/XML
   部件检查，再写 result、证据图、版本台账和可用的 PDF。不得把 spec 或 result.json 当作 PPT 的替代品。
5. **修发现并重跑。** 修页面或台账，不得为消除 finding 编造材料。溢出应删要点或拆页，不能缩到可读下限以下；
   母版、模板、图号或修改落位有误要修文件。剩余材料缺口写入 `uncertainty`、`gaps` 和 `limits`。
6. **核对交付。** 确认 deck 非空且可打开、result 含 case 的全字段、主要文件路径真实存在、案例角色/页数/时长
   一致。渲染器不存在时禁止创建假 PDF；明确说明只能做结构几何检查。运行时产物可以是二进制，技能包只放文本资源。

## 唯一真实 CLI

```bash
python -I -X utf8 scripts/deckbuild.py \
  --spec /app/work/spec.json \
  --case /input/case.json \
  --out /app/output
```

可单独用 `--case-id` 在没有 case 文件时保留已知标识；CLI 没有其他隐式安装步骤。Python 3.10+，核心只用标准库。
LibreOffice/soffice/office-renderer 是可选导出工具；Pillow/matplotlib 只用于可用的加速，字体测量可完全回退到标准库。
`DECKBUILD_NO_RENDER=1` 只供作者快速回归，**正式案例不要设置**。

正常路径写出：

- `deck.pptx`：可编辑 PresentationML；有 speakers notes 时，文字在实际 notes body placeholder 中；
- `deck.pdf`：只在真实渲染成功且文件非空、文件头为 PDF 时存在；
- `result.json`：审计、契约、页级 evidence_map、preview、source_record、template_application、版本与限制；
- `evidence_map.json`、`presentation_plan.json`、`change_records.json`：从最终 spec/审计生成的复核件。

## spec：公共骨架

```json
{
  "section": "deck_edit",
  "case_id": "demo-only",
  "output_contract": ["case_id", "deck_file", "evidence_map", "version_record", "custom_note"],
  "custom_note": {"kept": true},
  "spacing": {"title": 32, "body": 20},
  "font_latin": "Arial",
  "font_ea": "Microsoft YaHei",
  "min_font_pt": 14,
  "max_bullets_per_slide": 5,
  "require_notes": true,
  "min_slides": 4,
  "max_slides": 8,
  "goal": {"objective": "让评审理解证据与外推边界", "audience": "同行评审", "minutes": 8},
  "available_evidence": ["Sec. 2, p.3", "Fig. 3b, p.7", "Sec. 5, p.12"],
  "slides": [
    {"title": "涂层解决吸收速率瓶颈", "layout": "title", "role": "question",
     "claim": "吸收速率是要解决的问题", "evidence": "Sec. 2, p.3", "pace_minutes": 1,
     "notes": "先立问题，再进入对照。"},
    {"title": "等温对照分离结构效应与热效应", "layout": "content", "role": "method",
     "claim": "对照设计区分了两种解释", "evidence": "Sec. 2, p.3", "pace_minutes": 2,
     "bullets": ["两组等温", "每组 n = 6"], "notes": "说明对照条件。"},
    {"title": "涂层组速率为对照组 2.52 倍", "layout": "content", "role": "result",
     "claim": "31.2 / 12.4 = 2.52", "evidence": "Fig. 3b, p.7", "pace_minutes": 3,
     "caption": "Fig. 3b, p.7 — 两组，n = 6", "bullets": ["对照 12.4 a.u.", "涂层 31.2 a.u."],
     "notes": "直接指向面板与精确数值。"},
    {"title": "单一厚度结果不能外推", "layout": "content", "role": "limit",
     "claim": "厚度边界限制外推", "evidence": "Sec. 5, p.12", "pace_minutes": 2,
     "bullets": ["仅测一个厚度", "长期稳定性未评估"], "notes": "以结论和限制收束。"}
  ]
}
```

正式运行必须用材料中的真实值替换演示文字。每页（包括封面和结束页）都要有 claim/evidence；
若封面只含论文题目，也把论文题名/任务说明的真实定位加入证据白名单。不得沿用示例数字。

### 图与图像

`slides[].image` 是实际 PNG/JPEG 路径。生成器从文件头读取尺寸并 fit-and-centre，不拉伸；`image_alt` 写给屏幕阅读器
和图像比例审计使用的文字，不能只在文件名中暗示来源。位图不可取数时报告不确定性，不重绘假数据。
本引擎不声称生成原生 PowerPoint 图表对象；原图/位图始终保持可编辑位置和尺寸，图表内部不变成可编辑系列。

## 起始 deck：真实保包编辑

先抽取工作骨架（它不是 result.json）：

```bash
python -I -X utf8 scripts/decksource.py --source /input/start.pptx --out /app/work/source.json
```

在 spec 写 `"source_deck": "/input/start.pptx"`，并根据真实源稿补齐每页 claim/evidence/layout/notes。
引擎复制源包全部部件，只修改明确的 slide/notes DrawingML，不按记忆重建幻灯片。源文件和交付文件 SHA-256、
执行状态及包部件是否保持完整在 `source_record` 中。`delivered_revision` 之前的修改按顺序应用，之后不进入交付版。

### 文本替换或删除

```json
{
  "slide": 3, "target": "slide", "before": "结果",
  "after": "涂层组速率为对照组 2.52 倍", "reason": "标题写结论并绑定 Fig. 3b"
}
```

- `target` 可为 `slide` 或 `notes`；替换可跨 split runs，保留首个 run 格式；删除用 `action: "delete"`、
  保留完整 `before`、`after: ""`，以便回滚。
- before 不在源稿但 after 已存在时，视为幂等的 `already_present`，不误报；两者都没有则 high。
- 任意记录的 after 必须能在指定最终页或 notes 中读回；仅有建议而未落文件会得到 `edit.change_not_in_deck`。

### 实际几何与样式修改

```json
{"slide": 3, "action": "set_geometry", "shape": "Title", "unit": "in",
 "geometry": {"x": 0.5, "y": 0.35, "w": 12.33, "h": 1.0}, "reason": "对齐版心"}
```

```json
{"slide": 3, "action": "set_style", "shape": "Title",
 "font_size_pt": 32, "color": "17365D", "bold": true,
 "font_latin": "Arial", "font_ea": "Microsoft YaHei", "reason": "恢复标题层级"}
```

`shape` 也可为唯一 `title`/`body` 占位符名。`geometry_emu` 可替代 `geometry` 并省略 unit；形状缺失、重名、
非法尺寸会写 `edit.source_change_unapplied` 并阻断。重复应用相同样式为 `already_present`。
动画、OLE、SmartArt 内部和不受支持的形状操作只能成为 `structural_record_only` 加 limits，不能宣称已修改。
`style.footer` 是从零生成页的设置，不会在保包编辑中擅自给整个源稿注入页脚/Logo；起始稿应保留其原有母版，
或用上述明确 action 完成局部格式修改。

## 从零生成：主题、页边距、页脚、Logo 与动态页码

在 spec 顶层加 `style`；省略时采用稳定默认值。

```json
{
  "style": {
    "slide_in": [13.3333333333, 7.5],
    "margins_in": [0.35, 0.5, 0.9, 0.5],
    "title_height_in": 1.0,
    "gap_in": 0.15,
    "image_ratio": 0.38,
    "colors": {
      "background": "FFFFFF", "text": "1A1A1A", "title": "17365D",
      "accent": "0072B2", "muted": "5F6B76"
    },
    "footer": {
      "text": "Methods Group · measured results",
      "page_numbers": true,
      "logo": "/input/group-logo.png",
      "logo_alt": "Methods Group logo"
    }
  }
}
```

- `margins_in` 顺序固定为 **TRBL：上、右、下、左**，不是 CSS 的四边缩写猜测；颜色用六位 RGB。
- 标题、正文、图注与页脚都由同一组页边距派生。无图 caption 会预留独立带区；图像和 Logo 保持源宽高比。
- 动态页码写为 `p:ph type="sldNum"` + `a:fld type="slidenum"`，不是逐页硬编码一段普通数字。
- 缺 Logo、缺图、页脚/页码未落文件都有 finding。`embed_fonts: true` 时，包中没有真实字体部件也会报告。
- 样式类型或 RGB 无效时安全回退并写 limits；不得把低对比背景/文字组合写成可读。正文和标题显式 RGB 均已知时，
  引擎检查 WCAG 对比度；继承主题色无法解析时不猜测。

## 真实模板套用

```json
{
  "template": {"file": "/input/university.pptx", "name": "university-v2",
               "layouts": ["Title Slide", "Title and Content"]},
  "require_title_placeholder": true
}
```

`template.file` 接受实际 PPTX/POTX。`templatecheck.py` 测量页面尺寸、布局 name/type、layout→master 关系、
主题字体/主题色、标题/正文占位符的几何/字号/正文内边距；layout 自身缺几何时，仅在该占位符确实存在的前提下沿母版继承。

应用时复制真实 master/layout/theme 和内部依赖、调整画布、重连每页 layout；标题/正文在模板有对应占位符时转为原生
`p:ph` 并应用实测 `xfrm`、字号和字体，删除会遮挡模板背景的默认背景。blank layout 无占位符时，文本框回退在
`template_application.placeholder_records` 中如实记录；只有明确要求 `require_title_placeholder` 才将缺 title ph 视为 high。
不会把“模板文件名相同”冒充已套用，也不会把普通文本框冒充原生占位符。

## 最终文件实际检查什么

| 层面 | 实际检查/产物 |
|-|-|
| 叙事与科学映射 | 每页单一 claim、role、evidence 白名单、caption↔locator、主线/时长/受众计划、结束页与限制由 Agent 按上文安排 |
| 版本 | 每轮 instruction、每条 slide/before/after/reason、删除快照、交付指针、before/after 执行状态、源/产物 hash、包成员完整性 |
| 模板 | 真实 master/layout/theme 链、layout 匹配、原生占位符、标题几何与字号、页面尺寸、字体/颜色 |
| 可读性 | CJK 断行和字形 advance width 的宽/高双向溢出、字号下限、要点密度、图片比例、空白页、空白 deck、明确 RGB 对比度 |
| 几何 | 显式形状/图片的负坐标、越过画布、零尺寸文本框、正/反向重叠；图片上有意注记单列 medium，不与正文重叠混淆 |
| 导出 | 真实 PDF 和渲染器、字体发现/缺字、master/import 包完整性、两遍 slide 文本/几何/notes 一致性、动态页码/Logo/页脚落位 |
| 契约 | case_id 优先取 case 文件；原 output_contract 对象保留，所有同名字段回填，审计值优先，无法推导为 null + limits |

几何范围是显式 slide shape/picture；不模拟全部 group transform、PowerPoint 自动布局和字体替换。文字测量不含
kerning/ligature。真实 PDF 记录表示文件成功导出，不自动证明像素级一致；应把 PDF 光栅化后查看关键页，无法查看时明确限制。
科学 claim 的语义、图片内部数值和引文真实性仍须 Agent 回读原材料，不能用规则通过代替判断。

## 修改记录与版本台账规则

- 多轮必须 `delivered_revision`，每条变更必须有 slide、reason；每轮应有 instruction、changes，否则按级别报告。
- 文本 prior/after 不能只有半边；删除保存 before；noop 记 low；指向不存在页或 after 未落文件记 high。
- `deck.empty_deck`/`deck.no_slides`、`deck.empty_slide`、`deck.no_title`、`deck.evidence_missing`、
  `deck.evidence_unsupported`、`deck.caption_not_landed`、`image.source_missing`、`text.overflow` 是主要 high。
- `layout.out_of_bounds`、`layout.overlap`、`layout.figure_overlap`、`layout.missing_geometry`、
  `format.low_contrast`、`format.footer_missing`、`format.page_number_missing`、`format.logo_missing` 读取最终文件。
- `template.*`、`format.*`、`master.*`、`font.*`、`export.*` 的精确发现都保留在 findings[]，不得从最终 result 静默删除。

## 状态、拒绝与退出码

| status | exit | 用法 |
|-|-|-|
| clean | 0 | 无 findings；仍须人工核对科学语义 |
| review | 3 | 只有 medium/low；可交付，但必须说明并处置 |
| blocked | 4 | 至少一个 high；不得把未完成品写成完成 |
| undetermined | 5 | spec 缺失/坏 JSON/非对象/路由或源文件无法运行；结构化拒绝 |

拒绝路径独立工作，永远没有 bare traceback；只有可读 case（或显式 case-id）而不依赖坏 spec。case 可读时，
连拒绝 result 也保留原 output_contract 及全部同名字段；不存在的推导值为 null。case 不可读时如实标 limits，case_id 为 null。
`task.md` 或材料丢失由 Agent 在 spec/uncertainty/limits 中区分说明，不把文件名写成结论。

`output_contract` 支持名称数组、name→说明对象、含 field/name/key 的对象数组和单字符串。正常/拒绝路径都以案例中的
case_id/contract 为准；审计已有字段不被 spec 的 `status` 或自报 deck 覆盖。自定义可推导字段可放 case/spec 顶层直通；
无法得到的字段保留原名并写 null，不改名、不漏字段。

## 完整最小示例

`examples/spec.json` 是演示接口，不是正式案例答案，四页分别承担问题、方法、结果、限制，包含动态页码、版本和全字段契约。
其中数字只用于说明映射，正式任务必须替换为源材料真实值。

```bash
python -I -X utf8 scripts/deckbuild.py --spec examples/spec.json --case-id deck-example-001 --out /app/output
```

本机作者回归曾对该类规格得到非空 deck、真实 PDF、0 findings；平台实际导出以运行环境中的 `preview` 为准，
不沿用作者机器的状态。`examples/bench-report.json` 是早期公共示例回归摘要；最新能力报告见 `scripts/report_delivery4.json` 和
`scripts/report_probe_delivery4.json`，都不是平台正式案例成绩。

## 开源机制如何落地，而非只附链接

- **PptxGenJS**：采用其 master/layout 对象关系、TRBL margins、主题字体/`solidFill`、`bodyPr` insets/wrap，
  以及 `sldNum` placeholder + `slidenum` field 的具体结构；见 `pptxgen.py`、`templatecheck.py`。
  源码未提供通用文本溢出/越界检测，所以本包另写 `deckaudit.py`，没有宣称复用不存在的能力。
- **python-pptx**：按其 slide→layout 占位符克隆原则，date/footer/slide number 不盲目克隆；标题/正文 ph 保留类型和 idx，
  几何沿 layout/master本来继承；notes 放在真正的 body placeholder。见 `templatecheck.py`、`pptxgen.py`。
- **reveal.js**：采用固定画布约束、按剩余空间布局、媒体内在比例 fit 的做法；正式产物仍是 PPTX，不是 reveal HTML。
  reveal 不负责 OOXML 级重叠/越界，本包独立实现几何检查。

参考实现：PptxGenJS（gitbrent/PptxGenJS）、python-pptx（scanny/python-pptx）、reveal.js（hakimel/reveal.js）。
这里没有引入它们的运行时依赖；上述机制均在目标包中实际实现并接受 defect + clean guard 回归。

## 作者侧复核（不进入正式运行主路径）

```bash
DECKBUILD_NO_RENDER=1 python -I -X utf8 scripts/bench_deck.py
DECKBUILD_NO_RENDER=1 python -I -X utf8 scripts/bench_deck2.py
DECKBUILD_NO_RENDER=1 python -I -X utf8 scripts/bench_edit3.py
DECKBUILD_NO_RENDER=1 python -I -X utf8 scripts/bench_extra.py
DECKBUILD_NO_RENDER=1 python -I -X utf8 scripts/bench_delivery4.py
DECKBUILD_NO_RENDER=1 python -I -X utf8 scripts/probe_delivery4.py
```

新增 `bench_delivery4` 对 styled deck、真实源稿文本/几何/样式、低对比、越界、重叠、空白页和真实模板原生占位符做产物断言；
`probe_delivery4` 对实际 CLI 的拒绝、契约、退出码、幂等和无 traceback 做探针。测试二进制只进临时目录，不进提交包。
正式用例不要运行 bench 来代替生成结果。

## 适用边界

- Agent 负责论文精读、科学取舍、视觉复核和源值核对；引擎不替 Agent 发明 claim 或证据定位。
- 支持 DrawingML 文本替换/删除、指定形状几何/字体/RGB 样式；不重写动画、OLE/SmartArt 内部、复杂组合变换。
- 模板套用是 master/layout/theme 与 title/body 占位符的真实连接，不是 PowerPoint 全部版式引擎的复刻。
- 图片可编辑位置/尺寸，但位图内部不是可编辑数据系列；不会把原图重绘为伪造的原生 chart。
- 字体“声明”不等于“嵌入”。缺字体、缺字形和未嵌入风险均记录；目标机环境不同仍可能回流。
- 无渲染器时只保留 preview.rendered=false 和结构几何检查，绝不声称已完成视觉验收。
