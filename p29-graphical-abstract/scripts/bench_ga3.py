"""Benchmark for the contract-pass and defensive-input rules of the GA skill.

The claim, provenance, glyph and determinism rules live in bench_ga.py and
bench_ga2.py. This file covers the polish-pass additions:

  four new audit rules      ga.empty_label, ga.legend_not_declared,
                            ga.reading_order_unknown_node, ga.source_values_invalid
  one widened rule          ga.value_not_in_source now also reads the caption
  defensive typing          a takeaways field that is not an object counts as
                            not declared, instead of crashing the audit
  the delivery contract     case_id and every declared output_contract field are
                            carried into result.json (spec-carried values pass
                            through verbatim, audit-derived fields are kept,
                            the rest become null with a limits note)
  the refusal path          an unreadable spec, a non-object spec and a missing
                            spec file all write an undetermined result.json and
                            answer with exit code 5 -- never a traceback

Every defect scenario ships with its false-positive guard: correct practice
(the legend declared, the order naming real panels, the caption free of
unsourced numbers) must stay silent.

    python bench_ga3.py
"""

from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import matplotlib.pyplot as plt  # noqa: E402

import ga_figure  # noqa: E402

OUT = Path(__file__).resolve().parent / "_run_ga3"

# A clean abstract: three declared takeaways, three traced panels, distinct
# colours WITH a declared legend, every number in source, order names real ids.
BASE = {
    "canvas_mm": [170, 70],
    "size_limit_mm": [180, 80],
    "max_words": 60,
    "font_size": 9,
    "source_values": ["42", "3"],
    "takeaways": {"problem": "p1", "method": "m1", "finding": "f1"},
    "reading_order": ["p1", "m1", "f1"],
    "legend": ["吸收缓慢", "多孔涂层 42 nm", "吸收快 3 倍"],
    "materials": [{"id": "mat1", "name": "缓慢吸收"},
                  {"id": "mat2", "name": "多孔涂层"},
                  {"id": "mat3", "name": "吸收速率"}],
    "nodes": [
        {"id": "p1", "label": "吸收缓慢", "evidence": "mat1", "layer": 0, "color": "#D55E00"},
        {"id": "m1", "label": "多孔涂层 42 nm", "evidence": "mat2", "layer": 1, "color": "#0072B2"},
        {"id": "f1", "label": "吸收快 3 倍", "evidence": "mat3", "layer": 2, "color": "#009E73"},
    ],
    "edges": [
        {"from": "p1", "to": "m1", "type": "activate"},
        {"from": "m1", "to": "f1", "type": "activate"},
    ],
}


def d(**over):
    s = copy.deepcopy(BASE)
    s.update(over)
    return s


def run(name: str, spec: dict, case_id: str | None = None) -> dict:
    p = OUT / name
    p.mkdir(parents=True, exist_ok=True)
    (p / "spec.json").write_text(json.dumps(spec, ensure_ascii=False), encoding="utf-8")
    return ga_figure.build_and_audit(p / "spec.json", p / "o", case_id=case_id)


# --- spec-expressible rule scenarios (defect + guard pairs) ---------------------

def scen_empty_label():
    s = d(nodes=[{**BASE["nodes"][0], "label": "  "},
                 {**BASE["nodes"][1]}, {**BASE["nodes"][2]}])
    return s, ["ga.empty_label"]


def scen_empty_label_fp():
    return d(), []


def scen_legend_missing():
    s = d()
    s.pop("legend")
    return s, ["ga.legend_not_declared"]


def scen_legend_exempt_fp():
    """Guard: colours that carry no meaning may opt out of the legend rule."""
    s = d()
    s.pop("legend")
    s["legend_exempt"] = True
    return s, []


def scen_order_unknown():
    s = d(reading_order=["p1", "m1", "fX"])
    return s, ["ga.reading_order_unknown_node"]


def scen_order_known_fp():
    return d(), []


def scen_source_values_type():
    s = d(source_values="42")
    return s, ["ga.source_values_invalid"]


def scen_takeaways_type():
    """A takeaways field that is not an object declares nothing: treated as
    not declared, the audit still returns a structured result."""
    s = d()
    s["takeaways"] = ["p1", "m1", "f1"]
    return s, ["ga.missing_takeaway"]


def scen_caption_number():
    """The caption is part of the figure: a number in it must trace to source too."""
    s = d(caption="涂层厚度 88 nm，速率对比见图注")
    return s, ["ga.value_not_in_source"]


def scen_caption_clean_fp():
    s = d(caption="速率对比见正文图 3")
    return s, []


# --- the delivery contract -------------------------------------------------------

CONTRACT = {"deliverable": "editable SVG plus 300 dpi PNG",
            "status": "whatever the audit decides",
            "reproducibility": "the second render must match",
            "reviewer_note": "checked against the source materials",
            "export_format": "png"}


def scen_contract_passthrough():
    """case_id is recorded; every declared contract field lands in the result.

    The audit-derived fields (status, reproducibility) keep the audited values --
    a spec-carried value must never override the honest one. A spec-carried
    field (deliverable, reviewer_note) passes through verbatim. A field neither
    side can fill (export_format is declared in the contract but carried
    nowhere) becomes null and is named in limits, never fabricated.
    """
    spec = d(case_id="case-demo-001", output_contract=dict(CONTRACT))
    spec["deliverable"] = CONTRACT["deliverable"]
    spec["reviewer_note"] = "panels traced to Methods paragraphs 1-3"
    r = run("contract", spec)
    ok = (r.get("case_id") == "case-demo-001"
          and r.get("deliverable") == CONTRACT["deliverable"]
          and r.get("reviewer_note") == "panels traced to Methods paragraphs 1-3"
          and r.get("status") in ("clean", "review", "blocked")
          and r.get("reproducibility", {}).get("deterministic") is True
          and r.get("export_format") is None
          and any("export_format" in x for x in r.get("limits", [])))
    return r, ok


# --- the refusal path ------------------------------------------------------------

def _refused_case(name: str, payload: str, case_id: str | None = None) -> tuple[dict, bool]:
    p = OUT / name
    p.mkdir(parents=True, exist_ok=True)
    if payload is not None:
        (p / "spec.json").write_text(payload, encoding="utf-8")
    r = ga_figure.build_and_audit(p / "spec.json", p / "o", case_id=case_id)
    ok = (r.get("status") == "undetermined"
          and any(f.get("rule") == "audit.no_section" for f in r.get("findings", []))
          and (p / "o" / "result.json").exists()
          and (case_id is None or r.get("case_id") == case_id))
    return r, ok


def scen_refused_bad_json():
    return _refused_case("refused_bad_json", "{not json at all]")


def scen_refused_not_object():
    return _refused_case("refused_not_object", "[1, 2, 3]")


def scen_refused_missing_file():
    return _refused_case("refused_missing_file", None)


def scen_refused_case_id_kept():
    """Even a refusal keeps a case identifier the command line carried."""
    return _refused_case("refused_case_id", "{bad]", case_id="case-demo-002")


def scen_exit_code_undetermined():
    ok = ga_figure.EXIT_CODES.get("undetermined") == 5
    r = {"status": "undetermined"}
    return r, ok


SCEN = [
    ("clean", scen_empty_label_fp),
    ("empty_label", scen_empty_label),
    ("legend_missing", scen_legend_missing),
    ("legend_exempt_fp", scen_legend_exempt_fp),
    ("order_unknown", scen_order_unknown),
    ("order_known_fp", scen_order_known_fp),
    ("source_values_type", scen_source_values_type),
    ("takeaways_type", scen_takeaways_type),
    ("caption_number", scen_caption_number),
    ("caption_clean_fp", scen_caption_clean_fp),
]


def main() -> int:
    rows = []
    for name, builder in SCEN:
        spec, expect = builder()
        r = run(name, spec)
        fired = {f["rule"] for f in r.get("findings", [])}
        missing = [x for x in expect if x not in fired]
        spurious = [] if expect else [f["rule"] for f in r.get("findings", [])]
        ok = not missing and not spurious
        rows.append({"scenario": name, "expected": expect, "fired": sorted(fired),
                     "missing": missing, "spurious": spurious, "pass": ok,
                     "status": r.get("status")})
        print(f"{'PASS' if ok else 'FAIL'}  {name:<24} missing={missing} spurious={spurious}")

    r, ok = scen_contract_passthrough()
    rows.append({"scenario": "contract_passthrough", "expected": ["case_id + contract fields"],
                 "fired": [], "missing": [] if ok else ["contract echo incomplete"],
                 "spurious": [], "pass": ok, "status": r.get("status")})
    print(f"{'PASS' if ok else 'FAIL'}  contract_passthrough")

    for name, fn in (("refused_bad_json", scen_refused_bad_json),
                     ("refused_not_object", scen_refused_not_object),
                     ("refused_missing_file", scen_refused_missing_file),
                     ("refused_case_id_kept", scen_refused_case_id_kept),
                     ("exit_code_undetermined", scen_exit_code_undetermined)):
        r, ok = fn()
        rows.append({"scenario": name, "expected": ["undetermined + result.json"],
                     "fired": [], "missing": [] if ok else ["refusal contract broken"],
                     "spurious": [], "pass": ok, "status": r.get("status")})
        print(f"{'PASS' if ok else 'FAIL'}  {name:<24} refused={ok}")

    plt.close("all")
    passed = sum(1 for x in rows if x["pass"])
    report = {"schema_version": "ga3-bench/v1", "scenarios": rows,
              "totals": {"passed": passed, "of": len(rows)},
              "note": ("Polish-pass rules (empty label, undeclared legend, unknown reading-order "
                       "node, mistyped source values, caption numbers) with false-positive guards, "
                       "the output_contract echo, and the refusal path (exit 5, no traceback).")}
    (Path(__file__).resolve().parent / "report_ga3.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n{passed}/{len(rows)} scenarios pass")
    return 0 if passed == len(rows) else 1


if __name__ == "__main__":
    raise SystemExit(main())
