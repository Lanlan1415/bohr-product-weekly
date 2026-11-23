"""CLI: index a document corpus and answer a boolean query with located passages.

    python search_cli.py --corpus corpus.json --query "缓冲液 配制" --out ./out
    python search_cli.py --corpus corpus.json --query-file query.json --out ./out
    python search_cli.py --index index.json --query-file query.json --out ./out

corpus.json holds {"documents": [...]} (or {"corpus": [...]}, or a bare list);
query.json holds {"all": [...], "any": [...]} or a bare string. Writes
out/index.json (the index, kept for replay) and out/result.json (the query
record, the index fingerprint, and hits with verbatim locators). Exit codes:
0 ok — including an honest empty hit list, 5 refused (unreadable files, empty
corpus, malformed index, empty query), 2 usage. A refusal still writes
result.json — the refusal is a result, not a crash.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import search  # noqa: E402
import incremental_tracker  # noqa: E402


def _write_result(out_dir: Path, result: dict) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "result.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")


def _refused(out_dir: Path, rule: str, message: str) -> dict:
    result = {"schema_version": search.SCHEMA_VERSION, "status": "undetermined",
              "refusal": {"rule": rule, "message": message},
              "limits": ["no query was answered"]}
    _write_result(out_dir, result)
    return result


def run_files(corpus_path, index_path, query_path, query_str, out_dir: Path) -> dict:
    spec: dict = {}
    if index_path:
        try:
            idx = json.loads(Path(index_path).read_text(encoding="utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError, OSError) as exc:
            return _refused(out_dir, "search.spec_unreadable",
                            "the index file is not readable JSON: " + str(exc))
        if not isinstance(idx, dict):
            return _refused(out_dir, "search.index_malformed",
                            "the index file is not a JSON object")
        spec["index"] = idx
    elif corpus_path:
        try:
            data = json.loads(Path(corpus_path).read_text(encoding="utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError, OSError) as exc:
            return _refused(out_dir, "search.spec_unreadable",
                            "the corpus file is not readable JSON: " + str(exc))
        if isinstance(data, list):
            spec["corpus"] = data
        elif isinstance(data, dict) and isinstance(data.get("documents"), list):
            spec["corpus"] = data["documents"]
        elif isinstance(data, dict) and isinstance(data.get("corpus"), list):
            spec["corpus"] = data["corpus"]
        else:
            return _refused(out_dir, "search.empty_corpus",
                            "the corpus file holds neither a document list nor a "
                            "documents/corpus key")
    else:
        return _refused(out_dir, "search.empty_corpus",
                        "no corpus or index was given; there is nothing to search")

    if query_path:
        try:
            spec["query"] = json.loads(Path(query_path).read_text(encoding="utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError, OSError) as exc:
            return _refused(out_dir, "search.spec_unreadable",
                            "the query file is not readable JSON: " + str(exc))
    elif query_str is not None:
        spec["query"] = query_str
    else:
        return _refused(out_dir, "search.empty_query",
                        "no query was given (--query or --query-file)")

    index, result = search.search(spec)
    if index is not None:
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "index.json").write_text(
            json.dumps(index, ensure_ascii=False, indent=2), encoding="utf-8")
    _write_result(out_dir, result)
    return result


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="file-search", description=__doc__)
    ap.add_argument("--corpus", default=None, help="corpus JSON (documents list)")
    ap.add_argument("--index", default=None, help="a previously built index.json to query")
    ap.add_argument("--query", default=None, help="query string (any-of its terms)")
    ap.add_argument("--query-file", default=None, help="query JSON ({all, any} or a string)")
    ap.add_argument("--case", default="", help="case-mode: read /input-style case.json, write result.json with case_id + output_contract echo")
    ap.add_argument("--out", required=True, help="output directory")
    a = ap.parse_args(argv)

    if getattr(a, "case", ""):
        out_dir = a.out if hasattr(a, "out") else "./out"
        r = _run_case(Path(a.case), Path(out_dir))
        print(json.dumps({"status": r.get("status")}, ensure_ascii=False))
        return {"clean": 0, "review": 3, "undetermined": 5}.get(r.get("status"), 5)
    if bool(a.corpus) == bool(a.index):
        _refused(Path(a.out), "search.empty_corpus",
                 "exactly one of --corpus / --index must be given")
        return 5
    result = run_files(a.corpus, a.index, a.query_file, a.query, Path(a.out))
    print(json.dumps({"ok": result.get("ok", False),
                      "empty": result.get("empty"),
                      "hits": len(result.get("hits") or []),
                      "refusal": result.get("refusal")}, ensure_ascii=False))
    return 0 if result.get("ok") is True else 5



_BULKY = ("output_contract", "section", "query", "corpus", "documents", "index",
          "text", "queries", "hits", "search", "answers")


def _echo_contract(result: dict, case: dict) -> dict:
    """case_id at top; output_contract field echo:
    engine value > caller-carried > null+limits. Engine keys always win."""
    limits = result.setdefault("limits", [])
    if not isinstance(case, dict):
        return result
    cid = case.get("case_id")
    if cid is not None:
        result["case_id"] = cid
    contract = case.get("output_contract") or []
    if isinstance(contract, dict):
        fields = list(contract)
    elif isinstance(contract, str):
        fields = [contract]
    elif isinstance(contract, list):
        fields = contract
    else:
        fields = []
        limits.append("output_contract must be a field list, object, or string")
    aliases = {"results": "new_items", "papers": "new_items", "retrieval_results": "new_items",
               "new_records": "new_items", "latest_results": "new_items", "updates": "version_updates",
               "notifications": "reminders", "state": "next_state", "watermark": "next_watermark",
               "evidence": "date_interpretations", "coverage": "source_status",
               "status_explanation": "limits"}
    for key in fields:
        if not isinstance(key, str) or not key:
            limits.append("output_contract contains a non-string or empty field name")
            continue
        if key in result:
            continue
        if aliases.get(key) in result:
            result[key] = result[aliases[key]]
            continue
        if key in case:
            result[key] = case[key]
            continue
        result[key] = None
        limits.append(f"output_contract field '{key}' was not derivable by search")
    return result


def _run_case(case_path: Path, out_dir: Path) -> dict:
    """case-mode entry: read case.json, map fields through the same search pipeline,
    then echo case_id + output_contract into result.json."""
    try:
        case = json.loads(case_path.read_text(encoding="utf-8-sig"))
    except (json.JSONDecodeError, UnicodeDecodeError, OSError) as exc:
        return _refused(out_dir, "search.spec_unreadable", f"case file not readable: {exc}")
    if not isinstance(case, dict):
        return _refused(out_dir, "search.spec_not_object", "case file is not a JSON object")
    if incremental_tracker.is_tracker_spec(case):
        try:
            result = _echo_contract(incremental_tracker.run(case), case)
        except Exception as exc:
            result = _echo_contract({"schema_version": incremental_tracker.SCHEMA_VERSION,
                                     "status": "undetermined", "refusal": {
                                         "rule": "tracker.engine_error", "message": str(exc)[:240]},
                                     "limits": ["no incremental result was completed"]}, case)
        _write_result(out_dir, result)
        if isinstance(result.get("next_state"), dict):
            (out_dir / "next_state.json").write_text(
                json.dumps(result["next_state"], ensure_ascii=False, indent=2), encoding="utf-8")
        return result
    spec: dict = {}
    cf = case.get("index") or case.get("corpus") or case.get("documents")
    if cf is not None:
        spec["corpus"] = cf
    qf = case.get("query") or case.get("search_query") or case.get("q")
    if qf is not None:
        spec["query"] = qf
    try:
        index, result = search.search(spec)
    except Exception as exc:
        return _refused(out_dir, "search.engine_error", str(exc)[:200])
    if index is not None:
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "index.json").write_text(
            json.dumps(index, ensure_ascii=False, indent=2), encoding="utf-8")
    if isinstance(result, dict):
        result = _echo_contract(result, case)
        # A successful legacy search has no status; never turn a refusal into clean.
        if "status" not in result:
            result["status"] = "clean"
    _write_result(out_dir, result)
    return result

if __name__ == "__main__":
    raise SystemExit(main())
