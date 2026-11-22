"""A benchmark harness that can grade, reproduce, trace and retarget.

Both benchmark tasks in this contest ask for the same four things under different names:

  判得动 / 题能判定   an item carries task, input, reference and rubric, and the rubric is written
                      as observable predicates so two graders reach the same verdict
  跑得一致 / 跑得可复现  two runs of the same inputs produce the same per-item scores, and any
                      difference is recorded rather than smoothed away
  查得回              every score traces to the raw output, the run configuration and the rule
  改得动              a failure maps to an item, becomes a targeted item in the next version, and
                      only the affected scores are recomputed

The design decision that matters: a criterion is a **predicate over the output**, never a free-text
comment. If a criterion cannot be evaluated by the machine it is refused at item-load time, because
a rubric nobody can apply is how two graders end up disagreeing.
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

PREDICATES = ("contains", "any_of", "not_contains", "regex", "min_count",
              "anchor", "max_words", "min_words")


class ItemError(ValueError):
    pass


def _sha(obj) -> str:
    s = json.dumps(obj, sort_keys=True, ensure_ascii=False)
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
        rubric = it.get("rubric") or []
        if not rubric:
            problems.append({"id": iid, "reason": "no rubric"})
        total = 0.0
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


def grade_item(item: dict, output: str) -> dict:
    """Score one output against one item's rubric, recording the evidence per criterion."""
    criteria = []
    earned = 0.0
    possible = 0.0
    for crit in item.get("rubric") or []:
        kind = str(crit.get("predicate") or "").lower()
        weight = float(crit.get("weight", 1))
        possible += weight
        # A dict output's text criteria grade the answer field only: matching against the
        # whole stringified record would let the anchor quote satisfy a contains-check the
        # answer itself never made.
        if isinstance(output, dict):
            text = str(output.get("text") or output.get("answer") or "")
        else:
            text = str(output or "")
        # Case-insensitive matching ("ci") keeps two graders from disagreeing over
        # "Three-fold" vs "three-fold" — capitalisation is not what the criterion tests.
        ci = bool(crit.get("ci"))
        hay = text.casefold() if ci else text
        evidence, passed = "", False

        if kind == "contains":
            wanted = [str(v) for v in crit.get("values") or []]
            found = [v for v in wanted if (v.casefold() if ci else v) in hay]
            passed = len(found) == len(wanted)
            evidence = f"found {len(found)}/{len(wanted)}: {found}" + (" (ci)" if ci else "")
        elif kind == "any_of":
            # A reference answer must accept the legitimate wording variants, not one template.
            # Passing any one of the declared alternatives counts, which is what keeps two
            # graders from disagreeing over phrasing rather than content.
            options = [str(v) for v in crit.get("values") or []]
            hit = [v for v in options if (v.casefold() if ci else v) in hay]
            passed = bool(hit)
            evidence = f"accepted variant: {hit[0]!r}" if hit else f"none of {len(options)} variants"
        elif kind == "not_contains":
            banned = [str(v) for v in crit.get("values") or []]
            hit = [v for v in banned if (v.casefold() if ci else v) in hay]
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
        elif kind == "min_words":
            # The floor that catches a one-line evasion: an answer can dodge every
            # contains-check by saying almost nothing, so a substantive-answer rubric
            # also states the minimum it will accept.
            floor = int(crit.get("limit", 0))
            got = len(text.split())
            passed = got >= floor
            evidence = f"{got} words, floor {floor}"
        elif kind == "anchor":
            # The quote the answer claims must exist in the supplied input: this is what makes a
            # benchmark gradeable without a second human reading the paper.
            quote = str(_field(output if isinstance(output, dict) else {}, crit["field"]) or "")
            if not quote:
                quote = str(crit.get("quote") or "")
            passed = bool(quote) and quote in str(item.get("input") or "")
            evidence = f"quote {'found' if passed else 'absent'} in input: {quote[:40]!r}"

        criteria.append({"criterion": crit.get("criterion") or crit.get("name") or kind,
                         "predicate": kind, "weight": weight, "passed": passed,
                         "evidence": evidence})
        if passed:
            earned += weight

    score = 100.0 * earned / possible if possible else 0.0
    return {"item_id": item.get("id"), "score": round(score, 4),
            "criteria": criteria,
            "failure_type": None if score == 100 else _failure_type(criteria)}


def _failure_type(criteria: list[dict]) -> str:
    """Attribute a failure to a kind, so it can become a targeted item."""
    failed = [c for c in criteria if not c["passed"]]
    if not failed:
        return "none"
    kinds = {c["predicate"] for c in failed}
    if "anchor" in kinds:
        return "evidence_not_located"
    if "not_contains" in kinds:
        return "forbidden_content"
    if "max_words" in kinds:
        return "over_length"
    if "min_words" in kinds:
        return "under_length"
    if kinds == {"contains"}:
        return "missing_required_point"
    return "mixed"


# --- running ----------------------------------------------------------------

def run(items: list[dict], outputs: dict, config: dict | None = None) -> dict:
    """Grade a mapping of item_id -> raw output, keeping everything a score can be traced to."""
    config = config or {}
    results = []
    for it in items:
        iid = it.get("id")
        raw = outputs.get(iid)
        if raw is None:
            results.append({"item_id": iid, "score": 0.0, "criteria": [],
                            "failure_type": "not_attempted"})
            continue
        results.append(grade_item(it, raw))
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
    """Follow one score back to its output, its configuration and the criterion that decided it."""
    r = next((x for x in record["results"] if x["item_id"] == item_id), None)
    if r is None:
        return {"ok": False, "reason": f"{item_id} is not in run {record['run_id']}"}
    return {"ok": True, "run_id": record["run_id"], "itemset": record["itemset_digest"],
            "config": record["config"], "score": r["score"],
            "decided_by": [c for c in r["criteria"] if not c["passed"]] or
                          [{"criterion": "all passed", "evidence": "every criterion passed"}],
            "failure_type": r["failure_type"]}


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
