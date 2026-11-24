"""Benchmark for the search-academic skill (学术文献检索).

Scenarios pin the academic-search behaviours on top of the shared file-search
engine: a bare-string query ranks by distinct matched terms with index-order
ties, an any-list expansion recalls the synonym phrasing while the scope term
stays hard, a scope+topic probe keeps the off-domain record out, a duplicated
export under the same id is skipped and named so the source-id probe counts one
record, evidence locators are verbatim slices, and the CLI ships a green
example plus the exit-5 refusal contract.

    python bench_academic.py
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
    {"id": "a-001",
     "text": "id: a-001\n"
             "Attention-based transformers for protein structure prediction.\n"
             "record-token: a-001\nyear: 2021\njournal: Synthetic compatibility fixture A"},
    {"id": "a-002",
     "text": "id: a-002\n"
             "Self-attention language models recover protein contact maps.\n"
             "record-token: a-002\nyear: 2021"},
    {"id": "a-003",
     "text": "id: a-003\n"
             "Deep learning for protein structure prediction: a survey.\n"
             "record-token: a-003\nyear: 2022"},
    {"id": "a-004",
     "text": "id: a-004\n"
             "Dietary protein intake and ageing: a cohort study.\n"
             "record-token: a-004\nyear: 2020"},
    {"id": "a-001",
     "text": "id: a-001\n"
             "Attention-based transformers for protein structure prediction.\n"
             "record-token: a-001\nyear: 2021\njournal: Synthetic compatibility fixture A"},
]

EXPANSION = {"all": ["protein"], "any": ["transformer", "attention"]}

EXAMPLE_QUERY = EXPANSION

EXAMPLES = Path(__file__).resolve().parent.parent / "examples"
CLI = Path(__file__).resolve().parent / "search_cli.py"


def _run_cli(out, query_file=None):
    args = [sys.executable, "-B", "-I", "-X", "utf8", str(CLI), "--corpus", str(EXAMPLES / "corpus.json"),
            "--out", str(out)]
    args += ["--query-file", str(query_file or (EXAMPLES / "query.json"))]
    return subprocess.run(args, capture_output=True, text=True, timeout=120)


def scen_keyword_query_ranked(tmp, name):
    """A bare-string query ranks by distinct matched terms; ties keep index order."""
    _, res = search.search({"corpus": CORPUS, "query": "protein structure prediction"})
    order = [h["doc_id"] for h in res["hits"]]
    scores = [h["score"] for h in res["hits"]]
    return res["ok"] and order == ["a-001", "a-003", "a-002", "a-004"] \
        and scores == [3, 3, 1, 1] and res["documents_indexed"] == 4


def scen_expansion_any_list(tmp, name):
    """The any-list recalls the synonym phrasing; the scope term stays hard."""
    _, res = search.search({"corpus": CORPUS, "query": EXPANSION})
    ids = [h["doc_id"] for h in res["hits"]]
    return res["ok"] and ids == ["a-001", "a-002"] \
        and res["hits"][0]["score"] == 3 and res["hits"][1]["score"] == 2


def scen_scope_guard(tmp, name):
    """Scope + topic keeps the off-domain dietary cohort out."""
    _, res = search.search({"corpus": CORPUS, "query": {"all": ["protein", "prediction"]}})
    ids = [h["doc_id"] for h in res["hits"]]
    return res["ok"] and ids == ["a-001", "a-003"] \
        and "a-004" not in ids and "a-002" not in ids


def scen_duplicate_export_named(tmp, name):
    """The duplicated export is skipped and named; the source-id probe counts one record."""
    f = None
    _, res = search.search({"corpus": CORPUS,
                            "query": {"all": ["a-001"]}})
    f = next((x for x in res.get("findings", []) if x["rule"] == "search.doc_skipped"), None)
    return res["ok"] and [h["doc_id"] for h in res["hits"]] == ["a-001"] \
        and f is not None and f["count"] == 1 \
        and "duplicate doc id 'a-001'" in f["entries"][0]["reason"]


def scen_hit_locator_verbatim(tmp, name):
    """Every hit's passage quote equals the indexed paragraph slice."""
    docs = search.build_index(CORPUS)["index"]["documents"]
    _, res = search.search({"corpus": CORPUS, "query": EXPANSION})
    ok = len(res["hits"]) == 2
    for hit in res["hits"]:
        paras = docs[hit["doc_id"]]["paragraphs"]
        for p in hit["passages"]:
            loc = p["locator"]
            ok = ok and paras[loc["paragraph"]][loc["start"]:loc["end"]] == loc["quote"]
    return ok


def scen_replay_identical(tmp, name):
    """The query battery reruns byte-identical — the search path is reproducible."""
    battery = ["protein structure prediction", EXPANSION,
               {"all": ["protein", "prediction"]}]
    runs = []
    for _ in range(2):
        runs.append(json.dumps([search.search({"corpus": CORPUS, "query": q})[1]
                                for q in battery], ensure_ascii=False, sort_keys=True))
    return runs[0] == runs[1]


def scen_cli_examples_run(tmp, name):
    """The shipped example runs green: exit 0, the two transformer records ranked."""
    out = tmp / "out-ex"
    proc = _run_cli(out)
    if proc.returncode != 0 or not (out / "index.json").exists():
        return False
    res = json.loads((out / "result.json").read_text(encoding="utf-8"))
    idx = json.loads((out / "index.json").read_text(encoding="utf-8"))
    return res["ok"] and not res["empty"] \
        and [h["doc_id"] for h in res["hits"]] == ["a-001", "a-002"] \
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
    ("keyword_query_ranked", scen_keyword_query_ranked),
    ("expansion_any_list", scen_expansion_any_list),
    ("scope_guard", scen_scope_guard),
    ("duplicate_export_named", scen_duplicate_export_named),
    ("hit_locator_verbatim", scen_hit_locator_verbatim),
    ("replay_identical", scen_replay_identical),
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
    report = {"schema_version": "academic-bench/v1", "scenarios": rows,
              "totals": {"passed": passed, "of": len(rows)}}
    (Path(__file__).resolve().parent / "report_academic.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n{passed}/{len(rows)} scenarios pass")
    return 0 if passed == len(rows) else 1


if __name__ == "__main__":
    raise SystemExit(main())
