"""CLI: index a document corpus and answer a boolean query with located passages.

    python search_cli.py --corpus corpus.json --query "缓冲液 配制" --out ./out
    python search_cli.py --corpus corpus.json --query-file query.json --out ./out
    python search_cli.py --index index.json --query-file query.json --out ./out
    python search_cli.py --corpus corpus.json --query-file query.json \
        --case case.json --out ./out

corpus.json holds {"documents": [...]} (or {"corpus": [...]}, or a bare list);
query.json holds {"all": [...], "any": [...], "filters": {...}} or a bare
string. Writes out/index.json (the index, kept for replay) and out/result.json
(the query record with terms and filters, the index fingerprint, and hits with
verbatim section-level locators).

--case case.json echoes case_id and every output_contract field into
result.json (contract passthrough). The contract is echoed only on the
ok/partial path: on the refusal path the broken file may be the case file
itself, so nothing from it is echoed.

Exit codes: 0 ok (query answered, whole corpus indexed), 4 partial (query
answered but entries were skipped or warned — findings listed), 5 undetermined
(refusal: unreadable files, empty corpus, malformed index, empty query,
invalid filters), 2 usage. A refusal still writes result.json — the refusal is
a result, not a crash.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import search  # noqa: E402

# Contract fields whose VALUES are bulky material inputs, not deliverable
# metadata: they are echoed as null (and named in limits), never copied wholesale.
_BULKY = ("output_contract", "task", "materials", "documents", "corpus", "index",
          "text", "files", "annotations")


def _write_result(out_dir: Path, result: dict) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "result.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")


def _refused(out_dir: Path, rule: str, message: str) -> dict:
    """The refusal result: honest undetermined, contract NOT echoed — the
    broken file may be the case file itself."""
    result = {"schema_version": search.SCHEMA_VERSION, "status": "undetermined",
              "refusal": {"rule": rule, "message": message},
              "limits": ["no query was answered"]}
    _write_result(out_dir, result)
    return result


def _echo_contract(result: dict, case: dict, limits: list) -> None:
    """Contract passthrough (ok/partial path only): case_id plus every
    output_contract field. A field the result already carries is kept; a field
    the case supplies verbatim is copied unless bulky; a literal in the
    contract is backfilled; anything underivable is null and named in limits."""
    cid = case.get("case_id")
    if cid is None:
        cid = case.get("id")
    result["case_id"] = cid
    if cid is None:
        limits.append("case_id was not present in the case file")
    contract = case.get("output_contract")
    if isinstance(contract, dict):
        for key in contract:
            if key in result:
                continue
            if key in case and key not in _BULKY:
                result[key] = case[key]
                continue
            v = contract[key]
            if isinstance(v, (str, int, float, bool)) and \
                    (not isinstance(v, str) or len(v) <= 500):
                result[key] = v
                continue
            result[key] = None
            limits.append(f"output_contract field '{key}' was not derivable by this run")
    elif contract is not None:
        limits.append("output_contract was present but not an object, so no contract "
                      "fields were echoed")


def run_files(corpus_path, index_path, query_path, query_str, out_dir: Path,
              case_path=None) -> dict:
    limits: list = []
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

    case = None
    if case_path:
        try:
            case = json.loads(Path(case_path).read_text(encoding="utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError, OSError) as exc:
            return _refused(out_dir, "search.case_unreadable",
                            "the case file is not readable JSON: " + str(exc))
        if not isinstance(case, dict):
            return _refused(out_dir, "search.case_unreadable",
                            "the case file is not a JSON object")

    index, result = search.search(spec)
    if index is not None:
        try:
            out_dir.mkdir(parents=True, exist_ok=True)
            (out_dir / "index.json").write_text(
                json.dumps(index, ensure_ascii=False, indent=2), encoding="utf-8")
        except OSError as exc:
            return _refused(out_dir, "search.export_failed",
                            "the index could not be written (disk full or "
                            "permission denied?): " + str(exc))
        result["wrote_index"] = str(out_dir / "index.json")
    if case is not None:
        _echo_contract(result, case, limits)
    if limits:
        result["limits"] = limits
    _write_result(out_dir, result)
    return result


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="file-search", description=__doc__)
    ap.add_argument("--corpus", default=None, help="corpus JSON (documents list)")
    ap.add_argument("--index", default=None, help="a previously built index.json to query")
    ap.add_argument("--query", default=None, help="query string (any-of its terms)")
    ap.add_argument("--query-file", default=None,
                    help="query JSON ({all, any, filters} or a string)")
    ap.add_argument("--case", default=None,
                    help="case.json: echoes case_id and output_contract fields into result.json")
    ap.add_argument("--out", required=True, help="output directory")
    a = ap.parse_args(argv)
    if bool(a.corpus) == bool(a.index):
        _refused(Path(a.out), "search.empty_corpus",
                 "exactly one of --corpus / --index must be given")
        return 5
    result = run_files(a.corpus, a.index, a.query_file, a.query, Path(a.out), a.case)
    print(json.dumps({"ok": result.get("ok", False),
                      "status": result.get("status"),
                      "empty": result.get("empty"),
                      "hits": len(result.get("hits") or []),
                      "refusal": result.get("refusal"),
                      "case_id": result.get("case_id")}, ensure_ascii=False))
    # Exit codes: 0 ok, 4 partial, 5 undetermined (refusal), 2 usage.
    if result.get("ok") is True:
        return 4 if result.get("status") == "partial" else 0
    return 5


if __name__ == "__main__":
    raise SystemExit(main())
