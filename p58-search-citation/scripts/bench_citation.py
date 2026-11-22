"""Benchmark for the search-citation skill (引文追踪与关联文献发现).

Scenarios pin the citation-tracing behaviours on top of the shared file-search
engine: backward tracing locates the seed's own reference line verbatim, the
forward probe "cites: <id>" returns exactly the records carrying that citation
edge, the method lineage probe surfaces the parallel work that shares the
method source, a record nobody cites yields an honest empty (no fabricated
edge), duplicate exports are skipped and named, and the CLI ships a green
example plus the exit-5 refusal contract.

    python bench_citation.py
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
    {"id": "seed-2019",
     "text": "id: seed-2019\n"
             "Seed paper: message-passing neural potentials for molecular dynamics (2019).\n"
             "refs: meth-2014\n"
             "Introduced the descriptor-free potential that later work built on."},
    {"id": "follow-2021",
     "text": "id: follow-2021\n"
             "Follow-up: equivariant message-passing potential (2021).\n"
             "cites: seed-2019\ncites: meth-2014\n"
             "Improves the angular resolution of the seed."},
    {"id": "follow-2023",
     "text": "id: follow-2023\n"
             "Critique: benchmark caveats of the seed potential (2023).\n"
             "cites: seed-2019\n"
             "Reports failures under periodic boundary conditions."},
    {"id": "parallel-2022",
     "text": "id: parallel-2022\n"
             "Parallel work: kernel-based potentials without message passing (2022).\n"
             "cites: meth-2014\ncites: data-2016\n"
             "Related by method lineage; does not cite the seed."},
    {"id": "meth-2014",
     "text": "id: meth-2014\n"
             "Method origin: descriptor-based local energy decomposition (2014).\n"
             "refs: none\n"
             "The method both the seed and the parallel work build on."},
    {"id": "follow-2021",
     "text": "id: follow-2021\n"
             "Follow-up: equivariant message-passing potential (2021).\n"
             "cites: seed-2019\ncites: meth-2014\n"
             "Improves the angular resolution of the seed."},
]

EXAMPLE_QUERY = {"all": ["cites: seed-2019"]}

EXAMPLES = Path(__file__).resolve().parent.parent / "examples"
CLI = Path(__file__).resolve().parent / "search_cli.py"


def _run_cli(out, query_file=None):
    args = [sys.executable, str(CLI), "--corpus", str(EXAMPLES / "corpus.json"),
            "--out", str(out)]
    args += ["--query-file", str(query_file or (EXAMPLES / "query.json"))]
    return subprocess.run(args, capture_output=True, text=True, timeout=120)


def scen_backward_refs_line(tmp, name):
    """Backward tracing: the seed's own reference edge is located verbatim."""
    _, res = search.search({"corpus": CORPUS,
                            "query": {"all": ["id: seed-2019", "refs: meth-2014"]}})
    quotes = {p["locator"]["quote"] for h in res["hits"] for p in h["passages"]}
    return res["ok"] and [h["doc_id"] for h in res["hits"]] == ["seed-2019"] \
        and "refs: meth-2014" in quotes


def scen_forward_cites_edge(tmp, name):
    """Forward tracing: exactly the records carrying the citation edge are returned."""
    _, res = search.search({"corpus": CORPUS, "query": {"all": ["cites: seed-2019"]}})
    ids = [h["doc_id"] for h in res["hits"]]
    terms = {p["term"] for h in res["hits"] for p in h["passages"]}
    return res["ok"] and ids == ["follow-2021", "follow-2023"] \
        and "cites: seed-2019" in terms and "parallel-2022" not in ids


def scen_method_lineage(tmp, name):
    """The lineage probe surfaces follow-up and parallel work sharing the method source."""
    _, res = search.search({"corpus": CORPUS, "query": {"all": ["cites: meth-2014"]}})
    ids = [h["doc_id"] for h in res["hits"]]
    return res["ok"] and ids == ["follow-2021", "parallel-2022"] \
        and res["documents_indexed"] == 5


def scen_no_edge_honest(tmp, name):
    """A record nobody cites yields an honest empty — no fabricated forward edge."""
    _, res = search.search({"corpus": CORPUS, "query": {"all": ["cites: parallel-2022"]}})
    return res["ok"] and res["empty"] is True and res["hits"] == [] \
        and "never padded" in res["note"]


def scen_duplicate_export_named(tmp, name):
    """A duplicated export of a citing record is skipped and named, not double-counted."""
    _, res = search.search({"corpus": CORPUS, "query": {"all": ["cites: seed-2019"]}})
    f = next((x for x in res.get("findings", []) if x["rule"] == "search.doc_skipped"), None)
    return res["ok"] and f is not None and f["count"] == 1 \
        and "duplicate doc id 'follow-2021'" in f["entries"][0]["reason"] \
        and res["documents_indexed"] == 5


def scen_edge_locator_verbatim(tmp, name):
    """Every citation-edge passage quote equals the indexed paragraph slice."""
    docs = search.build_index(CORPUS)["index"]["documents"]
    _, res = search.search({"corpus": CORPUS, "query": {"all": ["cites: seed-2019"]}})
    ok = len(res["hits"]) == 2
    for hit in res["hits"]:
        paras = docs[hit["doc_id"]]["paragraphs"]
        for p in hit["passages"]:
            loc = p["locator"]
            ok = ok and paras[loc["paragraph"]][loc["start"]:loc["end"]] == loc["quote"]
    return ok


def scen_cli_examples_run(tmp, name):
    """The shipped example runs green: exit 0, both citing records with located edges."""
    out = tmp / "out-ex"
    proc = _run_cli(out)
    if proc.returncode != 0 or not (out / "index.json").exists():
        return False
    res = json.loads((out / "result.json").read_text(encoding="utf-8"))
    idx = json.loads((out / "index.json").read_text(encoding="utf-8"))
    return res["ok"] and not res["empty"] \
        and [h["doc_id"] for h in res["hits"]] == ["follow-2021", "follow-2023"] \
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
    ("backward_refs_line", scen_backward_refs_line),
    ("forward_cites_edge", scen_forward_cites_edge),
    ("method_lineage", scen_method_lineage),
    ("no_edge_honest", scen_no_edge_honest),
    ("duplicate_export_named", scen_duplicate_export_named),
    ("edge_locator_verbatim", scen_edge_locator_verbatim),
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
    report = {"schema_version": "citation-bench/v1", "scenarios": rows,
              "totals": {"passed": passed, "of": len(rows)}}
    (Path(__file__).resolve().parent / "report_citation.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n{passed}/{len(rows)} scenarios pass")
    return 0 if passed == len(rows) else 1


if __name__ == "__main__":
    raise SystemExit(main())
