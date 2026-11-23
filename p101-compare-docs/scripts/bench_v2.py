"""Three-suite author verification for compare_workorder.py (synthetic data only)."""
from __future__ import annotations

import argparse
import copy
import json
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
CLI = HERE / "compare_workorder.py"


def base_fixture():
    sources = {"documents": [
        {"document_id": "D1", "publication_type": "journal_article", "paragraphs": [
            {"paragraph_id": "T1-R2", "page": 4, "section": "Results", "table_id": "T1", "row": 2, "column": "rate",
             "text": "For catalyst X on dye A at 24 h, the measured rate was 1000 mg/L."},
            {"paragraph_id": "P20", "page": 5, "section": "Methods", "text": "The catalyst dose budget was 1 mg/mL for every run."}]},
        {"document_id": "D2", "publication_type": "journal_article", "paragraphs": [
            {"paragraph_id": "T2-R1", "page": 3, "section": "Results", "table_id": "T2", "row": 1, "column": "rate",
             "text": "At 24 h, catalyst X removed dye A at a measured rate of 1 g/L under the same protocol."},
            {"paragraph_id": "P8", "page": 2, "section": "Methods", "text": "We used a 1 mg/mL catalyst dose budget and the 2024 reference split."}]}]}
    alignment = {"question_id": "Q1", "entity": "catalyst-X", "time": "24 h", "metric": "removal-rate",
                 "units": "g/L", "material": "catalyst-X", "pollutant": "dye-A", "budget": "1 mg/mL", "dataset": "reference-2024"}
    cells = [
        {"cell_id": "C1", "doc_id": "D1", "field_id": "rate", "status": "reported", "value": 1000,
         "unit": "mg/L", "normalized_value": 1.0, "comparable": True, "alignment": dict(alignment),
         "evidence": {"source_document_id": "D1", "paragraph_id": "T1-R2", "quote": "1000 mg/L"}},
        {"cell_id": "C2", "doc_id": "D2", "field_id": "rate", "status": "reported", "value": 1.0,
         "unit": "g/L", "normalized_value": 1.0, "comparable": True, "alignment": dict(alignment),
         "evidence": {"source_document_id": "D2", "paragraph_id": "T2-R1", "quote": "1 g/L"}},]
    return sources, cells, alignment


def case_data():
    return {"case_id": "synthetic-compare-契约-01", "output_contract": [
        "comparison_table", "synthesis", "status",
        {"field": "operator_note"}, {"name": "case_carried"}],
        "case_carried": {"verbatim": [1, 2, 3]}}


def workorder_data():
    return {"workorder_id": "WO-SYTH-1", "field_ids": ["rate"],
            "fields": [{"field_id": "rate", "group": "metric", "definition": "24-hour dye-A removal rate",
                        "target_unit": "g/L"}]}


def matrix_data(cells):
    return {"documents": [{"doc_id": "D1"}, {"doc_id": "D2"}],
            "field_defs": [{"field_id": "rate", "group": "metric", "definition": "24-hour dye-A removal rate", "target_unit": "g/L"}],
            "cells": cells, "synthesis": [{"field_id": "rate", "relation": "consensus", "cell_ids": ["C1", "C2"],
                                                "difference_causes": [], "evidence_strength": "strong", "pooling_decision": "allowed"}]}


def cjk_fixture():
    sources = {"documents": [
        {"document_id": "甲", "paragraphs": [{"paragraph_id": "结果-2", "page": 8, "section": "结果", "text": "在相同剂量下，甲材料使降解率显著提高。"},
                                           {"paragraph_id": "方法-2", "page": 4, "section": "方法", "text": "甲组使用新鲜批次，反应温度为 25 °C。"}]},
        {"document_id": "乙", "paragraphs": [{"paragraph_id": "结果-4", "page": 6, "section": "结果", "text": "在相同剂量下，乙材料使降解率显著下降。"},
                                           {"paragraph_id": "方法-4", "page": 3, "section": "方法", "text": "乙组使用储存一年的批次，反应温度为 25 °C。"}]}]}
    keys = {"question_id": "问题1", "entity": "光催化剂", "time": "24 小时", "metric": "降解方向",
            "units": "not_applicable", "material": "同系列光催化剂", "pollutant": "染料A", "budget": "1 mg/mL", "dataset": "2024 分割"}
    cells = [
        {"cell_id": "中1", "doc_id": "甲", "field_id": "trend", "status": "reported", "value": "提高", "unit": "not_applicable",
         "direction": "increases", "strength": "strong", "alignment": dict(keys),
         "evidence": {"source_document_id": "甲", "paragraph_id": "结果-2", "quote": "使降解率显著提高"}},
        {"cell_id": "中2", "doc_id": "乙", "field_id": "trend", "status": "reported", "value": "下降", "unit": "not_applicable",
         "direction": "decreases", "strength": "strong", "alignment": dict(keys),
         "evidence": {"source_document_id": "乙", "paragraph_id": "结果-4", "quote": "使降解率显著下降"}}]
    matrix = {"documents": [{"doc_id": "甲"}, {"doc_id": "乙"}],
              "field_defs": [{"field_id": "trend", "group": "conclusion", "definition": "对染料A降解率的影响方向"}],
              "cells": cells, "synthesis": [{"field_id": "trend", "relation": "conflict", "cell_ids": ["中1", "中2"],
                  "evidence_strength": "moderate", "pooling_decision": "forbidden",
                  "difference_causes": [{"kind": "condition", "explanation": "新鲜批次与储存一年批次不同",
                      "evidence": [{"source_document_id": "甲", "paragraph_id": "方法-2", "quote": "使用新鲜批次"},
                                   {"source_document_id": "乙", "paragraph_id": "方法-4", "quote": "使用储存一年的批次"}]}]}]}
    workorder = {"fields": [{"field_id": "trend", "group": "conclusion", "definition": "对染料A降解率的影响方向"}]}
    return sources, workorder, matrix


def write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def run(root: Path, name: str, case, workorder, matrix, sources, raw_case=None):
    folder = root / name
    folder.mkdir()
    write_json(folder / "case.json", case)
    write_json(folder / "comparison-workorder.json", workorder)
    write_json(folder / "matrix.json", matrix)
    write_json(folder / "sources.json", sources)
    if raw_case is not None:
        (folder / "case.json").write_text(raw_case, encoding="utf-8")
    cmd = [sys.executable, "-I", str(CLI), "--case", str(folder / "case.json"), "--workorder",
           str(folder / "comparison-workorder.json"), "--matrix", str(folder / "matrix.json"),
           "--sources", str(folder / "sources.json"), "--out", str(folder / "out")]
    proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", timeout=45)
    result_path = folder / "out" / "result.json"
    result = json.loads(result_path.read_text(encoding="utf-8")) if result_path.exists() else {}
    return proc, result, result_path


def expect(results, name, condition, detail=""):
    results.append({"name": name, "pass": bool(condition), "detail": detail})
    if not condition:
        print("FAIL", name, detail)


def functional(root):
    results = []
    sources, cells, _ = base_fixture()
    proc, result, _ = run(root, "clean_units", case_data(), workorder_data(), matrix_data(cells), sources)
    expect(results, "clean unit conversion + top-level contract", proc.returncode == 0 and result["status"] == "success" and not result["findings"]
           and result["case_id"] == "synthetic-compare-契约-01" and result["case_carried"] == {"verbatim": [1, 2, 3]}
           and result["operator_note"] is None and result["comparison_table"] and "output_contract_fields" in result,
           proc.stderr + str(result.get("findings")))
    sources2, wo2, matrix2 = cjk_fixture()
    proc, result, _ = run(root, "clean_cjk_conflict", case_data(), wo2, matrix2, sources2)
    expect(results, "CJK conflict consensus/cause/evidence", proc.returncode == 0 and not result["findings"]
           and result["synthesis"][0]["relation"] == "conflict", proc.stderr + str(result.get("findings")))
    sources3, cells3, _ = base_fixture()
    cells3[1] = {"cell_id": "C2", "doc_id": "D2", "field_id": "rate", "status": "not_reported", "search_note": "searched Results, Table 2 and supplement"}
    matrix3 = matrix_data(cells3)
    matrix3["synthesis"] = [{"field_id": "rate", "relation": "insufficient_evidence", "cell_ids": ["C1", "C2"],
                             "evidence_strength": "insufficient", "pooling_decision": "forbidden", "difference_causes": []}]
    proc, result, _ = run(root, "clean_not_reported", case_data(), workorder_data(), matrix3, sources3)
    expect(results, "honest not_reported remains a complete answer", proc.returncode == 0 and result["status"] == "success"
           and result["uncertainty"], proc.stderr + str(result.get("findings")))
    return results


def hostile(root):
    results = []
    scenarios = []
    def scenario(name, mutate, rule, code=4):
        sources, cells, _ = base_fixture()
        matrix = matrix_data(cells)
        mutate(matrix, cells)
        scenarios.append((name, sources, matrix, rule, code))
    scenario("wrong_conversion", lambda m, c: c[0].update(normalized_value=1000), "compare.conversion_unreproducible")
    scenario("missing_grid", lambda m, c: c.pop(), "compare.grid_cell_missing")
    scenario("wrong_paper", lambda m, c: c[0]["evidence"].update(source_document_id="D2", paragraph_id="T2-R1", quote="1 g/L"), "compare.wrong_source")
    scenario("false_consensus", lambda m, c: c[1].update(value=2, normalized_value=2), "compare.consensus_misstated")
    scenario("pool_different_dataset", lambda m, c: c[1]["alignment"].update(dataset="other-split"), "compare.alignment_mismatch_pooled")
    scenario("conflict_without_cause", lambda m, c: (c[1].update(value=2, normalized_value=2), m["synthesis"][0].update(relation="conflict")), "compare.conflict_unattributed")
    scenario("divergence_hidden_as_insufficient", lambda m, c: (c[1].update(value=2, normalized_value=2), m["synthesis"][0].update(relation="insufficient_evidence", pooling_decision="forbidden")), "compare.divergence_unclassified")
    for name, sources, matrix, rule, code in scenarios:
        proc, result, _ = run(root, name, case_data(), workorder_data(), matrix, sources)
        rules = {x.get("rule") for x in result.get("findings", [])}
        expect(results, name, proc.returncode == code and rule in rules and "Traceback" not in proc.stderr, f"rc={proc.returncode} rules={rules} stderr={proc.stderr}")
    proc, result, path = run(root, "malformed", case_data(), workorder_data(), {}, {}, raw_case="{broken")
    expect(results, "malformed structured refusal", proc.returncode == 5 and result["status"] == "undetermined"
           and result["case_id"] is None and result["findings"] and "Traceback" not in proc.stderr, proc.stderr)
    sources, cells, _ = base_fixture()
    proc1, result1, path1 = run(root, "idempotent", case_data(), workorder_data(), matrix_data(cells), sources)
    cmd = [sys.executable, "-I", str(CLI), "--case", str(path1.parent.parent / "case.json"), "--workorder",
           str(path1.parent.parent / "comparison-workorder.json"), "--matrix", str(path1.parent.parent / "matrix.json"),
           "--sources", str(path1.parent.parent / "sources.json"), "--out", str(path1.parent)]
    first = path1.read_bytes()
    proc2 = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", timeout=45)
    expect(results, "idempotent full artifacts", proc1.returncode == proc2.returncode == 0 and first == path1.read_bytes(), proc2.stderr)
    return results


def smoke(root):
    results = []
    # Multi-entity partial conflict: values are comparable only after explicit conversion;
    # old and fresh samples are not pooled and difference evidence is required.
    sources, wo, matrix = cjk_fixture()
    matrix["documents"] = list(matrix["documents"])
    matrix["field_defs"][0]["definition"] = "真实感 smoke：同一问题、对象、时间、单位与污染物下的方向冲突"
    proc, result, out_path = run(root, "realistic_smoke", case_data(), wo, matrix, sources)
    cards = json.loads((out_path.parent / "evidence_cards.json").read_text(encoding="utf-8"))
    expect(results, "cold CLI + realistic quote provenance + artifacts", proc.returncode == 0 and len(cards) == 2
           and all(x["evidence"]["found"] and x["evidence"]["page"] for x in cards)
           and (out_path.parent / "comparison_table.json").exists(), proc.stderr + str(result.get("findings")))
    # Cold module import in isolated mode, with no cwd/package bytecode dependency.
    import_cmd = [sys.executable, "-I", "-c", "import importlib.util; p=r'%s'; s=importlib.util.spec_from_file_location('cmp_v2', p); m=importlib.util.module_from_spec(s); s.loader.exec_module(m); assert set(m.RELATIONS)=={'consensus','partial','conflict','insufficient_evidence'}" % CLI]
    cold = subprocess.run(import_cmd, cwd=str(root), capture_output=True, text=True, encoding="utf-8", timeout=30)
    expect(results, "cold import", cold.returncode == 0 and "Traceback" not in cold.stderr, cold.stderr)
    return results


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--suite", choices=["functional", "hostile", "smoke", "all"], default="all")
    args = ap.parse_args()
    suites = ["functional", "hostile", "smoke"] if args.suite == "all" else [args.suite]
    all_results = []
    with tempfile.TemporaryDirectory(prefix="compare-v2-bench-") as tmp:
        root = Path(tmp)
        for suite in suites:
            all_results.extend(globals()[suite](root))
    passed = sum(x["pass"] for x in all_results)
    summary = {"suite": args.suite, "passed": passed, "total": len(all_results), "failed": len(all_results) - passed}
    print(json.dumps(summary, ensure_ascii=False))
    return 0 if passed == len(all_results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
