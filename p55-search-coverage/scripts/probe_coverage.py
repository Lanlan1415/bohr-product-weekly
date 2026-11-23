"""Black-box hostile/contract/exit-code probes for coverage_cli.py."""
from __future__ import annotations

import copy
import json
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import case_common as C  # noqa: E402

BASE = json.loads((HERE.parent / "examples" / "case.json").read_text(encoding="utf-8"))
CLI = HERE / "coverage_cli.py"


def invoke(tmp: Path, case=None, raw=None, filename="case.json", outname="out"):
    path = tmp / filename
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(raw if raw is not None else json.dumps(case, ensure_ascii=False), encoding="utf-8")
    out = tmp / outname
    proc = subprocess.run([sys.executable, "-I", "-X", "utf8", str(CLI), "--case", str(path),
                           "--out", str(out)], capture_output=True, text=True, timeout=90)
    result = json.loads((out / "result.json").read_text(encoding="utf-8")) if (out / "result.json").exists() else {}
    return proc, result, out


def no_tb(proc):
    return "Traceback" not in proc.stderr and "Traceback" not in proc.stdout


def scenario(tmp, name):
    base = copy.deepcopy(BASE)
    if name == "malformed_json_exit5":
        p, r, _ = invoke(tmp, raw="{bad")
        return p.returncode == 5 and r["refusal"]["rule"] == "coverage.case_unreadable" and no_tb(p)
    if name == "case_array_exit4":
        p, r, _ = invoke(tmp, case=[])
        return p.returncode == 4 and r["refusal"]["rule"] == "coverage.case_not_object" and no_tb(p)
    if name == "unknown_section_exit5_contract":
        base["section"] = "something-else"
        p, r, _ = invoke(tmp, case=base)
        return p.returncode == 5 and r["refusal"]["rule"] == "coverage.unknown_section" \
            and all(k in r for k in C.contract_fields(base["output_contract"])[0]) and no_tb(p)
    if name == "missing_reference_set_exit5":
        base.pop("reference_set")
        p, r, _ = invoke(tmp, case=base)
        return p.returncode == 5 and r["refusal"]["rule"] == "coverage.no_reference_set" and no_tb(p)
    if name == "empty_reference_set_exit5":
        base["reference_set"] = []
        p, r, _ = invoke(tmp, case=base)
        return p.returncode == 5 and r["refusal"]["rule"] == "coverage.no_reference_set" and no_tb(p)
    if name == "missing_candidates_exit5":
        base.pop("documents")
        base.pop("supplementary_documents")
        p, r, _ = invoke(tmp, case=base)
        return p.returncode == 5 and r["refusal"]["rule"] == "coverage.no_candidates" and no_tb(p)
    if name == "wrong_document_shape_exit5":
        base["documents"] = 42
        p, r, _ = invoke(tmp, case=base)
        return p.returncode == 5 and r["refusal"]["rule"] in {"search.material_shape", "coverage.no_candidates"} and no_tb(p)
    if name == "partial_bad_record_is_named_review":
        base["documents"].append(42)
        p, r, _ = invoke(tmp, case=base)
        return p.returncode == 3 and r["omissions"] and no_tb(p)
    if name == "mapping_contract_full_echo":
        base["output_contract"] = {"case_id": "id", "coverage_metrics": {}, "检索结果": {},
                                   "delivery_note": "caller", "missing_field": "required"}
        base["delivery_note"] = "kept-exactly"
        p, r, _ = invoke(tmp, case=base)
        return p.returncode == 3 and r["delivery_note"] == "kept-exactly" \
            and r["missing_field"] is None and r["case_id"] == base["case_id"] \
            and r["output_contract"] == base["output_contract"] and no_tb(p)
    if name == "object_list_contract_and_status_not_spoofed":
        base["output_contract"] = [{"field": "case_id"}, {"name": "coverage_metrics"},
                                   {"key": "delivery_note"}, {"field": "status"}]
        base["delivery_note"] = 7
        base["status"] = "fabricated-clean-state"
        p, r, _ = invoke(tmp, case=base)
        return p.returncode == 0 and r["delivery_note"] == 7 and r["status"] == "clean" and no_tb(p)
    if name == "unsupported_contract_is_limit_not_crash":
        base["output_contract"] = 42
        p, r, _ = invoke(tmp, case=base)
        return p.returncode == 0 and any("unsupported type" in x for x in r["limits"]) and no_tb(p)
    if name == "missing_declared_material_exit5":
        base.pop("documents")
        base.pop("supplementary_documents")
        base["documents_path"] = "not-present-反向.json"
        p, r, _ = invoke(tmp, case=base)
        return p.returncode == 5 and r["refusal"]["rule"] == "search.material_missing" and no_tb(p)
    if name == "unicode_cold_path_and_exact_replay":
        case_path = "目录 with space/案例.json"
        p, r, out = invoke(tmp, case=base, filename=case_path, outname="冷 输出")
        if p.returncode != 0:
            return False
        p2, r2, out2 = invoke(tmp, case=base, filename=case_path, outname="second")
        return p2.returncode == 0 and (out / "result.json").read_bytes() == (out2 / "result.json").read_bytes() and no_tb(p2)
    if name == "manual_adjudication_can_confirm_and_reject":
        base["manual_adjudications"] = [{"ref_id": "ref-missing", "candidate_id": "cand-distractor",
                                          "decision": "covered", "reviewer": "synthetic-reviewer",
                                          "rationale": "Synthetic fixture override"}]
        p, r, _ = invoke(tmp, case=base)
        if p.returncode != 0 or r["coverage_metrics"]["known_set_recall"] != 1.0:
            return False
        base["manual_adjudications"] = [{"ref_id": "ref-alpha", "candidate_id": "cand-alpha-crossref",
                                          "decision": "different_work", "reviewer": "synthetic-reviewer",
                                          "rationale": "Synthetic misbinding rejection"}]
        p2, r2, _ = invoke(tmp, case=base, outname="reject-out")
        return p2.returncode == 0 and not next(x for x in r2["coverage_matrix"] if x["ref_id"] == "ref-alpha")["covered"] and no_tb(p2)
    if name == "usage_is_argparse_exit2":
        proc = subprocess.run([sys.executable, "-I", str(CLI)], capture_output=True, text=True, timeout=30)
        return proc.returncode == 2 and "Traceback" not in proc.stderr
    raise ValueError(name)


NAMES = [
    "malformed_json_exit5", "case_array_exit4", "unknown_section_exit5_contract",
    "missing_reference_set_exit5", "empty_reference_set_exit5", "missing_candidates_exit5",
    "wrong_document_shape_exit5", "partial_bad_record_is_named_review",
    "mapping_contract_full_echo", "object_list_contract_and_status_not_spoofed",
    "unsupported_contract_is_limit_not_crash", "missing_declared_material_exit5",
    "unicode_cold_path_and_exact_replay", "manual_adjudication_can_confirm_and_reject",
    "usage_is_argparse_exit2",
]


def main():
    rows = []
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        for name in NAMES:
            try:
                ok, why = bool(scenario(tmp, name)), ""
            except Exception as exc:
                ok, why = False, f"raised {type(exc).__name__}: {exc}"
            rows.append({"scenario": name, "pass": ok, "why": why})
            print(("PASS" if ok else "FAIL") + f"  {name:<58}{why}")
    passed = sum(r["pass"] for r in rows)
    C.write_json(HERE / "report_hostile.json", {
        "schema_version": "coverage-hostile/v1", "scenarios": rows,
        "totals": {"passed": passed, "of": len(rows)}, "fixture": "synthetic_not_official"})
    print(f"\n{passed}/{len(rows)} probes pass")
    return 0 if passed == len(rows) else 1


if __name__ == "__main__":
    raise SystemExit(main())
