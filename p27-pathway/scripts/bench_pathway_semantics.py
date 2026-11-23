"""Pathway-specific semantic/geometry acceptance tests for sourcebind.py.

All fixtures are EXAMPLE-ONLY synthetic source bindings, not formal test answers.
"""
from __future__ import annotations
import sys
sys.dont_write_bytecode = True
import copy
import hashlib
import json
import subprocess
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from bench_sourcebind import base_spec, dump  # noqa: E402
SOURCEBIND = HERE / "sourcebind.py"


def execute(spec: dict, root: Path, name: str, expected: int):
    path = dump(root / f"{name}.json", spec)
    out = root / name
    cp = subprocess.run([sys.executable, "-X", "utf8", str(SOURCEBIND), "--mode", "pathway",
                         "--spec", str(path), "--out", str(out)], capture_output=True, text=True,
                        encoding="utf-8", errors="replace", timeout=90)
    result = json.loads((out / "result.json").read_text(encoding="utf-8"))
    return cp, result, out


def rich_spec() -> dict:
    spec = base_spec("pathway")
    spec["compartments"][1]["layers"] = [1, 2, 3]
    spec["nodes"][1]["size"] = 4.0
    additions = [
        ("k1", "MAPK1", "P28482", 2),
        ("u1", "UBE2D1", "P51668", 2),
        ("r1", "NCK1", "P16333", 2),
        ("t1", "SLC1A1", "P43003", 3),
    ]
    for i, (nid, label, accession, layer) in enumerate(additions, len(spec["materials"]) + 1):
        mid = f"m{i}"
        spec["materials"].append({"id": mid, "name": label,
                                  "source": f"EXAMPLE mechanism relation involving {label}", "version": "example-v1"})
        spec["nodes"].append({"id": nid, "label": label, "kind": "protein", "evidence": mid,
                              "layer": layer, "compartment": "nucleus", "accession": accession,
                              "accession_source": "uniprot", "category": "protein"})
    edges = [
        ("phos", "p1", "k1", "phosphorylate", "predicted", False),
        ("ubi", "k1", "u1", "ubiquitinate", "hypothetical", False),
        ("rec", "u1", "r1", "recruit", "confirmed", False),
        ("tra", "r1", "t1", "transport", "predicted", False),
        ("feedback", "t1", "g1", "inhibit", "hypothetical", True),
    ]
    for eid, source, target, typ, confidence, feedback in edges:
        spec["connections"].append({"from": source, "to": target, "type": typ,
                                    "source": f"EXAMPLE {source} {typ} {target}", "confidence": confidence})
        spec["edges"].append({"id": eid, "from": source, "to": target, "type": typ,
                              "confidence": confidence, "feedback": feedback})
    spec["confidence_required"] = True
    spec["legend_notes"].append("节点面积正比于 size/表达量；虚线=预测，点线=假说；T1→G1=反馈抑制")
    return spec


def main() -> int:
    checks: list[dict] = []

    def record(name, ok, detail=""):
        checks.append({"name": name, "passed": bool(ok), "detail": str(detail)})
        print(("PASS" if ok else "FAIL"), name, ("— " + str(detail) if detail and not ok else ""))

    with tempfile.TemporaryDirectory(prefix="pathway-semantics-") as td:
        root = Path(td)
        spec = rich_spec()
        cp, result, out = execute(spec, root, "all-types", 0)
        record("8 relation semantics + branches + feedback + evidence styles generate clean",
               cp.returncode == 0 and not result["findings"],
               {"exit": cp.returncode, "stdout": cp.stdout[-700:], "stderr": cp.stderr[-700:]})
        mapping = json.loads((out / "mapping.json").read_text(encoding="utf-8"))
        svg = (out / "figure.svg").read_text(encoding="utf-8")
        types = {e["type"] for e in mapping["edges"]}
        record("activation/inhibition/modification/recruitment/transport/feedback all map to actual connectors",
               {"activate", "inhibit", "phosphorylate", "ubiquitinate", "recruit", "transport"} <= types
               and all(f"arrow-{t}" in svg for t in types)
               and 'data-feedback="true"' in svg and 'stroke-dasharray="8,5"' in svg and 'stroke-dasharray="2,5"' in svg)
        by_id = {n["id"]: n for n in mapping["nodes"]}
        width = lambda n: n["bbox"][2] - n["bbox"][0]
        record("size=4 doubles linear dimensions exactly once (area ratio 4)",
               abs(width(by_id["p1"]) / width(by_id["k1"]) - 2) < .01 and by_id["p1"]["size"] == 4.0)
        hashes1 = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in out.iterdir() if p.is_file()}
        cp2, result2, _ = execute(spec, root, "all-types", 0)
        hashes2 = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in out.iterdir() if p.is_file()}
        record("dense multi-compartment pathway remains byte-idempotent", cp2.returncode == 0 and hashes1 == hashes2)
        loop = next(e for e in mapping["edges"] if e["feedback"])
        record("feedback uses a reserved non-crossing arc above unrelated actors",
               loop["route"]["kind"] == "feedback_arc" and loop["route"]["control_y"] < min(n["bbox"][1] for n in mapping["nodes"])
               and result["checked"]["feedback_arcs"] == 1 and result["checked"]["crossings"] == 0
               and f"<path d=\"{loop['route']['d']}\"" in svg)

        wrong = base_spec("pathway")
        wrong["connections"][0]["type"] = "inhibit"
        cp, result, _ = execute(wrong, root, "type-mismatch", 4)
        record("source inhibition drawn as activation is blocked",
               cp.returncode == 4 and any(f["rule"] == "trace.relation_type_mismatch" for f in result["findings"]))

        wrong = base_spec("pathway")
        wrong["edges"][0]["from"], wrong["edges"][0]["to"] = "p1", "g1"
        cp, result, out = execute(wrong, root, "wrong-direction", 4)
        mapping = json.loads((out / "mapping.json").read_text(encoding="utf-8"))
        record("endpoint direction is not silently auto-reversed",
               cp.returncode == 4 and mapping["edges"][0]["from"] == "p1" and mapping["edges"][0]["to"] == "g1"
               and any(f["rule"] == "trace.connection_not_drawn" for f in result["findings"])
               and any(f["rule"] == "trace.edge_not_in_source" for f in result["findings"]))

        wrong = base_spec("pathway")
        wrong["materials"].append({"id": "m3", "name": "p53", "source": "EXAMPLE duplicate alias"})
        wrong["nodes"].append({"id": "dup", "label": "p53", "kind": "gene", "evidence": "m3", "layer": 0,
                               "compartment": "cytosol", "accession": "HGNC:11998", "accession_source": "hgnc", "category": "gene"})
        wrong["connections"].append({"from": "g1", "to": "dup", "type": "activate", "source": "EXAMPLE ambiguous step"})
        wrong["edges"].append({"id": "dup-edge", "from": "g1", "to": "dup", "type": "activate", "confidence": "confirmed"})
        cp, result, _ = execute(wrong, root, "alias-collision", 4)
        rules = {f["rule"] for f in result["findings"]}
        record("alias + same registry accession collision is blocked", "nomenclature.alias_collision" in rules and "nomenclature.accession_collision" in rules)

        distinct = base_spec("pathway")
        distinct["nodes"][1]["state_distinct"] = True
        distinct["nodes"][1]["state"] = "unmodified"
        distinct["materials"].append({"id": "m3", "name": "MDM2-pS166", "source": "EXAMPLE distinct modified state"})
        distinct["nodes"].append({"id": "p2", "label": "MDM2-pS166", "kind": "protein", "evidence": "m3",
                                  "layer": 1, "compartment": "nucleus", "accession": "Q00987", "accession_source": "uniprot",
                                  "category": "protein", "state_distinct": True, "state": "S166-phosphorylated"})
        distinct["connections"].append({"from": "g1", "to": "p2", "type": "activate", "source": "EXAMPLE modification produces MDM2-pS166"})
        distinct["edges"].append({"id": "state-edge", "from": "g1", "to": "p2", "type": "activate", "confidence": "confirmed"})
        cp, result, _ = execute(distinct, root, "distinct-states", 0)
        record("same accession + explicitly distinct molecular states is not a false collision", cp.returncode == 0)

        missing = base_spec("pathway")
        missing["confidence_required"] = True
        del missing["edges"][0]["confidence"]
        cp, result, _ = execute(missing, root, "confidence-missing", 3)
        record("required confidence missing is a visible review finding",
               cp.returncode == 3 and any(f["rule"] == "edge.confidence_missing" for f in result["findings"]))

        colour = base_spec("pathway")
        colour["nodes"][0]["color"] = "#56B4E9"
        colour["categories"]["gene"] = "#0072B2"
        cp, result, _ = execute(colour, root, "colour-mismatch", 3)
        record("node colour contradicting category legend is caught",
               cp.returncode == 3 and any(f["rule"] == "colour.category_mismatch" for f in result["findings"]))

        size = base_spec("pathway")
        size["nodes"][1]["size"] = 4
        size["legend_required"] = True
        cp, result, _ = execute(size, root, "size-unexplained", 3)
        record("size channel without explanation is reported",
               cp.returncode == 3 and any(f["rule"] == "legend.size_unexplained" for f in result["findings"]))

        report = {"schema_version": "pathway-semantics-bench/v1", "passed": sum(x["passed"] for x in checks),
                  "total": len(checks), "all_passed": all(x["passed"] for x in checks), "checks": checks,
                  "note": "EXAMPLE-ONLY synthetic mechanisms"}
        dump(HERE / "report_pathway_semantics.json", report)
        print("SUMMARY", report["passed"], "/", report["total"])
    return 0 if all(x["passed"] for x in checks) else 1


if __name__ == "__main__":
    raise SystemExit(main())
