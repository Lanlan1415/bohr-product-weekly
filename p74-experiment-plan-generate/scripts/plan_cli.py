"""CLI for prospective experiment-plan generation; writes deterministic editable artifacts."""
from __future__ import annotations

import argparse
import copy
import csv
import json
import sys
from pathlib import Path

from plan_engine import SCHEMA, SpecError, generate, refusal


def _unwrap(case):
    if not isinstance(case, dict):
        return case
    root = copy.deepcopy(case)
    for key in ("spec", "inputs", "input_data", "case_data"):
        nested = root.get(key)
        if isinstance(nested, dict) and not any(k in root for k in ("candidate_plans", "plan_template", "factors")):
            merged = copy.deepcopy(nested)
            for meta in ("case_id", "caseId", "output_contract", "objective", "research_objective", "sources", "assumptions", "uncertainties"):
                if meta in root:
                    merged[meta] = copy.deepcopy(root[meta])
            root = merged
            break
    if "case_id" not in root and isinstance(root.get("caseId"), str):
        root["case_id"] = root["caseId"]
    if "objective" not in root:
        for key in ("research_objective", "research_goal", "goal"):
            if key in root:
                root["objective"] = copy.deepcopy(root[key])
                break
    if "candidate_plans" not in root:
        for key in ("versioned_candidate_plans", "candidates", "plans"):
            if isinstance(root.get(key), list):
                root["candidate_plans"] = copy.deepcopy(root[key])
                break
    return root


def _write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _csv(result, out):
    rows = result.get("design_matrix") or []
    preferred = ["run_order", "run_id", "design_id", "cell", "independent_replicate"]
    extras = sorted({key for row in rows if isinstance(row, dict) for key in row} - set(preferred))
    fields = preferred + extras
    with (out / "design_matrix.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({k: row.get(k) for k in fields})


def _markdown(result):
    lines = ["# Experiment plan (prospective, not executed)", "",
             f"- case_id: `{result.get('case_id')}`", f"- status: **{result.get('status')}**",
             f"- schema: `{result.get('schema_version', SCHEMA)}`", ""]
    plan = result.get("selected_plan")
    if not isinstance(plan, dict):
        lines += ["No plan was selected. See `result.json` findings and constraint records.", ""]
    else:
        lines += [f"## Objective", "", str(plan.get("objective")), "",
                  f"Selected version: **{plan.get('plan_id')} / {plan.get('source_version')} / {plan.get('design_id')}**.",
                  f"Lifecycle: **{plan.get('lifecycle')}**; execution gate: **{plan.get('execution_gate')}**.", "",
                  "## Hypotheses", ""]
        for item in plan.get("hypotheses") or []:
            lines.append(f"- {item.get('statement')} Primary outcome: {item.get('primary_outcome')}; falsification: {item.get('falsification')}")
        lines += ["", "## Variables and controls", ""]
        for item in plan.get("variables") or []:
            lines.append(f"- **{item.get('name')}** ({item.get('role')}): {item.get('operational_definition') or item.get('definition')}; measurement: {item.get('measurement') or 'see design'}; unit: {item.get('unit') or 'declared in data dictionary'}")
        for item in plan.get("controls") or []:
            lines.append(f"- Control **{item.get('type')}**: {item.get('condition')}; purpose: {item.get('purpose')}; excludes: {item.get('excludes_confounder')}")
        lines += ["", "## Finite parameter domains", ""]
        for item in plan.get("parameters") or []:
            levels = [x.get("value") for x in item.get("levels") or []]
            lines.append(f"- **{item.get('name')}**: {levels} {item.get('unit') or ''}; source: {item.get('source') or item.get('levels', [{}])[0].get('source')}; basis: {item.get('rationale') or 'see level provenance'}")
        sample = plan.get("sample_size") or {}
        lines += ["", "## Sample size, replication and allocation", "",
                  f"- Experimental unit: {sample.get('experimental_unit')}",
                  f"- Independent n per cell: {sample.get('independent_n_per_cell')}; technical measurements per run: {sample.get('technical_replicates_per_run')}",
                  f"- Design cells: {sample.get('design_cells')}; total independent runs: {sample.get('total_independent_runs')}; total measurements: {sample.get('total_measurements')}",
                  f"- Basis: {sample.get('basis') or (sample.get('power_calculation') or {}).get('method')}",
                  f"- Randomization: {json.dumps(plan.get('randomization'), ensure_ascii=False)}",
                  f"- Blinding: {json.dumps(plan.get('blinding'), ensure_ascii=False)}", "",
                  "The full run-level randomized order is in `design_matrix.csv`; run_id links future observations back to this plan.", "",
                  "## Executable steps and schedule", ""]
        for item in plan.get("steps") or []:
            lines.append(f"- **{item.get('id')}** ({item.get('duration_minutes')} min; depends_on={item.get('depends_on', [])}): {item.get('action')} Acceptance: {item.get('acceptance_criteria')}; on failure: {item.get('failure_action')}; resolved parameters: {json.dumps(item.get('resolved_parameters'), ensure_ascii=False)}")
        lines += ["", "## Materials and equipment", ""]
        for kind in ("materials", "equipment"):
            for item in plan.get(kind) or []:
                lines.append(f"- {kind}: **{item.get('name')}**; model/spec: {item.get('model') or item.get('spec') or item.get('version')}; state: {item.get('state')}; source: {item.get('source')}")
        lines += ["", "## Cost and time", "",
                  f"- Cost: {json.dumps(plan.get('cost'), ensure_ascii=False)}",
                  f"- Schedule: {json.dumps(plan.get('schedule'), ensure_ascii=False)}", "",
                  "## Statistical plan and decision thresholds", "",
                  f"- Statistical plan: {json.dumps(plan.get('statistical_plan'), ensure_ascii=False)}"]
        for item in plan.get("decision_thresholds") or []:
            lines.append(f"- {item.get('metric')} {item.get('op')} {item.get('value')} {item.get('unit') or ''}; source: {item.get('source')}; if met: {item.get('action_if_met')}; if not: {item.get('action_if_not_met')}")
        lines += ["", "## Risks, safety, ethics and fallback", ""]
        for item in plan.get("risks") or []:
            lines.append(f"- Trigger: {item.get('trigger')}; consequence: {item.get('consequence')}; mitigation: {item.get('mitigation')}; fallback: {item.get('fallback')}; stop: {item.get('stop_rule')}")
        lines += [f"- Safety: {json.dumps(plan.get('safety'), ensure_ascii=False)}",
                  f"- Ethics: {json.dumps(plan.get('ethics'), ensure_ascii=False)}", "",
                  "## Optimization loop", "", json.dumps(result.get("optimization_loop"), ensure_ascii=False, indent=2), "",
                  "**No measured response is claimed. The next iteration requires actual observations linked by run_id.**", ""]
    lines += ["## Findings and limits", ""]
    for item in result.get("findings") or []:
        lines.append(f"- `{item.get('rule')}` ({item.get('severity')}): {item.get('message')} {item.get('path') or ''}")
    for item in result.get("limits") or []:
        lines.append(f"- LIMIT: {item}")
    return "\n".join(lines) + "\n"


def write_outputs(result, out):
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    _write_json(out / "result.json", result)
    _write_json(out / "change_records.json", result.get("change_records", []))
    _csv(result, out)
    (out / "plan.md").write_text(_markdown(result), encoding="utf-8")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--spec", help="structured generation spec")
    source.add_argument("--case", help="original case.json; known input wrappers are adapted")
    parser.add_argument("--out", required=True, help="output directory, normally /app/output")
    args = parser.parse_args(argv)
    path = Path(args.spec or args.case)
    spec = {}
    try:
        spec = _unwrap(json.loads(path.read_text(encoding="utf-8-sig")))
        result = generate(spec)
    except (json.JSONDecodeError, UnicodeDecodeError, OSError) as exc:
        result = refusal(f"input is not readable UTF-8 JSON: {exc}", spec)
    except (SpecError, TypeError, ValueError, KeyError, ZeroDivisionError, OverflowError) as exc:
        result = refusal(f"invalid generation spec: {exc}", spec)
    write_outputs(result, Path(args.out))
    print(json.dumps({"case_id": result.get("case_id"), "status": result["status"],
                      "selected_design": (result.get("selected_plan") or {}).get("design_id"),
                      "findings": result.get("severity_counts"),
                      "wrote": str(Path(args.out) / "result.json")}, ensure_ascii=False))
    return {"clean": 0, "review": 3, "blocked": 4, "undetermined": 5}[result["status"]]


if __name__ == "__main__":
    raise SystemExit(main())
