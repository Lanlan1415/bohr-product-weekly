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
import shutil
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import search  # noqa: E402
import incremental_tracker  # noqa: E402

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


def tracking_spec(**overrides):
    records_cr = [
        {"id": "cr-a", "version_group": "family-a", "version": "published",
         "doi": "10.1000/a", "title": "New assay for reproducibility", "authors": ["Jane Doe"],
         "published-online": {"date-parts": [[2026, 3, 5]]},
         "issued": {"date-parts": [[2026, 3, 5]]},
         "deposited": {"date-time": "2026-03-06T10:00:00Z"},
         "indexed": {"date-time": "2026-03-07T10:00:00Z"}},
        {"id": "cr-late", "version_group": "family-late", "doi": "10.1000/late",
         "title": "Old but newly indexed cohort", "published-online": {"date-parts": [[2026, 1, 15]]},
         "issued": {"date-parts": [[2026, 1, 15]]}, "indexed": {"date-time": "2026-03-10T08:00:00Z"}},
        {"id": "cr-boundary", "version_group": "family-boundary", "doi": "10.1000/boundary",
         "title": "Boundary conversion", "published-online": {"date-parts": [[2026, 3, 30]]},
         "issued": {"date-parts": [[2026, 3, 30]]},
         "indexed": {"date-time": "2026-04-01T00:30:00+02:00"}},
        {"id": "cr-outside", "version_group": "family-outside", "doi": "10.1000/outside",
         "title": "Outside after offset conversion", "issued": {"date-parts": [[2026, 3, 31]]},
         "indexed": {"date-time": "2026-03-31T23:30:00-02:00"}},
        {"id": "cr-v", "version_group": "family-v", "version": "published",
         "doi": "10.1000/vpub", "title": "Versioned assay", "status": "published",
         "issued": {"date-parts": [[2026, 3, 11]]}, "indexed": {"date-time": "2026-03-12T08:00:00Z"}},
        {"id": "cr-r", "doi": "10.1000/r", "version": "10.1000/r", "title": "Retracted baseline",
         "status": "retracted", "indexed": {"date-time": "2026-03-15T08:00:00Z"}},
        {"id": "cr-seen", "doi": "10.1000/seen", "version": "10.1000/seen", "title": "Already seen title",
         "status": "published", "indexed": {"date-time": "2026-03-18T08:00:00Z"}},
    ]
    records_epmc = [
        {"id": "ep-a", "version_group": "family-a", "version": "published",
         "doi": "10.1000/a", "title": "New assay for reproducibility", "authors": ["J. Doe"],
         "firstPublicationDate": "2026-03-05", "firstIndexDate": "2026-03-08T00:00:00Z"}
    ]
    previous = {"watermark": "2026-03-01T00:00:00Z", "works": [
        {"work_key": "family:family-v", "title": "Versioned assay", "version_records": [
            {"signature": "10.48550/arxiv.v", "version": "v1", "source": "arxiv", "record_id": "ax-v"}],
         "status": ["preprint"]},
        {"work_key": "doi:10.1000/r", "title": "Retracted baseline", "version_records": [
            {"signature": "10.1000/r", "version": "10.1000/r", "source": "crossref", "record_id": "old-r"}],
         "status": ["unchanged"]},
        {"work_key": "doi:10.1000/seen", "title": "Already seen title", "version_records": [
            {"signature": "10.1000/seen", "version": "10.1000/seen", "source": "crossref", "record_id": "old-seen"}],
         "status": ["published"]},
    ], "notifications": [], "read_works": [], "tracked_works": []}
    spec = {"mode": "latest", "required_sources": ["crossref", "europepmc"],
            "window": {"start": "2026-03-01T00:00:00Z", "end": "2026-04-01T00:00:00Z", "timezone": "UTC"},
            "tracking_date_fields": ["imported_at", "indexed"],
            "sources": {"crossref": {"status": "ok", "snapshot_ref": "fixture/crossref.json", "records": records_cr},
                        "europepmc": {"status": "ok", "snapshot_ref": "fixture/epmc.json", "records": records_epmc}},
            "previous_state": previous, "subscription": {"sources": ["crossref", "europepmc"]}}
    spec.update(overrides)
    return spec


def scen_tracker_closed_classification(tmp, name):
    """8 records -> 7 works: 2 new,1 late,1 out,1 version,1 status,1 unchanged."""
    result = incremental_tracker.run(tracking_spec())
    counts = result["count_reconciliation"]
    return result["status"] == "clean" and counts["records_valid"] == 8 and \
        counts["identity_clusters"] == 7 and counts["collapsed_observations"] == 1 and \
        counts["category_counts"] == {"new_works": 2, "late_arrivals": 1, "version_updates": 1,
            "status_updates": 1, "unchanged": 1, "out_of_window": 1, "review_required": 0} and \
        counts["closed"] and result["count_reconciliation"]["reminders_prepared"] == 5


def scen_tracker_cross_timezone_exact(tmp, name):
    """+02:00 midnight -> Mar31 22:30Z inside; -02:00 23:30 -> Apr1 01:30Z outside."""
    result = incremental_tracker.run(tracking_spec())
    inside = next(w for w in result["new_works"] if w["work_key"] == "family:family-boundary")
    event = next(e for e in result["date_interpretations"] if e["record_id"] == "cr-boundary")
    outside = next(w for w in result["out_of_window"] if w["work_key"] == "family:family-outside")
    outside_event = next(e for e in result["date_interpretations"] if e["record_id"] == "cr-outside")
    return event["event_utc"] == "2026-03-31T22:30:00Z" and event["window_relation"] == "inside" and \
        outside_event["event_utc"] == "2026-04-01T01:30:00Z" and outside_event["window_relation"] == "after" and \
        inside and outside


def scen_tracker_date_semantics_and_lag(tmp, name):
    """Late Jan publication indexed in March has 54 day lag; all date semantics stay distinct."""
    result = incremental_tracker.run(tracking_spec())
    late = result["late_arrivals"][0]
    dates = late["date_interpretations"][0]["dates"]
    assert late["publication_lag_days"] == 54
    return late["novelty_kind"] == "late_indexed_old_work" and \
        dates["online"]["utc"].startswith("2026-01-15") and dates["issued"]["utc"].startswith("2026-01-15") and \
        dates["deposited"] is None and dates["indexed"]["utc"] == "2026-03-10T08:00:00Z" and \
        not late.get("new_versions")


def scen_tracker_version_and_retraction_not_new(tmp, name):
    """New journal version and retraction stay out of new_works and retain old/new version evidence."""
    result = incremental_tracker.run(tracking_spec())
    version = result["version_updates"][0]
    status = result["status_updates"][0]
    return version["work_key"] == "family:family-v" and version["new_versions"] == ["published"] and \
        version["version_records"][0]["doi"] == "10.1000/vpub" and \
        status["work_key"] == "doi:10.1000/r" and status["update_kind"] == "status_change" and \
        all(w["work_key"] not in ("family:family-v", "doi:10.1000/r") for w in result["new_works"])


def scen_tracker_version_mirror_dedup(tmp, name):
    """Crossref/EuropePMC A records retain both lineages but one work and one notification."""
    result = incremental_tracker.run(tracking_spec())
    work = next(w for w in result["new_works"] if w["work_key"] == "family:family-a")
    ids = [n["notification_id"] for n in result["reminders"]]
    return len(work["source_records"]) == 2 and set(work["sources"]) == {"crossref", "europepmc"} and \
        len([n for n in result["reminders"] if n["work_key"] == "family:family-a"]) == 1 and len(ids) == len(set(ids))


def scen_tracker_idempotent_replay(tmp, name):
    """Same input is byte-equal; feeding next_state suppresses every prepared repeat notification."""
    first = incremental_tracker.run(tracking_spec())
    same = incremental_tracker.run(tracking_spec())
    repeated = incremental_tracker.run(tracking_spec(previous_state=first["next_state"]))
    return json.dumps(first, sort_keys=True, ensure_ascii=False) == json.dumps(same, sort_keys=True, ensure_ascii=False) and \
        not repeated["state_committed"] and not repeated["reminders"] and not repeated["new_works"] and \
        not repeated["late_arrivals"] and not repeated["version_updates"] and not repeated["status_updates"] and \
        len(repeated["unchanged"]) == 7


def scen_tracker_read_tracked_pause(tmp, name):
    """Already-read works suppress alerts; paused runs prepare no sends and preserve old watermark."""
    spec = tracking_spec()
    spec["previous_state"]["read_works"] = ["family:family-a"]
    read_result = incremental_tracker.run(spec)
    assert any(s["reason"] == "already read" and s["work_key"] == "family:family-a"
               for s in read_result["suppressed"])
    paused = incremental_tracker.run(tracking_spec(paused=True))
    return all(n["work_key"] != "family:family-a" for n in read_result["reminders"]) and \
        paused["next_watermark"] == "2026-03-01T00:00:00Z" and not paused["state_committed"] and \
        paused["count_reconciliation"]["reminders_prepared"] == 0


def scen_tracker_failure_holds_watermark(tmp, name):
    """An unavailable source leaves old state/watermark untouched and names missed-report risk."""
    spec = tracking_spec()
    spec["sources"]["semantic_scholar"] = {"status": "timeout", "error": "deadline", "records": []}
    spec["required_sources"] = ["crossref", "europepmc", "semantic_scholar"]
    result = incremental_tracker.run(spec)
    return result["status"] == "review" and not result["state_committed"] and \
        result["next_watermark"] == "2026-03-01T00:00:00Z" and \
        result["missed_reporting_risk"]["sources_incomplete"] == ["semantic_scholar"] and \
        sorted(result["next_state"]["works"], key=lambda w: w["work_key"]) == \
        sorted(spec["previous_state"]["works"], key=lambda w: w["work_key"])


def scen_tracker_undated_holds_watermark(tmp, name):
    """Online-only data is not silently substituted for the configured indexed observation."""
    spec = tracking_spec()
    spec["sources"]["crossref"]["records"].append({"id": "cr-undated", "version_group": "family-u",
        "title": "No discovery date", "published-online": {"date-parts": [[2026, 3, 20]]}})
    result = incremental_tracker.run(spec)
    return len(result["review_required"]) == 1 and not result["state_committed"] and \
        result["next_watermark"] == "2026-03-01T00:00:00Z" and result["status"] == "review"


def scen_tracker_imprecise_month_boundary(tmp, name):
    """A March-month indexed value overlaps a mid-March cutoff and requires review, not guessing."""
    spec = {"mode": "latest", "window": {"start": "2026-03-01", "end": "2026-03-15"},
            "tracking_date_fields": ["indexed"], "required_sources": ["crossref"],
            "sources": {"crossref": {"status": "ok", "records": [{"id": "month", "doi": "10.1/month",
                "title": "Month precision", "indexed": {"date-parts": [[2026, 3]]}}]}}}
    result = incremental_tracker.run(spec)
    return len(result["review_required"]) == 1 and "overlaps a window boundary" in \
        result["review_required"][0]["review_reasons"][0] and not result["state_committed"]


def scen_tracker_window_discontinuity(tmp, name):
    """A gap from previous watermark is surfaced and not auto-repaired."""
    spec = tracking_spec(window={"start": "2026-03-02T00:00:00Z", "end": "2026-04-01T00:00:00Z"})
    result = incremental_tracker.run(spec)
    return not result["state_committed"] and not result["current_window"]["continuous"] and \
        any(f["rule"] == "tracker.window_discontinuity" for f in result["findings"])


def scen_tracker_missing_window_refusal(tmp, name):
    """No system-clock fallback: missing window end is a structured refusal."""
    result = incremental_tracker.run({"mode": "latest", "previous_state": {}, "records": []})
    return result["status"] == "undetermined" and result["refusal"]["rule"] == "tracker.window_incomplete"


def scen_tracker_case_contract_cold_deterministic(tmp, name):
    """Cold import writes result+next_state; complete contract, exit 0 and deterministic output."""
    case = tracking_spec(case_id="latest-smoke-001", output_contract=["case_id", "new_works",
        "late_arrivals", "version_updates", "status_updates", "reminders", "next_watermark",
        "next_state", "owner_note", "unknown"], owner_note="kept")
    path = tmp / "case.json"
    path.write_text(json.dumps(case, ensure_ascii=False), encoding="utf-8")
    cold = tmp / "cold"
    shutil.copytree(Path(__file__).resolve().parent.parent, cold)
    blobs = []
    for label in ("a", "b"):
        out = tmp / label
        proc = subprocess.run([sys.executable, "-I", str(cold / "scripts" / "search_cli.py"),
                               "--case", str(path), "--out", str(out)], capture_output=True,
                              text=True, cwd=str(tmp), timeout=120)
        if proc.returncode != 0 or "Traceback" in proc.stderr or not (out / "next_state.json").exists():
            return False
        blobs.append((out / "result.json").read_bytes())
    result = json.loads(blobs[0])
    return blobs[0] == blobs[1] and result["case_id"] == "latest-smoke-001" and \
        result["owner_note"] == "kept" and result["unknown"] is None and \
        result["next_watermark"] == "2026-04-01T00:00:00Z" and \
        all(n["delivery_status"] == "prepared_not_sent" for n in result["reminders"])


SCENARIOS = [
    ("window_query", scen_window_query),
    ("tracker_closed_classification", scen_tracker_closed_classification),
    ("tracker_cross_timezone_exact", scen_tracker_cross_timezone_exact),
    ("tracker_date_semantics_and_lag", scen_tracker_date_semantics_and_lag),
    ("tracker_version_and_retraction_not_new", scen_tracker_version_and_retraction_not_new),
    ("tracker_version_mirror_dedup", scen_tracker_version_mirror_dedup),
    ("tracker_idempotent_replay", scen_tracker_idempotent_replay),
    ("tracker_read_tracked_pause", scen_tracker_read_tracked_pause),
    ("tracker_failure_holds_watermark", scen_tracker_failure_holds_watermark),
    ("tracker_undated_holds_watermark", scen_tracker_undated_holds_watermark),
    ("tracker_imprecise_month_boundary", scen_tracker_imprecise_month_boundary),
    ("tracker_window_discontinuity", scen_tracker_window_discontinuity),
    ("tracker_missing_window_refusal", scen_tracker_missing_window_refusal),
    ("tracker_case_contract_cold_deterministic", scen_tracker_case_contract_cold_deterministic),
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
