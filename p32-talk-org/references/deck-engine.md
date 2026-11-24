# talk-org engine map and verification boundary

All runtime code is in this package and uses Python 3.10+ standard library. Rendering/font/imaging
packages are optional accelerators, never import prerequisites.

```
pptxgen.py        editable PresentationML, notes, media, footer/slidenum, visible source bands
 deckaudit.py     final-file evidence, overflow, fonts/glyphs, bounds/overlap, package chain
 extra_rules.py   audience→story→claim→strength→timing→closing→QA→selection rules
 deckbuild.py     the only build CLI; result/plan/evidence/version records and full contract
 decksource.py    preserve-edit real starting decks (shared supporting path)
 templatecheck.py measured real-template application (shared supporting path)
```

`SKILL.md` is the operative workflow and complete spec reference. This file records implementation mechanics
and how the author tests them; it is not a second runtime entry point.

## Story mechanics actually enforced

- `goal` objective/audience/time, optional Q&A reserve; main-slide timing excludes backup/appendix.
- audience prior knowledge/decision/emphasis plan; declared emphasis must map to main roles.
- conclusion titles and one-claim checks; short topic labels and multiple assertion sentences fail independently.
- declared narrative coverage and order; backup roles are exempt from undeclared-role checks.
- final main slide must be a closing/limitation role, with a takeaway that actually lands in that slide.
- explicit threshold/limitation slide and evidence rationale for strength; strong label conflicts with hedging language.
- Q&A topics, duplicate questions, answer-slide bounds and answer evidence pointers.
- kept/omitted selection ledger with source+reason, plus per-slide selection reason when required.
- visible evidence: `require_evidence_on_slide` checks the final slide text, not just metadata JSON.

The rules produce review/blocked findings, not silent rewrites. An agent must change slides, evidence mappings,
or the study design; it cannot edit the audit fields or invent source positions to silence them.

## Artifact mechanics

- Speaker notes are written into a real notes body placeholder. Figures are aspect-fit from file headers without Pillow.
- Every slide with evidence gets a visible caption/source band; if an image caption already contains the exact
  locator, it is not duplicated. The band is separated from body geometry so it cannot silently overlap.
- Footer/Logo/dynamic page fields are real shapes/fields. Template application preserves caption bands by shortening
  only the body's `cy`, never its x/y/width; a template with missing master target is not applied.
- Audit re-reads delivered PPTX XML: claim/caption/evidence landing, notes, CJK width+height overflow, out-of-bounds,
  overlap, explicit-RGB contrast, glyph coverage, fonts, slide→layout→master chain, and repeat-build determinism.
- Content Use, OOXML layout enums, and each OPC part's default namespace are validated by real LibreOffice exports,
  not only XML parsing.

## Verification layers

Legacy coverage is 61 scenarios: 11 deck, 20 talk-rule/CJK/font/master, 7 contract/refusal, 23 focused section guards.
`bench_delivery4.py` adds 17 story/artifact scenarios including the complete clean 5+1 talk and a real source
deck whose visible evidence is deliberately absent. `probe_delivery4.py` adds 27 external CLI probes for all
exit codes, readable refusal JSON, contract field retention, unknown/malformed inputs, idempotency, source
preservation, closing review and audited status precedence.

Run author checks from the package root:

```bash
DECKBUILD_NO_RENDER=1 python -I -X utf8 scripts/bench_deck.py
DECKBUILD_NO_RENDER=1 python -I -X utf8 scripts/bench_deck2.py
DECKBUILD_NO_RENDER=1 python -I -X utf8 scripts/bench_contract.py
DECKBUILD_NO_RENDER=1 python -I -X utf8 scripts/bench_extra.py
DECKBUILD_NO_RENDER=1 python -I -X utf8 scripts/bench_delivery4.py
DECKBUILD_NO_RENDER=1 python -I -X utf8 scripts/probe_delivery4.py
```

Reports are text JSON under `scripts/`, not official platform scores. Temporary PPTX/PNG/PDF artifacts stay
outside the skill package. No binary fixture is shipped.

## Visual/export proof and limits

Run `deckbuild.py` without `DECKBUILD_NO_RENDER`. A real PDF and `%PDF-` header prove an independent office
implementation consumed the package; bytes are recorded. Pixel-level parity is not automatically proven and
should be checked by rasterizing key pages. Without a renderer, only structural/geometry verification is claimed.

The engine cannot read scientific meaning, choose study design, or verify that a cited panel number refers to the
intended experiment beyond the declared evidence map. It cannot simulate every PowerPoint layout engine, complex
group transforms, animation/OLE/SmartArt internals, kerning/ligatures, or target-machine font substitution.
Bitmap figures remain editable pictures, not native chart data. `clean` is a mechanical verdict, not peer review.
