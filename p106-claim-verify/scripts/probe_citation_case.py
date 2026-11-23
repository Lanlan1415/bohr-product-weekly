"""Adversarial CLI/contract/idempotence probes for citecheck."""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

SCRIPT = Path(__file__).resolve().with_name("citecheck.py")
EXAMPLE = Path(__file__).resolve().parents[1] / "examples" / "case.json"
RESULTS = []


def record(name, passed, detail=""):
    RESULTS.append({"probe": name, "passed": bool(passed), "detail": detail})
    if not passed:
        print("FAIL", name, detail)


def execute(root, raw, extra=None):
    root.mkdir(parents=True, exist_ok=True)
    case = root / "case.json"
    case.write_text(raw if isinstance(raw, str) else json.dumps(raw, ensure_ascii=False), encoding="utf-8")
    out = root / "out"
    proc = subprocess.run([sys.executable, "-I", str(SCRIPT), "--case", str(case), "--out", str(out)] + (extra or []), capture_output=True, text=True)
    path = out / "result.json"
    result = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}
    return proc, result, out


def main():
    with tempfile.TemporaryDirectory(prefix="cite-probe-") as tmp:
        root = Path(tmp)
        good = json.loads(EXAMPLE.read_text(encoding="utf-8"))
        for name, raw, expected in (("malformed_json", "{broken", 5), ("case_not_object", [1, 2], 5),
                                    ("missing_manuscript", {"case_id": "empty", "output_contract": ["audit_report", "unknown"]}, 5)):
            proc, result, out = execute(root / name, raw)
            record(name + "_structured_refusal", proc.returncode == expected and result.get("status") == "undetermined"
                   and result.get("case_id") in ({}, None) if name == "malformed_json" else proc.returncode == expected and result.get("status") == "undetermined", proc.stderr)
            record(name + "_no_traceback", "Traceback" not in proc.stderr)

        proc, result, _ = execute(root / "refusal_contract", {"case_id": "refusal-1", "status": "pretend-clean",
                                                               "output_contract": ["status", "audit_report", "missing_field"]})
        record("refusal_contract_null_and_engine_status", result.get("case_id") == "refusal-1" and result.get("status") == "undetermined"
               and "audit_report" in result and "missing_field" in result and result["missing_field"] is None
               and any("missing_field" in x for x in result.get("limits", [])), result)

        case = dict(good)
        case["output_contract"] = 42
        proc, result, _ = execute(root / "bad_contract_type", case)
        record("bad_contract_type_degrades", proc.returncode == 0 and any("unsupported type" in x for x in result.get("limits", [])), result)

        case = dict(good)
        case["output_contract"] = [{"field": "case_id"}, {"name": "audit_report"}, {"key": "missing_other"}, 7]
        case["missing_other"] = "case-carried-value"
        proc, result, _ = execute(root / "object_contract", case)
        record("object_contract_fields_and_case_value", result.get("case_id") == "cite-smoke-clean"
               and result.get("missing_other") == "case-carried-value" and len(result.get("output_contract_fields", [])) == 3, result)

        case = dict(good)
        case["references"] = 7
        case["claims"] = [None, "bad", 3]
        case["sources"] = [None, 5]
        proc, result, _ = execute(root / "wrong_nested_shapes", case)
        record("wrong_nested_shapes_no_crash", proc.returncode in (0, 3, 4, 5) and result.get("case_id") == "cite-smoke-clean" and "Traceback" not in proc.stderr, proc.stderr)

        case = dict(good)
        case["manuscript_text"] = None
        proc, result, _ = execute(root / "missing_material", case)
        record("missing_material_structured", proc.returncode == 5 and result.get("status") == "undetermined" and not result.get("citation_checks"), result)

        case = dict(good)
        case["manuscript_text"] = None
        case["materials"] = [{"name": "paper", "role": "manuscript", "path": "does-not-exist.pdf"}]
        proc, result, _ = execute(root / "unreadable_pdf", case)
        record("unreadable_pdf_no_fake_text", proc.returncode == 5 and result.get("status") == "undetermined" and not result.get("citation_checks"), result)

        out = root / "idem"
        args = [sys.executable, "-I", str(SCRIPT), "--case", str(EXAMPLE), "--out", str(out)]
        first = subprocess.run(args, capture_output=True, text=True)
        payloads_a = {name: (out / name).read_bytes() for name in ("result.json", "audit_report.md", "run_log.json")}
        second = subprocess.run(args, capture_output=True, text=True)
        payloads_b = {name: (out / name).read_bytes() for name in payloads_a}
        record("idempotent_byte_exact_rerun", first.returncode == second.returncode == 0 and payloads_a == payloads_b)

        code = "import importlib.util; p=importlib.util.spec_from_file_location('cold_cite', r'" + str(SCRIPT) + "'); m=importlib.util.module_from_spec(p); p.loader.exec_module(m); print(m.C.SCHEMA_VERSION)"
        cold = subprocess.run([sys.executable, "-I", "-c", code], capture_output=True, text=True)
        record("cold_import_isolated", cold.returncode == 0 and cold.stdout.strip() == "source-review/v1" and not cold.stderr, cold.stderr)

    passed = sum(r["passed"] for r in RESULTS)
    print(json.dumps({"suite": "citation_hostile", "passed": passed, "total": len(RESULTS), "failed": len(RESULTS)-passed}, ensure_ascii=False))
    return 0 if passed == len(RESULTS) else 1


if __name__ == "__main__":
    raise SystemExit(main())
