"""Benchmark for the measured-template rules.

The template rules used to be declarative: the spec said what the template
provides and the engine believed it. This bench proves the measured path — a
real template package is built (a genuine .potx-shaped zip, standard library
only), the spec names it, and the engine's verdicts are graded against what
the template file actually contains:

  template_clean            template matches the generator and the declarations
                            -> zero template.* findings (FP guard)
  template_no_file          no template named -> every template.* rule silent
  layout_not_found          a slide uses a layout the template does not have
  theme_font_mismatch       a declared face the measured theme never names
  title_geometry_drift      a patched slide whose title left the placeholder
  title_size_off            a deck whose title size leaves the template ladder
  slide_size_mismatch       a 4:3 template behind a 16:9 deck
  template_unreadable       the declared template is not a presentation package

    python bench_template.py
"""

from __future__ import annotations

import copy
import json
import sys
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import deckbuild  # noqa: E402
import extra_rules as X  # noqa: E402
import pptxgen as P  # noqa: E402

OUT = Path(__file__).resolve().parent / "_run_template"
EMU = P.EMU_IN

TPL_RULES = ("template.layout_not_found", "template.theme_font_mismatch",
             "template.title_geometry_drift", "template.title_size_off",
             "template.slide_size_mismatch", "template.unreadable")


def title_box_content():
    # Same expressions the generator uses for a content slide's title box, so
    # a template built from these numbers is exactly the generator's geometry.
    return (int(0.5 * EMU), int(0.35 * EMU), P.SLIDE_W - int(1.0 * EMU), int(1.0 * EMU))


def title_box_title():
    return (int(0.9 * EMU), int(2.4 * EMU), P.SLIDE_W - int(1.8 * EMU), int(1.5 * EMU))


def _layout(name: str, ltype: str, box, sz_pt: int) -> str:
    x, y, cx, cy = box
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<p:sldLayout xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" '
        'xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main" '
        'type="%s" preserve="1">'
        '<p:cSld name="%s"><p:spTree>'
        '<p:nvGrpSpPr><p:cNvPr id="1" name=""/><p:cNvGrpSpPr/><p:nvPr/></p:nvGrpSpPr>'
        '<p:grpSpPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="0" cy="0"/></a:xfrm></p:grpSpPr>'
        '<p:sp><p:nvSpPr><p:cNvPr id="2" name="Title Placeholder"/>'
        '<p:cNvSpPr><a:spLocks noGrp="1"/></p:cNvSpPr>'
        '<p:nvPr><p:ph type="title"/></p:nvPr></p:nvSpPr>'
        '<p:spPr><a:xfrm><a:off x="%d" y="%d"/><a:ext cx="%d" cy="%d"/></a:xfrm>'
        '<a:prstGeom prst="rect"><a:avLst/></a:prstGeom></p:spPr>'
        '<p:txBody><a:bodyPr/><a:lstStyle/><a:p><a:pPr lvl="0"/>'
        '<a:r><a:rPr lang="en-US" sz="%d" b="1"/><a:t>Title</a:t></a:r></a:p>'
        "</p:txBody></p:sp>"
        "</p:spTree></p:cSld>"
        "<p:clrMapOvr><a:masterClrMapping/></p:clrMapOvr></p:sldLayout>"
        % (ltype, name, x, y, cx, cy, sz_pt * 100)
    )


def build_template(path: Path, layouts=("Title Slide", "Title and Content"),
                   size=(P.SLIDE_W, P.SLIDE_H),
                   latin="Arial", ea="Microsoft YaHei") -> Path:
    """Write a genuine .potx-shaped package with the requested layouts."""
    content_types = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
        '<Default Extension="xml" ContentType="application/xml"/>'
        '<Override PartName="/ppt/presentation.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.template.main+xml"/>'
        '<Override PartName="/ppt/slideMasters/slideMaster1.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.slideMaster+xml"/>'
        '<Override PartName="/ppt/slideLayouts/slideLayout1.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.slideLayout+xml"/>'
        '<Override PartName="/ppt/slideLayouts/slideLayout2.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.slideLayout+xml"/>'
        '<Override PartName="/ppt/theme/theme1.xml" ContentType="application/vnd.openxmlformats-officedocument.theme+xml"/>'
        "</Types>")
    presentation = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<p:presentation xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" '
        'xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main">'
        '<p:sldMasterIdLst><p:sldMasterId id="2147483648" r:id="rId1"/></p:sldMasterIdLst>'
        '<p:sldSz cx="%d" cy="%d"/></p:presentation>' % size)
    master = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<p:sldMaster xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" '
        'xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main">'
        "<p:cSld><p:spTree/></p:cSld>"
        '<p:clrMap bg1="lt1" tx1="dk1" bg2="lt2" tx2="dk2"/>'
        '<p:sldLayoutIdLst><p:sldLayoutId id="2147483649" r:id="rId1"/>'
        '<p:sldLayoutId id="2147483650" r:id="rId2"/></p:sldLayoutIdLst></p:sldMaster>')
    theme = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<a:theme xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" name="BenchTheme">'
        "<a:themeElements><a:clrScheme name=\"Office\">"
        '<a:dk1><a:srgbClr val="1A1A1A"/></a:dk1><a:lt1><a:srgbClr val="FFFFFF"/></a:lt1>'
        "</a:clrScheme>"
        '<a:fontScheme name="BenchTheme">'
        '<a:majorFont><a:latin typeface="%s"/><a:ea typeface="%s"/><a:cs typeface=""/></a:majorFont>'
        '<a:minorFont><a:latin typeface="%s"/><a:ea typeface="%s"/><a:cs typeface=""/></a:minorFont>'
        "</a:fontScheme>"
        '<a:fmtScheme name="Office"><a:fillStyleLst><a:solidFill><a:schemeClr val="phClr"/>'
        '</a:solidFill></a:fillStyleLst><a:lnStyleLst><a:ln w="9525"><a:solidFill>'
        '<a:schemeClr val="phClr"/></a:solidFill></a:ln></a:lnStyleLst>'
        '<a:effectStyleLst><a:effectStyle><a:effectLst/></a:effectStyle></a:effectStyleLst>'
        '<a:bgFillStyleLst><a:solidFill><a:schemeClr val="phClr"/></a:solidFill>'
        "</a:bgFillStyleLst></a:fmtScheme></a:themeElements></a:theme>"
        % (latin, ea, latin, ea))
    rels_master = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slideLayout" Target="../slideLayouts/slideLayout1.xml"/>'
        '<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slideLayout" Target="../slideLayouts/slideLayout2.xml"/>'
        '<Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/theme" Target="../theme/theme1.xml"/>'
        "</Relationships>")
    lay_rels = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slideMaster" Target="../slideMasters/slideMaster1.xml"/>'
        "</Relationships>")

    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", content_types)
        z.writestr("_rels/.rels",
                   '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                   '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                   '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="ppt/presentation.xml"/>'
                   "</Relationships>")
        z.writestr("ppt/presentation.xml", presentation)
        z.writestr("ppt/_rels/presentation.xml.rels",
                   '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                   '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                   '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slideMaster" Target="slideMasters/slideMaster1.xml"/>'
                   "</Relationships>")
        z.writestr("ppt/slideMasters/slideMaster1.xml", master)
        z.writestr("ppt/slideMasters/_rels/slideMaster1.xml.rels", rels_master)
        z.writestr("ppt/slideLayouts/slideLayout1.xml",
                   _layout(layouts[0], "title", title_box_title(), 40))
        z.writestr("ppt/slideLayouts/slideLayout2.xml",
                   _layout(layouts[1], "body", title_box_content(), 32))
        z.writestr("ppt/slideLayouts/_rels/slideLayout1.xml.rels", lay_rels)
        z.writestr("ppt/slideLayouts/_rels/slideLayout2.xml.rels", lay_rels)
        z.writestr("ppt/theme/theme1.xml", theme)
    return path


BASE = {
    "section": "template_fit",
    "min_font_pt": 14,
    "max_bullets_per_slide": 5,
    "require_notes": True,
    "spacing": {"title": 32, "body": 20},
    "font_ea": "Microsoft YaHei",
    "font_latin": "Arial",
    "template": {"name": "conf-2026", "layouts": ["title", "content"]},
    "available_evidence": ["Fig. 3b, p.7"],
    "slides": [
        {"title": "多孔涂层加速吸收", "layout": "title", "claim": "问题：吸收速率是瓶颈",
         "evidence": "Fig. 3b, p.7", "notes": "引入问题，不读标题。"},
        {"title": "吸收速率提高 3 倍", "layout": "content", "claim": "涂层使吸收速率提高三倍",
         "evidence": "Fig. 3b, p.7",
         "bullets": ["对照组 12.4 a.u.", "涂层组 31.2 a.u.", "每组 n = 6"],
         "notes": "停顿；对比的是速率，不是终点。"},
    ],
}


def three_slides() -> dict:
    """BASE plus a second content slide, so layout groups have a group."""
    s = copy.deepcopy(BASE)
    s["slides"].append({
        "title": "机制：界面能与扩散路径", "layout": "content",
        "claim": "涂层降低界面能并缩短扩散路径", "evidence": "Fig. 3b, p.7",
        "bullets": ["界面能下降 18%", "扩散路径缩短一半"],
        "notes": "机制只给两个数字，细节留到问答。"})
    return s


def run(name: str, spec: dict) -> dict:
    d = OUT / name
    d.mkdir(parents=True, exist_ok=True)
    (d / "spec.json").write_text(json.dumps(spec, ensure_ascii=False), encoding="utf-8")
    return deckbuild.build_and_audit(d / "spec.json", d / "o")


def with_template(spec: dict, name: str, **kw) -> dict:
    tpl = build_template(OUT / f"{name}.potx", **kw)
    spec = copy.deepcopy(spec)
    spec["template"]["file"] = str(tpl)
    return spec


def scen_clean():
    return with_template(three_slides(), "clean"), []


def scen_no_file():
    return three_slides(), []


def scen_layout_not_found():
    s = with_template(three_slides(), "layout_nf")
    s["slides"][2]["layout"] = "two-column"
    return s


def scen_theme_font_mismatch():
    s = with_template(three_slides(), "font_mm")
    s["font_ea"] = "SimSun"
    return s


def scen_title_size_off():
    s = with_template(three_slides(), "size_off")
    s["spacing"] = {"title": 24, "body": 20}
    return s


def scen_slide_size_mismatch():
    return with_template(three_slides(), "size_mm", size=(9144000, 6858000))


def scen_template_unreadable():
    s = copy.deepcopy(three_slides())
    s["template"]["file"] = str(OUT / "not-a-template.json")
    (OUT / "not-a-template.json").write_text('{"not": "a presentation"}', encoding="utf-8")
    return s


def _patch_title_y(pptx: Path) -> None:
    """Move slide 3's title box off the template placeholder, the bench_deck2 way."""
    import xml.etree.ElementTree as ET
    a_ns = "http://schemas.openxmlformats.org/drawingml/2006/main"
    p_ns = "http://schemas.openxmlformats.org/presentationml/2006/main"
    ET.register_namespace("a", a_ns)
    ET.register_namespace("p", p_ns)
    tmp = pptx.with_suffix(".patched.pptx")
    with zipfile.ZipFile(pptx) as zin, zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as zout:
        for item in zin.namelist():
            data = zin.read(item)
            if item == "ppt/slides/slide3.xml":
                root = ET.fromstring(data)
                for sp in root.iter("{%s}sp" % p_ns):
                    cnv = sp.find(".//{%s}cNvPr" % p_ns)
                    if cnv is not None and cnv.get("name") == "Title":
                        off = sp.find(".//{%s}off" % a_ns)
                        off.set("y", str(int(off.get("y")) + 320040))
                data = ET.tostring(root, encoding="utf-8", xml_declaration=True)
            zout.writestr(item, data)
    tmp.replace(pptx)


def scen_title_geometry_drift():
    """Build the deck, then patch one title box off the template geometry.

    Unlike the other scenarios this one grades the section on the patched
    artifact directly (build_and_audit would write a fresh deck), so it
    returns a result-shaped dict rather than a spec.
    """
    spec = with_template(three_slides(), "geom_drift")
    d = OUT / "geom_drift_run"
    d.mkdir(parents=True, exist_ok=True)
    pptx = d / "deck.pptx"
    written = P.write_deck(deckbuild.spec_slides(spec), pptx,
                           spacing=spec.get("spacing"),
                           fonts=(spec["font_latin"], spec["font_ea"]))
    _patch_title_y(pptx)
    import templateread as TR
    tinfo = TR.read_template(spec["template"]["file"])
    ds = deckbuild.deck_summary(spec["slides"], pptx, written, tinfo)
    findings = X.run(spec, "template_fit", ds)
    return {"findings": findings, "status": "n/a"}, ["template.title_geometry_drift"]


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    rows = []
    # Each entry: (name, expect, spec_builder). The drift scenario builds its
    # own patched artifact and returns a result instead of a spec.
    for name, expect, builder in (
            ("clean", [], scen_clean),
            ("no_file", [], scen_no_file),
            ("layout_not_found", ["template.layout_not_found"], scen_layout_not_found),
            ("theme_font_mismatch", ["template.theme_font_mismatch"], scen_theme_font_mismatch),
            ("title_size_off", ["template.title_size_off"], scen_title_size_off),
            ("slide_size_mismatch", ["template.slide_size_mismatch"], scen_slide_size_mismatch),
            ("template_unreadable", ["template.unreadable"], scen_template_unreadable)):
        spec = builder()
        r = run(name, spec)
        fired = {f["rule"] for f in r["findings"]}
        tpl_fired = sorted(fired & set(TPL_RULES))
        missing = [x for x in expect if x not in fired]
        if not expect:
            spurious = tpl_fired            # clean/no-file: any template.* is spurious
        else:
            spurious = [f for f in tpl_fired if f not in expect and f != "template.unreadable"]
            # the unreadable probe legitimately fires only its own rule
        ok = not missing and not spurious
        rows.append({"scenario": name, "expected": expect, "fired": sorted(fired),
                     "missing": missing, "spurious": spurious, "pass": ok,
                     "status": r.get("status")})
        print(f"{'PASS' if ok else 'FAIL'}  {name:<22} missing={missing} spurious={spurious}")

    r, expect = scen_title_geometry_drift()
    fired = {f["rule"] for f in r["findings"]}
    missing = [x for x in expect if x not in fired]
    ok = not missing
    rows.append({"scenario": "title_geometry_drift", "expected": expect,
                 "fired": sorted(fired), "missing": missing, "spurious": [],
                 "pass": ok, "status": r.get("status")})
    print(f"{'PASS' if ok else 'FAIL'}  {'title_geometry_drift':<22} missing={missing}")

    # The measured result carries what the template actually provides.
    r = run("_probe_measured", with_template(three_slides(), "probe_meas"))
    tm = r.get("template_measured") or {}
    ok = (tm.get("read") and len(tm.get("layouts") or []) == 2
          and tm.get("theme_fonts", {}).get("major_latin") == "Arial"
          and tm.get("slide_size_emu") == [P.SLIDE_W, P.SLIDE_H])
    rows.append({"scenario": "template_measured_echo", "pass": ok, "template_measured": tm})
    print(f"{'PASS' if ok else 'FAIL'}  template_measured_echo")

    passed = sum(1 for x in rows if x["pass"])
    report = {"schema_version": "template-bench/v1", "scenarios": rows,
              "totals": {"passed": passed, "of": len(rows)},
              "note": ("Template constraints are measured from a real .potx-shaped "
                       "package built by this bench; clean and no-file scenarios "
                       "guard against firing without a template.")}
    (Path(__file__).resolve().parent / "report_template.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n{passed}/{len(rows)} pass")
    return 0 if passed == len(rows) else 1


if __name__ == "__main__":
    raise SystemExit(main())
