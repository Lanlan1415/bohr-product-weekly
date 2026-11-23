"""Paired defect/FP-guard scenarios for the reading-master evidence additions.

Every new rule has one planted defect and one independent clean guard. Guards assert
zero findings, not merely absence of the new rule, so a detector cannot pass by making
the baseline noisy.
"""

from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import sections as S  # noqa: E402
import writing as W  # noqa: E402
from bench_sections import BASE  # noqa: E402


def alter(base, fn):
    spec = copy.deepcopy(base)
    fn(spec)
    return spec


def duplicate_extract(spec):
    spec["conclusions"].append(copy.deepcopy(spec["conclusions"][0]))


def bad_condition(spec):
    spec["conclusions"][0]["condition"] = "每组 n = 6，30 °C，单一厚度"


def no_verify_source(spec):
    spec["source_text"] = ""


COUNTER = alter(BASE["claim_verify"], lambda s: s["claims"][0].update({
    "contested": True,
    "counter_evidence": [{"quote": "Samples were held at 25 C.", "locator": "p.7"}],
}))
COUNTER["source_text"] += " Samples were held at 25 C."


def bad_counter(spec):
    spec["claims"][0]["counter_evidence"] = [{"quote": "Samples were held at 25 C.",
                                               "locator": ""}]


def empty_question(spec):
    spec["answers"][0]["question"] = ""


def duplicate_evidence(spec):
    spec["evidence"].append(copy.deepcopy(spec["evidence"][0]))


def empty_evidence(spec):
    spec["evidence"].append({"id": "e2", "quote": "", "locator": "p.6"})


def duplicate_field(spec):
    spec["fields"].append(copy.deepcopy(spec["fields"][0]))


def no_document_text(spec):
    spec["documents"][0]["text"] = ""


TRANSLATION = {
    "output_mode": "plain",
    "source_text": "Coating may improve uptake.",
    "source_lang": "en",
    "target_text": "涂层可能提高吸收。",
    "target_lang": "zh",
    "glossary": {},
    "segments": [{"id": "s1", "source": "Coating may improve uptake.",
                  "target": "涂层可能提高吸收。"}],
}


def bad_segment_source(spec):
    spec["segments"][0]["source"] = "Coating may increase uptake."


def bad_segment_target(spec):
    spec["target_text"] = "涂层可能改善吸收。"


# name, section, base, defect edit, expected rule, engine
CASES = [
    ("extract_duplicate", "conclusion_extract", BASE["conclusion_extract"],
     duplicate_extract, "extract.duplicate_claim", "sections"),
    ("extract_condition", "conclusion_extract", BASE["conclusion_extract"],
     bad_condition, "extract.condition_value_unsupported", "sections"),
    ("verify_source", "claim_verify", BASE["claim_verify"],
     no_verify_source, "verify.source_unavailable", "sections"),
    ("verify_counter", "claim_verify", COUNTER,
     bad_counter, "verify.counter_evidence_unverified", "sections"),
    ("qa_question", "qa", BASE["qa"], empty_question, "qa.question_empty", "sections"),
    ("qa_duplicate_evidence", "qa", BASE["qa"],
     duplicate_evidence, "qa.duplicate_evidence_id", "sections"),
    ("qa_empty_evidence", "qa", BASE["qa"], empty_evidence, "qa.evidence_empty_quote", "sections"),
    ("compare_duplicate_field", "compare_docs", BASE["compare_docs"],
     duplicate_field, "compare.duplicate_field_name", "sections"),
    ("compare_no_text", "compare_docs", BASE["compare_docs"],
     no_document_text, "compare.cell_source_unverifiable", "sections"),
    ("xlate_segment_source", "translation", TRANSLATION,
     bad_segment_source, "xlate.segment_source_not_in_source", "writing"),
    ("xlate_segment_target", "translation", TRANSLATION,
     bad_segment_target, "xlate.segment_target_not_in_target", "writing"),
]


def main() -> int:
    rows = []
    for name, section, base, defect, rule, engine in CASES:
        audit = S.run if engine == "sections" else W.run
        for kind, spec in (("guard", copy.deepcopy(base)), ("defect", alter(base, defect))):
            findings, status, _ = audit(spec, section)
            fired = sorted({f["rule"] for f in findings})
            ok = (rule in fired) if kind == "defect" else not fired
            rows.append({"scenario": f"{name}_{kind}", "kind": kind, "section": section,
                         "expected": [rule] if kind == "defect" else [],
                         "fired": fired, "status": status, "pass": ok})
            print(f"{'PASS' if ok else 'FAIL'}  {name + '_' + kind:<38} {fired}")
    passed = sum(1 for row in rows if row["pass"])
    report = {"schema_version": "reading-master-bench/v1", "scenarios": rows,
              "totals": {"passed": passed, "of": len(rows)},
              "note": "Each added rule has an independent defect and zero-finding FP guard."}
    (Path(__file__).resolve().parent / "report_reading.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n{passed}/{len(rows)} scenarios pass")
    return 0 if passed == len(rows) else 1


if __name__ == "__main__":
    raise SystemExit(main())
