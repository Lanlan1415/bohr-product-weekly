# Audit rules: what is actually checked

## Pre-render refusals

- `encoding.unknown_chart_kind`: kind is outside bar/line/scatter/box/heatmap/histogram.
- `encoding.required_channel_unmapped`, `encoding.column_missing`, `encoding.not_numeric`: the
  declared mapping cannot be executed without inventing positions or values.
- `encoding.unsupported_channel`, `encoding.unsupported_channel_for_kind`: a channel would otherwise
  be silently ignored.
- `encoding.dual_axis_unsupported`: a second quantitative y scale is declared. Facet or normalise
  explicitly instead of making magnitudes look directly comparable.
- `input.encoding_not_object`: encoding is not a channel-to-column map.
- `data.no_rows`: a header-only or empty table cannot support a chart.
- `data.duplicate_marks`: repeated x(/y)/group keys in bar/heatmap would overplot one another.

A refusal carries case_id plus all readable output_contract fields and exits 5.

## Source and chart consistency

- `data.missing_numeric` (medium): required numeric cells are absent. They remain undrawn, never zero.
  Optional blank uncertainty cells are allowed and draw no error segment.
- `data.duplicate_rows` (low): identical input rows are preserved and counted, not silently removed.
- `data.small_sample` (low): fewer than three source rows limits distribution/uncertainty reading.
- `traceability.missing` (high): a visual record lacks its source row index.
- `traceability.row_coverage` (medium): fewer mark records than source rows.
- `encoding.drawn_value_mismatch` (high): the actual rendered centre/value differs from the mapped
  source, or a non-missing value has no expected geometry. This includes the previously overlapping
  grouped-bar failure; checking only the spec cannot catch it.

## Axes, encodings and annotation

- `axis.x_label_missing`, `axis.y_label_missing` (high): no axis label or fallback field name.
- `axis.x_unit_missing`, `axis.y_unit_missing` (medium): numeric axes have no declared unit; category
  axes are intentionally exempt.
- `color.unit_missing` (medium): numeric heatmap colour scale has no unit.
- `axis.value_clipped` (high): source values fall outside actual x/y limits. Bar auditing retains the
  zero-length baseline semantics.
- `axis.truncated_baseline` (high): declared bar baseline starts above zero.
- `axis.log_nonpositive` (medium): log/symlog/logit is requested over non-positive values.
- `encoding.time_as_bars` (medium): a time-like x field is shown as disconnected bars.
- `annotation.title_missing` (medium): no title is rendered.
- `annotation.errorbar_meaning_missing` (medium): x_err/y_err is mapped without SD/SEM/CI/range text.
- `error.column_not_drawn` (high): every declared uncertainty value is missing, so no bars appeared.
- `annotation.unknown_comparison` (high): a significance declaration names absent groups. The package
  does not render significance brackets and reports that limitation explicitly.
- `caption.n_mismatch` (high): caption_n is non-numeric or unsupported by rows/the declared n column.
  Without caption_n, the rendered caption says source rows rather than inferring independent n.

## Series and readability

- `series.missing_from_chart` (high): a source group did not reach the rendering groups.
- `legend.absent`, `legend.series_mismatch` (medium): legend and actual series disagree.
- `read.too_many_categories` (medium): >12 categorical x values or >8 series. Okabe-Ito is always
  backed by hatch/dash/marker plus text, so colour is not the only series channel.
- `layout.panel_missing` (low): no panel identifier is declared for possible composite use.
- `layout.text_overflow` (high): renderer bounding boxes show title, axis label, or caption outside
  the canvas. Caption wrapping is retried before this finding is evaluated.

## Exports and accessibility

- `export.empty_artifact` (high): SVG/PNG/PDF is absent or implausibly small.
- `export.no_live_text` (high): SVG labels are outlines rather than editable text.
- `export.accessibility_description_missing` (medium): SVG title/description was not embedded.
- `export.pdf_invalid` (high): output lacks a PDF signature.
- `export.low_dpi` (medium): requested raster dpi is below 300.
- `export.png_dpi_mismatch` (medium): the actual PNG pHYs chunk is below 300 dpi.
- `export.width_out_of_band` (medium): actual canvas misses the declared width/tolerance.
- `export.width_invalid` (medium): declared width cannot be measured.
- `font.unresolved`, `font.glyph_missing` (medium): no provable font, or a drawn character lacks a
  glyph. Font coverage includes title/caption/labels/units and category/legend text.

## Unrunnable input and render failures

- `input.spec_unreadable`, `input.spec_not_object`: malformed JSON or non-object spec.
- `input.data_unreadable`: missing/unreadable table, malformed JSON rows, duplicate CSV headers, or
  row/header shape mismatch.
- `input.request_invalid`: CLI auto/case preparation failed.
- `input.label_truncated` (medium): presentation text exceeded 240 characters and was clipped.
- `dependency.unavailable`: matplotlib/numpy cannot be imported in the scientific runtime.
- `render.failed`, `runtime.failed`: a concrete exception name is returned as undetermined, never a
  traceback or a blank image passed off as success.

Low/medium findings yield review (3); high findings on a rendered figure yield blocked (4); refused
and undetermined yield 5. The output limits distinguish programmatic evidence from scientific validity
and from human visual inspection.
