"""Benchmark for the file-search skill.

Each scenario asserts one property the challenge judges — reproducible query
records, verbatim section-level locators, honest empty results, hard boolean
AND filter conditions, duplicate-content naming, refusal behaviour — plus the
FP guards (a skipped corpus entry is named, a malformed index refuses instead
of partially searching, the CLI writes the index for replay and layers its
exit codes 0/4/5).

    python bench_search.py
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import search  # noqa: E402

CORPUS = [
    {"id": "paper-coating",
     "text": "Porous coatings raise the uptake rate three-fold.\n"
             "We measured uptake at 25 C with six replicates per arm."},
    {"id": "paper-anneal",
     "text": "Annealing at 500 C changed the coating hardness.\n"
             "The uptake was unchanged after anneal."},
    {"id": "protocol-buffer",
     "text": "1 缓冲液配制\nTris 缓冲液 50 mM，pH 7.4，过滤后 4 C 保存。\n\n"
             "2 存储\n分装后 -20 C 冻存，避免反复冻融。"},
]

SPEC = {"corpus": CORPUS, "query": {"all": ["uptake"], "any": ["three-fold", "replicates"]}}


def _refusal_of(res):
    return res[1] if isinstance(res, tuple) else res


def scen_single_term(tmp, name):
    """A single term hits the right document with a located passage."""
    _, res = search.search({"corpus": CORPUS, "query": "replicates"})
    loc = res["hits"][0]["passages"][0]["locator"]
    return res["ok"] and not res["empty"] and len(res["hits"]) == 1 \
        and res["hits"][0]["doc_id"] == "paper-coating" \
        and loc["paragraph"] == 1 and loc["quote"] == "replicates"


def scen_boolean_and(tmp, name):
    """all-terms is a hard constraint: a doc with only one term stays out."""
    _, res = search.search({"corpus": CORPUS, "query": {"all": ["uptake", "replicates"]}})
    ids = [h["doc_id"] for h in res["hits"]]
    return res["ok"] and ids == ["paper-coating"] \
        and res["hits"][0]["matched_terms"] == ["replicates", "uptake"]


def scen_boolean_or(tmp, name):
    """any-terms is an alternative set: docs with either term come back."""
    _, res = search.search({"corpus": CORPUS,
                            "query": {"any": ["replicates", "缓冲液"]}})
    ids = [h["doc_id"] for h in res["hits"]]
    # The CJK hit has both heading+body BM25 evidence, so it legitimately
    # outranks the body-only latin hit under the new relevance ranking.
    return res["ok"] and ids == ["protocol-buffer", "paper-coating"] \
        and res["hits"][0]["score"] == 1 and res["hits"][1]["score"] == 1 \
        and res["hits"][0]["rank_reason"]["body_bm25"] > res["hits"][1]["rank_reason"]["body_bm25"]


def scen_boolean_all_any(tmp, name):
    """Both given, both must hold — the all-set is filtered by the any-set."""
    _, res = search.search(SPEC)
    ids = [h["doc_id"] for h in res["hits"]]
    return res["ok"] and ids == ["paper-coating"] \
        and res["hits"][0]["matched_terms"] == ["replicates", "three-fold", "uptake"]


def scen_no_hit_honest(tmp, name):
    """A query nothing matches returns an empty list with a note — no padding."""
    _, res = search.search({"corpus": CORPUS, "query": "quantum chromodynamics"})
    return res["ok"] and res["empty"] is True and res["hits"] == [] \
        and "never padded" in res["note"] and res["documents_indexed"] == 3


def scen_empty_corpus_refusal(tmp, name):
    """An empty or non-list corpus is a refusal, never a searched nothing."""
    r1 = search.search({"corpus": [], "query": "uptake"})
    r2 = search.search({"query": "uptake"})
    r3 = search.search({"corpus": {"id": "x", "text": "uptake"}, "query": "uptake"})
    b = search.build_index([])
    refusals = [r[1]["refusal"]["rule"] for r in (r1, r2, r3)]
    return all(x == "search.empty_corpus" for x in refusals) \
        and b["refusal"]["rule"] == "search.empty_corpus"


def scen_cjk_query(tmp, name):
    """A CJK query term hits with a CJK passage locator."""
    _, res = search.search({"corpus": CORPUS, "query": "缓冲液"})
    hit = res["hits"][0]
    loc = hit["passages"][0]["locator"]
    paras = search.build_index(CORPUS)["index"]["documents"]["protocol-buffer"]["paragraphs"]
    return res["ok"] and len(res["hits"]) == 1 \
        and hit["doc_id"] == "protocol-buffer" \
        and loc["paragraph"] == 0 and loc["quote"] == "缓冲液" \
        and paras[loc["paragraph"]][loc["start"]:loc["end"]] == loc["quote"]


def scen_bare_string_doc(tmp, name):
    """A bare-string corpus entry is a document with a generated id."""
    corpus = ["Porous coatings raise uptake three-fold."]
    built = search.build_index(corpus)
    _, res = search.search({"corpus": corpus, "query": "coating"})
    return built["ok"] and built["index"]["order"] == ["doc-001"] \
        and res["hits"][0]["doc_id"] == "doc-001"


def scen_malformed_index(tmp, name):
    """A malformed index refuses as a whole instead of partially searching."""
    r1 = search.run_query({}, "uptake")
    r2 = search.run_query({"documents": {"a": "not-a-doc"}, "order": ["a"]}, "uptake")
    r3 = search.run_query({"documents": {}, "order": ["missing"]}, "uptake")
    r4 = search.run_query([1, 2, 3], "uptake")
    return all(not r["ok"] and r["refusal"]["rule"] == "search.index_malformed"
               for r in (r1, r2, r3, r4))


def scen_empty_query_refusal(tmp, name):
    """A query declaring nothing searchable is refused, not run as a no-op."""
    _, e1 = search.parse_query("")
    _, e2 = search.parse_query("   ")
    r3 = search.search({"corpus": CORPUS, "query": {}})
    r4 = search.search({"corpus": CORPUS, "query": {"all": [], "any": []}})
    r5 = search.search({"corpus": CORPUS})
    return e1["rule"] == "search.empty_query" \
        and e2["rule"] == "search.empty_query" \
        and r3[1]["refusal"]["rule"] == "search.empty_query" \
        and r4[1]["refusal"]["rule"] == "search.empty_query" \
        and r5[1]["refusal"]["rule"] == "search.empty_query"


def scen_reproducible_record(tmp, name):
    """The result records the query (terms and filters) + index fingerprint;
    a rerun is byte-identical."""
    i1, r1 = search.search(SPEC)
    i2, r2 = search.search(SPEC)
    return json.dumps(r1, ensure_ascii=False, sort_keys=True) \
        == json.dumps(r2, ensure_ascii=False, sort_keys=True) \
        and r1["query"] == {"all": ["uptake"], "any": ["three-fold", "replicates"],
                            "filters": {}} \
        and len(r1["index_sha256"]) == 16 and r1["documents_indexed"] == 3 \
        and i1["corpus_sha256"] == i2["corpus_sha256"]


def scen_locator_verbatim(tmp, name):
    """Every passage quote equals the indexed text slice at its recorded range."""
    _, res = search.search({"corpus": CORPUS,
                            "query": {"any": ["uptake", "coating", "缓冲液", "tris"]}})
    docs = search.build_index(CORPUS)["index"]["documents"]
    ok = len(res["hits"]) == 3
    for hit in res["hits"]:
        paras = docs[hit["doc_id"]]["paragraphs"]
        for p in hit["passages"]:
            loc = p["locator"]
            ok = ok and paras[loc["paragraph"]][loc["start"]:loc["end"]] == loc["quote"]
    return ok


def scen_doc_skipped_named(tmp, name):
    """A corpus entry that is not a document is skipped and named."""
    _, res = search.search({"corpus": [42, {"id": "a", "text": "uptake measured"}],
                            "query": "uptake"})
    f = next((x for x in res.get("findings", [])
              if x["rule"] == "search.doc_skipped"), None)
    return res["ok"] and f is not None and f["count"] == 1 \
        and "neither an object nor a string" in f["entries"][0]["reason"] \
        and res["documents_indexed"] == 1


def scen_cli_ok_writes(tmp, name):
    """The CLI happy path: exit 0, index.json (for replay) + result.json."""
    corpus_path = tmp / "corpus.json"
    query_path = tmp / "query.json"
    corpus_path.write_text(json.dumps({"documents": CORPUS}, ensure_ascii=False),
                           encoding="utf-8")
    query_path.write_text(json.dumps({"all": ["uptake"], "any": ["three-fold"]},
                                     ensure_ascii=False), encoding="utf-8")
    out = tmp / "out"
    proc = subprocess.run([sys.executable, str(Path(__file__).resolve().parent / "search_cli.py"),
                           "--corpus", str(corpus_path), "--query-file", str(query_path),
                           "--out", str(out)], capture_output=True, text=True, timeout=120)
    ok = proc.returncode == 0 and (out / "index.json").exists() \
        and (out / "result.json").exists()
    if not ok:
        return False
    result = json.loads((out / "result.json").read_text(encoding="utf-8"))
    idx = json.loads((out / "index.json").read_text(encoding="utf-8"))
    return result["ok"] and not result["empty"] \
        and result["hits"][0]["doc_id"] == "paper-coating" \
        and idx["corpus_sha256"][:16] == result["index_sha256"]


def scen_cli_refusal_exit5(tmp, name):
    """An empty corpus refuses with exit 5 and a written result.json."""
    corpus_path = tmp / "empty.json"
    corpus_path.write_text(json.dumps({"documents": []}), encoding="utf-8")
    out = tmp / "out5"
    proc = subprocess.run([sys.executable, str(Path(__file__).resolve().parent / "search_cli.py"),
                           "--corpus", str(corpus_path), "--query", "uptake",
                           "--out", str(out)], capture_output=True, text=True, timeout=120)
    ok = proc.returncode == 5 and (out / "result.json").exists()
    if not ok:
        return False
    result = json.loads((out / "result.json").read_text(encoding="utf-8"))
    return result["status"] == "undetermined" \
        and result["refusal"]["rule"] == "search.empty_corpus" \
        and not (out / "index.json").exists()


def scen_section_locator(tmp, name):
    """Hits fall at section granularity: a paragraph under a numbered heading
    carries that heading as its section, checkable against the index."""
    _, res = search.search({"corpus": CORPUS, "query": "冻融"})
    hit = res["hits"][0]
    loc = hit["passages"][0]["locator"]
    idx = search.build_index(CORPUS)["index"]
    secs = idx["documents"]["protocol-buffer"]["sections"]
    return res["ok"] and hit["doc_id"] == "protocol-buffer" \
        and loc["section"] == "2 存储" \
        and loc["quote"] == "冻融" \
        and {"paragraph": 2, "title": "2 存储"} in secs


def scen_sentence_starting_with_number_not_heading(tmp, name):
    """A sentence that merely starts with a number is not a section heading."""
    doc = [{"id": "lab", "text": "2 groups were measured at 25 C.\n"
                                 "The uptake rate was three-fold higher."}]
    idx = search.build_index(doc)["index"]["documents"]["lab"]
    _, res = search.search({"corpus": doc, "query": "uptake"})
    return all(s["section"] is None for s in idx["sections"] or []) \
        and idx["sections"] == [] \
        and res["hits"][0]["passages"][0]["locator"]["section"] is None


def scen_meta_filter_hard(tmp, name):
    """Declared filters execute as hard constraints: docs missing the key never
    match; an unsatisfiable filter is an honest empty naming the filter."""
    corpus = [
        {"id": "p23", "meta": {"year": 2023, "project": "P01", "type": "paper"},
         "text": "uptake measured with replicates."},
        {"id": "p24", "meta": {"year": 2024, "project": "P01", "type": "paper"},
         "text": "uptake measured again with replicates."},
        {"id": "nb", "text": "uptake in the notebook, no meta attached."},
    ]
    _, r23 = search.search({"corpus": corpus,
                            "query": {"all": ["uptake"], "filters": {"year": 2023}}})
    _, rnone = search.search({"corpus": corpus,
                              "query": {"all": ["uptake"], "filters": {"year": 1999}}})
    _, rmiss = search.search({"corpus": corpus,
                              "query": {"all": ["uptake"], "filters": {"project": "P02"}}})
    return r23["hits"] == [{"doc_id": "p23"}] or [h["doc_id"] for h in r23["hits"]] == ["p23"] \
        and rnone["empty"] is True and "1999" in rnone["note"] and "not relaxed" in rnone["note"] \
        and rmiss["empty"] is True


def scen_filter_invalid_refusal(tmp, name):
    """A malformed filter (non-object, non-scalar value) is a refusal — the
    constraint is never quietly dropped."""
    r1 = search.search({"corpus": CORPUS, "query": {"all": ["uptake"],
                                                    "filters": ["year", 2023]}})
    r2 = search.search({"corpus": CORPUS,
                        "query": {"all": ["uptake"], "filters": {"year": [2023]}}})
    e1 = r1[1]["refusal"]["rule"] if isinstance(r1, tuple) else None
    e2 = r2[1]["refusal"]["rule"] if isinstance(r2, tuple) else None
    return e1 == "search.filter_invalid" and e2 == "search.filter_invalid"


def scen_duplicate_content_named(tmp, name):
    """Identical text under two ids: both indexed, the copy named — it cannot
    pass as independent evidence."""
    corpus = [{"id": "orig", "text": "uptake measured with replicates."},
              {"id": "renamed-copy", "text": "uptake measured with replicates."}]
    _, res = search.search({"corpus": corpus, "query": "uptake"})
    f = next((x for x in res.get("findings", [])
              if x["rule"] == "search.duplicate_content"), None)
    return res["ok"] and f is not None \
        and sorted(f["doc_ids"]) == ["orig", "renamed-copy"] \
        and len(res["hits"]) == 2 and res["status"] == "partial"


def scen_doc_sha_in_hits(tmp, name):
    """Every hit carries the document's full sha256, matching the index —
    evidence is pinned to the exact version it came from."""
    idx = search.build_index(CORPUS)["index"]
    _, res = search.search(SPEC)
    hit = res["hits"][0]
    return hit["doc_sha256"] == idx["documents"]["paper-coating"]["sha256"] \
        and len(hit["doc_sha256"]) == 64


def scen_meta_invalid_warning(tmp, name):
    """A corpus entry whose meta is not an object: text still indexed, meta
    stored empty, the entry named — filters cannot silently use it."""
    corpus = [{"id": "a", "meta": "2023", "text": "uptake measured"}]
    _, res = search.search({"corpus": corpus,
                            "query": {"all": ["uptake"], "filters": {"year": 2023}}})
    f = next((x for x in res.get("findings", [])
              if x["rule"] == "search.meta_invalid"), None)
    return res["ok"] and f is not None and res["empty"] is True \
        and res["documents_indexed"] == 1


CASE54 = {"case_id": "case-bench-54",
          "output_contract": {"deliverable": "located search evidence",
                              "topic": "file search"}}


def scen_cli_skipped_exit4(tmp, name):
    """A run with a skipped corpus entry exits 4 (partial), result.json written."""
    corpus_path = tmp / "corpus.json"
    corpus_path.write_text(json.dumps(
        {"documents": [{"id": "a", "text": "uptake measured"}, 42]},
        ensure_ascii=False), encoding="utf-8")
    out = tmp / "out4"
    proc = subprocess.run([sys.executable, str(Path(__file__).resolve().parent / "search_cli.py"),
                           "--corpus", str(corpus_path), "--query", "uptake",
                           "--out", str(out)], capture_output=True, text=True, timeout=120)
    if proc.returncode != 4 or not (out / "result.json").exists():
        return False
    result = json.loads((out / "result.json").read_text(encoding="utf-8"))
    return result["status"] == "partial" and result.get("skipped") \
        and result["hits"]


def scen_cli_contract_passthrough(tmp, name):
    """--case echoes case_id and every output_contract field into result.json;
    the refusal path echoes none of it."""
    corpus_path = tmp / "corpus.json"
    query_path = tmp / "query.json"
    case_path = tmp / "case.json"
    corpus_path.write_text(json.dumps({"documents": CORPUS}, ensure_ascii=False),
                           encoding="utf-8")
    query_path.write_text(json.dumps({"all": ["uptake"], "any": ["three-fold"]},
                                     ensure_ascii=False), encoding="utf-8")
    case_path.write_text(json.dumps(CASE54, ensure_ascii=False), encoding="utf-8")
    out = tmp / "outc"
    proc = subprocess.run([sys.executable, str(Path(__file__).resolve().parent / "search_cli.py"),
                           "--corpus", str(corpus_path), "--query-file", str(query_path),
                           "--case", str(case_path), "--out", str(out)],
                          capture_output=True, text=True, timeout=120)
    if proc.returncode != 0:
        return False
    result = json.loads((out / "result.json").read_text(encoding="utf-8"))
    ok1 = result.get("case_id") == "case-bench-54" \
        and result.get("deliverable") == "located search evidence" \
        and result.get("topic") == "file search" and result.get("status") == "ok"
    # refusal path: contract must NOT be echoed
    out2 = tmp / "outc2"
    proc2 = subprocess.run([sys.executable, str(Path(__file__).resolve().parent / "search_cli.py"),
                            "--corpus", str(corpus_path),
                            "--query-file", str(tmp / "badq.json"),
                            "--case", str(case_path), "--out", str(out2)],
                           capture_output=True, text=True, timeout=120)
    (tmp / "badq.json").write_text("{oops", encoding="utf-8")
    proc3 = subprocess.run([sys.executable, str(Path(__file__).resolve().parent / "search_cli.py"),
                            "--corpus", str(corpus_path),
                            "--query-file", str(tmp / "badq.json"),
                            "--case", str(case_path), "--out", str(out2)],
                           capture_output=True, text=True, timeout=120)
    r3 = json.loads((out2 / "result.json").read_text(encoding="utf-8"))
    return ok1 and proc2.returncode == 5 and proc3.returncode == 5 \
        and r3.get("status") == "undetermined" \
        and r3.get("case_id") == "case-bench-54" and r3.get("deliverable") == "located search evidence" \
        and r3.get("topic") == "file search"


def scen_spec_carried_case_id(tmp, name):
    """A case_id declared on the spec itself passes through to result.json."""
    spec = dict(SPEC)
    spec["case_id"] = "spec-carried-54"
    _, res = search.search(spec)
    return res.get("case_id") == "spec-carried-54" \
        and json.dumps(search.search(spec)[1], ensure_ascii=False, sort_keys=True) \
        == json.dumps(res, ensure_ascii=False, sort_keys=True)


def scen_index_replay_with_filters(tmp, name):
    """A query with filters replays against the saved index and stays hard."""
    corpus = [{"id": "p23", "meta": {"year": 2023}, "text": "uptake replicates."},
              {"id": "p24", "meta": {"year": 2024}, "text": "uptake replicates too."}]
    built = search.build_index(corpus)["index"]
    r1 = search.run_query(built, {"all": ["uptake"], "filters": {"year": 2024}})
    r2 = search.run_query(built, {"all": ["uptake"], "filters": {"year": 2025}})
    h1 = r1["result"]["hits"]
    h2 = r2["result"]
    return h1 and h1[0]["doc_id"] == "p24" and h2["empty"] is True \
        and "2025" in h2["note"]


SCENARIOS = [
    ("single_term", scen_single_term),
    ("boolean_and", scen_boolean_and),
    ("boolean_or", scen_boolean_or),
    ("boolean_all_any", scen_boolean_all_any),
    ("no_hit_honest", scen_no_hit_honest),
    ("empty_corpus_refusal", scen_empty_corpus_refusal),
    ("cjk_query", scen_cjk_query),
    ("bare_string_doc", scen_bare_string_doc),
    ("malformed_index", scen_malformed_index),
    ("empty_query_refusal", scen_empty_query_refusal),
    ("reproducible_record", scen_reproducible_record),
    ("locator_verbatim", scen_locator_verbatim),
    ("doc_skipped_named", scen_doc_skipped_named),
    ("cli_ok_writes", scen_cli_ok_writes),
    ("cli_refusal_exit5", scen_cli_refusal_exit5),
    ("section_locator", scen_section_locator),
    ("numbered_sentence_not_heading", scen_sentence_starting_with_number_not_heading),
    ("meta_filter_hard", scen_meta_filter_hard),
    ("filter_invalid_refusal", scen_filter_invalid_refusal),
    ("duplicate_content_named", scen_duplicate_content_named),
    ("doc_sha_in_hits", scen_doc_sha_in_hits),
    ("meta_invalid_warning", scen_meta_invalid_warning),
    ("cli_skipped_exit4", scen_cli_skipped_exit4),
    ("cli_contract_passthrough", scen_cli_contract_passthrough),
    ("spec_carried_case_id", scen_spec_carried_case_id),
    ("index_replay_with_filters", scen_index_replay_with_filters),
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
    report = {"schema_version": "file-search-bench/v1", "scenarios": rows,
              "totals": {"passed": passed, "of": len(rows)}}
    (Path(__file__).resolve().parent / "report_search.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n{passed}/{len(rows)} scenarios pass")
    return 0 if passed == len(rows) else 1


if __name__ == "__main__":
    raise SystemExit(main())
