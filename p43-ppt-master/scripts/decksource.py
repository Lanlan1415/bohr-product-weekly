"""Inspect and text-edit a real starting PPTX without discarding its package.

The router's editing path must preserve the organizer's masters, layouts, media,
and embedded objects.  This module therefore patches only DrawingML paragraphs
in a copy of the source package.  It never rebuilds a source deck from memory.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import zipfile
from pathlib import Path
import xml.etree.ElementTree as ET

A = "http://schemas.openxmlformats.org/drawingml/2006/main"
P = "http://schemas.openxmlformats.org/presentationml/2006/main"
NS = {"a": A, "p": P}
ET.register_namespace("a", A)
ET.register_namespace("p", P)


def sha256(path: str | Path) -> str:
    h = hashlib.sha256()
    with Path(path).open("rb") as fh:
        for block in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def _slide_parts(z: zipfile.ZipFile) -> list[str]:
    return sorted(
        (n for n in z.namelist() if re.fullmatch(r"ppt/slides/slide\d+\.xml", n)),
        key=lambda n: int(re.search(r"(\d+)", n.rsplit("/", 1)[-1]).group(1)),
    )


def _texts(root: ET.Element) -> list[str]:
    return [t.text or "" for t in root.iter(f"{{{A}}}t")]


def inspect(path: str | Path) -> dict:
    """Return an honest extraction skeleton; claims/evidence remain for the agent."""
    path = Path(path)
    out = {"source_deck": str(path), "read": False, "slides": [], "limits": []}
    try:
        with zipfile.ZipFile(path) as z:
            parts = _slide_parts(z)
            if "ppt/presentation.xml" not in z.namelist():
                raise ValueError("ppt/presentation.xml is missing")
            for index, part in enumerate(parts, 1):
                root = ET.fromstring(z.read(part))
                text = "\n".join(t for t in _texts(root) if t.strip())
                notes_part = f"ppt/notesSlides/notesSlide{index}.xml"
                notes = ""
                if notes_part in z.namelist():
                    notes = "\n".join(_texts(ET.fromstring(z.read(notes_part))))
                lines = [line for line in text.splitlines() if line.strip()]
                out["slides"].append({
                    "title": lines[0] if lines else "",
                    "layout": "content",
                    "claim": "",
                    "evidence": "",
                    "bullets": lines[1:],
                    "notes": notes,
                })
            out["read"] = True
            out["sha256"] = sha256(path)
            out["slide_count"] = len(parts)
            if not parts:
                out["limits"].append("source deck contains no slides")
    except (OSError, zipfile.BadZipFile, ET.ParseError, ValueError) as exc:
        out["error"] = str(exc)
        out["limits"].append("source deck could not be parsed; no content was inferred")
    return out


def _ordered_revisions(spec: dict) -> list[dict]:
    revisions = list(spec.get("revisions") or [])
    pointer = spec.get("delivered_revision")
    if pointer is None:
        return revisions
    for pos, rev in enumerate(revisions, 1):
        try:
            match = int(pointer) in (pos, int(rev.get("n")))
        except (TypeError, ValueError):
            match = int(pointer) == pos
        if match:
            return revisions[:pos]
    return revisions


def _replace_in_part(data: bytes, before: str, after: str) -> tuple[bytes, int]:
    """Replace across split runs while retaining the first run's formatting."""
    root = ET.fromstring(data)
    replacements = 0
    for para in root.iter(f"{{{A}}}p"):
        nodes = list(para.iter(f"{{{A}}}t"))
        if not nodes:
            continue
        joined = "".join(node.text or "" for node in nodes)
        if before not in joined:
            continue
        updated = joined.replace(before, after, 1)
        nodes[0].text = updated
        for node in nodes[1:]:
            node.text = ""
        replacements += 1
    if not replacements:
        return data, 0
    return ET.tostring(root, encoding="utf-8", xml_declaration=True), replacements


def _already_in_part(data: bytes, after: str) -> bool:
    if not after:
        return False
    try:
        root = ET.fromstring(data)
    except ET.ParseError:
        return False
    return any(after in "".join(t.text or "" for t in para.iter(f"{{{A}}}t"))
               for para in root.iter(f"{{{A}}}p"))


def apply_changes(source: str | Path, output: str | Path, spec: dict) -> dict:
    """Apply revisions through the delivered pointer and preserve every other part.

    Each change becomes an execution record: applied, already_present, unsupported,
    or before_missing.  The caller turns before_missing into edit.before_not_in_source.
    """
    source, output = Path(source), Path(output)
    with zipfile.ZipFile(source) as zin:
        original = {name: zin.read(name) for name in zin.namelist()}
    parts = dict(original)
    records: list[dict] = []
    revisions = _ordered_revisions(spec)
    for rpos, rev in enumerate(revisions, 1):
        for cpos, change in enumerate(rev.get("changes") or [], 1):
            rec = {"revision": rev.get("n", rpos), "change": cpos,
                   "slide": change.get("slide"), "status": "unsupported"}
            records.append(rec)
            if "before" not in change or "after" not in change:
                rec["status"] = "structural_record_only"
                continue
            try:
                slide = int(change.get("slide"))
            except (TypeError, ValueError):
                rec["status"] = "invalid_slide"
                continue
            before, after = str(change.get("before") or ""), str(change.get("after") or "")
            if not before:
                rec["status"] = "before_missing"
                continue
            target = str(change.get("target") or "slide").lower()
            part = (f"ppt/notesSlides/notesSlide{slide}.xml" if target == "notes"
                    else f"ppt/slides/slide{slide}.xml")
            data = parts.get(part)
            if data is None:
                rec["status"] = "invalid_slide"
                continue
            try:
                updated, count = _replace_in_part(data, before, after)
            except ET.ParseError:
                rec["status"] = "malformed_xml"
                continue
            if count:
                parts[part] = updated
                rec["status"] = "applied"
                rec["replacements"] = count
            elif _already_in_part(data, after):
                rec["status"] = "already_present"
            else:
                rec["status"] = "before_missing"
    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as zout:
        for name, data in parts.items():
            zout.writestr(name, data)
    return {"source": str(source), "source_sha256": sha256(source),
            "output": str(output), "output_sha256": sha256(output),
            "package_preserved": set(parts) == set(original), "records": records}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--source", required=True)
    ap.add_argument("--out", required=True, help="JSON extraction skeleton, not a result.json")
    args = ap.parse_args(argv)
    report = inspect(args.source)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"read": report["read"], "slides": len(report["slides"]), "wrote": str(out)},
                     ensure_ascii=False))
    return 0 if report["read"] else 5


if __name__ == "__main__":
    raise SystemExit(main())
