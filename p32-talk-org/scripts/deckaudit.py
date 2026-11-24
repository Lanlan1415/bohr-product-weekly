"""Audit a generated .pptx by reading the file that was actually written.

Two principles, both learned the hard way in this project:

1. **Audit the artifact, not the input.** The layout audit reads the XML inside
   the .pptx, so a renderer that drops a font size, misplaces a box, or loses
   speaker notes is caught. A check that trusts the spec only re-states the spec.
2. **Measure text, do not estimate it.** Overflow is judged against real glyph
   widths from a font file, wrapped into the actual box, not against a character
   count. Where no font file is available the check degrades to a declared
   heuristic rather than pretending to measure.

The claim/evidence fields live in the authoring spec, not in the slide XML, so the
audit takes both and cross-references them.
"""

from __future__ import annotations

import json
import posixpath
import re
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

NS = {
    "a": "http://schemas.openxmlformats.org/drawingml/2006/main",
    "p": "http://schemas.openxmlformats.org/presentationml/2006/main",
    "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
}
EMU_IN = 914400

# A slide that a reader in the back of a seminar room must still be able to read.
MIN_BODY_PT = 14
MAX_BULLETS = 6
MAX_TITLE_CHARS = 80
MAX_BODY_PT = 24


def write_refused(out_dir, message: str, case_id=None) -> dict:
    """Write a standalone refusal; never call the normal contract-echo path.

    A malformed spec may not define the nested objects that echoing requires.
    Only an explicitly supplied scalar case id is retained here.
    """
    result = {"schema_version": "deckbuild/v3", "status": "undetermined",
              "findings": [{"rule": "audit.no_section", "severity": "high",
                            "message": message},
                           {"rule": "audit.refused", "severity": "high",
                            "message": message}],
              "severity_counts": {"high": 2},
              "limits": ["the case could not be run as declared"]}
    if case_id is not None:
        result["case_id"] = case_id
    try:
        out_dir = Path(out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "result.json").write_text(
            json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    except OSError as exc:
        result["limits"].append(f"result.json could not be written: {exc}")
    return result


def _font_path() -> str | None:
    """A real TTF for measurement, or None when none is available."""
    try:
        import matplotlib
        from matplotlib import font_manager
        return font_manager.findfont("DejaVu Sans", fallback_to_default=True)
    except Exception:
        pass
    for cand in ("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
                 "C:/Windows/Fonts/arial.ttf", "C:/Windows/Fonts/DejaVuSans.ttf"):
        if Path(cand).exists():
            return cand
    return None


_FONT = _font_path()

# The measurement font has to cover the characters being measured. Measuring Chinese
# bullets with a Latin-only face gives the wrong width, and therefore the wrong overflow
# verdict — the same root cause as labels rendering as boxes.
_MEASURE_CACHE: dict[str, str] = {}


def measure_font_for(text: str) -> str | None:
    """A font file that covers `text`, cached per character set."""
    key = "".join(sorted(set(text)))
    if key in _MEASURE_CACHE:
        return _MEASURE_CACHE[key] or None
    try:
        import fontsel
        got = fontsel.resolve(text)
        path = got.path if got.path else _FONT
    except Exception:
        path = _FONT
    _MEASURE_CACHE[key] = path or ""
    return path


def measure_text(text: str, size_pt: float, max_width_px: float, dpi: int = 96,
                 font_path: str | None = None) -> dict:
    """Wrapped size of a text block, in pixels at `dpi`.

    Returns {"lines", "width_px", "height_px", "measured": bool}. When no font file
    is available the width falls back to a per-character estimate and `measured`
    is False, so the caller can say the number is approximate.
    """
    if not text.strip():
        return {"lines": 0, "width_px": 0.0, "height_px": 0.0, "measured": _FONT is not None}

    px = max(size_pt * dpi / 72.0, 1.0)
    use = font_path or _FONT
    measure = None
    if use:
        try:
            from PIL import ImageFont
            font = ImageFont.truetype(use, int(round(px)))
            measure = lambda s: font.getbbox(s)[2] - font.getbbox(s)[0]
        except (ImportError, OSError, ValueError):
            try:
                import glyphmetrics
                metric = glyphmetrics.load(use)
                measure = lambda s: metric.width(s, px)
            except Exception:
                measure = None
    if measure is not None:
        line_h = px * 1.22
        measured = True
    else:
        # Last-resort estimate is named as such; optional imaging packages never
        # turn a valid deck run into a ModuleNotFoundError refusal.
        def measure(s: str) -> float:
            return sum((1.0 if ord(ch) > 0x2E80 else 0.52) * px for ch in s)
        line_h = px * 1.25
        measured = False

    # Break opportunities: a CJK character can start a new line anywhere, but a Latin
    # word cannot. Splitting only on whitespace means a Chinese paragraph is one
    # unbreakable token, so it measures as a single line and overflow is never seen —
    # which silently disabled this check for every Chinese deck.
    CJK = re.compile(r"[　-〿㐀-䶿一-鿿豈-﫿"
                     r"＀-￯]")
    tokens: list[str] = []
    for chunk in re.split(r"(\s+)", text):
        if not chunk:
            continue
        if CJK.search(chunk) and not chunk.isspace():
            buf = ""
            for ch in chunk:
                if CJK.match(ch):
                    if buf:
                        tokens.append(buf)
                        buf = ""
                    tokens.append(ch)
                else:
                    buf += ch
            if buf:
                tokens.append(buf)
        else:
            tokens.append(chunk)

    lines, cur = 1, ""
    widest = 0.0
    for w in tokens:
        trial = cur + w
        if measure(trial) > max_width_px and cur.strip():
            widest = max(widest, measure(cur))
            lines += 1
            cur = w.lstrip()
        else:
            cur = trial
    widest = max(widest, measure(cur))
    return {"lines": lines, "width_px": widest, "height_px": lines * line_h,
            "measured": measured, "font": use}


def _norm_term(token: str) -> str:
    """Fold hyphenation and common British/American spelling variants.

    'signalling'/'signaling', 'colour'/'color', 'characterise'/'characterize' and
    'time-course'/'timecourse' collapse to one key. Anything this does not know
    about stays distinct, which is the safe direction: it under-reports rather
    than inventing inconsistency.
    """
    t = token.lower().replace("-", "").replace("_", "")
    for brit, amer in (("lling", "ling"), ("lled", "led"), ("llor", "lor"),
                       ("isation", "ization"), ("our", "or"), ("ise", "ize"),
                       ("yse", "yze"), ("ae", "e"), ("oe", "e")):
        if t.endswith(brit):
            t = t[: -len(brit)] + amer
            break
    return t


def _path_for(family: str) -> str | None:
    try:
        from matplotlib import font_manager
        return font_manager.findfont(family, fallback_to_default=False)
    except Exception:
        try:
            import fontsel
            return fontsel.find_family(family)
        except Exception:
            return None


def _installed(family: str) -> bool:
    """Whether a typeface with this family name is actually available here."""
    try:
        from matplotlib import font_manager
        names = {f.name.lower() for f in font_manager.fontManager.ttflist}
        if family.lower() in names:
            return True
        return _path_for(family) is not None
    except Exception:
        return _path_for(family) is not None


def _emu(px: float, dpi: int = 96) -> float:
    """Pixels at 96 dpi -> EMU, for comparing measured text against a box."""
    return px / dpi * EMU_IN


def read_deck(path) -> list[dict]:
    """Parse the slide parts into shapes with geometry and runs."""
    slides: list[dict] = []
    with zipfile.ZipFile(path) as z:
        names = sorted(n for n in z.namelist() if re.fullmatch(r"ppt/slides/slide\d+\.xml", n))
        names.sort(key=lambda n: int(re.search(r"(\d+)", n.rsplit("/", 1)[-1]).group(1)))
        for name in names:
            root = ET.fromstring(z.read(name))
            idx = int(re.search(r"(\d+)", name.rsplit("/", 1)[-1]).group(1))
            shapes = []
            for sp in root.iter(f"{{{NS['p']}}}sp"):
                xfrm = sp.find(".//a:xfrm", NS)
                off = xfrm.find("a:off", NS) if xfrm is not None else None
                ext = xfrm.find("a:ext", NS) if xfrm is not None else None
                paras = []
                for p in sp.findall(".//a:p", NS):
                    runs = p.findall("a:r", NS) + p.findall("a:fld", NS)
                    text = "".join((r.find("a:t", NS).text or "") for r in runs
                                   if r.find("a:t", NS) is not None)
                    sz = None
                    colors = []
                    if runs:
                        rpr = runs[0].find("a:rPr", NS)
                        if rpr is not None and rpr.get("sz"):
                            sz = int(rpr.get("sz")) / 100.0
                    # Explicit typefaces the runs declare, if any. A run with none
                    # inherits the theme, which is exactly what "kept the theme font"
                    # means, so absence is collected as absence and never punished.
                    fonts = []
                    for r in runs:
                        rpr = r.find("a:rPr", NS)
                        if rpr is None:
                            continue
                        for tag in ("a:latin", "a:ea"):
                            el = rpr.find(tag, NS)
                            if el is not None and el.get("typeface"):
                                fonts.append(el.get("typeface"))
                        rgb = rpr.find("a:solidFill/a:srgbClr", NS)
                        if rgb is not None and rgb.get("val"):
                            colors.append(rgb.get("val").upper())
                    ppr = p.find("a:pPr", NS)
                    lvl = int(ppr.get("lvl", "0")) if ppr is not None else 0
                    if text.strip():
                        paras.append({"text": text, "size_pt": sz, "level": lvl,
                                      "fonts": fonts, "colors": colors})
                ph = sp.find(".//p:nvPr/p:ph", NS)
                shapes.append({
                    "kind": "sp",
                    "name": sp.find(".//p:cNvPr", NS).get("name", "") if sp.find(".//p:cNvPr", NS) is not None else "",
                    "placeholder": (ph.get("type") or "body") if ph is not None else "",
                    "x": int(off.get("x")) if off is not None else 0,
                    "y": int(off.get("y")) if off is not None else 0,
                    "cx": int(ext.get("cx")) if ext is not None else 0,
                    "cy": int(ext.get("cy")) if ext is not None else 0,
                    "has_xfrm": xfrm is not None,
                    "paras": paras,
                })
            pics = []
            for pic in root.iter(f"{{{NS['p']}}}pic"):
                xfrm = pic.find(".//a:xfrm", NS)
                off = xfrm.find("a:off", NS) if xfrm is not None else None
                ext = xfrm.find("a:ext", NS) if xfrm is not None else None
                blip = pic.find(".//a:blip", NS)
                cnv = pic.find(".//p:cNvPr", NS)
                pics.append({
                    "kind": "pic", "name": cnv.get("name", "") if cnv is not None else "",
                    "rel": blip.get(f"{{{NS['r']}}}embed") if blip is not None else None,
                    "descr": cnv.get("descr", "") if cnv is not None else "",
                    "x": int(off.get("x")) if off is not None else 0,
                    "y": int(off.get("y")) if off is not None else 0,
                    "cx": int(ext.get("cx")) if ext is not None else 0,
                    "cy": int(ext.get("cy")) if ext is not None else 0,
                    "has_xfrm": xfrm is not None, "paras": [], "placeholder": "",
                })
            notes = ""
            nname = f"ppt/notesSlides/notesSlide{idx}.xml"
            if nname in z.namelist():
                nroot = ET.fromstring(z.read(nname))
                notes = " ".join((t.text or "") for t in nroot.iter(f"{{{NS['a']}}}t"))
            bg = root.find("p:cSld/p:bg//a:srgbClr", NS)
            slide_number = any(sh.get("placeholder") == "sldNum" for sh in shapes)
            slides.append({"index": idx, "shapes": shapes, "pics": pics,
                           "notes": notes.strip(),
                           "background": bg.get("val").upper() if bg is not None and bg.get("val") else None,
                           "has_slide_number": slide_number})
    return slides


def _luminance(rgb: str) -> float | None:
    try:
        channels = [int(rgb[i:i + 2], 16) / 255 for i in (0, 2, 4)]
    except (TypeError, ValueError):
        return None
    linear = [v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4 for v in channels]
    return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]


def _contrast_ratio(a: str, b: str) -> float | None:
    la, lb = _luminance(a), _luminance(b)
    if la is None or lb is None:
        return None
    return (max(la, lb) + 0.05) / (min(la, lb) + 0.05)


def _intersection(a: dict, b: dict) -> tuple[int, int]:
    return (max(0, min(a["x"] + a["cx"], b["x"] + b["cx"]) - max(a["x"], b["x"])),
            max(0, min(a["y"] + a["cy"], b["y"] + b["cy"]) - max(a["y"], b["y"])))


def _slide_size(pptx_path) -> tuple[int, int] | None:
    try:
        with zipfile.ZipFile(pptx_path) as z:
            root = ET.fromstring(z.read("ppt/presentation.xml"))
            size = root.find("p:sldSz", NS)
            if size is not None:
                return int(size.get("cx")), int(size.get("cy"))
    except (OSError, KeyError, ET.ParseError, TypeError, ValueError, zipfile.BadZipFile):
        return None
    return None


def audit_deck(pptx_path, spec: dict, image_aspects: dict | None = None) -> dict:
    """Rules over the written deck, cross-referenced with the authoring spec."""
    slides = read_deck(pptx_path)
    findings: list[dict] = []

    def add(rule, severity, message, **extra):
        findings.append({"rule": rule, "severity": severity, "message": message, **extra})

    deck_text = "".join(p["text"] for sl in slides for sh in sl["shapes"] for p in sh["paras"])
    measure_font = measure_font_for(deck_text) if deck_text else _FONT

    spec_slides = spec.get("slides") or []
    min_pt = float(spec.get("min_font_pt", MIN_BODY_PT))
    max_bullets = int(spec.get("max_bullets_per_slide", MAX_BULLETS))
    require_notes = bool(spec.get("require_notes", False))
    evidence_list = {str(e).strip().lower() for e in (spec.get("available_evidence") or [])}
    measured_any = False
    glyph_coverage = "not_checked"
    geometry_checked = 0
    contrast_checked = 0
    canvas = _slide_size(pptx_path)
    style = spec.get("style") if isinstance(spec.get("style"), dict) else {}
    footer = style.get("footer") if isinstance(style.get("footer"), dict) else {}
    logo = footer.get("logo")
    if logo and not Path(str(logo)).is_file():
        add("image.logo_missing", "high",
            "the declared footer logo does not exist and was not embedded", logo=str(logo))

    # A file that opens but contains no pages is not a presentation deliverable.
    if not slides:
        add("deck.no_slides", "high",
            "the written presentation contains no slides, so there is no talk to deliver")
        # Backward-compatible rule name retained for the original p31 contract.
        add("deck.empty_deck", "high",
            "the written presentation contains no slides, so there is no talk to deliver")
    max_slides = spec.get("max_slides", (spec.get("goal") or {}).get("max_slides")
                          if isinstance(spec.get("goal"), dict) else None)
    min_slides = spec.get("min_slides")
    try:
        if max_slides is not None and len(slides) > int(max_slides):
            add("deck.slide_count_over_limit", "medium",
                "the written deck exceeds the declared slide budget",
                slides=len(slides), limit=int(max_slides))
        if min_slides is not None and len(slides) < int(min_slides):
            add("deck.slide_count_under_limit", "medium",
                "the written deck does not meet the declared minimum slide count",
                slides=len(slides), minimum=int(min_slides))
    except (TypeError, ValueError):
        add("deck.slide_budget_invalid", "low",
            "the declared slide budget is not an integer and could not be enforced",
            max_slides=max_slides, min_slides=min_slides)

    # Missing figures become an honest partial slide, never a build-time traceback.
    for index, meta in enumerate(spec_slides, 1):
        image = meta.get("image") if isinstance(meta, dict) else None
        if image and not Path(str(image)).is_file():
            add("image.source_missing", "high",
                "a declared source figure does not exist; the slide was delivered without it",
                slide=index, image=str(image))
            # Backward-compatible rule name used by the original talk-org bench.
            add("image.file_missing", "high",
                "a declared source figure does not exist; the slide was delivered without it",
                slide=index, image=str(image))

    # The per-slide evidence map the brief asks the delivered record to carry:
    # claim, evidence locator and caption from the authoring spec, each cross-checked
    # against what the written deck actually contains (caption_landed).
    deck_text_by_slide = {}
    for sl in slides:
        deck_text_by_slide[sl["index"]] = "".join(
            p_txt["text"] for sh in sl["shapes"] for p_txt in sh["paras"])
    evidence_map = []
    for i, ss in enumerate(spec_slides):
        cap = str(ss.get("caption") or "").strip()
        landed = (cap == "") or (cap in deck_text_by_slide.get(i + 1, ""))
        evidence_map.append({
            "slide": i + 1,
            "claim": str(ss.get("claim") or ss.get("title") or ""),
            "evidence": str(ss.get("evidence") or ""),
            "caption": cap,
            "caption_landed": landed,
        })
    if evidence_map and not all(e["caption_landed"] for e in evidence_map):
        add("deck.caption_not_landed", "high",
            "a caption the spec declares never landed in the written deck, so the "
            "evidence locator is missing from the deliverable")

    for sl in slides:
        i = sl["index"]
        texts = [p for sh in sl["shapes"] for p in sh["paras"]]
        title = next((p["text"] for sh in sl["shapes"]
                      if sh["name"].lower().startswith("title")
                      or sh.get("placeholder") in ("title", "ctrTitle")
                      for p in sh["paras"]), "")
        body_paras = [p for sh in sl["shapes"]
                      if sh["name"].lower() == "body" or sh.get("placeholder") == "body"
                      for p in sh["paras"]]

        # --- geometry: bounds, overlap and explicit RGB contrast ------------
        objects = list(sl["shapes"]) + list(sl["pics"])
        for obj in objects:
            if obj.get("has_xfrm") and obj.get("paras") and (obj["cx"] <= 0 or obj["cy"] <= 0):
                add("layout.missing_geometry", "medium",
                    "a text shape has an explicit but unusable zero-size box",
                    slide=i, shape=obj.get("name"))
            if obj["cx"] <= 0 or obj["cy"] <= 0:
                continue
            geometry_checked += 1
            if canvas and (obj["x"] < 0 or obj["y"] < 0 or
                           obj["x"] + obj["cx"] > canvas[0] + 12700 or
                           obj["y"] + obj["cy"] > canvas[1] + 12700):
                add("layout.out_of_bounds", "high",
                    "an element extends beyond the delivered slide canvas",
                    slide=i, shape=obj.get("name"), box=[obj["x"], obj["y"], obj["cx"], obj["cy"]],
                    canvas=list(canvas))
            if obj.get("paras") and obj.get("name", "").lower() not in {"notes placeholder"}:
                for p in obj["paras"]:
                    for color in p.get("colors") or []:
                        if sl.get("background"):
                            ratio = _contrast_ratio(color, sl["background"])
                            if ratio is not None:
                                contrast_checked += 1
                                threshold = 3.0 if (p.get("size_pt") or 0) >= 24 else 4.5
                                if ratio + 1e-9 < threshold:
                                    add("format.low_contrast", "medium",
                                        "explicit text color has insufficient contrast with the slide background",
                                        slide=i, shape=obj.get("name"), ratio=round(ratio, 2),
                                        required=threshold, text=p["text"][:40])
        visible = [o for o in objects if o["cx"] > 0 and o["cy"] > 0 and
                   (o.get("paras") or o.get("kind") == "pic")]
        for ai, a in enumerate(visible):
            for b in visible[ai + 1:]:
                iw, ih = _intersection(a, b)
                if iw <= 45720 or ih <= 45720:
                    continue
                smaller = min(a["cx"] * a["cy"], b["cx"] * b["cy"])
                ratio = (iw * ih / smaller) if smaller else 0
                if ratio < 0.08:
                    continue
                image_involved = a.get("kind") == "pic" or b.get("kind") == "pic"
                add("layout.figure_overlap" if image_involved else "layout.overlap",
                    "medium" if image_involved else "high",
                    "visible elements overlap substantially" +
                    ("; verify whether this is an intentional figure annotation" if image_involved else ""),
                    slide=i, shapes=[a.get("name"), b.get("name")], smaller_shape_fraction=round(ratio, 3))

        # --- declared footer/page-number outcomes --------------------------
        slide_text = "".join(p["text"] for p in texts)
        if footer.get("text") and str(footer["text"]) not in slide_text:
            add("format.footer_missing", "high", "the declared footer text did not land on the slide", slide=i)
        if footer.get("page_numbers") and not sl.get("has_slide_number"):
            add("format.page_number_missing", "high", "a dynamic slide-number placeholder is missing", slide=i)
        if footer.get("logo") and Path(str(logo)).is_file() and not any(
                str(p.get("name") or "").lower() == "logo" for p in sl["pics"]):
            add("format.logo_missing", "high", "the declared logo was not embedded on the slide", slide=i)

        # --- structure ----------------------------------------------------
        if not title:
            add("deck.no_title", "high", "the slide has no title text", slide=i)
        if not [p for p in texts if p["text"].strip()] and not sl["pics"]:
            add("deck.empty_slide", "high", "the slide carries neither text nor a figure", slide=i)
        if len(body_paras) > max_bullets:
            add("deck.too_many_bullets", "medium",
                "more bullets than the declared density limit, so the slide will be read "
                "rather than presented", slide=i, bullets=len(body_paras), limit=max_bullets)
        if len(title) > MAX_TITLE_CHARS:
            add("deck.title_too_long", "medium",
                "the title is long enough to wrap into the body area", slide=i,
                chars=len(title))

        # --- type sizes ---------------------------------------------------
        for p in texts:
            sz = p["size_pt"]
            if sz is None:
                add("text.size_missing", "medium",
                    "a run declares no font size, so the theme default decides legibility",
                    slide=i, text=p["text"][:40])
                continue
            if sz < min_pt:
                add("text.font_too_small", "high",
                    f"{sz:g} pt is below the legibility floor {min_pt:g} pt", slide=i,
                    text=p["text"][:40])
            if p in body_paras and sz > MAX_BODY_PT:
                add("text.body_too_large", "low",
                    f"body text at {sz:g} pt competes with the title", slide=i)

        # --- overflow, measured against the real box ----------------------
        for sh in sl["shapes"]:
            if not sh["paras"] or sh["cx"] <= 0:
                continue
            inner_w = sh["cx"] - 2 * int(0.12 * EMU_IN)
            inner_h = sh["cy"] - 2 * int(0.08 * EMU_IN)
            total_px = 0.0
            widest_px = 0.0
            for p in sh["paras"]:
                m = measure_text(p["text"], p["size_pt"] or 18.0, inner_w / EMU_IN * 96,
                                 font_path=measure_font)
                measured_any = measured_any or m["measured"]
                total_px += m["height_px"]
                widest_px = max(widest_px, m["width_px"])
            if _emu(total_px) > inner_h or _emu(widest_px) > inner_w:
                add("text.overflow", "high",
                    "the text exceeds its usable width or height; it will wrap, shrink or spill",
                    slide=i, shape=sh["name"] or "text",
                    needed_emu=int(_emu(total_px)), box_emu=inner_h,
                    widest_emu=int(_emu(widest_px)), usable_width_emu=inner_w)

        # --- images -------------------------------------------------------
        for pic in sl["pics"]:
            if not pic["descr"]:
                add("image.no_alt_text", "low",
                    "the picture has no alt text, so its content is lost to a screen reader",
                    slide=i)
            if image_aspects:
                src = image_aspects.get(pic["descr"])
                if src and pic["cy"]:
                    placed = pic["cx"] / pic["cy"]
                    # >3% distortion is visible in a figure panel.
                    if abs(placed - src) / src > 0.03:
                        add("image.aspect_distorted", "high",
                            "the image was stretched: placed aspect differs from the source",
                            slide=i, placed=round(placed, 3), source=round(src, 3))

        # --- claim and evidence -------------------------------------------
        meta = spec_slides[i - 1] if i - 1 < len(spec_slides) else {}
        if not meta.get("claim"):
            add("deck.claim_missing", "medium",
                "the slide declares no single claim, so it is a topic rather than an "
                "assertion", slide=i)
        ev = str(meta.get("evidence") or "").strip()
        if not ev:
            add("deck.evidence_missing", "high",
                "the slide carries no source locator, so a reader cannot check it against "
                "the paper", slide=i)
        elif evidence_list and ev.lower() not in evidence_list:
            add("deck.evidence_unsupported", "high",
                "the slide points at a source that is not in the provided evidence list",
                slide=i, evidence=ev, available=sorted(evidence_list)[:8])
        if spec.get("require_evidence_on_slide") and ev and ev.casefold() not in slide_text.casefold():
            add("deck.evidence_not_landed", "high",
                "the declared source locator is absent from the visible slide text",
                slide=i, evidence=ev)

        # --- speaker notes -------------------------------------------------
        if require_notes and not sl["notes"]:
            add("deck.notes_missing", "medium",
                "the slide has no speaker notes, so the talk repeats the slide text", slide=i)
        if sl["notes"] and title and sl["notes"].strip() == title.strip():
            add("deck.notes_repeat_title", "low",
                "the speaker notes only repeat the title", slide=i)

    # --- cross-slide terminology -----------------------------------------
    # Grouped by a normalised key that folds hyphenation and the common
    # British/American variants, then compared on the *lowercased* surface forms.
    # Comparing raw spellings would fire on "Uptake" vs "uptake", which is just a
    # capital letter at the start of a line.
    terms: dict[str, set[str]] = {}
    for sl in slides:
        for sh in sl["shapes"]:
            for p in sh["paras"]:
                for tok in re.findall(r"[A-Za-z][A-Za-z\-]{4,}", p["text"]):
                    terms.setdefault(_norm_term(tok), set()).add(tok.lower())
    for key, forms in terms.items():
        if len(forms) > 1:
            add("text.term_inconsistent", "medium",
                "the same term appears in more than one spelling across the deck",
                term=key, forms=sorted(forms))

    # --- font reality: declared, installed, and able to draw the text ------
    declared = (spec.get("font_ea"), spec.get("font_latin"))
    for fam in declared:
        if fam and not _installed(fam):
            add("font.declared_missing", "medium",
                "a declared typeface is not installed here, so the target application will "
                "substitute and the layout will shift", family=fam)
    if deck_text:
        import fontsel as _fs
        resolved = _fs.resolve(deck_text)
        glyph_coverage = "measured" if resolved.measured else "unverifiable"
        if resolved.missing and resolved.measured:
            add("export.missing_glyphs", "high",
                "characters in the deck have no glyph in any installed font, so they will "
                "render as empty boxes", characters="".join(resolved.missing)[:40],
                count=len(resolved.missing))
        elif declared[0] and _installed(declared[0]):
            # The declared East Asian face must itself cover the text, or the substitution
            # happens at render time even though the file is well formed.
            path = _path_for(declared[0])
            if path:
                miss = _fs.coverage(path, deck_text)
                if miss:
                    add("export.missing_glyphs_in_declared_font", "medium",
                        "the declared typeface cannot draw some characters in the deck",
                        characters="".join(miss)[:40], family=declared[0])

    # --- package sanity ---------------------------------------------------
    def _resolve(base: str, target: str) -> str:
        """Resolve an OPC relationship target relative to the part that names it."""
        return posixpath.normpath(posixpath.join(base, target)).replace("\\", "/")

    def _rel_targets(z, part_name: str, rel_type_suffix: str) -> list[str]:
        """Target parts of one relationship type, as package paths."""
        rels_name = posixpath.join(posixpath.dirname(part_name), "_rels",
                                   posixpath.basename(part_name) + ".rels").replace("\\", "/")
        if rels_name not in z.namelist():
            return []
        out = []
        for rel in ET.fromstring(z.read(rels_name)):
            if (rel.get("Type") or "").endswith("relationships/" + rel_type_suffix):
                out.append(rel.get("Target") or "")
        return out

    # --- the master chain behind every slide -------------------------------
    # "改一页时顺手改坏母版和后面所有页" leaves two signatures in the package: a
    # slide whose layout relationship is gone or points at a part that is not
    # there, and a deck whose slides no longer agree on which master they belong
    # to. Both are read from the relationships of the written file, so a deck
    # assembled or patched by hand is checked exactly like a generated one.
    masters: set[str] = set()
    with zipfile.ZipFile(pptx_path) as z:
        names = set(z.namelist())
        if "ppt/presentation.xml" not in names:
            add("export.invalid_package", "high", "presentation.xml is missing")
        if not any(n.startswith("ppt/slideMasters/") for n in names):
            add("export.no_master", "high", "the package has no slide master")
        if not any(n.startswith("ppt/theme/") for n in names):
            add("export.no_theme", "high", "the package has no theme, so fonts are undefined")

        for sl in slides:
            i = sl["index"]
            lay_targets = _rel_targets(z, f"ppt/slides/slide{i}.xml", "slideLayout")
            if not lay_targets:
                add("master.layout_missing", "high",
                    "the slide names no slide layout, so it inherits no master, theme or "
                    "placeholder geometry — the signature of an edit that broke the deck's "
                    "structure", slide=i)
                continue
            lay_part = _resolve("ppt/slides", lay_targets[0])
            if lay_part not in names:
                add("master.layout_missing", "high",
                    "the slide's layout relationship points at a part the package does not "
                    "contain, so the slide has no template behind it", slide=i,
                    layout=lay_part)
                continue
            mas_targets = _rel_targets(z, lay_part, "slideMaster")
            if not mas_targets:
                add("master.layout_missing", "high",
                    "the slide's layout resolves to no slide master, so the master styles "
                    "behind the page are undefined", slide=i, layout=lay_part)
                continue
            masters.add(_resolve(posixpath.dirname(lay_part), mas_targets[0]))
        if len(masters) > 1:
            add("master.inconsistent", "high",
                "the slides resolve to more than one slide master, so part of the deck sits "
                "on a different template — an edit that was supposed to touch one page "
                "reached the master behind the rest", masters=sorted(masters))

        # 字体不丢: when the workflow declares embedded fonts, the package must
        # actually carry them. A deck that declares embed_fonts and ships none is
        # substituted at render time on the first machine without the face — the
        # "导出 PDF 后字体被替换" failure, caught before the export instead of after.
        # Declarative: a spec that declares nothing is not punished (reported as a
        # limit instead), and embed_fonts that resolves false turns the check off.
        if spec.get("embed_fonts") and not any(n.startswith("ppt/fonts/") for n in names):
            add("embed.missing", "medium",
                "the workflow declares embedded fonts but the package carries none, so the "
                "first machine without the typeface will substitute it and the export will "
                "reflow", declared=str(spec.get("embed_fonts")))

    counts: dict[str, int] = {}
    for f in findings:
        counts[f["severity"]] = counts.get(f["severity"], 0) + 1

    return {
        "schema_version": "deckaudit/v1",
        "status": ("clean" if not findings else "blocked" if counts.get("high") else "review"),
        "findings": findings,
        "severity_counts": counts,
        "checked": {
            "slides": len(slides),
            "text_measured": measured_any,
            "glyph_coverage": glyph_coverage,
            # Report the font the measurements actually used, not the module default:
            # the two differ for any deck containing Chinese. "checked.font_file" is
            # the output-contract field a reader relies on to interpret overflow
            # verdicts: if it is not the declared typeface, the verdicts describe a
            # different font than the reader will see.
            "font_file": measure_font,
            "minimum_font_pt": min_pt,
            "canvas_emu": list(canvas) if canvas else None,
            "geometry_checked": geometry_checked,
            "contrast_checked": contrast_checked,
            "layout_scope": "explicit slide shapes/pictures only; inherited and group transforms are not fully simulated",
            "note": ("overflow measured against glyph metrics" if measured_any else
                      "no font file found; overflow is an estimate and is reported as such"),
            "evidence_map": evidence_map,
        },
        "evidence_map_top": evidence_map,
    }
