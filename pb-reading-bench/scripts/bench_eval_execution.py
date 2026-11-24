"""Behavioral/known-value tests for leakage, metrics, CI, baseline and CLI contracts.

All qrels/documents/agent answers are explicitly synthetic.  There is no platform
score, model execution, internet result or official evaluation dataset in this fixture.
"""
from __future__ import annotations

import json
import math
from pathlib import Path
import subprocess
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parent))
import benchkit as B
import evalkit as E

RUNNER = Path(__file__).resolve().with_name("evalrun.py")


def _items():
    input_doc = "Uptake rose three-fold under the coating. Only one thickness was tested."
    return [
        {"id": "R1", "task": "state effect", "input": input_doc, "reference": "three-fold", "split": "test", "source_id": "paper-A",
         "rubric": [{"criterion": "effect", "predicate": "contains", "weight": 60, "values": ["three-fold"]},
                    {"criterion": "quote", "predicate": "anchor", "weight": 40, "field": "quote"}]},
        {"id": "R2", "task": "state limitation", "input": input_doc, "reference": "one thickness", "split": "test", "source_id": "paper-B",
         "rubric": [{"criterion": "limit", "predicate": "contains", "weight": 60, "values": ["thickness"]},
                    {"criterion": "no invention", "predicate": "not_contains", "weight": 40, "values": ["p < 0.05"]}]},
    ]


def tests():
    rows = []
    def ok(name, cond, detail=""):
        rows.append({"scenario": name, "pass": bool(cond), "detail": str(detail)})
        print(("PASS " if cond else "FAIL ") + name + (" :: " + str(detail) if not cond else ""))
    inputs = [{"id": "a", "input": "alpha", "source_id": "g1"}, {"id": "b", "input": "alpha", "source_id": "g1"},
              {"id": "c", "input": "beta words", "source_id": "g2"}, {"id": "d", "input": "gamma", "source_id": "g3"}]
    split = E.make_split(inputs, seed=19, ratios={"train": 0.5, "dev": 0.0, "test": 0.5})
    groups = {name: [x["source_id"] for x in values] for name, values in split["splits"].items()}
    ok("group_disjoint_splitting", E.leakage_audit(split["splits"])["ok"] and (("g1" in groups["train"] and "g1" not in groups["test"]) or ("g1" in groups["test"] and "g1" not in groups["train"])), groups)
    manual = {"train": [inputs[0], inputs[2]], "dev": [], "test": [inputs[1], inputs[3]]}
    leaked = E.leakage_audit(manual)
    ok("source_overlap_is_hard_failure", not leaked["ok"] and "source_group_overlap" in str(leaked["errors"]) and "exact_input_overlap" in str(leaked["errors"]))
    view = E.model_view_deep_copy(_items())
    ok("gold_and_rubric_absent_from_model_view", "rubric" not in str(view) and "reference" not in str(view) and "qrels" not in str(view) and "anchor" not in str(view) and "Uptake rose three-fold" in str(view))
    leak = E.gold_leakage_audit(_items()[0], "answer: three-fold; use this anchor", _items()[0]["rubric"])
    ok("reference_leak_in_prompt_detected", not leak["ok"])

    good = B.run(_items(), {"R1": {"text": "Uptake rose three-fold", "quote": "Only one thickness was tested."}, "R2": {"text": "Only one thickness was tested."}})
    bad = B.run(_items(), {"R1": {"text": "Only one thickness was tested.", "quote": "Uptake rose three-fold under the coating"}, "R2": {"text": "Only one coating thickness."}})
    # Contains must not read the golden quote embedded in a structured output and award
    # a phrase which was absent from the answer text.
    main_scores = [r["score"] for r in good["results"]]
    bad_scores = [r["score"] for r in bad["results"]]
    ok("structured_output_does_not_leak_quote_into_text", main_scores == [100, 100] and bad_scores == [40, 100], bad_scores)
    ci_item = _items() + [{"id": "X", "task": "t", "input": "i", "reference": "nan",
                          "rubric": [{"criterion": "bad", "predicate": "contains", "weight": float("nan"), "values": ["x"]}]}]
    ok("nan_weight_refused", not B.validate_itemset(ci_item)["ok"])
    regex_item = _items() + [{"id": "Y", "task": "t", "input": "i", "reference": "r",
                             "rubric": [{"criterion": "bad", "predicate": "regex", "weight": 100, "pattern": "(a+)+$"}]}]
    ok("catastrophic_regex_refused_before_grading", not B.validate_itemset(regex_item)["ok"])
    ci_rubric = {"id": "ci", "task": "t", "input": "i", "reference": "r",
                 "rubric": [{"criterion": "word", "predicate": "any_of", "weight": 100, "values": ["ALPHA"], "ci": True}]}
    ok("explicit_ci_variant_works", B.run([ci_rubric], {"ci": "Alpha"})["total"] == 100)

    qrels = {"q1": {"d1": 2, "d2": 1}, "q2": {"d3": 1}}
    candidate = {"q1": {"d1": 10.0, "d2": 9.0, "dX": 8.0}, "q2": {"d2": 5.0, "d4": 4.0, "d3": 3.0}}
    metrics = E.evaluate_retrieval(qrels, candidate, [1, 3])
    # q1 is fully graded at k=1/3; q2's first hit occurs at rank 3 by design.
    expected_n3_q2 = 1.0 / math.log2(4)
    ok("known_ndcg_at_1_and_3", abs(metrics["per_query"]["nDCG@1"]["q1"] - 1) < 1e-12 and abs(metrics["per_query"]["nDCG@3"]["q2"] - expected_n3_q2) < 1e-12 and abs(metrics["mean"]["nDCG@3"] - (1 + expected_n3_q2) / 2) < 1e-12)
    ok("known_map_recall_precision_mrr", metrics["mean"]["Precision@1"] == 0.5 and abs(metrics["mean"]["MAP@3"] - (1 + 1 / 3) / 2) < 1e-12 and abs(metrics["mean"]["MRR@3"] - (1 + 1 / 3) / 2) < 1e-12 and abs(metrics["mean"]["Recall@3"] - 1) < 1e-12)
    q_missing = E.evaluate_retrieval({"q1": {"d1": 1}, "q0": {}}, {"q1": {"d1": 5}})
    ok("missing_qrels_not_forged_into_zero_or_perfect", q_missing["evaluable_queries"] == 1 and q_missing["mean"]["Recall@1"] == 1 and q_missing["skipped"][0]["kind"] == "no_positive_qrels")
    corpus = {"d1": "coating uptake high", "d2": "coating limitations", "d3": "one thickness only"}
    queries = {"q1": "coating uptake", "q2": "one thickness"}
    base = E.bm25_baseline(corpus, queries, k_value=3)
    ok("real_bm25_baseline_retrieves_relevant_text", next(iter(base["q1"])) == "d1" and next(iter(base["q2"])) == "d3")

    records = [B.run(_items(), {"R1": {"text": "three-fold", "quote": "Uptake rose three-fold"}, "R2": "Only one thickness"}, {"agent": "base"}),
               B.run(_items(), {"R1": {"text": "coating", "quote": "quote absent from the actual input"}, "R2": ""}, {"agent": "weak"})]
    boot1 = E.paired_bootstrap(records, iterations=200, seed=99)
    boot2 = E.paired_bootstrap(records, iterations=200, seed=99)
    ok("paired_bootstrap_deterministic_and_computed", boot1 == boot2 and boot1["iterations"] == 200 and boot1["intervals"]["weak"]["observed_mean"] == 0 and boot1["paired_deltas"][0]["observed_delta"] == -100, boot1)
    ok("fairness_and_seed_stability_are_visible", E.fairness(records)["comparable"] and E.run_stability(records)["groups"] == [])
    different = [records[0], dict(records[1], config={"agent": "weak", "budget": 1})]
    ok("unfair_budget_cannot_be_silently_ranked", not E.fairness(different)["comparable"])

    with tempfile.TemporaryDirectory(prefix="reading_eval_micro_") as td:
        root = Path(td)
        case = {"case_id": "synthetic-workorder-4", "custom": [5, "verbatim"],
                "output_contract": {"scores": "...", "custom": "...", "run_record": "..."},
                "workorder": {"items": _items(), "outputs": {"R1": {"text": "Uptake rose three-fold", "quote": "Uptake rose three-fold      "}, "R2": "Only one coating thickness was tested."},
                              "run_config": {"agent": "base", "budget": 64, "tools": ["none"], "bootstrap_iterations": 200},
                              "repeat_outputs": [{"config": {"agent": "skill", "budget": 64, "tools": ["none"]},
                                                  "outputs": {"R1": {"text": "Uptake rose three-fold", "quote": "Uptake rose three-fold"}, "R2": "Only one thickness"}}],
                              "retrieval": {"qrels": qrels, "results": candidate, "corpus": corpus, "queries": queries}}}
        p = root / "case.json"; p.write_text(json.dumps(case), encoding="utf-8")
        o1, o2 = root / "first", root / "second"
        command = [sys.executable, str(RUNNER), "--case", str(p), "--out"]
        a = subprocess.run(command + [str(o1)], capture_output=True, text=True)
        b = subprocess.run(command + [str(o2)], capture_output=True, text=True)
        # Anchor deliberately whitespace-changed should be honestly missing, not forced.
        first = json.loads((o1 / "result.json").read_text(encoding="utf-8"))
        second = json.loads((o2 / "result.json").read_text(encoding="utf-8"))
        ok("cli_contract_and_all_fields", a.returncode == 3 and first["case_id"] == case["case_id"] and first["custom"] == case["custom"] and "run_record" in first and "scores" in first)
        different_keys = [key for key in set(first) | set(second) if first.get(key) != second.get(key)]
        ok("cli_reproducible", first == second and (o1 / "model_view.json").read_bytes() == (o2 / "model_view.json").read_bytes() and not different_keys, different_keys)
        ok("cli_reports_actual_retrieval_and_baseline", first["retrieval_evaluation"]["metrics"]["evaluable_queries"] == 2 and first["retrieval_evaluation"]["baseline"]["name"] == "BM25-local-exact" and first["retrieval_evaluation"]["baseline"]["metrics"]["evaluable_queries"] == 2 and first["retrieval_evaluation"]["baseline"]["delta_vs_candidate"] is not None)
        ok("cli_raw_output_and_failure_trace", first["run"]["results"][0]["failure_type"] == "evidence_not_located" and first["trace"]["R1"]["raw_output"]["text"].startswith("Uptake") and first["failure_analysis"]["failed_items"] == 1)
        ok("cli_computed_bootstrap_and_pair_fairness", first["confidence"]["iterations"] == 200 and len(first["confidence"]["intervals"]) == 2 and first["fairness"]["comparable"])
        split_case = json.loads(json.dumps(case))
        split_case["workorder"]["items"][0]["split"] = "train"
        split_case["workorder"]["items"][1]["split"] = "test"
        p.write_text(json.dumps(split_case), encoding="utf-8")
        os = root / "heldout"; rs = subprocess.run(command + [str(os)], capture_output=True, text=True)
        scored = json.loads((os / "result.json").read_text(encoding="utf-8"))
        ok("cli_never_scores_train_as_heldout", scored["metrics"]["scope"] == "held_out_test" and [r["item_id"] for r in scored["run"]["results"]] == ["R2"] and scored["metrics"]["primary"] == 100, scored["metrics"])

        bad_case = dict(case); bad_case["workorder"] = dict(case["workorder"], items=_items(), outputs={"R1": "three-fold"})
        p.write_text(json.dumps(bad_case), encoding="utf-8")
        ob = root / "missing"; rb = subprocess.run(command + [str(ob)], capture_output=True, text=True)
        res = json.loads((ob / "result.json").read_text(encoding="utf-8"))
        ok("missing_output_is_partial_not_fake_model_score", rb.returncode == 3 and res["status"] == "partial" and any(r["failure_type"] == "not_attempted" for r in res["run"]["results"]) and "not a completed model quality score" in str(res["limits"]))
        malformed = root / "bad.json"; malformed.write_text("[]", encoding="utf-8")
        om = root / "malformed"; rm = subprocess.run([sys.executable, str(RUNNER), "--case", str(malformed), "--out", str(om)], capture_output=True, text=True)
        ok("invalid_case_structured_refusal", rm.returncode == 5 and not rm.stderr and json.loads((om / "result.json").read_text())["status"] == "undetermined", (rm.returncode, rm.stdout, rm.stderr))
    return rows


def main():
    rows = tests(); passed = sum(r["pass"] for r in rows)
    report = {"schema_version": "reading-evaluation-bench/v2", "synthetic": True,
              "scenarios": rows, "totals": {"passed": passed, "of": len(rows)}}
    (Path(__file__).resolve().parent / "report_execution.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print("%d/%d pass" % (passed, len(rows)))
    return 0 if passed == len(rows) else 1


if __name__ == "__main__":
    raise SystemExit(main())
