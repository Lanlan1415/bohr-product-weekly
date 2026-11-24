"""Functional bench for argument-map and cross-section reasoning audit."""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import logiccheck as E

EXAMPLE = Path(__file__).resolve().parents[1] / "examples" / "case.json"
RESULTS = []


def base():
    return json.loads(EXAMPLE.read_text(encoding="utf-8"))


def run(case):
    with tempfile.TemporaryDirectory(prefix="logic-bench-") as tmp:
        root = Path(tmp)
        path = root / "case.json"
        path.write_text(json.dumps(case, ensure_ascii=False), encoding="utf-8")
        return E.run(path, root / "out")


def rules(result):
    return {f.get("rule") for f in result.get("findings", [])}


def record(name, passed, detail=""):
    RESULTS.append({"scenario": name, "passed": bool(passed), "detail": detail})
    if not passed:
        readable = detail if isinstance(detail, str) else json.dumps(detail, ensure_ascii=False, default=str)[:5000]
        print("FAIL", name, readable)


def observational(case):
    case["design"] = "observational cross-sectional cohort"
    case["manuscript_text"] = case["manuscript_text"].replace("This was a randomized controlled trial. We recruited 40 adults and randomly assigned them to coached or self-directed walking.", "This was an observational cross-sectional study. We recruited 40 adults who reported coached or self-directed walking.")
    return case


def main():
    clean = run(base())
    record("clean_argument_map_zero_findings", clean["status"] == "clean" and not clean["findings"] and not clean["uncertainty"], clean)
    record("clean_promise_delivered", clean["promise_checks"] and all(x["status"] == "delivered" for x in clean["promise_checks"]), clean)
    record("argument_map_has_claim_evidence_locator", clean["argument_map"] and all(c["locator"] and "evidence" in c and "warrant" in c for c in clean["argument_map"]))
    record("question_method_result_conclusion_chain", clean["research_chains"] and all(
        set(c["steps"]) == {"problem", "method", "result", "conclusion"} and
        c["steps"]["problem"]["quote"] in base()["manuscript_text"] and
        all("claim_coverage" in c["steps"][role] for role in ("method", "result", "conclusion"))
        for c in clean["research_chains"]), clean.get("research_chains"))
    paragraph_functions_ok = all(p["function"] and p["quote"] and p["locator"] and p["proposed_function_is_heuristic"]
                                 for p in clean["paragraph_functions"])
    record("paragraph_function_inventory", bool(clean["paragraph_functions"]) and paragraph_functions_ok,
           clean.get("paragraph_functions"))

    case = base()
    case["manuscript_text"] = case["manuscript_text"].replace("2 Methods", "2 Procedure")
    result = run(case)
    record("missing_method_chain_has_executable_gap", any(
        "method" in c["missing_or_weak_roles"] and c["repair_actions"][0]["action"] and
        c["repair_actions"][0]["after"] for c in result["research_chains"]), result.get("research_chains"))

    case = base()
    case["manuscript_text"] = (
        "Abstract\nWe aim to compare wavelength drift in two coatings.\n\n"
        "1 Introduction\nWe aim to compare wavelength drift between coating A and coating B.\n\n"
        "3 Results\nCoating A drifted 2 nm and coating B drifted 1 nm in Table 1.\n\n"
        "2 Methods\nWe measured wavelength drift in coating A and coating B with the same spectrometer.\n\n"
        "4 Discussion\nThe wavelength drift may indicate a coating stability difference.\n\n"
        "5 Conclusion\nThe wavelength result is limited to these two coatings.\n")
    result = run(case)
    reorder = [edit for edit in result["editorial_plan"] if edit["edit_type"] == "reorder"]
    record("executable_section_reorder", bool(reorder) and all(
        edit["action"].lower().startswith("move") and edit["target"] and
        edit["source_quote"] in case["manuscript_text"] and edit["requires_author_review"]
        for edit in reorder), result.get("editorial_plan"))

    case = base()
    duplicated = ("We aim to compare daily step counts between coached and self-directed walking. "
                  "Prior studies motivate controlled measurement, but the appropriate population and follow-up window remain uncertain.")
    case["manuscript_text"] = case["manuscript_text"].replace("4 Discussion", "4 Discussion\n" + duplicated + "\n\n")
    result = run(case)
    cross_duplicates = [edit for edit in result["editorial_plan"] if edit["edit_type"] == "duplicate"]
    record("cross_section_duplicate_merge_plan", any(
        edit["action"].startswith("Merge repeated cross-section content") and
        len(edit["source_locators"]) == 2 and edit["target"] for edit in cross_duplicates),
        result.get("editorial_plan"))

    case = observational(base())
    case["manuscript_text"] = case["manuscript_text"].replace("In this sample, coached walking was associated with 8,200 rather than 7,900 daily steps over seven days.", "Coached walking caused higher daily step counts and improved health.")
    result = run(case)
    record("observational_causal_overreach", "logic.causal_overreach" in rules(result) and next(f for f in result["findings"] if f["rule"] == "logic.causal_overreach")["replacement_text"], result)

    case = observational(base())
    result = run(case)
    record("associational_and_hedged_clean", "logic.causal_overreach" not in rules(result), result)

    case = base()
    case["manuscript_text"] = case["manuscript_text"].replace("The coached group recorded 8,200 steps per day compared with 7,900 in the self-directed group. Table 1", "The difference between coached and self-directed walking was not significant. Table 1")
    case["manuscript_text"] = case["manuscript_text"].replace("In this sample, coached walking was associated with 8,200 rather than 7,900 daily steps over seven days.", "Coached walking increased daily step counts.")
    result = run(case)
    record("nonsignificant_claimed_as_effect", "logic.non_significant_result_claimed_as_effect" in rules(result), result)

    case = base()
    case["manuscript_text"] = case["manuscript_text"].replace("40 adults", "40 mice").replace("recruited adults", "recruited mice")
    case["manuscript_text"] = case["manuscript_text"].replace("Coached walking was associated", "Coached walking was associated")
    case["manuscript_text"] = case["manuscript_text"].replace("In this sample, coached walking was associated with 8,200 rather than 7,900 daily steps over seven days.", "This treatment improves memory in humans.")
    result = run(case)
    record("nonhuman_to_human_extrapolation", "logic.species_or_population_extrapolation" in rules(result), result)

    case = base()
    case["manuscript_text"] = case["manuscript_text"].replace("This was a randomized controlled trial.", "This single-centre study was a randomized controlled trial.")
    case["manuscript_text"] = case["manuscript_text"].replace("In this sample, coached walking was associated with 8,200 rather than 7,900 daily steps over seven days.", "This programme is universally effective for adults.")
    result = run(case)
    record("single_site_universal_extrapolation", "logic.sample_scope_extrapolation" in rules(result), result)

    case = observational(base())
    text = case["manuscript_text"]
    text = text.replace("The estimate is limited to this sample and measurement period.", "").replace("The step-count estimate is consistent with a modest short-term difference, but it may reflect adherence and the limited observation window. Alternative explanations include sensor measurement error and participant expectations. These findings are limited to the recruited adults and should not be extrapolated to clinical outcomes or other populations.", "The result supports the programme.")
    text = text.replace("In this sample, coached walking was associated with 8,200 rather than 7,900 daily steps over seven days.", "Coaching caused higher step counts through adherence.").replace("The estimate is limited to this sample and does not establish longer-term or clinical effects.", "")
    case["manuscript_text"] = text
    result = run(case)
    record("mechanism_without_alternative_explanations", "logic.alternative_explanations_not_addressed" in rules(result), result)

    case = base()
    case["manuscript_text"] = case["manuscript_text"].replace("In this sample, coached walking was associated with 8,200 rather than 7,900 daily steps over seven days.", "We demonstrate that coaching cures chronic disease.")
    result = run(case)
    record("strong_claim_without_evidence_chain", "logic.evidence_link_missing" in rules(result), result)

    case = base()
    case["manuscript_text"] = case["manuscript_text"].replace("We aim to compare daily step counts between coached and self-directed walking.", "We aim to compare mitochondrial respiration across zebrafish embryos.")
    result = run(case)
    record("introduction_promise_not_delivered", "logic.promise_not_delivered" in rules(result), result)

    case = base()
    case["manuscript_text"] = case["manuscript_text"].replace("The coached group recorded 8,200 steps per day compared with 7,900 in the self-directed group. Table 1", "The coached group recorded 9,100 steps per day compared with 7,900 in the self-directed group. Table 1")
    result = run(case)
    record("shared_control_changed_effect_contradiction", "logic.cross_section_contradiction" in rules(result), result)

    case = observational(base())
    case["manuscript_text"] += "\nSmith et al. (2020) demonstrated that coaching caused weight loss in their cohort.\n"
    result = run(case)
    record("third_party_claim_not_author_overclaim", "logic.causal_overreach" not in rules(result), result)

    case = observational(base())
    case["manuscript_text"] = case["manuscript_text"].replace("In this sample, coached walking was associated with 8,200 rather than 7,900 daily steps over seven days.", "We hypothesize that coaching caused higher daily step counts.")
    result = run(case)
    record("explicit_hypothesis_not_overclaim", "logic.causal_overreach" not in rules(result), result)

    case = base()
    case["manuscript_text"] = case["manuscript_text"].replace("40 adults", "40 mice").replace("recruited adults", "recruited mice")
    case["manuscript_text"] = case["manuscript_text"].replace("In this sample, coached walking was associated with 8,200 rather than 7,900 daily steps over seven days.", "This treatment may improve memory in humans.")
    result = run(case)
    record("hedged_translation_not_species_overclaim", "logic.species_or_population_extrapolation" not in rules(result), result)

    case = base()
    case["manuscript_text"] = case["manuscript_text"].replace("The estimate is limited to this sample and measurement period.", "").replace("The estimate is limited to this sample and does not establish longer-term or clinical effects.", "")
    case["manuscript_text"] = case["manuscript_text"].replace("The step-count estimate is consistent with a modest short-term difference, but it may reflect adherence and the limited observation window. Alternative explanations include sensor measurement error and participant expectations. These findings are limited to the recruited adults and should not be extrapolated to clinical outcomes or other populations.", "The result supports the programme.")
    case["manuscript_text"] = case["manuscript_text"].replace("In this sample, coached walking was associated with 8,200 rather than 7,900 daily steps over seven days.", "We demonstrate that coaching increases daily step counts.")
    result = run(case)
    record("absolute_conclusion_missing_boundaries", "logic.boundary_conditions_missing" in rules(result), result)

    with tempfile.TemporaryDirectory(prefix="logic-cli-bench-") as tmp:
        proc = subprocess.run([sys.executable, "-I", str(Path(E.__file__)), "--case", str(EXAMPLE), "--out", str(Path(tmp) / "out")], capture_output=True, text=True)
        record("cli_clean_exit_and_artifacts", proc.returncode == 0 and not proc.stderr and all((Path(tmp) / "out" / name).is_file() for name in ("result.json", "audit_report.md", "run_log.json")), proc.stderr)

    passed = sum(r["passed"] for r in RESULTS)
    print(json.dumps({"suite": "logic_case", "passed": passed, "total": len(RESULTS), "failed": len(RESULTS)-passed}, ensure_ascii=False))
    print(f"{passed}/{len(RESULTS)} pass")
    return 0 if passed == len(RESULTS) else 1


if __name__ == "__main__":
    raise SystemExit(main())
