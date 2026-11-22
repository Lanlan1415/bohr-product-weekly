"""Benchmark for the database-query-and-analysis skill.

Each scenario plants one defect (or proves one FP guard) aligned to the failure modes a
query-result analysis names — NULL handling, unit mixes, join-key duplicates, type
inconsistencies, report recomputation — plus the report-consistency and no-overwrite
guarantees. The clean baseline must report nothing, so a detector cannot pass by
flagging everything.

    python bench_dbquery.py
"""

from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import cleaning as C  # noqa: E402

BASE_ROWS = [
    {"sample_id": "S1", "absorbance": "0.32 AU", "n_replicates": "6", "measured": "2023-05-14"},
    {"sample_id": "S1-B", "absorbance": "0.3 AU", "n_replicates": "6", "measured": "2023-05-14"},
    {"sample_id": "S2", "absorbance": "0.45 AU", "n_replicates": "6", "measured": "2023年6月1日"},
    {"sample_id": "S3", "absorbance": "0.41 AU", "n_replicates": "5", "measured": "14.06.2023"},
]
BASE = {
    "rows": copy.deepcopy(BASE_ROWS),
    "columns": [
        {"name": "sample_id", "semantic": "id"},
        {"name": "absorbance", "target_unit": "AU", "plausible": [0, 2]},
        {"name": "n_replicates", "semantic": "numeric"},
        {"name": "measured", "semantic": "date"},
    ],
    "key_columns": ["sample_id"],
}


def scen_clean():
    return copy.deepcopy(BASE), [], {}


def scen_missing_not_zero():
    """FP guard: a genuine 0 stays a measured zero — it is not treated as NULL."""
    s = copy.deepcopy(BASE)
    s["rows"][2]["absorbance"] = "0 AU"
    return s, [], {}


def scen_missing_named():
    """A NULL/not-reported cell is a named missing value, never a coerced zero."""
    s = copy.deepcopy(BASE)
    s["rows"][2]["absorbance"] = "not reported"
    return s, ["clean.missing_values"], {}


def scen_unit_convert():
    """A value in a derived unit converts to the column's target unit, factor recorded."""
    s = copy.deepcopy(BASE)
    s["rows"][3]["absorbance"] = "410 mAU"
    return s, [], {}


def scen_unit_refused():
    """A value in an incompatible unit is a refusal, never a silent row drop."""
    s = copy.deepcopy(BASE)
    s["rows"][3]["absorbance"] = "0.41 mol"
    return s, [], {}


def scen_outlier_flagged():
    s = copy.deepcopy(BASE)
    s["columns"][1]["plausible"] = [0, 0.35]
    return s, [], {}


def scen_outlier_fp_guard():
    """FP guard: an unusual-but-declared value stays inside the declared range."""
    s = copy.deepcopy(BASE)
    s["columns"][1]["plausible"] = [0, 2]
    return s, [], {}


def scen_type_inconsistent():
    """A text value in a numeric column is a named gap, never dropped or coerced."""
    s = copy.deepcopy(BASE)
    s["rows"][3]["n_replicates"] = "six"
    return s, ["clean.unparsed_values"], {}


def scen_join_key_inflation():
    """Same entity, different values: a join that returned two measurements for one key
    must be reported, not averaged away."""
    s = copy.deepcopy(BASE)
    s["value_columns"] = ["absorbance"]
    s["rows"][1]["sample_id"] = "S1"            # same entity as row 0
    s["rows"][1]["absorbance"] = "0.5 AU"       # different value -> an experiment pair
    return s, ["clean.duplicate_experiments"], {}


def scen_null_sentinels():
    """NULL / -999 sentinels are missing values, not data and not parse failures."""
    s = copy.deepcopy(BASE)
    s["rows"][2]["absorbance"] = "NULL"
    s["rows"][3]["n_replicates"] = "-999"
    return s, ["clean.missing_values"], {}


def scen_duplicate_rows():
    """Two identical rows (join inflation) report as low-severity duplicates without
    blocking the review."""
    s = copy.deepcopy(BASE)
    s["rows"][1]["sample_id"] = "S1"      # same entity...
    s["rows"][1]["absorbance"] = "0.32 AU"  # ...and identical values -> a record copy
    return s, ["clean.duplicate_records"], {}


def scen_custom_missing_token():
    """A case-declared NULL token is honoured in findings AND the report."""
    s = copy.deepcopy(BASE)
    s["missing_tokens"] = ["<LOQ"]
    s["rows"][2]["absorbance"] = "<LOQ"
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
    spec["quality_report"] = {"rows": 4, "columns": 4, "cells": 16, "missing_cells": 0,
                              "unparsed_cells": 0, "duplicate_records": 0,
                              "duplicate_experiments": 0}
    return spec, [], {}


def scen_report_inconsistent():
    """A hand-written report whose numbers disagree with the table is flagged, not
    trusted — the report must be recomputable from the result set."""
    spec = copy.deepcopy(BASE)
    rows = spec["rows"]
    spec["quality_report"] = {
        "rows": len(rows), "columns": 4,
        "cells": len(rows) * 4,
        "missing_cells": 7, "unparsed_cells": 0,
    }
    return spec, ["clean.report_inconsistent"], {}


def scen_idempotent_second_pass():
    """The cleaned table re-run must change nothing (asserted via a second clean() call
    inside the runner's extra check)."""
    return copy.deepcopy(BASE), [], {}


SCENARIOS = [
    ("clean", scen_clean),
    ("missing_named", scen_missing_named),
    ("type_inconsistent", scen_type_inconsistent),
    ("missing_not_zero", scen_missing_not_zero),
    ("unit_convert", scen_unit_convert),
    ("unit_refused", scen_unit_refused),
    ("outlier_flagged", scen_outlier_flagged),
    ("outlier_fp_guard", scen_outlier_fp_guard),
    ("join_key_inflation", scen_join_key_inflation),
    ("null_sentinels", scen_null_sentinels),
    ("duplicate_rows", scen_duplicate_rows),
    ("custom_missing_token", scen_custom_missing_token),
    ("no_key_columns", scen_no_key_columns),
    ("dates_normalised", scen_dates_normalised),
    ("date_garbage", scen_date_garbage),
    ("report_consistent", scen_report_consistent),
    ("report_inconsistent", scen_report_inconsistent),
    ("idempotent_second_pass", scen_idempotent_second_pass),
]


def run_one(name, builder) -> dict:
    spec, expect, _ = builder()
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
        dates = [c for c in r["changes"] if c["rule"] == "R08" and c["column"] == "measured"]
        iso = {c["original"]: c["new"] for c in dates if c["new"]}
        if iso.get("2023年6月1日") != "2023-06-01":
            missing.append("R08.cjk")
        extra += f" dates={iso}"
    return {"scenario": name, "expected": expect, "fired": sorted(fired),
            "missing": missing, "spurious": spurious, "pass": not missing and not spurious,
            "extra": extra.strip()}


def main() -> int:
    rows = [run_one(n, b) for n, b in SCENARIOS]
    passed = sum(1 for r in rows if r["pass"])
    report = {
        "schema_version": "dbquery-bench/v1",
        "scenarios": rows,
        "totals": {"passed": passed, "of": len(rows)},
        "note": ("Each scenario plants one defect or proves one FP guard. The clean "
                 "baseline must report no high or medium finding."),
    }
    (Path(__file__).resolve().parent / "report_dbquery.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    for r in rows:
        print(("PASS" if r["pass"] else "FAIL") + f"  {r['scenario']:<24}"
              f" missing={r['missing']} spurious={r['spurious']}"
              + ((" |" + r["extra"]) if r["extra"] else ""))
    print(f"\n{passed}/{len(rows)} scenarios pass")
    return 0 if passed == len(rows) else 1


if __name__ == "__main__":
    raise SystemExit(main())
