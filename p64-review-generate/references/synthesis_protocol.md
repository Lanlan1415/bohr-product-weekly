# Evidence synthesis protocol and implementation references

The formal CLI builds a cross-study synthesis from an evidence table. It does not concatenate abstracts and it does not treat generic headings such as background/methods/challenges as corpus-derived themes.

## Computed workflow

1. Freeze review question and screening criteria; replay each include/exclude/undetermined decision and identify DOI/title duplicate exports.
2. Normalize only included canonical records into method/data/metric/conclusion rows. Every field must have an evidence ID with a verbatim quote and exact locator.
3. Assign one or more bounded themes through a rationale plus evidence refs. Multi-label membership is reported explicitly instead of forcing a lossy partition.
4. Group comparable outcomes by `comparison_key`. Different directions (`positive`, `negative`, `no_effect`, `mixed`) generate conflict candidates automatically.
5. Create cross-study claims: consensus, contradiction, method comparison or data comparison. Contradictions require independent support and contrary record sets. Other claims are downgraded when they omit opposing records.
6. Strength is computed, not self-declared: `established` requires at least two independent full-text records without omitted conflict; `suggestive` covers single-source or limited-text evidence; `contested` preserves disagreement; `undetermined` indicates an invalid two-sided claim. This is deliberately not presented as formal GRADE.
7. A research gap needs positive source evidence plus source/query/year/outcome scope checks. An empty search alone is never enough.
8. Generate the prose only after these tables exist. Each paragraph carries support and contrary locators, and citation coverage counts cited included records and locatable claims.

## GitHub practices consulted and implemented locally

- **PRISMA2020** (`https://github.com/prisma-flowdiagram/PRISMA2020`, `inst/extdata/PRISMA.csv`) provided the explicit stage-count and missing-value model. Here counts are derived from actual input rows; the systematic-review sibling adds full PRISMA closure and per-reason totals.
- **robvis** (`https://github.com/mcguinlu/robvis`, `data_raw/data_rob2.csv`, `R/rob_summary.R`) provided the per-study/domain judgement model and the distinction between evidence rows and aggregate summaries. The review engine keeps field-level quotes and conflict coverage behind each overall claim; the systematic-review sibling adds per-domain bias audit and unweighted summaries.
- **ASReview** (`https://github.com/asreview/asreview`) provided the separation of record labels, duplicate visibility and export state. This package does not import ASReview or use model-based stopping; all decisions remain explicit and replayable.

No external code, formal answers, real-paper metadata or search counts are bundled. All shipped examples are synthetic and marked accordingly.
