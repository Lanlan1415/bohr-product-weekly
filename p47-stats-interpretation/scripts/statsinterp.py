"""Audit declared statistical claims against the numbers the table itself computes.

The failure this module exists for is not a wrong t-test — it is a sentence that
disagrees with the numbers beside it: the group that is actually lower is written
up as "higher", a p of 0.30 is written up as "significant", and an interpretation
quotes a number that appears nowhere in the data. Those errors survive any amount
of correct arithmetic, because nobody re-reads the sentence against the table.

So every claim in ``spec.stats`` — ``{metric, test, value, p, interpretation}`` —
is checked three ways against group statistics recomputed from the rows:

  direction      mean_b > mean_a must agree with the claimed direction
  significance   the p value must agree with the significance language used
  citation       the interpretation must cite a number the table computes

A claim whose metric column does not exist, or whose named groups are absent from
the data, cannot be checked at all — that is reported as a finding, not skipped
silently, because an unverifiable claim reads as verified.
"""

from __future__ import annotations

import re

import units as U

# Direction lexicon. The interpretation describes group_b relative to group_a.
HIGHER_WORDS = (
    "higher", "increase", "increased", "greater", "larger", "above", "elevated",
    "高于", "增加", "升高", "大于", "更高", "提升", "提高", "增多", "上升",
)
LOWER_WORDS = (
    "lower", "decrease", "decreased", "smaller", "reduced", "below", "less",
    "低于", "降低", "减小", "小于", "更低", "减少", "下降",
)
DIRECTION_FIELD = {
    "higher": "higher", "increase": "higher", "increased": "higher",
    "greater": "higher", "up": "higher",
    "lower": "lower", "decrease": "lower", "decreased": "lower",
    "smaller": "lower", "down": "lower",
}

# Significance lexicon. Negation is tested first: "不显著" contains "显著".
NEG_SIG_WORDS = (
    "不显著", "无显著", "未达显著", "无统计学", "没有显著", "未见显著",
    "not significant", "not statistically", "no significant", "n.s.",
)
SIG_WORDS = ("显著", "significant")
SIGNIFICANCE_ALPHA = 0.05

NUM_RE = re.compile(r"-?\d+\.?\d*")


def column_values(rows: list[dict], column: str) -> list[float]:
    """Numeric values of one column; not-reported and unparsed cells are skipped."""
    out: list[float] = []
    for r in rows:
        if not isinstance(r, dict):
            continue
        m = U.parse_measurement(str(r.get(column, "")).strip())
        if m["kind"] in ("single", "plus_minus"):
            out.append(float(m["value"]))
        elif m["kind"] == "range":
            out.append((float(m["low"]) + float(m["high"])) / 2.0)
    return out


def _mean(vals: list[float]):
    return sum(vals) / len(vals) if vals else None


def parse_p(p) -> dict:
    """Parse a claimed p value into {"p": float|None, "significant": bool|None}.

    A number is taken literally; a string may carry a comparison ("<0.05",
    "p=0.31", "p > 0.05") or declare non-significance ("n.s.").
    """
    if p is None:
        return {"p": None, "significant": None}
    if isinstance(p, (int, float)):
        return {"p": float(p), "significant": float(p) < SIGNIFICANCE_ALPHA}
    s = str(p).strip().lower()
    if s in ("ns", "n.s.", "n.s", "not significant", "不显著"):
        return {"p": None, "significant": False}
    m = re.search(r"(<=|>=|<|>)\s*([01]?\.?\d+)", s)
    if m:
        val = float(m.group(2))
        op = m.group(1)
        if op == "<":
            return {"p": val, "significant": True}
        if op == "<=":
            return {"p": val, "significant": val < SIGNIFICANCE_ALPHA}
        # ">0.05" style claims assert non-significance regardless of the number
        return {"p": val, "significant": False}
    m = re.search(r"([01]?\.?\d+)", s)
    if m:
        val = float(m.group(1))
        return {"p": val, "significant": val < SIGNIFICANCE_ALPHA}
    return {"p": None, "significant": None}


def _direction_of_text(text: str) -> str | None:
    has_higher = any(w in text for w in HIGHER_WORDS)
    has_lower = any(w in text for w in LOWER_WORDS)
    if has_higher and has_lower:
        return None  # ambiguous wording; a lexical check cannot judge it
    if has_higher:
        return "higher"
    if has_lower:
        return "lower"
    return None


def _matches(num: float, computed: float) -> bool:
    tol = max(0.006, abs(computed) * 0.002)
    return abs(num - computed) <= tol


# --- distribution math (pure stdlib; validated against table anchors) --------

def _betacf(a: float, b: float, x: float) -> float:
    """Continued fraction for the regularised incomplete beta function."""
    MAXIT, EPS, FPMIN = 300, 3e-16, 1e-300
    qab, qap, qam = a + b, a + 1.0, a - 1.0
    c, d = 1.0, 1.0 - qab * x / qap
    if abs(d) < FPMIN:
        d = FPMIN
    d = 1.0 / d
    h = d
    for m in range(1, MAXIT + 1):
        m2 = 2 * m
        aa = m * (b - m) * x / ((qam + m2) * (a + m2))
        d = 1.0 + aa * d
        if abs(d) < FPMIN:
            d = FPMIN
        c = 1.0 + aa / c
        if abs(c) < FPMIN:
            c = FPMIN
        d = 1.0 / d
        h *= d * c
        aa = -(a + m) * (qab + m) * x / ((a + m2) * (qap + m2))
        d = 1.0 + aa * d
        if abs(d) < FPMIN:
            d = FPMIN
        c = 1.0 + aa / c
        if abs(c) < FPMIN:
            c = FPMIN
        d = 1.0 / d
        de = d * c
        h *= de
        if abs(de - 1.0) < EPS:
            break
    return h


def betainc(a: float, b: float, x: float) -> float:
    """Regularised incomplete beta I_x(a, b) via the continued fraction."""
    import math
    if x <= 0.0:
        return 0.0
    if x >= 1.0:
        return 1.0
    ln_bt = (math.lgamma(a + b) - math.lgamma(a) - math.lgamma(b)
             + a * math.log(x) + b * math.log(1.0 - x))
    bt = math.exp(ln_bt)
    if x < (a + 1.0) / (a + b + 2.0):
        return bt * _betacf(a, b, x) / a
    return 1.0 - bt * _betacf(b, a, 1.0 - x) / b


def t_two_sided_p(t: float, df: float):
    """Two-sided p value of Student t with df degrees of freedom; None if degenerate."""
    import math
    if df is None or df <= 0 or not math.isfinite(t):
        return None
    return betainc(df / 2.0, 0.5, df / (df + t * t))


def f_sf(f: float, d1: float, d2: float):
    """Upper-tail p value of the F distribution; None if degenerate."""
    if d1 is None or d2 is None or d1 <= 0 or d2 <= 0 or not (f == f):
        return None
    if f <= 0:
        return 1.0
    return betainc(d2 / 2.0, d1 / 2.0, d2 / (d2 + d1 * f))


def t_two_sided_critical(p: float, df: float):
    """Two-sided t critical value by bisection on t_two_sided_p."""
    if df is None or df <= 0 or not 0.0 < p < 1.0:
        return None
    lo, hi = 0.0, 1e5
    for _ in range(120):
        mid = (lo + hi) / 2.0
        if t_two_sided_p(mid, df) > p:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2.0


# --- descriptive and inferential statistics ----------------------------------

def _variance(vals: list[float]) -> float | None:
    """Sample variance (ddof=1); None for fewer than two values."""
    n = len(vals)
    if n < 2:
        return None
    m = sum(vals) / n
    return sum((x - m) ** 2 for x in vals) / (n - 1)


def _moments(vals: list[float]) -> dict:
    """Skewness and excess kurtosis (population form, g1 / g2)."""
    n = len(vals)
    m = sum(vals) / n
    m2 = sum((x - m) ** 2 for x in vals) / n
    m3 = sum((x - m) ** 3 for x in vals) / n
    m4 = sum((x - m) ** 4 for x in vals) / n
    skew = (m3 / m2 ** 1.5) if m2 > 0 and n >= 3 else 0.0
    kurt = (m4 / m2 ** 2 - 3.0) if m2 > 0 and n >= 4 else 0.0
    return {"skew": skew, "excess_kurtosis": kurt}


def welch_test(va: list[float], vb: list[float]) -> dict | None:
    """Welch two-sample t: unequal variances and unequal n are the safe default.

    Returns {t, df, p} or None when either group carries fewer than two values
    or one variance is zero — the caller reports those states as findings instead
    of letting a degenerate statistic through.
    """
    import math
    n1, n2 = len(va), len(vb)
    v1, v2 = _variance(va), _variance(vb)
    if n1 < 2 or n2 < 2 or v1 is None or v2 is None:
        return None
    if v1 <= 0 or v2 <= 0:
        return None
    m1, m2 = sum(va) / n1, sum(vb) / n2
    se2 = v1 / n1 + v2 / n2
    if se2 <= 0:
        return None
    t = (m2 - m1) / math.sqrt(se2)
    df = se2 ** 2 / ((v1 / n1) ** 2 / (n1 - 1) + (v2 / n2) ** 2 / (n2 - 1))
    p = t_two_sided_p(t, df)
    return {"t": t, "df": df, "p": p}


def cohens_d(va: list[float], vb: list[float]) -> float | None:
    """Pooled-SD standardised mean difference (positive = b above a); None if degenerate."""
    import math
    n1, n2 = len(va), len(vb)
    v1, v2 = _variance(va), _variance(vb)
    if n1 < 2 or n2 < 2 or v1 is None or v2 is None:
        return None
    dof = n1 + n2 - 2
    if dof <= 0:
        return None
    pooled2 = ((n1 - 1) * v1 + (n2 - 1) * v2) / dof
    if pooled2 <= 0:
        return None
    m1, m2 = sum(va) / n1, sum(vb) / n2
    return (m2 - m1) / math.sqrt(pooled2)


def anova_oneway(groups: dict[str, list[float]]) -> dict | None:
    """One-way ANOVA over >=3 groups: F, p, eta squared. None when degenerate.

    Groups with a single value or zero variance contribute to the sums but make
    the within-group variance degenerate only when ALL groups are that way; a
    single degenerate group is a data problem the caller reports separately.
    """
    import math
    usable = {g: v for g, v in groups.items() if len(v) >= 1}
    if len(usable) < 3:
        return None
    all_vals = [x for v in usable.values() for x in v]
    n = len(all_vals)
    k = len(usable)
    if n - k < 1:
        return None
    grand = sum(all_vals) / n
    ssb = sum(len(v) * ((sum(v) / len(v)) - grand) ** 2 for v in usable.values())
    ssw = sum((x - sum(v) / len(v)) ** 2 for v in usable.values() for x in v)
    if ssw <= 0:
        return None
    f = (ssb / (k - 1)) / (ssw / (n - k))
    p = f_sf(f, k - 1, n - k)
    eta2 = ssb / (ssb + ssw) if (ssb + ssw) > 0 else None
    return {"F": f, "df1": k - 1, "df2": n - k, "p": p,
            "eta_squared": round(eta2, 4) if eta2 is not None else None,
            "k_groups": k, "n": n}


def describe_column(rows: list, column: str, semantic: str | None = None) -> dict:
    """Full descriptive record for one column: n, centre, spread, quantiles, shape.

    Missing and unparsed cells are counted per category and excluded from every
    statistic — never coerced to zero. The observed unit spellings are reported
    so the measurement scale is on the record, not assumed. A declared
    categorical/text/id column gets a level census instead of fake numerics.
    """
    semantic = str(semantic or "").strip().lower()
    if semantic in ("categorical", "text", "id"):
        levels: dict[str, int] = {}
        n_total = 0
        for r in rows:
            if not isinstance(r, dict):
                continue
            n_total += 1
            v = str(r.get(column, "") or "").strip()
            if v:
                levels[v] = levels.get(v, 0) + 1
        return {"column": column, "semantic": semantic or "categorical",
                "n_total": n_total, "levels": dict(sorted(levels.items())),
                "n_levels": len(levels)}

    vals: list[float] = []
    units: dict[str, int] = {}
    n_missing = 0
    n_unparsed = 0
    n_total = 0
    for r in rows:
        if not isinstance(r, dict):
            continue
        raw = r.get(column)
        if raw is None or str(raw).strip() == "":
            n_total += 1
            n_missing += 1
            continue
        n_total += 1
        m = U.parse_measurement(str(raw).strip())
        if m["kind"] == "not_reported":
            n_missing += 1
        elif m["kind"] in ("single", "plus_minus"):
            vals.append(float(m["value"]))
            if m.get("unit"):
                units[m["unit"]] = units.get(m["unit"], 0) + 1
        elif m["kind"] == "range":
            vals.append((float(m["low"]) + float(m["high"])) / 2.0)
            if m.get("unit"):
                units[m["unit"]] = units.get(m["unit"], 0) + 1
        else:
            n_unparsed += 1
    rec: dict = {"column": column, "n_total": n_total, "n": len(vals),
                 "n_missing": n_missing, "n_unparsed": n_unparsed,
                 "units_seen": sorted(units)}
    if vals:
        import math
        n = len(vals)
        mean = sum(vals) / n
        var = _variance(vals)
        s = sorted(vals)
        def q(p):
            idx = (n - 1) * p
            lo = int(math.floor(idx))
            hi = min(lo + 1, n - 1)
            frac = idx - lo
            return s[lo] * (1 - frac) + s[hi] * frac
        rec.update({
            "mean": round(mean, 4),
            "sd": round(var ** 0.5, 4) if var is not None else None,
            "min": s[0], "q1": round(q(0.25), 4), "median": round(q(0.5), 4),
            "q3": round(q(0.75), 4), "max": s[-1],
            "iqr": round(q(0.75) - q(0.25), 4),
            **{k: round(v, 4) for k, v in _moments(vals).items()},
        })
    return rec


def outlier_rows_iqr(rows: list, column: str) -> dict | None:
    """Tukey-fence outliers for one column; None when the column is too sparse.

    1.5 x IQR fences, computed on the parsed numeric values. Outliers are listed
    (row, value) and kept in the data — flagging, not deletion, stays the rule.
    """
    if not isinstance(rows, list):
        return None
    pairs: list[tuple[int, float]] = []
    for i, r in enumerate(rows):
        if not isinstance(r, dict):
            continue
        raw = r.get(column)
        if raw is None or str(raw).strip() == "":
            continue
        m = U.parse_measurement(str(raw).strip())
        if m["kind"] in ("single", "plus_minus"):
            pairs.append((i, float(m["value"])))
        elif m["kind"] == "range":
            pairs.append((i, (float(m["low"]) + float(m["high"])) / 2.0))
    if len(pairs) < 8:
        return None
    s = sorted(v for _, v in pairs)
    n = len(s)
    import math as _m

    def q(p):
        idx = (n - 1) * p
        lo = int(_m.floor(idx))
        hi = min(lo + 1, n - 1)
        frac = idx - lo
        return s[lo] * (1 - frac) + s[hi] * frac

    q1, q3 = q(0.25), q(0.75)
    iqr = q3 - q1
    if iqr <= 0:
        return None
    lo_fence, hi_fence = q1 - 1.5 * iqr, q3 + 1.5 * iqr
    outside = [{"row": i, "value": v}
               for i, v in pairs if v < lo_fence or v > hi_fence]
    return {"column": column, "q1": round(q1, 4), "q3": round(q3, 4),
            "lower_fence": round(lo_fence, 4), "upper_fence": round(hi_fence, 4),
            "outliers": outside}


def recommend_charts(rows: list, spec: dict) -> list[dict]:
    """Deterministic chart recommendation per analysis shape (rubric: 图表选择).

    Group comparison with 2-8 groups and a numeric metric -> box plot with the
    group overlay; a lone numeric column with enough rows -> histogram; few
    points -> mean with CI bars; two numeric columns -> scatter.
    """
    out: list[dict] = []
    cols = [c for c in (spec.get("columns") or []) if isinstance(c, dict) and c.get("name")]
    group_col = str(spec.get("group_col") or "group")
    group_values = sorted({str(r.get(group_col, "")).strip() for r in rows
                           if isinstance(r, dict) and str(r.get(group_col, "")).strip()})
    numeric_cols = [c["name"] for c in cols
                    if str(c.get("semantic") or "numeric").lower() == "numeric"]
    for name in numeric_cols:
        vals = [str(r.get(name, "")).strip() for r in rows
                if isinstance(r, dict) and str(r.get(name, "")).strip()]
        parsed = sum(1 for v in vals
                     if U.parse_measurement(v)["kind"] in ("single", "plus_minus", "range"))
        if 2 <= len(group_values) <= 8:
            out.append({"column": name, "chart": "box_plot",
                        "why": "group comparison over " + str(len(group_values))
                               + " groups; show the spread, not just the mean"})
        elif parsed >= 20:
            out.append({"column": name, "chart": "histogram",
                        "why": "single numeric column with " + str(parsed)
                               + " usable values; distribution shape first"})
        elif parsed >= 2:
            out.append({"column": name, "chart": "mean_with_ci",
                        "why": "few usable points; a mean with an interval, never a bare bar"})
    cat_cols = [c["name"] for c in cols
                if str(c.get("semantic") or "").lower() == "categorical"]
    for name in cat_cols:
        if name == group_col:
            continue
        out.append({"column": name, "chart": "bar_counts",
                    "why": "categorical column; counts per level"})
    if len(numeric_cols) >= 2:
        out.append({"columns": numeric_cols[:2], "chart": "scatter",
                    "why": "two numeric columns; association before any correlation claim"})
    return out


def run_manifest(rows: list, spec: dict) -> dict:
    """The reproducibility block: engine, interpreter, input fingerprint, sizes.

    No timestamps — the same input must produce a byte-identical manifest, and
    the platform records the runtime independently.
    """
    import hashlib
    import json
    import sys
    payload = json.dumps(rows, sort_keys=True, ensure_ascii=False).encode("utf-8")
    return {"engine": "stats-interp/v2", "python": sys.version.split()[0],
            "stdlib_only": True, "n_rows": len(rows),
            "rows_sha256_16": hashlib.sha256(payload).hexdigest()[:16]}


def audit_stats(rows: list[dict], spec: dict) -> tuple[list[dict], list[dict]]:
    """Audit every declared claim; returns (findings, computed claim records)."""
    findings: list[dict] = []
    computed: list[dict] = []

    def add(rule, severity, message, **extra):
        findings.append({"rule": rule, "severity": severity, "message": message, **extra})

    columns = {str(k) for r in rows if isinstance(r, dict) for k in r}
    for c in spec.get("columns") or []:
        if isinstance(c, dict) and c.get("name"):
            columns.add(str(c["name"]))

    claims = spec.get("stats")
    if claims is None:
        return findings, computed
    if not isinstance(claims, list):
        add("stats.claim_malformed", "medium",
            "spec.stats is not a list, so no claim could be audited")
        return findings, computed

    for i, claim in enumerate(claims):
        if not isinstance(claim, dict):
            add("stats.claim_malformed", "medium",
                "a statistical claim is not an object; it was skipped and named",
                claim_index=i)
            continue
        metric = claim.get("metric")
        text = str(claim.get("interpretation") or "")
        if not metric or str(metric) not in columns:
            add("stats.metric_unknown", "high",
                "the claim names a metric that is not a column of the table, so its "
                "numbers cannot be traced to the data",
                claim_index=i, metric=metric, available=sorted(columns))
            continue
        metric = str(metric)
        if not text.strip():
            add("stats.claim_malformed", "medium",
                "the claim carries no interpretation text, so there is nothing to audit",
                claim_index=i, metric=metric)
            continue

        pp = parse_p(claim.get("p"))
        if claim.get("p") is not None and pp["p"] is None and pp["significant"] is None:
            add("stats.claim_malformed", "medium",
                "the claimed p could not be parsed from the value supplied, so the "
                "significance language check cannot run against it",
                claim_index=i, metric=metric, p_supplied=str(claim.get("p"))[:60])
        rec: dict = {"claim_index": i, "metric": metric, "test": claim.get("test"),
                     "p": pp["p"], "claimed_significant": pp["significant"]}

        group_col = str(claim.get("group_col") or spec.get("group_col") or "group")
        group_a, group_b = claim.get("group_a"), claim.get("group_b")
        nums_computed: list[float] = []

        if group_a is not None and group_b is not None:
            groups_present = {str(r.get(group_col, "")).strip()
                              for r in rows if isinstance(r, dict)}
            rows_a = [r for r in rows if isinstance(r, dict)
                      and str(r.get(group_col, "")).strip() == str(group_a).strip()]
            rows_b = [r for r in rows if isinstance(r, dict)
                      and str(r.get(group_col, "")).strip() == str(group_b).strip()]
            va = column_values(rows_a, metric)
            vb = column_values(rows_b, metric)
            if not va or not vb or str(group_a) not in groups_present or str(group_b) not in groups_present:
                add("stats.group_unknown", "high",
                    "a claimed group is not present in the grouping column, so the "
                    "comparison cannot be computed from the data",
                    claim_index=i, group_col=group_col, group_a=group_a, group_b=group_b,
                    groups_present=sorted(groups_present))
                continue

            # missing ratio per claimed group: a group that is mostly gaps cannot
            # carry the comparison the claim rests on
            for gname, grows, usable in ((group_a, rows_a, len(va)),
                                         (group_b, rows_b, len(vb))):
                n_total = len(grows)
                if n_total and (n_total - usable) / n_total > 0.5:
                    add("stats.missing_ratio_high", "medium",
                        "more than half of the claimed group's values are missing or "
                        "unusable; the comparison rests on the remaining minority",
                        claim_index=i, group=str(gname), group_col=group_col,
                        n_total=n_total, usable=usable)

            mean_a, mean_b = _mean(va), _mean(vb)
            diff = mean_b - mean_a
            rec.update({"group_col": group_col, "group_a": group_a, "group_b": group_b,
                        "n_a": len(va), "n_b": len(vb),
                        "mean_a": round(mean_a, 4), "mean_b": round(mean_b, 4),
                        "diff": round(diff, 4)})
            nums_computed = [mean_a, mean_b, diff]

            # shape advisories: skew/kurtosis in a small sample, before any test
            for gname, vals in ((group_a, va), (group_b, vb)):
                mo = _moments(vals)
                if (len(vals) >= 5 and abs(mo["skew"]) > 1.0) or \
                        (len(vals) >= 8 and abs(mo["excess_kurtosis"]) > 1.0):
                    add("stats.assumption_normality", "medium",
                        "strong skew/kurtosis indicators in a small sample; prefer a "
                        "non-parametric test or verify the distribution before reading "
                        "a parametric p value",
                        claim_index=i, group=str(gname),
                        n=len(vals), skew=round(mo["skew"], 4),
                        excess_kurtosis=round(mo["excess_kurtosis"], 4))

            # the inferential layer: Welch t (unequal variances are the safe
            # default), effect size, and the CI of the mean difference
            wt = welch_test(va, vb)
            if wt is None:
                if len(va) < 2 or len(vb) < 2:
                    add("stats.sample_too_small", "high",
                        "a claimed group carries fewer than two usable values; no "
                        "variance, no test, no significance claim from this data",
                        claim_index=i, n_a=len(va), n_b=len(vb))
                else:
                    add("stats.zero_variance", "high",
                        "a claimed group has zero variance; the t statistic is undefined "
                        "and the comparison cannot be audited",
                        claim_index=i, group_a=str(group_a), group_b=str(group_b))
            else:
                import math as _m
                rec.update({"t_stat": round(wt["t"], 4), "df": round(wt["df"], 2),
                            "p_computed": (round(wt["p"], 6)
                                           if wt["p"] is not None else None)})
                d = cohens_d(va, vb)
                if d is not None:
                    rec["cohen_d"] = round(d, 4)
                    corr = 1 - 3 / (4 * (len(va) + len(vb)) - 9)
                    rec["hedges_g"] = round(d * corr, 4)
                crit = t_two_sided_critical(0.05, wt["df"])
                if crit is not None:
                    v1, v2 = _variance(va), _variance(vb)
                    se = _m.sqrt(v1 / len(va) + v2 / len(vb))
                    rec["ci95_low"] = round(diff - crit * se, 4)
                    rec["ci95_high"] = round(diff + crit * se, 4)
                # claimed p vs the p the table computes: a significance verdict the
                # data does not support is exactly the p=0.04 problem
                if (pp["significant"] is not None and wt["p"] is not None
                        and (wt["p"] < SIGNIFICANCE_ALPHA) != pp["significant"]):
                    add("stats.p_mismatch", "medium",
                        "the claimed p implies a significance verdict the table's own "
                        "Welch test does not support (or vice versa); the claimed p may "
                        "come from another test — reconcile before shipping",
                        claim_index=i, p_claimed=pp["p"],
                        p_computed=round(wt["p"], 6))

            # three-plus groups in the data while the claim compares two: say
            # whether the others were excluded on purpose
            if len(groups_present) >= 3:
                rec["anova"] = None
                gvals = {}
                for gname in sorted(groups_present):
                    gvals[gname] = column_values([r for r in rows if isinstance(r, dict)
                                                  and str(r.get(group_col, "")).strip() == gname],
                                                 metric)
                av = anova_oneway(gvals)
                if av is not None:
                    rec["anova"] = {k: (round(v, 6) if isinstance(v, float) else v)
                                    for k, v in av.items()}
                if claim.get("correction") is None and claim.get("excluded_groups") is None:
                    add("stats.groups_omitted", "medium",
                        "the grouping column carries "
                        + str(len(groups_present))
                        + " groups but the claim compares two; declare excluded_groups "
                          "or the correction used before the comparison reads as global",
                        claim_index=i, groups_present=sorted(groups_present))
        else:
            vals = column_values(rows, metric)
            mean_all = _mean(vals)
            if mean_all is None:
                add("stats.metric_unknown", "high",
                    "the metric column carries no numeric value, so the claim cannot "
                    "be computed from the data", claim_index=i, metric=metric)
                continue
            rec.update({"n": len(vals), "mean": round(mean_all, 4)})
            nums_computed = [mean_all]
        computed.append(rec)

        # (a) direction: claimed wording vs the recomputed group means
        expected = None
        if "mean_b" in rec:
            expected = ("higher" if rec["mean_b"] > rec["mean_a"]
                        else "lower" if rec["mean_b"] < rec["mean_a"] else "equal")
        claimed = _direction_of_text(text)
        dfield = DIRECTION_FIELD.get(str(claim.get("direction") or "").strip().lower())
        claimed_dirs = {d for d in (claimed, dfield) if d}
        if expected in ("higher", "lower") and claimed_dirs:
            wrong = {d for d in claimed_dirs if d != expected}
            if wrong:
                add("stats.direction_mismatch", "high",
                    "the claimed direction contradicts the recomputed group means",
                    claim_index=i, metric=metric,
                    claimed_direction=sorted(wrong), computed_direction=expected,
                    mean_a=rec.get("mean_a"), mean_b=rec.get("mean_b"))
        elif expected == "equal" and claimed_dirs:
            add("stats.direction_mismatch", "high",
                "the recomputed group means are equal, but the interpretation claims "
                "a direction", claim_index=i, metric=metric,
                claimed_direction=sorted(claimed_dirs), computed_direction="equal",
                mean_a=rec.get("mean_a"), mean_b=rec.get("mean_b"))

        # (b) significance language must match the claimed p value
        low = text.lower()
        negated = any(w in low for w in NEG_SIG_WORDS) or re.search(r"\bns\b", low) is not None
        affirmative = (any(w in low for w in SIG_WORDS) and not negated)
        if pp["significant"] is True and negated:
            add("stats.significance_mismatch", "high",
                "the p value is below 0.05 but the interpretation states non-significance",
                claim_index=i, metric=metric, p=pp["p"])
        elif pp["significant"] is False and affirmative:
            add("stats.significance_mismatch", "high",
                "the p value is not below 0.05 but the interpretation claims significance",
                claim_index=i, metric=metric, p=pp["p"])

        # (c) the interpretation must cite a number the table computes
        cited = [float(m.group(0)) for m in NUM_RE.finditer(text)]
        cited_ok = any(_matches(n, c) for n in cited for c in nums_computed)
        claimed_value = claim.get("value")
        if claimed_value is not None:
            m = NUM_RE.search(str(claimed_value))
            if m:
                cv = float(m.group(0))
                rec["claimed_value"] = cv
                if not any(_matches(cv, c) for c in nums_computed):
                    add("stats.number_not_in_table", "high",
                        "the claimed statistic disagrees with the recomputed value",
                        claim_index=i, metric=metric, claimed_value=cv,
                        computed=[round(c, 4) for c in nums_computed])
        if not cited or not cited_ok:
            add("stats.number_not_in_table", "high",
                "the interpretation cites none of the numbers the table computes; every "
                "reading of a result must be traceable to the computed value",
                claim_index=i, metric=metric,
                computed=[round(c, 4) for c in nums_computed], cited=cited[:10])

    # multiple comparisons: three or more pairwise claims with no declared
    # correction is how significance gets manufactured by repetition
    pair_claims = [c for c in claims if isinstance(c, dict)
                   and c.get("group_a") is not None and c.get("group_b") is not None]
    if len(pair_claims) >= 3 and not any(c.get("correction") for c in pair_claims):
        add("stats.multiple_comparison", "medium",
            str(len(pair_claims)) + " pairwise claims with no declared multiple-comparison "
            "correction; repeated tests inflate the false-positive rate — declare the "
            "correction (e.g. Bonferroni) on the claims",
            n_pair_claims=len(pair_claims))

    return findings, computed
