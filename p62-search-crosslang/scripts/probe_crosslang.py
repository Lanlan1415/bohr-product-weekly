"""Black-box hostile probes for cross-language evidence, versions and contracts."""
from __future__ import annotations

import copy
import json
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import case_common as C  # noqa: E402

BASE = json.loads((HERE.parent / "examples" / "case.json").read_text(encoding="utf-8"))
CLI = HERE / "crosslang_cli.py"


def invoke(tmp, case=None, raw=None, filename="case.json", outname="out"):
    path = tmp / filename
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(raw if raw is not None else json.dumps(case, ensure_ascii=False), encoding="utf-8")
    out = tmp / outname
    proc = subprocess.run([sys.executable, "-I", "-X", "utf8", str(CLI), "--case", str(path), "--out", str(out)],
                          capture_output=True, text=True, timeout=90)
    result = json.loads((out / "result.json").read_text(encoding="utf-8")) if (out / "result.json").exists() else {}
    return proc, result, out


def no_tb(p):
    return "Traceback" not in p.stderr and "Traceback" not in p.stdout


def scenario(tmp, name):
    base = copy.deepcopy(BASE)
    if name == "bad_json_exit5":
        p, r, _ = invoke(tmp, raw="{bad")
        return p.returncode == 5 and r["refusal"]["rule"] == "crosslang.case_unreadable" and no_tb(p)
    if name == "array_case_exit4":
        p, r, _ = invoke(tmp, case=[])
        return p.returncode == 4 and r["refusal"]["rule"] == "crosslang.case_not_object" and no_tb(p)
    if name == "unknown_section_exit5_contract":
        base["section"] = "coverage"
        p, r, _ = invoke(tmp, case=base)
        return p.returncode == 5 and r["refusal"]["rule"] == "crosslang.unknown_section" \
            and all(k in r for k in C.contract_fields(base["output_contract"])[0]) and no_tb(p)
    if name == "no_documents_exit5":
        base.pop("documents")
        p, r, _ = invoke(tmp, case=base)
        return p.returncode == 5 and r["refusal"]["rule"] == "crosslang.no_documents" and no_tb(p)
    if name == "bad_document_shape_exit5":
        base["documents"] = 42
        p, r, _ = invoke(tmp, case=base)
        return p.returncode == 5 and r["refusal"]["rule"] in {"search.material_shape", "crosslang.no_documents"} and no_tb(p)
    if name == "no_concepts_exit5":
        base.pop("concepts")
        p, r, _ = invoke(tmp, case=base)
        return p.returncode == 5 and r["refusal"]["rule"] == "crosslang.no_concepts" and no_tb(p)
    if name == "empty_concepts_exit5":
        base["concepts"] = []
        p, r, _ = invoke(tmp, case=base)
        return p.returncode == 5 and r["refusal"]["rule"] == "crosslang.no_concepts" and no_tb(p)
    if name == "language_cannot_be_guessed_silently":
        base["documents"][5].pop("language")
        p, r, _ = invoke(tmp, case=base)
        return p.returncode == 3 and any(x["rule"] == "crosslang.language_uncertain" for x in r["findings"]) and no_tb(p)
    if name == "language_script_conflict_is_review":
        doc = base["documents"][5]
        doc["title"], doc["abstract"], doc["full_text"] = "细胞焦亡", "", ""
        p, r, _ = invoke(tmp, case=base)
        return p.returncode == 3 and any(x["rule"] == "crosslang.language_conflict" for x in r["findings"]) and no_tb(p)
    if name == "version_conflict_retains_both_views":
        base["documents"][2]["full_text"] = "A substantively different and unauthorized translation text."
        p, r, _ = invoke(tmp, case=base)
        w1 = next(x for x in r["candidate_set"] if x["work_id"] == "work:w1")
        return p.returncode == 3 and len(w1["views"]) == 3 \
            and any(x["rule"] == "crosslang.version_conflict" for x in r["findings"]) and no_tb(p)
    if name == "translation_service_failure_no_fabrication":
        base["translation_service_status"] = "failed: quota exhausted"
        p, r, _ = invoke(tmp, case=base)
        return p.returncode == 3 and any(x["rule"] == "crosslang.translation_service_unavailable" for x in r["findings"]) \
            and all(q["expression"] for q in r["multilingual_queries"]) and no_tb(p)
    if name == "machine_translation_is_version_evidence_not_original_quote":
        base["documents"][1]["version_kind"] = "machine_translation"
        p, r, _ = invoke(tmp, case=base)
        evidence = [ev for row in r["evidence_ledger"] if row["doc_id"] == "w1-en-publisher-translation" for ev in row["evidence"]]
        return evidence and all(ev["is_machine_translated_quote"] for ev in evidence) \
            and all(ev["quotation_role"] == "translation_version_evidence_not_original_quotation" for ev in evidence) and no_tb(p)
    if name == "abstract_only_not_promoted_to_fulltext":
        p, r, _ = invoke(tmp, case=base)
        view = next(v for w in r["candidate_set"] for v in w["views"] if v["doc_id"] == "w2-en-abstract-only")
        return p.returncode == 0 and view["abstract_only"] and not view["full_text_available"] and no_tb(p)
    if name == "malformed_prf_settings_degrade":
        base["pseudo_relevance_feedback"].update({"fb_docs": "many", "fb_terms": None, "min_document_frequency": "all"})
        p, r, _ = invoke(tmp, case=base)
        return p.returncode == 0 and "feedback_runs" in r and no_tb(p)
    if name == "contract_mapping_full_echo":
        base["output_contract"] = {"case_id": "id", "ranked_results": {}, "delivery": "x", "unknown": None}
        base["delivery"] = 12
        p, r, _ = invoke(tmp, case=base)
        return p.returncode == 3 and r["delivery"] == 12 and "unknown" in r and r["unknown"] is None \
            and r["output_contract"] == base["output_contract"] and no_tb(p)
    if name == "status_cannot_be_spoofed":
        base["output_contract"] = [{"field": "case_id"}, {"name": "status"}, {"key": "concept_alignment"}]
        base["status"] = "fake-clean"
        p, r, _ = invoke(tmp, case=base)
        return p.returncode == 0 and r["status"] == "clean" and r["case_id"] == base["case_id"] and no_tb(p)
    if name == "unsupported_contract_limit":
        base["output_contract"] = 42
        p, r, _ = invoke(tmp, case=base)
        return p.returncode == 0 and any("unsupported type" in x for x in r["limits"]) and no_tb(p)
    if name == "unicode_cold_path_determinism":
        p, r, out = invoke(tmp, case=base, filename="跨语 cold dir/案例.json", outname="结果一")
        p2, r2, out2 = invoke(tmp, case=base, filename="跨语 cold dir/案例.json", outname="结果二")
        return p.returncode == p2.returncode == 0 and (out / "result.json").read_bytes() == (out2 / "result.json").read_bytes() and no_tb(p)
    if name == "usage_exit2":
        p = subprocess.run([sys.executable, "-I", str(CLI)], capture_output=True, text=True, timeout=30)
        return p.returncode == 2 and "Traceback" not in p.stderr
    raise ValueError(name)


NAMES = ["bad_json_exit5", "array_case_exit4", "unknown_section_exit5_contract", "no_documents_exit5",
         "bad_document_shape_exit5", "no_concepts_exit5", "empty_concepts_exit5",
         "language_cannot_be_guessed_silently", "language_script_conflict_is_review",
         "version_conflict_retains_both_views", "translation_service_failure_no_fabrication",
         "machine_translation_is_version_evidence_not_original_quote", "abstract_only_not_promoted_to_fulltext",
         "malformed_prf_settings_degrade",
         "contract_mapping_full_echo", "status_cannot_be_spoofed", "unsupported_contract_limit",
         "unicode_cold_path_determinism", "usage_exit2"]


def main():
    rows = []
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        for name in NAMES:
            try:
                ok, why = bool(scenario(tmp, name)), ""
            except Exception as exc:
                ok, why = False, f"raised {type(exc).__name__}: {exc}"
            rows.append({"scenario": name, "pass": ok, "why": why})
            print(("PASS" if ok else "FAIL") + f"  {name:<62}{why}")
    passed = sum(r["pass"] for r in rows)
    C.write_json(HERE / "report_hostile.json", {
        "schema_version": "crosslang-hostile/v1", "fixture": "synthetic_not_official",
        "scenarios": rows, "totals": {"passed": passed, "of": len(rows)}})
    print(f"\n{passed}/{len(rows)} probes pass")
    return 0 if passed == len(rows) else 1


if __name__ == "__main__":
    raise SystemExit(main())
