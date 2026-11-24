"""Build or preserve-edit an academic deck, audit the file, and write result.json.

Three real artifact paths share one verdict:
  * no source_deck       -> generate an editable PresentationML deck;
  * source_deck          -> apply recorded text changes inside the real package;
  * template.file        -> connect the deliverable to that package's real shell.

Only successful audits use contract_echo.  Refusal is deliberately standalone and
never assumes that a spec (or its nested output_contract) exists.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import contract_echo as C  # noqa: E402
import deckaudit as A  # noqa: E402
import decksource as DS  # noqa: E402
import extra_rules as X  # noqa: E402
import pptxgen as P  # noqa: E402
import templatecheck as T  # noqa: E402

EXIT_CODES = {"clean": 0, "review": 3, "blocked": 4, "undetermined": 5}


def _spacing(spec: dict, limits: list[str]) -> dict[str, float]:
    raw = spec.get("spacing")
    if raw is None:
        raw = {}
    if not isinstance(raw, dict):
        limits.append(f"spacing type {type(raw).__name__} was invalid; defaults 32/20 used")
        raw = {}
    out: dict[str, float] = {}
    for key, default in (("title", 32.0), ("body", 20.0)):
        try:
            out[key] = float(raw.get(key, default))
            if out[key] <= 0:
                raise ValueError("font size must be positive")
        except (TypeError, ValueError, AttributeError) as exc:
            out[key] = default
            limits.append(f"spacing.{key} was invalid ({exc}); default {default:g} used")
    return out


def _generation_style(spec: dict, limits: list[str]) -> dict:
    """Return the exact style used by every build, including repeat builds."""
    style = P.normalize_style(spec.get("style"), limits)
    logo = style["footer"].get("logo")
    if logo and not Path(str(logo)).is_file():
        limits.append(f"footer logo is missing and was not embedded: {logo}")
        style["footer"]["logo"] = None
    return style


def _image_aspects(slides_spec: list[dict], spec: dict | None = None) -> dict:
    out = {}
    for slide in slides_spec:
        if not isinstance(slide, dict):
            continue
        image = slide.get("image")
        if not image or not Path(str(image)).is_file():
            continue
        size = P.image_size(image)
        if size and size[1]:
            out[slide.get("image_alt") or Path(str(image)).name] = size[0] / size[1]
    style = (spec or {}).get("style")
    if isinstance(style, dict) and isinstance(style.get("footer"), dict):
        footer = style["footer"]
        logo = footer.get("logo")
        if logo and Path(str(logo)).is_file():
            size = P.image_size(logo)
            if size and size[1]:
                out[str(footer.get("logo_alt") or Path(str(logo)).name)] = size[0] / size[1]
    return out


def spec_slides(spec: dict) -> list[P.Slide]:
    raw = spec.get("slides") or []
    if not isinstance(raw, list):
        raise ValueError("slides must be a list of objects")
    slides: list[P.Slide] = []
    for index, slide in enumerate(raw, 1):
        if not isinstance(slide, dict):
            raise ValueError(f"slide {index} is not an object")
        raw_bullets = slide.get("bullets") or []
        if not isinstance(raw_bullets, list):
            raise ValueError(f"slide {index} bullets must be a list")
        bullets = []
        for bullet in raw_bullets:
            if isinstance(bullet, dict):
                bullets.append(P.Bullet(text=str(bullet.get("text") or ""),
                                        level=int(bullet.get("level", 0))))
            else:
                bullets.append(P.Bullet(text=str(bullet)))
        image = slide.get("image")
        if image and not Path(str(image)).is_file():
            # The written artifact stays partial and auditable; image.source_missing
            # is raised against the spec by deckaudit, rather than failing the build.
            image = None
        slides.append(P.Slide(
            title=str(slide.get("title") or ""), bullets=bullets, image=image,
            image_alt=str(slide.get("image_alt") or ""), caption=str(slide.get("caption") or ""),
            notes=str(slide.get("notes") or ""), evidence=str(slide.get("evidence") or ""),
            claim=str(slide.get("claim") or ""), layout=str(slide.get("layout") or "content")))
    return slides


def deck_summary(slides_spec: list[dict], pptx_path: Path, written: dict) -> dict:
    """Read the delivered file, not the spec, for per-slide geometry and landing checks."""
    try:
        slides = A.read_deck(pptx_path)
    except Exception:
        return {"spacing": written.get("spacing"), "slides": []}
    out = []
    for index, slide in enumerate(slides, 1):
        meta = slides_spec[index - 1] if index - 1 < len(slides_spec) else {}
        if not isinstance(meta, dict):
            meta = {}
        geometry, body_geometry = None, None
        fonts, sizes, body_sizes, texts = set(), set(), set(), []
        title_colors, body_colors = set(), set()
        for shape in slide["shapes"]:
            is_title = (shape["name"].lower().startswith("title")
                        or shape.get("placeholder") in ("title", "ctrTitle"))
            is_body = (shape["name"].lower() == "body"
                       or shape.get("placeholder") in ("body", "object"))
            if is_title and geometry is None and (shape["cx"] or shape["cy"]):
                geometry = [shape["x"], shape["y"], shape["cx"], shape["cy"]]
            if is_body and body_geometry is None and (shape["cx"] or shape["cy"]):
                body_geometry = [shape["x"], shape["y"], shape["cx"], shape["cy"]]
            for para in shape["paras"]:
                texts.append(para["text"])
                if is_title:
                    fonts.update(f for f in (para.get("fonts") or []) if f)
                    title_colors.update(para.get("colors") or [])
                    if para.get("size_pt"):
                        sizes.add(float(para["size_pt"]))
                if is_body:
                    body_colors.update(para.get("colors") or [])
                    if para.get("size_pt"):
                        body_sizes.add(float(para["size_pt"]))
        out.append({"index": index, "layout": str(meta.get("layout") or "content"),
                    "title_geom": geometry, "body_geom": body_geometry,
                    "title_fonts": sorted(fonts), "title_sizes": sorted(sizes),
                    "title_colors": sorted(title_colors), "body_colors": sorted(body_colors),
                    "body_sizes": sorted(body_sizes), "text": "\n".join(texts),
                    "background": slide.get("background"), "has_slide_number": slide.get("has_slide_number"),
                    "notes": slide.get("notes") or ""})
    return {"spacing": written.get("spacing"), "slides": out}


def _fingerprint(path: Path) -> tuple:
    parts = []
    with zipfile.ZipFile(path) as z:
        names = sorted((n for n in z.namelist() if re.fullmatch(r"ppt/slides/slide\d+\.xml", n)),
                       key=lambda n: int(re.search(r"\d+", n.rsplit("/", 1)[-1]).group()))
        for name in names:
            text = z.read(name).decode("utf-8", "replace")
            strings = re.findall(r"<a:t>([^<]*)</a:t>", text)
            offsets = re.findall(r'<a:off x="(\d+)" y="(\d+)"\s*/?>', text)
            extents = re.findall(r'<a:ext cx="(\d+)" cy="(\d+)"\s*/?>', text)
            parts.append((name, tuple(strings), tuple(offsets), tuple(extents)))
    # Notes matter to reproducibility as much as visible slide text.
    with zipfile.ZipFile(path) as z:
        notes = tuple((n, hashlib.sha256(z.read(n)).hexdigest()) for n in sorted(z.namelist())
                      if n.startswith("ppt/notesSlides/notesSlide") and n.endswith(".xml"))
    return tuple(parts), notes


def _apply_template_if_requested(pptx: Path, spec: dict, measured: dict | None) -> dict:
    template = spec.get("template")
    if not measured or not isinstance(template, dict) or not template.get("file"):
        return {"applied": False, "reason": "no template file declared"}
    return T.apply_shell(pptx, template["file"], spec, measured)


def check_deterministic(spec: dict, out_dir: Path, template_measured: dict | None = None) -> dict:
    prints = []
    for run in (1, 2):
        temp = out_dir / f"_det{run}.pptx"
        if spec.get("source_deck"):
            DS.apply_changes(spec["source_deck"], temp, spec)
        else:
            P.write_deck(spec_slides(spec), temp, spacing=_spacing(spec, []),
                         fonts=(spec.get("font_latin", P.DEFAULT_FONT_LATIN),
                                spec.get("font_ea", P.DEFAULT_FONT_EA)),
                         style=_generation_style(spec, []))
        _apply_template_if_requested(temp, spec, template_measured)
        prints.append(_fingerprint(temp))
        temp.unlink(missing_ok=True)
    same = prints[0] == prints[1]
    return {"deterministic": same,
            "note": "two final artifacts compared on slide text, geometry and speaker notes",
            "detail": {} if same else {"slide_parts": len(prints[0][0])}}


def _render_preview(pptx_path: Path, out_dir: Path) -> dict:
    if os.environ.get("DECKBUILD_NO_RENDER") == "1":
        return {"rendered": False, "artifacts": [],
                "reason": "render explicitly disabled for regression run (DECKBUILD_NO_RENDER=1)"}
    candidates = []
    for command in ("soffice", "libreoffice", "office-renderer"):
        found = shutil.which(command)
        if found:
            candidates.append((command, found))
    for command, path in (
        ("soffice", "C:/Program Files/LibreOffice/program/soffice.exe"),
        ("soffice", "/usr/bin/soffice"),
        ("libreoffice", "/usr/bin/libreoffice"),
    ):
        if Path(path).is_file():
            candidates.append((command, path))
    for command, executable in candidates:
        try:
            proc = subprocess.run([executable, "--headless", "--convert-to", "pdf",
                                   "--outdir", str(out_dir), str(pptx_path)],
                                  check=True, capture_output=True, timeout=180)
            pdf = out_dir / (pptx_path.stem + ".pdf")
            if pdf.is_file() and pdf.stat().st_size:
                header = pdf.read_bytes()[:8]
                return {"rendered": True, "renderer": command, "pdf": str(pdf),
                        "artifacts": [str(pdf)], "returncode": proc.returncode,
                        "pdf_bytes": pdf.stat().st_size, "pdf_header_valid": header.startswith(b"%PDF-"),
                        "inspection": "real PDF produced; pixel-level parity is not claimed by this record"}
            reason = "renderer returned success but produced no non-empty PDF"
        except Exception as exc:
            reason = str(exc)[:240]
        return {"rendered": False, "renderer": command, "reason": reason, "artifacts": []}
    return {"rendered": False, "artifacts": [],
            "reason": "no office renderer on PATH or standard install locations"}


def _status(findings: list[dict]) -> tuple[str, dict]:
    counts: dict[str, int] = {}
    for finding in findings:
        counts[finding["severity"]] = counts.get(finding["severity"], 0) + 1
    status = "blocked" if counts.get("high") else ("review" if findings else "clean")
    return status, counts


def _source_findings(source_record: dict) -> list[dict]:
    findings = []
    if not source_record.get("package_preserved", True):
        findings.append({"rule": "edit.package_not_preserved", "severity": "high",
                         "message": "source editing added or dropped package parts"})
    for rec in source_record.get("records") or []:
        if rec.get("status") == "before_missing":
            findings.append({"rule": "edit.before_not_in_source", "severity": "high",
                             "message": "the recorded before text is absent from the named source "
                                        "slide and the after text is not already present",
                             "slide": rec.get("slide"), "revision": rec.get("revision"),
                             "change": rec.get("change"), "section": "deck_edit"})
        elif rec.get("status") in {"invalid_slide", "malformed_xml", "shape_missing",
                                    "shape_ambiguous", "invalid_geometry", "invalid_style"}:
            findings.append({"rule": "edit.source_change_unapplied", "severity": "high",
                             "message": "a recorded source-deck change could not be applied",
                             "reason": rec["status"], "slide": rec.get("slide"),
                             "revision": rec.get("revision"), "change": rec.get("change"),
                             "section": "deck_edit"})
    return findings


def build_and_audit(spec_path: Path, out_dir: Path, case_path: Path | None = None,
                    case_id: str | None = None) -> dict:
    case, case_error = C.read_case(case_path)
    refusal_id = case_id if case_id is not None else case.get("case_id")
    refusal_spec: dict = {}

    def refuse(message: str) -> dict:
        result = A.write_refused(out_dir, message, case_id=refusal_id)
        # A readable case is independent of a malformed/missing spec. Preserve its
        # complete contract even on refusal, without asking contract_echo to parse
        # or depend on any field from that bad spec.
        if case or refusal_id is not None:
            fallback = case if case else (refusal_spec if refusal_spec else {"case_id": refusal_id})
            C.apply(result, {}, fallback)
            try:
                Path(out_dir).mkdir(parents=True, exist_ok=True)
                (Path(out_dir) / "result.json").write_text(
                    json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
            except OSError as exc:
                result.setdefault("limits", []).append(f"refusal result could not be rewritten: {exc}")
        return result

    try:
        spec = json.loads(Path(spec_path).read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        return refuse(f"the spec file is not readable UTF-8 JSON: {exc}")
    if not isinstance(spec, dict):
        return refuse("the spec file is not an object; it must be a JSON object")
    if refusal_id is None:
        refusal_id = spec.get("case_id")
    refusal_spec = spec
    out_dir = Path(out_dir)
    try:
        out_dir.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        return refuse(f"the output directory cannot be created: {exc}")

    limits: list[str] = []
    if case_error:
        limits.append(case_error)
    spacing = _spacing(spec, limits)
    style = _generation_style(spec, limits)
    pptx = out_dir / "deck.pptx"
    source_record = None
    try:
        slides_spec = spec.get("slides") or []
        if not isinstance(slides_spec, list):
            raise ValueError("slides must be a list of objects")
        if spec.get("source_deck"):
            source = Path(str(spec["source_deck"]))
            if not source.is_file():
                return refuse(f"source_deck does not exist: {source}")
            source_record = DS.apply_changes(source, pptx, spec)
            if not slides_spec:
                # Metadata remain blank by design: no claims or evidence are invented.
                slides_spec = DS.inspect(source).get("slides") or []
                spec = dict(spec)
                spec["slides"] = slides_spec
            written = {"slides": len(A.read_deck(pptx)), "spacing": spacing,
                       "fonts": {"latin": spec.get("font_latin", P.DEFAULT_FONT_LATIN),
                                 "ea": spec.get("font_ea", P.DEFAULT_FONT_EA)}}
        else:
            slides = spec_slides(spec)
            P.write_deck(slides, pptx, spacing=spacing,
                         fonts=(str(spec.get("font_latin", P.DEFAULT_FONT_LATIN)),
                                str(spec.get("font_ea", P.DEFAULT_FONT_EA))), style=style)
            written = {"slides": len(slides), "spacing": spacing,
                       "fonts": {"latin": spec.get("font_latin", P.DEFAULT_FONT_LATIN),
                                 "ea": spec.get("font_ea", P.DEFAULT_FONT_EA)}}
            spec_slides(spec)  # validate once before any later section consumes it
    except (OSError, ValueError, TypeError, AttributeError, KeyError, zipfile.BadZipFile) as exc:
        return refuse(f"the spec cannot be built into a deck: {exc}")

    written["style"] = style
    template = spec.get("template")
    template_measured = None
    template_application = {"applied": False, "reason": "no template file declared"}
    if isinstance(template, dict) and template.get("file"):
        template_measured = T.measure(template["file"])
        try:
            template_application = _apply_template_if_requested(pptx, spec, template_measured)
        except (OSError, ValueError, TypeError, KeyError, zipfile.BadZipFile) as exc:
            template_application = {"applied": False, "reason": f"template application failed: {exc}"}

    try:
        audit = A.audit_deck(pptx, spec, image_aspects=_image_aspects(slides_spec, spec))
        measured_deck = T.measure(pptx)
        written["slide_size_emu"] = measured_deck.get("slide_size_emu")
        findings = list(audit["findings"])
        delivered_summary = deck_summary(slides_spec, pptx, written)
        if source_record:
            findings.extend(_source_findings(source_record))
        if template_measured is not None:
            findings.extend(T.audit(template_measured, spec, written.get("slide_size_emu"),
                                    delivered_summary))
        section = spec.get("section")
        if section:
            if not isinstance(section, str):
                return refuse("section must be a string")
            findings.extend(X.run(spec, section, delivered_summary))
        det = (check_deterministic(spec, out_dir) if template_measured is None
               else check_deterministic(spec, out_dir, template_measured))
        if not det["deterministic"]:
            findings.append({"rule": "repro.nondeterministic", "severity": "high",
                             "message": "two final builds differ in slide text, geometry or notes",
                             "detail": det["detail"]})
    except ValueError as exc:
        return refuse(str(exc))
    except (OSError, TypeError, AttributeError, KeyError, zipfile.BadZipFile) as exc:
        return refuse(f"the written deck could not be audited: {exc}")

    status, counts = _status(findings)
    preview = _render_preview(pptx, out_dir)
    if not preview.get("rendered"):
        limits.append("preview not rendered: " + str(preview.get("reason", "unknown")))
    if not audit["checked"].get("text_measured"):
        limits.append("text overflow was estimated, not measured: no usable font metrics")
    if template_measured is not None and not template_application.get("applied"):
        limits.append("template shell not applied: " + str(template_application.get("reason")))
    if source_record:
        for rec in source_record.get("records") or []:
            if rec.get("status") == "structural_record_only":
                limits.append("structural change retained in the ledger but not mechanically applied: "
                              f"slide {rec.get('slide')}")

    evidence_map = []
    for index, slide in enumerate(slides_spec, 1):
        if not isinstance(slide, dict):
            continue
        evidence_map.append({
            "slide": index, "title": slide.get("title") or "",
            "claim": slide.get("claim") or "", "strength": slide.get("strength"),
            "role": slide.get("role"), "strength_rationale": slide.get("strength_rationale"),
            "pace_minutes": slide.get("pace_minutes"), "takeaway": slide.get("takeaway"),
            "selection_reason": slide.get("selection_reason"),
            "evidence": slide.get("evidence") or "",
            "caption": slide.get("caption") or "", "notes_present": bool(slide.get("notes")),
        })
    uncertainty = spec.get("uncertainty", spec.get("pending_confirmation", []))
    if not isinstance(uncertainty, list):
        uncertainty = [str(uncertainty)]
    result = {
        "schema_version": "deckbuild/v3", "section": spec.get("section"),
        "status": status, "findings": findings, "severity_counts": counts,
        "deck": {"path": str(pptx), "slides": len(A.read_deck(pptx)),
                 "size_emu": written.get("slide_size_emu"), "spacing": spacing,
                 "fonts": written["fonts"], "source_deck": spec.get("source_deck"),
                 "style": style,
                 "template_applied": bool(template_application.get("applied"))},
        "evidence_map": evidence_map, "sources": evidence_map,
        "preview": preview, "reproducibility": det, "checked": audit["checked"],
        "template_measured": template_measured, "template_application": template_application,
        "source_record": source_record,
        "change_records": spec.get("revisions") or [], "uncertainty": uncertainty,
        "version_record": {"reproducibility": det, "source_record": source_record,
                           "delivered_revision": spec.get("delivered_revision"),
                           "change_records": spec.get("revisions") or []},
        "presentation_plan": {"goal": spec.get("goal"), "audience_plan": spec.get("audience_plan"),
                              "narrative": spec.get("narrative") or [],
                              "selection_ledger": spec.get("selection_ledger") or {},
                              "qa_prep": spec.get("qa_prep") or [],
                              "slides": evidence_map},
        "limits": limits,
        "artifacts": ([{"kind": "editable_presentation", "path": str(pptx)}]
                      + ([{"kind": "rendered_pdf", "path": preview["pdf"]}]
                         if preview.get("rendered") else [])),
    }
    if "presenter_notes" not in spec and any(
            isinstance(s, dict) and str(s.get("notes") or "").strip() for s in slides_spec):
        result["presenter_notes"] = [{"slide": i, "notes": str(s.get("notes") or "")}
                                     for i, s in enumerate(slides_spec, 1) if isinstance(s, dict)]
    if "qa_prep" in spec and "qa_ledger" not in spec:
        result["qa_ledger"] = spec.get("qa_prep") or []
    if isinstance(spec.get("goal"), dict) and spec["goal"].get("minutes") is not None:
        result["timing_plan"] = {
            "minutes": spec["goal"].get("minutes"), "qa_minutes": spec["goal"].get("qa_minutes"),
            "per_slide": [{"slide": i, "minutes": s.get("pace_minutes")}
                          for i, s in enumerate(slides_spec, 1) if isinstance(s, dict)]}
    if "selection_ledger" in spec:
        result["selection_ledger"] = spec.get("selection_ledger") or {}
    C.apply(result, spec, case if case or case_id is None else {"case_id": case_id})
    if case_id is not None:
        result["case_id"] = case_id
    try:
        (out_dir / "result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2),
                                             encoding="utf-8")
        (out_dir / "change_records.json").write_text(json.dumps(
            {"source_record": source_record, "delivered_revision": spec.get("delivered_revision"),
             "revisions": spec.get("revisions") or [], "reproducibility": det},
            ensure_ascii=False, indent=2), encoding="utf-8")
        (out_dir / "evidence_map.json").write_text(json.dumps(
            evidence_map, ensure_ascii=False, indent=2), encoding="utf-8")
        (out_dir / "presentation_plan.json").write_text(json.dumps(
            result["presentation_plan"], ensure_ascii=False, indent=2), encoding="utf-8")
    except OSError as exc:
        return refuse(f"result.json could not be written: {exc}")
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="deckbuild", description=__doc__)
    parser.add_argument("--spec", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--case", help="case.json supplying case_id/output_contract")
    parser.add_argument("--case-id", help="explicit case id, retained even on refusal")
    args = parser.parse_args(argv)
    try:
        result = build_and_audit(Path(args.spec), Path(args.out),
                                 case_path=Path(args.case) if args.case else None,
                                 case_id=args.case_id)
    except Exception as exc:  # external CLI boundary: never leak a traceback to the harness
        result = A.write_refused(args.out, f"unexpected engine boundary: {type(exc).__name__}: {exc}",
                                 case_id=args.case_id)
        emergency_case, _ = C.read_case(Path(args.case) if args.case else None)
        if emergency_case or args.case_id is not None:
            C.apply(result, {}, emergency_case if emergency_case else {"case_id": args.case_id})
            try:
                (Path(args.out) / "result.json").write_text(
                    json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
            except OSError:
                pass
    print(json.dumps({"status": result.get("status", "undetermined"),
                      "case_id": result.get("case_id"),
                      "findings": [f.get("rule") for f in result.get("findings", [])],
                      "slides": (result.get("deck") or {}).get("slides"),
                      "preview": (result.get("preview") or {}).get("rendered"),
                      "wrote": str(Path(args.out) / "result.json")}, ensure_ascii=False))
    return EXIT_CODES.get(result.get("status"), 5)


if __name__ == "__main__":
    raise SystemExit(main())
