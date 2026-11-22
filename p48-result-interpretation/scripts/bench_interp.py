"""Benchmark for the experiment-result interpretation engine.

Each scenario plants one defect (or proves one FP guard): grounded citation of
values and baselines, anomaly explanation coverage over both detectors (physical
range and IQR distribution), causal claims backed by a recorded cause, trend
direction consistency against the data's own movement, executable review steps,
and follow-up-experiment binding to recorded causes and stated risks — plus the
cleaning-pass findings the interpretation sits on and the CLI refusal paths. The
clean baseline must report nothing, so a detector cannot pass by flagging
everything.

    python bench_interp.py
"""

from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import cleandata as CL  # noqa: E402

BASE_ROWS = [
    {"sample": "S1", "batch": "B1", "hardness": "42.5", "cure_hours": "24"},
    {"sample": "S2", "batch": "B1", "hardness": "43.1", "cure_hours": "24"},
    {"sample": "S3", "batch": "B1", "hardness": "42.8", "cure_hours": "24"},
    {"sample": "S4", "batch": "B2", "hardness": "43.0", "cure_hours": "24"},
    {"sample": "S5", "batch": "B2", "hardness": "42.6", "cure_hours": "24"},
    {"sample": "S6", "batch": "B2", "hardness": "43.2", "cure_hours": "24"},
    {"sample": "S7", "batch": "B3", "hardness": "42.9", "cure_hours": "24"},
    {"sample": "S8", "batch": "B3", "hardness": "43.3", "cure_hours": "24"},
]
BASE_OBS = {
    "observation": "S2 硬度 43.1，处于批次 B1 基线 42.5 附近的正常波动范围",
    "value": 43.1,
    "baseline": 42.5,
    "explanation": "同批次平行样之间的正常波动，未触发剔除条件",
}
BASE = {
    "rows": copy.deepcopy(BASE_ROWS),
    "columns": [
        {"name": "sample", "semantic": "id"},
        {"name": "batch", "semantic": "categorical"},
        {"name": "hardness", "semantic": "numeric", "plausible": [0, 46]},
        {"name": "cure_hours", "semantic": "numeric"},
    ],
    "observations": [copy.deepcopy(BASE_OBS)],
}


def scen_clean():
    return "run", (copy.deepcopy(BASE["rows"]), copy.deepcopy(BASE)), []


def scen_value_not_in_data():
    s = copy.deepcopy(BASE)
    s["observations"] = [{"observation": "B3 批次硬度峰值 99.9", "value": 99.9,
                          "explanation": "远高于其他批次"}]
    return "run", (copy.deepcopy(s["rows"]), s), ["observation.value_not_in_data"]


def scen_baseline_not_in_data():
    s = copy.deepcopy(BASE)
    s["observations"][0]["baseline"] = 99.0
    return "run", (copy.deepcopy(s["rows"]), s), ["observation.value_not_in_data"]


def scen_outlier_unexplained():
    """A value beyond the declared physical range is flagged by two detectors."""
    s = copy.deepcopy(BASE)
    s["rows"][7]["hardness"] = "47.9"
    return "run", (copy.deepcopy(s["rows"]), s), ["anomaly.unexplained"]


def scen_outlier_explained_fp():
    """FP guard: the same outlier with a keep/drop/cap reason stays silent."""
    s = copy.deepcopy(BASE)
    s["rows"][7]["hardness"] = "47.9"
    s["observations"] = [{
        "observation": "S8 硬度 47.9，超出批内分布",
        "value": 47.9,
        "explanation": "超出该列物理合理上限与批内分布，建议剔除后复核 B3 批次记录，"
                       "报告中按剔除口径重算",
    }]
    return "run", (copy.deepcopy(s["rows"]), s), []


def scen_iqr_unexplained():
    """A value inside the physical range but far outside its own distribution."""
    s = copy.deepcopy(BASE)
    s["rows"][7]["hardness"] = "49.9"
    s["columns"][2]["plausible"] = [0, 100]
    return "run", (copy.deepcopy(s["rows"]), s), ["anomaly.unexplained"]


def scen_cause_asserted():
    s = copy.deepcopy(BASE)
    s["observations"] = [{"observation": "S5 硬度 42.6 偏低", "value": 42.6,
                          "explanation": "由于搅拌不均匀导致该样品固化不足"}]
    return "run", (copy.deepcopy(s["rows"]), s), ["anomaly.cause_asserted"]


def scen_cause_recorded_fp():
    """FP guard: the same causal wording with a recorded cause and an
    executable review step stays silent."""
    s = copy.deepcopy(BASE)
    s["observations"] = [{"observation": "S5 硬度 42.6 偏低", "value": 42.6,
                          "explanation": "由于搅拌不均匀导致该样品固化不足",
                          "cause": {"factor": "搅拌不均匀",
                                    "evidence": "B2 批搅拌日志缺失 12 分钟记录"},
                          "review_steps": ["回查 B2 批搅拌日志的搅拌时长字段"]}]
    return "run", (copy.deepcopy(s["rows"]), s), []


def scen_malformed_observation():
    s = copy.deepcopy(BASE)
    s["observations"] = ["S5 硬度偏低，原因待查", copy.deepcopy(BASE_OBS)]
    return "run", (copy.deepcopy(s["rows"]), s), ["observation.malformed"]


def scen_missing_named():
    """A not-reported cell is a named missing value in the cleaning pass."""
    s = copy.deepcopy(BASE)
    s["rows"][3]["hardness"] = "not reported"
    s["observations"] = []
    return "run", (copy.deepcopy(s["rows"]), s), ["clean.missing_values"]


def scen_duplicate_records():
    """Identical rows report as low-severity record copies, reviewable not blocking."""
    s = copy.deepcopy(BASE)
    s["rows"].append(copy.deepcopy(s["rows"][0]))
    s["key_columns"] = ["sample"]
    s["observations"] = []
    return "run", (copy.deepcopy(s["rows"]), s), ["clean.duplicate_records"]


def scen_units_in_cell_fp():
    """FP guard: values cited from unit-bearing cells still ground correctly."""
    s = copy.deepcopy(BASE)
    for r in s["rows"]:
        r["hardness"] = r["hardness"] + " MPa"
    return "run", (copy.deepcopy(s["rows"]), s), []


def scen_cli_unreadable_spec():
    """A spec that is not JSON is refused with exit-5 semantics, never a crash."""
    return "cli", "{ this is not json", ["clean.spec_unreadable"]


def scen_cli_no_rows():
    """A spec with neither rows nor a readable table_path is refused."""
    return "cli", {"columns": [{"name": "hardness"}]}, ["clean.spec_unreadable"]


# ---------------------------------------------------------------------------
# five-part mechanical rules: trend / review / next experiments
# ---------------------------------------------------------------------------

TREND_RISING = [
    {"sample": "T1", "cycle": "1", "strength": "10.0"},
    {"sample": "T2", "cycle": "2", "strength": "11.0"},
    {"sample": "T3", "cycle": "3", "strength": "12.0"},
    {"sample": "T4", "cycle": "4", "strength": "12.9"},
    {"sample": "T5", "cycle": "5", "strength": "14.0"},
]
TREND_FLAT_ROWS = [
    {"sample": "T1", "cycle": "1", "strength": "10.0"},
    {"sample": "T2", "cycle": "2", "strength": "10.0"},
    {"sample": "T3", "cycle": "3", "strength": "10.0"},
    {"sample": "T4", "cycle": "4", "strength": "9.99"},
    {"sample": "T5", "cycle": "5", "strength": "10.0"},
]
TREND_COLUMNS = [
    {"name": "sample", "semantic": "id"},
    {"name": "cycle", "semantic": "numeric"},
    {"name": "strength", "semantic": "numeric", "plausible": [0, 100]},
]


def _trend_spec(rows, obs):
    s = copy.deepcopy(BASE)
    s["rows"] = copy.deepcopy(rows)
    s["columns"] = copy.deepcopy(TREND_COLUMNS)
    s["trend"] = {"order_column": "cycle"}
    s["observations"] = [obs]
    return s


def scen_trend_mismatch_high():
    """A direction claim the data contradicts is a high finding: computed flat,
    claimed up."""
    obs = {"observation": "强度随循环次数上升", "value": 10.0, "metric": "strength",
           "trend_claim": {"metric": "strength", "direction": "up"},
           "explanation": "判读为上升趋势"}
    s = _trend_spec(TREND_FLAT_ROWS, obs)
    return "run", (copy.deepcopy(s["rows"]), s), ["trend.direction_mismatch"]


def scen_trend_match_fp():
    """FP guard: the same claim over actually rising data stays silent, and the
    audit records the claim as checked."""
    obs = {"observation": "强度随循环次数上升", "value": 14.0, "metric": "strength",
           "trend_claim": {"metric": "strength", "direction": "up"},
           "explanation": "五个循环单调上升"}
    s = _trend_spec(TREND_RISING, obs)
    return "run", (copy.deepcopy(s["rows"]), s), []


def scen_trend_word_no_order():
    """A direction word with no order column cannot be verified: named, not guessed."""
    obs = {"observation": "强度随循环次数上升", "value": 14.0, "metric": "strength",
           "explanation": "判读为上升趋势"}
    s = _trend_spec(TREND_RISING, obs)
    del s["trend"]
    return "run", (copy.deepcopy(s["rows"]), s), ["trend.unverifiable"]


def scen_trend_word_match_fp():
    """FP guard: a direction word plus declared metric and order column over
    agreeing data stays silent."""
    obs = {"observation": "强度随循环次数上升", "value": 14.0, "metric": "strength",
           "explanation": "判读为上升趋势"}
    s = _trend_spec(TREND_RISING, obs)
    return "run", (copy.deepcopy(s["rows"]), s), []


def scen_trend_mixed_words_fp():
    """FP guard: opposite direction words in one sentence are not judged — the
    engine records a limit instead of guessing which word applies."""
    obs = {"observation": "强度先上升后下降，末段持平", "value": 10.0, "metric": "strength",
           "explanation": "走势复杂，需分段判读"}
    s = _trend_spec(TREND_FLAT_ROWS, obs)
    return "run", (copy.deepcopy(s["rows"]), s), []


def scen_review_not_executable():
    """The named anti-pattern: 检查数据质量 has no executable verb or target."""
    s = copy.deepcopy(BASE)
    s["observations"][0]["review_steps"] = ["检查数据质量", "注意异常值"]
    return "run", (copy.deepcopy(s["rows"]), s), ["review.not_executable"]


def scen_review_executable_fp():
    """FP guard: verb + concrete target passes the executability check."""
    s = copy.deepcopy(BASE)
    s["observations"][0]["review_steps"] = [
        "回查 B3 批次 cure_log.csv 的 cure_hours 字段",
        "复算剔除 S8 后批内均值"]
    return "run", (copy.deepcopy(s["rows"]), s), []


def scen_review_missing_for_cause():
    """A recorded cause without any review step has no exclusion process."""
    s = copy.deepcopy(BASE)
    s["observations"] = [{"observation": "S5 硬度 42.6 偏低", "value": 42.6,
                          "explanation": "由于搅拌不均匀导致该样品固化不足",
                          "cause": {"factor": "搅拌不均匀",
                                    "evidence": "B2 批搅拌日志缺失 12 分钟记录"}}]
    return "run", (copy.deepcopy(s["rows"]), s), ["review.missing_for_cause"]


def scen_review_step_malformed():
    """A non-string review step is named, not silently skipped."""
    s = copy.deepcopy(BASE)
    s["observations"][0]["review_steps"] = ["回查原始记录表字段", 42]
    return "run", (copy.deepcopy(s["rows"]), s), ["review.step_malformed"]


def scen_next_unbound_and_risk():
    """A suggestion with no addresses and no risk fires both binding rules."""
    s = copy.deepcopy(BASE)
    s["observations"][0]["next_experiments"] = [{"change": "加密采样点"}]
    return "run", (copy.deepcopy(s["rows"]), s), ["next.unbound", "next.risk_missing"]


def scen_next_dangling():
    """A suggestion bound to a cause that is recorded nowhere dangles."""
    s = copy.deepcopy(BASE)
    s["observations"][0]["next_experiments"] = [
        {"change": "提高固化温度", "addresses": "温度过高", "risk": "设备上限 50 C"}]
    return "run", (copy.deepcopy(s["rows"]), s), ["next.dangling"]


def scen_next_bound_fp():
    """FP guard: change + recorded factor + risk stays silent."""
    s = copy.deepcopy(BASE)
    s["observations"][0].update({
        "explanation": "由于搅拌不均匀导致该样品固化不足",
        "cause": {"factor": "搅拌不均匀", "evidence": "B2 批搅拌日志缺失 12 分钟记录"},
        "review_steps": ["回查 B2 批搅拌日志的搅拌时长字段"],
        "next_experiments": [{"change": "补做搅拌时间对照", "addresses": "搅拌不均匀",
                              "risk": "设备占用 2 小时"}],
    })
    return "run", (copy.deepcopy(s["rows"]), s), []


def scen_metric_scoped_fp():
    """FP guard: a metric-scoped observation grounds correctly (regression for
    the NameError the metric scope used to raise)."""
    s = copy.deepcopy(BASE)
    s["observations"][0]["metric"] = "hardness"
    return "run", (copy.deepcopy(s["rows"]), s), []


SCENARIOS = [
    ("clean", scen_clean),
    ("value_not_in_data", scen_value_not_in_data),
    ("baseline_not_in_data", scen_baseline_not_in_data),
    ("outlier_unexplained", scen_outlier_unexplained),
    ("outlier_explained_fp", scen_outlier_explained_fp),
    ("iqr_unexplained", scen_iqr_unexplained),
    ("cause_asserted", scen_cause_asserted),
    ("cause_recorded_fp", scen_cause_recorded_fp),
    ("malformed_observation", scen_malformed_observation),
    ("missing_named", scen_missing_named),
    ("duplicate_records", scen_duplicate_records),
    ("units_in_cell_fp", scen_units_in_cell_fp),
    ("trend_mismatch_high", scen_trend_mismatch_high),
    ("trend_match_fp", scen_trend_match_fp),
    ("trend_word_no_order", scen_trend_word_no_order),
    ("trend_word_match_fp", scen_trend_word_match_fp),
    ("trend_mixed_words_fp", scen_trend_mixed_words_fp),
    ("review_not_executable", scen_review_not_executable),
    ("review_executable_fp", scen_review_executable_fp),
    ("review_missing_for_cause", scen_review_missing_for_cause),
    ("review_step_malformed", scen_review_step_malformed),
    ("next_unbound_and_risk", scen_next_unbound_and_risk),
    ("next_dangling", scen_next_dangling),
    ("next_bound_fp", scen_next_bound_fp),
    ("metric_scoped_fp", scen_metric_scoped_fp),
    ("cli_unreadable_spec", scen_cli_unreadable_spec),
    ("cli_no_rows", scen_cli_no_rows),
]


def run_one(name, builder, root: Path) -> dict:
    kind, payload, expect = builder()
    out = root / name
    out.mkdir(parents=True, exist_ok=True)
    extra = ""
    if kind == "cli":
        sp = out / "spec.json"
        if isinstance(payload, str):
            sp.write_text(payload, encoding="utf-8")
        else:
            sp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        r = CL.build_and_audit(sp, out / "res")
    else:
        rows, spec = payload
        r = CL.run(rows, spec)
    fired = {f["rule"] for f in r["findings"]}
    missing = [x for x in expect if x not in fired]
    spurious = []
    if not expect:
        spurious = [f["rule"] for f in r["findings"] if f["severity"] in ("high", "medium")]
    if name == "clean":
        s = r["interpretation_audit"]
        if s["n_flagged_anomalies"] != 0 or s["n_observations"] != 1:
            missing.append("interp_summary")
        extra = f" flagged={s['n_flagged_anomalies']} obs={s['n_observations']}"
    if name == "outlier_explained_fp":
        s = r["interpretation_audit"]
        if s["n_flagged_anomalies"] != 2 or s["n_explained_anomalies"] != 2:
            missing.append("explained_coverage")
        extra += f" flagged={s['n_flagged_anomalies']} explained={s['n_explained_anomalies']}"
    if name == "outlier_unexplained":
        s = r["interpretation_audit"]
        if s["n_flagged_anomalies"] != 2:
            missing.append("two_detectors")
        extra += f" flagged={s['n_flagged_anomalies']}"
    return {"scenario": name, "expected": expect, "fired": sorted(fired),
            "missing": missing, "spurious": spurious, "status": r["status"],
            "pass": not missing and not spurious, "extra": extra.strip()}


def main() -> int:
    root = Path(__file__).resolve().parent / "_run"
    rows = [run_one(n, b, root) for n, b in SCENARIOS]
    passed = sum(1 for r in rows if r["pass"])
    report = {
        "schema_version": "interp-bench/v1",
        "scenarios": rows,
        "totals": {"passed": passed, "of": len(rows)},
        "note": ("Each scenario plants one defect or proves one FP guard. The clean "
                 "baseline must report no high or medium finding, and the anomaly "
                 "summary counts are asserted against the planted data."),
    }
    (Path(__file__).resolve().parent.parent / "report_interp.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    for r in rows:
        print(("PASS" if r["pass"] else "FAIL") + f"  {r['scenario']:<26}"
              f" missing={r['missing']} spurious={r['spurious']}"
              + ((" |" + r["extra"]) if r["extra"] else ""))
    print(f"\n{passed}/{len(rows)} scenarios pass")
    return 0 if passed == len(rows) else 1


if __name__ == "__main__":
    raise SystemExit(main())
