#!/usr/bin/env python3
"""XML/structure/bounds/idempotence checks for actual mind-map artifacts."""
from __future__ import annotations

import copy
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import secrun  # noqa: E402

SPEC = json.loads((HERE.parent / "examples" / "spec.json").read_text(encoding="utf-8"))
SVG = "{http://www.w3.org/2000/svg}"
XLINK = "{http://www.w3.org/1999/xlink}href"
passed = failed = 0


def check(name, condition, detail=""):
    global passed, failed
    if condition:
        passed += 1
        print("PASS", name)
    else:
        failed += 1
        print("FAIL", name, detail)


def run(root, name, spec=None, raw=None):
    spec_path = root / (name + ".json")
    spec_path.write_text(raw if raw is not None else json.dumps(spec, ensure_ascii=False), encoding="utf-8")
    out = root / name
    result = secrun.build_and_audit(spec_path, out)
    return out, result


def boxes(svg_path):
    root = ET.parse(svg_path).getroot()
    width, height = int(root.attrib["width"]), int(root.attrib["height"])
    boxes = []
    for node in root.findall(".//%sg[@data-node-id]" % SVG):
        x, y = map(float, re.fullmatch(r"translate\((-?\d+(?:\.\d+)?) (-?\d+(?:\.\d+)?)\)", node.attrib["transform"]).groups())
        rect = node.find(".//%srect" % SVG)
        w, h = float(rect.attrib["width"]), float(rect.attrib["height"])
        texts = [float(t.attrib.get("y", 0)) for t in node.findall(".//%stext" % SVG)]
        boxes.append((node.attrib["data-node-id"], x, y, w, h, texts))
    return width, height, boxes


def independent_bounds(svg_path):
    width, height, items = boxes(svg_path)
    overlap, bounds = [], []
    for i, (aid, ax, ay, aw, ah, texts) in enumerate(items):
        if ax < 0 or ay < 0 or ax + aw > width or ay + ah > height or any(y < 0 or y > ah for y in texts):
            bounds.append(aid)
        for bid, bx, by, bw, bh, _ in items[i + 1:]:
            if min(ax + aw, bx + bw) - max(ax, bx) > 0 and min(ay + ah, by + bh) - max(ay, by) > 0:
                overlap.append((aid, bid))
    return overlap, bounds, items


def main():
    with tempfile.TemporaryDirectory(prefix="mindmap_render_") as td:
        root = Path(td)
        out, result = run(root, "clean", SPEC)
        artifacts = {"mindmap.svg", "mindmap.mm", "mindmap.html", "mindmap.json", "layout.json", "result.json"}
        check("01_complete_real_artifacts_clean", result["status"] == "clean" and result["findings"] == []
              and artifacts <= {p.name for p in out.iterdir()})
        xml_root = ET.parse(out / "mindmap.svg").getroot()
        nodes = xml_root.findall(".//%sg[@data-node-id]" % SVG)
        relations = xml_root.findall(".//%spath[@data-edge-id]" % SVG)
        check("02_svg_structure_and_relations", xml_root.tag == SVG + "svg" and len(nodes) == 8 and len(relations) == 3
              and all("data-basis" in r.attrib for r in relations))
        overlap, bounds, items = independent_bounds(out / "mindmap.svg")
        check("03_independent_svg_rect_no_overlap", not overlap and not bounds, str((overlap, bounds)))
        layout = json.loads((out / "layout.json").read_text(encoding="utf-8"))
        check("04_layout_json_matches_svg", {x[0] for x in items} == {x["id"] for x in layout["nodes"]}
              and layout["diagnostics"]["overlap_pairs"] == [] and layout["diagnostics"]["boundary_violations"] == [])

        mm_root = ET.parse(out / "mindmap.mm").getroot()
        check("05_freemind_one_root_and_nested_graph", mm_root.tag == "map" and len(mm_root.findall("node")) == 1
              and len(mm_root.findall(".//node")) == 8 and len(mm_root.findall(".//arrowlink")) == 3)
        structured = json.loads((out / "mindmap.json").read_text(encoding="utf-8"))
        check("06_parsed_relations_and_source_locators", len(structured["parent_relations"]) == 7
              and len(structured["edges"]) == 3 and len(structured["sources"]) == 7
              and all(x.get("evidence") for x in structured["sources"]))
        check("07_fact_summary_inference_and_priority_marks", any(n.attrib.get("data-kind") == "inference" for n in nodes)
              and any("high-priority" in n.attrib.get("class", "") for n in nodes)
              and any("[重点" in (t.text or "") for n in nodes for t in n.findall(".//%stext" % SVG)))

        linked = copy.deepcopy(SPEC)
        linked["nodes"][3]["source_url"] = "https://www.crossref.org/"
        out_link, result_link = run(root, "linked", linked)
        hrefs = [node.attrib.get(XLINK) for node in ET.parse(out_link / "mindmap.svg").getroot().findall(".//%sa" % SVG)]
        linked_sources = json.loads((out_link / "mindmap.json").read_text(encoding="utf-8"))["sources"]
        check("08_real_supplied_source_url_propagates", "https://www.crossref.org/" in hrefs
              and any(x["source_url"] == "https://www.crossref.org/" for x in linked_sources))

        long_spec = copy.deepcopy(SPEC)
        full = "超长标签A< overly long research label & evidence >" * 12
        long_spec["nodes"][4]["label"] = full
        out_long, result_long = run(root, "long_label", long_spec)
        overlap, bounds, _ = independent_bounds(out_long / "mindmap.svg")
        encoded = (out_long / "mindmap.svg").read_text(encoding="utf-8")
        long_nodes = ET.parse(out_long / "mindmap.svg").getroot().findall(".//%sg[@data-node-id]" % SVG)
        check("09_long_xml_label_bounded_with_full_accessible_label", result_long["status"] == "clean" and not overlap and not bounds
              and escape_amp_ok(encoded) and full in [n.attrib.get("data-label") for n in long_nodes] and "…" in encoded)

        # A different but valid re-run is byte deterministic for every file.
        out_a, r_a = run(root, "det_a", SPEC)
        out_b, r_b = run(root, "det_b", SPEC)
        hashes_a = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in out_a.iterdir()}
        hashes_b = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in out_b.iterdir()}
        check("10_all_outputs_byte_identical", hashes_a == hashes_b)

        cycle = copy.deepcopy(SPEC)
        cycle["nodes"][6]["parent"] = cycle["nodes"][7]["id"]
        out_cycle, r_cycle = run(root, "cycle", cycle)
        check("11_cycle_blocked_not_fake_svg", r_cycle["status"] == "blocked"
              and any(f["rule"] in ("map.cycle", "artifact.layout_failed") for f in r_cycle["findings"])
              and not (out_cycle / "mindmap.svg").exists() and (out_cycle / "result.json").exists())

        duplicate = copy.deepcopy(SPEC)
        duplicate["nodes"].append(copy.deepcopy(duplicate["nodes"][2]))
        out_dup, r_dup = run(root, "duplicate_id", duplicate)
        check("12_duplicate_id_refused_no_collision", r_dup["status"] == "blocked"
              and any(f["rule"] == "map.duplicate_node_id" for f in r_dup["findings"])
              and not (out_dup / "mindmap.svg").exists())

        bad_parent_kind = copy.deepcopy(SPEC)
        bad_parent_kind["nodes"][2]["parent_kind"] = "somehow-related"
        out_type, r_type = run(root, "parent_relation_unknown", bad_parent_kind)
        check("13_unknown_parent_relation_review_not_silent", r_type["status"] == "review"
              and any(f["rule"] == "map.parent_relation_unknown" for f in r_type["findings"])
              and (out_type / "mindmap.svg").exists())

        bad_label = copy.deepcopy(SPEC)
        bad_label["nodes"][4]["label"] = ""
        out_label, r_label = run(root, "empty_label", bad_label)
        check("14_empty_label_blocked", r_label["status"] == "blocked"
              and any(f["rule"] == "map.label_missing" for f in r_label["findings"]))

        roots = copy.deepcopy(SPEC)
        roots["nodes"].append({"id": "other-root", "label": "second root"})
        out_roots, r_roots = run(root, "two_roots", roots)
        check("15_two_roots_no_forest_masquerading_as_map", r_roots["status"] == "blocked"
              and not (out_roots / "mindmap.svg").exists())

        check("16_contract_echo_and_unseen_null", set(result["output_contract"]) == set(SPEC["output_contract"])
              and result["output_contract"]["case_id"] == SPEC["case_id"]
              and result["output_contract"]["svg"] == result["artifacts"]["mindmap.svg"]
              and result["output_contract"]["unseen_case_field"] is None
              and any("unseen_case_field" in x for x in result["limits"]))
        _, refusal = run(root, "nonobject", raw="[1,2,3]")
        check("17_nonobject_spec_structured_refusal", refusal["status"] == "undetermined"
              and refusal["findings"][0]["rule"] == "audit.no_section")

        # Stress complete node packing with 31 different labels and relations.
        stress = copy.deepcopy(SPEC)
        stress["title"] = "31-node span-packing stress"
        stress["max_nodes"] = 50
        stress["nodes"] = [{"id": "root", "label": "root"}]
        stress["edges"] = []
        for i in range(5):
            stress["nodes"].append({"id": "b%d" % i, "label": "branch %d" % i, "parent": "root", "evidence_exempt": True})
            for j in range(5):
                stress["nodes"].append({"id": "n%d_%d" % (i, j), "label": "Evidence %d-%d %s" % (i, j, "x" * (j * 14)),
                                         "parent": "b%d" % i, "evidence": "p.%d" % (i * 5 + j + 1), "kind": "fact"})
        stress["edges"] = [{"from": "n0_0", "to": "n4_4", "kind": "support", "basis": "stress-source basis"}]
        out_stress, r_stress = run(root, "stress31", stress)
        overlap, bounds, stress_boxes = independent_bounds(out_stress / "mindmap.svg")
        check("18_31_node_stress_nonoverlap_boundary", r_stress["status"] == "clean" and len(stress_boxes) == 31
              and not overlap and not bounds)

        # No-renderer path must never mislabel SVG as PNG. Renderer-equipped images
        # perform the positive conversion instead.
        png = out / "optional-preview.png"
        proc = subprocess.run([sys.executable, "-I", str(HERE / "render_preview.py"),
                               "--svg", str(out / "mindmap.svg"), "--png", str(png)],
                              capture_output=True, text=True)
        renderer_present = shutil.which("rsvg-convert") or shutil.which("inkscape") or _has_cairosvg()
        check("19_png_preview_honest", (proc.returncode == 0 and png.read_bytes().startswith(b"\x89PNG\r\n\x1a\n")) if renderer_present
              else (proc.returncode == 6 and not png.exists()), "rerender rc=" + str(proc.returncode))

    print("\n%d/%d pass" % (passed, passed + failed))
    return 1 if failed else 0


def _has_cairosvg():
    try:
        import cairosvg  # noqa: F401
        return True
    except (ImportError, OSError):
        return False


def escape_amp_ok(encoded):
    return "& evidence" not in encoded and "A< overly" not in encoded


if __name__ == "__main__":
    raise SystemExit(main())
