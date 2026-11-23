"""Read the template that was declared, instead of trusting the declaration.

Until this module existed the template's constraints were *declarative*: the
spec said which layouts and typefaces the template provides, and the engine
checked the deck against that statement. A wrong statement — a layout spelled
the way the author remembers it rather than the way the template names it, a
theme font from the previous template — silently re-based every rule that
consumed it. The rubric's first question, "指定模板是否被真实套用（母版、版式、
占位符继承关系可查）", cannot be answered from a declaration.

A .potx (or a .pptx used as a template) is an OPC package: `zipfile` opens it
and `xml.etree` parses the parts. From those parts this module measures:

  presentation.xml   slide size (EMU)                       -> template.slide_size_mismatch
  slideLayouts/*.xml  the layouts the template actually provides, by the names
                      it actually gives them (cSld name / type attribute)
                      -> template.layout_not_found
  each layout's      title placeholder geometry and declared run size
  title placeholder  -> template.title_geometry_drift, template.title_size_off
  theme/theme1.xml   major/minor latin + east-asian typefaces
                     -> template.theme_font_mismatch
  slideMasters       which master each layout belongs to

Everything is measured, and everything is optional: a spec that names no
template file turns every consumer off (declarative behaviour is unchanged),
and a template that cannot be read is reported as `template.unreadable` rather
than guessed at. Pure standard library; no python-pptx at run time.
"""

from __future__ import annotations

import posixpath
import re
import zipfile
import xml.etree.ElementTree as ET

NS = {
    "a": "http://schemas.openxmlformats.org/drawingml/2006/main",
    "p": "http://schemas.openxmlformats.org/presentationml/2006/main",
    "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
    "ct": "http://schemas.openxmlformats.org/package/2006/content-types",
    "rel": "http://schemas.openxmlformats.org/package/2006/relationships",
}

TEMPLATE_CONTENT_TYPES = (
    "application/vnd.openxmlformats-officedocument.presentationml.template.main+xml",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation.main+xml",
)

TITLE_PH_TYPES = {"title", "ctrtitle"}
BODY_PH_TYPES = {"body", "subtitles"}

# A title box counts as "at the template position" within this slop. The
# generator rounds to whole EMUs and templates differ by a hair across
# versions; 0.35 in (320040 EMU, the drift the bench injects) sits far
# outside this, honest variation sits far inside it.
GEOM_TOL_EMU = 114300   # 0.125 in


def _rel_targets(z: zipfile.ZipFile, part_name: str, rel_type_suffix: str) -> list[str]:
    rels_name = posixpath.join(posixpath.dirname(part_name), "_rels",
                               posixpath.basename(part_name) + ".rels").replace("\\", "/")
    if rels_name not in z.namelist():
        return []
    out = []
    for rel in ET.fromstring(z.read(rels_name)):
        if (rel.get("Type") or "").endswith("relationships/" + rel_type_suffix):
            out.append(rel.get("Target") or "")
    return out


def _resolve(base: str, target: str) -> str:
    return posixpath.normpath(posixpath.join(base, target)).replace("\\", "/")


def _shape_ph(sp) -> str | None:
    nv = sp.find(".//p:nvSpPr/p:nvPr/p:ph", NS)
    if nv is None:
        return None
    t = nv.get("type") or "body"
    return t.lower()


def _xfrm_of(sp) -> dict | None:
    xfrm = sp.find(".//a:xfrm", NS)
    if xfrm is None:
        return None
    off = xfrm.find("a:off", NS)
    ext = xfrm.find("a:ext", NS)
    if off is None or ext is None:
        return None
    try:
        return {"x": int(off.get("x")), "y": int(off.get("y")),
                "cx": int(ext.get("cx")), "cy": int(ext.get("cy"))}
    except (TypeError, ValueError):
        return None


def _first_size(sp) -> float | None:
    """The first explicitly declared run size in a layout placeholder."""
    for rpr in sp.iter(f"{{{NS['a']}}}rPr"):
        if rpr.get("sz"):
            try:
                return int(rpr.get("sz")) / 100.0
            except ValueError:
                return None
    for defrpr in sp.iter(f"{{{NS['a']}}}defRPr"):
        if defrpr.get("sz"):
            try:
                return int(defrpr.get("sz")) / 100.0
            except ValueError:
                return None
    return None


def _read_theme(z: zipfile.ZipFile, master_part: str) -> dict:
    """major/minor latin + ea typefaces from the theme behind one master."""
    fonts: dict[str, str] = {}
    theme_targets = _rel_targets(z, master_part, "theme")
    for target in theme_targets[:1]:
        part = _resolve(posixpath.dirname(master_part), target)
        if part not in z.namelist():
            continue
        try:
            root = ET.fromstring(z.read(part))
        except ET.ParseError:
            continue
        for scheme, key in (("a:majorFont", "major"), ("a:minorFont", "minor")):
            node = root.find(f".//a:fontScheme/{scheme}", NS)
            if node is None:
                continue
            for tag, side in (("a:latin", "latin"), ("a:ea", "ea")):
                el = node.find(tag, NS)
                if el is not None and el.get("typeface"):
                    fonts[f"{key}_{side}"] = el.get("typeface")
    return fonts


def _placeholder_defaults(z: zipfile.ZipFile, master_part: str) -> dict:
    """Title/body placeholders on a master, used when a layout omits geometry.

    Real templates often put only ``ph type=title`` on the layout and leave the
    box and type size on the master. Reading just the layout therefore reports
    "no geometry" for a perfectly measurable template. The fallback is scoped
    to a placeholder that is actually present on the layout: a blank layout
    must not acquire a title merely because its master has one.
    """
    out = {"title_ph": None, "title_sz": None, "body_ph": None, "body_sz": None}
    try:
        root = ET.fromstring(z.read(master_part))
    except (KeyError, ET.ParseError):
        return out
    for sp in root.iter(f"{{{NS['p']}}}sp"):
        kind = _shape_ph(sp)
        if kind in TITLE_PH_TYPES and out["title_ph"] is None:
            out["title_ph"] = _xfrm_of(sp)
            out["title_sz"] = _first_size(sp)
        elif kind in BODY_PH_TYPES and out["body_ph"] is None:
            out["body_ph"] = _xfrm_of(sp)
            out["body_sz"] = _first_size(sp)
    return out


def _layout_info(z: zipfile.ZipFile, part: str, master_defaults: dict) -> dict:
    """Read one layout and the relationship that joins it back to its master."""
    root = ET.fromstring(z.read(part))
    c_sld = root.find("p:cSld", NS)
    masters = _rel_targets(z, part, "slideMaster")
    master = (_resolve(posixpath.dirname(part), masters[0]) if masters else "")
    defaults = master_defaults.get(master) or {}
    entry = {
        "name": (c_sld.get("name") or "").strip() if c_sld is not None else "",
        "type": (root.get("type") or "").strip(),
        "master": master,
        "part": part,
        "title_present": False,
        "title_ph": None,
        "title_sz": None,
        "body_present": False,
        "body_ph": None,
        "title_geometry_inherited": False,
        "title_size_inherited": False,
    }
    for sp in root.iter(f"{{{NS['p']}}}sp"):
        kind = _shape_ph(sp)
        if kind in TITLE_PH_TYPES and not entry["title_present"]:
            entry["title_present"] = True
            entry["title_ph"] = _xfrm_of(sp)
            entry["title_sz"] = _first_size(sp)
            if entry["title_ph"] is None and defaults.get("title_ph") is not None:
                entry["title_ph"] = defaults["title_ph"]
                entry["title_geometry_inherited"] = True
            if entry["title_sz"] is None and defaults.get("title_sz") is not None:
                entry["title_sz"] = defaults["title_sz"]
                entry["title_size_inherited"] = True
        elif kind in BODY_PH_TYPES and not entry["body_present"]:
            entry["body_present"] = True
            entry["body_ph"] = _xfrm_of(sp) or defaults.get("body_ph")
    return entry


def read_template(path) -> dict:
    """Measure one template package, including master/layout inheritance.

    Returns ``read=False`` for any malformed XML rather than silently treating a
    parse failure as evidence that a layout or font is absent. Missing optional
    measurements remain structured ``None`` values so the caller can distinguish
    "not measurable" from "does not exist".
    """
    out: dict = {"read": False, "layouts": [], "theme_fonts": {}, "masters": [],
                 "slide_size_emu": None}
    try:
        z = zipfile.ZipFile(path)
    except (OSError, zipfile.BadZipFile) as exc:
        out["reason"] = f"not a readable package: {exc}"
        return out
    try:
        with z:
            names = set(z.namelist())
            pres = "ppt/presentation.xml"
            if pres not in names:
                out["reason"] = "presentation.xml missing — not a presentation package"
                return out
            proot = ET.fromstring(z.read(pres))
            sz = proot.find("p:sldSz", NS)
            if sz is not None:
                try:
                    out["slide_size_emu"] = [int(sz.get("cx")), int(sz.get("cy"))]
                except (TypeError, ValueError):
                    pass

            master_parts = sorted(n for n in names
                                  if re.fullmatch(r"ppt/slideMasters/slideMaster\d+\.xml", n))
            out["masters"] = list(master_parts)
            master_defaults = {mp: _placeholder_defaults(z, mp) for mp in master_parts}
            layout_parts = sorted(n for n in names
                                  if re.fullmatch(r"ppt/slideLayouts/slideLayout\d+\.xml", n))
            for mp in master_parts:
                for k, v in _read_theme(z, mp).items():
                    out["theme_fonts"].setdefault(k, v)
            # Read every layout part, including an orphan whose master back-link is
            # broken. Filtering only through slideMaster relationships would erase
            # precisely the defect that template.layout_master_missing must expose.
            out["layouts"] = [_layout_info(z, part, master_defaults)
                              for part in layout_parts]
            out["read"] = bool(master_parts)
            if not out["read"]:
                out["reason"] = "the package carries no slide master"
    except (zipfile.BadZipFile, ET.ParseError, OSError) as exc:
        out.update({"read": False, "layouts": [], "theme_fonts": {}, "masters": [],
                    "slide_size_emu": None,
                    "reason": f"template XML/package could not be parsed: {exc}"})
        return out
    return out


def norm_layout(s: str) -> str:
    """Lowercase letters/digits only, so 'Title Slide' and 'title_slide' compare."""
    return "".join(c for c in str(s or "").lower() if c.isalnum())


def match_layouts(declared: str, layouts: list[dict]) -> list[dict]:
    """Every measured layout a declared name could denote, best tier first.

    Exact normalised name/type matches win over containment. Keeping all ties is
    important: choosing the first duplicate would turn an ambiguous layout name
    into a confident but arbitrary geometry check.
    """
    want = norm_layout(declared)
    if not want:
        return []
    exact = [lay for lay in layouts
             if norm_layout(lay.get("name")) == want or norm_layout(lay.get("type")) == want]
    if exact:
        return exact
    return [lay for lay in layouts
            if (norm_layout(lay.get("name"))
                and (norm_layout(lay.get("name")) in want or want in norm_layout(lay.get("name"))))
            or (norm_layout(lay.get("type"))
                and (norm_layout(lay.get("type")) in want or want in norm_layout(lay.get("type"))))]


def match_layout(declared: str, layouts: list[dict]) -> dict | None:
    """The first best-tier match, or None when the layout is absent."""
    matches = match_layouts(declared, layouts)
    return matches[0] if matches else None


def geom_close(a: dict | None, b: dict | None, tol: int = GEOM_TOL_EMU) -> bool:
    """Whether two boxes sit at the template position within the tolerance."""
    if not a or not b:
        return False
    return all(abs(a[k] - b[k]) <= tol for k in ("x", "y", "cx", "cy"))
