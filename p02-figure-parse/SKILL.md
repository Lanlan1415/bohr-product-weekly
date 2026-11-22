---
name: figure-parse
description: >
  Read a scientific figure into structured, evidence-backed data, and ingest the
  tables that accompany it. Detects plot panels and axis frames, calibrates
  pixel coordinates to axis units from tick marks, digitises each coloured
  series into (x, y) pairs with units and a stated reading uncertainty, reads
  bar charts as per-bar values with their shared baseline, and reports ink marks
  above bars (error-bar caps, significance markers) as candidates. Reports
  honestly when a panel cannot be calibrated. Use when a task gives a raster
  figure (PNG/TIFF/JPEG of a paper plot) plus its tables and asks for plotted
  values, axis type, units, trend, bar heights, significance marks, or a data
  table rather than a prose description.
---

# figure-parse

Turns a chart image into numbers a reviewer can re-check, and keeps the paper's
own tables verbatim instead of re-typing them.

Two rules govern everything below:

1. **Never invent a tick value.** Geometry (where the ticks are) is measured
   from pixels. Labels (what the ticks say) come from the caller. When labels
   are missing the skill says so and reports axis fractions.
2. **Never silently change a unit.** A `%` is kept as printed and flagged, not
   quietly divided by 100. A log-axis error is reported as a factor, not an
   offset. Every transformation is named in the output.

## When to use it

Use when the material is a **raster figure** and the task wants plotted values,
axis type and scale (linear vs log, dual axis), units and their magnitude
(mV vs V), trend and peak positions, bar heights and their error bars,
significance marks, or a data table.

Do **not** use the figure path when:

- the material is already a **table** — use the table path below; digitising
  numbers that are already numbers only adds error
- the material is a **micrograph or gel** with no axis frame — there is no
  pixel-to-unit calibration to make; measure against the scale bar and say so
- vector source coordinates (SVG/PDF paths) are available — extract those
  directly, which is exact and beats any pixel method

## Curves and bars are read by different rules

A stroked curve and a solid bar are opposite geometries, and reading one with
the other's method produces confident nonsense: the per-column median that
traces a curve reads a solid bar as a horizontal line through its *middle*.

- A **curve** is thin: each column carries a few rows of ink, and the median-y
  per column is the trace. One `(x, y)` list per colour.
- A **bar** is solid: flat top, ink all the way down to a shared baseline. The
  bar detector refuses anything else — adjacent bars that touch merge into one
  run and fail the flat-top test, so the panel falls back to the curve path and
  is reported as not-bar-like, never guessed.
- Marks **above bar tops** (capped error bars, `*` significance glyphs) are
  drawn in black, invisible to the colour mask. They are reported as
  `annotations`: tall strokes as `error_bar_candidates`, glyph-scale blobs as
  `marker_candidates` — candidates, always confirmed by a reviewer
  against the figure, never asserted as measured values.

Every series entry carries a `reading_tier`: `calibrated_digitised` when both
axes fitted (values in physical units with a stated uncertainty) or
`axis_fraction` when they did not. When writing conclusions, keep the three
tiers apart:

| tier | may say |
|-|-|
| 图中直接可读 | values from `tables[]` (verbatim), calibrated series/bar values, bar baselines |
| 合理推断 | `features.trend`, peak ordering, comparisons between series, annotation candidates once confirmed |
| 无法确定 | uncalibrated panels, refused fits, marks nobody confirmed, anything under `limits[]` |

## Input contract

`/input/case.json` is the authority. Read it first; do not assume field names
from this document if the case file disagrees.

```json
{
  "case_id": "<string, echoed into the result>",
  "images": [
    {
      "path": "figure1a.png",
      "x_tick_values": [0, 2, 4, 6, 8, 10],
      "x_unit": "time (s)",
      "y_tick_values": [100, 80, 60, 40, 20, 0],
      "y_unit": "potential (mV)",
      "x_scale": "linear",
      "y_scale": "linear"
    }
  ],
  "tables": ["table1.csv"]
}
```

**Tick-value order is reading order.** `x_tick_values` run left→right;
`y_tick_values` run **top→bottom**, so a normal y axis fits with a negative
slope. If the list comes out the other way the skill reverses it and sets
`orientation_corrected`, rather than returning mirrored numbers — but a
genuinely inverted y axis must be declared with `"y_axis_inverted": true`, or it
will be "corrected" back to normal.

Each list must have one entry per detected tick. Put `null` where a label is
unreadable; the remaining pairs still calibrate.

## Calibration ladder

The skill tries four sources in order and names the one it used in
`calibration.x.source` / `.y.source`:

| # | source | how it is verified |
|-|-|-|
| 1 | `tick_labels` | least-squares residual over the tick positions |
| 2 | `tick_labels` with nulls | same, on the paired subset |
| 3 | `axis_limits_frame_edges` | **no residual** — frame edges assumed to equal the limits; a caveat says so |
| 4 | none | `axis_fraction` units, panel status `partial` |

A fit whose residual exceeds 2 px is **refused**, not reported. That check is
what stops a log axis from being read as linear with a confident-looking score:
the linear model cannot fit log tick positions, so the residual blows up and the
skill falls through the ladder instead of returning wrong numbers.

## Output contract

`/app/output/result.json`:

| field | meaning |
|-|-|
| `case_id` | echoed from the case file |
| `status` | `success` \| `partial` \| `undetermined` |
| `panels[]` | one per detected panel, with `frame_px`, `calibration`, `series[]` |
| `panels[].series[]` | per colour: a `curve` (x/y point lists) or `bar` entry (per-bar values), each with `reading_tier` |
| `panels[].series[].bars[]` | bar charts: `x_center`, `top_value`, `baseline_value`, `height_value` per bar |
| `panels[].series[].annotations` | ink above bar tops: `error_bar_candidates`, `marker_candidates` |
| `panels[].series[].error_bar_candidates[]` | curve error bars: tall isolated strokes, offered as candidates |
| `tables[]` | parsed tables: columns typed, values verbatim, unit hints |
| `limits[]` | every reason the result is less than complete |

If the case declares an `output_contract`, every field it names is present —
filled when derivable, `null` plus a `limits` entry when not. A `null` means
"could not derive", never a fabricated value.

## How to run it

1. **Tables first** — they are cheap and exact. They are also where most of the
   required content usually is.

   ```bash
   python scripts/tables.py --case /input/case.json --out /app/output tables/*.csv
   ```

   Refuses unparseable files by name instead of guessing. A column that is
   mostly but not entirely numeric keeps the offending row indices in
   `non_numeric_cells` rather than being coerced.

2. **Calibrate the figure, look at the geometry.**

   ```bash
   python scripts/figparse.py calibrate --image figure1a.png --out calib.json
   ```

3. **Supply the tick labels** from the figure text or an OCR pass, and check the
   counts: one value per detected tick, `null` where unreadable.

4. **Digitise.**

   ```bash
   python scripts/figparse.py run --case /input/case.json --out /app/output
   ```

   the steps compose in one order only: `run` first (it writes `panels` afresh), then `tables`, which merges its `tables` into the existing `result.json` — running them the other way round loses the table list.

5. **Check it against the benchmark before trusting a result.**

   ```bash
   python bench/bench.py make && python bench/bench.py score
   ```

   9 generated figures with analytic ground truth, covering linear, log-x,
   log-y, three crossing series, markers with error bars, a declared inverted
   axis, a bare image panel that must be refused, a bar chart read per bar, and
   bars with black error bars plus significance marks above them. On this
   machine all 9 pass; the forced-linear ablation passes 7, failing exactly the
   two log cases by refusing rather than by reporting wrong values. See
   `references/bench-method.md`.

## Reading the result honestly

- `rms_px` is the calibration residual. Sub-pixel means the tick positions are
  consistent with the fitted axis. Over 2 px the fit is refused outright.
- `y_uncertainty` (linear axes) is **reading precision** from the stroke width.
  `y_uncertainty_relative` (log axes) is a fractional factor — the same pixel
  error is multiplicative there, so a linear bar would understate the error at
  the top of the axis and overstate it at the bottom.
- `error_bar_candidates` are exactly that. A steep line segment and an error bar
  are geometrically similar; the skill isolates tall strokes that stand alone,
  and a reviewer confirms against the figure.
- `status: partial` with `axis_fraction` units is the honest outcome for a
  figure whose labels could not be read. Report it that way.

## Limits

- **Colour-separated series only.** Series differing only by marker shape or
  line style merge into one trace. Say so rather than presenting the merged
  curve as one series.
- **Bar detection needs gaps and colour.** Bars that touch merge into one run
  and fail the flat-top test, so the panel falls back to the curve path —
  grouped bars drawn edge-to-edge are reported as not-bar-like, not guessed. A
  very thick *dashed* flat line can present short flat runs on a shared
  baseline; check `n_bars` against the figure before trusting a bar reading.
  A greyscale bar chart cannot be separated from its spines at all — there the
  tool says so rather than returning values.
- **Frame and tick search run on near-black ink.** Axis furniture is drawn
  dark while data ink is saturated, which is how solid bars are kept from
  reading as spines. A figure whose spines are themselves coloured loses that
  separation and is reported honestly if the frame cannot be found.
- **Annotation candidates are not measurements.** An error-bar candidate is
  any tall ink mark above a bar top; a significance-marker candidate is any
  glyph-scale blob there. Brackets, letter grades and stray antialiasing land
  in the same lists — the reviewer confirms against the figure.
- **Local extrema cost accuracy.** Where a curve doubles back inside a single
  pixel column, the column sample lands between the two strands — up to about
  one stroke width of error at a turning point. Visible in the benchmark as the
  largest error on the sinusoid (≈1.9 units on a 0–100 axis).
- **No dual y-axis.** Only the left axis is calibrated. A second y axis is
  reported as not extracted; naming it is mandatory.
- **No legend reading.** Series are reported by colour, not by name.
- **No OCR dependency, by design.** Label accuracy on 6 px text varies far more
  than the geometry does, and a wrong label silently rescales everything. The
  label step stays explicit and visible to the caller.
- **Tables are parsed, not understood.** Header semantics, merged cells and
  footnotes are not interpreted. A mis-parsed table is a fabricated result, so
  unknown formats are refused rather than guessed.

## Failure handling

| symptom | what to do |
|-|-|
| `frame_px: null` | panel has no axis; treat as an image panel, do not digitise |
| fit refused with `rms_px` in the reason | axis model wrong (log? broken? stray tick) — fix the input, do not report |
| tick count ≠ value count | re-read the labels; put `null` for the unreadable ones |
| `orientation_corrected: true` | values were supplied bottom-up; correct only if the axis is normal |
| `values_increase_downward: true` | a deliberately inverted axis; confirm it is intended |
| `chart_type: "bar"` with `n_bars` not matching the figure | check for touching bars or a thick dashed line; the detector refuses rather than guesses, so a mismatch means the input needs a second look |
| `baseline_note` set | the shared baseline does not read as 0: offset axis, broken axis, or bad calibration — confirm before quoting `height_value` |
| annotation candidates present | confirm each against the figure before writing "significant" or an error magnitude |
| no series found | figure may be greyscale or single-colour; say so |

See `references/` for the method, the error budget, the field definitions and
the edge cases.

## Dependencies

This skill requires the following Python packages:

```
pip install matplotlib numpy Pillow
```

- **matplotlib**: figure rendering and axis calibration
- **numpy**: numerical array operations for data extraction
- **Pillow (PIL)**: image loading and pixel-level analysis

If these packages are not available, the skill will fail to produce figures. Install them before running any CLI command documented above.
