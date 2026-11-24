# Synthetic figure benchmark method (v2)

Run optionally, outside the case workflow:

```bash
python scripts/bench_figure.py --report /app/work/figure-bench.json
```

The self-contained driver creates every raster in a fresh temporary directory,
executes the public CLI, scores against analytic truth, and removes temporary
inputs. It never writes benchmark PNG/cases into the submission.

## Ten scenarios

1. linear two-series — clean baseline and worst sinusoid error check;
2. log-x — rejects a forced-linear interpretation;
3. log-y — relative recovery and multiplicative geometry;
4. three crossing series — hue separation;
5. markers plus error bars — no-line trace and candidates;
6. explicitly inverted y — orientation does not get auto-reversed;
7. no frame — must leave `frame_px=null`, not invent an axis;
8. bars — individual count/top values, shared baseline;
9. bar annotations — black error caps/significance candidates;
10. context/contract — explicit legend binding, one original table, one linked
    caption value, exact output-contract keys, per-point intervals, CSV and two
    byte-identical cold runs.

Linear and bar worst errors are capped at 2% of the plotted y span; log-y uses a
10% relative bound to reflect multiplicative reading. These tolerances are
regression choices, not estimated performance on published papers. The no-frame
case passes only by structured refusal/partial output, and the context case
passes only if every named check succeeds.

The source design takes DePlot/ChartQA's chart-to-table evaluation objective but
uses deterministic calibration rather than a learned table generator. The
reported values are local synthetic regression evidence only: no official fixed
case, whiteboard, competitor, DePlot or ChartQA score is claimed.
