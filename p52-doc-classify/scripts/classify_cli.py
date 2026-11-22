"""CLI: classify a batch of research documents against a declared taxonomy.

    python classify_cli.py --spec spec.json --out ./out

Writes out/result.json (the full batch result: per-record labels with matched
cues, per-category summary, findings) and out/summary.md (the per-category
summary table). Exit codes: 0 run ok, 5 refused (unreadable spec, empty
taxonomy, no records), 2 usage. A refusal still writes result.json — the
refusal is a result, not a crash.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import classify  # noqa: E402


def _write_result(out_dir: Path, result: dict) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "result.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")


def run_spec(spec_path: Path, out_dir: Path, min_hits: int = 1) -> dict:
    try:
        spec = json.loads(Path(spec_path).read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError, OSError) as exc:
        result = {"schema_version": classify.SCHEMA_VERSION, "status": "undetermined",
                  "refusal": {"rule": "cls.spec_unreadable",
                              "message": "the spec file is not readable JSON: " + str(exc)},
                  "limits": ["the batch was not run; nothing was classified"]}
        _write_result(out_dir, result)
        return result
    if not isinstance(spec, dict):
        result = {"schema_version": classify.SCHEMA_VERSION, "status": "undetermined",
                  "refusal": {"rule": "cls.spec_unreadable",
                              "message": "the spec file is not a JSON object"},
                  "limits": ["the batch was not run; nothing was classified"]}
        _write_result(out_dir, result)
        return result
    result = classify.run(spec, min_hits)

    # Echo the case's contract: case_id at the top level, and every output_contract
    # field either carried by the result already, copied from the spec verbatim
    # (bulky inputs excluded), or filled as null with an honest limits note.
    cid = spec.get("case_id")
    if cid is not None:
        result["case_id"] = cid
    limits = result.setdefault("limits", [])
    oc = spec.get("output_contract")
    if isinstance(oc, dict):
        keys = list(oc.keys())
    elif isinstance(oc, list):
        keys = [str(k) for k in oc]
    else:
        keys = []
        if oc is not None:
            limits.append("output_contract is neither an object nor a list of "
                          "field names, so no contract fields were echoed")
    _bulky = ("output_contract", "taxonomy", "records", "text", "files", "paths")
    for key in keys:
        if key in result:
            continue
        if key in spec and key not in _bulky:
            result[key] = spec[key]
            continue
        result[key] = None
        limits.append(f"output_contract field '{key}' was not derivable by this audit")

    _write_result(out_dir, result)
    if result.get("status") == "ok":
        (out_dir / "summary.md").write_text(classify.render_summary_md(result),
                                            encoding="utf-8")
    return result


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="doc-classify", description=__doc__)
    ap.add_argument("--spec", required=True, help="case spec JSON (taxonomy + records)")
    ap.add_argument("--out", required=True, help="output directory")
    ap.add_argument("--min-hits", type=int, default=1,
                    help="cue hits a category needs to become a label (default 1)")
    a = ap.parse_args(argv)
    result = run_spec(Path(a.spec), Path(a.out), a.min_hits)
    print(json.dumps({"status": result.get("status"),
                      "refusal": result.get("refusal"),
                      "summary": result.get("summary")}, ensure_ascii=False))
    return 0 if result.get("status") == "ok" else 5


if __name__ == "__main__":
    raise SystemExit(main())
