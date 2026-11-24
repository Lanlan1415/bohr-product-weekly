"""Data-split, leakage, retrieval-metric, baseline and uncertainty utilities.

Metric conventions follow beir-cellar/beir: qrels and query/doc-id scored runs,
nDCG/MAP/Recall/Precision@k, and MRR@k.  The code below is an independent stdlib
implementation with explicit qrels coverage and stable deterministic tie handling.
"""
from __future__ import annotations

import hashlib
import json
import math
import random
import re
import statistics


class EvaluationError(ValueError):
    pass


def _stable(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                    default=str).encode("utf-8")).hexdigest()


def text_norm(value):
    return " ".join(str(value or "").split()).casefold()


def source_group(item):
    for key in ("source_id", "paper_id", "document_id", "doc_id", "group_id", "source_group"):
        if item.get(key) not in (None, ""):
            return str(item[key])
    passages = item.get("input")
    if isinstance(passages, list):
        value = " ".join(str(p.get("text") or p.get("content") or "") if isinstance(p, dict) else str(p)
                         for p in passages)
    else:
        value = str(passages or "")
    # Same bytes/text (normalised whitespace only) are deliberately one leakage group;
    # content different in semantics is not guessed to be identical.
    return _stable(text_norm(value))


def make_split(items, seed=2026, ratios=None):
    """Assign whole source groups to disjoint train/dev/test partitions.

    Items never carry random timestamps or a globally mutable random state.  The seed and
    group allocation are included in the returned manifest for exact reruns.  Partition
    proportions are recorded as requested, not falsely asserted to be exact under grouping.
    """
    ratios = ratios or {"train": 0.6, "dev": 0.2, "test": 0.2}
    if any(k not in ratios for k in ("train", "dev", "test")) or abs(sum(ratios.values()) - 1) > 1e-8:
        raise EvaluationError("split ratios train/dev/test must sum to 1")
    if any(v < 0 for v in ratios.values()):
        raise EvaluationError("split ratios cannot be negative")
    groups = {}
    for item in items:
        if not isinstance(item, dict):
            raise EvaluationError("item must be an object")
        groups.setdefault(source_group(item), []).append(str(item.get("id")))
    ordered = sorted(groups, key=lambda g: _stable({"seed": seed, "group": g}) + g)
    allocation = {g: None for g in ordered}
    for g in ordered:
        # Independent hash-threshold assignment preserves source grouping exactly.
        value = int(_stable({"seed": seed, "assign": g})[:16], 16) / float(16**16 - 1)
        if value < ratios["train"]:
            allocation[g] = "train"
        elif value < ratios["train"] + ratios["dev"]:
            allocation[g] = "dev"
        else:
            allocation[g] = "test"
    result = {name: [] for name in ("train", "dev", "test")}
    for item in items:
        result[allocation[source_group(item)]].append(item)
    return {"splits": result, "seed": seed, "requested_ratios": ratios,
            "actual_counts": {k: len(v) for k, v in result.items()},
            "group_counts": {k: len({source_group(x) for x in values}) for k, values in result.items()},
            "method": "whole-source-group deterministic hash-threshold assignment"}


def leakage_audit(splits):
    errors, warnings = [], []
    names = [name for name in ("train", "dev", "test") if name in splits]
    memberships = {}
    for name in names:
        records = splits.get(name) or []
        groups = {source_group(item) for item in records if isinstance(item, dict)}
        qids = {str(item.get("id")) for item in records if isinstance(item, dict)}
        texts = {text_norm(item.get("input")): item.get("id") for item in records if isinstance(item, dict)}
        memberships[name] = (groups, qids, texts)
        if len(qids) != len(records):
            errors.append({"kind": "duplicate_query_id_within_split", "split": name})
        for item in records:
            if isinstance(item, dict) and item.get("split") and item["split"] != name:
                errors.append({"kind": "declared_split_mismatch", "split": name, "id": item.get("id")})
    for i, a in enumerate(names):
        for b in names[i + 1:]:
            ga, qa, ta = memberships[a]
            gb, qb, tb = memberships[b]
            shared = sorted(ga & gb)
            if shared:
                errors.append({"kind": "source_group_overlap", "splits": [a, b],
                               "groups": shared[:20], "count": len(shared)})
            if qa & qb:
                errors.append({"kind": "query_id_overlap", "splits": [a, b],
                               "ids": sorted(qa & qb)[:20]})
            shared_texts = sorted(set(ta) & set(tb))
            if shared_texts:
                errors.append({"kind": "exact_input_overlap", "splits": [a, b],
                               "items": [ta[x] for x in shared_texts[:20]]})
    for name, (groups, qids, _) in memberships.items():
        if not qids:
            warnings.append("split %s has no items; no held-out estimate can be claimed for it" % name)
    return {"ok": not errors, "fail_open": False, "errors": errors, "warnings": warnings,
            "checked_splits": names,
            "limits": ["Exact group/text/id leakage is checked. Semantic near-duplicates and pretraining contamination require external evidence and are not declared absent here."]}


def model_view(item):
    """Whitelisted, annotation-free view passed to a model, never a hand-edited copy."""
    if not isinstance(item, dict):
        raise EvaluationError("item model view must be a dictionary")
    allowed = {"id", "task", "input", "source_id", "paper_id", "document_id", "doc_id",
               "input_materials", "instructions", "constraints", "output_format"}
    return {k: item[k] for k in sorted(allowed) if k in item}


def gold_leakage_audit(item, prompt, rubric=None):
    """Find gold in extra cues, not in the actual source the task asks the model to read."""
    issues = []
    if isinstance(prompt, dict):
        forbidden = sorted(GOLD_FIELDS & set(prompt))
        issues.extend("forbidden_model_field:" + x for x in forbidden)
        aux = {k: v for k, v in prompt.items() if k not in {
            "input", "input_materials", "id", "source_id", "paper_id", "document_id", "doc_id"}}
        prompt_text = json.dumps(aux, ensure_ascii=False)
    else:
        prompt_text = str(prompt)
    # A reference appearing in source-text is evidence-conditioned, not leakage.  A
    # separate all-gold string in task/instructions/output format is.  This guard is
    # intentionally a whitelist, not a full natural-language leak oracle.
    for sequence in [item.get("reference"), item.get("gold_answer"), item.get("answer_key")]:
        if isinstance(sequence, str) and len(sequence.strip()) >= 8 and sequence.strip() in prompt_text:
            issues.append("reference_answer_verbatim_in_auxiliary_prompt")
            break
    if rubric is not None:
        keys = [str(x.get("criterion") or x.get("name") or "")
                for x in rubric if isinstance(x, dict)]
        if any(key and len(key) >= 5 and key in prompt_text for key in keys):
            issues.append("rubric_keys_in_auxiliary_prompt")
    return {"ok": not issues, "errors": issues,
            "model_view_sha256": _stable(model_view(item))}


GOLD_FIELDS = {"reference", "reference_answer", "gold", "gold_answer", "answer", "qrels",
               "rubric", "rubric_json", "scoring", "evaluation", "scores", "answer_key"}


def model_view_deep_copy(items):
    return [model_view(item) for item in items]


# --- Retrieval metrics ------------------------------------------------------

def _grade(value):
    if isinstance(value, bool):
        return 1.0 if value else 0.0
    try:
        f = float(value)
    except (TypeError, ValueError):
        return 0.0
    return f if math.isfinite(f) and f > 0 else 0.0


def _ranking(scores, k):
    if not isinstance(scores, dict):
        raise EvaluationError("ranking for a query must be doc_id -> numeric score")
    parsed = []
    for doc, score in scores.items():
        try:
            parsed.append((str(doc), float(score)))
        except (TypeError, ValueError):
            parsed.append((str(doc), float("-inf")))
    return [doc for doc, _ in sorted(parsed, key=lambda x: (-x[1], x[0]))[:k]]


def evaluate_retrieval(qrels, results, k_values=(1, 3, 5, 10)):
    if not isinstance(qrels, dict) or not isinstance(results, dict):
        raise EvaluationError("qrels and results must be dictionaries keyed by query ID")
    k_values = sorted({int(k) for k in k_values})
    if not k_values or k_values[0] <= 0:
        raise EvaluationError("k values must be positive integers")
    metrics = {name + "@" + str(k): {} for name in ("nDCG", "MAP", "Recall", "Precision", "MRR") for k in k_values}
    skipped_query_ids = []
    failures = []
    for qid in sorted(qrels):
        relevant = {str(d): _grade(rel) for d, rel in (qrels[qid] or {}).items() if _grade(rel) > 0}
        if not relevant:
            skipped_query_ids.append(qid)
            failures.append({"query_id": qid, "kind": "no_positive_qrels", "impact": "excluded from metric means; not counted as a perfect or zero result"})
            continue
        if qid not in results:
            failures.append({"query_id": qid, "kind": "missing_ranking", "impact": "excluded from metric means; run is incomplete"})
            skipped_query_ids.append(qid)
            continue
        for k in k_values:
            ranked = _ranking(results[qid], k)
            hits = [1.0 if doc in relevant else 0.0 for doc in ranked]
            found = sum(hits)
            metrics["Precision@" + str(k)][qid] = found / k
            metrics["Recall@" + str(k)][qid] = found / len(relevant)
            reciprocal = [1.0 / (i + 1) for i, hit in enumerate(hits) if hit]
            metrics["MRR@" + str(k)][qid] = reciprocal[0] if reciprocal else 0.0
            total = 0.0
            n_hits = 0
            for index, hit in enumerate(hits, 1):
                if hit:
                    n_hits += 1
                    total += n_hits / index
            metrics["MAP@" + str(k)][qid] = total / min(len(relevant), k)
            dcg = sum((2 ** relevant[doc] - 1) / math.log2(i + 2)
                      for i, doc in enumerate(ranked) if doc in relevant)
            ideal = sorted(relevant.values(), reverse=True)[:k]
            idcg = sum((2 ** rel - 1) / math.log2(i + 2) for i, rel in enumerate(ideal))
            metrics["nDCG@" + str(k)][qid] = dcg / idcg if idcg else 0.0
    summary = {}
    for name, rows in metrics.items():
        # No fabricated zero for a skipped query: it stays out of both the numerator and the
        # denominator.  Mean of no evaluable queries is explicitly undetermined.
        summary[name] = sum(rows.values()) / len(rows) if rows else None
        metrics[name] = rows
    return {"per_query": metrics, "mean": summary,
            "evaluable_queries": len(qrels) - len(skipped_query_ids),
            "declared_queries": len(qrels), "skipped": failures,
            "convention": "binary-positive coverage for Recall/Precision/MRR; graded nDCG; denominator min(#relevant,k) for MAP"}


def tokens(text):
    return re.findall(r"[a-zA-Z0-9_]{1,64}|[\u4e00-\u9fff]", str(text or "").lower())


def bm25_baseline(corpus, queries, k_value=100, k1=1.5, b=0.75):
    """A real, reproducible lexical baseline evaluated by the same qrels/metrics as systems."""
    docs = {str(doc): tokens(content) for doc, content in corpus.items()}
    frequencies = {doc: {t: words.count(t) for t in set(words)} for doc, words in docs.items()}
    lengths = {doc: len(words) for doc, words in docs.items()}
    avg = sum(lengths.values()) / len(lengths) if lengths else 1.0
    response = {}
    for qid, query in queries.items():
        qterms = tokens(query)
        scores = {}
        for doc, terms in docs.items():
            score = 0.0
            for term in sorted(set(qterms)):
                tf = frequencies[doc].get(term, 0)
                if not tf:
                    continue
                df = sum(1 for vals in frequencies.values() if term in vals)
                idf = math.log(1 + (len(docs) - df + 0.5) / (df + 0.5))
                score += idf * tf * (k1 + 1) / (tf + k1 * (1 - b + b * lengths[doc] / max(avg, 1e-12)))
            if score > 0:
                scores[doc] = score
        # Preserve tied zero documents too: ranking/missing-document behavior is explicit.
        if not scores:
            scores = {doc: 0.0 for doc in docs}
        response[str(qid)] = dict(sorted(scores.items(), key=lambda x: (-x[1], x[0]))[:k_value])
    return response


def _macro(record):
    rows = record.get("results") or []
    return sum(float(r.get("score", 0.0)) for r in rows) / len(rows) if rows else None


def mean_ci(values, confidence=0.95):
    if not values:
        return None
    vals = sorted(float(v) for v in values)
    def q(p):
        pos = (len(vals) - 1) * p
        lo = math.floor(pos); hi = math.ceil(pos)
        return vals[lo] + (vals[hi] - vals[lo]) * (pos - lo)
    return {"method": "percentile-bootstrap", "confidence": confidence,
            "iterations": len(vals), "low": q((1 - confidence) / 2),
            "high": q(1 - (1 - confidence) / 2), "estimated_mean": statistics.fmean(vals)}


def paired_bootstrap(records, iterations=1000, seed=2026, confidence=0.95):
    """Paired item-level bootstrap, with fixed seed and no invented significance claim."""
    if not records:
        raise EvaluationError("no run records supplied")
    item_ids = [r.get("item_id") for r in records[0].get("results") or []]
    if not item_ids:
        raise EvaluationError("run records have no item scores")
    if iterations < 100 or iterations > 100000:
        raise EvaluationError("bootstrap iterations must be in [100,100000]")
    for record in records:
        if [r.get("item_id") for r in record.get("results") or []] != item_ids:
            raise EvaluationError("paired runs differ in item IDs or order; cannot compare fairly")
        if records[0]["itemset_digest"] != record["itemset_digest"]:
            raise EvaluationError("paired runs differ in itemset digest")
    rng = random.Random(seed)
    total_samples, deltas = [], []
    for _ in range(iterations):
        indices = [rng.randrange(len(item_ids)) for _ in item_ids]
        totals = []
        for record in records:
            scores = [r["score"] for r in record["results"]]
            totals.append(sum(scores[i] for i in indices) / len(indices))
        total_samples.append(totals)
        deltas.append([x - totals[0] for x in totals[1:]])
    names = [str((r.get("config") or {}).get("agent") or (r.get("config") or {}).get("model") or "run-%d" % (i + 1))
             for i, r in enumerate(records)]
    intervals = {}
    for j, name in enumerate(names):
        intervals[name] = mean_ci([x[j] for x in total_samples], confidence)
        intervals[name]["observed_mean"] = _macro(records[j])
    differences = []
    for j in range(1, len(names)):
        interval = mean_ci([x[j - 1] for x in deltas], confidence)
        interval.update({"pair": [names[0], names[j]], "observed_delta": _macro(records[j]) - _macro(records[0]),
                         "not_a_proof_of_causality": True})
        differences.append(interval)
    return {"seed": seed, "iterations": iterations, "unit": "item (paired resampling)",
            "confidence": confidence, "intervals": intervals, "paired_deltas": differences,
            "warnings": (["Small item count: interval is descriptive and does not establish low variance."]
                         if len(item_ids) < 20 else []),
            "items": len(item_ids), "itemset_digest": records[0]["itemset_digest"]}


def fairness(records):
    """Do not compare materially different prompts, budgets, tool permissions or itemsets."""
    if not records:
        return {"comparable": False, "reason": "no records"}
    keys = ("budget", "tools", "permissions", "temperature", "prompt_digest", "tool_budget")
    reference = records[0].get("config") or {}
    mismatch = []
    for i, rec in enumerate(records[1:], 1):
        if rec.get("itemset_digest") != records[0].get("itemset_digest"):
            mismatch.append({"record": i, "field": "itemset_digest"})
        cfg = rec.get("config") or {}
        for key in keys:
            if cfg.get(key) != reference.get(key):
                mismatch.append({"record": i, "field": key,
                                 "first": reference.get(key), "other": cfg.get(key)})
    return {"comparable": not mismatch, "mismatches": mismatch,
            "agent_differences_allowed": True,
            "note": "Model/agent version differences are the comparison condition; shared itemset, prompt/tool powers and budgets are separately audited."}


def run_stability(records):
    by_key = {}
    for record in records:
        digest = record.get("itemset_digest")
        agent = str((record.get("config") or {}).get("agent") or "unknown")
        by_key.setdefault((digest, agent), []).append(_macro(record))
    groups = []
    for (digest, agent), values in by_key.items():
        if len(values) > 1:
            groups.append({"agent": agent, "itemset_digest": digest, "runs": len(values),
                           "mean": statistics.fmean(values),
                           "stdev": statistics.stdev(values), "min": min(values), "max": max(values),
                           "run_ids": [r.get("run_id") for r in records
                                       if r.get("itemset_digest") == digest and
                                       str((r.get("config") or {}).get("agent") or "unknown") == agent]})
    return {"groups": groups, "note": "Observed random/seed variation; not replaced by a confidence claim."}
