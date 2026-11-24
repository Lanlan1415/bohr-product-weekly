# deck-edit engine map and author verification

All paths below are inside this package and require Python 3.10+. Runtime generation uses only the
standard library; optional Pillow/matplotlib and office rendering improve measurement/export but are not import requirements.

```
pptxgen.py       styled PresentationML, figures, notes, footers, logos, dynamic slide numbers
 decksource.py   preserve-edit a source OPC package; DrawingML text/geometry/style actions
 templatecheck.py measure/apply real master/layout/theme and native title/body placeholders
 deckaudit.py    re-read slides: evidence, notes, fonts, CJK overflow, bounds, overlap, contrast
 contract_echo.py case identity and all output_contract fields, including readable-case refusal
 deckbuild.py    the only build CLI: spec -> final PPTX/PDF -> audit -> JSON records
```

The implementation-specific runtime workflow, source-edit actions, fields and limitations are documented
in `SKILL.md`. This reference is an author map, not another runtime entry point.

## Reference mechanisms actually implemented

- PptxGenJS-style TRBL margins, master/layout relationships, `bodyPr`, `solidFill` and dynamic
  `p:ph type="sldNum"` + `a:fld type="slidenum"`. Its source does not provide a general off-slide or
  text-overflow audit; this package implements those itself.
- python-pptx-style placeholder identity and layout/master inheritance. Native title/body placeholders
  retain type/index. Speaker notes occupy a body placeholder rather than a plain slide text box.
- reveal.js-style fixed-canvas layout and intrinsic-aspect media fitting. No HTML output is produced.

No third-party source or binary is bundled. The target package contains the implementations, not links alone.

## Regression set

Legacy suites cover 67 scenarios:

- `bench_deck.py`: 11 generation/audit scenarios, with a clean guard and real PPTX artifacts;
- `bench_deck2.py`: 16 revision, CJK, font, glyph, master and deterministic-build scenarios;
- `bench_edit3.py`: 13 page-budget, contract and structured-refusal scenarios;
- `bench_extra.py`: 27 focused rule and false-positive guards.

New artifact and hostile suites:

- `bench_delivery4.py`: 11 styled/source/template artifact scenarios, including byte comparison of
  the real applied master, dynamic page fields, low contrast, overlap, out-of-bounds and blank slides;
- `probe_delivery4.py`: 26 actual CLI probes for exit codes 0/3/4/5, result JSON, traceback absence,
  case/field passthrough, malformed inputs and repeat-build idempotency.

Run author checks from the package root:

```bash
DECKBUILD_NO_RENDER=1 python -I -X utf8 scripts/bench_deck.py
DECKBUILD_NO_RENDER=1 python -I -X utf8 scripts/bench_deck2.py
DECKBUILD_NO_RENDER=1 python -I -X utf8 scripts/bench_edit3.py
DECKBUILD_NO_RENDER=1 python -I -X utf8 scripts/bench_extra.py
DECKBUILD_NO_RENDER=1 python -I -X utf8 scripts/bench_delivery4.py
DECKBUILD_NO_RENDER=1 python -I -X utf8 scripts/probe_delivery4.py
```

Reports are `scripts/report_*.json`. Temporary PPTX/PNG assets are generated outside the package.
These author benches are not part of the numbered runtime workflow and cannot certify scientific meaning.

For visual smoke, run `deckbuild.py` without `DECKBUILD_NO_RENDER`. If LibreOffice is installed, the
engine discovers it on PATH or standard install locations and writes a real PDF. A valid PDF header and
non-empty bytes are recorded, but pixel parity requires separate rasterization/inspection. Without a
renderer, `preview.rendered=false` and explicit slide geometry checks remain; no visual claim is made.

## Scope boundaries

- Source editing covers DrawingML text and explicitly named shape geometry/style, not animation/OLE internals.
- Real template application covers master/layout/theme, title/body placeholders and their measured geometry.
- Overflow uses real glyph advance widths when available and CJK breaking; kerning/ligature and application
  auto-layout are not simulated fully. Inherited shapes without explicit geometry are not treated as zero-sized.
- Pictures remain editable objects but do not become native chart datasets. Scientific reading and citations
  require the agent to return to the source material; a clean mechanical audit is not scientific approval.
