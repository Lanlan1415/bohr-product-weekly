# Unit model and rule semantics

## Why a dimension model instead of a lookup table

A lookup table of `("mV","V") -> 0.001` pairs cannot reject `mg -> mm`. Tracking
seven base exponents (mass, length, time, current, temperature, amount, luminous)
lets the engine refuse a conversion that would be silently meaningless, which is
the whole point.

| unit | dimension | factor to SI base |
|-|-|-|
| `g` | mass | 1e-3 (SI base is kg) |
| `L` | length³ | 1e-3 |
| `M` | amount · length⁻³ | 1e3 (mol/L → mol/m³) |
| `eV` | mass · length² · time⁻² | 1.602176634e-19 |
| `bar` | mass · length⁻¹ · time⁻² | 1e5 |

Molar is `amount/volume`, not `mass/volume`. Defining it as mass concentration
makes `mol/L` and `mM` look like different quantities, and the conversion then
fails — which is how that bug was found, by the engine refusing its own table.

## Compound units

`mol/L`, `mg/mL`, `J/s`, `mg*kg` resolve by splitting on `/` and `*` and combining
dimension vectors, with a recursion depth bound. Anything stranger (`W/(m^2·K)`)
returns unrecognised and is reported by name. A guessed compound unit would be a
wrong number; a refused one is a visible gap.

## Refusals, and why they are the feature

| case | outcome |
|-|-|
| `mg` → `mm` | `dimension_mismatch`, with both dimension vectors |
| `psi` → `Pa` | `unknown_unit`, named |
| `degC` → `K` | `special_unit`, because a temperature *offset* is not a multiplier |
| `%` → `%` | identity (not a multiplicative conversion, but not an error) |

Each refusal appears in `changes[]` with the source cell, so the reviewer sees the
gap rather than a plausible number.

## Measurement kinds

`parse_measurement` returns `single`, `plus_minus`, `range`, `not_reported` or
`unparsed`. The last two are distinct on purpose:

- `not reported` is a **fact about the paper** and becomes a missing value.
- `about 5 mM` is **hedged**; parsing it as 5 discards the hedge, which is part of
  the claim being recorded.

## Idempotence

`idempotent` is computed by running the rules twice and counting *value rewrites*
on the second pass. Diagnostics (missing, unparsed, out-of-range) recur on every
pass by design, so counting them would report a rule conflict where there is only
an unfixed gap.

A `false` verdict means two rules disagree about the same cell, and the priority
order needs fixing — it is a high-severity finding, not a warning.

## What the rules deliberately do not do

- no averaging or imputation
- no deletion of out-of-range values (they are flagged and kept)
- no unit inference from magnitude
- no merging of same-entity rows with different values

## Field mapping and synonyms (R10 / R11)

The rubric's breakthrough directions name field mapping and synonym normalisation
explicitly, so both are engine rules, not prose:

- spec.field_aliases maps a source column name to its canonical name
  (`{"bg": "bandgap"}`). The rename is recorded in the ledger under R10 with the
  row, the old and the new column name; the value itself never moves. A column
  present in the rows but neither declared nor aliased is listed in
  result.unmapped_columns (finding clean.unmapped_columns) — the unmapped-fields
  list the rubric asks for.
- spec.synonyms maps normalised spellings to a canonical entity name
  ({"titanium dioxide": "TiO2"}). It changes only the key the duplicate census
  groups by; cells stay untouched. A spelling outside the table is listed in
  result.duplicates.synonym_unmapped (finding clean.synonym_unmapped) — merging
  across it stays a human decision. An absent or empty synonyms key disables the
  unmapped census entirely, so declaring nothing never flags every spelling.

## Provenance and the to-confirm list

- spec.source_column (e.g. "study") stamps every ledger entry and every duplicate
  entry with that row's source value; result.provenance lists the source values
  seen. An edit is then traceable past the row index to the record's origin.
- result.pending_review is the deliverable a reviewer reads first: unparsed cells,
  refused conversions, out-of-range values, duplicate experiments and unmapped
  entity spellings, each with its row and reason. The engine never decides these
  by itself; the list is capped at 500 entries with a truncation marker.

## Structured rewrites (ranges and error bars)

A range converts both endpoints and is written back as a range
("3.0-3.4 eV" -> "3000-3400 meV"); a plus-minus converts value and error together
("12±0.5 mV" -> "0.012±0.0005 V"). Converting only the low endpoint would silently
replace an interval with a point. When source and target unit match, the cell is
left verbatim — no re-serialisation, so "3.20 eV" keeps its trailing zero and the
cleaned cell always equals the ledger's recorded "new".

## Refusals at the CLI layer

An unrunnable case is refused with exit 5 and a written result file, never a
traceback: missing or unreadable spec (clean.spec_unreadable), non-object spec,
rows that are not a list, zero record rows (clean.no_rows), no rows and no table
path (clean.no_table), and a table file that is missing, unreadable or not
decodable text (clean.table_unreadable). Refusal results carry no contract echo:
echoing an output contract into a refused run would dress the refusal up as a
completed case.
