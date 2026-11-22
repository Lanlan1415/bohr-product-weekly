"""Benchmark for the contract-pass and page-budget rules of the deck-edit skill.

The revision, measurement, master-chain and embedding rules live in bench_deck.py,
bench_deck2.py and bench_extra.py. This file covers the polish-pass additions:

  two new audit rules    deck.empty_deck (a written deck with no slides is not a
                         deliverable) and deck.slide_count_over_limit (the
                         declared page budget is enforced, not admired)
  one new record rule    edit.revision_instruction_missing (a round without its
                         instruction loses the intent of the iteration)
  defensive typing       mistyped spacing still builds, with the coercion named
                         in limits instead of crashing
  the delivery contract  case_id and every declared output_contract field are
                         carried into result.json (spec-carried values pass
                         through verbatim, audit-derived fields are kept, the
                         rest become null with a limits note)
  the refusal path       an unreadable spec, a non-object spec and a missing
                         spec file all write an undetermined result.json and
                         answer with exit code 5 -- never a traceback

Every defect scenario ships with its false-positive guard: correct practice
(a deck inside its budget, a round that names its instruction) must stay silent.

    python bench_edit3.py
"""

from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import deckbuild  # noqa: E402

OUT = Path(__file__).resolve().parent / "_run_edit3"

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

SLIDE3 = {"title": "机制与限制", "claim": "孔径决定选择性", "evidence": "Fig. 3b, p.7",
          "bullets": ["孔径 42 nm 以下选择性最高"], "notes": "一句话带过，留给答辩。"}


def d(**over):
    s = copy.deepcopy(BASE)
    s.update(over)
    return s


def run(name: str, spec: dict, case_id: str | None = None) -> dict:
    p = OUT / name
    p.mkdir(parents=True, exist_ok=True)
    (p / "spec.json").write_text(json.dumps(spec, ensure_ascii=False), encoding="utf-8")
    return deckbuild.build_and_audit(p / "spec.json", p / "o", case_id=case_id)


# --- spec-expressible rule scenarios (defect + guard pairs) ---------------------

def scen_empty_deck():
    s = d(slides=[])
    return s, ["deck.empty_deck"]


def scen_slide_over_limit():
    s = d(slides=BASE["slides"] + [copy.deepcopy(SLIDE3)], max_slides=2)
    return s, ["deck.slide_count_over_limit"]


def scen_slide_within_limit_fp():
    s = d(slides=BASE["slides"] + [copy.deepcopy(SLIDE3)], max_slides=3)
    return s, []


def scen_instruction_missing():
    s = d()
    s["revisions"] = copy.deepcopy(BASE["revisions"])
    s["revisions"][0].pop("instruction")
    return s, ["edit.revision_instruction_missing"]


def scen_instruction_fp():
    return d(), []


def scen_mistyped_spacing():
    """A mistyped spacing must not crash the build: the default is used and the
    coercion is named in limits."""
    s = d(spacing="32/20")
    r = run("mistyped_spacing", s)
    ok = (r.get("status") in ("clean", "review")
          and any("spacing" in x for x in r.get("limits", []))
          and (r.get("deck") or {}).get("spacing") == {"title": 32, "body": 20})
    return r, ok


# --- the delivery contract -------------------------------------------------------

CONTRACT = {"deliverable": "editable deck.pptx",
            "status": "audit verdict",
            "reproducibility": "two builds must match",
            "export_format": "pptx"}


def scen_contract_passthrough():
    """case_id is recorded; every declared contract field lands in the result.

    The audit-derived fields (status, reproducibility) keep the audited values --
    a spec-carried value must never override the honest one. A spec-carried
    field (deliverable) passes through verbatim. A field neither side can fill
    (export_format is declared in the contract but carried nowhere) becomes null
    and is named in limits, never fabricated.
    """
    spec = d(case_id="deck-case-001", output_contract=dict(CONTRACT))
    spec["deliverable"] = CONTRACT["deliverable"]
    r = run("contract", spec)
    ok = (r.get("case_id") == "deck-case-001"
          and r.get("deliverable") == CONTRACT["deliverable"]
          and r.get("status") in ("clean", "review", "blocked")
          and r.get("reproducibility", {}).get("deterministic") is True
          and r.get("export_format") is None
          and any("export_format" in x for x in r.get("limits", [])))
    return r, ok


# --- the refusal path ------------------------------------------------------------

def _refused_case(name: str, payload: str | None, case_id: str | None = None) -> tuple[dict, bool]:
    p = OUT / name
    p.mkdir(parents=True, exist_ok=True)
    if payload is not None:
        (p / "spec.json").write_text(payload, encoding="utf-8")
    r = deckbuild.build_and_audit(p / "spec.json", p / "o", case_id=case_id)
    ok = (r.get("status") == "undetermined"
          and any(f.get("rule") == "audit.no_section" for f in r.get("findings", []))
          and (p / "o" / "result.json").exists()
          and (case_id is None or r.get("case_id") == case_id))
    return r, ok


def scen_refused_bad_json():
    return _refused_case("refused_bad_json", "{not json at all]")


def scen_refused_not_object():
    return _refused_case("refused_not_object", '"just a string"')


def scen_refused_missing_file():
    return _refused_case("refused_missing_file", None)


def scen_refused_case_id_kept():
    return _refused_case("refused_case_id", "[1, 2]", case_id="deck-case-002")


def scen_exit_code_undetermined():
    ok = deckbuild.EXIT_CODES.get("undetermined") == 5
    return {"status": "undetermined"}, ok


def scen_slides_wrong_type():
    """Slides declared as a bare string cannot become a deck: undetermined, no crash."""
    s = d(slides="two slides please")
    r = run("slides_wrong_type", s)
    return r, r.get("status") == "undetermined"


SCEN = [
    ("clean", scen_instruction_fp),
    ("empty_deck", scen_empty_deck),
    ("slide_over_limit", scen_slide_over_limit),
    ("slide_within_limit_fp", scen_slide_within_limit_fp),
    ("instruction_missing", scen_instruction_missing),
    ("mistyped_spacing", scen_mistyped_spacing),
    ("slides_wrong_type", scen_slides_wrong_type),
]


def main() -> int:
    rows = []
    for name, builder in SCEN:
        out = builder()
        if len(out) == 2 and isinstance(out[1], list):
            spec, expect = out
            r = run(name, spec)
            fired = {f["rule"] for f in r.get("findings", [])}
            missing = [x for x in expect if x not in fired]
            spurious = [] if expect else [f["rule"] for f in r.get("findings", [])]
            ok = not missing and not spurious
            rows.append({"scenario": name, "expected": expect, "fired": sorted(fired),
                         "missing": missing, "spurious": spurious, "pass": ok,
                         "status": r.get("status")})
            print(f"{'PASS' if ok else 'FAIL'}  {name:<24} missing={missing} spurious={spurious}")
        else:
            r, ok = out
            rows.append({"scenario": name, "pass": ok, "status": r.get("status")})
            print(f"{'PASS' if ok else 'FAIL'}  {name:<24} checked={ok}")

    for name, fn in (("contract_passthrough", scen_contract_passthrough),
                     ("refused_bad_json", scen_refused_bad_json),
                     ("refused_not_object", scen_refused_not_object),
                     ("refused_missing_file", scen_refused_missing_file),
                     ("refused_case_id_kept", scen_refused_case_id_kept),
                     ("exit_code_undetermined", scen_exit_code_undetermined)):
        r, ok = fn()
        rows.append({"scenario": name, "pass": ok, "status": r.get("status")})
        print(f"{'PASS' if ok else 'FAIL'}  {name:<24} checked={ok}")

    passed = sum(1 for x in rows if x["pass"])
    report = {"schema_version": "edit3-bench/v1", "scenarios": rows,
              "totals": {"passed": passed, "of": len(rows)},
              "note": ("Page-budget and record rules with false-positive guards, defensive "
                       "typing, the output_contract echo, and the refusal path (exit 5, no "
                       "traceback).")}
    (Path(__file__).resolve().parent / "report_edit3.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n{passed}/{len(rows)} scenarios pass")
    return 0 if passed == len(rows) else 1


if __name__ == "__main__":
    raise SystemExit(main())
