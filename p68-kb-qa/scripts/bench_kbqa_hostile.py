"""Hostile CLI/contract/exit-code probes for kbqa_cli.py."""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import tempfile
from pathlib import Path

CLI = Path(__file__).resolve().with_name("kbqa_cli.py")


def invoke(case, out, *extra):
    args = [sys.executable, "-I", "-X", "utf8", str(CLI), "--out", str(out)]
    if case is not None:
        args += ["--case", str(case)]
    args += list(extra)
    return subprocess.run(args, capture_output=True, text=True, timeout=120)


def valid_case(**over):
    value = {"case_id": "hostile-kbqa",
             "documents": [{"document_id": "ok", "text": "样品在测量期间保存于 4 C。"}],
             "questions": ["保存温度是多少？"],
             "output_contract": {"answers": [], "deliverable": "verified answers"}}
    value.update(over)
    return value


def no_crash(proc):
    return "Traceback" not in proc.stderr and "Traceback" not in proc.stdout


def parse_stdout(proc):
    try:
        return json.loads(proc.stdout)
    except (json.JSONDecodeError, TypeError):
        return None


def main():
    rows = []

    def probe(name, condition):
        ok = bool(condition)
        rows.append({"probe": name, "pass": ok})
        print(f"{'PASS' if ok else 'FAIL'}  {name}")

    with tempfile.TemporaryDirectory() as temp:
        root = Path(temp)
        bad = root / "bad.json"
        bad.write_text("{broken", encoding="utf-8")
        p = invoke(bad, root / "bad-out")
        probe("malformed_case_exit5", p.returncode == 5 and no_crash(p) and parse_stdout(p)
              and json.loads((root / "bad-out/result.json").read_text(encoding="utf-8"))["status"] == "undetermined")

        arr = root / "array.json"
        arr.write_text("[]", encoding="utf-8")
        p = invoke(arr, root / "array-out")
        probe("case_not_object_exit5", p.returncode == 5 and no_crash(p))

        p = invoke(root / "missing.json", root / "missing-out")
        probe("missing_case_exit5", p.returncode == 5 and no_crash(p))

        p = invoke(None, root / "no-case-out")
        probe("case_required_exit5", p.returncode == 5 and no_crash(p))

        empty = root / "empty.json"
        empty.write_text(json.dumps({"case_id": "empty", "questions": ["无答案问题"],
                                     "documents": [], "output_contract": {"answers": []}}, ensure_ascii=False), encoding="utf-8")
        p = invoke(empty, root / "empty-out")
        result = json.loads((root / "empty-out/result.json").read_text(encoding="utf-8"))
        probe("empty_library_explicit_unknown", p.returncode == 5 and no_crash(p)
              and result["status"] == "undetermined" and not result["evidence"]
              and result["answers"][0]["status"] == "insufficient_evidence")

        noq = root / "noq.json"
        noq.write_text(json.dumps(valid_case(questions=[]), ensure_ascii=False), encoding="utf-8")
        p = invoke(noq, root / "noq-out")
        probe("no_questions_exit5", p.returncode == 5 and no_crash(p))

        weird = root / "weird.json"
        weird.write_text(json.dumps(valid_case(documents=[None, 42, {"id": "empty"},
            {"document_id": "ok", "text": "样品在测量期间保存于 4 C。"}]), ensure_ascii=False), encoding="utf-8")
        p = invoke(weird, root / "weird-out")
        probe("hostile_document_shapes_partial", p.returncode == 3 and no_crash(p)
              and json.loads((root / "weird-out/result.json").read_text(encoding="utf-8"))["answers"][0]["status"] == "answered")

        bad_utf = root / "bad.txt"
        bad_utf.write_bytes("样品".encode("gbk"))
        partial = root / "partial.json"
        partial.write_text(json.dumps(valid_case(documents=[{"path": "bad.txt"},
            {"document_id": "ok", "text": "样品在测量期间保存于 4 C。"}]), ensure_ascii=False), encoding="utf-8")
        p = invoke(partial, root / "partial-out")
        probe("mixed_unreadable_and_good_partial", p.returncode == 3 and no_crash(p)
              and len(json.loads((root / "partial-out/result.json").read_text(encoding="utf-8"))["failures"]) >= 1)

        contract = root / "contract.json"
        contract.write_text(json.dumps(valid_case(output_contract=["not", "an", "object"]), ensure_ascii=False), encoding="utf-8")
        p = invoke(contract, root / "contract-out")
        result = json.loads((root / "contract-out/result.json").read_text(encoding="utf-8"))
        probe("nonobject_contract_degrades", p.returncode == 0 and no_crash(p)
              and any("output_contract" in x for x in result["limits"]))

        good = root / "good.json"
        spec = valid_case(questions=[{"question_id": "m", "question": "请分别回答保存温度，以及每组重复数量。"},
                                     {"question_id": "u", "question": "不存在的超光速参数是多少？"}])
        spec["documents"].append({"document_id": "reps", "text": "每组有六个重复。"})
        good.write_text(json.dumps(spec, ensure_ascii=False), encoding="utf-8")
        out1, out2 = root / "out1", root / "out2"
        p1, p2 = invoke(good, out1), invoke(good, out2)
        hashes = lambda out: {f.name: hashlib.sha256(f.read_bytes()).hexdigest()
                              for f in sorted(out.iterdir()) if f.is_file()}
        probe("deterministic_all_outputs", p1.returncode == p2.returncode == 0 and no_crash(p1)
              and hashes(out1) == hashes(out2))

        result = json.loads((out1 / "result.json").read_text(encoding="utf-8"))
        probe("multi_and_unknown_answer_coverage", result["coverage"]["questions"] == 2
              and result["coverage"]["insufficient_evidence"] == 1
              and result["answers"][0]["coverage"]["unanswered"] == 0)

        v = subprocess.run([sys.executable, "-I", "-X", "utf8", str(CLI), "--verify-only",
                            "--out", str(out1)], capture_output=True, text=True, timeout=120)
        probe("cold_verify_exit0", v.returncode == 0 and no_crash(v) and parse_stdout(v)["ok"])

        answer_path = out1 / "answers.json"
        # Tamper the authoritative result, not just the Markdown rendering.
        rpath = out1 / "result.json"
        tampered = json.loads(rpath.read_text(encoding="utf-8"))
        tampered["answers"][0]["claims"][0]["text"] = "无来源事实"
        rpath.write_text(json.dumps(tampered, ensure_ascii=False), encoding="utf-8")
        v = subprocess.run([sys.executable, "-I", "-X", "utf8", str(CLI), "--verify-only",
                            "--out", str(out1)], capture_output=True, text=True, timeout=120)
        probe("tampered_claim_verify_exit5", v.returncode == 5 and no_crash(v)
              and parse_stdout(v)["ok"] is False)

        v = subprocess.run([sys.executable, "-I", "-X", "utf8", str(CLI), "--verify-only",
                            "--out", str(root / "not-written")], capture_output=True, text=True, timeout=120)
        probe("verify_missing_export_exit5", v.returncode == 5 and no_crash(v))

        broken_work = root / "work-broken.json"
        broken_work.write_text("{", encoding="utf-8")
        workcase = root / "workcase.json"
        workcase.write_text(json.dumps({"case_id": "w", "workorder": broken_work.name,
                                        "questions": ["保存温度"], "documents": [{"text": "样品保存于 4 C。"}]},
                                       ensure_ascii=False), encoding="utf-8")
        p = invoke(workcase, root / "work-out")
        probe("broken_workorder_partial_not_crash", p.returncode == 3 and no_crash(p)
              and json.loads((root / "work-out/result.json").read_text(encoding="utf-8"))["failures"])

        deep = root / "deep.json"
        deep.write_text(json.dumps(valid_case(), ensure_ascii=False), encoding="utf-8")
        deep_out = root / "a" / "b" / "c"
        p = invoke(deep, deep_out)
        probe("nested_output_created", p.returncode == 0 and (deep_out / "answers.md").exists() and no_crash(p))

        out_file = root / "out-is-file"
        out_file.write_text("not a directory", encoding="utf-8")
        p = invoke(deep, out_file)
        probe("unwritable_output_structured_refusal", p.returncode == 5 and no_crash(p)
              and parse_stdout(p) and parse_stdout(p)["wrote"] is None)

    passed = sum(r["pass"] for r in rows)
    report = {"schema_version": "kbqa-hostile-bench/v1", "probes": rows,
              "totals": {"passed": passed, "of": len(rows)}}
    (Path(__file__).resolve().parent / "report_kbqa_hostile.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n{passed}/{len(rows)} scenarios pass")
    return 0 if passed == len(rows) else 1


if __name__ == "__main__":
    raise SystemExit(main())
