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

Fourteen scenarios in `bench_extra.py` cover the per-skill sections:

```
paper_to_deck  paper.figure_unattributed, paper.caption_missing
deck_edit      edit.change_without_reason, edit.change_is_noop
talk_org       org.goal_missing, org.claim_is_topic,
               org.evidence_strength_missing, org.pace_too_fast
template_fit   format.size_ladder_flat, format.undeclared_layout
                                            14/14 pass
```

Every clean baseline must report no high or medium finding, so a detector cannot
pass by flagging everything. Run both with:

```bash
python scripts/bench_deck.py
python scripts/bench_extra.py
```

These are author-side checks. Producing a deck needs only `deckbuild.py`.

## What the engine cannot do

- It cannot judge the story. It can prove a slide is untraceable; it cannot tell
  you the argument is in the wrong order.
- It cannot predict font substitution. If the declared typeface is missing on the
  target machine, metrics change and the overflow verdict is wrong.
- It cannot see inside a picture. A gap axis inside a rasterised chart is invisible.
- It cannot validate against a real journal template, because it does not ship one.
