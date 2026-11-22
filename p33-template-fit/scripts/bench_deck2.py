"""Benchmark for the polished template-fit skill.

Covers the template rules (size ladder, declared layouts), the deck hygiene rules, and
the things added in the polish passes: the declared typeface must exist, the text
must have glyphs, two builds must produce the same deck, and — against the written
deck — titles must keep the declared theme faces and one declared layout must keep
one title geometry, while declared content must actually land.

Three defects cannot be expressed in a spec — a missing typeface, a font without the
needed glyphs, and a non-reproducible build — so those inject them by patching and
restore afterwards. The drift and drop rules are proved on real .pptx files patched
after writing, with the unpatched two-content-slide build as their FP guard.

    python bench_deck2.py
"""

from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import deckaudit  # noqa: E402
import deckbuild  # noqa: E402
import extra_rules as X  # noqa: E402
import pptxgen as P  # noqa: E402

OUT = Path(__file__).resolve().parent / "_run_deck2"

BASE = {
    "section": "template_fit",
    "min_font_pt": 14,
    "max_bullets_per_slide": 5,
    "require_notes": True,
    "spacing": {"title": 32, "body": 20},
    "font_ea": "Microsoft YaHei",
    "font_latin": "Arial",
    "template": {"name": "conf-2026", "layouts": ["title", "content"]},
    "available_evidence": ["Fig. 3b, p.7"],
    "slides": [
        {"title": "多孔涂层加速吸收", "layout": "title", "claim": "问题：吸收速率是瓶颈",
         "evidence": "Fig. 3b, p.7", "notes": "引入问题，不读标题。"},
        {"title": "吸收速率提高 3 倍", "layout": "content", "claim": "涂层使吸收速率提高三倍",
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


def scen_ladder_flat():
    return d(spacing={"title": 22, "body": 20}), ["format.size_ladder_flat"]


def scen_undeclared_layout():
    s = d()
    s["slides"] = copy.deepcopy(BASE["slides"])
    s["slides"][1]["layout"] = "two-column"
    return s, ["format.undeclared_layout"]


def scen_overflow():
    """Long Chinese bullets at a large body size must be measured, not guessed."""
    s = d(spacing={"title": 32, "body": 44})
    s["slides"] = copy.deepcopy(BASE["slides"])
    s["slides"][1]["bullets"] = ["这是一段特意写得很长的中文正文，用来确认换行后的文本高度会"
                                 "超出文本框，而不是被按拉丁字体的宽度错误估算。"] * 5
    return s, ["text.overflow"]


def scen_font_too_small():
    return d(spacing={"title": 28, "body": 10}), ["text.font_too_small"]


def three_slides() -> dict:
    """BASE plus a second content slide, so the layout-group rules have a group."""
    s = copy.deepcopy(BASE)
    s["slides"] = copy.deepcopy(BASE["slides"])
    s["slides"].append({
        "title": "机制：界面能与扩散路径", "layout": "content",
        "claim": "涂层降低界面能并缩短扩散路径", "evidence": "Fig. 3b, p.7",
        "bullets": ["界面能下降 18%", "扩散路径缩短一半"],
        "notes": "机制只给两个数字，细节留到问答。"})
    return s


def scen_clean3():
    """Two content slides, unpatched: the FP guard for the drift and drop rules."""
    return three_slides(), []


SCEN = [
    ("clean", scen_clean),
    ("clean3", scen_clean3),
    ("ladder_flat", scen_ladder_flat),
    ("undeclared_layout", scen_undeclared_layout),
    ("overflow_cjk", scen_overflow),
    ("font_too_small", scen_font_too_small),
]


# --- artifact-level scenarios ---------------------------------------------------
# The template-fit section judges the written deck, so its drift and drop rules
# are proved on a real .pptx: build it, patch one part the way a hand-edited or
# half-adapted file looks (bench_deck.py's pattern), and run the section on the
# summary read back from the patched file.

def _patch_part(pptx: Path, part: str, edit) -> None:
    """Rewrite one XML part through the element tree, names registered."""
    import xml.etree.ElementTree as ET
    import zipfile
    a_ns = "http://schemas.openxmlformats.org/drawingml/2006/main"
    p_ns = "http://schemas.openxmlformats.org/presentationml/2006/main"
    ET.register_namespace("a", a_ns)
    ET.register_namespace("p", p_ns)
    tmp = pptx.with_suffix(".patched.pptx")
    with zipfile.ZipFile(pptx) as zin, zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as zout:
        for item in zin.namelist():
            data = zin.read(item)
            if item == part:
                root = ET.fromstring(data)
                edit(root, a_ns, p_ns)
                data = ET.tostring(root, encoding="utf-8", xml_declaration=True)
            zout.writestr(item, data)
    tmp.replace(pptx)


def _drop_last_body_para(root, a_ns: str, p_ns: str) -> None:
    """Remove one bullet paragraph — the missing-placeholder outcome: the layout
    holds and the material is simply not there."""
    for sp in root.iter("{%s}sp" % p_ns):
        cnv = sp.find(".//{%s}cNvPr" % p_ns)
        if cnv is None or cnv.get("name") != "Body":
            continue
        txbody = sp.find(".//{%s}txBody" % p_ns)
        paras = txbody.findall("{%s}p" % a_ns)
        if len(paras) >= 2:
            txbody.remove(paras[-1])


def _shift_title_box(root, a_ns: str, p_ns: str) -> None:
    """Move a content slide's title box — the page the adaptation never reached."""
    for sp in root.iter("{%s}sp" % p_ns):
        cnv = sp.find(".//{%s}cNvPr" % p_ns)
        if cnv is None or cnv.get("name") != "Title":
            continue
        off = sp.find(".//{%s}off" % a_ns)
        off.set("y", str(int(off.get("y")) + 320040))  # +0.35 in


def _retitle_font(root, a_ns: str, p_ns: str) -> None:
    """Set a title's typeface to one the declared theme does not name."""
    for sp in root.iter("{%s}sp" % p_ns):
        cnv = sp.find(".//{%s}cNvPr" % p_ns)
        if cnv is None or cnv.get("name") != "Title":
            continue
        for latin in sp.iter("{%s}latin" % a_ns):
            latin.set("typeface", "Times New Roman")


def artifact_scenario(name: str, spec: dict, edit, rule: str) -> tuple[dict, str]:
    """Build, patch slide 3, and run the template_fit section on the summary."""
    d = OUT / name
    d.mkdir(parents=True, exist_ok=True)
    pptx = d / "deck.pptx"
    written = P.write_deck(deckbuild.spec_slides(spec), pptx,
                           spacing=spec.get("spacing") or {"title": 32, "body": 20},
                           fonts=(spec.get("font_latin", P.DEFAULT_FONT_LATIN),
                                  spec.get("font_ea", P.DEFAULT_FONT_EA)))
    _patch_part(pptx, "ppt/slides/slide3.xml", edit)
    ds = deckbuild.deck_summary(spec.get("slides") or [], pptx, written)
    (d / "summary.json").write_text(json.dumps(ds, ensure_ascii=False, indent=2),
                                    encoding="utf-8")
    return X.run(spec, "template_fit", ds), rule


def injected_font_missing() -> tuple[dict, str]:
    """A declared typeface that is not installed anywhere."""
    saved = deckaudit._installed
    deckaudit._installed = lambda fam: fam.lower() != "fg-cjk-absent"
    try:
        r = run("font_missing", d(font_ea="FG-CJK-Absent"))
    finally:
        deckaudit._installed = saved
    return r, "font.declared_missing"


def injected_missing_glyphs() -> tuple[dict, str]:
    """A resolution that measured real coverage and found gaps: Latin-only image."""
    import fontsel
    saved = fontsel.resolve
    dj = fontsel._find(["DejaVuSans.ttf"])

    def partial(text: str = "") -> "fontsel.Resolved":
        real = fontsel.Resolved(family="DejaVu Sans", path=dj, measured=True,
                                missing=fontsel.coverage(dj, text))
        # Inject two glyphs no Latin face has, on top of whatever real gaps exist.
        missing = tuple(sorted(set(real.missing) | {"字", "形"}))
        return fontsel.Resolved(family="DejaVu Sans", path=dj, missing=missing,
                                measured=True)

    fontsel.resolve = partial
    try:
        r = run("glyphs", d())
    finally:
        fontsel.resolve = saved
    return r, "export.missing_glyphs"


def injected_unmeasurable_glyphs() -> tuple[dict, str]:
    """FP guard: coverage that could not be measured must NOT read as 'all missing'.

    Before the standard-library metrics reader this machine-without-matplotlib
    state reported every character as missing and blocked healthy decks; now
    the verdict is gated on `measured`.
    """
    import fontsel
    saved = fontsel.resolve
    fontsel.resolve = lambda text="": fontsel.Resolved(
        family="<none>", path=None, missing=tuple(sorted(set(text)))[:5], measured=False)
    try:
        r = run("glyphs_unmeasurable", d())
    finally:
        fontsel.resolve = saved
    return r, "__silent__"  # pass condition: export.missing_glyphs stayed silent


def injected_nondeterministic() -> tuple[dict, str]:
    saved = deckbuild.check_deterministic
    deckbuild.check_deterministic = lambda spec, out_dir: {
        "deterministic": False, "note": "injected", "detail": {"slides": 2}}
    try:
        r = run("nondet", d())
    finally:
        deckbuild.check_deterministic = saved
    return r, "repro.nondeterministic"


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
        print(f"{'PASS' if ok else 'FAIL'}  {name:<22} missing={missing} spurious={spurious}")

    for name, fn in (("font_missing", injected_font_missing),
                     ("missing_glyphs", injected_missing_glyphs),
                     ("nondeterministic", injected_nondeterministic),
                     ("unmeasurable_glyphs", injected_unmeasurable_glyphs)):
        r, rule = fn()
        fired = {f["rule"] for f in r["findings"]}
        if rule == "__silent__":
            ok = "export.missing_glyphs" not in fired
            expected = ["(no export.missing_glyphs)"]
        else:
            ok = rule in fired
            expected = [rule]
        rows.append({"scenario": name, "expected": expected,
                     "missing": [] if ok else expected, "spurious": [],
                     "pass": ok, "injected": True, "status": r["status"]})
        print(f"{'PASS' if ok else 'FAIL'}  {name:<22} injected={ok}")

    for name, edit, rule in (
            ("dropped_bullet_artifact", _drop_last_body_para, "format.content_dropped"),
            ("title_drift_artifact", _shift_title_box, "format.title_drift"),
            ("font_drift_artifact", _retitle_font, "format.font_drift")):
        findings, want = artifact_scenario(name, three_slides(), edit, rule)
        ok = want in {f["rule"] for f in findings}
        rows.append({"scenario": name, "expected": [want],
                     "missing": [] if ok else [want], "spurious": [],
                     "pass": ok, "artifact": True})
        print(f"{'PASS' if ok else 'FAIL'}  {name:<22} artifact={ok}")

    passed = sum(1 for x in rows if x["pass"])
    report = {"schema_version": "deck2-bench/v1", "scenarios": rows,
              "totals": {"passed": passed, "of": len(rows)},
              "note": ("Template rules plus declared-font existence, glyph coverage, build "
                       "determinism, and the written-deck drift/drop rules. Three scenarios "
                       "inject a defect into the engine, three patch the written .pptx.")}
    (Path(__file__).resolve().parent / "report_deck2.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n{passed}/{len(rows)} pass")
    return 0 if passed == len(rows) else 1


if __name__ == "__main__":
    raise SystemExit(main())
