"""Benchmark for the benchmark harness itself.

Each scenario asserts one of the four properties both benchmark tasks name, using the harness on a
small item set. Half of them assert a refusal, because a benchmark that grades everything as fine
is worse than no benchmark.

  判得动 / 题能判定   an item whose criterion is free text is refused at load
  跑得一致 / 可复现   two runs agree; a rubric is not order- or hash-dependent
  查得回             a score traces to its output, config and the criterion that failed
  改得动             a failure becomes a targeted item, and only that item is recomputed

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


def s_ci_variant_accepted(name: str) -> dict:
    """Capitalisation is not what the criterion tests: 'Three-Fold' passes a ci criterion."""
    ci_items = [dict(ITEMS[0], rubric=[
        {"criterion": "effect stated", "predicate": "contains", "weight": 50,
         "values": ["three-fold"], "ci": True},
        {"criterion": "quote located", "predicate": "anchor", "weight": 50,
         "field": "quote"},
    ])]
    rec = K.run(ci_items, {"R1": {"text": "UPTAKE ROSE Three-Fold.",
                                  "quote": "Uptake rose three-fold"}})
    r1 = next(x for x in rec["results"] if x["item_id"] == "R1")
    ok = r1["score"] == 100
    # and without ci, the same output must NOT pass — the flag is doing the work
    rec2 = K.run(ITEMS, {"R1": {"text": "UPTAKE ROSE Three-Fold.",
                                "quote": "Uptake rose three-fold"}})
    r2 = next(x for x in rec2["results"] if x["item_id"] == "R1")
    ok = ok and r2["score"] == 50
    return {"name": name, "pass": ok, "why": f"ci={r1['score']} exact={r2['score']}"}


def s_min_words_floor(name: str) -> dict:
    """A one-line evasion that dodges every contains-check fails the substantive floor."""
    floor_items = [{"id": "W1", "task": "substantive answer", "input": INPUT_DOC,
                    "reference": "uptake rose three-fold",
                    "rubric": [
                        {"criterion": "substance", "predicate": "min_words", "weight": 50,
                         "limit": 10},
                        {"criterion": "effect stated", "predicate": "contains", "weight": 50,
                         "values": ["three-fold"]},
                    ]}]
    thin = K.run(floor_items, {"W1": "Yes."})
    t = next(x for x in thin["results"] if x["item_id"] == "W1")
    ok = t["failure_type"] == "under_length" and t["score"] == 0
    full = K.run(floor_items, {"W1": "Under the coating uptake rose three-fold across "
                                     "six replicates per arm."})
    f = next(x for x in full["results"] if x["item_id"] == "W1")
    ok = ok and f["score"] == 100
    return {"name": name, "pass": ok,
            "why": f"thin={t['score']}/{t['failure_type']} full={f['score']}"}


SCEN = [s_items_valid, s_freetext_criterion_refused, s_weights_must_sum, s_grading_is_exact,
        s_anchor_catches_unsourced, s_reproducible, s_traceable, s_retarget,
        s_retarget_needs_failure, s_unattempted_is_zero, s_ci_variant_accepted,
        s_min_words_floor]


def main() -> int:
    rows = [scen(fn.__name__.replace("s_", ""), fn) for fn in SCEN]
    for r in rows:
        print(f"{'PASS' if r['pass'] else 'FAIL'}  {r['name']:<30} {r['why']}")
    passed = sum(1 for r in rows if r["pass"])
    report = {"schema_version": "benchkit-bench/v1", "scenarios": rows,
              "totals": {"passed": passed, "of": len(rows)},
              "note": ("Behavioural, and half the scenarios assert a refusal: an ungradable "
                       "criterion, an unsourced quote, a retarget that has no failure to work from.")}
    (HERE / "report_benchkit.json").write_text(json.dumps(report, ensure_ascii=False, indent=2),
                                               encoding="utf-8")
    print(f"\n{passed}/{len(rows)} pass")
    return 0 if passed == len(rows) else 1


if __name__ == "__main__":
    raise SystemExit(main())
