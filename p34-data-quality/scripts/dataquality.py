"""Run reversible, dictionary-driven cleaning and write auditable case outputs.

Exit codes: 0 clean, 3 review, 4 blocked, 5 undetermined. Every readable case
keeps case_id and all output_contract keys, including structured refusals.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import cleaning as C  # noqa: E402
import contract as K  # noqa: E402
import quality_gates as Q  # noqa: E402


def _case_metadata(case_path) -> dict | None:
    if case_path is None:
        return None
    case, err = K.load_spec(Path(case_path))
    return case if err is None and isinstance(case, dict) else None


def _merge_case(spec: dict, case: dict | None) -> dict:
    if not isinstance(case, dict):
        return spec
    for key in ("case_id", "output_contract"):
        if spec.get(key) is None and case.get(key) is not None:
            spec[key] = case[key]
    # Contract fields sometimes carry their pass-through payload only on case.
    contract = spec.get("output_contract")
    keys = contract.keys() if isinstance(contract, dict) else contract if isinstance(contract, list) else []
    for key in keys:
        if isinstance(key, str) and key not in spec and key in case and key not in K.BULKY:
            spec[key] = case[key]
    return spec


def _decode_table(raw: bytes, declared=None) -> tuple[str | None, str | None, str | None]:
    encodings = [str(declared)] if declared else []
    if raw.startswith((b"\xff\xfe", b"\xfe\xff")):
        encodings.append("utf-16")
    encodings.extend(["utf-8-sig", "gb18030"])
    tried = []
    for encoding in encodings:
        if not encoding or encoding in tried:
            continue
        tried.append(encoding)
        try:
            return raw.decode(encoding), encoding, None
        except (UnicodeDecodeError, LookupError) as exc:
            last = str(exc)
    return None, None, "table decoding failed; tried " + ", ".join(tried) + ": " + last


def _validate_dictionary(spec: dict) -> str | None:
    columns = spec.get("columns")
    if columns is None:
        return None
    if not isinstance(columns, list):
        return "spec.columns must be a list of dictionary entries"
    allowed = {"", "numeric", "date", "categorical", "text", "id"}
    for i, col in enumerate(columns):
        if not isinstance(col, dict) or not isinstance(col.get("name"), str) or not col["name"].strip():
            return f"columns[{i}] needs a non-empty string name"
        semantic = col.get("semantic")
        if semantic is not None and not isinstance(semantic, str):
            return f"columns[{i}].semantic must be a string"
        if isinstance(semantic, str) and semantic.strip().lower() not in allowed:
            return f"columns[{i}].semantic '{semantic}' is unsupported; use numeric/date/categorical/text/id"
        if col.get("target_unit") is not None and not isinstance(col.get("target_unit"), str):
            return f"columns[{i}].target_unit must be a string"
        plausible = col.get("plausible")
        if plausible is not None:
            if not isinstance(plausible, (list, tuple)) or len(plausible) != 2:
                return f"columns[{i}].plausible must be [lower, upper]"
            import math
            if any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v)
                   for v in plausible) or plausible[0] > plausible[1]:
                return f"columns[{i}].plausible needs finite ordered numeric bounds"
    for key in ("key_columns", "value_columns", "missing_tokens"):
        value = spec.get(key)
        if value is not None and (not isinstance(value, list)
                                  or any(not isinstance(item, str) for item in value)):
            return f"spec.{key} must be a list of strings"
    return None


def _load_rows(spec: dict) -> tuple[list[dict], str, str | None, dict]:
    """Load inline rows or a delimited text table with explicit encoding evidence."""
    rows = spec.get("rows")
    if isinstance(rows, list):
        records = [r for r in rows if isinstance(r, dict)]
        if len(records) != len(rows):
            return [], "inline", "every inline row must be a JSON object", {}
        return records, "inline", None, {"encoding": "json", "delimiter": None}
    if rows is not None:
        return [], "inline", "spec.rows must be a list of row objects", {}
    table = spec.get("table_path")
    if not isinstance(table, str) or not table.strip():
        return [], "none", None, {}
    p = Path(table)
    if not p.is_file():
        return [], str(table), f"table_path is missing or not a regular file: {table}", {}
    try:
        raw_bytes = p.read_bytes()
    except OSError as exc:
        return [], str(table), f"the table file could not be read: {exc}", {}
    raw, encoding, decode_err = _decode_table(raw_bytes, spec.get("encoding"))
    if decode_err:
        return [], str(table), decode_err, {}
    metadata = {"encoding": encoding, "file_sha256": hashlib.sha256(raw_bytes).hexdigest(),
                "bytes": len(raw_bytes)}
    if not raw or not raw.strip():
        return [], str(table), None, metadata
    delimiter = spec.get("delimiter")
    if delimiter not in (",", "\t", ";", "|"):
        first = raw.splitlines()[0]
        delimiter = max((",", "\t", ";", "|"), key=lambda d: first.count(d))
    metadata["delimiter"] = delimiter
    try:
        reader = csv.DictReader(io.StringIO(raw, newline=""), delimiter=delimiter)
        headers = reader.fieldnames or []
        if not headers or any(h is None or not str(h).strip() for h in headers):
            return [], str(table), "the table has an empty or unnamed header", metadata
        folded = [str(h).strip() for h in headers]
        if len(set(folded)) != len(folded):
            return [], str(table), "duplicate header names would silently overwrite cells", metadata
        parsed = list(reader)
    except (csv.Error, TypeError, ValueError) as exc:
        return [], str(table), f"the delimited table could not be parsed: {exc}", metadata
    if any(None in row for row in parsed):
        return [], str(table), "at least one row has more cells than the header", metadata
    return parsed, str(table), None, metadata


def build_and_audit(spec_path: Path, out_dir: Path, case_path=None) -> dict:
    case = _case_metadata(case_path)
    spec, err = K.load_spec(spec_path)
    if err:
        return K.refused(out_dir, err, case)
    if not isinstance(spec, dict):
        return K.refused(out_dir, "the spec file is valid JSON but not an object", case)
    spec = _merge_case(spec, case)
    dictionary_error = _validate_dictionary(spec)
    if dictionary_error:
        return K.refused(out_dir, dictionary_error, spec, rule="clean.dictionary_refused")
    out_dir = Path(out_dir)
    try:
        out_dir.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        return K.refused(out_dir, f"the output directory could not be created: {exc}", spec)

    rows, source, load_err, input_metadata = _load_rows(spec)
    if load_err:
        return K.refused(out_dir, load_err, spec)
    if not rows:
        return K.refused(out_dir, "no rows to clean: no readable inline records or table rows "
                         f"were supplied ({source})", spec)

    input_sha = hashlib.sha256(json.dumps(rows, sort_keys=True, ensure_ascii=False)
                               .encode("utf-8")).hexdigest()[:16]
    prior = out_dir / "result.json"
    if prior.exists():
        try:
            prev = json.loads(prior.read_text(encoding="utf-8-sig"))
        except (json.JSONDecodeError, UnicodeDecodeError, OSError):
            prev = {}
        if prev.get("original_sha256") == input_sha:
            limits = ["re-cleaning the same input into the same directory is refused"]
            result = {"schema_version": "data-quality/v3", "status": "blocked",
                      "case_id": spec.get("case_id"),
                      "findings": [{"rule": "clean.already_cleaned", "severity": "high",
                                    "message": "this exact input was already cleaned here; "
                                               "the first result is left intact",
                                    "original_sha256": input_sha}],
                      "severity_counts": {"high": 1}, "original_sha256": input_sha,
                      "limits": limits}
            K.echo_contract(spec, result, limits)
            try:
                (out_dir / "result-refused.json").write_text(
                    json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
            except OSError:
                pass
            return result

    try:
        result = C.clean(rows, spec)
        result = Q.augment(result, rows, spec)
    except Exception as exc:
        return K.refused(out_dir, f"the cleaning/audit pass was refused: {exc}", spec)
    result["schema_version"] = "data-quality/v3"
    result["row_source"] = source
    result["input_metadata"] = input_metadata
    result["spec"] = spec
    result["case_id"] = spec.get("case_id")

    limits = list(result.get("limits") or [])
    if len(result.get("changes") or []) >= 2000:
        result["reversible_log_complete"] = False
        limits.append("the core ledger reached its 2000-entry cap; full undo is not verified")
    if result.get("case_id") is None:
        limits.append("case_id was absent from both spec and case metadata")
    K.echo_contract(spec, result, limits)
    result["limits"] = list(dict.fromkeys(limits))

    try:
        (out_dir / "original.json").write_text(json.dumps(rows, ensure_ascii=False, indent=2),
                                               encoding="utf-8")
        if result["cleaned_table"]:
            cols = sorted({k for r in result["cleaned_table"] for k in r})
            buf = io.StringIO(newline="")
            writer = csv.DictWriter(buf, fieldnames=cols, extrasaction="ignore", lineterminator="\n")
            writer.writeheader()
            writer.writerows(result["cleaned_table"])
            (out_dir / "cleaned.csv").write_text(buf.getvalue(), encoding="utf-8", newline="")
        (out_dir / "validation_results.json").write_text(
            json.dumps(result["validation_results"], ensure_ascii=False, indent=2), encoding="utf-8")
        (out_dir / "result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2),
                                             encoding="utf-8")
    except OSError as exc:
        result["status"] = "undetermined"
        result["limits"] = result["limits"] + [f"outputs could not be written: {exc}"]
    return result


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="dataquality", description=__doc__)
    ap.add_argument("--spec", required=True, help="constructed case spec JSON")
    ap.add_argument("--out", required=True, help="output directory")
    ap.add_argument("--case", default=None, help="original /input/case.json for contract echo")
    args = ap.parse_args(argv)
    result = build_and_audit(Path(args.spec), Path(args.out), args.case)
    print(json.dumps({"status": result.get("status"), "case_id": result.get("case_id"),
                      "findings": [f["rule"] for f in result.get("findings", [])],
                      "idempotent": result.get("idempotent"),
                      "validation": result.get("validation_summary"),
                      "wrote": str(Path(args.out) / "result.json")}, ensure_ascii=False))
    return {"clean": 0, "review": 3, "blocked": 4, "undetermined": 5}.get(result.get("status"), 1)


if __name__ == "__main__":
    raise SystemExit(main())
