#!/usr/bin/env python3
"""Run a versioned, source-grounded reading evaluation and write its trace.

  python evalrun.py --case /input/case.json --out /app/output

Case may contain a ``workorder`` object, items directly, or the CLI may override
--items/--outputs.  It does NOT launch an LLM or invent missing outputs.  Retrieval
qrels/results are evaluated separately with BEIR-style metrics and a real BM25 baseline.
Exit codes: 0 completed comparable evaluation, 3 partial/failed outputs/audit warnings,
5 invalid workorder/refusal.  Everything writes result.json; no hidden official score is
claimed, and no gold/rubric/qrels are included in model_view.json.
"""
from __future__ import annotations

import argparse
from collections import defaultdict
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
import benchkit as B
import evalkit as E

SCHEMA = "reading-evaluation/v2"
LEAKAGE_RULES = {
    "duplicate_query_id_within_split": "benchmark.leakage_duplicate_query_id_within_split",
    "declared_split_mismatch": "benchmark.leakage_declared_split_mismatch",
    "source_group_overlap": "benchmark.leakage_source_group_overlap",
    "query_id_overlap": "benchmark.leakage_query_id_overlap",
    "exact_input_overlap": "benchmark.leakage_exact_input_overlap",
}


def contract_fields(contract):
    if isinstance(contract, dict):
        return list(contract)
    if isinstance(contract, list):
        result = []
        for item in contract:
            if isinstance(item, str): result.append(item)
            elif isinstance(item, dict):
                for key in ("name", "field", "key", "id"):
                    if item.get(key) is not None:
                        result.append(str(item[key])); break
        return result
    return []


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def item_from(obj):
    """Normalize public field aliases without treating filenames as scientific content."""
    if not isinstance(obj, dict):
        raise B.ItemError("one item is not a JSON object")
    item = dict(obj)
    for key in ("item_id", "question_id", "qid"):
        if item.get("id") in (None, "") and item.get(key) not in (None, ""):
            item["id"] = item[key]
    for key in ("instruction", "question"):
        if not item.get("task") and isinstance(item.get(key), str):
            item["task"] = item[key]
    if not item.get("input"):
        for key in ("input_text", "source_text", "context", "passage"):
            if item.get(key) not in (None, ""):
                item["input"] = item[key]
                break
    for key in ("reference_answer", "gold_answer", "reference_output", "answer_key"):
        if not item.get("reference") and item.get(key) not in (None, ""):
            item["reference"] = item[key]
    if not item.get("rubric"):
        for key in ("scoring", "criteria", "scoring_criteria"):
            if isinstance(item.get(key), list):
                item["rubric"] = item[key]
                break
    return item


def workorder_items(case, args):
    obj = case.get("workorder") if isinstance(case.get("workorder"), dict) else case
    raw = read_json(args.items) if args.items else (obj.get("items") or obj.get("itemset") or case.get("items") or [])
    if isinstance(raw, dict):
        raw = raw.get("items") or raw.get("questions") or raw.get("records") or []
    if not isinstance(raw, list) or not raw:
        raise B.ItemError("no non-empty items list supplied by workorder or --items")
    return [item_from(x) for x in raw], obj


def outputs_from(obj, case, args):
    if args.outputs:
        raw = read_json(args.outputs)
    else:
        raw = obj.get("outputs") if isinstance(obj, dict) else None
        if raw is None: raw = case.get("outputs")
    raw = raw or {}
    if isinstance(raw, list):
        out = {}
        for entry in raw:
            if isinstance(entry, dict):
                iid = entry.get("id") or entry.get("item_id") or entry.get("query_id")
                out[str(iid)] = entry.get("output", entry.get("raw_output", entry.get("prediction")))
        raw = out
    if not isinstance(raw, dict):
        raise B.ItemError("outputs must map item IDs to raw textual/structured output")
    return raw


def retrieval_from(obj, case, args):
    qrels, results, corpus, queries = None, None, None, None
    if args.qrels:
        qrels, results, corpus, queries = read_json(args.qrels), read_json(args.results or ""), read_json(args.corpus or ""), obj.get("queries") or case.get("queries")
    else:
        for key, value in (case.items() if isinstance(case, dict) else []):
            spec = value if isinstance(value, dict) else None
            if spec and isinstance(spec.get("qrels"), dict):
                qrels = spec["qrels"]; results = spec.get("results"); corpus = spec.get("corpus")
                queries = spec.get("queries") or case.get("queries")
                break
        if not qrels and isinstance(obj.get("retrieval"), dict):
            spec = obj["retrieval"]; qrels = spec.get("qrels"); results = spec.get("results"); corpus = spec.get("corpus"); queries = spec.get("queries")
    if not (qrels and results):
        return None
    metrics = E.evaluate_retrieval(qrels, results)
    baseline = None
    if isinstance(corpus, dict) and isinstance(queries, dict):
        baseline_run = E.bm25_baseline(corpus, queries)
        baseline_metrics = E.evaluate_retrieval(qrels, baseline_run)
        baseline = {"name": "BM25-local-exact", "results": baseline_run,
                    "expected_labels_are_not_generated": True,
                    "metrics": baseline_metrics,
                    "delta_vs_candidate": {key: (metrics["mean"][key] - baseline_metrics["mean"][key])
                                           if metrics["mean"][key] is not None and baseline_metrics["mean"][key] is not None else None
                                           for key in metrics["mean"]}}
    else:
        metrics["skipped"].append({"kind": "baseline_undetermined", "reason": "corpus and queries are required for the genuine lexical baseline"})
    return {"qrels": qrels, "raw_results": results, "metrics": metrics, "baseline": baseline}


def summarize_failures(items, record):
    grouped = defaultdict(list)
    for row in record["results"]:
        ft = row.get("failure_type")
        if ft:
            grouped[ft].append(row["item_id"])
    return {"by_failure": dict(grouped), "categories": len(grouped),
            "failed_items": sum(len(ids) for ids in grouped.values()),
            "recommendation": "Address execution/empty/malformed-output failures before retargeting semantic failures.  Create only targeted items for observed failure kinds."}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--case"); ap.add_argument("--items"); ap.add_argument("--outputs")
    ap.add_argument("--qrels"); ap.add_argument("--results"); ap.add_argument("--corpus")
    ap.add_argument("--out", required=True)
    args = ap.parse_args(argv)
    out = Path(args.out); out.mkdir(parents=True, exist_ok=True)
    case = {}
    try:
        if args.case:
            case = read_json(args.case)
            if not isinstance(case, dict): raise B.ItemError("case.json must be an object")
        items, obj = workorder_items(case, args)
        validation = B.validate_itemset(items)
        if not validation["ok"]:
            raise B.ItemError("itemset is not gradeable: " + json.dumps(validation["problems"][:20], ensure_ascii=False))
        raw_outputs = outputs_from(obj, case, args)
        cfg = dict(obj.get("run_config") or obj.get("config") or {})
        cfg.setdefault("mode", "raw-output-only; no model execution by this tool")
        cfg.setdefault("budget", 64)
        config_digest = E._stable(cfg)
        cfg["config_digest"] = config_digest
        split_declared = {name: [it for it in items if it.get("split") == name] for name in ("train", "dev", "test")}
        if any(it.get("split") for it in items):
            split_record = {"splits": split_declared, "method": "case-declared splits",
                            "actual_counts": {k: len(v) for k, v in split_declared.items()}}
        else:
            split_record = E.make_split(items)
        audit = E.leakage_audit(split_record["splits"])
        # Under an actual evaluation, leakage is not just a warning to ignore.
        declared_test = split_declared["test"]
        scoring_items = declared_test if declared_test else items
        scoring_ids = {it["id"] for it in scoring_items}
        split_record["evaluation_scope"] = "held_out_test" if declared_test else "unpartitioned_workorder_diagnostic"
        split_record["scored_item_ids"] = [it["id"] for it in scoring_items]
        records = []
        repeats = obj.get("repeat_outputs") if isinstance(obj.get("repeat_outputs"), list) else []
        for rindex, repeat in enumerate(repeats):
            if isinstance(repeat, dict):
                repeat_cfg = dict(cfg, **(repeat.get("config") or {}))
                outputs = repeat.get("outputs") or raw_outputs
                records.append(B.run(scoring_items, outputs, repeat_cfg))
        main_run = B.run(scoring_items, raw_outputs, cfg)
        records.insert(0, main_run)
        fairness = E.fairness(records)
        stability = E.run_stability(records)
        uncertainty = E.paired_bootstrap(records, iterations=cfg.get("bootstrap_iterations", 1000), seed=cfg.get("bootstrap_seed", 2026))
        retrieval = retrieval_from(obj, case, args)
        view = E.model_view_deep_copy(scoring_items)
        missing = [it["id"] for it in scoring_items if it["id"] not in raw_outputs]
        view_leaks = []
        for it in scoring_items:
            leak = E.gold_leakage_audit(it, view[[x["id"] for x in view].index(it["id"])] if it["id"] in [x["id"] for x in view] else {}, it.get("rubric"))
            if not leak["ok"]: view_leaks.append({"id": it["id"], "issues": leak["errors"]})
        limits = list(audit["warnings"]) + uncertainty["warnings"]
        if missing: limits.append("Missing outputs: %s; current record identifies not_attempted and is not a completed model quality score." % ",".join(missing[:30]))
        if not audit["ok"]: limits.append("Data/leakage validation failed; any quality comparison needs a corrected split before interpretation.")
        if not fairness["comparable"]: limits.append("Runs cannot be ranked as a fair like-for-like comparison: " + json.dumps(fairness["mismatches"], ensure_ascii=False))
        limits.append("Synthetic checker logs are local evidence, not DSH scores or independent semantic validation.")
        limits.append("Exact source/group/text leakage is covered; pretraining contamination and semantic near-duplicate searches remain outside this report unless evidenced elsewhere.")
        retrieval_issues = bool(retrieval and retrieval["metrics"]["skipped"])
        if retrieval_issues:
            limits.append("Retrieval qrels/results/baseline coverage is incomplete; skipped queries are not counted as successes.")
        incomplete_repeat = any(any(r.get("failure_type") for r in rec["results"]) for rec in records[1:])
        status = "success" if not missing and not view_leaks and audit["ok"] and fairness["comparable"] and not retrieval_issues and not incomplete_repeat and all(r.get("failure_type") is None for r in main_run["results"]) else "partial"
        findings = []
        for issue in audit["errors"]:
            findings.append({"rule": LEAKAGE_RULES.get(str(issue.get("kind")), "benchmark.leakage_other"), "severity": "high", **issue})
        for row in main_run["results"]:
            if row.get("failure_type"):
                findings.append({"rule": "benchmark." + row["failure_type"], "severity": "medium",
                                 "id": row["item_id"], "evidence": [c for c in row.get("criteria") or [] if c.get("passed") is False]})
        payload = {"schema_version": SCHEMA, "case_id": case.get("case_id"), "status": status,
                   "itemset": {"digest": validation["digest"], "items": items, "validation": validation},
                   "model_view": "model_view.json", "model_leakage": view_leaks,
                   "data_split": split_record, "leakage_audit": audit,
                   "run": main_run, "repeat_runs": records[1:],
                   "metrics": {"scope": split_record["evaluation_scope"], "primary": main_run["total"], "per_item": [dict(item_id=r["item_id"], score=r["score"], score_012=r.get("score_012")) for r in main_run["results"]]},
                   "confidence": uncertainty, "fairness": fairness, "stability": stability,
                   "retrieval_evaluation": retrieval,
                   "failure_analysis": summarize_failures(scoring_items, main_run),
                   "failure_samples": B.failures(scoring_items, main_run),
                   "trace": {item_id: B.trace(main_run, item_id) for item_id in [it["id"] for it in scoring_items]},
                   "reproducibility": {"itemset_digest": validation["digest"], "config_digest": config_digest,
                                       "run_id": main_run["run_id"], "bootstrap_seed": uncertainty["seed"],
                                       "command": "python evalrun.py --case CASE.json --out OUTPUT",
                                       "outputs_are_raw_agent_outputs_not_run_by_tool": True},
                   "findings": findings, "limits": limits}
        aliases = {"itemset_digest": validation["digest"], "run_record": main_run,
                   "scores": payload["metrics"], "confidence_interval": uncertainty,
                   "baselines": retrieval.get("baseline") if retrieval else None,
                   "failures": payload["failure_samples"], "uncertainty": limits,
                   "original_outputs": {r["item_id"]: r.get("raw_output") for r in main_run["results"]},
                   "evaluation_report": "evaluation_report.md"}
        for key in contract_fields(case.get("output_contract")):
            if key in payload: continue
            if key in aliases: payload[key] = aliases[key]
            elif key in case: payload[key] = case[key]
            else:
                payload[key] = None
                limits.append("output_contract field %r cannot be derived from supplied inputs" % key)
        (out / "model_view.json").write_text(json.dumps(view, ensure_ascii=False, indent=2), encoding="utf-8")
        (out / "evaluation.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        md = ["# Source-grounded reading evaluation", "", "Local evaluation evidence; not a DSH/platform score.", "",
              "- Status: %s" % status, "- Item-set digest: `%s`" % validation["digest"],
              "- Model view: `model_view.json` (references/rubrics/qrels excluded by schema)", "- Raw-output primary: %r" % main_run["total"],
              "- Fairness comparable: %s" % fairness["comparable"], "", "## Metrics", "```json",
              json.dumps(payload["metrics"], ensure_ascii=False, indent=2), "```", "## Paired bootstrap", "```json",
              json.dumps(uncertainty, ensure_ascii=False, indent=2), "```", "## Failure catalogue", "```json",
              json.dumps(payload["failure_samples"], ensure_ascii=False, indent=2), "```", "## Limits"] + ["- " + x for x in limits]
        (out / "evaluation_report.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    except Exception as exc:
        safe_case = case if isinstance(case, dict) else {}
        payload = {"schema_version": SCHEMA, "case_id": safe_case.get("case_id"), "status": "undetermined",
                   "findings": [{"rule": "benchmark.workorder_refused", "severity": "high", "message": str(exc)[:300]}],
                   "limits": ["Evaluation was not completed; no empty or unread item-set was scored as a valid run."]}
        for key in contract_fields(safe_case.get("output_contract")):
            payload[key] = safe_case.get(key)
            if key not in safe_case: payload["limits"].append("output_contract %r unavailable after refusal" % key)
        print(json.dumps({"status": "undetermined", "rc": 5, "error": str(exc)[:240]}, ensure_ascii=False))
        (out / "result.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return 5
    (out / "result.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    rc = 0 if status == "success" else 3
    print(json.dumps({"status": status, "rc": rc, "items": len(items),
                      "evaluable_retrieval_queries": retrieval["metrics"]["evaluable_queries"] if retrieval else None,
                      "wrote": str(out / "result.json")}, ensure_ascii=False))
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
