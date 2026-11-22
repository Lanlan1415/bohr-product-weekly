"""Rule+cue classification of research documents into a declared taxonomy.

The organising brief names the three ways this job usually fails: classification
stays a chat suggestion with labels nobody can re-check; a document that clearly
spans two categories is forced into one; and a document that fits nothing is
pushed into the least-bad drawer instead of being reported. This module is built
against those three failures:

  可解释     every label records the exact cues and example snippets that matched,
             and the confidence is that label's share of all cue hits — anyone
             holding the record and the declared taxonomy can recompute it
  多标签     every category with at least one cue hit is recorded; the primary
             label is the strongest, ties resolve by declared taxonomy order,
             and the runner-up labels stay on the record
  未分类诚实  a record no cue matches is reported as 未分类 with the reason;
             it is never pushed into a guessed category
  批次汇总   the batch result carries per-category counts (primary labels and
             label mentions), the multi-label list, skipped entries and the
             unclassified list

Refusals are honest as well: an empty taxonomy, no records, or an unreadable
spec is refused with a named rule — the batch is never run against a guessed
schema. No wall-clock fields are written, so re-running the same spec produces
a byte-identical result.
"""

from __future__ import annotations

import hashlib
import json

SCHEMA_VERSION = "doc-classify/v1"
UNCLASSIFIED = "未分类"


def _refusal(rule: str, message: str) -> dict:
    return {"schema_version": SCHEMA_VERSION, "status": "undetermined",
            "refusal": {"rule": rule, "message": message},
            "limits": ["the batch was not run; nothing was classified"]}


def valid_taxonomy(taxonomy):
    """Split the declared taxonomy into usable entries and named skips.

    An entry must be an object with a non-empty category; cues and examples are
    kept verbatim (trimmed, empties dropped), because the matched cue text is
    what makes a label checkable after the fact.
    """
    ok: list = []
    skipped: list = []
    for i, cat in enumerate(taxonomy or []):
        if not isinstance(cat, dict) or not str(cat.get("category") or "").strip():
            skipped.append({"index": i,
                            "reason": "taxonomy entry is not an object with a category name"})
            continue
        cues_raw = cat.get("cues")
        examples_raw = cat.get("examples")
        if cues_raw is not None and not isinstance(cues_raw, list):
            skipped.append({"index": i,
                            "reason": "taxonomy cues are not a list; the entry is skipped "
                                      "rather than character-split"})
            continue
        if examples_raw is not None and not isinstance(examples_raw, list):
            skipped.append({"index": i,
                            "reason": "taxonomy examples are not a list; the entry is skipped "
                                      "rather than character-split"})
            continue
        ok.append({
            "category": str(cat["category"]).strip(),
            "cues": [str(c).strip() for c in (cues_raw or []) if str(c).strip()],
            "examples": [str(e).strip() for e in (examples_raw or []) if str(e).strip()],
        })
    return ok, skipped


def cue_collisions(taxonomy):
    """Cues declared in more than one category, as findings.

    A shared cue is not an error: it counts for every category that declares it,
    which is exactly how a document can land in two labels at once. It is
    flagged so the spec author can see the overlap instead of discovering it in
    a review.
    """
    seen: dict = {}
    for cat in taxonomy:
        for cue in cat["cues"]:
            seen.setdefault(cue.lower(), []).append(cat["category"])
    out = []
    for cue in sorted(seen):
        cats = seen[cue]
        if len(cats) > 1:
            out.append({"rule": "cls.cue_collision", "severity": "medium",
                        "cue": cue, "categories": cats,
                        "why": "the same cue is declared in " + str(len(cats))
                               + " categories; it counts for each of them"})
    return out


def classify_record(rec_id: str, text: str, taxonomy, min_hits: int = 1) -> dict:
    """One record against the taxonomy: labels, primary, confidence, reason.

    A category becomes a label when at least `min_hits` declared cues or
    example snippets appear in the record text. Confidence is the primary
    label's share of all cue hits (1.0 when a single category matched, 0.5 on a
    two-way tie) — a recomputable share, not a probability: the matched cues,
    not the number, are the evidence.
    """
    low = str(text or "").lower()
    min_hits = max(1, int(min_hits or 1))
    labels = []
    for cat in taxonomy:
        matched = [c for c in cat["cues"] if c.lower() in low]
        ex_matched = [e for e in cat["examples"] if e.lower() in low]
        hits = len(matched) + len(ex_matched)
        if hits >= min_hits:
            labels.append({"category": cat["category"], "cue_hits": hits,
                           "matched_cues": matched, "matched_examples": ex_matched})
    # Stable sort: ties keep the declared taxonomy order, so the primary label
    # is a function of the spec alone, never of dict iteration luck.
    labels.sort(key=lambda l: -l["cue_hits"])
    total = sum(l["cue_hits"] for l in labels)
    if not labels:
        reason = "no declared cue or example appears in the record text"
        if not str(text or "").strip():
            reason = "the record has no text, so no cue can match it"
        return {"id": rec_id, "primary": UNCLASSIFIED, "confidence": 0.0,
                "multi_label": False, "labels": [], "reason": reason,
                "cue_hits_total": 0}
    top = labels[0]
    evidence = top["matched_cues"][:3] or top["matched_examples"][:2]
    reason = "top label by cue hits (" + ", ".join(evidence) + ")"
    if len(labels) > 1:
        reason += "; runner-up " + labels[1]["category"] + " also matched"
    return {"id": rec_id, "primary": top["category"],
            "confidence": round(top["cue_hits"] / total, 4),
            "multi_label": len(labels) > 1, "labels": labels, "reason": reason,
            "cue_hits_total": total}


def run(spec, min_hits: int = 1) -> dict:
    """Classify every record in the spec against the declared taxonomy.

    Returns the full batch result, or a refusal dict (status undetermined) when
    the taxonomy or the records cannot support a run at all.
    """
    if not isinstance(spec, dict):
        return _refusal("cls.spec_unreadable", "the spec is not a JSON object")
    tax_raw = spec.get("taxonomy")
    if not isinstance(tax_raw, list):
        return _refusal("cls.empty_taxonomy",
                        "spec.taxonomy is missing or not a list; a run without a declared "
                        "taxonomy would be guessing categories")
    taxonomy, tax_skipped = valid_taxonomy(tax_raw)
    if not taxonomy:
        return _refusal("cls.empty_taxonomy",
                        "no usable taxonomy entries (every entry must be an object with a "
                        "non-empty category name)")
    rec_raw = spec.get("records")
    if not isinstance(rec_raw, list) or not rec_raw:
        return _refusal("cls.no_records",
                        "spec.records is missing, empty or not a list; there is nothing "
                        "to classify")

    records = []
    skipped = []
    for i, rec in enumerate(rec_raw):
        if isinstance(rec, dict):
            rec_id = str(rec.get("id") or "").strip() or "rec-" + str(i + 1).zfill(3)
            text = rec.get("text")
            records.append({"id": rec_id, "title": str(rec.get("title") or "").strip(),
                            "text": "" if text is None else str(text), "index": i})
        elif isinstance(rec, str):
            # A bare string is a document with no metadata: classify its text
            # under a generated id rather than refusing usable content.
            records.append({"id": "rec-" + str(i + 1).zfill(3), "title": "",
                            "text": rec, "index": i})
        else:
            skipped.append({"index": i,
                            "reason": "record entry is neither an object nor a string: "
                                      + type(rec).__name__})
    if not records:
        return _refusal("cls.no_records",
                        "every record entry was skipped as malformed; nothing to classify")

    results = []
    for rec in records:
        cls = classify_record(rec["id"], rec["text"], taxonomy, min_hits)
        cls["index"] = rec["index"]
        cls["title"] = rec["title"]
        results.append(cls)

    per_category: dict = {}
    mentions: dict = {}
    for cat in taxonomy:
        per_category[cat["category"]] = 0
        mentions[cat["category"]] = 0
    per_category[UNCLASSIFIED] = 0
    for r in results:
        per_category[r["primary"]] = per_category.get(r["primary"], 0) + 1
        for lab in r["labels"]:
            mentions[lab["category"]] = mentions.get(lab["category"], 0) + 1
    unclassified = [r["id"] for r in results if r["primary"] == UNCLASSIFIED]
    multi = [r["id"] for r in results if r["multi_label"]]

    findings = cue_collisions(taxonomy)
    if tax_skipped:
        findings.append({"rule": "cls.taxonomy_entry_skipped", "severity": "low",
                         "count": len(tax_skipped), "entries": tax_skipped,
                         "why": "these taxonomy entries could not be used; the rest ran"})
    if skipped:
        findings.append({"rule": "cls.record_skipped", "severity": "low",
                         "count": len(skipped), "entries": skipped,
                         "why": "these record entries were neither objects nor strings; "
                                "named here instead of vanishing"})
    if unclassified:
        findings.append({"rule": "cls.unclassified", "severity": "low",
                         "count": len(unclassified), "ids": unclassified,
                         "why": "these records matched no declared cue; they are reported "
                                "as " + UNCLASSIFIED + " with the reason, not forced into "
                                "a category"})

    return {
        "schema_version": SCHEMA_VERSION,
        "status": "ok",
        "records": results,
        "summary": {
            "total_records": len(results),
            "per_category": per_category,
            "label_mentions": mentions,
            "unclassified_ids": unclassified,
            "multi_label_ids": multi,
        },
        "findings": findings,
        "taxonomy_declared": [{"category": c["category"], "cues": c["cues"],
                               "examples": c["examples"]} for c in taxonomy],
        "spec_sha256": hashlib.sha256(json.dumps(
            {"taxonomy": tax_raw, "records": rec_raw}, sort_keys=True,
            ensure_ascii=False).encode("utf-8")).hexdigest()[:16],
    }


def render_summary_md(result: dict) -> str:
    """The per-category summary table as a handover markdown file."""
    s = result["summary"]
    lines = ["# 文献分类批次汇总（batch summary）", ""]
    lines.append("schema " + result["schema_version"] + " · spec_sha256 "
                 + result["spec_sha256"] + " · records " + str(s["total_records"]))
    lines.append("")
    lines.append("| category | primary count | label mentions |")
    lines.append("|-|-|-|")
    for cat, n in s["per_category"].items():
        m = s["label_mentions"].get(cat)
        lines.append("| " + cat + " | " + str(n) + " | "
                     + ("—" if m is None else str(m)) + " |")
    lines.append("| **total** | " + str(s["total_records"]) + " | "
                 + str(sum(s["label_mentions"].values())) + " |")
    lines.append("")
    if s["multi_label_ids"]:
        lines.append("multi-label records（多标签，全部保留，未强行归一）: "
                     + ", ".join(s["multi_label_ids"]))
        lines.append("")
    if s["unclassified_ids"]:
        lines.append(UNCLASSIFIED + " records（诚实未归类，附原因）: "
                     + ", ".join(s["unclassified_ids"]))
        lines.append("")
    if result["findings"]:
        lines.append("## findings")
        lines.append("")
        for f in result["findings"]:
            lines.append("- " + f["rule"] + " (" + f.get("severity", "") + "): "
                         + f.get("why", ""))
        lines.append("")
    lines.append("(示意输出格式 — the table is computed from the run, never hand-written)")
    return "\n".join(lines)
