# Layout and export rules

Shared with the general schematic engine; see `scripts/schematic.py`.

## Structure
`coverage.incomplete`, `entity.duplicate`, `edge.count_mismatch`,
`edge.zero_length`.

## Geometry
`label.overlap`, `label.wider_than_box`, `label.outside_canvas`, `label.mismatch`.
Overlap requires a fixed `canvas_mm`: an auto-growing canvas always fits, which
hides collisions that appear in print.

## Direction
`edge.backward_flow` — a `flow` arrow pointing at the same or an earlier layer.
Cycles are legitimate in mechanisms but must use a type that says so, not the
forward-process arrow a reader will misread.

## Legibility
`font.too_small` (below `min_font_pt`, default 6), `colour.not_cb_safe` (outside
Okabe-Ito — palette membership only, not a contrast measurement).

## Export
`export.no_live_text` (SVG has no `<text>`, so labels are outlines — matplotlib's
default `svg.fonttype` is `path`, which does exactly this), `export.embedded_raster`,
`export.low_dpi`.

## What neither audit covers

- whether the biology is right
- whether the arrow type matches the relation
- aesthetics: balance, whitespace, hierarchy
- anything requiring a gene or pathway database

## Compartments (declared bands, constraint layout)

`compartments[]` declares subcellular bands (id, label, layers, optional colour). The
renderer draws each band behind the boxes and places nodes without an explicit `layer`
into the band they claim — the declared biology constrains the geometry. An explicit
layer that contradicts the band fires `compartment.mismatch` (high); a node naming an
undeclared band fires `compartment.undeclared` (medium).

## Direction refinements

`edge.feedback_unlabeled` — a backward activate/inhibit arrow must be marked
`feedback: true` (a feedback loop, not a layout mistake). `edge.backward_flow` is
suppressed when a flow edge declares `recycle: true`. `edge.dangling` reports a
connection naming an undeclared node instead of silently dropping it.

## Evidence strength and size

`edge.confidence_missing` / `edge.confidence_unknown` fire when
`confidence_required: true`: levels are confirmed/predicted/hypothetical, drawn as
solid/dashed/dotted. `nodes[].size` scales box area; `size.not_positive` reports
non-positive sizes and `legend.size_unexplained` fires when sizes vary while the
required legend explains no size mapping (`legend_notes[]` carries mapping text).

## Malformed entries

`node.malformed`, `edge.malformed`, `compart.malformed`: entries that cannot be drawn
are skipped and reported — one dirty row must not refuse the whole case.
