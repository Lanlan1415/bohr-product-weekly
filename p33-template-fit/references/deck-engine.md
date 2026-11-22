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

Overflow is decided by measuring glyph widths from a real font file, wrapping into
the actual box width, and comparing against the box height minus insets. The rungs,
in order: Pillow's raster (when installed), the standard-library TrueType reader
(`fontmetrics.py`: cmap + hmtx + head, also inside TTC collections), and only then a
per-character estimate — with `checked.text_measured` reporting which rung produced
the number, and `checked.note` saying so when the number is approximate.

Glyph coverage (`export.missing_glyphs`) now always runs on the standard-library cmap
reader; its verdicts match `matplotlib.ft2font.get_char_index` exactly on every system
font cross-checked (arial, msyh.ttc, simhei, calibri, times), and "no font file could
be read" is a distinct `measured=False` state that becomes a limit, never a false
"all characters missing" block.

CJK glyphs are counted at full em width, ASCII at the font's measured advance; line
breaking treats each CJK character as a break opportunity, so a Chinese paragraph can
no longer measure as one unbreakable token.

## The template is measured (round 2)

`templateread.py` opens a declared `.potx`/`.pptx` with `zipfile` and reads what the
package actually provides: layout names and types from `slideLayouts/*.xml`
(`cSld name` / `type`), theme typefaces from `theme1.xml`'s font scheme, title
placeholder geometry and declared run size per layout, slide size from
`presentation.xml`, and the master chain behind each layout. The `template.*` rules
compare the written deck against those measurements; `deckbuild` echoes a
`template_measured` object into result.json so a reviewer can verify
"母版、版式、占位符继承关系可查" without PowerPoint. When no template file is named,
all of it stays silent — the declarative checks are unchanged.

## Measured behaviour

Eleven scenarios in `bench_deck.py`, one planted defect each, every one writing a
real `.pptx` and re-reading it (fixtures generated with the standard-library PNG
writer, so the bench itself has no imaging dependency):

```
clean, too_many_bullets, font_too_small, overflow, no_title,
evidence_missing, evidence_unsupported, notes_missing,
aspect_distorted, no_alt_text, term_inconsistent
                                            11/11 pass
```

Twenty-eight scenarios in `bench_extra.py` cover the per-skill sections, every
defect carrying its false-positive guards:

```
paper_to_deck  paper.figure_unattributed, paper.caption_missing
deck_edit      edit.change_without_reason, edit.change_is_noop, ...
talk_org       org.goal_missing, org.claim_is_topic,
               org.evidence_strength_missing, org.pace_too_fast
template_fit   format.size_ladder_flat, format.undeclared_layout,
               format.font_drift, format.title_drift,
               format.content_dropped (+ FP guards)
                                            28/28 pass
```

Nine scenarios in `bench_template.py` prove the measured-template rules on a real
`.potx`-shaped package built by the bench itself, with clean/no-file FP guards:

```
clean, no_file, layout_not_found, theme_font_mismatch, title_size_off,
slide_size_mismatch, template_unreadable, title_geometry_drift,
template_measured_echo                     9/9 pass
```

Every clean baseline must report no high or medium finding, so a detector cannot
pass by flagging everything. Run them with:

```bash
python scripts/bench_deck.py
python scripts/bench_extra.py
python scripts/bench_deck2.py
python scripts/bench_template.py
```

These are author-side checks. Producing a deck needs only `deckbuild.py`.

## What the engine cannot do

- It cannot judge the story. It can prove a slide is untraceable; it cannot tell
  you the argument is in the wrong order.
- It cannot predict font substitution. If the declared typeface is missing on the
  target machine, metrics change and the overflow verdict is wrong.
- It cannot see inside a picture. A gap axis inside a rasterised chart is invisible.
- It cannot validate against a real journal template, because it does not ship one.
