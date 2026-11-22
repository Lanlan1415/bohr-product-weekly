"""Benchmark for the reading-client skill.

Each scenario exercises one of the four properties the task names, and asserts behaviour rather
than presence:

  串得起来  one workspace carries document, anchors, questions and notes
  对得上原文 every answer is bound to an anchor that still resolves
  留得下来 the session survives process exit and is re-readable
  讲得清楚 the export carries page/paragraph/character anchors

    python bench_reader.py
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
CLI = HERE / "cli.py"

DOC = (
    "Surface-area limitation is the binding constraint in the current process.\n"
    "We ask whether a porous coating raises the uptake rate.\n"
    "The coated samples were measured at 25 C with six replicates per arm.\n"
    "Uptake rose three-fold under the coating, and the effect persisted at week eight.\n"
    "Only one coating thickness was tested, so the result does not generalise.\n"
)


def run(store: Path, *args) -> tuple[int, dict]:
    out = subprocess.run([sys.executable, str(CLI), "--store", str(store), *args],
                         capture_output=True, text=True)
    try:
        return out.returncode, json.loads(out.stdout.strip().splitlines()[-1])
    except Exception:
        return out.returncode, {"raw": out.stdout[-300:], "err": out.stderr[-300:]}


def scenario(name: str, fn) -> dict:
    d = Path(tempfile.mkdtemp())
    try:
        return fn(d, name)
    finally:
        shutil.rmtree(d, ignore_errors=True)


# --- scenarios --------------------------------------------------------------

def s_golden_path(d: Path, name: str) -> dict:
    """open -> find -> ask -> note -> export keeps one anchored thread."""
    store = d / "ws.json"
    (d / "doc.txt").write_text(DOC, encoding="utf-8")
    code, info = run(store, "open", "--doc-id", "paper", "--text", str(d / "doc.txt"),
                     "--page-starts", "0,2")
    if code or not info.get("ok"):
        return {"name": name, "pass": False, "why": f"open failed {info}"}
    code, hits = run(store, "find", "--doc-id", "paper", "--quote", "Uptake rose three-fold")
    if code or not hits.get("hits"):
        return {"name": name, "pass": False, "why": "find returned no anchor"}
    code, asked = run(store, "ask", "--doc-id", "paper", "--quote", "Uptake rose three-fold",
                      "--question", "what was the effect?", "--answer", "three-fold")
    if code or not asked.get("ok"):
        return {"name": name, "pass": False, "why": f"ask failed {asked}"}
    code, noted = run(store, "note", "--doc-id", "paper", "--quote",
                      "Only one coating thickness", "--text", "limitation")
    if code or not noted.get("ok"):
        return {"name": name, "pass": False, "why": f"note failed {noted}"}
    code, exp = run(store, "export", "--out", str(d / "session.md"))
    if code or not exp.get("ok"):
        return {"name": name, "pass": False, "why": f"export failed {exp}"}
    md = (d / "session.md").read_text(encoding="utf-8")
    ok = ("p.2" in md) and ("¶3" in md) and ("chars" in md) and ("Uptake rose three-fold" in md)
    return {"name": name, "pass": ok, "why": "export carries anchor and quote" if ok
            else "export lost its anchors"}


def s_quote_absent(d: Path, name: str) -> dict:
    """Asking about text that is not in the document must be refused, not answered."""
    store = d / "ws.json"
    (d / "doc.txt").write_text(DOC, encoding="utf-8")
    run(store, "open", "--doc-id", "paper", "--text", str(d / "doc.txt"))
    code, res = run(store, "ask", "--doc-id", "paper", "--quote", "uptake fell four-fold",
                    "--question", "q", "--answer", "a")
    ok = code == 4 and res.get("ok") is False
    return {"name": name, "pass": ok, "why": f"exit={code} ok={res.get('ok')}"}


def s_anchor_goes_stale(d: Path, name: str) -> dict:
    """An anchor whose text no longer matches must fail verification and block export."""
    store = d / "ws.json"
    (d / "doc.txt").write_text(DOC, encoding="utf-8")
    run(store, "open", "--doc-id", "paper", "--text", str(d / "doc.txt"))
    run(store, "ask", "--doc-id", "paper", "--quote", "Uptake rose three-fold",
        "--question", "q", "--answer", "a")
    # someone re-types the paragraph: the same offsets no longer hold that quote
    ws = json.loads(store.read_text(encoding="utf-8"))
    ws["documents"]["paper"]["paragraphs"][3] = ("Uptake rose markedly under the coating, and "
                                                 "the effect persisted at week eight.")
    store.write_text(json.dumps(ws, ensure_ascii=False), encoding="utf-8")
    code, verify = run(store, "verify")
    code2, exp = run(store, "export", "--out", str(d / "s.md"))
    ok = verify.get("ok") is False and code2 == 4
    return {"name": name, "pass": ok,
            "why": f"verify_ok={verify.get('ok')} export_exit={code2}"}


def s_persistence(d: Path, name: str) -> dict:
    """The session must survive the process: a fresh reader sees the same anchors."""
    store = d / "ws.json"
    (d / "doc.txt").write_text(DOC, encoding="utf-8")
    run(store, "open", "--doc-id", "paper", "--text", str(d / "doc.txt"))
    run(store, "ask", "--doc-id", "paper", "--quote", "Uptake rose three-fold",
        "--question", "q", "--answer", "a")
    code, verify = run(store, "verify")
    data = json.loads(store.read_text(encoding="utf-8"))
    ok = (verify.get("anchors") == 1 and len(data["questions"]) == 1
          and data["documents"]["paper"]["sha256"])
    return {"name": name, "pass": ok, "why": f"anchors={verify.get('anchors')}"}


def s_page_attribution(d: Path, name: str) -> dict:
    """A paragraph's page comes from the declared breaks, not from a guess."""
    store = d / "ws.json"
    (d / "doc.txt").write_text(DOC, encoding="utf-8")
    run(store, "open", "--doc-id", "paper", "--text", str(d / "doc.txt"),
        "--page-starts", "0,2")
    code, hits = run(store, "find", "--doc-id", "paper", "--quote", "Uptake rose three-fold")
    page = (hits.get("hits") or [{}])[0].get("page")
    # paragraphs 0,1 are page 1; 2,3,4 are page 2 -> this quote is in paragraph 3
    ok = page == 2
    return {"name": name, "pass": ok, "why": f"page={page} (expected 2)"}



def s_docfile_formfeed(d: Path, name: str) -> dict:
    """A pdftotext-style file (form-feed page breaks) gets real page numbers, no guessing."""
    store = d / "ws.json"
    lines = DOC.splitlines()
    half = chr(12).encode("utf-8")
    (d / "doc.pdf.txt").write_bytes(
        "\n".join(lines[:2]).encode("utf-8") + half
        + "\n".join(lines[2:]).encode("utf-8"))
    code, info = run(store, "open", "--doc-id", "paper", "--doc-file", str(d / "doc.pdf.txt"))
    if code or not info.get("ok"):
        return {"name": name, "pass": False, "why": f"open failed {info}"}
    if info.get("pages", 0) < 2 or not info.get("derived_page_starts"):
        return {"name": name, "pass": False, "why": f"form feeds not turned into pages: {info}"}
    code, hits = run(store, "find", "--doc-id", "paper", "--quote", "Only one coating thickness")
    page = (hits.get("hits") or [{}])[0].get("page")
    if page != 2:
        return {"name": name, "pass": False, "why": f"page={page} (expected 2)"}
    return {"name": name, "pass": True, "why": f"pages={info.get('pages')} page=2"}

def s_result_contract(d: Path, name: str) -> dict:
    """result echoes case_id + output_contract fields; missing ones land null + limits."""
    store = d / "ws.json"
    (d / "doc.txt").write_text(DOC, encoding="utf-8")
    case = d / "case.json"
    case.write_text(json.dumps({
        "case_id": "case-rc-1",
        "output_contract": ["status", "case_id", "reading_result", "anchors",
                            "reading_notes", "not_derivable_field"],
        "reading_notes": "carried-value"}), encoding="utf-8")
    run(store, "open", "--doc-id", "paper", "--text", str(d / "doc.txt"), "--page-starts", "0,2")
    run(store, "note", "--doc-id", "paper",
        "--quote", "Uptake rose three-fold", "--text", "key effect")
    code, _ = run(store, "result", "--case", str(case), "--out", str(d / "out"))
    res_file = d / "out" / "result.json"
    if code or not res_file.exists():
        return {"name": name, "pass": False, "why": f"result exit {code}"}
    res = json.loads(res_file.read_text(encoding="utf-8"))
    if res.get("case_id") != "case-rc-1" or res.get("reading_notes") != "carried-value":
        return {"name": name, "pass": False, "why": "contract echo wrong"}
    if not res.get("anchors"):
        return {"name": name, "pass": False, "why": "engine-carried anchors missing"}
    if res.get("not_derivable_field") is not None or not res.get("limits"):
        return {"name": name, "pass": False, "why": "undeducible field must be null + limits"}
    return {"name": name, "pass": True, "why": "case_id + contract fields echoed, null+limits for the rest"}


def s_result_refusals(d: Path, name: str) -> dict:
    """Bad case / bad store refuse with exit 5 + result.json, never a traceback."""
    case = d / "case.json"
    case.write_text("{not json", encoding="utf-8")
    code, _ = run(d / "ws.json", "result", "--case", str(case), "--out", str(d / "out1"))
    if code != 5 or not (d / "out1" / "result.json").exists():
        return {"name": name, "pass": False, "why": f"bad case: exit {code}"}
    (d / "broken_ws.json").write_text("{oops", encoding="utf-8")
    case2 = d / "case2.json"
    case2.write_text(json.dumps({"case_id": "c2", "output_contract": ["status"]}), encoding="utf-8")
    code, _ = run(d / "broken_ws.json", "result", "--case", str(case2), "--out", str(d / "out2"))
    if code != 5 or not (d / "out2" / "result.json").exists():
        return {"name": name, "pass": False, "why": f"bad store: exit {code}"}
    return {"name": name, "pass": True, "why": "both refusals recorded exit 5 + result.json"}


def s_open_missing_doc(d: Path, name: str) -> dict:
    """open with a missing file refuses exit 5, prints one JSON line."""
    code, info = run(d / "ws.json", "open", "--doc-id", "x", "--text", str(d / "nope.txt"))
    if code != 5 or info.get("ok") is not False:
        return {"name": name, "pass": False, "why": f"exit {code} {str(info)[:60]}"}
    return {"name": name, "pass": True, "why": "missing document refused exit 5 with a reason"}


def s_ask_evidence_quote(d: Path, name: str) -> dict:
    """ask --evidence-quote: a wrong evidence quote refuses exit 4; a right one is stored."""
    store = d / "ws.json"
    (d / "doc.txt").write_text(DOC, encoding="utf-8")
    run(store, "open", "--doc-id", "paper", "--text", str(d / "doc.txt"), "--page-starts", "0,2")
    code, _ = run(store, "ask", "--doc-id", "paper",
                  "--quote", "Uptake rose three-fold",
                  "--question", "effect?", "--answer", "3x",
                  "--evidence-quote", "no such sentence here")
    if code != 4:
        return {"name": name, "pass": False, "why": f"absent evidence exit {code}"}
    code, _ = run(store, "ask", "--doc-id", "paper",
                  "--quote", "Uptake rose three-fold",
                  "--question", "effect?", "--answer", "3x",
                  "--evidence-quote", "Only one coating thickness was tested")
    ws = json.loads(store.read_text(encoding="utf-8"))
    q = ws.get("questions", [{}])[-1]
    if code or "evidence" not in q:
        return {"name": name, "pass": False, "why": f"evidence not stored (exit {code})"}
    return {"name": name, "pass": True, "why": "evidence quote located and bound to the answer"}


SCEN = [s_golden_path, s_quote_absent, s_anchor_goes_stale, s_persistence,
        s_page_attribution, s_docfile_formfeed, s_result_contract, s_result_refusals,
        s_open_missing_doc, s_ask_evidence_quote]


def main() -> int:
    rows = [scenario(fn.__name__.replace("s_", ""), fn) for fn in SCEN]
    for r in rows:
        print(f"{'PASS' if r['pass'] else 'FAIL'}  {r['name']:<22} {r['why']}")
    passed = sum(1 for r in rows if r["pass"])
    report = {"schema_version": "reader-bench/v1", "scenarios": rows,
              "totals": {"passed": passed, "of": len(rows)},
              "note": ("Behavioural: each scenario runs the CLI and asserts the four properties "
                       "the task names. A clean run is not the baseline here, a missing refusal is.")}
    (HERE / "report_reader.json").write_text(json.dumps(report, ensure_ascii=False, indent=2),
                                             encoding="utf-8")
    print(f"\n{passed}/{len(rows)} pass")
    return 0 if passed == len(rows) else 1


if __name__ == "__main__":
    raise SystemExit(main())
