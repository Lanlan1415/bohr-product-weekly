# Audit rules: what each one proves

## Encoding and structure

**`encoding.required_channel_unmapped`**, **`encoding.column_missing`**,
**`encoding.not_numeric`**, **`encoding.unknown_chart_kind`** — all four are
refusals raised before anything is drawn. They exist so the failure mode is an
error message rather than a chart of zeros.

**`series.missing_from_chart`** — a group present in the data never reached the
canvas. This is the data-chart equivalent of dropping a treatment arm.

**`legend.absent`** — several groups are drawn in different colours with nothing
saying which is which. Colour without a legend is decoration, not encoding.

## Axes

**`axis.*_label_missing`** — an unlabelled axis makes the panel unreadable once
it is separated from its caption.

**`axis.*_unit_missing`** — raised only for a **numeric** axis. A categorical axis
("control", "drug") has no unit, and demanding one produces a finding nobody can
act on. This rule was narrowed during development for exactly that reason: the
first version fired on every categorical bar chart.

**`axis.value_clipped`** — a data value sits outside the drawn limits, so its mark
is invisible while the chart still looks complete. Bar charts are compared against
a lower bound of zero, because that is what a reader assumes a bar length means.

## Errors and statistics

**`error.column_not_drawn`** — an error channel is mapped but no bars appeared,
usually because the column is blank or the wrong column was named. Drawing a mean
without its spread is a claim in itself.

**`annotation.unknown_comparison`** — a significance bracket compares two groups
and one of them is not in the data. This catches a bracket copied from a template.

**`caption.n_mismatch`** — the caption's sample size disagrees with the source.
When the table has an explicit `n` column, that column is authoritative and the
finding reports `distinct_n` and `n_total`, because "n = 6" usually means per
group, not six rows in total. The first version of this rule compared against row
count and produced false mismatches on any aggregated table.

## Traceability

**`traceability.missing`** — marks exist with no source row index. Without the
index the figure cannot be audited later, so this is a high-severity finding even
though the picture looks fine.

**`traceability.row_coverage`** — fewer marks than rows. Usually blank values
filtered out silently; the finding forces that to be stated.

## Export

**`export.no_live_text`** — the SVG has no `<text>`, so labels are outlines.
matplotlib's default `svg.fonttype` is `path`, which makes a perfectly good-looking
file that cannot be edited. This rule caught that default in this engine's own
renderer.

**`export.pdf_invalid`**, **`export.low_dpi`** — the export is not what a journal
will accept.

## Values, labels and export (round-2 rules)

**encoding.drawn_value_mismatch** — the audit reads the values back out of the
matplotlib artists (bar heights from the patches, scatter values from the
collection offsets) and reconciles them against the mark-to-row mapping. A
phantom bar (a missing cell drawn as a zero bar) or a dropped value is a
finding even though the picture looks complete. Bar and scatter reconcile
artist-to-source; line and heatmap reconcile through the mark rows only, because
their artists mix with error-bar objects.

**legend.series_mismatch** — legend entries must name exactly the series that
were drawn; an entry for a series that never reached the canvas makes colour
map to the wrong name.

**error.meaning_undeclared** — error bars drawn without a declared meaning
(SD/SEM/CI/range) are unreadable in review.

**label.cjk_font_missing** — labels containing CJK characters render as hollow
boxes unless a CJK-capable font is installed. The rule fires only when a label
actually contains CJK, so English charts are never flagged. On a machine with
Microsoft YaHei or a Noto CJK font installed the rule stays silent by design.

**export.png_dpi_mismatch** — reads the resolution back out of the PNG's pHYs
chunk, so the delivered artefact itself is measured rather than the parameter
being trusted.

**export.width_out_of_band** — when the delivery declares a target column
width (export.width_mm), the drawn width must be inside tolerance.

**caption.n_unparseable** — a caption sample size that is not a number cannot
be measured; the audit reports the shape instead of crashing.

**spec.unreadable / spec.not_object / data.unreadable / deps.unavailable /
render.failed / encoding.bad_shape** — every unrunnable case is a refusal with
exit 5, a written result.json and no traceback.

## What the audit cannot do

- It cannot tell you the statistics are right, only that the numbers are the
  source's numbers.
- It cannot judge whether the chart type suits the question — a bar chart of a
  continuous predictor passes every rule here and is still wrong.
- It cannot detect a truncated colour scale or a misleading axis break unless the
  break pushes a value outside the limits.
