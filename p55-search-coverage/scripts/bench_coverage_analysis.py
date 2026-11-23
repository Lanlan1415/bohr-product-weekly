"""Independent synthetic benches for the specialist coverage workflow.

These are not organizer cases or answer keys.  The fixture intentionally has a
computable 2/4 -> 3/4 known-set recall so recall and marginal gain can be
re-derived independently of the narrative.
"""
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
import coverage as E  # noqa: E402

ROOT = HERE.parent
CASE = json.loads((ROOT / "examples" / "case.json").read_text(encoding="utf-8"))
CLI = HERE / "coverage_cli.py"


def analyze(case):
    spec = C.merged_spec(copy.deepcopy(case))
    # The example's supplementary records are inline; this helper just isolates mutations.
    return E.analyze(spec, ROOT / "examples")


def invoke(tmp: Path, case: dict, name="case.json"):
    path = tmp / name
    path.write_text(json.dumps(case, ensure_ascii=False), encoding="utf-8")
    out = tmp / (path.stem + "-out")
    proc = subprocess.run([sys.executable, "-I", "-X", "utf8", str(CLI), "--case", str(path),
                           "--out", str(out)], capture_output=True, text=True, timeout=90)
    result = json.loads((out / "result.json").read_text(encoding="utf-8")) if (out / "result.json").exists() else {}
    return proc, result, out


def exact_identifier_and_source_slices(tmp, name):
    r = analyze(CASE)
    alpha = next(x for x in r["coverage_matrix"] if x["ref_id"] == "ref-alpha")
    if alpha["match"]["method"] != "identifier_exact":
        return False
    docs, _ = C.load_document_records(C.merged_spec(CASE), ROOT / "examples")
    normalized, _ = C.normalize_documents(docs, ["inline"] * len(docs))
    supplemental, _ = C.normalize_documents(CASE["supplementary_documents"],
                                             ["inline"] * len(CASE["supplementary_documents"]))
    normalized.extend(supplemental)
    for hit in r["coverage_matrix"]:
        for ev in hit["evidence"]:
            doc = next(d for d in normalized if d["doc_id"] == ev["locator"]["document_id"])
            unit = doc["units"][ev["locator"]["unit"]]
            loc = ev["locator"]
            if unit["text"][loc["start"]:loc["end"]] != ev["quote"]:
                return False
    return bool(alpha["evidence"])


def recall_and_miss_are_independently_closed(tmp, name):
    r = analyze(CASE)
    m = r["coverage_metrics"]
    ledger = r["coverage_matrix"]
    independently_covered = {row["ref_id"] for row in ledger if row["covered"]}
    return (independently_covered == {"ref-alpha", "ref-beta", "ref-gamma"}
            and m["covered_references"] / m["reference_total_after_internal_dedup"] == 0.75
            and m["known_set_recall"] == 0.75
            and [x["ref_id"] for x in r["missed_references"]] == ["ref-missing"]
            and r["independent_recompute"]["closure_holds"])


def supplementary_gain_is_set_difference_not_rewrite(tmp, name):
    r = analyze(CASE)
    s = r["supplementary_search"]
    before_ids = {"ref-alpha", "ref-beta"}
    after_ids = {x["ref_id"] for x in r["coverage_matrix"] if x["covered"]}
    expected = sorted(after_ids - before_ids)
    return (s["before"]["known_set_recall"] == 0.5 and s["after"]["known_set_recall"] == 0.75
            and s["newly_covered_ref_ids"] == expected == ["ref-gamma"]
            and s["marginal_gain"] == 1 and s["miss_reduction"] == 1)


def no_supplement_is_zero_gain(tmp, name):
    case = copy.deepcopy(CASE)
    case.pop("supplementary_documents")
    case["iterations"] = case["iterations"][:1]
    r = analyze(case)
    s = r["supplementary_search"]
    return s["basis"] == "single_snapshot_no_supplementary_round" and s["marginal_gain"] == 0 \
        and not s["supplementary_rounds"] and s["newly_covered_ref_ids"] == []


def miss_attribution_separates_verified_window_and_lexical_clue(tmp, name):
    r = analyze(CASE)
    miss = r["missed_references"][0]
    reasons = miss["miss_analysis"]["reasons"]
    window = next(x for x in reasons if x["reason_code"] == "time_window_excludes_reference")
    assert window["certainty"] == "verified_from_declared_protocol"
    lexical = next(x for x in reasons if x["reason_code"] == "query_lacks_reference_title_discriminators")
    return lexical["certainty"] == "lexical_clue_not_sole_cause" \
        and any(q["fields"] == ["Title", "Abstract"] for q in miss["attempted_queries"]) \
        and miss["miss_analysis"]["primary_reason"] == "time_window_excludes_reference"


def unknown_global_and_precision_are_null(tmp, name):
    r = analyze(CASE)
    m = r["coverage_metrics"]
    return m["absolute_coverage"] is None and m["candidate_precision"] is None \
        and any(x["rule"] == "coverage.precision_not_estimable" for x in r["findings"])


def precision_only_with_complete_labels(tmp, name):
    case = copy.deepcopy(CASE)
    case["candidate_labels_complete"] = True
    case["candidate_relevance_judgements"] = [
        {"doc_id": "cand-alpha-crossref", "relevant": True},
        {"doc_id": "cand-beta", "relevant": True},
        {"doc_id": "cand-distractor", "relevant": False},
        {"doc_id": "cand-gamma-publisher", "relevant": True},
    ]
    r = analyze(case)
    return r["coverage_metrics"]["candidate_precision"] == 0.75 \
        and r["coverage_metrics"]["precision_denominator"] == 4


def title_match_requires_corroboration(tmp, name):
    case = copy.deepcopy(CASE)
    # Remove every exact identifier for gamma and let only the supplementary title match.
    for ref in case["reference_set"]:
        if ref["ref_id"] == "ref-gamma":
            ref.pop("doi")
    for doc in case["supplementary_documents"]:
        doc.pop("doi")
    r = analyze(case)
    gamma = next(x for x in r["coverage_matrix"] if x["ref_id"] == "ref-gamma")
    if not gamma["covered"] or gamma["match"]["method"] != "title_exact_with_corroboration":
        return False
    case["supplementary_documents"][0]["year"] = 1999
    case["supplementary_documents"][0]["author"] = "Different Person"
    r2 = analyze(case)
    gamma2 = next(x for x in r2["coverage_matrix"] if x["ref_id"] == "ref-gamma")
    return not gamma2["covered"]


def near_title_without_author_or_year_waits_for_adjudication(tmp, name):
    case = copy.deepcopy(CASE)
    ref = case["reference_set"][0]
    ref.pop("doi")
    ref.pop("author")
    ref.pop("year")
    doc = case["documents"][0]
    doc.pop("DOI")
    doc.pop("authorString")
    doc.pop("year")
    r = analyze(case)
    row = r["coverage_matrix"][0]
    return row["status"] == "awaiting_adjudication" and not row["covered"] \
        and any(x["rule"] == "coverage.match_adjudication_required" for x in r["findings"])


def unavailable_reference_stays_in_denominator(tmp, name):
    r = analyze(CASE)
    gamma = next(x for x in r["coverage_matrix"] if x["ref_id"] == "ref-gamma")
    return gamma["reference"]["availability"] == "no_full_text" \
        and r["reference_freeze"]["denominator_rule"].find("unavailable") >= 0


def cjk_and_latin_boundaries_have_verified_offsets(tmp, name):
    cjk = "细胞焦亡由gasdermin介导，细胞凋亡是另一过程。"
    spans = C.term_occurrences(cjk, "细胞焦亡")
    if len(spans) != 1 or cjk[slice(*spans[0])] != "细胞焦亡":
        return False
    prefix_spans = C.term_occurrences(cjk, "细胞焦")
    if [cjk[s:e] for s, e in prefix_spans] != ["细胞焦"]:
        return False
    latin = "cat catastrophe Cat concatenate"
    return [latin[s:e] for s, e in C.term_occurrences(latin, "cat")] == ["cat", "Cat"]


def cli_contract_and_idempotency(tmp, name):
    proc, result, out_a = invoke(tmp, CASE)
    if proc.returncode != 0 or result["status"] != "clean" or "Traceback" in proc.stderr:
        return False
    names = C.contract_fields(CASE["output_contract"])[0]
    if any(name not in result for name in names) or result["case_id"] != CASE["case_id"]:
        return False
    second = tmp / "repeat-out"
    proc2 = subprocess.run([sys.executable, "-I", "-X", "utf8", str(CLI), "--case", str(tmp / "case.json"),
                            "--out", str(second)], capture_output=True, text=True, timeout=90)
    return proc2.returncode == 0 \
        and (out_a / "result.json").read_bytes() == (second / "result.json").read_bytes() \
        and (out_a / "coverage_matrix.jsonl").read_bytes() == (second / "coverage_matrix.jsonl").read_bytes()


SCENARIOS = [
    ("exact_identifier_and_source_slices", exact_identifier_and_source_slices),
    ("recall_and_miss_are_independently_closed", recall_and_miss_are_independently_closed),
    ("supplementary_gain_is_set_difference_not_rewrite", supplementary_gain_is_set_difference_not_rewrite),
    ("no_supplement_is_zero_gain", no_supplement_is_zero_gain),
    ("miss_attribution_separates_verified_window_and_lexical_clue", miss_attribution_separates_verified_window_and_lexical_clue),
    ("unknown_global_and_precision_are_null", unknown_global_and_precision_are_null),
    ("precision_only_with_complete_labels", precision_only_with_complete_labels),
    ("title_match_requires_corroboration", title_match_requires_corroboration),
    ("near_title_without_author_or_year_waits_for_adjudication", near_title_without_author_or_year_waits_for_adjudication),
    ("unavailable_reference_stays_in_denominator", unavailable_reference_stays_in_denominator),
    ("cjk_and_latin_boundaries_have_verified_offsets", cjk_and_latin_boundaries_have_verified_offsets),
    ("cli_contract_and_idempotency", cli_contract_and_idempotency),
]


def main():
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
            print(("PASS" if ok else "FAIL") + f"  {name:<60}{why}")
    passed = sum(x["pass"] for x in rows)
    report = {"schema_version": "coverage-analysis-bench/v1", "fixture": "synthetic_not_official",
              "scenarios": rows, "totals": {"passed": passed, "of": len(rows)},
              "independent_recall_check": "before=2/4, after=3/4, marginal_gain=1"}
    C.write_json(HERE / "report_coverage_analysis.json", report)
    print(f"\n{passed}/{len(rows)} scenarios pass")
    return 0 if passed == len(rows) else 1


if __name__ == "__main__":
    raise SystemExit(main())
