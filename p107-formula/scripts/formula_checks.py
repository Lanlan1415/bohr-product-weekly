"""Formula-specific executable checks layered onto the conservative presence audit."""
from __future__ import annotations

import re

import latexmath as LM


def _fmt_vector(dim):
    if not isinstance(dim, (list, tuple)):
        return dim
    return {k: v for k, v in zip(U.DIM_NAMES, dim) if v}


def _add(findings, rule, severity, message, **kw):
    findings.append({"rule": rule, "severity": severity, "message": message, **kw})


def executable_audit(spec: dict, findings: list[dict]) -> dict:
    """Audit declared formula quantity without requiring a unit for pure symbols.

    Meta findings are fired only where the task explicitly supplies the relevant
    catalog/check; a short plain-LaTeX-only case is not punished for not also having XML.
    """
    items = [f for f in spec.get("formulas") or [] if isinstance(f, dict)]
    sources_catalog = bool(spec.get("publisher_xml") or spec.get("source_formulas_xml"))
    numbers = {}
    evaluated = {}
    for idx, formula in enumerate(items):
        fid = str(formula.get("id") or "F%d" % (idx + 1))
        number = formula.get("number", formula.get("equation_number"))
        if number not in (None, ""):
            key = str(number).strip().strip("()[]").strip()
            if sources_catalog and key in numbers and numbers[key] != fid:
                _add(findings, "formula.equation_number_duplicate", "high",
                     "two catalogued formulas claim the same equation number; the source ID "
                     "must disambiguate them before cross-formula references can be reused",
                     formula=fid, number=key, conflicts_with=numbers[key])
            numbers.setdefault(key, fid)
        elif sources_catalog:
            _add(findings, "formula.equation_number_unrecovered", "medium",
                 "the publisher formula catalog is present but this formula's equation number "
                 "was not recovered; its dependencies cannot be located unambiguously", formula=fid)

        if formula.get("preserve_scripts") is True:
            # Explicitly indexed symbols must not be collapsed to an unindexed base.  The
            # opt-in flag preserves older short-LaTeX specs while making MathML catalogs strict.
            try:
                used = LM.symbols(str(formula.get("latex") or ""))
                declared = set()
                for value in formula.get("variables") or []:
                    if not isinstance(value, dict):
                        continue
                    name = str(value.get("name") or "").strip()
                    declared.add(LM.canonical_symbol(name))
                omitted = sorted(used - declared)
                if omitted:
                    _add(findings, "formula.variable_not_extracted", "high",
                         "an indexed/Greek symbol in the parsed expression is missing its exact variable row",
                         formula=fid, symbols=omitted[:12], preserve_scripts=True)
            except LM.MathUndetermined as exc:
                _add(findings, "formula.latex_unparsed", "high",
                     "a strict indexed-symbol formula cannot be parsed: " + str(exc), formula=fid)

        numeric = LM.numeric_check(formula)
        dimensional = LM.dimensional_check(formula) if formula.get("verify_dimensions", True) else {"status": "not_requested"}
        steps = LM.derivation_check(formula)
        evaluated[fid] = {"numeric": numeric, "dimensional": dimensional, "steps": steps}
        if numeric.get("status") == "mismatch":
            # Do not duplicate the legacy finding with identical semantics.  The rich
            # evidence_map still carries computed/expected/delta/tolerance.
            pass
        if dimensional.get("status") == "mismatch" and "formula.dimension_mismatch" not in {f.get("rule") for f in findings if f.get("formula") == fid}:
            _add(findings, "formula.dimension_inferred_mismatch", "high",
                 "declared variable-unit inference gives incompatible equation dimensions; "
                 "matching lhs_unit/rhs_unit labels cannot hide an internal expression mismatch",
                 formula=fid, dimensional=dimensional)
        # Explicitly-requested step checks must not pretend that missing values establish a
        # false step.  Mismatch and inability to compute are separate conclusions.
        for st in steps:
            if st.get("status") == "mismatch":
                _add(findings, "formula.step_math_mismatch", "high",
                     "the stated substitutions do not make this derivation transition equal; "
                     "the exact failing step is reported", formula=fid, step=st["step"],
                     from_value=st.get("from_value"), to_value=st.get("to_value"),
                     absolute_delta=st.get("absolute_delta"))
            elif st.get("status") == "undetermined":
                _add(findings, "formula.step_undetermined", "medium",
                     "a requested step check is undetermined, not verified: " + str(st.get("reason")),
                     formula=fid, step=st["step"])
    return evaluated


def enrich_findings(spec: dict, findings: list[dict]) -> list[dict]:
    evaluated = executable_audit(spec, findings)
    return evaluated


if __name__ == "__main__":  # simple cold-import-safe diagnostic, never part of main workflow
    import json
    print(json.dumps({"schema_version": "formula-executable/v1"}, ensure_ascii=False))


# imported late only for formatting vectors; keeps cold import without SymPy/ANTLR intact
import units as U
