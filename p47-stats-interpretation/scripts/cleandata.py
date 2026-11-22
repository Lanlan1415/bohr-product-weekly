"""CLI: clean a research table, then audit its declared statistical claims.

Two passes, one result:

  1. the rule-driven cleaning pass (missing vs zero, unit conversion, duplicates)
  2. the stats layer — descriptives, Welch t / one-way ANOVA, effect sizes and
     confidence intervals recomputed from the rows, IQR outliers, assumption
     advisories — plus the claim audit: every claim in spec.stats is checked
     against the recomputed group statistics (direction, significance language,
     computed-number citation, claimed-p plausibility)

The result carries, per the task's output requirements:

  case_id            the input identifier, echoed from the spec (or --case file)
  output_contract_*  every field the case's output_contract names (kept when the
                     result already carries it, copied verbatim when the spec
                     supplies it, null + a limit note when it cannot be derived)
  descriptives       per-column n / centre / spread / quantiles / shape / units
  stats_audit        the recomputed claim records (t, df, p, effect size, CI)
  outliers           Tukey-fence outliers, listed not deleted
  charts             deterministic chart recommendation per analysis shape
  run_manifest       engine, interpreter, input fingerprint (reproducibility)
  pending_review     what the engine would not decide by itself

Refusal discipline: an unreadable spec, a non-object spec, rows that are not a
list, or a case with no rows at all is refused with exit 5 and a written
result.json — never a traceback. Re-running the exact same input into the same
output directory is refused (exit 4) so a second pass can never stack on the
first. The original rows are preserved verbatim beside the result, and the
cleaned table is written as cleaned.csv.

Exit codes: 0 clean, 3 review, 4 blocked, 5 undetermined.
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
import statsinterp as S  # noqa: E402

# Fields that are bulky inputs rather than results: never copied wholesale into
# the result by the contract echo (descriptives, stats_audit and the charts carry
# their audited substance already).
_BULKY = {"output_contract", "spec", "rows", "columns", "table_path", "stats",
          "key_columns", "value_columns", "missing_tokens", "group_col",
          "field_aliases", "synonyms", "source_column", "quality_report"}


def _load_rows(spec_path: Path, spec: dict) -> tuple[list, str]:
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


def _refused(out_dir: Path, message: str, rule: str = "clean.spec_unreadable") -> dict:
    """The undetermined refusal every unrunnable case gets: an exit code, not a crash.

    Contract echo is deliberately NOT applied here: the case could not be run as
    declared, so echoing a contract into a refused result would dress the refusal
    up as a completed run.
    """
    result = {"schema_version": "stats-interp/v2", "status": "undetermined",
              "findings": [{"rule": rule, "severity": "high",
                            "message": message}],
              "limits": ["the case could not be run as declared"]}
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "result.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return result


def _echo_contract(result: dict, spec: dict) -> dict:
    """Echo case_id and every output_contract field into the result.

    A field the result already carries is kept as computed; a field the spec
    supplies (and that is not a bulky input) passes through verbatim; anything
    else is null with a limits note — never a fabricated value.
    """
    if not isinstance(spec, dict):
        return result
    cid = spec.get("case_id")
    if cid is not None and "case_id" not in result:
        result["case_id"] = cid
    limits = result.setdefault("limits", [])
    contract = spec.get("output_contract")
    if contract is None:
        return result
    if not isinstance(contract, dict):
        limits.append("output_contract is not an object, so no field was echoed")
        return result
    for key in contract:
        if key in result:
            continue
        if key in spec and key not in _BULKY:
            result[key] = spec[key]
            continue
        result[key] = None
        limits.append(f"output_contract field '{key}' was not derivable by this audit")
    return result


def _merge_case(spec: dict, case_path) -> dict:
    """Copy case_id / output_contract from the case file when the spec omits them.

    The runtime case file (/input/case.json) is the authoritative carrier of both;
    an unreadable case file is never fatal — the run proceeds without the echo.
    """
    if case_path is None:
        return spec
    try:
        case = json.loads(Path(case_path).read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return spec
    if not isinstance(case, dict):
        return spec
    if spec.get("case_id") is None and case.get("case_id") is not None:
        spec["case_id"] = case.get("case_id")
    if spec.get("output_contract") is None and case.get("output_contract") is not None:
        spec["output_contract"] = case.get("output_contract")
    return spec


def run(rows: list, spec: dict) -> dict:
    """Cleaning pass + descriptive/inferential layer + claim audit (no file IO)."""
    result = C.clean(rows, spec)
    stats_findings, computed = S.audit_stats(rows, spec)
    result["stats_audit"] = {
        "n_claims": len(spec.get("stats") or []) if isinstance(spec.get("stats"), list) else 0,
        "claims": computed,
    }

    # the deliverable layer: descriptives, outliers, charts, reproducibility
    col_defs = [c for c in (spec.get("columns") or [])
                if isinstance(c, dict) and c.get("name")]
    semantic_of = {str(c["name"]): str(c.get("semantic") or "") for c in col_defs}
    columns = [str(c["name"]) for c in col_defs]
    descriptives = [S.describe_column(rows, name, semantic_of.get(name))
                    for name in columns]
    result["descriptives"] = descriptives
    outliers = []
    for name in columns:
        if str(semantic_of.get(name) or "").strip().lower() in ("categorical", "text", "id"):
            continue
        rec = S.outlier_rows_iqr(rows, name)
        if rec and rec["outliers"]:
            outliers.append(rec)
    result["outliers"] = outliers
    result["charts"] = S.recommend_charts(rows, spec)
    result["run_manifest"] = S.run_manifest(rows, spec)

    # outliers become medium findings: listed with row and value, never deleted
    for rec in outliers:
        stats_findings.append({
            "rule": "stats.outliers_iqr", "severity": "medium",
            "message": "values outside the 1.5 IQR fences; listed and kept — the "
                       "keep/drop decision is a human one",
            "column": rec["column"], "fences": [rec["lower_fence"], rec["upper_fence"]],
            "outliers": rec["outliers"][:20]})

    # shape advisories that do not depend on any claim: the rubric asks for
    # distribution checks even before an interpretation is drafted. Groups the
    # claim audit already flagged are not flagged twice.
    flagged = {f.get("group") for f in stats_findings
               if f.get("rule") == "stats.assumption_normality"}
    group_col = str(spec.get("group_col") or "group")
    group_values = sorted({str(r.get(group_col, "")).strip() for r in rows
                           if isinstance(r, dict) and str(r.get(group_col, "")).strip()})
    for name in columns:
        for gname in group_values:
            if gname in flagged:
                continue
            gvals = S.column_values([r for r in rows if isinstance(r, dict)
                                     and str(r.get(group_col, "")).strip() == gname], name)
            if len(gvals) < 5:
                continue
            mo = S._moments(gvals)
            if abs(mo["skew"]) > 1.0 or (len(gvals) >= 8 and abs(mo["excess_kurtosis"]) > 1.0):
                stats_findings.append({
                    "rule": "stats.assumption_normality", "severity": "medium",
                    "message": "strong skew/kurtosis indicators in a small sample; "
                               "prefer a non-parametric test or verify the distribution "
                               "before reading a parametric p value",
                    "group": gname, "column": name, "n": len(gvals),
                    "skew": round(mo["skew"], 4),
                    "excess_kurtosis": round(mo["excess_kurtosis"], 4)})
                flagged.add(gname)

    result["findings"] = list(result.get("findings") or []) + stats_findings
    counts: dict[str, int] = {}
    for f in result["findings"]:
        counts[f["severity"]] = counts.get(f["severity"], 0) + 1
    result["severity_counts"] = counts
    result["status"] = ("blocked" if counts.get("high")
                        else "review" if counts else "clean")

    # the to-confirm list: unusable metric cells, Tukey outliers, duplicate
    # experiments, and every advisory finding's subject matter
    pending = []
    for rec in descriptives:
        if rec.get("n_unparsed"):
            pending.append({"column": rec["column"], "what": "unparsed",
                            "count": rec["n_unparsed"],
                            "why": "cells that could not be parsed; kept as named gaps"})
        if rec.get("n_missing"):
            pending.append({"column": rec["column"], "what": "missing",
                            "count": rec["n_missing"],
                            "why": "not-reported values; missing, never zero"})
    for rec in outliers:
        pending.append({"column": rec["column"], "what": "outlier",
                        "rows": [o["row"] for o in rec["outliers"]],
                        "why": "outside the 1.5 IQR fences; kept, decision is human"})
    if result.get("duplicates", {}).get("duplicate_experiments"):
        pending.append({"what": "duplicate_experiment",
                        "rows": [de["rows"] for de in result["duplicates"]
                                 ["rule_duplicate_experiments"]],
                        "why": "same entity, different values; merging needs a stated rule"})
    result["pending_review"] = pending
    result["schema_version"] = "stats-interp/v2"
    return result


def build_and_audit(spec_path: Path, out_dir: Path, case_path=None) -> dict:
    try:
        spec = json.loads(Path(spec_path).read_text(encoding="utf-8-sig"))
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        return _refused(out_dir, "the spec file is not readable JSON: " + str(exc))
    except OSError:
        return _refused(out_dir, "the spec file could not be read (missing or inaccessible)")
    if not isinstance(spec, dict):
        return _refused(out_dir, "the spec file is not a JSON object")
    spec = _merge_case(spec, case_path)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    rows = spec.get("rows")
    if rows is not None and not isinstance(rows, list):
        return _refused(out_dir, "spec.rows is not a list, so there is no table to analyse")
    rows, source = _load_rows(Path(spec_path), spec)
    if not rows:
        return _refused(out_dir,
                        "no rows to analyse: the case supplies neither an inline rows list "
                        "nor a readable table_path (" + source + ")")

    input_sha = hashlib.sha256(
        json.dumps(rows, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()[:16]
    prior = out_dir / "result.json"
    if prior.exists():
        try:
            prev = json.loads(prior.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            prev = {}
        if prev.get("original_sha256") == input_sha:
            result = {"schema_version": "stats-interp/v2", "status": "blocked",
                      "findings": [{"rule": "clean.already_cleaned", "severity": "high",
                                    "message": "this exact input was already analysed into "
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
    _echo_contract(result, spec)

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


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="cleandata", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--spec", required=True, help="case spec JSON")
    ap.add_argument("--out", required=True, help="output directory")
    ap.add_argument("--case", default=None,
                    help="runtime case file (/input/case.json) supplying case_id and "
                         "output_contract when the spec omits them")
    a = ap.parse_args(argv)
    r = build_and_audit(Path(a.spec), Path(a.out), a.case)
    print(json.dumps({"status": r["status"],
                      "case_id": r.get("case_id"),
                      "findings": [f["rule"] for f in r["findings"]],
                      "stats_audit": r.get("stats_audit"),
                      "wrote": str(Path(a.out) / "result.json")}, ensure_ascii=False))
    return {"clean": 0, "review": 3, "blocked": 4, "undetermined": 5}.get(r["status"], 1)


if __name__ == "__main__":
    raise SystemExit(main())
