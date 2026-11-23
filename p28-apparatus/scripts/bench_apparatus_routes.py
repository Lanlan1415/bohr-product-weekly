"""Apparatus and technical-route drawing tests (EXAMPLE-ONLY, no formal answers)."""
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
CLI = HERE / "sourcebind.py"


def execute(spec: dict, root: Path, name: str):
    path = dump(root / f"{name}.json", spec)
    out = root / name
    cp = subprocess.run([sys.executable, "-X", "utf8", str(CLI), "--mode", "apparatus",
                         "--spec", str(path), "--out", str(out)], capture_output=True, text=True,
                        encoding="utf-8", errors="replace", timeout=90)
    result = json.loads((out / "result.json").read_text(encoding="utf-8"))
    return cp, result, out


def rich_route() -> dict:
    spec = base_spec("apparatus")
    spec["nodes"][3]["stage"] = 5
    spec["nodes"][1]["milestone"] = True
    spec["step_order"] = ["heat", "pump", "valve", "waste", "detector"]
    spec["materials"].append({"id": "m5", "name": "废液收集 W-104",
                              "source": "EXAMPLE Methods ¶5: waste drains to W-104", "version": "example-v1"})
    spec["components"].append("废液收集 W-104")
    spec["nodes"].append({"id": "waste", "label": "废液收集 W-104", "part_kind": "sink",
                          "kind": "sink", "evidence": "m5", "stage": 4, "category": "waste"})
    spec["categories"]["waste"] = "#D55E00"
    spec["connections"].append({"from": "valve", "to": "waste", "type": "flow",
                                "source": "EXAMPLE Methods ¶5: valve drains to W-104"})
    spec["edges"].append({"id": "waste-flow", "from": "valve", "to": "waste", "type": "flow",
                          "flow_kind": "waste", "label": "废液出口"})
    spec["connections"].append({"from": "detector", "to": "pump", "type": "flow",
                                "source": "EXAMPLE Methods recycle line: detector return to pump"})
    spec["edges"].append({"id": "return", "from": "detector", "to": "pump", "type": "flow",
                          "flow_kind": "material", "recycle": True, "label": "回流"})
    spec["legend_notes"].append("S01–S05 与 Methods 顺序一致；分流至 W-104，检测后回流至 P-101")
    return spec


def main() -> int:
    checks: list[dict] = []

    def record(name, ok, detail=""):
        checks.append({"name": name, "passed": bool(ok), "detail": str(detail)})
        print(("PASS" if ok else "FAIL"), name, ("— " + str(detail) if detail and name and not ok else ""))

    with tempfile.TemporaryDirectory(prefix="apparatus-routes-") as td:
        root = Path(td)
        spec = rich_route()
        cp, result, out = execute(spec, root, "four-flows")
        record("apparatus with source, valve/diverter, detector, waste sink and recycle is clean",
               cp.returncode == 0 and not result["findings"], {"exit": cp.returncode, "stdout": cp.stdout[-900:], "stderr": cp.stderr[-900:]})
        svg = (out / "figure.svg").read_text(encoding="utf-8")
        mapping = json.loads((out / "mapping.json").read_text(encoding="utf-8"))
        record("material/energy/information/waste channels have distinct real strokes and legends",
               all(token in svg for token in ("material / 物料", "energy / 能量", "information / 信息", "waste / 废料"))
               and 'stroke-dasharray="8,5"' in svg and 'stroke-dasharray="2,5"' in svg)
        record("sequential stages S01-S05 and non-crossing recycle are drawn",
               all(f"S{i:02d}" in svg for i in range(1, 6))
               and next(e for e in mapping["edges"] if e["recycle"])["route"]["kind"] == "feedback_arc"
               and result["checked"]["crossings"] == 0 and result["checked"]["feedback_arcs"] == 1)
        by_id = {n["id"]: n for n in mapping["nodes"]}
        recycle = next(e for e in mapping["edges"] if e["recycle"])
        record("recycle ends at actual pump top anchor rather than crossing the valve",
               recycle["end"] == [by_id["pump"]["center"][0], by_id["pump"]["bbox"][1]]
               and "<path" in svg and "废液出口" in svg)
        record("route labels stay on-canvas and circular parts contain their labels",
               recycle["route"]["control_y"] >= 34 and recycle["label_pos"][1] >= 16
               and abs((by_id["pump"]["bbox"][2] - by_id["pump"]["bbox"][0]) - (by_id["pump"]["bbox"][3] - by_id["pump"]["bbox"][1])) < .001
               and abs((by_id["detector"]["bbox"][2] - by_id["detector"]["bbox"][0]) - (by_id["detector"]["bbox"][3] - by_id["detector"]["bbox"][1])) < .001)
        record("source-declared milestone is rendered as a blue outline + legend",
               by_id["pump"]["milestone"] is True and "milestone / 里程碑" in svg and 'stroke="#0072B2" stroke-width="3.0"' in svg)
        h1 = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in out.iterdir() if p.is_file()}
        cp2, _, _ = execute(spec, root, "four-flows")
        h2 = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in out.iterdir() if p.is_file()}
        record("four-flow + recycle rendering is byte-idempotent", cp2.returncode == 0 and h1 == h2)

        ports = base_spec("apparatus")
        ports["edges"][0]["from_port"] = "E"
        ports["edges"][0]["to_port"] = "W"
        cp, result, out = execute(ports, root, "ports")
        mapping = json.loads((out / "mapping.json").read_text(encoding="utf-8"))
        by_id = {n["id"]: n for n in mapping["nodes"]}
        e = mapping["edges"][0]
        record("schemdraw-style named ports are geometrically exact",
               cp.returncode == 0 and e["start"][0] == by_id["heat"]["bbox"][2] and e["end"][0] == by_id["pump"]["bbox"][0]
               and e["declared_ports"] == [{"node": "heat", "port": "E"}, {"node": "pump", "port": "W"}])

        wrong = base_spec("apparatus")
        wrong["nodes"][2]["kind"] = "decision"
        cp, result, _ = execute(wrong, root, "decision-no-branch")
        record("decision without alternate output is blocked",
               cp.returncode == 4 and any(f["rule"] == "route.decision_without_branches" for f in result["findings"]))

        wrong = rich_route()
        wrong["nodes"][2]["kind"] = "decision"
        cp, result, _ = execute(wrong, root, "decision-branched")
        record("decision/diverter with real alternative streams is not a false positive", cp.returncode == 0)

        valid_route = base_spec("apparatus")
        valid_route["figure_kind"] = "route"
        cp, result, _ = execute(valid_route, root, "technical-route-open")
        record("figure_kind=route retains entry/exit and stage-sequence semantics",
               cp.returncode == 0 and result.get("figure_kind") == "route" and result.get("renderer_mode") == "apparatus")

        closed = base_spec("apparatus")
        closed["figure_kind"] = "route"
        closed["connections"].append({"from": "detector", "to": "heat", "type": "flow", "source": "EXAMPLE closed process loop"})
        closed["edges"].append({"id": "closed-cycle", "from": "detector", "to": "heat", "type": "flow", "flow_kind": "material", "recycle": True})
        cp, result, _ = execute(closed, root, "technical-route-no-entry-exit")
        record("closed technical loop without an entry/exit is blocked, not hidden by apparatus mode",
               cp.returncode == 4 and "route.no_entry" in {f["rule"] for f in result["findings"]}
               and "route.no_exit" in {f["rule"] for f in result["findings"]})

        wrong = base_spec("apparatus")
        wrong["connections"].append({"from": "detector", "to": "valve", "type": "flow", "source": "EXAMPLE unverified-looking reverse step"})
        wrong["edges"].append({"id": "reverse", "from": "detector", "to": "valve", "type": "flow", "flow_kind": "material"})
        cp, result, _ = execute(wrong, root, "unmarked-backflow")
        record("unmarked backward material flow is a review finding, never auto-recycled",
               cp.returncode == 3 and any(f["rule"] == "edge.backward_flow" for f in result["findings"]))

        wrong = base_spec("apparatus")
        wrong["nodes"][1]["stage"] = 7
        cp, result, _ = execute(wrong, root, "stage-order-mismatch")
        record("stage number contradicting Methods order is reported",
               cp.returncode == 3 and any(f["rule"] == "route.numbering_vs_text" for f in result["findings"]))

        wrong = base_spec("apparatus")
        wrong["nodes"][1]["stage"] = 1
        cp, result, _ = execute(wrong, root, "stage-duplicate")
        record("two units at one stage position are blocked",
               cp.returncode == 4 and any(f["rule"] == "route.stage_duplicate" for f in result["findings"]))

        wrong = base_spec("apparatus")
        wrong["components"].append("不存在的冷阱")
        cp, result, _ = execute(wrong, root, "bom-missing-part")
        record("missing bill-of-materials component is blocked",
               cp.returncode == 4 and any(f["rule"] == "apparatus.component_missing" for f in result["findings"]))

        wrong = base_spec("apparatus")
        wrong["edges"][0]["flow_kind"] = "plasma"
        cp, result, out = execute(wrong, root, "unknown-flow-kind")
        record("unknown physical flow channel is not silently displayed as material",
               cp.returncode == 4 and any(f["rule"] == "flow.kind_unknown" for f in result["findings"])
               and "UNRESOLVED FLOW" in (out / "figure.svg").read_text(encoding="utf-8"))

        wrong = base_spec("apparatus")
        wrong["materials"].append({"id": "m6", "name": "孤立缓冲瓶", "source": "EXAMPLE isolated part"})
        wrong["nodes"].append({"id": "orphan", "label": "孤立缓冲瓶", "part_kind": "vessel", "evidence": "m6", "layer": 5})
        cp, result, _ = execute(wrong, root, "orphan")
        record("unconnected apparatus part cannot masquerade as a connected process",
               cp.returncode == 3 and any(f["rule"] == "apparatus.orphan_component" for f in result["findings"]))

        report = {"schema_version": "apparatus-routes-bench/v1", "passed": sum(x["passed"] for x in checks),
                  "total": len(checks), "all_passed": all(x["passed"] for x in checks), "checks": checks,
                  "note": "EXAMPLE-ONLY synthetic apparatus and route bindings"}
        dump(HERE / "report_apparatus_routes.json", report)
        print("SUMMARY", report["passed"], "/", report["total"])
    return 0 if all(x["passed"] for x in checks) else 1


if __name__ == "__main__":
    raise SystemExit(main())
