"""Artifact and rule regressions for audience-driven academic talk organization."""
from __future__ import annotations

import copy
import json
import sys
import tempfile
import zipfile
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS))
import deckaudit as A
import deckbuild as D
import pptxgen as P

ROOT = Path(tempfile.mkdtemp(prefix="p32_delivery4_"))
EXAMPLE = SCRIPTS.parent / "examples" / "spec.json"


def base() -> dict:
    return json.loads(EXAMPLE.read_text(encoding="utf-8"))


def run(name: str, spec: dict) -> tuple[dict, Path]:
    work = ROOT / name
    work.mkdir(parents=True, exist_ok=True)
    path = work / "spec.json"
    path.write_text(json.dumps(spec, ensure_ascii=False), encoding="utf-8")
    out = work / "out"
    return D.build_and_audit(path, out), out


def main() -> int:
    reports = []

    def scenario(name: str, result: dict, expected: list[str], checks=None):
        fired = {f["rule"] for f in result.get("findings", [])}
        missing = [x for x in expected if x not in fired]
        spurious = [] if expected else [f["rule"] for f in result.get("findings", [])]
        errors = list(checks(result) if checks else [])
        ok = not missing and not spurious and not errors
        reports.append({"scenario": name, "expected": expected, "fired": sorted(fired),
                        "missing": missing, "spurious": spurious, "assertions": errors, "pass": ok})
        print(f"{'PASS' if ok else 'FAIL'}  {name:<34} missing={missing} spurious={spurious} assertions={errors}")

    result, out = run("clean_story", base())
    def clean_checks(r):
        errors = []
        with zipfile.ZipFile(out / "deck.pptx") as z:
            slides = sorted(n for n in z.namelist() if n.startswith("ppt/slides/slide") and n.endswith(".xml"))
            notes = [n for n in z.namelist() if n.startswith("ppt/notesSlides/notesSlide") and n.endswith(".xml")]
            if len(slides) != 6 or len(notes) != 6: errors.append(f"slides={len(slides)}, notes={len(notes)}")
            fields = sum(z.read(n).count(b'type="slidenum"') for n in slides)
            if fields != 6: errors.append(f"slide number fields={fields}")
        deck = A.read_deck(out / "deck.pptx")
        spec = base()
        for i, slide in enumerate(deck):
            expected = spec["slides"][i]["evidence"]
            visible = " ".join(p["text"] for s in slide["shapes"] for p in s["paras"])
            if expected not in visible: errors.append(f"slide {i + 1}: evidence not visible: {expected}")
        if spec["slides"][4]["takeaway"] not in " ".join(
                p["text"] for s in deck[4]["shapes"] for p in s["paras"]):
            errors.append("takeaway not visible on main closing slide")
        if not r.get("reproducibility", {}).get("deterministic"): errors.append("non-deterministic rebuild")
        plan = r.get("presentation_plan") or {}
        if len(plan.get("selection_ledger", {}).get("kept", [])) != 3: errors.append("kept ledger missing")
        if len(plan.get("selection_ledger", {}).get("omitted", [])) != 1: errors.append("omitted ledger missing")
        if len(r.get("qa_ledger") or []) != 3: errors.append("QA ledger missing")
        if r.get("timing_plan", {}).get("qa_minutes") != 2: errors.append("QA time reserve missing")
        if r.get("not_available_from_material") is not None: errors.append("unknown contract field not null")
        return errors
    scenario("clean_complete_story", result, [], clean_checks)

    bad = base(); bad["slides"][2]["title"] = "结果"
    result, _ = run("topic_title", bad); scenario("topic_title_detected", result, ["org.title_is_topic"])

    bad = base(); bad["slides"][2]["claim"] = "First result is positive. Second result is negative."
    result, _ = run("multiple_claims", bad); scenario("multiple_claims_detected", result, ["org.multiple_claims"])

    bad = base(); bad["slides"][1]["role"], bad["slides"][2]["role"] = "result", "method"
    result, _ = run("narrative_backwards", bad); scenario("narrative_backwards_detected", result, ["org.narrative_order"])

    bad = base(); bad["slides"][4]["takeaway"] = "Only in speaker notes, not the final slide"
    result, _ = run("takeaway_not_landed", bad); scenario("takeaway_landing_checked", result, ["org.takeaway_not_landed"])

    bad = base(); bad["slides"][4]["role"] = "result"
    result, _ = run("missing_closing", bad); scenario("missing_closing_detected", result, ["org.closing_missing"])

    bad = base(); bad["slides"][4]["role"] = "conclusion"
    result, _ = run("missing_limitations", bad); scenario("missing_limitations_detected", result, ["org.limitations_missing"])

    bad = base(); bad["audience_plan"]["emphasis"] = ["background", "discussion"]
    result, _ = run("audience_emphasis_gap", bad); scenario("audience_emphasis_gap_detected", result, ["org.audience_emphasis_missing"])

    bad = base(); bad["slides"][2]["pace_minutes"] = 12
    result, _ = run("time_budget_exceeded", bad); scenario("time_budget_exceeded_detected", result, ["org.pace_budget_exceeded"])

    bad = base(); bad["slides"][4].pop("pace_minutes")
    result, _ = run("missing_slide_time", bad); scenario("missing_slide_time_detected", result, ["org.pace_slide_missing"])

    bad = base(); bad["qa_prep"] = bad["qa_prep"][:2]
    result, _ = run("missing_qa_topic", bad); scenario("missing_qa_topic_detected", result, ["org.qa_topics_missing"])

    bad = base(); bad["qa_prep"][0]["answer_slide"] = 99
    result, _ = run("invalid_qa_pointer", bad); scenario("invalid_qa_pointer_detected", result, ["org.qa_pointer_invalid"])

    bad = base(); bad["slides"][2].pop("strength_rationale")
    result, _ = run("missing_strength_reason", bad); scenario("missing_strength_reason_detected", result, ["org.strength_rationale_missing"])

    bad = base(); bad["slides"][2]["strength_rationale"] = "preliminary uncertain evidence only"
    result, _ = run("overstated_strength", bad); scenario("overstated_strength_detected", result, ["org.strength_overstated"])

    bad = base(); bad["selection_ledger"]["kept"][0].pop("reason")
    result, _ = run("incomplete_selection_ledger", bad); scenario("incomplete_selection_ledger_detected", result, ["org.selection_ledger_incomplete"])

    bad = base(); bad["slides"][2].pop("selection_reason")
    result, _ = run("missing_selection_reason", bad); scenario("missing_selection_reason_detected", result, ["org.slide_decision_missing"])

    # Real source-deck path: metadata can name evidence, but the visible source
    # band is absent and therefore must not pass require_evidence_on_slide.
    source_spec = base(); source_spec["slides"][2]["evidence"] = ""; source_spec["slides"][2]["caption"] = ""
    source = ROOT / "source-without-visible-evidence.pptx"
    P.write_deck(D.spec_slides(source_spec), source, spacing=source_spec["spacing"],
                 fonts=(source_spec["font_latin"], source_spec["font_ea"]),
                 style=P.normalize_style(source_spec.get("style")))
    bad = base(); bad["source_deck"] = str(source); bad["slides"][2]["caption"] = ""
    result, _ = run("evidence_not_landed_source", bad)
    scenario("visible_evidence_landing_checked", result, ["deck.evidence_not_landed"])

    passed = sum(1 for x in reports if x["pass"])
    result = {"schema_version": "talk-delivery-bench/v4", "temp_root": str(ROOT),
              "scenarios": reports, "totals": {"passed": passed, "of": len(reports)}}
    (SCRIPTS / "report_delivery4.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n{passed}/{len(reports)} scenarios pass\nartifacts: {ROOT}")
    return 0 if passed == len(reports) else 1


if __name__ == "__main__":
    raise SystemExit(main())
