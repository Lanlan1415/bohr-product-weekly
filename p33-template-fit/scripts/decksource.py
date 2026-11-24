"""Inspect and text-edit a real starting PPTX without discarding its package.

The router's editing path must preserve the organizer's masters, layouts, media,
and embedded objects.  This module therefore patches only DrawingML paragraphs
in a copy of the source package.  It never rebuilds a source deck from memory.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import zipfile
from pathlib import Path
import xml.etree.ElementTree as ET

A = "http://schemas.openxmlformats.org/drawingml/2006/main"
P = "http://schemas.openxmlformats.org/presentationml/2006/main"
NS = {"a": A, "p": P}
ET.register_namespace("a", A)
ET.register_namespace("p", P)


def _opc_xml(root: ET.Element, uri: str) -> bytes:
    ET.register_namespace("", uri)
    return ET.tostring(root, encoding="utf-8", xml_declaration=True)


def sha256(path: str | Path) -> str:
    h = hashlib.sha256()
    with Path(path).open("rb") as fh:
        for block in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def _slide_parts(z: zipfile.ZipFile) -> list[str]:
    return sorted(
        (n for n in z.namelist() if re.fullmatch(r"ppt/slides/slide\d+\.xml", n)),
        key=lambda n: int(re.search(r"(\d+)", n.rsplit("/", 1)[-1]).group(1)),
    )


def _slide_parts_from_names(names) -> list[str]:
    return sorted((n for n in names if re.fullmatch(r"ppt/slides/slide\d+\.xml", n)),
                  key=lambda n: int(re.search(r"(\d+)", n.rsplit("/", 1)[-1]).group(1)))


def _texts(root: ET.Element) -> list[str]:
    return [t.text or "" for t in root.iter(f"{{{A}}}t")]


def inspect(path: str | Path) -> dict:
    """Return an honest extraction skeleton; claims/evidence remain for the agent."""
    path = Path(path)
    out = {"source_deck": str(path), "read": False, "slides": [], "limits": []}
    try:
        with zipfile.ZipFile(path) as z:
            parts = _slide_parts(z)
            if "ppt/presentation.xml" not in z.namelist():
                raise ValueError("ppt/presentation.xml is missing")
            for index, part in enumerate(parts, 1):
                root = ET.fromstring(z.read(part))
                text = "\n".join(t for t in _texts(root) if t.strip())
                notes_part = f"ppt/notesSlides/notesSlide{index}.xml"
                notes = ""
                if notes_part in z.namelist():
                    notes = "\n".join(_texts(ET.fromstring(z.read(notes_part))))
                lines = [line for line in text.splitlines() if line.strip()]
                out["slides"].append({
                    "title": lines[0] if lines else "",
                    "layout": "content",
                    "claim": "",
                    "evidence": "",
                    "bullets": lines[1:],
                    "notes": notes,
                })
            out["read"] = True
            out["sha256"] = sha256(path)
            out["slide_count"] = len(parts)
            if not parts:
                out["limits"].append("source deck contains no slides")
    except (OSError, zipfile.BadZipFile, ET.ParseError, ValueError) as exc:
        out["error"] = str(exc)
        out["limits"].append("source deck could not be parsed; no content was inferred")
    return out


def _ordered_revisions(spec: dict) -> list[dict]:
    revisions = list(spec.get("revisions") or [])
    pointer = spec.get("delivered_revision")
    if pointer is None:
        return revisions
    for pos, rev in enumerate(revisions, 1):
        try:
            match = int(pointer) in (pos, int(rev.get("n")))
        except (TypeError, ValueError):
            match = int(pointer) == pos
        if match:
            return revisions[:pos]
    return revisions


def _replace_in_part(data: bytes, before: str, after: str) -> tuple[bytes, int]:
    """Replace across split runs while retaining the first run's formatting."""
    root = ET.fromstring(data)
    replacements = 0
    for para in root.iter(f"{{{A}}}p"):
        nodes = list(para.iter(f"{{{A}}}t"))
        if not nodes:
            continue
        joined = "".join(node.text or "" for node in nodes)
        if before not in joined:
            continue
        updated = joined.replace(before, after, 1)
        nodes[0].text = updated
        for node in nodes[1:]:
            node.text = ""
        replacements += 1
    if not replacements:
        return data, 0
    return ET.tostring(root, encoding="utf-8", xml_declaration=True), replacements


def _already_in_part(data: bytes, after: str) -> bool:
    if not after:
        return False
    try:
        root = ET.fromstring(data)
    except ET.ParseError:
        return False
    return any(after in "".join(t.text or "" for t in para.iter(f"{{{A}}}t"))
               for para in root.iter(f"{{{A}}}p"))


def _named_shapes(root: ET.Element, wanted: str) -> list[ET.Element]:
    """Resolve an explicit shape name, or the unique title/body placeholder."""
    needle = str(wanted or "").strip().casefold()
    matches = []
    for tag in (f"{{{P}}}sp", f"{{{P}}}pic"):
        for shape in root.iter(tag):
            props = shape.find(".//p:cNvPr", NS)
            name = (props.get("name") or "") if props is not None else ""
            ph = shape.find(".//p:nvPr/p:ph", NS)
            ph_type = (ph.get("type") or "body") if ph is not None else ""
            if (needle and name.casefold() == needle) or \
                    (needle in {"title", "body"} and ph_type.casefold() == needle):
                matches.append(shape)
    return matches


def _child(parent: ET.Element, tag: str, index: int = 0) -> ET.Element:
    found = parent.find(tag, NS)
    if found is None:
        found = ET.Element(f"{{{NS[tag.split(':')[0]]}}}{tag.split(':')[1]}")
        parent.insert(index, found)
    return found


def _geometry_action(data: bytes, change: dict) -> tuple[bytes, str, dict]:
    root = ET.fromstring(data)
    shapes = _named_shapes(root, str(change.get("shape") or change.get("shape_name") or ""))
    if len(shapes) != 1:
        return data, "shape_missing" if not shapes else "shape_ambiguous", {"matches": len(shapes)}
    raw = change.get("geometry_emu", change.get("geometry"))
    unit = "emu" if "geometry_emu" in change else str(change.get("unit") or "in").lower()
    if isinstance(raw, dict):
        vals = [raw.get("x"), raw.get("y"), raw.get("w", raw.get("cx")),
                raw.get("h", raw.get("cy"))]
    elif isinstance(raw, (list, tuple)):
        vals = list(raw)
    else:
        vals = []
    try:
        if len(vals) != 4:
            raise ValueError("geometry requires x,y,w,h")
        nums = [float(v) for v in vals]
        if any(v < 0 for v in nums) or nums[2] <= 0 or nums[3] <= 0:
            raise ValueError("origin must be non-negative and extents positive")
        if unit in {"in", "inch", "inches"}:
            nums = [v * 914400 for v in nums]
        elif unit != "emu":
            raise ValueError("unit must be 'in' or 'emu'")
        values = [int(round(v)) for v in nums]
    except (TypeError, ValueError) as exc:
        return data, "invalid_geometry", {"error": str(exc)}
    shape = shapes[0]
    sppr = _child(shape, "p:spPr")
    xfrm = sppr.find("a:xfrm", NS)
    if xfrm is None:
        xfrm = ET.Element(f"{{{A}}}xfrm")
        sppr.insert(0, xfrm)
    off = _child(xfrm, "a:off")
    ext = _child(xfrm, "a:ext")
    updated = 0
    for el, names, pair in ((off, ("x", "y"), values[:2]), (ext, ("cx", "cy"), values[2:])):
        for name, value in zip(names, pair):
            if el.get(name) != str(value):
                el.set(name, str(value)); updated += 1
    if not updated:
        return data, "already_present", {"geometry_emu": values}
    return (ET.tostring(root, encoding="utf-8", xml_declaration=True), "applied",
            {"shape": change.get("shape") or change.get("shape_name"), "geometry_emu": values})


def _style_action(data: bytes, change: dict) -> tuple[bytes, str, dict]:
    root = ET.fromstring(data)
    shapes = _named_shapes(root, str(change.get("shape") or change.get("shape_name") or ""))
    if len(shapes) != 1:
        return data, "shape_missing" if not shapes else "shape_ambiguous", {"matches": len(shapes)}
    color = str(change.get("color") or "").lstrip("#").upper()
    if color and not re.fullmatch(r"[0-9A-F]{6}", color):
        return data, "invalid_style", {"error": "color must be six-digit RGB"}
    try:
        size = float(change["font_size_pt"]) if "font_size_pt" in change else None
        if size is not None and not 4 <= size <= 200:
            raise ValueError("font_size_pt outside 4..200")
    except (TypeError, ValueError) as exc:
        return data, "invalid_style", {"error": str(exc)}
    updated = 0
    for run in list(shapes[0].iter(f"{{{A}}}r")) + list(shapes[0].iter(f"{{{A}}}fld")):
        rpr = run.find("a:rPr", NS)
        if rpr is None:
            rpr = ET.Element(f"{{{A}}}rPr"); run.insert(0, rpr)
        if size is not None and rpr.get("sz") != str(int(round(size * 100))):
            rpr.set("sz", str(int(round(size * 100)))); updated += 1
        if "bold" in change:
            value = "1" if bool(change["bold"]) else "0"
            if rpr.get("b") != value:
                rpr.set("b", value); updated += 1
        for key, tag in (("font_latin", "latin"), ("font_ea", "ea")):
            face = str(change.get(key) or "")
            if face:
                el = rpr.find(f"a:{tag}", NS)
                if el is None:
                    el = ET.SubElement(rpr, f"{{{A}}}{tag}")
                if el.get("typeface") != face:
                    el.set("typeface", face); updated += 1
        if color:
            fill = rpr.find("a:solidFill", NS)
            existing = fill.find("a:srgbClr", NS) if fill is not None else None
            if existing is not None and str(existing.get("val") or "").upper() == color:
                continue
            if fill is None:
                fill = ET.Element(f"{{{A}}}solidFill"); rpr.insert(0, fill)
            for child in list(fill):
                fill.remove(child)
            rgb = ET.SubElement(fill, f"{{{A}}}srgbClr")
            rgb.set("val", color); updated += 1
    if not updated:
        return data, "already_present", {"shape": change.get("shape") or change.get("shape_name")}
    return (ET.tostring(root, encoding="utf-8", xml_declaration=True), "applied",
            {"shape": change.get("shape") or change.get("shape_name"),
             "font_size_pt": size, "color": color or None})


def _batch_config(spec: dict) -> dict | None:
    raw = spec.get("batch_format")
    if not raw:
        return None
    return raw if isinstance(raw, dict) else {}


def _canvas(parts: dict[str, bytes]) -> tuple[int, int]:
    root = ET.fromstring(parts["ppt/presentation.xml"])
    size = root.find("p:sldSz", NS)
    if size is None:
        raise ValueError("source presentation has no slide size")
    return int(size.get("cx")), int(size.get("cy"))


def _next_shape_id(root: ET.Element) -> int:
    values = []
    for node in root.iter(f"{{{P}}}cNvPr"):
        try:
            values.append(int(node.get("id")))
        except (TypeError, ValueError):
            pass
    return max(values, default=1) + 1


def _drop_old_batch_shapes(root: ET.Element) -> None:
    tree = root.find("p:cSld/p:spTree", NS)
    if tree is None:
        raise ValueError("slide has no shape tree")
    for tag in ("sp", "pic"):
        for sp in list(tree.findall(f"p:{tag}", NS)):
            cnv = sp.find(".//p:cNvPr", NS)
            name = (cnv.get("name") or "") if cnv is not None else ""
            ph = sp.find(".//p:nvPr/p:ph", NS)
            ph_type = (ph.get("type") or "body") if ph is not None else ""
            if name in {"Footer", "Slide Number", "Logo"} or ph_type in {"ftr", "sldNum"}:
                tree.remove(sp)


def _logo_relation(parts: dict[str, bytes], index: int, logo: str) -> tuple[str, str]:
    """Embed one image and return its relationship ID and added package part."""
    import pptxgen as PG
    rel_ns = "http://schemas.openxmlformats.org/package/2006/relationships"
    rel_part = f"ppt/slides/_rels/slide{index}.xml.rels"
    if rel_part in parts:
        root = ET.fromstring(parts[rel_part])
    else:
        root = ET.Element(f"{{{rel_ns}}}Relationships")
        parts[rel_part] = _opc_xml(root, rel_ns)
    ext = Path(logo).suffix.lower().lstrip(".") or "png"
    media = f"ppt/media/batch_logo.{ext}"
    target = f"../media/batch_logo.{ext}"
    used = []
    for rel in list(root):
        if rel.get("Target") == target:
            if media not in parts:
                parts[media] = Path(logo).read_bytes()
            parts[rel_part] = _opc_xml(root, rel_ns)
            return rel.get("Id"), media
        match = re.fullmatch(r"rId(\d+)", rel.get("Id") or "")
        if match:
            used.append(int(match.group(1)))
    rid = f"rId{max(used, default=1) + 1}"
    rel = ET.SubElement(root, f"{{{rel_ns}}}Relationship")
    rel.set("Id", rid)
    rel.set("Type", "http://schemas.openxmlformats.org/officeDocument/2006/relationships/image")
    rel.set("Target", target)
    parts[media] = Path(logo).read_bytes()
    parts[rel_part] = _opc_xml(root, rel_ns)

    # Ensure content-type coverage even for a minimal organizer source package.
    ct_name = "[Content_Types].xml"
    ct = ET.fromstring(parts[ct_name])
    known = {str(el.get("Extension") or "").lower() for el in ct}
    if ext not in known:
        node = ET.SubElement(ct, "{http://schemas.openxmlformats.org/package/2006/content-types}Default")
        node.set("Extension", ext)
        node.set("ContentType", "image/jpeg" if ext in {"jpg", "jpeg"} else f"image/{ext}")
        parts[ct_name] = _opc_xml(ct, "http://schemas.openxmlformats.org/package/2006/content-types")
    return rid, media


def _apply_batch(slide_data: bytes, index: int, spec: dict, config: dict,
                 width: int, height: int, logo_rid: str | None) -> tuple[bytes, dict]:
    import pptxgen as PG
    data = slide_data
    applied_styles = []
    for kind in ("title", "body"):
        style = config.get(f"{kind}_style")
        if isinstance(style, dict) and style:
            updated, status, detail = _style_action(data, dict(style, shape=kind))
            if status in {"shape_ambiguous", "invalid_style"}:
                raise ValueError(f"batch {kind} style failed on slide {index}: {detail}")
            if status == "applied":
                data = updated; applied_styles.append(kind)
        geometry = config.get(f"{kind}_geometry")
        if geometry is not None:
            change = {"shape": kind, "unit": "in"}
            if isinstance(geometry, dict) and set(geometry) == {"x", "y", "cx", "cy"}:
                change["geometry_emu"] = geometry
            else:
                change["geometry"] = geometry
            updated, status, detail = _geometry_action(data, change)
            if status in {"shape_ambiguous", "invalid_geometry"}:
                raise ValueError(f"batch {kind} geometry failed on slide {index}: {detail}")
            if status == "applied":
                data = updated; applied_styles.append(f"{kind}_geometry")

    root = ET.fromstring(data)
    style = PG.normalize_style(spec.get("style"), [])
    footer = style["footer"]
    replace_footer = bool(config.get("footer", True)) and bool(
        footer.get("text") or footer.get("page_numbers") or footer.get("logo"))
    if replace_footer:
        _drop_old_batch_shapes(root)
    tree = root.find("p:cSld/p:spTree", NS)
    colors = style["colors"]
    top, right, bottom, left = (int(round(v * 914400)) for v in style["margins_in"])
    sid = _next_shape_id(root)
    footer_y = height - int(0.58 * 914400)
    footer_x = left
    body_size = float((spec.get("spacing") or {}).get("body", 20))
    if replace_footer and footer.get("logo") and logo_rid:
        logo = str(footer["logo"])
        sw, sh = int(0.58 * 914400), int(0.34 * 914400)
        x, y, w, h = left, footer_y, sw, sh
        size = PG.image_size(logo)
        if size:
            ox, oy, w0, h0 = PG.fit_into(sw, sh, size[0], size[1])
            x, y, w, h = left + ox, footer_y + oy, w0, h0
        node = PG._pic(sid, "Logo", logo_rid, x, y, w, h,
                       str(footer.get("logo_alt") or ""))
        tree.append(ET.fromstring(node)); sid += 1
        footer_x += int(0.72 * 914400)
    number_w = int(0.65 * 914400) if replace_footer and footer.get("page_numbers") else 0
    if replace_footer and footer.get("text"):
        node = PG._txbox(sid, "Footer", footer_x, footer_y,
                         max(int(0.5 * 914400), width - right - footer_x - number_w),
                         int(0.42 * 914400),
                         PG._para(str(footer["text"]), max(14, body_size - 6), 0, False,
                                  str(spec.get("font_latin") or PG.DEFAULT_FONT_LATIN),
                                  str(spec.get("font_ea") or PG.DEFAULT_FONT_EA), bullet=False,
                                  color=colors["muted"]))
        tree.append(ET.fromstring(node)); sid += 1
    if replace_footer and footer.get("page_numbers"):
        node = PG._slide_number(sid, index, width - right - number_w, footer_y, number_w,
                                int(0.42 * 914400), max(14, body_size - 6),
                                (str(spec.get("font_latin") or PG.DEFAULT_FONT_LATIN),
                                 str(spec.get("font_ea") or PG.DEFAULT_FONT_EA)), colors["muted"])
        tree.append(ET.fromstring(node)); sid += 1
    record = {"action": "batch_format", "slide": index, "status": "applied",
              "styles": applied_styles, "footer": bool(replace_footer and footer.get("text")),
              "page_number": bool(replace_footer and footer.get("page_numbers")),
              "logo": bool(replace_footer and footer.get("logo") and logo_rid)}
    return ET.tostring(root, encoding="utf-8", xml_declaration=True), record


def apply_changes(source: str | Path, output: str | Path, spec: dict) -> dict:
    """Apply revisions through the delivered pointer and preserve every other part.

    Each change becomes an execution record: applied, already_present, unsupported,
    or before_missing.  The caller turns before_missing into edit.before_not_in_source.
    """
    source, output = Path(source), Path(output)
    with zipfile.ZipFile(source) as zin:
        original = {name: zin.read(name) for name in zin.namelist()}
    parts = dict(original)
    records: list[dict] = []
    revisions = _ordered_revisions(spec)
    for rpos, rev in enumerate(revisions, 1):
        for cpos, change in enumerate(rev.get("changes") or [], 1):
            rec = {"revision": rev.get("n", rpos), "change": cpos,
                   "slide": change.get("slide"), "status": "unsupported"}
            records.append(rec)
            action = str(change.get("action") or "replace_text").strip().lower()
            if action in {"set_geometry", "move_resize", "set_style", "format_shape"}:
                try:
                    slide = int(change.get("slide"))
                except (TypeError, ValueError):
                    rec["status"] = "invalid_slide"
                    continue
                part = f"ppt/slides/slide{slide}.xml"
                data = parts.get(part)
                if data is None:
                    rec["status"] = "invalid_slide"
                    continue
                rec["action"] = action
                rec["shape"] = change.get("shape") or change.get("shape_name")
                try:
                    if action in {"set_geometry", "move_resize"}:
                        updated, status, detail = _geometry_action(data, change)
                    else:
                        updated, status, detail = _style_action(data, change)
                except ET.ParseError:
                    rec["status"] = "malformed_xml"
                    continue
                rec["status"] = status
                rec.update(detail)
                if status == "applied":
                    parts[part] = updated
                continue
            if "before" not in change or "after" not in change:
                rec["status"] = "structural_record_only"
                continue
            try:
                slide = int(change.get("slide"))
            except (TypeError, ValueError):
                rec["status"] = "invalid_slide"
                continue
            before, after = str(change.get("before") or ""), str(change.get("after") or "")
            if not before:
                rec["status"] = "before_missing"
                continue
            target = str(change.get("target") or "slide").lower()
            part = (f"ppt/notesSlides/notesSlide{slide}.xml" if target == "notes"
                    else f"ppt/slides/slide{slide}.xml")
            data = parts.get(part)
            if data is None:
                rec["status"] = "invalid_slide"
                continue
            try:
                updated, count = _replace_in_part(data, before, after)
            except ET.ParseError:
                rec["status"] = "malformed_xml"
                continue
            if count:
                parts[part] = updated
                rec["status"] = "applied"
                rec["replacements"] = count
            elif _already_in_part(data, after):
                rec["status"] = "already_present"
            else:
                rec["status"] = "before_missing"
    added_parts: set[str] = set()
    batch = _batch_config(spec)
    if batch is not None:
        width, height = _canvas(parts)
        style_footer = spec.get("style", {}).get("footer", {}) if isinstance(spec.get("style"), dict) else {}
        logo = style_footer.get("logo")
        logo_path = Path(str(logo)).is_file() if logo else False
        for match in _slide_parts_from_names(parts):
            index = int(re.search(r"(\d+)", match.rsplit("/", 1)[-1]).group(1))
            rid = None
            if logo_path:
                rid, media = _logo_relation(parts, index, str(logo))
                added_parts.add(media)
                rel_part = f"ppt/slides/_rels/slide{index}.xml.rels"
                if rel_part not in original:
                    added_parts.add(rel_part)
            parts[match], record = _apply_batch(parts[match], index, spec, batch,
                                                  width, height, rid)
            records.append(record)
    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as zout:
        for name, data in parts.items():
            zout.writestr(name, data)
    dropped = set(original) - set(parts)
    unexpected_added = (set(parts) - set(original)) - added_parts
    return {"source": str(source), "source_sha256": sha256(source),
            "output": str(output), "output_sha256": sha256(output),
            "package_preserved": not dropped and not unexpected_added,
            "added_parts": sorted(added_parts), "dropped_parts": sorted(dropped),
            "batch_format_applied": batch is not None,
            "records": records}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--source", required=True)
    ap.add_argument("--out", required=True, help="JSON extraction skeleton, not a result.json")
    args = ap.parse_args(argv)
    report = inspect(args.source)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"read": report["read"], "slides": len(report["slides"]), "wrote": str(out)},
                     ensure_ascii=False))
    return 0 if report["read"] else 5


if __name__ == "__main__":
    raise SystemExit(main())
