"""Behavioural regression for the research-quality appraisal engine.

Synthetic fixtures only; these are not official cases or benchmark scores.
Run: python -I -X utf8 scripts/bench_appraisal.py
"""
from __future__ import annotations

import copy
import json
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
ROOT = HERE.parent
CLI = HERE / "quality_cli.py"
EXAMPLE_DOCS = json.loads((ROOT / "examples/studies.json").read_text(encoding="utf-8"))["documents"]
CLEAN = EXAMPLE_DOCS[0]
ABSTRACT = EXAMPLE_DOCS[1]
SCENARIOS = []


def run_case(root: Path, case: dict, name: str = "case"):
    work = root / name
    work.mkdir(parents=True, exist_ok=True)
    path = work / "case.json"
    path.write_text(json.dumps(case, ensure_ascii=False), encoding="utf-8")
    out = work / "out"
    proc = subprocess.run([sys.executable, "-I", "-X", "utf8", str(CLI), "--case", str(path),
                           "--out", str(out)], capture_output=True, text=True, timeout=120)
    result = json.loads((out / "result.json").read_text(encoding="utf-8"))
    return proc, result, out


def case(doc=None, **kw):
    value = {"case_id": "bench", "section": "quality_appraisal", "documents": [copy.deepcopy(doc or CLEAN)],
             "research_question": "exercise chronic pain", "output_contract": ["case_id", "检索结果", "证据记录", "状态说明"]}
    value.update(kw)
    return value


def row(result, dimension, doc=0):
    return next(r for r in result["appraisals"][doc]["quality_table"] if r["dimension"] == dimension)


def scenario(name):
    def decorate(fn):
        fn.scenario_name = name
        SCENARIOS.append(fn)
        return fn
    return decorate


@scenario("clean_complete_rct_zero_findings")
def _(root):
    proc, r, _ = run_case(root, case())
    return proc.returncode == 0 and r["status"] == "clean" and not r["findings"] \
        and r["appraisals"][0]["overall"]["grade"] == "low" and not r["appraisals"][0]["review_queue"]


@scenario("abstract_only_forces_overall_abstention")
def _(root):
    proc, r, _ = run_case(root, case(ABSTRACT))
    return proc.returncode == 3 and r["appraisals"][0]["coverage"] == "abstract_only" \
        and r["appraisals"][0]["overall"]["grade"] == "insufficient"


@scenario("same_sentence_pvalue_contradiction_high")
def _(root):
    _, r, _ = run_case(root, case(ABSTRACT))
    item = row(r, "statistical_analysis")
    return item["judgement"] == "high" and any(e.get("kind") == "contradiction" and "p = 0.20" in e["quote"] for e in item["evidence"])


@scenario("observational_causal_overreach_high")
def _(root):
    _, r, _ = run_case(root, case(ABSTRACT))
    item = row(r, "conclusion_consistency")
    return item["judgement"] == "high" and any("Causal conclusion" in e.get("explanation", "") for e in item["evidence"])


@scenario("not_blinded_is_not_positive_evidence")
def _(root):
    doc = copy.deepcopy(CLEAN)
    doc["full_text"] = doc["full_text"].replace("Participants and outcome assessors were blinded; the trial was double-blind.",
                                                "Blinding of participants and outcome assessors was not reported.")
    _, r, _ = run_case(root, case(doc))
    item = row(r, "blinding")
    return item["judgement"] == "insufficient" and r["appraisals"][0]["overall"]["grade"] != "low"


@scenario("unknown_design_uses_generic_checks")
def _(root):
    doc = {"id": "unknown", "title": "Unknown design", "text": "We measured 20 samples with a calibrated instrument."}
    _, r, _ = run_case(root, case(doc))
    a = r["appraisals"][0]
    return a["design"]["design"] == "unknown" and "selection_bias" in [x["dimension"] for x in a["quality_table"]] \
        and a["overall"]["grade"] == "insufficient"


@scenario("preprint_not_mislabelled_peer_reviewed")
def _(root):
    _, r, _ = run_case(root, case(ABSTRACT))
    item = row(r, "source_quality")
    return "peer-review" in item["reason"] and "peer_reviewed" not in r["appraisals"][0]["metadata"]


@scenario("rct_and_cohort_have_distinct_checklists")
def _(root):
    _, r, _ = run_case(root, case(documents=[copy.deepcopy(CLEAN), copy.deepcopy(ABSTRACT)]))
    rct = {x["dimension"] for x in r["appraisals"][0]["quality_table"]}
    cohort = {x["dimension"] for x in r["appraisals"][1]["quality_table"]}
    return "random_sequence" in rct and "confounding" not in rct and "confounding" in cohort and "random_sequence" not in cohort


@scenario("protocol_abstains_on_results_and_conclusions")
def _(root):
    doc = copy.deepcopy(CLEAN)
    doc["id"] = "protocol"
    doc["full_text"] = "Study protocol: This randomized controlled trial protocol describes computer-generated random sequence generation and central randomization. Methods: materials and a validated primary outcome at 12 weeks are specified."
    _, r, _ = run_case(root, case(doc))
    a = r["appraisals"][0]
    domains = {x["dimension"] for x in a["quality_table"]}
    return a["design"]["design"] == "protocol" and "statistical_analysis" not in domains and "conclusion_consistency" not in domains \
        and a["overall"]["grade"] == "insufficient"


@scenario("computational_test_leakage_concern")
def _(root):
    doc = copy.deepcopy(CLEAN)
    doc["id"] = "ml"
    doc["full_text"] = "Methods: This machine-learning model study used a random row-level split; the test set was used for tuning. A baseline and software version are reported. Results: accuracy increased. Conclusion: performance is uncertain. Limitations: external validity. Ethics committee approval was not applicable to public data; funding: none; conflicts of interest: none. Data and code availability: code and software version are supplied."
    _, r, _ = run_case(root, case(doc))
    return row(r, "validation_leakage")["judgement"] == "some_concerns"


@scenario("valid_manual_review_retains_engine_judgement")
def _(root):
    doc = copy.deepcopy(ABSTRACT)
    # Obtain a valid evidence id through a first real run.
    _, before, _ = run_case(root, case(doc), "before")
    ev = row(before, "confounding")["evidence"]
    evidence_ids = [ev[0]["evidence_id"]] if ev else []
    decision = {"doc_id": "quality-cohort-abstract", "dimension": "confounding", "judgement": "high",
                "reviewer": "reviewer-B", "rationale": "Unadjusted comparison with confounding by indication", "evidence_ids": evidence_ids}
    proc, r, _ = run_case(root, case(doc, review_decisions=[decision]), "after")
    item = row(r, "confounding")
    return proc.returncode == 3 and item["judgement"] == "high" and item["engine_judgement"] == "insufficient" \
        and r["change_records"][-1]["operation"] == "manual_review"


@scenario("unknown_review_evidence_id_rejected")
def _(root):
    decision = {"doc_id": "quality-cohort-abstract", "dimension": "confounding", "judgement": "low",
                "reviewer": "reviewer-B", "rationale": "invalid evidence reference", "evidence_ids": ["not-an-id"]}
    _, r, _ = run_case(root, case(ABSTRACT, review_decisions=[decision]))
    item = row(r, "confounding")
    return item["judgement"] == "insufficient" and "engine_judgement" not in item


@scenario("all_text_quotes_slice_verified")
def _(root):
    docs, _, _ = __import__("quality_cli").load_normalized(case(documents=[copy.deepcopy(CLEAN), copy.deepcopy(ABSTRACT)]), ROOT)
    result = __import__("appraisal").appraise({"normalized_documents": docs})
    source = {(d["doc_id"], u["locator"]["unit"]): u["text"] for d in docs for u in d["units"]}
    for app in result["appraisals"]:
        for item in app["quality_table"]:
            for ev in item["evidence"]:
                loc = ev["locator"]
                text = source[(app["doc_id"], loc["unit"])]
                if text[loc["start"]:loc["end"]] != ev["quote"]:
                    return False
    return True


@scenario("relevance_and_quality_not_conflated")
def _(root):
    _, r, _ = run_case(root, case(documents=[copy.deepcopy(CLEAN), copy.deepcopy(ABSTRACT)]))
    candidates = r["candidate_set"]
    return candidates[0]["quality_grade"] != candidates[0]["relevance"]["basis"] \
        and all("quality_grade" in x and "relevance" in x for x in candidates)


@scenario("object_list_contract_engine_case_null_priority")
def _(root):
    c = case(output_contract=[{"field": "case_id"}, {"name": "检索结果"}, {"key": "delivery_note"}, "absent"],
             delivery_note={"kept": True})
    _, r, _ = run_case(root, c)
    return r["case_id"] == "bench" and isinstance(r["检索结果"], dict) and r["delivery_note"] == {"kept": True} \
        and r["absent"] is None and any("absent" in x for x in r["limits"]) and r["status"] == "review"


@scenario("deterministic_byte_replay")
def _(root):
    c = case()
    p1, r1, o1 = run_case(root, c, "one")
    p2, r2, o2 = run_case(root, c, "two")
    return p1.returncode == p2.returncode == 0 and (o1 / "result.json").read_bytes() == (o2 / "result.json").read_bytes()


def main():
    rows = []
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        for i, fn in enumerate(SCENARIOS):
            try:
                ok = bool(fn(root / str(i)))
                why = ""
            except Exception as exc:
                ok, why = False, f"{type(exc).__name__}: {exc}"
            rows.append({"scenario": fn.scenario_name, "pass": ok, "why": why})
            print(("PASS" if ok else "FAIL") + f"  {fn.scenario_name:<52}" + why)
    report = {"schema_version": "quality-appraisal-bench/v2", "fixture_notice": "synthetic regression only",
              "scenarios": rows, "totals": {"passed": sum(x["pass"] for x in rows), "of": len(rows)}}
    (HERE / "report_appraisal.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"\n{report['totals']['passed']}/{len(rows)} appraisal scenarios pass")
    return 0 if all(x["pass"] for x in rows) else 1


if __name__ == "__main__":
    raise SystemExit(main())
