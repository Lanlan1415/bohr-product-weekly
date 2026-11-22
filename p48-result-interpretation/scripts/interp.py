"""Audit an experiment interpretation against the data it claims to interpret.

A plausible-sounding explanation is the hardest defect to catch, because nothing
crashes and nothing is missing. So this module pins every interpretation to the
table with mechanical checks, one rule id each:

  grounding    a cited value (or baseline) must exist in the data
               (observation.value_not_in_data, high)
  anomalies    every anomaly the rules flag must carry an explanation
               (anomaly.unexplained, medium)
  causality    an explanation asserting a cause must record that cause
               (anomaly.cause_asserted, medium)
  trend        a claimed direction must agree with the data's own first-to-last
               movement (trend.direction_mismatch, high); a direction claim the
               data cannot verify is named instead of guessed
               (trend.unverifiable, medium)
  review       review steps must be executable: a concrete action verb plus a
               concrete target (file, field, batch, device log) — "检查数据
               质量" is the named anti-pattern (review.not_executable, medium);
               a recorded cause without any review step has no exclusion
               process (review.missing_for_cause, medium)
  next         each follow-up experiment must name the cause candidate it
               addresses (next.unbound / next.dangling, medium) and the risk
               that would make it non-executable if unconfirmed
               (next.risk_missing, medium)

Anomalies come from two detectors that must agree with the challenge wording
"结合物理上下限与分布判定": the physical plausible range declared per column
(R05 in the cleaning pass) and a distribution diagnostic (far-out IQR fences,
3xIQR, applied only to numeric columns with at least six parsed values). A value
outside the declared range is a hard flag; a value far outside the distribution
of its own column is a soft one. Either way, the interpretation must say why the
point is kept, dropped, or capped — an anomaly without a stated reason is
`anomaly.unexplained`.

The cause check is deliberately narrow: it does not judge whether a cause is
*correct*, only whether a causal sentence is backed by a recorded cause field.
A mechanism guess with nothing recorded behind it is `anomaly.cause_asserted`.
"""

from __future__ import annotations

import re

import units as U

CAUSE_WORDS = (
    "由于", "因为", "导致", "归因于", "造成", "引起", "源于", "所致", "起因",
    "because", "due to", "caused by", "cause of", "attributed to",
    "attribute to", "led to", "results from",
)
NUM_RE = re.compile(r"-?\d+\.?\d*")
IQR_K = 3.0          # far-out fence, not the 1.5x "mild outlier" fence
IQR_MIN_N = 6        # quartiles are noise below this; the diagnostic skips

# --- trend direction vocabulary ---------------------------------------------
# CJK entries match as substrings; latin entries match at word boundaries
# (stems of >=6 chars match their inflections: increas -> increase/increased).
TREND_UP = ("上升", "增加", "增大", "提高", "升高", "增强", "攀升", "走强", "增多",
            "increas", "rise", "risen", "rising", "elevat", "grew", "growth")
TREND_DOWN = ("下降", "减少", "降低", "减小", "减弱", "回落", "走低", "缩减",
              "decreas", "decline", "drop", "reduc", "fell", "fall", "weaken")
TREND_FLAT = ("持平", "保持稳定", "保持不变", "基本不变", "无明显变化", "平台期",
              "趋平", "plateau", "stable", "unchanged", "constant")
TREND_DEADBAND = 0.02   # |first->last|/scale at or below this counts as flat
TREND_MIN_POINTS = 2    # a direction needs at least two parseable points

# --- review-step executability vocabulary -----------------------------------
# "检查" alone is deliberately absent: "检查数据质量" is the anti-pattern the
# topic names. A step needs an action verb AND a concrete target.
REVIEW_VERBS_CJK = ("回查", "核对", "复算", "重跑", "重测", "复测", "加做", "补做",
                    "比对", "调取", "抽查", "追溯", "重复测量", "重新测量")
REVIEW_VERBS_RE = (
    r"\bverify\b", r"\bverified\b", r"\brecompute\b", r"\bre-?run\b",
    r"\bre-?check\b", r"\bcompare\b", r"\brepeat\b", r"\bcross-?check\b",
    r"\bre-?measure\b", r"\btrace\b", r"\binspect\b",
)
REVIEW_TARGET_RE = re.compile(
    r"[A-Za-z0-9_\-\u4e00-\u9fff]+\.(csv|tsv|json|xlsx|xls|log|txt|md|pdf|h5|parquet|docx)"
    r"|字段|列名|列号|行号|批次|日志|设备|样本|通道|孔位|对照组|对照|平行|原始数据|原始表"
    r"|工作簿|记录表|数据文件|设备台账|原始记录"
    r"|均值|平均值|平均|标准差|方差|斜率|截距|拟合|残差|峰值|极差|中位数|不确定度"
    r"|检出限|回收率|计数|偏差"
    r"|\b(field|column|row|batch|log|sample|channel|well|replicate|control|"
    r"workbook|file|mean|average|std|slope|median|fit)\b", re.IGNORECASE)


def column_values(rows: list[dict], column: str) -> list[float]:
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


def table_values(rows: list[dict], column: str | None = None) -> list[float]:
    """Every numeric cell value in the table (or in one column)."""
    if column:
        return column_values(rows, column)
    out: list[float] = []
    for r in rows:
        if not isinstance(r, dict):
            continue
        for k in r:
            out.extend(column_values([r], k))
    return out


def _exists(cited: float, values: list[float]) -> bool:
    return any(abs(cited - v) <= max(1e-9, abs(v) * 0.002) for v in values)


def _percentile(sorted_vals: list[float], q: float) -> float:
    n = len(sorted_vals)
    if n == 1:
        return sorted_vals[0]
    pos = q * (n - 1)
    lo = int(pos)
    frac = pos - lo
    hi = min(lo + 1, n - 1)
    return sorted_vals[lo] * (1 - frac) + sorted_vals[hi] * frac


def distribution_anomalies(rows: list[dict], spec: dict) -> list[dict]:
    """Far-out IQR flags per numeric column (n >= 6), with row indices."""
    flags: list[dict] = []
    for col in spec.get("columns") or []:
        if not isinstance(col, dict) or not col.get("name"):
            continue
        if str(col.get("semantic") or "").strip().lower() in ("id", "text", "date", "categorical"):
            continue
        name = str(col["name"])
        vals = column_values(rows, name)
        if len(vals) < IQR_MIN_N:
            continue
        s = sorted(vals)
        q1, q3 = _percentile(s, 0.25), _percentile(s, 0.75)
        iqr = q3 - q1
        lo_fence, hi_fence = q1 - IQR_K * iqr, q3 + IQR_K * iqr
        for ri, r in enumerate(rows):
            if not isinstance(r, dict):
                continue
            got = column_values([r], name)
            for v in got:
                if v < lo_fence or v > hi_fence:
                    flags.append({"column": name, "row": ri, "value": v,
                                  "source": "iqr", "fence": [round(lo_fence, 4), round(hi_fence, 4)]})
    return flags


def range_anomalies(clean_result: dict) -> list[dict]:
    """Values the cleaning pass flagged against the declared plausible range."""
    out: list[dict] = []
    for c in clean_result.get("changes") or []:
        if c.get("rule") == "R05" and c.get("new") is not None:
            out.append({"column": c.get("column"), "row": c.get("row"),
                        "value": c.get("new"), "source": "plausible_range",
                        "original": c.get("original")})
    return out


def claims_cause(text: str) -> bool:
    low = str(text or "").lower()
    return any(w in low for w in CAUSE_WORDS)


# ---------------------------------------------------------------------------
# trend direction: claim extraction and mechanical recomputation
# ---------------------------------------------------------------------------

def _has_word(low_text: str, word: str) -> bool:
    """CJK vocabulary matches as substrings; latin at word boundaries."""
    if any("\u2e80" <= ch <= "\u9fff" for ch in word):
        return word in low_text
    if len(word) >= 6:
        return re.search(r"\b" + re.escape(word) + r"\w*", low_text) is not None
    return re.search(r"\b" + re.escape(word) + r"\b", low_text) is not None


def claimed_directions(text: str) -> list[str]:
    """Directions the wording claims, in check order up/down/flat."""
    low = str(text or "").lower()
    out = []
    for d, words in (("up", TREND_UP), ("down", TREND_DOWN), ("flat", TREND_FLAT)):
        if any(_has_word(low, w) for w in words):
            out.append(d)
    return out


DIRECTION_SYNONYMS = {
    "up": ("up", "increase", "increased", "rising", "上升", "增加", "增大", "提高"),
    "down": ("down", "decrease", "decreased", "decline", "下降", "减少", "降低"),
    "flat": ("flat", "stable", "plateau", "unchanged", "持平", "稳定", "不变"),
}


def _norm_direction(raw) -> str | None:
    t = str(raw or "").strip().lower()
    if not t:
        return None
    for d, words in DIRECTION_SYNONYMS.items():
        if t in words or any(_has_word(t, w) for w in words):
            return d
    return None


def compute_direction(rows: list[dict], metric_col: str, order_col: str,
                      deadband: float = TREND_DEADBAND) -> dict | None:
    """First-to-last mechanical direction of metric_col ordered by order_col.

    Deterministic and recomputable: parse both cells per row, keep rows where
    both parse, sort by the order value, and classify by relative change
    (last - first) / max|value| against the deadband (default 2 percent).
    Returns None when fewer than two rows can be judged.
    """
    pts: list[tuple[float, float]] = []
    for r in rows:
        if not isinstance(r, dict):
            continue
        om = U.parse_measurement(str(r.get(order_col, "")).strip())
        vm = U.parse_measurement(str(r.get(metric_col, "")).strip())
        if om["kind"] == "range":
            ox = (float(om["low"]) + float(om["high"])) / 2.0
        elif om["kind"] in ("single", "plus_minus"):
            ox = float(om["value"])
        else:
            continue
        if vm["kind"] == "range":
            vy = (float(vm["low"]) + float(vm["high"])) / 2.0
        elif vm["kind"] in ("single", "plus_minus"):
            vy = float(vm["value"])
        else:
            continue
        pts.append((ox, vy))
    if len(pts) < TREND_MIN_POINTS:
        return None
    pts.sort(key=lambda p: p[0])
    first, last = pts[0][1], pts[-1][1]
    scale = max((abs(v) for _, v in pts), default=0.0) or 1.0
    rel = (last - first) / scale
    direction = "flat" if abs(rel) <= deadband else ("up" if rel > 0 else "down")
    return {"direction": direction, "n_points": len(pts),
            "first": first, "last": last,
            "rel_change": round(rel, 4),
            "order_column": order_col, "metric": metric_col}


def _cited_number(cell) -> float | None:
    if cell is None:
        return None
    if isinstance(cell, (int, float)):
        return float(cell)
    m = NUM_RE.search(str(cell))
    return float(m.group(0)) if m else None


# ---------------------------------------------------------------------------
# review steps and next experiments
# ---------------------------------------------------------------------------

def _step_executable(text: str) -> tuple[bool, str]:
    """A review step is executable when it pairs an action verb with a target."""
    low = str(text or "").lower()
    has_verb = any(v in str(text) for v in REVIEW_VERBS_CJK) \
        or any(re.search(p, low) for p in REVIEW_VERBS_RE)
    has_target = REVIEW_TARGET_RE.search(str(text)) is not None
    if not has_verb:
        return False, "no executable action verb (检查/确认/注意 do not count)"
    if not has_target:
        return False, "no concrete target (file, field, batch, device log)"
    return True, ""


def _cause_factors(o: dict) -> list[str]:
    """Recorded cause candidates on one observation."""
    cause = o.get("cause")
    factors: list[str] = []
    if isinstance(cause, dict):
        f = cause.get("factor")
        if f and str(f).strip():
            factors.append(str(f).strip())
        cands = cause.get("candidates")
        if isinstance(cands, list):
            for c in cands:
                if isinstance(c, dict) and str(c.get("factor") or "").strip():
                    factors.append(str(c["factor"]).strip())
        for k, v in cause.items():
            if k not in ("factor", "candidates") and isinstance(v, str) and v.strip() \
                    and k in ("factor_candidate", "hypothesis"):
                factors.append(v.strip())
    elif isinstance(cause, str) and cause.strip():
        factors.append(cause.strip())
    return factors


def _binding_match(addresses: str, factor: str) -> bool:
    a = re.sub(r"[\s]+", "", str(addresses).lower())
    f = re.sub(r"[\s]+", "", str(factor).lower())
    return bool(a) and bool(f) and (a in f or f in a)


def audit_interpretation(cleaned_rows: list[dict], spec: dict,
                         clean_result: dict | None = None) -> tuple[list[dict], dict]:
    """Audit spec.observations against the data; returns (findings, summary)."""
    findings: list[dict] = []
    limits: list[str] = []
    n_explained = 0
    n_review_steps = 0
    n_review_executable = 0
    n_next_experiments = 0
    n_trend_claims = 0

    def add(rule, severity, message, **extra):
        findings.append({"rule": rule, "severity": severity, "message": message, **extra})

    if clean_result is None:
        import cleaning as C
        clean_result = C.clean(cleaned_rows, spec)
    flagged = range_anomalies(clean_result) + distribution_anomalies(cleaned_rows, spec)

    columns = spec.get("columns") or []
    col_names = {str(c.get("name")) for c in columns
                 if isinstance(c, dict) and c.get("name")}
    trend_cfg = spec.get("trend") if isinstance(spec.get("trend"), dict) else {}
    order_col = str(trend_cfg.get("order_column") or "").strip() or None
    deadband = trend_cfg.get("deadband")
    try:
        deadband = abs(float(deadband))
    except (TypeError, ValueError):
        deadband = TREND_DEADBAND
    spec_factors = []
    cc = spec.get("cause_candidates")
    if isinstance(cc, list):
        for c in cc:
            if isinstance(c, dict) and str(c.get("factor") or "").strip():
                spec_factors.append(str(c["factor"]).strip())
            elif isinstance(c, str) and c.strip():
                spec_factors.append(c.strip())

    observations = spec.get("observations")
    obs_list: list[dict] = []
    if observations is None:
        observations = []
    if not isinstance(observations, list):
        add("observation.malformed", "medium",
            "spec.observations is not a list, so no observation could be audited")
        observations = []
    for i, o in enumerate(observations):
        if not isinstance(o, dict):
            add("observation.malformed", "medium",
                "an observation entry is not an object; it was skipped and named",
                observation_index=i)
            continue
        obs_list.append((i, o))

    # grounding: cited values and baselines must exist in the data
    for i, o in obs_list:
        metric = o.get("metric")
        scope = None
        if metric:
            if str(metric) in col_names:
                scope = str(metric)
            else:
                limits.append(f"observation {i} declares metric '{metric}', which is not a "
                              f"column of the table; the value check searched every column")
        values = table_values(cleaned_rows, scope)
        for field in ("value", "baseline"):
            cited = _cited_number(o.get(field))
            if cited is None:
                continue
            if not _exists(cited, values):
                add("observation.value_not_in_data", "high",
                    "the interpretation cites a number that does not exist in the data, "
                    "so the claim has no traceable source",
                    observation_index=i, field=field, cited=cited,
                    searched_column=scope or "all columns")

    # anomalies: every flagged point must carry an explanation that cites it
    for a in flagged:
        covered = False
        for i, o in obs_list:
            cited = _cited_number(o.get("value"))
            if cited is None or not _exists(cited, [a["value"]]):
                continue
            if str(o.get("explanation") or "").strip():
                covered = True
                n_explained += 1
                break
        if not covered:
            add("anomaly.unexplained", "medium",
                "a value flagged as anomalous carries no explanation; state why it is "
                "kept, dropped, or capped",
                column=a.get("column"), row=a.get("row"), value=a.get("value"),
                flagged_by=a.get("source"))

    # causality: a causal sentence needs a recorded cause behind it
    for i, o in obs_list:
        text = str(o.get("explanation") or "")
        if not claims_cause(text):
            continue
        cause = o.get("cause")
        recorded = bool(cause) and (
            str(cause).strip() not in ("", "None")
            if not isinstance(cause, dict)
            else any(str(v).strip() for v in cause.values()))
        if not recorded:
            add("anomaly.cause_asserted", "medium",
                "the explanation asserts a cause but no cause is recorded with the "
                "observation; record the candidate cause and its supporting evidence, "
                "or downgrade the wording to a correlation",
                observation_index=i, observation=str(o.get("observation") or "")[:80])

    # trend: claimed direction must agree with the data's own movement
    for i, o in obs_list:
        claim_field = o.get("trend_claim")
        explicit = isinstance(claim_field, dict)
        text_claims = claimed_directions(str(o.get("observation") or ""))
        if explicit:
            direction = _norm_direction(claim_field.get("direction"))
            if direction is None:
                add("trend.unverifiable", "medium",
                    "trend_claim.direction is not one of the up/down/flat synonyms, so "
                    "the claim cannot be checked mechanically",
                    observation_index=i,
                    claim=str(claim_field.get("direction"))[:40])
                continue
            metric = str(claim_field.get("metric") or o.get("metric") or "").strip()
            n_trend_claims += 1
            if metric not in col_names:
                add("trend.unverifiable", "medium",
                    "the trend claim names no usable metric column; declare "
                    "trend_claim.metric (a real column) so the direction can be recomputed",
                    observation_index=i, metric=metric or None)
                continue
            computed = _trend_or_limit(add, o, metric, order_col, cleaned_rows,
                                       deadband, limits, i)
            if isinstance(computed, dict):
                _trend_compare(add, i, direction, computed)
        elif text_claims:
            if len(set(text_claims)) > 1:
                limits.append(f"observation {i} mixes opposite direction words "
                              f"({', '.join(sorted(set(text_claims)))}); the engine does "
                              f"not guess which one applies — split the claim or use the "
                              f"trend_claim field")
                continue
            n_trend_claims += 1
            metric = str(o.get("metric") or "").strip()
            if metric not in col_names:
                add("trend.unverifiable", "medium",
                    "the wording claims a trend direction but names no metric column; "
                    "declare metric (and trend.order_column) or degrade the sentence to "
                    "a reading restatement",
                    observation_index=i, claimed=text_claims[0])
                continue
            computed = _trend_or_limit(add, o, metric, order_col, cleaned_rows,
                                       deadband, limits, i)
            if isinstance(computed, dict):
                _trend_compare(add, i, text_claims[0], computed)

    # review: steps must be executable; a recorded cause needs them
    for i, o in obs_list:
        steps = o.get("review_steps")
        if steps is None:
            if _cause_factors(o):
                add("review.missing_for_cause", "medium",
                    "a cause candidate is recorded but no review steps accompany it: "
                    "the exclusion process cannot be executed by a second person",
                    observation_index=i)
            continue
        if not isinstance(steps, list):
            add("review.step_malformed", "medium",
                "review_steps is not a list; declare one string per executable action",
                observation_index=i)
            continue
        texts: list[str] = []
        for j, s in enumerate(steps):
            if isinstance(s, str):
                texts.append(s)
            elif isinstance(s, dict) and str(s.get("action") or "").strip():
                texts.append(str(s["action"]))
            else:
                add("review.step_malformed", "medium",
                    "a review step is neither a string nor an object with action",
                    observation_index=i, step_index=j)
        for j, s in enumerate(texts):
            n_review_steps += 1
            ok, why = _step_executable(s)
            if ok:
                n_review_executable += 1
            else:
                add("review.not_executable", "medium",
                    "a review step cannot be executed by a second person: " + why,
                    observation_index=i, step_index=j, step=str(s)[:80])

    # next experiments: each binds to a recorded cause and a stated risk
    for i, o in obs_list:
        nex = o.get("next_experiments")
        if nex is None:
            continue
        if not isinstance(nex, list):
            add("next.malformed", "medium",
                "next_experiments is not a list; declare one object per suggestion "
                "with change, addresses and risk",
                observation_index=i)
            continue
        factors = _cause_factors(o) + spec_factors
        for j, s in enumerate(nex):
            n_next_experiments += 1
            if not isinstance(s, dict) or not str(s.get("change") or "").strip():
                add("next.malformed", "medium",
                    "a suggestion is not an object with a non-empty change",
                    observation_index=i, suggestion_index=j)
                continue
            addresses = str(s.get("addresses") or "").strip()
            if not addresses:
                add("next.unbound", "medium",
                    "a suggestion states no cause candidate it addresses; every "
                    "follow-up experiment must name the factor it targets",
                    observation_index=i, suggestion_index=j)
            elif not any(_binding_match(addresses, f) for f in factors):
                add("next.dangling", "medium",
                    "a suggestion addresses a cause candidate that is not recorded "
                    "anywhere; record the candidate (cause or cause_candidates) or fix "
                    "the binding",
                    observation_index=i, suggestion_index=j, addresses=addresses[:60],
                    recorded_factors=[f[:40] for f in factors])
            risk = s.get("risk")
            risk_ok = bool(risk) and (
                str(risk).strip() not in ("", "None")
                if not isinstance(risk, dict) else any(str(v).strip() for v in risk.values()))
            if not risk_ok:
                add("next.risk_missing", "medium",
                    "a suggestion carries no risk or precondition: an unconfirmed "
                    "suggestion must not read as an executable fact",
                    observation_index=i, suggestion_index=j)

    summary = {
        "n_observations": len(obs_list),
        "n_flagged_anomalies": len(flagged),
        "n_explained_anomalies": n_explained,
        "n_trend_claims": n_trend_claims,
        "n_review_steps": n_review_steps,
        "n_review_executable": n_review_executable,
        "n_next_experiments": n_next_experiments,
        "flagged": [{"column": a.get("column"), "row": a.get("row"),
                     "value": a.get("value"), "source": a.get("source")}
                    for a in flagged[:50]],
        "limits": limits,
    }
    return findings, summary


def _trend_or_limit(add, o, metric, order_col, cleaned_rows, deadband, limits, i):
    """Compute the mechanical direction, or name the claim unverifiable.

    An unverifiable direction claim is a medium finding, not a silent limit: a
    conclusion the table cannot support must be fixed (declare the ordering
    column) or degraded to a reading restatement before it ships.
    """
    if not order_col:
        add("trend.unverifiable", "medium",
            "the wording claims a trend direction but spec.trend.order_column is not "
            "declared, so no direction can be recomputed; declare the ordering column "
            "(time, dose, cycle) or drop the trend wording",
            observation_index=i, metric=metric)
        return None
    computed = compute_direction(cleaned_rows, metric, order_col, deadband)
    if computed is None:
        add("trend.unverifiable", "medium",
            "the trend claim cannot be verified: fewer than two rows carry parseable "
            "values for the metric ordered by the declared column; add the data or "
            "degrade the sentence to a reading restatement",
            observation_index=i, metric=metric, order_column=order_col)
        return None
    return computed


def _trend_compare(add, i, claimed: str, computed: dict) -> None:
    if computed["direction"] == claimed:
        return
    add("trend.direction_mismatch", "high",
        "the claimed trend direction contradicts the data's own first-to-last "
        "movement; a conclusion the numbers contradict must not ship",
        observation_index=i, claimed=claimed,
        computed=computed["direction"], first=computed["first"],
        last=computed["last"], rel_change=computed["rel_change"],
        n_points=computed["n_points"])
