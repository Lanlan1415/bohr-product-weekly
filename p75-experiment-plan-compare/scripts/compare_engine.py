"""Deterministic aligned comparison and selection of versioned experiment plans.

Hard gates precede MCDA. Scores are declared decision aids, never measured outcomes.
"""
from __future__ import annotations

import copy
import hashlib
import json
import math

SCHEMA = "experiment-plan-compare/v1"
SEVERITIES = ("high", "medium", "low")


class SpecError(ValueError):
    pass


def _num(x):
    return isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(x)


def _list(x):
    return x if isinstance(x, list) else []


def _dict(x):
    return x if isinstance(x, dict) else {}


def _round(x):
    return round(float(x), 8) if _num(x) else x


def _sha(x):
    return hashlib.sha256(json.dumps(x, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def _finding(findings, rule, severity, message, path=None, **locator):
    row = {"rule": rule, "severity": severity, "message": message}
    if path:
        row["path"] = path
    row.update({k: v for k, v in locator.items() if v is not None})
    findings.append(row)


def _compare(actual, op, expected):
    if actual is None:
        return None
    try:
        if op == "<=": return actual <= expected
        if op == "<": return actual < expected
        if op == ">=": return actual >= expected
        if op == ">": return actual > expected
        if op in ("==", "="): return actual == expected
        if op == "!=": return actual != expected
        if op == "in": return actual in expected
        if op == "contains": return expected in actual
    except (TypeError, ValueError):
        return False
    return False


def _lookup(candidate, metric):
    if metric in candidate["metrics"]:
        return candidate["metrics"][metric]
    current = candidate["plan"]
    for part in str(metric).split("."):
        if not isinstance(current, dict) or part not in current:
            return None
        current = current[part]
    return current


def _cost(candidate, findings):
    plan = candidate["plan"]
    items = plan.get("cost_items", [])
    if not isinstance(items, list):
        raise SpecError(f"{candidate['plan_id']}.cost_items must be a list")
    if not items:
        value = candidate["metrics"].get("total_cost")
        if _num(value):
            _finding(findings, "cost.not_itemised", "medium",
                     "total_cost is declared but cannot be recalculated without cost_items.",
                     f"candidate_plans.{candidate['plan_id']}.metrics.total_cost")
        return value, [], None
    total, currency, lines = 0.0, None, []
    for i, item in enumerate(items):
        path = f"candidate_plans.{candidate['plan_id']}.cost_items[{i}]"
        if not isinstance(item, dict) or not all(_num(item.get(k)) for k in ("quantity", "unit_cost")) or item["quantity"] < 0 or item["unit_cost"] < 0:
            _finding(findings, "cost.invalid_item", "high", "Cost item needs non-negative numeric quantity and unit_cost.", path)
            return None, lines, currency
        basis = item.get("basis", "per_plan")
        multiplier = {"per_plan": 1, "per_run": plan.get("n_runs"), "per_measurement": plan.get("n_measurements")}.get(basis)
        if not _num(multiplier) or multiplier < 0:
            _finding(findings, "cost.multiplier_missing", "high", f"Basis '{basis}' needs a declared non-negative n_runs/n_measurements.", path)
            return None, lines, currency
        this_currency = item.get("currency")
        if currency is None:
            currency = this_currency
        elif currency != this_currency:
            _finding(findings, "cost.currency_mixed", "high", "Convert unlike currencies using a dated source before addition.", path)
            return None, lines, currency
        amount = item["quantity"] * item["unit_cost"] * multiplier
        total += amount
        lines.append({"id": item.get("id", f"C{i+1}"), "kind": item.get("kind"),
                      "quantity": item["quantity"], "unit": item.get("unit"), "unit_cost": item["unit_cost"],
                      "basis": basis, "multiplier": multiplier, "currency": this_currency,
                      "amount": _round(amount), "source": item.get("source"),
                      "fixed_or_recurring": item.get("fixed_or_recurring", "fixed" if basis == "per_plan" else "recurring")})
    computed = _round(total)
    declared = candidate["metrics"].get("total_cost")
    if _num(declared) and not math.isclose(declared, computed, rel_tol=1e-9, abs_tol=1e-8):
        _finding(findings, "cost.total_mismatch", "high",
                 f"Declared total_cost={declared} differs from itemised total={computed}; engine uses itemised total.",
                 f"candidate_plans.{candidate['plan_id']}.metrics.total_cost", declared=declared, computed=computed)
    return computed, lines, currency


def _time(candidate, findings):
    plan = candidate["plan"]
    items = plan.get("time_items", [])
    if not isinstance(items, list):
        raise SpecError(f"{candidate['plan_id']}.time_items must be a list")
    if not items:
        value = candidate["metrics"].get("total_time_hours")
        if _num(value):
            _finding(findings, "time.not_itemised", "medium",
                     "total_time_hours is declared but preparation/queue/rework cannot be recalculated without time_items.",
                     f"candidate_plans.{candidate['plan_id']}.metrics.total_time_hours")
        return value, []
    total, lines = 0.0, []
    for i, item in enumerate(items):
        path = f"candidate_plans.{candidate['plan_id']}.time_items[{i}]"
        if not isinstance(item, dict) or not _num(item.get("hours")) or item["hours"] < 0:
            _finding(findings, "time.invalid_item", "high", "Time item needs non-negative numeric hours.", path)
            return None, lines
        basis = item.get("basis", "per_plan")
        multiplier = {"per_plan": 1, "per_run": plan.get("n_runs")}.get(basis)
        probability = item.get("probability", 1)
        if not _num(multiplier) or multiplier < 0 or not _num(probability) or not 0 <= probability <= 1:
            _finding(findings, "time.invalid_multiplier", "high", "Time multiplier or probability is invalid.", path)
            return None, lines
        expected = item["hours"] * multiplier * probability
        total += expected
        lines.append({"id": item.get("id", f"T{i+1}"), "kind": item.get("kind", "execution"),
                      "hours": item["hours"], "basis": basis, "multiplier": multiplier,
                      "probability": probability, "expected_hours": _round(expected), "source": item.get("source")})
    computed = _round(total)
    declared = candidate["metrics"].get("total_time_hours")
    if _num(declared) and not math.isclose(declared, computed, rel_tol=1e-9, abs_tol=1e-8):
        _finding(findings, "time.total_mismatch", "high",
                 f"Declared total_time_hours={declared} differs from itemised expected total={computed}; engine uses itemised total.",
                 f"candidate_plans.{candidate['plan_id']}.metrics.total_time_hours", declared=declared, computed=computed)
    return computed, lines


def _criteria(spec):
    raw = spec.get("criteria")
    if not isinstance(raw, list) or not raw:
        raise SpecError("criteria must be a non-empty list so every plan is compared on the same fields")
    criteria, names = [], set()
    for i, c in enumerate(raw):
        if not isinstance(c, dict) or not isinstance(c.get("name"), str) or not c["name"] or c["name"] in names:
            raise SpecError(f"criteria[{i}] needs a unique non-empty name")
        if not _num(c.get("weight")) or c["weight"] < 0 or c.get("direction", "max") not in ("min", "max"):
            raise SpecError(f"criterion '{c['name']}' needs non-negative weight and min/max direction")
        names.add(c["name"])
        row = copy.deepcopy(c)
        row["direction"] = c.get("direction", "max")
        criteria.append(row)
    if sum(c["weight"] for c in criteria) <= 0:
        raise SpecError("at least one criterion weight must be positive")
    total = sum(c["weight"] for c in criteria)
    for c in criteria:
        c["original_weight"] = c["weight"]
        c["weight"] = c["weight"] / total
    return criteria


def _uncertainties(candidate, findings):
    raw = candidate["plan"].get("uncertainties", {})
    result = {}
    if isinstance(raw, dict):
        iterable = [dict(_dict(v), metric=k) if isinstance(v, dict) else {"metric": k, "lower": None, "upper": None} for k, v in raw.items()]
    elif isinstance(raw, list):
        iterable = raw
    else:
        _finding(findings, "uncertainty.malformed", "medium", "uncertainties must be an object or list.", f"candidate_plans.{candidate['plan_id']}.uncertainties")
        return result
    for i, item in enumerate(iterable):
        if not isinstance(item, dict) or not item.get("metric") or not all(_num(item.get(k)) for k in ("lower", "upper")) or item["lower"] > item["upper"]:
            _finding(findings, "uncertainty.invalid_interval", "medium", "Uncertainty needs metric and numeric lower <= upper.", f"candidate_plans.{candidate['plan_id']}.uncertainties[{i}]")
            continue
        result[item["metric"]] = {"lower": item["lower"], "upper": item["upper"], "source": item.get("source"), "meaning": item.get("meaning")}
    return result


def _gates(spec, candidate, findings):
    constraints = spec.get("hard_constraints", [])
    if not isinstance(constraints, list):
        raise SpecError("hard_constraints must be a list")
    results = []
    for i, c in enumerate(constraints):
        path = f"hard_constraints[{i}]"
        if not isinstance(c, dict) or not c.get("metric") or not c.get("op") or "value" not in c:
            _finding(findings, "constraint.malformed", "high", "Hard constraint needs metric, op and value.", path)
            results.append({"id": f"constraint[{i}]", "status": "unknown", "source": None})
            continue
        actual = _lookup(candidate, c["metric"])
        passed = _compare(actual, c["op"], c["value"])
        status = "unknown" if passed is None else ("passed" if passed else "failed")
        interval = candidate["uncertainties"].get(c["metric"])
        uncertainty_gate = False
        if interval and actual is not None:
            low = _compare(interval["lower"], c["op"], c["value"])
            high = _compare(interval["upper"], c["op"], c["value"])
            outcomes = {low, high}
            if None in outcomes or len(outcomes) > 1 or (passed not in outcomes):
                status = "unknown"
                uncertainty_gate = True
        results.append({"id": c.get("id", f"constraint[{i}]"), "metric": c["metric"], "actual": actual,
                        "op": c["op"], "required": c["value"], "unit": c.get("unit"),
                        "status": status, "source": c.get("source"), "rationale": c.get("rationale"),
                        "uncertainty_interval": copy.deepcopy(interval), "uncertainty_gate": uncertainty_gate})
    return results


def _evidence_records(value):
    if isinstance(value, (str, dict)):
        value = [value]
    records = []
    for item in _list(value):
        if isinstance(item, str):
            records.append({"source_id": item})
        elif isinstance(item, dict):
            records.append(copy.deepcopy(item))
    return records


def _source_index(spec):
    sources = spec.get("sources", [])
    if isinstance(sources, dict):
        return {str(k): _dict(v) for k, v in sources.items()}
    return {str(x.get("id")): x for x in _list(sources) if isinstance(x, dict) and x.get("id")}


def _normalise(value, criterion, observed):
    bounds = criterion.get("scale_bounds")
    declared = isinstance(bounds, list) and len(bounds) == 2 and all(_num(x) for x in bounds) and bounds[1] > bounds[0]
    if not declared:
        bounds = criterion.get("_resolved_bounds") or [min(observed), max(observed)]
    lo, hi = bounds
    if hi == lo:
        return 1.0, bounds, "constant across compared plans; no discrimination"
    clipped = min(max(value, lo), hi)
    score = (clipped - lo) / (hi - lo)
    if criterion["direction"] == "min":
        score = 1 - score
    note = "clipped to declared scale" if value < lo or value > hi else None
    return score, bounds, note


def _rank(rows):
    ranked = sorted(rows, key=lambda x: (-x["score"], x["plan_id"]))
    for i, row in enumerate(ranked, 1):
        row["rank"] = i
    return ranked


def _build_scores(spec, candidates, criteria, findings, sources):
    eligible = [c for c in candidates if c["gate_status"] == "passed"]
    evidence_matrix, raw_matrix, rows = [], [], []
    for criterion in criteria:
        observed = [_lookup(c, criterion["name"]) for c in candidates]
        observed = [x for x in observed if _num(x)]
        if not criterion.get("scale_bounds") and observed:
            criterion["_resolved_bounds"] = [min(observed), max(observed)]
            _finding(findings, "criterion.bounds_derived", "medium",
                     f"Criterion '{criterion['name']}' lacks scale_bounds; observed min/max is used and adding a plan may change ranks.",
                     f"criteria.{criterion['name']}.scale_bounds")
        elif isinstance(criterion.get("scale_bounds"), list):
            criterion["_resolved_bounds"] = copy.deepcopy(criterion["scale_bounds"])
    for candidate in candidates:
        cells, total, missing = [], 0.0, False
        for criterion in criteria:
            name = criterion["name"]
            raw = _lookup(candidate, name)
            path = f"candidate_plans.{candidate['plan_id']}.metrics.{name}"
            evidence = _evidence_records(_dict(candidate["plan"].get("evidence")).get(name))
            calculation = None
            if name == "total_cost" and candidate["cost_lines"]:
                evidence += [{"source_id": x.get("source"), "locator": f"cost_items.{x['id']}"} for x in candidate["cost_lines"] if x.get("source")]
                calculation = {"formula": "sum(quantity*unit_cost*basis_multiplier)", "items": copy.deepcopy(candidate["cost_lines"])}
            if name == "total_time_hours" and candidate["time_lines"]:
                evidence += [{"source_id": x.get("source"), "locator": f"time_items.{x['id']}"} for x in candidate["time_lines"] if x.get("source")]
                calculation = {"formula": "sum(hours*basis_multiplier*probability)", "items": copy.deepcopy(candidate["time_lines"])}
            # De-duplicate identical source/locator records without losing quotes.
            evidence = list({json.dumps(x, ensure_ascii=False, sort_keys=True): x for x in evidence}.values())
            rationale = _dict(candidate["plan"].get("rationales")).get(name)
            base_cell = {"plan_id": candidate["plan_id"], "criterion": name, "raw": raw,
                         "unit": criterion.get("unit"), "direction": criterion["direction"],
                         "weight": _round(criterion["weight"]), "weight_basis": criterion.get("weight_basis"),
                         "scale_bounds": criterion.get("_resolved_bounds"), "rationale": rationale,
                         "evidence": evidence, "calculation": calculation,
                         "uncertainty": copy.deepcopy(candidate["uncertainties"].get(name))}
            if not _num(raw):
                _finding(findings, "criterion.value_missing", "high", f"Plan {candidate['plan_id']} lacks numeric value for '{name}'.", path)
                missing = True
                evidence_matrix.append({**base_cell, "normalised": None, "weighted_contribution": None, "evidence_status": "value_missing"})
                continue
            norm, bounds, note = _normalise(raw, criterion, [raw])
            if note == "clipped to declared scale":
                _finding(findings, "criterion.outside_scale", "medium", f"{candidate['plan_id']} {name}={raw} lies outside scale bounds {bounds}; score clipped and hard gates still apply.", path)
            refs = []
            for record in evidence:
                sid = record.get("source_id") or record.get("id")
                if sid:
                    refs.append(str(sid))
                    if sources and str(sid) not in sources:
                        _finding(findings, "evidence.unknown_source", "high", f"Evidence source '{sid}' is not in the case source registry.", path, source_id=sid)
            if not evidence:
                _finding(findings, "evidence.missing", "high", f"Plan {candidate['plan_id']} criterion '{name}' has no evidence locator.", path)
            if not rationale:
                _finding(findings, "evidence.rationale_missing", "medium", f"Explain why {candidate['plan_id']} receives raw score/value {raw} for {name}.", path)
            cell = {**base_cell, "normalised": _round(norm), "weighted_contribution": _round(norm * criterion["weight"]),
                    "scale_bounds": bounds, "note": note, "evidence_refs": sorted(set(refs)),
                    "evidence_status": "present" if evidence else "missing"}
            cells.append(cell)
            evidence_matrix.append(copy.deepcopy(cell))
            raw_matrix.append({"plan_id": candidate["plan_id"], "criterion": name, "raw": raw,
                               "unit": criterion.get("unit"), "normalised": cell["normalised"],
                               "weight": cell["weight"], "weighted_contribution": cell["weighted_contribution"],
                               "evidence_refs": cell["evidence_refs"], "rationale": rationale})
            if candidate["gate_status"] == "passed":
                total += norm * criterion["weight"]
        if candidate["gate_status"] == "passed" and not missing:
            rows.append({"plan_id": candidate["plan_id"], "version": candidate["version"],
                         "score": _round(total * 100), "cells": cells})
    return _rank(rows), raw_matrix, evidence_matrix


def _scenario_rank(base_rows, criteria, weights, value_override=None):
    value_override = value_override or {}
    reranked = []
    for row in base_rows:
        score = 0.0
        for i, criterion in enumerate(criteria):
            cell = next(x for x in row["cells"] if x["criterion"] == criterion["name"])
            norm = cell["normalised"]
            override = value_override.get((row["plan_id"], criterion["name"]))
            if override is not None:
                bounds = criterion.get("_resolved_bounds") or cell["scale_bounds"]
                lo, hi = bounds
                if hi == lo:
                    norm = 1.0
                else:
                    clipped = min(max(override, lo), hi)
                    norm = (clipped - lo) / (hi - lo)
                    if criterion["direction"] == "min":
                        norm = 1 - norm
            score += norm * weights[i]
        reranked.append({"plan_id": row["plan_id"], "version": row["version"], "score": _round(score * 100)})
    return _rank(reranked)


def _sensitivity(spec, ranked, criteria, findings):
    if not ranked:
        return {"assessed": False, "reason": "no eligible scored plan"}, {"assessed": False, "reason": "no eligible scored plan"}
    delta = _dict(spec.get("sensitivity")).get("weight_delta", 0.2)
    if not _num(delta) or not 0 < delta <= 1:
        raise SpecError("sensitivity.weight_delta must be in (0,1]")
    base_winner = ranked[0]["plan_id"]
    base_weights = [c["weight"] for c in criteria]
    scenarios = []
    for i, criterion in enumerate(criteria):
        for multiplier in (1 - delta, 1 + delta):
            weights = list(base_weights)
            weights[i] *= multiplier
            sw = sum(weights)
            weights = [w / sw for w in weights]
            scenario_rank = _scenario_rank(ranked, criteria, weights)
            scenarios.append({"scenario": "one_at_a_time_weight", "criterion": criterion["name"],
                              "multiplier": _round(multiplier), "winner": scenario_rank[0]["plan_id"],
                              "base_winner": base_winner, "winner_changed": scenario_rank[0]["plan_id"] != base_winner,
                              "ranking": [{"plan_id": r["plan_id"], "score": r["score"]} for r in scenario_rank]})
    thresholds = []
    if len(ranked) >= 2:
        a, b = ranked[0], ranked[1]
        for i, criterion in enumerate(criteria):
            if base_weights[i] >= 1:
                continue
            ca = next(x for x in a["cells"] if x["criterion"] == criterion["name"])
            cb = next(x for x in b["cells"] if x["criterion"] == criterion["name"])
            differences = {c["name"]: next(x for x in a["cells"] if x["criterion"] == c["name"])["normalised"] - next(x for x in b["cells"] if x["criterion"] == c["name"])["normalised"] for c in criteria}
            other = sum(base_weights[j] * differences[criteria[j]["name"]] for j in range(len(criteria)) if j != i) / (1 - base_weights[i])
            di = differences[criterion["name"]]
            denominator = other - di
            if abs(denominator) > 1e-12:
                root = other / denominator
                if 0 < root < 1:
                    thresholds.append({"criterion": criterion["name"], "winner": a["plan_id"], "runner_up": b["plan_id"],
                                       "weight_at_tie": _round(root), "current_weight": _round(base_weights[i]),
                                       "interpretation": "Other weights keep their relative proportions; at this weight the top two scores tie."})
    sensitivity = {"assessed": True, "method": "one-at-a-time weight perturbation; all other weights proportionally renormalised",
                   "weight_delta": delta, "base_winner": base_winner, "scenarios": scenarios,
                   "winner_stable": not any(x["winner_changed"] for x in scenarios),
                   "exact_top_two_weight_flip_thresholds": thresholds,
                   "ranking": [{"plan_id": r["plan_id"], "score": r["score"]} for r in ranked]}
    # Deterministic interval corner probes, one cell at a time. Hard gates were already
    # worst-case gated, so these scenarios cannot hide a constraint violation.
    uncertainty_scenarios = []
    for row in ranked:
        for cell in row["cells"]:
            interval = cell.get("uncertainty")
            if not isinstance(interval, dict):
                continue
            for side in ("lower", "upper"):
                value = interval.get(side)
                if not _num(value):
                    continue
                override = {(row["plan_id"], cell["criterion"]): value}
                scenario_rank = _scenario_rank(ranked, criteria, base_weights, override)
                uncertainty_scenarios.append({"scenario": "single_cell_interval_corner", "plan_id": row["plan_id"],
                                              "criterion": cell["criterion"], "side": side, "value": value,
                                              "source": interval.get("source"), "winner": scenario_rank[0]["plan_id"],
                                              "base_winner": base_winner, "winner_changed": scenario_rank[0]["plan_id"] != base_winner,
                                              "ranking": [{"plan_id": r["plan_id"], "score": r["score"]} for r in scenario_rank]})
    uncertainty = {"assessed": bool(uncertainty_scenarios), "method": "declared lower/upper single-cell interval corners; no probability distribution assumed",
                   "hard_gate_policy": "if a constraint interval crosses its threshold, the candidate is unknown/ineligible before scoring",
                   "scenarios": uncertainty_scenarios,
                   "winner_stable": not any(x["winner_changed"] for x in uncertainty_scenarios) if uncertainty_scenarios else None,
                   "reason": None if uncertainty_scenarios else "no numeric criterion intervals declared"}
    if not sensitivity["winner_stable"]:
        _finding(findings, "sensitivity.winner_unstable", "medium", "The winner changes under declared weight perturbation; make the recommendation conditional.", "sensitivity_analysis")
    if uncertainty["winner_stable"] is False:
        _finding(findings, "uncertainty.winner_unstable", "medium", "The winner changes at a declared evidence interval corner; do not present selection as robust.", "uncertainty_analysis")
    return sensitivity, uncertainty


def _tradeoffs(ranked):
    if not ranked:
        return []
    winner = ranked[0]
    rows = []
    for other in ranked[1:]:
        advantages, disadvantages, deltas = [], [], []
        for cell in winner["cells"]:
            other_cell = next(x for x in other["cells"] if x["criterion"] == cell["criterion"])
            delta = cell["normalised"] - other_cell["normalised"]
            record = {"criterion": cell["criterion"], "winner_raw": cell["raw"], "other_plan_id": other["plan_id"],
                      "other_raw": other_cell["raw"], "normalised_difference": _round(delta),
                      "weighted_difference": _round(delta * cell["weight"]),
                      "winner_evidence": cell["evidence_refs"], "other_evidence": other_cell["evidence_refs"]}
            deltas.append(record)
            if delta > 1e-10:
                advantages.append(record)
            elif delta < -1e-10:
                disadvantages.append(record)
        rows.append({"winner": winner["plan_id"], "other": other["plan_id"],
                     "score_difference": _round(winner["score"] - other["score"]),
                     "winner_advantages": advantages, "winner_disadvantages": disadvantages,
                     "decisive_criteria": sorted(deltas, key=lambda x: (-abs(x["weighted_difference"]), x["criterion"]))})
    return rows


def _contract(result, spec):
    contract = spec.get("output_contract", {})
    if isinstance(contract, dict):
        keys = list(contract)
    elif isinstance(contract, list):
        keys = [x if isinstance(x, str) else x.get("field", x.get("name")) for x in contract if isinstance(x, (str, dict))]
        keys = [x for x in keys if isinstance(x, str)]
    else:
        keys = []
        result.setdefault("limits", []).append("output_contract was malformed; expected an object or field list")
    aliases = {"selected_plan": "recommendation", "choice": "recommendation", "recommended_plan": "recommendation",
               "comparison_matrix": "scoring_matrix", "matrix": "scoring_matrix", "weights": "criteria",
               "constraints": "constraint_results", "hard_gates": "constraint_results",
               "sensitivity": "sensitivity_analysis", "uncertainty": "uncertainty_analysis",
               "trade_offs": "tradeoffs", "fallback": "fallback_plan", "fallback_triggers": "fallback_plan",
               "versions": "plan_versions", "candidate_plans": "plan_versions", "sources": "evidence_matrix",
               "reading_result": "comparison_summary", "evidence_and_boundaries": "evidence_matrix",
               "changes": "change_records"}
    for key in keys:
        if key in result:
            if result[key] is None:
                result.setdefault("limits", []).append(f"engine returned null for output_contract field '{key}'; caller input cannot override an engine conclusion")
            continue
        alias = aliases.get(key)
        if alias and alias in result:
            result[key] = result[alias]
            if result[key] is None:
                result.setdefault("limits", []).append(f"engine returned null for output_contract field '{key}'; caller input cannot override an engine conclusion")
        elif key in spec and key != "output_contract" and spec[key] is not None:
            result[key] = copy.deepcopy(spec[key])
        else:
            result[key] = None
            result.setdefault("limits", []).append(f"output_contract field '{key}' was not derivable; returned null rather than inventing content")
    return result


def compare(spec):
    if not isinstance(spec, dict):
        raise SpecError("spec must be a JSON object")
    if "output_contract" in spec:
        contract = spec["output_contract"]
        valid_list = isinstance(contract, list) and all(isinstance(x, str) or (isinstance(x, dict) and isinstance(x.get("field", x.get("name")), str)) for x in contract)
        if not isinstance(contract, dict) and not valid_list:
            raise SpecError("output_contract must be an object or a list of field names/field descriptors")
    if not spec.get("case_id"): 
        raise SpecError("case_id is required")
    if not spec.get("objective"):
        raise SpecError("objective is required to fix the comparison target")
    raw_candidates = spec.get("candidate_plans")
    if not isinstance(raw_candidates, list) or len(raw_candidates) < 2:
        raise SpecError("candidate_plans must contain at least two versioned plans")
    findings = []
    criteria = _criteria(spec)
    if not spec.get("hard_constraints"):
        _finding(findings, "constraint.none_declared", "medium", "No hard constraints declared; weighted scores must not be interpreted as permission to execute.", "hard_constraints")
    sources = _source_index(spec)
    candidates, seen = [], set()
    for i, raw in enumerate(raw_candidates):
        if not isinstance(raw, dict):
            raise SpecError(f"candidate_plans[{i}] must be an object")
        pid = raw.get("plan_id", raw.get("id"))
        if not isinstance(pid, str) or not pid or pid in seen:
            raise SpecError(f"candidate_plans[{i}] needs a unique plan_id")
        seen.add(pid)
        plan = copy.deepcopy(_dict(raw.get("plan")) or {k: copy.deepcopy(v) for k, v in raw.items() if k not in ("plan_id", "id", "version", "changes", "based_on")})
        candidate = {"plan_id": pid, "version": str(raw.get("version") or plan.get("version") or f"v{i+1}"),
                     "based_on": raw.get("based_on"), "changes": copy.deepcopy(_list(raw.get("changes"))),
                     "plan": plan, "metrics": copy.deepcopy(_dict(plan.get("metrics"))),
                     "plan_sha256": _sha(plan)}
        candidate["uncertainties"] = _uncertainties(candidate, findings)
        candidate["total_cost"], candidate["cost_lines"], candidate["currency"] = _cost(candidate, findings)
        candidate["total_time_hours"], candidate["time_lines"] = _time(candidate, findings)
        if candidate["total_cost"] is not None:
            candidate["metrics"]["total_cost"] = candidate["total_cost"]
        if candidate["total_time_hours"] is not None:
            candidate["metrics"]["total_time_hours"] = candidate["total_time_hours"]
        candidate["constraint_results"] = _gates(spec, candidate, findings)
        statuses = [x["status"] for x in candidate["constraint_results"]]
        candidate["gate_status"] = "failed" if "failed" in statuses else ("unknown" if "unknown" in statuses else "passed")
        candidates.append(candidate)
    ranked, scoring_matrix, evidence_matrix = _build_scores(spec, candidates, criteria, findings, sources)
    sensitivity, uncertainty = _sensitivity(spec, ranked, criteria, findings)
    eligible_ids = [r["plan_id"] for r in ranked]
    constraint_results = [{"plan_id": c["plan_id"], "version": c["version"], "gate_status": c["gate_status"],
                           "constraints": copy.deepcopy(c["constraint_results"])} for c in candidates]
    eliminated = [{"plan_id": c["plan_id"], "version": c["version"], "gate_status": c["gate_status"],
                   "reasons": [{"constraint_id": x.get("id"), "metric": x.get("metric"), "actual": x.get("actual"),
                                "op": x.get("op"), "required": x.get("required"), "status": x.get("status"),
                                "source": x.get("source"), "uncertainty_gate": x.get("uncertainty_gate", False)}
                               for x in c["constraint_results"] if x.get("status") != "passed"]}
                  for c in candidates if c["plan_id"] not in eligible_ids]
    tradeoffs = _tradeoffs(ranked)
    fallback = None
    if len(ranked) >= 2:
        runner = ranked[1]
        triggers = copy.deepcopy(_list(spec.get("fallback_triggers")))
        for i, trigger in enumerate(triggers):
            if not isinstance(trigger, dict) or not trigger.get("trigger") or not trigger.get("action") or trigger.get("target_plan_id") not in seen:
                _finding(findings, "fallback.malformed", "high", "Fallback needs trigger, action and an existing target_plan_id.", f"fallback_triggers[{i}]")
        if not triggers:
            _finding(findings, "fallback.triggers_missing", "medium", "A runner-up exists but no concrete switch trigger is declared.", "fallback_triggers")
        fallback = {"plan_id": runner["plan_id"], "version": runner["version"], "score": runner["score"], "triggers": triggers,
                    "note": "Fallback is prospective; revalidate all gates at the time of switching."}
    elif ranked:
        _finding(findings, "fallback.no_runner_up", "medium", "Only one plan is eligible; declare a stop/redesign trigger rather than naming an unvalidated fallback.", "fallback_triggers")
    recommendation = None
    if ranked:
        winner = ranked[0]
        tied = len(ranked) > 1 and math.isclose(winner["score"], ranked[1]["score"], abs_tol=1e-8)
        if tied:
            _finding(findings, "recommendation.tie", "medium", "Top scores tie; stable plan_id ordering is reported but expert preference is required.", "recommendation")
        recommendation = {"plan_id": winner["plan_id"], "version": winner["version"], "score": winner["score"],
                          "selection_status": "recommended_for_review_not_execution",
                          "statement": f"Prospectively select {winner['plan_id']} ({winner['version']}): every evaluated hard gate passed and its declared weighted score is {winner['score']:.4f}/100. This is not evidence of measured experimental success.",
                          "tie": tied, "tradeoffs": tradeoffs,
                          "robust_to_weight_probe": sensitivity.get("winner_stable"),
                          "robust_to_declared_interval_probes": uncertainty.get("winner_stable"),
                          "evidence_boundary": "Recommendation inherits all source, scale, ordinal-score and uncertainty limitations; no experiment was executed."}
    else:
        _finding(findings, "compare.no_feasible_plan", "high", "No candidate passed every hard gate with complete criterion scores; stop and revise rather than selecting the least-bad failure.", "candidate_plans")
    high = any(f["severity"] == "high" for f in findings)
    status = "blocked" if high else ("review" if findings else "clean")
    if recommendation and status == "blocked":
        recommendation["selection_status"] = "blocked_by_findings_do_not_execute"
    result = {
        "schema_version": SCHEMA, "case_id": spec["case_id"], "mode": "aligned_plan_comparison_and_choice",
        "status": status, "objective": copy.deepcopy(spec["objective"]),
        "criteria": [{k: copy.deepcopy(v) for k, v in c.items() if not k.startswith("_")} for c in criteria],
        "plan_versions": [{"plan_id": c["plan_id"], "version": c["version"], "based_on": c["based_on"],
                           "changes": c["changes"], "plan_sha256": c["plan_sha256"]} for c in candidates],
        "constraint_results": constraint_results, "eliminated_plans": eliminated,
        "candidate_evaluations": [{"plan_id": c["plan_id"], "version": c["version"], "gate_status": c["gate_status"],
                                   "total_cost": c["total_cost"], "currency": c["currency"], "cost_items": c["cost_lines"],
                                   "total_time_hours": c["total_time_hours"], "time_items": c["time_lines"],
                                   "score": next((r["score"] for r in ranked if r["plan_id"] == c["plan_id"]), None),
                                   "rank": next((r["rank"] for r in ranked if r["plan_id"] == c["plan_id"]), None)} for c in candidates],
        "scoring_matrix": scoring_matrix, "evidence_matrix": evidence_matrix,
        "ranking": [{"rank": r["rank"], "plan_id": r["plan_id"], "version": r["version"], "score": r["score"]} for r in ranked],
        "tradeoffs": tradeoffs, "sensitivity_analysis": sensitivity, "uncertainty_analysis": uncertainty,
        "recommendation": recommendation, "fallback_plan": fallback,
        "pending_review": copy.deepcopy(_list(spec.get("pending_review"))),
        "change_records": copy.deepcopy(_list(spec.get("change_records"))) + [{"change": "aligned comparison run", "method": SCHEMA, "input_sha256": _sha(spec), "actual_experiment_executed": False}],
        "comparison_summary": {"candidates": len(candidates), "eligible": len(ranked), "eliminated_or_unknown": len(eliminated),
                               "winner": recommendation.get("plan_id") if recommendation else None,
                               "execution_status": "not_executed"},
        "findings": findings,
        "limits": copy.deepcopy(_list(spec.get("limits"))) + ["MCDA ranks declared values and weights; it does not prove scientific superiority, causality, safety, or future performance.",
                                                                  "Ordinal scores and scale bounds require domain-owner confirmation; arithmetic cannot validate their meaning.",
                                                                  "All recommendations are prospective and no experiment was executed."],
        "reproducibility": {"input_sha256": _sha(spec), "engine_schema": SCHEMA, "third_party_dependencies": [],
                            "algorithm": "hard gates -> declared-bound minmax -> weighted sum -> stable plan_id tie break -> weight and interval-corner probes",
                            "artifacts": ["result.json", "comparison_matrix.csv", "evidence_matrix.csv", "sensitivity.json", "recommendation.md", "change_records.json"],
                            "deterministic": True}
    }
    result["severity_counts"] = {s: sum(1 for f in findings if f["severity"] == s) for s in SEVERITIES}
    result["checked"] = {"candidates": len(candidates), "criteria": len(criteria),
                         "hard_constraints": len(_list(spec.get("hard_constraints"))),
                         "evidence_cells": len(evidence_matrix), "weight_scenarios": len(_list(sensitivity.get("scenarios"))),
                         "uncertainty_scenarios": len(_list(uncertainty.get("scenarios")))}
    result["run_state"] = {"exit_meaning": {"clean": 0, "review": 3, "blocked": 4, "undetermined": 5}[status],
                           "handoff": "Resolve high findings; confirm weights/scales and activate fallback only on its recorded trigger.",
                           "actual_experiment_executed": False}
    return _contract(result, spec)


def refusal(message, spec=None):
    spec = spec if isinstance(spec, dict) else {}
    result = {"schema_version": SCHEMA, "case_id": spec.get("case_id"), "mode": "aligned_plan_comparison_and_choice",
              "status": "undetermined", "recommendation": None,
              "findings": [{"rule": "spec.refused", "severity": "high", "message": message}],
              "severity_counts": {"high": 1, "medium": 0, "low": 0}, "checked": {},
              "limits": ["Structured refusal: no recommendation was invented from a malformed spec."],
              "run_state": {"exit_meaning": 5, "handoff": "Repair the named spec error and rerun.", "actual_experiment_executed": False}}
    return _contract(result, spec)
