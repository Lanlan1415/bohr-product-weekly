"""Benchmark for the search-systematic-review skill (系统性文献综述).

Scenarios pin the review-chain behaviours on top of the shared file-search
engine: the frozen protocol probe (design AND population) drives the
title/abstract stage, the retraction probe is subtracted explicitly for the
final include set, every exclusion keeps a located reason probe, the quality
query isolates the low-risk studies, the PRISMA counts close (identified =
duplicates + screened; screened = included-at-screening + excluded), and the
CLI ships a green example plus the exit-5 refusal contract.

    python bench_sysrev.py
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
    {"id": "sr-001",
     "text": "id: sr-001\ndesign: randomised\n"
             "adults with chronic low back pain\n"
             "exercise therapy reduced pain at 12 months\nrisk: low"},
    {"id": "sr-002",
     "text": "id: sr-002\ndesign: randomised\n"
             "adults with chronic low back pain\n"
             "exercise therapy did not differ from usual care\nrisk: low"},
    {"id": "sr-003",
     "text": "id: sr-003\ndesign: randomised\n"
             "adolescents with scoliosis\n"
             "exercise therapy outcomes reported\nrisk: some"},
    {"id": "sr-004",
     "text": "id: sr-004\ndesign: cohort\n"
             "adults with chronic low back pain\n"
             "observational exercise cohort\nrisk: high"},
    {"id": "sr-005",
     "text": "id: sr-005\ndesign: randomised\n"
             "adults with chronic low back pain\n"
             "yoga-based exercise improved function\nrisk: some"},
    {"id": "sr-006",
     "text": "id: sr-006\ndesign: protocol\n"
             "adults with chronic low back pain\n"
             "study protocol only, no outcome data\nrisk: n/a"},
    {"id": "sr-002",
     "text": "id: sr-002\ndesign: randomised\n"
             "adults with chronic low back pain\n"
             "exercise therapy did not differ from usual care\nrisk: low"},
    {"id": "sr-007",
     "text": "id: sr-007\ndesign: randomised\n"
             "adults with chronic low back pain\n"
             "retracted: this randomised exercise trial was retracted in 2026\nrisk: high"},
]

PROTOCOL = {"all": ["design: randomised", "chronic low back pain"]}

EXAMPLE_QUERY = PROTOCOL

EXAMPLES = Path(__file__).resolve().parent.parent / "examples"
CLI = Path(__file__).resolve().parent / "search_cli.py"


def _run_cli(out, query_file=None):
    args = [sys.executable, str(CLI), "--corpus", str(EXAMPLES / "corpus.json"),
            "--out", str(out)]
    args += ["--query-file", str(query_file or (EXAMPLES / "query.json"))]
    return subprocess.run(args, capture_output=True, text=True, timeout=120)


def scen_protocol_screening(tmp, name):
    """The frozen protocol probe passes exactly the four eligible-at-screening records."""
    _, res = search.search({"corpus": CORPUS, "query": PROTOCOL})
    ids = [h["doc_id"] for h in res["hits"]]
    return res["ok"] and ids == ["sr-001", "sr-002", "sr-005", "sr-007"] \
        and res["documents_indexed"] == 7


def scen_retraction_subtraction(tmp, name):
    """The retraction probe is subtracted explicitly: the final include set has three."""
    _, inc = search.search({"corpus": CORPUS, "query": PROTOCOL})
    _, retr = search.search({"corpus": CORPUS, "query": {"all": ["retracted"]}})
    included = [h["doc_id"] for h in inc["hits"]]
    retracted = [h["doc_id"] for h in retr["hits"]]
    final = [x for x in included if x not in retracted]
    return retracted == ["sr-007"] and final == ["sr-001", "sr-002", "sr-005"]


def scen_exclusion_evidence(tmp, name):
    """Every exclusion keeps a located reason probe quoting the failing criterion."""
    _, e_pop = search.search({"corpus": CORPUS, "query": {"all": ["sr-003", "scoliosis"]}})
    _, e_des = search.search({"corpus": CORPUS, "query": {"all": ["sr-004", "design: cohort"]}})
    _, e_data = search.search({"corpus": CORPUS, "query": {"all": ["sr-006", "protocol"]}})
    quotes = set()
    for r in (e_pop, e_des, e_data):
        quotes |= {p["locator"]["quote"] for h in r["hits"] for p in h["passages"]}
    return all(len(r["hits"]) == 1 for r in (e_pop, e_des, e_data)) \
        and {"scoliosis", "design: cohort", "protocol"} <= quotes


def scen_quality_appraisal_query(tmp, name):
    """The quality query isolates the low-risk studies for the synthesis step."""
    _, res = search.search({"corpus": CORPUS, "query": {"all": ["risk: low"]}})
    ids = sorted(h["doc_id"] for h in res["hits"])
    return res["ok"] and ids == ["sr-001", "sr-002"] and "sr-007" not in ids


def scen_prisma_counts_close(tmp, name):
    """identified (8) = duplicates (1, named) + screened (7); screening includes 4."""
    _, res = search.search({"corpus": CORPUS, "query": PROTOCOL})
    f = next((x for x in res.get("findings", []) if x["rule"] == "search.doc_skipped"), None)
    return res["ok"] and len(CORPUS) == 8 and res["documents_indexed"] == 7 \
        and f is not None and f["count"] == 1 \
        and "duplicate doc id 'sr-002'" in f["entries"][0]["reason"] \
        and len(res["hits"]) == 4


def scen_evidence_locator_verbatim(tmp, name):
    """Every screening-hit passage quote equals the indexed paragraph slice."""
    docs = search.build_index(CORPUS)["index"]["documents"]
    _, res = search.search({"corpus": CORPUS, "query": PROTOCOL})
    ok = len(res["hits"]) == 4
    for hit in res["hits"]:
        paras = docs[hit["doc_id"]]["paragraphs"]
        for p in hit["passages"]:
            loc = p["locator"]
            ok = ok and paras[loc["paragraph"]][loc["start"]:loc["end"]] == loc["quote"]
    return ok


def scen_protocol_replay_identical(tmp, name):
    """The protocol battery reruns byte-identical — the review chain is reproducible."""
    battery = [PROTOCOL, {"all": ["retracted"]}, {"all": ["risk: low"]}]
    runs = []
    for _ in range(2):
        runs.append(json.dumps([search.search({"corpus": CORPUS, "query": q})[1]
                                for q in battery], ensure_ascii=False, sort_keys=True))
    return runs[0] == runs[1]


def scen_cli_examples_run(tmp, name):
    """The shipped example runs green: exit 0, the four screening-eligible records."""
    out = tmp / "out-ex"
    proc = _run_cli(out)
    if proc.returncode != 0 or not (out / "index.json").exists():
        return False
    res = json.loads((out / "result.json").read_text(encoding="utf-8"))
    idx = json.loads((out / "index.json").read_text(encoding="utf-8"))
    return res["ok"] and not res["empty"] \
        and [h["doc_id"] for h in res["hits"]] == ["sr-001", "sr-002", "sr-005", "sr-007"] \
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
    ("protocol_screening", scen_protocol_screening),
    ("retraction_subtraction", scen_retraction_subtraction),
    ("exclusion_evidence", scen_exclusion_evidence),
    ("quality_appraisal_query", scen_quality_appraisal_query),
    ("prisma_counts_close", scen_prisma_counts_close),
    ("evidence_locator_verbatim", scen_evidence_locator_verbatim),
    ("protocol_replay_identical", scen_protocol_replay_identical),
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
    report = {"schema_version": "sysrev-bench/v1", "scenarios": rows,
              "totals": {"passed": passed, "of": len(rows)}}
    (Path(__file__).resolve().parent / "report_sysrev.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n{passed}/{len(rows)} scenarios pass")
    return 0 if passed == len(rows) else 1


if __name__ == "__main__":
    raise SystemExit(main())
