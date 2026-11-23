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
           "theme_fonts": {}, "slide_size_emu": None, "master_parts": [], "theme_parts": []}
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
                title_nodes = [sp for sp in lay.iter(f"{{{NS['p']}}}sp")
                               if (sp.find(".//p:nvPr/p:ph", NS) is not None
                                   and (sp.find(".//p:nvPr/p:ph", NS).get("type") or "body")
                                   in ("title", "ctrTitle"))]
                out["layout_details"].append({
                    "part": part,
                    "name": (csld.get("name") or "") if csld is not None else "",
                    "type": lay.get("type") or "",
                    "master": _target(part, master_rels[0]) if master_rels else None,
                    "title_placeholder": bool(title_nodes),
                })
            out["layouts"] = [x["name"] or x["type"] for x in out["layout_details"]]
            for part in themes:
                theme = ET.fromstring(z.read(part))
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


def audit(measured: dict, spec: dict, deck_size: list[int] | None) -> list[dict]:
    findings: list[dict] = []

    def add(rule: str, severity: str, message: str, **detail):
        findings.append({"rule": rule, "severity": severity, "message": message,
                         "section": "template_fit", **detail})

    if not measured.get("read"):
        add("template.unreadable", "high",
            "the declared template is not a readable master/layout presentation package",
            reason=measured.get("reason"))
        return findings
    layouts = measured.get("layout_details") or []
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
        if matches and not matches[0].get("master"):
            add("template.layout_master_missing", "high",
                "the selected layout has no master relationship", slide=index,
                layout=matches[0]["part"])
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
        deck_parts[prels_name] = ET.tostring(prels, encoding="utf-8", xml_declaration=True)

        for index, lay in selected.items():
            slide_part = f"ppt/slides/slide{index}.xml"
            rel_name = _rels_name(slide_part)
            root = ET.fromstring(deck_parts[rel_name])
            for rel in root:
                if (rel.get("Type") or "").endswith("/slideLayout"):
                    rel.set("Target", posixpath.relpath(lay["part"], "ppt/slides"))
            deck_parts[rel_name] = ET.tostring(root, encoding="utf-8", xml_declaration=True)

        # Retain content-type declarations for every newly copied shell part.
        generated_ct = ET.fromstring(deck_parts["[Content_Types].xml"])
        template_ct = ET.fromstring(tpl.read("[Content_Types].xml"))
        covered = {el.get("PartName") for el in generated_ct if el.tag.endswith("Override")}
        for el in template_ct:
            part_name = el.get("PartName")
            if part_name and part_name.lstrip("/") in shell and part_name not in covered:
                generated_ct.append(el)
        deck_parts["[Content_Types].xml"] = ET.tostring(
            generated_ct, encoding="utf-8", xml_declaration=True)
        with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as out:
            for name, data in deck_parts.items():
                out.writestr(name, data)
    tmp.replace(generated)
    return {"applied": True, "template": str(template_path),
            "masters": measured["master_parts"], "layouts": {str(k): v["part"] for k, v in selected.items()}}
