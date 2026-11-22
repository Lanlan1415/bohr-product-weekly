---
name: paper-to-deck
description: >
  Convert a paper into an academic slide deck and prove each slide maps back to the
  source. Each slide declares one claim and the paper object it rests on; a figure
  placed on a slide must name the figure, table or equation it came from, and keep its
  caption. Measures overflow on real glyph metrics with Chinese line breaking, and
  checks that declared typefaces exist, that characters have glyphs, and that two builds
  produce the same deck. Use when a task gives a paper and asks for a talk or slide deck.
---

# paper-to-deck

A paper-to-slide conversion fails in a specific way: every slide is plausible and none
can be checked. A figure ends up attributed to the wrong panel, a caption loses the
conditions that made the result valid, and the deck reads like a summary while asserting
nothing traceable.

This skill makes the mapping explicit and verifies it in the file that gets written.

## Three failures that look like success

**An unattributed figure.** A slide shows a plot and never says `Fig. 3b`. The reader
cannot tell which panel it is, and neither can a reviewer.

**A caption that disappeared.** The caption carries the conditions — dose, n, temperature.
Losing it makes the figure unfalsifiable.

**Chinese text measured with a Latin-only metric.** Two compounding faults, both fixed
here, and both of which silently disabled the overflow check for every Chinese deck:

1. the measuring font was DejaVu Sans, which has **no CJK glyphs**, so the widths were
   wrong;
2. line breaking split on whitespace, and Chinese has none, so an entire Chinese
   paragraph measured as a single line and never overflowed:

```
before: paras=5  need_px≈72   box_h_px=474   (judged to fit)
after:  paras=5  need_px=358  box_h_px=474   (overflow reported)
```

checked.font_file names the font the measurements used — for a Chinese deck that is
not the Latin default.

## Workflow

### 1. Extract the skeleton before writing any slide

| field | meaning |
|-|-|
| `claim` | the one assertion this slide makes — a sentence, not a topic |
| `evidence` | the paper object it rests on: `Fig. 3b, p.7`, `Table 1`, `Eq. 2` |
| `notes` | what you will *say*, which must add what the slide does not show |

A slide with no evidence locator is not ready. A transition slide is the only legitimate
exception, and it should say so.

### 2. Write the spec

```json
{
  "section": "paper_to_deck",
  "spacing": {"title": 32, "body": 20},
  "font_ea": "Microsoft YaHei",
  "font_latin": "Arial",
  "min_font_pt": 14,
  "require_notes": true,
  "available_evidence": ["Fig. 3b, p.7", "Table 1, p.6"],
  "slides": [
    {"title": "多孔涂层加速吸收", "layout": "title", "caption": "42 nm 涂层，速率提高 3 倍",
     "claim": "问题是吸收速率，不是终点", "evidence": "Fig. 3b, p.7",
     "notes": "引入问题；不读标题。"},
    {"title": "吸收速率提高 3 倍", "claim": "涂层使速率提高三倍", "evidence": "Fig. 3b, p.7",
     "image": "figure3b.png", "image_alt": "吸收速率曲线，对照与涂层",
     "caption": "Fig. 3b, p.7 — 对比的是速率",
     "bullets": ["对照组 12.4 a.u.", "涂层组 31.2 a.u.", "每组 n = 6"],
     "notes": "停顿；对比的是速率，不是终点。"}
  ]
}
```

`available_evidence` is the list of paper objects that exist. Every `evidence` value is
checked against it, which catches the classic error of citing a figure number this paper
does not have.

### 3. Run it

```bash
python scripts/deckbuild.py --spec spec.json --out /app/output
```

Exit codes: `0` clean, `3` review, `4` blocked. Writes `result.json`, `deck.pptx`, and a
PDF preview when an office renderer is on PATH.

## Rules

### Paper mapping

| rule | severity | what it proves |
|-|-|-|
| `paper.figure_unattributed` | high | a slide shows a figure but names no paper object |
| `paper.caption_missing` | medium | a figure is placed without its conditions |
| `deck.evidence_missing` | high | the slide carries no source locator |
| `deck.evidence_unsupported` | high | the locator is not in `available_evidence` |
| `deck.claim_missing` | medium | the slide is a topic, not an assertion |
| `deck.notes_repeat_title` | low | the notes only repeat the title |

### Text and fonts

| rule | severity | what it proves |
|-|-|-|
| `text.overflow` | high | text does not fit its box, measured with CJK line breaking |
| `text.font_too_small` | high | below the legibility floor |
| `export.missing_glyphs` | high | characters no installed font can draw |
| `export.missing_glyphs_in_declared_font` | medium | the declared face cannot draw some characters |
| `font.declared_missing` | medium | a declared typeface is not installed here |

### Deck hygiene and build

| rule | severity | what it proves |
|-|-|-|
| `deck.too_many_bullets` | medium | over the declared density limit |
| `deck.no_title` | high | a slide has no title |
| `deck.notes_missing` | medium | no speaker notes |
| `image.aspect_distorted` | high | the picture was stretched |
| `repro.nondeterministic` | high | two builds differ |

## Output contract

`/app/output/result.json`: `status`, `findings[]`, `severity_counts`, `deck`,
`preview`, `reproducibility`, `checked`, `limits`.


|-|-|
| `deck.empty_slide` | high |
| `deck.title_too_long` | medium |
| `edit.change_half_diff` | medium |
| `edit.change_is_noop` | low   |
| `edit.change_not_in_deck` | high |
| `edit.change_slide_out_of_range` | high |
| `edit.change_without_reason` | high  |
| `edit.change_without_slide` | high |
| `edit.delete_without_snapshot` | high |
| `edit.delivered_revision_missing` | medium |
| `edit.revision_without_changes` | medium |
| `embed.missing` | medium |
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
| `format.undeclared_layout` | high  |
| `image.no_alt_text` | low   |
| `master.inconsistent` | high |
| `master.layout_missing` | high |
| `org.audience_missing` | medium |
| `org.claim_is_topic` | medium |
| `org.evidence_strength_missing` | medium |
| `org.goal_missing` | high  |
| `org.pace_too_fast` | medium |
| `org.pace_too_slow` | low |
| `text.body_too_large` | low |
| `text.size_missing` | medium |
| `text.term_inconsistent` | medium |

## Limits

- **The mapping is checked, not judged.** The audit proves a slide names a paper object;
  it cannot prove the object supports the claim.
- **`available_evidence` is only as complete as your extraction.** A correct locator that
  is missing from the list is reported as unsupported — add it, do not delete the check.
- **Notes are checked for presence and for repeating the title**, not for quality.
- **Fonts are declared, not embedded.** If the target machine lacks the face, the deck
  reflows; the audit reports the risk rather than preventing it.
- **No pictograms or native charts.** The generator writes text and one image per slide.
- **Determinism is compared on slide text and geometry**, not bytes.

## Failure handling

| symptom | what to do |
|-|-|
| `paper.figure_unattributed` | name the object in `caption` or `evidence` |
| `paper.caption_missing` | add the caption; conditions belong with the image |
| `deck.evidence_unsupported` | the object number is wrong, or missing from `available_evidence` |
| `text.overflow` | shorten the bullets or split the slide; never shrink below the floor |
| `export.missing_glyphs` | install a font covering those characters — this is 中文变方框 |
| `font.declared_missing` | use an installed face, or ship the font with the deck |
| `repro.nondeterministic` | the build changed between runs; fix before shipping |

## Verification

```bash
python scripts/bench_deck2.py    # 9 scenarios: paper mapping, CJK overflow, fonts, determinism
python scripts/bench_deck.py     # 11 scenarios: deck hygiene
python scripts/bench_extra.py    # 14 scenarios: per-skill sections
```

All pass in full on this machine. A missing typeface, a font without glyphs and a
non-reproducible build cannot be expressed in a spec, so those scenarios inject them by
patching.

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

## Requirements

Python 3.9+（3.14 实测）。matplotlib, numpy, Pillow (PIL)。
