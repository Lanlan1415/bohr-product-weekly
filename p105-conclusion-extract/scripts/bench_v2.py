"""Functional, hostile/contract and realistic suites for extract_workorder.py."""
from __future__ import annotations

import argparse
import copy
import json
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
CLI = HERE / "extract_workorder.py"


def status(status_name, **kwargs):
    return {"status": status_name, **kwargs}


def anchor(pid, quote, doc="P1"):
    return {"source_document_id": doc, "paragraph_id": pid, "quote": quote}


def numeric_item():
    ev = anchor("R-12", "12% higher uptake")
    return {"field_id": "uptake", "status": "reported", "scalar": 12,
            "claim_kind": "conclusion", "claim_form": "associational", "endpoint_match": "exact",
            "evidence": [ev],
            "unit": status("reported", value="%", evidence=[anchor("R-12", "%")]),
            "statistic": status("reported", test="Welch t-test", p_value="0.002", confidence_interval="95% CI 5–19",
                                effect_measure="percentage-point uptake difference",
                                evidence=[anchor("R-12", "p = 0.002")]),
            "experimental_condition": status("reported", summary="25 °C for 24 h", evidence=[anchor("R-12", "25 °C for 24 h")]),
            "comparator": status("reported", name="treatment B", evidence=[anchor("R-12", "treatment B")]),
            "sample": status("reported", population="mice", groups=[
                {"name": "treatment A", "n": 6, "unit": "mice", "role": "intervention"},
                {"name": "treatment B", "n": 6, "unit": "mice", "role": "comparator"}],
                evidence=[anchor("R-12", "6 mice per group")]),
            "endpoint": status("reported", name="24-hour cellular uptake", evidence=[anchor("R-12", "uptake")]),
            "uncertainty": status("reported", hedged=False, qualifiers=[], error_type="95% CI", error_value="5–19",
                                  evidence=[anchor("R-12", "95% CI 5–19")]),
            "statistical_basis": status("reported", analysis_population="all randomized mice", aggregation="mean difference",
                                        test="Welch t-test", p_value="0.002", multiple_testing="single prespecified endpoint")}


def cjk_item():
    return {"field_id": "direction_zh", "status": "reported", "scalar": "可能提高摄取",
            "claim_kind": "speculation", "claim_form": "descriptive", "endpoint_match": "alias",
            "endpoint_mapping_note": "提高摄取是摄取率的方向性表述，未替代效应量",
            "evidence": [anchor("讨论-3", "可能提高摄取", "中文源")],
            "unit": status("not_applicable", reason="仅方向性结论，无数值或物理单位"),
            "statistic": status("not_reported", search_note="结果段与讨论段均未见检验统计量"),
            "experimental_condition": status("reported", summary="单一浓度", evidence=[anchor("讨论-3", "仅观察到一个浓度", "中文源")]),
            "comparator": status("not_applicable", reason="作者只报告单组方向性推测，未给比较组"),
            "sample": status("not_reported", search_note="方法节和结果节均未报告样本量"),
            "endpoint": status("reported", name="细胞摄取方向", evidence=[anchor("讨论-3", "摄取", "中文源")]),
            "uncertainty": status("reported", hedged=True, qualifiers=["可能", "单一浓度"], error_type=None,
                                  evidence=[anchor("讨论-3", "可能", "中文源")]),
            "statistical_basis": status("not_reported", search_note="未报告检验、置信区间或多重比较口径")}


def sources_data():
    return {"documents": [
        {"document_id": "P1", "publication_type": "journal_article", "version": "accepted-manuscript", "paragraphs": [
            {"paragraph_id": "R-12", "page": 7, "section": "Results", "table_id": "T2", "row": 4, "column": "effect",
             "text": "Treatment A was associated with 12% higher uptake than treatment B (95% CI 5–19; p = 0.002), in 6 mice per group at 25 °C for 24 h."}]},
        {"document_id": "中文源", "publication_type": "journal_article", "paragraphs": [
            {"paragraph_id": "讨论-3", "page": 9, "section": "讨论",
             "text": "结果提示涂层可能提高摄取，但仅观察到一个浓度，因此不能外推到其他剂量。"}]}]}


def target_data():
    return {"fields": [{"field_id": "uptake", "field_type": "metric", "endpoint": "24-hour cellular uptake"},
                       {"field_id": "direction_zh", "field_type": "conclusion"},
                       {"field_id": "adverse_events", "field_type": "metric", "endpoint": "adverse event rate"}]}


def case_data():
    return {"case_id": "synthetic-extract-01", "output_contract": {"fields": "array", "status": "string",
            "case_carried": "object", "unresolved": "object"}, "case_carried": {"keep": True}}


def extraction_data():
    return {"fields": [numeric_item(), cjk_item(),
                       {"field_id": "adverse_events", "status": "not_reported",
                        "search_note": "searched abstract, Results, Table 3 and supplement; no adverse-event endpoint"}]}


def write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def run(root, name, case=None, targets=None, extraction=None, sources=None, raw_case=None):
    case = case if case is not None else case_data()
    targets = targets if targets is not None else target_data()
    extraction = extraction if extraction is not None else extraction_data()
    sources = sources if sources is not None else sources_data()
    folder = root / name
    folder.mkdir()
    write_json(folder / "case.json", case)
    write_json(folder / "target-fields.json", targets)
    write_json(folder / "extraction.json", extraction)
    write_json(folder / "sources.json", sources)
    if raw_case is not None:
        (folder / "case.json").write_text(raw_case, encoding="utf-8")
    out = folder / "out"
    cmd = [sys.executable, "-I", str(CLI), "--case", str(folder / "case.json"), "--targets", str(folder / "target-fields.json"),
           "--extraction", str(folder / "extraction.json"), "--sources", str(folder / "sources.json"), "--out", str(out)]
    proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", timeout=45)
    result = json.loads((out / "result.json").read_text(encoding="utf-8")) if (out / "result.json").exists() else {}
    return proc, result, out


def expect(results, name, condition, detail=""):
    results.append({"name": name, "pass": bool(condition), "detail": detail})
    if not condition:
        print("FAIL", name, detail)


def functional(root):
    results = []
    proc, result, out = run(root, "clean")
    expect(results, "clean all requested fields + CJK + gap + contract", proc.returncode == 0 and result["status"] == "success"
           and not result["findings"] and len(result["fields"]) == 3 and result["case_carried"] == {"keep": True}
           and result["unresolved"] is None and result["fields"][1]["uncertainty"]["hedged"] is True,
           proc.stderr + str(result.get("findings")))
    # Original values are retained even when a faithful optional conversion is added.
    extraction = extraction_data()
    extraction["fields"][0]["normalized_scalar"] = 0.12
    extraction["fields"][0]["normalized_unit"] = "fraction"
    proc, result, out = run(root, "conversion_guard", extraction=extraction)
    expect(results, "explicit raw-to-normalized path cannot silently change raw value", proc.returncode == 4
           and result["fields"][0]["scalar"] == 12 and "extract.unit_conversion_unavailable" in {x["rule"] for x in result["findings"]},
           proc.stderr + str(result.get("findings")))
    same = matrix = extraction_data()
    same["fields"][0]["normalized_scalar"] = 12.0
    same["fields"][0]["normalized_unit"] = "%"
    proc, result, out = run(root, "same_unit_conversion", extraction=same)
    expect(results, "reproducible explicit conversion", proc.returncode == 0 and result["fields"][0]["conversion"]["factor"] == 1.0,
           proc.stderr + str(result.get("findings")))
    return results


def hostile(root):
    results = []
    scenarios = []
    def add(name, mutate, rule):
        data = extraction_data()
        mutate(data)
        scenarios.append((name, data, rule))
    add("association_to_causal", lambda d: d["fields"][0].update(claim_form="causal"), "extract.association_promoted_to_causal")
    add("hedge_dropped", lambda d: d["fields"][1]["uncertainty"].update(hedged=False), "extract.hedge_dropped")
    add("endpoint_substitution", lambda d: d["fields"][0].update(endpoint_match="different"), "extract.endpoint_substituted")
    add("requested_field_missing", lambda d: d["fields"].pop(), "extract.requested_field_missing")
    add("wrong_numeric", lambda d: d["fields"][0].update(scalar=13), "extract.scalar_not_in_evidence")
    add("statistic_dropped", lambda d: (d["fields"][0]["statistic"].pop("p_value"), d["fields"][0]["statistical_basis"].pop("p_value")), "extract.statistic_dropped")
    add("bad_quote", lambda d: d["fields"][0]["evidence"][0].update(quote="13% lower uptake"), "evidence.quote_not_in_source")
    add("one_sided_conflict", lambda d: d["fields"][0].update(status="source_conflict", conflicts=d["fields"][0]["evidence"]), "extract.conflict_not_two_sided")
    add("unit_fabricated", lambda d: d["fields"][0]["unit"].update(value="mg/L"), "extract.unit_not_in_evidence")
    add("group_size_changed", lambda d: d["fields"][0]["sample"]["groups"][0].update(n=8), "extract.group_size_not_in_evidence")
    for name, data, rule in scenarios:
        proc, result, _ = run(root, name, extraction=data)
        rules = {x["rule"] for x in result.get("findings", [])}
        expect(results, name, proc.returncode == 4 and rule in rules and "Traceback" not in proc.stderr,
               f"rc={proc.returncode} rules={rules} stderr={proc.stderr}")
    proc, result, _ = run(root, "malformed", raw_case="{broken")
    expect(results, "malformed case refusal", proc.returncode == 5 and result["status"] == "undetermined"
           and result["case_id"] is None and "Traceback" not in proc.stderr, proc.stderr)
    proc1, result1, out = run(root, "idem")
    path = out / "result.json"
    first = path.read_bytes()
    cmd = [sys.executable, "-I", str(CLI), "--case", str(out.parent / "case.json"), "--targets", str(out.parent / "target-fields.json"),
           "--extraction", str(out.parent / "extraction.json"), "--sources", str(out.parent / "sources.json"), "--out", str(out)]
    proc2 = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", timeout=45)
    expect(results, "idempotent rerun", proc1.returncode == proc2.returncode == 0 and first == path.read_bytes(), proc2.stderr)
    return results


def smoke(root):
    results = []
    proc, result, out = run(root, "realistic")
    artifact = json.loads((out / "field_table.json").read_text(encoding="utf-8"))
    numeric = artifact[0]
    expect(results, "realistic sample/groups/units/statistics/source locators", proc.returncode == 0
           and [g["n"] for g in numeric["sample"]["groups"]] == [6, 6]
           and numeric["statistic"]["p_value"] == "0.002" and numeric["unit"]["value"] == "%"
           and numeric["evidence"][0]["page"] == 7 and numeric["evidence"][0]["char_start"] is not None,
           proc.stderr + str(result.get("findings")))
    cold_cmd = [sys.executable, "-I", "-c", "import importlib.util; p=r'%s'; s=importlib.util.spec_from_file_location('x_v2',p); m=importlib.util.module_from_spec(s); s.loader.exec_module(m); assert 'reported' in m.STATUSES" % CLI]
    cold = subprocess.run(cold_cmd, cwd=str(root), capture_output=True, text=True, encoding="utf-8", timeout=30)
    expect(results, "cold isolated import", cold.returncode == 0 and "Traceback" not in cold.stderr, cold.stderr)
    return results


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--suite", choices=["functional", "hostile", "smoke", "all"], default="all")
    args = ap.parse_args()
    suites = ["functional", "hostile", "smoke"] if args.suite == "all" else [args.suite]
    results = []
    with tempfile.TemporaryDirectory(prefix="extract-v2-bench-") as tmp:
        for suite in suites:
            results.extend(globals()[suite](Path(tmp)))
    passed = sum(x["pass"] for x in results)
    print(json.dumps({"suite": args.suite, "passed": passed, "total": len(results), "failed": len(results) - passed}, ensure_ascii=False))
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
