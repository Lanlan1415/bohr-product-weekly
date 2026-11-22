# Benchmark method

`bench/bench.py` generates figures whose true data is known, runs the skill on
them, and scores the recovery against that truth. Every number in the reports
is measured; none is asserted.

## Why a generated question set

The challenge supplies three fixed cases that a participant never sees. A skill
shipped without its own test set cannot say whether it works — only whether it
ran. These cases exist so that a change to the calibration code can be judged
by a number instead of by opinion.

They are **not** prepared answers and **not** formal test outputs: they are a
question set with a scorer, published so anyone can re-run it on their own
figures.

## The seven cases

| case | what it tests | why it is here |
|-|-|-|
| `01-linear-two-series` | plain linear axes, two stroked curves | the easy baseline; if this fails nothing else matters |
| `02-log-x` | logarithmic x axis | a linear reader misplaces every point away from the ticks |
| `03-log-y` | logarithmic y axis, four decades | exercises multiplicative uncertainty and relative scoring |
| `04-three-series` | three series, one crossing the others | hue separation with crossings |
| `05-markers-errorbars` | markers only, with error bars | catches "no continuous line means no series" |
| `06-inverted-y` | y axis declared inverted | checks the orientation correction does not fight a real inverted axis |
| `07-no-frame` | a bare image panel | must refuse to calibrate rather than invent an axis |

## Scoring

- **Linear axes:** worst absolute error must be under **2% of the plotted y
  span**.
- **Log axes:** worst **relative** error must be under **10%**. Absolute error
  across four decades is always large and never informative; and on a log axis
  the reading error is genuinely multiplicative, so a relative bound is the
  honest one.
- **Bar cases:** every bar's `top_value` must sit within 2% of the plotted y
  span of its truth value, and the bar count must match exactly — a missing or
  invented bar is a failure, not a near-miss. Bars-with-annotations cases
  additionally require the black error bars and the significance marks above
  the bars to be reported as candidates.
- **No-frame case:** passes only if every panel reports `frame_px: null`. A
  detected frame there means the tool invented geometry.

## Current results on the author's machine

```
figure-parse (auto)     9 / 9 pass
ablation: forced linear 7 / 9 pass
```

The ablation runs the identical pipeline with log-axis detection disabled. It
fails `02-log-x` and `03-log-y`, and it fails them by **refusing** — returning
`partial` with `axis_fraction` units — rather than by returning wrong numbers.
That refusal is the behaviour being tested: the residual check is what turns an
unrecognised log axis into an honest "I cannot calibrate this" instead of a
plausible wrong answer.

The two bar cases score the statistical-chart path: solid columns must be read
per bar (the curve path would read a bar as a horizontal line through its
middle), and the black marks above bar tops — invisible to the colour mask —
must surface as annotation candidates.

**What the ablation is and is not.** It is an ablation of *this* tool. It is not
a measurement of any other agent, model, or product, and it should not be read
as a claim about them. The challenge's own base-agent-versus-skill comparison is
produced by the evaluation platform, not here.

## Reproducing

```bash
python bench/bench.py make     # writes bench/cases/*/
python bench/bench.py score    # writes bench/report.json, exits non-zero on failure
```

`bench/report.json` carries the per-case numbers, including which truth curve
each digitised series was matched to — so a pass cannot hide a case that
matched the wrong curve.

## Known weaknesses of this benchmark

- Generated figures are cleaner than published ones: no JPEG artefacts, no
  overlapping annotations, no clipping, one font. Real-figure accuracy will be
  worse than the numbers above, and throughput on a real paper is the honest
  measure, not this table.
- Tolerance choices (2% of span, 10% relative) are defensible but arbitrary.
  They are stated here so they can be argued with.
- Seven cases is a small set. It catches regressions and the failure modes that
  were deliberately planted; it does not estimate general accuracy.
