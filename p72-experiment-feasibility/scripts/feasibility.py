"""Versioned, source-grounded feasibility review; no resource is assumed present.

Spec contract (planning declarations, not real laboratory records):
  hard_constraints: [{id, metric, op, value, unit, source, locator, category}]
  inventory: [{resource_id, status, capabilities:{name:{value,unit}}, ...}]
  plan_versions: [{plan_id, source_version, steps, parameters, equipment_requirements,
                   material_requirements, ethics, safety, risks, metrics}]
Metric names include total_cost, total_samples, device_hours, person_hours,
elapsed_hours and parameter.<name>. Every version is evaluated independently.

Only declared facts are calculated. An unknown, prospective order or approval is
never converted to pass. Hard-conflict => infeasible; unresolved conditions =>
conditional; all hard checks plus required readiness known feasible => feasible.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import math
from pathlib import Path

VERSION = "versioned-feasibility/v1"
CATEGORIES = ("hypotheses_variables", "controls", "equipment_materials",
              "time_samples", "parameter_ranges", "risks_anomalies", "ethics_safety")
NUMERIC_METRICS = {"total_cost", "total_samples", "device_hours", "person_hours",
                   "waiting_hours", "elapsed_hours"}


def obj(x):
    return x if isinstance(x, dict) else {}


def records(x):
    return [r for r in x if isinstance(r, dict)] if isinstance(x, list) else []


def number(x):
    if isinstance(x, bool):
        return None
    try:
        v = float(x)
        return v if math.isfinite(v) else None
    except (TypeError, ValueError, OverflowError):
        return None


def nonnegative(x):
    n = number(x)
    return n if n is not None and n >= 0 else None


def clean_number(x):
    return round(x, 10) if isinstance(x, float) else x


def txt(x):
    return str(x or "").strip()


def values(x):
    if isinstance(x, (str, int, float)):
        return [x]
    return [v for v in x if isinstance(v, (str, int, float))] if isinstance(x, list) else []


def compare(actual, op, expected):
    if actual is None or expected is None:
        return None
    if op == "in":
        return actual in values(expected)
    if op == "not_in":
        return actual not in values(expected)
    if op in ("==", "!="):
        result = txt(actual) == txt(expected)
        return result if op == "==" else not result
    if op in ("contains", "not_contains"):
        result = txt(expected) in txt(actual)
        return result if op == "contains" else not result
    a, b = number(actual), number(expected)
    if a is None or b is None:
        return None
    return {"<=": a <= b, "<": a < b, ">=": a >= b, ">": a > b,
            "==": a == b}.get(op)


def evidence(spec, plan):
    steps = records(plan.get("steps"))
    declared = plan.get("material_costs")
    if declared is not None:
        return number(obj(declared).get("amount")), {"formula": "plan.material_costs.amount",
            "source": obj(declared).get("source") or plan.get("source_version")}
    terms = []
    total = 0.0
    currencies = set()
    for i, step in enumerate(steps):
        quantity = nonnegative(step.get("material_quantity"))
        price = nonnegative(obj(step.get("unit_price")).get("amount"))
        if quantity is not None and price is not None:
            units = number(step.get("independent_runs", step.get("parallel_runs", 1))) or 1.0
            term = quantity * price * units
            total += term
            currencies.add(txt(obj(step.get("unit_price")).get("currency")))
            terms.append({"step": step.get("step_id", i), "quantity": quantity,
                          "unit_price": price, "parallel_runs": units, "cost": clean_number(term)})
        elif any(k in step for k in ("material_quantity", "unit_price")):
            return None, {"formula": "sum(quantity*price*parallel_runs)",
                          "unknown_step": step.get("step_id", i),
                          "reason": "quantity and unit price must both be present"}
    return (clean_number(total) if len(currencies) <= 1 else None), {
        "formula": "sum(quantity*unit_price*parallel_runs)", "terms": terms,
        "currencies": sorted(currencies),
        "reason": "mixed currencies require an explicit conversion record" if len(currencies) > 1 else None}


def aggregates(spec, plan):
    steps = records(plan.get("steps"))
    terms = []
    sums = {k: 0.0 for k in ("total_samples", "device_hours", "person_hours", "waiting_hours", "elapsed_hours")}
    unknown = set()
    keys = {"total_samples": "sample_units", "device_hours": "device_hours",
            "person_hours": "person_hours", "waiting_hours": "waiting_hours",
            "elapsed_hours": "elapsed_hours"}
    for i, step in enumerate(steps):
        if txt(step.get("independent_runs")) and number(step.get("independent_runs")) is None:
            unknown.add("independent_runs")
        runs = number(step.get("independent_runs")) or (1.0 if "independent_runs" not in step else 0.0)
        term = {"step": step.get("step_id", i), "independent_runs": runs}
        for metric, key in keys.items():
            if key not in step:
                continue
            n = nonnegative(step.get(key))
            if n is None:
                unknown.add(key)
            else:
                sums[metric] += n * runs
            term[key] = step.get(key)
        terms.append(term)
    sampling = obj(plan.get("sampling"))
    if sampling and "per_step" not in sampling:
        groups = records(sampling.get("groups"))
        if groups:
            total, formula = 0.0, []
            for i, g in enumerate(groups):
                n = nonnegative(g.get("units"))
                batches = nonnegative(g.get("independent_batches"))
                if n is None or batches is None:
                    unknown.add("sampling")
                else:
                    # Repeated readings do not inflate the independent sample count.
                    v = n * batches
                    total += v
                    formula.append({"group": g.get("group_id", i), "units": n,
                                    "independent_batches": batches, "total_independent_units": v})
            sums["total_samples"] = total
            terms.append({"formula": "sum(units_per_group*independent_batches)",
                          "exclude_technical_repetitions": True, "terms": formula})
    supplied = obj(plan.get("metrics"))
    for metric in sums:
        if metric in supplied:
            sums[metric] = number(supplied[metric])
        else:
            sums[metric] = clean_number(sums[metric])
        affected = keys[metric] in unknown
        if metric == "total_samples":
            affected = affected or "sampling" in unknown or "independent_runs" in unknown
        if affected:
            # Only the affected aggregate becomes unknown; other arithmetic survives.
            sums[metric] = number(supplied.get(metric))
    if "total_samples" in supplied:
        sums["total_samples"] = number(supplied["total_samples"])
    cost, e = evidence(spec, plan)
    sums["total_cost"] = cost if cost is not None else number(supplied.get("total_cost"))
    return sums, {"steps": terms, "cost": e,
                  "unknown_arithmetic_inputs": sorted(unknown),
                  "note": "Arithmetic uses declared units; repeated readings are not independent samples."}


def actual_metric(name, plan, totals):
    if name in totals:
        return totals[name]
    if name.startswith("parameter."):
        return plan.get("parameters", {}).get(name.partition(".")[2]) if isinstance(plan.get("parameters"), dict) else None
    if name.startswith("metrics."):
        return obj(plan.get("metrics")).get(name.split(".", 1)[1])
    if name.startswith("resources."):
        return obj(plan.get("resources")).get(name.split(".", 1)[1])
    return obj(plan.get("metrics")).get(name)


def hard_checks(spec, plan, totals):
    out = []
    units = dict(obj(spec.get("units")))
    units.update(obj(plan.get("units")))
    constraints = records(spec.get("hard_constraints")) + records(plan.get("hard_constraints"))
    for i, c in enumerate(constraints):
        cid = txt(c.get("id")) or f"constraint[{i}]"
        name = txt(c.get("metric"))
        actual = actual_metric(name, plan, totals)
        expected = c.get("value")
        result = {"constraint_id": cid, "category": c.get("category"),
                  "metric": name or None, "actual_value": clean_number(actual),
                  "operator": c.get("op"), "required_value": expected,
                  "expected_unit": c.get("unit"),
                  "actual_unit": units.get(name),
                  "source": c.get("source"), "locator": c.get("locator"),
                  "evidence_class": c.get("evidence_class", "declared_constraint")}
        if not name or not c.get("op"):
            result.update(status="unknown", because="metric and operator are required")
        elif not c.get("source"):
            result.update(status="unknown", because="no source evidence supplied for this bound")
        elif c.get("unit") and units.get(name) not in (None, c.get("unit")):
            result.update(status="unknown", because="unit mismatch requires a declared conversion")
        else:
            passed = compare(actual, c.get("op"), expected)
            status = "passed" if passed is True else "violated" if passed is False else "unknown"
            result.update(status=status,
                          because=None if passed is not None else "metric missing or nonnumeric")
        out.append(result)
    for req_index, req in enumerate(records(plan.get("equipment_requirements"))):
        rid = txt(req.get("resource_id"))
        found = next((r for r in records(spec.get("inventory"))
                      if txt(r.get("resource_id") or r.get("id")) == rid), None)
        cid = f"equipment.{rid or req_index}"
        base = {"constraint_id": cid, "category": "equipment_materials",
                "source": req.get("source"), "locator": req.get("locator")}
        if not rid or not req.get("source"):
            out.append(dict(base, constraint_id=cid, status="unknown", because="equipment ID/source missing"))
            continue
        if found is None:
            out.append(dict(base, status="unknown", resource_id=rid,
                            because="required equipment has no independently recorded inventory line"))
            continue
        state = txt(found.get("status")).lower()
        if state in ("missing", "not_owned", "unavailable", "broken", "不具备"):
            status = "violated"
        elif state in ("present", "available", "已具备"):
            status = "passed"
        elif state in ("external_confirmed", "outsourced_available"):
            status = "passed" if found.get("confirmed") is True else "unknown"
        else:
            status = "unknown"  # prospective booking or purchase is not readiness
        required = txt(req.get("capability"))
        if required:
            capability = obj(found.get("capabilities")).get(required)
            rv, av = number(req.get("min_value")), number(obj(capability).get("value"))
            if rv is None or av is None:
                status, detail = "unknown", "capability numeric range unreported"
            else:
                ok = av >= rv
                status = "passed" if ok else "violated"
                detail = f"required {rv} {req.get('unit')}; inventory {av} {obj(capability).get('unit')}"
                if req.get("unit") != obj(capability).get("unit"):
                    status, detail = "unknown", "capability units differ; no conversion declared"
        else:
            detail = "readiness state only; equipment capability not stated"
        out.append(dict(base, resource_id=rid, inventory_status=state or None,
                        inventory_source=found.get("source"), capability=required or None,
                        status=status, detail=detail))
    for i, req in enumerate(records(plan.get("material_requirements"))):
        mid, quantity, units = txt(req.get("resource_id")), number(req.get("quantity")), txt(req.get("unit"))
        found = next((r for r in records(spec.get("inventory"))
                      if txt(r.get("resource_id") or r.get("id")) == mid), None)
        base = {"constraint_id": f"material.{mid or i}", "category": "equipment_materials",
                "resource_id": mid or None, "source": req.get("source"), "locator": req.get("locator")}
        if found is None:
            out.append(dict(base, status="unknown", because="resource not verified as present or available"))
        else:
            state = txt(found.get("status")).lower()
            available = number(found.get("available_quantity"))
            unit_ok = not (quantity is not None and units and found.get("unit") and units != found.get("unit"))
            quantity_ok = quantity is not None and available is not None and available >= quantity
            confirmed_supply = (state in ("external_confirmed", "outsourced_available")
                                and found.get("confirmed") is True and quantity is not None
                                and (quantity_ok or number(found.get("lead_time_hours")) is not None))
            in_stock = state in ("present", "available", "in_stock", "已具备") and quantity_ok
            status = "passed" if (confirmed_supply or in_stock) and unit_ok else "unknown"
            if state in ("missing", "unavailable", "不具备") and available is not None and quantity is not None and available < quantity:
                status = "violated"
            out.append(dict(base, status=status, inventory_source=found.get("source"),
                            inventory_status=state or None, available_quantity=available,
                            required_quantity=quantity, lead_time_hours=number(found.get("lead_time_hours")),
                            unit=units or found.get("unit"),
                            because="unit mismatch requires conversion" if not unit_ok else
                                    "planning-only confirmed source or sufficient stock; no vendor delivery guarantee" if status == "passed" else
                                    "stock/procurement or lead-time evidence unresolved"))
    return out


def compliance(spec, plan):
    checks = []
    ethics = obj(plan.get("ethics"))
    involvement = ethics.get("involvement")
    approval_list = records(ethics.get("approvals"))
    for kind in ("human_samples", "animals", "personal_data", "biohazard"):
        involved = obj(involvement).get(kind) is True
        if not involved:
            continue
        candidates = [a for a in approval_list if txt(a.get("scope")) == kind or len(approval_list) == 1]
        if not candidates:
            checks.append({"check": "ethics." + kind, "status": "violated",
                           "because": "declared ethical involvement has no approval record"})
        else:
            for a in candidates:
                state = txt(a.get("status"))
                checks.append({"check": "ethics." + kind, "status": "passed" if state == "approved" else
                               "violated" if state in ("missing", "refused", "expired") else "unknown",
                               "approval_id": a.get("approval_id"), "source": a.get("source"),
                               "because": "approval must be in force before starting; pending is a precondition"})
    for i, h in enumerate(records(obj(plan.get("safety")).get("hazards"))):
        controls = records(h.get("required_controls")) + [c for c in h.get("controls", []) if isinstance(c, str)] if isinstance(h.get("controls"), list) else records(h.get("required_controls"))
        unavailable = [c for c in controls if isinstance(c, dict) and c.get("verified") is not True]
        if not controls or unavailable:
            checks.append({"check": f"safety.hazard[{i}]", "status": "violated",
                           "hazard": h.get("name"), "because": "required controls not all verified"})
        else:
            checks.append({"check": f"safety.hazard[{i}]", "status": "passed",
                           "hazard": h.get("name"), "controls": controls})
    return checks


def coverage(spec, plan):
    definitions = {
        "hypotheses_variables": ("hypothesis", "variables"),
        "controls": ("controls", "judgement_criteria"),
        "equipment_materials": ("equipment_requirements", "material_requirements"),
        "time_samples": ("steps", "sampling"),
        "parameter_ranges": ("parameter_domains", "parameters"),
        "risks_anomalies": ("risks",),
        "ethics_safety": ("ethics", "safety")}
    rows = []
    for category in CATEGORIES:
        keys = definitions[category]
        present = {k: bool(plan.get(k)) for k in keys}
        if category == "ethics_safety" and isinstance(obj(plan.get("ethics")).get("involvement"), dict):
            present["involvement_declared"] = True
        status = "reported" if all(present.values()) else "partial" if any(present.values()) else "unknown"
        rows.append({"category": category, "status": status,
                     "missing_or_unreported": [k for k, v in present.items() if not v],
                     "requirement": "explicitly report a scope, its basis, and unknowns; absence is never pass"})
    return rows


def evaluate(spec, plan, index):
    totals, arithmetic = aggregates(spec, plan)
    checks = hard_checks(spec, plan, totals)
    compliance_checks = compliance(spec, plan)
    for c in compliance_checks:
        c["constraint_id"] = c.get("check")
        c["category"] = "ethics_safety"
    checks.extend(compliance_checks)
    categories = coverage(spec, plan)
    findings = []
    if any(c["status"] == "violated" for c in checks):
        verdict, status = "infeasible", "blocked"
    elif any(c["status"] == "unknown" for c in checks) or any(c["status"] != "reported" for c in categories):
        verdict, status = "conditional", "review"
    else:
        verdict, status = "feasible", "clean"
    for c in checks:
        if c["status"] != "passed":
            findings.append({"rule": "feasibility.constraint_unknown" if c["status"] == "unknown" else
                              "feasibility.hard_constraint_violated",
                              "severity": "medium" if c["status"] == "unknown" else "high",
                              "plan_id": plan.get("plan_id", index),
                              "constraint_id": c["constraint_id"], "message": c.get("because") or "hard bound failed"})
    for c in categories:
        if c["status"] != "reported":
            findings.append({"rule": "feasibility.coverage_incomplete", "severity": "medium",
                              "plan_id": plan.get("plan_id", index), "category": c["category"],
                              "message": "not reported is not satisfied: " + ", ".join(c["missing_or_unreported"])})
    if arithmetic["unknown_arithmetic_inputs"]:
        findings.append({"rule": "feasibility.arithmetic_unknown", "severity": "medium",
                          "plan_id": plan.get("plan_id", index), "message": "one or more resource terms are missing",
                          "fields": arithmetic["unknown_arithmetic_inputs"]})
    remedies = []
    for c in checks:
        if c["status"] == "passed":
            continue
        safety = txt(c.get("constraint_id")).startswith("safety.")
        remedies.append({"constraint_id": c["constraint_id"], "status_before_removal": c["status"],
             "required_evidence": ["verified source record", "revised plan/version if required"],
             "action": "obtain verified control and approval before execution" if safety else
                       ("remove the bound conflict and re-evaluate the complete version" if c["status"] == "violated" else
                        "obtain explicit inventory/procurement/approval evidence; do not substitute a best guess"),
             "auto_promotes_feasible": False,
             "revalidation": "update source version and rerun this exact spec; all versions must be checked again"})
    return {"plan_id": plan.get("plan_id", f"version[{index}]"),
            "source_version": plan.get("source_version"), "source_locator": plan.get("source_locator"),
            "derived_metrics": totals, "derived_metric_arithmetic": arithmetic,
            "constraint_results": checks, "seven_category_coverage": categories,
            "verdict": verdict, "status": status,
            "blocking_conditions": [c["constraint_id"] for c in checks if c["status"] == "violated"],
            "unresolved_conditions": [c["constraint_id"] for c in checks if c["status"] == "unknown"],
            "remedies": remedies, "findings": findings,
            "assumptions": plan.get("assumptions", []),
            "evidence_boundary": "prospective planning declaration only; not a laboratory/vendor/approval audit"}


def prepare(spec):
    if not isinstance(spec, dict):
        raise ValueError("spec must be a JSON object")
    versions = records(spec.get("plan_versions") or spec.get("versions") or spec.get("candidate_plans"))
    if not versions and isinstance(spec.get("plan"), dict):
        versions = [spec["plan"]]
    if not versions:
        raise ValueError("no plan_versions/plan could be reviewed; supply explicit source-versioned plans")
    return versions


def run(spec):
    versions = prepare(spec)
    reviews = [evaluate(spec, p, i) for i, p in enumerate(versions)]
    findings = [f for r in reviews for f in r["findings"]]
    if not [r for r in reviews if r["verdict"] != "infeasible"]:
        findings.append({"rule": "feasibility.no_feasible_version", "severity": "high",
                          "message": "every supplied version has hard blockers; do not reinterpret conditions as approval"})
    counts = {}
    for f in findings:
        counts[f["severity"]] = counts.get(f["severity"], 0) + 1
    real = list(findings)
    status = "blocked" if counts.get("high") else "review" if real else "clean"
    feasible = [r["plan_id"] for r in reviews if r["verdict"] == "feasible"]
    conditional = [r["plan_id"] for r in reviews if r["verdict"] == "conditional"]
    canon = json.dumps(spec, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    result = {"schema_version": VERSION, "engine_version": "1.0", "status": status,
              "delivery_status": {"clean": "done", "review": "partial", "blocked": "failed"}[status],
              "findings": findings, "severity_counts": counts,
              "version_reviews": reviews,
              "overall_feasibility": {"feasible_version_ids": feasible,
                   "conditional_version_ids": conditional,
                   "infeasible_version_ids": [r["plan_id"] for r in reviews if r["verdict"] == "infeasible"],
                   "selection": "all versions reported; no assumption that latest version is best",
                   "conclusion_level": "infeasible" if not feasible and not conditional else
                                       "conditional" if not feasible or conditional else "feasible"},
              "sources": obj(spec.get("source_record")) or spec.get("sources", []),
              "uncertainty": ["unknown and prospective entries remain conditions, not evidence of availability"],
              "limits": ["Arithmetic covers declared terms only; no hidden costs, biological variability, sensor accuracy, procurement ETA or approval is inferred.",
                         "A conditional plan must not be executed until required evidence and controls are confirmed.",
                         "One version must not silently replace another source version."],
              "reproducibility": {"engine": "scripts/feasibility.py", "deterministic": True,
                                   "domain_sha256": hashlib.sha256(canon).hexdigest(),
                                   "rerun": "python scripts/feasibility.py --spec SPEC.json --out OUTPUT_DIR"},
              "reference_methods": [
                  {"name": "pymoo feasibility-first constraints",
                   "source": "https://pymoo.org/constraints/index.html",
                   "implemented_here": "violated -> infeasible; unknown -> conditional; no penalty value can outweigh a hard constraint"},
                  {"name": "explicit resource arithmetic and separate seven-category coverage",
                   "source": "local feasibility engine (standard library)",
                   "implemented_here": "sample, time, and money calculations retain units/evidence and unknown terms"}],
              "change_records": [{"action": "evaluate", "plan_id": r["plan_id"],
                                   "source_version_before": r["source_version"], "resource_values_changed": 0}
                                  for r in reviews]}
    result["feasibility_review"] = {
        "conclusion_level": result["overall_feasibility"]["conclusion_level"],
        "version_verdicts": [{"plan_id": r["plan_id"], "source_version": r["source_version"],
                               "verdict": r["verdict"], "blocking_conditions": r["blocking_conditions"],
                               "unresolved_conditions": r["unresolved_conditions"],
                               "seven_categories": r["seven_category_coverage"]} for r in reviews]}
    result["evidence_and_risks"] = {
        "evidence_boundary": "declared sources only; no missing file is treated as approval or availability",
        "resource_and_constraint_checks": {r["plan_id"]: r["constraint_results"] for r in reviews},
        "arithmetic": {r["plan_id"]: r["derived_metric_arithmetic"] for r in reviews},
        "risks_and_remedies": {r["plan_id"]: r["remedies"] for r in reviews}}
    result["confirmation_items"] = [
        {"plan_id": r["plan_id"], "constraint_id": c["constraint_id"],
         "reason": c.get("because"), "required_before_execution": True}
        for r in reviews for c in r["constraint_results"] if c["status"] != "passed"]
    return result


def contract(result, spec, case=None):
    case = obj(case)
    cid = spec.get("case_id", case.get("case_id", case.get("id")))
    if cid is not None:
        result["case_id"] = cid
    oc = spec.get("output_contract", case.get("output_contract"))
    keys = list(oc) if isinstance(oc, dict) else oc if isinstance(oc, list) else []
    if oc is not None and not isinstance(oc, (list, dict)):
        result["limits"].append("output_contract is not an object or field-name list")
    for key in [k for k in keys if isinstance(k, str)]:
        if key in result:
            continue
        v = spec.get(key, case.get(key))
        if v is not None and key not in ("rows", "plan_versions", "output_contract", "spec"):
            result[key] = copy.deepcopy(v)
        else:
            result[key] = None
            result["limits"].append(f"output_contract field '{key}' was not supplied or derivable")
    return result


def load_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def refuse(out, message, spec=None, case=None):
    r = {"schema_version": VERSION, "status": "undetermined", "delivery_status": "failed",
         "findings": [{"rule": "feasibility.spec_unreadable", "severity": "high",
                       "message": str(message)}],
         "limits": ["analysis could not run; missing information was not assumed to be satisfied"],
         "sources": [], "uncertainty": [str(message)], "version_reviews": [],
         "reproducibility": {"deterministic": True}}
    r = contract(r, obj(spec), case)
    out.mkdir(parents=True, exist_ok=True)
    (out / "result.json").write_text(json.dumps(r, ensure_ascii=False, indent=2), encoding="utf-8")
    return r


def build(spec_path, out, case_path=None):
    spec, case = None, None
    if case_path:
        try:
            case = load_json(case_path)
        except Exception as exc:
            return refuse(out, f"case file is not readable JSON: {exc}", spec, None)
    try:
        spec = load_json(spec_path)
        if isinstance(spec, dict) and isinstance(spec.get("spec"), dict):
            spec = spec["spec"]
        if not isinstance(spec, dict):
            raise ValueError("spec is not a JSON object")
    except Exception as exc:
        return refuse(out, exc, spec, case)
    try:
        r = run(spec)
    except (TypeError, ValueError, KeyError, OSError, ArithmeticError) as exc:
        return refuse(out, exc, spec, case)
    try:
        contract(r, spec, case)
        out.mkdir(parents=True, exist_ok=True)
        (out / "result.json").write_text(json.dumps(r, ensure_ascii=False, indent=2), encoding="utf-8")
    except (TypeError, ValueError, OSError) as exc:
        return refuse(out, exc, spec, case)
    return r


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--spec", required=True, help="local, derived feasibility spec")
    p.add_argument("--case", help="original case JSON for identity/output_contract metadata")
    p.add_argument("--out", required=True)
    a = p.parse_args(argv)
    r = build(Path(a.spec), Path(a.out), a.case)
    print(json.dumps({"status": r["status"], "overall_feasibility": r.get("overall_feasibility"),
                      "result": str(Path(a.out) / "result.json")}, ensure_ascii=False))
    return {"clean": 0, "review": 3, "blocked": 4, "undetermined": 5}.get(r["status"], 1)


if __name__ == "__main__":
    raise SystemExit(main())
