"""Benchmark for the deck audit.

Each scenario writes a real .pptx, audits the written file, and names the rule
that must fire. The clean baseline must stay silent on high and medium findings,
so a detector cannot pass by flagging everything.

    python bench_deck.py
"""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import deckaudit as A  # noqa: E402
import pnggen  # noqa: E402
import pptxgen as P  # noqa: E402

FIG_DIR = Path(tempfile.mkdtemp())
FIG = FIG_DIR / "fig.png"
# The fixture image is generated with the standard-library PNG writer: the bench
# used to import Pillow here, which made the bench itself crash on machines
# without Pillow — the same missing-dependency failure the audit was hardened
# against, one layer down.
_im = pnggen.Canvas(600, 400)
_im.rect_outline(40, 40, 560, 360, color=(0, 0, 0), width=2)
_im.save(FIG)

SPEC = {
    "min_font_pt": 14,
    "max_bullets_per_slide": 6,
    "require_notes": True,
    "available_evidence": ["Fig. 3b, p.7", "Table 1, p.6"],
    "slides": [
        {"claim": "question", "evidence": "Fig. 3b, p.7"},
        {"claim": "finding", "evidence": "Fig. 3b, p.7"},
    ],
}


def deck(title="Uptake was 3x faster", bullets=None, notes="Pause; contrast rate not endpoint.",
         image=None, alt="uptake curves", spacing=None, first_notes="Frame the question."):
    slides = [
        P.Slide(title="Porous coatings accelerate uptake", caption="42 nm, 3x rate",
                layout="title", notes=first_notes),
        P.Slide(title=title, claim="finding",
                bullets=bullets if bullets is not None else
                        [P.Bullet("Control: 12.4 a.u."), P.Bullet("Coated: 31.2 a.u.")],
                image=image, image_alt=alt, caption="Fig. 3b, p.7",
                evidence="Fig. 3b, p.7", notes=notes),
    ]
    return slides, spacing or {"title": 32, "body": 20}


def scen_clean():
    s, sp = deck()
    return s, sp, SPEC, [], {}


def scen_too_many_bullets():
    s, sp = deck(bullets=[P.Bullet(f"point {i}") for i in range(9)])
    return s, sp, SPEC, ["deck.too_many_bullets"], {}


def scen_font_too_small():
    s, sp = deck(spacing={"title": 28, "body": 10})
    return s, sp, SPEC, ["text.font_too_small"], {}


def scen_overflow():
    long = ("This sentence is deliberately, relentlessly long so that the wrapped text block "
            "cannot fit inside the body rectangle at this font size, which is exactly the "
            "condition a presenter discovers only after the file has been opened on site. ") * 3
    s, sp = deck(bullets=[P.Bullet(long), P.Bullet(long)])
    return s, sp, SPEC, ["text.overflow"], {}


def scen_no_title():
    s, sp = deck(title="")
    return s, sp, SPEC, ["deck.no_title"], {}


def scen_evidence_missing():
    spec = json.loads(json.dumps(SPEC))
    spec["slides"][1]["evidence"] = ""
    s, sp = deck()
    return s, sp, spec, ["deck.evidence_missing"], {}


def scen_evidence_unsupported():
    spec = json.loads(json.dumps(SPEC))
    spec["slides"][1]["evidence"] = "Fig. 9z, p.44"
    s, sp = deck()
    return s, sp, spec, ["deck.evidence_unsupported"], {}


def scen_notes_missing():
    s, sp = deck(notes="")
    return s, sp, SPEC, ["deck.notes_missing"], {}


def scen_aspect_distorted():
    """The generator now fits images, so distortion can only come from outside.

    This scenario rewrites the picture extent inside the written file, which is
    exactly what a hand-edited or third-party deck does — the rule has to work on
    artifacts this tool did not produce.
    """
    s, sp = deck(image=str(FIG))
    return s, sp, SPEC, ["image.aspect_distorted"], {"uptake curves": 1.5}


def scen_no_alt_text():
    s, sp = deck(image=str(FIG), alt="")
    return s, sp, SPEC, ["image.no_alt_text"], {}


def scen_term_inconsistent():
    s, sp = deck(bullets=[P.Bullet("Signalling through the cascade was measured."),
                          P.Bullet("Signaling amplitude rose 3-fold.")])
    return s, sp, SPEC, ["text.term_inconsistent"], {}


SCENARIOS = [
    ("clean", scen_clean),
    ("too_many_bullets", scen_too_many_bullets),
    ("font_too_small", scen_font_too_small),
    ("overflow", scen_overflow),
    ("no_title", scen_no_title),
    ("evidence_missing", scen_evidence_missing),
    ("evidence_unsupported", scen_evidence_unsupported),
    ("notes_missing", scen_notes_missing),
    ("aspect_distorted", scen_aspect_distorted),
    ("no_alt_text", scen_no_alt_text),
    ("term_inconsistent", scen_term_inconsistent),
]


def run_one(name, builder, root: Path) -> dict:
    slides, spacing, spec, expect, aspects = builder()
    d = root / name
    d.mkdir(parents=True, exist_ok=True)
    out = d / "deck.pptx"
    P.write_deck(slides, out, spacing=spacing)
    if name == "aspect_distorted":
        # Distort the written picture through the XML tree rather than a regex:
        # the pic element carries namespace attributes, and string patterns
        # against namespaced XML are a reliable source of silent no-matches.
        import shutil
        import zipfile
        import xml.etree.ElementTree as _ET
        A_NS = "http://schemas.openxmlformats.org/drawingml/2006/main"
        P_NS = "http://schemas.openxmlformats.org/presentationml/2006/main"
        _ET.register_namespace("a", A_NS)
        _ET.register_namespace("p", P_NS)
        tmp = d / "stretched.pptx"
        with zipfile.ZipFile(out) as zin, zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as zout:
            for item in zin.namelist():
                data = zin.read(item)
                if item == "ppt/slides/slide2.xml":
                    root = _ET.fromstring(data)
                    pic = root.find(".//{%s}pic" % P_NS)
                    ext = pic.find(".//{%s}ext" % A_NS)
                    ext.set("cx", str(int(ext.get("cx")) * 2))   # aspect 1.5 -> 3.0
                    data = _ET.tostring(root, encoding="utf-8", xml_declaration=True)
                zout.writestr(item, data)
        shutil.move(tmp, out)
    r = A.audit_deck(out, spec, image_aspects=aspects)
    fired = {f["rule"] for f in r["findings"]}
    missing = [x for x in expect if x not in fired]
    spurious = []
    if not expect:
        spurious = [f["rule"] for f in r["findings"] if f["severity"] in ("high", "medium")]
    return {"scenario": name, "expected": expect, "fired": sorted(fired),
            "missing": missing, "spurious": spurious, "status": r["status"],
            "pass": not missing and not spurious}


def main() -> int:
    root = Path(__file__).resolve().parent / "_run"
    rows = [run_one(n, b, root) for n, b in SCENARIOS]
    passed = sum(1 for r in rows if r["pass"])
    report = {"schema_version": "deck-bench/v1", "scenarios": rows,
              "totals": {"passed": passed, "of": len(rows)},
              "note": ("Real .pptx written and re-read for every scenario. The clean baseline must "
                       "stay silent on high and medium findings.")}
    (Path(__file__).resolve().parent / "report_deck.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    for r in rows:
        print(f"{'PASS' if r['pass'] else 'FAIL'}  {r['scenario']:<20}"
              f"expected={r['expected']} missing={r['missing']} spurious={r['spurious']}")
    print(f"\n{passed}/{len(rows)} scenarios pass")
    return 0 if passed == len(rows) else 1


if __name__ == "__main__":
    raise SystemExit(main())
