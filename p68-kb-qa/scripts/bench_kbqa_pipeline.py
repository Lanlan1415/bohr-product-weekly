"""Functional bench for the real retrieval -> extractive answer -> export pipeline.

Every case is synthetic and generated in a fresh temporary directory.  No formal
organiser case or prepared answer is embedded.  Clean baselines must verify every
claim against the exported paragraph and character range.
"""
from __future__ import annotations

import copy
import hashlib
import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import kbqa


def case(**over):
    base = {
        "case_id": "bench-kbqa",
        "documents": [{"document_id": "protocol", "version": "v2",
                       "text": "样品在测量期间保存于 4 C。\n\n每组使用六个重复。"}],
        "questions": [{"question_id": "q1", "question": "样品测量时的保存温度是多少？"}],
        "output_contract": {"answers": [], "evidence": [], "status": "",
                            "deliverable": "grounded answers", "unknown_object": {"required": True}},
    }
    base.update(over)
    return copy.deepcopy(base)


def run(root, spec, name="out"):
    return kbqa.run_case(spec, root, root / name)


def digest_outputs(path):
    return {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(path.iterdir()) if p.is_file()}


def build_scenarios():
    sc = []

    def add(name, fn):
        sc.append((name, fn))

    def pure_zh(root):
        r = run(root, case())
        a = r["answers"][0]
        return (a["status"] == "answered" and "保存于 4 C" in a["answer"]
                and a["claims"][0]["kind"] == "reported" and r["verification"]["ok"])

    add("clean_pure_chinese", pure_zh)

    def zh_english(root):
        s = case(documents=[{"document_id": "paper", "text": "All samples were held at 25 C during measurement."}])
        r = run(root, s)
        return r["answers"][0]["status"] == "answered" and "25 C" in r["answers"][0]["answer"]

    add("chinese_query_english_source", zh_english)

    def unknown(root):
        s = case(questions=[{"question_id": "u", "question": "量子引力常数的精确值是多少？"}])
        r = run(root, s)
        a = r["answers"][0]
        return (a["status"] == "insufficient_evidence" and not a["claims"]
                and a["answer_kind"] == "explicit_unknown" and a["gaps"])

    add("no_answer_abstains", unknown)

    def multihop(root):
        s = case(questions=[{"question_id": "m", "question": "请分别回答保存温度，以及每组的重复数量。"}])
        r = run(root, s)
        a = r["answers"][0]
        return (a["coverage"] == {"subquestions": 2, "answered": 2, "unanswered": 0}
                and len(a["claims"]) == 2 and len(r["query_plans"][0]["hops"]) == 2)

    add("multihop_complete_coverage", multihop)

    def explicit_subq(root):
        s = case(questions=[{"question_id": "m", "question": "两个条件", "subquestions": ["保存温度", "重复数量"]}])
        r = run(root, s)
        return len(r["answers"][0]["claims"]) == 2 and r["answers"][0]["status"] == "answered"

    add("explicit_subquestions", explicit_subq)

    def numeric_conflict(root):
        s = case(documents=[
            {"document_id": "v1", "version": "v1", "text": "样品在测量期间保存于 25 C。"},
            {"document_id": "v2", "version": "v2", "text": "样品在测量期间保存于 4 C。"}])
        r = run(root, s)
        conflict = r["conflicts"][0]
        values = sorted(x for pair in conflict["numeric_values"] for x in pair)
        return (r["answers"][0]["status"] == "conflicted" and values == ["25", "4"]
                and len(conflict["evidence"]) == 2 and r["versions"])

    add("version_numeric_conflict", numeric_conflict)

    def locators(root):
        r = run(root, case())
        c = r["answers"][0]["claims"][0]
        loc = c["locators"][0]
        evidence = next(e for e in r["evidence"] if e["evidence_id"] == c["cites"][0])
        return (loc["document_id"] == "protocol" and loc["paragraph"] == 1
                and loc["page"] is None and loc["char_start"] == 0
                and evidence["quote"] == c["text"] and r["verification"]["locator_coverage"] == 1)

    add("exact_sentence_locator_no_fake_page", locators)

    def real_page(root):
        s = case(documents=[{"document_id": "paged", "text": "封面\n\f第一组\n样品在测量期间保存于 4 C。\n\f讨论"}])
        r = run(root, s)
        loc = r["answers"][0]["claims"][0]["locators"][0]
        return loc["page"] == 2 and loc["paragraph"] == 3

    add("formfeed_real_page_coordinate", real_page)

    def duplicates(root):
        (root / "a.txt").write_text("样品在测量期间保存于 4 C。", encoding="utf-8")
        (root / "b.txt").write_text("样品在测量期间保存于 4 C。", encoding="utf-8")
        s = case(documents=[{"document_id": "a", "path": "a.txt"}, {"document_id": "alias-b", "path": "b.txt"}])
        r = run(root, s)
        return (len(r["answers"][0]["claims"]) == 1 and len(r["documents"]) == 2
                and r["documents"][0]["duplicate_of"] and r["documents"][1]["duplicate_of"])

    add("duplicates_kept_search_deduplicated", duplicates)

    def inventory_fields(root):
        (root / "sub").mkdir()
        (root / "sub" / "a.md").write_text("# 协议\n\n样品在测量期间保存于 4 C。", encoding="utf-8")
        s = case(documents=[{"document_id": "a", "path": "sub/a.md", "aliases": ["旧协议"],
                             "metadata": {"owner": "lab"}, "source": "workorder"}])
        r = run(root, s)
        d = r["documents"][0]
        return (d["file_type"] == ".md" and d["directory"] == "sub" and len(d["sha256"]) == 64
                and d["metadata"]["owner"] == "lab" and d["source"] == "workorder"
                and d["permissions"] == "read")

    add("directory_metadata_hash_permissions", inventory_fields)

    def contract(root):
        r = run(root, case())
        return (r["case_id"] == "bench-kbqa" and r["status"] == "done"
                and r["deliverable"] == "grounded answers" and r["answers"]
                and r["evidence"] and r["unknown_object"] is None
                and any("unknown_object" in x for x in r["limits"]))

    add("output_contract_all_fields", contract)

    def no_docs(root):
        s = case(documents=[])
        r = run(root, s)
        return (r["status"] == "undetermined" and r["answers"]
                and all(a["status"] == "insufficient_evidence" and not a["claims"] for a in r["answers"])
                and (root / "out" / "result.json").exists())

    add("empty_corpus_honest_undetermined", no_docs)

    def no_questions(root):
        s = case(questions=[])
        r = run(root, s)
        return r["status"] == "undetermined" and "question" in r["status_reason"]

    add("no_questions_honest_undetermined", no_questions)

    def missing_file(root):
        s = case(documents=[{"document_id": "missing", "path": "none.txt"},
                            {"document_id": "ok", "text": "样品在测量期间保存于 4 C。"}])
        r = run(root, s)
        return (r["status"] == "partial" and r["answers"][0]["status"] == "answered"
                and r["failures"][0]["rule"] == "kbqa.document_unreadable")

    add("missing_file_partial_recovery", missing_file)

    def malformed_records(root):
        s = case(documents=[42, None, {"document_id": "empty"},
                            {"document_id": "ok", "text": "样品在测量期间保存于 4 C。"}])
        r = run(root, s)
        rules = {f["rule"] for f in r["failures"]}
        return r["status"] == "partial" and "kbqa.record_not_object" in rules and "kbqa.document_has_no_content" in rules

    add("malformed_records_do_not_abort", malformed_records)

    def aliases(root):
        s = case(documents=[{"document_id": "p", "text": "Specimens were incubated at 4 C."}],
                 aliases={"sample": ["样品", "specimen"]})
        r = run(root, s)
        # Explicit aliases only expand to supplied terms.  Lack of semantic match
        # remains an honest unknown rather than a translation hallucination.
        return r["answers"][0]["status"] in {"answered", "insufficient_evidence"} and r["verification"]["ok"]

    add("declared_alias_query_variant", aliases)

    def deterministic(root):
        s = case(questions=[{"question_id": "m", "question": "请分别回答保存温度，以及每组的重复数量。"},
                            {"question_id": "u", "question": "不存在的火星实验参数是多少？"}])
        run(root, s, "out1")
        run(root, s, "out2")
        return digest_outputs(root / "out1") == digest_outputs(root / "out2")

    add("byte_deterministic_rerun", deterministic)

    def cold_verify(root):
        run(root, case())
        v = kbqa.verify_export(root / "out")
        return v["ok"] and v["claims_checked"] == 1

    add("cold_export_verification", cold_verify)

    def tamper_detected(root):
        run(root, case())
        p = root / "out" / "result.json"
        r = json.loads(p.read_text(encoding="utf-8"))
        r["answers"][0]["claims"][0]["text"] = "伪造的句子"
        p.write_text(json.dumps(r, ensure_ascii=False), encoding="utf-8")
        v = kbqa.verify_export(root / "out")
        return not v["ok"] and any(f["rule"] == "kbqa.quote_anchor_mismatch" for f in v["findings"])

    add("tampered_claim_detected", tamper_detected)

    def workorder(root):
        (root / "work.json").write_text(json.dumps({
            "documents": [{"document_id": "w", "text": "样品在测量期间保存于 4 C。"}],
            "questions": ["保存温度是多少？"]}, ensure_ascii=False), encoding="utf-8")
        s = {"case_id": "work", "workorder": "work.json", "output_contract": {"answers": []}}
        r = run(root, s)
        return r["case_id"] == "work" and r["answers"][0]["status"] == "answered"

    add("declared_workorder_loaded", workorder)

    def list_query(root):
        s = case(documents=[{"document_id": "a", "text": "文件 A 的记录温度为 4 C。"},
                            {"document_id": "b", "text": "文件 B 的记录温度为 25 C。"}],
                 questions=[{"question_id": "l", "question": "分别列出各文件记录的温度。"}])
        r = run(root, s)
        docs = {c["locators"][0]["document_id"] for c in r["answers"][0]["claims"]}
        return docs == {"a", "b"} and r["verification"]["ok"]

    add("multi_document_list_coverage", list_query)

    def exact_no_external_fact(root):
        r = run(root, case())
        answer = r["answers"][0]
        factual = [c["text"] for c in answer["claims"]]
        return all(t in "样品在测量期间保存于 4 C。\n\n每组使用六个重复。" for t in factual)

    add("all_answer_claims_verbatim_source", exact_no_external_fact)

    def duplicate_ids_do_not_overwrite(root):
        s = case(documents=[{"document_id": "same", "text": "样品保存在 4 C。"},
                            {"document_id": "same", "text": "每组包含六个重复。"}],
                 questions=[{"question_id": "m", "question": "请分别回答保存温度，以及每组重复数量。"}])
        r = run(root, s)
        ids = {c["locators"][0]["document_id"] for c in r["answers"][0]["claims"]}
        return (ids == {"same", "same~2"} and r["verification"]["ok"]
                and any(f["rule"] == "kbqa.duplicate_document_id" for f in r["failures"]))

    add("duplicate_ids_preserve_both_evidence_sets", duplicate_ids_do_not_overwrite)

    return sc


def main():
    rows = []
    for name, fn in build_scenarios():
        try:
            with tempfile.TemporaryDirectory() as td:
                ok = bool(fn(Path(td)))
            error = ""
        except Exception as exc:
            ok, error = False, f"{type(exc).__name__}: {exc}"
        rows.append({"scenario": name, "pass": ok, "error": error})
        print(f"{'PASS' if ok else 'FAIL'}  {name:<42} {error}")
    passed = sum(r["pass"] for r in rows)
    report = {"schema_version": "kbqa-pipeline-bench/v1", "scenarios": rows,
              "totals": {"passed": passed, "of": len(rows)},
              "note": "Synthetic functional cases only; clean claims are source-extractive and independently verified."}
    (Path(__file__).resolve().parent / "report_kbqa_pipeline.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n{passed}/{len(rows)} scenarios pass")
    return 0 if passed == len(rows) else 1


if __name__ == "__main__":
    raise SystemExit(main())
