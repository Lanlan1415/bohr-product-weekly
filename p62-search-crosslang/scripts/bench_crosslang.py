"""Benchmark for the search-crosslang skill (跨语言文献检索).

Scenarios pin the cross-language behaviours on top of the shared file-search
engine: a bilingual any-list raises recall across languages (each record hits
on its own language's term), the source-language term alone does not reach
the English body (why the term table is mandatory), a loanword term crosses
the language boundary, the DOI token links an original and its translation
view for version dedup counting, a CJK hit carries a verbatim locator, and
the CLI ships a green example plus the exit-5 refusal contract.

    python bench_crosslang.py
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
    {"id": "zh-focal-01",
     "text": "id: zh-focal-01\nlang: zh\n"
             "细胞焦亡由炎性小体驱动，gasdermin孔隙形成是关键步骤。\n"
             "doi: doi-10-1093-zhmr-026-0345"},
    {"id": "en-focal-01",
     "text": "id: en-focal-01\nlang: en\n"
             "Pyroptosis is driven by inflammasome activation and gasdermin pore formation.\n"
             "doi: doi-10-1038-s41590-025-04567-8"},
    {"id": "en-trans-01",
     "text": "id: en-trans-01\nlang: en\n"
             "trans-of: doi-10-1093-zhmr-026-0345\n"
             "English view of the zh original: pyroptosis and gasdermin pores."},
    {"id": "zh-other-01",
     "text": "id: zh-other-01\nlang: zh\n"
             "铁死亡依赖脂质过氧化，与细胞焦亡的通路不同。\n"
             "doi: doi-10-1093-zhmr-025-1122"},
]

BILINGUAL = {"all": [], "any": ["细胞焦亡", "pyroptosis"]}

EXAMPLE_QUERY = BILINGUAL

EXAMPLES = Path(__file__).resolve().parent.parent / "examples"
CLI = Path(__file__).resolve().parent / "search_cli.py"


def _run_cli(out, query_file=None):
    args = [sys.executable, str(CLI), "--corpus", str(EXAMPLES / "corpus.json"),
            "--out", str(out)]
    args += ["--query-file", str(query_file or (EXAMPLES / "query.json"))]
    return subprocess.run(args, capture_output=True, text=True, timeout=120)


def scen_bilingual_any_recall(tmp, name):
    """The bilingual any-list recalls records in both languages on their own terms."""
    _, res = search.search({"corpus": CORPUS, "query": BILINGUAL})
    ids = sorted(h["doc_id"] for h in res["hits"])
    return res["ok"] and len(ids) == 4 \
        and {"zh-focal-01", "en-focal-01"} <= set(ids)


def scen_source_term_language_bound(tmp, name):
    """The zh term alone does not reach the English body — the term table is mandatory."""
    _, res = search.search({"corpus": CORPUS, "query": {"all": ["细胞焦亡"]}})
    ids = sorted(h["doc_id"] for h in res["hits"])
    return res["ok"] and ids == ["zh-focal-01", "zh-other-01"] \
        and "en-focal-01" not in ids


def scen_loanword_crosses_boundary(tmp, name):
    """A loanword term crosses the boundary and reaches the zh original too."""
    _, res = search.search({"corpus": CORPUS, "query": {"all": ["gasdermin"]}})
    ids = sorted(h["doc_id"] for h in res["hits"])
    return res["ok"] and ids == ["en-focal-01", "en-trans-01", "zh-focal-01"] \
        and res["hits"][0]["doc_id"] == "zh-focal-01"


def scen_version_merge_link(tmp, name):
    """The DOI token links the original and its translation view: 2 views, 1 work."""
    _, res = search.search({"corpus": CORPUS,
                            "query": {"all": ["doi-10-1093-zhmr-026-0345"]}})
    ids = sorted(h["doc_id"] for h in res["hits"])
    return res["ok"] and ids == ["en-trans-01", "zh-focal-01"]


def scen_cjk_hit_verbatim(tmp, name):
    """A CJK probe hit carries a locator whose quote equals the paragraph slice."""
    _, res = search.search({"corpus": CORPUS, "query": {"all": ["炎性小体"]}})
    docs = search.build_index(CORPUS)["index"]["documents"]
    hit = res["hits"][0]
    loc = hit["passages"][0]["locator"]
    paras = docs[hit["doc_id"]]["paragraphs"]
    return res["ok"] and [h["doc_id"] for h in res["hits"]] == ["zh-focal-01"] \
        and paras[loc["paragraph"]][loc["start"]:loc["end"]] == loc["quote"] \
        and loc["quote"] == "炎性小体"


def scen_bilingual_replay(tmp, name):
    """The bilingual probe reruns byte-identical — per-language recall is recomputable."""
    r1 = search.search({"corpus": CORPUS, "query": BILINGUAL})[1]
    r2 = search.search({"corpus": CORPUS, "query": BILINGUAL})[1]
    return json.dumps(r1, ensure_ascii=False, sort_keys=True) \
        == json.dumps(r2, ensure_ascii=False, sort_keys=True) \
        and r1["query"] == {"all": [], "any": ["细胞焦亡", "pyroptosis"]}


def scen_cli_examples_run(tmp, name):
    """The shipped example runs green: exit 0, all four records recalled bilingually."""
    out = tmp / "out-ex"
    proc = _run_cli(out)
    if proc.returncode != 0 or not (out / "index.json").exists():
        return False
    res = json.loads((out / "result.json").read_text(encoding="utf-8"))
    idx = json.loads((out / "index.json").read_text(encoding="utf-8"))
    return res["ok"] and not res["empty"] and len(res["hits"]) == 4 \
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
    ("bilingual_any_recall", scen_bilingual_any_recall),
    ("source_term_language_bound", scen_source_term_language_bound),
    ("loanword_crosses_boundary", scen_loanword_crosses_boundary),
    ("version_merge_link", scen_version_merge_link),
    ("cjk_hit_verbatim", scen_cjk_hit_verbatim),
    ("bilingual_replay", scen_bilingual_replay),
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
    report = {"schema_version": "crosslang-bench/v1", "scenarios": rows,
              "totals": {"passed": passed, "of": len(rows)}}
    (Path(__file__).resolve().parent / "report_crosslang.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n{passed}/{len(rows)} scenarios pass")
    return 0 if passed == len(rows) else 1


if __name__ == "__main__":
    raise SystemExit(main())
