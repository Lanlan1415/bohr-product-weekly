"""Source-bound claim/evidence/reasoning audit for an original paper case.

  python logiccheck.py --case /input/case.json --out /app/output
  python logiccheck.py --case /input/case.json --material /app/work/paper.txt \
      --out /app/output

The engine builds an argument map before reporting defects.  Attributed claims,
explicit hypotheses, deliberate controls and hedged interpretations are excluded
from overclaim rules.  Every finding carries an executable revision action.
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import review_common as C  # noqa: E402

ALIASES = {"审查报告": "audit_report", "依据与边界": "evidence_bounds", "结果状态": "result_state",
           "review_report": "audit_report", "evidence_and_boundaries": "evidence_bounds",
           "result_status": "result_state", "logic_results": "argument_map", "reasoning_results": "reasoning_gaps"}
CAUSAL_RX = re.compile(r"\b(?:caus(?:e|es|ed|ing)|leads?\s+to|drives?|results?\s+in|improv(?:e|es|ed)|reduc(?:e|es|ed)|increas(?:e|es|ed)|decreas(?:e|es|ed)|effect\s+of)\b|导致|引起|改善|降低|提高", re.I)
STRONG_RX = re.compile(r"\b(?:prove[sd]?|demonstrat(?:e|es|ed)|establish(?:es|ed)|confirm(?:s|ed)|guarantee[sd]?|universally|always|all\s+\w+)\b|证明|证实|所有|普遍|必然", re.I)
HEDGE_RX = re.compile(r"\b(?:may|might|could|suggest(?:s|ed)?|consistent\s+with|associated\s+with|association|correlat(?:ed|ion)|appears?|seems?|possibly|potentially|limited\s+to)\b|可能|提示|相关|一致于|限于", re.I)
ATTRIBUTION_RX = re.compile(r"\baccording\s+to\b|\b\w+\s+et\s+al\.?(?:\s*\(\d{4}\))?\s+(?:argue|report|show|suggest|demonstrate|find|conclude|establish)(?:s|ed)?|\bprevious\s+(?:studies|work|research)\b|已有研究|据报道|\[[0-9,; \-–]+\]\s*(?:argue|report|show|demonstrate)", re.I)
HYPOTHESIS_RX = re.compile(r"\bwe\s+(?:hypothesi[sz]e|ask|aim|sought)\b|\bthis\s+study\s+(?:aims|sought)\b|\bwhether\b|\bhypothesis\b|假设|旨在|拟探讨", re.I)
NONSIGNIFICANT_RX = re.compile(r"\b(?:not|non[- ]?)\s*significant\b|\bno\s+significant\s+(?:effect|difference|association)\b|\bp\s*[>=]\s*0?\.0?5\b|不显著|无显著", re.I)
LIMITATION_RX = re.compile(r"\blimitations?\b|\blimited\s+to\b|\bcaution\b|\bconfound(?:ing|ers?)?\b|\breverse\s+causation\b|\balternative\s+explanations?\b|局限|限制|混杂|反向因果|替代解释", re.I)


def design_info(case: dict, doc: C.Document) -> tuple[str, list[dict]]:
    declared = str(case.get("design") or case.get("study_design") or "").lower()
    methods = [s for s in doc.spans if re.search(r"method|方法|design|设计", s["section"], re.I) and s["kind"] != "heading"]
    observational = [s for s in methods if re.search(r"\b(?:observational|cross[- ]sectional|cohort|case[- ]control|correlational|survey|retrospective|prospective\s+observational)\b|观察性|横断面|队列|病例对照|相关性研究|回顾性", s["text"], re.I)]
    experimental = [s for s in methods if re.search(r"\brandomi[sz]ed\b|\bRCT\b|\bexperimental\s+(?:design|trial)\b|\bcontrolled\s+trial\b|随机对照|随机分组|实验设计", s["text"], re.I)]
    if experimental and ("experiment" in declared or "random" in declared or "rct" in declared):
        return "experimental", experimental[:2]
    if observational:
        return "observational", observational[:2]
    if experimental:
        return "experimental", experimental[:2]
    if any(x in declared for x in ("observ", "cross", "cohort", "correl", "survey", "case-control")):
        return "observational", methods[:1]
    if any(x in declared for x in ("experiment", "random", "rct", "trial")):
        return "experimental", methods[:1]
    return "undetermined", methods[:1]


def is_attributed(span: dict) -> bool:
    return bool(ATTRIBUTION_RX.search(span["text"]))


def is_hypothesis(span: dict) -> bool:
    return bool(HYPOTHESIS_RX.search(span["text"]))


def is_hedged(text: str) -> bool:
    return bool(HEDGE_RX.search(text))


def conclusion_like(span: dict) -> bool:
    return bool(re.search(r"abstract|摘要|discussion|讨论|conclusion|结论", span["section"], re.I))


def claim_strength(span: dict, design: str) -> int:
    text = span["text"]
    if is_attributed(span) or is_hypothesis(span):
        return 0
    if is_hedged(text):
        return 1
    if STRONG_RX.search(text) or (conclusion_like(span) and CAUSAL_RX.search(text)):
        return 3
    if conclusion_like(span) and re.search(r"\b(?:we found|we show|our findings|this study shows|the programme|the treatment|the coating|the model)\b|本研究|我们发现|表明", text, re.I):
        return 2
    return 1


def scope(text: str) -> set[str]:
    found = set()
    for name, rx in (("human", r"\b(?:humans?|patients?|people|adults?|children|participants?)\b|人类|患者|人群|受试者"),
                     ("mouse", r"\b(?:mice|mouse|murine)\b|小鼠"), ("rat", r"\b(?:rats?)\b|大鼠"),
                     ("in_vitro", r"\b(?:in\s+vitro|cell\s+lines?|cells?)\b|体外|细胞系")):
        if re.search(rx, text, re.I):
            found.add(name)
    return found


def directions(text: str) -> set[str]:
    out = set()
    if re.search(r"\b(?:increase[sd]?|improve[sd]?|higher|greater|rise[sd]?|up[- ]regulat)\b|提高|增加|改善|升高", text, re.I):
        out.add("increase")
    if re.search(r"\b(?:decrease[sd]?|reduce[sd]?|lower|decline[sd]?|down[- ]regulat)\b|降低|减少|下降", text, re.I):
        out.add("decrease")
    return out


def numeric_values(text: str) -> set[str]:
    scrubbed = re.sub(r"\[\s*\d+(?:\s*[-–,;]\s*\d+)*\s*\]", " ", text)
    values = set(re.findall(r"(?<![\w.])\d+(?:\.\d+)?(?![\w.])", scrubbed))
    for word, number in {"one": "1", "two": "2", "three": "3", "four": "4", "five": "5",
                         "six": "6", "seven": "7", "eight": "8", "nine": "9", "ten": "10"}.items():
        if re.search(r"\b" + word + r"\b", scrubbed, re.I):
            values.add(number)
    return values


def claim_records(doc: C.Document, design: str) -> list[dict]:
    records = []
    for span in doc.spans:
        if span["kind"] == "heading" or not conclusion_like(span) or re.search(r"references|参考文献", span["section"], re.I):
            continue
        strength = claim_strength(span, design)
        if strength == 0:
            continue
        # Hedged/limited claims still belong in the map: their qualifiers are part
        # of the reasoning evidence, even though they do not trigger overclaim rules.
        records.append({"span": span, "strength": strength, "attributed": is_attributed(span),
                        "hypothesis": is_hypothesis(span), "hedged": is_hedged(span["text"])})
    return records


def build_map(doc: C.Document, case: dict, design: str) -> tuple[list[dict], list[dict]]:
    results = [s for s in doc.spans if s["kind"] != "heading"
               and re.search(r"results?|结果|analysis|分析", s["section"], re.I)]
    records = claim_records(doc, design)
    argument_map = []
    cross_checks = []
    for pos, record in enumerate(records, 1):
        span = record["span"]
        scored = sorted(((C.overlap(span["text"], candidate["text"]), candidate) for candidate in results),
                        key=lambda pair: pair[0], reverse=True)
        evidence = []
        for score, candidate in scored[:3]:
            if score < 0.12:
                continue
            evidence.append({"quote": candidate["text"], "locator": doc.locator(candidate),
                             "relation": "result_support_candidate", "claim_coverage": round(score, 4),
                             "non_significant": bool(NONSIGNIFICANT_RX.search(candidate["text"])),
                             "directions": sorted(directions(candidate["text"]))})
        pointers = re.findall(r"\b(?:Fig(?:ure)?\.?|Table)\s*\d+[A-Za-z]?|\[[0-9,; \-–]+\]", span["text"], re.I)
        qualifiers = []
        if record["hedged"]:
            qualifiers.append("modal/associational qualifier present")
        if LIMITATION_RX.search(span["text"]):
            qualifiers.append("explicit scope limitation in claim")
        missing_warrant = record["strength"] >= 2 and not evidence and not pointers
        argument_map.append({"claim_id": f"A{pos:03d}", "text": span["text"], "locator": doc.locator(span),
                             "section": span["section"], "claim_strength": record["strength"],
                             "design": design, "attributed_to_others": record["attributed"],
                             "hypothesis": record["hypothesis"], "qualifiers": qualifiers,
                             "evidence": evidence, "result_pointers": pointers,
                             "warrant": {"status": "missing" if missing_warrant else "linked_for_human_review",
                                         "note": "Lexical evidence links are candidates; entailment still requires scientific review."},
                             "alternative_explanations": {"required_for_strong_observational_claim": design == "observational" and record["strength"] >= 2,
                                                          "discussion_terms_present": bool(LIMITATION_RX.search(doc.text))}})
        if pointers or evidence:
            cross_checks.append({"claim_id": f"A{pos:03d}", "evidence_links": len(evidence) + len(pointers), "status": "linked"})
    return argument_map, cross_checks


def executable_fix(claim: str, kind: str) -> tuple[str, str | None]:
    if kind == "causal":
        replacement = CAUSAL_RX.sub("is associated with", claim)
        return ("Replace the causal verb with associational wording, keep the observational population/time window in the sentence, and add a causal design only if one actually exists.", replacement)
    if kind == "extrapolation":
        return ("Rewrite the conclusion for the measured species, cohort, site and follow-up window; add external/multi-site/human validation before making the broader claim.", None)
    if kind == "evidence":
        return ("Add the specific result/table/figure that entails this claim, including effect size and uncertainty, or delete/narrow the sentence to the available evidence.", None)
    if kind == "contradiction":
        return ("Check both quoted locations against the underlying result, correct the inconsistent value/direction/significance wording, and record the correction.", None)
    if kind == "alternative":
        return ("Add a named alternative-explanation paragraph addressing confounding, reverse causation and measurement bias, and state what analysis can/cannot exclude each one.", None)
    return ("Narrow the sentence to the measured scope and add the missing support or limitation.", None)


def finding(rule: str, severity: str, doc: C.Document, claim: dict, basis: str,
            kind: str, category: str = "论证链", evidence: dict | None = None) -> dict:
    fix, replacement = executable_fix(claim["text"], kind)
    return {"rule": rule, "category": category, "severity": severity, "facet": kind,
            "kind": "reasoning_defect" if severity == "high" else "reasoning_gap",
            "verdict": "logic_problem" if severity == "high" else "evidence_gap",
            "claim_id": claim["claim_id"], "location": claim["locator"], "excerpt": claim["text"],
            "evidence_quote": (evidence or {}).get("quote"), "evidence_locator": (evidence or {}).get("locator"),
            "basis": basis, "severity_basis": "affects the main claim" if severity == "high" else "limits inference precision or completeness",
            "fix": fix, "replacement_text": replacement}


def promise_checks(doc: C.Document) -> tuple[list[dict], list[dict]]:
    promises = [s for s in doc.spans if re.search(r"introduction|引言|前言", s["section"], re.I)
                and re.search(r"\bwe\s+(?:aim\s+to|sought\s+to|compare|evaluate|investigate|analy[sz]e)\b|\bthis\s+study\s+(?:aims|sought)\b|本研究旨在|我们旨在", s["text"], re.I)]
    delivery = [s for s in doc.spans if s["kind"] != "heading" and re.search(r"methods?|results?|discussion|方法|结果|讨论", s["section"], re.I)]
    findings, checks = [], []
    for pos, promise in enumerate(promises, 1):
        best_score = max((C.overlap(promise["text"], s["text"]) for s in delivery), default=0.0)
        checks.append({"promise_id": f"P{pos:03d}", "promise": promise["text"], "locator": doc.locator(promise),
                       "best_delivery_coverage": round(best_score, 4), "status": "delivered" if best_score >= 0.12 else "not_delivered"})
        if best_score < 0.12:
            findings.append({"rule": "logic.promise_not_delivered", "category": "章节衔接", "severity": "high", "facet": "cross_section",
                             "kind": "reasoning_defect", "verdict": "promise_without_delivery", "location": doc.locator(promise),
                             "excerpt": promise["text"], "basis": f"No method/result/discussion sentence reaches the declared content-overlap floor (best={best_score:.3f}).",
                             "severity_basis": "a stated research objective has no identifiable delivery",
                             "fix": "Add the promised comparison/analysis with a named result and locator, or remove the unsupported aim sentence and revise the abstract/conclusion consistently."})
    return findings, checks


def contradiction_checks(doc: C.Document, argument_map: list[dict]) -> tuple[list[dict], list[dict]]:
    findings, checks = [], []
    abstract = [s for s in doc.spans if re.search(r"abstract|摘要", s["section"], re.I) and s["kind"] != "heading"]
    body = [s for s in doc.spans if s["kind"] != "heading" and re.search(r"results?|discussion|conclusion|结果|讨论|结论", s["section"], re.I)]
    for a in abstract:
        a_nums = numeric_values(a["text"])
        a_plain = re.sub(r"\d+(?:\.\d+)?", " ", a["text"])
        for b in body:
            b_nums = numeric_values(b["text"])
            b_plain = re.sub(r"\d+(?:\.\d+)?", " ", b["text"])
            similarity = C.f1(a_plain, b_plain)
            if similarity < 0.56:
                continue
            check = {"abstract_quote": a["text"], "abstract_locator": doc.locator(a),
                     "body_quote": b["text"], "body_locator": doc.locator(b),
                     "similarity": round(similarity, 4), "abstract_values": sorted(a_nums),
                     "body_values": sorted(b_nums), "status": "consistent"}
            # Shared controls such as 7,900 may coexist with a changed effect value;
            # both sides having a distinct value is the contradiction signal.
            conflict = bool(a_nums and b_nums and a_nums != b_nums and (a_nums - b_nums) and (b_nums - a_nums))
            direction_conflict = bool(directions(a["text"]) and directions(b["text"])
                                      and directions(a["text"]).isdisjoint(directions(b["text"])))
            significance_conflict = bool(CAUSAL_RX.search(a["text"]) and NONSIGNIFICANT_RX.search(b["text"]))
            if conflict or direction_conflict or significance_conflict:
                check["status"] = "contradiction"
                reason = "disjoint numeric values" if conflict else ("opposite directions" if direction_conflict else "effect wording versus non-significant result")
                findings.append({"rule": "logic.cross_section_contradiction", "category": "前后一致性", "severity": "high",
                                 "facet": "contradiction", "kind": "reasoning_defect", "verdict": "source_internal_contradiction",
                                 "location": doc.locator(a), "excerpt": a["text"], "evidence_quote": b["text"],
                                 "evidence_locator": doc.locator(b), "basis": f"Aligned statements show {reason} (text similarity={similarity:.2f}).",
                                 "severity_basis": "the abstract and substantive conclusion cannot both be correct as written",
                                 "fix": executable_fix(a["text"], "contradiction")[0]})
            checks.append(check)
    return findings, checks


def audit(case: dict, materials: list[dict], material_errors: list[str]) -> dict:
    primary = materials[0]
    doc = C.Document(primary["text"], primary["name"])
    design, design_spans = design_info(case, doc)
    argument_map, cross_checks = build_map(doc, case, design)
    findings: list[dict] = []
    limitations_present = bool(LIMITATION_RX.search(doc.text))
    for claim in argument_map:
        if claim["claim_strength"] < 2 or claim["attributed_to_others"] or claim["hypothesis"]:
            continue
        text = claim["text"]
        hedged = bool(is_hedged(text))
        causal = bool(CAUSAL_RX.search(text)) and not hedged
        related_non_significant = next((e for e in claim["evidence"] if e["non_significant"] and e["claim_coverage"] >= 0.18), None)
        if related_non_significant and CAUSAL_RX.search(text):
            findings.append(finding("logic.non_significant_result_claimed_as_effect", "high", doc, claim,
                                    "The abstract/discussion states an effect while the linked results sentence explicitly reports non-significance.", "contradiction", "统计口径与结论", related_non_significant))
        elif design == "observational" and causal:
            findings.append(finding("logic.causal_overreach", "high", doc, claim,
                                    "The design evidence is observational/correlational, but this unhedged claim uses causal wording. A deliberate control or cited third-party claim is not being flagged.", "causal"))
        claim_scope = scope(text)
        evidence_scope = set().union(*(scope(e["quote"]) for e in claim["evidence"])) if claim["evidence"] else set()
        method_spans = [s for s in doc.spans if re.search(r"method|方法", s["section"], re.I) and s["kind"] != "heading"]
        method_scope = set().union(*(scope(s["text"]) for s in method_spans)) if method_spans else set()
        if "human" in claim_scope and not hedged and ((method_scope - {"human"}) or (evidence_scope and "human" not in evidence_scope)):
            findings.append(finding("logic.species_or_population_extrapolation", "high", doc, claim,
                                    f"The conclusion targets humans while design/evidence scope is {sorted(method_scope or evidence_scope)}; no direct human support is linked.", "extrapolation", "样本与外推"))
        if re.search(r"\b(?:all|universally|generalizable\s+to\s+all|widely\s+applicable|always)\b|所有|普遍适用|广泛适用", text, re.I) and not hedged:
            limited_sample = bool(re.search(r"\bsingle[- ](?:site|centre|center|institution|country|cell\s+line)\b|单中心|单一位点|一个细胞系", doc.text, re.I))
            if limited_sample or claim_scope:
                findings.append(finding("logic.sample_scope_extrapolation", "medium", doc, claim,
                                        "A universal/generalisable conclusion exceeds the declared or measured sample scope.", "extrapolation", "样本与外推"))
        if not claim["evidence"] and not claim["result_pointers"] and (claim["claim_strength"] >= 3 or causal):
            findings.append(finding("logic.evidence_link_missing", "high" if claim["claim_strength"] >= 3 else "medium", doc, claim,
                                    "No results sentence, figure/table pointer or citation is linked to this strong claim; this is an evidence-chain gap, not proof the claim is false.", "evidence"))
        if design == "observational" and causal and re.search(r"\b(?:through|via|mediated\s+by|because|mechanism)\b|通过|介导|机制", text, re.I) and not limitations_present:
            findings.append(finding("logic.alternative_explanations_not_addressed", "medium", doc, claim,
                                    "A mechanism/causal chain is asserted without a detectable limitation or alternative-explanation discussion.", "alternative", "替代解释"))
        if claim["claim_strength"] >= 3 and not limitations_present:
            findings.append(finding("logic.boundary_conditions_missing", "medium", doc, claim,
                                    "An absolute/strong conclusion is present but no limitation, scope condition or alternative explanation was located in the supplied text.", "evidence", "结论边界"))

    promise_findings, promise_results = promise_checks(doc)
    contradiction_findings, contradiction_results = contradiction_checks(doc, argument_map)
    findings.extend(promise_findings)
    findings.extend(contradiction_findings)
    findings = C.finalise_findings(findings)
    counts = C.severity_counts(findings)
    pending = list(material_errors)
    if design == "undetermined":
        pending.append("Study design could not be determined from structured fields/methods; causal-design verdicts were not inferred.")
    if not any(re.search(r"results?|结果", s["section"], re.I) for s in doc.spans):
        pending.append("No results section was parsed; claim-evidence and cross-section checks remain partial.")
    if not any(re.search(r"discussion|conclusion|讨论|结论", s["section"], re.I) for s in doc.spans):
        pending.append("No discussion/conclusion section was parsed; full-paper argument coverage cannot be claimed.")
    if len(doc.text) < 400:
        pending.append("The supplied manuscript is short; this may be an excerpt rather than a complete paper.")
    not_checked = ["statistical recomputation", "original-data verification", "truth of cited third-party claims",
                   "semantic entailment beyond explicit source links"]
    limits = ["Attributed claims, explicit hypotheses and hedged sentences are not treated as author overclaims.",
              "Result links are lexical support candidates, not proof of entailment; every evidence quote and locator is exposed for human adjudication.",
              "No design mismatch is inferred when the design is undetermined.",
              "Contradiction rules require aligned source statements and report both sides rather than choosing a winner."]
    status = "blocked" if counts.get("high") else ("review" if findings or pending else "clean")
    reasoning_gaps = [f for f in findings if f.get("category") in {"论证链", "替代解释", "结论边界", "样本与外推", "前后一致性"}]
    evidence_bounds = {"manuscript_quotes": [{"claim_id": c["claim_id"], "quote": c["text"], "locator": c["locator"],
                                              "evidence": c["evidence"]} for c in argument_map],
                       "design_evidence": [doc.evidence(s) for s in design_spans], "pending_review": pending,
                       "limitations_present": limitations_present}
    result = {"schema_version": C.SCHEMA_VERSION, "status": status, "ok": True,
              "audit_report": findings, "findings": findings, "argument_map": argument_map,
              "reasoning_gaps": reasoning_gaps, "cross_section_checks": cross_checks + promise_results + contradiction_results,
              "promise_checks": promise_results, "contradiction_checks": contradiction_results,
              "evidence_bounds": evidence_bounds, "uncertainty": pending,
              "result_state": C.result_state(findings,
                                             [c["claim_id"] for c in argument_map if c["evidence"] and not any(f.get("claim_id") == c["claim_id"] for f in findings)],
                                             pending, not_checked),
              "severity_counts": counts,
              "sources": [{k: v for k, v in m.items() if k != "text"} for m in materials],
              "checked": {"manuscript_sha256": doc.sha256, "manuscript_chars": len(doc.text),
                          "sentences": len(doc.spans), "claims": len(argument_map), "design": design,
                          "facets": {"claim_extraction": "checked", "evidence_links": "checked",
                                     "causal_vs_correlation": "checked_when_design_determined",
                                     "sample_extrapolation": "checked", "alternative_explanations": "checked",
                                     "cross_section_contradictions": "checked", "conclusion_scope": "checked"}},
              "limits": limits,
              "change_records": [{"stage": "claims", "action": "separate author claims from attribution, hypotheses and hedges",
                                  "claim_count": len(argument_map)},
                                 {"stage": "argument_map", "action": "link result evidence, qualifiers, warrant and alternative explanations"},
                                 {"stage": "review", "action": "emit source-located findings with executable revisions",
                                  "values_fabricated": False}]}
    return result


def run(case_path: str | Path, out_dir: str | Path, materials: list[str] | None = None) -> dict:
    case, error = C.read_json(case_path)
    if error:
        return C.refused({}, out_dir, "logic.case_unreadable", error, ALIASES)
    if not isinstance(case, dict):
        return C.refused({}, out_dir, "logic.case_not_object", "case.json must be a JSON object", ALIASES)
    records, errors = C.material_records(case, case_path, materials)
    if not records:
        detail = "no readable manuscript/full text was supplied" + (("; " + "; ".join(errors)) if errors else "")
        return C.refused(case, out_dir, "logic.no_manuscript", detail, ALIASES)
    try:
        result = C.complete_contract(audit(case, records, errors), case, ALIASES)
        C.write_artifacts(out_dir, result)
        return result
    except Exception as exc:
        return C.refused(case, out_dir, "logic.internal_error",
                         f"logic audit could not complete: {type(exc).__name__}: {exc}", ALIASES)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="logiccheck", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--case", required=True)
    parser.add_argument("--material", action="append", default=[])
    parser.add_argument("--out", required=True)
    args = parser.parse_args(argv)
    try:
        result = run(args.case, args.out, args.material)
    except Exception as exc:
        result = C.refused({}, args.out, "logic.runner_error", f"runner refused: {type(exc).__name__}: {exc}", ALIASES)
    print(C.summary_for_stdout(result))
    return C.EXIT_CODES.get(result.get("status"), 5)


if __name__ == "__main__":
    raise SystemExit(main())
