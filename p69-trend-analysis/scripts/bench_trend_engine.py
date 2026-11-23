"""Rule-by-rule and false-positive benchmark for the actual p69 trend engine."""
from __future__ import annotations

import copy
import csv
import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import trend_engine as E

PKG = Path(__file__).resolve().parent.parent
FIXTURE = json.loads((PKG / "examples/spec-trend.json").read_text(encoding="utf-8"))


def d():
    return copy.deepcopy(FIXTURE)


def run(spec):
    return E.analyze(spec, PKG / "examples")


def defects():
    s = d(); s["research_question"] = ""
    yield "research_question_missing", s, ["tr.research_question_missing"]
    s = d(); s.pop("search_protocol")
    yield "protocol_missing", s, ["tr.protocol_missing"]
    s = d(); s["search_protocol"].pop("sources")
    yield "protocol_field_missing", s, ["tr.protocol_field_missing"]
    s = d(); s["search_protocol"]["start_year"] = 2024; s["search_protocol"]["end_year"] = 2018
    yield "protocol_window_invalid", s, ["tr.protocol_window_invalid"]
    s = d(); s["search_protocol"]["year_basis"] = "remembered_date"
    yield "year_basis_unknown", s, ["tr.year_basis_unknown"]
    s = d(); s["records"] = []
    yield "no_records", s, ["tr.no_records"]
    s = d()
    for r in s["records"]:
        if r["id"] != "R010":
            r["decision"] = "exclude"; r["reason"] = "targeted exclusion"; r["reason_code"] = "off_topic"
    yield "no_included_records", s, ["tr.no_included_records"]
    s = d(); s["records"][0].pop("decision")
    yield "screening_decision_missing", s, ["tr.screening_decision_missing"]
    s = d(); s["records"][-1].pop("reason"); s["records"][-1].pop("reason_code")
    yield "exclusion_reason_missing", s, ["tr.exclusion_reason_missing"]
    s = d(); duplicate = copy.deepcopy(s["records"][2]); duplicate["id"] = "R011"; s["records"].append(duplicate)
    yield "duplicate_version", s, ["tr.duplicate_version"]
    s = d(); duplicate = copy.deepcopy(s["records"][1]); duplicate["id"] = "R001"; s["records"].append(duplicate)
    yield "record_id_duplicate", s, ["tr.record_id_duplicate"]
    s = d(); s["records"][0].pop("year")
    yield "year_missing", s, ["tr.year_missing"]
    s = d(); s["search_protocol"]["complete_through"] = 2020
    yield "incomplete_year_used", s, ["tr.incomplete_or_outside_year_used"]
    s = d(); s["trend_claims"][0]["expected_count"] = 3
    yield "trend_count_mismatch", s, ["tr.trend_count_mismatch"]
    s = d(); s["trend_claims"][0].update({"change_point_year": 2022, "significance": "confirmed"})
    yield "changepoint_overclaimed", s, ["tr.changepoint_overclaimed"]
    s = d(); s["trend_claims"][0]["text"] = "GNN 导致 2021 年主题合并。"
    yield "causal_overreach", s, ["tr.causal_overreach"]
    s = d(); s["trend_claims"][0]["evidence"] = []
    yield "trend_claim_unlinked", s, ["tr.trend_claim_unlinked"]
    s = d(); s["trend_claims"][0]["evidence"] = ["annual_counts.csv#year=1999"]
    yield "trend_claim_dangling_link", s, ["tr.trend_claim_unlinked"]
    s = d(); s["trend_claims"].append("increase")
    yield "trend_claim_shape", s, ["tr.trend_claim_shape"]
    s = d(); s["trend_claims"][0].pop("statement_type")
    yield "fact_inference_unlabelled", s, ["tr.fact_inference_unlabelled"]
    s = d(); s["records"][0].update({"title": "Baseline uptake", "topics": []})
    s["records"][0]["excerpts"] = [{"text": "A baseline was established for uptake measurements.", "locator": "p.2"}]
    yield "topic_unassigned", s, ["tr.topic_unassigned"]
    s = d(); s["ambiguous_terms"].append({"term": "GNN", "topic_by_context": {}})
    yield "topic_ambiguity_unresolved", s, ["tr.topic_ambiguity_unresolved"]
    s = d(); s["evolution_events"][0].pop("basis")
    yield "event_basis_missing", s, ["tr.event_basis_missing"]
    s = d(); s["evolution_events"] = ["merge"]
    yield "event_shape_invalid", s, ["tr.event_shape_invalid"]
    s = d(); s["evolution_events"][0]["topics"] = ["GNN"]
    yield "event_topics_incomplete", s, ["tr.event_topics_incomplete"]
    s = d(); s["evolution_events"][0]["type"] = "explosion"
    yield "event_type_unknown", s, ["tr.event_type_unknown"]
    s = d(); s["evolution_events"][0]["year"] = 2030
    yield "event_year_invalid", s, ["tr.event_year_invalid"]
    s = d(); s["evolution_events"][0]["evidence"][0]["record_id"] = "UNKNOWN"
    yield "evidence_unknown_record", s, ["tr.evidence_unknown_record"]
    s = d(); s["evolution_events"][0]["evidence"][0]["quote"] = "invented quotation"
    yield "evidence_quote_mismatch", s, ["tr.evidence_quote_mismatch"]
    s = d(); s["evolution_events"][0]["evidence"][0]["quote"] = ""
    yield "evidence_quote_missing", s, ["tr.evidence_quote_missing"]
    s = d(); s["evolution_events"][0]["evidence"][0].pop("locator")
    yield "evidence_locator_missing", s, ["tr.evidence_locator_missing"]
    s = d(); s["evolution_events"][0]["evidence"][0]["locator"] = "somewhere in paper"
    yield "evidence_locator_vague", s, ["tr.evidence_locator_vague"]
    s = d(); s["evolution_events"][0]["evidence"] = ["not-an-object", s["evolution_events"][0]["evidence"][1]]
    yield "evidence_shape_invalid", s, ["tr.evidence_shape_invalid"]
    s = d(); s["evolution_events"][0]["evidence"] = []
    yield "evolution_event_unsupported", s, ["tr.evolution_event_unsupported"]
    s = d(); s["gap_candidates"] = ["not-an-object"]
    yield "gap_shape_invalid", s, ["tr.gap_shape_invalid"]
    s = d(); s["gap_candidates"][0]["type"] = "unknown"
    yield "gap_type_unknown", s, ["tr.gap_type_unknown"]
    s = d(); s["gap_candidates"][0]["evidence"] = s["gap_candidates"][0]["evidence"][:1]
    yield "gap_without_positive_evidence", s, ["tr.gap_without_positive_evidence"]
    s = d(); s["gap_candidates"][0]["exclusion_checks"] = []
    yield "gap_without_exclusion_check", s, ["tr.gap_without_exclusion_check"]
    s = d(); s["gap_candidates"][0]["exclusion_checks"][0].pop("query")
    yield "gap_exclusion_check_incomplete", s, ["tr.gap_exclusion_check_incomplete"]
    s = d(); s["gap_candidates"][0]["type"] = "method_failure"
    yield "gap_failure_scope_missing", s, ["tr.gap_failure_scope_missing"]
    s = d(); s["gap_candidates"][0]["counterevidence"] = [{"record_id": "R006", "quote": "within-scale validation"}]
    yield "gap_counterevidence_unresolved", s, ["tr.gap_counterevidence_unresolved"]
    s = d(); s["gap_candidates"][0]["statement_type"] = "fact"
    yield "unsupported_gap_asserted", s, ["tr.unsupported_gap_asserted"]
    s = d(); s["representative_config"]["selection_method"] = "citations_only"
    yield "citation_only_selection", s, ["tr.citation_only_selection"]
    s = d(); s["records"][0]["citation_count"] = "many"
    yield "citation_count_invalid", s, ["tr.citation_count_invalid"]
    s = d(); s["phases"] = [BASE_PHASE, EMPTY_PHASE]
    yield "representative_phase_missing", s, ["tr.representative_phase_missing"]
    s = d(); s["representative_config"]["per_phase"] = 0
    yield "representative_quota_invalid", s, ["tr.representative_quota_invalid"]
    s = d(); s["phases"] = [{"id": "P1", "start_year": 2018, "end_year": 2024}]
    yield "phase_basis_missing", s, ["tr.phase_basis_missing"]
    s = d(); s["phases"] = [{"id": "P1", "start_year": 2024, "end_year": 2018, "basis": "test"}]
    yield "phase_window_invalid", s, ["tr.phase_window_invalid"]
    s = d(); s["records"][0].pop("locator"); s["records"][0]["excerpts"] = []
    yield "record_locator_missing", s, ["tr.record_locator_missing"]


BASE_PHASE = {"id": "P1", "start_year": 2018, "end_year": 2024,
              "basis": "declared complete window", "evidence": ["annual_counts.csv#year=2018"]}
EMPTY_PHASE = {"id": "P2", "start_year": 2025, "end_year": 2025,
               "basis": "future phase with no included records", "evidence": []}


def semantic_guards():
    result = run(d())
    checks = []
    checks.append(("clean_baseline", not result["findings"]))
    canonical = {x["topic"] for x in result["topic_evolution"]["topic_year_matrix"]}
    checks.append(("aliases_not_extra_zero_topics", "GNN" not in canonical and "graph neural network" not in canonical
                   and "graph transformer" not in canonical))
    checks.append(("excluded_topic_not_counted", "clinical dosing" not in canonical))
    checks.append(("date_basis_not_imputed", [x["year_basis"] for x in result["time_trend"]["year_basis_sensitivity"]] == ["online"]))
    annual = {x["year"]: x for x in result["time_trend"]["annual_counts"]}
    checks.append(("zero_baseline_growth_null", annual[2024]["growth_rate"] is None and annual[2023]["growth_rate"] == -1.0))
    reps = result["representative_works"]
    checks.append(("long_tail_method_first", any(x["record_id"] == "R003" for x in reps)
                   and all(x["record_id"] != "R004" for x in reps)))
    checks.append(("all_phases_covered", {x["phase_id"] for x in reps} == {"observed_window"}))
    checks.append(("gap_is_bounded", result["research_gaps"][0]["computed_status"] == "supported_bounded_gap"
                   and "不主张全局新颖性" in result["research_gaps"][0]["bounded_conclusion"]))
    shares = [x for x in result["topic_evolution"]["topic_year_matrix"]
              if x["topic"] == "graph neural networks" and x["year"] == 2020]
    checks.append(("multi_label_denominator", shares[0]["count"] == 2 and shares[0]["share"] == 1.0))
    checks.append(("no_forced_turning_point", result["time_trend"]["supported_change_points"] == []))
    # Direct statistical oracles: a real strong discontinuity can pass, while a flat
    # series cannot make the detector manufacture a turning point.
    strong = E._change_points([{"year": 2010 + i, "count": c} for i, c in enumerate(
        [1, 1, 1, 1, 2, 2, 15, 16, 17, 18, 19, 20])], 2, 0.05)
    flat = E._change_points([{"year": 2010 + i, "count": 3} for i in range(12)], 2, 0.05)
    checks.append(("strong_change_point_detectable", any(x["supported"] for x in strong)))
    checks.append(("flat_series_no_change_point", not any(x["supported"] for x in flat)))
    phased = d()
    phased["phases"] = [
        {"id": "early", "start_year": 2018, "end_year": 2020, "basis": "fixed first three years"},
        {"id": "late", "start_year": 2021, "end_year": 2024, "basis": "fixed later years"},
    ]
    phased_result = run(phased)
    checks.append(("multiple_phases_covered", not phased_result["findings"]
                   and {x["phase_id"] for x in phased_result["representative_works"]} == {"early", "late"}))
    conflict = d()
    conflict["records"][4]["excerpts"].append({"text": "Cross-scale transfer was reliable.", "locator": "Sec. 3, p.5"})
    conflict["records"][5]["excerpts"].append({"text": "Cross-scale transfer was not reliable.", "locator": "Sec. 3, p.5"})
    conflict["gap_candidates"].append({
        "id": "G2", "type": "conflicting_evidence", "statement_type": "inference", "status": "supported",
        "claim": "跨尺度迁移可靠性存在冲突证据",
        "evidence": [
            {"record_id": "R005", "quote": "Cross-scale transfer was reliable.", "locator": "Sec. 3, p.5", "direction": "supports"},
            {"record_id": "R006", "quote": "Cross-scale transfer was not reliable.", "locator": "Sec. 3, p.5", "direction": "refutes"},
        ],
        "exclusion_checks": [{"source": "synthetic-fixed-index", "query": "cross-scale reliability review",
                              "covered_years": [2018, 2024], "outcome": "conflict_not_resolved"}],
    })
    conflict_result = run(conflict)
    checks.append(("conflict_gap_supported", not conflict_result["findings"]
                   and conflict_result["research_gaps"][1]["computed_status"] == "supported_bounded_gap"))
    checks.append(("deterministic_analysis", run(d()) == result))
    return checks


def input_guards():
    checks = []
    root = Path(tempfile.mkdtemp(prefix="p69_record_inputs_"))
    spec = d(); records = spec.pop("records")
    json_path = root / "records.json"
    json_path.write_text(json.dumps(records, ensure_ascii=False), encoding="utf-8")
    spec["records_path"] = str(json_path)
    checks.append(("json_records_path_clean", not run(spec)["findings"]))
    jsonl_path = root / "records.jsonl"
    jsonl_path.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in records), encoding="utf-8")
    spec = d(); spec.pop("records"); spec["records_path"] = str(jsonl_path)
    checks.append(("jsonl_records_path_clean", not run(spec)["findings"]))

    # CSV carries JSON in the excerpts column, not pre-parsed answers.
    csv_path = root / "records.csv"
    fields = sorted({k for r in records for k in r})
    with csv_path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields)
        writer.writeheader()
        for r in records:
            writer.writerow({k: json.dumps(v, ensure_ascii=False) if isinstance(v, (list, dict)) else v
                             for k, v in r.items()})
    spec = d(); spec.pop("records"); spec["records_path"] = str(csv_path)
    result = run(spec)
    checks.append(("csv_records_path_clean", not result["findings"]))

    # Prospective protocol can be executed deterministically; without auto_apply it may not guess.
    spec = d()
    spec["screening_protocol"] = {"auto_apply": True, "must_match_any": ["coating", "GNN", "graph"],
                                  "exclude_terms": ["clinical dosing"]}
    for record in spec["records"]:
        record.pop("decision", None); record.pop("reason", None); record.pop("reason_code", None)
    result = run(spec)
    checks.append(("prospective_auto_screening_clean", not result["findings"]
                   and result["screening"]["excluded"] == 1 and result["screening"]["included"] == 9))
    return checks


def direct_unit_guards():
    findings = []
    got = E._validate_evidence([{"record_id": "X", "quote": "unresolved", "locator": "p.1"}],
                               {"X": {"record_id": "X"}}, findings, "unit")
    return [("evidence_source_text_missing", not got
             and any(x["rule"] == "tr.evidence_source_text_missing" for x in findings))]


def main():
    rows = []
    for name, spec, expected in defects():
        result = run(spec)
        fired = {x["rule"] for x in result["findings"]}
        missing = [x for x in expected if x not in fired]
        rows.append({"scenario": name, "expected": expected, "fired": sorted(fired),
                     "missing": missing, "pass": not missing})
        print(f"{'PASS' if not missing else 'FAIL'}  {name:<38} missing={missing}")
    for name, ok in semantic_guards() + input_guards() + direct_unit_guards():
        rows.append({"scenario": name, "expected": [], "pass": ok})
        print(f"{'PASS' if ok else 'FAIL'}  {name:<38} guard={ok}")
    passed = sum(x["pass"] for x in rows)
    report = {"schema_version": "trend-engine-bench/v2", "scenarios": rows,
              "totals": {"passed": passed, "of": len(rows)},
              "note": "All tr.* rules plus clean/determinism/input/semantic guards. No platform score is implied."}
    (Path(__file__).resolve().parent / "report_trend_engine.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n{passed}/{len(rows)} scenarios pass")
    return 0 if passed == len(rows) else 1


if __name__ == "__main__":
    raise SystemExit(main())
