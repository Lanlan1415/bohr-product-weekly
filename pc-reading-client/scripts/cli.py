"""Command-line front end for the reading client."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import reader  # noqa: E402


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="reader", description="A minimal reading client")
    ap.add_argument("--store", required=True, help="workspace JSON path")
    sub = ap.add_subparsers(dest="cmd", required=True)

    d = sub.add_parser("open", help="add a document")
    d.add_argument("--doc-id", required=True)
    d.add_argument("--text", default="", help="path to a UTF-8 text file")
    d.add_argument("--doc-file", default="",
                   help="path to a UTF-8 text/markdown file; form feeds (U+000C, kept "
                        "by pdftotext-style PDF extraction) mark page breaks and become "
                        "page numbers with no guessing")
    d.add_argument("--page-starts", default="", help="comma-separated first paragraph index per page")

    f = sub.add_parser("find", help="locate text and print anchors")
    f.add_argument("--doc-id", required=True)
    f.add_argument("--quote", required=True)

    q = sub.add_parser("ask", help="record a question bound to an anchor")
    q.add_argument("--doc-id", required=True)
    q.add_argument("--quote", required=True)
    q.add_argument("--question", required=True)
    q.add_argument("--answer", required=True)

    n = sub.add_parser("note", help="record an annotation bound to an anchor")
    n.add_argument("--doc-id", required=True)
    n.add_argument("--quote", required=True)
    n.add_argument("--text", required=True)

    e = sub.add_parser("export", help="write the session as markdown")
    e.add_argument("--out", required=True)

    sub.add_parser("verify", help="re-check every anchor")

    a = ap.parse_args(argv)
    ws = reader.Workspace(a.store)

    if a.cmd == "open":
        if bool(a.text) == bool(a.doc_file):
            print(json.dumps({"ok": False,
                              "reason": "give exactly one of --text or --doc-file"}))
            return 2
        if a.doc_file:
            raw = Path(a.doc_file).read_text(encoding="utf-8")
            # Form feeds are the page-break convention of pdftotext-style extraction:
            # declared structure carried by the extractor, not inferred by us.
            page_texts = raw.split("\f")
            text = "\n".join(p.strip("\n") for p in page_texts)
            starts, idx = [], 0
            for p in page_texts[:-1]:
                idx += len([ln for ln in p.strip("\n").split("\n") if ln.strip()])
                starts.append(idx)
            info = ws.add_document(a.doc_id, text, starts)
            info["derived_page_starts"] = starts
        else:
            text = Path(a.text).read_text(encoding="utf-8")
            starts = [int(x) for x in a.page_starts.split(",") if x.strip()]
            info = ws.add_document(a.doc_id, text, starts)
        ws.save()
        print(json.dumps({"ok": True, **info}))
        return 0

    if a.cmd == "find":
        hits = ws.find(a.doc_id, a.quote)
        print(json.dumps({"ok": bool(hits), "hits": hits}, ensure_ascii=False))
        return 0 if hits else 3

    anchor_for = lambda: _first_anchor(ws, a.doc_id, a.quote)

    if a.cmd == "ask":
        anchor = anchor_for()
        if anchor is None:
            print(json.dumps({"ok": False, "reason": f"quote not found in {a.doc_id}"}))
            return 4
        try:
            payload = reader.ask(ws, a.doc_id, anchor, a.question, a.answer)
        except ValueError as exc:
            print(json.dumps({"ok": False, "reason": str(exc)}))
            return 4
        ws.save()
        print(json.dumps({"ok": True, "anchor": payload["anchor"]}, ensure_ascii=False))
        return 0

    if a.cmd == "note":
        anchor = anchor_for()
        if anchor is None:
            print(json.dumps({"ok": False, "reason": f"quote not found in {a.doc_id}"}))
            return 4
        ws.add_anchor("note", anchor, {"text": a.text})
        ws.save()
        print(json.dumps({"ok": True, "anchor": anchor}, ensure_ascii=False))
        return 0

    if a.cmd == "export":
        check = reader.verify_all(ws)
        if not check["ok"]:
            print(json.dumps({"ok": False, "invalid": check["invalid"]}, ensure_ascii=False))
            return 4
        Path(a.out).write_text(reader.export_markdown(ws), encoding="utf-8")
        print(json.dumps({"ok": True, "wrote": a.out, "anchors": check["anchors"]}))
        return 0

    if a.cmd == "verify":
        print(json.dumps(reader.verify_all(ws), ensure_ascii=False))
        return 0
    return 2


def _first_anchor(ws, doc_id: str, quote: str):
    hits = ws.find(doc_id, quote)
    return hits[0] if hits else None


if __name__ == "__main__":
    raise SystemExit(main())
