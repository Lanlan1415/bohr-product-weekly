"""Benchmark for the literature-QA skill.

One scenario per rule, aligned to the scoring points this task states:

  an answer to every question, sub-questions covered  -> no_answers, empty_answer,
                                                         subquestion_unanswered
  facts, numbers, units matching the source           -> answer_value_not_in_source
  a citation locatable AND supportive                 -> citation_no_locator,
                                                         citation_unsupportive
  explicit handling of thin material and conflicts    -> material_insufficient_unflagged,
                                                         conflict_unhandled

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
    "evidence": [{"id": "e1", "quote": QUOTE, "locator": "p.7"},
                 {"id": "e2", "quote": "Samples were held at 25 C.",
                  "locator": "p.6"}],
    "answers": [
        {"question": "what is the uptake rate change",
         "answer": "the uptake rate increased three-fold with the porous coating",
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


SCEN = [
    ("clean", lambda: (d(), [])),

    ("no_answers", lambda: (d(answers=[]), ["qa.no_answers"])),
    ("empty_answer", lambda: (ans(answer=""), ["qa.empty_answer"])),
    ("refusal_without_reason",
     lambda: (ans(answer="", refused=True), ["qa.refusal_without_reason"])),
    ("uncited_answer", lambda: (ans(cites=[]), ["qa.uncited_answer"])),
    ("unknown_evidence", lambda: (ans(cites=["e9"]), ["qa.unknown_evidence"])),

    ("citation_no_locator", lambda: (ev(0, locator=""), ["qa.citation_no_locator"])),
    ("citation_unsupportive",
     lambda: (ans(answer="the coating was annealed at 500 C", cites=["e1"]),
              ["qa.citation_unsupportive"])),

    ("answer_value_not_in_source",
     lambda: (ans(answer="the uptake rate increased 5-fold with the porous coating",
                  cites=["e1"]),
              ["qa.answer_value_not_in_source"])),

    ("subquestion_unanswered",
     lambda: (ans(answer="the uptake rate increased three-fold with the porous coating",
                  cites=["e1"],
                  subquestions=["what is the uptake rate change",
                                "what was the sample temperature during measurement"]),
              ["qa.subquestion_unanswered"])),

    ("material_insufficient_unflagged",
     lambda: (d(material_sufficient=False), ["qa.material_insufficient_unflagged"])),
    ("conflict_unhandled",
     lambda: (d(conflicts=[{"question": 0,
                            "note": "two papers disagree on the magnitude"}]),
              ["qa.conflict_unhandled"])),
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
        print(f"{'PASS' if ok else 'FAIL'}  {name:<30} missing={missing} spurious={spurious}")

    passed = sum(1 for r in rows if r["pass"])
    report = {"schema_version": "qa-bench/v1", "scenarios": rows,
              "totals": {"passed": passed, "of": len(rows)},
              "note": ("One scenario per rule, aligned to the QA scoring points. Clean "
                       "baselines must report nothing.")}
    (Path(__file__).resolve().parent / "report_qa.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n{passed}/{len(rows)} pass")
    return 0 if passed == len(rows) else 1


if __name__ == "__main__":
    raise SystemExit(main())
