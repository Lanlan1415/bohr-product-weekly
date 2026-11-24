"""Deterministic standard-library statistics for manuscript audit inputs.

Implemented mechanisms follow the published SciPy/statsmodels definitions:
Student/Welch independent tests and effect sizes, Levene's absolute-deviation
ANOVA, Jarque-Bera residual screening, OLS auxiliary-regression Breusch-Pagan,
Ramsey RESET F tests, VIF, Fisher-z correlation intervals and BH/BY/Holm/
Bonferroni multiplicity adjustments.  This module performs real arithmetic and
returns explicit non-computable states instead of treating missing data as an
analysis error.  No NumPy/SciPy import is required.
"""
from __future__ import annotations

import math
from statistics import NormalDist

ND = NormalDist()


def number(value):
    if value is None or isinstance(value, bool):
        return None
    try:
        x = float(str(value).replace(",", "").strip())
        return x if math.isfinite(x) else None
    except (TypeError, ValueError, OverflowError):
        return None


def clean_numbers(values):
    if not isinstance(values, (list, tuple)):
        return []
    return [x for x in (number(v) for v in values) if x is not None]


def _betacf(a, b, x):
    qab, qap, qam = a + b, a + 1.0, a - 1.0
    c = 1.0
    d = 1.0 - qab * x / qap
    if abs(d) < 1e-300:
        d = 1e-300
    d = 1.0 / d
    h = d
    for m in range(1, 201):
        m2 = 2 * m
        aa = m * (b - m) * x / ((qam + m2) * (a + m2))
        d = 1.0 + aa * d
        c = 1.0 + aa / c
        if abs(d) < 1e-300:
            d = 1e-300
        if abs(c) < 1e-300:
            c = 1e-300
        d = 1.0 / d
        h *= d * c
        aa = -(a + m) * (qab + m) * x / ((a + m2) * (qap + m2))
        d = 1.0 + aa * d
        c = 1.0 + aa / c
        if abs(d) < 1e-300:
            d = 1e-300
        if abs(c) < 1e-300:
            c = 1e-300
        d = 1.0 / d
        delta = d * c
        h *= delta
        if abs(delta - 1.0) < 3e-14:
            return h
    raise ArithmeticError("incomplete beta did not converge")


def beta_inc(a, b, x):
    if min(a, b) <= 0 or not math.isfinite(a + b):
        raise ValueError("beta parameters must be positive")
    if x <= 0:
        return 0.0
    if x >= 1:
        return 1.0
    front = math.exp(math.lgamma(a + b) - math.lgamma(a) - math.lgamma(b)
                     + a * math.log(x) + b * math.log1p(-x))
    if x < (a + 1.0) / (a + b + 2.0):
        return front * _betacf(a, b, x) / a
    return 1.0 - front * _betacf(b, a, 1.0 - x) / b


def gamma_p(a, x):
    """Regularized lower incomplete gamma P(a,x), numerical Recipes form."""
    if a <= 0 or x < 0:
        raise ValueError("invalid incomplete gamma input")
    if x == 0:
        return 0.0
    if x < a + 1.0:
        ap, total, delta = a, 1.0 / a, 1.0 / a
        for _ in range(1, 301):
            ap += 1.0
            delta *= x / ap
            total += delta
            if abs(delta) < abs(total) * 3e-14:
                break
        return total * math.exp(-x + a * math.log(x) - math.lgamma(a))
    # Continued fraction for Q, then complement.
    b = x + 1.0 - a
    c = 1e300
    d = 1.0 / b
    h = d
    for i in range(1, 301):
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
        if abs(delta - 1.0) < 3e-14:
            break
    q = math.exp(-x + a * math.log(x) - math.lgamma(a)) * h
    return 1.0 - q


def chi2_sf(stat, df):
    if df <= 0:
        return None
    if stat < 0:
        return 1.0
    return min(1.0, max(0.0, 1.0 - gamma_p(df / 2.0, stat / 2.0)))


def f_sf(stat, df1, df2):
    if df1 <= 0 or df2 <= 0 or stat < 0 or not math.isfinite(stat):
        return None
    x = df2 / (df2 + df1 * stat) if stat else 1.0
    return min(1.0, max(0.0, beta_inc(df2 / 2.0, df1 / 2.0, x)))


def t_cdf(t, df):
    if df <= 0:
        return None
    if t == 0:
        return 0.5
    twice_tail = beta_inc(df / 2.0, 0.5, df / (df + t * t))
    return 1.0 - twice_tail / 2.0 if t > 0 else twice_tail / 2.0


def t_sf_two(t, df):
    if not math.isfinite(t) or df <= 0:
        return None
    return min(1.0, max(0.0, beta_inc(df / 2.0, 0.5, df / (df + t * t))))


def t_ppf(prob, df):
    if not 0 < prob < 1 or df <= 0:
        return None
    if prob == 0.5:
        return 0.0
    lo, hi = -1.0, 1.0
    while t_cdf(lo, df) > prob:
        lo *= 2
        if lo < -1e7:
            break
    while t_cdf(hi, df) < prob:
        hi *= 2
        if hi > 1e7:
            break
    for _ in range(100):
        mid = (lo + hi) / 2
        if t_cdf(mid, df) < prob:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


def _p_from_t(t, df, alternative):
    if alternative == "two-sided":
        return t_sf_two(t, df)
    cdf = t_cdf(t, df)
    return 1.0 - cdf if alternative == "greater" else cdf


def independent_t(mean1, sd1, n1, mean2, sd2, n2, equal_var=False,
                  alternative="two-sided", confidence=0.95):
    m1, m2, s1, s2 = map(number, (mean1, mean2, sd1, sd2))
    n1, n2 = number(n1), number(n2)
    if alternative not in {"two-sided", "greater", "less"}:
        return {"computable": False, "reason": "alternative must be two-sided, greater or less"}
    if not 0 < confidence < 1:
        return {"computable": False, "reason": "confidence must be in (0,1)"}
    if not all(x is not None for x in (m1, m2, s1, s2, n1, n2)) or n1 <= 1 or n2 <= 1:
        return {"computable": False, "reason": "two groups with numeric means, sample SDs and n>1 are required"}
    if n1 != int(n1) or n2 != int(n2) or s1 < 0 or s2 < 0:
        return {"computable": False, "reason": "integer sample sizes and non-negative sample SDs are required"}
    n1, n2 = int(n1), int(n2)
    df = n1 + n2 - 2
    pooled_var = ((n1 - 1) * s1 * s1 + (n2 - 1) * s2 * s2) / df
    difference = m1 - m2
    if equal_var:
        se = math.sqrt(pooled_var * (1 / n1 + 1 / n2))
        test_df = df
        test = "student_independent_t"
    else:
        v1, v2 = s1 * s1 / n1, s2 * s2 / n2
        se = math.sqrt(v1 + v2)
        denom = v1 * v1 / (n1 - 1) + v2 * v2 / (n2 - 1)
        test_df = (v1 + v2) ** 2 / denom if denom > 0 else None
        test = "welch_independent_t"
    if se == 0 or test_df is None or test_df <= 0:
        return {"computable": False, "reason": "zero standard error or undefined degrees of freedom",
                "mean_difference": difference, "standard_error": se}
    statistic = difference / se
    p = _p_from_t(statistic, test_df, alternative)
    critical = t_ppf(1 - (1 - confidence) / 2, test_df) if alternative == "two-sided" else t_ppf(confidence, test_df)
    if alternative == "less":
        ci = [-math.inf, difference + critical * se]
    elif alternative == "greater":
        ci = [difference - critical * se, math.inf]
    else:
        ci = [difference - critical * se, difference + critical * se]
    d = difference / math.sqrt(pooled_var) if pooled_var > 0 else None
    correction = 1 - 3 / (4 * df - 1) if df > 0.25 else None
    return {"computable": True, "test": test, "mean_difference": difference,
            "standard_error": se, "statistic": statistic, "df": test_df,
            "p_value": p, "alternative": alternative, "confidence": confidence,
            "mean_difference_ci": ci, "cohens_d": d,
            "hedges_g": d * correction if d is not None and correction is not None else None,
            "hedges_correction": correction,
            "inputs": {"mean1": m1, "sd1": s1, "n1": n1,
                       "mean2": m2, "sd2": s2, "n2": n2,
                       "equal_var": bool(equal_var)}}


def mean_sd(values, sample=True):
    xs = clean_numbers(values)
    if len(xs) < (2 if sample else 1):
        return None, None, len(xs)
    mean = sum(xs) / len(xs)
    variance = sum((x - mean) ** 2 for x in xs) / (len(xs) - (1 if sample else 0))
    return mean, math.sqrt(max(0.0, variance)), len(xs)


def _centering(values, method, proportiontocut=0.05):
    xs = sorted(clean_numbers(values))
    if method == "mean":
        return sum(xs) / len(xs)
    if method == "trimmed":
        cut = int(len(xs) * proportiontocut)
        tail = xs[cut:len(xs) - cut] if len(xs) - 2 * cut else xs
        return sum(tail) / len(tail)
    mid = len(xs) // 2
    return xs[mid] if len(xs) % 2 else (xs[mid - 1] + xs[mid]) / 2


def levene(groups, center="median", proportiontocut=0.05):
    if center not in {"median", "mean", "trimmed"}:
        return {"computable": False, "reason": "center must be median, mean or trimmed"}
    gs = [clean_numbers(g) for g in groups if isinstance(g, (list, tuple))]
    if len(gs) < 2 or any(len(g) < 2 for g in gs) or len(groups) != len(gs):
        return {"computable": False, "reason": "at least two fully numeric groups with n>=2 each are required"}
    zs = [[abs(x - _centering(g, center, proportiontocut)) for x in g] for g in gs]
    all_z = [x for g in zs for x in g]
    grand = sum(all_z) / len(all_z)
    means = [sum(g) / len(g) for g in zs]
    ssb = sum(len(g) * (m - grand) ** 2 for g, m in zip(zs, means))
    ssw = sum(sum((x - m) ** 2 for x in g) for g, m in zip(zs, means))
    df1, df2 = len(zs) - 1, len(all_z) - len(zs)
    if ssw == 0:
        return {"computable": False, "reason": "all absolute deviations are identical; Levene F is undefined",
                "df1": df1, "df2": df2}
    statistic = (ssb / df1) / (ssw / df2)
    return {"computable": True, "test": "levene_absolute_deviation_anova", "center": center,
            "statistic": statistic, "df1": df1, "df2": df2, "p_value": f_sf(statistic, df1, df2),
            "null": "population variances are equal; non-rejection does not prove equality"}


def jarque_bera(values):
    xs = clean_numbers(values)
    if len(xs) != len(values) if isinstance(values, (list, tuple)) else True:
        return {"computable": False, "reason": "all observations must be numeric"}
    if len(xs) < 8:
        return {"computable": False, "reason": "JB is offered only for n>=8 and remains an asymptotic screening test"}
    mean, sd_mle, n = mean_sd(xs, sample=False)
    if not sd_mle:
        return {"computable": False, "reason": "zero variance makes moments undefined"}
    skew = sum((x - mean) ** 3 for x in xs) / n / sd_mle ** 3
    excess = sum((x - mean) ** 4 for x in xs) / n / sd_mle ** 4 - 3
    statistic = n / 6 * (skew ** 2 + excess ** 2 / 4)
    return {"computable": True, "test": "jarque_bera", "n": n, "skewness": skew,
            "excess_kurtosis": excess, "statistic": statistic, "df": 2,
            "p_value": chi2_sf(statistic, 2),
            "interpretation_limit": "asymptotic normality screen; non-rejection is not proof of normality"}


def _mmult(left, right):
    return [[sum(a * b for a, b in zip(row, col)) for col in zip(*right)] for row in left]


def _solve(matrix, vector):
    n = len(matrix)
    a = [list(map(float, row)) + [float(vector[i])] for i, row in enumerate(matrix)]
    scale = max((abs(x) for row in matrix for x in row), default=1.0)
    for col in range(n):
        pivot = max(range(col, n), key=lambda r: abs(a[r][col]))
        if abs(a[pivot][col]) <= 1e-11 * max(1.0, scale):
            raise ValueError("design matrix is rank deficient")
        a[col], a[pivot] = a[pivot], a[col]
        div = a[col][col]
        a[col] = [x / div for x in a[col]]
        for row in range(n):
            if row == col:
                continue
            factor = a[row][col]
            a[row] = [x - factor * y for x, y in zip(a[row], a[col])]
    return [a[i][-1] for i in range(n)]


def ols(y, x, add_intercept=True):
    ys, rows = clean_numbers(y), x
    if not isinstance(rows, list) or not rows or len(rows) != len(ys):
        raise ValueError("X and y must have the same positive number of rows")
    design = []
    for row in rows:
        if number(row) is not None:
            vals = [number(row)]
        elif isinstance(row, (list, tuple)):
            vals = [number(v) for v in row]
            if any(v is None for v in vals):
                raise ValueError("X contains a nonnumeric value")
        else:
            raise ValueError("X rows must be numeric values or sequences")
        design.append(([1.0] if add_intercept else []) + vals)
    if len(ys) <= len(design[0]):
        raise ValueError("need more observations than fitted parameters")
    xt = list(zip(*design))
    xtx = [[sum(a * b for a, b in zip(col1, col2)) for col2 in xt] for col1 in xt]
    xty = [sum(a * b for a, b in zip(col, ys)) for col in xt]
    coef = _solve(xtx, xty)
    fitted = [sum(a * b for a, b in zip(row, coef)) for row in design]
    residual = [a - b for a, b in zip(ys, fitted)]
    sse = sum(e * e for e in residual)
    mean = sum(ys) / len(ys)
    tss = sum((v - mean) ** 2 for v in ys)
    r2 = 1 - sse / tss if tss > 0 else None
    return {"n": len(ys), "design": design, "coefficients": coef, "fitted": fitted,
            "residuals": residual, "sse": sse, "tss": tss, "r2": r2,
            "df_resid": len(ys) - len(design[0]), "p": len(design[0])}


def breusch_pagan(residuals, exog_het):
    if not isinstance(exog_het, list) or len(exog_het) != len(residuals):
        return {"computable": False, "reason": "residuals and exog_het must have matching rows"}
    try:
        aux = ols([e * e for e in residuals], exog_het, add_intercept=False)
        if aux["r2"] is None:
            return {"computable": False, "reason": "squared residuals have zero variance"}
        df1 = aux["p"] - 1
        if df1 <= 0:
            return {"computable": False, "reason": "constant-only exog_het has no heteroskedasticity degrees of freedom"}
        lm = aux["n"] * aux["r2"]
        fvalue = (aux["r2"] / df1) / ((1 - aux["r2"]) / aux["df_resid"]) if aux["r2"] < 1 else math.inf
        return {"computable": True, "test": "breusch_pagan_koenker_auxiliary_r2",
                "lm_statistic": lm, "lm_p_value": chi2_sf(lm, df1),
                "f_statistic": fvalue, "f_p_value": f_sf(fvalue, df1, aux["df_resid"]),
                "df1": df1, "df2": aux["df_resid"],
                "null": "error variance is unrelated to exog_het; see statsmodels LM/F semantics"}
    except (ValueError, ArithmeticError) as exc:
        return {"computable": False, "reason": str(exc)}


def ramsey_reset(y, x, power=3):
    try:
        power = int(power)
        if power < 2 or power > 5:
            return {"computable": False, "reason": "RESET power must be an integer from 2 to 5"}
        reduced = ols(y, x, add_intercept=True)
        augmented = [row + [fit ** p for p in range(2, power + 1)]
                     for row, fit in zip(reduced["design"], reduced["fitted"])]
        full = ols(y, augmented, add_intercept=False)
        q = power - 1
        numerator = (reduced["sse"] - full["sse"]) / q
        denominator = full["sse"] / full["df_resid"]
        if denominator <= 0:
            return {"computable": False, "reason": "augmented model has zero residual variance"}
        statistic = numerator / denominator
        return {"computable": True, "test": "ramsey_reset_f_fitted_powers",
                "statistic": statistic, "df1": q, "df2": full["df_resid"],
                "p_value": f_sf(statistic, q, full["df_resid"]),
                "powers": list(range(2, power + 1)),
                "null": "coefficients of added fitted-value powers are zero; rejection does not identify the correct model"}
    except (ValueError, ArithmeticError, TypeError) as exc:
        return {"computable": False, "reason": str(exc)}


def durbin_watson(residuals):
    xs = clean_numbers(residuals)
    denominator = sum(x * x for x in xs)
    if len(xs) < 3 or not denominator:
        return {"computable": False, "reason": "at least three residuals and positive SSE required"}
    return {"computable": True, "test": "durbin_watson",
            "statistic": sum((b - a) ** 2 for a, b in zip(xs, xs[1:])) / denominator,
            "interpretation_limit": "descriptive first-order serial-correlation screening; no p-value is computed here"}


def variance_inflation(x):
    if not isinstance(x, list) or not x or not isinstance(x[0], (list, tuple)):
        return {"computable": False, "reason": "full predictor matrix is required; intercept column is optional"}
    rows = [[number(v) for v in row] for row in x]
    if any(any(v is None for v in row) for row in rows) or len(x) < 3:
        return {"computable": False, "reason": "numeric predictor matrix with at least three rows is required"}
    # Remove a column that acts exactly like an intercept.
    predictors = list(range(len(rows[0])))
    constant = next((j for j in predictors if all(row[j] == rows[0][j] for row in rows)), None)
    if constant is not None:
        predictors.remove(constant)
    if len(predictors) < 2:
        return {"computable": False, "reason": "VIF needs at least two nonconstant predictors"}
    out = []
    for j in predictors:
        others = [k for k in predictors if k != j]
        try:
            aux = ols([row[j] for row in rows], [[row[k] for k in others] for row in rows], add_intercept=True)
            r2 = aux["r2"]
            vif = math.inf if r2 is not None and 1 - r2 <= 1e-14 else 1 / (1 - r2) if r2 is not None else None
        except ValueError as exc:
            r2, vif = None, None
            out.append({"column": j, "computable": False, "reason": str(exc)})
            continue
        out.append({"column": j, "r2_aux": r2, "vif": vif, "computable": vif is not None,
                    "caution": "VIF is predictor-specific; any threshold is a heuristic, not proof that the model is invalid"})
    return {"computable": all(v.get("computable") for v in out), "tests": out}


def adjust_pvalues(pvalues, method="bh"):
    ps = [number(v) for v in pvalues]
    if any(p is None or not 0 <= p <= 1 for p in ps):
        return {"computable": False, "reason": "all p values must be numeric in [0,1]"}
    m = len(ps)
    if not m:
        return {"computable": False, "reason": "no p values supplied"}
    method = method.lower().replace("benjamini_hochberg", "bh").replace("benjamini_yekutieli", "by")
    order = sorted(range(m), key=lambda i: (ps[i], i))
    adjusted = [None] * m
    if method == "bonferroni":
        adjusted = [min(1.0, p * m) for p in ps]
    elif method == "holm":
        running = 0.0
        for rank, idx in enumerate(order):
            running = max(running, (m - rank) * ps[idx])
            adjusted[idx] = min(1.0, running)
    elif method in {"bh", "by"}:
        harmonic = sum(1 / k for k in range(1, m + 1)) if method == "by" else 1.0
        following = 1.0
        for rank in range(m, 0, -1):
            idx = order[rank - 1]
            following = min(following, ps[idx] * m * harmonic / rank)
            adjusted[idx] = min(1.0, following)
    else:
        return {"computable": False, "reason": "supported methods: bonferroni, holm, bh, by"}
    return {"computable": True, "method": method, "family_size": m,
            "raw": ps, "adjusted": adjusted,
            "dependence_note": "BH assumes independence or positive regression dependence; BY is more conservative under general dependence"}


def normal_power(effect_size=None, nobs1=None, alpha=0.05, power=None, ratio=1.0,
                 alternative="two-sided", solve="power"):
    """Independent two-group NormalIndPower approximation, statsmodels semantics.

    effect_size is Cohen's standardized mean difference; ratio=nobs2/nobs1.
    Solve exactly one of power/effect_size/nobs1/ratio; returns continuous nobs1
    and rounded recruitment counts when applicable.  This is a normal
    approximation, not an exact noncentral-t power computation.
    """
    if alternative not in {"two-sided", "greater", "smaller"}:
        return {"computable": False, "reason": "invalid alternative"}
    alpha = number(alpha)
    if alpha is None or not 0 < alpha < 1:
        return {"computable": False, "reason": "alpha must be in (0,1)"}
    if solve not in {"power", "effect_size", "nobs1", "ratio"}:
        return {"computable": False, "reason": "solve must be power, effect_size, nobs1 or ratio"}
    z = ND.inv_cdf(1 - alpha / 2) if alternative == "two-sided" else ND.inv_cdf(1 - alpha)

    def achieved(d, n1, ratio_):
        d, n1, ratio_ = number(d), number(n1), number(ratio_)
        if d is None or n1 is None or ratio_ is None or n1 <= 0 or ratio_ <= 0:
            return None
        noncentral = abs(d) * math.sqrt(n1 * ratio_ / (1 + ratio_))
        if alternative == "two-sided":
            return ND.cdf(noncentral - z) + ND.cdf(-noncentral - z)
        return ND.cdf(noncentral - z)

    if solve == "power":
        result = achieved(effect_size, nobs1, ratio)
        return ({"computable": True, "solve": solve, "power": result, "method": "normal_two_sample_independent",
                 "effect_size": number(effect_size), "nobs1": number(nobs1), "ratio": number(ratio),
                 "alpha": alpha, "alternative": alternative,
                 "approximation_limit": "normal approximation, not noncentral-t"} if result is not None
                else {"computable": False, "reason": "numeric effect_size, nobs1 and ratio are required"})
    target = number(power)
    if target is None or not 0 < target < 1:
        return {"computable": False, "reason": "target power must be in (0,1)"}
    if target <= alpha:
        return {"computable": False, "reason": "target power must exceed the null rejection level alpha"}
    if solve == "effect_size":
        n1 = number(nobs1)
        ratio = number(ratio)
        if n1 is None or ratio is None or n1 <= 0 or ratio <= 0:
            return {"computable": False, "reason": "numeric nobs1 and ratio are required"}
        lo, hi = 0.0, 1.0
        while achieved(hi, n1, ratio) < target and hi < 1e5:
            hi *= 2
        for _ in range(100):
            mid = (lo + hi) / 2
            if achieved(mid, n1, ratio) < target:
                lo = mid
            else:
                hi = mid
        answer = (lo + hi) / 2
        return {"computable": True, "solve": solve, "effect_size": answer, "nobs1": n1,
                "ratio": ratio, "power": achieved(answer, n1, ratio), "alpha": alpha,
                "alternative": alternative, "method": "normal_two_sample_independent",
                "approximation_limit": "normal approximation, not noncentral-t"}
    if solve == "nobs1":
        d, ratio = number(effect_size), number(ratio)
        if not d or ratio is None or ratio <= 0:
            return {"computable": False, "reason": "nonzero effect_size and positive ratio are required"}
        lo, hi = 0.0, 1.0
        while achieved(d, hi, ratio) < target and hi < 1e9:
            hi *= 2
        for _ in range(100):
            mid = (lo + hi) / 2
            if achieved(d, mid, ratio) < target:
                lo = mid
            else:
                hi = mid
        answer = (lo + hi) / 2
        n1ceil = math.ceil(answer)
        return {"computable": True, "solve": solve, "effect_size": d, "ratio": ratio,
                "nobs1_continuous": answer, "nobs1": answer, "nobs1_rounded_up": n1ceil,
                "nobs2_from_ratio": answer * ratio, "nobs2_rounded_up": math.ceil(answer * ratio),
                "total_n_rounded_up": n1ceil + math.ceil(answer * ratio),
                "power_rounded_allocation": achieved(d, n1ceil, math.ceil(answer * ratio) / n1ceil),
                "power": achieved(d, answer, ratio), "alpha": alpha, "alternative": alternative,
                "method": "normal_two_sample_independent", "approximation_limit": "normal approximation, not noncentral-t"}
    n1, d = number(nobs1), number(effect_size)
    if n1 is None or not d or n1 <= 0:
        return {"computable": False, "reason": "numeric nobs1 and nonzero effect_size are required to solve ratio"}
    lo, hi = 1e-12, 1.0
    increasing = achieved(d, n1, 2.0) >= achieved(d, n1, 0.5)
    for _ in range(120):
        mid = (lo + hi) / 2
        if (achieved(d, n1, mid) < target) == increasing:
            lo = mid
        else:
            hi = mid
    answer = (lo + hi) / 2
    return {"computable": True, "solve": solve, "effect_size": d, "nobs1": n1, "ratio": answer,
            "power": achieved(d, n1, answer), "alpha": alpha, "alternative": alternative,
            "method": "normal_two_sample_independent", "approximation_limit": "normal approximation, not noncentral-t"}


def pearson(x, y, confidence=0.95):
    xs, ys = clean_numbers(x), clean_numbers(y)
    if len(xs) != len(ys) or len(xs) != len(x) or len(xs) < 3 or len(y) != len(ys):
        return {"computable": False, "reason": "paired numeric x/y of equal length n>=3 required"}
    mx, my = sum(xs) / len(xs), sum(ys) / len(ys)
    sxx = sum((v - mx) ** 2 for v in xs)
    syy = sum((v - my) ** 2 for v in ys)
    if sxx <= 0 or syy <= 0:
        return {"computable": False, "reason": "zero variance makes Pearson r undefined"}
    r = sum((a - mx) * (b - my) for a, b in zip(xs, ys)) / math.sqrt(sxx * syy)
    r = min(1.0, max(-1.0, r))
    df = len(xs) - 2
    statistic = math.copysign(math.inf, r) if abs(r) == 1 else r * math.sqrt(df / (1 - r * r))
    ci = None
    if len(xs) >= 4 and abs(r) < 1:
        zcrit = ND.inv_cdf(1 - (1 - confidence) / 2)
        z = math.atanh(r)
        radius = zcrit / math.sqrt(len(xs) - 3)
        ci = [math.tanh(z - radius), math.tanh(z + radius)]
    return {"computable": True, "test": "pearson_linear_correlation", "n": len(xs),
            "r": r, "statistic": statistic, "df": df, "p_value": t_sf_two(statistic, df) if math.isfinite(statistic) else 0.0,
            "r_fisher_z_ci": ci, "confidence": confidence,
            "interpretation_limit": "linear association only; neither causation nor general independence follows"}
