# Nomenclature rules: biology-specific entity hygiene

These checks exist because a pathway figure's most damaging errors are textual,
not graphical. The picture can be immaculate and still claim the wrong organism.

## Casing conventions

| species | convention | example |
|-|-|-|
| human | all upper case | `TP53`, `BRCA1`, `CDKN1A` |
| mouse / rat | first letter upper, rest lower | `Tp53`, `Brca1`, `Cdkn1a` |
| zebrafish | all lower case | `tp53` |
| yeast | all upper case | `TP53` |

`species` must be declared for strict checking. Without it, the audit only reports
**mixed conventions** — human-style and rodent-style symbols in one figure — which
is the symptom a reader actually notices.

**What this cannot do:** confirm a symbol exists. `Tp53` in a *mouse* panel is
correct and passes. `XYZZY1` in a human panel is well-formed and also passes. A
gene database is a different dependency, and pretending to have one would make
this check worse than useless.

## Italic convention

- gene symbols → **italic**
- protein names → roman
- complexes, metabolites, cell types → roman

The renderer sets italic from `kind` (`gene` → italic). An explicit `italic`
overrides it. The audit reads the **exported SVG** and checks whether the text
element actually carries `font-style: italic`, so a renderer that drops style is
caught rather than trusted.

## Alias collisions

Given `"aliases": {"TP53": ["Tp53", "p53", "BCC7"]}`, the audit maps every listed
form to the canonical name. If two different nodes resolve to the same canonical
entity, that is a high-severity finding: the figure shows two actors where the
source described one, which invents a step in the mechanism.

This is the single most valuable rule in the module, and it is entirely dependent
on the alias map being built from the source material rather than from memory.

## Accessions

Every gene or protein node should carry an identifier plus its source:

| source | format | example |
|-|-|-|
| `hgnc` | `HGNC:<digits>` | `HGNC:11998` |
| `uniprot` | 6- or 10-character accession | `Q00987`, `P04637` |
| `ensembl` | `ENS[GTP]...` | `ENSG00000141510` |
| `ncbi_gene` | numeric | `7157` |
| `chebi` | `CHEBI:<digits>` | `CHEBI:15377` |

A malformed accession is almost always a copy error, and it makes the entity
unresolvable in exactly the way the accession was meant to prevent. An accession with a
missing/unsupported registry fires `nomenclature.accession_source_unknown` rather than
receiving a false pass. Two actor nodes sharing one supported registry accession fire
`nomenclature.accession_collision`; genuine post-translational states are an explicit FP
guard only when both nodes set `state_distinct: true` and provide different `state` values.

## Vague entities

A blocklist of process words used as nodes: `signaling`, `pathway`, `cascade`,
`mechanism`, `response`, `regulation`, `activation`, `通路`, `信号`, `级联` and
similar. Drawing a verb as a box claims an entity the source may not define.

Deliberately a blocklist and not an NLP classifier: it is a nudge toward naming
the actual actors, not a proof of error. A figure legitimately labelled "signalling
cascade" as a *region* rather than a node should use a group label instead.
