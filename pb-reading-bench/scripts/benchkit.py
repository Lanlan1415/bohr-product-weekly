"""A benchmark harness that can grade, reproduce, trace and retarget.

Both benchmark tasks in this contest ask for the same four things under different names:

  判得动 / 题能判定   an item carries task, input, reference and rubric, and the rubric is written
                      as observable predicates so two graders reach the same verdict
  跑得一致 / 跑得可复现  two runs of the same inputs produce the same per-item scores, and any
                      difference is recorded rather than smoothed away
  查得回              every score traces to the raw output, the run configuration and the rule
  改得动              a failure maps to an item, becomes a targeted item in the next version, and
                      only the affected scores are recomputed

Alongside those four, the harness covers what the task's scoring table and direction list name:
raw outputs are retained in the run record (查得回 names the raw output itself), an empty or
malformed output is identified as its own failure kind rather than misattributed (异常处理),
failures() extracts the failure sample library, diff_itemsets() is the version comparison,
panel() aggregates by agent and item-set version, a declared "0-1-2" scale bands each score,
and a criterion declared "manual" is deferred to human review instead of being refused as prose.

The design decision that matters: a criterion is a **predicate over the output**, never a free-text
comment. If a criterion cannot be evaluated by the machine it is refused at item-load time, because
a rubric nobody can apply is how two graders end up disagreeing -- unless the author explicitly
declares it "manual", which records the deferral honestly instead of pretending to decide.
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

PREDICATES = ("contains", "any_of", "not_contains", "regex", "min_count",
              "anchor", "max_words", "manual")

# Optional item-card fields the task's 题集管理 direction names (难度, 数据授权). Declared
# fields are checked for well-formedness; absent fields are never a problem.
CARD_OPTIONAL = ("difficulty", "license", "data_authorization")


class ItemError(ValueError):
    pass


def _sha(obj) -> str:
    # default= keeps run_id computable when an output holds an unserialisable object: the
    # harness reports it as malformed_output instead of crashing on the digest.
    s = json.dumps(obj, sort_keys=True, ensure_ascii=False,
                   default=lambda o: f"<{type(o).__name__}>")
    return hashlib.sha256(s.encode("utf-8")).hexdigest()[:16]


# --- items ------------------------------------------------------------------

def validate_itemset(items: list[dict]) -> dict:
    """Refuse an item that cannot be graded by the machine.

    An item is gradable when it carries the five things the task names -- task, input, reference,
    rubric, and for each rubric criterion an observable predicate with its parameters.
    """
    problems = []
    seen = set()
    for i, it in enumerate(items):
        iid = it.get("id")
        if not iid:
            problems.append({"index": i, "reason": "item has no id"})
            continue
        if iid in seen:
            problems.append({"id": iid, "reason": "duplicate item id"})
        seen.add(iid)
        for field in ("task", "input", "reference"):
            if not str(it.get(field) or "").strip():
                problems.append({"id": iid, "reason": f"missing {field}"})
        for field in CARD_OPTIONAL:
            # Declared-but-empty is a card defect; an absent field is not checked at all.
            if field in it and not str(it.get(field) or "").strip():
                problems.append({"id": iid, "reason": f"{field} declared but empty"})
        rubric = it.get("rubric") or []
        if not rubric:
            problems.append({"id": iid, "reason": "no rubric"})
        total = 0.0
        machine = 0
        for j, crit in enumerate(rubric):
            kind = str(crit.get("predicate") or "").strip().lower()
            if kind not in PREDICATES:
                # A free-text criterion cannot be applied twice the same way.
                problems.append({"id": iid, "criterion": j,
                                 "reason": f"predicate '{kind}' is not one of "
                                           f"{'/'.join(PREDICATES)}"})
                continue
            weight = crit.get("weight", 1)
            try:
                total += float(weight)
            except (TypeError, ValueError):
                problems.append({"id": iid, "criterion": j, "reason": "weight is not numeric"})
            if kind in ("contains", "any_of", "not_contains") and not crit.get("values"):
                problems.append({"id": iid, "criterion": j, "reason": "contains needs values"})
            if kind == "regex" and not crit.get("pattern"):
                problems.append({"id": iid, "criterion": j, "reason": "regex needs a pattern"})
            if kind == "anchor" and not crit.get("field"):
                problems.append({"id": iid, "criterion": j,
                                 "reason": "anchor needs the output field holding the quote"})
            if kind == "manual":
                # An honestly declared human-judged criterion needs its review instruction,
                # or the reviewer has nothing to apply twice the same way either.
                if not str(crit.get("note") or "").strip():
                    problems.append({"id": iid, "criterion": j,
                                     "reason": "manual criterion needs a note for the reviewer"})
            else:
                machine += 1
        if rubric and machine == 0:
            problems.append({"id": iid, "reason": "no machine-decidable criterion"})
        if rubric and abs(total - 100.0) > 0.001 and it.get("normalise", True):
            # Not fatal, but a rubric that does not sum to 100 makes cross-item totals meaningless.
            problems.append({"id": iid, "reason": f"rubric weights sum to {total}, not 100"})
    return {"ok": not problems, "problems": problems,
            "items": len(items), "digest": _sha(items)}


# --- grading ----------------------------------------------------------------

def _field(output, path: str):
    cur = output
    for part in path.split("."):
        if isinstance(cur, dict):
            cur = cur.get(part)
        else:
            return None
    return cur


def grade_item(item: dict, output) -> dict:
    """Score one output against one item's rubric, recording the evidence per criterion."""
    criteria = []
    earned = 0.0
    possible = 0.0
    review: list[str] = []
    for crit in item.get("rubric") or []:
        kind = str(crit.get("predicate") or "").lower()
        weight = float(crit.get("weight", 1))
        name = crit.get("criterion") or crit.get("name") or kind
        if kind == "manual":
            # Declared human review: the machine records the deferral instead of pretending to
            # decide it. The weight stays in the rubric sum but is excluded from the machine
            # score, so the recorded number is exactly the machine-decidable part.
            note = str(crit.get("note") or "").strip()
            criteria.append({"criterion": name, "predicate": "manual", "weight": weight,
                             "passed": None,
                             "evidence": f"deferred to human review: {note}"})
            review.append(name)
            continue
        possible += weight
        text = str(output or "")
        evidence, passed = "", False

        if kind == "contains":
            wanted = [str(v) for v in crit.get("values") or []]
            found = [v for v in wanted if v in text]
            passed = len(found) == len(wanted)
            evidence = f"found {len(found)}/{len(wanted)}: {found}"
        elif kind == "any_of":
            # A reference answer must accept the legitimate wording variants, not one template.
            # Passing any one of the declared alternatives counts, which is what keeps two
            # graders from disagreeing over phrasing rather than content.
            options = [str(v) for v in crit.get("values") or []]
            hit = [v for v in options if v in text]
            passed = bool(hit)
            evidence = f"accepted variant: {hit[0]!r}" if hit else f"none of {len(options)} variants"
        elif kind == "not_contains":
            banned = [str(v) for v in crit.get("values") or []]
            hit = [v for v in banned if v in text]
            passed = not hit
            evidence = f"forbidden present: {hit}" if hit else "none present"
        elif kind == "regex":
            pattern = str(crit.get("pattern") or "")
            passed = re.search(pattern, text) is not None
            evidence = f"pattern {'matched' if passed else 'did not match'}: {pattern}"
        elif kind == "min_count":
            pattern = str(crit.get("pattern") or r"\d+(?:\.\d+)?")
            need = int(crit.get("min", 1))
            got = len(re.findall(pattern, text))
            passed = got >= need
            evidence = f"{got} matches, need {need}"
        elif kind == "max_words":
            limit = int(crit.get("limit", 10**9))
            got = len(text.split())
            passed = got <= limit
            evidence = f"{got} words, limit {limit}"
        elif kind == "anchor":
            # The quote the answer claims must exist in the supplied input: this is what makes a
            # benchmark gradeable without a second human reading the paper.
            quote = str(_field(output if isinstance(output, dict) else {}, crit["field"]) or "")
            if not quote:
                quote = str(crit.get("quote") or "")
            passed = bool(quote) and quote in str(item.get("input") or "")
            evidence = f"quote {'found' if passed else 'absent'} in input: {quote[:40]!r}"

        criteria.append({"criterion": name,
                         "predicate": kind, "weight": weight, "passed": passed,
                         "evidence": evidence})
        if passed:
            earned += weight

    score = 100.0 * earned / possible if possible else 0.0
    result = {"item_id": item.get("id"), "score": round(score, 4),
              "criteria": criteria,
              "failure_type": None if score == 100 else _failure_type(criteria)}
    if review:
        result["needs_review"] = review
    return result


def _failure_type(criteria: list[dict]) -> str:
    """Attribute a failure to a kind, so it can become a targeted item.

    Only machine-decidable criteria attribute failures; a deferred manual criterion
    (passed None) is neither a pass nor a machine-attributable failure.
    """
    failed = [c for c in criteria if c["passed"] is False]
    if not failed:
        return "none"
    kinds = {c["predicate"] for c in failed}
    if "anchor" in kinds:
        return "evidence_not_located"
    if "not_contains" in kinds:
        return "forbidden_content"
    if "max_words" in kinds:
        return "over_length"
    if kinds == {"contains"}:
        return "missing_required_point"
    return "mixed"


# --- running ----------------------------------------------------------------

def run(items: list[dict], outputs: dict, config: dict | None = None) -> dict:
    """Grade a mapping of item_id -> raw output, keeping everything a score can be traced to.

    The record retains each raw output verbatim: 查得回 names the raw output itself, not just
    a digest of it. An empty or malformed output is identified as its own failure kind instead
    of being graded into a misleading content failure. A declared score_scale must be one the
    harness can honour; an unsupported one is refused rather than silently ignored.
    """
    config = config or {}
    scale = str(config.get("score_scale") or "").strip()
    if scale and scale != "0-1-2":
        raise ItemError(f"score_scale '{scale}' is not supported; declare '0-1-2' or omit it")
    results = []
    for it in items:
        iid = it.get("id")
        raw = outputs.get(iid)
        if raw is None:
            results.append({"item_id": iid, "score": 0.0, "criteria": [], "raw_output": None,
                            "failure_type": "not_attempted"})
            continue
        if isinstance(raw, str) and not raw.strip():
            # 输出为空: attributing it to a missing content point would send the retarget
            # step after the wrong fix.
            results.append({"item_id": iid, "score": 0.0, "criteria": [], "raw_output": raw,
                            "failure_type": "empty_output",
                            "note": "output is empty; nothing to grade"})
            continue
        if not isinstance(raw, (str, dict)):
            # 格式不合规: neither text nor a structured record the predicates can address.
            results.append({"item_id": iid, "score": 0.0, "criteria": [], "raw_output": raw,
                            "failure_type": "malformed_output",
                            "note": f"output is {type(raw).__name__}; "
                                    f"expected text or a structured record"})
            continue
        res = grade_item(it, raw)
        res["raw_output"] = raw
        results.append(res)
    total = sum(r["score"] for r in results) / len(results) if results else 0.0
    record = {
        "run_id": _sha({"items": [i.get("id") for i in items], "outputs": outputs,
                        "config": config}),
        "itemset_digest": _sha(items),
        "config": config,
        "results": results,
        "total": round(total, 4),
        "failures_by_type": _tally(results),
    }
    if scale:
        # 评分表's suggested 0/1/2 record, kept beside the percentage: 2 correct, 1 partial,
        # 0 wrong or missing. Declared, or absent -- never inferred.
        for r in results:
            r["score_012"] = 2 if r["score"] >= 100 else (1 if r["score"] > 0 else 0)
        record["score_scale"] = scale
    return record


def _tally(results: list[dict]) -> dict:
    out: dict[str, int] = {}
    for r in results:
        ft = r.get("failure_type")
        if ft and ft != "none":
            out[ft] = out.get(ft, 0) + 1
    return out


def reproduce(items: list[dict], outputs: dict, config: dict | None = None) -> dict:
    """Run twice and compare. Any difference is reported, not averaged away."""
    a = run(items, outputs, config)
    b = run(items, outputs, config)
    deltas = [{"item_id": x["item_id"], "first": x["score"], "second": y["score"]}
              for x, y in zip(a["results"], b["results"]) if x["score"] != y["score"]]
    return {"stable": not deltas and a["total"] == b["total"],
            "total": a["total"], "repeat_total": b["total"], "deltas": deltas}


def trace(record: dict, item_id: str) -> dict:
    """Follow one score back to the raw output, its configuration and the deciding criterion."""
    r = next((x for x in record["results"] if x["item_id"] == item_id), None)
    if r is None:
        return {"ok": False, "reason": f"{item_id} is not in run {record['run_id']}"}
    return {"ok": True, "run_id": record["run_id"], "itemset": record["itemset_digest"],
            "config": record["config"], "score": r["score"],
            "raw_output": r.get("raw_output"),
            "decided_by": [c for c in r["criteria"] if c["passed"] is False] or
                          [{"criterion": "all passed",
                            "evidence": "every machine criterion passed"}],
            "needs_review": r.get("needs_review") or [],
            "failure_type": r["failure_type"]}


def failures(items: list[dict], record: dict) -> dict:
    """The failure sample library: each typical error kept with the item, the raw output and
    the reason, indexed by failure type so it is retrievable and can seed targeted items."""
    tasks = {i.get("id"): str(i.get("task") or "") for i in items}
    lib: dict[str, list[dict]] = {}
    for r in record.get("results") or []:
        ft = r.get("failure_type")
        if not ft or ft == "none":
            continue
        lib.setdefault(ft, []).append({
            "item_id": r.get("item_id"),
            "task": tasks.get(r.get("item_id")),
            "raw_output": r.get("raw_output"),
            "failed_criteria": [{"criterion": c.get("criterion"),
                                 "predicate": c.get("predicate"),
                                 "evidence": c.get("evidence")}
                                for c in r.get("criteria") or [] if c.get("passed") is False],
            "note": r.get("note"),
        })
    return lib


CARD_FIELDS = ("task", "input", "reference", "rubric")


def diff_itemsets(old: list[dict], new: list[dict]) -> dict:
    """Version comparison: what changed between two item sets, and which historical scores
    remain comparable. Structural equality per card field; the evaluated agent's side is
    panel()'s job."""
    def idx(seq):
        return {i.get("id"): i for i in seq if i.get("id")}

    o, n = idx(old), idx(new)
    added = [i.get("id") for i in new if i.get("id") and i.get("id") not in o]
    removed = [i.get("id") for i in old if i.get("id") and i.get("id") not in n]
    changed, comparable = [], []
    for iid, oi in o.items():
        if iid not in n:
            continue
        diffs = [f for f in CARD_FIELDS if oi.get(f) != n[iid].get(f)]
        if diffs:
            changed.append({"id": iid, "fields": diffs})
        else:
            comparable.append(iid)
    return {"old_digest": _sha(old), "new_digest": _sha(new),
            "added": added, "removed": removed, "changed": changed,
            "comparable_scores": comparable,
            "note": ("scores for unchanged items stay comparable across versions; "
                     "added, removed and changed items belong to their own version")}


def _dist(xs: list) -> dict:
    vals = [float(x) for x in xs if isinstance(x, (int, float))]
    if not vals:
        return {}
    return {"mean": round(sum(vals) / len(vals), 4), "min": min(vals), "max": max(vals)}


def panel(records: list[dict]) -> dict:
    """The results panel: aggregate run records by agent and item-set version, so strengths,
    weaknesses and score distributions are visible instead of one total."""
    order: list[tuple] = []
    groups: dict[tuple, dict] = {}
    for rec in records:
        cfg = rec.get("config") or {}
        agent = str(cfg.get("agent") or cfg.get("model") or "unknown")
        key = (agent, rec.get("itemset_digest"))
        if key not in groups:
            groups[key] = {"agent": agent, "itemset": rec.get("itemset_digest"),
                           "runs": 0, "totals": [], "items": {}, "failures_by_type": {}}
            order.append(key)
        g = groups[key]
        g["runs"] += 1
        g["totals"].append(rec.get("total"))
        for r in rec.get("results") or []:
            g["items"].setdefault(r.get("item_id"), []).append(r.get("score"))
        for t, n in (rec.get("failures_by_type") or {}).items():
            g["failures_by_type"][t] = g["failures_by_type"].get(t, 0) + int(n)
    out = []
    for key in order:
        g = groups[key]
        g["total_distribution"] = _dist(g.pop("totals"))
        g["items"] = {k: _dist(v) for k, v in g["items"].items()}
        out.append(g)
    return {"groups": out}


def retarget(items: list[dict], record: dict, item_id: str, new_item: dict) -> dict:
    """Turn a failure into a targeted item and recompute only the affected scores.

    The version bump is what makes a benchmark improvable: the old scores stay valid for the old
    item set, and the new item is scored without re-running the whole set.
    """
    r = next((x for x in record["results"] if x["item_id"] == item_id), None)
    if r is None:
        return {"ok": False, "reason": f"{item_id} is not in this run"}
    if r["score"] == 100:
        return {"ok": False, "reason": f"{item_id} did not fail, so there is nothing to retarget"}
    nid = new_item.get("id")
    if not nid or any(i.get("id") == nid for i in items):
        return {"ok": False, "reason": "the new item needs a fresh id"}
    trial = validate_itemset([new_item])
    if not trial["ok"]:
        return {"ok": False, "reason": "the new item is not gradable", "problems": trial["problems"]}

    nxt = list(items) + [new_item]
    return {"ok": True,
            "from_version": _sha(items), "to_version": _sha(nxt),
            "targeted_from": {"item_id": item_id, "failure_type": r["failure_type"]},
            "recompute_only": [nid],
            "unchanged_scores": {x["item_id"]: x["score"] for x in record["results"]
                                 if x["item_id"] != item_id},
            "note": "only the new item needs grading; existing scores belong to the old version"}
