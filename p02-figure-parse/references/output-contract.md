# figparse/v2 output contract

`result.json` always preserves `case_id` and every field named by a readable
case's `output_contract`. Computed results win over placeholders; same-named
values explicitly present in the case pass through verbatim; an underivable
field is `null` plus a `limits[]` entry. Null is not an invented zero.

| field | semantics |
|-|-|
| `schema_version` | `figparse/v2` |
| `case_id`, `status` | input identifier; `success`, `partial`, `undetermined` |
| `provenance` | tool/schema, actual case path, image count; no invented timestamps |
| `sources[]` | every image/table path and available caption/table locator |
| `panels[]` | panel-local bbox/frame/calibration/series/status/notes |
| `figure_metadata[]` | title/caption/panel/axis/unit/tick/legend/other-axis/scale-bar declarations |
| `tables[]` | every declared original table; parse failure is named, never silently dropped |
| `readings[]` | flat point/bar records and `digitized.csv` source rows |
| `claim_alignment[]` | linked caption/body numeric checks, not semantic equivalence proof |
| `uncertainty[]`, `limits[]` | machine-readable reading caveats and all delivery gaps |
| `refusal` | structured code/message for unreadable case or no readable data |

## Calibration

`calibration.x/y` contains `source`, `scale`, `slope`, `intercept`, `rms_px`,
`tick_pairs`, unit and orientation details. Tick calibration is verified in
pixel space; >2 px RMS is refused. `axis_limits_frame_edges` is weaker and has
no residual, so it carries a caveat and a 2 px base interval allowance.

## Series and raster intervals

Each series records `chart_type`, `series_index`, optional `series_label` and
`legend_binding`, appearance/hue, x/y arrays and units. Labels are never assigned
from list order alone. `evidence.points_px` and bar `x_center_px/top_px` retain
pixel-level audit anchors.

`value_status=estimated_from_raster_not_exact` means every calibrated number is
an image estimate. `reading_intervals[i].x/y` (bar: `x/top`) has:

- `estimate`, `lower`, `upper`;
- `pixel_center` and `pixel_half_width`;
- `unit`, `basis`, and `kind=raster_reading_interval_not_statistical_ci`.

Both pixel endpoints are mapped independently, so log intervals are asymmetric.
The interval is not experimental uncertainty, not SD/SEM, and not a statistical
confidence interval. Old `y_uncertainty` / `y_uncertainty_relative` fields are
kept for compatibility but retain the old stroke-only interpretation.

Error bars and significance glyphs are candidates pending visual confirmation.
An annotation is never used as the source's exact error measurement by default.

## CSV

`digitized.csv` has `image,panel_id,series_index,series_label,point_index,
bar_index,x_estimate,x_lower,x_upper,x_unit,y_estimate,y_lower,y_upper,y_unit,
reading_tier,value_status`. Calibrated physical units and uncalibrated axis
fractions are never mixed. For bar rows `y_*` describes the bar top.

## Claim alignment

Each `text_claims` record supplies an exact point/bar link, claimed numeric
value/unit and original source locator. Alignment is:

- `consistent`: numerical value lies in the expanded raster interval;
- `inconsistent`: value outside it, or units differ without an explicit conversion;
- `unresolved`: source/point/field is not available or not numeric.

No status proves causality, statistical significance or whole-sentence semantic
equivalence. A conflict preserves both locators for re-reading.

## Status and exit codes

- `success` / 0: real digitised data, no input/alignment/limit gap;
- `partial` / 3: some useful result but calibration, table, context or input gaps;
- `undetermined` / 5: no usable plot/table or unreadable case, with `refusal`.

All three write result JSON atomically. A repeat run overwrites the same current
deliverable deterministically instead of appending duplicate tables.
