# Fonts, layout and export verification

## Glyph coverage before rendering

Matplotlib commonly defaults to DejaVu Sans, which lacks CJK glyphs. A valid PNG
can therefore contain rows of empty boxes without raising an exception.

The resolver checks every character the figure will actually draw: node labels,
core message, role/result labels, steps, visual values, n/uncertainty notes, edges,
caption and limitations. It prefers Microsoft YaHei, Noto Sans SC, SimHei, Source
Han Sans, SimSun/DengXian/WenQuanYi, then DejaVu Sans. A font covering Chinese can
still miss µ, λ or a symbol; the exact missing characters are reported.

`font.family/path` and `missing_glyphs` are written to result.json. The CLI never
silently claims that an unresolved character was rendered correctly.

## Physical layout checks

The narrative is a single-page, left-to-right chain: question/input → method →
result/mechanism → bounded conclusion, with source scope beneath it. Main labels
are wrapped to fit their cards without changing tokens. Auxiliary labels are also
checked for canvas bounds and font floor. Long result notes are kept on one line
and checked against card width; move extended detail to caption instead of
stacking tiny text.

Result values sit outside error bars, bars share a zero baseline, and direct
labels/hatches/role text make colour a redundant channel. Conclusion arrows are
above the card layer so connectors cannot disappear behind a white box.

## Artifact checks

| Artifact | Actual check |
|-|-|
| `figure.svg` | XML parsing; live `<text>`; no embedded raster; title/desc; role=img; font-family |
| `figure.png` | non-empty PNG signature, declared dpi >= 300 and physical pHYs dpi >= 299 |
| `figure.pdf` | non-empty `%PDF` output from the same rendered canvas |
| `caption.txt` | declared caption plus source scope/limitations |
| `resolved_spec.json` | all actual declarative content needed to regenerate the figure |
| `change_records.json` | present for edits: field-level before/after values |

Empty/short artifacts, malformed XML, outlined labels and invalid PNG/PDF are
findings; a file extension by itself proves nothing.

## Determinism

Two renders compare text and geometry. In addition, wall-clock SVG/PDF metadata
is removed, PNG software metadata is fixed, and Matplotlib's generated definition
ids are canonicalised while preserving references. Runtime probes therefore can
and do compare the actual result.json/SVG/PNG/PDF/caption/spec/change records
byte-for-byte across repeated runs.

If matplotlib/numpy/Pillow cannot be imported, the standard-library JSON path
writes `undetermined`, `audit.no_section`, exit 5 and an explicit limit: no
SVG/PNG/PDF is claimed. It does not fabricate an artifact in a no-render runtime.
