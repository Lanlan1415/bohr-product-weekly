"""Benchmark for the search-systematic skill (系统性文献检索与纳排筛选).

Scenarios pin the PRISMA-style screening behaviours on top of the shared
file-search engine: a frozen protocol probe (design AND population tokens)
returns only eligible records, every exclusion keeps a located reason-code
probe, the audit counts close (identified = duplicates + screened), criteria
are never relaxed, the protocol battery reruns byte-identical, and the CLI
ships a green example plus the exit-5 refusal contract.

    python bench_systematic.py
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
    {"id": "rec-001",
     "text": "Screening record rec-001.\n"
             "Design: randomised controlled trial. Population: adults with type 2 diabetes.\n"
             "Excerpt: HbA1c fell 0.9 percent over 24 weeks."},
    {"id": "rec-002",
     "text": "Screening record rec-002.\n"
             "Design: cohort study. Population: adults with type 2 diabetes.\n"
             "Excerpt: retrospective allocation, 6-year follow-up."},
    {"id": "rec-003",
     "text": "Screening record rec-003.\n"
             "Design: randomised controlled trial. Population: paediatric asthma.\n"
             "Excerpt: children aged 6 to 12 years."},
    {"id": "rec-001",
     "text": "Screening record rec-001.\n"
             "Design: randomised controlled trial. Population: adults with type 2 diabetes.\n"
             "Excerpt: duplicate database export of the same study."},
    {"id": "rec-005",
     "text": "Screening record rec-005.\n"
             "Design: systematic review. Population: adults with type 2 diabetes.\n"
             "Excerpt: pooled 32 trials, no new data."},
    {"id": "rec-006",
     "text": "Screening record rec-006.\n"
             "Design: randomised controlled trial. Population: adults with hypertension.\n"
             "Excerpt: different population from the review question."},
]

PROTOCOL = {"all": ["randomised", "diabetes"]}

EXAMPLE_QUERY = PROTOCOL

EXAMPLES = Path(__file__).resolve().parent.parent / "examples"
CLI = Path(__file__).resolve().parent / "search_cli.py"


def _run_cli(out, query_file=None):
    args = [sys.executable, str(CLI), "--corpus", str(EXAMPLES / "corpus.json"),
            "--out", str(out)]
    args += ["--query-file", str(query_file or (EXAMPLES / "query.json"))]
    return subprocess.run(args, capture_output=True, text=True, timeout=120)


def scen_protocol_include(tmp, name):
    """The frozen protocol probe includes exactly the design+population eligible record."""
    _, res = search.search({"corpus": CORPUS, "query": PROTOCOL})
    return res["ok"] and [h["doc_id"] for h in res["hits"]] == ["rec-001"] \
        and res["documents_indexed"] == 5 \
        and res["hits"][0]["matched_terms"] == ["diabetes", "randomised"]


def scen_exclusion_reason_probes(tmp, name):
    """Each exclusion keeps a located reason probe: the failing criterion stays honest-empty."""
    _, e1 = search.search({"corpus": CORPUS, "query": {"all": ["rec-002", "randomised"]}})
    _, e2 = search.search({"corpus": CORPUS, "query": {"all": ["rec-005", "randomised"]}})
    _, e3 = search.search({"corpus": CORPUS, "query": {"all": ["rec-003", "diabetes"]}})
    _, h1 = search.search({"corpus": CORPUS, "query": {"all": ["rec-002", "cohort study"]}})
    _, h3 = search.search({"corpus": CORPUS, "query": {"all": ["rec-003", "paediatric asthma"]}})
    empties = all(r["empty"] is True and r["hits"] == [] for r in (e1, e2, e3))
    quotes = {p["locator"]["quote"] for h in (h1, h3) for p in h["hits"][0]["passages"]}
    return empties and [h["doc_id"] for h in h1["hits"]] == ["rec-002"] \
        and [h["doc_id"] for h in h3["hits"]] == ["rec-003"] \
        and "cohort study" in quotes and "paediatric asthma" in quotes


def scen_audit_counts_close(tmp, name):
    """identified (6 entries) = duplicates (1, named) + screened (5, indexed)."""
    _, res = search.search({"corpus": CORPUS, "query": PROTOCOL})
    f = next((x for x in res.get("findings", []) if x["rule"] == "search.doc_skipped"), None)
    return res["ok"] and len(CORPUS) == 6 and res["documents_indexed"] == 5 \
        and f is not None and f["count"] == 1 \
        and "duplicate doc id 'rec-001'" in f["entries"][0]["reason"]


def scen_criteria_not_relaxed(tmp, name):
    """Adding an unsatisfiable criterion stays empty — the protocol is never loosened."""
    _, res = search.search({"corpus": CORPUS,
                            "query": {"all": ["randomised", "diabetes", "elderly"]}})
    return res["ok"] and res["empty"] is True and res["hits"] == []


def scen_protocol_replay_identical(tmp, name):
    """The protocol battery reruns byte-identical — same records, same labels."""
    battery = [{"all": ["randomised", "diabetes"]},
               {"all": ["randomised"]},
               {"all": ["diabetes"]}]
    runs = []
    for _ in range(2):
        runs.append(json.dumps([search.search({"corpus": CORPUS, "query": q})[1]
                                for q in battery], ensure_ascii=False, sort_keys=True))
    return runs[0] == runs[1]


def scen_included_hit_verbatim(tmp, name):
    """The included record's passages quote the protocol criteria verbatim."""
    docs = search.build_index(CORPUS)["index"]["documents"]
    _, res = search.search({"corpus": CORPUS, "query": PROTOCOL})
    paras = docs["rec-001"]["paragraphs"]
    ok = True
    for p in res["hits"][0]["passages"]:
        loc = p["locator"]
        ok = ok and paras[loc["paragraph"]][loc["start"]:loc["end"]] == loc["quote"]
    quotes = {p["locator"]["quote"] for p in res["hits"][0]["passages"]}
    return ok and quotes >= {"randomised", "diabetes"}


def scen_cli_examples_run(tmp, name):
    """The shipped example runs green: exit 0, one eligible record, audit closure."""
    out = tmp / "out-ex"
    proc = _run_cli(out)
    if proc.returncode != 0 or not (out / "index.json").exists():
        return False
    res = json.loads((out / "result.json").read_text(encoding="utf-8"))
    return res["ok"] and not res["empty"] \
        and [h["doc_id"] for h in res["hits"]] == ["rec-001"] \
        and res["documents_indexed"] == 5 \
        and any(x["rule"] == "search.doc_skipped" for x in res.get("findings", []))


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
    ("protocol_include", scen_protocol_include),
    ("exclusion_reason_probes", scen_exclusion_reason_probes),
    ("audit_counts_close", scen_audit_counts_close),
    ("criteria_not_relaxed", scen_criteria_not_relaxed),
    ("protocol_replay_identical", scen_protocol_replay_identical),
    ("included_hit_verbatim", scen_included_hit_verbatim),
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
    report = {"schema_version": "systematic-bench/v1", "scenarios": rows,
              "totals": {"passed": passed, "of": len(rows)}}
    (Path(__file__).resolve().parent / "report_systematic.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n{passed}/{len(rows)} scenarios pass")
    return 0 if passed == len(rows) else 1


if __name__ == "__main__":
    raise SystemExit(main())
