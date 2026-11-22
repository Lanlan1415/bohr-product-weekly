# Layout and export rules (shared)

Identical to the schematic engine; see `scripts/schematic.py`.

| rule | severity | meaning |
|-|-|-|
| `coverage.incomplete` | high | an entity/relation from the checklist is absent |
| `label.overlap` | high | two labels collide (needs a fixed `canvas_mm`) |
| `label.wider_than_box` | medium | a label is wider than its own shape |
| `label.outside_canvas` | high | a label is clipped by the figure edge |
| `label.mismatch` | high | drawn label ≠ spec label |
| `edge.count_mismatch` | high | connectors drawn ≠ specified |
| `edge.backward_flow` | medium | a flow arrow runs backwards relative to layout |
| `edge.zero_length` | high | connected nodes landed on the same point |
| `entity.duplicate` | medium | two nodes share label and colour |
| `font.too_small` | medium | below the legibility floor |
| `colour.not_cb_safe` | low | outside the Okabe-Ito palette |
| `export.no_live_text` | high | SVG has no `<text>`; labels are outlines |
| `export.embedded_raster` | medium | SVG embeds a raster |
| `export.low_dpi` | medium | preview below 300 dpi |

## Note on overlap detection

`label.overlap` is only meaningful with a fixed `canvas_mm`. The renderer grows
the canvas to fit by default, which hides every collision that would appear once
the figure is placed in a journal column. The apparatus and roadmap examples both
declare a canvas for exactly this reason.
