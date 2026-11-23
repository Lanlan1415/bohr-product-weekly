---
name: template-fit
description: >
  Adapt academic slide content to a template and verify the layout actually holds.
  The template is measured, not just declared: a real .potx/.pptx package is read
  with zipfile+xml so the layout names, theme typefaces and title-placeholder
  geometry the engine checks against are what the file contains. Audits the written
  file for a flat hierarchy, layouts and faces the real template does not provide,
  titles that drifted off the template's placeholder, a caption and a source locator
  that name different figures, declared content that never landed in the written
  deck, text overflow measured with real glyph metrics including Chinese line
  breaking (pure-standard-library TTF advance widths), characters with no glyph,
  and two builds that differ. Use when a task supplies a template, a house style,
  or a format constraint, or when a deck "looks wrong" after being pasted into one.
---

# template-fit

Pasting content into a template fails quietly. Every placeholder is filled, the file
opens, and the deck has no hierarchy: title and body at 22 and 20 pt, so nothing reads
as a heading. Or the declared typeface is not on the target machine, so the application
substitutes and every line reflows.

None of that is visible in a slide sorter, and all of it is mechanically checkable.

## Three failures that look like success

**A flat type ladder.** `spacing.title / spacing.body` below 1.35 and the deck has no
readable hierarchy. This is the most common template-adaptation defect and the least
visible.

**A template that was never really applied.** The spec declares layouts and theme
faces the real template does not provide; pages fall back to defaults and lose the
theme. Since round 2 the engine *measures* the template file instead of trusting that
declaration (see `template.*` rules).

**Chinese text measured with a Latin-only metric.** Two compounding faults, both fixed
here and both of which silently disabled the overflow check for every Chinese deck:

1. the measuring font was DejaVu Sans, which has **no CJK glyphs**, so the widths were
   wrong;
2. line breaking split on whitespace, and Chinese has none — so an entire Chinese
   paragraph measured as a single line and never overflowed.

The measuring font is now resolved against the characters actually in the deck, and
line breaking treats each CJK character as a break opportunity:

```
measure font: C:\Windows\Fonts\msyh.ttc
shape=Body  paras=5  need_px=358  box_h_px=474   (before the fix: need_px≈72)
```

## Workflow

### 1. Declare the adaptation, and name the template file

```json
{
  "section": "template_fit",
  "case_id": "ppt-710fbc72-demo",
  "output_contract": ["status", "findings", "severity_counts", "deck", "preview",
                      "reproducibility", "checked", "limits", "case_id",
                      "slide_evidence_map"],
  "spacing": {"title": 32, "body": 20},
  "font_ea": "Microsoft YaHei",
  "font_latin": "Arial",
  "min_font_pt": 14,
  "max_bullets_per_slide": 5,
  "require_notes": true,
  "template": {"name": "conf-2026", "layouts": ["title", "content"],
               "file": "examples/template.potx"},
  "available_evidence": ["Fig. 3b, p.7"],
  "slide_evidence_map": [
    {"slide": 1, "source": "paper", "locator": "Section 1, p.1"},
    {"slide": 2, "source": "figure", "locator": "Fig. 3b, p.7"}],
  "pending_confirmation": [],
  "gaps": [],
  "slides": [
    {"title": "多孔涂层加速吸收", "layout": "title", "claim": "吸收速率是瓶颈",
     "evidence": "Fig. 3b, p.7", "notes": "引入问题，不读标题。"},
    {"title": "吸收速率提高 3 倍", "layout": "content", "claim": "涂层使速率提高三倍",
     "evidence": "Fig. 3b, p.7",
     "bullets": ["对照组 12.4 a.u.", "涂层组 31.2 a.u.", "每组 n = 6"],
     "notes": "停顿；对比的是速率，不是终点。"}
  ]
}
```

template 的 file 字段 is the round-2 switch: when it names a real `.potx`/`.pptx` package,
the engine reads that package (standard-library `zipfile` + ElementTree) and the
template rules run against **measurements**, not the declaration — the layouts the
file actually provides (by the names it gives them), the theme typefaces its font
scheme actually names, the title-placeholder geometry and run size each layout
declares, and the slide size. When the layout leaves title geometry or type size unset,
the reader follows its actual slide-master relationship and measures the matching master
placeholder; an orphan layout is reported rather than silently attached to the first master.
The result includes both the concise layout-name list and full **layout_details**, including
which values were inherited. When no file is named the declarative checks still run exactly
as before; nothing new fires. `template.layouts` remains the declared set used by
`format.undeclared_layout`; a used layout the *measured* template does not contain is the
higher-severity `template.layout_not_found`.

Each slide's `caption` is cross-checked against its `evidence` locator at the
figure-number level, and the build verifies that the declared titles, bullets and
captions actually landed in the written file — a bullet that never lands is what a
missing placeholder without a substitution looks like. Spec top-level keys
`slide_evidence_map`, `pending_confirmation`, `gaps` are copied into result.json by
the contract echo, so the three-part deliverable the task grades carries them filled.

### 2. Run it

```bash
python scripts/deckbuild.py --spec spec.json --out /app/output
```

Exit codes: `0` clean, `3` review, `4` blocked, `5` undetermined (refused case).
Writes `result.json`, `deck.pptx`, and a PDF preview when an office renderer is on
PATH. An unexpected engine error still writes an `undetermined` result.json and exits
5 — the CLI never raises a bare traceback.

### 3. Read the type ladder first

When a deck "looks wrong", check `format.size_ladder_flat` before anything else. Then
`text.overflow` — with the CJK fix, it now fires for Chinese text.

## Runtime entry (per case, six steps)

0. **Read the inputs.** `/input/case.json` first: record `case_id` and the exact
   `output_contract` field list; then `task.md` and the case material. Read the source
   paper, figures and the template file itself — never from labels.
1. **Route.** Match the task wording against the decision table below; one case may
   chain routes (adapt pages, then audit, then export check).
2. **Produce the target artifact first.** Write the deck under `/app/output/` via
   `deckbuild.py` (editable pptx), before any narration about it.
3. **Build the spec** with `case_id`, the `output_contract` array, template 的 file 字段
   pointing at the real template package, and the per-slide claim/evidence/notes.
4. **Audit.** `deckbuild.py` writes, re-reads and audits the file in one run; export
   the PDF/PNG render when a renderer exists and record who rendered what.
5. **Fix findings and rerun** until clean or each remaining finding is declared in
   `limits` (never silently dropped).
6. **Merge result.json**: every `output_contract` field verbatim + `case_id` + engine
   fields (`status`, `findings[]`, `severity_counts`, `deck`, `template_measured`,
   `preview`, `reproducibility`, `checked`, `limits`); undeducible contract fields are
   `null` and named in `limits`.

## Task wording → route decision table

| 任务措辞/案例特征 | 路由 | 依据 |
|-|-|-|
| "按模板/母版生成 PPT"，给了 .potx 或模板 pptx | deckbuild 全流程 + template 的 file 字段 | 模板可实测，走 measured 规则 |
| "只给格式要求（字号/字体/版心），没有模板文件" | deckbuild 全流程，不带 template 的 file 字段 | 声明式规则照常，模板实测静默 |
| "把论文第 X 节整理成汇报页" | slides[].claim/evidence/notes 主线 | 论文主线 + 页级证据映射 |
| "检查这页溢出/字太小/排版乱" | deckaudit 规则直读 written deck | text.overflow / font_too_small |
| "图号和正文引用对不上" | caption ↔ evidence locator 对照 | format.figure_mismatch |
| "导出 PDF 后字体/图片/备注丢了" | export.* + preview 记录 | pptx 与导出件一致性 |
| "批量统一页脚/字号/标题位置" | title_fonts/title_sizes/title_geom 分组 | format.title_drift 一致性 |
| "确认改过的页还在旧模板上" | theme faces + 模板实测对照 | format.font_drift / template.theme_font_mismatch |
| "版式名是套话还是真版式" | match_layout(declared, measured layouts) | template.layout_not_found |
| "两次生成结果不一致" | check_deterministic 两次构建比对 | repro.nondeterministic |
| "交付前自查" | 三条 bench（70 场景）可独立复跑 | Verification 节 |

## Rules

### Template conformance

| rule | severity | what it proves |
|-|-|-|
| `format.size_ladder_flat` | medium | title/body ratio under 1.35 — no hierarchy |
| `format.size_ladder_steep` | low | ratio over 3.0 — the title will wrap |
| `format.undeclared_layout` | high | a layout the spec's declared set does not name |
| `format.template_unnamed` | low | the adaptation is not reproducible |
| `format.font_drift` | medium | a title names a typeface the declared theme does not — a page still on the old template's font |
| `format.title_drift` | medium | slides on one declared layout place or size their titles differently — pages the adaptation never reached |
| `format.figure_mismatch` | high | the caption and the source locator name different figure numbers |
| `format.content_dropped` | high | declared title, bullet or caption text never landed in the written slide, or a declared slide is missing entirely |

### Template, measured (round 2 — need template 的 file 字段)

| rule | severity | what it proves |
|-|-|-|
| `template.layout_not_found` | high | a slide's layout does not exist in the measured template — it will fall back and lose the theme |
| `template.theme_font_mismatch` | medium | a declared face the measured theme never names — a face carried over from another template |
| `template.title_geometry_drift` | medium | a title box not at the position/size the template's title placeholder declares |
| `template.slide_size_mismatch` | medium | the deck's slide size differs from the template's — geometry cannot carry over |
| `template.title_size_off` | low | a title size outside 0.8–1.25× the size the template placeholder declares |
| `template.slide_size_unmeasured` | medium | the package is readable but carries no usable slide size; conformance is unknown |
| `template.theme_unmeasured` | medium | no typeface can be measured through the master/theme relationship |
| `template.title_placeholder_missing` | high | a used layout has no title placeholder and needs a declared fallback |
| `template.title_geometry_unmeasured` | medium | neither the layout title placeholder nor its master supplies geometry |
| `template.layout_master_missing` | high | a used layout's back-link names no existing master, breaking inheritance |
| `template.duplicate_layout_name` | medium | the requested alias resolves ambiguously to multiple measured layouts |
| `template.unreadable` | high | the declared template is not a readable presentation package — nothing could be measured |

### Fonts and glyphs

| rule | severity | what it proves |
|-|-|-|
| `export.missing_glyphs` | high | characters no installed font can draw |
| `export.missing_glyphs_in_declared_font` | medium | the declared face cannot draw some characters |
| `font.declared_missing` | medium | a declared typeface is not installed here |

### Layout and build

| rule | severity | what it proves |
|-|-|-|
| `text.overflow` | high | text does not fit its box, measured on real glyph metrics |
| `text.font_too_small` | high | below the legibility floor |
| `deck.too_many_bullets` | medium | over the declared density limit |
| `deck.no_title` | high | a slide has no title |
| `image.aspect_distorted` | high | a picture was stretched |
| `repro.nondeterministic` | high | two builds differ |

## Output contract

`/app/output/result.json` must carry, in this order of priority:

1. **Platform contract fields, verbatim**: every field named in case.json's
   `output_contract`, copied field-by-field (never renamed, never dropped; fill `null`
   with a note in `limits` when undeducible), plus `case_id` at the top level. The
   contract may arrive as a list of names, a name→description object, or a list of
   objects — all read the same way; an unrecognised shape is refused honestly, never
   crashed on.
2. Engine fields: `status`, `findings[]`, `severity_counts`, `deck` (path, slide count,
   size, spacing, fonts), `template_measured` (layouts, theme fonts, slide size as read
   from the template package), `preview` (whether a render was produced and by what),
   `reproducibility`, `checked` (incl. `font_file` and `glyph_coverage`), `limits`.
   The CLI copies spec-supplied values for contract fields it does not derive — so put
   `slide_evidence_map`, `pending_confirmation`, `gaps` in the spec (top level) and
   they land in result.json filled, not null.
3. The task's three-part deliverable, mapped from engine output:
   - **可编辑演示文件** — the pptx itself (页级结构、主张、图表、讲稿/备注、模板结果),
     path recorded in the `deck` object; `deck.claim_missing` / `deck.notes_missing`
     keep claims and speaker notes auditable per slide.
   - **页级证据映射** — per-slide mapping of content to the paper's figures, tables,
     sections or data: `slide_evidence_map[]` rows `{slide, source, locator}`;
     `deck.evidence_missing` / `deck.evidence_unsupported` / `paper.figure_unattributed`
     enforce 引用准确，未改写事实.
   - **渲染与版本记录** — source file + export + font/template provenance + change
     record: `preview` (render produced and by what), `reproducibility` (repeat builds
     identical), `export.*` findings for 字体替换/图片丢失/备注错位 during export,
     `changes[]` with reasons; 未确认部分写入 `pending_confirmation[]`，材料缺口写入
     `gaps[]`，不静默。

**checked** 的 **font_file** names the font the measurements used — if it is not the declared
typeface, overflow verdicts describe a different font than the reader will see.
**checked** 的 **glyph_coverage** says whether glyph coverage was *measured* or unverifiable —
an unmeasurable deck is a limit, never "all characters missing" (that false positive
used to block healthy decks on machines without a font reader).

## Minimal worked example（示例，非正式案例结果）

Input `examples/spec.json` (2 slides, `case_id: ppt-710fbc72-demo`). Its template file
path names the artifact produced by the next command, not a pre-shipped binary: a .potx
is a binary zip, so the text-only package regenerates it deterministically first:

```bash
python scripts/make_template.py --out examples/template.potx
python scripts/deckbuild.py --spec examples/spec.json --out examples/demo_out
# {"status": "clean", "findings": [], "slides": 2, "preview": false,
#  "wrote": "examples/demo_out/result.json"}   exit 0
```

Ran for real in a clean standard-library-only environment. 示意输出（示例）：
`result.json` carries the ten contract fields above verbatim plus
`template_measured = {"read": true, "layouts": ["Title Slide", "Title and Content"],
"theme_fonts": {"major_latin": "Arial", "major_ea": "Microsoft YaHei", ...},
"slide_size_emu": [12192000, 6858000]}` and
`checked = {"slides": 2, "text_measured": true, "font_file": ".../msyh.ttc",
"glyph_coverage": "measured", ...}`. The sample run's full result.json ships as
`examples/sample-result.json`.

## Rubric mapping

| 评分维度（分值） | 本包证据 |
|-|-|
| 实际效果 40 | 交付可编辑 pptx + 导出记录（deck/preview）；页内文字与主张逐页落点（format.content_dropped 反证）；母版/版式/占位符关系从模板包实测（template_measured + master chain 规则）；逐页偏差 findings 全量留痕 |
| 使用增益 25 | 同输入同模板下规则化重排（尺寸阶梯、密度上限、图号对照）相对裸 Agent 的返工页数可由 findings 计数对照；bench 70 场景可复跑证明判定稳定 |
| 创新增益 15 | 模板实测（template.*，.potx 无第三方库可读且含母版继承）、纯标准库 TTF advance 测量（fontmetrics）、CJK 断行溢出、确定性构建证明 |
| 可靠体验 10 | 退出码 0/3/4/5 全域、异常处置表、-I 隔离环境全 bench 通过、unexpected error 仍写 result.json |
| 生态贡献 10 | 六步运行时入口、路由表、worked example、bench 四件套、示例模板资产、限制清单 |

## Exception handling（异常处置表）

| 症状 | 处置 |
|-|-|
| spec 不是可读 JSON / 不是对象 | `_refused`：写 `audit.no_section` 的 undetermined result.json，退出码 5，不 echo 契约 |
| template 的 file 字段指向损坏/非 OPC 文件 | `template.unreadable` high + **template_measured.read=false**，其余规则照常 |
| 模板任一 XML part malformed | 不把解析失败当成“版式不存在”；整个模板标为不可读，退出 4，无 traceback |
| 布局没有标题几何 | 先沿 layout→master 实测继承；两端都没有才报 `template.title_geometry_unmeasured` |
| 布局缺标题占位符/母版回链 | 分别报 `template.title_placeholder_missing` / `template.layout_master_missing`，显式声明替代方案 |
| 页面尺寸或主题字体测不到 | 分别报 `template.slide_size_unmeasured` / `template.theme_unmeasured`，不声称已通过 |
| 同名布局有歧义 | `template.duplicate_layout_name`；唯一精确 type 匹配是 FP guard，不误报 |
| 模板 layouts 与声明名对不上（别名） | `match_layout` 归一化 + 包含匹配（title↔Title Slide）；确无匹配才 fire |
| 声明字体未安装 | `font.declared_missing`；无 matplotlib 时按 font 目录文件与 name 表判定，不再全员误报 |
| 机器上无任何字体文件可读 | **checked.glyph_coverage=unverifiable** 进 limits，**不**当作"全缺字" |
| Pillow 缺失 | 测量降到纯标准库 TTF advance（measured=true）；图像尺寸从 PNG/JPEG 头读 |
| matplotlib 缺失 | 字体发现走 fontsel 文件查找；覆盖率走 fontmetrics cmap；无 FP |
| 文本框溢出 | `text.overflow` high：改排/换版式，不许压字号 |
| 无 office renderer | **preview.rendered=false** + reason 进 limits，不伪造渲染 |
| 两次构建不一致 | `repro.nondeterministic` high，修到一致再交付 |
| 引擎内部未预期异常 | main 兜底 `_refused`：undetermined result.json，退出码 5，永不 traceback |
| output_contract 形状未知（非 list/dict/str） | 跳过并在 limits 说明，不迭代未知形状 |

## Limits

- **模板实测的范围。** `.potx` 按包结构读取：layouts 名称/类型、主题字体、标题占位符
  几何与字号、页面尺寸、母版归属。只对这个生成流程需要的标题/正文几何与标题字号
  建模 layout→master 继承；不模拟 PowerPoint 的全部主题样式和运行时 autofit。生成器
  写显式文本框，所以缺占位符的净效应仍靠 outcome 规则（`format.content_dropped`）兜底。
- **Fonts are declared, not embedded.** If the target machine lacks the face, the deck
  reflows; the audit reports the risk rather than preventing it. `embed_fonts` 声明会
  校验包内是否真的带了字体（`embed.missing`）。
- **The ladder is a ratio, not a typographic system** — leading, tracking and measure
  length are outside it.
- **Charts are images.** A native chart object cannot be produced, so "chart adaptation"
  means sizing a rendered figure.
- **No footers or page numbers.** The generator writes neither, so batch consistency
  is checked on titles, theme fonts and content presence rather than footer bands.
- **Determinism is compared on slide text and geometry**, not bytes.
- **Advance widths, no kerning.** 标准库测量读 hmtx/cmap，逐字 advance 相加；kerning
  与 ligature 未计入（差异 <2%，对溢出判定保守方向不影响结论）。

## Verification

```bash
python scripts/bench_template.py   # 18 scenarios: template/master measurement, 6 missing-state rules and FP guards
python scripts/bench_deck2.py      # 13 scenarios: template/drift/drop on the written deck, glyphs, determinism
python scripts/bench_deck.py       # 11 scenarios: deck hygiene
python scripts/bench_extra.py      # 28 scenarios: per-skill sections, every defect with FP guards
```

70 scenarios, all passing in a standard-library-only environment (`python -I -X utf8`)
and with the scientific stack present. A missing typeface, a font without glyphs and a
non-reproducible build cannot be expressed in a spec, so those scenarios inject them by
patching. Clean baselines must report zero findings — the guard that stops a detector
passing by flagging everything.

## 创新增益

本包相对通用 Agent 的新增能力（边界与证据形式一并写明）：

1. **模板实测而非声明**：`.potx/.pptx` 模板包用纯标准库 `zipfile+xml` 读取，layouts/
   主题字体/标题占位符几何/页面尺寸全部从文件测出；布局缺少几何或字号时，沿真实
   layout→master 关系读取母版占位符并标记 inherited。`template.*` 十二条实测规则 +
   **template_measured** 的 **layout_details** 回传，评审无需 PowerPoint 就能核"母版、版式、
   占位符继承关系可查"。边界：只继承正文生成需要的标题/正文几何和标题字号，不模拟
   PowerPoint 的全部运行时样式；缺占位符的后果仍靠 outcome 规则兜底。
   证据：bench_template 18 场景（含母版继承、同名歧义 FP guard 与实测回传断言）。
2. **纯标准库字形度量**：`fontmetrics.py` 直接解析 TTF/TTC/OTF 的 cmap/hmtx/head/name
   表——字形覆盖判定与 matplotlib.ft2font 在 5 个系统字体上完全一致，advance 宽度与
   Pillow 相差 <2%；无第三方库的机器上溢出检查与缺字检查真正生效。证据：交叉验证
   脚本输出 + bench_deck2 13 场景（含"不可验证≠全缺字"FP guard）。
3. **CJK 断行测量**：中文按字可断行的包装测量，纯中文段落不再是单个不可断 token——
   溢出检查对中文幻灯片真正生效。
4. **确定性构建证明**：同一 spec 跑两遍逐页比对，产出不同即报 repro.nondeterministic——
   可复现是被测属性而不是承诺。

## 生态贡献

1. **SKILL.md** 含用途、适用条件、六步运行时入口、任务措辞→路由决策表、输入输出、
   异常处置表、限制和自查方法
2. **scripts/** 纯标准库可独立导入（含 fontmetrics/templateread/pnggen 三个无依赖
   模块），规则库可通过 spec 配置扩展
3. **examples/** 最小调用示例 + 实跑示意输出（sample-result.json）+ 可复用的示例
   模板资产 template.potx
4. **bench/** 70 场景回归套件（4 个 bench 文件）可独立复跑验证，clean 基线零发现
5. **规则索引**每条规则 id + severity + 证明内容一行一个，可供其他包复用
6. **参考文档** references/deck-engine.md 记录引擎设计决策与"为什么无依赖"
7. **跨包复用**：deckaudit/deckbuild/extra_rules 的 section 机制已被 p30/p31/p32/p43
   共享，本包规则升级对所有 deck 轨包生效
8. **退出码与 result.json 契约**在包内四个 CLI 间一致，平台 harness 可按统一形状解析

## Requirements

Python 3.9+（3.14 实测）。**零第三方依赖**：全部功能在纯标准库环境（`python -I -X
utf8`）下工作——模板读取（zipfile+xml）、字形度量（struct 解析 TTF/TTC）、PNG 生成
（zlib+struct）。matplotlib / numpy / Pillow / python-pptx 存在时作为加速与交叉校验
使用，不存在时全部优雅降级并如实标注。
