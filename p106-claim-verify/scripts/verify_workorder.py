"""Verify claims-to-verify v2 with source-bound four-way support verdicts.

Retrieval overlap is recorded for audit only; entailment is separately adjudicated by
an agent using complete source context and seven preserved claim dimensions.  The
standard-library checker refuses internally inconsistent upgrades, fabricated quotes,
one-sided conflicts and insufficient-evidence-as-contradiction mistakes.
"""
from __future__ import annotations

import argparse
import copy
import json
import math
import re
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
import units as U  # noqa: E402
import v2_common as C  # noqa: E402

VERDICTS = {"supported", "partially_supported", "contradicted", "insufficient_evidence"}
KINDS = {"fact", "comparison", "causal", "scope"}
DIMENSIONS = {
    "polarity": {"same", "opposite", "mixed", "unknown"},
    "comparator": {"aligned", "missing", "mismatch", "not_applicable", "unknown"},
    "modality": {"same", "weaker", "stronger", "unknown"},
    "significance": {"aligned", "not_significant", "missing", "not_applicable", "unknown"},
    "scope": {"aligned", "narrower", "mismatch", "unknown"},
    "causality": {"causal", "associational", "mismatch", "not_applicable", "unknown"},
    "endpoint": {"exact", "alias", "different", "not_applicable", "unknown"},
}
HEDGE = re.compile(r"\b(?:may|might|could|suggest(?:s|ed)?|possibly|approximately|appears?|seems?|likely)\b|可能|或许|大约|提示|似乎", re.I)
NEG = re.compile(r"\b(?:no effect|no significant|not significant|did not|does not|do not|failed to|never|no difference|not observed)\b|没有显著|无显著|未观察到|未能|没有|并无|不能", re.I)
CAUSAL = re.compile(r"\b(?:caus(?:e|es|ed|al)|driv(?:e|es|en)|leading to|result(?:s|ed)? in)\b|导致|引起|使得", re.I)
ASSOCIATION = re.compile(r"\b(?:associated|correlat(?:ed|ion)|relationship|linked)\b|相关|关联", re.I)
COMPARATIVE = re.compile(r"\b(?:more|less|higher|lower|greater|than|compared|versus|improved|increased|decreased)\b|相比|高于|低于|多于|少于|优于|增加|降低", re.I)
NUMBER = re.compile(r"(?<![A-Za-z])[-+]?\d+(?:,\d{3})*(?:\.\d+)?(?:[eE][-+]?\d+)?")
# A comparator ("than") is one atomic comparison, not automatically two claims.
COMPOUND = re.compile(r"\s(?:and|but|because|while|whereas|however)\s|以及|并且|但是|然而|因为|同时", re.I)


def _records(value: Any) -> list[dict]:
    entries = list(value.values()) if isinstance(value, dict) else value
    return [x for x in entries if isinstance(x, dict)] if isinstance(entries, (list, tuple)) else []


def input_claims(data: Any) -> list[dict]:
    raw = data.get("claims") or data.get("claims_to_verify") or data.get("items") if isinstance(data, dict) else data
    out = []
    entries = raw if isinstance(raw, list) else []
    for pos, row in enumerate(entries):
        if isinstance(row, str):
            out.append({"claim_id": f"claim_{pos+1}", "claim_text": row})
        elif isinstance(row, dict):
            out.append(dict(row, claim_id=str(row.get("claim_id") or row.get("id") or f"claim_{pos+1}"),
                            claim_text=str(row.get("claim_text") or row.get("claim") or row.get("text") or "")))
    return out


def output_claims(data: Any) -> list[dict]:
    raw = data.get("claims") or data.get("verdicts") or data.get("items") if isinstance(data, dict) else data
    return _records(raw)


def _anchors(sub: dict, key: str) -> list[dict]:
    value = sub.get(key)
    if isinstance(value, dict):
        return [value]
    if isinstance(value, list):
        return [x for x in value if isinstance(x, dict)]
    if key == "evidence" and sub.get("quote") is not None:
        return [{k: sub.get(k) for k in ("source_id", "source_document_id", "paragraph_id", "verbatim", "quote",
                                        "context", "page", "section", "table_id", "row", "column", "figure_id",
                                        "bbox", "charspan") if sub.get(k) is not None}]
    return []


def _verify_anchors(corpus: C.SourceCorpus, raw: list[dict], owner: str, statement: str) -> tuple[list[dict], list[dict]]:
    findings, out = [], []
    for pos, item in enumerate(raw):
        ev, errs = corpus.anchor(item, f"{owner}[{pos}]")
        findings.extend(errs)
        if ev.get("found"):
            ev["retrieval_overlap"] = C.retrieval_overlap(statement, ev.get("context") or ev.get("verbatim"))
            ev["retrieval_note"] = "lexical candidate score only; not entailment"
        out.append(ev)
    return out, findings


def _number_set(text: Any) -> set[float]:
    vals = set()
    for match in NUMBER.finditer(str(text or "")):
        raw = match.group(0).replace(",", "")
        if re.fullmatch(r"(?:19|20)\d{2}", raw):
            continue
        try:
            vals.add(float(raw))
        except ValueError:
            pass
    return vals


def _support_analysis(sub: dict, owner: str) -> tuple[dict, list[dict]]:
    findings = []
    analysis = sub.get("support_analysis")
    if not isinstance(analysis, dict):
        return {}, [C.make_finding("verify.support_dimensions_missing", "high", f"{owner}: support_analysis object is required", owner)]
    analysis = copy.deepcopy(analysis)
    for name, allowed in DIMENSIONS.items():
        if analysis.get(name) not in allowed:
            findings.append(C.make_finding("verify.support_dimension_invalid", "high", f"{owner}: {name} must be one of {sorted(allowed)}", owner))
    if not str(analysis.get("rationale") or "").strip():
        findings.append(C.make_finding("verify.rationale_missing", "high", f"{owner}: rationale for entailment verdict is required", owner))
    return analysis, findings


def _verdict_consistency(verdict: str, a: dict, owner: str, kind: str) -> list[dict]:
    failures = []
    def bad(rule: str, message: str) -> None:
        failures.append(C.make_finding(rule, "high", f"{owner}: {message}", owner))
    if verdict == "supported":
        if a.get("polarity") != "same": bad("verify.polarity_overstated", "fully supported requires polarity=same")
        if a.get("comparator") not in {"aligned", "not_applicable"}: bad("verify.comparator_dropped", "fully supported requires comparator aligned/not_applicable")
        if a.get("modality") != "same": bad("verify.modality_overstated", "hedged/weaker source cannot support an unqualified full claim")
        if a.get("significance") not in {"aligned", "not_applicable"}: bad("verify.significance_dropped", "fully supported requires significance aligned/not_applicable")
        if a.get("scope") != "aligned": bad("verify.scope_overstated", "fully supported requires scope=aligned")
        if a.get("causality") not in ({"causal", "not_applicable"} if kind == "causal" else {"causal", "associational", "not_applicable"}): bad("verify.causality_overstated", "association cannot fully support a causal claim")
        if a.get("endpoint") != "exact": bad("verify.endpoint_substituted", "fully supported requires endpoint=exact")
    if verdict == "contradicted":
        if a.get("polarity") not in {"opposite", "mixed"} and a.get("significance") != "not_significant":
            bad("verify.contradiction_without_opposition", "contradicted requires opposite/mixed polarity or direct non-significance, not absence of evidence")
    if verdict == "insufficient_evidence" and a.get("polarity") == "opposite":
        bad("verify.opposition_hidden_as_insufficient", "declared opposite polarity should not be hidden as insufficient evidence")
    if verdict == "partially_supported" and not any(a.get(k) in values for k, values in {
        "polarity": {"mixed", "unknown"}, "comparator": {"missing", "mismatch", "unknown"},
        "modality": {"weaker", "unknown"}, "significance": {"missing", "unknown", "not_significant"},
        "scope": {"narrower", "mismatch", "unknown"}, "causality": {"associational", "unknown", "mismatch"},
        "endpoint": {"alias", "unknown", "different"}}.items()):
        bad("verify.partial_reason_missing", "partially_supported needs at least one explicit narrowed/missing dimension")
    return failures


def _verify_conversion(sub: dict, owner: str, claim_nums: set[float], evidence_nums: set[float]) -> tuple[dict | None, list[dict], set[float]]:
    raw = sub.get("unit_conversion")
    if raw is None:
        return None, [], evidence_nums
    if not isinstance(raw, dict):
        return None, [C.make_finding("verify.unit_conversion_invalid", "high", f"{owner}: unit_conversion must be an object")], evidence_nums
    findings = []
    try:
        claim_value = float(raw["claim_value"])
        evidence_value = float(raw["evidence_value"])
        claim_unit = str(raw["claim_unit"])
        evidence_unit = str(raw["evidence_unit"])
    except (KeyError, TypeError, ValueError):
        return None, [C.make_finding("verify.unit_conversion_invalid", "high", f"{owner}: conversion needs numeric claim/evidence values and units")], evidence_nums
    if claim_value not in claim_nums or evidence_value not in evidence_nums:
        findings.append(C.make_finding("verify.unit_conversion_orphaned", "high", f"{owner}: conversion operands must occur in claim/evidence", owner))
    conversion = U.convert(evidence_value, evidence_unit, claim_unit)
    if not conversion.get("ok"):
        findings.append(C.make_finding("verify.unit_conversion_unreproducible", "high", f"{owner}: {conversion.get('reason')}", owner))
    elif not math.isclose(conversion["value"], claim_value, rel_tol=1e-9, abs_tol=1e-12):
        findings.append(C.make_finding("verify.unit_conversion_unreproducible", "high", f"{owner}: {conversion.get('formula')} != {claim_value} {claim_unit}", owner))
    else:
        evidence_nums = set(evidence_nums)
        evidence_nums.add(claim_value)
    return conversion, findings, evidence_nums


def audit(workorder: Any, draft: Any, corpus: C.SourceCorpus) -> tuple[dict, list[dict]]:
    findings = [C.make_finding("sources.invalid", "high", x) for x in corpus.errors]
    expected = input_claims(workorder)
    expected_map = {str(x["claim_id"]): x for x in expected}
    if not expected:
        findings.append(C.make_finding("verify.no_input_claims", "high", "claims-to-verify contains no readable claims"))
    claims = output_claims(draft)
    seen_claims, seen_subs = set(), set()
    enriched, cards = [], []
    for pos, claim in enumerate(claims):
        cid = str(claim.get("claim_id") or claim.get("id") or f"claim_{pos+1}")
        text = str(claim.get("claim_text") or claim.get("claim") or claim.get("text") or "")
        if cid in seen_claims:
            findings.append(C.make_finding("verify.duplicate_claim", "high", f"{cid}: duplicate claim_id", cid))
        seen_claims.add(cid)
        if expected_map and cid not in expected_map:
            findings.append(C.make_finding("verify.unrequested_claim", "high", f"{cid}: not in claims-to-verify", cid))
        elif expected_map and expected_map[cid].get("claim_text") and text != expected_map[cid]["claim_text"]:
            findings.append(C.make_finding("verify.claim_text_changed", "high", f"{cid}: claim_text differs from claims-to-verify; do not answer a different question", cid))
        subs = claim.get("subclaims")
        if not isinstance(subs, list) or not subs:
            findings.append(C.make_finding("verify.subclaims_missing", "high", f"{cid}: at least one atomic subclaim is required", cid))
            continue
        if COMPOUND.search(text) and len(subs) < 2:
            findings.append(C.make_finding("verify.compound_not_split", "high", f"{cid}: compound claim requires independently verified subclaims", cid))
        new_claim = copy.deepcopy(claim)
        new_claim.update({"claim_id": cid, "claim_text": text, "subclaims": []})
        for spos, sub in enumerate(subs):
            if not isinstance(sub, dict):
                findings.append(C.make_finding("verify.subclaim_not_object", "high", f"{cid}.subclaims[{spos}] is not an object", cid))
                continue
            sid = str(sub.get("sub_id") or sub.get("subclaim_id") or f"{cid}.{spos+1}")
            if sid in seen_subs:
                findings.append(C.make_finding("verify.duplicate_subclaim", "high", f"{sid}: duplicate sub_id", sid))
            seen_subs.add(sid)
            kind = str(sub.get("kind") or "")
            if kind not in KINDS:
                findings.append(C.make_finding("verify.subclaim_kind_invalid", "high", f"{sid}: kind must be fact/comparison/causal/scope", sid))
            statement = str(sub.get("statement") or sub.get("claim") or "")
            if not statement:
                findings.append(C.make_finding("verify.empty_subclaim", "high", f"{sid}: statement is empty", sid))
            verdict = sub.get("verdict")
            if verdict not in VERDICTS:
                findings.append(C.make_finding("verify.verdict_invalid", "high", f"{sid}: invalid four-way verdict", sid))
                continue
            analysis, errs = _support_analysis(sub, sid)
            findings.extend(errs)
            if analysis:
                findings.extend(_verdict_consistency(verdict, analysis, sid, kind))
            raw_evidence = _anchors(sub, "evidence")
            evidence, errs = _verify_anchors(corpus, raw_evidence, f"{sid}.evidence", statement)
            findings.extend(errs)
            conflicts, errs = _verify_anchors(corpus, _anchors(sub, "conflicts") or _anchors(sub, "opposing_evidence"), f"{sid}.conflicts", statement)
            findings.extend(errs)
            if verdict == "insufficient_evidence":
                if raw_evidence:
                    findings.append(C.make_finding("verify.insufficient_has_entailing_quote", "medium", f"{sid}: evidence on an insufficient verdict is only a candidate; state why it is not entailing", sid))
                if not str(sub.get("search_note") or "").strip() or not sub.get("searched_sources"):
                    findings.append(C.make_finding("verify.search_trail_missing", "high", f"{sid}: insufficient_evidence needs search_note and searched_sources", sid))
            elif not raw_evidence:
                findings.append(C.make_finding("verify.evidence_missing", "high", f"{sid}: {verdict} requires a direct quotation and context", sid))
            if verdict == "contradicted" and str(sub.get("search_note") or "").strip().lower().startswith("no evidence"):
                findings.append(C.make_finding("verify.absence_is_not_contradiction", "high", f"{sid}: absence of evidence cannot contradict a claim", sid))
            consistency = sub.get("cross_document_consistency", "not_assessed" if not conflicts else None)
            if conflicts:
                locations = {(x.get("source_document_id"), x.get("paragraph_id")) for x in evidence + conflicts if x.get("found")}
                if consistency != "conflict":
                    findings.append(C.make_finding("verify.cross_document_consistency_missing", "high", f"{sid}: opposing evidence must be labelled conflict", sid))
                if len(locations) < 2 or not str(sub.get("conflict_note") or "").strip():
                    findings.append(C.make_finding("verify.conflict_not_two_sided", "high", f"{sid}: conflict needs two source locations and conflict_note", sid))
                if verdict in {"supported", "contradicted"}:
                    findings.append(C.make_finding("verify.conflict_unqualified_verdict", "high", f"{sid}: conflicting sources require partially_supported or insufficient_evidence", sid))
            all_text = " ".join(str(x.get("context") or x.get("verbatim") or "") for x in evidence)
            claim_negative = bool(NEG.search(statement))
            evidence_negative = bool(NEG.search(all_text))
            if verdict == "supported" and claim_negative != evidence_negative:
                findings.append(C.make_finding("verify.negation_misread", "high", f"{sid}: source and claim negation do not match; lexical similarity is not support", sid))
            if verdict == "supported" and HEDGE.search(all_text) and not HEDGE.search(statement):
                findings.append(C.make_finding("verify.hedge_dropped", "high", f"{sid}: hedged source cannot fully support an unqualified claim", sid))
            if verdict == "supported" and kind == "causal" and ASSOCIATION.search(all_text) and not CAUSAL.search(all_text):
                findings.append(C.make_finding("verify.association_is_not_causal", "high", f"{sid}: association-only source does not support causation", sid))
            claim_nums, evidence_nums = _number_set(statement), _number_set(all_text)
            conversion_result, conversion_findings, evidence_nums = _verify_conversion(sub, sid, claim_nums, evidence_nums)
            findings.extend(conversion_findings)
            if verdict == "supported" and claim_nums and not claim_nums.issubset(evidence_nums):
                findings.append(C.make_finding("verify.numeric_mismatch", "high", f"{sid}: claim numbers {sorted(claim_nums - evidence_nums)} are absent from direct evidence", sid))
            if verdict == "supported" and kind == "comparison" and COMPARATIVE.search(statement) and analysis.get("comparator") in {"missing", "mismatch", "not_applicable"}:
                findings.append(C.make_finding("verify.comparator_lost", "high", f"{sid}: comparison claim lost its comparator", sid))
            strength = sub.get("evidence_strength")
            if strength not in {"strong", "moderate", "weak", "insufficient"}:
                findings.append(C.make_finding("verify.evidence_strength_invalid", "medium", f"{sid}: evidence_strength strong/moderate/weak/insufficient is required", sid))
            source_ids = {x.get("source_document_id") for x in evidence if x.get("found")}
            if strength == "strong" and (len(source_ids) < 2 or verdict != "supported"):
                findings.append(C.make_finding("verify.strength_overstated", "high", f"{sid}: strong evidence requires full support from at least two full-text source documents", sid))
            if strength == "insufficient" and verdict != "insufficient_evidence":
                findings.append(C.make_finding("verify.strength_mismatch", "medium", f"{sid}: insufficient strength conflicts with verdict", sid))
            new_sub = copy.deepcopy(sub)
            new_sub.update({"sub_id": sid, "kind": kind, "statement": statement, "verdict": verdict,
                            "verification_status": "undetermined" if verdict == "insufficient_evidence" else "evidence_adjudicated",
                            "support_analysis": analysis, "evidence": evidence, "conflicts": conflicts,
                            "cross_document_consistency": consistency,
                            "unit_conversion_result": conversion_result,
                            "source_ids": sorted(x for x in source_ids if x)})
            new_claim["subclaims"].append(new_sub)
            cards.append({k: new_sub.get(k) for k in ("sub_id", "kind", "statement", "verdict", "verification_status",
                                                       "support_analysis", "evidence", "conflicts", "evidence_strength",
                                                       "cross_document_consistency", "conflict_note", "search_note", "searched_sources",
                                                       "unit_conversion", "unit_conversion_result")})
        enriched.append(new_claim)
    for cid in expected_map:
        if cid not in seen_claims:
            findings.append(C.make_finding("verify.input_claim_missing", "high", f"{cid}: no verification output; emit subclaims or honest insufficient verdicts", cid))
    return {"claims": enriched, "evidence_cards": cards, "source_quality": corpus.quality()}, findings


def build(case: dict, workorder: Any, draft: Any, bundle: Any, out_dir: Path) -> tuple[dict, int]:
    corpus = C.SourceCorpus(bundle)
    main, findings = audit(workorder, draft, corpus)
    findings = C.finalise_findings(findings)
    status, code = C.run_state(findings)
    verdict_counts = {v: sum(1 for c in main["claims"] for s in c["subclaims"] if s.get("verdict") == v) for v in sorted(VERDICTS)}
    sources = [{"source_document_id": did, "sha256": corpus.documents[did]["digest"], "quality": q}
               for did in sorted(corpus.documents) for q in main["source_quality"] if q["source_document_id"] == did]
    undetermined = [{"claim_id": c.get("claim_id"), "sub_id": s.get("sub_id"), "reason": s.get("search_note")}
                    for c in main["claims"] for s in c["subclaims"] if s.get("verification_status") == "undetermined"]
    result = {"schema_version": C.SCHEMA_VERSION, "status": status, "ok": status == "success",
              "section": "claim_verify_v2", "findings": findings, "audit_report": findings,
              "severity_counts": C.severity_counts(findings), "sources": sources,
              "source_quality": main["source_quality"], "claims": main["claims"],
              "evidence_cards": main["evidence_cards"], "verification_results": main["evidence_cards"],
              "uncertainty": undetermined,
              "checked": {"claims": len(main["claims"]), "subclaims": sum(len(c["subclaims"]) for c in main["claims"]),
                          "verdict_counts": verdict_counts,
                          "undetermined": len(undetermined)},
              "evidence_bounds": {"direct_quotes_and_context": True, "lexical_match_is_entailment": False,
                                  "no_evidence_state": "insufficient_evidence + verification_status=undetermined"},
              "fact_verified_independent_of_text": False,
              "result_state": {"passed": [s["sub_id"] for c in main["claims"] for s in c["subclaims"] if s.get("verdict") == "supported"],
                               "problems": [f["id"] for f in findings], "pending_review": [x["sub_id"] for x in undetermined]},
              "limits": ["This is an NLI-inspired audit, not a learned NLI model. Support dimensions and verdicts are agent judgements; literal source, polarity, numeric, modality and internal-consistency checks are deterministic.",
                         "Metadata-only sources cannot supply quotes. Unavailable full text and unverified DOI/page values remain undetermined; no network verification occurs."],
              "change_records": [{"action": "decompose_retrieve_adjudicate", "precedence": "complete context > direct quote > candidate lexical overlap", "fact_verified_independent_of_text": False}]}
    result = C.complete_contract(result, case, workorder=workorder)
    C.dump_json(out_dir / "evidence_cards.json", main["evidence_cards"])
    C.dump_json(out_dir / "result.json", result)
    return result, code


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--case", required=True)
    ap.add_argument("--claims-to-verify", default="", help="defaults beside case to claims-to-verify.json")
    ap.add_argument("--verdicts", required=True, help="agent-authored claims.json with atomic verdicts")
    ap.add_argument("--sources", default="", help="source snapshot JSON; defaults to case.source_documents/documents")
    ap.add_argument("--out", required=True)
    args = ap.parse_args(argv)
    out = Path(args.out)
    case, err = C.read_json(args.case)
    if err or not isinstance(case, dict):
        C.write_refusal(case, out, err or "case.json must be an object")
        return 5
    input_path = args.claims_to_verify or str(Path(args.case).parent / "claims-to-verify.json")
    workorder, err = C.read_json(input_path)
    if err or not isinstance(workorder, (dict, list)):
        C.write_refusal(case, out, err or "claims-to-verify.json must be an object or array", workorder=workorder)
        return 5
    try:
        draft, derr = C.read_json(args.verdicts)
        if derr or not isinstance(draft, (dict, list)):
            C.write_refusal(case, out, derr or "verdicts JSON must be an object or array", workorder=workorder)
            return 5
        if args.sources:
            bundle, serr = C.read_json(args.sources)
            if serr:
                C.write_refusal(case, out, serr, workorder=workorder)
                return 5
        else:
            bundle = {"documents": case.get("source_documents") or case.get("documents") or
                      (draft.get("source_documents", []) if isinstance(draft, dict) else [])}
        result, code = build(case, workorder, draft, bundle, out)
        print(json.dumps({"case_id": case.get("case_id"), "status": result["status"],
                          "verdict_counts": result["checked"]["verdict_counts"], "wrote": str(out / "result.json")}, ensure_ascii=False))
        return code
    except Exception as exc:
        C.write_refusal(case, out, f"v2 verification could not be completed: {type(exc).__name__}: {exc}", workorder=workorder)
        return 5


if __name__ == "__main__":
    raise SystemExit(main())
