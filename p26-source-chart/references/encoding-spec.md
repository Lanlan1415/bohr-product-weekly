# Encoding spec and how channels are validated

## Why channels map to column *names*

A spec that says `"y": [12.4, 31.2, 10.1, 14.8]` has already thrown away the link
to the source. A spec that says `"y": "response"` keeps it: the value at any mark
can be found again in the table, and a reviewer can check the mapping instead of
trusting it.

This indirection is the whole reason traceability is possible. Values live in the
data file and nowhere else.

## Validation order

1. **Chart kind** — must be one of `bar`, `line`, `scatter`, `box`, `heatmap`.
   An unknown kind is refused, never mapped to "the closest thing".
2. **Required channels** — each kind declares what it cannot be drawn without
   (`heatmap` additionally needs `value`). A missing channel is a refusal.
3. **Column existence** — every mapped column must be a real column. The finding
   lists the available columns so the fix is a one-line edit.
4. **Type fit** — `y`, `value`, `y_err`, `x_err` and a numeric `x` must be fully
   numeric. "Fully" means every non-blank cell parses; a column that is 90%
   numeric is not numeric, because the remaining 10% would silently become gaps
   or zeros.

## What refusal looks like

```json
{
  "status": "refused",
  "findings": [
    {"rule": "encoding.not_numeric", "severity": "high", "channel": "y",
     "column": "response",
     "message": "'response' is not fully numeric, so it cannot drive a numeric channel"}
  ],
  "note": "the spec was refused rather than approximated"
}
```

Refusing costs one round trip. Approximating costs a wrong figure that looks
finished, which is worse in every case that matters.

## Spec fields beyond channels

- error_meaning — what the error bars represent (SD, SEM, CI, range). Mapped
  error bars without it fire error.meaning_undeclared: a spread without a
  stated meaning cannot be reviewed.
- export.width_mm (+ tolerance_mm, default 2) — the journal column width the
  figure must fit. The audit measures the drawn width against it.
- error bars are drawn from the mapped column only; the engine never computes
  SD/SEM itself, because a derived statistic that is wrong is indistinguishable
  from a measured one.

## Chart-kind notes

- **bar** — a non-numeric `x` becomes the category axis, and the category strings
  are recorded per mark, so a bar can be traced by label as well as by row.
- **box** — one box per `group` value. Individual rows are still recorded in
  `mark_to_row`, so the distribution is traceable to the observations.
- **heatmap** — `x` and `y` define the grid, `value` fills cells. Cells present
  in the grid but absent from the data render as `NaN` (visible gaps), not zero.
- **line / scatter** — `y_err` draws error bars; a non-numeric `x` falls back to
  row order and the fallback is recorded in the mark, not hidden.
