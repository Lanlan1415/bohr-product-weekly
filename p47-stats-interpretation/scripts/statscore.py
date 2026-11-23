"""Direct statistical analyses with assumptions, effects, intervals and corrections.

All values are calculated from the supplied rows. Undefined quantities remain
null with an explicit reason. The module is stdlib-only; Student/F probabilities
come from statsinterp's independently anchored incomplete-beta implementation.
"""
from __future__ import annotations

import itertools
import math
from collections import Counter
from functools import lru_cache

import statsinterp as S

ALPHA = 0.05
Z975 = 1.959963984540054


def _finite_values(rows, column):
    out = []
    for value in S.column_values(rows, column):
        if math.isfinite(value):
            out.append(float(value))
    return out


def _quantile(values, p):
    values = sorted(values)
    if not values:
        return None
    idx = (len(values) - 1) * p
    lo = int(math.floor(idx))
    hi = min(lo + 1, len(values) - 1)
    frac = idx - lo
    return values[lo] * (1 - frac) + values[hi] * frac


def _describe(values, total_rows=None):
    n = len(values)
    rec = {"n": n, "n_excluded": None if total_rows is None else total_rows - n,
           "mean": None, "sd": None, "median": _quantile(values, 0.5),
           "q1": _quantile(values, 0.25), "q3": _quantile(values, 0.75),
           "min": min(values) if values else None, "max": max(values) if values else None}
    if values:
        rec["mean"] = sum(values) / n
        variance = S._variance(values)
        rec["sd"] = math.sqrt(variance) if variance is not None else None
        rec.update(S._moments(values))
    return rec


def jarque_bera(values):
    """Asymptotic JB normality diagnostic; not a proof of normality."""
    n = len(values)
    if n < 8 or S._variance(values) in (None, 0):
        return {"statistic": None, "df": 2, "p": None, "status": "undetermined",
                "reason": "JB requires n>=8 and non-zero variance; normality is not established"}
    moments = S._moments(values)
    jb = n / 6.0 * (moments["skew"] ** 2 + moments["excess_kurtosis"] ** 2 / 4.0)
    return {"statistic": jb, "df": 2, "p": math.exp(-jb / 2.0),
            "status": "computed", "method": "Jarque-Bera asymptotic chi-square(df=2)",
            "caution": "failure to reject does not prove normality"}


def _anova(groups):
    usable = {str(k): v for k, v in groups.items() if len(v) >= 1}
    k, n = len(usable), sum(len(v) for v in usable.values())
    if k < 2 or n <= k:
        return None
    grand = sum(x for v in usable.values() for x in v) / n
    ssb = sum(len(v) * (sum(v) / len(v) - grand) ** 2 for v in usable.values())
    ssw = sum((x - sum(v) / len(v)) ** 2 for v in usable.values() for x in v)
    if ssw <= 0 or not math.isfinite(ssw):
        return None
    msw = ssw / (n - k)
    f = (ssb / (k - 1)) / msw
    sst = ssb + ssw
    eta = ssb / sst if sst > 0 else None
    omega = (ssb - (k - 1) * msw) / (sst + msw) if sst + msw > 0 else None
    return {"F": f, "df1": k - 1, "df2": n - k, "p": S.f_sf(f, k - 1, n - k),
            "eta_squared": eta, "omega_squared": omega,
            "cohen_f": math.sqrt(eta / (1 - eta)) if eta is not None and 0 <= eta < 1 else None,
            "n": n, "k_groups": k, "ss_between": ssb, "ss_within": ssw}


def brown_forsythe(groups):
    """Brown-Forsythe/Levene-centred-at-median variance diagnostic."""
    deviations = {}
    for name, values in groups.items():
        if len(values) < 2:
            return {"F": None, "p": None, "status": "undetermined",
                    "reason": "each group needs at least two values"}
        median = _quantile(values, 0.5)
        deviations[name] = [abs(x - median) for x in values]
    result = _anova(deviations)
    if result is None:
        return {"F": None, "p": None, "status": "undetermined",
                "reason": "absolute deviations have zero residual variance"}
    return {"F": result["F"], "df1": result["df1"], "df2": result["df2"],
            "p": result["p"], "status": "computed",
            "method": "Brown-Forsythe (one-way ANOVA of absolute deviations from group medians)",
            "caution": "Welch does not require equal variances; classical ANOVA does"}


def _ranks(values):
    order = sorted(range(len(values)), key=lambda i: values[i])
    ranks = [0.0] * len(values)
    pos = 0
    while pos < len(order):
        end = pos + 1
        while end < len(order) and values[order[end]] == values[order[pos]]:
            end += 1
        rank = (pos + 1 + end) / 2.0
        for j in order[pos:end]:
            ranks[j] = rank
        pos = end
    return ranks


def _normal_two_sided(z):
    return min(1.0, math.erfc(abs(z) / math.sqrt(2.0)))


def _mann_whitney_exact(n1, n2, observed):
    @lru_cache(maxsize=None)
    def count(a, b, u):
        if u < 0 or u > a * b:
            return 0
        if a == 0 or b == 0:
            return 1 if u == 0 else 0
        return count(a - 1, b, u - b) + count(a, b - 1, u)
    total = math.comb(n1 + n2, n1)
    u = int(round(observed))
    lower = sum(count(n1, n2, j) for j in range(u + 1)) / total
    upper = sum(count(n1, n2, j) for j in range(u, n1 * n2 + 1)) / total
    return min(1.0, 2.0 * min(lower, upper))


def mann_whitney(a, b):
    """Independent rank test, positive effect means b tends to exceed a."""
    na, nb = len(a), len(b)
    if na < 1 or nb < 1:
        return None
    combined = a + b
    ranks = _ranks(combined)
    rank_b = sum(ranks[na:])
    u_b = rank_b - nb * (nb + 1) / 2.0
    effect = 2.0 * u_b / (na * nb) - 1.0
    counts = Counter(combined)
    tied = any(v > 1 for v in counts.values())
    if not tied and na * nb <= 100 and max(na, nb) <= 50:
        p = _mann_whitney_exact(na, nb, u_b)
        method = "exact conditional U distribution (no ties)"
        z = None
    else:
        n = na + nb
        tie_sum = sum(t ** 3 - t for t in counts.values())
        variance = na * nb / 12.0 * ((n + 1) - tie_sum / (n * (n - 1)))
        if variance <= 0:
            return {"test": "mann_whitney", "status": "undetermined", "U": u_b,
                    "p": None, "rank_biserial": effect,
                    "reason": "all values are tied; rank-test variance is zero"}
        delta = u_b - na * nb / 2.0
        z = (delta - math.copysign(0.5, delta)) / math.sqrt(variance) if delta else 0.0
        p = _normal_two_sided(z)
        method = "normal approximation with tie and continuity correction"
    return {"test": "mann_whitney", "status": "computed", "U": u_b, "z": z,
            "p": p, "p_method": method, "rank_biserial": effect,
            "effect_orientation": "positive means group_b tends to exceed group_a",
            "ci95": {"low": None, "high": None, "status": "undetermined",
                     "reason": "no distribution-free mean-difference CI is claimed for a rank test"}}


def _welch(a, b):
    result = S.welch_test(a, b)
    if result is None:
        return None
    na, nb = len(a), len(b)
    va, vb = S._variance(a), S._variance(b)
    diff = sum(b) / nb - sum(a) / na
    se = math.sqrt(va / na + vb / nb)
    critical = S.t_two_sided_critical(ALPHA, result["df"])
    d = S.cohens_d(a, b)
    correction = 1 - 3 / (4 * (na + nb) - 9)
    result.update({"test": "welch", "status": "computed", "mean_difference": diff,
                   "difference_orientation": "group_b minus group_a",
                   "ci95": {"low": diff - critical * se, "high": diff + critical * se,
                            "confidence": 0.95, "parameter": "difference of means"},
                   "cohen_d": d, "hedges_g": d * correction if d is not None else None})
    return result


def _gammainc_q(a, x):
    """Regularised upper incomplete gamma Q(a,x), Numerical Recipes method."""
    if x < 0 or a <= 0:
        return None
    if x == 0:
        return 1.0
    gln = math.lgamma(a)
    if x < a + 1.0:
        term, total = 1.0 / a, 1.0 / a
        for n in range(1, 1000):
            term *= x / (a + n)
            total += term
            if abs(term) <= abs(total) * 3e-15:
                break
        return max(0.0, min(1.0, 1.0 - total * math.exp(-x + a * math.log(x) - gln)))
    b, c = x + 1.0 - a, 1e300
    d, h = 1.0 / b, 1.0 / b
    for i in range(1, 1000):
        an = -i * (i - a)
        b += 2.0
        d = an * d + b
        if abs(d) < 1e-300:
            d = 1e-300
        c = b + an / c
        if abs(c) < 1e-300:
            c = 1e-300
        d = 1.0 / d
        delta = d * c
        h *= delta
        if abs(delta - 1.0) < 3e-15:
            break
    return max(0.0, min(1.0, math.exp(-x + a * math.log(x) - gln) * h))


def chi_square_sf(x, df):
    if not isinstance(df, int) or df < 1 or x < 0 or not math.isfinite(x):
        return None
    return _gammainc_q(df / 2.0, x / 2.0)


def _kruskal(groups):
    names = list(groups)
    n = sum(len(groups[g]) for g in names)
    k = len(names)
    if k < 3 or any(len(groups[g]) < 1 for g in names):
        return None
    all_values = [x for g in names for x in groups[g]]
    ranks = _ranks(all_values)
    rank_sums, start = {}, 0
    for g in names:
        rank_sums[g] = sum(ranks[start:start + len(groups[g])])
        start += len(groups[g])
    h = 12.0 / (n * (n + 1)) * sum(rank_sums[g] ** 2 / len(groups[g]) for g in names) - 3 * (n + 1)
    counts = Counter(all_values)
    correction = 1.0 - sum(t ** 3 - t for t in counts.values()) / (n ** 3 - n)
    if correction <= 0:
        return {"test": "kruskal_wallis", "status": "undetermined", "H": None, "p": None,
                "reason": "all values tied; tie correction is zero"}
    h /= correction
    return {"test": "kruskal_wallis", "status": "computed", "H": h, "df": k - 1,
            "p": chi_square_sf(h, k - 1), "epsilon_squared": (h - k + 1) / (n - k),
            "tie_correction": correction, "n": n, "k_groups": k,
            "ci95": {"low": None, "high": None, "status": "undetermined",
                     "reason": "an omnibus rank test has no single mean-difference CI"}}


def _paired(rows, metric, group_col, group_a, group_b, pair_col, requested, alpha):
    if not pair_col:
        return {"status": "undetermined", "test": None,
                "reason": "paired design requires pair_id; treating paired rows as independent is forbidden"}
    pairs = {}
    for i, row in enumerate(rows):
        if str(row.get(group_col, "")).strip() not in (str(group_a), str(group_b)):
            continue
        key = str(row.get(pair_col, "")).strip()
        if key:
            pairs.setdefault(key, []).append((i, row))
    diffs, excluded = [], []
    for key, entries in pairs.items():
        arows = [r for _, r in entries if str(r.get(group_col, "")).strip() == str(group_a)]
        brows = [r for _, r in entries if str(r.get(group_col, "")).strip() == str(group_b)]
        va, vb = _finite_values(arows, metric), _finite_values(brows, metric)
        if len(arows) != 1 or len(brows) != 1 or len(va) != 1 or len(vb) != 1:
            excluded.append(key)
            continue
        diffs.append(vb[0] - va[0])
    base = {"design": "paired", "pair_id": pair_col, "n_pairs": len(diffs),
            "excluded_pair_ids": sorted(excluded), "differences": _describe(diffs),
            "assumptions": {"differences_normality": jarque_bera(diffs)}}
    if len(diffs) < 2:
        return {**base, "status": "undetermined", "test": None, "p": None,
                "reason": "fewer than two complete pairs"}
    normality = base["assumptions"]["differences_normality"]
    test = requested
    if test == "auto":
        test = "wilcoxon" if len(diffs) < 8 or (normality.get("p") is not None and normality["p"] < alpha) else "paired_t"
    base["test"] = test
    if test == "paired_t":
        mean = sum(diffs) / len(diffs)
        sd = math.sqrt(S._variance(diffs))
        if sd <= 0:
            return {**base, "status": "undetermined", "p": None,
                    "reason": "paired differences have zero variance; t is undefined"}
        df = len(diffs) - 1
        se = sd / math.sqrt(len(diffs))
        t = mean / se
        p = S.t_two_sided_p(t, df)
        critical = S.t_two_sided_critical(ALPHA, df)
        return {**base, "status": "computed", "t": t, "df": df, "p": p,
                "mean_difference": mean, "cohen_dz": mean / sd,
                "ci95": {"low": mean - critical * se, "high": mean + critical * se,
                         "confidence": 0.95, "parameter": "mean paired difference (b-a)"}}
    if test != "wilcoxon":
        return {**base, "status": "undetermined", "p": None,
                "reason": "paired design supports paired_t, wilcoxon or auto"}
    nonzero = [d for d in diffs if d != 0]
    base["n_zero_differences"] = len(diffs) - len(nonzero)
    base["n_ranked_pairs"] = len(nonzero)
    if not nonzero:
        return {**base, "status": "undetermined", "p": None,
                "reason": "all paired differences are zero"}
    absvals = [abs(d) for d in nonzero]
    ranks = _ranks(absvals)
    wplus = sum(r for r, d in zip(ranks, nonzero) if d > 0)
    wminus = sum(r for r, d in zip(ranks, nonzero) if d < 0)
    total = sum(ranks)
    tied = len(set(absvals)) != len(absvals)
    if not tied and len(nonzero) <= 25:
        distribution = [1] + [0] * int(total)
        for rank in range(1, len(nonzero) + 1):
            for value in range(int(total), rank - 1, -1):
                distribution[value] += distribution[value - rank]
        count = sum(distribution)
        w = int(round(wplus))
        lower = sum(distribution[:w + 1]) / count
        upper = sum(distribution[w:]) / count
        p = min(1.0, 2 * min(lower, upper))
        method, z = "exact signed-rank distribution (no ties, zeros removed)", None
    else:
        variance = sum(r * r for r in ranks) / 4.0
        if variance <= 0:
            return {**base, "status": "undetermined", "p": None,
                    "reason": "signed-rank variance is zero"}
        delta = wplus - total / 2.0
        z = (delta - math.copysign(0.5, delta)) / math.sqrt(variance) if delta else 0.0
        p, method = _normal_two_sided(z), "normal approximation with tie/continuity correction"
    return {**base, "status": "computed", "W_plus": wplus, "W_minus": wminus, "z": z,
            "p": p, "p_method": method, "matched_rank_biserial": (wplus - wminus) / total,
            "ci95": {"low": None, "high": None, "status": "undetermined",
                     "reason": "no unrequested Walsh/Hodges-Lehmann interval is invented"}}


def adjust_pvalues(pvalues, method="holm", alpha=ALPHA):
    """Statsmodels-style adjusted p values and reject decisions in input order."""
    method = str(method or "holm").lower()
    aliases = {"bonf": "bonferroni", "holm-bonferroni": "holm", "bh": "fdr_bh",
               "fdr": "fdr_bh", "none": "none", "unadjusted": "none"}
    method = aliases.get(method, method)
    if method not in ("bonferroni", "holm", "fdr_bh", "none"):
        raise ValueError("correction must be bonferroni, holm, fdr_bh or none")
    if not 0 < alpha < 1:
        raise ValueError("alpha must be between zero and one")
    if any(not isinstance(p, (int, float)) or not math.isfinite(p) or not 0 <= p <= 1
           for p in pvalues):
        raise ValueError("every p value must be finite and in [0,1]")
    m = len(pvalues)
    if not m:
        return []
    adjusted = [None] * m
    if method == "none":
        adjusted = list(pvalues)
    elif method == "bonferroni":
        adjusted = [min(1.0, p * m) for p in pvalues]
    elif method == "holm":
        running = 0.0
        for rank, (p, index) in enumerate(sorted((p, i) for i, p in enumerate(pvalues))):
            running = max(running, (m - rank) * p)
            adjusted[index] = min(1.0, running)
    else:
        running = 1.0
        ordered = sorted((p, i) for i, p in enumerate(pvalues))
        for rank in range(m, 0, -1):
            p, index = ordered[rank - 1]
            running = min(running, p * m / rank)
            adjusted[index] = min(1.0, running)
    return [{"index": i, "p_raw": p, "p_adjusted": adjusted[i],
             "reject": adjusted[i] <= alpha, "method": method, "alpha": alpha, "m": m}
            for i, p in enumerate(pvalues)]


def _power_limit(n_values):
    return {"status": "undetermined", "observed_n": n_values,
            "post_hoc_power_computed": False,
            "reason": "prospective effect size, target power, allocation and design assumptions were not supplied",
            "interpretation": "p>=alpha does not establish equivalence; observed post-hoc power adds no independent evidence",
            "scope": "sample-size planning is outside this task; report the usable n and this limitation"}


def _format_p(p):
    if p is None:
        return "undetermined"
    return "<1e-12" if p < 1e-12 else f"{p:.6g}"


def _result_text(rec):
    if rec.get("status") != "computed":
        return "统计结果 undetermined：" + str(rec.get("reason") or "输入不足或检验退化")
    p = _format_p(rec.get("p"))
    if rec.get("test") == "welch":
        ci = rec["ci95"]
        return (f"{rec['group_b']} 相对 {rec['group_a']} 的均值差（b-a）={rec['mean_difference']:.6g}，"
                f"95% CI [{ci['low']:.6g}, {ci['high']:.6g}]；Welch t({rec['df']:.4g})="
                f"{rec['t']:.6g}，p={p}，Hedges g={rec['hedges_g']:.6g}。"
                "统计显著不等于实际重要；观察性比较不能据此断言因果。")
    if rec.get("test") == "paired_t":
        ci = rec["ci95"]
        return (f"配对差值（b-a）均值={rec['mean_difference']:.6g}，95% CI "
                f"[{ci['low']:.6g}, {ci['high']:.6g}]；paired t({rec['df']})={rec['t']:.6g}，"
                f"p={p}，Cohen dz={rec['cohen_dz']:.6g}。n={rec['n_pairs']} 个完整配对；不显著不证明等效。")
    if rec.get("test") == "mann_whitney":
        return (f"Mann–Whitney U={rec['U']:.6g}，p={p}（{rec['p_method']}），"
                f"rank-biserial={rec['rank_biserial']:.6g}（正值表示 b 倾向更高）。"
                "该秩检验不默认等同均值差检验；CI 未确定，不能编造。相关/组间关联不自动等于因果。")
    if rec.get("test") == "wilcoxon":
        return (f"Wilcoxon W+={rec['W_plus']:.6g}，p={p}（{rec['p_method']}），"
                f"matched rank-biserial={rec['matched_rank_biserial']:.6g}；"
                f"完整配对 n={rec['n_pairs']}，零差剔除 n={rec['n_zero_differences']}。不显著不证明等效。")
    if rec.get("test") == "anova":
        return (f"单因素 ANOVA：F({rec['df1']},{rec['df2']})={rec['F']:.6g}，p={p}，"
                f"eta²={rec['eta_squared']:.6g}，omega²={rec['omega_squared']:.6g}。"
                f"两两比较采用 {rec.get('correction')} 校正；整体关联不证明因果。")
    if rec.get("test") == "kruskal_wallis":
        return (f"Kruskal–Wallis H({rec['df']})={rec['H']:.6g}，p={p}，"
                f"epsilon²={rec['epsilon_squared']:.6g}；两两比较采用 {rec.get('correction')} 校正。"
                "整体秩差异不指定某一组，也不证明因果。")
    return "p=" + p + "；统计关联不自动等于因果。"


def _independent(rows, request, alpha):
    metric = str(request.get("metric") or "").strip()
    group_col = str(request.get("group_col") or "group").strip()
    if not metric or not group_col:
        return {"status": "undetermined", "reason": "metric and group_col are required"}
    labels = sorted({str(r.get(group_col, "")).strip() for r in rows
                     if str(r.get(group_col, "")).strip()})
    if request.get("groups") is not None:
        if not isinstance(request["groups"], list) or not all(isinstance(g, (str, int, float)) for g in request["groups"]):
            return {"status": "undetermined", "reason": "groups must be a list of scalar labels"}
        selected = [str(g).strip() for g in request["groups"]]
        labels = [g for g in labels if g in selected]
    if len(labels) < 2:
        return {"status": "undetermined", "reason": "fewer than two non-empty groups", "groups_seen": labels}
    grouped_rows = {g: [r for r in rows if str(r.get(group_col, "")).strip() == g] for g in labels}
    groups = {g: _finite_values(grouped_rows[g], metric) for g in labels}
    base = {"design": "independent", "metric": metric, "group_col": group_col,
            "group_a": labels[0], "group_b": labels[1] if len(labels) == 2 else None,
            "groups_seen": labels, "n_by_group": {g: len(groups[g]) for g in labels},
            "excluded_by_group": {g: len(grouped_rows[g]) - len(groups[g]) for g in labels},
            "descriptives_by_group": {g: _describe(groups[g], len(grouped_rows[g])) for g in labels},
            "duplicates_removed": False,
            "missing_policy": "available values only; named missing/unparsed/non-finite cells excluded and counted"}
    if any(len(groups[g]) < 2 for g in labels):
        return {**base, "status": "undetermined", "p": None,
                "reason": "each group needs at least two usable finite values"}
    normality = {g: jarque_bera(groups[g]) for g in labels}
    variance = brown_forsythe(groups)
    base["assumptions"] = {"normality_jarque_bera": normality, "variance_brown_forsythe": variance}
    requested = str(request.get("test") or ("welch" if len(labels) == 2 else "anova")).lower().replace("-", "_")
    aliases = {"t": "welch", "t_test": "welch", "welch_t": "welch", "mw": "mann_whitney",
               "mann_whitney_u": "mann_whitney", "one_way_anova": "anova",
               "kruskal": "kruskal_wallis", "kruskalwallis": "kruskal_wallis"}
    requested = aliases.get(requested, requested)
    nonnormal = any(j.get("p") is not None and j["p"] < alpha for j in normality.values())
    small = any(len(groups[g]) < 8 for g in labels)
    if requested == "auto":
        requested = ("mann_whitney" if len(labels) == 2 else "kruskal_wallis") if (nonnormal or small) else ("welch" if len(labels) == 2 else "anova")
        base["selection_reason"] = f"auto: small_sample={small}, JB_nonnormal={nonnormal}"
    base["requested_test"] = str(request.get("test") or ("welch" if len(labels) == 2 else "anova"))
    if len(labels) == 2:
        a, b = groups[labels[0]], groups[labels[1]]
        if requested == "welch":
            rec = _welch(a, b)
            if rec is None:
                return {**base, "status": "undetermined", "test": "welch", "p": None,
                        "reason": "Welch test is undefined (zero variance or insufficient residual df)"}
            return {**base, **rec}
        if requested == "mann_whitney":
            return {**base, **mann_whitney(a, b)}
        return {**base, "status": "undetermined", "test": requested, "p": None,
                "reason": "two independent groups support welch, mann_whitney or auto"}
    if requested == "anova":
        rec = _anova(groups)
        if rec is None:
            return {**base, "status": "undetermined", "test": "anova", "p": None,
                    "reason": "ANOVA is undefined because within-group variance is zero"}
        rec["test"] = "anova"
        rec["status"] = "computed"
    elif requested == "kruskal_wallis":
        rec = _kruskal(groups)
        if rec.get("status") != "computed":
            return {**base, **rec}
    else:
        return {**base, "status": "undetermined", "test": requested, "p": None,
                "reason": "three or more independent groups support anova, kruskal_wallis or auto"}
    correction = str(request.get("correction") or "holm").lower()
    pairs = []
    for ga, gb in itertools.combinations(labels, 2):
        pair = _welch(groups[ga], groups[gb]) if rec["test"] == "anova" else mann_whitney(groups[ga], groups[gb])
        pairs.append({"group_a": ga, "group_b": gb, "test": pair.get("test"),
                      "p": pair.get("p"), "mean_difference": pair.get("mean_difference"),
                      "ci95": pair.get("ci95"), "effect_size":
                          pair.get("hedges_g") if rec["test"] == "anova" else pair.get("rank_biserial")})
    try:
        adjusted = adjust_pvalues([p["p"] for p in pairs], correction, alpha)
    except ValueError as exc:
        return {**base, "status": "undetermined", "reason": str(exc)}
    for pair, adj in zip(pairs, adjusted):
        pair.update(adj)
    rec["pairwise_comparisons"] = pairs
    rec["correction"] = correction
    rec["multiple_testing"] = {"method": correction, "m": len(pairs), "alpha": alpha,
                               "family": f"{metric} across {len(labels)} groups",
                               "adjusted_values_computed": True}
    return {**base, **rec}


def correlation(rows, request, alpha=ALPHA):
    xcol, ycol = request.get("x"), request.get("y")
    if not isinstance(xcol, str) or not isinstance(ycol, str) or not xcol or not ycol:
        return {"status": "undetermined", "reason": "correlation requires string x and y columns"}
    pairs = []
    for row in rows:
        x, y = _finite_values([row], xcol), _finite_values([row], ycol)
        if len(x) == len(y) == 1:
            pairs.append((x[0], y[0]))
    n = len(pairs)
    method = str(request.get("method") or "pearson").lower()
    if n < 3:
        return {"status": "undetermined", "x": xcol, "y": ycol, "n": n,
                "reason": "fewer than three complete finite pairs"}
    xs, ys = [p[0] for p in pairs], [p[1] for p in pairs]
    if method == "spearman":
        xs, ys = _ranks(xs), _ranks(ys)
    elif method != "pearson":
        return {"status": "undetermined", "reason": "method must be pearson or spearman"}
    vx, vy = S._variance(xs), S._variance(ys)
    if not vx or not vy:
        return {"status": "undetermined", "x": xcol, "y": ycol, "n": n,
                "reason": "correlation undefined for a zero-variance column"}
    mx, my = sum(xs) / n, sum(ys) / n
    r = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / math.sqrt(vx * vy) / (n - 1)
    r = max(-1.0, min(1.0, r))
    if abs(r) == 1:
        p = 0.0
        t = None
    else:
        t = r * math.sqrt((n - 2) / (1 - r * r))
        p = S.t_two_sided_p(t, n - 2)
    ci = {"low": None, "high": None, "status": "undetermined",
          "reason": "Fisher z interval needs n>=4 and |r|<1"}
    if n >= 4 and abs(r) < 1:
        z = math.atanh(r)
        half = Z975 / math.sqrt(n - 3)
        ci = {"low": math.tanh(z - half), "high": math.tanh(z + half),
              "status": "computed", "confidence": 0.95, "method": "Fisher z"}
    rec = {"status": "computed", "x": xcol, "y": ycol, "method": method, "n": n,
           "n_excluded_pairwise": len(rows) - n, "r": r, "t": t, "df": n - 2, "p": p,
           "ci95": ci, "causation_established": False,
           "caution": "correlation does not establish causation; Spearman p/CI use the common large-sample approximation"}
    rec["result_text"] = (f"{method} r={r:.6g}，n={n}，p={_format_p(p)}，95% CI "
                          + (f"[{ci['low']:.6g}, {ci['high']:.6g}]" if ci["status"] == "computed" else "undetermined")
                          + "。相关不等于因果，区间是相关参数的区间而非个体预测范围。")
    return rec


def run_statistical(rows, spec):
    """Run explicitly requested direct analyses and correlations."""
    requests = spec.get("analyses")
    if requests is None and isinstance(spec.get("analysis"), dict):
        requests = [spec["analysis"]]
    if requests is None and spec.get("metrics") and spec.get("group_col"):
        requests = [{"metric": m, "group_col": spec["group_col"],
                     "test": spec.get("test", "auto"),
                     "correction": spec.get("multiple_correction", "holm")}
                    for m in spec["metrics"] if isinstance(m, str)]
    if requests is None:
        requests = []
    if not isinstance(requests, list):
        return {"analyses": [], "correlations": [], "multiple_testing_families": [],
                "findings": [{"rule": "stats.analysis_malformed", "severity": "high",
                              "message": "analyses must be a list of request objects"}]}
    findings, analyses, families = [], [], []
    for i, request in enumerate(requests):
        if not isinstance(request, dict):
            analyses.append({"request_index": i, "status": "undetermined", "reason": "request is not an object"})
            continue
        alpha = request.get("alpha", spec.get("alpha", ALPHA))
        if not isinstance(alpha, (int, float)) or isinstance(alpha, bool) or not 0 < alpha < 1:
            rec = {"status": "undetermined", "reason": "alpha must be numeric and between zero and one"}
        else:
            try:
                restriction = spec.get("_analysis_restriction")
                if restriction:
                    rec = {"status": "undetermined", "test": None,
                           "reason": str(restriction), "duplicates_unresolved": True}
                else:
                    design = str(request.get("design") or "independent").lower()
                    if design == "paired" or request.get("pair_id"):
                        labels = request.get("groups") or []
                        ga = request.get("group_a") or (labels[0] if len(labels) > 0 else None)
                        gb = request.get("group_b") or (labels[1] if len(labels) > 1 else None)
                        if ga is None or gb is None:
                            rec = {"status": "undetermined", "reason": "paired analysis requires group_a and group_b"}
                        else:
                            rec = _paired(rows, str(request.get("metric") or ""),
                                          str(request.get("group_col") or spec.get("group_col") or "group"),
                                          str(ga), str(gb), request.get("pair_id"),
                                          str(request.get("test") or "paired_t").lower().replace("-", "_"), alpha)
                    else:
                        rec = _independent(rows, request, alpha)
            except Exception as exc:
                rec = {"status": "undetermined", "reason": f"analysis refused: {exc}"}
        rec["request_index"] = i
        rec["power_and_sample_size"] = _power_limit(rec.get("n_pairs") or sum((rec.get("n_by_group") or {}).values()))
        rec["result_text"] = _result_text(rec)
        analyses.append(rec)
        if rec.get("status") != "computed":
            findings.append({"rule": "stats.analysis_undetermined", "severity": "high",
                             "request_index": i, "message": rec.get("reason")})
        if rec.get("multiple_testing"):
            families.append(rec["multiple_testing"] | {"request_index": i})
        if rec.get("test") in ("welch", "paired_t", "anova"):
            normal = rec.get("assumptions", {}).get("differences_normality") if rec.get("test") == "paired_t" else None
            normals = ([normal] if normal else list(rec.get("assumptions", {}).get("normality_jarque_bera", {}).values()))
            if any(n and n.get("p") is not None and n["p"] < alpha for n in normals):
                findings.append({"rule": "stats.normality_diagnostic", "severity": "medium",
                                 "request_index": i,
                                 "message": "JB diagnostic rejects normality; do not present parametric p as assumption-free"})
        variance = rec.get("assumptions", {}).get("variance_brown_forsythe", {})
        if rec.get("test") == "anova" and variance.get("p") is not None and variance["p"] < alpha:
            findings.append({"rule": "stats.variance_diagnostic", "severity": "medium",
                             "request_index": i,
                             "message": "Brown-Forsythe rejects variance homogeneity; classical ANOVA needs review"})
    corr_requests = spec.get("correlations") or []
    if not isinstance(corr_requests, list):
        findings.append({"rule": "stats.correlation_malformed", "severity": "high",
                         "message": "correlations must be a list"})
        corr_requests = []
    correlations = []
    for i, request in enumerate(corr_requests):
        if not isinstance(request, dict):
            rec = {"status": "undetermined", "reason": "correlation request is not an object"}
        else:
            try:
                restriction = spec.get("_analysis_restriction")
                if restriction:
                    rec = {"status": "undetermined", "reason": str(restriction),
                           "duplicates_unresolved": True}
                else:
                    rec = correlation(rows, request)
            except Exception as exc:
                rec = {"status": "undetermined", "reason": f"correlation refused: {exc}"}
        rec["request_index"] = i
        correlations.append(rec)
        if rec.get("status") != "computed":
            findings.append({"rule": "stats.correlation_undetermined", "severity": "high",
                             "request_index": i, "message": rec.get("reason")})
    return {"analyses": analyses, "correlations": correlations,
            "multiple_testing_families": families, "findings": findings,
            "limitations": ["Power/sample-size planning is not estimated from the observed effect; see each power_and_sample_size record.",
                            "Statistical association, including correlation and group differences, does not by itself establish causation."]}
