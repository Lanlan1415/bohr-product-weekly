# Statistical method notes (v3)

All direct analyses run on the cleaned and explicitly duplicate-resolved analysis table.
Missing, unparsed and non-finite cells are excluded per analysis and counted; no zero
substitution or imputation occurs. Duplicate records under the default `review` policy
block inferential output rather than silently increasing n.

## Independent comparisons

Welch uses `b-a`, unequal group variances, and the Welch–Satterthwaite df. Its CI is the
95% interval for the difference of means. Cohen d uses the pooled SD and Hedges g applies
the small-sample correction. A zero-variance/insufficient-df state returns undetermined.

For three or more groups, ordinary one-way ANOVA produces F, df, p, eta squared, omega
squared and Cohen f. Post-hoc comparisons are Welch tests with Holm adjustment by default.
A Brown–Forsythe diagnostic is reported separately because classical ANOVA does not share
Welch's unequal-variance protection.

## Paired designs

`pair_id` is mandatory. Complete one-before/one-after pairs define differences `b-a`;
incomplete, duplicated or nonnumeric pairs are listed and excluded. Paired t reports the
mean difference, its t CI and Cohen dz. Wilcoxon removes zero differences before ranking,
reports W+/W- and matched rank-biserial, and uses exact sign assignments when there are no
ties and n<=25; otherwise it uses the stated tie/continuity-corrected approximation.

Treating paired observations as independent is forbidden. Zero-variance differences or all
zero differences return undetermined instead of an invented infinite statistic.

## Rank tests and distribution functions

Mann–Whitney uses average ranks. For no ties and n1*n2<=100, an independent recurrence
enumerates the conditional U distribution; the two-sided p is twice the smaller inclusive
tail, capped at one. With ties/larger samples it uses a tie-corrected normal approximation
with continuity correction. Rank-biserial is `2U_b/(n1*n2)-1`, positive when b tends higher.

Kruskal–Wallis includes the standard tie correction and a regularized-gamma chi-square
survival implementation. The signed-rank exact distribution similarly enumerates sign
assignments. Undefined all-tied states are named, never coerced to p=0 or p=1 arbitrarily.

Student t and F tail probabilities use the existing regularized incomplete-beta continued
fraction, independently anchored at t=2.228138852/df=10 -> p=.05, t=12.706204736/df=1 ->
p=.05 and F=3.7083/(3,10) -> p=.05. The t quantile is bisection on that same function.

## Assumptions and effect intervals

Jarque–Bera uses n/6 * (skew² + excess_kurtosis²/4) and an asymptotic chi-square(df=2) tail.
It is undefined here for n<8 or zero variance. Non-rejection is not proof of normality.
Brown–Forsythe applies one-way ANOVA to absolute deviations from group medians.

Mean-difference CIs are parameter intervals, not individual prediction ranges or effect-size
CIs. Rank tests and omnibus tests do not receive fabricated mean-difference intervals.
ANOVA reports omega squared alongside eta squared; Kruskal reports epsilon squared.

## Multiplicity and correlation

Bonferroni, Holm and Benjamini–Hochberg adjusted p values are computed with original-input
index restoration and monotonicity enforcement. Rejection equals adjusted p<=alpha.
Reference anchor: raw `[.01,.04,.03]` gives Holm `[.03,.06,.06]` and BH `[.03,.04,.04]`.
This mirrors the useful output semantics of statsmodels `multipletests`, without depending
on that package.

Pearson uses complete finite pairs and a t statistic with n-2 df. Spearman applies the same
calculation to average ranks and is explicitly labelled as the common approximation. Fisher
z intervals require n>=4 and |r|<1; perfect correlation or smaller n leaves the CI
undetermined. Every correlation record states that association does not establish causation.

## Hand-check anchors

- Paired differences `[1,2,3]`: mean=2, sample sd=1, `t=2*sqrt(3)`, df=2,
  `p=0.0741799002274486`.
- Mann–Whitney `[1,2]` vs `[3,4]`: U=4; two extreme assignments among six -> exact p=2/6.
- Three groups `[1,2,3]`, `[4,5,6]`, `[7,8,9]`: rank sums 6,15,24 -> H=7.2;
  chi-square df=2 tail is `exp(-3.6)`.
- Ordinary ANOVA on those groups: SSB=54, SSW=6 -> F=27 with df=(2,6).

## Limits

Prospective power/sample-size planning is outside the task. Observed post-hoc power is not
computed; p>=alpha does not demonstrate equivalence. The package does not claim Shapiro–Wilk,
Hodges–Lehmann intervals, noncentral-t effect-size intervals, mixed-effects models or causal
identification. Those quantities remain null/absent with limits, never synthetic values.