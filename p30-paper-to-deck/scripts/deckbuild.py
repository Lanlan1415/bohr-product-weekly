"""Build an academic deck from a spec, audit the written file, write result.json.

Dependencies: standard library only, plus Pillow and matplotlib when present for
text measurement and image reading. No python-pptx at run time — see pptxgen.py
for why.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import deckaudit as A  # noqa: E402
import extra_rules as X  # noqa: E402
import pptxgen as P  # noqa: E402


def _image_aspects(slides_spec: list[dict]) -> dict:
    """Source aspect ratio per alt-text key, read from the image files."""
    out = {}
    for s in slides_spec:
        img = s.get("image")
        if not img or not Path(img).exists():
            continue
        try:
            from PIL import Image
            with Image.open(img) as im:
                w, h = im.size
            out[s.get("image_alt") or Path(img).name] = w / h
        except Exception:
            continue
    return out


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
    import hashlib
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
                     spacing=spec.get("spacing") or {"title": 32, "body": 20},
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
            subprocess.run([exe, "--headless", "--convert-to", "pdf",
                            "--outdir", str(out_dir), str(pptx_path)],
                           check=True, capture_output=True, timeout=180)
            pdf = out_dir / (pptx_path.stem + ".pdf")
            if pdf.exists():
                return {"rendered": True, "renderer": cmd, "pdf": str(pdf)}
        except Exception as exc:
            return {"rendered": False, "renderer": cmd, "reason": str(exc)[:200]}
    return {"rendered": False, "reason": "no office renderer on PATH (soffice / office-renderer)"}


def build_and_audit(spec_path: Path, out_dir: Path) -> dict:
    spec = json.loads(Path(spec_path).read_text(encoding="utf-8"))
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    slides_spec = spec.get("slides") or []
    slides = spec_slides(spec)

    pptx = out_dir / "deck.pptx"
    written = P.write_deck(slides, pptx,
                           spacing=spec.get("spacing") or {"title": 32, "body": 20},
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
    section = spec.get("section")
    if section:
        extra = X.run(spec, section, deck_summary(slides_spec, pptx, written))
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

    result = {
        "schema_version": "deckbuild/v1",
        "status": audit["status"],
        "findings": audit["findings"],
        "severity_counts": audit["severity_counts"],
        "deck": {"path": str(pptx), "slides": written["slides"],
                 "size_emu": written["slide_size_emu"], "spacing": written["spacing"],
                 "fonts": written["fonts"]},
        "preview": preview,
        "reproducibility": det,
        "checked": audit["checked"],
        "limits": limits,
    }
    (out_dir / "result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2),
                                         encoding="utf-8")
    return result


def main(argv: list[str] | None = None) -> int:
    import argparse

    ap = argparse.ArgumentParser(prog="deckbuild", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--spec", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args(argv)
    r = build_and_audit(Path(a.spec), Path(a.out))
    print(json.dumps({"status": r["status"],
                      "findings": [f["rule"] for f in r["findings"]],
                      "slides": r["deck"]["slides"],
                      "preview": r["preview"].get("rendered"),
                      "wrote": str(Path(a.out) / "result.json")}, ensure_ascii=False))
    return {"clean": 0, "review": 3, "blocked": 4}.get(r["status"], 1)


if __name__ == "__main__":
    raise SystemExit(main())
