# Encoding spec and how channels are validated

## Why channels map to column *names*

A spec that says `"y": [12.4, 31.2, 10.1, 14.8]` has already thrown away the link
to the source. A spec that says `"y": "response"` keeps it: the value at any mark
can be found again in the table, and a reviewer can check the mapping instead of
trusting it.

This indirection is the whole reason traceability is possible. Values live in the
data file and nowhere else.

## Validation order

1. **Chart kind** — must be one of `bar`, `line`, `scatter`, `box`, `heatmap`.
   An unknown kind is refused, never mapped to "the closest thing".
2. **Required channels** — each kind declares what it cannot be drawn without
   (`heatmap` additionally needs `value`). A missing channel is a refusal.
3. **Empty table** — a header-only table is refused with `data.no_rows`, never
   rendered as an empty panel and never crashed on.
4. **Column existence** — every mapped column must be a real column. The finding
   lists the available columns so the fix is a one-line edit.
5. **Type fit** — which channels must be numeric depends on the kind:
   `value`, `y_err` and `x_err` always; `y` for every kind except heatmap (its y
   is a grid coordinate); `x` only for line and scatter, whose x sits on a
   continuous scale. "Fully" means every non-blank cell parses; a column that is
   90% numeric is not numeric, because the remaining 10% would silently become
   gaps or zeros.
6. **Unreadable inputs** — a spec that is not JSON, not an object, or a data file
   that cannot be parsed produces status "undetermined" (exit 5) with a named
   finding, never a traceback.

## What refusal looks like

```json
{
  "status": "refused",
  "findings": [
    {"rule": "encoding.not_numeric", "severity": "high", "channel": "y",
     "column": "response",
     "message": "'response' is not fully numeric, so it cannot drive a numeric channel"}
  ],
  "note": "the spec was refused rather than approximated"
}
```

Refusing costs one round trip. Approximating costs a wrong figure that looks
finished, which is worse in every case that matters.

## Chart-kind notes

- **bar** — a non-numeric `x` becomes the category axis, and the category strings
  are recorded per mark, so a bar can be traced by label as well as by row. A
  *numeric* x that is time-like (year-like values, or a date/time column name) is
  reported as a kind mismatch: draw a line or scatter instead.
- **box** — one box per `group` value. Individual rows are still recorded in
  `mark_to_row`, so the distribution is traceable to the observations.
- **heatmap** — `x` and `y` define the grid, `value` fills cells; both
  coordinates may be categorical. Cells present in the grid but absent from the
  data render as `NaN` (visible gaps), not zero. The colour range matters: an
  undeclared range is reported, and a declared range that clips data values is a
  high finding.
- **line / scatter** — `y_err` draws error bars; a non-numeric `x` falls back to
  row order and the fallback is recorded in the mark, not hidden.
- **missing values** — a blank y cell draws nothing (NaN), never a silent
  zero-height bar; the mark row keeps the honest `null`.

## Axis and annotation options the audit reads back

| spec field | effect | audit rule it feeds |
|-|-|-|
| `ylim` | applied to the drawn axis | `axis.truncated_baseline` (bar baseline above zero), `axis.value_clipped` |
| `y_scale` | log / symlog / logit | `axis.log_nonpositive` when data contain non-positive values |
| `color_range` | heatmap palette floor/ceiling | `color.range_undeclared`, `color.range_clipped` |
| `errorbar_meaning` | SD / SEM / CI declared with the error channel | `annotation.errorbar_meaning_missing` |
| `panel` | panel letter recorded for composites | `layout.panel_missing` (low) |

## Unreadable and hostile input

The CLI never answers a bad input with a traceback. Four statuses cover every
case, each with its own exit code:

| status | when | exit |
|-|-|-|
| `clean` | audit found nothing to report | 0 |
| `review` | only low/medium findings | 3 |
| `blocked` | any high finding on a rendered figure | 4 |
| `refused` | the encoding plan was rejected before rendering | 5 |
| `undetermined` | spec/data unreadable, not an object, or rendering itself failed | 5 |

`refused` and the rendered statuses carry the case contract (case_id plus every
output_contract field, null-filled with a note in limits where the engine cannot
derive one). `undetermined` does not echo the contract: the spec may be
unreadable, so there is nothing trustworthy to echo.

## Export defaults

| artifact | how it is written | why |
|-|-|-|
| `figure.svg` | live text (`svg.fonttype=none`) | labels stay editable in Illustrator/Inkscape |
| `figure.png` | 300 dpi raster | reviewer preview and print |
| `figure.pdf` | vector | submission-ready scalable copy |

The font is resolved against the characters the figure actually draws (spec label
fields plus category values from the data), preferring a CJK-capable face when the
labels are Chinese. Coverage is proven per character; a character no candidate font
covers is named in the audit instead of silently becoming a box.
