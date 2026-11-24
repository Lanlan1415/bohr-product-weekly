---
name: template-fit
description: >
  Apply an academic PPTX/POTX template and whole-deck house style for real. Use when a task
  supplies a starting deck, template, master/layout requirements, fonts, colors, margins, logos,
  footers or export rules. Measures master→layout→placeholder relationships, applies native title/body
  placeholders and theme fonts/colors, batch-applies geometry and dynamic page numbers, fits figures,
  and audits the delivered PPTX for overflow, overlap, bounds, contrast, layout drift, invalid packages
  and nondeterminism. Produces an editable PPTX, real PDF preview when a renderer exists, evidence map,
  template application record, version ledger and full case/output_contract JSON with exits 0/3/4/5.
---

# template-fit：把模板真正套进文件，而不是写模板名称

本技能完成 **科研材料/起始 deck → 可编辑 PPTX → 实际模板/批量格式 → 导出件与偏差记录**。
只交付文字建议、只复制模板文件名、只修封面和前三页，或把 XML 能解压冒充 Office 能打开，都不算完成。
先打开实际论文、图表、起始 PPTX 和模板，再写页面；不得虚构科学数据、模板、字体、预览或软件状态。

## 固定运行入口

输入为 `/input/case.json`、`/input/task.md` 与真实附件。中间文件放 `/app/work`，结果放 `/app/output`。

0. **先读契约和需求。** 逐字段记录 `case_id` 和 `output_contract`；从 task 固定受众、时长、页数、模板、
   母版/版式、字体、RGB、页边距、页脚/Logo/页码、导出要求。定位实际 PDF、图形、数据、PPTX/POTX。
1. **建立内容映射。** 从材料提取问题—方法—结果—限制，按受众/时长排页。每页一个 claim 和 role，
   标题写结论，evidence 精确指向实际图/表/公式/章节/数据。图页有 image_alt/caption/evidence；speaker notes
   负责解释和过渡，不复读标题。结论页必须保留限制，不能把备份页当结束页。
2. **先抽真实源稿/模板。** 有起始 deck 时用 `decksource.py` 抽骨架，不从记忆重建；有 `template.file` 时实测
   layout、master、主题和占位符。文件标签不是母版，POTX 扩展名也不是模板可打开的证明。
3. **构造 spec。** 将交付版 slides、available_evidence、require_notes、min/max_slides、font/spacing、style、
   source_deck、batch_format、template 与不确定性写入 `/app/work/spec.json`。CLI 传 `--case /input/case.json`，
   无需复制或改名 contract 字段。
4. **尽早生成真实文件。** 运行下述唯一构建 CLI。引擎先产生 deck.pptx，再读回最终文件审计；
   还导出 evidence_map、presentation_plan、change_records 和 renderer 可用时的真实 PDF。
5. **按 findings 修文件并重跑。** 溢出用删要点/拆页/换 layout，不把字号压到下限；图号不一致修 caption/evidence
   映射；同 layout 的位置、字号、RGB 漂移逐页修复，而不是只修标题。材料确实不支持时写 uncertainty/gaps/limits。
6. **交付前独立复核。** 检查 deck 非空、最终 PPTX 与 PDF 页数、母版/布局位置、占位符、页脚和页码、每页证据。
   没有 renderer 时只能声称结构几何检查，禁止创建假 PDF 或把 preview false 改成 true。

## 真实 CLI

```bash
python -I -X utf8 scripts/deckbuild.py \
  --spec /app/work/spec.json \
  --case /input/case.json \
  --out /app/output
```

可选 `--case-id` 只在没有 case 文件时补充已知标识。Python 3.10+，核心全部标准库；Pillow/matplotlib 只是可选加速，
不成为导入依赖。渲染自动尝试 PATH 上的 soffice/libreoffice/office-renderer 和常见安装位置。
`DECKBUILD_NO_RENDER=1` 仅供作者快速回归，正式案例不要设置。

实际产物：

- `deck.pptx`：可编辑 PresentationML；源稿保包修改、模板母版/版式和 notes body placeholder 真实存在；
- `deck.pdf`：只有实际渲染成功、字节非空和 `%PDF-` 文件头有效时才列出；
- `result.json`：包含最终 findings、deck、preview、checked、template_measured、template_application、
  source_record、version_record、evidence_map、uncertainty、limits 与原 case 的全部契约字段；
- `evidence_map.json`、`presentation_plan.json`、`change_records.json`：用于逐页/逐版独立复核。

## 三页最小 spec 骨架

```json
{
  "section": "template_fit",
  "case_id": "demo-only",
  "output_contract": ["case_id", "deck_file", "evidence_map", "template_application", "version_record"],
  "spacing": {"title": 32, "body": 20},
  "font_latin": "Arial", "font_ea": "Microsoft YaHei",
  "min_font_pt": 14, "max_bullets_per_slide": 5, "require_notes": true,
  "template": {"file": "/input/university.pptx", "name": "university-v2",
               "layouts": ["Title Slide", "Title and Content"]},
  "require_title_placeholder": true,
  "style": {
    "margins_in": [0.35, 0.5, 0.9, 0.5],
    "colors": {"background": "FFFFFF", "text": "1A1A1A", "title": "17365D",
               "accent": "0072B2", "muted": "5F6B76"},
    "footer": {"text": "Department · Research Review", "page_numbers": true,
               "logo": "/input/dept-logo.png", "logo_alt": "Department logo"}
  },
  "available_evidence": ["Sec. 2, p.3", "Fig. 3b, p.7", "Sec. 5, p.12"],
  "slides": [
    {"title": "多孔涂层解决吸收速率瓶颈", "layout": "title", "role": "question",
     "claim": "吸收速率是要解决的问题", "evidence": "Sec. 2, p.3",
     "pace_minutes": 1.5, "notes": "先立问题，再进入对照。"},
    {"title": "涂层组速率为对照组 2.52 倍", "layout": "content", "role": "result",
     "claim": "31.2 / 12.4 = 2.52", "evidence": "Fig. 3b, p.7", "pace_minutes": 3,
     "caption": "Fig. 3b, p.7 — 每组 n = 6", "bullets": ["对照 12.4 a.u.", "涂层 31.2 a.u."],
     "notes": "直接指向面板和条件。"},
    {"title": "单一厚度结果不能外推", "layout": "content", "role": "limit",
     "claim": "厚度边界限制外推", "evidence": "Sec. 5, p.12", "pace_minutes": 1.5,
     "bullets": ["仅测一个厚度", "长期稳定性未评估"], "notes": "以结论和限制收束。"}
  ]
}
```

替换为材料真实值。`available_evidence` 是白名单，不能用它是为了让审计通过而填不存在的定位。
每页都有 claim/evidence，图注只写材料支持的样本、条件和面板含义。

## 真实模板：测量、应用和读回核验

`template.file` 接受实际 `.pptx` 或 `.potx`。**不要**在没有模板文件时填 file 路径；无 file 时只应用声明式规则。
实测内容：

- `presentation.xml` 的 exact slide size（EMU），区分“画布相同”与仅宽高比相同；
- layout 的 name/type、layout→master 回链、master 目标部件是否存在；layout 别名只在唯一匹配时应用；
- theme major/minor latin/EA 字体与完整主题色；
- 所选 layout 的 title/body placeholder、类型/idx、几何、字号以及 bodyPr 内边距；
- layout 的 placeholder 自身缺几何/字号时，仅在该 placeholder 确实存在时沿真实 master 继承，blank layout 不会凭空获得 title。

应用顺序：

1. 从零生成或保包修改源 deck；
2. 显式开启时做 batch_format；
3. 复制真实 master/layout/theme 及依赖、更新画布和关系，重连每页 layout；
4. 有对应真占位符时，把 title/body 写成原生 `p:ph` 并应用实测几何、字号、字体、bodyPr 和主题色；
5. 移除生成阶段的默认显式背景，恢复模板继承；
6. 读回最终 slide，核对标题/正文几何、字号、RGB、layout 和 master，并把应用结果写进 `template_application`。

没有 title/body placeholder 的 blank layout 不会被伪造成占位符；对应文本框回退写入 `placeholder_records`。
`require_title_placeholder: true` 时缺 title ph 是 high，不能以文本框代替后隐瞒。slide layout type 必须是合法 OOXML 枚举，
不要发明 `body` 当 layout type；内容页可用 `obj` 等合法类型并靠实测 name/alias 匹配。

主题色的原则是 **最终真实模板优先**：应用时用主题色替换明确 title/body RGB。`template.theme_color_mismatch`
以交付文件实际 RGB 为准；直接的无产物单元审计才退回比较声明值。已经被真实主题修正的旧声明不会继续误报。
字号阶梯同样优先读交付文件实际 title/body size，不再按已被纠错的旧 spec 判失败。

## 可选演示模板生成器

仅用于演示/回归接口，不是正式模板或预制答案。它在临时位置生成可打开的 PresentationML，再扩展为
Title Slide / Title and Content 两个真实 layout：

```bash
python -I -X utf8 scripts/make_template.py --out /app/work/demo-template.pptx \
  --latin Arial --ea "Microsoft YaHei"
```

把你的 spec 中 `template.file` 指向该 PPTX，再运行 `deckbuild.py`。生成器不写死科学结果；二进制只在运行目录产生，
不得放进技能提交包。本机回归用 LibreOffice 实际打开了原模板和应用后的 deck，而不是只检查 zip。

## 起始 deck：source_deck 与可重复编辑

```bash
python -I -X utf8 scripts/decksource.py --source /input/start.pptx --out /app/work/source.json
```

在 spec 加 `"source_deck": "/input/start.pptx"`。源包所有部件先复制；revisions 支持跨 split runs 文本替换/删除、
指定 Title/Body/shape 的 `set_geometry` 和 `set_style`，记录 before/after/reason、状态、源/产物 SHA-256 和包成员变化。
`delivered_revision` 截断到交付轮；after 已存在是幂等 `already_present`，不是 before_missing。

## 整册批量格式：batch_format

仅在显式声明 `batch_format` 时修改源稿的整册样式。完全格式如下：

```json
{
  "source_deck": "/input/start.pptx",
  "batch_format": {
    "footer": true,
    "title_style": {
      "font_size_pt": 32, "color": "17365D", "bold": true,
      "font_latin": "Arial", "font_ea": "Microsoft YaHei"
    },
    "body_style": {"font_size_pt": 20, "color": "1A1A1A"},
    "title_geometry": {"x": 0.5, "y": 0.35, "w": 12.33, "h": 1.0},
    "body_geometry": {"x": 0.5, "y": 1.5, "w": 12.33, "h": 5.1}
  },
  "style": {
    "margins_in": [0.35, 0.5, 0.9, 0.5],
    "colors": {"background": "FFFFFF", "text": "1A1A1A", "title": "17365D", "muted": "5F6B76"},
    "footer": {"text": "Department · Research Review", "page_numbers": true,
               "logo": "/input/dept-logo.png", "logo_alt": "Department logo"}
  }
}
```

- 几何 dict 为英寸 x/y/w/h；也接受 EMU `title_geometry: {"x", "y", "cx", "cy"}`。cover 无 body 时不报错。
- 页脚/页码/Logo 按每页真实画布置入；动态页码用 `p:ph type="sldNum"` + `a:fld type="slidenum"`。
- 开启 footer 替换会删除本工作流旧 Footer/Slide Number/Logo（包括 `p:pic` 类型 Logo）再重建，避免重复。
- `"footer": false` 只关闭页脚替换，不删除原页脚，也不妨碍 title/body_style。不要为了“样式统一”丢原页脚。
- Logo 是所有页共享的一个 media 部件；缺失时不能伪造图标。新增部件在 `source_record.added_parts` 明示。
- batch 后若再套真实模板，由模板的 title/body 最后胜出；batch 的 footer/page number/Logo 保留。两次完整构建
  对最终 slide 文本、几何和 notes 做一致性检查，OPC 部件重复测试还可独立比较。

批处理只能修改明确支持的 DrawingML，不声称修改动画、OLE/SmartArt 内部或所有 group transform。
被覆盖的源包不能无故掉部件；仅为声明的共享 Logo/关系新增部件不算破坏保全。

## 从零生成与图片/页脚样式

`style.margins_in` 顺序为 **TRBL（上、右、下、左）**；`slide_in` 默认 13.333×7.5。`title_height_in`、`gap_in`、
`image_ratio` 控制实际布局。正文、无图 caption 与 footer 预留独立带区，不能事后把 caption 覆盖在正文上。
PNG/JPEG 尺寸从文件头读取并等比 fit-and-centre，Logo/Fig 都保留 alt。图表内部仍是位图，不能宣称转成原生 chart dataset。
字号、字体、RGB、页脚、动态页码、Logo 都写进真实 XML，随后再检查是否落文件。

## 实际检查，而非模板自述

| 层面 | 最终检查 |
|-|-|
| 科研映射 | 每页 claim/evidence 白名单、caption↔locator、图/来源缺失讲清 |
| 母版模板 | layout 唯一匹配、master 部件存在、slide→layout→master 链、真实 master/theme、原生 title/body ph |
| 跨页一致 | 同 layout title/body 几何和字号、实际字体与主题、实际 RGB、页边距/留白、页脚、页码、Logo |
| 内容落位 | 声明标题/bullets/caption/slide 是否写入最终页，图注/证据是否对应 |
| 可读性 | CJK 断行 + 实际 glyph advance 的宽/高溢出、字号下限、要点密度、位图比例、空白页、空白 deck |
| 几何 | 负坐标、出画布、零尺寸文本框、显著 overlap；图片注记单列，不与正文—正文 high 混淆 |
| 导出 | 真实 PDF、字体发现/缺字/嵌入声明、deterministic 重跑、OPC/ContentTypes/Relationships 可打开性 |
| 契约 | 原 case_id、output_contract 对象和每个同名字段；审计值优先，未推导值 null + limits |

继承 placeholder 没有显式 xfrm 时不被误判为零尺寸。几何审计只覆盖显式 slide shapes/pictures，不模拟全部组合变换、
PowerPoint 自动布局或字体渲染。溢出测量不含 kerning/ligature。PDF 文件生成不自动等于逐像素一致，应光栅化关键页；
无法渲染/查看时必须在 limits 写明。科学内容仍须人工/Agent 回到原材料，`clean` 不是科学正确性的替代品。

## 状态、结构化拒绝与契约

| status | exit | 用法 |
|-|-|-|
| clean | 0 | 无 findings；并不自动证明科学语义或平台评分 |
| review | 3 | 仅 medium/low；可交付但必须说明剩余问题 |
| blocked | 4 | 至少一个 high；不得声称完成 |
| undetermined | 5 | spec 缺失/坏 JSON/非对象、未知 section、源文件无法运行等 |

主要 high 包括 template.layout_not_found、template.layout_master_missing、template.unreadable、
format.undeclared_layout、format.content_dropped、format.footer_missing、format.page_number_missing、
text.overflow、layout.out_of_bounds、layout.overlap、image.source_missing/logo_missing、master.layout_missing。
`template.title_placeholder_missing` 在 require_title_placeholder 时启用；title/body 几何无法测、主题/字号/色彩漂移分别报告。

CLI 边界即使遇到未预期错误也写 result、无 bare traceback。只要 case 可读，坏/缺失 spec 的拒绝 result 也保留 case_id 和全部
output_contract 字段；不存在的推导值保留原名写 null，而不是省略。contract 支持字符串、名称数组、name→说明对象和
含 field/name/key 的对象数组。审计结果会覆盖 spec 里伪造的 status/deck 自报值。

task.md 或材料不可读时，Agent 在 uncertainty/gaps/limits 中区分“材料缺失、无法判断、运行失败”。
渲染器不可用不会生成空 PDF 充数；语法可运行的 spec 仍尽可能留下诚实的部分 PPTX 和差异记录。

## 完整最小示例

`examples/spec.json` 是声明式 house-style 演示（无外部二进制依赖），四页包含问题、方法、结果、限制、页码、备注和契约。
它是接口示例，不是正式案例答案。

```bash
python -I -X utf8 scripts/deckbuild.py \
  --spec examples/spec.json --case-id ppt-710fbc72-demo --out /app/output
```

真实模板 smoke 先运行上文的 `make_template.py`，再把交付 spec 的 `template.file` 指向生成的 PPTX。
平台预览状态以当前运行的 preview 为准，不照搬作者机器的渲染状态。

## 开源机制确实落地

- **PptxGenJS**：真实 master 对象挂接、TRBL margins、theme font/solidFill、bodyPr、动态 slidenum field。
  本包在 `pptxgen.py`、`decksource.py`、`templatecheck.py` 实现；另写开源中没有通用实现的越界、重叠和文本溢出审计。
- **python-pptx**：按 layout 的 placeholder 类型/idx/继承关系生成 title/body，notes 用真实 body placeholder，
  不盲目克隆 date/footer/slide-number placeholder。见 `templatecheck.py` 和 `pptxgen.py`。
- **reveal.js**：固定画布、按剩余空间布局、媒体内在比例 fit；以其思路实现 OOXML 布局，最终产物是 PPTX 而不是 HTML。

参考实现为 gitbrent/PptxGenJS、scanny/python-pptx、hakimel/reveal.js；无这些库的运行时依赖。
特别保证 OPC/ContentTypes/Relationships 在每次回写时保留正确结构，接受真实 LibreOffice 打开/导出验证而非仅 XML parse。

## 作者侧复核（不在正式工作流中替代出稿）

```bash
DECKBUILD_NO_RENDER=1 python -I -X utf8 scripts/bench_deck.py
DECKBUILD_NO_RENDER=1 python -I -X utf8 scripts/bench_deck2.py
DECKBUILD_NO_RENDER=1 python -I -X utf8 scripts/bench_template.py
DECKBUILD_NO_RENDER=1 python -I -X utf8 scripts/bench_extra.py
DECKBUILD_NO_RENDER=1 python -I -X utf8 scripts/bench_delivery4.py
DECKBUILD_NO_RENDER=1 python -I -X utf8 scripts/probe_delivery4.py
```

70 个 legacy 场景覆盖原有模板/审计规则；新增 bench_delivery4 覆盖真实双 layout、颜色/画布纠正、源稿 batch、
Logo/页码幂等、body drift 和契约对象；probe_delivery4 用真实 CLI 覆盖拒绝、退出码、完整字段、无 traceback、
重复构建、真实 source batch 和真实模板。测试二进制只写临时目录。报告 `scripts/report_*.json` 不是平台正式成绩。

## 适用边界

- 引擎不替 Agent 做论文精读或判断 scientific claim；页级白名单和最终映射仍需回读源材料。
- 模板应用覆盖真实 master/layout/theme 及 title/body 占位符，不是整个 PowerPoint 排版引擎的复刻。
- 图片的位置/尺寸可编辑，图片内部不是原生 chart series；不从位图编造可编辑数据。
- 字体声明不等于嵌入；缺字体、缺字形和未嵌入风险照实记录。目标机不同仍可能回流。
- 无 renderer 时只报告 preview=false 和结构几何检查，不声称视觉验收。
