"""Adversarial/real-file checks for the hybrid file-search implementation."""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import search  # noqa: E402
import localfiles  # noqa: E402

CLI = Path(__file__).resolve().parent / "search_cli.py"


def _run(args):
    return subprocess.run([sys.executable, "-I", "-X", "utf8", str(CLI)] + list(map(str, args)),
                          capture_output=True, text=True, timeout=120)


def scen_bm25_saturation(tmp, name):
    corpus = [{"id": "once", "text": "coating alpha beta gamma"},
              {"id": "repeat", "text": "coating coating coating coating coating coating coating coating coating coating"}]
    _, res = search.search({"corpus": corpus, "query": "coating"})
    scores = {h["doc_id"]: h["rank_reason"]["body_bm25"] for h in res["hits"]}
    return scores["repeat"] > scores["once"] and scores["repeat"] < 10 * scores["once"]


def scen_metadata_channel(tmp, name):
    corpus = [{"id": "d1", "title": "Buffer Protocol", "path": "records/p1.txt",
               "meta": {"project": "P-7"}, "text": "nothing relevant in body"}]
    _, res = search.search({"corpus": corpus, "query": "P-7"})
    hit = res["hits"][0]
    return hit["rank_reason"]["metadata_rank"] == 1 and hit["rank_reason"]["metadata_bm25"] > 0 \
        and hit["field_matches"] and hit["field_matches"][0]["field"] == "metadata"


def scen_cjk_boundaries(tmp, name):
    _, no = search.search({"corpus": [{"id": "split", "text": "缓。冲。液"}], "query": "缓冲"})
    corpus = [{"id": "protocol", "text": "1 缓冲液配制\nTris 缓冲液 50 mM，过滤后备用。"}]
    _, yes = search.search({"corpus": corpus, "query": "缓冲液配方在哪里"})
    return no["empty"] and not yes["empty"] and "液配" in yes["hits"][0]["matched_terms"]


def scen_page_and_verbatim(tmp, name):
    corpus = [{"id": "p", "text": "1 第一页\n无关键词。\f2 第二页\n缓冲液配方在这里。"}]
    idx = search.build_index(corpus)["index"]
    res = search.run_query(idx, "缓冲液")["result"]
    loc = res["hits"][0]["passages"][0]["locator"]
    para = idx["documents"]["p"]["paragraphs"][loc["paragraph"]]
    return loc["page"] == 2 and loc["section"] == "2 第二页" \
        and para[loc["start"]:loc["end"]] == loc["quote"]


def scen_no_result_diagnostics(tmp, name):
    corpus = [{"id": "a", "meta": {"year": 2023}, "text": "uptake"},
              {"id": "b", "meta": {"year": 2024}, "text": "uptake"}]
    _, res = search.search({"corpus": corpus,
                            "query": {"all": ["uptake"], "filters": {"year": 1999}}})
    info = res["no_result"]
    return info["reason"] == "filters_excluded_all_term_matches" \
        and info["term_matching_doc_ids_before_filters"] == ["a", "b"] \
        and info["available_filter_values"] == {"year": [2023, 2024]}


def scen_ambiguity_and_copy_evidence(tmp, name):
    corpus = [{"id": "a", "text": "same buffer formula"}, {"id": "b", "text": "same buffer formula"}]
    _, res = search.search({"corpus": corpus, "query": "buffer"})
    return res["ambiguity"]["is_ambiguous"] and res["evidence"]["independent_document_count"] == 1 \
        and res["evidence"]["duplicate_doc_id_sets"] == [["a", "b"]]


def scen_rank_explanation_recomputable(tmp, name):
    corpus = [{"id": "a", "text": "buffer buffer long text tail"},
              {"id": "b", "text": "buffer short"}]
    i1, r1 = search.search({"corpus": corpus, "query": "buffer"})
    i2, r2 = search.search({"corpus": corpus, "query": "buffer"})
    return json.dumps(r1, sort_keys=True) == json.dumps(r2, sort_keys=True) \
        and all("body_term_contributions" in h["rank_reason"] for h in r1["hits"]) \
        and i1["corpus_sha256"] == i2["corpus_sha256"]


def _real_root(tmp):
    root = tmp / "root"
    root.mkdir(exist_ok=True)
    (root / "protocol.txt").write_text("1 缓冲液配制\nTris 缓冲液 50 mM。\f2 保存\n4 C 保存。", encoding="utf-8")
    with zipfile.ZipFile(root / "paper.docx", "w") as zf:
        zf.writestr("docProps/core.xml", "<cp:coreProperties xmlns:cp='x' xmlns:dc='d'><dc:title>Coating uptake</dc:title><dc:creator>Zhang</dc:creator></cp:coreProperties>")
        zf.writestr("word/document.xml", "<w:document xmlns:w='w'><w:body><w:p><w:r><w:t>Porous coating uptake measured.</w:t></w:r></w:p></w:body></w:document>")
    (root / "scan.pdf").write_bytes(b"%PDF-1.4 not a real parseable PDF")
    (root / "metadata.json").write_text(json.dumps({"records": [
        {"path": "protocol.txt", "meta": {"year": 2024, "title": "缓冲液方法"}},
        {"path": "paper.docx", "meta": {"year": 2023}}
    ]}, ensure_ascii=False), encoding="utf-8")
    return root


def scen_real_root_coverage(tmp, name):
    root = _real_root(tmp)
    got = localfiles.build_corpus(root)
    by_id = {d["id"]: d for d in got["corpus"]}
    scan = next(r for r in got["coverage"] if r["path"] == "scan.pdf")
    return got["ok"] and len(got["corpus"]) == 2 and by_id["paper.docx"]["text"].startswith("Porous") \
        and by_id["paper.docx"]["meta"]["title"] == "Coating uptake" \
        and scan["status"] == "failed" and len(scan["source_sha256"]) == 64


def scen_real_root_cli_and_readonly(tmp, name):
    root = _real_root(tmp)
    before = {p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
              for p in root.rglob("*") if p.is_file()}
    case = tmp / "case.json"
    case.write_text(json.dumps({"case_id": name, "output_contract": {
        "search_result": {}, "operation_evidence": {}, "failure_recovery": {}, "required_literal": "kept"}}), encoding="utf-8")
    out = tmp / "out"
    proc = _run(["--root", root, "--query", "缓冲液配方在哪里", "--case", case, "--out", out])
    if proc.returncode != 4 or not (out / "coverage.json").is_file():
        return False
    result = json.loads((out / "result.json").read_text(encoding="utf-8"))
    after = {p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
             for p in root.rglob("*") if p.is_file()}
    loc = result["hits"][0]["passages"][0]["locator"]
    return before == after and result["case_id"] == name and result["required_literal"] == "kept" \
        and loc["page"] == 1 and result["status"] == "partial" \
        and any(f["rule"] == "search.file_extraction_incomplete" for f in result["findings"])


def scen_refusal_contract_and_idempotence(tmp, name):
    case = tmp / "case.json"
    case.write_text(json.dumps({"case_id": name, "output_contract": {
        "search_result": {}, "failure_recovery": {}, "required": 7}}), encoding="utf-8")
    bad = tmp / "bad.json"
    bad.write_text("{oops", encoding="utf-8")
    out = tmp / "out"
    root = _real_root(tmp)
    p1 = _run(["--root", root, "--query-file", bad, "--case", case, "--out", out])
    if p1.returncode != 5:
        return False
    r1 = json.loads((out / "result.json").read_text(encoding="utf-8"))
    p2 = _run(["--root", root, "--query-file", bad, "--case", case, "--out", out])
    r2_raw = (out / "result.json").read_bytes()
    return p2.returncode == 5 and r1["case_id"] == name and r1["required"] == 7 \
        and "search_result" in r1 and "failure_recovery" in r1 \
        and json.dumps(r1, ensure_ascii=False, sort_keys=True) == json.dumps(
            json.loads(r2_raw), ensure_ascii=False, sort_keys=True)


SCENARIOS = [
    ("bm25_saturation", scen_bm25_saturation),
    ("metadata_channel", scen_metadata_channel),
    ("cjk_boundaries", scen_cjk_boundaries),
    ("page_and_verbatim", scen_page_and_verbatim),
    ("no_result_diagnostics", scen_no_result_diagnostics),
    ("ambiguity_and_copy_evidence", scen_ambiguity_and_copy_evidence),
    ("rank_explanation_recomputable", scen_rank_explanation_recomputable),
    ("real_root_coverage", scen_real_root_coverage),
    ("real_root_cli_and_readonly", scen_real_root_cli_and_readonly),
    ("refusal_contract_and_idempotence", scen_refusal_contract_and_idempotence),
]


def main() -> int:
    rows = []
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        for name, fn in SCENARIOS:
            try:
                ok, why = bool(fn(tmp, name)), ""
            except Exception as exc:
                ok, why = False, f"raised {type(exc).__name__}: {exc}"
            rows.append({"scenario": name, "pass": ok, "why": why})
            print(("PASS" if ok else "FAIL") + f"  {name:<38}" + why)
    passed = sum(r["pass"] for r in rows)
    report = {"schema_version": "file-search-hybrid-bench/v1", "scenarios": rows,
              "totals": {"passed": passed, "of": len(rows)}}
    (Path(__file__).resolve().parent / "report_search_hybrid.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n{passed}/{len(rows)} scenarios pass")
    return int(passed != len(rows))


if __name__ == "__main__":
    raise SystemExit(main())
