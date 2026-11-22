"""CLI: run the rule-driven data-quality pass and write result.json + cleaned table.

The original input is never overwritten: the original table's sha256 is recorded,
and the cleaned table is written beside the result as cleaned.csv. Re-running the
same input into the same output directory is refused (clean.already_cleaned, exit 4)
so an already-cleaned copy can never be silently re-cleaned on top of itself.

Unrunnable input never surfaces as a traceback: an unreadable or missing spec, a
non-object spec, a broken table_path and an audit crash all come back as status
"undetermined" (exit 5) with a result.json naming the case. The refusal path
lives in contract.py and deliberately does not run the contract echo.
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
import contract as K  # noqa: E402


def _load_rows(spec: dict) -> tuple[list[dict], str, str | None]:
    """Rows come from the spec's "rows" key or a table file the spec points at.

    Returns (rows, source, error). A hostile rows type degrades to the file
    path, and any read failure is a message rather than a raise.
    """
    rows = spec.get("rows")
    if isinstance(rows, list):
        return ([r for r in rows if isinstance(r, dict)], "inline", None)
    if rows is not None and not isinstance(rows, list):
        # A dict or string under rows is a spec authoring error, not a table;
        # fall through to table_path so the caller's message stays accurate.
        pass
    table = spec.get("table_path")
    if not table or not isinstance(table, str):
        return [], "none", None
    p = Path(table)
    if not p.exists():
        return [], "missing", None
    try:
        raw = p.read_text(encoding="utf-8-sig", errors="replace")
    except OSError as exc:
        return [], str(table), f"the table file could not be read: {exc}"
    if not raw.strip():
        return [], str(table), None
    first = raw.splitlines()[0]
    delim = "\t" if first.count("\t") > first.count(",") else ","
    parsed = list(csv.DictReader(io.StringIO(raw), delimiter=delim))
    return ([r for r in parsed if isinstance(r, dict)], str(table), None)


def build_and_audit(spec_path: Path, out_dir: Path) -> dict:
    spec, err = K.load_spec(spec_path)
    if err:
        return K.refused(out_dir, err)
    if not isinstance(spec, dict):
        return K.refused(out_dir, "the spec file is valid JSON but not an object")
    out_dir = Path(out_dir)
    try:
        out_dir.mkdir(parents=True, exist_ok=True)
    except OSError:
        return K.refused(out_dir, "the output directory could not be created", spec)

    rows, source, load_err = _load_rows(spec)
    if load_err:
        return K.refused(out_dir, load_err, spec)
    if not rows:
        return K.refused(
            out_dir,
            "no rows to clean: the case supplies neither a readable inline rows list nor a "
            "readable table_path (" + source + ")", spec)

    input_sha = hashlib.sha256(
        json.dumps(rows, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()[:16]
    prior = out_dir / "result.json"
    if prior.exists():
        try:
            prev = json.loads(prior.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError, OSError):
            prev = {}
        if prev.get("original_sha256") == input_sha:
            result = {"schema_version": "data-quality/v1", "status": "blocked",
                      "findings": [{"rule": "clean.already_cleaned", "severity": "high",
                                    "message": "this exact input was already cleaned into this "
                                               "output directory; re-cleaning it would stack a "
                                               "second pass on top of the first",
                                    "original_sha256": input_sha}],
                      "severity_counts": {"high": 1}, "original_sha256": input_sha,
                      "limits": ["re-cleaning the same input into the same directory is refused"]}
            cid = spec.get("case_id")
            if cid is not None:
                result["case_id"] = cid
            # The first run's full result stays intact; the refusal is recorded beside it.
            try:
                (out_dir / "result-refused.json").write_text(
                    json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
            except OSError:
                pass
            return result

    try:
        result = C.clean(rows, spec)
    except Exception as exc:  # a rule bug must never surface as a caller-side traceback
        return K.refused(out_dir, f"the cleaning pass failed on this spec and was refused: {exc}",
                         spec)
    result["schema_version"] = "data-quality/v1"
    result["row_source"] = source
    result["spec"] = spec

    limits: list = []
    cid = spec.get("case_id")
    if cid is not None:
        result["case_id"] = cid
    K.echo_contract(spec, result, limits)
    result["limits"] = limits

    # The original is preserved verbatim beside the result — a cleaning pass that
    # cannot show the before is not reviewable.
    try:
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
    except OSError as exc:
        result["status"] = "undetermined"
        result["limits"] = result["limits"] + [f"outputs could not be written: {exc}"]
    return result


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="dataquality", description=__doc__)
    ap.add_argument("--spec", required=True, help="case spec JSON")
    ap.add_argument("--out", required=True, help="output directory")
    a = ap.parse_args(argv)
    r = build_and_audit(Path(a.spec), Path(a.out))
    print(json.dumps({"status": r.get("status"),
                      "findings": [f["rule"] for f in r.get("findings", [])],
                      "idempotent": r.get("idempotent"),
                      "wrote": str(Path(a.out) / "result.json")}, ensure_ascii=False))
    return {"clean": 0, "review": 3, "blocked": 4, "undetermined": 5}.get(r.get("status"), 1)


if __name__ == "__main__":
    raise SystemExit(main())
