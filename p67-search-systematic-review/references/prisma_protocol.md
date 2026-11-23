# PRISMA, bias and synthesis protocol

## External implementations consulted

1. **PRISMA2020** — `https://github.com/prisma-flowdiagram/PRISMA2020`
   - `inst/extdata/PRISMA.csv` explicitly distinguishes `database_results`, `duplicates`, `excluded_automatic`, `excluded_other`, `records_screened`, `records_excluded`, `dbr_sought_reports`, `dbr_notretrieved_reports`, `dbr_assessed`, `dbr_excluded`, `new_studies`, `new_reports`, and total/meta-analysis rows.
   - The external package formats these boxes but does not itself prove count consistency. This Skill adds six arithmetic checks and totals per reason code. `NA`/null remains unavailable, not zero.
   - `prisma_flow.csv` retains PRISMA `data`, `box`, `n`, exclusion details and source scope, so a reviewer can walk the same route rather than inspect only a static picture.
2. **robvis** — `https://github.com/mcguinlu/robvis`
   - `data_raw/data_rob2.csv` stores Study × D1–D5 × Overall rows with Low, Some concerns, High and No information.
   - `R/rob_summary.R` exposes tool-specific domain positions, `overall` and `weighted`; unweighted summaries are explicit.
   - This Skill computes overall risk from domain judgements, checks a reported overall for mismatches, and reports unweighted domain counts/proportions. It never uses domain counting as an effect-size weight.
3. **ASReview** — `https://github.com/asreview/asreview`
   - Its review/simulation separation informed explicit labels, prior/final decisions, duplicate visibility and export state. No model-based stopping or active-learning relevance ranking is silently applied here.

No external code or real-case results are bundled. All tests use synthetic records.

## Count model

For non-prospective runs, the engine checks:

- identified = malformed + duplicates + automation removed + other removed + records screened;
- records screened = title/abstract excluded + undetermined + reports sought;
- reports sought = reports not retrieved + full text assessed;
- full text assessed = full text excluded + undetermined + reports included;
- title/abstract reason-code totals = title/abstract excluded;
- full-text reason-code totals = full-text excluded.

A fixed corpus uses actual supplied rows, not assumed database hits. An executed search requires every source `hit_count` to equal its supplied export rows. A prospective protocol leaves external PRISMA counts null; it cannot be presented as a completed review.

Reports map to studies through `study_id`. Reports and studies are counted separately. Exactly one primary synthesis report per study prevents double counting; other included reports remain usable as supporting evidence.

## Risk-of-bias model

- ROB2 requires D1–D5. Any high domain produces overall high; otherwise any some-concerns/no-information domain prevents an overall low and yields some concerns; all remaining informative domains must be low for overall low.
- ROBINS-I requires D1–D7 and supports low/moderate/serious/critical/no-information/not-applicable. The overall uses the most severe informative domain.
- QUADAS-2 uses D1–D4; generic appraisals require at least one declared domain.
- Every domain judgement needs exact evidence from the included study. Overall computation is deterministic and a supplied `overall_reported` must agree.
- Domain summaries are unweighted. Primary vs sensitivity sets are protocol-declared via `primary_overall`; excluded-from-primary studies remain visible in all-study results and sensitivity changes.

## Effect synthesis and heterogeneity

When enabled, pooling requires the complete comparison group to have at least two primary studies, the same effect measure, finite estimates and positive standard errors. For study `i`, `y_i` is the estimate and `se_i` its standard error:

- fixed weight `w_i = 1 / se_i^2`;
- fixed mean `mu_F = sum(w_i*y_i) / sum(w_i)` and `se_F = sqrt(1/sum(w_i))`;
- `Q = sum(w_i*(y_i-mu_F)^2)`, `df=k-1`;
- `I2 = max(0, (Q-df)/Q) * 100%` (zero when Q=0);
- DerSimonian-Laird `tau2 = max(0, (Q-df)/(sum(w_i)-sum(w_i^2)/sum(w_i)))`;
- random weight `w_i* = 1/(se_i^2+tau2)`, with corresponding mean `mu_R` and `se_R`;
- normal 95% intervals are `estimate ± 1.96*se`.

The output includes both fixed and random models, Q, df, I2, tau2, included study IDs, all estimates and standard errors. I2 >= 75% is labelled exploratory-only and cannot serve as an unconditional headline. Clinical/method variation is reported separately from statistical heterogeneity. Selective removal of inconvenient studies is never allowed; sensitivity by risk uses a separately declared set.

This is deliberately not a substitute for a statistician's choice of effect model, small-sample correction, publication-bias analysis or GRADE.
