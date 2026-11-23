# Novelty audit protocol and external implementation references

This package uses explicit evidence and collision states, not keyword absence as a novelty proof.

## Evidence and decision states

- **P**: the original full text and decisive section were inspected.
- **A**: only the abstract was inspected; decisive claims remain bounded.
- **M**: metadata only.
- **U**: unverifiable. M/U cannot support a clear novelty gate.
- Collision classes: `direct_precedent`, `renamed_mechanism`, `algebraic_equivalent`, `statistical_equivalent`, `routine_adaptation`, `scene_transfer`, `followup_work`, `strong_baseline`, `none`.
- Claim outcomes: `covered_by_prior_work`, `specific_residual_difference`, `incremental_transfer_not_method_first`, `contested_in_scope`, `not_covered_in_declared_scope`, `undetermined`.
- Overall outcomes: `go_within_scope`, `conditional_go`, `pre_study_required`, `revise_and_recheck`, `undetermined`. These are independent gates, not a weighted score in which resources can compensate for a novelty collision.

## Concrete GitHub practices consulted

1. **PRISMA2020** (`https://github.com/prisma-flowdiagram/PRISMA2020`, `inst/extdata/PRISMA.csv`) distinguishes identification, screening and inclusion, represents missing values as `NA` rather than zero, and stores counts plus exclusion reasons in an explicit table. The topic engine adopts the same distinction for prospective searches: `hit_count` is null/undetermined unless a search was actually executed. The systematic-review sibling package implements the full PRISMA arithmetic rather than merely displaying boxes.
2. **robvis** (`https://github.com/mcguinlu/robvis`, `data_raw/data_rob2.csv`, `R/rob_summary.R`) stores per-study/per-domain judgements separately from the overall judgement and makes weighted versus unweighted summaries explicit. The topic engine likewise keeps source verification (P/A/M/U) separate from novelty and feasibility decisions; the systematic-review sibling uses per-domain evidence and unweighted bias summaries.
3. **research-novelty-gate** (`https://github.com/Cupit-zy/research-novelty-gate`, `references/workflow.md`) describes direct-precedent, renamed-mechanism, equivalence, routine-adaptation and strong-baseline collision checks, P/A/M/U evidence states, and independent go/no-go gates. This package implements those ideas as validated JSON rows and deterministic outcome computation. The external repository was consulted as a method reference; no external code or answer content is bundled.

The comparison matrix requires task, method, data, metric and conclusion evidence for every work. An incomparable row must identify the aspect and reason. Counter-evidence remains visible until a specific response is supplied. `not_covered_in_declared_scope` never means “the first worldwide”.
