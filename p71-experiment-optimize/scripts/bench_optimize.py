"""Benchmark for the experiment-parameter optimisation skill.

One scenario per rule, aligned to the scoring points this task states:

  a recommendation loop a second person can re-run
      -> stage_missing, no_commit, no_data_version, no_command, no_logs, no_exit_status
  constraints with provenance (device manual, SOP, history)
      -> material_without_source, material_without_version, material_state_undeclared,
         material_no_license (+ dataset FP guard)
  the feasible domain, not vibes -> environment_incomplete, env_conflict_unflagged
  every recommended value has a basis -> parameter_source_undeclared,
      assumed_without_justification, parameter_no_locator
  response metrics with tolerance and verdicts -> no_tolerance, no_comparison_basis,
      no_statistic, metric_no_verdict, difference_unclassified, difference_unexplained
  a graded recommendation with a basis -> verdict_unclassified, verdict_without_basis

    python bench_optimize.py
"""

from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import sections as S  # noqa: E402

BASE = {
    "commit": "opt-round-2024-05-17",
    "data_version": "exp-history@2024-05",
    "commands": ["python optimise.py --strategy sequential --budget 60"],
    "checklist": {
        "materials": [{"name": "管式炉温控模块", "source": "设备手册 TC-220 rev C",
                       "version": "rev C", "state": "present"}],
        "environment": {"dependencies": "约束清单 constraints.csv v3",
                        "hardware": "管式炉 TC-220 / K 型热电偶", "seed": "0"},
        "parameters": [{"name": "退火温度", "source": "paper", "locator": "SOP-A07 §4.2"}],
        "run": {"logs": "runs/opt-round3.log", "exit_status": "succeeded"},
        "results": {"tolerance": "±2 C", "comparison_basis": "转化率主指标",
                    "statistic": "3 次重复的均值",
                    "metrics": [{"name": "转化率", "paper": 0.82, "reproduced": 0.815,
                                 "within_tolerance": True}]},
        "verdict": "reproducible",
        "verdict_basis": "所有响应指标在容差内，建议值均落在设备量程与安全阈值之内",
    },
}


def d(**over):
    s = copy.deepcopy(BASE)
    s.update(over)
    return s


def ck(**over):
    s = copy.deepcopy(BASE)
    s["checklist"] = copy.deepcopy(BASE["checklist"])
    s["checklist"].update(over)
    return s


def mat(**over):
    s = copy.deepcopy(BASE)
    s["checklist"] = copy.deepcopy(BASE["checklist"])
    s["checklist"]["materials"] = [dict(BASE["checklist"]["materials"][0], **over)]
    return s


def par(**over):
    s = copy.deepcopy(BASE)
    s["checklist"] = copy.deepcopy(BASE["checklist"])
    s["checklist"]["parameters"] = [dict(BASE["checklist"]["parameters"][0], **over)]
    return s


def res(**over):
    s = copy.deepcopy(BASE)
    s["checklist"] = copy.deepcopy(BASE["checklist"])
    s["checklist"]["results"] = dict(BASE["checklist"]["results"], **over)
    return s


def env(**over):
    s = copy.deepcopy(BASE)
    s["checklist"] = copy.deepcopy(BASE["checklist"])
    s["checklist"]["environment"] = dict(BASE["checklist"]["environment"], **over)
    return s


SCEN = [
    ("clean", lambda: (d(), [])),

    # the recommendation loop and its artefacts
    ("stage_missing", lambda: (ck(run=None), ["repro.stage_missing"])),
    ("no_round_id", lambda: (d(commit=""), ["repro.no_commit"])),
    ("no_history_snapshot", lambda: (d(data_version=""), ["repro.no_data_version"])),
    ("no_search_command", lambda: (d(commands=[]), ["repro.no_command"])),
    ("no_run_log", lambda: (ck(run={"exit_status": "succeeded"}), ["repro.no_logs"])),
    ("no_exit_status", lambda: (ck(run={"logs": "runs/opt-round3.log"}),
                                ["repro.no_exit_status"])),

    # constraints with provenance
    ("constraint_no_source", lambda: (mat(source=""), ["repro.material_without_source"])),
    ("constraint_no_version", lambda: (mat(version=""), ["repro.material_without_version"])),
    ("constraint_state_undeclared",
     lambda: (mat(state=""), ["repro.material_state_undeclared"])),
    # a declared script/protocol artefact must carry its license; a plain dataset need not
    ("script_no_license", lambda: (mat(kind="code"), ["repro.material_no_license"])),
    ("fp_dataset_no_license", lambda: (mat(kind="dataset"), [])),

    # the feasible domain
    ("feasible_domain_incomplete",
     lambda: (env(hardware=""), ["repro.environment_incomplete"])),
    ("constraint_conflict_unflagged",
     lambda: (env(dependencies_detail=[{"name": "target-temperature",
                                        "paper_version": "350 C",
                                        "actual_version": "280 C"}]),
              ["repro.env_conflict_unflagged"])),

    # every recommended value has a basis
    ("param_source_undeclared", lambda: (par(source=""),
                                         ["repro.parameter_source_undeclared"])),
    ("assumed_without_justification",
     lambda: (par(source="assumed", locator=""), ["repro.assumed_without_justification"])),
    ("param_no_locator", lambda: (par(locator=""), ["repro.parameter_no_locator"])),

    # response metrics: tolerance, basis, statistic, verdicts
    ("no_tolerance", lambda: (res(tolerance=""), ["repro.no_tolerance"])),
    ("no_comparison_basis", lambda: (res(comparison_basis=""), ["repro.no_comparison_basis"])),
    ("no_statistic", lambda: (res(statistic=""), ["repro.no_statistic"])),
    ("metric_no_verdict",
     lambda: (res(metrics=[{"name": "转化率", "paper": 0.82, "reproduced": 0.71}]),
              ["repro.metric_no_verdict"])),
    ("tradeoff_unclassified",
     lambda: (res(metrics=[{"name": "转化率", "paper": 0.82, "reproduced": 0.71,
                            "within_tolerance": False}]),
              ["repro.difference_unclassified"])),
    ("tradeoff_unexplained",
     lambda: (res(metrics=[{"name": "转化率", "paper": 0.82, "reproduced": 0.71,
                            "within_tolerance": False, "delta_class": "methodological"}]),
              ["repro.difference_unexplained"])),

    # the graded recommendation
    ("verdict_unclassified", lambda: (ck(verdict="mostly fine"),
                                      ["repro.verdict_unclassified"])),
    ("verdict_without_basis", lambda: (ck(verdict_basis=""), ["repro.verdict_without_basis"])),
]


def main() -> int:
    rows = []
    for name, builder in SCEN:
        spec, expect = builder()
        findings, status, counts = S.run(spec, "reproduce")
        fired = {f["rule"] for f in findings}
        missing = [r for r in expect if r not in fired]
        spurious = [] if expect else [f["rule"] for f in findings]
        ok = not missing and not spurious
        rows.append({"scenario": name, "expected": expect, "fired": sorted(fired),
                     "missing": missing, "spurious": spurious, "pass": ok,
                     "status": status})
        print(f"{'PASS' if ok else 'FAIL'}  {name:<30} missing={missing} spurious={spurious}")

    passed = sum(1 for r in rows if r["pass"])
    report = {"schema_version": "optimize-bench/v1", "scenarios": rows,
              "totals": {"passed": passed, "of": len(rows)},
              "note": ("One scenario per rule, aligned to the parameter-optimisation scoring "
                       "points. Clean baselines must report nothing.")}
    (Path(__file__).resolve().parent / "report_optimize.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n{passed}/{len(rows)} pass")
    return 0 if passed == len(rows) else 1


if __name__ == "__main__":
    raise SystemExit(main())
