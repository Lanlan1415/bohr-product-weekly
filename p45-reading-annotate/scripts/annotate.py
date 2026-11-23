"""Annotation ingestion, verification, note structuring, linking and retrieval.

The post-extraction half of reading-annotation work: annotations arrive already
extracted (a highlight/underline/margin-note list with page and quote), and this
module does the four things that make them usable — anchor verification, typed
preservation, structured notes, and honest linking — then exports a retrieval
index. It never guesses an anchor: a quote that does not exist in the loaded
document is refused and named, not silently re-pointed; an OCR-drifted quote is
refused WITH its closest real candidate so the reader can re-extract instead of
guessing.
"""

from __future__ import annotations

import csv
import datetime
import difflib
import hashlib
import json
import re
from pathlib import Path

SCHEMA = "annotate/v3"

NOTE_KINDS = ("question", "method", "result", "reusable", "doubt", "context")
ANN_TYPES = ("highlight", "underline", "margin", "handwriting", "web-clip")

# Cue order matters: doubt is checked first so 待验证/存疑 notes are not swallowed
# by the question cues; a declared kind always wins over every cue.
_CUES = (
    ("doubt", ("待验证", "存疑", "疑点", "待确认", "doubt", "unverified", "uncertain")),
    ("question", ("为什么", "如何", "是否", "能否", "why", "how", "?", "？")),
    ("method", ("方法", "步骤", "protocol", "we measured", "we used", "实验", "测得")),
    ("result", ("结果", "表明", "增加了", "降低了", "提高了", "提升", "倍",
                "increased", "decreased", "three-fold", "fold")),
    ("reusable", ("可复用", "reusable", "template", "基准", "baseline", "参照")),
)


def note_kind(note_text: str, declared: str | None = None) -> str:
    """The note's kind: declared wins when valid, otherwise cued from the text."""
    d = (declared or "").strip().lower()
    if d in NOTE_KINDS:
        return d
    low = str(note_text or "").lower()
    for kind, cues in _CUES:
        if any(c in low for c in cues):
            return kind
    return "context"


def key_terms(note_text: str, min_len: int = 2) -> list[str]:
    """Content terms of a note, for linking. CJK bigrams + latin words."""
    s = str(note_text or "")
    latin = [w for w in re.findall(r"[A-Za-z][A-Za-z0-9_-]{%d,}" % (min_len - 1), s)]
    cjk = re.findall(r"[\u4e00-\u9fff]{%d,}" % max(min_len, 2), s)
    grams: set[str] = set(latin)
    for run in cjk:
        n = max(min_len, 2)
        grams.update(run[i:i + n] for i in range(len(run) - n + 1))
    stop = {"the", "and", "for", "with", "this", "that", "from", "are", "was",
            "他们的", "我们", "因此", "但是", "然后"}
    return sorted(g for g in grams if g.lower() not in stop)


def file_hash(text: str) -> str:
    return hashlib.sha256(str(text or "").encode("utf-8")).hexdigest()[:16]


def _string_list(value) -> list[str]:
    """Declared tags/topics/concepts/entities; no inference from filenames."""
    if value is None:
        return []
    values = value if isinstance(value, list) else [value]
    out = []
    for value in values:
        if isinstance(value, (str, int, float)) and str(value).strip():
            item = str(value).strip()
            if item not in out:
                out.append(item)
    return out


def _source_time(record: dict):
    value = next((record.get(k) for k in ("source_time", "date", "created_at", "timestamp")
                  if isinstance(record.get(k), str) and record.get(k).strip()), None)
    return value.strip() if value else None


def valid_iso_date(value: str) -> bool:
    try:
        datetime.date.fromisoformat(str(value)[:10])
        return bool(re.fullmatch(r"\d{4}-\d{2}-\d{2}(?:[T ].*)?", str(value)))
    except (ValueError, TypeError):
        return False


def _event_once(ws, event: dict) -> None:
    """Idempotent operation log: identical retries do not grow the workspace."""
    events = ws.data.setdefault("events", [])
    if event not in events:
        events.append(event)


class Annotator:
    """Annotation store over the reading workspace's documents."""

    def __init__(self, ws):
        self.ws = ws

    # --- refusals ---------------------------------------------------------
    def _ocr_suggestion(self, doc_id: str, quote: str) -> dict | None:
        """Closest real text for a refused quote, so OCR drift gets a named
        candidate instead of a bare refusal. Slides a quote-sized window over
        every paragraph (a whole-paragraph ratio would dilute a short quote to
        noise). None when nothing is close enough."""
        doc = self.ws.data["documents"].get(doc_id)
        if doc is None:
            return None
        best, best_r, best_at = None, 0.0, ""
        ql = quote.lower()
        n = len(ql)
        for i, para in enumerate(doc["paragraphs"]):
            pl = para.lower()[:1200]
            if len(pl) < max(2, n // 2):
                continue
            for s in range(0, max(1, len(pl) - n + 1)):
                r = difflib.SequenceMatcher(None, ql, pl[s:s + n]).ratio()
                if r > best_r:
                    best, best_r = i, r
                    best_at = para[s:s + n]
        if best is not None and best_r >= 0.6:
            return {"paragraph": best, "similarity": round(best_r, 2),
                    "candidate": best_at[:120]}
        return None

    def _refuse(self, refused: list, index: int, rule: str, reason: str, **extra) -> None:
        rec = {"index": index, "rule": rule, "reason": reason}
        rec.update(extra)
        refused.append(rec)

    # --- ingest -----------------------------------------------------------
    def ingest(self, doc_id: str, annotations) -> dict:
        """Verify and store one file's annotation records.

        Every record must quote text that exists in the loaded document; a
        mismatched quote is refused by name (with the closest real candidate when
        the mismatch looks like OCR drift). Type and colour semantics are kept
        verbatim — a red highlight and a yellow underline are not the same thing,
        and an unknown extractor type is preserved as-is rather than collapsed.
        """
        refused: list[dict] = []
        accepted: list[dict] = []
        newly: list[str] = []
        updated: list[str] = []
        if not isinstance(annotations, list):
            self._refuse(refused, -1, "ann.annotations_not_list",
                         "the annotations file must be a JSON list of records")
            self._trace_command_refusal(doc_id, refused)
            return {"ok": False, "accepted": [], "refused": refused}
        store = self.ws.data.setdefault("annotations", {})
        doc = self.ws.data["documents"].get(doc_id)
        if doc is None:
            self._refuse(refused, -1, "ann.doc_not_loaded",
                         f"document '{doc_id}' is not loaded")
            self._trace_command_refusal(doc_id, refused)
            return {"ok": False, "accepted": [], "refused": refused}
        for i, a in enumerate(annotations):
            if not isinstance(a, dict):
                self._refuse(refused, i, "ann.record_not_object",
                             "annotation record is not an object")
                continue
            declared_kind = a.get("kind")
            if declared_kind is not None and \
                    str(declared_kind).strip().lower() not in NOTE_KINDS:
                self._refuse(refused, i, "ann.declared_kind_unknown",
                             f"declared kind '{declared_kind}' is not one of "
                             f"{list(NOTE_KINDS)}; declare a valid kind or omit it "
                             f"to let the text cues decide")
                continue
            quote = str(a.get("quote") or "").strip()
            page = a.get("page")
            if not quote:
                self._refuse(refused, i, "ann.no_quote",
                             "no quote: the anchor would be empty")
                continue
            # Find EVERY occurrence, then disambiguate: the declared page picks
            # the occurrence when it resolves, the declared character offset picks
            # it when the quote repeats inside one paragraph; an ambiguous or
            # contradicting declaration is refused by name. Silently anchoring to
            # the first match is exactly the anchor-drift failure this skill
            # exists to prevent.
            hits = self.ws.find(doc_id, quote)
            # A string-valued or float declared page ("2", 2.0) is coerced, so the
            # refusal message never reads "not on the declared 1".
            if isinstance(page, str) and page.strip().isdigit():
                page = int(page.strip())
            if isinstance(page, float) and page.is_integer():
                page = int(page)
            declared_page = page
            declared_start = a.get("start")
            if isinstance(declared_start, str) and declared_start.strip().lstrip("-").isdigit():
                declared_start = int(declared_start.strip())
            if isinstance(declared_start, float) and declared_start.is_integer():
                declared_start = int(declared_start)
            if not hits:
                sug = self._ocr_suggestion(doc_id, quote)
                if sug is not None:
                    self._refuse(refused, i, "ann.anchor_ocr_drift",
                                 "anchor mismatch: the quoted text does not exist in "
                                 "the loaded document; the closest real paragraph is "
                                 "named in the suggestion — likely OCR drift or a "
                                 "re-flow change",
                                 quote=quote[:60], suggestion=sug)
                else:
                    self._refuse(refused, i, "ann.anchor_mismatch",
                                 "anchor mismatch: the quoted text does not exist "
                                 "in the loaded document",
                                 quote=quote[:60])
                continue
            if declared_page is not None:
                on_page = [h for h in hits
                           if self.ws.page_of(doc_id, h["paragraph"]) == declared_page]
                if not on_page:
                    pages_seen = sorted({self.ws.page_of(doc_id, h["paragraph"])
                                         for h in hits})
                    self._refuse(refused, i, "ann.anchor_page_conflict",
                                 "the quoted text exists only on page(s) "
                                 + str(pages_seen) + ", not on the declared "
                                 + str(declared_page), quote=quote[:60])
                    continue
                hits = on_page
            if declared_start is not None:
                at_offset = [h for h in hits if h["start"] == declared_start]
                if not at_offset:
                    self._refuse(refused, i, "ann.anchor_offset_conflict",
                                 "declared character offset " + str(declared_start)
                                 + " does not match any occurrence (found starts: "
                                 + str(sorted({h["start"] for h in hits})[:6]) + ")",
                                 quote=quote[:60])
                    continue
                hits = at_offset
            if len(hits) > 1:
                self._refuse(refused, i, "ann.anchor_ambiguous",
                             "ambiguous anchor: the quote occurs "
                             + str(len(hits)) + " times (paragraphs "
                             + str([h["paragraph"] for h in hits])
                             + "); declare the page or the character offset to "
                               "disambiguate", quote=quote[:60])
                continue
            located = hits[0]
            # 类型不丢: the extractor's type is preserved verbatim (lowercased);
            # an unknown type stays itself instead of being collapsed into highlight.
            ann_type = str(a.get("type") or "").strip().lower() or "unspecified"
            rec = {
                "doc_id": doc_id,
                "page": self.ws.page_of(doc_id, located["paragraph"]),
                "paragraph": located["paragraph"],
                "start": located["start"],
                "end": located["end"],
                "quote": quote,
                "type": ann_type,
                "color": str(a.get("color") or "").strip() or None,
                "note_text": str(a.get("note") or a.get("text") or "").strip(),
                "note_kind": note_kind(a.get("note") or a.get("text"), a.get("kind")),
                "tags": _string_list(a.get("tags")),
                "topics": _string_list(a.get("topics") or a.get("topic")),
                "key_concepts": _string_list(a.get("key_concepts") or a.get("concepts")),
                "entities": _string_list(a.get("entities") or a.get("entity")),
                "source_time": _source_time(a),
                "source_sha": doc["sha256"][:16],
                # Runtime wall clock is deliberately excluded: exported notes,
                # cards, indexes and result.json must be deterministic.  This
                # nullable field remains only for backward schema compatibility.
                "ingested_at": None,
            }
            key = hashlib.sha256(json.dumps(
                {k: rec[k] for k in ("doc_id", "quote", "type", "page", "paragraph")},
                sort_keys=True).encode("utf-8")).hexdigest()[:12]
            rec["annotation_id"] = key
            first_time = key not in store
            accepted_rec = rec
            if first_time:
                newly.append(key)
                store[key] = rec
                # Register the anchor once, so re-ingesting the same file never
                # inflates the workspace's anchor list. The anchor carries the
                # RESOLVED page, so a page-less ingest still verifies.
                self.ws.add_anchor("annotation", {
                    "doc_id": doc_id, "page": rec["page"],
                    "paragraph": located["paragraph"],
                    "start": located["start"], "end": located["end"],
                    "quote": quote,
                }, {"annotation_id": key})
            else:
                existing = store[key]
                editable = ("color", "note_text", "note_kind", "tags", "topics",
                            "key_concepts", "entities", "source_time", "source_sha")
                delta = {k: {"old": existing.get(k), "new": rec.get(k)}
                         for k in editable if existing.get(k) != rec.get(k)}
                if delta:
                    updated.append(key)
                    store[key] = rec
                    change = {"kind": "annotation-update", "annotation_id": key,
                              "doc_id": doc_id, "fields": delta}
                    _event_once(self.ws, change)
                    changes = self.ws.data.setdefault("changes", [])
                    if change not in changes:
                        changes.append(change)
                else:
                    accepted_rec = existing
            accepted.append(accepted_rec)
        if newly or updated or refused:
            _event_once(self.ws, {
                "kind": "ingest", "doc_id": doc_id,
                "accepted": len(accepted), "refused": len(refused),
                "newly_stored": len(newly), "updated": len(updated),
                "refusal_rules": [r.get("rule") for r in refused][:10],
            })
        self._persist_refusals(doc_id, refused)
        return {"ok": bool(accepted), "accepted": accepted, "refused": refused,
                "newly_stored": len(newly), "updated": len(updated)}

    def _trace_command_refusal(self, doc_id: str, refused: list) -> None:
        """Command-level refusals (nothing was ingested, so there is nothing to
        recover into the deliverable): recorded in the event trail and returned
        to the caller, not parked in the per-document refusal bag."""
        _event_once(self.ws, {
            "kind": "ingest", "doc_id": doc_id,
            "accepted": 0, "refused": len(refused), "newly_stored": 0, "updated": 0,
            "refusal_rules": [r.get("rule") for r in refused][:10],
        })

    def _persist_refusals(self, doc_id: str, refused: list) -> None:
        """Keep the LATEST ingest's refusal records per document in the workspace,
        so 失败与恢复 reflects the current state: a refusal the reader has fixed
        (or a re-ingest without it) clears the old record, and the history of
        counts stays in operation_trace. Refusals carry their doc_id."""
        for r in refused:
            r.setdefault("doc_id", doc_id)
        bag = [r for r in self.ws.data.setdefault("refusals", [])
               if r.get("doc_id") != doc_id]
        bag.extend(refused)
        del bag[:-400]
        self.ws.data["refusals"] = bag

    # --- duplicate files --------------------------------------------------
    def duplicate_doc_ids(self, doc_id: str) -> list[str]:
        """Other doc ids whose content hash is identical — the same file
        downloaded twice. They are reported, never silently merged."""
        doc = self.ws.data["documents"].get(doc_id)
        if doc is None:
            return []
        return [k for k, v in self.ws.data["documents"].items()
                if k != doc_id and v.get("sha256") == doc.get("sha256")]

    # --- notes ------------------------------------------------------------
    def structured_notes(self, doc_id: str | None = None) -> list[dict]:
        """Every annotation as a structured note with its source anchor."""
        out = []
        records = list(self.ws.data.get("annotations", {}).values())
        for rec in sorted(records, key=lambda r: r["annotation_id"]):
            if doc_id and rec["doc_id"] != doc_id:
                continue
            out.append({
                "annotation_id": rec["annotation_id"],
                "doc_id": rec["doc_id"],
                "note_kind": rec["note_kind"],
                "quote": rec["quote"],
                "anchor": {"doc_id": rec["doc_id"], "page": rec["page"],
                           "paragraph": rec["paragraph"], "start": rec["start"],
                           "end": rec["end"]},
                "type": rec["type"],
                "color": rec["color"],
                "tags": rec.get("tags", []),
                "topics": rec.get("topics", []),
                "key_concepts": rec.get("key_concepts", []),
                "entities": rec.get("entities", []),
                "source_time": rec.get("source_time"),
                "note_text": rec["note_text"],
                "source_sha": rec["source_sha"],
                "ingested_at": rec.get("ingested_at"),
                "terms": key_terms(rec["note_text"] + " " + rec["quote"]),
            })
        return out

    def links(self, notes: list[dict], min_shared: int = 2) -> list[dict]:
        """Link notes that share >= min_shared content terms AND the same kind.

        Sharing one term is not a knowledge relation; requiring the same note kind
        keeps a method note from being chained to a result note on a shared word.
        The shared terms ARE the link's stated evidence — 可解释, not a black box.
        """
        try:
            min_shared = max(2, int(min_shared))
        except (TypeError, ValueError):
            min_shared = 2
        out = []
        for i in range(len(notes)):
            for j in range(i + 1, len(notes)):
                a, b = notes[i], notes[j]
                if a["note_kind"] != b["note_kind"]:
                    continue
                shared = sorted(set(a["terms"]) & set(b["terms"]))
                if len(shared) >= min_shared:
                    out.append({"between": [a["annotation_id"], b["annotation_id"]],
                                "shared_terms": shared[:6], "kind": a["note_kind"]})
        return out

    def version_siblings(self, notes: list[dict]) -> list[dict]:
        """Same quote annotated in different source files (versions/duplicate
        downloads): the records stay separate with their own hashes, and the
        split is made EXPLICIT as a version-sibling link instead of either
        silently merging the versions or leaving the batch disjointed."""
        out = []
        for i in range(len(notes)):
            for j in range(i + 1, len(notes)):
                a, b = notes[i], notes[j]
                if a["doc_id"] == b["doc_id"]:
                    continue
                if a["quote"] == b["quote"] and a["type"] == b["type"]:
                    out.append({"between": [a["annotation_id"], b["annotation_id"]],
                                "kind": "version-sibling",
                                "evidence": "the same quote and type appear in two "
                                            "source files; records keep their own "
                                            "source hashes",
                                "docs": [a["doc_id"], b["doc_id"]]})
        return out

    def card_for_note(self, note: dict) -> dict:
        """One stable, source-grounded knowledge card per structured note."""
        declared = set(note.get("key_concepts", [])) | set(note.get("entities", []))
        lexical = set(note.get("tags", [])) | set(note.get("terms", [])[:6])
        # Declared concepts/entities suppress noisy lexical fallback; declared
        # tags remain meaningful concepts without rewriting their source values.
        concepts = sorted(declared | set(note.get("tags", []))) if declared else sorted(lexical)
        comment = bool(note.get("note_text"))
        return {
            "card_id": "card-" + note["annotation_id"],
            "annotation_ids": [note["annotation_id"]],
            "doc_id": note["doc_id"],
            "note_kind": note["note_kind"],
            "title": (note.get("key_concepts") or note.get("tags") or
                      [note["note_kind"] + ": " + note["quote"][:32]])[0],
            "topics": sorted(note.get("topics", [])),
            "tags": sorted(note.get("tags", [])),
            "key_concepts": concepts,
            "concepts_origin": "declared+lexical" if declared else "lexical-fallback",
            "entities": sorted(note.get("entities", [])),
            "source_excerpt": note["quote"],
            "reader_comment": note.get("note_text") or None,
            "summary": note.get("note_text") or note["quote"],
            "summary_kind": "reader_comment" if comment else "source_excerpt",
            "anchor": note["anchor"],
            "source_sha": note["source_sha"],
            "source_time": note.get("source_time"),
            "type": note["type"], "color": note.get("color"),
            "review_schedule": {"interval_days": [1, 3, 7, 16], "state": "not_started",
                                "due_date": None,
                                "note": "relative offsets only; no review was performed or dated"},
            "related_card_ids": [], "backlinks": [],
        }

    def knowledge_cards(self, notes: list[dict], links: list[dict] | None = None,
                        siblings: list[dict] | None = None) -> list[dict]:
        """Cards plus explicit reciprocal links and backlinks.

        Hypothesis-style selectors remain on the source annotation; cards reuse
        that one anchor rather than inventing a second locator.  All associations
        are explainable shared terms or version-sibling evidence.
        """
        cards = [self.card_for_note(n) for n in notes]
        by_ann = {c["annotation_ids"][0]: c for c in cards}
        links = self.links(notes) if links is None else links
        siblings = self.version_siblings(notes) if siblings is None else siblings
        for edge in list(links) + list(siblings):
            a, b = edge["between"]
            if a not in by_ann or b not in by_ann:
                continue
            ca, cb = by_ann[a]["card_id"], by_ann[b]["card_id"]
            edge["between_cards"] = [ca, cb]
            edge["directions"] = [[ca, cb], [cb, ca]]
            edge["bidirectional"] = True
            by_ann[a]["related_card_ids"].append(cb)
            by_ann[b]["related_card_ids"].append(ca)
            by_ann[a]["backlinks"].append(cb)
            by_ann[b]["backlinks"].append(ca)
        for card in cards:
            card["related_card_ids"] = sorted(set(card["related_card_ids"]))
            card["backlinks"] = sorted(set(card["backlinks"]))
            card["wikilinks"] = ["[[" + c + "]]" for c in card["related_card_ids"]]
        return cards

    def follow_up_actions(self, cards: list[dict]) -> list[dict]:
        out = []
        for card in cards:
            verify = card["note_kind"] in {"doubt", "question"}
            out.append({
                "card_id": card["card_id"],
                "action": "verify-against-source" if verify else "scheduled-retrieval-review",
                "reason": "reader marked a question/doubt" if verify else
                          "review the anchored excerpt and retrieve related cards",
                "anchor": card["anchor"],
                "related_card_ids": card["related_card_ids"],
                "review_schedule": card["review_schedule"],
            })
        return out

    def retrieve(self, question: str, notes: list[dict], top: int = 8,
                 kind: str | None = None, doc_id: str | None = None,
                 tag: str | None = None, topic: str | None = None,
                 concept: str | None = None, entity: str | None = None,
                 since: str | None = None, until: str | None = None) -> list[dict]:
        """Rank notes against a question by shared terms; honest about misses.

        Filters (kind / doc_id / tag) narrow the searched pool; an empty result
        after filtering is a miss and is returned as an empty list, never padded.
        """
        for label, value in (("since", since), ("until", until)):
            if value is not None and not valid_iso_date(value):
                raise ValueError(f"{label} must be an ISO date (YYYY-MM-DD)")
        try:
            top = max(1, int(top))
        except (TypeError, ValueError):
            top = 8
        pool = notes
        if kind:
            pool = [n for n in pool if n["note_kind"] == kind]
        if doc_id:
            pool = [n for n in pool if n["doc_id"] == doc_id]
        if tag:
            pool = [n for n in pool if tag in n.get("tags", [])]
        if topic:
            pool = [n for n in pool if topic in n.get("topics", [])]
        if concept:
            pool = [n for n in pool if concept in self.card_for_note(n)["key_concepts"]]
        if entity:
            pool = [n for n in pool if entity in n.get("entities", [])]
        if since:
            pool = [n for n in pool if n.get("source_time") and
                    valid_iso_date(n["source_time"]) and n["source_time"][:10] >= since[:10]]
        if until:
            pool = [n for n in pool if n.get("source_time") and
                    valid_iso_date(n["source_time"]) and n["source_time"][:10] <= until[:10]]
        q_terms = set(key_terms(question))
        if not q_terms:
            return []
        scored = []
        for n in pool:
            card = self.card_for_note(n)
            search_terms = set(n["terms"]) | set(key_terms(" ".join(
                card["tags"] + card["topics"] + card["key_concepts"] + card["entities"])))
            shared = sorted(q_terms & search_terms)
            if shared:
                scored.append({"annotation_id": n["annotation_id"], "card_id": card["card_id"],
                               "score": len(shared), "shared": shared[:6],
                               "note_kind": n["note_kind"], "doc_id": n["doc_id"],
                               "topics": card["topics"], "tags": card["tags"],
                               "key_concepts": card["key_concepts"], "entities": card["entities"],
                               "source_time": card["source_time"],
                               "note_text": n.get("note_text"),
                               "quote": n["quote"][:80], "anchor": n["anchor"]})
        scored.sort(key=lambda x: (-x["score"], x["card_id"]))
        return scored[:top]

    def export(self, out_dir: Path) -> dict:
        """Export notes, linked knowledge cards, a review sheet and one index."""
        notes = self.structured_notes()
        links = self.links(notes)
        siblings = self.version_siblings(notes)
        cards = self.knowledge_cards(notes, links, siblings)
        followups = self.follow_up_actions(cards)
        by_ann = {c["annotation_ids"][0]: c for c in cards}
        out_dir = Path(out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        lines = ["# Reading annotations — structured notes", ""]
        for n in notes:
            a = n["anchor"]
            card = by_ann[n["annotation_id"]]
            where = f"`{n['doc_id']}` " + (f"p.{a['page']}, " if a["page"] is not None else "page=unprovided, ")
            where += f"¶{a['paragraph']}, chars {a['start']}–{a['end']}"
            lines.append(f"## [[{card['card_id']}]] [{n['note_kind']}] {n['quote'][:60]}")
            lines.append(f"*anchor*: {where} · type={n['type']}"
                         + (f" colour={n['color']}" if n["color"] else "")
                         + (f" · tags={','.join(n['tags'])}" if n.get("tags") else ""))
            if n["note_text"]:
                lines.append(f"reader comment (not source text): {n['note_text']}")
            lines.append(f"terms: {', '.join(n['terms'][:8])}")
            lines.append("forward: " + (", ".join("[[" + c + "]]" for c in card["related_card_ids"]) or "none"))
            lines.append("backlinks: " + (", ".join("[[" + c + "]]" for c in card["backlinks"]) or "none"))
            lines.append("")
        if siblings:
            lines.append("## Version siblings", "")
            for s in siblings:
                lines.append(f"- {s['between'][0]} ↔ {s['between'][1]} "
                             f"(docs {', '.join(s['docs'])}) — same quote in two "
                             f"source files, records stay separate")
            lines.append("")
        (out_dir / "notes.md").write_text("\n".join(lines), encoding="utf-8")

        card_lines = ["# Knowledge cards", "",
                      "Reader comments are explicitly separated from verbatim source excerpts.", ""]
        for c in cards:
            a = c["anchor"]
            where = f"`{a['doc_id']}` " + (f"p.{a['page']}, " if a["page"] is not None else "page=unprovided, ")
            where += f"¶{a['paragraph']}, chars {a['start']}–{a['end']}"
            card_lines.extend([f"## [[{c['card_id']}]] {c['title']}", "",
                               f"kind={c['note_kind']} · topics={','.join(c['topics']) or 'none'} · "
                               f"tags={','.join(c['tags']) or 'none'}",
                               f"key concepts: {', '.join(c['key_concepts']) or 'none'} ({c['concepts_origin']})",
                               f"entities: {', '.join(c['entities']) or 'none'}",
                               f"source: {where} · sha={c['source_sha']}", "",
                               "> " + c["source_excerpt"], ""])
            if c["reader_comment"]:
                card_lines.extend(["reader comment (not source text): " + c["reader_comment"], ""])
            card_lines.extend([
                "forward links: " + (", ".join("[[" + x + "]]" for x in c["related_card_ids"]) or "none"),
                "backlinks: " + (", ".join("[[" + x + "]]" for x in c["backlinks"]) or "none"),
                "review: relative offsets 1/3/7/16 days · state=not_started · due_date=null", ""])
        (out_dir / "cards.md").write_text("\n".join(card_lines), encoding="utf-8")
        with (out_dir / "review.csv").open("w", encoding="utf-8", newline="") as handle:
            writer = csv.writer(handle, lineterminator="\n")
            writer.writerow(["card_id", "front", "back", "back_kind", "interval_days",
                             "state", "due_date", "source_anchor"])
            for c in cards:
                prompt = c["reader_comment"] or "Review the verbatim source excerpt and explain its relevance"
                writer.writerow([c["card_id"], prompt, c["source_excerpt"], c["summary_kind"],
                                 "1|3|7|16", "not_started", "", json.dumps(c["anchor"], ensure_ascii=False,
                                 sort_keys=True)])
        (out_dir / "index.json").write_text(
            json.dumps({"schema_version": SCHEMA, "notes": notes, "cards": cards,
                        "links": links, "version_siblings": siblings,
                        "follow_up_actions": followups,
                        "retrieval": {"filters": ["question", "kind", "doc_id", "tag", "topic",
                                                   "concept", "entity", "since", "until"],
                                      "time_filter_uses_only_declared_source_time": True}},
                       ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
        return {"ok": True, "notes": len(notes), "cards": len(cards), "links": len(links),
                "version_siblings": len(siblings), "follow_up_actions": len(followups),
                "wrote": [str(out_dir / name) for name in
                          ("notes.md", "cards.md", "review.csv", "index.json")]}
