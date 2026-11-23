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
import localfiles  # noqa: E402

# Contract fields whose VALUES are bulky material inputs, not deliverable
# metadata: they are echoed as null (and named in limits), never copied wholesale.
_BULKY = ("output_contract", "task", "materials", "documents", "corpus", "index",
          "text", "files", "annotations")


def _write_result(out_dir: Path, result: dict) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "result.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")


def _refused(out_dir: Path, rule: str, message: str, case: dict | None = None,
             extra: dict | None = None) -> dict:
    """Structured undetermined result; a readable case contract still passses."""
    result = {"schema_version": search.SCHEMA_VERSION, "status": "undetermined",
              "refusal": {"rule": rule, "message": message},
              "limits": ["no query was answered"]}
    if extra:
        result.update(extra)
    _echo_contract(result, case)
    _write_result(out_dir, result)
    return result


def _echo_contract(result: dict, case: dict, limits: list | None = None) -> None:
    """Case id + every contract key on success and structured refusals."""
    if not case:
        return
    if limits is None:
        limits = result.setdefault("limits", [])
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
            derived = {
                "search_result": {"hits": result.get("hits") or (result.get("search_result") or {}).get("hits", []),
                                  "ranking": result.get("ranking"),
                                  "ambiguity": result.get("ambiguity"),
                                  "no_result": result.get("no_result")},
                "operation_evidence": {"index_sha256": result.get("index_sha256"),
                                       "documents_indexed": result.get("documents_indexed"),
                                       "wrote_index": result.get("wrote_index"),
                                       "coverage": result.get("coverage")},
                "failure_recovery": {"findings": result.get("findings") or [],
                                     "refusal": result.get("refusal"),
                                     "no_result": result.get("no_result"),
                                     "limits": limits},
                "sources": result.get("coverage"),
                "uncertainty": {"ambiguity": result.get("ambiguity"),
                                "findings": result.get("findings") or []},
            }
            if key in derived:
                value = derived[key]
                usable = value is not None and (not isinstance(value, dict) or
                                                any(v is not None for v in value.values()))
                if usable:
                    result[key] = value
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
              case_path=None, root_path=None, metadata=None) -> dict:
    limits: list = []
    spec: dict = {}
    case = None
    if case_path:
        try:
            case = json.loads(Path(case_path).read_text(encoding="utf-8-sig"))
        except (json.JSONDecodeError, UnicodeDecodeError, OSError) as exc:
            return _refused(out_dir, "search.case_unreadable",
                            "the case file is not readable JSON: " + str(exc))
        if not isinstance(case, dict):
            return _refused(out_dir, "search.case_unreadable",
                            "the case file is not a JSON object")
    coverage = None
    issues = []
    if root_path:
        loaded = localfiles.build_corpus(Path(root_path), metadata or [])
        coverage = loaded.get("coverage")
        issues = loaded.get("issues") or []
        if not loaded.get("ok"):
            return _refused(out_dir, loaded["refusal"]["rule"], loaded["refusal"]["message"],
                            case, {"coverage": coverage, "extraction_issues": issues})
        spec["corpus"] = loaded["corpus"]
    elif index_path:
        try:
            idx = json.loads(Path(index_path).read_text(encoding="utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError, OSError) as exc:
            return _refused(out_dir, "search.spec_unreadable",
                            "the index file is not readable JSON: " + str(exc), case)
        if not isinstance(idx, dict):
            return _refused(out_dir, "search.index_malformed",
                            "the index file is not a JSON object", case)
        spec["index"] = idx
    elif corpus_path:
        try:
            data = json.loads(Path(corpus_path).read_text(encoding="utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError, OSError) as exc:
            return _refused(out_dir, "search.spec_unreadable",
                            "the corpus file is not readable JSON: " + str(exc), case)
        if isinstance(data, list):
            spec["corpus"] = data
        elif isinstance(data, dict) and isinstance(data.get("documents"), list):
            spec["corpus"] = data["documents"]
        elif isinstance(data, dict) and isinstance(data.get("corpus"), list):
            spec["corpus"] = data["corpus"]
        else:
            return _refused(out_dir, "search.empty_corpus",
                            "the corpus file holds neither a document list nor a "
                            "documents/corpus key", case)
    else:
        return _refused(out_dir, "search.empty_corpus",
                        "no root, corpus or index was given; there is nothing to search", case)

    if query_path:
        try:
            spec["query"] = json.loads(Path(query_path).read_text(encoding="utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError, OSError) as exc:
            return _refused(out_dir, "search.spec_unreadable",
                            "the query file is not readable JSON: " + str(exc), case,
                            {"coverage": coverage, "extraction_issues": issues})
    elif query_str is not None:
        spec["query"] = query_str
    else:
        return _refused(out_dir, "search.empty_query",
                        "no query was given (--query or --query-file)", case,
                        {"coverage": coverage, "extraction_issues": issues})

    index, result = search.search(spec)
    if coverage is not None:
        result["coverage"] = coverage
        result["extraction_issues"] = issues
        if issues and index is not None:
            result["status"] = "partial"
            result.setdefault("findings", []).append({
                "rule": "search.file_extraction_incomplete", "severity": "medium",
                "count": len(issues), "entries": issues,
                "why": "these files were not indexed; no text or metadata was invented"})
    if index is not None:
        try:
            out_dir.mkdir(parents=True, exist_ok=True)
            (out_dir / "index.json").write_text(
                json.dumps(index, ensure_ascii=False, indent=2), encoding="utf-8")
            if coverage is not None:
                (out_dir / "coverage.json").write_text(
                    json.dumps({"files": coverage, "issues": issues}, ensure_ascii=False, indent=2),
                    encoding="utf-8")
        except OSError as exc:
            return _refused(out_dir, "search.export_failed",
                            "the index could not be written (disk full or "
                            "permission denied?): " + str(exc), case,
                            {"coverage": coverage, "extraction_issues": issues})
        result["wrote_index"] = str(out_dir / "index.json")
        if coverage is not None:
            result["wrote_coverage"] = str(out_dir / "coverage.json")
    _echo_contract(result, case, limits)
    if limits:
        result["limits"] = limits
    _write_result(out_dir, result)
    return result


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="file-search", description=__doc__)
    ap.add_argument("--root", default=None, help="real file tree to hash and extract before indexing")
    ap.add_argument("--metadata", action="append", default=None,
                    help="declared metadata sidecar relative to --root (repeatable; metadata.* auto-detected)")
    ap.add_argument("--corpus", default=None, help="corpus JSON (documents list)")
    ap.add_argument("--index", default=None, help="a previously built index.json to query")
    ap.add_argument("--query", default=None, help="query string (any-of its terms)")
    ap.add_argument("--query-file", default=None,
                    help="query JSON ({all, any, filters} or a string)")
    ap.add_argument("--case", default=None,
                    help="case.json: echoes case_id and output_contract fields into result.json")
    ap.add_argument("--out", required=True, help="output directory")
    a = ap.parse_args(argv)
    if sum(bool(v) for v in (a.root, a.corpus, a.index)) != 1:
        _refused(Path(a.out), "search.empty_corpus",
                 "exactly one of --root / --corpus / --index must be given")
        return 5
    result = run_files(a.corpus, a.index, a.query_file, a.query, Path(a.out), a.case,
                       root_path=a.root, metadata=a.metadata)
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
