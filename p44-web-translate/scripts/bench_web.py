"""Benchmark for the web body-extraction + per-paragraph translation traceability.

Each scenario pins one rule or one FP guard: extraction classes, locator
round-trip, honest empty body, citation-span cut, footnote cut, the translation
audit (untranslated / orphan / empty / passthrough / number preservation /
glossary enforcement / target language), and the case-contract passthrough.

    python bench_web.py
"""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import cleanweb  # noqa: E402
import webtranslate  # noqa: E402

HERE = Path(__file__).resolve().parent

PAGE = (
    "首页\n"
    "登录\n"
    "广告\n"
    "1 Introduction\n"
    "Porous coatings raise the uptake rate three-fold at room temperature.\n"
    "\n"
    "2 Methods\n"
    "We measured uptake with six replicates per arm.\n"
    "Download PDF\n"
    "3 Discussion\n"
    "Only one thickness was tested, so the result does not generalise.\n"
    "Related articles\n"
    "相关文章：另一篇涂层论文\n"
    "Copyright 2023\n"
)


def scen_body_extraction(tmp=None):
    r = cleanweb.extract_body(PAGE)
    texts = [b["text"] for b in r["body"]]
    ok = (len(texts) == 6
          and texts[0] == "1 Introduction"
          and any("three-fold" in x for x in texts)
          and any("does not generalise" in x for x in texts)
          and all(not any(c["text"] in t for c in r["cuts"]) for t in texts))
    cuts_classes = {c["class"] for c in r["cuts"]}
    return ok and {"nav", "ads", "related", "page-furniture"} <= cuts_classes


def scen_locator_roundtrip(tmp=None):
    """Every body paragraph's locator points at real line numbers in the source."""
    r = cleanweb.extract_body(PAGE)
    lines = PAGE.splitlines()
    for b in r["body"]:
        line = lines[b["first_line"]]
        if line.strip() and line.strip() not in b["text"] and b["text"][:20] not in line:
            return False
    return True


def scen_full_page_noise(tmp=None):
    """A page that is all navigation: honest empty body, not a guessed article."""
    r = cleanweb.extract_body("首页\n登录\n订阅\nCopyright 2023\n")
    return len(r["body"]) == 0 and len(r["cuts"]) >= 3


def scen_citation_list_cut(tmp=None):
    r = cleanweb.extract_body("Reference list follows.\n[1] Smith J. Some title. 2020.\n[2] Lee K. Other. 2021.\n")
    return all(c["class"] == "citation-list" for c in r["cuts"]) and len(r["cuts"]) == 2


def scen_footnote_cut(tmp=None):
    """Footnote lines are cut as their own class; mid-paragraph markers stay body."""
    page = ("1 Introduction\n"
            "Porous coatings raise the uptake rate three-fold.\n"
            "① All experiments were run at room temperature.\n"
            "注：本文数据为示意。\n"
            "2 Methods\n"
            "We measured uptake with six replicates.\n")
    r = cleanweb.extract_body(page)
    classes = {c["class"] for c in r["cuts"]}
    texts = " ".join(b["text"] for b in r["body"])
    return "footnote" in classes and "three-fold" in texts and "six replicates" in texts


def scen_footnote_fp_guard(tmp=None):
    """A circled marker NOT at line start does not cut a body line."""
    r = cleanweb.extract_body("The coating worked at 25 C① and stayed stable.\n")
    return len(r["body"]) == 1 and not r["cuts"]


def _run(tmp, translated_records, case=None, glossary=None, target_lang="zh",
         page_text=PAGE):
    td = Path(tmp)
    (td / "page.txt").write_text(page_text, encoding="utf-8")
    (td / "translated.json").write_text(
        json.dumps(translated_records, ensure_ascii=False), encoding="utf-8")
    case_path = None
    if case is not None:
        (td / "case.json").write_text(json.dumps(case, ensure_ascii=False), encoding="utf-8")
        case_path = td / "case.json"
    glossary_path = None
    if glossary is not None:
        (td / "gloss.json").write_text(
            json.dumps(glossary, ensure_ascii=False), encoding="utf-8")
        glossary_path = td / "gloss.json"
    return webtranslate.build_and_audit(
        td / "page.txt", td / "out", td / "translated.json",
        case_path=case_path, glossary_path=glossary_path, target_lang=target_lang)


FULL_ZH = [
    {"id": "P1", "target": "1 引言"},
    {"id": "P2", "target": "多孔涂层在室温下使吸收速率提高三倍。"},
    {"id": "P3", "target": "2 方法"},
    {"id": "P4", "target": "我们用每组六个重复测量吸收。"},
    {"id": "P5", "target": "3 讨论"},
    {"id": "P6", "target": "只测试了一种厚度，所以该结果不能外推。"},
]


def scen_clean_baseline(tmp=None):
    """A fully translated audit with only noise cuts: review, no medium/high findings."""
    with tempfile.TemporaryDirectory() as td:
        r = _run(td, FULL_ZH)
        rules = [f["rule"] for f in r["findings"]]
        return (r["status"] == "review"
                and not any(f["severity"] in ("high", "medium") for f in r["findings"])
                and rules == ["web.noise_cut"])


def scen_number_preserved(tmp=None):
    """FP guard: digits kept in the translation produce no number finding."""
    page = "1 Results\nUptake rose from 12 to 36 units at 25 C.\n"
    zh = [{"id": "P1", "target": "1. 结果"},
          {"id": "P2", "target": "在 25 C 下，吸收从 12 升到 36 个单位。"}]
    with tempfile.TemporaryDirectory() as td:
        r = _run(td, zh, page_text=page)
        return not any(f["rule"] == "web.number_dropped" for f in r["findings"])


def scen_number_dropped(tmp=None):
    """Digits lost in translation are flagged for review."""
    page = "1 Results\nUptake rose from 12 to 36 units at 25 C.\n"
    zh = [{"id": "P1", "target": "1 结果"},
          {"id": "P2", "target": "吸收速率大幅上升。"}]
    with tempfile.TemporaryDirectory() as td:
        r = _run(td, zh, page_text=page)
        f = [x for x in r["findings"] if x["rule"] == "web.number_dropped"]
        return len(f) == 1 and set(f[0]["missing"]) == {"12", "36", "25"}


def scen_glossary_enforced(tmp=None):
    """A glossary term whose declared gloss is absent from the target is flagged."""
    page = "1 Background\nThe porous coating absorbs water quickly.\n"
    zh = [{"id": "P1", "target": "背景"},
          {"id": "P2", "target": "这种涂层很快吸水。"}]
    gloss = {"porous coating": "多孔涂层"}
    with tempfile.TemporaryDirectory() as td:
        r = _run(td, zh, glossary=gloss, page_text=page)
        f = [x for x in r["findings"] if x["rule"] == "web.term_gloss_mismatch"]
        return len(f) == 1 and f[0]["terms"] == ["porous coating"]


def scen_glossary_match_clean(tmp=None):
    """FP guard: when the declared gloss IS used, no glossary finding appears."""
    page = "1 Background\nThe porous coating absorbs water quickly.\n"
    zh = [{"id": "P1", "target": "背景"},
          {"id": "P2", "target": "多孔涂层很快吸水。"}]
    gloss = {"porous coating": "多孔涂层"}
    with tempfile.TemporaryDirectory() as td:
        r = _run(td, zh, glossary=gloss, page_text=page)
        return not any(f["rule"] == "web.term_gloss_mismatch" for f in r["findings"])


def scen_target_not_zh(tmp=None):
    """A translation with no Chinese characters is flagged when zh is assumed,
    and not flagged when the declared target language is not zh."""
    page = "1 Results\nThe coating doubled the uptake.\n"
    en = [{"id": "P1", "target": "1 Results"},
          {"id": "P2", "target": "The coating doubled the uptake rate."}]
    with tempfile.TemporaryDirectory() as td:
        r = _run(td, en, page_text=page)
        flagged = any(f["rule"] == "web.target_not_zh" for f in r["findings"])
    with tempfile.TemporaryDirectory() as td:
        r2 = _run(td, en, page_text=page, target_lang="en")
        clean = not any(f["rule"] == "web.target_not_zh" for f in r2["findings"])
    return flagged and clean


def scen_translated_record_invalid(tmp=None):
    """Non-object records in the translation file are named, not silently dropped."""
    bad = ["oops", {"id": "P1", "target": "引言"}, 42]
    with tempfile.TemporaryDirectory() as td:
        r = _run(td, bad)
        f = [x for x in r["findings"] if x["rule"] == "web.translated_record_invalid"]
        return len(f) == 1 and f[0]["records"] == [0, 2] \
            and any(x["rule"] == "web.paragraph_untranslated" and x.get("segment") == "P2"
                    for x in r["findings"])


def scen_contract_passthrough(tmp=None):
    """case_id and output_contract fields are echoed into result.json verbatim:
    literal contract values are copied, a schema-object field nobody can derive is
    null and named in limits."""
    case = {"case_id": "case-test-0001",
            "output_contract": {"deliverable": "clean body + per-paragraph zh translation",
                                "page_url": "https://example.org/paper",
                                "paragraph_schema": {"id": "P1", "target": "..."}}}
    with tempfile.TemporaryDirectory() as td:
        r = _run(td, FULL_ZH, case=case)
        return (r.get("case_id") == "case-test-0001"
                and r.get("deliverable") == "clean body + per-paragraph zh translation"
                and r.get("page_url") == "https://example.org/paper"
                and r.get("paragraph_schema") is None
                and any("paragraph_schema" in l for l in r["limits"]))


def scen_cli_exit_undetermined(tmp=None):
    """A missing page file exits 5 with a result.json on disk and no traceback."""
    import subprocess
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        r = subprocess.run([sys.executable, str(HERE / "webtranslate.py"),
                            "--page", str(td / "nope.txt"), "--out", str(td / "out")],
                           capture_output=True, text=True, timeout=120)
        res = json.loads((td / "out" / "result.json").read_text(encoding="utf-8"))
        return (r.returncode == 5 and res["status"] == "undetermined"
                and "Traceback" not in r.stderr)


SCENARIOS = [
    ("body_extraction", scen_body_extraction),
    ("locator_roundtrip", scen_locator_roundtrip),
    ("full_page_noise", scen_full_page_noise),
    ("citation_list_cut", scen_citation_list_cut),
    ("footnote_cut", scen_footnote_cut),
    ("footnote_fp_guard", scen_footnote_fp_guard),
    ("clean_baseline", scen_clean_baseline),
    ("number_preserved", scen_number_preserved),
    ("number_dropped", scen_number_dropped),
    ("glossary_enforced", scen_glossary_enforced),
    ("glossary_match_clean", scen_glossary_match_clean),
    ("target_not_zh", scen_target_not_zh),
    ("translated_record_invalid", scen_translated_record_invalid),
    ("contract_passthrough", scen_contract_passthrough),
    ("cli_exit_undetermined", scen_cli_exit_undetermined),
]


def main() -> int:
    rows = []
    for name, fn in SCENARIOS:
        try:
            ok = bool(fn())
            why = ""
        except Exception as exc:
            ok, why = False, f"raised {type(exc).__name__}: {exc}"
        rows.append({"scenario": name, "pass": ok, "why": why})
        print(("PASS" if ok else "FAIL") + f"  {name:<26}" + why)

    # CLI smoke: clean + translate with an orphan id
    import subprocess
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        (td / "page.txt").write_text(PAGE, encoding="utf-8")
        translated = [{"id": "P1", "target": "多孔涂层使吸收速率提高三倍。"},
                      {"id": "P9", "target": "ghost"}]
        (td / "translated.json").write_text(json.dumps(translated, ensure_ascii=False),
                                            encoding="utf-8")
        r = subprocess.run([sys.executable, str(HERE / "webtranslate.py"),
                            "--page", str(td / "page.txt"),
                            "--out", str(td / "out"), "--translated", str(td / "translated.json")],
                           capture_output=True, text=True, timeout=120)
        res = json.loads((td / "out" / "result.json").read_text(encoding="utf-8"))
        rules = [f["rule"] for f in res["findings"]]
        ok = res["status"] == "review" and "web.paragraph_untranslated" in rules \
            and "web.orphan_translation" in rules and "Traceback" not in r.stderr
        rows.append({"scenario": "cli_orphan_trace", "pass": ok, "why": ""})
        print(("PASS" if ok else "FAIL") + "  cli_orphan_trace")

    passed = sum(1 for r in rows if r["pass"])
    report = {"schema_version": "web-bench/v1", "scenarios": rows,
              "totals": {"passed": passed, "of": len(rows)}}
    (Path(__file__).resolve().parent.parent / "report_web.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n{passed}/{len(rows)} scenarios pass")
    return 0 if passed == len(rows) else 1


if __name__ == "__main__":
    raise SystemExit(main())
