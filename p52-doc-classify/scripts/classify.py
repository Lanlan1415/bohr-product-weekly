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
import re

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
        category = str(cat["category"]).strip().strip("/")
        parts = [p.strip() for p in category.split("/") if p.strip()]
        ok.append({
            "category": category,
            "level": len(parts),
            "parent": "/".join(parts[:-1]) or None,
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


_GENERIC_CUES = {"pdf", "txt", "doc", "docx", "csv", "tsv", "json", "file",
                 "document", "paper", "download", "scan", "copy", "final", "new"}
_FIELD_WEIGHTS = {"title": 2.0, "abstract": 1.5, "keywords": 2.0, "text": 1.0,
                  "body": 1.0, "journal": 1.25, "subject": 1.5, "meta": 0.75}


def _specificity(cue: str) -> float:
    """Generic filenames/extensions cannot carry a category by themselves."""
    cue = str(cue or "").strip().casefold().lstrip(".")
    if not cue or cue in _GENERIC_CUES:
        return 0.0
    if len(cue) == 1:
        return 0.15
    if re.fullmatch(r"[a-z]{1,3}", cue):
        return 0.35
    return 1.0


def _field_texts(record: dict) -> dict[str, str]:
    fields: dict[str, str] = {}
    for key in ("title", "abstract", "keywords", "text", "body", "journal", "subject"):
        value = record.get(key)
        if isinstance(value, (list, tuple)):
            value = " ".join(str(v) for v in value)
        if value not in (None, ""):
            fields[key] = str(value)
    meta = record.get("meta")
    if isinstance(meta, dict):
        # Path/extension are deliberately excluded: those can be seen, not read.
        vals = [str(meta[k]) for k in sorted(meta)
                if k not in {"path", "file", "filename", "extension", "attachments"}
                and meta[k] not in (None, "", [], {})]
        if vals:
            fields["meta"] = "\n".join(vals)
    if not fields and record.get("text") is not None:
        fields["text"] = str(record.get("text") or "")
    return fields


def _match(field: str, needle: str) -> tuple[int, int] | None:
    """Casefolded substring for CJK; token boundaries for latin-only cues."""
    if not needle:
        return None
    if re.fullmatch(r"[a-z0-9_.+-]+", needle, flags=re.I):
        pattern = r"(?<![a-z0-9])" + re.escape(needle) + r"(?![a-z0-9])"
        match = re.search(pattern, field, flags=re.I)
        return match.span() if match else None
    match = re.search(re.escape(needle), field, flags=re.I)
    return match.span() if match else None


def classify_record(rec_id: str, text, taxonomy, min_hits: int = 1) -> dict:
    """Classify with field-weighted, source-located and calibrated evidence.

    ``confidence = evidence_share * min(top_weight/2, 1)``. It is a deterministic
    evidence score, not a learned probability. A single ordinary body cue cannot
    exceed 0.5; a generic extension or one-letter cue cannot establish a label.
    """
    record = text if isinstance(text, dict) else {"id": rec_id, "text": text}
    try:
        min_hits = max(1, int(min_hits or 1))
    except (TypeError, ValueError):
        min_hits = 1
    fields = _field_texts(record)
    labels = []
    weak = []
    for order, cat in enumerate(taxonomy):
        matched, ex_matched, evidence = [], [], []
        weight = 0.0
        for kind, candidates in (("cue", cat.get("cues") or []), ("example", cat.get("examples") or [])):
            for candidate in candidates:
                specificity = _specificity(candidate) if kind == "cue" else 1.0
                best = None
                for field, content in fields.items():
                    span = _match(content, candidate)
                    if span is None:
                        continue
                    field_weight = _FIELD_WEIGHTS.get(field, 0.75) * (2.0 if kind == "example" else 1.0)
                    candidate_evidence = {"kind": kind, "cue": candidate, "field": field,
                                          "start": span[0], "end": span[1],
                                          "quote": content[span[0]:span[1]],
                                          "field_weight": field_weight,
                                          "specificity": specificity,
                                          "weight": field_weight * specificity}
                    if best is None or candidate_evidence["weight"] > best["weight"]:
                        best = candidate_evidence
                if best is None:
                    continue
                evidence.append(best)
                if kind == "cue":
                    matched.append(candidate)
                else:
                    ex_matched.append(candidate)
                weight += best["weight"]
        hits = len(matched) + len(ex_matched)
        base = {"category": cat["category"], "level": cat.get("level", 1),
                "parent": cat.get("parent"), "cue_hits": hits,
                "weighted_evidence": round(weight, 6),
                "matched_cues": matched, "matched_examples": ex_matched,
                "evidence": evidence, "declared_order": order}
        if hits >= min_hits and weight > 0:
            labels.append(base)
        elif hits:
            weak.append(base)
    labels.sort(key=lambda l: (-l["weighted_evidence"], -l["cue_hits"], l["declared_order"]))
    total = sum(l["weighted_evidence"] for l in labels)
    if not labels:
        if weak:
            reason = "only generic/low-specificity evidence matched; candidate labels require review"
        elif not any(v.strip() for v in fields.values()):
            reason = "the record has no readable text or metadata, so no evidence can match"
        else:
            reason = "no declared cue or example appears in the record text or metadata"
        return {"id": rec_id, "primary": UNCLASSIFIED, "confidence": 0.0,
                "evidence_share": 0.0, "multi_label": False, "labels": [],
                "candidate_labels": weak, "review_required": True,
                "uncertainty": "unknown_or_weak_evidence", "reason": reason,
                "cue_hits_total": sum(x["cue_hits"] for x in weak),
                "source_evidence": [e for x in weak for e in x["evidence"]]}
    top = labels[0]
    share = top["weighted_evidence"] / total if total else 0.0
    coverage = min(top["weighted_evidence"] / 2.0, 1.0)
    confidence = round(share * coverage, 4)
    ambiguous = len(labels) > 1 and abs(top["weighted_evidence"] - labels[1]["weighted_evidence"]) < 1e-9
    for lab in labels:
        lab.pop("declared_order", None)
        lab["evidence_share"] = round(lab["weighted_evidence"] / total, 4) if total else 0.0
    first = top["evidence"][0] if top["evidence"] else None
    reason = ("top label by field-weighted exact evidence ("
              + ", ".join(top["matched_cues"][:3] or top["matched_examples"][:2]) + ")")
    if first:
        reason += f"; first evidence is {first['field']}[{first['start']}:{first['end']}]"
    if ambiguous:
        reason += "; runner-up has equal evidence and is retained as a candidate"
    elif len(labels) > 1:
        reason += "; runner-up " + labels[1]["category"] + " also matched"
    return {"id": rec_id, "primary": top["category"], "confidence": confidence,
            "evidence_share": round(share, 4), "evidence_coverage": round(coverage, 4),
            "confidence_formula": "evidence_share * min(top_weighted_evidence/2, 1); not a probability",
            "multi_label": len(labels) > 1, "labels": labels,
            "candidate_labels": [], "review_required": confidence < 0.6 or ambiguous,
            "uncertainty": ("ambiguous_top_labels" if ambiguous else
                            "low_or_single_source_evidence" if confidence < 0.6 else None),
            "ambiguity": {"is_ambiguous": ambiguous,
                          "candidate_categories": [x["category"] for x in labels[:2]] if ambiguous else []},
            "reason": reason, "cue_hits_total": sum(l["cue_hits"] for l in labels),
            "source_evidence": top["evidence"]}


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
            rec_id = str(rec.get("id") or rec.get("path") or "").strip() or "rec-" + str(i + 1).zfill(3)
            item = dict(rec)
            item["id"] = rec_id
            item["title"] = str(rec.get("title") or "").strip()
            item["text"] = "" if rec.get("text") is None else str(rec.get("text"))
            item["index"] = i
            records.append(item)
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
        cls = classify_record(rec["id"], rec, taxonomy, min_hits)
        cls["index"] = rec["index"]
        cls["title"] = rec["title"]
        if rec.get("path"):
            cls["path"] = rec["path"]
        if isinstance(rec.get("meta"), dict):
            cls["metadata"] = rec["meta"]
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
    needs_review = [r["id"] for r in results if r.get("review_required")]
    hierarchy = []
    for cat in taxonomy:
        name = cat["category"]
        children = sorted({c["category"] for c in taxonomy if c.get("parent") == name})
        subtree = sum(1 for r in results
                      if r["primary"] == name or r["primary"].startswith(name + "/"))
        hierarchy.append({"category": name, "level": cat.get("level", 1),
                          "parent": cat.get("parent"), "children": children,
                          "primary_direct": per_category.get(name, 0),
                          "primary_subtree": subtree})

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
                         "why": "these records lacked sufficient declared evidence; they are "
                                "reported as " + UNCLASSIFIED + " with reasons and candidates"})
    low = [r["id"] for r in results if r["primary"] != UNCLASSIFIED
           and r.get("confidence", 0) < 0.6]
    if low:
        findings.append({"rule": "cls.low_confidence", "severity": "low",
                         "count": len(low), "ids": low,
                         "why": "single or limited evidence; the score formula and source spans "
                                "are recorded and these classifications require review"})
    ambiguous = [r["id"] for r in results
                 if (r.get("ambiguity") or {}).get("is_ambiguous")]
    if ambiguous:
        findings.append({"rule": "cls.ambiguous", "severity": "low", "count": len(ambiguous),
                         "ids": ambiguous, "why": "top labels have equal weighted evidence; "
                                                   "primary follows declared order and alternatives remain"})

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
            "needs_review_ids": needs_review,
            "hierarchy": hierarchy,
        },
        "findings": findings,
        "taxonomy_declared": [{"category": c["category"], "level": c.get("level", 1),
                               "parent": c.get("parent"), "cues": c["cues"],
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
