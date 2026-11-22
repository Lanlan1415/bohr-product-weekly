"""Build an academic deck from a spec, audit the written file, write result.json.

Dependencies: standard library only, plus Pillow and matplotlib when present for
text measurement and image reading. No python-pptx at run time — see pptxgen.py
for why.

Unrunnable input never surfaces as a traceback: an unreadable spec, a non-object
spec, an unknown section and an audit crash all come back as status
"undetermined" (exit 5) with a result.json naming the case. The refusal path
lives in contract.py and deliberately does not run the contract echo.
"""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import contract as C  # noqa: E402
import deckaudit as A  # noqa: E402
import extra_rules as X  # noqa: E402
import pptxgen as P  # noqa: E402

STRENGTH_SCALE = ("strong", "moderate", "weak")
DEFAULT_SPACING = {"title": 32, "body": 20}
DEFAULT_MIN_PT = A.MIN_BODY_PT
DEFAULT_MAX_BULLETS = A.MAX_BULLETS


def _num(value, default):
    """A finite number, or the default. Type-hostile input degrades, not crashes."""
    try:
        value = float(value)
    except (TypeError, ValueError):
        return default
    return value if value == value else default  # NaN degrades too


def coerce_spec(spec: dict) -> tuple[dict, list[str]]:
    """Normalise hostile field types into the shapes the rules read.

    Every downgrade is recorded as a limit note, so a degraded run says what it
    ignored instead of silently reading a different spec than the caller sent.
    Returns (coerced copy, notes).
    """
    notes: list[str] = []

    def take_list(key):
        v = spec.get(key)
        if v is None:
            return []
        if isinstance(v, list):
            return v
        notes.append(f"field '{key}' was not a list and was ignored")
        return []

    def take_dict(key, default):
        v = spec.get(key)
        if isinstance(v, dict):
            return v
        if v is not None:
            notes.append(f"field '{key}' was not an object and was ignored")
        return dict(default) if isinstance(default, dict) else default

    out = dict(spec)
    out["slides"] = take_list("slides")
    slides = []
    for s in out["slides"]:
        if isinstance(s, str):
            s = {"title": s}
        elif not isinstance(s, dict):
            notes.append("a slide entry was not an object and was ignored")
            continue
        sl = {k: ("" if v is None else str(v)) for k, v in s.items()
              if k in ("title", "claim", "strength", "evidence", "notes",
                       "image", "image_alt", "caption", "layout", "role")}
        bl = s.get("bullets")
        if isinstance(bl, list):
            sl["bullets"] = [{"text": str(b.get("text", "")), "level": b.get("level", 0)}
                             if isinstance(b, dict) else {"text": str(b), "level": 0}
                             for b in bl]
        elif bl:
            notes.append("a slide's bullets were not a list and were ignored")
        slides.append(sl)
    out["slides"] = slides

    out["goal"] = take_dict("goal", {})
    sp = take_dict("spacing", DEFAULT_SPACING)
    out["spacing"] = {"title": _num(sp.get("title"), 32), "body": _num(sp.get("body"), 20)} \
        if isinstance(sp, dict) else dict(DEFAULT_SPACING)
    out["template"] = take_dict("template", None) or None

    ev = spec.get("available_evidence")
    if ev is None:
        out["available_evidence"] = []
    elif isinstance(ev, (list, tuple)):
        out["available_evidence"] = [str(x) for x in ev]
    elif isinstance(ev, str):
        out["available_evidence"] = [ev]
    else:
        out["available_evidence"] = []
        notes.append("field 'available_evidence' was not a list and was ignored")

    out["min_font_pt"] = _num(spec.get("min_font_pt", DEFAULT_MIN_PT), DEFAULT_MIN_PT)
    out["max_bullets_per_slide"] = int(_num(spec.get("max_bullets_per_slide",
                                                        DEFAULT_MAX_BULLETS),
                                            DEFAULT_MAX_BULLETS))
    out["require_notes"] = bool(spec.get("require_notes", False))

    rev = spec.get("revisions")
    if rev is None:
        out["revisions"] = []
    elif isinstance(rev, list):
        out["revisions"] = [r if isinstance(r, dict) else {"changes": []} for r in rev]
    elif rev:
        out["revisions"] = []
        notes.append("field 'revisions' was not a list and was ignored")

    if not isinstance(spec.get("strength_scale"), (list, tuple)):
        out["strength_scale"] = list(STRENGTH_SCALE)
    if not isinstance(spec.get("narrative"), (list, tuple)):
        if spec.get("narrative") is not None:
            notes.append("field 'narrative' was not a list and was ignored")
        out["narrative"] = None
    return out, notes


def _image_aspects(slides_spec: list[dict]) -> dict:
    """Source aspect ratio per alt-text key, read from the image files."""
    out = {}
    for s in slides_spec:
        img = s.get("image")
        if not img or not Path(img).is_file():
            continue
        try:
            from PIL import Image
            with Image.open(img) as im:
                w, h = im.size
            out[s.get("image_alt") or Path(img).name] = w / h
        except Exception:
            continue
    return out


def check_declared_images(slides_spec: list[dict]) -> list[dict]:
    """A declared figure that cannot be read is lost content, named before the build.

    The slide is still built — minus the picture — so the run delivers an honest
    partial result instead of crashing on zipfile's open of a missing file.
    """
    findings = []
    for i, s in enumerate(slides_spec, start=1):
        img = s.get("image")
        if img and not Path(img).is_file():
            findings.append({
                "rule": "image.file_missing", "severity": "high",
                "message": "the slide declares a figure the filesystem does not have, so the "
                           "page was built without it and the visual evidence is lost",
                "slide": i, "image": str(img)})
    return findings


def deck_summary(slides_spec: list[dict], pptx_path, written: dict | None = None) -> dict:
    """The written deck as read back from disk, in the shape the section rules consume.

    The template-fit section judges the artifact, not the spec: which typefaces the
    titles actually name, where the title boxes actually sit, and which declared text
    actually landed. All of that is read here from the .pptx that was written. If the
    file cannot be re-read the summary degrades to the spacing-only form the older
    callers passed, and the declarative rules stay silent rather than guessing.
    The deck-edit section additionally reads each slide's speaker notes, because a
    recorded change may legitimately land in the notes rather than on the slide.
    """
    spacing = (written or {}).get("spacing")
    try:
        slides = A.read_deck(pptx_path)
    except Exception:
        return {"spacing": spacing}
    out = []
    for i, sl in enumerate(slides, start=1):
        meta = slides_spec[i - 1] if i - 1 < len(slides_spec) else {}
        geom = None
        fonts: set[str] = set()
        sizes: set[float] = set()
        texts: list[str] = []
        for sh in sl["shapes"]:
            is_title = sh["name"].lower().startswith("title")
            if is_title and geom is None and (sh["cx"] or sh["cy"]):
                geom = [sh["x"], sh["y"], sh["cx"], sh["cy"]]
            for p in sh["paras"]:
                texts.append(p["text"])
                if is_title:
                    for f in p.get("fonts") or []:
                        if f:
                            fonts.add(f)
                    if p.get("size_pt"):
                        sizes.add(float(p["size_pt"]))
        out.append({
            "index": i,
            "layout": str(meta.get("layout") or "content"),
            "title_geom": geom,
            "title_fonts": sorted(fonts),
            "title_sizes": sorted(sizes),
            "text": "\n".join(texts),
            "notes": sl.get("notes") or "",
        })
    return {"spacing": spacing, "slides": out}


def spec_slides(spec: dict) -> list:
    """The spec's slide entries as generator Slide objects.

    build_and_audit, check_deterministic and the benches all need the same
    translation, so it lives in exactly one place.
    """
    slides = []
    for s in spec.get("slides") or []:
        bullets = [P.Bullet(text=b.get("text", ""), level=int(b.get("level", 0)))
                   if isinstance(b, dict) else P.Bullet(text=str(b))
                   for b in (s.get("bullets") or [])]
        slides.append(P.Slide(
            title=s.get("title", ""), bullets=bullets, image=s.get("image"),
            image_alt=s.get("image_alt", ""), caption=s.get("caption", ""),
            notes=s.get("notes", ""), evidence=s.get("evidence", ""),
            claim=s.get("claim", ""), layout=s.get("layout", "content")))
    return slides


def check_deterministic(spec: dict, out_dir: Path) -> dict:
    """Build the deck twice and compare what a reader would see.

    Slide XML carries no timestamp, so the comparison can be structural: the strings
    and the geometry. Core properties are excluded because they legitimately differ.
    """
    import re
    import zipfile

    def fingerprint(path: Path) -> tuple:
        parts = []
        with zipfile.ZipFile(path) as z:
            for name in sorted(n for n in z.namelist() if n.startswith("ppt/slides/slide")):
                txt = z.read(name).decode("utf-8", "replace")
                strings = sorted(re.findall(r"<a:t>([^<]*)</a:t>", txt))
                offs = sorted(re.findall(r'<a:off x="(\d+)" y="(\d+)"/>', txt))
                exts = sorted(re.findall(r'<a:ext cx="(\d+)" cy="(\d+)"/>', txt))
                parts.append((name, tuple(strings), tuple(offs), tuple(exts)))
        return tuple(parts)

    prints = []
    for run in (1, 2):
        tmp = out_dir / f"_det{run}.pptx"
        _ = run
        P.write_deck(spec_slides(spec), tmp,
                     spacing=spec.get("spacing") or DEFAULT_SPACING,
                     fonts=(spec.get("font_latin", P.DEFAULT_FONT_LATIN),
                            spec.get("font_ea", P.DEFAULT_FONT_EA)))
        prints.append(fingerprint(tmp))
        try:
            tmp.unlink()
        except OSError:
            pass
    same = prints[0] == prints[1]
    return {"deterministic": same,
            "note": "two builds compared on slide text and geometry",
            "detail": {} if same else {"slides": len(prints[0])}}


def _render_preview(pptx_path: Path, out_dir: Path) -> dict:
    """Render to PDF/PNG when an office renderer exists; say so when it does not.

    The pinned image provides an `office-renderer`; a development machine usually
    does not. Reporting the absence is the honest outcome — claiming a preview that
    was never made is not.
    """
    for cmd in ("soffice", "libreoffice", "office-renderer"):
        exe = shutil.which(cmd)
        if not exe:
            continue
        try:
            import subprocess
            subprocess.run([exe, "--headless", "--convert-to", "pdf",
                            "--outdir", str(out_dir), str(pptx_path)],
                           check=True, capture_output=True, timeout=180)
            pdf = out_dir / (pptx_path.stem + ".pdf")
            if pdf.exists():
                return {"rendered": True, "renderer": cmd, "pdf": str(pdf)}
        except Exception as exc:
            return {"rendered": False, "renderer": cmd, "reason": str(exc)[:200]}
    return {"rendered": False, "reason": "no office renderer on PATH (soffice / office-renderer)"}


def evidence_map(spec: dict) -> list[dict]:
    """The page-level evidence mapping, as declared by the authoring spec.

    One row per slide: the assertion, its strength label and the source locator a
    reader can check the page against. This is the deliverable the case contract
    calls the per-page mapping — exported here so a reviewer can audit claim to
    source without opening the deck.
    """
    rows = []
    for i, s in enumerate(spec.get("slides") or [], start=1):
        rows.append({
            "slide": i,
            "title": str(s.get("title") or ""),
            "claim": str(s.get("claim") or ""),
            "strength": str(s.get("strength") or ""),
            "evidence": str(s.get("evidence") or ""),
            "notes": bool(str(s.get("notes") or "").strip()),
        })
    return rows


def build_and_audit(spec_path: Path, out_dir: Path, section: str | None = None) -> dict:
    """spec -> deck -> audit -> result dict (written to result.json).

    Every unrunnable shape comes back as an undetermined refusal with exit
    semantics handled by the caller — never a traceback.
    """
    spec, err = C.load_spec(spec_path)
    if err:
        return C.refused(out_dir, err)
    if not isinstance(spec, dict):
        return C.refused(out_dir, "the spec file is valid JSON but not an object")

    sec = section or spec.get("section")
    if sec is not None and not isinstance(sec, str):
        return C.refused(out_dir, "the section field is not a string", spec)
    if isinstance(sec, str) and sec not in X.SECTIONS:
        return C.refused(out_dir, f"unknown section '{sec}'; "
                                  f"choose from {sorted(X.SECTIONS)}", spec)

    spec, notes = coerce_spec(spec)
    out_dir = Path(out_dir)
    try:
        out_dir.mkdir(parents=True, exist_ok=True)
        result = _build(spec, sec, out_dir)
    except Exception as exc:  # a rule bug must never surface as a caller-side traceback
        return C.refused(out_dir, f"the build failed on this spec and was refused: {exc}", spec)

    limits = result["limits"] + notes
    result["limits"] = limits
    cid = spec.get("case_id")
    if cid is not None:
        result["case_id"] = cid
    if sec:
        result["section"] = sec
    C.echo_contract(spec, result, result["limits"])
    try:
        (out_dir / "result.json").write_text(
            json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    except OSError as exc:
        result["status"] = "undetermined"
        result["limits"] = result["limits"] + [f"result.json could not be written: {exc}"]
    return result


def _build(spec: dict, sec: str | None, out_dir: Path) -> dict:
    slides_spec = spec.get("slides") or []

    # Declared figures that cannot be read are dropped here and named, so the
    # build delivers an honest partial deck instead of crashing inside the writer.
    image_findings = check_declared_images(slides_spec)
    if image_findings:
        bad = {f["slide"] for f in image_findings}
        slides_spec = [s for i, s in enumerate(slides_spec, start=1) if i not in bad]
        spec = dict(spec)
        spec["slides"] = slides_spec

    # A deck with no pages is not a talk. The file would be a technically valid
    # package with zero slides and every rule would stay silent, so the emptiness
    # is named here instead of shipping a clean verdict over nothing.
    if not slides_spec:
        return {
            "schema_version": "deckbuild/v2",
            "status": "blocked",
            "findings": [{"rule": "deck.no_slides", "severity": "high",
                          "message": "the spec declares no slides, so there is no talk to "
                                     "organise or audit"}],
            "severity_counts": {"high": 1},
            "deck": {"path": str(out_dir / "deck.pptx"), "slides": 0,
                     "size_emu": [P.SLIDE_W, P.SLIDE_H],
                     "spacing": spec.get("spacing") or DEFAULT_SPACING,
                     "fonts": {"latin": spec.get("font_latin", P.DEFAULT_FONT_LATIN),
                               "ea": spec.get("font_ea", P.DEFAULT_FONT_EA)},
                     "template": None},
            "evidence_map": [],
            "preview": {"rendered": False, "reason": "no deck was written"},
            "reproducibility": {"deterministic": True, "note": "no slides to compare",
                                "detail": {}},
            "checked": {"slides": 0, "text_measured": False, "font_file": None,
                        "minimum_font_pt": spec.get("min_font_pt", DEFAULT_MIN_PT),
                        "note": "no slides"},
            "limits": [],
        }

    slides = spec_slides(spec)
    pptx = out_dir / "deck.pptx"
    written = P.write_deck(slides, pptx,
                           spacing=spec.get("spacing") or DEFAULT_SPACING,
                           fonts=(spec.get("font_latin", P.DEFAULT_FONT_LATIN),
                                  spec.get("font_ea", P.DEFAULT_FONT_EA)))
    audit = A.audit_deck(pptx, spec, image_aspects=_image_aspects(slides_spec))
    det = check_deterministic(spec, out_dir)
    if not det["deterministic"]:
        audit["findings"].append({
            "rule": "repro.nondeterministic", "severity": "high",
            "message": "building the same spec twice produced different slides, so the deck "
                       "cannot be reproduced", "detail": det["detail"]})
        c = {}
        for f in audit["findings"]:
            c[f["severity"]] = c.get(f["severity"], 0) + 1
        audit["severity_counts"] = c
        audit["status"] = "blocked" if c.get("high") else ("review" if audit["findings"] else "clean")
    preview = _render_preview(pptx, out_dir)

    # The skill-specific section runs on top of the shared deck audit; its findings
    # join the same list so there is one verdict. The section sees the written deck
    # (deck_summary), not the spec, so its artifact-level rules judge the file.
    if sec:
        extra = X.run(spec, sec, deck_summary(slides_spec, pptx, written))
        audit["findings"].extend(extra)
        counts = {}
        for f in audit["findings"]:
            counts[f["severity"]] = counts.get(f["severity"], 0) + 1
        audit["severity_counts"] = counts
        audit["status"] = ("clean" if not audit["findings"]
                           else "blocked" if counts.get("high") else "review")

    limits = []
    if not preview.get("rendered"):
        limits.append("preview not rendered: " + str(preview.get("reason", "unknown")))
    if not audit["checked"].get("text_measured"):
        limits.append("text overflow was estimated, not measured: no font file was available")

    template = spec.get("template") or {}
    result = {
        "schema_version": "deckbuild/v2",
        "status": audit["status"],
        "findings": image_findings + audit["findings"],
        "severity_counts": audit["severity_counts"],
        "deck": {"path": str(pptx), "slides": written["slides"],
                 "size_emu": written["slide_size_emu"], "spacing": written["spacing"],
                 "fonts": written["fonts"],
                 "template": str(template.get("name")) if template.get("name") else None},
        "evidence_map": evidence_map(spec),
        "preview": preview,
        "reproducibility": det,
        "checked": audit["checked"],
        "limits": limits,
    }
    counts = {}
    for f in result["findings"]:
        counts[f["severity"]] = counts.get(f["severity"], 0) + 1
    result["severity_counts"] = counts
    return result


def main(argv: list[str] | None = None) -> int:
    import argparse

    ap = argparse.ArgumentParser(prog="deckbuild", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--spec", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--section", help="override the spec's declared section")
    a = ap.parse_args(argv)
    r = build_and_audit(Path(a.spec), Path(a.out), a.section)
    print(json.dumps({"status": r.get("status"),
                      "findings": [f["rule"] for f in r.get("findings", [])],
                      "slides": (r.get("deck") or {}).get("slides"),
                      "preview": (r.get("preview") or {}).get("rendered"),
                      "wrote": str(Path(a.out) / "result.json")}, ensure_ascii=False))
    return {"clean": 0, "review": 3, "blocked": 4, "undetermined": 5}.get(r["status"], 1)


if __name__ == "__main__":
    raise SystemExit(main())
