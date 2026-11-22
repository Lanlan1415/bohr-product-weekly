"""Benchmark for the search-latest skill (最新文献发现与追踪).

Scenarios pin the incremental-tracking behaviours on top of the shared
file-search engine: a date-token window query returns only in-window records,
a shared DOI token is the merge key for preprint/published versions, retracted
records stay retrievable for explicit subtraction, a CJK record hits with a
verbatim locator, the window probe reruns byte-identical, and the CLI ships a
green example plus the exit-5 refusal contract.

    python bench_latest.py
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
    {"id": "snap-a1",
     "text": "[2026-03-02] Cryo-EM structures of the spike at 2.1 A resolution.\n"
             "doi: doi-10-1038-s41586-026-08101-3\nstatus: published"},
    {"id": "snap-a1",
     "text": "[2026-03-02] Cryo-EM structures of the spike at 2.1 A resolution "
             "(feed mirror).\ndoi: doi-10-1038-s41586-026-08101-3\nstatus: preprint"},
    {"id": "snap-b1",
     "text": "[2026-02-14] Baseline cohort description from the previous window.\n"
             "doi: doi-10-1234-baseline-2026\nstatus: published"},
    {"id": "snap-c1",
     "text": "[2026-03-18] Retraction notice: the 2025 nanopore baseline paper was "
             "retracted.\ndoi: doi-10-1234-nanopore-2025\nstatus: retracted"},
    {"id": "snap-d1",
     "text": "[2026-03-21] 新型低温电镜方法在病毒刺突解析中的应用。\n"
             "doi: doi-10-12345-zh-em-2026\nstatus: published"},
]

WINDOW = {"all": ["2026-03"]}
MERGE_KEY = "doi-10-1038-s41586-026-08101-3"

EXAMPLE_QUERY = {"all": ["2026-03"]}

EXAMPLES = Path(__file__).resolve().parent.parent / "examples"
CLI = Path(__file__).resolve().parent / "search_cli.py"


def _run_cli(out, query_file=None):
    args = [sys.executable, str(CLI), "--corpus", str(EXAMPLES / "corpus.json"),
            "--out", str(out)]
    args += ["--query-file", str(query_file or (EXAMPLES / "query.json"))]
    return subprocess.run(args, capture_output=True, text=True, timeout=120)


def scen_window_query(tmp, name):
    """The window probe returns exactly the in-window records; the old snapshot stays out."""
    _, res = search.search({"corpus": CORPUS, "query": WINDOW})
    ids = sorted(h["doc_id"] for h in res["hits"])
    return res["ok"] and not res["empty"] and ids == ["snap-a1", "snap-c1", "snap-d1"] \
        and "snap-b1" not in ids and res["documents_indexed"] == 4


def scen_version_merge_key(tmp, name):
    """The DOI token is the merge key: the duplicated mirror is skipped, one record hits."""
    _, res = search.search({"corpus": CORPUS, "query": {"all": [MERGE_KEY]}})
    f = next((x for x in res.get("findings", []) if x["rule"] == "search.doc_skipped"), None)
    return res["ok"] and [h["doc_id"] for h in res["hits"]] == ["snap-a1"] \
        and f is not None and f["count"] == 1 and res["documents_indexed"] == 4


def scen_retracted_flagged(tmp, name):
    """The retraction probe isolates the retracted record so a reminder can label it."""
    _, res = search.search({"corpus": CORPUS, "query": {"all": ["retracted"]}})
    hit = res["hits"][0]
    terms = {p["term"] for p in hit["passages"]}
    return res["ok"] and [h["doc_id"] for h in res["hits"]] == ["snap-c1"] \
        and "retracted" in terms


def scen_cjk_record_verbatim(tmp, name):
    """A CJK in-window record hits and its locator quote is a verbatim paragraph slice."""
    _, res = search.search({"corpus": CORPUS, "query": {"all": ["低温电镜"]}})
    docs = search.build_index(CORPUS)["index"]["documents"]
    hit = res["hits"][0]
    loc = hit["passages"][0]["locator"]
    paras = docs[hit["doc_id"]]["paragraphs"]
    return res["ok"] and hit["doc_id"] == "snap-d1" \
        and paras[loc["paragraph"]][loc["start"]:loc["end"]] == loc["quote"] \
        and loc["quote"] == "低温电镜"


def scen_window_replay_identical(tmp, name):
    """The window probe reruns byte-identical — the increment is recomputable."""
    r1 = search.search({"corpus": CORPUS, "query": WINDOW})[1]
    r2 = search.search({"corpus": CORPUS, "query": WINDOW})[1]
    return json.dumps(r1, ensure_ascii=False, sort_keys=True) \
        == json.dumps(r2, ensure_ascii=False, sort_keys=True) \
        and r1["query"] == {"all": ["2026-03"], "any": []}


def scen_empty_window_honest(tmp, name):
    """A window with no new records is an honest empty, not a padded reminder."""
    _, res = search.search({"corpus": CORPUS, "query": {"all": ["2026-04"]}})
    return res["ok"] and res["empty"] is True and res["hits"] == [] \
        and res["documents_indexed"] == 4 and "never padded" in res["note"]


def scen_cli_examples_run(tmp, name):
    """The shipped example runs green: exit 0, index.json + result.json, 3 in-window hits."""
    out = tmp / "out-ex"
    proc = _run_cli(out)
    if proc.returncode != 0 or not (out / "index.json").exists():
        return False
    res = json.loads((out / "result.json").read_text(encoding="utf-8"))
    idx = json.loads((out / "index.json").read_text(encoding="utf-8"))
    return res["ok"] and not res["empty"] \
        and sorted(h["doc_id"] for h in res["hits"]) == ["snap-a1", "snap-c1", "snap-d1"] \
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
    ("window_query", scen_window_query),
    ("version_merge_key", scen_version_merge_key),
    ("retracted_flagged", scen_retracted_flagged),
    ("cjk_record_verbatim", scen_cjk_record_verbatim),
    ("window_replay_identical", scen_window_replay_identical),
    ("empty_window_honest", scen_empty_window_honest),
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
    report = {"schema_version": "latest-bench/v1", "scenarios": rows,
              "totals": {"passed": passed, "of": len(rows)}}
    (Path(__file__).resolve().parent / "report_latest.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n{passed}/{len(rows)} scenarios pass")
    return 0 if passed == len(rows) else 1


if __name__ == "__main__":
    raise SystemExit(main())
