"""Self-contained deterministic Nanopublication benchmark (synthetic only)."""
import copy, json, subprocess, sys, tempfile
from pathlib import Path
HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
CASE = ROOT / "examples/fixtures/synthetic_case.json"
DRAFT = ROOT / "examples/fixtures/synthetic_draft.json"
SOURCE = ROOT / "examples/fixtures/synthetic_source.txt"
CLI = HERE / "nanopub_build.py"


def run(root, case, draft, source=True):
    root = Path(root); root.mkdir(parents=True, exist_ok=True)
    case_path = root / "case.json"
    draft_path = root / "draft.json"
    case_path.write_text(case if isinstance(case, str) else json.dumps(case, ensure_ascii=False), encoding="utf-8")
    draft_path.write_text(draft if isinstance(draft, str) else json.dumps(draft, ensure_ascii=False), encoding="utf-8")
    cmd = [sys.executable, "-I", str(CLI), "--case", str(case_path), "--draft", str(draft_path), "--out", str(root / "out")]
    if source:
        cmd += ["--source", str(SOURCE)]
    cp = subprocess.run(cmd, capture_output=True, text=True, cwd=str(root))
    result_path = root / "out/result.json"
    result = json.loads(result_path.read_text(encoding="utf-8")) if result_path.exists() else None
    return cp, result


def scenario(name, fn):
    return {"scenario": name, "pass": bool(fn())}


def main():
    base_case = json.loads(CASE.read_text(encoding="utf-8"))
    base_draft = json.loads(DRAFT.read_text(encoding="utf-8"))
    rows = []
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        def clean():
            cp, r = run(root / "clean", base_case, base_draft)
            return cp.returncode == 0 and r["status"] == "success" and r["assertion_count"] == 2 and r["rdf_validation"]["valid"]
        rows.append(scenario("clean-baseline", clean))
        def deterministic():
            a = root / "det-a"; b = root / "det-b"
            cp1, r1 = run(a, base_case, base_draft); cp2, r2 = run(b, base_case, base_draft)
            if cp1.returncode != 0 or cp2.returncode != 0: return False
            return ((a / "out/nanopubs.trig").read_bytes() == (b / "out/nanopubs.trig").read_bytes() and
                    (a / "out/result.json").read_bytes() == (b / "out/result.json").read_bytes() and
                    (a / "out/evidence_map.md").read_bytes() == (b / "out/evidence_map.md").read_bytes())
        rows.append(scenario("deterministic-cold-repeat", deterministic))
        def evidence_gap():
            draft = copy.deepcopy(base_draft); draft["assertions"][0]["evidence"]["quote"] = "not in source"
            cp, r = run(root / "ev-gap", base_case, draft)
            return cp.returncode == 3 and r["status"] == "partial" and any("evidence.not_found" in x.get("code", "") for x in r["skipped_reason"]) and r["nanopubs"][0]["evidence"]["quote_verification"]["status"] == "not_found"
        rows.append(scenario("evidence-not-found-partial", evidence_gap))
        def metadata_gap():
            draft = copy.deepcopy(base_draft)
            draft.pop("publication_info"); draft["source_metadata"] = {"material_file": "only-local-name.txt"}
            cp, r = run(root / "meta-gap", base_case, draft)
            trig = (root / "meta-gap/out/nanopubs.trig").read_text(encoding="utf-8")
            codes = {x.get("code", "") for x in r["skipped_reason"]}
            return (cp.returncode == 3 and "unreported" in trig and "createdDateStatus" in trig and
                    "licenseStatus" in trig and "https://doi.org/" not in trig and "orcid.org/" not in trig and
                    "pubinfo.license_unreported" in codes)
        rows.append(scenario("missing-metadata-never-minted", metadata_gap))
        def duplicate_ids():
            draft = copy.deepcopy(base_draft); draft["assertions"][1]["id"] = "A1"
            cp, r = run(root / "dup", base_case, draft)
            return cp.returncode == 3 and r["assertion_count"] == 1 and any(x.get("code") == "assertion.duplicate_id" for x in r["skipped_reason"])
        rows.append(scenario("duplicate-id-not-reminted", duplicate_ids))
        def invalid_spo():
            draft = copy.deepcopy(base_draft); draft["assertions"] = [dict(draft["assertions"][0])]
            draft["assertions"][0].pop("subject")
            cp, r = run(root / "spo", base_case, draft)
            return cp.returncode == 5 and r["status"] == "failed" and r["refusal"]["code"] == "nanopub.no_valid_assertion" and r["summary"] == base_case["summary"]
        rows.append(scenario("incomplete-spo-refusal-and-contract", invalid_spo))
        def malformed_draft():
            cp, r = run(root / "bad-draft", base_case, "{bad")
            return cp.returncode == 5 and r["case_id"] == base_case["case_id"] and r["summary"] == base_case["summary"] and r["status"] == "failed"
        rows.append(scenario("malformed-draft-contract-preserved", malformed_draft))
        def malformed_case():
            cp, r = run(root / "bad-case", "{bad", base_draft)
            return cp.returncode == 5 and r["refusal"]["code"] == "nanopub.case_unreadable" and r["status"] == "failed"
        rows.append(scenario("malformed-case-structured-refusal", malformed_case))
        def supplied_uri():
            draft = copy.deepcopy(base_draft); draft["assertions"][0]["np_uri"] = "urn:fixture:caller-supplied-nanopub"
            cp, r = run(root / "uri", base_case, draft)
            return cp.returncode == 0 and r["nanopubs"][0]["uri"] == "urn:fixture:caller-supplied-nanopub" and not r["nanopubs"][0]["local_unpublished"]
        rows.append(scenario("supplied-uri-preserved", supplied_uri))
        def no_evidence_source():
            cp, r = run(root / "no-source", base_case, base_draft, source=False)
            return cp.returncode == 3 and all(x["evidence"]["quote_verification"]["status"] == "not_checked" for x in r["nanopubs"])
        rows.append(scenario("source-unavailable-not-verified", no_evidence_source))
        for row in rows:
            print(("PASS" if row["pass"] else "FAIL"), row["scenario"])
    passed = sum(r["pass"] for r in rows)
    print("%d/%d scenarios pass" % (passed, len(rows)))
    return 0 if passed == len(rows) else 1


if __name__ == "__main__":
    raise SystemExit(main())
