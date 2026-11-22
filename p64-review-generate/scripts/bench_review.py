"""Benchmark for the review-generate skill (文献综述生成).

Scenarios pin the review behaviours on top of the shared file-search engine:
theme tokens partition the evidence base without overlap, every potential
support for a claim carries a quotable passage (the claim-to-evidence backlink
is checkable), conflicting findings stay retrievable on both sides, a screened-
out record stays out of the evidence probes while remaining auditable in the
index, evidence locators are verbatim slices, and the CLI ships a green example
plus the exit-5 refusal contract.

    python bench_review.py
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
    {"id": "ev-001",
     "text": "id: ev-001\ntheme: efficacy\n"
             "Trial A reported serum biomarker Y fell by 30 percent under drug X.\n"
             "finding: lower"},
    {"id": "ev-002",
     "text": "id: ev-002\ntheme: efficacy\n"
             "Trial B found biomarker Y unchanged after 12 weeks of drug X.\n"
             "finding: unchanged"},
    {"id": "ev-003",
     "text": "id: ev-003\ntheme: mechanism\n"
             "Drug X inhibits the kinase that upregulates biomarker Y synthesis.\n"
             "finding: lower"},
    {"id": "ev-004",
     "text": "id: ev-004\ntheme: safety\n"
             "No serious adverse events attributed to drug X across 240 participants.\n"
             "finding: safe"},
    {"id": "excluded-01",
     "text": "id: excluded-01\ntheme: protocol-only\n"
             "Conference abstract with no extractable result for drug X."},
]

CLAIM_SUPPORT = {"all": ["biomarker Y"]}

EXAMPLE_QUERY = {"all": ["theme: efficacy"]}

EXAMPLES = Path(__file__).resolve().parent.parent / "examples"
CLI = Path(__file__).resolve().parent / "search_cli.py"


def _run_cli(out, query_file=None):
    args = [sys.executable, str(CLI), "--corpus", str(EXAMPLES / "corpus.json"),
            "--out", str(out)]
    args += ["--query-file", str(query_file or (EXAMPLES / "query.json"))]
    return subprocess.run(args, capture_output=True, text=True, timeout=120)


def scen_theme_partition(tmp, name):
    """Theme probes partition the evidence base; each record carries exactly one theme."""
    _, eff = search.search({"corpus": CORPUS, "query": {"all": ["theme: efficacy"]}})
    _, mech = search.search({"corpus": CORPUS, "query": {"all": ["theme: mechanism"]}})
    _, safety = search.search({"corpus": CORPUS, "query": {"all": ["theme: safety"]}})
    return [h["doc_id"] for h in eff["hits"]] == ["ev-001", "ev-002"] \
        and [h["doc_id"] for h in mech["hits"]] == ["ev-003"] \
        and [h["doc_id"] for h in safety["hits"]] == ["ev-004"]


def scen_claim_support_backlink(tmp, name):
    """Every potential support for the claim carries a quotable evidence passage."""
    _, res = search.search({"corpus": CORPUS, "query": CLAIM_SUPPORT})
    ids = [h["doc_id"] for h in res["hits"]]
    return res["ok"] and ids == ["ev-001", "ev-002", "ev-003"] \
        and all(h["passages"] for h in res["hits"]) \
        and all(p["locator"]["quote"] == "biomarker Y"
                for h in res["hits"] for p in h["passages"])


def scen_conflict_preserved(tmp, name):
    """Both sides of the conflicting evidence stay retrievable — the review shows both."""
    _, lower = search.search({"corpus": CORPUS, "query": {"all": ["finding: lower"]}})
    _, unchanged = search.search({"corpus": CORPUS,
                                  "query": {"all": ["finding: unchanged"]}})
    return sorted(h["doc_id"] for h in lower["hits"]) == ["ev-001", "ev-003"] \
        and [h["doc_id"] for h in unchanged["hits"]] == ["ev-002"]


def scen_screened_out_audit(tmp, name):
    """The screened-out record stays out of evidence probes yet auditable in the index."""
    _, res = search.search({"corpus": CORPUS, "query": CLAIM_SUPPORT})
    ids = [h["doc_id"] for h in res["hits"]]
    return res["ok"] and "excluded-01" not in ids and res["documents_indexed"] == 5


def scen_evidence_locator_verbatim(tmp, name):
    """Every evidence passage quote equals the indexed paragraph slice."""
    docs = search.build_index(CORPUS)["index"]["documents"]
    _, res = search.search({"corpus": CORPUS, "query": CLAIM_SUPPORT})
    ok = len(res["hits"]) == 3
    for hit in res["hits"]:
        paras = docs[hit["doc_id"]]["paragraphs"]
        for p in hit["passages"]:
            loc = p["locator"]
            ok = ok and paras[loc["paragraph"]][loc["start"]:loc["end"]] == loc["quote"]
    return ok


def scen_battery_replay_identical(tmp, name):
    """The review battery (themes, claim support, conflict sides) reruns byte-identical."""
    battery = [{"all": ["theme: efficacy"]}, {"all": ["theme: mechanism"]},
               {"all": ["theme: safety"]}, CLAIM_SUPPORT,
               {"all": ["finding: lower"]}, {"all": ["finding: unchanged"]}]
    runs = []
    for _ in range(2):
        runs.append(json.dumps([search.search({"corpus": CORPUS, "query": q})[1]
                                for q in battery], ensure_ascii=False, sort_keys=True))
    return runs[0] == runs[1]


def scen_cli_examples_run(tmp, name):
    """The shipped example runs green: exit 0, the two efficacy records."""
    out = tmp / "out-ex"
    proc = _run_cli(out)
    if proc.returncode != 0 or not (out / "index.json").exists():
        return False
    res = json.loads((out / "result.json").read_text(encoding="utf-8"))
    idx = json.loads((out / "index.json").read_text(encoding="utf-8"))
    return res["ok"] and not res["empty"] \
        and [h["doc_id"] for h in res["hits"]] == ["ev-001", "ev-002"] \
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
    ("theme_partition", scen_theme_partition),
    ("claim_support_backlink", scen_claim_support_backlink),
    ("conflict_preserved", scen_conflict_preserved),
    ("screened_out_audit", scen_screened_out_audit),
    ("evidence_locator_verbatim", scen_evidence_locator_verbatim),
    ("battery_replay_identical", scen_battery_replay_identical),
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
    report = {"schema_version": "review-bench/v1", "scenarios": rows,
              "totals": {"passed": passed, "of": len(rows)}}
    (Path(__file__).resolve().parent / "report_review.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n{passed}/{len(rows)} scenarios pass")
    return 0 if passed == len(rows) else 1


if __name__ == "__main__":
    raise SystemExit(main())
