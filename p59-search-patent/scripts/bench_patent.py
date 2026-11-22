"""Benchmark for the search-patent skill (专利与技术文献检索).

Scenarios pin the patent-search behaviours on top of the shared file-search
engine: a normalised publication number locates exactly one patent record,
an unknown number is an honest empty (never a guessed record), the family
token groups simple-family members, the status and CPC filters separate
granted/expended records and technical classes, a duplicated export is
skipped and named, and the CLI ships a green example plus the exit-5
refusal contract.

    python bench_patent.py
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
    {"id": "pat-US10132852B2",
     "text": "id: pat-US10132852B2\n"
             "Title: graphene coating composition.\n"
             "number: US10132852B2\nfamily: F101\nstatus: granted\ncpc: C09D\n"
             "members: US20160264451A1, EP3061620A1"},
    {"id": "pat-EP3061620A1",
     "text": "id: pat-EP3061620A1\n"
             "Title: graphene coating composition (European application).\n"
             "number: EP3061620A1\nfamily: F101\nstatus: pending\ncpc: C09D"},
    {"id": "pat-US9988776B2",
     "text": "id: pat-US9988776B2\n"
             "Title: ceramic thermal barrier coating.\n"
             "number: US9988776B2\nfamily: F202\nstatus: expired\ncpc: C04B"},
    {"id": "pat-WO2017166469A1",
     "text": "id: pat-WO2017166469A1\n"
             "Title: graphene coating via spray pyrolysis (PCT application).\n"
             "number: WO2017166469A1\nfamily: F101\nstatus: pending\ncpc: C23C"},
    {"id": "pat-EP3061620A1",
     "text": "id: pat-EP3061620A1\n"
             "Title: graphene coating composition (European application).\n"
             "number: EP3061620A1\nfamily: F101\nstatus: pending\ncpc: C09D"},
]

EXAMPLE_QUERY = {"all": ["F101"]}

EXAMPLES = Path(__file__).resolve().parent.parent / "examples"
CLI = Path(__file__).resolve().parent / "search_cli.py"


def _run_cli(out, query_file=None):
    args = [sys.executable, str(CLI), "--corpus", str(EXAMPLES / "corpus.json"),
            "--out", str(out)]
    args += ["--query-file", str(query_file or (EXAMPLES / "query.json"))]
    return subprocess.run(args, capture_output=True, text=True, timeout=120)


def scen_number_lookup_exact(tmp, name):
    """A normalised publication number locates exactly one record with a verbatim number line."""
    _, res = search.search({"corpus": CORPUS, "query": {"all": ["US10132852B2"]}})
    hit = res["hits"][0]
    docs = search.build_index(CORPUS)["index"]["documents"]
    paras = docs["pat-US10132852B2"]["paragraphs"]
    number_paras = [i for i, p in enumerate(paras) if p == "number: US10132852B2"]
    hit_paras = {p["locator"]["paragraph"] for p in hit["passages"]}
    ok_slices = all(paras[p["locator"]["paragraph"]][p["locator"]["start"]:p["locator"]["end"]]
                    == p["locator"]["quote"] for p in hit["passages"])
    return res["ok"] and [h["doc_id"] for h in res["hits"]] == ["pat-US10132852B2"] \
        and hit["passages"][0]["term"] == "US10132852B2" \
        and number_paras[0] in hit_paras and ok_slices


def scen_unknown_number_honest(tmp, name):
    """A number not in the snapshot is an honest empty — never a guessed record."""
    _, res = search.search({"corpus": CORPUS, "query": {"all": ["US11111111B1"]}})
    return res["ok"] and res["empty"] is True and res["hits"] == [] \
        and res["documents_indexed"] == 4 and "never padded" in res["note"]


def scen_family_grouping(tmp, name):
    """The family token groups the simple-family members and excludes other families."""
    _, res = search.search({"corpus": CORPUS, "query": {"all": ["F101"]}})
    ids = sorted(h["doc_id"] for h in res["hits"])
    return res["ok"] and ids == ["pat-EP3061620A1", "pat-US10132852B2", "pat-WO2017166469A1"] \
        and "pat-US9988776B2" not in ids


def scen_status_and_cpc_filters(tmp, name):
    """Status tokens and CPC class tokens filter exactly as declared."""
    _, granted = search.search({"corpus": CORPUS, "query": {"all": ["status: granted"]}})
    _, expired = search.search({"corpus": CORPUS, "query": {"all": ["status: expired"]}})
    _, coatings = search.search({"corpus": CORPUS, "query": {"all": ["C09D"]}})
    return [h["doc_id"] for h in granted["hits"]] == ["pat-US10132852B2"] \
        and [h["doc_id"] for h in expired["hits"]] == ["pat-US9988776B2"] \
        and sorted(h["doc_id"] for h in coatings["hits"]) \
        == ["pat-EP3061620A1", "pat-US10132852B2"]


def scen_duplicate_export_named(tmp, name):
    """A duplicated export of the same filing is skipped and named, not double-counted."""
    _, res = search.search({"corpus": CORPUS, "query": {"all": ["EP3061620A1"]}})
    f = next((x for x in res.get("findings", []) if x["rule"] == "search.doc_skipped"), None)
    return res["ok"] and f is not None and f["count"] == 1 \
        and "duplicate doc id 'pat-EP3061620A1'" in f["entries"][0]["reason"] \
        and res["documents_indexed"] == 4


def scen_record_locator_verbatim(tmp, name):
    """Every passage quote on a patent record equals the indexed paragraph slice."""
    docs = search.build_index(CORPUS)["index"]["documents"]
    _, res = search.search({"corpus": CORPUS, "query": {"all": ["F101"]}})
    ok = len(res["hits"]) == 3
    for hit in res["hits"]:
        paras = docs[hit["doc_id"]]["paragraphs"]
        for p in hit["passages"]:
            loc = p["locator"]
            ok = ok and paras[loc["paragraph"]][loc["start"]:loc["end"]] == loc["quote"]
    return ok


def scen_cli_examples_run(tmp, name):
    """The shipped example runs green: exit 0, the three F101 family members."""
    out = tmp / "out-ex"
    proc = _run_cli(out)
    if proc.returncode != 0 or not (out / "index.json").exists():
        return False
    res = json.loads((out / "result.json").read_text(encoding="utf-8"))
    idx = json.loads((out / "index.json").read_text(encoding="utf-8"))
    return res["ok"] and not res["empty"] \
        and sorted(h["doc_id"] for h in res["hits"]) \
        == ["pat-EP3061620A1", "pat-US10132852B2", "pat-WO2017166469A1"] \
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
    ("number_lookup_exact", scen_number_lookup_exact),
    ("unknown_number_honest", scen_unknown_number_honest),
    ("family_grouping", scen_family_grouping),
    ("status_and_cpc_filters", scen_status_and_cpc_filters),
    ("duplicate_export_named", scen_duplicate_export_named),
    ("record_locator_verbatim", scen_record_locator_verbatim),
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
    report = {"schema_version": "patent-bench/v1", "scenarios": rows,
              "totals": {"passed": passed, "of": len(rows)}}
    (Path(__file__).resolve().parent / "report_patent.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n{passed}/{len(rows)} scenarios pass")
    return 0 if passed == len(rows) else 1


if __name__ == "__main__":
    raise SystemExit(main())
