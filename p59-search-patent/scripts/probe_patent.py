"""Thirty black-box hostile probes for the patent-search CLI.

Every probe requires an expected exit in {0,3,4,5}, a parseable result.json, and
no traceback on stdout/stderr.  Fixtures are synthetic and are not official answers.
Run: python -I -X utf8 scripts/probe_patent.py
"""

from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parent.parent
EXAMPLES = ROOT / "examples"
CLI = Path(__file__).resolve().parent / "search_cli.py"
PROBES = []


def probe(name, expected):
    def decorate(fn):
        PROBES.append((name, expected, fn))
        return fn
    return decorate


def dump(path, value, raw=False):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(str(value) if raw else json.dumps(value, ensure_ascii=False), encoding="utf-8")
    return path


def doc(doc_id="p1", **overrides):
    fields = {"Title": "Synthetic hostile fixture", "document_type": "patent",
              "number": "US10000000B2", "application_number": "US16" +
              str(sum((i + 1) * ord(c) for i, c in enumerate(doc_id)) % 1000000).zfill(6),
              "grant_number": "US10000000B2", "family": "F1", "inpadoc_family": "I1",
              "priority_date": "2020-01-01", "filing_date": "2021-01-01",
              "status": "pending", "status_date": "2026-01-15",
              "claim_version": "publication-v1", "source": "synthetic source",
              "source_type": "provided_snapshot", "query_date": "2026-01-15",
              "license": "synthetic licence", "access": "green"}
    fields.update(overrides)
    text = "\n".join(["id: " + doc_id] + [f"{key}: {value}" for key, value in fields.items()
                                          if value is not None])
    return {"id": doc_id, "text": text}


def command(tmp, corpus, query, case=None, index=False):
    source = dump(tmp / ("index.json" if index else "corpus.json"), corpus)
    query_file = dump(tmp / "query.json", query)
    args = ["--index" if index else "--corpus", str(source),
            "--query-file", str(query_file)]
    if case is not None:
        case_file = case if isinstance(case, Path) else dump(tmp / "case.json", case)
        args += ["--case", str(case_file)]
    return args


def yes(result, out, proc):
    return True, ""


def has(result, rule):
    return rule in {f.get("rule") for f in result.get("findings", [])}


@probe("example_contract_clean", 0)
def _(tmp):
    args = ["--corpus", str(EXAMPLES / "corpus.json"), "--query-file",
            str(EXAMPLES / "query.json"), "--case", str(EXAMPLES / "case.json")]
    return args, lambda r, o, p: (r.get("case_id") == "example-family-simple-v2"
                                  and len(r.get("hits", [])) == 2, "worked example contract")


@probe("unknown_number_clean_empty", 0)
def _(tmp):
    return command(tmp, json.loads((EXAMPLES / "corpus.json").read_text(encoding="utf-8")),
                   "US11111111B1"), lambda r, o, p: (r.get("empty") is True
                   and r.get("hits") == [], "unknown number must remain clean and empty")


@probe("inpadoc_scope_clean", 0)
def _(tmp):
    query = dict(json.loads((EXAMPLES / "query.json").read_text(encoding="utf-8")))
    query["family_scope"] = "inpadoc"
    return command(tmp, json.loads((EXAMPLES / "corpus.json").read_text(encoding="utf-8")), query), \
        lambda r, o, p: (len(r.get("hits", [])) == 3
                         and r["families"][0]["scope"] == "inpadoc", "INPADOC scope")


@probe("malformed_corpus_json", 5)
def _(tmp):
    corpus = dump(tmp / "bad.json", "{not json", raw=True)
    query = dump(tmp / "query.json", {"all": ["x"]})
    return ["--corpus", str(corpus), "--query-file", str(query)], yes


@probe("empty_corpus", 5)
def _(tmp):
    return command(tmp, [], {"all": ["x"]}), yes


@probe("corpus_wrong_shape", 5)
def _(tmp):
    return command(tmp, {"not_documents": []}, {"all": ["x"]}), yes


@probe("missing_corpus_file", 5)
def _(tmp):
    query = dump(tmp / "query.json", {"all": ["x"]})
    return ["--corpus", str(tmp / "absent.json"), "--query-file", str(query)], yes


@probe("malformed_query_json", 5)
def _(tmp):
    corpus = dump(tmp / "corpus.json", [doc()])
    query = dump(tmp / "query.json", "{bad", raw=True)
    return ["--corpus", str(corpus), "--query-file", str(query)], yes


@probe("empty_query", 5)
def _(tmp):
    return command(tmp, [doc()], {}), yes


@probe("unknown_query_field", 5)
def _(tmp):
    return command(tmp, [doc()], {"famly": "F1"}), yes


@probe("invalid_query_date", 5)
def _(tmp):
    return command(tmp, [doc()], {"date_from": "2020-02-30"}), yes


@probe("number_alias_conflict", 5)
def _(tmp):
    return command(tmp, [doc()], {"number": "US10000000B2",
                                  "publication_number": "US10000000B2"}), yes


@probe("index_root_not_object", 5)
def _(tmp):
    return command(tmp, [], {"all": ["x"]}, index=True), yes


@probe("index_malformed_entry", 5)
def _(tmp):
    idx = {"documents": {"x": {"text": "number: US10000000B2"}}, "order": ["x"]}
    return command(tmp, idx, {"all": ["x"]}, index=True), yes


@probe("index_duplicate_order", 5)
def _(tmp):
    idx = {"documents": {"x": {"text": "x", "paragraphs": ["x"]}},
           "order": ["x", "x"], "restricted": []}
    return command(tmp, idx, {"all": ["x"]}, index=True), yes


@probe("all_restricted_blocked_no_leak", 4)
def _(tmp):
    secret = doc("secret", access="red", Title="SECRET-CLAIM-TEXT")
    def check(result, out, proc):
        blobs = (out / "index.json").read_text(encoding="utf-8") + \
            (out / "result.json").read_text(encoding="utf-8")
        return result.get("documents_indexed") == 0 and has(result, "patent.source_restricted") \
            and "SECRET-CLAIM-TEXT" not in blobs, "restricted text must never be serialized"
    return command(tmp, [secret], {"status": "pending"}), check


@probe("mixed_restricted_review_no_leak", 3)
def _(tmp):
    docs = [doc("open"), doc("secret", number="EP10000000A1", grant_number=None,
                             access="red", Title="SECRET-CLAIM-TEXT")]
    def check(result, out, proc):
        blob = (out / "index.json").read_text(encoding="utf-8")
        return [h["doc_id"] for h in result.get("hits", [])] == ["open"] \
            and "SECRET-CLAIM-TEXT" not in blob, "authorised partial result only"
    return command(tmp, docs, {"family": "F1"}), check


@probe("yellow_metadata_review_no_leak", 3)
def _(tmp):
    record = doc("yellow", access="yellow", display_scope="number,source",
                 Title="SECRET-YELLOW-CLAIM-TEXT")
    def check(result, out, proc):
        blob = (out / "index.json").read_text(encoding="utf-8") + \
            (out / "result.json").read_text(encoding="utf-8")
        return has(result, "patent.source_restricted") \
            and "SECRET-YELLOW-CLAIM-TEXT" not in blob \
            and bool(result.get("display_limited")), "yellow raw text must be stripped before indexing"
    return command(tmp, [record], "US10000000B2"), check


@probe("current_status_unverified_review", 3)
def _(tmp):
    query = {"number": "US10000000B2", "require_current_status": True}
    return command(tmp, [doc(registry_verified="true")], query), \
        lambda r, o, p: (has(r, "patent.status_unverified")
                         and r["hits"][0]["legal_status"]["current_status"] == "undetermined",
                         "snapshot status cannot masquerade as current registry status")


@probe("dated_registry_verification_clean", 0)
def _(tmp):
    query = {"number": "US10000000B2", "require_current_status": True}
    record = doc(registry_verified="true", source_type="official_registry")
    return command(tmp, [record], query), \
        lambda r, o, p: (not has(r, "patent.status_unverified")
                         and r["hits"][0]["legal_status"]["current_status"] == "pending",
                         "dated registry evidence satisfies request")


@probe("claim_version_missing_review", 3)
def _(tmp):
    query = {"number": "US10000000B2", "require_claims": True}
    return command(tmp, [doc(claim_version=None)], query), \
        lambda r, o, p: (has(r, "patent.claim_version_missing"), "claim provenance must be explicit")


@probe("contract_missing_review", 3)
def _(tmp):
    case = {"case_id": "probe-contract-gap", "output_contract": ["unavailable_field"]}
    def check(result, out, proc):
        return result.get("unavailable_field", "absent") is None \
            and has(result, "patent.contract_field_missing"), "missing field becomes null+review"
    return command(tmp, [doc()], {"number": "US10000000B2"}, case=case), check


@probe("refusal_never_echoes_contract", 5)
def _(tmp):
    case = {"case_id": "probe-refusal", "output_contract": ["unavailable_field"],
            "unavailable_field": "forbidden echo"}
    def check(result, out, proc):
        return result.get("case_id") == "probe-refusal" and "unavailable_field" not in result \
            and "output_contract_fields" not in result, "no contract fabrication on refusal"
    return command(tmp, [doc()], {"unknown": True}, case=case), check


@probe("priority_date_missing_review", 3)
def _(tmp):
    docs = [doc("a"), doc("b", number="EP10000000A1", grant_number=None,
                          priority_date=None, filing_date="2019-01-01")]
    query = {"date_field": "priority_date", "date_from": "2019-01-01", "date_to": "2021-01-01"}
    return command(tmp, docs, query), \
        lambda r, o, p: (has(r, "patent.date_missing")
                         and [h["doc_id"] for h in r["hits"]] == ["a"],
                         "filing date cannot fill priority date")


@probe("invalid_document_date_review", 3)
def _(tmp):
    docs = [doc("a"), doc("b", number="EP10000000A1", grant_number=None,
                          priority_date="2020-02-30")]
    query = {"date_from": "2020-01-01", "date_to": "2020-12-31"}
    return command(tmp, docs, query), \
        lambda r, o, p: (has(r, "patent.date_invalid"), "invalid source date named")


@probe("metadata_conflict_review", 3)
def _(tmp):
    record = doc()
    record["publication_number"] = "US20000000A1"
    return command(tmp, [record], {"number": "US20000000A1", "all": ["Synthetic"]}), \
        lambda r, o, p: (has(r, "patent.metadata_conflict"), "both conflicting values retained")


@probe("source_license_unknown_review", 3)
def _(tmp):
    query = {"number": "US10000000B2", "require_source_license": True}
    return command(tmp, [doc(license=None)], query), \
        lambda r, o, p: (has(r, "patent.source_license_unknown"), "permission cannot be guessed")


@probe("non_object_case", 5)
def _(tmp):
    corpus = dump(tmp / "corpus.json", [doc()])
    query = dump(tmp / "query.json", {"all": ["Synthetic"]})
    case = dump(tmp / "case.json", [])
    return ["--corpus", str(corpus), "--query-file", str(query), "--case", str(case)], yes


@probe("cjk_source_locator_clean", 0)
def _(tmp):
    record = doc("zh", Title="石墨烯涂层", applicant="示例研究院")
    return command(tmp, [record], {"number": "US10000000B2", "all": ["涂层"]}), \
        lambda r, o, p: (len(r.get("hits", [])) == 1
                         and any("涂层" in passage["locator"]["quote"]
                                 for passage in r["hits"][0]["passages"]), "UTF-8 source quote")


@probe("deterministic_byte_replay", 0)
def _(tmp):
    args = ["--corpus", str(EXAMPLES / "corpus.json"), "--query-file",
            str(EXAMPLES / "query.json"), "--case", str(EXAMPLES / "case.json")]
    def check(result, out, proc):
        second = tmp / "second"
        rerun = subprocess.run([sys.executable, "-I", "-X", "utf8", str(CLI),
                                *args, "--out", str(second)], capture_output=True, text=True,
                               timeout=120)
        return rerun.returncode == 0 and (out / "result.json").read_bytes() == \
            (second / "result.json").read_bytes() and (out / "index.json").read_bytes() == \
            (second / "index.json").read_bytes(), "result and index must be byte-identical"
    return args, check


@probe("saved_index_replay", 0)
def _(tmp):
    args = ["--corpus", str(EXAMPLES / "corpus.json"), "--query-file",
            str(EXAMPLES / "query.json"), "--case", str(EXAMPLES / "case.json")]
    def check(result, out, proc):
        replay = subprocess.run([sys.executable, "-I", "-X", "utf8", str(CLI), "--index",
                                 str(out / "index.json"), "--query-file",
                                 str(EXAMPLES / "query.json"), "--case",
                                 str(EXAMPLES / "case.json"), "--out", str(tmp / "replay")],
                                capture_output=True, text=True, timeout=120)
        replay_result = json.loads((tmp / "replay" / "result.json").read_text(encoding="utf-8"))
        return replay.returncode == 0 and replay_result["hits"] == result["hits"] \
            and replay_result["index_sha256"] == result["index_sha256"], "index replay equivalence"
    return args, check


def main() -> int:
    rows = []
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        for number, (name, expected, builder) in enumerate(PROBES):
            tmp = root / str(number)
            tmp.mkdir(parents=True, exist_ok=True)
            out = tmp / "out"
            trace_free = False
            try:
                args, checker = builder(tmp)
                proc = subprocess.run([sys.executable, "-I", "-X", "utf8", str(CLI),
                                       *args, "--out", str(out)], capture_output=True,
                                      text=True, timeout=120)
                parseable = (out / "result.json").is_file()
                result = json.loads((out / "result.json").read_text(encoding="utf-8")) \
                    if parseable else {}
                trace_free = "Traceback" not in proc.stdout + proc.stderr
                extra_ok, detail = checker(result, out, proc)
                ok = bool(proc.returncode == expected and parseable and trace_free and extra_ok)
                why = "" if ok else (f"exit={proc.returncode} expected={expected}; "
                                     f"result={parseable}; traceback_free={trace_free}; {detail}")
            except Exception as exc:
                proc = None
                ok, why = False, f"probe harness caught {type(exc).__name__}: {exc}"
                result = {}
            rows.append({"probe": name, "expected_exit": expected,
                         "actual_exit": proc.returncode if proc else None,
                         "result_json": bool(result), "traceback_free": trace_free,
                         "pass": ok, "why": why})
            print(("PASS" if ok else "FAIL") + f"  {name:<40}" + ("" if ok else why))
    passed = sum(row["pass"] for row in rows)
    report = {"schema_version": "patent-probes/v1", "probes": rows,
              "totals": {"passed": passed, "of": len(rows)},
              "allowed_exits": [0, 3, 4, 5],
              "fixture_notice": "synthetic hostile probes; no official case output"}
    (Path(__file__).resolve().parent / "report_probe.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n{passed}/{len(rows)} probes pass")
    return 0 if passed == len(rows) else 1


if __name__ == "__main__":
    raise SystemExit(main())
