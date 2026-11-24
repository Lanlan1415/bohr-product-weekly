"""Third-round real-feeling smoke, cold-copy imports and determinism.

python -B -I -X utf8 scripts/smoke_academic_v2.py
Uses public-author metadata and explicitly synthetic no-DOI Chinese text only.
"""
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
    proc = subprocess.run([sys.executable, "-B", "-I", "-X", "utf8", str(cli), "--case", str(case),
                           "--out", str(out)], cwd=cwd, env=ENV, capture_output=True, text=True, timeout=120)
    path = out / "result.json"
    result = json.loads(path.read_text(encoding="utf-8")) if path.exists() else None
    return proc, result


def hashes(out):
    return {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in out.iterdir() if p.is_file()}


def main():
    rows = []
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        cold = tmp / "cold-package"
        shutil.copytree(PACKAGE, cold, ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "_run*"))
        cli = cold / "scripts" / "academic_cli.py"

        def check(name, fn):
            try:
                ok, why = bool(fn()), ""
            except Exception as exc:
                ok, why = False, f"{type(exc).__name__}: {exc}"
            rows.append({"scenario": name, "pass": ok, "why": why})
            print(("PASS" if ok else "FAIL") + f"  {name:<46}" + why)

        def real_example_two_dirs():
            p1, r1 = run(cli, cold / "examples" / "case.json", tmp / "example-a", tmp)
            p2, r2 = run(cli, cold / "examples" / "case.json", tmp / "example-b", tmp)
            return (p1.returncode == p2.returncode == 3 and
                    [x["record_id"] for x in r1["candidate_set"]] == ["crossref-alphafold", "datacite-attention"] and
                    hashes(tmp / "example-a") == hashes(tmp / "example-b") and
                    "Traceback" not in p1.stdout + p1.stderr + p2.stdout + p2.stderr)
        check("cold_copy_real_metadata_cross_language_deterministic", real_example_two_dirs)

        chinese_case = tmp / "chinese.json"
        chinese_case.write_text(json.dumps({
            "case_id": "chinese-only-smoke", "research_question": "固态电解质晶界如何影响离子电导率？",
            "records": [{"id": "zh-synthetic", "title": "晶界工程提升固态电解质离子电导率",
                         "abstract": "这是明确标注的中文合成回归文本；研究晶界与离子输运。",
                         "authors": ["合成测试作者"], "year": 2024, "journal": "合成测试记录", "language": "zh"}],
            "output_contract": ["检索结果", "证据记录", "状态说明"]}, ensure_ascii=False), encoding="utf-8")
        check("pure_chinese_question_and_verbatim_evidence", lambda: (
            lambda p, r: p.returncode == 3 and len(r["candidate_set"]) == 1 and
            any("晶界" in (e["quote"] or "") for e in r["candidate_set"][0]["evidence"]) and
            r["candidate_set"][0]["metadata"]["doi"] is None and
            "Traceback" not in p.stdout + p.stderr)(*run(cli, chinese_case, tmp / "zh-out", tmp)))

        english_case = tmp / "english.json"
        english_case.write_text(json.dumps({
            "case_id": "english-crosslang-smoke", "research_question": "Attention mechanisms for protein structure prediction",
            "records": json.loads((cold / "examples" / "records.json").read_text(encoding="utf-8")),
            "output_contract": ["检索结果", "证据记录", "状态说明"]}), encoding="utf-8")
        check("english_question_cross_language_seed_expansion", lambda: (
            lambda p, r: p.returncode == 3 and len(r["candidate_set"]) == 2 and
            {c["concept_id"] for c in r["query_plan"]["concepts"]} >= {"attention", "protein-structure-prediction"} and
            all(s["execution_status"] == "planned_not_executed" for s in r["query_plan"]["source_queries"]) and
            "Traceback" not in p.stdout + p.stderr)(*run(cli, english_case, tmp / "en-out", tmp)))

        zero_case = tmp / "zero.json"
        zero_case.write_text(json.dumps({"case_id": "zero-smoke", "query": {"all": ["missing-token-zzzz"]},
                                         "records": json.loads((cold / "examples" / "records.json").read_text(encoding="utf-8"))}), encoding="utf-8")
        check("zero_hit_not_padded_or_called_remote", lambda: (
            lambda p, r: p.returncode == 3 and r["candidate_set"] == [] and r["状态说明"]["空结果"] and
            all(q["remote_hit_count"] is None for q in r["query_log"]) and
            "Traceback" not in p.stdout + p.stderr)(*run(cli, zero_case, tmp / "zero-out", tmp)))

        def cold_import_every_engine_module():
            code = "import sys;sys.dont_write_bytecode=True;sys.path.insert(0,sys.argv[1]);import retrieval_common,academic_engine;print(retrieval_common.SCHEMA_VERSION)"
            proc = subprocess.run([sys.executable, "-B", "-I", "-X", "utf8", "-c", code, str(cold / "scripts")],
                                  cwd=tmp, env=ENV, capture_output=True, text=True, timeout=120)
            return (proc.returncode == 0 and proc.stdout.strip() == "source-bound-retrieval/v2" and
                    not list(cold.rglob("*.pyc")))
        check("cold_import_no_private_path_or_bytecode", cold_import_every_engine_module)

        clean_case = tmp / "clean.json"
        clean_case.write_text(json.dumps({"case_id": "clean-smoke", "research_question": "蛋白质结构预测",
                                          "records": [json.loads((cold / "examples" / "records.json").read_text(encoding="utf-8"))[0]],
                                          "output_contract": ["检索结果", "证据记录", "状态说明"]}, ensure_ascii=False), encoding="utf-8-sig")
        check("clean_case_exit0_and_all_artifacts", lambda: (
            lambda p, r: p.returncode == 0 and r["status"] == "clean" and r["findings"] == [] and
            all((tmp / "clean-out" / name).exists() for name in r["deliverables"]) and
            "Traceback" not in p.stdout + p.stderr)(*run(cli, clean_case, tmp / "clean-out", tmp)))

        def recompute_artifact_hashes():
            proc, result = run(cli, clean_case, tmp / "clean-out", tmp)
            return all(hashlib.sha256((tmp / "clean-out" / a["path"]).read_bytes()).hexdigest() == a["sha256"]
                       for a in result["artifacts"])
        check("reported_artifact_hashes_recomputable", recompute_artifact_hashes)

    passed = sum(x["pass"] for x in rows)
    report = {"schema_version": "academic-search-v2-smoke/v1", "official_score": False,
              "scenarios": rows, "totals": {"passed": passed, "of": len(rows)}}
    (HERE / "report_academic_smoke.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"\n{passed}/{len(rows)} smoke scenarios pass")
    return 0 if passed == len(rows) else 1


if __name__ == "__main__":
    raise SystemExit(main())
