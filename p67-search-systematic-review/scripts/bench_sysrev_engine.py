"""Full PRISMA/quality/meta regression battery; synthetic records only."""
from __future__ import annotations

import copy
import importlib.util
import json
import math
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import sysrev_engine as E  # noqa: E402

ROOT = HERE.parent
BASE = json.loads((ROOT / "examples" / "sysrev-spec.json").read_text(encoding="utf-8"))
CASE = json.loads((ROOT / "examples" / "case.json").read_text(encoding="utf-8"))
CLI = HERE / "sysrevrun.py"
NAMES = ["research_product", "search_protocol", "prisma_flow", "screening_log", "quality_appraisals",
         "quality_summary", "evidence_matrix", "synthesis_claims", "heterogeneity", "meta_analysis",
         "research_gaps", "uncertainties", "deliverables"]


def spec(): return copy.deepcopy(BASE)
def record(data, rid): return next(row for row in data["records"] if row.get("report_id") == rid)
def quality(data, sid): return next(row for row in data["quality_appraisals"] if row["study_id"] == sid)
def rules(result): return {row["rule"] for row in result.get("findings", [])}
def close(a, b): return math.isclose(a, b, rel_tol=1e-8, abs_tol=1e-8)


def run_cli(tmp, data=None, case=CASE, raw_spec=None):
    tmp.mkdir(parents=True, exist_ok=True)
    source = tmp / "spec.json"
    source.write_text(raw_spec if raw_spec is not None else json.dumps(data or spec(), ensure_ascii=False), encoding="utf-8")
    case_file = tmp / "case.json"
    if case is not None: case_file.write_text(json.dumps(case, ensure_ascii=False), encoding="utf-8")
    out = tmp / "out"
    args = [sys.executable, "-B", "-I", "-X", "utf8", str(CLI), "--spec", str(source), "--out", str(out)]
    if case is not None: args += ["--case", str(case_file)]
    proc = subprocess.run(args, capture_output=True, text=True, timeout=60)
    path = out / "result.json"
    result = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    return proc, result, out


def clean(tmp, name):
    r = E.analyze(spec()); c = r["prisma_flow"]["counts"]
    expected = {"identified":8,"malformed":0,"duplicates":1,"records_screened":7,"records_excluded":1,
                "reports_sought":6,"reports_not_retrieved":1,"reports_assessed":5,"reports_excluded":1,
                "reports_included":4,"studies_included":4}
    return (r["status"] == "clean" and not r["findings"] and all(c[k] == v for k,v in expected.items())
            and all(r["prisma_flow"]["checks"].values()) and r["prisma_flow"]["complete"]
            and len(r["meta_analysis"]) == 2)


def artifacts_contract(tmp, name):
    p,r,out = run_cli(tmp)
    expected = {"systematic_review.md","search_protocol.csv","screening_log.csv","prisma_flow.csv",
                "quality_appraisal.csv","evidence_matrix.csv","evidence_synthesis.csv","heterogeneity.csv","result.json"}
    return (p.returncode == 0 and expected == {x.name for x in out.iterdir()}
            and r["output_contract_fields"] == NAMES and all(r.get(k) is not None for k in NAMES)
            and r["case_id"] == CASE["case_id"] and r["output_contract"] == CASE["output_contract"]
            and len(r["artifacts"]) == 8 and len(r["prisma_flow"]["rows"]) == 15)


def exact_meta_parameters(tmp, name):
    r = E.analyze(spec()); pain, function = r["meta_analysis"]
    return (close(pain["Q"],5.2) and close(pain["I2_percent"],100*4.2/5.2)
            and close(pain["random_effects_DL"]["tau2"],0.6825)
            and close(pain["random_effects_DL"]["estimate"],-0.5807692307692308)
            and not pain["headline_allowed"]
            and close(function["Q"],0.08839779005524878) and function["I2_percent"] == 0
            and close(function["random_effects_DL"]["estimate"],4.979005524861878)
            and function["headline_allowed"])


def prospective_all_null(tmp, name):
    data = spec(); data["search_protocol"]["status"] = "prospective"
    data["records"] = []; data["quality_appraisals"] = []; data["synthesis_claims"] = []; data["research_gaps"] = []
    r = E.analyze(data)
    return (r["status"] == "review" and "sr.prospective_protocol_only" in rules(r)
            and all(value is None for value in r["prisma_flow"]["counts"].values())
            and not r["prisma_flow"]["complete"] and any(row["kind"] == "prospective_only" for row in r["uncertainties"])
            and r["citation_coverage"]["included_reports"] == 0)


def prospective_fake_hits(tmp, name):
    data = spec(); data["search_protocol"]["status"] = "prospective"
    data["search_protocol"]["databases"][0]["hit_count"] = 0
    r = E.analyze(data)
    return "sr.unexecuted_hit_count" in rules(r) and r["status"] == "blocked"


def executed_export_mismatch(tmp, name):
    data = spec(); data["search_protocol"]["status"] = "executed"
    data["search_protocol"]["databases"][0]["hit_count"] = 4
    data["search_protocol"]["databases"][1]["hit_count"] = 999
    r = E.analyze(data)
    return "sr.export_count_mismatch" in rules(r) and r["status"] == "blocked"


def malformed_rows_arithmetic(tmp, name):
    data = spec(); data["records"] += [None,"bad"]
    r = E.analyze(data); c = r["prisma_flow"]["counts"]
    return (c["identified"] == 10 and c["malformed"] == 2 and r["prisma_flow"]["checks"]["identification_closes"]
            and "sr.record_invalid" in rules(r) and r["status"] == "blocked")


def ta_reason_required(tmp, name):
    data = spec(); record(data,"X1")["ta_reason"] = ""
    r = E.analyze(data)
    return "sr.ta_exclusion_reason_missing" in rules(r)


def reviewer_conflict_detected(tmp, name):
    data = spec(); record(data,"R1")["ta_reviews"] = [{"reviewer":"A","decision":"include"},{"reviewer":"B","decision":"exclude"}]
    r = E.analyze(data)
    return "sr.review_conflict_unresolved" in rules(r)


def reviewer_adjudication_replays(tmp, name):
    data = spec(); r1 = record(data,"R1")
    r1["ta_reviews"] = [{"reviewer":"A","decision":"include"},{"reviewer":"B","decision":"exclude"}]
    r1["ta_adjudication"] = {"reviewer":"C","decision":"include","reason":"原文符合冻结设计条款"}
    r = E.analyze(data)
    return r["status"] == "clean" and any(row["kind"] == "reviewer_disagreement" for row in r["uncertainties"])


def not_retrieved_reason(tmp, name):
    data = spec(); record(data,"X3")["retrieval_reason"] = ""
    r = E.analyze(data)
    return "sr.not_retrieved_reason_missing" in rules(r) and r["prisma_flow"]["counts"]["reports_not_retrieved"] == 1


def quality_domain_required(tmp, name):
    data = spec(); quality(data,"S1")["domains"] = quality(data,"S1")["domains"][:-1]
    r = E.analyze(data)
    return "sr.quality_domain_coverage" in rules(r)


def quality_overall_mismatch(tmp, name):
    data = spec(); quality(data,"S1")["overall_reported"] = "high"
    r = E.analyze(data)
    return "sr.quality_overall_mismatch" in rules(r)


def quality_unweighted_summary(tmp, name):
    r = E.analyze(spec()); d3 = next(row for row in r["quality_summary"]["by_domain"] if row["tool_domain"] == "ROB2:D3")
    return (d3["n"] == 4 and d3["counts"] == {"low":3,"high":1}
            and close(d3["proportions"]["high"],0.25) and r["quality_summary"]["overall"]["counts"] == {"low":2,"high":1,"some_concerns":1})


def quote_tamper(tmp, name):
    data = spec(); record(data,"R1")["evidence"][0]["quote"] = "fabricated quote"
    r = E.analyze(data)
    return "sr.quote_not_in_source" in rules(r)


def cross_report_reference(tmp, name):
    data = spec(); record(data,"R1")["field_evidence"]["method"] = ["R2:M"]
    r = E.analyze(data)
    return "sr.field_evidence_cross_report" in rules(r)


def incomplete_effect_is_narrative(tmp, name):
    data = spec(); del record(data,"R2")["effect"]["se"]
    r = E.analyze(data); meta = next(row for row in r["heterogeneity"] if row["comparison_key"] == "exercise_vs_care_pain_12w")["meta_analysis"]
    return not meta["computed"] and "positive standard error" in meta["reason"] and len(r["meta_analysis"]) == 1


def no_selective_subset_pool(tmp, name):
    data = spec(); del record(data,"R1")["effect"]
    r = E.analyze(data); meta = next(row for row in r["heterogeneity"] if row["comparison_key"] == "exercise_vs_care_pain_12w")["meta_analysis"]
    return not meta["computed"] and meta["k"] == 2


def risk_sensitivity(tmp, name):
    r = E.analyze(spec()); c1,c2 = r["synthesis_claims"]
    return (c1["sensitivity_changed"] and c1["primary_study_ids_after_risk_filter"] == ["S1"]
            and not c2["sensitivity_changed"] and c2["computed_strength"] == "established_within_scope")


def conflict_must_be_two_sided(tmp, name):
    data = spec(); data["synthesis_claims"][0]["type"] = "synthesis"; data["synthesis_claims"][0]["contradicting_evidence_refs"] = []
    r = E.analyze(data)
    return {"sr.claim_omits_opposing_reports","sr.conflict_unaddressed"} <= rules(r)


def multi_report_study_not_double_counted(tmp, name):
    data = spec(); secondary = copy.deepcopy(record(data,"R1")); old_to_new = "R1B"
    secondary["report_id"] = old_to_new; secondary["synthesis_role"] = "secondary"; secondary["context_only"] = True
    secondary["title"] = "Synthetic Trial A Secondary Report"; secondary["doi"] = "synthetic-r1-secondary"
    secondary["evidence"] = []
    for ev in record(data,"R1")["evidence"]:
        new_ev = copy.deepcopy(ev); new_ev["id"] = ev["id"].replace("R1:","R1B:"); secondary["evidence"].append(new_ev)
    secondary["field_evidence"] = {key:[ref.replace("R1:","R1B:") for ref in refs] for key,refs in secondary["field_evidence"].items()}
    secondary["effect"]["evidence_ref"] = "R1B:E"
    data["records"].append(secondary)
    r = E.analyze(data); c = r["prisma_flow"]["counts"]
    return (r["status"] == "clean" and c["reports_included"] == 5 and c["studies_included"] == 4
            and all(row["k"] == 2 for row in r["meta_analysis"]))


def included_coverage_audit(tmp, name):
    data = spec(); data["synthesis_claims"] = data["synthesis_claims"][:1]
    r = E.analyze(data)
    return ("sr.included_report_not_synthesized" in rules(r)
            and set(r["citation_coverage"]["uncited_report_ids"]) == {"R3","R4"})


def fixed_empty_blocked(tmp, name):
    data = spec(); data["records"] = []; data["quality_appraisals"] = []; data["synthesis_claims"] = []; data["research_gaps"] = []
    r = E.analyze(data)
    return "sr.records_missing" in rules(r) and r["status"] == "blocked"


def refusal_contract(tmp, name):
    p,r,_ = run_cli(tmp,raw_spec="{bad")
    return (p.returncode == 5 and r["status"] == "undetermined" and r["case_id"] == CASE["case_id"]
            and r["output_contract_fields"] == NAMES and all(k in r for k in NAMES) and "Traceback" not in p.stderr)


def idempotent_bytes(tmp, name):
    p1,_,out = run_cli(tmp); one = {x.name:x.read_bytes() for x in out.iterdir() if x.is_file()}
    p2 = subprocess.run([sys.executable,"-B","-I","-X","utf8",str(CLI),"--spec",str(tmp/"spec.json"),
                         "--case",str(tmp/"case.json"),"--out",str(out)],capture_output=True,text=True,timeout=60)
    two = {x.name:x.read_bytes() for x in out.iterdir() if x.is_file()}
    return p1.returncode == p2.returncode == 0 and one == two


def cold_import(tmp, name):
    module_path = HERE / "sysrev_engine.py"; loaded = importlib.util.spec_from_file_location("cold_sysrev_engine",module_path)
    module = importlib.util.module_from_spec(loaded); loaded.loader.exec_module(module)
    r = module.analyze(spec())
    return r["status"] == "clean" and len(r["meta_analysis"]) == 2


SCENARIOS = [
 ("clean_baseline",clean),("artifacts_and_contract",artifacts_contract),("exact_meta_parameters",exact_meta_parameters),
 ("prospective_all_null",prospective_all_null),("prospective_fake_hits",prospective_fake_hits),
 ("executed_export_mismatch",executed_export_mismatch),("malformed_rows_arithmetic",malformed_rows_arithmetic),
 ("ta_reason_required",ta_reason_required),("reviewer_conflict_detected",reviewer_conflict_detected),
 ("reviewer_adjudication_replays",reviewer_adjudication_replays),("not_retrieved_reason",not_retrieved_reason),
 ("quality_domain_required",quality_domain_required),("quality_overall_mismatch",quality_overall_mismatch),
 ("quality_unweighted_summary",quality_unweighted_summary),("quote_tamper",quote_tamper),
 ("cross_report_reference",cross_report_reference),("incomplete_effect_is_narrative",incomplete_effect_is_narrative),
 ("no_selective_subset_pool",no_selective_subset_pool),("risk_sensitivity",risk_sensitivity),
 ("conflict_must_be_two_sided",conflict_must_be_two_sided),("multi_report_study_not_double_counted",multi_report_study_not_double_counted),
 ("included_coverage_audit",included_coverage_audit),("fixed_empty_blocked",fixed_empty_blocked),
 ("refusal_contract",refusal_contract),("idempotent_bytes",idempotent_bytes),("cold_import",cold_import),
]


def main():
    rows=[]
    with tempfile.TemporaryDirectory() as td:
        root=Path(td)
        for pos,(name,fn) in enumerate(SCENARIOS):
            try: ok,why=bool(fn(root/f"{pos:02d}_{name}",name)),""
            except Exception as exc: ok,why=False,f"raised {type(exc).__name__}: {exc}"
            rows.append({"scenario":name,"pass":ok,"why":why}); print(("PASS" if ok else "FAIL")+f"  {name:<42}"+why)
    passed=sum(row["pass"] for row in rows)
    report={"schema_version":"sysrev-engine-bench/v2","synthetic_only":True,"scenarios":rows,"totals":{"passed":passed,"of":len(rows)}}
    (HERE/"report_sysrev_engine.json").write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
    print(f"\n{passed}/{len(rows)} scenarios pass")
    return 0 if passed==len(rows) else 1


if __name__ == "__main__": raise SystemExit(main())
