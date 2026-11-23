---
name: library-mgmt
description: >
  Inventory and repair a real research file library without changing source
  files. Hashes original bytes with SHA-256, inventories every regular file,
  extracts real text when a backend exists, keeps field-level metadata
  provenance, finds exact duplicates, version candidates, conflicting metadata,
  missing/orphan attachments, and produces a collision-safe naming/directory
  plan plus a searchable handover. Includes a legacy inline-text library with
  version chains. Use for actual folders, sidecar metadata, aliases, workorders
  asking for recovery/index plans, or a verifiable library handover. Do not use
  for BM25 passage-level retrieval (use file-search) or taxonomy labelling of
  document content (use doc-classify). No Zotero account or publisher record is
  assumed.
---

# 科研资料库与文件管理

## What is actually implemented

The primary entry point is `scripts/filecare_cli.py`. It treats the **original
file bytes**, not a filename or an extracted surrogate, as the artifact.

| Rubric concern | Mechanical implementation |
|---|---|
| Complete manifest | Recursive regular-file inventory with relative path, bytes, extension/kind, permissions, full 64-hex SHA-256, extraction status/backend/detail; walk errors, symlinks and unreadable files are named |
| Real duplicates | Groups only identical original-byte hashes. Same title or same filename never proves duplication; every source copy is retained |
| Metadata | Declared JSON/CSV/TSV records and safe embedded OOXML/PDF metadata only, with `meta_src` per field; missing required fields stay null/missing |
| Versions and conflicts | Explicit version links stay separate from declared-DOI/title+year `version_candidates`; identical file sets across identity keys are merged so one relation/conflict is counted once. Different content hashes and conflicting field values stay visible; no authoritative version is guessed |
| Missing/conflicting/orphan attachments | Declared attachments and aliases are resolved inside root; outside-root references, missing files and ambiguous aliases are refused; unreferenced files are listed when records exist |
| Naming and directories | Declared cues choose folders; author-year-title, DOI, title or original-stem fallback generates safe recommendations. Unsafe characters are removed and collisions get a hash suffix |
| Reproducible plan | `operation_plan.json` gives old→new rows and reversal instructions. **No plan row is executed; no source move/rename/overwrite/delete occurs** |
| Searchable handover | Optional full-text/title/path/metadata query with matched terms and a real snippet; an empty query result stays empty and explained |

The legacy `scripts/library_cli.py` remains available for inline UTF-8 text
records. It supplies `@vN` version chains, duplicate/sibling sets and
`library.json + inventory.md + manifest.tsv`; it is not presented as a binary
file inspector.

## Harbor runtime procedure

1. Read `/input/case.json`, `task.md` and the organizer's actual workorder and
   materials. Preserve `case_id` and all `output_contract` keys. Locate the
   actual file root; do not infer file contents from a domain label.
2. Translate the workorder—not guessed scientific metadata—into a JSON spec.
   Declare `structure`, `meta_fields`, `records`/`metadata_files` and naming
   options only when supported by the case. Save intermediate work in
   `/app/work`; final artifacts belong in `/app/output`.
3. Run the real-file command below with `--root ACTUAL_ROOT`. Keep output
   outside the source tree. It hashes and inspects, writes an inventory and a
   review plan, and leaves input writes at zero.
4. Inspect every `filecare.*` finding. Distinguish unreadable files from
   unsupported/no-text extraction, missing attachments, duplicate content,
   version candidates, metadata conflicts and orphan files. Do not claim OCR,
   publisher reconciliation or a repaired attachment that did not occur.
5. If the workorder asks about recoverability/search, use `--query`. Verify the
   hits and snippets against actual text; if nothing matches, keep the honest
   empty result rather than widening it invisibly.
6. Finish with `/app/output/result.json`, plus `file_inventory.json`,
   `operation_plan.json` and `inventory.md`. A readable case supplies `case_id`
   and every original contract field on ok, partial **and structured refusal**
   paths. Known `library_result`, `operation_evidence`, `failure_recovery`,
   `sources`, `uncertainty` and change-record fields are derived from the run;
   other values pass through exactly as supplied or become null with a limit.

The procedure ends at the deliverables. Verification commands are optional
author tooling below, not a runtime gate.

## Real CLI and minimal runnable example

From the package directory:

```bash
python scripts/filecare_cli.py \
  --root examples/real_library \
  --spec examples/filecare_spec.json \
  --case examples/case.json \
  --query "缓冲液" \
  --out ./out-filecare
```

Expected for this example: three inventoried files (two text documents and the
metadata sidecar), one exact duplicate set, real snippets, and a plan only. Exit
is 0 when no partial/conflict finding exists. It is an example, not a formal
case answer.

Spec shape:

```json
{
  "structure": [{"folder": "protocols/buffer", "cues": ["缓冲液", "Tris"]}],
  "meta_fields": ["author", "year", "project", "doi"],
  "records": [
    {"id": "paper-a", "path": "paper.pdf", "aliases": ["main-paper"],
     "meta": {"title": "Actual declared title", "year": 2024},
     "attachments": ["supplement.xlsx"]}
  ],
  "metadata_files": ["metadata.json"],
  "organize": {"naming_template": "author-year-title"}
}
```

`metadata_files` defaults to existing `metadata.json`, `metadata.csv` and
`metadata.tsv` in root. JSON accepts a list of records, an object containing
one of the record/document/file/item arrays, or a `{path: metadata}` map. CSV/TSV uses a
`path` (or `file`) column. Values are retained with source row/field locators.
There is no network metadata enrichment.

Legacy inline-text command:

```bash
python scripts/library_cli.py --spec examples/spec.json \
  --case examples/case.json --query "涂层 吸收速率" --verify --out ./out-inline
```

## Outputs and status

- `result.json`: `status`, `case_id`, `counts`, `documents`, full raw hashes,
  `duplicates`, `version_candidates`, `declared_version_links`, `attachments`,
  `metadata_conflicts`, `operation_plan`, `operation_evidence`, `retrieval`,
  `findings`, `limits`, and all case-derived top-level fields.
- `file_inventory.json`: machine-readable manifest and relationships.
- `operation_plan.json`: proposed moves with `executed: false`, source hashes,
  naming evidence and rollback instructions; `executed_moves: 0`.
- `inventory.md`: human handover table and anomalies.
- The inline legacy CLI writes its own `library.json`, `inventory.md`,
  `manifest.tsv`, and `result.json`.

| Exit | status | Meaning |
|---|---|---|
| 0 | ok | Complete inspection with no integrity/readability/link/conflict limitation |
| 4 | partial | Results exist, but named unreadable/extraction/missing/conflict items or changed hashes limit completion |
| 5 | undetermined | Bad JSON/case, missing or empty root, no usable inline records, or export/integrity failure |
| 2 | usage | argparse rejected the command shape |

Important finding rules: `filecare.walk_skipped`, `filecare.unreadable`,
`filecare.text_unavailable`, `filecare.duplicate_content`,
`filecare.attachment_missing`, `filecare.attachment_orphan`,
`filecare.metadata_conflict`, `filecare.related_metadata_conflict`,
`filecare.unfiled`, `filecare.integrity_changed`. Refusal rules:
`filecare.root_missing`, `filecare.empty_root`, `filecare.spec_unreadable`,
`filecare.case_unreadable`, `filecare.export_failed`.

The unchanged legacy engines emit and this version also documents:
`lib.spec_unreadable`, `lib.case_unreadable`, `lib.no_records`,
`lib.export_failed`, `lib.integrity_mismatch`, `lib.integrity_verified`,
`lib.record_skipped`, `lib.file_missing`, `lib.file_unreadable`,
`lib.meta_invalid`, `lib.id_invalid`, `lib.structure_skipped`,
`lib.folder_empty`, `lib.version_created`, `lib.duplicate_content`,
`lib.version_sibling`, and `lib.unfiled`. The text-only manifest/metadata paths
`manifest.tsv` and `metadata.tsv`, and the test-only `orphan.dat` fixture name,
are filenames rather than findings.

## Method provenance and reusable mechanisms

Zotero's `getFileBaseNameFromItem`, unique copy/move handling and linked-file
path resolution were inspected in
https://github.com/zotero/zotero/blob/main/chrome/content/zotero/xpcom/attachments.js
. The applicable mechanisms are implemented locally: metadata-driven naming,
portable linked attachment paths, collision-safe targets and missing-link
reporting. Zotero's file does not provide content-hash deduplication, so this
package additionally hashes every original file in full and never auto-deletes
a duplicate. No Zotero code, private Zotero data or network dependency is
required.

The local high-scoring reading client's explicit page/paragraph anchors and
p02's real PDF-backend fallback inspired the same discipline here: evidence is
reported only when extracted by a named backend, never from an assumed label.
Those packages were not modified.

## Requirements and honest limits

- Python 3.10+; inventory, text, JSON/CSV/TSV and DOCX/PPTX/XLSX XML extraction
  use only the standard library. Python 3.14 was used for verification.
- PDF extraction tries PyMuPDF, then pypdf, then `pdftotext` on PATH. If none
  yields a text layer, status is failed/no-text/unsupported with errors; OCR is
  not fabricated. Extraction is capped at 16 MiB per file in `extract`.
- OOXML extraction reads actual document/slide/worksheet XML and core
  properties. Legacy `.doc/.xls/.ppt`, encrypted files and arbitrary binaries
  may remain unextracted but still appear in the raw-byte manifest.
- Plans are intentionally non-executable. A reviewer must apply them with a
  separate, authorized tool; this skill never claims that a proposed move was
  completed. Original mtime, permissions and ownership are not rewritten.
- Version candidates are evidence groups, not final publication decisions.
  Folder/cue assignment is lexical and a matched cue is not subject-matter
  proof. Full-text search in this package is small-batch lexical handover
  search; use `file-search` for ranked hybrid retrieval and section citations.
- No wall-clock fields are emitted. Repeating the same unchanged input and
  output paths produces byte-identical JSON. Directory walks do not follow
  symlinks and declared paths may not escape root.

## Optional verification (author-side, not a runtime step)

```bash
python -I -X utf8 scripts/bench_library.py   # legacy inline/text: 25 scenarios
python -I -X utf8 scripts/bench_filecare.py  # real files/contracts: 10 scenarios
```

Current local baseline: **35/35 scenarios pass** (25 + 10). Reports are
`scripts/report_library.json` and `scripts/report_filecare.json`.
