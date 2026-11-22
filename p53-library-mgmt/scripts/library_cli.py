"""CLI: ingest records into a research library and export the handover inventory.

    python library_cli.py --spec spec.json --out ./out [--query "缓冲液"]
                          [--case case.json] [--verify]

Writes out/library.json (the store: content + sha256 + folders + version links),
out/inventory.md (the human handover view), out/manifest.tsv (the archive
manifest: full 64-hex sha256 + byte length per document) and out/result.json
(the structured run result: counts, refusals, duplicate and sibling sets,
retrieval, meta provenance).

--case case.json echoes case_id and every output_contract field into
result.json (contract passthrough). --verify recomputes every stored hash
after export and records the self-check in result.json.

Exit codes: 0 ok (every record ingested), 4 partial (stored, some records
refused — limits listed in result.json), 5 undetermined (refusal: unreadable
spec/case, nothing ingestible, integrity mismatch), 2 usage. A refusal still
writes result.json — the refusal is a result, not a crash. The contract is
echoed only on the ok/partial path: on the refusal path the broken file may be
the case file itself, so nothing from it is echoed.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import library  # noqa: E402

# Contract fields whose VALUES are bulky material inputs, not deliverable
# metadata: they are echoed as null (and named in limits), never copied wholesale.
_BULKY = ("output_contract", "task", "materials", "documents", "records",
          "text", "files", "annotations")


def _write_result(out_dir: Path, result: dict) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "result.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")


def _refused(out_dir: Path, rule: str, message: str) -> dict:
    """The refusal result: honest undetermined, contract NOT echoed — the
    broken file may be the case file itself."""
    result = {"schema_version": library.SCHEMA_VERSION, "status": "undetermined",
              "refusal": {"rule": rule, "message": message},
              "limits": ["nothing was ingested into the library"]}
    _write_result(out_dir, result)
    return result


def _echo_contract(result: dict, case: dict, limits: list) -> None:
    """Contract passthrough (ok/partial path only): case_id plus every
    output_contract field. A field the result already carries is kept; a field
    the case supplies verbatim is copied unless bulky; a literal in the
    contract is backfilled; anything underivable is null and named in limits."""
    cid = case.get("case_id")
    if cid is None:
        cid = case.get("id")
    result["case_id"] = cid
    if cid is None:
        limits.append("case_id was not present in the case file")
    contract = case.get("output_contract")
    if isinstance(contract, dict):
        for key in contract:
            if key in result:
                continue
            if key in case and key not in _BULKY:
                result[key] = case[key]
                continue
            v = contract[key]
            if isinstance(v, (str, int, float, bool)) and \
                    (not isinstance(v, str) or len(v) <= 500):
                result[key] = v
                continue
            result[key] = None
            limits.append(f"output_contract field '{key}' was not derivable by this run")
    elif contract is not None:
        limits.append("output_contract was present but not an object, so no contract "
                      "fields were echoed")


def run_spec(spec_path: Path, out_dir: Path, query=None, case_path=None,
             verify=False) -> dict:
    limits: list = []
    try:
        spec = json.loads(Path(spec_path).read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError, OSError) as exc:
        return _refused(out_dir, "lib.spec_unreadable",
                        "the spec file is not readable JSON: " + str(exc))
    if not isinstance(spec, dict):
        return _refused(out_dir, "lib.spec_unreadable",
                        "the spec file is not a JSON object")
    if query:
        spec = dict(spec)
        spec["query"] = query

    case = None
    if case_path:
        try:
            case = json.loads(Path(case_path).read_text(encoding="utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError, OSError) as exc:
            return _refused(out_dir, "lib.case_unreadable",
                            "the case file is not readable JSON: " + str(exc))
        if not isinstance(case, dict):
            return _refused(out_dir, "lib.case_unreadable",
                            "the case file is not a JSON object")

    lib, result = library.run(spec, base_dir=str(Path(spec_path).resolve().parent))
    if lib is None:
        _write_result(out_dir, result)
        return result

    # Spec-carried values pass through: a case_id declared on the spec itself
    # is honoured when the case file did not provide one.
    if result.get("case_id") is None and isinstance(spec.get("case_id"), (str, int)):
        result["case_id"] = spec["case_id"]

    try:
        export = lib.export(out_dir, result)
    except OSError as exc:
        return _refused(out_dir, "lib.export_failed",
                        "the export could not be written (disk full or "
                        "permission denied?): " + str(exc))
    result["wrote"] = export["wrote"]

    if verify:
        vres = library.verify_store(out_dir / "library.json")
        if vres["ok"]:
            result["findings"].append({
                "rule": "lib.integrity_verified", "severity": "info",
                "count": vres["checked"],
                "why": "every stored sha256 was recomputed from the exported "
                       "text and matched — the archive is self-consistent"})
        else:
            return _refused(out_dir, "lib.integrity_mismatch",
                            "integrity self-check failed: " + str(vres["reason"]))

    if case is not None:
        _echo_contract(result, case, limits)
    if limits:
        result["limits"] = limits
    _write_result(out_dir, result)
    return result


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="library-mgmt", description=__doc__)
    ap.add_argument("--spec", required=True,
                    help="case spec JSON (structure + records[, meta_fields, query])")
    ap.add_argument("--out", required=True, help="output directory")
    ap.add_argument("--query", default=None,
                    help="optional retrieval query answered in result.json and inventory.md")
    ap.add_argument("--case", default=None,
                    help="case.json: echoes case_id and output_contract fields into result.json")
    ap.add_argument("--verify", action="store_true",
                    help="recompute every stored hash after export (integrity self-check)")
    a = ap.parse_args(argv)
    result = run_spec(Path(a.spec), Path(a.out), a.query, a.case, a.verify)
    print(json.dumps({"status": result.get("status"),
                      "refusal": result.get("refusal"),
                      "counts": result.get("counts"),
                      "case_id": result.get("case_id")}, ensure_ascii=False))
    # Exit codes: 0 ok, 4 partial, 5 undetermined (refusal), 2 usage.
    status = result.get("status")
    return {"ok": 0, "partial": 4, "undetermined": 5}.get(status, 5)


if __name__ == "__main__":
    raise SystemExit(main())
