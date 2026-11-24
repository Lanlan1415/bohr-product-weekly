"""Standard-library OOXML, provenance and geometry regression scenarios.

Run with `python -I -X utf8 scripts/bench_layout.py`.  Every case writes a real
PPTX, mutates the delivered XML where a defect is planted, and audits that file.
"""
from __future__ import annotations

import base64
import copy
import json
import sys
import zipfile
from pathlib import Path
import xml.etree.ElementTree as ET

SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS))
import deckaudit as A  # noqa: E402
import pptxgen as P  # noqa: E402

OUT = SCRIPTS / "_run_layout"
NS = {"a": A.NS["a"], "p": A.NS["p"]}
for prefix in ("a", "p"):
    ET.register_namespace(prefix, NS[prefix])

# Valid 1x1 transparent PNG generated in the temporary bench tree, not shipped
# as a binary skill resource. The engine only places it; no scientific claim is
# attached to this non-data smoke image.
PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVQIHWP4z8DwHwAFgAI/ScL9WQAAAABJRU5ErkJggg==")

BASE_SPEC = {
    "min_font_pt": 14,
    "max_bullets_per_slide": 6,
    "require_notes": True,
    "available_evidence": ["Fig. 3b, p.7"],
    "slides": [{"title": "吸收速率是瓶颈", "claim": "速率而非终点是未满足需求",
                "evidence": "Fig. 3b, p.7", "notes": "先界定问题，再转入方法。"}],
}


def _slide(*, bullets=("n = 6 per group",), evidence="Fig. 3b, p.7", image=None,
           caption="Fig. 3b, p.7 — measured uptake"):
    return P.Slide(title="吸收速率是瓶颈", claim="速率而非终点是未满足需求",
                   bullets=[P.Bullet(str(x)) for x in bullets], notes="先界定问题，再转入方法。",
                   evidence=evidence, image=image, image_alt="1x1 smoke image" if image else "",
                   caption=caption)


def _write(name: str, slide: P.Slide, spec: dict) -> Path:
    root = OUT / name
    root.mkdir(parents=True, exist_ok=True)
    path = root / "deck.pptx"
    P.write_deck([slide], path, spacing={"title": 32, "body": 20},
                 fonts=("Arial", "Microsoft YaHei"))
    (root / "spec.json").write_text(json.dumps(spec, ensure_ascii=False), encoding="utf-8")
    return path


def _mutate(path: Path, name: str, fn) -> None:
    temp = path.with_name(path.stem + "-mutated.pptx")
    with zipfile.ZipFile(path) as zin, zipfile.ZipFile(temp, "w", zipfile.ZIP_DEFLATED) as zout:
        for part in zin.namelist():
            data = zin.read(part)
            if part == name:
                root = ET.fromstring(data)
                fn(root)
                data = ET.tostring(root, encoding="utf-8", xml_declaration=True)
            zout.writestr(part, data)
    temp.replace(path)


def _title_outside(root: ET.Element) -> None:
    shape = root.find(".//p:sp", NS)
    off = shape.find("p:spPr/a:xfrm/a:off", NS)
    off.set("x", str(P.SLIDE_W + 1000))


def _picture_outside(root: ET.Element) -> None:
    off = root.find(".//p:pic/p:spPr/a:xfrm/a:off", NS)
    off.set("y", str(P.SLIDE_H + 1000))


def _body_on_title(root: ET.Element) -> None:
    shapes = root.findall(".//p:sp", NS)
    assert len(shapes) >= 2
    title_off = shapes[0].find("p:spPr/a:xfrm/a:off", NS)
    shape = next(s for s in shapes if (s.find(".//p:cNvPr", NS).get("name") == "Body"))
    off = shape.find("p:spPr/a:xfrm/a:off", NS)
    off.set("x", title_off.get("x"))
    off.set("y", title_off.get("y"))


def _white_on_white(root: ET.Element) -> None:
    csld = root.find("p:cSld", NS)
    bg = ET.Element(f"{{{NS['p']}}}bg")
    props = ET.SubElement(bg, f"{{{NS['p']}}}bgPr")
    fill = ET.SubElement(props, f"{{{NS['a']}}}solidFill")
    ET.SubElement(fill, f"{{{NS['a']}}}srgbClr", val="FFFFFF")
    ET.SubElement(props, f"{{{NS['a']}}}effectLst")
    csld.insert(0, bg)
    for rgb in root.findall(".//a:rPr/a:solidFill/a:srgbClr", NS):
        rgb.set("val", "FFFFFF")


def _scenarios():
    spec = copy.deepcopy(BASE_SPEC)
    path = _write("clean", _slide(), spec)
    yield "clean_geometry_provenance_contrast", path, spec, []

    spec = copy.deepcopy(BASE_SPEC)
    spec["slides"][0]["bullets"] = ["W" * 500]
    path = _write("horizontal_overflow", _slide(bullets=["W" * 500]), spec)
    yield "horizontal_unbreakable_token", path, spec, ["text.overflow"]

    spec = copy.deepcopy(BASE_SPEC)
    path = _write("text_outside_canvas", _slide(), spec)
    _mutate(path, "ppt/slides/slide1.xml", _title_outside)
    yield "text_outside_canvas", path, spec, ["shape.out_of_bounds"]

    spec = copy.deepcopy(BASE_SPEC)
    image = OUT / "smoke.png"
    image.parent.mkdir(parents=True, exist_ok=True)
    image.write_bytes(PNG)
    spec["slides"][0].update({"image": str(image), "image_alt": "1x1 smoke image",
                              "caption": "Fig. 3b, p.7 — measured uptake"})
    path = _write("picture_outside_canvas", _slide(image=str(image)), spec)
    _mutate(path, "ppt/slides/slide1.xml", _picture_outside)
    yield "picture_outside_canvas", path, spec, ["shape.out_of_bounds"]

    spec = copy.deepcopy(BASE_SPEC)
    path = _write("text_collision", _slide(), spec)
    _mutate(path, "ppt/slides/slide1.xml", _body_on_title)
    yield "text_collision", path, spec, ["shape.overlap"]

    spec = copy.deepcopy(BASE_SPEC)
    path = _write("low_contrast", _slide(), spec)
    _mutate(path, "ppt/slides/slide1.xml", _white_on_white)
    yield "low_contrast", path, spec, ["text.contrast_low"]

    # A third-party/manual deck may declare a source in its spec but have no
    # visible locator. The production generator writes one, so the clean case
    # above is also this rule's false-positive guard.
    spec = copy.deepcopy(BASE_SPEC)
    path = _write("evidence_not_landed", _slide(evidence="", caption=""), spec)
    yield "evidence_not_landed", path, spec, ["deck.evidence_not_landed"]


def main() -> int:
    reports = []
    for name, path, spec, expected in _scenarios():
        result = A.audit_deck(path, spec)
        fired = {row["rule"] for row in result["findings"]}
        missing = sorted(set(expected) - fired)
        spurious = [] if expected else sorted(fired)
        extra_ok = True
        detail = {}
        if not expected:
            with zipfile.ZipFile(path) as z:
                root = ET.fromstring(z.read("ppt/slides/slide1.xml"))
                body_props = root.findall(".//p:sp/p:txBody/a:bodyPr", NS)
                extra_ok = bool(body_props) and all(
                    p.find("a:noAutofit", NS) is not None for p in body_props)
                extra_ok = extra_ok and bad_zip(z) is None
            visible = "\n".join(p["text"] for sl in A.read_deck(path)
                                for sh in sl["shapes"] for p in sh["paras"])
            extra_ok = extra_ok and "Fig. 3b, p.7" in visible
            extra_ok = extra_ok and result["checked"]["contrast_checks"] > 0
            detail = {"noAutofit": extra_ok, "contrast_checks": result["checked"]["contrast_checks"]}
        ok = not missing and not spurious and extra_ok
        reports.append({"scenario": name, "expected": expected, "fired": sorted(fired),
                        "missing": missing, "spurious": spurious, "detail": detail,
                        "pass": ok})
        print(f"{'PASS' if ok else 'FAIL'}  {name:<38} missing={missing} spurious={spurious}")
    passed = sum(1 for row in reports if row["pass"])
    (SCRIPTS / "report_layout.json").write_text(json.dumps({
        "schema_version": "ppt-master-layout-bench/v1", "scenarios": reports,
        "totals": {"passed": passed, "of": len(reports)}}, ensure_ascii=False, indent=2),
        encoding="utf-8")
    print(f"\n{passed}/{len(reports)} scenarios pass")
    return 0 if passed == len(reports) else 1


def bad_zip(z: zipfile.ZipFile):
    return z.testzip()


if __name__ == "__main__":
    raise SystemExit(main())
