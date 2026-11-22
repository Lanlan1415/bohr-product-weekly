"""Benchmark for the search-multi-db skill (多数据库联合检索).

Scenarios pin the federation behaviours on top of the shared file-search
engine: a normalised DOI token is the merge key present on every source
record of the same work, per-source probes count recall per database, a
source missing from the snapshot is an honest empty (the gap is named, not
swallowed), a field a source does not export stays honestly unmatched, the
mapped year field answers across records, and the CLI ships a green example
plus the exit-5 refusal contract.

    python bench_multidb.py
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import search  # noqa: E402

CORPUS = [
    {"id": "xref-001",
     "text": "id: xref-001\nsrc: crossref\n"
             "title: Nanopore direct RNA detection at single-molecule resolution\n"
             "doi: doi-10-1038-s41592-026-01234-5\nyear: 2026\njournal: Nature Methods"},
    {"id": "epmc-001",
     "text": "id: epmc-001\nsrc: europepmc\n"
             "title: Nanopore direct RNA detection at single-molecule resolution\n"
             "doi: doi-10-1038-s41592-026-01234-5\nyear: 2026\nnote: abstract view"},
    {"id": "xref-002",
     "text": "id: xref-002\nsrc: crossref\n"
             "title: Protein complex assembly inferred from deep mutational scanning\n"
             "doi: doi-10-1038-s41591-025-09876-1\nyear: 2025\njournal: Molecular Systems Biology"},
    {"id": "epmc-002",
     "text": "id: epmc-002\nsrc: europepmc\n"
             "title: Single-cell transcriptomics of the human retina\n"
             "doi: doi-10-1038-s41586-024-07730-0\nyear: 2024"},
]

MERGE_KEY = "doi-10-1038-s41592-026-01234-5"

EXAMPLE_QUERY = {"all": [MERGE_KEY]}

EXAMPLES = Path(__file__).resolve().parent.parent / "examples"
CLI = Path(__file__).resolve().parent / "search_cli.py"


def _run_cli(out, query_file=None):
    args = [sys.executable, str(CLI), "--corpus", str(EXAMPLES / "corpus.json"),
            "--out", str(out)]
    args += ["--query-file", str(query_file or (EXAMPLES / "query.json"))]
    return subprocess.run(args, capture_output=True, text=True, timeout=120)


def scen_doi_merge_key(tmp, name):
    """The DOI token hits on every source record of the same work — the merge key exists."""
    _, res = search.search({"corpus": CORPUS, "query": {"all": [MERGE_KEY]}})
    ids = sorted(h["doc_id"] for h in res["hits"])
    return res["ok"] and ids == ["epmc-001", "xref-001"] \
        and res["documents_indexed"] == 4


def scen_source_coverage(tmp, name):
    """Per-source probes count recall per database exactly as declared."""
    _, cr = search.search({"corpus": CORPUS, "query": {"all": ["src: crossref"]}})
    _, ep = search.search({"corpus": CORPUS, "query": {"all": ["src: europepmc"]}})
    return sorted(h["doc_id"] for h in cr["hits"]) == ["xref-001", "xref-002"] \
        and sorted(h["doc_id"] for h in ep["hits"]) == ["epmc-001", "epmc-002"]


def scen_source_gap_honest(tmp, name):
    """A source absent from the snapshot is an honest empty — the gap is named."""
    _, res = search.search({"corpus": CORPUS, "query": {"all": ["src: semanticscholar"]}})
    return res["ok"] and res["empty"] is True and res["hits"] == [] \
        and "never padded" in res["note"]


def scen_field_gap_honest(tmp, name):
    """A record missing the journal field stays unmatched — no defaulted value."""
    _, res = search.search({"corpus": CORPUS,
                            "query": {"all": ["journal: Nature Methods"]}})
    ids = [h["doc_id"] for h in res["hits"]]
    return res["ok"] and ids == ["xref-001"] and "epmc-002" not in ids


def scen_mapped_year_field(tmp, name):
    """The mapped year token answers across source records with that year."""
    _, res = search.search({"corpus": CORPUS, "query": {"all": ["2026"]}})
    ids = sorted(h["doc_id"] for h in res["hits"])
    return res["ok"] and ids == ["epmc-001", "xref-001"]


def scen_merge_locator_verbatim(tmp, name):
    """Every merge-key passage quote equals the indexed paragraph slice."""
    docs = search.build_index(CORPUS)["index"]["documents"]
    _, res = search.search({"corpus": CORPUS, "query": {"all": [MERGE_KEY]}})
    ok = len(res["hits"]) == 2
    for hit in res["hits"]:
        paras = docs[hit["doc_id"]]["paragraphs"]
        for p in hit["passages"]:
            loc = p["locator"]
            ok = ok and paras[loc["paragraph"]][loc["start"]:loc["end"]] == loc["quote"]
    return ok


def scen_cli_examples_run(tmp, name):
    """The shipped example runs green: exit 0, both source records of the merged work."""
    out = tmp / "out-ex"
    proc = _run_cli(out)
    if proc.returncode != 0 or not (out / "index.json").exists():
        return False
    res = json.loads((out / "result.json").read_text(encoding="utf-8"))
    idx = json.loads((out / "index.json").read_text(encoding="utf-8"))
    return res["ok"] and not res["empty"] \
        and sorted(h["doc_id"] for h in res["hits"]) == ["epmc-001", "xref-001"] \
        and idx["corpus_sha256"][:16] == res["index_sha256"]


def scen_cli_refusal_exit5(tmp, name):
    """A malformed query file refuses with exit 5 and a written refusal record."""
    bad = tmp / "bad.json"
    bad.write_text("{not json", encoding="utf-8")
    out = tmp / "out-ref"
    proc = _run_cli(out, query_file=bad)
    if proc.returncode != 5:
        return False
    res = json.loads((out / "result.json").read_text(encoding="utf-8"))
    return res["status"] == "undetermined" \
        and res["refusal"]["rule"] == "search.spec_unreadable"


SCENARIOS = [
    ("doi_merge_key", scen_doi_merge_key),
    ("source_coverage", scen_source_coverage),
    ("source_gap_honest", scen_source_gap_honest),
    ("field_gap_honest", scen_field_gap_honest),
    ("mapped_year_field", scen_mapped_year_field),
    ("merge_locator_verbatim", scen_merge_locator_verbatim),
    ("cli_examples_run", scen_cli_examples_run),
    ("cli_refusal_exit5", scen_cli_refusal_exit5),
]


def main() -> int:
    rows = []
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        for name, fn in SCENARIOS:
            try:
                ok = bool(fn(tmp, name))
                why = ""
            except Exception as exc:
                ok, why = False, f"raised {type(exc).__name__}: {exc}"
            rows.append({"scenario": name, "pass": ok, "why": why})
            print(("PASS" if ok else "FAIL") + f"  {name:<26}" + why)
    passed = sum(1 for r in rows if r["pass"])
    report = {"schema_version": "multidb-bench/v1", "scenarios": rows,
              "totals": {"passed": passed, "of": len(rows)}}
    (Path(__file__).resolve().parent / "report_multidb.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n{passed}/{len(rows)} scenarios pass")
    return 0 if passed == len(rows) else 1


if __name__ == "__main__":
    raise SystemExit(main())
