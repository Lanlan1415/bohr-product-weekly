# The shared deck engine

Four slides-track skills share one measured engine. That is deliberate: four
reimplementations of "does this text fit its box" would give four different
answers to one question, and the answer would stop meaning anything.

```
scripts/pptxgen.py     write a real .pptx with the standard library only
scripts/deckaudit.py   read the written file back and audit it
scripts/deckbuild.py   spec -> deck -> audit -> result.json
scripts/extra_rules.py the one section that makes this skill distinct
```

## Why the generator has no dependencies

The pinned evaluation image lists the tools it provides, and `python-pptx` is not
among them. A skill that imports it fails at import time and produces no deck at
all. So `pptxgen.py` writes PresentationML directly with `zipfile` and
`xml.sax.saxutils`, and reads PNG/JPEG dimensions from their headers with
`int.from_bytes`.

The output is a genuine package — one master, one layout, one theme, one slide
part per slide — and it was verified by opening the generated files with
`python-pptx` in an environment where that library *is* available:

```
slides 2 | size 12192000 x 6858000
has_notes True | notes: Pause here; the key contrast is rate.
```

That is the useful form of a self-check: an independent implementation agrees the
file is a valid presentation.

## Why the audit reads the file, not the spec

Checking the spec only restates the spec. `deckaudit.py` unzips the `.pptx` and
parses each `slideN.xml`, so a renderer that drops a font size, misplaces a box, or
loses the notes placeholder is caught. Two defects in this engine's own history
were found exactly this way:

1. **Speaker notes were written into a plain text box**, so `python-pptx` reported
   `notes_text_frame is None` and PowerPoint showed an empty notes pane. Notes
   must live in the body placeholder (`ph type="body"`); the placeholder identity
   is what makes them speaker notes.
2. **Images were forced into a fixed 4.6×3.4 in slot regardless of source aspect**,
   which stretched every non-1.35 figure. The generator now fits-and-centres, and
   `image.aspect_distorted` catches the case when a deck arrives from elsewhere.

## Text measurement

Overflow is decided by measuring glyph widths from a real font file (DejaVu Sans
via matplotlib, or a system TTF), wrapping into the actual box width, and comparing
against the box height minus insets. When no font file can be found the check
degrades to a per-character estimate and `checked.note` says so — the number is
then approximate and is reported as approximate.

CJK glyphs are counted at full em width, ASCII at the font's measured advance.

## Measured behaviour

Eleven scenarios in `bench_deck.py`, one planted defect each, every one writing a
real `.pptx` and re-reading it:

```
clean, too_many_bullets, font_too_small, overflow, no_title,
evidence_missing, evidence_unsupported, notes_missing,
aspect_distorted, no_alt_text, term_inconsistent
                                            11/11 pass
```

Sixteen scenarios in `bench_deck2.py`: the revision record (slide, reason, complete
before/after pair or deletion snapshot, in-range slide, delivered revision, and the
record checked against the written deck through the full build), CJK overflow
measurement, and five scenarios that patch a real written package — a lost layout
relationship, two masters behind one deck, a declared embedding the package does not
carry, plus the false-positive guards for each:

```
clean, no_reason, no_slide, noop_change, revision_empty,
record_not_applied, overflow_cjk, term_drift,
font_missing, missing_glyphs, nondeterministic,
master_broken, master_shared_fp, master_inconsistent, embed_missing,
embed_fp_embedded
                                            16/16 pass
```

Twenty-seven scenarios in `bench_extra.py` cover the per-skill sections; every
defect ships with the false-positive guard that proves correct practice stays
silent (Lesson 6):

```
paper_to_deck  paper.figure_unattributed, paper.caption_missing
deck_edit      edit.change_without_reason, edit.change_is_noop,
               edit.change_half_diff, edit.change_slide_out_of_range,
               edit.delete_without_snapshot, edit.delivered_revision_missing,
               edit.change_not_in_deck — each with its declarative guard
talk_org       org.goal_missing, org.claim_is_topic,
               org.evidence_strength_missing, org.pace_too_fast
template_fit   format.size_ladder_flat, format.undeclared_layout
                                            27/27 pass
```

Thirteen scenarios in `bench_edit3.py` cover the polish-pass additions: the page
budget (deck.empty_deck, deck.slide_count_over_limit), the round record
(edit.revision_instruction_missing), defensive typing (mistyped spacing builds
with the coercion named in limits), the output_contract echo (case_id plus every
declared field carried into result.json — audit-derived fields keep the audited
values, spec-carried values pass through verbatim, the rest become null with a
limits note), and the refusal path (bad JSON / non-object / missing file → an
undetermined result.json and exit code 5, never a traceback):

```
clean, empty_deck, slide_over_limit, slide_within_limit_fp,
instruction_missing, mistyped_spacing, slides_wrong_type,
contract_passthrough, refused_bad_json, refused_not_object,
refused_missing_file, refused_case_id_kept, exit_code_undetermined
                                            13/13 pass
```

Every clean baseline must report no high or medium finding, so a detector cannot
pass by flagging everything. Run all four with:

```bash
python scripts/bench_deck.py
python scripts/bench_deck2.py
python scripts/bench_extra.py
python scripts/bench_edit3.py
```

These are author-side checks. Producing a deck needs only `deckbuild.py`.

## What the engine cannot do

- It cannot judge the story. It can prove a slide is untraceable; it cannot tell
  you the argument is in the wrong order.
- It cannot predict font substitution on a machine it has not seen. It checks the
  declared typeface here, the glyphs of the text here, and — when the spec declares
  `embed_fonts: true` — that the package really carries embedded fonts. If the
  target machine lacks the face and nothing is embedded, the deck still reflows.
- It cannot see inside a picture. A gap axis inside a rasterised chart is invisible.
- It cannot validate against a real journal template, because it does not ship one.
