"""Deterministic contract/hostility checks for the primary Introduction CLI."""
from __future__ import annotations

import copy
import hashlib
import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / "scripts" / "introcrun.py"
EXAMPLE = ROOT / "examples" / "spec.json"


def base():
    return json.loads(EXAMPLE.read_text(encoding="utf-8"))


def invoke(spec, work, name, raw=None):
    target = work / name
    target.mkdir()
    path = target / "spec.json"
    path.write_text(raw if raw is not None else json.dumps(spec, ensure_ascii=False), encoding="utf-8")
    out = target / "out"
    proc = subprocess.run([sys.executable, "-I", str(CLI), "--spec", str(path), "--out", str(out)],
                          capture_output=True, text=True, cwd=target, timeout=60)
    result_path = out / "result.json"
    result = json.loads(result_path.read_text(encoding="utf-8")) if result_path.exists() else {}
    assert "Traceback" not in proc.stdout + proc.stderr, (name, proc.stdout, proc.stderr)
    return proc, result, out


def main():
    checks = []
    with tempfile.TemporaryDirectory(prefix="introcrun-bench-") as tmp:
        work = Path(tmp)

        def check(name, condition, detail=""):
            checks.append({"name": name, "passed": bool(condition), "detail": detail})
            print(f"{'PASS' if condition else 'FAIL'}  {name} {detail if not condition else ''}")

        proc, result, out = invoke(base(), work, "clean")
        check("clean_full_workflow", proc.returncode == 0 and not result["findings"], proc.stdout + proc.stderr)
        check("clean_artifacts", all((out / name).is_file() and (out / name).stat().st_size > 0
                                   for name in ("intro_related_work.md", "comparison_matrix.csv", "result.json")))
        check("contract_fields_and_bulk_values", result["case_id"] == "intro-synthetic-clean-001" and
              result["evidence_map"] == base()["evidence_map"] and
              result["version_boundary"] == base()["version_boundary"] and
              set(result["output_contract_fields"]) == set(base()["output_contract"]))
        matrix = (out / "comparison_matrix.csv").read_text(encoding="utf-8")
        check("nearest_dimensions_in_csv", all(field in matrix for field in
              ("problem_setting", "method_route", "data_evaluation", "scope")))
        check("explicit_disclaimer_is_clean", not any("NOVELTY" in f["code"] for f in result["findings"]))

        proc, result, _ = invoke(None, work, "bad_json", "{broken")
        check("bad_json_refused", proc.returncode == 5 and result["findings"][0]["code"] == "intro.spec_unreadable")
        proc, result, _ = invoke(None, work, "array", "[]")
        check("array_refused", proc.returncode == 5 and result["case_id"] is None and
              result["findings"][0]["code"] == "intro.spec_not_object")
        proc, result, _ = invoke(None, work, "missing", raw="")
        check("missing_content_refused", proc.returncode == 5 and result["status"] == "undetermined")

        spec = base()
        spec["section"] = "format_template"
        proc, result, _ = invoke(spec, work, "wrong_track")
        check("wrong_track_structured_refusal", proc.returncode == 5 and
              result["findings"][0]["code"] == "intro.section_unknown" and
              result["case_id"] == spec["case_id"] and
              result["evidence_map"] == spec["evidence_map"] and
              "version_boundary" in result and "limits" in result)

        spec = base()
        spec["groups"][0]["papers"][0]["anchors"][2]["quote"] = "原文并不存在的句子"
        proc, result, _ = invoke(spec, work, "fabricated_quote")
        check("fabricated_quote_blocked", proc.returncode == 4 and
              any(f["code"] == "INTRO_QUOTE_NOT_IN_SOURCE" for f in result["findings"]), proc.stdout)

        spec = base()
        del spec["nearest_works"][0]["scope"]
        proc, result, _ = invoke(spec, work, "missing_dimension")
        check("missing_closest_dimension_blocked", any(f["code"] == "INTRO_NEAREST_DIMENSION_MISSING"
              for f in result["findings"]), proc.stdout)

        spec = base()
        spec["contributions"][0]["scope"] = ""
        proc, result, _ = invoke(spec, work, "missing_scope")
        check("missing_contribution_scope_blocked", any(f["code"] == "INTRO_CONTRIBUTION_SCOPE_MISSING"
              for f in result["findings"]), proc.stdout)

        spec = base()
        spec["contributions"][0]["claim"] = "我们首次提出并首创该统一异常检测理论"
        proc, result, _ = invoke(spec, work, "novelty_hype")
        check("unsupported_first_claim_blocked", proc.returncode == 4 and
              any(f["code"] == "INTRO_NOVELTY_OVERCLAIM" for f in result["findings"]), proc.stdout)

        spec = base()
        spec["nearest_works"][0]["comparison_status"] = "provisional"
        spec["nearest_works"][0]["reason"] = "仅有摘要可核对初步差异，方法细节待全文复核"
        for paper in spec["groups"][0]["papers"]:
            paper["evidence_status"] = "abstract_only"
            paper["downgrade_reason"] = "只有摘要，无法声称全文逐段核验"
        proc, result, _ = invoke(spec, work, "abstract_only")
        check("abstract_only_provisional_review", proc.returncode == 3 and
              any(f["code"] == "INTRO_EVIDENCE_LIMITED" for f in result["findings"]) and
              not any(f["code"] == "INTRO_NEAREST_COMPARISON_UNVERIFIED" for f in result["findings"]), proc.stdout)

        spec = base()
        spec["citation_labels"]["liu2021"] = "Citation absent from draft"
        proc, result, _ = invoke(spec, work, "missing_citation")
        check("matrix_citation_must_reach_draft", any(f["code"] == "INTRO_MATRIX_CITATION_NOT_IN_DRAFT"
              for f in result["findings"]), proc.stdout)

        spec = base()
        spec["gap_chain"][1]["marker"] = "未标明判断"
        proc, result, _ = invoke(spec, work, "hidden_author_judgment")
        check("hidden_author_judgment_flagged", any(f["code"] == "INTRO_AUTHOR_JUDGMENT_HIDDEN"
              for f in result["findings"]), proc.stdout)

        deterministic = base()
        _, first, out_a = invoke(deterministic, work, "idem_a")
        _, second, out_b = invoke(deterministic, work, "idem_b")
        digest_a = {name: hashlib.sha256((out_a / name).read_bytes()).hexdigest()
                    for name in ("result.json", "intro_related_work.md", "comparison_matrix.csv")}
        digest_b = {name: hashlib.sha256((out_b / name).read_bytes()).hexdigest() for name in digest_a}
        check("byte_determinism", digest_a == digest_b)
        check("idempotent_clean_repeat", first == second and first["status"] == "clean")

    passed = sum(item["passed"] for item in checks)
    print(json.dumps({"suite": "introcrun_contract", "passed": passed,
                      "total": len(checks), "failed": len(checks) - passed}, ensure_ascii=False))
    return 0 if passed == len(checks) else 1


if __name__ == "__main__":
    raise SystemExit(main())
