---
name: deck-edit
description: >
  Generate and revise an academic slide deck while keeping a reviewable record of every
  change. Requires each revision to name the slide it touched, the instruction of the
  round and why; keeps the before/after diff complete; snapshots removed text so it can
  be restored; names the delivered revision; and checks each recorded change against the
  written deck. Builds a real .pptx with the standard library (no python-pptx needed),
  keeps terminology consistent across slides, measures text overflow on real glyph
  metrics with Chinese line breaking, checks that declared typefaces exist, that
  characters have glyphs, that every slide still resolves to the one slide master, that
  the deck fits its declared page budget, that declared font embedding is really in the
  package, and that two builds produce the same deck. Writes a structured result.json
  carrying the case's output_contract fields verbatim plus case_id, and refuses with an
  undetermined result (exit code 5) instead of crashing when the input cannot be read.
  Use when a task asks to generate, edit, shorten, expand, re-target, translate, or
  iterate on an academic deck.
---

# deck-edit（学术 PPT 生成与编辑）

迭代是汇报稿悄悄塌掉的地方。一轮"压缩到十分钟"删掉了承载主张的限定词；一轮
"面向评审改写"把同一个实体换了三种叫法；两轮之后没有人说得清改了什么、为什么改，
唯一可行的回应就是推倒重来。本 Skill 让每一次修改都留下可复核的记录，并对着
写出来的文件核验记录本身。

## 五种"看起来成功"的失败

**没有人能复核的修改。** 没有理由的改动无法被复议或撤销；没有页码的改动无法被
定位。

**改写引入的术语漂移。** `signalling` 和 `signaling` 出现在相邻两条要点里，而且
是同一轮引入的。

**无法重建的稿子。** 同一 spec 两次构建产出不同页面，意味着迭代历史描述的是一份
已经不存在的文档。

**用拉丁度量丈量中文。** 两个复合缺陷，都曾让溢出检查对所有中文稿静默失效：

1. 度量字体是 DejaVu Sans，没有 CJK 字形，宽度全错；
2. 断行只按空白切分——中文没有空白——整段中文被当成一行，永远不会溢出：

```
before: shape=Body  paras=5  need_px≈72   box_h_px=474   (judged to fit)
after:  shape=Body  paras=5  need_px=358  box_h_px=474   (overflow reported)
```

度量字体按实际出现的字符解析，每个 CJK 字符都是断行点。checked.font_file 记录
实际用的字体——中文稿里它不该是拉丁默认字体，这个差别就是证据。

**不能重放的记录。** 只留 before/after 单边的 diff 无法逐页比较；删除不留快照
就无法回退——记录存在的意义就是回退。指向不存在页码的改动无法对文件核验。两个
版本并存而没有指针时，没人说得清哪一版交付。母版链同样被核验：某页的 layout
关系丢失、或整个稿子的一半挂在另一个母版上，正是"只想改一页却改坏了全部"的
签名。

## 运行时入口与输出契约（Harbor runtime contract）

平台把本 Skill 安装在 /skills/weekly-skill，运行时输入固定为 /input/case.json 与
/input/task.md；工作目录 /app/work，最终交付物与 result.json 必须写入 /app/output。
实际输入文件和原论文是事实依据；不依据错误的领域标签补造数据。

### 六步运行时入口（harness agent 按此执行）

1. **读 case**：读 /input/case.json，取 case_id 与 output_contract 全部字段；读
   task.md 拿任务措辞与约束（受众、时长、页数上限、模板要求）。
2. **判形态路由**：生成 / 编辑 / 受众改写 / 模板适配，决定 section 与 spec 形态
   （见下表）。论文缺图、图片为位图无法取数等材料边界在此登记 uncertainty。
3. **先产出目标产物**：从论文主线提取页级主张与讲解顺序，先用引擎把 deck.pptx
   （可编辑演示文件本体）构建出来——产物先于审计存在。
4. **构造 spec**：页级结构（title/claim/evidence/bullets/notes/layout）、修改记录
   （revisions + delivered_revision）、模板与字体声明写成 spec JSON（放 /app/work），
   带上 case_id 与 output_contract 原文让引擎直通回填。抽不出的字段留空并登记
   uncertainty，不臆造。
5. **审计并修发现重跑**：跑引擎，按 rule 逐条修发现（页数超限砍页、溢出删要点、
   证据缺位补定位）后重跑，直到 clean 或剩余发现全部属于"材料不支持、只能如实
   声明"。
6. **合并 result.json**：按下述合成规则合成最终 /app/output/result.json，把
   deck.pptx 与真实渲染出的 PDF/PNG 预览一并放入 /app/output；预览渲染器不在时
   在 limits 里如实声明，不谎称渲染过。

### 任务措辞 → 路由决策表

| 任务措辞 / 材料形态 | 路由 | 依据 |
|-|-|-|
| 从论文/提纲生成一版可讲稿 | section 免填（或按内容取舍），主路径 deckbuild.py；每页声明 claim/evidence/notes | 页级证据映射是评分项，主张先行 |
| "改一页"/"压缩第 N 页"/缩短篇幅 | section 为 deck_edit；revisions 记录本轮 instruction + 逐条 change（slide/before/after/reason） | 迭代是本题评分核心；半边 diff 是 medium 发现 |
| 面向评审 / 面向导师改写 | section 为 deck_edit + talk_org；goal 声明 objective/audience/minutes | 受众与时长是主张强度与节奏的裁判依据 |
| "10 分钟" / 页数上限 / "不超过 N 页" | goal.minutes 或 max_slides 进 spec | 页数超限与节奏过快/过慢各有一条规则 |
| 模板适配（母版/字号阶梯/页脚） | section 为 template_fit；template.layouts + spacing + 字体声明 | 未声明 layout 会回落默认并丢主题；字号阶梯必须真是阶梯 |
| 论文图表插入 | slides[].image + image_alt + caption；section 为 paper_to_deck | 图片必须指名论文对象（Fig./Table/Eq.）；无 caption 报 medium |
| 中文内容 / 中英混排 | 主路径（度量字体按字符解析，CJK 逐字断行） | 拉丁度量会漏掉全部中文溢出 |
| 多轮迭代（≥2 轮历史） | revisions 多轮 + delivered_revision 指针 | 没有交付指针的迭代史无法判定哪版交付 |
| 论文缺图 / 图片为位图 | 登记 uncertainty；不凭空生成曲线占位 | 题面点名的失败模式：占位图与凭空曲线 |
| case.json / task.md 缺失或不可解析 | 拒绝路径（见下） | 结构化 result.json，状态 undetermined 或 failed，绝不裸崩 |
| 任务要求 PDF/讲义导出 | 交付 deck.pptx + limits 声明预览能力边界 | 渲染器在 PATH 时产出 PDF 预览，不在时如实说明 |

### result.json 合成规则（顺序即覆盖优先级）

```
result.json =
  1. case.json 中 output_contract 的全部原始字段 —— 逐字段原文保留：
     引擎已产出的字段保持审计值（审计值优先于 spec 携带值），
     spec 携带值的字段逐字直通，
     两边都产不出的字段填 null 并在 limits 里点名 —— 绝不编造
  2. case_id —— 取自 case.json（经 spec 直通或 CLI --case-id）
  3. 主结果 —— deck.pptx（页级结构 + 主张 + 图表 + 讲稿/备注 + 模板结果）
  4. 引擎审计字段 —— status, findings, severity_counts, deck, preview,
     reproducibility, checked
  5. sources —— 页级证据映射：每页 evidence/caption → 论文图、表、章节或数据，
     由 available_evidence 清单背书
  6. uncertainty —— 待复核项：缺图、位图不可取数、槽位不足、默认参数、需人工确认项
  7. change_records —— 逐轮台账：instruction + 每条 change 的 slide/before/after/
     reason，即 spec 的 revisions（审计已核其完整性）
  8. limits —— 能力边界与"未检查项"的如实声明
```

### 题面输出字段对齐（用题面原词）

| 题面要求 | 本包落点 |
|-|-|
| 输入标识 | result.json 顶部 case_id；schema_version 标注引擎版本 |
| 主结果 | deck.pptx + result.json 的 deck 块（页数、页幅、字号阶梯、字体）；完成标准"能围绕论文主线讲清楚"由页级 claim/evidence/notes 审计背书 |
| 页级证据映射 | 每页 evidence/caption → 论文图、表、章节；deck.evidence_missing（high）与 deck.evidence_unsupported（high）把关"引用准确，未改写事实" |
| 渲染与版本记录 | preview（渲染器存在时真实 PDF）+ reproducibility（两遍构建一致）+ change_records（逐轮台账）+ checked.font_file（度量字体记录） |
| 运行状态 | status：clean=完成；review=可交付但带发现；blocked=存在未修复 high；undetermined=输入不可运行（拒绝路径） |
| 不确定性 | uncertainty 列表，逐条可复核 |
| 可编辑演示文件 | deck.pptx 由标准库直写 PresentationML，PowerPoint/WPS/LibreOffice 可打开编辑；母版链审计保证"改一页不改坏全部" |

### 材料缺失时拒绝而不是崩溃

材料缺失、无法判断、运行失败三种情形都必须落一份结构化 result.json 再退出；绝不
裸抛异常，也绝不交一个空白输出目录。引擎层的拒绝路径（spec 不是可读 JSON / 不是
JSON 对象 / 文件缺失 / 页面无法构建）由引擎直接落 result.json：状态 undetermined、
发现规则 audit.no_section（high）、退出码 5。

退出码全表：

| status | exit | 含义 |
|-|-|-|
| clean | 0 | 零发现，直接交付 |
| review | 3 | 带 medium/low 发现，可交付但须逐条处置或声明 |
| blocked | 4 | 存在 high 发现，修复前不得交付 |
| undetermined | 5 | 输入不可运行（坏 JSON / 非对象 / 文件缺失 / 构建失败），什么都没交付 |

拒绝是自包含路径：它运行在任何审计存在之前，只依赖 json 模块，不调用契约回填
（回填所依赖的 spec 恰恰是读不出来的那份输入）；CLI 显式传入的 case 标识仍然保留。

| 情形 | status | 处置 |
|-|-|-|
| spec 不是可读 JSON / 不是 JSON 对象 / 文件缺失 | undetermined（引擎直接落盘） | 退出码 5，永不 traceback |
| spec 能读但构不成页面（slides 类型错位、字段形状错误） | undetermined（引擎直接落盘） | 发现写明原因；不交半成品 |
| 未知 section 名 | undetermined（引擎直接落盘） | 四个合法 section 见路由表；错误名拒绝而不是静默跳过 |
| case.json 或 task.md 缺失/不可解析 | failed | harness 合成 result.json：reason=missing_input，uncertainty 写明缺什么 |
| 论文缺图 / 图片为位图无法取数 | review | 照常成稿；该页登记 uncertainty，不画占位曲线 |
| 模板槽位不足（layout 不在 template.layouts） | review | format.undeclared_layout（high）指出回落页；换声明内 layout 或在 limits 声明 |
| 引擎依赖缺失（Pillow/matplotlib 字体） | 启动失败 | Python 导入层抛 ImportError——依赖在 Dependencies 声明；度量退化为估算并如实报告 |

拒绝模板（**示例**，非正式案例结果）：

```json
{
  "case_id": "（取自 case.json）",
  "status": "failed",
  "reason": "missing_input",
  "sources": [],
  "uncertainty": ["task.md 缺失，页数与受众约束未知；按 15 页默认预算不成立，需补充"],
  "limits": ["拒绝构建：没有任务约束无法判定页级取舍"]
}
```

## 完整 worked example（**示例**，非正式案例结果）

最小输入（examples/spec.json，节选；完整字段以文件为准）：

```json
{
  "case_id": "deck-example-001",
  "output_contract": {"deliverable": "editable deck.pptx", "status": "audit verdict"},
  "deliverable": "editable deck.pptx",
  "section": "deck_edit",
  "max_slides": 5,
  "min_font_pt": 14, "max_bullets_per_slide": 5, "require_notes": true,
  "spacing": {"title": 32, "body": 20},
  "font_ea": "Microsoft YaHei", "font_latin": "Arial",
  "available_evidence": ["Fig. 3b, p.7"],
  "revisions": [
    {"n": 2, "instruction": "压缩到十分钟", "changes": [
      {"slide": 2, "before": "吸收速率明显提高", "after": "吸收速率提高 3 倍",
       "reason": "把模糊的程度词换成实测倍数"}]}
  ],
  "delivered_revision": 2,
  "slides": [
    {"title": "多孔涂层加速吸收", "layout": "title", "claim": "吸收速率是当前工艺的瓶颈",
     "evidence": "Fig. 3b, p.7", "notes": "引入问题；不读标题。"},
    {"title": "吸收速率提高 3 倍", "layout": "content", "claim": "涂层使吸收速率提高三倍",
     "evidence": "Fig. 3b, p.7",
     "bullets": ["对照组 12.4 a.u.", "涂层组 31.2 a.u.", "每组 n = 6"],
     "notes": "停顿；对比的是速率，不是终点。"}
  ]
}
```

调用（本机实跑）：

```bash
python scripts/deckbuild.py --spec examples/spec.json --out examples/out --case-id deck-example-001
```

实跑输出（示意，非正式案例结果）：

```
{"status": "clean", "case_id": "deck-example-001", "findings": [],
 "slides": 2, "preview": false, "wrote": "examples\\out\\result.json"}
```

实跑 result.json 关键字段（示意，非正式案例结果；本机无 office 渲染器，预览如实
声明未渲染）：

```
schema_version   deckbuild/v1
case_id          deck-example-001
status           clean
deliverable      editable deck.pptx                  <- output_contract 字段直通
deck             slides=2, size_emu=[12192000, 6858000],
                 spacing={title:32, body:20},
                 fonts={latin:Arial, ea:Microsoft YaHei}
reproducibility  deterministic=true（两遍构建按页文本与几何比对）
checked          slides=2, text_measured=true（真实字形度量）,
                 font_file=<度量字体路径>, minimum_font_pt=14
limits           ["preview not rendered: no office renderer on PATH (soffice / office-renderer)"]
```

## Workflow

### 1. 修改记录随改随记

记录形状规则，全部是检查项而不是倡议：

- 一条文本修改必须带 **before 与 after 两边**，或——对删除——声明 action 为删除并
  把被删文本放进 before；
- 一条修改的 slide 指向稿子实际包含的页；
- 两轮以上时 delivered_revision 指出交付哪一轮（按 n 标签或列表位置；单轮天然就是
  交付版）；
- 每轮声明 instruction（这轮要做什么），每条 change 声明 reason（为什么这么改）；
- change 的 after 文本必须真的落在所指页面的正文或演讲备注里——审计读的是写出来
  的文件，记录描述了没做过的修改会被点名。

### 2. Run it

```bash
python scripts/deckbuild.py --spec spec.json --out /app/output
```

退出码：0 clean / 3 review / 4 blocked / 5 undetermined。写出 result.json、
deck.pptx，以及 office 渲染器在 PATH 时的 PDF 预览。

**页面本体，不只是记录，是交付物。** 标题陈述该页的主张（"涂层使吸收速率提高
三倍"），不是该页的主题（"结果"）；每页都带主张所依据的来源定位（evidence 缺失
是 high 发现）；演讲备注讲要点之外的话，而不是复读要点；修改记录指明交付版本，
复核者打开的一定是交付的那版。

### 3. Build 先于信任

- reproducibility.deterministic — 两遍构建按页文本与几何比对；
- checked.font_file — 度量实际用的字体（中文稿里不是拉丁默认字体才是对的）；
- findings 里 edit.* — 修改记录的完整性；
- findings 里 master.* — 每页仍解析到同一个母版；
- findings 里 embed.missing — 仅当 spec 声明 embed_fonts 且包里没有字体部件时触发。

## 六类要素检查表（逐项落点）

交付前逐项核对；任何一项缺失都要么补齐、要么在 limits 里写明原因。

| 题面六类要素 | spec/交付落点 | 引擎检查 |
|-|-|
| 论文主线 | 页序 + 每页 claim + goal.objective | deck.claim_missing, org.goal_missing, org.claim_is_topic, org.pace_too_fast, org.pace_too_slow |
| 页结构 | slides[].layout/title/bullets、max_slides、max_bullets_per_slide | deck.no_title, deck.empty_slide, deck.too_many_bullets, deck.slide_count_over_limit, deck.empty_deck, deck.title_too_long |
| 图表引用 | slides[].image/image_alt/caption/evidence + available_evidence | paper.figure_unattributed, paper.caption_missing, deck.evidence_missing, deck.evidence_unsupported, format.figure_mismatch, image.no_alt_text, image.aspect_distorted |
| 讲解逻辑 | slides[].notes、require_notes、org.strength | deck.notes_missing, deck.notes_repeat_title, org.evidence_strength_missing, org.audience_missing |
| 模板约束 | template.layouts/name、spacing、font_ea/font_latin、embed_fonts | format.size_ladder_flat, format.size_ladder_steep, format.undeclared_layout, format.template_unnamed, format.font_drift, format.title_drift, font.declared_missing, embed.missing |
| 导出渲染 | deck.pptx + preview + checked.font_file | text.overflow, text.font_too_small, text.size_missing, text.body_too_large, text.term_inconsistent, export.missing_glyphs, export.missing_glyphs_in_declared_font, master.layout_missing, master.inconsistent, export.invalid_package, export.no_master, export.no_theme, repro.nondeterministic |

## Rules

### 修改记录（演示稿迭代）

| rule | severity | what it proves |
|-|-|-|
| `edit.change_without_reason` | high | 一条改动没有理由，无法复核或撤销 |
| `edit.change_without_slide` | high | 一条改动没有页码，无法定位 |
| `edit.change_slide_out_of_range` | high | 改动指向稿子不存在的页，记录无法映射到文件 |
| `edit.delete_without_snapshot` | high | 删除没有留存被删文本，无法回退 |
| `edit.change_not_in_deck` | high | 记录的新文本没有落在所指页或其备注里 |
| `edit.change_half_diff` | medium | 文本修改只留单边 before/after，无法逐页比较 |
| `edit.delivered_revision_missing` | medium | 两轮以上没有交付指针 |
| `edit.revision_without_changes` | medium | 一轮记录没有任何改动 |
| `edit.revision_instruction_missing` | low | 一轮没有 instruction，本轮意图丢失 |
| `edit.change_is_noop` | low | before 与 after 相同 |

### 文本、术语与字体

| rule | severity | what it proves |
|-|-|-|
| `text.overflow` | high | 文本装不进文本框，按 CJK 断行的真实字形度量 |
| `text.font_too_small` | high | 低于可读下限 |
| `text.term_inconsistent` | medium | 同一术语全稿两种拼法 |
| `export.missing_glyphs` | high | 字符在任何已装字体里都无字形 |
| `export.missing_glyphs_in_declared_font` | medium | 声明的字体本身画不出部分字符 |
| `font.declared_missing` | medium | 声明的字体本机未安装 |
| `embed.missing` | medium | 声明了字体嵌入而包里没有嵌入字体 |

### 稿面卫生与构建

| rule | severity | what it proves |
|-|-|-|
| `deck.empty_deck` | high | 写出的稿子没有任何页面，没有可讲的东西 |
| `deck.slide_count_over_limit` | medium | 页数超过声明预算，收尾会被迫砍页 |
| `deck.no_title` | high | 一页没有标题 |
| `deck.evidence_missing` | high | 一页没有来源定位 |
| `deck.too_many_bullets` | medium | 要点超过声明的密度上限 |
| `deck.notes_missing` | medium | 没有演讲备注，报告变成念稿 |
| `master.layout_missing` | high | 一页没有 layout 或其 layout 解析不到母版 |
| `master.inconsistent` | high | 各页解析到多个母版——改一页改坏了模板 |
| `repro.nondeterministic` | high | 两遍构建不一致 |
| `audit.no_section` | high | 输入不可运行（拒绝路径的发现规则） |

### 完整规则索引（引擎规则已按严格验收全部入档）

| rule | severity |
|-|-|
| `deck.claim_missing` | medium |
| `deck.empty_slide` | high |
| `deck.evidence_unsupported` | high |
| `deck.notes_repeat_title` | low |
| `deck.title_too_long` | medium |
| `export.invalid_package` | high |
| `export.no_master` | high |
| `export.no_theme` | high |
| `format.content_dropped` | high |
| `format.figure_mismatch` | high |
| `format.font_drift` | medium |
| `format.size_ladder_flat` | medium |
| `format.size_ladder_steep` | low |
| `format.template_unnamed` | low |
| `format.title_drift` | medium |
| `format.undeclared_layout` | high |
| `image.aspect_distorted` | high |
| `image.no_alt_text` | low |
| `org.audience_missing` | medium |
| `org.claim_is_topic` | medium |
| `org.evidence_strength_missing` | medium |
| `org.goal_missing` | high |
| `org.pace_too_fast` | medium |
| `org.pace_too_slow` | low |
| `paper.caption_missing` | medium |
| `paper.figure_unattributed` | high |
| `text.body_too_large` | low |
| `text.size_missing` | medium |

## 异常处置表

| 异常 | 识别 | 处置动作 |
|-|-|-|
| 修改没有理由 | edit.change_without_reason | 意图还在记忆里时立刻补写 reason |
| 修改只留单边 diff | edit.change_half_diff | 补齐 before/after 两边；半条记录无法比较或回退 |
| 删除不留快照 | edit.delete_without_snapshot | 把被删文本放进 before，否则内容不可恢复 |
| 记录与文件不符 | edit.change_not_in_deck | 应用该修改或更正记录——两者必居其一 |
| 页码越界 | edit.change_slide_out_of_range | 页码写错或页面没写——修记录或修稿 |
| 迭代无交付指针 | edit.delivered_revision_missing | 在 delivered_revision 里点名交付轮 |
| 轮次无 instruction | edit.revision_instruction_missing | 补写本轮指令；每轮"为什么改"是台账的一部分 |
| 压缩后溢出 | text.overflow | 继续删要点，不要缩字号（缩到下限以下会另报 high） |
| 术语两种拼法 | text.term_inconsistent | 选定一种并全稿重跑；发现清单列出了两种形式 |
| 中文变方框 | export.missing_glyphs | 安装覆盖这些字符的字体——这是题面点名的失败 |
| 声明字体本机没有 | font.declared_missing | 换已装字体，或随稿发布字体 |
| 声明嵌入却没嵌 | embed.missing | 真正把字体打进包里，或撤回 embed_fonts 声明 |
| 页数超预算 | deck.slide_count_over_limit | 按 claim 强度砍页并补一轮 revision 记录，不要临场删 |
| 母版被改坏 | master.layout_missing / master.inconsistent | 重建稿子，不要手补 XML |
| slides/spacing/字体字段类型错位 | 拒绝路径或 limits 说明 | 构不成立面拒绝（undetermined）；可安全回退的数值字段用默认值并在 limits 声明 |
| spec 是坏 JSON / 非对象 / 文件缺失 | audit.no_section | 状态 undetermined、退出码 5、落盘 result.json，永不 traceback |
| 导出预览渲染器不在 | preview.rendered=false | limits 如实声明"预览未渲染"，不谎称产出过 PDF |
| 任务给的是位图无数据 | 抽取阶段 | 登记 uncertainty；不凭空生成曲线占位 |

## 创新增益

本 Skill 的新增能力，全部围绕"迭代可复核"这一题面点名的突破方向：

1. **修改记录即合同**：每轮 revision 带 instruction、每条 change 带
   slide/before/after/reason，多轮必有交付指针；审计读写出来的 .pptx 逐条核对
   记录（新文本必须真的落在所指页或备注里）。通用 Agent 的"我改好了"没有这层
   可复核性。
2. **先建包再审计**：生成器用标准库直写 PresentationML（zipfile + XML），不依赖
   python-pptx；审计再解包读回页面 XML——字体大小丢失、备注占位符丢失、图片
   被拉伸这类"生成器自己的病"是被审计抓出来的，不是靠 spec 自证。
3. **真实度量而非估算**：溢出判定用真实字形宽度（按实际字符解析字体、CJK 逐字
   断行）对真实文本框计算；没有字体文件时退化为估算并在 checked 里如实标注。
4. **母版链守护**：逐页解析 layout→master 关系，"改一页改坏全部"以
   master.layout_missing / master.inconsistent 两条 high 规则落地。
5. **确定性构建**：同一 spec 两遍构建按页文本与几何指纹比对，deterministic=true
   是交付条件；多轮迭代因此可回到任何一版。
6. **页预算约束**：声明 max_slides（或 goal 内）后超页是 medium 发现——页数取舍
   从临场砍页提前到成稿前。

增益边界（创新证据的适用范围）：增益在"可证明"一侧——记录完整性、溢出度量、
母版一致性、构建确定性、页预算。不在"讲得好"：叙事顺序的优劣、翻译质量、
母版样式是否好看，都不是引擎能判断的（见 Limits）。

## 生态贡献

- **使用说明**：本 SKILL.md 即完整使用说明——用途、适用条件、调用方式、输入输出、
  异常处理、限制和自查方法齐全；其他人或 Agent 可按说明独立复跑。
- **依赖**：生成器纯标准库（zipfile + xml），审计可选 matplotlib（字体解析）与
  Pillow（字形测量）；一行 pip 安装（见 Dependencies）；无网络依赖、无作者个人
  文件依赖。
- **配置**：全部行为由 spec JSON 配置（页预算、字号上下限、要点密度、备注开关、
  证据清单、模板 layouts、嵌入声明），按案例调整不需要改引擎代码。
- **示例**：examples/spec.json 是含 case_id 与 output_contract 的最小输入示例（把
  上节 worked example 的命令指向任意可写目录即可实跑复现）；examples/bench-report.json
  是示意输出。
- **资源可复用**：scripts/ 各模块可独立导入——deckaudit.py（解包审计）、
  pptxgen.py（标准库 OOXML 生成）、deckbuild.py（spec→稿→审计→result）、
  fontsel.py（逐字符字体解析）、contract_echo.py（契约回填）；references/deck-engine.md
  记录引擎的设计约束与已知教训，可单独取用。
- **适用范围**：学术汇报稿的生成、压缩、扩写、受众改写、翻译后重建与多轮迭代；
  不适用于动画编排、演讲计时器与在线协作编辑。
- **限制**：见 Limits 一节，逐条写明能力边界。
- **维护信息**：规则集以 rule id 固化，bench 回归套件（4 个 bench 文件、67 个场景）
  即版本门槛；任何规则改动必须同步本文件并重跑 bench。

## Verification

```bash
python scripts/bench_deck.py     # 11/11 scenarios: 稿面卫生，真实写出再读回
python scripts/bench_deck2.py    # 16/16: 修改记录、CJK 度量、字体、母版链、嵌入
python scripts/bench_extra.py    # 27/27: 四个 section，每条缺陷带假阳性守卫
python scripts/bench_edit3.py    # 13/13: 页预算与记录规则、契约回填、拒绝路径
```

四个 bench 在本机全量通过。缺字体、无字形、不可复现构建、母版链断裂、声明嵌入
缺包这类缺陷无法用 spec 表达，对应场景通过 patch 注入或对写出的真实包打补丁——
测的是审计器对真实缺陷的反应，不是 mock。拒绝路径（坏 JSON / 非对象 / 文件缺失
/ 未知 section → 状态 undetermined + 退出码 5 + 落盘 result.json）由 bench_edit3
与外部探针双重覆盖。

## Dependencies

本包对第三方库的依赖刻意最小化：

```
pip install matplotlib numpy Pillow
```

- **（核心，无依赖）** deckbuild.py + pptxgen.py + deckaudit.py + extra_rules.py：
  纯 Python 标准库即可生成与审计完整的 .pptx——评测镜像不提供 python-pptx，
  因此本包不用它，生成器直写 OOXML。
- **matplotlib**：字体查找与逐字符字形覆盖检查（fontsel）。缺失时溢出度量退化为
  估算并在 checked 如实标注。
- **Pillow (PIL)**：字形宽度测量。缺失时同样退化为估算。

If these packages are not available, the deck still builds and the audit still
runs; only glyph measurement degrades to an estimate (reported in checked and
limits). A failed import cannot produce a result.json — install the packages
before running any command documented above.

## Limits

- **台账是结构不是文采。** 审计核验一条修改有页码、有理由、有完整 before/after
  对（或删除快照）、指向存在的页、交付轮有指针。它无法判断理由好不好。
- **记录只验一个方向。** after 文本必须落在所指页或备注里；before 文本是否真的
  在改前存在，流水线没有留底，验不了。结构性修改（无文本对）不做落点核验。
- **术语折叠是短清单。** 连字符与英式/美式词尾。自造同义词对（tumour/neoplasm）
  抓不到。
- **语言切换不验证。** 翻译稿只查几何与一致性，不查翻译质量。
- **嵌入按声明检查。** 只有声明 embed_fonts 为真时才读包内字体部件；不声明时
  该风险作为 limit 报告而不是发现。
- **母版链是结构性的。** 每页必须经 layout 解析到唯一母版；内容相同但无关系
  损伤的页面查不出，母版样式好不好不在范围内。
- **确定性按页文本与几何比对**，不按字节：core properties 合法地随构建变化。
- **叙事质量不在引擎内。** 引擎能证明一页不可溯源，不能证明论证顺序排错了。
