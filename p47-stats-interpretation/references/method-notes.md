# Method notes: how the three claim checks work

## Why the audit recomputes instead of trusting

A report can be internally consistent and wrong: every sentence agrees with every
other sentence, and none of them agrees with the table. So the audit treats the
rows as the only source of truth. Group means, the difference, and the per-group
n are recomputed from the raw cells (values like `12.4`, `12.4 mg/L` and
`12.4±0.3` all parse; "not reported" and unparsed cells are excluded, never
counted as zero). The recomputed record is written into
`result.stats_audit.claims[]`, so a reviewer can check the report against it
without re-deriving anything.

## Direction check

The interpretation describes group_b relative to group_a. The direction claim is
read from two places and both must agree with the numbers:

- the wording: a small bilingual lexicon of upward words (higher, 增加, 高于,
  升高, 大于, 提升, 提高, 上升, ...) and downward words (lower, 低于, 降低, 减小,
  下降, ...). A sentence containing both is treated as ambiguous and skipped —
  a lexical check refuses to guess.
- the optional `direction` field on the claim ("higher" / "lower"), for
  interpretations that state the direction without the words.

If the recomputed means show mean_b above mean_a, the claim may say "higher";
saying "lower" (or claiming a direction when the means are equal) is
`stats.direction_mismatch`, a high finding.

## Significance check

The claimed p is parsed literally (number), or from strings like `"<0.05"`,
`"p=0.31"`, `"p > 0.05"`, or `"n.s."`. Significance language is detected
lexically, negation first — "不显著" contains "显著", so negation patterns
(不显著, 无显著, 未达显著, 无统计学, not significant, n.s.) are tested before
the affirmative ones. Then:

- p below 0.05 and negated wording → `stats.significance_mismatch`
- p at or above 0.05 and affirmative wording → `stats.significance_mismatch`

An interpretation that says nothing about significance is not forced to. The
check catches the two dangerous directions: dressing a null result as a finding,
and burying a real one.

## Number-citation check

Every number appearing in the interpretation is extracted, and at least one must
match a number the table computes (either group mean, the difference, or — for
whole-column claims — the overall mean). Matching uses a rounding tolerance
(0.2% of the computed value, floor 0.006 absolute) so the one-decimal rounding
convention of real reports does not fire false positives, while a cited 99.9
against a computed 31.23 does. Additionally, if the claim declares a `value`
(the claimed statistic), it is compared against the recomputed values and any
disagreement beyond the tolerance is reported. The finding carries both the
claimed and the computed numbers, so the fix is a rewrite, not an investigation.

## What the audit deliberately does not do

- It does not choose or run a statistical test. Test selection, normality and
  variance-homogeneity checks, and multiple-comparison correction belong upstream;
  this module audits the *sentence against the numbers*.
- It does not verify the claimed p value itself — only that the wording agrees
  with it.
- It does not judge practical significance. A significant 0.1% difference is
  correctly reported as significant; whether it matters is a human call the
  interpretation should carry.

## The statistical layer (v2)

The audit no longer only checks sentences: the engine now computes the numbers a
report should contain, in pure stdlib.

**Distributions.** The t and F tail probabilities come from the regularised
incomplete beta function (continued fraction, lgamma for the log terms). Validated
against table anchors: t=2.228139, df=10 gives 0.05 exactly; t=12.7062, df=1 gives
0.05; F=3.7083, df(3,10) gives 0.05; F=4.8259 gives 0.025; agreement is at the
1e-6 level, far below any reported precision. The t quantile (for confidence
intervals) is bisection on the same function — no external tables.

**Welch, not Student.** The two-sample test is Welch by default: unequal variances
and unequal group sizes are exactly the situation a real table presents, and
Student's pooled test silently degrades there. The claim record carries t, the
Welch-Satterthwaite df, and the computed p — so "p=0.04 被写成证明有效" has an
engine-computed counterparty. A claimed p whose significance verdict contradicts
the computed one is a medium finding (the claim may come from another test —
reconcile, do not fabricate agreement).

**Effect sizes and intervals.** Cohen's d (pooled SD) and Hedges g (small-sample
corrected) accompany every two-group claim, plus the 95% CI of the mean
difference from the t quantile. Three or more groups get a one-way ANOVA (F, p,
eta squared) on the grouping column, recorded even when the claim compares only
two — the rubric's "三组数据被塞进两样本 t 检验" becomes visible arithmetic.

**Shape advisories.** Per group: skewness and excess kurtosis; |skew| > 1 with
n >= 5 (or |excess kurtosis| > 1 with n >= 8) raises an advisory to prefer a
non-parametric test. Below those n the statistics are too unstable to advise on —
that silence is deliberate, not an oversight. Variance homogeneity is handled by
construction: Welch is always used, so a heteroscedastic table never meets a
pooled-variance test.

**Degenerate states are findings, not crashes.** A group with fewer than two
usable values (no variance) is stats.sample_too_small; zero variance is
stats.zero_variance; a group that is mostly gaps is stats.missing_ratio_high.
In every case the comparison is refused an audit verdict instead of being forced.

**Outliers.** Tukey 1.5-IQR fences on the pooled numeric values (columns with
fewer than 8 usable values are skipped — fences are meaningless there). Outliers
are listed with row and value and kept in the data; the keep/drop decision is a
human one, which is why they land in the to-confirm list as well.

**Charts.** A deterministic recommendation per analysis shape: 2-8 groups ->
box plot; a lone numeric column with >= 20 usable values -> histogram; few
points -> mean with CI bars; two numeric columns -> scatter. It is a
recommendation with its reason attached, not a rendering.

**Reproducibility.** run_manifest carries the engine version, the interpreter
version, the row count and the first 16 hex of the rows' sha256 — no timestamps,
so the same input yields a byte-identical manifest, and the platform records the
rest of the environment itself.

**What the layer still does not do.** It does not choose between test families
on your behalf beyond Welch/ANOVA (no Shapiro-Wilk, no Levene — shape advisories
are the honest stdlib substitute); it does not do post-hoc pairwise corrections
arithmetic (it audits that you declared one); it does not compute power or
sample size (out of scope per the task statement).
