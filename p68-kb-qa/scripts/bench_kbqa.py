"""Benchmark for the knowledge-base QA skill.

One scenario per rule, aligned to the scoring points this task states:

  an answer to every knowledge-base question        -> no_answers, empty_answer,
                                                       refusal_without_reason
  sub-questions covered                             -> subquestion_unanswered
  values traced to the cited KB entry               -> answer_value_not_in_source
  a citation locatable AND supportive               -> citation_no_locator,
                                                       citation_unsupportive
  an entry outside the audited knowledge base       -> uncited_answer, unknown_evidence
  thin material and version conflicts handled       -> material_insufficient_unflagged,
                                                       conflict_unhandled

    python bench_kbqa.py
"""

from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import sections as S  # noqa: E402

QUOTE = ("Dataset v2 raised the reported uptake to three-fold over control. "
         "v1 reported two-fold; v2 supersedes it.")

BASE = {
    "evidence": [
        {"id": "kb-0217",
         "quote": QUOTE,
         "locator": "datasets/uptake-2024/README.md @v2 §3"},
        {"id": "kb-0088",
         "quote": "All samples were held at 25 C during measurement.",
         "locator": "protocols/sample-handling.md @v1 §2"},
    ],
    "answers": [
        {"question": "知识库中记录的摄取率提升是多少",
         "answer": "v2 记录的摄取率提升是三倍（three-fold），并注明 v1 的两倍记录已被 v2 取代",
         "cites": ["kb-0217"]}
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
    ("unknown_evidence", lambda: (ans(cites=["kb-9999"]), ["qa.unknown_evidence"])),

    ("citation_no_locator", lambda: (ev(0, locator=""), ["qa.citation_no_locator"])),
    # same-script pair: an English answer against the English entry text. A Chinese answer
    # citing an English entry is checked anchor-only (see SKILL.md Limits), so the
    # lexical-support gate is only exercised within one script.
    ("citation_unsupportive",
     lambda: (ans(answer="the samples were annealed at 500 C", cites=["kb-0217"]),
              ["qa.citation_unsupportive"])),

    ("answer_value_not_in_source",
     lambda: (ans(answer="the v2 entry reports a 5-fold uptake increase", cites=["kb-0217"]),
              ["qa.answer_value_not_in_source"])),

    ("subquestion_unanswered",
     lambda: (ans(answer="v2 记录的摄取率提升是三倍（three-fold）", cites=["kb-0217"],
                  subquestions=["知识库中记录的摄取率提升是多少",
                                "样品测量时的保存温度是多少"]),
              ["qa.subquestion_unanswered"])),

    ("material_insufficient_unflagged",
     lambda: (d(material_sufficient=False), ["qa.material_insufficient_unflagged"])),
    ("conflict_unhandled",
     lambda: (d(conflicts=[{"question": 0,
                            "note": "v1 与 v2 两个版本对摄取率提升的记录不一致"}]),
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
    report = {"schema_version": "kbqa-bench/v1", "scenarios": rows,
              "totals": {"passed": passed, "of": len(rows)},
              "note": ("One scenario per rule, aligned to the KB-QA scoring points. Clean "
                       "baselines must report nothing.")}
    (Path(__file__).resolve().parent / "report_kbqa.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n{passed}/{len(rows)} pass")
    return 0 if passed == len(rows) else 1


if __name__ == "__main__":
    raise SystemExit(main())
