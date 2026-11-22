"""Merge several per-route result.json files into one final case result.

A case can run several routes (draft, then structure, then format...); each
route writes its own result.json. The runtime contract needs ONE result.json
per case, so the merge is mechanical, not an Agent judgement call:

  status          strictest of the inputs (clean < review < blocked < undetermined)
  findings        concatenated; each finding gains a `route` key naming its source
  severity_counts recomputed from the merged findings, never carried over
  checked         per-route scope preserved under a `routes` mapping
  limits          concatenated with route attribution
  deliverables    union of the routes' deliverable lists, de-duplicated
  output_contract fields   union across inputs: a field one route derived carries
                  that value (first non-null in input order wins); a field no
                  route could derive stays null and is named in limits; two
                  routes disagreeing on a derived field is a conflict finding
  case_id         all inputs must agree; a mismatch is a high finding (blocked)

Refusal discipline matches the two audit CLIs: no input files, an input that is
not readable JSON, or an input that is not a JSON object each produce an
`undetermined` result.json and exit 5 — never a traceback, and never a silent
partial merge.

Exit codes: 0 clean, 3 review, 4 blocked, 5 undetermined.

    python merge_results.py --out /app/output/result.json \
        /app/work/routes/draft/result.json /app/work/routes/format/result.json
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

SCHEMA = "merge/v1"
_STRICT = ("clean", "review", "blocked", "undetermined")
_STRICT_RANK = {s: i for i, s in enumerate(_STRICT)}


def _strictest(statuses) -> str:
    worst = "clean"
    for s in statuses:
        if _STRICT_RANK.get(s, len(_STRICT)) > _STRICT_RANK[worst]:
            worst = s if s in _STRICT_RANK else "undetermined"
    return worst


def _refused(out_path: Path, message: str) -> dict:
    """The refusal every unmergeable request gets: an exit code, not a crash.

    It writes only the refusal record — no output_contract echo happens here,
    because nothing was audited and there is no spec to echo from.
    """
    result = {"schema_version": SCHEMA, "status": "undetermined",
              "findings": [{"rule": "audit.merge_refused", "severity": "high",
                            "message": message}],
              "severity_counts": {"high": 1},
              "limits": ["the merge could not be performed as requested"]}
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(result, ensure_ascii=False, indent=2),
                        encoding="utf-8")
    return result


def _route_label(path: Path) -> str:
    """A stable name for the route a result came from.

    Engine CLIs write `result.json`, so the parent directory usually carries
    the route identity; a differently-named file uses its own stem.
    """
    if path.stem == "result":
        return path.parent.name or path.stem
    return path.stem


def load_results(paths) -> tuple[list[dict], list[str]]:
    """Read every input result file; report the ones that cannot be read.

    Returns (records, errors): records are (label, path, data) triples for the
    readable inputs, errors are human-readable reasons for the rest. The caller
    refuses the whole merge when errors exist, mirroring the audit CLIs, where
    an unreadable spec is a refusal rather than a partial run.
    """
    records: list[dict] = []
    errors: list[str] = []
    for p in paths:
        path = Path(p)
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError, OSError) as exc:
            errors.append(f"{path}: not readable JSON ({exc})")
            continue
        if not isinstance(data, dict):
            errors.append(f"{path}: not a JSON object")
            continue
        records.append({"label": _route_label(path), "path": str(path), "data": data})
    return records, errors


def merge_results(records: list[dict]) -> dict:
    """Merge readable route records into one result dict (pure, no I/O)."""
    merged: dict = {"schema_version": SCHEMA}
    findings: list[dict] = []
    limits: list[str] = []
    deliverables: list = []
    contract_values: dict = {}
    contract_null: list[str] = []
    contract_conflicts: list[str] = []

    for rec in records:
        label, data = rec["label"], rec["data"]
        findings.extend(dict(f, route=label) for f in (data.get("findings") or [])
                        if isinstance(f, dict))
        for lim in (data.get("limits") or []):
            limits.append(f"[{label}] {lim}")
        dl = data.get("deliverables")
        if isinstance(dl, list):
            for item in dl:
                if item not in deliverables:
                    deliverables.append(item)
        for key, value in data.items():
            if key in ("schema_version", "findings", "severity_counts", "limits",
                       "status", "section", "checked", "case_id"):
                continue
            if value is None:
                if key not in contract_values:
                    contract_null.append(key)
                continue
            if key not in contract_values or contract_values[key] is None:
                contract_values[key] = value
            elif contract_values[key] != value and key not in contract_conflicts:
                contract_conflicts.append(key)

    merged["status"] = _strictest([rec["data"].get("status") or "undetermined"
                                   for rec in records])
    merged["sections"] = [rec["data"].get("section") for rec in records]
    merged["routes"] = [{"route": rec["label"], "path": rec.get("path", ""),
                         "status": rec["data"].get("status"),
                         "checked": rec["data"].get("checked")}
                        for rec in records]
    merged["findings"] = findings
    counts: dict[str, int] = {}
    for f in findings:
        sev = f.get("severity")
        if sev:
            counts[sev] = counts.get(sev, 0) + 1
    merged["severity_counts"] = counts
    merged["limits"] = limits
    merged["checked"] = {"routes": {rec["label"]: rec["data"].get("checked")
                                    for rec in records}}

    case_ids = {str(rec["data"].get("case_id")) for rec in records
                if rec["data"].get("case_id") is not None}
    if len(case_ids) > 1:
        merged["findings"].append({
            "rule": "merge.case_id_mismatch", "severity": "high",
            "message": "route results carry different case_id values, so they are "
                       "not runs of one case; the merged deliverable is untrustworthy",
            "case_ids": sorted(case_ids)})
        merged["status"] = max(merged["status"], "blocked", key=_STRICT_RANK.get)
        merged["limits"].append("case_id mismatch between routes — check which "
                                "routes were actually run for this case")
        counts["high"] = counts.get("high", 0) + 1
        merged["severity_counts"] = counts
    elif case_ids:
        merged["case_id"] = sorted(case_ids)[0]

    if contract_conflicts:
        for key in contract_conflicts:
            merged["findings"].append({
                "rule": "merge.field_conflict", "severity": "medium",
                "message": "two routes derived different values for the same "
                           "output_contract field; the first non-null value is kept",
                "field": key})
            merged["limits"].append(
                f"output_contract field '{key}' had conflicting values across "
                f"routes; the first non-null value is kept")
    merged["severity_counts"] = counts
    for key, value in contract_values.items():
        merged[key] = value
    for key in contract_null:
        if key not in merged:
            merged[key] = None
            merged["limits"].append(
                f"output_contract field '{key}' was not derivable by any route")
    if deliverables:
        merged["deliverables"] = deliverables
    return merged


def merge_paths(paths, out_path) -> dict:
    """Load, merge and write; the CLI's one entry point."""
    records, errors = load_results(paths)
    if errors or not records:
        detail = "; ".join(errors) if errors else "no input result files were given"
        return _refused(out_path, f"route results unreadable or missing: {detail}")
    result = merge_results(records)
    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return result


def main(argv=None) -> int:
    import argparse
    ap = argparse.ArgumentParser(prog="merge_results", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("results", nargs="*", help="per-route result.json paths")
    ap.add_argument("--out", required=True, help="path of the merged result.json")
    a = ap.parse_args(argv)
    r = merge_paths(a.results, a.out)
    print(json.dumps({"status": r.get("status"),
                      "findings": [f["rule"] for f in r.get("findings", [])],
                      "routes": [x.get("route") for x in r.get("routes", [])],
                      "wrote": str(a.out)}, ensure_ascii=False))
    return {"clean": 0, "review": 3, "blocked": 4, "undetermined": 5}.get(r.get("status"), 1)


if __name__ == "__main__":
    raise SystemExit(main())
