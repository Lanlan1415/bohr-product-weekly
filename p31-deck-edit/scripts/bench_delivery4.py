"""Artifact-level regression for styled decks, real source edits and templates.

Every scenario uses a fresh temporary directory. Binaries never leak into the
submitted skill package. A clean guard asserts zero findings; defect scenarios
must both fire the named rule and, where applicable, preserve a readable PPTX.
"""
from __future__ import annotations

import copy
import json
import sys
import tempfile
import zipfile
from pathlib import Path
import xml.etree.ElementTree as ET

ROOT = Path(tempfile.mkdtemp(prefix="p31_delivery4_"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import deckaudit as A
import deckbuild as D
import decksource as DS
import pptxgen as P
import pnggen
import templatecheck as T

NS = {"a": "http://schemas.openxmlformats.org/drawingml/2006/main",
      "p": "http://schemas.openxmlformats.org/presentationml/2006/main"}
ASSETS = ROOT / "assets"
ASSETS.mkdir()
LOGO = ASSETS / "logo.png"
canvas = pnggen.Canvas(320, 160)
canvas.rect_outline(4, 4, 315, 155, color=(0, 114, 178), width=5)
canvas.save(LOGO)


def base() -> dict:
    return {
        "section": "deck_edit", "case_id": "delivery4-demo",
        "output_contract": {"case_id": "id", "status": "audit", "deck_file": "pptx",
                            "version_record": "versions", "custom_note": "object", "absent": "null"},
        "custom_note": {"preserved": [1, 2]},
        "spacing": {"title": 32, "body": 20}, "font_ea": "Microsoft YaHei", "font_latin": "Arial",
        "min_font_pt": 14, "max_bullets_per_slide": 5, "require_notes": True,
        "available_evidence": ["Fig. 3b, p.7", "Sec. 2, p.3"],
        "style": {"colors": {"background": "FFFFFF", "text": "1A1A1A", "title": "17365D",
                             "accent": "0072B2", "muted": "5F6B76"},
                  "margins_in": [0.35, 0.5, 0.9, 0.5],
                  "footer": {"text": "Methods Group · measured results", "page_numbers": True,
                             "logo": str(LOGO), "logo_alt": "Methods Group logo"}},
        "revisions": [{"n": 1, "instruction": "quantify the measured conclusion", "changes": [
            {"slide": 2, "before": "吸收速率明显提高", "after": "吸收速率提高 3 倍",
             "reason": "bind the title to the measured comparison"}]}],
        "delivered_revision": 1,
        "slides": [
            {"title": "多孔涂层解决吸收速率瓶颈", "layout": "title", "claim": "速率是研究问题",
             "evidence": "Sec. 2, p.3", "notes": "先交代问题，再进入对照设计。"},
            {"title": "吸收速率提高 3 倍", "layout": "content", "claim": "涂层使速率提高三倍",
             "evidence": "Fig. 3b, p.7", "caption": "Fig. 3b, p.7 — 每组 n = 6",
             "bullets": ["对照组 12.4 a.u.", "涂层组 31.2 a.u.", "每组 n = 6"],
             "notes": "强调速率而不是终点，并说明重复数。"},
        ],
    }


def run(name: str, spec: dict, case: dict | None = None) -> tuple[dict, Path]:
    work = ROOT / name
    work.mkdir(parents=True, exist_ok=True)
    path = work / "spec.json"
    path.write_text(json.dumps(spec, ensure_ascii=False), encoding="utf-8")
    kwargs = {}
    if case is not None:
        cp = work / "case.json"
        cp.write_text(json.dumps(case, ensure_ascii=False), encoding="utf-8")
        kwargs["case_path"] = cp
    out = work / "out"
    return D.build_and_audit(path, out, **kwargs), out


def rewrite_part(path: Path, part: str, fn) -> None:
    temp = path.with_name(path.stem + "_patched.pptx")
    with zipfile.ZipFile(path) as zin, zipfile.ZipFile(temp, "w", zipfile.ZIP_DEFLATED) as zout:
        for name in zin.namelist():
            data = zin.read(name)
            if name == part:
                root = ET.fromstring(data)
                fn(root)
                data = ET.tostring(root, encoding="utf-8", xml_declaration=True)
            zout.writestr(name, data)
    temp.replace(path)


def make_source(name: str, final_title: str = "吸收速率明显提高") -> tuple[Path, dict]:
    spec = base()
    spec["style"] = {}
    spec["slides"][1]["title"] = final_title
    work = ROOT / name
    work.mkdir(parents=True, exist_ok=True)
    path = work / "source.pptx"
    P.write_deck(D.spec_slides(spec), path, spacing=spec["spacing"],
                 fonts=(spec["font_latin"], spec["font_ea"]), style=P.normalize_style())
    return path, spec


def make_template() -> Path:
    """Create a real title/body layout from a generated editable slide."""
    path = ASSETS / "native-template.pptx"
    source_spec = base()
    source_spec["style"] = {}
    P.write_deck(D.spec_slides(source_spec), path, spacing=source_spec["spacing"],
                 fonts=(source_spec["font_latin"], source_spec["font_ea"]), style=P.normalize_style())
    layout_part = "ppt/slideLayouts/slideLayout1.xml"
    with zipfile.ZipFile(path) as z:
        slide = ET.fromstring(z.read("ppt/slides/slide2.xml"))
        layout = ET.fromstring(z.read(layout_part))
    tree = layout.find("p:cSld/p:spTree", NS)
    for sp in list(slide.findall("p:cSld/p:spTree/p:sp", NS)):
        cnv = sp.find(".//p:cNvPr", NS)
        name = (cnv.get("name") or "") if cnv is not None else ""
        if name not in {"Title", "Body"}:
            continue
        nv = sp.find("p:nvSpPr/p:nvPr", NS)
        ph = ET.Element("{%s}ph" % NS["p"])
        if name == "Body":
            ph.set("type", "body"); ph.set("idx", "1")
        else:
            ph.set("type", "title")
        nv.insert(0, ph)
        tree.append(sp)
    csld = layout.find("p:cSld", NS)
    csld.set("name", "Title and Content")
    data = ET.tostring(layout, encoding="utf-8", xml_declaration=True)
    rewrite_part(path, layout_part, lambda _: None)
    # rewrite_part above cannot inject an already serialized root; perform the
    # actual replacement in a second straightforward package pass.
    temp = path.with_name("native-template-final.pptx")
    with zipfile.ZipFile(path) as zin, zipfile.ZipFile(temp, "w", zipfile.ZIP_DEFLATED) as zout:
        for item in zin.namelist():
            zout.writestr(item, data if item == layout_part else zin.read(item))
    temp.replace(path)
    return path


def main() -> int:
    reports = []

    def scenario(name: str, result: dict, expected: list[str], checks=None):
        fired = {f["rule"] for f in result.get("findings", [])}
        missing = [rule for rule in expected if rule not in fired]
        spurious = [] if expected else [f["rule"] for f in result.get("findings", [])]
        extra = list(checks(result) if checks else [])
        ok = not missing and not spurious and not extra
        reports.append({"scenario": name, "expected": expected, "fired": sorted(fired),
                        "missing": missing, "spurious": spurious, "assertion_failures": extra,
                        "pass": ok})
        print(f"{'PASS' if ok else 'FAIL'}  {name:<32} missing={missing} spurious={spurious} assertions={extra}")

    # 1: real styled output, dynamic page numbers and embedded logo.
    result, out = run("clean_styled", base())
    def styled_checks(r):
        errors = []
        with zipfile.ZipFile(out / "deck.pptx") as z:
            slides = [n for n in z.namelist() if n.startswith("ppt/slides/slide") and n.endswith(".xml")]
            fields = sum(z.read(n).count(b'type="slidenum"') for n in slides)
            media = [n for n in z.namelist() if n.startswith("ppt/media/")]
            if fields != 2: errors.append(f"slidenum fields={fields}")
            if not media: errors.append("logo media absent")
            if b'Methods Group' not in z.read("ppt/slides/slide1.xml"): errors.append("footer absent")
        if not r.get("reproducibility", {}).get("deterministic"): errors.append("non-deterministic")
        if r.get("custom_note") != {"preserved": [1, 2]}: errors.append("custom contract damaged")
        if r.get("absent") is not None: errors.append("absent field not null")
        return errors
    scenario("clean_styled_footer_logo", result, [], styled_checks)

    bad = base(); bad["style"]["colors"].update({"text": "FFFFFF", "title": "FFFFFF"})
    result, _ = run("low_contrast", bad)
    scenario("low_contrast_detected", result, ["format.low_contrast"])

    bad = base(); bad["style"] = "invalid-style"
    result, _ = run("bad_style_type", bad)
    scenario("bad_style_degrades_with_limit", result, [],
             lambda r: [] if any("style" in x for x in r["limits"]) else ["style limit absent"])

    bad = base(); bad["style"]["footer"]["logo"] = str(ROOT / "ghost.png")
    result, _ = run("missing_logo", bad)
    scenario("missing_logo_detected", result, ["image.logo_missing"])

    # 2–5: source package is edited, not regenerated or merely described.
    source, spec = make_source("source_structural")
    spec["source_deck"] = str(source)
    spec["revisions"][0]["changes"] += [
        {"slide": 2, "action": "set_geometry", "shape": "Title", "reason": "align the title",
         "geometry": {"x": 0.55, "y": 0.35, "w": 12.23, "h": 1.0}},
        {"slide": 2, "action": "set_style", "shape": "Title", "reason": "apply title hierarchy",
         "font_size_pt": 34, "color": "0072B2"},
    ]
    result, out = run("source_text_geometry_style", spec)
    def source_checks(r):
        errors = []
        records = r.get("source_record", {}).get("records") or []
        if [x.get("status") for x in records] != ["applied", "applied", "applied"]:
            errors.append(f"record statuses={[x.get('status') for x in records]}")
        if not r.get("source_record", {}).get("package_preserved"): errors.append("source package changed membership")
        slides = A.read_deck(out / "deck.pptx")
        title = next(s for s in slides[1]["shapes"] if s["name"] == "Title")
        if title["x"] != int(0.55 * 914400): errors.append("geometry not applied")
        if not title["paras"] or title["paras"][0].get("size_pt") != 34: errors.append("font size not applied")
        if "0072B2" not in (title["paras"][0].get("colors") or []): errors.append("color not applied")
        return errors
    scenario("source_text_geometry_style", result, [], source_checks)

    already, spec = make_source("source_idempotent", "吸收速率提高 3 倍")
    spec["source_deck"] = str(already)
    result, _ = run("source_already_applied", spec)
    scenario("source_already_applied_guard", result, [],
             lambda r: [] if r["source_record"]["records"][0]["status"] == "already_present"
             else ["expected idempotent already_present"])

    missing, spec = make_source("source_shape_missing")
    spec["source_deck"] = str(missing)
    spec["revisions"][0]["changes"] = [{"slide": 2, "action": "set_geometry", "shape": "Ghost",
                                        "reason": "test missing shape handling",
                                        "geometry": {"x": 1, "y": 1, "w": 2, "h": 1}}]
    result, _ = run("source_shape_missing", spec)
    scenario("source_missing_shape_blocked", result, ["edit.source_change_unapplied"])

    # 6–8: geometry fault injection against the real artifact.
    spec = base(); spec["style"] = {}
    path = ROOT / "out_of_bounds.pptx"
    P.write_deck(D.spec_slides(spec), path, spacing=spec["spacing"],
                 fonts=(spec["font_latin"], spec["font_ea"]), style=P.normalize_style())
    def move_body(root):
        for sp in root.findall("p:cSld/p:spTree/p:sp", NS):
            cnv = sp.find(".//p:cNvPr", NS)
            if cnv is not None and cnv.get("name") == "Body":
                sp.find("p:spPr/a:xfrm/a:off", NS).set("x", "13000000")
    rewrite_part(path, "ppt/slides/slide2.xml", move_body)
    result = A.audit_deck(path, spec)
    scenario("out_of_bounds_detected", result, ["layout.out_of_bounds"])

    path2 = ROOT / "overlap.pptx"
    P.write_deck(D.spec_slides(spec), path2, spacing=spec["spacing"],
                 fonts=(spec["font_latin"], spec["font_ea"]), style=P.normalize_style())
    def overlap(root):
        for sp in root.findall("p:cSld/p:spTree/p:sp", NS):
            cnv = sp.find(".//p:cNvPr", NS)
            if cnv is not None and cnv.get("name") == "Body":
                sp.find("p:spPr/a:xfrm/a:off", NS).set("y", "320040")
    rewrite_part(path2, "ppt/slides/slide2.xml", overlap)
    result = A.audit_deck(path2, spec)
    scenario("text_overlap_detected", result, ["layout.overlap"])

    empty_spec = base(); empty_spec["style"] = {}; empty_spec["slides"] = [
        {"title": "", "claim": "empty placeholder", "evidence": "Sec. 2, p.3"}]
    empty_path = ROOT / "empty.pptx"
    P.write_deck([P.Slide(title="")], empty_path)
    result = A.audit_deck(empty_path, empty_spec)
    scenario("blank_slide_detected", result, ["deck.empty_slide"])

    # 9: real template shell and native title/body placeholders.
    template = make_template()
    spec = base(); spec["style"] = {}
    spec["template"] = {"file": str(template), "name": "native", "layouts": ["blank"]}
    spec["require_title_placeholder"] = True
    for slide in spec["slides"]:
        slide["layout"] = "blank"
    result, out = run("template_native_placeholders", spec)
    def template_checks(r):
        errors = []
        if not r.get("template_application", {}).get("applied"): errors.append("template not applied")
        records = r.get("template_application", {}).get("placeholder_records") or {}
        if not all(v.get("title_placeholder") for v in records.values()) or \
                not records.get("2", {}).get("body_placeholder"):
            errors.append("native placeholders not assigned (cover has no body by design)")
        with zipfile.ZipFile(template) as z:
            master = z.read("ppt/slideMasters/slideMaster1.xml")
        with zipfile.ZipFile(out / "deck.pptx") as z:
            if z.read("ppt/slideMasters/slideMaster1.xml") != master: errors.append("master bytes differ")
            for i in (1, 2):
                root = ET.fromstring(z.read(f"ppt/slides/slide{i}.xml"))
                kinds = [(ph.get("type") or "body") for ph in root.findall(".//p:ph", NS)]
                if "title" not in kinds or (i == 2 and "body" not in kinds):
                    errors.append(f"slide {i} ph kinds={kinds}")
        return errors
    scenario("template_native_placeholders", result, [], template_checks)

    passed = sum(1 for x in reports if x["pass"])
    report = {"schema_version": "deck-delivery-bench/v4", "temp_root": str(ROOT),
              "scenarios": reports, "totals": {"passed": passed, "of": len(reports)}}
    report_path = Path(__file__).resolve().parent / "report_delivery4.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n{passed}/{len(reports)} scenarios pass\nartifacts: {ROOT}")
    return 0 if passed == len(reports) else 1


if __name__ == "__main__":
    raise SystemExit(main())
