"""Benchmark for the writing-client skill.

Behavioural: each scenario drives the CLI and asserts one of the four properties the task names.

  改得准      a rewrite is refused as a wording edit; a declared citation edit may move citations
  改得可追溯  an edit with no basis, or with a basis that does not resolve, is refused
  格式不塌    applying is refused when the edit would move headings/captions/citations/tables
  交付可用    versions diff, restore appends history, export and result carry the contract fields

The task's scoring table adds five more families, each new rule shipping with a defect scenario
and a false-positive guard (correct input must yield zero findings):

  事实与来源映射   a term edit whose replacement is not in the basis's declared content is
                   refused; a basis without declared content is never checked
  异常处理         an empty draft, an unreadable draft, an empty reference library, a quoted span
                   the manuscript does not have (指令与稿件内容冲突) and an unwritable export
                   path are each refused as their own diagnosis, never a traceback
  结果完整性       workorder points no card claims are named by coverage, never silently dropped
  版本与边界       an edit that declares confirm:true is flagged for human confirmation in the
                   export and the result; edits that do not are never flagged
  结构化交付       result writes case_id, honest status, uncertainty, change records and the
                   refused proposals with their reasons; an undeclared case_id is echoed as
                   null, never punished

    python bench_writer.py
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
CLI = HERE / "wcli.py"

DRAFT = (
    "1 Introduction\n"
    "Uptake rose markedly under the coating [doe2020].\n"
    "2 Methods\n"
    "We measured 3 mM samples.\n"
    "Fig 1 shows the rate curve.\n"
)

DRAFT_TABLE = DRAFT + "| sample | uptake |\n"


def run(store: Path, *args) -> tuple[int, dict]:
    out = subprocess.run([sys.executable, str(CLI), "--store", str(store), *args],
                         capture_output=True, text=True)
    try:
        return out.returncode, json.loads(out.stdout.strip().splitlines()[-1])
    except Exception:
        return out.returncode, {"raw": out.stdout[-200:], "err": out.stderr[-200:]}


def setup(d: Path, text=DRAFT, refs=None, mats=None) -> Path:
    store = d / "ws.json"
    (d / "draft.txt").write_text(text, encoding="utf-8")
    run(store, "load", "--text", str(d / "draft.txt"),
        "--references", json.dumps(refs if refs is not None else
                                   [{"key": "doe2020", "title": "coating"}]),
        "--materials", json.dumps(mats if mats is not None else [{"id": "M1"}]))
    return store


def propose(store: Path, d: Path, edits) -> tuple[int, dict]:
    p = d / "edits.json"
    p.write_text(json.dumps(edits), encoding="utf-8")
    return run(store, "propose", "--edits", str(p))


def scenario(name, fn) -> dict:
    d = Path(tempfile.mkdtemp())
    try:
        return fn(d, name)
    finally:
        shutil.rmtree(d, ignore_errors=True)


# --- the four named properties ----------------------------------------------

def s_golden(d: Path, name: str) -> dict:
    """Accept one card, apply, diff, export; the rejected card is not applied.

    Also the FP guard for edit.span_not_found: a quote that IS in the draft forms a card.
    """
    store = setup(d)
    code, res = propose(store, d, [
        {"kind": "term", "quote": "markedly", "after": "three-fold", "basis": "doe2020"},
        {"kind": "wording", "quote": "We measured", "after": "We assayed", "basis": "M1"},
    ])
    if code or len(res.get("cards") or []) != 2:
        return {"name": name, "pass": False, "why": f"propose failed {res}"}
    ids = [c["id"] for c in res["cards"]]
    run(store, "accept", "--id", ids[0])
    run(store, "reject", "--id", ids[1], "--reason", "keeps the agent voice")
    code, ap = run(store, "apply")
    if code or not ap.get("ok"):
        return {"name": name, "pass": False, "why": f"apply failed {ap}"}
    code, df = run(store, "diff", "--from", "v0", "--to", ap["version"])
    code, ex = run(store, "export", "--out", str(d / "out"))
    final = (d / "out" / "final.md").read_text(encoding="utf-8")
    tracked = (d / "out" / "tracked_changes.md").read_text(encoding="utf-8")
    ok = ("three-fold" in final and "We measured" in final
          and len(df.get("changes") or []) == 1
          and "basis" in tracked and "before" in tracked)
    return {"name": name, "pass": ok,
            "why": f"changed={len(df.get('changes') or [])} tracked_ok={'basis' in tracked}"}


def s_no_basis(d: Path, name: str) -> dict:
    store = setup(d)
    code, res = propose(store, d, [{"kind": "wording", "quote": "markedly",
                                    "after": "three-fold"}])
    ok = code == 4 and res.get("refused")
    return {"name": name, "pass": ok, "why": f"exit={code} refused={bool(res.get('refused'))}"}


def s_basis_unresolved(d: Path, name: str) -> dict:
    store = setup(d)
    code, res = propose(store, d, [{"kind": "wording", "quote": "markedly",
                                    "after": "three-fold", "basis": "ghost2019"}])
    ok = code == 4 and any("does not resolve" in r["reason"] for r in res.get("refused", []))
    return {"name": name, "pass": ok, "why": json.dumps(res.get("refused"))[:90]}


def s_rewrite_refused(d: Path, name: str) -> dict:
    """A 'wording' edit that replaces a phrase with a paragraph is a rewrite."""
    store = setup(d)
    code, res = propose(store, d, [{
        "kind": "wording", "quote": "markedly",
        "after": "markedly in every condition tested and also in the control arm and in the "
                 "second material and across all temperatures considered",
        "basis": "doe2020"}])
    ok = code == 4 and any("rewrite" in r["reason"] for r in res.get("refused", []))
    return {"name": name, "pass": ok, "why": json.dumps(res.get("refused"))[:90]}


def s_skeleton_guard(d: Path, name: str) -> dict:
    """Dropping a citation from a wording edit would move the skeleton, so apply refuses.

    Also the FP guard for the declared-citation exemption: the wording layer never gets it.
    """
    store = setup(d)
    code, res = propose(store, d, [{"kind": "wording", "quote": "under the coating [doe2020]",
                                    "after": "under the coating", "basis": "M1"}])
    if code or not res.get("cards"):
        return {"name": name, "pass": False, "why": f"propose failed {res}"}
    run(store, "accept", "--id", res["cards"][0]["id"])
    code, ap = run(store, "apply")
    ok = code == 4 and "skeleton" in ap.get("reason", "")
    return {"name": name, "pass": ok, "why": json.dumps(ap)[:110]}


def s_restore(d: Path, name: str) -> dict:
    """Restore appends a new version instead of rewriting history."""
    store = setup(d)
    code, res = propose(store, d, [{"kind": "term", "quote": "markedly",
                                    "after": "three-fold", "basis": "doe2020"}])
    run(store, "accept", "--id", res["cards"][0]["id"])
    code, ap = run(store, "apply")
    v2 = ap["version"]
    code, rs = run(store, "restore", "--version", "v0")
    data = json.loads(store.read_text(encoding="utf-8"))
    ok = (rs.get("ok") and rs["restored_from"] == "v0"
          and len(data["versions"]) >= 3 and v2 in data["versions"])
    return {"name": name, "pass": ok, "why": f"restored={rs.get('restored_from')} "
                                            f"versions={len(data['versions'])}"}


def s_idempotent(d: Path, name: str) -> dict:
    store = setup(d)
    code, ap = run(store, "apply")
    ok = ap.get("ok") and ap.get("changed") == 0 and ap.get("version") == "v0"
    return {"name": name, "pass": ok, "why": json.dumps(ap)[:100]}


def s_stale_card(d: Path, name: str) -> dict:
    """A card proposed against v0 cannot be accepted once the document has moved."""
    store = setup(d)
    code, res = propose(store, d, [{"kind": "term", "quote": "markedly",
                                    "after": "three-fold", "basis": "doe2020"},
                                   {"kind": "wording", "quote": "3 mM",
                                    "after": "3.0 mM", "basis": "M1"}])
    ids = [c["id"] for c in res["cards"]]
    run(store, "accept", "--id", ids[0])
    run(store, "apply")
    code, dec = run(store, "accept", "--id", ids[1])
    ok = code == 4 and not dec.get("ok")
    return {"name": name, "pass": ok, "why": json.dumps(dec)[:110]}


# --- 引用协作: a declared citation edit may land (its layer, declared) --------

def s_citation_edit_applies(d: Path, name: str) -> dict:
    """A citation-kind edit that re-points a reference must apply — that is the layer it
    declared (引用协作); the wording layer never gets this exemption (s_skeleton_guard)."""
    store = setup(d, refs=[{"key": "doe2020"}, {"key": "roe2021", "title": "coating"}])
    code, res = propose(store, d, [{"kind": "citation", "quote": "[doe2020]",
                                    "after": "[roe2021]", "basis": "roe2021"}])
    if code or not res.get("cards"):
        return {"name": name, "pass": False, "why": f"propose failed {res}"}
    run(store, "accept", "--id", res["cards"][0]["id"])
    code, ap = run(store, "apply")
    if code or not ap.get("ok"):
        return {"name": name, "pass": False, "why": f"apply refused {ap}"}
    final = "\n".join(json.loads(store.read_text(encoding="utf-8"))
                      ["versions"][ap["version"]]["paragraphs"])
    ok = "[roe2021]" in final and "[doe2020]" not in final
    return {"name": name, "pass": ok, "why": f"applied={ap.get('version')} "
                                            f"repointed={'[roe2021]' in final}"}


def s_span_not_found(d: Path, name: str) -> dict:
    """指令与稿件内容冲突: the instruction names text the manuscript does not have."""
    store = setup(d)
    code, res = propose(store, d, [{"kind": "wording", "quote": "text absent from the draft",
                                    "after": "something", "basis": "M1"}])
    ok = code == 4 and any("edit.span_not_found" in r["reason"]
                           for r in res.get("refused", []))
    return {"name": name, "pass": ok, "why": json.dumps(res.get("refused"))[:90]}


# --- 异常处理: each failure is its own diagnosis -------------------------------

def s_citation_library_missing(d: Path, name: str) -> dict:
    """引用库缺失: a citation edit with no references loaded is a library diagnosis."""
    store = setup(d, refs=[])
    code, res = propose(store, d, [{"kind": "citation", "quote": "[doe2020]",
                                    "after": "[roe2021]", "basis": "roe2021"}])
    ok = code == 4 and any("edit.library_missing" in r["reason"]
                           for r in res.get("refused", []))
    return {"name": name, "pass": ok, "why": json.dumps(res.get("refused"))[:90]}


def s_citation_library_resolves(d: Path, name: str) -> dict:
    """FP guard: with the reference loaded, the same citation edit forms a card."""
    store = setup(d, refs=[{"key": "roe2021"}])
    code, res = propose(store, d, [{"kind": "citation", "quote": "[doe2020]",
                                    "after": "[roe2021]", "basis": "roe2021"}])
    ok = code == 0 and bool(res.get("cards"))
    return {"name": name, "pass": ok, "why": f"cards={len(res.get('cards') or [])}"}


def s_empty_draft_refused(d: Path, name: str) -> dict:
    """文档损坏: an empty draft is refused as its own diagnosis, not loaded silently.

    FP guard first: a normal draft loads fine against the same CLI.
    """
    (d / "empty.txt").write_text("", encoding="utf-8")
    (d / "draft.txt").write_text(DRAFT, encoding="utf-8")
    code_fp, res_fp = run(d / "a.json", "load", "--text", str(d / "draft.txt"))
    code, res = run(d / "b.json", "load", "--text", str(d / "empty.txt"))
    ok = (code_fp == 0 and res_fp.get("ok")
          and code == 4 and "load.empty_draft" in res.get("reason", ""))
    return {"name": name, "pass": ok, "why": f"fp={code_fp} refused={res.get('reason', '')[:60]}"}


def s_unreadable_refused(d: Path, name: str) -> dict:
    """文档损坏或加密: a draft that is not UTF-8 text is refused, never a traceback.

    FP guard first: a normal draft loads fine.
    """
    (d / "draft.txt").write_text(DRAFT, encoding="utf-8")
    code_fp, res_fp = run(d / "a.json", "load", "--text", str(d / "draft.txt"))
    (d / "bad.txt").write_bytes(b"\xff\xfe\xad\xde\xff\x00bad")
    code, res = run(d / "b.json", "load", "--text", str(d / "bad.txt"))
    ok = (code_fp == 0 and res_fp.get("ok")
          and code == 4 and "load.unreadable" in res.get("reason", ""))
    return {"name": name, "pass": ok, "why": f"fp={code_fp} refused={res.get('reason', '')[:60]}"}


def s_export_failure_clean(d: Path, name: str) -> dict:
    """导出失败: an unwritable path is a clean refusal, not a crash.

    FP guard first: the same export to a writable path succeeds.
    """
    store = setup(d)
    code_fp, res_fp = run(store, "export", "--out", str(d / "out"))
    (d / "blocker").write_text("a file, not a directory", encoding="utf-8")
    code, res = run(store, "export", "--out", str(d / "blocker" / "out"))
    ok = (code_fp == 0 and res_fp.get("ok")
          and code == 4 and "export.failure" in res.get("reason", ""))
    return {"name": name, "pass": ok, "why": f"fp={code_fp} refused={res.get('reason', '')[:60]}"}


# --- 事实与来源映射: no facts beyond the material -------------------------------

BS_REFS = [{"key": "doe2020", "content": "Uptake rose three-fold under the coating."}]
BS_MATS = [{"id": "M1", "content": "We measured 3 mM samples."}, {"id": "M2"}]


def s_basis_support_refused(d: Path, name: str) -> dict:
    """不新增材料外事实: a term replacement the declared basis content does not carry."""
    store = setup(d, refs=BS_REFS, mats=BS_MATS)
    code, res = propose(store, d, [{"kind": "term", "quote": "markedly",
                                    "after": "five-fold", "basis": "doe2020"}])
    ok = code == 4 and any("edit.basis_support" in r["reason"]
                           for r in res.get("refused", []))
    return {"name": name, "pass": ok, "why": json.dumps(res.get("refused"))[:90]}


def s_basis_support_declared_only(d: Path, name: str) -> dict:
    """FP guard: a replacement the content carries passes, and a basis that declares no
    content is never checked — absent fields are not faults."""
    store = setup(d, refs=BS_REFS, mats=BS_MATS)
    code, res = propose(store, d, [
        {"kind": "term", "quote": "markedly", "after": "three-fold", "basis": "doe2020"},
        {"kind": "term", "quote": "We measured", "after": "We assayed", "basis": "M2"}])
    ok = code == 0 and len(res.get("cards") or []) == 2
    return {"name": name, "pass": ok, "why": f"cards={len(res.get('cards') or [])} "
                                            f"refused={len(res.get('refused') or [])}"}


# --- 格式不塌: tables stay consistent ----------------------------------------

def s_table_column_guard(d: Path, name: str) -> dict:
    """Adding a column to a table row moves the skeleton (表格), so apply refuses."""
    store = setup(d, text=DRAFT_TABLE)
    code, res = propose(store, d, [{"kind": "format", "quote": "| sample | uptake |",
                                    "after": "| sample | uptake | notes |", "basis": "M1"}])
    if code or not res.get("cards"):
        return {"name": name, "pass": False, "why": f"propose failed {res}"}
    run(store, "accept", "--id", res["cards"][0]["id"])
    code, ap = run(store, "apply")
    ok = (code == 4 and "skeleton" in ap.get("reason", "")
          and "table_columns" in (ap.get("changed") or []))
    return {"name": name, "pass": ok, "why": json.dumps(ap)[:110]}


def s_table_cell_edit_clean(d: Path, name: str) -> dict:
    """FP guard: editing text inside a table cell keeps the column profile and applies."""
    store = setup(d, text=DRAFT_TABLE)
    code, res = propose(store, d, [{"kind": "wording", "quote": "| uptake |",
                                    "after": "| rate |", "basis": "M1"}])
    if code or not res.get("cards"):
        return {"name": name, "pass": False, "why": f"propose failed {res}"}
    run(store, "accept", "--id", res["cards"][0]["id"])
    code, ap = run(store, "apply")
    final = "\n".join(json.loads(store.read_text(encoding="utf-8"))
                      ["versions"].get(ap.get("version"), {}).get("paragraphs", []))
    ok = ap.get("ok") and "| sample | rate |" in final
    return {"name": name, "pass": ok, "why": f"applied={ap.get('version')} "
                                            f"cell={'| sample | rate |' in final}"}


# --- 改得准: 增删改 — declared deletions land, structure-level ones do not ------

def s_deletion_applies(d: Path, name: str) -> dict:
    """增删改: an explicit empty replacement deletes the span and applies cleanly."""
    store = setup(d)
    code, res = propose(store, d, [{"kind": "term", "quote": "markedly", "after": "",
                                    "basis": "doe2020"}])
    if code or not res.get("cards"):
        return {"name": name, "pass": False, "why": f"propose refused {res}"}
    run(store, "accept", "--id", res["cards"][0]["id"])
    code, ap = run(store, "apply")
    final = "\n".join(json.loads(store.read_text(encoding="utf-8"))
                      ["versions"].get(ap.get("version"), {}).get("paragraphs", []))
    ok = ap.get("ok") and "markedly" not in final and "under the coating" in final
    return {"name": name, "pass": ok, "why": f"applied={ap.get('version')} "
                                            f"gone={'markedly' not in final}"}


def s_whole_paragraph_delete_refused(d: Path, name: str) -> dict:
    """FP guard for deletions: a deletion that swallows a whole paragraph is a structure
    change, and an edit with no after key at all is still an unfinished edit."""
    store = setup(d)
    code, res = propose(store, d, [{"kind": "wording", "quote": "We measured 3 mM samples.",
                                    "after": "", "basis": "M1"}])
    gone = any("edit.delete_span" in r["reason"] and "whole paragraph" in r["reason"]
               for r in res.get("refused", []))
    code2, res2 = propose(store, d, [{"kind": "wording", "quote": "3 mM", "basis": "M1"}])
    unfinished = any("no replacement text" in r["reason"]
                     for r in res2.get("refused", []))
    ok = code == 4 and gone and code2 == 4 and unfinished
    return {"name": name, "pass": ok, "why": f"whole={gone} unfinished={unfinished}"}


# --- 结果完整性: workorder coverage, never silently dropped --------------------

WO = [{"id": "W1", "task": "fix the term"}, {"id": "W2", "task": "reword the method"},
      {"id": "W3", "task": "check the caption"}]


def s_coverage_gap_named(d: Path, name: str) -> dict:
    """A workorder point no card claims is named as a gap (材料缺口), not dropped."""
    store = setup(d)
    (d / "workorder.json").write_text(json.dumps(WO), encoding="utf-8")
    code, pl = run(store, "plan", "--workorder", str(d / "workorder.json"))
    code, res = propose(store, d, [
        {"kind": "term", "quote": "markedly", "after": "three-fold", "basis": "doe2020",
         "covers": "W1"},
        {"kind": "wording", "quote": "We measured", "after": "We assayed", "basis": "M1",
         "covers": ["W2"]}])
    code, cov = run(store, "coverage")
    ok = (pl.get("ok") and cov.get("planned")
          and cov.get("unaddressed") == ["W3"]
          and cov["points"][0]["cards"] and not cov["points"][2]["cards"])
    return {"name": name, "pass": ok, "why": f"unaddressed={cov.get('unaddressed')}"}


def s_coverage_full_clean(d: Path, name: str) -> dict:
    """FP guard: every point claimed leaves no gap, and a workspace with no workorder is
    never punished — coverage simply reports that nothing is checked."""
    store = setup(d)
    (d / "workorder.json").write_text(json.dumps(WO[:2]), encoding="utf-8")
    run(store, "plan", "--workorder", str(d / "workorder.json"))
    propose(store, d, [
        {"kind": "term", "quote": "markedly", "after": "three-fold", "basis": "doe2020",
         "covers": "W1"},
        {"kind": "wording", "quote": "We measured", "after": "We assayed", "basis": "M1",
         "covers": "W2"}])
    code, cov = run(store, "coverage")
    code2, bare = run(d / "b.json", "coverage")
    ok = (cov.get("planned") and cov.get("unaddressed") == []
          and bare.get("ok") and bare.get("planned") is False
          and bare.get("unaddressed") == [])
    return {"name": name, "pass": ok, "why": f"full={cov.get('unaddressed')} "
                                            f"bare-planned={bare.get('planned')}"}


# --- 版本与边界: declared human-confirmation flags -----------------------------

def s_confirm_flagged(d: Path, name: str) -> dict:
    """人工确认项: an edit declaring confirm:true is flagged in the export and the result."""
    store = setup(d)
    code, res = propose(store, d, [{"kind": "wording", "quote": "We measured",
                                    "after": "We assayed", "basis": "M1",
                                    "confirm": True}])
    if code or not res.get("cards"):
        return {"name": name, "pass": False, "why": f"propose failed {res}"}
    run(store, "accept", "--id", res["cards"][0]["id"])
    run(store, "apply")
    code, ex = run(store, "export", "--out", str(d / "out"))
    tracked = (d / "out" / "tracked_changes.md").read_text(encoding="utf-8")
    kinds = [u["kind"] for u in ex.get("uncertainty") or []]
    ok = ("needs human confirmation" in tracked and "card.needs_confirm" in kinds)
    return {"name": name, "pass": ok, "why": f"kinds={kinds}"}


def s_no_confirm_flag_clean(d: Path, name: str) -> dict:
    """FP guard: edits that do not declare confirm are never flagged, and a fully decided
    workspace reports no uncertainty at all."""
    store = setup(d)
    code, res = propose(store, d, [{"kind": "term", "quote": "markedly",
                                    "after": "three-fold", "basis": "doe2020"}])
    card = (res.get("cards") or [{}])[0]
    run(store, "accept", "--id", card.get("id"))
    run(store, "apply")
    code, ex = run(store, "export", "--out", str(d / "out"))
    ok = ("needs_confirm" not in json.dumps(card)
          and ex.get("uncertainty") == [] and ex.get("status") == "complete")
    return {"name": name, "pass": ok, "why": f"uncertainty={ex.get('uncertainty')} "
                                            f"status={ex.get('status')}"}


# --- 结构化交付: result carries the output contract ----------------------------

def s_result_contract_fields(d: Path, name: str) -> dict:
    """The structured deliverable: case_id echoed, honest status, change records, refused
    proposals with their reasons — and it lands on disk."""
    store = setup(d)
    run(store, "load", "--text", str(d / "draft.txt"),
        "--case-id", "CASE-77",
        "--references", json.dumps([{"key": "doe2020"}]),
        "--materials", json.dumps([{"id": "M1"}]))
    code, res = propose(store, d, [
        {"kind": "term", "quote": "markedly", "after": "three-fold", "basis": "doe2020"},
        {"kind": "wording", "quote": "no such span here", "after": "x", "basis": "M1"}])
    run(store, "accept", "--id", res["cards"][0]["id"])
    run(store, "apply")
    code, rec = run(store, "result", "--out", str(d / "res.json"))
    saved = json.loads((d / "res.json").read_text(encoding="utf-8"))
    ok = (rec.get("ok") and saved["case_id"] == "CASE-77"
          and saved["status"] == "complete"
          and len(saved["refused_proposals"]) == 1
          and "edit.span_not_found" in saved["refused_proposals"][0]["reason"]
          and len(saved["cards"]) == 1 and saved["applied"]
          and bool(saved.get("final_sha256")))
    return {"name": name, "pass": ok,
            "why": f"case_id={saved['case_id']} status={saved['status']} "
                   f"refused={len(saved['refused_proposals'])}"}


def s_result_undeclared_case_id_clean(d: Path, name: str) -> dict:
    """FP guard: an undeclared case_id is echoed as null — never punished, never invented."""
    store = setup(d)
    code, rec = run(store, "result", "--out", str(d / "res.json"))
    ok = (rec.get("ok") and rec.get("case_id") is None
          and rec.get("status") == "complete")
    return {"name": name, "pass": ok, "why": f"case_id={rec.get('case_id')} "
                                            f"status={rec.get('status')}"}


def s_result_partial_status(d: Path, name: str) -> dict:
    """A pending card makes the status honest: partial, with its limits named."""
    store = setup(d)
    propose(store, d, [{"kind": "term", "quote": "markedly", "after": "three-fold",
                        "basis": "doe2020"}])
    code, rec = run(store, "result", "--out", str(d / "res.json"))
    ok = (rec.get("status") == "partial" and bool(rec.get("limits"))
          and any(u["kind"] == "undecided_cards" for u in rec.get("uncertainty") or []))
    return {"name": name, "pass": ok, "why": f"status={rec.get('status')} "
                                            f"limits={rec.get('limits')}"}


SCEN = [s_golden, s_no_basis, s_basis_unresolved, s_rewrite_refused, s_skeleton_guard,
        s_restore, s_idempotent, s_stale_card,
        s_citation_edit_applies, s_span_not_found,
        s_citation_library_missing, s_citation_library_resolves,
        s_empty_draft_refused, s_unreadable_refused, s_export_failure_clean,
        s_basis_support_refused, s_basis_support_declared_only,
        s_table_column_guard, s_table_cell_edit_clean,
        s_deletion_applies, s_whole_paragraph_delete_refused,
        s_coverage_gap_named, s_coverage_full_clean,
        s_confirm_flagged, s_no_confirm_flag_clean,
        s_result_contract_fields, s_result_undeclared_case_id_clean, s_result_partial_status]


def main() -> int:
    rows = [scenario(fn.__name__.replace("s_", ""), fn) for fn in SCEN]
    for r in rows:
        print(f"{'PASS' if r['pass'] else 'FAIL'}  {r['name']:<34} {r['why']}")
    passed = sum(1 for r in rows if r["pass"])
    report = {"schema_version": "writing-client-bench/v2", "scenarios": rows,
              "totals": {"passed": passed, "of": len(rows)},
              "note": ("Behavioural: every scenario drives the CLI. Half assert a refusal, and "
                       "every new rule ships with a defect scenario and its false-positive "
                       "guard (correct input must find nothing): an unsupported term "
                       "replacement, a moved table column, a whole-paragraph deletion, an "
                       "empty reference library, an empty or unreadable draft, an unwritable "
                       "export, an undeclared confirm flag, an undeclared case_id — each "
                       "paired with the clean guard for the same rule.")}
    (HERE / "report_writer.json").write_text(json.dumps(report, ensure_ascii=False, indent=2),
                                             encoding="utf-8")
    print(f"\n{passed}/{len(rows)} pass")
    return 0 if passed == len(rows) else 1


if __name__ == "__main__":
    raise SystemExit(main())
