"""Benchmark for the search-quality skill (文献研究质量评价).

Scenarios pin the appraisal behaviours on top of the shared file-search
engine: each rubric domain is a token probe whose hit carries the verbatim
evidence sentence, a domain the paper does not report stays unmatched (the
engine cannot match what the text does not claim), the design tag separates
RCTs from observational designs, the composite risk-low row needs every
rubric token at once, the rubric battery reruns byte-identical, and the CLI
ships a green example plus the exit-5 refusal contract.

    python bench_quality.py
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
    {"id": "study-rct-01",
     "text": "id: study-rct-01\ndesign: rct\n"
             "Trial registration: pre-registered NCT04567890.\n"
             "Methods: participants were randomised 1:1 with allocation concealed in "
             "sequentially numbered opaque envelopes; outcome assessors were blinded.\n"
             "Analysis: intention-to-treat, n=214."},
    {"id": "study-rct-02",
     "text": "id: study-rct-02\ndesign: rct\n"
             "Trial registration: pre-registered NCT07894561.\n"
             "Methods: participants were randomised 1:1; blinding of outcome assessors "
             "was not reported.\n"
             "Analysis: per-protocol, n=88."},
    {"id": "study-obs-01",
     "text": "id: study-obs-01\ndesign: cohort\n"
             "Design: retrospective cohort, not randomised.\n"
             "Methods: allocation concealment is not applicable; no blinding.\n"
             "Analysis: propensity-score adjusted, n=1204."},
]

RISK_LOW_ROW = {"all": ["pre-registered", "allocation concealed", "blinded"]}

EXAMPLE_QUERY = RISK_LOW_ROW

EXAMPLES = Path(__file__).resolve().parent.parent / "examples"
CLI = Path(__file__).resolve().parent / "search_cli.py"


def _run_cli(out, query_file=None):
    args = [sys.executable, str(CLI), "--corpus", str(EXAMPLES / "corpus.json"),
            "--out", str(out)]
    args += ["--query-file", str(query_file or (EXAMPLES / "query.json"))]
    return subprocess.run(args, capture_output=True, text=True, timeout=120)


def scen_rubric_domain_hit(tmp, name):
    """The allocation-concealment probe hits the one study with a quotable evidence sentence."""
    _, res = search.search({"corpus": CORPUS,
                            "query": {"all": ["allocation concealed"]}})
    quotes = {p["locator"]["quote"] for p in res["hits"][0]["passages"]}
    return res["ok"] and [h["doc_id"] for h in res["hits"]] == ["study-rct-01"] \
        and "allocation concealed" in quotes


def scen_not_reported_stays_unmatched(tmp, name):
    """A domain the paper does not report stays unmatched — no padded judgement."""
    _, res = search.search({"corpus": CORPUS, "query": {"all": ["blinded"]}})
    ids = [h["doc_id"] for h in res["hits"]]
    return res["ok"] and ids == ["study-rct-01"] and "study-rct-02" not in ids \
        and "study-obs-01" not in ids


def scen_design_tag_query(tmp, name):
    """The design tag separates the RCTs from the observational cohort."""
    _, rcts = search.search({"corpus": CORPUS, "query": {"all": ["design: rct"]}})
    _, composite = search.search({"corpus": CORPUS,
                                  "query": {"all": ["design: rct", "allocation concealed"]}})
    return sorted(h["doc_id"] for h in rcts["hits"]) == ["study-rct-01", "study-rct-02"] \
        and [h["doc_id"] for h in composite["hits"]] == ["study-rct-01"]


def scen_risk_low_threshold(tmp, name):
    """The risk-low row needs every rubric token at once; a study missing two stays out."""
    _, res = search.search({"corpus": CORPUS, "query": RISK_LOW_ROW})
    hit = res["hits"][0]
    return res["ok"] and [h["doc_id"] for h in res["hits"]] == ["study-rct-01"] \
        and hit["matched_terms"] == ["allocation concealed", "blinded", "pre-registered"]


def scen_rubric_battery_replay(tmp, name):
    """The rubric battery reruns byte-identical — the appraisal sheet is reproducible."""
    battery = [{"all": ["allocation concealed"]}, {"all": ["blinded"]},
               {"all": ["design: rct"]}, RISK_LOW_ROW, {"all": ["n=214"]}]
    runs = []
    for _ in range(2):
        runs.append(json.dumps([search.search({"corpus": CORPUS, "query": q})[1]
                                for q in battery], ensure_ascii=False, sort_keys=True))
    return runs[0] == runs[1]


def scen_evidence_locator_verbatim(tmp, name):
    """Every rubric-hit passage quote equals the indexed paragraph slice."""
    docs = search.build_index(CORPUS)["index"]["documents"]
    _, res = search.search({"corpus": CORPUS, "query": {"all": ["blinded"]}})
    paras = docs["study-rct-01"]["paragraphs"]
    ok = True
    for p in res["hits"][0]["passages"]:
        loc = p["locator"]
        ok = ok and paras[loc["paragraph"]][loc["start"]:loc["end"]] == loc["quote"]
    return ok


def scen_cli_examples_run(tmp, name):
    """The shipped example runs green: exit 0, exactly the risk-low candidate."""
    out = tmp / "out-ex"
    proc = _run_cli(out)
    if proc.returncode != 0 or not (out / "index.json").exists():
        return False
    res = json.loads((out / "result.json").read_text(encoding="utf-8"))
    idx = json.loads((out / "index.json").read_text(encoding="utf-8"))
    return res["ok"] and not res["empty"] \
        and [h["doc_id"] for h in res["hits"]] == ["study-rct-01"] \
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
    ("rubric_domain_hit", scen_rubric_domain_hit),
    ("not_reported_stays_unmatched", scen_not_reported_stays_unmatched),
    ("design_tag_query", scen_design_tag_query),
    ("risk_low_threshold", scen_risk_low_threshold),
    ("rubric_battery_replay", scen_rubric_battery_replay),
    ("evidence_locator_verbatim", scen_evidence_locator_verbatim),
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
    report = {"schema_version": "quality-bench/v1", "scenarios": rows,
              "totals": {"passed": passed, "of": len(rows)}}
    (Path(__file__).resolve().parent / "report_quality.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n{passed}/{len(rows)} scenarios pass")
    return 0 if passed == len(rows) else 1


if __name__ == "__main__":
    raise SystemExit(main())
