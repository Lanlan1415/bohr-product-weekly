# Output fields

Every number is measured. If a field could not be derived it is `null` and the
reason appears in `limits[]`.

## Top level

| field | type | notes |
|-|-|-|
| `schema_version` | string | `figparse/v1` |
| `case_id` | string | echoed from the case file; never invented |
| `status` | enum | `success`, `partial`, `undetermined` |
| `panels` | array | one per detected panel |
| `tables` | array | parsed tables, added by `scripts/tables.py` |
| `limits` | array of string | every reason this result is partial |
| `provenance` | object | tool name, case file path, image count |

## `panels[]`

| field | type | notes |
|-|-|-|
| `panel_id` | string | `p1`, `p2`, … in reading order |
| `bbox_px` | object | `x0,y0,x1,y1` in full-image pixels |
| `frame_px` | object \| null | `left,top,right,bottom` in **panel-local** pixels; `null` means no axis frame |
| `frame_px.closed` | bool | whether right/top spines actually exist |
| `calibration.x`, `.y` | object | see below |
| `series` | array | digitised traces |
| `status` | enum | per-panel status |
| `notes` | array of string | human-readable caveats |

## `calibration.x` / `.y`

| field | notes |
|-|-|
| `ok` | false when no source could calibrate the axis |
| `source` | `tick_labels`, `axis_limits_frame_edges`, or `none` — how much trust this deserves |
| `scale` | `linear` or `log`, as fitted |
| `slope`, `intercept` | the fit; **y slope is negative** on a normal axis |
| `rms_px` | residual in px-equivalent units; a fit above 2 px is refused outright |
| `tick_pairs` | `[{px, value}]` — every pair the fit used, so it can be re-checked |
| `ticks_paired` / `ticks_detected` / `ticks_unread` | how much of the axis was actually labelled |
| `outlier_px` | ticks that sit far off the fit |
| `unit` | from the case file, `null` if not given |
| `label_source` | `case_file` or `missing` |
| `orientation_corrected` | values were supplied bottom-up and were reversed |
| `values_increase_downward` | y only; `true` = a real inverted axis, or a list that resists correction |
| `caveat` | present when the source cannot verify itself (frame-edge calibration) |

## `series[]`

| field | notes |
|-|-|
| `series_index` | order of discovery, most pixels first |
| `appearance` | `hue_bin`, `median_hue_deg`, `pixels` — enough to match a legend swatch |
| `x`, `y` | parallel arrays in axis units, or `axis_fraction` when uncalibrated |
| `x_unit`, `y_unit` | `axis_fraction` is the honest unit when labels were unreadable |
| `y_uncertainty` | linear axes: half the median stroke width in axis units |
| `y_uncertainty_relative` | log axes: fractional factor, applied as `y * (1 ± value)` |
| `error_bar_candidates` | tall isolated strokes with `x`, `y`, `y_err`; **candidates**, not data |
| `features` | `y_max`/`y_min` with their x, `y_span`, `direction_changes`, `trend` |
| `evidence` | how it was read, the frame used, the panel origin |

Because `evidence` carries `panel_origin_px`, any digitised point maps back to a
pixel in the original image and can be re-inspected. That is the point of
reporting it.

## `tables[]`

| field | notes |
|-|-|
| `path` | the file it came from |
| `ok` | false when the format was not recognised — the file is named, not guessed at |
| `n_rows`, `n_columns` | shape after parsing |
| `columns[]` | one per column, in file order |
| `columns[].kind` | `numeric` or `text`, decided by whether every non-empty cell parses |
| `columns[].values` | numeric: rounded floats, `null` for blank; text: strings verbatim |
| `columns[].non_numeric_cells` | text columns: row indices whose cell looked numeric |
| `columns[].unit_hint` | `percent` when the column used `%`; values stay as printed |
| `evidence` | how it was read |

## Filling an organiser `output_contract`

If `case.json` has an `output_contract`, each key it names is present at the top
level of `result.json`. Keys this tool can supply are filled. Keys it cannot
(`figure_caption`, `legend_text`, a prose `summary`) are set to `null` with a
`limits` entry — the agent doing the run fills those from the figure text and
the paper body, then removes the corresponding limit. A `null` left in place is
a statement that the field was not derived, which is always better than a
plausible-looking guess.
