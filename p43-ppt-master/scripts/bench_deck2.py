"""Benchmark for the polished deck-edit skill.

Covers the revision rules (every change names its slide and its reason, carries a
complete before/after pair or a deletion snapshot, and points at a slide the deck
actually contains), Chinese text measurement, and the polish-pass additions: the
declared typeface must exist, the text must have glyphs, and two builds must
produce the same deck.

The artifact-level additions patch a real written package, which is the only way
to express the defect: a slide whose layout relationship was lost, a deck whose
halves sit on different masters, and a declared font embedding that the package
does not carry. Each defect ships with its false-positive guard (Lesson 6): the
same patch that keeps the master chain intact, and a package that really does
carry its embedded fonts, must stay silent.

    python bench_deck2.py
"""

from __future__ import annotations

import copy
import json
import shutil
import sys
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import deckaudit as A  # noqa: E402
import deckbuild  # noqa: E402
import pptxgen as P  # noqa: E402

OUT = Path(__file__).resolve().parent / "_run_edit2"

BASE = {
    "section": "deck_edit",
    "min_font_pt": 14,
    "max_bullets_per_slide": 5,
    "require_notes": True,
    "spacing": {"title": 32, "body": 20},
    "font_ea": "Microsoft YaHei",
    "font_latin": "Arial",
    "available_evidence": ["Fig. 3b, p.7"],
    "revisions": [
        {"n": 2, "instruction": "压缩到十分钟", "changes": [
            {"slide": 2, "before": "吸收速率明显提高",
             "after": "吸收速率提高 3 倍",
             "reason": "把模糊的程度词换成实测倍数"}]}
    ],
    "slides": [
        {"title": "多孔涂层加速吸收", "layout": "title", "claim": "吸收速率是瓶颈",
         "evidence": "Fig. 3b, p.7", "notes": "引入问题，不读标题。"},
        {"title": "吸收速率提高 3 倍", "claim": "涂层使速率提高三倍",
         "evidence": "Fig. 3b, p.7",
         "bullets": ["对照组 12.4 a.u.", "涂层组 31.2 a.u.", "每组 n = 6"],
         "notes": "停顿；对比的是速率，不是终点。"},
    ],
}


def d(**over):
    s = copy.deepcopy(BASE)
    s.update(over)
    return s


def run(name: str, spec: dict) -> dict:
    p = OUT / name
    p.mkdir(parents=True, exist_ok=True)
    (p / "spec.json").write_text(json.dumps(spec, ensure_ascii=False), encoding="utf-8")
    return deckbuild.build_and_audit(p / "spec.json", p / "o")


def scen_clean():
    return d(), []


def scen_no_reason():
    s = d()
    s["revisions"] = copy.deepcopy(BASE["revisions"])
    s["revisions"][0]["changes"][0]["reason"] = ""
    return s, ["edit.change_without_reason"]


def scen_no_slide():
    s = d()
    s["revisions"] = copy.deepcopy(BASE["revisions"])
    s["revisions"][0]["changes"][0].pop("slide")
    return s, ["edit.change_without_slide"]


def scen_noop():
    s = d()
    s["revisions"] = copy.deepcopy(BASE["revisions"])
    s["revisions"][0]["changes"][0]["after"] = BASE["revisions"][0]["changes"][0]["before"]
    return s, ["edit.change_is_noop"]


def scen_revision_empty():
    s = d()
    s["revisions"] = [{"n": 3, "instruction": "无改动", "changes": []}]
    return s, ["edit.revision_without_changes"]


def scen_overflow_cjk():
    """Long Chinese bullets must be measured with CJK line breaking, not one line."""
    s = d(spacing={"title": 32, "body": 44})
    s["slides"] = copy.deepcopy(BASE["slides"])
    s["slides"][1]["bullets"] = ["这是一段特意写得很长的中文正文，用来确认换行后的文本高度会"
                                 "超出文本框，而不是被当成一行来估算。"] * 5
    return s, ["text.overflow"]


def scen_term_drift():
    s = d()
    s["slides"] = copy.deepcopy(BASE["slides"])
    s["slides"][1]["bullets"] = ["对照组的 signalling 通路", "涂层组的 signaling 通路"]
    return s, ["text.term_inconsistent"]


def scen_record_not_applied():
    """The record must be the change that was made.

    The recorded new text never landed in the named slide or its notes; the
    builder hands the written deck to the section, so the full pipeline catches
    it — not just a hand-built summary.
    """
    s = d()
    s["revisions"] = copy.deepcopy(BASE["revisions"])
    s["revisions"][0]["changes"][0]["after"] = "这行文字从未被写进任何一页"
    return s, ["edit.change_not_in_deck"]


SCEN = [
    ("clean", scen_clean),
    ("no_reason", scen_no_reason),
    ("no_slide", scen_no_slide),
    ("noop_change", scen_noop),
    ("revision_empty", scen_revision_empty),
    ("record_not_applied", scen_record_not_applied),
    ("overflow_cjk", scen_overflow_cjk),
    ("term_drift", scen_term_drift),
]


def injected_font_missing() -> tuple[dict, str]:
    saved = A._installed
    A._installed = lambda fam: fam.lower() != "fg-cjk-absent"
    try:
        r = run("font_missing", d(font_ea="FG-CJK-Absent"))
    finally:
        A._installed = saved
    return r, "font.declared_missing"


def injected_missing_glyphs() -> tuple[dict, str]:
    import fontsel
    saved = fontsel.resolve
    dj = fontsel._find(["DejaVuSans.ttf"])
    fontsel.resolve = lambda text="": fontsel.Resolved(
        family="DejaVu Sans", path=dj, missing=fontsel.coverage(dj, text))
    try:
        r = run("glyphs", d())
    finally:
        fontsel.resolve = saved
    return r, "export.missing_glyphs"


def injected_nondeterministic() -> tuple[dict, str]:
    saved = deckbuild.check_deterministic
    deckbuild.check_deterministic = lambda spec, out_dir: {
        "deterministic": False, "note": "injected", "detail": {"slides": 2}}
    try:
        r = run("nondet", d())
    finally:
        deckbuild.check_deterministic = saved
    return r, "repro.nondeterministic"


# --- artifact scenarios: patch a written package --------------------------------
# The master-chain and embedding defects cannot be expressed in a spec either —
# they are damages done to a real package after (or while) it is written, so the
# bench patches the written file the way a careless edit would, and its guards
# patch the same file the way a correct edit would.

def _patch_pptx(path: Path, parts: dict) -> None:
    """Rewrite a package in place. None drops the part; a string replaces or adds it."""
    tmp = path.with_name(path.stem + "_patch.pptx")
    with zipfile.ZipFile(path) as zin, zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as zout:
        for item in zin.namelist():
            if item in parts:
                data = parts[item]
                if data is not None:
                    zout.writestr(item, data)
            else:
                zout.writestr(item, zin.read(item))
        for item, data in parts.items():
            if item not in zin.namelist() and data is not None:
                zout.writestr(item, data)
    shutil.move(tmp, path)


def _build(name: str, spec: dict) -> Path:
    p = OUT / name
    p.mkdir(parents=True, exist_ok=True)
    pptx = p / "deck.pptx"
    P.write_deck(deckbuild.spec_slides(spec), pptx,
                 spacing=spec.get("spacing") or {"title": 32, "body": 20},
                 fonts=(spec.get("font_latin", P.DEFAULT_FONT_LATIN),
                        spec.get("font_ea", P.DEFAULT_FONT_EA)))
    return pptx


def _slide_rels(*entries: str) -> str:
    body = "".join(e.replace("RIDSLOT", f'rId{i + 1}') for i, e in enumerate(entries))
    return ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            + body + "</Relationships>")


REL_LAYOUT = ('<Relationship Id="RIDSLOT" Type="http://schemas.openxmlformats.org/'
              'officeDocument/2006/relationships/slideLayout" '
              'Target="../slideLayouts/slideLayout%s.xml"/>')
REL_NOTES = ('<Relationship Id="RIDSLOT" Type="http://schemas.openxmlformats.org/'
             'officeDocument/2006/relationships/notesSlide" '
             'Target="../notesSlides/notesSlide2.xml"/>')


def artifact_master_broken() -> tuple[dict, list[str]]:
    # Slide 2 loses its layout relationship: it inherits no master, theme or
    # placeholder geometry — the signature of an edit that broke the structure.
    spec = d()
    pptx = _build("master_broken", spec)
    _patch_pptx(pptx, {"ppt/slides/_rels/slide2.xml.rels": _slide_rels(REL_NOTES)})
    return A.audit_deck(pptx, spec), ["master.layout_missing"]


def artifact_master_shared_layout_fp() -> tuple[dict, list[str]]:
    # The guard: a second layout that still belongs to the one master is a
    # legitimate package — every slide resolves to the same master, so nothing
    # fires.
    spec = d()
    pptx = _build("master_shared_fp", spec)
    _patch_pptx(pptx, {
        "ppt/slideLayouts/slideLayout2.xml": P.LAYOUT,
        "ppt/slideLayouts/_rels/slideLayout2.xml.rels": P.LAYOUT_RELS,
        "ppt/slides/_rels/slide2.xml.rels": _slide_rels(REL_LAYOUT % "2", REL_NOTES),
    })
    return A.audit_deck(pptx, spec), []


def artifact_master_inconsistent() -> tuple[dict, list[str]]:
    # A second master that only the later half of the deck sits on: the edit was
    # supposed to touch one page and reached the template behind the rest.
    spec = d()
    pptx = _build("master_inconsistent", spec)
    _patch_pptx(pptx, {
        "ppt/slideMasters/slideMaster2.xml": P.MASTER,
        "ppt/slideLayouts/slideLayout2.xml": P.LAYOUT,
        "ppt/slideLayouts/_rels/slideLayout2.xml.rels": P.LAYOUT_RELS.replace(
            "slideMaster1", "slideMaster2"),
        "ppt/slides/_rels/slide2.xml.rels": _slide_rels(REL_LAYOUT % "2", REL_NOTES),
    })
    return A.audit_deck(pptx, spec), ["master.inconsistent"]


def artifact_embed_missing() -> tuple[dict, list[str]]:
    # The workflow declares embedded fonts; the package ships none, so the first
    # machine without the typeface substitutes it and the export reflows.
    spec = d(embed_fonts=True)
    pptx = _build("embed_missing", spec)
    return A.audit_deck(pptx, spec), ["embed.missing"]


def artifact_embed_fp_embedded() -> tuple[dict, list[str]]:
    # The guard: the same declaration against a package that really carries the
    # embedded font parts must stay silent.
    spec = d(embed_fonts=True)
    pptx = _build("embed_fp", spec)
    _patch_pptx(pptx, {"ppt/fonts/font1.fntdata": "fntdata placeholder (bench)"})
    return A.audit_deck(pptx, spec), []


def main() -> int:
    rows = []
    for name, builder in SCEN:
        spec, expect = builder()
        r = run(name, spec)
        fired = {f["rule"] for f in r["findings"]}
        missing = [x for x in expect if x not in fired]
        spurious = [] if expect else [f["rule"] for f in r["findings"]]
        ok = not missing and not spurious
        rows.append({"scenario": name, "expected": expect, "fired": sorted(fired),
                     "missing": missing, "spurious": spurious, "pass": ok,
                     "status": r["status"]})
        print(f"{'PASS' if ok else 'FAIL'}  {name:<20} missing={missing} spurious={spurious}")

    for name, fn in (("font_missing", injected_font_missing),
                     ("missing_glyphs", injected_missing_glyphs),
                     ("nondeterministic", injected_nondeterministic)):
        r, rule = fn()
        ok = rule in {f["rule"] for f in r["findings"]}
        rows.append({"scenario": name, "expected": [rule],
                     "missing": [] if ok else [rule], "spurious": [],
                     "pass": ok, "injected": True, "status": r["status"]})
        print(f"{'PASS' if ok else 'FAIL'}  {name:<20} injected={ok}")

    for name, fn in (("master_broken", artifact_master_broken),
                     ("master_shared_fp", artifact_master_shared_layout_fp),
                     ("master_inconsistent", artifact_master_inconsistent),
                     ("embed_missing", artifact_embed_missing),
                     ("embed_fp_embedded", artifact_embed_fp_embedded)):
        r, expect = fn()
        fired = {f["rule"] for f in r["findings"]}
        missing = [x for x in expect if x not in fired]
        spurious = [] if expect else [f["rule"] for f in r["findings"]]
        ok = not missing and not spurious
        rows.append({"scenario": name, "expected": expect, "fired": sorted(fired),
                     "missing": missing, "spurious": spurious, "pass": ok,
                     "patched": True, "status": r["status"]})
        print(f"{'PASS' if ok else 'FAIL'}  {name:<20} patched={ok}")

    passed = sum(1 for x in rows if x["pass"])
    report = {"schema_version": "deck-edit-bench/v1", "scenarios": rows,
              "totals": {"passed": passed, "of": len(rows)},
              "note": ("Revision rules plus CJK measurement, declared-font existence, glyph "
                       "coverage, build determinism, the master chain behind every slide and "
                       "declared font embedding. Three scenarios inject a defect and five "
                       "patch the written package.")}
    (Path(__file__).resolve().parent / "report_deck2.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n{passed}/{len(rows)} pass")
    return 0 if passed == len(rows) else 1


if __name__ == "__main__":
    raise SystemExit(main())
