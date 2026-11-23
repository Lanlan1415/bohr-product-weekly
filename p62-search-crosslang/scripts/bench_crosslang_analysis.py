"""Synthetic verification for controlled cross-language retrieval, evidence and PRF."""
from __future__ import annotations

import copy
import json
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import case_common as C  # noqa: E402
import crosslang as E  # noqa: E402

ROOT = HERE.parent
BASE = json.loads((ROOT / "examples" / "case.json").read_text(encoding="utf-8"))
CLI = HERE / "crosslang_cli.py"


def run(case):
    return E.analyze(C.merged_spec(copy.deepcopy(case)), ROOT / "examples")


def invoke(tmp, case):
    path = tmp / "跨语言.case.json"
    path.write_text(json.dumps(case, ensure_ascii=False), encoding="utf-8")
    out = tmp / "out-a"
    proc = subprocess.run([sys.executable, "-I", "-X", "utf8", str(CLI), "--case", str(path), "--out", str(out)],
                          capture_output=True, text=True, timeout=90)
    result = json.loads((out / "result.json").read_text(encoding="utf-8")) if (out / "result.json").exists() else {}
    return proc, result, out, path


def controlled_terms_queries_and_provenance(tmp, name):
    case = copy.deepcopy(BASE)
    case["target_languages"] = ["pt", "en", "zh"]
    r = run(case)
    zh = next(x for x in r["concept_alignment"] if x["concept_id"] == "cell-death" and x["language"] == "zh")
    expressions = {q["query_id"]: q["expression"] for q in r["multilingual_queries"]}
    return {"细胞焦亡", "细胞炎性坏死", "焦亡"} <= {x["term"] for x in zh["terms"]} \
        and " OR " in expressions["en-cell-death"] and ") AND (" in expressions["en-combined"] \
        and expressions["en-combined"] != expressions["pt-combined"] \
        and any(x.get("translation_service") for x in r["concept_alignment"])


def independent_work_recall_and_gain(tmp, name):
    r = run(BASE)
    refs = {x["ref_id"] for x in BASE["reference_set"]}
    before = set(r["known_set_evaluation"]["before"]["covered_ref_ids"])
    after = set(r["known_set_evaluation"]["after"]["covered_ref_ids"])
    return len(refs) == 3 and len(before) == 2 and len(after) == 3 \
        and before == {"ref-w1", "ref-w2"} and after == refs \
        and len(before) / len(refs) == r["known_set_evaluation"]["before"]["known_set_recall"] \
        and len(after) / len(refs) == r["known_set_evaluation"]["after"]["known_set_recall"] \
        and after - before == {"ref-w3"} and set(r["crosslingual_recall_gain"]["newly_covered_ref_ids"]) == after - before


def exact_duplicate_does_not_inflate_work_or_views(tmp, name):
    r = run(BASE)
    return (r["documents_indexed"], r["unique_input_views_after_exact_dedup"], r["unique_candidate_works"]) == (6, 5, 3) \
        and len(r["exact_duplicate_views"]) == 1 and not r["exact_duplicate_views"][0]["counted_as_new_view"]


def original_translation_and_abstract_versions_remain_distinct(tmp, name):
    r = run(BASE)
    w1 = next(x for x in r["candidate_set"] if x["work_id"] == "work:w1")
    w2 = next(x for x in r["candidate_set"] if x["work_id"] == "work:w2")
    versions = {v["doc_id"]: v["version_kind"] for v in w1["views"] + w2["views"]}
    return versions["w1-pt-original"] == "original_or_supplied_view" \
        and versions["w1-en-publisher-translation"] == "publisher_full_translation" \
        and versions["w2-en-abstract-only"] == "abstract_only" and len(w1["views"]) == 2


def language_routes_queries_to_original_language_views(tmp, name):
    r = run(BASE)
    pt = next(q for q in r["query_results"] if q["query_id"] == "pt-combined")
    en = next(q for q in r["query_results"] if q["query_id"] == "en-combined")
    return {h["doc_id"] for h in pt["hits"]} == {"w1-pt-original", "w2-pt-original"} \
        and {h["doc_id"] for h in en["hits"]} == {"w1-en-publisher-translation", "w2-en-abstract-only", "w3-en-original"} \
        and all(h["body_language"] == "en" for h in en["hits"] for h in h["evidence"])


def every_evidence_quote_is_an_original_exact_slice(tmp, name):
    r = run(BASE)
    raw_by_id = {d["id"]: d for d in BASE["documents"]}
    count = 0
    for row in r["evidence_ledger"]:
        for ev in row["evidence"]:
            doc = raw_by_id[row["doc_id"]]
            loc = ev["locator"]
            source = doc[loc["source_field"]]
            if isinstance(source, list):
                return False
            assert source[loc["start"]:loc["end"]] == ev["quote"]
            assert ev["is_machine_translated_quote"] is False
            assert ev["text_origin"] == next(v for w in r["candidate_set"] for v in w["views"] if v["doc_id"] == row["doc_id"])["version_kind"]
            count += 1
    return count > 20


def query_translation_is_not_an_original_quote(tmp, name):
    r = run(BASE)
    for row in r["evidence_ledger"]:
        for ev in row["evidence"]:
            if ev.get("generated_from_query") or ev["text_origin"] == "machine_translation":
                return False
    return "generated queries" not in r["quotation_policy"] or "never" in r["quotation_policy"]


def duplicate_variants_do_not_change_rrf_scores(tmp, name):
    r1 = run(BASE)
    case = copy.deepcopy(BASE)
    duplicate = copy.deepcopy(case["documents"][1])
    duplicate["id"] = "another-exact-export"
    duplicate["source"] = "yet another export source"
    case["documents"].append(duplicate)
    r2 = run(case)
    return r2["unique_input_views_after_exact_dedup"] == 5 \
        and [(x["work_id"], x["score"]) for x in r1["cross_language_ranking"]] == [(x["work_id"], x["score"]) for x in r2["cross_language_ranking"]]


def prf_is_real_but_isolated_by_default(tmp, name):
    r = run(BASE)
    pt = next(x for x in r["feedback_runs"] if x["language"] == "pt")
    en = next(x for x in r["feedback_runs"] if x["language"] == "en")
    terms = {x["term"].casefold() for x in pt["terms"] + en["terms"]}
    return pt["candidate_doc_ids"] == ["w1-pt-original", "w2-pt-original"] \
        and len(en["candidate_doc_ids"]) == 3 and {"celular", "modelo", "cell", "experimental"} <= terms \
        and "fixture" not in terms and not any(x["accepted"] for x in r["feedback_runs"]) \
        and r["accepted_prf_query_count"] == 0 and all(x["validation_status"].startswith("unverified") for x in (pt, en))


def accepted_prf_changes_only_documented_ranking_branch(tmp, name):
    case = copy.deepcopy(BASE)
    case["pseudo_relevance_feedback"]["accept_prf"] = True
    r1, r2 = run(BASE), run(case)
    return r2["accepted_prf_query_count"] == 2 \
        and all(x["accepted"] for x in r2["feedback_runs"]) \
        and all([h["rank"] for h in run["candidate_ranking"]] == list(range(1, len(run["candidate_ranking"]) + 1))
                and all(h["prf_matched_terms"] for h in run["candidate_ranking"]) for run in r2["feedback_runs"]) \
        and r2["known_set_evaluation"]["after"]["known_set_recall"] == r1["known_set_evaluation"]["after"]["known_set_recall"] \
        and any(x["score"] != y["score"] for x, y in zip(r1["cross_language_ranking"], r2["cross_language_ranking"]))


def cjk_token_boundaries_are_measured_not_unicode_assumed(tmp, name):
    text = "细胞焦亡パイロトーシス"
    tokens = E.tokenize_with_offsets(text)
    chinese = [t for t in tokens if t["kind"] == "cjk_bigram_measured_span"]
    if [(t["surface"], t["start"], t["end"]) for t in chinese] != [("细胞", 0, 2), ("胞焦", 1, 3), ("焦亡", 2, 4)]:
        return False
    katakana = [t for t in tokens if t["surface"] == "パイロトーシス"]
    assert len(katakana) == 1
    assert text[katakana[0]["start"]:katakana[0]["end"]] == "パイロトーシス"
    assert not [t for t in tokens if t["surface"] == "细胞焦亡"]
    return True


def latin_word_boundaries_and_cjk_matching(tmp, name):
    text = "cat catastrophe Cat pyroptosisx pyroptosis 细胞焦亡"
    return [text[s:e] for s, e in C.term_occurrences(text, "cat")] == ["cat", "Cat"] \
        and [text[s:e] for s, e in C.term_occurrences(text, "pyroptosis")] == ["pyroptosis"] \
        and [text[s:e] for s, e in C.term_occurrences(text, "细胞焦亡")] == ["细胞焦亡"]


def missing_translation_never_invents_query(tmp, name):
    case = copy.deepcopy(BASE)
    case["target_languages"] = ["zh"]
    case["concepts"][1]["terms"].pop("zh")
    r = run(case)
    return r["status"] == "review" \
        and any(x["rule"] == "crosslang.term_translation_missing" for x in r["findings"]) \
        and any(x["rule"] == "crosslang.language_query_incomplete" for x in r["findings"]) \
        and not any(q["query_id"] == "zh-combined" for q in r["multilingual_queries"]) \
        and next(x for x in r["concept_alignment"] if x["concept_id"] == "pore-protein" and x["language"] == "zh")["terms"] == []


def declared_language_without_hits_is_not_padded(tmp, name):
    case = copy.deepcopy(BASE)
    case["target_languages"] = ["zh"]
    r = run(case)
    zh = r["language_summary"][0]
    return r["status"] == "review" and zh["work_hits_after_dedup"] == 0 \
        and len(zh["empty_query_ids"]) == 3 and any(x["rule"] == "crosslang.language_has_no_results" for x in r["findings"]) \
        and r["known_set_evaluation"]["before"]["covered_works"] == 2 \
        and r["known_set_evaluation"]["after"]["covered_works"] == 2


def unknown_source_language_is_explicit_review(tmp, name):
    case = copy.deepcopy(BASE)
    case.pop("source_language")
    r = run(case)
    return r["source_language"] == "und" and r["status"] == "review" \
        and any(x["rule"] == "crosslang.source_language_unknown" for x in r["findings"]) \
        and r["known_set_evaluation"]["before"]["known_set_recall"] is None \
        and r["known_set_evaluation"]["marginal_gain"] is None \
        and r["independent_recompute"]["gain_recount"] is None


def unknown_known_set_and_global_recall_not_fabricated(tmp, name):
    case = copy.deepcopy(BASE)
    case.pop("reference_set")
    r = run(case)
    return r["status"] == "review" and r["known_set_evaluation"]["after"]["known_set_recall"] is None \
        and r["known_set_evaluation"]["after"]["absolute_crosslingual_recall"] is None \
        and any(x["rule"] == "crosslang.known_set_missing" for x in r["findings"])


def cli_contract_and_determinism(tmp, name):
    proc, r, out_a, path = invoke(tmp, BASE)
    if proc.returncode != 0 or "Traceback" in proc.stderr:
        return False
    fields = C.contract_fields(BASE["output_contract"])[0]
    if any(k not in r for k in fields) or r["case_id"] != BASE["case_id"]:
        return False
    out_b = tmp / "out-b"
    p2 = subprocess.run([sys.executable, "-I", "-X", "utf8", str(CLI), "--case", str(path), "--out", str(out_b)],
                        capture_output=True, text=True, timeout=90)
    return p2.returncode == 0 and (out_a / "result.json").read_bytes() == (out_b / "result.json").read_bytes() \
        and (out_a / "original_evidence.jsonl").read_bytes() == (out_b / "original_evidence.jsonl").read_bytes()


SCENARIOS = [
    ("controlled_terms_queries_and_provenance", controlled_terms_queries_and_provenance),
    ("independent_work_recall_and_gain", independent_work_recall_and_gain),
    ("exact_duplicate_does_not_inflate_work_or_views", exact_duplicate_does_not_inflate_work_or_views),
    ("original_translation_and_abstract_versions_remain_distinct", original_translation_and_abstract_versions_remain_distinct),
    ("language_routes_queries_to_original_language_views", language_routes_queries_to_original_language_views),
    ("every_evidence_quote_is_an_original_exact_slice", every_evidence_quote_is_an_original_exact_slice),
    ("query_translation_is_not_an_original_quote", query_translation_is_not_an_original_quote),
    ("duplicate_variants_do_not_change_rrf_scores", duplicate_variants_do_not_change_rrf_scores),
    ("prf_is_real_but_isolated_by_default", prf_is_real_but_isolated_by_default),
    ("accepted_prf_changes_only_documented_ranking_branch", accepted_prf_changes_only_documented_ranking_branch),
    ("cjk_token_boundaries_are_measured_not_unicode_assumed", cjk_token_boundaries_are_measured_not_unicode_assumed),
    ("latin_word_boundaries_and_cjk_matching", latin_word_boundaries_and_cjk_matching),
    ("missing_translation_never_invents_query", missing_translation_never_invents_query),
    ("declared_language_without_hits_is_not_padded", declared_language_without_hits_is_not_padded),
    ("unknown_source_language_is_explicit_review", unknown_source_language_is_explicit_review),
    ("unknown_known_set_and_global_recall_not_fabricated", unknown_known_set_and_global_recall_not_fabricated),
    ("cli_contract_and_determinism", cli_contract_and_determinism),
]


def main():
    rows = []
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        for name, fn in SCENARIOS:
            try:
                ok, why = bool(fn(tmp, name)), ""
            except Exception as exc:
                ok, why = False, f"raised {type(exc).__name__}: {exc}"
            rows.append({"scenario": name, "pass": ok, "why": why})
            print(("PASS" if ok else "FAIL") + f"  {name:<65}{why}")
    passed = sum(r["pass"] for r in rows)
    C.write_json(HERE / "report_crosslang_analysis.json", {
        "schema_version": "crosslang-analysis-bench/v1", "fixture": "synthetic_not_official",
        "scenarios": rows, "totals": {"passed": passed, "of": len(rows)},
        "independent_recall_check": "3 works; baseline=2/3; expanded=3/3; gain=1; raw views=6; dedup views=5"})
    print(f"\n{passed}/{len(rows)} scenarios pass")
    return 0 if passed == len(rows) else 1


if __name__ == "__main__":
    raise SystemExit(main())
