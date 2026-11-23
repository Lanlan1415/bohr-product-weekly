"""Extract every target-fields v2 field with literal, source-bound evidence.

Input extraction.json is authored by the agent after reading the real paper(s).  This
CLI validates target coverage, scalar/unit/statistic/condition/comparator components,
exact quote+context locators, reproducible unit conversion and causal/endpoint bounds.
No absent value is converted to zero and no correlation is promoted to causation.
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

STATUSES = {"reported", "not_reported", "source_conflict", "extraction_failed"}
COMPONENT_STATUSES = {"reported", "not_reported", "not_applicable"}
CLAIM_KINDS = {"conclusion", "data", "limitation", "speculation"}
CLAIM_FORMS = {"descriptive", "associational", "causal"}
HEDGE = re.compile(r"\b(?:may|might|could|suggest(?:s|ed)?|possibly|approximately|appears?|seems?|likely)\b|可能|或许|大约|提示|似乎", re.I)
ASSOCIATION = re.compile(r"\b(?:associated|correlat(?:ed|ion)|relationship|linked)\b|相关|关联", re.I)
CAUSAL = re.compile(r"\b(?:caus(?:e|es|ed|al)|driv(?:e|es|en)|leading to|result(?:s|ed)? in)\b|导致|引起|使得", re.I)
P_VALUE = re.compile(r"\bp\s*[<=>≤≥]\s*0?\.\d+|\bp\s*[<=>≤≥]\s*1\b", re.I)


def _records(value: Any) -> list[dict]:
    entries = list(value.values()) if isinstance(value, dict) else value
    return [x for x in entries if isinstance(x, dict)] if isinstance(entries, (list, tuple)) else []


def target_fields(data: Any) -> list[dict]:
    raw = data.get("fields") or data.get("target_fields") or data.get("targets") if isinstance(data, dict) else data
    out = []
    for pos, row in enumerate(_records(raw) if not isinstance(raw, list) or any(isinstance(x, dict) for x in raw or []) else raw):
        if isinstance(row, str):
            out.append({"field_id": row})
        elif isinstance(row, dict):
            out.append(dict(row, field_id=str(row.get("field_id") or row.get("name") or row.get("id") or f"field_{pos+1}")))
    return out


def extraction_fields(data: Any) -> list[dict]:
    raw = data.get("fields") or data.get("extractions") or data.get("items") if isinstance(data, dict) else data
    return _records(raw)


def _evidence_list(owner: dict, key: str = "evidence") -> list[dict]:
    value = owner.get(key)
    if isinstance(value, list):
        return [x for x in value if isinstance(x, dict)]
    if isinstance(value, dict):
        return [value]
    # Accept legacy flat primary evidence while emitting the normalised schema below.
    if owner is not None and owner.get("verbatim") is not None:
        return [{k: owner.get(k) for k in ("source_document_id", "paragraph_id", "verbatim", "quote",
                                          "context", "page", "section", "table_id", "row", "column",
                                          "figure_id", "bbox", "charspan") if owner.get(k) is not None}]
    return []


def _component(item: dict, name: str, owner: str) -> tuple[dict, list[dict]]:
    findings = []
    value = item.get(name)
    if not isinstance(value, dict):
        return {"status": None, "value": None}, [C.make_finding(
            "extract.component_missing", "high", f"{owner}: component '{name}' must be an object with status", owner)]
    component = copy.deepcopy(value)
    status = component.get("status")
    if status not in COMPONENT_STATUSES:
        findings.append(C.make_finding("extract.component_status_invalid", "high",
                                       f"{owner}: {name}.status must be reported/not_reported/not_applicable", owner))
    elif status == "not_reported" and not str(component.get("search_note") or "").strip():
        findings.append(C.make_finding("extract.component_gap_unqualified", "high",
                                       f"{owner}: {name}=not_reported needs search_note", owner))
    elif status == "not_applicable" and not str(component.get("reason") or "").strip():
        findings.append(C.make_finding("extract.component_na_unqualified", "high",
                                       f"{owner}: {name}=not_applicable needs a scientific reason", owner))
    return component, findings


def _check_anchors(corpus: C.SourceCorpus, anchors: list[dict], owner: str) -> tuple[list[dict], list[dict]]:
    out, findings = [], []
    if not anchors:
        return out, [C.make_finding("extract.evidence_missing", "high", f"{owner}: at least one exact evidence anchor is required", owner)]
    for pos, raw in enumerate(anchors):
        ev, errs = corpus.anchor(raw, f"{owner}.evidence[{pos}]")
        findings.extend(errs)
        out.append(ev)
    return out, findings


def _check_unit(item: dict, unit: dict, owner: str) -> tuple[Any, list[dict]]:
    findings = []
    scalar = item.get("scalar", item.get("value"))
    unit_value = unit.get("value") if unit.get("status") == "reported" else unit.get("unit")
    if unit.get("status") == "reported" and not str(unit_value or "").strip():
        findings.append(C.make_finding("extract.unit_missing", "high", f"{owner}: unit=reported but has no original unit value", owner))
    if isinstance(scalar, (int, float)) and not isinstance(scalar, bool):
        if not math.isfinite(float(scalar)):
            findings.append(C.make_finding("extract.scalar_not_finite", "high", f"{owner}: scalar is not finite", owner))
        if unit.get("status") != "reported" or not unit_value:
            findings.append(C.make_finding("extract.numeric_unit_missing", "high", f"{owner}: scalar is numeric; unit must be reported explicitly (count/ratio/dimensionless allowed)", owner))
    if item.get("normalized_scalar") is None:
        return None, findings
    normalized = item.get("normalized_scalar")
    target = item.get("normalized_unit")
    if not isinstance(normalized, (int, float)) or isinstance(normalized, bool) or not math.isfinite(float(normalized)):
        findings.append(C.make_finding("extract.normalized_scalar_invalid", "high", f"{owner}: normalized_scalar is not finite numeric", owner))
        return None, findings
    conversion = U.convert(float(scalar), str(unit_value or ""), str(target or "")) if isinstance(scalar, (int, float)) and not isinstance(scalar, bool) else {"ok": False, "reason": "original scalar is not numeric"}
    if not conversion.get("ok"):
        findings.append(C.make_finding("extract.unit_conversion_unavailable", "high", f"{owner}: {conversion.get('reason')}", owner))
    elif not math.isclose(float(normalized), float(conversion["value"]), rel_tol=1e-9, abs_tol=1e-12):
        findings.append(C.make_finding("extract.unit_conversion_unreproducible", "high", f"{owner}: {conversion.get('formula')} != {normalized} {target}", owner))
    item["conversion"] = {k: copy.deepcopy(conversion.get(k)) for k in ("src", "dst", "factor", "formula") if conversion.get(k) is not None}
    return conversion.get("value") if conversion.get("ok") else None, findings


def audit(workorder: dict, extraction: dict, corpus: C.SourceCorpus) -> tuple[dict, list[dict]]:
    findings = [C.make_finding("sources.invalid", "high", x) for x in corpus.errors]
    targets = target_fields(workorder)
    target_ids = [str(x["field_id"]) for x in targets]
    target_map = {str(x["field_id"]): x for x in targets}
    if not targets or len(target_ids) != len(set(target_ids)):
        findings.append(C.make_finding("extract.target_schema_invalid", "high", "target-fields must contain unique field_id objects/strings"))
    items = extraction_fields(extraction)
    seen: dict[str, dict] = {}
    output_fields = []
    for pos, item in enumerate(items):
        fid = str(item.get("field_id") or item.get("id") or f"field_{pos+1}")
        if fid in seen:
            findings.append(C.make_finding("extract.duplicate_field_id", "high", f"{fid}: duplicate output row", fid))
            continue
        seen[fid] = item
        if target_ids and fid not in target_map:
            findings.append(C.make_finding("extract.unrequested_field", "high", f"{fid}: not present in target-fields", fid))
        item = copy.deepcopy(item)
        owner = fid
        status = item.get("status")
        if status not in STATUSES:
            findings.append(C.make_finding("extract.field_status_invalid", "high", f"{fid}: invalid reported/not_reported/source_conflict/extraction_failed status", fid))
            continue
        item["scalar"] = item.get("scalar", item.get("value"))
        if status == "not_reported":
            if not str(item.get("search_note") or "").strip():
                findings.append(C.make_finding("extract.not_reported_unsearched", "high", f"{fid}: not_reported needs search_note", fid))
            item.update({"scalar": None, "evidence": [], "verification_status": "undetermined"})
            _complete_gap_components(item)
            output_fields.append(item)
            continue
        if status == "extraction_failed":
            if not str(item.get("failure_note") or "").strip():
                findings.append(C.make_finding("extract.failure_unexplained", "high", f"{fid}: extraction_failed needs failure_note", fid))
            item.update({"verification_status": "undetermined"})
            _complete_gap_components(item)
            output_fields.append(item)
            continue
        if status == "source_conflict":
            note = str(item.get("conflict_note") or "").strip()
            anchors = _evidence_list(item, "conflicts") or _evidence_list(item)
            evs, errs = _check_anchors(corpus, anchors, fid)
            findings.extend(errs)
            locations = {(x.get("source_document_id"), x.get("paragraph_id")) for x in evs if x.get("found")}
            if not note or len(locations) < 2:
                findings.append(C.make_finding("extract.conflict_not_two_sided", "high", f"{fid}: source_conflict needs conflict_note and at least two distinct source locations", fid))
            item.update({"evidence": evs, "scalar": item.get("scalar"), "verification_status": "undetermined"})
            _complete_gap_components(item)
            output_fields.append(item)
            continue
        if item.get("scalar") in (None, ""):
            findings.append(C.make_finding("extract.scalar_missing", "high", f"{fid}: reported scalar/value is empty", fid))
        if item.get("claim_kind") not in CLAIM_KINDS:
            findings.append(C.make_finding("extract.claim_kind_invalid", "high", f"{fid}: claim_kind must be conclusion/data/limitation/speculation", fid))
        if item.get("claim_form") not in CLAIM_FORMS:
            findings.append(C.make_finding("extract.claim_form_invalid", "high", f"{fid}: claim_form must be descriptive/associational/causal", fid))
        if item.get("endpoint_match") not in {"exact", "alias", "different", "not_applicable"}:
            findings.append(C.make_finding("extract.endpoint_alignment_missing", "high", f"{fid}: endpoint_match exact/alias/different/not_applicable is required", fid))
        elif item.get("endpoint_match") == "different":
            findings.append(C.make_finding("extract.endpoint_substituted", "high", f"{fid}: a different endpoint cannot answer the requested field", fid))
        elif item.get("endpoint_match") == "alias" and not str(item.get("endpoint_mapping_note") or "").strip():
            findings.append(C.make_finding("extract.endpoint_alias_unexplained", "high", f"{fid}: endpoint alias requires endpoint_mapping_note", fid))
        anchors, errs = _check_anchors(corpus, _evidence_list(item), fid)
        findings.extend(errs)
        item["evidence"] = anchors
        if isinstance(item.get("scalar"), (int, float)) and not isinstance(item.get("scalar"), bool):
            scalar_text = format(float(item["scalar"]), ".15g")
            if not any(re.search(r"(?<![\d.])" + re.escape(scalar_text) + r"(?![\d.])",
                                 str(ev.get("verbatim") or "").replace(",", "")) for ev in anchors):
                findings.append(C.make_finding("extract.scalar_not_in_evidence", "high",
                                               f"{fid}: scalar {scalar_text} is absent from primary quotation", fid))
        components = {}
        for name in COMPONENT_NAMES:
            component, errs = _check_component_and_anchors(corpus, item, name, fid)
            findings.extend(errs)
            components[name] = component
        item.update(components)
        context = " ".join(str(x.get("context") or x.get("verbatim") or "") for x in anchors)
        unit_value = components["unit"].get("value")
        if components["unit"].get("status") == "reported" and unit_value and str(unit_value) not in {"count", "ratio", "dimensionless"}:
            unit_aliases = {"percent": "%", "percentage": "%", "degC": "°C", "degree C": "°C"}
            needle = unit_aliases.get(str(unit_value), str(unit_value))
            if needle not in context:
                findings.append(C.make_finding("extract.unit_not_in_evidence", "high", f"{fid}: original unit '{unit_value}' is absent from primary evidence", fid))
        sample_evidence = context + " " + " ".join(str(x.get("verbatim") or "") for x in components["sample"].get("evidence", []))
        for group in components["sample"].get("groups", []) if isinstance(components["sample"].get("groups"), list) else []:
            if isinstance(group, dict) and isinstance(group.get("n"), (int, float)) and not isinstance(group.get("n"), bool):
                number = format(float(group["n"]), ".15g")
                if not re.search(r"(?<![\d.])" + re.escape(number) + r"(?![\d.])", sample_evidence.replace(",", "")):
                    findings.append(C.make_finding("extract.group_size_not_in_evidence", "high", f"{fid}: group '{group.get('name') or group.get('label')}' n={number} is absent from sample evidence", fid))
        uncertainty = components["uncertainty"]
        if not isinstance(uncertainty.get("hedged"), bool):
            findings.append(C.make_finding("extract.hedge_status_missing", "high", f"{fid}: uncertainty.hedged must be true/false", fid))
        elif HEDGE.search(context) and not uncertainty.get("hedged"):
            findings.append(C.make_finding("extract.hedge_dropped", "high", f"{fid}: source context is hedged but uncertainty.hedged=false", fid))
        if item.get("claim_form") == "causal" and ASSOCIATION.search(context) and not CAUSAL.search(context):
            findings.append(C.make_finding("extract.association_promoted_to_causal", "high", f"{fid}: association-only evidence cannot be extracted as a causal conclusion", fid))
        # A faithfully hedged causal speculation is valid.  Only an unqualified
        # rewrite is an error (covered by extract.hedge_dropped above).
        if item.get("claim_form") == "associational" and item.get("claim_kind") == "conclusion" and not uncertainty.get("hedged") and ASSOCIATION.search(context):
            item.setdefault("strength", "association_only")
        if P_VALUE.search(context):
            statistic = components["statistic"]
            basis = components["statistical_basis"]
            has_p = statistic.get("p_value") is not None or basis.get("p_value") is not None
            if not has_p:
                findings.append(C.make_finding("extract.statistic_dropped", "high", f"{fid}: evidence contains a p-value but statistic/statistical_basis omitted it", fid))
        normalized, errs = _check_unit(item, components["unit"], fid)
        findings.extend(errs)
        item["normalized_value_verified"] = normalized
        if target_map.get(fid, {}).get("endpoint") and item.get("endpoint_match") == "not_applicable":
            findings.append(C.make_finding("extract.requested_endpoint_ignored", "high", f"{fid}: target requests an endpoint; endpoint_match cannot be not_applicable", fid))
        item["verification_status"] = "verified_literal_and_locator"
        output_fields.append(item)
    for fid in target_ids:
        if fid not in seen:
            findings.append(C.make_finding("extract.requested_field_missing", "high", f"{fid}: target field has no result row; emit a classified gap", fid))
    if target_ids:
        output_fields.sort(key=lambda x: target_ids.index(str(x.get("field_id") or x.get("id"))) if str(x.get("field_id") or x.get("id")) in target_ids else len(target_ids))
    return {"fields": output_fields, "source_quality": corpus.quality()}, findings


COMPONENT_NAMES = ("unit", "statistic", "experimental_condition", "comparator", "sample",
                   "endpoint", "uncertainty", "statistical_basis")


def _complete_gap_components(item: dict) -> None:
    reason = item.get("search_note") or item.get("failure_note") or item.get("conflict_note") or "parent field has no verified value"
    for name in COMPONENT_NAMES:
        if not isinstance(item.get(name), dict):
            if item.get("status") == "extraction_failed":
                item[name] = {"status": "not_applicable", "reason": reason}
            else:
                item[name] = {"status": "not_reported", "search_note": reason}


def _check_component_and_anchors(corpus: C.SourceCorpus, item: dict, name: str, fid: str) -> tuple[dict, list[dict]]:
    component, findings = _component(item, name, fid)
    if component.get("status") == "reported":
        # Groups remain structured with per-group n and role; other components retain
        # their native values.  A reported component needs its own literal anchor unless
        # it is merely an explicit statistical basis already contained in primary evidence.
        if name == "sample" and isinstance(component.get("groups"), list):
            for pos, group in enumerate(component["groups"]):
                if not isinstance(group, dict):
                    findings.append(C.make_finding("extract.group_not_object", "high", f"{fid}: sample.groups[{pos}] is not an object", fid))
                elif not str(group.get("name") or group.get("label") or "").strip():
                    findings.append(C.make_finding("extract.group_unnamed", "high", f"{fid}: sample group needs name/label", fid))
        if name == "uncertainty" and "hedged" not in component:
            component["hedged"] = None
        anchors = _evidence_list(component)
        if anchors:
            verified, errs = _check_anchors(corpus, anchors, f"{fid}.{name}")
            findings.extend(errs)
            component["evidence"] = verified
        elif name not in {"statistic", "statistical_basis", "uncertainty", "unit"}:
            findings.append(C.make_finding("extract.component_evidence_missing", "high", f"{fid}: {name}=reported needs its own evidence anchor", fid))
    else:
        component.pop("evidence", None)
    return component, findings


def build(case: dict, workorder: dict, extraction: dict, bundle: Any, out_dir: Path) -> tuple[dict, int]:
    corpus = C.SourceCorpus(bundle)
    main, findings = audit(workorder, extraction, corpus)
    findings = C.finalise_findings(findings)
    status, code = C.run_state(findings)
    sources = [{"source_document_id": did, "sha256": corpus.documents[did]["digest"]} for did in sorted(corpus.documents)]
    uncertainty = []
    for item in main["fields"]:
        if item.get("status") != "reported":
            uncertainty.append({"field_id": item.get("field_id") or item.get("id"), "status": item.get("status"),
                                "reason": item.get("search_note") or item.get("failure_note") or item.get("conflict_note")})
    result = {"schema_version": C.SCHEMA_VERSION, "status": status, "ok": status == "success",
              "section": "conclusion_extract_v2", "findings": findings, "audit_report": findings,
              "severity_counts": C.severity_counts(findings), "sources": sources,
              "source_quality": main["source_quality"], "field_table": main["fields"],
              "fields": main["fields"], "uncertainty": uncertainty,
              "checked": {"target_fields": len(target_fields(workorder)), "returned_fields": len(main["fields"]),
                          "status_counts": {s: sum(1 for x in main["fields"] if x.get("status") == s) for s in sorted(STATUSES)}},
              "limits": ["Literal passage and locator checks do not prove scientific entailment; claim_form/endpoint alignment remain declared judgements with deterministic overclaim guards.",
                         "The engine reads only supplied source snapshots and uses no network, DOI lookup or fabricated full-text/page verification.",
                         "Unit conversion is optional and checked only on an explicit raw->normalized path; raw values are preserved."],
              "change_records": [{"action": "field_by_field_evidence_binding", "guards": ["target coverage", "sample/group/comparator/condition", "statistical basis", "hedge/causality/endpoint", "unit reproduction"]}]}
    result = C.complete_contract(result, case, workorder=workorder)
    C.dump_json(out_dir / "field_table.json", main["fields"])
    C.dump_json(out_dir / "result.json", result)
    return result, code


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--case", required=True)
    ap.add_argument("--targets", default="", help="target-fields.json; defaults beside case")
    ap.add_argument("--extraction", required=True)
    ap.add_argument("--sources", default="", help="source snapshot JSON; defaults to case.source_documents/documents")
    ap.add_argument("--out", required=True)
    args = ap.parse_args(argv)
    out = Path(args.out)
    case, err = C.read_json(args.case)
    if err or not isinstance(case, dict):
        C.write_refusal(case, out, err or "case.json must be an object")
        return 5
    target_path = args.targets or str(Path(args.case).parent / "target-fields.json")
    workorder, err = C.read_json(target_path)
    if err or not isinstance(workorder, (dict, list)):
        C.write_refusal(case, out, err or "target-fields.json must be an object or array", workorder=workorder)
        return 5
    try:
        extraction, xerr = C.read_json(args.extraction)
        if xerr or not isinstance(extraction, (dict, list)):
            C.write_refusal(case, out, xerr or "extraction.json must be an object or array", workorder=workorder)
            return 5
        if args.sources:
            bundle, serr = C.read_json(args.sources)
            if serr:
                C.write_refusal(case, out, serr, workorder=workorder)
                return 5
        else:
            bundle = {"documents": case.get("source_documents") or case.get("documents") or
                      (extraction.get("source_documents", []) if isinstance(extraction, dict) else [])}
        result, code = build(case, workorder, extraction, bundle, out)
        print(json.dumps({"case_id": case.get("case_id"), "status": result["status"],
                          "fields": len(result["fields"]), "wrote": str(out / "result.json")}, ensure_ascii=False))
        return code
    except Exception as exc:
        C.write_refusal(case, out, f"v2 extraction could not be completed: {type(exc).__name__}: {exc}", workorder=workorder)
        return 5


if __name__ == "__main__":
    raise SystemExit(main())
