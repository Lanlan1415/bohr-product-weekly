"""Clean a table, compute declared analyses, and audit statistical prose.

Direct analyses use the actual cleaned table, not the pre-conversion cells.
CSV/TSV and read-only SQLite are supported. Every readable case preserves
case_id and all output_contract fields, including structured refusals.
Exit codes: 0 clean, 3 review, 4 blocked, 5 undetermined.
"""
from __future__ import annotations

import argparse
import copy
import csv
import hashlib
import io
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import cleaning as C  # noqa: E402
import statscore as SC  # noqa: E402
import statsinterp as S  # noqa: E402
import tableio  # noqa: E402

_BULKY = {"output_contract", "spec", "rows", "columns", "table_path", "sqlite_path",
          "database_path", "db_path", "query", "sql", "stats", "analyses", "analysis",
          "correlations", "key_columns", "value_columns", "missing_tokens", "group_col",
          "field_aliases", "synonyms", "source_column", "quality_report"}
_DERIVED = {"cleaned_table": "cleaned_table", "descriptives": "descriptives",
            "stats_audit": "stats_audit", "analysis_results": "analysis_results",
            "statistical_analysis": "analysis_results", "analyses": "analysis_results",
            "correlations": "correlations", "assumption_diagnostics": "assumption_diagnostics",
            "result_text": "result_text", "power_and_sample_size": "power_and_sample_size",
            "data_dictionary": "data_dictionary", "changes": "changes",
            "quality_report": "quality_report", "run_manifest": "run_manifest"}


def _load_case(case_path):
    if case_path is None:
        return None
    try:
        case = json.loads(Path(case_path).read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return None
    return case if isinstance(case, dict) else None


def _refused(out_dir: Path, message: str, spec=None, rule="clean.spec_unreadable") -> dict:
    result = {"schema_version": "stats-interp/v3", "status": "undetermined",
              "case_id": spec.get("case_id") if isinstance(spec, dict) else None,
              "findings": [{"rule": rule, "severity": "high", "message": str(message)}],
              "severity_counts": {"high": 1},
              "limits": ["the case could not be run as declared"]}
    if isinstance(spec, dict):
        _echo_contract(result, spec)
    else:
        result["limits"].append("case metadata was unavailable; case_id could not be recovered")
    try:
        out_dir = Path(out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2),
                                             encoding="utf-8")
    except OSError:
        pass
    return result


def _echo_contract(result: dict, spec: dict) -> dict:
    if not isinstance(spec, dict):
        return result
    result.setdefault("case_id", spec.get("case_id"))
    limits = result.setdefault("limits", [])
    contract = spec.get("output_contract")
    if isinstance(contract, dict):
        keys = [str(k) for k in contract]
    elif isinstance(contract, list):
        keys = [k for k in contract if isinstance(k, str)]
        if len(keys) != len(contract):
            limits.append("non-string output_contract entries were invalid")
    elif contract is None:
        return result
    else:
        limits.append("output_contract was neither an object nor a list")
        result["output_contract_fields"] = []
        return result
    for key in keys:
        if key in result:
            continue
        if key in spec and key not in _BULKY:
            result[key] = spec[key]
            continue
        source = _DERIVED.get(key)
        if result.get("status") != "undetermined" and source in result:
            result[key] = result[source]
            continue
        result[key] = None
        limits.append(f"output_contract field '{key}' was not derivable in status {result.get('status')}")
    result["output_contract_fields"] = keys
    return result


def _merge_case(spec: dict, case: dict | None) -> dict:
    if not isinstance(case, dict):
        return spec
    for key in ("case_id", "output_contract"):
        if spec.get(key) is None and case.get(key) is not None:
            spec[key] = case[key]
    contract = spec.get("output_contract")
    keys = contract.keys() if isinstance(contract, dict) else contract if isinstance(contract, list) else []
    for key in keys:
        if isinstance(key, str) and key not in spec and key in case and key not in _BULKY:
            spec[key] = case[key]
    return spec


def _apply_claim_corrections(computed, spec):
    """Compute a real adjustment for recomputed p values across claim families."""
    eligible = [(i, rec) for i, rec in enumerate(computed)
                if isinstance(rec.get("p_computed"), (int, float))
                and 0 <= rec["p_computed"] <= 1]
    if len(eligible) < 2:
        return None, []
    claims = spec.get("stats") or []
    declared = {str(c.get("correction")).lower() for c in claims
                if isinstance(c, dict) and c.get("correction")}
    method = next(iter(declared)) if len(declared) == 1 else "holm"
    try:
        adjusted = SC.adjust_pvalues([rec["p_computed"] for _, rec in eligible], method)
    except ValueError:
        adjusted = SC.adjust_pvalues([rec["p_computed"] for _, rec in eligible], "holm")
        method = "holm"
    findings = []
    for (index, rec), adjustment in zip(eligible, adjusted):
        rec["p_adjusted"] = adjustment["p_adjusted"]
        rec["significant_adjusted"] = adjustment["reject"]
        rec["correction_applied"] = adjustment
        claimed_sig = rec.get("claimed_significant")
        if claimed_sig is not None and claimed_sig != adjustment["reject"]:
            findings.append({"rule": "stats.adjusted_significance_mismatch", "severity": "medium",
                             "claim_index": index,
                             "message": "the prose's significance matches the raw claimed p but not the multiplicity-adjusted result",
                             "p_adjusted": adjustment["p_adjusted"], "method": method})
    return {"family": "all recomputed pairwise claim p values", "m": len(eligible),
            "method": method, "declared_methods": sorted(declared),
            "applied_by": "declared" if len(declared) == 1 else "engine_default_holm",
            "adjustments": adjusted}, findings


def _prepare_analysis_rows(rows, spec):
    """Resolve duplicates explicitly before any inferential n can be computed."""
    dupes = C.find_duplicates(rows, spec.get("key_columns") or [], spec.get("value_columns") or [])
    policy = str(spec.get("duplicate_policy") or "review").lower()
    exact = int(dupes.get("duplicate_records") or 0)
    experiments = int(dupes.get("duplicate_experiments") or 0)
    drop = set()
    if policy == "drop_exact_copies":
        for group in dupes.get("rule_duplicate_records", []):
            indices = sorted(i for i in group.get("rows", []) if isinstance(i, int))
            drop.update(indices[1:])
    prepared = [row for i, row in enumerate(rows) if i not in drop]
    justification = str(spec.get("duplicate_justification") or "").strip()
    justified = policy in ("keep_as_independent", "keep_replicates") and bool(justification)
    restriction = None
    if policy not in ("review", "drop_exact_copies", "keep_as_independent", "keep_replicates"):
        restriction = "unknown duplicate_policy; choose review, drop_exact_copies or a justified keep policy"
    elif experiments and not justified:
        restriction = ("duplicate experiments/share entity keys remain; declare an explicit justified replicate role "
                       "before treating rows as independent")
    elif exact and policy == "review":
        restriction = ("exact duplicate records detected; set duplicate_policy=drop_exact_copies after reviewing the "
                       "ledger, or provide a justified keep policy")
    metadata = {"duplicate_policy": policy, "duplicate_record_groups": exact,
                "duplicate_experiment_groups": experiments, "duplicate_rows_removed": len(drop),
                "dropped_duplicate_rows_zero_based": sorted(drop),
                "duplicate_justification": justification or None,
                "duplicate_census": "key_based" if spec.get("key_columns") else "not_evaluated_no_keys"}
    return prepared, restriction, metadata


def run(rows: list, original_spec: dict) -> dict:
    """Cleaning + direct computations + descriptives + prose audit (no file IO)."""
    spec = copy.deepcopy(original_spec)
    inferred = False
    if not isinstance(spec.get("columns"), list) or not spec.get("columns"):
        spec["columns"] = tableio.infer_columns(rows)
        inferred = True
    result = C.clean(rows, spec)
    cleaned_rows = result.get("cleaned_table") or []
    analysis_rows, duplicate_restriction, duplicate_meta = _prepare_analysis_rows(cleaned_rows, spec)
    analysis_spec = spec
    if duplicate_restriction:
        analysis_spec = copy.deepcopy(spec)
        analysis_spec["_analysis_restriction"] = duplicate_restriction
    result["analysis_table"] = analysis_rows
    result["data_dictionary"] = {"columns": copy.deepcopy(spec.get("columns") or []),
                                 "source": "conservatively inferred because no dictionary was supplied" if inferred
                                           else "case-declared spec.columns",
                                 "key_columns": list(spec.get("key_columns") or []),
                                 "inference_limit": None if not inferred else
                                     "keys, units and causal/design roles are never inferred; declare them explicitly"}
    stats_findings, computed = S.audit_stats(analysis_rows, spec)
    result["stats_audit"] = {
        "n_claims": len(spec.get("stats") or []) if isinstance(spec.get("stats"), list) else 0,
        "claims": computed,
    }
    claim_family, correction_findings = _apply_claim_corrections(computed, spec)
    result["claim_multiplicity"] = claim_family
    stats_findings.extend(correction_findings)

    if duplicate_restriction and (spec.get("stats") or spec.get("analyses") or spec.get("analysis") or spec.get("correlations")):
        stats_findings.append({"rule": "stats.duplicates_unresolved", "severity": "high",
                               "message": duplicate_restriction,
                               **duplicate_meta})
    direct = SC.run_statistical(analysis_rows, analysis_spec)
    result["analysis_results"] = direct["analyses"]
    result["correlations"] = direct["correlations"]
    result["multiple_testing_families"] = direct["multiple_testing_families"]
    result["result_text"] = ([rec.get("result_text") for rec in direct["analyses"] if rec.get("result_text")]
                             + [rec.get("result_text") for rec in direct["correlations"] if rec.get("result_text")])
    result["assumption_diagnostics"] = [{"request_index": rec.get("request_index"),
                                         "test": rec.get("test"), "assumptions": rec.get("assumptions")}
                                        for rec in direct["analyses"] if rec.get("assumptions")]
    result["power_and_sample_size"] = [{"request_index": rec.get("request_index"), **rec["power_and_sample_size"]}
                                       for rec in direct["analyses"]]
    result["limits"] = list(direct["limitations"]) if direct["analyses"] or direct["correlations"] else []

    col_defs = [c for c in (spec.get("columns") or []) if isinstance(c, dict) and c.get("name")]
    semantic_of = {str(c["name"]): str(c.get("semantic") or "") for c in col_defs}
    columns = [str(c["name"]) for c in col_defs]
    descriptives = [S.describe_column(analysis_rows, name, semantic_of.get(name)) for name in columns]
    result["descriptives"] = descriptives
    outliers = []
    for name in columns:
        if str(semantic_of.get(name) or "").strip().lower() in ("categorical", "text", "id"):
            continue
        rec = S.outlier_rows_iqr(analysis_rows, name)
        if rec and rec["outliers"]:
            outliers.append(rec)
    result["outliers"] = outliers
    result["charts"] = S.recommend_charts(analysis_rows, spec)
    result["run_manifest"] = S.run_manifest(rows, spec)
    result["run_manifest"]["engine"] = "stats-interp/v3"
    result["run_manifest"]["analysis_input"] = "cleaned_table after declared unit/date/whitespace conversions"
    result["analysis_population"] = {"input_rows": len(rows), "cleaned_rows": len(cleaned_rows),
                                    "analysis_rows": len(analysis_rows), "missing_values_imputed": False,
                                    "duplicate_restriction": duplicate_restriction, **duplicate_meta,
                                    "rule": "per-analysis available values; exclusions are counted per request"}

    for rec in outliers:
        stats_findings.append({"rule": "stats.outliers_iqr", "severity": "medium",
                               "message": "values outside 1.5 IQR fences; listed and kept for human review",
                               "column": rec["column"], "fences": [rec["lower_fence"], rec["upper_fence"]],
                               "outliers": rec["outliers"][:20]})

    # Existing shape advisories remain as a guard even when no direct test is requested.
    flagged = {f.get("group") for f in stats_findings if f.get("rule") == "stats.assumption_normality"}
    group_col = str(spec.get("group_col") or "group")
    group_values = sorted({str(r.get(group_col, "")).strip() for r in analysis_rows
                           if isinstance(r, dict) and str(r.get(group_col, "")).strip()})
    for name in columns:
        for gname in group_values:
            if gname in flagged:
                continue
            gvals = S.column_values([r for r in analysis_rows if isinstance(r, dict)
                                     and str(r.get(group_col, "")).strip() == gname], name)
            if len(gvals) < 5:
                continue
            moments = S._moments(gvals)
            if abs(moments["skew"]) > 1.0 or (len(gvals) >= 8 and abs(moments["excess_kurtosis"]) > 1.0):
                stats_findings.append({"rule": "stats.assumption_normality", "severity": "medium",
                                       "message": "strong skew/kurtosis indicators; verify distribution before a parametric reading",
                                       "group": gname, "column": name, "n": len(gvals),
                                       "skew": round(moments["skew"], 4),
                                       "excess_kurtosis": round(moments["excess_kurtosis"], 4)})
                flagged.add(gname)

    stats_findings.extend(direct["findings"])
    result["findings"] = list(result.get("findings") or []) + stats_findings
    counts = {}
    for finding in result["findings"]:
        counts[finding["severity"]] = counts.get(finding["severity"], 0) + 1
    result["severity_counts"] = counts
    result["status"] = "blocked" if counts.get("high") else "review" if counts else "clean"

    pending = []
    for rec in descriptives:
        if rec.get("n_unparsed"):
            pending.append({"column": rec["column"], "what": "unparsed", "count": rec["n_unparsed"],
                            "why": "unparsed cells are named gaps, never zero"})
        if rec.get("n_missing"):
            pending.append({"column": rec["column"], "what": "missing", "count": rec["n_missing"],
                            "why": "not-reported values excluded and counted per analysis"})
    for rec in outliers:
        pending.append({"column": rec["column"], "what": "outlier",
                        "rows": [o["row"] for o in rec["outliers"]],
                        "why": "outside 1.5 IQR fences; kept for a documented decision"})
    if result.get("duplicates", {}).get("duplicate_experiments"):
        pending.append({"what": "duplicate_experiment",
                        "rows": [de["rows"] for de in result["duplicates"]["rule_duplicate_experiments"]],
                        "why": "same entity, different values; not merged or used to inflate n silently"})
    for rec in direct["analyses"]:
        if rec.get("status") != "computed":
            pending.append({"what": "analysis_undetermined", "request_index": rec.get("request_index"),
                            "why": rec.get("reason")})
    result["pending_review"] = pending
    result["schema_version"] = "stats-interp/v3"
    return result


def build_and_audit(spec_path: Path, out_dir: Path, case_path=None) -> dict:
    case = _load_case(case_path)
    try:
        spec = json.loads(Path(spec_path).read_text(encoding="utf-8-sig"))
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        return _refused(out_dir, "the spec file is not readable JSON: " + str(exc), case)
    except OSError:
        return _refused(out_dir, "the spec file could not be read (missing or inaccessible)", case)
    if not isinstance(spec, dict):
        return _refused(out_dir, "the spec file is not a JSON object", case)
    spec = _merge_case(spec, case)
    out_dir = Path(out_dir)
    try:
        out_dir.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        return _refused(out_dir, f"output directory could not be created: {exc}", spec)

    rows, source, input_metadata, load_error = tableio.load_table(spec)
    if load_error:
        return _refused(out_dir, load_error, spec)
    if not rows:
        return _refused(out_dir, f"no rows to analyse from inline/table/SQLite input ({source})", spec)

    input_sha = hashlib.sha256(json.dumps(rows, sort_keys=True, ensure_ascii=False)
                               .encode("utf-8")).hexdigest()[:16]
    prior = out_dir / "result.json"
    if prior.exists():
        try:
            prev = json.loads(prior.read_text(encoding="utf-8-sig"))
        except (json.JSONDecodeError, UnicodeDecodeError, OSError):
            prev = {}
        if prev.get("original_sha256") == input_sha:
            result = {"schema_version": "stats-interp/v3", "status": "blocked",
                      "case_id": spec.get("case_id"),
                      "findings": [{"rule": "clean.already_cleaned", "severity": "high",
                                    "message": "this exact input was already analysed here; first result left intact",
                                    "original_sha256": input_sha}],
                      "severity_counts": {"high": 1}, "original_sha256": input_sha,
                      "limits": ["re-analysis into the same directory is refused"]}
            _echo_contract(result, spec)
            try:
                (out_dir / "result-refused.json").write_text(json.dumps(result, ensure_ascii=False, indent=2),
                                                             encoding="utf-8")
            except OSError:
                pass
            return result

    try:
        result = run(rows, spec)
    except Exception as exc:
        return _refused(out_dir, f"analysis was refused after an internal validation failure: {exc}", spec,
                        rule="stats.internal_refused")
    result["row_source"] = source
    result["spec"] = spec
    result["original_sha256"] = input_sha
    result["input_metadata"] = input_metadata
    result["run_manifest"]["input_metadata"] = input_metadata
    if result.get("case_id") is None:
        result["case_id"] = spec.get("case_id")
    if result.get("case_id") is None:
        result.setdefault("limits", []).append("case_id was absent from spec and case metadata")
    _echo_contract(result, spec)
    result["limits"] = list(dict.fromkeys(result.get("limits") or []))

    try:
        (out_dir / "original.json").write_text(json.dumps(rows, ensure_ascii=False, indent=2),
                                               encoding="utf-8")
        if result.get("cleaned_table"):
            cols = sorted({k for r in result["cleaned_table"] for k in r})
            buf = io.StringIO(newline="")
            writer = csv.DictWriter(buf, fieldnames=cols, extrasaction="ignore", lineterminator="\n")
            writer.writeheader()
            writer.writerows(result["cleaned_table"])
            (out_dir / "cleaned.csv").write_text(buf.getvalue(), encoding="utf-8", newline="")
        if result.get("analysis_table") != result.get("cleaned_table") and result.get("analysis_table"):
            cols = sorted({k for r in result["analysis_table"] for k in r})
            buf = io.StringIO(newline="")
            writer = csv.DictWriter(buf, fieldnames=cols, extrasaction="ignore", lineterminator="\n")
            writer.writeheader()
            writer.writerows(result["analysis_table"])
            (out_dir / "analysis.csv").write_text(buf.getvalue(), encoding="utf-8", newline="")
        (out_dir / "analysis.json").write_text(json.dumps({
            "case_id": result.get("case_id"), "analysis_results": result["analysis_results"],
            "correlations": result["correlations"], "result_text": result["result_text"],
            "assumption_diagnostics": result["assumption_diagnostics"],
            "power_and_sample_size": result["power_and_sample_size"]}, ensure_ascii=False, indent=2),
            encoding="utf-8")
        (out_dir / "result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2,
                                                         allow_nan=False), encoding="utf-8")
    except (OSError, ValueError) as exc:
        return _refused(out_dir, f"outputs could not be written or serialised: {exc}", spec,
                        rule="stats.output_refused")
    return result


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="cleandata", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--spec", required=True, help="case spec JSON")
    ap.add_argument("--out", required=True, help="output directory")
    ap.add_argument("--case", default=None, help="original /input/case.json for contract echo")
    args = ap.parse_args(argv)
    result = build_and_audit(Path(args.spec), Path(args.out), args.case)
    print(json.dumps({"status": result.get("status"), "case_id": result.get("case_id"),
                      "findings": [f["rule"] for f in result.get("findings", [])],
                      "n_analyses": len(result.get("analysis_results") or []),
                      "n_correlations": len(result.get("correlations") or []),
                      "wrote": str(Path(args.out) / "result.json")}, ensure_ascii=False))
    return {"clean": 0, "review": 3, "blocked": 4, "undetermined": 5}.get(result.get("status"), 1)


if __name__ == "__main__":
    raise SystemExit(main())
