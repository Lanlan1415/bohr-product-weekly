"""CLI: audit a database query result table and write result.json + the cleaned table.

The query itself runs upstream; this pass takes the returned rows (inline or via a
table_path the spec points at — CSV/TSV/JSON) and runs the rule-driven cleaning and
quality statistics over them, so the numbers in the analysis report are computed from
the table instead of asserted.

The original input is never overwritten: the original table's sha256 is recorded, and
the cleaned table is written beside the result as cleaned.csv. Re-running the same
input into the same output directory is refused (clean.already_cleaned, exit 4) so an
already-cleaned copy can never be silently re-cleaned on top of itself.
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
import cleaning as C  # noqa: E402


def _load_rows(spec_path: Path, spec: dict) -> tuple[list[dict], str]:
    """Rows come from the spec's "rows" key or a result table the spec points at."""
    rows = spec.get("rows")
    if rows is not None:
        return [r for r in rows if isinstance(r, dict)], "inline"
    table = spec.get("table_path")
    if not table:
        return [], "none"
    p = Path(table)
    if not p.is_absolute():
        p = Path(spec_path).parent / table
    if not p.exists():
        return [], "missing"
    raw = p.read_text(encoding="utf-8-sig", errors="replace")
    first = raw.splitlines()[0] if raw.strip() else ""
    delim = "\t" if first.count("\t") > first.count(",") else ","
    parsed = list(csv.DictReader(io.StringIO(raw), delimiter=delim))
    return [r for r in parsed if isinstance(r, dict)], str(table)


def build_and_audit(spec_path: Path, out_dir: Path) -> dict:
    try:
        spec = json.loads(Path(spec_path).read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        return _refused(out_dir, "the spec file is not readable JSON: " + str(exc))
    if not isinstance(spec, dict):
        return _refused(out_dir, "the spec file is not a JSON object")
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    rows, source = _load_rows(Path(spec_path), spec)
    if not rows:
        return _refused(out_dir,
                        "no rows to audit: the case supplies neither an inline rows list nor a "
                        "readable table_path (" + source + ")")

    input_sha = hashlib.sha256(
        json.dumps(rows, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()[:16]
    prior = out_dir / "result.json"
    if prior.exists():
        try:
            prev = json.loads(prior.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            prev = {}
        if prev.get("original_sha256") == input_sha:
            result = {"schema_version": "cleandata/v1", "status": "blocked",
                      "findings": [{"rule": "clean.already_cleaned", "severity": "high",
                                    "message": "this exact input was already audited into this "
                                               "output directory; re-running it would stack a "
                                               "second pass on top of the first",
                                    "original_sha256": input_sha}],
                      "severity_counts": {"high": 1}, "original_sha256": input_sha}
            # The first run's full result stays intact; the refusal is recorded beside it.
            (out_dir / "result-refused.json").write_text(
                json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
            return result

    result = C.clean(rows, spec)
    result["schema_version"] = "cleandata/v1"
    result["row_source"] = source
    result["spec"] = spec

    # Echo the case's output_contract: engine value > spec carried > null + limits.
    cid = spec.get("case_id")
    if cid is not None:
        result["case_id"] = cid
    _BULKY = ("output_contract", "section", "spec", "rows", "table_path", "text", "raw")
    for key in (spec.get("output_contract") or []):
        if key in result:
            continue
        if key in spec and key not in _BULKY:
            result[key] = spec[key]
            continue
        result[key] = None
        result.setdefault("limits", []).append(
            f"output_contract field '{key}' was not derivable by this audit")

    # The original is preserved verbatim beside the result — an audit pass that
    # cannot show the before is not reviewable.
    (out_dir / "original.json").write_text(
        json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    if result["cleaned_table"]:
        cols = sorted({k for r in result["cleaned_table"] for k in r})
        buf = io.StringIO()
        w = csv.DictWriter(buf, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        for r in result["cleaned_table"]:
            w.writerow(r)
        (out_dir / "cleaned.csv").write_text(buf.getvalue(), encoding="utf-8")

    (out_dir / "result.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return result


def _refused(out_dir: Path, message: str) -> dict:
    result = {"schema_version": "cleandata/v1", "status": "undetermined",
              "findings": [{"rule": "clean.spec_unreadable", "severity": "high",
                            "message": message}],
              "limits": ["the case could not be run as declared"]}
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "result.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return result


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="cleandata", description=__doc__)
    ap.add_argument("--spec", required=True, help="case spec JSON")
    ap.add_argument("--out", required=True, help="output directory")
    a = ap.parse_args(argv)
    r = build_and_audit(Path(a.spec), Path(a.out))
    print(json.dumps({"status": r["status"],
                      "findings": [f["rule"] for f in r["findings"]],
                      "rows": r.get("rows"), "idempotent": r.get("idempotent"),
                      "wrote": str(Path(a.out) / "result.json")}, ensure_ascii=False))
    return {"clean": 0, "review": 3, "blocked": 4, "undetermined": 5}.get(r["status"], 1)


if __name__ == "__main__":
    raise SystemExit(main())
