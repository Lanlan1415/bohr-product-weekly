"""Opt-in research commercialization regression suite; synthetic fixtures only."""
from __future__ import annotations

import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
import commercial_transfer as CT  # noqa: E402
import sections as S  # noqa: E402

SOURCE = ("In the lab, a porous coating increased uptake 3-fold from 2 mg/g to 6 mg/g "
          "(Fig 3b) [doe2020], using 12 lab samples. Only one coating thickness was tested.")
TEXT = ("多孔涂层将吸附量提高 3 倍。实验中，涂层使吸附量由 2 mg/g 增至 6 mg/g"
        "（Fig. 3b），使用 12 个实验室样本 [doe2020]。仅在一种涂层厚度下完成验证，"
        "尚不能外推为量产效果。外部调研摘要称“两个中试用户各有 20 万元年度试验预算”"
        " [mkt2025]。在同样实验条件下，目标是在 2 年内将单批处理成本从 1000 元降到 800 元；"
        "这是按“1000 × 0.80 = 800 元”得到的商业估算，不是论文实测结果 [a-value]。"
        "中试、第三方复测和知识产权核查仍是放大门槛。"
        "痛点是实验室成果缺少可复核的放大验证与成本路径；拟分阶段推进，而非宣称立即产业化。")

BASE = {
    "case_id": "synthetic-transfer-clean",
    "section": "dissemination",
    "audience": "industry pilot team",
    "source_text": SOURCE,
    "text": TEXT,
    "evidence": ["doe2020"],
    "key_conclusions": ["多孔涂层将吸附量提高 3 倍"],
    "limitations": "only one coating thickness was tested; no production-scale evidence",
    "open_questions": [],
    "changes": [{"action": "将实验结果与转化条件、估算分开陈述",
                 "reason": "避免把论文事实和商业假设混写"}],
    "transfer_profile": {
        "scientific_facts": [
            {"id": "lab01", "claim": "实验室多孔涂层吸附量由 2 mg/g 增至 6 mg/g",
             "claim_type": "research_fact", "source_locator": "paper:Fig.3b",
             "source_excerpt": "increased uptake 3-fold from 2 mg/g to 6 mg/g"}
        ],
        "pain_points": [
            {"id": "pain1", "problem": "实验室成果缺少放大验证与成本路径",
             "user": "中试团队", "claim_type": "commercial_assumption",
             "basis": "由论文实验室局限形成的待访谈需求假设",
             "uncertainty": "还需用户访谈确认这是否是付费痛点"}
        ],
        "technology_maturity": {"level": "TRL4", "status": "research_fact",
                                "scope": "12 个实验室样本、一种涂层厚度、实验室条件",
                                "evidence_refs": ["lab01"]},
        "intellectual_property": [
            {"type": "patent_application", "status": "patent_pending",
             "owner": "研究单位（合成 fixture）", "reference": "CN-SYNTHETIC-001",
             "claim_type": "external_evidence"}
        ],
        "validation": [
            {"id": "val01", "environment": "实验室、一种涂层厚度",
             "sample_or_scale": "12 lab samples", "baseline": "2 mg/g",
             "result": "6 mg/g（3-fold，Fig.3b）", "evidence_refs": ["lab01"]}
        ],
        "applications": [
            {"id": "app01", "scenario": "同类多孔材料的中试吸附处理",
             "user": "中试团队", "conditions": "同种材料和厚度，完成中试与第三方复测后再放大",
             "painpoint_refs": ["pain1"]}
        ],
        "market": {
            "evidence": [
                {"id": "mkt2025", "claim": "两个中试用户各有 20 万元年度试验预算",
                 "status": "external_evidence",
                 "source_excerpt": "两个中试用户各有 20 万元年度试验预算",
                 "locator": "Synthetic Partner Interview Note mkt-2025, p.1"}
            ],
            "competitors": [
                {"name": "现有涂层工艺",
                 "comparison_axis": "同一条件下的吸附基准与单批成本（需对照复测）",
                 "evidence_refs": ["lab01"]}
            ],
            "unknowns": ["目标地区渗透率、实际采购转化率和竞争对手报价尚无材料"]
        },
        "commercial_assumptions": [
            {"id": "a-value", "claim": "2 年内单批处理成本可由 1000 元降至 800 元",
             "status": "commercial_assumption",
             "basis": "1000 × 0.80 = 800 元；价格、良率和采购量仅作待验证估算",
             "uncertainty": "中试产量、良率和报价变化都会改变估算"}
        ],
        "roadmap": [
            {"stage": "中试方案设计", "owner": "技术负责人",
             "milestone": "形成样本量和评价口径一致的中试方案", "resources": "中试装置、材料和分析人员",
             "success_gate": "双方确认中试指标和采样方案", "stop_condition": "材料或装置与实验条件不兼容"},
            {"stage": "第三方复测与决策", "owner": "项目负责人",
             "milestone": "完成第三方复测与知识产权核查", "resources": "独立检测机构和法律顾问",
             "success_gate": "复测达预设指标并完成权属确认", "stop_condition": "未达阈值或权属不能确认则停止"}
        ],
        "risks": [
            {"risk": "实验室结果不能放大", "likelihood": "中高", "impact": "高",
             "mitigation": "分阶段中试并独立复测", "trigger": "关键指标连续低于方案阈值", "owner": "技术负责人"},
            {"risk": "预算或权属假设不成立", "likelihood": "中", "impact": "高",
             "mitigation": "报价复核与法律尽调", "trigger": "预算证据过期或权属文件缺失", "owner": "项目负责人"}
        ],
        "quantified_value": [
            {"id": "qv01", "metric": "单批处理成本", "baseline": "1000 元", "target": "800 元",
             "unit": "元/批", "time_horizon": "2 年", "method": "1000 × 0.80 = 800 元",
             "status": "commercial_assumption", "basis": "1000 × 0.80 = 800 元，暂不承诺实现",
             "uncertainty": "实际中试规模和良率可能改变结果", "evidence_refs": []}
        ]
    },
    "output_contract": {
        "case_id": "identifier", "status": "run state", "rewrite": "full transfer draft",
        "target_text": "editable draft", "deliverable": "target artifact",
        "evidence_map": "fact/source mapping", "transfer_assessment": "fact vs assumption summary",
        "technology_maturity": "TRL and scope", "intellectual_property": "IP state",
        "validation": "validation evidence", "market": "market and competitors",
        "roadmap": "implementation route", "risks": "risk register", "quantified_value": "value",
        "boundary": "open questions and limits",
        "editor_review": {"decision": "human decision", "comments": "human notes"}
    },
    "limits": [],
}


def rules(spec):
    findings, status, _ = S.run(spec, "dissemination")
    return [x["rule"] for x in findings], status


def run_case(case_path: Path, out: Path, spec=False):
    proc = subprocess.run(
        [sys.executable, "-I", "-B", str(ROOT / "secrun.py"),
         "--spec" if spec else "--case", str(case_path), "--out", str(out)],
        capture_output=True, text=True, timeout=120)
    path = out / "result.json"
    result = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    return proc, result, path


def main():
    rows = []

    def check(name, condition, detail=""):
        rows.append({"scenario": name, "pass": bool(condition), "detail": detail})
        print(f"{'PASS' if condition else 'FAIL'}  {name:<40} {detail}")

    def defect(name, mutation, expected, forbidden=()):
        spec = copy.deepcopy(BASE)
        mutation(spec)
        found, _ = rules(spec)
        check(name, all(x in found for x in expected) and not any(x in found for x in forbidden),
              str(sorted(set(found))))

    found, status = rules(copy.deepcopy(BASE))
    check("clean_commercial_profile", found == [] and status == "clean", str(found))
    old = copy.deepcopy(BASE)
    old.pop("transfer_profile")
    found, _ = rules(old)
    check("ordinary_outreach_no_commercial_rules", not any(x.startswith("transfer.") for x in found), str(found))
    defect("profile_wrong_type", lambda s: s.update(transfer_profile=[]), ["transfer.profile_malformed"])
    defect("pain_point_removed", lambda s: s["transfer_profile"].update(pain_points=[]),
           ["transfer.pain_point_missing"])
    defect("trl_not_invented", lambda s: s["transfer_profile"]["technology_maturity"].update(level="世界领先"),
           ["transfer.maturity_unjustified"])
    defect("maturity_evidence_orphan",
           lambda s: s["transfer_profile"]["technology_maturity"].update(evidence_refs=["not-a-source"]),
           ["transfer.validation_evidence_missing"])
    defect("ip_owner_missing",
           lambda s: s["transfer_profile"]["intellectual_property"][0].pop("owner"),
           ["transfer.ip_evidence_missing"])
    defect("validation_evidence_removed", lambda s: s["transfer_profile"].update(validation=[]),
           ["transfer.validation_missing"])
    defect("application_not_linked_to_pain",
           lambda s: s["transfer_profile"]["applications"][0].update(painpoint_refs=["other"]),
           ["transfer.application_unbound"])
    defect("external_market_claim_unlocated",
           lambda s: s["transfer_profile"]["market"]["evidence"][0].pop("locator"),
           ["transfer.external_evidence_unlocated"])
    defect("external_market_value_mismatch",
           lambda s: (s["transfer_profile"]["market"]["evidence"][0].update(source_excerpt="two users have 200 元 budgets"),
                      s.update(text=TEXT.replace("20 万元", "200 元"))),
           ["transfer.external_evidence_mismatch"])
    defect("competitor_and_unknown_both_absent",
           lambda s: s["transfer_profile"]["market"].update(competitors=[], unknowns=[]),
           ["transfer.competitor_missing"])
    defect("assumption_basis_missing",
           lambda s: s["transfer_profile"]["commercial_assumptions"][0].update(basis=""),
           ["transfer.assumption_basis_missing"])
    defect("assumption_cannot_cite_orphan",
           lambda s: s["transfer_profile"]["commercial_assumptions"][0].update(
               evidence_refs=["invented-report"]),
           ["transfer.validation_evidence_missing"])
    defect("competitor_cannot_cite_orphan",
           lambda s: s["transfer_profile"]["market"]["competitors"][0].update(
               evidence_refs=["invented-benchmark"]),
           ["transfer.validation_evidence_missing"])
    defect("unsupported_research_fact",
           lambda s: s["transfer_profile"]["scientific_facts"][0].update(source_excerpt="production yield doubled"),
           ["transfer.research_fact_not_in_source"])
    defect("unregistered_new_market_number",
           lambda s: s.update(text=TEXT + " 预计市场规模为 987654 亿元。"),
           ["diss.invariant_added"])
    defect("value_arithmetic_wrong",
           lambda s: s["transfer_profile"]["quantified_value"][0].update(method="1000 × 0.70 = 800 元"),
           ["transfer.value_arithmetic_mismatch"])
    defect("value_baseline_missing",
           lambda s: s["transfer_profile"]["quantified_value"][0].pop("baseline"),
           ["transfer.value_incomplete"])
    defect("roadmap_owner_missing", lambda s: s["transfer_profile"]["roadmap"][0].pop("owner"),
           ["transfer.roadmap_incomplete"])
    defect("risk_register_missing", lambda s: s["transfer_profile"].update(risks=[]),
           ["transfer.risk_missing"])
    defect("malformed_validation_shape", lambda s: s["transfer_profile"].update(validation="N/A"),
           ["transfer.validation_missing"])

    # Unknown TRL/IP is allowed but remains an explicit human review, never a clean fact.
    unknown = copy.deepcopy(BASE)
    unknown["transfer_profile"]["technology_maturity"] = {"level": None, "status": "unknown",
        "scope": "only laboratory evidence supplied", "notes": "actual TRL needs validation",
        "evidence_refs": ["lab01"]}
    unknown["transfer_profile"]["intellectual_property"] = [{"type": "patent_application",
        "status": "unknown", "notes": "owner/registry record not supplied"}]
    found, status = rules(unknown)
    check("unknown_trl_ip_routes_to_human_review",
          "transfer.unresolved_business_boundary" in found and status == "review", str(found))
    check("commercial_summary_distinguishes_fact_and_assumption",
          CT.summary(BASE)["scientific_facts"] == ["lab01"]
          and CT.summary(BASE)["external_evidence"] == ["mkt2025"]
          and CT.summary(BASE)["commercial_assumptions"] == 1)
    check("supported_numbers_never_duplicate_source",
          CT.supported_quantities(BASE)[(800.0, "")] == 1)

    with tempfile.TemporaryDirectory(prefix="commercial_bench_") as td:
        tmp = Path(td)
        case = copy.deepcopy(BASE)
        path = tmp / "case.json"
        path.write_text(json.dumps(case, ensure_ascii=False), encoding="utf-8")
        proc, result, result_path = run_case(path, tmp / "out")
        check("case_cli_clean_full_commercial_contract",
              proc.returncode == 0 and result.get("status") == "clean"
              and all(k in result for k in case["output_contract"])
              and result.get("target_text") == TEXT
              and result.get("rewrite", {}).get("text") == TEXT,
              f"exit={proc.returncode} findings={[x.get('rule') for x in result.get('findings', [])]}")
        check("contract_derives_profile_sections",
              result.get("technology_maturity", {}).get("level") == "TRL4"
              and result.get("intellectual_property") == case["transfer_profile"]["intellectual_property"]
              and result.get("validation") == case["transfer_profile"]["validation"]
              and result.get("quantified_value") == case["transfer_profile"]["quantified_value"])
        check("boundary_and_business_review_available",
              "boundary" in result and "business_and_commercialization_review" in result["boundary"]
              and result.get("transfer_assessment", {}).get("commercial_assumptions") == 1)
        check("nested_contract_shape_preserved",
              set(result.get("editor_review", {})) == {"decision", "comments"}
              and result["editor_review"]["decision"] is None
              and any("editor_review.decision" in x for x in result.get("limits", [])))
        first = result_path.read_bytes()
        proc2, _, _ = run_case(path, tmp / "out")
        check("commercial_rerun_byte_identical", proc2.returncode == 0 and result_path.read_bytes() == first)

        nested = {"case_id": case["case_id"], "output_contract": case["output_contract"],
                  "transfer_profile": case["transfer_profile"],
                  "spec": {k: v for k, v in case.items() if k not in
                           ("case_id", "output_contract", "transfer_profile")}}
        nested_path = tmp / "nested.json"
        nested_path.write_text(json.dumps(nested, ensure_ascii=False), encoding="utf-8")
        p_nested, r_nested, _ = run_case(nested_path, tmp / "out_nested")
        check("nested_spec_and_profile_direct_entry",
              p_nested.returncode == 0 and r_nested.get("case_id") == case["case_id"]
              and r_nested.get("target_text") == TEXT)
        nested["spec"]["section"] = ["dissemination"]
        bad_path = tmp / "bad_section.json"
        bad_path.write_text(json.dumps(nested, ensure_ascii=False), encoding="utf-8")
        p_bad, r_bad, _ = run_case(bad_path, tmp / "out_bad")
        check("refusal_preserves_direct_contract",
              p_bad.returncode == 5 and r_bad.get("status") == "undetermined"
              and all(k in r_bad for k in case["output_contract"])
              and "Traceback" not in p_bad.stderr)
        malformed = tmp / "malformed.json"
        malformed.write_text("{bad", encoding="utf-8")
        p_malformed, r_malformed, _ = run_case(malformed, tmp / "out_malformed")
        check("malformed_case_refusal", p_malformed.returncode == 5
              and r_malformed.get("case_id") is None and "Traceback" not in p_malformed.stderr)
        p_legacy, r_legacy, _ = run_case(path, tmp / "out_legacy", spec=True)
        check("legacy_spec_compatibility", p_legacy.returncode == 0
              and r_legacy.get("status") == "clean")

        cold = subprocess.run(
            [sys.executable, "-I", "-B", "-c",
             "import importlib.util,sys;p=" + repr(str(ROOT / 'commercial_transfer.py')) +
             ";s=importlib.util.spec_from_file_location('cold_transfer',p);"
             "m=importlib.util.module_from_spec(s);sys.path.insert(0," + repr(str(ROOT)) +
             ");s.loader.exec_module(m);print('ok')"],
            capture_output=True, text=True, timeout=120)
        check("cold_isolated_import", cold.returncode == 0 and "ok" in cold.stdout,
              cold.stderr.strip()[:160])

    report = {"schema_version": "commercial-transfer-bench/v1", "fixtures_are_synthetic": True,
              "scenarios": rows, "totals": {"passed": sum(x["pass"] for x in rows), "of": len(rows)}}
    (ROOT / "report_commercial.json").write_text(json.dumps(report, ensure_ascii=False, indent=2),
                                                encoding="utf-8")
    print(f"\n{report['totals']['passed']}/{len(rows)} pass")
    return 0 if all(x["pass"] for x in rows) else 1


if __name__ == "__main__":
    raise SystemExit(main())
