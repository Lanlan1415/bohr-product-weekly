---
name: file-search
description: >
  Search an actual research file tree with hard boolean/metadata filters,
  Unicode-safe CJK tokenization, field-weighted BM25 and explainable
  body+metadata rank fusion. Returns section/page/paragraph/character locators
  with verbatim quotes, source/document hashes, rank reasons, duplicate-evidence
  groups, top-tie ambiguity and diagnostic no-result states. Builds a real
  coverage report for unindexed files; never invents OCR, synonyms, metadata or
  relaxed filters. Supports raw directories, JSON corpora and saved indexes.
  Use for in-library retrieval and evidence backlinks, not open-web discovery.
---

# 科研文件智能检索

## Implemented retrieval path

The primary entry point is `scripts/search_cli.py --root`. It performs:

`actual files → original-byte hashes + extraction coverage → paragraph/section
index → exact boolean/filter gates → BM25/body + BM25/metadata → weighted rank
fusion → checkable evidence`.

| Capability | Actual behavior |
|---|---|
| Full text + metadata | Body and headings form the body channel; title, source path and declared metadata form the metadata channel. Title and metadata-only hits are valid and carry `field_matches` |
| CJK boundaries | Contiguous Unicode codepoint unigrams/bigrams for scoring; no grams cross punctuation, whitespace or latin text. Long bare Chinese queries also emit bigrams instead of becoming one impossible substring |
| BM25 | `idf=ln(1+(N-n+0.5)/(n+0.5))`, `k1=1.2`, `b=0.75`, saturated term frequency and field-length normalization. Term/field contributions are emitted |
| Hybrid fusion | Body rank weight 0.75 and metadata rank weight 0.25, merged by document id as `0.75/body_rank + 0.25/metadata_rank`. Equal scores share ranks; final ties keep corpus order |
| Hard constraints | `all` terms must appear, `any` needs at least one, and every exact metadata filter must match. Documents missing a filter key never match; no ranking stage resurrects an excluded document |
| Evidence | Hits include title/path/meta, document and optional original-file hashes, `matched_terms`, field matches, rank reasons and passages with physical page (form-feed convention), section, paragraph, `[start,end)` and verbatim quote |
| No hit and ambiguity | `no_result` distinguishes no term match from filters excluding term matches, lists pre-filter candidates and observed filter values. Exact top ties produce `ambiguity` instead of a silently chosen answer |
| Duplicate evidence | Same-text ids are grouped, `independent_document_count` is reduced, and duplicate-copy warnings remain visible |
| Extraction honesty | `coverage.json` records each file's role, size, full original SHA-256, backend/status/detail. Unsupported, failed and no-text files are not silently searched or described as indexed |

`score` remains the backward-compatible number of distinct matched query terms.
**`ranking_score` is the BM25/fusion ordering score**; neither is a semantic
probability.

## Harbor runtime procedure

1. Read `/input/case.json`, `task.md` and the real library/workorder. Preserve
   `case_id` and every `output_contract` field. Establish which materials are
   searchable, which metadata is declared, and which queries/filters are hard
   requirements.
2. Use `--root` for real files, `--corpus` for prepared text, or `--index` to
   replay an existing index. Place intermediate work in `/app/work` and final
   outputs in `/app/output`; never write the index or coverage report into the
   source library.
3. Translate a natural query deliberately: exact required terms into `all`,
   caller-declared alternatives/abbreviations into `any`, and exact metadata
   conditions into `filters`. Do not allow the engine to guess synonyms or
   relax a condition. A bare query is acceptable for direct CJK/latin recall.
4. Run the CLI. Inspect `coverage.json`: unreadable, encrypted, corrupt,
   unsupported, large or no-text files are limitations, not invisible misses.
   Every indexed document must correspond to an actual extracted text layer.
5. Audit hits against `index.json`: quote equals paragraph `[start:end)`,
   section/page are right for the source's form-feed markers, hashes match, and
   every filter was applied. Review duplicate groups and top-tie ambiguity.
6. Deliver `/app/output/result.json`, `index.json` and, for `--root`,
   `coverage.json`. For an empty result, retain `no_result` diagnostics and do
   not pad with near misses. On a readable case, structured refusals also carry
   `case_id` and all contract fields. `search_result`, `operation_evidence`,
   `failure_recovery`, `sources` and `uncertainty` are derived from real run
   state when named by the contract.

The procedure ends at the deliverables. Benches are optional author-side
checks, not a mandatory runtime self-test.

## Real CLI and runnable examples

Actual files with CJK query and contract passthrough:

```bash
python scripts/search_cli.py \
  --root examples/real_library \
  --query "缓冲液配方在哪里" \
  --case examples/case.json \
  --out ./out-search
```

The example has one real protocol text file and one metadata sidecar. The
sidecar is indexed only through the linked document's metadata channel, not as
an independent scientific document. Query terms hit body/title and return
section/character evidence. This is a minimal example, not a formal case answer.

Structured query with hard filters:

```bash
python scripts/search_cli.py \
  --root examples/real_library \
  --query-file examples/query_filters.json \
  --case examples/case.json --out ./out-filtered

# Existing corpus/index interfaces remain supported:
python scripts/search_cli.py --corpus examples/corpus.json \
  --query-file examples/query.json --case examples/case.json --out ./out-corpus
python scripts/search_cli.py --index ./out-corpus/index.json \
  --query "缓冲液" --out ./out-replay
```

Exactly one of `--root`, `--corpus`, `--index` is required. `--metadata NAME`
can be repeated to choose metadata sidecars; existing `metadata.json`,
`metadata.csv` and `metadata.tsv` in root are also recognized.

Corpus records support `{id, text, title, path, source_sha256, meta}`. A
`pages` array can be converted to form-feed-separated text. Query objects use:

```json
{"all": ["缓冲液"], "any": ["Tris", "buffer"],
 "filters": {"year": 2024, "project": "P01"}}
```

## Outputs and exit discipline

- `index.json`: exact indexed text, paragraph/page map, sections, body and
  metadata fields, declared meta, source/document hashes, document order,
  corpus fingerprint and BM25 statistics.
- `coverage.json`: actual root-file coverage and extraction issues (`--root`).
- `result.json`: normalized query, full index fingerprint, normalized ranking
  method, hits and rank explanations, duplicate evidence, ambiguity/no-result
  diagnostics, coverage, findings/status and contract fields.

| Exit | status | Meaning |
|---|---|---|
| 0 | ok | Query answered with full extraction/index coverage |
| 4 | partial | Query answered, but corpus entries or actual files were skipped/failed and named |
| 5 | undetermined | Bad query/corpus/index/case/root, invalid filters, no usable text or export failure; structured `refusal` written |
| 2 | usage | Wrong argument combinations or invalid flags |

`search.spec_unreadable`, `search.case_unreadable`, `search.empty_corpus`,
`search.index_malformed`, `search.empty_query`, `search.filter_invalid`,
`search.export_failed` are refusals. `search.doc_skipped`,
`search.meta_invalid`, `search.duplicate_content` and
`search.file_extraction_incomplete` are findings. `search.root_missing` is
rejected by the real-root adapter.

## Method provenance

The implementation directly applies mechanisms inspected in:

- Tantivy's BM25 implementation:
  https://github.com/quickwit-oss/tantivy/blob/main/src/query/bm25.rs — its
  document-frequency IDF, `k1=1.2/b=0.75` saturation/length normalization and
  per-term explanation model.
- Tantivy `NgramTokenizer`:
  https://github.com/quickwit-oss/tantivy/blob/main/src/tokenizer/ngram_tokenizer.rs
  — Unicode codepoint-frontier tokenization. Here n-grams are generated only
  inside contiguous CJK runs and offsets returned to users remain Python
  character offsets of the original paragraph.
- txtai's hybrid-search implementation:
  https://github.com/neuml/txtai/blob/master/src/python/txtai/embeddings/search/hybrid.py
  — side-specific ranked results merged by document id with declared weights.
  This package uses weighted reciprocal rank and explicit tied ranks, not a
  neural embedding or a fake semantic model.

The local high-scoring reading client's page anchors and p02's real PDF
fallbacks informed the locator/backend discipline. No other package or shared
engine is imported or modified.

## Requirements and limits

- Python 3.10+ and the standard library cover indexing, ranking, text and
  OOXML extraction. Python 3.14 was used for verification.
- PDF extraction tries PyMuPDF, pypdf, then `pdftotext`. Missing backends,
  encrypted/corrupt PDFs and scans without a text layer yield named failures;
  OCR is not claimed. The local-file extractor has a 16 MiB per-file budget.
- DOCX/PPTX/XLSX use their real XML. PPTX slides and PDF pages map to form-feed
  physical pages. A file without form feeds has `page: null`; printed-page
  reconciliation and two-column reading-order correction are not invented.
- This is hybrid **lexical metadata** search, not dense semantic retrieval.
  Alternative terms must be declared in `any`; range/nested geo/filter
  expressions are not implemented. Metadata matching is exact (numeric/string
  forms compare transparently).
- No wall-clock fields or random scoring are used. Replaying the same unchanged
  index/query is byte-identical. A real-root rerun is deterministic when the
  input tree and output paths are unchanged.

## Optional verification (author-side)

```bash
python -I -X utf8 scripts/bench_search.py         # legacy/boolean: 26 scenarios
python -I -X utf8 scripts/bench_search_hybrid.py  # hybrid/real files: 10 scenarios
```

Current local baseline: **36/36 scenarios pass** (26 + 10). Reports are
`scripts/report_search.json` and `scripts/report_search_hybrid.json`.
