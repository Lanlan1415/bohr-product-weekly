"""Benchmark for the search-filter-rank skill (文献筛选与智能排序).

Scenarios pin the screening/ranking behaviours on top of the shared file-search
engine: score = distinct matched criteria terms so evidence-rich records rise,
ties keep index order so the ranking is deterministic, a keyword-rich record
missing the design term stays excluded (the all-constraint is never relaxed),
the top-k cut is a function of corpus + query alone, layer labels derive from
the matched terms, and the CLI ships a green example plus the exit-5 refusal
contract.

    python bench_filter_rank.py
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
    {"id": "cand-001",
     "text": "id: cand-001\n"
             "Additive manufacturing of Ti-6Al-4V.\n"
             "Cooling rate controls the microstructure; columnar grains were mapped."},
    {"id": "cand-002",
     "text": "id: cand-002\n"
             "Additive manufacturing process windows for 316L steel.\n"
             "Solidification mapping predicted the microstructure."},
    {"id": "cand-003",
     "text": "id: cand-003\n"
             "Additive manufacturing machine calibration guide.\n"
             "No microstructure or cooling measurements reported."},
    {"id": "cand-004",
     "text": "id: cand-004\n"
             "Conventional casting of aluminium alloys.\n"
             "Cooling rate and microstructure correlations along the casting route."},
    {"id": "cand-005",
     "text": "id: cand-005\n"
             "Review of additive manufacturing defects.\n"
             "Porosity taxonomy; microstructure briefly mentioned."},
    {"id": "cand-006",
     "text": "id: cand-006\n"
             "Additive manufacturing of Ti-6Al-4V lattices.\n"
             "Cooling rate mapped to microstructure; ductility trade-offs."},
]

QUERY = {"all": ["additive"],
         "any": ["cooling rate", "solidification", "microstructure"]}

EXAMPLE_QUERY = QUERY

EXAMPLES = Path(__file__).resolve().parent.parent / "examples"
CLI = Path(__file__).resolve().parent / "search_cli.py"


def _run_cli(out, query_file=None):
    args = [sys.executable, str(CLI), "--corpus", str(EXAMPLES / "corpus.json"),
            "--out", str(out)]
    args += ["--query-file", str(query_file or (EXAMPLES / "query.json"))]
    return subprocess.run(args, capture_output=True, text=True, timeout=120)


def scen_rank_order_scores(tmp, name):
    """Score = distinct matched terms; the expected order and scores come back."""
    _, res = search.search({"corpus": CORPUS, "query": QUERY})
    order = [h["doc_id"] for h in res["hits"]]
    scores = [h["score"] for h in res["hits"]]
    return res["ok"] and order == ["cand-001", "cand-002", "cand-006", "cand-003", "cand-005"] \
        and scores == [3, 3, 3, 2, 2]


def scen_hard_exclusion_not_relaxed(tmp, name):
    """A keyword-rich record missing the design term stays excluded — no relaxation."""
    _, res = search.search({"corpus": CORPUS, "query": QUERY})
    ids = [h["doc_id"] for h in res["hits"]]
    return res["ok"] and "cand-004" not in ids and res["documents_indexed"] == 6


def scen_topk_cut(tmp, name):
    """The top-3 cut is deterministic and puts the three evidence-rich records first."""
    _, res = search.search({"corpus": CORPUS, "query": QUERY})
    return [h["doc_id"] for h in res["hits"][:3]] == ["cand-001", "cand-002", "cand-006"]


def scen_ties_keep_index_order(tmp, name):
    """Equal scores keep corpus order — two reruns are byte-identical."""
    r1 = search.search({"corpus": CORPUS, "query": QUERY})[1]
    r2 = search.search({"corpus": CORPUS, "query": QUERY})[1]
    return json.dumps(r1, ensure_ascii=False, sort_keys=True) \
        == json.dumps(r2, ensure_ascii=False, sort_keys=True) \
        and r1["hits"][3]["doc_id"] == "cand-003" and r1["hits"][4]["doc_id"] == "cand-005"


def scen_layer_labels(tmp, name):
    """Layer labels derive from matched terms: primary (3 terms) vs secondary (2 terms)."""
    _, res = search.search({"corpus": CORPUS, "query": QUERY})
    primary = [h["doc_id"] for h in res["hits"] if h["score"] == 3]
    secondary = [h["doc_id"] for h in res["hits"] if h["score"] == 2]
    m5 = next(h for h in res["hits"] if h["doc_id"] == "cand-005")
    return primary == ["cand-001", "cand-002", "cand-006"] \
        and secondary == ["cand-003", "cand-005"] \
        and m5["matched_terms"] == ["additive", "microstructure"]


def scen_hit_locator_verbatim(tmp, name):
    """Every ranked hit's passage quote equals the indexed paragraph slice."""
    docs = search.build_index(CORPUS)["index"]["documents"]
    _, res = search.search({"corpus": CORPUS, "query": QUERY})
    ok = len(res["hits"]) == 5
    for hit in res["hits"]:
        paras = docs[hit["doc_id"]]["paragraphs"]
        for p in hit["passages"]:
            loc = p["locator"]
            ok = ok and paras[loc["paragraph"]][loc["start"]:loc["end"]] == loc["quote"]
    return ok


def scen_cli_examples_run(tmp, name):
    """The shipped example runs green: exit 0, the ranked list in bench order."""
    out = tmp / "out-ex"
    proc = _run_cli(out)
    if proc.returncode != 0 or not (out / "index.json").exists():
        return False
    res = json.loads((out / "result.json").read_text(encoding="utf-8"))
    idx = json.loads((out / "index.json").read_text(encoding="utf-8"))
    return res["ok"] and not res["empty"] \
        and [h["doc_id"] for h in res["hits"]] \
        == ["cand-001", "cand-002", "cand-006", "cand-003", "cand-005"] \
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
    ("rank_order_scores", scen_rank_order_scores),
    ("hard_exclusion_not_relaxed", scen_hard_exclusion_not_relaxed),
    ("topk_cut", scen_topk_cut),
    ("ties_keep_index_order", scen_ties_keep_index_order),
    ("layer_labels", scen_layer_labels),
    ("hit_locator_verbatim", scen_hit_locator_verbatim),
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
    report = {"schema_version": "filter-rank-bench/v1", "scenarios": rows,
              "totals": {"passed": passed, "of": len(rows)}}
    (Path(__file__).resolve().parent / "report_filter_rank.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n{passed}/{len(rows)} scenarios pass")
    return 0 if passed == len(rows) else 1


if __name__ == "__main__":
    raise SystemExit(main())
