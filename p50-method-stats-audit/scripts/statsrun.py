"""Source-bound methods/statistics review with real numerical recomputation.

Primary interface:
  python statsrun.py --case /input/case.json --out /app/output
  python statsrun.py --spec examples/spec-stats.json --out out_stats

--manuscript supplies a separate TXT/MD/TEX/PDF source. --data supplies a CSV
for declared raw-data diagnostics.  Exit 0 clean, 3 review/reporting gaps,
4 blocked/high issue, 5 undetermined refusal.  JSON is written on every
readable-output path; malformed inputs never expose a traceback.
"""
from __future__ import annotations

import argparse
import copy
import csv
import json
import math
import re
import subprocess
import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import sections as LEGACY  # noqa: E402
import statscore as SC  # noqa: E402

SCHEMA = "method-statistics-review/v2"
DIMENSIONS = (
    "design_question_match", "independent_units", "randomization_blinding",
    "sample_size_power", "missing_data", "outliers", "distributions_variance",
    "model_choice", "multiplicity", "effect_size_ci", "p_value_interpretation",
    "correlation_causation", "sensitivity_robustness", "reproducibility",
)
DIM_ZH = {
    "design_question_match": "设计—问题匹配", "independent_units": "独立单位与伪重复",
    "randomization_blinding": "随机化与盲法", "sample_size_power": "样本量与功效",
    "missing_data": "缺失数据", "outliers": "异常值", "distributions_variance": "分布与方差假设",
    "model_choice": "模型选择", "multiplicity": "多重比较", "effect_size_ci": "效应量与置信区间",
    "p_value_interpretation": "p值解释", "correlation_causation": "相关与因果",
    "sensitivity_robustness": "敏感性/稳健性", "reproducibility": "复现",
}
TEXT_KEYS = ("manuscript_text", "full_text", "paper_text", "draft")
PATH_KEYS = ("manuscript_path", "paper_path", "pdf_path", "manuscript", "paper")
BULKY = set(TEXT_KEYS) | {"output_contract", "raw_data", "checks", "statistical_checks",
                          "power_analyses", "comparison_families", "p_value_statements",
                          "variables", "endpoints", "comparisons", "figures", "materials",
                          "references", "documents", "data", "inputs"}
CAUSAL = re.compile(r"\b(causes?|caused|drives?|leads?\s+to|proves?)\b|导致|证明|引起", re.I)


def norm(v):
    return re.sub(r"\s+", " ", str(v or "")).strip()


def clip(v, n=500):
    s = norm(v)
    return s if len(s) <= n else s[:n].rstrip() + "…"


def records(v):
    return v if isinstance(v, list) else []


def truth(v):
    return bool(norm(v)) and norm(v).lower() not in {"none", "null", "n/a", "missing", "not reported", "未报告", "缺失"}


def contains(text, quote):
    return bool(norm(quote)) and norm(quote).rstrip("…") in norm(text)


def read_pdf(path):
    errors = []
    try:
        import fitz
        with fitz.open(str(path)) as doc:
            text = "\n".join(p.get_text("text") for p in doc)
        if text.strip():
            return text, None
        errors.append("PyMuPDF returned an empty text layer")
    except Exception as exc:
        errors.append(f"PyMuPDF: {exc}")
    try:
        from pypdf import PdfReader
        text = "\n".join(p.extract_text() or "" for p in PdfReader(str(path)).pages)
        if text.strip():
            return text, None
        errors.append("pypdf returned an empty text layer")
    except Exception as exc:
        errors.append(f"pypdf: {exc}")
    try:
        p = subprocess.run(["pdftotext", "-layout", str(path), "-"], capture_output=True, timeout=60)
        text = p.stdout.decode("utf-8", "replace") if p.returncode == 0 else ""
        if text.strip():
            return text, None
        errors.append("pdftotext returned no text")
    except (OSError, subprocess.SubprocessError) as exc:
        errors.append(f"pdftotext: {exc}")
    return "", "; ".join(errors)


def read_source(path):
    try:
        if path.stat().st_size > 30_000_000:
            return "", "source exceeds the 30MB parser safety limit"
    except OSError as exc:
        return "", str(exc)
    if path.suffix.lower() == ".pdf":
        return read_pdf(path)
    try:
        raw = path.read_bytes()
    except OSError as exc:
        return "", str(exc)
    for enc in ("utf-8-sig", "utf-16", "gb18030"):
        try:
            return raw.decode(enc), None
        except UnicodeDecodeError:
            continue
    return raw.decode("latin-1"), "non-UTF source decoded as latin-1; preserve uncertainty"


def walk_text(value):
    if isinstance(value, dict):
        for key in TEXT_KEYS:
            if isinstance(value.get(key), str) and value[key].strip():
                return value[key]
        for key in ("documents", "papers", "sources", "inputs", "materials"):
            got = walk_text(value.get(key))
            if got:
                return got
    elif isinstance(value, list):
        for item in value:
            got = walk_text(item)
            if got:
                return got
    return ""


def walk_path(value):
    if isinstance(value, dict):
        for key in PATH_KEYS:
            if isinstance(value.get(key), str) and value[key].strip():
                return value[key]
        if any(k in value for k in ("path", "file_path", "file")):
            v = value.get("path") or value.get("file_path") or value.get("file")
            if isinstance(v, str) and Path(v).suffix.lower() in {".pdf", ".txt", ".md", ".tex", ".json"}:
                return v
        for child in value.values():
            if isinstance(child, (dict, list)):
                got = walk_path(child)
                if got:
                    return got
    elif isinstance(value, list):
        for item in value:
            got = walk_path(item)
            if got:
                return got
    return ""


def load_text(spec, base, override=None):
    limits, sources = [], []
    inline = "" if override else walk_text(spec)
    if inline.strip():
        return inline, limits, ["case.inline_manuscript"]
    candidate = override or walk_path(spec)
    if not candidate:
        return "", ["no manuscript text supplied; structured calculations remain possible but are incomplete review"], sources
    path = Path(candidate)
    if not path.is_absolute():
        choices = [base / path, Path("/input") / path, Path("/app/work") / path]
        path = next((p for p in choices if p.exists()), choices[0])
    text, err = read_source(path)
    if text.strip():
        sources.append(str(path))
        if err:
            limits.append(err)
        return text, limits, sources
    limits.append(f"manuscript could not be read: {err or 'no text layer'}")
    if path.suffix.lower() == ".json" and path.exists():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            text = walk_text(data)
            if text.strip():
                sources.append(str(path))
                return text, limits, sources
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            limits.append(f"JSON text fallback failed: {exc}")
    return "", limits, sources


def location(item, text=""):
    quote = item.get("source_quote") or item.get("quote") if isinstance(item, dict) else None
    loc = item.get("source_locator") or item.get("location") if isinstance(item, dict) else None
    if isinstance(loc, str):
        loc = {"reported": loc}
    elif not isinstance(loc, dict):
        loc = {}
    if quote:
        loc["quote"] = clip(quote)
        loc["quote_verified"] = contains(text, str(quote)) if text else None
    return loc


def finding(out, rule, dimension, severity, message, item=None, text="",
            defect_class="method_observation", suggestion="Verify the cited result and rerun.",
            scope="manuscript", **extra):
    item = item if isinstance(item, dict) else {}
    f = {"rule": rule, "dimension": dimension, "dimension_zh": DIM_ZH[dimension],
         "severity": severity, "finding": message, "message": message,
         "location": location(item, text), "basis": norm(item.get("basis") or "declared inputs and deterministic audit"),
         "defect_class": defect_class, "suggestion": suggestion, "scope": scope,
         "source_name": item.get("name")}
    f.update(extra)
    out.append(f)


def evidence_validate(spec, text, findings):
    candidates = []
    for key in ("statistical_checks", "checks", "power_analyses", "comparison_families", "p_value_statements"):
        candidates.extend(x for x in records(spec.get(key)) if isinstance(x, dict))
    for key in ("missing_data", "outliers", "independence", "reproducibility", "sensitivity"):
        if isinstance(spec.get(key), dict):
            candidates.append(spec[key])
    for item in candidates:
        q = item.get("source_quote") or item.get("quote")
        if q and text and not contains(text, str(q)):
            finding(findings, "msv.evidence_not_in_source", "reproducibility", "high",
                    "A source_quote supplied for this audit is not present in the manuscript.", item,
                    defect_class="review_evidence_error", scope="review_process",
                    suggestion="Replace the quotation with exact manuscript wording or remove the unverified claim.")
    for stmt in records(spec.get("review_findings")):
        if not isinstance(stmt, dict):
            continue
        q = stmt.get("source_quote") or stmt.get("quote")
        if q and text and not contains(text, str(q)):
            finding(findings, "msv.evidence_not_in_source", "reproducibility", "high",
                    "A reviewer finding is attached to a quotation absent from the manuscript.", stmt,
                    defect_class="review_evidence_error", scope="review_process")
            continue
        dim = stmt.get("dimension") if stmt.get("dimension") in DIMENSIONS else "model_choice"
        sev = norm(stmt.get("severity") or "medium").lower()
        if sev not in {"high", "medium", "low"}:
            sev = "medium"
        message = norm(stmt.get("finding") or stmt.get("message"))
        if message and (q or stmt.get("source_locator") or stmt.get("defect_class") == "reporting_gap"):
            finding(findings, "msv.reviewer_substantiated_issue", dim, sev, message, stmt, text,
                    defect_class=norm(stmt.get("defect_class") or "review_observation"),
                    suggestion=norm(stmt.get("suggestion") or "Address the evidenced issue and retain the source boundary."))
        elif message:
            finding(findings, "msv.reviewer_issue_unverified", dim, "high",
                    "A substantive reviewer finding has neither source evidence nor a bounded reporting-gap basis.", stmt,
                    defect_class="review_evidence_error", scope="review_process")


def legacy_dimension(rule):
    if any(x in rule for x in ("randomisation", "blinding")):
        return "randomization_blinding"
    if any(x in rule for x in ("sample", "attrition", "tolerance", "no_stages")):
        return "sample_size_power"
    if "multiple_comparisons" in rule:
        return "multiplicity"
    if "ci_missing" in rule or "errorbar" in rule:
        return "effect_size_ci"
    if "model" in rule or "statistic" in rule:
        return "model_choice"
    if "missing_handling" in rule:
        return "missing_data"
    if any(x in rule for x in ("causal", "non_significant", "overclaim", "negative_result")):
        return "p_value_interpretation"
    if rule.startswith("repro."):
        return "reproducibility"
    if "control" in rule or "design" in rule or "endpoint" in rule:
        return "design_question_match"
    if "variable" in rule or "cutpoint" in rule:
        return "model_choice"
    return "effect_size_ci"


def run_legacy(spec, findings, limits):
    requested = spec.get("legacy_sections", "auto")
    if requested == "auto":
        requested = []
        if any(k in spec for k in ("design", "variables", "endpoints", "model", "sample_size")):
            requested.append("method_stats")
        if "results_text" in spec or "discussion_text" in spec:
            requested.append("results_discussion")
        if any(k in spec for k in ("checklist", "commit", "data_version", "commands")) and "reproducibility" not in spec:
            requested.append("reproduce")
    if isinstance(requested, str):
        requested = [requested]
    if not isinstance(requested, list):
        return []
    ran = []
    for section in requested:
        if section not in {"method_stats", "results_discussion", "reproduce"}:
            limits.append(f"unsupported legacy section skipped: {section}")
            continue
        try:
            found, _, _ = LEGACY.run(copy.deepcopy(spec), section)
        except Exception as exc:
            finding(findings, "msv.legacy_audit_failed", "reproducibility", "high",
                    f"Requested legacy section {section} failed: {exc}",
                    defect_class="execution_failure", scope="review_process")
            continue
        ran.append(section)
        for old in found:
            dim = legacy_dimension(str(old.get("rule", "")))
            f = dict(old)
            f.update({"dimension": dim, "dimension_zh": DIM_ZH[dim],
                      "origin": section, "finding": old.get("message", old.get("rule")),
                      "scope": "manuscript", "location": {k: old.get(k) for k in ("field", "variable", "sentence", "metric", "stage") if old.get(k) is not None},
                      "defect_class": "reporting_gap" if old.get("reporting_gap") else old.get("defect_class", "method_or_reporting_issue"),
                      "basis": f"legacy {section} rule on declared manuscript fields",
                      "suggestion": "Resolve the evidenced issue; reporting absence must not be rewritten as proof of non-performance."})
            findings.append(f)
    return ran


def compare_reported(calc, item, kind, findings, text):
    if not calc.get("computable"):
        return
    comparisons = []
    p = calc.get("p_value", calc.get("power") if kind == "power" else None)
    if kind == "power":
        # Power comparisons are legitimate only for the same approximation/model.
        if item.get("reported_power") is not None:
            expected = SC.number(item.get("reported_power"))
            tolerance = SC.number(item.get("power_tolerance"))
            tolerance = 0.005 if tolerance is None else abs(tolerance)
            ok = expected is not None and p is not None and abs(expected - p) <= max(tolerance, tolerance * abs(expected))
            comparisons.append(("reported_power", "power", expected, p, ok, "msv.power_recompute_mismatch"))
    else:
        if item.get("reported_p") is not None:
            op = norm(item.get("reported_p_operator") or "=")
            expected = SC.number(item.get("reported_p"))
            computed = SC.number(p)
            if expected is not None and computed is not None:
                tolerance = SC.number(item.get("p_tolerance"))
                tolerance = 1e-4 if tolerance is None else abs(tolerance)
                ok = computed < expected if op == "<" else computed <= expected if op == "<=" else computed > expected if op == ">" else computed >= expected if op == ">=" else abs(computed - expected) <= max(tolerance, tolerance * abs(expected))
                comparisons.append((f"reported_p {op}", "p_value", expected, computed, ok, "msv.reported_p_recompute_mismatch"))
        for input_key, calc_key, tol, rule in (
                ("reported_statistic", "statistic", 1e-4, "msv.reported_statistic_recompute_mismatch"),
                ("reported_df", "df", 0.05, "msv.reported_df_recompute_mismatch")):
            if item.get(input_key) is not None and calc.get(calc_key) is not None:
                expected, computed = SC.number(item[input_key]), SC.number(calc[calc_key])
                tolerance = SC.number(item.get("statistic_tolerance"))
                tolerance = tol if tolerance is None else abs(tolerance)
                comparisons.append((input_key, calc_key, expected, computed,
                                    expected is not None and abs(computed - expected) <= max(tolerance, tolerance * abs(expected)), rule))
        if isinstance(item.get("reported_ci"), list) and len(item["reported_ci"]) == 2 and isinstance(calc.get("mean_difference_ci"), list):
            expected = [SC.number(v) for v in item["reported_ci"]]
            computed = calc["mean_difference_ci"]
            tolerance = SC.number(item.get("ci_tolerance"))
            tolerance = 1e-4 if tolerance is None else abs(tolerance)
            ok = all(v is not None and math.isfinite(v) and math.isfinite(c) and abs(v - c) <= max(tolerance, tolerance * abs(v))
                     for v, c in zip(expected, computed))
            comparisons.append(("reported_ci", "mean_difference_ci", expected, computed, ok, "msv.reported_ci_recompute_mismatch"))
        if item.get("reported_effect_size") is not None:
            expected = SC.number(item.get("reported_effect_size"))
            kind_effect = norm(item.get("effect_type") or "cohens_d").lower()
            computed = calc.get(kind_effect)
            tolerance = SC.number(item.get("effect_tolerance"))
            tolerance = 1e-4 if tolerance is None else abs(tolerance)
            if computed is not None:
                comparisons.append(("reported_effect_size", kind_effect, expected, computed,
                                    expected is not None and abs(computed - expected) <= max(tolerance, tolerance * abs(expected)),
                                    "msv.reported_effect_recompute_mismatch"))
    for label, calc_key, expected, computed, ok, rule in comparisons:
        if ok:
            continue
        finding(findings, rule, "sample_size_power" if kind == "power" else "effect_size_ci", "high",
                f"{label} disagrees with the deterministic recomputation: expected/claimed={expected}, computed={computed}.",
                item, text, defect_class="numeric_inconsistency",
                suggestion="Recalculate from the declared inputs and model; do not force the manuscript values to agree by editing inputs.",
                expected=expected, computed=computed, calculation=calc_key)


def analysis_checks(spec, text, calculations, findings, used):
    checks = spec.get("statistical_checks", spec.get("checks", []))
    if isinstance(checks, dict):
        checks = [checks]
    for item in records(checks):
        if not isinstance(item, dict):
            continue
        typ = norm(item.get("type") or item.get("test")).lower()
        used.update({"model_choice", "effect_size_ci"})
        if typ in {"independent_t", "welch_t", "student_t", "t_test_independent"}:
            calc = SC.independent_t(item.get("mean1"), item.get("sd1"), item.get("n1"),
                                    item.get("mean2"), item.get("sd2"), item.get("n2"),
                                    equal_var=bool(item.get("equal_var")) or typ == "student_t",
                                    alternative=norm(item.get("alternative") or "two-sided").lower(),
                                    confidence=SC.number(item.get("confidence")) or 0.95)
            calc.update({"name": item.get("name"), "type": "independent_t", "source_locator": item.get("source_locator")})
            calculations.append(calc)
            compare_reported(calc, item, "independent_t", findings, text)
            ci = calc.get("mean_difference_ci")
            declared_ci = item.get("reported_ci") if isinstance(item.get("reported_ci"), list) and len(item.get("reported_ci")) == 2 else None
            ci = declared_ci or ci
            confidence = SC.number(item.get("confidence")) or 0.95
            alpha = SC.number(item.get("alpha")) or (1.0 - confidence)
            p = SC.number(item.get("reported_p")) if item.get("reported_p") is not None else calc.get("p_value")
            if (calc.get("computable") and p is not None and ci and len(ci) == 2 and
                    norm(item.get("alternative") or "two-sided").lower() == "two-sided" and
                    abs(confidence - (1.0 - alpha)) <= 1e-12 and
                    all(SC.number(v) is not None and math.isfinite(SC.number(v)) for v in ci)):
                p_sig = p < alpha
                ci_null = SC.number(item.get("null_value")) or 0.0
                ci_sig = not (ci[0] <= ci_null <= ci[1])
                if p_sig != ci_sig:
                    finding(findings, "msv.p_ci_decision_conflict", "p_value_interpretation", "high",
                            f"Two-sided p={p:g} and {100*(SC.number(item.get('confidence')) or .95):g}% CI={ci} imply different alpha={alpha} decisions about the null value {ci_null}.",
                            item, text, defect_class="numeric_inconsistency",
                            suggestion="Check tails, confidence level, null value and which estimand each result describes before interpreting significance.")
        elif typ == "power":
            used.add("sample_size_power")
            calc = SC.normal_power(item.get("effect_size"), item.get("nobs1"), item.get("alpha", 0.05),
                                   item.get("power"), item.get("ratio", 1.0),
                                   norm(item.get("alternative") or "two-sided").lower(), norm(item.get("solve") or "power"))
            calc.update({"name": item.get("name"), "type": "power", "source_locator": item.get("source_locator")})
            calculations.append(calc)
            if calc.get("computable") and item.get("approximation", "normal") == "normal":
                compare_reported(calc, item, "power", findings, text)


def multiplicity_checks(spec, text, calculations, findings, used):
    families = spec.get("comparison_families", [])
    if isinstance(families, dict):
        families = [families]
    for family in records(families):
        if not isinstance(family, dict):
            continue
        used.add("multiplicity")
        comps = [p for p in records(family.get("comparisons")) if isinstance(p, dict)]
        raw = [p.get("p", p.get("p_value")) for p in comps]
        method = norm(family.get("method") or family.get("correction") or "bh").lower()
        calc = SC.adjust_pvalues(raw, method)
        calc.update({"name": family.get("name"), "type": "multiplicity", "source_locator": family.get("source_locator"),
                     "calculation_basis": "declared correction" if truth(family.get("method") or family.get("correction")) else "hypothetical default only; not attributed to the authors"})
        calculations.append(calc)
        if not calc.get("computable"):
            continue
        for i, comp in enumerate(comps):
            if comp.get("reported_adjusted_p") is None:
                continue
            expected = SC.number(comp.get("reported_adjusted_p"))
            actual = calc["adjusted"][i]
            tol = SC.number(family.get("tolerance"))
            tol = 1e-4 if tol is None else abs(tol)
            if expected is None or abs(expected - actual) > max(tol, tol * abs(expected)):
                finding(findings, "msv.adjusted_p_recompute_mismatch", "multiplicity", "high",
                        f"Adjusted p for {comp.get('name', i)} is {expected}; {calc['method']} recomputation gives {actual}.",
                        dict(family, source_quote=family.get("source_quote") or comp.get("source_quote")), text,
                        defect_class="numeric_inconsistency",
                        suggestion="Recalculate within the declared comparison family and version; preserve the original ordering.")
        if not truth(family.get("method") or family.get("correction")) and family.get("confirmatory") is True and len(comps) > 1:
            finding(findings, "msv.multiplicity_unaddressed", "multiplicity", "medium",
                    f"A confirmatory family of {len(comps)} comparisons has no multiplicity method; raw p values alone cannot establish familywise/error-rate control.",
                    family, text, defect_class="reporting_gap",
                    suggestion="Declare the actual correction and family, or label analyses exploratory; do not invent a post-hoc correction to strengthen claims.")


def raw_for(spec, external_data):
    raw = spec.get("raw_data", external_data)
    return raw if isinstance(raw, list) else []


def column(raw, name):
    vals = []
    for row in raw:
        if not isinstance(row, dict) or name not in row:
            return []
        vals.append(row[name])
    return vals


def paired(raw, xname, yname):
    xs, ys = [], []
    for row in raw:
        if not isinstance(row, dict):
            continue
        x, y = SC.number(row.get(xname)), SC.number(row.get(yname))
        if x is not None and y is not None:
            xs.append(x)
            ys.append(y)
    return xs, ys


def diagnostics(spec, external_data, text, calculations, findings, used):
    items = spec.get("diagnostics", [])
    if isinstance(items, dict):
        items = [items]
    raw = raw_for(spec, external_data)
    for item in records(items):
        if not isinstance(item, dict):
            continue
        typ = norm(item.get("type")).lower()
        if typ == "levene":
            used.add("distributions_variance")
            groups = item.get("groups")
            if not groups and item.get("group_column") and item.get("value_column"):
                names = sorted({str(r.get(item["group_column"])) for r in raw if isinstance(r, dict)})
                groups = [[r.get(item["value_column"]) for r in raw if isinstance(r, dict) and str(r.get(item["group_column"])) == name] for name in names]
            calc = SC.levene(groups or [], norm(item.get("center") or "median"),
                             SC.number(item.get("proportiontocut")) or 0.05)
            calc.update({"name": item.get("name"), "type": typ, "source_locator": item.get("source_locator")})
            calculations.append(calc)
            compare_reported(calc, item, typ, findings, text)
            if calc.get("computable") and calc["p_value"] < (SC.number(item.get("alpha")) or 0.05) and item.get("model_requires_equal_variance") is True:
                finding(findings, "msv.equal_variance_assumption_signal", "distributions_variance", "medium",
                        f"Levene ({item.get('center', 'median')}) gives F={calc['statistic']:.8g}, p={calc['p_value']:.8g}; evidence against the equal-variance requirement should be addressed by a suitable/sensitivity analysis.",
                        item, text, defect_class="diagnostic_signal",
                        suggestion="Use a variance-appropriate model or robust sensitivity analysis; a diagnostic p-value alone does not prove a particular correction.")
        elif typ in {"normality", "jarque_bera"}:
            used.add("distributions_variance")
            values = item.get("values")
            if not values and item.get("column"):
                values = column(raw, item["column"])
            calc = SC.jarque_bera(values or [])
            calc.update({"name": item.get("name"), "type": "jarque_bera", "source_locator": item.get("source_locator")})
            calculations.append(calc)
            compare_reported(calc, item, typ, findings, text)
            if calc.get("computable") and calc["p_value"] < (SC.number(item.get("alpha")) or 0.05) and item.get("model_assumes_normality") is True:
                finding(findings, "msv.residual_normality_signal", "distributions_variance", "medium",
                        f"Jarque-Bera={calc['statistic']:.8g}, p={calc['p_value']:.8g} indicates non-normal moments in the declared sample/residuals.",
                        item, text, defect_class="diagnostic_signal",
                        suggestion="Inspect residual plots and robust/nonparametric sensitivity; JB is asymptotic and does not select a unique alternative model.")
        elif typ == "correlation":
            used.update({"distributions_variance", "correlation_causation", "effect_size_ci"})
            x, y = item.get("x"), item.get("y")
            if item.get("x_column") and item.get("y_column"):
                x, y = paired(raw, item["x_column"], item["y_column"])
            calc = SC.pearson(x or [], y or [], SC.number(item.get("confidence")) or 0.95)
            calc.update({"name": item.get("name"), "type": typ, "source_locator": item.get("source_locator")})
            calculations.append(calc)
            compare_reported(calc, item, typ, findings, text)
        elif typ in {"regression", "regression_diagnostics"}:
            used.update({"model_choice", "distributions_variance", "outliers"})
            y, x = item.get("y"), item.get("x")
            if item.get("y_column") and item.get("x_columns"):
                y = [SC.number(v) for v in column(raw, item["y_column"])]
                columns = [column(raw, c) for c in item["x_columns"]]
                x = [[columns[j][i] for j in range(len(columns))] for i in range(len(y))] if all(len(c) == len(y) for c in columns) else []
            try:
                fit = SC.ols(y or [], x or [], add_intercept=item.get("add_intercept", True) is not False)
                calc = {"computable": True, "name": item.get("name"), "type": "regression",
                        "source_locator": item.get("source_locator"), "n": fit["n"], "p": fit["p"],
                        "r2": fit["r2"], "sse": fit["sse"], "df_resid": fit["df_resid"],
                        "coefficients": fit["coefficients"], "rmse": math.sqrt(fit["sse"] / fit["df_resid"]),
                        "durbin_watson": SC.durbin_watson(fit["residuals"]),
                        "breusch_pagan": SC.breusch_pagan(fit["residuals"], fit["design"]),
                        "ramsey_reset": SC.ramsey_reset(y, x, item.get("reset_power", 3)),
                        "vif": SC.variance_inflation(x or [])}
                # Residual vectors are intentionally not repeated in the report.
                calculations.append(calc)
                alpha = SC.number(item.get("alpha")) or 0.05
                reset = calc["ramsey_reset"]
                if reset.get("computable") and reset["p_value"] < alpha:
                    finding(findings, "msv.model_specification_signal", "model_choice", "medium",
                            f"Ramsey RESET F={reset['statistic']:.8g}, p={reset['p_value']:.8g} rejects zero coefficients for fitted-value powers {reset['powers']}.",
                            item, text, defect_class="diagnostic_signal",
                            suggestion="Investigate functional form with domain knowledge and sensitivity models; RESET does not identify the correct model.")
                bp = calc["breusch_pagan"]
                if bp.get("computable") and bp["f_p_value"] < alpha:
                    finding(findings, "msv.heteroskedasticity_signal", "distributions_variance", "medium",
                            f"Breusch-Pagan auxiliary regression F={bp['f_statistic']:.8g}, p={bp['f_p_value']:.8g} indicates variance related to the supplied design matrix.",
                            item, text, defect_class="diagnostic_signal",
                            suggestion="Report robust covariance or an appropriate variance model and sensitivity; do not infer a unique cause from BP.")
                threshold = SC.number(item.get("vif_threshold"))
                if threshold:
                    for vif in calc["vif"].get("tests", []):
                        if vif.get("vif") is not None and vif["vif"] > threshold:
                            finding(findings, "msv.collinearity_signal", "model_choice", "medium",
                                    f"Predictor column {vif['column']} has VIF={vif['vif']:.8g}, above the caller-declared heuristic {threshold}.",
                                    item, text, defect_class="diagnostic_signal",
                                    suggestion="Inspect design coding, precision and domain-appropriate sensitivity; VIF alone does not prove model invalidity.")
                expected = item.get("reported_coefficients")
                if isinstance(expected, list) and len(expected) == len(fit["coefficients"]):
                    tol = SC.number(item.get("coefficient_tolerance")) or 1e-5
                    for j, (want, got) in enumerate(zip(expected, fit["coefficients"])):
                        want = SC.number(want)
                        if want is None or abs(want - got) > max(tol, tol * abs(want)):
                            finding(findings, "msv.regression_coefficient_recompute_mismatch", "model_choice", "high",
                                    f"Regression coefficient {j} is reported as {want} but OLS recomputation gives {got}.",
                                    item, text, defect_class="numeric_inconsistency",
                                    suggestion="Recheck column order, intercept, complete cases and OLS version before changing the report.")
                for field, path, label in (
                        ("reported_bp_p", ("breusch_pagan", "f_p_value"), "Breusch-Pagan F p"),
                        ("reported_reset_p", ("ramsey_reset", "p_value"), "RESET F p")):
                    if item.get(field) is not None and calc[path[0]].get(path[1]) is not None:
                        want, got = SC.number(item[field]), calc[path[0]][path[1]]
                        tol = SC.number(item.get("p_tolerance")) or 1e-4
                        if want is None or abs(want - got) > max(tol, tol * abs(want)):
                            finding(findings, "msv.diagnostic_p_recompute_mismatch", "model_choice", "high",
                                    f"{label} is reported as {want} but recomputation gives {got}.",
                                    item, text, defect_class="numeric_inconsistency",
                                    suggestion="Verify matrix construction, residual order and which diagnostic statistic was reported.")
            except (ValueError, ArithmeticError, TypeError) as exc:
                calculations.append({"computable": False, "type": "regression", "name": item.get("name"),
                                     "source_locator": item.get("source_locator"), "reason": str(exc)})


def design_and_reporting(spec, text, calculations, findings, used):
    design = norm(spec.get("design")).lower().replace("-", "_").replace(" ", "_")
    question = norm(spec.get("research_question_type") or spec.get("question_type")).lower()
    if design or question:
        used.add("design_question_match")
    if any(k in spec for k in ("randomisation", "randomization", "blinding", "controls", "endpoints")):
        used.add("randomization_blinding")
    allowed = {
        "causal_effect": {"rct", "randomized", "randomised", "experiment", "quasi_experiment", "natural_experiment"},
        "diagnostic_accuracy": {"diagnostic", "cross_sectional", "cohort", "case_control"},
        "prediction": {"cohort", "experimental", "observational", "cross_sectional", "rct", "secondary_analysis"},
        "descriptive": {"cross_sectional", "cohort", "case_series", "qualitative", "survey", "observational"},
    }
    if question in allowed and design and not any(k in design for k in allowed[question]):
        finding(findings, "msv.design_question_mismatch", "design_question_match", "high",
                f"Declared question={question} and design={design} do not match; supplying more reporting detail cannot fix this mismatch.",
                spec, text, defect_class="method_defect",
                suggestion="Use a design that answers the question or narrow the question/conclusion to what this design identifies.")

    independence = spec.get("independence")
    if isinstance(independence, dict):
        used.add("independent_units")
        allocation = norm(independence.get("allocation_unit") or independence.get("experimental_unit")).lower()
        analysis = norm(independence.get("analysis_unit") or independence.get("statistical_unit")).lower()
        model = norm(independence.get("model") or spec.get("model")).lower()
        handles = any(k in model for k in ("mixed", "cluster", "gee", "frailty", "paired", "repeated", "within")) or independence.get("accounts_for_clustering") is True
        if allocation and analysis and allocation != analysis and not handles:
            finding(findings, "msv.pseudoreplication_independence_conflict", "independent_units", "high",
                    f"Allocation/experimental unit is {allocation} but analysis treats {analysis} as independent without a cluster/repeated/paired method.",
                    independence, text, defect_class="method_defect",
                    suggestion="Analyse at the independent assignment unit or use a model that accounts for within-unit dependence and report its implementation.")
        n_rows = SC.number(independence.get("n_observations"))
        n_units = SC.number(independence.get("n_independent_units"))
        if n_rows is not None and n_units is not None and n_rows > 0 and n_units > 0:
            ratio = n_rows / n_units
            calculations.append({"computable": True, "type": "independent_unit_accounting",
                                 "source_locator": independence.get("source_locator"),
                                 "n_observations": n_rows, "n_independent_units": n_units,
                                 "observations_per_independent_unit": ratio})
            if n_units > n_rows:
                finding(findings, "msv.independent_unit_count_impossible", "independent_units", "high",
                        f"Independent units ({n_units:g}) exceed total observations ({n_rows:g}).", independence, text,
                        defect_class="numeric_inconsistency",
                        suggestion="Reconcile identifiers, duplicated records and the denominator used for inference.")
            elif ratio > 1 and independence.get("treats_observations_as_independent") is True and not handles:
                finding(findings, "msv.pseudoreplication_count_confirmed", "independent_units", "high",
                        f"{n_rows:g} observations come from {n_units:g} independent units (ratio={ratio:.8g}) and are nevertheless treated as independent.",
                        independence, text, defect_class="method_defect",
                        suggestion="Use the independent-unit denominator or a dependence-aware model; the effective sample size is not the row count.")

    model = norm(spec.get("model") or spec.get("model_type")).lower()
    outcome = norm(spec.get("outcome_type")).lower()
    if outcome:
        used.add("model_choice")
    compatible = {
        "linear_regression": {"continuous"}, "linear_mixed_model": {"continuous"},
        "logistic_regression": {"binary"}, "poisson_regression": {"count"},
        "negative_binomial_regression": {"count"}, "cox_regression": {"time_to_event"},
        "ordinal_regression": {"ordinal"}, "multinomial_regression": {"nominal"},
    }
    model_key = model.replace("-", "_").replace(" ", "_")
    if outcome and model_key in compatible and outcome not in compatible[model_key]:
        finding(findings, "msv.model_outcome_mismatch", "model_choice", "high",
                f"Declared {model_key} is incompatible with {outcome} outcome data.", spec, text,
                defect_class="method_defect",
                suggestion="Select an outcome-compatible model/link and rerun all downstream estimates, not just relabel the method.")

    missing = spec.get("missing_data")
    if isinstance(missing, dict):
        used.add("missing_data")
        expected, observed = SC.number(missing.get("expected_n")), SC.number(missing.get("observed_n"))
        count = SC.number(missing.get("missing_count"))
        if count is None and expected is not None and observed is not None:
            count = expected - observed
        fraction = count / expected if count is not None and expected and count >= 0 else None
        calculations.append({"computable": count is not None, "type": "missing_data_accounting",
                             "source_locator": missing.get("source_locator"), "missing_count": count,
                             "expected_n": expected, "observed_n": observed, "missing_fraction": fraction})
        if count is not None and (count < 0 or observed is not None and expected is not None and count != expected - observed):
            finding(findings, "msv.missing_count_inconsistent", "missing_data", "high",
                    f"Missing count {count} is inconsistent with expected-observed accounting {expected}-{observed}.",
                    missing, text, defect_class="numeric_inconsistency",
                    suggestion="Reconcile missing records by variable and analysis, not merely total participant counts.")
        if count and not truth(missing.get("handling")):
            finding(findings, "msv.missing_handling_missing", "missing_data", "medium",
                    "Missing observations are declared but their handling is not reported; this is a reporting gap, not proof that the chosen method was wrong.",
                    missing, text, defect_class="reporting_gap",
                    suggestion="Report the actual complete-case/imputation/weighting workflow and assumptions by analysis.")
        if truth(missing.get("handling")) and not truth(missing.get("mechanism_or_assumption")):
            finding(findings, "msv.missing_assumption_unreported", "missing_data", "medium",
                    "A missing-data method is named without its mechanism/assumptions or justification.", missing, text,
                    defect_class="reporting_gap",
                    suggestion="Report MCAR/MAR/MNAR reasoning as applicable and sensitivity analysis; do not assert missing at random merely because imputation was used.")

    outliers = spec.get("outliers")
    if isinstance(outliers, dict):
        used.add("outliers")
        if outliers.get("removed") is True and outliers.get("prespecified") is False and not truth(outliers.get("sensitivity_analysis")):
            finding(findings, "msv.data_driven_outlier_exclusion", "outliers", "high",
                    "Observations were removed by a non-prespecified outlier decision without sensitivity analysis, so the primary estimand/result may be selected by the observed data.",
                    outliers, text, defect_class="method_defect",
                    suggestion="Restore and justify the analysis population; report both all-observation and justified sensitivity analyses.")
        elif outliers.get("detected") is True and not truth(outliers.get("handling")):
            finding(findings, "msv.outlier_handling_missing", "outliers", "medium",
                    "Detected outliers have no reported handling; no inference about wrongful exclusion is made.", outliers, text,
                    defect_class="reporting_gap",
                    suggestion="Report detection criteria, whether points were retained, and the effect on the fitted result.")

    conclusion = spec.get("causal_claim") or spec.get("conclusion")
    if design or conclusion:
        used.add("correlation_causation")
    if conclusion and any(k in design for k in ("observ", "correl", "cross_section")) and CAUSAL.search(norm(conclusion)):
        finding(findings, "msv.correlation_causal_overreach", "correlation_causation", "high",
                f"The declared {design} design is paired with causal wording: {clip(conclusion, 220)}", spec, text,
                defect_class="method_defect",
                suggestion="Rewrite as an association or provide the actual causal identification and sensitivity strategy; a p-value is not causal identification.")

    sensitivity = spec.get("sensitivity_analyses")
    trigger = any(k in spec for k in ("missing_data", "outliers", "diagnostics")) or any(k in design for k in ("observ", "correl"))
    if sensitivity is not None or trigger:
        used.add("sensitivity_robustness")
    if trigger and (not isinstance(sensitivity, list) or not sensitivity):
        finding(findings, "msv.sensitivity_analysis_missing", "sensitivity_robustness", "medium",
                "Dependence/model/missing-data/outlier/causal assumptions are implicated but no sensitivity analysis is reported; this is a reporting gap, not automatic proof of a wrong model.",
                spec, text, defect_class="reporting_gap",
                suggestion="Report the prespecified or clearly labelled robustness analyses that were actually performed and whether conclusions change.")

    repro = spec.get("reproducibility")
    if isinstance(repro, dict):
        used.add("reproducibility")
        required = ["data_version", "analysis_command"] if spec.get("computational_study") else []
        if repro.get("code_used") is True:
            required.append("code_version")
        if repro.get("randomness_used") is True:
            required.append("seed")
        absent = [key for key in required if not truth(repro.get(key))]
        if absent:
            finding(findings, "msv.reanalysis_fields_missing", "reproducibility", "medium",
                    "Independent numerical reanalysis is not fully reproducible; missing fields: " + ", ".join(absent),
                    repro, text, defect_class="reporting_gap",
                    suggestion="Record the actual versions, commands and seeds; if unavailable, name the irreproducible step rather than fabricating them.")
        for record in records(repro.get("reported_values")):
            if not isinstance(record, dict):
                continue
            want, got = SC.number(record.get("reported")), SC.number(record.get("recomputed"))
            tol = SC.number(record.get("tolerance"))
            tol = 1e-9 if tol is None else abs(tol)
            delta = want - got if want is not None and got is not None else None
            ok = delta is not None and abs(delta) <= tol
            calculations.append({"computable": delta is not None, "type": "reanalysis_value_comparison",
                                 "name": record.get("name"), "reported": want, "recomputed": got,
                                 "difference": delta, "tolerance": tol, "within_tolerance": ok})
            if delta is None:
                continue
            if not ok:
                finding(findings, "msv.reanalysis_value_mismatch", "reproducibility", "high",
                        f"Reanalysis value {record.get('name')} differs by {delta:g}, exceeding declared tolerance {tol:g}.",
                        dict(repro, **record), text, defect_class="numeric_inconsistency",
                        suggestion="Preserve both values and trace provenance; classify the difference only after checking versions and numerical precision.")


def p_value_statements(spec, text, findings, used):
    for item in records(spec.get("p_value_statements")):
        if not isinstance(item, dict):
            continue
        used.update({"p_value_interpretation", "effect_size_ci"})
        claim = norm(item.get("claim") or item.get("interpretation"))
        p = SC.number(item.get("p_value", item.get("p")))
        alpha = SC.number(item.get("alpha")) or 0.05
        if re.search(r"probability (?:that )?(?:the )?null hypothesis is true|chance (?:that )?(?:the )?null|null hypothesis.{0,20}(?:is )?(?:true|false).{0,20}probabil|null.{0,10}probability|原假设为真的概率|原假设.{0,8}概率为", claim, re.I):
            finding(findings, "msv.p_probability_of_null_misread", "p_value_interpretation", "high",
                    "A p-value is interpreted as the posterior probability that H0 is true; it is instead a tail probability under the null and model.",
                    dict(item, source_quote=item.get("source_quote") or claim), text,
                    defect_class="interpretation_error",
                    suggestion="State the data-compatible tail-probability definition and keep posterior probabilities within an explicit Bayesian model.")
        if p is not None and p >= alpha and re.search(r"\b(proves?|demonstrates?|establishes?)\b.{0,50}\b(no|zero|absence of)\b|\b(no effect|equivalent|equivalence|no difference)\b|证明.{0,10}(无效|无差异|等效)|没有效应|等效于", claim, re.I):
            finding(findings, "msv.nonsignificant_as_no_effect", "p_value_interpretation", "high",
                    f"Non-significant p={p:g} is used to claim no effect/equivalence; absence of rejection does not establish absence or equivalence.",
                    item, text, defect_class="interpretation_error",
                    suggestion="Report effect size and CI, and use a prespecified equivalence/non-inferiority margin and appropriate test for such a claim.")
        if p is not None and p < alpha and re.search(r"\b(large|important|clinically meaningful|strong effect|重大效应|临床意义显著|影响很大)\b", claim, re.I) and not truth(item.get("effect_size")):
            finding(findings, "msv.significance_equated_with_importance", "p_value_interpretation", "medium",
                    "Statistical significance is used as evidence of effect magnitude/importance without an accompanying effect estimate.",
                    item, text, defect_class="interpretation_error",
                    suggestion="Interpret magnitude and precision against the domain threshold; statistical significance alone does not establish importance.")
        if item.get("significant_vs_nonsignificant_comparison") is True:
            finding(findings, "msv.significance_difference_without_direct_test", "p_value_interpretation", "high",
                    "Different significance labels in two analyses are treated as evidence that their effects differ; significance is not transitive.",
                    item, text, defect_class="interpretation_error",
                    suggestion="Estimate and test the between-group contrast or interaction directly with its CI; comparing p>alpha with p<alpha is not that test.")
        if item.get("significant") is True and not truth(item.get("effect_size")):
            finding(findings, "msv.effect_size_missing_for_claim", "effect_size_ci", "medium",
                    "A significance-based claim lacks an effect estimate in the supplied statement.", item, text,
                    defect_class="reporting_gap",
                    suggestion="Report the actual effect estimate with its scale and uncertainty; do not infer magnitude from p alone.")


def finalize(spec, text, sources, limits, calculations, findings, used, legacy_ran):
    rank = {"high": 3, "medium": 2, "low": 1}
    findings.sort(key=lambda f: (DIMENSIONS.index(f["dimension"]) if f.get("dimension") in DIMENSIONS else 99,
                                 -rank.get(f.get("severity"), 0), str(f.get("rule")), str(f.get("finding"))))
    for i, f in enumerate(findings, 1):
        f["id"] = f"S{i:03d}"
    dimensions = []
    coverage = spec.get("dimension_coverage", {}) if isinstance(spec.get("dimension_coverage"), dict) else {}
    for dim in DIMENSIONS:
        own = [f for f in findings if f.get("dimension") == dim]
        manuscript = [f for f in own if f.get("scope") == "manuscript"]
        worst = max([rank.get(f.get("severity"), 0) for f in manuscript] or [0])
        cov = coverage.get(dim) if isinstance(coverage.get(dim), dict) else {}
        applicability = "not_applicable" if cov.get("status") == "not_applicable" else "applicable"
        dimensions.append({"dimension": dim, "dimension_zh": DIM_ZH[dim],
                           "input_status": "assessed" if dim in used else "not_assessable",
                           "applicability": applicability,
                           "applicability_rationale": cov.get("rationale"),
                           "status": "not_applicable" if applicability == "not_applicable" and worst == 0 else
                                     "major_revision" if worst == 3 else "minor_revision" if worst == 2
                                     else "attention_suggested" if worst == 1
                                     else "no_defect_detected_in_supplied_scope" if dim in used
                                     else "not_assessable_from_supplied_materials",
                           "finding_ids": [f["id"] for f in own],
                           "highest_severity": next((s for s, n in rank.items() if n == worst), None),
                           "note": "No supplied evidence is not evidence that the paper satisfied this facet.",
                           "applicable_reporting_standard": reporting_standard(spec, dim)})
    man = [f for f in findings if f.get("scope") == "manuscript"]
    proc = [f for f in findings if f.get("scope") == "review_process"]
    counts, pc = Counter(f["severity"] for f in man), Counter(f["severity"] for f in proc)
    numerical_incomplete = any(not c.get("computable") for c in calculations)
    source_incomplete = any("manuscript could not be read" in str(x) or "no manuscript text supplied" in str(x) for x in limits)
    status = "blocked" if any(f["severity"] == "high" for f in findings) else "review" if findings or len(used) < len(DIMENSIONS) or numerical_incomplete or source_incomplete else "clean"
    grade = "major_methods_revision" if any(f["severity"] == "high" for f in man) else "minor_methods_revision" if any(f["severity"] == "medium" for f in man) else "review_incomplete" if findings or len(used) < len(DIMENSIONS) or numerical_incomplete or source_incomplete else "no_major_defect_detected"
    # A completely specified, qualified case must be able to end clean even though
    # some facets are legitimately not applicable rather than not assessable.
    if not findings and spec.get("review_complete") is True and len(used) == len(DIMENSIONS) and not numerical_incomplete and not source_incomplete:
        status, grade = "clean", "no_major_defect_detected"
    quotes = []
    for f in findings:
        q = f.get("location", {}).get("quote")
        if q and contains(text, q):
            quotes.append({"finding_id": f["id"], "quote": q, "location": f["location"]})
    pending = [f["id"] for f in proc] + [f["id"] for f in man if f.get("defect_class") == "reporting_gap"]
    result = {
        "schema_version": SCHEMA, "case_id": spec.get("case_id"), "status": status,
        "overall_assessment": {"grade": grade, "publication_decision": None,
                               "basis": "highest source-bound severity; missing computations and reporting gaps remain distinguishable"},
        "findings": findings, "audit_report": copy.deepcopy(findings),
        "method_dimensions": dimensions,
        "severity_counts": {s: counts.get(s, 0) for s in ("high", "medium", "low")},
        "review_process_severity_counts": {s: pc.get(s, 0) for s in ("high", "medium", "low")},
        "statistical_recalculations": calculations, "recomputations": calculations,
        "evidence_and_boundaries": {"manuscript_quotes": quotes,
                                    "field_evidence": [{"dimension": d["dimension"], "input_status": d["input_status"],
                                                        "applicable_reporting_standard": d["applicable_reporting_standard"]} for d in dimensions],
                                    "pending_review": pending,
                                    "not_checked": [d["dimension"] for d in dimensions if d["input_status"] == "not_assessable"],
                                    "not_computable": [{"index": i, "name": c.get("name"), "type": c.get("type"),
                                                        "reason": c.get("reason")} for i, c in enumerate(calculations) if not c.get("computable")]},
        "result_status": {"pass": [d["dimension"] for d in dimensions if d["status"] == "no_defect_detected_in_supplied_scope"],
                          "problems": [f["id"] for f in man], "pending": pending,
                          "not_checked": [d["dimension"] for d in dimensions if d["input_status"] == "not_assessable"],
                          "status": status, "status_reason": f"{len(man)} study findings; {len(proc)} review-process findings; {sum(not c.get('computable') for c in calculations)} non-computable checks"},
        "sources": sources, "checked": {"dimensions": len(DIMENSIONS), "dimensions_with_inputs": len(used),
                                         "recalculations": len(calculations), "legacy_sections": legacy_ran},
        "limits": limits + ["Normal-power results are approximations, not exact noncentral-t power.",
                            "JB, Levene, BP/RESET and VIF are diagnostic signals, not standalone proof of method invalidity.",
                            "Non-computable values indicate missing inputs and are not method errors."],
        "review_receipt": {"engine": SCHEMA, "deterministic_order": True,
                           "calculation_engine": "statscore standard-library formulas",
                           "dimensions": list(DIMENSIONS), "reporting_guideline_role": "reporting completeness only"},
    }
    if result["case_id"] is None:
        del result["case_id"]
    contract(spec, result)
    return result


def reporting_standard(spec, dim):
    design = norm(spec.get("design")).lower()
    if any(k in design for k in ("rct", "randomized", "randomised", "随机")):
        mapping = {
            "randomization_blinding": "CONSORT: sequence generation, allocation concealment, implementation, blinding",
            "sample_size_power": "CONSORT: sample-size determination and stopping guidance",
            "independent_units": "CONSORT: unit of randomisation and participant flow",
            "effect_size_ci": "CONSORT: effect size and precision for each outcome",
            "missing_data": "CONSORT: numbers analysed and losses/exclusions",
            "reproducibility": "CONSORT: protocol, registration and statistical methods traceability",
        }
        return mapping.get(dim, "CONSORT reporting item where applicable; not a quality/design certificate")
    return "SAMPL-style statistical reporting where applicable; a reporting checklist does not validate the design"


def contract(spec, result):
    c = spec.get("output_contract")
    keys = list(c) if isinstance(c, dict) else [str(k) for k in c] if isinstance(c, list) else []
    aliases = {"review_report": "audit_report", "审查报告": "audit_report", "method_assessment": "method_dimensions",
               "维度审查": "method_dimensions", "calculations": "statistical_recalculations",
               "复算": "statistical_recalculations", "evidence": "evidence_and_boundaries",
               "依据与边界": "evidence_and_boundaries", "uncertainty": "limits", "不确定性": "limits"}
    for key in keys:
        if key in result:
            continue
        if key in aliases:
            result[key] = copy.deepcopy(result[aliases[key]])
        elif key in spec and key not in BULKY:
            result[key] = copy.deepcopy(spec[key])
        else:
            result[key] = None
            result.setdefault("limits", []).append(f"output_contract field '{key}' was not derivable by this audit")


def load_csv(path):
    raw = path.read_bytes()
    text = None
    for enc in ("utf-8-sig", "utf-16", "gb18030"):
        try:
            text = raw.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    if text is None:
        raise ValueError("CSV is not UTF-8/UTF-16/GB18030 text")
    rows = []
    for row in csv.DictReader(text.splitlines()):
        clean = {}
        for key, val in row.items():
            if key is None:
                continue
            num = SC.number(val)
            clean[key] = num if num is not None and norm(val) else val
        rows.append(clean)
    return rows


def audit(spec, manuscript_override=None, data_override=None, base_dir=None):
    if not isinstance(spec, dict):
        return refusal(spec, "case input must be a JSON object")
    # Wrong input types must not be reinterpreted as scientific design defects.
    for key in ("design", "model", "model_type", "research_question_type", "question_type",
                "outcome_type", "conclusion", "causal_claim"):
        if key in spec and spec[key] is not None and not isinstance(spec[key], str):
            return refusal(spec, f"field '{key}' must be a string, not {type(spec[key]).__name__}")
    for key in (*TEXT_KEYS,):
        if key in spec and spec[key] is not None and not isinstance(spec[key], str):
            return refusal(spec, f"field '{key}' must contain manuscript text as a string, not {type(spec[key]).__name__}")
    for key in ("statistical_checks", "checks", "power_analyses", "comparison_families",
                "diagnostics", "p_value_statements", "review_findings"):
        if key in spec and spec[key] is not None and not isinstance(spec[key], (list, dict)):
            return refusal(spec, f"field '{key}' must be an object or array, not {type(spec[key]).__name__}")
    base = Path(base_dir) if base_dir else Path.cwd()
    external = data_override or spec.get("data_path")
    external_data = []
    data_limits = []
    if external:
        path = Path(external)
        if not path.is_absolute():
            path = base / path
        try:
            external_data = load_csv(path)
        except (OSError, ValueError, csv.Error) as exc:
            data_limits.append(f"CSV could not be loaded: {exc}; raw-data checks remain non-computable")
    text, limits, sources = load_text(spec, base, manuscript_override)
    limits.extend(data_limits)
    structured_present = any(k in spec for k in ("design", "variables", "statistical_checks", "checks", "diagnostics",
                                                  "power_analyses", "comparison_families", "independence", "review_findings"))
    if not text.strip() and not structured_present:
        return refusal(spec, "neither readable manuscript text nor auditable structured statistical inputs were supplied", limits)
    calculations, findings, used = [], [], set()
    evidence_validate(spec, text, findings)
    analysis_checks(spec, text, calculations, findings, used)
    # Power can be supplied separately from other statistical checks.
    for item in records(spec.get("power_analyses")):
        if isinstance(item, dict):
            analysis_checks({"statistical_checks": [dict(item, type="power")]}, text, calculations, findings, used)
    multiplicity_checks(spec, text, calculations, findings, used)
    diagnostics(spec, external_data, text, calculations, findings, used)
    design_and_reporting(spec, text, calculations, findings, used)
    p_value_statements(spec, text, findings, used)
    legacy_ran = run_legacy(spec, findings, limits)
    # Dimensions require supplied inputs or an explicit, justified applicability
    # decision. review_complete alone cannot turn unread facets into a clean pass.
    coverage = spec.get("dimension_coverage", {})
    if isinstance(coverage, dict):
        for dim, state in coverage.items():
            if (dim in DIMENSIONS and isinstance(state, dict) and
                    state.get("status") in {"not_applicable", "assessed"} and norm(state.get("rationale"))):
                used.add(dim)
    if any(k in spec for k in ("sample_size", "sample_size_basis", "recruited_n", "analysed_n")):
        used.add("sample_size_power")
    if "model" in spec or "model_type" in spec:
        used.add("model_choice")
    if "confidence_intervals" in spec or "p_values_reported" in spec:
        used.add("effect_size_ci")
    if "reproduce" in legacy_ran:
        used.add("reproducibility")
    if "results_discussion" in legacy_ran:
        used.update({"p_value_interpretation", "effect_size_ci"})
    return finalize(spec, text, sources, limits, calculations, findings, used, legacy_ran)


def refusal(spec, message, limits=None):
    findings = [{"id": "S001", "rule": "msv.input_not_readable", "severity": "high",
                 "dimension": "reproducibility", "dimension_zh": DIM_ZH["reproducibility"],
                 "finding": message, "message": message, "scope": "review_process",
                 "defect_class": "execution_failure", "location": {},
                 "suggestion": "Provide readable source text or structured analysis inputs, then rerun."}]
    result = {"schema_version": SCHEMA, "status": "undetermined",
              "overall_assessment": {"grade": "not_assessable", "publication_decision": None},
              "findings": findings, "audit_report": findings,
              "method_dimensions": [{"dimension": d, "dimension_zh": DIM_ZH[d], "input_status": "not_assessable",
                                     "status": "not_assessable_from_supplied_materials", "finding_ids": ["S001"]} for d in DIMENSIONS],
              "severity_counts": {"high": 0, "medium": 0, "low": 0},
              "review_process_severity_counts": {"high": 1, "medium": 0, "low": 0},
              "statistical_recalculations": [], "recomputations": [],
              "evidence_and_boundaries": {"manuscript_quotes": [], "field_evidence": [],
                                            "pending_review": ["S001"], "not_checked": list(DIMENSIONS), "not_computable": []},
              "result_status": {"pass": [], "problems": [], "pending": ["S001"],
                                "not_checked": list(DIMENSIONS), "status": "undetermined", "status_reason": message},
              "sources": [], "checked": {"dimensions": len(DIMENSIONS), "dimensions_with_inputs": 0, "recalculations": 0},
              "limits": list(limits or []) + [message]}
    if isinstance(spec, dict):
        if spec.get("case_id") is not None:
            result["case_id"] = spec.get("case_id")
        contract(spec, result)
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(prog="statsrun", description=__doc__)
    parser.add_argument("--case"), parser.add_argument("--spec"), parser.add_argument("--manuscript")
    parser.add_argument("--data"), parser.add_argument("--out", default="out_stats")
    try:
        args, unknown = parser.parse_known_args(argv)
    except SystemExit:
        args, unknown = None, ["argument parsing failed"]
    if args is None or unknown or not (args.case or args.spec):
        out = Path(args.out) if args else Path("out_stats")
        result = refusal({}, "expected --case or --spec and readable study inputs")
        write(out, result)
        print(json.dumps({"status": "undetermined", "wrote": str(out / "result.json")}, ensure_ascii=False))
        return 5
    source = args.case or args.spec
    try:
        spec = json.loads(Path(source).read_text(encoding="utf-8"))
        if not isinstance(spec, dict):
            result = refusal(spec, "case input must be a JSON object")
        else:
            try:
                result = audit(spec, args.manuscript, args.data, Path(source).resolve().parent)
            except Exception as exc:
                result = refusal(spec, f"audit refused after input/processing error: {exc}")
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        result = refusal({}, f"case file is not readable JSON: {exc}")
    error = write(Path(args.out), result)
    if error:
        print(json.dumps({"status": "undetermined", "error": error}, ensure_ascii=False))
        return 5
    print(json.dumps({"status": result["status"], "grade": result.get("overall_assessment", {}).get("grade"),
                      "findings": [f.get("rule") for f in result.get("findings", [])],
                      "recalculations": len(result.get("statistical_recalculations", [])),
                      "wrote": str(Path(args.out) / "result.json")}, ensure_ascii=False))
    return {"clean": 0, "review": 3, "blocked": 4, "undetermined": 5}[result["status"]]


def write(out, result):
    try:
        out.mkdir(parents=True, exist_ok=True)
        (out / "result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return None
    except OSError as exc:
        return f"result.json could not be written: {exc}"


if __name__ == "__main__":
    raise SystemExit(main())
