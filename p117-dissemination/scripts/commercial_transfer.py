"""Evidence-bounded research commercialization audit (opt-in, standard library).

The normal dissemination rules stay unchanged for outreach. When a spec declares
``transfer_profile``, this module validates the additional technical/business
artifact and keeps research facts, external evidence and assumptions separate.
It never looks up or invents market size, TRL, IP status or commercial returns.
"""
from __future__ import annotations

from collections import Counter
import json
import re

import guard as G

ALLOWED_CLAIM_TYPES = {"research_fact", "external_evidence", "commercial_assumption", "unknown"}
COMMERCIAL_LISTS = (
    "scientific_facts", "market_evidence", "commercial_assumptions", "quantified_value",
    "validation", "intellectual_property", "pain_points", "applications", "roadmap", "risks",
)


def enabled(spec: dict) -> bool:
    return isinstance(spec, dict) and "transfer_profile" in spec


def profile(spec: dict) -> dict:
    value = spec.get("transfer_profile") if isinstance(spec, dict) else None
    return value if isinstance(value, dict) else {}


def records(profile: dict, key: str) -> list[dict]:
    value = profile.get(key)
    return [x for x in value if isinstance(x, dict)] if isinstance(value, list) else []


def _string(item: dict, key: str) -> str:
    if not isinstance(item, dict):
        return ""
    value = item.get(key)
    return value.strip() if isinstance(value, str) else ""


def _claim_type(item: dict, default="research_fact") -> str:
    value = item.get("claim_type", item.get("status", default))
    return str(value or default).strip().lower()


def _has(item: dict, key: str) -> bool:
    value = item.get(key)
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, dict)):
        return bool(value)
    return True


def _refs(item: dict, key="evidence_refs") -> list[str]:
    value = item.get(key)
    if not isinstance(value, list):
        return []
    return [str(x) for x in value if isinstance(x, (str, int)) and str(x)]


def market_evidence_records(p: dict) -> list[dict]:
    market = p.get("market")
    if not isinstance(market, dict):
        return []
    value = market.get("evidence")
    return [x for x in value if isinstance(x, dict)] if isinstance(value, list) else []


def _fact_ids(p: dict) -> set[str]:
    ids = set()
    for item in records(p, "scientific_facts") + market_evidence_records(p):
        if _string(item, "id"):
            ids.add(_string(item, "id"))
    return ids


def additional_source_ids(spec: dict) -> list[str]:
    """IDs the ordinary citation check may legitimately use in outreach/pitch text."""
    if not enabled(spec):
        return []
    p = profile(spec)
    ids = set(_fact_ids(p))
    for key in ("validation", "intellectual_property", "commercial_assumptions"):
        for item in records(p, key):
            if _string(item, "id"):
                ids.add(_string(item, "id"))
    return sorted(ids)


def supported_quantities(spec: dict) -> Counter:
    """Numbers explicitly supported by external evidence or labelled assumptions.

    Only excerpts and structured quantified records count, not a numeric claim in
    a prose claim field. Ordinary measured values still need source_text.
    """
    result = Counter()
    if not enabled(spec):
        return result
    p = profile(spec)
    for key in ("commercial_assumptions", "quantified_value", "validation"):
        for item in records(p, key) + (market_evidence_records(p) if key == "validation" else []):
            seen_in_record = set()
            for field in ("source_excerpt", "excerpt", "value_excerpt", "quantified_value",
                          "baseline", "target", "result", "method", "time_horizon"): 
                value = item.get(field)
                if isinstance(value, (dict, list)):
                    text = json.dumps(value, ensure_ascii=False, sort_keys=True)
                elif isinstance(value, str):
                    text = value
                else:
                    continue
                for quantity in G.extract_quantities(text):
                    try:
                        numeric = round(float(quantity.value), 9)
                    except (TypeError, ValueError):
                        continue
                    pair = (numeric, quantity.unit or "")
                    if pair not in seen_in_record:
                        # baseline/target repeated in the same calculation are one evidence item,
                        # not independent observations supporting another occurrence.
                        result[pair] += 1
                    seen_in_record.add(pair)
    return result


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", G.normalise(text or "")).strip()


def _audit_facts(p: dict, source_text: str, add) -> None:
    facts = p.get("scientific_facts")
    if isinstance(facts, list) and any(not isinstance(item, dict) for item in facts):
        add("transfer.fact_provenance_missing", "high",
            "every scientific_facts entry must be an object with a source excerpt")
    if not records(p, "scientific_facts"):
        add("transfer.scientific_facts_missing", "high",
            "a transfer draft needs a research-fact ledger rather than a bare promotional narrative")
        facts = []
    for index, item in enumerate(records(p, "scientific_facts")):
        if _claim_type(item) != "research_fact":
            add("transfer.fact_classification_invalid", "high",
                "scientific_facts entries must be research_fact, not a commercial assumption",
                index=index)
        claim, excerpt = _string(item, "claim"), _string(item, "source_excerpt")
        if not claim or not excerpt:
            add("transfer.fact_provenance_missing", "high",
                "a research fact needs a claim and a verbatim source_excerpt", index=index)
        elif not source_text.strip():
            add("transfer.research_fact_not_verifiable", "medium",
                "source_text is absent, so the research excerpt cannot be checked", index=index)
        elif _norm(excerpt) not in _norm(source_text):
            add("transfer.research_fact_not_in_source", "high",
                "the research-fact source_excerpt does not occur in source_text; it may be an "
                "unsupported scientific claim", index=index, excerpt=excerpt[:120])


def _audit_external_evidence(p: dict, add) -> None:
    for index, item in enumerate(market_evidence_records(p)):
        kind = _claim_type(item, "external_evidence")
        if kind not in ("external_evidence", "research_fact"):
            add("transfer.fact_classification_invalid", "high",
                "market_evidence must be external_evidence or research_fact; assumptions belong "
                "in commercial_assumptions", index=index)
        if not _string(item, "claim") or not _string(item, "source_excerpt"):
            add("transfer.market_evidence_missing", "high",
                "an external market claim needs both a claim and a source excerpt", index=index)
        if not _string(item, "locator"):
            add("transfer.external_evidence_unlocated", "high",
                "an external market claim has no report/DOI/URL/database location", index=index)
        claim_q = Counter((round(float(q.value), 9), q.unit or "")
                          for q in G.extract_quantities(_string(item, "claim")))
        excerpt_q = Counter((round(float(q.value), 9), q.unit or "")
                            for q in G.extract_quantities(_string(item, "source_excerpt")))
        unsupported = list((claim_q - excerpt_q).elements())
        if unsupported:
            add("transfer.external_evidence_mismatch", "high",
                "numbers in the market claim do not match its own source excerpt",
                index=index, unsupported=[list(x) for x in unsupported[:10]])


def _audit_reference(item: dict, index: int, source_ids: set[str], add) -> None:
    refs = _refs(item)
    if refs and all(ref in source_ids for ref in refs):
        return
    # A business hypothesis may proceed without evidence only when it is openly
    # labelled AND has a falsifiable/rational basis. It may not pretend to be a fact.
    if _claim_type(item) == "commercial_assumption":
        audit_assumption(item, index, add, source_ids)
        return
    missing = sorted(set(refs) - source_ids)
    add("transfer.validation_evidence_missing", "high",
        "required evidence references are absent or point at no registered research/external fact",
        index=index, missing_references=missing)


def audit_assumption(item: dict, index: int, add, source_ids: set[str] | None = None) -> None:
    references = _refs(item) if isinstance(item, dict) else []
    if references and source_ids is not None:
        missing = sorted(set(references) - source_ids)
        if missing:
            add("transfer.validation_evidence_missing", "high",
                "an assumption cites an unregistered source; remove the false citation or register evidence",
                index=index, missing_references=missing)
    if not _string(item, "basis"):
        add("transfer.assumption_basis_missing", "medium",
            "an unsupported commercial assumption needs its reasoning/calculation basis",
            index=index)
    if not _string(item, "uncertainty"):
        add("transfer.assumption_uncertainty_missing", "medium",
            "a commercial assumption needs its uncertainty or falsification condition", index=index)


def _require_fields(items: list[dict], fields: tuple[str, ...], rule: str, add,
                    source_ids: set[str] | None = None) -> None:
    for index, item in enumerate(items):
        missing = [key for key in fields if not _has(item, key)]
        if missing:
            add(rule, "high", "a commercial transfer section has missing mandatory content",
                index=index, missing=missing)
        if source_ids is not None:
            _audit_reference(item, index, source_ids, add)


_ARITHMETIC = re.compile(
    r"^\s*([-+]?\d+(?:\.\d+)?)\s*([+*/×xX-])\s*([-+]?\d+(?:\.\d+)?)"
    r"\s*=\s*([-+]?\d+(?:\.\d+)?)\s*[^\d\s].*$")
_OPS = {"*": lambda a, b: a * b, "×": lambda a, b: a * b,
        "x": lambda a, b: a * b, "X": lambda a, b: a * b,
        "+": lambda a, b: a + b, "-": lambda a, b: a - b,
        "/": lambda a, b: a / b if b else float("nan")}


def audit_value_arithmetic(item: dict, index: int, add) -> None:
    """Evaluate only a simple numeric equation; never eval arbitrary user text."""
    method = _string(item, "method")
    match = _ARITHMETIC.fullmatch(method)
    if not match:
        return  # Named models require human review, not unsafe eval.
    left, right = float(match.group(1)), float(match.group(3))
    expected = float(match.group(4))
    actual = _OPS[match.group(2)](left, right)
    baseline = G.extract_quantities(_string(item, "baseline"))
    target = G.extract_quantities(_string(item, "target"))
    close = lambda a, b: abs(a - b) <= max(1e-9, abs(a) * 1e-9)
    equation_bad = not close(actual, expected)
    endpoints_bad = ((baseline and not close(left, baseline[0].value))
                     or (target and not close(expected, target[0].value))
                     or (int(match.group(2) in ("*", "×", "x", "X"))
                        and baseline and target and not close(right, expected / baseline[0].value
                                                             if baseline[0].value else actual)))
    if equation_bad or endpoints_bad:
        add("transfer.value_arithmetic_mismatch", "high",
            "quantified-value arithmetic or its baseline/target endpoints does not compute",
            index=index, left=left, right=right, expected_result=expected,
            actual_result=None if actual != actual else actual)


def _audit_profile(p: dict, source_text: str, add) -> None:
    _audit_facts(p, source_text, add)
    _audit_external_evidence(p, add)
    source_ids = _fact_ids(p)

    # User problem / pain point, with its origin distinguished from a hypothesis.
    if not records(p, "pain_points"):
        add("transfer.pain_point_missing", "high",
            "no concrete user problem and intended beneficiary is declared")
    _require_fields(records(p, "pain_points"), ("problem", "user"), "transfer.pain_point_incomplete", add)
    for index, item in enumerate(records(p, "pain_points")):
        _audit_reference(item, index, source_ids, add)

    # TRL is not guessed from adjectives. The evidence and scope must be inspectable.
    maturity = p.get("technology_maturity")
    if not isinstance(maturity, dict):
        add("transfer.maturity_missing", "high",
            "technology_maturity requires level/status, validation scope and evidence references")
        maturity = {}
    level = maturity.get("level")
    level_match = re.fullmatch(r"(?:TRL\s*)?([1-9])", str(level or "").strip(), re.I)
    if not level_match:
        if _claim_type(maturity) == "unknown" and _string(maturity, "notes"):
            add("transfer.unresolved_business_boundary", "medium",
                "technology readiness remains explicitly unknown and needs verification")
        else:
            add("transfer.maturity_unjustified", "high",
                "TRL must be an integer 1..9 or explicit unknown; do not infer it from promotional prose")
    if not _string(maturity, "scope"):
        add("transfer.maturity_scope_missing", "high",
            "the maturity claim does not declare the environment/scale at which it was validated")
    _audit_reference(maturity, 0, source_ids, add)

    # Ownership/IP: unknown is fine, missing or invented registration is not.
    if not records(p, "intellectual_property"):
        add("transfer.ip_missing", "high",
            "intellectual_property must declare ownership/IP status or explicit unknown")
    for index, item in enumerate(records(p, "intellectual_property")):
        kind = _string(item, "status").lower()
        if not _string(item, "type") or not kind:
            add("transfer.ip_incomplete", "high", "IP needs a type and status", index=index)
        if kind == "unknown":
            add("transfer.unresolved_business_boundary", "medium",
                "IP status is deliberately left for legal/owner confirmation", index=index)
        elif not _string(item, "owner") or not _string(item, "reference"):
            add("transfer.ip_evidence_missing", "high",
                "a claimed patent/application/license right needs owner and a checkable reference",
                index=index)
        evidence_class = str(item.get("claim_type") or "external_evidence").strip().lower()
        if evidence_class not in ALLOWED_CLAIM_TYPES:
            add("transfer.fact_classification_invalid", "high",
                "IP claim_type is not research_fact/external_evidence/assumption/unknown",
                index=index)

    # Validation evidence and the application domains it can support.
    if not records(p, "validation"):
        add("transfer.validation_missing", "high",
            "validation evidence is missing; the draft cannot support a transfer-ready claim")
    _require_fields(records(p, "validation"),
                    ("id", "environment", "sample_or_scale", "baseline", "result"),
                    "transfer.validation_incomplete", add, source_ids)
    if not records(p, "applications"):
        add("transfer.application_missing", "high",
            "no concrete application scenario and required conditions is declared")
    _require_fields(records(p, "applications"), ("scenario", "user", "conditions", "painpoint_refs"),
                    "transfer.application_incomplete", add)
    pain_ids = {_string(x, "id") for x in records(p, "pain_points") if _string(x, "id")}
    for index, item in enumerate(records(p, "applications")):
        if not set(_refs(item, "painpoint_refs")) & pain_ids:
            add("transfer.application_unbound", "high",
                "an application scenario does not connect to a declared pain point", index=index)

    # Market/competitor evidence or explicit unknowns. No fabricated market size.
    market = p.get("market")
    if not isinstance(market, dict):
        add("transfer.market_missing", "high",
            "market needs evidence, competitors and explicit unknowns")
        market = {}
    if "evidence" in market and not isinstance(market.get("evidence"), list):
        add("transfer.market_evidence_missing", "high", "market.evidence must be a list")
    if not market_evidence_records(p) and not market.get("unknowns"):
        add("transfer.market_evidence_missing", "high",
            "provide traceable market evidence or name the missing evidence in market.unknowns")
    if not _string(market, "unknowns") and not isinstance(market.get("unknowns"), list):
        add("transfer.market_unknowns_missing", "medium",
            "market.unknowns must name missing evidence or be an explicit empty list")
    competitors = market.get("competitors")
    if not isinstance(competitors, list) or (not competitors and not market.get("unknowns")):
        add("transfer.competitor_missing", "medium",
            "provide actual comparable competitors/baselines or name the missing competitor evidence")
    if isinstance(competitors, list):
        _require_fields([x for x in competitors if isinstance(x, dict)],
                        ("name", "comparison_axis", "evidence_refs"),
                        "transfer.competitor_incomplete", add, source_ids)

    # Separate business assumptions: basis and uncertainty are mandatory.
    if "commercial_assumptions" in p and not isinstance(p.get("commercial_assumptions"), list):
        add("transfer.assumption_registry_malformed", "high",
            "commercial_assumptions must be a list of labelled assumption records")
    for index, item in enumerate(records(p, "commercial_assumptions")):
        if not _string(item, "claim"):
            add("transfer.assumption_claim_missing", "high",
                "a commercial assumption does not state the proposition it qualifies", index=index)
        if _claim_type(item) not in ("commercial_assumption", "unknown"):
            add("transfer.fact_classification_invalid", "high",
                "commercial_assumptions cannot be relabelled as research facts", index=index)
        audit_assumption(item, index, add, source_ids)

    # Implementation route and stop/scale decisions.
    if not records(p, "roadmap"):
        add("transfer.roadmap_missing", "high",
            "the implementation route is not a list of executable stages")
    _require_fields(records(p, "roadmap"),
                    ("stage", "owner", "milestone", "resources", "success_gate", "stop_condition"),
                    "transfer.roadmap_incomplete", add)
    if not records(p, "risks"):
        add("transfer.risk_missing", "high",
            "no execution/IP/market/scale-up risk register is declared")
    _require_fields(records(p, "risks"),
                    ("risk", "likelihood", "impact", "mitigation", "trigger", "owner"),
                    "transfer.risk_incomplete", add)

    # Quantified value requires denominator/baseline/method, not promotional adjectives.
    if not records(p, "quantified_value"):
        add("transfer.value_missing", "high",
            "no baseline-relative quantified value or explicit unknown value is supplied")
    for index, item in enumerate(records(p, "quantified_value")):
        kind = _claim_type(item, "commercial_assumption")
        if kind not in ALLOWED_CLAIM_TYPES:
            add("transfer.fact_classification_invalid", "high",
                "quantified value has an invalid evidence classification", index=index, status=kind)
        if kind == "unknown":
            add("transfer.unresolved_business_boundary", "medium",
                "quantified value remains explicitly unknown", index=index)
            _require_fields([item], ("metric", "notes"), "transfer.value_incomplete", add)
        else:
            _require_fields([item], ("metric", "baseline", "target", "unit", "time_horizon", "method"),
                            "transfer.value_incomplete", add)
            if kind == "commercial_assumption":
                audit_assumption(item, index, add, source_ids)
            else:
                _audit_reference(item, index, source_ids, add)
            audit_value_arithmetic(item, index, add)


def audit(spec: dict, source_text: str, add) -> None:
    """Audit an opted-in profile. Ordinary outreach without the key is untouched."""
    if not enabled(spec):
        return
    p = spec.get("transfer_profile")
    if not isinstance(p, dict):
        add("transfer.profile_malformed", "high",
            "transfer_profile must be an object containing evidence and business ledgers")
        return
    _audit_profile(p, source_text, add)


def summary(spec: dict) -> dict | None:
    if not enabled(spec):
        return None
    p = profile(spec)
    unknowns = []
    for key in COMMERCIAL_LISTS:
        for index, item in enumerate(records(p, key)):
            if _claim_type(item, "research_fact") == "unknown":
                unknowns.append({"section": key, "index": index})
    maturity = p.get("technology_maturity")
    if isinstance(maturity, dict) and _claim_type(maturity) == "unknown":
        unknowns.append({"section": "technology_maturity"})
    return {
        "scientific_facts": [_string(x, "id") for x in records(p, "scientific_facts") if _string(x, "id")],
        "external_evidence": [_string(x, "id") for x in market_evidence_records(p) if _string(x, "id")],
        "commercial_assumptions": len(records(p, "commercial_assumptions")),
        "validation_records": len(records(p, "validation")),
        "quantified_value_records": len(records(p, "quantified_value")),
        "explicit_unknowns": unknowns,
        "evidence_boundary": "IDs and excerpts support traceability only; external registry/market truth is not independently verified",
    }


def open_questions(spec: dict) -> list[dict]:
    if not enabled(spec):
        return []
    p = profile(spec)
    summary_data = summary(spec) or {}
    out = [dict(x, type="human_review") for x in summary_data.get("explicit_unknowns", [])]
    market = p.get("market")
    if isinstance(market, dict) and market.get("unknowns"):
        out.append({"type": "human_review", "section": "market", "items": market["unknowns"]})
    return out
