# Encoding spec and validation

## Channel-to-column model

Values belong in the data table, not hand-copied into the spec. `encoding.y = "response"`
retains the source relationship; `encoding.y = [12.4, 31.2]` does not. `field_types` records
nominal/ordinal/quantitative/temporal inference evidence. Automatic mode writes a resolved spec and
then follows the same validation path as explicit mode.

Supported kinds are `bar`, `line`, `scatter`, `box`, `heatmap`, and `histogram`. Channels are
`x`, `y`, `value`, `group`, `x_err`, and `y_err`, but only where meaningful:

| kind | required | numeric requirements and layout |
|-|-|-|
| bar | x,y | y (and optional y_err) numeric; stable x category order and dodged groups |
| line | x,y | x,y numeric; rows sorted by numeric x within each series |
| scatter | x,y | x,y numeric; missing coordinates stay undrawn, never become row numbers |
| box | x,y | y numeric; x×group boxes with visible raw observations |
| heatmap | x,y,value | value numeric; x/y can be categories; no group channel |
| histogram | x | x numeric; optional group; y is derived Count and must not be mapped |

`x_err` is supported for line/scatter; `y_err` for bar/line/scatter. Unknown channels or channels
that do not fit the kind are refused. `y2`, `secondary_y`, `right_y`, and `twinx` are refused as
`encoding.dual_axis_unsupported` rather than silently ignored.

## Validation order

1. Chart kind and empty table (`data.no_rows`).
2. Encoding object, required channels, unsupported dual axes/channels.
3. Every mapped column exists. CSV duplicate headers and rows wider than the header are rejected.
4. Required numeric channels must parse all non-missing values. Blank/NULL tokens remain missing;
   other text is not converted to zero.
5. Bar and heatmap category/series keys must be unique. Duplicate keys would overlap and therefore
   produce `data.duplicate_marks`; aggregate explicitly or choose box/scatter.
6. Only then are dependencies and rendering attempted.

Unknown kinds and invalid plans return `refused` with exit 5. Unreadable spec/data, missing
matplotlib/numpy, or a render failure return `undetermined` with exit 5. Both produce result.json;
readable specs retain case_id and all output_contract keys, including null+limits for unknown values.

## Rendering and derived transformations

- **bar**: each bar records source row and actual centre/height. It is not valid to infer aggregate
  means from repeated rows implicitly.
- **box**: the statistical box is derived by matplotlib, while every source observation is overlaid
  and mapped to its real display coordinate and value.
- **line/scatter**: source rows retain x_err/y_err and actual x/y artist values. Log scales and
  declared limits are applied before the clipping checks.
- **heatmap**: absent cells are NaN gaps. Duplicate cells are refused. A declared colour range and
  value unit are checked; out-of-range values cannot be silently pinned to the palette ends.
- **histogram**: `bins` defaults to 10, or strictly increasing `bin_edges` can be supplied. Shared
  edges across groups, member rows, counts, and bin assignments are returned in `aggregates` and
  `mark_to_row`. Histogram observations do not pretend to have one artist per source row.
- **labels**: title, wrapped caption, axis/colorbar labels and units are really rendered. Caption
  contains declared n or the more cautious source-row count, plus uncertainty semantics where used.

## Presentation and accessibility

Okabe-Ito colour is paired with hatches (bar/box), dashes (line/histogram), and markers
(scatter/box/line), plus text legends. SVG embeds role=img, title and description. These are
machine-checkable accessibility mechanisms, not a claim that a person visually inspected every plot.

`figsize`, `dpi`, and `export.width_mm` affect the real canvas. Caption wrapping uses actual figure
width, followed by a renderer bounding-box check for title, x/y labels, and caption. Any text outside
the canvas is `layout.text_overflow` (high). Exports retain live SVG text and are checked for file
size, PNG pHYs resolution, PDF signature, and actual width.

## Status and exit codes

| status | exit | meaning |
|-|-|-|
| clean | 0 | no findings |
| review | 3 | only low/medium findings |
| blocked | 4 | rendered, but a high finding prevents unqualified delivery |
| refused | 5 | rejected before rendering |
| undetermined | 5 | execution capability/input could not be determined |

The engine writes structured failures, not tracebacks. Missing CLI arguments themselves remain an
argparse usage error (2). Significance group declarations are validated but no brackets are drawn;
that limitation is explicit. No SD/SEM/CI, statistical test, correlation matrix, or scientific
conclusion is invented from a table merely to make the result look complete.
