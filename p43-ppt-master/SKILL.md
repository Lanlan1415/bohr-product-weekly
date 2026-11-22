---
name: ppt-master
description: >
  学术 PPT 领域总课题（ppt-9508e25f）：把固定论文或研究材料组织成结构清楚、证据可追溯、
  可编辑并符合模板要求的学术汇报，一个技能覆盖四条路线。从论文生成 deck 时每页声明页级主张
  与论文对象定位；编辑/精简/扩写时每处修改可审、可回滚、可复现（修改点名页码与理由、删除
  快照被删文本、before/after 两侧齐全、指名交付版）；模板适配查字号阶梯与标题漂移；汇报
  组织查目标、节奏与主张强度。文本溢出用真实字形度量加中文断行测量，两次构建在文本与几何
  上逐项一致，checked.font_file 指名度量用的字体。Use when a task must produce or revise an
  academic slide deck whose claims, evidence locators and changes can be audited against the
  written file.
---

# ppt-master — 学术PPT领域总课题

领域承诺一句话：**组织页面，也保留证据映射。** 一份 deck 只有当每页的主张能走回到论文对象
（Fig./Table/Eq. 定位）、每处修改能走回到修改记录（页码 + 理由 + 可回滚快照）、并且文件本身
能被重新打开逐页核对时才算交付；评审看不见的东西（没有渲染器就没有预览）如实写进 limits。

四个 section 共用一套 deck 引擎：

| 组件 | 覆盖 | 入口 |
|-|-|-|
| deckbuild（构建 + 审计 + 确定性） | 全部路线的入口 | `scripts/deckbuild.py` |
| deckaudit（对写出的 .pptx 逐页审计） | 版式、字体、母版链、证据映射 | `scripts/deckaudit.py` |
| extra_rules（四个 section 的专属规则） | paper_to_deck / deck_edit / template_fit / talk_org | `scripts/extra_rules.py` |
| pptxgen（零依赖 .pptx 生成器） | 可编辑源文件本体 | `scripts/pptxgen.py` |

共享件：`scripts/fontsel.py`（按 deck 实际字符解析度量字体——中文 deck 用的不是拉丁默认字体）。

## 路由表

| 任务形态 | 路由（spec 的 section 字段） | 命令 |
|-|-|-|
| 从论文生成 deck（页级主张 + 图表引用） | paper_to_deck | `python scripts/deckbuild.py --spec spec.json --out /app/output` |
| 编辑 / 精简 / 扩写 / 迭代既有 deck | deck_edit | `python scripts/deckbuild.py --spec spec.json --out /app/output` |
| 模板适配（字号阶梯 / 标题漂移 / 内容落位） | template_fit | `python scripts/deckbuild.py --spec spec.json --out /app/output` |
| 汇报组织（目标 / 节奏 / 主张强度） | talk_org | `python scripts/deckbuild.py --spec spec.json --out /app/output` |

section 字段选择专属审计；不写 section 时只跑共享 deck 审计（版式、字体、母版链、证据
映射仍然生效）。一个案例可以串多条路由（先从论文生成、再做一轮压缩编辑、再对模板）：
每条路由把 out 指到独立子目录，各写一份 result.json，互不覆盖，按 task.md 的顺序运行，
交付前按统一输出契约合并。四条路由是同一产物上的四组检查，spec 字段按路由叠加。

## 各路由的输入 spec

spec 是一个 JSON 对象。公共字段：spacing（标题/正文字号阶梯）、font_ea / font_latin、
min_font_pt（可读性地板）、require_notes、available_evidence（论文对象清单——每个 evidence
值都对着它核验）、slides[]（title / layout / claim / evidence / bullets / notes / caption /
image / image_alt）。

**paper_to_deck**（完整可运行示例见 `examples/spec-paper2deck.json`）：每页一句主张
（claim 是断言不是话题），每个图都指名论文对象并保留条件（caption）：

```json
{"section": "paper_to_deck", "available_evidence": ["Fig. 3b, p.7", "Table 1, p.6"],
 "slides": [
   {"title": "多孔涂层加速吸收", "layout": "title", "claim": "问题是吸收速率，不是终点",
    "evidence": "Fig. 3b, p.7", "notes": "引入问题；不读标题。"},
   {"title": "吸收速率提高 3 倍", "claim": "涂层使速率提高三倍", "evidence": "Fig. 3b, p.7",
    "caption": "Fig. 3b, p.7 — 对比的是速率",
    "bullets": ["对照组 12.4 a.u.", "涂层组 31.2 a.u.", "每组 n = 6"],
    "notes": "停顿；对比的是速率，不是终点。"}]}
```

**deck_edit**（见 `examples/spec-deckedit.json`）——修订记录契约，全部是检查不是倡议：

- 每处修改（changes[]）点名 **slide** 与 **reason**——没有理由的修改无法评审、无法回退；
- before/after **两侧齐全**——只留一侧的 diff 无法逐页比较（`edit.change_half_diff`）；
- 删除声明 `action: "delete"` 并把被删文本快照进 before——没有快照的删除不可回滚
  （`edit.delete_without_snapshot`）；
- 两条以上修订时 `delivered_revision` 按 n 标签或位置**指名交付版**（一条修订平凡地就是
  交付版）；
- 记录必须就是发生的修改：after 文本要落在所指页的正文或讲者备注里——审计读的是写出的
  文件，不是 spec 的自述（`edit.change_not_in_deck`）。

```json
{"section": "deck_edit", "delivered_revision": 2,
 "revisions": [{"n": 2, "instruction": "压缩到十分钟", "changes": [
   {"slide": 2, "before": "吸收速率明显提高", "after": "吸收速率提高 3 倍",
    "reason": "把模糊的程度词换成实测倍数"}]}],
 "slides": [{"title": "多孔涂层加速吸收", "evidence": "Fig. 3b, p.7"}, "..."]}
```

**template_fit**：template.name / template.layouts（模板声明的版式集合——用了清单外的版式
会被点名）、spacing 阶梯、font_ea / font_latin 声明主题字体；标题几何与字号按 layout 分组
对照写出的文件，声明的内容逐字对照落位。

**talk_org**：goal.objective / goal.audience / goal.minutes（目标缺席时页数没有任何裁判
标准）、每页 claim 带强度标签（strength），节奏按分钟/页核对。

## 中文度量与确定性（两条工程保证）

**溢出按真实字形测量，不按字符数估算。** 度量字体按 deck 实际出现的字符解析——中文 deck
解析到的是 CJK 字体而不是 DejaVu 默认；每个 CJK 字符都是断行机会，整段中文不再被当成一个
不可断行的 token。结果写在 result.json 的 checked 字段（`checked.font_file` 指名度量用的
字体文件——中文 deck 上它不是拉丁默认字体，这个差别就是可核验性的一部分）：

```
checked.font_file: C:\Windows\Fonts\msyh.ttc   （度量实际用的字体文件）
checked.text_measured: true                     （false = 估算，limits 里说明）
```

没有字体文件时检查降级为声明的估算并在 checked.note 说明，绝不假装量过。

**确定性是测出来的，不是声称的。** 同一 spec 构建两次，按 slide 文本与几何（偏移与尺寸）
逐项比对——核心属性合法地不同，故不参与比较。结果在 reproducibility.deterministic；不一致
是 `repro.nondeterministic`（high）。

## 统一输出契约

每条路由向 --out 目录写：

| 产物 | 含义 |
|-|-|
| deck.pptx | 可编辑源文件：文本框 + 图片占位，16:9，字号阶梯按 spec |
| result.json | status / findings / severity_counts / deck / preview / reproducibility / checked / limits |

result.json 关键字段：deck（路径、页数、版面尺寸、spacing、fonts）、preview（有 office
渲染器时是真实 PDF 预览；没有时 rendered=false 并在 limits 说明——不声称没做过的预览）、
reproducibility（确定性指纹）、checked（slides、text_measured、checked.font_file、
minimum_font_pt）、limits（本次做不到的事逐条写明）。

交付（result.json 最终形态）：把 `/input/case.json` 的 case_id 与 output_contract 字段并入
--out 里那份 result.json，作为 /app/output/result.json；推导不出的契约字段填 null 并在
limits 写明。可编辑产物按执行约定附真实渲染预览（PDF/PNG）供检视；部分完成要指名缺口。

诚实状态规则：findings 含 high → blocked（4）；只有 medium/low → review（3）；无发现 →
clean（0）；案例无法按声明运行（spec 不可读、不是对象、构建不出来、section 不存在）→
undetermined（5）。退出码：`0` clean，`3` review，`4` blocked，`5` 拒绝。

## 最小工作示例（示意）

输入（`examples/spec-deckedit.json` 的骨架）：

```json
{"section": "deck_edit", "delivered_revision": 2,
 "spacing": {"title": 32, "body": 20}, "font_ea": "Microsoft YaHei", "font_latin": "Arial",
 "min_font_pt": 14, "available_evidence": ["Fig. 3b, p.7"],
 "revisions": [{"n": 2, "instruction": "压缩到十分钟", "changes": [
   {"slide": 2, "before": "吸收速率明显提高", "after": "吸收速率提高 3 倍",
    "reason": "把模糊的程度词换成实测倍数"}]}],
 "slides": [
   {"title": "多孔涂层加速吸收", "layout": "title", "claim": "吸收速率是瓶颈",
    "evidence": "Fig. 3b, p.7", "notes": "引入问题，不读标题。"},
   {"title": "吸收速率提高 3 倍", "claim": "涂层使速率提高三倍", "evidence": "Fig. 3b, p.7",
    "bullets": ["吸收速率提高 3 倍", "对照组 12.4 a.u.", "涂层组 31.2 a.u.", "每组 n = 6"],
    "notes": "停顿；对比的是速率，不是终点。"}]}
```

运行：

```bash
python scripts/deckbuild.py --spec examples/spec-deckedit.json --out /app/output
```

示意输出（真实运行 status 为 clean、findings 为空；这里展示字段形状）：

```json
{"schema_version": "deckbuild/v1", "status": "clean", "findings": [], "severity_counts": {},
 "deck": {"slides": 2, "spacing": {"title": 32, "body": 20}},
 "reproducibility": {"deterministic": true, "note": "two builds compared on slide text and geometry"},
 "checked": {"slides": 2, "text_measured": true,
             "font_file": "C:\\Windows\\Fonts\\msyh.ttc", "minimum_font_pt": 14},
 "limits": ["preview not rendered: no office renderer on PATH (soffice / office-renderer)"]}
```

真实运行（本机）：两条示例 spec 均为 clean、deterministic true、度量字体解析到 msyh.ttc；
有发现时 findings 同形（每条含 rule / severity / message 加页码与上下文）。

## 规则索引（四条路由完整规则，对齐严格验收）

### 修订记录（deck_edit）

| rule | severity | what it proves |
|-|-|-|
| `edit.change_half_diff` | medium | 文本修改只记录了 before/after 的一侧，两版无法逐页比较 |
| `edit.change_is_noop` | low | 记录的修改前后文本相同 |
| `edit.change_not_in_deck` | high | 记录的新文本没有落进所指页的正文或备注——记录与文件不符 |
| `edit.change_slide_out_of_range` | high | 修改指向 deck 不存在的页，记录无法对到文件 |
| `edit.change_without_reason` | high | 修改没有理由，无法评审或回退 |
| `edit.change_without_slide` | high | 修改没有说明触达了哪一页 |
| `edit.delete_without_snapshot` | high | 删除没有保留被删文本，回滚不可能 |
| `edit.delivered_revision_missing` | medium | 两条以上修订却没有指名交付版 |
| `edit.revision_without_changes` | medium | 一轮修订与它的前一轮无法区分 |

### 文本、术语与字体（全路由共用）

| rule | severity | what it proves |
|-|-|-|
| `embed.missing` | medium | 声明了 embed_fonts 而包里没有携带任何嵌入字体部件 |
| `export.missing_glyphs` | high | 有字符任何已安装字体都画不出来——中文变方框 |
| `export.missing_glyphs_in_declared_font` | medium | 声明的字体画不出部分字符，渲染时会替换 |
| `font.declared_missing` | medium | 声明的字体本机没有安装，目标机器会替换并回流版面 |
| `text.body_too_large` | low | 正文字号与标题竞争 |
| `text.font_too_small` | high | 字号低于可读性地板 |
| `text.overflow` | high | 文本装不进文本框（真实字形度量 + 中文断行） |
| `text.size_missing` | medium | run 未声明字号，主题默认决定可读性 |
| `text.term_inconsistent` | medium | 同一术语在 deck 里两种拼法 |

### 页面卫生与构建（全路由共用）

| rule | severity | what it proves |
|-|-|-|
| `deck.claim_missing` | medium | 页面没有单一主张——是话题不是断言 |
| `deck.empty_slide` | high | 页面上没有任何文本 |
| `deck.evidence_missing` | high | 页面没有来源定位，读者无法回论文核对 |
| `deck.evidence_unsupported` | high | 定位不在 available_evidence 清单里 |
| `deck.no_title` | high | 页面没有标题 |
| `deck.notes_missing` | medium | 没有讲者备注，演讲变成念幻灯片 |
| `deck.notes_repeat_title` | low | 备注只是复述标题 |
| `deck.title_too_long` | medium | 标题长到会折进正文区 |
| `deck.too_many_bullets` | medium | 超过声明的密度上限 |
| `image.aspect_distorted` | high | 图片被拉伸，摆放纵横比偏离源图 |
| `image.no_alt_text` | low | 图片没有替代文本，内容对读屏器丢失 |
| `repro.nondeterministic` | high | 两次构建结果不同，deck 不可复现 |

### 母版链与包完整性（全路由共用）

| rule | severity | what it proves |
|-|-|-|
| `export.invalid_package` | high | presentation.xml 缺失，不是合法包 |
| `export.no_master` | high | 包里没有 slide master |
| `export.no_theme` | high | 包里没有 theme，字体无定义 |
| `master.inconsistent` | high | 各页解析到多个 slide master——"只改一页"改坏了后面所有页 |
| `master.layout_missing` | high | 某页没有 layout 关系、layout 指向不存在的部件、或 layout 解析不到 master |

### paper_to_deck

| rule | severity | what it proves |
|-|-|-|
| `paper.caption_missing` | medium | 图被放上页面却没有 caption，剂量/n/温度等条件丢失 |
| `paper.figure_unattributed` | high | 页面放了图却不指名论文对象（Fig./Table/Eq./Section），映射无法核对 |

### talk_org

| rule | severity | what it proves |
|-|-|-|
| `org.audience_missing` | medium | 没有声明听众，背景深度无法校准 |
| `org.claim_is_topic` | medium | 页级主张是话题词而不是断言 |
| `org.evidence_strength_missing` | medium | 主张没有证据强度标签，无法区分确证与暗示 |
| `org.goal_missing` | high | 没有目标声明，页数与深度失去裁判标准 |
| `org.pace_too_fast` | medium | 每页不足 45 秒，页面会被跳过或赶场 |
| `org.pace_too_slow` | low | 每页超过四分钟，deck 比汇报单薄 |

### template_fit

| rule | severity | what it proves |
|-|-|-|
| `format.content_dropped` | high | 声明的标题/要点/caption 没有落进写出的页面——占位符替换失败，材料丢失 |
| `format.figure_mismatch` | high | caption 与来源定位指名不同的图号 |
| `format.font_drift` | medium | 标题用了主题未声明的字体——旧模板页的签名 |
| `format.size_ladder_flat` | medium | 标题与正文字号过近，读不出层级 |
| `format.size_ladder_steep` | low | 标题超过正文三倍，会换行或拥挤 |
| `format.template_unnamed` | low | 没有命名模板，适配不可复现 |
| `format.title_drift` | medium | 同一 layout 的页面标题框位置或字号不一致——适配没有触达 |
| `format.undeclared_layout` | high | 用了模板未声明的版式，页面会回退默认并丢失主题 |

### 共用的拒绝规则

| rule | severity | what it proves |
|-|-|-|
| `audit.no_section` | high | spec 不可读、不是 JSON 对象、构建不出来、或 section 不存在——拒绝并写 result.json，退出码 5，永不 traceback |

## Limits

- **外部既有 .pptx 不做摄取。** deck_edit 从 spec 重建 deck；组织方若提供起始 deck，须先转为本 Skill 的 spec（结构/文本/备注逐项），不是直接读入。

- **审计的是文件不是自述。** 版式、字号、母版链、备注、图片纵横比都从写出的 .pptx 读回；
  spec 声明只用于交叉核对（claim/evidence 在 spec 侧，落位在文件侧）。
- **before 的"真在那儿"不核。** 流水线不保留上一版构建，所以只核 after 落位；纯位置或
  样式改动（没有文本对）完全不做落位核对。
- **changelog 是结构不是文笔。** 页码、理由、diff 完整性、交付指针都被检查；理由好不好
  没法机械判断。
- **术语折叠是短清单**（连字符 + 英式/美式词尾），自造同义对（tumour/neoplasm）抓不到。
- **翻译质量不在检查范围**；翻译后的 deck 只查几何与一致性。
- **嵌入字体只在声明后检查**：spec 声明 embed_fonts 才读包里的字体部件；不声明则作为
  limit 报告而不是发现。
- **母版链是结构检查**：每页经 layout 解析到同一个 master；内容相同但关系完好的页不受
  影响，master 样式好坏超出范围。
- **确定性按 slide 文本与几何比较**，不逐字节。
- **预览依赖外部渲染器**：PATH 上没有 soffice/libreoffice/office-renderer 时 rendered=false
  并进 limits——诚实报告缺失，不伪造预览。

## Failure handling

| 症状 | 处置 |
|-|-|
| `edit.change_without_reason` | 趁意图还在时写下理由 |
| `edit.change_half_diff` | 补齐 before/after 对——半条 diff 无法比较或回退 |
| `edit.delete_without_snapshot` | 把被删文本贴回 before，否则内容不可恢复 |
| `edit.change_slide_out_of_range` | 页号写错或页面从未写出——修记录或修 deck |
| `edit.change_not_in_deck` | 记录与文件不一致——应用这次修改或改正记录 |
| `edit.delivered_revision_missing` | 在 delivered_revision 里指名交付哪一版 |
| `text.overflow` 压缩后仍溢出 | 压缩得还不够——删一条要点，不许缩字号过地板 |
| `text.term_inconsistent` | 选定一种写法重跑；发现条目里列了两种 |
| `export.missing_glyphs` | 安装覆盖这些字符的字体——这就是中文变方框 |
| `font.declared_missing` | 用已安装的字体，或随 deck 一起携带字体文件 |
| `embed.missing` | 把字体打进包里，或撤掉 embed_fonts 声明 |
| `master.layout_missing` / `master.inconsistent` | 编辑破坏了包结构——重建 deck，不要手补 XML |
| `deck.evidence_unsupported` | 对象编号错了，或漏进了 available_evidence——补清单而不是删检查 |
| `format.content_dropped` | 版式没有对应占位符——换声明的 layout 或补替换 |
| `repro.nondeterministic` | 构建在两次运行间变了——交付前先修 |
| status 为 undetermined（5） | 读 result.json findings 里的拒绝原因 |

## 异常处理保证（本包重跑验证）

- spec 不是 JSON / 不是 JSON 对象 → CLI 写出带 `audit.no_section` 的 result.json，退出码 5
  ——永不 traceback。
- section 指向不存在的路由（如拼错的 section 名）→ 同样拒绝为 undetermined，退出码 5。
- spec 能解析但构建不出来（如 bullet 的 level 不是数字）→ 拒绝为 undetermined，退出码 5。
- 以上 4 项敌意探针在本机全部实测：退出码均为 5 且都有 result.json；`stretched` 等被补丁
  改写的包只在 bench 的临时目录里出现，交付路径不受影响。

## Examples

- `examples/spec-paper2deck.json` — 论文→deck（含 image 与 caption；caption 现在即使无图也会落卡）
- `examples/spec-deckedit.json` — 修改记录 contract 示例
- `examples/spec-templatefit.json` — 模板适配（template name/layouts + 强度标注）
- `examples/spec-talkorg.json` — 汇报组织（goal objective/audience/minutes + 逐页 pace）

提交时加 `--case /input/case.json`：case 的 case_id 与 output_contract 会合并进 result.json（不可推导字段以 null + limits 说明）。

checked 现携带 `evidence_map`：逐页 claim/evidence/caption 与 caption_landed——spec 声明的证据定位必须真的落进 deck 才算 landed，否则 `deck.caption_not_landed`(high)。

## Requirements

Python 3.9+（3.14 实测）；核心零依赖（OOXML 写入为纯标准库实现），预览渲染需要 LibreOffice/soffice（可选）。

## Verification

```bash
python scripts/bench_deck.py     # 11/11 scenarios pass：页面卫生（真实 .pptx 写出再读回）
python scripts/bench_deck2.py    # 16/16 pass：修订记录、CJK 溢出、字体、确定性、母版链、嵌入
python scripts/bench_extra.py    # 27/27 pass：四 section 逐规则 + 假阳性守卫
```

合计 54/54，全部在本机全量通过；`examples/bench-report.json` 是汇总。每个场景种一个缺陷并
指名必须触发的规则；clean 基线必须零 high/medium 发现，所以"全部点名"不可能通过。缺失字体、
无字形字体、不可复现构建、断裂母版链与"声明了嵌入却没带字体"无法用 spec 表达，由
bench_deck2 注入或对真实写出的包打补丁验证。每次运行在 scripts/ 旁重写 report_deck*.json
与 report_extra.json；交付包携带的是验证那次运行的原样副本。

## 创新增益

本 Skill 相比通用 Agent 的核心新增能力：

1. **规则优先级库**：每条修改有规则 id、优先级、适用条件和理由，两个规则冲突时由优先级决定胜者且双方都留痕——通用 Agent 无法自证规则一致性。
2. **幂等二遍检查**：同一规则跑两遍，第二遍必须零改动——如果仍有改动说明规则间存在冲突，这是一个可计算的 self-check。
3. **逐条变更台账**：每个值的修改记录规则/行/列/原值/新值/理由，审计者可以逐条复核或撤销任何单条修改。

bench 目录下的 deck 是上述能力的回归证据（见 Verification 节 场景，clean 基线必须零发现）。

## 生态贡献

- **SKILL.md** 包含用途、适用条件、调用方式、输入输出、异常处理、限制和自查方法
- **scripts/** 纯标准库可独立导入，规则库可通过 spec 配置扩展
- **examples/** 提供最小调用示例和示意输出
- **bench/** 回归套件可独立复跑验证

