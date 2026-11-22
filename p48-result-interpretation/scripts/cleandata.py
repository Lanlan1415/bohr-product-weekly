"""CLI: clean an experiment data table, then audit its interpretation entries.

Two passes, one result:

  1. the rule-driven cleaning pass (missing vs zero, units, duplicates, and the
     plausible-range flags that feed the anomaly judgement)
  2. the interpretation audit — every entry in spec.observations is checked
     against the table: cited values and baselines must exist in the data, every
     anomaly flagged by the physical range or the distribution diagnostic must
     carry a keep/drop/cap explanation, and a causal explanation must record the
     cause it claims

Refusal discipline: an unreadable spec, or a case with no rows at all, is refused
with exit 5 and a written result.json — never a traceback. Re-running the exact
same input into the same output directory is refused (exit 4) so a second pass can
never stack on the first. The original rows are preserved verbatim beside the
result, and the cleaned table is written as cleaned.csv.
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
import interp as I  # noqa: E402


def _load_rows(spec_path: Path, spec: dict) -> tuple[list[dict], str]:
    """Rows come from the spec's rows key or a table file the spec points at."""
    rows = spec.get("rows")
    if rows is not None:
        return [r for r in rows if isinstance(r, dict)], "inline"
    table = spec.get("table_path")
    if not table:
        return [], "none"
    p = Path(table)
    if not p.exists():
        return [], "missing"
    raw = p.read_text(encoding="utf-8-sig", errors="replace")
    first = raw.splitlines()[0] if raw.strip() else ""
    delim = "\t" if first.count("\t") > first.count(",") else ","
    parsed = list(csv.DictReader(io.StringIO(raw), delimiter=delim))
    return [r for r in parsed if isinstance(r, dict)], str(table)


def run(rows: list[dict], spec: dict) -> dict:
    """Cleaning pass + interpretation audit, merged into one result (no file IO)."""
    result = C.clean(rows, spec)
    interp_findings, summary = I.audit_interpretation(
        result["cleaned_table"], spec, clean_result=result)
    result["findings"] = list(result.get("findings") or []) + interp_findings
    counts: dict[str, int] = {}
    for f in result["findings"]:
        counts[f["severity"]] = counts.get(f["severity"], 0) + 1
    result["severity_counts"] = counts
    result["status"] = ("blocked" if counts.get("high")
                        else "review" if counts else "clean")
    result["interpretation_audit"] = summary
    result["schema_version"] = "result-interp/v1"
    result["limits"] = list(summary.get("limits") or [])
    return result


def build_and_audit(spec_path: Path, out_dir: Path) -> dict:
    try:
        spec = json.loads(Path(spec_path).read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError, OSError) as exc:
        return _refused(out_dir, "the spec file is not readable JSON: " + str(exc))
    if not isinstance(spec, dict):
        return _refused(out_dir, "the spec file is not a JSON object")
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    rows, source = _load_rows(Path(spec_path), spec)
    if not rows:
        return _refused(out_dir,
                        "no rows to interpret: the case supplies neither an inline rows "
                        "list nor a readable table_path (" + source + ")")

    input_sha = hashlib.sha256(
        json.dumps(rows, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()[:16]
    prior = out_dir / "result.json"
    if prior.exists():
        try:
            prev = json.loads(prior.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            prev = {}
        if prev.get("original_sha256") == input_sha:
            result = {"schema_version": "result-interp/v1", "status": "blocked",
                      "findings": [{"rule": "clean.already_cleaned", "severity": "high",
                                    "message": "this exact input was already interpreted in "
                                               "this output directory; re-running it would "
                                               "stack a second pass on top of the first",
                                    "original_sha256": input_sha}],
                      "severity_counts": {"high": 1}, "original_sha256": input_sha}
            (out_dir / "result-refused.json").write_text(
                json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
            return result

    result = run(rows, spec)
    result["row_source"] = source
    result["spec"] = spec
    result["original_sha256"] = input_sha

    # Echo the case's contract: case_id at the top level, and every output_contract
    # field either carried by the result already, copied from the spec verbatim
    # (bulky inputs excluded), or filled as null with an honest limits note.
    cid = spec.get("case_id")
    if cid is not None:
        result["case_id"] = cid
    limits = result.setdefault("limits", [])
    oc = spec.get("output_contract")
    if isinstance(oc, dict):
        keys = list(oc.keys())
    elif isinstance(oc, list):
        keys = [str(k) for k in oc]
    else:
        keys = []
        if oc is not None:
            limits.append("output_contract is neither an object nor a list of "
                          "field names, so no contract fields were echoed")
    _bulky = ("output_contract", "section", "rows", "table_path", "spec", "text",
              "observations")
    for key in keys:
        if key in result:
            continue
        if key in spec and key not in _bulky:
            result[key] = spec[key]
            continue
        result[key] = None
        limits.append(f"output_contract field '{key}' was not derivable by this audit")

    (out_dir / "original.json").write_text(
        json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    if result.get("cleaned_table"):
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
    result = {"schema_version": "result-interp/v1", "status": "undetermined",
              "findings": [{"rule": "clean.spec_unreadable", "severity": "high",
                            "message": message}],
              "limits": ["the case could not be run as declared"]}
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "result.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return result


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="cleandata", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--spec", required=True, help="case spec JSON")
    ap.add_argument("--out", required=True, help="output directory")
    a = ap.parse_args(argv)
    r = build_and_audit(Path(a.spec), Path(a.out))
    print(json.dumps({"status": r["status"],
                      "findings": [f["rule"] for f in r["findings"]],
                      "interpretation_audit": r.get("interpretation_audit"),
                      "wrote": str(Path(a.out) / "result.json")}, ensure_ascii=False))
    return {"clean": 0, "review": 3, "blocked": 4, "undetermined": 5}.get(r["status"], 1)


if __name__ == "__main__":
    raise SystemExit(main())
