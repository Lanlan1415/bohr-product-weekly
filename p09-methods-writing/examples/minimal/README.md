# Minimal example (not a contest case)

Five config values and prose using only those values (50% is the percent form of dropout 0.5).
The primary methodflow runner proves that parameters are not converted into protocol steps, the
RNG seed does not prove allocation randomisation/blinding, and an invented 99 is blocked. Dataset
and most method categories are deliberately absent, so the honest status is `partial`, not success.

```bash
python3 -I scripts/run_example.py
```

The runner also validates result.json and refreshes example_result.json with an EXAMPLE ONLY label.
