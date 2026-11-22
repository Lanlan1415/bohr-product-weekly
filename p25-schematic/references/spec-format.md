# Spec and checklist format

## `spec.json`

| key | required | meaning |
|-|-|-|
| `nodes[]` | yes | the entities to draw; each needs an `id` |
| `edges[]` | no | the relations to draw; each needs `from` / `to` |
| `canvas_mm` | strongly recommended | `[width, height]` of the journal slot in millimetres |
| `font_size` | no | label size in points, default 9 |
| `min_font_pt` | no | legibility floor used by the audit, default 6 |
| `materials[]` | no | the components the source names; arms `trace.*` |
| `connections[]` | no | the joins the source states; arms `trace.edge_not_in_source` |
| `categories` | no | mapping (category to colour, nodes inherit) or list of category names; arms `colour.category_*` |
| `legend[]` | no | the legend entries the figure must explain; arms `legend.entry_unmatched` |
| `legend_required` | no | with `true`, every drawn label needs a legend entry (`legend.entity_unlisted`) |
| `step_order[]` | no | the order the source text presents steps in; arms `route.numbering_vs_text` |
| `case_id` | no | the case identifier, echoed into `result.json` |
| `output_contract` | no | keys whose values the result must carry; unknown keys become null with a limits note |

All cross-checks are declared-only: without the declaration the rule stays silent, and
the audit never invents a journal parameter or a source number.

### `nodes[]`

| key | meaning |
|-|-|
| `id` | stable identifier; edges refer to it |
| `label` | the text drawn; must match what the source calls the entity |
| `layer` | optional column index. Omit to layer by longest path from the sources |
| `color` | optional hex; prefer an Okabe-Ito value or the audit flags it. Inherited from `categories` when the category declares one |
| `category` | the class the legend / colour mapping explains |
| `evidence` | id of the `materials` item that calls for this node |
| `panel` | optional panel tag (a / b / c); drawn in declared order |
| `stage` | optional step number, checked against `step_order` |
| `italic` | optional; gene symbols are italic by default (`kind: "gene"`) |

### `edges[]`

| key | meaning |
|-|-|
| `from`, `to` | node ids |
| `type` | `activate`, `inhibit`, `bind`, or `flow` (default) |

Edge types are visually distinct on purpose: solid arrow for activation, flat head for
inhibition, dashed for binding, grey arrow for process flow. Using one style for two
meanings is a correctness bug in a diagram, not a style choice — and a `type` that is not
one of the four is reported (`edge.type_unknown`) rather than silently drawn as flow.

## `checklist.json`

This is the extracted truth, written **before** drawing and checked **after**.

| key | meaning |
|-|-|
| `entities[]` | `{id, label, evidence}` — `evidence` is a page/paragraph/figure locator |
| `relations[]` | `{from, to, type, evidence}` |

The audit compares the spec's node and edge sets against these and reports anything
missing (`coverage.incomplete`). Relations whose endpoints are themselves missing are
folded into the missing-entity report instead of being listed twice.

**Do not add to the spec anything that is not in the checklist**, and do not add to the
checklist anything the material does not state. An entity invented to make the layout look
balanced is a fabricated result, which is a scored red line in this contest.
