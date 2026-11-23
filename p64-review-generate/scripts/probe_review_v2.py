"""Independent hostile probes for reviewrun; synthetic inputs only."""
from __future__ import annotations

import copy
import json
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
CLI = HERE / "reviewrun.py"
BASE = json.loads((ROOT / "examples" / "review-spec.json").read_text(encoding="utf-8"))
CASE = json.loads((ROOT / "examples" / "case.json").read_text(encoding="utf-8"))


def invoke(tmp: Path, spec_text=None, case_text=None, spec_data=None, case_data=CASE,
           missing_spec=False, out_as_file=False):
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
    args = [sys.executable, "-B", "-I", "-X", "utf8", str(CLI), "--spec", str(source), "--out", str(out)]
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
        print(("PASS" if ok else "FAIL") + f"  {name:<38}" + detail)

    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        p, r, _ = invoke(root / "missing", missing_spec=True)
        check("missing_spec_exit5_contract", p.returncode == 5 and r and len(r["output_contract_fields"]) == 11 and no_tb(p), p.stderr[-140:])

        p, r, _ = invoke(root / "badjson", spec_text="{bad")
        check("malformed_spec_exit5", p.returncode == 5 and r and r["status"] == "undetermined" and no_tb(p), p.stderr[-140:])

        p, r, _ = invoke(root / "list", spec_text="[]")
        check("nonobject_spec_exit5", p.returncode == 5 and r and no_tb(p), p.stderr[-140:])

        p, r, _ = invoke(root / "badcase", case_text="{bad")
        check("malformed_case_exit5", p.returncode == 5 and r and r["status"] == "undetermined" and no_tb(p), p.stderr[-140:])

        p, r, _ = invoke(root / "listcase", case_text="[]")
        check("nonobject_case_exit5", p.returncode == 5 and r and no_tb(p), p.stderr[-140:])

        empty = copy.deepcopy(BASE); empty["records"] = []; empty["synthesis_claims"] = []; empty["research_gaps"] = []
        p, r, out = invoke(root / "empty", spec_data=empty)
        check("empty_corpus_blocked_outputs", p.returncode == 4 and r and r["status"] == "blocked"
              and r["citation_coverage"]["included_records"] == 0
              and (out / "review_draft.md").exists() and no_tb(p), p.stderr[-140:])

        malformed = copy.deepcopy(BASE)
        malformed["records"] = [None, "bad", {}]
        malformed["themes"] = [None]
        malformed["synthesis_claims"] = [None, {"support_evidence_refs": [None]}]
        malformed["research_gaps"] = [None]
        p, r, out = invoke(root / "rows", spec_data=malformed)
        check("malformed_rows_no_crash", p.returncode == 4 and r and r["findings"] and no_tb(p), p.stderr[-140:])

        p, r, _ = invoke(root / "outfile", out_as_file=True)
        check("output_path_conflict_exit5", p.returncode == 5 and no_tb(p), p.stderr[-140:])

        p = subprocess.run([sys.executable, "-B", "-I", "-X", "utf8", str(CLI)], capture_output=True, text=True, timeout=60)
        check("usage_exit2", p.returncode == 2 and no_tb(p), p.stderr[-140:])

        odd_case = {"case_id": "odd-review-contract", "status": "case-must-not-win",
                    "output_contract": ["research_product", 9, {"bogus": True}, "status"]}
        p, r, _ = invoke(root / "oddcontract", case_data=odd_case)
        check("contract_types_and_engine_priority", p.returncode == 0 and r
              and r["output_contract_fields"] == ["research_product", "status"]
              and r["status"] == "clean" and r["case_id"] == "odd-review-contract"
              and len(r["limits"]) >= 5 and no_tb(p), p.stderr[-140:])

        cjk = copy.deepcopy(BASE)
        cjk["records"][0]["title"] = "合成监督运动随机对照研究"
        cjk["records"][0]["evidence"][0]["quote"] = "受试者接受十二周个体化运动。"
        cjk["records"][0]["source_excerpt"] += "\n受试者接受十二周个体化运动。"
        cjk["themes"][0]["label"] = "运动与疼痛的中文主题"
        p, r, _ = invoke(root / "cjk", spec_data=cjk)
        check("cjk_realistic_smoke", p.returncode == 0 and r and r["status"] == "clean" and no_tb(p), p.stderr[-140:])

        p1, r1, out = invoke(root / "repeat")
        one = {x.name: x.read_bytes() for x in out.iterdir() if x.is_file()}
        p2 = subprocess.run([sys.executable, "-B", "-I", "-X", "utf8", str(CLI),
                             "--spec", str(root / "repeat" / "spec.json"), "--case", str(root / "repeat" / "case.json"),
                             "--out", str(out)], capture_output=True, text=True, timeout=60)
        two = {x.name: x.read_bytes() for x in out.iterdir() if x.is_file()}
        check("separate_process_determinism", p1.returncode == p2.returncode == 0 and one == two and no_tb(p2), p2.stderr[-140:])

        cold = subprocess.run([sys.executable, "-B", "-I", "-X", "utf8", "-c",
                               "import importlib.util,pathlib; "
                               f"p=pathlib.Path(r'{CLI}'); s=importlib.util.spec_from_file_location('cold_reviewrun',p); "
                               "m=importlib.util.module_from_spec(s); s.loader.exec_module(m); print(m.EXIT['undetermined'])"],
                              capture_output=True, text=True, timeout=60)
        check("cold_import_no_side_effect", cold.returncode == 0 and cold.stdout.strip() == "5" and no_tb(cold), cold.stderr[-140:])

        p, r, out = invoke(root / "selfcheck")
        draft = (out / "review_draft.md").read_text(encoding="utf-8")
        required = ["方法、数据、评价与结论比较", "支持证据", "相反/限制证据", "研究缺口", "纳入文献引用覆盖：4/4"]
        check("real_smoke_contains_synthesis", p.returncode == 0 and all(text in draft for text in required)
              and "Pain decreased more" in draft and "did not reach" in draft and no_tb(p), p.stderr[-140:])

    passed = sum(row["pass"] for row in rows)
    report = {"schema_version": "review-hostile-probes/v2", "synthetic_only": True,
              "totals": {"passed": passed, "of": len(rows)}, "probes": rows}
    (HERE / "probe_review_v2.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n{passed}/{len(rows)} hostile probes pass")
    return 0 if passed == len(rows) else 1


if __name__ == "__main__":
    raise SystemExit(main())
