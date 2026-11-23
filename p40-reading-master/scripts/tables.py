"""Parse original CSV/TSV/Markdown/JSON tables without inventing values.

    python scripts/tables.py table1.csv --out /app/output --case /input/case.json

A bad table is refused by name while other tables continue. Process status follows the
same contract as every route: success/clean 0, partial/review 3, blocked 4, undetermined 5.
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import contract as C  # noqa: E402

MAX_ROWS = 5000


def _numeric(cell: str) -> float | None:
    """Parse a number, preserving the printed percent value (12% stays 12)."""
    s = cell.strip().replace("−", "-").replace(",", "")
    if not s:
        return None
    if s.endswith("%"):
        s = s[:-1].strip()
    try:
        return float(s)
    except ValueError:
        return None


def sniff_delimiter(text: str) -> str:
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
            continue
        rows.append(cells)
    return rows


def parse_table(path: Path) -> dict:
    """Return a typed table or an ok=false record; never raise on bad input."""
    try:
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
                return {"path": str(path), "ok": False,
                        "reason": "JSON is not a non-empty array of record objects"}
        elif "|" in raw and raw.strip().startswith("|"):
            rows = parse_markdown_table(raw)
            header, rows = (rows[0], rows[1:]) if rows else ([], [])
        else:
            reader = list(csv.reader(io.StringIO(raw), delimiter=sniff_delimiter(raw)))
            header, rows = (reader[0], reader[1:]) if reader else ([], [])
        if not header:
            return {"path": str(path), "ok": False, "reason": "no header row found"}

        rows = rows[:MAX_ROWS]
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
                "values": ([None if n is None else round(n, 12) for n in nums]
                           if numeric else cells),
                "non_numeric_cells": (None if numeric else
                                      [i for i, n in enumerate(nums)
                                       if n is None and cells[i].strip()]),
            }
            if percent:
                entry["unit_hint"] = "percent"
                entry["unit_note"] = ("values are the numbers printed before %, not fractions; "
                                      "divide by 100 only when a calculation requires a fraction")
            typed.append(entry)
        return {
            "path": str(path),
            "ok": True,
            "n_rows": len(rows),
            "n_columns": len(header),
            "columns": typed,
            "evidence": {
                "read_by": "table parser, values taken verbatim",
                "format": suffix.lstrip(".") or "delimited",
                "locator": f"{path.name}: header row 1; data rows 2..{len(rows) + 1}",
            },
        }
    except (json.JSONDecodeError, csv.Error, OSError, TypeError, ValueError) as exc:
        return {"path": str(path), "ok": False,
                "reason": f"table could not be parsed: {type(exc).__name__}: {str(exc)[:140]}"}
    except Exception as exc:
        return {"path": str(path), "ok": False,
                "reason": f"table analysis was undetermined: {type(exc).__name__}: {str(exc)[:120]}"}


def _refused(out_dir: Path, message: str) -> dict:
    """No-contract-echo refusal for an unreadable case or unwritable route."""
    result = {"schema_version": "figparse/v1", "case_id": "UNKNOWN",
              "status": "undetermined", "panels": [], "tables": [],
              "limits": [message]}
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "result.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return result


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("files", nargs="+")
    ap.add_argument("--out", required=True, help="directory for result.json")
    ap.add_argument("--case", help="case.json to echo case_id and merge into its result")
    args = ap.parse_args(argv)
    out_dir = Path(args.out)
    try:
        out_dir.mkdir(parents=True, exist_ok=True)
        case = C.read_case(args.case) if args.case else {}
    except (OSError, ValueError) as exc:
        try:
            result = _refused(out_dir, str(exc))
        except Exception:
            print(json.dumps({"ok": False, "status": "undetermined", "wrote": None}))
            return 5
        print(json.dumps({"ok": False, "status": "undetermined",
                          "wrote": str(out_dir / "result.json")}, ensure_ascii=False))
        return 5

    tables = [parse_table(Path(f)) for f in args.files]
    target = out_dir / "result.json"
    result = {"schema_version": "figparse/v1", "case_id": "UNKNOWN",
              "status": "undetermined", "panels": [], "limits": []}
    if args.case and target.exists():
        try:
            previous = json.loads(target.read_text(encoding="utf-8"))
            if isinstance(previous, dict) and isinstance(previous.get("limits"), list):
                result = previous
        except (json.JSONDecodeError, UnicodeDecodeError, OSError):
            result["limits"].append("existing result.json was unreadable and was replaced")
    result["tables"] = tables
    failed = [t for t in tables if not t.get("ok")]
    succeeded = [t for t in tables if t.get("ok")]
    if failed:
        result["limits"].append(f"{len(failed)} table(s) could not be parsed: " +
                                ", ".join(t["path"] for t in failed))
    has_panels = any(p.get("series") for p in (result.get("panels") or [])
                     if isinstance(p, dict))
    if failed:
        result["status"] = "partial" if (succeeded or has_panels) else "undetermined"
    elif succeeded:
        if result.get("status") not in ("success", "partial"):
            result["status"] = "success"
    else:
        result["status"] = "undetermined"

    if result["status"] != "undetermined":
        C.merge_result(result, case)
    elif C.case_id(case) is not None:
        result["case_id"] = C.case_id(case)
    try:
        target.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    except OSError as exc:
        print(json.dumps({"ok": False, "status": "undetermined", "wrote": None,
                          "reason": str(exc)[:140]}, ensure_ascii=False))
        return 5
    print(json.dumps({"ok": result["status"] != "undetermined", "status": result["status"],
                      "tables": len(tables), "wrote": str(target)}, ensure_ascii=False))
    return C.status_exit(result["status"])


if __name__ == "__main__":
    raise SystemExit(main())
