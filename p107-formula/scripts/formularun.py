#!/usr/bin/env python3
"""Recognise actual publisher MathML into a reviewable formula record and result.

Usage:
  python formularun.py --case /input/case.json --result /app/output/result.json

All generated definitions are explicitly marked pending paper evidence.  A missing
formula is an honest insufficiency, not an empty-but-successful reconstruction.
Exit codes: 0 complete numeric checks pass, 3 partial/review needed, 5 unreadable
case/no actual formula material.  Spec writing is deterministic; no scores are made.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
import latexmath as LM

SCHEMA = "formula-recognition/v1"


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def contract_fields(contract):
    if isinstance(contract, dict):
        return list(contract)
    if isinstance(contract, list):
        out = []
        for field in contract:
            if isinstance(field, str):
                out.append(field)
            elif isinstance(field, dict):
                for key in ("name", "field", "key", "id"):
                    if field.get(key) is not None:
                        out.append(str(field[key]))
                        break
        return out
    return []


def xml_candidates(directory: Path):
    preferred = ["artifacts/source-formulas.xml", "artifacts/publisher-source.xml",
                 "source-formulas.xml", "publisher-source.xml"]
    out = []
    for rel in preferred:
        p = directory / rel
        if p.is_file():
            out.append(p)
    if not out:
        # Avoid recursively consuming unrelated XML experiments or answer files.
        for p in sorted(directory.glob("*.xml")):
            if any(s in p.name.lower() for s in ("formula", "publisher", "jats", "article")):
                out.append(p)
    return out


def _definitions_from_text(text: str):
    """Only exact-pattern definitions marked to their actual paragraph can seed a row.

    This is a narrow recall aid, not a source of scientific guesses.  The workflow asks
    the reader to verify every definition/range/unit against its locator before finalizing.
    """
    definitions = {}
    pattern = r"(?P<name>\\?[A-Za-z]+|[α-ωΑ-Ω])(?:\s*\([^)]{1,24}\))?\s*(?:denotes|is defined as|represents|is the)\s+(?P<definition>[^.;]{2,180})"
    for match in __import__("re").finditer(pattern, text or "", flags=__import__("re").I):
        name = match.group("name").lstrip("\\")
        name = LM.GREEK.get(name, name)
        defs = definitions.setdefault(name, match.group("definition").strip())
        # First stated definition wins only within this exact text anchor; conflicts remain
        # for the reviewing reader, never silently merged as synonymous quantities.
        if definitions[name] != match.group("definition").strip():
            definitions[name] = None
    return definitions


def build(case: dict, input_dir: Path):
    limits, sources, records = [], [], []
    for path in xml_candidates(input_dir):
        try:
            text = path.read_text(encoding="utf-8-sig")
            parsed = LM.round_trip_mathml(text)
        except (OSError, UnicodeError, LM.ET.ParseError) as exc:
            limits.append("cannot parse %s: %s" % (path.name, str(exc)[:160]))
            continue
        source_id = path.stem
        sources.append({"source_id": source_id, "path": str(path),
                        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                        "formula_nodes": parsed["count"]})
        for i, entered in enumerate(parsed["formulas"]):
            definitions = _definitions_from_text(text)
            variables = []
            for symbol in entered.get("symbols") or []:
                defined = definitions.get(symbol) or definitions.get(LM.GREEK_REVERSE.get(symbol, symbol))
                variables.append({"name": symbol, "definition": defined,
                                  "range": None, "unit": None,
                                  "source": "paper" if defined else None,
                                  "locator": "MathML source %s; verify definition in surrounding text" % entered["source_id"]})
            records.append({"id": "%s-F%d" % (source_id, i + 1),
                            "number": entered.get("number"),
                            "source_id": entered.get("source_id"),
                            "locator": "publisher XML source id %s" % entered["source_id"],
                            "latex": entered.get("latex"), "preserve_scripts": True,
                            "variables": variables, "steps": [],
                            "boundary_conditions": None,
                            "verified": False,
                            "recognition": entered.get("parse"),
                            "verification": "undetermined: definition, assumptions, dimensional and numeric checks require source evidence"})
    return records, sources, limits


def render(case: dict, records: list, sources: list, limits: list):
    record_path = "formula-record.json"
    numeric = {}
    undetermined = []
    for f in records:
        numeric[f["id"]] = {"dimensional": LM.dimensional_check(f) if f.get("lhs_unit") or any(v.get("unit") for v in f["variables"]) else {"status": "undetermined", "reason": "no sourced unit declarations yet"},
                            "numeric": LM.numeric_check(f), "steps": LM.derivation_check(f)}
        undetermined.append(f["id"])
    if records:
        limits.append("Recognition preserves MathML structure; prose definitions, ranges, units and derivation assumptions still require source verification.")
        limits.append("No scalar evaluation is claimed for unsupported matrix/piecewise/special-function constructs.")
        status = "partial" if undetermined else "clean"
    else:
        limits.append("No parseable source-formula MathML was found; the provided material cannot support equation reconstruction.")
        status = "undetermined"
    result = {"schema_version": SCHEMA, "case_id": case.get("case_id"), "status": status,
              "formulas": records, "evidence_map": sources,
              "verification": numeric,
              "boundary": {"uncertainty": undetermined, "declared_limits": limits},
              "formula_record": record_path, "limits": limits,
              "recognition": {"mathml_only": True, "source_nodes": len(records)}}
    flat_vars = [dict(v, equation_id=f["id"], equation_number=f.get("number")) for f in records for v in f["variables"]]
    derivatives = [{"formula": f["id"], "steps": f["steps"]} for f in records]
    aliases = {"formula_records": records, "equations": records, "parsed_formulas": records,
               "variables": flat_vars, "variable_table": flat_vars,
               "derivations": derivatives, "evidence": sources, "sources": sources,
               "uncertainty": limits, "numerical_verification": numeric}
    for key in contract_fields(case.get("output_contract")):
        if key in result:
            continue
        if key in aliases:
            result[key] = aliases[key]
        elif key in case:
            result[key] = case[key]
        else:
            result[key] = None
            limits.append("output_contract field %r was not derivable from actual XML material" % key)
    return result


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--case", required=True)
    ap.add_argument("--input", help="source directory; defaults to the case directory")
    ap.add_argument("--result", required=True)
    ap.add_argument("--spec", help="also write sections/secrun-ready formula spec here")
    args = ap.parse_args(argv)
    result_path = Path(args.result)
    result_path.parent.mkdir(parents=True, exist_ok=True)
    case = {}
    try:
        case = load_json(Path(args.case))
        if not isinstance(case, dict):
            raise ValueError("case.json is not a JSON object")
    except (OSError, UnicodeError, ValueError) as exc:
        result = {"schema_version": SCHEMA, "status": "undetermined",
                  "findings": [{"rule": "formula.source_unreadable", "severity": "high",
                                "message": str(exc)[:240]}], "limits": ["case is unreadable"]}
        result_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps({"status": "undetermined", "rc": 5, "wrote": str(result_path)}, ensure_ascii=False))
        return 5
    input_dir = Path(args.input) if args.input else Path(args.case).resolve().parent
    try:
        records, sources, limits = build(case, input_dir)
        result = render(case, records, sources, limits)
        result_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        (result_path.parent / "formula-record.json").write_text(
            json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")
        if args.spec:
            spec = dict(case, section="formula", formulas=records)
            Path(args.spec).parent.mkdir(parents=True, exist_ok=True)
            Path(args.spec).write_text(json.dumps(spec, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception as exc:
        # A malformed node must never masquerade as a recognised formula or produce a trace-only result.
        result = {"schema_version": SCHEMA, "case_id": case.get("case_id"), "status": "undetermined",
                  "findings": [{"rule": "formula.parser_error", "severity": "high", "message": str(exc)[:240]}],
                  "limits": ["recognition did not complete; no formulas were invented"]}
        for key in contract_fields(case.get("output_contract")):
            result.setdefault(key, case.get(key))
        result_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps({"status": "undetermined", "rc": 5, "wrote": str(result_path)}, ensure_ascii=False))
        return 5
    rc = 5 if not records else 3 if result["status"] in {"partial", "undetermined"} else 0
    print(json.dumps({"status": result["status"], "rc": rc, "sources": len(sources),
                      "formulas": len(records), "wrote": str(result_path)}, ensure_ascii=False))
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
