"""Deterministic research-trend analysis over an exact, reviewable literature corpus.

The engine computes products rather than merely auditing prose: deduplication and
screening ledgers, annual counts, topic/year shares, bounded change-point evidence,
phase-aware representative selection, and research-gap exclusion tests.  It uses
only the standard library and never treats an absent retrieval result as a global
research gap.
"""
from __future__ import annotations

import csv
import itertools
import json
import math
import random
import re
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path
from statistics import mean

SCHEMA = "trend-analysis/v2"
GAP_TYPES = {"repeated_unresolved", "method_failure", "conflicting_evidence"}
EVENT_TYPES = {"emergence", "merge", "split", "decline"}
STATEMENT_TYPES = {"fact", "inference", "undetermined"}


def _norm(value) -> str:
    return re.sub(r"\s+", " ", unicodedata.normalize("NFKC", str(value or ""))).strip()


def _key(value) -> str:
    return _norm(value).casefold().replace("‑", "-").replace("–", "-")


def _add(findings: list[dict], rule: str, severity: str, message: str, **detail) -> None:
    findings.append({"rule": rule, "severity": severity, "message": message, **detail})


def _as_list(value) -> list:
    if value in (None, ""):
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    return [value]


def _int(value):
    if value in (None, ""):
        return None
    try:
        number = int(str(value).strip())
    except (TypeError, ValueError):
        return None
    return number if 1000 <= number <= 9999 else None


def _number(value):
    if value in (None, ""):
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def load_records_file(path: str | Path) -> list[dict]:
    """Read JSON, JSONL or CSV records; parsing errors are named, not swallowed."""
    path = Path(path)
    suffix = path.suffix.casefold()
    if suffix == ".csv":
        with path.open("r", encoding="utf-8-sig", newline="") as fh:
            rows = []
            for row in csv.DictReader(fh):
                converted = dict(row)
                for field in ("topics", "keywords", "methods", "objects", "scales", "contribution_type"):
                    if isinstance(converted.get(field), str):
                        converted[field] = [x.strip() for x in re.split(r"[|;]", converted[field]) if x.strip()]
                for field in ("excerpts", "screening", "disambiguation"):
                    raw = converted.get(field)
                    if isinstance(raw, str) and raw.strip().startswith(("[", "{")):
                        converted[field] = json.loads(raw)
                if isinstance(converted.get("citation_count"), str):
                    converted["citation_count"] = _number(converted["citation_count"])
                if isinstance(converted.get("first_method"), str):
                    converted["first_method"] = converted["first_method"].strip().casefold() in ("1", "true", "yes")
                rows.append(converted)
            return rows
    if suffix in (".jsonl", ".ndjson"):
        rows = []
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if not line.strip():
                continue
            item = json.loads(line)
            if not isinstance(item, dict):
                raise ValueError(f"{path.name}:{lineno} is not a record object")
            rows.append(item)
        return rows
    value = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(value, dict):
        value = value.get("records", value.get("documents"))
    if not isinstance(value, list) or any(not isinstance(x, dict) for x in value):
        raise ValueError("record file must contain a list of objects (or a records/documents list)")
    return value


def _source_rows(spec: dict, spec_dir: Path) -> list[dict]:
    rows = list(spec.get("records") or spec.get("documents") or [])
    source = spec.get("records_path")
    if source:
        path = Path(str(source))
        if not path.is_absolute():
            path = spec_dir / path
        rows.extend(load_records_file(path))
    if any(not isinstance(x, dict) for x in rows):
        raise ValueError("every literature record must be an object")
    return rows


def _decision(record: dict) -> str:
    screening = record.get("screening") if isinstance(record.get("screening"), dict) else {}
    value = record.get("screening_decision", record.get("decision", screening.get("decision")))
    value = _key(value)
    if value in ("include", "included", "yes", "纳入"):
        return "include"
    if value in ("exclude", "excluded", "no", "排除"):
        return "exclude"
    return "undetermined"


def _screen_reason(record: dict) -> tuple[str, str]:
    screening = record.get("screening") if isinstance(record.get("screening"), dict) else {}
    reason = _norm(record.get("screening_reason", record.get("reason", screening.get("reason"))))
    code = _key(record.get("reason_code", screening.get("reason_code")))
    return reason, code


def _record_text(record: dict) -> str:
    parts = [record.get(k) for k in ("title", "abstract", "keywords", "topics", "full_text")]
    for excerpt in _as_list(record.get("excerpts")):
        if isinstance(excerpt, dict):
            parts.extend([excerpt.get("text"), excerpt.get("quote")])
        else:
            parts.append(excerpt)
    return _norm(" ".join(_norm(x) for x in parts if x not in (None, "", [])))


def _term_present(term: str, text: str) -> bool:
    term, text = _key(term), _key(text)
    if not term:
        return False
    if re.search(r"[\u3400-\u9fff]", term):
        return term in text
    return re.search(r"(?<![a-z0-9])" + re.escape(term) + r"(?![a-z0-9])", text) is not None


def _year_for(record: dict, basis: str) -> tuple[int | None, str]:
    fields = {
        "publication": ("publication_year", "year"),
        "online": ("online_year",),
        "print": ("print_year",),
        "preprint": ("preprint_year",),
    }
    for field in fields.get(basis, ("year",)):
        year = _int(record.get(field))
        if year is not None:
            return year, field
    # A generic year can serve a non-publication basis only when the record
    # explicitly declares that its year has that meaning.
    if basis != "publication" and _key(record.get("year_type")) == basis:
        year = _int(record.get("year"))
        if year is not None:
            return year, "year (declared year_type=" + basis + ")"
    return None, "missing"


def _auto_decision(record: dict, protocol: dict) -> tuple[str, str, str]:
    """Prospective rules can screen only when auto_apply is explicitly enabled."""
    if not protocol.get("auto_apply"):
        return "undetermined", "", "prospective decision not executed"
    text = _record_text(record)
    excluded = [x for x in _as_list(protocol.get("exclude_terms")) if _term_present(str(x), text)]
    if excluded:
        return "exclude", "matched prospective exclusion term: " + ", ".join(map(str, excluded)), "exclusion_term"
    required = _as_list(protocol.get("must_match_any"))
    if required and not any(_term_present(str(x), text) for x in required):
        return "exclude", "no required research-question term in the declared fields", "off_topic"
    if protocol.get("require_abstract") and not _norm(record.get("abstract")):
        return "undetermined", "abstract required by protocol but unavailable", "missing_abstract"
    return "include", "all declared prospective automatic criteria matched", "protocol_match"


def prepare_records(spec: dict, spec_dir: Path, findings: list[dict]) -> tuple[list[dict], dict, list[dict]]:
    raw = _source_rows(spec, spec_dir)
    protocol = spec.get("search_protocol") if isinstance(spec.get("search_protocol"), dict) else {}
    screening_protocol = spec.get("screening_protocol") if isinstance(spec.get("screening_protocol"), dict) else {}
    if not raw:
        _add(findings, "tr.no_records", "high", "no literature records were supplied")
    if not _norm(spec.get("research_question", spec.get("question"))):
        _add(findings, "tr.research_question_missing", "high", "no research question bounds the analysis")
    if not protocol:
        _add(findings, "tr.protocol_missing", "high", "no search protocol was supplied")
    for field in ("sources", "queries", "start_year", "end_year", "year_basis"):
        if protocol.get(field) in (None, "", []):
            _add(findings, "tr.protocol_field_missing", "high",
                 "the search protocol omits a field needed to reproduce scope and year slicing",
                 field=field)
    start, end = _int(protocol.get("start_year")), _int(protocol.get("end_year"))
    if start and end and end < start:
        _add(findings, "tr.protocol_window_invalid", "high", "the protocol end year precedes its start year")
    elif start and end and end - start > 200:
        _add(findings, "tr.protocol_window_invalid", "high", "the declared year window exceeds 200 years")
    basis = _key(protocol.get("year_basis")) or "unspecified"
    if basis not in ("publication", "online", "print", "preprint"):
        _add(findings, "tr.year_basis_unknown", "high", "the declared year basis is unsupported", basis=basis)
        basis = "publication"

    rows: list[dict] = []
    seen_ids: dict[str, str] = {}
    seen_identity: dict[str, str] = {}
    for index, original in enumerate(raw, 1):
        record = dict(original)
        rid = _norm(record.get("record_id", record.get("id"))) or f"R{index:03d}"
        record["original_index"] = index
        record["record_id"] = rid
        if rid in seen_ids:
            _add(findings, "tr.record_id_duplicate", "high",
                 "two input rows share one record id, so evidence references are ambiguous", record_id=rid)
            rid = f"{rid}__row{index}"
            record["record_id"] = rid
        else:
            seen_ids[rid] = rid
        doi = _key(record.get("doi"))
        doi = re.sub(r"^https?://(?:dx\.)?doi\.org/", "", doi).rstrip(".")
        title_key = re.sub(r"[^a-z0-9\u3400-\u9fff]+", "", _key(record.get("title")))
        identity = ("doi:" + doi) if doi else ("title:" + title_key if title_key else f"row:{index}")
        duplicate_of = seen_identity.get(identity)
        if duplicate_of:
            record["duplicate_of"] = duplicate_of
            _add(findings, "tr.duplicate_version", "medium",
                 "a DOI/title duplicate was retained in the ledger but excluded from statistics",
                 record_id=rid, duplicate_of=duplicate_of, identity=identity.split(":", 1)[0])
        else:
            seen_identity[identity] = rid
        record["doi_normalized"] = doi or "not_reported"

        decision = _decision(record)
        reason, reason_code = _screen_reason(record)
        if decision == "undetermined" and not duplicate_of:
            decision, auto_reason, auto_code = _auto_decision(record, screening_protocol)
            if auto_reason:
                reason, reason_code = auto_reason, auto_code
        if duplicate_of:
            decision, reason_code = "exclude", "duplicate"
            reason = f"duplicate/version of {duplicate_of}; retained only in audit ledger"
        record["screening_decision_normalized"] = decision
        record["screening_reason_normalized"] = reason or "not_reported"
        record["reason_code_normalized"] = reason_code or "not_reported"
        if decision == "undetermined":
            _add(findings, "tr.screening_decision_missing", "high",
                 "a record remains undetermined and cannot silently enter or leave the corpus",
                 record_id=rid)
        if decision == "exclude" and not reason_code and not reason:
            _add(findings, "tr.exclusion_reason_missing", "high",
                 "an excluded record has neither a reason nor a reason code", record_id=rid)
        year, provenance = _year_for(record, basis)
        record["year_used"] = year
        record["year_provenance"] = provenance
        if decision == "include" and year is None:
            _add(findings, "tr.year_missing", "medium",
                 "an included record lacks the year required by the declared basis; it is not counted as zero",
                 record_id=rid, year_basis=basis)
        record["year_basis"] = basis
        complete_through = _int(protocol.get("complete_through"))
        record["incomplete_year"] = bool(year and complete_through and year > complete_through)
        record["outside_window"] = bool(year and start and end and not start <= year <= end)
        record["included_in_corpus"] = decision == "include" and not duplicate_of
        record["included_in_trends"] = bool(record["included_in_corpus"] and year is not None
                                             and not record["outside_window"] and not record["incomplete_year"])
        if not record["included_in_trends"] and record["included_in_corpus"]:
            reason = ("missing year" if year is None else "outside protocol window" if record["outside_window"]
                      else "incomplete year" if record["incomplete_year"] else "not counted")
            record["trend_exclusion"] = reason
        rows.append(record)
    if raw and not any(r["included_in_corpus"] for r in rows):
        _add(findings, "tr.no_included_records", "high", "no record is eligible after deduplication and screening")
    uncertainty = []
    for record in rows:
        if record["included_in_corpus"] and not record["included_in_trends"]:
            uncertainty.append({"kind": "time_slice_exclusion", "record_id": record["record_id"],
                                "reason": record.get("trend_exclusion", "not counted")})
    return rows, protocol, uncertainty


def evidence_matrix(rows: list[dict]) -> list[dict]:
    matrix = []
    for r in rows:
        excerpts = [x for x in _as_list(r.get("excerpts")) if isinstance(x, dict)]
        locators = [_norm(x.get("locator")) for x in excerpts if _norm(x.get("locator"))]
        if _norm(r.get("locator")):
            locators.insert(0, _norm(r.get("locator")))
        if r["included_in_corpus"] and not locators:
            # The finding is emitted by audit_cross_references, where findings is available.
            pass
        matrix.append({
            "record_id": r["record_id"], "doi": r.get("doi_normalized", "not_reported"),
            "title": _norm(r.get("title")) or "not_reported",
            "year_used": r.get("year_used") if r.get("year_used") is not None else "not_reported",
            "year_basis": r.get("year_basis"), "year_provenance": r.get("year_provenance"),
            "source_type": _norm(r.get("source_type")) or "not_reported",
            "screening_decision": r.get("screening_decision_normalized"),
            "screening_reason": r.get("screening_reason_normalized"),
            "reason_code": r.get("reason_code_normalized"),
            "duplicate_of": r.get("duplicate_of"),
            "included_in_trends": r.get("included_in_trends"),
            "trend_exclusion": r.get("trend_exclusion"),
            "topics": [_norm(x) for x in _as_list(r.get("topics"))],
            "method": [_norm(x) for x in _as_list(r.get("methods"))] or "not_reported",
            "object": [_norm(x) for x in _as_list(r.get("objects", r.get("object")))] or "not_reported",
            "scale": [_norm(x) for x in _as_list(r.get("scales", r.get("scale")))] or "not_reported",
            "contribution_type": [_norm(x) for x in _as_list(r.get("contribution_type"))],
            "citation_count": r.get("citation_count") if r.get("citation_count") is not None else "not_reported",
            "locators": locators or ["not_reported"],
            "source_file": _norm(r.get("source_file", r.get("source"))) or "not_reported",
        })
    return matrix


def _permutation_p(left: list[float], right: list[float]) -> tuple[float, int, str]:
    pooled = left + right
    n_left = len(left)
    observed = abs(mean(right) - mean(left))
    n = len(pooled)
    if n <= 10:
        extreme = 0
        total = 0
        for indices in itertools.combinations(range(n), n_left):
            chosen = set(indices)
            a = [pooled[i] for i in range(n) if i in chosen]
            b = [pooled[i] for i in range(n) if i not in chosen]
            extreme += abs(mean(a) - mean(b)) >= observed - 1e-12
            total += 1
        return extreme / total, total, "exact_two_sided_permutation"
    rng = random.Random(20261123 + n * 1009 + n_left)
    extreme = 0
    iterations = 2000
    for _ in range(iterations):
        shuffled = list(pooled)
        rng.shuffle(shuffled)
        extreme += abs(mean(shuffled[:n_left]) - mean(shuffled[n_left:])) >= observed - 1e-12
    return (extreme + 1) / (iterations + 1), iterations + 1, "deterministic_monte_carlo_permutation"


def _annual_for(rows: list[dict], basis: str, start: int, end: int, complete_through=None) -> list[dict]:
    counts = Counter()
    for r in rows:
        if not r.get("included_in_corpus"):
            continue
        year, _ = _year_for(r, basis)
        if year is not None and start <= year <= end and (complete_through is None or year <= complete_through):
            counts[year] += 1
    total = sum(counts.values())
    output = []
    for year in range(start, end + 1):
        if complete_through is not None and year > complete_through:
            continue
        count = counts[year]
        output.append({"year": year, "count": count,
                       "corpus_share": round(count / total, 6) if total else None,
                       "evidence": [f"evidence_matrix.csv#year_used={year}&included_in_trends=True"]})
    return output


def _change_points(annual: list[dict], min_segment=2, alpha=0.05) -> list[dict]:
    candidates = []
    raw = []
    for pos in range(min_segment, len(annual) - min_segment + 1):
        left = [float(x["count"]) for x in annual[:pos]]
        right = [float(x["count"]) for x in annual[pos:]]
        if not left or not right:
            continue
        left_mean, right_mean = mean(left), mean(right)
        p, permutations, method = _permutation_p(left, right)
        raw.append({"year": annual[pos]["year"], "left_years": [annual[0]["year"], annual[pos - 1]["year"]],
                    "right_years": [annual[pos]["year"], annual[-1]["year"]],
                    "left_mean": round(left_mean, 6), "right_mean": round(right_mean, 6),
                    "absolute_difference": round(right_mean - left_mean, 6),
                    "relative_difference": (round((right_mean - left_mean) / abs(left_mean), 6)
                                              if left_mean else None),
                    "p_value": p, "permutations": permutations, "method": method,
                    "left_values": left, "right_values": right})
    multiplicity = len(raw)
    for item in raw:
        item["bonferroni_p"] = min(1.0, item["p_value"] * multiplicity) if multiplicity else None
        item["multiplicity"] = multiplicity
        item["alpha"] = alpha
        item["supported"] = item["bonferroni_p"] is not None and item["bonferroni_p"] <= alpha
        item["interpretation"] = ("supported turning point within this corpus" if item["supported"]
                                  else "not distinguished from discrete fluctuation")
        item["evidence"] = [f"annual_counts.csv#year={y}" for y in range(
            item["left_years"][0], item["right_years"][1] + 1)]
        candidates.append(item)
    return candidates


def compute_time(rows: list[dict], protocol: dict, spec: dict) -> dict:
    start, end = _int(protocol.get("start_year")), _int(protocol.get("end_year"))
    basis = _key(protocol.get("year_basis")) or "publication"
    if start is None or end is None or end < start or end - start > 200:
        return {"year_basis": basis, "annual_counts": [], "change_point_candidates": [],
                "phases": [], "interpretations": [], "limits": ["valid year window unavailable"]}
    complete_through = _int(protocol.get("complete_through"))
    effective_end = min(end, complete_through) if complete_through else end
    annual = _annual_for(rows, basis, start, effective_end)
    total = sum(x["count"] for x in annual)
    for index, row in enumerate(annual):
        previous = annual[index - 1]["count"] if index else None
        row["previous_count"] = previous
        row["absolute_change"] = row["count"] - previous if previous is not None else None
        row["growth_rate"] = ((row["count"] - previous) / previous) if previous else None
        lo = max(0, index - 2)
        row["moving_average_3"] = round(mean([x["count"] for x in annual[lo:index + 1]]), 6)
        if row["growth_rate"] is not None:
            row["growth_rate"] = round(row["growth_rate"], 6)
    cagr = None
    if len(annual) > 1 and annual[0]["count"] > 0 and annual[-1]["count"] >= 0:
        cagr = (annual[-1]["count"] / annual[0]["count"]) ** (1 / (len(annual) - 1)) - 1
    config = spec.get("change_point_config") if isinstance(spec.get("change_point_config"), dict) else {}
    min_segment = int(config.get("min_segment", 2))
    alpha = float(config.get("alpha", 0.05))
    candidates = _change_points(annual, max(1, min_segment), alpha)
    supported = [x for x in candidates if x["supported"]]
    best = min(supported, key=lambda x: (-abs(x["absolute_difference"]), x["year"])) if supported else None

    if best:
        phase_specs = [
            ("phase_before_" + str(best["year"]), start, best["year"] - 1,
             f"segment before {best['year']}; Bonferroni-adjusted permutation evidence"),
            ("phase_from_" + str(best["year"]), best["year"], effective_end,
             f"segment from {best['year']}; Bonferroni-adjusted permutation evidence"),
        ]
    else:
        phase_specs = [("observed_window", start, effective_end,
                        "single descriptive phase: no turning point survived multiplicity correction")]
    phases = [{"phase_id": pid, "start_year": a, "end_year": b, "basis": rationale,
               "statement_type": "inference", "evidence": best["evidence"] if best else
               [f"annual_counts.csv#year={x['year']}" for x in annual]}
              for pid, a, b, rationale in phase_specs if a <= b]
    interpretations = [{
        "id": "window_change", "statement_type": "fact",
        "text": f"在 {start}–{effective_end} 的既定口径内，纳入计数由 {annual[0]['count']} 变为 {annual[-1]['count']}；"
                f"净变化 {annual[-1]['count'] - annual[0]['count']}，CAGR 为 {cagr if cagr is not None else '不可计算'}。",
        "evidence": [f"annual_counts.csv#year={start}", f"annual_counts.csv#year={effective_end}"],
        "scope": "included, deduplicated records with the declared year basis only",
    }]
    interpretations.append({
        "id": "turning_point_verdict", "statement_type": "inference",
        "text": (f"{best['year']} 是本语料内经 Bonferroni 校正后支持的候选拐点；该统计不支持原因解释。"
                 if best else "没有候选拐点经 Bonferroni 校正后达到声明阈值；年度变化保留为波动候选，不写成确定性衰退或爆发。"),
        "evidence": best["evidence"] if best else [f"annual_counts.csv#year={x['year']}" for x in annual],
        "confidence": "bounded_by_small_time_series_and_corpus_coverage",
    })

    sensitivity = []
    for alternate in ("online", "print", "publication", "preprint"):
        if alternate == basis:
            continue
        availability = sum(1 for r in rows if r.get("included_in_corpus") and _year_for(r, alternate)[0] is not None)
        if not availability:
            continue
        alt_annual = _annual_for(rows, alternate, start, effective_end)
        alt_candidates = _change_points(alt_annual, max(1, min_segment), alpha)
        alt_supported = [x["year"] for x in alt_candidates if x["supported"]]
        sensitivity.append({"year_basis": alternate, "records_with_year": availability,
                            "annual_counts": alt_annual,
                            "supported_change_points": alt_supported,
                            "primary_supported_change_points": [x["year"] for x in supported],
                            "classification_changed": alt_supported != [x["year"] for x in supported],
                            "note": "sensitivity table, not a pooled mixture of date definitions"})
    incomplete = sorted({r["year_used"] for r in rows if r.get("incomplete_year") and r.get("year_used")})
    return {"year_basis": basis, "window": {"start_year": start, "end_year": end,
             "complete_through": complete_through, "analysis_end_year": effective_end},
            "annual_counts": annual, "total_counted": total, "cagr": cagr,
            "change_point_method": {"test": "two-sided permutation on segment mean count difference",
                                    "multiplicity": "Bonferroni across candidate years",
                                    "min_segment": min_segment, "alpha": alpha},
            "change_point_candidates": candidates, "supported_change_points": [x["year"] for x in supported],
            "phases": phases, "interpretations": interpretations,
            "incomplete_years_excluded": incomplete, "year_basis_sensitivity": sensitivity,
            "limits": ["observational bibliometric counts do not identify causes",
                       "zero means no included record in this fixed corpus, not global absence"]}


def compute_topics(rows: list[dict], protocol: dict, spec: dict, findings: list[dict]) -> dict:
    alias_spec = spec.get("topic_aliases") if isinstance(spec.get("topic_aliases"), dict) else {}
    alias_to_topic = {}
    canonical = set()
    for topic, variants in alias_spec.items():
        canonical.add(str(topic))
        values = variants.get("variants", []) if isinstance(variants, dict) else variants
        for variant in [topic] + list(_as_list(values)):
            alias_to_topic[_key(variant)] = str(topic)
    for r in rows:
        if not r.get("included_in_corpus"):
            continue
        for topic in _as_list(r.get("topics")):
            mapped = alias_to_topic.get(_key(topic), _norm(topic))
            canonical.add(mapped)
            alias_to_topic.setdefault(_key(topic), mapped)
    ambiguous = spec.get("ambiguous_terms") if isinstance(spec.get("ambiguous_terms"), list) else []
    assigned: dict[str, list[str]] = {}
    assignments = []
    terminology: dict[str, dict] = {}
    for r in rows:
        if not r.get("included_in_corpus"):
            continue
        rid = r["record_id"]
        topics = []
        for raw_topic in _as_list(r.get("topics")):
            topic = alias_to_topic.get(_key(raw_topic), _norm(raw_topic))
            if topic:
                topics.append(topic)
                assignments.append({"record_id": rid, "topic": topic, "variant": _norm(raw_topic),
                                    "method": "declared_topic_normalized", "evidence": f"evidence_matrix.csv#{rid}"})
        text = _record_text(r)
        if not topics:
            for variant, topic in sorted(alias_to_topic.items()):
                if _term_present(variant, text):
                    topics.append(topic)
                    assignments.append({"record_id": rid, "topic": topic, "variant": variant,
                                        "method": "alias_match", "evidence": f"record:{rid} title/abstract/keywords"})
        for definition in ambiguous:
            if not isinstance(definition, dict):
                continue
            term = _norm(definition.get("term"))
            if not term or not _term_present(term, text):
                continue
            context_map = definition.get("topic_by_context") if isinstance(definition.get("topic_by_context"), dict) else {}
            supplied = r.get("disambiguation") if isinstance(r.get("disambiguation"), dict) else {}
            topic = supplied.get(term) or supplied.get(_key(term))
            context_used = "record_disambiguation" if topic else None
            if not topic:
                hits = [(context, mapped) for context, mapped in context_map.items() if _term_present(context, text)]
                if len({str(mapped) for _, mapped in hits}) == 1 and hits:
                    context_used, topic = hits[0]
            if not topic:
                _add(findings, "tr.topic_ambiguity_unresolved", "high",
                     "an ambiguous term occurs without a unique context/disambiguation; it was not merged",
                     record_id=rid, term=term)
            else:
                topics.append(str(topic))
                assignments.append({"record_id": rid, "topic": str(topic), "variant": term,
                                    "method": "context_disambiguated", "context": context_used,
                                    "evidence": f"record:{rid} disambiguation"})
                canonical.add(str(topic))
        topics = sorted(set(topics))
        assigned[rid] = topics
        if not topics:
            _add(findings, "tr.topic_unassigned", "medium",
                 "an included record has no defensible topic assignment", record_id=rid)
        for topic in topics:
            variants = {a["variant"] for a in assignments if a["record_id"] == rid and a["topic"] == topic}
            for variant in variants:
                entry = terminology.setdefault(variant, {"variant": variant, "canonical_topic": topic,
                                                         "records": set(), "years": set()})
                entry["records"].add(rid)
                if r.get("year_used") is not None:
                    entry["years"].add(r["year_used"])

    annual = _annual_for(rows, _key(protocol.get("year_basis")) or "publication",
                         _int(protocol.get("start_year")) or 0, _int(protocol.get("end_year")) or 0,
                         _int(protocol.get("complete_through")))
    matrix = []
    for topic in sorted(canonical):
        for row in annual:
            year = row["year"]
            count = sum(1 for r in rows if r.get("included_in_trends") and topic in assigned.get(r["record_id"], [])
                        and r.get("year_used") == year)
            matrix.append({"topic": topic, "year": year, "count": count,
                           "annual_included_count": row["count"],
                           "share": round(count / row["count"], 6) if row["count"] else None,
                           "share_denominator": "all included trend-counted records in that year",
                           "multi_label": True,
                           "evidence": [f"topic_year_matrix.csv#topic={topic}&year={year}"]})
    summaries = []
    for topic in sorted(canonical):
        cells = [x for x in matrix if x["topic"] == topic]
        nonzero = [x for x in cells if x["count"]]
        total = sum(x["count"] for x in cells)
        peak = max((x["count"] for x in cells), default=0)
        summary = {"topic": topic, "total_assignments": total,
                   "first_observed_year": nonzero[0]["year"] if nonzero else None,
                   "last_observed_year": nonzero[-1]["year"] if nonzero else None,
                   "peak_years": [x["year"] for x in cells if x["count"] == peak and peak],
                   "first_observation_scope": "first appearance in this fixed corpus, not invention date",
                   "evidence": [x["evidence"][0] for x in nonzero]}
        if nonzero and cells[-1]["count"] == 0 and nonzero[-1]["year"] < cells[-1]["year"]:
            summary["decline_candidate"] = {"statement_type": "inference",
                "text": "latest declared year has zero assignments after earlier presence; absence is corpus-bounded",
                "evidence": [nonzero[-1]["evidence"][0], cells[-1]["evidence"][0]]}
        summaries.append(summary)
    terms = []
    for entry in terminology.values():
        years = sorted(entry["years"])
        terms.append({"variant": entry["variant"], "canonical_topic": entry["canonical_topic"],
                      "records": sorted(entry["records"]), "first_year": years[0] if years else None,
                      "last_year": years[-1] if years else None,
                      "note": "alias normalized only under the declared mapping"})
    return {"assignments": assignments, "topic_year_matrix": matrix, "topic_summaries": summaries,
            "terminology": sorted(terms, key=lambda x: (x["canonical_topic"], x["variant"])),
            "multi_label_note": "a record may have multiple topics; topic shares need not sum to one",
            "homonym_note": "ambiguous terms without context remain unassigned and generate findings"}


def select_representatives(rows: list[dict], phases: list[dict], spec: dict,
                           findings: list[dict]) -> list[dict]:
    config = spec.get("representative_config") if isinstance(spec.get("representative_config"), dict) else {}
    if _key(config.get("selection_method")) in ("citations", "citations_only", "citation_count"):
        _add(findings, "tr.citation_only_selection", "high",
             "representative selection must not rank solely by total citation count")
    quota = int(config.get("per_phase", 2))
    if quota < 1:
        _add(findings, "tr.representative_quota_invalid", "medium", "per_phase must be positive; one was used")
        quota = 1
    weights = {"method_first": 4.0, "contribution": 2.0, "evidence": 2.0, "citation": 1.0}
    if isinstance(config.get("weights"), dict):
        for key in weights:
            value = _number(config["weights"].get(key))
            if value is not None and value >= 0:
                weights[key] = value
    selected = []
    for phase in phases:
        candidates = [r for r in rows if r.get("included_in_trends")
                      and phase["start_year"] <= r["year_used"] <= phase["end_year"]]
        if not candidates:
            _add(findings, "tr.representative_phase_missing", "high",
                 "a declared phase has no eligible included record", phase_id=phase["phase_id"])
            continue
        citation_values = sorted(_number(r.get("citation_count")) for r in candidates
                                 if _number(r.get("citation_count")) is not None)
        for r in candidates:
            if r.get("citation_count") not in (None, "") and _number(r.get("citation_count")) is None:
                _add(findings, "tr.citation_count_invalid", "medium",
                     "a declared citation count is not a finite number", record_id=r["record_id"])
        scored = []
        for r in candidates:
            citations = _number(r.get("citation_count"))
            percentile = None
            if citations is not None and citation_values:
                below = sum(v < citations for v in citation_values)
                equal = sum(v == citations for v in citation_values)
                percentile = (below + 0.5 * equal) / len(citation_values)
            first = bool(r.get("first_method"))
            contributions = [_key(x) for x in _as_list(r.get("contribution_type"))]
            has_contribution = bool(contributions)
            locators = [_norm(x.get("locator")) for x in _as_list(r.get("excerpts"))
                        if isinstance(x, dict) and _norm(x.get("locator"))]
            if _norm(r.get("locator")):
                locators.append(_norm(r.get("locator")))
            score = (weights["method_first"] * first + weights["contribution"] * has_contribution
                     + weights["evidence"] * bool(locators)
                     + weights["citation"] * (percentile or 0))
            reasons = []
            if first:
                reasons.append("method-first flag preserved even for a low-citation/long-tail work")
            if has_contribution:
                reasons.append("contribution type declared: " + ", ".join(contributions))
            if locators:
                reasons.append("exact source locator available")
            if percentile is not None:
                reasons.append(f"within-phase citation percentile {percentile:.3f}, only a weighted component")
            scored.append((score, r, {"score": round(score, 6), "citation_percentile_within_phase": percentile,
                                      "reasons": reasons, "locators": locators or ["not_reported"]}))
        scored.sort(key=lambda x: (-x[0], x[1]["record_id"]))
        chosen = []
        first_candidates = [x for x in scored if x[1].get("first_method")]
        if first_candidates:
            chosen.append(first_candidates[0])
        for item in scored:
            if item not in chosen:
                chosen.append(item)
            if len(chosen) >= quota:
                break
        for score, r, detail in chosen[:quota]:
            selected.append({"record_id": r["record_id"], "title": _norm(r.get("title")),
                             "year": r.get("year_used"), "phase_id": phase["phase_id"],
                             "phase_window": [phase["start_year"], phase["end_year"]],
                             "selection_method": "phase-aware method-first + contribution + evidence + within-phase citation",
                             "weights": weights, "selection_score": score, **detail,
                             "evidence": [f"evidence_matrix.csv#{r['record_id']}"],
                             "statement_type": "inference",
                             "scope": "representative of this declared phase/corpus, not a global best-work list"})
    return selected


def _included_map(rows: list[dict]) -> dict[str, dict]:
    return {r["record_id"]: r for r in rows if r.get("included_in_corpus")}


def _validate_evidence(evidence: list, included: dict[str, dict], findings: list[dict], owner: str) -> list[dict]:
    validated = []
    for index, item in enumerate(evidence):
        if not isinstance(item, dict):
            _add(findings, "tr.evidence_shape_invalid", "high", "evidence item is not an object", owner=owner)
            continue
        rid = _norm(item.get("record_id", item.get("source_id", item.get("key"))))
        locator = _norm(item.get("locator"))
        quote = _norm(item.get("quote", item.get("text")))
        valid = True
        if rid not in included:
            valid = False
            _add(findings, "tr.evidence_unknown_record", "high",
                 "evidence points to no included, deduplicated record", owner=owner, record_id=rid)
        if not locator:
            valid = False
            _add(findings, "tr.evidence_locator_missing", "high",
                 "exact-source evidence lacks a page/section/paragraph/table locator", owner=owner, record_id=rid)
        elif not re.search(r"(?:\b(?:p\.?|pp\.?|page|sec(?:tion)?\.?|fig(?:ure)?\.?|table|tab\.?|para(?:graph)?\.?)\s*\d+"
                           r"|第\s*\d+\s*页|¶\s*\d+|图\s*\d+|表\s*\d+|#\s*\d+)", locator, re.I):
            valid = False
            _add(findings, "tr.evidence_locator_vague", "medium",
                 "the locator does not identify a page, section, figure, table or numbered paragraph",
                 owner=owner, record_id=rid, locator=locator)
        if not quote:
            valid = False
            _add(findings, "tr.evidence_quote_missing", "high", "exact-source evidence has no quote", owner=owner)
        elif rid in included:
            text = _record_text(included[rid])
            if not text:
                valid = False
                _add(findings, "tr.evidence_source_text_missing", "high",
                     "the attributed record supplies no text against which the quote can be checked",
                     owner=owner, record_id=rid)
            elif _key(quote) not in _key(text):
                valid = False
                _add(findings, "tr.evidence_quote_mismatch", "high",
                     "the evidence quote does not occur in the attributed record's supplied text",
                     owner=owner, record_id=rid, quote=quote[:120])
        if valid:
            validated.append({**item, "record_id": rid, "locator": locator, "quote": quote})
    return validated


def assess_gaps(rows: list[dict], spec: dict, protocol: dict, findings: list[dict]) -> list[dict]:
    included = _included_map(rows)
    assessed = []
    candidates = spec.get("gap_candidates") if isinstance(spec.get("gap_candidates"), list) else []
    for index, gap in enumerate(candidates, 1):
        if not isinstance(gap, dict):
            _add(findings, "tr.gap_shape_invalid", "high", "a gap candidate is not an object", gap=index)
            continue
        gid = _norm(gap.get("gap_id", gap.get("id"))) or f"G{index:02d}"
        gtype = _key(gap.get("type"))
        if gtype not in GAP_TYPES:
            _add(findings, "tr.gap_type_unknown", "high",
                 "gap type must be repeated_unresolved, method_failure or conflicting_evidence",
                 gap_id=gid, type=gtype)
        statement_type = _key(gap.get("statement_type"))
        if statement_type not in STATEMENT_TYPES:
            _add(findings, "tr.fact_inference_unlabelled", "medium",
                 "a gap must distinguish fact, inference and undetermined", owner=gid)
        evidence = _validate_evidence(_as_list(gap.get("evidence")), included, findings, gid)
        record_ids = {x["record_id"] for x in evidence if x["record_id"] in included}
        enough_positive = bool(evidence)
        if gtype == "repeated_unresolved":
            enough_positive = len(record_ids) >= 2
        elif gtype == "conflicting_evidence":
            directions = {_key(x.get("direction", x.get("role"))) for x in evidence}
            enough_positive = len(record_ids) >= 2 and (
                len(directions) >= 2 or {"conflict_a", "conflict_b"} <= directions)
        elif gtype == "method_failure":
            enough_positive = bool(evidence)
            if not _norm(gap.get("failure_scope", gap.get("object", gap.get("scale")))):
                _add(findings, "tr.gap_failure_scope_missing", "high",
                     "a method-failure gap names no object/scale/method boundary", gap_id=gid)
        if not enough_positive:
            _add(findings, "tr.gap_without_positive_evidence", "high",
                 "the gap lacks enough direct, independent positive evidence for its declared type",
                 gap_id=gid, records=sorted(record_ids))
        checks = _as_list(gap.get("exclusion_checks", gap.get("resolution_checks")))
        complete_checks = []
        for pos, check in enumerate(checks, 1):
            if not isinstance(check, dict):
                continue
            absent = [k for k in ("source", "query", "covered_years", "outcome") if check.get(k) in (None, "", [])]
            if absent:
                _add(findings, "tr.gap_exclusion_check_incomplete", "high",
                     "a resolution/exclusion search does not state source, query, years and outcome",
                     gap_id=gid, check=pos, missing=absent)
            else:
                complete_checks.append(check)
        if not complete_checks:
            _add(findings, "tr.gap_without_exclusion_check", "high",
                 "no reproducible resolution/exclusion search accompanies the gap", gap_id=gid)
        if gap.get("counterevidence") and not _norm(gap.get("counterevidence_response")):
            _add(findings, "tr.gap_counterevidence_unresolved", "high",
                 "counterevidence is declared but not answered or used to bound the gap", gap_id=gid)
        supported = (gtype in GAP_TYPES and enough_positive and bool(complete_checks)
                     and statement_type == "inference"
                     and not (gap.get("counterevidence") and not _norm(gap.get("counterevidence_response"))))
        computed_status = "supported_bounded_gap" if supported else "undetermined"
        if _key(gap.get("status")) in ("supported", "confirmed", "supported_bounded_gap") and not supported:
            _add(findings, "tr.unsupported_gap_asserted", "high",
                 "the candidate is asserted as supported although its evidence/exclusion chain is incomplete",
                 gap_id=gid)
        assessed.append({"gap_id": gid, "type": gtype, "candidate": _norm(gap.get("claim", gap.get("text"))),
                         "statement_type": statement_type or "undetermined", "computed_status": computed_status,
                         "evidence": evidence, "exclusion_checks": complete_checks,
                         "counterevidence_response": gap.get("counterevidence_response"),
                         "bounded_conclusion": ((_norm(gap.get("claim", gap.get("text")))
                             + "；仅限已声明文献、年份、对象与解决性检索范围，不主张全局新颖性。")
                             if supported else "证据或排除链不足；保持 undetermined，不把未检索到写成研究空白。"),
                         "uncertainty": [] if supported else ["positive evidence, exclusion checks, counterevidence or type requirements remain incomplete"]})
    return assessed


def validate_interpretations(spec: dict, time: dict, rows: list[dict], findings: list[dict]) -> None:
    annual = {x["year"]: x for x in time.get("annual_counts", [])}
    supported = set(time.get("supported_change_points") or [])
    included = _included_map(rows)
    for index, claim in enumerate(_as_list(spec.get("trend_claims")), 1):
        if not isinstance(claim, dict):
            _add(findings, "tr.trend_claim_shape", "high", "a trend claim is not an object", claim=index)
            continue
        cid = _norm(claim.get("id")) or f"T{index:02d}"
        if _key(claim.get("statement_type")) not in STATEMENT_TYPES:
            _add(findings, "tr.fact_inference_unlabelled", "medium",
                 "a trend claim must be labelled fact, inference or undetermined", owner=cid)
        year = _int(claim.get("year"))
        if year and year not in annual and (claim.get("expected_count") is not None or year in time.get("incomplete_years_excluded", [])):
            _add(findings, "tr.incomplete_or_outside_year_used", "high",
                 "a trend claim uses a year excluded from the complete analysis window", claim=cid, year=year)
        if year in annual and claim.get("expected_count") is not None:
            expected = _number(claim.get("expected_count"))
            if expected is None or expected != annual[year]["count"]:
                _add(findings, "tr.trend_count_mismatch", "high",
                     "a claimed annual count cannot be recomputed from the evidence matrix",
                     claim=cid, year=year, expected=claim.get("expected_count"), actual=annual[year]["count"])
        cp = _int(claim.get("change_point_year"))
        if cp and _key(claim.get("significance")) in ("confirmed", "supported", "significant") and cp not in supported:
            _add(findings, "tr.changepoint_overclaimed", "high",
                 "a claimed turning point did not survive the declared permutation/multiplicity test",
                 claim=cid, year=cp)
        text = _norm(claim.get("text", claim.get("claim")))
        if re.search(r"\b(?:causes?|because of|leads? to|drives?)\b|导致|因为|驱动", text, re.I):
            _add(findings, "tr.causal_overreach", "high",
                 "an observational trend claim uses causal language", claim=cid)
        evidence = claim.get("evidence")
        if not evidence:
            _add(findings, "tr.trend_claim_unlinked", "high",
                 "a trend interpretation has no annual-cell or exact-source evidence link", claim=cid)
        else:
            for ref in _as_list(evidence):
                if isinstance(ref, dict):
                    _validate_evidence([ref], included, findings, cid)
                    continue
                ref_text = _norm(ref)
                match = re.fullmatch(r"annual_counts\.csv#year=(\d{4})", ref_text)
                matrix_ref = re.fullmatch(r"evidence_matrix\.csv#([A-Za-z0-9_:\-]+)", ref_text)
                valid = (bool(match) and int(match.group(1)) in annual) or (
                    bool(matrix_ref) and matrix_ref.group(1) in included)
                if not valid:
                    _add(findings, "tr.trend_claim_unlinked", "high",
                         "a trend evidence reference does not resolve to a computed annual cell or included record",
                         claim=cid, evidence=ref_text)


def validate_events(spec: dict, rows: list[dict], protocol: dict, findings: list[dict]) -> list[dict]:
    included = _included_map(rows)
    events = []
    start, end = _int(protocol.get("start_year")), _int(protocol.get("end_year"))
    for index, event in enumerate(_as_list(spec.get("evolution_events")), 1):
        if not isinstance(event, dict):
            _add(findings, "tr.event_shape_invalid", "high", "an evolution event is not an object", event=index)
            continue
        eid = _norm(event.get("event_id", event.get("id"))) or f"E{index:02d}"
        etype = _key(event.get("type", event.get("event_type")))
        year = _int(event.get("year", event.get("start_year")))
        topics = [_norm(x) for x in _as_list(event.get("topics", event.get("topic")))]
        if etype not in EVENT_TYPES:
            _add(findings, "tr.event_type_unknown", "high", "unknown evolution event type", event_id=eid)
        if etype in ("merge", "split") and len(topics) < 2:
            _add(findings, "tr.event_topics_incomplete", "high",
                 "merge/split requires at least two explicitly named topics", event_id=eid)
        if year is None or (start and end and not start <= year <= end):
            _add(findings, "tr.event_year_invalid", "high",
                 "an evolution event lacks a year inside the protocol window", event_id=eid, year=year)
        if not _norm(event.get("basis", event.get("rationale"))):
            _add(findings, "tr.event_basis_missing", "high",
                 "an evolution event does not say what changed or on what relation/terminology evidence",
                 event_id=eid)
        if _key(event.get("statement_type")) not in STATEMENT_TYPES:
            _add(findings, "tr.fact_inference_unlabelled", "medium",
                 "an evolution event must be labelled fact, inference or undetermined", owner=eid)
        evidence = _validate_evidence(_as_list(event.get("evidence")), included, findings, eid)
        if not evidence:
            _add(findings, "tr.evolution_event_unsupported", "high",
                 "an evolution event has no exact-source evidence", event_id=eid)
        events.append({"event_id": eid, "type": etype, "year": year, "topics": topics,
                       "basis": event.get("basis", event.get("rationale")), "evidence": evidence,
                       "statement_type": event.get("statement_type", "undetermined"),
                       "scope": "evolution within the included corpus; no unobserved causal mechanism inferred"})
    return events


def analyze(spec: dict, spec_dir: str | Path = ".") -> dict:
    findings: list[dict] = []
    rows, protocol, uncertainty = prepare_records(spec, Path(spec_dir), findings)
    matrix = evidence_matrix(rows)
    time = compute_time(rows, protocol, spec)
    topics = compute_topics(rows, protocol, spec, findings)
    custom_phases = spec.get("phases") if isinstance(spec.get("phases"), list) else []
    phases = time.get("phases") or []
    if custom_phases:
        phases = []
        for index, phase in enumerate(custom_phases, 1):
            if not isinstance(phase, dict):
                continue
            pid = _norm(phase.get("phase_id", phase.get("id"))) or f"phase_{index}"
            a, b = _int(phase.get("start_year")), _int(phase.get("end_year"))
            if a is None or b is None or b < a:
                _add(findings, "tr.phase_window_invalid", "high", "a phase window is invalid", phase_id=pid)
                continue
            if not _norm(phase.get("basis", phase.get("rationale"))):
                _add(findings, "tr.phase_basis_missing", "medium",
                     "a custom phase lacks a quantitative/source basis", phase_id=pid)
            phases.append({"phase_id": pid, "start_year": a, "end_year": b,
                           "basis": phase.get("basis", phase.get("rationale")),
                           "statement_type": phase.get("statement_type", "inference"),
                           "evidence": phase.get("evidence") or []})
    representatives = select_representatives(rows, phases, spec, findings)
    gaps = assess_gaps(rows, spec, protocol, findings)
    events = validate_events(spec, rows, protocol, findings)
    validate_interpretations(spec, time, rows, findings)
    included = _included_map(rows)
    for r in included.values():
        locators = [_norm(x.get("locator")) for x in _as_list(r.get("excerpts"))
                    if isinstance(x, dict) and _norm(x.get("locator"))]
        if not locators and not _norm(r.get("locator")):
            _add(findings, "tr.record_locator_missing", "high",
                 "an included record has no source locator for evidence return", record_id=r["record_id"])
    for item in uncertainty:
        item["scope"] = "time trend only; record remains visible in evidence matrix"
    for value in _as_list(spec.get("uncertainty")):
        uncertainty.append({"kind": "declared", "message": _norm(value)})
    uncertainty.append({"kind": "boundary", "message": "fixed-corpus results do not establish global novelty, completeness or causality"})
    if not gaps:
        uncertainty.append({"kind": "research_gap", "message": "no supported bounded gap was produced; this is not evidence that no gap exists"})
    counts = Counter(f["severity"] for f in findings)
    status = "blocked" if counts.get("high") else ("review" if findings else "clean")
    sources = [{"record_id": r["record_id"], "title": _norm(r.get("title")), "doi": r.get("doi_normalized"),
                "year": r.get("year_used"), "year_basis": r.get("year_basis"),
                "source_file": _norm(r.get("source_file", r.get("source"))) or "not_reported",
                "locators": [_norm(x.get("locator")) for x in _as_list(r.get("excerpts"))
                             if isinstance(x, dict) and _norm(x.get("locator"))]
                             or ([_norm(r.get("locator"))] if _norm(r.get("locator")) else [])}
               for r in rows if r.get("included_in_corpus")]
    topic_evolution = {**topics, "events": events, "phases": phases,
                       "generated_interpretations": topics.get("topic_summaries", [])}
    return {"schema_version": SCHEMA, "status": status, "findings": findings,
            "severity_counts": dict(counts), "research_question": spec.get("research_question", spec.get("question")),
            "search_protocol": protocol,
            "screening_protocol": spec.get("screening_protocol") or {},
            "screening": {"identified": len(rows),
                          "included": sum(r["included_in_corpus"] for r in rows),
                          "excluded": sum(r["screening_decision_normalized"] == "exclude" for r in rows),
                          "undetermined": sum(r["screening_decision_normalized"] == "undetermined" for r in rows),
                          "duplicates": sum(bool(r.get("duplicate_of")) for r in rows),
                          "time_counted": sum(r["included_in_trends"] for r in rows)},
            "evidence_matrix": matrix, "time_trend": time, "topic_evolution": topic_evolution,
            "representative_works": representatives, "research_gaps": gaps,
            "sources": sources, "uncertainty": uncertainty,
            "checked": {"input_records": len(rows), "evidence_rows": len(matrix),
                        "annual_cells": len(time.get("annual_counts", [])),
                        "topic_year_cells": len(topics.get("topic_year_matrix", [])),
                        "phases": len(phases), "representatives": len(representatives),
                        "gap_candidates": len(gaps),
                        "rule": "all tables recomputed from normalized records; no external facts added"},
            "limits": list(time.get("limits") or []) + [
                "automated relevance screening runs only when screening_protocol auto_apply is true",
                "representative and gap verdicts are bounded inferences, not global priority/novelty certificates"],
            "change_records": spec.get("change_records", spec.get("changes", []))}
