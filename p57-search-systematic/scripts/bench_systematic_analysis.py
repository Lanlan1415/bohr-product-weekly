"""Synthetic independent verification for the systematic screening engine."""
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
import systematic as E  # noqa: E402

ROOT = HERE.parent
BASE = json.loads((ROOT / "examples" / "case.json").read_text(encoding="utf-8"))
CLI = HERE / "systematic_cli.py"


def run(case):
    return E.analyze(C.merged_spec(copy.deepcopy(case)), ROOT / "examples")


def invoke(tmp, case):
    path = tmp / "screening.case.json"
    path.write_text(json.dumps(case, ensure_ascii=False), encoding="utf-8")
    out = tmp / "contract-out"
    proc = subprocess.run([sys.executable, "-I", "-X", "utf8", str(CLI), "--case", str(path), "--out", str(out)],
                          capture_output=True, text=True, timeout=90)
    result = json.loads((out / "result.json").read_text(encoding="utf-8")) if (out / "result.json").exists() else {}
    return proc, result, out, path


def protocol_is_replayable_and_complete(tmp, name):
    r = run(BASE)
    queries = r["search_protocol"]["databases_and_queries"]
    required = {"database", "platform", "query_string", "fields", "coverage_from", "coverage_to", "date_searched", "language_limits"}
    return len(queries) == 2 and all(required <= set(q) for q in queries) \
        and all(q["query_string"] for q in queries) and r["protocol_sha256"] == C.fingerprint({
            "criteria": [{k: c[k] for k in ("id", "type", "field", "values", "match", "reason_code")} for c in r["protocol"]["criteria"]],
            "searches": queries, "review_mode": "dual_independent"})


def independent_identification_and_stage_recount(tmp, name):
    r = run(BASE)
    merge = r["search_protocol"]["deduplication"]["merge_log"]
    exact = sum(x["kind"] == "duplicate_removed" for x in merge)
    linked = sum(x["kind"] == "version_linked" for x in merge)
    raw = r["flow_counts"]["identification"]["raw_records"]
    final = r["screening_decisions"]
    included = sum(x["final_decision"] == "include" for x in final)
    excluded_ta = sum(x["title_abstract"]["decision"] == "exclude" for x in final)
    advanced = sum(x["title_abstract"]["decision"] == "include" for x in final)
    ft_excluded = sum(x["title_abstract"]["decision"] == "include" and x["full_text"]["decision"] == "exclude" for x in final)
    return raw - exact - linked == len(final) == 3 and (exact, linked) == (1, 1) \
        and excluded_ta + advanced + sum(x["title_abstract"]["decision"] == "pending" for x in final) == 3 \
        and advanced == included + ft_excluded + sum(x["title_abstract"]["decision"] == "include" and x["full_text"]["decision"] == "pending" for x in final) \
        and (included, excluded_ta, advanced, ft_excluded) == (1, 2, 1, 0) and r["prisma_counts_closed"]


def preprint_and_duplicate_are_not_double_counted(tmp, name):
    r = run(BASE)
    work = next(c for c in r["candidate_set"] if c["cluster_id"] == "work-1")
    kinds = {x["removed_record_id"]: x["kind"] for x in r["search_protocol"]["deduplication"]["merge_log"]}
    return set(work["record_ids"]) == {"rec-001", "rec-001-duplicate", "rec-001-preprint"} \
        and kinds == {"rec-001-duplicate": "duplicate_removed", "rec-001-preprint": "version_linked"}


def similar_title_different_dois_are_not_merged(tmp, name):
    docs, _ = C.normalize_documents([
        {"id": "a", "doi": "10.1/a", "title": "Same intervention trial", "author": "Chen", "year": 2020},
        {"id": "b", "doi": "10.1/b", "title": "Same intervention trial", "author": "Chen", "year": 2020}], ["inline", "inline"])
    clusters, merges, conflicts = E._deduplicate(docs)
    return len(clusters) == 2 and merges == [] and not conflicts


def doi_conflict_is_not_silently_merged(tmp, name):
    docs, _ = C.normalize_documents([
        {"id": "a", "doi": "10.1/a", "title": "Completely separate clinical trial"},
        {"id": "b", "doi": "10.1/a", "title": "Unrelated theoretical taxonomy analysis"}], ["inline", "inline"])
    clusters, merges, conflicts = E._deduplicate(docs)
    return len(clusters) == 2 and merges == [] and conflicts[0]["rule"] == "systematic.identifier_conflict"


def every_final_decision_has_reason_and_source_evidence(tmp, name):
    r = run(BASE)
    for row in r["screening_decisions"]:
        if row["final_decision"] == "exclude" and not row["exclusion_reason_codes"]:
            return False
        if not row["final_evidence"]:
            return False
        for ev in row["final_evidence"]:
            if not ev.get("quote") or not ev.get("locator", {}).get("source_field"):
                return False
    cohort = next(x for x in r["screening_decisions"] if x["cluster_id"] == "10.3000/cohort")
    return "EX-DESIGN" in cohort["exclusion_reason_codes"] \
        and any(e["quote"] == "prospective cohort study" for e in cohort["final_evidence"])


def disagreement_is_adjudicated_not_majority_voted(tmp, name):
    r = run(BASE)
    wrong = next(x for x in r["screening_decisions"] if x["cluster_id"] == "10.3000/wrong-pop")
    adj = wrong["title_abstract"]["adjudication"]
    return wrong["final_decision"] == "exclude" and wrong["title_abstract"]["resolution"] == "third_party_adjudication" \
        and adj["reviewer"] == "reviewer-C" and adj["reason_code"] == "EX-POP" and adj["rationale"] \
        and any(e["quote"] == "hypertension without diabetes" for e in adj["evidence"])


def unresolved_disagreement_stays_pending_and_closed(tmp, name):
    case = copy.deepcopy(BASE)
    case.pop("adjudications")
    r = run(case)
    wrong = next(x for x in r["screening_decisions"] if x["cluster_id"] == "10.3000/wrong-pop")
    return wrong["final_decision"] == "pending" and r["status"] == "review" \
        and r["flow_counts"]["overall"]["pending"] == 1 and r["prisma_counts_closed"] \
        and not r["flow_counts"]["overall"]["process_complete"]


def missing_votes_are_not_fabricated(tmp, name):
    case = copy.deepcopy(BASE)
    case.pop("reviewer_decisions")
    case.pop("adjudications")
    r = run(case)
    return len(r["pending_records"]) == 3 and not r["included_records"] and not r["excluded_records"] \
        and all(x["human_confirmation_required"] for x in r["screening_decisions"]) \
        and r["reviewer_agreement"]["title_abstract"]["agreement_rate"] is None \
        and any(x["rule"] == "systematic.human_review_absent" for x in r["findings"])


def single_reviewer_in_dual_mode_does_not_finalize(tmp, name):
    case = copy.deepcopy(BASE)
    case["reviewer_decisions"] = [v for v in case["reviewer_decisions"] if v["reviewer"] == "reviewer-A"]
    case.pop("adjudications")
    r = run(case)
    return r["status"] == "review" and not r["included_records"] and not r["excluded_records"] \
        and all(x["title_abstract"]["requires_second_reviewer"] for x in r["screening_decisions"])


def criteria_version_drift_triggers_rescreen(tmp, name):
    case = copy.deepcopy(BASE)
    for vote in case["reviewer_decisions"]:
        vote["criteria_version"] = "proto-old"
    r = run(case)
    return r["status"] == "review" and len(r["pending_records"]) == 3 \
        and sum(x["rule"] == "systematic.criteria_version_conflict" for x in r["findings"]) == 8 \
        and r["change_records"][-1]["old_version_votes_requiring_rescreen"] == 8


def reason_disagreement_is_retained_even_when_decision_agrees(tmp, name):
    case = copy.deepcopy(BASE)
    for vote in case["reviewer_decisions"]:
        if vote["record_id"] == "rec-002" and vote["reviewer"] == "reviewer-B":
            vote["reason_code"] = "EX-POP"
    r = run(case)
    row = next(x for x in r["screening_decisions"] if x["cluster_id"] == "10.3000/cohort")
    return row["final_decision"] == "exclude" and r["status"] == "review" \
        and any(x["rule"] == "systematic.reason_code_disagreement" for x in r["findings"]) \
        and set(row["exclusion_reason_codes"]) == {"EX-DESIGN", "EX-POP"}


def unverified_review_quote_invalidates_vote(tmp, name):
    case = copy.deepcopy(BASE)
    case["reviewer_decisions"][0]["evidence"] = ["a fabricated sentence absent from the record"]
    r = run(case)
    return r["status"] == "review" \
        and any(x["rule"] == "systematic.reviewer_evidence_unverified" for x in r["findings"]) \
        and not r["included_records"]


def lexical_absence_does_not_auto_exclude(tmp, name):
    case = copy.deepcopy(BASE)
    case["documents"] = [case["documents"][0]]
    case["documents"][0].pop("design")
    case["documents"][0].pop("population")
    case["reviewer_decisions"] = []
    case["adjudications"] = []
    r = run(case)
    suggestion = r["screening_decisions"][0]["machine_suggestion"]
    return suggestion["decision"] == "pending" and r["screening_decisions"][0]["final_decision"] == "pending" \
        and "AWAIT-EVIDENCE:INC-DESIGN" in suggestion["reason_codes"]


def word_boundaries_and_cjk_quotes(tmp, name):
    text = "细胞焦亡 cat catastrophe Cat"
    assert [text[s:e] for s, e in C.term_occurrences(text, "cat")] == ["cat", "Cat"]
    assert [text[s:e] for s, e in C.term_occurrences(text, "细胞焦亡")] == ["细胞焦亡"]
    return True


def cli_contract_and_determinism(tmp, name):
    proc, r, out_a, path = invoke(tmp, BASE)
    if proc.returncode != 0 or "Traceback" in proc.stderr:
        return False
    fields = C.contract_fields(BASE["output_contract"])[0]
    if any(k not in r for k in fields) or r["case_id"] != BASE["case_id"]:
        return False
    out_b = tmp / "second-out"
    proc2 = subprocess.run([sys.executable, "-I", "-X", "utf8", str(CLI), "--case", str(path), "--out", str(out_b)],
                           capture_output=True, text=True, timeout=90)
    return proc2.returncode == 0 and (out_a / "result.json").read_bytes() == (out_b / "result.json").read_bytes() \
        and (out_a / "flow_audit.json").read_bytes() == (out_b / "flow_audit.json").read_bytes()


SCENARIOS = [
    ("protocol_is_replayable_and_complete", protocol_is_replayable_and_complete),
    ("independent_identification_and_stage_recount", independent_identification_and_stage_recount),
    ("preprint_and_duplicate_are_not_double_counted", preprint_and_duplicate_are_not_double_counted),
    ("similar_title_different_dois_are_not_merged", similar_title_different_dois_are_not_merged),
    ("doi_conflict_is_not_silently_merged", doi_conflict_is_not_silently_merged),
    ("every_final_decision_has_reason_and_source_evidence", every_final_decision_has_reason_and_source_evidence),
    ("disagreement_is_adjudicated_not_majority_voted", disagreement_is_adjudicated_not_majority_voted),
    ("unresolved_disagreement_stays_pending_and_closed", unresolved_disagreement_stays_pending_and_closed),
    ("missing_votes_are_not_fabricated", missing_votes_are_not_fabricated),
    ("single_reviewer_in_dual_mode_does_not_finalize", single_reviewer_in_dual_mode_does_not_finalize),
    ("criteria_version_drift_triggers_rescreen", criteria_version_drift_triggers_rescreen),
    ("reason_disagreement_is_retained_even_when_decision_agrees", reason_disagreement_is_retained_even_when_decision_agrees),
    ("unverified_review_quote_invalidates_vote", unverified_review_quote_invalidates_vote),
    ("lexical_absence_does_not_auto_exclude", lexical_absence_does_not_auto_exclude),
    ("word_boundaries_and_cjk_quotes", word_boundaries_and_cjk_quotes),
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
    C.write_json(HERE / "report_systematic_analysis.json", {
        "schema_version": "systematic-analysis-bench/v1", "fixture": "synthetic_not_official",
        "scenarios": rows, "totals": {"passed": passed, "of": len(rows)},
        "independent_flow_check": "raw=5; duplicate=1; version_link=1; clusters=3; TA=2 excluded+1 advanced; FT=1 included"})
    print(f"\n{passed}/{len(rows)} scenarios pass")
    return 0 if passed == len(rows) else 1


if __name__ == "__main__":
    raise SystemExit(main())
