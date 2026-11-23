"""End-to-end acceptance bench for sourcebind.py (no repository scratch output).

Usage: python -X utf8 scripts/bench_sourcebind.py --mode schematic [--report report.json]
The same suite covers pathway/apparatus semantics when invoked with those modes.
"""
from __future__ import annotations

import sys
sys.dont_write_bytecode = True
import argparse
import copy
import hashlib
import json
import subprocess
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path

SCRIPT = Path(__file__).resolve().with_name("sourcebind.py")
sys.path.insert(0, str(SCRIPT.parent))
import sourcebind as sb  # noqa: E402


def dump(path: Path, value) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def base_spec(mode: str) -> dict:
    if mode == "pathway":
        return {
            "case_id": f"EXAMPLE-{mode}-clean", "figure_kind": mode, "title": "source-bound mechanism",
            "species": "human", "aliases": {"TP53": ["p53"]},
            "materials": [
                {"id": "m1", "name": "TP53", "source": "EXAMPLE Results ¶2: TP53 activates MDM2", "version": "example-v1"},
                {"id": "m2", "name": "MDM2", "source": "EXAMPLE Results ¶2: MDM2 is downstream", "version": "example-v1"}],
            "connections": [{"from": "g1", "to": "p1", "type": "activate", "source": "EXAMPLE Results ¶2: TP53 activates MDM2", "confidence": "confirmed"}],
            "compartments": [{"id": "cytosol", "label": "细胞质", "layers": [0]}, {"id": "nucleus", "label": "细胞核", "layers": [1]}],
            "nodes": [
                {"id": "g1", "label": "TP53", "kind": "gene", "evidence": "m1", "layer": 0,
                 "compartment": "cytosol", "accession": "HGNC:11998", "accession_source": "hgnc", "category": "gene"},
                {"id": "p1", "label": "MDM2", "kind": "protein", "evidence": "m2", "layer": 1,
                 "compartment": "nucleus", "accession": "Q00987", "accession_source": "uniprot", "category": "protein"}],
            "edges": [{"id": "r1", "from": "g1", "to": "p1", "type": "activate", "confidence": "confirmed"}],
            "categories": {"gene": "#56B4E9", "protein": "#009E73"},
            "legend_notes": ["箭头方向 = 来源所述上下游；区室 = 材料声明"],
        }
    if mode == "apparatus":
        return {
            "case_id": "EXAMPLE-apparatus-clean", "figure_kind": mode, "title": "source-bound apparatus and route",
            "materials": [
                {"id": "m1", "name": "加热器", "source": "EXAMPLE Methods ¶1: heated feed", "version": "example-v1"},
                {"id": "m2", "name": "循环泵 P-101", "source": "EXAMPLE Methods ¶2: pump P-101", "version": "example-v1"},
                {"id": "m3", "name": "膜阀 V-102", "source": "EXAMPLE Methods ¶3: valve V-102", "version": "example-v1"},
                {"id": "m4", "name": "检测器 D-103", "source": "EXAMPLE Methods ¶4: detector D-103", "version": "example-v1"}],
            "components": ["加热器", "循环泵 P-101", "膜阀 V-102", "检测器 D-103"],
            "connections": [
                {"from": "heat", "to": "pump", "type": "flow", "source": "EXAMPLE Methods ¶1-2: heat supplied to pump"},
                {"from": "pump", "to": "valve", "type": "flow", "source": "EXAMPLE Methods ¶2-3: material enters valve"},
                {"from": "valve", "to": "detector", "type": "flow", "source": "EXAMPLE Methods ¶3-4: detector signal"}],
            "nodes": [
                {"id": "heat", "label": "加热器", "part_kind": "vessel", "kind": "heater", "evidence": "m1", "stage": 1, "category": "energy"},
                {"id": "pump", "label": "循环泵 P-101", "part_kind": "pump", "kind": "pump", "evidence": "m2", "stage": 2, "category": "unit"},
                {"id": "valve", "label": "膜阀 V-102", "part_kind": "valve", "kind": "valve", "evidence": "m3", "stage": 3, "category": "unit"},
                {"id": "detector", "label": "检测器 D-103", "part_kind": "detector", "kind": "detector", "evidence": "m4", "stage": 4, "category": "signal"}],
            "edges": [
                {"id": "flow1", "from": "heat", "to": "pump", "type": "flow", "flow_kind": "energy", "label": "能量输入"},
                {"id": "flow2", "from": "pump", "to": "valve", "type": "flow", "flow_kind": "material", "label": "物料"},
                {"id": "flow3", "from": "valve", "to": "detector", "type": "flow", "flow_kind": "information", "label": "检测信息"}],
            "step_order": ["heat", "pump", "valve", "detector"],
            "categories": {"energy": "#E69F00", "unit": "#56B4E9", "signal": "#009E73"},
            "legend_notes": ["阶段编号与 Methods ¶1–4 一致；端口连接按 from→to"],
        }
    return {
        "case_id": "EXAMPLE-schematic-clean", "figure_kind": mode, "title": "source-bound schematic",
        "materials": [
            {"id": "m1", "name": "基底", "source": "EXAMPLE Methods ¶2: substrate", "version": "example-v1"},
            {"id": "m2", "name": "催化剂", "source": "EXAMPLE Methods ¶2: catalyst binds substrate", "version": "example-v1"},
            {"id": "m3", "name": "产物", "source": "EXAMPLE Results ¶1: product 42 nm", "version": "example-v1"}],
        "connections": [
            {"from": "a", "to": "b", "type": "bind", "source": "EXAMPLE Methods ¶2: catalyst deposited on substrate"},
            {"from": "b", "to": "c", "type": "activate", "source": "EXAMPLE Results ¶1: product forms on catalyst"}],
        "nodes": [
            {"id": "a", "label": "基底 <script>alert(1)</script>", "evidence": "m1", "layer": 0, "category": "reactant"},
            {"id": "b", "label": "催化剂：长标签用于自动换行与包围盒避让", "evidence": "m2", "layer": 1, "category": "agent", "value": 20, "unit": "min"},
            {"id": "c", "label": "产物", "evidence": "m3", "layer": 2, "category": "output", "value": 42, "unit": "nm"}],
        "edges": [{"id": "e1", "from": "a", "to": "b", "type": "bind"}, {"id": "e2", "from": "b", "to": "c", "type": "activate"}],
        "categories": {"reactant": "#56B4E9", "agent": "#009E73", "output": "#E69F00"},
        "legend_notes": ["数值与单位逐字来自示例材料；换行不改变标签或单位"],
    }


def run(args: list[str], cwd: Path) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, "-X", "utf8", str(SCRIPT), *args], cwd=cwd,
                          capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=90)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=("schematic", "pathway", "apparatus"), default="schematic")
    ap.add_argument("--report")
    args = ap.parse_args()
    checks: list[dict] = []

    def record(name: str, ok: bool, detail=""):
        checks.append({"name": name, "passed": bool(ok), "detail": str(detail)})
        print(("PASS" if ok else "FAIL"), name, ("— " + str(detail) if detail and not ok else ""))

    def invoke(name: str, cli: list[str], expected: int, cwd: Path):
        cp = run(cli, cwd)
        result_path = Path(cli[cli.index("--out") + 1]) / "result.json"
        result = json.loads(result_path.read_text(encoding="utf-8")) if result_path.exists() else {}
        record(name, cp.returncode == expected and bool(result), {"exit": cp.returncode, "expected": expected, "stdout": cp.stdout[-500:], "stderr": cp.stderr[-800:]})
        return cp, result

    with tempfile.TemporaryDirectory(prefix=f"sourcebind-{args.mode}-") as td:
        root = Path(td)
        spec = base_spec(args.mode)
        spec_path = dump(root / "spec.json", spec)
        case = {"case_id": spec["case_id"], "reviewer_note": "CASE-VALUE-UNCHANGED",
                "output_contract": {"fields": ["case_id", "editable_source", "exports", "mapping_json", "figure_audit", "sources", "uncertainty", "visual_check", "reviewer_note"]}}
        case_path = dump(root / "case.json", case)
        out = root / "clean"
        cp, result = invoke("clean baseline generates SVG/PNG/PDF and resolves fields-schema contract",
                            ["--mode", args.mode, "--spec", str(spec_path), "--case", str(case_path), "--out", str(out)], 0, root)
        baseline_ok = cp.returncode == 0
        if baseline_ok:
            try:
                assert result["case_id"] == case["case_id"]
                assert result["reviewer_note"] == "CASE-VALUE-UNCHANGED"
                assert result["output_contract"] == case["output_contract"]
                assert result["contract_field_values"]["exports"] == result["exports"]
                assert result["visual_check"].startswith("not performed")
                assert {x["format"] for x in result["exports"]} == {"svg", "png", "pdf"}
                assert all(x["magic_ok"] and x["bytes"] > 1000 for x in result["exports"])
                assert next(x for x in result["exports"] if x["format"] == "png")["dpi"] >= 299
                assert next(x for x in result["exports"] if x["format"] == "pdf")["font_embedded"]
                assert result["checked"]["node_overlaps"] == 0
                svg = (out / "figure.svg").read_text(encoding="utf-8")
                ET.fromstring(svg)
                assert "<script" not in svg.lower()
                assert args.mode != "schematic" or "&lt;script&gt;" in svg
                assert args.mode != "pathway" or "arrow-activate" in svg
                assert args.mode != "apparatus" or all(token in svg for token in ("stroke-dasharray=\"8,5\"", "energy / 能量", "<circle"))
                baseline_ok = True
            except Exception as exc:
                baseline_ok = False
                record("clean artifact semantics, XML safety, units and export magic", False, repr(exc))
            else:
                record("clean artifact semantics, XML safety, units and export magic", True)
        first_hashes = {name: digest(out / name) for name in ("figure.svg", "figure.png", "figure.pdf", "mapping.json", "spec.json", "result.json")} if baseline_ok else {}
        cp2, _ = invoke("idempotent rerun exit", ["--mode", args.mode, "--spec", str(spec_path), "--case", str(case_path), "--out", str(out)], 0, root)
        second_hashes = {name: digest(out / name) for name in first_hashes}
        record("SVG/PNG/PDF/mapping/spec/result are byte-identical on rerun", first_hashes == second_hashes,
               {k: (first_hashes.get(k), second_hashes.get(k)) for k in first_hashes if first_hashes.get(k) != second_hashes.get(k)})

        # --case-id must work even when the output directory does not exist yet.
        _, fresh = invoke("case-id on a fresh output directory creates the full figure",
                          ["--mode", args.mode, "--spec", str(spec_path), "--case-id", "fresh-output-case", "--out", str(root / "fresh-case-id")], 0, root)
        record("fresh case-id is reflected in every contract surface",
               fresh.get("case_id") == "fresh-output-case" and (root / "fresh-case-id" / "figure.svg").exists())

        # Flat output_contract and independent spec case_id passthrough.
        flat_spec = copy.deepcopy(spec)
        flat_spec["deliverable_svg"] = {"format": "svg", "note": "case descriptor must survive"}
        flat_spec["output_contract"] = {"case_id": "echo", "status": "actual", "exports": "actual",
                                        "deliverable_svg": "echo descriptor", "not_derivable": "unknown"}
        flat_path = dump(root / "flat-spec.json", flat_spec)
        _, flat = invoke("flat contract accepted without crash", ["--mode", args.mode, "--spec", str(flat_path), "--out", str(root / "flat")], 0, root)
        record("flat contract every key echoed; unknown null + limit; case descriptor preserved",
               flat.get("case_id") == flat_spec["case_id"] and flat.get("output_contract", {}).get("deliverable_svg") == flat_spec["deliverable_svg"]
               and flat.get("output_contract", {}).get("not_derivable") is None
               and any("not_derivable" in x for x in flat.get("limits", [])))

        bad_json = root / "bad.json"; bad_json.write_text("{broken", encoding="utf-8")
        _, bad = invoke("malformed spec refuses with exit 5", ["--mode", args.mode, "--spec", str(bad_json), "--case", str(case_path), "--out", str(root / "bad")], 5, root)
        record("malformed refusal is structured and preserves case_id + contract fields",
               bad.get("status") == "undetermined" and bad.get("case_id") == case["case_id"]
               and bad.get("output_contract") == case["output_contract"]
               and set(bad.get("contract_field_values", {})) == set(case["output_contract"]["fields"]))
        array_path = dump(root / "array.json", [1, 2, 3])
        invoke("non-object spec refuses with exit 5", ["--mode", args.mode, "--spec", str(array_path), "--out", str(root / "array")], 5, root)
        invoke("unreadable case refuses with exit 5", ["--mode", args.mode, "--spec", str(spec_path), "--case", str(bad_json), "--out", str(root / "badcase")], 5, root)
        empty = copy.deepcopy(spec); empty["nodes"] = []
        empty_path = dump(root / "empty.json", empty)
        invoke("no drawable nodes refuses with exit 5", ["--mode", args.mode, "--spec", str(empty_path), "--out", str(root / "empty")], 5, root)
        bad_canvas = copy.deepcopy(spec); bad_canvas["canvas_mm"] = [150, float("nan")]
        bad_canvas_path = dump(root / "bad-canvas.json", bad_canvas)
        invoke("non-finite canvas refuses with exit 5", ["--mode", args.mode, "--spec", str(bad_canvas_path), "--out", str(root / "badcanvas")], 5, root)

        dangling = copy.deepcopy(spec); dangling["edges"][0]["to"] = "GHOST"
        dangling_path = dump(root / "dangling.json", dangling)
        _, dr = invoke("dangling edge yields blocked artifact not traceback", ["--mode", args.mode, "--spec", str(dangling_path), "--case", str(case_path), "--out", str(root / "dangling")], 4, root)
        record("dangling refusal names endpoint and still leaves valid SVG",
               any(f["rule"] == "edge.dangling" for f in dr.get("findings", [])) and (root / "dangling" / "figure.svg").exists())
        unknown = copy.deepcopy(spec); unknown["edges"][0]["type"] = " activat "
        unknown_path = dump(root / "unknown.json", unknown)
        _, ur = invoke("unknown relation blocked with exit 4", ["--mode", args.mode, "--spec", str(unknown_path), "--case", str(case_path), "--out", str(root / "unknown")], 4, root)
        unknown_svg = (root / "unknown" / "figure.svg").read_text(encoding="utf-8")
        record("unknown relation is visible as unresolved, never silently restyled",
               any(f["rule"] == "edge.type_unknown" for f in ur.get("findings", [])) and "UNRESOLVED RELATION" in unknown_svg)

        # Tamper the already-written connector geometry: the independent XML audit
        # must reject it even though the input spec remains correct.
        tampered = root / "tampered.svg"; tampered.write_bytes((out / "figure.svg").read_bytes())
        tree = ET.parse(tampered); ns = {"s": sb.SVG_NS}
        line = tree.find(".//s:g[@id='layer-edges']/s:g/s:line", ns)
        x1, x2 = line.get("x1"), line.get("x2"); y1, y2 = line.get("y1"), line.get("y2")
        line.set("x1", x2); line.set("x2", x1); line.set("y1", y2); line.set("y2", y1)
        tree.write(tampered, encoding="utf-8", xml_declaration=True)
        norm, _, _ = sb.normalise_spec(spec, args.mode)
        layout, _ = sb.make_layout(norm, args.mode)
        nodes, edges = sb.semantic_records(norm, layout)
        findings, _ = sb.structure_audit(norm, layout, nodes, edges, tampered)
        record("reversed SVG ports are caught independently of the input spec",
               any(f["rule"] == "edge.geometry_mismatch" for f in findings))
        line.set("marker-end", "url(#arrow-inhibit)" if args.mode != "pathway" else "url(#arrow-bind)")
        tree.write(tampered, encoding="utf-8", xml_declaration=True)
        findings2, _ = sb.structure_audit(norm, layout, nodes, edges, tampered)
        record("tampered arrowhead semantics are caught", any(f["rule"] == "edge.arrowhead_mismatch" for f in findings2))

        if args.mode == "pathway":
            wrong = copy.deepcopy(spec); wrong["nodes"][1]["compartment"] = "cytosol"
            wrong_path = dump(root / "wrong-compartment.json", wrong)
            _, wr = invoke("biological compartment mismatch is high and exits 4", ["--mode", args.mode, "--spec", str(wrong_path), "--case", str(case_path), "--out", str(root / "wrongcomp")], 4, root)
            record("compartment finding points at the misplaced entity", any(f["rule"] == "compartment.mismatch" for f in wr.get("findings", [])))
        if args.mode == "apparatus":
            recycle = copy.deepcopy(spec)
            recycle["connections"].append({"from": "detector", "to": "pump", "type": "flow", "source": "EXAMPLE Methods recycle loop"})
            recycle["edges"].append({"id": "return", "from": "detector", "to": "pump", "type": "flow", "flow_kind": "material", "recycle": True, "label": "回流"})
            recycle_path = dump(root / "recycle.json", recycle)
            cp_rec, rr = invoke("declared recycle + stage feedback renders without false backward-flow block", ["--mode", args.mode, "--spec", str(recycle_path), "--case", str(case_path), "--out", str(root / "recycle")], 0, root)
            record("recycle and flow channels survive in mapping", rr.get("reproducibility", {}).get("deterministic") is True and any(e.get("recycle") for e in json.loads((root / "recycle" / "mapping.json").read_text(encoding="utf-8"))["edges"]) if cp_rec.returncode == 0 else False)

        # Source-preserving edit and destructive-address refusal.
        edits = [{"op": "rename", "target_id": spec["nodes"][0]["id"], "new_label": "编辑后的源标签"},
                 {"op": "recolour", "target_id": spec["nodes"][0]["id"], "color": "#56B4E9"},
                 {"op": "set_relation_type", "target_id": spec["edges"][0]["id"], "new_type": "inhibit"}]
        edits_path = dump(root / "edits.json", edits)
        edit_out = root / "edit"
        _, er = invoke("source-preserving SVG edit is structured", ["--edit-svg", str(out / "figure.svg"), "--edits", str(edits_path), "--case", str(case_path), "--out", str(edit_out)], 3, root)
        edited_text = (edit_out / "figure.svg").read_text(encoding="utf-8")
        ET.fromstring(edited_text)
        record("edit preserves XML/other elements and updates addressed text/marker",
               er.get("edit", {}).get("unrelated_elements_preserved") is True and "编辑后的源标签" in edited_text
               and 'data-type="inhibit"' in edited_text and len(er.get("change_records", [])) == 3)
        unknown_edit = dump(root / "bad-edit.json", [{"op": "rename", "target_id": "NO-SUCH-ID", "new_label": "x"}])
        invoke("unknown SVG edit target refuses with exit 5", ["--edit-svg", str(out / "figure.svg"), "--edits", str(unknown_edit), "--out", str(root / "bad-edit-out")], 5, root)
        invoke("missing SVG edit instructions refuse with exit 5", ["--edit-svg", str(out / "figure.svg"), "--out", str(root / "missing-edit-out")], 5, root)
        invoke("case-only input without semantic extraction refuses with exit 5", ["--case", str(case_path), "--mode", args.mode, "--out", str(root / "case-only")], 5, root)

        report = {"schema_version": "sourcebind-bench/v1", "mode": args.mode,
                  "passed": sum(c["passed"] for c in checks), "total": len(checks),
                  "all_passed": all(c["passed"] for c in checks), "checks": checks,
                  "note": "EXAMPLE-ONLY synthetic source-bound specs; not formal test answers"}
        if args.report:
            dump(Path(args.report), report)
        print("SUMMARY", report["passed"], "/", report["total"], "mode=", args.mode)
        if args.report:
            print("REPORT", str(Path(args.report).resolve()))
    return 0 if all(c["passed"] for c in checks) else 1


if __name__ == "__main__":
    raise SystemExit(main())
