# Fonts and export: the failure that looks like success

## Why this needs its own document

A figure with unreadable labels passes every check that only looks at the file: it
opens, it has the right page size, the shapes are placed, the SVG is valid. The one
thing wrong with it is that the reader cannot read it.

matplotlib's default is **DejaVu Sans, which has no CJK glyphs**. A Chinese label
renders as empty boxes and matplotlib emits only a warning:

```
UserWarning: Glyph 27979 (CJK UNIFIED IDEOGRAPH-6D4B) missing from font(s) DejaVu Sans.
```

That warning goes to a console nobody is reading in an automated run. So the skill
checks coverage itself, before and after drawing.

## Resolution, in order

| preference | family | covers |
|-|-|-|
| 1 | Microsoft YaHei | CJK + Latin + Greek |
| 2 | Noto Sans SC | CJK + Latin + Greek |
| 3 | SimHei | CJK + Latin |
| 4 | Source Han Sans SC | CJK + Latin + Greek |
| 5 | SimSun / DengXian / WenQuanYi | CJK + Latin |
| 6 | DejaVu Sans | Latin + Greek, **no CJK** |

The first candidate that covers **every character the figure will draw** wins. If none
does, the best (fewest missing characters) is used and `font.missing_glyphs` lists
what will print as a box.

Coverage is computed from the labels, title, caption and group names in the spec — the
characters actually used, not "does this look like a Chinese font". A font can cover
`实验装置` and still lack `µ` or `θ`.

## Export requirements

| requirement | check |
|-|-|
| vector, editable | `export.no_live_text` — SVG must contain `<text>`, not outlines |
| no rasterised content | `export.embedded_raster` — an embedded `<image>` will not scale |
| print resolution | `export.low_dpi` — preview below 300 dpi |
| font declared | the SVG carries a `font-family`; the family is echoed in `result.json` |

The live-text rule exists because matplotlib's own `svg.fonttype` default is `path`,
which converts every label to outlines. That produces a perfect-looking, entirely
un-editable figure — and it was found in this engine by its own audit.

## Reproducibility

The third judging criterion is that re-running gives the same figure. Two renders are
compared on:

- the drawn strings, sorted
- the path geometry, sorted
- group transforms, sorted

Timestamps and generated ids are excluded: they differ between runs and say nothing
about the figure. A `repro.nondeterministic` finding means the layout changed, which
for a reader means the reproducibility claim is false.
