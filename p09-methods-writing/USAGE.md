# Usage — methods-from-config

Formal mapping: `product-arena-05-64faa4a2`（写作09｜方法与实验章节写作）.
The validated package root is `p09-methods-writing/` in p3work and github_export.

## Primary command

The Agent writes an editable chapter from the supplied records; the engine does deterministic
extraction and auditing, not scientific invention.

```bash
python3 -I scripts/methodflow.py \
  --case /input/case.json --input-root /input \
  --prose /app/work/methods.md \
  --work /app/work --out /app/output
```

Add `--spec /app/work/method-spec.json` only when `coverage_overrides` records a sourced,
case-specific `not_applicable` decision. Then validate:

```bash
python3 -I scripts/validate_result.py /app/output/result.json \
  --contract resources/output_contract.json --case /input/case.json
```

Exit codes are `0` success, `3` partial with named gaps, `4` partial with unsupported numbers or
parameter conflicts, and `5` structured refusal/undetermined. Inspect `coverage.json`,
`gap_analysis.json`, `parameter_table.json`, `evidence_map.json`, and `methods.md` alongside
`result.json`. Every rerun replaces these files wholesale.

## Optional numeric-only check

```bash
python3 -I scripts/numeric_consistency.py \
  --prose /app/work/methods.md --table /app/output/result.json
```

Exit 0 means supported, 1 means unsupported/unit mismatch, 3 means unreadable input. The primary
pipeline also checks actual protocol/log excerpts, not only the parameter table.

## Tests

```bash
python3 -I scripts/bench_methodflow.py
python3 -I scripts/run_example.py
```

The fixtures are synthetic examples, not official cases. `assemble_result.py` remains a historical
compatibility script; its shallow nested-JSON/contract handling is not used by the primary workflow.
See `SKILL.md` for the complete field contract, 13 coverage categories, output precedence, failure
handling, and limits.
