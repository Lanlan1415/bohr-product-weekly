"""Command line for the writing client: propose, decide, apply, diff, restore, export.

Refusals print one JSON line with an honest reason and exit 4 — including an unreadable or
empty draft (load.unreadable / load.empty_draft), which is a diagnosis, not a traceback.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import writing_client as W  # noqa: E402


def _client(store) -> W.WritingClient:
    return W.WritingClient(store)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="wcli")
    ap.add_argument("--store", required=True)
    sub = ap.add_subparsers(dest="cmd", required=True)

    ld = sub.add_parser("load", help="load a draft")
    ld.add_argument("--text", required=True)
    ld.add_argument("--materials", default="[]", help="JSON list of {id, content?}")
    ld.add_argument("--references", default="[]", help="JSON list of {key, content?}")
    ld.add_argument("--case-id", default="", help="the case's input identifier, echoed into "
                                                  "the export and the structured result")

    pl = sub.add_parser("plan", help="register the workorder's edit points")
    pl.add_argument("--workorder", required=True,
                    help="JSON file: a list of point ids or {id, task} objects")

    sub.add_parser("coverage", help="report which workorder points have cards")

    pr = sub.add_parser("propose", help="propose edits from a JSON file")
    pr.add_argument("--edits", required=True,
                    help="JSON list of {kind,quote,after,basis, covers?, confirm?}")

    de = sub.add_parser("accept", help="accept a card")
    de.add_argument("--id", required=True)
    de.add_argument("--reason", default="")

    rj = sub.add_parser("reject", help="reject a card")
    rj.add_argument("--id", required=True)
    rj.add_argument("--reason", default="")

    sub.add_parser("apply", help="apply accepted cards")

    df = sub.add_parser("diff", help="diff two versions")
    df.add_argument("--from", dest="a", required=True)
    df.add_argument("--to", dest="b", required=True)

    rs = sub.add_parser("restore", help="restore a version as a new one")
    rs.add_argument("--version", required=True)

    ex = sub.add_parser("export", help="write tracked changes and final text")
    ex.add_argument("--out", required=True)

    rt = sub.add_parser("result", help="write the structured result for the output contract")
    rt.add_argument("--out", required=True)

    a = ap.parse_args(argv)
    c = _client(a.store)

    if a.cmd == "load":
        try:
            text = Path(a.text).read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            # 文档损坏或加密: identified as its own failure, never a traceback.
            print(json.dumps({"ok": False,
                              "reason": "load.unreadable: the draft could not be read as "
                                        "UTF-8 text",
                              "error": str(exc)}, ensure_ascii=False))
            return 4
        try:
            materials = json.loads(a.materials) if a.materials else []
            references = json.loads(a.references) if a.references else []
        except json.JSONDecodeError as exc:
            print(json.dumps({"ok": False,
                              "reason": f"load.unreadable: materials/references are not valid JSON: {exc}"},
                             ensure_ascii=False))
            return 4
        info = c.load(text, materials, references,
                      case_id=a.case_id.strip() or None)
        if not info.get("ok"):
            print(json.dumps(info, ensure_ascii=False))
            return 4
        c.save()
        print(json.dumps({"ok": True, **info}))
        return 0

    if a.cmd == "plan":
        try:
            points = json.loads(Path(a.workorder).read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, ValueError) as exc:
            print(json.dumps({"ok": False,
                              "reason": "plan.coverage: the workorder could not be read as "
                                        "JSON", "error": str(exc)}, ensure_ascii=False))
            return 4
        res = c.plan(points)
        c.save()
        print(json.dumps(res, ensure_ascii=False))
        return 0 if res.get("ok") else 4

    if a.cmd in ("diff", "export", "result", "accept", "reject", "apply",
                 "restore") and not c.loaded():
        print(json.dumps({"ok": False,
                          "reason": "no document loaded: run load before this command"},
                         ensure_ascii=False))
        return 4
    if a.cmd == "coverage":
        print(json.dumps(c.coverage(), ensure_ascii=False))
        return 0

    if a.cmd == "propose":
        try:
            edits = json.loads(Path(a.edits).read_text(encoding="utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            print(json.dumps({"ok": False,
                              "reason": f"edits file is not readable JSON: {exc}"},
                             ensure_ascii=False))
            return 4
        if not c.loaded():
            print(json.dumps({"ok": False,
                              "reason": "no document loaded: run load before this command"},
                             ensure_ascii=False))
            return 4
        res = c.propose(edits)
        c.save()
        print(json.dumps({"ok": not res["refused"], **res}, ensure_ascii=False))
        return 0 if not res["refused"] else 4

    if a.cmd in ("accept", "reject"):
        res = c.decide(a.id, a.cmd == "accept", a.reason)
        c.save()
        print(json.dumps(res, ensure_ascii=False))
        return 0 if res.get("ok") else 4

    if a.cmd == "apply":
        res = c.apply()
        c.save()
        print(json.dumps(res, ensure_ascii=False))
        return 0 if res.get("ok") else 4

    if a.cmd == "diff":
        print(json.dumps({"ok": True, "changes": c.diff(a.a, a.b)}, ensure_ascii=False))
        return 0

    if a.cmd == "restore":
        res = c.restore(a.version)
        c.save()
        print(json.dumps(res, ensure_ascii=False))
        return 0 if res.get("ok") else 4

    if a.cmd == "export":
        res = c.export(a.out)
        print(json.dumps(res, ensure_ascii=False))
        return 0 if res.get("ok") else 4

    if a.cmd == "result":
        res = c.result(a.out)
        print(json.dumps(res, ensure_ascii=False))
        return 0 if res.get("ok") else 4
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
