"""Deterministic bounded DoE + feasibility-first multi-objective optimization.

All scientific relationships are supplied by the case as observed_runs or explicit
response_models. This command never invents measurements or fits unreported data.
Model predictions remain recommendations for validation, not measured outcomes.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import itertools
import json
import math
import random
import re
from pathlib import Path

VERSION = "bounded-parameter-optimization/v1"
EPS = 1e-9
T975 = {1: 12.706, 2: 4.303, 3: 3.182, 4: 2.776, 5: 2.571,
        6: 2.447, 7: 2.365, 8: 2.306, 9: 2.262, 10: 2.228,
        15: 2.131, 20: 2.086, 25: 2.060, 30: 2.042}


def object_(x):
    return x if isinstance(x, dict) else {}


def rows(x):
    return [v for v in x if isinstance(v, dict)] if isinstance(x, list) else []


def num(x):
    if isinstance(x, bool):
        return None
    try:
        v = float(x)
        return v if math.isfinite(v) else None
    except (ValueError, TypeError, OverflowError):
        return None


def integer(x, fallback=None):
    n = num(x)
    return int(n) if n is not None and abs(n - round(n)) < EPS and n >= 0 else fallback


def rnd(x):
    return round(x, 10) if isinstance(x, float) else x


def mean(xs):
    return sum(xs) / len(xs) if xs else None


def sd(xs):
    return math.sqrt(sum((v - mean(xs)) ** 2 for v in xs) / (len(xs) - 1)) if len(xs) > 1 else None


def summary(xs):
    vals = sorted(v for v in map(num, xs if isinstance(xs, list) else [xs]) if v is not None)
    if not vals:
        return {"value": None, "n_independent": 0, "uncertainty": "not reported"}
    s = {"value": mean(vals), "n_independent": len(vals), "values": vals}
    if len(vals) > 1:
        s["sample_sd"] = sd(vals)
        s["standard_error"] = s["sample_sd"] / math.sqrt(len(vals))
        df = len(vals) - 1
        t = T975.get(df, T975[max(k for k in T975 if k <= df)] if df <= 30 else 2.0)
        s["mean_ci95"] = [s["value"] - t * s["standard_error"], s["value"] + t * s["standard_error"]]
        s["ci_method"] = "mean ± t(0.975, n-1) * sample_sd / sqrt(n)"
        if df > 30:
            s["ci_approximation"] = "t critical approximated as 2.0 for df>30"
    else:
        s["uncertainty"] = "no replicate standard deviation estimable from one value"
    return {k: rnd(v) if isinstance(v, float) else v for k, v in s.items()}


def domain(v):
    if not isinstance(v, dict) or not str(v.get("name", "")).strip():
        raise ValueError("every variable needs a nonempty name")
    name = str(v["name"])
    kind = str(v.get("kind", "continuous"))
    if not v.get("source"):
        raise ValueError(f"variable {name} lacks a domain source")
    if v.get("values") is not None:
        if not isinstance(v["values"], list) or not v["values"]:
            raise ValueError(f"variable {name} has no finite values")
        vals = v["values"]
        if kind != "categorical":
            vals = [num(x) for x in vals]
            if any(x is None for x in vals):
                raise ValueError(f"numeric variable {name} includes a nonnumeric level")
    elif kind == "categorical":
        raise ValueError(f"categorical variable {name} requires explicit values")
    else:
        lo, hi, step = num(v.get("lower")), num(v.get("upper")), num(v.get("step"))
        if lo is None or hi is None or step is None or hi < lo or step <= 0:
            raise ValueError(f"variable {name} requires lower <= upper and positive finite step")
        if abs(lo - hi) < EPS:
            vals = [lo]
        else:
            count = int(math.floor((hi - lo) / step + 1e-8))
            vals = [lo + i * step for i in range(count + 1)]
            if vals[-1] < hi - 1e-8:
                # The original domain endpoint must not be skipped just because
                # its grid spacing does not land exactly on the upper limit.
                if not v.get("allow_final_partial_step"):
                    raise ValueError(f"variable {name} upper bound is not on its step grid")
                vals.append(hi)
        if len(vals) > 10000:
            raise ValueError(f"finite domain of {name} is too large; provide a bounded grid")
    vals = list(dict.fromkeys((json.dumps(x, ensure_ascii=False, sort_keys=True), x) for x in vals))
    vals = [x[1] for x in vals]
    return {"name": name, "kind": kind, "unit": v.get("unit"), "source": v.get("source"),
            "locator": v.get("locator"), "levels": vals, "raw": v}


def models(spec):
    out = {}
    for run in rows(spec.get("observed_runs")):
        if not run.get("source"):
            raise ValueError("every observed run requires a raw-data source/locator")
    for name in ("cost_model", "time_model", "sample_model"):
        if object_(spec.get(name)).get("coefficients") and not spec[name].get("source"):
            raise ValueError(f"{name} needs a resource/price source and locator")
    for name, m in object_(spec.get("response_models")).items():
        if not isinstance(m, dict):
            continue
        if not m.get("source"):
            raise ValueError(f"response model {name} has no calibration/source record")
        model = object_(m.get("model", m))
        if str(m.get("kind", model.get("kind", "polynomial"))) != "polynomial":
            raise ValueError("only explicit polynomial model specifications are supported")
        out[name] = {"model": model, "source": m["source"], "locator": m.get("locator"),
                     "sd": num(m.get("sd")), "unit": m.get("unit")}
    return out


def polynomial(model, params):
    vals = {str(k): num(v) for k, v in object_(params).items()}
    result = num(model.get("intercept", 0))
    if result is None:
        return None
    for key, coef in object_(model.get("coefficients")).items():
        c, x = num(coef), vals.get(key)
        if c is None or x is None:
            return None
        result += c * x
    for key, coef in object_(model.get("quadratic")).items():
        c, x = num(coef), vals.get(key)
        if c is None or x is None:
            return None
        result += c * x * x
    for key, coef in object_(model.get("interactions")).items():
        c = num(coef)
        names = key.split(":")
        if c is None or len(names) != 2 or any(vals.get(k) is None for k in names):
            return None
        result += c * vals[names[0]] * vals[names[1]]
    return result


def match(a, b):
    if set(a) != set(b):
        return False
    for k in a:
        x, y = num(a[k]), num(b[k])
        if x is not None and y is not None:
            if abs(x - y) > max(EPS, abs(x) * 1e-8):
                return False
        elif a[k] != b[k]:
            return False
    return True


def responses(spec, given_models, params):
    out = {}
    matched = [r for r in rows(spec.get("observed_runs")) if match(params, object_(r.get("parameters")))]
    merged = []
    for r in matched:
        merged.append({"responses": object_(r.get("responses")), "source": r.get("source"),
                       "locator": r.get("locator")})
    for objective in rows(spec.get("objectives")):
        name = str(objective.get("name", ""))
        observed = []
        for record in merged:
            raw = record["responses"].get(name)
            if isinstance(raw, list):
                observed.extend(num(x) for x in raw)
            elif raw is not None:
                observed.append(num(raw))
        known = [v for v in observed if v is not None]
        if known:
            stats = summary(known)
            out[name] = {"kind": "observed", "statistics": stats, "value": stats["value"],
                         "source": [r["source"] for r in merged],
                         "limit": "aggregate of matched declared runs; independence claim must come from input"}
        elif name in ("total_cost", "total_time_hours", "total_samples") and object_(spec.get({
                "total_cost": "cost_model", "total_time_hours": "time_model",
                "total_samples": "sample_model"}[name])):
            model_key = {"total_cost": "cost_model", "total_time_hours": "time_model",
                         "total_samples": "sample_model"}[name]
            model_obj = object_(spec.get(model_key))
            reps = integer(object_(spec.get("study_design")).get("independent_replicates"), 1)
            per = polynomial(model_obj, params)
            value = per * reps if per is not None and reps is not None else None
            out[name] = {"kind": "deterministic_cost_model", "value": value,
                         "statistics": {"value": value, "n_independent": 0},
                         "source": model_obj.get("source"), "locator": model_obj.get("locator"),
                         "formula": f"per_point({per}) * independent_replicates({reps})",
                         "limit": "resource arithmetic prediction, not a completed experimental invoice"}
        elif name in given_models:
            reg = given_models[name]
            value = polynomial(reg["model"], params)
            out[name] = {"kind": "model_predicted", "value": value,
                         "statistics": {"value": value, "n_independent": 0},
                         "source": reg["source"], "locator": reg["locator"],
                         "model_sd": reg["sd"], "limit": "not an experimentally validated response"}
        else:
            out[name] = {"kind": "unknown", "value": None,
                         "statistics": {"value": None, "n_independent": 0},
                         "limit": "no observed response or validated model supplied"}
    for v in out.values():
        if isinstance(v["value"], float):
            v["value"] = rnd(v["value"])
    return out


def derived(spec, params, resp):
    cost_model = object_(spec.get("cost_model"))
    time_model = object_(spec.get("time_model"))
    sample_model = object_(spec.get("sample_model"))
    cost = polynomial(cost_model, params) if cost_model else None
    time = polynomial(time_model, params) if time_model else None
    samples = polynomial(sample_model, params) if sample_model else None
    for record in rows(spec.get("observed_runs")):
        if match(params, object_(record.get("parameters"))):
            c = object_(record.get("resources"))
            cost, time, samples = [num(c.get(k, default)) for k, default in
                                   (("cost", cost), ("time_hours", time), ("samples", samples))]
            break
    reps = integer(object_(spec.get("study_design")).get("independent_replicates"), 1)
    if reps is None or reps < 1:
        reps = None
    out = {}
    for k, v in (("total_cost", cost), ("total_time_hours", time), ("total_samples", samples)):
        declared = object_(spec.get("resources")) if k != "total_samples" else object_(spec.get("resources"))
        if v is not None and reps is not None:
            out[k] = rnd(v * reps if k != "total_samples" else v * reps)
            out[k + "_formula"] = f"per_evaluation({v}) * independent_replicates({reps})"
        else:
            out[k] = None
            out[k + "_formula"] = None
    out.update(object_(spec.get("metrics")))
    for objective in rows(spec.get("objectives")):
        if str(objective.get("name", "")) in resp:
            out["response." + str(objective["name"])] = resp[objective["name"]]["value"]
    return out


def metric(name, params, metrics, resp):
    if name.startswith("parameter."):
        return params.get(name.split(".", 1)[1])
    if name.startswith("response."):
        return metrics.get(name)
    return metrics.get(name, resp.get(name, {}).get("value"))


def cmp_(actual, op, expected):
    if actual is None or expected is None:
        return None
    if op in ("in", "not_in"):
        lis = expected if isinstance(expected, list) else [expected]
        return actual in lis if op == "in" else actual not in lis
    if op in ("==", "!="):
        equal = str(actual) == str(expected)
        return equal if op == "==" else not equal
    a, b = num(actual), num(expected)
    if a is None or b is None:
        return None
    return {"<=": a <= b, "<": a < b, ">=": a >= b, ">": a > b}.get(op)


def constraints(spec, params, metrics, resp):
    out = []
    cs = rows(spec.get("hard_constraints"))
    budget = object_(spec.get("resources"))
    if num(budget.get("total_cost")) is not None:
        cs.append({"id": "resource.total_cost", "metric": "total_cost", "op": "<=",
                   "value": budget["total_cost"], "source": budget.get("source")})
    if num(budget.get("total_time_hours")) is not None:
        cs.append({"id": "resource.total_time_hours", "metric": "total_time_hours", "op": "<=",
                   "value": budget["total_time_hours"], "source": budget.get("source")})
    if num(budget.get("total_samples")) is not None:
        cs.append({"id": "resource.total_samples", "metric": "total_samples", "op": "<=",
                   "value": budget["total_samples"], "source": budget.get("source")})
    for i, c in enumerate(cs):
        name = str(c.get("metric", ""))
        actual = metric(name, params, metrics, resp)
        result = cmp_(actual, c.get("op"), c.get("value"))
        record = {"constraint_id": c.get("id", f"constraint[{i}]"), "metric": name,
                  "actual_value": actual, "operator": c.get("op"), "required_value": c.get("value"),
                  "unit": c.get("unit"), "source": c.get("source"),
                  "status": "pass" if result is True else "violated" if result is False else "unknown"}
        if not c.get("source"):
            record["status"] = "unknown"
            record["reason"] = "constraint source/locator required"
        if record["status"] == "violated":
            cv = metric_violation(actual, c.get("op"), c.get("value"))
        elif record["status"] == "unknown":
            cv = None
        else:
            cv = 0.0
        record["constraint_violation"] = rnd(cv) if isinstance(cv, float) else cv
        out.append(record)
    known_violations = [c["constraint_violation"] for c in out if c["status"] == "violated"]
    unknown = [x for x in out if x["status"] == "unknown"]
    norm = None if unknown else max(1.0, len(out))
    cv = sum(known_violations) / norm if not unknown and out else (None if unknown else 0.0)
    return {"checks": out, "status": "infeasible" if known_violations else
            "unknown" if unknown or not out else "feasible",
            "normalized_cv": rnd(cv) if isinstance(cv, float) else cv,
            "formula": "sum(max(0, violation)) / max(1, number_of_constraints); unknown is never CV=0"}


def metric_violation(actual, op, expected):
    a, b = num(actual), num(expected)
    if a is None or b is None:
        return 1.0  # categorical mismatch: finite, explicitly non-physical CV unit
    if op == "<=":
        return max(0.0, (a - b) / max(abs(b), EPS))
    if op == "<":
        return max(0.0, (a - b + EPS) / max(abs(b), EPS))
    if op == ">=":
        return max(0.0, (b - a) / max(abs(b), EPS))
    if op == ">":
        return max(0.0, (b - a + EPS) / max(abs(b), EPS))
    return 1.0


def evaluate(spec, mods, params):
    resp = responses(spec, mods, params)
    metrics = derived(spec, params, resp)
    gate = constraints(spec, params, metrics, resp)
    missing = [o["name"] for o in rows(spec.get("objectives")) if resp.get(o.get("name"), {}).get("value") is None]
    return {"parameters": {k: rnd(v) if isinstance(v, float) else v for k, v in params.items()},
            "responses": resp, "metrics": {k: rnd(v) if isinstance(v, float) else v
                                             for k, v in metrics.items() if not k.endswith("_formula")},
            "metric_formulas": {k: v for k, v in metrics.items() if k.endswith("_formula")},
            "gate": gate, "unknown_objective_values": missing,
            "selection_status": "eligible" if gate["status"] == "feasible" and not missing else
                                "unknown" if gate["status"] == "unknown" else
                                "response_unknown" if missing else "infeasible",
            "response_basis": ["observed matched runs" if any(r["kind"] == "observed" for r in resp.values())
                                else "declared explicit model only"]}


def key(params):
    return json.dumps(params, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def lhs(variables, n, seed, offset):
    # Pydoc-free equivalent of ordinary LHS (one seeded jittered point per
    # dimension-stratum). A fixed seed is part of the recorded domain.
    rng = random.Random(seed)
    perms = []
    for v in variables:
        d = len(v["levels"])
        buckets = list(range(d))
        if d >= n:
            buckets = rng.sample(buckets, n)
        else:
            buckets = [buckets[i % d] for i in range(n)]
            rng.shuffle(buckets)
        perms.append(buckets)
    points = []
    for j in range(n):
        params = {}
        for v, buckets in zip(variables, perms):
            levels = v["levels"]
            idx = buckets[j]
            if len(levels) >= n:
                params[v["name"]] = levels[idx]
            else:
                params[v["name"]] = levels[(idx + offset) % len(levels)]
        points.append(params)
    return points


def rank_pool(pool, objectives):
    eligible = [p for p in pool if p["selection_status"] == "eligible"]
    weights = [float(num(o.get("weight", 1)) or 0) for o in objectives]
    sw = sum(weights)
    if sw <= 0:
        weights = [1.0] * len(objectives)
        sw = max(1, len(weights))
    weights = [w / sw for w in weights]
    bounds = {}
    for o in objectives:
        values = [p["responses"][o["name"]]["value"] for p in eligible]
        bounds[o["name"]] = [min(values), max(values)] if values else [None, None]
    for p in eligible:
        raw = {}
        total = 0.0
        for w, o in zip(weights, objectives):
            val = p["responses"][o["name"]]["value"]
            lo, hi = bounds[o["name"]]
            if hi is None or lo is None:
                score = None
            elif abs(hi - lo) <= EPS:
                score = 1.0
            elif o.get("direction", "maximize") == "minimize":
                score = (hi - val) / (hi - lo)
            else:
                score = (val - lo) / (hi - lo)
            raw[o["name"]] = score
            total += w * score if score is not None else 0.0
        p["objective_scores"] = raw
        p["weighted_score"] = rnd(total)
        p["scoring_formula"] = "sum(normalised_weight * minmax_score) over feasible complete-response candidates only"
    ranked = sorted(eligible, key=lambda p: (-p["weighted_score"], key(p["parameters"])))
    for i, p in enumerate(ranked):
        p["rank"] = i + 1
    # Feasibility dominates scalar score, even for a very favourable response.
    for p in pool:
        p.setdefault("weighted_score", None)
        p.setdefault("rank", None)
    p_rank = {key(p["parameters"]): p for p in ranked}
    return p_rank, bounds, dict((o["name"], w) for o, w in zip(objectives, weights))


def weight_sensitivity(pool, objectives, best, bounds):
    if best is None:
        return {"method": "one_at_a_time full re-ranking", "scenarios": []}
    out = []
    for i, o in enumerate(objectives):
        for factor in (0.8, 1.2):
            changed = [dict(x) for x in objectives]
            w = num(changed[i].get("weight", 1))
            changed[i]["weight"] = (w if w is not None else 1) * factor
            _, _, _ = rank_pool(pool, objectives)
            for p in pool:
                if not p.get("objective_scores"):
                    continue
                all_w = [max(0.0, num(x.get("weight", 1)) or 0) for x in changed]
                s = sum(all_w) or len(all_w)
                weights = [x / s for x in all_w] if sum(all_w) else [1.0 / len(all_w)] * len(all_w)
                p["_candidate_score"] = sum(weights[j] * p["objective_scores"].get(x["name"], 0)
                                            for j, x in enumerate(changed))
            eligible = sorted([p for p in pool if p["selection_status"] == "eligible"],
                              key=lambda p: (-p.get("_candidate_score", 0), key(p["parameters"])))
            winner = eligible[0] if eligible else None
            for p in pool:
                p.pop("_candidate_score", None)
            out.append({"changed_objective": o["name"], "factor": factor,
                        "winner": winner["parameters"] if winner else None,
                        "winner_changed": winner is not None and key(winner["parameters"]) != key(best["parameters"]),
                        "method": "same objective min-max scaling and all feasible candidates re-ranked"})
    return {"method": "one_at_a_time full re-ranking, each weight multiplied by 0.8 and 1.2 then renormalised",
            "scenarios": out, "stable_winner": not any(s["winner_changed"] for s in out)}


def morris(spec, mods, best, objective):
    if best is None:
        return []
    base = best["parameters"]
    deltas = []
    for v in spec["_domains"]:
        levels = v["levels"] if len(v["levels"]) <= 4 else [v["levels"][0], v["levels"][len(v["levels"]) // 2], v["levels"][-1]]
        effects = []
        if v["kind"] == "categorical":
            continue
        points = []
        for level in levels:
            p = dict(base); p[v["name"]] = level
            e = evaluate(spec, mods, p)
            y = metric("response." + objective, p, e["metrics"], e["responses"])
            points.append({"value": level, "response": y,
                           "gate_status": e["gate"]["status"]})
        if len(points) < 2:
            continue
        lo, hi = points[0]["response"], points[-1]["response"]
        dx = points[-1]["value"] - points[0]["value"]
        if abs(dx) > EPS and lo is not None and hi is not None:
            effects.append((hi - lo) / dx)
        for a, b in zip(points, points[1:]):
            dx = b["value"] - a["value"]
            ya, yb = a["response"], b["response"]
            if abs(dx) > EPS and ya is not None and yb is not None:
                effects.append((yb - ya) / dx)
        if effects:
            deltas.append({"parameter": v["name"], "delta_levels": [p["value"] for p in points],
                           "elementary_effects": effects, "mu": mean(effects),
                           "mu_star": mean([abs(x) for x in effects]), "sigma": sd(effects) if len(effects) > 1 else None,
                           "n_elementary_effects": len(effects),
                           "formula": "EE=(f(x_i+delta)-f(x_i))/delta; mu=mean(EE), mu_star=mean(|EE|), sigma=sample_sd(EE)",
                           "points": points,
                           "limit": "small finite-grid local screen; sigma with few paths is not an interaction significance test"})
    return deltas


def optimize(spec):
    spec = copy.deepcopy(spec)
    variables = [domain(v) for v in rows(spec.get("variables"))]
    if not variables:
        raise ValueError("no finite variables supplied")
    spec["_domains"] = variables
    objectives = rows(spec.get("objectives"))
    objectives = [o for o in objectives if str(o.get("name", "")).strip()]
    if not objectives:
        raise ValueError("at least one objective with name/direction is required")
    for objective in objectives:
        if objective.get("direction", "maximize") not in ("maximize", "minimize"):
            raise ValueError("objective.direction must be exactly maximize or minimize")
    mods = models(spec)
    search = object_(spec.get("search"))
    grid_size = math.prod(len(v["levels"]) for v in variables)
    if grid_size > 20000:
        raise ValueError("finite cartesian domain exceeds 20000 cells; provide a smaller explicit bounded grid with documented sampling levels")
    full_grid = list(itertools.product(*(v["levels"] for v in variables)))
    domains = [dict(zip((v["name"] for v in variables), point)) for point in full_grid]
    requested = integer(search.get("max_evaluations"))
    default_budget = min(1000, len(domains))
    budget = requested if requested and requested > 0 else default_budget
    budget = min(budget, 5000)
    baseline = object_(spec.get("baseline"))
    baseline_params = baseline.get("parameters")
    pending = []
    if isinstance(baseline_params, dict):
        pending.append((copy.deepcopy(baseline_params), "baseline"))
    for k, p in enumerate(domains):
        if len(domains) <= budget or k < budget // 2:
            pending.append((p, "full_grid" if len(domains) <= budget else "grid_prefix"))
    seed = integer(search.get("seed"))
    declared_seed = integer(search.get("seed", spec.get("seed")))
    if seed is None:
        seed = 0
    fraction = num(search.get("initial_fraction"))
    fraction = 0.6 if fraction is None else min(1.0, max(0.0, fraction))
    initial = max(1, int(budget * fraction))
    for k, p in enumerate(lhs(variables, max(1, initial), seed, k_default(spec))):
        pending.append((p, "seeded_lhs"))
    pool, seen = [], set()
    def take(points):
        for params, strategy in points:
            if len(pool) >= budget:
                return
            if any(params.get(v["name"]) not in v["levels"] for v in variables):
                continue
            dig = key(params)
            if dig in seen:
                continue
            seen.add(dig)
            result = evaluate(spec, mods, params)
            result["evaluation_index"] = len(pool) + 1
            result["strategy"] = strategy
            result["id"] = f"candidate-{len(pool)+1:04d}"
            pool.append(result)
    take(pending)
    if not pool:
        raise ValueError("no valid candidate can be produced from the supplied domains and baseline")
    patience = integer(search.get("patience"), max(2, len(variables)))
    patience = max(1, patience)
    paused = 0
    last_score = None
    stop_reason = "evaluation budget exhausted"
    improvement_tolerance = num(search.get("improvement_tolerance"))
    if improvement_tolerance is None or improvement_tolerance < 0:
        improvement_tolerance = 0.0
    while len(pool) < budget:
        _, _, _ = rank_pool(pool, objectives)
        valid = [p for p in pool if p["selection_status"] == "eligible"]
        centre = valid[0] if valid else pool[0]
        trials = []
        for v in variables:
            for level in v["levels"]:
                candidate = dict(centre["parameters"])
                candidate[v["name"]] = level
                if candidate != centre["parameters"]:
                    trials.append((candidate, "coordinate_neighbour"))
        before = len(pool)
        take(trials)
        _, bounds, _ = rank_pool(pool, objectives)
        valid = [p for p in pool if p["selection_status"] == "eligible"]
        current_score = None
        if valid:
            valid.sort(key=lambda p: (-p["weighted_score"], key(p["parameters"])))
            current_score = valid[0]["weighted_score"]
        if len(pool) == before:
            stop_reason = "all coordinate points are already evaluated within this finite domain"
            break
        if current_score is None or last_score is None or current_score - last_score > improvement_tolerance:
            paused = 0
        else:
            paused += 1
        last_score = current_score
        if paused >= patience and valid:
            stop_reason = f"no score improvement greater than {improvement_tolerance} for {patience} new-point rounds"
            break
    _, bounds, weights = rank_pool(pool, objectives)
    feasible = sorted([p for p in pool if p["selection_status"] == "eligible"],
                      key=lambda p: (-p["weighted_score"], key(p["parameters"])))
    best = feasible[0] if feasible else None
    compare = None
    if best is not None and isinstance(baseline_params, dict):
        base_eval = next((p for p in pool if match(p["parameters"], baseline_params) and
                          match(baseline_params, p["parameters"])), None)
        compare = {"baseline_parameters": baseline_params}
        if base_eval:
            compare["candidate_gate_status"] = base_eval["gate"]["status"]
            compare["responses"] = {}
            for o in objectives:
                name = o["name"]
                x = base_eval["responses"][name]["value"]
                y = best["responses"][name]["value"]
                compare["responses"][name] = {"baseline": x, "candidate": y,
                       "delta": y - x if x is not None and y is not None else None,
                       "relative_delta": (y - x) / abs(x) if x not in (None, 0) and y is not None else None,
                       "measurement_tolerance": o.get("tolerance"),
                       "conclusion": "model/observed arithmetic only; no causal or experimental evidence claim"}
                if base_eval["responses"][name]["kind"] == "observed" and best["responses"][name]["kind"] == "observed":
                    a = base_eval["responses"][name]["statistics"].get("values", [])
                    b = best["responses"][name]["statistics"].get("values", [])
                    delta = sd(a), sd(b)
                    if len(a) > 1 and len(b) > 1:
                        pooled = math.sqrt(((len(a) - 1) * delta[0] ** 2 + (len(b) - 1) * delta[1] ** 2) /
                                          (len(a) + len(b) - 2))
                        compare["responses"][name]["cohens_d_pooled_sensitivity"] = (mean(b) - mean(a)) / pooled if pooled > 0 else None
                        compare["responses"][name]["effect_note"] = "direction not transformed for preferred objective; pooled-SD effect only"
    weight_stable = weight_sensitivity(pool, objectives, best, bounds)
    sens = morris(spec, mods, best, objectives[0]["name"])
    findings = []
    if best is None:
        findings.append({"rule": "optimization.no_feasible_complete_point", "severity": "high",
                          "message": "no candidate passed all bounds with complete objective values; do not issue a partial optimum"})
    else:
        findings.append({"rule": "optimization.validation_required", "severity": "low",
                          "message": "selected coordinates are computational candidates; verify against the supplied experimental protocol before execution"})
    if not search.get("max_evaluations"):
        findings.append({"rule": "optimization.budget_defaulted", "severity": "medium",
                          "message": f"search.max_evaluations not supplied; deterministic fallback budget {budget} used"})
    if declared_seed is None:
        findings.append({"rule": "optimization.seed_missing", "severity": "medium", "message": "no seed declared; deterministic fallback seed 0 used"})
    if not any(r["kind"] == "observed" for p in pool for r in p["responses"].values()):
        findings.append({"rule": "optimization.response_model_only", "severity": "medium",
                          "message": "recommendations rely on explicit models, not completed real experiments"})
    if not isinstance(baseline_params, dict):
        findings.append({"rule": "optimization.baseline_missing", "severity": "medium",
                          "message": "baseline.parameters is not supplied; no baseline comparison is claimed"})
    for o in objectives:
        if not o.get("measurement"):
            findings.append({"rule": "optimization.response_tolerance_undeclared", "severity": "medium",
                              "objective": o.get("name"), "message": "declare measurement method and tolerance for this response"})
    counts = {}
    for f in findings:
        counts[f["severity"]] = counts.get(f["severity"], 0) + 1
    status = "blocked" if counts.get("high") else "review" if findings else "clean"
    canon = json.dumps({k: v for k, v in spec.items() if not k.startswith("_")}, ensure_ascii=False,
                       sort_keys=True, separators=(",", ":")).encode("utf-8")
    result = {"schema_version": VERSION, "status": status,
              "delivery_status": {"clean": "done", "review": "partial", "blocked": "failed"}[status],
              "findings": findings, "severity_counts": counts,
              "objective_declaration": objectives,
              "parameter_domains": variables,
              "baseline_comparisons": compare,
              "candidate_evaluations": pool, "search_trace": [
                  {"evaluation_index": p["evaluation_index"], "candidate_id": p["id"],
                   "strategy": p["strategy"], "gate_status": p["gate"]["status"],
                   "objective_scores": p.get("objective_scores"), "weighted_score": p.get("weighted_score")}
                  for p in pool],
              "search_record": {"full_grid_size": len(domains), "evaluated": len(pool),
                   "max_evaluations": budget, "seed": seed, "lhs_initial_fraction": initial / budget,
                   "initial_method": "baseline if supplied + bounded grid prefix when small + seeded stratified LHS",
                   "local_method": "single-variable coordinate neighbours of the current eligible candidate",
                   "stop_rules": {"budget_exhausted": len(pool) >= budget,
                       "patience_after_rounds": patience,
                       "improvement_tolerance": improvement_tolerance,
                       "exhausted_when_all_coordinate_points_seen": True},
                   "actual_stop_reason": stop_reason,
                   "seed_explicitly_declared": declared_seed is not None,
                   "budget_detail": "counts model/known-data evaluations only; experimental costs are separately gated",
                   "local_screen_paths": 1},
              "weight_sensitivity": weight_stable,
              "parameter_sensitivity": {"method": "finite-grid Morris elementary effects",
                   "primary_objective": objectives[0]["name"], "results": sens,
                   "reference": "https://github.com/SALib/SALib/blob/main/src/SALib/analyze/morris.py"},
              "source_and_evidence": [{"source": v["source"], "locator": v.get("locator"),
                                       "parameter": v["name"]} for v in variables] +
                                     [{"source": m["source"], "locator": m.get("locator"),
                                       "model": name} for name, m in mods.items()],
              "limits": ["Predicted responses are not fabricated wet measurements. Real validation must use source units, approved ranges, and independent repeats.",
                         "max-min scaling uses the evaluated feasible pool, so ranking is not a universal clinical/physical optimum.",
                         "Morris screens are local to the selected point and finite grid, not global causal sensitivity.",
                         "Unmatched observations, units or constraints are kept unknown and cannot silently switch to predictions."],
              "reproducibility": {"engine": "scripts/bounded_optimize.py", "seed": seed,
                                   "domain_sha256": hashlib.sha256(canon).hexdigest(),
                                   "python": "3.9+ standard library",
                                   "rerun": "python scripts/bounded_optimize.py --spec SPEC.json --case CASE.json --out OUTPUT_DIR"},
              "reference_methods": [{"name": "pymoo feasibility-first", "source": "https://pymoo.org/constraints/index.html",
                      "implemented_here": "complete feasible candidates rank by weighted objective; violated candidates never promoted"},
                     {"name": "SciPy QMC LatinHypercube", "source": "https://docs.scipy.org/doc/scipy/reference/generated/scipy.stats.qmc.LatinHypercube.html",
                      "implemented_here": "seeded stratification across finite domains, without numpy dependency; continuous random LHS requires a declared finite grid"},
                     {"name": "SALib Morris elementary effects", "source": "https://github.com/SALib/SALib/blob/main/src/SALib/analyze/morris.py",
                      "implemented_here": "mu/mu_star/sigma of explicit local finite-grid elementary effects"}]}
    result["experiment_plan"] = {
        "objective_declaration": objectives,
        "baseline": baseline_params,
        "variable_domains": [{"name": v["name"], "levels": v["levels"], "unit": v["unit"]} for v in variables],
        "search_and_budget": result["search_record"],
        "stopping_rule": result["search_record"]["stop_rules"],
        "validation": "recommended points require source-grounded approval and independent validation"}
    result["evidence_and_risks"] = {
        "sources": result["source_and_evidence"],
        "baseline_comparisons": compare,
        "response_tolerances": [{"name": o["name"], "measurement": o.get("measurement"),
                                  "tolerance": o.get("tolerance")} for o in objectives],
        "feasible_candidate_constraints": best["gate"]["checks"] if best else [p["gate"] for p in pool[:8]],
        "sensitivity": result["parameter_sensitivity"]}
    result["sources"] = result["source_and_evidence"]
    result["uncertainty"] = [
        {"kind": kind, "source": "no completed experimental validation" if kind == "response_model_only" else
                  "finite evaluated pool; candidate rank may change with new domain levels",
         "passed_constraints_only": best["gate"]["checks"] if best else None}
        for kind in sorted({f["rule"] for f in findings})]
    result["confirmation_items"] = [c for p in pool[:100] for c in p["gate"]["checks"]
                                    if c["status"] != "pass"]
    if best:
        result["recommended_parameters"] = best["parameters"]
        result["recommendation"] = {"candidate_id": best["id"], "parameters": best["parameters"],
             "predicted_or_observed_responses": best["responses"], "cost_and_resource_metrics": best["metrics"],
             "constraint_results": best["gate"]["checks"], "weighted_score": best["weighted_score"],
             "basis": "feasible best candidate under supplied objectives and pool",
             "pending_validation": not any(v["kind"] == "observed" for v in best["responses"].values()),
             "replicate_and_acceptance_plan": {"independent_replicates": object_(spec.get("study_design")).get("independent_replicates"),
                  "do_not_call_technical_repeats_independent": True,
                  "report": ["mean", "sample_sd", "standard_error", "mean_ci95", "source_data_rows"],
                  "acceptance": "predeclare objective tolerance and hard constraints; do not substitute model uncertainty for experimental uncertainty"}}
    else:
        result["recommended_parameters"] = None
        result["recommendation"] = {"status": "not_recommended",
             "reason": "no hard-feasible candidate with complete response evidence",
             "least_violating_candidates": sorted([{"parameters": p["parameters"],
                  "normalized_cv": p["gate"]["normalized_cv"], "status": p["selection_status"]}
                  for p in pool if p["gate"]["status"] == "infeasible"],
                 key=lambda x: (x["normalized_cv"], key(x["parameters"])))[:5]}
    return result


def k_default(spec):
    return integer(spec.get("search", {}).get("lhs_offset"), 0) if isinstance(spec.get("search"), dict) else 0


def with_contract(result, spec, case):
    case = object_(case)
    cid = spec.get("case_id", case.get("case_id", case.get("id")))
    if cid is not None:
        result["case_id"] = cid
    oc = spec.get("output_contract", case.get("output_contract"))
    keys = list(oc) if isinstance(oc, dict) else oc if isinstance(oc, list) else []
    if oc is not None and not isinstance(oc, (dict, list)):
        result["limits"].append("output_contract is not an object or list of field names")
    for k in [x for x in keys if isinstance(x, str)]:
        if k in result:
            continue
        v = spec.get(k, case.get(k))
        if v is not None and k not in ("variables", "observed_runs", "response_models", "output_contract", "spec"):
            result[k] = copy.deepcopy(v)
        else:
            result[k] = None
            result["limits"].append(f"output_contract field '{k}' is not derivable by this engine")
    return result


def write_refusal(out, message, spec=None, case=None):
    r = {"schema_version": VERSION, "status": "undetermined", "delivery_status": "failed",
         "findings": [{"rule": "optimization.spec_unreadable", "severity": "high", "message": str(message)}],
         "recommended_parameters": None, "limits": [str(message)],
         "uncertainty": ["no response or experimental state inferred while input was invalid"],
         "source_and_evidence": [], "candidate_evaluations": []}
    with_contract(r, object_(spec), case)
    out.mkdir(parents=True, exist_ok=True)
    (out / "result.json").write_text(json.dumps(r, ensure_ascii=False, indent=2), encoding="utf-8")
    return r


def build(spec_path, out, case_path=None):
    spec, case = None, None
    if case_path:
        try:
            case = json.loads(Path(case_path).read_text(encoding="utf-8-sig"))
        except Exception as exc:
            return write_refusal(out, f"invalid case: {exc}")
    try:
        spec = json.loads(Path(spec_path).read_text(encoding="utf-8-sig"))
        if isinstance(spec, dict) and isinstance(spec.get("spec"), dict):
            spec = spec["spec"]
        if not isinstance(spec, dict):
            raise ValueError("spec is not a JSON object")
        result = optimize(spec)
        with_contract(result, spec, case)
        out.mkdir(parents=True, exist_ok=True)
        (out / "result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        return result
    except (ValueError, TypeError, KeyError, OSError, ArithmeticError) as exc:
        return write_refusal(out, exc, spec, case)


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--spec", required=True)
    p.add_argument("--case")
    p.add_argument("--out", required=True)
    a = p.parse_args(argv)
    r = build(Path(a.spec), Path(a.out), a.case)
    print(json.dumps({"status": r["status"], "recommended_parameters": r.get("recommended_parameters"),
                      "result": str(Path(a.out) / "result.json")}, ensure_ascii=False))
    return {"clean": 0, "review": 3, "blocked": 4, "undetermined": 5}.get(r["status"], 1)


if __name__ == "__main__":
    raise SystemExit(main())
