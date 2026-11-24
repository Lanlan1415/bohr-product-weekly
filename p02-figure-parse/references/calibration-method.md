# Calibration method and error budget

## Why geometry and labels are separate steps

A wrong tick *label* rescales every number on the axis, and does it silently:
the plot still looks right, the output still looks plausible. A wrong tick
*position* is caught immediately by the fit residual. So this skill measures
positions from pixels — cheap, reproducible, checkable — and refuses to guess
labels, which on 6 px text are impossible to verify from the image alone.

## Pipeline

1. **Ink mask.** A pixel is ink when it is more than `INK_DELTA` (60) below the
   panel's median luma. Using the panel median rather than a fixed threshold
   keeps one code path for a clean render and an over-exposed scan.
2. **Panel split.** Dilate the ink mask 9 px, label connected components, drop
   anything under 40×40, merge components overlapping in both axes. Dilation is
   what keeps a panel's tick labels and markers attached to its own panel.
3. **Frame.** The longest straight ink runs are the spines. The leftmost long
   vertical run is the y axis, the lowest long horizontal run is the x axis.
   Right and top fall back to the panel edge when the plot has no opposing
   spines — the common journal case — because calibration only needs the two
   real axes, and clipping to the panel never discards data.
4. **Ticks.** A tick is a short stroke perpendicular to an axis, in the narrow
   band just outside the spine (≤7 px). Runs of 1–6 px count; longer runs are
   the spine itself or a gridline.
5. **Fit and verify.** Least squares in pixel space. `auto` fits both linear
   (`v = a·p + b`) and log (`log10 v = a·p + b`) and keeps the smaller
   px-equivalent residual. **A fit worse than 2 px is refused.** This is the
   single most important line in the tool: it is what makes an unrecognised log
   axis produce "I cannot calibrate this" instead of a plausible wrong answer.
6. **Digitise.** Saturated pixels inside the frame (S ≥ 45) binned on a 15° hue
   grid. Per series, each column contributes one median-y sample. Pixels within
   2 px of the frame are excluded so spine antialiasing does not read as data.

## Orientation

Image rows grow downward; a normal y axis grows upward. Tick positions and tick
values are therefore paired **in reading order** (top→bottom), which makes a
normal y axis fit with a *negative* slope.

If the supplied list fits with a positive slope, the likely cause is a
bottom-to-top list rather than a genuinely inverted plot. The skill reverses it,
refits, and sets `orientation_corrected`. A real inverted axis must be declared
with `y_axis_inverted: true`, or it will be corrected back to normal — which is
the right default (inverted axes are rare, bottom-up lists are common), but it
is a default, and the output says so.

## Error budget

| source | size | how it shows up |
|-|-|-|
| stroke half-width | 0.5–1.5 px | `y_uncertainty` — the dominant term |
| tick centroid quantisation | ≤1 px | in `rms_px` |
| frame edge detection | ≤1 px | a constant offset, invisible in `rms_px` |
| curve doubling back at an extremum | ~1 stroke | per-point scatter at turning points |

**On a log axis the budget is multiplicative.** Half a stroke is a constant
*pixel* span, which through a log axis becomes a constant *factor*: at 85 px per
decade and a 3 px stroke that is about 4% in value, everywhere on the axis. A
linear error bar there would understate the error at the top and overstate it at
the bottom, so the log path reports `y_uncertainty_relative` instead of
`y_uncertainty`.

**`rms_px` cannot see a constant offset.** A frame edge detected one pixel
inward shifts every reading equally and the residual stays at zero, because all
ticks shift together. No pure-geometry method can catch that, which is why the
run procedure ends by reading the extreme values back against the picture by
eye.

## Per-reading interval (v2)

Every calibrated point maps both ends of its pixel interval through the fitted
axis. The current synthetic-benchmark maximum linear y error is 1.855 units on a
0–100 axis and log-y worst relative error is 7.81%; all 10/10 geometry/context
scenarios pass (see `references/bench-method.md`). These values are synthetic
regression measurements, not accuracy on the platform's unpublished cases.

Unlike the compatibility field `y_uncertainty`, which only represents half the
stroke width, `reading_intervals[].x/y` includes pixel quantisation, tick RMS
and (for y) half the measured stroke thickness. For log axes, independently
mapping the two endpoints retains multiplicative asymmetry. Frame-limit fits
have no residual to measure, so a stated 2 px base allowance is used. These
intervals do not cover wrong OCR/axis choice, a shared systematic frame offset,
occlusion or experimental uncertainty. They are raster-reading intervals, never
statistical confidence intervals.

## When to distrust the output

- `source: axis_limits_frame_edges` — no residual to verify the fit; correct
  only if the axes box really is the data range (ggplot's default margins break
  this).
- any `outlier_px` — the tick list contains a mark that is not a tick.
- `orientation_corrected` on an axis you believe is inverted — declare it.
- a series that looks implausibly smooth, or a flapping trace — the hue bin is
  probably catching two series at once.
