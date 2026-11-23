"""Deep-routing, real-source/template and contract regression scenarios for p43."""
from __future__ import annotations

import copy
import json
import sys
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import deckbuild as D
import decksource as DS
import extra_rules as X
import pptxgen as P
import templatecheck as T

OUT = Path(__file__).resolve().parent / "_run_master"
BASE = {
    "section": "paper_to_deck", "case_id": "ppt-master-demo-001",
    "output_contract": ["case_id", "status", "deck_file", "evidence_map", "custom_note", "absent"],
    "custom_note": {" preserved ": True},
    "spacing": {"title": 32, "body": 20}, "font_ea": "Microsoft YaHei", "font_latin": "Arial",
    "min_font_pt": 14, "max_bullets_per_slide": 5, "require_notes": True,
    "available_evidence": ["Fig. 3b, p.7", "Sec. 2, p.3"],
    "required_mainline": ["question", "result"],
    "slides": [
        {"title": "吸收速率是瓶颈", "layout": "content", "role": "question",
         "claim": "多孔涂层解决速率瓶颈", "evidence": "Sec. 2, p.3", "notes": "先立问题。"},
        {"title": "吸收速率提高 3 倍", "layout": "content", "role": "result",
         "claim": "涂层使速率提高三倍", "evidence": "Fig. 3b, p.7",
         "caption": "Fig. 3b, p.7 — 对比的是速率",
         "bullets": ["对照组 12.4 a.u.", "涂层组 31.2 a.u.", "每组 n = 6"],
         "notes": "强调速率而非终点。"},
    ],
}


def d(**updates):
    value = copy.deepcopy(BASE)
    value.update(updates)
    return value


def run(name: str, spec: dict, case: dict | None = None):
    root = OUT / name
    root.mkdir(parents=True, exist_ok=True)
    path = root / "spec.json"
    path.write_text(json.dumps(spec, ensure_ascii=False), encoding="utf-8")
    case_path = None
    if case is not None:
        case_path = root / "case.json"
        case_path.write_text(json.dumps(case, ensure_ascii=False), encoding="utf-8")
    return D.build_and_audit(path, root / "out", case_path=case_path)


def rule_scenarios():
    yield "clean", d(), []
    yield "no_slides", d(slides=[]), ["deck.no_slides", "paper.mainline_missing"]
    yield "slide_over", d(max_slides=1), ["deck.slide_count_over_limit"]
    yield "slide_under", d(min_slides=3), ["deck.slide_count_under_limit"]
    yield "slide_budget_guard", d(min_slides=2, max_slides=2), []
    yield "slide_budget_invalid", d(max_slides="two"), ["deck.slide_budget_invalid"]
    yield "missing_image", d(), []
    # Yielded separately below because the base must be deeply modified.
    edit = d(section="deck_edit", revisions=[{"n": 1, "changes": []}])
    yield "instruction_missing", edit, ["edit.revision_instruction_missing", "edit.revision_without_changes"]
    edit_ok = d(section="deck_edit", revisions=[{"n": 1, "instruction": " polish ", "changes": [
        {"slide": 2, "before": "提高", "after": "提高 3 倍", "reason": "quantify"}]}])
    yield "instruction_guard", edit_ok, []
    talk = d(section="talk_org", required_mainline=[], goal={
        "objective": "评审理解证据边界", "audience": "评审", "minutes": 2},
        narrative=["question", "result"], qa_prep=[{"question": "n?", "answer": "6"}])
    for slide in talk["slides"]:
        slide["strength"] = "measured"
    yield "talk_clean_guards", talk, []
    bad = copy.deepcopy(talk); bad["narrative"] = ["question", "method", "result"]
    yield "narrative_missing", bad, ["org.narrative_incomplete"]
    bad = copy.deepcopy(talk); bad["slides"][0]["role"] = "extra"
    yield "role_outside", bad, ["org.role_undeclared", "org.narrative_incomplete"]
    bad = copy.deepcopy(talk); bad["require_qa_prep"] = True; bad["qa_prep"] = [{"question": "n?"}]
    yield "qa_incomplete", bad, ["org.qa_prep_missing"]
    bad = copy.deepcopy(talk); bad["require_qa_prep"] = True
    yield "qa_guard", bad, []
    bad = copy.deepcopy(talk); bad["slides"][0]["pace_minutes"] = 1.5; bad["slides"][1]["pace_minutes"] = 1
    yield "pace_exceeded", bad, ["org.pace_budget_exceeded"]
    bad = copy.deepcopy(talk); bad["slides"][0]["pace_minutes"] = 0.5; bad["slides"][1]["pace_minutes"] = 1
    yield "pace_guard", bad, []
    bad = copy.deepcopy(talk); bad["slides"][0]["pace_minutes"] = "soon"
    yield "pace_invalid", bad, ["org.pace_budget_invalid"]
    bad = copy.deepcopy(talk); bad["slides"][0]["strength"] = "very strong"
    yield "strength_unknown", bad, ["org.strength_unknown"]
    bad = copy.deepcopy(talk); bad["strength_scale"] = ["weak", "measured"]
    yield "strength_custom_guard", bad, []
    yield "mainline_guard", d(), []
    bad = d(required_mainline=["question", "method", "result", "limit"])
    yield "mainline_missing", bad, ["paper.mainline_missing"]


def _source_spec():
    spec = d(section="deck_edit", required_mainline=[], revisions=[
        {"n": 1, "instruction": "量化标题", "changes": [
            {"slide": 2, "before": "吸收速率明显提高", "after": "吸收速率提高 3 倍",
             "reason": "用实测倍数替换模糊程度词"}]}], delivered_revision=1)
    return spec


def _make_source(name: str, final_title="吸收速率明显提高"):
    source_spec = _source_spec()
    source_spec["slides"][1]["title"] = final_title
    root = OUT / name
    root.mkdir(parents=True, exist_ok=True)
    source = root / "source.pptx"
    P.write_deck(D.spec_slides(source_spec), source, spacing={"title": 32, "body": 20},
                 fonts=("Arial", "Microsoft YaHei"))
    return source


def _make_template(name="template_base"):
    root = OUT / name
    root.mkdir(parents=True, exist_ok=True)
    path = root / "real-template.pptx"
    P.write_deck([P.Slide(title="Template placeholder")], path,
                 spacing={"title": 32, "body": 20}, fonts=("Arial", "Microsoft YaHei"))
    return path


def section_guard_scenarios():
    rows = []
    # Missing image versus the normal no-image guard.
    spec = d(); spec["slides"][1]["image"] = str(OUT / "does-not-exist.png")
    rows.append(("image_missing", run("image_missing", spec), ["image.source_missing"]))
    rows.append(("image_absent_guard", run("image_absent_guard", d()), []))

    for name, source_title, expected in (
        ("source_clean", "吸收速率明显提高", []),
        ("source_already_applied_guard", "吸收速率提高 3 倍", []),
        ("source_before_missing", "完全不同的标题", ["edit.before_not_in_source"]),
    ):
        spec = _source_spec(); spec["source_deck"] = str(_make_source(name, source_title))
        result = run(name, spec)
        if name == "source_clean":
            assert result["source_record"]["package_preserved"] is True
            assert result["source_record"]["records"][0]["status"] == "applied"
        rows.append((name, result, expected))
    spec = _source_spec(); spec["source_deck"] = str(_make_source("source_invalid_slide"))
    spec["revisions"][0]["changes"][0]["slide"] = 9
    rows.append(("source_invalid_slide", run("source_invalid_slide", spec),
                 ["edit.source_change_unapplied"]))

    # Synthetic execution record isolates package-integrity accounting from XML editing.
    findings = D._source_findings({"package_preserved": False, "records": []})
    rows.append(("package_preserved_guard",
                 {"findings": D._source_findings({"package_preserved": True, "records": []})}, []))
    rows.append(("package_not_preserved", {"findings": findings}, ["edit.package_not_preserved"]))

    # Real template application, with the output master compared byte-for-byte.
    template = _make_template()
    spec = d(template={"name": "real", "file": str(template), "layouts": ["blank"]},
             font_latin="Arial", font_ea="Microsoft YaHei")
    for slide in spec["slides"]:
        slide["layout"] = "blank"
    result = run("template_applied_clean", spec)
    rows.append(("template_applied_clean", result, []))
    with zipfile.ZipFile(template) as z:
        expected_master = z.read("ppt/slideMasters/slideMaster1.xml")
    with zipfile.ZipFile(OUT / "template_applied_clean/out/deck.pptx") as z:
        assert z.read("ppt/slideMasters/slideMaster1.xml") == expected_master
    assert result["template_application"]["applied"] is True
    assert result["deck"]["template_applied"] is True

    measured = T.measure(template)
    # Each measured-template rule gets a focused defect; the clean physical run above
    # is their shared false-positive guard.
    bad_spec = copy.deepcopy(spec); bad_spec["slides"][0]["layout"] = "missing"
    rows.append(("template_layout_missing_unit", {"findings": T.audit(measured, bad_spec, [12192000, 6858000])},
                 ["template.layout_not_found"]))
    duplicate = copy.deepcopy(measured); duplicate["layout_details"].append(copy.deepcopy(measured["layout_details"][0]))
    duplicate["layout_details"][1]["part"] = "ppt/slideLayouts/slideLayout9.xml"
    rows.append(("template_duplicate_unit", {"findings": T.audit(duplicate, spec, [12192000, 6858000])},
                 ["template.duplicate_layout_name"]))
    require_ph = copy.deepcopy(spec); require_ph["require_title_placeholder"] = True
    rows.append(("template_placeholder_unit", {"findings": T.audit(measured, require_ph, [12192000, 6858000])},
                 ["template.title_placeholder_missing"]))
    orphan = copy.deepcopy(measured); orphan["layout_details"][0]["master"] = None
    rows.append(("template_orphan_unit", {"findings": T.audit(orphan, spec, [12192000, 6858000])},
                 ["template.layout_master_missing"]))
    other_font = copy.deepcopy(spec); other_font["font_latin"] = "Off Theme Face"
    rows.append(("template_font_unit", {"findings": T.audit(measured, other_font, [12192000, 6858000])},
                 ["template.theme_font_mismatch"]))
    rows.append(("template_size_unit", {"findings": T.audit(measured, spec, [1, 2])},
                 ["template.slide_size_mismatch"]))
    absent = T.measure(OUT / "absent-template.pptx")
    rows.append(("template_unreadable_unit", {"findings": T.audit(absent, spec, None)},
                 ["template.unreadable"]))
    return rows


def contract_check():
    spec = d(case_id=None, output_contract=None, custom_note=None, status="pretend-clean")
    case = {"case_id": "case-from-file", "output_contract": [
        {"field": "case_id"}, {"name": "status"}, "deck_file", "evidence_map",
        "render_record", "version_record", "custom_note", "absent"],
        "custom_note": "case value retained"}
    result = run("contract", spec, case)
    checks = [result.get("case_id") == "case-from-file",
              result.get("status") == "clean",
              result.get("deck_file", "").endswith("deck.pptx"),
              len(result.get("evidence_map") or []) == 2,
              result.get("custom_note") == "case value retained",
              "absent" in result and result["absent"] is None,
              any("absent" in line for line in result["limits"])]
    return all(checks), result


def main():
    rows = []
    for name, spec, expected in rule_scenarios():
        if name == "missing_image":
            continue
        result = run(name, spec)
        rows.append((name, result, expected))
    rows.extend(section_guard_scenarios())
    passed = 0
    reports = []
    for name, result, expected in rows:
        fired = {f["rule"] for f in result.get("findings", [])}
        missing = [rule for rule in expected if rule not in fired]
        spurious = [] if expected else [f["rule"] for f in result.get("findings", [])]
        ok = not missing and not spurious
        passed += int(ok)
        reports.append({"scenario": name, "expected": expected, "fired": sorted(fired),
                        "missing": missing, "spurious": spurious, "pass": ok})
        print(f"{'PASS' if ok else 'FAIL'}  {name:<32} missing={missing} spurious={spurious}")
    ok, contract_result = contract_check()
    passed += int(ok)
    reports.append({"scenario": "contract_case_file_passthrough", "pass": ok,
                    "case_id": contract_result.get("case_id")})
    print(f"{'PASS' if ok else 'FAIL'}  contract_case_file_passthrough")
    total = len(reports)
    report_path = Path(__file__).resolve().parent / "report_master.json"
    report_path.write_text(json.dumps({"schema_version": "ppt-master-deep-bench/v1",
        "scenarios": reports, "totals": {"passed": passed, "of": total}}, ensure_ascii=False, indent=2),
        encoding="utf-8")
    print(f"\n{passed}/{total} scenarios pass")
    return 0 if passed == total else 1


if __name__ == "__main__":
    raise SystemExit(main())
