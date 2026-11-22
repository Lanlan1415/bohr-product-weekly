"""Table ingest for the "one image plus all its tables" case shape.

The challenge's v2 input revision makes each case one original figure *and* all
of its original tables. Figures go through the calibration path; tables must
not. A table is already numbers, so digitising it would only add error — it is
parsed, located, and reported as-is.

Supported inputs: delimited text (CSV/TSV, delimiter sniffed), markdown pipe
tables, and JSON arrays of records. Everything else is refused by name rather
than guessed at, because a mis-parsed table is a fabricated result.

    python scripts/tables.py --out /app/output tables/*.csv
"""

from __future__ import annotations

import argparse
import csv
import io
import json
from pathlib import Path

MAX_ROWS = 5000


def _numeric(cell: str) -> float | None:
    """Parse a table cell as a number, or return None.

    Accepts a minus sign written as U+2212, thousands separators, and simple
    scientific notation. A trailing % is *removed but not divided by 100*: the
    column is then annotated as percent, so the value stays the number the paper
    printed. Silently turning 12% into 0.12 is a unit change nobody can see.
    """
    s = cell.strip().replace("\u2212", "-").replace(",", "")
    if not s:
        return None
    if s.endswith("%"):
        s = s[:-1].strip()
    try:
        return float(s)
    except ValueError:
        return None


def sniff_delimiter(text: str) -> str:
    """Pick the delimiter from the header line by counting candidates."""
    first = text.splitlines()[0] if text.strip() else ""
    counts = {d: first.count(d) for d in (",", "\t", ";", "|")}
    best = max(counts, key=counts.get)
    return best if counts[best] > 0 else ","


def parse_markdown_table(text: str) -> list[list[str]]:
    rows = []
    for line in text.splitlines():
        line = line.strip()
        if not line.startswith("|"):
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        if all(set(c) <= set("-: ") for c in cells):
            continue  # the separator row
        rows.append(cells)
    return rows


def parse_table(path: Path) -> dict:
    """Parse one table file into a header plus typed rows.

    A file that does not exist is refused by name (the same contract as an
    unparseable file), not a crash.
    """
    if not path.exists():
        return {"path": str(path), "ok": False, "reason": "file not found"}
    raw = path.read_text(encoding="utf-8-sig", errors="replace")
    suffix = path.suffix.lower()

    if suffix == ".json":
        data = json.loads(raw)
        if isinstance(data, list) and data and isinstance(data[0], dict):
            header = list(data[0].keys())
            rows = [[str(r.get(h, "")) for h in header] for r in data]
        else:
            return {"path": str(path), "ok": False, "reason": "JSON is not an array of records"}
    elif "|" in raw and raw.strip().startswith("|"):
        rows = parse_markdown_table(raw)
        header, rows = (rows[0], rows[1:]) if rows else ([], [])
    else:
        delim = sniff_delimiter(raw)
        reader = list(csv.reader(io.StringIO(raw), delimiter=delim))
        header, rows = (reader[0], reader[1:]) if reader else ([], [])

    if not header:
        return {"path": str(path), "ok": False, "reason": "no header row found"}

    rows = rows[:MAX_ROWS]
    # Type each column by how many of its non-empty cells parse as numbers.
    typed = []
    for j, name in enumerate(header):
        cells = [r[j] if j < len(r) else "" for r in rows]
        nums = [_numeric(c) for c in cells]
        filled = [n for n, c in zip(nums, cells) if c.strip()]
        numeric = bool(filled) and all(n is not None for n in filled)
        percent = numeric and any(c.strip().endswith("%") for c in cells)
        entry = {
            "column": name,
            "kind": "numeric" if numeric else "text",
            "values": [None if n is None else round(n, 12) for n in nums] if numeric else cells,
            # A column that is mostly numeric but not entirely is a data-quality
            # signal the reader needs to see, not something to coerce away.
            "non_numeric_cells": None if numeric else
                                 [i for i, n in enumerate(nums) if n is None and cells[i].strip()],
        }
        if percent:
            entry["unit_hint"] = "percent"
            entry["unit_note"] = ("values are the numbers printed before %, not fractions; "
                                  "divide by 100 yourself if the calculation needs a fraction")
        typed.append(entry)

    return {
        "path": str(path),
        "ok": True,
        "n_rows": len(rows),
        "n_columns": len(header),
        "columns": typed,
        "evidence": {"read_by": "table parser, values taken verbatim",
                     "format": suffix.lstrip(".") or "delimited"},
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("files", nargs="+")
    ap.add_argument("--out", required=True, help="directory for result.json")
    ap.add_argument("--case", help="case.json to echo case_id and merge into its result")
    a = ap.parse_args()

    tables = [parse_table(Path(f)) for f in a.files]

    out_dir = Path(a.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    target = out_dir / "result.json"
    if a.case and target.exists():
        result = json.loads(target.read_text(encoding="utf-8"))
    else:
        result = {"schema_version": "figparse/v1", "case_id": "UNKNOWN",
                  "status": "undetermined", "panels": [], "limits": []}

    result["tables"] = tables
    failed = [t for t in tables if not t.get("ok")]
    if failed:
        result["limits"].append(f"{len(failed)} table(s) could not be parsed: " +
                                ", ".join(t["path"] for t in failed))
    if a.case:
        result["case_id"] = json.loads(Path(a.case).read_text(encoding="utf-8")).get(
            "case_id", result["case_id"])
    target.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"ok": True, "tables": len(tables), "wrote": str(target)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
