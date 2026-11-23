"""Benchmark for the doc-classification skill.

Each scenario asserts one property the challenge judges — explainable labels,
multi-label honesty, 未分类 honesty, the batch summary, refusal behaviour — plus
the FP guards (a cue collision must not distort a clean classification; a rerun
must be byte-identical; the CLI refusal still writes result.json). The land
scenarios pin the five-step landing protocol mechanically: P1 inventory hashes,
P3 naming degradation and collisions, P4 dedup/version relations, P5 journal,
rollback, idempotent rerun and the no-overwrite conflict rule.

    python bench_classify.py
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import classify  # noqa: E402
import land  # noqa: E402

TAX = [
    {"category": "实验方法", "cues": ["方法", "protocol", "we measured", "步骤"]},
    {"category": "研究结果", "cues": ["结果", "increased", "three-fold", "表明"]},
    {"category": "数据集", "cues": ["dataset", "csv", "supplementary"]},
]

SPEC = {"taxonomy": TAX, "records": [
    {"id": "r1", "title": "paper note", "text": "结果：涂层使吸收速率提高三倍 three-fold"},
    {"id": "r2", "title": "lab log", "text": "方法：uptake at 25 C。结果：重复性良好"},
    {"id": "r3", "title": "shopping", "text": "牛奶、鸡蛋、咖啡豆"},
]}


def _by_id(result):
    return {r["id"]: r for r in result["records"]}


def _finding(result, rule):
    return next((f for f in result["findings"] if f["rule"] == rule), None)


def scen_clean_classification(tmp, name):
    res = classify.run(SPEC)
    recs = _by_id(res)
    return res["status"] == "ok" and recs["r1"]["primary"] == "研究结果" \
        and recs["r1"]["confidence"] == 1.0 and not recs["r1"]["multi_label"]


def scen_matched_cues_explainable(tmp, name):
    """Every label carries the exact cues that matched — the evidence is on the record."""
    res = classify.run(SPEC)
    recs = _by_id(res)
    cues = recs["r1"]["labels"][0]["matched_cues"]
    return "结果" in cues and "three-fold" in cues \
        and recs["r1"]["labels"][0]["cue_hits"] == 2


def scen_multi_label_recorded(tmp, name):
    """A record hitting two categories keeps both labels; the tie resolves by
    declared taxonomy order, and the runner-up stays visible."""
    res = classify.run(SPEC)
    r2 = _by_id(res)["r2"]
    cats = [l["category"] for l in r2["labels"]]
    return r2["multi_label"] and r2["primary"] == "实验方法" \
        and cats == ["实验方法", "研究结果"] and r2["confidence"] == 0.25 \
        and r2["evidence_share"] == 0.5 and r2["review_required"] \
        and r2["ambiguity"]["is_ambiguous"] \
        and res["summary"]["multi_label_ids"] == ["r2"]


def scen_unclassified_honest(tmp, name):
    """A record nothing matches lands in 未分类 with the reason, plus a finding."""
    res = classify.run(SPEC)
    r3 = _by_id(res)["r3"]
    f = _finding(res, "cls.unclassified")
    return r3["primary"] == "未分类" and "no declared cue" in r3["reason"] \
        and f is not None and f["ids"] == ["r3"] \
        and res["summary"]["per_category"]["未分类"] == 1


def scen_empty_taxonomy_refused(tmp, name):
    """No declared taxonomy is a refusal, not a guessed classification."""
    r1 = classify.run({"records": [{"id": "a", "text": "结果：three-fold"}]})
    r2 = classify.run({"taxonomy": [], "records": [{"id": "a", "text": "x"}]})
    r3 = classify.run({"taxonomy": [{"cues": ["x"]}], "records": [{"id": "a", "text": "x"}]})
    return r1["refusal"]["rule"] == "cls.empty_taxonomy" \
        and r2["refusal"]["rule"] == "cls.empty_taxonomy" \
        and r3["refusal"]["rule"] == "cls.empty_taxonomy" \
        and all(r["status"] == "undetermined" for r in (r1, r2, r3))


def scen_no_records_refused(tmp, name):
    """Missing, empty or all-malformed records are refusals."""
    r1 = classify.run({"taxonomy": TAX})
    r2 = classify.run({"taxonomy": TAX, "records": []})
    r3 = classify.run({"taxonomy": TAX, "records": [123, None]})
    return r1["refusal"]["rule"] == "cls.no_records" \
        and r2["refusal"]["rule"] == "cls.no_records" \
        and r3["refusal"]["rule"] == "cls.no_records"


def scen_bare_string_record(tmp, name):
    """A bare-string record is a document with no metadata: classified by its text."""
    res = classify.run({"taxonomy": TAX,
                        "records": ["结果：three-fold 提升明显", {"id": "obj", "text": "dataset csv"}]})
    recs = _by_id(res)
    return res["status"] == "ok" and recs["rec-001"]["primary"] == "研究结果" \
        and recs["obj"]["primary"] == "数据集"


def scen_record_skipped_named(tmp, name):
    """A record entry that is neither object nor string is named, not dropped."""
    res = classify.run({"taxonomy": TAX,
                        "records": [{"id": "ok1", "text": "结果：three-fold"}, 42,
                                    {"id": "ok2", "text": "dataset csv"}]})
    f = _finding(res, "cls.record_skipped")
    return res["status"] == "ok" and f is not None and f["count"] == 1 \
        and f["entries"][0]["index"] == 1 \
        and {r["id"] for r in res["records"]} == {"ok1", "ok2"}


def scen_cue_collision_finding(tmp, name):
    """The same cue in two categories counts for both — flagged, and multi-label
    classification still works."""
    tax = [{"category": "A", "cues": ["uptake", "coating"]},
           {"category": "B", "cues": ["uptake", "anneal"]}]
    res = classify.run({"taxonomy": tax,
                        "records": [{"id": "d", "text": "uptake coating anneal"}]})
    f = _finding(res, "cls.cue_collision")
    rec = _by_id(res)["d"]
    return f is not None and f["categories"] == ["A", "B"] \
        and rec["multi_label"] and rec["primary"] == "A" \
        and [l["category"] for l in rec["labels"]] == ["A", "B"]


def scen_batch_summary_counts(tmp, name):
    """The summary table: per-category primary counts + label mentions."""
    res = classify.run(SPEC)
    s = res["summary"]
    return s["total_records"] == 3 \
        and s["per_category"] == {"实验方法": 1, "研究结果": 1, "数据集": 0, "未分类": 1} \
        and s["label_mentions"] == {"实验方法": 1, "研究结果": 2, "数据集": 0} \
        and s["unclassified_ids"] == ["r3"]


def scen_rerun_identical(tmp, name):
    """No wall-clock fields: the same spec re-runs byte-identical."""
    a = json.dumps(classify.run(SPEC), ensure_ascii=False, sort_keys=True)
    b = json.dumps(classify.run(SPEC), ensure_ascii=False, sort_keys=True)
    return a == b


def scen_min_cue_hits_threshold(tmp, name):
    """min_cue_hits raises the labelling bar; below it the record is honestly 未分类."""
    tax = [{"category": "A", "cues": ["uptake", "coating"]}]
    res = classify.run({"taxonomy": tax, "records": [
        {"id": "strong", "text": "uptake and coating"},
        {"id": "weak", "text": "uptake only"}]}, min_hits=2)
    recs = _by_id(res)
    return recs["strong"]["primary"] == "A" and recs["weak"]["primary"] == "未分类" \
        and recs["strong"]["labels"][0]["cue_hits"] == 2


def scen_cli_ok_writes(tmp, name):
    """The CLI happy path: exit 0, result.json + summary.md written."""
    spec_path = tmp / "spec.json"
    spec_path.write_text(json.dumps(SPEC, ensure_ascii=False), encoding="utf-8")
    out = tmp / "out"
    proc = subprocess.run([sys.executable, str(Path(__file__).resolve().parent / "classify_cli.py"),
                           "--spec", str(spec_path), "--out", str(out)],
                          capture_output=True, text=True, timeout=120)
    ok = proc.returncode == 0 and (out / "result.json").exists() and (out / "summary.md").exists()
    if not ok:
        return False
    result = json.loads((out / "result.json").read_text(encoding="utf-8"))
    summary = (out / "summary.md").read_text(encoding="utf-8")
    return result["status"] == "ok" and "| category |" in summary \
        and "未分类" in summary


def scen_cli_refusal_exit5(tmp, name):
    """A spec without a taxonomy is refused with exit 5 and a written result.json."""
    spec_path = tmp / "bad.json"
    spec_path.write_text(json.dumps({"records": [{"id": "a", "text": "x"}]},
                                    ensure_ascii=False), encoding="utf-8")
    out = tmp / "out5"
    proc = subprocess.run([sys.executable, str(Path(__file__).resolve().parent / "classify_cli.py"),
                           "--spec", str(spec_path), "--out", str(out)],
                          capture_output=True, text=True, timeout=120)
    ok = proc.returncode == 5 and (out / "result.json").exists()
    if not ok:
        return False
    result = json.loads((out / "result.json").read_text(encoding="utf-8"))
    return result["status"] == "undetermined" \
        and result["refusal"]["rule"] == "cls.empty_taxonomy" \
        and not (out / "summary.md").exists()


# ---------------------------------------------------------------------------
# Landing-protocol scenarios (P1 / P3 / P4 / P5)
# ---------------------------------------------------------------------------

def _tree(tmp: Path, name: str = "batch") -> Path:
    batch = tmp / name
    (batch / "sub").mkdir(parents=True, exist_ok=True)
    (batch / "a_published.pdf").write_bytes(b"%PDF-1.4 real body " * 6)
    (batch / "b_preprint.pdf").write_bytes(b"%PDF-1.4 real body " * 6 + b"v2")
    (batch / "note.txt").write_text("coating uptake three-fold", encoding="utf-8")
    (batch / "sub" / "dup.txt").write_text("same bytes", encoding="utf-8")
    (batch / "dup.txt").write_text("same bytes", encoding="utf-8")
    return batch


ENTRIES = [
    {"path": "a_published.pdf", "category": "研究结果", "author": "Zhang",
     "year": 2023, "title": "Coating uptake", "doi": "10.1/xyz",
     "version": "published"},
    {"path": "b_preprint.pdf", "category": "研究结果", "author": "Zhang",
     "year": 2022, "title": "Coating uptake preprint", "doi": "doi:10.1/XYZ",
     "version": "preprint"},
    {"path": "note.txt", "category": "实验方法", "author": "Li Si", "year": 2024,
     "title": "Protocol draft"},
    {"path": "dup.txt", "category": "数据集"},
    {"path": "sub/dup.txt", "category": "数据集"},
]


def scen_land_inventory_hashes(tmp, name):
    """P1: every file lands in the inventory with sha256, size and kind."""
    batch = _tree(tmp, name)
    inv = land.inventory(batch)
    paths = {f["path"] for f in inv["files"]}
    ok = inv["status"] == "ok" and len(inv["files"]) == 5 \
        and "sub/dup.txt" in paths \
        and all(f["sha256"] and f["size"] >= 0 for f in inv["files"]) \
        and inv["counts"]["files"] == 5 and not inv["findings"]
    hashes = {f["path"]: f["sha256"] for f in inv["files"]}
    inv2 = land.inventory(batch)
    return ok and hashes == {f["path"]: f["sha256"] for f in inv2["files"]}


def scen_land_inventory_flags(tmp, name):
    """P1: 0-byte files, encrypted PDFs and unreadable files are named, never dropped."""
    batch = tmp / "flags"
    batch.mkdir(exist_ok=True)
    (batch / "empty.txt").write_text("", encoding="utf-8")
    (batch / "locked.pdf").write_bytes(b"%PDF-1.4 /Encrypt <</V 2>>" + b"pad" * 20)
    (batch / "fine.txt").write_text("ok", encoding="utf-8")
    inv = land.inventory(batch)
    rules = {f["rule"] for f in inv["findings"]}
    empty = next(f for f in inv["files"] if f["path"] == "empty.txt")
    enc = next(f for f in inv["files"] if f["path"] == "locked.pdf")
    return "inv.zero_byte" in rules and "inv.pdf_encrypted" in rules \
        and empty["usable"] is False and enc["encrypted"] is True \
        and enc["usable"] is False and len(inv["files"]) == 3


def scen_land_plan_naming_degradation(tmp, name):
    """P3: special chars stripped, long names truncated with a hash suffix,
    metadata-missing names follow the declared degradation chain."""
    batch = tmp / "degrade"
    batch.mkdir(exist_ok=True)
    (batch / "x1.pdf").write_bytes(b"1")
    (batch / "x2.pdf").write_bytes(b"2")
    (batch / "x3.pdf").write_bytes(b"3")
    (batch / "x4.pdf").write_bytes(b"4")
    long_title = "Extremely Long Study Title About Coating Uptake Behaviour " \
                 "Under Varying Conditions"
    entries = [
        {"path": "x1.pdf", "category": "研究结果", "author": "A/B:<wi?", "year": 2023,
         "title": long_title},
        {"path": "x2.pdf", "category": "研究结果", "doi": "10.1/abc"},
        {"path": "x3.pdf", "category": "研究结果"},
        {"path": "x4.pdf", "category": "研究结果", "title": "Only title known"},
    ]
    r1 = land.build_plan(entries, land.inventory(batch), {})
    r2 = land.build_plan(entries, land.inventory(batch), {})
    rows = {p["path"]: p for p in r1["plan"]}
    n1 = rows["x1.pdf"]["new"]
    degraded = {p["path"] for p in r1["plan"] if p["metadata_incomplete"]}
    return json.dumps(r1["plan"]) == json.dumps(r2["plan"]) \
        and "/" not in Path(n1).stem and ":" not in Path(n1).stem \
        and len(Path(n1).stem) <= 60 and n1.split("-")[-1] != "" \
        and rows["x2.pdf"]["name_basis"].startswith("doi") \
        and rows["x3.pdf"]["name_basis"].startswith("uncategorized") \
        and rows["x4.pdf"]["name_basis"].startswith("title") \
        and degraded == {"x2.pdf", "x3.pdf", "x4.pdf"}


def scen_land_plan_collision_guard(tmp, name):
    """P3: same target name -> hash suffix, not overwrite; a repeated entry
    path is named and planned once."""
    batch = tmp / "coll"
    batch.mkdir(exist_ok=True)
    (batch / "m1.txt").write_bytes(b"one")
    (batch / "m2.txt").write_bytes(b"two")
    entries = [
        {"path": "m1.txt", "category": "A", "title": "same name"},
        {"path": "m2.txt", "category": "A", "title": "same name"},
        {"path": "m2.txt", "category": "B"},
    ]
    r = land.build_plan(entries, land.inventory(batch), {})
    rules = {f["rule"] for f in r["findings"]}
    rows = [p for p in r["plan"] if p["path"] in ("m1.txt", "m2.txt")]
    targets = [p["new"] for p in rows]
    return "name.collision_resolved" in rules and "plan.duplicate_entry" in rules \
        and len(rows) == 2 and len(set(targets)) == 2


def scen_land_dup_exact_archive(tmp, name):
    """P4: identical bytes -> keep one, archive the rest into duplicates/,
    never delete: the file count on disk is unchanged after execution."""
    batch = _tree(tmp, name)
    out = tmp / "outdup"
    r = land.land_run({"entries": ENTRIES}, batch, out, execute_now=True)
    dupf = next((d for d in r["duplicates"]), None)
    tree_after = [p for p in batch.rglob("*") if p.is_file()]
    return r["status"] == "review" and dupf is not None \
        and dupf["keep"] == "dup.txt" and dupf["archive"] == ["sub/dup.txt"] \
        and len(tree_after) == 5 \
        and (batch / "duplicates" / "dup.txt").is_file()


def scen_land_dup_near_version(tmp, name):
    """P4: same DOI, different bytes -> candidate duplicate kept for manual
    confirm; declared versions yield a formal/preprint relation, and neither
    file is moved automatically."""
    batch = _tree(tmp, name)
    r = land.land_run({"entries": ENTRIES}, batch, tmp / "outnear")
    near = next((g for g in r["near_duplicates"]), None)
    rel = next((v for v in r["version_relations"]), None)
    rules = {f["rule"] for f in r["findings"]}
    moves = {p["path"] for p in r["plan"] if p["op"] == "move"}
    return r["status"] == "review" and near is not None \
        and near["basis"] == "doi" and near["decision"] == "manual_confirm" \
        and set(near["paths"]) == {"a_published.pdf", "b_preprint.pdf"} \
        and rel is not None and rel["formal"] == ["a_published.pdf"] \
        and rel["preprint"] == ["b_preprint.pdf"] \
        and "dup.near" in rules and "ver.relation" in rules \
        and "a_published.pdf" in moves and "b_preprint.pdf" in moves


def scen_land_exec_journal_rollback(tmp, name):
    """P5: executed moves are journalled with both-end hashes; rollback
    restores the original tree exactly (paths and hashes)."""
    batch = _tree(tmp, name)
    out = tmp / "outrb"
    before = {str(p.relative_to(batch)): land._sha256_file(p)
              for p in sorted(batch.rglob("*")) if p.is_file()}
    r = land.land_run({"entries": ENTRIES}, batch, out, execute_now=True)
    journal = [json.loads(l) for l in
               (out / "journal.jsonl").read_text(encoding="utf-8").splitlines()]
    rb = land.rollback(out / "journal.jsonl", batch, out)
    after = {str(p.relative_to(batch)): land._sha256_file(p)
             for p in sorted(batch.rglob("*")) if p.is_file()}
    return r["executed"]["changed"] == 5 and len(journal) == 5 \
        and all(e["op"] == "move" and e["sha256"] == e["sha256_verified"]
                for e in journal) \
        and rb["status"] == "ok" and rb["restored"] == 5 and rb["mismatches"] == 0 \
        and before == after


def scen_land_exec_idempotent_noop(tmp, name):
    """P5: a rerun over the executed tree resumes the manifest and does zero ops."""
    batch = _tree(tmp, name)
    out = tmp / "outnoop"
    r1 = land.land_run({"entries": ENTRIES}, batch, out, execute_now=True)
    r2 = land.land_run({"entries": ENTRIES}, batch, out, execute_now=True)
    return r1["executed"]["changed"] == 5 \
        and r2["mode"] == "resume" and r2["executed"]["changed"] == 0 \
        and r2["executed"]["already_done"] == 5 and r2.get("idempotent") is True \
        and r2["status"] == "ok" and not r2["findings"]


def scen_land_exec_conflict_no_overwrite(tmp, name):
    """P5: a differing target file is never overwritten — a named conflict
    blocks the batch and the target content survives byte-for-byte."""
    batch = tmp / "conf"
    batch.mkdir(exist_ok=True)
    (batch / "k.txt").write_text("original content", encoding="utf-8")
    entries = [{"path": "k.txt", "category": "A", "title": "k doc"}]
    out = tmp / "outconf"
    land.land_run({"entries": entries}, batch, out, execute_now=True)
    rb = land.rollback(out / "journal.jsonl", batch, out)
    target = batch / "A" / "k-doc.txt"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("someone else's file", encoding="utf-8")
    (batch / "k.txt").write_text("original content", encoding="utf-8")
    land.execute(land.build_plan(entries, land.inventory(batch), {})["plan"],
                 batch, out)
    return rb["status"] == "ok" \
        and target.read_text(encoding="utf-8") == "someone else's file" \
        and (batch / "k.txt").read_text(encoding="utf-8") == "original content"


def scen_land_cli_contract_and_exits(tmp, name):
    """CLI: contract echo (case_id + output_contract fields), exit 0 on a clean
    batch (no dup/near findings), exit 5 with a written result.json on an
    unreadable spec."""
    batch = tmp / name
    batch.mkdir(exist_ok=True)
    (batch / "one.pdf").write_bytes(b"paper one")
    (batch / "two.txt").write_text("note two", encoding="utf-8")
    clean_entries = [
        {"path": "one.pdf", "category": "研究结果", "author": "Zhang", "year": 2023,
         "title": "Coating uptake"},
        {"path": "two.txt", "category": "实验方法", "author": "Li Si", "year": 2024,
         "title": "Protocol draft"},
    ]
    spec = {"case_id": "case-p52-1", "entries": clean_entries,
            "output_contract": {"library_result": {}, "operation_evidence": {}}}
    sp = tmp / "landspec.json"
    sp.write_text(json.dumps(spec, ensure_ascii=False), encoding="utf-8")
    out = tmp / "outcli"
    p1 = subprocess.run([sys.executable, "-I", "-X", "utf8",
                         str(Path(__file__).resolve().parent / "land_cli.py"),
                         "--spec", str(sp), "--root", str(batch), "--out", str(out)],
                        capture_output=True, text=True, timeout=120)
    rj = out / "result.json"
    ok1 = p1.returncode == 0 and rj.exists() and (out / "plan.md").exists()
    if not ok1:
        return False
    res = json.loads(rj.read_text(encoding="utf-8"))
    bad = tmp / "bad.json"
    bad.write_text("{not json", encoding="utf-8")
    out2 = tmp / "outcli5"
    p2 = subprocess.run([sys.executable, "-I", "-X", "utf8",
                         str(Path(__file__).resolve().parent / "land_cli.py"),
                         "--spec", str(bad), "--root", str(batch), "--out", str(out2)],
                        capture_output=True, text=True, timeout=120)
    res2 = json.loads((out2 / "result.json").read_text(encoding="utf-8"))
    return res["case_id"] == "case-p52-1" \
        and "library_result" in res and "operation_evidence" in res \
        and p2.returncode == 5 and res2["status"] == "undetermined" \
        and res2["refusal"]["rule"] == "land.spec_unreadable"


SCENARIOS = [
    ("clean_classification", scen_clean_classification),
    ("matched_cues_explainable", scen_matched_cues_explainable),
    ("multi_label_recorded", scen_multi_label_recorded),
    ("unclassified_honest", scen_unclassified_honest),
    ("empty_taxonomy_refused", scen_empty_taxonomy_refused),
    ("no_records_refused", scen_no_records_refused),
    ("bare_string_record", scen_bare_string_record),
    ("record_skipped_named", scen_record_skipped_named),
    ("cue_collision_finding", scen_cue_collision_finding),
    ("batch_summary_counts", scen_batch_summary_counts),
    ("rerun_identical", scen_rerun_identical),
    ("min_cue_hits_threshold", scen_min_cue_hits_threshold),
    ("cli_ok_writes", scen_cli_ok_writes),
    ("cli_refusal_exit5", scen_cli_refusal_exit5),
    ("land_inventory_hashes", scen_land_inventory_hashes),
    ("land_inventory_flags", scen_land_inventory_flags),
    ("land_plan_naming_degradation", scen_land_plan_naming_degradation),
    ("land_plan_collision_guard", scen_land_plan_collision_guard),
    ("land_dup_exact_archive", scen_land_dup_exact_archive),
    ("land_dup_near_version", scen_land_dup_near_version),
    ("land_exec_journal_rollback", scen_land_exec_journal_rollback),
    ("land_exec_idempotent_noop", scen_land_exec_idempotent_noop),
    ("land_exec_conflict_no_overwrite", scen_land_exec_conflict_no_overwrite),
    ("land_cli_contract_and_exits", scen_land_cli_contract_and_exits),
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
    report = {"schema_version": "doc-classify-bench/v1", "scenarios": rows,
              "totals": {"passed": passed, "of": len(rows)}}
    (Path(__file__).resolve().parent / "report_classify.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n{passed}/{len(rows)} scenarios pass")
    return 0 if passed == len(rows) else 1


if __name__ == "__main__":
    raise SystemExit(main())
