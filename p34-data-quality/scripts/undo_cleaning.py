"""Restore the original rows from a cleaning result and its reversible ledger.

Usage: python undo_cleaning.py --result /app/output/result.json --out /app/work/undo
Writes restored.json, restored.csv when possible, and restoration.json. No input
file is overwritten. Exit 0 requires an exact match to original.json; exit 3
means restored but no original snapshot was available for comparison; exit 5 is
a structured refusal with no traceback.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import quality_gates as Q  # noqa: E402


def _digest(value) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                     separators=(",", ":")).encode("utf-8")).hexdigest()


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="undo_cleaning", description=__doc__)
    ap.add_argument("--result", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args(argv)
    out = Path(args.out)
    try:
        out.mkdir(parents=True, exist_ok=True)
        result_path = Path(args.result)
        result = json.loads(result_path.read_text(encoding="utf-8-sig"))
        if not isinstance(result, dict) or not isinstance(result.get("cleaned_table"), list):
            raise ValueError("result has no cleaned_table list")
        restored = Q.restore_rows(result["cleaned_table"], result.get("changes") or [])
        original_path = result_path.parent / "original.json"
        original = None
        if original_path.is_file():
            original = json.loads(original_path.read_text(encoding="utf-8-sig"))
        exact = None if original is None else restored == original
        (out / "restored.json").write_text(json.dumps(restored, ensure_ascii=False, indent=2),
                                           encoding="utf-8")
        if restored:
            columns = sorted({str(k) for row in restored if isinstance(row, dict) for k in row})
            buf = io.StringIO()
            writer = csv.DictWriter(buf, fieldnames=columns, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(restored)
            (out / "restored.csv").write_text(buf.getvalue(), encoding="utf-8")
        status = "restored" if exact is not False else "undetermined"
        receipt = {"status": status, "case_id": result.get("case_id"),
                   "exact_match_original": exact,
                   "restored_sha256": _digest(restored),
                   "original_sha256": _digest(original) if original is not None else None,
                   "undo_command": f"python scripts/undo_cleaning.py --result {result_path} --out {out}",
                   "limits": ([] if exact is not None else
                              ["original.json was unavailable; byte-level equivalence was not verified"])}
        if exact is False:
            receipt["limits"] = ["restored rows differ from original.json; inspect ledger drift"]
        (out / "restoration.json").write_text(json.dumps(receipt, ensure_ascii=False, indent=2),
                                              encoding="utf-8")
        print(json.dumps(receipt, ensure_ascii=False))
        return 0 if exact is True else 3 if exact is None else 5
    except Exception as exc:
        try:
            out.mkdir(parents=True, exist_ok=True)
            failure = {"status": "undetermined", "case_id": None,
                       "findings": [{"rule": "clean.undo_refused", "severity": "high",
                                     "message": str(exc)}],
                       "limits": ["restoration was not completed"]}
            (out / "restoration.json").write_text(json.dumps(failure, ensure_ascii=False, indent=2),
                                                  encoding="utf-8")
            print(json.dumps(failure, ensure_ascii=False))
        except OSError:
            pass
        return 5


if __name__ == "__main__":
    raise SystemExit(main())
