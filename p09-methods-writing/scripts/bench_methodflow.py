"""End-to-end method/evidence bench; all scientific fixtures are synthetic examples."""
from __future__ import annotations

import copy
import json
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import methodflow as M  # noqa: E402

CONFIG = {
    "experiment": {
        "design": "randomized controlled", "variables": {"independent": "coating", "outcome": "uptake"},
        "control": {"name": "uncoated", "version": "v1"},
        "equipment": {"name": "Microscope X", "manufacturer": "Acme"},
        "dataset": {"name": "Cells2025", "version": "v1.2", "split": "80/20", "preprocessing": "filter"},
        "sample_size": 6, "replicates": 3, "randomization": "computer allocation",
        "blinding": "outcome assessors", "statistics": {"test": "t-test", "alpha": 0.05},
        "ethics": {"approval": "IRB-42", "consent": "written"}, "safety": "BSL-1",
        "reproducibility": {"commit": "abc123", "environment": "python 3.11", "seed": 42,
                             "data_version": "v1.2"},
        "parameters": {"learning_rate": 0.001, "batch_size": 32},
        "limitation": "small sample limits generalisation"
    }
}
PROSE = """# Methods
We used a randomized controlled design with coating and uncoated control.
Samples were prepared at 25 °C for 30 min with n = 6 and 3 independent replicates.
We trained with learning_rate 0.001 and batch_size 32 using random seed 42.
Cells2025 v1.2 was split 80/20; outcomes were compared with a t-test.
"""


def main() -> int:
    rows = []
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)

        def fixture(name, prose=PROSE):
            d = root / name; d.mkdir()
            (d / "config.json").write_text(json.dumps(CONFIG), encoding="utf-8")
            (d / "protocol.md").write_text("1. Prepare samples at 25 °C for 30 min.\n"
                                           "2. Record the outcome for each sample.\n", encoding="utf-8")
            (d / "methods.md").write_text(prose, encoding="utf-8")
            case = {"case_id": f"methods-{name}", "command": "python train.py --config config.json",
                    "materials": {"config": "config.json", "protocol": "protocol.md", "prose": "methods.md"},
                    "output_contract": {"case_id": "id", "status": "engine", "parameter_table": "engine",
                                        "coverage": "engine", "case_value": "case", "unknown": "unknown"},
                    "case_value": {"keep": True}}
            cp = d / "case.json"; cp.write_text(json.dumps(case), encoding="utf-8")
            return d, cp, case

        def run(name, mutator=None, expected_status=None, expected_rc=None, expected_rules=()):
            d, cp, case = fixture(name)
            if mutator:
                mutator(d, cp, case)
            result, rc = M.build(M.load_case(cp, None), cp, d, "", d, d / "out")
            fired = {f["rule"] for f in result["findings"]}
            ok = all(rule in fired for rule in expected_rules)
            if expected_status:
                ok = ok and result["status"] == expected_status
            if expected_rc is not None:
                ok = ok and rc == expected_rc
            rows.append({"scenario": name, "pass": ok, "status": result["status"], "exit": rc,
                         "fired": sorted(fired)})
            return d, cp, case, result, rc

        d, cp, case, r, rc = run("complete_evidence_clean", expected_status="success", expected_rc=0)
        rows[-1]["pass"] = rows[-1]["pass"] and len(r["steps"]) == 2 \
            and all(x["state"] != "missing" for x in r["coverage"]) \
            and r["case_value"] == {"keep": True} and r["unknown"] is None \
            and not r["number_audit"]["unsupported"]

        def unsupported(d, cp, case):
            (d / "methods.md").write_text(PROSE + "The fabricated accuracy was 99.6.\n", encoding="utf-8")
        run("unsupported_number_blocked", unsupported, "partial", 4, ["methods.unsupported_prose_number"])

        def params_only(d, cp, case):
            (d / "protocol.md").unlink()
            case["materials"].pop("protocol")
            # Remove the sentence whose only evidence was the deleted protocol;
            # this isolates the steps-vs-parameters assertion from numeric support.
            (d / "methods.md").write_text(PROSE.replace(
                "Samples were prepared at 25 °C for 30 min with n = 6 and 3 independent replicates.\n",
                "We analysed n = 6 samples with 3 independent replicates.\n"), encoding="utf-8")
            cp.write_text(json.dumps(case), encoding="utf-8")
        d, cp, case, r, rc = run("parameters_are_not_steps", params_only, "partial", 3)
        rows[-1]["pass"] = rows[-1]["pass"] and r["steps"] == [] \
            and any(x["category"] == "steps" and x["state"] == "missing" for x in r["coverage"])

        def seed_not_randomisation(d, cp, case):
            cfg = copy.deepcopy(CONFIG); cfg["experiment"].pop("randomization"); cfg["experiment"].pop("blinding")
            (d / "config.json").write_text(json.dumps(cfg), encoding="utf-8")
        d, cp, case, r, rc = run("rng_seed_not_allocation", seed_not_randomisation, "partial", 3)
        rows[-1]["pass"] = rows[-1]["pass"] and any(
            x["category"] == "randomization_blinding" and x["state"] == "missing" for x in r["coverage"])

        def justified_na(d, cp, case):
            cfg = copy.deepcopy(CONFIG); cfg["experiment"].pop("randomization"); cfg["experiment"].pop("blinding")
            (d / "config.json").write_text(json.dumps(cfg), encoding="utf-8")
            case["coverage_overrides"] = {"randomization_blinding": {
                "status": "not_applicable", "rationale": "computational fixed-split benchmark; no allocation or assessor",
                "source": "task.md fixed dataset protocol"}}
            cp.write_text(json.dumps(case), encoding="utf-8")
        d, cp, case, r, rc = run("not_applicable_requires_source", justified_na, "success", 0)
        rows[-1]["pass"] = rows[-1]["pass"] and any(
            x["category"] == "randomization_blinding" and x["state"] == "not_applicable" for x in r["coverage"])

        def unjustified_na(d, cp, case):
            cfg = copy.deepcopy(CONFIG); cfg["experiment"].pop("randomization"); cfg["experiment"].pop("blinding")
            (d / "config.json").write_text(json.dumps(cfg), encoding="utf-8")
            case["coverage_overrides"] = {"randomization_blinding": {"status": "not_applicable"}}
            cp.write_text(json.dumps(case), encoding="utf-8")
        run("unjustified_na_rejected", unjustified_na, "partial", 3, ["methods.coverage_gap"])

        def conflict(d, cp, case):
            (d / "second.json").write_text('{"experiment":{"reproducibility":{"seed": 43}}}', encoding="utf-8")
            case["materials"]["logs"] = "second.json"; cp.write_text(json.dumps(case), encoding="utf-8")
        run("same_key_conflict", conflict, "partial", 4, ["methods.parameter_conflict"])

        def missing_prose(d, cp, case):
            (d / "methods.md").unlink()
        run("missing_prose_partial", missing_prose, "partial", 3, ["methods.prose_missing"])

        def missing_config(d, cp, case):
            case["materials"]["config"] = "absent.json"; cp.write_text(json.dumps(case), encoding="utf-8")
        run("missing_declared_config_refused", missing_config, "refused", 5, ["methods.input_unreadable"])

        # Nested JSON extraction uses full dotted paths and keeps locators.
        nested = M.extract_json(CONFIG, root / "virtual.json")
        ok = any(x["name"] == "experiment.parameters.learning_rate" and x["value"] == 0.001
                 and x["locator"].startswith("JSON path") for x in nested)
        rows.append({"scenario": "nested_config_with_locator", "pass": ok, "fired": []})

        # CLI malformed case: structured exit 5 and no traceback.
        d, cp, case = fixture("bad_json"); cp.write_text("{broken", encoding="utf-8")
        p = subprocess.run([sys.executable, "-B", "-I", str(HERE / "methodflow.py"), "--case", str(cp),
                            "--input-root", str(d), "--work", str(d), "--out", str(d / "badout")],
                           capture_output=True, text=True, timeout=30)
        try:
            refused = json.loads((d / "badout" / "result.json").read_text(encoding="utf-8"))
            # A malformed case cannot reveal its own contract fields; refusal still
            # includes the top-level id slot and never fabricates those unknown names.
            ok = p.returncode == 5 and refused["status"] == "refused" and "Traceback" not in p.stderr \
                and "case_id" in refused and refused["case_id"] == "unknown"
        except Exception:
            ok = False
        rows.append({"scenario": "malformed_case_structured_refusal", "pass": ok, "fired": []})

        # Idempotency and engine-over-case contract precedence through the actual CLI.
        d, cp, case = fixture("idempotent"); case["status"] = "pretend-success"
        cp.write_text(json.dumps(case), encoding="utf-8")
        cmd = [sys.executable, "-B", "-I", str(HERE / "methodflow.py"), "--case", str(cp),
               "--input-root", str(d), "--work", str(d), "--out", str(d / "out")]
        a = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        first = (d / "out" / "result.json").read_bytes()
        b = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        second = (d / "out" / "result.json").read_bytes()
        payload = json.loads(first)
        ok = (a.returncode == b.returncode == 0 and first == second and payload["status"] == "success"
              and "Traceback" not in a.stderr + b.stderr)
        rows.append({"scenario": "cli_idempotency_engine_precedence", "pass": ok, "fired": []})

    for row in rows:
        print(("PASS" if row["pass"] else "FAIL") + f"  {row['scenario']:<40} {row.get('fired', [])}")
    passed = sum(bool(x["pass"]) for x in rows)
    report = {"schema_version": "methodflow-bench/v1", "scenarios": rows,
              "totals": {"passed": passed, "of": len(rows)}}
    (HERE / "report_methodflow.json").write_text(json.dumps(report, ensure_ascii=False, indent=2),
                                                  encoding="utf-8")
    print(f"\n{passed}/{len(rows)} pass")
    return 0 if passed == len(rows) else 1


if __name__ == "__main__":
    raise SystemExit(main())
