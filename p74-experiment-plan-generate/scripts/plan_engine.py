"""Deterministic, provenance-aware experiment plan generation and revision.

Planning only: this module never executes an experiment and never invents a response.
"""
from __future__ import annotations

import copy
import hashlib
import itertools
import json
import math
import random
from decimal import Decimal, InvalidOperation
from statistics import NormalDist

SCHEMA = "experiment-plan-generate/v1"
SEVERITIES = ("high", "medium", "low")


class SpecError(ValueError):
    """A structured refusal, never an uncaught input-data exception."""


def _num(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def _list(value):
    return value if isinstance(value, list) else []


def _dict(value):
    return value if isinstance(value, dict) else {}


def _finding(findings, rule, severity, message, path=None, **locator):
    item = {"rule": rule, "severity": severity, "message": message}
    if path:
        item["path"] = path
    item.update({k: v for k, v in locator.items() if v is not None})
    findings.append(item)


def _sha(spec):
    return hashlib.sha256(json.dumps(spec, ensure_ascii=False, sort_keys=True,
                                     separators=(",", ":")).encode("utf-8")).hexdigest()


def _round(value):
    return round(float(value), 8) if _num(value) else value


def _source_ids(value):
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        return [x for x in value if isinstance(x, str)]
    return []


def _merge_plan(spec, candidate):
    base = copy.deepcopy(_dict(candidate.get("plan")))
    if not base:
        base = copy.deepcopy(_dict(spec.get("plan_template") or spec.get("plan")))
    for key, value in candidate.items():
        if key not in ("plan", "plan_id", "id", "version", "changes", "based_on"):
            base[key] = copy.deepcopy(value)
    return base


def _domain_levels(domain, cap):
    """Return explicit finite levels; decimal stepping avoids accumulated float drift."""
    if isinstance(domain, list):
        return copy.deepcopy(domain)
    if isinstance(domain, dict) and all(k in domain for k in ("min", "max", "step")):
        try:
            lo, hi, step = (Decimal(str(domain[k])) for k in ("min", "max", "step"))
        except (InvalidOperation, ValueError):
            raise SpecError("a numeric domain has non-numeric min/max/step")
        if step <= 0 or hi < lo:
            raise SpecError("a numeric domain must have step > 0 and max >= min")
        values, current = [], lo
        while current <= hi:
            if len(values) >= cap:
                raise SpecError("a numeric domain exceeds the finite-level safety cap")
            values.append(float(current))
            current += step
        return values
    raise SpecError("every factor needs an explicit levels list or finite {min,max,step} domain")


def _normalise_factors(raw_factors, cap=256):
    if not isinstance(raw_factors, list) or not raw_factors:
        raise SpecError("factors must be a non-empty list of finite parameter domains")
    factors, names = [], set()
    for index, raw in enumerate(raw_factors):
        if not isinstance(raw, dict) or not isinstance(raw.get("name"), str) or not raw["name"].strip():
            raise SpecError(f"factors[{index}] needs a non-empty name")
        name = raw["name"].strip()
        if name in names:
            raise SpecError(f"duplicate factor name: {name}")
        names.add(name)
        domain = raw.get("levels", raw.get("values", raw.get("domain")))
        levels = _domain_levels(domain, cap)
        if not levels:
            raise SpecError(f"factor '{name}' has an empty domain")
        parsed = []
        for level in levels:
            value = level.get("value") if isinstance(level, dict) else level
            if value is None or (isinstance(value, float) and not math.isfinite(value)):
                raise SpecError(f"factor '{name}' contains an invalid level")
            parsed.append({"value": copy.deepcopy(value),
                           "source": (level.get("source") if isinstance(level, dict) else raw.get("source")),
                           "rationale": (level.get("rationale") if isinstance(level, dict) else raw.get("rationale"))})
        item = copy.deepcopy(raw)
        item["name"] = name
        item["levels"] = parsed
        factors.append(item)
    combinations = math.prod(len(f["levels"]) for f in factors)
    return factors, combinations


def _sample_size(spec, plan, n_cells, findings):
    ss = _dict(plan.get("sample_size") or spec.get("sample_size"))
    design = _dict(plan.get("design") or spec.get("design"))
    reps = ss.get("n_per_cell", ss.get("biological_replicates", ss.get("replicates")))
    if not isinstance(reps, int) or isinstance(reps, bool) or reps < 1:
        _finding(findings, "sample_size.missing", "high",
                 "Declare a positive number of independent biological/experimental replicates per design cell.",
                 "sample_size.n_per_cell")
        reps = None
    technical = ss.get("technical_replicates", 1)
    if not isinstance(technical, int) or isinstance(technical, bool) or technical < 1:
        _finding(findings, "sample_size.technical_invalid", "high",
                 "technical_replicates must be a positive integer and does not increase independent n.",
                 "sample_size.technical_replicates")
        technical = None
    controls = design.get("control_runs_per_replication", 0)
    centers = design.get("center_points", 0)
    if not isinstance(controls, int) or controls < 0 or not isinstance(centers, int) or centers < 0:
        raise SpecError("control_runs_per_replication and center_points must be non-negative integers")
    control_conditions = design.get("control_conditions", [])
    center_values = design.get("center_values")
    if controls > 0 and (not isinstance(control_conditions, list) or len(control_conditions) != controls or not all(isinstance(x, dict) for x in control_conditions)):
        _finding(findings, "design.control_conditions_mismatch", "high",
                 "Declare exactly one design.control_conditions object per extra control run per replication.",
                 "design.control_conditions")
        control_conditions = []
    if centers > 0 and not isinstance(center_values, dict):
        _finding(findings, "design.center_values_missing", "high",
                 "Declare the actual center_values for each center-point run; never invent a midpoint.",
                 "design.center_values")
    total = n_cells * reps + (controls + centers) * reps if reps is not None else None
    measurements = total * technical if total is not None and technical is not None else None
    calculation = None
    required = None
    effect, sd = ss.get("minimum_effect"), ss.get("sd")
    alpha, power = ss.get("alpha", 0.05), ss.get("power", 0.8)
    if any(x is not None for x in (ss.get("minimum_effect"), ss.get("sd"))):
        if all(_num(x) for x in (effect, sd, alpha, power)) and effect > 0 and sd > 0 and 0 < alpha < 1 and 0 < power < 1:
            if n_cells != 2:
                _finding(findings, "sample_size.power_model_mismatch", "high",
                         "The built-in normal approximation is only for two independent groups; supply a domain-appropriate calculation for this design.",
                         "sample_size")
            else:
                dist = NormalDist()
                attrition = ss.get("attrition_rate", 0)
                if not _num(attrition) or not 0 <= attrition < 1:
                    raise SpecError("sample_size.attrition_rate must be in [0,1)")
                raw_n = 2 * ((dist.inv_cdf(1 - alpha / 2) + dist.inv_cdf(power)) * sd / effect) ** 2
                required = math.ceil(raw_n)
                adjusted = math.ceil(required / (1 - attrition))
                calculation = {"method": "two_group_two_sided_normal_approximation",
                               "formula": "ceil(2*((z_(1-alpha/2)+z_power)*sd/minimum_effect)^2), then attrition adjustment",
                               "alpha": alpha, "power": power, "minimum_effect": effect,
                               "sd": sd, "attrition_rate": attrition,
                               "n_per_group_before_attrition": required,
                               "n_per_group_after_attrition": adjusted,
                               "source": ss.get("basis") or ss.get("source")}
                if reps is not None and reps < adjusted:
                    _finding(findings, "sample_size.underpowered", "high",
                             f"Declared n={reps} is below the calculated attrition-adjusted n={adjusted} per group.",
                             "sample_size.n_per_cell", calculated_n=adjusted)
        else:
            _finding(findings, "sample_size.power_inputs_invalid", "high",
                     "Power calculation needs positive minimum_effect/sd and valid alpha/power.",
                     "sample_size")
    if reps is not None and not (ss.get("basis") or calculation):
        _finding(findings, "sample_size.basis_missing", "medium",
                 "Record the power calculation, pilot, historical precision, or resource-constrained pilot rationale for n.",
                 "sample_size.basis")
    return {"experimental_unit": ss.get("experimental_unit"),
            "independent_n_per_cell": reps, "technical_replicates_per_run": technical,
            "design_cells": n_cells, "control_runs_per_replication": controls,
            "control_conditions": copy.deepcopy(control_conditions), "center_values": copy.deepcopy(center_values),
            "center_points": centers, "total_independent_runs": total,
            "total_measurements": measurements, "basis": ss.get("basis"),
            "power_calculation": calculation,
            "note": "Technical repeats are measurements, not independent experimental units."}


def _lookup(plan, metrics, path):
    if path in metrics:
        return metrics[path]
    current = plan
    for part in str(path).split("."):
        if not isinstance(current, dict) or part not in current:
            return None
        current = current[part]
    return current


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


def _cost(plan, spec, sample, findings):
    items = plan.get("cost_items", spec.get("cost_items", []))
    if not isinstance(items, list):
        raise SpecError("cost_items must be a list")
    if not items:
        return None, [], None
    total, currency, lines = 0.0, None, []
    for i, item in enumerate(items):
        if not isinstance(item, dict) or not all(_num(item.get(k)) for k in ("quantity", "unit_cost")):
            _finding(findings, "cost.invalid_item", "high",
                     "Each cost item needs numeric quantity and unit_cost.", f"cost_items[{i}]")
            return None, lines, currency
        basis = item.get("basis", "per_plan")
        multiplier = {"per_plan": 1, "per_run": sample["total_independent_runs"],
                      "per_measurement": sample["total_measurements"]}.get(basis)
        if multiplier is None:
            _finding(findings, "cost.unknown_multiplier", "high",
                     f"Cost basis '{basis}' cannot be calculated until independent n is known.", f"cost_items[{i}]")
            return None, lines, currency
        amount = item["quantity"] * item["unit_cost"] * multiplier
        item_currency = item.get("currency")
        if currency is None:
            currency = item_currency
        elif item_currency != currency:
            _finding(findings, "cost.currency_mixed", "high",
                     "Do not add unlike currencies; convert with a dated source first.", f"cost_items[{i}]")
            return None, lines, currency
        total += amount
        lines.append({"id": item.get("id", f"C{i+1}"), "kind": item.get("kind"),
                      "basis": basis, "quantity": item["quantity"], "unit": item.get("unit"),
                      "unit_cost": item["unit_cost"], "multiplier": multiplier,
                      "currency": item_currency, "amount": _round(amount),
                      "source": item.get("source"), "fixed_or_recurring": item.get("fixed_or_recurring", "recurring" if basis != "per_plan" else "fixed")})
    return _round(total), lines, currency


def _time(plan, spec, sample, findings):
    items = plan.get("time_items", spec.get("time_items", []))
    if not isinstance(items, list):
        raise SpecError("time_items must be a list")
    if not items:
        return None, []
    total, lines = 0.0, []
    for i, item in enumerate(items):
        if not isinstance(item, dict) or not _num(item.get("hours")) or item["hours"] < 0:
            _finding(findings, "time.invalid_item", "high", "Each time item needs non-negative numeric hours.", f"time_items[{i}]")
            return None, lines
        basis = item.get("basis", "per_plan")
        multiplier = {"per_plan": 1, "per_run": sample["total_independent_runs"]}.get(basis)
        probability = item.get("probability", 1)
        if multiplier is None or not _num(probability) or not 0 <= probability <= 1:
            _finding(findings, "time.invalid_multiplier", "high", "Time basis/probability is not calculable.", f"time_items[{i}]")
            return None, lines
        expected = item["hours"] * multiplier * probability
        total += expected
        lines.append({"id": item.get("id", f"T{i+1}"), "kind": item.get("kind", "execution"),
                      "basis": basis, "hours": item["hours"], "multiplier": multiplier,
                      "probability": probability, "expected_hours": _round(expected),
                      "source": item.get("source")})
    return _round(total), lines


def _constraints(spec, plan, metrics, factors):
    raw = _list(spec.get("hard_constraints")) + _list(plan.get("hard_constraints"))
    constraints = copy.deepcopy(raw)
    resources = _dict(plan.get("resources") or spec.get("resources"))
    budget = _dict(resources.get("budget"))
    if _num(budget.get("amount")):
        constraints.append({"id": "resource.budget", "metric": "total_cost", "op": "<=",
                            "value": budget["amount"], "unit": budget.get("currency"), "source": budget.get("source")})
    if _num(resources.get("time_window_hours")):
        constraints.append({"id": "resource.time", "metric": "total_time_hours", "op": "<=",
                            "value": resources["time_window_hours"], "unit": "h", "source": resources.get("source")})
    if _num(resources.get("sample_limit")):
        constraints.append({"id": "resource.samples", "metric": "total_independent_runs", "op": "<=",
                            "value": resources["sample_limit"], "unit": "independent runs", "source": resources.get("source")})
    equipment = {x.get("id"): x for x in _list(plan.get("equipment") or spec.get("equipment")) if isinstance(x, dict)}
    for factor in factors:
        eid = factor.get("equipment_id")
        if not eid:
            continue
        eq = _dict(equipment.get(eid))
        ranges = _dict(eq.get("parameter_ranges"))
        bounds = ranges.get(factor["name"], factor.get("equipment_range", eq.get("range")))
        if isinstance(bounds, list) and len(bounds) == 2 and all(_num(x) for x in bounds):
            for level in factor["levels"]:
                value = level["value"]
                if _num(value):
                    constraints.append({"id": f"equipment.{factor['name']}.{value}", "metric": "parameter." + factor["name"],
                                        "op": ">=", "value": bounds[0], "source": eq.get("source"), "equipment_id": eid})
                    constraints.append({"id": f"equipment.{factor['name']}.{value}", "metric": "parameter." + factor["name"],
                                        "op": "<=", "value": bounds[1], "source": eq.get("source"), "equipment_id": eid})
        else:
            constraints.append({"id": f"equipment.{factor['name']}.unknown", "metric": "parameter." + factor["name"],
                                "op": "==", "value": None, "source": eq.get("source"), "equipment_id": eid,
                                "missing_range": True})
    return constraints


def _gate(alternative, spec, plan, factors):
    values = dict(alternative["metrics"])
    for name, value in alternative["parameter_values"].items():
        values["parameter." + name] = value
    results = []
    for i, constraint in enumerate(_constraints(spec, plan, values, factors)):
        if not isinstance(constraint, dict):
            results.append({"id": f"constraint[{i}]", "status": "unknown", "reason": "malformed constraint"})
            continue
        metric = constraint.get("metric")
        actual = values.get(metric)
        expected = constraint.get("value")
        if constraint.get("missing_range"):
            actual = None
        passed = _compare(actual, constraint.get("op"), expected) if not constraint.get("missing_range") else None
        status = "unknown" if passed is None else ("passed" if passed else "failed")
        results.append({"id": constraint.get("id", f"constraint[{i}]"), "metric": metric,
                        "actual": actual, "op": constraint.get("op"), "required": expected,
                        "unit": constraint.get("unit"), "status": status,
                        "source": constraint.get("source"), "equipment_id": constraint.get("equipment_id")})
    return results


def _criteria(spec, plan):
    optimisation = _dict(spec.get("optimization") or plan.get("optimization"))
    criteria = optimisation.get("criteria", spec.get("criteria", []))
    if not isinstance(criteria, list):
        raise SpecError("optimization.criteria must be a list")
    parsed = []
    for i, c in enumerate(criteria):
        if not isinstance(c, dict) or not isinstance(c.get("name"), str) or not _num(c.get("weight")) or c["weight"] < 0:
            raise SpecError(f"criterion[{i}] needs name and non-negative numeric weight")
        direction = c.get("direction", "max")
        if direction not in ("min", "max"):
            raise SpecError(f"criterion '{c['name']}' direction must be min or max")
        item = copy.deepcopy(c)
        item["direction"] = direction
        parsed.append(item)
    if parsed and sum(c["weight"] for c in parsed) <= 0:
        raise SpecError("at least one optimisation criterion weight must be positive")
    total = sum(c["weight"] for c in parsed) or 1
    for c in parsed:
        c["original_weight"] = c["weight"]
        c["weight"] = c["weight"] / total
    return parsed, optimisation


def _normalise(value, criterion, observed):
    bounds = criterion.get("scale_bounds")
    if not (isinstance(bounds, list) and len(bounds) == 2 and all(_num(x) for x in bounds) and bounds[1] > bounds[0]):
        lo, hi = min(observed), max(observed)
        bounds = [lo, hi]
    else:
        lo, hi = bounds
    if hi == lo:
        return 1.0, bounds, "constant criterion; no discrimination among alternatives"
    clipped = min(max(value, lo), hi)
    score = (clipped - lo) / (hi - lo)
    if criterion["direction"] == "min":
        score = 1 - score
    return score, bounds, "clipped to declared scale" if value < lo or value > hi else None


def _rank_scored(rows, criteria):
    ranked = sorted(rows, key=lambda r: (-r["score"], r["plan_id"], r["design_id"]))
    for rank, row in enumerate(ranked, 1):
        row["rank"] = rank
    return ranked


def _score(alternatives, criteria, findings):
    if not criteria:
        return [], [], {"assessed": False, "reason": "no criteria declared"}
    rows, matrix = [], []
    for alt in alternatives:
        cells, total, missing = [], 0.0, False
        for criterion in criteria:
            name = criterion["name"]
            raw = alt["metrics"].get(name)
            observed = [a["metrics"].get(name) for a in alternatives if _num(a["metrics"].get(name))]
            if not _num(raw) or not observed:
                _finding(findings, "criterion.value_missing", "high",
                         f"Alternative {alt['design_id']} lacks numeric criterion '{name}'.",
                         f"alternatives.{alt['design_id']}.metrics.{name}")
                missing = True
                continue
            norm, bounds, note = _normalise(raw, criterion, observed)
            refs = _source_ids(_dict(alt["plan"].get("evidence")).get(name))
            if name in ("total_cost", "total_time_hours"):
                refs += [x.get("source") for x in alt["cost_lines"] + alt["time_lines"] if x.get("source")]
            refs = list(dict.fromkeys(refs))
            rationale = _dict(alt["plan"].get("rationales")).get(name) or criterion.get("rationale")
            cells.append({"criterion": name, "raw": raw, "unit": criterion.get("unit"),
                          "direction": criterion["direction"], "scale_bounds": bounds,
                          "normalised": _round(norm), "weight": _round(criterion["weight"]),
                          "weighted": _round(norm * criterion["weight"]),
                          "evidence_refs": refs, "rationale": rationale, "note": note})
            if not refs:
                _finding(findings, "criterion.evidence_missing", "medium",
                         f"Alternative {alt['design_id']} criterion '{name}' has no source reference.",
                         f"alternatives.{alt['design_id']}.evidence.{name}")
            if not rationale:
                _finding(findings, "criterion.rationale_missing", "medium",
                         f"Explain the raw score for {alt['design_id']} / {name}.",
                         f"alternatives.{alt['design_id']}.rationales.{name}")
            total += norm * criterion["weight"]
        if not missing:
            rows.append({"plan_id": alt["plan_id"], "design_id": alt["design_id"],
                         "score": _round(total * 100), "cells": cells})
            matrix.extend([{"plan_id": alt["plan_id"], "design_id": alt["design_id"], **cell} for cell in cells])
    ranked = _rank_scored(rows, criteria)
    sensitivity = []
    if ranked:
        base_winner = ranked[0]["design_id"]
        for i, criterion in enumerate(criteria):
            for factor in (0.8, 1.2):
                modified = copy.deepcopy(criteria)
                modified[i]["weight"] = criterion["weight"] * factor
                sw = sum(c["weight"] for c in modified) or 1
                for c in modified:
                    c["weight"] /= sw
                reranked = []
                for alt in alternatives:
                    row = next((r for r in rows if r["design_id"] == alt["design_id"]), None)
                    if row is None:
                        continue
                    score = 0.0
                    for c in modified:
                        cell = next(x for x in row["cells"] if x["criterion"] == c["name"])
                        score += cell["normalised"] * c["weight"]
                    reranked.append({"design_id": alt["design_id"], "plan_id": alt["plan_id"], "score": _round(score * 100)})
                reranked = _rank_scored(reranked, modified)
                sensitivity.append({"scenario": "one_at_a_time_weight", "criterion": criterion["name"],
                                    "multiplier": factor, "winner": reranked[0]["design_id"],
                                    "base_winner": base_winner, "winner_changed": reranked[0]["design_id"] != base_winner,
                                    "ranking": [{"design_id": r["design_id"], "score": r["score"]} for r in reranked]})
    robust = bool(ranked) and not any(x["winner_changed"] for x in sensitivity)
    return ranked, matrix, {"assessed": True, "method": "one-at-a-time criterion weight +/-20%, other weights proportionally renormalised",
                            "scenarios": sensitivity, "stable_winner": robust}


def _audit_plan(plan, selected, spec, sample, findings):
    hypotheses = _list(plan.get("hypotheses") or spec.get("hypotheses"))
    variables = _list(plan.get("variables") or spec.get("variables"))
    controls = _list(plan.get("controls") or spec.get("controls"))
    if not hypotheses:
        _finding(findings, "hypothesis.missing", "high", "State at least one falsifiable hypothesis.", "hypotheses")
    for i, h in enumerate(hypotheses):
        if not isinstance(h, dict) or not all(h.get(k) for k in ("statement", "primary_outcome", "falsification")):
            _finding(findings, "hypothesis.not_falsifiable", "high", "Hypothesis needs statement, primary_outcome and falsification condition.", f"hypotheses[{i}]")
    roles = set()
    for i, v in enumerate(variables):
        if not isinstance(v, dict):
            _finding(findings, "variable.malformed", "high", "Variable must be an object.", f"variables[{i}]")
            continue
        role = v.get("role")
        roles.add(role)
        if not v.get("name") or not role or not (v.get("operational_definition") or v.get("definition")):
            _finding(findings, "variable.undefined", "high", "Variable needs name, role and operational definition.", f"variables[{i}]")
        if role in ("dependent", "outcome", "primary_outcome") and not v.get("measurement"):
            _finding(findings, "variable.measurement_missing", "high", "Outcome variable needs measurement method and instrument.", f"variables[{i}]")
        if role in ("confounder", "covariate") and not v.get("control_strategy"):
            _finding(findings, "variable.confounder_uncontrolled", "medium", "Declare how this confounder is measured and controlled.", f"variables[{i}]")
    if not roles.intersection({"independent", "factor", "exposure"}):
        _finding(findings, "variable.independent_missing", "high", "Declare at least one independent variable/factor.", "variables")
    if not roles.intersection({"dependent", "outcome", "primary_outcome"}):
        _finding(findings, "variable.outcome_missing", "high", "Declare at least one dependent/outcome variable.", "variables")
    if not controls:
        _finding(findings, "control.missing", "high", "Provide controls matched to the hypothesis; explain if no positive control is scientifically applicable.", "controls")
    for i, c in enumerate(controls):
        if not isinstance(c, dict) or not all(c.get(k) for k in ("type", "purpose", "excludes_confounder", "condition")):
            _finding(findings, "control.incomplete", "high", "Control needs type, purpose, excluded confounder and condition.", f"controls[{i}]")
    randomisation = _dict(plan.get("randomization") or plan.get("randomisation") or spec.get("randomization") or spec.get("randomisation"))
    if randomisation.get("method") in (None, "") or (randomisation.get("method") != "not_applicable" and not isinstance(randomisation.get("seed"), int)):
        _finding(findings, "randomization.incomplete", "medium", "Declare allocation/run-order method and integer seed, or not_applicable with rationale.", "randomization")
    if randomisation.get("method") == "not_applicable" and not randomisation.get("rationale"):
        _finding(findings, "randomization.rationale_missing", "medium", "Explain why randomization is not applicable.", "randomization.rationale")
    blinding = _dict(plan.get("blinding") or spec.get("blinding"))
    if not blinding.get("status") or (blinding.get("status") in ("none", "not_feasible") and not blinding.get("rationale")):
        _finding(findings, "blinding.incomplete", "medium", "Declare who is blinded and coding/unblinding procedure, or why blinding is not feasible.", "blinding")
    steps = _list(plan.get("steps") or spec.get("steps"))
    if not steps:
        _finding(findings, "steps.missing", "high", "Provide executable, ordered protocol steps.", "steps")
    ids = {s.get("id") for s in steps if isinstance(s, dict) and s.get("id")}
    for i, s in enumerate(steps):
        if not isinstance(s, dict) or not s.get("id") or not s.get("action"):
            _finding(findings, "steps.incomplete", "high", "Step needs id and concrete action.", f"steps[{i}]")
            continue
        if not s.get("acceptance_criteria") or not s.get("failure_action"):
            _finding(findings, "steps.decision_missing", "high", "Each step needs acceptance criteria and failure action.", f"steps[{i}]")
        for dep in _list(s.get("depends_on")):
            if dep not in ids:
                _finding(findings, "steps.unknown_dependency", "high", f"Unknown dependency '{dep}'.", f"steps[{i}].depends_on")
    # Kahn cycle check; deterministic and independent of input ordering.
    remaining = {s.get("id"): set(_list(s.get("depends_on"))) for s in steps if isinstance(s, dict) and s.get("id")}
    done = set()
    while remaining:
        ready = sorted(k for k, deps in remaining.items() if deps <= done)
        if not ready:
            _finding(findings, "steps.dependency_cycle", "high", "Step dependency graph contains a cycle.", "steps")
            break
        for key in ready:
            done.add(key)
            remaining.pop(key)
    for kind in ("materials", "equipment"):
        items = _list(plan.get(kind) or spec.get(kind))
        if not items:
            _finding(findings, f"{kind}.missing", "high", f"List required {kind} with specifications and provenance.", kind)
        for i, item in enumerate(items):
            if not isinstance(item, dict) or not item.get("name") or not item.get("source") or not item.get("state"):
                _finding(findings, f"{kind}.provenance_missing", "high", "Resource needs name, source and present/missing/partial state.", f"{kind}[{i}]")
            if isinstance(item, dict) and item.get("state") in ("missing", "partial"):
                _finding(findings, f"{kind}.unavailable", "high", "Resolve missing/partial resource before execution; keep plan on hold.", f"{kind}[{i}].state")
    stats = _dict(plan.get("statistical_plan") or spec.get("statistical_plan"))
    for key in ("primary_outcome", "test", "alpha", "missing_data", "exclusion_criteria", "software"):
        if stats.get(key) is None:
            _finding(findings, "statistics.incomplete", "high", f"Statistical plan lacks {key}.", f"statistical_plan.{key}")
    if sample["design_cells"] > 2 and not stats.get("multiple_comparisons"):
        _finding(findings, "statistics.multiplicity_missing", "high", "Declare multiplicity control for this multi-cell design.", "statistical_plan.multiple_comparisons")
    thresholds = _list(plan.get("decision_thresholds") or spec.get("decision_thresholds"))
    if not thresholds:
        _finding(findings, "threshold.missing", "high", "Predeclare quantitative success/stop thresholds and both actions.", "decision_thresholds")
    for i, t in enumerate(thresholds):
        if not isinstance(t, dict) or not all(k in t for k in ("metric", "op", "value", "source", "action_if_met", "action_if_not_met")):
            _finding(findings, "threshold.incomplete", "high", "Threshold needs metric, op, value, source and both actions.", f"decision_thresholds[{i}]")
    risks = _list(plan.get("risks") or spec.get("risks"))
    if not risks:
        _finding(findings, "risk.missing", "high", "Predeclare failure modes and fallback paths.", "risks")
    for i, r in enumerate(risks):
        if not isinstance(r, dict) or not all(r.get(k) for k in ("trigger", "consequence", "mitigation", "fallback", "stop_rule")):
            _finding(findings, "risk.incomplete", "high", "Risk needs trigger, consequence, mitigation, fallback and stop rule.", f"risks[{i}]")
    safety = _dict(plan.get("safety") or spec.get("safety"))
    ethics = _dict(plan.get("ethics") or spec.get("ethics"))
    for name, block in (("safety", safety), ("ethics", ethics)):
        if not block.get("status"):
            _finding(findings, f"{name}.status_missing", "high", f"Declare {name} status and review boundary.", name)
        if block.get("status") in ("pending", "required_not_approved"):
            _finding(findings, f"{name}.approval_pending", "high", "Plan may be reviewed but execution remains on hold pending approval.", name)
        if block.get("status") == "not_required" and not block.get("rationale"):
            _finding(findings, f"{name}.rationale_missing", "medium", "Record why approval is not required.", name)


def _schedule(steps, parameter_values):
    resolved, schedule, ends = [], [], {}
    for i, original in enumerate(steps):
        step = copy.deepcopy(original) if isinstance(original, dict) else {"id": f"step_{i+1}", "action": None}
        bindings = _list(step.get("parameter_bindings"))
        values = []
        for binding in bindings:
            name = binding.get("factor") if isinstance(binding, dict) else binding
            if name in parameter_values:
                values.append({"name": name, "value": copy.deepcopy(parameter_values[name]),
                               "unit": binding.get("unit") if isinstance(binding, dict) else None})
        step["resolved_parameters"] = values
        resolved.append(step)
    # Repeated relaxation gives deterministic earliest-start schedule for a DAG.
    for _ in range(len(resolved) + 1):
        changed = False
        for step in resolved:
            sid = step.get("id")
            if sid in ends or not isinstance(step.get("duration_minutes"), (int, float)):
                continue
            deps = _list(step.get("depends_on"))
            if all(dep in ends for dep in deps):
                start = max([ends[dep][1] for dep in deps] or [0])
                end = start + step["duration_minutes"]
                ends[sid] = (start, end)
                schedule.append({"step_id": sid, "start_minute": start, "end_minute": end,
                                 "depends_on": deps})
                changed = True
        if not changed:
            break
    schedule.sort(key=lambda x: (x["start_minute"], x["step_id"]))
    return resolved, schedule


def _run_order(matrix, randomisation):
    rows = copy.deepcopy(matrix)
    seed = randomisation.get("seed")
    if randomisation.get("method") and randomisation.get("method") != "not_applicable" and isinstance(seed, int):
        random.Random(seed).shuffle(rows)
        randomised = True
    else:
        randomised = False
    for order, row in enumerate(rows, 1):
        row["run_order"] = order
    return rows, randomised


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
    aliases = {
        "experiment_plan": "selected_plan", "experimental_plan": "selected_plan", "final_plan": "selected_plan",
        "optimized_plan": "selected_plan", "optimised_plan": "selected_plan", "plan": "selected_plan",
        "candidate_plans": "plan_versions", "versions": "plan_versions", "design": "design_matrix",
        "evidence": "evidence_and_boundaries", "confirmation_items": "pending_review",
        "uncertainty": "uncertainties", "changes": "change_records", "sources": "evidence_and_boundaries",
        "reading_result": "plan_summary", "results": "selected_plan"
    }
    limits = result.setdefault("limits", [])
    for key in keys:
        if key in result:
            if result[key] is None:
                limits.append(f"engine returned null for output_contract field '{key}'; caller input cannot override an engine conclusion")
            continue
        alias = aliases.get(key)
        if alias and alias in result:
            result[key] = result[alias]
            if result[key] is None:
                limits.append(f"engine returned null for output_contract field '{key}'; caller input cannot override an engine conclusion")
        elif key in spec and key != "output_contract" and spec[key] is not None:
            result[key] = copy.deepcopy(spec[key])
        else:
            result[key] = None
            limits.append(f"output_contract field '{key}' was not derivable; returned null rather than inventing content")
    return result


def generate(spec):
    if not isinstance(spec, dict):
        raise SpecError("spec must be a JSON object")
    if "output_contract" in spec:
        contract = spec["output_contract"]
        valid_list = isinstance(contract, list) and all(isinstance(x, str) or (isinstance(x, dict) and isinstance(x.get("field", x.get("name")), str)) for x in contract)
        if not isinstance(contract, dict) and not valid_list:
            raise SpecError("output_contract must be an object or a list of field names/field descriptors")
    if not spec.get("case_id"): 
        raise SpecError("case_id is required so the result remains traceable")
    if not spec.get("objective"):
        raise SpecError("objective is required; do not infer a research objective from a filename")
    candidates = spec.get("candidate_plans")
    if candidates is None:
        candidates = [{"plan_id": "P1", "version": "v1", "plan": spec.get("plan_template") or spec.get("plan")}]
    if not isinstance(candidates, list) or not candidates:
        raise SpecError("candidate_plans must be a non-empty list (one plan is enough, three versioned plans are supported)")
    findings = []
    raw_factors = spec.get("factors")
    if raw_factors is None and isinstance(spec.get("plan_template"), dict):
        raw_factors = spec["plan_template"].get("factors")
    max_combinations = _dict(spec.get("optimization")).get("max_combinations", 256)
    if not isinstance(max_combinations, int) or not 1 <= max_combinations <= 1024:
        raise SpecError("optimization.max_combinations must be an integer in [1,1024]")
    factors, n_combinations = _normalise_factors(raw_factors, max_combinations)
    if n_combinations > max_combinations:
        raise SpecError(f"full factorial needs {n_combinations} cells, above declared max_combinations={max_combinations}; narrow the recorded finite domain or use a separately justified design")
    alternatives, versions = [], []
    for ci, candidate in enumerate(candidates):
        if not isinstance(candidate, dict):
            _finding(findings, "candidate.malformed", "high", "Candidate plan must be an object.", f"candidate_plans[{ci}]")
            continue
        pid = str(candidate.get("plan_id") or candidate.get("id") or f"P{ci+1}")
        version = str(candidate.get("version") or f"v{ci+1}")
        plan = _merge_plan(spec, candidate)
        versions.append({"plan_id": pid, "version": version, "based_on": candidate.get("based_on"),
                         "changes": copy.deepcopy(_list(candidate.get("changes"))),
                         "source": candidate.get("source")})
        sample = _sample_size(spec, plan, n_combinations, findings)
        total_cost, cost_lines, currency = _cost(plan, spec, sample, findings)
        total_time, time_lines = _time(plan, spec, sample, findings)
        metrics = copy.deepcopy(_dict(plan.get("metrics")))
        metrics.update({"total_cost": total_cost, "total_time_hours": total_time,
                        "total_independent_runs": sample["total_independent_runs"],
                        "n_design_cells": n_combinations})
        for combo_index, combination in enumerate(itertools.product(*[f["levels"] for f in factors]), 1):
            values = {f["name"]: copy.deepcopy(level["value"]) for f, level in zip(factors, combination)}
            parameter_values = dict(values)
            metric_values = dict(metrics)
            for name, value in values.items():
                metric_values["parameter." + name] = value
            design_id = f"{pid}-D{combo_index:03d}"
            alt = {"plan_id": pid, "source_version": version, "design_id": design_id,
                   "plan": plan, "parameter_values": parameter_values,
                   "parameters": [{"name": f["name"], "value": copy.deepcopy(level["value"]),
                                   "unit": f.get("unit"), "source": level.get("source"),
                                   "rationale": level.get("rationale"), "equipment_id": f.get("equipment_id")}
                                  for f, level in zip(factors, combination)],
                   "sample_size": sample, "metrics": metric_values,
                   "total_cost": total_cost, "currency": currency, "cost_lines": cost_lines,
                   "total_time_hours": total_time, "time_lines": time_lines}
            alt["constraint_results"] = _gate(alt, spec, plan, factors)
            statuses = [x["status"] for x in alt["constraint_results"]]
            alt["gate_status"] = "failed" if "failed" in statuses else ("unknown" if "unknown" in statuses else "passed")
            alternatives.append(alt)
    if not alternatives:
        raise SpecError("no usable candidate plan could be constructed")
    # A candidate is eligible only if its ENTIRE full-factorial design is feasible.
    # We rank versioned designs, never a single cherry-picked cell from a factorial.
    grouped = {}
    for alternative in alternatives:
        grouped.setdefault(alternative["plan_id"], []).append(alternative)
    eligible = []
    for pid in sorted(grouped):
        members = grouped[pid]
        statuses = [m["gate_status"] for m in members]
        if any(s == "failed" for s in statuses):
            continue
        representative = copy.deepcopy(members[0])
        representative["design_id"] = f"{pid}-FF"
        representative["member_design_ids"] = [m["design_id"] for m in members]
        representative["gate_status"] = "unknown" if "unknown" in statuses else "passed"
        representative["constraint_results"] = [dict(item, design_id=m["design_id"])
                                                   for m in members for item in m["constraint_results"]]
        representative["parameter_values"] = {f["name"]: [copy.deepcopy(level["value"]) for level in f["levels"]]
                                                for f in factors}
        representative["parameters"] = [{"name": f["name"], "unit": f.get("unit"),
                                          "source": f.get("source"), "rationale": f.get("rationale"),
                                          "equipment_id": f.get("equipment_id"),
                                          "levels": copy.deepcopy(f["levels"])} for f in factors]
        if representative["gate_status"] == "passed":
            eligible.append(representative)
    criteria, optimisation = _criteria(spec, eligible[0]["plan"] if eligible else alternatives[0]["plan"])
    if not criteria:
        _finding(findings, "optimize.criteria_missing", "medium",
                 "No preference criteria declared; first feasible design is selected by stable ID, not called scientifically optimal.",
                 "optimization.criteria")
    for criterion in criteria:
        if not criterion.get("scale_bounds"):
            _finding(findings, "criterion.bounds_derived", "medium",
                     f"Criterion '{criterion['name']}' has no declared scale_bounds; observed eligible min/max will be used and may cause rank reversal.",
                     f"optimization.criteria.{criterion['name']}.scale_bounds")
    ranked, scoring_matrix, sensitivity = _score(eligible, criteria, findings)
    selected = None
    if ranked:
        winner_id = ranked[0]["design_id"]
        selected = next(a for a in eligible if a["design_id"] == winner_id)
    elif eligible and not criteria:
        selected = sorted(eligible, key=lambda a: (a["plan_id"], a["design_id"]))[0]
    if selected is None:
        _finding(findings, "optimize.no_feasible_plan", "high",
                 "No candidate/design cell passed every hard constraint with a complete score; revise resources or domains with expert approval.",
                 "candidate_plans")
        result = {"schema_version": SCHEMA, "case_id": spec["case_id"], "mode": "generate_and_revise_plan",
                  "status": "blocked", "objective": copy.deepcopy(spec["objective"]),
                  "selected_plan": None, "plan_versions": versions,
                  "candidate_summaries": [{k: a[k] for k in ("plan_id", "source_version", "design_id", "parameter_values", "gate_status", "constraint_results")} for a in alternatives],
                  "scoring_matrix": scoring_matrix, "sensitivity_analysis": sensitivity,
                  "findings": findings, "limits": ["No executable plan selected; all failures remain explicit."]}
    else:
        plan = selected["plan"]
        _audit_plan(plan, selected, spec, selected["sample_size"], findings)
        # Materialise every factorial cell, then every independent replicate.
        matrix = []
        for cell, combination in enumerate(itertools.product(*[f["levels"] for f in factors]), 1):
            values = {f["name"]: copy.deepcopy(level["value"]) for f, level in zip(factors, combination)}
            matrix.append({"design_id": f"{selected['plan_id']}-D{cell:03d}", "cell": cell, **values})
        expanded = []
        reps = selected["sample_size"]["independent_n_per_cell"]
        if reps is not None:
            for row in matrix:
                for replicate in range(1, reps + 1):
                    expanded.append({**copy.deepcopy(row), "independent_replicate": replicate,
                                     "run_id": f"{row['design_id']}-C{row['cell']:02d}-R{replicate:02d}"})
            for replicate in range(1, reps + 1):
                for index, condition in enumerate(selected["sample_size"].get("control_conditions") or [], 1):
                    expanded.append({"design_id": f"{selected['plan_id']}-CTRL{index:02d}", "cell": "control",
                                     "control_index": index, **copy.deepcopy(condition),
                                     "independent_replicate": replicate,
                                     "run_id": f"{selected['plan_id']}-CTRL{index:02d}-R{replicate:02d}"})
                for index in range(1, selected["sample_size"]["center_points"] + 1):
                    center_values = selected["sample_size"].get("center_values")
                    if isinstance(center_values, dict):
                        expanded.append({"design_id": f"{selected['plan_id']}-CENTER{index:02d}", "cell": "center",
                                         "center_index": index, **copy.deepcopy(center_values),
                                         "independent_replicate": replicate,
                                         "run_id": f"{selected['plan_id']}-CENTER{index:02d}-R{replicate:02d}"})
        randomisation = _dict(plan.get("randomization") or plan.get("randomisation") or spec.get("randomization") or spec.get("randomisation"))
        ordered, randomised = _run_order(expanded, randomisation)
        steps = _list(plan.get("steps") or spec.get("steps"))
        resolved_steps, step_schedule = _schedule(steps, selected["parameter_values"])
        safety = copy.deepcopy(_dict(plan.get("safety") or spec.get("safety")))
        ethics = copy.deepcopy(_dict(plan.get("ethics") or spec.get("ethics")))
        execution_hold = any(f["rule"] in ("safety.approval_pending", "ethics.approval_pending", "materials.unavailable", "equipment.unavailable") for f in findings)
        selected_plan = {
            "plan_id": selected["plan_id"], "source_version": selected["source_version"],
            "design_id": selected["design_id"], "lifecycle": "planned_not_executed",
            "execution_gate": "HOLD" if execution_hold else "REVIEW_BEFORE_EXECUTION",
            "objective": copy.deepcopy(spec["objective"]),
            "hypotheses": copy.deepcopy(_list(plan.get("hypotheses") or spec.get("hypotheses"))),
            "variables": copy.deepcopy(_list(plan.get("variables") or spec.get("variables"))),
            "controls": copy.deepcopy(_list(plan.get("controls") or spec.get("controls"))),
            "parameters": copy.deepcopy(selected["parameters"]),
            "sample_size": copy.deepcopy(selected["sample_size"]),
            "randomization": {**copy.deepcopy(randomisation), "run_order_generated": randomised},
            "blinding": copy.deepcopy(_dict(plan.get("blinding") or spec.get("blinding"))),
            "steps": resolved_steps, "materials": copy.deepcopy(_list(plan.get("materials") or spec.get("materials"))),
            "equipment": copy.deepcopy(_list(plan.get("equipment") or spec.get("equipment"))),
            "schedule": {"steps": step_schedule, "time_items": copy.deepcopy(selected["time_lines"]),
                         "total_expected_hours": selected["total_time_hours"],
                         "includes_preparation_queue_and_rework": True},
            "cost": {"total": selected["total_cost"], "currency": selected["currency"],
                     "items": copy.deepcopy(selected["cost_lines"]),
                     "formula": "sum(quantity * unit_cost * basis_multiplier); no unlike currencies added"},
            "statistical_plan": copy.deepcopy(_dict(plan.get("statistical_plan") or spec.get("statistical_plan"))),
            "decision_thresholds": copy.deepcopy(_list(plan.get("decision_thresholds") or spec.get("decision_thresholds"))),
            "risks": copy.deepcopy(_list(plan.get("risks") or spec.get("risks"))),
            "safety": safety, "ethics": ethics,
            "constraint_results": copy.deepcopy(selected["constraint_results"]),
            "selection_score": next((r["score"] for r in ranked if r["design_id"] == selected["design_id"]), None),
            "selection_basis": "weighted declared criteria after hard-constraint gate" if criteria else "first feasible stable ID; preference criteria absent",
            "measured_response_claimed": False
        }
        high = sum(1 for f in findings if f["severity"] == "high")
        status = "blocked" if high else ("review" if findings else "clean")
        result = {
            "schema_version": SCHEMA, "case_id": spec["case_id"], "mode": "generate_and_revise_plan",
            "status": status, "objective": copy.deepcopy(spec["objective"]),
            "selected_plan": selected_plan, "plan_versions": versions,
            "candidate_summaries": [{k: copy.deepcopy(a[k]) for k in ("plan_id", "source_version", "design_id", "parameter_values", "gate_status", "constraint_results")} for a in alternatives],
            "design_matrix": ordered, "scoring_matrix": scoring_matrix,
            "ranking": [{k: r[k] for k in ("rank", "plan_id", "design_id", "score")} for r in ranked],
            "sensitivity_analysis": sensitivity,
            "optimization_loop": {"method": "explicit finite full factorial (Cartesian product) -> hard gates -> declared weighted-sum normalisation -> prospective validation",
                                  "design_cells_per_plan": n_combinations, "max_combinations": max_combinations,
                                  "selection_is_prospective": True, "winner_stable_under_weight_probe": sensitivity.get("stable_winner") if sensitivity.get("assessed") else None,
                                  "next_iteration": {"required_input": "actual run-level observations linked by run_id",
                                                     "actions": ["check preregistered thresholds", "estimate effects with uncertainty", "revise only recorded parameter domains", "create a new source_version and rerun"],
                                                     "actual_results_executed": False}},
            "change_records": copy.deepcopy(_list(next((c for c in candidates if isinstance(c, dict) and str(c.get("plan_id") or c.get("id")) == selected["plan_id"]), {}).get("changes"))) + [{"change": "materialised selected finite full-factorial design", "source_version": selected["source_version"], "design_id": selected["design_id"], "parameters": copy.deepcopy(selected["parameter_values"])}],
            "evidence_and_boundaries": {"sources": copy.deepcopy(spec.get("sources", [])), "assumptions": copy.deepcopy(spec.get("assumptions", [])),
                                        "scoring_cells": scoring_matrix,
                                        "boundary": "Planning arithmetic and declared evidence only; not a vendor quote, safety approval, ethics approval, or measured future response."},
            "pending_review": copy.deepcopy(spec.get("pending_review", [])),
            "uncertainties": copy.deepcopy(spec.get("uncertainties", [])),
            "plan_summary": {"selected_plan_id": selected["plan_id"], "design_id": selected["design_id"],
                             "n_design_cells": n_combinations, "n_candidate_versions": len(versions),
                             "execution_status": "not_executed"},
            "findings": findings,
            "limits": copy.deepcopy(_list(spec.get("limits"))) + ["The engine validates declared structure/arithmetic, not scientific adequacy or regulatory approval.",
                                                                     "No experiment was run; selection and predicted metrics are prospective."],
            "reproducibility": {"input_sha256": _sha(spec), "engine_schema": SCHEMA,
                                "algorithm": "itertools.product in declared factor order; stable sort by score/design_id; seeded random.Random for run order",
                                "python_requires": "3.9+", "third_party_dependencies": [],
                                "artifacts": ["result.json", "plan.md", "design_matrix.csv", "change_records.json"],
                                "deterministic": True}
        }
    counts = {s: sum(1 for f in result.get("findings", []) if f.get("severity") == s) for s in SEVERITIES}
    result["severity_counts"] = counts
    result["checked"] = {"candidate_versions": len(result.get("plan_versions", [])),
                         "design_alternatives": len(result.get("candidate_summaries", [])),
                         "rules": sorted({f["rule"] for f in result.get("findings", [])})}
    result["run_state"] = {"exit_meaning": {"clean": 0, "review": 3, "blocked": 4, "undetermined": 5}[result["status"]],
                           "handoff": "Resolve high findings before execution; review findings require named scientific/resource confirmation.",
                           "actual_experiment_executed": False}
    return _contract(result, spec)


def refusal(message, spec=None, out_case_id=None):
    spec = spec if isinstance(spec, dict) else {}
    case_id = spec.get("case_id", out_case_id)
    result = {"schema_version": SCHEMA, "case_id": case_id, "mode": "generate_and_revise_plan",
              "status": "undetermined", "selected_plan": None,
              "findings": [{"rule": "spec.refused", "severity": "high", "message": message}],
              "severity_counts": {"high": 1, "medium": 0, "low": 0}, "checked": {},
              "limits": ["Structured refusal: the spec was not executable; no plan or experiment result was invented."],
              "run_state": {"exit_meaning": 5, "handoff": "Repair the named spec error and rerun.",
                            "actual_experiment_executed": False}}
    return _contract(result, spec)
