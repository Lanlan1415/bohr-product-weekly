# template-fit engine map and verification boundary

All scripts are inside this package. Runtime generation requires Python 3.10+ and only the standard library;
optional imaging/font tools and LibreOffice improve coverage but are not import prerequisites.

```
pptxgen.py        real styled PPTX, media, notes, footers, logos, dynamic slidenum
 decksource.py    preserve-edit and explicitly requested whole-source batch format
 templatecheck.py measured/applied master-layout-theme, native placeholders, OPC output
 deckaudit.py     final slide evidence, overflow, bounds, overlap, contrast, package chains
 extra_rules.py   template-specific type ladder, layout/font/title/body drift, content dropped
 deckbuild.py     the only build CLI; final artifact and full case/result records
```

`SKILL.md` is the operative workflow and parameter reference. This file prevents the historically separate
`templateread.py`/fixture documentation from being mistaken for the current production route. Current template
application uses `templatecheck.py`; old `templateread.py` is retained as a reusable layout-reading utility for
legacy measurements, not as the `deckbuild.py` entry point.

## Actual mechanisms

- Master/layout/theme dependencies are copied and slide→layout relationships are reconnected. The selected
  layout's title/body placeholders supply native type/index, geometry, size, bodyPr and theme styling.
- Layout-level missing geometry is inherited only from the same actual placeholder on its existing master.
  Missing master targets and duplicate aliases are never hidden by selecting the first match silently.
- Batch formatting is opt-in. It replaces old workflow footers/page fields/Logo (both `p:sp` and `p:pic`)
  before adding exactly one set per slide; `footer:false` preserves existing elements. Logo is one shared media part.
- Colors and type ladders are read back from the delivered deck. Real template colors can correct stale declared
  colors without leaving a false mismatch. The final layout—not the input spec's superseded 24/20 values—decides.
- Every OPC part is serialized with the appropriate default namespace per write. ContentTypes and package
  relationships do not share one global default registration because ElementTree replaces the previous mapping.
  Valid OOXML layout type values are used; XML acceptance alone is never treated as Office validation.

## Verification layers

Legacy suites cover 70 scenarios: `bench_deck.py` 11, `bench_deck2.py` 13, `bench_template.py` 18,
and `bench_extra.py` 28. They retain clean/no-file false-positive guards, CJK measurements, template relationships,
and malformed artifact injection.

`bench_delivery4.py` adds 12 artifact scenarios: renderer-proven two-layout template, theme correction, title-size
and canvas correction, source batch footer/Logo/style, combined batch+template, footer opt-out, body drift,
missing logo and a required placeholder failure. It asserts actual placeholder XML, dynamic field counts,
shared media, real colors/font sizes/canvas and preserved package parts.

`probe_delivery4.py` adds 27 real external CLI probes for exit codes 0/3/4/5, readable result JSON, traceback-free
refusal, complete case/output_contract retention, unknown shapes, malformed decks/templates, repeat determinism,
real source batch and real native template application.

Run all author checks:

```bash
DECKBUILD_NO_RENDER=1 python -I -X utf8 scripts/bench_deck.py
DECKBUILD_NO_RENDER=1 python -I -X utf8 scripts/bench_deck2.py
DECKBUILD_NO_RENDER=1 python -I -X utf8 scripts/bench_template.py
DECKBUILD_NO_RENDER=1 python -I -X utf8 scripts/bench_extra.py
DECKBUILD_NO_RENDER=1 python -I -X utf8 scripts/bench_delivery4.py
DECKBUILD_NO_RENDER=1 python -I -X utf8 scripts/probe_delivery4.py
```

Reports are text `scripts/report_*.json`, not official platform scores. Test PPTX/PNG resources stay in temporary folders.
`make_template.py` is a reproducible demo artifact builder, not a source of official answers or a bundled binary.

## Visual/export proof

Run `deckbuild.py` without `DECKBUILD_NO_RENDER`. When LibreOffice is available, real PDF conversion proves that
both OPC and PresentationML relationships can be consumed by an independent implementation. PDF bytes and the
`%PDF-` header are recorded, but pixel parity requires additional rasterization/inspection. Without a renderer,
only structural XML/glyph/geometry checks are claimed.

Scientific reading, source-value accuracy and citation semantics remain the agent's responsibility. Picture locations
are editable but raster internals do not become native chart datasets. Complex group transforms, animations,
OLE/SmartArt internals and target-machine font substitution are outside full simulation and are listed as limits.
