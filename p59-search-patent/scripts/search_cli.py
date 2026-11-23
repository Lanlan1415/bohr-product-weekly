"""Run patent/technical-literature retrieval and write a replayable result.json.

Examples:
    python search_cli.py --corpus corpus.json --query-file query.json --out ./out
    python search_cli.py --case /input/case.json --corpus work/corpus.json \
        --query-file work/query.json --out /app/output
    python search_cli.py --index out/index.json --query "US 10,132,852 B2" --out ./replay

A case can supply case_id, output_contract, documents/corpus, and query.  Explicit
CLI inputs override those defaults.  Successful and partially successful runs echo
every declared output_contract field: engine values win, explicit case values are
used next, and unavailable values become null with a review finding.  A refused run
never echoes contract fields because no query was completed.

Exit codes: 0 clean, 3 review/partial, 4 blocked by source permission, 5
undetermined/refused, 2 command-line usage.  Every non-usage path writes result.json.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
import search  # noqa: E402

EXIT_CODES = {"clean": 0, "review": 3, "blocked": 4, "undetermined": 5}
_CONTRACT_ALIASES = {
    "results": "检索结果", "search_results": "检索结果", "retrieval_results": "检索结果",
    "evidence": "证据记录", "evidence_records": "证据记录",
    "evidence_and_sources": "证据记录", "run_state": "状态说明",
    "run_status": "状态说明", "state": "状态说明", "status_explanation": "状态说明",
}


def _write_result(out_dir: Path, result: dict) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "result.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")


def _refused(out_dir: Path, rule: str, message: str, case_id=None) -> dict:
    """Write an undetermined result; deliberately do not echo output_contract."""
    result = {"schema_version": search.SCHEMA_VERSION, "case_id": case_id,
              "ok": False, "status": "undetermined",
              "refusal": {"rule": rule, "message": message},
              "limits": ["no query was answered"],
              "uncertainty": ["no query was answered"]}
    _write_result(out_dir, result)
    return result


def _case_id(case: dict):
    value = case.get("case_id")
    if value is None or isinstance(value, (str, int)):
        return value
    return str(value)


def _contract_fields(contract) -> list:
    fields = []
    if isinstance(contract, dict):
        raw = list(contract)
    elif isinstance(contract, (list, tuple)):
        raw = list(contract)
    else:
        raw = []
    for entry in raw:
        if isinstance(entry, str):
            name = entry.strip()
        elif isinstance(entry, dict):
            name = str(entry.get("name") or entry.get("field") or entry.get("key") or "").strip()
        else:
            name = ""
        if name and name not in fields:
            fields.append(name)
    return fields


def contract_echo(case: dict, result: dict) -> list:
    """Fill declared fields on a completed run and return missing-field notes."""
    fields = _contract_fields(case.get("output_contract"))
    notes = []
    for field in fields:
        if result.get(field) is not None:
            continue
        value = case.get(field)
        if value is None or (isinstance(value, str) and not value.strip()):
            alias = _CONTRACT_ALIASES.get(field)
            if alias and result.get(alias) is not None:
                result[field] = result[alias]
                continue
            result[field] = None
            notes.append("output_contract field '" + field + "' has no evidenced value")
        else:
            result[field] = value
    if fields:
        result["output_contract_fields"] = fields
    return notes


def _read_json(path, label: str, out_dir: Path, case_id=None):
    try:
        value = json.loads(Path(path).read_text(encoding="utf-8"))
        return value, None
    except (json.JSONDecodeError, UnicodeDecodeError, OSError, ValueError) as exc:
        return None, _refused(out_dir, "search.spec_unreadable",
                              "the " + label + " file is not readable JSON: " + str(exc), case_id)


def _merge_wrapper(case: dict, wrapper: dict) -> dict:
    """Wrapper metadata supplements --case; explicit case values take precedence."""
    merged = {key: value for key, value in wrapper.items()
              if key in {"case_id", "output_contract", "query", "search_query"}}
    merged.update(case)
    return merged


def _unwrap_query(data):
    if isinstance(data, dict) and "query" in data and not (
            set(data) & ({"all", "any", "not", "filters"} | search._FILTER_KEYS)):
        return data["query"]
    return data


def _with_source_defaults(documents: list, wrapper: dict) -> list:
    defaults = {key: wrapper[key] for key in search.SOURCE_FIELDS
                if key in wrapper and not isinstance(wrapper[key], (dict, list))}
    if not defaults:
        return documents
    out = []
    for entry in documents:
        if isinstance(entry, dict):
            item = dict(entry)
            for key, value in defaults.items():
                item.setdefault(key, value)
            out.append(item)
        else:
            out.append(entry)
    return out


def run_files(corpus_path, index_path, query_path, query_str, out_dir: Path,
              case_path=None) -> dict:
    case: dict = {}
    if case_path:
        data, refusal = _read_json(case_path, "case", out_dir)
        if refusal:
            return refusal
        if not isinstance(data, dict):
            return _refused(out_dir, "search.spec_unreadable", "the case must be a JSON object")
        case = data

    spec: dict = {}
    if index_path and corpus_path:
        return _refused(out_dir, "search.empty_corpus",
                        "use exactly one of --corpus / --index", _case_id(case))
    if index_path:
        idx, refusal = _read_json(index_path, "index", out_dir, _case_id(case))
        if refusal:
            return refusal
        if not isinstance(idx, dict):
            return _refused(out_dir, "search.index_malformed",
                            "the index file is not a JSON object", _case_id(case))
        spec["index"] = idx
    elif corpus_path:
        data, refusal = _read_json(corpus_path, "corpus", out_dir, _case_id(case))
        if refusal:
            return refusal
        if isinstance(data, list):
            spec["corpus"] = data
        elif isinstance(data, dict) and isinstance(data.get("documents"), list):
            case = _merge_wrapper(case, data)
            spec["corpus"] = _with_source_defaults(data["documents"], data)
        elif isinstance(data, dict) and isinstance(data.get("corpus"), list):
            case = _merge_wrapper(case, data)
            spec["corpus"] = _with_source_defaults(data["corpus"], data)
        else:
            return _refused(out_dir, "search.empty_corpus",
                            "the corpus file holds no documents/corpus list", _case_id(case))
    elif isinstance(case.get("documents"), list):
        spec["corpus"] = _with_source_defaults(case["documents"], case)
    elif isinstance(case.get("corpus"), list):
        spec["corpus"] = _with_source_defaults(case["corpus"], case)
    else:
        return _refused(out_dir, "search.empty_corpus",
                        "no corpus, index, or case document list was given", _case_id(case))

    if query_path:
        data, refusal = _read_json(query_path, "query", out_dir, _case_id(case))
        if refusal:
            return refusal
        if isinstance(data, dict):
            case = _merge_wrapper(case, data)
        spec["query"] = _unwrap_query(data)
    elif query_str is not None:
        spec["query"] = query_str
    elif case.get("query") is not None:
        spec["query"] = case["query"]
    elif case.get("search_query") is not None:
        spec["query"] = case["search_query"]
    else:
        return _refused(out_dir, "search.empty_query",
                        "no query was given (--query, --query-file, or case query)", _case_id(case))

    try:
        index, result = search.search(spec)
    except Exception as exc:  # hostile inputs become a traceable refusal, never a traceback
        return _refused(out_dir, "search.internal_error",
                        "the search could not complete: " + type(exc).__name__, _case_id(case))
    if index is None:
        result["case_id"] = _case_id(case)
        _write_result(out_dir, result)
        return result

    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "index.json").write_text(
        json.dumps(index, ensure_ascii=False, indent=2), encoding="utf-8")
    result["case_id"] = _case_id(case)
    notes = contract_echo(case, result)
    if notes:
        result.setdefault("findings", []).append({
            "rule": "patent.contract_field_missing", "severity": "medium",
            "message": "one or more declared output_contract fields have no evidenced value",
            "entries": [{"field": field, "value": None}
                        for field in _contract_fields(case.get("output_contract"))
                        if result.get(field) is None],
            "count": len(notes),
        })
        result["limits"] = list(result.get("limits") or []) + notes
        result.setdefault("change_records", []).append({
            "stage": "contract", "action": "write_null_for_unevidenced_fields",
            "notes": notes, "values_fabricated": False})
    search._finalise(result, index["documents"])
    _write_result(out_dir, result)
    return result


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="patent-search", description=__doc__)
    parser.add_argument("--case", default=None, help="platform case.json (metadata and defaults)")
    parser.add_argument("--corpus", default=None, help="corpus JSON (documents list)")
    parser.add_argument("--index", default=None, help="previously built index.json")
    parser.add_argument("--query", default=None, help="bare text or patent number")
    parser.add_argument("--query-file", default=None, help="query JSON")
    parser.add_argument("--out", required=True, help="output directory")
    args = parser.parse_args(argv)
    try:
        result = run_files(args.corpus, args.index, args.query_file, args.query,
                           Path(args.out), args.case)
    except Exception as exc:  # includes odd path types and unforeseen malformed structures
        result = _refused(Path(args.out), "search.internal_error",
                          "the runner could not complete: " + type(exc).__name__)
    print(json.dumps({"status": result.get("status", "undetermined"),
                      "case_id": result.get("case_id"),
                      "empty": result.get("empty"),
                      "hits": len(result.get("hits") or []),
                      "findings": [f.get("rule") for f in result.get("findings") or []],
                      "refusal": result.get("refusal")}, ensure_ascii=False))
    return EXIT_CODES.get(result.get("status"), 5)


if __name__ == "__main__":
    raise SystemExit(main())
