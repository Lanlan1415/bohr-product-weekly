# Judgement notes: how anomalies and causes are judged

## Two detectors, two different kinds of evidence

The challenge names "结合物理上下限与分布诊断判定", and the two detectors are not
interchangeable:

- **Physical range (`plausible` per column)** — a hard, declarative bound: a
  curing time cannot be negative, a hardness reading above the instrument's
  ceiling is impossible. A value outside it is flagged by the cleaning pass (R05)
  with the value, the range, and the reason on the record. Where the bound comes
  from (data dictionary, instrument spec, process limit) belongs in the report.
- **Distribution diagnostic (IQR far-out fence)** — a soft, data-driven bound:
  the column's own quartiles, flagged only beyond 3xIQR. The far-out fence (not
  the 1.5x mild fence) is deliberate: flagging normal variation as anomalous is
  a named failure mode of this topic, and the mild fence does exactly that on
  small samples. The diagnostic also refuses to run below six parsed values —
  below that, quartiles describe the sample, not the process.

When the two disagree (inside the physical range, far outside the distribution —
or the reverse), the report should carry both fences and the sample size, and the
physical bound wins for the keep/drop/cap decision.

## What "explained" means

An anomaly is explained when an observation entry cites the flagged value and
states what happens to it: kept (with why it stays), dropped (with the
recalculation convention for the report), or capped (with the cap value). The
coverage check matches values, so the explanation must cite the number — an
explanation about a different row does not cover this one. The summary in
`interpretation_audit` counts flagged versus explained, so a reviewer can see the
gap without reading the prose.

## The cause check is a record check, not a truth check

Causal wording (由于 / 导致 / 归因于 / because / due to / ...) in an explanation
asserts a mechanism. The engine does not and cannot verify the mechanism; what it
can verify is that the assertion left a trace: a `cause` field on the observation
recording the candidate cause and its supporting evidence (a log, a batch record,
a failed control). An assertion without a record is `anomaly.cause_asserted`,
because a mechanism guess with no exclusion process behind it is exactly the
failure mode the topic names — "原因只给一个没有排除过程的机理猜测".

Downgrading the wording is always an acceptable fix: "与搅拌时间相关" states a
correlation and needs no cause record; "由搅拌时间不足导致" states a cause and
needs one.

## Grounding: why cited numbers must exist

A trend sentence that no row supports is not an interpretation, it is a
generation artifact. Every `value` and `baseline` cited by an observation is
matched against the parsed numeric cells of the table (unit-bearing cells parse;
the optional `metric` field scopes the search to one column). The tolerance is
tight (0.2%) — it absorbs decimal-formatting differences, not paraphrasing a
number that is not in the data. The finding names the cited number and where the
engine searched, so the fix is either to cite a real value or to add the data
with a note.

## Trend direction: first-to-last consistency, not curve fitting

The mechanical trend check is deliberately simple, because its job is to catch
one specific defect: a conclusion whose direction the numbers contradict. The
engine sorts rows by the declared `trend.order_column`, takes the metric's
first-to-last relative change (last - first) / max|value|, and classifies it as
up, down, or flat against a deadband (default 2 percent, configurable via
`trend.deadband`). A claim that contradicts the classification is
`trend.direction_mismatch` (high). A claim the table cannot verify — no order
column declared, fewer than two parseable points — is `trend.unverifiable`
(medium): declare the ordering column or degrade the sentence to a reading
restatement. Opposite direction words in one sentence ("先升后降") are not
adjudicated: the engine records a limit and asks for a split claim or an
explicit `trend_claim`. The deadband absorbs normal jitter; it is a convention,
so the report should state it next to the claim.

## Review steps: form, not truth

An executable review step pairs an action verb (回查 / 核对 / 复算 / 重跑 /
比对 / …, or verify / recompute / rerun / compare / repeat / trace) with a
concrete target (a file name, a field, a batch, a device log, a computable
quantity). "检查数据质量" fails both halves — 检查 is deliberately not on the
verb list, and 质量 names no target — which is exactly the anti-pattern the
topic calls out. The check is a form check: it cannot know whether the step,
once executed, actually excludes the cause; that is the executor's judgement.
What it can do is guarantee that every recorded cause ships with an exclusion
process someone else can start (`review.missing_for_cause`) and that no step
asks a second person to do something unactionable.

## Next experiments: bound to a cause, priced with a risk

A follow-up experiment is only actionable when three things are on the record:
what to change (`change`), which recorded cause candidate it addresses
(`addresses`, matched by containment against the observation's cause factors or
the spec-level cause_candidates), and the risk or precondition of running it
(`risk`: equipment time, safety boundary, budget, "needs expert confirmation").
An unbound suggestion (`next.unbound`) or one pointing at a candidate recorded
nowhere (`next.dangling`) is a hypothesis without an anchor; a risk-free
suggestion (`next.risk_missing`) reads as an executable fact, which the
confirmation-items contract forbids. The fix is always to write the missing
half down, never to drop the suggestion.

