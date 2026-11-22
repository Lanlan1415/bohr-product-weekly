"""Benchmark for the literature-QA skill.

One scenario per rule, aligned to the scoring points this task states:

  an answer to every question, sub-questions covered  -> question_missing, no_answers,
                                                         empty_answer, subquestion_unanswered
  facts, numbers, units matching the source           -> answer_value_not_in_source
                                                         (cross-script numeral bridge)
  a citation locatable AND supportive                 -> citation_no_locator,
                                                         citation_unsupportive,
                                                         unknown_paper, quote_not_in_paper,
                                                         citation_no_paper
  the answer schema the brief fixes                   -> status_invalid, conditions_missing,
                                                         partial_without_gaps, claim_field_missing,
                                                         claim_kind_invalid, claim_no_evidence,
                                                         claim_evidence_incomplete
  explicit handling of thin material and conflicts    -> material_insufficient_unflagged,
                                                         conflict_unhandled, refusal_without_reason
  malformed entries degrade, not crash                -> malformed_answer

    python bench_qa.py
"""

from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import sections as S  # noqa: E402

QUOTE = ("The uptake rate increased with the porous coating. "
         "The increase was three-fold over control.")

BASE = {
    "case_id": "qa-bench-case",
    "questions": ["Q1"],
    "evidence": [{"id": "e1", "quote": QUOTE, "locator": "p.7", "paragraph_id": "P12"},
                 {"id": "e2", "quote": "Samples were held at 25 C.",
                  "locator": "p.6", "paragraph_id": "P9"}],
    "answers": [
        {"question_id": "Q1",
         "question": "what is the uptake rate change",
         "answer": "the uptake rate increased three-fold with the porous coating",
         "conditions": ["porous coating present", "room temperature"],
         "status": "answered",
         "unanswered_parts": [],
         "cites": ["e1"]}
    ],
}


def d(**over):
    s = copy.deepcopy(BASE)
    s.update(over)
    return s


def ans(**over):
    s = copy.deepcopy(BASE)
    s["answers"] = [dict(BASE["answers"][0], **over)]
    return s


def ev(index, **over):
    s = copy.deepcopy(BASE)
    s["evidence"] = copy.deepcopy(BASE["evidence"])
    s["evidence"][index] = dict(BASE["evidence"][index], **over)
    s["answers"] = copy.deepcopy(BASE["answers"])
    return s


CLAIM = {"claim_id": "C1", "text": "the coating tripled the uptake rate",
         "kind": "reported",
         "evidence": [{"paragraph_id": "P12", "quote": "The increase was three-fold over control."}]}

CROSS_ANSWER = "多孔涂层使吸收速率提高了 3 倍。"
CROSS_ANSWER_WRONG = "多孔涂层使吸收速率提高了 5 倍。"


def cross_spec(answer):
    """Chinese answer citing the English passage: the runtime shape of this brief."""
    s = d()
    s["answers"] = [dict(BASE["answers"][0], question="吸收速率变化是多少",
                         answer=answer, conditions=["多孔涂层", "室温"])]
    return s


SCEN = [
    ("clean", lambda: (d(), [])),

    # coverage
    ("no_answers", lambda: (d(answers=[]), ["qa.no_answers"])),
    ("empty_answer", lambda: (ans(answer=""), ["qa.empty_answer"])),
    ("question_missing",
     lambda: (d(questions=["Q1", "Q2", "Q3"]), ["qa.question_missing"])),
    ("questions_all_covered_fp",
     lambda: (d(questions=["Q1"],
                answers=[dict(BASE["answers"][0]),
                         dict(BASE["answers"][0], question_id="Q2")]), [])),
    ("malformed_answer",
     lambda: (d(answers=BASE["answers"] + ["junk-string"]), ["qa.malformed_answer"])),
    ("malformed_evidence",
     lambda: (d(evidence="not-a-list"), ["qa.malformed_evidence"])),
    ("evidence_absent_with_cites",
     lambda: (d(evidence=None), ["qa.malformed_evidence"])),
    ("evidence_absent_claims_only_fp",
     lambda: (d(evidence=None,
                answers=[dict(BASE["answers"][0], cites=[],
                              claims=[{"claim_id": "C1", "text": "the coating tripled "
                                                             "the uptake rate",
                                       "kind": "reported",
                                       "evidence": [{"paragraph_id": "P12",
                                                     "quote": "three-fold over control"}]}])]),
              [])),
    ("subquestion_unanswered",
     lambda: (ans(answer="the uptake rate increased three-fold with the porous coating",
                  cites=["e1"],
                  subquestions=["what is the uptake rate change",
                                "what was the sample temperature during measurement"]),
              ["qa.subquestion_unanswered"])),

    # citations and facts
    ("uncited_answer", lambda: (ans(cites=[]), ["qa.uncited_answer"])),
    ("unknown_evidence", lambda: (ans(cites=["e9"]), ["qa.unknown_evidence"])),
    ("citation_no_locator", lambda: (ev(0, locator="", paragraph_id=""),
                                     ["qa.citation_no_locator"])),
    ("paragraph_id_is_locator_fp", lambda: (ev(0, locator=""), [])),
    ("citation_unsupportive",
     lambda: (ans(answer="the coating was annealed at 500 C", cites=["e1"]),
              ["qa.citation_unsupportive"])),
    ("answer_value_not_in_source",
     lambda: (ans(answer="the uptake rate increased 5-fold with the porous coating",
                  cites=["e1"]),
              ["qa.answer_value_not_in_source"])),
    ("crosslang_value_bridge", lambda: (cross_spec(CROSS_ANSWER), [])),
    ("crosslang_value_wrong", lambda: (cross_spec(CROSS_ANSWER_WRONG),
                                       ["qa.answer_value_not_in_source"])),
    ("crosslang_quotes_cjk",
     lambda: (d(evidence=[{"id": "e1",
                           "quote": "多孔涂层的吸收速率是对照组的三倍。",
                           "locator": "第7页", "paragraph_id": "P12"}],
                answers=[dict(BASE["answers"][0],
                              question="吸收速率变化是多少",
                              answer="多孔涂层使吸收速率提高为对照组的三倍。",
                              conditions=["多孔涂层"])]), [])),

    # the answer schema the brief fixes
    ("status_invalid", lambda: (ans(status="ok"), ["qa.status_invalid"])),
    ("conditions_missing", lambda: (ans(conditions=None), ["qa.conditions_missing"])),
    ("conditions_empty_ok_fp", lambda: (ans(conditions=[]), [])),
    ("partial_without_gaps",
     lambda: (ans(status="partial"), ["qa.partial_without_gaps"])),
    ("partial_with_gaps_fp",
     lambda: (ans(status="partial", unanswered_parts=["the sample temperature"]), [])),

    # claims
    ("claim_clean_fp", lambda: (ans(claims=[CLAIM]), [])),
    ("claim_no_evidence",
     lambda: (ans(claims=[dict(CLAIM, evidence=[])]), ["qa.claim_no_evidence"])),
    ("claim_evidence_incomplete",
     lambda: (ans(claims=[dict(CLAIM, evidence=[{"paragraph_id": "P12"}])]),
              ["qa.claim_evidence_incomplete"])),
    ("claim_evidence_locator_ok_fp",
     lambda: (ans(claims=[dict(CLAIM,
                               evidence=[{"locator": "p.7",
                                          "quote": "The increase was three-fold over control."}])]),
              [])),
    ("claim_kind_invalid",
     lambda: (ans(claims=[dict(CLAIM, kind="opinion")]), ["qa.claim_kind_invalid"])),
    ("claim_inferred_ok_fp", lambda: (ans(claims=[dict(CLAIM, kind="inferred")]), [])),
    ("claim_field_missing",
     lambda: (ans(claims=[{"claim_id": "C1", "text": "no kind given",
                           "evidence": [{"paragraph_id": "P12", "quote": "three-fold"}]}]),
              ["qa.claim_field_missing"])),

    # paper attribution
    ("paper_quote_ok_fp",
     lambda: (d(papers=[{"paper_id": "P1", "text": QUOTE + " More text follows."}]),
              [])),
    ("quote_not_in_paper",
     lambda: (d(papers=[{"paper_id": "P1", "text": "Completely unrelated text about boilers."}],
                evidence=[dict(BASE["evidence"][0], paper_id="P1")]),
              ["qa.quote_not_in_paper"])),
    ("unknown_paper",
     lambda: (d(papers=[{"paper_id": "P1", "text": QUOTE}],
                evidence=[dict(BASE["evidence"][0], paper_id="P9")]),
              ["qa.unknown_paper"])),
    ("citation_no_paper",
     lambda: (d(papers=[{"paper_id": "P1", "text": QUOTE},
                        {"paper_id": "P2", "text": "Other paper text."}]),
              ["qa.citation_no_paper"])),

    # thin material, conflicts, refusals
    ("material_insufficient_unflagged",
     lambda: (d(material_sufficient=False), ["qa.material_insufficient_unflagged"])),
    ("material_refused_ok_fp",
     lambda: (d(material_sufficient=False,
                answers=[dict(BASE["answers"][0], refused=True,
                              reason="the material does not report the control rate")]),
              [])),
    ("refusal_without_reason",
     lambda: (ans(answer="", refused=True), ["qa.refusal_without_reason"])),
    ("refusal_status_bridge",
     lambda: (ans(answer="", status="insufficient_evidence"),
              ["qa.refusal_without_reason"])),
    ("input_error_status_refusal_fp",
     lambda: (ans(answer="", status="input_error", reason="case.json unreadable"), [])),
    ("conflict_unhandled",
     lambda: (d(conflicts=[{"question": 0,
                            "note": "two papers disagree on the magnitude"}]),
              ["qa.conflict_unhandled"])),
    ("conflict_acknowledged_fp",
     lambda: (d(conflicts=[{"question": 0,
                            "note": "two papers disagree on the magnitude"}],
                answers=[dict(BASE["answers"][0],
                              answer="the uptake rate increased three-fold with the "
                                     "porous coating, but the supplied passages conflict "
                                     "on the magnitude; we follow the direct measurement",
                              conditions=["porous coating present"])]),
              [])),
]


def main() -> int:
    rows = []
    for name, builder in SCEN:
        spec, expect = builder()
        findings, status, counts = S.run(spec, "qa")
        fired = {f["rule"] for f in findings}
        missing = [r for r in expect if r not in fired]
        spurious = [] if expect else [f["rule"] for f in findings]
        ok = not missing and not spurious
        rows.append({"scenario": name, "expected": expect, "fired": sorted(fired),
                     "missing": missing, "spurious": spurious, "pass": ok,
                     "status": status})
        print(f"{'PASS' if ok else 'FAIL'}  {name:<32} missing={missing} spurious={spurious}")

    # coverage summary shape: the delivered result.json must show the run shape
    cov = S.qa_coverage(d())
    cov_ok = (cov["counts"]["answered"] == 1 and cov["counts"]["refused"] == 0
              and cov["questions"][0]["question_id"] == "Q1")
    rows.append({"scenario": "coverage_summary_shape", "expected": [], "fired": [],
                 "missing": [], "spurious": [] if cov_ok else
                 ["qa_coverage did not summarise the run shape"], "pass": cov_ok,
                 "status": "clean"})
    print(f"{'PASS' if cov_ok else 'FAIL'}  coverage_summary_shape")
    passed = sum(1 for r in rows if r["pass"])
    report = {"schema_version": "qa-bench/v1", "scenarios": rows,
              "totals": {"passed": passed, "of": len(rows)},
              "note": ("One scenario per rule plus false-positive guards, aligned to the QA "
                       "scoring points. Clean baselines must report nothing.")}
    (Path(__file__).resolve().parent / "report_qa.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n{passed}/{len(rows)} pass")
    return 0 if passed == len(rows) else 1


if __name__ == "__main__":
    raise SystemExit(main())
