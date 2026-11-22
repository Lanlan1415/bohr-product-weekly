# Failure modes and what to do about them

Each row is a case seen on real paper figures, with the honest handling.

| situation | what the tool does | what the run must report |
|-|-|-|
| **No axis frame** (micrograph, gel, photo) | `frame_px: null` | It is an image panel; pixel-to-unit calibration does not apply. Measure against the scale bar and say the measurement came from the bar. |
| **Cropped axis** (spine or ticks cut off) | frame found, tick count short | Name which axis lost ticks and which range is untrustworthy. |
| **Log axis** | `auto` picks log when it fits better; `scale: log` | Confirm against the tick labels. Never present a log-axis reading as linear. |
| **Log axis supplied as linear** | fit residual exceeds 2 px → **refused**, panel `partial` | The axis model is wrong. Fix the input; do not report the numbers. |
| **Dual y axis** | only the left axis is calibrated | Name the second axis as *not extracted*. Two axes on one panel is where silent errors live. |
| **Missing legend** | series digitised but unnamed | Report each series by `median_hue_deg` plus a colour word, and state that the series-to-label mapping is unavailable from the image. Do not guess which curve is which. |
| **Over-exposed / washed out** | the saturation floor may drop pixels | If a series loses points mid-trace, `n_points` drops and gaps appear. Report the gap; do not smooth over it. |
| **Overlapping curves** | the lower series vanishes where covered | Report the covered span explicitly. Interpolating through it fabricates data. |
| **Grey or single-colour plot** | no saturated pixels, so no series | Say the figure is not colour-separated, so digitisation cannot separate series. Read specific values by eye and label them as eye-read. |
| **Error bars in the series colour** | tall isolated strokes reported as `error_bar_candidates` | Treat them as candidates, not data: a steep line segment looks the same. Confirm against the figure before using them. |
| **Curve doubles back at an extremum** | one column holds two strands; the sample lands between them | Expect up to about one stroke width of error at turning points. Say so if the task depends on a peak value. |
| **Tick count differs from supplied values** | `ok: false` with both counts in the reason | Re-read the labels; put `null` where a label is unreadable. Do not delete a tick to make the counts match. |
| **Values supplied bottom-up** | `orientation_corrected: true`, values reversed | Confirm the axis is normal. If it is genuinely inverted, declare `y_axis_inverted`. |
| **Genuinely inverted y axis** | kept as supplied when declared | `values_increase_downward: true` — make sure the reader knows, because a mirrored axis inverts every conclusion drawn from it. |
| **Figure is actually a table** | n/a | Do not run the figure path. Use `scripts/tables.py`. |
| **Table column partly numeric** | `kind: text`, `non_numeric_cells` filled | Name the offending row indices. Do not coerce them to zero. |
| **Table uses `%`** | `unit_hint: percent`, values kept as printed | Report the value and the unit as the paper had them. Convert only if the calculation needs a fraction. |
| **Table format not recognised** | `ok: false` with a reason | Name the file and stop. A guessed parse is a fabricated table. |

## What this skill will not do

- It will not read a legend and attach names to curves.
- It will not infer units from magnitude alone ("looks like mV").
- It will not promote `error_bar_candidates` to measured error bars on its own.
- It will not calibrate a second (right-hand) y axis.
- It will not fill a missing region of a curve.
- It will not interpret what a table *means* — only its values and their types.

Each of those is a place where a base agent typically produces a confident
sentence with nothing behind it. The value of this skill is that it stops at the
edge of the evidence and says where the edge is.
