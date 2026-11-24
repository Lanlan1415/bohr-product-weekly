"""Hostile contract/exit/review/idempotence probes for screening_cli.py."""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
CLI = HERE / "screening_cli.py"
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
            print(("PASS" if ok else "FAIL") + f"  {name:<46}" + why)

        clean = tmp / "clean.json"
        clean.write_text(json.dumps({"case_id": "screening-probe-clean", "research_question": "protein folding",
                                     "records": [PUBLIC[0]],
                                     "screening_protocol": {"inclusion_criteria": [{"id": "INC", "terms": ["protein"]}],
                                                            "exclusion_criteria": [],
                                                            "human_review_thresholds": {"confidence_below": 0.7, "tie_margin": 0}},
                                     "output_contract": ["检索结果", "证据记录", "状态说明"]}), encoding="utf-8-sig")
        missing = tmp / "absent.json"
        check("missing_case_exit5_no_trace", lambda: (lambda p, r: p.returncode == 5 and r["status"] == "undetermined" and no_trace(p))(*run(missing, tmp / "missing-out")))

        scalar = tmp / "scalar.json"
        scalar.write_text("7", encoding="utf-8")
        check("scalar_case_exit4", lambda: (lambda p, r: p.returncode == 4 and r["status"] == "blocked" and
                                             r["refusal"]["rule"] == "retrieval.case_not_object" and no_trace(p))(*run(scalar, tmp / "scalar-out")))

        empty = tmp / "empty.json"
        empty.write_text(json.dumps({"case_id": "empty", "records": [], "research_question": "protein",
                                     "output_contract": [{"field": "检索结果"}, "unknown"]}), encoding="utf-8")
        check("empty_candidates_exit4_contract", lambda: (lambda p, r: p.returncode == 4 and r["case_id"] == "empty" and
                                                           r["unknown"] is None and r["状态说明"]["运行状态"] == "blocked" and no_trace(p))(*run(empty, tmp / "empty-out")))

        malformed = tmp / "malformed.json"
        malformed.write_text(json.dumps({"research_question": "protein", "records": {}}), encoding="utf-8")
        check("records_invalid_exit5", lambda: (lambda p, r: p.returncode == 5 and
                                                 r["refusal"]["rule"] == "retrieval.records_invalid" and no_trace(p))(*run(malformed, tmp / "malformed-out")))

        no_protocol = tmp / "no-protocol.json"
        no_protocol.write_text(json.dumps({"records": [PUBLIC[0]]}), encoding="utf-8")
        check("protocol_missing_exit4", lambda: (lambda p, r: p.returncode == 4 and
                                                  r["refusal"]["rule"] == "screening.protocol_missing" and no_trace(p))(*run(no_protocol, tmp / "no-protocol-out")))

        bad_fields = tmp / "bad-fields.json"
        bad_fields.write_text(json.dumps({"records": [PUBLIC[0]], "screening_protocol": {
            "inclusion_criteria": [{"id": "bad", "terms": ["protein"], "fields": ["imaginary"]}]}}), encoding="utf-8")
        check("criterion_bad_field_exit4", lambda: (lambda p, r: p.returncode == 4 and
                                                     r["refusal"]["rule"] == "screening.criterion_fields_invalid" and no_trace(p))(*run(bad_fields, tmp / "bad-fields-out")))

        bad_weights = json.loads(clean.read_text(encoding="utf-8-sig"))
        bad_weights["screening_protocol"]["ranking_weights"] = {"relevance": 0.9, "criteria_coverage": 0.9,
                                                                  "metadata_completeness": 0.9, "source_trace": 0.9}
        weights_case = tmp / "weights.json"
        weights_case.write_text(json.dumps(bad_weights), encoding="utf-8")
        check("ranking_weights_not_one_exit4", lambda: (lambda p, r: p.returncode == 4 and
                                                         r["refusal"]["rule"] == "screening.rank_weights_invalid" and no_trace(p))(*run(weights_case, tmp / "weights-out")))

        bad_time = json.loads(clean.read_text(encoding="utf-8-sig"))
        bad_time["start_date"] = {"bad": "time"}
        time_case = tmp / "time.json"
        time_case.write_text(json.dumps(bad_time), encoding="utf-8")
        check("invalid_time_not_dropped_exit4", lambda: (lambda p, r: p.returncode == 4 and
                                                          r["refusal"]["rule"] == "retrieval.invalid_temporal_boundary" and no_trace(p))(*run(time_case, tmp / "time-out")))

        bad_lang = json.loads(clean.read_text(encoding="utf-8-sig"))
        bad_lang["languages"] = 42
        lang_case = tmp / "lang.json"
        lang_case.write_text(json.dumps(bad_lang), encoding="utf-8")
        check("invalid_language_not_dropped_exit4", lambda: (lambda p, r: p.returncode == 4 and
                                                              r["refusal"]["rule"] == "retrieval.invalid_language_boundary" and no_trace(p))(*run(lang_case, tmp / "lang-out")))

        negative_k = json.loads(clean.read_text(encoding="utf-8-sig"))
        negative_k["top_k"] = -1
        k_case = tmp / "k.json"
        k_case.write_text(json.dumps(negative_k), encoding="utf-8")
        check("negative_topk_exit4", lambda: (lambda p, r: p.returncode == 4 and
                                               r["refusal"]["rule"] == "screening.top_k_invalid" and no_trace(p))(*run(k_case, tmp / "k-out")))

        pdf = tmp / "record.pdf"
        pdf.write_bytes(b"not extracted")
        pdf_case = tmp / "pdf.json"
        pdf_case.write_text(json.dumps({"research_question": "protein", "records_path": "record.pdf"}), encoding="utf-8")
        check("pdf_not_extracted_exit5", lambda: (lambda p, r: p.returncode == 5 and
                                                   r["refusal"]["rule"] == "retrieval.material_unsupported" and no_trace(p))(*run(pdf_case, tmp / "pdf-out")))

        check("clean_bom_exit0_zero_findings", lambda: (lambda p, r: p.returncode == 0 and r["status"] == "clean" and
                                                         r["findings"] == [] and r["review_queue"] == [] and no_trace(p))(*run(clean, tmp / "clean-out")))

        off_topic = {"case_id": "off-topic", "research_question": "protein folding",
                     "records": [{"id": "off", "title": "Completely unrelated fixture", "abstract": "coating insulation only",
                                  "authors": ["Synthetic"], "year": 2024, "journal": "Synthetic fixture", "language": "en"}],
                     "screening_protocol": {"inclusion_criteria": [{"id": "INC", "terms": ["protein"]}], "exclusion_criteria": []}}
        off_case = tmp / "off.json"
        off_case.write_text(json.dumps(off_topic), encoding="utf-8")
        check("zero_retained_review_not_blocked", lambda: (lambda p, r: p.returncode == 3 and r["status"] == "review" and
                                                            r["candidate_set_summary"]["include"] == 0 and len(r["excluded_records"]) == 1 and no_trace(p))(*run(off_case, tmp / "off-out")))
        check("refusal_not_empty_success", lambda: (lambda p, r: r["status"] == "blocked" and
                                                     not r["状态说明"]["空结果"] and r["refusal"]["rule"] == "screening.protocol_missing")(*run(no_protocol, tmp / "no-protocol-out2")))

        def review_valid():
            value = json.loads(clean.read_text(encoding="utf-8-sig"))
            value["review_decisions"] = [{"record_id": "crossref-alphafold", "decision": "exclude", "reviewer": "fixture-reviewer",
                                           "rationale": "explicit synthetic review-declaration fixture", "time": "2026-11-24T00:00:00Z"}]
            case = tmp / "review.json"
            case.write_text(json.dumps(value), encoding="utf-8")
            proc, result = run(case, tmp / "review-out")
            row = result["excluded_records"][0]
            return proc.returncode == 3 and row["engine_decision"] == "include" and row["final_decision"] == "exclude" \
                and len(result["human_review_history"]) == 1 and result["human_review_history"][0]["user_id"] == "fixture-reviewer" and no_trace(proc)
        check("valid_review_applied_with_history", review_valid)

        def review_invalid():
            value = json.loads(clean.read_text(encoding="utf-8-sig"))
            value["review_decisions"] = [{"record_id": "unknown", "decision": "exclude", "reviewer": "unregistered", "rationale": "x"}]
            case = tmp / "bad-review.json"
            case.write_text(json.dumps(value), encoding="utf-8")
            proc, result = run(case, tmp / "bad-review-out")
            return proc.returncode == 3 and result["ranked_included"][0]["final_decision"] == "include" \
                and result["human_review_history"] == [] and any(f["rule"] == "screening.review_invalid" for f in result["findings"])
        check("unknown_review_target_not_applied", review_invalid)

        def review_conflicts():
            value = json.loads(clean.read_text(encoding="utf-8-sig"))
            value["review_decisions"] = [
                {"record_id": "crossref-alphafold", "decision": "include", "reviewer": "A", "rationale": "fixture A"},
                {"record_id": "crossref-alphafold", "decision": "exclude", "reviewer": "B", "rationale": "fixture B"}]
            case = tmp / "conflict-review.json"
            case.write_text(json.dumps(value), encoding="utf-8")
            proc, result = run(case, tmp / "conflict-review-out")
            return proc.returncode == 3 and result["pending_records"][0]["review_resolution"] == "unresolved_human_label_conflict" \
                and any(f["rule"] == "screening.human_label_conflict" for f in result["findings"])
        check("conflicting_review_votes_pending", review_conflicts)

        def review_adjudication():
            value = json.loads(clean.read_text(encoding="utf-8-sig"))
            value["review_decisions"] = [
                {"record_id": "crossref-alphafold", "decision": "include", "reviewer": "A", "rationale": "fixture A"},
                {"record_id": "crossref-alphafold", "decision": "exclude", "reviewer": "B", "rationale": "fixture B"},
                {"record_id": "crossref-alphafold", "decision": "include", "reviewer": "C", "role": "adjudicator",
                 "rationale": "explicit fixture adjudication"}]
            case = tmp / "adjudication.json"
            case.write_text(json.dumps(value), encoding="utf-8")
            proc, result = run(case, tmp / "adjudication-out")
            return proc.returncode == 0 and result["ranked_included"][0]["review_resolution"] == "adjudicated_by_declared_reviewer" \
                and len(result["human_review_history"]) == 3 and no_trace(proc)
        check("adjudication_is_explicit_and_replayable", review_adjudication)

        def unknown_contract():
            value = json.loads(clean.read_text(encoding="utf-8-sig"))
            value["status"] = "fabricated-clean"
            value["output_contract"] = [{"field": "检索结果"}, {"name": "证据记录"}, {"key": "状态说明"}, "unknown", "status"]
            case = tmp / "contract.json"
            case.write_text(json.dumps(value), encoding="utf-8")
            proc, result = run(case, tmp / "contract-out")
            return proc.returncode == 3 and result["unknown"] is None and result["status"] == "review" and no_trace(proc)
        check("contract_fields_and_engine_priority", unknown_contract)

        def deterministic_two_dirs():
            p1, r1 = run(clean, tmp / "det-a", tmp)
            p2, r2 = run(clean, tmp / "det-b", tmp)
            return p1.returncode == p2.returncode == 0 and hashes(tmp / "det-a") == hashes(tmp / "det-b") and no_trace(p1) and no_trace(p2)
        check("all_outputs_two_dirs_identical", deterministic_two_dirs)

        def idempotent_same_dir():
            run(clean, tmp / "same-out")
            before = hashes(tmp / "same-out")
            proc, result = run(clean, tmp / "same-out")
            return before == hashes(tmp / "same-out") and proc.returncode == 0 and no_trace(proc)
        check("same_out_directory_idempotent", idempotent_same_dir)

        def cold_import():
            code = "import sys;sys.dont_write_bytecode=True;sys.path.insert(0,sys.argv[1]);import retrieval_common,screening_engine;print(screening_engine.SCHEMA_VERSION)"
            proc = subprocess.run([sys.executable, "-B", "-I", "-X", "utf8", "-c", code, str(HERE)], cwd=tmp,
                                  env=ENV, capture_output=True, text=True, timeout=120)
            return proc.returncode == 0 and proc.stdout.strip() == "screening-rank/v2" and "Traceback" not in proc.stderr
        check("cold_isolated_import", cold_import)

        def socket_guard():
            code = """import runpy,sys
sys.dont_write_bytecode=True
def hook(event,args):
    if event == 'socket.connect': raise AssertionError('NETWORK ATTEMPT')
sys.addaudithook(hook)
case,out,cli=sys.argv[1],sys.argv[2],sys.argv[3]
sys.argv=['screening_cli.py','--case',case,'--out',out]
runpy.run_path(cli,run_name='__main__')
"""
            proc = subprocess.run([sys.executable, "-B", "-I", "-X", "utf8", "-c", code,
                                   str(clean), str(tmp / "socket-out"), str(CLI)], cwd=tmp, env=ENV,
                                  capture_output=True, text=True, timeout=120)
            return proc.returncode == 0 and "NETWORK ATTEMPT" not in proc.stderr
        check("socket_audit_no_network", socket_guard)

        def example_accounting():
            proc, result = run(ROOT / "examples" / "case.json", tmp / "example-out")
            summary = result["candidate_set_summary"]
            return proc.returncode == 3 and (summary["include"], summary["pending"], summary["exclude"]) == (2, 2, 4) \
                and len(result["screening_log"]) == 9 and summary["all_raw_rows_accounted"] \
                and result["human_review_history"] == [] and no_trace(proc)
        check("nine_row_example_counting_and_no_fake_review", example_accounting)

        def stdout_json():
            proc, result = run(clean, tmp / "stdout-out")
            line = json.loads(proc.stdout)
            return line["status"] == "clean" and line["include"] == 1 and line["pending"] == 0 and line["remote_hit_count"] is None and no_trace(proc)
        check("stdout_structured_single_json", stdout_json)

        def artifacts():
            proc, result = run(clean, tmp / "hash-out")
            return all(hashlib.sha256((tmp / "hash-out" / a["path"]).read_bytes()).hexdigest() == a["sha256"]
                       for a in result["artifacts"]) and no_trace(proc)
        check("artifact_hashes_exact", artifacts)

    passed = sum(x["pass"] for x in rows)
    report = {"schema_version": "screening-rank-v2-hostile/v1", "official_score": False,
              "probes": rows, "totals": {"passed": passed, "of": len(rows)}}
    (HERE / "report_filter_rank_hostile.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"\n{passed}/{len(rows)} probes pass")
    return 0 if passed == len(rows) else 1


if __name__ == "__main__":
    raise SystemExit(main())
