"""Deep bilingual conservation/contract regression suite; synthetic fixtures only."""
from __future__ import annotations

import copy
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
import bilingual_extra as BX  # noqa: E402
import writeaudit as CLI  # noqa: E402
import writing as W  # noqa: E402

S1 = "Only 3 samples may show higher sorption at approximately 25 °C, with $E=mc^2$ (Fig. 1) [1]."
S2 = "The process did not decrease unless the pH changed, as reported in [@doi:10.1038/example.4; @smith2020]."
T1 = "在约 25 °C 下，仅 3 个样本的吸附量可能提高，$E=mc^2$（图 1）[1]。"
T2 = "如 [@doi:10.1038/example.4; @smith2020] 所报道，除非 pH 改变，否则该过程未降低。"
SEGMENTS = [
    {"id": "p1", "source": S1, "target": T1},
    {"id": "p2", "source": S2, "target": T2},
]


def clean_spec():
    return {
        "case_id": "synthetic-bilingual-clean",
        "section": "translation", "output_mode": "bilingual",
        "source_lang": "en", "target_lang": "zh",
        "source_text": S1 + " " + S2,
        "segments": copy.deepcopy(SEGMENTS),
        "glossary": {
            "sorption": {"preferred": "吸附量", "source_form": "sorption",
                         "variants": ["absorption"], "basis": "synthetic domain term convention"},
        },
        "backcheck": [{"segment": "p1", "verdict": "match"},
                      {"segment": "p2", "verdict": "match"}],
        "ambiguities": [{"segment": "p2", "issue": "scope of unless", "status": "resolved",
                         "resolution": "除非 pH 改变 explicitly preserves the exception"}],
        "naturalness_review": {"audience": "researchers", "register": "academic",
                                "reviewer": "bilingual editor", "literal_spans": []},
        "output_contract": {
            "case_id": "identifier", "status": "run state", "deliverable": "translation",
            "target_text": "complete editable target",
            "evidence_map": "conservation ledger", "boundary": "limits and review",
            "editor_review": {"decision": "human decision", "comments": "human comments"},
        },
        "limits": [],
    }


def rules(spec):
    findings, status, _ = W.run(spec, "translation")
    return [f["rule"] for f in findings], status


def magnitude_spec(conversions):
    spec = clean_spec()
    spec.update(output_mode="plain", source_lang="zh", target_lang="en", segments=[],
                source_text="样本量达到 300 万[1]。",
                target_text="The sample reached 3 million [1].",
                glossary={}, backcheck=[], ambiguities=[], conversions=conversions)
    return spec


def run_cli(case_path: Path, out: Path, spec=False):
    flag = "--spec" if spec else "--case"
    proc = subprocess.run([sys.executable, "-I", "-B", str(ROOT / "writeaudit.py"), flag,
                           str(case_path), "--out", str(out)], capture_output=True, text=True,
                          timeout=120)
    result_path = out / "result.json"
    result = json.loads(result_path.read_text(encoding="utf-8")) if result_path.exists() else {}
    return proc, result, result_path


def main():
    rows = []

    def check(name, condition, detail=""):
        rows.append({"scenario": name, "pass": bool(condition), "detail": detail})
        print(f"{'PASS' if condition else 'FAIL'}  {name:<38} {detail}")

    def defect(name, mutate, expected, forbidden=()):
        spec = clean_spec()
        mutate(spec)
        found, _ = rules(spec)
        check(name, all(rule in found for rule in expected)
              and not any(rule in found for rule in forbidden), str(sorted(set(found))))

    found, status = rules(clean_spec())
    check("clean_full_bilingual_zero_findings", found == [] and status == "clean", str(found))

    defect("formula_semantics_changed",
           lambda s: s["segments"][0].update(target=T1.replace("E=mc^2", "E=mc^3")),
           ["xlate.formula_missing", "xlate.formula_added"])
    defect("display_math_dropped",
           lambda s: (s.update(output_mode="plain", source_lang="en", target_lang="en",
                               source_text="Identity \\[\\Delta G = \\mu\\] is fixed.",
                               target_text="Identity \\[\\Delta G = \\lambda\\] is fixed.",
                               segments=[]),),
           ["xlate.formula_missing", "xlate.formula_added"])
    defect("persistent_doi_dropped",
           lambda s: s["segments"][1].update(target=T2.replace("10.1038/example.4", "10.1038/changed.4")),
           ["xlate.citation_identity_missing", "xlate.citation_identity_added"])
    defect("manubot_alias_dropped",
           lambda s: s["segments"][1].update(target=T2.replace("@smith2020", "@other2020")),
           ["xlate.citation_identity_missing", "xlate.citation_identity_added"])
    defect("segment_order_reversed",
           lambda s: s.update(segments=list(reversed(s["segments"]))),
           ["xlate.segment_order_changed"])
    defect("segment_duplicate_source",
           lambda s: s.update(segments=[copy.deepcopy(s["segments"][0]),
                                         dict(copy.deepcopy(s["segments"][0]), id="p2")]),
           ["xlate.segment_duplicate_source"])
    defect("source_span_fabricated",
           lambda s: s["segments"][0].update(source="A fabricated sentence that was never supplied."),
           ["xlate.segment_source_mismatch"])
    defect("only_scope_lost",
           lambda s: s["segments"][0].update(target=T1.replace("仅 3 个", "3 个")),
           ["xlate.segment_limiter_changed"])
    defect("approximation_added",
           lambda s: s["segments"][1].update(target="约" + T2),
           ["xlate.segment_limiter_changed"])
    defect("segment_negation_lost",
           lambda s: s["segments"][1].update(target=T2.replace("未降低", "降低了")),
           ["xlate.segment_negation_changed"])
    defect("segment_hedge_lost",
           lambda s: s["segments"][0].update(target=T1.replace("可能提高", "提高")),
           ["xlate.segment_hedge_changed"])
    defect("ambiguity_unresolved",
           lambda s: s.update(ambiguities=[{"segment": "p2", "issue": "unless scope"}]),
           ["xlate.ambiguity_unresolved"])
    defect("ambiguity_orphan",
           lambda s: s.update(ambiguities=[{"segment": "does-not-exist", "issue": "word sense",
                                             "resolution": "reviewed"}]),
           ["xlate.ambiguity_orphaned"])
    defect("ambiguity_registry_wrong_type", lambda s: s.update(ambiguities="pending"),
           ["xlate.ambiguity_registry_malformed"])
    defect("glossary_variants_wrong_type",
           lambda s: s["glossary"]["sorption"].update(variants=42),
           ["xlate.glossary_variants_malformed"])
    found, _ = rules(magnitude_spec([{"from": "300 万", "to": "30 million"}]))
    check("conversion_endpoint_arithmetic_not_arbitrary",
          "xlate.conversion_arithmetic_mismatch" in found
          and "xlate.invariant_broken" in found, str(found))
    found, _ = rules(magnitude_spec([{"from": "300 万", "to": "3 million", "factor": "1e3"}]))
    check("conversion_factor_hint_audited",
          "xlate.conversion_factor_mismatch" in found
          and "xlate.invariant_broken" not in found, str(found))
    found, _ = rules(magnitude_spec("300万 -> 3 million"))
    check("conversion_record_malformed_no_excuse",
          "xlate.conversion_malformed" in found and "xlate.invariant_broken" in found)
    found, _ = rules(magnitude_spec([{"from": "3 万", "to": "30,000", "factor": 10000}])
                     | {"source_text": "样本量达到 3 万[1]。",
                        "target_text": "The sample reached 30,000 [1]."})
    check("chinese_magnitude_to_comma_digits_clean", not any(
        r.startswith("xlate.conversion") or r == "xlate.invariant_broken" for r in found), str(found))
    bad_languages = clean_spec()
    bad_languages["source_lang"] = ["en"]
    bad_languages["target_lang"] = {"name": "zh"}
    found, _ = rules(bad_languages)
    check("wrong_language_scalar_types_never_crash", "xlate.segment_order_changed" not in found)

    spec = clean_spec()
    spec["ambiguities"] = [{"segment": "p2", "issue": "nuance requires author decision",
                             "status": "open"}]
    found, _ = rules(spec)
    opens = W.open_questions(spec, "translation")
    check("open_ambiguity_is_honest_review_not_silenced",
          "xlate.ambiguity_unresolved" not in found
          and any(x.get("kind") == "ambiguity_backcheck" for x in opens))

    # Repeated identical source passages are a legitimate clean twin.
    repeated = clean_spec()
    repeated.update(source_text="Same result. Same result.",
                    segments=[{"id": "a", "source": "Same result.", "target": "同一结果。"},
                              {"id": "b", "source": "Same result.", "target": "同一结果。"}],
                    output_mode="bilingual", source_lang="en", target_lang="zh",
                    source_glossary_unused=None)
    repeated.pop("source_glossary_unused")
    repeated["glossary"] = {}
    repeated["backcheck"] = []
    repeated["ambiguities"] = []
    found, _ = rules(repeated)
    check("repeated_source_paragraphs_no_alignment_fp",
          not any(r in found for r in ("xlate.segment_duplicate_source",
                                        "xlate.segment_source_mismatch")), str(found))

    # DOI identity survives @doi -> resolver URL; aliases and equations stay.
    plain = clean_spec()
    plain.update(output_mode="plain", source_lang="en", target_lang="zh", segments=[],
                 source_text="The source is [@doi:10.1038/example.4; @smith2020] with $\\Delta G$.",
                 target_text="来源为 https://doi.org/10.1038/example.4 和 [@smith2020]，含 $\\Delta G$。",
                 glossary={}, backcheck=[], ambiguities=[])
    found, _ = rules(plain)
    check("doi_url_equivalence_and_formula_no_fp",
          not any(r.startswith("xlate.citation_identity") or r.startswith("xlate.formula")
                  for r in found), str(found))
    check("cross_language_figure_xref_equivalence",
          BX.extract_xrefs(S1) == BX.extract_xrefs(T1))

    with tempfile.TemporaryDirectory(prefix="bilingual_deep_") as td:
        tmp = Path(td)
        case = clean_spec()
        case_path = tmp / "case.json"
        case_path.write_text(json.dumps(case, ensure_ascii=False), encoding="utf-8")
        proc, result, result_path = run_cli(case_path, tmp / "out_case")
        check("case_direct_clean_contract",
              proc.returncode == 0 and result.get("case_id") == case["case_id"]
              and all(k in result for k in case["output_contract"])
              and result.get("deliverable", {}).get("segment_count") == 2,
              f"exit={proc.returncode} findings={[x.get('rule') for x in result.get('findings', [])]}")
        check("declared_target_text_not_nulled",
              result.get("target_text") == W._segments_text(SEGMENTS, "target")
              and result.get("output_contract", {}).get("target_text") == result.get("target_text"))
        check("output_has_symbol_and_citation_evidence",
              any(x.get("kind") == "formula" for x in result.get("evidence_map", []))
              and any(x.get("kind") == "persistent_citation" and x.get("verdict") == "match"
                      for x in result.get("evidence_map", [])))
        check("nested_contract_shape_preserved",
              set(result.get("editor_review", {})) == {"decision", "comments"}
              and all(v is None for v in result["editor_review"].values())
              and any("editor_review.decision" in x for x in result.get("limits", [])))
        first = result_path.read_bytes()
        proc_again, _, _ = run_cli(case_path, tmp / "out_case")
        check("case_rerun_byte_identical",
              proc_again.returncode == 0 and result_path.read_bytes() == first)

        # Nested spec receives identity/contract from its actual case envelope.
        nested = {"case_id": "case-envelope", "output_contract": case["output_contract"],
                  "spec": {k: v for k, v in case.items() if k not in ("case_id", "output_contract")}}
        nested_path = tmp / "nested_case.json"
        nested_path.write_text(json.dumps(nested, ensure_ascii=False), encoding="utf-8")
        proc_nested, r_nested, _ = run_cli(nested_path, tmp / "out_nested")
        check("nested_spec_case_entry",
              proc_nested.returncode == 0 and r_nested.get("case_id") == "case-envelope"
              and all(k in r_nested for k in nested["output_contract"]))

        bad_section = copy.deepcopy(nested)
        bad_section["spec"]["section"] = "not-a-section"
        bad_path = tmp / "bad_section.json"
        bad_path.write_text(json.dumps(bad_section, ensure_ascii=False), encoding="utf-8")
        proc_bad, r_bad, _ = run_cli(bad_path, tmp / "out_bad_section")
        check("structured_refusal_retains_contract",
              proc_bad.returncode == 5 and r_bad.get("status") == "undetermined"
              and r_bad.get("case_id") == "case-envelope"
              and all(k in r_bad for k in nested["output_contract"]))
        list_section = copy.deepcopy(nested)
        list_section["spec"]["section"] = ["translation"]
        list_path = tmp / "list_section.json"
        list_path.write_text(json.dumps(list_section, ensure_ascii=False), encoding="utf-8")
        proc_list, r_list, _ = run_cli(list_path, tmp / "out_list_section")
        check("list_section_refusal_no_traceback",
              proc_list.returncode == 5 and r_list.get("status") == "undetermined"
              and r_list.get("case_id") == "case-envelope" and "Traceback" not in proc_list.stderr)

        malformed = tmp / "malformed.json"
        malformed.write_text("{bad json", encoding="utf-8")
        proc_json, r_json, _ = run_cli(malformed, tmp / "out_bad_json")
        check("malformed_case_refusal_no_traceback",
              proc_json.returncode == 5 and r_json.get("case_id") is None
              and "Traceback" not in proc_json.stderr)
        missing = tmp / "missing.json"
        proc_missing, r_missing, _ = run_cli(missing, tmp / "out_missing")
        check("missing_case_refusal", proc_missing.returncode == 5
              and r_missing.get("status") == "undetermined")

        # Legacy --spec and isolated cold import remain executable.
        proc_legacy, r_legacy, _ = run_cli(case_path, tmp / "out_legacy", spec=True)
        check("legacy_spec_compatibility", proc_legacy.returncode == 0
              and r_legacy.get("case_id") == case["case_id"])
        cold = subprocess.run(
            [sys.executable, "-I", "-B", "-c",
             "import importlib.util,sys;sys.dont_write_bytecode=True;p=" + repr(str(ROOT / 'bilingual_extra.py')) +
             ";s=importlib.util.spec_from_file_location('cold_bilingual',p);"
             "m=importlib.util.module_from_spec(s);"
             "sys.path.insert(0," + repr(str(ROOT)) + ");s.loader.exec_module(m);print('ok')"],
            capture_output=True, text=True, timeout=120)
        check("cold_isolated_import", cold.returncode == 0 and "ok" in cold.stdout,
              cold.stderr.strip()[:160])

    report = {"schema_version": "bilingual-deep-bench/v1", "fixtures_are_synthetic": True,
              "scenarios": rows, "totals": {"passed": sum(x["pass"] for x in rows), "of": len(rows)}}
    (ROOT / "report_bilingual_deep.json").write_text(json.dumps(report, ensure_ascii=False, indent=2),
                                                     encoding="utf-8")
    print(f"\n{report['totals']['passed']}/{len(rows)} pass")
    return 0 if all(x["pass"] for x in rows) else 1


if __name__ == "__main__":
    raise SystemExit(main())
