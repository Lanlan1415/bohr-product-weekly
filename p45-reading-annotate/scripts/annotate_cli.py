"""CLI for the reading-annotation skill: load docs, ingest annotations, verify,
retrieve, export, and finish with a contract-carrying result.json.

    python annotate_cli.py --store ws.json load --doc-id paper --doc-file extracted.txt
    python annotate_cli.py --store ws.json ingest --doc-id paper --annotations ann.json
    python annotate_cli.py --store ws.json retrieve --question "为什么用高温退火" [--kind method] [--doc-id paper] [--tag 温度] [--topic 涂层] [--concept uptake] [--entity sample] [--since 2024-01-01] [--until 2024-12-31]
    python annotate_cli.py --store ws.json export --out ./out
    python annotate_cli.py --store ws.json result --out /app/output [--case case.json]

Exit codes: 0 ok / done, 2 usage, 3 partial, 4 refused or failed, 5 undetermined (store or
case file unreadable — an honest refusal, never a traceback).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import reader  # noqa: E402
import annotate  # noqa: E402

# Contract fields whose VALUES are bulky material inputs, not deliverable
# metadata: they are echoed as null (and named in limits), never copied wholesale.
_BULKY = ("output_contract", "task", "materials", "documents", "annotations",
          "text", "files", "questions", "cards")
_CONTRACT_ALIASES = {
    "annotations": "notes", "knowledge_cards": "cards", "knowledge_links": "links",
    "backlinks": "links", "version_relations": "version_siblings",
    "follow_up": "follow_up_actions", "review_actions": "follow_up_actions",
    "files": "documents", "sources": "documents", "verification": "verify",
    "changes": "change_records", "logs": "operation_trace",
    "uncertainties": "uncertainty",
}


def _print(payload: dict) -> None:
    print(json.dumps(payload, ensure_ascii=False))


def _refused_result(out_dir: Path, reason: str, rule: str = "ann.store_unreadable") -> int:
    """Undetermined refusal for the result command: writes the honest minimal
    result.json (exit 5). The contract is NOT echoed on the refusal path — the
    broken file may be the case file itself."""
    result = {"schema_version": "annotate/v3", "status": "undetermined",
              "findings": [{"rule": rule, "severity": "high",
                            "message": reason}],
              "limits": ["the run could not be completed as declared"]}
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "result.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    _print({"ok": False, "status": "undetermined",
            "reason": reason,
            "wrote": str(Path(out_dir) / "result.json")})
    return 5


def _echo_contract(result: dict, case: dict, limits: list) -> None:
    """Echo case_id and every output_contract field into result.json (same
    discipline as the platform contract: a field already carried is kept; one the
    case supplies verbatim is copied unless bulky; a literal in the contract is
    backfilled; anything underivable is null and named in limits)."""
    cid = case.get("case_id")
    if cid is None:
        cid = case.get("id")
    result["case_id"] = cid
    if cid is None:
        limits.append("case_id was not present in the case file")
    contract = case.get("output_contract")
    if isinstance(contract, dict):
        for key in contract:
            if key in result:
                continue
            if key in case and key not in _BULKY:
                result[key] = case[key]
                continue
            v = contract[key]
            if isinstance(v, (str, int, float, bool)) and \
                    (not isinstance(v, str) or len(v) <= 500):
                result[key] = v
                continue
            alias = _CONTRACT_ALIASES.get(key) or _CONTRACT_ALIASES.get(key.lower())
            if alias and alias in result:
                result[key] = result[alias]
                continue
            result[key] = None
            limits.append(f"output_contract field '{key}' was not derivable by this audit")
    elif contract is not None:
        limits.append("output_contract was present but not an object, so no contract "
                      "fields were echoed")


_RECOVERY = {
    "ann.doc_not_loaded": "load the document first (load --doc-id ... --doc-file ...)",
    "ann.no_quote": "the record needs a verbatim quote as its anchor",
    "ann.record_not_object": "make every annotation record a JSON object",
    "ann.annotations_not_list": "the annotations file must be a JSON list of records",
    "ann.declared_kind_unknown": "declare a valid kind or omit kind to use text cues",
    "ann.anchor_mismatch": "fix the quote text or re-extract; never loosen the match",
    "ann.anchor_ocr_drift": "re-extract the quote from the suggested paragraph "
                            "(OCR drift or re-flow changed the text)",
    "ann.anchor_page_conflict": "correct the declared page, or omit it to resolve "
                                "from the text",
    "ann.anchor_offset_conflict": "correct the declared character offset, or omit it",
    "ann.anchor_ambiguous": "declare the page or the character offset to "
                            "disambiguate the repeated quote",
    "ann.duplicate_document": "the same content was loaded twice; keep one id or "
                              "record the alias in notes — never split the batch",
}


def _derive_status(notes: list, refusals: list, vres: dict) -> tuple[str, str]:
    if not notes:
        why = (f"no annotation was accepted; {len(refusals)} record(s) were refused"
               if refusals else "no annotations were ingested")
        return "failed", why
    if not vres.get("ok"):
        bad = len(vres.get("invalid") or [])
        return "partial", f"{bad} anchor(s) no longer resolve; re-anchor the affected records"
    if refusals:
        return "partial", f"{len(refusals)} record(s) were refused (see failure_recovery)"
    return "done", ""


def run_result(ws, ann, out_dir: Path, case_path: str | None) -> int:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    limits: list = []
    case = None
    if case_path:
        try:
            case = json.loads(Path(case_path).read_text(encoding="utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError, OSError) as exc:
            return _refused_result(out_dir, f"case file is not readable JSON: {exc}")
        if not isinstance(case, dict):
            return _refused_result(out_dir, "case file is not a JSON object")

    notes = ann.structured_notes()
    links = ann.links(notes)
    siblings = ann.version_siblings(notes)
    cards = ann.knowledge_cards(notes, links, siblings)
    followups = ann.follow_up_actions(cards)
    vres = reader.verify_all(ws)
    refusals = ws.data.get("refusals", [])
    status, reason = _derive_status(notes, refusals, vres)

    docs = []
    for k, v in ws.data["documents"].items():
        d = {"doc_id": k, "paragraphs": len(v["paragraphs"]),
             "sha256_12": v["sha256"][:12]}
        dups = ann.duplicate_doc_ids(k)
        if dups:
            d["duplicate_of"] = dups
        docs.append(d)

    invalid = vres.get("invalid") or []
    failure_recovery = []
    for r in refusals:
        entry = {"rule": r.get("rule"), "index": r.get("index"),
                 "reason": r.get("reason")}
        if r.get("rule") in _RECOVERY:
            entry["recovery"] = _RECOVERY[r.get("rule")]
        failure_recovery.append(entry)
    for b in invalid:
        failure_recovery.append({"rule": "anchor_unresolved", "index": b.get("index"),
                                 "reason": b.get("reason"),
                                 "recovery": "re-anchor the affected records against "
                                             "the current document text"})

    uncertainty = []
    for r in refusals:
        if r.get("rule") == "ann.anchor_ocr_drift":
            sug = r.get("suggestion") or {}
            uncertainty.append({
                "item": f"record {r.get('index')}: quote drifted (closest real "
                        f"paragraph {sug.get('paragraph')}, similarity "
                        f"{sug.get('similarity')})",
                "why": "re-extract the exact quote from the suggested paragraph, "
                       "or confirm the source text changed"})
    for b in invalid:
        uncertainty.append({"item": f"anchor {b.get('index')} unresolved: "
                                    f"{b.get('reason')}",
                            "why": "the document changed since ingest; re-anchor or "
                                   "record the version"})

    result = {
        "schema_version": "annotate/v3",
        "status": status,
        "status_reason": reason,
        # 资料结果: documents, structured notes/cards, reciprocal links, versions
        "documents": docs,
        "notes": notes,
        "cards": cards,
        "links": links,
        "version_siblings": siblings,
        "follow_up_actions": followups,
        "retrieval": {"filters": ["question", "kind", "doc_id", "tag", "topic",
                                   "concept", "entity", "since", "until"],
                      "time_filter_uses_only_declared_source_time": True},
        # 操作证据: hashes, verify report, idempotent event trail, edit diffs
        "verify": {"anchors": vres.get("anchors"), "invalid": invalid,
                   "ok": vres.get("ok")},
        "operation_trace": ws.data.get("events", [])[-30:],
        "change_records": ws.data.get("changes", []),
        # 失败与恢复: refusals with recovery actions, uncertainty, limits
        "failure_recovery": failure_recovery,
        "uncertainty": uncertainty,
        "limits": limits,
        "exports": ["notes.md", "cards.md", "review.csv", "index.json"],
    }
    # Finalisation always writes the editable/exportable artifacts as well as
    # result.json; one command cannot accidentally produce JSON without cards.
    ann.export(out_dir)
    if case is not None:
        _echo_contract(result, case, limits)
    (out_dir / "result.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    _print({"ok": True, "status": status, "case_id": result.get("case_id"),
            "notes": len(notes), "cards": len(cards), "links": len(links),
            "version_siblings": len(siblings), "follow_up_actions": len(followups),
            "refusals": len(refusals),
            "wrote": str(out_dir / "result.json")})
    return {"done": 0, "partial": 3, "failed": 4}.get(status, 1)


def _main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="annotate", description=__doc__)
    ap.add_argument("--store", required=True)
    sub = ap.add_subparsers(dest="cmd", required=True)

    d = sub.add_parser("load", help="load a document into the workspace")
    d.add_argument("--doc-id", required=True)
    d.add_argument("--doc-file", required=True, help="UTF-8 text; form feeds mark pages")

    g = sub.add_parser("ingest", help="verify + store annotation records")
    g.add_argument("--doc-id", required=True)
    g.add_argument("--annotations", required=True, help="JSON file of annotation records")

    sub.add_parser("notes", help="print structured notes")
    q = sub.add_parser("retrieve", help="rank notes against a question")
    q.add_argument("--question", required=True)
    q.add_argument("--kind", help="restrict to one note kind")
    q.add_argument("--doc-id", help="restrict to one source document")
    q.add_argument("--tag", help="restrict to notes carrying this tag")
    q.add_argument("--topic", help="declared topic/theme filter")
    q.add_argument("--concept", help="declared or lexical key-concept filter")
    q.add_argument("--entity", help="declared entity filter")
    q.add_argument("--since", help="inclusive ISO source_time lower bound (YYYY-MM-DD)")
    q.add_argument("--until", help="inclusive ISO source_time upper bound (YYYY-MM-DD)")

    e = sub.add_parser("export", help="write notes.md + cards.md + review.csv + index.json")
    e.add_argument("--out", required=True)

    sub.add_parser("verify", help="re-check every stored anchor")

    r = sub.add_parser("result", help="write result.json with case contract passthrough")
    r.add_argument("--out", required=True)
    r.add_argument("--case", help="case.json: echoes case_id and output_contract fields")

    a = ap.parse_args(argv)

    if a.cmd == "retrieve" and a.kind and a.kind not in annotate.NOTE_KINDS:
        _print({"ok": False, "reason": f"unknown kind '{a.kind}'; valid kinds: "
                                       f"{list(annotate.NOTE_KINDS)}"})
        return 2
    if a.cmd == "retrieve":
        if any(value is not None and not annotate.valid_iso_date(value)
               for value in (a.since, a.until)):
            _print({"ok": False, "rule": "ann.invalid_time_filter",
                    "reason": "since/until must be ISO dates (YYYY-MM-DD)"})
            return 2
        if a.since and a.until and a.since[:10] > a.until[:10]:
            _print({"ok": False, "rule": "ann.invalid_time_filter",
                    "reason": "since must not be later than until"})
            return 2

    try:
        ws = reader.Workspace(a.store)
    except (json.JSONDecodeError, UnicodeDecodeError, OSError) as exc:
        if a.cmd == "result":
            return _refused_result(Path(a.out),
                                   f"workspace store is unreadable: {exc}")
        _print({"ok": False, "status": "undetermined", "rule": "ann.store_unreadable",
                "reason": f"workspace store is unreadable: {exc}"})
        return 5
    ann = annotate.Annotator(ws)

    if a.cmd == "load":
        doc_path = Path(a.doc_file)
        if not doc_path.exists():
            _print({"ok": False, "rule": "ann.doc_file_missing",
                    "reason": "document file not found: " + a.doc_file})
            return 4
        try:
            raw = doc_path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError) as exc:
            _print({"ok": False, "rule": "ann.doc_file_unreadable",
                    "reason": "document file could not be read: " + str(exc)})
            return 4
        page_texts = raw.split("\f")
        text = "\n".join(p.strip("\n") for p in page_texts)
        starts, idx = [], 0
        for p in page_texts[:-1]:
            idx += len([ln for ln in p.strip("\n").split("\n") if ln.strip()])
            starts.append(idx)
        info = ws.add_document(a.doc_id, text, starts)
        # A duplicate download (same content, another id) is reported, never
        # silently merged or split into two unrelated batches.
        dups = ann.duplicate_doc_ids(a.doc_id)
        if dups:
            annotate._event_once(ws, {"kind": "duplicate-document",
                                      "doc_id": a.doc_id, "duplicate_of": dups})
        try:
            ws.save()
        except OSError as exc:
            _print({"ok": False, "status": "undetermined", "rule": "ann.store_unwritable",
                    "reason": f"workspace store could not be written: {exc}"})
            return 5
        _print({"ok": True, **info,
                "duplicate_of": dups if dups else None})
        return 0

    if a.cmd == "ingest":
        try:
            records = json.loads(Path(a.annotations).read_text(encoding="utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError, OSError) as exc:
            _print({"ok": False, "rule": "ann.annotations_unreadable",
                    "reason": f"annotations file is not readable JSON: {exc}"})
            return 4
        res = ann.ingest(a.doc_id, records)
        try:
            ws.save()
        except OSError as exc:
            _print({"ok": False, "status": "undetermined", "rule": "ann.store_unwritable",
                    "reason": f"workspace store could not be written: {exc}"})
            return 5
        _print(res)
        return 0 if res.get("ok") else 4

    if a.cmd == "notes":
        _print({"ok": True, "notes": ann.structured_notes()})
        return 0

    if a.cmd == "retrieve":
        notes = ann.structured_notes()
        filters = {"kind": a.kind, "doc_id": a.doc_id, "tag": a.tag, "topic": a.topic,
                   "concept": a.concept, "entity": a.entity, "since": a.since, "until": a.until}
        filters = {k: v for k, v in filters.items() if v is not None}
        hits = ann.retrieve(a.question, notes, kind=a.kind, doc_id=a.doc_id, tag=a.tag,
                            topic=a.topic, concept=a.concept, entity=a.entity,
                            since=a.since, until=a.until)
        event = {"kind": "retrieve", "question": a.question, "filters": filters,
                 "hit_card_ids": [h["card_id"] for h in hits]}
        annotate._event_once(ws, event)
        try:
            ws.save()
        except OSError as exc:
            _print({"ok": False, "status": "undetermined", "rule": "ann.store_unwritable",
                    "reason": f"workspace store could not be written: {exc}"})
            return 5
        _print({"ok": True, "question": a.question, "filters": filters, "hits": hits,
                "empty_reason": None if hits else "no note/card matched the question and filters; no result was invented"})
        return 0

    if a.cmd == "verify":
        res = reader.verify_all(ws)
        _print(res)
        return 0 if res.get("ok") else 4

    if a.cmd == "export":
        res = ann.export(Path(a.out))
        try:
            ws.save()
        except OSError as exc:
            _print({"ok": False, "status": "undetermined", "rule": "ann.store_unwritable",
                    "reason": f"workspace store could not be written: {exc}"})
            return 5
        _print(res)
        return 0 if res.get("ok") else 4

    if a.cmd == "result":
        return run_result(ws, ann, Path(a.out), a.case)
    return 2


def main(argv=None) -> int:
    """Last-resort structured boundary for valid-but-hostile store shapes."""
    try:
        return _main(argv)
    except Exception as exc:
        reason = "annotation pipeline refused invalid input: " + \
                 (type(exc).__name__ + ": " + str(exc))[:500]
        args = list(argv) if argv is not None else sys.argv[1:]
        if "--out" in args:
            try:
                out = Path(args[args.index("--out") + 1])
                return _refused_result(out, reason, rule="ann.invalid_input")
            except (ValueError, IndexError, OSError):
                pass
        _print({"ok": False, "status": "undetermined", "rule": "ann.invalid_input",
                "reason": reason})
        return 5


if __name__ == "__main__":
    raise SystemExit(main())
