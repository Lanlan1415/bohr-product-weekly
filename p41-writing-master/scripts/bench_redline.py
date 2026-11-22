"""Benchmark for the language-polish redline route.

Each scenario plants one rewrite defect between an original and an edited text
(quantity dropped, citation dropped, claim strengthened, term drift) or proves an
FP guard (a faithful polish must stay silent).

    python bench_redline.py
"""

from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import sections as S  # noqa: E402

BASE = {
    "section": "redline_review",
    "original_text": "We measured the uptake rate at 25 C with 6 replicates per arm [1]. "
                     "The porous coating raised the uptake three-fold compared with the bare alloy.",
    "edited_text": "We measured the uptake rate at 25 C with 6 replicates per arm [1]. "
                   "The porous coating raised the uptake three-fold compared with the bare alloy.",
    "glossary": {"uptake rate": {"preferred": "uptake rate", "source_form": "uptake rate",
                                 "variants": ["absorption speed"], "basis": "field convention"}},
}


def scen_clean():
    """A faithful polish that only rewords lightly must stay silent."""
    s = copy.deepcopy(BASE)
    s["edited_text"] = s["edited_text"].replace("raised the uptake three-fold",
                                                "raised the uptake rate three-fold")
    return s, []


def scen_quantity_dropped():
    s = copy.deepcopy(BASE)
    s["edited_text"] = ("We measured the uptake rate with 6 replicates per arm [1]. "
                        "The porous coating raised the uptake three-fold compared with the bare alloy.")
    return s, ["quantity.dropped"]


def scen_citation_dropped():
    s = copy.deepcopy(BASE)
    s["edited_text"] = ("We measured the uptake rate at 25 C with 6 replicates per arm. "
                        "The porous coating raised the uptake three-fold compared with the bare alloy.")
    return s, ["citation.dropped"]


def scen_claim_strengthened():
    s = copy.deepcopy(BASE)
    s["edited_text"] = ("We measured the uptake rate at 25 C with 6 replicates per arm [1]. "
                        "The porous coating proves the uptake increases three-fold versus the bare alloy.")
    return s, ["claim.strengthened"]


def scen_term_drift():
    s = copy.deepcopy(BASE)
    s["edited_text"] = ("We measured the absorption speed at 25 C with 6 replicates per arm [1]. "
                        "The porous coating raised the absorption speed three-fold compared with the bare alloy.")
    return s, ["term.drift"]


def scen_sentence_removed():
    s = copy.deepcopy(BASE)
    s["edited_text"] = "We measured the uptake rate at 25 C with 6 replicates per arm [1]."
    return s, ["sentence.removed"]


def scen_quantity_introduced():
    s = copy.deepcopy(BASE)
    s["edited_text"] = ("We measured the uptake rate at 25 C with 6 replicates per arm [1]. "
                        "The porous coating raised the uptake three-fold at 40 C versus the bare alloy.")
    return s, ["quantity.introduced"]


SCENARIOS = [
    ("clean", scen_clean),
    ("quantity_dropped", scen_quantity_dropped),
    ("citation_dropped", scen_citation_dropped),
    ("claim_strengthened", scen_claim_strengthened),
    ("term_drift", scen_term_drift),
    ("sentence_removed", scen_sentence_removed),
    ("quantity_introduced", scen_quantity_introduced),
]


def run_one(name, builder) -> dict:
    spec, expect = builder()
    findings, status, _ = S.run(copy.deepcopy(spec), "redline_review")
    fired = {f["rule"] for f in findings}
    missing = [x for x in expect if x not in fired]
    spurious = []
    if not expect:
        spurious = [f["rule"] for f in findings if f["severity"] in ("high", "medium")]
    return {"scenario": name, "expected": expect, "fired": sorted(fired),
            "missing": missing, "spurious": spurious, "status": status,
            "pass": not missing and not spurious}


def main() -> int:
    rows = [run_one(n, b) for n, b in SCENARIOS]
    passed = sum(1 for r in rows if r["pass"])
    report = {
        "schema_version": "redline-bench/v1",
        "scenarios": rows,
        "totals": {"passed": passed, "of": len(rows)},
        "note": ("Each scenario plants one rewrite defect between an original and an "
                 "edited text; the faithful-polish baseline must stay silent."),
    }
    (Path(__file__).resolve().parent.parent / "report_redline.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    for r in rows:
        print(("PASS" if r["pass"] else "FAIL") + f"  {r['scenario']:<22}"
              f" missing={r['missing']} spurious={r['spurious']}")
    print(f"\n{passed}/{len(rows)} scenarios pass")
    return 0 if passed == len(rows) else 1


if __name__ == "__main__":
    raise SystemExit(main())
