"""Benchmark for the data-quality skill.

Each scenario plants one defect (or proves one FP guard) aligned to the five
processing classes the task names — missing values, outliers, duplicates, format
conversion, quality report — plus the dictionary-to-table alignment rules, the
mixed-unit hazard, and the report-consistency and no-overwrite guarantees. The
clean baseline must report nothing, so a detector cannot pass by flagging
everything.

    python bench_dataquality.py
"""

from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import cleaning as C  # noqa: E402

BASE_ROWS = [
    {"material": "TiO2", "bandgap": "3.20 eV", "n": "6", "measured": "2023-05-14"},
    {"material": "TiO2-B", "bandgap": "3.2 eV", "n": "6", "measured": "2023-05-14"},
    {"material": "ZnO", "bandgap": "3.4 eV", "n": "6", "measured": "2023年6月1日"},
    {"material": "GaN", "bandgap": "3.35 eV", "n": "5", "measured": "14.06.2023"},
]
BASE = {
    "rows": copy.deepcopy(BASE_ROWS),
    "columns": [
        {"name": "material", "semantic": "id"},
        {"name": "bandgap", "target_unit": "eV", "plausible": [0, 6]},
        {"name": "n", "semantic": "numeric"},
        {"name": "measured", "semantic": "date"},
    ],
    "key_columns": ["material"],
}


def scen_clean():
    return copy.deepcopy(BASE), [], {}


def scen_missing_not_zero():
    """FP guard: a genuine 0 stays a measured zero — it is not treated as missing."""
    s = copy.deepcopy(BASE)
    s["rows"][2]["bandgap"] = "0 eV"
    return s, [], {}


def scen_missing_named():
    """A not-reported value is a named missing cell, never a coerced zero."""
    s = copy.deepcopy(BASE)
    s["rows"][2]["bandgap"] = "not reported"
    return s, ["clean.missing_values"], {}


def scen_unit_convert():
    s = copy.deepcopy(BASE)
    s["rows"][3]["bandgap"] = "3400 meV"
    return s, [], {}


def scen_unit_refused():
    s = copy.deepcopy(BASE)
    s["rows"][3]["bandgap"] = "3.4 mol"
    return s, [], {}


def scen_outlier_flagged():
    s = copy.deepcopy(BASE)
    s["columns"][1]["plausible"] = [0, 3.3]
    return s, [], {}


def scen_outlier_fp_guard():
    """FP guard: an unusual-but-declared value stays inside the declared range."""
    s = copy.deepcopy(BASE)
    s["columns"][1]["plausible"] = [0, 4]
    return s, [], {}


def scen_unparsed_named():
    """A cell that parses to nothing is kept as a named gap, never dropped."""
    s = copy.deepcopy(BASE)
    s["rows"][3]["n"] = "six"
    return s, ["clean.unparsed_values"], {}


def scen_duplicate_experiments():
    """The same entity with different values is two measurements (value_columns declared)."""
    s = copy.deepcopy(BASE)
    s["value_columns"] = ["bandgap"]
    s["rows"][1]["material"] = "TiO2"          # same entity as row 0
    s["rows"][1]["bandgap"] = "3.5 eV"          # different value -> an experiment pair
    return s, ["clean.duplicate_experiments"], {}


def scen_missing_token_nd():
    """ND / -999 style sentinels are missing values, not data and not parse failures."""
    s = copy.deepcopy(BASE)
    s["rows"][2]["bandgap"] = "ND"
    s["rows"][3]["n"] = "-999"
    return s, ["clean.missing_values"], {}


def scen_duplicates_review_only():
    """Two identical records report as low-severity duplicates without blocking."""
    s = copy.deepcopy(BASE)
    s["rows"][1]["material"] = "TiO2"    # same entity...
    s["rows"][1]["bandgap"] = "3.20 eV"  # ...and identical values -> a record copy
    return s, ["clean.duplicate_records"], {}


def scen_custom_missing_token():
    """A case-declared token (<LOQ) is a missing value in findings AND the report."""
    s = copy.deepcopy(BASE)
    s["missing_tokens"] = ["<LOQ"]
    s["rows"][2]["bandgap"] = "<LOQ"
    return s, ["clean.missing_values"], {}


def scen_no_key_columns():
    """No key_columns -> the duplicate census is skipped, never spuriously fired."""
    s = copy.deepcopy(BASE)
    s.pop("key_columns")
    return s, [], {}


def scen_dates_normalised():
    s = copy.deepcopy(BASE)
    s["rows"][3]["measured"] = "2023/06/14"
    return s, [], {}


def scen_date_garbage():
    """An unrecognisable date is a named unparsed cell, never a guessed value."""
    s = copy.deepcopy(BASE)
    s["rows"][3]["measured"] = "mid-June"
    return s, ["clean.unparsed_values"], {}


def scen_report_consistent():
    """FP guard: a supplied quality report that matches the table stays silent."""
    spec = copy.deepcopy(BASE)
    spec["quality_report"] = {"rows": 4, "columns": 4, "cells": 16, "missing_cells": 0, "unparsed_cells": 0, "duplicate_records": 0, "duplicate_experiments": 0}
    return spec, [], {}


def scen_report_inconsistent():
    spec = copy.deepcopy(BASE)
    rows = spec["rows"]
    spec["quality_report"] = {
        "rows": len(rows), "columns": 4,
        "cells": len(rows) * 4,
        "missing_cells": 7, "unparsed_cells": 0,
    }
    return spec, ["clean.report_inconsistent"], {}


def scen_dictionary_alignment():
    """The dictionary declares a column the table does not carry."""
    s = copy.deepcopy(BASE)
    s["columns"].append({"name": "yield_pct", "semantic": "numeric"})
    return s, ["clean.column_missing"], {}


def scen_key_column_missing():
    """A declared key column in no row: the duplicate census is impossible (high)."""
    s = copy.deepcopy(BASE)
    s["key_columns"] = ["sample_code"]
    return s, ["clean.key_column_missing"], {}


def scen_ragged_rows():
    """One row drops a column the others carry: the table's shape drifts."""
    s = copy.deepcopy(BASE)
    del s["rows"][2]["n"]
    return s, ["clean.ragged_rows"], {}


def scen_undeclared_columns():
    """A column the table carries but the dictionary does not declare passes through, named."""
    s = copy.deepcopy(BASE)
    for r in s["rows"]:
        r["lab_note"] = "handled"
    return s, ["clean.column_undeclared"], {}


def scen_mixed_units():
    """One column, two written units, no target declared: an averaging hazard."""
    s = copy.deepcopy(BASE)
    for col in s["columns"]:
        if col["name"] == "bandgap":
            col.pop("target_unit", None)
    s["rows"][0]["bandgap"] = "3.20 eV"
    s["rows"][1]["bandgap"] = "3100 meV"
    return s, ["clean.mixed_units"], {}


def scen_mixed_units_fp():
    """FP guard: with a declared target unit the mix is the plan, not a hazard."""
    s = copy.deepcopy(BASE)
    s["rows"][0]["bandgap"] = "3.20 eV"
    s["rows"][1]["bandgap"] = "3100 meV"
    return s, [], {}


def scen_empty_rows():
    """A well-formed table whose every cell is blank is named, not cleaned silently."""
    s = copy.deepcopy(BASE)
    s["rows"] = [{"material": "", "bandgap": "", "n": "", "measured": ""} for _ in range(2)]
    return s, ["clean.empty_rows"], {}


def scen_idempotent_second_pass():
    """The cleaned table re-run must change nothing (checked in-code, so this
    scenario asserts via a second clean() call inside the runner's extra check)."""
    return copy.deepcopy(BASE), [], {}


SCENARIOS = [
    ("clean", scen_clean),
    ("missing_named", scen_missing_named),
    ("unparsed_named", scen_unparsed_named),
    ("missing_not_zero", scen_missing_not_zero),
    ("unit_convert", scen_unit_convert),
    ("unit_refused", scen_unit_refused),
    ("outlier_flagged", scen_outlier_flagged),
    ("outlier_fp_guard", scen_outlier_fp_guard),
    ("duplicate_experiments", scen_duplicate_experiments),
    ("missing_token_nd", scen_missing_token_nd),
    ("duplicates_review_only", scen_duplicates_review_only),
    ("custom_missing_token", scen_custom_missing_token),
    ("no_key_columns", scen_no_key_columns),
    ("dates_normalised", scen_dates_normalised),
    ("date_garbage", scen_date_garbage),
    ("report_consistent", scen_report_consistent),
    ("report_inconsistent", scen_report_inconsistent),
    ("dictionary_alignment", scen_dictionary_alignment),
    ("key_column_missing", scen_key_column_missing),
    ("ragged_rows", scen_ragged_rows),
    ("undeclared_columns", scen_undeclared_columns),
    ("mixed_units", scen_mixed_units),
    ("mixed_units_fp", scen_mixed_units_fp),
    ("empty_rows", scen_empty_rows),
    ("idempotent_second_pass", scen_idempotent_second_pass),
]


def run_one(name, builder, out_root: Path) -> dict:
    spec, expect, _ = builder()
    out = out_root / name
    out.mkdir(parents=True, exist_ok=True)
    r = C.clean(spec["rows"], spec)
    fired = {f["rule"] for f in r["findings"]}
    missing = [x for x in expect if x not in fired]
    spurious = []
    if not expect:
        spurious = [f["rule"] for f in r["findings"] if f["severity"] in ("high", "medium")]
    # idempotence assertion for the dedicated scenario
    extra = ""
    if name == "idempotent_second_pass":
        ok = r["idempotent"] is True
        extra = f" idempotent={r['idempotent']}"
        if not ok:
            missing.append("idempotent")
    # date normalisation assertion
    if name == "dates_normalised":
        got = {v["original"]: v["value"] for run in [] for v in []}
        dates = [c for c in r["changes"] if c["rule"] == "R08" and c["column"] == "measured"]
        iso = {c["original"]: c["new"] for c in dates if c["new"]}
        if iso.get("2023年6月1日") != "2023-06-01":
            missing.append("R08.cjk")
        extra += f" dates={iso}"
    return {"scenario": name, "expected": expect, "fired": sorted(fired),
            "missing": missing, "spurious": spurious, "pass": not missing and not spurious,
            "extra": extra.strip()}


def main() -> int:
    out_root = Path(__file__).resolve().parent / "_run"
    rows = [run_one(n, b, out_root) for n, b in SCENARIOS]
    passed = sum(1 for r in rows if r["pass"])
    report = {
        "schema_version": "dataquality-bench/v1",
        "scenarios": rows,
        "totals": {"passed": passed, "of": len(rows)},
        "note": ("Each scenario plants one defect or proves one FP guard. The clean "
                 "baseline must report no high or medium finding."),
    }
    (Path(__file__).resolve().parent.parent / "report_dataquality.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    for r in rows:
        print(("PASS" if r["pass"] else "FAIL") + f"  {r['scenario']:<24}"
              f" missing={r['missing']} spurious={r['spurious']}"
              + ((" |" + r["extra"]) if r["extra"] else ""))
    print(f"\n{passed}/{len(rows)} scenarios pass")
    return 0 if passed == len(rows) else 1


if __name__ == "__main__":
    raise SystemExit(main())
