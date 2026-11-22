# Claim rules for a graphical abstract

## Why a graphical abstract needs its own audit

Layout rules answer "is this drawn correctly". They cannot answer "is this a
complete claim". A tidy, legible, correctly-exported three-box figure can still
fail to state what was found, or state a number the paper does not report.

## The three parts

`takeaways.problem`, `.method`, `.finding` must all be declared.

Each value is either a **node id** or **text that must appear on the canvas**.
Matching is by substring, deliberately: declaring `"Porous coating"` against the
label `"Porous coating, 42 nm"` counts as placed, because the takeaway genuinely
is on the figure and demanding exact equality would produce false failures. This
was confirmed against the benchmark scenario `takeaway_not_placed`, which had to
be rewritten once to use wording that is actually absent.

If you cannot declare all three, the honest move is to say the source does not
support a graphical abstract yet. Illustrating the setup without the finding is
the most common way a graphical abstract misleads.

## `ga.value_not_in_source`

Every numeral drawn in a label **or in the declared caption** is compared, after
normalisation, against `source_values`. Normalisation is by numeric value, so
`3`, `3.0` and `3.00` are the same figure. The caption is part of the figure:
a number that would be flagged on the canvas does not become acceptable by
moving it into the caption.

This is the rule worth the most. Three reasons it matters here specifically:

1. a graphical abstract is usually made last, from memory, under time pressure
2. it carries the most-read sentence of the paper
3. nobody checks it against the table

What it does not catch: a unit change (`3x` → `3%`), a hedge dropped
("up to 3x" → "3x"), or a comparison against the wrong control. Those need a
reader.

Related guard rules:

- `ga.source_values_unavailable` — no list was supplied, so numbers could not be
  checked (an honest gap, reported as such).
- `ga.source_values_invalid` — a list was declared but is not a list, so the
  check cannot run; mistyping the field must not pass silently.

## Panel readability: `ga.empty_label`

A panel with an empty or whitespace-only label cannot state its takeaway and
cannot be traced to a claim. It is reported as a medium finding; the honest fix
is a label carrying the source's own wording.

## The colour legend: `ga.legend_not_declared`

A graphical abstract encodes meaning in colour — problem, method and finding are
often told apart by colour alone. A figure that draws two or more colours and
declares no legend leaves the coding unexplained for a reader, and unreadable
again in grey-scale printing. The rule fires when two or more distinct node
colours are drawn and no legend entries are declared; `legend_exempt: true` opts
out for figures whose colours are purely decorative.

## The reading order: `ga.reading_order` and `ga.reading_order_unknown_node`

The declared reading order is compared against the drawn `layer` values. A
disagreement means a reader following the picture will read the panels in a
different sequence than intended — usually harmless, occasionally catastrophic
when the finding appears before the problem. Order entries naming panels that
are not on the canvas are reported separately, because an order that cannot be
followed is no order at all.

## `ga.takeaway_panels_unlinked`

If two or more takeaway panels are node ids, at least one edge must connect them
in declared order. Three boxes with no arrows is a legend, not an argument.

## `ga.reading_order`

The declared `reading_order` is compared against the drawn `layer` values. A
disagreement means a reader following the picture will read the panels in a
different sequence than intended — usually harmless, occasionally catastrophic
when the finding appears before the problem. Entries naming panels that are not
on the canvas fire `ga.reading_order_unknown_node` separately.

## Limits of the claim audit

- Text is matched, not understood.
- Numerical comparison ignores units and hedges.
- Word counting covers labels and a declared `caption` only; text rasterised into
  an image, or added afterwards in a vector editor, is invisible.
- Publisher limits are whatever `size_limit_mm` / `max_words` declare. There is no
  built-in journal table, because such a table would be wrong the moment a journal
  updated its guidance.
- Malformed input is handled defensively: a takeaways field that is not an object
  counts as not declared (the finding names the type it found), a legend or
  reading-order field that is not a list is treated as undeclared, and a
  canvas or size-limit field that is not a numeric pair skips the size check.
  A case with one mistyped field still gets a structured result instead of a
  crash.
