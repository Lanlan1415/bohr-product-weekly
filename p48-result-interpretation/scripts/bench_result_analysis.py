"""Executable observation/effect/SPC/reader and refusal benches for the new CLI."""
from __future__ import annotations

import copy
import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from result_analysis import build, main_analysis, parse_cell  # noqa: E402
from result_diagnostics import sd  # noqa: E402


def fixture():
    values = [10.0, 10.1, 9.9, 10.2, 9.8, 10.0, 10.05, 50.0]
    rows = [{"sample": f"S{i}", "batch": "A" if i < 2 else "B", "cycle": i + 1,
             "hardness": v, "group": "control" if i < 4 else "treated"} for i, v in enumerate(values)]
    cfg = {"columns": [{"name": "sample", "semantic": "id"},
                        {"name": "batch", "semantic": "categorical"},
                        {"name": "group", "semantic": "categorical"},
                        {"name": "cycle", "semantic": "ordered_numeric"},
                        {"name": "hardness", "semantic": "response", "unit": "MPa",
                          "plausible": [0, 20], "plausible_source": "synthetic physical range"}],
            "group_by": "batch", "order_column": "cycle", "response_columns": ["hardness"],
            "comparisons": [{"response": "hardness", "group_column": "group", "left": "control", "right": "treated"}],
            "domain": "materials"}
    return rows, cfg


def main():
    reports = []
    def record(name, ok, extra=None):
        reports.append({"scenario": name, "pass": bool(ok), "detail": extra or {}})
        print(("PASS" if ok else "FAIL") + "  " + name + ("  " + str(extra) if extra else ""))

    rows, cfg = fixture(); result = main_analysis(rows, cfg)
    anomalies = result["interpretation"]["anomaly_points"]
    record("grouped_iqr_and_physical_flags", any(a["detection_rule"] == "declared_physical_range" for a in anomalies)
           and all(a["value"] == 50 for a in anomalies)
           and all(a["group"]["batch"] == "B" for a in anomalies))
    record("outlier_effect_and_retention", any(a.get("robust_effect") is not None for a in anomalies)
           and all(a["retained_in_primary_analysis"] for a in anomalies)
           and result["measurement_tables"]["all_original_rows_even_when_flagged"])
    record("three_hypothesis_boundaries", any(h["class"] == "methodological" and "falsification_test" in h for h in result["interpretation"]["possible_causes"]))
    record("trend_not_story_descriptive", result["interpretation"]["result_trends"][0]["computed_observation"]["slope_per_declared_x_unit"] > 0)
    comp = result["effect_sizes"][0]
    record("effect_sizes_and_influence_sensitivity", "cohens_d_pooled" in comp
           and comp["suspicious_point_influence"]["all_rows_retained_in_primary"]
           and comp["suspicious_point_influence"]["sensitivity_without_flagged_mean_delta"] is not None)

    # Five explicitly declared split/effect pairs; no fictitious wet experiment.
    split_rows = []
    for fold in range(1, 6):
        for estimator, base in (("centroid", 0.8), ("ridge", 0.9)):
            split_rows.append({"split_id": fold, "estimator": estimator,
                               "accuracy": base + fold * (0.002 if estimator == "ridge" else 0.001)})
    iris_cfg = {"columns": [{"name": "estimator", "semantic": "categorical"},
                              {"name": "accuracy", "semantic": "response", "unit": "1"}],
                 "group_by": "estimator", "response_columns": ["accuracy"],
                 "comparisons": [{"response": "accuracy", "group_column": "estimator",
                                   "left": "centroid", "right": "ridge", "pair_by": "split_id"}]}
    paired = main_analysis(split_rows, iris_cfg)["effect_sizes"][0]
    record("five_split_paired_effect", paired["n_pairs"] == 5 and abs(paired["mean_difference"] - 0.103) < 1e-9
           and paired["comparison_type"] == "paired_difference"
           and "fold sharing is not" in paired["independence"])
    record("paired_ci_present", "low" in paired["mean_difference_ci95"] and paired["cohens_dz"] > 0)

    spc_rows = []
    for i, value in enumerate([0.0, 0.1, -0.1, 0.05, -0.05, 0.02] + list(range(1, 9))):
        spc_rows.append({"t": i + 1, "phase": "reference" if i < 6 else "production", "y": value})
    spc_cfg = {"columns": [{"name": "phase", "semantic": "categorical"},
                            {"name": "y", "semantic": "response", "unit": "1"}],
                "response_columns": ["y"], "order_column": "t",
                "spc": {"enabled": True, "baseline_filter": {"phase": "reference"},
                         "run_length": 8, "trend_length": 6, "source": "synthetic independent baseline"}}
    spc = main_analysis(spc_rows, spc_cfg)["statistical_process_control"][0]
    spc_rules = {event["rule"] for event in spc["events"]}
    record("spc_three_explicit_rules", spc["status"] == "calculated"
           and {"beyond_3_sigma", "run_8_same_side", "trend_6_monotonic"} <= spc_rules, sorted(spc_rules))
    no_baseline = copy.deepcopy(spc_cfg); del no_baseline["spc"]["baseline_filter"]
    unavailable = main_analysis(spc_rows, no_baseline)["statistical_process_control"][0]
    record("no_invented_spc_reference", unavailable["status"] == "unconfigured" and unavailable.get("events", []) == [])

    bad_units = parse_cell("4.5 MPa", {"target_unit": "N"}, {})
    censored = parse_cell("<LOD", {"semantic": "response"}, {})
    record("units_not_causally_or_arbitrarily_converted", bad_units[0] is None and bad_units[1]["kind"] == "unit_refused")
    record("censoring_not_zero", censored[0] is None and censored[1]["kind"] == "censored")

    pair_bad_rows = [{"pair": 1, "group": "a", "y": 2}, {"pair": 1, "group": "a", "y": 9},
                     {"pair": 1, "group": "b", "y": 3}]
    amb = main_analysis(pair_bad_rows, {"columns": [{"name": "group", "semantic": "categorical"}, {"name": "y", "semantic": "response"}],
                          "response_columns": ["y"], "comparisons": [{"group_column": "group", "left": "a", "right": "b", "pair_by": "pair"}]})["effect_sizes"][0]
    record("duplicate_pairs_not_last_row_wins", amb["comparison_type"] == "ambiguous_pairing")

    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td); rows, cfg = fixture(); cfg["case_id"] = "actual-case-id"
        config = dict(cfg, output_contract=["interpretation", "evidence_and_risks", "confirmation_items"])
        csv_path = tmp / "readings.csv"
        names = list(rows[0]); csv_path.write_text("\n".join([",".join(names)] + [",".join(str(r[k]) for k in names) for r in rows]), encoding="utf-8")
        spec_path = tmp / "analysis-spec.json"; cfg.pop("rows", None)
        schema_path = tmp / "schema.json"
        schema = dict(config, table_path=str(csv_path))
        schema_path.write_text(json.dumps(schema, ensure_ascii=False), encoding="utf-8")
        case = tmp / "case.json"; case.write_text(json.dumps({"case_id": "actual-case-id", "output_contract": ["interpretation", "evidence_and_risks", "confirmation_items"]}), encoding="utf-8")
        a = build(schema_path, tmp / "a", case); b = build(schema_path, tmp / "b", case)
        record("csv_cli_contract_determinism", a["case_id"] == "actual-case-id"
               and all(key in a for key in config["output_contract"])
               and json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)
               and (tmp / "a" / "original-table.csv").is_file())
        record("source_row_trace", all(a.get("source") for a in a["interpretation"]["anomaly_points"]))

        spec_path.write_text("[1,2]", encoding="utf-8")
        bad = build(spec_path, tmp / "bad", case)
        record("structured_refusal_with_original_contract", bad["status"] == "undetermined"
               and bad["case_id"] == "actual-case-id" and len(bad["interpretation"]) == 5
               and all(key in bad for key in config["output_contract"]))

        # A real ZIP/XML workbook exercises the standard-library fallback.
        import zipfile
        from result_analysis import xlsx_standard_library
        workbook = tmp / "native-xml.xlsx"
        with zipfile.ZipFile(workbook, "w") as archive:
            archive.writestr("xl/workbook.xml", '<workbook xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="Data" sheetId="1" r:id="rId1"/></sheets></workbook>')
            archive.writestr("xl/_rels/workbook.xml.rels", '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Target="worksheets/data.xml"/></Relationships>')
            archive.writestr("xl/worksheets/data.xml", '<worksheet><sheetData><row r="1"><c r="A1" t="inlineStr"><is><t>sample</t></is></c><c r="B1" t="inlineStr"><is><t>score</t></is></c></row><row r="2"><c r="A2" t="inlineStr"><is><t>alpha</t></is></c><c r="B2"><v>10.5</v></c></row><row r="3"><c r="A3" t="inlineStr"><is><t>beta</t></is></c><c r="B3"><f>B2*2</f><v>50</v></c></row></sheetData></worksheet>')
        converted, chosen_sheet, sheet_names = xlsx_standard_library(workbook)
        from result_analysis import rows_from_matrix
        native_rows = rows_from_matrix(converted)
        record("xlsx_zip_xml_real_fallback", chosen_sheet == "Data" and native_rows[0]["sample"] == "alpha"
               and float(native_rows[1]["score"]) == 50)

        # Actual available readers are exercised; missing optional packages must refuse honestly.
        try:
            import importlib.util
            if importlib.util.find_spec("openpyxl") is not None:
                import openpyxl
                book = openpyxl.Workbook(); first = book.active; first.title = "main"; first["A1"] = "unselected"
                book.create_sheet("selected").append(["sample", "batch", "hardness"])
                target_sheet = book["selected"]
                for i, r in enumerate(rows):
                    target_sheet.append([r["sample"], r["batch"], r["hardness"]])
                workbook = tmp / ("method" + ".xlsx"); book.save(workbook)
                multi_cfg = dict(config, table_path=str(workbook)); multi_cfg.pop("columns", None)
                multi_cfg.pop("order_column", None)  # this reader-only fixture contains no cycle column
                multi_cfg["response_columns"] = ["hardness"]; multi_cfg["group_by"] = "batch"
                schema_path.write_text(json.dumps(multi_cfg, ensure_ascii=False), encoding="utf-8")
                refused = build(schema_path, tmp / "sheet-refused", case)
                chosen = build(schema_path, tmp / "sheet-selected", case, sheet="selected")
                record("xlsx_explicit_sheet_and_read", refused["status"] == "undetermined"
                       and chosen["status"] in ("clean", "review") and chosen["measurement_tables"]["source_rows"] == 8)
            else:
                missing = build(None, tmp / "xlsx-unsupported", case, table=tmp / ("none" + ".xlsx"))
                record("xlsx_missing_optional_dependency_named", missing["status"] == "undetermined")
        except ImportError:
            pass
        try:
            import importlib.util
            if importlib.util.find_spec("scipy") is not None:
                import scipy.io
                import numpy as np
                mat = tmp / ("numeric" + ".mat"); scipy.io.savemat(mat, {"observed": np.array([[1, 2], [3, 4]])})
                mat_cfg = {"table_path": str(mat), "output_contract": config["output_contract"]}
                schema_path.write_text(json.dumps(mat_cfg, ensure_ascii=False), encoding="utf-8")
                found = build(schema_path, tmp / "mat", case, mat_variable="observed")
                record("numeric_mat_matrix_read", found["status"] in ("clean", "review")
                       and found["measurement_tables"]["source_rows"] == 2)
            else:
                missing = build(None, tmp / "mat-unsupported", case, table=tmp / ("none" + ".mat"))
                record("scipy_missing_optional_dependency_named", missing["status"] == "undetermined")
        except ImportError:
            pass

    passed = sum(r["pass"] for r in reports)
    root = Path(__file__).resolve().parent.parent
    (root / "examples" / "analysis-bench-report.json").write_text(
        json.dumps({"schema_version": "experimental-result-bench/v1", "scenarios": reports,
                    "totals": {"passed": passed, "of": len(reports)}}, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n{passed}/{len(reports)} scenarios pass")
    return 0 if passed == len(reports) else 1


if __name__ == "__main__":
    raise SystemExit(main())
