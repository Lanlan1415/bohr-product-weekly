"""Minimal call example. Outputs are illustrative, not an official case result."""
import json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import benchkit as K

items = json.loads(Path("examples/itemset.json").read_text(encoding="utf-8"))
outputs = json.loads(Path("examples/outputs.json").read_text(encoding="utf-8"))

print("valid:", K.validate_itemset(items)["ok"])
record = K.run(items, outputs, {"rubric_version": "v1"})
print("total:", record["total"], "| failures:", record["failures_by_type"])
print("reproduce:", K.reproduce(items, outputs, {"rubric_version": "v1"}))
print("trace W1:", json.dumps(K.trace(record, "W1"), ensure_ascii=False)[:160])
