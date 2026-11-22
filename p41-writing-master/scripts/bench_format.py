"""Benchmark for the format-and-template adaptation skill.

One scenario per rule, aligned to the scoring points this task states:

  the format spec is met AND the content is unchanged  -> spec_*, content_*
  headings bound to styles, TOC generated              -> heading_style_unbound, toc_not_generated
  every template check and content unit covered        -> checklist_incomplete, unit_*
  the input-to-output path is reproducible             -> conversion_undocumented, export_*

    python bench_format.py
"""

from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import writing as W  # noqa: E402

BASE = {
    "text": "1 Introduction\nWe study it [a1].\n2 Methods\nWe use 3 mM [a2].\n"
            "3 Results\nIt works [a3].\n",
    "template": {
        "sections": ["introduction", "methods", "results"],
        "word_limit": 4000,
        "spec": {"font": "Times New Roman", "size_pt": 11, "line_spacing": 1.5,
                 "margin_mm": 25, "columns": 1, "caption_position": "below",
                 "reference_style": "APA", "heading_levels": 3, "export_format": "docx"},
        "checks": ["margins", "caption_position", "reference_style"],
    },
    "headings": [
        {"level": 1, "number": "1", "text": "Introduction", "style": "Heading 1"},
        {"level": 1, "number": "2", "text": "Methods", "style": "Heading 1"},
        {"level": 1, "number": "3", "text": "Results", "style": "Heading 1"},
    ],
    "input_units": {"figures": 2, "tables": 1, "equations": 3, "footnotes": 4},
    "output_units": {"figures": 2, "tables": 1, "equations": 3, "footnotes": 4},
    "conversion_steps": ["open in Word", "apply template styles", "export to PDF"],
    "export": {"format": "pdf", "font_embedded": True, "page_size_measured": True,
               "toc_refreshed": True, "editable": True},
    "checks_done": ["margins", "caption_position", "reference_style"],
    "references": [{"key": "a1"}, {"key": "a2"}, {"key": "a3"}],
}


def d(**over):
    s = copy.deepcopy(BASE)
    s.update(over)
    return s


def d2(base, **over):
    """Override a composed baseline (e.g. tmpl(...) output) with top-level keys."""
    s = copy.deepcopy(base)
    s.update(over)
    return s


def tmpl(**over):
    s = copy.deepcopy(BASE)
    s["template"] = {**copy.deepcopy(BASE["template"]), **over}
    return s


def heading(i, **over):
    s = copy.deepcopy(BASE)
    s["headings"] = copy.deepcopy(BASE["headings"])
    s["headings"][i] = {**BASE["headings"][i], **over}
    return s


SCEN = [
    ("clean", lambda: (d(), [])),

    # the format spec
    ("spec_missing", lambda: (tmpl(spec={}), ["fmt.spec_missing"])),
    ("spec_value_missing",
     lambda: (tmpl(spec={k: v for k, v in BASE["template"]["spec"].items()
                        if k != "line_spacing"}), ["fmt.spec_value_missing"])),

    # structure and headings
    ("section_missing",
     lambda: (d(text="1 Introduction\nWe study it [a1].\n2 Methods\nWe use 3 mM [a2].\n"),
              ["fmt.section_missing"])),
    ("section_order",
     lambda: (d(text="1 Methods\nWe use 3 mM [a2].\n2 Introduction\nIt works [a1].\n"
                     "3 Results\nOk [a3].\n"),
              ["fmt.section_order"])),
    ("heading_level_skip",
     lambda: (d(headings=[
         {"level": 1, "number": "1", "text": "Introduction", "style": "Heading 1"},
         {"level": 3, "number": "1.1.1", "text": "Deep sub", "style": "Heading 3"},
         {"level": 1, "number": "2", "text": "Methods", "style": "Heading 1"},
         {"level": 1, "number": "3", "text": "Results", "style": "Heading 1"}]),
         ["fmt.heading_level_skip"])),
    ("heading_style_unbound",
     lambda: (heading(1, style=""), ["fmt.heading_style_unbound"])),
    ("toc_not_generated",
     lambda: (d(toc_expected=True, toc_generated=False), ["fmt.toc_not_generated"])),
    ("word_limit",
     lambda: (tmpl(word_limit=5), ["fmt.word_limit_exceeded"])),

    # references
    ("cite_ghost",
     lambda: (d(text="1 Introduction\nWe study it [a9].\n2 Methods\nWe use 3 mM [a2].\n"
                     "3 Results\nIt works [a3].\n"),
              ["fmt.citation_not_in_reference_list"])),
    ("ref_uncited",
     lambda: (d(references=[{"key": "a1"}, {"key": "a2"}, {"key": "a3"}, {"key": "a4"}]),
              ["fmt.reference_never_cited"])),
    ("reference_style_missing",
     lambda: (tmpl(spec={**BASE["template"]["spec"], "reference_style": ""}),
              ["fmt.reference_style_missing"])),

    # content must survive
    ("unit_lost",
     lambda: (d(output_units={"figures": 2, "tables": 1, "equations": 3, "footnotes": 2}),
              ["fmt.unit_lost"])),
    ("unit_added",
     lambda: (d(output_units={"figures": 3, "tables": 1, "equations": 3, "footnotes": 4}),
              ["fmt.unit_added"])),
    ("unit_counts_incomplete",
     lambda: (d(output_units={}), ["fmt.unit_counts_incomplete"])),

    # conversion and export
    ("conversion_undocumented",
     lambda: (d(conversion_steps=[]), ["fmt.conversion_undocumented"])),
    ("export_unverified", lambda: (d(export={}), ["fmt.export_unverified"])),
    ("font_not_embedded",
     lambda: (d(export={**BASE["export"], "font_embedded": False}), ["fmt.font_not_embedded"])),
    ("toc_not_refreshed",
     lambda: (d(export={**BASE["export"], "toc_refreshed": False}), ["fmt.toc_not_refreshed"])),
    ("not_editable",
     lambda: (d(export={**BASE["export"], "editable": False}), ["fmt.not_editable"])),
    ("export_field_missing",
     lambda: (d(export={k: v for k, v in BASE["export"].items() if k != "page_size_measured"}),
              ["fmt.export_field_missing"])),

    # the template checklist
    ("checklist_incomplete",
     lambda: (d(checks_done=["margins"]), ["fmt.checklist_incomplete"])),

    # cross-references (排得对)
    ("crossref_dangling", lambda: (d(figures=[{"number": 1}],
                                     text=BASE["text"] + " 见图5。"), ["fmt.crossref_dangling"])),
    ("figure_never_referenced",
     lambda: (d(figures=[{"number": 1}, {"number": 2}]), ["fmt.figure_never_referenced"])),
    ("content_rasterized",
     lambda: (d(export={**BASE["export"], "rasterized": True}), ["fmt.content_rasterized"])),
    # false-positive guards: every figure cited, or none declared, stays silent
    ("fp_crossrefs_ok", lambda: (d(figures=[{"number": 1}, {"number": 2}],
                                   text=BASE["text"] + " 见图1与图2，表2。"), [])),

    # header/footer (排得对): checked only when the template spec declares it
    ("header_footer_unverified",
     lambda: (tmpl(spec={**BASE["template"]["spec"],
                         "header_footer": {"header": "论文标题", "footer": "页码"}}),
              ["fmt.header_footer_unverified"])),
    # FP guard: declared items all recorded as set -> silent
    ("fp_header_footer_recorded",
     lambda: (d2(tmpl(spec={**BASE["template"]["spec"],
                            "header_footer": {"header": "论文标题", "footer": "页码"}}),
                 header_footer_applied={"header": "论文标题", "footer": "第 X 页 共 Y 页"}), [])),
    # FP guard: an explicit "not set" mark is the honest answer the task accepts
    ("fp_header_footer_notset",
     lambda: (d2(tmpl(spec={**BASE["template"]["spec"],
                            "header_footer": {"header": "论文标题", "footer": "页码"}}),
                 header_footer_status={"header": "论文标题", "footer": "not set"}), [])),

    # conflicting template provisions (模板版本差异): declared -> adopted required
    ("conflict_unresolved",
     lambda: (tmpl(conflicts=[{"topic": "正文字号", "version_2019": "小四",
                               "version_2021": "五号"}]),
              ["fmt.conflict_unresolved"])),
    # FP guard: the adopted version is recorded -> silent
    ("fp_conflict_adopted",
     lambda: (tmpl(conflicts=[{"topic": "正文字号", "version_2019": "小四",
                               "version_2021": "五号"}],
                    adopted="按 2021 版执行：正文五号"), [])),

    # page numbers (交得出): declared -> export confirmation required
    ("page_numbers_unverified", lambda: (d(page_numbers=True),
                                         ["fmt.page_numbers_unverified"])),
    ("page_numbers_reported_false",
     lambda: (d(page_numbers=True,
                export={**BASE["export"], "page_numbers_ok": False}),
              ["fmt.page_numbers_unverified"])),
    # the template side can declare it too
    ("page_numbers_spec_declared",
     lambda: (tmpl(spec={**BASE["template"]["spec"], "page_numbers": "bottom center"}),
              ["fmt.page_numbers_unverified"])),
    # FP guards: confirmation present -> silent; undeclared -> silent
    ("fp_page_numbers_ok",
     lambda: (d(page_numbers=True,
                export={**BASE["export"], "page_numbers_ok": True}), [])),
    ("fp_page_numbers_undeclared",
     lambda: (d(export={**BASE["export"], "format": "docx"}), [])),
]


def main() -> int:
    rows = []
    for name, builder in SCEN:
        spec, expect = builder()
        findings, status, counts = W.run(spec, "format_template")
        fired = {f["rule"] for f in findings}
        missing = [r for r in expect if r not in fired]
        spurious = [] if expect else [f["rule"] for f in findings]
        ok = not missing and not spurious
        rows.append({"scenario": name, "expected": expect, "fired": sorted(fired),
                     "missing": missing, "spurious": spurious, "pass": ok,
                     "status": status})
        print(f"{'PASS' if ok else 'FAIL'}  {name:<26} missing={missing} spurious={spurious}")

    passed = sum(1 for r in rows if r["pass"])
    report = {"schema_version": "format-bench/v1", "scenarios": rows,
              "totals": {"passed": passed, "of": len(rows)},
              "note": ("One scenario per rule, aligned to the format-adaptation scoring points. "
                       "Clean baselines must report nothing.")}
    (Path(__file__).resolve().parent / "report_format.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n{passed}/{len(rows)} pass")
    return 0 if passed == len(rows) else 1


if __name__ == "__main__":
    raise SystemExit(main())
