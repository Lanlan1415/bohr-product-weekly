"""CLI for aligned experiment-plan comparison; produces deterministic review artifacts."""
from __future__ import annotations

import argparse
import copy
import csv
import json
from pathlib import Path

from compare_engine import SCHEMA, SpecError, compare, refusal


def _unwrap(case):
    if not isinstance(case, dict):
        return case
    root = copy.deepcopy(case)
    for key in ("spec", "inputs", "input_data", "case_data"):
        nested = root.get(key)
        if isinstance(nested, dict) and not any(k in root for k in ("candidate_plans", "criteria")):
            merged = copy.deepcopy(nested)
            for meta in ("case_id", "caseId", "output_contract", "objective", "research_objective", "sources", "pending_review", "fallback_triggers"):
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


def _write_csv(path, rows, preferred):
    extras = sorted({key for row in rows if isinstance(row, dict) for key in row} - set(preferred))
    fields = preferred + extras
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            flat = {}
            for key in fields:
                value = row.get(key)
                flat[key] = json.dumps(value, ensure_ascii=False, sort_keys=True) if isinstance(value, (dict, list)) else value
            writer.writerow(flat)


def _markdown(result):
    lines = ["# Aligned experiment-plan comparison", "", f"- case_id: `{result.get('case_id')}`",
             f"- status: **{result.get('status')}**", f"- objective: {result.get('objective')}",
             "- lifecycle: **comparison only; no experiment executed**", "", "## Common criteria and weights", "",
             "| Criterion | Direction | Normalized weight | Unit | Scale bounds | Weight basis |", "|---|---:|---:|---|---|---|"]
    for c in result.get("criteria") or []:
        lines.append(f"| {c.get('name')} | {c.get('direction')} | {c.get('weight')} | {c.get('unit')} | {c.get('scale_bounds')} | {c.get('weight_basis') or c.get('rationale')} |")
    lines += ["", "## Hard-gate results", ""]
    for candidate in result.get("constraint_results") or []:
        lines.append(f"### {candidate.get('plan_id')} ({candidate.get('version')}): {candidate.get('gate_status')}")
        for c in candidate.get("constraints") or []:
            lines.append(f"- `{c.get('id')}`: {c.get('metric')} actual={c.get('actual')} {c.get('op')} required={c.get('required')} => **{c.get('status')}**; source={c.get('source')}; uncertainty={c.get('uncertainty_interval')}")
    lines += ["", "## Scores and ranking", "", "| Rank | Plan | Version | Score / 100 |", "|---:|---|---|---:|"]
    for row in result.get("ranking") or []:
        lines.append(f"| {row.get('rank')} | {row.get('plan_id')} | {row.get('version')} | {row.get('score')} |")
    lines += ["", "The complete per-cell raw value, normalization, weighted contribution, evidence and rationale are in `comparison_matrix.csv` and `evidence_matrix.csv`.", "",
              "## Cost and time recalculation", ""]
    for c in result.get("candidate_evaluations") or []:
        lines.append(f"- **{c.get('plan_id')}**: cost={c.get('total_cost')} {c.get('currency')}, expected total time={c.get('total_time_hours')} h; score={c.get('score')}; gate={c.get('gate_status')}")
    lines += ["", "## Recommendation and trade-offs", ""]
    recommendation = result.get("recommendation")
    if recommendation:
        lines += [recommendation.get("statement"), "", f"Selection state: **{recommendation.get('selection_status')}**; robust to weight probe={recommendation.get('robust_to_weight_probe')}; robust to declared interval probe={recommendation.get('robust_to_declared_interval_probes')}.", ""]
        for row in result.get("tradeoffs") or []:
            lines.append(f"### {row.get('winner')} vs {row.get('other')} (score difference {row.get('score_difference')})")
            for item in row.get("winner_disadvantages") or []:
                lines.append(f"- Accepted disadvantage on {item.get('criterion')}: winner={item.get('winner_raw')}, other={item.get('other_raw')}, weighted difference={item.get('weighted_difference')}")
            for item in row.get("decisive_criteria") or []:
                lines.append(f"- Decisive dimension {item.get('criterion')}: normalized difference={item.get('normalised_difference')}, weighted difference={item.get('weighted_difference')}")
    else:
        lines.append("No selectable plan. Do not choose a failed candidate merely because it has a high soft score.")
    lines += ["", "## Eliminated or undetermined plans", ""]
    for row in result.get("eliminated_plans") or []:
        lines.append(f"- **{row.get('plan_id')}**: {json.dumps(row.get('reasons'), ensure_ascii=False)}")
    lines += ["", "## Sensitivity and uncertainty", "", "```json", json.dumps(result.get("sensitivity_analysis"), ensure_ascii=False, indent=2), "```", "",
              "```json", json.dumps(result.get("uncertainty_analysis"), ensure_ascii=False, indent=2), "```", "",
              "## Fallback triggers", ""]
    fallback = result.get("fallback_plan")
    if fallback:
        lines.append(f"Fallback candidate: **{fallback.get('plan_id')} ({fallback.get('version')})**. {fallback.get('note')}")
        for trigger in fallback.get("triggers") or []:
            lines.append(f"- Trigger: {trigger.get('trigger')}; action: {trigger.get('action')}; target: {trigger.get('target_plan_id')}; source: {trigger.get('source')}")
    else:
        lines.append("No validated fallback; stop and redesign if the selected route fails.")
    lines += ["", "## Findings and limits", ""]
    for item in result.get("findings") or []:
        lines.append(f"- `{item.get('rule')}` ({item.get('severity')}): {item.get('message')} {item.get('path') or ''}")
    for item in result.get("limits") or []:
        lines.append(f"- LIMIT: {item}")
    return "\n".join(lines) + "\n"


def write_outputs(result, out):
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    _write_json(out / "result.json", result)
    _write_csv(out / "comparison_matrix.csv", result.get("scoring_matrix") or [],
               ["plan_id", "criterion", "raw", "unit", "direction", "normalised", "weight", "weighted_contribution", "evidence_refs", "rationale"])
    _write_csv(out / "evidence_matrix.csv", result.get("evidence_matrix") or [],
               ["plan_id", "criterion", "raw", "unit", "normalised", "weighted_contribution", "evidence_refs", "evidence", "rationale", "uncertainty", "calculation"])
    _write_json(out / "sensitivity.json", {"sensitivity_analysis": result.get("sensitivity_analysis"),
                                           "uncertainty_analysis": result.get("uncertainty_analysis")})
    _write_json(out / "change_records.json", result.get("change_records", []))
    (out / "recommendation.md").write_text(_markdown(result), encoding="utf-8")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--spec")
    source.add_argument("--case", help="original case.json; known wrappers are adapted")
    parser.add_argument("--out", required=True)
    args = parser.parse_args(argv)
    spec = {}
    try:
        spec = _unwrap(json.loads(Path(args.spec or args.case).read_text(encoding="utf-8-sig")))
        result = compare(spec)
    except (json.JSONDecodeError, UnicodeDecodeError, OSError) as exc:
        result = refusal(f"input is not readable UTF-8 JSON: {exc}", spec)
    except (SpecError, TypeError, ValueError, KeyError, ZeroDivisionError, OverflowError) as exc:
        result = refusal(f"invalid comparison spec: {exc}", spec)
    write_outputs(result, Path(args.out))
    print(json.dumps({"case_id": result.get("case_id"), "status": result["status"],
                      "recommendation": (result.get("recommendation") or {}).get("plan_id"),
                      "findings": result.get("severity_counts"),
                      "wrote": str(Path(args.out) / "result.json")}, ensure_ascii=False))
    return {"clean": 0, "review": 3, "blocked": 4, "undetermined": 5}[result["status"]]


if __name__ == "__main__":
    raise SystemExit(main())
