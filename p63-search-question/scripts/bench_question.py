"""Benchmark for the search-question skill (科研问题驱动检索).

Scenarios pin the question-driven behaviours on top of the shared file-search
engine: a complex question decomposes into frozen sub-question probes (object
AND mechanism / method tokens), the object scope keeps off-topic electrolytes
out, a sub-question with no supporting evidence returns an honest empty (the
research gap is a record), round-2 probes reuse a term discovered in round-1
with a quotable locator, evidence locators are verbatim slices, and the CLI
ships a green example plus the exit-5 refusal contract.

    python bench_question.py
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
    {"id": "p-001",
     "text": "id: p-001\n对象: 固态电解质\n"
             "Mechanism: grain-boundary lithium transport limits ionic conductivity.\n"
             "Method: impedance spectroscopy with blocking electrodes."},
    {"id": "p-002",
     "text": "id: p-002\n对象: 固态电解质\n"
             "Mechanism: space-charge layers at electrode interfaces raise interfacial "
             "resistance.\nMethod: impedance spectroscopy, symmetric cells."},
    {"id": "p-003",
     "text": "id: p-003\n对象: liquid electrolyte\n"
             "Mechanism: solvent coordination governs ion pairing.\n"
             "Method: Raman spectroscopy."},
    {"id": "p-004",
     "text": "id: p-004\n对象: 固态电解质\n"
             "Mechanism: dendrite penetration through grain boundaries at high current.\n"
             "Method: operando microscopy."},
    {"id": "p-005",
     "text": "id: p-005\n对象: polymer electrolyte\n"
             "Mechanism: segmental motion couples to ion transport.\n"
             "Method: dielectric relaxation spectroscopy."},
]

S1_MECHANISM = {"all": ["固态电解质", "grain"]}
S2_METHOD = {"all": ["固态电解质", "impedance"]}
S3_GAP = {"all": ["固态电解质", "grain", "simulation"]}

EXAMPLE_QUERY = S1_MECHANISM

EXAMPLES = Path(__file__).resolve().parent.parent / "examples"
CLI = Path(__file__).resolve().parent / "search_cli.py"


def _run_cli(out, query_file=None):
    args = [sys.executable, "-B", "-I", "-X", "utf8", str(CLI), "--corpus", str(EXAMPLES / "corpus.json"),
            "--out", str(out)]
    args += ["--query-file", str(query_file or (EXAMPLES / "query.json"))]
    return subprocess.run(args, capture_output=True, text=True, timeout=120)


def scen_decomposition_probes(tmp, name):
    """Sub-question probes cover the mechanism and the method evidence separately."""
    _, s1 = search.search({"corpus": CORPUS, "query": S1_MECHANISM})
    _, s2 = search.search({"corpus": CORPUS, "query": S2_METHOD})
    return [h["doc_id"] for h in s1["hits"]] == ["p-001", "p-004"] \
        and [h["doc_id"] for h in s2["hits"]] == ["p-001", "p-002"]


def scen_object_scope_guard(tmp, name):
    """The object scope keeps the liquid and polymer electrolyte papers out."""
    _, res = search.search({"corpus": CORPUS, "query": {"all": ["固态电解质"]}})
    ids = [h["doc_id"] for h in res["hits"]]
    return res["ok"] and ids == ["p-001", "p-002", "p-004"] \
        and "p-003" not in ids and "p-005" not in ids


def scen_gap_honest_empty(tmp, name):
    """A sub-question with no supporting evidence is an honest empty — the gap is a record."""
    _, res = search.search({"corpus": CORPUS, "query": S3_GAP})
    return res["ok"] and res["empty"] is True and res["hits"] == [] \
        and res["query"] == {"all": ["固态电解质", "grain", "simulation"], "any": []} \
        and "never padded" in res["note"]


def scen_round2_discovered_term(tmp, name):
    """Round 2 reuses a term discovered in round 1 and lands on the quotable mechanism."""
    _, r1 = search.search({"corpus": CORPUS, "query": {"all": ["space-charge"]}})
    _, r2 = search.search({"corpus": CORPUS,
                           "query": {"all": ["space-charge", "resistance"]}})
    terms = {p["term"] for h in r2["hits"] for p in h["passages"]}
    return [h["doc_id"] for h in r1["hits"]] == ["p-002"] \
        and [h["doc_id"] for h in r2["hits"]] == ["p-002"] \
        and {"space-charge", "resistance"} <= terms


def scen_evidence_locator_verbatim(tmp, name):
    """Every sub-question hit carries a locator whose quote equals the paragraph slice."""
    docs = search.build_index(CORPUS)["index"]["documents"]
    ok = True
    for probe in (S1_MECHANISM, S2_METHOD):
        _, res = search.search({"corpus": CORPUS, "query": probe})
        for hit in res["hits"]:
            paras = docs[hit["doc_id"]]["paragraphs"]
            for p in hit["passages"]:
                loc = p["locator"]
                ok = ok and paras[loc["paragraph"]][loc["start"]:loc["end"]] == loc["quote"]
    return ok


def scen_probes_replay_identical(tmp, name):
    """The sub-question battery reruns byte-identical — the retrieval path is reproducible."""
    battery = [S1_MECHANISM, S2_METHOD, S3_GAP, {"all": ["space-charge"]}]
    runs = []
    for _ in range(2):
        runs.append(json.dumps([search.search({"corpus": CORPUS, "query": q})[1]
                                for q in battery], ensure_ascii=False, sort_keys=True))
    return runs[0] == runs[1]


def scen_cli_examples_run(tmp, name):
    """The shipped example runs green: exit 0, the two grain-boundary mechanism records."""
    out = tmp / "out-ex"
    proc = _run_cli(out)
    if proc.returncode != 0 or not (out / "index.json").exists():
        return False
    res = json.loads((out / "result.json").read_text(encoding="utf-8"))
    idx = json.loads((out / "index.json").read_text(encoding="utf-8"))
    return res["ok"] and not res["empty"] \
        and [h["doc_id"] for h in res["hits"]] == ["p-001", "p-004"] \
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
    ("decomposition_probes", scen_decomposition_probes),
    ("object_scope_guard", scen_object_scope_guard),
    ("gap_honest_empty", scen_gap_honest_empty),
    ("round2_discovered_term", scen_round2_discovered_term),
    ("evidence_locator_verbatim", scen_evidence_locator_verbatim),
    ("probes_replay_identical", scen_probes_replay_identical),
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
    report = {"schema_version": "question-bench/v1", "scenarios": rows,
              "totals": {"passed": passed, "of": len(rows)}}
    (Path(__file__).resolve().parent / "report_question.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n{passed}/{len(rows)} scenarios pass")
    return 0 if passed == len(rows) else 1


if __name__ == "__main__":
    raise SystemExit(main())
