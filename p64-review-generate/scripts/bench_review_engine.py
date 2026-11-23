"""Regression battery for thematic evidence synthesis (synthetic records only)."""
from __future__ import annotations

import copy
import importlib.util
import json
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import review_engine as E  # noqa: E402

ROOT = HERE.parent
BASE = json.loads((ROOT / "examples" / "review-spec.json").read_text(encoding="utf-8"))
CASE = json.loads((ROOT / "examples" / "case.json").read_text(encoding="utf-8"))
CLI = HERE / "reviewrun.py"
NAMES = ["research_product", "screening", "themes", "comparison_matrix", "synthesis_claims",
         "research_gaps", "evidence_matrix", "citation_coverage", "uncertainties",
         "change_records", "deliverables"]


def spec():
    return copy.deepcopy(BASE)


def run_cli(tmp: Path, data=None, case=CASE, raw_spec=None):
    tmp.mkdir(parents=True, exist_ok=True)
    source = tmp / "spec.json"
    source.write_text(raw_spec if raw_spec is not None else json.dumps(data or spec(), ensure_ascii=False), encoding="utf-8")
    case_file = tmp / "case.json"
    if case is not None:
        case_file.write_text(json.dumps(case, ensure_ascii=False), encoding="utf-8")
    out = tmp / "out"
    args = [sys.executable, "-B", "-I", "-X", "utf8", str(CLI), "--spec", str(source), "--out", str(out)]
    if case is not None:
        args += ["--case", str(case_file)]
    proc = subprocess.run(args, capture_output=True, text=True, timeout=60)
    path = out / "result.json"
    result = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    return proc, result, out


def has_rule(result, rule):
    return rule in {row.get("rule") for row in result.get("findings", [])}


def clean(tmp, name):
    r = E.analyze(spec())
    return (r["status"] == "clean" and not r["findings"] and r["citation_coverage"]["record_coverage_ratio"] == 1
            and r["screening"]["identified_input_rows"] == 6 and r["screening"]["duplicates"] == 1
            and r["conflict_candidates"][0]["status"] == "addressed_two_sided")


def artifacts_contract(tmp, name):
    p, r, out = run_cli(tmp)
    expected = {"review_draft.md", "evidence_matrix.csv", "theme_comparison.csv", "screening_log.csv",
                "citation_coverage.csv", "result.json"}
    draft = (out / "review_draft.md").read_text(encoding="utf-8")
    return (p.returncode == 0 and expected == {x.name for x in out.iterdir()}
            and r["output_contract_fields"] == NAMES and all(r.get(k) is not None for k in NAMES)
            and r["case_id"] == CASE["case_id"] and r["output_contract"] == CASE["output_contract"]
            and len(r["artifacts"]) == 5 and "支持证据：R1 [R1:R]" in draft)


def duplicate_and_screening_counts(tmp, name):
    r = E.analyze(spec())
    return (r["screening"] == {**r["screening"], "identified_input_rows": 6,
            "malformed_rows": 0, "duplicates": 1, "screened_unique_records": 5,
            "included": 4, "excluded": 1, "undetermined": 0}
            and r["screening"]["duplicate_rows"][0]["duplicate_of"] == "R1"
            and r["citation_coverage"]["included_records"] == 4)


def excluded_evidence_citation(tmp, name):
    data = spec()
    excluded = next(row for row in data["records"] if row["id"] == "X1")
    excluded["evidence"] = [{"id": "X1:E", "quote": "Postoperative pain was measured.", "locator": "synthetic-X abstract"}]
    data["synthesis_claims"].append({"id": "CBAD", "type": "consensus", "theme_id": "T1",
        "comparison_key": "exercise_vs_care_pain_12w", "statement": "错误引用排除研究",
        "support_evidence_refs": ["X1:E"], "contradicting_evidence_refs": []})
    r = E.analyze(data)
    return has_rule(r, "review.excluded_evidence_cited") and r["status"] == "blocked"


def quote_tamper(tmp, name):
    data = spec(); data["records"][0]["evidence"][0]["quote"] = "fabricated quote"
    r = E.analyze(data)
    return has_rule(r, "review.quote_not_in_source")


def theme_rationale_required(tmp, name):
    data = spec(); data["records"][0]["theme_assignments"][0]["rationale"] = ""
    r = E.analyze(data)
    return has_rule(r, "review.theme_rationale_missing")


def record_unclustered(tmp, name):
    data = spec(); data["records"][2]["theme_assignments"] = []
    r = E.analyze(data)
    return has_rule(r, "review.record_unclustered")


def conflict_unaddressed(tmp, name):
    data = spec(); data["synthesis_claims"] = [row for row in data["synthesis_claims"] if row["id"] != "C1"]
    r = E.analyze(data)
    return (r["conflict_candidates"][0]["status"] == "unaddressed_conflict"
            and has_rule(r, "review.conflict_unaddressed") and has_rule(r, "review.record_not_synthesized"))


def claim_omits_conflict(tmp, name):
    data = spec()
    claim = data["synthesis_claims"][0]
    claim["type"] = "consensus"; claim["contradicting_evidence_refs"] = []
    r = E.analyze(data)
    out = next(row for row in r["synthesis_claims"] if row["claim_id"] == "C1")
    return (has_rule(r, "review.claim_omits_conflict") and out["computed_strength"] == "contested"
            and out["omitted_conflicting_records"] == ["R2"])


def consensus_single_source(tmp, name):
    data = spec(); data["synthesis_claims"][1]["support_evidence_refs"] = ["R3:R"]
    r = E.analyze(data)
    claim = next(row for row in r["synthesis_claims"] if row["claim_id"] == "C2")
    return has_rule(r, "review.consensus_single_source") and claim["computed_strength"] == "suggestive"


def abstract_strength_downgrade(tmp, name):
    data = spec(); data["records"][3]["full_text_status"] = "abstract_only"
    r = E.analyze(data)
    return (next(row for row in r["synthesis_claims"] if row["claim_id"] == "C2")["computed_strength"] == "suggestive"
            and any(row["kind"] == "limited_text" for row in r["uncertainties"]))


def gap_needs_positive_evidence(tmp, name):
    data = spec(); data["research_gaps"][0]["positive_evidence_refs"] = []
    r = E.analyze(data)
    return (has_rule(r, "review.gap_positive_evidence_missing")
            and r["research_gaps"][0]["computed_status"] == "undetermined")


def gap_needs_scope_check(tmp, name):
    data = spec(); data["research_gaps"][0]["scope_checks"] = []
    r = E.analyze(data)
    return (has_rule(r, "review.gap_scope_missing")
            and r["research_gaps"][0]["computed_status"] == "candidate_only_scope_check_missing")


def criteria_frozen(tmp, name):
    data = spec(); data["screening_protocol"]["frozen_before_review"] = False
    r = E.analyze(data)
    return has_rule(r, "review.criteria_not_frozen") and r["status"] == "blocked"


def malformed_arithmetic(tmp, name):
    data = spec(); data["records"] += [None, "bad"]
    r = E.analyze(data)
    s = r["screening"]
    return (s["identified_input_rows"] == 8 and s["malformed_rows"] == 2
            and s["identified_input_rows"] == s["malformed_rows"] + s["duplicates"] + s["screened_unique_records"])


def undetermined_not_silently_included(tmp, name):
    data = spec(); data["records"][3]["decision"] = "undetermined"
    r = E.analyze(data)
    return (r["screening"]["undetermined"] == 1 and r["screening"]["included"] == 3
            and has_rule(r, "review.excluded_evidence_cited"))


def cross_record_field_reference(tmp, name):
    data = spec(); data["records"][0]["field_evidence"]["method"] = ["R2:M"]
    r = E.analyze(data)
    return has_rule(r, "review.field_evidence_cross_record")


def missing_source_locator(tmp, name):
    data = spec(); data["corpus"]["sources"][0]["locator"] = ""
    r = E.analyze(data)
    return has_rule(r, "review.source_locator_missing")


def refusal_contract(tmp, name):
    p, r, _ = run_cli(tmp, raw_spec="{bad")
    return (p.returncode == 5 and r["status"] == "undetermined" and r["case_id"] == CASE["case_id"]
            and r["output_contract_fields"] == NAMES and all(k in r for k in NAMES)
            and "Traceback" not in p.stderr)


def idempotent_bytes(tmp, name):
    p1, _, out = run_cli(tmp)
    one = {x.name: x.read_bytes() for x in out.iterdir() if x.is_file()}
    p2 = subprocess.run([sys.executable, "-B", "-I", "-X", "utf8", str(CLI),
        "--spec", str(tmp / "spec.json"), "--case", str(tmp / "case.json"), "--out", str(out)],
        capture_output=True, text=True, timeout=60)
    two = {x.name: x.read_bytes() for x in out.iterdir() if x.is_file()}
    return p1.returncode == p2.returncode == 0 and one == two


def cold_import(tmp, name):
    module_path = HERE / "review_engine.py"
    loaded = importlib.util.spec_from_file_location("cold_review_engine", module_path)
    module = importlib.util.module_from_spec(loaded); loaded.loader.exec_module(module)
    r = module.analyze(spec())
    return r["status"] == "clean" and r["checked"]["included_records"] == 4


SCENARIOS = [
    ("clean_baseline", clean), ("artifacts_and_contract", artifacts_contract),
    ("duplicate_and_screening_counts", duplicate_and_screening_counts),
    ("excluded_evidence_citation", excluded_evidence_citation), ("quote_tamper", quote_tamper),
    ("theme_rationale_required", theme_rationale_required), ("record_unclustered", record_unclustered),
    ("conflict_unaddressed", conflict_unaddressed), ("claim_omits_conflict", claim_omits_conflict),
    ("consensus_single_source", consensus_single_source), ("abstract_strength_downgrade", abstract_strength_downgrade),
    ("gap_needs_positive_evidence", gap_needs_positive_evidence), ("gap_needs_scope_check", gap_needs_scope_check),
    ("criteria_frozen", criteria_frozen), ("malformed_arithmetic", malformed_arithmetic),
    ("undetermined_not_silently_included", undetermined_not_silently_included),
    ("cross_record_field_reference", cross_record_field_reference),
    ("missing_source_locator", missing_source_locator), ("refusal_contract", refusal_contract),
    ("idempotent_bytes", idempotent_bytes), ("cold_import", cold_import),
]


def main():
    rows = []
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        for pos, (name, fn) in enumerate(SCENARIOS):
            try:
                ok, why = bool(fn(root / f"{pos:02d}_{name}", name)), ""
            except Exception as exc:
                ok, why = False, f"raised {type(exc).__name__}: {exc}"
            rows.append({"scenario": name, "pass": ok, "why": why})
            print(("PASS" if ok else "FAIL") + f"  {name:<36}" + why)
    passed = sum(row["pass"] for row in rows)
    report = {"schema_version": "review-engine-bench/v2", "synthetic_only": True,
              "scenarios": rows, "totals": {"passed": passed, "of": len(rows)}}
    (HERE / "report_review_engine.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n{passed}/{len(rows)} scenarios pass")
    return 0 if passed == len(rows) else 1


if __name__ == "__main__":
    raise SystemExit(main())
