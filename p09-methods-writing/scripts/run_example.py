#!/usr/bin/env python3
"""Regenerate and verify the synthetic minimal example (never an official case)."""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXAMPLE = ROOT / "examples" / "minimal"


def run_script(script, *argv):
    return subprocess.run([sys.executable, "-I", str(ROOT / "scripts" / script), *argv],
                          check=False, text=True, capture_output=True)


def assemble(prose, out, work):
    proc = run_script("methodflow.py", "--case", str(EXAMPLE / "case.json"),
                      "--input-root", str(EXAMPLE), "--prose", str(prose) if prose else "",
                      "--work", str(work), "--out", str(out))
    return proc, json.loads((out / "result.json").read_text(encoding="utf-8"))


def main() -> int:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        good_proc, good = assemble(None, root / "good", root / "work")
        if good_proc.returncode != 3 or good["status"] != "partial":
            raise SystemExit("minimal case must be honestly partial: " + good_proc.stdout + good_proc.stderr)
        if good["number_audit"]["unsupported"]:
            raise SystemExit("good prose unexpectedly flagged")
        if good["datasets"][0]["status"] != "not_in_source":
            raise SystemExit("dataset absence was not preserved")
        if {row["name"] for row in good["parameter_table"]} != {"seed", "lr", "epochs", "batch_size", "dropout"}:
            raise SystemExit("unexpected parameter extraction")
        if good["steps"] != []:
            raise SystemExit("parameters must not be converted into protocol steps")
        if any(row["category"] == "randomization_blinding" and row["state"] == "reported"
               for row in good["coverage"]):
            raise SystemExit("RNG seed must not prove allocation randomisation/blinding")

        bad_path = root / "bad.md"
        bad_path.write_text("We train for 12 epochs and report 99.\n", encoding="utf-8")
        bad_proc, bad = assemble(bad_path, root / "bad", root / "work-bad")
        if bad_proc.returncode != 4 or not any(x["number"] == "99" for x in bad["number_audit"]["unsupported"]):
            raise SystemExit("invented 99 was not blocked by primary pipeline")

        audit_good = run_script("numeric_consistency.py", "--prose", str(EXAMPLE / "prose.md"),
                                "--table", str(root / "good" / "result.json"))
        if audit_good.returncode != 0:
            raise SystemExit("numeric_consistency should accept good prose")
        audit_bad = run_script("numeric_consistency.py", "--prose", str(bad_path),
                               "--table", str(root / "good" / "result.json"))
        if audit_bad.returncode != 1:
            raise SystemExit("numeric_consistency should reject invented 99")

        check = run_script("validate_result.py", str(root / "good" / "result.json"),
                           "--contract", str(ROOT / "resources" / "output_contract.json"),
                           "--case", str(EXAMPLE / "case.json"))
        if check.returncode != 0:
            raise SystemExit("validate_result failed:\n" + check.stdout + check.stderr)

    destination = EXAMPLE / "example_result.json"
    destination.write_text(json.dumps({
        "label": "EXAMPLE ONLY. Not an official contest case and not a prepared answer.",
        "result": good}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("example ok -> %s" % destination)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
