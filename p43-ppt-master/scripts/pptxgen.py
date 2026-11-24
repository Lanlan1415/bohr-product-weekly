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

import zipfile
from dataclasses import dataclass, field
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


def _run(text: str, size_pt: float, bold: bool, font_latin: str, font_ea: str) -> str:
    return (
        '<a:r><a:rPr lang="en-US" sz="%d" b="%d" dirty="0">'
        '<a:solidFill><a:srgbClr val="1A1A1A"/></a:solidFill>'
        '<a:latin typeface="%s"/><a:ea typeface="%s"/></a:rPr>'
        "<a:t>%s</a:t></a:r>"
        % (int(size_pt * 100), 1 if bold else 0, escape(font_latin), escape(font_ea), escape(text))
    )


def _para(text: str, size_pt: float, level: int, bold: bool,
          font_latin: str, font_ea: str, bullet: bool = True) -> str:
    mar = level * int(0.28 * EMU_IN)
    indent = -int(0.22 * EMU_IN) if bullet else 0
    bu = ('<a:buChar char="•"/>' if bullet else "<a:buNone/>")
    return (
        '<a:p><a:pPr lvl="%d" marL="%d" indent="%d">%s</a:pPr>%s</a:p>'
        % (level, mar, indent, bu, _run(text, size_pt, bold, font_latin, font_ea))
    )


def _txbox(shape_id: int, name: str, x: int, y: int, cx: int, cy: int, paras: str,
           anchor: str = "t") -> str:
    return (
        '<p:sp xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main">'
        "<p:nvSpPr><p:cNvPr id=\"%d\" name=\"%s\"/><p:cNvSpPr txBox=\"1\"/><p:nvPr/></p:nvSpPr>"
        '<p:spPr><a:xfrm><a:off x="%d" y="%d"/><a:ext cx="%d" cy="%d"/></a:xfrm>'
        '<a:prstGeom prst="rect"><a:avLst/></a:prstGeom><a:noFill/></p:spPr>'
        '<p:txBody><a:bodyPr wrap="square" lIns="%d" rIns="%d" tIns="%d" bIns="%d" anchor="%s">'
        "<a:noAutofit/></a:bodyPr><a:lstStyle/>%s</p:txBody></p:sp>"
        % (shape_id, escape(name), x, y, cx, cy, INSET_X, INSET_X, INSET_Y, INSET_Y, anchor, paras)
    )


def _pic(shape_id: int, name: str, rel_id: str, x: int, y: int, cx: int, cy: int,
         alt: str) -> str:
    return (
        '<p:pic xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main">'
        '<p:nvPicPr><p:cNvPr id="%d" name="%s" descr="%s"/><p:cNvPicPr><a:picLocks '
        'noChangeAspect="1"/></p:cNvPicPr><p:nvPr/></p:nvPicPr>'
        '<p:blipFill><a:blip r:embed="%s"/><a:stretch><a:fillRect/></a:stretch></p:blipFill>'
        '<p:spPr><a:xfrm><a:off x="%d" y="%d"/><a:ext cx="%d" cy="%d"/></a:xfrm>'
        '<a:prstGeom prst="rect"><a:avLst/></a:prstGeom></p:spPr></p:pic>'
        % (shape_id, escape(name), escape(alt), rel_id, x, y, cx, cy)
    )


def _slide_xml(slide: Slide, spacing: dict, fonts: tuple[str, str]) -> tuple[str, list[str]]:
    """One slide part. Returns the XML and the list of image paths it references."""
    latin, ea = fonts
    title_sz = spacing["title"]
    body_sz = spacing["body"]
    shapes: list[str] = []
    images: list[str] = []
    sid = 2

    # A source locator belongs on the editable page, not only in result.json. Avoid
    # duplicating it when the authored caption already contains the exact locator.
    evidence = slide.evidence.strip()
    evidence_in_caption = bool(evidence and evidence.casefold() in slide.caption.casefold())
    source_line = "" if not evidence or evidence_in_caption else f"Source: {evidence}"
    footer_font = max(body_sz - 4, 12.0)

    if slide.layout == "title":
        shapes.append(_txbox(sid, "Title", int(0.9 * EMU_IN), int(2.4 * EMU_IN),
                             SLIDE_W - int(1.8 * EMU_IN), int(1.5 * EMU_IN),
                             _para(slide.title, title_sz + 8, 0, True, latin, ea, bullet=False),
                             anchor="b"))
        sid += 1
        if slide.caption:
            shapes.append(_txbox(sid, "Subtitle", int(0.9 * EMU_IN), int(4.0 * EMU_IN),
                                 SLIDE_W - int(1.8 * EMU_IN), int(1.0 * EMU_IN),
                                 _para(slide.caption, body_sz, 0, False, latin, ea, bullet=False)))
            sid += 1
        if source_line:
            shapes.append(_txbox(sid, "Source", int(0.5 * EMU_IN), int(6.65 * EMU_IN),
                                 SLIDE_W - int(1.0 * EMU_IN), int(0.6 * EMU_IN),
                                 _para(source_line, footer_font, 0, False, latin, ea,
                                       bullet=False)))
            sid += 1
    else:
        shapes.append(_txbox(sid, "Title", int(0.5 * EMU_IN), int(0.35 * EMU_IN),
                             SLIDE_W - int(1.0 * EMU_IN), int(1.0 * EMU_IN),
                             _para(slide.title, title_sz, 0, True, latin, ea, bullet=False)))
        sid += 1

        footer_lines = []
        if slide.caption and not slide.image:
            footer_lines.append(slide.caption)
        if source_line:
            footer_lines.append(source_line)
        # Reserve geometry before writing the body: two distinct footer lines get
        # two lines of height instead of being squeezed into a one-line strip.
        footer_y = int((6.35 if len(footer_lines) > 1 else 6.65) * EMU_IN)
        footer_h = int((0.85 if len(footer_lines) > 1 else 0.6) * EMU_IN)
        body_x, body_y = int(0.5 * EMU_IN), int(1.5 * EMU_IN)
        body_w = SLIDE_W - int(1.0 * EMU_IN)
        body_bottom = footer_y - int(0.1 * EMU_IN) if footer_lines else SLIDE_H - int(0.9 * EMU_IN)
        body_h = body_bottom - body_y

        if slide.image:
            # Image on the right third, text on the left two thirds.
            img_w = int(4.6 * EMU_IN)
            img_h = int(3.4 * EMU_IN)
            img_x = SLIDE_W - img_w - int(0.5 * EMU_IN)
            # Deliberately no fallback text: substituting "figure" here would make an
            # missing alt text invisible to the audit, and the audit is the only thing
            # that can report it.
            img_y = int(1.5 * EMU_IN)
            size = image_size(slide.image)
            if size:
                # Fit inside the slot and centre it. Stretching to the slot would
                # distort the figure, which the audit reports as a defect.
                ox, oy, cw, ch = fit_into(img_w, img_h, size[0], size[1])
                img_x, img_y, img_w, img_h = img_x + ox, img_y + oy, cw, ch
            shapes.append(_pic(sid, "Figure", "rId2", img_x, img_y, img_w, img_h,
                               slide.image_alt or ""))
            sid += 1
            images.append(slide.image)
            body_w = img_x - body_x - int(0.3 * EMU_IN)
            if slide.caption:
                shapes.append(_txbox(sid, "Caption",
                                     SLIDE_W - int(4.6 * EMU_IN) - int(0.5 * EMU_IN),
                                     int(5.1 * EMU_IN), int(4.6 * EMU_IN), int(0.7 * EMU_IN),
                                     _para(slide.caption, footer_font, 0, False, latin, ea,
                                           bullet=False)))
                sid += 1

        if slide.bullets:
            paras = "".join(
                _para(b.text, body_sz - 2 * b.level, min(b.level, 3), False, latin, ea)
                for b in slide.bullets)
            shapes.append(_txbox(sid, "Body", body_x, body_y, body_w, body_h, paras))
            sid += 1

        if footer_lines:
            # Caption and/or exact source locator must land in the visible deck.
            paras = "".join(_para(line, footer_font, 0, False, latin, ea, bullet=False)
                            for line in footer_lines)
            shapes.append(_txbox(sid, "Source" if source_line else "Caption",
                                 int(0.5 * EMU_IN), footer_y,
                                 SLIDE_W - int(1.0 * EMU_IN), footer_h, paras))
            sid += 1

    xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<p:sld xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" '
        'xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main">'
        "<p:cSld><p:spTree>"
        '<p:nvGrpSpPr><p:cNvPr id="1" name=""/><p:cNvGrpSpPr/><p:nvPr/></p:nvGrpSpPr>'
        '<p:grpSpPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="0" cy="0"/>'
        '<a:chOff x="0" y="0"/><a:chExt cx="0" cy="0"/></a:xfrm></p:grpSpPr>'
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


def _theme(fonts: tuple[str, str]) -> str:
    latin, ea = fonts
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<a:theme xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" name="FigureParse">'
        "<a:themeElements>"
        '<a:clrScheme name="Office">'
        '<a:dk1><a:srgbClr val="1A1A1A"/></a:dk1><a:lt1><a:srgbClr val="FFFFFF"/></a:lt1>'
        '<a:dk2><a:srgbClr val="44546A"/></a:dk2><a:lt2><a:srgbClr val="E7E6E6"/></a:lt2>'
        '<a:accent1><a:srgbClr val="0072B2"/></a:accent1>'
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
        % (latin, ea, latin, ea)
    )


def write_deck(slides: list[Slide], out_path, spacing: dict | None = None,
               fonts: tuple[str, str] = (DEFAULT_FONT_LATIN, DEFAULT_FONT_EA)) -> dict:
    """Write the package. Returns a summary the audit can consume."""
    spacing = spacing or {"title": 32, "body": 20}
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
        f'<p:sldSz cx="{SLIDE_W}" cy="{SLIDE_H}"/><p:notesSz cx="{SLIDE_H}" cy="{SLIDE_W}"/>'
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
        z.writestr("ppt/theme/theme1.xml", _theme(fonts))

        for i, slide in enumerate(slides, start=1):
            xml, images = _slide_xml(slide, spacing, fonts)
            z.writestr(f"ppt/slides/slide{i}.xml", xml)
            rels = ['<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slideLayout" Target="../slideLayouts/slideLayout1.xml"/>']
            for k, img in enumerate(images):
                ext = str(img).rsplit(".", 1)[-1].lower()
                media = f"image{i}_{k + 1}.{ext}"
                z.write(img, f"ppt/media/{media}")
                rels.append(
                    f'<Relationship Id="rId{k + 2}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/image" Target="../media/{media}"/>')
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
            "slide_size_emu": [SLIDE_W, SLIDE_H]}
