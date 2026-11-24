"""Executable regressions for MathML/LaTeX, units, substitution, steps and contracts.

The fixture is synthetic, created specifically for this verification; it is not an
official case, not an obtained public score and not a substitute for paper-level OCR.
"""
from __future__ import annotations

import copy
import json
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import latexmath as LM
import sections as S


def checks():
    out = []
    def ok(name, condition, detail=""):
        out.append({"scenario": name, "pass": bool(condition), "detail": str(detail)})
        print(("PASS " if condition else "FAIL ") + name + (" :: " + str(detail) if detail and not condition else ""))

    xml = """<article xmlns:mml='http://www.w3.org/1998/Math/MathML'>
      <mml:math id='m1'><mml:semantics><mml:mrow><mml:mi>E</mml:mi><mml:mo>=</mml:mo>
      <mml:mfrac><mml:mrow><mml:mi>h</mml:mi><mml:mi>c</mml:mi></mml:mrow><mml:msub><mml:mi>λ</mml:mi><mml:mn>0</mml:mn></mml:msub></mml:mfrac>
      <mml:mo>+</mml:mo><mml:msubsup><mml:mi>β</mml:mi><mml:mn>1</mml:mn><mml:mn>2</mml:mn></mml:msubsup></mml:mrow></mml:semantics></mml:math></article>"""
    cat = LM.catalog_mathml(xml)
    ok("mathml_fraction_scripts_greek_number", cat[0]["number"] is None and "\\frac" in cat[0]["latex"] and "_{0}" in cat[0]["latex"] and "^{2}" in cat[0]["latex"] and "beta" in cat[0]["latex"], cat[0])
    parsed_symbols = LM.symbols(cat[0]["latex"])
    ok("mathml_symbol_catalog", {"E", "h", "c", "λ_0", "β_1"} <= parsed_symbols, parsed_symbols)

    matrix = "<math xmlns='http://www.w3.org/1998/Math/MathML' id='m9'><mtable><mtr><mtd><msub><mi>x</mi><mn>1</mn></msub></mtd><mtd><msup><mi>α</mi><mn>2</mn></msup></mtd></mtr></mtable><mtext>(9)</mtext></math>"
    mat = LM.catalog_mathml(matrix)[0]
    ok("mathml_matrix_and_number", mat["number"] == "9" and "pmatrix" in mat["latex"] and "_{1}" in mat["latex"] and "alpha" in mat["latex"], mat)
    ok("known_arithmetic_F_ma", LM.evaluate("m a", {"m": 2.0, "a": 3.0}) == 6.0)
    ok("known_fraction_and_implicit_multiply", abs(LM.evaluate("\\frac{h c}{\\lambda}", {"h": 4.0, "c": 8.0, "lambda": 2.0}) - 16.0) < 1e-12)
    ok("greek_subscript_numeric_alias", LM.evaluate("k_B T", {"k_B": 2.0, "T": 4.0}) == 8.0)
    ok("full_greek_subscript_alias_both_directions",
       LM.evaluate("λ_1 + 1", {"lambda_1": 2.0}) == 3.0
       and LM.evaluate("lambda_1 + 1", {"λ_1": 2.0}) == 3.0,
       (LM.symbols("\\lambda_1 + 1"), LM.symbols("λ_1 + 1")))
    try:
        LM.evaluate("λ_1", {"λ_1": 2.0, "lambda_1": 3.0})
        alias_conflict = False
    except LM.MathUndetermined as exc:
        alias_conflict = "ambiguous" in str(exc)
    ok("conflicting_aliases_are_not_silently_overwritten", alias_conflict)
    try:
        got = LM.evaluate("\\int_0^1 x\\,dx", {"x": 1})
        ok("unsupported_integrals_are_not_zero", False, got)
    except LM.MathUndetermined:
        ok("unsupported_integrals_are_not_zero", True)

    def formula(**kw):
        f = {"id": "unit-force", "latex": kw.pop("latex", "F = m a"),
             "lhs_unit": "N", "rhs_unit": "N",
             "variables": [
                 {"name": "F", "definition": "force", "source": "paper", "locator": "Eq. 1", "unit": "N", "range": "> 0"},
                 {"name": "m", "definition": "mass", "source": "paper", "locator": "p.2", "unit": "kg", "range": "> 0"},
                 {"name": "a", "definition": "acceleration", "source": "paper", "locator": "p.2", "unit": "m/s^2", "range": "finite"}],
             "steps": [], "boundary_conditions": "non-relativistic rigid body", "verified": True,
             "numeric": {"expression": "m a", "inputs": {"m": {"value": 2, "unit": "kg"}, "a": {"value": 3, "unit": "m/s^2"}},
                         "expected": {"value": 6, "unit": "N"}, "tolerance": 1e-12}}
        f.update(kw)
        return f

    f = formula()
    numeric = LM.numeric_check(f)
    ok("real_units_numeric_match", numeric["status"] == "match" and numeric["computed"] == 6, numeric)
    f2 = formula(numeric={"expression": "m a", "inputs": {"m": "2000 g", "a": "300 cm/s^2"}, "expected": "6 N", "tolerance": 1e-12})
    ok("prefix_unit_conversion_before_substitution", LM.numeric_check(f2)["status"] == "match", LM.numeric_check(f2))
    ok("automatic_dimension_derivation", LM.dimensional_check(f2)["status"] == "match", LM.dimensional_check(f2))
    wrong_units = formula(variables=[formula()["variables"][0], dict(formula()["variables"][1], unit="s"), formula()["variables"][2]])
    dimbad = LM.dimensional_check(wrong_units)
    ok("dimension_mismatch_is_explicit", dimbad["status"] == "mismatch", dimbad)
    unknown = formula(variables=[formula()["variables"][0], dict(formula()["variables"][1], unit="flurbles"), formula()["variables"][2]])
    ok("unknown_units_are_undetermined", LM.dimensional_check(unknown)["status"] == "undetermined")

    step_good = formula(steps=[{"from": "m a + 1", "to": "m a + 1", "justification": "identity", "check": True}])
    ok("derivation_match_has_numeric_delta", LM.derivation_check(step_good)[0]["status"] == "match")
    step_bad = formula(steps=[{"from": "m a + 1", "to": "m a + 2", "justification": "claimed cancellation", "check": True}])
    bad = LM.derivation_check(step_bad)[0]
    ok("derivation_error_location_and_delta", bad["status"] == "mismatch" and bad["step"] == 0 and bad["absolute_delta"] == -1, bad)
    step_unknown = formula(steps=[{"from": "a", "to": "a + unknown", "check": True}])
    unknown_step = LM.derivation_check(step_unknown)[0]
    ok("derivation_cannot_compute_is_undetermined", unknown_step["status"] == "undetermined" and "unknown" in unknown_step["reason"])

    spec = {"formulas": [formula()]}
    findings, status, _ = S.run(spec, "formula")
    # derivation_missing and no step issue are incidental here; clean executable guards
    # must not add dimension/step/numeric false positives to the existing audit.
    rules = {x["rule"] for x in findings}
    ok("legacy_no_false_positive_guard", not {"formula.dimension_inferred_mismatch", "formula.step_undetermined", "formula.substitution_mismatch"} & rules, sorted(rules))
    f3 = formula(steps=[{"from": "m a + 1", "to": "m a + 2", "justification": "bad", "check": True}])
    fired = {x["rule"] for x in S.run({"formulas": [f3]}, "formula")[0]}
    ok("sections_emits_real_step_error", "formula.step_math_mismatch" in fired, fired)
    duplicate = {"publisher_xml": "supplied", "formulas": [formula(number="(1)", id="a"), formula(number="1", id="b")]}
    dup = {x["rule"] for x in S.run(duplicate, "formula")[0]}
    ok("equation_number_conflict_detected", "formula.equation_number_duplicate" in dup)
    indexed = {"id": "ix", "preserve_scripts": True, "latex": "x_i = 2",
               "variables": [{"name": "x_i", "definition": "species i concentration", "source": "paper", "locator": "Eq. 2"}],
               "steps": [], "verified": True, "note_numeric": False}
    indexed_clean = {x["rule"] for x in S.run({"formulas": [indexed]}, "formula")[0]}
    ok("complete_indexed_symbol_not_false_positive", "formula.variable_not_extracted" not in indexed_clean and "formula.latex_unparsed" not in indexed_clean, indexed_clean)
    collapsed = dict(indexed, variables=[dict(indexed["variables"][0], name="x")])
    collapse_rules = {x["rule"] for x in S.run({"formulas": [collapsed]}, "formula")[0]}
    ok("index_loss_is_rejected_in_strict_mode", "formula.variable_not_extracted" in collapse_rules and "formula.latex_unparsed" not in collapse_rules, collapse_rules)

    with tempfile.TemporaryDirectory(prefix="formula_math_smoke_") as td:
        root = Path(td)
        (root / "artifacts").mkdir()
        source = "<article><math id='f1'><mfrac><mn>3</mn><mn>2</mn></mfrac><mtext>(1)</mtext></math></article>"
        (root / "artifacts" / "source-formulas.xml").write_text(source, encoding="utf-8")
        case = {"case_id": "local-math-smoke", "output_contract": {"formulas": "...", "custom": "...", "verification": "..."}, "custom": {"passed": "verbatim"}}
        (root / "case.json").write_text(json.dumps(case), encoding="utf-8")
        first = root / "out1"; second = root / "out2"
        a = subprocess.run([sys.executable, str(Path(__file__).with_name("formularun.py")), "--case", str(root / "case.json"), "--result", str(first / "result.json"), "--spec", str(root / "spec.json")], capture_output=True, text=True)
        b = subprocess.run([sys.executable, str(Path(__file__).with_name("formularun.py")), "--case", str(root / "case.json"), "--result", str(second / "result.json")], capture_output=True, text=True)
        ra = json.loads((first / "result.json").read_text(encoding="utf-8"))
        ok("recognition_cli_contract_and_exit", a.returncode == 3 and ra["case_id"] == case["case_id"] and ra["custom"] == case["custom"] and len(ra["formulas"]) == 1, (a.returncode, a.stdout, a.stderr))
        ok("recognition_deterministic_and_partial_honest", b.returncode == 3 and (first / "result.json").read_bytes() == (second / "result.json").read_bytes() and ra["recognition"]["source_nodes"] == 1)
        badcase = root / "bad.json"; badcase.write_text("[]", encoding="utf-8")
        c = subprocess.run([sys.executable, str(Path(__file__).with_name("formularun.py")), "--case", str(badcase), "--result", str(root / "refusal.json")], capture_output=True, text=True)
        ok("malformed_case_structured_refusal", c.returncode == 5 and json.loads((root / "refusal.json").read_text(encoding="utf-8"))["status"] == "undetermined" and not c.stderr)
    return out


def main():
    rows = checks()
    passed = sum(r["pass"] for r in rows)
    report = {"schema_version": "formula-executable-bench/v1", "synthetic": True,
              "scenarios": rows, "totals": {"passed": passed, "of": len(rows)}}
    (Path(__file__).resolve().parent / "report_math_execution.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print("%d/%d pass" % (passed, len(rows)))
    return 0 if passed == len(rows) else 1


if __name__ == "__main__":
    raise SystemExit(main())
