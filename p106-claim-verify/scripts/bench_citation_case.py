"""Functional bench for the full-text citation engine; clean baseline must be silent."""
from __future__ import annotations

import copy
import json
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import citecheck as E

EXAMPLE = Path(__file__).resolve().parents[1] / "examples" / "case.json"
RESULTS = []


def base():
    return json.loads(EXAMPLE.read_text(encoding="utf-8"))


def run(case):
    with tempfile.TemporaryDirectory(prefix="cite-bench-") as tmp:
        root = Path(tmp)
        path = root / "case.json"
        path.write_text(json.dumps(case, ensure_ascii=False), encoding="utf-8")
        return E.run(path, root / "out")


def record(name, condition, detail=""):
    RESULTS.append({"scenario": name, "passed": bool(condition), "detail": detail})
    if not condition:
        print("FAIL", name, detail)


def rules(result):
    return {f.get("rule") for f in result.get("findings", [])}


def main():
    clean = run(base())
    record("clean_full_text_zero_findings", clean["status"] == "clean" and not clean["findings"] and not clean["uncertainty"], clean)
    record("clean_direct_support", clean["citation_checks"][0]["support_verdict"] == "supports")
    record("clean_metadata_independent", clean["metadata_checks"][0]["overall"] == "match" and clean["citation_checks"][0]["fact_verified"] is False)
    record("contract_and_case_identity", clean["case_id"] == "cite-smoke-clean" and clean["status"] != "case-must-not-override-engine" and clean["custom_missing"] is None)

    case = base()
    case["sources"][0]["title"] = "A different title"
    case["sources"][0]["year"] = 2022
    case["sources"][0]["authors"] = [{"family": "Someone"}]
    result = run(case)
    record("doi_title_author_year_mismatch", "cite.metadata_mismatch" in rules(result) and set(result["metadata_checks"][0]["mismatches"]) == {"title", "author", "year"}, result["metadata_checks"])
    record("metadata_mismatch_does_not_rewrite_support", result["citation_checks"][0]["support_verdict"] == "supports")

    case = base()
    case["sources"] = [{"key": "1", "doi": "10.1234/example.1", "title": "Porous coatings increase uptake", "authors": [{"family": "Doe"}, {"family": "Roe"}], "year": 2020}]
    result = run(case)
    record("metadata_only_cannot_verify_claim", result["metadata_checks"][0]["overall"] == "match" and result["citation_checks"][0]["support_verdict"] == "undetermined" and result["uncertainty"])

    case = base()
    case["sources"][0]["text"] = "2 Results\nSolvent polarity changed the crystallisation temperature in another experiment.\n"
    result = run(case)
    record("unrelated_source_not_supported", result["citation_checks"][0]["support_verdict"] == "not_supported" and "cite.claim_not_supported" in rules(result), result["citation_checks"])

    case = base()
    case["sources"][0]["text"] = case["sources"][0]["text"].replace("three-fold", "two-fold")
    result = run(case)
    record("numeric_scope_partial_support", result["citation_checks"][0]["support_verdict"] == "partial" and result["citation_checks"][0]["alignment"]["missing_numbers"] == ["3"])

    case = base()
    case["manuscript_text"] = case["manuscript_text"].replace("increased uptake three-fold [1]", "caused uptake three-fold [1]")
    case["sources"][0]["text"] = "2 Results\nThe porous coating was associated with uptake three-fold in this observational cohort.\n"
    result = run(case)
    record("causal_claim_associational_evidence", result["citation_checks"][0]["support_verdict"] == "partial" and result["citation_checks"][0]["support_relation"] == "scope_mismatch")

    case = base()
    case["manuscript_text"] = case["manuscript_text"].replace("[1]", "[2]", 1)
    result = run(case)
    record("callout_without_reference", "cite.reference_not_in_list" in rules(result) and result["citation_checks"][0]["support_verdict"] == "undetermined")

    case = base()
    case["manuscript_text"] = case["manuscript_text"].replace("The porous coating increased uptake three-fold [1].", "The porous coating increased uptake three-fold but reduced stability [1].")
    result = run(case)
    record("compound_claim_split", len(result["citation_checks"]) == 2 and {c["support_verdict"] for c in result["citation_checks"]} == {"supports", "not_supported"}, result["citation_checks"])

    case = base()
    case["manuscript_text"] = case["manuscript_text"].replace("The porous coating increased uptake three-fold in 24 samples.", "The porous coating increased uptake nine-fold in 24 samples.")
    result = run(case)
    record("abstract_body_numeric_conflict", "fact.numeric_conflict" in rules(result), result["fact_checks"])

    case = base()
    case["claims"] = [{"id": "explicit", "claim": "porous coating increases uptake three-fold", "reference_key": "1",
                       "evidence": [{"source": "1", "quote": "In 24 samples, the porous coating increased uptake three-fold compared with uncoated controls.", "locator": "p.1 results"}]}]
    result = run(case)
    record("explicit_exact_evidence", result["citation_checks"][0]["support_verdict"] == "supports" and result["citation_checks"][0]["evidence_locator"])

    case["claims"][0]["evidence"][0]["quote"] = "This quotation was never present in the supplied source."
    result = run(case)
    record("fabricated_evidence_quote_rejected", "cite.evidence_quote_not_in_source" in rules(result) and result["citation_checks"][0]["support_verdict"] == "undetermined")

    case = base()
    case["manuscript_text"] = case["manuscript_text"].replace("https://doi.org/10.1234/example.1", "DOI: broken-value")
    result = run(case)
    record("malformed_doi_is_not_invented", "cite.doi_malformed" in rules(result))

    case = base()
    case["manuscript_text"] = case["manuscript_text"].replace("three-fold [1]", "three-fold (Doe et al., 2020)").replace("[1] Doe", "Doe")
    result = run(case)
    record("author_year_callout_resolution", len(result["citation_instances"]) == 1 and result["citation_checks"][0]["support_verdict"] == "supports", result["citation_instances"])

    # One full CLI invocation verifies stdout, exit code, and the three persisted artifacts.
    with tempfile.TemporaryDirectory(prefix="cite-cli-bench-") as tmp:
        root = Path(tmp)
        proc = subprocess.run([sys.executable, "-I", str(Path(E.__file__)), "--case", str(EXAMPLE), "--out", str(root / "out")], capture_output=True, text=True)
        record("cli_clean_exit_and_artifacts", proc.returncode == 0 and not proc.stderr and all((root / "out" / name).is_file() for name in ("result.json", "audit_report.md", "run_log.json")), proc.stderr)

    passed = sum(r["passed"] for r in RESULTS)
    print(json.dumps({"suite": "citation_case", "passed": passed, "total": len(RESULTS), "failed": len(RESULTS)-passed}, ensure_ascii=False))
    print(f"{passed}/{len(RESULTS)} pass")
    return 0 if passed == len(RESULTS) else 1


if __name__ == "__main__":
    raise SystemExit(main())
