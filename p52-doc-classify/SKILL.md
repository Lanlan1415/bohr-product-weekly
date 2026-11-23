---
name: doc-classify
description: >
  Classify actual research files into a declared multi-level taxonomy using
  inspectable, field-weighted evidence—not filename extensions or a single
  arbitrary keyword. Emits exact source spans, calibrated confidence, multi-
  label and ambiguity candidates, unknown classes, missing metadata, full raw
  SHA-256 duplicates and version relations. Produces a safe old→new plan and,
  on request, a hash-verified organised COPY outside the source tree. Never
  moves, overwrites or deletes an input file. Use for literature/data batch
  classification, tags, naming, dedup and reversible handover; not open-web
  literature discovery or neural-model classification claims.
---

# 文献与资料自动分类

## Implemented evidence and landing model

The primary entry point is `scripts/filebatch_cli.py`; it reads real files,
classifies their extracted content and can materialize an organised copy.

### Classification, not filename guessing

- Taxonomy entries are `{category, cues, examples}`; `研究/实验方法` is a real
  two-level category with `level: 2`, `parent: 研究`, and nested destination
  directories. Only declared hierarchy nodes are emitted.
- Evidence fields have explicit weights: title 2.0, abstract 1.5, keywords
  2.0, body/text 1.0, journal 1.25, subject 1.5, other declared metadata 0.75.
  Exact examples count double within their field. Latin-only cues respect token
  boundaries; CJK cues match actual text spans.
- **Filename, path and extension are never classification evidence.** Generic
  file-format/document words, one-character and very short low-specificity cues
  cannot establish a label; they remain review candidates when declared.
- Each label includes matched cues/examples plus source evidence
  `{field,start,end,quote,field_weight,specificity,weight}`. Every asserted
  class is traceable to actual extracted content or declared metadata.

`weighted_evidence` is summed per category, `evidence_share` is its share of all
label evidence, and:

```text
confidence = evidence_share * min(top_weighted_evidence / 2, 1)
```

Thus an ordinary single body cue cannot exceed 0.5, while title/exact-example
or corroborated evidence can be stronger. This is a deterministic evidence
score, **not a learned model probability**. Low scores and equal top labels
set `review_required`; runner-ups remain in `labels` as multi-label candidates,
and a no-evidence file stays `未分类` with candidates and a reason. The result
includes `needs_review_ids`, ambiguity records and per-declared-node direct and
subtree counts.

### Files, metadata and non-destructive organization

- Every regular file receives size, kind/encryption/use status and a **full
  64-hex SHA-256 of original bytes**. Exact duplicates use this hash, not a
  title. Same-name/different-byte files are not duplicates.
- Metadata comes only from declared JSON/CSV/TSV records, real embedded OOXML/
  PDF properties, or an actual DOI regex match in extracted content. Every
  value has `metadata_provenance`; author/year/title are never inferred from a
  filename. A conflict keeps the first value and emits a warning.
- Destination paths preserve category levels and optional year. Naming uses
  author-year-title → DOI → title → original stem with missing fields named;
  unsafe characters and overlong names are normalized, and target collisions
  receive a content-hash suffix.
- Exact duplicates go to a duplicate-archive **copy** plan; DOI/title+author+
  year near duplicates remain `manual_confirm`, and overlapping identity groups
  coalesce into one evidence group/relation instead of being counted twice.
  DOI-looking strings inside a metadata sidecar are not attributed to that
  sidecar itself. Preprint/published relations require declared version data or
  explicitly reported filename cues, never an authoritative-title guess.
- Default mode is plan-only. `--materialize DEST` creates copies only in a
  separate destination outside the source root. Source hashes are rechecked,
  copied hashes are verified, a copy journal is written, existing identical
  targets are idempotent no-ops, and differing targets are never overwritten.
  **No source move/rename/delete/overwrite occurs.**

The older `classify_cli.py` (inline records), `land_cli.py` (legacy move/journal
API for isolated local batches) and their engines remain for compatibility.
The Harbor path below uses the non-destructive filebatch/copy API.

## Harbor runtime procedure

1. Read `/input/case.json`, `task.md`, workorder and actual files. Preserve
   `case_id` and all `output_contract` fields. Identify the real source root
   and any declared taxonomy/metadata sidecars; labels and extensions are not
   document content.
2. Express the workorder taxonomy as JSON with real category paths, cues and,
   if available, exact examples. Do not invent a training model, gold labels,
   author/year/DOI, or a semantic confidence score. Save intermediate work in
   `/app/work`.
3. Run `filebatch_cli.py --root ACTUAL_ROOT --spec WORKORDER --out
   /app/output`. Omit `--materialize` to review `operation_plan.json` before
   any copy. Inspect extraction failures, unknown classes, low-confidence and
   ambiguous items, duplicate/version groups and metadata warnings.
4. When an organised deliverable is requested, rerun with
   `--materialize /app/output/organized`. The source must remain separate.
   Copies provide a real directory tree while `source_writes: 0`; near/unknown
   items remain visibly reviewable rather than being silently merged.
5. Audit result rows: each file has a label/reason, actual evidence locators,
   confidence and provenance; each copy has matching before/after SHA-256.
   A rerun over an existing copy tree must show `already_done` and no journal
   duplication. Do not claim a repaired version relation that remains manual.
6. Deliver `result.json`, `classification.json`, `operation_plan.json`,
   `summary.md`, any verified `organized/` copy tree and copy journal. Status
   is ok/review/blocked/undetermined with exit 0/3/4/5. On every readable-case
   path—including structured refusal—retain `case_id` and every original
   output-contract key. Contract `library_result`, `classification_result`,
   `operation_evidence`, `failure_recovery`, `sources` and `uncertainty` are
   derived from actual results.

The procedure ends at the deliverables. Verification below is optional author
tooling and is not a required runtime self-test.

## Real CLI and runnable example

```bash
python scripts/filebatch_cli.py \
  --root examples/real_library \
  --spec examples/filebatch_spec.json \
  --case examples/case.json \
  --out ./out-classification \
  --materialize ./out-organized
```

The example contains one real method text and a three-branch multi-level
taxonomy. The command extracts actual method cues, detects the literal DOI,
creates `研究/实验方法/...` in the **copy** tree and exits 0. Omit
`--materialize` for a deterministic plan-only run.

Spec shape:

```json
{
  "taxonomy": [
    {"category": "研究/实验方法", "cues": ["方法", "protocol", "we measured"]},
    {"category": "研究/研究结果", "cues": ["结果", "increased", "three-fold"]}
  ],
  "metadata_files": ["metadata.json"],
  "min_hits": 1,
  "organize": {"naming_template": "author-year-title", "year_subdir": true,
               "max_name_len": 60, "dupes_dir": "duplicates"}
}
```

`metadata.json/csv/tsv` are auto-detected when present. They remain inventoried
files themselves, so their own classification may honestly be `未分类`.
Invalid `min_hits` degrades to 1; a missing taxonomy is refused instead of
inventing categories.

Legacy inline-record command:

```bash
python scripts/classify_cli.py --spec examples/spec.json --out ./out-inline
```

## Outputs and exits

- `result.json`: status, counts, all original contract fields, file inventories
  and classifications, hierarchy summary, metadata/provenance, full duplicate
  and version sets, plan, optional copy evidence, findings and limits.
- `classification.json`: file-level classes, scores, source spans and declared
  taxonomy/summary.
- `operation_plan.json`: source-to-copy recommendations, secondary labels,
  confidence/reason/evidence, duplicates, near duplicates and versions.
- `summary.md`: human handover table.
- `copy_journal.jsonl`: successful/failed copy records with full verified
  hashes (only when materialization was requested).
- `/app/output/organized/**`: real organised copies, if requested.

| Exit | status | Meaning |
|---|---|---|
| 0 | ok | Classified and/or copied without review/blocking findings |
| 3 | review | Unknown/weak/ambiguous classes, near duplicates or non-fatal extraction issues need human review; honest deliverables still exist |
| 4 | blocked | Source/target/hash/copy conflict or unsafe destination; no conflicting target was overwritten |
| 5 | undetermined | Bad JSON/case/root/taxonomy or execution/export failure with structured refusal |
| 2 | usage | argparse usage error |

Core rules include `cls.empty_taxonomy`, `cls.no_records`,
`cls.spec_unreadable`, `cls.record_skipped`, `cls.unclassified`,
`cls.low_confidence`, `cls.ambiguous`, `dup.exact`, `dup.near`,
`ver.relation`, `copy.path_escape`, `copy.source_mismatch`,
`copy.target_conflict`, `copy.mismatch`, `copy.destination_conflict` and
`filebatch.*` refusals. A `review` result is not rewritten as completed gold.

The complete implemented auxiliary index is `cls.cue_collision`,
`cls.taxonomy_entry_skipped`, `inv.unreadable`, `inv.zero_byte`,
`inv.pdf_encrypted`, `plan.entry_not_found`, `plan.duplicate_entry`,
`plan.uncovered_files`, `name.collision_resolved`, `name.degraded`,
`ver.ambiguous`, `exec.source_missing`, `exec.skipped_conflict`,
`exec.move_failed`, `exec.mismatch`, `rollback.source_missing`,
`rollback.failed`, `rollback.mismatch`, `copy.source_unreadable`,
`copy.failed`, `land.spec_unreadable`, `land.root_missing`, `land.no_entries`,
`filebatch.spec_unreadable`, `filebatch.case_unreadable`,
`filebatch.root_missing`, `filebatch.output_conflict`,
`filebatch.export_failed`, and `filebatch.run_failed`. The legacy
`journal.jsonl`, `rollback.jsonl` and `metadata.tsv` are filenames in the
legacy journal or regression fixtures, not classification rules.

## Method provenance and local reuse

Zotero's `getFileBaseNameFromItem` metadata.template chain, unique collision
handling and linked/stored attachment separation informed the naming and
provenance design (source:
https://github.com/zotero/zotero/blob/main/chrome/content/zotero/xpcom/attachments.js
). This package adds full original-byte hashing, missing/orphan checks, field-
weighted evidence and safe output-side copies; it does not depend on Zotero.

The local reading client's explicit quote/offset verification and p02's real
PDF-backend fallbacks were reused as design constraints: every semantic-looking
field must have actual evidence, and missing extraction becomes a named limit.
No shared engine or other agent's package was changed.

## Requirements and limitations

- Python 3.10+; standard library implements inventory, ranking rules and
  DOCX/PPTX/XLSX XML extraction. Verified with Python 3.14.
- PDF extraction tries PyMuPDF, pypdf, then `pdftotext`; encrypted/corrupt/
  no-text files are named and remain unknown unless declared metadata supplies
  real evidence. No OCR or online metadata enrichment is claimed. Extraction
  has a 16 MiB per-file budget in the filebatch reader.
- This is explicit rule/content classification, not a trained classifier.
  Recall is bounded by the declared taxonomy/cues. Unknown and multi-label are
  first-class outputs; confidence does not guarantee correctness to a hidden
  semantic gold label. Parent nodes absent from the taxonomy are not invented.
- Exact duplicates are archived only as copies; near duplicates and version
  authority always await review. Legacy `.doc/.xls/.ppt` and arbitrary binary
  attachments may be inventory-only.
- Output and source roots must be separate and neither may contain the other.
  Plan-only runs are byte-identical on unchanged inputs/output paths. Copy
  reruns intentionally report `already_done`; no wall-clock records are used.

## Optional verification (author-side)

```bash
python -I -X utf8 scripts/bench_classify.py   # legacy classify/land: 24 scenarios
python -I -X utf8 scripts/bench_filebatch.py  # real evidence/copies: 11 scenarios
```

Current local baseline: **35/35 scenarios pass** (24 + 11). Reports are
`scripts/report_classify.json` and `scripts/report_filebatch.json`.
