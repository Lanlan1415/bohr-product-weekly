"""Inspect, safely apply, and audit real DOCX/TeX template adaptation.

The historical writeaudit.py checks declared records.  This primary entry point
adds file-level evidence: DOCX OOXML is read directly from its ZIP (never
extracted), controlled style/page settings are changed without changing text,
content units are counted before/after, and every declared template requirement
gets pass/fail/unverified in a compliance matrix.  TeX templates are parsed for
actual class/geometry/font/bibliography declarations.  Rendering, visual quality,
and font embedding are never inferred from OOXML.

Usage:
  python formatfit.py --spec /app/work/format-spec.json --case /input/case.json \
      --input-root /input --out /app/output

Spec essentials: source_file, template_file (docx/json/tex), output_file when
auditing an existing conversion, apply:true to create adapted.docx, and optional
template.spec/sections/headings.  See examples/run_minimal.py.

Exit 0 clean, 3 review (unverified properties), 4 blocked (mismatch/content
loss), 5 undetermined/refused.  Structured result.json is written on input and
processing errors; unexpected exceptions do not leak a traceback.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import re
import sys
import zipfile
from pathlib import Path
from typing import Any
from xml.etree import ElementTree as ET

EXIT = {"clean": 0, "review": 3, "blocked": 4, "undetermined": 5}
W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
M = "http://schemas.openxmlformats.org/officeDocument/2006/math"
NS = {"w": W, "m": M}
Q = lambda tag: f"{{{W}}}{tag}"
UNIT_KINDS = ("figures", "tables", "equations", "footnotes", "comments", "revisions",
              "fields", "section_breaks", "embedded")
CONTROLLED = ("margin_mm", "page_size", "font", "size_pt", "line_spacing", "columns",
              "caption_position", "reference_style", "heading_levels", "export_format",
              "header_footer", "page_numbers", "toc_expected")
DERIVED = {"case_id", "status", "findings", "severity_counts", "checked", "limits",
           "deliverable", "revised_manuscript", "export_record", "change_log",
           "template_requirements", "compliance", "content_preservation", "sources",
           "rendering", "applied_changes", "contract_fields"}


def _add(findings: list[dict], rule: str, severity: str, message: str, **kw: Any) -> None:
    findings.append({"rule": rule, "severity": severity, "message": message, **kw})


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _text_of(el: ET.Element | None) -> str:
    if el is None:
        return ""
    return "".join((x.text or "") for x in el.iter() if x.tag in {Q("t"), Q("delText")})


def _child(parent: ET.Element, tag: str) -> ET.Element:
    found = parent.find(f"w:{tag}", NS)
    if found is None:
        found = ET.SubElement(parent, Q(tag))
    return found


def _float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _mm(twips: Any) -> float | None:
    number = _float(twips)
    return round(number * 25.4 / 1440.0, 3) if number is not None else None


def _twips(mm: Any) -> str | None:
    number = _float(mm)
    return str(int(round(number * 1440.0 / 25.4))) if number is not None else None


def _style(styles: ET.Element, style_id: str) -> ET.Element | None:
    for st in styles.findall("w:style", NS):
        if st.get(Q("styleId")) == style_id:
            return st
    return None


def _rpr_values(rpr: ET.Element | None) -> dict[str, Any]:
    out: dict[str, Any] = {}
    if rpr is None:
        return out
    fonts = rpr.find("w:rFonts", NS)
    if fonts is not None:
        out["font"] = (fonts.get(Q("ascii")) or fonts.get(Q("hAnsi"))
                       or fonts.get(Q("eastAsia")))
    size = rpr.find("w:sz", NS)
    if size is not None and _float(size.get(Q("val"))) is not None:
        out["size_pt"] = _float(size.get(Q("val"))) / 2
    return out


def _ppr_values(ppr: ET.Element | None) -> dict[str, Any]:
    out: dict[str, Any] = {}
    if ppr is None:
        return out
    spacing = ppr.find("w:spacing", NS)
    if spacing is not None and spacing.get(Q("line")):
        line = _float(spacing.get(Q("line")))
        if line is not None:
            out["line_spacing"] = round(line / 240.0, 3)
    return out


def _normal_style(styles: ET.Element) -> ET.Element | None:
    normal = _style(styles, "Normal")
    if normal is not None:
        return normal
    for st in styles.findall("w:style", NS):
        if st.get(Q("type")) == "paragraph" and st.get(Q("default")) == "1":
            return st
    return None


def inspect_docx(path: Path) -> dict[str, Any]:
    """Read OOXML without extraction, so hostile archive paths cannot escape."""
    with zipfile.ZipFile(path) as zf:
        bad = zf.testzip()
        if bad:
            raise ValueError(f"corrupt DOCX member: {bad}")
        names = set(zf.namelist())
        document = ET.fromstring(zf.read("word/document.xml"))
        styles = ET.fromstring(zf.read("word/styles.xml"))
        defaults_rpr = styles.find("w:docDefaults/w:rPrDefault/w:rPr", NS)
        defaults_ppr = styles.find("w:docDefaults/w:pPrDefault/w:pPr", NS)
        normal = _normal_style(styles)
        observed = _rpr_values(defaults_rpr)
        observed.update(_rpr_values(normal.find("w:rPr", NS) if normal is not None else None))
        observed.update(_ppr_values(defaults_ppr))
        observed.update(_ppr_values(normal.find("w:pPr", NS) if normal is not None else None))
        sects = document.findall(".//w:sectPr", NS)
        if sects:
            sect = sects[-1]
            margins = sect.find("w:pgMar", NS)
            if margins is not None:
                observed["margin_mm"] = {side: _mm(margins.get(Q(side)))
                                         for side in ("top", "right", "bottom", "left",
                                                      "header", "footer", "gutter")
                                         if margins.get(Q(side)) is not None}
            size = sect.find("w:pgSz", NS)
            if size is not None:
                observed["page_size"] = {"width_mm": _mm(size.get(Q("w"))),
                                         "height_mm": _mm(size.get(Q("h"))),
                                         "orientation": size.get(Q("orient")) or "portrait"}
            cols = sect.find("w:cols", NS)
            if cols is not None:
                observed["columns"] = int(cols.get(Q("num")) or 1)
            else:
                observed["columns"] = 1
        paragraphs = []
        for p in document.findall(".//w:body//w:p", NS):
            pstyle = p.find("w:pPr/w:pStyle", NS)
            paragraphs.append({"text": _text_of(p),
                               "style": pstyle.get(Q("val")) if pstyle is not None else None,
                               "has_figure": bool(p.findall(".//w:drawing", NS)
                                                  or p.findall(".//w:pict", NS))})
        headings = [{"text": p["text"], "style": p["style"]} for p in paragraphs
                    if p["style"] and re.search(r"heading|标题", p["style"], re.I)]
        heading_ids = [st.get(Q("styleId")) for st in styles.findall("w:style", NS)]
        observed["heading_levels"] = max([int(m.group(1)) for sid in heading_ids if sid
                                          for m in [re.match(r"Heading(\d+)$", sid)] if m] or [0])
        full_text = "\n".join(p["text"] for p in paragraphs)
        units = {
            "figures": len(document.findall(".//w:drawing", NS)) + len(document.findall(".//w:pict", NS)),
            "tables": len(document.findall(".//w:tbl", NS)),
            "equations": len(document.findall(".//m:oMath", NS)),
            "revisions": len(document.findall(".//w:ins", NS)) + len(document.findall(".//w:del", NS)),
            "fields": len(document.findall(".//w:fldSimple", NS)) + len(document.findall(".//w:instrText", NS)),
            "section_breaks": len(sects), "embedded": len(document.findall(".//w:object", NS)),
            "footnotes": 0, "comments": 0,
        }
        if "word/footnotes.xml" in names:
            foot = ET.fromstring(zf.read("word/footnotes.xml"))
            units["footnotes"] = sum(1 for f in foot.findall("w:footnote", NS)
                                     if _float(f.get(Q("id"))) is None or _float(f.get(Q("id"))) > 0)
        if "word/comments.xml" in names:
            units["comments"] = len(ET.fromstring(zf.read("word/comments.xml")).findall("w:comment", NS))
        header_footer_text = []
        # TOC lives in the body; PAGE normally lives in footer parts. Read both.
        instructions = [(x.text or "") for x in document.findall(".//w:instrText", NS)]
        embedded_fonts = False
        for name in sorted(names):
            if re.fullmatch(r"word/(?:header|footer)\d*\.xml", name):
                root = ET.fromstring(zf.read(name))
                header_footer_text.append(_text_of(root))
                instructions.extend((x.text or "") for x in root.findall(".//w:instrText", NS))
            if name == "word/fontTable.xml":
                root = ET.fromstring(zf.read(name))
                embedded_fonts = any(x.tag in {Q("embedRegular"), Q("embedBold"), Q("embedItalic"),
                                                Q("embedBoldItalic")} for x in root.iter())
        # Caption positions are measured relative to actual figure paragraphs/tables.
        body = document.find("w:body", NS)
        caption_events = []
        if body is not None:
            children = list(body)
            for i, el in enumerate(children):
                is_fig = bool(el.findall(".//w:drawing", NS) or el.findall(".//w:pict", NS))
                is_table = el.tag == Q("tbl")
                if not (is_fig or is_table):
                    continue
                neighbours = []
                for j in (i - 1, i + 1):
                    if 0 <= j < len(children) and children[j].tag == Q("p"):
                        txt = _text_of(children[j]).strip()
                        if re.match(r"^(?:fig(?:ure)?\.?|图|table|表)\s*\d+", txt, re.I):
                            neighbours.append("above" if j < i else "below")
                caption_events.append({"kind": "table" if is_table else "figure",
                                       "positions": neighbours})
        return {"path": str(path), "observed": observed, "paragraphs": paragraphs,
                "headings": headings, "text": full_text, "units": units,
                "header_footer_text": "\n".join(header_footer_text),
                "instructions": instructions, "font_embedded": embedded_fonts,
                "caption_events": caption_events, "valid_zip": True, "format": "docx"}


def template_requirements(path: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    """Extract requirements from the actual template, plus source evidence."""
    suffix = path.suffix.lower()
    if suffix == ".docx":
        info = inspect_docx(path)
        req = {k: copy.deepcopy(v) for k, v in info["observed"].items()
               if k in {"margin_mm", "page_size", "font", "size_pt", "line_spacing",
                        "columns", "heading_levels"} and v not in (None, "", {}, 0)}
        return req, {"kind": "docx_ooxml", "path": str(path), "sha256": _sha(path),
                     "sections": info["paragraphs"][:20]}
    text = path.read_text(encoding="utf-8-sig")
    if suffix == ".json":
        payload = json.loads(text)
        if not isinstance(payload, dict):
            raise ValueError("template JSON must be an object")
        tmpl = payload.get("template") if isinstance(payload.get("template"), dict) else payload
        req = tmpl.get("spec") if isinstance(tmpl.get("spec"), dict) else tmpl
        return copy.deepcopy(req), {"kind": "json_declarations", "path": str(path), "sha256": _sha(path)}
    if suffix not in {".tex", ".sty", ".cls", ".txt"}:
        raise ValueError(f"unsupported template format: {suffix}")
    req: dict[str, Any] = {}
    class_match = re.search(r"\\documentclass(?:\[([^\]]+)\])?", text)
    if class_match:
        options = [x.strip() for x in (class_match.group(1) or "").split(",")]
        size = next((x for x in options if re.fullmatch(r"\d+(?:\.\d+)?pt", x)), None)
        if size:
            req["size_pt"] = float(size[:-2])
        if "twocolumn" in options:
            req["columns"] = 2
        elif "onecolumn" in options:
            req["columns"] = 1
    geometry = re.search(r"\\usepackage(?:\[([^\]]+)\])?\{geometry\}", text)
    if geometry and geometry.group(1):
        opts = geometry.group(1)
        margin = re.search(r"(?:^|,)\s*margin\s*=\s*([\d.]+)\s*(mm|cm|in)", opts)
        if margin:
            value = float(margin.group(1)) * {"mm": 1, "cm": 10, "in": 25.4}[margin.group(2)]
            req["margin_mm"] = round(value, 3)
        else:
            sides = {}
            for side in ("top", "right", "bottom", "left"):
                m = re.search(rf"(?:^|,)\s*{side}\s*=\s*([\d.]+)\s*(mm|cm|in)", opts)
                if m:
                    sides[side] = round(float(m.group(1)) * {"mm": 1, "cm": 10, "in": 25.4}[m.group(2)], 3)
            if sides:
                req["margin_mm"] = sides
    font = re.search(r"\\setmainfont(?:\[[^\]]*\])?\{([^}]+)\}", text)
    if font:
        req["font"] = font.group(1).strip()
    stretch = re.search(r"\\setstretch\{([\d.]+)\}", text)
    if stretch:
        req["line_spacing"] = float(stretch.group(1))
    bib = re.search(r"\\bibliographystyle\{([^}]+)\}", text)
    if bib:
        req["reference_style"] = bib.group(1).strip()
    if re.search(r"\\begin\{abstract\}", text):
        req["required_sections"] = ["abstract"]
    return req, {"kind": "tex_source", "path": str(path), "sha256": _sha(path)}


def _set_style_values(styles: ET.Element, style_id: str, font: Any, size: Any,
                      spacing: Any, changes: list[dict]) -> None:
    st = _style(styles, style_id)
    if st is None:
        st = ET.SubElement(styles, Q("style"), {Q("type"): "paragraph", Q("styleId"): style_id})
        name = ET.SubElement(st, Q("name")); name.set(Q("val"), style_id)
        if style_id.startswith("Heading"):
            level = int(style_id[7:] or 1)
            ppr = ET.SubElement(st, Q("pPr")); outline = ET.SubElement(ppr, Q("outlineLvl"))
            outline.set(Q("val"), str(level - 1))
            ET.SubElement(st, Q("qFormat"))
    rpr = _child(st, "rPr")
    if font not in (None, ""):
        fonts = _child(rpr, "rFonts")
        for attr in ("ascii", "hAnsi", "eastAsia", "cs"):
            fonts.set(Q(attr), str(font))
        changes.append({"target": style_id, "property": "font", "value": font})
    if _float(size) is not None:
        for tag in ("sz", "szCs"):
            _child(rpr, tag).set(Q("val"), str(int(round(float(size) * 2))))
        changes.append({"target": style_id, "property": "size_pt", "value": size})
    if _float(spacing) is not None:
        ppr = _child(st, "pPr"); sp = _child(ppr, "spacing")
        sp.set(Q("line"), str(int(round(float(spacing) * 240)))); sp.set(Q("lineRule"), "auto")
        changes.append({"target": style_id, "property": "line_spacing", "value": spacing})


def apply_docx(source: Path, output: Path, requirements: dict[str, Any],
               headings: Any) -> tuple[dict[str, Any], list[dict]]:
    """Apply only structural/style fields; never rewrite science or remove XML parts."""
    if source.resolve() == output.resolve():
        raise ValueError("output_file must differ from source_file; source is never overwritten")
    with zipfile.ZipFile(source) as zin:
        infos = zin.infolist()
        blobs = {info.filename: zin.read(info.filename) for info in infos}
    document = ET.fromstring(blobs["word/document.xml"])
    styles = ET.fromstring(blobs["word/styles.xml"])
    changes: list[dict] = []
    sects = document.findall(".//w:sectPr", NS)
    if not sects:
        body = document.find("w:body", NS)
        if body is None:
            raise ValueError("DOCX has no document body")
        sects = [ET.SubElement(body, Q("sectPr"))]
    margin_req = requirements.get("margin_mm")
    if margin_req not in (None, ""):
        for sect in sects:
            margins = _child(sect, "pgMar")
            values = margin_req if isinstance(margin_req, dict) else {
                k: margin_req for k in ("top", "right", "bottom", "left")}
            for side, value in values.items():
                twips = _twips(value)
                if twips is not None and side in {"top", "right", "bottom", "left", "header", "footer", "gutter"}:
                    margins.set(Q(side), twips)
        changes.append({"target": "all sections", "property": "margin_mm", "value": margin_req})
    page = requirements.get("page_size")
    if isinstance(page, dict):
        for sect in sects:
            size = _child(sect, "pgSz")
            for key, attr in (("width_mm", "w"), ("height_mm", "h")):
                twips = _twips(page.get(key))
                if twips:
                    size.set(Q(attr), twips)
            if page.get("orientation"):
                size.set(Q("orient"), str(page["orientation"]))
        changes.append({"target": "all sections", "property": "page_size", "value": page})
    if _float(requirements.get("columns")) is not None:
        for sect in sects:
            _child(sect, "cols").set(Q("num"), str(int(float(requirements["columns"]))))
        changes.append({"target": "all sections", "property": "columns", "value": requirements["columns"]})
    font, size = requirements.get("font"), requirements.get("size_pt")
    spacing = requirements.get("line_spacing")
    defaults_rpr = styles.find("w:docDefaults/w:rPrDefault/w:rPr", NS)
    if defaults_rpr is None:
        defaults = styles.find("w:docDefaults", NS)
        if defaults is None:
            defaults = ET.Element(Q("docDefaults")); styles.insert(0, defaults)
        rdefault = _child(defaults, "rPrDefault"); defaults_rpr = _child(rdefault, "rPr")
    if font not in (None, ""):
        fonts = _child(defaults_rpr, "rFonts")
        for attr in ("ascii", "hAnsi", "eastAsia", "cs"):
            fonts.set(Q(attr), str(font))
    _set_style_values(styles, "Normal", font, size, spacing, changes)
    for level in range(1, max(1, int(_float(requirements.get("heading_levels")) or 3)) + 1):
        _set_style_values(styles, f"Heading{level}", font, None, spacing, changes)
    _set_style_values(styles, "Caption", font, None, spacing, changes)
    if isinstance(headings, dict):
        headings = [headings]
    if not isinstance(headings, (list, tuple)):
        headings = []
    for h in headings:
        if not isinstance(h, dict) or not str(h.get("text") or "").strip():
            continue
        level = int(_float(h.get("level")) or 1)
        wanted = str(h["text"]).strip()
        matched = False
        for p in document.findall(".//w:body//w:p", NS):
            if _text_of(p).strip() == wanted:
                ppr = p.find("w:pPr", NS)
                if ppr is None:
                    ppr = ET.Element(Q("pPr")); p.insert(0, ppr)
                pstyle = _child(ppr, "pStyle"); pstyle.set(Q("val"), f"Heading{level}")
                matched = True
        if not matched:
            raise ValueError(f"heading to bind was not found exactly: {wanted[:80]}")
        changes.append({"target": wanted[:80], "property": "paragraph_style",
                        "value": f"Heading{level}"})
    blobs["word/document.xml"] = ET.tostring(document, encoding="utf-8", xml_declaration=True)
    blobs["word/styles.xml"] = ET.tostring(styles, encoding="utf-8", xml_declaration=True)
    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as zout:
        for info in infos:
            # Preserve member names and timestamps, but never preserve symlink entries.
            if (info.external_attr >> 16) & 0o120000 == 0o120000:
                raise ValueError(f"symlink in DOCX is refused: {info.filename}")
            zout.writestr(info, blobs[info.filename])
    return {"path": str(output), "format": "docx", "editable": True}, changes


def _same(expected: Any, observed: Any) -> bool:
    if isinstance(expected, dict):
        if not isinstance(observed, dict):
            return False
        return all(_same(v, observed.get(k)) for k, v in expected.items())
    if isinstance(expected, (int, float)) and not isinstance(expected, bool):
        got = _float(observed)
        return got is not None and abs(float(expected) - got) < 0.011
    if isinstance(expected, str):
        return str(observed or "").strip().lower() == expected.strip().lower()
    return expected == observed


def contract_names(raw: Any) -> list[str]:
    if isinstance(raw, dict):
        wrappers = {"fields", "required", "lists", "optional"}
        if raw and set(raw).issubset(wrappers):
            out = []
            for value in raw.values():
                for name in contract_names(value):
                    if name not in out:
                        out.append(name)
            return out
        return [str(k) for k in raw]
    out = []
    if isinstance(raw, (list, tuple)):
        for e in raw:
            name = e if isinstance(e, str) else str(e.get("name") or e.get("field") or e.get("key") or "") if isinstance(e, dict) else ""
            if name and name not in out:
                out.append(name)
    return out


def echo_contract(spec: dict, result: dict) -> None:
    fields = contract_names(spec.get("output_contract"))
    for field in fields:
        if field in DERIVED and field in result:
            if result[field] is None and not any(field in str(note) for note in result.setdefault("limits", [])):
                result["limits"].append(f"output_contract field '{field}' is null because the engine could not derive it")
            continue
        if field in spec and field != "output_contract" and spec[field] is not None:
            result[field] = copy.deepcopy(spec[field])
        else:
            result[field] = None
            result.setdefault("limits", []).append(
                f"output_contract field '{field}' was not derivable; left null")
    if fields:
        result["output_contract_fields"] = fields


def _status(findings: list[dict]) -> tuple[str, dict]:
    counts = {}
    for f in findings:
        counts[f["severity"]] = counts.get(f["severity"], 0) + 1
    return ("blocked" if counts.get("high") else "review" if findings else "clean"), counts


def _write(out: Path, result: dict) -> None:
    out.mkdir(parents=True, exist_ok=True)
    (out / "result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n",
                                     encoding="utf-8")


def _resolve(raw: Any, roots: list[Path]) -> Path | None:
    if not isinstance(raw, (str, Path)) or not str(raw).strip():
        return None
    p = Path(raw)
    if p.is_absolute() and p.exists():
        return p
    for root in roots:
        candidate = root / str(raw)
        if candidate.exists():
            return candidate
    return p if p.is_absolute() else roots[0] / p


def build(spec: dict, out: Path, case_path: Path | None = None,
          input_root: Path | None = None) -> dict:
    roots = [p for p in (case_path.parent if case_path else None, input_root, Path.cwd()) if p]
    source = _resolve(spec.get("source_file") or spec.get("source"), roots)
    template_path = _resolve(spec.get("template_file"), roots)
    if source is None or not source.is_file():
        raise ValueError("source_file is missing or unreadable")
    if source.suffix.lower() != ".docx":
        raise ValueError("primary file-level apply currently requires a .docx source; TeX can be "
                         "template evidence but is not silently converted")
    before = inspect_docx(source)
    extracted, template_source = ({}, {"kind": "case_spec_only"})
    if template_path is not None and template_path.is_file():
        extracted, template_source = template_requirements(template_path)
    tmpl = spec.get("template") if isinstance(spec.get("template"), dict) else {}
    explicit = tmpl.get("spec") if isinstance(tmpl.get("spec"), dict) else {}
    requirements = dict(extracted)
    requirements.update(copy.deepcopy(explicit))  # explicit case rules override observed defaults
    provenance = {k: template_source["kind"] for k in extracted}
    provenance.update({k: "case_or_task_explicit_spec" for k in explicit})
    output_raw = spec.get("output_file")
    output = _resolve(output_raw, roots) if output_raw else out / "adapted.docx"
    if spec.get("apply"):
        if template_path is None and not explicit:
            raise ValueError("no actual template or explicit format requirements were supplied")
        deliverable, changes = apply_docx(source, output, requirements, spec.get("headings"))
    else:
        if output is None or not output.is_file():
            raise ValueError("output_file is required when apply is not true")
        changes = []
        deliverable = {"path": str(output), "format": output.suffix.lower().lstrip("."),
                       "editable": output.suffix.lower() == ".docx"}
    after = inspect_docx(output)
    findings: list[dict] = []
    compliance: list[dict] = []

    def record(field: str, status: str, required: Any, observed: Any, evidence: str,
               rule: str | None = None, message: str = "") -> None:
        compliance.append({"field": field, "required": required, "observed": observed,
                           "status": status, "evidence": evidence})
        if status == "fail":
            _add(findings, rule or "fit.requirement_mismatch", "high",
                 message or f"the delivered file does not meet the declared {field} requirement",
                 field=field, required=required, observed=observed)
        elif status == "unverified":
            _add(findings, "fit.check_unverified", "medium",
                 message or f"{field} cannot be verified by this OOXML/source audit", field=field)

    for field in CONTROLLED:
        if field not in requirements or requirements[field] in (None, "", {}, []):
            continue
        expected = requirements[field]
        if field == "caption_position":
            positions = [p for e in after["caption_events"] for p in e["positions"]]
            if not positions:
                record(field, "unverified", expected, positions,
                       "no figure/table caption pair could be resolved structurally")
            elif all(p == str(expected).lower() for p in positions):
                record(field, "pass", expected, positions, "caption paragraphs adjacent to actual objects")
            else:
                record(field, "fail", expected, positions, "OOXML caption/object adjacency",
                       "fit.caption_position_mismatch")
        elif field == "reference_style":
            # OOXML content does not prove APA/Vancouver field ordering or punctuation.
            record(field, "unverified", expected, None,
                   "DOCX text cannot by itself prove bibliography style semantics")
        elif field == "header_footer":
            required_hf = expected if isinstance(expected, dict) else {"header_footer": expected}
            observed_hf = after["header_footer_text"]
            missing = [str(v) for v in required_hf.values()
                       if str(v).strip().lower() not in {"not set", "none", ""}
                       and str(v).strip().lower() not in observed_hf.lower()]
            record(field, "fail" if missing else "pass", expected, observed_hf,
                   "header/footer XML text", "fit.header_footer_mismatch" if missing else None)
        elif field == "page_numbers":
            has_page = any(re.search(r"\bPAGE\b", x, re.I) for x in after["instructions"])
            record(field, "pass" if (not expected or has_page) else "fail", expected, has_page,
                   "PAGE field instruction in footer XML", "fit.page_numbers_missing")
        elif field == "toc_expected":
            has_toc = any(re.search(r"\bTOC\b", x, re.I) for x in after["instructions"])
            record(field, "pass" if (not expected or has_toc) else "fail", expected, has_toc,
                   "TOC field instruction in document XML", "fit.toc_missing")
        else:
            observed = after["observed"].get(field)
            if field == "export_format":
                observed = output.suffix.lower().lstrip(".")
                ok = str(expected).lower().lstrip(".") == observed
            elif field == "margin_mm" and not isinstance(expected, dict) and isinstance(observed, dict):
                ok = all(_same(expected, observed.get(side)) for side in ("top", "right", "bottom", "left"))
            else:
                ok = _same(expected, observed)
            rule = {"margin_mm": "fit.margin_mismatch", "font": "fit.font_mismatch",
                    "size_pt": "fit.size_mismatch", "line_spacing": "fit.spacing_mismatch",
                    "columns": "fit.columns_mismatch", "heading_levels": "fit.heading_style_mismatch",
                    "export_format": "fit.export_format_mismatch"}.get(field)
            record(field, "pass" if ok else "fail", expected, observed,
                   "actual output OOXML styles/section properties", rule)

    required_sections = tmpl.get("sections") or requirements.get("required_sections") or []
    if isinstance(required_sections, str):
        required_sections = [required_sections]
    if isinstance(required_sections, (list, tuple)):
        flat = re.sub(r"\s+", " ", after["text"]).lower()
        for section in required_sections:
            label = re.sub(r"[_-]+", " ", str(section)).strip().lower()
            present = label in flat
            compliance.append({"field": "required_section", "required": str(section),
                               "observed": present, "status": "pass" if present else "fail",
                               "evidence": "delivered document text"})
            if not present:
                _add(findings, "fit.required_text_missing", "high",
                     "a section/declaration required by the template is absent from the delivered text",
                     section=str(section))
    declarations = tmpl.get("declarations")
    if isinstance(declarations, dict):
        declarations = list(declarations)
    if isinstance(declarations, (list, tuple)):
        for declaration in declarations:
            label = re.sub(r"[_-]+", " ", str(declaration)).strip().lower()
            if label and label not in after["text"].lower():
                _add(findings, "fit.required_text_missing", "high",
                     "a required declaration is absent", declaration=str(declaration))

    text_equal = before["text"] == after["text"]
    if not text_equal:
        _add(findings, "fit.content_changed", "high",
             "document text changed during a format-only adaptation; restore the original content")
    unit_rows = []
    for kind in UNIT_KINDS:
        b, a = before["units"].get(kind, 0), after["units"].get(kind, 0)
        unit_rows.append({"kind": kind, "before": b, "after": a, "preserved": a == b})
        if a < b:
            _add(findings, "fit.unit_lost", "high", "a content unit was lost during adaptation",
                 kind=kind, before=b, after=a)
        elif a > b:
            _add(findings, "fit.unit_added", "medium", "a content unit appeared during adaptation",
                 kind=kind, before=b, after=a)
    status, counts = _status(findings)
    cid = spec.get("case_id")
    cid = str(cid) if cid is not None else None
    source_rows = [{"kind": "source_manuscript", "path": str(source), "sha256": _sha(source)},
                   template_source, {"kind": "delivered_manuscript", "path": str(output),
                                     "sha256": _sha(output)}]
    limits = list(spec.get("limits") if isinstance(spec.get("limits"), list) else [])
    limits.extend([
        "OOXML verification is structural, not visual inspection; render and inspect previews separately",
        "pagination, line breaking, font substitution and visual fidelity are not measured by this script",
        "reference-style semantics require a dedicated style processor or human check; never inferred from appearance",
    ])
    if requirements.get("font") and not after["font_embedded"]:
        limits.append("required font is not recorded as embedded in fontTable.xml; no embedding was claimed")
    result = {
        "schema_version": "formatfit/v1", "case_id": cid, "status": status,
        "findings": findings, "severity_counts": counts,
        "checked": {"requirements": len(compliance), "content_units": len(unit_rows),
                    "source_paragraphs": len(before["paragraphs"]),
                    "output_paragraphs": len(after["paragraphs"])},
        "limits": limits,
        "deliverable": deliverable, "revised_manuscript": deliverable,
        "template_requirements": {"values": requirements, "provenance": provenance},
        "compliance": compliance, "applied_changes": changes, "change_log": changes,
        "content_preservation": {"text_identical": text_equal, "units": unit_rows,
                                 "all_units_preserved": all(x["preserved"] for x in unit_rows)},
        "sources": source_rows,
        "export_record": {"format": deliverable["format"], "zip_opened": after["valid_zip"],
                          "editable_ooxml": True, "page_properties_measured": True,
                          "font_embedded_observed": after["font_embedded"],
                          "visual_inspection": "not_performed"},
        "rendering": {"visual_inspection": "not_performed", "pdf_or_png_rendered": False,
                      "font_embedding_verified": False, "pagination_verified": False},
    }
    echo_contract(spec, result)
    _write(out, result)
    (out / "compliance.json").write_text(json.dumps(compliance, ensure_ascii=False, indent=2) + "\n",
                                         encoding="utf-8")
    return result


def load_spec(spec_path: Path, case_path: Path | None) -> dict:
    raw = json.loads(spec_path.read_text(encoding="utf-8-sig"))
    if not isinstance(raw, dict):
        raise ValueError("spec must be a JSON object")
    if case_path is None:
        return raw
    case = json.loads(case_path.read_text(encoding="utf-8-sig"))
    if not isinstance(case, dict):
        raise ValueError("case must be a JSON object")
    merged = dict(case); merged.update(raw)
    if "case_id" not in raw:
        for key in ("case_id", "id", "caseId"):
            if case.get(key) is not None:
                merged["case_id"] = case[key]; break
    materials = case.get("materials") if isinstance(case.get("materials"), dict) else {}
    if "source_file" not in merged:
        for key in ("manuscript", "source", "source_file", "input_docx", "draft_file"):
            if materials.get(key):
                merged["source_file"] = materials[key]; break
    if "template_file" not in merged:
        for key in ("template", "template_file", "journal_template", "style_file"):
            if isinstance(materials.get(key), (str, Path)):
                merged["template_file"] = materials[key]; break
    return merged


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--spec", required=True); ap.add_argument("--case")
    ap.add_argument("--input-root"); ap.add_argument("--out", required=True)
    args = ap.parse_args(argv)
    out = Path(args.out); spec = {}
    try:
        case_path = Path(args.case) if args.case else None
        spec = load_spec(Path(args.spec), case_path)
        result = build(spec, out, case_path, Path(args.input_root) if args.input_root else None)
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError, zipfile.BadZipFile, ET.ParseError) as exc:
        message = f"format adaptation could not run: {exc}"
        result = {"schema_version": "formatfit/v1", "case_id": spec.get("case_id"),
                  "status": "undetermined", "findings": [{"rule": "fit.input_unreadable",
                  "severity": "high", "message": message}], "severity_counts": {"high": 1},
                  "checked": {}, "limits": [message], "deliverable": None,
                  "compliance": [], "rendering": {"visual_inspection": "not_performed"}}
        echo_contract(spec, result); _write(out, result)
    except Exception as exc:
        message = f"format adaptation failed at the structured boundary: {type(exc).__name__}: {exc}"
        result = {"schema_version": "formatfit/v1", "case_id": spec.get("case_id"),
                  "status": "undetermined", "findings": [{"rule": "fit.processing_error",
                  "severity": "high", "message": message}], "severity_counts": {"high": 1},
                  "checked": {}, "limits": [message], "deliverable": None,
                  "compliance": [], "rendering": {"visual_inspection": "not_performed"}}
        echo_contract(spec, result); _write(out, result)
    print(json.dumps({"status": result.get("status"), "case_id": result.get("case_id"),
                      "findings": [f.get("rule") for f in result.get("findings", [])],
                      "wrote": str(out / "result.json")}, ensure_ascii=False))
    return EXIT.get(str(result.get("status")), 5)


if __name__ == "__main__":
    raise SystemExit(main())
