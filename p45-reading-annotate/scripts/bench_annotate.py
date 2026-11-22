"""Benchmark for the reading-annotation skill.

Each scenario asserts one of the four properties the task judges — anchors come
back to the exact page/position, annotation types and colours survive, version
siblings stay separate, structured notes retrieve honestly — plus the FP guards.

    python bench_annotate.py
"""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import reader  # noqa: E402
import annotate  # noqa: E402

DOC = ("1 Introduction\n"
       "Porous coatings raise the uptake rate three-fold.\n"
       "\n"
       "2 Methods\n"
       "We measured uptake at 25 C with six replicates per arm.\n"
       "\n"
       "3 Discussion\n"
       "Only one coating thickness was tested, so the result does not generalise.\n")


def _ws(tmp: Path, name: str):
    ws = reader.Workspace(tmp / f"{name}.json")
    ws.add_document("paper", "\n".join(l for l in DOC.splitlines() if l.strip()), [2, 4])
    ann = annotate.Annotator(ws)
    return ws, ann


def scen_anchor_ok(tmp, name):
    ws, ann = _ws(tmp, name)
    res = ann.ingest("paper", [
        {"quote": "three-fold", "page": 1, "type": "highlight", "color": "yellow",
         "note": "结果：涂层使吸收速率提高三倍"},
        {"quote": "six replicates", "page": 2, "type": "underline", "note": "方法：每组六个重复"}])
    return res["ok"] and len(res["accepted"]) == 2 and not res["refused"]


def scen_anchor_mismatch_refused(tmp, name):
    ws, ann = _ws(tmp, name)
    res = ann.ingest("paper", [
        {"quote": "this sentence does not exist", "page": 1, "type": "highlight"}])
    return len(res["refused"]) == 1 and not res["accepted"] \
        and "anchor mismatch" in res["refused"][0]["reason"]


def scen_types_preserved(tmp, name):
    ws, ann = _ws(tmp, name)
    ann.ingest("paper", [
        {"quote": "three-fold", "page": 1, "type": "highlight", "color": "red"},
        {"quote": "six replicates", "page": 2, "type": "margin"}])
    notes = {n["quote"]: n for n in ann.structured_notes()}
    return notes["three-fold"]["type"] == "highlight" and notes["three-fold"]["color"] == "red" \
        and notes["six replicates"]["type"] == "margin"


def scen_note_kinds(tmp, name):
    ws, ann = _ws(tmp, name)
    ann.ingest("paper", [
        {"quote": "three-fold", "page": 1, "type": "highlight", "note": "结果：三倍提升"},
        {"quote": "six replicates", "page": 2, "type": "underline", "note": "方法步骤：六个重复"},
        {"quote": "does not generalise", "page": 3, "type": "margin",
         "note": "局限：单一厚度"}])
    kinds = {n["quote"]: n["note_kind"] for n in ann.structured_notes()}
    return kinds["three-fold"] == "result" and kinds["six replicates"] == "method" \
        and kinds["does not generalise"] in ("context", "reusable")


def scen_versions_separate(tmp, name):
    """Two files carrying the same quote stay separate records with different hashes."""
    ws, ann = _ws(tmp, name)
    v2_text = DOC.replace("six replicates", "eight replicates")
    ws.add_document("paper-v2", "\n".join(l for l in v2_text.splitlines() if l.strip()), [])
    ann.ingest("paper", [{"quote": "three-fold", "page": 1, "type": "highlight"}])
    ann.ingest("paper-v2", [{"quote": "three-fold", "page": 1, "type": "highlight"}])
    notes = ann.structured_notes()
    docs = {n["doc_id"] for n in notes}
    hashes = {n["source_sha"] for n in notes}
    return len(notes) == 2 and docs == {"paper", "paper-v2"} and len(hashes) == 2


def scen_linking_same_kind(tmp, name):
    """Notes link only within the same kind and >=2 shared terms — one shared word is not a relation."""
    ws, ann = _ws(tmp, name)
    ann.ingest("paper", [
        {"quote": "three-fold", "page": 1, "type": "highlight", "note": "结果：uptake 提高三倍"},
        {"quote": "six replicates", "page": 2, "type": "underline",
         "note": "结果：uptake 六个重复测得"},
        {"quote": "only one thickness", "page": 3, "type": "margin", "note": "方法：单一厚度"}])
    notes = ann.structured_notes()
    links = ann.links(notes, min_shared=2)
    by_id = {n["annotation_id"]: n["note_kind"] for n in notes}
    return all(by_id[l["between"][0]] == by_id[l["between"][1]] for l in links) \
        and all(l["kind"] == "result" for l in links)


def scen_retrieve(tmp, name):
    ws, ann = _ws(tmp, name)
    ann.ingest("paper", [
        {"quote": "three-fold", "page": 1, "type": "highlight", "note": "结果：uptake 提高三倍"},
        {"quote": "six replicates", "page": 2, "type": "underline", "note": "方法：六个重复"}])
    hits = ann.retrieve("uptake 提高了多少倍", ann.structured_notes())
    return hits and hits[0]["note_kind"] == "result"


def scen_retrieve_miss_honest(tmp, name):
    """A question nothing matches returns an empty hit list — no invented results."""
    ws, ann = _ws(tmp, name)
    ann.ingest("paper", [{"quote": "three-fold", "page": 1, "type": "highlight"}])
    hits = ann.retrieve("量子色动力学修正", ann.structured_notes())
    return hits == []


def scen_export(tmp, name):
    ws, ann = _ws(tmp, name)
    ann.ingest("paper", [
        {"quote": "three-fold", "page": 1, "type": "highlight", "note": "结果：三倍"},
        {"quote": "six replicates", "page": 2, "type": "underline", "note": "方法：六重复"}])
    out = tmp / "out"
    res = ann.export(out)
    ok = res["ok"] and (out / "notes.md").exists() and (out / "index.json").exists()
    idx = json.loads((out / "index.json").read_text(encoding="utf-8"))
    return ok and len(idx["notes"]) == 2 and len(idx["links"]) >= 0


def scen_positive_link(tmp, name):
    """Two same-kind notes sharing >=2 terms create a real link with shared_terms."""
    ws, ann = _ws(tmp, name)
    ann.ingest("paper", [
        {"quote": "three-fold", "page": 1, "type": "highlight", "note": "结果：uptake 提高三倍"},
        {"quote": "six replicates", "page": 2, "type": "underline", "note": "结果：uptake 与六次重复一致"}])
    notes = ann.structured_notes()
    links = ann.links(notes, min_shared=2)
    return len(links) >= 1 and links[0]["kind"] == "result" and len(links[0]["shared_terms"]) >= 2


def scen_single_term_no_link(tmp, name):
    """Same kind (result) sharing exactly ONE term (结果): no link is created."""
    ws, ann = _ws(tmp, name)
    ann.ingest("paper", [
        {"quote": "three-fold", "page": 1, "type": "highlight", "note": "结果：uptake 明显"},
        {"quote": "six replicates", "page": 2, "type": "underline", "note": "结果：重复良好"}])
    notes = ann.structured_notes()
    kinds = {n["note_kind"] for n in notes}
    links = ann.links(notes, min_shared=2)
    return kinds == {"result"} and links == []


def scen_ambiguous_refused(tmp, name):
    """A quote occurring twice with no declared page is refused, naming the paragraphs."""
    ws, ann = _ws(tmp, name)
    res = ann.ingest("paper", [{"quote": "uptake", "type": "underline"}])
    return len(res["refused"]) == 1 and "ambiguous anchor" in res["refused"][0]["reason"]


def scen_page_mismatch_refused(tmp, name):
    """A declared page that contradicts the document is refused at ingest time."""
    ws, ann = _ws(tmp, name)
    res = ann.ingest("paper", [{"quote": "three-fold", "page": 2, "type": "highlight"}])
    return len(res["refused"]) == 1 and "not on the declared" in res["refused"][0]["reason"]


def scen_reingest_idempotent(tmp, name):
    """Re-ingesting the same file does not inflate the anchor list."""
    ws, ann = _ws(tmp, name)
    recs = [{"quote": "three-fold", "page": 1, "type": "highlight"}]
    ann.ingest("paper", recs)
    before = len(ws.data["anchors"])
    ann.ingest("paper", recs)
    after = len(ws.data["anchors"])
    return before == after == 1


def scen_pageless_verifies(tmp, name):
    """A page-less ingest is accepted with a resolved page and verify passes."""
    ws, ann = _ws(tmp, name)
    res = ann.ingest("paper", [{"quote": "three-fold", "type": "highlight"}])
    if not res["accepted"]:
        return False
    res_v = reader.verify_all(ws)
    return res_v["ok"] and res_v["anchors"] == 1


def scen_verify_anchors(tmp, name):
    ws, ann = _ws(tmp, name)
    ann.ingest("paper", [{"quote": "three-fold", "page": 1, "type": "highlight"}])
    res = reader.verify_all(ws)
    return res["ok"] and res["anchors"] == 1


def scen_ocr_drift_suggested(tmp, name):
    """A drifted quote is refused WITH its closest real paragraph — the reader can
    re-extract instead of guessing."""
    ws, ann = _ws(tmp, name)
    res = ann.ingest("paper", [{"quote": "three-f0ld", "page": 1, "type": "highlight"}])
    if len(res["refused"]) != 1 or res["accepted"]:
        return False
    r = res["refused"][0]
    return (r.get("rule") == "ann.anchor_ocr_drift"
            and isinstance(r.get("suggestion"), dict)
            and r["suggestion"]["paragraph"] >= 0
            and r["suggestion"]["similarity"] >= 0.6)


def scen_ocr_drift_no_suggestion(tmp, name):
    """FP guard: a quote nothing resembles gets a plain mismatch, no bogus hint."""
    ws, ann = _ws(tmp, name)
    res = ann.ingest("paper", [{"quote": "zzz qqq www vvv", "type": "highlight"}])
    r = res["refused"][0]
    return len(res["refused"]) == 1 and r.get("rule") == "ann.anchor_mismatch" \
        and "suggestion" not in r


def scen_declared_kind_unknown(tmp, name):
    """An invalid declared kind is refused by name, never silently re-typed."""
    ws, ann = _ws(tmp, name)
    res = ann.ingest("paper", [{"quote": "three-fold", "page": 1, "type": "highlight",
                                "kind": "foo"}])
    return len(res["refused"]) == 1 \
        and res["refused"][0].get("rule") == "ann.declared_kind_unknown" \
        and not res["accepted"]


def scen_type_unknown_preserved(tmp, name):
    """An extractor type outside the five known values is kept verbatim — 类型不丢."""
    ws, ann = _ws(tmp, name)
    ann.ingest("paper", [{"quote": "three-fold", "page": 1, "type": "Squiggle"}])
    notes = {n["quote"]: n for n in ann.structured_notes()}
    return notes["three-fold"]["type"] == "squiggle"


def scen_doubt_kind(tmp, name):
    """待验证/存疑 notes cue the doubt kind — 待验证疑点 is a first-class kind."""
    ws, ann = _ws(tmp, name)
    ann.ingest("paper", [{"quote": "three-fold", "page": 1, "type": "margin",
                          "note": "存疑：单一厚度能否外推待验证"}])
    kinds = [n["note_kind"] for n in ann.structured_notes()]
    return kinds == ["doubt"]


def scen_duplicate_document(tmp, name):
    """The same file loaded twice under two ids is reported, not merged."""
    ws, ann = _ws(tmp, name)
    same_text = "\n".join(ws.data["documents"]["paper"]["paragraphs"])
    ws.add_document("paper-again", same_text, [])
    dups = ann.duplicate_doc_ids("paper-again")
    return dups == ["paper"] and ann.duplicate_doc_ids("paper") == ["paper-again"]


def scen_version_siblings_linked(tmp, name):
    """The same quote in two source files stays split (own hashes) but is linked
    explicitly as a version-sibling with its evidence."""
    ws, ann = _ws(tmp, name)
    v2 = DOC.replace("six replicates", "eight replicates")
    ws.add_document("paper-v2", "\n".join(l for l in v2.splitlines() if l.strip()), [])
    ann.ingest("paper", [{"quote": "three-fold", "page": 1, "type": "highlight"}])
    ann.ingest("paper-v2", [{"quote": "three-fold", "page": 1, "type": "highlight"}])
    notes = ann.structured_notes()
    sib = ann.version_siblings(notes)
    hashes = {n["source_sha"] for n in notes}
    return len(notes) == 2 and len(hashes) == 2 and len(sib) == 1 \
        and sib[0]["kind"] == "version-sibling" and len(sib[0]["docs"]) == 2


def scen_tag_preserved_and_filtered(tmp, name):
    """Tags survive ingest verbatim and narrow retrieval."""
    ws, ann = _ws(tmp, name)
    ann.ingest("paper", [
        {"quote": "three-fold", "page": 1, "type": "highlight", "tags": ["温度", "uptake"],
         "note": "结果：三倍"},
        {"quote": "six replicates", "page": 2, "type": "underline", "tags": ["重复"],
         "note": "方法：六个重复"}])
    notes = {n["quote"]: n for n in ann.structured_notes()}
    if notes["three-fold"]["tags"] != ["温度", "uptake"]:
        return False
    hits = ann.retrieve("三倍", ann.structured_notes(), tag="温度")
    return len(hits) == 1 and hits[0]["annotation_id"] == notes["three-fold"]["annotation_id"]


def scen_offset_disambiguation(tmp, name):
    """A quote repeated inside ONE paragraph is disambiguated by a declared
    character offset instead of being refused."""
    ws = reader.Workspace(tmp / f"{name}.json")
    ws.add_document("dup", "The result replicated the result of the pilot.", [])
    ann = annotate.Annotator(ws)
    res = ann.ingest("dup", [{"quote": "result", "start": 26, "type": "underline"}])
    if not res["accepted"]:
        return False
    rec = res["accepted"][0]
    amb = ann.ingest("dup", [{"quote": "result", "type": "underline"}])
    return rec["start"] == 26 and len(amb["refused"]) == 1 \
        and amb["refused"][0].get("rule") == "ann.anchor_ambiguous"


def scen_retrieve_filters(tmp, name):
    """kind and doc-id filters narrow retrieval; a filter with no match stays an
    honest empty list."""
    ws, ann = _ws(tmp, name)
    v2 = DOC.replace("six replicates", "eight replicates")
    ws.add_document("paper-v2", "\n".join(l for l in v2.splitlines() if l.strip()), [])
    ann.ingest("paper", [{"quote": "three-fold", "page": 1, "type": "highlight",
                          "note": "结果：三倍"}])
    ann.ingest("paper-v2", [{"quote": "eight replicates", "page": 1, "type": "underline",
                             "note": "方法：八个重复"}])
    notes = ann.structured_notes()
    by_kind = ann.retrieve("重复", notes, kind="method")
    by_doc = ann.retrieve("重复", notes, doc_id="paper-v2")
    empty = ann.retrieve("重复", notes, kind="reusable")
    return len(by_kind) == 1 and by_kind[0]["note_kind"] == "method" \
        and len(by_doc) == 1 and by_doc[0]["anchor"]["doc_id"] == "paper-v2" \
        and empty == []


def _cli(tmp, *args):
    import subprocess
    return subprocess.run([sys.executable, "-X", "utf8",
                           str(Path(__file__).resolve().parent / "annotate_cli.py")]
                          + list(args), capture_output=True, text=True, timeout=120)


def scen_result_contract_passthrough(tmp, name):
    """The result command echoes case_id and output_contract fields into
    result.json and exits 0 when done."""
    store = tmp / f"{name}.json"
    _cli(tmp, "--store", str(store), "load", "--doc-id", "paper",
         "--doc-file", str(_docfile(tmp)))
    (tmp / "ann.json").write_text(json.dumps(
        [{"quote": "three-fold", "page": 1, "type": "highlight",
          "note": "结果：三倍"}], ensure_ascii=False), encoding="utf-8")
    _cli(tmp, "--store", str(store), "ingest", "--doc-id", "paper",
         "--annotations", str(tmp / "ann.json"))
    (tmp / "case.json").write_text(json.dumps({
        "case_id": "case-probe-9",
        "output_contract": {"deliverable": "structured annotation notes",
                            "knowledge_links": 0}}), encoding="utf-8")
    p = _cli(tmp, "--store", str(store), "result", "--out", str(tmp / "out"),
             "--case", str(tmp / "case.json"))
    if p.returncode != 0 or "Traceback" in p.stderr:
        return False
    res = json.loads((tmp / "out" / "result.json").read_text(encoding="utf-8"))
    return (res.get("case_id") == "case-probe-9"
            and res.get("deliverable") == "structured annotation notes"
            and res.get("knowledge_links") == 0
            and res.get("status") == "done"
            and len(res.get("notes", [])) == 1
            and res.get("verify", {}).get("ok") is True
            and "failure_recovery" in res and "uncertainty" in res)


def scen_result_failed_honest(tmp, name):
    """An empty store reports status failed with the refusal surfaced — 未完成
    never masquerades as 完成."""
    store = tmp / f"{name}.json"
    _cli(tmp, "--store", str(store), "load", "--doc-id", "paper",
         "--doc-file", str(_docfile(tmp)))
    (tmp / "badann.json").write_text(json.dumps(
        [{"quote": "not in the document", "type": "highlight"}], ensure_ascii=False),
        encoding="utf-8")
    _cli(tmp, "--store", str(store), "ingest", "--doc-id", "paper",
         "--annotations", str(tmp / "badann.json"))
    p = _cli(tmp, "--store", str(store), "result", "--out", str(tmp / "out2"))
    if p.returncode != 4 or "Traceback" in p.stderr:
        return False
    res = json.loads((tmp / "out2" / "result.json").read_text(encoding="utf-8"))
    return res.get("status") == "failed" \
        and res.get("failure_recovery") \
        and res["failure_recovery"][0]["rule"] == "ann.anchor_mismatch" \
        and not res.get("notes")


def scen_store_corrupt_refused(tmp, name):
    """A corrupt store file is an exit-5 refusal with no traceback."""
    store = tmp / f"{name}.json"
    store.write_text("{corrupt json", encoding="utf-8")
    p = _cli(tmp, "--store", str(store), "verify")
    return p.returncode == 5 and "Traceback" not in p.stderr \
        and "ann.store_unreadable" in p.stdout


def _docfile(tmp):
    f = tmp / "doc.txt"
    if not f.exists():
        f.write_text("\f".join([
            "1 Introduction\nPorous coatings raise the uptake rate three-fold.",
            "2 Methods\nWe measured uptake at 25 C with six replicates per arm.",
            "3 Discussion\nOnly one coating thickness was tested.",
        ]), encoding="utf-8")
    return f


SCENARIOS = [
    ("anchor_ok", scen_anchor_ok),
    ("anchor_mismatch_refused", scen_anchor_mismatch_refused),
    ("types_preserved", scen_types_preserved),
    ("note_kinds", scen_note_kinds),
    ("versions_separate", scen_versions_separate),
    ("linking_same_kind", scen_linking_same_kind),
    ("retrieve", scen_retrieve),
    ("retrieve_miss_honest", scen_retrieve_miss_honest),
    ("export", scen_export),
    ("positive_link", scen_positive_link),
    ("single_term_no_link", scen_single_term_no_link),
    ("ambiguous_refused", scen_ambiguous_refused),
    ("page_mismatch_refused", scen_page_mismatch_refused),
    ("reingest_idempotent", scen_reingest_idempotent),
    ("pageless_verifies", scen_pageless_verifies),
    ("verify_anchors", scen_verify_anchors),
    ("ocr_drift_suggested", scen_ocr_drift_suggested),
    ("ocr_drift_no_suggestion", scen_ocr_drift_no_suggestion),
    ("declared_kind_unknown", scen_declared_kind_unknown),
    ("type_unknown_preserved", scen_type_unknown_preserved),
    ("doubt_kind", scen_doubt_kind),
    ("duplicate_document", scen_duplicate_document),
    ("version_siblings_linked", scen_version_siblings_linked),
    ("tag_preserved_and_filtered", scen_tag_preserved_and_filtered),
    ("offset_disambiguation", scen_offset_disambiguation),
    ("retrieve_filters", scen_retrieve_filters),
    ("result_contract_passthrough", scen_result_contract_passthrough),
    ("result_failed_honest", scen_result_failed_honest),
    ("store_corrupt_refused", scen_store_corrupt_refused),
]


def main() -> int:
    rows = []
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        for name, fn in SCENARIOS:
            try:
                ok = bool(fn(tmp, name))
                why = ""
            except Exception as exc:
                ok, why = False, f"raised {type(exc).__name__}: {exc}"
            rows.append({"scenario": name, "pass": ok, "why": why})
            print(("PASS" if ok else "FAIL") + f"  {name:<26}" + why)
    passed = sum(1 for r in rows if r["pass"])
    report = {"schema_version": "annotate-bench/v1", "scenarios": rows,
              "totals": {"passed": passed, "of": len(rows)}}
    (Path(__file__).resolve().parent / "report_annotate.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n{passed}/{len(rows)} scenarios pass")
    return 0 if passed == len(rows) else 1


if __name__ == "__main__":
    raise SystemExit(main())
