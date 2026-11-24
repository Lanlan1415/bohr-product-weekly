"""Third-round real-feeling cross-language, cold-copy and determinism smoke."""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
PACKAGE = HERE.parent
ENV = dict(os.environ, PYTHONDONTWRITEBYTECODE="1", PYTHONUTF8="1")


def run(cli, case, out, cwd):
    proc = subprocess.run([sys.executable, "-B", "-I", "-X", "utf8", str(cli), "--case", str(case), "--out", str(out)],
                          cwd=cwd, env=ENV, capture_output=True, text=True, timeout=120)
    path = out / "result.json"
    return proc, json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


def hashes(out):
    return {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in out.iterdir() if p.is_file()}


def main():
    rows = []
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        cold = tmp / "cold"
        shutil.copytree(PACKAGE, cold, ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "_run*"))
        cli = cold / "scripts" / "question_cli.py"

        def check(name, fn):
            try:
                ok, why = bool(fn()), ""
            except Exception as exc:
                ok, why = False, f"{type(exc).__name__}: {exc}"
            rows.append({"scenario": name, "pass": ok, "why": why})
            print(("PASS" if ok else "FAIL") + f"  {name:<48}" + why)

        def cold_example_replay():
            p1, r1 = run(cli, cold / "examples" / "case.json", tmp / "example-a", tmp)
            p2, r2 = run(cli, cold / "examples" / "case.json", tmp / "example-b", tmp)
            s1 = next(s for s in r1["subquestion_results"] if s["subquestion_id"] == "S01")
            s3 = next(s for s in r1["subquestion_results"] if s["subquestion_id"] == "S03")
            gap = next(s for s in r1["subquestion_results"] if s["subquestion_id"] == "S05")
            return (p1.returncode == p2.returncode == 3 and s1["status"] == "answered_with_conflicts_human_review" and
                    s3["status"] == "answered" and gap["direct_answer_work_ids"] == [] and
                    gap["partial_diagnostic_work_ids"] and hashes(tmp / "example-a") == hashes(tmp / "example-b"))
        check("cold_copy_full_example_idempotent", cold_example_replay)

        def english_cross_language():
            value = json.loads((cold / "examples" / "case.json").read_text(encoding="utf-8"))
            value["case_id"] = "english-crosslang-smoke"
            value["research_question"] = "For solid-state electrolytes, how do grain boundaries affect ionic conductivity and how is interfacial resistance measured by impedance spectroscopy?"
            value["concepts"] = [c for c in value["concepts"] if c["id"] in {"object", "grain", "conductivity", "impedance", "interface"}]
            value["records"] = json.loads((cold / "examples" / "records.json").read_text(encoding="utf-8"))
            value.pop("records_path", None)
            case = tmp / "english.json"
            case.write_text(json.dumps(value), encoding="utf-8")
            proc, result = run(cli, case, tmp / "english-out", tmp)
            return (proc.returncode == 3 and len(result["subquestion_results"]) == 4 and
                    any(e["record_id"] == "en-interface-02" for s in result["subquestion_results"] for e in s["direct_evidence"]) and
                    "Traceback" not in proc.stdout + proc.stderr)
        check("english_question_cross_language_execution", english_cross_language)

        def chinese_only():
            value = json.loads((cold / "examples" / "case.json").read_text(encoding="utf-8"))
            value["case_id"] = "chinese-only-smoke"
            value["research_question"] = "固态电解质的晶界如何影响离子电导率？"
            value["concepts"] = [c for c in value["concepts"] if c["id"] in {"object", "grain", "conductivity"}]
            value["records"] = json.loads((cold / "examples" / "records.json").read_text(encoding="utf-8"))
            value.pop("records_path", None)
            case = tmp / "chinese.json"
            case.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8-sig")
            proc, result = run(cli, case, tmp / "chinese-out", tmp)
            return (proc.returncode == 3 and len(result["subquestion_results"]) == 2 and
                    any(e["record_id"] == "zh-grain-01" for s in result["subquestion_results"] for e in s["direct_evidence"]) and
                    "Traceback" not in proc.stdout + proc.stderr)
        check("pure_chinese_bom_question_execution", chinese_only)

        def reverse_dependencies():
            public = json.loads((cold / "examples" / "public_real_records.json").read_text(encoding="utf-8"))
            value = {"case_id": "dependency-smoke", "records": public,
                     "subquestions": [{"id": "S2", "question": "protein", "query": {"all": ["protein"]}, "depends_on": ["S1"]},
                                      {"id": "S1", "question": "attention", "query": {"all": ["attention"]}}],
                     "output_contract": ["检索结果", "证据记录", "状态说明"]}
            case = tmp / "deps.json"
            case.write_text(json.dumps(value), encoding="utf-8")
            proc, result = run(cli, case, tmp / "deps-out", tmp)
            return (proc.returncode == 3 and [q["subquestion_id"] for q in result["query_log"]] == ["S1", "S2"] and
                    len(result["candidate_set"]) == 2 and "Traceback" not in proc.stdout + proc.stderr)
        check("reverse_declared_queries_topological_execution", reverse_dependencies)

        def zero():
            public = json.loads((cold / "examples" / "public_real_records.json").read_text(encoding="utf-8"))
            value = {"case_id": "zero-smoke", "records": public,
                     "subquestions": [{"id": "Q", "question": "zero", "query": {"all": ["no-match-token-zzzz"]}}]}
            case = tmp / "zero.json"
            case.write_text(json.dumps(value), encoding="utf-8")
            proc, result = run(cli, case, tmp / "zero-out", tmp)
            return proc.returncode == 3 and result["candidate_set"] == [] and len(result["query_log"]) == 1 \
                and result["query_log"][0]["remote_hit_count"] is None and "Traceback" not in proc.stdout + proc.stderr
        check("zero_hit_no_implicit_broadening", zero)

        def cold_import():
            code = "import sys;sys.dont_write_bytecode=True;sys.path.insert(0,sys.argv[1]);import retrieval_common,question_engine;print(question_engine.SCHEMA_VERSION)"
            proc = subprocess.run([sys.executable, "-B", "-I", "-X", "utf8", "-c", code, str(cold / "scripts")],
                                  cwd=tmp, env=ENV, capture_output=True, text=True, timeout=120)
            return proc.returncode == 0 and proc.stdout.strip() == "question-search/v2" and not list(cold.rglob("*.pyc"))
        check("cold_import_no_private_paths_or_pyc", cold_import)

        public = json.loads((cold / "examples" / "public_real_records.json").read_text(encoding="utf-8"))
        clean = tmp / "clean.json"
        clean.write_text(json.dumps({"case_id": "clean-smoke", "research_question": "protein structure prediction",
                                     "records": [public[0]], "output_contract": ["检索结果", "证据记录", "状态说明"]}), encoding="utf-8")

        def clean_artifacts():
            proc, result = run(cli, clean, tmp / "clean-out", tmp)
            return (proc.returncode == 0 and result["findings"] == [] and
                    all((tmp / "clean-out" / name).exists() for name in result["deliverables"]) and
                    all(hashlib.sha256((tmp / "clean-out" / a["path"]).read_bytes()).hexdigest() == a["sha256"]
                        for a in result["artifacts"]) and "Traceback" not in proc.stdout + proc.stderr)
        check("clean_real_metadata_exit0_and_hashes", clean_artifacts)

    passed = sum(x["pass"] for x in rows)
    report = {"schema_version": "question-search-v2-smoke/v1", "official_score": False,
              "scenarios": rows, "totals": {"passed": passed, "of": len(rows)}}
    (HERE / "report_question_smoke.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"\n{passed}/{len(rows)} smoke scenarios pass")
    return 0 if passed == len(rows) else 1


if __name__ == "__main__":
    raise SystemExit(main())
