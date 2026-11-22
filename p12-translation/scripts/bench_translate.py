"""Benchmark for the translation / bilingual-writing skill.

One scenario per rule, aligned to the scoring points this task states, plus one
false-positive guard scenario per rule added on top of a clean baseline:

  the requested output shape is what was delivered   -> mode_missing, segments_missing,
                                                        segment_unpaired, segment_id_duplicate,
                                                        segment_id_absent
  the pairs carry the whole declared source          -> segment_coverage_low
  a declared back-translation pass is complete       -> backcheck_missing, backcheck_orphaned
  terms, numbers, units, citations preserved         -> invariant_broken, invariant_added,
                                                        negation_changed,
                                                        hedge_strength_changed
  a locked term actually reaches the target          -> term_missing
  unresolved work is registered, not just marked     -> placeholder_unregistered
  a scanned source says what OCR did                 -> ocr_degradation_unrecorded
  coverage of figures/tables/footnotes/references    -> component_untranslated
  maintainable terminology with a basis              -> term_variant, term_entry_no_basis,
                                                        glossary_conflict
  magnitude words converted and accounted for        -> number_conversion_unexplained
  a runnable, undamaged input                        -> replacement_char_present,
                                                        language_pair_degenerate
  comma-grouped numbers survive unwinding            -> comma_number_clean (FP guard)

    python bench_translate.py
"""

from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import writing as W  # noqa: E402

SRC = "涂层的吸收率提高到原来的3倍[1]。样品在25 °C下测量[2]。"
TGT = "The coating improved uptake 3-fold [1]. Samples were measured at 25 °C [2]."

BASE = {
    "output_mode": "plain",
    "source_lang": "zh",
    "target_lang": "en",
    "source_text": SRC,
    "target_text": TGT,
}


def d(**over):
    s = copy.deepcopy(BASE)
    s.update(over)
    return s


BILINGUAL = d(
    output_mode="bilingual",
    source_text="",
    target_text="",
    segments=[
        {"id": "s1", "source": "涂层的吸收率提高到原来的3倍[1]。",
         "target": "The coating improved uptake 3-fold [1]."},
        {"id": "s2", "source": "样品在25 °C下测量[2]。",
         "target": "Samples were measured at 25 °C [2]."},
    ],
)


def seg(index, **over):
    s = copy.deepcopy(BILINGUAL)
    s["segments"] = copy.deepcopy(BILINGUAL["segments"])
    s["segments"][index] = dict(BILINGUAL["segments"][index], **over)
    return s


SCEN = [
    ("clean_plain", lambda: (d(), [])),
    ("clean_bilingual", lambda: (copy.deepcopy(BILINGUAL), [])),

    # output shape
    ("mode_missing", lambda: (d(output_mode=""), ["xlate.mode_missing"])),
    ("mode_unknown", lambda: (d(output_mode="side-by-side"), ["xlate.mode_unknown"])),
    ("segments_missing", lambda: (d(output_mode="bilingual"), ["xlate.segments_missing"])),
    ("segment_unpaired", lambda: (seg(1, target=""), ["xlate.segment_unpaired"])),
    ("segment_id_duplicate",
     lambda: (d(output_mode="bilingual", source_text="", target_text="",
                segments=[{"id": "s1", "source": "甲", "target": "A"},
                          {"id": "s1", "source": "乙", "target": "B"}]),
              ["xlate.segment_id_duplicate"])),

    # invariants
    ("quantity_dropped",
     lambda: (d(target_text="The coating improved uptake [1]. Samples were measured at 25 °C [2]."),
              ["xlate.invariant_broken"])),
    ("quantity_added",
     lambda: (d(target_text="The coating improved uptake 3-fold [1]. Samples were measured at "
                            "25 °C and 40 °C [2]."),
              ["xlate.invariant_added"])),
    ("citation_dropped",
     lambda: (d(target_text="The coating improved uptake 3-fold. Samples were measured at 25 °C."),
              ["xlate.invariant_broken"])),

    # meaning boundaries
    ("negation_changed",
     lambda: (d(target_text="The coating did not improve uptake 3-fold [1]. Samples were not "
                            "measured at 25 °C [2]."),
              ["xlate.negation_changed"])),
    ("hedge_strength_changed",
     lambda: (d(source_text="涂层可能提高吸收率[1]。",
                target_text="The coating clearly increases uptake [1]."),
              ["xlate.hedge_strength_changed"])),

    # magnitude words
    ("conversion_unexplained",
     lambda: (d(source_text="样本量达到 300 万[1]。", target_text="The sample reached 3 million [1]."),
              ["xlate.number_conversion_unexplained"])),
    ("conversion_declared_clean",
     # zh->en moves digits DOWN (300 万 -> 3 million): the recorded conversion
     # excuses the change in either direction, not only upward.
     lambda: (d(source_text="样本量达到 300 万[1]。",
                target_text="The sample reached 3 million [1].",
                conversions=[{"from": "300 万", "to": "3 million", "factor": "1e6"}]),
              [])),

    # coverage of non-body parts
    ("component_untranslated",
     lambda: (d(components={"figures": "3", "figures_marker": "Fig."}),
              ["xlate.component_untranslated"])),

    # residue, length, terminology
    ("untranslated_residue",
     lambda: (d(target_text="The coating 涂层 improved uptake 3-fold [1]. Samples were measured "
                            "at 25 °C [2]."),
              ["xlate.untranslated_residue"])),
    ("length_out_of_band",
     # Document-scale source: the band is noise on a two-segment demo, so it
     # only applies above ~200 source characters.
     lambda: (d(source_text=SRC * 8, target_text="Short [1] [2]."),
              ["xlate.length_out_of_band"])),
    ("term_variant",
     lambda: (d(glossary={"uptake": {"preferred": "uptake", "variants": ["sorption"],
                                     "basis": "field convention"}},
                target_text="The coating improved sorption 3-fold [1]. Samples were measured at "
                            "25 °C [2]."),
              ["xlate.term_variant"])),
    ("term_entry_no_basis",
     lambda: (d(glossary={"uptake": {"preferred": "uptake", "variants": []}}),
              ["xlate.term_entry_no_basis"])),

    # a locked term must actually reach the target (先锁后译)
    ("term_missing_guard",
     # FP guard: the entry's declared abbreviation is used, so the locked term
     # did reach the target in its short form.
     lambda: (d(source_lang="en", target_lang="zh",
                source_text="Machine learning was used to classify the spectra.",
                target_text="我们用ML方法对光谱进行了分类。",
                glossary={"machine learning": {"preferred": "机器学习", "abbreviation": "ML",
                                               "variants": [], "basis": "textbook convention"}}),
              [])),

    # every segment addressable

    # the pairs must carry the declared source
    ("segment_coverage_guard",
     # FP guard: same declaration, pairs cover all of it (merging/splitting
     # segments must not fire the rule).
     lambda: (d(output_mode="bilingual", target_text="", source_text=SRC,
                segments=[{"id": "s1", "source": "涂层的吸收率提高到原来的3倍[1]。",
                           "target": "The coating improved uptake 3-fold [1]."},
                          {"id": "s2", "source": "样品在25 °C下测量[2]。",
                           "target": "Samples were measured at 25 °C [2]."}]),
              [])),

    # a declared back-translation pass must cover the high-risk segments
    ("backcheck_guard",
     lambda: (dict(BILINGUAL, backcheck=[{"segment": "s1"}, {"segment": "s2"}]), [])),

    # unresolved work must be registered, not only marked
    ("placeholder_guard",
     # FP guard: the marker is registered in limits — the mark stays in the text.
     lambda: (d(source_lang="en", target_lang="zh",
                source_text="The exact concentration is given in Appendix A.",
                target_text="准确浓度见附录A（TODO）。",
                limits=["Appendix A marked TODO pending the exact concentration from the "
                        "source PDF"]),
              [])),

    # a scanned source must record what OCR did
    ("ocr_guard",
     lambda: (d(source_format="pdf", text_layer=False,
                ocr={"engine": "tesseract", "confidence": 0.92}), [])),

    # --- round 2: restored declarative rules, each with its own scenario ----

    # "30,000" must survive as one number: a faithful rendering to 30000 was
    # once read as a dropped 30-and-0 (comma unwinding bug). This guard pins it.
    ("comma_number_clean",
     lambda: (d(source_lang="en", target_lang="zh",
                source_text="A total of 30,000 samples were analysed [1].",
                target_text="共分析了 30000 个样本[1]。"),
              [])),

    # a locked term must reach the target (术语稳): the concept occurs in the
    # source, the locked rendering arrives nowhere.
    ("term_missing",
     lambda: (d(glossary={"吸收率": {"preferred": "absorptance", "variants": [],
                                     "basis": "ISO 9287 field usage"}}),
              ["xlate.term_missing"])),

    # the pairs must carry the declared source (对得齐): a whole chunk of the
    # declared source has no pair.
    ("segment_coverage_low",
     lambda: (d(output_mode="bilingual", source_text=SRC * 3,
                segments=[{"id": "s1", "source": "涂层的吸收率提高到原来的3倍[1]。",
                           "target": "The coating improved uptake 3-fold [1]."},
                          {"id": "s2", "source": "样品在25 °C下测量[2]。",
                           "target": "Samples were measured at 25 °C [2]."}]),
              ["xlate.segment_coverage_low"])),

    # a declared back-translation pass with no record for a high-risk segment
    ("backcheck_missing",
     lambda: (dict(BILINGUAL, backcheck=[{"segment": "s1"}]),
              ["xlate.backcheck_missing"])),

    # a back-translation record pointing at a segment id that does not exist
    ("backcheck_orphaned",
     lambda: (dict(BILINGUAL, backcheck=[{"segment": "s1"}, {"segment": "s2"},
                                         {"segment": "s9"}]),
              ["xlate.backcheck_orphaned"])),

    # a work marker left in the text with nothing routing it to a human
    ("placeholder_unregistered",
     lambda: (d(source_lang="en", target_lang="zh",
                source_text="The exact concentration is given in Appendix A.",
                target_text="准确浓度见附录A（待确认）。"),
              ["xlate.placeholder_unregistered"])),

    # a scanned source that presents recognised text as verified text
    ("ocr_unrecorded",
     lambda: (d(source_format="pdf", text_layer=False),
              ["xlate.ocr_degradation_unrecorded"])),

    # two glossary concepts claim the same preferred form (术语表冲突)
    ("glossary_conflict",
     lambda: (d(glossary={"吸附": {"preferred": "sorption", "variants": [],
                                   "basis": "IUPAC"},
                          "吸着": {"preferred": "sorption", "variants": [],
                                   "basis": "textbook B"}}),
              ["xlate.glossary_conflict"])),

    # encoding damage is named, not silently audited
    ("replacement_char",
     lambda: (d(target_text=TGT.replace("uptake", "upta\ufffdke")),
              ["xlate.replacement_char_present"])),

    # a degenerate language pair cannot be a translation
    ("same_lang_pair",
     lambda: (d(source_lang="en", target_lang="en",
                source_text="The coating improved uptake 3-fold [1].",
                target_text="The coating improved uptake 3-fold [1]."),
              ["xlate.language_pair_degenerate"])),

    # a bilingual delivery where no segment carries an id cannot be addressed
    ("segment_id_absent",
     lambda: (d(output_mode="bilingual", source_text="", target_text="",
                segments=[{"source": "涂层的吸收率提高到原来的3倍[1]。",
                           "target": "The coating improved uptake 3-fold [1]."},
                          {"source": "样品在25 °C下测量[2]。",
                           "target": "Samples were measured at 25 °C [2]."}]),
              ["xlate.segment_id_absent"])),
]


def main() -> int:
    rows = []
    for name, builder in SCEN:
        spec, expect = builder()
        findings, status, counts = W.run(spec, "translation")
        fired = {f["rule"] for f in findings}
        missing = [r for r in expect if r not in fired]
        spurious = [] if expect else [f["rule"] for f in findings]
        ok = not missing and not spurious
        rows.append({"scenario": name, "expected": expect, "fired": sorted(fired),
                     "missing": missing, "spurious": spurious, "pass": ok,
                     "status": status})
        print(f"{'PASS' if ok else 'FAIL'}  {name:<26} missing={missing} spurious={spurious}")

    passed = sum(1 for r in rows if r["pass"])
    report = {"schema_version": "translation-bench/v1", "scenarios": rows,
              "totals": {"passed": passed, "of": len(rows)},
              "note": ("One scenario per rule, aligned to the translation scoring points. "
                       "Clean baselines must report nothing.")}
    (Path(__file__).resolve().parent / "report_translation.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n{passed}/{len(rows)} pass")
    return 0 if passed == len(rows) else 1


if __name__ == "__main__":
    raise SystemExit(main())
