"""Command-line front end for the reading client.

Every command prints one JSON line and returns a documented exit code:
0 ok, 2 usage, 3 find matched nothing, 4 refused (quote absent / anchor invalid /
export blocked), 5 undetermined (unreadable store or case, unwritable output —
refusal is recorded, never a traceback).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import reader  # noqa: E402

_BULKY = ("output_contract", "case", "text", "documents", "notes", "questions")


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()[:16]


def _write(out_dir: Path, result: dict) -> None:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "result.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")


def _refuse(out_dir, case, message: str) -> int:
    """A refusal is a recorded outcome: write result.json, exit 5, no traceback."""
    result = {"status": "undetermined",
              "findings": [{"rule": "rc.refused", "severity": "high", "message": message}],
              "limits": ["the case could not be run as declared; nothing was recorded"]}
    if isinstance(case, dict):
        cid = case.get("case_id")
        if cid is not None:
            result["case_id"] = cid
        for key in (case.get("output_contract") or []):
            if key not in result and not (key in case and key not in _BULKY):
                result[key] = None
    _write(out_dir, result)
    return 5


def _echo_contract(result: dict, case: dict, ws_summary: dict) -> dict:
    """case_id at the top; output_contract fields: engine value > spec value > null+limits."""
    limits = result.setdefault("limits", [])
    cid = case.get("case_id")
    if cid is not None:
        result["case_id"] = cid
    for key in (case.get("output_contract") or []):
        if key in result:
            continue
        if key in ws_summary and key not in _BULKY:
            result[key] = ws_summary[key]
        elif key in case and key not in _BULKY:
            result[key] = case[key]
        else:
            result[key] = None
            limits.append(f"output_contract field '{key}' was not derivable by this client")
    return result


def _load_case(path: str):
    p = Path(path)
    try:
        case = json.loads(p.read_text(encoding="utf-8-sig"))
    except (json.JSONDecodeError, UnicodeDecodeError, OSError) as exc:
        return None, f"the case file is not readable JSON: {exc}"
    if not isinstance(case, dict):
        return None, "the case file is not a JSON object"
    return case, ""


def _summary(ws) -> dict:
    check = reader.verify_all(ws)
    return {"documents": ws.data.get("documents", {}),
            "anchors": ws.data.get("anchors", []),
            "verify": {"ok": check["ok"], "anchors": check["anchors"],
                       "invalid": check.get("invalid", [])}}


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
    q.add_argument("--evidence-quote", default="",
                   help="optional second quote the answer rests on; located and stored "
                        "so the answer carries its own evidence, not just the selection")

    n = sub.add_parser("note", help="record an annotation bound to an anchor")
    n.add_argument("--doc-id", required=True)
    n.add_argument("--quote", required=True)
    n.add_argument("--text", required=True)

    e = sub.add_parser("export", help="write the session as markdown")
    e.add_argument("--out", required=True)

    sub.add_parser("verify", help="re-check every anchor")

    r = sub.add_parser("result", help="write result.json (case_id + output_contract echo)")
    r.add_argument("--case", required=True, help="path to /input-style case.json")
    r.add_argument("--out", required=True, help="output directory")

    a = ap.parse_args(argv)
    out_dir = Path(a.out).parent if a.cmd == "result" else None

    try:
        ws = reader.Workspace(a.store)
    except (json.JSONDecodeError, UnicodeDecodeError, OSError) as exc:
        case, _ = _load_case(a.case) if a.cmd == "result" else (None, "")
        print(json.dumps({"ok": False, "reason": f"workspace unreadable: {exc}"}, ensure_ascii=False))
        if a.cmd == "result":
            return _refuse(Path(a.out), case or {}, f"workspace unreadable: {exc}")
        return 5

    if a.cmd == "open":
        if bool(a.text) == bool(a.doc_file):
            print(json.dumps({"ok": False,
                              "reason": "give exactly one of --text or --doc-file"}))
            return 2
        try:
            if a.doc_file:
                raw = Path(a.doc_file).read_text(encoding="utf-8-sig")
                page_texts = raw.split("\f")
                text = "\n".join(p.strip("\n") for p in page_texts)
                starts, idx = [], 0
                for p in page_texts[:-1]:
                    idx += len([ln for ln in p.strip("\n").split("\n") if ln.strip()])
                    starts.append(idx)
                info = ws.add_document(a.doc_id, text, starts)
                info["derived_page_starts"] = starts
                info["source_sha256"] = _sha(Path(a.doc_file))
            else:
                text = Path(a.text).read_text(encoding="utf-8-sig")
                starts = [int(x) for x in a.page_starts.split(",") if x.strip()]
                info = ws.add_document(a.doc_id, text, starts)
                info["source_sha256"] = _sha(Path(a.text))
            ws.save()
        except (OSError, UnicodeDecodeError, ValueError) as exc:
            print(json.dumps({"ok": False, "reason": f"document unreadable: {exc}"}, ensure_ascii=False))
            return 5
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
        if a.evidence_quote:
            ev = _first_anchor(ws, a.doc_id, a.evidence_quote)
            if ev is None:
                print(json.dumps({"ok": False,
                                  "reason": "evidence quote not found; answer recorded with "
                                            "no evidence is refused by design"}))
                return 4
            payload["evidence"] = ev
            ws.data["questions"][-1]["evidence"] = ev
        ws.save()
        print(json.dumps({"ok": True, "anchor": payload["anchor"]}, ensure_ascii=False))
        return 0

    if a.cmd == "note":
        anchor = anchor_for()
        if anchor is None:
            print(json.dumps({"ok": False, "reason": f"quote not found in {a.doc_id}"}))
            return 4
        ws.add_anchor("note", anchor, {"text": a.text})
        try:
            ws.save()
        except OSError as exc:
            print(json.dumps({"ok": False, "reason": f"annotation write failed: {exc}"}))
            return 5
        print(json.dumps({"ok": True, "anchor": anchor}, ensure_ascii=False))
        return 0

    if a.cmd == "export":
        check = reader.verify_all(ws)
        if not check["ok"]:
            print(json.dumps({"ok": False, "invalid": check["invalid"]}, ensure_ascii=False))
            return 4
        try:
            Path(a.out).write_text(reader.export_markdown(ws), encoding="utf-8")
        except OSError as exc:
            print(json.dumps({"ok": False, "reason": f"export write failed: {exc}"}))
            return 5
        print(json.dumps({"ok": True, "wrote": a.out, "anchors": check["anchors"]}))
        return 0

    if a.cmd == "verify":
        print(json.dumps(reader.verify_all(ws), ensure_ascii=False))
        return 0

    if a.cmd == "result":
        case, err = _load_case(a.case)
        if case is None:
            return _refuse(Path(a.out), {}, err)
        summary = _summary(ws)
        result = {"status": "done" if summary["verify"]["ok"] else "review",
                  "reading_result": summary,
                  "evidence_and_boundaries": {
                      "anchors": ws.data.get("anchors", []),
                      "unreported": ["quotes that are paraphrases cannot anchor (exact "
                                     "substring only)", "scanned pages without a text layer"]},
                  "run_state": {"exit_meaning": "0 done / 4 refused / 5 undetermined",
                                "handoff": "re-run find on any anchor the verify step broke"},
                  "limits": []}
        result = _echo_contract(result, case, summary)
        _write(Path(a.out), result)
        print(json.dumps({"ok": True, "status": result["status"],
                          "wrote": str(Path(a.out) / "result.json")}, ensure_ascii=False))
        return 0
    return 2


def _first_anchor(ws, doc_id: str, quote: str):
    hits = ws.find(doc_id, quote)
    return hits[0] if hits else None


if __name__ == "__main__":
    raise SystemExit(main())
