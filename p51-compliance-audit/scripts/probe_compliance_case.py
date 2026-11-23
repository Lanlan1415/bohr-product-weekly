"""Adversarial CLI, contract, cold-import and idempotence checks for compliancecheck."""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

SCRIPT = Path(__file__).resolve().with_name("compliancecheck.py")
EXAMPLE = Path(__file__).resolve().parents[1] / "examples" / "case.json"
RESULTS = []


def record(name, passed, detail=""):
    RESULTS.append({"probe": name, "passed": bool(passed), "detail": detail})
    if not passed:
        print("FAIL", name, detail)


def execute(root, raw):
    root.mkdir(parents=True, exist_ok=True)
    case = root / "case.json"
    case.write_text(raw if isinstance(raw, str) else json.dumps(raw, ensure_ascii=False), encoding="utf-8")
    out = root / "out"
    proc = subprocess.run([sys.executable, "-I", str(SCRIPT), "--case", str(case), "--out", str(out)], capture_output=True, text=True)
    path = out / "result.json"
    result = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}
    return proc, result, out


def main():
    with tempfile.TemporaryDirectory(prefix="compliance-probe-") as tmp:
        root = Path(tmp)
        good = json.loads(EXAMPLE.read_text(encoding="utf-8"))
        for name, raw in (("malformed_json", "{broken"), ("case_not_object", [1, 2]),
                          ("missing_manuscript", {"case_id": "empty", "output_contract": ["audit_report", "unknown"]})):
            proc, result, _ = execute(root / name, raw)
            record(name + "_refusal", proc.returncode == 5 and result.get("status") == "undetermined" and (root / name / "out" / "result.json").is_file(), result)
            record(name + "_no_traceback", "Traceback" not in proc.stderr, proc.stderr)

        proc, result, _ = execute(root / "refusal_contract", {"case_id": "refusal-compliance", "status": "clean",
                                                               "output_contract": ["status", "审查报告", "依据与边界", "missing_field"]})
        record("refusal_contract_complete", result.get("case_id") == "refusal-compliance" and result.get("status") == "undetermined"
               and result.get("审查报告") == [] and "依据与边界" in result and result.get("missing_field") is None
               and any("missing_field" in x for x in result.get("limits", [])), result)

        case = dict(good)
        case["output_contract"] = 42
        proc, result, _ = execute(root / "bad_contract", case)
        record("bad_contract_degrades", proc.returncode == 0 and any("unsupported type" in x for x in result.get("limits", [])), result)

        case = dict(good)
        case["output_contract"] = [{"field": "case_id"}, {"name": "compliance_matrix"}, {"key": "custom"}, None]
        case["custom"] = "case-carried"
        proc, result, _ = execute(root / "object_contract", case)
        record("object_contract_and_case_value", result.get("custom") == "case-carried" and len(result.get("output_contract_fields", [])) == 3, result)

        case = dict(good)
        for key in ("authors", "author_contributions", "images", "references", "journal_requirements", "comparison_corpus"):
            case[key] = 7
        proc, result, _ = execute(root / "wrong_nested_shapes", case)
        record("wrong_nested_shapes_no_crash", proc.returncode in (0, 3, 4, 5) and result.get("case_id") == "compliance-clean-smoke" and "Traceback" not in proc.stderr, proc.stderr)

        case = dict(good)
        case["manuscript_text"] = None
        case["materials"] = [{"role": "manuscript", "path": "missing.pdf"}]
        proc, result, _ = execute(root / "unreadable_pdf", case)
        record("unreadable_pdf_no_fake_clean", proc.returncode == 5 and result.get("status") == "undetermined" and not result.get("compliance_matrix"), result)

        out = root / "idem"
        args = [sys.executable, "-I", str(SCRIPT), "--case", str(EXAMPLE), "--out", str(out)]
        first = subprocess.run(args, capture_output=True, text=True)
        payloads_a = {name: (out / name).read_bytes() for name in ("result.json", "audit_report.md", "run_log.json")}
        second = subprocess.run(args, capture_output=True, text=True)
        payloads_b = {name: (out / name).read_bytes() for name in payloads_a}
        record("idempotent_byte_exact_rerun", first.returncode == second.returncode == 0 and payloads_a == payloads_b)

        code = "import importlib.util; p=importlib.util.spec_from_file_location('cold_compliance', r'" + str(SCRIPT) + "'); m=importlib.util.module_from_spec(p); p.loader.exec_module(m); print(m.C.SCHEMA_VERSION)"
        cold = subprocess.run([sys.executable, "-I", "-c", code], capture_output=True, text=True)
        record("cold_import_isolated", cold.returncode == 0 and cold.stdout.strip() == "source-review/v1" and not cold.stderr, cold.stderr)

    passed = sum(r["passed"] for r in RESULTS)
    print(json.dumps({"suite": "compliance_hostile", "passed": passed, "total": len(RESULTS), "failed": len(RESULTS)-passed}, ensure_ascii=False))
    return 0 if passed == len(RESULTS) else 1


if __name__ == "__main__":
    raise SystemExit(main())
