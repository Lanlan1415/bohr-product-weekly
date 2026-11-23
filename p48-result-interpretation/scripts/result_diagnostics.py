"""Observation-first trend, anomaly, SPC and effect-size calculations.
Pure functions over typed table rows; no causal inference or row deletion.
"""
from __future__ import annotations

import math


def num(x):
    if isinstance(x, bool):
        return None
    try:
        y = float(x)
        return y if math.isfinite(y) else None
    except (TypeError, ValueError, OverflowError):
        return None


def avg(x):
    return sum(x) / len(x) if x else None


def sd(x):
    return math.sqrt(sum((v - avg(x)) ** 2 for v in x) / (len(x) - 1)) if len(x) > 1 else None


def perc(vals, q):
    s = sorted(vals)
    if not s:
        return None
    if len(s) == 1:
        return s[0]
    p = q * (len(s) - 1)
    lo, frac = int(p), p - int(p)
    return s[lo] * (1 - frac) + s[min(lo + 1, len(s) - 1)] * frac


def rnd(x):
    return round(x, 10) if isinstance(x, float) and math.isfinite(x) else x


def t_value(df):
    table = [(1, 12.706), (2, 4.303), (3, 3.182), (4, 2.776), (5, 2.571),
             (6, 2.447), (7, 2.365), (8, 2.306), (9, 2.262), (10, 2.228),
             (15, 2.131), (20, 2.086), (25, 2.06), (30, 2.042)]
    record = table if df >= 30 else [(d, t) for d, t in table if d <= df]
    if record:
        degrees, val = max(record)
        return val, degrees, "lookup t(0.975, floor(df))"
    return 2.0, df, "explicit large-df approximation"


def ci(x):
    if len(x) < 2:
        return None
    t, degrees, method = t_value(len(x) - 1)
    s = sd(x) / math.sqrt(len(x))
    return {"low": rnd(avg(x) - t * s), "high": rnd(avg(x) + t * s),
            "df": len(x) - 1, "method": method}


def linear(points):
    """Least squares, with honest residual/R2 diagnostics rather than a story."""
    if len(points) < 2:
        return {"direction": "unverifiable", "n": len(points)}
    xl = [x for x, _ in points]; yl = [y for _, y in points]
    xm, ym = avg(xl), avg(yl)
    divisor = sum((x - xm) ** 2 for x in xl)
    if divisor <= 1e-15:
        return {"direction": "order_is_constant_no_slope", "n": len(points),
                "delta_last_minus_first": rnd(yl[-1] - yl[0]), "y_range": rnd(max(yl) - min(yl))}
    slope = sum((x - xm) * (y - ym) for x, y in points) / divisor
    intercept = ym - slope * xm
    residuals = [y - (intercept + slope * x) for x, y in points]
    sst = sum((y - ym) ** 2 for y in yl)
    sse = sum(r * r for r in residuals)
    r2 = 1 - sse / sst if sst > 0 else (1.0 if sse == 0 else 0.0)
    dslope = math.sqrt(sse / (len(points) - 2) / divisor) if len(points) > 2 else None
    return {"n": len(points), "x_min": xl[0], "x_max": xl[-1], "first_y": yl[0],
            "last_y": yl[-1], "delta_last_minus_first": yl[-1] - yl[0], "y_range": max(yl) - min(yl),
            "slope_per_declared_x_unit": slope, "intercept": intercept, "r_squared": r2,
            "slope_standard_error": dslope, "max_absolute_residual": max(map(abs, residuals)),
            "formula": "OLS y = intercept + slope*x; descriptive, not a causal model or a causal knot"}


def deseason_trend(rowdata, response, xcol, tolerance=None, xunit=None, yunit=None):
    rows = [(num(r["values"].get(xcol)), num(r["values"].get(response)), r) for r in rowdata]
    usable = [(x, y, r) for x, y, r in rows if x is not None and y is not None]
    usable.sort(key=lambda a: (a[0], a[1], a[2]["row_index"]))
    pts = [(a, b) for a, b, _ in usable]
    fit = linear(pts)
    if "slope_per_declared_x_unit" in fit:
        tol = num(tolerance)
        if tol is not None:
            feature = "approximate_flat_within_tolerance" if abs(fit["slope_per_declared_x_unit"]) <= tol else (
                "increasing" if fit["slope_per_declared_x_unit"] > 0 else "decreasing")
        else:
            feature = "linear_slope_positive" if fit["slope_per_declared_x_unit"] > 0 else (
                "linear_slope_negative" if fit["slope_per_declared_x_unit"] < 0 else "flat_zero_slope")
    else:
        feature = fit["direction"]
    plateau = None if num(tolerance) is None else {
        "test": "successive-difference intervals within declared tolerance",
        "runs": plateau_runs(usable, float(tolerance)),
        "tolerance": tolerance,
        "not_a_certificate_of_biological_equilibrium": True}
    bp = None
    if len(pts) >= 6:
        best = None
        for cut in range(2, len(pts) - 1):
            before, after = linear(pts[:cut]), linear(pts[cut:])
            sse = sum((y - (a["intercept"] + a["slope_per_declared_x_unit"] * x)) ** 2
                      for part, a in ((pts[:cut], before), (pts[cut:], after))
                      for x, y in part)
            if best is None or sse < best["sse"]:
                best = {"cut": cut, "at_x": pts[cut][0], "sse": sse, "before": before, "after": after}
        bp = {"rule": "candidate hinge minimizes SSE over ordered two-line pieces",
              "min_candidates_per_piece": 2, "not_ci_or_mechanism_proof": True, **best}
    return {"response": response, "order_column": xcol,
            "n_ordered_observations": len(pts), "computed_observation": {k: rnd(v) if isinstance(v, float) else v for k, v in fit.items()},
            "observed_direction_label": feature, "x_unit": xunit, "y_unit": yunit,
            "plateau_analysis": plateau, "candidate_change_point": bp,
            "source_rows": [u[2]["source"] for u in usable],
            "unverified_inputs": [{"row_index": r["row_index"], "where": xcol if x is None else response}
                                   for x, y, r in rows if x is None or y is None],
            "interpretation_class": "computed_data_summary; no mechanism inferred"}


def plateau_runs(points, tolerance):
    out, run = [], []
    for index, (_, y, r) in enumerate(points):
        if run and abs(y - run[-1]["value"]) <= tolerance:
            run.append({"value": y, "row_index": r["row_index"]})
        else:
            if len(run) >= 2:
                out.append(run)
            run = [{"value": y, "row_index": r["row_index"]}]
    if len(run) >= 2:
        out.append(run)
    return [{"first_row_index": run[0]["row_index"], "last_row_index": run[-1]["row_index"],
             "n": len(run)} for run in out]


def point_q(records):
    values = [r["numeric"] for r in records if r.get("numeric") is not None]
    Q1, Q3 = perc(values, 0.25), perc(values, 0.75)
    med = perc(values, 0.5)
    mad = perc([abs(v - med) for v in values], 0.5) if med is not None and values else None
    return values, Q1, Q3, med, mad


def reference_tables(rowdata, response):
    groups = {}
    for r in rowdata:
        if num(r["values"].get(response)) is not None:
            groups.setdefault(tuple(sorted(r["group_key"].items())), []).append(r)
    return groups


def robust_anomalies(rowdata, response, min_n=6, iqr_k=3.0, anomaly_group=None):
    out = []
    for group_key, records in sorted(reference_tables(rowdata, response).items()):
        vals, q1, q3, med, mad = point_q(records)
        if len(vals) < min_n or q1 is None or q3 is None:
            continue
        iqr = q3 - q1
        lower, upper = q1 - iqr_k * iqr, q3 + iqr_k * iqr
        rs = mad * 1.4826 if mad is not None else None
        for r in records:
            v = r["numeric"]
            rule = None
            if iqr > 0 and (v < lower or v > upper):
                rule = "far_out_iqr_" + str(iqr_k)
            z = (v - med) / rs if rs and rs > 0 else None
            if z is not None and abs(z) > 3.5:
                rule = (rule + "+" if rule else "") + "robust_mad_z_gt_3.5"
            if iqr == 0 and v != med:
                rule = "constant_reference_deviation"
            if not rule:
                continue
            robust_effect = (v - med) / rs if rs and rs > 0 else None
            out.append({"anomaly_id": f"row-{r['row_index']}-{response}", "response": response,
                "row_index": r["row_index"], "value": v,
                "group": anomaly_group if anomaly_group is not None else dict(group_key),
                "source": r["source"], "detection_rule": rule, "n_in_reference_group": len(vals),
                "reference": {"median": med, "q1": q1, "q3": q3, "iqr": iqr, "mad": mad,
                               "robust_sigma_if_nonzero": rs, "far_out_iqr_fence": [lower, upper]},
                "deviation_from_median": v - med, "robust_z": z, "robust_effect": robust_effect,
                "threshold_source": "declared rule and current data group, not an external physical limit",
                "retained_in_primary_analysis": True,
                "retention_decision": "flagged for review; not deleted, capped, or imputed"})
    return out


def effect(recordgroups, left, right, pair_key, config):
    if not left or not right:
        return None
    left_vals = [r["numeric"] for r in left if r.get("numeric") is not None]
    right_vals = [r["numeric"] for r in right if r.get("numeric") is not None]
    a = {"metric": config.get("response"), "left_group": config.get("left"), "right_group": config.get("right"),
         "comparison_type": "descriptive_observational_effect", "source_left": [r["source"] for r in left],
         "source_right": [r["source"] for r in right], "n_left_rows": len(left_vals), "n_right_rows": len(right_vals)}
    if pair_key:
        for side, group in (("left", left), ("right", right)):
            counts = {}
            for r in group:
                key = str(r["values"].get(pair_key))
                if key != "None":
                    counts[key] = counts.get(key, 0) + 1
            if any(n > 1 for n in counts.values()) and not config.get("average_technical_replicates"):
                a.update(comparison_type="ambiguous_pairing", paired_by=pair_key,
                         duplicate_pair_keys={side: sorted(k for k, n in counts.items() if n > 1)},
                         not_causal_effect=True,
                         error="duplicate pair identifiers; no last-row-wins pairing; explicitly average technical replicates only if permitted")
                return a
        def pair_map(group):
            indexed = {}
            for r in group:
                if r["values"].get(pair_key) is not None:
                    indexed.setdefault(str(r["values"][pair_key]), []).append(r)
            output = {}
            for k, vals in indexed.items():
                output[k] = dict(vals[-1])
                output[k]["numeric"] = avg([r["numeric"] for r in vals if r.get("numeric") is not None]) if len(vals) > 1 else vals[-1]["numeric"]
            return output
        left_map, right_map = pair_map(left), pair_map(right)
        if config.get("average_technical_replicates"):
            a["technical_replicate_aggregation"] = "arithmetic mean within pair key; such repeats remain non-independent"
        keys = sorted(set(left_map) & set(right_map))
        deltas = [right_map[k]["numeric"] - left_map[k]["numeric"] for k in keys
                  if right_map[k].get("numeric") is not None and left_map[k].get("numeric") is not None]
        a.update(comparison_type="paired_difference", n_pairs=len(deltas),
                 mean_difference=avg(deltas) if deltas else None, sd_difference=sd(deltas),
                 mean_difference_ci95=ci(deltas) if len(deltas) > 1 else None,
                 paired_by=pair_key, paired_keys=keys,
                 independence="declaration-dependent pairing; split/fold sharing is not an independent biological replicate" if "split" in str(pair_key).lower() or "fold" in str(pair_key).lower() else
                              "declared independent pairs; input supplies this evidence")
        if len(deltas) > 1 and sd(deltas) and sd(deltas) > 0:
            a["cohens_dz"] = avg(deltas) / sd(deltas)
        a["effect_formula"] = "mean(pairwise right-left); Cohen dz = mean(delta)/sd(delta)"
        a["not_causal_effect"] = True
        return {k: rnd(v) if isinstance(v, float) else v for k, v in a.items()}
    m_left, m_right = avg(left_vals), avg(right_vals)
    a.update(comparison_type="two_group_difference", mean_left=m_left, mean_right=m_right,
             mean_difference_right_minus_left=(m_right - m_left if m_left is not None and m_right is not None else None),
             relative_difference=(m_right - m_left) / abs(m_left) if m_left not in (None, 0) and m_right is not None else None,
             ci95_left=ci(left_vals), ci95_right=ci(right_vals))
    if len(left_vals) >= 2 and len(right_vals) >= 2:
        n1, n2, sa, sb = len(left_vals), len(right_vals), sd(left_vals), sd(right_vals)
        pooled = math.sqrt(((n1 - 1) * sa ** 2 + (n2 - 1) * sb ** 2) / (n1 + n2 - 2))
        standard_error = math.sqrt(sa ** 2 / n1 + sb ** 2 / n2)
        dfn = (standard_error ** 4) / (((sa ** 2 / n1) ** 2 / (n1 - 1)) + ((sb ** 2 / n2) ** 2 / (n2 - 1))) if standard_error else None
        a["cohens_d_pooled"] = (m_right - m_left) / pooled if pooled > 0 else None
        a["hedges_g"] = a["cohens_d_pooled"] * (1 - 3 / (4 * (n1 + n2) - 9)) if a["cohens_d_pooled"] is not None else None
        if dfn and dfn > 1:
            t, used_df, method = t_value(dfn)
            mdiff = m_right - m_left
            a["welch_mean_difference_ci95"] = {"low": mdiff - t * standard_error,
                                                "high": mdiff + t * standard_error,
                                                "df": dfn, "critical_df_lookup": used_df, "method": method}
    a["uncertainty_scope"] = "row-level intervals under the declared table mapping; no new independent experimental units inferred"
    a["effect_formula"] = "right mean - left mean; pooled SD / Hedges correction when n>=2; Welch interval for mean difference"
    a["not_causal_effect"] = True
    return {k: rnd(v) if isinstance(v, float) else v for k, v in a.items()}


def sensitivity(recordgroups, response, left, right, anomalies):
    keys = sorted({r["row_index"] for r in left + right})
    removed = {a["row_index"] for a in anomalies if a.get("response") == response}
    keep_left = [r for r in left if r["row_index"] not in removed]
    keep_right = [r for r in right if r["row_index"] not in removed]
    left_v = [r["numeric"] for r in left if r.get("numeric") is not None]
    right_v = [r["numeric"] for r in right if r.get("numeric") is not None]
    a, b = [r["numeric"] for r in keep_left if r.get("numeric") is not None], [r["numeric"] for r in keep_right if r.get("numeric") is not None]
    return {"response": response, "left_group": config_label(left), "right_group": config_label(right),
            "primary_all_rows_mean_delta": avg(right_v) - avg(left_v) if left_v and right_v else None,
            "sensitivity_without_flagged_mean_delta": avg(b) - avg(a) if a and b else None,
            "flagged_row_indices": sorted(removed), "all_rows_retained_in_primary": True,
            "note": "influence analysis only; dropping flagged points is not default data cleaning or a confirmed correction"}


def config_label(rows):
    if not rows:
        return None
    return rows[0].get("group_key")


def spc(rowdata, response, config, default_order=None):
    cfg = dict(config)
    order = cfg.get("order_column", default_order)
    if not order:
        return {"status": "unconfigured", "reason": "SPC needs a declared order_column and an independent baseline reference"}
    usable = sorted((r for r in rowdata if num(r["values"].get(response)) is not None and num(r["values"].get(order)) is not None),
                    key=lambda r: (num(r["values"][order]), r["row_index"]))
    baseline_filter = cfg.get("baseline_filter") if isinstance(cfg.get("baseline_filter"), dict) else None
    baseline = [r for r in usable if baseline_filter and all(str(r["original"].get(k)) == str(v) for k, v in baseline_filter.items())]
    centre = num(cfg.get("centerline"))
    sigma = num(cfg.get("sigma"))
    method = "declared centerline/sigma"
    if centre is None or sigma is None:
        if not baseline:
            return {"status": "unconfigured", "response": response, "reason": "no centerline/sigma or baseline_filter supplied; do not pretend a baseline exists"}
        centre = avg([r["numeric"] for r in baseline]) if centre is None else centre
        sigma = sd([r["numeric"] for r in baseline]) if sigma is None else sigma
        method = "estimated only from explicitly declared baseline_filter rows"
        if len(baseline) < 6:
            return {"status": "insufficient_baseline", "response": response,
                    "n_baseline": len(baseline), "reason": "at least six declared reference rows are required to estimate process limits"}
    if not cfg.get("source") and not baseline_filter:
        return {"status": "unconfigured", "reason": "centerline/sigma must be source-grounded or explicitly estimated from baseline_filter"}
    if sigma is None or sigma <= 0:
        return {"status": "degenerate_sigma", "response": response, "centerline": centre, "sigma": sigma,
                "reason": "non-positive or unavailable sigma cannot support a numeric control-limit claim"}
    center_result = []
    for r in usable:
        z = (r["numeric"] - centre) / sigma
        if abs(z) > 3:
            center_result.append({"rule": "beyond_3_sigma", "row_index": r["row_index"], "value": r["numeric"],
                                      "z": z, "source": r["source"], "retained_in_primary_analysis": True})
    length = int(num(cfg.get("run_length", 8)) or 8)
    signs = []
    for r in usable:
        z = (r["numeric"] - centre) / sigma
        signs.append(1 if z > 0 else -1 if z < 0 else 0)
    for sign in (-1, 1):
        for start in range(0, len(usable) - length + 1):
            if all(x == sign for x in signs[start:start + length]):
                block = usable[start:start + length]
                center_result.append({"rule": f"run_{length}_same_side", "side": sign,
                                       "first_row": block[0]["row_index"], "last_row": block[-1]["row_index"],
                                       "source": [r["source"] for r in block]})
                break  # one run per side, not hundreds of redundant overlapping events
    trend_length = int(num(cfg.get("trend_length", 6)) or 6)
    if trend_length >= 2:
        for slope_sign in (-1, 1):
            found = False
            for start in range(0, len(usable) - trend_length + 1):
                diffs = [usable[i + 1]["numeric"] - usable[i]["numeric"] for i in range(start, start + trend_length - 1)]
                if all(d > 0 for d in diffs) or (slope_sign == -1 and all(d < 0 for d in diffs)):
                    block = usable[start:start + trend_length]
                    center_result.append({"rule": f"trend_{trend_length}_monotonic",
                                           "first_row": block[0]["row_index"], "last_row": block[-1]["row_index"],
                                           "source": [r["source"] for r in block]})
                    found = True
                    break
            if found:
                continue
    return {"response": response, "status": "calculated", "order_column": order,
            "centerline": centre, "sigma": sigma, "sigma_method": method, "source": cfg.get("source"),
            "baseline_filter": baseline_filter, "n_time_points": len(usable),
            "control_limits": [centre - 3 * sigma, centre + 3 * sigma],
            "reference": "https://www.itl.nist.gov/div898/handbook/pmc/section3/pmc31.htm",
            "rules": "beyond 3 sigma; one run per side of length>=8; 6 strictly monotonic points",
            "events": center_result,
            "warning": "SPC flags assignable-cause investigations; limits are not universal biological effect thresholds or proof of process stability"}
