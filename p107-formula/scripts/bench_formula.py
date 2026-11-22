"""Benchmark for the formula-parsing skill.

One scenario per rule, aligned to the scoring points this task states:

  a usable structured expression, not just a LaTeX line  -> unbalanced_*
  symbols/superscripts/Greek/units correspond            -> variable_not_extracted, unit_*
  variable explanations follow the original definition   -> variable_undefined/no_locator
  the numeric substitution actually computes             -> substitution_mismatch
  variable table, derivation, boundary conditions        -> derivation_missing,
                                                            boundary_conditions_missing,
                                                            verification_missing

    python bench_formula.py
"""

from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import sections as S  # noqa: E402

BASE = {
    "formulas": [
        {"id": "F1",
         "latex": "E = h c / \\lambda",
         "lhs_unit": "J", "rhs_unit": "J",
         "variables": [
             {"name": "E", "definition": "photon energy", "source": "paper",
              "locator": "Eq. 1, p.3", "unit": "J"},
             {"name": "h", "definition": "Planck constant", "source": "convention",
              "locator": "Eq. 1, p.3", "unit": "J*s"},
             {"name": "c", "definition": "speed of light", "source": "convention",
              "locator": "Eq. 1, p.3", "unit": "m/s"},
             {"name": "\u03bb", "definition": "wavelength", "source": "paper",
              "locator": "Eq. 1, p.3", "unit": "m"},
         ],
         "steps": [{"from": "E = h \u03bd", "to": "E = h c / \u03bb",
                    "justification": "\u03bd = c / \u03bb for light in vacuum"}],
         "boundary_conditions": "single photon, vacuum",
         "verified": True,
         "numeric": {"expression": "h*c/lambda",
                     "inputs": {"h": 6.626e-34, "c": 2.998e8, "lambda": 5.32e-7},
                     "expected": 3.734e-19, "tolerance": 1e-21}},
    ]
}


def d(**over):
    s = copy.deepcopy(BASE)
    s.update(over)
    return s


def f(**over):
    s = copy.deepcopy(BASE)
    s["formulas"] = copy.deepcopy(BASE["formulas"])
    s["formulas"][0].update(over)
    return s


def var(index, **over):
    s = copy.deepcopy(BASE)
    s["formulas"] = copy.deepcopy(BASE["formulas"])
    s["formulas"][0]["variables"] = copy.deepcopy(BASE["formulas"][0]["variables"])
    s["formulas"][0]["variables"][index].update(over)
    return s


SCEN = [
    ("clean", lambda: (d(), [])),

    # structure
    ("unbalanced_braces",
     lambda: (f(latex="E = h c / \\lambda{"), ["formula.unbalanced_braces"])),
    ("unbalanced_delimiters",
     lambda: (f(latex="E = (h c / \\lambda"), ["formula.unbalanced_delimiters"])),

    # symbols and variables
    ("variable_not_extracted",
     lambda: (f(latex="E = h c / \\lambda + k T"), ["formula.variable_not_extracted"])),
    ("variable_undefined", lambda: (var(1, definition=""), ["formula.variable_undefined"])),
    ("variable_source_undeclared",
     lambda: (var(1, source=""), ["formula.variable_source_undeclared"])),
    ("variable_no_locator", lambda: (var(1, locator=""), ["formula.variable_no_locator"])),

    # dimensions
    ("dimension_mismatch",
     lambda: (f(lhs_unit="J", rhs_unit="Pa"), ["formula.dimension_mismatch"])),
    ("unit_unknown", lambda: (f(rhs_unit="flurbles"), ["formula.unit_unknown"])),

    # derivation
    ("derivation_missing", lambda: (f(steps=[]), ["formula.derivation_missing"])),
    ("step_incomplete",
     lambda: (f(steps=[{"from": "E = h \u03bd", "justification": "x"}]),
              ["formula.step_incomplete"])),
    ("step_unjustified",
     lambda: (f(steps=[{"from": "E = h \u03bd", "to": "E = h c / \u03bb"}]),
              ["formula.step_unjustified"])),

    # conditions and verdict
    ("boundary_missing", lambda: (f(boundary_conditions=""), ["formula.boundary_conditions_missing"])),
    ("verification_missing", lambda: (f(verified=None), ["formula.verification_missing"])),

    # numeric substitution
    ("substitution_mismatch",
     lambda: (f(numeric={"expression": "h*c/lambda",
                         "inputs": {"h": 6.626e-34, "c": 2.998e8, "lambda": 5.32e-7},
                         "expected": 9.99e-19, "tolerance": 1e-21}),
              ["formula.substitution_mismatch"])),
    ("numeric_incomplete",
     lambda: (f(numeric={"expression": "h*c/lambda"}), ["formula.numeric_incomplete"])),
    ("substitution_not_evaluable",
     lambda: (f(numeric={"expression": "h*c/unknown_symbol",
                         "inputs": {"h": 1.0}, "expected": 2.0, "tolerance": 1e-9}),
              ["formula.substitution_not_evaluable"])),

    ("no_items", lambda: (d(formulas=[]), ["formula.no_items"])),

    # multi-character script without braces typesets as only its first character
    ("bare_script", lambda: (d(formulas=[{**copy.deepcopy(BASE["formulas"][0]),
                                          "latex": "E = h c / \\lambda_12"}]),
                             ["formula.bare_script"])),
    # a declared cross-formula dependency must resolve
    ("step_unknown_dependency", lambda: (d(formulas=[{**copy.deepcopy(BASE["formulas"][0]),
                                                      "steps": [{"from": "E = h ν",
                                                                 "to": "E = h c / \\lambda",
                                                                 "justification": "substitute ν from F9",
                                                                 "uses": ["F9"]}]}]),
                                         ["formula.step_unknown_dependency"])),

    # --- matrix / piecewise environments (认得准) -----------------------
    ("environment_unclosed",
     lambda: (f(latex="E = h c / \\lambda \\begin{cases}"),
              ["formula.environment_unclosed"])),
    ("fp_env_balanced",
     lambda: (f(latex="E = h c / \\lambda \\begin{cases} h c \\end{cases}"), [])),

    # --- the substitution is anchored to the table (讲得清 + 算得回) ------
    ("numeric_input_undeclared",
     lambda: (f(numeric={"expression": "h*c/lambda",
                         "inputs": {"h": 6.626e-34, "c": 2.998e8, "lambda": 5.32e-7,
                                    "T": 300},
                         "expected": 3.734e-19, "tolerance": 1e-21}),
              ["formula.numeric_input_undeclared"])),
    ("input_value_conflicts_variable",
     lambda: (var(1, value=1e-34),
              ["formula.input_value_conflicts_variable"])),
    ("fp_input_value_match", lambda: (var(1, value=6.626e-34), [])),

    # --- dependencies named in the step text (推得顺) --------------------
    ("step_dependency_undeclared",
     lambda: (d(formulas=[{**copy.deepcopy(BASE["formulas"][0]),
                           "steps": [{"from": "E = h ν", "to": "E = h c / λ",
                                      "justification": "substitute ν = c / λ from F2"}]}]),
              ["formula.step_dependency_undeclared"])),

    # --- the pass bound is declared (算得回) ------------------------------
    ("tolerance_undeclared",
     lambda: (f(numeric={"expression": "h*c/lambda",
                         "inputs": {"h": 6.626e-34, "c": 2.998e8, "lambda": 5.32e-7},
                         "expected": 3.734e-19}),
              ["formula.tolerance_undeclared"])),
    ("numeric_malformed", lambda: (f(numeric="h*c/lambda"),
                                   ["formula.numeric_malformed"])),
    ("no_numeric_check", lambda: (f(numeric=None), ["formula.no_numeric_check"])),
    ("fp_note_numeric_false", lambda: (f(numeric=None, note_numeric=False), [])),

    # false-positive guards
    ("fp_dimensionless", lambda: (d(formulas=[{**copy.deepcopy(BASE["formulas"][0]),
                                               "variables": copy.deepcopy(BASE["formulas"][0]["variables"])
                                               + [{"name": "π",
                                                   "definition": "circle ratio",
                                                   "source": "convention",
                                                   "locator": "Eq. 1, p.3",
                                                   "unit": "",
                                                   "dimensionless": True}]}]), [])),
    ("fp_braced_script", lambda: (d(formulas=[{**copy.deepcopy(BASE["formulas"][0]),
                                               "latex": "E = h c / \\lambda_{12}"}]), [])),
]


def main() -> int:
    rows = []
    for name, builder in SCEN:
        spec, expect = builder()
        findings, status, counts = S.run(spec, "formula")
        fired = {f["rule"] for f in findings}
        missing = [r for r in expect if r not in fired]
        spurious = [] if expect else [f["rule"] for f in findings]
        ok = not missing and not spurious
        rows.append({"scenario": name, "expected": expect, "fired": sorted(fired),
                     "missing": missing, "spurious": spurious, "pass": ok,
                     "status": status})
        print(f"{'PASS' if ok else 'FAIL'}  {name:<26} missing={missing} spurious={spurious}")

    passed = sum(1 for r in rows if r["pass"])
    report = {"schema_version": "formula-bench/v1", "scenarios": rows,
              "totals": {"passed": passed, "of": len(rows)},
              "note": ("One scenario per rule, aligned to the formula scoring points. "
                       "Clean baselines must report nothing.")}
    (Path(__file__).resolve().parent / "report_formula.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n{passed}/{len(rows)} pass")
    return 0 if passed == len(rows) else 1


if __name__ == "__main__":
    raise SystemExit(main())
