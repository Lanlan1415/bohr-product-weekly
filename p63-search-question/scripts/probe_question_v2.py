"""Black-box hostile probes for question_cli.py (no network, no official score)."""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
CLI = HERE / "question_cli.py"
ROOT = HERE.parent
PUBLIC = json.loads((ROOT / "examples" / "public_real_records.json").read_text(encoding="utf-8"))
ENV = dict(os.environ, PYTHONDONTWRITEBYTECODE="1", PYTHONUTF8="1")


def run(case, out, cwd=None):
    proc = subprocess.run([sys.executable, "-B", "-I", "-X", "utf8", str(CLI), "--case", str(case),
                           "--out", str(out)], cwd=cwd, env=ENV, capture_output=True, text=True, timeout=120)
    path = out / "result.json"
    return proc, json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


def hashes(out):
    return {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in out.iterdir() if p.is_file()}


def no_trace(proc):
    return "Traceback" not in proc.stdout + proc.stderr


def main():
    rows = []
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)

        def check(name, fn):
            try:
                ok, why = bool(fn()), ""
            except Exception as exc:
                ok, why = False, f"{type(exc).__name__}: {exc}"
            rows.append({"probe": name, "pass": ok, "why": why})
            print(("PASS" if ok else "FAIL") + f"  {name:<44}" + why)

        clean = tmp / "clean.json"
        clean.write_text(json.dumps({"case_id": "question-probe-clean", "research_question": "protein structure prediction",
                                     "records": [PUBLIC[0]], "output_contract": ["检索结果", "证据记录", "状态说明"]}), encoding="utf-8-sig")
        missing = tmp / "absent.json"
        check("missing_case_exit5_no_trace", lambda: (lambda p, r: p.returncode == 5 and r["status"] == "undetermined" and no_trace(p))(*run(missing, tmp / "missing-out")))

        scalar = tmp / "scalar.json"
        scalar.write_text("[]", encoding="utf-8")
        check("nonobject_case_exit4", lambda: (lambda p, r: p.returncode == 4 and r["status"] == "blocked" and
                                                r["refusal"]["rule"] == "retrieval.case_not_object" and no_trace(p))(*run(scalar, tmp / "scalar-out")))

        empty = tmp / "empty.json"
        empty.write_text(json.dumps({"case_id": "empty", "research_question": "protein", "records": [],
                                     "output_contract": [{"field": "检索结果"}, "unknown"]}), encoding="utf-8")
        check("empty_corpus_exit4_contract", lambda: (lambda p, r: p.returncode == 4 and r["case_id"] == "empty" and
                                                       r["unknown"] is None and r["状态说明"]["运行状态"] == "blocked" and no_trace(p))(*run(empty, tmp / "empty-out")))

        malformed = tmp / "malformed.json"
        malformed.write_text(json.dumps({"research_question": "protein", "records": {"not": "a list"}}), encoding="utf-8")
        check("records_shape_exit5", lambda: (lambda p, r: p.returncode == 5 and
                                               r["refusal"]["rule"] == "retrieval.records_invalid" and no_trace(p))(*run(malformed, tmp / "malformed-out")))

        missing_q = tmp / "no-question.json"
        missing_q.write_text(json.dumps({"records": [PUBLIC[0]]}), encoding="utf-8")
        check("no_subquestions_exit4", lambda: (lambda p, r: p.returncode == 4 and
                                                 r["refusal"]["rule"] == "question.no_subquestions" and no_trace(p))(*run(missing_q, tmp / "no-question-out")))

        punct = tmp / "punct.json"
        punct.write_text(json.dumps({"research_question": "？？？", "records": [PUBLIC[0]]}, ensure_ascii=False), encoding="utf-8")
        check("punctuation_question_exit4", lambda: (lambda p, r: p.returncode == 4 and
                                                      r["refusal"]["rule"] == "question.no_subquestions" and no_trace(p))(*run(punct, tmp / "punct-out")))

        empty_subquery = tmp / "empty-subquery.json"
        empty_subquery.write_text(json.dumps({"records": [PUBLIC[0]],
                                               "subquestions": [{"id": "S1", "question": "empty", "query": {}}]}), encoding="utf-8")
        check("empty_frozen_subquery_exit4", lambda: (lambda p, r: p.returncode == 4 and
                                                       r["refusal"]["rule"] == "question.subquery_empty" and no_trace(p))(*run(empty_subquery, tmp / "empty-subquery-out")))

        cycle = tmp / "cycle.json"
        cycle.write_text(json.dumps({"records": [PUBLIC[0]],
                                      "subquestions": [{"id": "S1", "question": "protein", "depends_on": ["S2"]},
                                                       {"id": "S2", "question": "attention", "depends_on": ["S1"]}]}), encoding="utf-8")
        check("dependency_cycle_exit4", lambda: (lambda p, r: p.returncode == 4 and
                                                  r["refusal"]["rule"] == "question.dependency_cycle" and no_trace(p))(*run(cycle, tmp / "cycle-out")))

        material = tmp / "material.json"
        material.write_text(json.dumps({"research_question": "protein", "records_path": "absent.json"}), encoding="utf-8")
        check("material_missing_exit5", lambda: (lambda p, r: p.returncode == 5 and
                                                  r["refusal"]["rule"] == "retrieval.material_missing" and no_trace(p))(*run(material, tmp / "material-out")))

        (tmp / "paper.pdf").write_bytes(b"offline binary placeholder")
        pdf = tmp / "pdf.json"
        pdf.write_text(json.dumps({"research_question": "protein", "records_path": "paper.pdf"}), encoding="utf-8")
        check("pdf_not_pretended_text_exit5", lambda: (lambda p, r: p.returncode == 5 and
                                                        r["refusal"]["rule"] == "retrieval.material_unsupported" and no_trace(p))(*run(pdf, tmp / "pdf-out")))

        time = tmp / "time.json"
        time.write_text(json.dumps({"research_question": "protein", "records": [PUBLIC[0]], "start_date": ["bad"]}), encoding="utf-8")
        check("time_boundary_type_exit4", lambda: (lambda p, r: p.returncode == 4 and
                                                    r["refusal"]["rule"] == "retrieval.invalid_temporal_boundary" and no_trace(p))(*run(time, tmp / "time-out")))

        lang = tmp / "lang.json"
        lang.write_text(json.dumps({"research_question": "protein", "records": [PUBLIC[0]], "languages": 42}), encoding="utf-8")
        check("language_boundary_type_exit4", lambda: (lambda p, r: p.returncode == 4 and
                                                        r["refusal"]["rule"] == "retrieval.invalid_language_boundary" and no_trace(p))(*run(lang, tmp / "lang-out")))

        check("clean_bom_exit0_zero_findings", lambda: (lambda p, r: p.returncode == 0 and r["status"] == "clean" and
                                                         r["findings"] == [] and no_trace(p))(*run(clean, tmp / "clean-out")))

        zero = tmp / "zero.json"
        zero.write_text(json.dumps({"case_id": "zero", "records": [PUBLIC[0]],
                                     "subquestions": [{"id": "S1", "question": "frozen", "query": {"all": ["zzzz-no-match"]}}],
                                     "output_contract": ["检索结果", "证据记录", "状态说明"]}), encoding="utf-8")
        check("zero_hits_review_not_blocked", lambda: (lambda p, r: p.returncode == 3 and r["status"] == "review" and
                                                        r["candidate_set"] == [] and r["状态说明"]["空结果"] and no_trace(p))(*run(zero, tmp / "zero-out")))
        check("refusal_not_empty_success", lambda: (lambda p, r: r["status"] == "blocked" and
                                                     not r["状态说明"]["空结果"] and r["refusal"]["rule"] == "question.dependency_cycle")(*run(cycle, tmp / "cycle-out2")))

        def contract_priority():
            value = json.loads(clean.read_text(encoding="utf-8-sig"))
            value["status"] = "fabricated-clean"
            value["output_contract"] = [{"field": "检索结果"}, {"name": "证据记录"}, {"key": "状态说明"}, "unknown", "status"]
            path = tmp / "contract.json"
            path.write_text(json.dumps(value), encoding="utf-8")
            proc, result = run(path, tmp / "contract-out")
            return proc.returncode == 3 and result["unknown"] is None and result["status"] == "review" and no_trace(proc)
        check("contract_shapes_engine_wins", contract_priority)

        def replay_directories():
            p1, r1 = run(clean, tmp / "det-a", tmp)
            p2, r2 = run(clean, tmp / "det-b", tmp)
            return p1.returncode == p2.returncode == 0 and hashes(tmp / "det-a") == hashes(tmp / "det-b") and no_trace(p1) and no_trace(p2)
        check("all_artifacts_two_dirs_identical", replay_directories)

        def replay_same():
            run(clean, tmp / "same-out")
            before = hashes(tmp / "same-out")
            proc, result = run(clean, tmp / "same-out")
            return before == hashes(tmp / "same-out") and proc.returncode == 0 and no_trace(proc)
        check("same_directory_idempotent", replay_same)

        def cold_import():
            code = "import sys;sys.dont_write_bytecode=True;sys.path.insert(0,sys.argv[1]);import retrieval_common,question_engine;print(question_engine.SCHEMA_VERSION)"
            proc = subprocess.run([sys.executable, "-B", "-I", "-X", "utf8", "-c", code, str(HERE)], cwd=tmp,
                                  env=ENV, capture_output=True, text=True, timeout=120)
            return proc.returncode == 0 and proc.stdout.strip() == "question-search/v2" and "Traceback" not in proc.stderr
        check("cold_isolated_import", cold_import)

        def socket_guard():
            code = """import runpy,sys
sys.dont_write_bytecode=True
def hook(event,args):
    if event == 'socket.connect': raise AssertionError('NETWORK ATTEMPT')
sys.addaudithook(hook)
case,out,cli=sys.argv[1],sys.argv[2],sys.argv[3]
sys.argv=['question_cli.py','--case',case,'--out',out]
runpy.run_path(cli,run_name='__main__')
"""
            proc = subprocess.run([sys.executable, "-B", "-I", "-X", "utf8", "-c", code,
                                   str(clean), str(tmp / "socket-out"), str(CLI)], cwd=tmp, env=ENV,
                                  capture_output=True, text=True, timeout=120)
            return proc.returncode == 0 and "NETWORK ATTEMPT" not in proc.stderr
        check("socket_audit_no_network", socket_guard)

        def example_scope():
            proc, result = run(ROOT / "examples" / "case.json", tmp / "example-out")
            gap = next(s for s in result["subquestion_results"] if s["subquestion_id"] == "S05")
            return proc.returncode == 3 and gap["direct_answer_work_ids"] == [] and gap["partial_diagnostic_work_ids"] \
                and all(q["remote_hit_count"] is None for q in result["query_log"]) and no_trace(proc)
        check("example_gap_not_padded_or_global", example_scope)

        def stdout_json():
            proc, result = run(clean, tmp / "stdout-out")
            line = json.loads(proc.stdout)
            return line["status"] == "clean" and line["answered"] == 1 and line["remote_hit_count"] is None and no_trace(proc)
        check("stdout_structured_json", stdout_json)

        def artifacts():
            proc, result = run(clean, tmp / "hash-out")
            return all(hashlib.sha256((tmp / "hash-out" / a["path"]).read_bytes()).hexdigest() == a["sha256"]
                       for a in result["artifacts"]) and no_trace(proc)
        check("artifact_hashes_exact", artifacts)

    passed = sum(x["pass"] for x in rows)
    report = {"schema_version": "question-search-v2-hostile/v1", "official_score": False,
              "probes": rows, "totals": {"passed": passed, "of": len(rows)}}
    (HERE / "report_question_hostile.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"\n{passed}/{len(rows)} probes pass")
    return 0 if passed == len(rows) else 1


if __name__ == "__main__":
    raise SystemExit(main())
