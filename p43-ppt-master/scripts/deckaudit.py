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

import contract_echo as C

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


def write_refused(out_dir, message: str, case_id=None, case: dict | None = None) -> dict:
    """Write a structured refusal and safely retain a readable case contract.

    The spec is never consulted here: it may be absent or malformed.  Only the
    independently parsed case supplies identity and contract fields.  Contract
    backfill is guarded so even a hostile contract cannot hide the refusal.
    """
    result = {"schema_version": "deckbuild/v3", "status": "undetermined",
              "findings": [{"rule": "audit.no_section", "severity": "high",
                            "message": message}],
              "severity_counts": {"high": 1},
              "limits": ["the case could not be run as declared"]}
    if isinstance(case, dict) and case:
        try:
            C.apply(result, {}, case)
        except Exception as exc:  # refusal must remain available for every input
            result["limits"].append(
                f"case contract could not be backfilled on refusal: {type(exc).__name__}: {exc}")
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
                    runs = p.findall("a:r", NS)
                    text = "".join((r.find("a:t", NS).text or "") for r in runs
                                   if r.find("a:t", NS) is not None)
                    sz = None
                    if runs:
                        rpr = runs[0].find("a:rPr", NS)
                        if rpr is not None and rpr.get("sz"):
                            sz = int(rpr.get("sz")) / 100.0
                    # Explicit typefaces and RGB colors, if any. A run with none
                    # inherits the theme, so absence is collected as absence and
                    # never guessed into either a font or contrast violation.
                    fonts, colors = [], []
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
                sppr = sp.find("p:spPr", NS)
                fill_node = sppr.find("a:solidFill/a:srgbClr", NS) if sppr is not None else None
                shapes.append({
                    "kind": "sp",
                    "name": sp.find(".//p:cNvPr", NS).get("name", "") if sp.find(".//p:cNvPr", NS) is not None else "",
                    "placeholder": (ph.get("type") or "body") if ph is not None else "",
                    "x": int(off.get("x")) if off is not None else 0,
                    "y": int(off.get("y")) if off is not None else 0,
                    "cx": int(ext.get("cx")) if ext is not None else 0,
                    "cy": int(ext.get("cy")) if ext is not None else 0,
                    "paras": paras,
                    "fill_rgb": fill_node.get("val").upper()
                               if fill_node is not None and fill_node.get("val") else None,
                })
            bg = root.find("p:cSld/p:bg", NS)
            bg_rgb = bg.find(".//a:srgbClr", NS) if bg is not None else None
            pics = []
            for pic in root.iter(f"{{{NS['p']}}}pic"):
                xfrm = pic.find(".//a:xfrm", NS)
                off = xfrm.find("a:off", NS) if xfrm is not None else None
                ext = xfrm.find("a:ext", NS) if xfrm is not None else None
                blip = pic.find(".//a:blip", NS)
                cnv = pic.find(".//p:cNvPr", NS)
                pics.append({
                    "kind": "pic",
                    "name": cnv.get("name", "Figure") if cnv is not None else "Figure",
                    "rel": blip.get(f"{{{NS['r']}}}embed") if blip is not None else None,
                    "descr": cnv.get("descr", "") if cnv is not None else "",
                    "x": int(off.get("x")) if off is not None else 0,
                    "y": int(off.get("y")) if off is not None else 0,
                    "cx": int(ext.get("cx")) if ext is not None else 0,
                    "cy": int(ext.get("cy")) if ext is not None else 0,
                })
            notes = ""
            nname = f"ppt/notesSlides/notesSlide{idx}.xml"
            if nname in z.namelist():
                nroot = ET.fromstring(z.read(nname))
                notes = " ".join((t.text or "") for t in nroot.iter(f"{{{NS['a']}}}t"))
            slides.append({"index": idx, "shapes": shapes, "pics": pics, "notes": notes.strip(),
                           "background_rgb": bg_rgb.get("val").upper()
                                             if bg_rgb is not None and bg_rgb.get("val") else None})
    return slides


def _part_background(z: zipfile.ZipFile, part: str | None) -> str | None:
    """Read an explicit RGB background from a slide, layout or master part."""
    if not part or part not in z.namelist():
        return None
    try:
        root = ET.fromstring(z.read(part))
    except (KeyError, ET.ParseError):
        return None
    node = root.find("p:cSld/p:bg//a:srgbClr", NS)
    return node.get("val").upper() if node is not None and node.get("val") else None


def _theme_background(z: zipfile.ZipFile, master_part: str | None) -> str | None:
    """Resolve the theme's background-1 RGB when no explicit background exists."""
    if not master_part or master_part not in z.namelist():
        return None
    rel_name = posixpath.join(posixpath.dirname(master_part), "_rels",
                              posixpath.basename(master_part) + ".rels")
    if rel_name not in z.namelist():
        return None
    for rel in ET.fromstring(z.read(rel_name)):
        if not (rel.get("Type") or "").endswith("relationships/theme"):
            continue
        theme_part = posixpath.normpath(posixpath.join(posixpath.dirname(master_part),
                                                       rel.get("Target") or ""))
        if theme_part not in z.namelist():
            continue
        root = ET.fromstring(z.read(theme_part))
        bg1 = root.find(".//a:clrScheme/a:lt1", NS)
        if bg1 is None:
            return None
        rgb = bg1.find("a:srgbClr", NS)
        if rgb is not None and rgb.get("val"):
            return rgb.get("val").upper()
        system = bg1.find("a:sysClr", NS)
        if system is not None and system.get("lastClr"):
            return system.get("lastClr").upper()
    return None


def _relative_luminance(rgb: str) -> float:
    channels = [int(rgb[i:i + 2], 16) / 255.0 for i in (0, 2, 4)]
    linear = [v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4
              for v in channels]
    return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]


def _contrast_ratio(fg: str, bg: str) -> float:
    a, b = _relative_luminance(fg), _relative_luminance(bg)
    lighter, darker = max(a, b), min(a, b)
    return (lighter + 0.05) / (darker + 0.05)


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
    measured_count = 0
    measured_total = 0
    contrast_checks = 0
    slide_w, slide_h = 12192000, 6858000
    try:
        with zipfile.ZipFile(pptx_path) as z:
            pres = ET.fromstring(z.read("ppt/presentation.xml"))
            size = pres.find("p:sldSz", NS)
            if size is not None:
                slide_w = int(size.get("cx", slide_w))
                slide_h = int(size.get("cy", slide_h))
    except (KeyError, ET.ParseError, TypeError, ValueError):
        # export.invalid_package reports the missing/broken presentation below;
        # geometric checks retain a conservative standard canvas meanwhile.
        pass

    # A file that opens but contains no pages is not a presentation deliverable.
    if not slides:
        add("deck.no_slides", "high",
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
        evidence = str(ss.get("evidence") or "")
        evidence_landed = (not evidence or evidence.casefold()
                           in deck_text_by_slide.get(i + 1, "").casefold())
        evidence_map.append({
            "slide": i + 1,
            "claim": str(ss.get("claim") or ss.get("title") or ""),
            "evidence": evidence,
            "caption": cap,
            "caption_landed": landed,
            "evidence_landed": evidence_landed,
        })
    if evidence_map and not all(e["caption_landed"] for e in evidence_map):
        add("deck.caption_not_landed", "high",
            "a caption the spec declares never landed in the written deck, so the "
            "evidence locator is missing from the deliverable")
    evidence_not_landed = [e["slide"] for e in evidence_map if not e["evidence_landed"]]
    if evidence_not_landed:
        add("deck.evidence_not_landed", "high",
            "a declared source locator is absent from the visible slide text; "
            "the editable deck does not retain its own page-level provenance",
            slides=evidence_not_landed)

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

        # --- canvas geometry and real text-box collisions ------------------
        # Intentional decoration may overlap freely; only content-bearing text
        # boxes are collision-checked. Pictures still receive canvas bounds checks.
        tolerance = int(0.01 * EMU_IN)
        text_shapes = [sh for sh in sl["shapes"]
                       if any(p["text"].strip() for p in sh["paras"])]
        for obj in text_shapes + sl["pics"]:
            x, y, w, h = (obj[k] for k in ("x", "y", "cx", "cy"))
            if (w <= 0 or h <= 0 or x < -tolerance or y < -tolerance
                    or x + w > slide_w + tolerance or y + h > slide_h + tolerance):
                add("shape.out_of_bounds", "high",
                    "a content object has non-positive geometry or extends beyond the slide canvas",
                    slide=i, shape=obj.get("name") or obj["kind"],
                    geometry=[x, y, w, h], canvas=[slide_w, slide_h])
        for left in range(len(text_shapes)):
            a = text_shapes[left]
            area_a = a["cx"] * a["cy"]
            if area_a <= 0:
                continue
            for right in range(left + 1, len(text_shapes)):
                b = text_shapes[right]
                area_b = b["cx"] * b["cy"]
                if area_b <= 0:
                    continue
                iw = max(0, min(a["x"] + a["cx"], b["x"] + b["cx"]) - max(a["x"], b["x"]))
                ih = max(0, min(a["y"] + a["cy"], b["y"] + b["cy"]) - max(a["y"], b["y"]))
                overlap = iw * ih
                if overlap and overlap / min(area_a, area_b) >= 0.25:
                    add("shape.overlap", "high",
                        "two non-empty text boxes overlap by at least 25% of the smaller box",
                        slide=i, shapes=[a["name"], b["name"]],
                        overlap_ratio=round(overlap / min(area_a, area_b), 3))

        # --- structure ----------------------------------------------------
        if not title:
            add("deck.no_title", "high", "the slide has no title text", slide=i)
        if not [p for p in texts if p["text"].strip()]:
            add("deck.empty_slide", "high", "the slide carries no text at all", slide=i)
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
            horizontal_needed_emu = 0
            for p in sh["paras"]:
                max_width_px = max(inner_w / EMU_IN * 96, 1.0)
                m = measure_text(p["text"], p["size_pt"] or 18.0, max_width_px,
                                 font_path=measure_font)
                measured_any = measured_any or m["measured"]
                measured_count += int(bool(m["measured"]))
                measured_total += 1
                total_px += m["height_px"]
                # A single unbreakable Latin token used to bypass the vertical-only
                # test. Check its measured width explicitly, allowing raster rounding.
                if m["width_px"] > max_width_px * 1.01 + 1.0:
                    horizontal_needed_emu = max(horizontal_needed_emu, int(_emu(m["width_px"])))
            if _emu(total_px) > inner_h or horizontal_needed_emu:
                add("text.overflow", "high",
                    "the measured text exceeds its box horizontally or vertically; "
                    "automatic shrink-to-fit must not hide the defect",
                    slide=i, shape=sh["name"] or "text",
                    needed_emu=int(_emu(total_px)), box_emu=inner_h,
                    horizontal_needed_emu=horizontal_needed_emu,
                    horizontal_box_emu=inner_w if horizontal_needed_emu else None)

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
        if resolved.missing:
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
    master_by_slide: dict[int, tuple[str, str]] = {}
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
            master_part = _resolve(posixpath.dirname(lay_part), mas_targets[0])
            masters.add(master_part)
            master_by_slide[i] = (lay_part, master_part)
        if len(masters) > 1:
            add("master.inconsistent", "high",
                "the slides resolve to more than one slide master, so part of the deck sits "
                "on a different template — an edit that was supposed to touch one page "
                "reached the master behind the rest", masters=sorted(masters))

        # Contrast is checked only when both foreground and background RGB values
        # can be resolved from the actual package. Unknown effects/images are not
        # guessed into a verdict. Background precedence follows the real shell:
        # shape -> slide -> layout -> master -> theme background-1.
        for sl in slides:
            i = sl["index"]
            lay_part, master_part = master_by_slide.get(i, (None, None))
            inherited_bg = (sl.get("background_rgb") or _part_background(z, lay_part)
                            or _part_background(z, master_part)
                            or _theme_background(z, master_part))
            reported_contrast: set[tuple[str, str, str]] = set()
            for sh in sl["shapes"]:
                bg = sh.get("fill_rgb") or inherited_bg
                if not bg:
                    continue
                for para in sh["paras"]:
                    for fg in para.get("colors") or []:
                        try:
                            ratio = _contrast_ratio(fg, bg)
                        except (ValueError, TypeError):
                            continue  # malformed/unsupported colors cannot be judged
                        contrast_checks += 1
                        threshold = 3.0 if (para.get("size_pt") or 0) >= 24 else 4.5
                        key = (sh["name"], fg, bg)
                        if ratio < threshold and key not in reported_contrast:
                            reported_contrast.add(key)
                            add("text.contrast_low", "high",
                                "explicit text and background colors have insufficient contrast",
                                slide=i, shape=sh["name"], foreground=fg, background=bg,
                                ratio=round(ratio, 2), minimum=threshold)

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
            "text_measured_all": measured_total > 0 and measured_count == measured_total,
            "text_measurements": measured_total,
            "text_measurements_with_glyphs": measured_count,
            "contrast_checks": contrast_checks,
            "slide_size_emu": [slide_w, slide_h],
            # Report the font the measurements actually used, not the module default:
            # the two differ for any deck containing Chinese. "checked.font_file" is
            # the output-contract field a reader relies on to interpret overflow
            # verdicts: if it is not the declared typeface, the verdicts describe a
            # different font than the reader will see.
            "font_file": measure_font,
            "minimum_font_pt": min_pt,
            "note": ("overflow measured against glyph metrics"
                      if measured_total and measured_count == measured_total else
                      "some or all overflow measurements are estimates and are reported as such"),
            "evidence_map": evidence_map,
        },
        "evidence_map_top": evidence_map,
    }
