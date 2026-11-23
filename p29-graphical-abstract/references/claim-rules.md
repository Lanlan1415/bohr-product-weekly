# Claim and narrative rules for a graphical abstract

## Four linked claims and one leader

`takeaways.problem`, `.method`, `.finding` and `.conclusion` must all be declared.
Each value is a node id or source text appearing in a node label. Substring matching
is deliberate: `Porous coating` is genuinely present in `Porous coating, 42 nm`.

A single explicit `core_message.text` leads the figure. Its evidence must point to
`materials[]`; a node carrying the bounded conclusion also requires evidence. The
four linked panels must have every adjacent edge in reading order, not merely one
arrow somewhere in the figure. The intended `reading_order` must follow the layers.

The old three-box pattern (problem/method/finding) is insufficient for the official
four-element workorder. Missing conclusion or broken final link is a finding, not a
stylistic variation.

## Source numbers versus result marks

`ga.value_not_in_source` checks every numeral in labels, core message, caption,
limitations and visual data after numeric-value normalisation (`3` equals `3.0`).
Moving a number into a caption does not evade the source check. Typography alone
cannot check a changed unit, lost hedge or inappropriate control; a reader must.

Quantitative findings require an actual data-to-mark encoding, not just a large
number in a coloured box:

- finding node has `visual_data.kind=bar` with one to four items;
- baseline defaults to and must remain zero;
- every value is finite and occurs in `source_values`;
- every item has evidence (or inherits its node's evidence), plus a text label;
- lower and upper, when used, bracket the central value;
- the unit states a real unit or explicit dimensionless declaration;
- `n_caption`/`n` and uncertainty semantics are visible and source-supported;
- the renderer reads each bar back and compares `rendered_value` with source_value.

Purely qualitative papers use `result_modality=qualitative`; this is an honest
routing decision, not a licence to invent measurements.

## Scope and uncertainty

`limitations[]` states source-supported scope/limits beside the conclusion. Missing
scope is a review finding (`ga.limitations_missing`); an invented limitation is not
an acceptable remedy. `uncertainty[]` records unresolved extraction/interpretation
questions in JSON and is separate from the source-backed limitation panel.

## Text, legend and reading hygiene

- Empty labels (`ga.empty_label`) cannot state a claim.
- Multiple node colours without a declared legend trigger
  `ga.legend_not_declared`; purely decorative encoding may use `legend_exempt`.
- Word count now includes labels, core message, limits, caption and visual labels.
  Publisher constraints come from the case, not a hard-coded journal table.
- Labels inserted with line breaks for physical fit are compared by whitespace
  normalisation. Any changed scientific word, number or entity still mismatches.

## Defensive refusal

A takeaways field of the wrong type counts as missing instead of crashing. Bad JSON,
non-object specs, empty nodes, render failures and missing scientific dependencies
write an undetermined result with `audit.no_section` and exit 5. If case.json is
readable, its case_id and every output_contract field still reach that structured
refusal. Formal case contracts take precedence over a working spec contract.
