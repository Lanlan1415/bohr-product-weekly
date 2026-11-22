"""Benchmark for the reproduction-and-verification skill.

One scenario per rule, aligned to the loop the task describes:

  material location -> environment -> parameters -> code run -> comparison -> verdict

plus the four artefacts another machine needs (commit, data version, command, logs) and the
requirement that an out-of-tolerance metric says whether the gap is numeric noise or
methodological.

    python bench_reproduce.py
"""

from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import sections as S  # noqa: E402

BASE = {
    "commit": "a1b2c3d4e5f6",
    "data_version": "dataset@2024-05",
    "commands": ["python train.py --config cfg/a.yaml"],
    "checklist": {
        "materials": [{"name": "dataset", "source": "repo", "version": "v1.2",
                       "state": "present"}],
        "environment": {"dependencies": "pinned in requirements.txt",
                        "hardware": "A100 40GB", "seed": "0"},
        "parameters": [{"name": "lr", "source": "paper", "value": "3e-4",
                        "locator": "Table 1, p.4"}],
        "run": {"logs": "logs/train.log", "exit_status": "succeeded"},
        "results": {"tolerance": "1e-3",
                    "comparison_basis": "Table 2 main metric",
                    "statistic": "mean of 5 seeds",
                    "metrics": [{"name": "accuracy", "paper": 0.912,
                                 "reproduced": 0.9108, "within_tolerance": True}]},
        "verdict": "reproducible",
        "verdict_basis": "all metrics within tolerance",
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

    # the loop and its artefacts
    ("stage_missing", lambda: (ck(run=None), ["repro.stage_missing"])),
    ("stage_unknown", lambda: (d(stages=["materials", "horoscope_reading"]),
                               ["repro.stage_unknown"])),
    ("no_stages", lambda: (d(stages=[]), ["repro.no_stages"])),
    ("no_commit", lambda: (d(commit=""), ["repro.no_commit"])),
    ("no_data_version", lambda: (d(data_version=""), ["repro.no_data_version"])),
    ("no_command", lambda: (d(commands=[]), ["repro.no_command"])),
    ("command_blank", lambda: (d(commands=["  ", ""]), ["repro.command_blank"])),
    ("no_logs", lambda: (ck(run={"exit_status": "succeeded"}), ["repro.no_logs"])),
    ("no_exit_status", lambda: (ck(run={"logs": "logs/train.log"}), ["repro.no_exit_status"])),

    # materials
    ("material_no_source", lambda: (mat(source=""), ["repro.material_without_source"])),
    ("material_no_version", lambda: (mat(version=""), ["repro.material_without_version"])),
    ("material_state_undeclared", lambda: (mat(state=""), ["repro.material_state_undeclared"])),
    # a declared code artefact must carry its license; a dataset without one is fine
    ("material_no_license", lambda: (mat(kind="code"), ["repro.material_no_license"])),
    ("fp_dataset_no_license", lambda: (mat(kind="dataset"), [])),

    # environment
    ("env_incomplete", lambda: (env(hardware=""), ["repro.environment_incomplete"])),
    ("env_conflict_unflagged",
     lambda: (env(dependencies_detail=[{"name": "torch", "paper_version": "2.1.0",
                                        "actual_version": "2.3.1"}]),
              ["repro.env_conflict_unflagged"])),

    # parameters
    ("parameter_source_undeclared", lambda: (par(source=""), ["repro.parameter_source_undeclared"])),
    ("assumed_without_justification",
     lambda: (par(source="assumed", locator=""), ["repro.assumed_without_justification"])),
    ("parameter_no_locator", lambda: (par(locator=""), ["repro.parameter_no_locator"])),
    # 跑得对: provenance without the value itself is not an executable parameter table
    ("parameter_no_value", lambda: (par(value=""), ["repro.parameter_no_value"])),

    # comparison
    ("no_tolerance", lambda: (res(tolerance=""), ["repro.no_tolerance"])),
    ("no_comparison_basis", lambda: (res(comparison_basis=""), ["repro.no_comparison_basis"])),
    ("no_statistic", lambda: (res(statistic=""), ["repro.no_statistic"])),
    # 对得上: neither number recorded means nothing is compared
    ("metric_value_missing",
     lambda: (res(metrics=[{"name": "accuracy"}]), ["repro.metric_value_missing"])),
    ("metric_no_verdict",
     lambda: (res(metrics=[{"name": "accuracy", "paper": 0.912, "reproduced": 0.80}]),
              ["repro.metric_no_verdict"])),
    ("difference_unclassified",
     lambda: (res(metrics=[{"name": "accuracy", "paper": 0.912, "reproduced": 0.80,
                            "within_tolerance": False}]),
              ["repro.difference_unclassified"])),
    ("difference_unexplained",
     lambda: (res(metrics=[{"name": "accuracy", "paper": 0.912, "reproduced": 0.80,
                            "within_tolerance": False, "delta_class": "methodological"}]),
              ["repro.difference_unexplained"])),

    # verdict
    ("verdict_unclassified", lambda: (ck(verdict="mostly fine"), ["repro.verdict_unclassified"])),
    ("verdict_without_basis", lambda: (ck(verdict_basis=""), ["repro.verdict_without_basis"])),
    # 讲得清: the grade must agree with its own record
    ("verdict_inconsistent_with_missing",
     lambda: (mat(state="missing"), ["repro.verdict_inconsistent_with_missing"])),
    ("partial_verdict_without_gaps",
     lambda: (ck(verdict="partially_reproducible", verdict_basis="some metrics matched"),
              ["repro.partial_verdict_without_gaps"])),
    ("fp_partial_with_gap",
     lambda: (ck(verdict="partially_reproducible", verdict_basis="accuracy out of tolerance",
                 results={"tolerance": "1e-3", "comparison_basis": "Table 2 main metric",
                          "statistic": "mean of 5 seeds",
                          "metrics": [{"name": "accuracy", "paper": 0.912, "reproduced": 0.80,
                                       "within_tolerance": False,
                                       "delta_class": "methodological",
                                       "explanation": "seed handling differs from the paper"}]}),
              [])),
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
        print(f"{'PASS' if ok else 'FAIL'}  {name:<28} missing={missing} spurious={spurious}")

    passed = sum(1 for r in rows if r["pass"])
    report = {"schema_version": "reproduce-bench/v1", "scenarios": rows,
              "totals": {"passed": passed, "of": len(rows)},
              "note": ("One scenario per rule, aligned to the reproduction loop and its "
                       "artefacts. Clean baselines must report nothing.")}
    (Path(__file__).resolve().parent / "report_reproduce.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n{passed}/{len(rows)} pass")
    return 0 if passed == len(rows) else 1


if __name__ == "__main__":
    raise SystemExit(main())
