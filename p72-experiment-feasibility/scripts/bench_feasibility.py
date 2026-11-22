"""Benchmark for the experiment-feasibility skill.

One scenario per rule, aligned to the scoring points this task states:

  a review a second reviewer can re-run
      -> stage_missing, no_commit, no_data_version, no_command, no_logs, no_exit_status
  resource checks against a recorded inventory (device ledger, purchase record, SOP)
      -> material_without_source, material_without_version, material_state_undeclared,
         material_no_license (+ dataset FP guard)
  conditions snapshot complete; plan-vs-inventory conflicts flagged
      -> environment_incomplete, env_conflict_unflagged
  parameters with provenance (SOP/manual vs assumed by the reviewer)
      -> parameter_source_undeclared, assumed_without_justification, parameter_no_locator
  tolerances and verdicts on every checkable claim
      -> no_tolerance, no_comparison_basis, no_statistic, metric_no_verdict,
         difference_unclassified, difference_unexplained
  a graded feasibility verdict with its condition list
      -> verdict_unclassified, verdict_without_basis

    python bench_feasibility.py
"""

from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import sections as S  # noqa: E402

BASE = {
    "commit": "protocol@v2.3",
    "data_version": "inventory@2024-06",
    "commands": ["python feasibility_check.py --protocol SOP-A07 --inventory lab"],
    "checklist": {
        "materials": [{"name": "超低温冰箱位", "source": "设备台账 2024-06",
                       "version": "MDF-86V58", "state": "present"}],
        "environment": {"dependencies": "审批与外部平台清单 v2",
                        "hardware": "低温冰箱 / 大容量离心机 / 二级生物安全柜",
                        "seed": "审查口径 rev2"},
        "parameters": [{"name": "保存温度", "source": "paper", "locator": "SOP-A07 §4.2"}],
        "run": {"logs": "reviews/feas-2024-06-12.log", "exit_status": "succeeded"},
        "results": {"tolerance": "±2 C", "comparison_basis": "方案声明值 vs 台账核查值",
                    "statistic": "逐项核查结果清单",
                    "metrics": [{"name": "保存温度达标", "paper": -80, "reproduced": -79,
                                 "within_tolerance": True}]},
        "verdict": "partially_reproducible",
        "verdict_basis": "设备与试剂已具备；动物伦理批件在审，取得批件后方可开工",
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

    # the review loop and its artefacts
    ("stage_missing", lambda: (ck(run=None), ["repro.stage_missing"])),
    ("no_protocol_version", lambda: (d(commit=""), ["repro.no_commit"])),
    ("no_inventory_snapshot", lambda: (d(data_version=""), ["repro.no_data_version"])),
    ("no_check_command", lambda: (d(commands=[]), ["repro.no_command"])),
    ("no_review_log", lambda: (ck(run={"exit_status": "succeeded"}), ["repro.no_logs"])),
    ("no_exit_status",
     lambda: (ck(run={"logs": "reviews/feas-2024-06-12.log"}), ["repro.no_exit_status"])),

    # resource checks with provenance
    ("resource_no_source", lambda: (mat(source=""), ["repro.material_without_source"])),
    ("resource_no_version", lambda: (mat(version=""), ["repro.material_without_version"])),
    ("resource_state_undeclared",
     lambda: (mat(state=""), ["repro.material_state_undeclared"])),
    # a declared script/protocol artefact must carry its license; a plain dataset need not
    ("script_no_license", lambda: (mat(kind="code"), ["repro.material_no_license"])),
    ("fp_dataset_no_license", lambda: (mat(kind="dataset"), [])),

    # the conditions snapshot; plan-vs-inventory conflict must be recorded
    ("conditions_incomplete",
     lambda: (env(hardware=""), ["repro.environment_incomplete"])),
    ("plan_inventory_conflict_unflagged",
     lambda: (env(dependencies_detail=[{"name": "保存温度上限", "paper_version": "-80 C",
                                        "actual_version": "-70 C"}]),
              ["repro.env_conflict_unflagged"])),

    # parameters with provenance
    ("param_source_undeclared",
     lambda: (par(source=""), ["repro.parameter_source_undeclared"])),
    ("assumed_without_justification",
     lambda: (par(source="assumed", locator=""), ["repro.assumed_without_justification"])),
    ("param_no_locator", lambda: (par(locator=""), ["repro.parameter_no_locator"])),

    # tolerance and verdicts on checkable claims
    ("no_tolerance", lambda: (res(tolerance=""), ["repro.no_tolerance"])),
    ("no_comparison_basis", lambda: (res(comparison_basis=""), ["repro.no_comparison_basis"])),
    ("no_statistic", lambda: (res(statistic=""), ["repro.no_statistic"])),
    ("check_no_verdict",
     lambda: (res(metrics=[{"name": "保存温度达标", "paper": -80, "reproduced": -70}]),
              ["repro.metric_no_verdict"])),
    ("gap_unclassified",
     lambda: (res(metrics=[{"name": "保存温度达标", "paper": -80, "reproduced": -70,
                            "within_tolerance": False}]),
              ["repro.difference_unclassified"])),
    ("gap_unexplained",
     lambda: (res(metrics=[{"name": "保存温度达标", "paper": -80, "reproduced": -70,
                            "within_tolerance": False, "delta_class": "methodological"}]),
              ["repro.difference_unexplained"])),

    # the graded feasibility verdict
    ("verdict_unclassified", lambda: (ck(verdict="看起来可行"),
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
        print(f"{'PASS' if ok else 'FAIL'}  {name:<36} missing={missing} spurious={spurious}")

    passed = sum(1 for r in rows if r["pass"])
    report = {"schema_version": "feasibility-bench/v1", "scenarios": rows,
              "totals": {"passed": passed, "of": len(rows)},
              "note": ("One scenario per rule, aligned to the feasibility-review scoring "
                       "points. Clean baselines must report nothing.")}
    (Path(__file__).resolve().parent / "report_feasibility.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n{passed}/{len(rows)} pass")
    return 0 if passed == len(rows) else 1


if __name__ == "__main__":
    raise SystemExit(main())
