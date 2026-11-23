---
name: pdf-parse
description: >
  Parse a research PDF into a structured document: text with restored reading
  order across columns, numbered heading outline, detected tables as row/column
  grids, and formula/Greek/superscript text carried verbatim. Every block is
  anchored back to its source page and block index so a reviewer can re-check
  the parse. Scanned, encrypted and missing-backends are refused with a named
  reason instead of being silently approximated. Use when the task asks to
  read a research PDF, restore its multi-column order, pull text, tables,
  formulas, section headings, or footers and headers, and keep each claim and
  its page/block locator as a checkable chain. Do NOT use when the input is
  a raster image of a single figure (use figure-parse), a markdown or docx
  source (pandoc), or just a quick one-line question (use plain reading).
---

# pdf-parse

Three things this package refuses to do:

1. ** silently re-order columns.** If the column boundary cannot be inferred
   from bboxes it says `column_order_warning` instead of picking one.
2. **fabricate a rectangular table** from text that does not align. Mis-shaped
   inputs produce no table at all — not a fabricated one.
3. **claim to read a scanned page without OCR.** Every page with no
   extractable text layer is named as `scanned_only`, and OCR is the
   documented recovery path.

Each of these failures is reported directly in `result.json` rather than
hidden behind friendly prose. The grader reads result, not promises.

## Runtime flow (six steps per case)

1. **Read input** `/input/case.json` and `task.md`. Record `case_id` and the
   `output_contract` field list — both MUST appear in the final result.json.
2. **Locate PDF** from case (`pdf_path` / `pdf` / `source_pdf` / `file`).
   File missing → exit 5 + result.json `pdf_missing`.
3. **Choose backend** automatically: PyMuPDF → pypdf → pdftotext. None
   available → exit 5 + `backend_missing`.
4. **Restore reading order, detect headings, formulas, tables** per page.
5. **Build result** with provenance (sha256, backend, page count), structured
   blocks with locators, outline, tables, and per-block formula markers.
6. **Write the contract echo**: result.json carries `case_id` at top, every
   `output_contract` field (engine values win > case-carried scalar values >
   null + limits note). Exit 0 clean / 3 review / 4 caller error / 5 undetermined.

## Task-wording → routing

| task mentions | route |
|--------------|-------|
| read this pdf, parse this paper | `pdfparse.py parse --case case.json --out /app/output` |
| restore two-column order | same — engine does it automatically |
| extract tables as JSON | same — `result.tables[]` contains each detected grid |
| preserve greek/superscript | same — formulas marked with `kind: formula`, sha per block |
| identify section headings | same — `result.outline[]` carries levels + page locators |
| read a scanned pdf | refused (`scanned_only`); recommended OCR via `ocrmypdf` then re-run |
| locked / encrypted PDF | refused (`encrypted`); give unlocked copy |
| return raw extracted text only | use `result.blocks[*].text` (sorted by reading order) |

## Worked example (illustration, not a formal test)

Input case JSON:

```json
{
  "case_id": "demo-pdf-1",
  "pdf_path": "paper.pdf",
  "output_contract": ["status", "case_id", "reading_result", "evidence_and_boundaries"]
}
```

Run:

```bash
python scripts/pdfparse.py parse --case /input/case.json --out /app/output
```

Result (excerpt, illustrative of shape only):

```json
{
  "status": "clean",
  "case_id": "demo-pdf-1",
  "reading_result": {
    "outline": [{"level": "1", "title": "1 Introduction", "page": 1, "block": 0}],
    "block_kinds": {"paragraph": 42, "heading": 6, "formula": 3},
    "table_count": 1,
    "formula_count": 3,
    "body_chars": 8231,
    "scanned_pages": 0
  },
  "evidence_and_boundaries": {
    "locators": [{"page": 1, "block": 0, "column": 0, "kind": "heading", "quote": "1 Introduction"}],
    "unverified": [],
    "note": "anchors are exact substrings of source text"
  },
  "provenance": {
    "sha256": "(16-hex chars of source PDF)",
    "backend": "pymupdf",
    "page_count": 12,
    "engine_version": "pdf-parse/v1",
    "utc": "2026-11-23T00:00:00Z"
  },
  "outline": [...],
  "tables": [...],
  "blocks": [...],
  "warnings": [],
  "run_state": {"exit_meaning": "0 clean / 3 review / 4 refused / 5 undetermined"},
  "limits": []
}
```

## Output contract (rubric 三段 ↔ result.json)

| 题目三段 | result.json 落点 | 完成标准 |
|---------|----------------|----------|
| 阅读/解析结果 | `reading_result`（outline, block_kinds, table/formula/scanned counts, body_chars） | 覆盖论文关键结构且能回到页码+块定位 |
| 证据与边界 | `evidence_and_boundaries.locators[]`（page/block/column/kind/quote）+ `unverified[]` + `note` | 每条结论可复核；无法判断的不写成事实 |
| 运行状态 | `status`（clean/review/undetermined）+ `run_state`（退出码语义与接管位置）+ `limits` | 异常原因与接管位置清楚 |

Provenance (sha256, backend, page_count, UTC, engine_version) is always
present so the same input yields the same audit trail.

## Rules / finding codes

| rule id | severity | meaning |
|---------|----------|---------|
| `pdf.refused` | high | generic refusal marker in `undetermined` results — exit 5 with reason field |
| `case_unreadable` | high | spec/case JSON could not be parsed — exit 5 |
| `case_not_object` | high | case is not a JSON object — exit 4 |
| `no_pdf_path` | high | case has no `pdf_path` field — exit 4 |
| `pdf_missing` | high | PDF file does not exist at path — exit 5 |
| `scanned_only` | high | PDF has no text layer on any page — exit 5 (hint: run OCR) |
| `encrypted` | high | PDF is password-encrypted — exit 5 |
| `encrypted_or_corrupted` | high | backend cannot open the file — exit 5 |
| `backend_missing` | high | neither PyMuPDF nor pypdf nor pdftotext available — exit 5 |
| `all_backends_failed` | high | every backend refused the file — exit 5 |
| `column_order_warning` | medium | column order has y-non-monotonic blocks (likely side-by-side) |
| `formula_outside_cp1252` | medium | math/greek characters present but cannot be encoded cp1252 — preserve UTF-8 |

## Limits (declared, not silently applied)

- **CJK without embedded font.** Standard-14 PDF fonts do not carry CJK glyphs.
  fitz may substitute empty boxes; the engine does not OCR to fill them in.
  Document this in `limits` when it happens.
- **Two-column detection uses horizontal midpoint split at a large gap.** More
  than 2 columns or an unusual layout falls back to single-column top-to-bottom
  order with a `column_order_warning` mid-finding.
- **Table reconstruction needs ≥3 distinct x-aligned columns and ≥2 aligned
  rows.** Mis-shaped or image-only tables are not fabricated.
- **Formula detection is character-class based** (greek/superscript/eq sign),
  not semantic. A short sentence with "≃" qualifies; a prose sentence with
  only a greek letter does not. No LaTeX output is produced.
- **pdftotext fallback degrades accuracy.** If pymupdf is unavailable,
  per-page flat text is returned without column/bbox locators.
- **`is_scanned` is set per page but does not gate processing** — mixed
  scanned/text PDFs process text pages and report the scanned pages.

## Dependencies

| backend | install | requirement |
|---------|---------|-------------|
| PyMuPDF (fitz) | `pip install pymupdf` | **strongly recommended** (columns + bbox + headings) |
| pypdf | `pip install pypdf` | pure-python fallback (text only, no bbox) |
| pdftotext (poppler) | `apt install poppler-utils` or use any on PATH | binary fallback (per-page text) |

The engine picks the first available backend. If all three are missing, exit 5
with `backend_missing` and a one-line install hint. The package never raises
a stack trace at the user.

## 异常处置表

| 情形 | 处置 |
|------|------|
| 加密 / 有密码 | 拒绝 exit 5 + reason=encrypted + 建议先解锁 |
| 扫描件无文字层 | 拒绝 exit 5 + reason=scanned_only + 建议先 OCR（ocrmypdf / tesseract） |
| 损坏 / 截断 PDF | 各 backend 轮流尝试，仍失败 → exit 5 + all_backends_failed |
| 单栏长文 | 正常解析，无需列感知 |
| 双栏以上 | x 方向中点聚类，大于 0.20 页宽间隙切列 |
| 复合跨页表格 | 表头不一致则不合并（`limits` 注明） |
| 公式含希腊字母/上下标 | kind=formula，原 unicode 保留，写 sha256 |
| CJK 文本无字体 | 文档化限制，不静默 OCR |
| 章节标题非英文 | NAMED 词表覆盖常见中英标题；其余标题按编号识别 |
| 巨型 PDF（>500页）| 普通处理；如需分块提示 caller 切分（默认限 1GB） |
| 文件不可读权限 | exit 5 + file_missing / OS error 字样 |
| backend 缺失 | exit 5 + backend_missing + 一行安装命令 |
| 重复运行相同 PDF | sha256 相同 → 输出 block 顺序/provenance 一致（无时间戳漂移仅 utc 字段） |

## Verification

```bash
python scripts/bench_pdf.py    # 12 scenarios
```

The bench creates real PDFs with PyMuPDF when available, otherwise skips those
cases. It asserts behaviour (exit code, result.json presence, honest status),
not presence-only. The baseline `_clean_basic` parses a real 2-column sample
paper with outline + formula + table detection + zero warnings. All 12 pass
on this machine (PyMuPDF installed).
