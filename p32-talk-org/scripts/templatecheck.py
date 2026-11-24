"""Measure and physically apply an organizer-supplied PPTX/POTX template shell.

Only standard-library OPC/XML operations are used.  Applying a template keeps
its real master/layout/theme parts and reconnects every generated slide to the
requested layout; it does not merely copy a template name into the spec.
"""
from __future__ import annotations

import hashlib
import posixpath
import re
import zipfile
from pathlib import Path
import xml.etree.ElementTree as ET

NS = {
    "a": "http://schemas.openxmlformats.org/drawingml/2006/main",
    "p": "http://schemas.openxmlformats.org/presentationml/2006/main",
    "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
    "ct": "http://schemas.openxmlformats.org/package/2006/content-types",
    "pr": "http://schemas.openxmlformats.org/package/2006/relationships",
}
for prefix in ("a", "p", "r"):
    ET.register_namespace(prefix, NS[prefix])


def _opc_xml(root: ET.Element, kind: str) -> bytes:
    """Serialize one OPC part with its own default namespace, not ns0.

    ElementTree removes any previous default mapping when another URI is set,
    so CT and package relationships must be registered per write, not globally.
    """
    ET.register_namespace("", NS[kind])
    return ET.tostring(root, encoding="utf-8", xml_declaration=True)


def _digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _resolve(part: str, target: str) -> str:
    return posixpath.normpath(posixpath.join(posixpath.dirname(part), target))


def _rels_name(part: str) -> str:
    return posixpath.join(posixpath.dirname(part), "_rels", posixpath.basename(part) + ".rels")


def _relations(z: zipfile.ZipFile, part: str) -> list[ET.Element]:
    name = _rels_name(part)
    if name not in z.namelist():
        return []
    return list(ET.fromstring(z.read(name)))


def _target(part: str, rel: ET.Element) -> str:
    return _resolve(part, rel.get("Target") or "")


def _norm(value: str) -> str:
    return "".join(ch for ch in str(value or "").casefold() if ch.isalnum())


def _ph(sp: ET.Element) -> ET.Element | None:
    return sp.find(".//p:nvPr/p:ph", NS)


def _ph_type(sp: ET.Element) -> str:
    ph = _ph(sp)
    return ((ph.get("type") or "body") if ph is not None else "").lower()


def _geometry(sp: ET.Element | None) -> dict | None:
    if sp is None:
        return None
    xfrm = sp.find("p:spPr/a:xfrm", NS)
    off = xfrm.find("a:off", NS) if xfrm is not None else None
    ext = xfrm.find("a:ext", NS) if xfrm is not None else None
    if off is None or ext is None:
        return None
    try:
        return {"x": int(off.get("x")), "y": int(off.get("y")),
                "cx": int(ext.get("cx")), "cy": int(ext.get("cy"))}
    except (TypeError, ValueError):
        return None


def _first_size(sp: ET.Element | None) -> float | None:
    if sp is None:
        return None
    for tag in ("rPr", "defRPr"):
        for node in sp.iter(f"{{{NS['a']}}}{tag}"):
            if node.get("sz"):
                try:
                    return int(node.get("sz")) / 100.0
                except ValueError:
                    pass
    return None


def _body_pr(sp: ET.Element | None) -> dict:
    if sp is None:
        return {}
    body = sp.find("p:txBody/a:bodyPr", NS)
    keys = ("lIns", "rIns", "tIns", "bIns", "anchor", "wrap", "vert")
    return {k: body.get(k) for k in keys if body is not None and body.get(k) is not None}


def _placeholder(part_root: ET.Element, kind: str) -> ET.Element | None:
    kinds = {"title": {"title", "ctrtitle"}, "body": {"body", "object", "subtitles"}}[kind]
    return next((sp for sp in part_root.iter(f"{{{NS['p']}}}sp") if _ph_type(sp) in kinds), None)


def _layout_details(z: zipfile.ZipFile, part: str, master: str | None,
                    name: str, kind: str) -> dict:
    root = ET.fromstring(z.read(part))
    master_root = ET.fromstring(z.read(master)) if master in z.namelist() else None
    detail = {"part": part, "name": name, "type": kind, "master": master,
              "master_exists": bool(master and master in z.namelist()),
              "title_placeholder": False, "title_geometry": None, "body_geometry": None,
              "title_size_pt": None, "body_size_pt": None,
              "title_body_pr": {}, "body_body_pr": {}}
    for side in ("title", "body"):
        ph = _placeholder(root, side)
        master_ph = _placeholder(master_root, side) if master_root is not None else None
        # A blank layout has no title merely because its master has one. Inheritance
        # is used only for a placeholder actually present on the selected layout.
        if ph is not None:
            detail[f"{side}_placeholder"] = True
            detail[f"{side}_placeholder_idx"] = (_ph(ph).get("idx") if _ph(ph) is not None else None)
            detail[f"{side}_geometry"] = _geometry(ph) or _geometry(master_ph)
            detail[f"{side}_geometry_inherited"] = _geometry(ph) is None and _geometry(master_ph) is not None
            detail[f"{side}_size_pt"] = _first_size(ph) or _first_size(master_ph)
            detail[f"{side}_body_pr"] = _body_pr(ph) or _body_pr(master_ph)
    return detail


def layout_matches(requested: str, layouts: list[dict]) -> list[dict]:
    want = _norm(requested)
    exact = [x for x in layouts if want and want in {_norm(x["name"]), _norm(x["type"])}]
    if exact:
        return exact
    aliases = {"title": "titleslide", "content": "titleandcontent", "blank": "blank"}
    want = aliases.get(want, want)
    return [x for x in layouts if want and (
        want in {_norm(x["name"]), _norm(x["type"])}
        or want in _norm(x["name"]) or _norm(x["name"]) in want)]


def measure(path: str | Path) -> dict:
    out = {"read": False, "path": str(path), "layouts": [], "layout_details": [],
           "theme_fonts": {}, "theme_colors": {}, "slide_size_emu": None,
           "master_parts": [], "theme_parts": []}
    try:
        with zipfile.ZipFile(path) as z:
            names = set(z.namelist())
            root = ET.fromstring(z.read("ppt/presentation.xml"))
            size = root.find("p:sldSz", NS)
            if size is not None:
                out["slide_size_emu"] = [int(size.get("cx")), int(size.get("cy"))]
            layouts = sorted(n for n in names if re.fullmatch(r"ppt/slideLayouts/slideLayout\d+\.xml", n))
            masters = sorted(n for n in names if re.fullmatch(r"ppt/slideMasters/slideMaster\d+\.xml", n))
            themes = sorted(n for n in names if re.fullmatch(r"ppt/theme/theme\d+\.xml", n))
            out["master_parts"], out["theme_parts"] = masters, themes
            out["master_hashes"] = {n: _digest(z.read(n)) for n in masters}
            for part in layouts:
                lay = ET.fromstring(z.read(part))
                csld = lay.find("p:cSld", NS)
                master_rels = [r for r in _relations(z, part)
                               if (r.get("Type") or "").endswith("/slideMaster")]
                master = _target(part, master_rels[0]) if master_rels else None
                out["layout_details"].append(_layout_details(
                    z, part, master, (csld.get("name") or "") if csld is not None else "",
                    lay.get("type") or ""))
            out["layouts"] = [x["name"] or x["type"] for x in out["layout_details"]]
            for part in themes:
                theme = ET.fromstring(z.read(part))
                scheme_node = theme.find(".//a:clrScheme", NS)
                if scheme_node is not None:
                    for color_node in list(scheme_node):
                        rgb = color_node.find("a:srgbClr", NS)
                        sysrgb = color_node.find("a:sysClr", NS)
                        value = (rgb.get("val") if rgb is not None else
                                 sysrgb.get("lastClr") if sysrgb is not None else None)
                        if value:
                            out["theme_colors"].setdefault(color_node.tag.rsplit("}", 1)[-1], value.upper())
                for scheme, prefix in (("majorFont", "major"), ("minorFont", "minor")):
                    node = theme.find(f".//a:{scheme}", NS)
                    if node is None:
                        continue
                    for tag, side in (("latin", "latin"), ("ea", "ea")):
                        el = node.find(f"a:{tag}", NS)
                        if el is not None and el.get("typeface"):
                            out["theme_fonts"].setdefault(f"{prefix}_{side}", el.get("typeface"))
            out["read"] = bool(masters and layouts)
            if not out["read"]:
                out["reason"] = "template has no usable slide master/layout pair"
    except (OSError, KeyError, zipfile.BadZipFile, ET.ParseError, TypeError, ValueError) as exc:
        out["reason"] = f"template package could not be parsed: {exc}"
    return out


def audit(measured: dict, spec: dict, deck_size: list[int] | None,
          delivered: dict | None = None) -> list[dict]:
    findings: list[dict] = []

    def add(rule: str, severity: str, message: str, **detail):
        findings.append({"rule": rule, "severity": severity, "message": message,
                         "section": "template_fit", **detail})

    if not measured.get("read"):
        add("template.unreadable", "high",
            "the declared template is not a readable master/layout presentation package",
            reason=measured.get("reason"))
        return findings
    if not measured.get("slide_size_emu"):
        add("template.slide_size_unmeasured", "medium",
            "the real template has no usable slide size; canvas conformance is unknown")
    if any(spec.get(k) for k in ("font_latin", "font_ea")) and not measured.get("theme_fonts"):
        add("template.theme_unmeasured", "medium",
            "no theme typefaces could be resolved through the real template")
    layouts = measured.get("layout_details") or []
    delivered_slides = (delivered or {}).get("slides") or []
    for index, slide in enumerate(spec.get("slides") or [], 1):
        matches = layout_matches(str(slide.get("layout") or "content"), layouts)
        if not matches:
            add("template.layout_not_found", "high",
                "the requested slide layout does not exist in the measured template",
                slide=index, requested=slide.get("layout"))
        elif len(matches) > 1:
            add("template.duplicate_layout_name", "medium",
                "the requested layout alias is ambiguous in the measured template",
                slide=index, requested=slide.get("layout"), matches=[x["part"] for x in matches])
        elif spec.get("require_title_placeholder") and not matches[0].get("title_placeholder"):
            add("template.title_placeholder_missing", "high",
                "the selected real layout has no title placeholder; declare a deliberate fallback",
                slide=index, layout=matches[0]["part"])
        if matches and (not matches[0].get("master") or not matches[0].get("master_exists", True)):
            add("template.layout_master_missing", "high",
                "the selected layout has no master relationship or its target does not exist",
                slide=index, layout=matches[0]["part"], master=matches[0].get("master"))
        if len(matches) == 1 and matches[0].get("title_placeholder") and not matches[0].get("title_geometry"):
            add("template.title_geometry_unmeasured", "medium",
                "the selected title placeholder provides no geometry on the layout or its master",
                slide=index, layout=matches[0]["part"])
        if len(matches) == 1 and index <= len(delivered_slides):
            actual = delivered_slides[index - 1]
            expected = matches[0].get("title_geometry")
            got = actual.get("title_geom")
            if expected and not got:
                add("template.title_geometry_unmeasured", "medium",
                    "the delivered title has no measurable box against a measured layout", slide=index)
            elif expected and got:
                want = [expected[k] for k in ("x", "y", "cx", "cy")]
                if len(got) != 4 or any(abs(float(a) - b) > 114300 for a, b in zip(got, want)):
                    add("template.title_geometry_drift", "medium",
                        "the delivered title box differs from the selected real layout placeholder",
                        slide=index, expected=want, actual=got)
            expected_size = matches[0].get("title_size_pt")
            sizes = actual.get("title_sizes") or []
            if expected_size and sizes:
                off = [s for s in sizes if not 0.8 * expected_size <= float(s) <= 1.25 * expected_size]
                if off:
                    add("template.title_size_off", "low",
                        "the delivered title size differs from the real layout placeholder",
                        slide=index, expected=expected_size, actual=off)
            if actual.get("body_geom") and matches[0].get("body_geometry"):
                expected_body = matches[0]["body_geometry"]
                want_body = [expected_body[k] for k in ("x", "y", "cx", "cy")]
                got_body = actual["body_geom"]
                mismatch = len(got_body) != 4 or any(abs(float(a) - b) > 114300 for a, b in zip(got_body, want_body))
                caption_adjusted = False
                if mismatch and str(slide.get("caption") or slide.get("evidence") or "").strip() and len(got_body) == 4:
                    # Caption bands are a declared content split. Only a shortened
                    # cy with identical origin/width is exempt, never a margin move.
                    caption_adjusted = (
                        all(abs(float(got_body[j]) - want_body[j]) <= 114300 for j in range(3))
                        and 0 < float(got_body[3]) < want_body[3])
                if mismatch and not caption_adjusted:
                    add("template.body_geometry_drift", "medium",
                        "the delivered body box differs from the selected real layout placeholder",
                        slide=index, expected=want_body, actual=got_body)
            expected_body_size = matches[0].get("body_size_pt")
            body_sizes = actual.get("body_sizes") or []
            if expected_body_size and body_sizes:
                off_body = [s for s in body_sizes if not 0.8 * expected_body_size <= float(s) <= 1.25 * expected_body_size]
                if off_body:
                    add("template.body_size_off", "low",
                        "the delivered body size differs from the real layout placeholder",
                        slide=index, expected=expected_body_size, actual=off_body)
    declared = {str(spec.get(k) or "") for k in ("font_latin", "font_ea")} - {""}
    theme = {v for v in (measured.get("theme_fonts") or {}).values() if v}
    if declared and theme:
        missing = sorted(declared - theme)
        if missing:
            add("template.theme_font_mismatch", "medium",
                "declared typefaces differ from the measured template theme",
                declared=missing, measured=sorted(theme))
    template_size = measured.get("slide_size_emu")
    if template_size and deck_size and list(template_size) != list(deck_size):
        add("template.slide_size_mismatch", "medium",
            "the written deck canvas differs from the real template canvas",
            template=template_size, deck=deck_size)
    style = spec.get("style") if isinstance(spec.get("style"), dict) else {}
    declared_colors = style.get("colors") if isinstance(style.get("colors"), dict) else {}
    theme_colors = measured.get("theme_colors") or {}
    color_map = {"background": ("lt1", "bg1"), "text": ("dk1", "tx1"),
                 "title": ("dk2", "tx2", "accent1"), "accent": ("accent1",)}
    mismatches = []
    for name, choices in color_map.items():
        expected = [str(theme_colors[c]).upper() for c in choices if theme_colors.get(c)]
        if not expected:
            continue
        observed: set[str] = set()
        if delivered_slides:
            # Judge the final artifact. Inherited backgrounds and theme colors are
            # valid precisely because the old explicit declaration was replaced.
            for actual_slide in delivered_slides:
                if name == "background" and actual_slide.get("background"):
                    observed.add(str(actual_slide["background"]).upper())
                elif name == "title":
                    observed.update(str(v).upper() for v in actual_slide.get("title_colors") or [])
                elif name == "text":
                    observed.update(str(v).upper() for v in actual_slide.get("body_colors") or [])
        elif name in declared_colors:
            # Direct/unit audit has no written-deck summary, so the declaration is
            # the only available evidence and remains a valid mismatch probe.
            observed.add(str(declared_colors[name]).lstrip("#").upper())
        for actual in sorted(observed):
            if actual not in expected:
                mismatches.append({"field": name, "actual": actual, "template": expected})
    if mismatches:
        add("template.theme_color_mismatch", "medium",
            "delivered colors differ from the real template color scheme", colors=mismatches)
    return findings


def _copy_family(template: zipfile.ZipFile, seed_parts: list[str]) -> dict[str, bytes]:
    """Copy template shell parts and their internal dependencies, never its slides."""
    parts: dict[str, bytes] = {}
    queue = list(seed_parts)
    while queue:
        part = queue.pop(0)
        if not part or part in parts or part not in template.namelist():
            continue
        if part.startswith(("ppt/slides/", "ppt/notesSlides/")):
            continue
        parts[part] = template.read(part)
        rel_name = _rels_name(part)
        if rel_name in template.namelist():
            parts[rel_name] = template.read(rel_name)
            for rel in _relations(template, part):
                if rel.get("TargetMode") == "External":
                    continue
                target = _target(part, rel)
                if target.startswith(("ppt/slides/", "ppt/notesSlides/")):
                    continue
                queue.append(target)
    return parts


def _ensure(parent: ET.Element, tag: str, index: int = 0) -> ET.Element:
    node = parent.find(tag, NS)
    if node is None:
        node = ET.Element(f"{{{NS[tag.split(':')[0]]}}}{tag.split(':')[1]}")
        parent.insert(index, node)
    return node


def _apply_geometry(sp: ET.Element, geometry: dict | None) -> None:
    if not geometry:
        return
    sppr = _ensure(sp, "p:spPr")
    xfrm = sppr.find("a:xfrm", NS)
    if xfrm is None:
        xfrm = ET.Element(f"{{{NS['a']}}}xfrm"); sppr.insert(0, xfrm)
    off = _ensure(xfrm, "a:off")
    ext = _ensure(xfrm, "a:ext")
    for key in ("x", "y"):
        off.set(key, str(geometry[key]))
    for key in ("cx", "cy"):
        ext.set(key, str(geometry[key]))


def _apply_placeholder(sp: ET.Element, kind: str, detail: dict) -> bool:
    if not detail.get(f"{kind}_placeholder"):
        return False
    nv = sp.find("p:nvSpPr/p:nvPr", NS)
    if nv is None:
        return False
    for old in list(nv.findall("p:ph", NS)):
        nv.remove(old)
    ph = ET.Element(f"{{{NS['p']}}}ph")
    if kind == "body":
        ph.set("type", "body")
    else:
        ph.set("type", "title")
    idx = detail.get(f"{kind}_placeholder_idx")
    if idx:
        ph.set("idx", str(idx))
    nv.insert(0, ph)
    c_nv = sp.find("p:nvSpPr/p:cNvSpPr", NS)
    if c_nv is not None:
        c_nv.attrib.pop("txBox", None)
    _apply_geometry(sp, detail.get(f"{kind}_geometry"))
    attrs = detail.get(f"{kind}_body_pr") or {}
    body_pr = sp.find("p:txBody/a:bodyPr", NS)
    if body_pr is not None:
        for key, value in attrs.items():
            body_pr.set(key, str(value))
    for run in list(sp.iter(f"{{{NS['a']}}}r")) + list(sp.iter(f"{{{NS['a']}}}fld")):
        rpr = run.find("a:rPr", NS)
        if rpr is None:
            rpr = ET.Element(f"{{{NS['a']}}}rPr"); run.insert(0, rpr)
        size = detail.get(f"{kind}_size_pt")
        if size:
            rpr.set("sz", str(int(round(float(size) * 100))))
    return True


def _apply_layout(slide_data: bytes, detail: dict, theme_fonts: dict,
                  theme_colors: dict | None = None) -> tuple[bytes, dict]:
    root = ET.fromstring(slide_data)
    # A generated explicit white rectangle would hide the real template background.
    csld = root.find("p:cSld", NS)
    if csld is not None:
        for bg in list(csld.findall("p:bg", NS)):
            csld.remove(bg)
    record = {"title_placeholder": False, "body_placeholder": False,
              "textbox_fallback": [], "theme_fonts_applied": bool(theme_fonts),
              "theme_colors_applied": bool(theme_colors)}
    for sp in root.iter(f"{{{NS['p']}}}sp"):
        cnv = sp.find(".//p:cNvPr", NS)
        name = (cnv.get("name") or "") if cnv is not None else ""
        ph = _ph(sp)
        ph_type = (ph.get("type") or "body") if ph is not None else ""
        for kind in ("title", "body"):
            named = name.casefold().startswith(kind) or (
                ph_type in ({"title", "ctrtitle"} if kind == "title" else {"body", "object"}))
            if not named:
                continue
            if _apply_placeholder(sp, kind, detail):
                record[f"{kind}_placeholder"] = True
            else:
                record["textbox_fallback"].append(kind)
            fonts = (("major_latin", "major_ea") if kind == "title" else ("minor_latin", "minor_ea"))
            for run in sp.iter(f"{{{NS['a']}}}r"):
                rpr = run.find("a:rPr", NS)
                if rpr is None:
                    continue
                for tag, key in (("latin", fonts[0]), ("ea", fonts[1])):
                    if not theme_fonts.get(key):
                        continue
                    node = rpr.find(f"a:{tag}", NS)
                    if node is None:
                        node = ET.SubElement(rpr, f"{{{NS['a']}}}{tag}")
                    node.set("typeface", str(theme_fonts[key]))
                if theme_colors:
                    keys = ("dk2", "tx2", "accent1", "dk1", "tx1") if kind == "title" else ("dk1", "tx1")
                    color = next((theme_colors[k] for k in keys if theme_colors.get(k)), None)
                    if color:
                        fill = rpr.find("a:solidFill", NS)
                        if fill is None:
                            fill = ET.Element(f"{{{NS['a']}}}solidFill")
                            rpr.insert(0, fill)
                        for old in list(fill):
                            fill.remove(old)
                        ET.SubElement(fill, f"{{{NS['a']}}}srgbClr").set("val", str(color).upper())
            break
    # Preserve an independent caption band when a full-height template body
    # would cover it. x/y/width stay on the layout; height is the required content
    # split, recorded by the downstream geometry audit and never hidden silently.
    captions = []
    bodies = []
    for sp in root.iter(f"{{{NS['p']}}}sp"):
        cnv = sp.find(".//p:cNvPr", NS)
        name = (cnv.get("name") or "") if cnv is not None else ""
        if name.casefold() == "caption":
            captions.append(sp)
        if _ph_type(sp) in {"body", "object"}:
            bodies.append(sp)
    for body in bodies:
        body_box = _geometry(body)
        if not body_box:
            continue
        for caption in captions:
            cap_box = _geometry(caption)
            if not cap_box:
                continue
            gap = int(0.15 * 914400)
            adjusted_cy = cap_box["y"] - body_box["y"] - gap
            if 0 < adjusted_cy < body_box["cy"]:
                updated = dict(body_box, cy=adjusted_cy)
                _apply_geometry(body, updated)
                body_box = updated
                record.setdefault("caption_bands_preserved", []).append(
                    {"caption_y": cap_box["y"], "body_cy": adjusted_cy})
    return ET.tostring(root, encoding="utf-8", xml_declaration=True), record


def apply_shell(generated: str | Path, template_path: str | Path,
                spec: dict, measured: dict) -> dict:
    """Replace the generated shell with the real template and reconnect slide layouts."""
    if not measured.get("read"):
        return {"applied": False, "reason": measured.get("reason", "template unreadable")}
    generated, template_path = Path(generated), Path(template_path)
    layouts = measured["layout_details"]
    selected: dict[int, dict] = {}
    for index, slide in enumerate(spec.get("slides") or [], 1):
        matches = layout_matches(str(slide.get("layout") or "content"), layouts)
        if len(matches) != 1:
            return {"applied": False, "reason": f"slide {index} has {len(matches)} matching layouts"}
        if not matches[0].get("master_exists", True):
            return {"applied": False, "reason": f"slide {index} layout has no existing master part"}
        selected[index] = matches[0]
    tmp = generated.with_name(generated.stem + "_template.pptx")
    with zipfile.ZipFile(generated) as deck, zipfile.ZipFile(template_path) as tpl:
        shell_seeds = measured["master_parts"] + measured["theme_parts"] + [x["part"] for x in layouts]
        shell = _copy_family(tpl, shell_seeds)
        deck_parts = {n: deck.read(n) for n in deck.namelist()
                      if not n.startswith(("ppt/slideMasters/", "ppt/slideLayouts/", "ppt/theme/"))}
        deck_parts.update(shell)

        # Slide size comes from the real template; presentation relationships point to it.
        pres_name = "ppt/presentation.xml"
        pres = ET.fromstring(deck_parts[pres_name])
        size = pres.find("p:sldSz", NS)
        if size is not None and measured.get("slide_size_emu"):
            size.set("cx", str(measured["slide_size_emu"][0]))
            size.set("cy", str(measured["slide_size_emu"][1]))
        deck_parts[pres_name] = ET.tostring(pres, encoding="utf-8", xml_declaration=True)
        prels_name = "ppt/_rels/presentation.xml.rels"
        prels = ET.fromstring(deck_parts[prels_name])
        for rel in prels:
            kind = (rel.get("Type") or "").rsplit("/", 1)[-1]
            if kind == "slideMaster" and measured["master_parts"]:
                rel.set("Target", posixpath.relpath(measured["master_parts"][0], "ppt"))
            elif kind == "theme" and measured["theme_parts"]:
                rel.set("Target", posixpath.relpath(measured["theme_parts"][0], "ppt"))
        deck_parts[prels_name] = _opc_xml(prels, "pr")

        placeholder_records = {}
        for index, lay in selected.items():
            slide_part = f"ppt/slides/slide{index}.xml"
            slide_xml, placeholder_records[str(index)] = _apply_layout(
                deck_parts[slide_part], lay, measured.get("theme_fonts") or {},
                measured.get("theme_colors") or {})
            deck_parts[slide_part] = slide_xml
            rel_name = _rels_name(slide_part)
            root = ET.fromstring(deck_parts[rel_name])
            for rel in root:
                if (rel.get("Type") or "").endswith("/slideLayout"):
                    rel.set("Target", posixpath.relpath(lay["part"], "ppt/slides"))
            deck_parts[rel_name] = _opc_xml(root, "pr")

        # Retain content-type declarations for every newly copied shell part.
        generated_ct = ET.fromstring(deck_parts["[Content_Types].xml"])
        template_ct = ET.fromstring(tpl.read("[Content_Types].xml"))
        covered = {el.get("PartName") for el in generated_ct if el.tag.endswith("Override")}
        for el in template_ct:
            part_name = el.get("PartName")
            if part_name and part_name.lstrip("/") in shell and part_name not in covered:
                generated_ct.append(el)
        deck_parts["[Content_Types].xml"] = _opc_xml(generated_ct, "ct")
        with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as out:
            for name, data in deck_parts.items():
                out.writestr(name, data)
    tmp.replace(generated)
    return {"applied": True, "template": str(template_path),
            "masters": measured["master_parts"], "layouts": {str(k): v["part"] for k, v in selected.items()},
            "placeholder_records": placeholder_records,
            "note": "real master/layout/theme copied; title/body use native placeholders when the selected layout provides them"}
