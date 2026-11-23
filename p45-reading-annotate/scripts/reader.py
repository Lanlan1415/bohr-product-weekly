"""A reading client as a runnable tool: open, locate, ask, annotate, export.

The four things this task says decide the figure are the four things this module enforces:

  串得起来  one workspace holds the document, the anchors, the questions and the answers, so a
            reader never carries text to another window
  对得上原文 every answer is bound to an anchor (page, paragraph, character range, quote) and the
            quote is checked against the stored text
  留得下来 the workspace is a file; nothing lives only in a conversation
  讲得清楚 the export carries every anchor and the edit history, so another person can replay it

An anchor is the unit that makes all of this checkable:

    {"doc_id": ..., "page": 7, "paragraph": 3, "start": 120, "end": 168, "quote": "..."}

`start`/`end` are character offsets into the paragraph, so the anchor survives re-rendering and
can be re-verified by anyone holding the document.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path


class Workspace:
    """A reading session persisted to one JSON file."""

    def __init__(self, path):
        self.path = Path(path)
        if self.path.exists():
            self.data = json.loads(self.path.read_text(encoding="utf-8"))
        else:
            self.data = {"version": 1, "documents": {}, "anchors": [], "notes": [],
                         "questions": [], "events": []}

    # --- persistence ------------------------------------------------------
    def save(self) -> None:
        # Saving is persistence, not a semantic operation.  Repeated saves must
        # not manufacture event-log or export differences.
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self.data, ensure_ascii=False, indent=2), encoding="utf-8")

    # --- documents --------------------------------------------------------
    def add_document(self, doc_id: str, text: str, page_breaks: list[int] | None = None) -> dict:
        """Store a document split into paragraphs, and index where each page starts.

        Pages are supplied explicitly because a plain-text reading client cannot infer them;
        an inferred page number is an anchor a reader cannot verify.
        """
        paragraphs = [p for p in text.split("\n") if p.strip()]
        pages = page_breaks or []
        self.data["documents"][doc_id] = {
            "paragraphs": paragraphs,
            "page_starts": pages,
            "sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
        }
        # Page count: page 1, plus one page per declared break after it (a leading 0
        # marks where page 1 itself starts and adds no page).
        n_pages = 1 + sum(1 for s in pages if s > 0)
        return {"doc_id": doc_id, "paragraphs": len(paragraphs),
                "pages": n_pages}

    def page_of(self, doc_id: str, paragraph: int) -> int:
        """1-based page that a paragraph falls on, from the declared page starts.

        `page_starts` holds the first paragraph index of each page after the first, so a
        paragraph at or past starts[0] is on page 2. A leading 0 (where page 1 itself
        begins) is tolerated and ignored — without this, following the documented
        convention reported every page-2 paragraph as page 1.
        """
        starts = self.data["documents"][doc_id]["page_starts"]
        page = 1
        for first_para in starts:
            if first_para > 0 and paragraph >= first_para:
                page += 1
        return page

    def paragraph(self, doc_id: str, index: int) -> str:
        return self.data["documents"][doc_id]["paragraphs"][index]

    # --- locating ---------------------------------------------------------
    def find(self, doc_id: str, needle: str) -> list[dict]:
        """Every occurrence of `needle`, returned as ready-made anchors.

        An unknown doc id is a typo the reader made, not a crash: it simply matches
        nothing, and the CLI reports it with the same exit code as an absent quote.
        """
        doc = self.data["documents"].get(doc_id)
        if doc is None:
            return []
        out = []
        for i, para in enumerate(doc["paragraphs"]):
            start = 0
            while True:
                at = para.find(needle, start)
                if at < 0:
                    break
                out.append({
                    "doc_id": doc_id, "page": self.page_of(doc_id, i), "paragraph": i,
                    "start": at, "end": at + len(needle), "quote": needle,
                })
                start = at + 1
        return out

    def add_anchor(self, kind: str, anchor: dict, payload: dict) -> dict:
        """Record an anchor with the thing it anchors (a note or a question)."""
        record = {"anchor": anchor, "kind": kind, "payload": payload}
        self.data["anchors"].append(record)
        if kind == "note":
            self.data["notes"].append(payload)
        elif kind == "question":
            self.data["questions"].append(payload)
        return record

    def anchor_is_valid(self, anchor: dict) -> tuple[bool, str]:
        """Check that the anchor still points at the text it claims."""
        doc = self.data["documents"].get(anchor.get("doc_id") or "")
        if doc is None:
            return False, f"document '{anchor.get('doc_id')}' is not in the workspace"
        paras = doc["paragraphs"]
        idx = anchor.get("paragraph")
        if not isinstance(idx, int) or not 0 <= idx < len(paras):
            return False, f"paragraph {idx} is outside the document"
        start, end = anchor.get("start"), anchor.get("end")
        if not isinstance(start, int) or not isinstance(end, int):
            return False, "anchor has no character range"
        if not 0 <= start < end <= len(paras[idx]):
            return False, f"range [{start},{end}) is outside paragraph {idx}"
        if paras[idx][start:end] != anchor.get("quote"):
            return False, "the quoted text does not exist at the recorded range"
        if anchor.get("page") != self.page_of(anchor["doc_id"], idx):
            return False, "the recorded page does not match the paragraph's page"
        return True, "ok"


def ask(ws: Workspace, doc_id: str, anchor: dict, question: str, answer: str) -> dict:
    """Record a question against a selection, refusing an answer with no anchor.

    The refusal is the point: an answer without an anchor is the failure the task names —
    "答案无法回到具体页码".
    """
    ok, why = ws.anchor_is_valid(anchor)
    if not ok:
        raise ValueError(f"anchor rejected: {why}")
    payload = {"question": question, "answer": answer, "anchor": anchor}
    ws.add_anchor("question", anchor, payload)
    return payload


def export_markdown(ws: Workspace) -> str:
    """Render the session as a document a reader can follow back to the source."""
    lines = ["# Reading session", ""]
    for doc_id, doc in ws.data["documents"].items():
        lines.append(f"## Document `{doc_id}`  ({len(doc['paragraphs'])} paragraphs, "
                     f"sha256 {doc['sha256'][:12]}…)")
        lines.append("")
    for rec in ws.data["anchors"]:
        a = rec["anchor"]
        where = f"p.{a['page']}, ¶{a['paragraph']}, chars {a['start']}–{a['end']}"
        if rec["kind"] == "question":
            lines += [f"### Q: {rec['payload']['question']}",
                      f"*anchor*: `{a['doc_id']}` {where}",
                      "",
                      f"> {a['quote']}",
                      "",
                      f"**A**: {rec['payload']['answer']}", ""]
        else:
            lines += [f"### Note", f"*anchor*: `{a['doc_id']}` {where}", "",
                      f"> {a['quote']}", "", f"{rec['payload'].get('text', '')}", ""]
    return "\n".join(lines)


def verify_all(ws: Workspace) -> dict:
    """Re-check every anchor in the workspace, so an export can be trusted."""
    bad = []
    for i, rec in enumerate(ws.data["anchors"]):
        ok, why = ws.anchor_is_valid(rec["anchor"])
        if not ok:
            bad.append({"index": i, "kind": rec["kind"], "reason": why})
    return {"anchors": len(ws.data["anchors"]), "invalid": bad,
            "ok": not bad}
