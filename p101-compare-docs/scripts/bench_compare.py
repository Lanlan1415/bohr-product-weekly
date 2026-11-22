"""Benchmark for the cross-document comparison skill.

One scenario per rule plus false-positive guards, aligned to the scoring points
this task states:

  one field table, cell by cell              -> field_group_missing, field_undefined, field_missing
  each cell from the paper it names          -> cell_no_locator, cell_not_in_source,
                                                cell_wrong_source, duplicate_document_id
  conditions travel with the value           -> cell_metadata_missing, unit_mismatch,
                                                target_unit_undeclared
  comparability stated, not assumed          -> comparability_undeclared,
                                                condition_conflict_unmarked,
                                                noncomparable_pooled
  a recorded conversion recomputes           -> conversion_unreproducible
  direction and strength not misread         -> direction_missing, strength_missing,
                                                conflict_unattributed, consistency_misstated
  malformed entries degrade, not crash       -> schema_entry_skipped, document_skipped

    python bench_compare.py
"""

from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import sections as S  # noqa: E402

DOC_A_TEXT = "Bandgap of 3.20 eV was measured for sample A."
DOC_B_TEXT = "Bandgap of 3.37 eV was measured for sample B."

BASE = {
    "field_groups": ["metric", "conclusion"],
    "documents": [
        {"id": "A", "text": DOC_A_TEXT, "fields": {
            "bandgap": {"value": "3.20 eV", "unit": "eV", "locator": "Table 1 row 2",
                        "dataset": "sample A", "metric": "optical bandgap",
                        "control": "annealed"},
            "trend": {"value": "bandgap", "direction": "decreases", "strength": "moderate",
                      "locator": "p.5"}}},
        {"id": "B", "text": DOC_B_TEXT, "fields": {
            "bandgap": {"value": "3.37 eV", "unit": "eV", "locator": "Table 2 row 1",
                        "dataset": "sample B", "metric": "optical bandgap",
                        "control": "as-grown"},
            "trend": {"value": "bandgap", "direction": "decreases", "strength": "moderate",
                      "locator": "p.6"}}},
    ],
    "fields": [
        {"name": "bandgap", "group": "metric",
         "definition": "reported optical bandgap", "target_unit": "eV",
         "comparability": "same optical method",
         "condition_variance": "control state differs (annealed vs as-grown); values "
                               "compared as reported, not pooled as same-condition"},
        {"name": "trend", "group": "conclusion",
         "definition": "direction of the bandgap trend",
         "conflict_note": "none observed"},
    ],
}


def d(**over):
    s = copy.deepcopy(BASE)
    s.update(over)
    return s


def cell(doc: int, field: str, **over):
    s = d()
    s["documents"] = copy.deepcopy(BASE["documents"])
    s["documents"][doc]["fields"][field] = dict(
        BASE["documents"][doc]["fields"][field], **over)
    return s


def conc_spec(a_from: dict | None, a_value: str, a_unit: str,
              pollutant_a: str = "methylene blue", pollutant_b: str = "methylene blue",
              condition_keys: list | None = None,
              variance: bool = True, same_batch: bool = False):
    """Two-document uptake-concentration spec for the conversion and condition scenarios.

    Both papers report ug/L; the matrix records mg/L with the conversion path declared.
    """
    band = {"name": "conc", "group": "data",
            "definition": "uptake concentration at equilibrium",
            "target_unit": "mg/L", "comparability": "same adsorbent and dose"}
    if variance:
        band["condition_variance"] = "batches differ; values compared as reported"
    s = d(field_groups=["data", "conclusion"],
          fields=[band,
                  {"name": "trend", "group": "conclusion",
                   "definition": "direction of the uptake trend",
                   "conflict_note": "none observed"}])
    if condition_keys:
        s["condition_keys"] = condition_keys
    batch_a, batch_b = ("batch 1", "batch 1") if same_batch else ("batch 1", "batch 2")
    a_cell = {"value": a_value, "unit": a_unit, "locator": "Table 1 row 2",
              "dataset": batch_a, "metric": "uptake", "control": "uncoated",
              "pollutant": pollutant_a}
    if a_from:
        a_cell["converted_from"] = a_from
    s["documents"] = [
        {"id": "A", "text": "Uptake of 25 ug/L was measured.", "fields": {
            "conc": a_cell,
            "trend": {"value": "uptake", "direction": "increases", "strength": "moderate",
                      "locator": "p.5"}}},
        {"id": "B", "text": "Uptake of 30 ug/L was measured.", "fields": {
            "conc": {"value": "0.030", "unit": "mg/L",
                     "converted_from": {"value": 30, "unit": "µg/L"},
                     "locator": "Table 2 row 1", "dataset": batch_b,
                     "metric": "uptake", "control": "uncoated",
                     "pollutant": pollutant_b},
            "trend": {"value": "uptake", "direction": "increases", "strength": "moderate",
                      "locator": "p.6"}}},
    ]
    return s


SCEN = [
    ("clean", lambda: (d(), [])),

    # schema and coverage
    ("no_schema", lambda: (d(fields=[]), ["compare.no_schema"])),
    ("too_few_docs", lambda: (d(documents=BASE["documents"][:1]), ["compare.too_few_documents"])),
    ("group_missing", lambda: (d(field_groups=["metric", "conclusion", "method"]),
                               ["compare.field_group_missing"])),
    ("field_undefined",
     lambda: (d(fields=[{"name": "bandgap", "group": "metric", "target_unit": "eV",
                         "comparability": "same",
                         "condition_variance": "control differs; compared as reported"},
                        {"name": "trend", "group": "conclusion"}]),
              ["compare.field_undefined"])),
    ("field_missing", lambda: (d(documents=[
        BASE["documents"][0],
        {**copy.deepcopy(BASE["documents"][1]),
         "fields": {k: v for k, v in BASE["documents"][1]["fields"].items() if k != "trend"}}]),
        ["compare.field_missing"])),

    # traceability of a cell
    ("cell_no_locator", lambda: (cell(0, "bandgap", locator=""), ["compare.cell_no_locator"])),
    ("cell_locator_vague",
     lambda: (cell(0, "bandgap", locator="见上文"), ["compare.cell_locator_vague"])),
    ("cell_not_in_source",
     lambda: (cell(0, "bandgap", verbatim="Bandgap of 9.99 eV was measured"),
              ["compare.cell_not_in_source"])),

    # one column per paper
    ("duplicate_document_id",
     lambda: (d(documents=[copy.deepcopy(BASE["documents"][0]),
                           {**copy.deepcopy(BASE["documents"][1]), "id": "A"}]),
              ["compare.duplicate_document_id"])),

    # conditions and units
    ("metadata_missing",
     lambda: (cell(0, "bandgap", dataset="", control=""), ["compare.cell_metadata_missing"])),
    ("unit_mismatch",
     lambda: (cell(0, "bandgap", value="2.5 psi", unit="psi"), ["compare.unit_mismatch"])),
    ("comparability_undeclared",
     lambda: (d(fields=[{"name": "bandgap", "group": "metric",
                         "definition": "optical bandgap", "target_unit": "eV",
                         "condition_variance": "control differs; compared as reported"},
                        {"name": "trend", "group": "conclusion",
                         "definition": "trend", "conflict_note": "none"}]),
              ["compare.comparability_undeclared"])),
    ("condition_conflict_unmarked",
     lambda: (d(fields=[{"name": "bandgap", "group": "metric",
                         "definition": "reported optical bandgap", "target_unit": "eV",
                         "comparability": "same optical method"},
                        {"name": "trend", "group": "conclusion",
                         "definition": "trend", "conflict_note": "none observed"}]),
              ["compare.condition_conflict_unmarked"])),
    ("same_conditions_fp",
     lambda: (d(documents=[
        BASE["documents"][0],
        {**copy.deepcopy(BASE["documents"][1]),
         "fields": {**copy.deepcopy(BASE["documents"][1]["fields"]),
                    "bandgap": {**copy.deepcopy(BASE["documents"][1]["fields"]["bandgap"]),
                                "dataset": "sample A", "control": "annealed"}}}]),
        [])),
    ("condition_keys_conflict",
     lambda: (conc_spec(None, "0.025", "mg/L",
                        pollutant_a="methylene blue", pollutant_b="rhodamine B",
                        condition_keys=["pollutant"], variance=False, same_batch=True),
              ["compare.condition_conflict_unmarked"])),
    ("condition_keys_same_fp",
     lambda: (conc_spec(None, "0.025", "mg/L", condition_keys=["pollutant"],
                        variance=False, same_batch=True), [])),

    # a recorded conversion must recompute
    ("conversion_ok",
     lambda: (conc_spec({"value": 25, "unit": "µg/L"}, "0.025", "mg/L"), [])),
    ("conversion_mismatch",
     lambda: (conc_spec({"value": 45, "unit": "µg/L"}, "0.025", "mg/L"),
              ["compare.conversion_unreproducible"])),
    ("conversion_dimension_mismatch",
     lambda: (conc_spec({"value": 25, "unit": "µg/L"}, "3.20", "eV"),
              ["compare.conversion_unreproducible"])),
    ("conversion_unknown_unit_fp",
     lambda: (conc_spec({"value": 25, "unit": "zorp"}, "0.025", "mg/L"), [])),

    # direction and strength
    ("direction_missing",
     lambda: (cell(0, "trend", direction=""), ["compare.direction_missing"])),
    ("strength_missing",
     lambda: (cell(0, "trend", strength=""), ["compare.strength_missing"])),
    ("conflict_unattributed",
     lambda: (
         d(documents=[
             copy.deepcopy(BASE["documents"][0]),
             {**copy.deepcopy(BASE["documents"][1]),
              "fields": {**BASE["documents"][1]["fields"],
                         "trend": {**BASE["documents"][1]["fields"]["trend"],
                                   "direction": "increases"}}},
         ],
           fields=[{"name": "bandgap", "group": "metric",
                    "definition": "optical bandgap", "target_unit": "eV",
                    "comparability": "same",
                    "condition_variance": "control differs; compared as reported"},
                   {"name": "trend", "group": "conclusion", "definition": "trend"}]),
         ["compare.conflict_unattributed"],
     )),
    ("consistency_misstated",
     lambda: (
         d(documents=[
             copy.deepcopy(BASE["documents"][0]),
             {**copy.deepcopy(BASE["documents"][1]),
              "fields": {**BASE["documents"][1]["fields"],
                         "trend": {**BASE["documents"][1]["fields"]["trend"],
                                   "direction": "increases"}}},
         ],
           fields=[{"name": "bandgap", "group": "metric",
                    "definition": "optical bandgap", "target_unit": "eV",
                    "comparability": "same",
                    "condition_variance": "control differs; compared as reported"},
                   {"name": "trend", "group": "conclusion", "definition": "trend",
                    "conflict_note": "attributed to synthesis temperature",
                    "consistency": "consistent"}]),
         ["compare.consistency_misstated"],
     )),
    ("consistency_agree_fp",
     lambda: (d(fields=[BASE["fields"][0],
                        {"name": "trend", "group": "conclusion", "definition": "trend",
                         "conflict_note": "none observed", "consistency": "consistent"}]),
              [])),
    ("consistency_conflict_false",
     lambda: (d(fields=[BASE["fields"][0],
                        {"name": "trend", "group": "conclusion", "definition": "trend",
                         "consistency": "conflict"}]),
              ["compare.consistency_misstated"])),

    # --- workorder v2: exact source_document_id per cell --------------------
    # A cell that names another supplied document (or an unknown one) is the
    # "value copied from the wrong paper" failure; the own-document declaration
    # and a bare paragraph id must stay silent.
    ("cell_wrong_source",
     lambda: (cell(0, "bandgap", source_document_id="B"),
              ["compare.cell_wrong_source"])),
    ("cell_wrong_source_unknown",
     lambda: (cell(0, "bandgap", source_document_id="Z9"),
              ["compare.cell_wrong_source"])),
    ("cell_source_own_fp", lambda: (cell(0, "bandgap", source_document_id="A"), [])),
    ("paragraph_id_locator_fp",
     lambda: (cell(0, "bandgap", locator="", paragraph_id="P3"), [])),

    # --- units must be normalisable before synthesis ------------------------
    ("target_unit_undeclared",
     lambda: (d(fields=[{"name": "bandgap", "group": "metric",
                         "definition": "reported optical bandgap",
                         "comparability": "same optical method",
                         "condition_variance": "control differs; compared as reported"},
                        {"name": "trend", "group": "conclusion",
                         "definition": "trend", "conflict_note": "none observed"}]),
              ["compare.target_unit_undeclared"])),
    ("target_unit_categorical_fp",
     lambda: (d(fields=[{"name": "bandgap", "group": "metric",
                         "definition": "sample grade", "target_unit": "",
                         "comparability": "same rubric",
                         "condition_variance": "control differs; compared as reported"},
                        {"name": "trend", "group": "conclusion",
                         "definition": "trend", "conflict_note": "none observed"}],
                   documents=[
                       {"id": "A", "text": "Sample A graded high.",
                        "fields": {"bandgap": {"value": "high", "locator": "p.3",
                                               "dataset": "sA", "metric": "grade",
                                               "control": "annealed"},
                                   "trend": {"value": "bandgap", "direction": "decreases",
                                             "strength": "moderate", "locator": "p.5"}}},
                       {"id": "B", "text": "Sample B graded low.",
                        "fields": {"bandgap": {"value": "low", "locator": "p.4",
                                               "dataset": "sB", "metric": "grade",
                                               "control": "as-grown"},
                                   "trend": {"value": "bandgap", "direction": "decreases",
                                             "strength": "moderate", "locator": "p.6"}}}]),
              [])),

    # --- the pooling judgment must not contradict the cells -----------------
    ("noncomparable_pooled",
     lambda: (_noncomparable_pooled_spec(), ["compare.noncomparable_pooled"])),
    ("comparable_subset_fp",
     lambda: (d(fields=[dict(BASE["fields"][0], comparable_subset="A, B"),
                        BASE["fields"][1]]), [])),

    # --- malformed schema and corpus entries degrade, never crash -----------
    ("schema_entry_skipped",
     lambda: (d(fields=[BASE["fields"][0], BASE["fields"][1], "junk-string-entry"]),
              ["compare.schema_entry_skipped"])),
    ("document_skipped",
     lambda: (d(documents=BASE["documents"] + ["junk-string-doc"]),
              ["compare.document_skipped"])),
]


def _noncomparable_pooled_spec():
    """BASE with a comparable_subset that lists a noncomparable-marked document."""
    s = d(fields=[dict(BASE["fields"][0], comparable_subset=["A", "B"]), BASE["fields"][1]])
    s["documents"] = copy.deepcopy(BASE["documents"])
    s["documents"][1]["fields"]["bandgap"]["noncomparable"] = True
    return s



def main() -> int:
    rows = []
    for name, builder in SCEN:
        spec, expect = builder()
        findings, status, counts = S.run(spec, "compare_docs")
        fired = {f["rule"] for f in findings}
        missing = [r for r in expect if r not in fired]
        spurious = [] if expect else [f["rule"] for f in findings]
        ok = not missing and not spurious
        rows.append({"scenario": name, "expected": expect, "fired": sorted(fired),
                     "missing": missing, "spurious": spurious, "pass": ok,
                     "status": status})
        print(f"{'PASS' if ok else 'FAIL'}  {name:<32} missing={missing} spurious={spurious}")

    passed = sum(1 for r in rows if r["pass"])

    # The delivered result.json must carry the matrix itself, not only the verdict:
    # the clean baseline yields 4 cells (2 fields x 2 documents), all reported.
    cov = S.compare_coverage(d())
    cells_ok = (len(cov.get("cells") or []) == 4
                and cov["not_reported"]["bandgap"] == []
                and cov["not_reported"]["trend"] == []
                and all(c.get("locator") for c in cov["cells"]))
    rows.append({"scenario": "coverage_matrix_shape", "expected": [],
                 "fired": [], "missing": [], "spurious": [] if cells_ok else
                 ["coverage matrix did not carry the cells (value/locator per field x "
                  "document)"], "pass": cells_ok, "status": "clean"})
    print(f"{'PASS' if cells_ok else 'FAIL'}  coverage_matrix_shape")
    passed += 1 if cells_ok else 0

    report = {"schema_version": "compare-bench/v1", "scenarios": rows,
              "totals": {"passed": passed, "of": len(rows)},
              "note": ("One scenario per rule plus false-positive guards, aligned to the "
                       "comparison scoring points. Clean baselines must report nothing.")}
    (Path(__file__).resolve().parent / "report_compare.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n{passed}/{len(rows)} pass")
    return 0 if passed == len(rows) else 1


if __name__ == "__main__":
    raise SystemExit(main())
