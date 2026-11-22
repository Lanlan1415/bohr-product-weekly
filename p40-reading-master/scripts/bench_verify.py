"""Benchmark for the evidence-traceability skill.

One scenario per rule, aligned to the chain the task states:

  claim -> evidence span -> locator -> support verdict -> rationale

plus sub-judgement coverage and counter-evidence. A claim's verdict is only usable if the
whole chain is present, so a missing link is a finding rather than a note.

    python bench_verify.py
"""

from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import sections as S  # noqa: E402

QUOTE = "The porous coating increased the uptake rate three-fold."

BASE = {
    "references": [{"key": "doe2020", "title": "Porous coatings for uptake",
                    "year": 2020}],
    "source_text": QUOTE + " Samples were held at 25 C.",
    "claims": [
        {"claim": "porous coating increases uptake rate",
         "support": "supports",
         "rationale": "the quoted sentence states the rate increase directly",
         "evidence": [{"source": "doe2020", "quote": QUOTE,
                       "locator": "Fig 3b, p.7"}]}
    ],
}


def d(**over):
    s = copy.deepcopy(BASE)
    s.update(over)
    return s


def claim(**over):
    s = d()
    s["claims"] = copy.deepcopy(BASE["claims"])
    s["claims"][0].update(over)
    return s


def span(**over):
    s = d()
    s["claims"] = copy.deepcopy(BASE["claims"])
    s["claims"][0]["evidence"] = [dict(BASE["claims"][0]["evidence"][0], **over)]
    return s


SCEN = [
    ("clean", lambda: (d(), [])),

    # link 1/2: the span itself
    ("no_evidence", lambda: (claim(evidence=[]), ["verify.no_evidence"])),
    ("empty_quote", lambda: (span(quote=""), ["verify.evidence_empty_quote"])),
    ("quote_not_in_source",
     lambda: (span(quote="The coating tripled uptake in every sample."),
              ["verify.quote_not_in_source"])),

    # link 3: locator
    ("no_locator", lambda: (span(locator=""), ["verify.evidence_no_locator"])),
    ("locator_vague", lambda: (span(locator="见上文"), ["verify.evidence_locator_vague"])),

    # link 4/5: verdict and rationale
    ("support_undeclared", lambda: (claim(support=""), ["verify.support_undeclared"])),
    ("rationale_missing", lambda: (claim(rationale=""), ["verify.rationale_missing"])),

    # topic-related vs genuinely supporting
    ("evidence_unrelated",
     lambda: (claim(claim="porous coating raises uptake rate",
                    evidence=[{"source": "doe2020",
                               "quote": "Samples were held at 25 C.",
                               "locator": "p.7"}]),
              ["verify.evidence_unrelated"])),

    # sources
    ("unknown_source", lambda: (span(source="roe2021"), ["verify.unknown_source"])),
    ("metadata_incomplete",
     lambda: (d(references=[{"key": "doe2020", "title": "Porous coatings for uptake"}]),
              ["verify.reference_metadata_incomplete"])),

    # sub-judgements
    ("subjudgement_no_verdict",
     lambda: (claim(claim="coating increases uptake and reduces cost",
                    subjudgements=[{"kind": "fact",
                                    "statement": "coating increases uptake"}]),
              ["verify.subjudgement_verdict_missing"])),
    ("subjudgement_kind_unknown",
     lambda: (claim(subjudgements=[{"kind": "opinion",
                                    "statement": "coating is better",
                                    "support": "supports"}]),
              ["verify.subjudgement_kind_unknown"])),
    ("subjudgements_missing",
     lambda: (claim(claim="coating increases uptake but reduces stability"),
              ["verify.subjudgements_missing"])),

    # counter-evidence
    ("counter_evidence_missing",
     lambda: (claim(contested=True), ["verify.counter_evidence_missing"])),

    ("no_claims", lambda: (d(claims=[]), ["verify.no_claims"])),
]


def main() -> int:
    rows = []
    for name, builder in SCEN:
        spec, expect = builder()
        findings, status, counts = S.run(spec, "claim_verify")
        fired = {f["rule"] for f in findings}
        missing = [r for r in expect if r not in fired]
        spurious = [] if expect else [f["rule"] for f in findings]
        ok = not missing and not spurious
        rows.append({"scenario": name, "expected": expect, "fired": sorted(fired),
                     "missing": missing, "spurious": spurious, "pass": ok,
                     "status": status})
        print(f"{'PASS' if ok else 'FAIL'}  {name:<24} missing={missing} spurious={spurious}")

    passed = sum(1 for r in rows if r["pass"])
    report = {"schema_version": "verify-bench/v1", "scenarios": rows,
              "totals": {"passed": passed, "of": len(rows)},
              "note": ("One scenario per rule, aligned to the claim->span->locator->verdict"
                       "->rationale chain. Clean baselines must report nothing.")}
    (Path(__file__).resolve().parent / "report_verify.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n{passed}/{len(rows)} pass")
    return 0 if passed == len(rows) else 1


if __name__ == "__main__":
    raise SystemExit(main())
