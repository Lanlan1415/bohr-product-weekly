"""Artifact regressions for real templates and whole-deck batch formatting."""
from __future__ import annotations

import copy
import json
import sys
import tempfile
import zipfile
from pathlib import Path
import xml.etree.ElementTree as ET

ROOT = Path(tempfile.mkdtemp(prefix="p33_delivery4_"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import bench_template as BT
import deckaudit as A
import deckbuild as D
import decksource as DS
import extra_rules as X
import pptxgen as P
import pnggen
import templatecheck as T

NS = {"a": "http://schemas.openxmlformats.org/drawingml/2006/main",
      "p": "http://schemas.openxmlformats.org/presentationml/2006/main"}
LOGO = ROOT / "logo.png"
canvas = pnggen.Canvas(320, 160)
canvas.rect_outline(4, 4, 315, 155, color=(0, 114, 178), width=5)
canvas.save(LOGO)


def rewrite(path: Path, part: str, fn) -> None:
    tmp = path.with_name(path.stem + "_edit.pptx")
    with zipfile.ZipFile(path) as zin, zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as zout:
        for name in zin.namelist():
            data = zin.read(name)
            if name == part:
                root = ET.fromstring(data)
                fn(root)
                data = ET.tostring(root, encoding="utf-8", xml_declaration=True)
            zout.writestr(name, data)
    tmp.replace(path)


def native_template(name="native", size=(P.SLIDE_W, P.SLIDE_H),
                    latin="Arial", ea="Microsoft YaHei") -> Path:
    """Extend a renderer-proven full PPTX into a two-layout real template."""
    path = ROOT / f"{name}.pptx"
    source_spec = base()
    source_spec["font_latin"] = latin
    source_spec["font_ea"] = ea
    source_spec["style"]["slide_in"] = [size[0] / P.EMU_IN, size[1] / P.EMU_IN]
    P.write_deck(D.spec_slides(source_spec), path, spacing=source_spec["spacing"],
                 fonts=(source_spec["font_latin"], source_spec["font_ea"]),
                 style=P.normalize_style(source_spec["style"]))
    with zipfile.ZipFile(path) as z:
        parts = {n: z.read(n) for n in z.namelist()}
    original_layout = ET.fromstring(parts["ppt/slideLayouts/slideLayout1.xml"])
    slide1 = ET.fromstring(parts["ppt/slides/slide1.xml"])
    slide2 = ET.fromstring(parts["ppt/slides/slide2.xml"])

    def shape(slide, wanted):
        for sp in slide.findall("p:cSld/p:spTree/p:sp", NS):
            cnv = sp.find(".//p:cNvPr", NS)
            if cnv is not None and cnv.get("name") == wanted:
                node = copy.deepcopy(sp)
                nv = node.find("p:nvSpPr/p:nvPr", NS)
                ph = ET.Element("{%s}ph" % NS["p"])
                if wanted == "Body":
                    ph.set("type", "body"); ph.set("idx", "1")
                else:
                    ph.set("type", "title")
                nv.insert(0, ph)
                props = node.find("p:nvSpPr/p:cNvSpPr", NS)
                if props is not None:
                    props.attrib.pop("txBox", None)
                return node
        raise AssertionError(f"missing fixture shape {wanted}")

    layout1 = copy.deepcopy(original_layout)
    layout1.set("type", "title")
    layout1.find("p:cSld", NS).set("name", "Title Slide")
    layout1.find("p:cSld/p:spTree", NS).append(shape(slide1, "Title"))
    layout2 = copy.deepcopy(original_layout)
    layout2.set("type", "obj")
    layout2.find("p:cSld", NS).set("name", "Title and Content")
    tree2 = layout2.find("p:cSld/p:spTree", NS)
    tree2.append(shape(slide2, "Title")); tree2.append(shape(slide2, "Body"))
    parts["ppt/slideLayouts/slideLayout1.xml"] = ET.tostring(layout1, encoding="utf-8", xml_declaration=True)
    parts["ppt/slideLayouts/slideLayout2.xml"] = ET.tostring(layout2, encoding="utf-8", xml_declaration=True)
    parts["ppt/slideLayouts/_rels/slideLayout2.xml.rels"] = parts["ppt/slideLayouts/_rels/slideLayout1.xml.rels"]

    rel_ns = "http://schemas.openxmlformats.org/package/2006/relationships"
    mrels = ET.fromstring(parts["ppt/slideMasters/_rels/slideMaster1.xml.rels"])
    relation = ET.SubElement(mrels, f"{{{rel_ns}}}Relationship")
    relation.set("Id", "rId3")
    relation.set("Type", "http://schemas.openxmlformats.org/officeDocument/2006/relationships/slideLayout")
    relation.set("Target", "../slideLayouts/slideLayout2.xml")
    ET.register_namespace("", rel_ns)
    parts["ppt/slideMasters/_rels/slideMaster1.xml.rels"] = ET.tostring(mrels, encoding="utf-8", xml_declaration=True)
    master = ET.fromstring(parts["ppt/slideMasters/slideMaster1.xml"])
    ids = master.find("p:sldLayoutIdLst", NS)
    item = ET.SubElement(ids, f"{{{NS['p']}}}sldLayoutId")
    item.set("id", "2147483650")
    item.set("{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id", "rId3")
    ET.register_namespace("r", "http://schemas.openxmlformats.org/officeDocument/2006/relationships")
    parts["ppt/slideMasters/slideMaster1.xml"] = ET.tostring(master, encoding="utf-8", xml_declaration=True)
    ct = ET.fromstring(parts["[Content_Types].xml"])
    override = ET.SubElement(ct, "{http://schemas.openxmlformats.org/package/2006/content-types}Override")
    override.set("PartName", "/ppt/slideLayouts/slideLayout2.xml")
    override.set("ContentType", "application/vnd.openxmlformats-officedocument.presentationml.slideLayout+xml")
    ET.register_namespace("", "http://schemas.openxmlformats.org/package/2006/content-types")
    parts["[Content_Types].xml"] = ET.tostring(ct, encoding="utf-8", xml_declaration=True)
    tmp = path.with_name(path.stem + "_two-layout.pptx")
    with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as zout:
        for item, data in parts.items():
            zout.writestr(item, data)
    tmp.replace(path)
    return path


def base() -> dict:
    spec = copy.deepcopy(BT.three_slides())
    spec.update({
        "case_id": "template-delivery4",
        "output_contract": ["case_id", "status", "deck_file", "template_application",
                            "version_record", "custom", "absent"],
        "custom": {"preserved": True},
        "require_title_placeholder": True,
        "style": {"colors": {"background": "FFFFFF", "text": "1A1A1A", "title": "1A1A1A",
                             "accent": "0072B2", "muted": "5F6B76"}},
    })
    return spec


def run(name: str, spec: dict) -> tuple[dict, Path]:
    work = ROOT / name
    work.mkdir(parents=True, exist_ok=True)
    path = work / "spec.json"
    path.write_text(json.dumps(spec, ensure_ascii=False), encoding="utf-8")
    out = work / "out"
    return D.build_and_audit(path, out), out


def make_source(name: str, spec: dict) -> Path:
    path = ROOT / f"{name}-source.pptx"
    P.write_deck(D.spec_slides(spec), path, spacing=spec["spacing"],
                 fonts=(spec["font_latin"], spec["font_ea"]), style=P.normalize_style(spec.get("style")))
    return path


def main() -> int:
    reports = []

    def scenario(name: str, result: dict, expected: list[str], checks=None):
        fired = {f["rule"] for f in result.get("findings", [])}
        missing = [x for x in expected if x not in fired]
        spurious = [] if expected else [f["rule"] for f in result.get("findings", [])]
        errors = list(checks(result) if checks else [])
        ok = not missing and not spurious and not errors
        reports.append({"scenario": name, "expected": expected, "fired": sorted(fired),
                        "missing": missing, "spurious": spurious, "assertions": errors, "pass": ok})
        print(f"{'PASS' if ok else 'FAIL'}  {name:<34} missing={missing} spurious={spurious} assertions={errors}")

    template = native_template()
    spec = base(); spec["template"]["file"] = str(template)
    # Guard the full-height layout body versus an independent caption band.
    spec["slides"][1]["caption"] = "Fig. 3b, p.7 — same measured comparison"
    result, out = run("native_template", spec)
    def native_checks(r):
        errors = []
        if not r.get("template_application", {}).get("applied"): errors.append("template not applied")
        if r.get("custom") != {"preserved": True}: errors.append("custom value lost")
        with zipfile.ZipFile(out / "deck.pptx") as z:
            for i in (1, 2, 3):
                root = ET.fromstring(z.read(f"ppt/slides/slide{i}.xml"))
                kinds = [(ph.get("type") or "body") for ph in root.findall(".//p:ph", NS)]
                if "title" not in kinds: errors.append(f"slide{i}: title ph absent")
                if i > 1 and "body" not in kinds: errors.append(f"slide{i}: body ph absent")
        return errors
    scenario("native_template_clean", result, [], native_checks)

    bad = base(); bad["template"]["file"] = str(template); bad["style"]["colors"]["text"] = "FFFFFF"
    direct = {"findings": T.audit(T.measure(template), bad, [P.SLIDE_W, P.SLIDE_H])}
    scenario("declared_theme_color_mismatch_unit", direct, ["template.theme_color_mismatch"])
    result, out = run("theme_color_corrected", bad)
    scenario("template_corrects_theme_color", result, [],
             lambda r: [] if D.deck_summary(bad["slides"], out / "deck.pptx", r["deck"])
             ["slides"][1]["body_colors"] == ["1A1A1A"]
             else ["final body color was not replaced by real theme color"])

    # Bad declared title size is corrected by the actual template, not left wrong.
    bad = base(); bad["template"]["file"] = str(template); bad["spacing"] = {"title": 24, "body": 20}
    result, out = run("title_size_corrected", bad)
    def title_corrected(r):
        actual = D.deck_summary(bad["slides"], out / "deck.pptx", r["deck"])
        sizes = actual["slides"][1]["title_sizes"]
        errors = [] if sizes == [32.0] else [f"content title sizes={sizes}"]
        if any(f["rule"] == "template.title_size_off" for f in r["findings"]):
            errors.append("corrected deck still reports title_size_off")
        return errors
    scenario("template_corrects_title_size", result, [], title_corrected)

    # Resize canvas and placeholder geometry together, proving physical application.
    small_template = native_template("small", size=(9144000, 6858000))
    bad = base(); bad["template"]["file"] = str(small_template)
    result, out = run("small_canvas_applied", bad)
    def small_checks(r):
        errors = []
        if r["deck"]["size_emu"] != [9144000, 6858000]: errors.append(f"size={r['deck']['size_emu']}")
        if any(f["rule"] == "template.slide_size_mismatch" for f in r["findings"]):
            errors.append("applied deck still mismatches template canvas")
        return errors
    scenario("template_canvas_applied", result, [], small_checks)
    measured = T.measure(small_template)
    direct = {"findings": T.audit(measured, spec, [P.SLIDE_W, P.SLIDE_H])}
    scenario("preapplication_size_mismatch_unit", direct, ["template.slide_size_mismatch"])

    # Whole-source batch run: the old page fields are replaced exactly once.
    spec = base(); spec.pop("require_title_placeholder")
    spec["template"] = {"name": "declared-house", "layouts": ["title", "content"]}
    spec["style"]["footer"] = {"text": "Old footer", "page_numbers": True}
    source = make_source("batch_source", spec)
    spec["source_deck"] = str(source)
    spec["style"]["footer"] = {"text": "House · measured results", "page_numbers": True,
                               "logo": str(LOGO), "logo_alt": "House logo"}
    spec["batch_format"] = {
        "title_style": {"font_size_pt": 34, "color": "17365D", "font_latin": "Arial", "font_ea": "Microsoft YaHei"},
        "body_style": {"font_size_pt": 18, "color": "1A1A1A"},
    }
    result, out = run("source_batch", spec)
    def batch_checks(r):
        errors = []
        if not r.get("source_record", {}).get("package_preserved"): errors.append("source package lost parts")
        if not r.get("source_record", {}).get("batch_format_applied"): errors.append("batch flag absent")
        if not r.get("reproducibility", {}).get("deterministic"): errors.append("non-deterministic")
        with zipfile.ZipFile(out / "deck.pptx") as z:
            slides = [n for n in z.namelist() if n.startswith("ppt/slides/slide") and n.endswith(".xml")]
            fields = sum(z.read(n).count(b'type="slidenum"') for n in slides)
            if fields != 3: errors.append(f"page fields={fields}, expected exactly 3")
            if sum(z.read(n).count(b'House') for n in slides) < 3: errors.append("new footer not on every page")
            media = [n for n in z.namelist() if n.startswith("ppt/media/batch_logo")]
            if len(media) != 1: errors.append(f"shared logo parts={media}")
        summaries = D.deck_summary(spec["slides"], out / "deck.pptx", r["deck"])
        if summaries["slides"][1]["title_sizes"] != [34.0]: errors.append("batch title size not applied")
        if summaries["slides"][1]["body_sizes"] != [18.0]: errors.append("batch body size not applied")
        return errors
    scenario("source_batch_footer_logo_styles", result, [], batch_checks)

    # Batch + real template: template title/body wins last, batch footer persists.
    combined = copy.deepcopy(spec); combined["template"]["file"] = str(template)
    combined["require_title_placeholder"] = True
    result, out = run("source_batch_template", combined)
    def combined_checks(r):
        errors = []
        if not r.get("template_application", {}).get("applied"): errors.append("real template absent")
        with zipfile.ZipFile(out / "deck.pptx") as z:
            fields = sum(z.read(n).count(b'type="slidenum"') for n in z.namelist()
                         if n.startswith("ppt/slides/slide") and n.endswith(".xml"))
            if fields != 3: errors.append(f"fields after template={fields}")
        summary = D.deck_summary(combined["slides"], out / "deck.pptx", r["deck"])
        if summary["slides"][0]["title_sizes"] != [40.0] or summary["slides"][1]["title_sizes"] != [32.0]:
            errors.append(f"template title sizes not final: {[x['title_sizes'] for x in summary['slides']]}")
        return errors
    scenario("source_batch_plus_real_template", result, [], combined_checks)

    # Opting out of footer replacement must preserve, never drop or duplicate.
    quiet = base(); quiet.pop("require_title_placeholder")
    quiet["template"] = {"name": "declared", "layouts": ["title", "content"]}
    quiet["style"]["footer"] = {"text": "Keep original", "page_numbers": True}
    source = make_source("keep_footer", quiet)
    quiet["source_deck"] = str(source)
    quiet["batch_format"] = {"footer": False, "title_style": {"font_size_pt": 30}}
    result, out = run("source_batch_keep_footer", quiet)
    def keep_checks(r):
        with zipfile.ZipFile(out / "deck.pptx") as z:
            fields = sum(z.read(n).count(b'type="slidenum"') for n in z.namelist()
                         if n.startswith("ppt/slides/slide") and n.endswith(".xml"))
            originals = sum(z.read(n).count(b'Keep original') for n in z.namelist()
                            if n.startswith("ppt/slides/slide") and n.endswith(".xml"))
        return [] if fields == 3 and originals == 3 else [f"fields={fields}, original footers={originals}"]
    scenario("source_batch_footer_optout", result, [], keep_checks)

    # Fault injection on the body, not on a spec assertion.
    drift = base(); drift.pop("require_title_placeholder")
    drift["template"] = {"name": "declared", "layouts": ["title", "content"]}
    path = ROOT / "body-drift.pptx"
    P.write_deck(D.spec_slides(drift), path, spacing=drift["spacing"],
                 fonts=(drift["font_latin"], drift["font_ea"]), style=P.normalize_style())
    def move_body(root):
        for sp in root.findall("p:cSld/p:spTree/p:sp", NS):
            cnv = sp.find(".//p:cNvPr", NS)
            if cnv is not None and cnv.get("name") == "Body":
                sp.find("p:spPr/a:xfrm/a:off", NS).set("x", "700000")
    rewrite(path, "ppt/slides/slide2.xml", move_body)
    summary = D.deck_summary(drift["slides"], path, {"spacing": drift["spacing"]})
    result = {"findings": X.run(drift, "template_fit", summary)}
    scenario("body_margin_drift_detected", result, ["format.body_drift"])

    ghost = base(); ghost.pop("require_title_placeholder")
    ghost["template"] = {"name": "declared", "layouts": ["title", "content"]}
    ghost["style"]["footer"] = {"text": "House", "page_numbers": True}
    source = make_source("missing_logo", ghost)
    ghost["style"]["footer"]["logo"] = str(ROOT / "ghost.png")
    ghost["source_deck"] = str(source); ghost["batch_format"] = True
    result, _ = run("source_batch_missing_logo", ghost)
    scenario("source_batch_missing_logo", result, ["image.logo_missing"])

    missing_title = native_template("missing_title")
    def drop_title(root):
        tree = root.find("p:cSld/p:spTree", NS)
        for sp in list(tree.findall("p:sp", NS)):
            ph = sp.find(".//p:ph", NS)
            if ph is not None and (ph.get("type") or "body") == "title":
                tree.remove(sp)
    rewrite(missing_title, "ppt/slideLayouts/slideLayout2.xml", drop_title)
    bad = base(); bad["template"]["file"] = str(missing_title)
    result, _ = run("required_title_placeholder_missing", bad)
    scenario("required_title_placeholder_missing", result, ["template.title_placeholder_missing"])

    passed = sum(1 for x in reports if x["pass"])
    report = {"schema_version": "template-delivery-bench/v4", "temp_root": str(ROOT),
              "scenarios": reports, "totals": {"passed": passed, "of": len(reports)}}
    (Path(__file__).resolve().parent / "report_delivery4.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n{passed}/{len(reports)} scenarios pass\nartifacts: {ROOT}")
    return 0 if passed == len(reports) else 1


if __name__ == "__main__":
    raise SystemExit(main())
