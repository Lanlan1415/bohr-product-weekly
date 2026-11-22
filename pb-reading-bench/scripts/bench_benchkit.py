"""Benchmark for the benchmark harness itself.

Each scenario asserts one of the four properties both benchmark tasks name, using the harness on a
small item set. Half of them assert a refusal, because a benchmark that grades everything as fine
is worse than no benchmark.

  判得动 / 题能判定   an item whose criterion is free text is refused at load
  跑得一致 / 可复现   two runs agree; a rubric is not order- or hash-dependent
  查得回             a score traces to its output, config and the criterion that failed
  改得动             a failure becomes a targeted item, and only that item is recomputed

The scoring table and direction list add five more families, each with a defect scenario and a
false-positive guard (correct input must yield zero findings):

  原始输出留存        a run record retains each raw output verbatim; a clean run scores unchanged
  异常处理            an empty output and a malformed output are their own failure kinds
  失败样例库          failures() indexes errors by type with item, output and reason; a clean
                      run yields an empty library
  版本对比            diff_itemsets() names changed card fields and the still-comparable scores
  评分表              a declared "0-1-2" scale bands every score; an unsupported scale is
                      refused; a declared manual criterion is deferred to human review; an
                      undeclared scale changes nothing

    python bench_benchkit.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import benchkit as K  # noqa: E402

INPUT_DOC = ("Uptake rose three-fold under the coating. Only one thickness was tested, so the "
             "result does not generalise.")

ITEMS = [
    {"id": "R1", "task": "state the measured effect", "input": INPUT_DOC,
     "reference": "uptake rose three-fold",
     "rubric": [
         {"criterion": "effect stated", "predicate": "contains", "weight": 50,
          "values": ["three-fold"]},
         {"criterion": "quote located", "predicate": "anchor", "weight": 50,
          "field": "quote"},
     ]},
    {"id": "R2", "task": "state the limitation", "input": INPUT_DOC,
     "reference": "only one thickness",
     "rubric": [
         {"criterion": "limitation named", "predicate": "contains", "weight": 60,
          "values": ["thickness"]},
         {"criterion": "no invented numbers", "predicate": "not_contains", "weight": 40,
          "values": ["p < 0.05"]},
     ]},
]

GOOD = {
    "R1": {"text": "Uptake rose three-fold under the coating.",
           "quote": "Uptake rose three-fold"},
    "R2": {"text": "Only one coating thickness was tested."},
}


def scen(name: str, fn) -> dict:
    try:
        return fn(name)
    except Exception as exc:  # a crash is a failure of the harness, not of the scenario
        return {"name": name, "pass": False, "why": f"raised {type(exc).__name__}: {exc}"}


def s_items_valid(name: str) -> dict:
    v = K.validate_itemset(ITEMS)
    return {"name": name, "pass": v["ok"], "why": json.dumps(v["problems"])[:110]}


def s_freetext_criterion_refused(name: str) -> dict:
    bad = [{"id": "X1", "task": "t", "input": INPUT_DOC, "reference": "r",
            "rubric": [{"criterion": "reads well", "predicate": "prose", "weight": 100}]}]
    v = K.validate_itemset(bad)
    ok = not v["ok"] and any("not one of" in p["reason"] for p in v["problems"])
    return {"name": name, "pass": ok, "why": json.dumps(v["problems"])[:110]}


def s_weights_must_sum(name: str) -> dict:
    bad = [{"id": "X2", "task": "t", "input": INPUT_DOC, "reference": "r",
            "rubric": [{"criterion": "c", "predicate": "contains", "weight": 40,
                        "values": ["x"]}]}]
    v = K.validate_itemset(bad)
    ok = not v["ok"] and any("sum to" in p["reason"] for p in v["problems"])
    return {"name": name, "pass": ok, "why": json.dumps(v["problems"])[:110]}


def s_grading_is_exact(name: str) -> dict:
    rec = K.run(ITEMS, GOOD)
    r1 = next(x for x in rec["results"] if x["item_id"] == "R1")
    r2 = next(x for x in rec["results"] if x["item_id"] == "R2")
    ok = r1["score"] == 100 and r2["score"] == 100 and rec["total"] == 100
    return {"name": name, "pass": ok, "why": f"R1={r1['score']} R2={r2['score']}"}


def s_anchor_catches_unsourced(name: str) -> dict:
    """An answer quoting text that is not in the input must fail the anchor criterion."""
    bad = dict(GOOD)
    bad["R1"] = {"text": "Uptake rose three-fold.", "quote": "Uptake rose five-fold"}
    rec = K.run(ITEMS, bad)
    r1 = next(x for x in rec["results"] if x["item_id"] == "R1")
    ok = r1["score"] == 50 and r1["failure_type"] == "evidence_not_located"
    return {"name": name, "pass": ok,
            "why": f"score={r1['score']} type={r1['failure_type']}"}


def s_reproducible(name: str) -> dict:
    rep = K.reproduce(ITEMS, GOOD, {"model": "x", "budget": 64})
    same_config = K.run(ITEMS, GOOD, {"model": "x", "budget": 64})["run_id"] == \
                  K.run(ITEMS, GOOD, {"model": "x", "budget": 64})["run_id"]
    ok = rep["stable"] and same_config
    return {"name": name, "pass": ok, "why": f"stable={rep['stable']} deltas={rep['deltas']}"}


def s_traceable(name: str) -> dict:
    bad = dict(GOOD)
    bad["R2"] = {"text": "Only one coating thickness was tested, p < 0.05."}
    rec = K.run(ITEMS, bad, {"model": "x"})
    tr = K.trace(rec, "R2")
    ok = (tr["ok"] and tr["failure_type"] == "forbidden_content"
          and tr["decided_by"] and tr["config"] == {"model": "x"})
    return {"name": name, "pass": ok, "why": json.dumps(tr)[:110]}


def s_retarget(name: str) -> dict:
    bad = dict(GOOD)
    bad["R2"] = {"text": "The limitation was not stated."}
    rec = K.run(ITEMS, bad)
    new_item = {"id": "R2b", "task": "state the limitation in one sentence",
                "input": INPUT_DOC, "reference": "only one thickness",
                "rubric": [{"criterion": "limitation named", "predicate": "contains",
                            "weight": 100, "values": ["thickness"]}]}
    res = K.retarget(ITEMS, rec, "R2", new_item)
    ok = (res.get("ok") and res["recompute_only"] == ["R2b"]
          and "R1" in res["unchanged_scores"] and res["from_version"] != res["to_version"])
    return {"name": name, "pass": ok, "why": json.dumps(res)[:110]}


def s_retarget_needs_failure(name: str) -> dict:
    rec = K.run(ITEMS, GOOD)
    res = K.retarget(ITEMS, rec, "R1", {"id": "R1b", "task": "t", "input": "i", "reference": "r",
                                        "rubric": [{"criterion": "c", "predicate": "contains",
                                                    "weight": 100, "values": ["x"]}]})
    ok = not res.get("ok") and "did not fail" in res.get("reason", "")
    return {"name": name, "pass": ok, "why": json.dumps(res)[:110]}


def s_unattempted_is_zero(name: str) -> dict:
    rec = K.run(ITEMS, {"R1": GOOD["R1"]})
    r2 = next(x for x in rec["results"] if x["item_id"] == "R2")
    ok = r2["score"] == 0 and r2["failure_type"] == "not_attempted"
    return {"name": name, "pass": ok, "why": r2["failure_type"]}


# --- 原始输出留存 (查得回 names the raw output, not just a digest of it) ----------------

def s_raw_output_retained(name: str) -> dict:
    rec = K.run(ITEMS, GOOD)
    kept = all(r.get("raw_output") == GOOD[r["item_id"]] for r in rec["results"])
    tr = K.trace(rec, "R1")
    ok = kept and rec["total"] == 100 and tr["ok"] and tr["raw_output"] == GOOD["R1"]
    return {"name": name, "pass": ok,
            "why": f"total={rec['total']} trace-has-raw={tr.get('raw_output') is not None}"}


# --- 异常处理: 输出为空 / 格式不合规 are identified, not misattributed ------------------

def s_empty_output_identified(name: str) -> dict:
    rec = K.run(ITEMS, {"R1": GOOD["R1"], "R2": "   "})
    r2 = next(x for x in rec["results"] if x["item_id"] == "R2")
    ok = (r2["score"] == 0 and r2["failure_type"] == "empty_output"
          and r2["raw_output"] == "   "
          and rec["failures_by_type"].get("empty_output") == 1)
    return {"name": name, "pass": ok, "why": f"type={r2['failure_type']} tally={rec['failures_by_type']}"}


def s_malformed_output_identified(name: str) -> dict:
    rec = K.run(ITEMS, {"R1": GOOD["R1"], "R2": ["thickness", "p < 0.05"]})
    r1 = next(x for x in rec["results"] if x["item_id"] == "R1")
    r2 = next(x for x in rec["results"] if x["item_id"] == "R2")
    ok = (r2["failure_type"] == "malformed_output" and r2["score"] == 0
          and "list" in str(r2.get("note"))
          and r1["score"] == 100)  # a structured dict output is legitimate, never malformed
    return {"name": name, "pass": ok,
            "why": f"type={r2['failure_type']} dict-R1={r1['score']}"}


# --- 失败样例库: errors indexed by type with item, raw output and reason ----------------

def s_failures_library(name: str) -> dict:
    bad = dict(GOOD)
    bad["R2"] = "The limitation was not stated."
    rec = K.run(ITEMS, bad)
    lib = K.failures(ITEMS, rec)
    samples = lib.get("missing_required_point") or []
    ok = (bool(samples)
          and samples[0]["item_id"] == "R2"
          and samples[0]["task"] == "state the limitation"
          and samples[0]["raw_output"] == bad["R2"]
          and samples[0]["failed_criteria"][0]["criterion"] == "limitation named")
    return {"name": name, "pass": ok,
            "why": json.dumps({k: len(v) for k, v in lib.items()})[:110]}


def s_failures_clean_run_fp(name: str) -> dict:
    """FP guard: a correct run leaves the failure library empty."""
    rec = K.run(ITEMS, GOOD)
    lib = K.failures(ITEMS, rec)
    ok = lib == {}
    return {"name": name, "pass": ok, "why": json.dumps(lib)[:110]}


# --- 版本对比: changed card fields, and which historical scores stay comparable ----------

def s_diff_itemsets_changed(name: str) -> dict:
    v2 = json.loads(json.dumps(ITEMS))
    v2[1]["rubric"] = [{"criterion": "limitation named", "predicate": "contains", "weight": 100,
                        "values": ["thickness"]}]
    d = K.diff_itemsets(ITEMS, v2)
    ok = (d["changed"] == [{"id": "R2", "fields": ["rubric"]}]
          and d["added"] == [] and d["removed"] == []
          and d["comparable_scores"] == ["R1"]
          and d["old_digest"] != d["new_digest"] and bool(d["note"]))
    return {"name": name, "pass": ok,
            "why": f"changed={d['changed']} comparable={d['comparable_scores']}"}


def s_diff_itemsets_identical_fp(name: str) -> dict:
    """FP guard: two identical versions differ in nothing and everything stays comparable."""
    d = K.diff_itemsets(ITEMS, ITEMS)
    ok = (not d["added"] and not d["removed"] and not d["changed"]
          and d["comparable_scores"] == ["R1", "R2"] and d["old_digest"] == d["new_digest"])
    return {"name": name, "pass": ok, "why": f"changed={d['changed']}"}


# --- 评分表: declared 0-1-2 scale, and declared human review -----------------------------

def s_scale_012_declared(name: str) -> dict:
    bad = dict(GOOD)
    bad["R2"] = "Only one coating thickness was tested, p < 0.05."  # 60/100 -> partial
    rec = K.run(ITEMS, bad, {"model": "x", "score_scale": "0-1-2"})
    r1 = next(x for x in rec["results"] if x["item_id"] == "R1")
    r2 = next(x for x in rec["results"] if x["item_id"] == "R2")
    ok = (r1["score_012"] == 2 and r2["score_012"] == 1
          and rec["score_scale"] == "0-1-2" and rec["total"] == 80.0)
    return {"name": name, "pass": ok,
            "why": f"R1={r1['score_012']} R2={r2['score_012']} scale={rec.get('score_scale')}"}


def s_scale_unsupported_refused(name: str) -> dict:
    try:
        K.run(ITEMS, GOOD, {"score_scale": "0-5"})
        ok, why = False, "no refusal raised"
    except K.ItemError as exc:
        ok, why = "not supported" in str(exc), str(exc)[:90]
    return {"name": name, "pass": ok, "why": why}


def s_scale_undeclared_fp(name: str) -> dict:
    """FP guard: without a declared scale, nothing is banded and nothing is flagged."""
    rec = K.run(ITEMS, GOOD, {"model": "x"})
    ok = ("score_scale" not in rec
          and all("score_012" not in r for r in rec["results"]) and rec["total"] == 100)
    return {"name": name, "pass": ok,
            "why": f"scale-absent={('score_scale' not in rec)} total={rec['total']}"}


def s_manual_criterion_deferred(name: str) -> dict:
    item = {"id": "M1", "task": "assess the wording", "input": INPUT_DOC,
            "reference": "uptake rose three-fold",
            "rubric": [
                {"criterion": "effect stated", "predicate": "contains", "weight": 60,
                 "values": ["three-fold"]},
                {"criterion": "terminology judged by a human", "predicate": "manual",
                 "weight": 40, "note": "check terms against the paper's own usage"},
            ]}
    v = K.validate_itemset([item])
    rec = K.run([item], {"M1": {"text": "Uptake rose three-fold under the coating."}})
    r = rec["results"][0]
    crit = next(c for c in r["criteria"] if c["predicate"] == "manual")
    ok = (v["ok"] and r["score"] == 100 and r["failure_type"] is None
          and r.get("needs_review") == ["terminology judged by a human"]
          and crit["passed"] is None and "human review" in crit["evidence"])
    return {"name": name, "pass": ok,
            "why": f"score={r['score']} review={r.get('needs_review')}"}


def s_manual_without_note_refused(name: str) -> dict:
    bad = [{"id": "X3", "task": "t", "input": INPUT_DOC, "reference": "r",
            "rubric": [{"criterion": "c", "predicate": "contains", "weight": 50,
                        "values": ["x"]},
                       {"criterion": "h", "predicate": "manual", "weight": 50}]}]
    v = K.validate_itemset(bad)
    ok = not v["ok"] and any("needs a note" in p["reason"] for p in v["problems"])
    return {"name": name, "pass": ok, "why": json.dumps(v["problems"])[:110]}


def s_items_without_manual_unaffected_fp(name: str) -> dict:
    """FP guard: items with no manual criterion behave exactly as before."""
    rec = K.run(ITEMS, GOOD)
    ok = (all("needs_review" not in r for r in rec["results"])
          and all(c["passed"] is not None for r in rec["results"] for c in r["criteria"])
          and rec["total"] == 100)
    return {"name": name, "pass": ok, "why": f"total={rec['total']}"}


# --- 题集管理: declared optional card fields are checked; absent ones never punished ------

def s_optional_card_fields_empty_refused(name: str) -> dict:
    bad = [{"id": "X4", "task": "t", "input": INPUT_DOC, "reference": "r",
            "difficulty": "", "license": None,
            "rubric": [{"criterion": "c", "predicate": "contains", "weight": 100,
                        "values": ["x"]}]}]
    v = K.validate_itemset(bad)
    reasons = {p["reason"] for p in v["problems"]}
    ok = (not v["ok"] and "difficulty declared but empty" in reasons
          and "license declared but empty" in reasons)
    return {"name": name, "pass": ok, "why": json.dumps(v["problems"])[:110]}


def s_optional_card_fields_valid_fp(name: str) -> dict:
    """FP guard: well-formed declared fields and absent fields alike produce zero problems."""
    good = [{"id": "X5", "task": "t", "input": INPUT_DOC, "reference": "r",
             "difficulty": "hard", "license": "CC BY 4.0",
             "rubric": [{"criterion": "c", "predicate": "contains", "weight": 100,
                         "values": ["x"]}]}]
    v = K.validate_itemset(good)
    return {"name": name, "pass": v["ok"], "why": json.dumps(v["problems"])[:110]}


# --- 结果面板: strengths, weaknesses and distributions across agents and versions ---------

def s_panel_groups(name: str) -> dict:
    good = K.run(ITEMS, GOOD, {"agent": "base"})
    bad_out = dict(GOOD)
    bad_out["R2"] = "The limitation was not stated."
    bad = K.run(ITEMS, bad_out, {"agent": "skill"})
    p = K.panel([good, bad])
    gs = {g["agent"]: g for g in p["groups"]}
    ok = (len(p["groups"]) == 2
          and gs["base"]["total_distribution"]["mean"] == 100
          and gs["base"]["failures_by_type"] == {}
          and gs["skill"]["items"]["R2"]["max"] < 100
          and sum(gs["skill"]["failures_by_type"].values()) >= 1)
    return {"name": name, "pass": ok,
            "why": f"agents={[g['agent'] for g in p['groups']]}"}


def s_panel_clean_run_fp(name: str) -> dict:
    """FP guard: a single perfect run aggregates to one clean group with zero failures."""
    p = K.panel([K.run(ITEMS, GOOD, {"agent": "solo"})])
    g = p["groups"][0]
    ok = (len(p["groups"]) == 1 and g["total_distribution"]["mean"] == 100
          and g["failures_by_type"] == {})
    return {"name": name, "pass": ok, "why": json.dumps(g["total_distribution"])[:110]}


SCEN = [s_items_valid, s_freetext_criterion_refused, s_weights_must_sum, s_grading_is_exact,
        s_anchor_catches_unsourced, s_reproducible, s_traceable, s_retarget,
        s_retarget_needs_failure, s_unattempted_is_zero,
        s_raw_output_retained, s_empty_output_identified, s_malformed_output_identified,
        s_failures_library, s_failures_clean_run_fp,
        s_diff_itemsets_changed, s_diff_itemsets_identical_fp,
        s_scale_012_declared, s_scale_unsupported_refused, s_scale_undeclared_fp,
        s_manual_criterion_deferred, s_manual_without_note_refused,
        s_items_without_manual_unaffected_fp,
        s_optional_card_fields_empty_refused, s_optional_card_fields_valid_fp,
        s_panel_groups, s_panel_clean_run_fp]


def main() -> int:
    rows = [scen(fn.__name__.replace("s_", ""), fn) for fn in SCEN]
    for r in rows:
        print(f"{'PASS' if r['pass'] else 'FAIL'}  {r['name']:<30} {r['why']}")
    passed = sum(1 for r in rows if r["pass"])
    report = {"schema_version": "benchkit-bench/v1", "scenarios": rows,
              "totals": {"passed": passed, "of": len(rows)},
              "note": ("Behavioural, and about half the scenarios assert a refusal or a clean "
                       "zero-finding guard: an ungradable criterion, an unsourced quote, a "
                       "retarget with no failure, an empty or malformed output, an unsupported "
                       "scale, a manual criterion without a note -- each paired with the "
                       "correct-input-must-find-nothing guard for the same rule.")}
    (HERE / "report_benchkit.json").write_text(json.dumps(report, ensure_ascii=False, indent=2),
                                               encoding="utf-8")
    print(f"\n{passed}/{len(rows)} pass")
    return 0 if passed == len(rows) else 1


if __name__ == "__main__":
    raise SystemExit(main())
