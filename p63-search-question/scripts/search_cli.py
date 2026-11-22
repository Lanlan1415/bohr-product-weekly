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
    ap.add_argument("--out", required=True, help="output directory")
    a = ap.parse_args(argv)
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


if __name__ == "__main__":
    raise SystemExit(main())
