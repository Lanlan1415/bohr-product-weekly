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
import contract_echo  # noqa: E402
import deckaudit as A  # noqa: E402
import extra_rules as X  # noqa: E402
import pptxgen as P  # noqa: E402

EXIT_CODES = {"clean": 0, "review": 3, "blocked": 4, "undetermined": 5}


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


def _write_refused(out_dir: Path, message: str, case_id: str | None = None) -> dict:
    """A refusal is a recorded outcome: write result.json, status undetermined.

    Self-contained on purpose: it runs before any audit exists, so it depends on
    nothing but the json module and never calls the contract echoer -- the spec
    it would echo from is exactly the input that could not be read. Anything the
    caller passed as a plain case identifier on the command line is still kept.
    """
    result = {"schema_version": "deckbuild/v1", "status": "undetermined",
              "findings": [{"rule": "audit.no_section", "severity": "high",
                            "message": message}],
              "limits": ["the case could not be run as declared"]}
    if case_id:
        result["case_id"] = str(case_id)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "result.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return result


def _sanitise(spec: dict) -> tuple[dict, list[str]]:
    """A defensive copy with mistyped numeric/enum fields coerced to safe values.

    A case with one mistyped field (spacing as a string, min_font_pt as a word,
    available_evidence as a bare value) still deserves an audited deck instead of
    a crash. Each coercion is named in the returned notes so the result can say
    a default was used rather than pretending the spec declared it.
    """
    s = dict(spec)
    notes: list[str] = []
    sp = s.get("spacing")
    if not isinstance(sp, dict) or not isinstance(sp.get("title"), (int, float)) \
            or not isinstance(sp.get("body"), (int, float)):
        s["spacing"] = {"title": 32, "body": 20}
        if sp is not None:
            notes.append("spacing was malformed; the engine default (title 32 pt / "
                         "body 20 pt) was used")
    for key, default in (("min_font_pt", A.MIN_BODY_PT),
                         ("max_bullets_per_slide", A.MAX_BULLETS)):
        v = s.get(key)
        if v is not None and not isinstance(v, (int, float)):
            s[key] = default
            notes.append(f"{key} was not a number; the engine default was used")
    if "require_notes" in s and not isinstance(s.get("require_notes"), bool):
        s["require_notes"] = bool(s.get("require_notes"))
    ev = s.get("available_evidence")
    if ev is not None and not isinstance(ev, (list, tuple)):
        s["available_evidence"] = []
        notes.append("available_evidence was not a list; the evidence check was skipped")
    for key in ("font_latin", "font_ea"):
        v = s.get(key)
        if v is not None and not isinstance(v, str):
            s[key] = P.DEFAULT_FONT_LATIN if key == "font_latin" else P.DEFAULT_FONT_EA
            notes.append(f"{key} was not a string; the engine default typeface was used")
    return s, notes


def build_and_audit(spec_path: Path, out_dir: Path, case_id: str | None = None) -> dict:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    try:
        spec = json.loads(Path(spec_path).read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        return _write_refused(out_dir, f"the spec file is not readable JSON: {exc}", case_id)
    except OSError:
        return _write_refused(out_dir, "the spec file could not be read", case_id)
    if not isinstance(spec, dict):
        return _write_refused(out_dir, "the spec file is not a JSON object", case_id)
    if case_id is None:
        case_id = spec.get("case_id")
    case_id = str(case_id) if case_id is not None else None

    spec2, sanitise_notes = _sanitise(spec)

    try:
        slides_spec = spec2.get("slides") if isinstance(spec2.get("slides"), (list, tuple)) \
            else []
        slides = spec_slides(spec2)
    except (ValueError, TypeError, KeyError, AttributeError) as exc:
        return _write_refused(out_dir, f"the spec cannot be turned into slides: {exc}",
                              case_id)

    try:
        pptx = out_dir / "deck.pptx"
        written = P.write_deck(slides, pptx,
                               spacing=spec2.get("spacing") or {"title": 32, "body": 20},
                               fonts=(spec2.get("font_latin", P.DEFAULT_FONT_LATIN),
                                      spec2.get("font_ea", P.DEFAULT_FONT_EA)))
        audit = A.audit_deck(pptx, spec2, image_aspects=_image_aspects(slides_spec))
    except (ValueError, TypeError, KeyError, AttributeError, OSError) as exc:
        return _write_refused(out_dir, f"the deck could not be built or audited: {exc}",
                              case_id)
    det = check_deterministic(spec2, out_dir)
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
    section = spec2.get("section")
    if section:
        try:
            extra = X.run(spec2, section, deck_summary(slides_spec, pptx, written))
        except (ValueError, TypeError, AttributeError) as exc:
            return _write_refused(out_dir, f"unknown section or dispatch failure: {exc}",
                                  case_id)
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
    limits.extend(sanitise_notes)

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
    if case_id is not None:
        result["case_id"] = case_id
    result = contract_echo.apply(result, spec)
    (out_dir / "result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2),
                                         encoding="utf-8")
    return result


def main(argv: list[str] | None = None) -> int:
    import argparse

    ap = argparse.ArgumentParser(prog="deckbuild", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--spec", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--case-id", help="case identifier to record in result.json")
    a = ap.parse_args(argv)
    r = build_and_audit(Path(a.spec), Path(a.out), case_id=a.case_id)
    print(json.dumps({"status": r["status"],
                      "case_id": r.get("case_id"),
                      "findings": [f["rule"] for f in r.get("findings", [])],
                      "slides": (r.get("deck") or {}).get("slides"),
                      "preview": (r.get("preview") or {}).get("rendered"),
                      "wrote": str(Path(a.out) / "result.json")}, ensure_ascii=False))
    return EXIT_CODES.get(r["status"], 1)


if __name__ == "__main__":
    raise SystemExit(main())
