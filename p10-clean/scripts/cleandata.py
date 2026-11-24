"""Clean and standardise an extracted literature table, emitting a reviewable ledger.

The result carries, per the task's output requirements:

  case_id            the input identifier, echoed from the spec (or --case file)
  output_contract_*  every field the case's output_contract names (kept when the
                     result already carries it, copied verbatim when the spec
                     supplies it, null + a limit note when it cannot be derived)
  changes[]          the row-level change ledger (rule, row, column, original, new, why)
  pending_review     the to-confirm list the engine refuses to decide by itself
  cleaned_table      the analysable table, also written as cleaned.csv

Exit codes: 0 clean, 3 review, 4 blocked, 5 undetermined (refused, never a crash).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import cleaning as C  # noqa: E402

# Fields that are bulky inputs rather than results: never copied wholesale into
# the result by the contract echo (the ledger and cleaned table carry their
# audited substance already).
_BULKY = {"output_contract", "spec", "rows", "columns", "table", "table_path",
          "key_columns", "value_columns", "missing_tokens", "field_aliases",
          "synonyms", "source_column", "quality_report"}


def load_rows(path: Path, encoding: str = "utf-8-sig") -> list:
    """Decode only the explicitly selected encoding; never repair mojibake silently."""
    encoding = encoding if isinstance(encoding, str) and encoding.strip() else "utf-8-sig"
    raw = Path(path).read_bytes().decode(encoding, errors="strict")
    if Path(path).suffix.lower() == ".json":
        data = json.loads(raw)
        if isinstance(data, list):
            return data
        if isinstance(data, dict):
            return data.get("rows", [])
        return []
    import csv
    import io
    first = raw.splitlines()[0] if raw.strip() else ""
    delim = "\t" if first.count("\t") > first.count(",") else ","
    return list(csv.DictReader(io.StringIO(raw), delimiter=delim))


def _refused(out_dir: Path, message: str, rule: str = "clean.spec_unreadable",
             source: dict | None = None) -> dict:
    """Structured undetermined result, including every readable contract field.

    A refusal never pretends to be a success; missing derived fields are null and
    explicitly limited. Case values are echoed only when present and readable.
    """
    source = source if isinstance(source, dict) else {}
    result = {"schema_version": "cleandata/v2",
              "case_id": source.get("case_id", "UNKNOWN"), "status": "undetermined",
              "findings": [{"rule": rule, "severity": "high", "message": message}],
              "limits": ["the case could not be run as declared"],
              "refusal": {"code": rule, "message": message}}
    contract = source.get("output_contract")
    if isinstance(contract, dict):
        for key in contract:
            if key in result:
                continue
            if key in source and key not in _BULKY:
                result[key] = source[key]
            else:
                result[key] = None
                result["limits"].append("output_contract field '%s' was not derivable because the run was refused" % key)
    elif contract is not None:
        result["limits"].append("output_contract is not an object; field names were not guessed")
    out_dir = Path(out_dir); out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n",
                                         encoding="utf-8")
    return result


def _echo_contract(result: dict, spec: dict) -> dict:
    """Echo case_id and every output_contract field into the result.

    A field the result already carries is kept as computed; a field the spec
    supplies (and that is not a bulky input) passes through verbatim; anything
    else is null with a limits note — never a fabricated value.
    """
    if not isinstance(spec, dict):
        return result
    cid = spec.get("case_id")
    if cid is not None and "case_id" not in result:
        result["case_id"] = cid
    limits = result.setdefault("limits", [])
    contract = spec.get("output_contract")
    if contract is None:
        return result
    if not isinstance(contract, dict):
        limits.append("output_contract is not an object, so no field was echoed")
        return result
    for key in contract:
        if key in result:
            continue
        if key in spec and key not in _BULKY:
            result[key] = spec[key]
            continue
        result[key] = None
        limits.append(f"output_contract field '{key}' was not derivable by this cleaning pass")
    return result


def _merge_case(spec: dict, case_path) -> dict:
    """Copy case_id / output_contract from the case file when the spec omits them.

    The runtime case file (/input/case.json) is the authoritative carrier of both;
    a spec assembled by hand may forget them, so the CLI can pull them in. An
    unreadable case file is never fatal — the run just proceeds without the echo.
    """
    if case_path is None:
        return spec
    try:
        case = json.loads(Path(case_path).read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return spec
    if not isinstance(case, dict):
        return spec
    if spec.get("case_id") is None and case.get("case_id") is not None:
        spec["case_id"] = case.get("case_id")
    if spec.get("output_contract") is None and case.get("output_contract") is not None:
        spec["output_contract"] = case.get("output_contract")
    return spec


def _normalise_spec(spec):
    """Accept either native columns or Frictionless-style data_dictionary.fields."""
    if not spec.get("columns") and isinstance(spec.get("data_dictionary"), dict):
        fields = spec["data_dictionary"].get("fields")
        if isinstance(fields, list):
            columns = []
            for field in fields:
                if not isinstance(field, dict) or not field.get("name"):
                    continue
                col = dict(field)
                col["semantic"] = field.get("semantic") or field.get("type") or "numeric"
                for key in (field.get("constraints") or {}):
                    col[key] = field["constraints"][key]
                columns.append(col)
            spec["columns"] = columns
    if spec.get("rows") is None and isinstance(spec.get("records"), list):
        spec["rows"] = spec["records"]
    return spec


def build_and_audit(spec_path: Path, out_dir: Path, case_path=None) -> dict:
    if spec_path is None and case_path is not None:
        spec_path = Path(case_path)
    out_dir = Path(out_dir); out_dir.mkdir(parents=True, exist_ok=True)
    case = None
    if case_path is not None:
        try:
            case = json.loads(Path(case_path).read_text(encoding="utf-8-sig"))
            if not isinstance(case, dict):
                return _refused(out_dir, "case.json is not a JSON object", rule="clean.case_unreadable")
        except (OSError, json.JSONDecodeError, UnicodeDecodeError) as exc:
            return _refused(out_dir, "case.json could not be read: %s" % str(exc)[:200],
                            rule="clean.case_unreadable")
    try:
        spec = json.loads(Path(spec_path).read_text(encoding="utf-8-sig"))
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        return _refused(out_dir, "the spec file is not readable JSON: %s" % exc, source=case)
    except OSError:
        return _refused(out_dir, "the spec file could not be read (missing or inaccessible)", source=case)
    if not isinstance(spec, dict):
        return _refused(out_dir, "the spec file is not a JSON object", source=case)
    spec = _merge_case(spec, case_path)
    spec = _normalise_spec(spec)

    rows = spec.get("rows")
    if rows is None:
        table = spec.get("table") or spec.get("table_path")
        if not table:
            return _refused(out_dir, "the case supplies neither rows nor a table_path",
                            rule="clean.no_table", source=spec)
        try:
            rows = load_rows(Path(table) if Path(table).is_absolute()
                             else Path(spec_path).parent / table,
                             encoding=spec.get("source_encoding") or "utf-8-sig")
        except OSError:
            return _refused(out_dir, "the table file could not be read: " + str(table),
                            rule="clean.table_unreadable", source=spec)
        except (UnicodeDecodeError, LookupError) as exc:
            detail = "byte %s" % exc.start if isinstance(exc, UnicodeDecodeError) else "unknown encoding"
            return _refused(out_dir,
                            "the table file is not decodable in the explicitly selected encoding "
                            "(%s): %s" % (detail, table), rule="clean.table_unreadable", source=spec)
        except json.JSONDecodeError as exc:
            return _refused(out_dir, "the table file is not parseable JSON: " + str(exc),
                            rule="clean.table_unreadable", source=spec)

    if not isinstance(rows, list):
        return _refused(out_dir, "spec.rows is not a list, so there is no table to clean", source=spec)
    if not any(isinstance(r, dict) for r in rows):
        return _refused(out_dir,
                        "the table has no record rows (empty list, or entries that are not JSON objects)",
                        rule="clean.no_rows", source=spec)

    spec["rows"] = rows
    try:
        result = C.clean(rows, spec)
        import structured as S
        result = S.enrich(result, rows, spec)
    except (ValueError, TypeError, AttributeError, KeyError, OverflowError) as exc:
        return _refused(out_dir, "normalisation could not be completed without guessing: %s" % str(exc)[:200],
                        rule="clean.processing_error", source=spec)
    result["schema_version"] = "cleandata/v2"
    result["limits"] = []
    if not spec.get("columns"):
        result["limits"].append("no column schema declared; only duplicates and identity were checked")

    # The fingerprint covers both the raw rows and the effective rule declaration,
    # so a corrected schema is a legitimate new run. Re-running identical input
    # writes the same outputs again (true idempotence), not a second stacked edit.
    import hashlib as _hl
    rules_view = {k: v for k, v in spec.items() if k not in ("rows", "output_contract", "case_id")}
    input_sha = _hl.sha256(json.dumps({"rows": rows, "rules": rules_view}, sort_keys=True,
                                      ensure_ascii=False).encode("utf-8")).hexdigest()[:16]
    result["original_sha256"] = input_sha
    result["rerun_policy"] = "same input + rules + output path is an idempotent overwrite, never a stacked conversion"
    _echo_contract(result, spec)
    (out_dir / "result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n",
                                         encoding="utf-8")
    if result.get("cleaned_table"):
        import csv
        cols = spec.get("columns") or []
        header = [c["name"] for c in cols if isinstance(c, dict) and c.get("name")]
        if not header or any(h not in result["cleaned_table"][0] for h in header):
            header = list(result["cleaned_table"][0].keys())
        with open(out_dir / "cleaned.csv", "w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=header, extrasaction="ignore")
            w.writeheader()
            w.writerows(result["cleaned_table"])
    S.write_analysis_csv(result, out_dir / "analysis.csv")
    return result


def main(argv: list[str] | None = None) -> int:
    import argparse
    ap = argparse.ArgumentParser(prog="cleandata", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--spec", default=None,
                    help="native spec; when omitted, --case itself must contain rows/records or table_path")
    ap.add_argument("--out", required=True)
    ap.add_argument("--case", default=None,
                    help="runtime case file (/input/case.json) supplying case_id and "
                         "output_contract when the spec omits them")
    a = ap.parse_args(argv)
    if a.spec is None and a.case is None:
        ap.error("supply --spec, or --case for a self-contained case")
    r = build_and_audit(Path(a.spec) if a.spec is not None else None, Path(a.out), a.case)
    print(json.dumps({"status": r["status"],
                      "case_id": r.get("case_id"),
                      "findings": [f["rule"] for f in r["findings"]],
                      "rows": r.get("rows"), "idempotent": r.get("idempotent"),
                      "wrote": str(Path(a.out) / "result.json")}, ensure_ascii=False))
    return {"clean": 0, "review": 3, "blocked": 4, "undetermined": 5}.get(r["status"], 1)


if __name__ == "__main__":
    raise SystemExit(main())
