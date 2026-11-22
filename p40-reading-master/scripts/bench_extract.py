"""Benchmark for the conclusion-and-data extraction skill.

One scenario per rule, aligned to the four scoring points this task states:

  one field table across body / table / figure / supplement   -> source.*, field.*
  values verbatim; conclusion vs limitation vs speculation    -> value_not_in_source_text,
                                                                kind.*, hedge_dropped
  a gap stated as not-reported or extraction-failed           -> gap_unclassified
  every field locatable to page/section/cell/figure           -> locator.*

The clean baseline must report nothing, so a detector cannot pass by flagging everything.

    python bench_extract.py
"""

from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import sections as S  # noqa: E402

SOURCE_TEXT = (
    "The porous coating improved uptake 3-fold (Fig. 3b, p.7). "
    "All measurements were made at 25 \u00b0C with n = 6 per group. "
    "We caution that only one coating thickness was tested."
)

BASE = {
    "fields": [
        {"name": "effect_size", "definition": "reported fold change in uptake rate"},
        {"name": "sample_n", "definition": "number of replicates per group"},
        {"name": "thickness", "definition": "coating thickness in nm"},
    ],
    "source_text": SOURCE_TEXT,
    "sources_present": ["body", "figure"],
    "conclusions": [
        {"claim": "涂层的吸收速率提高到原来的 3 倍",
         "condition": "每组 n = 6，25 \u00b0C，单一厚度",
         "locator": "Fig 3b, p.7",
         "claim_kind": "conclusion", "source_kind": "figure", "hedged": True,
         "effect_size": "3-fold", "sample_n": 6, "thickness": 42,
         "values": [{"value": 3, "unit": "fold", "verbatim": "3-fold"}]},
        {"claim": "只测试了一种涂层厚度，结论不能外推到其他厚度",
         "condition": "不适用（局限说明）",
         "locator": "p.7",
         "claim_kind": "limitation", "source_kind": "body", "hedged": True,
         "effect_size": "", "effect_size_status": "not_reported",
         "sample_n": 6, "thickness": 42,
         "values": []},
    ],
}


def d(**over):
    s = copy.deepcopy(BASE)
    s.update(over)
    return s


def item(i=0, **over):
    s = d()
    s["conclusions"] = copy.deepcopy(BASE["conclusions"])
    s["conclusions"][i].update(over)
    return s


SCEN = [
    ("clean", lambda: (d(), [])),

    # schema
    ("schema_missing", lambda: (d(fields=[]), ["extract.schema_missing"])),
    ("field_undefined", lambda: (d(fields=[{"name": "effect_size"},
                                           {"name": "sample_n"},
                                           {"name": "thickness"}]),
                                 ["extract.field_undefined"])),

    # claim kind
    ("kind_undeclared", lambda: (item(claim_kind=""), ["extract.kind_undeclared"])),
    ("kind_unknown", lambda: (item(claim_kind="observation"), ["extract.kind_unknown"])),

    # source coverage
    ("source_kind_missing", lambda: (item(source_kind=""), ["extract.source_kind_missing"])),
    ("source_kind_unknown", lambda: (item(source_kind="appendix"), ["extract.source_kind_unknown"])),
    ("source_not_covered",
     lambda: (d(sources_present=["body", "figure", "supplement"]),
              ["extract.source_not_covered"])),

    # locator
    ("missing_locator", lambda: (item(locator=""), ["extract.missing_locator"])),
    ("locator_vague", lambda: (item(locator="见上文"), ["extract.locator_vague"])),

    # conditions and hedging
    ("missing_condition", lambda: (item(condition=""), ["extract.missing_condition"])),
    ("hedge_dropped",
     lambda: (item(claim="涂层总是把吸收速率提高到原来的 3 倍", hedged=False),
              ["extract.hedge_dropped"])),

    # gaps must be classified
    # A blank field is only a gap if it is labelled; drop the label to make one.
    ("gap_unclassified", lambda: (d(conclusions=[
        copy.deepcopy(BASE["conclusions"][0]),
        {k: v for k, v in BASE["conclusions"][1].items() if k != "effect_size_status"}]),
        ["extract.gap_unclassified"])),
    ("field_absent", lambda: (d(conclusions=[
        {k: v for k, v in BASE["conclusions"][0].items() if k != "thickness"},
        copy.deepcopy(BASE["conclusions"][1])]),
        ["extract.field_absent"])),

    # values
    ("value_without_unit", lambda: (d(conclusions=[
        {**copy.deepcopy(BASE["conclusions"][0]),
         "values": [{"value": 3, "verbatim": "3-fold"}]},
        copy.deepcopy(BASE["conclusions"][1])]),
        ["extract.value_without_unit"])),
    ("count_no_unit_clean", lambda: (d(conclusions=[
        {**copy.deepcopy(BASE["conclusions"][0]),
         "values": [{"value": 6, "verbatim": "n = 6"}]},
        copy.deepcopy(BASE["conclusions"][1])]), [])),
    ("value_not_in_source", lambda: (d(conclusions=[
        {**copy.deepcopy(BASE["conclusions"][0]),
         "values": [{"value": 5, "unit": "fold", "verbatim": "5-fold"}]},
        copy.deepcopy(BASE["conclusions"][1])]),
        ["extract.value_not_in_source_text"])),

    ("no_items", lambda: (d(conclusions=[]), ["extract.no_items"])),
]


def main() -> int:
    rows = []
    for name, builder in SCEN:
        spec, expect = builder()
        findings, status, counts = S.run(spec, "conclusion_extract")
        fired = {f["rule"] for f in findings}
        missing = [r for r in expect if r not in fired]
        spurious = [] if expect else [f["rule"] for f in findings]
        ok = not missing and not spurious
        rows.append({"scenario": name, "expected": expect, "fired": sorted(fired),
                     "missing": missing, "spurious": spurious, "pass": ok,
                     "status": status})
        print(f"{'PASS' if ok else 'FAIL'}  {name:<22} missing={missing} spurious={spurious}")

    passed = sum(1 for r in rows if r["pass"])
    report = {"schema_version": "extract-bench/v1", "scenarios": rows,
              "totals": {"passed": passed, "of": len(rows)},
              "note": ("One scenario per rule, aligned to the task's four scoring points. "
                       "Clean baselines must report nothing.")}
    (Path(__file__).resolve().parent / "report_extract.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n{passed}/{len(rows)} pass")
    return 0 if passed == len(rows) else 1


if __name__ == "__main__":
    raise SystemExit(main())
