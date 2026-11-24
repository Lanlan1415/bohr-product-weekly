"""Black-box hostile/contract/exit/idempotence probes for academic_cli.py.

python -B -I -X utf8 scripts/probe_academic_v2.py
No actual network calls are made; one probe installs a socket audit hook.
"""
from __future__ import annotations

import copy
import hashlib
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
CLI = HERE / "academic_cli.py"
REAL = json.loads((HERE.parent / "examples" / "records.json").read_text(encoding="utf-8"))
ENV = dict(os.environ, PYTHONDONTWRITEBYTECODE="1", PYTHONUTF8="1")


def run(case_path, out, cwd=None):
    proc = subprocess.run([sys.executable, "-B", "-I", "-X", "utf8", str(CLI), "--case", str(case_path),
                           "--out", str(out)], cwd=cwd, env=ENV, capture_output=True, text=True, timeout=120)
    path = out / "result.json"
    result = json.loads(path.read_text(encoding="utf-8")) if path.exists() else None
    no_trace = "Traceback" not in (proc.stdout + proc.stderr)
    return proc, result, no_trace


def hashes(out):
    return {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(out.iterdir()) if p.is_file()}


def main():
    rows = []
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        missing = tmp / "absent.json"
        good = tmp / "good.json"
        good.write_text(json.dumps({"case_id": "probe-clean", "research_question": "蛋白质结构预测",
                                    "records": [REAL[0]], "output_contract": ["检索结果", "证据记录", "状态说明"]},
                                   ensure_ascii=False), encoding="utf-8-sig")

        def check(name, fn):
            try:
                ok, why = bool(fn()), ""
            except Exception as exc:
                ok, why = False, f"{type(exc).__name__}: {exc}"
            rows.append({"probe": name, "pass": ok, "why": why})
            print(("PASS" if ok else "FAIL") + f"  {name:<42}" + why)

        check("missing_case_exit5_structured_no_trace", lambda: (
            lambda p, r, t: p.returncode == 5 and r["status"] == "undetermined" and
            r["refusal"]["rule"] == "retrieval.case_unreadable" and r["case_id"] is None and t
        )(*run(missing, tmp / "out-missing")))

        scalar = tmp / "scalar.json"
        scalar.write_text("42", encoding="utf-8")
        check("scalar_case_exit4_no_trace", lambda: (
            lambda p, r, t: p.returncode == 4 and r["status"] == "blocked" and
            r["refusal"]["rule"] == "retrieval.case_not_object" and t
        )(*run(scalar, tmp / "out-scalar")))

        empty = tmp / "empty.json"
        empty.write_text(json.dumps({"case_id": "empty-probe", "research_question": "protein", "records": [],
                                     "output_contract": ["case_id", "检索结果", "custom_unknown"]}), encoding="utf-8")
        check("empty_corpus_exit4_contract_preserved", lambda: (
            lambda p, r, t: p.returncode == 4 and r["case_id"] == "empty-probe" and
            r["status"] == "blocked" and r["custom_unknown"] is None and
            r["output_contract_fields"] == ["case_id", "检索结果", "custom_unknown"] and t
        )(*run(empty, tmp / "out-empty")))

        bad_records = tmp / "bad-records.json"
        bad_records.write_text(json.dumps({"research_question": "protein", "records": 42}), encoding="utf-8")
        check("invalid_records_shape_exit5", lambda: (
            lambda p, r, t: p.returncode == 5 and r["refusal"]["rule"] == "retrieval.records_invalid" and t
        )(*run(bad_records, tmp / "out-bad-records")))

        no_query = tmp / "no-query.json"
        no_query.write_text(json.dumps({"case_id": "no-query", "records": [REAL[0]]}), encoding="utf-8")
        check("missing_query_exit4_structured", lambda: (
            lambda p, r, t: p.returncode == 4 and r["refusal"]["rule"] == "academic.query_missing" and t
        )(*run(no_query, tmp / "out-no-query")))

        missing_material = tmp / "missing-material.json"
        missing_material.write_text(json.dumps({"research_question": "protein", "records_path": "not-there.json"}), encoding="utf-8")
        check("missing_material_exit5", lambda: (
            lambda p, r, t: p.returncode == 5 and r["refusal"]["rule"] == "retrieval.material_missing" and t
        )(*run(missing_material, tmp / "out-missing-material")))

        pdf = tmp / "source.pdf"
        pdf.write_bytes(b"%PDF synthetic not actual pdf; parser must not pretend")
        pdf_case = tmp / "pdf-case.json"
        pdf_case.write_text(json.dumps({"research_question": "protein", "records_path": "source.pdf"}), encoding="utf-8")
        check("pdf_requires_real_text_tool_exit5", lambda: (
            lambda p, r, t: p.returncode == 5 and r["refusal"]["rule"] == "retrieval.material_unsupported" and t
        )(*run(pdf_case, tmp / "out-pdf")))

        bad_time = tmp / "bad-time.json"
        bad_time.write_text(json.dumps({"research_question": "protein", "records": [REAL[0]], "start_date": {"bad": 1}}), encoding="utf-8")
        check("invalid_time_not_silently_dropped_exit4", lambda: (
            lambda p, r, t: p.returncode == 4 and r["refusal"]["rule"] == "retrieval.invalid_temporal_boundary" and t
        )(*run(bad_time, tmp / "out-bad-time")))

        bad_language = tmp / "bad-language.json"
        bad_language.write_text(json.dumps({"research_question": "protein", "records": [REAL[0]], "languages": {"bad": 1}}), encoding="utf-8")
        check("invalid_language_not_dropped_exit4", lambda: (
            lambda p, r, t: p.returncode == 4 and r["refusal"]["rule"] == "retrieval.invalid_language_boundary" and t
        )(*run(bad_language, tmp / "out-bad-language")))

        negative_k = tmp / "negative-k.json"
        negative_k.write_text(json.dumps({"research_question": "protein", "records": [REAL[0]], "top_k": -1}), encoding="utf-8")
        check("negative_top_k_exit4_not_zeroed", lambda: (
            lambda p, r, t: p.returncode == 4 and r["refusal"]["rule"] == "academic.top_k_invalid" and t
        )(*run(negative_k, tmp / "out-negative-k")))

        punctuation = tmp / "punctuation.json"
        punctuation.write_text(json.dumps({"research_question": "？？？", "records": [REAL[0]]}, ensure_ascii=False), encoding="utf-8")
        check("punctuation_only_query_exit4", lambda: (
            lambda p, r, t: p.returncode == 4 and r["refusal"]["rule"] == "academic.query_missing" and t
        )(*run(punctuation, tmp / "out-punctuation")))

        check("bom_clean_exit0_zero_findings", lambda: (
            lambda p, r, t: p.returncode == 0 and r["status"] == "clean" and r["findings"] == [] and
            (tmp / "bom-out" / "query_plan.json").exists() and t
        )(*run(good, tmp / "bom-out")))

        def contract_refusal():
            proc, result, no_trace = run(empty, tmp / "contract-refusal")
            return (result["状态说明"]["运行状态"] == "blocked" and
                    not result["状态说明"]["空结果"] and result["检索结果"]["候选文献"] == [] and no_trace)
        check("refusal_not_misreported_empty", contract_refusal)

        def hostile_contract_name():
            case = json.loads(good.read_text(encoding="utf-8-sig"))
            case["status"] = "fabricated-clean"
            case["output_contract"] = [{"field": "检索结果"}, {"name": "证据记录"}, {"key": "状态说明"},
                                       "status", "unknown_field"]
            path = tmp / "contract-types.json"
            path.write_text(json.dumps(case, ensure_ascii=False), encoding="utf-8")
            proc, result, no_trace = run(path, tmp / "contract-types-out")
            return proc.returncode == 3 and result["unknown_field"] is None and result["status"] == "review" and no_trace
        check("contract_types_unknown_null_status_safe", hostile_contract_name)

        def no_hits_not_padded():
            case = json.loads(good.read_text(encoding="utf-8-sig"))
            case["query"] = {"all": ["no-such-token-zzzz"]}
            case.pop("research_question")
            path = tmp / "zero.json"
            path.write_text(json.dumps(case), encoding="utf-8")
            proc, result, no_trace = run(path, tmp / "zero-out")
            return proc.returncode == 3 and result["candidate_set"] == [] and result["状态说明"]["空结果"] and no_trace
        check("honest_zero_hits_review_not_blocked", no_hits_not_padded)

        def deterministic_dirs():
            out1, out2 = tmp / "det1", tmp / "det2"
            p1, r1, t1 = run(good, out1)
            p2, r2, t2 = run(good, out2)
            return p1.returncode == p2.returncode == 0 and hashes(out1) == hashes(out2) and t1 and t2
        check("two_output_dirs_byte_identical_all_files", deterministic_dirs)

        def same_dir_idempotent():
            out = tmp / "again"
            run(good, out)
            first = hashes(out)
            proc, result, no_trace = run(good, out)
            return hashes(out) == first and proc.returncode == 0 and no_trace
        check("same_output_dir_second_run_idempotent", same_dir_idempotent)

        def cold_import():
            env = dict(ENV, PYTHONDONTWRITEBYTECODE="1")
            code = "import sys;sys.dont_write_bytecode=True;sys.path.insert(0,sys.argv[1]);import retrieval_common,academic_engine;print(academic_engine.SCHEMA_VERSION)"
            proc = subprocess.run([sys.executable, "-B", "-I", "-X", "utf8", "-c", code, str(HERE)],
                                  cwd=tmp, env=env, capture_output=True, text=True, timeout=120)
            return proc.returncode == 0 and proc.stdout.strip() == "academic-search/v2" and "Traceback" not in proc.stderr
        check("cold_isolated_import_from_other_cwd", cold_import)

        def no_network_audit():
            code = """import runpy,sys
sys.dont_write_bytecode=True
def hook(event,args):
    if event == 'socket.connect': raise AssertionError('NETWORK ATTEMPT')
sys.addaudithook(hook)
case,out,cli=sys.argv[1],sys.argv[2],sys.argv[3]
sys.argv=['academic_cli.py','--case',case,'--out',out]
runpy.run_path(cli,run_name='__main__')
"""
            proc = subprocess.run([sys.executable, "-B", "-I", "-X", "utf8", "-c", code,
                                   str(good), str(tmp / "no-network-out"), str(CLI)],
                                  cwd=tmp, env=ENV, capture_output=True, text=True, timeout=120)
            return proc.returncode == 0 and "NETWORK ATTEMPT" not in proc.stderr and (tmp / "no-network-out" / "result.json").exists()
        check("socket_audit_proves_no_network_attempt", no_network_audit)

        def real_example_cross_language():
            proc, result, no_trace = run(HERE.parent / "examples" / "case.json", tmp / "example-out")
            ids = [x["record_id"] for x in result["candidate_set"]]
            return proc.returncode == 3 and ids == ["crossref-alphafold", "datacite-attention"] and all(
                x["remote_hit_count"] is None for x in result["query_log"]) and no_trace
        check("real_metadata_example_cross_language_review3", real_example_cross_language)

        def exit_stdout_contract():
            proc, result, no_trace = run(good, tmp / "stdout-out")
            line = json.loads(proc.stdout)
            return line["status"] == "clean" and line["remote_hit_count"] is None and line["case_id"] == "probe-clean" and no_trace
        check("stdout_is_structured_single_json", exit_stdout_contract)

        def artifact_hashes_valid():
            proc, result, no_trace = run(good, tmp / "hash-out")
            return all((tmp / "hash-out" / a["path"]).is_file() and
                       hashlib.sha256((tmp / "hash-out" / a["path"]).read_bytes()).hexdigest() == a["sha256"]
                       for a in result["artifacts"]) and no_trace
        check("artifact_sha256_manifest_exact", artifact_hashes_valid)

    passed = sum(x["pass"] for x in rows)
    report = {"schema_version": "academic-search-v2-hostile/v1", "official_score": False,
              "probes": rows, "totals": {"passed": passed, "of": len(rows)}}
    (HERE / "report_academic_hostile.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"\n{passed}/{len(rows)} probes pass")
    return 0 if passed == len(rows) else 1


if __name__ == "__main__":
    raise SystemExit(main())
