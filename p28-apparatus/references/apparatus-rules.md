# Apparatus and roadmap rules

## Why these two figure types get their own audit

The shared layout audit asks "is this drawn correctly". It cannot ask "does this
apparatus show every part" or "can this route be followed", because those
questions need to know the figure *is* an apparatus or a route. That is what
`figure_kind` declares.

## Apparatus rules

### `apparatus.component_missing`
The spec may carry a `components` list — the bill of materials, extracted from
the methods. Every entry must appear as a node label (case-insensitive). A part
that is named in the text and absent from the drawing is the most consequential
error an apparatus figure can make: the reader concludes the experiment did not
use it.

### `apparatus.indistinguishable_components`
Two nodes with the same label **and** the same colour are indistinguishable. The
finding is medium rather than high because identical parts sometimes *are*
interchangeable in the drawn abstraction — but then the author must say so with
`"grouped": true`. Supplying an `instance` field (`"A"`, `"B"`) also resolves it,
and usually should be surfaced in the label too.

### `apparatus.orphan_component`
A node with no edge. In a real apparatus nothing floats, so an orphan is almost
always a leftover from an earlier layout. Reported as medium: a legend-only or
annotation node is a legitimate exception.

## Roadmap rules

### `route.stage_duplicate` / `route.stage_gap`
Stage numbers must be unique and contiguous. A gap is medium because a protocol
genuinely can skip a stage; the finding asks for an explanation rather than
demanding renumbering.

### `route.decision_without_branches`
A node with `kind: "decision"` needs at least two outgoing edges. A decision with
one path is not a decision — it is a step wearing a diamond.

### `route.no_entry` / `route.no_exit`
In a directed graph, a node with no incoming edges is a start and one with no
outgoing edges is an end. A cyclic protocol has neither, so both fire together;
that combination is deliberate and is exercised by the `no_exit` benchmark
scenario. In that case the fix is an explicit start marker, not renumbering.

## Deliberately out of scope

- **Pictograms.** A pump drawn as a pump communicates mechanism this engine cannot
  know. An honest labelled box beats an invented symbol.
- **Port alignment and mating geometry.** "Interface alignment" implies physical
  surfaces; only connection topology is checked.
- **Scale and proportions.** A 10 cm part and a 1 m part are the same box size.
- **Timeline axes.** A roadmap with real durations needs a time axis; `stage` is
  ordinal only.
