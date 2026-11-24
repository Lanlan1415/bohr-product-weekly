"""Third-round cold-copy, Chinese/cross-language, human-group and replay smoke."""
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
        cli = cold / "scripts" / "screening_cli.py"

        def check(name, fn):
            try:
                ok, why = bool(fn()), ""
            except Exception as exc:
                ok, why = False, f"{type(exc).__name__}: {exc}"
            rows.append({"scenario": name, "pass": ok, "why": why})
            print(("PASS" if ok else "FAIL") + f"  {name:<50}" + why)

        def cold_example_replay():
            p1, r1 = run(cli, cold / "examples" / "case.json", tmp / "example-a", tmp)
            p2, r2 = run(cli, cold / "examples" / "case.json", tmp / "example-b", tmp)
            summary = r1["candidate_set_summary"]
            return (p1.returncode == p2.returncode == 3 and (summary["include"], summary["pending"], summary["exclude"]) == (2, 2, 4)
                    and len(r1["screening_log"]) == 9 and hashes(tmp / "example-a") == hashes(tmp / "example-b"))
        check("cold_copy_nine_rows_full_replay", cold_example_replay)

        chinese = tmp / "chinese.json"
        chinese.write_text(json.dumps({
            "case_id": "chinese-screening-smoke", "research_question": "增材制造的凝固与微观组织",
            "records": [{"id": "zh-synthetic", "title": "增材制造冷却行为研究",
                         "abstract": "明确标注的中文合成筛选文本：冷却速率与凝固决定微观组织。",
                         "authors": ["合成测试作者"], "year": 2024, "journal": "合成筛选记录", "language": "zh"}],
            "screening_protocol": {"inclusion_criteria": [
                {"id": "INC-OBJECT", "terms": ["增材制造", "additive manufacturing", "3D打印"]},
                {"id": "INC-EVIDENCE", "any": ["冷却速率", "凝固", "微观组织", "microstructure"]}],
                "exclusion_criteria": [], "human_review_thresholds": {"confidence_below": 0.7, "tie_margin": 0}},
            "output_contract": ["检索结果", "证据记录", "状态说明"]}, ensure_ascii=False), encoding="utf-8-sig")

        def chinese_screening():
            proc, result = run(cli, chinese, tmp / "zh-out", tmp)
            row = result["ranked_included"][0]
            return (proc.returncode == 3 and row["final_decision"] == "include" and
                    all(c["matched"] for c in row["criteria_matches"]) and any("凝固" in (e["quote"] or "")
                        for c in row["criteria_matches"] for e in c["evidence"]) and
                    row["metadata"]["doi"] is None and "Traceback" not in proc.stdout + proc.stderr)
        check("pure_chinese_criteria_and_verbatim_evidence", chinese_screening)

        def english_crosslang_from_same_protocol():
            value = json.loads(chinese.read_text(encoding="utf-8-sig"))
            value["case_id"] = "english-crosslang-screening"
            value["research_question"] = "additive manufacturing solidification microstructure"
            value["records"] = [{"id": "en-synthetic", "title": "Additive manufacturing solidification",
                                 "abstract": "Synthetic cross-language text: solidification determines microstructure.",
                                 "authors": ["Synthetic Author"], "year": 2024, "journal": "Synthetic fixture", "language": "en"}]
            case = tmp / "en.json"
            case.write_text(json.dumps(value), encoding="utf-8")
            proc, result = run(cli, case, tmp / "en-out", tmp)
            return proc.returncode == 3 and result["ranked_included"][0]["final_decision"] == "include" \
                and all(c["matched"] for c in result["ranked_included"][0]["criteria_matches"])
        check("english_cross_language_same_protocol", english_crosslang_from_same_protocol)

        public = json.loads((cold / "examples" / "public_real_records.json").read_text(encoding="utf-8"))
        duplicate = tmp / "duplicate.json"
        second = dict(public[0], id="second-duplicate-export")
        duplicate.write_text(json.dumps({
            "case_id": "duplicate-label-smoke", "research_question": "protein folding", "records": [public[0], second],
            "screening_protocol": {"inclusion_criteria": [{"id": "INC", "terms": ["protein"]}], "exclusion_criteria": []},
            "review_decisions": [{"record_id": "second-duplicate-export", "decision": "exclude",
                                  "reviewer": "explicit-fixture-reviewer", "rationale": "explicit duplicate-member label fixture"}],
            "output_contract": ["检索结果", "证据记录", "状态说明"]}), encoding="utf-8")

        def duplicate_member_label():
            proc, result = run(cli, duplicate, tmp / "duplicate-out", tmp)
            history = result["human_review_history"][0]
            return (proc.returncode == 3 and history["record_id"] == "second-duplicate-export" and
                    result["excluded_records"][0]["final_decision"] == "exclude" and
                    result["change_records"][0]["after"] == "exclude" and len(result["screening_log"]) == 2 and
                    "Traceback" not in proc.stdout + proc.stderr)
        check("duplicate_member_label_group_consistency", duplicate_member_label)

        zero = tmp / "zero.json"
        zero.write_text(json.dumps({"case_id": "zero-retained", "research_question": "protein folding",
                                    "records": [{"id": "unrelated", "title": "Unrelated fixture", "abstract": "nothing relevant",
                                                 "authors": ["Synthetic"], "year": 2024, "journal": "Synthetic", "language": "en"}],
                                    "screening_protocol": {"inclusion_criteria": [{"id": "INC", "terms": ["protein"]}]}}), encoding="utf-8")

        def zero_retained():
            proc, result = run(cli, zero, tmp / "zero-out", tmp)
            return proc.returncode == 3 and result["candidate_set_summary"]["include"] == 0 \
                and result["candidate_set_summary"]["exclude"] == 1 and result["candidate_set_summary"]["remote_hit_count"] is None
        check("zero_retained_not_remote_or_blocked", zero_retained)

        def cold_import():
            code = "import sys;sys.dont_write_bytecode=True;sys.path.insert(0,sys.argv[1]);import retrieval_common,screening_engine;print(screening_engine.SCHEMA_VERSION)"
            proc = subprocess.run([sys.executable, "-B", "-I", "-X", "utf8", "-c", code, str(cold / "scripts")],
                                  cwd=tmp, env=ENV, capture_output=True, text=True, timeout=120)
            return proc.returncode == 0 and proc.stdout.strip() == "screening-rank/v2" and not list(cold.rglob("*.pyc"))
        check("cold_import_no_private_paths_or_pyc", cold_import)

        clean = tmp / "clean.json"
        clean.write_text(json.dumps({"case_id": "clean-screening-smoke", "research_question": "protein folding",
                                     "records": [public[0]],
                                     "screening_protocol": {"inclusion_criteria": [{"id": "INC", "terms": ["protein"]}],
                                                            "exclusion_criteria": [],
                                                            "human_review_thresholds": {"confidence_below": 0.7, "tie_margin": 0}},
                                     "output_contract": ["检索结果", "证据记录", "状态说明"]}), encoding="utf-8")

        def clean_replay():
            proc, result = run(cli, clean, tmp / "clean-out", tmp)
            return (proc.returncode == 0 and result["status"] == "clean" and result["findings"] == [] and
                    all((tmp / "clean-out" / name).exists() for name in result["deliverables"]) and
                    all(hashlib.sha256((tmp / "clean-out" / a["path"]).read_bytes()).hexdigest() == a["sha256"]
                        for a in result["artifacts"]) and "Traceback" not in proc.stdout + proc.stderr)
        check("clean_real_metadata_exit0_artifacts_hashes", clean_replay)

    passed = sum(x["pass"] for x in rows)
    report = {"schema_version": "screening-rank-v2-smoke/v1", "official_score": False,
              "scenarios": rows, "totals": {"passed": passed, "of": len(rows)}}
    (HERE / "report_filter_rank_smoke.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"\n{passed}/{len(rows)} smoke scenarios pass")
    return 0 if passed == len(rows) else 1


if __name__ == "__main__":
    raise SystemExit(main())
