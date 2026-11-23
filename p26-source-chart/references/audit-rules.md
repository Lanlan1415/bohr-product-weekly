# Audit rules: what each one proves

## Encoding and structure

**`encoding.required_channel_unmapped`**, **`encoding.column_missing`**,
**`encoding.not_numeric`**, **`encoding.unknown_chart_kind`**, **`data.no_rows`** —
all five are refusals raised before anything is drawn. They exist so the failure
mode is an error message rather than a chart of zeros or a crash.

**`encoding.time_as_bars`** — the x column is time-like (a date/time column name,
or four-plus integer values in year range) but is drawn as disconnected bars.
Ordering survives as a label, continuity does not: the between-point trend a
reader assumes from a time axis is invisible. Line or scatter preserves it.

**`series.missing_from_chart`** — a group present in the data never reached the
canvas. This is the data-chart equivalent of dropping a treatment arm.

**`legend.absent`** — several groups are drawn in different colours with nothing
saying which is which. Colour without a legend is decoration, not encoding.

## Axes

**`axis.x_label_missing` / `axis.y_label_missing`** — an unlabelled axis makes the
panel unreadable once it is separated from its caption.

**`axis.x_unit_missing` / `axis.y_unit_missing`** — raised only for a **numeric**
axis. A categorical axis ("control", "drug") has no unit, and demanding one
produces a finding nobody can act on. This rule was narrowed during development
for exactly that reason: the first version fired on every categorical bar chart.

**`axis.value_clipped`** — a data value sits outside the drawn limits, so its mark
is invisible while the chart still looks complete. Bar charts are compared against
a lower bound of zero, because that is what a reader assumes a bar length means.

**`axis.truncated_baseline`** — the spec declares a y-axis that starts above zero
on a bar chart. Bar length is read as value; a baseline above zero keeps only the
tip of each bar and exaggerates the differences between them. The engine applies
the declared limit before auditing, so what is reported is what the reader sees.

**`axis.log_nonpositive`** — the declared y scale is logarithmic while the data
contain zero or negative values. A log axis cannot place them; they drop out
silently unless the audit names the count.

## Errors and statistics

**`error.column_not_drawn`** — an error channel is mapped but no bars appeared,
usually because the column is blank or the wrong column was named. Drawing a mean
without its spread is a claim in itself.

**`annotation.errorbar_meaning_missing`** — an error channel is drawn but the spec
never says whether the bars are SD, SEM or a confidence interval. The three answer
different questions; a caption cannot retro-declare what the spec omitted.

**`annotation.unknown_comparison`** — a significance bracket compares two groups
and one of them is not in the data. This catches a bracket copied from a template.

**`caption.n_mismatch`** — the caption's sample size disagrees with the source.
When the table has an explicit `n` column, that column is authoritative and the
row count is not, because one row may aggregate several observations; the finding
carries `distinct_n` and `n_total` so the reviewer can judge which reading the
caption meant. A non-numeric caption_n is reported here too: it cannot name a
sample size at all.

## Readability

**`read.too_many_categories`** — more than twelve categories on one categorical
axis, or more than eight series on one palette. Past those limits the panel stops
being readable at single-column width and colours repeat, so the legend can no
longer disambiguate the series. The fix is a split panel or grouped classes,
declared before export rather than discovered by a reviewer.

## Traceability

**`traceability.missing`** — marks exist without a source row index. The
`mark_to_row` mapping is the deliverable that makes a figure reviewable; marks
outside it cannot be audited at all.

**`traceability.row_coverage`** — fewer marks than source rows. Usually rows were
filtered out by an undeclared step; the fix is to declare the filter, not to
silently accept the shortfall.

## Colour range (heatmap)

**`color.range_undeclared`** — a heatmap ships without a declared colour scale
range, so a reader cannot tell whether the palette spans the data or quietly
truncates it.

**`color.range_clipped`** — a declared colour range does not cover the data: cells
beyond the range are pinned to the palette ends and their magnitude is misread.

## Layout

**`layout.panel_missing`** — no panel letter is declared. Low severity on purpose:
a lone figure may legitimately have none, but a composite cannot place this export
without one, and the result records nothing.

## Export and fonts

**`export.no_live_text`** — the SVG carries no `<text>` elements: every label was
converted to outlines, so the file cannot be edited downstream.

**`export.pdf_invalid`** — the "PDF" is not a PDF; whatever was written cannot be
submitted.

**`export.low_dpi`** — the raster preview is below 300 dpi, below common journal
requirements.

**`font.unresolved`** — no readable font file was found on the machine, so glyph
coverage could not be proven. Reported as a review finding, never assumed away.

**`font.glyph_missing`** — a drawn label contains characters with no glyph in the
resolved font (the classic cause of Chinese-as-empty-boxes). The finding names the
font and the exact missing characters, so the fix is to switch fonts or drop the
characters — knowingly, not after a reviewer finds the boxes.

**`input.label_truncated`** — a spec string field exceeded the presentation length
limit (240 characters) and was clipped before rendering, because a megabyte-long
label stalls the renderer for minutes. The clipped fields are named; the drawn
labels are no longer the submitted text verbatim until the spec is fixed.

## Unrunnable input (status undetermined)

**`input.spec_unreadable`** — the spec file is not readable JSON. The run answers
with a result.json and exit 5, never a traceback.

**`input.spec_not_object`** — the spec parses but is not a JSON object (a bare
list or string), so no encoding can be planned from it.

**`input.data_unreadable`** — the data file cannot be parsed as CSV or JSON
(missing file, decode error, malformed JSON).

**`render.failed`** — the spec and data are readable but the rendering itself
raised (a geometry matplotlib rejects, for example). The failure is reported with
its exception name; nothing partial is passed off as a figure.

## Version 3 additions

**`encoding.incomplete_interval`** — absolute errorband endpoints or two sides of
an asymmetric interval are incomplete. **`error.invalid_value`** names negative
error magnitudes; **`error.invalid_interval`** catches lower/centre/upper order
violations row by row. **`encoding.unsupported_channel`** and
**`encoding.unsupported_channel_for_kind`** prevent a meaningful channel from
being silently ignored.

**`layout.caption_outside_canvas`** measures the rendered caption's pixel bounds
against the actual canvas. Caption wrapping uses physical figure width so small
journal panels do not silently cut off the units, n or uncertainty declaration.

**`encoding.dual_axis_unsupported`** prevents a second quantitative axis;
**`data.duplicate_marks`** prevents overplotted duplicate bar/cell keys;
**`data.missing_numeric`** names missing required values without converting them
to zero. **`export.empty_artifact`**, **`export.svg_invalid`** and
**`export.png_invalid`** validate actual files; **`export.svg_invalid`** is based
on XML parsing rather than a suffix. **`export.accessibility_description_missing`**
checks the real SVG title/description.

**`input.request_invalid`** is the structured CLI preparation refusal. It also
covers invalid source-edit patches and a base SVG without live text. Edit patches
that try to replace source data are refused before rendering.
