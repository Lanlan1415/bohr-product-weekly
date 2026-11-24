"""Write a real .pptx with nothing but the standard library.

Why hand-roll OOXML instead of using python-pptx: the pinned evaluation image
lists the tools it provides, and python-pptx is not among them. A skill that
imports it fails on import in that image, and a skill that fails on import
produces no deck at all. `zipfile` and `xml.sax.saxutils` are always there.

The output is a genuine PresentationML package: one master, one layout, one theme,
one slide part per slide. It is deliberately small — no animations, no charts, no
SmartArt — because everything this skill draws is text and one image per slide,
and every unsupported feature would be another way to produce an unopenable file.

Geometry is in EMU (1 inch = 914400 EMU), which is what the format uses and what
the audit needs in order to judge overflow against a real box size.
"""

from __future__ import annotations

import re
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from xml.sax.saxutils import escape

EMU_IN = 914400
SLIDE_W = 12192000                      # exact 16:9 (13.333 in)
SLIDE_H = int(7.5 * EMU_IN)

DEFAULT_FONT_LATIN = "Arial"
DEFAULT_FONT_EA = "Microsoft YaHei"

# Text frame insets used by the layout, in EMU. The audit must use the same
# numbers to compute usable area, so they live here rather than in two places.
INSET_X = int(0.12 * EMU_IN)
INSET_Y = int(0.08 * EMU_IN)


DEFAULT_STYLE = {
    "slide_in": [13.3333333333, 7.5],
    # PptxGenJS uses TRBL margins; keeping that convention makes imported layouts
    # deterministic and avoids silently swapping the footer and title margins.
    "margins_in": [0.35, 0.5, 0.9, 0.5],
    "title_height_in": 1.0,
    "gap_in": 0.15,
    "image_ratio": 0.38,
    "colors": {
        "background": "FFFFFF", "text": "1A1A1A", "title": "1A1A1A",
        "accent": "0072B2", "muted": "5F6B76",
    },
    "footer": {"text": "", "page_numbers": False, "logo": None, "logo_alt": ""},
}


def normalize_style(raw=None, limits: list[str] | None = None) -> dict:
    """Validate one JSON style block and return a complete, independent value.

    Unknown keys are ignored by design; invalid declared measurements/colors are
    replaced by explicit defaults and recorded in limits, never by a traceback.
    """
    limits = limits if limits is not None else []
    if raw is not None and not isinstance(raw, dict):
        limits.append("style was not an object; documented defaults used")
    raw = raw if isinstance(raw, dict) else {}
    out = {k: (dict(v) if isinstance(v, dict) else list(v) if isinstance(v, list) else v)
           for k, v in DEFAULT_STYLE.items()}
    out["colors"] = dict(DEFAULT_STYLE["colors"])
    out["footer"] = dict(DEFAULT_STYLE["footer"])

    for key, default, lo, hi in (("title_height_in", 1.0, 0.5, 2.5),
                                 ("gap_in", 0.15, 0.0, 1.0),
                                 ("image_ratio", 0.38, 0.2, 0.7)):
        try:
            value = float(raw.get(key, default))
            if not lo <= value <= hi:
                raise ValueError(f"outside {lo}..{hi}")
            out[key] = value
        except (TypeError, ValueError) as exc:
            limits.append(f"style.{key} invalid ({exc}); default {default:g} used")
    for key, default in (("slide_in", DEFAULT_STYLE["slide_in"]),
                         ("margins_in", DEFAULT_STYLE["margins_in"])):
        value = raw.get(key, default)
        try:
            vals = [float(x) for x in value]
            wanted = 2 if key == "slide_in" else 4
            if len(vals) != wanted or any(x < 0 for x in vals) or any(x > 30 for x in vals):
                raise ValueError(f"expected {wanted} non-negative inch values")
            if key == "slide_in" and (vals[0] < 6 or vals[1] < 4):
                raise ValueError("canvas is too small for readable slides")
            out[key] = vals
        except (TypeError, ValueError) as exc:
            limits.append(f"style.{key} invalid ({exc}); documented default used")
            out[key] = list(default)
    colors = raw.get("colors") if isinstance(raw.get("colors"), dict) else {}
    for name in out["colors"]:
        value = str(colors.get(name, out["colors"][name]) or "").lstrip("#").upper()
        if not re.fullmatch(r"[0-9A-F]{6}", value):
            limits.append(f"style.colors.{name} was not six-digit RGB; default used")
            value = out["colors"][name]
        out["colors"][name] = value
    footer = raw.get("footer") if isinstance(raw.get("footer"), dict) else {}
    out["footer"] = {
        "text": str(footer.get("text") or ""),
        "page_numbers": bool(footer.get("page_numbers", False)),
        "logo": footer.get("logo"),
        "logo_alt": str(footer.get("logo_alt") or ""),
    }
    return out


@dataclass
class Bullet:
    text: str
    level: int = 0


@dataclass
class Slide:
    title: str
    bullets: list[Bullet] = field(default_factory=list)
    image: str | None = None            # path to a PNG on disk
    image_alt: str = ""
    caption: str = ""
    notes: str = ""
    evidence: str = ""                  # e.g. "Fig. 3b, p.7" — the source locator
    claim: str = ""                     # the one assertion this slide carries
    layout: str = "content"             # "title" | "content"


def image_size(path) -> tuple[int, int] | None:
    """Pixel size of a PNG or JPEG, read from the header with no imaging library.

    Needed so a picture can be fitted to its slot without distortion. Parsing two
    well-specified headers is cheaper than making Pillow a hard dependency of a
    generator whose whole point is to have none.
    """
    PNG_MAGIC = bytes([0x89, 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A])
    JPEG_MAGIC = bytes([0xFF, 0xD8])
    SOF_MARKERS = (0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB)
    try:
        with open(path, "rb") as fh:
            head = fh.read(32)
            if head[:8] == PNG_MAGIC:
                # IHDR is always first: width and height are big-endian at 16..24
                return int.from_bytes(head[16:20], "big"), int.from_bytes(head[20:24], "big")
            if head[:2] == JPEG_MAGIC:
                fh.seek(2)
                while True:
                    marker = fh.read(2)
                    if len(marker) < 2:
                        return None
                    if marker[0] != 0xFF:
                        continue
                    kind = marker[1]
                    if kind in SOF_MARKERS:
                        seg = fh.read(7)
                        if len(seg) < 7:
                            return None
                        height = int.from_bytes(seg[3:5], "big")
                        width = int.from_bytes(seg[5:7], "big")
                        return width, height
                    length = int.from_bytes(fh.read(2), "big")
                    fh.seek(length - 2, 1)
    except OSError:
        return None
    return None



def fit_into(box_w: int, box_h: int, src_w: int, src_h: int) -> tuple[int, int, int, int]:
    """Largest centred rect inside the box with the source aspect -> (x, y, cx, cy)."""
    if not src_w or not src_h:
        return 0, 0, box_w, box_h
    scale = min(box_w / src_w, box_h / src_h)
    cx, cy = int(src_w * scale), int(src_h * scale)
    return (box_w - cx) // 2, (box_h - cy) // 2, cx, cy


def _run(text: str, size_pt: float, bold: bool, font_latin: str, font_ea: str,
         color: str = "1A1A1A") -> str:
    return (
        '<a:r><a:rPr lang="en-US" sz="%d" b="%d" dirty="0">'
        '<a:solidFill><a:srgbClr val="%s"/></a:solidFill>'
        '<a:latin typeface="%s"/><a:ea typeface="%s"/></a:rPr>'
        "<a:t>%s</a:t></a:r>"
        % (int(size_pt * 100), 1 if bold else 0, escape(color),
           escape(font_latin), escape(font_ea), escape(text))
    )


def _para(text: str, size_pt: float, level: int, bold: bool,
          font_latin: str, font_ea: str, bullet: bool = True,
          color: str = "1A1A1A") -> str:
    mar = level * int(0.28 * EMU_IN)
    indent = -int(0.22 * EMU_IN) if bullet else 0
    bu = ('<a:buChar char="•"/>' if bullet else "<a:buNone/>")
    return (
        '<a:p><a:pPr lvl="%d" marL="%d" indent="%d">%s</a:pPr>%s</a:p>'
        % (level, mar, indent, bu,
           _run(text, size_pt, bold, font_latin, font_ea, color))
    )


def _txbox(shape_id: int, name: str, x: int, y: int, cx: int, cy: int, paras: str,
           anchor: str = "t") -> str:
    return (
        '<p:sp xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main" xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
        "<p:nvSpPr><p:cNvPr id=\"%d\" name=\"%s\"/><p:cNvSpPr txBox=\"1\"/><p:nvPr/></p:nvSpPr>"
        '<p:spPr><a:xfrm><a:off x="%d" y="%d"/><a:ext cx="%d" cy="%d"/></a:xfrm>'
        '<a:prstGeom prst="rect"><a:avLst/></a:prstGeom><a:noFill/></p:spPr>'
        '<p:txBody><a:bodyPr wrap="square" lIns="%d" rIns="%d" tIns="%d" bIns="%d" anchor="%s">'
        "<a:normAutofit/></a:bodyPr><a:lstStyle/>%s</p:txBody></p:sp>"
        % (shape_id, escape(name), x, y, cx, cy, INSET_X, INSET_X, INSET_Y, INSET_Y, anchor, paras)
    )


def _pic(shape_id: int, name: str, rel_id: str, x: int, y: int, cx: int, cy: int,
         alt: str) -> str:
    return (
        '<p:pic xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main" xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
        '<p:nvPicPr><p:cNvPr id="%d" name="%s" descr="%s"/><p:cNvPicPr><a:picLocks '
        'noChangeAspect="1"/></p:cNvPicPr><p:nvPr/></p:nvPicPr>'
        '<p:blipFill><a:blip r:embed="%s"/><a:stretch><a:fillRect/></a:stretch></p:blipFill>'
        '<p:spPr><a:xfrm><a:off x="%d" y="%d"/><a:ext cx="%d" cy="%d"/></a:xfrm>'
        '<a:prstGeom prst="rect"><a:avLst/></a:prstGeom></p:spPr></p:pic>'
        % (shape_id, escape(name), escape(alt), rel_id, x, y, cx, cy)
    )


def _slide_number(shape_id: int, number: int, x: int, y: int, cx: int, cy: int,
                  size_pt: float, fonts: tuple[str, str], color: str) -> str:
    """A real dynamic slide-number field, not a hard-coded numeral in a body box."""
    latin, ea = fonts
    return (
        '<p:sp xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main" xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
        '<p:nvSpPr><p:cNvPr id="%d" name="Slide Number"/><p:cNvSpPr/>'
        '<p:nvPr><p:ph type="sldNum" sz="quarter" idx="4294967295"/></p:nvPr></p:nvSpPr>'
        '<p:spPr><a:xfrm><a:off x="%d" y="%d"/><a:ext cx="%d" cy="%d"/></a:xfrm>'
        '<a:prstGeom prst="rect"><a:avLst/></a:prstGeom><a:noFill/></p:spPr>'
        '<p:txBody><a:bodyPr wrap="square" lIns="%d" rIns="%d" tIns="%d" bIns="%d"/>'
        '<a:lstStyle/><a:p><a:pPr algn="r"/>'
        '<a:fld id="{F7021451-1387-4CA6-816F-3879F97B5CBC}" type="slidenum">'
        '<a:rPr lang="en-US" sz="%d" dirty="0"><a:solidFill><a:srgbClr val="%s"/></a:solidFill>'
        '<a:latin typeface="%s"/><a:ea typeface="%s"/></a:rPr><a:t>%d</a:t></a:fld></a:p>'
        '</p:txBody></p:sp>'
        % (shape_id, x, y, cx, cy, INSET_X, INSET_X, INSET_Y, INSET_Y,
           int(size_pt * 100), escape(color), escape(latin), escape(ea), number)
    )


def _slide_xml(slide: Slide, spacing: dict, fonts: tuple[str, str],
               style: dict | None = None, slide_number: int = 1) -> tuple[str, list[tuple[str, str]]]:
    """One slide part and its (relationship-id, image-path) pairs.

    All visible geometry derives from the same TRBL margins. Media is fitted to
    its slot like reveal.js `.stretch`; the footer uses PptxGenJS's slidenum form.
    """
    style = style or normalize_style()
    latin, ea = fonts
    title_sz, body_sz = spacing["title"], spacing["body"]
    colors = style["colors"]
    width, height = (int(round(v * EMU_IN)) for v in style["slide_in"])
    top, right, bottom, left = (int(round(v * EMU_IN)) for v in style["margins_in"])
    title_h, gap = int(style["title_height_in"] * EMU_IN), int(style["gap_in"] * EMU_IN)
    shapes: list[str] = []
    images: list[tuple[str, str]] = []
    sid, next_rel = 2, 2
    footer = style["footer"]
    has_footer = bool(footer.get("text") or footer.get("page_numbers") or footer.get("logo"))
    footer_y = height - int(0.58 * EMU_IN)
    content_bottom = height - bottom
    if has_footer:
        content_bottom = min(content_bottom, footer_y - int(0.12 * EMU_IN))
    caption_text = str(slide.caption or "").strip()
    if slide.evidence and slide.evidence not in caption_text:
        caption_text = f"{slide.evidence} | {caption_text}" if caption_text else str(slide.evidence)

    if slide.layout == "title":
        cover_x = left + int(0.4 * EMU_IN)
        cover_w = width - left - right - int(0.8 * EMU_IN)
        shapes.append(_txbox(sid, "Title", cover_x, int(height * 0.32), cover_w,
                             int(1.5 * EMU_IN),
                             _para(slide.title, title_sz + 8, 0, True, latin, ea,
                                   bullet=False, color=colors["title"]), anchor="b"))
        sid += 1
        if caption_text:
            shapes.append(_txbox(sid, "Subtitle", cover_x, int(height * 0.32) + int(1.65 * EMU_IN),
                                 cover_w, int(1.0 * EMU_IN),
                                 _para(caption_text, body_sz, 0, False, latin, ea,
                                       bullet=False, color=colors["muted"])))
            sid += 1
    else:
        shapes.append(_txbox(sid, "Title", left, top, width - left - right, title_h,
                             _para(slide.title, title_sz, 0, True, latin, ea,
                                   bullet=False, color=colors["title"])))
        sid += 1
        body_x, body_y = left, top + title_h + gap
        body_w = width - left - right
        body_h = max(int(0.5 * EMU_IN), content_bottom - body_y)
        if caption_text and not slide.image:
            # Reserve the caption/source band up front; placing it afterwards over the
            # body box is exactly the silent overlap this generator must prevent.
            body_h = max(int(0.5 * EMU_IN), body_h - int(0.70 * EMU_IN))
        caption_y = None

        if slide.image:
            slot_w = int(body_w * style["image_ratio"])
            media_gap = max(gap, int(0.25 * EMU_IN))
            slot_x = width - right - slot_w
            slot_h = int(body_h * (0.67 if caption_text else 0.86))
            img_x, img_y, img_w, img_h = slot_x, body_y, slot_w, slot_h
            size = image_size(slide.image)
            if size:
                ox, oy, cw, ch = fit_into(slot_w, slot_h, size[0], size[1])
                img_x, img_y, img_w, img_h = slot_x + ox, body_y + oy, cw, ch
            rel_id = f"rId{next_rel}"; next_rel += 1
            shapes.append(_pic(sid, "Figure", rel_id, img_x, img_y, img_w, img_h,
                               slide.image_alt or ""))
            images.append((rel_id, str(slide.image)))
            sid += 1
            body_w = max(int(1.0 * EMU_IN), slot_x - body_x - media_gap)
            if caption_text:
                caption_y = body_y + slot_h + gap
                shapes.append(_txbox(sid, "Caption", slot_x, caption_y, slot_w,
                                     max(int(0.45 * EMU_IN), content_bottom - caption_y),
                                     _para(caption_text, max(14, body_sz - 4), 0, False,
                                           latin, ea, bullet=False, color=colors["muted"])))
                sid += 1

        if slide.bullets:
            paras = "".join(
                _para(b.text, body_sz - 2 * b.level, min(b.level, 3), False, latin, ea,
                      color=colors["text"]) for b in slide.bullets)
            shapes.append(_txbox(sid, "Body", body_x, body_y, body_w, body_h, paras))
            sid += 1
        if caption_text and not slide.image:
            caption_y = content_bottom - int(0.55 * EMU_IN)
            shapes.append(_txbox(sid, "Caption", left, caption_y, body_w,
                                 int(0.55 * EMU_IN),
                                 _para(caption_text, max(14, body_sz - 4), 0, False,
                                       latin, ea, bullet=False, color=colors["muted"])))
            sid += 1

    if has_footer:
        footer_x = left
        if footer.get("logo"):
            logo = str(footer["logo"])
            slot_w, slot_h = int(0.58 * EMU_IN), int(0.34 * EMU_IN)
            logo_x, logo_y, logo_w, logo_h = left, footer_y, slot_w, slot_h
            size = image_size(logo)
            if size:
                ox, oy, cw, ch = fit_into(slot_w, slot_h, size[0], size[1])
                logo_x, logo_y, logo_w, logo_h = left + ox, footer_y + oy, cw, ch
            rel_id = f"rId{next_rel}"; next_rel += 1
            shapes.append(_pic(sid, "Logo", rel_id, logo_x, logo_y, logo_w, logo_h,
                               str(footer.get("logo_alt") or "")))
            images.append((rel_id, logo)); sid += 1
            footer_x += int(0.72 * EMU_IN)
        number_w = int(0.65 * EMU_IN) if footer.get("page_numbers") else 0
        if footer.get("text"):
            shapes.append(_txbox(sid, "Footer", footer_x, footer_y,
                                 max(int(0.5 * EMU_IN), width - right - footer_x - number_w),
                                 int(0.42 * EMU_IN),
                                 _para(str(footer["text"]), max(14, body_sz - 6), 0, False,
                                       latin, ea, bullet=False, color=colors["muted"])))
            sid += 1
        if footer.get("page_numbers"):
            shapes.append(_slide_number(sid, slide_number, width - right - number_w,
                                        footer_y, number_w, int(0.42 * EMU_IN),
                                        max(14, body_sz - 6), fonts, colors["muted"]))
            sid += 1

    xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<p:sld xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" '
        'xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main">'
        '<p:cSld><p:bg><p:bgPr><a:solidFill><a:srgbClr val="%s"/></a:solidFill>'
        '<a:effectLst/></p:bgPr></p:bg><p:spTree>'
        '<p:nvGrpSpPr><p:cNvPr id="1" name=""/><p:cNvGrpSpPr/><p:nvPr/></p:nvGrpSpPr>'
        '<p:grpSpPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="0" cy="0"/>'
        '<a:chOff x="0" y="0"/><a:chExt cx="0" cy="0"/></a:xfrm></p:grpSpPr>'
        % colors["background"]
        + "".join(shapes)
        + "</p:spTree></p:cSld><p:clrMapOvr><a:masterClrMapping/></p:clrMapOvr></p:sld>"
    )
    return xml, images


def _notes_placeholder(text: str, fonts: tuple[str, str]) -> str:
    """A notes slide's text must live in the body placeholder with ph type=body.

    A plain text box renders nothing in the notes pane: python-pptx reports
    notes_text_frame as None and PowerPoint shows an empty note. The placeholder
    identity, not the geometry, is what makes it speaker notes.
    """
    latin, ea = fonts
    body = _para(text, 12, 0, False, latin, ea, bullet=False)
    return (
        '<p:sp><p:nvSpPr><p:cNvPr id="2" name="Notes Placeholder 2"/>'
        '<p:cNvSpPr><a:spLocks noGrp="1"/></p:cNvSpPr>'
        '<p:nvPr><p:ph type="body" idx="1"/></p:nvPr></p:nvSpPr>'
        '<p:spPr><a:xfrm><a:off x="%d" y="0"/><a:ext cx="%d" cy="%d"/></a:xfrm>'
        '<a:prstGeom prst="rect"><a:avLst/></a:prstGeom></p:spPr>'
        '<p:txBody><a:bodyPr lIns="%d" tIns="%d"/><a:lstStyle/>%s</p:txBody></p:sp>'
        % (int(0.6 * EMU_IN), int(6.9 * EMU_IN), int(5.0 * EMU_IN), INSET_X, INSET_Y, body)
    )


def _notes_xml(text: str, fonts: tuple[str, str]) -> str:
    latin, ea = fonts
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<p:notes xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" '
        'xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main">'
        "<p:cSld><p:spTree>"
        '<p:nvGrpSpPr><p:cNvPr id="1" name=""/><p:cNvGrpSpPr/><p:nvPr/></p:nvGrpSpPr>'
        '<p:grpSpPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="0" cy="0"/>'
        '<a:chOff x="0" y="0"/><a:chExt cx="0" cy="0"/></a:xfrm></p:grpSpPr>'
        + _notes_placeholder(text, fonts)
        + "</p:spTree></p:cSld><p:clrMapOvr><a:masterClrMapping/></p:clrMapOvr></p:notes>"
    )


CONTENT_TYPES = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
    '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
    '<Default Extension="xml" ContentType="application/xml"/>'
    '<Default Extension="png" ContentType="image/png"/>'
    '<Default Extension="jpeg" ContentType="image/jpeg"/>'
    '<Default Extension="jpg" ContentType="image/jpeg"/>'
    '<Override PartName="/ppt/presentation.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.presentation.main+xml"/>'
    '<Override PartName="/ppt/slideMasters/slideMaster1.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.slideMaster+xml"/>'
    '<Override PartName="/ppt/slideLayouts/slideLayout1.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.slideLayout+xml"/>'
    '<Override PartName="/ppt/theme/theme1.xml" ContentType="application/vnd.openxmlformats-officedocument.theme+xml"/>'
    '{slides}'
    '{notes}'
    '<Override PartName="/docProps/core.xml" ContentType="application/vnd.openxmlformats-package.core-properties+xml"/>'
    '<Override PartName="/docProps/app.xml" ContentType="application/vnd.openxmlformats-officedocument.extended-properties+xml"/>'
    "</Types>"
)

ROOT_RELS = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
    '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="ppt/presentation.xml"/>'
    '<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" Target="docProps/core.xml"/>'
    '<Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/extended-properties" Target="docProps/app.xml"/>'
    "</Relationships>"
)

MASTER = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    '<p:sldMaster xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" '
    'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" '
    'xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main">'
    "<p:cSld><p:spTree>"
    '<p:nvGrpSpPr><p:cNvPr id="1" name=""/><p:cNvGrpSpPr/><p:nvPr/></p:nvGrpSpPr>'
    '<p:grpSpPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="0" cy="0"/>'
    '<a:chOff x="0" y="0"/><a:chExt cx="0" cy="0"/></a:xfrm></p:grpSpPr>'
    "</p:spTree></p:cSld>"
    '<p:clrMap bg1="lt1" tx1="dk1" bg2="lt2" tx2="dk2" accent1="accent1" '
    'accent2="accent2" accent3="accent3" accent4="accent4" accent5="accent5" '
    'accent6="accent6" hlink="hlink" folHlink="folHlink"/>'
    '<p:sldLayoutIdLst><p:sldLayoutId id="2147483649" r:id="rId1"/></p:sldLayoutIdLst>'
    "</p:sldMaster>"
)

MASTER_RELS = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
    '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slideLayout" Target="../slideLayouts/slideLayout1.xml"/>'
    '<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/theme" Target="../theme/theme1.xml"/>'
    "</Relationships>"
)

LAYOUT = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    '<p:sldLayout xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" '
    'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" '
    'xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main" type="blank" preserve="1">'
    "<p:cSld name=\"Blank\"><p:spTree>"
    '<p:nvGrpSpPr><p:cNvPr id="1" name=""/><p:cNvGrpSpPr/><p:nvPr/></p:nvGrpSpPr>'
    '<p:grpSpPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="0" cy="0"/>'
    '<a:chOff x="0" y="0"/><a:chExt cx="0" cy="0"/></a:xfrm></p:grpSpPr>'
    "</p:spTree></p:cSld>"
    "<p:clrMapOvr><a:masterClrMapping/></p:clrMapOvr></p:sldLayout>"
)

LAYOUT_RELS = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
    '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slideMaster" Target="../slideMasters/slideMaster1.xml"/>'
    "</Relationships>"
)


def _theme(fonts: tuple[str, str], style: dict | None = None) -> str:
    latin, ea = fonts
    colors = (style or normalize_style())["colors"]
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<a:theme xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" name="FigureParse">'
        "<a:themeElements>"
        '<a:clrScheme name="Office">'
        '<a:dk1><a:srgbClr val="%s"/></a:dk1><a:lt1><a:srgbClr val="%s"/></a:lt1>'
        '<a:dk2><a:srgbClr val="%s"/></a:dk2><a:lt2><a:srgbClr val="%s"/></a:lt2>'
        '<a:accent1><a:srgbClr val="%s"/></a:accent1>'
        '<a:accent2><a:srgbClr val="D55E00"/></a:accent2>'
        '<a:accent3><a:srgbClr val="009E73"/></a:accent3>'
        '<a:accent4><a:srgbClr val="E69F00"/></a:accent4>'
        '<a:accent5><a:srgbClr val="CC79A7"/></a:accent5>'
        '<a:accent6><a:srgbClr val="56B4E9"/></a:accent6>'
        '<a:hlink><a:srgbClr val="0072B2"/></a:hlink>'
        '<a:folHlink><a:srgbClr val="CC79A7"/></a:folHlink>'
        "</a:clrScheme>"
        '<a:fontScheme name="FigureParse">'
        '<a:majorFont><a:latin typeface="%s"/><a:ea typeface="%s"/><a:cs typeface=""/></a:majorFont>'
        '<a:minorFont><a:latin typeface="%s"/><a:ea typeface="%s"/><a:cs typeface=""/></a:minorFont>'
        "</a:fontScheme>"
        '<a:fmtScheme name="Office"><a:fillStyleLst><a:solidFill><a:schemeClr val="phClr"/></a:solidFill>'
        '<a:solidFill><a:schemeClr val="phClr"/></a:solidFill>'
        '<a:solidFill><a:schemeClr val="phClr"/></a:solidFill></a:fillStyleLst>'
        "<a:lnStyleLst><a:ln w=\"9525\"><a:solidFill><a:schemeClr val=\"phClr\"/></a:solidFill></a:ln>"
        "<a:ln w=\"25400\"><a:solidFill><a:schemeClr val=\"phClr\"/></a:solidFill></a:ln>"
        "<a:ln w=\"38100\"><a:solidFill><a:schemeClr val=\"phClr\"/></a:solidFill></a:ln></a:lnStyleLst>"
        '<a:effectStyleLst><a:effectStyle><a:effectLst/></a:effectStyle>'
        '<a:effectStyle><a:effectLst/></a:effectStyle>'
        '<a:effectStyle><a:effectLst/></a:effectStyle></a:effectStyleLst>'
        '<a:bgFillStyleLst><a:solidFill><a:schemeClr val="phClr"/></a:solidFill>'
        '<a:solidFill><a:schemeClr val="phClr"/></a:solidFill>'
        '<a:solidFill><a:schemeClr val="phClr"/></a:solidFill></a:bgFillStyleLst>'
        "</a:fmtScheme></a:themeElements></a:theme>"
        % (colors["text"], colors["background"], colors["title"], colors["background"],
           colors["accent"], latin, ea, latin, ea)
    )


def write_deck(slides: list[Slide], out_path, spacing: dict | None = None,
               fonts: tuple[str, str] = (DEFAULT_FONT_LATIN, DEFAULT_FONT_EA),
               style: dict | None = None) -> dict:
    """Write the package. Returns a summary the audit can consume."""
    spacing = spacing or {"title": 32, "body": 20}
    style = style or normalize_style()
    width, height = (int(round(v * EMU_IN)) for v in style["slide_in"])
    out_path = str(out_path)
    slide_ct, notes_ct = [], []
    for i in range(1, len(slides) + 1):
        slide_ct.append(
            '<Override PartName="/ppt/slides/slide%d.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.slide+xml"/>' % i)
        if slides[i - 1].notes:
            notes_ct.append(
                '<Override PartName="/ppt/notesSlides/notesSlide%d.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.notesSlide+xml"/>' % i)

    pres_rels = [
        '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slideMaster" Target="slideMasters/slideMaster1.xml"/>',
        '<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/theme" Target="theme/theme1.xml"/>',
    ]
    sld_ids = []
    for i in range(1, len(slides) + 1):
        rid = "rId%d" % (i + 2)
        pres_rels.append(
            f'<Relationship Id="{rid}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slide" Target="slides/slide{i}.xml"/>')
        sld_ids.append(f'<p:sldId id="{255 + i}" r:id="{rid}"/>')

    presentation = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<p:presentation xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" '
        'xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main" saveSubsetFonts="1">'
        '<p:sldMasterIdLst><p:sldMasterId id="2147483648" r:id="rId1"/></p:sldMasterIdLst>'
        "<p:sldIdLst>" + "".join(sld_ids) + "</p:sldIdLst>"
        f'<p:sldSz cx="{width}" cy="{height}"/><p:notesSz cx="{height}" cy="{width}"/>'
        "</p:presentation>"
    )

    with zipfile.ZipFile(out_path, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml",
                   CONTENT_TYPES.format(slides="".join(slide_ct), notes="".join(notes_ct)))
        z.writestr("_rels/.rels", ROOT_RELS)
        z.writestr("docProps/core.xml",
                   '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                   '<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" '
                   'xmlns:dc="http://purl.org/dc/elements/1.1/">'
                   "<dc:title>Academic deck</dc:title></cp:coreProperties>")
        z.writestr("docProps/app.xml",
                   '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                   '<Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/extended-properties">'
                   "<Application>figure-parse deckgen</Application></Properties>")
        z.writestr("ppt/presentation.xml", presentation)
        z.writestr("ppt/_rels/presentation.xml.rels",
                   '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                   '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                   + "".join(pres_rels) + "</Relationships>")
        z.writestr("ppt/slideMasters/slideMaster1.xml", MASTER)
        z.writestr("ppt/slideMasters/_rels/slideMaster1.xml.rels", MASTER_RELS)
        z.writestr("ppt/slideLayouts/slideLayout1.xml", LAYOUT)
        z.writestr("ppt/slideLayouts/_rels/slideLayout1.xml.rels", LAYOUT_RELS)
        z.writestr("ppt/theme/theme1.xml", _theme(fonts, style))

        for i, slide in enumerate(slides, start=1):
            xml, images = _slide_xml(slide, spacing, fonts, style, i)
            z.writestr(f"ppt/slides/slide{i}.xml", xml)
            rels = ['<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slideLayout" Target="../slideLayouts/slideLayout1.xml"/>']
            for k, (rel_id, img) in enumerate(images):
                ext = str(img).rsplit(".", 1)[-1].lower()
                media = f"image{i}_{k + 1}.{ext}"
                z.write(img, f"ppt/media/{media}")
                rels.append(
                    f'<Relationship Id="{rel_id}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/image" Target="../media/{media}"/>')
            if slide.notes:
                rels.append(
                    f'<Relationship Id="rId{len(rels) + 1}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/notesSlide" Target="../notesSlides/notesSlide{i}.xml"/>')
            z.writestr(f"ppt/slides/_rels/slide{i}.xml.rels",
                       '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                       '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                       + "".join(rels) + "</Relationships>")
            if slide.notes:
                z.writestr(f"ppt/notesSlides/notesSlide{i}.xml", _notes_xml(slide.notes, fonts))
                z.writestr(f"ppt/notesSlides/_rels/notesSlide{i}.xml.rels",
                           '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                           '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                           f'<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slide" Target="../slides/slide{i}.xml"/>'
                           "</Relationships>")

    return {"path": out_path, "slides": len(slides),
            "notes_slides": sum(1 for s in slides if s.notes),
            "spacing": spacing, "fonts": {"latin": fonts[0], "ea": fonts[1]},
            "slide_size_emu": [width, height], "style": style}
