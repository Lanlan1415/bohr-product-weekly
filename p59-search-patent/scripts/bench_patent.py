"""Regression bench for search-patent.  Every patent finding has a trigger and FP guard.

Run with: python -I -X utf8 scripts/bench_patent.py
All fixtures are synthetic; no fixture is an official case answer or legal opinion.
"""

from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parent))
import search  # noqa: E402
import search_cli  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
EXAMPLES = ROOT / "examples"
CLI = Path(__file__).resolve().parent / "search_cli.py"
CORPUS = json.loads((EXAMPLES / "corpus.json").read_text(encoding="utf-8"))["documents"]
SCENARIOS = []


def scenario(name):
    def decorate(fn):
        SCENARIOS.append((name, fn))
        return fn
    return decorate


def outcome(condition, detail=""):
    return bool(condition), detail


def run(corpus, query):
    _, result = search.search({"corpus": corpus, "query": query})
    return result


def rules(result):
    return {finding.get("rule") for finding in result.get("findings", [])}


def has_rule(result, rule):
    return rule in rules(result)


def ids(result):
    return [hit["doc_id"] for hit in result.get("hits", [])]


def patent(doc_id="p1", **overrides):
    fields = {
        "Title": "Synthetic coating fixture",
        "document_type": "patent", "number": "US10000000B2",
        "application_number": "US16" + str(sum((i + 1) * ord(c) for i, c in enumerate(doc_id))
                                               % 1000000).zfill(6),
        "grant_number": "US10000000B2",
        "family": "F1", "inpadoc_family": "I1", "priority_date": "2020-01-01",
        "filing_date": "2021-01-01", "publication_date": "2022-01-01",
        "status": "pending", "status_date": "2026-01-15", "cpc": "C09D5/08",
        "applicant": "Example Applicant", "claim_version": "publication-v1",
        "claims_source": "synthetic source-located claims",
        "source": "synthetic registry snapshot", "source_type": "provided_snapshot",
        "source_version": "bench-v2", "query_date": "2026-01-15",
        "license": "synthetic reusable fixture", "access": "green",
    }
    fields.update(overrides)
    lines = [f"id: {doc_id}"]
    for key, value in fields.items():
        if value is None:
            continue
        if isinstance(value, (list, tuple)):
            value = ", ".join(str(v) for v in value)
        lines.append(f"{key}: {value}")
    return {"id": doc_id, "text": "\n".join(lines)}


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")
    return path


def run_cli(out, query_file=None, corpus=None, case=None, index=None, query=None):
    args = [sys.executable, "-I", "-X", "utf8", str(CLI), "--out", str(out)]
    if index:
        args += ["--index", str(index)]
    else:
        args += ["--corpus", str(corpus or (EXAMPLES / "corpus.json"))]
    if query_file:
        args += ["--query-file", str(query_file)]
    elif query is not None:
        args += ["--query", query]
    else:
        args += ["--query-file", str(EXAMPLES / "query.json")]
    if case:
        args += ["--case", str(case)]
    return subprocess.run(args, capture_output=True, text=True, timeout=120)


@scenario("example_cli_contract")
def _(tmp):
    out = tmp / "example"
    proc = run_cli(out, case=EXAMPLES / "case.json")
    if proc.returncode != 0:
        return outcome(False, proc.stdout + proc.stderr)
    result = json.loads((out / "result.json").read_text(encoding="utf-8"))
    expected = {"case_id", "检索结果", "证据记录", "状态说明", "delivery_note"}
    return outcome(result["case_id"] == "example-family-simple-v2"
                   and result["status"] == "clean" and ids(result) ==
                   ["pat-US10132852B2", "pat-EP3061620A1"]
                   and expected <= set(result) and result["delivery_note"].startswith("Synthetic")
                   and len(result["index_sha256"]) == 64 and result.get("change_records"),
                   "example must preserve case_id, contract fields, and actual change records")


@scenario("inpadoc_family_expansion")
def _(tmp):
    query = dict(json.loads((EXAMPLES / "query.json").read_text(encoding="utf-8")))
    query["family_scope"] = "inpadoc"
    result = run(CORPUS, query)
    return outcome(set(ids(result)) == {"pat-US10132852B2", "pat-EP3061620A1",
                                       "pat-WO2017166469A1"}
                   and len(result["families"]) == 1
                   and result["families"][0]["family_id"] == "I901"
                   and "does not establish equal claim scope" in result["families"][0]["claim_scope"],
                   "INPADOC expansion must include WO but retain the non-exhaustive/claim caveat")


@scenario("number_lookup_normalised_exact")
def _(tmp):
    result = run(CORPUS, "US 10,132,852 B2")
    application = run(CORPUS, {"application_number": "US15/123456"})
    return outcome(ids(result) == ["pat-US10132852B2"]
                   and result["query"]["number"] == "US10132852B2"
                   and ids(application) == ["pat-US10132852B2"],
                   "formatted publication/application numbers must normalise and match exactly")


@scenario("unknown_number_honest")
def _(tmp):
    result = run(CORPUS, "US11111111B1")
    return outcome(result["status"] == "clean" and result["empty"] and result["hits"] == []
                   and "never padded" in result["note"],
                   "unknown number is a clean empty over this snapshot, not a guessed record")


@scenario("number_kind_no_substitution")
def _(tmp):
    result = run(CORPUS, {"application_number": "US10132852B2"})
    return outcome(result["empty"] and not has_rule(result, "patent.number_collision"),
                   "a grant/publication number must not be reused as an application number")


@scenario("status_cpc_and_not_filters")
def _(tmp):
    expired = run(CORPUS, {"status": "expired"})
    cpc = run(CORPUS, {"cpc": "C09D"})
    excluded = run(CORPUS, {"all": ["graphene"], "not": ["pyrolysis"],
                            "document_type": "patent"})
    return outcome(ids(expired) == ["pat-US9988776B2"]
                   and set(ids(cpc)) == {"pat-US10132852B2", "pat-EP3061620A1"}
                   and set(ids(excluded)) == {"pat-US10132852B2", "pat-EP3061620A1"},
                   "status is exact, CPC is hierarchical, and NOT is a hard exclusion")


@scenario("patent_paper_boundary")
def _(tmp):
    papers = run(CORPUS, {"all": ["graphene"], "document_type": "technical_paper"})
    patents = run(CORPUS, {"all": ["graphene"], "document_type": "patent"})
    return outcome(ids(papers) == ["paper-graphene-comparison"]
                   and set(ids(patents)) == {"pat-US10132852B2", "pat-EP3061620A1",
                                             "pat-WO2017166469A1"},
                   "technical papers and patent records share an index but remain separately filterable")


@scenario("duplicate_export_named")
def _(tmp):
    result = run(CORPUS, {"number": "EP3061620A1"})
    finding = next((f for f in result["findings"] if f["rule"] == "search.doc_skipped"), None)
    return outcome(ids(result) == ["pat-EP3061620A1"] and result["documents_indexed"] == 5
                   and finding and finding["count"] == 1 and result["status"] == "clean",
                   "duplicate id is named once and low severity does not force review")


@scenario("record_locator_verbatim")
def _(tmp):
    built = search.build_index(CORPUS)
    result = run(CORPUS, {"family_of": "US10132852B2", "family_scope": "simple",
                          "all": ["graphene"]})
    for hit in result["hits"]:
        paragraphs = built["index"]["documents"][hit["doc_id"]]["paragraphs"]
        if not hit["passages"]:
            return outcome(False, "hit has no evidence passage")
        for passage in hit["passages"]:
            loc = passage["locator"]
            if loc["doc_id"] != hit["doc_id"] or \
                    paragraphs[loc["paragraph"]][loc["start"]:loc["end"]] != loc["quote"]:
                return outcome(False, "quote is not a source slice")
    return outcome(True)


@scenario("deterministic_rerun")
def _(tmp):
    spec = {"corpus": CORPUS, "query": json.loads((EXAMPLES / "query.json").read_text(encoding="utf-8"))}
    first_index, first = search.search(spec)
    second_index, second = search.search(spec)
    return outcome(json.dumps(first, sort_keys=True, ensure_ascii=False) ==
                   json.dumps(second, sort_keys=True, ensure_ascii=False)
                   and json.dumps(first_index, sort_keys=True, ensure_ascii=False) ==
                   json.dumps(second_index, sort_keys=True, ensure_ascii=False),
                   "identical corpus+query must replay byte-equivalent JSON content")


@scenario("cli_refusal_exit5")
def _(tmp):
    bad = tmp / "bad.json"
    bad.write_text("{not json", encoding="utf-8")
    out = tmp / "refusal"
    proc = run_cli(out, query_file=bad)
    result = json.loads((out / "result.json").read_text(encoding="utf-8"))
    return outcome(proc.returncode == 5 and result["status"] == "undetermined"
                   and result["refusal"]["rule"] == "search.spec_unreadable"
                   and "Traceback" not in proc.stderr,
                   "malformed JSON must write undetermined and exit 5")


@scenario("refusal_no_contract_echo")
def _(tmp):
    case = write_json(tmp / "case.json", {
        "case_id": "refused-contract", "output_contract": ["unavailable_field"],
        "unavailable_field": "must not be copied"})
    bad = write_json(tmp / "bad-query.json", {"unknown_option": True})
    proc = run_cli(tmp / "out", query_file=bad, case=case)
    result = json.loads((tmp / "out" / "result.json").read_text(encoding="utf-8"))
    return outcome(proc.returncode == 5 and result["case_id"] == "refused-contract"
                   and "unavailable_field" not in result and "output_contract_fields" not in result
                   and result["status"] == "undetermined",
                   "refusal must not fabricate contract-shaped results")


@scenario("number_collision")
def _(tmp):
    docs = [patent("a"), patent("b")]
    result = run(docs, {"number": "US10000000B2"})
    return outcome(has_rule(result, "patent.number_collision") and result["status"] == "review"
                   and set(ids(result)) == {"a", "b"},
                   "same normalised number on distinct ids must not be silently merged")


@scenario("number_collision_fp_guard")
def _(tmp):
    docs = [patent("a"), patent("b", number="US10000000A1", grant_number=None,
                                application_number="US16000001")]
    result = run(docs, {"family": "F1"})
    return outcome(not has_rule(result, "patent.number_collision") and result["status"] == "clean",
                   "distinct kind-coded numbers and same-document publication/grant are not collisions")


@scenario("family_conflict")
def _(tmp):
    docs = [patent("a", family="F1"), patent("b", family="F2")]
    result = run(docs, {"family_of": "US10000000B2"})
    return outcome(has_rule(result, "patent.family_conflict")
                   and {f["family_id"] for f in result["families"]} == {"F1", "F2"},
                   "multiple declared family ids remain separate and reviewable")


@scenario("family_conflict_fp_guard")
def _(tmp):
    docs = [patent("a"), patent("b", number="EP10000000A1", grant_number=None)]
    result = run(docs, {"family_of": "US10000000B2", "family_scope": "simple"})
    return outcome(not has_rule(result, "patent.family_conflict") and set(ids(result)) == {"a", "b"},
                   "one declared simple-family id is not a conflict")


@scenario("family_missing")
def _(tmp):
    docs = [patent("a", family=None, members="EP10000000A1"),
            patent("b", number="EP10000000A1", grant_number=None, family="F2")]
    result = run(docs, {"family_of": "US10000000B2"})
    return outcome(has_rule(result, "patent.family_missing") and ids(result) == ["a"]
                   and result["status"] == "review",
                   "a members link must not substitute for a missing declared family id")


@scenario("family_missing_fp_guard")
def _(tmp):
    docs = [patent("a"), patent("b", number="EP10000000A1", grant_number=None)]
    result = run(docs, {"family_of": "US10000000B2"})
    return outcome(not has_rule(result, "patent.family_missing") and set(ids(result)) == {"a", "b"},
                   "declared family id supports expansion without a missing warning")


@scenario("date_missing")
def _(tmp):
    docs = [patent("a"), patent("b", number="EP10000000A1", grant_number=None,
                                priority_date=None, filing_date="2019-01-01")]
    result = run(docs, {"date_field": "priority_date", "date_from": "2019-01-01",
                        "date_to": "2021-12-31"})
    return outcome(ids(result) == ["a"] and has_rule(result, "patent.date_missing"),
                   "filing date must not fill a missing priority date")


@scenario("date_missing_fp_guard")
def _(tmp):
    docs = [patent("a"), patent("b", number="EP10000000A1", grant_number=None,
                                priority_date="2020-06-01")]
    result = run(docs, {"date_from": "2020-01-01", "date_to": "2020-12-31"})
    return outcome(set(ids(result)) == {"a", "b"} and not has_rule(result, "patent.date_missing"),
                   "present in-range priority dates produce no missing warning")


@scenario("date_invalid")
def _(tmp):
    docs = [patent("a"), patent("b", number="EP10000000A1", grant_number=None,
                                priority_date="2020-02-30")]
    result = run(docs, {"date_from": "2020-01-01", "date_to": "2020-12-31"})
    return outcome(ids(result) == ["a"] and has_rule(result, "patent.date_invalid"),
                   "impossible dates are excluded and named")


@scenario("date_invalid_fp_guard")
def _(tmp):
    docs = [patent("a", priority_date="2020"),
            patent("b", number="EP10000000A1", grant_number=None, priority_date="2020-06")]
    result = run(docs, {"date_from": "2020-01-01", "date_to": "2020-12-31"})
    return outcome(set(ids(result)) == {"a", "b"} and not has_rule(result, "patent.date_invalid")
                   and all(hit["dates"]["priority_date"][0]["valid"] for hit in result["hits"]),
                   "year/month precision is valid and is not promoted to a fake day")


@scenario("date_order")
def _(tmp):
    result = run([patent("a", priority_date="2022-01-01", filing_date="2021-01-01")],
                 {"number": "US10000000B2"})
    return outcome(has_rule(result, "patent.date_order") and result["status"] == "review",
                   "priority after filing is a metadata consistency warning")


@scenario("date_order_fp_guard")
def _(tmp):
    result = run([patent("a", priority_date="2020-01-01", filing_date="2021-01-01")],
                 {"number": "US10000000B2"})
    return outcome(not has_rule(result, "patent.date_order") and result["status"] == "clean",
                   "priority earlier than filing is valid")


@scenario("query_date_invalid")
def _(tmp):
    _, result = search.search({"corpus": [patent()],
                               "query": {"date_from": "2020-02-30"}})
    return outcome(result["status"] == "undetermined"
                   and result["refusal"]["rule"] == "patent.query_date_invalid",
                   "invalid query dates refuse before retrieval")


@scenario("query_date_invalid_fp_guard")
def _(tmp):
    result = run([patent()], {"date_from": "2020-01-01", "date_to": "2020-12-31"})
    return outcome(result["status"] == "clean" and ids(result) == ["p1"],
                   "valid inclusive date interval runs normally")


@scenario("status_unverified")
def _(tmp):
    result = run([patent(registry_verified="true", source_type="provided_snapshot")],
                 {"number": "US10000000B2", "require_current_status": True})
    return outcome(has_rule(result, "patent.status_unverified")
                   and result["hits"][0]["legal_status"]["current_status"] == "undetermined",
                   "a snapshot token is not current official legal status")


@scenario("status_unverified_fp_guard")
def _(tmp):
    result = run([patent(registry_verified="true", source_type="official_registry",
                         query_date="2026-01-15")],
                 {"number": "US10000000B2", "require_current_status": True})
    return outcome(not has_rule(result, "patent.status_unverified")
                   and result["hits"][0]["legal_status"]["registry_verified"] is True
                   and result["hits"][0]["legal_status"]["current_status"] == "pending",
                   "dated official-registry verification satisfies the declared evidence level")


@scenario("status_conflict")
def _(tmp):
    result = run([patent("a", status="pending"), patent("b", status="expired")],
                 {"number": "US10000000B2"})
    return outcome(has_rule(result, "patent.status_conflict") and result["status"] == "review",
                   "same-number records with different status tokens require adjudication")


@scenario("status_conflict_fp_guard")
def _(tmp):
    docs = [patent("a", status="pending"),
            patent("b", number="EP10000000A1", grant_number=None, status="expired")]
    result = run(docs, {"family": "F1"})
    return outcome(not has_rule(result, "patent.status_conflict") and result["status"] == "clean",
                   "different family members may legitimately have different legal states")


@scenario("claim_version_missing")
def _(tmp):
    docs = [patent("a", claim_version=None), patent("b", number="EP10000000A1", grant_number=None)]
    required = run([docs[0]], {"number": "US10000000B2", "require_claims": True})
    filtered = run(docs, {"claim_version": "publication-v1"})
    return outcome(has_rule(required, "patent.claim_version_missing")
                   and has_rule(filtered, "patent.claim_version_missing")
                   and ids(filtered) == ["b"],
                   "required or filtered claim versions must identify missing provenance")


@scenario("claim_version_missing_fp_guard")
def _(tmp):
    result = run([patent()], {"claim_version": "publication-v1", "require_claims": True})
    located = any(p["locator"].get("field") == "claim_version"
                  for p in result["hits"][0]["passages"])
    return outcome(not has_rule(result, "patent.claim_version_missing") and located,
                   "present claim version is returned with a source line locator")


@scenario("source_restricted_all_blocked")
def _(tmp):
    secret = patent("secret", Title="SECRET-CLAIM-TEXT", access="red")
    index, result = search.search({"corpus": [secret], "query": {"status": "pending"}})
    encoded = json.dumps(index, ensure_ascii=False) + json.dumps(result, ensure_ascii=False)
    return outcome(result["status"] == "blocked" and result["empty"]
                   and has_rule(result, "patent.source_restricted")
                   and result["documents_indexed"] == 0 and "SECRET-CLAIM-TEXT" not in encoded,
                   "all-restricted input blocks and no restricted text reaches either artifact")


@scenario("source_restricted_mixed_degrades")
def _(tmp):
    docs = [patent("open"), patent("secret", number="EP10000000A1", grant_number=None,
                                   access="red", Title="SECRET-CLAIM-TEXT")]
    index, result = search.search({"corpus": docs, "query": {"family": "F1"}})
    finding = next(f for f in result["findings"] if f["rule"] == "patent.source_restricted")
    return outcome(result["status"] == "review" and finding["severity"] == "medium"
                   and ids(result) == ["open"] and "SECRET-CLAIM-TEXT" not in json.dumps(index),
                   "mixed input returns authorised hits and explicitly marks the restricted gap")


@scenario("source_restricted_fp_guard")
def _(tmp):
    result = run([patent("open", access="green")], {"number": "US10000000B2"})
    return outcome(not has_rule(result, "patent.source_restricted") and result["status"] == "clean"
                   and result["hits"][0]["passages"],
                   "authorised green records are searchable and quotable")


@scenario("source_yellow_metadata_only")
def _(tmp):
    record = patent("yellow", access="yellow", display_scope="number,source",
                    Title="SECRET-YELLOW-CLAIM-TEXT")
    # Explicit scopes supplement default bibliographic identifiers; raw prose and
    # non-authorised labels are discarded before the index is written.
    index, result = search.search({"corpus": [record], "query": "US10000000B2"})
    blob = json.dumps(index, ensure_ascii=False) + json.dumps(result, ensure_ascii=False)
    return outcome(result["status"] == "review" and ids(result) == ["yellow"]
                   and has_rule(result, "patent.source_restricted")
                   and "SECRET-YELLOW-CLAIM-TEXT" not in blob
                   and result["display_limited"][0]["access"] == "yellow",
                   "yellow source must expose only authorised metadata, never raw prose")


@scenario("source_yellow_full_text_fp_guard")
def _(tmp):
    record = patent("yellow", access="yellow", display_scope="full_text")
    result = run([record], {"number": "US10000000B2", "all": ["Synthetic"],
                            "require_source_license": True})
    return outcome(result["status"] == "clean" and not has_rule(result, "patent.source_restricted")
                   and result["hits"][0]["passages"],
                   "explicit full_text scope permits normal authorised yellow processing")


@scenario("source_license_unknown")
def _(tmp):
    result = run([patent(license=None)], {"number": "US10000000B2",
                                         "require_source_license": True})
    return outcome(has_rule(result, "patent.source_license_unknown") and result["status"] == "review",
                   "requested licence evidence cannot be inferred from access to a file")


@scenario("source_license_unknown_fp_guard")
def _(tmp):
    result = run([patent()], {"number": "US10000000B2", "require_source_license": True})
    return outcome(not has_rule(result, "patent.source_license_unknown") and result["status"] == "clean",
                   "explicit licence and access fields satisfy the source check")


@scenario("field_missing")
def _(tmp):
    result = run([patent(source=None)], {"number": "US10000000B2",
                                        "require_fields": ["source", "priority_date"]})
    finding = next(f for f in result["findings"] if f["rule"] == "patent.field_missing")
    return outcome(finding["entries"] == [{"doc_id": "p1", "field": "source"}],
                   "only the actually absent required field is named")


@scenario("field_missing_fp_guard")
def _(tmp):
    result = run([patent()], {"number": "US10000000B2",
                              "require_fields": ["source", "priority_date"]})
    return outcome(not has_rule(result, "patent.field_missing") and result["status"] == "clean",
                   "present required metadata produces no finding")


@scenario("query_field_unknown")
def _(tmp):
    _, result = search.search({"corpus": [patent()], "query": {"famly": "F1"}})
    return outcome(result["status"] == "undetermined"
                   and result["refusal"]["rule"] == "patent.query_field_unknown",
                   "a misspelled filter must not be silently ignored")


@scenario("query_field_unknown_fp_guard")
def _(tmp):
    result = run([patent()], {"filters": {"number": "US10000000B2",
                                         "number_kind": "publication"}})
    return outcome(result["status"] == "clean" and ids(result) == ["p1"],
                   "declared filters object accepts supported patent fields")


@scenario("metadata_conflict")
def _(tmp):
    base = patent("a")
    base["publication_number"] = "US20000000A1"
    result = run([base], {"number": "US20000000A1", "all": ["Synthetic"]})
    finding = next(f for f in result["findings"] if f["rule"] == "patent.metadata_conflict")
    return outcome(result["status"] == "review" and finding["entries"][0]["text_value"]
                   and finding["entries"][0]["structured_value"] == "US20000000A1",
                   "structured-vs-text conflict retains both values and uses the declared override")


@scenario("metadata_conflict_fp_guard")
def _(tmp):
    base = patent("a")
    base["publication_number"] = "US10000000B2"
    result = run([base], {"number": "US10000000B2"})
    return outcome(not has_rule(result, "patent.metadata_conflict") and result["status"] == "clean",
                   "matching structured and text metadata are not a conflict")


@scenario("contract_field_missing")
def _(tmp):
    case = write_json(tmp / "case.json", {
        "case_id": "contract-gap", "output_contract": [{"name": "unavailable_field"}]})
    proc = run_cli(tmp / "out", case=case)
    result = json.loads((tmp / "out" / "result.json").read_text(encoding="utf-8"))
    return outcome(proc.returncode == 3 and result["unavailable_field"] is None
                   and has_rule(result, "patent.contract_field_missing")
                   and result["case_id"] == "contract-gap",
                   "missing contract values become null plus a review finding, never invented content")


@scenario("contract_field_missing_fp_guard")
def _(tmp):
    case = write_json(tmp / "case.json", {
        "case_id": "contract-ok",
        "output_contract": {"case_id": None, "results": None, "evidence": None, "run_state": None}})
    proc = run_cli(tmp / "out", case=case)
    result = json.loads((tmp / "out" / "result.json").read_text(encoding="utf-8"))
    return outcome(proc.returncode == 0 and not has_rule(result, "patent.contract_field_missing")
                   and result["results"] == result["检索结果"]
                   and result["evidence"] == result["证据记录"]
                   and result["run_state"] == result["状态说明"],
                   "dict contract and common aliases map to actual rubric sections without a gap")


@scenario("structured_record_without_text")
def _(tmp):
    record = {"id": "structured", "publication_number": "US 10,000,000 B2",
              "document_type": "patent", "family": ["F1"], "priority_date": "2020-01-01",
              "source": "structured synthetic record", "license": "fixture", "access": "green"}
    index, result = search.search({"corpus": [record], "query": "US10000000B2"})
    return outcome(ids(result) == ["structured"] and index["documents"]["structured"]["text"]
                   and result["hits"][0]["passages"],
                   "recognised structured metadata can be indexed without a pre-extracted text layer")


@scenario("cjk_applicant_and_unicode_locator")
def _(tmp):
    docs = [patent("zh", applicant="示例石墨烯研究院", Title="石墨烯涂层"),
            patent("other", number="EP10000000A1", grant_number=None, applicant="其他申请人",
                   Title="陶瓷涂层")]
    result = run(docs, {"applicant": "石墨烯", "all": ["涂层"]})
    quote_ok = all(p["locator"]["quote"] for h in result["hits"] for p in h["passages"])
    return outcome(ids(result) == ["zh"] and quote_ok,
                   "CJK applicant and title queries remain whole and locators retain UTF-8 text")


@scenario("index_replay")
def _(tmp):
    first_out = tmp / "first"
    first_proc = run_cli(first_out, case=EXAMPLES / "case.json")
    replay_out = tmp / "replay"
    replay_proc = run_cli(replay_out, index=first_out / "index.json",
                          case=EXAMPLES / "case.json")
    first = json.loads((first_out / "result.json").read_text(encoding="utf-8"))
    replay = json.loads((replay_out / "result.json").read_text(encoding="utf-8"))
    return outcome(first_proc.returncode == replay_proc.returncode == 0
                   and first["hits"] == replay["hits"]
                   and first["index_sha256"] == replay["index_sha256"],
                   "saved index supports an equivalent independent replay")


@scenario("internal_error_refusal")
def _(tmp):
    original = search.search
    try:
        def explode(spec):
            raise RuntimeError("hostile fixture")
        search.search = explode
        result = search_cli.run_files(EXAMPLES / "corpus.json", None, EXAMPLES / "query.json",
                                      None, tmp / "out", EXAMPLES / "case.json")
    finally:
        search.search = original
    return outcome(result["status"] == "undetermined" and result["case_id"] ==
                   "example-family-simple-v2" and result["refusal"]["rule"] == "search.internal_error"
                   and "delivery_note" not in result,
                   "unexpected engine failure is contained as undetermined without contract fabrication")


def main() -> int:
    rows = []
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        for number, (name, fn) in enumerate(SCENARIOS):
            try:
                case_tmp = tmp / str(number)
                case_tmp.mkdir(parents=True, exist_ok=True)
                value = fn(case_tmp)
                ok, why = value if isinstance(value, tuple) else (bool(value), "")
            except Exception as exc:
                ok, why = False, f"raised {type(exc).__name__}: {exc}"
            rows.append({"scenario": name, "pass": ok, "why": why})
            print(("PASS" if ok else "FAIL") + f"  {name:<38}" + ("" if ok else why))
    passed = sum(1 for row in rows if row["pass"])
    report = {"schema_version": "patent-bench/v2", "scenarios": rows,
              "totals": {"passed": passed, "of": len(rows)},
              "fp_guards": sum(name.endswith("fp_guard") for name, _ in SCENARIOS),
              "fixture_notice": "synthetic regression fixtures; not official case answers"}
    (Path(__file__).resolve().parent / "report_patent.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n{passed}/{len(rows)} scenarios pass")
    return 0 if passed == len(rows) else 1


if __name__ == "__main__":
    raise SystemExit(main())
