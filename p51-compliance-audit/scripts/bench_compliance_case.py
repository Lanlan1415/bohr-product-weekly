"""Functional bench for source-bound compliance audit and false-positive guards."""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import compliancecheck as E

EXAMPLE = Path(__file__).resolve().parents[1] / "examples" / "case.json"
RESULTS = []


def base():
    return json.loads(EXAMPLE.read_text(encoding="utf-8"))


def run(case):
    with tempfile.TemporaryDirectory(prefix="compliance-bench-") as tmp:
        root = Path(tmp)
        path = root / "case.json"
        path.write_text(json.dumps(case, ensure_ascii=False), encoding="utf-8")
        return E.run(path, root / "out")


def rules(result):
    return {f.get("rule") for f in result.get("findings", [])}


def record(name, passed, detail=""):
    RESULTS.append({"scenario": name, "passed": bool(passed), "detail": detail})
    if not passed:
        print("FAIL", name, detail if isinstance(detail, str) else "", sorted(rules(detail)) if isinstance(detail, dict) else "")


def remove(case, needle):
    case["manuscript_text"] = case["manuscript_text"].replace(needle, "")
    return case


def main():
    clean = run(base())
    record("clean_full_manuscript_zero_findings", clean["status"] == "clean" and not clean["findings"] and not clean["uncertainty"], clean)
    record("clean_contract_chinese_aliases", clean["case_id"] == "compliance-clean-smoke" and clean["审查报告"] == [] and clean["依据与边界"] and clean["结果状态"])
    record("no_corpus_or_guideline_is_honest_not_checked", clean["compliance_matrix"]["text_reuse"]["status"] == "not_checked" and clean["compliance_matrix"]["journal_requirements"]["status"] == "not_checked")

    case = remove(base(), "Ethics approval was granted by the University Institutional Review Board under protocol IRB-2024-017. All participants provided written informed consent before enrolment.")
    result = run(case)
    record("human_research_ethics_and_consent_gaps", {"compliance.ethics_approval_not_reported", "compliance.informed_consent_not_reported"} <= rules(result), result)

    case = base().copy()
    case["manuscript_text"] = case["manuscript_text"].replace("Ethics approval was granted by the University Institutional Review Board under protocol IRB-2024-017.", "Ethics approval was granted by the relevant committee after appropriate review.")
    result = run(case)
    record("ethics_identifier_gap_not_approval_denial", "compliance.ethics_identifier_not_reported" in rules(result) and "compliance.ethics_approval_not_reported" not in rules(result), result)

    for name, needle, expected in (
        ("data_statement_gap", "Data availability: De-identified aggregate data are available in the institutional repository under accession DA-104.", "compliance.data_availability_not_reported"),
        ("code_statement_gap", "Code availability: The analysis source code is available at the same accession, version 1.0.", "compliance.code_availability_not_reported"),
        ("coi_statement_gap", "Competing interests: The authors declare no competing interests.", "compliance.coi_not_reported")):
        case = remove(base(), needle)
        result = run(case)
        record(name, expected in rules(result) and all(f["verdict"] == "not_reported_not_misconduct" for f in result["findings"] if f["rule"] == expected), result)

    case = base()
    case["manuscript_text"] += "\nWe used GPT-4 to edit the manuscript for grammar.\n"
    result = run(case)
    record("actual_ai_assistance_needs_disclosure", "compliance.ai_use_disclosure_not_reported" in rules(result), result)

    case = base()
    case["manuscript_text"] += "\nDuring the preparation of this manuscript, we used GPT-4 for language editing; all authors reviewed and verified the output.\n"
    result = run(case)
    record("explicit_ai_disclosure_clean", "compliance.ai_use_disclosure_not_reported" not in rules(result), result)

    case = base()
    case["manuscript_text"] += "\nWe evaluated ChatGPT as a research subject for diagnostic answer quality.\n"
    result = run(case)
    record("ai_as_research_subject_not_use", "compliance.ai_use_disclosure_not_reported" not in rules(result), result)

    case = base()
    case["authors"] = [{"given": "Ada", "family": "Lovelace"}, {"given": "Alan", "family": "Turing"}]
    case["author_contributions"] = {"Ada Lovelace": ["analysis"], "Grace Hopper": ["writing"]}
    result = run(case)
    record("authorship_mapping_both_directions", {"compliance.author_contribution_not_mapped", "compliance.contributor_not_in_author_list"} <= rules(result), result)

    case = base()
    case["manuscript_text"] += "\nFigure 2 was adapted from Example et al.\n"
    result = run(case)
    record("third_party_permission_gap", "copyright.reuse_permission_not_reported" in rules(result), result)

    case = base()
    case["manuscript_text"] += "\nFigure 2 was adapted from Example et al. with permission and licensed under CC BY.\n"
    result = run(case)
    record("third_party_permission_present_clean", "copyright.reuse_permission_not_reported" not in rules(result), result)

    case = base()
    case["manuscript_text"] += "\nThe exported cohort table contains Patient ID: P-10493.\n"
    result = run(case)
    record("direct_identifier_detected", "privacy.direct_identifier_exposed" in rules(result), result)

    case = base()
    case["images"] = [{"id": "Fig1", "sha256": "ab12"}, {"id": "Fig4", "sha256": "ab12"}]
    result = run(case)
    record("identical_image_hash_investigation_signal", "integrity.identical_image_reuse_undeclared" in rules(result) and next(f for f in result["findings"] if f["rule"] == "integrity.identical_image_reuse_undeclared")["verdict"] == "requires_investigation_not_falsification_verdict", result)

    case = base()
    case["images"] = [{"id": "Fig1", "sha256": "ab12", "reuse_declared": True}, {"id": "Fig4", "sha256": "ab12", "reuse_declared": True}]
    result = run(case)
    record("declared_image_reuse_clean", "integrity.identical_image_reuse_undeclared" not in rules(result), result)

    sentence = "We evaluated whether a coached walking programme was associated with daily activity in adults."
    case = base()
    case["comparison_corpus"] = [{"title": "Prior text", "text": sentence}]
    result = run(case)
    record("exact_unattributed_text_overlap", "integrity.possible_unattributed_text_reuse" in rules(result) and next(x for x in result["text_reuse_checks"] if x["manuscript_quote"] == sentence)["verdict"] == "possible_unattributed_text_reuse", result)

    case = base()
    case["manuscript_text"] = case["manuscript_text"].replace(sentence, sentence + " [1]")
    case["comparison_corpus"] = [{"title": "Prior text", "text": sentence}]
    result = run(case)
    record("quoted_or_cited_overlap_not_misconduct", "integrity.possible_unattributed_text_reuse" not in rules(result), result)

    case = base()
    case["title"] = "Effects of a coached walking programme on activity"
    case["comparison_corpus"] = [{"title": "Effects of a coached walking programme on activity", "abstract": "We evaluated whether a coached walking programme was associated with daily activity in adults. Forty adults participated in a randomised controlled comparison. Activity was measured for seven days using a wearable sensor."}]
    result = run(case)
    record("prior_publication_overlap_requires_review", "integrity.possible_redundant_publication" in rules(result) or result["duplicate_publication_checks"], result)

    case = base()
    case["references"] = [{"key": "1", "title": "Retracted walking study", "retracted": True, "retraction_notice": "Journal notice 2024-9"}]
    result = run(case)
    record("retracted_source_bound_to_supplied_notice", "compliance.retracted_source_used" in rules(result), result)

    case = base()
    case["journal_requirements"] = {"required_sections": ["Limitations"], "required_declarations": ["data_availability", "ai_use_disclosure"], "word_limit": 50}
    result = run(case)
    record("guideline_requirements_and_provenance", {"journal.required_section_missing", "journal.required_declaration_missing", "journal.word_limit_exceeded"} <= rules(result) and result["uncertainty"], result)

    with tempfile.TemporaryDirectory(prefix="compliance-cli-bench-") as tmp:
        proc = subprocess.run([sys.executable, "-I", str(Path(E.__file__)), "--case", str(EXAMPLE), "--out", str(Path(tmp) / "out")], capture_output=True, text=True)
        record("cli_clean_exit_and_artifacts", proc.returncode == 0 and not proc.stderr and all((Path(tmp) / "out" / name).is_file() for name in ("result.json", "audit_report.md", "run_log.json")), proc.stderr)

    passed = sum(r["passed"] for r in RESULTS)
    print(json.dumps({"suite": "compliance_case", "passed": passed, "total": len(RESULTS), "failed": len(RESULTS)-passed}, ensure_ascii=False))
    print(f"{passed}/{len(RESULTS)} pass")
    return 0 if passed == len(RESULTS) else 1


if __name__ == "__main__":
    raise SystemExit(main())
