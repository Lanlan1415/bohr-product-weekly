"""Benchmark for the search-coverage skill (检索覆盖率与遗漏分析).

Scenarios pin the coverage-specific behaviours on top of the shared file-search
engine: one frozen probe per reference work, an honest empty probe record for a
reference the corpus lacks (the miss is a record, not a redefinition), duplicate
candidate exports skipped so the denominator is not inflated, and a byte-identical
rerun so coverage is recomputable — plus the CLI happy path on the shipped example
and the exit-5 refusal contract.

    python bench_coverage.py
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
     "text": "Irreversible electroporation for locally advanced pancreatic cancer: "
             "a prospective cohort.\n"
             "Ninety patients received electroporation ablation with a median "
             "survival of 18 months."},
    {"id": "cand-002",
     "text": "Nanoknife ablation of the pancreas: a multicentre registry.\n"
             "The nanoknife device delivered 90 pulses across three electrodes."},
    {"id": "cand-003",
     "text": "Thermal radiofrequency ablation of liver tumours.\n"
             "Radiofrequency electrodes were placed percutaneously; no pancreas "
             "involvement in this series."},
    {"id": "cand-004",
     "text": "EUS-guided fiducial placement before stereotactic radiotherapy.\n"
             "No ablation device was used in this cohort."},
    {"id": "cand-002",
     "text": "Nanoknife ablation of the pancreas: a multicentre registry.\n"
             "The nanoknife device delivered 90 pulses across three electrodes."},
]

REFERENCE = [
    {"ref_id": "ref-01", "probe": {"all": ["electroporation", "pancreatic"]}},
    {"ref_id": "ref-02", "probe": {"all": ["nanoknife", "pancreas"]}},
    {"ref_id": "ref-03", "probe": {"all": ["electroporation", "murine"]}},
]

EXAMPLE_QUERY = {"all": ["nanoknife", "pancreas"]}

EXAMPLES = Path(__file__).resolve().parent.parent / "examples"
CLI = Path(__file__).resolve().parent / "search_cli.py"


def _run_cli(out, query_file=None):
    args = [sys.executable, str(CLI), "--corpus", str(EXAMPLES / "corpus.json"),
            "--out", str(out)]
    if query_file is not None:
        args += ["--query-file", str(query_file)]
    else:
        args += ["--query-file", str(EXAMPLES / "query.json")]
    return subprocess.run(args, capture_output=True, text=True, timeout=120)


def scen_reference_probe_hit(tmp, name):
    """Frozen probes hit the retrieved candidates for ref-01 and ref-02."""
    ids = {}
    passages_ok = True
    for ref in REFERENCE[:2]:
        _, res = search.search({"corpus": CORPUS, "query": ref["probe"]})
        ids[ref["ref_id"]] = [h["doc_id"] for h in res["hits"]]
        passages_ok = passages_ok and all(h["passages"] for h in res["hits"])
    return ids["ref-01"] == ["cand-001"] and ids["ref-02"] == ["cand-002"] \
        and passages_ok


def scen_reference_miss_honest(tmp, name):
    """A reference the corpus lacks returns an honest empty probe record."""
    _, res = search.search({"corpus": CORPUS, "query": REFERENCE[2]["probe"]})
    return res["ok"] and res["empty"] is True and res["hits"] == [] \
        and "never padded" in res["note"] and res["documents_indexed"] == 4 \
        and res["query"] == {"all": ["electroporation", "murine"], "any": []}


def scen_duplicate_export_named(tmp, name):
    """A duplicated candidate export is skipped and named; denominator stays 4."""
    _, res = search.search({"corpus": CORPUS, "query": REFERENCE[0]["probe"]})
    f = next((x for x in res.get("findings", []) if x["rule"] == "search.doc_skipped"), None)
    return res["ok"] and f is not None and f["count"] == 1 \
        and "duplicate doc id 'cand-002'" in f["entries"][0]["reason"] \
        and res["documents_indexed"] == 4


def scen_coverage_ledger_replay(tmp, name):
    """Rerunning the probe battery is byte-identical, so coverage is recomputable."""
    runs = []
    for _ in range(2):
        battery = [search.search({"corpus": CORPUS, "query": r["probe"]})[1] for r in REFERENCE]
        runs.append(json.dumps(battery, ensure_ascii=False, sort_keys=True))
    return runs[0] == runs[1]


def scen_probe_not_relaxed(tmp, name):
    """A probe whose full all-set is unsatisfiable stays empty — never degraded."""
    _, res = search.search({"corpus": CORPUS,
                            "query": {"all": ["electroporation", "pancreatic", "murine"]}})
    return res["ok"] and res["empty"] is True and res["hits"] == []


def scen_hit_locator_verbatim(tmp, name):
    """Every probe-hit passage quote equals the indexed paragraph slice."""
    docs = search.build_index(CORPUS)["index"]["documents"]
    ok = True
    for ref in REFERENCE[:2]:
        _, res = search.search({"corpus": CORPUS, "query": ref["probe"]})
        for hit in res["hits"]:
            paras = docs[hit["doc_id"]]["paragraphs"]
            for p in hit["passages"]:
                loc = p["locator"]
                ok = ok and paras[loc["paragraph"]][loc["start"]:loc["end"]] == loc["quote"]
    return ok and res["hits"][0]["passages"][0]["term"] in ("electroporation", "nanoknife")


def scen_cli_examples_run(tmp, name):
    """The shipped example runs green: exit 0, index.json + result.json, ref-02 hit."""
    out = tmp / "out-ex"
    proc = _run_cli(out)
    if proc.returncode != 0 or not (out / "index.json").exists():
        return False
    res = json.loads((out / "result.json").read_text(encoding="utf-8"))
    idx = json.loads((out / "index.json").read_text(encoding="utf-8"))
    return res["ok"] and not res["empty"] \
        and [h["doc_id"] for h in res["hits"]] == ["cand-002"] \
        and idx["corpus_sha256"][:16] == res["index_sha256"] \
        and res["documents_indexed"] == 4


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
    ("reference_probe_hit", scen_reference_probe_hit),
    ("reference_miss_honest", scen_reference_miss_honest),
    ("duplicate_export_named", scen_duplicate_export_named),
    ("coverage_ledger_replay", scen_coverage_ledger_replay),
    ("probe_not_relaxed", scen_probe_not_relaxed),
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
    report = {"schema_version": "coverage-bench/v1", "scenarios": rows,
              "totals": {"passed": passed, "of": len(rows)}}
    (Path(__file__).resolve().parent / "report_coverage.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n{passed}/{len(rows)} scenarios pass")
    return 0 if passed == len(rows) else 1


if __name__ == "__main__":
    raise SystemExit(main())
