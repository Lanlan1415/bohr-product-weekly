"""Independent regression bench for academic-search/v2 (not an official score).

python -B -I -X utf8 scripts/bench_academic_v2.py
"""
from __future__ import annotations

import copy
import json
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import academic_engine as E  # noqa: E402
import retrieval_common as C  # noqa: E402

EXAMPLES = HERE.parent / "examples"
REAL = json.loads((EXAMPLES / "records.json").read_text(encoding="utf-8"))


def case(question="蛋白质结构预测", records=None, **kw):
    value = {"case_id": "academic-bench-v2", "research_question": question,
             "records": copy.deepcopy(records if records is not None else [REAL[0]]),
             "top_k": 10, "output_contract": ["检索结果", "证据记录", "状态说明"]}
    value.update(kw)
    return value


def synthetic(identifier, title, abstract, **kw):
    # No DOI or real-work identity is assigned to synthetic records.
    value = {"id": identifier, "source": "explicitly synthetic author metadata",
             "title": title, "abstract": abstract, "authors": ["Synthetic Test Author"],
             "year": 2024, "journal": "Synthetic Bench Record (not a journal claim)",
             "language": "en"}
    value.update(kw)
    return value


def build(value):
    return E.build_result(value, HERE.parent)


def run_scenarios(tmp):
    alpha, attention = REAL[0], REAL[1]

    def clean_baseline():
        result = build(case())
        return (result["status"] == "clean" and result["findings"] == [] and
                len(result["candidate_set"]) == 1 and
                result["candidate_set"][0]["metadata"]["doi"] == "10.1038/s41586-021-03819-2")

    def chinese_cross_language_expansion():
        result = build(case("蛋白质结构预测中，Transformer 与注意力机制有哪些应用？", REAL))
        logs = {x["query_id"]: x for x in result["query_log"]}
        return (len(result["candidate_set"]) == 2 and logs["QBASE"]["local_snapshot_hit_count"] == 0 and
                logs["QEXP"]["local_snapshot_hit_count"] == 2 and
                all(x["execution_status"] == "planned_not_executed" for x in result["query_plan"]["source_queries"]))

    def no_fake_remote_or_recalled_counts():
        result = build(case(records=REAL))
        summary = result["candidate_set_summary"]
        return (summary["source_export_records"] == 3 and summary["deduplicated_works"] == 2 and
                summary["remote_hit_count"] is None and
                all(x["remote_hit_count"] is None for x in result["query_log"]) and
                all(x["remote_hit_count"] is None for x in result["query_plan"]["source_queries"]))

    def duplicate_audit_covers_all_rows():
        result = build(case(records=REAL))
        audit = result["dedup_audit"]
        return (len(audit) == 3 and sum(x["duplicate_of"] is not None for x in audit) == 1 and
                {x["dataset_row"] for x in audit} == {0, 1, 2} and
                len(result["candidate_set"][0]["member_ids"]) == 2)

    def preprint_formal_version_conflict():
        preprint = copy.deepcopy(attention)
        formal = copy.deepcopy(attention)
        formal["id"] = "same-title-formal-metadata-fixture"
        formal["doi"] = None
        formal["publication_status"] = "published"
        formal["journal"] = "Example Proceedings (explicit synthetic metadata)"
        formal["abstract"] = "Explicit synthetic abstract; no real abstract is claimed."
        result = build(case("attention", [preprint, formal]))
        return (len(result["candidate_set"]) == 1 and
                result["candidate_set"][0]["dedup_status"] == "version_or_metadata_conflict" and
                any(f["rule"] == "academic.source_version_conflict" for f in result["findings"]))

    def query_api_shapes_and_boundaries():
        result = build(case(start_date="2020-01-01", end_date="2022-12-31", languages=["en"]))
        plans = {x["source"]: x for x in result["query_plan"]["source_queries"]}
        oa, cr, ep = plans["OpenAlex"], plans["Crossref"], plans["Europe PMC"]
        return (oa["parameters"]["filter"].startswith("from_publication_date:2020-01-01,to_publication_date:2022-12-31") and
                "language:en" in oa["parameters"]["filter"] and oa["parameters"]["cursor"] == "*" and
                cr["parameters"]["query.bibliographic"] and "from-pub-date:2020-01-01" in cr["parameters"]["filter"] and
                "TITLE_ABS:" in ep["parameters"]["query"] and "FIRST_PDATE:[2020-01-01 TO 2022-12-31]" in ep["parameters"]["query"] and
                all(x["remote_hit_count"] is None for x in plans.values()))

    def date_and_unknown_year_boundary():
        unknown = synthetic("unknown-year", "Protein folding with missing year", "missing year", year=None)
        result = build(case(records=[alpha, attention, unknown], start_date="2020", end_date="2022"))
        ids = [x["record_id"] for x in result["candidate_set"]]
        reasons = [x for log in result["query_log"] for x in log["excluded_from_boundary_or_boolean"]]
        return ids == ["crossref-alphafold"] and any("missing year" in x["reason"] for x in reasons)

    def all_any_not_not_relaxed():
        good = synthetic("s1", "Protein attention test", "sensitive example about protein and attention")
        no_any = synthetic("s2", "Protein folding test", "protein only")
        no_all = synthetic("s3", "Attention test", "attention only")
        value = case(question="", records=[good, no_any, no_all],
                     queries=[{"query_id": "STRICT", "query": {"all": ["protein"], "any": ["attention"], "not": ["secret"]}}])
        result = build(value)
        strict = next(x for x in result["query_log"] if x["query_id"] == "STRICT")
        return (strict["local_snapshot_hit_work_ids"] and
                [item["record_id"] for item in result["candidate_set"]] == ["s1"])

    def not_gate_excludes_without_padding():
        good = synthetic("s1", "Protein attention test", "secret synthetic marker")
        result = build(case(question="", records=[good],
                            queries=[{"query_id": "NOT", "query": {"all": ["protein"], "any": ["attention"], "not": ["secret"]}}]))
        not_log = next(x for x in result["query_log"] if x["query_id"] == "NOT")
        return not_log["local_snapshot_hit_count"] == 0 and "empty_result" in not_log and not_log["remote_hit_count"] is None

    def separate_relevance_metadata_source():
        common = synthetic("same-text", "Explicit common title", "protein folding common abstract")
        one = C.load_records({"records": [dict(common, source="Crossref supplied fixture")]}, HERE.parent)
        two = C.load_records({"records": [dict(common, source="unnamed local fixture")]}, HERE.parent)
        # Compare identical fields after changing only provenance, not its question match.
        w1, _, _ = C.deduplicate(one)
        w2, _, _ = C.deduplicate(two)
        i1, i2 = C.BM25Index(w1), C.BM25Index(w2)
        s1, s2 = i1.score(w1[0]["work_id"], ["protein folding"]), i2.score(w2[0]["work_id"], ["protein folding"])
        return s1["bm25"] == s2["bm25"] and w1[0]["source_quality"]["score"] != w2[0]["source_quality"]["score"]

    def openalex_inverted_abstract_and_authors():
        raw = {"id": "W-synthetic", "display_name": "OpenAlex adapter fixture",
               "authorships": [{"author": {"display_name": "Fixture Author"}}],
               "abstract_inverted_index": {"protein": [2], "folding": [3], "Synthetic": [0], "fixture": [1]}}
        record = C.normalize_record(raw, 0, "inline")
        return record["fields"]["abstract"] == "Synthetic fixture protein folding" and record["metadata"]["authors"] == ["Fixture Author"]

    def crossref_and_epmc_loaders():
        crossref = tmp / "crossref.json"
        crossref.write_text(json.dumps({"message": {"items": [alpha]}}), encoding="utf-8")
        europe = tmp / "epmc.json"
        europe.write_text(json.dumps({"resultList": {"result": [{"id": "fixture-pmid", "title": "Adapter fixture",
                                                                  "abstractText": "synthetic adapter text"}]}}), encoding="utf-8")
        return len(C.read_material(crossref)) == 1 and C.read_material(europe)[0]["title"] == "Adapter fixture"

    def ris_loader_without_fake_ids():
        path = tmp / "fixture.ris"
        path.write_text("TY  - JOUR\nTI  - Explicit RIS fixture\nAU  - Test Author\nAB  - protein folding\nPY  - 2024\nER  -\n", encoding="utf-8")
        rows = C.read_material(path)
        return rows[0]["title"] == "Explicit RIS fixture" and rows[0]["doi"] if False else (
            rows[0]["title"] == "Explicit RIS fixture" and "doi" not in rows[0] and rows[0]["authors"] == ["Test Author"])

    def verbatim_evidence_locators():
        result = build(case(records=REAL))
        records = C.load_records({"records": REAL}, HERE.parent)
        works, _, _ = C.deduplicate(records)
        by_id = {w["work_id"]: w for w in works}
        checks = []
        for item in result["candidate_set"]:
            for ev in item["evidence"]:
                loc = ev["locator"]
                text = by_id[item["work_id"]]["fields"][ev["field"]]
                checks.append(ev["status"] == "verbatim" and text[loc["start"]:loc["end"]] == ev["quote"])
        return bool(checks) and all(checks)

    def ranking_tie_and_topk():
        one = synthetic("tie-1", "A deterministic title", "common topic with identical lexical evidence")
        two = synthetic("tie-2", "B deterministic title", "common topic with identical lexical evidence")
        result = build(case("common", [two, one], top_k=1))
        ranks = [x["record_id"] for x in result["candidate_set"]]
        return ranks == ["tie-1", "tie-2"] and [x["in_top_k"] for x in result["candidate_set"]] == [True, False]

    def candidate_metadata_missing_is_review():
        no_abstract = synthetic("missing-abstract", "Protein folding fixture", "", journal=None)
        result = build(case(records=[no_abstract]))
        candidate = result["candidate_set"][0]
        return (result["status"] == "review" and candidate["metadata_completeness"]["score"] < 1 and
                "abstract" in candidate["metadata_completeness"]["missing_fields"] and "bm25" in candidate["relevance"])

    def candidate_controlled_terms_not_executed():
        result = build(case("随机对照试验", [synthetic("rct-fixture", "Randomized trial fixture", "randomized trial")]))
        pending = result["query_plan"]["controlled_vocabulary_pending_review"]
        return bool(pending) and all(p["execution_status"] == "not_executed_requires_vocabulary_review" for p in pending) and all(
            "MeSH" not in p["parameters"].get("query", "") for p in result["query_plan"]["source_queries"] if p["source"] == "Europe PMC")

    def contract_shapes_and_engine_priority():
        value = case(output_contract={"检索结果": {}, "证据记录": {}, "custom_note": {}, "status": {}, "unavailable": {}},
                     custom_note="caller provenance retained", status="fabricated-clean")
        result = build(value)
        return (result["case_id"] == "academic-bench-v2" and result["status"] == "review" and
                result["custom_note"] == "caller provenance retained" and result["unavailable"] is None and
                "unavailable" in result["output_contract_fields"])

    def engine_replay_is_byte_deterministic():
        value = case("蛋白质结构预测中，Transformer 与注意力机制有哪些应用？", REAL)
        first, second = build(value), build(value)
        return C.dumps(first) == C.dumps(second)

    def invalid_doi_is_not_verified_or_dedup_key():
        one = synthetic("bad-doi-1", "Protein fixture A", "protein folding", doi="not-a-doi")
        two = synthetic("bad-doi-2", "Protein fixture B", "protein folding", doi="not-a-doi")
        records = C.load_records({"records": [one, two]}, HERE.parent)
        works, _, _ = C.deduplicate(records)
        result = build(case(records=[one, two]))
        return len(works) == 2 and all(not r["doi_valid_syntax"] for r in records) and any(
            f["rule"] == "academic.doi_syntax_invalid" for f in result["findings"])

    def access_restriction_does_not_serialize_body():
        blocked = synthetic("restricted", "Protein folding restricted fixture", "SECRET BODY MUST NOT APPEAR", access="restricted")
        result = build(case(records=[blocked, alpha]))
        serialized = json.dumps(result, ensure_ascii=False)
        return "SECRET BODY MUST NOT APPEAR" not in serialized and any(
            f["rule"] == "academic.access_blocked" for f in result["findings"])

    scenarios = [
        ("clean_baseline_zero_findings", clean_baseline),
        ("pure_chinese_cross_language_expansion", chinese_cross_language_expansion),
        ("no_fake_remote_or_recalled_counts", no_fake_remote_or_recalled_counts),
        ("duplicate_audit_covers_all_rows", duplicate_audit_covers_all_rows),
        ("preprint_formal_version_conflict", preprint_formal_version_conflict),
        ("query_api_shapes_and_boundaries", query_api_shapes_and_boundaries),
        ("date_and_unknown_year_boundary", date_and_unknown_year_boundary),
        ("all_any_gate_not_relaxed", all_any_not_not_relaxed),
        ("not_gate_excludes_without_padding", not_gate_excludes_without_padding),
        ("relevance_metadata_source_separate", separate_relevance_metadata_source),
        ("openalex_inverted_abstract_and_authors", openalex_inverted_abstract_and_authors),
        ("crossref_and_epmc_loaders", crossref_and_epmc_loaders),
        ("ris_loader_no_fake_doi", ris_loader_without_fake_ids),
        ("verbatim_evidence_locators", verbatim_evidence_locators),
        ("ranking_tie_and_topk", ranking_tie_and_topk),
        ("candidate_metadata_missing_is_review", candidate_metadata_missing_is_review),
        ("candidate_controlled_not_executed", candidate_controlled_terms_not_executed),
        ("contract_shapes_engine_priority", contract_shapes_and_engine_priority),
        ("engine_replay_byte_deterministic", engine_replay_is_byte_deterministic),
        ("invalid_doi_not_dedup_key", invalid_doi_is_not_verified_or_dedup_key),
        ("access_restriction_body_omitted", access_restriction_does_not_serialize_body),
    ]
    rows = []
    for name, fn in scenarios:
        try:
            ok, why = bool(fn()), ""
        except Exception as exc:
            ok, why = False, f"{type(exc).__name__}: {exc}"
        rows.append({"scenario": name, "pass": ok, "why": why})
        print(("PASS" if ok else "FAIL") + f"  {name:<44}" + why)
    return rows


def main():
    with tempfile.TemporaryDirectory() as td:
        rows = run_scenarios(Path(td))
    passed = sum(x["pass"] for x in rows)
    report = {"schema_version": "academic-search-v2-bench/v1", "official_score": False,
              "inputs": "public real DOI metadata plus explicitly synthetic no-DOI fixtures",
              "scenarios": rows, "totals": {"passed": passed, "of": len(rows)}}
    (HERE / "report_academic_v2.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"\n{passed}/{len(rows)} scenarios pass")
    return 0 if passed == len(rows) else 1


if __name__ == "__main__":
    raise SystemExit(main())
