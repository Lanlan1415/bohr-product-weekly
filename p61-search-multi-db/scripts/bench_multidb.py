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
import shutil
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import search  # noqa: E402
import federated_search  # noqa: E402

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


def federation_spec(**overrides):
    """Hand-reconciled fixture: 10 raw = 9 valid + 1 rejected; 9 valid -> 6 works.

    A has three observations, the V version family has two, and B/Vpre/C/X/Y
    provide four singleton clusters.  X and Y deliberately share title/author
    but have distinct DOIs and therefore remain separate works.
    """
    spec = {
        "mode": "multi_db", "required_sources": ["crossref", "europepmc", "openalex"],
        "query": {"title": "reproducible detection system", "author": "Jane Doe",
                  "from_date": "2024-01-01", "until_date": "2026-12-31"},
        "required_fields": ["title", "doi", "authors", "year", "journal"],
        "sources": {
            "crossref": {"status": "ok", "query": {"filter": "from-pub-date:2024-01-01"},
                         "raw_response_ref": "input/crossref.json", "records": [
                {"id": "cr-a", "DOI": "https://doi.org/10.1000/ALPHA",
                 "title": "Reproducible Detection System", "author": [{"given": "Jane", "family": "Doe"}],
                 "issued": {"date-parts": [[2025, 4, 1]]}, "container-title": ["Journal A"]},
                {"id": "cr-b", "DOI": "10.1000/beta", "title": "Crossref only benchmark",
                 "author": [{"given": "Alan", "family": "Turing"}], "year": 2025},
                {"id": "cr-v", "DOI": "10.1000/version-journal", "title": "Versioned assay",
                 "version_group": "family-v", "version": "published", "year": 2026},
                {"id": "cr-x", "DOI": "10.1000/x", "title": "Same named paper", "year": 2025,
                 "authors": ["Jane Doe"]},
                42,
            ]},
            "europepmc": {"status": "ok", "query": "TITLE:reproducible", "records": [
                {"id": "ep-a", "pmid": "123", "doi": "10.1000/alpha",
                 "title": "Reproducible detection system", "authors": ["J. Doe"], "year": 2024},
                {"id": "ep-v", "DOI": "10.48550/arxiv.v", "title": "Versioned assay",
                 "version_group": "family-v", "version": "v1", "year": 2025},
                {"id": "ep-c", "doi": "10.1000/unique-europe", "title": "Europe PMC only cohort",
                 "year": 2024},
            ]},
            "openalex": {"status": "ok", "query": {"search": "reproducible detection system"}, "records": [
                {"id": "oa-a", "title": "Reproducible Detection Systems", "display_name": "Reproducible Detection Systems",
                 "authors": [{"display_name": "Jane Doe"}], "publication_year": 2025},
                {"id": "oa-y", "doi": "10.1000/y", "title": "Same named paper!", "year": 2025,
                 "authors": ["J. Doe"]},
            ]},
        },
    }
    spec.update(overrides)
    return spec


def _work_for_doi(result, doi):
    return next((w for w in result["merged_records"] if doi in w["identifiers"]["doi"]), None)


def scen_federated_closed_counts(tmp, name):
    """10 raw -> 9 valid -> 6 unique; single=4/multi=2; duplicate source observations=3."""
    result = federated_search.run(federation_spec())
    counts = result["count_reconciliation"]
    return counts["identified_records"] == 10 and counts["valid_records"] == 9 and \
        counts["unique_works"] == 6 and counts["duplicate_observations"] == 3 and \
        counts["single_source_works"] == 4 and counts["multi_source_works"] == 2 and counts["closed"]


def scen_federated_native_query_translation(tmp, name):
    """Each source gets native fields rather than a copied Crossref query."""
    translations = {q["source"]: q for q in federated_search.run(federation_spec())["query_translations"]}
    crossref = translations["crossref"]["translated_query"]["parameters"]
    europe = translations["europepmc"]["translated_query"]["parameters"]["query"]
    openalex = translations["openalex"]["translated_query"]["parameters"]
    return "query.bibliographic" in crossref and "query.author" in crossref and \
        'TITLE:"reproducible detection system"' in europe and 'AUTH:"Jane Doe"' in europe and \
        "title.search:reproducible detection system" in openalex["filter"] and \
        all(q["execution_claim"] == "retained_export_only" for q in translations.values())


def scen_federated_exact_and_fuzzy_dedup(tmp, name):
    """DOI and fuzzy title+author+±1 year observations form one three-view A cluster."""
    result = federated_search.run(federation_spec())
    work = _work_for_doi(result, "10.1000/alpha")
    rules = {d["rule"] for d in result["merge_decisions"] if d.get("merged")}
    return work is not None and len(work["source_records"]) == 3 and \
        set(work["sources"]) == {"crossref", "europepmc", "openalex"} and \
        "doi_exact" in rules and "title_fuzzy_author" in rules


def scen_federated_distinct_doi_and_transitive_veto(tmp, name):
    """X/Y never merge; a missing-DOI fuzzy record cannot bridge two DOI clusters."""
    result = federated_search.run(federation_spec())
    x = _work_for_doi(result, "10.1000/x")
    y = _work_for_doi(result, "10.1000/y")
    rows = [{"source": "crossref", "records": [
        {"id": "a", "doi": "10.10/a", "title": "Triplet work", "year": 2020, "authors": ["J. Doe"]},
        {"id": "b", "title": "Triplet work", "year": 2020, "authors": ["J. Doe"]},
        {"id": "c", "doi": "10.10/c", "title": "Triplet work", "year": 2020, "authors": ["J. Doe"]},
    ]}]
    triple = federated_search.run({"mode": "multi_db", "sources": rows if False else {
        "crossref": {"status": "ok", "records": rows[0]["records"]}},
        "required_sources": ["crossref"]})
    return x["work_id"] != y["work_id"] and triple["unique_work_count"] == 2 and \
        any(d["rule"] == "transitive_identity_veto" for d in triple["merge_decisions"])


def scen_federated_version_merge_lineage(tmp, name):
    """Different preprint/journal DOIs merge only in declared family and both survive."""
    result = federated_search.run(federation_spec())
    work = _work_for_doi(result, "10.1000/version-journal")
    return len(work["version_records"]) == 2 and work["doi"] == "10.1000/version-journal" and \
        set(work["identifiers"]["doi"]) == {"10.1000/version-journal", "10.48550/arxiv.v"} and \
        any(d["rule"] == "declared_version_group" for d in result["merge_decisions"])


def scen_federated_conflicts_preserved(tmp, name):
    """A's 2024/2025 disagreement retains both values and per-record field provenance."""
    result = federated_search.run(federation_spec())
    work = _work_for_doi(result, "10.1000/alpha")
    conflict = next(c for c in work["metadata_conflicts"] if c["field"] == "year")
    return set(conflict["alternative_values_retained"]) == {2024, 2025} and \
        len(work["field_provenance"]["year"]) == 3 and \
        all("raw_record" in r for r in work["source_records"])


def scen_federated_unique_overlap_and_fields(tmp, name):
    """Europe-only C appears in unique coverage and missing journal counts remain visible."""
    result = federated_search.run(federation_spec())
    coverage = result["coverage"]
    unique_ids = coverage["unique_to_source"]["europepmc"]
    return len(unique_ids) == 1 and "10.1000/unique-europe" in \
        _work_for_doi(result, "10.1000/unique-europe")["identifiers"]["doi"] and \
        coverage["field_coverage"]["journal"]["missing"] >= 4 and coverage["pairwise_overlap"]


def scen_federated_source_failure_degrades(tmp, name):
    """Adding an unavailable required source gives a partial review with closed counts, not fake coverage."""
    spec = federation_spec(required_sources=["crossref", "europepmc", "openalex", "semantic_scholar"])
    spec["sources"]["semantic_scholar"] = {"status": "timeout", "error": "deadline exceeded", "records": []}
    result = federated_search.run(spec)
    summary = next(s for s in result["source_coverage"] if s["source"] == "semantic_scholar")
    return result["status"] == "review" and summary["status"] == "timeout" and \
        "semantic_scholar" in result["coverage"]["sources_with_gaps"] and result["count_reconciliation"]["closed"]


def scen_federated_record_rejection_and_filter(tmp, name):
    """Malformed rows and declared exclusions close counts and retain named reasons."""
    spec = federation_spec(exclude_terms=["crossref only"])
    result = federated_search.run(spec)
    counts = result["count_reconciliation"]
    return len(result["rejected_records"]) == 1 and len(result["filtered_records"]) == 1 and \
        counts["filtered_records"] == 1 and counts["unique_works"] == 5 and counts["closed"]


def scen_federated_clean_single_source(tmp, name):
    """A clean one-source export has one work and zero duplicates; no mandatory multi-source padding."""
    result = federated_search.run({"mode": "multi_db", "required_sources": ["crossref"],
        "sources": {"crossref": {"status": "ok", "records": [
            {"id": "one", "doi": "10.1000/one", "title": "One work"}]}}})
    return result["status"] == "clean" and result["unique_work_count"] == 1 and \
        result["duplicate_observations"] == 0 and result["count_reconciliation"]["closed"]


def scen_federated_no_sources_refusal(tmp, name):
    """No source data is an explicit refusal, not a falsely clean empty union."""
    result = federated_search.run({"mode": "multi_db"})
    return result["status"] == "undetermined" and result["refusal"]["rule"] == "multidb.no_sources"


def scen_federated_case_contract_cold_deterministic(tmp, name):
    """Cold import + arbitrary contract fields + byte-identical repeat + no traceback."""
    case = federation_spec(case_id="multi-smoke-001", output_contract={
        "case_id": {}, "results": {}, "query_translations": {}, "source_coverage": {},
        "count_reconciliation": {}, "owner_note": {}, "unavailable": {}}, owner_note="kept")
    # A realistic clean smoke input; malformed rows are covered separately above.
    case["sources"]["crossref"]["records"] = [
        r for r in case["sources"]["crossref"]["records"] if isinstance(r, dict)]
    path = tmp / "case.json"
    path.write_text(json.dumps(case, ensure_ascii=False), encoding="utf-8")
    cold = tmp / "cold"
    shutil.copytree(Path(__file__).resolve().parent.parent, cold)
    blobs, results = [], []
    for label in ("a", "b"):
        out = tmp / label
        proc = subprocess.run([sys.executable, "-I", str(cold / "scripts" / "search_cli.py"),
                               "--case", str(path), "--out", str(out)], capture_output=True,
                              text=True, cwd=str(tmp), timeout=120)
        if proc.returncode != 0 or "Traceback" in proc.stderr:
            return False
        blobs.append((out / "result.json").read_bytes())
        results.append(json.loads(blobs[-1]))
    result = results[0]
    return blobs[0] == blobs[1] and result["case_id"] == "multi-smoke-001" and \
        result["owner_note"] == "kept" and result["unavailable"] is None and \
        len(result["results"]) == 6 and any("unavailable" in x for x in result["limits"])


SCENARIOS = [
    ("doi_merge_key", scen_doi_merge_key),
    ("federated_closed_counts", scen_federated_closed_counts),
    ("federated_native_query_translation", scen_federated_native_query_translation),
    ("federated_exact_and_fuzzy_dedup", scen_federated_exact_and_fuzzy_dedup),
    ("federated_distinct_doi_and_transitive_veto", scen_federated_distinct_doi_and_transitive_veto),
    ("federated_version_merge_lineage", scen_federated_version_merge_lineage),
    ("federated_conflicts_preserved", scen_federated_conflicts_preserved),
    ("federated_unique_overlap_and_fields", scen_federated_unique_overlap_and_fields),
    ("federated_source_failure_degrades", scen_federated_source_failure_degrades),
    ("federated_record_rejection_and_filter", scen_federated_record_rejection_and_filter),
    ("federated_clean_single_source", scen_federated_clean_single_source),
    ("federated_no_sources_refusal", scen_federated_no_sources_refusal),
    ("federated_case_contract_cold_deterministic", scen_federated_case_contract_cold_deterministic),
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
