"""Table/XLSX/MATLAB ingestion + five-part experimental-result interpretation.

Never drops a flagged point from primary evidence. Observed data, derived statistics,
and not-yet-tested hypotheses are separate records. The caller must map raw source
columns to actual experimental meanings; no dataset-named answer path is built in.
"""
from __future__ import annotations

import argparse
import copy
import csv
import hashlib
import json
import math
import re
import sys
from pathlib import Path

# `python -I` omits the script directory; use an explicit package-local import
# without requiring installation or a network dependency.
sys.path.insert(0, str(Path(__file__).resolve().parent))
import result_diagnostics as D

VERSION = "experimental-result-analysis/v1"
GROUP_HINTS = ("batch", "group", "condition", "estimator", "channel", "well", "sample",
               "物种", "批次", "分组", "组别", "工况", "孔位", "通道", "处理")
NUMBER = re.compile(r"^\s*([+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?)\s*(.*?)\s*$")


def object_(x):
    return x if isinstance(x, dict) else {}


def list_records(x):
    return [r for r in x if isinstance(r, dict)] if isinstance(x, list) else []


def rows_from_matrix(matrix):
    if not matrix:
        return []
    matrix = [list(r) for r in matrix if isinstance(r, (tuple, list))]
    if not matrix:
        return []
    headers = [str(x).strip() if x is not None else "" for x in matrix[0]]
    headers = [h or f"column_{i + 1}" for i, h in enumerate(headers)]
    used = {}
    unique = []
    for h in headers:
        used[h] = used.get(h, 0) + 1
        unique.append(h if used[h] == 1 else f"{h}_{used[h]}")
    out = []
    for row in matrix[1:]:
        if not any(str(x or "").strip() for x in row):
            continue
        out.append({unique[i]: row[i] if i < len(row) else None for i in range(len(unique))})
    return out


def xlsx_standard_library(path, requested_sheet=None):
    """Read shared-string/inline-string XLSX cells without optional dependencies.

    Formula *cached* values are read, never evaluated. This deliberately does not
    implement XLS styles, MATLAB formulas, macros or date semantics; those remain
    explicit limitations rather than silently converting Excel serial numbers.
    """
    try:
        import posixpath
        import zipfile
        import xml.etree.ElementTree as ET
        def local(tag):
            return tag.rsplit("}", 1)[-1]
        with zipfile.ZipFile(path) as archive:
            shared = []
            if "xl/sharedStrings.xml" in archive.namelist():
                root = ET.fromstring(archive.read("xl/sharedStrings.xml"))
                for item in root:
                    shared.append("".join(child.text or "" for child in item.iter() if local(child.tag) == "t"))
            workbook = ET.fromstring(archive.read("xl/workbook.xml"))
            rels = ET.fromstring(archive.read("xl/_rels/workbook.xml.rels"))
            targets = {rel.attrib.get("Id"): rel.attrib.get("Target")
                       for rel in rels if rel.attrib.get("Id")}
            sheets = []
            for child in workbook.iter():
                if local(child.tag) != "sheet":
                    continue
                name = child.attrib.get("name")
                rid = next((value for key, value in child.attrib.items() if local(key) == "id"), None)
                if rid not in targets:
                    raise ValueError(f"XLSX relationship for sheet {name} is missing")
                target = targets[rid]
                destination = target.lstrip("/") if target.startswith("/") else posixpath.normpath(posixpath.join("xl", target))
                if destination not in archive.namelist():
                    raise ValueError(f"XLSX worksheet part is missing for {name}")
                sheets.append((name, destination))
            if not sheets:
                raise ValueError("XLSX has no declared worksheets")
            names = [name for name, _ in sheets]
            if requested_sheet is None:
                if len(names) != 1:
                    raise ValueError("multiple workbook sheets are present; choose a declared sheet/table mapping instead of guessing: " + ", ".join(names))
                requested_sheet = names[0]
            if requested_sheet not in names:
                raise ValueError("requested workbook sheet is absent; available: " + ", ".join(names))
            root = ET.fromstring(archive.read(dict(sheets)[requested_sheet]))
            matrix = []
            for row in (node for node in root.iter() if local(node.tag) == "row"):
                cells = {}
                for cell in (node for node in row if local(node.tag) == "c"):
                    ref = cell.attrib.get("r")
                    letters = "".join(ch for ch in str(ref) if ch.isalpha()) if ref else ""
                    index = 0
                    for letter in letters.upper():
                        index = index * 26 + ord(letter) - ord("A") + 1
                    if not index:
                        index = len(cells) + 1
                    kind = cell.attrib.get("t")
                    children = list(cell.iter())
                    if kind == "inlineStr":
                        value = "".join(n.text or "" for n in children if local(n.tag) == "t")
                    else:
                        value_node = next((n for n in children if local(n.tag) == "v"), None)
                        value = value_node.text if value_node is not None else None
                        if kind == "s" and value is not None:
                            try:
                                value = shared[int(value)]
                            except (ValueError, IndexError):
                                raise ValueError("invalid shared-string cell in workbook; contents not guessed")
                    cells[index - 1] = value
                if cells:
                    width = max(cells) + 1
                    matrix.append([cells.get(i) for i in range(width)])
            if not matrix:
                raise ValueError(f"sheet {requested_sheet} has no nonempty worksheet rows")
            return matrix, requested_sheet, names
    except (OSError, zipfile.BadZipFile, ET.ParseError) as exc:
        raise ValueError("workbook is not a readable XLSX package: " + str(exc))


def parse_cell(raw, column, spec):
    if isinstance(raw, (int, float)) and not isinstance(raw, bool):
        v, cell_unit = D.num(raw), None
        text = raw
    elif isinstance(raw, dict):
        v, cell_unit = D.num(raw.get("value")), raw.get("unit")
        text = raw.get("value")
    else:
        text = str(raw if raw is not None else "").strip()
        if not text or text.lower() in ("na", "n/a", "nan", "none", "null", "nd", "not reported", "未报告", "未检出"):
            return None, {"kind": "missing", "raw": raw}
        if text.lstrip().startswith(("<", ">", "≤", "≥")):
            return None, {"kind": "censored", "raw": raw,
                           "note": "censoring retained; not coerced to zero or the limit value"}
        parts = NUMBER.match(text.replace(",", ""))
        if not parts:
            return None, {"kind": "unparsed", "raw": raw}
        v, cell_unit = D.num(parts.group(1)), parts.group(2).strip() or None
    target = column.get("target_unit", column.get("unit"))
    if cell_unit and target:
        factor = object_(column.get("unit_conversions")).get(cell_unit)
        if cell_unit == target:
            factor = 1.0
        if D.num(factor) is None:
            return None, {"kind": "unit_refused", "raw": raw, "unit": cell_unit,
                           "target_unit": target, "requires_explicit_factor": True}
        v *= D.num(factor)
    elif cell_unit and not target:
        return None, {"kind": "unit_unknown", "raw": raw, "unit": cell_unit,
                       "requires_column_unit_or_explicit_conversion": True}
    return v, {"kind": "measurement", "raw": raw,
                "unit": target or column.get("unit") or None}


def source_table(path, sheet=None, mat_variable=None):
    path = Path(path)
    suffix = path.suffix.lower()
    limits = []
    tables = []
    if suffix in (".csv", ".tsv", ".txt"):
        content = path.read_text(encoding="utf-8-sig", errors="strict")
        delimiter = "\t" if suffix == ".tsv" else ","
        data = list(csv.reader(content.splitlines(), delimiter=delimiter))
        tables.append(rows_from_matrix(data))
    elif suffix == ".json":
        raw = json.loads(path.read_text(encoding="utf-8-sig"))
        if isinstance(raw, list):
            tables.append([r for r in raw if isinstance(r, dict)])
        elif isinstance(raw, dict):
            candidates = raw.get("rows", raw.get("records", raw.get("data")))
            if isinstance(candidates, list):
                tables.append([r for r in candidates if isinstance(r, dict)])
            elif isinstance(candidates, dict):
                table = next(((v, k) for k, v in candidates.items() if isinstance(v, list)), None)
                if table:
                    if table[0] and isinstance(table[0][0], dict):
                        tables.append([r for r in table[0] if isinstance(r, dict)])
                    else:
                        tables.append(rows_from_matrix(table[0]))
                        limits.append(f"JSON source was a matrix under {table[1]}")
    elif suffix in (".xlsx", ".xlsm"):
        try:
            import openpyxl
        except (ImportError, OSError):
            matrix, sheet, names = xlsx_standard_library(path, sheet)
            tables.append(rows_from_matrix(matrix))
            limits.append("workbook read via standard-library ZIP/XML read-only fallback; formulas are not recalculated")
        else:
            book = openpyxl.load_workbook(path, read_only=True, data_only=True)
            try:
                names = book.sheetnames
                if sheet is None:
                    if len(names) != 1:
                        raise ValueError("multiple workbook sheets are present; choose a declared sheet/table mapping instead of guessing: " + ", ".join(names))
                    sheet = names[0]
                if sheet not in names:
                    raise ValueError("requested workbook sheet is absent; available: " + ", ".join(names))
                matrix = [list(row) for row in book[sheet].iter_rows(values_only=True)]
                tables.append(rows_from_matrix(matrix))
                limits.append("workbook read with data_only/read_only; formulas are not recalculated by this CLI")
            finally:
                book.close()
    elif suffix == ".mat":
        try:
            import scipy.io
        except (ImportError, OSError) as exc:
            raise ValueError(".mat input requires scipy.io for this version; complex MATLAB mappings may need an explicit extraction step: " + str(exc))
        raw = scipy.io.loadmat(path, squeeze_me=False, struct_as_record=False)
        public = [(k, v) for k, v in raw.items() if not k.startswith("__")]
        if mat_variable is None:
            ranked = sorted(public, key=lambda kv: len(kv[0]))
            if len(ranked) != 1:
                raise ValueError("MATLAB file needs an explicit mat_variable/source-column mapping; variables present: " + ", ".join(k for k, _ in public))
            mat_variable, data = ranked[0]
        else:
            if mat_variable not in raw:
                raise ValueError("mat_variable not in file; available: " + ", ".join(k for k, _ in public))
            data = raw[mat_variable]
        names = getattr(getattr(data, "dtype", None), "names", None)
        if names:
            converted = data.reshape(-1).tolist()
            table = []
            for record in converted:
                if isinstance(record, dict):
                    table.append(record)
                elif hasattr(record, "dtype") and record.dtype.names:
                    table.append({name: getattr(record, name).item() if hasattr(getattr(record, name), "item") else getattr(record, name) for name in record.dtype.names})
            if not table:
                raise ValueError(f"MATLAB variable {mat_variable} has structured fields but no scalar rows; provide explicit cell/field mapping")
            tables.append(table)
            limits.append(f"MATLAB structured source: {', '.join(names)}; scientific meaning must be supplied by caller")
        elif hasattr(data, "tolist"):
            simple = data.tolist()
            if not isinstance(simple, list) or (simple and isinstance(simple[0], str)):
                simple = [simple]
            simple = [r if isinstance(r, list) else [r] for r in simple]
            matrix = [[f"column_{i + 1}" for i in range(max((len(r) for r in simple), default=0))]] + simple
            tables.append(rows_from_matrix(matrix))
            limits.append(f"MATLAB numeric matrix columns are unnamed column_N; declare response/group roles explicitly, source variable={mat_variable}")
        else:
            raise ValueError("unsupported MATLAB source type; no data inferred from its label")
    else:
        raise ValueError("unsupported source format. Use csv/tsv/json; .xlsx/.xlsm needs openpyxl; numeric/tabular .mat needs scipy")
    rows = [r for table in tables for r in table]
    if not rows:
        raise ValueError("the selected source/sheet/table contains zero interpretable rows")
    return rows, {"source_path": str(path), "format": suffix, "sheet": sheet,
                  "mat_variable": mat_variable, "n_rows": len(rows), "limits": limits,
                  "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}


def infer_columns(rows, cfg):
    stated = list_records(cfg.get("columns"))
    definitions = object_(cfg.get("column_units"))
    claimed = {str(c.get("name")): dict(c) for c in stated if c.get("name")}
    for k, unit in definitions.items():
        claimed.setdefault(k, {"name": k, "unit": unit})
    names = []
    for row in rows:
        for key in row:
            if key not in names:
                names.append(key)
    columns = []
    for name in names:
        column = claimed.get(name, {"name": name})
        if name not in claimed:
            hints = any(h.lower() in name.lower() for h in GROUP_HINTS)
            numeric_seen = any(parse_cell(row.get(name), column, cfg)[0] is not None for row in rows)
            column["semantic"] = "categorical" if hints or not numeric_seen else "response"
        columns.append(column)
    return columns


def spec_rows(input_rows, cfg, source_record):
    columns = infer_columns(input_rows, cfg)
    measures = [c for c in columns if c.get("semantic") == "response" or c.get("target_unit") or c.get("plausible")]
    requested = cfg.get("response_columns")
    if isinstance(requested, list):
        measures = [c for c in columns if c["name"] in requested]
    elif isinstance(requested, str):
        measures = [c for c in columns if c["name"] == requested]
    group_names = cfg.get("group_by") or cfg.get("anomaly_group_by") or []
    if isinstance(group_names, str):
        group_names = [group_names]
    group_names = [x for x in group_names if isinstance(x, str)]
    if not group_names and isinstance(cfg.get("anomaly_group_by"), list):
        group_names = cfg["anomaly_group_by"]
    rows, discarded = [], []
    for i, row in enumerate(input_rows):
        values, cell_kinds, troubles = {}, {}, []
        converted = {}
        for column in columns:
            name = column["name"]
            if str(column.get("semantic", "")).lower() in ("id", "text", "categorical"):
                raw = row.get(name)
                value = raw if raw is not None and str(raw).strip() else None
                detail = {"kind": "category", "raw": raw} if value is not None else {"kind": "missing", "raw": raw}
            else:
                value, detail = parse_cell(row.get(name), column, cfg)
            values[name] = value
            cell_kinds[name] = {k: v for k, v in detail.items() if k != "raw"}
            if value is None:
                troubles.append({"column": name, **detail})
            elif detail["kind"] == "measurement":
                converted[name] = value
        group_key = {name: str(row.get(name)) for name in group_names}
        row_index = i + 2 if source_record.get("format") != "inline" else i
        rows.append({"row_index": row_index, "original": copy.deepcopy(row), "values": values,
                     "converted_numeric": converted, "cell_kinds": cell_kinds,
                     "source": {"file": source_record.get("source_path", "inline"), "row": row_index,
                                "sheet": source_record.get("sheet")},
                     "group_key": group_key, "parse_problems": troubles})
    return rows, columns, group_names


def main_analysis(input_rows, cfg, source_record=None):
    source_record = source_record or {"source_path": "inline", "format": "inline", "limits": []}
    if not isinstance(cfg, dict):
        raise ValueError("analysis spec must be an object")
    rows, columns, declared_groups = spec_rows(input_rows, cfg, source_record)
    if not rows:
        raise ValueError("no source rows to interpret")
    response_names = [c["name"] for c in columns if c.get("semantic") == "response" or c.get("target_unit") or c.get("plausible")]
    requested = cfg.get("response_columns")
    if isinstance(requested, (list, str)):
        response_names = [x for x in [requested] if isinstance(x, str)] if isinstance(requested, str) else [x for x in requested if isinstance(x, str)]
    order = object_(cfg.get("trend")).get("order_column") or cfg.get("order_column")
    if not requested:
        response_names = [name for name in response_names if name != order]
    units = object_(cfg.get("column_units"))
    findings, limits = [], list(source_record.get("limits", []))
    available_columns = {c["name"] for c in columns}
    missing_responses = [name for name in response_names if name not in available_columns]
    if missing_responses and len(missing_responses) == len(response_names):
        raise ValueError("none of the declared response columns exist in the actual table schema: " + ", ".join(missing_responses))
    if missing_responses:
        findings.append({"rule": "analysis.missing_response_column", "severity": "medium",
                          "columns": missing_responses, "message": "requested responses absent from the source remain explicitly unanalysed"})
        response_names = [name for name in response_names if name in available_columns]
    if order and order not in available_columns:
        raise ValueError("declared trend/ordering column is absent from the actual table: " + str(order))
    # Source-cell anomalies never delete a record or manufacture a replacement.
    all_parse_problems = [(r, p) for r in rows for p in r["parse_problems"]]
    failures = [p for r, p in all_parse_problems if p["kind"] not in ("missing", "censored")]
    if failures:
        findings.append({"rule": "analysis.unparsed_or_ambiguous_cells", "severity": "medium",
                          "message": "some response cells cannot be safely interpreted without unit/structure declarations",
                          "count": len(failures)})
    if any(p["kind"] == "censored" for r, p in all_parse_problems):
        limits.append("censored/<LOD cells remain named censored; no numeric bound value or zero was substituted")
    # Data row index within input is retained on every flagged event.
    bounds = cfg.get("anomaly_rules") if isinstance(cfg.get("anomaly_rules"), dict) else {}
    min_n = int(D.num(bounds.get("min_n", 6)) or 6)
    iqr_k = D.num(bounds.get("iqr_k", 3.0)) or 3.0
    anomalies = []
    for response in response_names:
        for r in rows:
            r["numeric"] = D.num(r["values"].get(response))
        anomalies += D.robust_anomalies(rows, response, min_n=max(3, min_n), iqr_k=iqr_k)
        for column in columns:
            if column["name"] != response or not isinstance(column.get("plausible"), (tuple, list)):
                continue
            bounds_raw = column["plausible"]
            if len(bounds_raw) != 2 or any(D.num(x) is None for x in bounds_raw):
                limits.append(f"invalid plausible range for {response}: not interpreted")
                continue
            low, high = D.num(bounds_raw[0]), D.num(bounds_raw[1])
            for r in rows:
                v = D.num(r["values"].get(response))
                if v is not None and not low <= v <= high:
                    anomalies.append({"anomaly_id": f"row-{r['row_index']}-{response}-physical", "response": response,
                        "row_index": r["row_index"], "value": v, "source": r["source"],
                        "group": r["group_key"], "detection_rule": "declared_physical_range",
                        "fence": [low, high], "threshold_source": column.get("plausible_source") or column.get("source"),
                        "deviation_from_median": None, "robust_effect": None,
                        "retained_in_primary_analysis": True,
                        "retention_decision": "physical range finding; do not delete without a prespecified audited reason"})
    # Preserve the first data anomaly per detector; source refs remain independent.
    anomalies.sort(key=lambda a: (a["response"], a["row_index"], a["detection_rule"]))
    trends = []
    if order:
        for response in response_names:
            column = next(c for c in columns if c["name"] == response)
            trends.append(D.deseason_trend(rows, response, order,
                tolerance=column.get("trend_slope_tolerance"),
                xunit=units.get(order, next((c.get("unit") for c in columns if c["name"] == order), None)),
                yunit=units.get(response, column.get("unit"))))
    elif cfg.get("require_trend"):
        findings.append({"rule": "analysis.trend_order_missing", "severity": "medium",
                          "message": "no declared order column; do not convert unordered row order into a time/dose trend"})
    comparisons = []
    # Every comparison is evaluated in the declared response's own units.
    for comp in list_records(cfg.get("comparisons")):
        response = comp.get("response") if comp.get("response") in response_names else response_names[0] if len(response_names) == 1 else None
        group_column = comp.get("group_column") or (declared_groups[0] if len(declared_groups) == 1 else None)
        left, right, pair_key = comp.get("left"), comp.get("right"), comp.get("pair_by")
        if response is None or group_column is None or left is None or right is None:
            findings.append({"rule": "analysis.incomplete_comparison", "severity": "medium",
                              "message": "a comparison needs response, group_column, left and right; none inferred silently", "declaration": comp})
            continue
        # A separate metric can be used per comparison without mixing columns.
        for r in rows:
            r["numeric"] = D.num(r["values"].get(response))
        lg = [r for r in rows if str(r["original"].get(group_column)) == str(left)]
        rg = [r for r in rows if str(r["original"].get(group_column)) == str(right)]
        if not lg or not rg:
            limits.append(f"comparison {left} versus {right} lacks one designated group; no effect inferred")
            continue
        result = D.effect(lg + rg, lg, rg, pair_key, dict(comp, response=response, left=left, right=right))
        if result:
            if result.get("comparison_type") == "ambiguous_pairing":
                findings.append({"rule": "analysis.ambiguous_pairing", "severity": "medium",
                                  "message": "duplicate pair identifiers cannot be collapsed by last-row-wins; preserve the ambiguity or explicitly average technical repeats",
                                  "pair_by": pair_key})
            response_name = response
            result["suspicious_point_influence"] = D.sensitivity([r for r in rows if str(r["original"].get(group_column)) in (str(left), str(right))],
                                                               response_name, lg, rg, anomalies)
            comparisons.append(result)
    process_control = []
    spc = object_(cfg.get("spc"))
    if spc.get("enabled"):
        for response in response_names:
            local = dict(object_(spc.get("per_response", {})).get(response, {k: v for k, v in spc.items() if k not in ("enabled", "per_response")}))
            for r in rows:
                r["numeric"] = D.num(r["values"].get(response))
            spc_result = D.spc(rows, response, local, order)
            spc_result.setdefault("events", [])
            process_control.append(spc_result)
        if any(x.get("status") in ("unconfigured", "insufficient_baseline", "degenerate_sigma") for x in process_control):
            limits.append("one or more SPC diagnostics lack a valid declared reference; no automated control claim was substituted")
    hypotheses = build_hypotheses(anomalies, cfg)
    verify = [h["falsification_test"] for h in hypotheses]
    if any(not h.get("falsification_test") or not h["falsification_test"].get("falsifies_if") for h in list_records(cfg.get("cause_candidates"))):
        findings.append({"rule": "analysis.hypothesis_unfalsifiable", "severity": "medium",
                          "message": "one or more declared causes lacks an executable falsification criterion"})
    if anomalies:
        findings.append({"rule": "analysis.anomaly_review_required", "severity": "low", "count": len(anomalies),
                          "message": "anomalies are recorded and retained; reviewed treatment is required, not silent removal"})
    sources = [source_record] + [{"locator": a["source"], "value": a["value"], "response": a["response"]} for a in anomalies]
    reasons = sorted({f["severity"] for f in findings})
    status = "blocked" if "high" in reasons else "review" if "medium" in reasons else "clean"
    result = {"schema_version": VERSION, "status": status,
              "delivery_status": {"clean": "done", "review": "partial", "blocked": "failed"}[status],
              "findings": findings, "limits": limits,
              "sources": sources, "uncertainty": [
                  "source units, replicate independence and threshold provenance must be checked before using the interpretation",
                  "a robust/control-rule flag is not a causal diagnosis; each hypothesis retains falsification criteria"],
              "interpretation": {
                  "result_trends": trends,
                  "anomaly_points": anomalies,
                  "possible_causes": hypotheses,
                  "review_steps": verify,
                  "next_experiments": [h.get("validation_experiment") for h in hypotheses if h.get("validation_experiment")]},
              "observed_vs_inferred": {
                  "observed": [{"source": a["source"], "row": a["row_index"], "measurement": a["value"]} for a in anomalies],
                  "computed_statistics": {"effects": comparisons, "spc": process_control,
                                           "trend_rows": [t.get("source_rows") for t in trends]},
                  "inferences": [{"kind": "unverified_hypothesis", "hypothesis_id": h["hypothesis_id"]} for h in hypotheses]},
              "effect_sizes": comparisons,
              "statistical_process_control": process_control,
              "measurement_tables": {"source_rows": len(rows), "original_values_retained": True,
                    "rows_with_parse_problems": len([r for r in rows if r["parse_problems"]]),
                    "row_schema": [{"row_index": r["row_index"], "original": r["original"],
                                    "source": r["source"], "parse_problems": r["parse_problems"],
                                    "cell_kinds": r["cell_kinds"]} for r in rows],
                    "all_original_rows_even_when_flagged": True},
              "evidence_and_risks": {"detector": bounds, "comparisons": comparisons,
                    "spc": process_control, "do_not_delete_anomalies_by_default": True,
                    "causal_boundary": "association/chronology/control differences alone do not establish causality"},
              "confirmation_items": [{"row": a["row_index"], "response": a["response"],
                    "rule": a["detection_rule"], "source": a["source"],
                    "review_not_delete": True} for a in anomalies],
              "reproducibility": {"engine": "scripts/result_analysis.py + result_diagnostics.py",
                    "formula_version": "robust_IQR_MAD_SPC_OLS_effects/v1",
                    "deterministic": True, "seed": None,
                    "source_record": source_record,
                    "spec_sha256": hashlib.sha256(json.dumps(cfg, ensure_ascii=False, sort_keys=True,
                        separators=(",", ":")).encode("utf-8")).hexdigest()},
              "reference_methods": [{"name": "NIST control charts and 3 sigma/sequence investigations",
                    "source": "https://www.itl.nist.gov/div898/handbook/pmc/section3/pmc31.htm",
                    "implemented_here": "independently declared baseline centerline/sigma, declared order, 3 sigma, same-side runs, monotonic run"},
                   {"name": "robust IQR/MAD, effect size and influence sensitivity",
                    "source": "local pure-Python result_diagnostics implementation",
                    "implemented_here": "grouped robust fences, robust effects, paired/unpaired uncertainty, all-row versus flagged-exclusion sensitivity"}]}
    return result


def build_hypotheses(anomalies, cfg):
    out, known = [], set()
    for i, h in enumerate(list_records(cfg.get("cause_candidates"))):
        supports = h.get("supporting_evidence") or h.get("supports") or []
        if isinstance(supports, str):
            supports = [supports]
        contra = h.get("contradicting_evidence") or h.get("contradictions") or []
        if isinstance(contra, str):
            contra = [contra]
        hypothesis_id = h.get("hypothesis_id", f"declared-{i + 1}")
        known.add(hypothesis_id)
        test = h.get("falsification_test") or {
            "action": f"repeat the exact source and matched-control comparison for {hypothesis_id}",
            "falsifies_if": h.get("would_be_refuted_if"),
            "source": h.get("source"), "then": "if falsified, lower priority and update the competing hypotheses"}
        out.append({"hypothesis_id": hypothesis_id, "statement": h.get("factor") or h.get("statement"),
            "class": h.get("class") or "undeclared", "priority": "only ranked by explicitly supplied supporting evidence, not certainty",
            "supporting_evidence": supports, "contradicting_evidence": contra,
            "falsification_test": test, "validation_experiment": h.get("validation_experiment"),
            "observation_status": "candidate, not observed cause"})
    out.sort(key=lambda h: (-len(h["supporting_evidence"]), str(h["hypothesis_id"])))
    declared_domain = str(cfg.get("domain") or cfg.get("domain_type") or cfg.get("experiment_domain") or "").lower()
    classes = ["technical", "methodological"]
    if declared_domain in ("biological", "bio", "wet_lab", "wet-lab", "biology", "生物"):
        classes.append("biological")
    for a in anomalies[:20]:
        for kind in classes:
            hid = f"{a['anomaly_id']}:{kind}"
            if hid in known:
                continue
            known.add(hid)
            target = a["source"]
            if kind == "technical":
                reason = "a data-entry, sensor/channel, clock or logging mismatch remains possible"
                action = f"re-read raw value at {target}; compare the actual source timestamp/channel/batch metadata and duplicate acquisition log"
                falsifies = "source record agrees with normalized value and paired acquisition/instrument logs agree without missing steps"
            elif kind == "methodological":
                reason = "pre-processing, unit conversion, comparator choice, or grouping can create a difference"
                action = f"recompute {a['response']} at {target} in original units; compare the prespecified control and matched technical repeats"
                falsifies = "all normalization and group allocations are correct while the departure remains across independent repeats"
            else:
                reason = "a genuine condition/sample difference remains a competing hypothesis, not its causal proof"
                action = f"review {target}; propose an independent, controlled source repeat with unchanged technical settings"
                falsifies = "independent matched repeats under unchanged settings do not reproduce the difference; remaining confounders require separate comparison"
            out.append({"hypothesis_id": hid, "statement": reason, "class": kind,
                "priority": "unranked alternative: only anomaly evidence, no cause attribution",
                "supporting_evidence": [f"row {a['row_index']} triggered {a['detection_rule']}; this supports an anomaly search only"],
                "contradicting_evidence": [],
                "falsification_test": {"action": action, "falsifies_if": falsifies,
                    "source": target, "reason": "executable evidence update, not cosmetic replot"},
                "validation_experiment": {"action": "if permitted and pre-specified, run the matched controlled repeat identified by the falsification test",
                    "controls": "same raw measurement pathway, predefined comparison and acceptance criterion; do not discard flagged values",
                    "precondition": "resource/safety/sample availability are unknown unless the case supplies them",
                    "success_or_failure_changes_hypothesis": "record both outcomes and rank competing causes again"},
                "observation_status": "hypothesis, never direct observation"})
    return out


def bind_contract(result, spec, case):
    case = object_(case)
    cid = spec.get("case_id", case.get("case_id", case.get("id")))
    if cid is not None:
        result["case_id"] = cid
    oc = spec.get("output_contract", case.get("output_contract"))
    keys = list(oc) if isinstance(oc, dict) else oc if isinstance(oc, list) else []
    if oc is not None and not isinstance(oc, (dict, list)):
        result["limits"].append("output_contract is neither an object nor a list of field names")
    for key in [k for k in keys if isinstance(k, str)]:
        if key in result:
            continue
        value = spec.get(key, case.get(key))
        if value is not None and key not in ("rows", "table_path", "spec", "observations", "output_contract"):
            result[key] = copy.deepcopy(value)
        else:
            result[key] = None
            result["limits"].append(f"output_contract field '{key}' was not derivable by the analysis")
    return result


def refusal(out, message, spec=None, case=None):
    r = {"schema_version": VERSION, "status": "undetermined", "delivery_status": "failed",
         "findings": [{"rule": "analysis.input_error", "severity": "high", "message": str(message)}],
         "sources": [], "uncertainty": [str(message)],
         "interpretation": {"result_trends": [], "anomaly_points": [], "possible_causes": [],
                              "review_steps": [], "next_experiments": []},
         "limits": [str(message)]}
    bind_contract(r, object_(spec), case)
    out.mkdir(parents=True, exist_ok=True)
    (out / "result.json").write_text(json.dumps(r, ensure_ascii=False, indent=2), encoding="utf-8")
    return r


def build(spec_path=None, out=Path("/app/output"), case_path=None, table=None, sheet=None, mat_variable=None):
    spec, case = {}, None
    if case_path:
        try:
            case = json.loads(Path(case_path).read_text(encoding="utf-8-sig"))
        except Exception as exc:
            return refusal(out, "original case cannot be read: " + str(exc))
    try:
        if spec_path:
            spec = json.loads(Path(spec_path).read_text(encoding="utf-8-sig"))
            if isinstance(spec, dict) and isinstance(spec.get("spec"), dict):
                spec = spec["spec"]
            if not isinstance(spec, dict):
                raise ValueError("spec must be a JSON object")
        if table is not None:
            spec["table_path"] = str(table)
        if sheet is not None:
            spec["sheet"] = sheet
        if mat_variable is not None:
            spec["mat_variable"] = mat_variable
        if isinstance(case, dict):
            spec.setdefault("case_id", case.get("case_id", case.get("id")))
            spec.setdefault("output_contract", case.get("output_contract"))
        if isinstance(spec.get("rows"), list):
            rows = [r for r in spec["rows"] if isinstance(r, dict)]
            source_record = {"source_path": "inline", "format": "inline", "n_rows": len(rows), "sheet": None}
        else:
            table = spec.get("table_path") or spec.get("source_path")
            if not table:
                raise ValueError("no data supplied: rows or table_path required; an explicit workbook/MAT variable mapping may also be required")
            path = Path(table)
            if not path.is_absolute() and spec_path:
                path = Path(spec_path).parent / path
            raw_rows, source_record = source_table(path, spec.get("sheet"), spec.get("mat_variable"))
            rows = raw_rows
        if not rows:
            raise ValueError("no records after source-table extraction; no missing science invented")
        result = main_analysis(rows, spec, source_record)
        bind_contract(result, spec, case)
        out.mkdir(parents=True, exist_ok=True)
        (out / "result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")
        (out / "original-records.json").write_text(json.dumps(rows, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
        # An auditable, lossless copy of every source cell; the primary result never hides it.
        with (out / "original-table.csv").open("w", newline="", encoding="utf-8-sig") as handle:
            from csv import DictWriter
            keys = list(dict.fromkeys(k for r in rows for k in r))
            writer = DictWriter(handle, fieldnames=keys, extrasaction="ignore")
            writer.writeheader()
            for r in rows:
                writer.writerow({k: json.dumps(r.get(k), ensure_ascii=False) if isinstance(r.get(k), (dict, list)) else r.get(k) for k in keys})
        return result
    except (ValueError, TypeError, KeyError, OSError, ImportError, ArithmeticError) as exc:
        return refusal(out, exc, spec, case)


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--spec", help="JSON analysis specification/inline rows; optional with --table")
    p.add_argument("--case", help="original /input/case.json for case_id/output_contract")
    p.add_argument("--table", help="override table_path with a real csv/tsv/json/xlsx/mat file")
    p.add_argument("--sheet", help="required explicit workbook sheet when multiple exist")
    p.add_argument("--mat-variable", help="explicit MATLAB variable for simple numeric/tabular conversion")
    p.add_argument("--out", required=True)
    a = p.parse_args(argv)
    r = build(Path(a.spec) if a.spec else None, Path(a.out), a.case, a.table, a.sheet, a.mat_variable)
    print(json.dumps({"status": r["status"], "anomalies": len(r.get("interpretation", {}).get("anomaly_points", [])),
                      "comparisons": len(r.get("effect_sizes", [])),
                      "result": str(Path(a.out) / "result.json")}, ensure_ascii=False))
    return {"clean": 0, "review": 3, "blocked": 4, "undetermined": 5}.get(r["status"], 1)


if __name__ == "__main__":
    raise SystemExit(main())
