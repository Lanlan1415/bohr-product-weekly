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
import shutil
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import search  # noqa: E402
import citation_graph  # noqa: E402

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


def graph_spec(**overrides):
    """Small independently auditable graph: arrows below mean citing -> cited.

    F->S, C->S, L->{S,P}, G->F, S->{M,D}, P->{M,D}.  P therefore
    co-cites with S through L and is bibliographically coupled through M,D.
    """
    works = [
        {"id": "S", "doi": "10.1000/seed", "title": "Seed method", "year": 2019,
         "version_group": "family-s", "version": "published",
         "authors": ["Ada Lovelace"], "source": "crossref"},
        {"id": "S-preprint", "version_group": "family-s", "version": "v1",
         "doi": "10.48550/arxiv.seed", "title": "Seed method", "year": 2018,
         "authors": ["A. Lovelace"], "source": "arxiv"},
        {"id": "F", "doi": "10.1000/follow", "title": "Improved seed", "year": 2021,
         "authors": ["Bernie Smith"], "source": "openalex"},
        {"id": "C", "doi": "10.1000/critique", "title": "Seed caveats", "year": 2023,
         "source": "openalex"},
        {"id": "P", "doi": "10.1000/parallel", "title": "Parallel method", "year": 2022,
         "source": "semantic_scholar"},
        {"id": "L", "doi": "10.1000/later", "title": "Joint evaluation", "year": 2024,
         "source": "crossref"},
        {"id": "G", "doi": "10.1000/grandchild", "title": "Next generation", "year": 2025,
         "source": "crossref"},
        {"id": "M", "doi": "10.1000/method", "title": "Method origin", "year": 2014,
         "source": "crossref"},
        {"id": "D", "doi": "10.1000/data", "title": "Data origin", "year": 2016,
         "source": "crossref"},
    ]
    triples = [("F", "S", "opalex-f-s", "Improves the seed"),
               ("C", "S", "openalex-c-s", "Reports limitations"),
               ("L", "S", "openalex-l-s", "Compares against seed"),
               ("L", "P", "openalex-l-p", "Compares against parallel"),
               ("G", "F", "crossref-g-f", "Extends the improvement"),
               ("S", "M", "crossref-s-m", "We use the descriptor"),
               ("S", "D", "crossref-s-d", "We evaluate on the dataset"),
               ("P", "M", "europepmc-p-m", "Uses the descriptor"),
               ("P", "D", "europepmc-p-d", "Evaluates the dataset")]
    edges = [{"citing_id": a, "cited_id": b, "source_record_id": rid,
              "source": "openalex" if rid.startswith("openalex") or rid.startswith("opalex")
                         else ("crossref" if rid.startswith("crossref") else "europepmc"),
              "context": context, "context_locator": {"record": rid, "field": "reference"}}
             for a, b, rid, context in triples]
    # An exact duplicate export must collapse without losing provenance.
    edges.append(dict(edges[0]))
    spec = {"mode": "citation", "seed_id": "10.1000/seed", "works": works,
            "edges": edges, "max_depth": 2, "direction": "both", "max_nodes": 50,
            "source_status": {"openalex": {"status": "ok"},
                              "crossref": {"status": "ok"}, "europepmc": {"status": "ok"}}}
    spec.update(overrides)
    return spec


def scen_graph_forward_backward_sets(tmp, name):
    """Forward depth two = F,C,L,G; backward depth one = M,D (independent hand count)."""
    forward = citation_graph.run(graph_spec(direction="forward"))
    backward = citation_graph.run(graph_spec(direction="backward", max_depth=1))
    fids = {c["work_id"] for c in forward["candidates"]}
    bids = {c["work_id"] for c in backward["candidates"]}
    return fids == {"10.1000/follow", "10.1000/critique", "10.1000/later", "10.1000/grandchild"} and \
        bids == {"10.1000/method", "10.1000/data"} and \
        all(c["depth"] <= 2 for c in forward["candidates"])


def scen_graph_multihop_path_exact(tmp, name):
    """G's shortest path has two real hops F->S and G->F in reverse chronological traversal."""
    result = citation_graph.run(graph_spec(direction="forward"))
    candidate = next(c for c in result["candidates"] if c["work_id"] == "10.1000/grandchild")
    hops = candidate["shortest_path"]
    return candidate["depth"] == 2 and candidate["relation"] == "indirect" and \
        [(h["citing_id"], h["cited_id"], h["traversal_direction"]) for h in hops] == \
        [("10.1000/follow", "10.1000/seed", "forward"),
         ("10.1000/grandchild", "10.1000/follow", "forward")] and \
        all(h["source"] and h["citation_context"] for h in hops)


def scen_graph_co_citation_and_coupling(tmp, name):
    """P is related through L and through two shared references M,D, not by invented P->S."""
    result = citation_graph.run(graph_spec())
    rel = next(a for a in result["associations"] if a["work_id"] == "10.1000/parallel")
    assert rel["association"] == "co_citation+bibliographic_coupling"
    return rel["shared_citing_works"] == ["10.1000/later"] and \
        rel["shared_references"] == ["10.1000/data", "10.1000/method"] and \
        not any(e["citing_id"] == "10.1000/parallel" and e["cited_id"] == "10.1000/seed"
                for e in result["citation_edges"])


def scen_graph_edge_context_and_sources(tmp, name):
    """Every retained graph edge has source, endpoint direction, context and locator."""
    result = citation_graph.run(graph_spec())
    return len(result["citation_edges"]) == 9 and \
        all(e["direction"] == "citing_to_cited" and e["source"] and
            e["source_record_id"] and e["citation_context"] and e["context_locator"]
            for e in result["citation_edges"]) and result["duplicate_edges"]


def scen_graph_version_group_merge(tmp, name):
    """Seed preprint and journal merge only via explicit version group; both DOIs survive."""
    result = citation_graph.run(graph_spec())
    seed = result["seed"]
    return len(seed["version_records"]) == 2 and \
        {r["doi"] for r in seed["version_records"]} == {"10.1000/seed", "10.48550/arxiv.seed"} and \
        any(m["rule"] == "declared_version_group" for m in result["identity_merges"]) and \
        seed["conflicting_metadata"]


def scen_graph_distinct_doi_veto(tmp, name):
    """Same title and author with two non-version DOIs must not merge."""
    rows = [{"id": "a", "doi": "10.1000/a", "title": "Identical title", "year": 2020,
             "authors": ["Jane Doe"]}, {"id": "b", "doi": "10.1000/b", "title": "Identical Title!",
             "year": 2020, "authors": ["J. Doe"]}]
    result = citation_graph.run({"mode": "citation", "seed_id": "a", "works": rows})
    return not result["identity_merges"] and result["coverage"]["works_considered"] == 2


def scen_graph_fuzzy_title_merge(tmp, name):
    """One punctuation/subtitle variant merges with author and year guards when one DOI is absent."""
    rows = [{"id": "a", "doi": "10.1000/same", "title": "A reproducible citation method",
             "year": 2020, "authors": ["Jane Doe"]},
            {"id": "b", "title": "A reproducible citation methods",
             "year": 2021, "authors": ["J. Doe"], "source": "europepmc"}]
    result = citation_graph.run({"mode": "citation", "seed_id": "a", "works": rows})
    return len(result["identity_merges"]) == 1 and \
        result["identity_merges"][0]["rule"] == "title_fuzzy_author"


def scen_graph_budget_stop_honest(tmp, name):
    """A one-node expansion stops honestly; no claim of complete coverage."""
    result = citation_graph.run(graph_spec(max_nodes=1))
    return result["candidate_count"] == 1 and result["status"] == "review" and \
        any(f["rule"] == "citation.budget_stopped" for f in result["findings"]) and \
        result["network_summary"]["stop_reason"] == "max_nodes"


def scen_graph_no_edge_clean_empty(tmp, name):
    """An isolated but valid seed yields a clean empty expansion, not padded citations."""
    result = citation_graph.run({"mode": "citation", "seed_id": "solo", "works": [
        {"id": "solo", "title": "A new preprint", "year": 2026}]})
    return result["status"] == "clean" and result["candidates"] == [] and \
        result["citation_edges"] == [] and result["associations"] == []


def scen_graph_seed_refusal(tmp, name):
    """An unresolved seed produces a structured refusal."""
    result = citation_graph.run({"mode": "citation", "works": [], "max_depth": 2})
    return result["status"] == "undetermined" and \
        result["refusal"]["rule"] == "citation.seed_unresolved" and result["limits"]


def scen_graph_source_gap_not_zero_citations(tmp, name):
    """A failed source marks incomplete coverage; empty/absence is not universal zero citations."""
    result = citation_graph.run(graph_spec(source_status={"openalex": {"status": "timeout"}}))
    return "uncertainty" in result and "does not prove zero citations" in result["uncertainty"] and \
        any("openalex" in x for x in result["limits"])


def scen_graph_case_contract_cold_deterministic(tmp, name):
    """Cold installed copy: full contract passthrough, exit 0, byte-identical repeat runs."""
    case = graph_spec(case_id="graph-smoke-001", output_contract=[
        "case_id", "candidates", "citation_edges", "paths", "associations", "identity_merges",
        "status", "uncertainty", "owner_note", "unknown_required"], owner_note="verbatim")
    case_path = tmp / "graph-case.json"
    case_path.write_text(json.dumps(case, ensure_ascii=False), encoding="utf-8")
    cold = tmp / "cold-skill"
    shutil.copytree(Path(__file__).resolve().parent.parent, cold)
    outputs = []
    for label in ("a", "b"):
        out = tmp / ("out-" + label)
        proc = subprocess.run([sys.executable, "-I", str(cold / "scripts" / "search_cli.py"),
                               "--case", str(case_path), "--out", str(out)],
                              capture_output=True, text=True, timeout=120, cwd=str(tmp))
        if proc.returncode != 0:
            return False
        outputs.append((out / "result.json").read_bytes())
    result = json.loads(outputs[0])
    return outputs[0] == outputs[1] and result["case_id"] == "graph-smoke-001" and \
        result["owner_note"] == "verbatim" and result["unknown_required"] is None and \
        len(result["candidates"]) > 0 and any("unknown_required" in x for x in result["limits"])


def scen_graph_refusal_exit_and_no_traceback(tmp, name):
    """Unreadable case emits result.json and exit 5, never a traceback/nonzero crash fallback."""
    missing = tmp / "does-not-exist.json"
    out = tmp / "missing-out"
    proc = subprocess.run([sys.executable, "-I", str(CLI), "--case", str(missing), "--out", str(out)],
                          capture_output=True, text=True, timeout=120)
    result = json.loads((out / "result.json").read_text(encoding="utf-8"))
    return proc.returncode == 5 and "Traceback" not in proc.stderr and \
        result["status"] == "undetermined" and result["refusal"]["rule"] == "search.spec_unreadable"


SCENARIOS = [
    ("backward_refs_line", scen_backward_refs_line),
    ("graph_forward_backward_sets", scen_graph_forward_backward_sets),
    ("graph_multihop_path_exact", scen_graph_multihop_path_exact),
    ("graph_co_citation_and_coupling", scen_graph_co_citation_and_coupling),
    ("graph_edge_context_and_sources", scen_graph_edge_context_and_sources),
    ("graph_version_group_merge", scen_graph_version_group_merge),
    ("graph_distinct_doi_veto", scen_graph_distinct_doi_veto),
    ("graph_fuzzy_title_merge", scen_graph_fuzzy_title_merge),
    ("graph_budget_stop_honest", scen_graph_budget_stop_honest),
    ("graph_no_edge_clean_empty", scen_graph_no_edge_clean_empty),
    ("graph_seed_refusal", scen_graph_seed_refusal),
    ("graph_source_gap_not_zero_citations", scen_graph_source_gap_not_zero_citations),
    ("graph_case_contract_cold_deterministic", scen_graph_case_contract_cold_deterministic),
    ("graph_refusal_exit_and_no_traceback", scen_graph_refusal_exit_and_no_traceback),
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
