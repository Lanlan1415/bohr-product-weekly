"""Three independent synthetic suites for verify_workorder.py."""
from __future__ import annotations

import argparse
import copy
import json
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
CLI = HERE / "verify_workorder.py"


def anchor(doc, pid, quote):
    return {"source_document_id": doc, "paragraph_id": pid, "quote": quote}


def analysis(polarity="same", comparator="aligned", modality="same", significance="aligned",
             scope="aligned", causality="associational", endpoint="exact", rationale="direct statement and complete local context match"):
    return {"polarity": polarity, "comparator": comparator, "modality": modality, "significance": significance,
            "scope": scope, "causality": causality, "endpoint": endpoint, "rationale": rationale}


def subclaim(sid, statement, verdict, evidence, kind="fact", a=None, strength="moderate", **kwargs):
    return {"sub_id": sid, "kind": kind, "statement": statement, "verdict": verdict,
            "evidence": evidence, "support_analysis": a or analysis(), "evidence_strength": strength, **kwargs}


def draft_data():
    claims = [
        {"claim_id": "C1", "claim_text": "Treatment A had 12% higher uptake than Treatment B in mice at 24 h.",
         "subclaims": [subclaim("C1.1", "Treatment A had 12% higher uptake than Treatment B in mice at 24 h.", "supported",
                                [anchor("D1", "P1", "12% higher uptake")], "comparison", strength="moderate")]},
        {"claim_id": "C2", "claim_text": "Treatment A increases survival in mice.",
         "subclaims": [subclaim("C2.1", "Treatment A increases survival in mice.", "partially_supported",
                                [anchor("D1", "P2", "may improve survival")], "causal",
                                analysis(modality="weaker", significance="not_significant", scope="narrower", causality="associational",
                                         rationale="only a nonsignificant, hedged trend in elderly mice"), "weak",
                                limitations=["elderly mice only", "p = 0.08"])]},
        {"claim_id": "C3", "claim_text": "Treatment A improved memory in aged rats.",
         "subclaims": [subclaim("C3.1", "Treatment A improved memory in aged rats.", "contradicted",
                                [anchor("D2", "P3", "did not improve memory")], "fact",
                                analysis(polarity="opposite", rationale="the direct experiment reports no improvement"), "moderate")]},
        {"claim_id": "C4", "claim_text": "Treatment A cures fibrosis in humans.",
         "subclaims": [subclaim("C4.1", "Treatment A cures fibrosis in humans.", "insufficient_evidence", [], "causal",
                                analysis(polarity="unknown", comparator="unknown", modality="unknown", significance="unknown",
                                         scope="unknown", causality="unknown", endpoint="unknown", rationale="no human fibrosis evidence in supplied materials"),
                                "insufficient", search_note="searched all supplied full text; no human fibrosis experiment or trial",
                                searched_sources=["D1", "D2", "D3"])]},
        {"claim_id": "C5", "claim_text": "Treatment A reduces inflammation after 24 hours.",
         "subclaims": [subclaim("C5.1", "Treatment A reduces inflammation after 24 hours.", "partially_supported",
                                [anchor("D1", "P5", "reduced inflammation after 24 hours")], "causal",
                                analysis(polarity="mixed", significance="unknown", scope="unknown", causality="causal",
                                         rationale="two full-text sources disagree so the claim is qualified"), "weak",
                                conflicts=[anchor("D2", "P4", "did not reduce inflammation after 24 hours")],
                                cross_document_consistency="conflict",
                                conflict_note="D1 reports a reduction while D2 directly reports no reduction after the same time window") ]},
        {"claim_id": "C6", "claim_text": "本实验剂量为 1 g/L。",
         "subclaims": [subclaim("C6.1", "本实验剂量为 1 g/L。", "supported", [anchor("D3", "方法-2", "1000 mg/L")], "fact",
                                analysis(causality="not_applicable", rationale="1 g/L 与 1000 mg/L 的显式换算相等"), "moderate",
                                unit_conversion={"claim_value": 1, "claim_unit": "g/L", "evidence_value": 1000, "evidence_unit": "mg/L"})]},]
    return {"claims": claims}


def workorder_data():
    return {"claims": [{"claim_id": c["claim_id"], "claim_text": c["claim_text"]} for c in draft_data()["claims"]]}


def sources_data():
    return {"documents": [
        {"document_id": "D1", "publication_type": "journal_article", "peer_review_status": "peer_reviewed", "paragraphs": [
            {"paragraph_id": "P1", "page": 7, "section": "Results", "text": "Treatment A was associated with 12% higher uptake than Treatment B (p = 0.002) in mice at 24 h."},
            {"paragraph_id": "P2", "page": 8, "section": "Results", "text": "In elderly mice only, Treatment A may improve survival (p = 0.08)."},
            {"paragraph_id": "P5", "page": 9, "section": "Results", "text": "Treatment A reduced inflammation after 24 hours."}]},
        {"document_id": "D2", "publication_type": "journal_article", "paragraphs": [
            {"paragraph_id": "P3", "page": 6, "section": "Results", "text": "Treatment A did not improve memory in aged rats."},
            {"paragraph_id": "P4", "page": 6, "section": "Results", "text": "Treatment A did not reduce inflammation after 24 hours."}]},
        {"document_id": "D3", "publication_type": "journal_article", "paragraphs": [
            {"paragraph_id": "方法-2", "page": 3, "section": "方法", "text": "本实验剂量为 1000 mg/L，溶液温度为 25 °C。"}]}]}


def case_data():
    return {"case_id": "synthetic-claim-verify-01", "output_contract": ["claims", "evidence_cards", "result_state",
            {"field": "case_carried"}, {"name": "unknown_field"}], "case_carried": [1, {"same": True}]}


def write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def run(root, name, case=None, workorder=None, draft=None, sources=None, raw_case=None):
    case = case if case is not None else case_data()
    workorder = workorder if workorder is not None else workorder_data()
    draft = draft if draft is not None else draft_data()
    sources = sources if sources is not None else sources_data()
    folder = root / name
    folder.mkdir()
    write_json(folder / "case.json", case)
    write_json(folder / "claims-to-verify.json", workorder)
    write_json(folder / "verdicts.json", draft)
    write_json(folder / "sources.json", sources)
    if raw_case is not None:
        (folder / "case.json").write_text(raw_case, encoding="utf-8")
    out = folder / "out"
    cmd = [sys.executable, "-I", str(CLI), "--case", str(folder / "case.json"), "--claims-to-verify", str(folder / "claims-to-verify.json"),
           "--verdicts", str(folder / "verdicts.json"), "--sources", str(folder / "sources.json"), "--out", str(out)]
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
    counts = result.get("checked", {}).get("verdict_counts", {})
    expect(results, "four verdicts + conflict + no evidence + CJK + conversion + contract",
           proc.returncode == 0 and not result["findings"] and counts.get("supported") == 2
           and counts.get("partially_supported") == 2 and counts.get("contradicted") == 1
           and counts.get("insufficient_evidence") == 1 and result["case_carried"] == [1, {"same": True}]
           and result["unknown_field"] is None,
           proc.stderr + str(result.get("findings")))
    expect(results, "unit conversion and no-evidence undetermined are materialized",
           result["claims"][5]["subclaims"][0]["unit_conversion_result"]["ok"] is True
           and result["claims"][3]["subclaims"][0]["verification_status"] == "undetermined"
           and result["checked"]["undetermined"] == 1, str(result.get("checked")))
    return results


def hostile(root):
    results = []
    scenarios = []
    def add(name, mutate, rule):
        data = draft_data()
        mutate(data)
        scenarios.append((name, data, rule))
    # Highly similar sentence with opposite meaning must not become supported.
    add("similar_but_negative", lambda d: (d["claims"][2]["subclaims"][0].update(verdict="supported"),
        d["claims"][2]["subclaims"][0].update(support_analysis=analysis())), "verify.negation_misread")
    add("hedged_upgraded", lambda d: (d["claims"][1]["subclaims"][0].update(verdict="supported"),
        d["claims"][1]["subclaims"][0].update(support_analysis=analysis(causality="causal"))), "verify.hedge_dropped")
    add("numeric_changed", lambda d: d["claims"][0]["subclaims"][0].update(statement="Treatment A had 13% higher uptake than Treatment B in mice at 24 h."), "verify.numeric_mismatch")
    add("wrong_unit_conversion", lambda d: d["claims"][5]["subclaims"][0]["unit_conversion"].update(claim_value=2), "verify.unit_conversion_orphaned")
    add("unsupported_absence", lambda d: d["claims"][3]["subclaims"][0].update(search_note=""), "verify.search_trail_missing")
    add("conflict_one_sided", lambda d: d["claims"][4]["subclaims"][0].update(conflict_note=""), "verify.conflict_not_two_sided")
    add("bad_quote", lambda d: d["claims"][0]["subclaims"][0]["evidence"][0].update(quote="13% higher uptake"), "evidence.quote_not_in_source")
    add("compound_not_split", lambda d: d["claims"].append({"claim_id": "C7", "claim_text": "Treatment A improved memory and reduced inflammation.",
        "subclaims": [subclaim("C7.1", "Treatment A improved memory and reduced inflammation.", "supported", [anchor("D1", "P5", "reduced inflammation")])]}), "verify.compound_not_split")
    add("strong_single_source", lambda d: d["claims"][0]["subclaims"][0].update(evidence_strength="strong"), "verify.strength_overstated")
    add("same_id_different_question", lambda d: d["claims"][0].update(claim_text="Treatment A had no effect."), "verify.claim_text_changed")
    for name, data, rule in scenarios:
        proc, result, _ = run(root, name, draft=data)
        rules = {x["rule"] for x in result.get("findings", [])}
        expect(results, name, proc.returncode == 4 and rule in rules and "Traceback" not in proc.stderr,
               f"rc={proc.returncode} rules={rules} stderr={proc.stderr}")
    proc, result, _ = run(root, "malformed", raw_case="{broken")
    expect(results, "malformed structured refusal", proc.returncode == 5 and result["status"] == "undetermined"
           and result["case_id"] is None and "Traceback" not in proc.stderr, proc.stderr)
    proc1, _, out = run(root, "idempotent")
    path = out / "result.json"
    first = path.read_bytes()
    cmd = [sys.executable, "-I", str(CLI), "--case", str(out.parent / "case.json"), "--claims-to-verify", str(out.parent / "claims-to-verify.json"),
           "--verdicts", str(out.parent / "verdicts.json"), "--sources", str(out.parent / "sources.json"), "--out", str(out)]
    proc2 = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", timeout=45)
    expect(results, "deterministic idempotent artifacts", proc1.returncode == proc2.returncode == 0 and first == path.read_bytes(), proc2.stderr)
    return results


def smoke(root):
    results = []
    proc, result, out = run(root, "realistic")
    cards = json.loads((out / "evidence_cards.json").read_text(encoding="utf-8"))
    expect(results, "realistic evidence cards + source quality + conflicts + coordinates", proc.returncode == 0 and len(cards) == 6
           and all(x["evidence"] or x["verdict"] == "insufficient_evidence" for x in cards)
           and all(x["evidence"][0]["page"] for x in cards if x["evidence"])
           and len(result["source_quality"]) == 3 and result["evidence_bounds"]["lexical_match_is_entailment"] is False,
           proc.stderr + str(result.get("findings")))
    cold_cmd = [sys.executable, "-I", "-c", "import importlib.util; p=r'%s'; s=importlib.util.spec_from_file_location('v_v2',p); m=importlib.util.module_from_spec(s); s.loader.exec_module(m); assert 'insufficient_evidence' in m.VERDICTS" % CLI]
    cold = subprocess.run(cold_cmd, cwd=str(root), capture_output=True, text=True, encoding="utf-8", timeout=30)
    expect(results, "cold isolated import", cold.returncode == 0 and "Traceback" not in cold.stderr, cold.stderr)
    return results


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--suite", choices=["functional", "hostile", "smoke", "all"], default="all")
    args = ap.parse_args()
    suites = ["functional", "hostile", "smoke"] if args.suite == "all" else [args.suite]
    results = []
    with tempfile.TemporaryDirectory(prefix="verify-v2-bench-") as tmp:
        for suite in suites:
            results.extend(globals()[suite](Path(tmp)))
    passed = sum(x["pass"] for x in results)
    print(json.dumps({"suite": args.suite, "passed": passed, "total": len(results), "failed": len(results) - passed}, ensure_ascii=False))
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
