"""Independent hostile CLI probes for topicrun; all inputs are synthetic."""
from __future__ import annotations

import copy
import json
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
CLI = HERE / "topicrun.py"
BASE = json.loads((ROOT / "examples" / "topic-spec.json").read_text(encoding="utf-8"))
CASE = json.loads((ROOT / "examples" / "case.json").read_text(encoding="utf-8"))


def invoke(tmp: Path, spec_text=None, case_text=None, spec_data=None, case_data=CASE,
           missing_spec=False, out_as_file=False, extra=()):
    tmp.mkdir(parents=True, exist_ok=True)
    source = tmp / "spec.json"
    if not missing_spec:
        source.write_text(spec_text if spec_text is not None else json.dumps(
            spec_data if spec_data is not None else BASE, ensure_ascii=False), encoding="utf-8")
    case_file = tmp / "case.json"
    if case_text is not None or case_data is not None:
        case_file.write_text(case_text if case_text is not None else json.dumps(case_data, ensure_ascii=False), encoding="utf-8")
    out = tmp / "out"
    if out_as_file:
        out.write_text("not a directory", encoding="utf-8")
    args = [sys.executable, "-I", "-X", "utf8", str(CLI), "--spec", str(source), "--out", str(out), *extra]
    if case_text is not None or case_data is not None:
        args += ["--case", str(case_file)]
    proc = subprocess.run(args, capture_output=True, text=True, timeout=60)
    result_file = out / "result.json" if out.is_dir() else None
    result = json.loads(result_file.read_text(encoding="utf-8")) if result_file and result_file.exists() else None
    return proc, result, out


def no_tb(proc):
    return "Traceback" not in proc.stderr and "Traceback" not in proc.stdout


def main():
    rows = []

    def check(name, ok, detail=""):
        rows.append({"probe": name, "pass": bool(ok), "detail": detail})
        print(("PASS" if ok else "FAIL") + f"  {name:<34}" + detail)

    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        proc, result, _ = invoke(root / "missing", missing_spec=True)
        check("missing_spec_exit5", proc.returncode == 5 and result and result["status"] == "undetermined" and no_tb(proc), proc.stderr[-160:])

        proc, result, _ = invoke(root / "badjson", spec_text="{bad")
        check("malformed_spec_contract", proc.returncode == 5 and result and len(result["output_contract_fields"]) == 11 and no_tb(proc), proc.stderr[-160:])

        proc, result, _ = invoke(root / "list", spec_text="[]")
        check("nonobject_spec_exit5", proc.returncode == 5 and result and result["status"] == "undetermined" and no_tb(proc), proc.stderr[-160:])

        proc, result, _ = invoke(root / "badcase", case_text="{bad")
        check("malformed_case_exit5", proc.returncode == 5 and result and result["status"] == "undetermined" and no_tb(proc), proc.stderr[-160:])

        proc, result, _ = invoke(root / "listcase", case_text="[]")
        check("nonobject_case_exit5", proc.returncode == 5 and result and result["status"] == "undetermined" and no_tb(proc), proc.stderr[-160:])

        empty = copy.deepcopy(BASE)
        empty["works"] = []
        empty["innovation_claims"] = []
        proc, result, out = invoke(root / "empty", spec_data=empty)
        check("empty_evidence_blocked_artifacts", proc.returncode == 4 and result and result["status"] == "blocked"
              and (out / "topic_evaluation.md").exists() and no_tb(proc), proc.stderr[-160:])

        malformed = copy.deepcopy(BASE)
        malformed["works"] = [None, "bad", {}]
        malformed["innovation_claims"] = [None, {"nearest_comparisons": [None]}]
        malformed["feasibility"]["prerequisites"] = [None]
        proc, result, _ = invoke(root / "rows", spec_data=malformed)
        check("malformed_rows_no_crash", proc.returncode == 4 and result and result["findings"] and no_tb(proc), proc.stderr[-160:])

        proc, result, _ = invoke(root / "outfile", out_as_file=True)
        check("output_path_conflict_exit5", proc.returncode == 5 and no_tb(proc), proc.stderr[-160:])

        proc = subprocess.run([sys.executable, "-I", "-X", "utf8", str(CLI)], capture_output=True, text=True, timeout=60)
        check("usage_exit2", proc.returncode == 2 and no_tb(proc), proc.stderr[-160:])

        odd_case = {"case_id": "odd-contract", "status": "case-must-not-win",
                    "output_contract": ["research_product", 9, {"bogus": True}, "status"]}
        proc, result, _ = invoke(root / "oddcontract", case_data=odd_case)
        check("contract_types_and_engine_priority", proc.returncode == 0 and result
              and result["output_contract_fields"] == ["research_product", "status"]
              and result["status"] == "clean" and result["case_id"] == "odd-contract"
              and len(result["limits"]) >= 4 and no_tb(proc), proc.stderr[-160:])

        cjk = copy.deepcopy(BASE)
        cjk["works"][0]["title"] = "合成强监督基线研究"
        cjk["works"][0]["evidence"][0]["quote"] = "我们研究低资源文本分类。"
        cjk["works"][0]["source_excerpt"] += "\n我们研究低资源文本分类。"
        proc, result, _ = invoke(root / "cjk", spec_data=cjk)
        check("cjk_realistic_smoke", proc.returncode == 0 and result and result["status"] == "clean" and no_tb(proc), proc.stderr[-160:])

        proc1, result1, out = invoke(root / "repeat")
        snapshot = {p.name: p.read_bytes() for p in out.iterdir() if p.is_file()}
        proc2 = subprocess.run([sys.executable, "-I", "-X", "utf8", str(CLI),
                                "--spec", str(root / "repeat" / "spec.json"),
                                "--case", str(root / "repeat" / "case.json"),
                                "--out", str(out)], capture_output=True, text=True, timeout=60)
        snapshot2 = {p.name: p.read_bytes() for p in out.iterdir() if p.is_file()}
        check("separate_process_determinism", proc1.returncode == proc2.returncode == 0
              and snapshot == snapshot2 and no_tb(proc2), proc2.stderr[-160:])

        cold = subprocess.run([sys.executable, "-I", "-X", "utf8", "-c",
                               "import importlib.util,json,pathlib; "
                               f"p=pathlib.Path(r'{CLI}'); s=importlib.util.spec_from_file_location('cold_topicrun',p); "
                               "m=importlib.util.module_from_spec(s); s.loader.exec_module(m); "
                               "print(m.EXIT['undetermined'])"], capture_output=True, text=True, timeout=60)
        check("cold_import_no_side_effect", cold.returncode == 0 and cold.stdout.strip() == "5" and no_tb(cold), cold.stderr[-160:])

        prospective = copy.deepcopy(BASE)
        prospective["search_protocol"]["status"] = "prospective"
        proc, result, out = invoke(root / "prospective", spec_data=prospective)
        text = (out / "topic_evaluation.md").read_text(encoding="utf-8") if (out / "topic_evaluation.md").exists() else ""
        check("no_fake_counts_or_novelty", proc.returncode == 4 and result
              and all(row["hit_count"] is None for row in result["search_protocol"]["sources"])
              and "undetermined" in text and "全球无人研究" not in text and no_tb(proc), proc.stderr[-160:])

    passed = sum(row["pass"] for row in rows)
    report = {"schema_version": "topic-hostile-probes/v2", "synthetic_only": True,
              "totals": {"passed": passed, "of": len(rows)}, "probes": rows}
    (HERE / "probe_topic_v2.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n{passed}/{len(rows)} hostile probes pass")
    return 0 if passed == len(rows) else 1


if __name__ == "__main__":
    raise SystemExit(main())
